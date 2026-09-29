"""Background images for main menu entries (Home Screens > Background image; Bald_ScreenArt_<screen>, Bald_Fanart).

A hub keeps its image in its own "image" field (Skin Variables do_edit), so it follows the hub when it moves; Home,
Live TV, Search, Settings and Power keep theirs in Skin.String(Bald.Art.<kind>). The menu shows the image while it
previews the entry, and a screen's rows show it in place of an item's thumb when the item has no fanart."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from kodi_includes import resolve_window


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
KINDS = ("home", "livetv", "search", "settings", "power")
HUB = "$EXP[Bald_HubCategorySelected]"


def kind(name):
    return f"String.IsEqual(Container(9300).ListItem.Property(kind),{name})"


class ScreenArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.window = resolve_window("Custom_1117_BaldHomeScreens.xml")

    def actions(self, control_id):
        control = self.window.find(f".//control[@id='{control_id}']")
        return [(node.get("condition"), node.text) for node in control.findall("onclick")]

    def test_a_hub_picks_its_image_into_its_own_field(self):
        hub = [action for condition, action in self.actions("9412") if condition == HUB]
        self.assertEqual(hub, [
            "Skin.Reset(Bald.PickedArt)",
            "Skin.SetImage(Bald.PickedArt)",
            "SetProperty(Bald.WidgetsDirty,1,home)",
            "RunPlugin($INFO[Container(9300).ListItem.Property(url)]&func=do_edit&&image&&$INFO[Skin.String(Bald.PickedArt)])",
        ])
        clear = [action for condition, action in self.actions("9413") if condition == HUB]
        self.assertEqual(clear[-1], "RunPlugin($INFO[Container(9300).ListItem.Property(url)]&func=do_edit&&image&&null)")

    def test_the_other_entries_keep_theirs_in_skin_strings(self):
        pick, clear = dict((c, a) for c, a in self.actions("9412")), dict((c, a) for c, a in self.actions("9413"))
        for name in KINDS:
            with self.subTest(kind=name):
                self.assertEqual(pick[kind(name)], f"Skin.SetImage(Bald.Art.{name})")
                self.assertEqual(clear[kind(name)], f"Skin.Reset(Bald.Art.{name})")

    def test_search_settings_and_power_are_listed(self):
        items = self.window.findall(".//control[@id='9300']/content/item")
        listed = [item.findtext("property[@name='kind']") for item in items]
        for name in ("search", "settings", "power"):
            self.assertIn(name, listed)

    def test_the_hub_list_exposes_each_hubs_image(self):
        items = self.window.findall(".//control[@id='9300']/content/item")
        hubs = [item for item in items if item.findtext("property[@name='kind']") == "hub"]
        for n, item in enumerate(hubs):
            self.assertEqual(item.findtext("property[@name='image']"),
                             f"$INFO[Container(9390).ListItemAbsolute({n}).Property(image)]")

    def test_every_screen_has_its_art_names(self):
        fallback = ET.parse(XML / "Includes_Bald_HomeDefaults.xml").getroot()
        for screen in ["home", "livetv"] + [f"hub{n}" for n in range(1, 9)]:
            with self.subTest(screen=screen):
                variable = fallback.find(f"variable[@name='Bald_ScreenArt_{screen}']")
                values = [(value.get("condition"), value.text) for value in variable.findall("value")]
                self.assertEqual(values[0], (f"!String.IsEmpty(Skin.String(Bald.Art.{screen}))",
                                             f"$INFO[Skin.String(Bald.Art.{screen})]"))
                self.assertIsNotNone(fallback.find(f"expression[@name='Bald_HasArt_{screen}']"))


if __name__ == "__main__":
    unittest.main()
