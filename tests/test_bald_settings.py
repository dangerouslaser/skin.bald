import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from kodi_includes import resolve_window


ROOT = Path(__file__).resolve().parents[1]


def home_menu_button(root, label):
    return next(
        include for include in root.findall(".//control[@id='9000']/include[@content='Bald_HomeMenuButton']")
        if include.findtext("param[@name='label']") == label
    )


class BaldSettingsTests(unittest.TestCase):
    def test_settings_has_dedicated_bald_tile(self):
        root = ET.parse(ROOT / "1080i" / "Settings.xml").getroot()
        item = next(i for i in root.findall(".//item") if i.findtext("label") == "Bald Settings")
        self.assertEqual(item.findtext("onclick"), "ActivateWindow(1115)")

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
        self.assertEqual([item.findtext("label") for item in items], ["Home", "Movies", "TV Shows", "Live TV"])
        self.assertEqual(items[0].find("property[@name='enabled']").text, "true")
        self.assertIn("Bald.Screen.Movies", ET.tostring(root, encoding="unicode"))
        self.assertIn("Bald.Screen.TVShows", ET.tostring(root, encoding="unicode"))
        self.assertIn("Bald.Screen.HideLiveTV", ET.tostring(root, encoding="unicode"))

    def test_optional_screens_control_main_menu_membership(self):
        root = ET.parse(ROOT / "1080i" / "Home.xml").getroot()
        movies = home_menu_button(root, "Movies")
        tvshows = home_menu_button(root, "TV shows")
        self.assertEqual(movies.findtext("param[@name='visible']"), "Skin.HasSetting(Bald.Screen.Movies)")
        self.assertEqual(tvshows.findtext("param[@name='visible']"), "Skin.HasSetting(Bald.Screen.TVShows)")
        self.assertNotIn("!Skin.HasSetting", movies.findtext("param[@name='visible']"))
        self.assertNotIn("!Skin.HasSetting", tvshows.findtext("param[@name='visible']"))

        livetv = home_menu_button(root, "Live TV")
        self.assertEqual(
            livetv.findtext("param[@name='visible']"),
            "!Skin.HasSetting(Bald.Screen.HideLiveTV)",
        )

    def test_live_tv_screen_has_toggle_but_no_widget_editor(self):
        root = ET.parse(ROOT / "1080i" / "Custom_1117_BaldHomeScreens.xml").getroot()
        toggle = root.find(".//control[@id='9401']")
        configure = root.find(".//control[@id='9402']")
        self.assertIn("Bald.Screen.HideLiveTV", ET.tostring(toggle, encoding="unicode"))
        self.assertEqual(
            configure.findtext("visible"),
            "!String.IsEqual(Container(9300).ListItem.Property(node),livetv)",
        )

    def test_optional_screens_restore_their_last_row_when_entered_from_menu(self):
        root = ET.parse(ROOT / "1080i" / "Home.xml").getroot()
        for screen, label in (("movies", "Movies"), ("tvshows", "TV shows")):
            item = home_menu_button(root, label)
            screen_actions = [item.findtext(f"param[@name='enter{index}']") for index in range(1, 5)]
            self.assertIn(f"SetProperty(Bald.Screen,{screen},home)", screen_actions)
            self.assertIn(
                f"SetProperty(Bald.Row,$INFO[Window(home).Property(Bald.Row.{screen})],home)",
                screen_actions,
            )
            self.assertIn("ClearProperty(Bald.Menu,home)", screen_actions)
            self.assertIn(f"SetFocus($INFO[Window(home).Property(Bald.Row.{screen})])", screen_actions)

    def test_menu_selection_previews_each_screens_last_active_widget(self):
        home_includes = (ROOT / "1080i" / "Includes_Bald_Home.xml").read_text()
        rows = ET.parse(ROOT / "1080i" / "Includes_Bald_HomeDefaults.xml").getroot()
        fanart = [value.get("condition") for value in rows.findall("variable[@name='Bald_Fanart']/value")]

        for screen, row, preview in (
            ("home", "9101", "Bald_PreviewHome"),
            ("movies", "9201", "Bald_PreviewMovies"),
            ("tvshows", "9301", "Bald_PreviewTVShows"),
        ):
            self.assertIn(
                f'String.IsEqual(Window(home).Property(Bald.MenuPreview),{screen})',
                home_includes,
            )
            self.assertIn(
                f"$EXP[{preview}] + String.IsEqual(Window(home).Property(Bald.Row.{screen}),{row}) + !String.IsEmpty(Container({row}).ListItem.Art(fanart))",
                fanart,
            )
            logo = next(
                node for node in rows.findall(f"include[@name='Bald_ConfiguredArtLogos_{screen}']/definition/include")
                if node.findtext("param[@name='c']") == row and node.findtext("param[@name='p']") == "Odd"
            )
            self.assertEqual(
                logo.findtext("param[@name='preview']"),
                f"$EXP[{preview}] + String.IsEqual(Window(home).Property(Bald.Row.{screen}),{row})",
            )

        row_definition = ET.parse(ROOT / "1080i" / "Includes_Bald_Home.xml").getroot().find(
            ".//include[@name='Bald_Row']/definition/control[@type='group']/visible"
        ).text
        self.assertIn("Property(Bald.MenuPreview),$PARAM[screen]", row_definition)
        self.assertIn("Property(Bald.Row.$PARAM[screen]),$PARAM[id]", row_definition)

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
            self.assertIn("$PARAM[preview]", visibility)
            self.assertIn(
                "[!$EXP[Bald_WidgetPreview] + String.IsEqual(Window(home).Property(Bald.Row),$PARAM[c])]",
                visibility,
            )

    def test_widget_rows_reopen_menu_on_the_active_screen(self):
        root = ET.parse(ROOT / "1080i" / "Includes_Bald_Home.xml").getroot()
        row = root.find(".//include[@name='Bald_Row']/definition/control[@type='fixedlist']")
        back_actions = [(node.get("condition"), node.text) for node in row.findall("onback")]
        up_actions = [(node.get("condition"), node.text) for node in row.findall("onup")]

        self.assertIn(("String.IsEqual(Window(home).Property(Bald.Screen),home)", "SetFocus(9001)"), back_actions)
        self.assertIn(("String.IsEqual(Window(home).Property(Bald.Screen),movies)", "SetFocus(9002)"), back_actions)
        self.assertIn(
            (
                "String.IsEqual(Window(home).Property(Bald.Screen),tvshows)",
                "SetFocus(9003)",
            ),
            back_actions,
        )
        self.assertTrue(any(
            condition.startswith("Integer.IsEqual($PARAM[index],1) + String.IsEqual(Window(home).Property(Bald.Screen),movies)")
            and action == "SetFocus(9002)"
            for condition, action in up_actions
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
        movies = home_menu_button(root, "Movies")
        tvshows = home_menu_button(root, "TV shows")
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
        self.assertEqual(disclosure.findtext("visible"), "!String.IsEmpty(ListItem.Property(library))")


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

        home = (ROOT / "1080i" / "Includes_Bald_Home.xml").read_text()
        self.assertIn("!Skin.HasSetting(Bald.DisableBlur)", home)
        self.assertIn("!Skin.HasSetting(Bald.HideClearlogo)", home)
        self.assertIn("!Skin.HasSetting(Bald.HideMediaFlags)", home)


if __name__ == "__main__":
    unittest.main()
