from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1] / '1080i'


class SearchUITests(unittest.TestCase):
    def test_home_search_launches_global_search_directly(self):
        home = ET.parse(ROOT / 'Home.xml').getroot()
        item = next(node for node in home.findall(".//control[@id='9000']/content/item")
                    if node.findtext("property[@name='id']") == 'search')
        actions = [(node.get('condition'), node.text) for node in item.findall('onclick')
                   if node.text != 'SetProperty(Bald.SearchOrigin,home,home)']
        self.assertEqual(actions, [
            ('System.AddonIsEnabled(script.globalsearch)', 'RunScript(script.globalsearch)'),
            ('System.HasAddon(script.globalsearch) + !System.AddonIsEnabled(script.globalsearch)', 'EnableAddon(script.globalsearch)'),
            ('!System.HasAddon(script.globalsearch)', 'InstallAddon(script.globalsearch)'),
        ])

    def test_library_search_launches_global_search_scoped_to_content(self):
        root = ET.parse(ROOT / 'View_510_Bald_Posters.xml').getroot()
        menu = root.find("include[@name='Bald_LibraryOptions']//control[@id='9150']/content")
        searches = [item for item in menu.findall('item') if item.findtext('label') == 'Search']
        self.assertEqual(
            [(item.findtext('visible'), [node.text for node in item.findall('onclick')]) for item in searches],
            [
                ('Control.IsVisible(510) | Control.IsVisible(511) | Control.IsVisible(512) | Control.IsVisible(513) | Control.IsVisible(514) | Control.IsVisible(515)', ['SetProperty(Bald.SearchOrigin,library,home)', 'RunScript(script.globalsearch,movies=true)']),
                ('Control.IsVisible(520) | Control.IsVisible(521) | Control.IsVisible(522) | Control.IsVisible(523) | Control.IsVisible(530) | Control.IsVisible(531)', ['SetProperty(Bald.SearchOrigin,library,home)', 'RunScript(script.globalsearch,tvshows=true)']),
                ('Control.IsVisible(540) | Control.IsVisible(541) | Control.IsVisible(542)', ['SetProperty(Bald.SearchOrigin,library,home)', 'RunScript(script.globalsearch,episodes=true)']),
            ],
        )

    def test_global_search_override_preserves_addon_contract(self):
        root = ET.parse(ROOT / 'script-globalsearch.xml').getroot()
        self.assertEqual(root.findtext('views'), '50')
        for control_id in ('50', '990', '991', '999', '9000'):
            self.assertIsNotNone(root.find(f".//control[@id='{control_id}']"), control_id)
        menu = root.find(".//control[@id='9000']")
        self.assertEqual((menu.findtext('left'), menu.findtext('top'), menu.findtext('width')),
                         ('1440', '454', '420'))
        new_search = root.find(".//control[@id='990']")
        self.assertEqual((new_search.findtext('left'), new_search.findtext('top'), new_search.findtext('width')),
                         ('1440', '392', '420'))
        self.assertEqual(menu.findtext('scrolltime'), '0')
        self.assertEqual([node.text for node in menu.findall('onright')],
                         ['ClearProperty(Bald.SearchMenu)', '50'])
        xml = ET.tostring(root, encoding='unicode')
        self.assertNotIn('globalsearch-', xml)
        self.assertIn('Window.Property(TMDbHelper.ListItem.BlurImage)', xml)
        self.assertIn('$INFO[Container(50).ListItem.Label]', xml)
        self.assertIn('Skin.SetBool(TMDbHelper.UseLocalWidgetContainer)',
                      [node.text for node in root.findall('onload')])
        self.assertIn('SetProperty(TMDbHelper.WidgetContainer,50)',
                      [node.text for node in root.findall('onload')])
        self.assertNotIn('Skin.Reset(TMDbHelper.UseLocalWidgetContainer)',
                         [node.text for node in root.findall('onunload')])
        return_action = next(node for node in root.findall('onunload')
                             if node.text == 'SetProperty(Bald.ReturnSearch,true,home)')
        self.assertEqual(return_action.get('condition'),
                         'String.IsEqual(Window(home).Property(Bald.SearchOrigin),home)')
        loading = root.find(".//control[@id='991']")
        self.assertEqual(loading.findtext('left'), '96')
        self.assertEqual(loading.findtext('font'), 'Bald_Section')
        for control_id in ('990', '9000'):
            control = root.find(f".//control[@id='{control_id}']")
            for direction in ('onleft', 'onright'):
                self.assertEqual([node.text for node in control.findall(direction)],
                                 ['ClearProperty(Bald.SearchMenu)', '50'])
        self.assertEqual(root.find(".//control[@id='50']").findtext('onleft'), '990')
        headers = next(group for group in root.findall('.//control[@type="group"]')
                       if group.findtext("control/label") == 'Title')
        self.assertEqual(headers.findtext('visible'), '!Control.IsVisible(991)')

    def test_keyboard_preserves_contract_ids_with_bald_character_style(self):
        keyboard = ET.parse(ROOT / 'DialogKeyboard.xml').getroot()
        for control_id in ('8', '32', '100', '302', '303', '304', '305', '306', '312'):
            self.assertIsNotNone(keyboard.find(f".//control[@id='{control_id}']"), control_id)
        generated_ids = {node.get('value') for node in keyboard.findall(".//param[@name='id']")}
        self.assertTrue({'300', '301'}.issubset(generated_ids))
        buttons = ET.parse(ROOT / 'Includes_Buttons.xml').getroot()
        style = buttons.find("include[@name='Bald_KeyboardButton']")
        self.assertEqual(style.findtext('font'), 'Bald_KeyboardKey')
        self.assertEqual(style.findtext('textcolor'), 'bald_ink')
        self.assertEqual(style.findtext('focusedcolor'), 'bald_field')
        self.assertEqual(style.findtext('texturefocus'), 'buttons/roundbutton-fo.png')
        self.assertEqual(style.findtext('texturenofocus'), '')
        used_styles = {node.text for node in keyboard.findall('.//include')}
        self.assertIn('Bald_KeyboardButton', used_styles)
        self.assertNotIn('KeyboardButton', used_styles)


if __name__ == '__main__':
    unittest.main()
