"""The Home row label line's item count: hidden unless Appearance turns on Bald.ShowRowCount."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import implies
from kodi_includes import expand_call, include_definitions
from skin_strings import bald_strings


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
SETTING = "Skin.HasSetting(Bald.ShowRowCount)"


def label_line(style):
    holder = ET.Element("holder")
    holder.extend(expand_call("Bald_Row", {"id": "9101", "style": style}, include_definitions()))
    return next(node for node in holder.iter("control") if node.get("type") == "grouplist")


class RowCountTests(unittest.TestCase):
    def test_the_count_shows_only_with_the_setting(self):
        for style in ("fanart", "thumbnail", "logo", "poster"):
            line = label_line(style)
            self.assertEqual(line.findtext("orientation"), "horizontal")
            children = line.findall("control")
            counts = [node for node in children if "NumItems" in (node.findtext("label") or "")]
            self.assertEqual(len(counts), 1, style)
            visible = counts[0].findtext("visible")
            self.assertIsNotNone(visible, style)
            # Unset means hidden: the count needs the setting, and the setting's absence hides it.
            self.assertTrue(implies(visible, SETTING), style)
            self.assertFalse(implies(visible, f"!{SETTING}"), style)

    def test_the_count_follows_the_label(self):
        children = label_line("fanart").findall("control")
        # The breadcrumb (screen name, slash), the label, then the count.
        self.assertEqual([node.get("type") for node in children], ["label"] * 4)
        # Only the count (last) collapses. The row hints are on Home's hint line (tests/test_home_row_hints.py).
        self.assertEqual([node.find("visible") is None for node in children], [True, True, True, False])

    def test_appearance_offers_the_toggle_under_information(self):
        root = ET.parse(XML / "Custom_1118_BaldAppearance.xml").getroot()
        rows = root.findall(".//control[@id='9600']/control")
        ids = [row.get("id") for row in rows]
        toggle = root.find(".//control[@id='9612']")
        self.assertIsNotNone(toggle)
        self.assertEqual(toggle.get("type"), "radiobutton")
        self.assertEqual(ids.index("9612"), ids.index("9611") + 1)
        setting_row = toggle.find("include[@content='Bald_SettingRow']")
        self.assertEqual(setting_row.findtext("param[@name='item']"), "2")
        self.assertEqual(toggle.findtext("selected"), SETTING)
        self.assertEqual(toggle.findtext("onclick"), "Skin.ToggleSetting(Bald.ShowRowCount)")
        self.assertEqual(toggle.findtext("label"), "$LOCALIZE[31769]")
        self.assertEqual(bald_strings()[31769], "Show item count in rows")


if __name__ == "__main__":
    unittest.main()
