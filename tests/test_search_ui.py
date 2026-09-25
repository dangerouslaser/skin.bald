from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1] / '1080i'


class SearchUITests(unittest.TestCase):
    def test_home_search_opens_the_bald_chooser(self):
        home = ET.parse(ROOT / 'Home.xml').getroot()
        item = next(node for node in home.findall(".//control[@id='9000']/content/item")
                    if node.findtext("property[@name='id']") == 'search')
        self.assertEqual([node.text for node in item.findall('onclick')],
                         ['ClearProperty(Bald.Menu,home)', 'ActivateWindow(1107)'])

    def test_search_chooser_reuses_home_menu_geometry_and_rows(self):
        root = ET.parse(ROOT / 'Custom_1107_SearchDialog.xml').getroot()
        menu = root.find(".//control[@id='9000']")
        self.assertEqual((menu.findtext('left'), menu.findtext('top'), menu.findtext('width')),
                         ('1440', '392', '420'))
        self.assertEqual(int(menu.findtext('height')), 3 * int(menu.find('itemlayout').get('height')))
        self.assertEqual(menu.findtext('itemlayout/include'), 'Bald_MenuRowUnfocused')
        self.assertEqual(menu.find('focusedlayout/include').get('content'), 'Bald_MenuRowFocused')
        self.assertEqual([item.findtext('label') for item in menu.findall('content/item')],
                         ['Library', 'Add-ons', 'YouTube'])
        self.assertIsNotNone(root.find(".//include[@content='Bald_MenuNote']"))
        self.assertEqual(menu.findtext('onback'), 'Dialog.Close(1107)')

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
