"""Regression checks for the library URL bridge; no Kodi instance required."""
import json
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from scripts.info import recommendation_path
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


if __name__ == '__main__':
    unittest.main()
