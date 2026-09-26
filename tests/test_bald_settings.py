import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import home_menu
from conditions import atoms, equivalent, has_action, implies, same_actions
from kodi_includes import expand, resolve_window
from skin_strings import loc


ROOT = Path(__file__).resolve().parents[1]


def home_menu_button(root, preview):
    """A main-menu entry by its preview screen, which stays fixed while its label is localized."""
    return next(
        include for include in root.findall(".//control[@id='9000']/include[@content='Bald_HomeMenuButton']")
        if include.findtext("param[@name='preview']") == preview
    )


class BaldSettingsTests(unittest.TestCase):
    def test_settings_has_dedicated_bald_tile(self):
        root = ET.parse(ROOT / "1080i" / "Settings.xml").getroot()
        item = next(i for i in root.findall(".//item") if i.findtext("onclick") == "ActivateWindow(1115)")
        self.assertEqual(item.findtext("label"), loc("Bald Settings"))

    def test_bald_settings_exposes_home_and_platform_settings(self):
        root = resolve_window("Custom_1115_BaldSettings.xml")
        actions = [node.text for node in root.findall(".//onclick")]
        self.assertIn("ActivateWindow(1117)", actions)
        self.assertIn("ActivateWindow(1118)", actions)
        self.assertIn("RunAddon(service.coreelec.settings)", actions)
        self.assertIn("RunAddon(service.libreelec.settings)", actions)

    def test_widget_editor_reads_live_homewidget_node_and_rebuilds(self):
        root = ET.parse(ROOT / "1080i" / "Custom_1116_BaldHomeWidgets.xml").getroot()
        content = root.find(".//control[@id='9100']/content").text
        self.assertIn("info=get_shortcuts_node", content)
        self.assertIn("Bald.ConfigureNode", content)
        self.assertIn("skin=skin.bald", content)
        # Closing the editor stamps the rows; Home rebuilds when the stamp it passes to Skin Variables changes.
        stamp = root.findtext("onunload")
        self.assertTrue(stamp.startswith("Skin.SetString(Bald.WidgetsStamp,"))
        self.assertIn("System.Time(hh:mm:ss)", stamp)
        self.assertNotIn("buildtemplate", ET.tostring(root, encoding="unicode"))

    def test_home_builds_its_rows_on_load_only_when_inputs_change(self):
        home = ET.parse(ROOT / "1080i" / "Home.xml").getroot()
        builds = [node for node in home.findall("onload") if "buildtemplate" in node.text]
        self.assertEqual(len(builds), 1)
        action = builds[0].text
        self.assertTrue(action.startswith("RunScript(script.skinvariables,action=buildtemplate,"))
        self.assertIn("lastbuildtime=$INFO[Skin.String(Bald.WidgetsStamp)]", action)
        self.assertNotIn("force", action)
        self.assertIsNone(builds[0].get("condition"))

    def test_screen_editor_has_mandatory_home_and_optional_media_screens(self):
        root = ET.parse(ROOT / "1080i" / "Custom_1117_BaldHomeScreens.xml").getroot()
        items = root.findall(".//control[@id='9300']/content/item")
        self.assertEqual([item.findtext("property[@name='node']") for item in items],
                         ["homewidgets", "movieswidgets", "tvshowswidgets", "livetv"])
        self.assertEqual([item.findtext("label") for item in items],
                         ["$LOCALIZE[10000]", "$LOCALIZE[342]", loc("TV Shows"), loc("Live TV")])
        self.assertEqual(items[0].find("property[@name='enabled']").text, "true")
        self.assertIn("Bald.Screen.Movies", ET.tostring(root, encoding="unicode"))
        self.assertIn("Bald.Screen.TVShows", ET.tostring(root, encoding="unicode"))
        self.assertIn("Bald.Screen.HideLiveTV", ET.tostring(root, encoding="unicode"))

    def test_optional_screens_control_main_menu_membership(self):
        root = ET.parse(ROOT / "1080i" / "Home.xml").getroot()
        movies = home_menu_button(root, "movies")
        tvshows = home_menu_button(root, "tvshows")
        # Movies and TV shows are opt-in; Live TV is opt-out.
        self.assertTrue(equivalent(movies.findtext("param[@name='visible']"), "Skin.HasSetting(Bald.Screen.Movies)"))
        self.assertTrue(equivalent(tvshows.findtext("param[@name='visible']"), "Skin.HasSetting(Bald.Screen.TVShows)"))
        livetv = home_menu_button(root, "livetv")
        self.assertTrue(equivalent(livetv.findtext("param[@name='visible']"), "!Skin.HasSetting(Bald.Screen.HideLiveTV)"))

    def test_live_tv_screen_has_toggle_but_no_widget_editor(self):
        root = ET.parse(ROOT / "1080i" / "Custom_1117_BaldHomeScreens.xml").getroot()
        toggle = root.find(".//control[@id='9401']")
        configure = root.find(".//control[@id='9402']")
        self.assertIn("Bald.Screen.HideLiveTV", ET.tostring(toggle, encoding="unicode"))
        self.assertTrue(equivalent(configure.findtext("visible"),
                                   "!String.IsEqual(Container(9300).ListItem.Property(node),livetv)"))

    def test_optional_screens_restore_their_last_row_when_entered_from_menu(self):
        for screen in ("home", "movies", "tvshows"):
            actions = home_menu.select_actions(home_menu.entry(preview=screen))
            has_rows = f"$EXP[Bald_HasRows_{screen}]"
            self.assertTrue(same_actions(actions, [
                (has_rows, f"SetProperty(Bald.Screen,{screen},home)"),
                (has_rows, f"SetProperty(Bald.Row,$INFO[Window(home).Property(Bald.Row.{screen})],home)"),
                (has_rows, "ClearProperty(Bald.Menu,home)"),
                (has_rows, f"SetFocus($INFO[Window(home).Property(Bald.Row.{screen})])"),
            ]), actions)
            self.assertTrue(has_action(
                home_menu.actions(home_menu.entry(preview=screen), "onfocus"), None,
                f"SetProperty(TMDbHelper.WidgetContainer,$INFO[Window(home).Property(Bald.Row.{screen})],home)"))

    def test_menu_entries_leave_up_and_down_to_the_grouplist(self):
        root = ET.parse(ROOT / "1080i" / "Home.xml").getroot()
        menu = root.find(".//control[@id='9000']")
        self.assertEqual(menu.findtext("onup"), "noop")
        self.assertEqual(menu.findtext("ondown"), "noop")
        entries = home_menu.entries()
        self.assertEqual([node.findtext("param[@name='id']") for node in entries], [f"900{n}" for n in range(1, 7)])
        self.assertEqual([node.findtext("param[@name='preview']") for node in entries],
                         ["home", "movies", "tvshows", "livetv", "search", "settings"])
        for node in entries:
            self.assertFalse([child for child in node.findall("param") if child.get("name") not in
                              {"id", "label", "preview", "visible", "suffix", "right"}])
            for child in home_menu.nested(node):
                self.assertIn(child.tag, {"onclick", "onfocus"})

        button = ET.parse(ROOT / "1080i" / "Includes_Bald_Home.xml").getroot().find(
            "include[@name='Bald_HomeMenuButton']/definition/control[@type='button']"
        )
        self.assertIsNone(button.find("onup"))
        self.assertIsNone(button.find("ondown"))
        self.assertIsNotNone(button.find("nested"))
        self.assertEqual([node.text for node in button.findall("onleft")], ["Action(Select)"])
        self.assertEqual([node.text for node in button.findall("onfocus")][-2:],
                         ["SetProperty(Bald.Menu,1,home)", "SetProperty(Bald.MenuPreview,$PARAM[preview],home)"])

    def test_menu_selection_previews_each_screens_last_active_widget(self):
        rows = ET.parse(ROOT / "1080i" / "Includes_Bald_HomeDefaults.xml").getroot()
        fanart = [value.get("condition") for value in rows.findall("variable[@name='Bald_Fanart']/value")]

        for screen, row, preview in (
            ("home", "9101", "Bald_PreviewHome"),
            ("movies", "9201", "Bald_PreviewMovies"),
            ("tvshows", "9301", "Bald_PreviewTVShows"),
        ):
            self.assertTrue(implies(f"$EXP[{preview}]", f"String.IsEqual(Window(home).Property(Bald.MenuPreview),{screen})"))
            wanted = (f"$EXP[{preview}] + String.IsEqual(Window(home).Property(Bald.Row.{screen}),{row})"
                      f" + !String.IsEmpty(Container({row}).ListItem.Art(fanart))")
            self.assertTrue(any(c and equivalent(c, wanted) for c in fanart), screen)
            logo = next(
                node for node in rows.findall(f"include[@name='Bald_ConfiguredArtLogos_{screen}']/definition/include")
                if node.findtext("param[@name='c']") == row and node.findtext("param[@name='p']") == "Odd"
            )
            self.assertTrue(equivalent(logo.findtext("param[@name='preview']"),
                                       f"$EXP[{preview}] + String.IsEqual(Window(home).Property(Bald.Row.{screen}),{row})"))

        row_definition = ET.parse(ROOT / "1080i" / "Includes_Bald_Home.xml").getroot().find(
            ".//include[@name='Bald_Row']/definition/control[@type='group']/visible"
        ).text
        # With the menu open, a row shows exactly when its screen is previewed and it was that screen's last row.
        previewed = ("String.IsEqual(Window(home).Property(Bald.MenuPreview),$PARAM[screen])"
                     " + String.IsEqual(Window(home).Property(Bald.Row.$PARAM[screen]),$PARAM[id])")
        self.assertTrue(equivalent(f"$EXP[Bald_MenuOpen] + [{row_definition}]", f"$EXP[Bald_MenuOpen] + {previewed}"))

        row = ET.parse(ROOT / "1080i" / "Includes_Bald_Home.xml").getroot().find(
            ".//include[@name='Bald_Row']/definition/control[@type='fixedlist']"
        )
        self.assertIn(
            "SetProperty(Bald.Row.$PARAM[screen],$PARAM[id],home)",
            [node.text for node in row.findall("onfocus")],
        )

    def test_menu_preview_backdrop_uses_the_same_live_fanart_as_the_preview(self):
        root = ET.parse(ROOT / "1080i" / "Includes_Bald_Home.xml").getroot()
        backdrop = root.find(".//include[@name='Bald_BackdropImage']")
        images = backdrop.findall("control[@type='image']")

        self.assertEqual(len(images), 1)
        self.assertIn("TMDbHelper.ListItem.BlurImage", images[0].findtext("texture"))
        self.assertEqual(images[0].findtext("fadetime"), "800")

    def test_menu_preview_suppresses_the_previously_active_rows_clearlogo(self):
        root = ET.parse(ROOT / "1080i" / "Includes_Bald_Home.xml").getroot()
        logo = root.find(".//include[@name='Bald_ArtLogo']")
        images = logo.findall("definition/control[@type='image']")

        self.assertEqual(len(images), 3)
        for image in images:
            visibility = image.findtext("visible")
            self.assertIn("$PARAM[preview]", atoms(visibility))
            # Outside its own preview, a row's logo shows only for the current row while no widget preview is open.
            self.assertTrue(implies(
                visibility, "!$EXP[Bald_WidgetPreview] + String.IsEqual(Window(home).Property(Bald.Row),$PARAM[c])",
                assume={"$PARAM[preview]": False, "$PARAM[ignore_home_row]": False}))

    def test_widget_rows_reopen_menu_on_the_active_screen(self):
        root = ET.parse(ROOT / "1080i" / "Includes_Bald_Home.xml").getroot()
        row = root.find(".//include[@name='Bald_Row']/definition/control[@type='fixedlist']")
        back_actions = [(node.get("condition"), node.text) for node in row.findall("onback")]
        up_actions = [(node.get("condition"), node.text) for node in row.findall("onup")]

        for screen, entry in (("home", "9001"), ("movies", "9002"), ("tvshows", "9003")):
            self.assertTrue(has_action(back_actions, f"String.IsEqual(Window(home).Property(Bald.Screen),{screen})",
                                       f"SetFocus({entry})"), screen)
        # Up from the first row returns to the active screen's menu entry.
        self.assertTrue(any(
            action == "SetFocus(9002)" and implies(
                cond, "Integer.IsEqual($PARAM[index],1) + String.IsEqual(Window(home).Property(Bald.Screen),movies)")
            for cond, action in up_actions
        ))

    def test_main_menu_accent_dot_follows_focus(self):
        root = ET.parse(ROOT / "1080i" / "Includes_Bald_Home.xml").getroot()
        focused = root.find(".//include[@name='Bald_MenuRowFocused']")
        unfocused = root.find(".//include[@name='Bald_MenuRowUnfocused']")

        self.assertEqual(focused.findtext("param[@name='always_dot']"), "true")
        self.assertIsNone(unfocused.find(".//control[@type='image']"))
        self.assertNotIn("ListItem.Property(id),home", ET.tostring(focused, encoding="unicode"))

    def test_disabled_optional_menu_entries_collapse_without_gaps(self):
        root = ET.parse(ROOT / "1080i" / "Home.xml").getroot()
        menu = root.find(".//control[@id='9000']")
        self.assertEqual(menu.get("type"), "grouplist")
        self.assertEqual(menu.findtext("orientation"), "vertical")
        self.assertEqual(menu.findtext("itemgap"), "0")
        self.assertEqual(menu.findtext("height"), "310")
        self.assertEqual(menu.findtext("scrolltime"), "320")

    def test_media_screens_disclose_and_open_their_full_libraries_with_right(self):
        root = ET.parse(ROOT / "1080i" / "Home.xml").getroot()
        movies = home_menu_button(root, "movies")
        tvshows = home_menu_button(root, "tvshows")
        self.assertEqual(movies.findtext("param[@name='suffix']"), "  ›")
        self.assertEqual(tvshows.findtext("param[@name='suffix']"), "  ›")
        self.assertEqual(movies.findtext("param[@name='right']"), "9197")
        self.assertEqual(tvshows.findtext("param[@name='right']"), "9196")

        self.assertEqual(root.findtext(".//control[@id='9197']/onfocus"), "ActivateWindow(Videos,videodb://movies/titles/,return)")
        self.assertEqual(root.findtext(".//control[@id='9196']/onfocus"), "ActivateWindow(Videos,videodb://tvshows/titles/,return)")

        focused = ET.parse(ROOT / "1080i" / "Includes_Bald_Home.xml").getroot().find(
            ".//include[@name='Bald_MenuRowFocused']"
        )
        disclosure = next(label for label in focused.findall(".//control[@type='label']") if label.findtext("label") == "›")
        self.assertTrue(equivalent(disclosure.findtext("visible"), "!String.IsEmpty(ListItem.Property(library))"))


    def test_add_widget_passes_named_parameters_not_positional_paths(self):
        root = ET.parse(ROOT / "1080i" / "Custom_1116_BaldHomeWidgets.xml").getroot()
        action = root.find(".//control[@id='9206']/onclick").text
        self.assertIn("&&limit::25", action)
        self.assertIn("&&secondary::0", action)
        self.assertIn("&&use_rawpath::True", action)

    def test_bald_appearance_settings_are_wired_to_rendering(self):
        root = ET.parse(ROOT / "1080i" / "Custom_1118_BaldAppearance.xml").getroot()
        xml = ET.tostring(root, encoding="unicode")
        for setting in (
            "Bald.HideClearlogo",
            "Bald.DisableBlur",
            "Bald.HideMediaFlags",
            "Bald.AmbientOff",
            "Bald.AutoHideMenuHint",
        ):
            self.assertIn(setting, xml)

        home = expand((ROOT / "1080i" / "Includes_Bald_Home.xml").read_text())
        self.assertIn("!Skin.HasSetting(Bald.DisableBlur)", home)
        self.assertIn("!Skin.HasSetting(Bald.HideClearlogo)", home)
        self.assertIn("!Skin.HasSetting(Bald.HideMediaFlags)", home)


if __name__ == "__main__":
    unittest.main()


class SettingsBackTests(unittest.TestCase):
    def test_back_steps_to_the_previous_window_instead_of_home(self):
        # PreviousMenu behaves like Escape and leaves for Home; Kodi's own Back retraces the window history.
        import xml.etree.ElementTree as ET
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / '1080i'
        for name in ('Includes_Bald_Configure.xml', 'Custom_1115_BaldSettings.xml', 'Custom_1116_BaldHomeWidgets.xml',
                     'Custom_1117_BaldHomeScreens.xml', 'Custom_1118_BaldAppearance.xml', 'SkinSettings.xml',
                     'Settings.xml', 'SettingsCategory.xml',
                     'SettingsProfile.xml', 'SettingsSystemInfo.xml'):
            with self.subTest(file=name):
                backs = [node.text for node in ET.parse(root / name).getroot().iter('onback')]
                self.assertNotIn('PreviousMenu', backs)
