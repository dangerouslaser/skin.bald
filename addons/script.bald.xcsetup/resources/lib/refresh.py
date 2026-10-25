from __future__ import annotations

import glob
import http.client
import json
import os
import tempfile
import urllib.request
import xml.etree.ElementTree as ET

import xbmc
import xbmcvfs

from resources.lib.config import ConfigError, build_api_url, build_m3u, build_urls


ADDON_ID = "script.bald.xcsetup"
IPTV_ID = "pvr.iptvsimple"
# IPTV Simple's m3uRefreshMode values (instance-settings.xml).
REFRESH_ONCE_PER_DAY = "2"
DEFAULT_REFRESH_HOUR = 4


def instance_files() -> list[str]:
    data_dir = xbmcvfs.translatePath(f"special://profile/addon_data/{IPTV_ID}")
    return sorted(glob.glob(os.path.join(data_dir, "instance-settings-*.xml")))


def playlist_path() -> str:
    data_dir = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON_ID}")
    return os.path.join(data_dir, "live.m3u")


def _setting(root: ET.Element, setting_id: str) -> str:
    node = root.find(f"setting[@id='{setting_id}']")
    return (node.text or "") if node is not None else ""


def set_setting(root: ET.Element, setting_id: str, value: str) -> None:
    node = root.find(f"setting[@id='{setting_id}']")
    if node is None:
        node = ET.SubElement(root, "setting", {"id": setting_id})
    node.attrib.pop("default", None)
    node.text = value


def write_instance(tree: ET.ElementTree, path: str) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".bald-xc-", suffix=".xml", dir=os.path.dirname(path))
    os.close(descriptor)
    try:
        tree.write(temporary, encoding="UTF-8", xml_declaration=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def managed_instances() -> list[str]:
    """IPTV Simple instances that read the playlist this add-on writes."""
    target = playlist_path()
    found = []
    for path in instance_files():
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError):
            continue
        if _setting(root, "m3uPathType") == "0" and _setting(root, "m3uPath") == target:
            found.append(path)
    return found


def ensure_daily_refresh(path: str) -> bool:
    """Turn on IPTV Simple's once-a-day reload of the playlist and XMLTV. True when the file changed."""
    tree = ET.parse(path)
    root = tree.getroot()
    if _setting(root, "m3uRefreshMode") == REFRESH_ONCE_PER_DAY:
        return False
    set_setting(root, "m3uRefreshMode", REFRESH_ONCE_PER_DAY)
    write_instance(tree, path)
    return True


def refresh_hour(path: str) -> int:
    try:
        hour = int(_setting(ET.parse(path).getroot(), "m3uRefreshHour"))
    except (ET.ParseError, OSError, ValueError):
        return DEFAULT_REFRESH_HOUR
    return hour if 0 <= hour <= 23 else DEFAULT_REFRESH_HOUR


def xc_data(server: str, username: str, password: str, action: str) -> list[dict]:
    request = urllib.request.Request(
        build_api_url(server, username, password, action),
        headers={"User-Agent": "Kodi/22 Bald XC Setup"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (OSError, ValueError, http.client.HTTPException) as exc:  # HTTPException: a cut-off answer
        raise ConfigError(f"Could not read XC {action.replace('_', ' ')}: {exc}") from exc
    if not isinstance(payload, list):
        raise ConfigError(f"The XC {action.replace('_', ' ')} response was not a list.")
    return payload


def build_playlist(server: str, username: str, password: str, output: str) -> tuple[str, int]:
    categories = xc_data(server, username, password, "get_live_categories")
    streams = xc_data(server, username, password, "get_live_streams")
    return build_m3u(server, username, password, output, categories, streams), len(streams)


def write_playlist(content: str) -> bool:
    """Write live.m3u. True when its contents changed."""
    target = playlist_path()
    try:
        with open(target, encoding="UTF-8", newline="") as handle:
            if handle.read() == content:
                return False
    except OSError:
        pass
    data_dir = os.path.dirname(target)
    os.makedirs(data_dir, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".bald-xc-", suffix=".m3u", dir=data_dir)
    try:
        with os.fdopen(descriptor, "w", encoding="UTF-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def stored_credentials(addon) -> tuple[str, str, str, str]:
    server = addon.getSettingString("server")
    username = addon.getSettingString("username")
    password = addon.getSettingString("password")
    output = addon.getSettingString("output") or "ts"
    build_urls(server, username, password, output)
    return server, username, password, output


def rebuild(addon) -> tuple[bool, int]:
    """Regenerate live.m3u from the stored XC account. Returns (changed, stream count)."""
    content, count = build_playlist(*stored_credentials(addon))
    return write_playlist(content), count


def restart_iptv_simple() -> None:
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
