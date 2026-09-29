import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import home_menu
from home_screens import SCREENS as HOME_SCREENS
from conditions import all_of, atoms, equivalent, has_action, implies, same_actions
from kodi_includes import expand, resolve_window
from skin_strings import loc


ROOT = Path(__file__).resolve().parents[1]


HUBS = [f"hub{n}" for n in range(1, 9)]


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
        # A hub's rows are the widgets of its entry in the hubs menu (node = its position, mode = widgets).
        self.assertIn("$INFO[Window(home).Property(Bald.ConfigureItem),&node=,]", content)
        self.assertIn("mode=$INFO[Window(home).Property(Bald.ConfigureMode)]", content)
        self.assertIn("skin=skin.bald", content)
        # Closing the editor after a change stamps the rows; Home rebuilds when the stamp it passes to Skin Variables
        # changes.
        self.assert_stamps_only_after_a_change("Custom_1116_BaldHomeWidgets.xml")
        self.assertNotIn("buildtemplate", ET.tostring(root, encoding="unicode"))

    def test_home_builds_its_rows_on_load_only_when_inputs_change(self):
        home = ET.parse(ROOT / "1080i" / "Home.xml").getroot()
        builds = [node for node in home.findall("onload") if "buildtemplate" in node.text]
        self.assertEqual(len(builds), 1)
        action = builds[0].text
        self.assertTrue(action.startswith("RunScript(script.skinvariables,action=buildtemplate,"))
        self.assertIn("lastbuildtime=$INFO[Skin.String(Bald.WidgetsStamp)]", action)
        self.assertNotIn("force", action)
        # Not before the one-time hubs migration (scripts/hubs.py) has written the hubs list and set its marker.
        self.assertTrue(equivalent(builds[0].get("condition"), "!String.IsEmpty(Skin.String(Bald.HubsMigrated))"))

    def test_screen_editor_lists_home_the_hubs_live_tv_and_add_hub(self):
        root = resolve_window("Custom_1117_BaldHomeScreens.xml")
        items = root.findall(".//control[@id='9300']/content/item")
        self.assertEqual([item.findtext("property[@name='kind']") for item in items],
                         ["home"] + ["hub"] * 8 + ["livetv", "add"])
        self.assertEqual([item.get("id") for item in items], ["1"] + [str(10 + n) for n in range(8)] + ["2", "3"])
        self.assertEqual(items[0].findtext("label"), "$LOCALIZE[10000]")
        self.assertEqual(items[-2].findtext("label"), loc("Live TV"))
        self.assertEqual(items[-1].findtext("label"), loc("Add hub"))
        # Hub n shows the entry at position n of the live hubs list 9390, while there is one.
        for n, item in enumerate(items[1:9]):
            self.assertEqual(item.findtext("label"), f"$INFO[Container(9390).ListItemAbsolute({n}).Label]")
            # Skin Variables' own index for the entry: Kodi reads a plain number in a static item's property as a string id.
            self.assertEqual(item.findtext("property[@name='slot']"), f"$INFO[Container(9390).ListItemAbsolute({n}).Property(item)]")
            self.assertEqual(item.findtext("property[@name='url']"), f"$INFO[Container(9390).ListItemAbsolute({n}).Property(url)]")
            self.assertTrue(implies(item.findtext("visible"), f"Integer.IsGreater(Container(9390).NumItems,{n})"))
        hubs = root.find(".//control[@id='9390']")
        self.assertIn("menu=hubs", hubs.findtext("content"))
        self.assertIn("edit=true", hubs.findtext("content"))
        self.assertNotIn("Bald.Screen.Movies", ET.tostring(root, encoding="unicode"))
        self.assertIn("Bald.Screen.HideLiveTV", ET.tostring(root, encoding="unicode"))
        # Closing it after a change rebuilds Home on its next load, as the widget editor does.
        self.assert_stamps_only_after_a_change("Custom_1117_BaldHomeScreens.xml")

    def assert_stamps_only_after_a_change(self, name):
        window = resolve_window(name)
        unloads = [(n.get("condition"), n.text) for n in window.findall("onunload")]
        stamp = next(u for u in unloads if u[1].startswith("Skin.SetString(Bald.WidgetsStamp,"))
        self.assertIn("System.Time(hh:mm:ss)", stamp[1])
        self.assertEqual(stamp[0], "!String.IsEmpty(Window(home).Property(Bald.WidgetsDirty))")
        self.assertIn((None, "ClearProperty(Bald.WidgetsDirty,home)"), unloads[unloads.index(stamp) + 1:])
        # Every Skin Variables action marks the rows changed first, under the same condition.
        runs = 0
        for parent in window.iter():
            clicks = [n for n in parent if n.tag == "onclick"]
            for i, click in enumerate(clicks):
                if click.text.startswith("RunPlugin("):
                    runs += 1
                    with self.subTest(window=name, action=click.text[:60]):
                        self.assertGreater(i, 0)
                        mark = clicks[i - 1]
                        self.assertEqual((mark.get("condition"), mark.text), (click.get("condition"), "SetProperty(Bald.WidgetsDirty,1,home)"))
        self.assertGreater(runs, 5)

    def test_hub_rows_run_skin_variables_actions_on_the_selected_hub(self):
        root = resolve_window("Custom_1117_BaldHomeScreens.xml")
        url = "$INFO[Container(9300).ListItem.Property(url)]"
        expected = {
            "9401": f"RunPlugin({url}&func=do_toggle&&disabled)",
            "9403": f"RunPlugin({url}&func=do_edit&&label)",
            "9404": f"RunPlugin({url}&func=do_action&&grouping::grouping://hubs/&&use_rawpath::True)",
            "9405": f"RunPlugin({url}&func=do_edit&&path&&null)",
            "9406": f"RunPlugin({url}&func=do_move&&-1)",
            "9407": f"RunPlugin({url}&func=do_move&&1)",
            "9408": f"RunPlugin({url}&func=do_delete)",
        }
        for control_id, action in expected.items():
            node = root.find(f".//control[@id='{control_id}']")
            self.assertIn(action, [n.text for n in node.findall("onclick")], control_id)
            self.assertTrue(implies(all_of([n.text for n in node.findall("visible")]), "$EXP[Bald_HubCategorySelected]")
                            or control_id == "9401", control_id)
        # Moving keeps the sidebar selection on the moved hub.
        self.assertIn("Control.Move(9300,-1)", [n.text for n in root.find(".//control[@id='9406']").findall("onclick")])
        self.assertIn("Control.Move(9300,1)", [n.text for n in root.find(".//control[@id='9407']").findall("onclick")])
        # The widget editor opens on the hub's own rows.
        rows = [(n.get("condition"), n.text) for n in root.find(".//control[@id='9402']").findall("onclick")]
        self.assertTrue(has_action(rows, "$EXP[Bald_HubCategorySelected]", "SetProperty(Bald.ConfigureNode,hubs,home)"))
        self.assertTrue(has_action(rows, "$EXP[Bald_HubCategorySelected]",
                                   "SetProperty(Bald.ConfigureItem,$INFO[Container(9300).ListItem.Property(slot)],home)"))
        self.assertTrue(has_action(rows, "$EXP[Bald_HubCategorySelected]", "SetProperty(Bald.ConfigureMode,widgets,home)"))
        self.assertTrue(has_action(rows, "String.IsEqual(Container(9300).ListItem.Property(kind),livetv)",
                                   "SetProperty(Bald.ConfigureNode,livetvwidgets,home)"))
        # The editor never opens on a hub without its index (Skin Variables would edit the hubs list as rows).
        self.assertEqual(rows[-1], ("!$EXP[Bald_HubCategorySelected] | !String.IsEmpty(Container(9300).ListItem.Property(slot))",
                                    "ActivateWindow(1116)"))
        # Add hub: up to eight, appended through Skin Variables' browser.
        add = [(n.get("condition"), n.text) for n in root.find(".//control[@id='9409']").findall("onclick")]
        self.assertTrue(any("func=do_new" in action and "menu=hubs" in action and implies(cond, "!$EXP[Bald_HubsFull]")
                            for cond, action in add))
        full = ET.parse(ROOT / "1080i" / "Includes_Bald_Configure.xml").getroot().findtext(
            "expression[@name='Bald_HubsFull']")
        self.assertEqual(full, "[Integer.IsGreater(Container(9390).NumItems,7)]")

    def test_hubs_and_live_tv_control_main_menu_membership(self):
        for n, hub in enumerate(HUBS, start=1):
            entry = home_menu.entry(preview=hub)
            self.assertEqual(entry.get("id"), f"901{n}")
            self.assertTrue(equivalent(entry.findtext("visible"), f"$EXP[Bald_HubShown_{hub}]"))
        livetv = home_menu.entry(preview="livetv")
        self.assertTrue(equivalent(livetv.findtext("visible"), "!Skin.HasSetting(Bald.Screen.HideLiveTV)"))

    def test_live_tv_has_a_toggle_and_its_own_rows(self):
        root = resolve_window("Custom_1117_BaldHomeScreens.xml")
        toggle = root.find(".//control[@id='9401']")
        configure = root.find(".//control[@id='9402']")
        self.assertIn("Bald.Screen.HideLiveTV", ET.tostring(toggle, encoding="unicode"))
        # Its only other condition is its settings level (Basic: always shown).
        self.assertTrue(equivalent(all_of([n.text for n in configure.findall("visible")]),
                                   "!String.IsEqual(Container(9300).ListItem.Property(kind),add)"))

    def test_screens_restore_their_last_row_when_entered_from_menu(self):
        for screen in ["home"] + HUBS:
            actions = home_menu.select_actions(home_menu.entry(preview=screen))
            has_rows = f"$EXP[Bald_HasRows_{screen}]"
            entering = [
                (has_rows, f"SetProperty(Bald.Screen,{screen},home)"),
                (has_rows, f"SetProperty(Bald.Row,$INFO[Window(home).Property(Bald.Row.{screen})],home)"),
                (has_rows, f"SetProperty(Bald.RowStyle,$VAR[Bald_RowStyle_{screen}],home)"),
                (has_rows, "ClearProperty(Bald.Menu,home)"),
                (has_rows, f"SetFocus($INFO[Window(home).Property(Bald.Row.{screen})])"),
            ]
            if screen != "home":
                # A hub without rows opens its target instead (bridge 902n, as Right does).
                entering.append((f"!{has_rows} + $EXP[Bald_HubHasOpen_{screen}]", f"SetFocus(902{screen[3:]})"))
            # With Appearance > Behavior "Select on a hub opens its library" off (the default); tests/test_hub_select.py
            # covers it on.
            off = home_menu.setting(False)
            self.assertTrue(same_actions(home_menu.live(actions, off), entering, off), actions)
            # The background follows the screen's remembered row while it is previewed (Bald_FollowContainer).
            onfocus = home_menu.actions(home_menu.entry(preview=screen), "onfocus")
            row = f"$INFO[Window(home).Property(Bald.Row.{screen})]"
            self.assertTrue(has_action(onfocus, None, f"SetProperty(Bald.FocusContainer,{row},home)"))
            self.assertTrue(has_action(onfocus, "$EXP[Bald_TMDbHelperFollows]",
                                       f"SetProperty(TMDbHelper.WidgetContainer,{row},home)"))

    def test_live_tv_select_enters_its_rows_and_right_opens_the_guide(self):
        # Like a hub: Select (and Left, which does what Select does) enters the rows while there are rows and a PVR
        # add-on, else opens the guide; Right opens the guide through bridge 9029.
        livetv = home_menu.entry(preview="livetv")
        rows = "$EXP[Bald_LiveTVRows]"
        off = home_menu.setting(False)
        select = home_menu.live(home_menu.select_actions(livetv), off)
        self.assertTrue(same_actions(select, [
            (rows, "SetProperty(Bald.Screen,livetv,home)"),
            (rows, "SetProperty(Bald.Row,$INFO[Window(home).Property(Bald.Row.livetv)],home)"),
            (rows, "SetProperty(Bald.RowStyle,$VAR[Bald_RowStyle_livetv],home)"),
            (rows, "ClearProperty(Bald.Menu,home)"),
            (rows, "SetFocus($INFO[Window(home).Property(Bald.Row.livetv)])"),
            (f"!{rows}", "SetProperty(Bald.ReturnMenu,9004,home)"),
            (f"!{rows}", "ActivateWindow(TVGuide)"),
        ], off), select)
        self.assertTrue(same_actions(home_menu.live(home_menu.actions(livetv, "onleft"), off), [("true", "Action(Select)")], off))
        self.assertTrue(same_actions(home_menu.live(home_menu.actions(livetv, "onright"), off), [("true", "9029")], off))
        self.assertEqual([n.text for n in home_menu.control(9029).findall("onfocus")],
                         ["SetProperty(Bald.ReturnMenu,9004,home)", "ActivateWindow(TVGuide)", "SetFocus(9004)"])
        live_rows = ET.parse(ROOT / "1080i" / "Includes_Bald_Home.xml").getroot().findtext(
            "expression[@name='Bald_LiveTVRows']")
        self.assertTrue(equivalent(live_rows, "System.HasPVRAddon + $EXP[Bald_HasRows_livetv]"))

    def test_menu_entries_leave_up_and_down_to_the_grouplist(self):
        root = ET.parse(ROOT / "1080i" / "Home.xml").getroot()
        menu = root.find(".//control[@id='9000']")
        # The ends wrap: the grouplist joins the last entry to the first when it has no onup/ondown of its own.
        self.assertIsNone(menu.find("onup"))
        self.assertIsNone(menu.find("ondown"))
        # Menu order: Home, the eight hub slots (the user's order), Live TV, Search, Settings, Power.
        entries = home_menu.entries()
        self.assertEqual([node.get("id") for node in entries],
                         ["9001"] + [f"901{n}" for n in range(1, 9)] + ["9004", "9005", "9006", "9007"])
        self.assertEqual([home_menu.previewed(node) for node in entries],
                         ["home"] + HUBS + ["livetv", "search", "settings", "power"])
        for node in entries:
            self.assertIsNone(node.find("onup"))
            self.assertIsNone(node.find("ondown"))

        button = ET.parse(ROOT / "1080i" / "Includes_Bald_Home.xml").getroot().find(
            "include[@name='Bald_HomeMenuButton']/definition/control[@type='button']"
        )
        self.assertIsNone(button.find("onup"))
        self.assertIsNone(button.find("ondown"))
        self.assertIsNotNone(button.find("nested"))
        self.assertEqual([(node.get("condition"), node.text) for node in button.findall("onleft")],
                         [("$PARAM[left_if]", "Action(Select)")])
        self.assertEqual([node.text for node in button.findall("onfocus")][-3:],
                         ["SetProperty(Bald.Menu,1,home)", "SetProperty(Bald.MenuPreview,$PARAM[preview],home)",
                          "SetProperty(Bald.RowStyle,$VAR[Bald_PreviewRowStyle],home)"])

    def test_menu_selection_previews_each_screens_last_active_widget(self):
        rows = ET.parse(ROOT / "1080i" / "Includes_Bald_HomeDefaults.xml").getroot()
        fanart = [value.get("condition") for value in rows.findall("variable[@name='Bald_Fanart']/value")]

        for screen, row, preview in (
            ("home", "9101", "Bald_PreviewHome"),
            ("livetv", "9051", "Bald_PreviewLiveTV"),
            ("hub1", "9201", "Bald_PreviewHub1"),
            ("hub2", "9301", "Bald_PreviewHub2"),
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
        self.assertTrue(equivalent(f"$EXP[Bald_MenuOpen] + $PARAM[enabled] + [{row_definition}]",
                                   f"$EXP[Bald_MenuOpen] + $PARAM[enabled] + {previewed}"))
        self.assertTrue(implies(row_definition, "$PARAM[enabled]"))

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

        # A still copy (no fadetime, on the first frame) under the crossfading one (curtain prototype).
        self.assertEqual(len(images), 2)
        for image in images:
            # The live blur, or the last one seen in windows without their own (Bald_BlurImage).
            self.assertIn("$VAR[Bald_BlurImage]", image.findtext("texture"))
        blur = root.find("variable[@name='Bald_BlurImage']")
        self.assertEqual(blur.findall("value")[-1].text, "$INFO[Window(home).Property(TMDbHelper.ListItem.BlurImage)]")
        self.assertIsNone(images[0].find("fadetime"))
        self.assertIsNone(images[0].find("texture").get("background"))
        self.assertEqual(images[1].findtext("fadetime"), "800")

    def test_menu_preview_suppresses_the_previously_active_rows_clearlogo(self):
        root = ET.parse(ROOT / "1080i" / "Includes_Bald_Home.xml").getroot()
        logo = root.find(".//include[@name='Bald_ArtLogo']")
        group = logo.find("definition/control[@type='group']")
        self.assertEqual(len(group.findall("control[@type='image']")), 3)
        # The row's group holds the three images (Kodi skips them while it is hidden).
        visibility = group.findtext("visible")
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
        # Back, and Up from the first row, focus the row's own screen entry (menu, written per screen by the generator).
        self.assertIn((None, "SetFocus($PARAM[menu])"), back_actions)
        self.assertIn(("Integer.IsEqual($PARAM[index],1)", "SetFocus($PARAM[menu])"), up_actions)
        fallback = ET.parse(ROOT / "1080i" / "Includes_Bald_HomeDefaults.xml").getroot()
        for screen, title, _, entry in HOME_SCREENS:
            for call in fallback.findall(f"include[@name='Bald_Generated_{title}Widgets']/definition/include"):
                self.assertEqual(call.findtext("param[@name='menu']"), str(entry), screen)
                self.assertEqual(call.findtext("param[@name='screen']"), screen)

    def test_main_menu_accent_dot_follows_focus(self):
        root = ET.parse(ROOT / "1080i" / "View_510_Bald_Posters.xml").getroot()
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
        self.assertEqual(menu.findtext("itemgap"), "6")
        self.assertEqual(menu.findtext("height"), "310")
        self.assertEqual(menu.findtext("scrolltime"), "320")

    def test_hubs_disclose_and_open_their_targets_with_right(self):
        for n, hub in enumerate(HUBS, start=1):
            entry = home_menu.entry(preview=hub)
            self.assertEqual(entry.findtext("label"), f"$VAR[Bald_HubLabel_{hub}]$VAR[Bald_HubSuffix_{hub}]")
            # Right navigates to the bridge only when the hub has a target (a conditional numeric onright).
            off = home_menu.setting(False)
            self.assertTrue(same_actions(home_menu.live(home_menu.actions(entry, "onright"), off),
                                         [(f"$EXP[Bald_HubHasOpen_{hub}]", f"902{n}")], off))
            bridge = home_menu.control(f"902{n}")
            self.assertEqual(bridge.get("type"), "button")
        # The seeded Movies and TV shows hubs open the libraries the old 9197 and 9196 bridges opened.
        fallback = ET.parse(ROOT / "1080i" / "Includes_Bald_HomeDefaults.xml").getroot()
        self.assertEqual(fallback.findtext("include[@name='Bald_HubOpen_hub1']/definition/onfocus"),
                         "ActivateWindow(videos,videodb://movies/titles/,return)")
        self.assertEqual(fallback.findtext("include[@name='Bald_HubOpen_hub2']/definition/onfocus"),
                         "ActivateWindow(videos,videodb://tvshows/titles/,return)")
        # The bridge remembers its menu entry for the return to Home (Bald_ReturnToMenu), opens the target, then hands
        # focus back to the entry (a target that leaves Home active would otherwise strand it on the bridge).
        self.assertEqual([n.text for n in home_menu.control(9021).findall("onfocus")],
                         ["SetProperty(Bald.ReturnMenu,9011,home)", "SetProperty(Bald.HubTitle,$ESCVAR[Bald_HubLabel_hub1],home)",
                          "ActivateWindow(videos,videodb://movies/titles/,return)", "SetFocus(9011)"])
        self.assertIsNone(fallback.find("include[@name='Bald_HubOpen_hub3']/definition/onfocus"))
        suffix = fallback.find("variable[@name='Bald_HubSuffix_hub1']/value")
        self.assertEqual((suffix.get("condition"), suffix.text), ("$EXP[Bald_HubHasOpen_hub1]", "  ›"))

        focused = ET.parse(ROOT / "1080i" / "View_510_Bald_Posters.xml").getroot().find(
            ".//include[@name='Bald_MenuRowFocused']"
        )
        disclosure = next(label for label in focused.findall(".//control[@type='label']") if label.findtext("label") == "›")
        self.assertTrue(equivalent(disclosure.findtext("visible"), "!String.IsEmpty(ListItem.Property(library))"))


if __name__ == "__main__":
    unittest.main()
