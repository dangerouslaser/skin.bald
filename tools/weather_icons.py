"""Render Bald's built-in weather icons (the default weather icon pack) into media/bald/weather/.

Run: python3 tools/weather_icons.py            (render the committed SVGs)
     python3 tools/weather_icons.py --fetch    (first re-download the SVGs at METEOCONS)

The icons are Meteocons Monochrome by Bas Milius (MIT, https://meteocons.com, npm @meteocons/svg-static), kept as
downloaded in tools/weather_icons/ with their licence, which ships next to the PNGs as LICENSE-Meteocons.txt. Each
Kodi weather code (0-47, the FanartCode Weather.Data() gives) and na get one icon. The PNGs are white on transparent,
SIZE px square with the whole 128 x 128 view box, so every icon keeps the set's own size and placement; the skin tints
them through colordiffuse. Needs rsvg-convert (Homebrew librsvg) and Pillow.
"""
import argparse
import io
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(__file__).resolve().parent / "weather_icons"
OUT = ROOT / "media" / "bald" / "weather"
METEOCONS = "0.1.0"  # pinned @meteocons/svg-static version the committed SVGs came from
SIZE = 256
SS = 4  # rendered 4 x larger and reduced

# Kodi weather code -> Meteocons Monochrome icon. Thunderstorms (1-3) and heavy snow (41, 43) use the plain
# glyphs rather than Meteocons' "extreme" and hurricane ones, so the set reads evenly.
ICONS = {
    0: "tornado",
    1: "thunderstorms-rain",
    2: "thunderstorms-rain",
    3: "thunderstorms",
    4: "thunderstorms-rain",
    5: "sleet",
    6: "sleet",
    7: "sleet",
    8: "drizzle",
    9: "drizzle",
    10: "sleet",
    11: "rain",
    12: "rain",
    13: "snow",
    14: "snow",
    15: "wind-snow",
    16: "snow",
    17: "hail",
    18: "sleet",
    19: "dust",
    20: "fog",
    21: "haze",
    22: "smoke",
    23: "wind",
    24: "wind",
    25: "thermometer-colder",
    26: "cloudy",
    27: "overcast-night",
    28: "overcast-day",
    29: "partly-cloudy-night",
    30: "partly-cloudy-day",
    31: "clear-night",
    32: "clear-day",
    33: "mostly-clear-night",
    34: "mostly-clear-day",
    35: "hail",
    36: "sun-hot",
    37: "thunderstorms-day",
    38: "thunderstorms-day-rain",
    39: "partly-cloudy-day-rain",
    40: "rain",
    41: "snow",
    42: "partly-cloudy-day-snow",
    43: "snow",
    44: "partly-cloudy-day",
    45: "thunderstorms-night-rain",
    46: "partly-cloudy-night-snow",
    47: "thunderstorms-night",
    "na": "not-available",
}


def fetch():
    base = f"https://cdn.jsdelivr.net/npm/@meteocons/svg-static@{METEOCONS}"
    for name in sorted(set(ICONS.values())):
        with urllib.request.urlopen(f"{base}/monochrome/{name}.svg", timeout=30) as response:
            (SRC / f"{name}.svg").write_bytes(response.read())
        print(f"fetched {name}.svg")
    with urllib.request.urlopen(f"{base}/LICENSE", timeout=30) as response:
        (SRC / "LICENSE").write_bytes(response.read())


def render(svg_path):
    # Monochrome Meteocons paint in currentColor (masks and clips use their own black and white): paint it white.
    text = svg_path.read_text().replace("currentColor", "#ffffff")
    png = subprocess.run(["rsvg-convert", "-w", str(SIZE * SS), "-h", str(SIZE * SS), "-f", "png"],
                         input=text.encode(), capture_output=True, check=True).stdout
    big = Image.open(io.BytesIO(png)).convert("RGBA")
    alpha = big.getchannel("A").resize((SIZE, SIZE), Image.LANCZOS)
    out = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
    out.putalpha(alpha)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fetch", action="store_true", help="re-download the Meteocons SVGs first")
    args = parser.parse_args()
    if not shutil.which("rsvg-convert"):
        sys.exit("rsvg-convert not found (brew install librsvg)")
    if args.fetch:
        fetch()
    OUT.mkdir(parents=True, exist_ok=True)
    rendered = {}
    for code, name in ICONS.items():
        if name not in rendered:
            rendered[name] = render(SRC / f"{name}.svg")
        rendered[name].save(OUT / f"{code}.png", optimize=True)
        print(f"{name}.svg -> media/bald/weather/{code}.png")
    shutil.copyfile(SRC / "LICENSE", OUT / "LICENSE-Meteocons.txt")


if __name__ == "__main__":
    main()
