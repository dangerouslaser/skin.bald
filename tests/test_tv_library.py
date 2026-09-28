from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

import home_menu
from kodi_includes import expand_call
from conditions import atoms, equivalent, has_action, implies, shows_for_content


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
            self.assertTrue(shows_for_content(control.findtext('visible'), content), control_id)
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
        self.assertEqual([n.text for n in series.findall('ondown')], ['SetFocus(9160)', 'NotifyAll(skin.bald,bald.letters|520)', 'RunScript(skin.bald,letters,520)'])
        self.assertEqual(seasons.findtext('ondown'), 'noop')
        self.assertIsNone(episodes.find('ondown'))

    def test_home_tv_item_opens_configured_screen(self):
        # TV shows is the second seeded hub (slot 2).
        item = home_menu.entry(preview='hub2')
        self.assertTrue(equivalent(item.findtext("visible"), '$EXP[Bald_HubShown_hub2]'))
        self.assertIn(
            'SetFocus($INFO[Window(home).Property(Bald.Row.hub2)])',
            [action for _, action in home_menu.select_actions(item)],
        )

    def test_legacy_chrome_is_hidden_for_every_bald_tv_level(self):
        custom = ('520', '530', '540')
        visible_conditions = [n.text for n in self.nav.findall('.//visible') if n.text]
        self.assertTrue(any(equivalent(text, '!$EXP[Bald_LibraryViewActive]') for text in visible_conditions))
        for view in custom:
            self.assertTrue(implies(f'Control.IsVisible({view})', '$EXP[Bald_LibraryViewActive]'), view)

    def test_legacy_video_views_route_tv_levels_to_bald_views(self):
        files = ('View_50_List.xml', 'View_51_Poster.xml', 'View_52_IconWall.xml', 'View_53_Shift.xml', 'View_54_InfoWall.xml', 'View_55_WideList.xml', 'View_500_Wall.xml', 'View_501_Banner.xml', 'View_504_MediaList.xml')
        expected = {
            'Container.Content(movies)': 'Container.SetViewMode(510)',
            'Container.Content(tvshows)': 'Container.SetViewMode(520)',
            'Container.Content(seasons)': 'Container.SetViewMode(530)',
            'Container.Content(episodes)': 'Container.SetViewMode(540)',
        }
        for filename in files:
            root = ET.parse(ROOT / filename).getroot()
            self.assertIn('Bald_BaldViewRedirect', [node.text for node in root.iter('include')], filename)
        actions = [(node.get('condition'), node.text) for node in expand_call('Bald_BaldViewRedirect')]
        for condition, action in expected.items():
            self.assertTrue(has_action(actions, condition, action), action)

    def test_shared_logo_has_container_tvshow_fallback(self):
        shared = ET.parse(ROOT / 'Includes_Bald_Home.xml').getroot()
        logo = shared.find("include[@name='Bald_ArtLogo']")
        textures = [node.text for node in logo.findall('definition/control/control/texture')]
        self.assertIn('$INFO[Container.Art(tvshow.clearlogo)]', textures)

    def test_alternate_views_are_registered_for_their_content_levels(self):
        expected = {521: 'tvshows', 522: 'tvshows', 523: 'tvshows', 531: 'seasons', 541: 'episodes', 542: 'episodes'}
        registered = self.nav.findtext('views').split(',')
        for control_id, content in expected.items():
            control = self.alternates.find(f".//control[@id='{control_id}']")
            self.assertIsNotNone(control, control_id)
            self.assertTrue(shows_for_content(control.findtext('visible'), content), control_id)
            self.assertIn(str(control_id), registered)

    def test_alternate_view_cycles_stay_within_each_tv_level(self):
        options = ET.Element('holder')
        options.extend(expand_call('Bald_LibraryOptions'))
        transitions = {}
        for item in options.findall('.//content/item'):
            visible = item.findtext('visible')
            actions = [node.text for node in item.findall('onclick')]
            if visible and actions and actions[0].startswith('Container.SetViewMode('):
                # Each view item shows for exactly one view.
                view, = atoms(visible)
                self.assertTrue(equivalent(visible, view), visible)
                transitions[int(re.fullmatch(r'Control\.IsVisible\((\d+)\)', view).group(1))] = int(
                    re.fullmatch(r'Container\.SetViewMode\((\d+)\)', actions[0]).group(1))
                self.assertEqual(actions[-1], 'SetFocus(9150)')
        self.assertEqual([transitions[n] for n in (520, 521, 522, 523)], [521, 522, 523, 520])
        self.assertEqual([transitions[n] for n in (530, 531, 532)], [531, 532, 530])
        self.assertEqual([transitions[n] for n in (540, 541, 542)], [541, 542, 540])

    def test_episode_wall_uses_cropped_sixteen_by_nine_thumbnails(self):
        tile = self.alternates.find("include[@name='Bald_TVEpisodeWallTile']")
        art = next(image for image in tile.findall('.//control[@type="image"]') if image.findtext('texture') == '$VAR[Bald_EpisodeThumb]')
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


class SeriesPageTests(unittest.TestCase):
    """View 532: the Seasons level drawn as the TV info page (docs/SPEC.md 5.12)."""

    def setUp(self):
        self.alternates = ET.parse(ROOT / 'View_521_Bald_TV_Alternates.xml').getroot()
        self.view = self.alternates.find("include[@name='View_532_Bald_SeriesPage']")
        self.nav = ET.parse(ROOT / 'MyVideoNav.xml').getroot()
        self.tabs = self.view.find(".//control[@id='532']")
        self.row = self.view.find(".//control[@id='5302']")
        self.built = expand_call('View_532_Bald_SeriesPage')[0]

    def test_series_page_is_a_registered_seasons_view(self):
        self.assertEqual(self.tabs.get('type'), 'list')
        self.assertTrue(shows_for_content(self.tabs.findtext('visible'), 'seasons'))
        self.assertEqual(self.tabs.find('viewtype').get('label'), '31846')
        self.assertIn('532', self.nav.findtext('views').split(','))
        self.assertIn('View_532_Bald_SeriesPage', [n.text for n in self.nav.iter('include')])
        # Kodi's own seasons container: no content provider of its own.
        self.assertIsNone(self.tabs.find('content'))
        for expression in ('$EXP[Bald_LibrarySeasonView]', '$EXP[Bald_LibraryViewActive]'):
            self.assertTrue(implies('Control.IsVisible(532)', expression), expression)
        self.assertTrue(equivalent(self.view.find('control').findtext('visible'), 'Control.IsVisible(532)'))

    def test_series_page_reuses_the_info_page_parts(self):
        calls = {n.get('content') or n.text: {p.get('name'): p.text for p in n.findall('param')}
                 for n in self.view.iter('include')}
        for name in ('Bald_InfoTVHeader', 'Bald_InfoScrims', 'Bald_InfoTVDim', 'Bald_InfoTVEpisodeSwap',
                     'Bald_InfoTVEpisodeRowLayout', 'Bald_InfoTVEpisodeDetail'):
            self.assertIn(name, calls)
        self.assertEqual(calls['Bald_InfoTVTabsLayout'], {'tabs': '532'})
        # The library's own ratings setting governs the episode line; the header has no show item to rate.
        self.assertEqual(calls['Bald_InfoTVEpisodeDetail']['ratings'], '$EXP[Bald_RatingsLibrary]')
        self.assertNotIn('ratings', calls['Bald_InfoTVHeader'])
        self.assertEqual(calls['Bald_InfoTVHeader']['plot'], '$INFO[Container.ShowPlot]')
        # The underline follows the view list's focus, and Kodi's parent item gets none.
        underline = self.built.find(".//control[@id='532']/focusedlayout/control[@type='group']")
        self.assertTrue(implies(underline.findtext('visible'), 'Control.HasFocus(532)'))
        self.assertTrue(implies(underline.findtext('visible'), '!ListItem.IsParentFolder'))
        # Same cards and row geometry as the info page's row.
        row = self.built.find(".//control[@id='5302']")
        self.assertEqual((row.get('type'), row.findtext('focusposition'), row.findtext('top')), ('fixedlist', '0', '670'))
        self.assertEqual(row.find('itemlayout').get('width'), '344')

    def test_episode_row_follows_the_focused_season(self):
        content = self.row.find('content')
        self.assertEqual(content.text, '$VAR[Bald_SeriesPageEpisodesPath]')
        self.assertEqual((content.get('sortby'), content.get('sortorder')), ('episode', 'ascending'))
        self.assertGreater(int(content.get('limit')), 0)
        values = self.alternates.find("variable[@name='Bald_SeriesPageEpisodesPath']").findall('value')
        self.assertTrue(values)
        for value in values:
            self.assertEqual(value.text, '$INFO[Container(532).ListItem.FolderPath]')
            # Never the parent item's folder, which is the whole show list.
            self.assertTrue(implies(value.get('condition') or 'true', '!Container(532).ListItem.IsParentFolder'))

    def test_navigation_contract(self):
        self.assertEqual(self.tabs.findtext('onup'), '9150')
        self.assertEqual((self.tabs.findtext('onleft'), self.tabs.findtext('onright')), ('noop', 'noop'))
        down = [(n.get('condition') or 'true', n.text) for n in self.built.find(".//control[@id='532']").findall('ondown')]
        self.assertTrue(down)
        for condition, action in down:
            self.assertTrue(action.startswith('SetFocus(5302'), action)
            self.assertTrue(implies(condition, '$EXP[Bald_InfoTVHasEpisodes]'), condition)
        # A new season starts at its first unwatched episode (the watched count) or its first episode.
        self.assertTrue(any('ListItem.Property(WatchedEpisodes)' in a for _, a in down))
        self.assertIn('SetFocus(5302,0,absolute)', [a for _, a in down])
        self.assertEqual(self.row.findtext('onup'), 'SetFocus(532)')
        self.assertEqual([n.text for n in self.row.findall('onback')], ['SetFocus(532)', 'Action(Back)'])
        for key in ('ondown', 'onleft', 'onright'):
            self.assertEqual(self.row.findtext(key), 'noop')
        built_row = self.built.find(".//control[@id='5302']")
        self.assertEqual([n.text for n in built_row.findall('onclick')],
                         ['NotifyAll(skin.bald,bald.play|episode|$INFO[Container(5302).ListItem.DBID])',
                          'RunScript(skin.bald,play,episode,$INFO[Container(5302).ListItem.DBID])'])
        self.assertIn('SetProperty(Bald.Series.RowFor,$ESCINFO[Container(532).ListItem.FolderPath],videos)',
                      [n.text for n in self.row.findall('onfocus')])

    def test_show_header_line_comes_from_the_script(self):
        actions = [(n.get('condition'), n.text) for n in self.tabs.findall('onfocus')]
        self.assertTrue(has_action(actions, '!$EXP[Bald_SeriesPageMetaReady] + !$EXP[Bald_HelperActions]',
                                   'RunScript(skin.bald,seriesmeta)'))
        self.assertTrue(has_action(actions, '!$EXP[Bald_SeriesPageMetaReady] + $EXP[Bald_HelperActions]',
                                   'NotifyAll(skin.bald,bald.seriesmeta)'))
        ready = self.alternates.findtext("expression[@name='Bald_SeriesPageMetaReady']")
        self.assertIn('Window(videos).Property(Bald.Series.For)', ready)
        self.assertIn('Container.FolderPath', ready)
        # The script reads the show from this list, and plays from this window.
        from scripts import info
        self.assertEqual(self.tabs.get('id'), str(info.SERIES_PAGE))
        self.assertIn('Window.IsActive(videos)', info.PLAY_WINDOWS)


if __name__ == '__main__':
    unittest.main()
