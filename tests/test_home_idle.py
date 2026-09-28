"""Home idle: the art frame expands to 96,120 1728 x 840 (equal 96 / 120 px margins) instead of the rows dimming.

The frame group zooms uniformly (Kodi cannot animate a size) while a full-size layer of the same art fades in over it,
so the growth reads as one expansion without stretching; everything the big frame covers fades out, and a small clock
sits in its lower right. Over background video, under Reduce motion and with idle off see the tests below."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import equivalent, implies
from kodi_includes import Skin, include_definitions
from motion import FULL, REDUCE, split

XML = Path(__file__).resolve().parents[1] / "1080i"
BIG = (96, 120, 1728, 840)
# The frame's art box on every row style: 1248 x 702 at 96,120 (a poster row shows the middle 576 of it through its
# masks, the art nudged up 63 px; idle undoes the nudge). The art is 16:9 fanart.
ART = (96, 120, 1248, 702)


def includes():
    return ET.parse(XML / "Includes_Bald_Home.xml").getroot()


def expression(name):
    return includes().findtext(f"expression[@name='{name}']")


def definition(name):
    return include_definitions()[name]


def conditionals(node):
    return [a for a in node.iter("animation") if a.get("type") == "Conditional"]


def fade(animation):
    effect = animation.find("effect[@type='fade']")
    return effect.get("start"), effect.get("end"), effect.get("time"), effect.get("delay", "0")


def number(value):
    return float(value)


class IdleConditionTests(unittest.TestCase):
    def test_when_the_frame_expands(self):
        body = expression("Bald_IdleExpand")
        # Idle on Home (so never with Idle after = Off: Bald_IdleReached never holds, tests/test_idle.py), once the idle
        # timer has parked focus on the wake button, which also closes the menu.
        self.assertTrue(implies(body, "$EXP[Bald_Idle]"))
        self.assertTrue(implies(body, "$EXP[Bald_IdleReached]"))
        self.assertTrue(implies(body, "Control.HasFocus(9199)"))
        self.assertTrue(implies(body, "!$EXP[Bald_MenuOpen]"))
        # Never over background video (the masks cannot be drawn over it), under a dialog, or with info open.
        self.assertTrue(implies(body, "!$EXP[Bald_VideoBackdropOn]"))
        self.assertTrue(implies(body, "!$EXP[Bald_DialogOver]"))
        self.assertTrue(implies(body, "!$EXP[Bald_InfoOpen]"))
        # The zoom is full motion only.
        self.assertTrue(equivalent(expression("Bald_IdleZoom"), "$EXP[Bald_IdleExpand] + $EXP[Bald_FullMotion]"))


class IdleFrameGeometryTests(unittest.TestCase):
    def zooms(self):
        return {split(a.get("condition"))[1]: a.find("effect") for a in conditionals(definition("Bald_AnimIdleFrame"))}

    def test_the_zoom_maps_the_frame_art_onto_the_full_layers_crop(self):
        x, y, w, h = ART
        bx, by, bw, bh = BIG
        scale = bw / w
        # The full-size layer (aspectratio scale) fills the big rect's width with the 16:9 art and crops it vertically,
        # centred: the art spans by + (bh - h * scale) / 2 for h * scale.
        top, height = by + (bh - h * scale) / 2, h * scale
        grow, shrink = self.zooms()["$EXP[Bald_IdleExpand]"], self.zooms()["!$EXP[Bald_IdleExpand]"]
        self.assertAlmostEqual(number(grow.get("end")) / 100, scale, places=4)
        self.assertEqual((grow.get("start"), shrink.get("start"), shrink.get("end")), ("100", grow.get("end"), "100"))
        self.assertEqual(grow.get("center"), shrink.get("center"))
        cx, cy = (number(v) for v in grow.get("center").split(","))

        def zoom(px, py):
            s = number(grow.get("end")) / 100
            return cx + s * (px - cx), cy + s * (py - cy)

        left, art_top = zoom(x, y)
        right, art_bottom = zoom(x + w, y + h)
        self.assertAlmostEqual(left, bx, delta=0.1)
        self.assertAlmostEqual(right, bx + bw, delta=0.1)
        self.assertAlmostEqual(art_top, top, delta=0.1)
        self.assertAlmostEqual(art_bottom, top + height, delta=0.1)
        # 54 to 1026: it spills 66 px above and below the big rect, which the idle masks cover.
        self.assertAlmostEqual(art_top, 54, delta=0.1)

    def test_grow_and_shrink_timing(self):
        grow, shrink = self.zooms()["$EXP[Bald_IdleExpand]"], self.zooms()["!$EXP[Bald_IdleExpand]"]
        self.assertEqual((grow.get("time"), grow.get("tween"), grow.get("easing")), ("900", "cubic", "out"))
        self.assertEqual((shrink.get("time"), shrink.get("tween"), shrink.get("easing")), ("480", "cubic", "out"))
        for animation in conditionals(definition("Bald_AnimIdleFrame")):
            self.assertEqual(animation.get("reversible"), "false")

    def test_a_poster_row_undoes_its_nudge_in_step(self):
        # Every row style ends at the same big rect: a poster row's art (nudged up 63 px) goes back to the landscape
        # position over the grow, so the one zoom maps it the same way.
        art = definition("Bald_AnimPosterArt")
        undo = [a for a in conditionals(art)
                if split(a.get("condition"))[0] == "full"
                and equivalent(split(a.get("condition"))[1], "$EXP[Bald_PosterRow] + $EXP[Bald_IdleZoom]")]
        self.assertEqual(len(undo), 1)
        effect = undo[0].find("effect")
        grow = self.zooms()["$EXP[Bald_IdleExpand]"]
        self.assertEqual((effect.get("start"), effect.get("end"), effect.get("time")), ("0,-63", "0,0", grow.get("time")))
        # The nudge itself holds only while not expanding.
        nudges = [a for a in conditionals(art) if a.find("effect").get("end") == "0,-63"]
        self.assertTrue(nudges)
        for animation in nudges:
            self.assertTrue(implies(split(animation.get("condition"))[1], "!$EXP[Bald_IdleZoom]"))

    def test_the_full_layer(self):
        body = definition("Bald_IdleFrame")
        groups = [g for g in body.findall("control") if g.get("type") == "group"]
        layer = next(g for g in groups if g.find("control[@type='image']/aspectratio") is not None
                     and g.findtext("control[@type='image']/aspectratio") == "scale")
        self.assertEqual(tuple(int(layer.findtext(k).replace("Bald_SafeLeft", "96")) for k in ("left", "top", "width", "height")), BIG)
        image = layer.find("control[@type='image']")
        self.assertEqual((image.findtext("width"), image.findtext("height")), ("1728", "840"))
        texture = image.find("texture")
        self.assertEqual((texture.text, texture.get("background")), ("$VAR[Bald_Fanart]", "true"))
        # It crossfades a new item as the frame's layers do.
        frame_fade = definition("Bald_ArtLayer").find(".//control[@type='image']").findtext("fadetime")
        self.assertEqual(image.findtext("fadetime"), frame_fade)
        # In over the grow, out over the shrink; the frame, fading, never goes see-through: alpha 0 at rest.
        call = layer.find("include[@content='Bald_AnimIdleLayer']")
        params = {p.get("name"): p.text for p in call.findall("param")}
        self.assertEqual((params["time"], params["out"]), ("900", "480"))

    def test_idle_masks_cover_everything_outside_the_big_rect(self):
        body = definition("Bald_IdleFrame")
        masks = [g for g in body.findall("control") if g.find("include[@content='Bald_BackdropWindow']") is not None]
        self.assertEqual(len(masks), 1)
        rects = {tuple(int(c.findtext(f"param[@name='{k}']")) for k in "xywh")
                 for c in masks[0].findall("include[@content='Bald_BackdropWindow']")}
        self.assertEqual(rects, {(0, 0, 96, 1080), (1824, 0, 96, 1080), (96, 0, 1728, 120), (96, 960, 1728, 120)})
        params = {p.get("name"): p.text for p in masks[0].find("include[@content='Bald_AnimIdleLayer']").findall("param")}
        # There at once, gone once the frame has shrunk (480).
        self.assertEqual(params["time"], "0")
        self.assertGreaterEqual(int(params["out_delay"]), 480)


class IdleLayerAnimationTests(unittest.TestCase):
    def test_the_layer_pair_rests_at_alpha_0(self):
        pair = conditionals(definition("Bald_AnimIdleLayer"))
        self.assertEqual([a.get("condition") for a in pair], ["$EXP[Bald_IdleExpand]", "!$EXP[Bald_IdleExpand]"])
        self.assertEqual([fade(a)[:2] for a in pair], [("0", "100"), ("100", "0")])
        for animation in pair:
            self.assertEqual(animation.get("reversible"), "false")
            effect = animation.find("effect")
            self.assertEqual((effect.get("tween"), effect.get("easing")), ("sine", "inout"))

    def test_the_chrome_fades_out_under_the_big_frame(self):
        # Out first, before the frame grows (its zoom waits 300); back last, once the 480 shrink is done.
        chrome = conditionals(definition("Bald_AnimIdleChrome"))
        self.assertEqual([c.get("condition") for c in chrome], ["$EXP[Bald_IdleExpand]", "!$EXP[Bald_IdleExpand]"])
        out, back = chrome
        self.assertEqual((out.find("effect").get("start"), out.find("effect").get("end"), out.find("effect").get("time")), ("100", "0", "300"))
        self.assertEqual((back.find("effect").get("start"), back.find("effect").get("end"), back.find("effect").get("time"),
                          back.find("effect").get("delay")), ("0", "100", "360", "480"))
        grow = conditionals(definition("Bald_AnimIdleFrame"))[0].find("effect")
        self.assertEqual(grow.get("delay"), out.find("effect").get("time"), "the frame grows once the chrome is out")
        shrink = conditionals(definition("Bald_AnimIdleFrame"))[1].find("effect")
        self.assertEqual(int(back.find("effect").get("delay")), int(shrink.get("time")), "the chrome returns once it has shrunk")
        for anim in chrome:
            self.assertEqual([e.get("type") for e in anim.findall("effect")], ["fade"])

    def test_home_uses_them(self):
        raw = ET.parse(XML / "Home.xml").getroot()
        groups = [g for g in raw.iter("control") if g.get("type") in ("group", "grouplist")]

        def carrying(name):
            return [g for g in groups if name in [i.text for i in g.findall("include")]]

        frame = carrying("Bald_AnimIdleFrame")
        self.assertEqual(len(frame), 1)
        self.assertIn("Bald_AnimInfoFrame", [i.text for i in frame[0].findall("include")])
        self.assertIn("Bald_AnimPosterArt", [i.text for i in frame[0].findall("include")])
        self.assertEqual(len(carrying("Bald_AnimIdleArtOverlay")), 1)
        self.assertIn("Bald_ConfiguredArtLogos", [i.text for i in carrying("Bald_AnimIdleArtOverlay")[0].findall("include")])
        self.assertIn("Bald_HomeFrameMasks", [i.text for i in carrying("Bald_AnimIdleMasks")[0].findall("include")])
        # Clock and date, caption, section line.
        chrome = carrying("Bald_AnimIdleChrome")
        self.assertIn("$EXP[Bald_ShowHomeClock]", [g.findtext("visible") for g in chrome])
        self.assertIn("Bald_ConfiguredCaptions", [i.text for g in chrome for i in g.findall("include")])
        self.assertTrue(any(g.get("type") == "grouplist" and g.findtext("top") == "966" for g in chrome))
        # The expanded frame sits over the frame masks and under the chrome.
        order = [c for c in raw.iter() if c.tag in ("include", "control")]
        names = [c.text if c.tag == "include" else None for c in order]
        self.assertLess(names.index("Bald_HomeFrameMasks"), names.index("Bald_IdleFrame"))
        self.assertLess(names.index("Bald_IdleFrame"), names.index("Bald_ConfiguredCaptions"))
        self.assertLess(names.index("Bald_IdleFrame"), names.index("Bald_GeneratedRows"))

    def test_the_rows_fade_out_instead_of_dimming(self):
        row = definition("Bald_Row")
        for control in row.findall("control"):
            with self.subTest(control=control.get("type")):
                self.assertIn("Bald_AnimIdleChrome", [i.text for i in control.findall("include")])

    def test_no_idle_dim_is_left(self):
        # The old dims (rows 100 to 40, the section line to 45) are gone; what fades on plain Bald_Idle now fades to 0
        # (the row dots, count and menu hint, which is all that changes over background video).
        for name in ("Home.xml", "Includes_Bald_Home.xml"):
            for animation in ET.parse(XML / name).getroot().iter("animation"):
                if "Bald_Idle]" not in (animation.get("condition") or ""):
                    continue
                with self.subTest(file=name, condition=animation.get("condition")):
                    self.assertEqual([e.get("end") for e in animation.findall("effect")], ["0"])


class IdleClockAndLogoTests(unittest.TestCase):
    def groups(self):
        return [g for g in definition("Bald_IdleFrame").findall("control") if g.get("type") == "group"]

    def test_the_small_clock(self):
        clock = next(g for g in self.groups() if g.find("control[@type='label']") is not None)
        self.assertEqual((clock.findtext("left"), clock.findtext("top"), clock.findtext("width"), clock.findtext("height")),
                         ("Bald_SafeLeft", "120", "1728", "840"))
        # It follows Appearance › Date & time, and hides with Home's clock.
        self.assertEqual(clock.findtext("visible"), "$EXP[Bald_ShowHomeClock]")
        label = clock.find("control[@type='label']")
        self.assertEqual(label.findtext("label"), "$VAR[Bald_ClockTime]")
        self.assertEqual(label.findtext("textcolor"), "bald_ink")
        self.assertEqual(label.findtext("align"), "right")
        # 32 px in from the big frame's right and bottom edges.
        self.assertEqual(1728 - int(label.findtext("left")) - int(label.findtext("width")), 32)
        self.assertEqual(840 - int(label.findtext("top")) - int(label.findtext("height")), 32)
        # A pure black gradient in the corner behind it (no field tint).
        scrim = clock.find("control[@type='image']")
        self.assertEqual(scrim.findtext("texture"), "bald/scrim_logo.png")
        self.assertEqual(scrim.find("texture").get("flipx"), "true")
        self.assertIsNone(scrim.find("texture").get("colordiffuse"))
        self.assertEqual(int(scrim.findtext("left")) + int(scrim.findtext("width")), 1728)
        self.assertEqual(int(scrim.findtext("top")) + int(scrim.findtext("height")), 840)
        # In after the expansion, out at once on waking.
        params = {p.get("name"): p.text for p in clock.find("include[@content='Bald_AnimIdleLayer']").findall("param")}
        self.assertGreaterEqual(int(params["delay"]), 400)
        self.assertEqual(params.get("out_delay", "0"), "0")

    def test_the_idle_clearlogo(self):
        logo = next(g for g in self.groups()
                    if any(i.findtext("texture") == "$VAR[Bald_Logo]" for i in g.findall("control[@type='image']")))
        image = next(i for i in logo.findall("control[@type='image']") if i.findtext("texture") == "$VAR[Bald_Logo]")
        self.assertEqual(image.findtext("visible"), "$EXP[Bald_ShowClearlogo]")
        # Lower left of the big frame, inside it.
        self.assertLessEqual(int(image.findtext("left")) + int(image.findtext("width")), 1728 // 2)
        bottom = int(image.findtext("top")) + int(image.findtext("height"))
        self.assertLess(bottom, 840)
        self.assertGreaterEqual(bottom, 840 - 96)


class IdleReduceMotionTests(unittest.TestCase):
    def test_zooms_are_full_motion_only_and_the_crossfade_stays(self):
        for animation in conditionals(definition("Bald_AnimIdleFrame")):
            self.assertEqual(split(animation.get("condition"))[0], "full")
            self.assertEqual([e.get("type") for e in animation.findall("effect")], ["zoom"])
        text = ET.tostring(includes().find("include[@name='Bald_AnimIdleFrame']"), encoding="unicode")
        self.assertNotIn(REDUCE, text)
        # The fades that make the crossfade are ungated, so they run under Reduce motion too.
        for name in ("Bald_AnimIdleLayer", "Bald_AnimIdleChrome", "Bald_AnimIdleArtOverlay", "Bald_AnimIdleMasks"):
            text = ET.tostring(includes().find(f"include[@name='{name}']"), encoding="unicode")
            self.assertNotIn(FULL, text, name)
            self.assertNotIn(REDUCE, text, name)
        # Under Reduce motion a poster row keeps its nudge (the frame does not change) while idle.
        self.assertTrue(implies("$EXP[Bald_ReduceMotion]", "!$EXP[Bald_IdleZoom]"))


class IdleOverSkinTests(unittest.TestCase):
    def test_the_resolved_home_window_has_one_idle_frame(self):
        home = Skin().window("Home.xml")
        big = [c for c in home.iter("control") if c.get("type") == "image" and c.findtext("width") == "1728"
               and c.findtext("height") == "840" and c.findtext("texture") == "$VAR[Bald_Fanart]"]
        self.assertEqual(len(big), 1)


if __name__ == "__main__":
    unittest.main()
