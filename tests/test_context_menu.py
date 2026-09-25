"""Layout invariants for Kodi's dynamically populated context menu."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


XML = Path(__file__).resolve().parents[1] / '1080i'


class ContextMenuTests(unittest.TestCase):
    def setUp(self):
        self.root = ET.parse(XML / 'DialogContextMenu.xml').getroot()
        self.group = self.root.find(".//control[@id='996']")
        self.button = self.root.find(".//control[@id='1000']")

    def test_viewport_fits_exactly_five_buttons(self):
        height = int(self.button.findtext('height'))
        gap = int(self.group.findtext('itemgap'))
        self.assertEqual(int(self.group.find('height').get('max')), 5 * height + 4 * gap)
        self.assertEqual(self.group.findtext('scrolltime'), '0')

    def test_short_menu_still_clamps_dialog_to_screen_origin(self):
        background = int(self.root.find(".//control[@id='999']/height").text)
        maximum = int(self.group.find('height').get('max'))
        self.assertGreaterEqual(background - maximum, 1080)

    def test_navigation_does_not_wrap(self):
        self.assertEqual(self.group.findtext('onup'), 'noop')
        self.assertEqual(self.group.findtext('ondown'), 'noop')

    def test_note_is_shared_and_below_maximum_viewport(self):
        includes = ET.parse(XML / 'Includes_Bald_Home.xml').getroot()
        note = includes.find("include[@name='Bald_MenuNote']/definition/control")
        bottom = int(self.group.findtext('top')) + int(self.group.find('height').get('max'))
        self.assertEqual(note.findtext('top'), '$PARAM[y]')
        self.assertGreater(int(includes.findtext("include[@name='Bald_MenuNote']/param[@name='y']")), bottom)
        for name in ['Home.xml', 'DialogContextMenu.xml']:
            root = ET.parse(XML / name).getroot()
            self.assertIsNotNone(root.find(".//include[@content='Bald_MenuNote']"))


if __name__ == '__main__':
    unittest.main()
