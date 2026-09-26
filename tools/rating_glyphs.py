"""Render the rating pills' source glyphs (Includes_Bald_Ratings.xml) into media/bald/ratings/.

Run: python3 tools/rating_glyphs.py            (render the committed SVGs)
     python3 tools/rating_glyphs.py --fetch    (first re-download the Simple Icons SVGs at SIMPLE_ICONS)

Sources live in tools/rating_glyphs/: brand marks from Simple Icons (CC0 1.0, https://simpleicons.org; the marks
themselves remain their owners' trademarks and are used only to name the source of a score), and Bald's own glyphs
for sources Simple Icons has no mark for. Every glyph is drawn on a 24 x 24 view box. The PNGs are white on
transparent, SIZE px square, and the skin tints them with a palette token through colordiffuse. Needs rsvg-convert
(Homebrew librsvg) and Pillow.
"""
import argparse
import io
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(__file__).resolve().parent / "rating_glyphs"
OUT = ROOT / "media" / "bald" / "ratings"
SIMPLE_ICONS = "16.32.0"  # pinned npm version the committed brand SVGs came from
# 2 x the largest display size (20 px on the information screens' 30 px pill); rendered 4 x larger and reduced.
SIZE = 40
SS = 4

# PNG name -> (SVG in tools/rating_glyphs, Simple Icons slug or None for a Bald glyph).
GLYPHS = {
    "imdb": ("imdb.svg", "imdb"),
    "tmdb": ("themoviedatabase.svg", "themoviedatabase"),
    "rt": ("rottentomatoes.svg", "rottentomatoes"),
    "metacritic": ("metacritic.svg", "metacritic"),
    "trakt": ("trakt.svg", "trakt"),
    "jellyfin": ("jellyfin.svg", "jellyfin"),
    "kodi": ("kodi.svg", "kodi"),
    "rt_audience": ("popcorn.svg", None),
    "tvdb": ("tv.svg", None),
    "you": ("you.svg", None),
    "rating": ("star.svg", None),
}


def fetch():
    for svg, slug in GLYPHS.values():
        if slug:
            url = f"https://cdn.jsdelivr.net/npm/simple-icons@{SIMPLE_ICONS}/icons/{slug}.svg"
            with urllib.request.urlopen(url) as response:
                (SRC / svg).write_bytes(response.read())
            print(f"fetched {slug} -> {svg}")


def render(svg_path):
    text = svg_path.read_text()
    # Simple Icons SVGs carry no fill (black by default): paint the whole mark white.
    text = re.sub(r"<svg\b", '<svg fill="#ffffff"', text, count=1)
    png = subprocess.run(["rsvg-convert", "-w", str(SIZE * SS), "-h", str(SIZE * SS), "-f", "png"],
                         input=text.encode(), capture_output=True, check=True).stdout
    big = Image.open(io.BytesIO(png)).convert("RGBA")
    alpha = big.getchannel("A").resize((SIZE, SIZE), Image.LANCZOS)
    out = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
    out.putalpha(alpha)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fetch", action="store_true", help="re-download the Simple Icons SVGs first")
    args = parser.parse_args()
    if not shutil.which("rsvg-convert"):
        sys.exit("rsvg-convert not found (brew install librsvg)")
    if args.fetch:
        fetch()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (svg, _slug) in GLYPHS.items():
        render(SRC / svg).save(OUT / f"{name}.png", optimize=True)
        print(f"{svg} -> media/bald/ratings/{name}.png")


if __name__ == "__main__":
    main()
