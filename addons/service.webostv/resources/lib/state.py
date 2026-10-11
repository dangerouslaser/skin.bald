"""TvState snapshot and its Window(10000) property publisher."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import xbmcgui

HOME_WINDOW = 10000
PREFIX = "WebOS."

SOUND_OUTPUT_LABELS = {
    "tv_speaker": "TV speaker",
    "external_arc": "HDMI ARC",
    "external_optical": "Optical",
    "bt_soundbar": "Bluetooth",
    "tv_external_speaker": "TV speaker + optical",
    "tv_speaker_headphone": "TV speaker + headphones",
    "headphone": "Headphones",
    "lineout": "Line out",
}


def sound_output_label(value: str) -> str:
    return SOUND_OUTPUT_LABELS.get(value, value.replace("_", " ").capitalize())


@dataclass(frozen=True)
class TvState:
    """Immutable snapshot of what the service knows about the TV."""

    connected: bool = False
    paired: bool = False
    host: str = ""
    power: str = ""
    is_on: bool = False
    screen_on: bool = False
    volume: int | None = None
    muted: bool | None = None
    app_id: str = ""
    app_title: str = ""
    input_id: str = ""
    input_label: str = ""
    sound_output: str = ""
    picture_preset: str = ""
    picture_supported: bool | None = None
    model: str = ""
    # Not published as properties; used by the UI and action resolution.
    apps: tuple[tuple[str, str], ...] = field(default=(), compare=False)
    inputs: tuple[tuple[str, str, str], ...] = field(default=(), compare=False)

    @classmethod
    def from_client(
        cls,
        tv_state: Any,
        *,
        connected: bool,
        paired: bool,
        host: str,
        picture_preset: str = "",
        picture_supported: bool | None = None,
        model: str = "",
    ) -> TvState:
        """Build a snapshot from aiowebostv's WebOsTvState."""
        app_id = tv_state.current_app_id or ""
        apps = tuple(
            (app_id_, str(app.get("title") or app_id_))
            for app_id_, app in (tv_state.apps or {}).items()
        )
        # aiowebostv keys inputs by appId; keep (input id, label, appId).
        inputs = tuple(
            (str(i.get("id", "")), str(i.get("label") or i.get("id", "")), app_id_)
            for app_id_, i in (tv_state.inputs or {}).items()
        )
        current_input = next((i for i in inputs if i[2] == app_id), None)
        # Unrenamed HDMI inputs aren't launch points; use the input label.
        title = dict(apps).get(app_id, "") or (current_input[1] if current_input else "")
        power = (tv_state.power_state or {}).get("state", "")
        if not power and connected:
            power = "Active" if tv_state.is_on else ""
        return cls(
            connected=connected,
            paired=paired,
            host=host,
            power=power if connected else "",
            is_on=bool(tv_state.is_on) if connected else False,
            screen_on=bool(tv_state.is_screen_on) if connected else False,
            volume=tv_state.volume,
            muted=tv_state.muted,
            app_id=app_id,
            app_title=title,
            input_id=current_input[0] if current_input else "",
            input_label=current_input[1] if current_input else "",
            sound_output=tv_state.sound_output or "",
            picture_preset=picture_preset,
            picture_supported=picture_supported,
            model=model,
            apps=apps,
            inputs=inputs,
        )

    def properties(self) -> dict[str, str]:
        """Window property values (without the WebOS. prefix)."""

        from .presets import label as preset_label  # noqa: PLC0415

        def flag(value: bool | None) -> str:
            return "" if value is None else ("true" if value else "false")

        return {
            "Connected": flag(self.connected),
            "Paired": flag(self.paired),
            "Host": self.host,
            "Power": self.power,
            "On": flag(self.is_on),
            "ScreenOn": flag(self.screen_on),
            "Volume": "" if self.volume is None else str(self.volume),
            "Muted": flag(self.muted),
            "App": self.app_id,
            "AppTitle": self.app_title,
            "Input": self.input_id,
            "InputLabel": self.input_label,
            "SoundOutput": self.sound_output,
            "SoundOutputLabel": sound_output_label(self.sound_output) if self.sound_output else "",
            "PicturePreset": self.picture_preset,
            "PicturePresetLabel": preset_label(self.picture_preset) if self.picture_preset else "",
            "Model": self.model,
            "PictureSupported": flag(self.picture_supported),
        }


class PropertyPublisher:
    """Writes TvState to Window(10000), touching only changed properties."""

    def __init__(self, window_id: int = HOME_WINDOW) -> None:
        self._window = xbmcgui.Window(window_id)
        self._last: dict[str, str] = {}

    def publish(self, state: TvState) -> list[str]:
        """Publish a snapshot; return the property names that changed."""
        changed = []
        for name, value in state.properties().items():
            if self._last.get(name) == value:
                continue
            if value:
                self._window.setProperty(PREFIX + name, value)
            else:
                self._window.clearProperty(PREFIX + name)
            self._last[name] = value
            changed.append(name)
        return changed

    def clear(self) -> None:
        for name in list(self._last):
            self._window.clearProperty(PREFIX + name)
        self._last.clear()
