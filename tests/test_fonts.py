"""Font.xml's fontsets are interchangeable: switching lookandfeel.font swaps the typeface and nothing moves.

A fontset may differ from Default only in its files and in linespacing, and a changed linespacing must give the same
pixel line height as Default. Kodi's line height (CGUIFontTTF::GetLineHeight) is linespacing times FreeType's
size->metrics.height, which for TrueType is the face height (ascender - descender + line gap, from hhea, or from
OS/2 typo metrics when USE_TYPO_METRICS is set) scaled to the pixel size and rounded to a whole pixel.

Bald Settings > Appearance > Typography cycles through the three (1080i/Custom_1118_BaldAppearance.xml, 9631).
"""

import math
import re
import struct
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from skin_strings import strings

ROOT = Path(__file__).resolve().parents[1]
FONT_XML = ROOT / "1080i" / "Font.xml"
# Fontsets Bald offers, with the file prefix of each typeface. DM Sans is Default (lookandfeel.font's default value);
# Instrument Sans is the reference set the others are compared with; Onest, the one with Cyrillic, keeps the id Arial
# of the arial.ttf set it replaced, so a user who had chosen that one for Cyrillic lands on Onest.
TYPEFACES = {"InstrumentSans": "InstrumentSans-", "Default": "DMSans-", "Arial": "Onest-"}
BASE = "InstrumentSans"
LABELS = {"Default": "DM Sans", "InstrumentSans": "Instrument Sans", "Arial": "Onest"}
# The Russian alphabet and the Ukrainian, Belarusian, Serbian and Macedonian letters (U+0401-U+045F, without the rare
# E and I with grave, U+0400, U+040D, U+0450, U+045D, which Onest lacks) and Ukrainian Ghe with upturn.
CYRILLIC = [c for c in range(0x0401, 0x0460) if c not in (0x040D, 0x0450, 0x045D)] + [0x0490, 0x0491]


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


def characters(path):
    """The code points a TrueType file maps, from its Unicode BMP cmap subtable (format 4)."""
    data = path.read_bytes()
    tables = {}
    for i in range(struct.unpack(">H", data[4:6])[0]):
        tag, _, offset, _ = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
        tables[tag.decode("latin-1")] = offset
    cmap = tables["cmap"]
    for i in range(struct.unpack(">H", data[cmap + 2:cmap + 4])[0]):
        platform, encoding, offset = struct.unpack(">HHI", data[cmap + 4 + 8 * i:cmap + 12 + 8 * i])
        sub = cmap + offset
        if (platform, encoding) in ((3, 1), (0, 3)) and struct.unpack(">H", data[sub:sub + 2])[0] == 4:
            break
    else:
        raise AssertionError(f"{path.name}: no format 4 Unicode cmap")
    segments = struct.unpack(">H", data[sub + 6:sub + 8])[0] // 2
    ends = struct.unpack(f">{segments}H", data[sub + 14:sub + 14 + 2 * segments])
    base = sub + 16 + 2 * segments
    starts = struct.unpack(f">{segments}H", data[base:base + 2 * segments])
    deltas = struct.unpack(f">{segments}h", data[base + 2 * segments:base + 4 * segments])
    range_at = base + 4 * segments
    ranges = struct.unpack(f">{segments}H", data[range_at:range_at + 2 * segments])
    found = set()
    for n, (start, end, delta, offset) in enumerate(zip(starts, ends, deltas, ranges)):
        for code in range(start, min(end, 0xFFFE) + 1):
            if offset:
                where = range_at + 2 * n + offset + 2 * (code - start)
                glyph = struct.unpack(">H", data[where:where + 2])[0]
                glyph = (glyph + delta) & 0xFFFF if glyph else 0
            else:
                glyph = (code + delta) & 0xFFFF
            if glyph:
                found.add(code)
    return found


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

    def test_every_fontset_defines_the_default_names(self):
        sets = fontsets()
        expected = sorted(name for name, _ in entries(sets["Default"]))
        for fontset_id, fontset in sets.items():
            with self.subTest(fontset=fontset_id):
                self.assertEqual(sorted(name for name, _ in entries(fontset)), expected)

    def test_fontsets_differ_from_default_only_in_typeface_file_and_linespacing(self):
        sets = fontsets()
        self.assertEqual(set(sets), set(TYPEFACES))
        default = entries(sets[BASE])
        for fontset_id, prefix in TYPEFACES.items():
            with self.subTest(fontset=fontset_id):
                swapped = []
                for name, fields in default:
                    fields = dict(fields)
                    fields["filename"] = fields["filename"].replace(TYPEFACES[BASE], prefix)
                    fields.pop("linespacing", None)
                    swapped.append((name, fields))
                ours = [(name, {k: v for k, v in fields.items() if k != "linespacing"})
                        for name, fields in entries(sets[fontset_id])]
                self.assertEqual(ours, swapped)

    def test_a_changed_linespacing_keeps_defaults_pixel_line_height(self):
        sets = fontsets()
        default = entries(sets[BASE])
        changed = 0
        for fontset_id in TYPEFACES:
            for (name, base), (_, fields) in zip(default, entries(sets[fontset_id])):
                if fields.get("linespacing") == base.get("linespacing") or "/" in fields["filename"]:
                    continue
                changed += 1
                with self.subTest(fontset=fontset_id, font=name):
                    self.assertAlmostEqual(line_height(fields), line_height(base), delta=0.5)
        self.assertTrue(changed, "DM Sans matches Instrument Sans' line heights through linespacing")

    def test_multi_line_fonts_keep_their_line_height_in_every_fontset(self):
        # Fonts of textboxes and wrapped labels: their line pitch is layout, so DM Sans must match it.
        multi_line = {"Bald_CaptionMeta", "Bald_CaptionPlot", "Bald_CaptionTitle", "Bald_CastName", "Bald_CastRole",
                      "Bald_DetailValue", "Bald_InfoPlot", "Bald_MenuNote", "Bald_Section", "font12", "font13",
                      "font27", "font37"}
        sets = fontsets()
        default = entries(sets[BASE])
        for fontset_id in TYPEFACES:
            for (name, base), (_, fields) in zip(default, entries(sets[fontset_id])):
                if name in multi_line and "/" not in fields["filename"]:
                    with self.subTest(fontset=fontset_id, font=name):
                        self.assertAlmostEqual(line_height(fields), line_height(base), delta=0.5)

    def test_fontsets_have_a_label_and_their_files_ship(self):
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
        self.assertIn("The Onest Project Authors", (ROOT / "fonts" / "Onest-OFL.txt").read_text())

    def test_each_fontset_is_labelled_with_its_typeface(self):
        text = strings()
        for fontset_id, fontset in fontsets().items():
            with self.subTest(fontset=fontset_id):
                self.assertEqual(text[int(fontset.get("idloc"))], LABELS[fontset_id])

    def test_onest_draws_cyrillic_in_every_weight_it_ships(self):
        # Every file the set ships with, Noto Sans (the keyboard's keys) included.
        files = {fields["filename"] for _, fields in entries(fontsets()["Arial"]) if "/" not in fields["filename"]}
        self.assertEqual({f for f in files if f.startswith("Onest-")},
                         {"Onest-Regular.ttf", "Onest-Medium.ttf", "Onest-SemiBold.ttf"})
        for filename in sorted(files):
            with self.subTest(file=filename):
                found = characters(ROOT / "fonts" / filename)
                self.assertEqual([hex(c) for c in CYRILLIC if c not in found], [])
                self.assertTrue(set(range(0x20, 0x7F)) <= found)  # and all of printable ASCII

    def test_every_ui_font_draws_the_modifier_letters_providers_use(self):
        # Live TV providers decorate titles with superscript and small capital letters ("ᴺᵉʷ", "ᴸᶦᵛᵉ", "ᴴᴰ"); Kodi has no
        # per-glyph fallback, so a font without them shows boxes (tools/add_superscripts.py adds them).
        letters = {ord(c) for c in "ᴺᵉʷᴸᶦᵛᴴᴰᴿᴱᴾᵀ¹²³⁴⁵⁶⁷⁸⁹⁰"}
        for path in sorted((ROOT / "fonts").glob("*.ttf")):
            if path.name.startswith("NotoSans"):
                continue
            with self.subTest(font=path.name):
                self.assertEqual(sorted(hex(c) for c in letters - characters(path)), [])

    def test_only_kodis_bundled_arial_remains_and_only_for_text_from_outside_the_skin(self):
        # Estuary's old Arial fontset named a skin-local arial.ttf that Bald never shipped.
        for fontset_id, fontset in fontsets().items():
            for name, fields in entries(fontset):
                if "arial" in fields["filename"].lower():
                    with self.subTest(fontset=fontset_id, font=name):
                        self.assertEqual(fields["filename"], "special://xbmc/media/Fonts/arial.ttf")
                        self.assertIn(name, ("font23_narrow", "font32"))


class TypographyRowTests(unittest.TestCase):
    """Appearance > Typography (9631): one click moves one step along DM Sans, Instrument Sans, Onest."""

    @classmethod
    def setUpClass(cls):
        window = ET.parse(ROOT / "1080i" / "Custom_1118_BaldAppearance.xml").getroot()
        cls.row = window.find(".//control[@id='9631']")
        configure = ET.parse(ROOT / "1080i" / "Includes_Bald_Configure.xml").getroot()
        cls.name = configure.find("variable[@name='Bald_FontName']")

    @staticmethod
    def holds(condition, font):
        """Whether an onclick condition (String.IsEqual(Skin.Font,...) terms joined by +) holds for `font`."""
        for term in (t.strip() for t in condition.split("+")):
            match = re.fullmatch(r"(!?)String\.IsEqual\(Skin\.Font,(\w+)\)", term)
            assert match, term
            if (match.group(2) == font) == bool(match.group(1)):
                return False
        return True

    def clicked(self, font):
        """The builtins one click runs: Kodi checks every condition first, then runs the matching actions."""
        return [n.text for n in self.row.findall("onclick") if self.holds(n.get("condition"), font)]

    def test_each_click_moves_one_step_round_the_three(self):
        cycle = {"Default": "InstrumentSans", "InstrumentSans": "Arial", "Arial": "Default"}
        self.assertEqual(set(cycle), set(TYPEFACES))
        for font, following in cycle.items():
            with self.subTest(font=font):
                self.assertEqual(self.clicked(font), [f"RunScript(skin.bald,font,{following})"])

    def test_a_fontset_bald_does_not_have_steps_to_instrument_sans(self):
        # Kodi draws Default for an id Font.xml lacks, so the next step is Instrument Sans.
        for font in ("DMSans", ""):
            with self.subTest(font=font):
                self.assertEqual(self.clicked(font), ["RunScript(skin.bald,font,InstrumentSans)"])

    def test_the_row_names_the_selected_typeface(self):
        text = strings()
        values = [(v.get("condition"), v.text) for v in self.name.findall("value")]
        self.assertEqual(values, [("String.IsEqual(Skin.Font,InstrumentSans)", "$LOCALIZE[31940]"),
                                  ("String.IsEqual(Skin.Font,Arial)", "$LOCALIZE[31415]"),
                                  (None, "$LOCALIZE[31941]")])
        self.assertEqual([text[int(v[1][10:-1])] for v in values], ["Instrument Sans", "Onest", "DM Sans"])
        self.assertEqual(self.row.findtext("label2"), "$VAR[Bald_FontName]")


class TextSizeRowTests(unittest.TestCase):
    """Appearance > Typography > Text size (9638): one click moves one step along Default (0), Large (4), Larger (8),
    Kodi's lookandfeel.skinzoom, as kept in Skin.String(Bald.TextSize)."""

    STRING = "Skin.String(Bald.TextSize)"

    @classmethod
    def setUpClass(cls):
        window = ET.parse(ROOT / "1080i" / "Custom_1118_BaldAppearance.xml").getroot()
        cls.rows = [node.get("id") for node in window.iter("control") if node.get("id") in ("9631", "9638")]
        cls.row = window.find(".//control[@id='9638']")
        configure = ET.parse(ROOT / "1080i" / "Includes_Bald_Configure.xml").getroot()
        cls.label = configure.find("variable[@name='Bald_TextSizeLabel']")

    @classmethod
    def holds(cls, condition, stored):
        """Whether a condition (String.IsEqual / String.IsEmpty terms on the skin string, joined by +) holds."""
        for term in (t.strip() for t in condition.split("+")):
            match = re.fullmatch(r"(!?)String\.(IsEqual|IsEmpty)\(Skin\.String\(Bald\.TextSize\)(?:,(-?\w+))?\)", term)
            assert match, term
            truth = stored == match.group(3) if match.group(2) == "IsEqual" else stored == ""
            if truth == bool(match.group(1)):
                return False
        return True

    def clicked(self, stored):
        return [n.text for n in self.row.findall("onclick") if self.holds(n.get("condition"), stored)]

    def shown(self, stored):
        """The label2 text for a stored value: the first value whose condition holds."""
        for value in self.label.findall("value"):
            if value.get("condition") is None or self.holds(value.get("condition"), stored):
                return value.text

    def test_each_click_moves_one_step_round_the_three(self):
        for stored, following in {"": "4", "0": "4", "4": "8", "8": "0"}.items():
            with self.subTest(stored=stored):
                self.assertEqual(self.clicked(stored), [f"RunScript(skin.bald,textsize,{following})"])

    def test_a_zoom_set_elsewhere_steps_to_large(self):
        for stored in ("2", "10", "-4", "30"):
            with self.subTest(stored=stored):
                self.assertEqual(self.clicked(stored), ["RunScript(skin.bald,textsize,4)"])

    def test_the_row_names_the_size(self):
        text = strings()
        self.assertEqual(self.row.findtext("label"), "$LOCALIZE[31430]")
        self.assertEqual(text[31430], "Text size")
        self.assertEqual(self.row.findtext("label2"), "$VAR[Bald_TextSizeLabel]")
        for stored, expected in {"": "$LOCALIZE[571]", "0": "$LOCALIZE[571]", "4": "$LOCALIZE[31431]",
                                 "8": "$LOCALIZE[31432]", "10": "$INFO[Skin.String(Bald.TextSize),, %]",
                                 "-4": "$INFO[Skin.String(Bald.TextSize),, %]"}.items():
            with self.subTest(stored=stored):
                self.assertEqual(self.shown(stored), expected)
        self.assertEqual((text[31431], text[31432]), ("Large", "Larger"))

    def test_the_row_follows_the_font_row_at_standard(self):
        self.assertEqual(self.rows, ["9631", "9638"])
        include = self.row.find("include[@content='Bald_SettingRow']")
        params = {p.get("name"): p.text for p in include.findall("param")}
        self.assertEqual(params, {"list": "9500", "item": "5", "level": "standard"})

    def test_the_steps_are_the_scripts_sizes(self):
        from scripts import info
        steps = sorted({int(n.text.rsplit(",", 1)[1][:-1]) for n in self.row.findall("onclick")})
        self.assertEqual(tuple(steps), info.TEXT_SIZES)
        self.assertEqual(info.TEXT_SIZE_SKIN_STRING, "Bald.TextSize")


if __name__ == "__main__":
    unittest.main()
