"""Layout contracts for the native movie-library view."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1] / "1080i"


class LibraryViewTests(unittest.TestCase):
    def setUp(self):
        self.view = ET.parse(ROOT / "View_510_Bald_Posters.xml").getroot()

    def test_registered_native_movie_only_view_with_three_slots(self):
        nav = ET.parse(ROOT / "MyVideoNav.xml").getroot()
        self.assertIn("510", nav.findtext("views").split(","))
        self.assertIn("View_510_Bald_Posters", [n.text for n in nav.iter("include")])
        includes = ET.parse(ROOT / "Includes.xml").getroot()
        self.assertIn("View_510_Bald_Posters.xml", [n.get("file") for n in includes])
        control = self.view.find(".//control[@id='510']")
        self.assertEqual(control.findtext("visible"), "Container.Content(movies)")
        self.assertIsNone(control.find("content"))
        self.assertEqual(int(control.findtext("width")), 3 * int(control.find("itemlayout").get("width")))
        self.assertEqual(control.findtext("onup"), "9150")
        self.assertEqual([n.text for n in control.findall('ondown')], ['SetFocus(9160)', 'RunScript(skin.bald,letters,510)'])

    def test_caption_reuses_home_media_flags_and_motion(self):
        caption = self.view.find("include[@name='Bald_LibraryCaption']//include")
        self.assertEqual(caption.get("content"), "Bald_Caption")
        self.assertEqual(caption.findtext("param[@name='c']"), "$PARAM[c]")
        self.assertEqual(self.view.findtext("include[@name='Bald_LibraryCaption']/param[@name='c']"), "510")
        self.assertEqual(caption.findtext("param[@name='width']"), "528")
        shared = ET.parse(ROOT / "Includes_Bald_Home.xml").getroot()
        home_caption = shared.find("include[@name='Bald_Caption']")
        self.assertIsNotNone(home_caption.find(".//include[@content='Bald_MediaFlagItems']"))
        self.assertEqual(len(shared.findall("include[@name='Bald_MediaFlagItems']//include[@content='Bald_Flag']")), 9)
        self.assertEqual(home_caption.findtext("param[@name='width']"), "384")
        self.assertEqual(home_caption.findtext("param[@name='x']"), "1420")

    def test_art_reuses_transition_with_four_overflow_masks(self):
        art = self.view.find("include[@name='Bald_LibraryArt']//include")
        self.assertEqual(art.get("content"), "Bald_ArtLayer")
        self.assertEqual(art.findtext("param[@name='width']"), "528")
        self.assertEqual(art.findtext("param[@name='height']"), "297")
        masks = self.view.findall(".//include[@content='Bald_BackdropWindow']")
        bounds = [tuple(int(n.findtext(f"param[@name='{key}']")) for key in ("x", "y", "w", "h")) for n in masks]
        self.assertEqual(bounds, [(1264, 198, 32, 345), (1824, 198, 32, 345), (1296, 198, 528, 24), (1296, 519, 528, 24)])

    def test_no_redundant_details_button(self):
        self.assertIsNone(self.view.find(".//control[@id='6101']"))
        home = ET.parse(ROOT / "Home.xml").getroot()
        item = next(item for item in home.findall(".//control[@id='9000']/include") if item.findtext("param[@name='label']") == "Movies")
        self.assertEqual(item.findtext("param[@name='visible']"), "Skin.HasSetting(Bald.Screen.Movies)")
        self.assertIn(
            "SetFocus($INFO[Window(home).Property(Bald.Row.movies)])",
            [item.findtext("param[@name='enter4']")],
        )

    def test_frame_masks_are_outside_preview_menu_animations(self):
        root = self.view.find("include[@name='Bald_LibraryPreview']/definition")
        self.assertEqual(len(root.findall("include[@content='Bald_BackdropWindow']")), 4)
        preview = next(n for n in root.findall('control') if 'ListItem.IsParentFolder' in (n.findtext('visible') or ''))
        self.assertFalse(preview.findall(".//include[@content='Bald_BackdropWindow']"))
        self.assertFalse(preview.findall("animation/effect[@type='slide']"))
        self.assertEqual(preview.find("animation[@type='Hidden']/effect").get('time'), '180')

    def test_posters_crop_to_fill_the_frame_in_both_focus_states(self):
        item = self.view.find("include[@name='Bald_LibraryPosterItem']")
        poster = next(n for n in item.iter('control') if n.findtext('texture') == '$VAR[Bald_LibraryPoster]')
        self.assertEqual(poster.findtext('aspectratio'), 'scale')
        self.assertEqual((poster.findtext('width'), poster.findtext('height')), ('$PARAM[width]', '$PARAM[height]'))
        self.assertEqual((item.findtext("param[@name='width']"), item.findtext("param[@name='height']")), ('360', '540'))
        container = self.view.find(".//control[@id='510']")
        self.assertEqual(container.findtext('itemlayout/include'), 'Bald_LibraryPosterItem')
        self.assertEqual(container.find('focusedlayout/include').get('content'), 'Bald_LibraryPosterItem')

    def test_footer_reuses_detail_view_hint_spacing(self):
        hint = self.view.find(".//include[@content='Bald_InfoHintPair']")
        self.assertEqual(hint.findtext("param[@name='width']"), "1024")
        self.assertEqual(hint.findtext("param[@name='third_visible']"), "true")

    def test_audio_codec_flag_maps_names_and_hides_missing_data(self):
        shared = ET.parse(ROOT / "Includes_Bald_Home.xml").getroot()
        caption = shared.find("include[@name='Bald_Caption']")
        codec = next(n for n in shared.findall("include[@name='Bald_MediaFlagItems']//include[@content='Bald_Flag']") if "$MAP[" in n.findtext("param[@name='label']"))
        self.assertEqual(codec.findtext("param[@name='label']"), "$MAP[DefaultCodecMap, Container($PARAM[c]).ListItem.AudioCodec]")
        self.assertEqual(codec.findtext("param[@name='visible']"), "!String.IsEmpty(Container($PARAM[c]).ListItem.AudioCodec)")
        group = next(n for n in caption.iter("control") if n.find("include[@content='Bald_MediaFlagItems']") is not None)
        self.assertIn("!String.IsEmpty(Container($PARAM[c]).ListItem.AudioCodec)", group.findtext("visible"))

    def test_options_have_five_rows_native_actions_and_return_routes(self):
        menu = self.view.find(".//control[@id='9150']")
        self.assertEqual((menu.findtext('left'), menu.findtext('top'), menu.findtext('width')), ('1440', '392', '420'))
        self.assertEqual(int(menu.findtext('height')), 5 * int(menu.find('itemlayout').get('height')))
        self.assertEqual(menu.findtext('scrolltime'), '0')
        for direction in ('onup', 'ondown', 'onright'):
            self.assertEqual(menu.findtext(direction), 'noop')
        for direction in ('onleft', 'onback'):
            self.assertEqual(menu.findtext(direction), '50')
        actions = [n.text for n in menu.iter('onclick')]
        for action in ('SendClick(3)', 'SendClick(4)', 'SendClick(10)', 'Filter',
                       'RunScript(script.globalsearch,movies=true)',
                       'RunScript(script.globalsearch,tvshows=true)',
                       'RunScript(script.globalsearch,episodes=true)'):
            self.assertIn(action, actions)
        self.assertNotIn('Container.NextViewMode', actions)
        movie_view_actions = [
            item.find('onclick').text for item in menu.findall('content/item')
            if (item.findtext('visible') or '') in {f'Control.IsVisible({view})' for view in (510, 511, 512, 513, 514, 515)}
            and (item.findtext('onclick') or '').startswith('Container.SetViewMode')
        ]
        self.assertEqual(movie_view_actions, [f'Container.SetViewMode({view})' for view in (511, 512, 513, 514, 515, 510)])
        view_items = [item for item in menu.findall('content/item') if item.findtext('label') == 'View']
        self.assertEqual(len(view_items), 15)
        self.assertTrue(all(item.findall('onclick')[1].text == 'SetFocus(9150)' for item in view_items))
        self.assertIsNotNone(self.view.find("include[@name='Bald_LibraryOptions']//include[@content='Bald_MenuNote']"))
        self.assertEqual(menu.findtext('itemlayout/include'), 'Bald_MenuRowUnfocused')
        self.assertEqual(menu.findtext('focusedlayout/include'), '')
        focused = menu.find("focusedlayout/include[@content='Bald_MenuRowFocused']")
        self.assertEqual(focused.findtext("param[@name='always_dot']"), 'true')
        footer = self.view.find("include[@name='View_510_Bald_Posters']//control[visible='$EXP[Bald_LibraryMenuOpen]']")
        self.assertEqual((footer.findtext('left'), footer.findtext("include/param[@name='width']")), ('1404', '420'))

    def test_home_and_library_share_menu_row_components(self):
        library = self.view.find(".//control[@id='9150']")
        self.assertEqual(library.find('focusedlayout/include').get('content'), 'Bald_MenuRowFocused')
        includes = ET.parse(ROOT / 'Includes_Bald_Home.xml').getroot()
        shared = includes.find("include[@name='Bald_MenuRowFocused']")
        self.assertEqual(shared.findtext(".//control[@type='image']/visible"), '$PARAM[always_dot]')
        home_button = includes.find("include[@name='Bald_HomeMenuButton']")
        self.assertEqual(home_button.findtext(".//texturefocus"), 'bald/menu_dot.png')

    def test_movie_entry_rejects_legacy_estuary_view_modes(self):
        nav = ET.parse(ROOT / 'MyVideoNav.xml').getroot()
        action = next(node for node in nav.findall('onload') if node.text == 'Container.SetViewMode(510)')
        self.assertIn('Container.Content(movies)', action.get('condition'))
        for view in range(510, 516):
            self.assertIn(f'!Control.IsVisible({view})', action.get('condition'))

    def test_letter_mode_uses_native_jumps_and_restores_its_focus(self):
        mode = self.view.find(".//control[@id='9160']")
        for direction, action in [('onleft', 'PrevLetter'), ('onright', 'NextLetter')]:
            actions = mode.findall(direction)
            self.assertEqual([n.text for n in actions], ['SetFocus(50)', f'Action({action})', 'SetFocus(9160)'])
            self.assertTrue(all(n.get('condition') == '$EXP[Bald_LibraryTitleSorted]' for n in actions[:2]))
        for direction in ('onup', 'onback'):
            self.assertEqual(mode.findtext(direction), '50')
        self.assertEqual(mode.findtext('onclick'), 'SetFocus(50)')
        self.assertEqual(mode.findtext('ondown'), 'noop')
        self.assertEqual(mode.findtext('onfocus'), 'SetProperty(TMDbHelper.WidgetContainer,$INFO[Window(videos).Property(Bald.LibraryContainer)],videos)')
        self.assertEqual(self.view.findtext("expression[@name='Bald_LibraryTitleSorted']"), 'String.IsEqual(Container.SortMethod,$LOCALIZE[556])')

    def test_full_alphabet_fits_beneath_posters(self):
        cells = self.view.findall("include[@name='Bald_LibraryLetters']//include[@content='Bald_LibraryLetterCell']")
        self.assertEqual([n.findtext("param[@name='letter']") for n in cells], list('0ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
        self.assertEqual(cells[0].findtext("param[@name='label']"), '0–9')
        end = max(int(n.findtext("param[@name='x']")) + int(n.findtext("param[@name='width']")) for n in cells)
        self.assertLessEqual(end, 1140)
        cell = self.view.find("include[@name='Bald_LibraryLetterCell']")
        self.assertTrue(any('Bald.AvailableLetters' in (n.text or '') for n in cell.iter('visible')))
        self.assertIn('bald/dot.png', [n.text for n in cell.iter('texture')])
