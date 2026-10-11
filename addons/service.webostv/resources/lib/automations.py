"""Playback rules: pick the TV picture preset from Kodi's HDR type.

Runs on the service loop. The Kodi thread forwards player events with
``loop.call_soon_threadsafe(rules.av_started, hdr_type)`` / ``rules.stopped``.

One-shot overrides ("Play with Filmmaker Mode" and friends in the context
menu): ``arm()`` stores a request that the next playback session uses
instead of the rules: a picture preset, screen off while playing, and/or
turning the TV off when the video ends. Everything is undone on stop.

Restore semantics: webOS keeps separate picture-mode memories for SDR and
HDR signals. The preset to restore after playback is the SDR preset seen
while Kodi was idle (Kodi's GUI is SDR), not whatever the TV reported at
the moment playback began or ended, which may be an HDR or Dolby Vision
memory while the signal switches.

Timing: a preset only applies once the TV is on the matching signal (the
TV refuses an HDR preset on an SDR signal and vice versa). Before setting
one, wait until the TV reports a preset of the same family (SDR, HDR or
Dolby Vision), i.e. the signal has switched, then retry a few times if the
TV still doesn't take it.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from . import kodilog as log
from . import presets
from .errors import ActionError

if TYPE_CHECKING:
    from .settings import Settings
    from .tv import TvController

HDR_KINDS = ("sdr", "hdr10", "hlg", "dolbyvision")
# An armed override expires if playback doesn't start within this time.
ARM_TTL = 60.0
# Wait this long after a video ends before turning the TV off, so the next
# playlist item can start.
END_SETTLE = 5.0
# Wait up to this long for the TV to switch to the signal a preset needs.
SIGNAL_SETTLE = 8.0
SIGNAL_POLL = 0.25
# Attempts to set a preset, and the pause between them.
SET_ATTEMPTS = 3
RETRY_DELAY = 1.0
# TVs that won't report their picture mode can't tell when the signal has
# switched either: wait this long instead, then send the preset once.
BLIND_SIGNAL_DELAY = 4.0


def normalize_hdr_type(label: str) -> str | None:
    """Map VideoPlayer.HdrType to a rule key; None if unrecognized."""
    value = (label or "").strip().lower().replace(" ", "").replace("+", "plus")
    if value in ("", "sdr", "none"):
        return "sdr"
    if value in ("hdr10", "hdr10plus", "hdr"):
        return "hdr10"
    if value in ("dolbyvision", "dv"):
        return "dolbyvision"
    if value == "hlg":
        return "hlg"
    return None


class PlaybackRules:
    def __init__(self, controller: TvController, settings: Settings) -> None:
        self.controller = controller
        self.settings = settings
        current = controller.picture_preset
        self.idle_mode: str | None = current if current and presets.family(current) == "sdr" else None
        self.applied = False
        self._session = False
        self._pending: asyncio.Task | None = None
        self._armed: tuple[dict, float] | None = None
        self._override: dict | None = None
        self._screen_off = False
        self._ended = False
        self._busy = False
        self._stop_requested = False
        controller.picture_listeners.append(self._on_picture)

    def update(self, settings: Settings) -> None:
        self.settings = settings

    def presets(self) -> dict[str, str]:
        s = self.settings
        return {
            "sdr": s.preset_sdr,
            "hdr10": s.preset_hdr10,
            "hlg": s.preset_hlg,
            "dolbyvision": s.preset_dv,
        }

    def _on_picture(self, mode: str) -> None:
        # Only learn the "home" preset while nothing is playing, and only an
        # SDR one: right after playback the TV can briefly report its HDR or
        # Dolby Vision memory while switching back.
        if not self._session and presets.family(mode) == "sdr":
            self.idle_mode = mode

    def _schedule(self, coro_factory, delay: float | None = None) -> None:
        previous = self._pending
        if previous is not None and not previous.done() and not self._busy:
            # Still in its debounce delay: replace it.
            previous.cancel()
            previous = None
        self._pending = asyncio.ensure_future(self._delayed(coro_factory, delay, previous))

    async def _delayed(self, coro_factory, delay: float | None, previous) -> None:
        if previous is not None:
            # An apply/restore already talking to the TV runs to completion,
            # so stopping mid-apply still restores afterwards.
            with contextlib.suppress(Exception):
                await previous
        await asyncio.sleep(max(0.0, self.settings.rules_debounce if delay is None else delay))
        self._busy = True
        try:
            await coro_factory()
        finally:
            self._busy = False

    def arm(self, override: dict) -> dict:
        """Use this override for the next playback session.

        Keys: "picture" (intent or preset name, "" = rules as usual),
        "screen_off" (bool), "power_off_at_end" (bool).
        """
        loop = asyncio.get_running_loop()
        self._armed = (dict(override), loop.time() + ARM_TTL)
        log.info(f"next playback: {override}")
        return {"armed": override}

    def _take_armed(self) -> dict | None:
        armed, self._armed = self._armed, None
        if armed is None or asyncio.get_running_loop().time() > armed[1]:
            return None
        return armed[0]

    # events (loop thread) -------------------------------------------------

    def av_started(self, hdr_label: str) -> None:
        if not self._session:
            self._override = self._take_armed()
        self._session = True
        self._ended = False
        self._stop_requested = False
        kind = normalize_hdr_type(hdr_label)
        log.debug(f"video started, HdrType={hdr_label!r} -> {kind}")
        if kind is None and not self._override:
            log.info(f"unknown HdrType {hdr_label!r}; no picture rule applied")
            self._schedule(_noop)
            return
        self._schedule(lambda: self._apply(kind))

    def stopped(self) -> None:
        if not self._session:
            return
        log.debug("playback stopped")
        self._ended = False
        self._stop_requested = True
        self._schedule(self._restore)

    def ended(self) -> None:
        """Playback reached the end (not stopped by the user)."""
        if not self._session:
            return
        log.debug("playback ended")
        self._ended = True
        self._stop_requested = True
        delay = None
        if self._override and self._override.get("power_off_at_end"):
            delay = max(END_SETTLE, self.settings.rules_debounce)
        self._schedule(self._restore, delay)

    # actions --------------------------------------------------------------

    async def _target(self, kind: str | None) -> str:
        override = self._override or {}
        choice = override.get("picture") or ""
        if choice:
            try:
                modes = await self.controller.picture_modes()
            except ActionError:
                modes = []
            target = presets.resolve(presets.candidates(choice), kind, modes)
            if target is None:
                log.warning(f"no {choice!r} preset for {kind or 'this'} signal")
            return target or ""
        if not self.settings.rules_enabled or kind is None:
            return ""
        return self.presets().get(kind, "")

    async def _set_when_ready(self, target: str, *, abort=lambda: False) -> str | None:
        """Set a preset once the TV is on its signal; return an error or None."""
        loop = asyncio.get_running_loop()
        if self.controller.picture_readable is False:
            deadline = loop.time() + BLIND_SIGNAL_DELAY
            while loop.time() < deadline and not abort():
                await asyncio.sleep(SIGNAL_POLL)
            if abort():
                return "playback stopped"
            try:
                await self.controller.set_picture_mode(target)
            except ActionError as err:
                return err.message
            return None
        wanted = presets.family(target)
        deadline = loop.time() + SIGNAL_SETTLE
        while (
            presets.family(self.controller.picture_preset or target) != wanted
            and loop.time() < deadline
            and not abort()
        ):
            await asyncio.sleep(SIGNAL_POLL)
        if abort():
            return "playback stopped"
        error = ""
        for attempt in range(SET_ATTEMPTS):
            if self.controller.picture_preset == target:
                return None
            try:
                await self.controller.set_picture_mode(target)
                return None
            except ActionError as err:
                error = err.message
            if attempt + 1 < SET_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY)
                if abort():
                    return "playback stopped"
        return error

    async def _apply(self, kind: str | None) -> None:
        if not self.controller.connected:
            return
        target = await self._target(kind)
        if target and self.controller.picture_preset != target:
            error = await self._set_when_ready(target, abort=lambda: self._stop_requested)
            if error:
                log.warning(f"{kind} playback: cannot set preset {target!r}: {error}")
            else:
                self.applied = True
                log.info(f"{kind} playback: picture preset {target}")
        await self._apply_screen()

    async def _apply_screen(self) -> None:
        if (self._override or {}).get("screen_off") and not self._screen_off:
            try:
                await self.controller.screen(False)
                self._screen_off = True
                log.info("screen off for this playback")
            except ActionError as err:
                log.warning(f"cannot turn the screen off: {err.message}")

    async def _restore(self) -> None:
        override, self._override = self._override, None
        ended, self._ended = self._ended, False
        try:
            restore = self.applied and (
                bool(override) or (self.settings.rules_enabled and self.settings.restore_on_stop)
            )
            target = self.idle_mode
            if restore and target and self.controller.connected:
                if self.controller.picture_preset != target:
                    error = await self._set_when_ready(target)
                    if error:
                        log.warning(f"cannot restore preset {target!r}: {error}")
                    else:
                        log.info(f"playback ended: restored picture preset {target}")
            if self._screen_off and self.controller.connected:
                with contextlib.suppress(ActionError):
                    await self.controller.screen(True)
            if override and override.get("power_off_at_end") and ended:
                log.info("video finished; turning the TV off")
                try:
                    await self.controller.power_off()
                except ActionError as err:
                    log.warning(f"cannot turn the TV off: {err.message}")
        finally:
            self.applied = False
            self._screen_off = False
            self._session = False

    async def close(self) -> None:
        if self._pending is not None and not self._pending.done():
            self._pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pending
        with contextlib.suppress(ValueError):
            self.controller.picture_listeners.remove(self._on_picture)


async def _noop() -> None:
    return None
