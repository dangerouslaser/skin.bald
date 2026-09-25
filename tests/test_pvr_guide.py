import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / '1080i'


class PVRGuideTests(unittest.TestCase):
    def test_home_live_tv_opens_native_guide(self):
        home = ET.parse(ROOT / 'Home.xml').getroot()
        item = next(node for node in home.findall(".//control[@id='9000']/content/item")
                    if node.findtext("property[@name='id']") == 'livetv')
        self.assertEqual([node.text for node in item.findall('onclick')],
                         ['ActivateWindow(TVGuide)'])

    def test_primary_guide_preserves_native_contract(self):
        guide = ET.parse(ROOT / 'MyPVRGuide.xml').getroot()
        self.assertEqual(guide.findtext('views'), '50')
        self.assertEqual(guide.findtext('menucontrol'), '9000')
        self.assertIsNotNone(guide.find(".//control[@id='11']"))
        self.assertIsNotNone(guide.find(".//control[@id='63']"))
        self.assertIsNotNone(guide.find(".//include[@content='Bald_EpgGrid']"))
        self.assertIsNotNone(guide.find(".//include[@content='PVRSideBar']"))
        self.assertIsNotNone(guide.find(".//include[.='PVRChannelNumberInput']"))

        includes = ET.parse(ROOT / 'Includes_PVR.xml').getroot()
        grid = includes.find("include[@name='Bald_EpgGrid']/definition/control[@type='epggrid']")
        self.assertEqual(grid.get('id'), '$PARAM[control_id]')
        self.assertEqual(grid.findtext('onleft'), '9000')
        self.assertEqual(grid.findtext('onup'), '11')
        progress = grid.find('progresstexture')
        self.assertEqual(progress.text, 'windows/pvr/epg_progress_vertical.png')
        self.assertEqual(progress.get('border'), '0,60,18,14')
        self.assertIsNotNone(grid.find('rulerlayout'))
        self.assertIsNotNone(grid.find('channellayout'))
        self.assertIsNotNone(grid.find('focusedchannellayout'))
        self.assertIsNotNone(grid.find('itemlayout'))
        self.assertIsNotNone(grid.find('focusedlayout'))


if __name__ == '__main__':
    unittest.main()
