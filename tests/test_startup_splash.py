"""Startup splash: Home holds a splash over itself until every configured row has loaded (docs/NOTES.md)."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from skin_strings import english


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"


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


if __name__ == "__main__":
    unittest.main()
