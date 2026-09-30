#!/usr/bin/env python3
"""Draw the remote's keys into Bald's UI fonts, so a hint shows the key it names instead of spelling it out
("▼ Cast & details", "○ Play", "↶ Close").

Kodi draws a label with one font file (CGUIFontTTF), so a key in a hint either comes from the font or has to be a
separate image lined up by hand in every font. These glyphs, in the Private Use Area, are drawn to Bald's hint type
(Bald_Hint, 17 px) and centred on the capitals, with the space to the name built into the advance, so "key + name"
needs no space and reads the same in every font and size.

    U+E100  Up      filled triangle            U+E106  Select  circle (Lucide "circle")
    U+E101  Down    filled triangle            U+E107  Back    Lucide "undo-2"
    U+E102  Left    filled triangle            U+E108  Info    Lucide "info"
    U+E103  Right   filled triangle, after     U+E109  Menu    Lucide "menu"
    U+E105  Up and down, the two triangles

The arrows are solid triangles 9 by 5.5 px. The other keys follow Lucide's outlines (lucide.dev, ISC licence) on its
24 unit grid, at 0.525 px a unit (the circle's outer edge about the capital height), stroked 1.5 px with round ends
like the text's stems (a little heavier in the heavier weights). A Right key follows its name ("Scroll by letters ▶"),
so its space comes before it: hints read left to right, Left's first and Right's last.

The skin writes them through $VAR[Bald_KeyUp] and the other Bald_Key* variables (Includes_Bald_Common.xml).
DM Sans, Instrument Sans and Onest are SIL OFL 1.1 without a Reserved Font Name, so the modified fonts keep their
names (as with tools/add_superscripts.py). Needs fontTools (pip install fonttools). Run it on the fonts as committed
before the keys were added, or again on these, which redraws the glyphs in place.

  python3 tools/hint_keys.py
"""

import math
from pathlib import Path

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
TARGETS = sorted(p for p in (ROOT / "fonts").glob("*.ttf") if p.name.startswith(("DMSans-", "InstrumentSans-", "Onest-")))
PX = 17  # the hint size the measures below are in
BASE, HEIGHT = 9, 5.5  # an up or down triangle, px (left and right: HEIGHT wide, BASE tall)
BEARING, GAP, PAIR = 1, 7, 3  # px: before the ink, from the ink to the name, between the up-and-down pair's triangles
UNIT = 0.525  # px per Lucide unit
STROKE = {"Regular": 1.5, "Medium": 1.65, "SemiBold": 1.8, "Bold": 1.95}


def arc(cx, cy, r, start, end, steps):
    return [(cx + r * math.cos(start + (end - start) * i / steps), cy + r * math.sin(start + (end - start) * i / steps))
            for i in range(steps + 1)]


# Lucide outlines, 24 unit grid with y down: polylines, each drawn with a round stroke.
ICONS = {
    "select": [arc(12, 12, 10, 0, 2 * math.pi, 48)],
    "back": [[(9, 14), (4, 9), (9, 4)], [(4, 9), (14.5, 9)] + arc(14.5, 14.5, 5.5, -math.pi / 2, math.pi / 2, 16)[1:] + [(11, 20)]],
    "info": [arc(12, 12, 10, 0, 2 * math.pi, 48), [(12, 16), (12, 12)], [(12, 8), (12, 8)]],
    "menu": [[(4, 6), (20, 6)], [(4, 12), (20, 12)], [(4, 18), (20, 18)]],
}
GLYPHS = {0xE100: ("up",), 0xE101: ("down",), 0xE102: ("left",), 0xE103: ("right",), 0xE105: ("up", "down"),
          0xE106: ("select",), 0xE107: ("back",), 0xE108: ("info",), 0xE109: ("menu",)}
TRAILING = {0xE103}  # drawn after its name: the space before the ink, the bearing after


def capsule(pen, a, b, r):
    """A clockwise outline of the segment a-b with round ends of radius r (a dot when a is b)."""
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    left = ang + math.pi / 2
    point = lambda c, t: (round(c[0] + r * math.cos(t)), round(c[1] + r * math.sin(t)))
    reach = r / math.cos(math.pi / 8)

    def half_turn(c, start):  # clockwise, in four quadratic eighths
        for k in range(4):
            mid, end = start - (k + 0.5) * math.pi / 4, start - (k + 1) * math.pi / 4
            pen.qCurveTo((round(c[0] + reach * math.cos(mid)), round(c[1] + reach * math.sin(mid))), point(c, end))

    pen.moveTo(point(a, left))
    pen.lineTo(point(b, left))
    half_turn(b, left)
    pen.lineTo(point(a, left + math.pi))
    half_turn(a, left + math.pi)
    pen.closePath()


def triangle(pen, direction, x, mid, unit):
    b, h = BASE * unit, HEIGHT * unit
    points = {"up": [(x, mid - h / 2), (x + b / 2, mid + h / 2), (x + b, mid - h / 2)],
              "down": [(x, mid + h / 2), (x + b, mid + h / 2), (x + b / 2, mid - h / 2)],
              "left": [(x, mid), (x + h, mid + b / 2), (x + h, mid - b / 2)],
              "right": [(x, mid + b / 2), (x + h, mid), (x, mid - b / 2)]}[direction]
    pen.moveTo(tuple(round(v) for v in points[0]))
    for p in points[1:]:
        pen.lineTo(tuple(round(v) for v in p))
    pen.closePath()
    return b if direction in ("up", "down") else h


def icon(pen, name, x, mid, unit, r):
    """A Lucide outline with its left ink edge at x; returns the ink width."""
    k = UNIT * unit
    lines = ICONS[name]
    xs = [p[0] for line in lines for p in line]
    left = min(xs)
    for line in lines:
        pts = [(x + r + (px - left) * k, mid - (py - 12) * k) for px, py in line]
        for a, b in zip(pts, pts[1:]):
            capsule(pen, a, b, r)
    return (max(xs) - left) * k + 2 * r


def draw(font, parts, weight, trailing=False):
    unit = font["head"].unitsPerEm / PX
    r = STROKE[weight] * unit / 2
    mid = font["OS/2"].sCapHeight / 2
    pen = TTGlyphPen(None)
    x = (GAP if trailing else BEARING) * unit
    for n, part in enumerate(parts):
        if n:
            x += PAIR * unit
        x += icon(pen, part, x, mid, unit, r) if part in ICONS else triangle(pen, part, x, mid, unit)
    advance = round(x + (BEARING if trailing else GAP) * unit)
    return pen.glyph(), advance


def add(path):
    font = TTFont(path)
    weight = path.stem.split("-")[1]
    glyf, hmtx = font["glyf"], font["hmtx"]
    for codepoint, parts in GLYPHS.items():
        name = f"uni{codepoint:04X}"
        glyph, advance = draw(font, parts, weight, codepoint in TRAILING)
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
        print(f"{path.name}: {len(GLYPHS)} keys")


if __name__ == "__main__":
    main()
