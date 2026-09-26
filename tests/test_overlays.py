"""Global overlays (busy, toasts, background progress, volume, text viewer, power menu): Kodi's contracts and Bald's look.

Windows are checked as Kodi builds them, with every include expanded, so the rules cover the shared overlay includes too.
"""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from kodi_includes import SKIN, Skin
from skin_strings import strings


ROOT = SKIN.parent
RESTYLED = ("DialogBusy.xml", "DialogNotification.xml", "DialogExtendedProgressBar.xml", "DialogVolumeBar.xml",
            "Custom_1103_VolumeSlider.xml", "Custom_1102_TextViewer.xml", "DialogTextViewer.xml")
CHECKED = RESTYLED + ("DialogButtonMenu.xml",)

# Control ids Kodi's C++ binds (or the skin's own wiring relies on), with the control type each must be.
CONTRACTS = {
    # CGUIDialogKaiToast: POPUP_ICON, POPUP_CAPTION_TEXT, POPUP_NOTIFICATION_BUTTON (a fadelabel: Kodi waits for it).
    "DialogNotification.xml": {"400": "image", "401": "fadelabel", "402": "fadelabel"},
    # CGUIDialogExtendedProgressBar: CONTROL_LABELHEADER, CONTROL_LABELTITLE, CONTROL_PROGRESS.
    "DialogExtendedProgressBar.xml": {"30": "label", "31": "label", "32": "progress"},
    # CGUIDialogTextViewer: CONTROL_HEADING, CONTROL_TEXTAREA; 1000/3000 are the skin's focus holder and page control.
    "DialogTextViewer.xml": {"1": "label", "5": "textbox", "1000": "button", "3000": "scrollbar"},
    "Custom_1102_TextViewer.xml": {"1": "label", "2000": "textbox", "1000": "button", "3000": "scrollbar"},
    # Hidden Player.Volume progress whose label is the percentage; 11 is 1103's default control.
    "DialogVolumeBar.xml": {"29999": "progress"},
    "Custom_1103_VolumeSlider.xml": {"29999": "progress", "11": "slider"},
    "DialogButtonMenu.xml": {"9000": "panel", "2": "label"},
}

COLOR_ATTRS = ("colordiffuse",)
COLOR_TAGS = ("textcolor", "focusedcolor", "disabledcolor", "shadowcolor", "selectedcolor", "invalidcolor",
              "colordiffuse")
FONT_TAGS = ("font", "monofont")
POPUP_MOTION = ("Custom_1102_TextViewer.xml", "DialogTextViewer.xml")
CURVES = {"slide": ("cubic", "out"), "fade": ("sine", "inout"), "zoom": ("back", "out")}


def defined_colors():
    root = ET.parse(ROOT / "colors" / "defaults.xml").getroot()
    return {node.get("name") for node in root.iter("color")}


def bald_fonts():
    root = ET.parse(SKIN / "Font.xml").getroot()
    return {node.findtext("name") for node in root.iter("font") if (node.findtext("name") or "").startswith("Bald_")}


class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skin = Skin()
        cls.windows = {name: cls.skin.window(name) for name in CHECKED}
        cls.colors = {name for name in defined_colors() if name.startswith("bald_")}
        cls.estuary_colors = defined_colors() - cls.colors

    def variable_values(self, root):
        """Text of every skin variable a window shows, one level deep."""
        values = []
        for text in (node.text or "" for node in root.iter()):
            for name in re.findall(r"\$VAR\[([^\],]+)", text):
                variable = self.skin.variables.get(name)
                self.assertIsNotNone(variable, name)
                values += [value.text or "" for value in variable.iter("value")]
        return values

    def test_includes_resolve(self):
        self.assertEqual(self.skin.missing, [])
        registered = [node.get("file") for node in ET.parse(SKIN / "Includes.xml").getroot().findall("include")]
        self.assertIn("Includes_Bald_Overlays.xml", registered)

    def test_native_ids_are_present_with_their_types(self):
        for name, contract in CONTRACTS.items():
            root = self.windows[name]
            for control_id, kind in contract.items():
                with self.subTest(window=name, id=control_id):
                    nodes = [node for node in root.iter("control") if node.get("id") == control_id]
                    self.assertEqual(len(nodes), 1)
                    self.assertEqual(nodes[0].get("type"), kind)

    def test_default_controls_exist(self):
        for name, root in self.windows.items():
            default = root.findtext("defaultcontrol")
            if default:
                with self.subTest(window=name):
                    self.assertTrue(any(node.get("id") == default for node in root.iter("control")))

    def sources(self):
        """The files this stream restyled, as written, plus its own include file (the shared popup surface,
        DialogBackgroundCommons, and the power menu's ButtonMenuList are covered by test_popup_theme)."""
        paths = [SKIN / name for name in CHECKED] + [SKIN / "Includes_Bald_Overlays.xml"]
        return {path.name: ET.parse(path).getroot() for path in paths}

    def test_only_bald_colour_tokens(self):
        for name, root in self.sources().items():
            used = set()
            for node in root.iter():
                used |= {node.get(attr) for attr in COLOR_ATTRS if node.get(attr)}
                if node.tag in COLOR_TAGS and (node.text or "").strip():
                    used.add(node.text.strip())
                used |= set(re.findall(r"\[COLOR[ =]([^\]]+)\]", node.text or ""))
            for text in self.variable_values(root):
                used |= set(re.findall(r"\[COLOR[ =]([^\]]+)\]", text))
            used = {value for value in used if "$PARAM[" not in value}
            with self.subTest(file=name):
                self.assertEqual(used - self.colors, set())
                self.assertEqual(used & self.estuary_colors, set())

    def test_only_bald_fonts(self):
        fonts = bald_fonts()
        for name, root in self.sources().items():
            used = {node.text.strip() for node in root.iter() if node.tag in FONT_TAGS and (node.text or "").strip()}
            with self.subTest(file=name):
                self.assertEqual(used - fonts, set())
        # As Kodi builds them, every window that shows text uses Bald fonts only.
        for name in CHECKED:
            used = {node.text.strip() for node in self.windows[name].iter() if node.tag in FONT_TAGS and (node.text or "").strip()}
            with self.subTest(window=name):
                self.assertEqual(used - fonts, set())

    def test_motion_is_fade_slide_zoom_on_bald_curves(self):
        # Busy dots pulse by fading only; nothing rotates. The text viewers open with the shared popup animation
        # (Animation_DialogPopupOpenClose), whose curves belong to the popup theme.
        for name in RESTYLED:
            for anim in self.windows[name].iter("animation"):
                effects = [anim] if anim.get("effect") else list(anim.iter("effect"))
                for effect in effects:
                    kind = effect.get("effect") or effect.get("type")
                    with self.subTest(window=name, effect=kind):
                        self.assertIn(kind, CURVES)
                        if effect.get("tween") and name not in POPUP_MOTION:
                            self.assertEqual((effect.get("tween"), effect.get("easing")), CURVES[kind])

    def test_no_previous_menu_on_back(self):
        for name in CHECKED:
            for node in self.windows[name].iter("onback"):
                with self.subTest(window=name):
                    self.assertNotEqual((node.text or "").strip().lower(), "previousmenu")

    def test_background_progress_shows_one_status_line(self):
        root = self.windows["DialogExtendedProgressBar.xml"]
        labels = {node.get("id"): node for node in root.iter("control") if node.get("type") == "label"}
        # The percentage is the bar's alone: no label repeats control 32.
        for node in root.iter():
            self.assertNotIn("GetLabel(32)", node.text or "")
        # Title and step share one grouplist row; the step hides when empty or already in the title.
        row = next(node for node in root.iter("control") if node.get("type") == "grouplist")
        self.assertEqual({"30", "31"}, {node.get("id") for node in row if node.get("id")})
        step = " ".join(node.text for node in labels["31"].findall("visible"))
        self.assertRegex(step, r"!String\.IsEmpty\(Control\.GetLabel\(31\)\)")
        self.assertRegex(step, r"!String\.(Contains|IsEqual)\(Control\.GetLabel\(30\),Control\.GetLabel\(31\)\)")
        bar = next(node for node in root.iter("control") if node.get("id") == "32")
        self.assertEqual(bar.find("midtexture").get("colordiffuse"), "bald_accent")

    def test_accent_marks_progress_only(self):
        for name in RESTYLED:
            for node in self.windows[name].iter():
                if node.get("colordiffuse") == "bald_accent":
                    with self.subTest(window=name, tag=node.tag):
                        self.assertIn(node.tag, ("midtexture", "textureslidernibfocus"))
                if node.tag in COLOR_TAGS:
                    with self.subTest(window=name, tag=node.tag):
                        self.assertNotEqual((node.text or "").strip(), "bald_accent")

    def test_estuary_provenance_is_noted(self):
        for name in RESTYLED:
            head = (SKIN / name).read_text(encoding="utf-8")[:600]
            with self.subTest(window=name):
                self.assertIn("Estuary", head)
                self.assertIn("LICENSE-Estuary.txt", head)

    def test_power_menu_uses_the_shared_popup_theme(self):
        raw = ET.parse(SKIN / "DialogButtonMenu.xml").getroot()
        self.assertIsNotNone(raw.find(".//include[@content='DialogBackgroundCommons']"))
        panel = raw.find(".//control[@id='9000']")
        self.assertEqual((panel.findtext("include") or "").strip(), "ButtonMenuList")

    def test_muted_label_is_a_skin_string(self):
        variable = self.skin.variables["Bald_VolumeLabel"]
        ids = [int(n) for value in variable.iter("value") for n in re.findall(r"\$LOCALIZE\[(\d+)\]", value.text or "")]
        self.assertTrue(ids)
        for number in ids:
            self.assertIn(number, range(31650, 31660))
            self.assertIn(number, strings())


if __name__ == "__main__":
    unittest.main()
