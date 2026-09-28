"""Info page transitions: Home's frame zoom hands off to the dialog, which draws the art layers (scrims on Overview, the
blurred backdrop on Cast and More) and the pages over it; opened away from Home the dialog draws its own sharp backdrop.
The timings are constants (Bald_InfoZoom* / Bald_InfoReturn* in Includes_Bald_Home.xml, the dialog's in
Includes_Bald_Info.xml); the tests hold how they relate."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from kodi_includes import CONSTANT_ATTRIBUTES, NATIVE, constants, expand_call, parse
from motion import split

XML = Path(__file__).resolve().parents[1] / "1080i"
OWN = "$EXP[Bald_InfoOwnBackdrop]"


def window_animations(control):
    """{(type, condition): fade effect} of a control's WindowOpen / WindowClose animations (long or short form)."""
    result = {}
    for animation in control.findall("animation"):
        kind = animation.get("type") or (animation.text or "").strip()
        if kind not in ("WindowOpen", "WindowClose"):
            continue
        effect = animation.find("effect") if animation.find("effect") is not None else animation
        result[(kind, animation.get("condition"))] = (int(effect.get("time")), int(effect.get("delay", "0")))
    return result


class InfoDialogTimingTests(unittest.TestCase):
    def setUp(self):
        self.dialog = parse(XML / "DialogVideoInfo.xml")
        groups = self.dialog.find("controls").findall("control[@type='group']")
        self.backdrop = next(g for g in groups if g.findtext("visible") == OWN)
        self.art = next(g for g in groups if g.find(".//control[@id='5200']") is not None)
        self.pages = next(g for g in groups if g.find("include") is not None
                          and "Bald_InfoCastPage" in [i.text for i in g.findall("include")])
        self.values = {k: int(v) for k, v in constants().items() if k.startswith("Bald_Info")}

    def test_the_art_layers_leave_with_the_backdrop_they_cover(self):
        # Over the dialog's own backdrop the scrims and the Cast and More backdrop come and go with it: gone sooner,
        # the blurred backdrop uncovered the sharp fanart for a moment before it dissolved (closing from Cast or More).
        own = window_animations(self.backdrop)
        art = window_animations(self.art)
        self.assertEqual(art[("WindowOpen", OWN)], own[("WindowOpen", None)])
        self.assertEqual(art[("WindowClose", OWN)], own[("WindowClose", None)])
        # From Home they leave with the text, before the frame returns.
        pages = window_animations(self.pages)
        self.assertEqual(art[("WindowClose", "!" + OWN)], pages[("WindowClose", None)])
        self.assertEqual(art[("WindowOpen", "!" + OWN)], pages[("WindowOpen", None)])
        # The text leaves faster than the art dissolves (a 130 fade of the full-screen art read as a snap).
        self.assertLess(pages[("WindowClose", None)][0], own[("WindowClose", None)][0])
        # Both art layers sit in that one group, Overview's scrims and the Cast and More backdrop crossfading.
        scrims = next(g for g in self.art.findall("control") if g.findtext("include") == "Bald_InfoScrims")
        blur = self.art.find("control[@id='5200']")
        self.assertEqual(scrims.findtext("visible"), "$EXP[Bald_InfoOnOverview]")
        self.assertEqual(blur.findtext("visible"), "!$EXP[Bald_InfoOnOverview]")

    def test_from_home_the_dialog_waits_for_the_zoom(self):
        pages = window_animations(self.pages)[("WindowOpen", None)]
        delay, time = pages[1], pages[0]
        self.assertGreater(delay, self.values["Bald_InfoZoomDelay"])
        self.assertLess(delay, self.values["Bald_InfoZoomDelay"] + self.values["Bald_InfoZoomTime"])
        self.assertEqual((time, delay), (self.values["Bald_InfoInTime"], self.values["Bald_InfoInDelay"]))

    def test_the_approved_values(self):
        self.assertEqual(self.values, {"Bald_InfoZoomDelay": 40, "Bald_InfoZoomTime": 640, "Bald_InfoReturnDelay": 30,
                                       "Bald_InfoReturnTime": 540, "Bald_InfoInDelay": 260, "Bald_InfoInTime": 360,
                                       "Bald_InfoOutTime": 130, "Bald_InfoBackdropTime": 380,
                                       "Bald_InfoPageFadeTime": 460})


class InfoHandoffTests(unittest.TestCase):
    def effects(self, name):
        holder = ET.Element("holder")
        holder.extend(expand_call(name))
        return {(split(a.get("condition"))): a.findall("effect") for a in holder.iter("animation")}

    def test_home_masks_return_after_the_frame(self):
        frame = self.effects("Bald_AnimInfoFrame")
        back = frame[("full", "!$EXP[Bald_InfoOpen]")][0]
        end = int(back.get("delay")) + int(back.get("time"))
        masks = self.effects("Bald_AnimInfoMasks")[(None, "!$EXP[Bald_InfoOpen]")][0]
        self.assertGreaterEqual(int(masks.get("delay")), end)

    def test_a_poster_rows_nudge_moves_with_the_zoom(self):
        frame = self.effects("Bald_AnimInfoFrame")
        art = self.effects("Bald_AnimPosterArt")
        opening = frame[("full", "$EXP[Bald_InfoOpen]")][0]
        undo = art[("full", "$EXP[Bald_PosterRow] + $EXP[Bald_InfoOpen]")][0]
        self.assertEqual((undo.get("time"), undo.get("delay")), (opening.get("time"), opening.get("delay")))
        closing = frame[("full", "!$EXP[Bald_InfoOpen]")][0]
        nudge = art[("full", "$EXP[Bald_PosterRow] + !$EXP[Bald_InfoOpen] + !$EXP[Bald_IdleZoom]")][0]
        self.assertEqual((nudge.get("time"), nudge.get("delay")), (closing.get("time"), closing.get("delay")))


class ConstantNameTests(unittest.TestCase):
    def test_every_named_timing_is_a_constant(self):
        # Kodi resolves a constant in these attributes; an unknown name reaches it as a number it cannot read (0, no
        # animation). Include parameters that carry a timing count too.
        values = constants()
        timing_params = {"in", "in_delay", "out", "out_delay", "back", "back_delay", "time", "delay"}
        sources = [ET.parse(path).getroot() for path in NATIVE]
        for root in sources:
            for node in root.iter():
                names = [part for key, value in node.attrib.items() if key in CONSTANT_ATTRIBUTES
                         for part in value.split(",") if part.startswith("Bald_") and "$" not in part]
                if node.tag == "param" and node.get("name") in timing_params and (node.text or "").startswith("Bald_"):
                    names.append(node.text)
                for name in names:
                    with self.subTest(name=name):
                        self.assertIn(name, values)


if __name__ == "__main__":
    unittest.main()
