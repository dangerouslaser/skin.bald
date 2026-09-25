from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1] / '1080i'


class TVLibraryTests(unittest.TestCase):
    def setUp(self):
        self.root = ET.parse(ROOT / 'View_520_Bald_TV.xml').getroot()
        self.nav = ET.parse(ROOT / 'MyVideoNav.xml').getroot()

    def test_three_native_levels_are_registered_independently(self):
        expected = {520: 'tvshows', 530: 'seasons', 540: 'episodes'}
        views = self.nav.findtext('views').split(',')
        for control_id, content in expected.items():
            control = self.root.find(f".//control[@id='{control_id}']")
            self.assertIsNotNone(control)
            self.assertEqual(control.findtext('visible'), f'Container.Content({content})')
            self.assertIn(str(control_id), views)

    def test_series_and_seasons_use_native_poster_lists(self):
        for control_id in (520, 530):
            control = self.root.find(f".//control[@id='{control_id}']")
            self.assertEqual(control.get('type'), 'list')
            self.assertEqual(control.findtext('itemlayout/include'), 'Bald_LibraryPosterItem')
            self.assertIsNone(control.find('content'))
            self.assertEqual(int(control.findtext('width')), 3 * int(control.find('itemlayout').get('width')))

    def test_episode_view_is_seven_row_artwork_list(self):
        control = self.root.find(".//control[@id='540']")
        self.assertEqual(control.get('type'), 'list')
        self.assertEqual(int(control.findtext('height')), 7 * int(control.find('itemlayout').get('height')))
        self.assertEqual(control.findtext('itemlayout/include'), 'Bald_TVEpisodeRow')
        self.assertIsNotNone(self.root.find(".//include[@content='Bald_MediaFlagItems']"))
        self.assertEqual(len(self.root.findall("include[@name='View_540_Bald_Episodes']//include[@content='Bald_BackdropWindow']")), 4)

    def test_series_only_exposes_alphabet_navigation(self):
        series = self.root.find(".//control[@id='520']")
        seasons = self.root.find(".//control[@id='530']")
        episodes = self.root.find(".//control[@id='540']")
        self.assertEqual([n.text for n in series.findall('ondown')], ['SetFocus(9160)', 'RunScript(skin.bald,letters)'])
        self.assertEqual(seasons.findtext('ondown'), 'noop')
        self.assertIsNone(episodes.find('ondown'))

    def test_home_tv_item_opens_native_library(self):
        home = ET.parse(ROOT / 'Home.xml').getroot()
        item = next(item for item in home.findall(".//control[@id='9000']/content/item") if item.findtext('label') == 'TV shows')
        self.assertIn('ActivateWindow(Videos,videodb://tvshows/titles/,return)', [n.text for n in item.findall('onclick')])

    def test_legacy_chrome_is_hidden_for_every_bald_tv_level(self):
        custom = ('520', '530', '540')
        visible_conditions = [n.text or '' for n in self.nav.findall('.//visible')]
        self.assertTrue(any(all(f'!Control.IsVisible({view})' in condition for view in custom) for condition in visible_conditions))

    def test_legacy_video_views_route_tv_levels_to_bald_views(self):
        files = ('View_50_List.xml', 'View_51_Poster.xml', 'View_52_IconWall.xml', 'View_53_Shift.xml', 'View_54_InfoWall.xml', 'View_55_WideList.xml', 'View_500_Wall.xml', 'View_501_Banner.xml', 'View_504_MediaList.xml')
        expected = {
            'Container.Content(tvshows)': 'Container.SetViewMode(520)',
            'Container.Content(seasons)': 'Container.SetViewMode(530)',
            'Container.Content(episodes)': 'Container.SetViewMode(540)',
        }
        for filename in files:
            root = ET.parse(ROOT / filename).getroot()
            actions = {(node.get('condition'), node.text) for node in root.findall('.//onfocus')}
            for condition, action in expected.items():
                self.assertIn((condition, action), actions, filename)

    def test_shared_logo_has_container_tvshow_fallback(self):
        shared = ET.parse(ROOT / 'Includes_Bald_Home.xml').getroot()
        logo = shared.find("include[@name='Bald_ArtLogo']")
        textures = [node.text for node in logo.findall('definition/control/texture')]
        self.assertIn('$INFO[Container.Art(tvshow.clearlogo)]', textures)


if __name__ == '__main__':
    unittest.main()
