#!/usr/bin/env python3
"""Add the superscript, subscript and small capital letters Bald's UI fonts lack, drawn from each font's own letters.

Kodi draws each string with one font file and has no per-glyph fallback (CGUIFontTTF), so characters a font lacks
show as empty boxes. Live TV providers decorate titles with modifier letters ("ᴸᶦᵛᵉ", "ᴺᵉʷ", "ᴴᴰ"), which DM Sans,
Instrument Sans and Onest do not have. For each character of these ranges a font does not map:

    U+00B2, U+00B3, U+00B9  the Latin-1 superscript digits (² ³ ¹)
    U+02B0-02FF  spacing modifier letters (ʰ ʷ ʸ ...)
    U+1D00-1DBF  phonetic extensions and supplement (ᴬ ᴮ ... ᵃ ᵇ ... ᶦ ᶻ, small capitals)
    U+2070-209F  superscripts and subscripts (⁰ ⁴ ... ⁿ ₀ ...)

- a superscript or subscript (Unicode's <super> or <sub> of one letter or digit) is that letter from the same family,
  scaled to 62% and raised so its capitals top out at the capital height (or lowered below the baseline);
- a small capital (LATIN LETTER SMALL CAPITAL X) is the capital scaled to the x-height;
- both are taken from the next heavier weight of the family (Regular from Medium, and so on), since scaling a letter
  down thins its stems;
- anything else (IPA and tone letters with no base letter in the font) is copied from Noto Sans (SIL OFL 1.1,
  fonts/NotoSans-OFL.txt), scaled to the font's units per em.

DM Sans, Instrument Sans and Onest are SIL OFL 1.1 without a Reserved Font Name, so the modified fonts keep their names.
Needs fontTools (pip install fonttools). Run it on the fonts as they shipped (DM Sans and Instrument Sans as of commit
433c9dd1, Onest as of 6cd9c09b), then tools/hint_keys.py. Running it again changes nothing: characters a font already
maps are skipped.

  python3 tools/add_superscripts.py
"""

import re
import unicodedata
from pathlib import Path

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "fonts"
SOURCE = FONTS / "NotoSans-Regular.ttf"
TARGETS = sorted(p for p in FONTS.glob("*.ttf") if p.name.startswith(("DMSans-", "InstrumentSans-", "Onest-")))
RANGES = ((0x00B2, 0x00B3), (0x00B9, 0x00B9), (0x02B0, 0x02FF), (0x1D00, 0x1DBF), (0x2070, 0x209F))
HEAVIER = {"Regular": "Medium", "Medium": "SemiBold", "SemiBold": "Bold", "Bold": "Bold"}
SCALE = 0.62  # superscripts and subscripts
SUB_DROP = 0.14  # em below the baseline a subscript's baseline sits
SIDE = 0.02  # em added either side of a synthesised letter


def wanted(codepoint):
    return any(low <= codepoint <= high for low, high in RANGES)


def recipe(codepoint):
    """(kind, base codepoint) for a character drawn from another letter, else None."""
    char = chr(codepoint)
    decomposition = unicodedata.decomposition(char).split()
    if len(decomposition) == 2 and decomposition[0] in ("<super>", "<sub>"):
        return decomposition[0].strip("<>"), int(decomposition[1], 16)
    match = re.fullmatch(r"LATIN LETTER SMALL CAPITAL ([A-Z])", unicodedata.name(char, ""))
    if match:
        return "smallcap", ord(match.group(1))
    return None


def heavier(path):
    family, weight = path.stem.split("-")
    candidate = FONTS / f"{family}-{HEAVIER[weight]}.ttf"
    return candidate if candidate.exists() else path


def map_codepoint(font, codepoint, name):
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap[codepoint] = name


def drawn(glyphset, name, matrix):
    recording = DecomposingRecordingPen(glyphset)
    glyphset[name].draw(recording)
    pen = TTGlyphPen(None)
    recording.replay(TransformPen(pen, matrix))
    return pen.glyph()


def add(target_path, source):
    font = TTFont(target_path)
    cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm
    cap, xheight = font["OS/2"].sCapHeight, font["OS/2"].sxHeight
    base_font = TTFont(heavier(target_path))
    base_cmap, base_glyphs = base_font.getBestCmap(), base_font.getGlyphSet()
    base_scale = upm / base_font["head"].unitsPerEm
    source_cmap, source_glyphs = source.getBestCmap(), source.getGlyphSet()
    noto_scale = upm / source["head"].unitsPerEm
    glyf, hmtx = font["glyf"], font["hmtx"]
    counts = {"drawn": 0, "noto": 0}
    for codepoint in sorted(c for low, high in RANGES for c in range(low, high + 1)):
        if codepoint in cmap:
            continue
        name = f"uni{codepoint:04X}"
        how = recipe(codepoint)
        # Only from letters outside these ranges, so no weight builds on letters another run has just added.
        if how and how[1] in base_cmap and not wanted(how[1]):
            kind, base = how
            base_name = base_cmap[base]
            if kind == "smallcap":
                s, dy = xheight / cap, 0
            else:
                s = SCALE
                dy = cap * (1 - s) if kind == "super" else -SUB_DROP * upm
            s *= base_scale
            side = SIDE * upm
            glyph = drawn(base_glyphs, base_name, (s, 0, 0, s, side, dy))
            advance = round(base_font["hmtx"][base_name][0] * s + 2 * side)
            counts["drawn"] += 1
        elif codepoint in source_cmap:
            glyph = drawn(source_glyphs, source_cmap[codepoint], (noto_scale, 0, 0, noto_scale, 0, 0))
            advance = round(source["hmtx"][source_cmap[codepoint]][0] * noto_scale)
            counts["noto"] += 1
        else:
            continue
        glyf[name] = glyph  # adds it to the glyph order when new
        glyph.recalcBounds(glyf)
        hmtx[name] = (advance, getattr(glyph, "xMin", 0))
        map_codepoint(font, codepoint, name)
    if counts["drawn"] or counts["noto"]:
        font.setGlyphOrder(glyf.glyphOrder)
        for stale in ("hdmx", "LTSH", "VDMX"):  # per-glyph tables that would no longer match the glyph count
            if stale in font:
                del font[stale]
        font.save(target_path)
    return counts


def main():
    source = TTFont(SOURCE)
    for path in TARGETS:
        counts = add(path, source)
        print(f"{path.name}: {counts['drawn']} drawn from its own letters, {counts['noto']} from Noto Sans")


if __name__ == "__main__":
    main()
