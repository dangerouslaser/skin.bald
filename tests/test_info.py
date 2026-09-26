"""Regression checks for the library URL bridge; no Kodi instance required."""
import json
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from scripts.info import recommendation_path, recommendation_subject
from scripts import info


class RecommendationPathTests(unittest.TestCase):
    def decode(self, path):
        url = urlsplit(path)
        query = parse_qs(url.query, strict_parsing=True)
        self.assertEqual(set(query), {"xsp"})
        self.assertEqual(url.fragment, "")
        return url, json.loads(query["xsp"][0])

    def test_special_characters_cannot_split_or_change_the_query(self):
        for title in ['Mr. & Mrs. Smith', 'A "quote", a slash / and a backslash \\',
                      '100% + #1 = café', '映画 & кино', 'literal %26 and %22']:
            with self.subTest(title=title):
                _, playlist = self.decode(recommendation_path('movie', title, ['Action']))
                self.assertEqual(playlist['rules']['and'][1]['value'], [title])

    def test_genres_are_array_entries_not_english_prefixes(self):
        genre = 'Acción & aventura / "Especial"'
        _, playlist = self.decode(recommendation_path('movie', 'Test', [genre, 'Drama']))
        self.assertEqual(playlist['rules']['and'][0]['value'], [genre])

    def test_tv_queries_stay_in_the_tv_library(self):
        url, playlist = self.decode(recommendation_path('tvshow', 'A show', ['Drama']))
        self.assertEqual(url.netloc, 'tvshows')
        self.assertEqual(playlist['type'], 'tvshows')

    def test_missing_genres_and_unsupported_items_do_not_browse_the_whole_library(self):
        self.assertEqual(recommendation_path('movie', 'Test', []), '')
        self.assertEqual(recommendation_path('episode', 'Test', ['Drama']), '')

    def test_episode_recommendations_resolve_to_the_parent_tv_series(self):
        xbmc = Mock()
        xbmc.executeJSONRPC.side_effect = [
            json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {'episodedetails': {'tvshowid': 42}}}),
            json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {'tvshowdetails': {'title': 'Parent show', 'genre': ['Drama']}}}),
        ]
        media_type, details = recommendation_subject(xbmc, 'episode', 7)
        self.assertEqual(media_type, 'tvshow')
        self.assertEqual(details, {'title': 'Parent show', 'genre': ['Drama']})
        first_request = json.loads(xbmc.executeJSONRPC.call_args_list[0].args[0])
        second_request = json.loads(xbmc.executeJSONRPC.call_args_list[1].args[0])
        self.assertEqual(first_request['method'], 'VideoLibrary.GetEpisodeDetails')
        self.assertEqual(first_request['params']['properties'], ['tvshowid'])
        self.assertEqual(second_request['method'], 'VideoLibrary.GetTVShowDetails')

    def test_episode_without_a_valid_parent_fails_closed(self):
        for tvshowid in (None, 0, -1):
            with self.subTest(tvshowid=tvshowid):
                xbmc = Mock()
                details = {} if tvshowid is None else {'tvshowid': tvshowid}
                xbmc.executeJSONRPC.return_value = json.dumps({
                    'jsonrpc': '2.0', 'id': 1,
                    'result': {'episodedetails': details},
                })
                self.assertEqual(recommendation_subject(xbmc, 'episode', 7), ('', {}))
                self.assertEqual(xbmc.executeJSONRPC.call_count, 1)


class InfoLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.properties = {12003: {'Bald.Identity': 'movie:1'}, 10000: {}}
        self.windows = {}
        for window_id, properties in self.properties.items():
            window = Mock()
            window.getProperty.side_effect = lambda key, p=properties: p.get(key, '')
            window.setProperty.side_effect = lambda key, value, p=properties: p.update({key: value})
            window.clearProperty.side_effect = lambda key, p=properties: p.pop(key, None)
            self.windows[window_id] = window
        self.xbmc = Mock()
        self.xbmc.getInfoLabel.return_value = 'image://fanart'
        self.xbmc.getCondVisibility.return_value = True
        self.gui = Mock()
        self.gui.Window.side_effect = self.windows.__getitem__
        self.modules = patch.dict('sys.modules', {'xbmc': self.xbmc, 'xbmcgui': self.gui})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_old_onload_cannot_publish_art_or_recommendations(self):
        info.run('recommendations', 'movie', '2')
        self.windows[12003].setProperty.assert_not_called()
        self.xbmc.executeJSONRPC.assert_not_called()

    def test_superseded_lookup_does_not_publish_a_previous_titles_list(self):
        def lookup(*args):
            self.properties[12003]['Bald.Identity'] = 'movie:2'
            return {'title': 'Old title', 'genre': ['Drama']}
        with patch.object(info, 'get_details', side_effect=lookup):
            info.run('recommendations', 'movie', '1')
        self.assertNotIn('Bald.MorePath', self.properties[12003])

    def test_failed_lookup_releases_handoff_guard_without_closing_dialog(self):
        with patch.object(info, 'get_details', side_effect=RuntimeError('lookup failed')):
            with self.assertRaises(RuntimeError):
                info.run('open', 'movie', '2')
        self.assertNotIn('Bald.InfoSwitch', self.properties[10000])
        self.xbmc.executebuiltin.assert_not_called()

    def test_repeat_selection_does_not_start_a_second_exchange(self):
        self.properties[10000]['Bald.InfoSwitch'] = 'existing exchange'
        info.run('open', 'movie', '2')
        self.xbmc.executeJSONRPC.assert_not_called()
        self.assertEqual(self.properties[10000]['Bald.InfoSwitch'], 'existing exchange')

    def test_episode_publishes_parent_series_recommendations_and_heading(self):
        self.properties[12003]['Bald.Identity'] = 'episode:7'
        with patch.object(info, 'recommendation_subject', return_value=(
                'tvshow', {'title': 'Parent show', 'genre': ['Drama']})):
            info.run('recommendations', 'episode', '7')
        self.assertEqual(self.properties[12003]['Bald.MoreFor'], 'Parent show')
        url, playlist = RecommendationPathTests().decode(self.properties[12003]['Bald.MorePath'])
        self.assertEqual(url.netloc, 'tvshows')
        self.assertEqual(playlist['type'], 'tvshows')

    def test_superseded_episode_lookup_publishes_neither_heading_nor_path(self):
        self.properties[12003]['Bald.Identity'] = 'episode:7'
        def lookup(*args):
            self.properties[12003]['Bald.Identity'] = 'episode:8'
            return 'tvshow', {'title': 'Old parent', 'genre': ['Drama']}
        with patch.object(info, 'recommendation_subject', side_effect=lookup):
            info.run('recommendations', 'episode', '7')
        self.assertNotIn('Bald.MoreFor', self.properties[12003])
        self.assertNotIn('Bald.MorePath', self.properties[12003])


def episode(episodeid, season, number, playcount=0, lastplayed='', position=0, firstaired=''):
    return {'episodeid': episodeid, 'season': season, 'episode': number, 'playcount': playcount,
            'lastplayed': lastplayed, 'resume': {'position': position, 'total': 3000 if position else 0},
            'firstaired': firstaired}


class NextEpisodeTests(unittest.TestCase):
    def test_in_progress_latest_episode_resumes(self):
        episodes = [episode(1, 1, 1, 1, '2026-01-01 10:00:00'), episode(2, 1, 2, 0, '2026-01-02 10:00:00', 600),
                    episode(3, 1, 3)]
        chosen, resume = info.next_episode(episodes)
        self.assertEqual((chosen['episodeid'], resume), (2, True))
        self.assertEqual(info.action_label(chosen, resume), 'Resume S1 E2')

    def test_next_unwatched_after_the_most_recent_episode_plays(self):
        episodes = [episode(3, 2, 1), episode(1, 1, 1, 1, '2026-01-01 10:00:00'),
                    episode(2, 1, 2, 1, '2026-01-03 10:00:00'), episode(4, 2, 2)]
        chosen, resume = info.next_episode(episodes)
        self.assertEqual((chosen['episodeid'], resume), (3, False))
        self.assertEqual(info.action_label(chosen, resume), 'Play S2 E1')

    def test_rewatch_continues_after_the_latest_not_the_earliest_gap(self):
        episodes = [episode(1, 1, 1), episode(2, 1, 2, 1, '2026-01-01 10:00:00'),
                    episode(3, 1, 3, 1, '2026-02-01 10:00:00'), episode(4, 1, 4)]
        self.assertEqual(info.next_episode(episodes)[0]['episodeid'], 4)

    def test_unstarted_and_finished_shows_start_at_the_first_regular_episode(self):
        specials = episode(9, 0, 1)
        self.assertEqual(info.next_episode([episode(2, 1, 2), specials, episode(1, 1, 1)])[0]['episodeid'], 1)
        finished = [episode(1, 1, 1, 1, '2026-01-01 10:00:00'), episode(2, 1, 2, 1, '2026-01-02 10:00:00')]
        self.assertEqual(info.next_episode(finished), (finished[0], False))

    def test_specials_only_and_empty_shows(self):
        self.assertEqual(info.next_episode([episode(9, 0, 1)])[0]['episodeid'], 9)
        self.assertEqual(info.next_episode([]), (None, False))

    def test_header_meta_skips_missing_fields(self):
        episodes = [episode(1, 1, 1, firstaired='2019-04-01'), episode(2, 3, 8, firstaired='2024-11-30'),
                    episode(3, 3, 9, firstaired='')]
        years = info.years_label(2019, episodes)
        self.assertEqual(years, '2019 to 2024')
        self.assertEqual(info.tv_meta(years, 3, 'TV-14'), '2019 to 2024, 3 seasons, TV-14')
        self.assertEqual(info.tv_meta(info.years_label(2020, []), 1, ''), '2020, 1 season')
        self.assertEqual(info.tv_meta('', 0, ''), '')


class FakeKodi:
    """Just enough of xbmc for the season and episode lists: Control.Move changes selection, and moving the
    season tab reloads the episode row with the new season (keeping its index, as Kodi does)."""

    def __init__(self, seasons, episodes_by_season, focus=5003):
        self.lists = {5301: {'items': [{'Season': s} for s in seasons], 'current': 0},
                      5302: {'items': [], 'current': 2}}
        self.episodes = episodes_by_season
        self.focus = focus
        self.visible = True
        self.builtins = []
        self.reload()
        self.Monitor = lambda: Mock(waitForAbort=Mock(return_value=False))

    def reload(self):
        season = self.lists[5301]['items'][self.lists[5301]['current']]['Season']
        rows = self.lists[5302]
        rows['items'] = [{'Season': season, 'DBID': str(dbid)} for dbid in self.episodes.get(season, [])]
        rows['current'] = min(rows['current'], max(len(rows['items']) - 1, 0))

    def getInfoLabel(self, label):
        container = int(label[10:14])
        data = self.lists[container]
        field = label.split(').', 1)[1]
        if field == 'NumItems':
            return str(len(data['items']))
        if field == 'CurrentItem':
            return str(data['current'] + 1)
        index, name = field[len('ListItemAbsolute('):].split(').')
        items = data['items']
        return items[int(index)].get(name, '') if 0 <= int(index) < len(items) else ''

    def getCondVisibility(self, condition):
        if condition == 'Window.IsVisible(movieinformation)':
            return self.visible
        if condition == info.EPISODE_ACTIONS:
            return self.focus in (5001, 5002)
        return False  # Container(...).IsUpdating

    def executebuiltin(self, command, wait=False):
        self.builtins.append(command)
        if command.startswith('Control.Move('):
            container, offset = map(int, command[13:-1].split(','))
            self.lists[container]['current'] += offset
            if container == 5301:
                self.reload()
        elif command == 'SetFocus(5302)':
            self.focus = 5302


class TvRowPositionTests(unittest.TestCase):
    def setUp(self):
        self.window = Mock()
        self.properties = {'Bald.Identity': 'episode:22'}
        self.window.getProperty.side_effect = lambda key: self.properties.get(key, '')
        self.window.setProperty.side_effect = lambda key, value: self.properties.update({key: value})

    def test_episode_opens_its_season_selects_it_and_takes_focus(self):
        kodi = FakeKodi(['', '0', '1', '2'], {'2': [21, 22, 23], '': [11, 21], '0': [1]}, focus=5002)
        self.assertTrue(info.tv_position(kodi, self.window, 'episode:22', 2, 22, True))
        self.assertEqual(kodi.lists[5301]['current'], 3)
        self.assertEqual(kodi.lists[5302]['current'], 1)
        self.assertEqual(self.properties['Bald.TV.RowFor'], '4')
        self.assertEqual(kodi.builtins[-1], 'SetFocus(5302)')

    def test_show_opens_on_the_first_episode_and_leaves_focus_on_the_action(self):
        kodi = FakeKodi(['1', '2'], {'1': [11, 12, 13, 14], '2': [21, 22, 23]}, focus=5003)
        self.properties['Bald.Identity'] = 'tvshow:5'
        self.assertTrue(info.tv_position(kodi, self.window, 'tvshow:5', 1, 0, False))
        # A fresh fixedlist sits on item 3; it is moved back to the first episode.
        self.assertEqual(kodi.lists[5302]['current'], 0)
        self.assertIn('Control.Move(5302,-2)', kodi.builtins)
        self.assertNotIn('SetFocus(5302)', kodi.builtins)

    def test_user_moving_off_the_action_keeps_their_focus(self):
        kodi = FakeKodi(['1'], {'1': [11, 12]}, focus=5004)
        self.assertTrue(info.tv_position(kodi, self.window, 'episode:22', 1, 12, True))
        self.assertNotIn('SetFocus(5302)', kodi.builtins)

    def test_replaced_dialog_and_missing_season_stop_without_moving(self):
        kodi = FakeKodi(['1', '2'], {'1': [11], '2': [21]})
        self.assertFalse(info.tv_position(kodi, self.window, 'episode:99', 2, 21, True))
        self.assertFalse(info.tv_position(kodi, self.window, 'episode:22', 7, 0, True))
        self.assertEqual(kodi.builtins, [])


class TvInfoLifecycleTests(unittest.TestCase):
    setUp = InfoLifecycleTests.setUp

    def rpc_results(self, *results):
        self.xbmc.executeJSONRPC.side_effect = [json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': r}) for r in results]

    def test_episode_publishes_show_header_and_opens_on_itself(self):
        self.properties[12003]['Bald.Identity'] = 'episode:22'
        self.rpc_results(
            {'episodedetails': {'tvshowid': 5, 'season': 2}},
            {'tvshowdetails': {'title': 'Show', 'year': 2019, 'genre': ['Drama', 'Mystery'], 'plot': 'Plot.',
                               'mpaa': 'TV-14', 'season': 2}},
            {'episodes': [episode(21, 2, 1, 1, '2026-01-01 10:00:00', firstaired='2021-01-01'),
                          episode(22, 2, 2, firstaired='2021-01-08')]})
        with patch.object(info, 'tv_position') as position:
            info.run('tvinfo', 'episode', '22')
        published = self.properties[12003]
        self.assertEqual(published['Bald.TV.Meta'], '2019 to 2021, 2 seasons, TV-14')
        self.assertEqual(published['Bald.TV.Genre'], 'Drama / Mystery')
        self.assertEqual((published['Bald.TV.NextLabel'], published['Bald.TV.NextID']), ('Play S2 E2', '22'))
        position.assert_called_once()
        self.assertEqual(position.call_args.args[3:], (2, 22, True))
        methods = [json.loads(c.args[0])['method'] for c in self.xbmc.executeJSONRPC.call_args_list]
        self.assertEqual(methods, ['VideoLibrary.GetEpisodeDetails', 'VideoLibrary.GetTVShowDetails',
                                   'VideoLibrary.GetEpisodes'])

    def test_show_opens_on_the_next_episodes_season(self):
        self.properties[12003]['Bald.Identity'] = 'tvshow:5'
        self.rpc_results(
            {'tvshowdetails': {'title': 'Show', 'year': 2019, 'genre': [], 'plot': '', 'mpaa': '', 'season': 3}},
            {'episodes': [episode(11, 1, 1, 1, '2026-01-01 10:00:00'), episode(31, 3, 1, 0, '2026-02-01 10:00:00', 90)]})
        with patch.object(info, 'tv_position') as position:
            info.run('tvinfo', 'tvshow', '5')
        self.assertEqual(self.properties[12003]['Bald.TV.NextLabel'], 'Resume S3 E1')
        self.assertEqual(position.call_args.args[3:], (3, 0, False))

    def test_superseded_or_invalid_items_publish_nothing(self):
        self.properties[12003]['Bald.Identity'] = 'tvshow:5'
        for args in (('tvinfo', 'tvshow', '6'), ('tvinfo', 'movie', '5'), ('tvinfo', 'tvshow', '0')):
            info.run(*args)
        self.xbmc.executeJSONRPC.assert_not_called()

        def replaced(*args):
            self.properties[12003]['Bald.Identity'] = 'tvshow:6'
            return json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {
                'tvshowdetails': {'title': 'Old'}, 'episodes': []}})
        self.xbmc.executeJSONRPC.side_effect = replaced
        with patch.object(info, 'tv_position') as position:
            info.run('tvinfo', 'tvshow', '5')
        self.assertNotIn('Bald.TV.Title', self.properties[12003])
        position.assert_not_called()

    def test_play_closes_info_then_resumes_through_the_player_api(self):
        visible = iter([True, True, False])
        self.xbmc.getCondVisibility.side_effect = lambda condition: (
            next(visible) if condition == 'Window.IsVisible(movieinformation)' else True)
        self.xbmc.Monitor.return_value.waitForAbort.return_value = False
        self.rpc_results({})
        info.run('play', 'episode', '22')
        self.xbmc.executebuiltin.assert_called_once_with('Dialog.Close(movieinformation)', wait=True)
        request = json.loads(self.xbmc.executeJSONRPC.call_args.args[0])
        self.assertEqual((request['method'], request['params']),
                         ('Player.Open', {'item': {'episodeid': 22}, 'options': {'resume': True}}))

    def test_play_ignores_other_media_and_invalid_ids(self):
        for args in (('play', 'movie', '22'), ('play', 'episode', 'x'), ('play', 'episode', '')):
            info.run(*args)
        self.xbmc.executeJSONRPC.assert_not_called()
        self.xbmc.executebuiltin.assert_not_called()


if __name__ == '__main__':
    unittest.main()
