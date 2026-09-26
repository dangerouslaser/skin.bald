"""Shared foundations: control defaults, select dialog layouts, shared buttons, label colour markup and the colour
file. They keep Kodi's contracts and use only Bald's fonts and colour tokens."""
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from kodi_includes import SKIN, expand_call, resolve_window


ROOT = SKIN.parent
COLORS = ROOT / "colors"
COLOR_TAGS = {"textcolor", "focusedcolor", "disabledcolor", "selectedcolor", "shadowcolor", "invalidcolor",
              "textcolor2", "focusedcolor2", "controllerdiffuse"}
COLOR_ATTRS = {"colordiffuse"}
MARKUP = re.compile(r"\[COLOR[ =]([^\]]+)\]")
# Files this stream restyled as a whole; Variables.xml is checked for its label colour markup only.
RESTYLED = ("Defaults.xml", "Includes_DialogSelect.xml", "Includes_Bald_Foundations.xml", "Includes_Buttons.xml")


def palette():
    return {node.get("name"): node.text for node in ET.parse(COLORS / "defaults.xml").getroot()}


def font_names():
    fontset = ET.parse(SKIN / "Font.xml").getroot().find("fontset")
    return {node.findtext("name") for node in fontset.findall("font")}


def is_dynamic(value):
    return "$" in value


def colour_uses(root):
    """(value, where) for every colour a file names: colour tags, colordiffuse attributes, colour params and label
    [COLOR] markup. Empty values and $PARAM/$VAR/$INFO references are left out."""
    uses = []
    for node in root.iter():
        values = []
        if node.tag in COLOR_TAGS and node.text:
            values.append(node.text.strip())
        values += [value for key, value in node.attrib.items() if key in COLOR_ATTRS]
        if node.tag == "param" and "color" in (node.get("name") or ""):
            values.append(node.get("value", node.text or ""))
        for text in [node.text or ""] + list(node.attrib.values()):
            values += MARKUP.findall(text)
        uses += [(value, node.tag) for value in values if value and not is_dynamic(value)]
    return uses


def font_uses(root):
    uses = [node.text.strip() for node in root.iter("font") if node.text and node.text.strip()]
    uses += [node.get("value", node.text or "") for node in root.iter("param") if node.get("name") == "font"]
    return [value for value in uses if value and not is_dynamic(value)]


class ColourFileTests(unittest.TestCase):
    def test_only_the_bald_palette_is_offered(self):
        # Kodi lists every colors/*.xml under Skin colours; Estuary's themes defined no bald_* token.
        self.assertEqual([path.name for path in COLORS.glob("*.xml")], ["defaults.xml"])

    def test_every_colour_name_the_skin_uses_is_defined(self):
        defined = set(palette())
        for path in sorted(SKIN.glob("*.xml")):
            for value, tag in colour_uses(ET.parse(path).getroot()):
                if re.fullmatch(r"[0-9A-Fa-f]{8}", value):
                    continue
                with self.subTest(file=path.name, colour=value):
                    self.assertIn(value, defined)


class RestyledFileTests(unittest.TestCase):
    def test_restyled_files_use_only_bald_tokens(self):
        tokens = {name for name in palette() if name.startswith("bald_")}
        for name in RESTYLED:
            for value, tag in colour_uses(ET.parse(SKIN / name).getroot()):
                with self.subTest(file=name, tag=tag, colour=value):
                    self.assertIn(value, tokens)

    def test_restyled_files_use_only_bald_fonts(self):
        bald = {name for name in font_names() if name.startswith("Bald_")}
        for name in RESTYLED:
            for value in font_uses(ET.parse(SKIN / name).getroot()):
                with self.subTest(file=name, font=value):
                    self.assertIn(value, bald)

    def test_variables_label_markup_uses_bald_tokens(self):
        tokens = {name for name in palette() if name.startswith("bald_")}
        root = ET.parse(SKIN / "Variables.xml").getroot()
        found = [value for node in root.iter("value") for value in MARKUP.findall(node.text or "")]
        self.assertTrue(found)
        for value in found:
            with self.subTest(colour=value):
                self.assertIn(value, tokens)

    def test_no_previousmenu_on_back(self):
        # docs/NOTES.md: PreviousMenu behaves like Escape in Kodi 22.
        for name in RESTYLED + ("DialogSelect.xml", "Variables.xml"):
            for node in ET.parse(SKIN / name).getroot().iter("onback"):
                with self.subTest(file=name):
                    self.assertNotIn("previousmenu", (node.text or "").lower())

    def test_restyled_estuary_files_keep_their_licence_header(self):
        for name in ("Defaults.xml", "Includes_DialogSelect.xml", "Includes_Buttons.xml"):
            with self.subTest(file=name):
                text = (SKIN / name).read_text()
                self.assertIn("Estuary", text[:600])
                self.assertIn("LICENSE-Estuary.txt", text[:600])


class DefaultsTests(unittest.TestCase):
    def defaults(self):
        return {node.get("type"): node for node in ET.parse(SKIN / "Defaults.xml").getroot().findall("default")}

    def test_text_controls_default_to_bald_fonts_and_ink(self):
        defaults = self.defaults()
        for kind in ("label", "fadelabel", "textbox", "button", "togglebutton", "radiobutton", "spincontrolex",
                     "sliderex", "edit", "colorbutton", "spincontrol"):
            with self.subTest(type=kind):
                self.assertTrue(defaults[kind].findtext("font").startswith("Bald_"))
                self.assertTrue(defaults[kind].findtext("textcolor").startswith("bald_ink"))

    def test_labels_and_buttons_have_no_default_focused_colour(self):
        # Kodi draws focused text in textcolor when focusedcolor is unset, and list labels in a focused layout use
        # focusedcolor: a default here would recolour every focused list row and every button that brings its own
        # focus texture.
        defaults = self.defaults()
        for kind in ("label", "fadelabel", "textbox", "button", "togglebutton"):
            with self.subTest(type=kind):
                self.assertIsNone(defaults[kind].find("focusedcolor"))

    def test_settings_spinner_direction_is_kept(self):
        # SettingsCategory's spinner (9) takes reverse from the default.
        self.assertEqual(self.defaults()["spincontrolex"].findtext("reverse"), "yes")

    def test_keyboard_keys_keep_their_text_offset(self):
        key, = [node for node in ET.parse(SKIN / "Includes_Buttons.xml").getroot().findall("include")
                if node.get("name") == "Bald_KeyboardButton"]
        self.assertEqual(key.findtext("textoffsetx"), "7")


class SelectDialogTests(unittest.TestCase):
    def test_native_ids_are_present(self):
        root = resolve_window("DialogSelect.xml")
        ids = {node.get("id") for node in root.iter("control")}
        # CGUIDialogSelect; CDialogGameSaves; CDialogGameVideoSelect.
        for control_id in ("1", "3", "5", "6", "7", "8", "61", "9001",
                           "10820", "10822", "10823", "10824", "10825", "10826", "10828",
                           "10811", "10812"):
            with self.subTest(id=control_id):
                self.assertIn(control_id, ids)
        types = {node.get("id"): node.get("type") for node in root.iter("control") if node.get("id")}
        self.assertEqual(types["61"], "scrollbar")
        self.assertIn(types["6"], ("list", "fixedlist"))
        self.assertEqual(types["10812"], "textbox")

    def test_select_lists_keep_their_navigation(self):
        root = resolve_window("DialogSelect.xml")
        for node in root.iter("control"):
            if node.get("id") in ("3", "6") and node.get("type") != "panel":
                with self.subTest(id=node.get("id")):
                    self.assertEqual(node.findtext("onleft"), "9001")
                    self.assertEqual(node.findtext("onright"), "61")
                    self.assertEqual(node.findtext("pagecontrol"), "61")

    def test_stream_rows_use_the_popup_list_look(self):
        fixedlist, = expand_call("Bald_SelectStreamList", {"width": "930", "label": "a", "label2": "b"})
        item, focused = fixedlist.find("itemlayout"), fixedlist.find("focusedlayout")
        self.assertEqual([node.findtext("textcolor") for node in item.iter("control") if node.get("type") == "label"],
                         ["bald_ink70", "bald_ink45"])
        self.assertEqual([node.findtext("textcolor") for node in focused.iter("control")
                          if node.get("type") == "label"], ["bald_ink", "bald_ink60"])
        surfaces = [node.find("texture") for node in focused.iter("control") if node.get("type") == "image"]
        self.assertIn(("bald/white.png", "bald_ink10"), {(tex.text, tex.get("colordiffuse")) for tex in surfaces})

    def test_game_video_tiles_keep_the_live_preview(self):
        root = resolve_window("DialogSelect.xml")
        panels = [node for node in root.iter("control") if node.get("id") == "10811"]
        self.assertEqual(len(panels), 4)  # the view layout serves stretch mode and rotation
        for panel in panels:
            for layout in ("itemlayout", "focusedlayout"):
                with self.subTest(layout=layout):
                    self.assertEqual(len([node for node in panel.find(layout).iter("control")
                                          if node.get("type") == "gamewindow"]), 1)


if __name__ == "__main__":
    unittest.main()
