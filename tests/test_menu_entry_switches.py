"""Customization can take Search, Settings and Power out of Home's main menu (Bald.Screen.Hide*), but never Settings and
Power together, and a hidden Settings moves into the power menu, so Kodi's settings stay in reach."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import equivalent

XML = Path(__file__).resolve().parents[1] / "1080i"
KIND = "String.IsEqual(Container(9300).ListItem.Property(kind),{})"


class MenuEntrySwitchTests(unittest.TestCase):
    def test_home_hides_each_entry_by_its_switch(self):
        home = (XML / "Home.xml").read_text(encoding="utf-8")
        for button, name in (("9005", "Search"), ("9006", "Settings"), ("9007", "Power")):
            self.assertIn(f'<param name="id">{button}</param>', home)
            self.assertIn(f'<param name="visible">!Skin.HasSetting(Bald.Screen.Hide{name})</param>', home)

    def test_settings_and_power_are_never_both_hidden(self):
        root = ET.parse(XML / "Custom_1117_BaldHomeScreens.xml").getroot()
        switch = root.find(".//control[@id='9401']")
        enable = switch.findtext("enable")
        # Off while it is the shown one of the pair and the other is hidden; otherwise on.
        expected = (f"![[{KIND.format('settings')} + !Skin.HasSetting(Bald.Screen.HideSettings) + Skin.HasSetting(Bald.Screen.HidePower)]"
                    f" | [{KIND.format('power')} + !Skin.HasSetting(Bald.Screen.HidePower) + Skin.HasSetting(Bald.Screen.HideSettings)]]")
        self.assertTrue(equivalent(enable, expected))
        clicks = {node.get("condition"): node.text for node in switch.findall("onclick")}
        for name in ("search", "settings", "power"):
            self.assertEqual(clicks[KIND.format(name)], f"Skin.ToggleSetting(Bald.Screen.Hide{name.capitalize()})")

    def test_a_hidden_settings_is_in_the_power_menu(self):
        listing = ET.parse(XML / "DialogButtonMenu.xml").getroot().find(".//control[@id='9000']/content")
        settings = [item for item in listing.findall("item") if item.findtext("label") == "$LOCALIZE[5]"]
        self.assertEqual(len(settings), 1)
        self.assertEqual(settings[0].findtext("visible"), "Skin.HasSetting(Bald.Screen.HideSettings)")
        self.assertEqual([n.text for n in settings[0].findall("onclick")],
                         ["Dialog.Close(shutdownmenu)", "ActivateWindow(settings)"])


if __name__ == "__main__":
    unittest.main()
