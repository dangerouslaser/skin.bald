"""Media windows restyle (docs/NOTES.md, "Media windows restyle"): music, pictures, games, weather, the login screen
and three popup interiors keep Kodi's control contract and use only Bald tokens, fonts and surfaces."""
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from kodi_includes import SKIN, Skin
from test_localization import literal_text, shown_texts


ROOT = Path(__file__).resolve().parents[1]

# Control ids Kodi's C++ binds in each window (xbmc master, Kodi 22), checked in the resolved window. Ids Estuary
# never shipped and Kodi treats as optional are listed only where Bald now provides them.
NATIVE_IDS = {
    # CGUIDialogColorPicker: heading, swatch panel, cancel.
    "DialogColorPicker.xml": {"1", "6", "7"},
    # CGUIDialogMediaSource: heading, path list, browse, name, add, remove, OK, cancel.
    "DialogMediaSource.xml": {"2", "10", "11", "12", "13", "14", "18", "19"},
    # CGUIDialogVideoManager (+Versions, +Extras): title, list, play, remove, choose art, add/rename/default version,
    # add/rename extra.
    "DialogVideoManager.xml": {"2", "50", "21", "26", "27", "22", "24", "25", "23", "28"},
    # CGUIWindowLoginScreen: profile list, heading, selected-profile counter.
    "LoginScreen.xml": {"52", "2", "3"},
    # CGUIWindowSlideShow: the error-message font label.
    "SlideShow.xml": {"10"},
    # CGUIDialogPictureInfo: the details list.
    "DialogPictureInfo.xml": {"5"},
    # CGUIWindowVisualisation: the visualisation.
    "MusicVisualisation.xml": {"2"},
    # CGUIDialogMusicInfo: refresh, rating, play, choose art, artist/album info, list.
    "DialogMusicInfo.xml": {"6", "7", "8", "10", "12", "50"},
    # CDialogGameOSD / CDialogGameOSDHelp: menu and help text.
    "GameOSD.xml": {"1103", "1101"},
    # Controller, port and agent dialogs and the disc manager (games/*/windows/*Defines.h, DiscManagerIDs.h).
    "DialogGameControllers.xml": {"2", "3", "4", "5", "7", "8", "9", "10", "17", "18", "19", "20", "21", "22", "31", "32", "108321"},
}
# Kodi reads these control types by id, so the type must stay what Kodi casts to.
NATIVE_TYPES = {
    ("DialogMusicInfo.xml", "50"): "panel",
    ("DialogPictureInfo.xml", "5"): "list",
    ("LoginScreen.xml", "52"): "fixedlist",
    ("MusicVisualisation.xml", "2"): "visualisation",
    ("SlideShow.xml", "10"): "label",
    ("DialogColorPicker.xml", "6"): "panel",
    ("DialogMediaSource.xml", "12"): "edit",
}

# Files this stream restyled; every colour, font and chrome texture in them is Bald's.
RESTYLED = sorted(NATIVE_IDS) + [
    "Includes_Bald_Media.xml",
    "Includes_MusicInfo.xml",
    "Includes_Games.xml",
]
COLOR_TAGS = {"textcolor", "focusedcolor", "disabledcolor", "invalidcolor", "selectedcolor", "shadowcolor",
              "colordiffuse", "controllerdiffuse"}
TEXT_CONTROLS = {"label", "fadelabel", "textbox", "edit"}
# Estuary chrome textures replaced by Bald surfaces. Estuary icons stay (tinted), per the Bald brief.
ESTUARY_CHROME = re.compile(r"^(dialogs/|buttons/(dialog)?button-|lists/focus|colors/|overlays/|spinner)")
DYNAMIC = re.compile(r"\$(INFO|VAR|PARAM|ESCINFO)\[")


def tokens():
    root = ET.parse(ROOT / "colors" / "defaults.xml").getroot()
    return {node.get("name") for node in root.iter("color") if node.get("name", "").startswith("bald_")}


def fonts():
    root = ET.parse(SKIN / "Font.xml").getroot()
    return {node.text for node in root.iter("name") if (node.text or "").startswith("Bald_")}


def colours_in(root):
    """(where, value) for every colour a file names: colour tags, colordiffuse attributes and [COLOR x] tags."""
    for node in root.iter():
        if node.tag in COLOR_TAGS and (node.text or "").strip():
            yield node.tag, node.text.strip()
        if node.get("colordiffuse"):
            yield f"{node.tag}@colordiffuse", node.get("colordiffuse")
        for text in (node.text or "", *(node.attrib.values())):
            for name in re.findall(r"\[COLOR=?\s*([^\]]+)\]", text):
                yield "[COLOR]", name.strip()


class NativeContractTests(unittest.TestCase):
    def test_native_ids_are_present(self):
        for name, ids in NATIVE_IDS.items():
            root = Skin().window(name)
            present = {node.get("id") for node in root.iter("control")}
            with self.subTest(window=name):
                self.assertEqual(ids - present, set())

    def test_native_control_types(self):
        for (name, control_id), kind in NATIVE_TYPES.items():
            root = Skin().window(name)
            types = {node.get("type") for node in root.iter("control") if node.get("id") == control_id}
            with self.subTest(window=name, id=control_id):
                self.assertEqual(types, {kind})

    def test_disc_manager_keeps_its_menu_template(self):
        # DiscManagerIDs.h: menu 3 is built from items 108323-108327 in this order.
        root = ET.parse(SKIN / "Includes_Games.xml").getroot()
        menu = next(node for node in root.iter("control") if node.get("id") == "3"
                    and node.find("content/item[@id='108323']") is not None)
        self.assertEqual([item.get("id") for item in menu.findall("content/item")],
                         ["108323", "108324", "108325", "108326", "108327"])

    def test_music_info_leaves_kodi_managed_visibility_alone(self):
        # Kodi shows and hides 7, 8 and 12 itself; a <visible> on them would override it every frame.
        root = Skin().window("DialogMusicInfo.xml")
        for node in root.iter("control"):
            if node.get("id") in ("7", "8", "12"):
                visible = [v.text for v in node.findall("visible")]
                with self.subTest(id=node.get("id")):
                    self.assertTrue(all((v or "").strip() in ("", "true") for v in visible), visible)

    def test_no_onback_previousmenu(self):
        for name in NATIVE_IDS:
            root = Skin().window(name)
            with self.subTest(window=name):
                self.assertFalse([n for n in root.iter("onback") if "previousmenu" in (n.text or "").lower()])


class BaldLookTests(unittest.TestCase):
    def test_only_bald_colour_tokens(self):
        known = tokens()
        for name in RESTYLED:
            root = ET.parse(SKIN / name).getroot()
            for where, value in colours_in(root):
                if DYNAMIC.search(value):
                    continue
                with self.subTest(file=name, where=where):
                    self.assertIn(value, known)

    def test_only_bald_fonts(self):
        known = fonts()
        for name in RESTYLED:
            root = ET.parse(SKIN / name).getroot()
            for node in root.iter("font"):
                value = (node.text or "").strip()
                if value.startswith("$PARAM["):
                    continue
                with self.subTest(file=name, font=value):
                    self.assertIn(value, known)

    def test_text_controls_name_their_font_and_colour(self):
        # Defaults.xml still gives an unstyled label Estuary's font13 in white.
        for name in RESTYLED:
            root = ET.parse(SKIN / name).getroot()
            for node in root.iter("control"):
                if node.get("type") not in TEXT_CONTROLS or node.find("include") is not None:
                    continue
                with self.subTest(file=name, id=node.get("id"), label=node.findtext("label")):
                    self.assertIsNotNone(node.find("font"))
                    self.assertIsNotNone(node.find("textcolor"))

    def test_no_estuary_chrome_textures(self):
        for name in RESTYLED:
            root = ET.parse(SKIN / name).getroot()
            for node in root.iter():
                if not node.tag.startswith("texture") and node.tag != "bordertexture":
                    continue
                with self.subTest(file=name, texture=node.text):
                    self.assertNotRegex((node.text or "").strip(), ESTUARY_CHROME)

    def test_scrollbars_use_the_bald_track(self):
        for name in NATIVE_IDS:
            root = Skin().window(name)
            for node in root.iter("control"):
                if node.get("type") != "scrollbar":
                    continue
                with self.subTest(window=name, id=node.get("id")):
                    self.assertEqual(node.findtext("texturesliderbar"), "bald/white.png")
                    self.assertEqual(node.findtext("width"), "4")

    def test_window_text_is_localized(self):
        for name in RESTYLED:
            root = ET.parse(SKIN / name).getroot()
            for where, text in shown_texts(root):
                with self.subTest(file=name, where=where):
                    # $FEATURE[feature,controller] names a controller button, not text.
                    shown = literal_text(re.sub(r"\$FEATURE\[[^\]]*\]", "", text))
                    self.assertNotRegex(shown, r"[A-Za-z]{2,}", text)

    def test_estuary_origin_is_credited(self):
        for name in RESTYLED:
            if not name.startswith("Includes_Bald_"):
                with self.subTest(file=name):
                    self.assertIn("Estuary", (SKIN / name).read_text(encoding="utf-8")[:1500])

    def test_media_includes_are_registered(self):
        registered = [node.get("file") for node in ET.parse(SKIN / "Includes.xml").getroot().findall("include")]
        self.assertIn("Includes_Bald_Media.xml", registered)


if __name__ == "__main__":
    unittest.main()
