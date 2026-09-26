import re
import unittest
import xml.etree.ElementTree as ET

from kodi_includes import SKIN, include_definitions, resolve_window

ROOT = SKIN.parent

WINDOWS = {
    "Custom_1115_BaldSettings.xml": ("9000", ["9001"]),
    "Custom_1116_BaldHomeWidgets.xml": ("9100", ["9200", "9201", "9202", "9203", "9204", "9205", "9206", "9207"]),
    "Custom_1117_BaldHomeScreens.xml": ("9300", ["9400", "9401", "9402"]),
    "Custom_1118_BaldAppearance.xml": ("9500", ["9600", "9601", "9602", "9611", "9621", "9622", "9623"]),
}

def tokens(path, tag):
    return {node.findtext("name") if tag == "font" else node.get("name")
            for node in ET.parse(path).getroot().iter(tag)}


class SettingsScaffoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        definitions = include_definitions()
        cls.windows = {name: resolve_window(name, definitions) for name in WINDOWS}
        cls.fonts = tokens(SKIN / "Font.xml", "font")
        cls.colors = tokens(ROOT / "colors" / "defaults.xml", "color")

    def control(self, window, control_id):
        return self.windows[window].find(f".//control[@id='{control_id}']")

    def test_every_settings_window_keeps_its_control_ids(self):
        for name, (categories, others) in WINDOWS.items():
            for control_id in [categories, *others]:
                self.assertIsNotNone(self.control(name, control_id), f"{name} lost control {control_id}")

    def test_every_settings_window_draws_the_same_frame(self):
        for name in WINDOWS:
            controls = self.windows[name].find("controls")
            images = controls.findall("control[@type='image']")
            textures = [image.findtext("texture") for image in images]
            self.assertIn("bald/white.png", textures[0], name)
            self.assertIn("TMDbHelper.ListItem.BlurImage", textures[1], f"{name} has no Bald backdrop")
            self.assertEqual(images[2].findtext("width"), "590", name)
            title = controls.find("control[@type='label']")
            self.assertEqual((title.findtext("left"), title.findtext("top")), ("96", "96"), name)

    def test_category_lists_share_one_layout(self):
        layouts = set()
        for name, (categories, _) in WINDOWS.items():
            category_list = self.control(name, categories)
            self.assertEqual(category_list.get("type"), "list", name)
            focused = category_list.find("focusedlayout")
            dot = focused.find(".//control[@type='image']/texture")
            self.assertEqual((dot.text, dot.get("colordiffuse")), ("bald/dot.png", "bald_accent"), name)
            unfocused = category_list.find("itemlayout/control[@type='label']")
            self.assertEqual(unfocused.findtext("textcolor"), "bald_ink34", name)
            layout = ET.tostring(category_list.find("itemlayout")) + ET.tostring(focused)
            layouts.add(re.sub(rb"Bald_\w+|HasFocus\(\d+\)", b"", layout))
            expected = "Bald_InfoTagline" if name.startswith("Custom_1116") else "Bald_MenuItem"
            self.assertEqual(unfocused.findtext("font"), expected, name)
        self.assertEqual(len(layouts), 1, "category list layouts differ between settings windows")

    def test_settings_windows_use_only_bald_fonts_and_colors(self):
        for name, root in self.windows.items():
            for node in root.iter("font"):
                self.assertTrue(node.text.startswith("Bald_"), f"{name}: {node.text}")
                self.assertIn(node.text, self.fonts, name)
            for tag in ("textcolor", "focusedcolor", "disabledcolor", "colordiffuse"):
                for node in root.iter(tag):
                    self.assertIn(node.text, self.colors, f"{name}: {tag} {node.text}")
            for node in root.iter():
                if "colordiffuse" in node.attrib:
                    self.assertIn(node.get("colordiffuse"), self.colors, f"{name}: {node.get('colordiffuse')}")

    def test_footer_hints_are_sentence_case_on_the_info_hint_line(self):
        for name, root in self.windows.items():
            hints = [group for group in root.iter("control")
                     if group.get("type") == "group" and group.findtext("top") == "954"]
            self.assertEqual(len(hints), 1, name)
            self.assertEqual(int(hints[0].findtext("left")) + int(hints[0].find("control").findtext("width")), 1824)
            for label in hints[0].iter("label"):
                self.assertFalse(label.text.isupper(), f"{name}: {label.text}")
            for label in root.iter("label"):
                self.assertNotIn("  •  ", label.text or "", name)

    def test_appearance_rows_follow_category_ids_not_labels(self):
        root = self.windows["Custom_1118_BaldAppearance.xml"]
        ids = [item.get("id") for item in root.findall(".//control[@id='9500']/content/item")]
        self.assertEqual(ids, ["1", "2", "3"])
        seen = set()
        for row in self.control("Custom_1118_BaldAppearance.xml", "9600").findall("control"):
            conditions = [node.text for node in row.findall("visible")]
            self.assertFalse(any("ListItem.Label" in condition for condition in conditions), row.get("id"))
            owners = [re.fullmatch(r"Container\(9500\)\.HasFocus\((\d+)\)", condition) for condition in conditions]
            owners = [match.group(1) for match in owners if match]
            self.assertEqual(len(owners), 1, f"row {row.get('id')} must belong to one category")
            self.assertIn(owners[0], ids)
            seen.add(owners[0])
        self.assertEqual(seen, set(ids), "every category needs rows")


if __name__ == "__main__":
    unittest.main()
