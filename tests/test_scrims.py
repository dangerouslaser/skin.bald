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

    def test_dark_info_scrims_are_the_shared_ones_at_double_strength(self):
        from PIL import Image
        for name in ("scrim_info_h", "scrim_info_b"):
            base = Image.open(ROOT / "media" / "bald" / f"{name}.png").convert("RGBA").getchannel("A")
            dark = Image.open(ROOT / "media" / "bald" / f"{name}_dark.png").convert("RGBA").getchannel("A")
            self.assertEqual(base.size, dark.size, name)
            for a, d in zip(base.tobytes(), dark.tobytes()):
                self.assertEqual(d, round(255 * (1 - (1 - a / 255) ** 2)), name)


if __name__ == "__main__":
    unittest.main()
