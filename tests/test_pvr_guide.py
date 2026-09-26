import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
import importlib.util


ROOT = Path(__file__).resolve().parents[1] / '1080i'
REPO = ROOT.parent


class PVRGuideTests(unittest.TestCase):
    def test_home_live_tv_opens_native_guide(self):
        home = ET.parse(ROOT / 'Home.xml').getroot()
        item = next(node for node in home.findall(".//control[@id='9000']/content/item")
                    if node.findtext("property[@name='id']") == 'livetv')
        self.assertEqual([node.text for node in item.findall('onclick')],
                         ['ActivateWindow(TVGuide)'])
        self.assertEqual(item.findtext('visible'),
                         '!Skin.HasSetting(Bald.Screen.HideLiveTV)')

    def test_primary_guide_preserves_native_contract(self):
        guide = ET.parse(ROOT / 'MyPVRGuide.xml').getroot()
        self.assertEqual(guide.findtext('onload'),
                         'RunScript(special://skin/scripts/pvr_keymap.py,remove)')
        self.assertEqual(guide.findtext('views'), '50')
        self.assertEqual(guide.findtext('menucontrol'), '9000')
        self.assertIsNotNone(guide.find(".//control[@id='11']"))
        self.assertIsNotNone(guide.find(".//control[@id='63']"))
        self.assertIsNotNone(guide.find(".//include[@content='Bald_EpgGrid']"))
        self.assertIsNotNone(guide.find(".//include[.='Bald_PVRGuideTools']"))
        self.assertIsNotNone(guide.find(".//include[.='PVRChannelNumberInput']"))

        includes = ET.parse(ROOT / 'Includes_PVR.xml').getroot()
        grid = includes.find("include[@name='Bald_EpgGrid']/definition/control[@type='epggrid']")
        self.assertEqual(grid.get('id'), '$PARAM[control_id]')
        self.assertEqual(grid.findtext('onleft'), '9000')
        self.assertEqual(grid.findtext('onright'), '50')
        self.assertEqual(grid.findtext('onup'), '50')
        progress = grid.find('progresstexture')
        self.assertEqual(progress.text, 'bald/epg_now.png')
        self.assertEqual(progress.get('border'), '0,0,1,0')
        self.assertEqual(progress.get('colordiffuse'), '809FB0C6')
        self.assertIsNotNone(grid.find('rulerlayout'))
        self.assertIsNotNone(grid.find('channellayout'))
        self.assertIsNotNone(grid.find('focusedchannellayout'))
        self.assertIsNotNone(grid.find('itemlayout'))
        self.assertIsNotNone(grid.find('focusedlayout'))
        self.assertEqual(grid.findtext('top'), '420')
        self.assertEqual(grid.findtext('bottom'), '144')
        ruler_height = int(grid.find('rulerlayout').get('height'))
        row_height = int(grid.find('channellayout').get('height'))
        self.assertEqual(1080 - 420 - 144 - ruler_height, 7 * row_height)

        item = grid.find('itemlayout')
        self.assertFalse(any(node.findtext('texture') == 'bald/white.png'
                             for node in item.findall("control[@type='image']")))

        tools = includes.find("include[@name='Bald_PVRGuideTools']")
        self.assertIsNotNone(tools)
        actions = [node.text for node in tools.findall(".//param[@name='action']")]
        for action in ('PVR.EpgGridControl(CurrentProgramme)',
                       'PVR.EpgGridControl(SelectGroup)',
                       'PVR.EpgGridControl(PreviousGroup)',
                       'PVR.EpgGridControl(NextGroup)',
                       'PVR.EpgGridControl(SelectDate)',
                       'ActivateWindow(TVSearch)'):
            self.assertIn(action, actions)

    def test_retired_guide_left_keymap_cleanup_is_idempotent(self):
        path = REPO / 'scripts' / 'pvr_keymap.py'
        spec = importlib.util.spec_from_file_location('pvr_keymap', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            class XbmcVfs:
                @staticmethod
                def translatePath(_path):
                    return directory

            class Xbmc:
                calls = []

                @classmethod
                def executebuiltin(cls, action):
                    cls.calls.append(action)

            keymap = Path(directory) / 'bald-pvr.xml'
            keymap.write_text('<keymap/>', encoding='utf-8')
            self.assertTrue(module.remove(Xbmc, XbmcVfs))
            self.assertFalse(module.remove(Xbmc, XbmcVfs))
            self.assertEqual(Xbmc.calls, ['Action(reloadkeymaps)'])


if __name__ == '__main__':
    unittest.main()
