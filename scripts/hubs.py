"""One-time move of the Movies and TV shows Home screens into the user-managed hubs list (docs/NOTES.md, Home hubs).

RunScript(skin.bald,hubs), from Startup.xml or Home.xml while Skin.String(Bald.HubsMigrated) is empty.

Before 0.3, Home had two fixed optional screens, each with its own Skin Variables row list
(addon_data/script.skinvariables/nodes/skin.bald/skinvariables-shortcut-movieswidgets.json and ...-tvshowswidgets.json)
and a skin bool that put it in the main menu (Bald.Screen.Movies, Bald.Screen.TVShows). Now Home reads one list of up
to eight hubs, skinvariables-shortcut-hubs.json, whose entries carry their own rows in "widgets". This script:

  1. leaves a hubs list that the user has already changed alone (anything but the shipped default, ignoring the
     guids Skin Variables adds when it reads a list), so it never duplicates hubs or overwrites later edits;
  2. on an install that used the old screens (it has an old row list, a screen switched on, or a Home build), writes
     the shipped hubs (1 Movies, 2 TV shows, in that order) with each old row list copied over verbatim (labels, paths,
     styles, logo switches, limits and any other field) and "disabled" set on a hub whose screen was off, so its rows
     survive and one switch shows it again;
  3. on a fresh install writes nothing: Skin Variables copies the shipped hubs (both shown) on first read;
  4. clears the old bools, sets Bald.HubsMigrated, stamps Bald.WidgetsStamp and, when Home is showing, runs the same
     Home build Home runs itself (it skips its own build until the marker is set).

The old row files are left in place as a backup; nothing reads them any more. If anything fails the marker stays unset,
so the next Home load tries again, and Home keeps its shipped fallback rows meanwhile.
"""
import json
import os
from copy import deepcopy

SKIN = "skin.bald"
NODES = "special://profile/addon_data/script.skinvariables/nodes/{}/".format(SKIN)
SEED = "special://skin/shortcuts/skinvariables-shortcut-hubs.json"
HUBS = "skinvariables-shortcut-hubs.json"
# The old screens, in their old menu order, with the row list and the skin bool that showed each one.
OLD_SCREENS = (
    ("movies", "skinvariables-shortcut-movieswidgets.json", "Bald.Screen.Movies"),
    ("tvshows", "skinvariables-shortcut-tvshowswidgets.json", "Bald.Screen.TVShows"),
)
# The shipped hubs that stand for them (tests/test_home_hubs.py checks the seed's order).
SEED_PATHS = {"movies": "videodb://movies/titles/", "tvshows": "videodb://tvshows/titles/"}
MARKER = "Bald.HubsMigrated"
LOCK = "Bald.HubsMigrating"
BUILD_HASH = "script-skinvariables-generator-hash"
# Skin Variables caches each list in a Home window property (script.skinvariables resources/lib/shortcuts/futils.py).
CACHE_PROPERTY = "SkinVariables.ShortcutsNode.{}-{}".format(SKIN, HUBS)


def without_guids(value):
    """A row or hub list as the user sees it: Skin Variables adds a "guid" to every entry when it reads a list."""
    if isinstance(value, list):
        return [without_guids(item) for item in value]
    if isinstance(value, dict):
        return {key: without_guids(item) for key, item in value.items() if key != "guid"}
    return value


def is_default(hubs, seed):
    return without_guids(hubs) == without_guids(seed)


def migrated_hubs(seed, old_rows, enabled):
    """The seed with the old screens' rows and switches: old_rows and enabled are keyed by "movies" and "tvshows";
    a missing row list (None) keeps the seed's rows, which are the old shipped defaults."""
    hubs = deepcopy(seed)
    for key, _, _ in OLD_SCREENS:
        hub = next(h for h in hubs if h.get("path") == SEED_PATHS[key])
        rows = old_rows.get(key)
        if isinstance(rows, list):
            hub["widgets"] = deepcopy(rows)
        if not enabled.get(key):
            hub["disabled"] = "True"
    return hubs


def plan(seed, current, old_rows, enabled, built_before):
    """The hubs list to write, or None to write nothing. current is the user's hubs list, None when there is none."""
    if current is not None and not is_default(current, seed):
        return None
    used_old_screens = built_before or any(rows is not None for rows in old_rows.values()) or any(enabled.values())
    if not used_old_screens:
        return None
    return migrated_hubs(seed, old_rows, enabled)


def read_list(path):
    """A JSON list from path, or None when the file is missing, empty or not a list."""
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, list) else None


def migrate(xbmc, xbmcgui, xbmcvfs):
    home = xbmcgui.Window(10000)
    try:
        nodes = xbmcvfs.translatePath(NODES)
        seed = read_list(xbmcvfs.translatePath(SEED))
        if seed is None:
            raise ValueError("no shipped hubs list")
        old_rows = {key: read_list(os.path.join(nodes, name)) for key, name, _ in OLD_SCREENS}
        enabled = {key: xbmc.getCondVisibility("Skin.HasSetting({})".format(bool_name)) for key, _, bool_name in OLD_SCREENS}
        built_before = bool(xbmc.getInfoLabel("Skin.String({})".format(BUILD_HASH)))
        hubs = plan(seed, read_list(os.path.join(nodes, HUBS)), old_rows, enabled, built_before)
        if hubs is not None:
            xbmcvfs.mkdirs(nodes)
            with open(os.path.join(nodes, HUBS), "w", encoding="utf-8") as handle:
                json.dump(hubs, handle, indent=4)
            home.clearProperty(CACHE_PROPERTY)
        for _, _, bool_name in OLD_SCREENS:
            xbmc.executebuiltin("Skin.Reset({})".format(bool_name), True)
        stamp = "hubs_" + xbmc.getInfoLabel("System.Date(yyyy-mm-dd)") + "_" + xbmc.getInfoLabel("System.Time(hh:mm:ss)")
        xbmc.executebuiltin("Skin.SetString(Bald.WidgetsStamp,{})".format(stamp), True)
        xbmc.executebuiltin("Skin.SetString({},1)".format(MARKER), True)
        xbmc.log("Bald hubs: {}".format("migrated the Movies and TV shows screens" if hubs is not None
                                        else "kept the hubs list as it is"), xbmc.LOGINFO)
        if xbmc.getCondVisibility("Window.IsActive(home)"):
            xbmc.executebuiltin("RunScript(script.skinvariables,action=buildtemplate,lastbuildtime={})".format(stamp))
    finally:
        home.clearProperty(LOCK)
