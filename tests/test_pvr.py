"""Live TV windows restyled in Bald (Includes_Bald_PVR.xml): Kodi's contract survives and only Bald's look remains.

The windows started as Kodi 22 Estuary copies. These checks parse the XML (resolved through tests/kodi_includes.py
where the rendered result matters) rather than matching literal strings.
"""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from kodi_includes import Skin, resolve_constants
from skin_strings import PO, strings
from test_localization import literal_text, shown_texts


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
INCLUDES = XML / "Includes_Bald_PVR.xml"
WINDOWS = ("DialogPVRChannelsOSD.xml", "DialogPVRChannelGuide.xml", "DialogPVRInfo.xml", "DialogPVRGuideControls.xml",
           "MyPVRChannels.xml", "MyPVRRecordings.xml", "MyPVRTimers.xml", "MyPVRSearch.xml", "MyPVRProviders.xml",
           "DialogPVRRadioRDSInfo.xml", "DialogPVRChannelManager.xml", "DialogPVRGroupManager.xml")
LIST_WINDOWS = ("MyPVRChannels.xml", "MyPVRRecordings.xml", "MyPVRTimers.xml", "MyPVRSearch.xml",
                "MyPVRProviders.xml")
STRING_IDS = range(31660, 31680)

# Control ids Kodi 22's C++ binds (xbmc/pvr/windows and xbmc/pvr/dialogs, CGUIMediaWindow), or that Estuary's
# variables read, by window. Each must still exist, with the control type Kodi casts it to where that matters.
CONTRACT = {
    "DialogPVRChannelsOSD.xml": {"11": None},
    "DialogPVRChannelGuide.xml": {"11": None},
    "DialogPVRInfo.xml": {"4": None, "5": None, "6": None, "8": None, "9": None, "10": None, "11": None},
    "DialogPVRGuideControls.xml": {str(n): "button" for n in (600, 601, 602, 603, 604, 605,
                                                            70040, 70041, 70042, 70043, 70044, 70045)},
    "MyPVRChannels.xml": {"50": None, "3": None, "4": None, "28": None, "29": "label", "30": "label",
                          "6": "radiobutton", "31": "radiobutton", "9000": "grouplist"},
    "MyPVRRecordings.xml": {"50": None, "3": None, "4": None, "28": None, "29": "label", "30": "label",
                            "5": "radiobutton", "7": "radiobutton", "10": None, "9000": "grouplist"},
    "MyPVRTimers.xml": {"50": None, "3": None, "4": None, "28": None, "29": "label", "30": "label",
                        "8": "radiobutton", "9000": "grouplist"},
    "MyPVRSearch.xml": {"50": None, "3": None, "4": None, "28": None, "29": "label", "30": "label",
                        "9000": "grouplist"},
    "MyPVRProviders.xml": {"50": None, "3": None, "4": None, "28": None, "29": "label", "9000": "grouplist"},
    "DialogPVRRadioRDSInfo.xml": {},
    "DialogPVRChannelManager.xml": {"2": "label", "4": None, "5": None, "6": None, "7": "radiobutton", "8": "edit",
                                    "9": None, "12": "radiobutton", "13": "spincontrolex", "14": "radiobutton",
                                    "20": "list", "30": None, "31": None, "34": "togglebutton", "35": None},
    "DialogPVRGroupManager.xml": {"1": "label", "11": "list", "12": "list", "13": "list", "20": "label",
                                  "21": "label", "22": "label", "25": "radiobutton", "26": None, "27": None,
                                  "28": None, "29": None, "34": "togglebutton", "35": None},
}
CONTAINERS = {"list", "fixedlist", "wraplist", "panel"}

# Guide controls: every button still runs the EPG-grid action Estuary gave it.
GUIDE_ACTIONS = {
    "600": "PVR.EpgGridControl(FirstProgramme)", "601": "PVR.EpgGridControl(-12)",
    "602": "PVR.EpgGridControl(CurrentProgramme)", "603": "PVR.EpgGridControl(+12)",
    "604": "PVR.EpgGridControl(LastProgramme)", "605": "PVR.EpgGridControl(SelectDate)",
    "70040": "PVR.EpgGridControl(FirstChannel)", "70041": "PVR.EpgGridControl(PlayingChannel)",
    "70042": "PVR.EpgGridControl(LastChannel)", "70043": "PVR.EpgGridControl(PreviousGroup)",
    "70044": "PVR.EpgGridControl(NextGroup)", "70045": "PVR.EpgGridControl(SelectGroup)",
}

COLOR_TAGS = {"textcolor", "focusedcolor", "disabledcolor", "selectedcolor", "shadowcolor", "invalidcolor",
              "textcolor2", "focusedcolor2", "colordiffuse"}
TEXT_CONTROLS = {"label", "textbox", "button", "radiobutton", "togglebutton", "edit", "spincontrolex"}
ALLOWED_TWEENS = {("cubic", "out"), ("sine", "inout"), ("back", "out")}


def colors():
    root = ET.parse(ROOT / "colors" / "defaults.xml").getroot()
    return {node.get("name") for node in root.iter("color")}


def fonts():
    root = ET.parse(XML / "Font.xml").getroot()
    return {node.findtext("name") for node in root.iter("font")}


BALD_COLORS = {name for name in colors() if name.startswith("bald_")}
ESTUARY_COLORS = colors() - BALD_COLORS
BALD_FONTS = {name for name in fonts() if name.startswith("Bald_")}
ESTUARY_FONTS = fonts() - BALD_FONTS


# The shared Bald popup surface (Includes.xml) is themed and tested with the popup theme (tests/test_popup_theme.py);
# the managers' style checks cover what they draw inside it.
SHARED_SURFACE = {"DialogBackgroundCommons"}


def resolved(name, without=()):
    """The window as Kodi expands it, optionally leaving out calls to the named includes."""
    root = ET.parse(XML / name).getroot()
    for parent in list(root.iter()):
        for call in [child for child in parent if child.tag == "include"
                     and (child.get("content") or (child.text or "").strip()) in without]:
            parent.remove(call)
    Skin()._resolve(root)
    return resolve_constants(root)


def styled(name):
    return resolved(name, SHARED_SURFACE)


def raw(name):
    return ET.parse(XML / name).getroot()


def controls(root):
    return [node for node in root.iter("control")]


def hidden(control):
    """Kodi-bound controls parked off-screen (HiddenObject) or never visible draw nothing."""
    return control.findtext("left", "").strip() == "-3000" or control.findtext("visible", "").strip() == "false"


class ContractTests(unittest.TestCase):
    def test_native_ids_are_present_with_their_types(self):
        for name, ids in CONTRACT.items():
            found = {}
            for node in controls(resolved(name)):
                found.setdefault(node.get("id"), node.get("type"))
            for control_id, kind in ids.items():
                with self.subTest(window=name, id=control_id):
                    self.assertIn(control_id, found)
                    if kind:
                        self.assertEqual(found[control_id], kind)

    def test_views_and_menu_control(self):
        for name in LIST_WINDOWS:
            root = raw(name)
            with self.subTest(window=name):
                self.assertEqual(root.findtext("views"), "50")
                self.assertEqual([node.text for node in root.findall("menucontrol")], ["9000"])
                self.assertEqual(root.findtext("defaultcontrol"), "50")
                view = [node for node in controls(resolved(name)) if node.get("id") == "50"]
                self.assertEqual(len(view), 1)
                self.assertIn(view[0].get("type"), CONTAINERS)
                self.assertIsNotNone(view[0].find("viewtype"))
                self.assertEqual(view[0].findtext("onleft"), "9000")

    def test_item_views_over_video_keep_list_eleven(self):
        for name in ("DialogPVRChannelsOSD.xml", "DialogPVRChannelGuide.xml"):
            root = resolved(name)
            with self.subTest(window=name):
                self.assertEqual(raw(name).findtext("defaultcontrol"), "11")
                view, = [node for node in controls(root) if node.get("id") == "11"]
                self.assertIn(view.get("type"), CONTAINERS)
                self.assertEqual(view.findtext("pagecontrol"), "60")

    def test_channel_switcher_keeps_the_group_actions(self):
        view, = [node for node in controls(resolved("DialogPVRChannelsOSD.xml")) if node.get("id") == "11"]
        self.assertEqual(view.findtext("onleft"), "PreviousChannelGroup")
        self.assertEqual(view.findtext("onright"), "NextChannelGroup")

    def test_guide_controls_run_the_same_actions(self):
        root = resolved("DialogPVRGuideControls.xml")
        for control_id, action in GUIDE_ACTIONS.items():
            node, = [node for node in controls(root) if node.get("id") == control_id]
            with self.subTest(id=control_id):
                self.assertEqual([click.text for click in node.findall("onclick")], [action])

    def test_skin_actions_survive(self):
        def clicks(name, control_id):
            node, = [node for node in controls(resolved(name)) if node.get("id") == control_id]
            return [click.text for click in node.findall("onclick")]

        self.assertIn("SendClick(28)", clicks("MyPVRChannels.xml", "9010"))
        self.assertEqual(clicks("MyPVRChannels.xml", "31"), ["right"])
        self.assertIn("ActivateWindow(videoplaylist)", clicks("MyPVRRecordings.xml", "302"))
        for name in LIST_WINDOWS:
            with self.subTest(window=name):
                self.assertEqual(clicks(name, "9020"), ["SendClick(3)"])
                self.assertEqual(clicks(name, "9021"), ["Container.SetSortDirection"])
        self.assertIn("ActivateWindow(1102)", clicks("DialogPVRInfo.xml", "138"))
        self.assertIn("ActivateWindow(1104)", clicks("DialogPVRInfo.xml", "102"))

    def test_info_actions_are_kodi_handled(self):
        # Kodi relabels and hides these by id; a skin onclick would run twice.
        root = resolved("DialogPVRInfo.xml")
        actions, = [node for node in controls(root) if node.get("id") == "5000"]
        ids = [node.get("id") for node in actions.findall("control")]
        self.assertEqual(ids, ["5", "10", "8", "6", "9", "11", "4", "102"])
        for node in actions.findall("control"):
            if node.get("id") != "102":
                self.assertEqual(node.findall("onclick"), [], node.get("id"))

    def test_no_onback_previousmenu(self):
        for name in WINDOWS:
            for node in resolved(name).iter("onback"):
                with self.subTest(window=name):
                    self.assertNotIn("previousmenu", (node.text or "").lower())
        for node in raw("../1080i/Includes_Bald_PVR.xml").iter("onback"):
            self.assertNotIn("previousmenu", (node.text or "").lower())


class StyleTests(unittest.TestCase):
    def color_values(self, root):
        for node in root.iter():
            if node.tag in COLOR_TAGS and (node.text or "").strip():
                yield node.tag, node.text.strip()
            if node.get("colordiffuse"):
                yield f"{node.tag}@colordiffuse", node.get("colordiffuse")
            for text in (node.text or "", *node.attrib.values()):
                for name in re.findall(r"\[COLOR ([^\]]+)\]", text):
                    yield f"{node.tag}[COLOR]", name

    def test_only_bald_colours(self):
        for name in (*WINDOWS, "Includes_Bald_PVR.xml"):
            root = raw(name) if name.startswith("Includes") else styled(name)
            for where, value in self.color_values(root):
                if value.startswith("$PARAM["):
                    continue  # checked where the include is used, in the resolved windows
                with self.subTest(file=name, where=where):
                    self.assertIn(value, BALD_COLORS)
                    self.assertNotIn(value, ESTUARY_COLORS)

    def test_only_bald_fonts(self):
        for name in (*WINDOWS, "Includes_Bald_PVR.xml"):
            root = raw(name) if name.startswith("Includes") else styled(name)
            for node in root.iter():
                if node.tag in ("font", "font2") and (node.text or "").strip():
                    with self.subTest(file=name, font=node.text):
                        self.assertIn(node.text.strip(), BALD_FONTS)
                        self.assertNotIn(node.text.strip(), ESTUARY_FONTS)

    def test_visible_text_sets_its_own_bald_font_and_colour(self):
        # Kodi's control defaults (Defaults.xml) are Estuary's; every drawn text control overrides them.
        for name in WINDOWS:
            for node in controls(styled(name)):
                if node.get("type") not in TEXT_CONTROLS or hidden(node):
                    continue
                if node.get("type") == "button" and not node.findtext("label", "").strip():
                    continue  # text-less hit areas (close-on-click background, the plot button over its textbox)
                with self.subTest(window=name, id=node.get("id"), type=node.get("type")):
                    self.assertIn(node.findtext("font", "").strip(), BALD_FONTS)
                    self.assertIn(node.findtext("textcolor", "").strip(), BALD_COLORS)

    def test_no_estuary_panels_or_focus_textures(self):
        # Estuary surfaces are replaced by Bald's field, scrims, pills and dots. Icons Kodi or Estuary supply
        # (status, lock) are allowed when tinted with a Bald token.
        for name in WINDOWS:
            for node in styled(name).iter():
                text = (node.text or "").strip()
                if not node.tag.startswith("texture") and node.tag not in ("midtexture", "texturebg", "bordertexture"):
                    continue
                if not text or text.startswith(("$", "bald/")):
                    continue
                with self.subTest(window=name, tag=node.tag, texture=text):
                    self.assertFalse(text.startswith(("buttons/", "dialogs/dialog-bg", "lists/", "frame/",
                                                      "colors/", "osd/")), text)
                    self.assertIn(node.get("colordiffuse"), BALD_COLORS)

    def test_motion_is_fade_slide_zoom_on_bald_curves(self):
        for name in (*WINDOWS, "Includes_Bald_PVR.xml"):
            for node in raw(name).iter():
                if node.tag == "animation" and node.get("effect"):
                    effects = [node]
                elif node.tag == "effect":
                    effects = [node]
                else:
                    continue
                for effect in effects:
                    kind = effect.get("effect") or effect.get("type")
                    with self.subTest(file=name, effect=kind):
                        self.assertIn(kind, ("fade", "slide", "zoom"))
                        if int(effect.get("time", "0")) > 0:
                            self.assertIn((effect.get("tween"), effect.get("easing")), ALLOWED_TWEENS)

    def test_progress_bars_use_the_accent(self):
        # Live progress in lists, the mini guide, the preview and the information dialog: accent over an ink track.
        found = 0
        for name in ("MyPVRChannels.xml", "DialogPVRChannelsOSD.xml", "DialogPVRChannelGuide.xml",
                     "DialogPVRInfo.xml"):
            for node in controls(resolved(name)):
                if node.get("type") == "progress" and node.findtext("info") == "ListItem.Progress":
                    found += 1
                    with self.subTest(window=name):
                        self.assertEqual(node.find("midtexture").get("colordiffuse"), "bald_accent")
                        self.assertEqual(node.find("texturebg").get("colordiffuse"), "bald_ink10")
        self.assertGreaterEqual(found, 4)

    def test_focused_rows_mark_focus_with_the_accent_dot(self):
        for name, list_id in (("MyPVRChannels.xml", "50"), ("MyPVRRecordings.xml", "50"),
                              ("DialogPVRChannelsOSD.xml", "11"), ("DialogPVRChannelGuide.xml", "11")):
            view, = [node for node in controls(resolved(name)) if node.get("id") == list_id]
            dots = [node for node in view.find("focusedlayout").iter("control")
                    if node.findtext("texture") == "bald/dot.png"]
            unfocused = [node for node in view.find("itemlayout").iter("control")
                         if node.findtext("texture") == "bald/dot.png" and "false" not in node.findtext("visible", "")]
            with self.subTest(window=name):
                self.assertTrue(dots)
                self.assertEqual(dots[0].find("texture").get("colordiffuse"), "bald_accent")
                # The item layout's dot, if any, is the timer mark, never the focus dot.
                self.assertTrue(all("HasTimer" in node.findtext("visible", "") for node in unfocused))


class StringTests(unittest.TestCase):
    def test_live_tv_strings_are_defined_used_and_cited(self):
        po = PO.read_text(encoding="utf-8")
        defined = {num: text for num, text in strings().items() if num in STRING_IDS}
        self.assertTrue(defined)
        uses = {}
        for path in XML.glob("*.xml"):
            for num in re.findall(r"\$LOCALIZE\[(\d+)\]", path.read_text(encoding="utf-8")):
                if int(num) in STRING_IDS:
                    uses.setdefault(int(num), set()).add(path.name)
        self.assertEqual(set(uses) - set(defined), set(), "undefined")
        self.assertEqual(set(defined) - set(uses), set(), "unused")
        texts = list(defined.values())
        self.assertEqual(sorted({t for t in texts if texts.count(t) > 1}), [], "one id per string")
        for num in defined:
            block = po.split(f'msgctxt "#{num}"')[0].rsplit("\n\n", 1)[-1]
            self.assertEqual(set(re.findall(r"^#: /1080i/(\S+)$", block, re.M)), uses[num], f"#{num}")

    def test_no_hardcoded_english(self):
        for name in WINDOWS:
            for where, text in shown_texts(raw(name)):
                with self.subTest(window=name, where=where):
                    self.assertNotRegex(literal_text(text), r"[A-Za-z]{2,}", text)


class GuideSeparationTests(unittest.TestCase):
    def test_restyled_windows_do_not_use_the_guide_parts(self):
        guide = {"Bald_EpgGrid", "Bald_PVRGuideTools", "Bald_PVRGuideToolButton"}
        for name in (*WINDOWS, "Includes_Bald_PVR.xml"):
            calls = {node.get("content") or (node.text or "").strip() for node in raw(name).iter("include")}
            with self.subTest(file=name):
                self.assertFalse(calls & guide)

    def test_bald_live_tv_includes_are_registered_after_the_estuary_pvr_file(self):
        files = [node.get("file") for node in ET.parse(XML / "Includes.xml").getroot().findall("include")
                 if node.get("file")]
        self.assertIn("Includes_Bald_PVR.xml", files)
        self.assertLess(files.index("Includes_PVR.xml"), files.index("Includes_Bald_PVR.xml"))


if __name__ == "__main__":
    unittest.main()
