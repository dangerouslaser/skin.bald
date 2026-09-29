"""Where Home puts focus as it loads (Home.xml onload, Includes_Bald_Home.xml Bald_Restoring and Bald_StartOnMenu).

A fresh start (the first load of a Kodi session, or after the widget editor or Home Screens) opens the menu on the
start screen's entry, unless Appearance > Behavior starts on the rows. Returning from any other window keeps Home's
state and puts focus back where it was left: the menu entry it was on, or the row."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import home_menu
from conditions import implies


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
RESTORING = "$EXP[Bald_Restoring]"
RETURNING = "$EXP[Bald_ReturningToRow]"


class HomeReturnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = ET.parse(XML / "Home.xml").getroot()
        cls.includes = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        cls.onload = [(node.get("condition") or "true", node.text) for node in cls.home.findall("onload")]

    def expression(self, name):
        return self.includes.findtext(f"expression[@name='{name}']")

    def test_leaving_home_marks_the_next_load_as_a_return(self):
        self.assertEqual([node.text for node in self.home.findall("onunload")], ["SetProperty(Bald.Left,1,home)"])
        clear = self.onload.index(("true", "ClearProperty(Bald.Left,home)"))
        # Cleared last, after the onloads that read it.
        for index, (condition, _) in enumerate(self.onload):
            if "Bald_Restoring" in condition or "Bald_ReturningToRow" in condition:
                self.assertLess(index, clear)
        self.assertIn("!String.IsEmpty(Window(home).Property(Bald.Left))", self.expression("Bald_ReturningToRow"))
        self.assertIn("$EXP[Bald_ReturningToMenu]", self.expression("Bald_Restoring"))
        self.assertIn("$EXP[Bald_ReturningToRow]", self.expression("Bald_Restoring"))

    def test_changing_the_rows_starts_home_fresh(self):
        configure = ET.parse(XML / "Includes_Bald_Configure.xml").getroot()
        stamp = configure.find("include[@name='Bald_StampWidgetsOnUnload']")
        self.assertIn("ClearProperty(Bald.Left,home)", [node.text for node in stamp.findall("onunload")])

    def test_the_start_state_is_kept_on_every_return(self):
        for condition, action in self.onload:
            if action.startswith(("SetProperty(Bald.Row", "SetProperty(Bald.Screen,", "SetProperty(Bald.RowStyle,")):
                with self.subTest(action=action):
                    self.assertTrue(implies(condition, f"!{RESTORING}"), condition)

    def test_a_fresh_start_opens_the_menu_and_a_return_goes_back(self):
        fresh = [(c, a) for c, a in self.onload if a == "SetFocus($VAR[Bald_StartMenuEntry])" and "Bald_StartOnMenu" in c]
        self.assertEqual(len(fresh), 1)
        self.assertTrue(implies(fresh[0][0], f"!{RESTORING} + !$EXP[Bald_Preloading] + $EXP[Bald_StartHasRows]"))
        back = {a: c for c, a in self.onload if RETURNING in c}
        self.assertTrue(implies(back["SetFocus($VAR[Bald_MenuPreviewEntry])"], "$EXP[Bald_MenuOpen]"))
        self.assertTrue(implies(back["SetFocus($INFO[Window(home).Property(Bald.Row)])"], "!$EXP[Bald_MenuOpen]"))
        # After the fresh start's focus, so a return wins; before the splash takes focus.
        order = [a for _, a in self.onload]
        self.assertLess(self.onload.index(fresh[0]), order.index("SetFocus($VAR[Bald_MenuPreviewEntry])"))
        self.assertLess(order.index("SetFocus($VAR[Bald_MenuPreviewEntry])"), order.index("SetFocus(9198)"))

    def test_the_splash_lifts_onto_the_menu(self):
        lift = self.home.find(".//control[@id='9195']")
        actions = [(node.get("condition") or "true", node.text) for node in lift.findall("onfocus")]
        menu = [c for c, a in actions if a == "SetFocus($VAR[Bald_StartMenuEntry])" and "Bald_StartOnMenu" in c]
        self.assertEqual(len(menu), 1)
        # After the row that becomes current, so Back from the menu reaches it.
        self.assertGreater(actions.index((menu[0], "SetFocus($VAR[Bald_StartMenuEntry])")),
                           actions.index(("!$EXP[Bald_HomeHidden] + $EXP[Bald_HasRows_home]", "SetFocus(9101)")))

    def test_every_menu_entry_is_found_again_from_its_preview(self):
        variable = self.includes.find("variable[@name='Bald_MenuPreviewEntry']")
        by_preview = {value.get("condition"): value.text for value in variable.findall("value")}
        for entry in home_menu.entries():
            preview = home_menu.previewed(entry)
            with self.subTest(preview=preview):
                self.assertEqual(by_preview.get(f"$EXP[Bald_MenuPreview_{preview}]"), entry.get("id"))

    def test_behavior_offers_starting_on_the_rows(self):
        root = ET.parse(XML / "Custom_1118_BaldAppearance.xml").getroot()
        row = root.find(".//control[@id='9630']")
        self.assertEqual(row.get("type"), "radiobutton")
        self.assertEqual(row.findtext("onclick"), "Skin.ToggleSetting(Bald.HomeStartsOnRows)")
        self.assertEqual(row.findtext("selected"), "Skin.HasSetting(Bald.HomeStartsOnRows)")
        self.assertEqual(self.expression("Bald_StartOnMenu"), "[!Skin.HasSetting(Bald.HomeStartsOnRows)]")


if __name__ == "__main__":
    unittest.main()
