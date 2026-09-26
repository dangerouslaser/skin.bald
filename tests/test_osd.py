"""The Bald video OSD (Includes_Bald_OSD.xml; docs/SPEC.md 5.16, "Video OSD"): Kodi and add-on control contracts, the
Playback settings, the down chain, helper guards, the companion panels' stand-in rows, Bald-only styling and focus
safety."""

import re
import unittest
import xml.etree.ElementTree as ET


from kodi_includes import SKIN, expressions, include_definitions, resolve_window

ROOT = SKIN.parent
OSD_INCLUDES = "Includes_Bald_OSD.xml"
COMPANIONS = {"Custom_1120_OSDInfoPanel.xml": ("1120", "70043"), "Custom_1121_OSDAudioStreams.xml": ("1121", "70060"),
              "Custom_1122_OSDSubtitleStreams.xml": ("1122", "70061"), "Custom_1123_OSDVideoPanel.xml": ("1123", "70062"),
              "Custom_1124_OSDNextItem.xml": ("1124", "607")}
UPNEXT = ["script-upnext-upnext.xml", "script-upnext-stillwatching.xml", "script-upnext-upnext-simple.xml",
          "script-upnext-stillwatching-simple.xml"]
WINDOWS = (["VideoOSD.xml", "DialogSeekBar.xml", "VideoOSDBookmarks.xml", "Custom_1119_BaldPlayback.xml",
            "Custom_1125_OSDPlaylist.xml", "Custom_1126_OSDCast.xml", "Custom_1127_OSDInfoOverlay.xml",
            "Custom_1128_OSDDetails.xml"] + list(COMPANIONS) + UPNEXT)
# The row's buttons in order: transport, then tools.
ROW = ["602", "600", "607", "603", "804", "70045", "70047", "70043", "70060", "70061", "70062"]
CHAIN = ["pvrchannelguide", "pvrosdchannels", "1125", "videobookmarks", "1126"]
FOCUSABLE = {"button", "radiobutton", "togglebutton", "slider", "sliderex", "spincontrol", "spincontrolex", "edit",
             "list", "fixedlist", "wraplist", "panel", "grouplist"}
TEXTURE_TAGS = {"texture", "texturefocus", "texturenofocus", "texturebg", "lefttexture", "midtexture", "righttexture",
                "overlaytexture", "textureslidernib", "textureslidernibfocus", "texturesliderbar",
                "textureradioonfocus", "textureradioonnofocus", "textureradioofffocus", "textureradiooffnofocus",
                "textureradioondisabled", "textureradiooffdisabled"}
TWEENS = {"slide": {("cubic", "out")}, "fade": {("sine", "inout")}, "zoom": {("back", "out"), ("sine", "inout")}}


def ids(root):
    found = {}
    for node in root.iter("control"):
        if node.get("id"):
            found.setdefault(node.get("id"), node)
    return found


def activations(node, tag="ondown"):
    """(condition, window) for each ActivateWindow in a control's <tag> actions."""
    out = []
    for action in node.findall(tag):
        match = re.fullmatch(r"ActivateWindow\(([^)]+)\)", (action.text or "").strip())
        if match:
            out.append((action.get("condition") or "", match.group(1)))
    return out


class OSDContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.windows = {name: resolve_window(name) for name in WINDOWS}

    def test_kodi_and_addon_ids_keep_their_types(self):
        wanted = {"DialogSeekBar.xml": {"401": "slider", "402": "slider", "403": "slider"},
                  "VideoFullScreen.xml": {"10": "label", "11": "label", "12": "label"},
                  "VideoOSDBookmarks.xml": {"2": "button", "3": "button", "4": "button", "11": "panel"}}
        for name in UPNEXT:
            wanted[name] = {"3012": "button", "3013": "button", "3014": "progress"}
        for name, table in wanted.items():
            found = ids(self.windows.get(name) or resolve_window(name))
            for control_id, kind in table.items():
                with self.subTest(window=name, id=control_id):
                    self.assertIn(control_id, found)
                    self.assertEqual(found[control_id].get("type"), kind)

    def test_seek_nibs_show_while_seeking_and_linger(self):
        found = ids(self.windows["DialogSeekBar.xml"])
        for control_id in ("401", "402", "403"):
            nib = found[control_id]
            with self.subTest(id=control_id):
                self.assertIn("Player.Seeking", nib.findtext("visible"))
                hidden = [a for a in nib.findall("animation") if a.get("type") == "Hidden"]
                self.assertEqual(hidden[0].find("effect").get("delay"), "300")

    def test_osd_row_order_and_seek_sliders(self):
        osd = self.windows["VideoOSD.xml"]
        found = ids(osd)
        row = [c.get("id") for group in ("201", "202") for c in found[group].findall("control")]
        self.assertEqual(row, ROW)
        self.assertEqual(found["87"].findtext("action"), "seek")
        self.assertEqual(found["88"].findtext("action"), "pvr.seek")
        # Up from a transport button reaches the slider only when seeking is possible.
        ups = [(n.get("condition"), n.text) for n in found["602"].findall("onup")]
        self.assertTrue(all("Player.SeekEnabled" in (condition or "") for condition, _ in ups), ups)

    def test_radio_textures_are_static(self):
        # Kodi's radio textures take no $VAR (0.2.0's play/pause drew a broken icon); icons switch through <selected>.
        for name, root in self.windows.items():
            for node in root.iter():
                if node.tag.startswith("textureradio"):
                    with self.subTest(window=name, tag=node.tag):
                        self.assertNotIn("$VAR[", node.text or "")
                        self.assertNotIn("$INFO[", node.text or "")

    def test_sliders_have_a_real_bar_texture(self):
        # Kodi scales the nib by the control height over the bar texture's height; an empty bar ballooned it.
        for name, root in self.windows.items():
            for slider in root.iter("control"):
                if slider.get("type") == "slider":
                    with self.subTest(window=name, slider=slider.get("id")):
                        self.assertTrue((slider.findtext("texturesliderbar") or "").strip())

    def test_live_tv_swaps_back_and_forward(self):
        found = ids(self.windows["VideoOSD.xml"])
        self.assertEqual(found["600"].findtext("textureradioonnofocus"), "osd/fullscreen/buttons/guide.png")
        self.assertEqual(found["607"].findtext("textureradioonnofocus"), "osd/fullscreen/buttons/record-white.png")
        self.assertEqual(found["600"].findtext("selected"), "VideoPlayer.Content(livetv)")
        back = [(n.get("condition") or "", n.text) for n in found["600"].findall("onclick")]
        self.assertIn(("VideoPlayer.Content(livetv)", "ActivateWindow(TVGuide)"), back)
        forward = [(n.get("condition") or "", n.text) for n in found["607"].findall("onclick")]
        self.assertIn(("VideoPlayer.Content(livetv)", "PVR.ToggleRecordPlayingChannel"), forward)

    def test_play_pause_hides_itself_and_live_tv_gets_a_focus(self):
        root = ET.parse(SKIN / "VideoOSD.xml").getroot()
        self.assertEqual(root.findtext("defaultcontrol"), "602")
        onload = [(n.get("condition"), n.text) for n in root.findall("onload")]
        self.assertIn(("!Player.PauseEnabled", "SetFocus(600)"), onload)
        found = ids(self.windows["VideoOSD.xml"])
        self.assertEqual(found["602"].findtext("visible"), "Player.PauseEnabled")
        self.assertIn(found["600"].findtext("visible"), (None, "true"))

    def test_no_focusable_control_is_hidden_only_by_a_parent(self):
        # CGUIControl::CanFocus ignores a parent's visibility (the 0.2.0 Live TV lock-up): a focusable control under a
        # group that has <visible> must carry its own.
        for name, root in self.windows.items():
            parents = {child: node for node in root.iter() for child in node}
            for control in root.iter("control"):
                if control.get("type") not in FOCUSABLE or control.get("type") == "grouplist":
                    continue
                node, hidden_parent = parents.get(control), False
                while node is not None:
                    if node.tag == "control" and node.find("visible") is not None:
                        hidden_parent = True
                    node = parents.get(node)
                if hidden_parent:
                    with self.subTest(window=name, id=control.get("id")):
                        self.assertIsNotNone(control.find("visible"))

    def test_no_onback_previousmenu(self):
        for name in WINDOWS + [OSD_INCLUDES]:
            for node in ET.parse(SKIN / name).getroot().iter("onback"):
                with self.subTest(file=name):
                    self.assertNotIn("previousmenu", (node.text or "").lower().replace(" ", ""))


class CompanionTests(unittest.TestCase):
    def test_each_panel_repeats_the_row_with_its_button_real(self):
        osd = ids(resolve_window("VideoOSD.xml"))
        for name, (window_id, owner) in COMPANIONS.items():
            root = resolve_window(name)
            found = ids(root)
            self.assertEqual(root.findtext("defaultcontrol"), owner)
            row = [c for group in ("201", "202") for c in found[group].findall("control")]
            with self.subTest(window=name):
                self.assertEqual([c.get("id") for c in row], ROW)
                for control in row:
                    self.assertEqual(control.findtext("visible"), osd[control.get("id")].findtext("visible"))
                    if control.get("id") == owner:
                        self.assertEqual(control.get("type"), "radiobutton")
                        continue
                    self.assertEqual(control.get("type"), "button")
                    self.assertEqual([n.text for n in control.findall("onfocus")],
                                     [f"Dialog.Close({window_id},true)", f"SetFocus({control.get('id')})"])

    def test_focusing_a_tool_opens_its_panel(self):
        osd = ids(resolve_window("VideoOSD.xml"))
        for name, (window_id, owner) in COMPANIONS.items():
            focus = [n.text for n in osd[owner].findall("onfocus")]
            with self.subTest(button=owner):
                self.assertIn(f"ActivateWindow({window_id})", focus)

    def test_companions_close_instantly_so_stand_ins_can_hand_focus_back(self):
        for name in COMPANIONS:
            root = resolve_window(name)
            closes = [a for a in root.iter("animation") if a.get("type") == "WindowClose"]
            with self.subTest(window=name):
                self.assertEqual(closes, [])

    def test_stream_lists_use_skin_variables(self):
        for name, list_id, kind, method in (("Custom_1121_OSDAudioStreams.xml", "8110", "audio", "set_player_audiostream"),
                                            ("Custom_1122_OSDSubtitleStreams.xml", "8120", "subtitle", "set_player_subtitle")):
            stream_list = ids(resolve_window(name))[list_id]
            with self.subTest(window=name):
                self.assertEqual(stream_list.findtext("content"),
                                 f"plugin://script.skinvariables/?info=get_player_streams&stream_type={kind}"
                                 "&reload=$INFO[Window.Property(UID)]")
                self.assertEqual(stream_list.findtext("visible"), "$EXP[Bald_OSDHasSkinVariables]")
                clicks = [n.text for n in stream_list.findall("onclick")]
                self.assertIn(f"RunScript(script.skinvariables,{method}=$INFO[ListItem.Property(index)],"
                              "reload_property=UID)", clicks)
        subtitles = ids(resolve_window("Custom_1122_OSDSubtitleStreams.xml"))["8120"]
        self.assertIn("Action(ShowSubtitles)", [n.text for n in subtitles.findall("onclick")])


class ChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definitions = include_definitions()
        cls.bodies = expressions()

    def chain(self, stage):
        holder = ET.Element("control")
        for node in self.definitions[f"Bald_OSDChainFrom_{stage}"]:
            holder.append(node)
        return activations(holder)

    def test_chain_order_and_each_stage_skips_the_ones_before(self):
        for stage in range(5):
            targets = [window for _, window in self.chain(stage)]
            with self.subTest(stage=stage):
                self.assertEqual(targets, CHAIN[stage:])
                for index, (condition, _) in enumerate(self.chain(stage)):
                    # every earlier candidate of this stage is excluded
                    self.assertEqual(condition.count("!$EXP[Bald_OSDChain"), index)

    def test_every_stage_can_be_switched_off(self):
        for name, setting in (("Guide", "NoGuidePanel"), ("Channels", "NoChannelsPanel"),
                              ("Playlist", "NoPlaylistPanel"), ("Bookmarks", "NoBookmarksPanel"),
                              ("Cast", "NoCastPanel")):
            with self.subTest(stage=name):
                self.assertIn(f"!Skin.HasSetting(Bald.OSD.{setting})", self.bodies[f"Bald_OSDChain{name}"])

    def test_each_panel_continues_the_chain(self):
        osd = ids(resolve_window("VideoOSD.xml"))
        for button in ROW:
            with self.subTest(button=button):
                self.assertEqual([w for _, w in activations(osd[button])], CHAIN)
        playlist = ids(resolve_window("Custom_1125_OSDPlaylist.xml"))["8150"]
        self.assertEqual([w for _, w in activations(playlist)], CHAIN[3:])
        self.assertEqual(playlist.findtext("onup"), "Dialog.Close(1125)")
        bookmarks = ids(resolve_window("VideoOSDBookmarks.xml"))
        self.assertEqual([w for _, w in activations(bookmarks["11"])], CHAIN[4:])
        self.assertEqual(bookmarks["9001"].findtext("onup"), "Dialog.Close(videobookmarks)")
        guide = ids(resolve_window("DialogPVRChannelGuide.xml"))["11"]
        self.assertEqual([w for _, w in activations(guide)], ["pvrosdchannels"])

    def test_chain_panels_stop_the_auto_close(self):
        for name in ("Custom_1125_OSDPlaylist.xml", "Custom_1126_OSDCast.xml", "VideoOSDBookmarks.xml",
                     "DialogPVRChannelGuide.xml", "DialogPVRChannelsOSD.xml"):
            onload = [n.text for n in ET.parse(SKIN / name).getroot().findall("onload")]
            with self.subTest(window=name):
                self.assertIn("CancelAlarm(bald_osd_close,true)", onload)


class HelperGuardTests(unittest.TestCase):
    def test_cast_needs_tmdb_helper(self):
        bodies = expressions()
        guard = bodies["Bald_OSDHasTMDbHelper"]
        self.assertIn("System.HasAddon(plugin.video.themoviedb.helper)", guard)
        self.assertIn("System.AddonIsEnabled(plugin.video.themoviedb.helper)", guard)
        self.assertIn("$EXP[Bald_OSDHasTMDbHelper]", bodies["Bald_OSDChainCast"])
        # 1126 is only ever opened through the guarded chain.
        for path in SKIN.glob("*.xml"):
            for node in ET.parse(path).getroot().iter():
                if (node.text or "").strip() == "ActivateWindow(1126)":
                    with self.subTest(file=path.name):
                        self.assertIn("$EXP[Bald_OSDChainCast]", node.get("condition") or "")
        row = ids(resolve_window("Custom_1119_BaldPlayback.xml"))["9835"]
        self.assertEqual(row.findtext("enable"), "$EXP[Bald_OSDHasTMDbHelper]")

    def test_skin_variables_guard(self):
        guard = expressions()["Bald_OSDHasSkinVariables"]
        self.assertIn("System.HasAddon(script.skinvariables)", guard)
        self.assertIn("System.AddonIsEnabled(script.skinvariables)", guard)


class SettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = resolve_window("Custom_1119_BaldPlayback.xml")
        cls.page_text = ET.tostring(cls.page, encoding="unicode")
        cls.osd_text = (SKIN / OSD_INCLUDES).read_text(encoding="utf-8")

    def test_every_osd_setting_is_on_the_playback_page(self):
        read = set(re.findall(r"Skin\.(?:HasSetting|String)\((Bald\.OSD\.\w+)", self.osd_text))
        read |= set(re.findall(r"Skin\.(?:HasSetting|String)\((Bald\.OSD\.\w+)",
                               (SKIN / "Custom_1128_OSDDetails.xml").read_text()))
        self.assertEqual(read, {"Bald.OSD.AutoClose", "Bald.OSD.PauseMode", "Bald.OSD.PauseDelay",
                                "Bald.OSD.TimeDisplay", "Bald.OSD.DetailsLogo", "Bald.OSD.DetailsFlags",
                                "Bald.OSD.DetailsPlot", "Bald.OSD.HideInfoArt",
                                "Bald.OSD.HideInfoPlot", "Bald.OSD.NoGuidePanel", "Bald.OSD.NoChannelsPanel",
                                "Bald.OSD.NoPlaylistPanel", "Bald.OSD.NoBookmarksPanel", "Bald.OSD.NoCastPanel"})
        for setting in read:
            with self.subTest(setting=setting):
                self.assertRegex(self.page_text, rf"Skin\.(ToggleSetting|SetString|Reset)\({re.escape(setting)}[,)]")

    def test_toggles_are_named_so_unset_is_the_default(self):
        # On by default reads as the negation of a Hide/No setting; the opt-ins are the three details on the controls.
        for row in self.page.iter("control"):
            if row.get("type") != "radiobutton":
                continue
            selected = row.findtext("selected")
            with self.subTest(id=row.get("id")):
                if "Bald.OSD.Details" in selected:
                    self.assertRegex(selected, r"^Skin\.HasSetting\(Bald\.OSD\.Details(Logo|Flags|Plot)\)$")
                else:
                    self.assertRegex(selected, r"^!Skin\.HasSetting\(Bald\.OSD\.(Hide|No)\w+\)")

    def test_value_labels_end_with_the_default(self):
        definitions = {node.get("name"): node for node in ET.parse(SKIN / OSD_INCLUDES).getroot().iter("variable")}
        for row in self.page.iter("control"):
            label2 = row.findtext("label2")
            if not label2:
                continue
            name = re.fullmatch(r"\$VAR\[(\w+)\]", label2).group(1)
            values = definitions[name].findall("value")
            with self.subTest(variable=name):
                self.assertGreater(len(values), 1)
                self.assertIsNone(values[-1].get("condition"))

    def test_bald_settings_opens_the_page(self):
        home = resolve_window("Custom_1115_BaldSettings.xml")
        self.assertIn("ActivateWindow(1119)", [n.text for n in home.iter("onclick")])

    def test_estuary_auto_close_is_retired_and_migrated(self):
        timers = (SKIN / "Timers.xml").read_text()
        self.assertNotIn("<name>autoclosevideoosd</name>", timers)
        self.assertIn("<name>bald_osd_close</name>", timers)
        startup = (SKIN / "Startup.xml").read_text()
        self.assertIn("Skin.Reset(OSDAutoClose)", startup)
        for name in ("DialogSettings.xml", "DialogSlider.xml", "DialogSubtitles.xml"):
            with self.subTest(dialog=name):
                self.assertIn("Bald_OSDSuspendAutoClose", (SKIN / name).read_text())


class OSDStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        palette = ET.parse(ROOT / "colors" / "defaults.xml").getroot()
        cls.colors = {node.get("name") for node in palette if node.get("name", "").startswith("bald_")}
        cls.fontsets = [{f.findtext("name") for f in fs.findall("font")}
                        for fs in ET.parse(SKIN / "Font.xml").getroot().findall("fontset")]
        cls.roots = {name: resolve_window(name) for name in WINDOWS}

    def test_bald_fonts_in_every_fontset_and_bald_colours(self):
        for name, root in self.roots.items():
            for node in root.iter():
                text = (node.text or "").strip()
                with self.subTest(window=name, tag=node.tag, text=text):
                    if node.tag == "font" and text:
                        self.assertTrue(text.startswith("Bald_"))
                        for fontset in self.fontsets:
                            if "Bald_Section" in fontset:
                                self.assertIn(text, fontset)
                    if node.tag in ("textcolor", "focusedcolor", "disabledcolor", "selectedcolor") and text:
                        self.assertIn(text, self.colors)
                    if node.get("colordiffuse"):
                        self.assertIn(node.get("colordiffuse"), self.colors)

    def test_every_drawn_texture_is_tinted_unless_it_is_art(self):
        # An untinted skin texture draws white (the 0.2.0 report of a white blob under the OSD): every image,
        # progress, slider and button texture names a colour token, except artwork from $INFO/$VAR.
        for name, root in self.roots.items():
            for node in root.iter():
                text = (node.text or "").strip()
                # slider_clear.png is fully transparent: it only sizes a slider's nib.
                if (node.tag not in TEXTURE_TAGS or not text or "$INFO[" in text or "$VAR[" in text
                        or text == "bald/slider_clear.png"):
                    continue
                with self.subTest(window=name, tag=node.tag, texture=text):
                    self.assertIn(node.get("colordiffuse"), self.colors)

    def test_motion_uses_the_three_curves(self):
        for name, root in self.roots.items():
            for effect in root.iter("effect"):
                kind = effect.get("type")
                with self.subTest(window=name, effect=kind):
                    self.assertIn(kind, TWEENS)
                    self.assertIn((effect.get("tween"), effect.get("easing")), TWEENS[kind])

    def test_hints_sit_on_the_hint_line(self):
        for name in ["VideoOSD.xml", "Custom_1125_OSDPlaylist.xml", "Custom_1126_OSDCast.xml",
                     "VideoOSDBookmarks.xml"] + list(COMPANIONS):
            groups = [n for n in self.roots[name].iter("control")
                      if n.get("type") == "group" and n.findtext("top") == "954"]
            with self.subTest(window=name):
                self.assertEqual(len(groups), 1)
                self.assertEqual(groups[0].findtext("left"), "1224")


if __name__ == "__main__":
    unittest.main()
