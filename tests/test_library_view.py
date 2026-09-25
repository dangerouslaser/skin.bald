"""Layout contracts for the native movie-library view."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1] / "1080i"


class LibraryViewTests(unittest.TestCase):
    def setUp(self):
        self.view = ET.parse(ROOT / "View_510_Bald_Posters.xml").getroot()

    def test_registered_native_movie_only_view_with_three_slots(self):
        nav = ET.parse(ROOT / "MyVideoNav.xml").getroot()
        self.assertIn("510", nav.findtext("views").split(","))
        self.assertIn("View_510_Bald_Posters", [n.text for n in nav.iter("include")])
        includes = ET.parse(ROOT / "Includes.xml").getroot()
        self.assertIn("View_510_Bald_Posters.xml", [n.get("file") for n in includes])
        control = self.view.find(".//control[@id='510']")
        self.assertEqual(control.findtext("visible"), "Container.Content(movies)")
        self.assertIsNone(control.find("content"))
        self.assertEqual(int(control.findtext("width")), 3 * int(control.find("itemlayout").get("width")))
        self.assertEqual(control.findtext("onup"), "9000")
        self.assertEqual(control.findtext("ondown"), "noop")

    def test_caption_reuses_home_media_flags_and_motion(self):
        caption = self.view.find("include[@name='Bald_LibraryCaption']//include")
        self.assertEqual(caption.get("content"), "Bald_Caption")
        self.assertEqual(caption.findtext("param[@name='c']"), "510")
        self.assertEqual(caption.findtext("param[@name='width']"), "528")
        shared = ET.parse(ROOT / "Includes_Bald_Home.xml").getroot()
        home_caption = shared.find("include[@name='Bald_Caption']")
        self.assertEqual(len(home_caption.findall(".//include[@content='Bald_Flag']")), 9)
        self.assertEqual(home_caption.findtext("param[@name='width']"), "384")
        self.assertEqual(home_caption.findtext("param[@name='x']"), "1420")

    def test_art_reuses_transition_with_four_overflow_masks(self):
        art = self.view.find("include[@name='Bald_LibraryArt']//include")
        self.assertEqual(art.get("content"), "Bald_ArtLayer")
        self.assertEqual(art.findtext("param[@name='width']"), "528")
        self.assertEqual(art.findtext("param[@name='height']"), "297")
        masks = self.view.findall(".//include[@content='Bald_BackdropWindow']")
        bounds = [tuple(int(n.findtext(f"param[@name='{key}']")) for key in ("x", "y", "w", "h")) for n in masks]
        self.assertEqual(bounds, [(1264, 198, 32, 345), (1824, 198, 32, 345), (1296, 198, 528, 24), (1296, 519, 528, 24)])

    def test_no_redundant_details_button(self):
        self.assertIsNone(self.view.find(".//control[@id='6101']"))
        home = ET.parse(ROOT / "Home.xml").getroot()
        self.assertIn("ActivateWindow(Videos,videodb://movies/titles/,return)", [n.text for n in home.iter("onclick")])

    def test_footer_reuses_detail_view_hint_spacing(self):
        hint = self.view.find(".//include[@content='Bald_InfoHintPair']")
        self.assertEqual(hint.findtext("param[@name='width']"), "824")
        self.assertEqual(hint.findtext("param[@name='third_visible']"), "true")

    def test_audio_codec_flag_maps_names_and_hides_missing_data(self):
        shared = ET.parse(ROOT / "Includes_Bald_Home.xml").getroot()
        caption = shared.find("include[@name='Bald_Caption']")
        codec = next(n for n in caption.findall(".//include[@content='Bald_Flag']") if "$MAP[" in n.findtext("param[@name='label']"))
        self.assertEqual(codec.findtext("param[@name='label']"), "$MAP[DefaultCodecMap, Container($PARAM[c]).ListItem.AudioCodec]")
        self.assertEqual(codec.findtext("param[@name='visible']"), "!String.IsEmpty(Container($PARAM[c]).ListItem.AudioCodec)")
        group = next(n for n in caption.iter("control") if codec in list(n))
        self.assertIn("!String.IsEmpty(Container($PARAM[c]).ListItem.AudioCodec)", group.findtext("visible"))
