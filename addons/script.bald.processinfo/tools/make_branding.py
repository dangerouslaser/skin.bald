#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Draw Bald Process Info's own artwork into branding/.

TinyPPI's name, logo and original artwork are not licensed for forks (see
upstream's LICENSE-ASSETS), so this fork ships its own: every file below is
drawn here, or rendered from Lucide icons (ISC, branding/_src/lucide/LICENSE).
tools/fork_branding.py copies branding/ over the upstream tree.

Needs Pillow and rsvg-convert (librsvg). Run from the repository root:
    python3 tools/make_branding.py
The output is committed; this only has to run again when the artwork changes.
"""

import io
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "branding"
SRC = OUT / "_src"
LUCIDE = SRC / "lucide"
FONT = SRC / "fonts" / "DMSans-SemiBold.ttf"
MEDIA = OUT / "resources" / "skins" / "Default" / "media"
WEB_ICONS = OUT / "resources" / "web" / "icons"

WHITE = (255, 255, 255, 255)
FIELD = (11, 12, 16, 255)        # Bald's page colour
SS = 4                           # supersampling factor for hand-drawn shapes


def font(size):
    return ImageFont.truetype(str(FONT), size)


def canvas(w, h, scale=SS):
    im = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def save(im, path, size=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if size and im.size != size:
        im = im.resize(size, Image.LANCZOS)
    im.save(path, optimize=True)


# --- Lucide icons ----------------------------------------------------------

def lucide_svg(name, stroke_width=2.0, filled=False):
    text = (LUCIDE / f"{name}.svg").read_text()
    text = text.replace('stroke="currentColor"', 'stroke="#fff"')
    text = text.replace('stroke-width="2"', f'stroke-width="{stroke_width}"')
    if filled:
        text = text.replace('fill="none"', 'fill="#fff"')
    # Drop the size attributes' class noise but keep the licence comment.
    return text


def render_svg(svg_text, size):
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(svg_text)
        name = f.name
    png = subprocess.check_output(["rsvg-convert", "-w", str(size), "-h", str(size), name])
    Path(name).unlink()
    return Image.open(io.BytesIO(png)).convert("RGBA")


# Web dashboard icons: file name -> (lucide icon, filled)
WEB = {
    "chapter-next": ("skip-forward", True),
    "chapter-previous": ("skip-back", True),
    "check": ("check", False),
    "chevron-down": ("chevron-down", False),
    "download": ("download", False),
    "key": ("key-round", False),
    "no": ("circle-x", False),
    "yes": ("circle-check", False),
    "pause": ("pause", True),
    "play": ("play", True),
    "stop": ("square", True),
    "star": ("star", True),
    "tab-films": ("film", False),
    "tab-history": ("history", False),
    "tab-live": ("radio", False),
    "tab-metadata": ("file-code-2", False),
    "tab-series": ("tv", False),
    "tab-settings": ("settings", False),
    "theme-adaptive": ("sun-moon", False),
    "theme-dark": ("moon", False),
    "theme-midnight": ("moon-star", False),
    "volume": ("volume-2", False),
    "volume-muted": ("volume-x", False),
}

# Overlay icons (64 px, white; the skin tints them): file -> lucide icon
ICONS = {
    "arrow-progress": "sliders-horizontal",
    "camcorder": "video",
    "chart": "chart-no-axes-column",
    "check-circle": "circle-check",
    "circle-xmark": "circle-x",
    "layer-group": "layers",
    "memory": "memory-stick",
    "volume": "volume-2",
}


def make_icons():
    for name, (icon, filled) in WEB.items():
        path = WEB_ICONS / f"{name}.svg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(lucide_svg(icon, filled=filled))

    for name, icon in ICONS.items():
        save(render_svg(lucide_svg(icon, stroke_width=2.25), 64), MEDIA / "icons" / f"{name}.png")

    # L5 active-area icon: horizontal and vertical extents side by side.
    lrtb = Image.new("RGBA", (143, 67), (0, 0, 0, 0))
    lrtb.alpha_composite(render_svg(lucide_svg("move-horizontal", 2.25), 67), (0, 0))
    lrtb.alpha_composite(render_svg(lucide_svg("move-vertical", 2.25), 67), (76, 0))
    save(lrtb, MEDIA / "icons" / "lrtb.png")

    # VS10 badge: a ring with the engine's name set in DM Sans.
    im, d = canvas(64, 64)
    s = SS
    d.ellipse((2 * s, 2 * s, 62 * s, 62 * s), outline=WHITE, width=4 * s)
    f = font(17 * s)
    for text, y in (("VS", 21), ("10", 42)):
        d.text((32 * s, y * s), text, font=f, fill=WHITE, anchor="mm")
    save(im, MEDIA / "icons" / "vs10.png", (64, 64))

    for side, icon in (("left", "chevron-left"), ("right", "chevron-right")):
        save(render_svg(lucide_svg(icon, stroke_width=3), 32), MEDIA / "dialog" / f"arrow-{side}.png")


# --- Shapes ----------------------------------------------------------------

CAP_RADIUS = 18


def make_shapes():
    # Panel end caps: the skin stretches a flat middle between a start and an end.
    for panel, h in (("channels", 265), ("dialog", 546), ("dv-overlay", 1000), ("overlay", 665)):
        for end in ("start", "end"):
            im, d = canvas(23, h)
            r = CAP_RADIUS * SS
            if end == "start":
                d.rounded_rectangle((0, 0, 23 * SS + 2 * r, h * SS - 1), radius=r, fill=WHITE)
            else:
                d.rounded_rectangle((-2 * r, 0, 23 * SS - 1, h * SS - 1), radius=r, fill=WHITE)
            save(im, MEDIA / "background" / f"{panel}-bg-{end}.png", (23, h))

    # Splash corners: quarter discs that round the splash panel's corners.
    for corner in ("tl", "tr", "bl", "br"):
        im, d = canvas(48, 48)
        e = 48 * SS
        cx = e if corner[1] == "l" else 0
        cy = e if corner[0] == "t" else 0
        d.ellipse((cx - e, cy - e, cx + e, cy + e), fill=WHITE)
        save(im, MEDIA / "splash" / f"corner-{corner}.png", (48, 48))

    def pill(w, h, path):
        im, d = canvas(w, h)
        d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), radius=h * SS // 2, fill=WHITE)
        save(im, path, (w, h))

    pill(280, 80, MEDIA / "common" / "button-white.png")
    pill(670, 100, MEDIA / "common" / "pill.png")
    pill(1360, 12, MEDIA / "progress" / "bar.png")

    im, d = canvas(64, 64)
    d.ellipse((1 * SS, 1 * SS, 63 * SS, 63 * SS), fill=WHITE)
    save(im, MEDIA / "common" / "dot-circle.png", (64, 64))

    save(Image.new("RGBA", (1, 1), WHITE), MEDIA / "common" / "dot-1x1.png")


# --- Speaker layouts -------------------------------------------------------
#
# A plan view: the room seen from above, the screen wall at the top, one seat
# in the middle.  Positions are fractions of the room (x across, y front to
# back); "sub" is drawn as a block, "top" as a ring (a ceiling speaker).

SPEAKERS = {
    "FL": (0.28, 0.14, "spk"), "FR": (0.72, 0.14, "spk"), "C": (0.50, 0.10, "spk"),
    "SW": (0.12, 0.16, "sub"),
    "SL": (0.08, 0.56, "spk"), "SR": (0.92, 0.56, "spk"),
    "SBL": (0.27, 0.90, "spk"), "SBR": (0.73, 0.90, "spk"), "SB": (0.50, 0.92, "spk"),
    "TL": (0.34, 0.46, "top"), "TR": (0.66, 0.46, "top"),
}
LAYOUTS = {
    "1.0": ("C",),
    "2.0": ("FL", "FR"),
    "2.1": ("FL", "FR", "SW"),
    "3.1": ("FL", "C", "FR", "SW"),
    "4.1": ("FL", "FR", "SL", "SR", "SW"),
    "5.1": ("FL", "C", "FR", "SL", "SR", "SW"),
    "6.1": ("FL", "C", "FR", "SL", "SR", "SB", "SW"),
    "7.1": ("FL", "C", "FR", "SL", "SR", "SBL", "SBR", "SW"),
    "5.1.2": ("FL", "C", "FR", "SL", "SR", "SW", "TL", "TR"),
    "7.1.2": ("FL", "C", "FR", "SL", "SR", "SBL", "SBR", "SW", "TL", "TR"),
}


def _room(w, h):
    """The room rectangle inside a w x h box, in supersampled pixels."""
    pad_x, pad_y = w * 0.09, h * 0.11
    return (pad_x * SS, pad_y * SS, (w - pad_x) * SS, (h - pad_y) * SS)


def _at(room, fx, fy):
    x0, y0, x1, y1 = room
    return x0 + (x1 - x0) * fx, y0 + (y1 - y0) * fy


def make_layer(w, h, folder):
    im, d = canvas(w, h)
    room = _room(w, h)
    line = max(2, round(w / 200)) * SS
    d.rounded_rectangle(room, radius=14 * SS, outline=WHITE, width=line)
    # The screen along the front wall.
    sx0, sy = _at(room, 0.36, 0.0)
    sx1, _ = _at(room, 0.64, 0.0)
    d.line((sx0, sy + 6 * SS, sx1, sy + 6 * SS), fill=WHITE, width=line * 2)
    # The seat.
    cx, cy = _at(room, 0.5, 0.62)
    sw, sh = w * 0.09 * SS, h * 0.07 * SS
    d.rounded_rectangle((cx - sw, cy - sh / 2, cx + sw, cy + sh / 2), radius=6 * SS, outline=WHITE, width=line)
    save(im, MEDIA / "channels" / folder / "layer.png", (w, h))


def make_layout(w, h, folder, name, speakers):
    im, d = canvas(w, h)
    room = _room(w, h)
    unit = w / 400                       # 1.0 at the small size
    f = font(round(13 * unit * SS))
    for key in speakers:
        fx, fy, kind = SPEAKERS[key]
        x, y = _at(room, fx, fy)
        if kind == "top":
            r = 11 * unit * SS
            d.ellipse((x - r, y - r, x + r, y + r), outline=WHITE, width=round(3 * unit * SS))
            d.ellipse((x - r / 3, y - r / 3, x + r / 3, y + r / 3), fill=WHITE)
        elif kind == "sub":
            s = 13 * unit * SS
            d.rounded_rectangle((x - s, y - s, x + s, y + s), radius=4 * unit * SS, fill=WHITE)
        else:
            s = 9 * unit * SS
            d.rounded_rectangle((x - s, y - s, x + s, y + s), radius=3 * unit * SS, fill=WHITE)
        # Label beside or below the mark, whichever keeps it inside the room.
        label_y = y + 24 * unit * SS if fy < 0.8 else y - 24 * unit * SS
        d.text((x, label_y), key, font=f, fill=WHITE, anchor="mm")
    save(im, MEDIA / "channels" / folder / f"{name}.png", (w, h))


def make_channels():
    for w, h in ((400, 241), (495, 298)):
        folder = f"{w}x{h}"
        make_layer(w, h, folder)
        for name, speakers in LAYOUTS.items():
            make_layout(w, h, folder, name, speakers)


# --- Icon and fanart -------------------------------------------------------

def mark(d, x, y, unit):
    """Bald Process Info's mark: three readout rows and a status dot."""
    for i, length in enumerate((1.0, 0.72, 0.86)):
        top = y + i * 1.9 * unit
        d.rounded_rectangle((x, top, x + 9 * unit * length, top + unit), radius=unit / 2, fill=WHITE)
    d.ellipse((x + 9.8 * unit, y + 3.8 * unit, x + 10.8 * unit, y + 4.8 * unit), fill=WHITE)


def make_icon():
    im = Image.new("RGBA", (512 * SS, 512 * SS), FIELD)
    d = ImageDraw.Draw(im)
    mark(d, 118 * SS, 150 * SS, 26 * SS)
    d.text((256 * SS, 400 * SS), "process info", font=font(46 * SS), fill=(236, 238, 242, 255), anchor="mm")
    save(im.convert("RGB"), OUT / "icon.png", (512, 512))


def make_fanart():
    im = Image.new("RGBA", (1920 * 2, 1080 * 2), FIELD)
    d = ImageDraw.Draw(im)
    mark(d, 180 * 2, 330 * 2, 34 * 2)
    d.text((180 * 2, 650 * 2), "Bald Process Info", font=font(96 * 2), fill=(236, 238, 242, 255), anchor="ls")
    d.text((180 * 2, 730 * 2), "What your player is doing, while it does it.", font=font(40 * 2),
           fill=(236, 238, 242, 150), anchor="ls")
    save(im.convert("RGB"), OUT / "fanart.png", (1920, 1080))


def main():
    make_icons()
    make_shapes()
    make_channels()
    make_icon()
    make_fanart()
    print(f"branding written to {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
