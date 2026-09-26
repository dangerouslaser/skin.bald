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
    # Fully transparent 16 px square: the bar texture for sliders whose bar is not drawn. Kodi scales a slider's nib
    # by the control height over this texture's height, so it matches slider_nib.png (16 px) for a 1:1 nib.
    save(Image.new("RGBA", (16, 16), (0, 0, 0, 0)), "slider_clear.png")
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

    # ---- Info dialog (docs/SPEC.md 5.2) ----
    # Horizontal scrim: field 92% at 0, 72% at 32%, 0 at 64% (white; colorized with colordiffuse).
    def ramp(n, stops):
        out = []
        for i in range(n):
            t = (i + 0.5) / n
            for (t0, a0), (t1, a1) in zip(stops, stops[1:]):
                if t <= t1:
                    out.append(a0 + (a1 - a0) * max(0.0, (t - t0) / (t1 - t0)))
                    break
        return out
    h = ramp(1920, [(0.0, 0.92), (0.32, 0.72), (0.64, 0.0), (1.0, 0.0)])
    im = Image.new("RGBA", (1920, 4))
    for x, a in enumerate(h):
        for y in range(4):
            im.putpixel((x, y), (255, 255, 255, round(a * 255)))
    save(im, "scrim_info_h.png")
    # Bottom scrim: field 85% at the bottom edge, 0 at 42% up.
    v = ramp(1080, [(0.0, 0.85), (0.42, 0.0), (1.0, 0.0)])
    im = Image.new("RGBA", (4, 1080))
    for y, a in enumerate(v):
        for x in range(4):
            im.putpixel((x, 1079 - y), (255, 255, 255, round(a * 255)))
    save(im, "scrim_info_b.png")
    # Action pills: 54 px tall, fully rounded. 9-slice border 27.
    save(rounded(54, 54, 27), "pill.png")
    save(rounded(54, 54, 27, stroke=1.5), "pill_outline.png")
    # Cast: 112 px circle (mask and placeholder) and a 3 px ring outside it (118 px).
    save(rounded(112, 112, 56), "circle_112.png")
    save(rounded(118, 118, 59, stroke=3), "ring_118.png")
    # More like this: 256 x 144 tile, 4 px corners.
    save(rounded(256, 144, 4), "tile_256.png")
    # Context menu focus marker: the Home menu's 10 px accent dot, vertically centred at the left of a 440 x 56 item.
    im = Image.new("RGBA", (440, 56), (255, 255, 255, 0))
    d = dot.resize((10, 10), Image.LANCZOS)
    im.paste((255, 255, 255, 255), (0, 23), d)
    save(im, "menu_dot.png")
    # Progress track and bar: 4 px, rounded. 9-slice border 2.
    save(rounded(8, 4, 2), "bar.png")

    # EPG "now" progress: Kodi stretches this texture over all elapsed time.
    # Keep the stretchable body transparent and preserve only the 1 px right edge
    # (with border="0,0,1,0"). A wider edge is softened by Kodi's filtering and
    # reads as a glow rather than a precise point in time.
    # Zero RGB as well as alpha in the transparent body. Kodi's EPG texture
    # scaler can otherwise sample the hidden white channels into a soft halo.
    im = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).line([(3, 0), (3, 3)], fill=(255, 255, 255, 255), width=1)
    save(im, "epg_now.png")
    tv_info_textures()


def tv_info_textures():
    """TV info episode cards (docs/SPEC.md 5.3)."""
    # Card scrim: black 72% at the bottom edge, 0 at 55% up (white; colorized with colordiffuse).
    im = Image.new("RGBA", (4, 180))
    for y in range(180):
        t = (y + 0.5) / 180
        a = 0.72 * max(0.0, 1 - t / 0.55)
        for x in range(4):
            im.putpixel((x, 179 - y), (255, 255, 255, round(a * 255)))
    save(im, "scrim_card.png")
    # Watched check: the prototype's 24-unit path (5,12.5 / 9.5,17 / 19,7.5), 2.6 stroke, round caps, drawn for 16 px.
    size, scale = 48, 2
    mark = Image.new("L", (size * SS, size * SS), 0)
    d = ImageDraw.Draw(mark)
    k = scale * SS
    pts = [(5 * k, 12.5 * k), (9.5 * k, 17 * k), (19 * k, 7.5 * k)]
    width = round(2.6 * k)
    d.line(pts, fill=255, width=width, joint="curve")
    for x, y in (pts[0], pts[-1]):
        d.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=255)
    im = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    im.putalpha(mark.resize((size, size), Image.LANCZOS))
    save(im, "check.png")
    settings_textures()


def settings_textures():
    """Kodi's settings pages (SettingsCategory.xml templates): spinner arrows and the slider."""
    # Spinner arrow: a right-pointing chevron in a 32 px square, drawn for 16 px (2 px stroke, round caps).
    # The left arrow is the same texture with flipx.
    size, k = 32, 2 * SS
    mark = Image.new("L", (size * SS, size * SS), 0)
    d = ImageDraw.Draw(mark)
    pts = [(6 * k, 3.5 * k), (10.5 * k, 8 * k), (6 * k, 12.5 * k)]
    width = round(2 * k)
    d.line(pts, fill=255, width=width, joint="curve")
    for x, y in (pts[0], pts[-1]):
        d.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=255)
    im = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    im.putalpha(mark.resize((size, size), Image.LANCZOS))
    save(im, "chevron.png")
    # Slider track: a 4 px rounded line centred in a 16 px tall texture, so the 16 px nib keeps its size (Kodi scales
    # the nib by the control height over the track texture's height). 9-slice border 8,0,8,0.
    im = Image.new("RGBA", (16, 16), (255, 255, 255, 0))
    im.paste(rounded(16, 4, 2), (0, 6))
    save(im, "slider_bar.png")
    # Slider nib: a 16 px dot.
    save(rounded(16, 16, 8), "slider_nib.png")
    playback_textures()


def playback_textures():
    """Player OSD icon buttons (Includes_Bald_Playback.xml): the focus texture of a 64 x 84 button, transparent but
    for an 8 px dot centred under the 56 px icon (x 28-36, y 70-78). Drawn at its own size, so no border."""
    im = Image.new("RGBA", (64, 84), (255, 255, 255, 0))
    mark = Image.new("L", (8 * SS, 8 * SS), 0)
    ImageDraw.Draw(mark).ellipse([0, 0, 8 * SS - 1, 8 * SS - 1], fill=255)
    im.paste((255, 255, 255, 255), (28, 70), mark.resize((8, 8), Image.LANCZOS))
    save(im, "osd_focus.png")
    osd_textures()


def osd_textures():
    """Video OSD buttons (Includes_Bald_OSD.xml): the focus texture of an 80 x 96 button, a 72 px disc centred at the
    top (x 4-76, y 0-72) behind the 48 px icon, transparent below where the language code sits. Drawn at its own size,
    so no border."""
    im = Image.new("RGBA", (80, 96), (255, 255, 255, 0))
    disc = Image.new("L", (72 * SS, 72 * SS), 0)
    ImageDraw.Draw(disc).ellipse([0, 0, 72 * SS - 1, 72 * SS - 1], fill=255)
    im.paste((255, 255, 255, 255), (4, 0), disc.resize((72, 72), Image.LANCZOS))
    save(im, "osd_disc.png")


if __name__ == "__main__":
    main()
