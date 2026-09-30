#!/usr/bin/env python3
"""Add the superscript and small-capital letters Bald's UI fonts lack, from Noto Sans (fonts/NotoSans-Regular.ttf).

Kodi draws each string with one font file and has no per-glyph fallback (CGUIFontTTF), so characters a font lacks
show as empty boxes. Live TV providers decorate titles with modifier letters ("ᴸᶦᵛᵉ", "ᴺᵉʷ", "ᴴᴰ"), which DM Sans,
Instrument Sans and Onest do not have. This copies the glyphs of these ranges that a font lacks from Noto Sans (SIL OFL
1.1, fonts/NotoSans-OFL.txt), scaled to the font's units per em, into each of Bald's fonts in place:

    U+02B0-02FF  spacing modifier letters (ʰ ʷ ʸ ...)
    U+1D00-1DBF  phonetic extensions and supplement (ᴬ ᴮ ... ᵃ ᵇ ... ᶦ ᶻ, small capitals)
    U+2070-209F  superscripts and subscripts (⁰ ⁴ ... ⁿ ₀ ...)
    U+00B2, U+00B3, U+00B9  the Latin-1 superscript digits (² ³ ¹), which Instrument Sans lacks

DM Sans, Instrument Sans and Onest are SIL OFL 1.1 without a Reserved Font Name, so the modified fonts keep their names.
Needs fontTools (pip install fonttools). Running it again changes nothing: characters a font already maps are skipped, and a glyph it has
under the uniXXXX name but maps no character to is mapped rather than copied.

  python3 tools/add_superscripts.py
"""

from pathlib import Path

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fonts" / "NotoSans-Regular.ttf"
TARGETS = sorted(p for p in (ROOT / "fonts").glob("*.ttf") if p.name.startswith(("DMSans-", "InstrumentSans-", "Onest-")))
RANGES = ((0x00B2, 0x00B3), (0x00B9, 0x00B9), (0x02B0, 0x02FF), (0x1D00, 0x1DBF), (0x2070, 0x209F))


def wanted(codepoint):
    return any(low <= codepoint <= high for low, high in RANGES)


def map_codepoint(font, codepoint, name):
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap[codepoint] = name


def add(target_path, source):
    font = TTFont(target_path)
    cmap = font.getBestCmap()
    source_cmap = source.getBestCmap()
    source_glyphs = source.getGlyphSet()
    scale = font["head"].unitsPerEm / source["head"].unitsPerEm
    glyf, hmtx = font["glyf"], font["hmtx"]
    encoded = set(cmap.values())
    added = 0
    for codepoint, name in sorted(source_cmap.items()):
        if not wanted(codepoint) or codepoint in cmap:
            continue
        new_name = f"uni{codepoint:04X}" if codepoint <= 0xFFFF else f"u{codepoint:05X}"
        if new_name in glyf:
            if new_name not in encoded:  # the font draws it but maps no character to it: map this one
                map_codepoint(font, codepoint, new_name)
                encoded.add(new_name)
                added += 1
            continue
        recording = DecomposingRecordingPen(source_glyphs)
        source_glyphs[name].draw(recording)
        pen = TTGlyphPen(None)
        recording.replay(TransformPen(pen, (scale, 0, 0, scale, 0, 0)))
        glyph = pen.glyph()
        advance = source["hmtx"][name][0]
        glyf[new_name] = glyph
        glyph.recalcBounds(glyf)
        hmtx[new_name] = (round(advance * scale), getattr(glyph, "xMin", 0))  # glyf[...] = adds it to the order
        map_codepoint(font, codepoint, new_name)
        encoded.add(new_name)
        added += 1
    if added:
        font.setGlyphOrder(glyf.glyphOrder)
        for stale in ("hdmx", "LTSH", "VDMX"):  # per-glyph tables that would no longer match the glyph count
            if stale in font:
                del font[stale]
        font.save(target_path)
    return added


def main():
    source = TTFont(SOURCE)
    for path in TARGETS:
        print(f"{path.name}: {add(path, source)} glyphs added")


if __name__ == "__main__":
    main()
