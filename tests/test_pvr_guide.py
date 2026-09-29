import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import home_menu
from conditions import equivalent
from kodi_includes import Skin


ROOT = Path(__file__).resolve().parents[1] / '1080i'
REPO = ROOT.parent


class PVRGuideTests(unittest.TestCase):
    def test_home_live_tv_opens_native_guide(self):
        item = home_menu.entry(preview='livetv')
        # Without Live TV rows (or a PVR add-on) Select opens the guide; Right always does (bridge 9029).
        # (With Appearance > Behavior "Select on a hub opens its library" on, Select opens it with rows too.)
        from conditions import has_action
        self.assertTrue(has_action(home_menu.select_actions(item), '!$EXP[Bald_LiveTVRows]', 'ActivateWindow(TVGuide)',
                                   home_menu.setting(False)))
        self.assertTrue(equivalent(item.findtext("visible"), '!Skin.HasSetting(Bald.Screen.HideLiveTV)'))

    def test_primary_guide_preserves_native_contract(self):
        guide = ET.parse(ROOT / 'MyPVRGuide.xml').getroot()
        # Bald Helper removes the retired Left keymap when it starts; the guide runs no script on open.
        self.assertFalse(any('pvr_keymap' in (node.text or '') for node in guide.iter('onload')))
        self.assertEqual(guide.findtext('views'), '50')
        self.assertEqual(guide.findtext('menucontrol'), '9000')
        self.assertIsNotNone(guide.find(".//control[@id='11']"))
        self.assertIsNotNone(guide.find(".//control[@id='63']"))
        self.assertIsNotNone(guide.find(".//include[@content='Bald_EpgGrid']"))
        self.assertIsNotNone(guide.find(".//include[.='Bald_PVRGuideTools']"))
        # Direct channel number entry, drawn as the Live TV windows draw it.
        number = [node for node in Skin().window('MyPVRGuide.xml').iter('control')
                  if node.get('type') == 'label' and 'PVR.ChannelNumberInput' in (node.findtext('label') or '')]
        self.assertEqual([node.findtext('font') for node in number], ['Bald_Clock'])

        includes = ET.parse(ROOT / 'Includes_PVR.xml').getroot()
        # The grid as the guide window resolves it: one epggrid, the window's control 50.
        grid, = [node for node in Skin().window('MyPVRGuide.xml').iter('control') if node.get('type') == 'epggrid']
        self.assertEqual(grid.get('id'), '50')
        self.assertEqual(grid.findtext('onleft'), '9000')
        self.assertEqual(grid.findtext('onright'), '50')
        self.assertEqual(grid.findtext('onup'), '50')
        self.assertEqual(grid.findtext('onback'), '9000')
        self.assertEqual(grid.findtext('scrolltime'), '200')
        progress = grid.find('progresstexture')
        self.assertEqual(progress.text, 'bald/epg_now.png')
        self.assertEqual(progress.get('border'), '0,0,1,0')
        self.assertEqual(progress.get('colordiffuse'), 'bald_accent50')
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
        for action in ('SetFocus(50)',
                       'PVR.EpgGridControl(CurrentProgramme)',
                       'PVR.EpgGridControl(SelectGroup)',
                       'PVR.EpgGridControl(SelectDate)',
                       'PreviousMenu'):
            self.assertIn(action, actions)
        # The other Live TV windows (timers, recordings, ...), TV or radio as the guide is.
        areas = [node.text for node in tools.findall(".//include[@content='Bald_PVRGuideAreaButton']/param[@name='area']")]
        self.assertEqual(areas, ['Channels', 'Recordings', 'Timers', 'TimerRules', 'Search'])
        area = includes.find("include[@name='Bald_PVRGuideAreaButton']")
        clicks = [node.text for node in area.iter('onclick')]
        self.assertEqual(clicks, ['ActivateWindow(TV$PARAM[area])', 'ActivateWindow(Radio$PARAM[area])'])
        self.assertNotIn('PVR.EpgGridControl(PreviousGroup)', actions)
        self.assertNotIn('PVR.EpgGridControl(NextGroup)', actions)

    def test_retired_script_is_gone(self):
        self.assertFalse((REPO / 'scripts' / 'pvr_keymap.py').exists())


if __name__ == '__main__':
    unittest.main()
