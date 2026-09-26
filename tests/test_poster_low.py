from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1] / '1080i'


class PosterLowTests(unittest.TestCase):
    def setUp(self):
        self.root = ET.parse(ROOT / 'View_515_Bald_PosterLow.xml').getroot()

    def test_native_horizontal_list_has_eight_visible_posters(self):
        control = self.root.find(".//control[@id='515']")
        self.assertEqual(control.get('type'), 'list')
        self.assertEqual(control.findtext('orientation'), 'horizontal')
        self.assertEqual(control.findtext('visible'), 'Container.Content(movies)')
        self.assertIsNone(control.find('content'))
        self.assertEqual(int(control.findtext('width')), 8 * int(control.find('itemlayout').get('width')))
        self.assertEqual((control.findtext('left'), control.findtext('width')), ('96', '1248'))
        self.assertGreaterEqual(int(control.findtext('height')), int(control.find('focusedlayout').get('height')))
        self.assertEqual([n.text for n in control.findall('ondown')], ['SetFocus(9160)', 'RunScript(skin.bald,letters,515)'])
        nav = ET.parse(ROOT / 'MyVideoNav.xml').getroot()
        self.assertIn('515', nav.findtext('views').split(','))
        self.assertIn('View_515_Bald_PosterLow', [n.text for n in nav.iter('include')])

    def test_reuses_home_art_logo_caption_and_flags(self):
        for name in ('Bald_ArtLayer', 'Bald_ArtLogo', 'Bald_Caption'):
            self.assertIsNotNone(self.root.find(f".//include[@content='{name}']"))
        caption = self.root.find("include[@name='Bald_PosterLowCaption']//include[@content='Bald_Caption']")
        self.assertEqual(caption.findtext("param[@name='c']"), '515')
        shared = ET.parse(ROOT / 'Includes_Bald_Home.xml').getroot()
        self.assertIsNotNone(shared.find("include[@name='Bald_Caption']//include[@content='Bald_MediaFlags']"))

    def test_masks_are_fixed_and_alphabet_covers_low_rail(self):
        view = self.root.find("include[@name='View_515_Bald_PosterLow']/control")
        masks = view.findall("include[@content='Bald_BackdropWindow']")
        self.assertEqual(len(masks), 4)
        letter_mask = next(group for group in view.findall('control') if group.findtext('visible') == '$EXP[Bald_LibraryLettersOpen]')
        self.assertIsNotNone(letter_mask.find("include[@content='Bald_BackdropWindow']"))
        preview = next(group for group in view.findall('control') if 'ListItem.Title' in (group.findtext('visible') or ''))
        self.assertFalse(preview.findall(".//include[@content='Bald_BackdropWindow']"))

    def test_options_footer_avoids_menu_note_and_poster_rail(self):
        footer = self.root.find("include[@name='Bald_PosterLowFooter']/definition")
        browse = next(node for node in footer.findall('control') if '!$EXP[Bald_LibraryMenuOpen]' in (node.findtext('visible') or ''))
        self.assertEqual(browse.findtext('top'), '954')
        group = next(node for node in footer.findall('control') if node.findtext('visible') == '$EXP[Bald_LibraryMenuOpen]')
        self.assertGreaterEqual(int(group.findtext('left')), 96 + 1248)
        self.assertGreaterEqual(int(group.findtext('top')), 936)

    def test_home_width_options_do_not_need_a_backdrop_panel(self):
        view = self.root.find("include[@name='View_515_Bald_PosterLow']/control")
        menu_masks = [group for group in view.findall('control') if group.findtext('visible') == '$EXP[Bald_LibraryMenuOpen]' and group.find("include[@content='Bald_BackdropWindow']") is not None]
        self.assertEqual(menu_masks, [])
        footer = self.root.find("include[@name='Bald_PosterLowFooter']/definition")
        hint = next(group for group in footer.findall('control') if group.findtext('visible') == '$EXP[Bald_LibraryMenuOpen]')
        self.assertEqual((hint.findtext('left'), hint.findtext("include/param[@name='width']")), ('1404', '420'))

    def test_focused_ring_fits_list_height(self):
        tile = self.root.find("include[@name='Bald_PosterLowTile']//include[@content='Bald_LibraryPosterItem']")
        ring_bottom = 9 + int(tile.findtext("param[@name='ring_height']"))
        list_height = int(self.root.find(".//control[@id='515']").findtext('height'))
        self.assertLessEqual(ring_bottom, list_height)
        ring_right = 9 + int(tile.findtext("param[@name='ring_width']"))
        center = int(tile.findtext("param[@name='center']").split(',')[0])
        focused_right = center + (ring_right - center) * 1.025
        self.assertLessEqual(focused_right, 156)
        poster_right = 12 + int(tile.findtext("param[@name='width']"))
        focused_poster_right = center + (poster_right - center) * 1.025
        self.assertLessEqual(focused_poster_right, 156)

    def test_side_masks_cover_full_settle_zoom(self):
        view = self.root.find("include[@name='View_515_Bald_PosterLow']/control")
        masks = view.findall("include[@content='Bald_BackdropWindow']")
        widths = [int(node.findtext("param[@name='w']")) for node in masks]
        self.assertGreaterEqual(widths[0], 32)
        self.assertGreaterEqual(widths[1], 32)
