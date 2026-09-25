import unittest
from unittest.mock import Mock
from scripts.letters import available_letters, bucket, publish


class LetterAvailabilityTests(unittest.TestCase):
    def test_available_and_missing_letters_from_current_results(self):
        letters = ['', '0', 'A', 'A', 'C', 'Z']
        self.assertEqual(available_letters(len(letters), letters.__getitem__), ';0;A;C;Z;')

    def test_empty_results(self):
        self.assertEqual(available_letters(0, Mock()), ';;')

    def test_number_symbol_and_non_latin_bucket(self):
        for letter in ('0', '9', '(', 'é', '日'):
            self.assertEqual(bucket(letter), '0')
        self.assertEqual(bucket('a'), 'A')

    def test_stops_after_all_displayed_groups_found(self):
        values = '0ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        read = Mock(side_effect=values.__getitem__)
        available_letters(5000, read)
        self.assertEqual(read.call_count, 27)

    def test_publish_does_not_replace_results_after_leaving_mode(self):
        xbmc, gui, window = Mock(), Mock(), Mock()
        gui.Window.return_value = window
        props = {}
        window.setProperty.side_effect = props.__setitem__
        window.getProperty.side_effect = lambda key: props.get(key, '')
        xbmc.getInfoLabel.side_effect = lambda key: {
            'Container(510).NumAllItems': '1', 'Container.FolderPath': 'movies',
            'Container(510).ListItemAbsolute(0).SortLetter': 'A',
        }.get(key, '')
        xbmc.getCondVisibility.return_value = False
        publish(xbmc, gui)
        self.assertNotIn('Bald.AvailableLetters', props)
        xbmc.getCondVisibility.side_effect = lambda condition: condition not in ('Control.IsVisible(511)', 'Control.IsVisible(512)')
        publish(xbmc, gui)
        self.assertEqual(props['Bald.AvailableLetters'], ';A;')

    def test_wall_container_is_scanned_when_active(self):
        xbmc, gui, window = Mock(), Mock(), Mock()
        gui.Window.return_value = window
        props = {}
        window.setProperty.side_effect = props.__setitem__
        window.getProperty.side_effect = lambda key: props.get(key, '')
        xbmc.getCondVisibility.side_effect = lambda condition: condition != 'Control.IsVisible(512)'
        xbmc.getInfoLabel.side_effect = lambda key: {
            'Container(511).NumAllItems': '1', 'Container.FolderPath': 'movies',
            'Container(511).ListItemAbsolute(0).SortLetter': 'B',
        }.get(key, '')
        publish(xbmc, gui)
        self.assertEqual(props['Bald.AvailableLetters'], ';B;')

    def test_preview_wall_container_is_scanned_when_active(self):
        xbmc, gui, window = Mock(), Mock(), Mock()
        gui.Window.return_value = window
        props = {}
        window.setProperty.side_effect = props.__setitem__
        window.getProperty.side_effect = lambda key: props.get(key, '')
        xbmc.getCondVisibility.return_value = True
        xbmc.getInfoLabel.side_effect = lambda key: {
            'Container(512).NumAllItems': '1', 'Container.FolderPath': 'movies',
            'Container(512).ListItemAbsolute(0).SortLetter': 'C',
        }.get(key, '')
        publish(xbmc, gui)
        self.assertEqual(props['Bald.AvailableLetters'], ';C;')

    def test_no_scan_outside_bald_views(self):
        xbmc, gui = Mock(), Mock()
        xbmc.getCondVisibility.return_value = False
        publish(xbmc, gui)
        xbmc.getInfoLabel.assert_not_called()
        gui.Window.assert_not_called()
