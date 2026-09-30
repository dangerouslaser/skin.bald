"""Library views open their options with the key their footer names (the views wrap at every other edge).

Horizontal rows: Up opens the options (Left and Right wrap along the row), "Up for options". Vertical lists: Left, and
Up / Down wrap, "Left for options". Grids: Left from the left column, and Up / Down wrap top to bottom, "Left edge for
options"."""

import re
import unittest
from pathlib import Path

XML = Path(__file__).resolve().parents[1] / "1080i"
UP, LEFT, LEFT_EDGE = "31828", "31685", "31703"
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


def footer_hint(text, cid, kind):
    """The options hint the view's footer shows."""
    call = re.search(r'<include content="Bald_(?:WallFooter|TVFooter)"><param name="c">%s</param>(.*?)</include>' % cid, text)
    if call:
        given = re.search(r'<param name="options_hint">\$LOCALIZE\[(\d+)\]</param>', call.group(1))
        if given:
            return given.group(1)
        wall = (XML / "View_511_Bald_Wall.xml").read_text()
        tv = (XML / "View_520_Bald_TV.xml").read_text()
        source = wall if "WallFooter" in call.group(0) else tv
        return re.search(r'<param name="options_hint">\$LOCALIZE\[(\d+)\]</param>', source).group(1)
    # Views with their own hint line (510, 515): the third hint.
    return re.search(r'<param name="third">\$LOCALIZE\[(\d+)\]</param>', text).group(1)


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
