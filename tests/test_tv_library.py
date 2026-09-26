from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

import home_menu
from kodi_includes import expand


ROOT = Path(__file__).resolve().parents[1] / '1080i'


class TVLibraryTests(unittest.TestCase):
    def setUp(self):
        self.root = ET.parse(ROOT / 'View_520_Bald_TV.xml').getroot()
        self.alternates = ET.parse(ROOT / 'View_521_Bald_TV_Alternates.xml').getroot()
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
        self.assertIsNotNone(self.root.find(".//include[@content='Bald_MediaFlags']"))
        self.assertEqual(len(self.root.findall("include[@name='View_540_Bald_Episodes']//include[@content='Bald_BackdropWindow']")), 4)

    def test_series_only_exposes_alphabet_navigation(self):
        series = self.root.find(".//control[@id='520']")
        seasons = self.root.find(".//control[@id='530']")
        episodes = self.root.find(".//control[@id='540']")
        self.assertEqual([n.text for n in series.findall('ondown')], ['SetFocus(9160)', 'RunScript(skin.bald,letters,520)'])
        self.assertEqual(seasons.findtext('ondown'), 'noop')
        self.assertIsNone(episodes.find('ondown'))

    def test_home_tv_item_opens_configured_screen(self):
        item = home_menu.entry(label='TV shows')
        self.assertEqual(item.findtext("param[@name='visible']"), 'Skin.HasSetting(Bald.Screen.TVShows)')
        self.assertIn(
            'SetFocus($INFO[Window(home).Property(Bald.Row.tvshows)])',
            [action for _, action in home_menu.select_actions(item)],
        )

    def test_legacy_chrome_is_hidden_for_every_bald_tv_level(self):
        custom = ('520', '530', '540')
        visible_conditions = [n.text or '' for n in self.nav.findall('.//visible')]
        self.assertIn('!$EXP[Bald_LibraryViewActive]', visible_conditions)
        active = expand('$EXP[Bald_LibraryViewActive]')
        self.assertTrue(all(f'Control.IsVisible({view})' in active for view in custom))

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

    def test_alternate_views_are_registered_for_their_content_levels(self):
        expected = {521: 'tvshows', 522: 'tvshows', 523: 'tvshows', 531: 'seasons', 541: 'episodes', 542: 'episodes'}
        registered = self.nav.findtext('views').split(',')
        for control_id, content in expected.items():
            control = self.alternates.find(f".//control[@id='{control_id}']")
            self.assertIsNotNone(control, control_id)
            self.assertEqual(control.findtext('visible'), f'Container.Content({content})')
            self.assertIn(str(control_id), registered)

    def test_alternate_view_cycles_stay_within_each_tv_level(self):
        options = ET.parse(ROOT / 'View_510_Bald_Posters.xml').getroot().find("include[@name='Bald_LibraryOptions']")
        transitions = {}
        for item in options.findall('.//content/item'):
            visible = item.findtext('visible')
            actions = [node.text for node in item.findall('onclick')]
            if visible and visible.startswith('Control.IsVisible(') and actions and actions[0].startswith('Container.SetViewMode('):
                transitions[int(visible.removeprefix('Control.IsVisible(').removesuffix(')'))] = int(actions[0].removeprefix('Container.SetViewMode(').removesuffix(')'))
                self.assertEqual(actions[-1], 'SetFocus(9150)')
        self.assertEqual([transitions[n] for n in (520, 521, 522, 523)], [521, 522, 523, 520])
        self.assertEqual([transitions[n] for n in (530, 531)], [531, 530])
        self.assertEqual([transitions[n] for n in (540, 541, 542)], [541, 542, 540])

    def test_episode_wall_uses_cropped_sixteen_by_nine_thumbnails(self):
        tile = self.alternates.find("include[@name='Bald_TVEpisodeWallTile']")
        art = next(image for image in tile.findall('.//control[@type="image"]') if image.findtext('texture') == '$INFO[ListItem.Art(thumb)]')
        self.assertEqual((art.findtext('width'), art.findtext('height'), art.findtext('aspectratio')), ('192', '108', 'scale'))

    def test_alternate_episode_preview_keeps_metadata_flags_and_art_fallbacks(self):
        caption = self.alternates.find("include[@name='Bald_TVEpisodeSmallCaption']")
        self.assertIsNotNone(caption.find(".//include[@content='Bald_MediaFlags']"))
        # The episode line (air date and runtime) is the shared library episode meta, read from this caption's list.
        meta = caption.find(".//include[@content='Bald_MetaLibraryEpisode']")
        self.assertEqual(meta.findtext("param[@name='container']"), 'Container($PARAM[c]).')
        for container in (541, 542):
            variable = self.alternates.find(f"variable[@name='Bald_EpisodeThumb{container}']")
            values = [node.text or '' for node in variable.findall('value')]
            self.assertTrue(any('Art(thumb)' in value for value in values))
            self.assertTrue(any('Art(fanart)' in value for value in values))
            self.assertTrue(any('Container.Art(tvshow.fanart)' in value for value in values))

    def test_series_poster_low_rail_matches_artwork_width(self):
        view = self.alternates.find("include[@name='View_523_Bald_SeriesPosterLow']")
        rail = view.find(".//control[@id='523']")
        self.assertEqual(rail.findtext('width'), '1248')
        self.assertTrue(any(node.find("param[@name='w']").text == '1248' for node in view.findall(".//include[@content='Bald_BackdropWindow']") if node.find("param[@name='w']") is not None))


if __name__ == '__main__':
    unittest.main()
