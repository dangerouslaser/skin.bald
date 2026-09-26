"""Per-row display styles on Home: each style's tiles, the generator's style field and the widget editor's Style action."""

import importlib.util
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import equivalent, implies
from kodi_includes import Skin, expand_call, include_definitions
from skin_strings import bald_strings


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
FALLBACK = XML / "Includes_Bald_HomeDefaults.xml"
LANDSCAPE = ("fanart", "thumbnail", "logo")
STYLES = LANDSCAPE + ("poster",)
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


class PosterRowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definitions = include_definitions()

    def row(self, style, slot):
        elements = expand_call("Bald_Row", {"id": "9101", "style": style, "slot": slot, "start": str(int(slot) + 1)},
                               self.definitions)
        return elements, fixedlist(elements)

    def label_top(self, elements):
        holder = ET.Element("holder")
        holder.extend(elements)
        line = next(node for node in holder.iter("control") if node.get("type") == "grouplist")
        return line.findtext("top")

    def test_poster_rows_reuse_the_poster_low_rail(self):
        elements, row = self.row("poster", "5")
        self.assertEqual(tuple(row.findtext(tag) for tag in ("left", "top", "width", "height")), ("96", "738", "1248", "234"))
        for layout in ("itemlayout", "focusedlayout"):
            node = row.find(layout)
            self.assertEqual((node.get("width"), node.get("height")), ("156", "234"), layout)
        poster = self.definitions["Bald_RowTiles_poster"]
        self.assertEqual([node.get("content") for node in poster.iter("include")].count("Bald_PosterLowTile"), 2)
        # The rail sits where view 515 puts its list (a shared constant).
        view = ET.parse(XML / "View_515_Bald_PosterLow.xml").getroot().find(".//control[@id='515']")
        self.assertEqual(view.findtext("top"), poster.findtext("top"))
        # The label line sits 12 px above the posters, as it does above landscape tiles (856 + 26 + 12 = 894).
        self.assertEqual(self.label_top(elements), "712")
        self.assertEqual(self.label_top(self.row("fanart", "2")[0]), "856")

    def test_poster_focus_travels_to_slot_5_and_landscape_to_slot_2(self):
        for style, slot in (("poster", "5"), ("fanart", "2")):
            _, row = self.row(style, slot)
            self.assertEqual((row.findtext("focusposition"), row.findtext("movement")), (slot, slot), style)
        builder = load_builder()
        rows = [{"label": s, "path": f"videodb://{s}/", "target": "videos", "limit": "5", "secondary": "0", "style": s}
                for s in STYLES + ("",)]
        original = builder.menu_items
        builder.menu_items = lambda menu: rows if menu == "homewidgets" else []
        try:
            root = ET.fromstring(builder.fallback_text().split("\n", 1)[1])
        finally:
            builder.menu_items = original
        for call in row_calls(root, "Home"):
            slot = "5" if param(call, "style") == "poster" else "2"
            self.assertEqual((param(call, "slot"), param(call, "start")), (slot, str(int(slot) + 1)), param(call, "style"))
            # The row-start fix the row above includes uses this row's own slot.
            fix = root.find(f"include[@name='Bald_RowStart_{param(call, 'id')}']/definition")
            self.assertIn(f"Control.Move({param(call, 'id')},-{slot})", [node.text for node in fix.findall("onfocus")])
        styles = {value.text for value in root.findall("variable[@name='Bald_RowStyle_home']/value")}
        self.assertEqual(styles, set(STYLES))

    def test_the_frame_follows_a_window_property(self):
        body = ET.parse(XML / "Includes_Bald_Home.xml").getroot().findtext("expression[@name='Bald_PosterRow']")
        self.assertTrue(equivalent(body, "String.IsEqual(Window(home).Property(Bald.RowStyle),poster)"))
        self.assertNotIn("Container(", body)


def slides(include):
    """(condition, start, end, time, delay, tween, easing) for each non-reversible Conditional slide in an include."""
    node = include_definitions()[include]
    return [(anim.get("condition"), effect.get("start"), effect.get("end"), effect.get("time"), effect.get("delay"),
             effect.get("tween"), effect.get("easing"))
            for anim in node.iter("animation") if anim.get("type") == "Conditional" and anim.get("reversible") == "false"
            for effect in anim.findall("effect") if effect.get("type") == "slide"]


class PosterFrameTests(unittest.TestCase):
    def test_mask_and_art_animations_shrink_the_frame_for_poster_rows(self):
        edge = slides("Bald_AnimPosterEdge")
        art = slides("Bald_AnimPosterArt")
        for entry in edge + art:
            self.assertEqual(entry[5:], ("cubic", "out"))  # the move curve

        def one(entries, condition):
            found = [entry for entry in entries if equivalent(entry[0], condition)]
            self.assertEqual(len(found), 1, condition)
            return found[0][1:5]

        poster, landscape, info = "$EXP[Bald_PosterRow]", "!$EXP[Bald_PosterRow]", "$EXP[Bald_InfoOpen]"
        # The bottom edge (mask, scrim and logo) moves up 126 px and back.
        self.assertEqual(one(edge, poster)[:2], ("0,0", "0,-126"))
        self.assertEqual(one(edge, landscape)[:2], ("0,-126", "0,0"))
        # The art moves up 63 px, back for landscape rows, and back in step with the info zoom while info is open,
        # so the zoomed art is exactly a landscape row's.
        self.assertEqual(one(art, f"{poster} + !{info}")[:2], ("0,0", "0,-63"))
        self.assertEqual(one(art, landscape)[:2], ("0,-63", "0,0"))
        zoom = next(anim.find("effect") for anim in include_definitions()["Bald_AnimInfoFrame"].iter("animation")
                    if equivalent(anim.get("condition"), info))
        self.assertEqual(one(art, f"{poster} + {info}"), ("0,-63", "0,0", zoom.get("time"), zoom.get("delay")))
        # Art and edge move together.
        self.assertEqual(one(art, f"{poster} + !{info}")[2:], one(edge, poster)[2:])
        self.assertEqual(one(art, landscape)[2:], one(edge, landscape)[2:])

    def test_home_applies_the_frame_animations(self):
        home = Skin().window("Home.xml")
        groups = [group for group in home.iter("control") if group.get("type") == "group"]

        def ends(group):
            return {effect.get("end") for effect in group.findall("animation/effect")}

        art = [group for group in groups if {"153.846", "0,-63"} <= ends(group)]
        self.assertEqual(len(art), 1)
        self.assertIn("$VAR[Bald_Fanart]", [node.text for node in art[0].iter("texture")])
        overlay = [group for group in groups if {"153.846", "0,-126"} <= ends(group)]
        self.assertEqual(len(overlay), 1)
        self.assertIn("bald/scrim_logo.png", [node.text for node in overlay[0].iter("texture")])
        masks = [group for group in groups if "0,-126" in ends(group) and group.find("control[@type='grouplist']") is not None]
        self.assertEqual(len(masks), 1)
        window = masks[0].find("control[@type='grouplist']")
        self.assertEqual((window.findtext("top"), window.findtext("height")), ("822", "156"))
        # A fixed, aligned mask covers 696-852 on a poster row.
        fixed = [group.find("control[@type='grouplist']") for group in groups
                 if group.findtext("visible") and equivalent(group.findtext("visible"), "$EXP[Bald_PosterRow]")]
        self.assertEqual([(node.findtext("top"), node.findtext("height")) for node in fixed], [("696", "156")])


ROW_SETTER = re.compile(r"SetProperty\(Bald\.(Row|Row\.\w+|MenuPreview),")
ACTIONS = ("onload", "onfocus", "onclick", "onup", "ondown", "onleft", "onright", "onback", "onunfocus")


class RowStylePropertyTests(unittest.TestCase):
    def test_the_style_is_set_wherever_the_displayed_row_changes(self):
        home = Skin().window("Home.xml")
        checked = 0
        for owner in [home] + list(home.iter("control")):
            for tag in ACTIONS:
                actions = [(node.get("condition"), node.text or "") for node in owner.findall(tag)]
                style = [cond for cond, text in actions if text.startswith("SetProperty(Bald.RowStyle,")]
                for cond, text in actions:
                    if not ROW_SETTER.match(text):
                        continue
                    checked += 1
                    self.assertTrue(any(implies(cond or "true", other or "true") for other in style),
                                    f"{owner.get('id')} {tag}: {text}")
        self.assertGreater(checked, 10)

    def test_the_menu_preview_uses_the_previewed_screens_remembered_row(self):
        values = [(value.get("condition"), value.text) for value in
                  ET.parse(XML / "Includes_Bald_Home.xml").getroot().findall("variable[@name='Bald_PreviewRowStyle']/value")]
        for screen, _ in SCREENS:
            self.assertIn((f"$EXP[Bald_MenuPreview_{screen}]", f"$VAR[Bald_RowStyle_{screen}]"), values)
        # Generated: each screen's style variable reads that screen's remembered row, Bald.Row.<screen>.
        root = ET.parse(FALLBACK).getroot()
        for screen, title in SCREENS:
            conditions = [value.get("condition") for value in root.findall(f"variable[@name='Bald_RowStyle_{screen}']/value")]
            ids = [param(row, "id") for row in row_calls(root, title)]
            self.assertEqual(conditions, [f"String.IsEqual(Window(home).Property(Bald.Row.{screen}),{i})" for i in ids] + [None])


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
