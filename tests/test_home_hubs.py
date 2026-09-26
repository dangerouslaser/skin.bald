"""User-managed Home hubs (docs/NOTES.md, Home hubs; docs/SPEC.md 5.1 and 5.4): eight fixed slots filled from the
Skin Variables hubs menu, Live TV rows, and the one-time migration of the old Movies and TV shows screens."""

import collections
import importlib.util
import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import home_menu
from conditions import equivalent, implies
from home_screens import HUB_SLOTS, SCREENS, hubs, rows
from kodi_includes import Skin, resolve_window

from scripts import hubs as migration


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
FALLBACK = XML / "Includes_Bald_HomeDefaults.xml"
HUBS = [f"hub{n}" for n in range(1, HUB_SLOTS + 1)]


def load_builder():
    spec = importlib.util.spec_from_file_location("build_home_defaults", ROOT / "tools" / "build_home_defaults.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(menus):
    """The generated includes for these row menus (menu name -> list), as Skin Variables would write them."""
    builder = load_builder()
    builder.menu_items = lambda menu: menus.get(menu, [])
    return builder.fallback_text()


def row(label, **fields):
    return {"label": label, "path": f"videodb://{label}/", "target": "videos", "limit": "5", "secondary": "0", **fields}


def control_ids(root):
    return [int(node.get("id")) for node in root.iter("control") if (node.get("id") or "").isdigit()]


class HubSlotTests(unittest.TestCase):
    def test_there_are_eight_hub_slots_everywhere_a_slot_is_named(self):
        lists = ET.parse(ROOT / "shortcuts" / "generator" / "screens.xml").getroot().findall("lists/list")
        self.assertEqual([node.get("name") for node in lists if node.get("name").startswith("hub")], HUBS)
        self.assertEqual([home_menu.previewed(node) for node in home_menu.entries()][1:1 + HUB_SLOTS], HUBS)
        for n in range(1, HUB_SLOTS + 1):
            self.assertEqual(home_menu.control(9020 + n).get("type"), "button")
        editor = resolve_window("Custom_1117_BaldHomeScreens.xml")
        slots = [item.findtext("property[@name='slot']") for item in editor.findall(".//control[@id='9300']/content/item")
                 if item.findtext("property[@name='kind']") == "hub"]
        self.assertEqual(slots, [f"$INFO[Container(9390).ListItemAbsolute({n}).Property(item)]" for n in range(HUB_SLOTS)])
        full = ET.parse(XML / "Includes_Bald_Configure.xml").getroot().findtext("expression[@name='Bald_HubsFull']")
        self.assertEqual(full, f"[Integer.IsGreater(Container(9390).NumItems,{HUB_SLOTS - 1})]")
        timers = {node.findtext("name") for node in ET.parse(XML / "Timers.xml").getroot().findall("timer")}
        for _, _, base, _ in SCREENS:
            self.assertIn(f"bald_rowstart_{base + 1}", timers)

    def test_menu_order_is_home_hubs_live_tv_search_settings(self):
        self.assertEqual([home_menu.previewed(node) for node in home_menu.entries()],
                         ["home"] + HUBS + ["livetv", "search", "settings"])
        self.assertEqual([node.get("id") for node in home_menu.entries()],
                         ["9001"] + [str(9010 + n) for n in range(1, HUB_SLOTS + 1)] + ["9004", "9005", "9006"])

    def test_control_ids_do_not_collide_with_every_slot_full(self):
        # Twenty rows on Home, Live TV and all eight hubs: the most Home can build.
        full = [row(f"r{i}") for i in range(20)]
        text = build({"homewidgets": full, "livetvwidgets": full,
                      "hubs": [{"label": f"Hub {n}", "path": "videodb://movies/titles/", "target": "videos",
                                "widgets": full} for n in range(HUB_SLOTS)]})
        with tempfile.TemporaryDirectory() as folder:
            generated = Path(folder) / "generated.xml"
            generated.write_text(text, encoding="utf-8")
            skin = Skin(generated=generated)
            home = skin.window("Home.xml")
            self.assertEqual(skin.unknown_references(home), [])
        ids = control_ids(home)
        duplicates = [i for i, count in collections.Counter(ids).items() if count > 1]
        self.assertEqual(duplicates, [])
        expected_rows = {base + i for _, _, base, _ in SCREENS for i in range(1, 21)}
        self.assertLessEqual(expected_rows, set(ids))
        fixed = {9000, 9001, 9004, 9005, 9006, 9029, 9180, 9194, 9195, 9198, 9199}
        fixed |= set(range(9011, 9019)) | set(range(9021, 9029))
        self.assertFalse(fixed & expected_rows)
        self.assertLessEqual(fixed, set(ids))

    def test_empty_slots_build_nothing(self):
        root = ET.parse(FALLBACK).getroot()
        listed = len(hubs())
        for n in range(listed + 1, HUB_SLOTS + 1):
            hub, title = f"hub{n}", f"Hub{n}"
            self.assertEqual(list(root.find(f"include[@name='Bald_Generated_{title}Widgets']/definition")), [], hub)
            self.assertEqual(root.findtext(f"expression[@name='Bald_HubShown_{hub}']"), "[false]")
            self.assertEqual(root.findtext(f"expression[@name='Bald_HubHasOpen_{hub}']"), "[false]")
            self.assertEqual(list(root.find(f"include[@name='Bald_HubOpen_{hub}']/definition")), [])
        home = Skin().window("Home.xml")
        self.assertFalse([i for i in control_ids(home) if 9400 < i < 10000 and i % 100 <= 20])
        # Their menu entries stay hidden (and so unfocusable: the grouplist skips hidden entries).
        for n in range(listed + 1, HUB_SLOTS + 1):
            self.assertEqual(home_menu.entry(preview=f"hub{n}").findtext("visible"), f"$EXP[Bald_HubShown_hub{n}]")

    def test_a_hub_carries_its_label_open_target_and_switch(self):
        text = build({"hubs": [
            {"label": "Kids", "path": "videodb://movies/genres/", "target": "videos", "widgets": [row("a")]},
            {"label": "Off", "path": "videodb://tvshows/titles/", "target": "videos", "disabled": "True",
             "widgets": [row("b", style="poster", logo="off")]},
            {"label": "Weather", "path": "ActivateWindow(Weather)", "target": ""},
            {"label": "Nothing to open", "widgets": [row("c")]},
        ]})
        root = ET.fromstring(text.split("\n", 1)[1])
        values = lambda name: root.findtext(f"expression[@name='{name}']")
        self.assertEqual(root.findtext("variable[@name='Bald_HubLabel_hub1']/value"), "Kids")
        self.assertEqual(values("Bald_HubShown_hub1"), "[false]| [true]")
        self.assertEqual(root.findtext("include[@name='Bald_HubOpen_hub1']/definition/onfocus"),
                         "ActivateWindow(videos,videodb://movies/genres/,return)")
        # Turned off: out of the menu, rows kept (built, as a switched-off screen's rows always were).
        self.assertEqual(values("Bald_HubShown_hub2"), "[false]")
        self.assertEqual([node.findtext("param[@name='id']") for node in
                          root.findall("include[@name='Bald_Generated_Hub2Widgets']/definition/include")], ["9301"])
        # A path with no window is a builtin; no rows, but Select and Right open it.
        self.assertEqual(root.findtext("include[@name='Bald_HubOpen_hub3']/definition/onfocus"), "ActivateWindow(Weather)")
        self.assertEqual(values("Bald_HasRows_hub3"), "[false]")
        self.assertEqual(values("Bald_HubHasOpen_hub3"), "[false]| [true]")
        self.assertEqual(values("Bald_HubHasOpen_hub4"), "[false]")
        # Each hub's rows go back to its own menu entry.
        rows4 = root.findall("include[@name='Bald_Generated_Hub4Widgets']/definition/include")
        self.assertEqual([node.findtext("param[@name='menu']") for node in rows4], ["9014"])

    def test_the_seeded_hubs_are_movies_then_tv_shows_with_their_libraries(self):
        seeded = hubs()
        self.assertEqual([(hub["label"], hub["path"], hub["target"]) for hub in seeded],
                         [("$LOCALIZE[342]", "videodb://movies/titles/", "videos"),
                          ("$LOCALIZE[20343]", "videodb://tvshows/titles/", "videos")])
        self.assertEqual([hub["path"] for hub in seeded], [migration.SEED_PATHS["movies"], migration.SEED_PATHS["tvshows"]])
        self.assertTrue(all(hub["widgets"] and "disabled" not in hub for hub in seeded))
        self.assertFalse((ROOT / "shortcuts" / "skinvariables-shortcut-movieswidgets.json").exists())

    def test_right_opens_the_target_and_select_does_without_rows(self):
        includes = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        hub = includes.find("include[@name='Bald_HomeMenuHub']/definition/include[@content='Bald_HomeMenuButton']")
        self.assertEqual(hub.findtext("param[@name='right']"), "902$PARAM[n]")
        self.assertEqual(hub.findtext("param[@name='right_if']"), "$EXP[Bald_HubHasOpen_hub$PARAM[n]]")
        bridge = includes.find("include[@name='Bald_HubBridge']/definition/control")
        self.assertEqual(bridge.get("id"), "902$PARAM[n]")
        self.assertEqual(bridge.find("include").get("content"), "Bald_HubOpen_hub$PARAM[n]")


class LiveTVRowTests(unittest.TestCase):
    def test_live_tv_ships_pvr_rows_as_estuary_uses_them(self):
        shipped = rows("livetv")
        self.assertEqual([(r["path"], r["target"], r["sortby"], r["sortorder"]) for r in shipped], [
            ("pvr://channels/tv/*?view=lastplayed", "tvchannels", "lastplayed", "descending"),
            ("pvr://recordings/tv/active?view=flat", "tvrecordings", "date", "descending"),
            ("pvr://timers/tv/timers/?view=hidedisabled", "tvtimers", "date", "ascending"),
        ])
        # The same paths as Kodi 22's bundled Estuary Home PVR widgets, when that copy is present.
        estuary = Path("/Applications/Kodi.app/Contents/Resources/Kodi/addons/skin.estuary/xml/Home.xml")
        if estuary.is_file():
            text = estuary.read_text(encoding="utf-8")
            for r in shipped:
                self.assertIn(f'value="{r["path"]}"', text)
        root = ET.parse(FALLBACK).getroot()
        calls = root.findall("include[@name='Bald_Generated_LiveTVWidgets']/definition/include")
        self.assertEqual([node.findtext("param[@name='id']") for node in calls], ["9051", "9052", "9053"])
        for call, r in zip(calls, shipped):
            content = call.find("content")
            self.assertEqual((content.get("sortby"), content.get("sortorder")), (r["sortby"], r["sortorder"]))
            # Hidden without a PVR add-on.
            self.assertEqual(call.findtext("param[@name='enabled']"), "System.HasPVRAddon")
            self.assertEqual(call.findtext("param[@name='menu']"), "9004")
        # Rows without a sort field keep their old content element.
        home = root.find("include[@name='Bald_Generated_HomeWidgets']/definition/include/content")
        self.assertIsNone(home.get("sortby"))

    def test_live_tv_rows_count_only_with_pvr(self):
        includes = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        loading = includes.findtext("expression[@name='Bald_RowsLoading']")
        self.assertIn("[System.HasPVRAddon + !Skin.HasSetting(Bald.Screen.HideLiveTV) + $EXP[Bald_RowsLoading_livetv]]",
                      loading)
        self.assertTrue(equivalent(includes.findtext("expression[@name='Bald_PreviewLiveTV']"),
                                   "$EXP[Bald_MenuOpen] + $EXP[Bald_MenuPreview_livetv] + System.HasPVRAddon"))


class MigrationWiringTests(unittest.TestCase):
    def test_startup_and_home_start_the_migration_once(self):
        unset = "String.IsEmpty(Skin.String(Bald.HubsMigrated))"
        startup = [(node.get("condition"), node.text) for node in ET.parse(XML / "Startup.xml").getroot().findall("onload")]
        self.assertIn((unset, "SetProperty(Bald.HubsMigrating,1,home)"), startup)
        self.assertIn((unset, "RunScript(skin.bald,hubs)"), startup)
        home = [(node.get("condition"), node.text) for node in ET.parse(XML / "Home.xml").getroot().findall("onload")]
        idle = f"{unset} + String.IsEmpty(Window(home).Property(Bald.HubsMigrating))"
        started = [cond for cond, action in home if action == "RunScript(skin.bald,hubs)"]
        self.assertEqual(len(started), 1)
        self.assertTrue(equivalent(started[0], idle))
        self.assertTrue(any(action == "SetProperty(Bald.HubsMigrating,1,home)" and equivalent(cond, idle)
                            for cond, action in home))
        # The build waits for the marker, so it never builds from the old screens.
        build = next(cond for cond, action in home if action.startswith("RunScript(script.skinvariables,action=buildtemplate"))
        self.assertTrue(implies(build, "!" + unset))

    def test_the_script_is_dispatched(self):
        text = (ROOT / "scripts" / "info.py").read_text()
        self.assertIn('if action == "hubs":', text)
        self.assertIn("from hubs import migrate", text)


class FakeKodi:
    """Just enough of xbmc, xbmcgui and xbmcvfs for scripts/hubs.py."""

    def __init__(self, profile, bools=(), strings=None, home_active=False):
        self.profile = Path(profile)
        self.bools = set(bools)
        self.strings = dict(strings or {})
        self.builtins = []
        self.properties = {"Bald.HubsMigrating": "1"}
        self.home_active = home_active
        self.LOGINFO = 1
        self.logged = []

    # xbmcvfs
    def translatePath(self, path):
        if path.startswith("special://skin/"):
            return str(ROOT / path[len("special://skin/"):])
        return str(self.profile / path[len("special://profile/"):])

    def mkdirs(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)

    # xbmc
    def getCondVisibility(self, condition):
        match = re.fullmatch(r"Skin\.HasSetting\((.+)\)", condition)
        if match:
            return match.group(1) in self.bools
        return condition == "Window.IsActive(home)" and self.home_active

    def getInfoLabel(self, label):
        match = re.fullmatch(r"Skin\.String\((.+)\)", label)
        return self.strings.get(match.group(1), "") if match else "2026-09-26"

    def executebuiltin(self, action, wait=False):
        self.builtins.append(action)
        match = re.fullmatch(r"Skin\.SetString\(([^,]+),(.*)\)", action)
        if match:
            self.strings[match.group(1)] = match.group(2)
        match = re.fullmatch(r"Skin\.Reset\((.+)\)", action)
        if match:
            self.bools.discard(match.group(1))

    def log(self, message, level=0):
        self.logged.append(message)

    # xbmcgui
    def Window(self, window_id):
        return self

    def clearProperty(self, name):
        self.properties.pop(name, None)


def nodes(profile):
    return Path(profile) / "addon_data" / "script.skinvariables" / "nodes" / "skin.bald"


class MigrationTests(unittest.TestCase):
    def seed(self):
        return hubs()

    def test_a_fresh_install_writes_nothing_and_keeps_the_shipped_hubs(self):
        self.assertIsNone(migration.plan(self.seed(), None, {"movies": None, "tvshows": None},
                                         {"movies": False, "tvshows": False}, built_before=False))

    def test_an_old_install_moves_its_rows_and_switches_into_slots_one_and_two(self):
        movies = [row("In progress", style="poster", logo="off", guid="guid-1", icon="x.png")]
        result = migration.plan(self.seed(), None, {"movies": movies, "tvshows": None},
                                {"movies": True, "tvshows": False}, built_before=True)
        self.assertEqual([hub["path"] for hub in result], ["videodb://movies/titles/", "videodb://tvshows/titles/"])
        # Movies: the old list verbatim (every field), shown. TV shows: never edited, so the old shipped rows; off.
        self.assertEqual(result[0]["widgets"], movies)
        self.assertNotIn("disabled", result[0])
        self.assertEqual(result[1]["widgets"], self.seed()[1]["widgets"])
        self.assertEqual(result[1]["disabled"], "True")

    def test_hubs_the_user_already_changed_are_never_overwritten(self):
        changed = self.seed()[:1] + [{"label": "Mine", "path": "", "widgets": []}]
        self.assertIsNone(migration.plan(self.seed(), changed, {"movies": [row("x")], "tvshows": None},
                                         {"movies": True, "tvshows": True}, built_before=True))
        # The shipped list as Skin Variables copied it (with guids) still counts as untouched.
        copied = json.loads(json.dumps(self.seed()))
        for hub in copied:
            hub["guid"] = "guid-0"
            for widget in hub["widgets"]:
                widget["guid"] = "guid-1"
        self.assertTrue(migration.is_default(copied, self.seed()))
        self.assertIsNotNone(migration.plan(self.seed(), copied, {"movies": [row("x")], "tvshows": None},
                                            {"movies": True, "tvshows": True}, built_before=True))

    def test_migrate_writes_once_sets_the_marker_and_builds_on_home(self):
        with tempfile.TemporaryDirectory() as profile:
            folder = nodes(profile)
            folder.mkdir(parents=True)
            old_movies = [row("Custom movies", style="thumbnail")]
            (folder / "skinvariables-shortcut-movieswidgets.json").write_text(json.dumps(old_movies))
            kodi = FakeKodi(profile, bools={"Bald.Screen.Movies"}, home_active=True)
            migration.migrate(kodi, kodi, kodi)
            written = json.loads((folder / "skinvariables-shortcut-hubs.json").read_text())
            self.assertEqual(written[0]["widgets"], old_movies)
            self.assertNotIn("disabled", written[0])
            self.assertEqual(written[1]["disabled"], "True")
            self.assertEqual(kodi.strings["Bald.HubsMigrated"], "1")
            self.assertFalse(kodi.bools)
            self.assertNotIn("Bald.HubsMigrating", kodi.properties)
            stamp = kodi.strings["Bald.WidgetsStamp"]
            self.assertEqual(kodi.builtins[-1], f"RunScript(script.skinvariables,action=buildtemplate,lastbuildtime={stamp})")
            # The old list stays as a backup.
            self.assertTrue((folder / "skinvariables-shortcut-movieswidgets.json").exists())

            # Run again (the marker lost, say): the hubs list is the user's now, so nothing is duplicated or replaced.
            written[0]["label"] = "Films"
            (folder / "skinvariables-shortcut-hubs.json").write_text(json.dumps(written))
            again = FakeKodi(profile, bools={"Bald.Screen.Movies", "Bald.Screen.TVShows"})
            migration.migrate(again, again, again)
            self.assertEqual(json.loads((folder / "skinvariables-shortcut-hubs.json").read_text()), written)
            self.assertEqual(again.strings["Bald.HubsMigrated"], "1")

    def test_a_failed_migration_leaves_the_marker_unset_and_releases_the_lock(self):
        with tempfile.TemporaryDirectory() as profile:
            kodi = FakeKodi(profile)
            kodi.translatePath = lambda path: str(Path(profile) / "missing" / "nothing.json")
            with self.assertRaises(ValueError):
                migration.migrate(kodi, kodi, kodi)
            self.assertNotIn("Bald.HubsMigrated", kodi.strings)
            self.assertNotIn("Bald.HubsMigrating", kodi.properties)


if __name__ == "__main__":
    unittest.main()


class WidgetEditorUrlTests(unittest.TestCase):
    """Skin Variables 2.2.4 drops the node from the url of each row it lists for a nested list (its node setter only
    takes a string, and resolving the node assigns it a tuple), so an action on that url edits the top-level hubs list.
    The widget editor must address rows through Bald_WidgetItemUrl, which names the hub's node itself."""

    def test_editor_actions_never_use_the_rows_own_url(self):
        window = ET.parse(XML / "Custom_1116_BaldHomeWidgets.xml").getroot()
        actions = [re.fullmatch(r"RunPlugin\((.*)\)", node.text).group(1) for node in window.iter("onclick")
                   if node.text.startswith("RunPlugin(")]
        self.assertTrue(actions)
        for action in actions:
            with self.subTest(action=action[:60]):
                self.assertTrue(action.startswith("$VAR[Bald_WidgetItemUrl]&func="), action)

    def test_hub_rows_are_addressed_by_node_and_item(self):
        root = ET.parse(XML / "Includes_Bald_Configure.xml").getroot()
        values = root.find("variable[@name='Bald_WidgetItemUrl']").findall("value")
        self.assertIn("&node=$INFO[Window(home).Property(Bald.ConfigureItem)]", values[0].text)
        self.assertIn("&item=$INFO[Container(9100).ListItem.Property(item)]", values[0].text)
        self.assertEqual(values[-1].text, "$INFO[Container(9100).ListItem.Property(url)]")


class RowSortTests(unittest.TestCase):
    """The widget editor's Sort by and Order rows write the row's sortby / sortorder fields, and the generator puts them
    on the row's <content> only when set (no sortby keeps the path's own order)."""

    METHODS = {"title", "year", "rating", "dateadded", "lastplayed", "playcount", "time", "random"}

    def test_editor_offers_kodi_sort_methods_and_orders(self):
        window = ET.parse(XML / "Custom_1116_BaldHomeWidgets.xml").getroot()
        sort = window.find(".//control[@id='9210']").findtext("onclick")
        pairs = dict(p.split("=") for p in re.search(r"&&sortby&&(.*?)&&", sort).group(1).split("&"))
        self.assertEqual(pairs.pop("$LOCALIZE[571]"), "null")
        self.assertEqual(set(pairs.values()), self.METHODS)
        order = window.find(".//control[@id='9211']").findtext("onclick")
        self.assertIn("&&sortorder&&$LOCALIZE[584]=ascending&$LOCALIZE[585]=descending&&", order)
        self.assertIn("!String.IsEqual(Container(9100).ListItem.Property(sortby),random)", window.find(".//control[@id='9211']").findtext("visible"))

    def test_generator_writes_sort_attributes_only_when_set(self):
        rules = ET.parse(Path(__file__).resolve().parents[1] / "shortcuts" / "generator" / "screen.xml").getroot()
        content_sort = next(r for r in rules.iter("rules") if r.get("name") == "content_sort").findall("rule")
        self.assertEqual([c.text for c in content_sort[0].findall("condition")], ["{item_sortby}!=", "{item_sortorder}!="])
        self.assertEqual([c.text for c in content_sort[1].findall("condition")], ["{item_sortby}!="])
        self.assertEqual(content_sort[1].findtext("value"), ' sortby="{item_sortby}"')
        self.assertEqual(content_sort[-1].findall("condition"), [])
