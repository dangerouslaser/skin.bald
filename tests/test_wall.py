from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1] / '1080i'


class WallTests(unittest.TestCase):
    def setUp(self):
        self.root = ET.parse(ROOT / 'View_511_Bald_Wall.xml').getroot()

    def test_native_eight_by_two_panel_registered_for_movies(self):
        panel = self.root.find(".//control[@id='511']")
        self.assertEqual(panel.get('type'), 'panel')
        self.assertEqual(panel.findtext('visible'), 'Container.Content(movies)')
        self.assertIsNone(panel.find('content'))
        self.assertEqual(int(panel.findtext('width')), 8 * int(panel.find('itemlayout').get('width')))
        self.assertEqual(int(panel.findtext('height')), 2 * int(panel.find('itemlayout').get('height')))
        nav = ET.parse(ROOT / 'MyVideoNav.xml').getroot()
        self.assertIn('511', nav.findtext('views').split(','))
        self.assertIn('View_511_Bald_Wall', [n.text for n in nav.iter('include')])

    def test_reuses_poster_and_media_flags(self):
        poster = self.root.find("include[@name='Bald_WallPoster']//include")
        self.assertEqual(poster.get('content'), 'Bald_LibraryPosterItem')
        self.assertEqual(poster.findtext("param[@name='width']"), '192')
        self.assertEqual(poster.findtext("param[@name='height']"), '288')
        self.assertEqual(poster.findtext("param[@name='show_label']"), 'false')
        flags = self.root.find(".//include[@content='Bald_MediaFlagItems']")
        self.assertEqual(flags.findtext("param[@name='c']"), '511')

    def test_shared_controls_exist_once_in_video_window(self):
        nav = ET.parse(ROOT / 'MyVideoNav.xml').getroot()
        for name in ('Bald_LibraryOptions', 'Bald_LibraryLetters'):
            self.assertEqual(sum(n.text == name for n in nav.iter('include')), 1)
        legacy = ET.parse(ROOT / 'View_510_Bald_Posters.xml').getroot()
        for root in (legacy.find("include[@name='View_510_Bald_Posters']"), self.root):
            self.assertFalse(any(n.text in ('Bald_LibraryOptions', 'Bald_LibraryLetters') for n in root.iter('include')))

    def test_preview_wall_has_five_by_two_native_slots(self):
        root = ET.parse(ROOT / 'View_512_Bald_WallPreview.xml').getroot()
        panel = root.find(".//control[@id='512']")
        self.assertEqual(panel.get('type'), 'panel')
        self.assertEqual(panel.findtext('visible'), 'Container.Content(movies)')
        self.assertIsNone(panel.find('content'))
        self.assertEqual(int(panel.findtext('width')), 5 * int(panel.find('itemlayout').get('width')))
        self.assertEqual(int(panel.findtext('height')), 2 * int(panel.find('itemlayout').get('height')))
        for name in ('Bald_LibraryPreview', 'Bald_WallFooter'):
            self.assertEqual(root.findtext(f".//include[@content='{name}']/param[@name='c']"), '512')
        self.assertEqual(panel.findtext('itemlayout/include'), 'Bald_WallPoster')
        self.assertIn('SetProperty(TMDbHelper.WidgetContainer,512,videos)', [n.text for n in panel.findall('onfocus')])
        nav = ET.parse(ROOT / 'MyVideoNav.xml').getroot()
        self.assertIn('512', nav.findtext('views').split(','))
        self.assertIn('View_512_Bald_WallPreview', [n.text for n in nav.iter('include')])
        self.assertTrue(all('512' in n.get('condition') for n in nav.findall(".//control[@id='9151']/onfocus")))
