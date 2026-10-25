from __future__ import annotations

import os
import shutil
import sys
import xml.etree.ElementTree as ET

import xbmc
import xbmcaddon
import xbmcgui

from resources.lib.config import ConfigError, build_urls, redact_url
from resources.lib.refresh import (
    REFRESH_ONCE_PER_DAY,
    build_playlist,
    ensure_daily_refresh,
    instance_files as _instance_files,
    managed_instances,
    playlist_path,
    rebuild,
    restart_iptv_simple as _restart_iptv_simple,
    set_setting as _set,
    write_instance,
    write_playlist,
)


ADDON = xbmcaddon.Addon()


def _log(message: str) -> None:
    xbmc.log(f"{ADDON.getAddonInfo('id')}: {message}", xbmc.LOGINFO)


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


def _apply(path: str, m3u_path: str, epg_url: str) -> str:
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != "settings":
        raise ConfigError("The selected IPTV Simple instance file is not valid.")

    backup = f"{path}.bald-xc-backup"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)

    # A configured but disabled multi-instance client never registers with Kodi's
    # PVR manager. Applying XC credentials is an explicit request to use this
    # instance, so enable it along with its playlist and EPG settings.
    _set(root, "kodi_addon_instance_enabled", "true")
    _set(root, "m3uPathType", "0")
    _set(root, "m3uPath", m3u_path)
    _set(root, "m3uUrl", "")
    _set(root, "m3uCache", "false")
    _set(root, "epgPathType", "1")
    _set(root, "epgUrl", epg_url)
    _set(root, "epgCache", "true")
    # The playlist is a local file this add-on's service rebuilds from the XC API every day.
    # IPTV Simple's once-a-day refresh rereads it and the XMLTV, so channels and guide stay current.
    _set(root, "m3uRefreshMode", REFRESH_ONCE_PER_DAY)
    write_instance(tree, path)
    return backup


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


def _refresh_now() -> None:
    """Rebuild the playlist from the stored XC account and reload IPTV Simple, without the guided flow."""
    instances = managed_instances()
    if not instances:
        raise ConfigError("No IPTV Simple instance uses the Bald XC playlist yet. Run the guided setup first.")
    changed, count = rebuild(ADDON)
    for path in instances:
        if ensure_daily_refresh(path):
            _log(f"Turned on daily refresh for {os.path.basename(path)}")
    _log(f"Refreshed {count} XC live streams (playlist {'changed' if changed else 'unchanged'})")
    _restart_iptv_simple()
    xbmcgui.Dialog().notification("Bald XC Setup", f"Reloaded {count} channels and the guide", ADDON.getAddonInfo("icon"))


def main() -> None:
    try:
        if "refresh" in sys.argv[1:]:
            _refresh_now()
            return
        entered = _credentials()
        if entered is None:
            return
        server, username, password, output = entered
        _unused_playlist_url, epg_url = build_urls(server, username, password, output)
        playlist, count = build_playlist(server, username, password, output)
        target = _choose_instance(_instance_files())
        if not xbmcgui.Dialog().yesno(
            "Bald XC Setup",
            f"Apply {count} XC live streams to IPTV Simple?\n\n"
            "The current instance settings will be backed up first.",
        ):
            return
        write_playlist(playlist)
        backup = _apply(target, playlist_path(), epg_url)
        _log(f"Configured {os.path.basename(target)} with {count} XC live streams; epg={redact_url(epg_url)}")
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
