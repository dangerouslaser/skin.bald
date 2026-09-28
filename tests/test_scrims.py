from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKIN = ROOT / "1080i"


class ScrimTests(unittest.TestCase):
    def test_every_scrim_is_black(self):
        """Gradients darken towards pure black (bald_scrim), never the blue-black field."""
        for path in SKIN.glob("*.xml"):
            for match in re.finditer(r"<texture[^>]*>[^<]*scrim[^<]*</texture>", path.read_text(encoding="utf-8")):
                texture = match.group(0)
                colour = re.search(r'colordiffuse="([^"]*)"', texture)
                with self.subTest(file=path.name, texture=texture):
                    if colour:
                        self.assertEqual(colour.group(1), "bald_scrim")
                    else:
                        self.assertIn("scrim_logo.png", texture, "only the logo scrim carries its own (black) colour")

    def test_dark_info_scrims(self):
        from PIL import Image
        side = Image.open(ROOT / "media" / "bald" / "scrim_info_h.png").convert("RGBA").getchannel("A")
        dark = Image.open(ROOT / "media" / "bald" / "scrim_info_h_dark.png").convert("RGBA").getchannel("A")
        self.assertEqual(side.size, dark.size)
        for a, d in zip(side.tobytes(), dark.tobytes()):
            self.assertEqual(d, round(255 * (1 - (1 - a / 255) ** 1.6)))
        bottom = Image.open(ROOT / "media" / "bald" / "scrim_info_b_dark.png").convert("RGBA").getchannel("A")
        column = [bottom.getpixel((0, y)) for y in range(bottom.height)]
        self.assertEqual(bottom.size, (4, 1080))
        self.assertEqual(column[300], 0)
        self.assertEqual(column, sorted(column), "darkens steadily towards the bottom")
        self.assertGreaterEqual(column[820], 215)
        self.assertEqual(column[-1], 245)


if __name__ == "__main__":
    unittest.main()
