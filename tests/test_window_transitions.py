"""Home and the library across a window change (docs/NOTES.md, "Dark frame between Home and the library"): Kodi resets
every non-constant image texture on window deinit and a <fadetime> image fades its first picture in from nothing, so the
art placeholders wait for that fade, the blurred backdrop has a still layer that is there on the first frame, and the
library keeps its backgrounds outside the moving group as Home does."""
import re
import unittest
import xml.etree.ElementTree as ET

from conditions import equivalent
from kodi_includes import SKIN, include_definitions, parse


LIBRARY_VIEWS = ("View_510_Bald_Posters.xml", "View_514_Bald_ArtworkList.xml", "View_515_Bald_PosterLow.xml",
                 "View_520_Bald_TV.xml", "View_521_Bald_TV_Alternates.xml")
# The frames whose art is Bald_ArtLayer (fadetime 700) over a placeholder: (file, width, height, how many).
FRAMES = {
    "Home.xml": [("1248", "702", 1)],
    "View_510_Bald_Posters.xml": [("528", "297", 1)],
    "View_514_Bald_ArtworkList.xml": [("1008", "567", 1)],
    "View_515_Bald_PosterLow.xml": [("1248", "576", 1)],
    "View_520_Bald_TV.xml": [("1008", "567", 1)],
    "View_521_Bald_TV_Alternates.xml": [("528", "297", 1), ("1248", "576", 1)],
}
TILE_INCLUDE = re.compile(r"(Item|Tile|Poster)$")


def fade(animation):
    effects = animation.findall("effect")
    return [(e.get("type"), e.get("start"), e.get("end"), e.get("time"), e.get("delay"), e.get("tween"), e.get("easing"))
            for e in effects]


def parents(root):
    return {child: parent for parent in root.iter() for child in parent}


class ArtPlaceholderTests(unittest.TestCase):
    def setUp(self):
        self.definitions = include_definitions()

    def test_placeholder_arrives_only_after_the_art_layers_first_fade(self):
        definition = self.definitions["Bald_ArtPlaceholder"].find("definition")
        images = definition.findall("control")
        self.assertEqual([image.get("type") for image in images], ["image"])
        texture = images[0].find("texture")
        self.assertEqual((texture.text, texture.get("colordiffuse")), ("bald/white.png", "bald_placeholder"))
        animations = images[0].findall("animation")
        self.assertEqual([a.get("type") for a in animations], ["WindowOpen"])
        (effect,) = fade(animations[0])
        art_fadetime = int(self.definitions["Bald_ArtLayer"].find("definition/control/fadetime").text)
        self.assertEqual(effect[:3], ("fade", "0", "100"))
        self.assertEqual((effect[5], effect[6]), ("sine", "inout"), "fades are sine inout")
        self.assertGreaterEqual(int(effect[4]), art_fadetime, "the fill must not show under the art's first fade")
        self.assertEqual(effect[3], "380", "the arrival fade is the window-open fade")

    def test_every_art_frame_placeholder_uses_the_include(self):
        for name, frames in FRAMES.items():
            root = parse(SKIN / name)
            calls = root.iter("include")
            found = [(c.findtext("param[@name='width']"), c.findtext("param[@name='height']"))
                     for c in calls if c.get("content") == "Bald_ArtPlaceholder"]
            for width, height, count in frames:
                with self.subTest(file=name, frame=(width, height)):
                    self.assertEqual(found.count((width, height)), count)

    def test_no_raw_placeholder_remains_under_frame_art(self):
        # A raw placeholder fill may only draw inside a tile (an item layout or a tile include), never under
        # Bald_ArtLayer art, which fades in from nothing on every window open.
        for name in ("Home.xml",) + LIBRARY_VIEWS:
            root = parse(SKIN / name)
            up = parents(root)
            for texture in root.iter("texture"):
                if texture.get("colordiffuse") != "bald_placeholder":
                    continue
                node, tile = texture, False
                while node in up:
                    node = up[node]
                    if node.tag in ("itemlayout", "focusedlayout") or (
                            node.tag == "include" and TILE_INCLUDE.search(node.get("name") or "")):
                        tile = True
                with self.subTest(file=name, line=ET.tostring(texture)[:60]):
                    self.assertTrue(tile, "raw placeholder outside a tile: use Bald_ArtPlaceholder")

    def test_home_placeholder_sits_first_in_the_art_frame_under_the_layers(self):
        root = parse(SKIN / "Home.xml")
        frame = next(g for g in root.iter("control") if g.get("type") == "group"
                     and g.find("include[@content='Bald_ArtPlaceholder']") is not None)
        # Drawn children only: the frame's plain <include>name</include> entries are its animations.
        children = [c for c in frame if c.tag == "control" or (c.tag == "include" and c.get("content"))]
        self.assertEqual(children[0].get("content"), "Bald_ArtPlaceholder")
        self.assertEqual([c.get("content") for c in children[1:3]], ["Bald_ArtLayer", "Bald_ArtLayer"])
        self.assertEqual((frame.findtext("width"), frame.findtext("height")), ("1248", "702"))


class ScrimAndLogoTests(unittest.TestCase):
    """The logo scrim is a dark gradient: on a window open it comes in with the logo after the art starts."""

    def assert_logo_in_on_window_open(self, group, where):
        animations = [a for a in group.findall("animation") if a.get("type") == "WindowOpen"]
        self.assertEqual(len(animations), 1, where)
        self.assertEqual(fade(animations[0]), [("fade", "0", "100", "520", "380", "sine", "inout")], where)

    def test_home_scrim_and_clearlogos_fade_in_after_the_art_on_window_open(self):
        root = parse(SKIN / "Home.xml")
        group = next(g for g in root.iter("control") if g.get("type") == "group"
                     and g.find("include") is not None
                     and "Bald_ConfiguredArtLogos" in [i.text for i in g.findall("include")])
        self.assertIsNotNone(group.find("control/texture[.='bald/scrim_logo.png']"))
        self.assert_logo_in_on_window_open(group, "Home")

    def test_library_big_frames_do_the_same(self):
        for name, container in (("View_515_Bald_PosterLow.xml", "515"), ("View_521_Bald_TV_Alternates.xml", "523")):
            root = parse(SKIN / name)
            scrims = [t for t in root.iter("texture") if t.text == "bald/scrim_logo.png"
                      and f"Container({container})" in (parents(root)[t].findtext("visible") or "")]
            self.assertEqual(len(scrims), 1, name)
            up = parents(root)
            group = up[up[scrims[0]]]
            self.assertEqual(group.get("type"), "group", name)
            self.assertTrue(any("Logo" in (i.get("content") or "") for i in group.findall("include")), name)
            self.assert_logo_in_on_window_open(group, name)


class BackdropTests(unittest.TestCase):
    def setUp(self):
        self.root = parse(SKIN / "Includes_Bald_Home.xml")
        self.images = self.root.find("include[@name='Bald_BackdropImage']").findall("control")

    def test_backdrop_is_a_still_layer_under_the_crossfading_one(self):
        self.assertEqual([i.get("type") for i in self.images], ["image", "image"])
        still, crossfading = self.images
        self.assertIsNone(still.find("fadetime"))
        self.assertIsNone(still.find("texture").get("background"), "loaded in the foreground, so it is on frame 1")
        self.assertEqual(crossfading.findtext("fadetime"), "800")
        self.assertEqual(crossfading.find("texture").get("background"), "true")
        for key in ("texture", "visible", "colordiffuse", "aspectratio", "width", "height"):
            self.assertEqual(still.findtext(key), crossfading.findtext(key), key)
        self.assertIn("TMDbHelper.ListItem.BlurImage", still.findtext("texture"))
        self.assertEqual(still.findtext("colordiffuse"), "bald_backdrop")

    def test_both_layers_need_the_helper_and_the_setting(self):
        for image in self.images:
            self.assertTrue(equivalent(
                image.findtext("visible"),
                "!Skin.HasSetting(Bald.DisableBlur) + $EXP[Bald_HasTMDbHelper]"
                " + !String.IsEmpty(Window(home).Property(TMDbHelper.ListItem.BlurImage))"))


class StillBackgroundTests(unittest.TestCase):
    """The moving group (Bald_AnimWindowDepth) holds the content only; field and backdrop sit outside it."""

    def moving_group(self, root):
        groups = [c for c in root.find("controls") if c.get("type") == "group"
                  and c.find("include[@content='Bald_AnimWindowDepth']") is not None]
        self.assertEqual(len(groups), 1)
        return groups[0]

    def test_home_backdrop_is_outside_the_moving_group(self):
        root = parse(SKIN / "Home.xml")
        controls = list(root.find("controls"))
        moving = self.moving_group(root)
        backdrop = root.find("controls/include[@content='Bald_Backdrop']")
        self.assertLess(controls.index(backdrop), controls.index(moving))
        self.assertEqual(controls[0].find("texture").get("colordiffuse"), "bald_field")

    def test_library_draws_field_and_backdrop_outside_the_moving_group_for_bald_views(self):
        root = parse(SKIN / "MyVideoNav.xml")
        controls = list(root.find("controls"))
        moving = self.moving_group(root)
        still = next(c for c in controls if c.get("type") == "group" and c.find("include") is not None
                     and c.findtext("include") == "Bald_BackdropImage")
        self.assertLess(controls.index(still), controls.index(moving))
        self.assertTrue(equivalent(still.findtext("visible"), "$EXP[Bald_LibraryViewActive]"))
        field = still.find("control[@type='image']/texture")
        self.assertEqual((field.text, field.get("colordiffuse")), ("bald/white.png", "bald_field"))
        self.assertIsNone(still.find("animation"), "the still background never animates")
        estuary = root.find("controls/include[.='DefaultBackground']")
        self.assertLess(controls.index(estuary), controls.index(still))


if __name__ == "__main__":
    unittest.main()
