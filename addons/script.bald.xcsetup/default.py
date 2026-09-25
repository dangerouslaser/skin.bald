from __future__ import annotations

import glob
import json
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
import urllib.request

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib.config import ConfigError, build_api_url, build_m3u, build_urls, redact_url


ADDON = xbmcaddon.Addon()
IPTV_ID = "pvr.iptvsimple"


def _log(message: str) -> None:
    xbmc.log(f"{ADDON.getAddonInfo('id')}: {message}", xbmc.LOGINFO)


def _instance_files() -> list[str]:
    data_dir = xbmcvfs.translatePath(f"special://profile/addon_data/{IPTV_ID}")
    return sorted(glob.glob(os.path.join(data_dir, "instance-settings-*.xml")))


def _choose_instance(paths: list[str]) -> str:
    if not paths:
        raise ConfigError("IPTV Simple has no configured instance yet. Open IPTV Simple once, create an instance, then run this setup again.")
    if len(paths) == 1:
        return paths[0]
    labels = []
    for path in paths:
        label = os.path.basename(path)
        try:
            root = ET.parse(path).getroot()
            name = root.find("setting[@id='kodi_addon_instance_name']")
            if name is not None and name.text:
                label = f"{name.text} ({label})"
        except (ET.ParseError, OSError):
            pass
        labels.append(label)
    selected = xbmcgui.Dialog().select("Choose IPTV Simple instance", labels)
    if selected < 0:
        raise ConfigError("Setup cancelled.")
    return paths[selected]


def _set(root: ET.Element, setting_id: str, value: str) -> None:
    node = root.find(f"setting[@id='{setting_id}']")
    if node is None:
        node = ET.SubElement(root, "setting", {"id": setting_id})
    node.attrib.pop("default", None)
    node.text = value


def _apply(path: str, playlist_path: str, epg_url: str) -> str:
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != "settings":
        raise ConfigError("The selected IPTV Simple instance file is not valid.")

    backup = f"{path}.bald-xc-backup"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)

    _set(root, "m3uPathType", "0")
    _set(root, "m3uPath", playlist_path)
    _set(root, "m3uUrl", "")
    _set(root, "m3uCache", "false")
    _set(root, "epgPathType", "1")
    _set(root, "epgUrl", epg_url)
    _set(root, "epgCache", "true")
    directory = os.path.dirname(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".bald-xc-", suffix=".xml", dir=directory)
    os.close(descriptor)
    try:
        tree.write(temporary, encoding="UTF-8", xml_declaration=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return backup


def _xc_data(server: str, username: str, password: str, action: str) -> list[dict]:
    request = urllib.request.Request(
        build_api_url(server, username, password, action),
        headers={"User-Agent": "Kodi/22 Bald XC Setup"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"Could not read XC {action.replace('_', ' ')}: {exc}") from exc
    if not isinstance(payload, list):
        raise ConfigError(f"The XC {action.replace('_', ' ')} response was not a list.")
    return payload


def _write_playlist(content: str) -> str:
    data_dir = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON.getAddonInfo('id')}")
    os.makedirs(data_dir, exist_ok=True)
    target = os.path.join(data_dir, "live.m3u")
    descriptor, temporary = tempfile.mkstemp(prefix=".bald-xc-", suffix=".m3u", dir=data_dir)
    try:
        with os.fdopen(descriptor, "w", encoding="UTF-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def _restart_iptv_simple() -> None:
    for enabled in (False, True):
        request = json.dumps({
            "jsonrpc": "2.0",
            "method": "Addons.SetAddonEnabled",
            "params": {"addonid": IPTV_ID, "enabled": enabled},
            "id": 1,
        })
        response = json.loads(xbmc.executeJSONRPC(request))
        if "error" in response:
            raise ConfigError(f"Kodi could not {'enable' if enabled else 'disable'} IPTV Simple.")
        xbmc.sleep(1000)


def _prompt(label: str, current: str = "", hidden: bool = False) -> str | None:
    option = xbmcgui.ALPHANUM_HIDE_INPUT if hidden else 0
    value = xbmcgui.Dialog().input(
        label,
        defaultt=current,
        type=xbmcgui.INPUT_ALPHANUM,
        option=option,
    )
    return value if value else None


def _credentials() -> tuple[str, str, str, str] | None:
    server = _prompt("Xtream Codes server URL", ADDON.getSettingString("server"))
    if server is None:
        return None
    username = _prompt("Xtream Codes username", ADDON.getSettingString("username"))
    if username is None:
        return None
    password = _prompt("Xtream Codes password", ADDON.getSettingString("password"), hidden=True)
    if password is None:
        return None

    current_output = ADDON.getSettingString("output") or "ts"
    outputs = (("MPEG-TS (recommended)", "ts"), ("HLS (M3U8)", "m3u8"))
    selected = xbmcgui.Dialog().select(
        "Stream output",
        [label for label, _value in outputs],
        preselect=1 if current_output == "m3u8" else 0,
    )
    if selected < 0:
        return None
    output = outputs[selected][1]

    # Validate the complete entry before saving any part of it.
    build_urls(server, username, password, output)
    ADDON.setSettingString("server", server.strip().rstrip("/"))
    ADDON.setSettingString("username", username.strip())
    ADDON.setSettingString("password", password.strip())
    ADDON.setSettingString("output", output)
    return server, username, password, output


def main() -> None:
    try:
        if "refresh" in sys.argv[1:]:
            server = ADDON.getSettingString("server")
            username = ADDON.getSettingString("username")
            password = ADDON.getSettingString("password")
            output = ADDON.getSettingString("output") or "ts"
            build_urls(server, username, password, output)
        else:
            entered = _credentials()
            if entered is None:
                return
            server, username, password, output = entered
        _unused_playlist_url, epg_url = build_urls(server, username, password, output)
        categories = _xc_data(server, username, password, "get_live_categories")
        streams = _xc_data(server, username, password, "get_live_streams")
        playlist = build_m3u(server, username, password, output, categories, streams)
        target = _choose_instance(_instance_files())
        if not xbmcgui.Dialog().yesno(
            "Bald XC Setup",
            f"Apply {len(streams)} XC live streams to IPTV Simple?\n\n"
            "The current instance settings will be backed up first.",
        ):
            return
        playlist_path = _write_playlist(playlist)
        backup = _apply(target, playlist_path, epg_url)
        _log(f"Configured {os.path.basename(target)} with {len(streams)} XC live streams; epg={redact_url(epg_url)}")
        _restart_iptv_simple()
        xbmcgui.Dialog().ok(
            "Bald XC Setup",
            "IPTV Simple has been configured and restarted.\n\n"
            f"Backup: {os.path.basename(backup)}",
        )
    except (ConfigError, ET.ParseError, OSError) as exc:
        xbmcgui.Dialog().ok("Bald XC Setup", str(exc))


if __name__ == "__main__":
    main()
