from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from conditions import equivalent, shows_for_content
from kodi_includes import expand_call

ROOT = Path(__file__).resolve().parents[1] / '1080i'


class ArtworkListTests(unittest.TestCase):
    def test_native_seven_row_list_and_registration(self):
        root = ET.parse(ROOT / 'View_514_Bald_ArtworkList.xml').getroot()
        control = root.find(".//control[@id='514']")
        self.assertEqual(control.get('type'), 'list')
        self.assertIsNone(control.find('content'))
        self.assertTrue(shows_for_content(control.findtext('visible'), 'movies'))
        self.assertEqual(int(control.findtext('height')), 7 * int(control.find('itemlayout').get('height')))
        self.assertEqual(control.findtext('onleft'), '9150')
        self.assertEqual([n.text for n in control.findall('onright')], ['SetFocus(9160)', 'RunScript(skin.bald,letters,514)'])
        nav = ET.parse(ROOT / 'MyVideoNav.xml').getroot()
        self.assertIn('514', nav.findtext('views').split(','))
        self.assertIn('View_514_Bald_ArtworkList', [n.text for n in nav.iter('include')])

    def test_logo_geometry_keeps_home_defaults(self):
        # Called with only a row and parity (as Home does), every fallback image sits in Home's logo box.
        images = expand_call('Bald_ArtLogo', {'c': '9101', 'p': 'Odd'})
        self.assertEqual(len(images), 3)
        for image in images:
            self.assertEqual([image.findtext(key) for key in ('left', 'top', 'width', 'height')], ['52', '486', '560', '170'])

    def test_preview_reuses_home_art_logo_and_flags(self):
        root = ET.parse(ROOT / 'View_514_Bald_ArtworkList.xml').getroot()
        for name in ('Bald_ArtLayer', 'Bald_ArtLogo', 'Bald_MediaFlags', 'Bald_AnimCaptionIn'):
            self.assertIsNotNone(root.find(f".//include[@content='{name}']"))
        self.assertEqual(len(root.findall(".//include[@content='Bald_BackdropWindow']")), 4)

    def test_caption_does_not_fade_live_incoming_text_out(self):
        root = ET.parse(ROOT / 'View_514_Bald_ArtworkList.xml').getroot()
        caption = root.find("include[@name='Bald_ArtworkListCaption']/definition/control")
        self.assertIsNone(caption.find("animation[@type='Hidden']"))
        plot = caption.find("control[@type='textbox']")
        self.assertTrue(equivalent(plot.findtext('visible'), '!$EXP[Bald_LibraryLettersOpen]'))
