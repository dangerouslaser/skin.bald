"""Generate skin.bald's small UI textures into media/bald/. Run: python3 tools/textures.py"""
import math
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "media" / "bald"
SS = 8  # supersampling factor for anti-aliased shapes


def rounded(w, h, r, stroke=None, inset=0.0):
    """White rounded rect (filled, or a ring of `stroke` px) with AA."""
    im = Image.new("L", (w * SS, h * SS), 0)
    d = ImageDraw.Draw(im)
    box = [inset * SS, inset * SS, (w - inset) * SS - 1, (h - inset) * SS - 1]
    if stroke:
        d.rounded_rectangle(box, r * SS, outline=255, width=round(stroke * SS))
    else:
        d.rounded_rectangle(box, r * SS, fill=255)
    a = im.resize((w, h), Image.LANCZOS)
    out = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    out.putalpha(a)
    return out


def save(im, name):
    im.save(OUT / name, optimize=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    save(Image.new("RGBA", (8, 8), (255, 255, 255, 255)), "white.png")
    dot = Image.new("L", (64 * SS, 64 * SS), 0)
    ImageDraw.Draw(dot).ellipse([0, 0, 64 * SS - 1, 64 * SS - 1], fill=255)
    im = Image.new("RGBA", (64, 64), (255, 255, 255, 0)); im.putalpha(dot.resize((64, 64), Image.LANCZOS))
    save(im, "dot.png")
    # Tile: 176x99, 3 px corners. Used as the placeholder fill and as the art's diffuse mask.
    save(rounded(176, 99, 3), "tile.png")
    # Focus ring: 3 px ring outside a 3 px-radius tile. 9-slice, border 8.
    save(rounded(24, 24, 6, stroke=3), "focus_ring.png")
    # Media flag chip outline: 1.5 px, radius 5. 9-slice, border 6.
    save(rounded(16, 16, 5, stroke=1.5, inset=0.25), "chip.png")
    # Logo scrim: CSS linear-gradient(32deg, black 60% at 0, 26% at 30%, 0 at 54%) at half size.
    w, h = 624, 351
    a = math.radians(32)
    dx, dy = math.sin(a), -math.cos(a)
    L = abs(w * dx) + abs(h * dy)
    stops = [(0.0, 0.60), (0.30, 0.26), (0.54, 0.0), (1.0, 0.0)]
    im = Image.new("RGBA", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            t = ((x + 0.5 - w / 2) * dx + (y + 0.5 - h / 2) * dy) / L + 0.5
            for (t0, a0), (t1, a1) in zip(stops, stops[1:]):
                if t <= t1:
                    v = a0 + (a1 - a0) * max(0.0, (t - t0) / (t1 - t0))
                    break
            px[x, y] = (0, 0, 0, round(v * 255))
    save(im, "scrim_logo.png")


if __name__ == "__main__":
    main()
