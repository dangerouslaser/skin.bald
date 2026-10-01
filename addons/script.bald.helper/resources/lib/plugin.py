"""Bald Helper's plugin entry (plugin://script.bald.helper/): the OSD cast panel's list, and the settings actions.

    ?info=cast&dbtype=movie|episode|tvshow&dbid=N   the library item's cast: name, role, photo, in billing order.
                                                     An episode lists its own cast, then the show's not already
                                                     listed.
    ?info=crew&dbtype=movie|episode&dbid=N          the library's director and writer names as text items (the
                                                     library keeps no crew photos).
    ?info=livetv_channels&query=Q                   Live TV channels matching Q, for Bald's Search (livetv.py).
    ?info=livetv_programmes&query=Q                 programmes on now or later matching Q, for Bald's Search.
    ?info=library_tags[&all=1]                      the libraries (Plex and Jellyfin libraries are tags), then
                                                     every tag, as folders, for the content picker's "Libraries
                                                     and tags" (libraries.py).
    ?info=library_tag&tag=T                         rows for one tag (Plex and Jellyfin libraries are tags).
    ?action=play_channel&channelid=N                 switches to channel N.
    ?action=warm_livetv                              refreshes the programme search's cache (Home's Search runs it).
    ?action=search[&start=movies|tvshows|episodes]   asks for a query (Kodi's keyboard, headed "Search") and shows
                                                     it in Bald's Search (window 1130), opening it, or refreshing it
                                                     for a new search; start names the category to begin on.
    ?action=live_search                              from Global Search's "No results found" dialog: closes it
                                                     (Global Search closes too) and opens Bald's Live TV search.
    ?action=programme&channelid=N&broadcastid=B&now=1  what Select does on a programme: its channel when it is on
                                                     now, else a choice of recording it or switching to the channel.
    ?action=test_key                                 checks the MDbList key with GET /user and shows the result.
    ?action=clear_cache                              forgets every cached rating.

Everything comes from VideoLibrary.Get*Details over JSON-RPC: local, no key, no network (the two actions aside).
Nothing here imports xbmc at module level, so the tests drive it with stand-ins.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import parse_qsl

from . import common, libraries, livetv, mdblist
from .common import ADDON_ID, DATA_DIR, DATABASE, KEY_SETTING
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
S_COPIED = 32117
S_NOTHING_TO_COPY = 32118
TMDBHELPER_ID = "plugin.video.themoviedb.helper"
TMDBHELPER_KEY = "mdblist_apikey"
TMDBHELPER_SETTINGS = "special://profile/addon_data/plugin.video.themoviedb.helper/settings.xml"


def parse(argument: str) -> dict:
    return dict(parse_qsl(argument.lstrip("?")))


def details(xbmc, dbtype: str, dbid: int, properties: list[str]) -> dict:
    method, id_name, result = DETAILS[dbtype]
    return common.jsonrpc(xbmc, method, {id_name: dbid, "properties": properties}).get(result) or {}


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


RECORD, SWITCH = 264, 19000  # Kodi's "Record" and "Switch to channel"


def list_livetv(xbmc, xbmcgui, xbmcplugin, xbmcvfs, handle: int, base: str, query: dict, clock=None) -> int:
    """The Live TV channels or programmes matching query["query"] (livetv.py); returns how many were listed. The
    query and the count go on Home too (Bald.SearchLive.Query, .Channels, .Programmes)."""
    text = query.get("query", "")
    items = []
    if query.get("info") == "livetv_channels":
        for channel in livetv.match_channels(livetv.channels(xbmc), text):
            item = xbmcgui.ListItem(channel["name"], channel["now"], offscreen=True)
            item.setArt({"thumb": channel["logo"], "icon": channel["logo"] or "DefaultTVShows.png"})
            for key in ("number", "kind"):
                item.setProperty(key, channel[key])
            item.setProperty("channelid", str(channel["id"]))
            items.append((f"{base}?info=none", item, False))
    else:
        cache = xbmcvfs.translatePath(common.DATA_DIR) if xbmcvfs is not None else None
        found, programmes = livetv.guide(xbmc, cache)
        by_id = {c["id"]: c for c in found}
        now = datetime.now(timezone.utc) if clock is None else clock()
        time_format = xbmc.getRegion("time")
        now_label = xbmc.getLocalizedString(livetv.NOW_LABEL)
        day = lambda weekday: xbmc.getLocalizedString(livetv.SHORT_DAYS + weekday)  # noqa: E731
        for programme in livetv.match_programmes(programmes, text, now):
            channel = by_id.get(programme["channel"], {})
            item = xbmcgui.ListItem(programme["title"], channel.get("name", ""), offscreen=True)
            item.setArt({"thumb": channel.get("logo", ""), "icon": channel.get("logo") or "DefaultTVShows.png"})
            on_now = programme["start_time"] <= now < programme["end_time"]
            item.setProperty("when", livetv.when(programme["start_time"], programme["end_time"], now, time_format,
                                                 now_label, day))
            item.setProperty("now", "true" if on_now else "")
            item.setProperty("plot", programme.get("plot", ""))
            item.setProperty("number", channel.get("number", ""))
            item.setProperty("channelid", str(programme["channel"]))
            item.setProperty("broadcastid", str(programme["broadcast"] or ""))
            items.append((f"{base}?info=none", item, False))
    # For Global Search's "No results found" dialog, which cannot read Search's lists (DialogConfirm.xml). Not for an
    # empty query: Search's lists list again with none as Global Search closes, which would blank the last search's.
    if text.strip():
        home = xbmcgui.Window(common.HOME_WINDOW)
        home.setProperty("Bald.SearchLive.Query", text)
        home.setProperty("Bald.SearchLive.Channels" if query.get("info") == "livetv_channels" else
                         "Bald.SearchLive.Programmes", str(len(items)))
    xbmcplugin.addDirectoryItems(handle, items, len(items))
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    return len(items)


def play_channel(xbmc, channelid: str) -> bool:
    if not channelid.isdigit():
        return False
    common.jsonrpc(xbmc, "Player.Open", {"item": {"channelid": int(channelid)}})
    return True


SEARCH_OPEN = "Window.IsVisible(script-globalsearch.xml)"
LIVE_SEARCH_WINDOW = 1130  # Custom_1130_BaldLiveSearch.xml


def live_search(xbmc, steps: int = 50) -> bool:
    """Global Search asks "Search again?" when the libraries have nothing, and closes on anything but Yes, so its
    Live TV matches cannot be shown in its window. Close the question, wait for Global Search to go, and open Bald's
    Live TV search on the same query (Window(home).Property(Bald.SearchLive.Query))."""
    # The window's own copy of the query, which later searches' listings leave alone.
    query = xbmc.getInfoLabel("Window(home).Property(Bald.SearchLive.Query)")
    xbmc.executebuiltin(f"SetProperty(Bald.LiveSearch.Query,{query},home)")
    xbmc.executebuiltin("Dialog.Close(yesnodialog)")
    monitor = xbmc.Monitor()
    for _ in range(steps):
        if not xbmc.getCondVisibility(SEARCH_OPEN):
            break
        if monitor.waitForAbort(0.1):
            return False
    xbmc.executebuiltin(f"ActivateWindow({LIVE_SEARCH_WINDOW})")
    # With no channel matches, start on the programmes (the window's default is the channels).
    home = xbmc.getInfoLabel("Window(home).Property(Bald.SearchLive.Channels)")
    if home in ("", "0"):
        for _ in range(steps):
            if xbmc.getCondVisibility(f"Window.IsActive({LIVE_SEARCH_WINDOW}) + Integer.IsGreater(Container(62).NumItems,0)"):
                xbmc.executebuiltin("SetFocus(62)")
                break
            if monitor.waitForAbort(0.1):
                return False
    return True


SEARCH_WINDOW = 1130  # Custom_1130_BaldSearch.xml
SEARCH_QUERY = "Bald.SearchQuery"
SEARCH_HEADING = 137  # Kodi's "Search"


def search(xbmc, xbmcgui, query: dict) -> bool:
    """Ask for a query and show it in Bald's Search. The keyboard opens from here rather than from the window's onload:
    a keyboard opened while a window is still opening never finishes closing in Kodi 22. Double quotes are dropped:
    the query sits inside the smart-playlist rule of each library list (Includes_Bald_Search.xml)."""
    text = xbmcgui.Dialog().input(xbmc.getLocalizedString(SEARCH_HEADING)).replace('"', "").strip()
    if not text:
        return False
    xbmc.executebuiltin(f'Skin.SetString({SEARCH_QUERY},"{text}")')
    start = query.get("start", "")
    if xbmc.getCondVisibility(f"Window.IsActive({SEARCH_WINDOW})"):
        # A new search: start over on the first category with results.
        xbmc.executebuiltin(f"ClearProperty(Bald.SearchCat,{SEARCH_WINDOW})")
        xbmc.executebuiltin("SetFocus(9198)")
    else:
        if start in ("movies", "tvshows", "episodes"):
            xbmc.executebuiltin(f"SetProperty(Bald.SearchStart,{start},home)")
        xbmc.executebuiltin(f"ActivateWindow({SEARCH_WINDOW})")
    return True


def programme(xbmc, xbmcgui, query: dict) -> str:
    """Select on a programme: on now, its channel; later, record it or switch to its channel. Returns what it did."""
    channelid, broadcastid = query.get("channelid", ""), query.get("broadcastid", "")
    if query.get("now") == "true" or not broadcastid.isdigit():
        return "play" if play_channel(xbmc, channelid) else "none"
    choice = xbmcgui.Dialog().contextmenu([xbmc.getLocalizedString(RECORD), xbmc.getLocalizedString(SWITCH)])
    if choice == 0:
        common.jsonrpc(xbmc, "PVR.AddTimer", {"broadcastid": int(broadcastid)})
        return "record"
    if choice == 1:
        return "play" if play_channel(xbmc, channelid) else "none"
    return "none"


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


def tmdbhelper_key(xbmcaddon, xbmcvfs) -> str:
    """TMDb Helper's MDbList key: from its saved settings file (readable while it is disabled, when Kodi will not
    open the add-on), else through the add-on API; '' when there is none."""
    if xbmcvfs is not None:
        try:
            import xml.etree.ElementTree as ET  # noqa: PLC0415

            root = ET.parse(xbmcvfs.translatePath(TMDBHELPER_SETTINGS)).getroot()
            for setting in root.iter("setting"):
                value = (setting.text or setting.get("value") or "").strip()  # settings version 2, or 1
                if setting.get("id") == TMDBHELPER_KEY and value:
                    return value
        except Exception:  # noqa: BLE001 - no file yet, or not readable
            pass
    try:
        return xbmcaddon.Addon(TMDBHELPER_ID).getSettingString(TMDBHELPER_KEY).strip()
    except Exception:  # noqa: BLE001 - not installed, disabled or no such setting
        return ""


def copy_tmdbhelper_key(xbmcaddon, xbmcgui, xbmcvfs=None) -> bool:
    """Copy TMDb Helper's MDbList key into this add-on's setting (never shown or logged), then check it."""
    addon = xbmcaddon.Addon(ADDON_ID)
    text = addon.getLocalizedString
    key = tmdbhelper_key(xbmcaddon, xbmcvfs)
    if not key:
        xbmcgui.Dialog().notification(text(S_HEADING), text(S_NOTHING_TO_COPY),
                                      getattr(xbmcgui, "NOTIFICATION_WARNING", ""), 5000)
        return False
    addon.setSettingString(KEY_SETTING, key)
    xbmcgui.Dialog().notification(text(S_HEADING), text(S_COPIED), getattr(xbmcgui, "NOTIFICATION_INFO", ""), 3000)
    test_key(xbmcaddon, xbmcgui)
    return True


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
    elif action == "copy_tmdbhelper_key":
        copy_tmdbhelper_key(xbmcaddon, xbmcgui, xbmcvfs)
    elif action == "clear_cache":
        clear_cache(xbmcaddon, xbmcgui, xbmcvfs)
    elif action == "warm_livetv":
        livetv.guide(xbmc, xbmcvfs.translatePath(common.DATA_DIR))
    elif action == "live_search":
        live_search(xbmc)
    elif action == "search":
        search(xbmc, xbmcgui, query)
    elif action == "play_channel":
        play_channel(xbmc, query.get("channelid", ""))
    elif action == "programme":
        programme(xbmc, xbmcgui, query)
    elif query.get("info") in ("livetv_channels", "livetv_programmes") and handle >= 0:
        list_livetv(xbmc, xbmcgui, xbmcplugin, xbmcvfs, handle, base, query)
    elif query.get("info") == "library_tags" and handle >= 0:
        libraries.list_tags(xbmc, xbmcgui, xbmcplugin, xbmcvfs, handle, base, query.get("all") == "1",
                            xbmcaddon.Addon(ADDON_ID).getLocalizedString)
    elif query.get("info") == "library_tag" and handle >= 0:
        libraries.list_tag(xbmc, xbmcgui, xbmcplugin, xbmcvfs, handle, query.get("tag", ""),
                           xbmcaddon.Addon(ADDON_ID).getLocalizedString)
    elif query.get("info") in ("cast", "crew") and handle >= 0:
        list_people(xbmc, xbmcgui, xbmcplugin, handle, base, query)
    elif handle >= 0:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
