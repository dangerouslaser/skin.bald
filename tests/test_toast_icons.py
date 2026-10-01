"""Kodi's own toasts take Bald's icons (tools/toast_icons.py): the PNGs in media/, and none under those names in the
pack inherited from Estuary, which Kodi reads before the loose files."""

import sys
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import xbt  # noqa: E402

NAMES = ("DefaultIconInfo.png", "DefaultIconWarning.png", "DefaultIconError.png")


class ToastIconTests(unittest.TestCase):
    def test_bald_draws_kodis_toast_icons(self):
        for name in NAMES:
            with self.subTest(name=name):
                image = Image.open(ROOT / "media" / name)
                self.assertEqual((image.size, image.mode), ((128, 128), "RGBA"))
                # bald_ink on transparent: Kodi does not tint a toast's icon.
                colours = {pixel[:3] for pixel in image.getdata() if pixel[3] == 255}
                self.assertEqual(colours, {(0xEC, 0xEE, 0xF2)})

    def test_the_pack_no_longer_has_estuarys(self):
        version, files = xbt.read()
        self.assertEqual(version, b"3")
        packed = {name.lower() for name, _, _ in files}
        self.assertFalse(packed & {name.lower() for name in NAMES})
        self.assertIn("defaultactor.png", packed)  # the rest of Estuary's pack stays

    def test_lucides_licence_ships(self):
        self.assertIn("ISC License", (ROOT / "LICENSE-Lucide.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
