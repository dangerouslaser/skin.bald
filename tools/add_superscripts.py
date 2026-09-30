#!/usr/bin/env python3
"""Give Bald's UI fonts one set of superscript, subscript and small capital letters: Noto Sans's, in every typeface.

Kodi draws each string with one font file and has no per-glyph fallback (CGUIFontTTF), so characters a font lacks
show as empty boxes. Live TV providers decorate titles with modifier letters ("ᴸᶦᵛᵉ", "ᴺᵉʷ", "ᴴᴰ"), and none of Bald's
typefaces has them: DM Sans ships ¹ ² ³ ⁴, Onest ¹ ² ³ and ʷ, Instrument Sans none. Mixing those with letters from
elsewhere set "ᴺᵉʷ" at two heights, so every character below that is a superscript, subscript or small capital
(Unicode's <super> or <sub> of a letter, or LATIN LETTER SMALL CAPITAL) is copied from Noto Sans (SIL OFL 1.1,
fonts/NotoSans-OFL.txt), scaled to the font's units per em, replacing the font's own where it has one. Other
characters of the ranges (IPA modifiers and tone letters) are copied only where the font lacks them, so its spacing
accents (ˆ ˇ ˘ ˙ ...) stay its own.

    U+00B2, U+00B3, U+00B9  the Latin-1 superscript digits (² ³ ¹)
    U+02B0-02FF  spacing modifier letters (ʰ ʷ ʸ ...)
    U+1D00-1DBF  phonetic extensions and supplement (ᴬ ᴮ ... ᵃ ᵇ ... ᶦ ᶻ, small capitals)
    U+2070-209F  superscripts and subscripts (⁰ ⁴ ... ⁿ ₀ ...)

DM Sans, Instrument Sans and Onest are SIL OFL 1.1 without a Reserved Font Name, so the modified fonts keep their names.
Needs fontTools (pip install fonttools). Run it on the fonts as they shipped (DM Sans and Instrument Sans as of commit
433c9dd1, Onest as of 6cd9c09b), then tools/hint_keys.py. Running it again gives the same fonts.

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


def wanted(codepoint):
    return any(low <= codepoint <= high for low, high in RANGES)


def superscript_like(codepoint):
    """A superscript, subscript or small capital: always Noto's, so they all match."""
    char = chr(codepoint)
    decomposition = unicodedata.decomposition(char).split()
    if len(decomposition) == 2 and decomposition[0] in ("<super>", "<sub>"):
        return True
    return re.fullmatch(r"LATIN LETTER SMALL CAPITAL [A-Z]", unicodedata.name(char, "")) is not None


def map_codepoint(font, codepoint, name):
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap[codepoint] = name


def add(target_path, source):
    font = TTFont(target_path)
    cmap = font.getBestCmap()
    scale = font["head"].unitsPerEm / source["head"].unitsPerEm
    source_glyphs = source.getGlyphSet()
    glyf, hmtx = font["glyf"], font["hmtx"]
    added = replaced = 0
    for codepoint, source_name in sorted(source.getBestCmap().items()):
        if not wanted(codepoint):
            continue
        name = f"bald.noto.{codepoint:04X}"
        native = codepoint in cmap and cmap[codepoint] != name
        if native and not superscript_like(codepoint):
            continue
        recording = DecomposingRecordingPen(source_glyphs)
        source_glyphs[source_name].draw(recording)
        pen = TTGlyphPen(None)
        recording.replay(TransformPen(pen, (scale, 0, 0, scale, 0, 0)))
        glyph = pen.glyph()
        # A name of its own, so a glyph the font's other characters share (composites, kerning) is left alone.
        glyf[name] = glyph  # adds it to the glyph order when new
        glyph.recalcBounds(glyf)
        hmtx[name] = (round(source["hmtx"][source_name][0] * scale), getattr(glyph, "xMin", 0))
        map_codepoint(font, codepoint, name)
        if native:
            replaced += 1
        else:
            added += 1
    font.setGlyphOrder(glyf.glyphOrder)
    for stale in ("hdmx", "LTSH", "VDMX"):  # per-glyph tables that would no longer match the glyph count
        if stale in font:
            del font[stale]
    font.save(target_path)
    return added, replaced


def main():
    source = TTFont(SOURCE)
    for path in TARGETS:
        added, replaced = add(path, source)
        print(f"{path.name}: {added} added from Noto Sans, {replaced} of its own replaced")


if __name__ == "__main__":
    main()
