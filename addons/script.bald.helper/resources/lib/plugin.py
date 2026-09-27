"""Bald Helper's plugin entry (plugin://script.bald.helper/): the OSD cast panel's list, and the settings actions.

    ?info=cast&dbtype=movie|episode|tvshow&dbid=N   the library item's cast: name, role, photo, in billing order.
                                                     An episode lists its own cast, then the show's not already
                                                     listed.
    ?info=crew&dbtype=movie|episode&dbid=N          the library's director and writer names as text items (the
                                                     library keeps no crew photos).
    ?action=test_key                                 checks the MDbList key with GET /user and shows the result.
    ?action=clear_cache                              forgets every cached rating.

Everything comes from VideoLibrary.Get*Details over JSON-RPC: local, no key, no network (the two actions aside).
Nothing here imports xbmc at module level, so the tests drive it with stand-ins.
"""

from __future__ import annotations

import json
import os
from urllib.parse import parse_qsl

try:
    from . import mdblist
except ImportError:  # loaded by file path (the tests)
    import importlib.util as _util

    _spec = _util.spec_from_file_location("bald_helper_mdblist", os.path.join(os.path.dirname(__file__), "mdblist.py"))
    mdblist = _util.module_from_spec(_spec)
    _spec.loader.exec_module(mdblist)

ADDON_ID = "script.bald.helper"
DATA_DIR = "special://profile/addon_data/script.bald.helper"
DATABASE = "ratings.db"
KEY_SETTING = "mdblist_key"
ACTOR_ICON = "DefaultActor.png"
DIRECTOR, WRITER = 20339, 20417  # Kodi's own "Director" and "Writer"

DETAILS = {
    "movie": ("VideoLibrary.GetMovieDetails", "movieid", "moviedetails"),
    "tvshow": ("VideoLibrary.GetTVShowDetails", "tvshowid", "tvshowdetails"),
    "episode": ("VideoLibrary.GetEpisodeDetails", "episodeid", "episodedetails"),
}

# The helper's own strings (resources/language/resource.language.en_gb/strings.po).
S_HEADING = 32100
S_OK = 32110
S_OK_QUOTA = 32111
S_REJECTED = 32112
S_EMPTY = 32113
S_UNREACHABLE = 32114
S_ERROR = 32115
S_CLEARED = 32116


def parse(argument: str) -> dict:
    return dict(parse_qsl(argument.lstrip("?")))


def jsonrpc(xbmc, method: str, params: dict) -> dict:
    try:
        answer = json.loads(xbmc.executeJSONRPC(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                                                            "params": params})))
    except (TypeError, ValueError):
        return {}
    return (answer.get("result") or {}) if isinstance(answer, dict) else {}


def details(xbmc, dbtype: str, dbid: int, properties: list[str]) -> dict:
    method, id_name, result = DETAILS[dbtype]
    return jsonrpc(xbmc, method, {id_name: dbid, "properties": properties}).get(result) or {}


def _ordered(cast) -> list[dict]:
    people = [c for c in (cast or []) if isinstance(c, dict) and str(c.get("name") or "").strip()]
    return sorted(people, key=lambda c: (c.get("order") if isinstance(c.get("order"), int) else 1 << 30))


def cast(xbmc, dbtype: str, dbid: int) -> list[dict]:
    """[{name, role, thumbnail, order}] for a library movie, TV show or episode; [] when unknown."""
    if dbtype not in DETAILS:
        return []
    item = details(xbmc, dbtype, dbid, ["cast", "tvshowid"] if dbtype == "episode" else ["cast"])
    people = _ordered(item.get("cast"))
    if dbtype == "episode" and isinstance(item.get("tvshowid"), int) and item["tvshowid"] > 0:
        names = {p["name"] for p in people}
        show = _ordered(details(xbmc, "tvshow", item["tvshowid"], ["cast"]).get("cast"))
        people += [p for p in show if p["name"] not in names]
    return [{"name": str(p["name"]), "role": str(p.get("role") or ""), "thumbnail": str(p.get("thumbnail") or ""),
             "order": index} for index, p in enumerate(people)]


def crew(xbmc, dbtype: str, dbid: int) -> list[dict]:
    """Directors, then writers, as [{name, role_id}] (a person in both is listed once, as director)."""
    if dbtype not in ("movie", "episode"):
        return []
    item = details(xbmc, dbtype, dbid, ["director", "writer"])
    found, seen = [], set()
    for field, role in (("director", DIRECTOR), ("writer", WRITER)):
        for name in item.get(field) or []:
            name = str(name).strip()
            if name and name not in seen:
                seen.add(name)
                found.append({"name": name, "role_id": role})
    return found


def list_people(xbmc, xbmcgui, xbmcplugin, handle: int, base: str, query: dict) -> bool:
    dbtype = query.get("dbtype", "")
    dbid = query.get("dbid", "")
    if not dbid.isdigit() or dbtype not in DETAILS:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return False
    items = []
    if query.get("info") == "crew":
        for person in crew(xbmc, dbtype, int(dbid)):
            item = xbmcgui.ListItem(person["name"], xbmc.getLocalizedString(person["role_id"]), offscreen=True)
            item.setArt({"icon": ACTOR_ICON})
            items.append((f"{base}?info=none", item, False))
    else:
        for person in cast(xbmc, dbtype, int(dbid)):
            item = xbmcgui.ListItem(person["name"], person["role"], offscreen=True)
            item.setArt({"thumb": person["thumbnail"], "icon": ACTOR_ICON} if person["thumbnail"]
                        else {"icon": ACTOR_ICON})
            item.setProperty("order", str(person["order"]))
            items.append((f"{base}?info=none", item, False))
    xbmcplugin.addDirectoryItems(handle, items, len(items))
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    return True


def test_key(xbmcaddon, xbmcgui, fetch=None) -> str:
    """Check the saved key and show a notification; returns the result code (the key is never shown or logged)."""
    addon = xbmcaddon.Addon(ADDON_ID)
    text = addon.getLocalizedString
    result, data = mdblist.check_key(addon.getSettingString(KEY_SETTING), **({"fetch": fetch} if fetch else {}))
    if result == "ok":
        if data.get("limit") and data.get("remaining") is not None:
            message = text(S_OK_QUOTA).format(user=data["username"] or "MDbList", remaining=data["remaining"],
                                              limit=data["limit"])
        else:
            message = text(S_OK).format(user=data["username"] or "MDbList")
    else:
        message = text({"rejected": S_REJECTED, "empty": S_EMPTY, "unreachable": S_UNREACHABLE}.get(result, S_ERROR))
        if result == "error":
            message = message.format(status=data.get("status", "?"))
    icon = getattr(xbmcgui, "NOTIFICATION_INFO" if result == "ok" else "NOTIFICATION_WARNING", "")
    xbmcgui.Dialog().notification(text(S_HEADING), message, icon, 6000)
    return result


def clear_cache(xbmcaddon, xbmcgui, xbmcvfs) -> int:
    addon = xbmcaddon.Addon(ADDON_ID)
    path = os.path.join(xbmcvfs.translatePath(DATA_DIR), DATABASE)
    removed = 0
    if os.path.exists(path):
        cache = mdblist.Cache(path)
        try:
            removed = cache.clear()
        finally:
            cache.close()
    xbmcgui.Dialog().notification(addon.getLocalizedString(S_HEADING),
                                  addon.getLocalizedString(S_CLEARED).format(count=removed),
                                  getattr(xbmcgui, "NOTIFICATION_INFO", ""), 4000)
    return removed


def run(argv, xbmc, xbmcgui, xbmcplugin, xbmcaddon, xbmcvfs) -> None:
    base = argv[0].split("?", 1)[0]
    handle = int(argv[1]) if len(argv) > 1 and argv[1].lstrip("-").isdigit() else -1
    query = parse(argv[2] if len(argv) > 2 else "")
    action = query.get("action")
    if action == "test_key":
        test_key(xbmcaddon, xbmcgui)
    elif action == "clear_cache":
        clear_cache(xbmcaddon, xbmcgui, xbmcvfs)
    elif query.get("info") in ("cast", "crew") and handle >= 0:
        list_people(xbmc, xbmcgui, xbmcplugin, handle, base, query)
    elif handle >= 0:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
