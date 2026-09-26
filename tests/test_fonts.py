"""Font.xml's Latin fontsets are interchangeable: switching lookandfeel.font only swaps the typeface."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONT_XML = ROOT / "1080i" / "Font.xml"
# Non-Latin fallback; it keeps Estuary's own list rather than Bald's names.
UNICODE_FONTSETS = {"Arial"}
# Fontsets Bald offers, with the file prefix of each typeface.
TYPEFACES = {"Default": "InstrumentSans-", "DMSans": "DMSans-"}


def fontsets():
    return {node.get("id"): node for node in ET.parse(FONT_XML).getroot().findall("fontset")}


def entries(fontset):
    """Every font as (name, {field: value}) in file order, filename included."""
    return [(font.findtext("name"), {child.tag: (child.text or "").strip() for child in font if child.tag != "name"})
            for font in fontset.findall("font")]


class FontsetTests(unittest.TestCase):
    def test_default_comes_first_so_kodi_falls_back_to_it(self):
        self.assertEqual(ET.parse(FONT_XML).getroot().find("fontset").get("id"), "Default")

    def test_every_latin_fontset_defines_the_default_names(self):
        sets = fontsets()
        expected = sorted(name for name, _ in entries(sets["Default"]))
        for fontset_id, fontset in sets.items():
            if fontset_id in UNICODE_FONTSETS:
                continue
            with self.subTest(fontset=fontset_id):
                self.assertEqual(sorted(name for name, _ in entries(fontset)), expected)

    def test_latin_fontsets_differ_from_default_only_in_the_typeface_file(self):
        sets = fontsets()
        self.assertEqual(set(sets) - UNICODE_FONTSETS, set(TYPEFACES))
        default = entries(sets["Default"])
        for fontset_id, prefix in TYPEFACES.items():
            with self.subTest(fontset=fontset_id):
                swapped = []
                for name, fields in default:
                    fields = dict(fields)
                    fields["filename"] = fields["filename"].replace(TYPEFACES["Default"], prefix)
                    swapped.append((name, fields))
                self.assertEqual(entries(sets[fontset_id]), swapped)

    def test_latin_fontsets_have_a_label_and_their_files_ship(self):
        sets = fontsets()
        for fontset_id in TYPEFACES:
            with self.subTest(fontset=fontset_id):
                self.assertTrue(sets[fontset_id].get("idloc", "").isdigit())
                for _, fields in entries(sets[fontset_id]):
                    filename = fields["filename"]
                    if "/" not in filename:
                        self.assertTrue((ROOT / "fonts" / filename).is_file(), filename)

    def test_each_shipped_typeface_has_its_licence(self):
        self.assertIn("Instrument Sans", (ROOT / "fonts" / "OFL.txt").read_text())
        self.assertIn("DM Sans", (ROOT / "fonts" / "DMSans-OFL.txt").read_text())


if __name__ == "__main__":
    unittest.main()
