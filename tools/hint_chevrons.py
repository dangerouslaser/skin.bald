#!/usr/bin/env python3
"""Draw Bald's navigation chevrons into its UI fonts, so a hint names its key with a chevron ("˅ Cast & details").

Kodi draws a label with one font file (CGUIFontTTF), so an arrow in a hint either comes from the font or has to be a
separate image lined up by hand in every font. These glyphs, in the Private Use Area, are drawn to Bald's hint type
(Bald_Hint, 17 px): a chevron 9 by 4.5 px with a 1.5 px round stroke (a little heavier in the heavier weights),
centred on the capitals, and 7 px of space after it built into its advance, so "chevron + name" needs no space and
reads the same in every font and size. A right chevron follows its name instead ("Scroll by letters ›"), so its
space comes before it: hints read left to right, Left's first and Right's last, and a hint for both Left and Right
sits between the two ("‹ Jump letters ›").

    U+E100  up        U+E101  down       U+E102  left       U+E103  right (after its name)
    U+E105  up and down

The skin writes them through $VAR[Bald_ChevronUp] and the other Bald_Chevron* variables (Includes_Bald_Common.xml).
DM Sans, Instrument Sans and Onest are SIL OFL 1.1 without a Reserved Font Name, so the modified fonts keep their
names (as with tools/add_superscripts.py). Needs fontTools (pip install fonttools). Running it again redraws the
glyphs in place.

  python3 tools/hint_chevrons.py
"""

import math
from pathlib import Path

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
TARGETS = sorted(p for p in (ROOT / "fonts").glob("*.ttf") if p.name.startswith(("DMSans-", "InstrumentSans-", "Onest-")))
PX = 17  # the hint size the measures below are in
WIDTH, HEIGHT = 9, 4.5  # an up or down chevron's ink centreline, px (left and right: HEIGHT by WIDTH)
BEARING, GAP, PAIR = 1, 7, 3  # px: before the ink, from the ink to the next letter, between a pair's two chevrons
STROKE = {"Regular": 1.5, "Medium": 1.65, "SemiBold": 1.8, "Bold": 1.95}
GLYPHS = {0xE100: ("up",), 0xE101: ("down",), 0xE102: ("left",), 0xE103: ("right",), 0xE105: ("up", "down")}
TRAILING = {0xE103}  # drawn after its name: the space before the ink, the bearing after


def capsule(a, b, r):
    """A clockwise outline of the segment a-b with round ends of radius r: (kind, points) steps for a pen."""
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    steps = []

    def arc(centre, start):
        # A half turn clockwise in four quadratic eighths.
        for k in range(4):
            mid, end = start - (k + 0.5) * math.pi / 4, start - (k + 1) * math.pi / 4
            reach = r / math.cos(math.pi / 8)
            steps.append(("q", [(centre[0] + reach * math.cos(mid), centre[1] + reach * math.sin(mid)),
                                (centre[0] + r * math.cos(end), centre[1] + r * math.sin(end))]))

    left = ang + math.pi / 2
    start = (a[0] + r * math.cos(left), a[1] + r * math.sin(left))
    steps.append(("l", [(b[0] + r * math.cos(left), b[1] + r * math.sin(left))]))
    arc(b, left)
    steps.append(("l", [(a[0] - r * math.cos(left), a[1] - r * math.sin(left))]))
    arc(a, left + math.pi)
    return start, steps


def chevron(direction, x, mid, em):
    """The centreline of one chevron starting at x (its ink's left edge less the stroke), centred on mid."""
    w, h = WIDTH * em / PX, HEIGHT * em / PX
    if direction == "up":
        return [(x, mid - h / 2), (x + w / 2, mid + h / 2), (x + w, mid - h / 2)], w
    if direction == "down":
        return [(x, mid + h / 2), (x + w / 2, mid - h / 2), (x + w, mid + h / 2)], w
    if direction == "left":
        return [(x + h, mid + w / 2), (x, mid), (x + h, mid - w / 2)], h
    return [(x, mid + w / 2), (x + h, mid), (x, mid - w / 2)], h


def draw(font, directions, weight, trailing=False):
    em = font["head"].unitsPerEm
    unit = em / PX
    r = STROKE[weight] * unit / 2
    mid = font["OS/2"].sCapHeight / 2
    pen = TTGlyphPen(None)
    x = (GAP if trailing else BEARING) * unit + r
    for n, direction in enumerate(directions):
        if n:
            x += PAIR * unit + 2 * r
        line, size = chevron(direction, x, mid, em)
        for a, b in zip(line, line[1:]):
            start, steps = capsule(a, b, r)
            pen.moveTo(tuple(round(v) for v in start))
            for kind, points in steps:
                points = [tuple(round(v) for v in p) for p in points]
                pen.lineTo(points[0]) if kind == "l" else pen.qCurveTo(*points)
            pen.closePath()
        x += size
    advance = round(x + r + (BEARING if trailing else GAP) * unit)
    return pen.glyph(), advance


def add(path):
    font = TTFont(path)
    weight = path.stem.split("-")[1]
    glyf, hmtx = font["glyf"], font["hmtx"]
    for codepoint, directions in GLYPHS.items():
        name = f"uni{codepoint:04X}"
        glyph, advance = draw(font, directions, weight, codepoint in TRAILING)
        glyf[name] = glyph  # adds it to the glyph order when new
        glyph.recalcBounds(glyf)
        hmtx[name] = (advance, glyph.xMin)
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[codepoint] = name
    font.setGlyphOrder(glyf.glyphOrder)
    for stale in ("hdmx", "LTSH", "VDMX"):  # per-glyph tables that would no longer match the glyph count
        if stale in font:
            del font[stale]
    font.save(path)


def main():
    for path in TARGETS:
        add(path)
        print(f"{path.name}: {len(GLYPHS)} chevrons")


if __name__ == "__main__":
    main()
