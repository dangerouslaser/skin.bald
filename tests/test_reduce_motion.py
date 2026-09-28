"""Reduce motion (Appearance › Behavior, Bald.ReduceMotion): zooms and slides become plain fades. Every timed slide or
zoom in the skin sits in an animation gated on Bald_FullMotion; right after it comes its twin under Bald_ReduceMotion
with the fades alone (same timings), or, where the move holds a layout, the same move at time 0. Window changes reuse
the background-video fade (Bald_FadeOnly). Instant steps (time 0, such as the burn-in drift) are not motion."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from motion import FULL, REDUCE, split
from skin_strings import loc

XML = Path(__file__).resolve().parents[1] / "1080i"
MOVES = ("slide", "zoom")


def files():
    return [p for p in sorted(XML.glob("*.xml")) if "generator" not in p.name]


def effects(animation):
    """(type, attributes) per effect; an old-style animation (effect= on the tag) is its own single effect."""
    if animation.get("effect"):
        return [(animation.get("effect"), {k: v for k, v in animation.attrib.items() if k != "condition"})]
    return [(e.get("type"), dict(e.attrib)) for e in animation.findall("effect")]


def moves(animation):
    return [a for kind, a in effects(animation) if kind in MOVES and a.get("time", "0") != "0"]


def animations(root):
    for parent in root.iter():
        children = list(parent)
        for index, child in enumerate(children):
            if child.tag == "animation":
                yield child, children[index + 1] if index + 1 < len(children) else None


class ReduceMotionTests(unittest.TestCase):
    def test_every_timed_move_is_gated(self):
        for path in files():
            for animation, _ in animations(ET.parse(path).getroot()):
                if not moves(animation):
                    continue
                condition = animation.get("condition") or ""
                with self.subTest(file=path.name, condition=condition):
                    gated = split(condition)[0] == "full" or "!$EXP[Bald_FadeOnly]" in condition
                    self.assertTrue(gated, "a timed slide or zoom without the reduce-motion gate")

    def test_twins_follow_with_fades_or_an_instant_move(self):
        count = 0
        for path in files():
            for animation, following in animations(ET.parse(path).getroot()):
                state, base = split(animation.get("condition"))
                if state == "reduce":
                    with self.subTest(file=path.name, condition=animation.get("condition")):
                        self.assertEqual(moves(animation), [], "a reduce-motion twin that still moves")
                if state != "full":
                    continue
                fades = [(k, a) for k, a in effects(animation) if k == "fade"]
                twin_state = split(following.get("condition"))[0] if following is not None else None
                with self.subTest(file=path.name, condition=animation.get("condition")):
                    if twin_state != "reduce":
                        # No twin: a pure move (a focus pop, a nudge) that simply does not happen.
                        self.assertEqual(fades, [], "fades lost under reduce motion")
                        continue
                    count += 1
                    self.assertEqual(split(following.get("condition"))[1], base)
                    self.assertEqual(following.get("type"), animation.get("type"))
                    self.assertEqual(following.get("reversible"), animation.get("reversible"))
                    twin = effects(following)
                    instant = [(k, {**a, "time": "0"}) if k in MOVES else (k, a) for k, a in effects(animation)]
                    twin_fades = [(k, a) for k, a in twin if k == "fade"]
                    if twin == fades:
                        continue
                    # A layout move: the same effects with the move at time 0, and possibly a fade in added.
                    self.assertEqual([e for e in twin if e[0] in MOVES], [e for e in instant if e[0] in MOVES])
                    for fade in fades:
                        self.assertIn(fade, twin_fades)
        self.assertGreater(count, 40)

    def test_the_central_includes_are_covered(self):
        # The shared motion includes each carry both states.
        text = {p.name: p.read_text(encoding="utf-8") for p in files()}
        roots = {}
        for file, include in (("Includes_Animations.xml", "Animation_DialogPopupOpenClose"),
                              ("Includes_Bald_Home.xml", "Bald_AnimRowSwap"),
                              ("Includes_Bald_Home.xml", "Bald_AnimInfoFrame"),
                              ("Includes_Bald_Home.xml", "Bald_AnimPosterArt"),
                              ("Includes_Bald_Home.xml", "Bald_AnimCaptionIn"),
                              ("Includes_Bald_Info.xml", "Bald_InfoPage"),
                              ("Includes_Bald_Overlays.xml", None)):
            body = text[file]
            if include:
                roots.setdefault(file, ET.parse(XML / file).getroot())
                body = ET.tostring(roots[file].find(f"include[@name='{include}']"), encoding="unicode")
            with self.subTest(file=file, include=include):
                self.assertIn(FULL, body)
                self.assertIn(REDUCE, body)

    def test_window_changes_fade_without_their_move(self):
        common = ET.parse(XML / "Includes_Bald_Common.xml").getroot()
        self.assertEqual(common.findtext("expression[@name='Bald_FullMotion']"), "[!Skin.HasSetting(Bald.ReduceMotion)]")
        self.assertEqual(common.findtext("expression[@name='Bald_ReduceMotion']"), "[Skin.HasSetting(Bald.ReduceMotion)]")
        self.assertEqual(common.findtext("expression[@name='Bald_FadeOnly']"),
                         "[$EXP[Bald_VideoBackdropOn] | $EXP[Bald_ReduceMotion]]")
        depth = common.find("include[@name='Bald_AnimWindowDepth']/definition")
        fade_only = [a for a in depth.findall("animation") if not moves(a)]
        self.assertEqual(sorted(a.get("type") for a in fade_only), ["WindowClose", "WindowOpen"])
        for animation in fade_only:
            self.assertIn("$EXP[Bald_FadeOnly]", animation.get("condition"))

    def test_the_info_handoff_fades_in_at_its_new_size(self):
        frame = ET.parse(XML / "Includes_Bald_Home.xml").getroot().find("include[@name='Bald_AnimInfoFrame']")
        twins = [a for a in frame.findall("animation") if split(a.get("condition"))[0] == "reduce"]
        self.assertEqual(len(twins), 2)
        for twin in twins:
            kinds = {e.get("type"): e for e in twin.findall("effect")}
            self.assertEqual(kinds["zoom"].get("time"), "0")
            fade = kinds["fade"]
            self.assertEqual((fade.get("start"), fade.get("end"), fade.get("tween"), fade.get("easing")),
                             ("0", "100", "sine", "inout"))
            self.assertEqual(fade.get("delay"), kinds["zoom"].get("delay"))

    def test_the_setting_row(self):
        row = ET.parse(XML / "Custom_1118_BaldAppearance.xml").getroot().find(".//control[@id='9681']")
        self.assertEqual(row.get("type"), "radiobutton")
        self.assertEqual(row.findtext("label"), loc("Reduce motion"))
        self.assertEqual(row.findtext("selected"), "Skin.HasSetting(Bald.ReduceMotion)")
        self.assertEqual(row.findtext("onclick"), "Skin.ToggleSetting(Bald.ReduceMotion)")
        self.assertEqual(row.find("include/param[@name='item']").text, "3")  # Behavior
        self.assertRegex((XML / "IDs").read_text(encoding="utf-8"), r"(?m)^9681\tBehavior: reduce motion")
        german = (XML.parent / "language" / "resource.language.de_de" / "strings.po").read_text(encoding="utf-8")
        self.assertIn('msgctxt "#31371"\nmsgid "Reduce motion"\nmsgstr "Bewegung reduzieren"', german)


if __name__ == "__main__":
    unittest.main()
