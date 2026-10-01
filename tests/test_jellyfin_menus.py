"""Jellyfin for Kodi's context menu and resume prompt in Bald's context menu look (script-jellyfin-context.xml,
script-jellyfin-resume.xml): the ids the add-on binds, in the menu column."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from kodi_includes import Skin

XML = Path(__file__).resolve().parents[1] / "1080i"


class JellyfinMenuTests(unittest.TestCase):
    def test_resume_keeps_the_addons_buttons_in_the_menu_column(self):
        raw = ET.parse(XML / "script-jellyfin-resume.xml").getroot()
        self.assertEqual(raw.findtext("defaultcontrol"), "100")
        window = Skin().window("script-jellyfin-resume.xml")
        group = window.find(".//control[@id='100']")
        self.assertEqual((group.get("type"), group.findtext("left"), group.findtext("top")), ("grouplist", "1430", "392"))
        for button in ("3010", "3011"):
            node = group.find(f"control[@id='{button}']")
            self.assertEqual((node.findtext("height"), node.findtext("font"), node.findtext("textcolor")),
                             ("56", "Bald_MenuItem", "bald_ink34"))

    def test_context_keeps_the_addons_list_and_user_image(self):
        window = Skin().window("script-jellyfin-context.xml")
        self.assertEqual(ET.parse(XML / "script-jellyfin-context.xml").getroot().findtext("defaultcontrol"), "155")
        listing = window.find(".//control[@id='155']")
        self.assertEqual((listing.get("type"), listing.findtext("top")), ("list", "392"))
        self.assertEqual(listing.find("itemlayout").get("height"), "62")  # 56 + the menu's 6 px gap
        self.assertEqual(int(listing.findtext("height")), 5 * 56 + 4 * 6)
        self.assertIsNotNone(window.find(".//control[@id='150']"))  # the add-on sets it; hidden in Bald

    def test_the_kodi_menu_and_the_jellyfin_menus_share_one_look(self):
        for name in ("DialogContextMenu.xml", "script-jellyfin-resume.xml", "script-jellyfin-context.xml"):
            text = (XML / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn("<include>Bald_MenuMotion</include>", text)
                self.assertIn("<include>Bald_MenuScrim</include>", text)


if __name__ == "__main__":
    unittest.main()
