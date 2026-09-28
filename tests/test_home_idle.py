"""Home idle (ambient mode): the art frame expands to 96,120 1728 x 840 (equal 96 / 120 px margins) and everything it
covers fades out.

The frame group zooms uniformly (Kodi cannot animate a size) while a full-size layer of the same art fades in over it,
so the growth reads as one expansion without stretching; a big clearlogo and a small clock sit in its lower corners.
The timings are the Bald_Idle* constants (Includes_Bald_Home.xml); the tests below hold how they relate, so the
sequence cannot drift apart when one is tuned. Over background video, under Reduce motion and with idle off see the
tests below."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import equivalent, implies
from kodi_includes import Skin, constants, expand_call, include_definitions
from motion import FULL, REDUCE, split

XML = Path(__file__).resolve().parents[1] / "1080i"
BIG = (96, 120, 1728, 840)
# The frame's art box on every row style: 1248 x 702 at 96,120 (a poster row shows 120-696 of it through its masks,
# the art nudged up 63 px; idle undoes the nudge). The art is 16:9 fanart.
ART = (96, 120, 1248, 702)
EXPAND, WAKE = "$EXP[Bald_IdleExpand]", "!$EXP[Bald_IdleExpand]"


def includes():
    return ET.parse(XML / "Includes_Bald_Home.xml").getroot()


def expression(name):
    return includes().findtext(f"expression[@name='{name}']")


def expanded(name, params=None):
    """What an include expands to, nested includes, $PARAM and constants resolved (as Kodi loads it)."""
    holder = ET.Element("holder")
    holder.extend(expand_call(name, params))
    return holder


def conditionals(node):
    return [a for a in node.iter("animation") if a.get("type") == "Conditional"]


def pair(node):
    """{condition: effect} of an include's paired Conditionals (one effect each)."""
    result = {}
    for animation in conditionals(node):
        effects = animation.findall("effect")
        assert len(effects) == 1, ET.tostring(animation)
        result[animation.get("condition")] = effects[0]
    return result


def span(effect):
    """(start, end) in ms of an effect after its condition changes."""
    delay = int(effect.get("delay", "0"))
    return delay, delay + int(effect.get("time", "0"))


def layers():
    """The groups of Bald_IdleFrame by role, with their resolved animations."""
    groups = [g for g in expanded("Bald_IdleFrame").findall("control") if g.get("type") == "group"]
    masks = groups[0]  # the idle masks come first, under the rest
    full =next(g for g in groups if g.findtext("control[@type='image']/texture") == "$VAR[Bald_Fanart]")
    logo = next(g for g in groups if any(i.findtext("texture") == "$VAR[Bald_Logo]" for i in g.findall("control[@type='image']")))
    clock = next(g for g in groups if g.find("control[@type='label']") is not None)
    return {"masks": masks, "full": full, "logo": logo, "clock": clock}


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


class IdleTimingTableTests(unittest.TestCase):
    """The sequence, from the constants: enter, then wake."""

    def setUp(self):
        self.values = {k: int(v) for k, v in constants().items() if k.startswith("Bald_Idle")}
        self.frame = pair(expanded("Bald_AnimIdleFrame"))
        self.chrome = pair(expanded("Bald_AnimIdleChrome"))
        self.overlay = pair(expanded("Bald_AnimIdleArtOverlay"))
        self.frame_masks = pair(expanded("Bald_AnimIdleMasks"))
        self.layers = {name: pair(group) for name, group in layers().items()}

    def test_every_timing_is_a_constant(self):
        # No literal times in the idle includes: each names a Bald_Idle* constant, so the table is the one place to tune.
        definitions = include_definitions()
        for name in ("Bald_AnimIdleFrame", "Bald_AnimIdleChrome", "Bald_AnimIdleArtOverlay", "Bald_AnimIdleMasks",
                     "Bald_IdleFrame"):
            node = definitions[name]
            # (Visible / Hidden fades and <fadetime> crossfade items and logos, not the idle sequence.)
            values = [e.get(k) for a in conditionals(node) for e in a.iter("effect") for k in ("time", "delay")
                      if e.get(k) is not None]
            values += [p.text for p in node.iter("param") if p.get("name") in ("in", "in_delay", "out", "out_delay",
                                                                              "back", "back_delay")]
            with self.subTest(include=name):
                for value in values:
                    self.assertTrue(value == "0" or value in self.values, value)
        # The poster row's nudge undo too.
        undo = [a for a in conditionals(definitions["Bald_AnimPosterArt"]) if "+ $EXP[Bald_IdleZoom]]" in a.get("condition")]
        self.assertEqual([(a.find("effect").get("time"), a.find("effect").get("delay")) for a in undo],
                         [("Bald_IdleGrowTime", "Bald_IdleGrowDelay")])

    def test_enter(self):
        grow = span(self.frame[f"[{EXPAND}] + {FULL}"])
        # The chrome is out before the frame starts to grow.
        self.assertEqual(span(self.chrome[EXPAND]), (0, grow[0]))
        # The full-size layer fades in over exactly the zoom.
        self.assertEqual(span(self.layers["full"][EXPAND]), grow)
        # The frame's logo overlay and masks leave as the zoom starts; the idle masks are there at once.
        self.assertEqual(span(self.overlay[EXPAND])[0], grow[0])
        self.assertEqual(span(self.frame_masks[EXPAND])[0], grow[0])
        self.assertEqual(span(self.layers["masks"][EXPAND]), (0, 0))
        # The small clock, then the big clearlogo, come in once the zoom is well under way (cubic out: most of the move
        # is done in its first half), before it settles.
        clock, logo = span(self.layers["clock"][EXPAND]), span(self.layers["logo"][EXPAND])
        for start, end in (clock, logo):
            self.assertGreater(start, grow[0] + (grow[1] - grow[0]) // 3)
            self.assertLess(start, grow[1])
        self.assertLess(clock[0], logo[0])

    def test_wake(self):
        shrink = span(self.frame[f"[{WAKE}] + {FULL}"])
        self.assertEqual(shrink[0], 0)
        # The full-size layer leaves over exactly the shrink; the chrome waits for it.
        self.assertEqual(span(self.layers["full"][WAKE]), shrink)
        self.assertEqual(span(self.chrome[WAKE])[0], shrink[1])
        # The frame's masks come back as the shrink ends, and are fully back before the idle masks start to leave, which
        # they do only once the frame has shrunk: the two overlap, so the art's edges are never uncovered.
        masks_back = span(self.frame_masks[WAKE])
        idle_masks_out = span(self.layers["masks"][WAKE])
        self.assertLess(masks_back[0], shrink[1])
        self.assertGreaterEqual(masks_back[1], shrink[1])
        self.assertLessEqual(masks_back[1], idle_masks_out[0])
        self.assertGreaterEqual(idle_masks_out[0], shrink[1])
        # The frame's logo overlay is back after the shrink; the big clearlogo and small clock leave at once, together.
        self.assertGreaterEqual(span(self.overlay[WAKE])[1], shrink[1])
        self.assertEqual(span(self.layers["logo"][WAKE]), span(self.layers["clock"][WAKE]))
        self.assertEqual(span(self.layers["logo"][WAKE])[0], 0)

    def test_the_approved_values(self):
        # The approved sequence (docs/SPEC.md, idle); a change here is a change to the design.
        self.assertEqual(self.values, {
            "Bald_IdleGrowDelay": 300, "Bald_IdleGrowTime": 900, "Bald_IdleOverlayOutTime": 200,
            "Bald_IdleFrameMasksOutTime": 150, "Bald_IdleClockInDelay": 700, "Bald_IdleClockInTime": 400,
            "Bald_IdleLogoInDelay": 800, "Bald_IdleLogoInTime": 500, "Bald_IdleShrinkTime": 480,
            "Bald_IdleChromeBackTime": 360, "Bald_IdleFrameMasksBackDelay": 450, "Bald_IdleFrameMasksBackTime": 100,
            "Bald_IdleMasksOutDelay": 600, "Bald_IdleMasksOutTime": 80, "Bald_IdleOverlayBackDelay": 400,
            "Bald_IdleOverlayBackTime": 400, "Bald_IdleCornerOutTime": 150})


class IdleFrameGeometryTests(unittest.TestCase):
    def zooms(self):
        return {split(a.get("condition"))[1]: a.find("effect") for a in conditionals(expanded("Bald_AnimIdleFrame"))}

    def test_the_zoom_maps_the_frame_art_onto_the_full_layers_crop(self):
        x, y, w, h = ART
        bx, by, bw, bh = BIG
        scale = bw / w
        # The full-size layer (aspectratio scale) fills the big rect's width with the 16:9 art and crops it vertically,
        # centred: the art spans by + (bh - h * scale) / 2 for h * scale.
        top, height = by + (bh - h * scale) / 2, h * scale
        grow, shrink = self.zooms()[EXPAND], self.zooms()[WAKE]
        self.assertAlmostEqual(float(grow.get("end")) / 100, scale, places=4)
        self.assertEqual((grow.get("start"), shrink.get("start"), shrink.get("end")), ("100", grow.get("end"), "100"))
        self.assertEqual(grow.get("center"), shrink.get("center"))
        cx, cy = (float(v) for v in grow.get("center").split(","))

        def zoom(px, py):
            s = float(grow.get("end")) / 100
            return cx + s * (px - cx), cy + s * (py - cy)

        left, art_top = zoom(x, y)
        right, art_bottom = zoom(x + w, y + h)
        self.assertAlmostEqual(left, bx, delta=0.1)
        self.assertAlmostEqual(right, bx + bw, delta=0.1)
        self.assertAlmostEqual(art_top, top, delta=0.1)
        self.assertAlmostEqual(art_bottom, top + height, delta=0.1)
        # 54 to 1026: it spills 66 px above and below the big rect, which the idle masks cover.
        self.assertAlmostEqual(art_top, 54, delta=0.1)

    def test_grow_and_shrink_curves(self):
        for effect in self.zooms().values():
            self.assertEqual((effect.get("tween"), effect.get("easing")), ("cubic", "out"))
        for animation in conditionals(expanded("Bald_AnimIdleFrame")):
            self.assertEqual(animation.get("reversible"), "false")

    def test_a_poster_row_undoes_its_nudge_in_step(self):
        # Every row style ends at the same big rect: a poster row's art (nudged up 63 px) goes back to the landscape
        # position over the grow, so the one zoom maps it the same way.
        art = expanded("Bald_AnimPosterArt")
        undo = [a for a in conditionals(art)
                if split(a.get("condition"))[0] == "full"
                and equivalent(split(a.get("condition"))[1], "$EXP[Bald_PosterRow] + $EXP[Bald_IdleZoom]")]
        self.assertEqual(len(undo), 1)
        effect = undo[0].find("effect")
        grow = self.zooms()[EXPAND]
        self.assertEqual((effect.get("start"), effect.get("end")), ("0,-63", "0,0"))
        self.assertEqual(span(effect), span(grow))
        # The nudge itself holds only while not expanding.
        nudges = [a for a in conditionals(art) if a.find("effect").get("end") == "0,-63"]
        self.assertTrue(nudges)
        for animation in nudges:
            self.assertTrue(implies(split(animation.get("condition"))[1], "!$EXP[Bald_IdleZoom]"))

    def test_the_full_layer(self):
        layer = layers()["full"]
        self.assertEqual(tuple(int(layer.findtext(k)) for k in ("left", "top", "width", "height")), BIG)
        image = layer.find("control[@type='image']")
        self.assertEqual((image.findtext("width"), image.findtext("height"), image.findtext("aspectratio")),
                         ("1728", "840", "scale"))
        texture = image.find("texture")
        self.assertEqual((texture.text, texture.get("background")), ("$VAR[Bald_Fanart]", "true"))
        # It crossfades a new item as the frame's layers do.
        frame_fade = include_definitions()["Bald_ArtLayer"].find(".//control[@type='image']").findtext("fadetime")
        self.assertEqual(image.findtext("fadetime"), frame_fade)

    def test_idle_masks_cover_everything_outside_the_big_rect(self):
        body = include_definitions()["Bald_IdleFrame"]
        masks = [g for g in body.findall("control") if g.find("include[@content='Bald_BackdropWindow']") is not None]
        self.assertEqual(len(masks), 1)
        rects = {tuple(int(c.findtext(f"param[@name='{k}']")) for k in "xywh")
                 for c in masks[0].findall("include[@content='Bald_BackdropWindow']")}
        self.assertEqual(rects, {(0, 0, 96, 1080), (1824, 0, 96, 1080), (96, 0, 1728, 120), (96, 960, 1728, 120)})


class IdleLayerAnimationTests(unittest.TestCase):
    def test_the_pairs(self):
        # Layers shown only while expanded rest at alpha 0; what idle hides rests at 100. Sine in-out fades, paired
        # non-reversible Conditionals.
        for name, rest in (("Bald_AnimIdleLayer", "0"), ("Bald_AnimIdleHide", "100")):
            animations = conditionals(include_definitions()[name])
            self.assertEqual(len(animations), 2)
            self.assertEqual(animations[1].get("condition"), "!" + animations[0].get("condition"))
            self.assertEqual(animations[1].find("effect").get("end"), rest)
            self.assertEqual(animations[0].find("effect").get("start"), rest)
            for animation in animations:
                self.assertEqual(animation.get("reversible"), "false")
                effect = animation.find("effect")
                self.assertEqual((effect.get("type"), effect.get("tween"), effect.get("easing")), ("fade", "sine", "inout"))

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
        row = include_definitions()["Bald_Row"]
        for control in row.findall("control"):
            with self.subTest(control=control.get("type")):
                self.assertIn("Bald_AnimIdleChrome", [i.text for i in control.findall("include")])

    def test_no_idle_dim_is_left(self):
        # The old dims (rows 100 to 40, the section line to 45) are gone; what fades on plain Bald_Idle fades to 0
        # (the row dots, count and menu hint, which is all that changes over background video).
        for name in ("Home.xml", "Includes_Bald_Home.xml"):
            for animation in ET.parse(XML / name).getroot().iter("animation"):
                if "Bald_Idle]" not in (animation.get("condition") or ""):
                    continue
                with self.subTest(file=name, condition=animation.get("condition")):
                    self.assertEqual([e.get("end") for e in animation.findall("effect")], ["0"])


class IdleClockAndLogoTests(unittest.TestCase):
    def test_the_small_clock(self):
        clock = layers()["clock"]
        self.assertEqual(tuple(int(clock.findtext(k)) for k in ("left", "top", "width", "height")), BIG)
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

    def test_the_idle_clearlogo(self):
        logo = layers()["logo"]
        image = next(i for i in logo.findall("control[@type='image']") if i.findtext("texture") == "$VAR[Bald_Logo]")
        self.assertEqual(image.findtext("visible"), "$EXP[Bald_ShowClearlogo]")
        # Lower left of the big frame, inside it.
        self.assertLessEqual(int(image.findtext("left")) + int(image.findtext("width")), 1728 // 2)
        bottom = int(image.findtext("top")) + int(image.findtext("height"))
        self.assertLess(bottom, 840)
        self.assertGreaterEqual(bottom, 840 - 96)


class IdleReduceMotionTests(unittest.TestCase):
    def test_zooms_are_full_motion_only_and_the_crossfade_stays(self):
        for animation in conditionals(include_definitions()["Bald_AnimIdleFrame"]):
            self.assertEqual(split(animation.get("condition"))[0], "full")
            self.assertEqual([e.get("type") for e in animation.findall("effect")], ["zoom"])
        text = ET.tostring(includes().find("include[@name='Bald_AnimIdleFrame']"), encoding="unicode")
        self.assertNotIn(REDUCE, text)
        # The fades that make the crossfade are ungated, so they run under Reduce motion too.
        for name in ("Bald_AnimIdleLayer", "Bald_AnimIdleHide", "Bald_AnimIdleChrome", "Bald_AnimIdleArtOverlay",
                     "Bald_AnimIdleMasks"):
            text = ET.tostring(expanded(name, {"in": "1", "out": "1", "back": "1"}), encoding="unicode")
            self.assertNotIn(FULL, text, name)
            self.assertNotIn(REDUCE, text, name)
            self.assertNotIn("Bald_IdleZoom", text, name)
        # Under Reduce motion a poster row keeps its nudge (the frame does not change) while idle.
        self.assertTrue(implies("$EXP[Bald_ReduceMotion]", "!$EXP[Bald_IdleZoom]"))


class IdleOverSkinTests(unittest.TestCase):
    def test_the_resolved_home_window_has_one_idle_frame(self):
        home = Skin().window("Home.xml")
        big = [c for c in home.iter("control") if c.get("type") == "image" and c.findtext("width") == "1728"
               and c.findtext("height") == "840" and c.findtext("texture") == "$VAR[Bald_Fanart]"]
        self.assertEqual(len(big), 1)
        # Every idle time resolves to a number: a mistyped constant name would reach Kodi as 0 (no animation).
        for effect in home.iter("effect"):
            for key in ("time", "delay"):
                value = effect.get(key)
                if value is not None and "$" not in value:
                    self.assertTrue(value.isdigit(), f"{key}={value}")


if __name__ == "__main__":
    unittest.main()
