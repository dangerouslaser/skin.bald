"""Background video (Playback › Background video): playing video shows, dimmed, behind Bald's windows."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from kodi_includes import include_definitions, resolve_window

ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
ON = "$EXP[Bald_VideoBackdropOn]"
FIELD = '<control type="image"><width>1920</width><height>1080</height><texture colordiffuse="bald_field">bald/white.png</texture></control>'


def includes(name):
    return ET.parse(XML / name).getroot()


class BackgroundVideoTests(unittest.TestCase):
    def setUp(self):
        self.common = includes("Includes_Bald_Common.xml")
        self.home = includes("Includes_Bald_Home.xml")

    def test_on_while_video_plays_unless_turned_off(self):
        body = self.common.find("expression[@name='Bald_VideoBackdropOn']").text
        self.assertEqual(body, "[Player.HasVideo + !Skin.HasSetting(Bald.OSD.NoBackgroundVideo)]")
        row = includes("Custom_1119_BaldPlayback.xml").find(".//control[@id='9807']")
        self.assertEqual(row.findtext("selected"), "!Skin.HasSetting(Bald.OSD.NoBackgroundVideo)")
        self.assertEqual(row.findtext("onclick"), "Skin.ToggleSetting(Bald.OSD.NoBackgroundVideo)")

    def test_the_video_is_dimmed_and_replaces_the_field(self):
        video = self.common.find("include[@name='Bald_VideoBackdrop']/control")
        self.assertEqual(video.findtext("visible"), ON)
        self.assertEqual([c.get("type") for c in video.findall("control")], ["videowindow"] + ["image"] * 4)
        # One dim per level; anything else (unset) is 80 %, so no value leaves the video undimmed.
        dims = {c.findtext("visible"): c.find("texture").get("colordiffuse") for c in video.findall("control[@type='image']")}
        levels = " + ".join(f"!Skin.String(Bald.OSD.BackgroundVideoDim,{n})" for n in (60, 70, 90))
        self.assertEqual(dims, {levels: "bald_video_dim",
                                "Skin.String(Bald.OSD.BackgroundVideoDim,60)": "bald_video_dim60",
                                "Skin.String(Bald.OSD.BackgroundVideoDim,70)": "bald_video_dim70",
                                "Skin.String(Bald.OSD.BackgroundVideoDim,90)": "bald_video_dim90"})
        field = self.common.find("include[@name='Bald_Field']/control")
        self.assertEqual(field.findtext("visible"), f"!{ON}")
        base = [n.text for n in self.common.findall("include[@name='Bald_WindowBase']/include")]
        self.assertEqual(base, ["Bald_Field", "Bald_VideoBackdrop"])

    def test_every_bald_window_shows_it(self):
        for name in ("Home.xml", "script-globalsearch.xml", "MyPVRGuide.xml", "Custom_1129_BaldCurtain.xml"):
            text = (XML / name).read_text(encoding="utf-8")
            with self.subTest(window=name):
                self.assertTrue("Bald_WindowBase" in text or "Bald_VideoBackdrop" in text)
        # The library windows draw it over DefaultBackground, whose own videowindow they leave out (one videowindow).
        for name in ("MyVideoNav.xml", "MyMusicNav.xml"):
            window = resolve_window(name)
            with self.subTest(window=name):
                shown = [c for c in window.iter("control") if c.get("type") == "videowindow"
                         and not any((v.text or "").startswith("false + ") for v in c.findall("visible"))]
                self.assertEqual(len(shown), 1)
                self.assertIn('<include content="DefaultBackground"><param name="video">false</param></include>\n\t\t<include>Bald_VideoBackdrop</include>',
                              (XML / name).read_text(encoding="utf-8"))
        # Estuary windows show the video under their field only while the setting is on.
        background = includes("Includes.xml").find("include[@name='DefaultBackground']")
        video = background.find("definition/control[@type='videowindow']")
        self.assertEqual([v.text for v in video.findall("visible")], [f"$PARAM[video] + {ON}", "!Slideshow.IsActive"])
        self.assertEqual(background.findtext("param[@name='video']"), "true")
        fanart = background.find(".//control[@id='31111']")
        self.assertIn(f"![{ON} |", fanart.findtext("visible"))
        # Library views and pages draw no opaque full-screen field over it.
        for path in sorted(XML.glob("View_5*.xml")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(view=path.name):
                self.assertNotIn(FIELD + "<include>Bald_BackdropImage</include>", text)

    def test_info_pages_show_it(self):
        # Cast and More like this: the dimmed video, not Home's zoomed sharp fanart, behind the page.
        page = includes("DialogVideoInfo.xml").find(".//control[@id='5200']")
        self.assertEqual([n.text for n in page.findall("include")], ["Bald_WindowBase", "Bald_BackdropImage"])

    def test_no_second_full_screen_dim_over_it(self):
        # A window that shows the video already dims it: a full-screen 60 % field layer on top must give way.
        definitions = include_definitions()
        checked = []
        for path in sorted(XML.glob("*.xml")):
            if path.name.startswith(("Includes", "View_", "script-skinvariables", "Font", "Constants", "Defaults")):
                continue
            window = resolve_window(path.name, definitions)
            # The info dialog's layers dim Home's art frame (the Overview), which shows over the video.
            if path.name == "DialogVideoInfo.xml":
                continue
            if window.tag != "window" or not any(t.get("colordiffuse") == "bald_video_dim" for t in window.iter("texture")):
                continue
            checked.append(path.name)
            parents = {child: parent for parent in window.iter() for child in parent}

            def full_screen(image, colour):
                texture = image.find("texture")
                return (image.get("type") == "image" and texture is not None and texture.get("colordiffuse") == colour
                        and (image.findtext("width"), image.findtext("height")) == ("1920", "1080"))

            for image in window.iter("control"):
                if not full_screen(image, "bald_field60"):
                    continue
                # Over an opaque field of its own (the library Series page's backdrop), it dims that, not the video.
                siblings = list(parents[image])
                if any(full_screen(s, "bald_field") and s.find("visible") is None for s in siblings[:siblings.index(image)]):
                    continue
                gates, node = [], image
                while node is not None:
                    gates += [v.text or "" for v in node.findall("visible")]
                    node = parents.get(node)
                # Conditional overlays (channel number entry) dim on purpose; a standing layer must give way.
                with self.subTest(window=path.name):
                    self.assertTrue(gates, "a full-screen 60 % field layer that stays over the video")
        self.assertTrue({"Home.xml", "script-globalsearch.xml", "MyVideoNav.xml", "MyPVRGuide.xml"} <= set(checked), checked)

    def test_the_blur_gives_way(self):
        for image in self.home.findall("include[@name='Bald_BackdropImage']/control"):
            self.assertIn(f"!{ON}", image.findtext("visible"))

    def test_frame_masks_are_not_drawn_but_overlay_panels_are(self):
        mask = self.home.find("include[@name='Bald_BackdropWindow']/definition/control")
        self.assertEqual(mask.findtext("visible"), f"!{ON} | $PARAM[panel]")
        for name in ("View_511_Bald_Wall.xml", "View_515_Bald_PosterLow.xml", "View_521_Bald_TV_Alternates.xml"):
            self.assertIn('<param name="panel">true</param>', (XML / name).read_text(encoding="utf-8"))

    def test_no_settle_zoom_over_video(self):
        layer = self.home.find("include[@name='Bald_ArtLayer']/definition/control")
        visible = {a.get("condition"): [e.get("type") for e in a] for a in layer.findall("animation[@type='Visible']")}
        self.assertEqual(visible, {f"!{ON}": ["fade", "zoom"], ON: ["fade"]})

    def test_poster_rows_get_a_576_frame(self):
        body = self.home.find("expression[@name='Bald_VideoPosterFrame']").text
        self.assertEqual(body, f"[{ON} + $EXP[Bald_PosterRow] + !$EXP[Bald_InfoOpen]]")
        frame = includes("Home.xml")
        group = next(g for g in frame.iter("control") if g.findtext("visible") == "$EXP[Bald_VideoPosterFrame]")
        self.assertEqual(group.findtext("top"), "63")
        heights = [p.text for p in group.iter("param") if p.get("name") == "height"]
        self.assertEqual(heights, ["576", "576", "576"])
        # Both dialog-art copies linger after a dialog closes; the 702 one gives way at once to the 576 frame.
        calls = [c for c in frame.iter("include") if c.get("content") == "Bald_DialogArt"]
        self.assertEqual([c.findtext("param[@name='cut']") for c in calls], [None, "$EXP[Bald_VideoPosterFrame]"])
        art = self.home.find("include[@name='Bald_DialogArt']/definition/control")
        hidden = {a.get("condition"): [(e.get("time"), e.get("delay")) for e in a] for a in art.findall("animation[@type='Hidden']")}
        self.assertEqual(hidden, {"![$PARAM[cut]]": [("250", "900")], "$PARAM[cut]": [("130", None)]})

    def test_back_from_the_menu_returns_to_the_video(self):
        button = self.home.find("include[@name='Bald_HomeMenuButton']/definition/control")
        first = button.find("onback")
        self.assertEqual((first.get("condition"), first.text), (ON, "Action(FullScreen)"))

    def test_window_changes_over_video_fade_without_sliding(self):
        depth = self.common.find("include[@name='Bald_AnimWindowDepth']/definition")
        for animation in depth.findall("animation"):
            kinds = [e.get("type") for e in animation]
            if "slide" in kinds:
                self.assertIn(f"!{ON}", animation.get("condition"))
            else:
                self.assertIn(ON, animation.get("condition"))
                self.assertEqual(kinds, ["fade"])
        self.assertEqual(sorted(a.get("type") for a in depth.findall("animation") if "slide" not in [e.get("type") for e in a]),
                         ["WindowClose", "WindowOpen"])
        # The curtain keeps its fades: cutting it in and out made the change flicker.
        curtain = includes("Custom_1129_BaldCurtain.xml")
        self.assertEqual([a.get("condition") for a in curtain.findall("animation")], [None, None])

    def test_strings(self):
        for language, text in (("en_gb", ""), ("de_de", "Hintergrundvideo")):
            po = (ROOT / "language" / f"resource.language.{language}" / "strings.po").read_text(encoding="utf-8")
            self.assertRegex(po, rf'msgctxt "#31997"\nmsgid "Background video"\nmsgstr "{text}"')


if __name__ == "__main__":
    unittest.main()


class IdleDriftTests(unittest.TestCase):
    """The idle burn-in drift steps every 3 minutes instead of pulsing (a pulsing slide redraws every frame)."""

    def test_no_pulsing_animation_in_bald_windows(self):
        for name in ("Home.xml", "MusicVisualisation.xml"):
            root = includes(name)
            self.assertFalse(any(a.get("pulse") == "true" for a in root.iter("animation")), name)

    def test_the_steps_are_instant_and_driven_by_a_looping_timer(self):
        drift = includes("Includes_Bald_Common.xml").find("include[@name='Bald_IdleDrift']/definition")
        effects = [a.find("effect") for a in drift.findall("animation")]
        self.assertEqual([e.get("time") for e in effects], ["0", "0", "0"])
        timer = next(t for t in includes("Timers.xml").iter("timer") if t.findtext("name") == "bald_drift")
        self.assertIn("System.IdleTime(60)", timer.findtext("start"))
        self.assertIn("Skin.TimerElapsedSecs(bald_drift),720", timer.findtext("stop"))
