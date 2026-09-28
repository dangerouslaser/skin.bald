"""Watch-state marks on Home's row tiles (Bald_TileMarks, Includes_Bald_Home.xml): a watched check and a progress bar
on every tile style that shows one library item (fanart, thumbnail, poster, square), none on logo, text and weather
rows. They follow the Appearance switches (9636 Bald.HideWatchedMarks, 9637 Bald.HideProgressMarks), keep to opaque
colours (tiles sit over background video), sit over the tile title and pop with the tile."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import equivalent, implies
from kodi_includes import expand_call, expressions


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
HOME = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
COLORS = {node.get("name"): node.text for node in ET.parse(ROOT / "colors" / "defaults.xml").getroot()}

# Tile rectangle in its slot (x, y, w, h), unfocused dim, pop and centre, per style (Bald_TileTitle's values).
TILES = {
    "fanart": ((10, 10, 176, 99), "bald_tile_dim", "100", "98,59"),
    "thumbnail": ((10, 10, 176, 99), "bald_tile_dim", "100", "98,59"),
    "poster": ((12, 12, 140, 210), "bald_poster_dim", "102.5", "78,117"),
    "square": ((12, 12, 184, 184), "bald_poster_dim", "102.5", "104,104"),
}
NO_MARKS = ("logo", "text", "weather")


def layouts(style):
    """The row's itemlayout and focusedlayout, fully expanded."""
    holder = ET.Element("fixedlist")
    holder.extend(expand_call(f"Bald_RowTiles_{style}"))
    return holder.find("itemlayout"), holder.find("focusedlayout")


def marks(layout):
    """The marks group(s) in a layout: the group whose visibility is Bald_TileMarkItem."""
    return [node for node in layout.iter("control")
            if node.get("type") == "group" and (node.findtext("visible") or "") == "$EXP[Bald_TileMarkItem]"]


def opaque(color):
    value = COLORS.get(color, color)
    return bool(re.fullmatch(r"[Ff]{2}[0-9A-Fa-f]{6}", value or ""))


class TileMarksTests(unittest.TestCase):
    def test_every_single_item_style_has_marks_in_both_layouts(self):
        for style in TILES:
            for layout in layouts(style):
                with self.subTest(style=style, layout=layout.tag):
                    self.assertEqual(len(marks(layout)), 1)

    def test_logo_text_and_weather_rows_have_none(self):
        for style in NO_MARKS:
            for layout in layouts(style):
                with self.subTest(style=style, layout=layout.tag):
                    self.assertEqual(marks(layout), [])

    def test_marks_sit_on_the_tile_rect(self):
        for style, ((x, y, w, h), _, _, _) in TILES.items():
            for layout in layouts(style):
                group = marks(layout)[0]
                check, bar = [node for node in group if node.tag == "control" and node.get("type") == "group"]
                with self.subTest(style=style, layout=layout.tag):
                    # Check: a 24 px dot 8 px in from the top right corner.
                    self.assertEqual((int(check.findtext("left")), int(check.findtext("top"))), (x + w - 32, y + 8))
                    dot = check.find("control")
                    self.assertEqual((dot.findtext("width"), dot.findtext("height")), ("24", "24"))
                    # Bar: 4 px, 8 px in from the sides, its bottom 4 px above the tile's bottom edge.
                    self.assertEqual((int(bar.findtext("left")), int(bar.findtext("top"))), (x + 8, y + h - 8))
                    for node in bar.findall("control"):
                        self.assertEqual((int(node.findtext("width")), node.findtext("height")), (w - 16, "4"))

    def test_marks_follow_the_appearance_switches(self):
        common = ET.parse(XML / "Includes_Bald_Common.xml").getroot()
        self.assertEqual(common.findtext("expression[@name='Bald_ShowWatchedMarks']"), "[!Skin.HasSetting(Bald.HideWatchedMarks)]")
        self.assertEqual(common.findtext("expression[@name='Bald_ShowProgressMarks']"), "[!Skin.HasSetting(Bald.HideProgressMarks)]")
        for style in TILES:
            group = marks(layouts(style)[0])[0]
            check, bar = [node for node in group if node.tag == "control" and node.get("type") == "group"]
            with self.subTest(style=style):
                self.assertTrue(equivalent(check.findtext("visible"), "$EXP[Bald_TileWatched] + $EXP[Bald_ShowWatchedMarks]"))
                self.assertTrue(equivalent(bar.findtext("visible"), "$EXP[Bald_TileInProgress] + $EXP[Bald_ShowProgressMarks]"))
                self.assertTrue(implies(check.findtext("visible"), "!Skin.HasSetting(Bald.HideWatchedMarks)"))
                self.assertTrue(implies(bar.findtext("visible"), "!Skin.HasSetting(Bald.HideProgressMarks)"))

    def test_which_items_get_which_mark(self):
        bodies = expressions()
        # Video items only: music has play counts too, favourites have none.
        for dbtype in ("album", "song", "artist"):
            self.assertTrue(implies("$EXP[Bald_TileMarkItem]", f"!String.IsEqual(ListItem.DBType,{dbtype})", bodies))
        # Resume wins over the check, as in list rows; a partly watched show or season is in progress.
        self.assertTrue(implies("$EXP[Bald_TileWatched]", "!ListItem.IsResumable", bodies))
        self.assertTrue(implies("$EXP[Bald_TileWatched]", "Integer.IsGreater(ListItem.PlayCount,0)", bodies))
        self.assertTrue(implies("ListItem.IsResumable", "$EXP[Bald_TileInProgress]", bodies))
        self.assertTrue(implies("[String.IsEqual(ListItem.DBType,tvshow) + Integer.IsGreater(ListItem.Property(WatchedEpisodes),0)"
                                " + Integer.IsGreater(ListItem.Property(UnWatchedEpisodes),0)]", "$EXP[Bald_TileInProgress]", bodies))
        self.assertTrue(implies("$EXP[Bald_TileWatched]", "!$EXP[Bald_TileShowInProgress]", bodies))
        # The bar reads the item's resume percentage, else the show's watched-episode percentage.
        group = marks(layouts("fanart")[0])[0]
        bars = [node for node in group.iter("control") if node.get("type") == "progress"]
        self.assertEqual([(node.findtext("info"), node.findtext("visible")) for node in bars],
                         [("ListItem.PercentPlayed", "ListItem.IsResumable"),
                          ("ListItem.Property(WatchedEpisodePercent)", "!ListItem.IsResumable")])

    def test_colours_are_opaque_and_follow_focus(self):
        self.assertEqual(COLORS["bald_mark_track"], "FF4A4B4F")
        for style, (_, dim, _, _) in TILES.items():
            for layout, fill in zip(layouts(style), (dim, "bald_ink")):
                group = marks(layout)[0]
                used = [node.get("colordiffuse") for node in group.iter() if node.get("colordiffuse")]
                with self.subTest(style=style, layout=layout.tag):
                    self.assertTrue(used)
                    for color in used:
                        self.assertTrue(opaque(color), color)
                    self.assertIn("bald_field", used)  # The check's dot, the episode card's bald_field60 made solid.
                    check = next(node for node in group.iter("texture") if node.text == "bald/check.png")
                    self.assertEqual(check.get("colordiffuse"), fill)
                    track = "bald_mark_track" if fill == "bald_ink" else "bald_mark_track_dim"
                    self.assertIn(track, used)

    def test_marks_pop_with_the_tile_and_sit_over_the_title(self):
        for style, (_, _, pop, center) in TILES.items():
            for layout in layouts(style):
                group = marks(layout)[0]
                with self.subTest(style=style, layout=layout.tag):
                    animations = group.findall("animation")
                    self.assertEqual(len(animations), 1)
                    self.assertEqual(animations[0].get("type"), "Focus")
                    self.assertEqual(animations[0].get("condition"), "$EXP[Bald_FullMotion]")
                    zoom = animations[0].find("effect")
                    self.assertEqual((zoom.get("type"), zoom.get("end"), zoom.get("center"), zoom.get("time"),
                                      zoom.get("tween"), zoom.get("easing")),
                                     ("zoom", pop, center, "280", "back", "out"))
                    # Drawn after the title (its scrim would darken them), in the same parent.
                    parent = next(node for node in layout.iter() if group in list(node))
                    children = list(parent)
                    titles = [index for index, node in enumerate(children)
                              if node.find("control[@type='label']/label") is not None
                              and node.findtext("control[@type='label']/label") == "$INFO[ListItem.Label]"
                              and node.find("control[@type='image']/texture") is not None
                              and node.findtext("control[@type='image']/texture") == "bald/scrim_card.png"]
                    self.assertTrue(titles)
                    self.assertGreater(children.index(group), max(titles))

    def test_settings_rows_and_ids_say_they_cover_home_tiles(self):
        appearance = (XML / "Custom_1118_BaldAppearance.xml").read_text(encoding="utf-8")
        self.assertIn("on Home's row tiles\n\t\t\t\t     (Bald_TileMarks", appearance)
        self.assertRegex((XML / "IDs").read_text(encoding="utf-8"), r"9637 progress marks \(both: TV episode cards, Home row tiles")
        for language in ("en_gb", "de_de"):
            text = (ROOT / "language" / f"resource.language.{language}" / "strings.po").read_text(encoding="utf-8")
            for string in ("31339", "31340"):
                block = text.split(f'msgctxt "#{string}"')[0].rsplit("\n\n", 1)[-1]
                with self.subTest(language=language, string=string):
                    self.assertIn("Home tiles", block)


if __name__ == "__main__":
    unittest.main()
