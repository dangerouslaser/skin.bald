"""WebOsService: asyncio loop thread, Kodi Monitor, IPC dispatch.

The Kodi thread never does network I/O. Monitor callbacks hand work to
the loop with run_coroutine_threadsafe; the loop thread owns TvController.
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from concurrent.futures import Future
from typing import Any

import xbmc
import xbmcaddon
import xbmcgui

from . import bootstrap, ipc
from . import kodilog as log
from .errors import ActionError, BadRequest
from .settings import Settings

ADDON_ID = "service.webostv"
ADDON_NAME = "LG webOS TV"
SHUTDOWN_TIMEOUT = 2.0
LOCK_FILE = "service.lock"


class _Monitor(xbmc.Monitor):
    def __init__(self, service: WebOsService) -> None:
        super().__init__()
        self._service = service

    def onNotification(self, sender: str, method: str, data: str) -> None:  # noqa: N802
        parsed = ipc.parse_notification(sender, method, data)
        if parsed is None or parsed[0] != ipc.REQUEST:
            return
        self._service.handle_request(parsed[1])

    def onSettingsChanged(self) -> None:  # noqa: N802
        self._service.reload_settings()


class _Player(xbmc.Player):
    """Forwards video playback events to the playback rules on the loop."""

    def __init__(self, service: WebOsService) -> None:
        super().__init__()
        self._service = service

    def onAVStarted(self) -> None:  # noqa: N802
        if self.isPlayingVideo():
            self._service.player_event("av_started", xbmc.getInfoLabel("VideoPlayer.HdrType"))

    def onPlayBackStopped(self) -> None:  # noqa: N802
        self._service.player_event("stopped")

    def onPlayBackEnded(self) -> None:  # noqa: N802
        self._service.player_event("ended")

    def onPlayBackError(self) -> None:  # noqa: N802
        self._service.player_event("stopped")


def _log_task_error(task: Any) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.warning(f"background task failed: {task.exception()!r}")


class _KodiSide:
    """What the TV watcher may do to Kodi (called from the loop thread)."""

    def __init__(self, service: WebOsService) -> None:
        self._service = service

    def is_playing(self) -> bool:
        return xbmc.getCondVisibility("Player.Playing")

    def is_paused(self) -> bool:
        return xbmc.getCondVisibility("Player.Paused")

    def pause(self) -> None:
        if self.is_playing():
            xbmc.executebuiltin("PlayerControl(Play)")  # toggles

    def resume(self) -> None:
        if self.is_paused():
            xbmc.executebuiltin("PlayerControl(Play)")

    def stop(self) -> None:
        xbmc.executebuiltin("PlayerControl(Stop)")

    def shutdown(self) -> None:
        # Kodi's own shutdown function (Settings > System > Power saving).
        xbmc.executebuiltin("ShutDown()")

    def set_overlay(self, active: bool) -> None:
        # The "home" action (another process) reads this.
        window = xbmcgui.Window(10000)
        if active:
            window.setProperty("WebOS.TransparentControl", "true")
        else:
            window.clearProperty("WebOS.TransparentControl")
        if self._service.overlay is not None:
            self._service.overlay.set_active(active)

    def save_setting(self, key: str, value: str) -> None:
        xbmcaddon.Addon(ADDON_ID).setSetting(key, value)


class WebOsService:
    def __init__(self) -> None:
        self.settings = Settings.load()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self.controller: Any = None
        self.publisher: Any = None
        self.monitor: _Monitor | None = None
        self.player: _Player | None = None
        self.rules: Any = None
        self.watcher: Any = None
        self._inputs: tuple = ()
        self._launcher_key: tuple = ()
        self._lock_fd: int | None = None
        self.overlay: Any = None

    # entry ---------------------------------------------------------------

    def run(self) -> None:
        """Start, block until Kodi asks us to abort, then shut down."""
        if not self.start():
            return
        assert self.monitor is not None
        self.monitor.waitForAbort()
        self.shutdown()

    def start(self) -> bool:
        if not bootstrap.python_supported():
            version = ".".join(map(str, sys.version_info[:3]))
            log.error(f"Python {version} is too old; aiowebostv needs 3.11+. Service disabled.")
            self.notify("error", f"Needs Python 3.11+ (found {version})")
            return False

        bootstrap.install()
        log.set_debug(self.settings.debug)
        log.install_handler()
        if not self._acquire_instance_lock():
            # Kodi can start a service twice when it's installed while Kodi
            # runs; two copies would fight over the TV and run every action twice.
            log.warning("another copy of the service is already running; this one exits")
            return False

        # Lazy imports: only pay for aiowebostv/websockets once we know we run.
        from .automations import PlaybackRules  # noqa: PLC0415
        from .remote import Overlay  # noqa: PLC0415
        from .state import PropertyPublisher  # noqa: PLC0415
        from .tv import TvController  # noqa: PLC0415
        from .watcher import TvWatcher  # noqa: PLC0415

        self.publisher = PropertyPublisher()
        self.overlay = Overlay(self.forward, lambda: self.settings.kodi_input)
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._loop_main, name="webostv-loop", daemon=True)
        self.thread.start()

        async def create() -> None:
            # WebOsClient calls get_running_loop() in __init__, so the
            # controller (which builds clients) is created on the loop.
            self.controller = TvController(
                self.settings,
                on_state=self._on_state,
                on_mac=self.save_mac,
                on_host=self.save_host,
                notify=self.notify,
            )
            await self.controller.start()
            self.rules = PlaybackRules(self.controller, self.settings)
            self.watcher = TvWatcher(self.controller, self.settings, _KodiSide(self))

        self._submit(create()).result(timeout=5)
        self.publish_setting_labels()
        self.monitor = _Monitor(self)
        self.player = _Player(self)
        log.info(
            f"service started (host {self.settings.host}, "
            f"Python {sys.version.split()[0]}, "
            f"Kodi {xbmc.getInfoLabel('System.BuildVersion') or 'unknown'})"
        )
        return True

    def _acquire_instance_lock(self) -> bool:
        try:
            import fcntl  # noqa: PLC0415
        except ImportError:  # Windows: no flock; rely on Kodi
            return True
        from . import storage  # noqa: PLC0415

        path = storage.data_path(LOCK_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self._lock_fd = fd
        return True

    def _release_instance_lock(self) -> None:
        if self._lock_fd is not None:
            os.close(self._lock_fd)  # closing releases the flock
            self._lock_fd = None

    def _loop_main(self) -> None:
        assert self.loop is not None
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def shutdown(self) -> None:
        log.info("service stopping")
        if self.loop is None:
            return
        for part in (self.watcher, self.rules):
            if part is None:
                continue
            try:
                self._submit(part.close()).result(timeout=SHUTDOWN_TIMEOUT)
            except Exception:  # noqa: BLE001
                pass
        if self.overlay is not None:
            self.overlay.close()
        if self.controller is not None:
            try:
                self._submit(self.controller.stop()).result(timeout=SHUTDOWN_TIMEOUT)
            except Exception as err:  # noqa: BLE001
                log.warning(f"controller stop did not finish cleanly: {err!r}")
        self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread is not None:
            self.thread.join(SHUTDOWN_TIMEOUT)
        if self.publisher is not None:
            self.publisher.clear()
        self._release_instance_lock()
        self.monitor = None
        self.player = None
        self.loop = None

    def _submit(self, coro: Any) -> Future:
        assert self.loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    # Kodi callbacks (Kodi thread) ---------------------------------------

    def _on_state(self, state: Any) -> None:
        """Loop thread: every TvState the controller publishes."""
        self.publisher.publish(state)
        # Refresh launcher.json (plugin listings) when apps or inputs change.
        key = (tuple(a for a, _t in state.apps), tuple(i[0] for i in state.inputs))
        if state.connected and state.apps and key != self._launcher_key:
            self._launcher_key = key
            from . import launcher  # noqa: PLC0415

            try:
                points = self.controller.launch_points()
            except ActionError:
                return
            task = asyncio.ensure_future(launcher.refresh(points))
            task.add_done_callback(_log_task_error)
        # Input names arrive after connecting; refresh WebOS.KodiInput.
        if state.inputs and state.inputs != self._inputs:
            self._inputs = state.inputs
            self.publish_setting_labels()

    def publish_setting_labels(self) -> None:
        """WebOS.Rule.<kind>: friendly name of each HDR rule preset (skins)."""
        from .presets import label  # noqa: PLC0415

        window = xbmcgui.Window(10000)
        s = self.settings
        # Kodi's input, with the TV's name for it when known.
        kodi_input = s.kodi_input
        state = getattr(self.controller, "state", None)
        for input_id, input_label, _app in getattr(state, "inputs", ()):
            if input_id == kodi_input and input_label != input_id:
                kodi_input = f"{input_label} ({input_id})"
        for key, value in (("KodiInput", kodi_input), ("ConfiguredHost", s.host)):
            if value:
                window.setProperty(f"WebOS.{key}", value)
            else:
                window.clearProperty(f"WebOS.{key}")
        for kind, value in (("SDR", s.preset_sdr), ("HDR10", s.preset_hdr10),
                            ("HLG", s.preset_hlg), ("DolbyVision", s.preset_dv)):
            if value:
                window.setProperty(f"WebOS.Rule.{kind}", label(value))
            else:
                window.clearProperty(f"WebOS.Rule.{kind}")

    def reload_settings(self) -> None:
        settings = Settings.load()
        log.set_debug(settings.debug)
        if settings == self.settings:
            return
        self.settings = settings
        self.publish_setting_labels()
        if self.loop is not None:
            for part in (self.rules, self.watcher):
                if part is not None:
                    self.loop.call_soon_threadsafe(part.update, settings)
            # Someone is changing settings in Kodi's UI, so the TV is
            # showing Kodi right now: a good moment to learn its input.
            if self.watcher is not None:
                self.loop.call_soon_threadsafe(self.watcher.learn_input, "settings changed")
        if self.controller is not None:
            self._submit(self.controller.reconfigure(settings))

    def player_event(self, event: str, *args: Any) -> None:
        if self.loop is None or self.rules is None:
            return
        self.loop.call_soon_threadsafe(getattr(self.rules, event), *args)
        if event == "av_started" and self.watcher is not None:
            self.loop.call_soon_threadsafe(self.watcher.video_started)

    def forward(self, name: str, args: list[Any]) -> None:
        """Run an action for transparent control; no reply, errors logged."""
        if self.loop is None or self.controller is None:
            return
        from . import actions  # noqa: PLC0415

        async def run() -> None:
            try:
                await actions.dispatch(self.controller, name, args)
            except ActionError as err:
                log.debug(f"forwarded {name} failed: {err.message}")

        self._submit(run())

    def handle_request(self, request: dict[str, Any]) -> Future | None:
        if self.loop is None or self.controller is None:
            return None
        return self._submit(self._run_request(request))

    # loop thread ---------------------------------------------------------

    async def _run_request(self, request: dict[str, Any]) -> dict[str, Any]:
        from . import actions  # noqa: PLC0415

        request_id = str(request.get("id"))
        name = str(request.get("action", ""))
        args = request.get("args") or []
        if not isinstance(args, list):
            args = [args]
        log.debug(f"request {name} {args}")
        try:
            result = await actions.dispatch(self.controller, name, args, rules=self.rules)
            if name == "status" and self.watcher is not None:
                result = {**result, **self.watcher.status()}
            reply = ipc.reply_ok(request_id, result)
        except ActionError as err:
            level = log.info if isinstance(err, BadRequest) else log.warning
            level(f"{name} failed: {err.code}: {err.message}")
            reply = ipc.reply_error(request_id, err.code, err.message)
        except Exception as err:  # noqa: BLE001
            log.error(f"{name} crashed: {err!r}")
            reply = ipc.reply_error(request_id, "internal_error", repr(err))
        if not reply["ok"] and request.get("notify_errors"):
            self.notify("error", f"{name}: {reply['message']}")
        ipc.notify_all(ipc.REPLY, reply)
        return reply

    def save_mac(self, mac: str) -> None:
        """Persist a learned MAC (triggers onSettingsChanged -> reload)."""
        xbmcaddon.Addon(ADDON_ID).setSetting("mac", mac)

    def save_host(self, host: str) -> None:
        """Persist a host found by discovery (no reconnect: already there)."""
        xbmcaddon.Addon(ADDON_ID).setSetting("host", host)

    def notify(self, kind: str, message: str) -> None:
        icon = xbmcgui.NOTIFICATION_ERROR if kind == "error" else xbmcgui.NOTIFICATION_INFO
        xbmcgui.Dialog().notification(ADDON_NAME, message, icon, 5000, False)
