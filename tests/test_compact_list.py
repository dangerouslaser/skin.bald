from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1] / '1080i'


class CompactListTests(unittest.TestCase):
    def test_native_list_has_thirteen_rows_and_shared_preview(self):
        root = ET.parse(ROOT / 'View_513_Bald_CompactList.xml').getroot()
        control = root.find(".//control[@id='513']")
        self.assertEqual(control.get('type'), 'list')
        self.assertIsNone(control.find('content'))
        self.assertEqual(control.findtext('visible'), 'Container.Content(movies)')
        self.assertEqual(int(control.findtext('height')), 13 * int(control.find('itemlayout').get('height')))
        self.assertEqual(control.findtext('onleft'), '9150')
        self.assertEqual([n.text for n in control.findall('onright')], ['SetFocus(9160)', 'RunScript(skin.bald,letters,513)'])
        self.assertEqual(root.findtext(".//include[@content='Bald_LibraryPreview']/param[@name='c']"), '513')
        nav = ET.parse(ROOT / 'MyVideoNav.xml').getroot()
        self.assertIn('513', nav.findtext('views').split(','))
        self.assertIn('View_513_Bald_CompactList', [n.text for n in nav.iter('include')])

    def test_status_prioritizes_resume_and_columns_fit(self):
        root = ET.parse(ROOT / 'Includes_Bald_LibraryList.xml').getroot()
        values = root.findall("variable[@name='Bald_ListWatchState']/value")
        self.assertEqual(values[0].get('condition'), 'ListItem.IsResumable')
        self.assertEqual(values[0].text, '$LOCALIZE[13404]')  # Kodi's "Resume"
        self.assertEqual(values[1].text, '$LOCALIZE[16102]')  # Kodi's "Watched"
        self.assertFalse(values[2].text)
        for label in root.findall("include/definition/control"):
            self.assertLessEqual(int(label.findtext('left')) + int(label.findtext('width')), 1140)
