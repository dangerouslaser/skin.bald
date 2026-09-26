"""Font.xml's Latin fontsets are interchangeable: switching lookandfeel.font swaps the typeface and nothing moves.

A fontset may differ from Default only in its files and in linespacing, and a changed linespacing must give the same
pixel line height as Default. Kodi's line height (CGUIFontTTF::GetLineHeight) is linespacing times FreeType's
size->metrics.height, which for TrueType is the face height (ascender - descender + line gap, from hhea, or from
OS/2 typo metrics when USE_TYPO_METRICS is set) scaled to the pixel size and rounded to a whole pixel.
"""

import math
import struct
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


def face_height(path):
    """(units per em, FreeType face height in font units) of a TrueType file."""
    data = path.read_bytes()
    tables = {}
    for i in range(struct.unpack(">H", data[4:6])[0]):
        tag, _, offset, _ = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
        tables[tag.decode("latin-1")] = offset
    units_per_em = struct.unpack(">H", data[tables["head"] + 18:tables["head"] + 20])[0]
    ascender, descender, line_gap = struct.unpack(">hhh", data[tables["hhea"] + 4:tables["hhea"] + 10])
    os2 = tables["OS/2"]
    fs_selection = struct.unpack(">H", data[os2 + 62:os2 + 64])[0]
    if fs_selection & (1 << 7):
        ascender, descender, line_gap = struct.unpack(">hhh", data[os2 + 68:os2 + 74])
    return units_per_em, ascender - descender + line_gap


def line_height(fields):
    """Kodi's pixel line height for a font entry (1080i skin at 1080 lines, so no GUI scaling)."""
    units_per_em, height = face_height(ROOT / "fonts" / fields["filename"])
    natural = math.floor(height * int(fields["size"]) / units_per_em + 0.5)
    return float(fields.get("linespacing", "1")) * natural


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

    def test_latin_fontsets_differ_from_default_only_in_typeface_file_and_linespacing(self):
        sets = fontsets()
        self.assertEqual(set(sets) - UNICODE_FONTSETS, set(TYPEFACES))
        default = entries(sets["Default"])
        for fontset_id, prefix in TYPEFACES.items():
            with self.subTest(fontset=fontset_id):
                swapped = []
                for name, fields in default:
                    fields = dict(fields)
                    fields["filename"] = fields["filename"].replace(TYPEFACES["Default"], prefix)
                    fields.pop("linespacing", None)
                    swapped.append((name, fields))
                ours = [(name, {k: v for k, v in fields.items() if k != "linespacing"})
                        for name, fields in entries(sets[fontset_id])]
                self.assertEqual(ours, swapped)

    def test_a_changed_linespacing_keeps_defaults_pixel_line_height(self):
        sets = fontsets()
        default = entries(sets["Default"])
        changed = 0
        for fontset_id in TYPEFACES:
            for (name, base), (_, fields) in zip(default, entries(sets[fontset_id])):
                if fields.get("linespacing") == base.get("linespacing") or "/" in fields["filename"]:
                    continue
                changed += 1
                with self.subTest(fontset=fontset_id, font=name):
                    self.assertAlmostEqual(line_height(fields), line_height(base), delta=0.5)
        self.assertTrue(changed, "DMSans matches Instrument Sans' line heights through linespacing")

    def test_multi_line_fonts_keep_their_line_height_in_every_fontset(self):
        # Fonts of textboxes and wrapped labels: their line pitch is layout, so DM Sans must match it.
        multi_line = {"Bald_CaptionMeta", "Bald_CaptionPlot", "Bald_CaptionTitle", "Bald_CastName", "Bald_CastRole",
                      "Bald_DetailValue", "Bald_InfoPlot", "Bald_MenuNote", "Bald_Section", "font12", "font13",
                      "font14", "font27", "font27_narrow", "font30_title", "font32_title", "font36_title", "font37",
                      "font45_title"}
        sets = fontsets()
        default = entries(sets["Default"])
        for fontset_id in TYPEFACES:
            for (name, base), (_, fields) in zip(default, entries(sets[fontset_id])):
                if name in multi_line and "/" not in fields["filename"]:
                    with self.subTest(fontset=fontset_id, font=name):
                        self.assertAlmostEqual(line_height(fields), line_height(base), delta=0.5)

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
