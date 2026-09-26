"""The player windows restyled in Bald's language (Includes_Bald_Playback.xml; docs/SPEC.md 5, "Playback (proposed)").

They keep every control id Kodi binds and every skin id, action and navigation route Estuary gave them; only Bald
fonts and colour tokens are used; and no window adds an onback PreviousMenu (docs/NOTES.md).
"""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import kodi_includes
from conditions import all_of, equivalent, same_actions
from kodi_includes import SKIN, expand_call, expressions, include_definitions, resolve_window
from skin_strings import PO, strings

ROOT = SKIN.parent
ESTUARY = Path("/Applications/Kodi.app/Contents/Resources/Kodi/addons/skin.estuary/xml")
PLAYBACK_RANGE = range(31616, 31650)

# Restyled windows and the ids Kodi's C++ binds in them, with the control type each must stay (checked against
# xbmc master: CGUIDialogSeekBar, CGUIWindowFullScreen, CGUIDialogSlider, CGUIDialogVideoBookmarks,
# CGUIDialogSubtitles). Windows whose class binds nothing list only their skin ids.
WINDOWS = {
    "DialogSeekBar.xml": {"401": "slider", "403": "slider", "40000": "label"},
    "VideoOSD.xml": {"87": "button", "200": "group", "201": "grouplist", "202": "grouplist", "600": "radiobutton",
                     "601": "radiobutton", "602": "button", "603": "radiobutton", "606": "radiobutton",
                     "607": "radiobutton", "608": "radiobutton", "698": "group", "804": "radiobutton",
                     "6000": "group", **{str(i): "radiobutton" for i in range(70040, 70049)}},
    "MusicOSD.xml": {"87": "button", "200": "group", "201": "grouplist", "202": "grouplist", "600": "radiobutton",
                     "601": "radiobutton", "602": "button", "603": "radiobutton", "606": "radiobutton",
                     "607": "radiobutton", "608": "radiobutton", "698": "group", "699": "group",
                     "70040": "radiobutton", "70041": "radiobutton", "70048": "radiobutton", "70050": "radiobutton",
                     "70051": "radiobutton", "70052": "radiobutton", "70053": "button", "70054": "radiobutton",
                     "70055": "radiobutton"},
    "PlayerControls.xml": {"23": "progress", "87": "button", "201": "grouplist", "600": "radiobutton",
                           "602": "radiobutton", "603": "radiobutton", "605": "radiobutton", "607": "radiobutton",
                           "699": "group", "704": "button"},
    "VideoOSDBookmarks.xml": {"2": "button", "3": "button", "4": "button", "11": "panel", "9001": "grouplist"},
    "Custom_1109_TopBarOverlay.xml": {},
    "Custom_1110_TempoControl.xml": {"11": "button", "12": "button"},
    "DialogFullScreenInfo.xml": {"999": "button"},
    "VideoFullScreen.xml": {"0": "group", "1": "group", "10": "label", "11": "label", "12": "label"},
    "Custom_1101_SettingsDialog.xml": {"1": "label", "11000": "group", "11100": "grouplist", "22002": "button"},
    "DialogSlider.xml": {"10": "label", "11": "slider", "12": "label", "13": "button", "14": "button"},
    "DialogSubtitles.xml": {"73": "scrollbar", "100": "label", "110": "image", "120": "list", "130": "grouplist",
                            "140": "label", "150": "list", "160": "button", "250": "group"},
}
# Files restyled by this pass: the windows plus their includes.
FILES = list(WINDOWS) + ["Includes_Bald_Playback.xml", "Includes_SettingsDialog.xml"]
# Estuary includes still called: they carry no Estuary colours or fonts (the popup surface and buttons are Bald).
SHARED_INCLUDES = {"HiddenObject", "DialogBackgroundCommons", "DefaultDialogButton", "DefaultSimpleListLayout",
                   "Animation_DialogPopupOpenClose", "SettingsDialogLayout", "SettingsDialogOSDVisible"}
# Estuary variables still read: textures and plain labels only.
SHARED_VARIABLES = {"PlayerClearLogoVar", "NowPlayingPosterVar", "PlayerControlsPlayImageVar",
                    "PlayerControlsRepeatImageVar", "VideoPlayerForwardRewindVar", "ActiveVideoPlayerSubtitleLanguage",
                    "ActiveVideoPlayerAudioLanguage", "AudioCodecVar", "AudioChannelsVar", "VideoCodecVar",
                    "VideoHDRTypeVar", "VideoResolutionTypeVar"}
ACTION_TAGS = ("onclick", "onleft", "onright", "onup", "ondown", "onback", "onfocus", "onunfocus", "action",
               "selected", "enable", "info")
COLOR_TAGS = ("textcolor", "focusedcolor", "disabledcolor", "selectedcolor", "invalidcolor", "shadowcolor",
              "textcolor2", "focusedcolor2")


def _ids(root):
    """First control for each id, in document order."""
    found = {}
    for node in root.iter("control"):
        if node.get("id") is not None:
            found.setdefault(node.get("id"), node)
    return found


def _actions(control, tag):
    return [(node.get("condition"), (node.text or "").strip()) for node in control.findall(tag)]


def _estuary_window(filename):
    definitions = include_definitions(ESTUARY)
    root = ET.parse(ESTUARY / filename).getroot()
    kodi_includes._expand_in_place(root, definitions)
    return root


class PlaybackContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.windows = {name: resolve_window(name) for name in WINDOWS}

    def test_kodi_and_skin_ids_are_present_with_their_types(self):
        for name, wanted in WINDOWS.items():
            ids = _ids(self.windows[name])
            for control_id, kind in wanted.items():
                with self.subTest(window=name, id=control_id):
                    self.assertIn(control_id, ids)
                    self.assertEqual(ids[control_id].get("type"), kind)

    def test_seek_controls_keep_their_actions(self):
        osd = _ids(self.windows["VideoOSD.xml"])
        seek = osd["87"]
        self.assertEqual(_actions(seek, "onleft"), [(None, "StepBack")])
        self.assertEqual(_actions(seek, "onright"), [("!Player.Paused", "StepForward"),
                                                     ("Player.Paused", "PlayerControl(FrameAdvance(1))")])
        self.assertEqual(_actions(seek, "onup"), [(None, "200")])
        mini = _ids(self.windows["PlayerControls.xml"])["87"]
        self.assertEqual(_actions(mini, "onright"), [("!Player.Forwarding32x", "PlayerControl(Forward)")])
        self.assertEqual(_actions(mini, "onup"), [(None, "201")])
        sliders = [node for node in self.windows["VideoOSD.xml"].iter("control") if node.get("type") == "slider"]
        self.assertEqual(sorted(node.findtext("action") for node in sliders), ["pvr.seek", "seek"])

    @unittest.skipUnless(ESTUARY.is_dir(), "Kodi 22's bundled Estuary is not installed")
    def test_every_estuary_id_keeps_its_actions_and_visibility(self):
        bodies = expressions()
        for name in WINDOWS:
            estuary = _ids(_estuary_window(name))
            bald = _ids(self.windows[name])
            for control_id, old in estuary.items():
                with self.subTest(window=name, id=control_id):
                    self.assertIn(control_id, bald)
                    new = bald[control_id]
                    for tag in ACTION_TAGS:
                        self.assertTrue(same_actions(_actions(new, tag), _actions(old, tag), bodies),
                                        f"{tag}: {_actions(new, tag)} != {_actions(old, tag)}")
                    self.assertTrue(equivalent(all_of([v.text for v in new.findall("visible")]),
                                               all_of([v.text for v in old.findall("visible")]), bodies))

    @unittest.skipUnless(ESTUARY.is_dir(), "Kodi 22's bundled Estuary is not installed")
    def test_window_visibility_is_estuarys(self):
        bodies = expressions()
        for name in ("DialogSeekBar.xml", "Custom_1109_TopBarOverlay.xml", "PlayerControls.xml"):
            old = [v.text for v in ET.parse(ESTUARY / name).getroot().findall("visible")]
            new = [v.text for v in ET.parse(SKIN / name).getroot().findall("visible")]
            with self.subTest(window=name):
                self.assertTrue(equivalent(all_of(new), all_of(old), bodies))

    @unittest.skipUnless(ESTUARY.is_dir(), "Kodi 22's bundled Estuary is not installed")
    def test_overlay_states_match_estuarys_conditions(self):
        bodies = expressions()
        seekbar = ET.parse(ESTUARY / "DialogSeekBar.xml").getroot()
        bottom = seekbar.find("controls/control[@type='group']/visible").text
        self.assertTrue(equivalent("$EXP[Bald_PlaybackBottomBlock]", bottom, bodies))
        top = ET.parse(ESTUARY / "Custom_1109_TopBarOverlay.xml").getroot().findall("controls/control")
        self.assertTrue(equivalent("$EXP[Bald_PlaybackPauseHeader]", top[0].findtext("visible"), bodies))
        self.assertTrue(equivalent("$EXP[Bald_PlaybackTopChrome]", top[1].findtext("visible"), bodies))

    def test_no_window_adds_an_onback_previousmenu(self):
        for name in FILES:
            for node in ET.parse(SKIN / name).getroot().iter("onback"):
                with self.subTest(file=name):
                    self.assertNotIn("previousmenu", (node.text or "").lower().replace(" ", ""))

    def test_files_keep_the_estuary_notice(self):
        for name in FILES:
            if name == "Includes_Bald_Playback.xml":
                continue
            head = (SKIN / name).read_text(encoding="utf-8")[:1500]
            with self.subTest(file=name):
                self.assertIn("Estuary", head)
                self.assertIn("LICENSE-Estuary.txt", head)


class PlaybackStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        palette = ET.parse(ROOT / "colors" / "defaults.xml").getroot()
        cls.colors = {node.get("name") for node in palette if node.get("name", "").startswith("bald_")}
        fontset = ET.parse(SKIN / "Font.xml").getroot().find("fontset")
        cls.fonts = {node.findtext("name") for node in fontset.findall("font") if node.findtext("name").startswith("Bald_")}
        cls.roots = {name: ET.parse(SKIN / name).getroot() for name in FILES}

    def test_only_bald_fonts_and_colour_tokens(self):
        for name, root in self.roots.items():
            for node in root.iter():
                with self.subTest(file=name, tag=node.tag, text=node.text):
                    text = (node.text or "").strip()
                    if node.tag in ("font", "font2") and text:
                        self.assertIn(text, self.fonts)
                    if node.tag in COLOR_TAGS and text and "$PARAM" not in text:
                        self.assertIn(text, self.colors)
                    diffuse = node.get("colordiffuse")
                    if diffuse and "$PARAM" not in diffuse:
                        self.assertIn(diffuse, self.colors)
                    for value in [text] + list(node.attrib.values()):
                        for color in re.findall(r"\[COLOR\s*=?\s*([^\]]+)\]", value):
                            self.assertIn(color, self.colors)

    def test_colour_params_are_tokens(self):
        for name, root in self.roots.items():
            for node in root.iter("param"):
                value = node.get("value", node.text or "").strip()
                if node.get("name", "").endswith("color") and value and "$PARAM" not in value:
                    with self.subTest(file=name, param=node.get("name")):
                        self.assertIn(value, self.colors)

    def test_no_estuary_includes_or_coloured_variables(self):
        for name, root in self.roots.items():
            for node in root.iter("include"):
                call = node.get("content") or (node.text or "").strip()
                if node.get("file") or not call:
                    continue
                with self.subTest(file=name, include=call):
                    self.assertTrue(call.startswith("Bald_") or call in SHARED_INCLUDES
                                    or call.startswith("SettingsDialog"), call)
            text = (SKIN / name).read_text(encoding="utf-8")
            for variable in re.findall(r"\$VAR\[([^\],]+)", text):
                with self.subTest(file=name, variable=variable):
                    self.assertTrue(variable.startswith("Bald_") or variable in SHARED_VARIABLES, variable)

    def test_estuary_colour_and_font_names_are_gone(self):
        estuary_colors = {node.get("name") for node in ET.parse(ROOT / "colors" / "defaults.xml").getroot()
                          if not node.get("name", "").startswith("bald_")}
        for name in FILES:
            text = (SKIN / name).read_text(encoding="utf-8")
            with self.subTest(file=name):
                self.assertIsNone(re.search(r"\bfont\d|font_clock|WeatherTemp", text))
                for color in estuary_colors:
                    self.assertNotRegex(text, rf'[>"]{color}[<"]|COLOR {color}\]')

    def test_osd_buttons_use_the_icon_button(self):
        for name in ("VideoOSD.xml", "MusicOSD.xml", "PlayerControls.xml"):
            root = resolve_window(name)
            for button in root.iter("control"):
                if button.get("type") != "radiobutton" or button.get("id") is None:
                    continue  # the popup surface's close mark has no id
                with self.subTest(window=name, id=button.get("id")):
                    self.assertEqual(button.findtext("texturefocus"), "bald/osd_focus.png")
                    self.assertEqual(button.find("texturefocus").get("colordiffuse"), "bald_accent")
                    self.assertIn(button.find("textureradiooffnofocus").get("colordiffuse"),
                                  ("bald_ink60", "bald_accent"))
                    self.assertEqual(button.findtext("width"), "64")

    def test_seek_track_is_thin_ink_with_an_accent_playhead(self):
        root = resolve_window("DialogSeekBar.xml")
        ids = _ids(root)
        for control_id in ("401", "403"):
            slider = ids[control_id]
            self.assertEqual(slider.findtext("textureslidernib"), "bald/slider_nib.png")
            self.assertEqual(slider.find("textureslidernib").get("colordiffuse"), "bald_accent")
            self.assertIn(slider.findtext("texturesliderbar"), (None, ""))
        lines = [node for node in root.iter("control") if node.findtext("texture") == "bald/bar.png"]
        self.assertTrue(lines)
        self.assertEqual({node.findtext("height") for node in lines}, {"4"})
        self.assertIn("bald_ink28", {node.find("texture").get("colordiffuse") for node in lines})
        played = [node for node in root.iter("control")
                  if node.get("type") == "progress" and node.findtext("info") == "Player.Progress"]
        self.assertEqual([node.find("midtexture").get("colordiffuse") for node in played], ["bald_ink"])

    def test_osd_sits_on_the_bottom_scrim_with_hints_on_the_hint_line(self):
        scrim, = expand_call("Bald_PlaybackScrim")
        self.assertEqual(scrim.findtext("texture"), "bald/scrim_info_b.png")
        self.assertEqual(scrim.find("texture").get("colordiffuse"), "bald_field")
        seekbar = ET.tostring(resolve_window("DialogSeekBar.xml"), encoding="unicode")
        self.assertIn("bald/scrim_info_b.png", seekbar)
        for name in ("VideoOSD.xml", "MusicOSD.xml"):
            groups = [node for node in resolve_window(name).iter("control")
                      if node.get("type") == "group" and node.findtext("top") == "954"]
            with self.subTest(window=name):
                self.assertEqual(len(groups), 1)

    def test_pause_header_has_homes_clock(self):
        root = resolve_window("Custom_1109_TopBarOverlay.xml")
        clocks = [node for node in root.iter("control") if node.findtext("font") == "Bald_Clock"]
        self.assertEqual(len(clocks), 1)
        self.assertEqual(clocks[0].findtext("label"), "$INFO[System.Time(hh:mm)]")

    def test_osd_settings_rows_use_the_settings_row(self):
        root = resolve_window("Custom_1101_SettingsDialog.xml")
        rows = [node for node in root.iter("control") if (node.get("id") or "").startswith("221")]
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(id=row.get("id")):
                self.assertEqual(row.findtext("font"), "Bald_Section")
                self.assertEqual(row.findtext("texturefocus"), "bald/menu_dot.png")
                self.assertEqual(row.findtext("height"), "56")


class PlaybackStringTests(unittest.TestCase):
    def test_playback_strings_are_defined_used_and_cited(self):
        po = PO.read_text(encoding="utf-8")
        table = {num: text for num, text in strings().items() if num in PLAYBACK_RANGE}
        self.assertTrue(table)
        uses = {}
        for path in SKIN.glob("*.xml"):
            for num in re.findall(r"\$LOCALIZE\[(\d+)\]", path.read_text(encoding="utf-8")):
                if int(num) in PLAYBACK_RANGE:
                    uses.setdefault(int(num), set()).add(path.name)
        self.assertEqual(sorted(uses), sorted(table), "every playback string is defined and used")
        for num in table:
            block = po.split(f'msgctxt "#{num}"')[0].rsplit("\n\n", 1)[-1]
            self.assertEqual(set(re.findall(r"^#: /1080i/(\S+)$", block, re.M)), uses[num], f"#{num}")
        texts = list(table.values())
        self.assertEqual(len(texts), len(set(texts)))


if __name__ == "__main__":
    unittest.main()
