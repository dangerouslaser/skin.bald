"""Structural regressions for the native Kodi paged info dialog."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from conditions import equivalent, find_value, implies
from kodi_includes import parse
from skin_strings import loc


ROOT = Path(__file__).resolve().parents[1] / "1080i"


class InfoPagesTests(unittest.TestCase):
    def setUp(self):
        self.dialog = parse(ROOT / "DialogVideoInfo.xml")
        self.pages = parse(ROOT / "Includes_Bald_InfoPages.xml")
        self.shared = ET.parse(ROOT / "Includes_Bald_Info.xml").getroot()

    def test_hint_pair_right_aligns_as_a_unit_with_20px_separator(self):
        pair = self.shared.find("include[@name='Bald_InfoHintPair']/definition/control")
        self.assertEqual(pair.get("type"), "grouplist")
        self.assertEqual(pair.findtext("align"), "right")
        self.assertEqual(pair.findtext("width"), "$PARAM[width]")
        hint = self.shared.find("include[@name='Bald_InfoHintPair']")
        self.assertEqual(hint.findtext("param[@name='width']"), "384")
        self.assertEqual(hint.findtext("param[@name='third_visible']"), "false")
        self.assertEqual(pair.findtext("itemgap"), "0")
        labels = pair.findall("control")
        self.assertEqual([node.findtext("width") for node in labels], ["auto", "20", "auto", "20", "auto"])
        self.assertEqual(labels[1].findtext("label"), "·")
        self.assertTrue(all(node.findtext("height") == "24" for node in labels))
        overview = next(node for node in self.dialog.iter("control") if node.findtext("label") == loc("Down for cast & details"))
        self.assertEqual(overview.findtext("align"), "right")
        self.assertEqual(overview.findtext("height"), "24")
        self.assertEqual(overview.findtext("top"), "954")
        self.assertFalse(self.pages.findall(".//include[@content='Bald_InfoHintPair']"))
        self.assertEqual(len(self.dialog.findall(".//include[@content='Bald_InfoHintPair']")), 2)

    def test_recommendation_fanart_reuses_home_transition_and_masks(self):
        frame = self.pages.find(".//control[@id='5205']")
        self.assertEqual(frame.get("type"), "group")
        page = self.pages.find("include[@name='Bald_InfoRecommendationsPage']/control")
        self.assertIn("Bald_ArtFrameMasks", [node.text for node in page.findall("include")])
        self.assertEqual((frame.findtext("width"), frame.findtext("height")), ("1248", "702"))
        layers = frame.findall(".//include[@content='Bald_ArtLayer']")
        self.assertEqual(len(layers), 2)
        # One layer per parity of the focused recommendation, as Home's crossfade.
        for parity in ("Odd", "Even"):
            self.assertEqual(sum(equivalent(node.findtext("param[@name='visible']"),
                                            f"Integer.Is{parity}(Container(5100).CurrentItem)") for node in layers), 1)
        for node in layers:
            self.assertEqual(node.findtext("param[@name='texture']"), "$VAR[Bald_ItemFanart5100]")
        home = ET.parse(ROOT / "Includes_Bald_Home.xml").getroot()
        layer = home.find("include[@name='Bald_ArtLayer']")
        masks = home.findall("include[@name='Bald_ArtFrameMasks']/include")
        bounds = [tuple(int(node.findtext(f"param[@name='{key}']")) for key in ("x", "y", "w", "h")) for node in masks]
        self.assertEqual(bounds, [(0, 80, 96, 782), (1344, 80, 60, 782), (96, 80, 1248, 40), (96, 822, 1248, 30)])
        home_window = ET.parse(ROOT / "Home.xml").getroot()
        self.assertIn("Bald_ArtFrameMasks", [node.text for node in home_window.iter("include")])
        self.assertEqual(layer.findtext("param[@name='texture']"), "$VAR[Bald_Fanart]")
        zoom = layer.find(".//effect[@type='zoom']")
        self.assertEqual((zoom.get("start"), zoom.get("end"), zoom.get("time")), ("105", "100", "1500"))
        self.assertEqual(layer.find(".//animation[@type='Hidden']/effect").get("time"), "700")

    def test_native_playback_and_cast_contracts(self):
        for control_id in ("8", "9", "11"):
            self.assertIsNotNone(self.dialog.find(f".//control[@id='{control_id}']"))
        cast = self.pages.find(".//control[@id='50']")
        self.assertEqual(cast.get("type"), "list")
        self.assertEqual(int(cast.findtext("width")), 5 * int(cast.find("itemlayout").get("width")))

    def test_episode_overview_uses_episode_identity_and_cast_poster_crops(self):
        title = self.shared.find("variable[@name='Bald_InfoTitle']")
        episode = 'String.IsEqual(ListItem.DBType,episode)'
        values = [(value.get('condition'), value.text) for value in title.findall('value')]
        self.assertEqual(find_value(values, episode), '$INFO[ListItem.Title]')
        meta = find_value([(value.get('condition'), value.text)
                           for value in self.shared.findall("variable[@name='Bald_InfoMeta']/value")], episode)
        for field in ('ListItem.TVShowTitle', 'ListItem.Season', 'ListItem.Episode'):
            self.assertIn(field, meta)
        overview_title = next(node for node in self.pages.findall("include[@name='Bald_InfoOverview']//control[@type='label']") if node.findtext('label') == '$VAR[Bald_InfoTitle]')
        # An episode always shows its title as text (its show's clearlogo would name the show, not the episode).
        self.assertTrue(implies(episode, overview_title.findtext('visible')))
        poster = self.pages.find(".//control[@id='5204']")
        self.assertEqual(poster.findtext('aspectratio'), 'scale')

    def test_more_like_heading_uses_resolved_recommendation_subject(self):
        label = next(node for node in self.pages.findall("include[@name='Bald_InfoRecommendationsPage']//control[@type='label']") if 'Bald.MoreFor' in (node.findtext('label') or ''))
        self.assertEqual(label.findtext('label'), f"$INFO[Window(movieinformation).Property(Bald.MoreFor),{loc('For')} ,]")

    def test_three_independent_pages_without_section_slides(self):
        for name in ("Bald_InfoOverview", "Bald_InfoCastPage", "Bald_InfoRecommendationsPage"):
            self.assertIsNotNone(self.pages.find(f"include[@name='{name}']"))
            self.assertIn(name, [node.text for node in self.dialog.iter("include")])
        transition = self.shared.find("include[@name='Bald_InfoPage']/definition")
        self.assertEqual(transition.find("visible").get("allowhiddenfocus"), "true")
        self.assertEqual([node.get("type") for node in transition.findall("animation")], ["Visible", "Hidden"])
        self.assertEqual(transition.find("animation/effect[@type='slide']").get("start"), "0,18")

    def test_preview_is_scoped_to_recommendation_container(self):
        captions = self.pages.findall("include[@name='Bald_InfoRecommendationsPage']//include[@content='Bald_Caption']")
        self.assertEqual(len(captions), 2)
        self.assertEqual({node.findtext("param[@name='p']") for node in captions}, {"Odd", "Even"})
        for node in captions:
            self.assertEqual(node.findtext("param[@name='c']"), "5100")
            self.assertEqual(node.findtext("param[@name='ignore_home_row']"), "true")
        home = ET.parse(ROOT / "Includes_Bald_Home.xml").getroot()
        caption = home.find("include[@name='Bald_Caption']")
        self.assertEqual(caption.findtext("param[@name='ignore_home_row']"), "false")
        labels = [node.text for node in caption.iter("label")]
        for field in ("Title", "Plot", "Genre"):
            self.assertIn(f"$INFO[Container($PARAM[c]).ListItem.{field}]", labels)
        self.assertIsNotNone(caption.find(".//include[@content='Bald_MediaFlags']"))
        delays = {node.findtext("param[@name='delay']") for node in caption.findall(".//include[@content='Bald_AnimCaptionIn']")}
        self.assertEqual(delays, {"180", "275", "300", "350"})
        art = self.shared.find("variable[@name='Bald_ItemFanart5100']")
        self.assertTrue(all("Container(5100).ListItem.Art" in node.text for node in art))
        self.assertEqual(self.pages.findtext(".//control[@id='5204']/texture"), "$VAR[Bald_InfoPoster]")

    def test_recommendations_reuse_home_clearlogos_for_both_parities(self):
        logos = self.pages.findall("include[@name='Bald_InfoRecommendationsPage']//include[@content='Bald_ArtLogo']")
        self.assertEqual(len(logos), 2)
        self.assertEqual({node.findtext("param[@name='p']") for node in logos}, {"Odd", "Even"})
        for node in logos:
            self.assertEqual(node.findtext("param[@name='c']"), "5100")
            self.assertEqual(node.findtext("param[@name='ignore_home_row']"), "true")
        home = ET.parse(ROOT / "Includes_Bald_Home.xml").getroot()
        shared = home.find("include[@name='Bald_ArtLogo']")
        self.assertEqual(shared.findtext("param[@name='ignore_home_row']"), "false")
        some_logo = " | ".join(f"!String.IsEmpty({art})" for art in (
            "Container($PARAM[c]).ListItem.Art(clearlogo)", "Container($PARAM[c]).ListItem.Art(tvshow.clearlogo)",
            "Container.Art(tvshow.clearlogo)"))
        for image in shared.findall("definition/control"):
            visible = image.findtext("visible")
            # On Home the logo follows the current row; ignore_home_row="true" (used above) lifts that for the dialog.
            self.assertTrue(implies(visible, "String.IsEqual(Window(home).Property(Bald.Row),$PARAM[c])",
                                    assume={"$PARAM[ignore_home_row]": False, "$PARAM[preview]": False}))
            self.assertFalse(implies(visible, "String.IsEqual(Window(home).Property(Bald.Row),$PARAM[c])",
                                     assume={"$PARAM[ignore_home_row]": True}))
            self.assertTrue(implies(visible, some_logo))

    def test_reuses_home_blur_and_clears_local_override(self):
        self.assertEqual(self.dialog.findtext(".//control[@id='5200']/include"), "Bald_BackdropImage")
        self.assertIn("ClearProperty(TMDbHelper.WidgetContainer,movieinformation)", [node.text for node in self.dialog.findall("onunload")])
        for name in ("Bald_InfoToOverview", "Bald_InfoBackToCast"):
            self.assertIn("ClearProperty(TMDbHelper.WidgetContainer,movieinformation)", [node.text for node in self.shared.find(f"include[@name='{name}']")])

    def test_empty_state_has_return_route_and_guarded_readiness(self):
        fallback = self.pages.find(".//control[@id='5150']")
        self.assertEqual(fallback.findtext("include"), "Bald_InfoBackToCast")
        timers = ET.parse(ROOT / "Timers.xml").getroot()
        timer = next(node for node in timers if node.findtext("name") == "bald_info_recommendations_ready")
        start = timer.findtext("start")
        for required in ("Control.HasFocus(5150)", "Window.IsActive(movieinformation)", "Integer.IsGreater(Container(5100).NumItems,0)"):
            self.assertTrue(implies(start, required), required)
        self.assertNotIn("$EXP", start)  # Not expanded by the skin timer loader.
        self.assertEqual(timer.findtext("onstart"), "SetFocus(5100)")


if __name__ == "__main__":
    unittest.main()
