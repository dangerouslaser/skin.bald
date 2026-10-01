"""Draw the toasts' icons for Kodi's own notifications into media/: DefaultIconInfo.png, DefaultIconWarning.png and
DefaultIconError.png, the names Kodi gives a toast's icon (CGUIDialogKaiToast) when the caller passes none of its own.

They are Lucide's "info", "triangle-alert" and "circle-x" (lucide.dev, ISC, LICENSE-Lucide.txt at the skin's root),
stroked 1.5 units like the hint keys, in bald_ink on transparent, SIZE px square over Lucide's whole 24 unit grid.
Kodi does not tint a toast's icon (an add-on's icon is its own artwork), so the colour is in the PNG. The pack
inherited from Estuary has its own icons under these names and Kodi reads the pack first, so they are dropped from
it here (tools/xbt.py). Needs rsvg-convert (Homebrew librsvg).

  python3 tools/toast_icons.py
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xbt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "media"
SIZE = 128
INK = "#EFEFEF"  # bald_ink (colors/defaults.xml)
ICONS = {
    "DefaultIconInfo.png": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "DefaultIconWarning.png": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/>'
                              '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    "DefaultIconError.png": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
}


def svg(body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
            f'stroke="{INK}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


def main():
    for name, body in ICONS.items():
        subprocess.run(["rsvg-convert", "-w", str(SIZE), "-h", str(SIZE), "-o", str(OUT / name)],
                       input=svg(body).encode(), check=True)
        print(name)
    names = {name.lower() for name in ICONS}
    if names & {name.lower() for name, _, _ in xbt.read()[1]}:
        print(f"dropped {xbt.drop(names)} from {xbt.PACK.name}")


if __name__ == "__main__":
    main()
