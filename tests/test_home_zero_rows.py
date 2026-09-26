import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import equivalent, implies, parse, same_actions
from skin_strings import loc


XML = Path(__file__).resolve().parents[1] / "1080i"
NO_ROWS = "!$EXP[Bald_HasRows_home]"
HAS_ROW = "!String.IsEmpty(Window(home).Property(Bald.Row))"


class HomeZeroRowsTests(unittest.TestCase):
    def test_generator_reports_whether_each_screen_has_rows(self):
        fallback = ET.parse(XML / "Includes_Bald_HomeDefaults.xml").getroot()
        for screen, count in (("home", 3), ("movies", 2), ("tvshows", 2)):
            # An "or" of a false seed and one true term per configured row.
            tree = parse(fallback.findtext(f"expression[@name='Bald_HasRows_{screen}']"))
            self.assertEqual(tree, ("or", [False] + [True] * count))

    def test_home_without_rows_focuses_the_menu_instead_of_a_missing_row(self):
        home = ET.parse(XML / "Home.xml").getroot()
        onload = [(node.get("condition"), node.text) for node in home.findall("onload")]

        def position(condition, action):
            return next(i for i, pair in enumerate(onload) if same_actions([pair], [(condition, action)]))

        clear, focus = position(NO_ROWS, "ClearProperty(Bald.Row,home)"), position(NO_ROWS, "SetFocus(9001)")
        # After the unconditional current-row setup, before Search's own return focus.
        self.assertLess(position(None, "SetProperty(Bald.Row,9101,home)"), clear)
        search_focus = next(i for i, (_, action) in enumerate(onload) if action == "SetFocus(9005)")
        self.assertLess(focus, search_focus)

    def test_focus_returns_to_the_menu_when_there_is_no_current_row(self):
        includes = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        values = [(value.get("condition"), value.text) for value in includes.findall("variable[@name='Bald_RowFocus']/value")]
        self.assertTrue(same_actions(values, [(HAS_ROW, "$INFO[Window(home).Property(Bald.Row)]"), (None, "9001")]))
        self.assertIsNone(values[-1][0])
        wake = ET.parse(XML / "Home.xml").getroot().find(".//control[@id='9199']")
        for tag in ("onup", "ondown", "onleft", "onright", "onclick", "onback"):
            self.assertEqual(wake.findtext(tag), "SetFocus($VAR[Bald_RowFocus])")
        button = includes.find("include[@name='Bald_HomeMenuButton']/definition/control")
        for node in button.findall("onback"):
            self.assertTrue(equivalent(node.get("condition"), HAS_ROW))
        # Timers.xml keeps the literal (docs/NOTES.md: $EXP in a timer condition did not trigger).
        timers = ET.parse(XML / "Timers.xml").getroot()
        ambient = next(t for t in timers.findall("timer") if t.findtext("name") == "bald_ambient")
        self.assertTrue(implies(ambient.find("onstop").get("condition"), HAS_ROW))

    def test_widget_editor_keeps_at_least_one_row(self):
        editor = ET.parse(XML / "Custom_1116_BaldHomeWidgets.xml").getroot()
        remove = editor.find(".//control[@id='9207']")
        self.assertEqual(remove.findtext("label"), loc("Remove widget"))
        self.assertTrue(equivalent(remove.findtext("visible"), "Integer.IsGreater(Container(9100).NumItems,1)"))


if __name__ == "__main__":
    unittest.main()
