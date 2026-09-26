import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


XML = Path(__file__).resolve().parents[1] / "1080i"
NO_ROWS = "!$EXP[Bald_HasRows_home]"
HAS_ROW = "!String.IsEmpty(Window(home).Property(Bald.Row))"


class HomeZeroRowsTests(unittest.TestCase):
    def test_generator_reports_whether_each_screen_has_rows(self):
        fallback = ET.parse(XML / "Includes_Bald_HomeDefaults.xml").getroot()
        for screen, count in (("home", 3), ("movies", 2), ("tvshows", 2)):
            text = fallback.findtext(f"expression[@name='Bald_HasRows_{screen}']")
            self.assertTrue(text.startswith("[false]"))
            self.assertEqual(text.count("| [true]"), count)

    def test_home_without_rows_focuses_the_menu_instead_of_a_missing_row(self):
        home = ET.parse(XML / "Home.xml").getroot()
        onload = [(node.get("condition"), node.text) for node in home.findall("onload")]
        self.assertIn((NO_ROWS, "ClearProperty(Bald.Row,home)"), onload)
        self.assertIn((NO_ROWS, "SetFocus(9001)"), onload)
        # After the unconditional current-row setup, before Search's own return focus.
        self.assertLess(onload.index((None, "SetProperty(Bald.Row,9101,home)")), onload.index((NO_ROWS, "ClearProperty(Bald.Row,home)")))
        search_focus = next(i for i, (_, action) in enumerate(onload) if action == "SetFocus(9005)")
        self.assertLess(onload.index((NO_ROWS, "SetFocus(9001)")), search_focus)

    def test_focus_returns_to_the_menu_when_there_is_no_current_row(self):
        includes = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        values = [(value.get("condition"), value.text) for value in includes.findall("variable[@name='Bald_RowFocus']/value")]
        self.assertEqual(values, [(HAS_ROW, "$INFO[Window(home).Property(Bald.Row)]"), (None, "9001")])
        wake = ET.parse(XML / "Home.xml").getroot().find(".//control[@id='9199']")
        for tag in ("onup", "ondown", "onleft", "onright", "onclick", "onback"):
            self.assertEqual(wake.findtext(tag), "SetFocus($VAR[Bald_RowFocus])")
        button = includes.find("include[@name='Bald_HomeMenuButton']/definition/control")
        for node in button.findall("onback"):
            self.assertEqual(node.get("condition"), HAS_ROW)
        timers = ET.parse(XML / "Timers.xml").getroot()
        ambient = next(t for t in timers.findall("timer") if t.findtext("name") == "bald_ambient")
        self.assertIn(HAS_ROW, ambient.find("onstop").get("condition"))

    def test_widget_editor_keeps_at_least_one_row(self):
        editor = ET.parse(XML / "Custom_1116_BaldHomeWidgets.xml").getroot()
        remove = editor.find(".//control[@id='9207']")
        self.assertEqual(remove.findtext("label"), "Remove widget")
        self.assertEqual(remove.findtext("visible"), "Integer.IsGreater(Container(9100).NumItems,1)")


if __name__ == "__main__":
    unittest.main()
