"""Per-row display styles on Home: each style's tiles, the generator's style field and the widget editor's Style action."""

import importlib.util
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import implies
from kodi_includes import expand_call, include_definitions
from skin_strings import bald_strings


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
FALLBACK = XML / "Includes_Bald_HomeDefaults.xml"
LANDSCAPE = ("fanart", "thumbnail", "logo")
STYLES = LANDSCAPE
SCREENS = (("home", "Home"), ("movies", "Movies"), ("tvshows", "TVShows"))


def load_builder():
    spec = importlib.util.spec_from_file_location("build_home_defaults", ROOT / "tools" / "build_home_defaults.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row_calls(root, title):
    return root.findall(f"include[@name='Bald_Generated_{title}Widgets']/definition/include")


def param(node, name):
    return node.findtext(f"param[@name='{name}']")


def fixedlist(elements):
    holder = ET.Element("holder")
    holder.extend(elements)
    return next(node for node in holder.iter("control") if node.get("type") == "fixedlist")


def textures(node):
    return [texture.text for texture in node.iter("texture")]


class RowStyleIncludeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definitions = include_definitions()

    def row(self, style):
        return fixedlist(expand_call("Bald_Row", {"id": "9101", "style": style}, self.definitions))

    def test_every_style_has_its_tiles_include(self):
        for style in STYLES:
            self.assertIn(f"Bald_RowTiles_{style}", self.definitions)
            row = self.row(style)
            self.assertIsNotNone(row.find("itemlayout"), style)
            self.assertIsNotNone(row.find("focusedlayout"), style)
            self.assertIsNotNone(row.findtext("width"), style)

    def test_bald_row_picks_its_tiles_by_style_and_defaults_to_fanart(self):
        row = self.definitions["Bald_Row"]
        self.assertEqual(param(row, "style"), "fanart")
        calls = [node.get("content") for node in row.iter("include")]
        self.assertIn("Bald_RowTiles_$PARAM[style]", calls)
        # With no style the row is exactly the fanart row.
        default = fixedlist(expand_call("Bald_Row", {"id": "9101"}, self.definitions))
        self.assertEqual(ET.tostring(default), ET.tostring(self.row("fanart")))

    def test_landscape_styles_share_the_fanart_geometry(self):
        geometry = {style: tuple(self.row(style).findtext(tag) for tag in ("left", "top", "width", "height"))
                    for style in LANDSCAPE}
        self.assertEqual(geometry["fanart"], ("86", "884", "1258", "119"))
        self.assertEqual(set(geometry.values()), {geometry["fanart"]})
        for style in LANDSCAPE:
            layout = self.row(style).find("itemlayout")
            self.assertEqual((layout.get("width"), layout.get("height")), ("192", "119"), style)

    def test_thumbnail_tiles_use_stills_and_landscape_art(self):
        self.assertIn("$VAR[Bald_ItemFanart]", textures(self.row("fanart").find("itemlayout")))
        for layout in ("itemlayout", "focusedlayout"):
            self.assertIn("$VAR[Bald_ItemThumbnail]", textures(self.row("thumbnail").find(layout)))
        values = [(value.get("condition"), value.text) for value in
                  ET.parse(XML / "Includes_Bald_Common.xml").getroot().findall("variable[@name='Bald_ItemThumbnail']/value")]
        # Episodes: the still chain first. Everything else: landscape art, then the fanart chain. A movie's thumb (its
        # poster, usually) is never read directly.
        self.assertTrue(implies(values[0][0], "ListItem.IsEpisode"))
        self.assertEqual(values[0][1], "$VAR[Bald_EpisodeThumb]")
        self.assertTrue(any("Art(landscape)" in text for _, text in values))
        self.assertEqual(values[-1], (None, "$VAR[Bald_ItemFanart]"))
        self.assertFalse(any("Art(thumb)" in text for _, text in values))

    def test_logo_tiles_overlay_the_clearlogo_only_when_there_is_one(self):
        for layout in ("itemlayout", "focusedlayout"):
            node = self.row("logo").find(layout)
            self.assertIn("$VAR[Bald_ItemLogo]", textures(node))
            self.assertIn("bald/scrim_logo.png", textures(node))
            overlay = next(group for group in node.iter("control") if group.get("type") == "group"
                           and "bald/scrim_logo.png" in [c.findtext("texture") for c in group.findall("control")])
            visible = overlay.findtext("visible")
            self.assertTrue(implies(visible, "$EXP[Bald_ShowClearlogo]"))
            self.assertTrue(implies(visible, "!String.IsEmpty(ListItem.Art(clearlogo)) | !String.IsEmpty(ListItem.Art(tvshow.clearlogo))"))
        for style in ("fanart", "thumbnail"):
            self.assertNotIn("bald/scrim_logo.png", textures(self.row(style)))


class GeneratedStyleTests(unittest.TestCase):
    def test_fallback_carries_a_style_for_every_row(self):
        root = ET.parse(FALLBACK).getroot()
        for _, title in SCREENS:
            rows = row_calls(root, title)
            self.assertTrue(rows, title)
            for row in rows:
                self.assertIn(param(row, "style"), STYLES, param(row, "id"))

    def test_rows_without_a_style_are_fanart(self):
        builder = load_builder()
        rows = [{"label": "A", "path": "videodb://a/", "target": "videos", "limit": "5", "secondary": "0"},
                {"label": "B", "path": "videodb://b/", "target": "videos", "limit": "5", "secondary": "0", "style": ""},
                {"label": "C", "path": "videodb://c/", "target": "videos", "limit": "5", "secondary": "0", "style": "bogus"}]
        rows += [{"label": s, "path": f"videodb://{s}/", "target": "videos", "limit": "5", "secondary": "0", "style": s}
                 for s in STYLES]
        original = builder.menu_items
        builder.menu_items = lambda menu: rows if menu == "homewidgets" else []
        try:
            root = ET.fromstring(builder.fallback_text().split("\n", 1)[1])
        finally:
            builder.menu_items = original
        styles = [param(row, "style") for row in row_calls(root, "Home")]
        self.assertEqual(styles, ["fanart", "fanart", "fanart", *STYLES])


class EditorStyleTests(unittest.TestCase):
    def test_the_widget_editor_has_a_style_choice(self):
        root = ET.parse(XML / "Custom_1116_BaldHomeWidgets.xml").getroot()
        button = root.find(".//control[@id='9208']")
        self.assertIsNotNone(button)
        self.assertEqual(button.findtext("label2"), "$VAR[Bald_WidgetStyleLabel]")
        action = button.findtext("onclick")
        # Skin Variables' do_edit: key, then label=value pairs joined by &, a heading, and use_prop_pairs.
        match = re.fullmatch(r"RunPlugin\(\$INFO\[Container\(9100\)\.ListItem\.Property\(url\)\]&func=do_edit"
                             r"&&style&&(?P<pairs>[^,]+?)&&(?P<heading>[^&]+)&&True\)", action)
        self.assertIsNotNone(match, action)
        pairs = [pair.split("=") for pair in match.group("pairs").split("&")]
        self.assertEqual([value for _, value in pairs], list(STYLES))
        names = bald_strings()
        for label, _ in pairs + [[match.group("heading"), None]]:
            number = int(re.fullmatch(r"\$LOCALIZE\[(\d+)\]", label).group(1))
            self.assertNotRegex(names[number], r"[&=,+]")

        values = [(value.get("condition"), value.text) for value in ET.parse(XML / "Includes_Bald_Configure.xml")
                  .getroot().findall("variable[@name='Bald_WidgetStyleLabel']/value")]
        labels = dict(pairs)
        for label, style in pairs:
            if style == "fanart":
                continue
            self.assertIn((f"String.IsEqual(Container(9100).ListItem.Property(style),{style})", label), values)
        self.assertEqual(values[-1], (None, next(label for label, style in pairs if style == "fanart")))
        self.assertEqual(len(labels), len(STYLES))


if __name__ == "__main__":
    unittest.main()
