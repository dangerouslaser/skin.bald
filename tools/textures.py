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
    # Rating pill: the chip's shape filled, drawn at 10% ink (Includes_Bald_Ratings.xml). 9-slice, border 6.
    save(rounded(16, 16, 5, inset=0.25), "chip_fill.png")
    # The same pill in two halves, so a rating pill can put its source glyph (an image) before its value (an auto-width
    # button): the left end, rounded on the left only (border 6,6,0,6), and the right part (border 0,6,6,6). Cut from
    # a 32 px pill so the cut edge is fully filled.
    wide = rounded(32, 16, 5, inset=0.25)
    save(wide.crop((0, 0, 16, 16)), "chip_fill_l.png")
    save(wide.crop((16, 0, 32, 16)), "chip_fill_r.png")
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
    # A chapter or scene break on the seek track (Bald_PlaybackTrackMarks): a 2 px square-ended separator, tinted
    # bald_field so the line reads as segments. bar.png's 8 px rounded ends drew 8 px black blocks across the line.
    save(Image.new("RGBA", (2, 4), (255, 255, 255, 255)), "bar_gap.png")

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
    # In-progress clock, the check's companion on tiles: Lucide's clock (circle r 10 at 12,12; hands 12,6 / 12,12 /
    # 16,14) drawn smaller (r 8.5, hands 12,7.5 / 12,12 / 15.5,14) so the check's 2.6 stroke fits the same 24 units.
    mark = Image.new("L", (size * SS, size * SS), 0)
    d = ImageDraw.Draw(mark)
    r = 8.5 * k
    d.ellipse([12 * k - r, 12 * k - r, 12 * k + r, 12 * k + r], outline=255, width=width)
    pts = [(12 * k, 7.5 * k), (12 * k, 12 * k), (15.5 * k, 14 * k)]
    d.line(pts, fill=255, width=width, joint="curve")
    for x, y in (pts[0], pts[-1]):
        d.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=255)
    im = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    im.putalpha(mark.resize((size, size), Image.LANCZOS))
    save(im, "clock.png")
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
    guide_textures()
    osd_scrims()


def osd_scrims():
    """The player's gradients (Includes_Bald_OSD.xml, Includes_Bald_Playback.xml), cut to the rows they darken.
    They were scrim_info_b stretched: 85% black at the edge to 0 at 42% of the image's height, so most of each image
    was clear and still blended on every frame the OSD drew, which slow GPUs feel during playback. Each is now drawn
    1:1 at its own height:
      scrim_osd_short  the bar alone: 660 px stretched, clear above 277 px.
      scrim_osd_tall   the controls, a panel or the info overlay: the 1280 px stretch (clear above 538 px) with the short
                       one over it, blended into one image so the two are never drawn together.
      scrim_osd_top    the top edge behind the clock and view-mode lines: 640 px stretched and flipped, clear below 269.
    White, tinted by the skin (bald_scrim)."""
    def ramp(d, reach):
        return max(0.0, 0.85 * (1 - d / reach))

    def strip(alphas, name, from_bottom=True):
        im = Image.new("RGBA", (4, len(alphas)), (255, 255, 255, 0))
        for d, a in enumerate(alphas):
            y = len(alphas) - 1 - d if from_bottom else d
            for x in range(4):
                im.putpixel((x, y), (255, 255, 255, round(a * 255)))
        save(im, name)

    short, tall = 0.42 * 660, 0.42 * 1280
    strip([ramp(d + 0.5, short) for d in range(math.ceil(short))], "scrim_osd_short.png")
    strip([1 - (1 - ramp(d + 0.5, tall)) * (1 - ramp(d + 0.5, short)) for d in range(math.ceil(tall))],
          "scrim_osd_tall.png")
    top = 0.42 * 640
    strip([ramp(d + 0.5, top) for d in range(math.ceil(top))], "scrim_osd_top.png", from_bottom=False)


def guide_textures():
    """The TV guide (Bald_EpgGrid, Includes_PVR.xml): a programme cell, 32 px with 6 px corners, stretched with border 8;
    and the now line, the grid's progress texture, which Kodi stretches over all the elapsed time with border 0,0,2,0
    so only its 2 px right edge shows. Its clear body is 256 px wide: the old 4 px one was stretched about a hundred
    times, and the filtering smeared the lit edge into a dark band tens of pixels wide beside the line. Clear pixels
    are zero in RGB too, or the scaler samples the hidden white into a halo."""
    save(rounded(32, 32, 6), "epg_cell.png")
    im = Image.new("RGBA", (258, 4), (0, 0, 0, 0))
    im.paste((255, 255, 255, 255), (256, 0, 258, 4))
    save(im, "epg_nowline.png")


if __name__ == "__main__":
    main()
