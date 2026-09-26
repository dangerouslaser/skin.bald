"""Kodi's own settings windows drawn in Bald's settings scaffold: the control ids Kodi binds, the templates it clones,
and the scaffold's tokens, fonts and motion. Checks structure, not XML spelling."""

import unittest
import xml.etree.ElementTree as ET

from kodi_includes import SKIN, include_definitions, resolve_window

ROOT = SKIN.parent

# Control ids Kodi binds by number, with the control type each must be. Sources (xbmc master, Kodi 22):
# settings/dialogs/GUIDialogSettingsBase.{h,cpp}, settings/windows/GUIWindowSettingsCategory.cpp.
CATEGORY_CONTRACT = {
    "2": "label",           # CONTROL_SETTINGS_LABEL: heading
    "3": "grouplist",       # CATEGORY_GROUP_ID
    "5": "grouplist",       # SETTINGS_GROUP_ID
    "6": "textbox",         # CONTROL_SETTINGS_DESCRIPTION
    "7": "button",          # CONTROL_DEFAULT_BUTTON
    "8": "radiobutton",     # CONTROL_DEFAULT_RADIOBUTTON
    "9": "spincontrolex",   # CONTROL_DEFAULT_SPIN
    "10": "button",         # CONTROL_DEFAULT_CATEGORY_BUTTON
    "11": "image",          # CONTROL_DEFAULT_SEPARATOR
    "12": "edit",           # CONTROL_DEFAULT_EDIT
    "13": "sliderex",       # CONTROL_DEFAULT_SLIDER
    "14": "label",          # CONTROL_DEFAULT_SETTING_LABEL: group title
    "15": "colorbutton",    # CONTROL_DEFAULT_COLORBUTTON
    "20": "radiobutton",    # CONTROL_BTN_LEVELS
}
# Setting templates Kodi clones into grouplist 5, one per setting.
ROW_TEMPLATES = ("7", "8", "9", "12", "13", "15")

# Motion (CLAUDE.md): move = cubic out, fade = sine in-out, pop = back out. Only fade, slide and zoom.
CURVES = {"fade": ("sine", "inout"), "slide": ("cubic", "out"), "zoom": ("back", "out")}

WINDOWS = ("SettingsCategory.xml",)


def tokens(path, tag):
    return {node.findtext("name") if tag == "font" else node.get("name")
            for node in ET.parse(path).getroot().iter(tag)}


class NativeSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        definitions = include_definitions()
        cls.windows = {name: resolve_window(name, definitions) for name in WINDOWS}
        cls.fonts = tokens(SKIN / "Font.xml", "font")
        cls.colors = {name for name in tokens(ROOT / "colors" / "defaults.xml", "color") if name.startswith("bald_")}

    def controls(self, window, control_id):
        return [node for node in self.windows[window].iter("control") if node.get("id") == control_id]

    def control(self, window, control_id):
        found = self.controls(window, control_id)
        self.assertEqual(len(found), 1, f"{window}: control {control_id} appears {len(found)} times")
        return found[0]

    # ---- Kodi's contract ----

    def test_settings_pages_keep_every_id_kodi_binds(self):
        for control_id, kind in CATEGORY_CONTRACT.items():
            with self.subTest(id=control_id):
                self.assertEqual(self.control("SettingsCategory.xml", control_id).get("type"), kind)

    def test_level_button_cycles_the_settings_level(self):
        level = self.control("SettingsCategory.xml", "20")
        self.assertEqual([node.text for node in level.findall("onclick")], ["SettingsLevelChange"])
        # It must not show a radio state: the first of each radio texture (the one Kodi reads) is empty.
        for tag in ("textureradioonfocus", "textureradioonnofocus", "textureradioofffocus", "textureradiooffnofocus"):
            self.assertFalse((level.findtext(tag) or "").strip(), tag)

    def test_heading_is_the_sidebar_title(self):
        controls = self.windows["SettingsCategory.xml"].find("controls")
        title = controls.find("control[@type='label']")
        self.assertEqual(title.get("id"), "2")
        self.assertEqual((title.findtext("left"), title.findtext("top")), ("96", "96"))

    def test_grouplists_scroll_the_settings_and_categories(self):
        settings = self.control("SettingsCategory.xml", "5")
        self.assertEqual(settings.findtext("orientation"), "vertical")
        self.assertEqual(settings.findtext("pagecontrol"), "60")
        self.assertEqual(self.control("SettingsCategory.xml", "60").get("type"), "scrollbar")
        self.assertEqual(settings.findtext("onleft"), "3")
        self.assertEqual(self.control("SettingsCategory.xml", "3").findtext("onright"), "5")

    # ---- The templates Kodi clones ----

    def test_setting_rows_share_the_scaffold_row(self):
        looks = set()
        for control_id in ROW_TEMPLATES:
            template = self.control("SettingsCategory.xml", control_id)
            focus = template.find("texturefocus")
            look = (template.findtext("font"), template.findtext("height"), template.findtext("textoffsetx"),
                    template.findtext("textcolor"), template.findtext("focusedcolor"), template.findtext("disabledcolor"),
                    focus.text, focus.get("colordiffuse"), (template.findtext("texturenofocus") or "").strip())
            looks.add(look)
        self.assertEqual(looks, {("Bald_Section", "56", "26", "bald_ink45", "bald_ink", "bald_ink28",
                                  "bald/menu_dot.png", "bald_accent", "")})

    def test_rows_fill_the_settings_pane(self):
        width = self.control("SettingsCategory.xml", "5").findtext("width")
        for control_id in ROW_TEMPLATES + ("14",):
            self.assertEqual(self.control("SettingsCategory.xml", control_id).findtext("width"), width, control_id)

    def test_toggle_state_is_the_right_hand_dot(self):
        radio = self.control("SettingsCategory.xml", "8")
        self.assertEqual(radio.find("textureradioonnofocus").get("colordiffuse"), "bald_accent")
        self.assertEqual(radio.findtext("textureradiooffnofocus"), "bald/dot.png")
        self.assertIsNotNone(radio.find("textureradiooffdisabled"))

    def test_spinner_and_slider_have_bald_parts(self):
        spinner = self.control("SettingsCategory.xml", "9")
        for tag in ("textureup", "texturedown", "textureupfocus", "texturedownfocus",
                    "textureupdisabled", "texturedowndisabled"):
            self.assertEqual(spinner.findtext(tag), "bald/chevron.png", tag)
        self.assertEqual(spinner.find("texturedown").get("flipx"), "true")
        self.assertIsNone(spinner.find("textureup").get("flipx"))

        slider = self.control("SettingsCategory.xml", "13")
        self.assertEqual(slider.findtext("texturesliderbar"), "bald/slider_bar.png")
        self.assertEqual(slider.findtext("textureslidernib"), "bald/slider_nib.png")
        self.assertIsNotNone(slider.find("texturesliderbardisabled"))
        self.assertIsNotNone(slider.find("textureslidernibdisabled"))
        # Kodi scales the nib by the slider height over the track texture's height: equal heights keep it 16 px.
        self.assertEqual(slider.findtext("sliderheight"), "16")

    def test_category_button_is_a_sidebar_row(self):
        button = self.control("SettingsCategory.xml", "10")
        self.assertEqual(button.findtext("font"), "Bald_MenuItem")
        self.assertEqual(button.findtext("textcolor"), "bald_ink34")
        self.assertEqual(button.findtext("texturefocus"), "bald/menu_dot.png")
        group = self.control("SettingsCategory.xml", "3")
        # 56 px buttons and a 6 px gap: the scaffold list's 62 px pitch.
        self.assertEqual(int(button.findtext("height")) + int(group.findtext("itemgap")), 62)
        self.assertEqual(group.findtext("width"), button.findtext("width"))

    def test_group_titles_and_separators_are_quiet(self):
        title = self.control("SettingsCategory.xml", "14")
        self.assertTrue(title.findtext("font").startswith("Bald_"))
        self.assertEqual(title.findtext("textcolor"), "bald_ink60")
        separator = self.control("SettingsCategory.xml", "11")
        self.assertEqual(separator.find("texture").get("colordiffuse"), "bald_ink10")

    # ---- Scaffold conventions ----

    def test_no_back_overrides(self):
        # Kodi's Back retraces window history (and saves the settings); PreviousMenu would jump to Home.
        for name, root in self.windows.items():
            self.assertEqual([node.text for node in root.iter("onback")], [], name)

    def test_only_bald_fonts_and_colors(self):
        for name, root in self.windows.items():
            for node in root.iter("font"):
                self.assertIn(node.text, self.fonts, f"{name}: {node.text}")
                self.assertTrue(node.text.startswith("Bald_"), f"{name}: {node.text}")
            for tag in ("textcolor", "focusedcolor", "disabledcolor", "invalidcolor", "selectedcolor", "shadowcolor",
                        "colordiffuse", "backgroundcolor"):
                for node in root.iter(tag):
                    self.assertIn(node.text, self.colors, f"{name}: {tag} {node.text}")
            for node in root.iter():
                if "colordiffuse" in node.attrib:
                    self.assertIn(node.get("colordiffuse"), self.colors, f"{name}: <{node.tag}> {node.get('colordiffuse')}")

    def test_textures_are_bald_textures_that_exist(self):
        texture_tags = {"texture", "texturefocus", "texturenofocus", "textureup", "texturedown", "textureupfocus",
                        "texturedownfocus", "textureupdisabled", "texturedowndisabled", "texturesliderbar",
                        "texturesliderbardisabled", "textureslidernib", "textureslidernibfocus",
                        "textureslidernibdisabled", "texturesliderbackground", "texturesliderbarfocus",
                        "texturecolormask", "texturecolordisabledmask"}
        for name, root in self.windows.items():
            for node in root.iter():
                is_texture = node.tag in texture_tags or node.tag.startswith("textureradio")
                path = (node.text or "").strip()
                if not is_texture or not path or path.startswith("$"):
                    continue
                self.assertTrue(path.startswith("bald/"), f"{name}: <{node.tag}> {path}")
                self.assertTrue((ROOT / "media" / path).is_file(), f"{name}: {path} is missing")

    def test_motion_uses_the_spec_curves(self):
        for name, root in self.windows.items():
            for animation in root.iter("animation"):
                effects = animation.findall("effect") or [animation]
                for effect in effects:
                    kind = effect.get("effect") if effect is animation else effect.get("type")
                    self.assertIn(kind, CURVES, f"{name}: {kind}")
                    self.assertEqual((effect.get("tween"), effect.get("easing")), CURVES[kind], f"{name}: {kind}")

    def test_hints_sit_on_the_hint_line(self):
        for name, root in self.windows.items():
            hints = [group for group in root.iter("control")
                     if group.get("type") == "group" and group.findtext("top") == "954"]
            self.assertEqual(len(hints), 1, name)
            self.assertEqual(int(hints[0].findtext("left")) + int(hints[0].find("control").findtext("width")), 1824)

    def test_estuary_chrome_is_gone(self):
        for name, root in self.windows.items():
            text = (SKIN / name).read_text(encoding="utf-8") + ET.tostring(root, encoding="unicode")
            for estuary in ("DefaultBackground", "TopBar", "BottomBar", "OpenClose_", "ContentPanel", "button_focus"):
                self.assertNotIn(estuary, text, name)
            self.assertEqual(root.findtext("backgroundcolor"), "bald_field", name)


if __name__ == "__main__":
    unittest.main()
