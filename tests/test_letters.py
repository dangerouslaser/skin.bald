from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET
from scripts.letters import available_letters, bucket, publish, view_container

ROOT = Path(__file__).resolve().parents[1] / '1080i'
LETTERS = 'RunScript(skin.bald,letters'


def fake_kodi(container, letter, visible=True, folder='movies'):
    """Mocks for one view: its container holds one item sorted under `letter`."""
    xbmc, gui, window = Mock(), Mock(), Mock()
    gui.Window.return_value = window
    props = {}
    window.setProperty.side_effect = props.__setitem__
    window.getProperty.side_effect = lambda key: props.get(key, '')
    xbmc.getCondVisibility.side_effect = lambda condition: visible and (
        condition == f'Control.IsVisible({container})' or condition.startswith('Window.IsActive'))
    xbmc.getInfoLabel.side_effect = lambda key: {
        f'Container({container}).NumAllItems': '1', 'Container.FolderPath': folder,
        f'Container({container}).ListItemAbsolute(0).SortLetter': letter,
    }.get(key, '')
    return xbmc, gui, props


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
        xbmc, gui, props = fake_kodi(510, 'A', visible=False)
        publish(xbmc, gui, '510')
        self.assertNotIn('Bald.AvailableLetters', props)
        xbmc, gui, props = fake_kodi(510, 'A')
        publish(xbmc, gui, '510')
        self.assertEqual(props['Bald.AvailableLetters'], ';A;')

    def test_passed_view_container_is_scanned(self):
        for container in (510, 511, 512, 513, 514, 515, 520, 521, 522, 523):
            with self.subTest(container=container):
                xbmc, gui, props = fake_kodi(container, 'G')
                publish(xbmc, gui, str(container))
                self.assertEqual(props['Bald.AvailableLetters'], ';G;')

    def test_only_the_passed_container_is_read(self):
        # 511 is visible but the call site named 510: nothing is scanned.
        xbmc, gui, props = fake_kodi(511, 'B')
        publish(xbmc, gui, '510')
        xbmc.getInfoLabel.assert_not_called()
        gui.Window.assert_not_called()

    def test_invalid_container_argument_does_nothing(self):
        for value in ('', None, 'abc', '510)', '-510', '50', '9160', '5100', '51 0'):
            with self.subTest(value=value):
                xbmc, gui, _ = fake_kodi(510, 'A')
                publish(xbmc, gui, value)
                xbmc.getCondVisibility.assert_not_called()
                xbmc.getInfoLabel.assert_not_called()
                gui.Window.assert_not_called()

    def test_view_container_accepts_only_view_range(self):
        self.assertEqual(view_container('523'), 523)
        self.assertEqual(view_container(' 510 '), 510)
        self.assertIsNone(view_container('499'))
        self.assertIsNone(view_container('600'))

    def test_no_scan_when_container_is_hidden(self):
        xbmc, gui, _ = fake_kodi(510, 'A', visible=False)
        publish(xbmc, gui, '510')
        xbmc.getInfoLabel.assert_not_called()
        gui.Window.assert_not_called()


class LetterDispatchTests(unittest.TestCase):
    def test_info_script_forwards_the_container_argument(self):
        from scripts import info
        xbmc, gui, letters = Mock(), Mock(), Mock()
        with patch.dict('sys.modules', {'xbmc': xbmc, 'xbmcgui': gui, 'letters': letters}):
            info.run('letters', '521')
        letters.publish.assert_called_once_with(xbmc, gui, '521')


class LetterCallSiteTests(unittest.TestCase):
    def test_every_call_site_passes_its_own_container(self):
        sites = []
        for path in sorted(ROOT.glob('View_5*.xml')):
            for control in ET.parse(path).getroot().iter('control'):
                for action in control:
                    text = (action.text or '').strip()
                    if text.startswith(LETTERS):
                        sites.append((path.name, control.get('id'), text))
        self.assertTrue(sites)
        for name, control_id, text in sites:
            with self.subTest(file=name, control=control_id):
                self.assertIsNotNone(view_container(control_id))
                self.assertEqual(text, f'{LETTERS},{control_id})')

    def test_every_letters_view_calls_the_script(self):
        called = {int(site.get('id')) for path in ROOT.glob('View_5*.xml')
                  for site in ET.parse(path).getroot().iter('control')
                  if any((a.text or '').startswith(LETTERS) for a in site)}
        self.assertEqual(called, {510, 511, 512, 513, 514, 515, 520, 521, 522, 523})


if __name__ == '__main__':
    unittest.main()
