"""Startup splash: Home holds a splash over itself until every configured row has loaded (docs/NOTES.md)."""

import importlib.util
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import atoms, equivalent, implies, parse, same_actions
from skin_strings import english


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
SCREENS = (("home", 9100), ("movies", 9200), ("tvshows", 9300))
PRELOADING = "!String.IsEmpty(Window(home).Property(Bald.Preload))"


def configured(screen, base):
    rows = json.loads((ROOT / "shortcuts" / f"skinvariables-shortcut-{screen}widgets.json").read_text())
    return [base + index for index in range(1, len(rows) + 1)]


def load_builder():
    spec = importlib.util.spec_from_file_location("build_home_defaults", ROOT / "tools" / "build_home_defaults.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def loading_terms(text):
    """Bald_RowsLoading_<screen>: an "or" seeded with false (valid with no rows), one IsUpdating term per row."""
    if text.strip() == "[false]":
        return []
    kind, terms = parse(text)
    assert (kind, terms[0]) == ("or", False), text
    return terms[1:]


class PreloadSettingTests(unittest.TestCase):
    def test_setting_lives_in_behavior_and_defaults_on(self):
        root = ET.parse(XML / "Custom_1118_BaldAppearance.xml").getroot()
        row = root.find(".//control[@id='9624']")
        self.assertIsNotNone(row)
        self.assertEqual(row.get("type"), "radiobutton")
        # Behavior is category item 3.
        self.assertEqual(row.find("include[@content='Bald_SettingRow']/param[@name='item']").text, "3")
        self.assertEqual(english(row.findtext("label")), "Preload Home at startup")
        # A negatively named bool, so a fresh install (setting unset) preloads.
        self.assertEqual(row.findtext("selected"), "!Skin.HasSetting(Bald.DisablePreload)")
        self.assertEqual(row.findtext("onclick"), "Skin.ToggleSetting(Bald.DisablePreload)")


class PreloadRowsTests(unittest.TestCase):
    def test_every_row_counts_as_visible_while_preloading_and_still_loading(self):
        row = ET.parse(XML / "Includes_Bald_Home.xml").getroot().find(
            "include[@name='Bald_Row']/definition/control[@type='fixedlist']")
        visible = row.findtext("visible")
        # Whatever screen, row or menu state: preloading and still loading is enough.
        self.assertTrue(implies(f"{PRELOADING} + Container($PARAM[id]).IsUpdating", visible))
        # Once its list has fetched, the preload no longer holds the row visible (it hides behind the splash).
        self.assertFalse(implies(PRELOADING, visible))

    def test_fallback_waits_for_every_configured_row(self):
        fallback = ET.parse(XML / "Includes_Bald_HomeDefaults.xml").getroot()
        for screen, base in SCREENS:
            terms = loading_terms(fallback.findtext(f"expression[@name='Bald_RowsLoading_{screen}']"))
            self.assertEqual(terms, [("atom", f"Container({row}).IsUpdating") for row in configured(screen, base)])

    def test_generator_writes_one_loading_term_per_row_for_any_row_count(self):
        builder = load_builder()
        config = json.loads((ROOT / "shortcuts" / "skinvariables-generator.json").read_text())
        for count in (0, 1, 5):
            builder.menu_items = lambda menu, count=count: [
                {"label": f"Row {i}", "path": f"videodb://movies/titles/?r={i}", "target": "videos", "limit": "25",
                 "secondary": "0"} for i in range(count)]
            root = ET.fromstring(builder.build_xml(config))
            for screen, base in SCREENS:
                terms = loading_terms(root.findtext(f"expression[@name='Bald_RowsLoading_{screen}']"))
                self.assertEqual(terms, [("atom", f"Container({base + i}).IsUpdating") for i in range(1, count + 1)],
                                 (screen, count))

    def test_rows_loaded_covers_every_screen_and_waits_out_dialogs(self):
        text = "$EXP[Bald_RowsLoaded]"
        mentioned = atoms(text)
        for screen, base in SCREENS:
            for row in configured(screen, base):
                self.assertIn(f"Container({row}).IsUpdating", mentioned)
        # Under a modal dialog Container(...) reads the dialog, so the rows never count as loaded then.
        self.assertTrue(implies(text, "!System.HasActiveModalDialog"))
        # A Home row still loading keeps the splash up.
        self.assertTrue(implies("Container(9101).IsUpdating", "!" + text))


def timer(name):
    timers = ET.parse(XML / "Timers.xml").getroot()
    return next(node for node in timers.findall("timer") if node.findtext("name") == name)


class SplashTests(unittest.TestCase):
    def setUp(self):
        self.home = ET.parse(XML / "Home.xml").getroot()
        self.includes = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        self.splash = self.includes.find("include[@name='Bald_Splash']/control")

    def test_startup_sets_the_property_and_the_timeout_then_opens_the_startup_window(self):
        startup = ET.parse(XML / "Startup.xml").getroot()
        onload = [(node.get("condition"), node.text) for node in startup.findall("onload")]
        # The remote-only mouse fix and the hand-off to the startup window stay.
        self.assertIn(("System.GetBool(input.enablemouse)", "RunScript(skin.bald,mouse)"), onload)
        self.assertEqual(onload[-1], (None, "ReplaceWindow($INFO[System.StartupWindow])"))
        wanted = "!Skin.HasSetting(Bald.DisablePreload) + String.IsEqual(System.StartupWindow,10000)"
        for action in ("SetProperty(Bald.Preload,1,home)", "AlarmClock(bald_preload,noop,00:10,silent)"):
            condition = next(c for c, a in onload if a == action)
            self.assertTrue(equivalent(condition, wanted), action)
        # Only Startup.xml sets it: ReloadSkin and skin switches do not run Startup.xml.
        for path in XML.glob("*.xml"):
            if path.name != "Startup.xml":
                self.assertNotIn("SetProperty(Bald.Preload", path.read_text(), path.name)

    def test_splash_layer_shows_only_while_preloading_and_is_drawn_last(self):
        self.assertTrue(equivalent(self.splash.findtext("visible"), PRELOADING))
        top = [node for node in self.home.find("controls")]
        self.assertEqual((top[-1].tag, (top[-1].text or "").strip()), ("include", "Bald_Splash"))
        hidden = self.splash.find("animation[@type='Hidden']/effect")
        self.assertEqual((hidden.get("type"), hidden.get("time"), hidden.get("tween"), hidden.get("easing")),
                         ("fade", "600", "sine", "inout"))

    def test_splash_draws_cycling_library_fanart_and_the_wordmark(self):
        driver = self.splash.find("control[@id='9180']")
        # Inside the splash group, never hidden by a condition of its own (hidden lists do not load).
        self.assertIsNone(driver.find("visible"))
        self.assertEqual(driver.find("autoscroll").get("time"), "4500")
        self.assertEqual([node.text for node in driver.findall("content")],
                         ["special://skin/playlists/random_movies.xsp", "special://skin/playlists/random_tvshows.xsp"])
        image = next(node for node in self.splash.findall("control[@type='image']")
                     if node.findtext("texture") == "$VAR[Bald_SplashFanart]")
        self.assertEqual(image.find("texture").get("background"), "true")
        self.assertEqual(image.findtext("fadetime"), "1000")
        fanart = [value.text for value in self.includes.findall("variable[@name='Bald_SplashFanart']/value")]
        self.assertEqual(fanart, ["$INFO[Container(9180).ListItem.Art(fanart)]",
                                  "$INFO[Container(9180).ListItem.Art(tvshow.fanart)]"])
        labels = self.splash.findall("control[@type='label']")
        self.assertEqual([english(label.findtext("label")) for label in labels], ["Bald."])
        self.assertEqual(labels[0].findtext("font"), "Bald_Clock")
        self.assertEqual((labels[0].findtext("align"), labels[0].findtext("aligny")), ("center", "center"))

    def test_home_holds_the_first_row_and_focus_until_the_splash_lifts(self):
        onload = [(node.get("condition"), node.text) for node in self.home.findall("onload")]
        clear = onload.index(("$EXP[Bald_Preloading]", "ClearProperty(Bald.Row,home)"))
        focus = onload.index(("$EXP[Bald_Preloading]", "SetFocus(9198)"))
        # After everything else that sets the current row or focus.
        for index, (_, action) in enumerate(onload):
            if action.startswith(("SetProperty(Bald.Row,", "SetFocus(")) and index not in (clear, focus):
                self.assertLess(index, min(clear, focus), action)
        hold = self.home.find(".//control[@id='9198']")
        for tag in ("onup", "ondown", "onleft", "onright", "onclick", "onback"):
            for node in hold.findall(tag):
                if node.text != "noop":
                    self.assertTrue(implies(node.get("condition"), "!" + PRELOADING), tag)
        lift = self.home.find(".//control[@id='9195']")
        actions = [(node.get("condition"), node.text) for node in lift.findall("onfocus")]
        self.assertTrue(same_actions(actions, [
            (None, "ClearProperty(Bald.Preload,home)"),
            (None, "CancelAlarm(bald_preload,silent)"),
            ("$EXP[Bald_HasRows_home]", "SetFocus(9101)"),
            ("!$EXP[Bald_HasRows_home]", "SetFocus(9001)"),
        ]))

    def test_timer_lifts_when_rows_have_loaded_or_the_alarm_ran_out(self):
        marker = self.home.find(".//control[@id='9194']")
        self.assertTrue(equivalent(marker.findtext("visible"), "$EXP[Bald_RowsLoaded]"))
        lift = timer("bald_preload")
        start = lift.findtext("start")
        self.assertNotIn("$EXP[", start)
        base = f"Window.IsActive(home) + {PRELOADING} + !System.HasActiveModalDialog"
        self.assertTrue(implies(f"{base} + Control.IsVisible(9194)", start))
        # Timeout path: the 10 s alarm from Startup.xml has run out.
        self.assertTrue(implies(f"{base} + !System.HasAlarm(bald_preload)", start))
        self.assertTrue(implies(start, PRELOADING))
        self.assertEqual([node.text for node in lift.findall("onstart")],
                         ["ClearProperty(Bald.Preload,home)", "CancelAlarm(bald_preload,silent)", "SetFocus(9195)"])

    def test_idle_and_ambient_wait_for_the_splash(self):
        for name in ("bald_idle", "bald_ambient"):
            self.assertTrue(implies(timer(name).findtext("start"), "String.IsEmpty(Window(home).Property(Bald.Preload))"),
                            name)


if __name__ == "__main__":
    unittest.main()
