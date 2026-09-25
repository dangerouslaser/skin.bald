from __future__ import annotations

import glob
import os
import shutil
import xml.etree.ElementTree as ET

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib.config import ConfigError, build_urls, redact_url


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


def _apply(path: str, playlist_url: str, epg_url: str) -> str:
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != "settings":
        raise ConfigError("The selected IPTV Simple instance file is not valid.")

    backup = f"{path}.bald-xc-backup"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)

    _set(root, "m3uPathType", "1")
    _set(root, "m3uUrl", playlist_url)
    _set(root, "m3uCache", "true")
    _set(root, "epgPathType", "1")
    _set(root, "epgUrl", epg_url)
    _set(root, "epgCache", "true")
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    return backup


def _restart_iptv_simple() -> None:
    request = (
        '{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled",'
        f'"params":{{"addonid":"{IPTV_ID}","enabled":false}},"id":1}}'
    )
    xbmc.executeJSONRPC(request)
    xbmc.sleep(500)
    request = (
        '{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled",'
        f'"params":{{"addonid":"{IPTV_ID}","enabled":true}},"id":1}}'
    )
    xbmc.executeJSONRPC(request)


def main() -> None:
    ADDON.openSettings()
    server = ADDON.getSettingString("server")
    username = ADDON.getSettingString("username")
    password = ADDON.getSettingString("password")
    output = ADDON.getSettingString("output") or "ts"

    try:
        playlist_url, epg_url = build_urls(server, username, password, output)
        target = _choose_instance(_instance_files())
        if not xbmcgui.Dialog().yesno(
            "Bald XC Setup",
            "Apply these Xtream Codes details to IPTV Simple?\n\n"
            "The current instance settings will be backed up first.",
        ):
            return
        backup = _apply(target, playlist_url, epg_url)
        _log(f"Configured {os.path.basename(target)}; playlist={redact_url(playlist_url)}")
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
