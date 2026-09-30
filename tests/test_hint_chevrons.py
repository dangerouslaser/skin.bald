"""Navigation hints name their key with a chevron (Bald_Chevron*, Includes_Bald_Common.xml) and read left to right.

The chevrons are glyphs tools/hint_chevrons.py draws into Bald's UI fonts. A left, up or down chevron comes before
its name ("‹ Options", "˅ Cast & details"), a right one after it ("Scroll by letters ›"), and a hint for both Left
and Right has one either side. A footer lists Left's hint first, then Up's, the keys without a direction, Down's,
and Right's last.
"""

import re
import unittest
from pathlib import Path

from skin_strings import strings
from test_fonts import characters

ROOT = Path(__file__).resolve().parents[1]
SKIN = ROOT / "1080i"
CODEPOINTS = {"Up": 0xE100, "Down": 0xE101, "Left": 0xE102, "Right": 0xE103, "UpDown": 0xE105}
HINT_INCLUDES = ("Bald_InfoHintPair", "Bald_PVRHints", "Bald_SettingsHints", "Bald_HomeHintLine")


def rank(value):
    """Where a hint belongs, left to right; None when it is only known at run time."""
    if "$PARAM[" in value or "$VAR[Bald_MenuHint" in value:
        return None
    left, right = value.startswith("$VAR[Bald_ChevronLeft]"), value.endswith("$VAR[Bald_ChevronRight]")
    if left and right:
        return 2
    if left:
        return 0
    if right:
        return 4
    if value.startswith("$VAR[Bald_ChevronUp"):
        return 1
    if value.startswith("$VAR[Bald_ChevronDown]"):
        return 3
    return 2


class HintChevronTests(unittest.TestCase):
    def test_every_ui_font_draws_the_chevrons(self):
        fonts = sorted(p for p in (ROOT / "fonts").glob("*.ttf") if not p.name.startswith("NotoSans"))
        self.assertEqual(len(fonts), 10)
        for path in fonts:
            with self.subTest(font=path.name):
                self.assertTrue(set(CODEPOINTS.values()) <= characters(path))

    def test_the_variables_name_the_glyphs(self):
        common = (SKIN / "Includes_Bald_Common.xml").read_text(encoding="utf-8")
        for name, codepoint in CODEPOINTS.items():
            self.assertIn(f'<variable name="Bald_Chevron{name}"><value>&#x{codepoint:04X};</value></variable>', common)

    def test_no_hint_spells_out_a_direction(self):
        table = strings()
        for path in SKIN.glob("*.xml"):
            for num in re.findall(r"\$LOCALIZE\[(\d+)\]", path.read_text(encoding="utf-8")):
                text = table.get(int(num), "")
                if text == "Up next":  # a heading, not a hint
                    continue
                with self.subTest(file=path.name, string=num):
                    self.assertNotRegex(text, r"^(Up|Down|Left|Right)( |$)|^(Up|Down|Left|Right) (/|and|or) ")

    def test_a_right_chevron_follows_its_name_and_the_others_lead(self):
        for path in SKIN.glob("*.xml"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertNotRegex(text, r"\$VAR\[Bald_ChevronRight\]\$LOCALIZE")
                self.assertNotRegex(text, r"\$LOCALIZE\[\d+\]\$VAR\[Bald_Chevron(Up|Down|Left|UpDown)\]")

    def test_footers_read_left_to_right(self):
        checked = 0
        for path in SKIN.glob("*.xml"):
            text = path.read_text(encoding="utf-8")
            for call in re.finditer(r'<include content="(%s)">(.*?)</include>' % "|".join(HINT_INCLUDES), text, re.S):
                params = dict(re.findall(r'<param name="(first|second|third)">(.*?)</param>', call.group(2), re.S))
                ranks = [rank(params[n]) for n in ("first", "second", "third") if n in params]
                ranks = [r for r in ranks if r is not None]
                with self.subTest(file=path.name, call=call.group(2)[:120]):
                    self.assertEqual(ranks, sorted(ranks))
                checked += 1
        self.assertGreater(checked, 30)

    def test_the_menu_names_what_left_and_right_do(self):
        home = (SKIN / "Includes_Bald_Home.xml").read_text(encoding="utf-8")
        featured = re.search(r'<expression name="Bald_MenuHintFeatured">(.*?)</expression>', home).group(1)
        browse = re.search(r'<expression name="Bald_MenuHintBrowse">(.*?)</expression>', home).group(1)
        # Left enters the rows of Home, Live TV and every hub; Right opens a hub's target unless the swap is on.
        self.assertEqual(sorted(re.findall(r"Control\.HasFocus\((\d+)\)", featured)),
                         ["9001", "9004"] + [f"901{n}" for n in range(1, 9)])
        for n in range(1, 9):
            self.assertIn(f"[Control.HasFocus(901{n}) + $EXP[Bald_HubHasOpen_hub{n}] + !$EXP[Bald_HubSwap_hub{n}]]", browse)
        self.assertIn('<expression name="Bald_MenuHintGuide">[Control.HasFocus(9004) + !$EXP[Bald_LiveTVSwap]]</expression>', home)
        self.assertIn("$VAR[Bald_ChevronLeft]$LOCALIZE[31788]", home)
        self.assertIn("$LOCALIZE[31789]$VAR[Bald_ChevronRight]", home)
        self.assertIn("$LOCALIZE[31790]$VAR[Bald_ChevronRight]", home)
        self.assertIn("<include>Bald_MenuHints</include>", (SKIN / "Home.xml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
