from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from kodi_includes import expand_call

import home_menu
from conditions import equivalent, implies, same_actions
from kodi_includes import parse


ROOT = Path(__file__).resolve().parents[1] / '1080i'


class SearchUITests(unittest.TestCase):
    def test_home_search_launches_global_search_directly(self):
        item = home_menu.entry(preview='search')
        actions = home_menu.select_actions(item)
        self.assertEqual(actions[0], (None, 'SetProperty(Bald.SearchOrigin,home,home)'))
        self.assertTrue(same_actions(actions[1:], [
            # Bald Helper reads the Live TV schedules while the query is typed (Search's programme matches).
            ('System.AddonIsEnabled(script.globalsearch) + $EXP[Bald_SearchCanLive]',
             'RunPlugin(plugin://script.bald.helper/?action=warm_livetv)'),
            ('System.AddonIsEnabled(script.globalsearch)', 'RunScript(script.globalsearch)'),
            ('System.HasAddon(script.globalsearch) + !System.AddonIsEnabled(script.globalsearch)', 'EnableAddon(script.globalsearch)'),
            ('!System.HasAddon(script.globalsearch)', 'InstallAddon(script.globalsearch)'),
        ]), actions)

    def test_library_search_launches_global_search_scoped_to_content(self):
        root = ET.Element('holder')
        root.extend(expand_call('Bald_LibraryOptions'))
        menu = root.find(".//control[@id='9150']/content")
        searches = [item for item in menu.findall('item')
                    if any(node.text.startswith('RunScript(script.globalsearch') for node in item.findall('onclick'))]
        self.assertTrue(all(item.findtext('label') == '$LOCALIZE[137]' for item in searches))  # Kodi's "Search"
        views = [int(v) for v in ET.parse(ROOT / 'MyVideoNav.xml').getroot().findtext('views').split(',')]

        def shown_for(visible):
            # The views an entry shows for, checked to be exactly an OR of Control.IsVisible over them.
            shown = [str(v) for v in sorted(views) if implies(f'Control.IsVisible({v})', visible)]
            self.assertTrue(equivalent(visible, ' | '.join(f'Control.IsVisible({v})' for v in shown)), visible)
            return shown

        self.assertEqual(
            # Each entry shows for exactly its content level's Bald views.
            [(shown_for(item.findtext('visible')), [node.text for node in item.findall('onclick')]) for item in searches],
            [
                (['510', '511', '512', '513', '514', '515'], ['SetProperty(Bald.SearchOrigin,library,home)', 'RunScript(script.globalsearch,movies=true)']),
                (['520', '521', '522', '523', '530', '531', '532'], ['SetProperty(Bald.SearchOrigin,library,home)', 'RunScript(script.globalsearch,tvshows=true)']),
                (['540', '541', '542'], ['SetProperty(Bald.SearchOrigin,library,home)', 'RunScript(script.globalsearch,episodes=true)']),
            ],
        )

    def test_live_tv_matches_from_bald_helper(self):
        from kodi_includes import Skin
        raw = parse(ROOT / 'script-globalsearch.xml')
        root = Skin().window('script-globalsearch.xml')
        query = '$INFO[Window.Property(GlobalSearch.SearchString)]'
        channels, programmes = root.find(".//control[@id='61']"), root.find(".//control[@id='62']")
        self.assertEqual(channels.findtext('content'), f'plugin://script.bald.helper/?info=livetv_channels&query={query}')
        self.assertEqual(programmes.findtext('content'), f'plugin://script.bald.helper/?info=livetv_programmes&query={query}')
        # Loaded whenever Live TV and the helper are there (Kodi fills only visible lists); faded out unless chosen.
        for node, shown in ((channels, 'Bald_SearchLiveChannels'), (programmes, 'Bald_SearchLiveProgrammes')):
            self.assertEqual(node.findtext('visible'), '$EXP[Bald_SearchCanLive]')
            fade = node.find("animation[@type='Conditional']") or node.find('animation')
            self.assertEqual(fade.get('condition'), f'!$EXP[{shown}]')
            self.assertEqual((node.findtext('onup'), node.findtext('ondown'), node.findtext('onleft')),
                             (node.get('id'), node.get('id'), '990'))
        self.assertIn('?action=play_channel&channelid=$INFO[ListItem.Property(channelid)]', channels.findtext('onclick'))
        # Each list says what shows as it takes focus (the headings and preview follow Bald.SearchLive).
        self.assertIn('SetProperty(Bald.SearchLive,channels)', [n.text for n in channels.findall('onfocus')])
        self.assertIn('SetProperty(Bald.SearchLive,programmes)', [n.text for n in programmes.findall('onfocus')])
        self.assertIn('?action=programme&channelid=', programmes.findtext('onclick'))
        # The results fade out while Live TV shows, but stay visible: Global Search finds its list among the visible
        # views, or it focuses nothing. They take focus back when a category is chosen.
        results = root.find(".//control[@id='50']")
        self.assertIsNone(results.find('visible'))
        fade = results.find("animation[@type='Conditional']") or results.find('animation')
        self.assertEqual(fade.get('condition'), '$EXP[Bald_SearchLiveShown]')
        self.assertIn('ClearProperty(Bald.SearchLive)', [n.text for n in results.findall('onfocus')])
        # The options' Live TV entries, under the categories.
        buttons = raw.findall(".//include[@content='Bald_SearchLiveButton']")
        self.assertEqual([(b.findtext("param[@name='id']"), b.findtext("param[@name='list']"), b.findtext("param[@name='kind']"))
                          for b in buttons], [('9101', '61', 'channels'), ('9102', '62', 'programmes')])
        # One selection at a time: the results' dot shows only while they have focus; a Live TV entry's dot sits
        # beside it (Kodi does not evaluate $MATH, so its position is passed in).
        dot = results.find("focusedlayout/control[@type='image']")
        self.assertEqual(dot.findtext('visible'), 'Control.HasFocus(50)')
        for button in raw.findall(".//include[@content='Bald_SearchLiveButton']"):
            top, dot_top = int(button.findtext("param[@name='top']")), int(button.findtext("param[@name='dot_top']"))
            self.assertEqual(dot_top, top + 24)
        self.assertNotIn('$MATH[', (ROOT / 'Includes_Bald_Common.xml').read_text(encoding='utf-8'))
        no_results = root.find(".//control[@id='999']")
        self.assertEqual(no_results.findtext('visible'), '!$EXP[Bald_SearchLiveShown]')

    def test_live_tv_only_results_open_bald_live_search(self):
        # Global Search asks "Search again?" and closes on anything else when the libraries have nothing; with Live TV
        # matches (Bald Helper counts them on Home), that question offers Live TV, which opens Bald's own window.
        dialog = parse(ROOT / 'DialogConfirm.xml')
        button = next(i for i in dialog.iter('include')
                      if any(p.get('name') == 'id' and p.get('value') == '14' for p in i.findall('param')))
        params = {p.get('name'): p.get('value') for p in button.findall('param')}
        self.assertEqual(params['onclick'], 'RunPlugin(plugin://script.bald.helper/?action=live_search)')
        for part in ('Window.IsVisible(script-globalsearch.xml)', 'String.IsEqual(Control.GetLabel(1),$LOCALIZE[284])',
                     'Integer.IsGreater(Window(home).Property(Bald.SearchLive.Channels),0)'):
            self.assertIn(part, params['visible'])
        search = parse(ROOT / 'script-globalsearch.xml')
        onload = [n.text for n in search.findall('onload')]
        self.assertIn('ClearProperty(Bald.SearchLive.Channels,home)', onload)
        self.assertIn('ClearProperty(Bald.SearchLive.Programmes,home)', onload)
        from kodi_includes import Skin
        window = Skin().window('Custom_1130_BaldLiveSearch.xml')
        channels, programmes = window.find(".//control[@id='61']"), window.find(".//control[@id='62']")
        self.assertIn('query=$INFO[Window(home).Property(Bald.LiveSearch.Query)]', channels.findtext('content'))
        self.assertEqual((channels.findtext('onright'), programmes.findtext('onleft')), ('62', '61'))

    def test_global_search_override_preserves_addon_contract(self):
        root = parse(ROOT / 'script-globalsearch.xml')
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
        # Leaving the options returns to what shows: a Live TV list (61 channels, 62 programmes) or the results.
        self.assertEqual([(node.get('condition'), node.text) for node in menu.findall('onright')],
                         [(None, 'ClearProperty(Bald.SearchMenu)'), ('$EXP[Bald_SearchLiveChannels]', '61'),
                          ('$EXP[Bald_SearchLiveProgrammes]', '62'), ('!$EXP[Bald_SearchLiveShown]', '50')])
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
        self.assertTrue(equivalent(return_action.get('condition'),
                                   'String.IsEqual(Window(home).Property(Bald.SearchOrigin),home)'))
        loading = root.find(".//control[@id='991']")
        self.assertEqual(loading.findtext('left'), '96')
        self.assertEqual(loading.findtext('font'), 'Bald_Section')
        for control_id in ('990', '9000'):
            control = root.find(f".//control[@id='{control_id}']")
            for direction in ('onleft', 'onright'):
                self.assertEqual([node.text for node in control.findall(direction)],
                                 ['ClearProperty(Bald.SearchMenu)', '61', '62', '50'])
        self.assertEqual(root.find(".//control[@id='50']").findtext('onleft'), '990')
        headers = next(group for group in root.findall('.//control[@type="group"]')
                       if group.findtext("control/label") == '$LOCALIZE[369]')  # Kodi's "Title"
        self.assertTrue(equivalent(headers.findtext('visible'), '!Control.IsVisible(991) + !$EXP[Bald_SearchLiveShown]'))

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
