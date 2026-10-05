"""Watch-state marks on the library's poster views (Bald_LibraryPosterItem, View_510_Bald_Posters.xml): the watched
check of Home's tiles (Bald_TileMarks) and a progress bar (Bald_TileBar) on every poster in the movie, series and
season views, placed from the poster's rectangle, following the Appearance switches and the tile's focus colours."""

import unittest
import xml.etree.ElementTree as ET

from conditions import equivalent, implies
from kodi_includes import expand_call, expressions


# View include, container id, poster rectangle in its slot (x, y, w, h).
VIEWS = {
    "View_510_Bald_Posters": ("510", (12, 12, 360, 540)),
    "View_511_Bald_Wall": ("511", (12, 12, 192, 288)),
    "View_512_Bald_WallPreview": ("512", (12, 12, 192, 288)),
    "View_515_Bald_PosterLow": ("515", (12, 12, 140, 210)),
    "View_520_Bald_Series": ("520", (12, 12, 360, 540)),
    "View_521_Bald_SeriesWall": ("521", (12, 12, 192, 288)),
    "View_523_Bald_SeriesPosterLow": ("523", (12, 12, 140, 210)),
    "View_530_Bald_Seasons": ("530", (12, 12, 360, 540)),
}


def layouts(view, cid):
    holder = ET.Element("holder")
    holder.extend(expand_call(view))
    container = next(node for node in holder.iter("control") if node.get("id") == cid)
    return container.find("itemlayout"), container.find("focusedlayout")


def groups(layout, visible):
    return [node for node in layout.iter("control")
            if node.get("type") == "group" and node.findtext("visible")
            and equivalent(node.findtext("visible"), visible)]


class LibraryTileMarksTests(unittest.TestCase):
    def test_every_poster_view_has_one_check_and_one_bar(self):
        for view, (cid, (x, y, w, h)) in VIEWS.items():
            for layout in layouts(view, cid):
                with self.subTest(view=view, layout=layout.tag):
                    (marks,) = groups(layout, "$EXP[Bald_TileMarkItem]")
                    (check,) = [node for node in marks if node.get("type") == "group"]
                    self.assertEqual((int(check.findtext("left")), int(check.findtext("top"))), (x + w - 32, y + 8))
                    (bar,) = groups(layout, "$EXP[Bald_TileMarkItem] + $EXP[Bald_TileInProgress] + $EXP[Bald_ShowProgressMarks]")
                    self.assertEqual((int(bar.findtext("left")), int(bar.findtext("top"))), (x + 8, y + h - 8))
                    progress = [node for node in bar if node.get("type") == "progress"]
                    self.assertEqual([node.findtext("info") for node in progress],
                                     ["ListItem.PercentPlayed", "ListItem.Property(WatchedEpisodePercent)"])
                    for node in progress:
                        self.assertEqual(node.findtext("width"), str(w - 16))
                        self.assertEqual(node.find("texturebg").text, "bald/bar.png")

    def test_marks_follow_the_switches_and_resume_wins(self):
        bodies = expressions()
        layout = layouts("View_520_Bald_Series", "520")[0]
        (marks,) = groups(layout, "$EXP[Bald_TileMarkItem]")
        (check,) = [node for node in marks if node.get("type") == "group"]
        self.assertTrue(implies(check.findtext("visible"), "!Skin.HasSetting(Bald.HideWatchedMarks)", bodies))
        self.assertTrue(implies(check.findtext("visible"), "Integer.IsGreater(ListItem.PlayCount,0)", bodies))
        self.assertTrue(implies(check.findtext("visible"), "!ListItem.IsResumable", bodies))
        (bar,) = [node for node in layout.iter("control") if node.get("type") == "group"
                  and "Bald_TileInProgress" in (node.findtext("visible") or "")]
        self.assertTrue(implies(bar.findtext("visible"), "!Skin.HasSetting(Bald.HideProgressMarks)", bodies))

    def test_focus_colours(self):
        for view, (cid, _) in VIEWS.items():
            item, focused = layouts(view, cid)
            for layout, fill, track in ((item, None, "bald_mark_track_dim"), (focused, "bald_ink", "bald_mark_track")):
                with self.subTest(view=view, layout=layout.tag):
                    check = next(node for node in layout.iter("texture") if node.text == "bald/check.png")
                    if fill:
                        self.assertEqual(check.get("colordiffuse"), fill)
                    else:
                        self.assertNotEqual(check.get("colordiffuse"), "bald_ink")
                    tracks = {node.get("colordiffuse") for node in layout.iter("texturebg")}
                    self.assertEqual(tracks, {track})

    def test_home_poster_row_keeps_its_own_marks_only(self):
        for layout_tag in ("itemlayout", "focusedlayout"):
            holder = ET.Element("fixedlist")
            holder.extend(expand_call("Bald_RowTiles_poster"))
            layout = holder.find(layout_tag)
            with self.subTest(layout=layout_tag):
                self.assertEqual(len(groups(layout, "$EXP[Bald_TileMarkItem]")), 1)
                self.assertFalse([node for node in layout.iter("control") if node.get("type") == "progress"])


if __name__ == "__main__":
    unittest.main()
