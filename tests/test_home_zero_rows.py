import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import equivalent, implies, parse, same_actions
from skin_strings import loc

import home_menu


XML = Path(__file__).resolve().parents[1] / "1080i"
NO_ROWS = "!$EXP[Bald_StartHasRows]"
HAS_ROW = "!String.IsEmpty(Window(home).Property(Bald.Row))"


class HomeZeroRowsTests(unittest.TestCase):
    def test_generator_reports_whether_each_screen_has_rows(self):
        fallback = ET.parse(XML / "Includes_Bald_HomeDefaults.xml").getroot()
        for screen, count in (("home", 3), ("livetv", 3), ("hub1", 2), ("hub2", 2), ("hub3", 0)):
            # An "or" of a false seed and one true term per configured row; an empty slot is just false.
            tree = parse(fallback.findtext(f"expression[@name='Bald_HasRows_{screen}']"))
            self.assertEqual(tree, ("or", [False] + [True] * count) if count else False)

    def test_home_without_rows_focuses_the_menu_instead_of_a_missing_row(self):
        home = ET.parse(XML / "Home.xml").getroot()
        onload = [(node.get("condition"), node.text) for node in home.findall("onload")]

        def position(condition, action):
            return next(i for i, pair in enumerate(onload) if same_actions([pair], [(condition, action)]))

        clear = position(NO_ROWS, "ClearProperty(Bald.Row,home)")
        focus = position(NO_ROWS, "SetFocus($VAR[Bald_StartMenuEntry])")
        # With Home shown that is Home's own test and entry (Bald_StartHasRows, Bald_StartMenuEntry).
        self.assertTrue(home_menu.same_under(NO_ROWS, "!$EXP[Bald_HasRows_home]", home_menu.HOME_SHOWN))
        self.assertEqual(home_menu.variable_value("Bald_StartMenuEntry", home_menu.HOME_SHOWN), "9001")
        # After the current-row setup (skipped only when returning to a menu entry), before Search's own return focus.
        self.assertLess(position("!$EXP[Bald_Restoring]", "SetProperty(Bald.Row,$VAR[Bald_StartRow],home)"), clear)
        search_focus = next(i for i, (_, action) in enumerate(onload) if action == "SetFocus(9005)")
        self.assertLess(focus, search_focus)

    def test_focus_returns_to_the_menu_when_there_is_no_current_row(self):
        includes = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        values = [(value.get("condition"), value.text) for value in includes.findall("variable[@name='Bald_RowFocus']/value")]
        self.assertTrue(same_actions(values, [(HAS_ROW, "$INFO[Window(home).Property(Bald.Row)]"),
                                              ("$EXP[Bald_HomeHidden]", "$VAR[Bald_StartMenuEntry]"), (None, "9001")]))
        self.assertIsNone(values[-1][0])
        wake = ET.parse(XML / "Home.xml").getroot().find(".//control[@id='9199']")
        for tag in ("onup", "ondown", "onleft", "onright", "onclick", "onback"):
            self.assertEqual(wake.findtext(tag), "SetFocus($VAR[Bald_RowFocus])")
        button = includes.find("include[@name='Bald_HomeMenuButton']/definition/control")
        backs = button.findall("onback")
        # With background video, Back from the menu returns to the video; otherwise to the row.
        self.assertEqual((backs[0].get("condition"), backs[0].text), ("$EXP[Bald_VideoBackdropOn]", "Action(FullScreen)"))
        for node in backs[1:]:
            self.assertTrue(equivalent(node.get("condition"), f"{HAS_ROW} + !$EXP[Bald_VideoBackdropOn]"))
        # Home's own move to the menu without rows is not a menu open the hint counts.
        counts = [n for n in button.findall("onfocus") if "Bald.MenuOpens" in n.text]
        self.assertEqual(len(counts), 3)
        for node in counts:
            self.assertIn("!$EXP[Bald_MenuOpen] + $EXP[Bald_HasRow] + ", node.get("condition"))
        # Timers.xml keeps the literal (docs/NOTES.md: $EXP in a timer condition did not trigger).
        timers = ET.parse(XML / "Timers.xml").getroot()
        ambient = next(t for t in timers.findall("timer") if t.findtext("name") == "bald_ambient")
        self.assertTrue(implies(ambient.find("onstop").get("condition"), HAS_ROW))

    def test_widget_editor_keeps_at_least_one_home_row(self):
        editor = ET.parse(XML / "Custom_1116_BaldHomeWidgets.xml").getroot()
        remove = editor.find(".//control[@id='9207']")
        self.assertEqual(remove.findtext("label"), loc("Remove widget"))
        home = "String.IsEqual(Window(home).Property(Bald.ConfigureNode),homewidgets)"
        # Home's last row stays; a hub or Live TV may lose its last row (then Select or Right opens its target).
        self.assertTrue(implies(f"{home} + !Integer.IsGreater(Container(9100).NumItems,1)", f"![{remove.findtext('visible')}]"))
        self.assertTrue(equivalent(remove.findtext("visible"),
                                   f"[Integer.IsGreater(Container(9100).NumItems,1) | !{home}]"
                                   " + String.IsEmpty(Container(9100).ListItem.Property(blank))"))


if __name__ == "__main__":
    unittest.main()
