"""Home hidden from the main menu (Home Screens > Home > Show in the main menu; Bald.Screen.HideHome).

Home never hides with no hub shown. Hidden, Home's rows are disabled and Home's onload starts on the first shown hub
with rows (menu order), else Live TV's rows, else the menu open on the first shown hub (docs/NOTES.md, Home hidden)."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import home_menu
from conditions import equivalent, implies, same_actions
from kodi_includes import expand_follow


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
HIDE = "Skin.HasSetting(Bald.Screen.HideHome)"
HUBS = range(1, 9)
# Includes_Bald_Home.xml's expressions only: the generated per-slot names stay atoms, so every hub layout is covered.
BODIES = home_menu.setting(False)


def shown(n):
    return f"$EXP[Bald_HubShown_hub{n}]"


def rows(n):
    return f"$EXP[Bald_HasRows_hub{n}]"


def layout(hidden=True, shown_hubs=(), rows_hubs=(), livetv=False):
    """Atom values for a menu: Home hidden or not, which hubs are shown and which have rows, Live TV's rows."""
    assume = {HIDE: hidden, "Skin.HasSetting(Bald.Screen.HideLiveTV)": False,
              "System.HasPVRAddon": livetv, "$EXP[Bald_HasRows_livetv]": livetv, "$EXP[Bald_HasRows_home]": True}
    for n in HUBS:
        assume[shown(n)] = n in shown_hubs
        assume[rows(n)] = n in rows_hubs
    return assume


def start(assume):
    return {name: home_menu.variable_value(name, assume, BODIES)
            for name in ("Bald_StartScreen", "Bald_StartRow", "Bald_StartRowStyle", "Bald_StartMenuEntry")}


def holds(condition, assume):
    return implies("true", condition, BODIES, assume=assume)


class HiddenHomeTests(unittest.TestCase):
    def setUp(self):
        self.includes = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        self.home = ET.parse(XML / "Home.xml").getroot()

    def test_home_hides_only_while_some_hub_is_shown(self):
        hidden = self.includes.findtext("expression[@name='Bald_HomeHidden']")
        any_hub = " | ".join(shown(n) for n in HUBS)
        self.assertTrue(equivalent(hidden, f"{HIDE} + [{any_hub}]", BODIES))
        self.assertEqual(home_menu.entry(preview="home").findtext("visible"), "!$EXP[Bald_HomeHidden]")
        # Never everything hidden: with no hub shown the Home entry stays whatever the setting says.
        self.assertTrue(holds("!$EXP[Bald_HomeHidden]", layout(hidden=True)))

    def test_home_shown_starts_exactly_as_before(self):
        self.assertEqual(start(layout(hidden=False, shown_hubs=(1, 2), rows_hubs=(1, 2))), {
            "Bald_StartScreen": "home", "Bald_StartRow": "9101",
            "Bald_StartRowStyle": "$VAR[Bald_RowStyle_home]", "Bald_StartMenuEntry": "9001"})
        self.assertTrue(holds("$EXP[Bald_StartHasRows]", layout(hidden=False)))

    def test_hidden_starts_on_the_first_shown_hub_with_rows(self):
        # Hub 1 shown without rows, hub 2 hidden with rows, hub 3 shown with rows: hub 3.
        assume = layout(shown_hubs=(1, 3, 4), rows_hubs=(2, 3, 4), livetv=True)
        self.assertEqual(start(assume), {"Bald_StartScreen": "hub3", "Bald_StartRow": "9401",
                                         "Bald_StartRowStyle": "$VAR[Bald_RowStyle_hub3]", "Bald_StartMenuEntry": "9011"})
        self.assertTrue(holds("$EXP[Bald_StartHasRows]", assume))

    def test_hidden_starts_on_live_tv_when_no_shown_hub_has_rows(self):
        assume = layout(shown_hubs=(2,), rows_hubs=(1,), livetv=True)
        self.assertEqual(start(assume)["Bald_StartScreen"], "livetv")
        self.assertEqual(start(assume)["Bald_StartRow"], "9051")
        self.assertEqual(start(assume)["Bald_StartRowStyle"], "$VAR[Bald_RowStyle_livetv]")
        self.assertTrue(holds("$EXP[Bald_StartHasRows]", assume))

    def test_hidden_with_nothing_to_show_opens_the_menu_on_the_first_shown_hub(self):
        assume = layout(shown_hubs=(2, 5), rows_hubs=(), livetv=False)
        self.assertTrue(holds("!$EXP[Bald_StartHasRows]", assume))
        self.assertEqual(start(assume)["Bald_StartMenuEntry"], "9012")
        self.assertEqual(start(assume)["Bald_StartScreen"], "hub2")
        loads = [(n.get("condition"), n.text) for n in self.home.findall("onload")]
        self.assertIn(("!$EXP[Bald_StartHasRows]", "ClearProperty(Bald.Row,home)"), loads)
        self.assertIn(("!$EXP[Bald_StartHasRows]", "SetFocus($VAR[Bald_StartMenuEntry])"), loads)

    def test_onload_sets_the_start_state_and_focus_unless_returning_to_a_menu_entry(self):
        loads = [(n.get("condition"), n.text) for n in expand_follow(self.home) if n.tag == "onload"]
        returning = "!$EXP[Bald_ReturningToMenu]"
        for action in ("SetProperty(Bald.Row,$VAR[Bald_StartRow],home)", "SetProperty(Bald.Screen,$VAR[Bald_StartScreen],home)",
                       "SetProperty(Bald.RowStyle,$VAR[Bald_StartRowStyle],home)",
                       "SetProperty(Bald.FocusContainer,$VAR[Bald_StartRow],home)"):
            with self.subTest(action=action):
                self.assertTrue(same_actions([p for p in loads if p[1] == action], [(returning, action)]))
        self.assertTrue(same_actions([p for p in loads if p[1] == "SetProperty(TMDbHelper.WidgetContainer,$VAR[Bald_StartRow],home)"],
                                     [(f"{returning} + $EXP[Bald_TMDbHelperFollows]",
                                       "SetProperty(TMDbHelper.WidgetContainer,$VAR[Bald_StartRow],home)")]))
        texts = [text for _, text in loads]
        focus = texts.index("SetFocus($INFO[Window(home).Property(Bald.Row)])")
        cond = loads[focus][0]
        self.assertTrue(equivalent(cond, f"{returning} + !$EXP[Bald_Preloading] + $EXP[Bald_HomeHidden] + $EXP[Bald_StartHasRows]"))
        # After the start row is set; before Search's and the menu entry's return focus and the splash's hold.
        self.assertLess(texts.index("SetProperty(Bald.Row,$VAR[Bald_StartRow],home)"), focus)
        for later in ("SetFocus(9005)", "SetFocus(9198)"):
            self.assertLess(focus, texts.index(later))
        children = list(self.home)
        position = next(i for i, n in enumerate(children) if n.tag == "onload" and n.text == "SetFocus($INFO[Window(home).Property(Bald.Row)])")
        restore = next(i for i, n in enumerate(children) if n.tag == "include" and n.text == "Bald_ReturnToMenu")
        self.assertLess(position, restore)
        # The default control is still Home's row 1.
        self.assertEqual(self.home.find("defaultcontrol").get("always"), "true")
        self.assertEqual(self.home.findtext("defaultcontrol"), "9101")

    def test_home_rows_are_disabled_while_home_is_hidden(self):
        screens = ET.parse(ROOT / "shortcuts" / "generator" / "screens.xml").getroot()
        home = screens.find("lists/list[@name='home']")
        self.assertEqual(home.findtext("value[@name='enabled']"), "!$EXP[Bald_HomeHidden]")
        fallback = ET.parse(XML / "Includes_Bald_HomeDefaults.xml").getroot()
        calls = fallback.findall("include[@name='Bald_Generated_HomeWidgets']/definition/include")
        self.assertTrue(calls)
        self.assertEqual({c.findtext("param[@name='enabled']") for c in calls}, {"!$EXP[Bald_HomeHidden]"})
        # Not waited for behind the splash.
        loading = self.includes.findtext("expression[@name='Bald_RowsLoading']")
        self.assertIn("[!$EXP[Bald_HomeHidden] + $EXP[Bald_RowsLoading_home]]", loading)

    def test_stranded_focus_moves_on_through_9195(self):
        marker = next(c for c in self.home.iter("control") if c.get("id") == "9193")
        self.assertEqual(marker.findtext("visible"), "$EXP[Bald_HomeRowStranded]")
        stranded = self.includes.findtext("expression[@name='Bald_HomeRowStranded']")
        self.assertTrue(implies(stranded, "$EXP[Bald_HomeHidden] + !$EXP[Bald_Preloading]", BODIES))
        self.assertIn("Integer.IsGreater(System.CurrentControlID,9100)", stranded)
        self.assertIn("Integer.IsLess(System.CurrentControlID,9121)", stranded)
        timers = ET.parse(XML / "Timers.xml").getroot()
        timer = next(t for t in timers.findall("timer") if t.findtext("name") == "bald_home_start")
        self.assertNotIn("$EXP[", timer.findtext("start"))
        self.assertTrue(equivalent(timer.findtext("start"), "Window.IsActive(home) + Control.IsVisible(9193)"))
        self.assertEqual(timer.findtext("onstart"), "SetFocus(9195)")
        lift = next(c for c in self.home.iter("control") if c.get("id") == "9195")
        for tag in ("onup", "ondown", "onleft", "onright", "onclick"):
            self.assertEqual(lift.findtext(tag), "SetFocus($VAR[Bald_RowFocus])")

    def test_home_screens_offers_the_switch_and_explains_home(self):
        from skin_strings import strings
        editor = ET.parse(XML / "Custom_1117_BaldHomeScreens.xml").getroot()
        switch = editor.find(".//control[@id='9401']")
        home = "String.IsEqual(Container(9300).ListItem.Property(kind),home)"
        self.assertTrue(implies(home, switch.findtext("visible")))
        self.assertIn((home, "Skin.ToggleSetting(Bald.Screen.HideHome)"), [(n.get("condition"), n.text) for n in switch.findall("onclick")])
        self.assertTrue(implies(f"{home} + !{HIDE}", switch.findtext("selected")))
        only_home = {"String.IsEqual(Container(9300).ListItem.Property(kind),livetv)": False,
                     "String.IsEqual(Container(9300).ListItem.Property(kind),hub)": False}
        self.assertTrue(implies(f"{home} + {HIDE}", f"![{switch.findtext('selected')}]", assume=only_home))
        note = next(i for i in editor.iter("item") if i.findtext("property[@name='kind']") == "home")
        self.assertEqual(note.findtext("property[@name='note']"), "$LOCALIZE[31741]")
        self.assertIn("everyday rows", strings()[31741])


if __name__ == "__main__":
    unittest.main()
