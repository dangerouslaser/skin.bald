import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import equivalent


ROOT = Path(__file__).resolve().parents[1] / "1080i"


class SettingsAccessTests(unittest.TestCase):
    def test_platform_settings_are_available_when_installed(self):
        settings = ET.parse(ROOT / "Settings.xml").getroot()
        items = {item.findtext("label"): item for item in settings.findall(".//content/item")}

        expected = {
            "LibreELEC": "service.libreelec.settings",
            "CoreELEC": "service.coreelec.settings",
        }
        for label, addon_id in expected.items():
            item = items[label]
            self.assertEqual(item.findtext("onclick"), "RunAddon({})".format(addon_id))
            self.assertTrue(equivalent(item.findtext("visible"), "System.AddonIsEnabled({})".format(addon_id)))


if __name__ == "__main__":
    unittest.main()
