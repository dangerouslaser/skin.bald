"""Background video (Playback › Background video): playing video shows, dimmed, behind Bald's windows."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

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
        self.assertEqual([c.get("type") for c in video.findall("control")], ["videowindow", "image"])
        self.assertEqual(video.find("control[@type='image']/texture").get("colordiffuse"), "bald_video_dim")
        field = self.common.find("include[@name='Bald_Field']/control")
        self.assertEqual(field.findtext("visible"), f"!{ON}")
        base = [n.text for n in self.common.findall("include[@name='Bald_WindowBase']/include")]
        self.assertEqual(base, ["Bald_Field", "Bald_VideoBackdrop"])

    def test_every_bald_window_shows_it(self):
        for name in ("Home.xml", "script-globalsearch.xml", "MyPVRGuide.xml", "Custom_1129_BaldCurtain.xml"):
            text = (XML / name).read_text(encoding="utf-8")
            with self.subTest(window=name):
                self.assertTrue("Bald_WindowBase" in text or "Bald_VideoBackdrop" in text)
        for name in ("MyVideoNav.xml", "MyMusicNav.xml"):
            text = (XML / name).read_text(encoding="utf-8")
            self.assertIn("<include>DefaultBackground</include>\n\t\t<include>Bald_VideoBackdrop</include>", text)
        # Library views and pages draw no opaque full-screen field over it.
        for path in sorted(XML.glob("View_5*.xml")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(view=path.name):
                self.assertNotIn(FIELD + "<include>Bald_BackdropImage</include>", text)

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
        self.assertEqual(heights, ["576", "576"])

    def test_back_from_the_menu_returns_to_the_video(self):
        button = self.home.find("include[@name='Bald_HomeMenuButton']/definition/control")
        first = button.find("onback")
        self.assertEqual((first.get("condition"), first.text), (ON, "Action(FullScreen)"))

    def test_no_window_transitions_over_video(self):
        depth = self.common.find("include[@name='Bald_AnimWindowDepth']/definition")
        for animation in depth.findall("animation"):
            self.assertIn(f"!{ON}", animation.get("condition"))
        curtain = includes("Custom_1129_BaldCurtain.xml")
        for animation in curtain.findall("animation"):
            self.assertEqual(animation.get("condition"), f"!{ON}")

    def test_strings(self):
        for language, text in (("en_gb", ""), ("de_de", "Hintergrundvideo")):
            po = (ROOT / "language" / f"resource.language.{language}" / "strings.po").read_text(encoding="utf-8")
            self.assertRegex(po, rf'msgctxt "#31997"\nmsgid "Background video"\nmsgstr "{text}"')


if __name__ == "__main__":
    unittest.main()
