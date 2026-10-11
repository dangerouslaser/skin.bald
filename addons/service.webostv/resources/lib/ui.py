"""Program UI: select dialogs that drive the service over IPC."""

from __future__ import annotations

import asyncio
from typing import Any

import xbmc
import xbmcaddon
import xbmcgui

from . import ipc, lang

ADDON_NAME = "LG webOS TV"

SOUND_OUTPUTS = (
    "tv_speaker",
    "external_arc",
    "external_optical",
    "bt_soundbar",
    "tv_external_speaker",
    "tv_speaker_headphone",
    "headphone",
    "lineout",
)

# Shown in this order; the full list lives in aiowebostv/buttons.py.
REMOTE_BUTTONS = (
    "HOME", "BACK", "UP", "DOWN", "LEFT", "RIGHT", "ENTER", "EXIT",
    "MENU", "QMENU", "INFO", "INPUT_HUB", "GUIDE",
    "PLAY", "PAUSE", "STOP", "REWIND", "FASTFORWARD",
    "VOLUMEUP", "VOLUMEDOWN", "MUTE", "CHANNELUP", "CHANNELDOWN",
    "RED", "GREEN", "YELLOW", "BLUE", "ASPECT_RATIO", "CC", "POWER",
)


def _dialog() -> xbmcgui.Dialog:
    return xbmcgui.Dialog()


def _call(action: str, args: list[Any] | None = None) -> dict[str, Any] | None:
    reply = ipc.call(action, args)
    if reply.get("ok"):
        return reply
    message = reply.get("message") or lang.get(lang.ACTION_FAILED)
    if reply.get("error") == "timeout":
        message = lang.get(lang.NOT_RUNNING)
    _dialog().notification(ADDON_NAME, message, xbmcgui.NOTIFICATION_ERROR)
    return None


def pages() -> dict[str, Any]:
    """Entry points for RunScript(service.webostv,ui,<page>) (skins)."""
    return {
        "input": choose_input,
        "app": choose_app,
        "sound_output": choose_sound_output,
        "picture_preset": choose_picture_preset,
        "volume": choose_volume,
        "remote": remote,
        "toast": send_toast,
        "status": status,
        "find_tv": find_tv,
        "repair": repair,
    }


def run_page(name: str) -> None:
    page = pages().get(name.strip().lower())
    if page is None:
        run()
    else:
        page()


def run() -> None:
    menu = (
        (lang.INPUTS, choose_input),
        (lang.APPS, choose_app),
        (lang.SOUND_OUTPUT, choose_sound_output),
        (lang.PICTURE_PRESET, choose_picture_preset),
        (lang.BUTTONS, remote),
        (lang.SEND_TOAST, send_toast),
        (lang.STATUS, status),
        (lang.FIND_TV, find_tv),
        (lang.REPAIR, repair),
    )
    while True:
        index = _dialog().select(ADDON_NAME, [lang.get(label) for label, _ in menu])
        if index < 0:
            return
        menu[index][1]()


def _mark(label: str, current: bool) -> str:
    return f"{label}  [{lang.get(lang.CURRENT)}]" if current else label


def choose_input() -> None:
    reply = _call("catalog")
    if not reply:
        return
    catalog = reply["result"]
    inputs = catalog.get("inputs", [])
    labels = [_mark(i["label"], i["app_id"] == catalog.get("current_app")) for i in inputs]
    index = _dialog().select(lang.get(lang.INPUTS), labels)
    if index >= 0:
        _call("input", [inputs[index]["id"]])


def choose_app() -> None:
    reply = _call("catalog")
    if not reply:
        return
    catalog = reply["result"]
    apps = catalog.get("apps", [])
    labels = [_mark(a["title"], a["id"] == catalog.get("current_app")) for a in apps]
    index = _dialog().select(lang.get(lang.APPS), labels)
    if index >= 0:
        _call("app", [apps[index]["id"]])


def choose_sound_output() -> None:
    reply = _call("catalog")
    if not reply:
        return
    current = reply["result"].get("sound_output")
    outputs = list(SOUND_OUTPUTS)
    if current and current not in outputs:
        outputs.insert(0, current)
    from .state import sound_output_label  # noqa: PLC0415

    labels = [_mark(sound_output_label(o), o == current) for o in outputs]
    index = _dialog().select(lang.get(lang.SOUND_OUTPUT), labels)
    if index >= 0:
        _call("sound_output", [outputs[index]])


def choose_picture_preset() -> None:
    """Pick a preset valid for what the TV is showing right now."""
    from . import presets  # noqa: PLC0415

    reply = _call("picture_modes")
    if not reply:
        return
    current = reply["result"].get("current") or ""
    modes = reply["result"].get("modes", [])
    if reply["result"].get("readable", True):
        values = [m["value"] for m in modes if m.get("visible")]
    else:
        # The TV can't say which presets fit the current signal; use Kodi's.
        from .automations import normalize_hdr_type  # noqa: PLC0415

        kind = "sdr"
        if xbmc.getCondVisibility("Player.HasVideo"):
            kind = normalize_hdr_type(xbmc.getInfoLabel("VideoPlayer.HdrType")) or "sdr"
        values = presets.for_kind(kind, [m["value"] for m in modes])
    if not values:
        return
    labels = [_mark(presets.label(v), v == current) for v in values]
    index = _dialog().select(lang.get(lang.PICTURE_PRESET), labels)
    if index >= 0:
        _call("picture_preset", [values[index]])


def _back_to_settings(stay: bool) -> None:
    # Settings dialog buttons close the dialog; reopen it unless called
    # from a skin page ("stay").
    if not stay:
        xbmc.executebuiltin("Addon.OpenSettings(service.webostv)")


def choose_rule_preset(kind: str, stay: bool = False) -> None:
    """Settings button: pick the preset a playback rule applies."""
    from . import presets  # noqa: PLC0415

    kind = kind.strip().lower()
    setting_id = presets.SETTING_IDS.get(kind)
    if setting_id is None:
        return
    reply = _call("picture_modes")
    if not reply:
        return
    values = presets.for_kind(kind, [m["value"] for m in reply["result"].get("modes", [])])
    addon = xbmcaddon.Addon("service.webostv")
    current = addon.getSetting(setting_id)
    options = [""] + values
    labels = [_mark(lang.get(lang.NO_CHANGE), current == "")] + [
        _mark(presets.label(v), v == current) for v in values
    ]
    index = _dialog().select(lang.get(lang.PICTURE_PRESET), labels)
    if index >= 0:
        addon.setSetting(setting_id, options[index])
    _back_to_settings(stay)


def choose_kodi_input(stay: bool = False) -> None:
    """Settings button: which TV input Kodi's box is plugged into."""
    reply = _call("catalog")
    addon = xbmcaddon.Addon("service.webostv")
    if reply:
        current = addon.getSetting("kodi_input")
        inputs = reply["result"].get("inputs", [])
        options = [""] + [i["id"] for i in inputs]
        labels = [_mark(lang.get(lang.AUTOMATIC), current == "")] + [
            _mark(f"{i['label']} ({i['id']})" if i["label"] != i["id"] else i["id"], i["id"] == current)
            for i in inputs
        ]
        index = _dialog().select(lang.get(lang.KODI_INPUT), labels)
        if index >= 0:
            addon.setSetting("kodi_input", options[index])
    _back_to_settings(stay)


def choose_volume() -> None:
    reply = _call("status")
    if not reply:
        return
    current = reply["result"].get("volume")
    text = _dialog().numeric(0, lang.get(lang.VOLUME), "" if current is None else str(current))
    if text and text.isdigit():
        _call("volume", [str(min(100, int(text)))])


# Settings a skin page may change: bools toggle, options open a picker.
EDITABLE_BOOLS = {
    "rules_enabled", "restore_on_stop", "resume_on_return", "transparent_control",
    "toast_on_connect", "auto_discover", "loopback_fallback", "debug",
}
EDITABLE_OPTIONS = {
    "on_tv_off": (32210, 32211, 32212, 32213),
    "on_switch_away": (32210, 32211, 32212),
}
OPTION_HEADINGS = {"on_tv_off": 32203, "on_switch_away": 32204}


def change_setting(key: str) -> None:
    """RunScript(service.webostv,setting,<id>): toggle or pick a value."""
    key = key.strip()
    addon = xbmcaddon.Addon("service.webostv")
    if key in EDITABLE_BOOLS:
        addon.setSetting(key, "false" if addon.getSettingBool(key) else "true")
    elif key in EDITABLE_OPTIONS:
        labels = [addon.getLocalizedString(i) or str(i) for i in EDITABLE_OPTIONS[key]]
        try:
            current = int(addon.getSetting(key) or 0)
        except ValueError:
            current = 0
        heading = addon.getLocalizedString(OPTION_HEADINGS[key]) or key
        index = _dialog().select(heading, [_mark(t, i == current) for i, t in enumerate(labels)],
                                 preselect=current)
        if index >= 0:
            addon.setSetting(key, str(index))


def remote() -> None:
    last = 0
    while True:
        index = _dialog().select(lang.get(lang.BUTTONS), list(REMOTE_BUTTONS), preselect=last)
        if index < 0:
            return
        last = index
        if _call("button", [REMOTE_BUTTONS[index]]) is None:
            return


def send_toast() -> None:
    message = _dialog().input(lang.get(lang.TOAST_PROMPT))
    if message:
        _call("toast", [message])


def status() -> None:
    reply = _call("status")
    if reply:
        show_status(reply["result"])


def show_status(info: dict[str, Any]) -> None:
    def yes_no(value: Any) -> str:
        return "yes" if value else "no"

    lines = [
        f"Host: {info.get('host', '')}"
        + (f" (configured {info['configured_host']})"
           if info.get("configured_host") and info.get("configured_host") != info.get("host")
           else ""),
        f"Connected: {yes_no(info.get('connected'))}",
        f"Paired: {yes_no(info.get('paired'))}"
        + (" (blocked: use Re-pair)" if info.get("pairing_blocked") else ""),
        f"Model: {info.get('model') or '-'}",
        f"Firmware: {info.get('firmware') or '-'}",
        f"Power: {info.get('power') or '-'}",
        f"Volume: {info.get('volume') if info.get('volume') is not None else '-'}"
        + (" (muted)" if info.get("muted") else ""),
        f"App: {info.get('app') or '-'}",
        f"Input: {info.get('input') or '-'}",
        f"Sound output: {info.get('sound_output') or '-'}",
        f"Picture preset: {info.get('picture_preset') or '-'}",
        f"Kodi's TV input: {info.get('kodi_input') or 'not set'}"
        + {True: " (on screen)", False: " (not on screen)"}.get(info.get("kodi_on_screen"), ""),
        "Transparent control: "
        + ("active" if info.get("transparent_active")
           else "on, waiting" if info.get("transparent_control") else "off"),
    ]
    _dialog().textviewer(lang.get(lang.STATUS), "\n".join(lines))


def repair() -> None:
    if _call("repair"):
        _dialog().notification(ADDON_NAME, lang.get(lang.REPAIR_STARTED))


def find_tv() -> None:
    """Search the LAN, let the user pick a TV, and save it as the host."""
    from . import discovery  # noqa: PLC0415

    _dialog().notification(ADDON_NAME, lang.get(lang.SEARCHING), xbmcgui.NOTIFICATION_INFO, 3000)
    xbmc.executebuiltin("ActivateWindow(busydialognocancel)")
    try:
        found = asyncio.run(discovery.discover())
    finally:
        xbmc.executebuiltin("Dialog.Close(busydialognocancel)")
    if not found:
        _dialog().ok(lang.get(lang.FIND_TV), lang.get(lang.NO_TVS_FOUND))
        return
    discovery.remember(found)
    addon = xbmcaddon.Addon("service.webostv")
    current = addon.getSetting("host")
    labels = [_mark(tv.label, tv.host == current) for tv in found]
    index = _dialog().select(lang.get(lang.FIND_TV), labels)
    if index < 0:
        return
    tv = found[index]
    if tv.host != current:
        # The service reconnects on the settings change; a TV paired before
        # is recognised by UUID and doesn't prompt again.
        addon.setSetting("host", tv.host)
    _dialog().notification(ADDON_NAME, f"{lang.get(lang.TV_SELECTED)}: {tv.name}")
