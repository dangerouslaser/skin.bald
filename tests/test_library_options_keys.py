"""Library views open their options with the key their footer names (the views wrap at every other edge).

Horizontal rows: Up opens the options (Left and Right wrap along the row), "˄ Options". Vertical lists: Left, and
Up / Down wrap, "‹ Options". Grids: Left from the left column, and Up / Down wrap top to bottom, "‹ Options". The
key glyph names the key (Bald_Key*, Includes_Bald_Common.xml); the text is the same "Options" string."""

import re
import unittest
from pathlib import Path

XML = Path(__file__).resolve().parents[1] / "1080i"
OPTIONS = "31661"
UP, LEFT, LEFT_EDGE = "Up", "Left", "Left"
VIEWS = {  # container: (file, kind, the footer's options hint)
    "510": ("View_510_Bald_Posters.xml", "row", UP), "515": ("View_515_Bald_PosterLow.xml", "row", UP),
    "520": ("View_520_Bald_TV.xml", "row", UP), "530": ("View_520_Bald_TV.xml", "row", UP),
    "523": ("View_521_Bald_TV_Alternates.xml", "row", UP),
    "513": ("View_513_Bald_CompactList.xml", "list", LEFT), "514": ("View_514_Bald_ArtworkList.xml", "list", LEFT),
    "540": ("View_520_Bald_TV.xml", "list", LEFT), "522": ("View_521_Bald_TV_Alternates.xml", "list", LEFT),
    "531": ("View_521_Bald_TV_Alternates.xml", "list", LEFT), "541": ("View_521_Bald_TV_Alternates.xml", "list", LEFT),
    "551": ("View_550_Bald_Music.xml", "list", LEFT), "552": ("View_550_Bald_Music.xml", "list", LEFT),
    "511": ("View_511_Bald_Wall.xml", "grid", LEFT_EDGE), "512": ("View_512_Bald_WallPreview.xml", "grid", LEFT_EDGE),
    "521": ("View_521_Bald_TV_Alternates.xml", "grid", LEFT_EDGE),
    "542": ("View_521_Bald_TV_Alternates.xml", "grid", LEFT_EDGE), "550": ("View_550_Bald_Music.xml", "grid", LEFT_EDGE),
}


def control_text(text, cid):
    """The container's own markup, up to the next control."""
    start = re.search(r'<control type="(?:list|panel|fixedlist)" id="%s"' % cid, text).start()
    end = text.find("<control ", start + 1)
    return text[start:end if end > 0 else len(text)]


HINT = r'<param name="%s">\$VAR\[Bald_Key(\w+)\]\$LOCALIZE\[(\d+)\]</param>'


def footer_hint(text, cid, kind):
    """The key the view's footer names for its options: the chevron before "Options"."""
    call = re.search(r'<include content="Bald_(?:WallFooter|TVFooter)"><param name="c">%s</param>(.*?)</include>' % cid, text)
    if call:
        given = re.search(HINT % "options_hint", call.group(1))
        if not given:
            wall = (XML / "View_511_Bald_Wall.xml").read_text()
            tv = (XML / "View_520_Bald_TV.xml").read_text()
            source = wall if "WallFooter" in call.group(0) else tv
            given = re.search(HINT % "options_hint", source)
    else:
        # Views with their own hint line (510, 515): the first hint, as the options open Up (read left to right).
        given = re.search(HINT % "first", text)
    chevron, hint = given.groups()
    assert hint == OPTIONS, (cid, hint)
    return chevron


class OptionsKeyTests(unittest.TestCase):
    def test_each_view_opens_options_with_the_key_it_names(self):
        for cid, (name, kind, hint) in VIEWS.items():
            text = (XML / name).read_text()
            own = control_text(text, cid)
            if kind == "list" and cid in ("551", "552") or kind == "grid" and cid == "550":
                up = re.search(r'<param name="up">(\d+)</param>', own)
                up = up.group(1) if up else "9150"
            else:
                up = re.search(r"<onup>([^<]*)</onup>", own).group(1)
            with self.subTest(view=cid):
                if kind == "row":
                    self.assertEqual(up, "9150")
                else:
                    self.assertEqual(up, cid, "Up wraps")
                self.assertEqual(footer_hint(text, cid, kind), hint)

    def test_no_view_names_the_menu_key_any_more(self):
        for path in XML.glob("View_5*_Bald_*.xml"):
            self.assertNotIn("$LOCALIZE[31829]", path.read_text(), path.name)


if __name__ == "__main__":
    unittest.main()
