from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1] / '1080i'


class ArtworkListTests(unittest.TestCase):
    def test_native_seven_row_list_and_registration(self):
        root = ET.parse(ROOT / 'View_514_Bald_ArtworkList.xml').getroot()
        control = root.find(".//control[@id='514']")
        self.assertEqual(control.get('type'), 'list')
        self.assertIsNone(control.find('content'))
        self.assertEqual(control.findtext('visible'), 'Container.Content(movies)')
        self.assertEqual(int(control.findtext('height')), 7 * int(control.find('itemlayout').get('height')))
        self.assertEqual(control.findtext('onleft'), '9150')
        self.assertEqual([n.text for n in control.findall('onright')], ['SetFocus(9160)', 'RunScript(skin.bald,letters,514)'])
        nav = ET.parse(ROOT / 'MyVideoNav.xml').getroot()
        self.assertIn('514', nav.findtext('views').split(','))
        self.assertIn('View_514_Bald_ArtworkList', [n.text for n in nav.iter('include')])

    def test_logo_geometry_keeps_home_defaults(self):
        root = ET.parse(ROOT / 'Includes_Bald_Home.xml').getroot()
        logo = root.find("include[@name='Bald_ArtLogo']")
        for key, value in [('x','52'), ('y','486'), ('width','560'), ('height','170')]:
            self.assertEqual(logo.findtext(f"param[@name='{key}']"), value)
        for image in logo.findall('definition/control'):
            self.assertEqual(image.findtext('width'), '$PARAM[width]')
            self.assertEqual(image.findtext('height'), '$PARAM[height]')

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
        self.assertEqual(plot.findtext('visible'), '!$EXP[Bald_LibraryLettersOpen]')
