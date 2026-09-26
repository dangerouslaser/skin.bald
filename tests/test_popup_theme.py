from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from kodi_includes import expand_call


ROOT = Path(__file__).resolve().parents[1] / "1080i"


class PopupThemeTests(unittest.TestCase):
    def test_dialog_buttons_use_bald_pills_without_overlap(self):
        # A dialog button as dialogs call it (id and label only): a 72 px Bald pill.
        button, = expand_call("DefaultDialogButton", {"id": "10", "label": "$LOCALIZE[186]"})
        self.assertEqual(button.findtext("height"), "72")
        self.assertEqual(button.findtext("font"), "Bald_Section")
        self.assertEqual(button.findtext("textcolor"), "bald_ink")
        self.assertEqual(button.findtext("focusedcolor"), "bald_field")
        self.assertEqual(button.findtext("texturefocus"), "bald/pill.png")
        self.assertEqual(button.find("texturefocus").get("border"), "27")
        self.assertEqual(button.findtext("texturenofocus"), "bald/pill_outline.png")

        for filename in ("Constants_1080.xml", "Constants_720.xml"):
            constants = ET.parse(ROOT / filename).getroot()
            gap = int(constants.findtext("constant[@name='dialogbuttons_itemgap']"))
            self.assertGreaterEqual(gap, 0)

        for path in ROOT.glob("*.xml"):
            root = ET.parse(path).getroot()
            for group in root.findall(".//control[@type='grouplist']"):
                if group.find(".//include[@content='DefaultDialogButton']") is None:
                    continue
                itemgap = group.findtext("itemgap")
                if itemgap is not None and itemgap.lstrip("-").isdigit():
                    self.assertGreaterEqual(int(itemgap), 0, f"{path.name} has overlapping dialog actions")

    def test_keyboard_action_stack_has_non_overlapping_pitch(self):
        keyboard = ET.parse(ROOT / "DialogKeyboard.xml").getroot()
        actions = keyboard.find(".//control[@id='95200']")
        gap = int(actions.findtext("itemgap"))
        style = ET.parse(ROOT / "Includes_Buttons.xml").getroot().find(
            "include[@name='Bald_KeyboardAction']"
        )
        height = int(style.findtext("param[@name='height']"))
        self.assertGreaterEqual(gap, 0)
        self.assertEqual(height + gap, 80)

    def test_shared_dialog_surface_uses_bald_tokens(self):
        includes = ET.parse(ROOT / "Includes.xml").getroot()
        surface = includes.find("include[@name='DialogBackgroundCommons']")
        textures = {(node.text, node.get("colordiffuse")) for node in surface.iter("texture")}
        self.assertIn(("bald/white.png", "bald_field"), textures)
        self.assertIn(("bald/white.png", "bald_ink10"), textures)
        group = surface.find("control[@type='group']")
        base = group.find("control[@type='image'][1]")
        self.assertEqual(base.findtext("bottom"), "0")
        self.assertEqual(base.find("texture").get("colordiffuse"), "bald_field")
        header = next(node for element in expand_call("DialogBackgroundCommons", {"header_id": "1"})
                      for node in element.iter("control") if node.get("id") == "1")
        self.assertEqual(header.findtext("font"), "Bald_CaptionTitle")
        self.assertEqual(header.findtext("textcolor"), "bald_ink")

    def test_power_menu_uses_bald_list_tokens(self):
        includes = ET.parse(ROOT / "Includes_Buttons.xml").getroot()
        menu = includes.find("include[@name='ButtonMenuList']")
        self.assertNotIn("button_focus", ET.tostring(menu, encoding="unicode"))
        self.assertNotIn("dialog_tint", ET.tostring(menu, encoding="unicode"))
        self.assertEqual(menu.findtext("itemlayout/control[@type='label']/font"), "Bald_Section")
        self.assertEqual(
            menu.findtext("focusedlayout/control[@type='label']/textcolor"), "bald_ink"
        )

    def test_confirm_dialog_preserves_native_contract(self):
        confirm = ET.parse(ROOT / "DialogConfirm.xml").getroot()
        for control_id in ("9", "20"):
            self.assertIsNotNone(confirm.find(f".//control[@id='{control_id}']"), control_id)
        generated_ids = {node.get("value") for node in confirm.findall(".//param[@name='id']")}
        self.assertTrue({"10", "11", "12"}.issubset(generated_ids))
        self.assertEqual(
            confirm.find(".//include[@content='DialogBackgroundCommons']/param[@name='header_id']").get("value"),
            "1",
        )
        body = confirm.find(".//control[@id='9']")
        self.assertEqual(body.findtext("font"), "Bald_InfoPlot")
        self.assertEqual(body.findtext("textcolor"), "bald_ink70")


if __name__ == "__main__":
    unittest.main()
