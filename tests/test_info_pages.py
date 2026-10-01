"""Structural regressions for the native Kodi paged info dialog."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from conditions import equivalent, find_value, implies
from kodi_includes import expand_call, expand_follow, expressions, parse
from skin_strings import loc
from motion import full_motion


ROOT = Path(__file__).resolve().parents[1] / "1080i"


class InfoPagesTests(unittest.TestCase):
    def setUp(self):
        self.dialog = parse(ROOT / "DialogVideoInfo.xml")
        self.pages = parse(ROOT / "Includes_Bald_InfoPages.xml")
        self.shared = ET.parse(ROOT / "Includes_Bald_Info.xml").getroot()

    def test_detail_values_keep_to_two_lines(self):
        # A label does not stop at its height (seven writers ran into the row below): a text box shows the value and
        # keeps to the two lines that fit; the label, drawn clear, is what the "Not available" fallback reads.
        from kodi_includes import include_definitions
        detail = include_definitions()["Bald_Detail"].find("definition")
        value = detail.find("control[@id='$PARAM[id]']")
        self.assertEqual(value.findtext("textcolor"), "00FFFFFF")
        box = detail.find("control[@type='textbox']")
        self.assertEqual((box.findtext("height"), box.findtext("label"), box.findtext("font")),
                         ("56", "$PARAM[value]", "Bald_DetailValue"))

    def test_hint_pair_right_aligns_as_a_unit_with_32px_separator(self):
        # As the dialog calls it (two hints, default width): 384 wide, right-aligned, third hint hidden.
        pair, = expand_call("Bald_InfoHintPair", {"first": "a", "second": "b"})
        self.assertEqual(pair.get("type"), "grouplist")
        self.assertEqual(pair.findtext("align"), "right")
        self.assertEqual(pair.findtext("width"), "384")
        self.assertEqual(pair.findtext("itemgap"), "0")
        labels = pair.findall("control")
        self.assertEqual([node.findtext("visible") for node in labels[3:]], ["false", "false"])
        self.assertEqual(expand_call("Bald_InfoHintPair", {"width": "1024"})[0].findtext("width"), "1024")
        self.assertEqual([node.findtext("width") for node in labels], ["auto", "32", "auto", "32", "auto"])
        self.assertEqual(labels[1].findtext("label"), "·")
        self.assertTrue(all(node.findtext("height") == "24" for node in labels))
        overview = next(node for node in self.dialog.iter("control") if node.findtext("label") == "$VAR[Bald_KeyDown]" + loc("Cast & details"))
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
        # Home has its own masks, which also shape the frame for poster rows (test_home_row_styles).
        self.assertIn("Bald_HomeFrameMasks", [node.text for node in home_window.iter("include")])
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
        # Every item's title is its own (an episode's too).
        self.assertEqual([(value.get('condition'), value.text) for value in title.findall('value')], [(None, '$INFO[ListItem.Title]')])
        meta = find_value([(value.get('condition'), value.text)
                           for value in self.shared.findall("variable[@name='Bald_InfoMeta']/value")], episode)
        for field in ('ListItem.TVShowTitle', 'ListItem.Season', 'ListItem.Episode'):
            self.assertIn(field, meta)
        # An episode never reaches the movie Overview (it has the TV Overview), so that page has no episode branches.
        call = next(node for node in self.dialog.iter("include") if node.text == "Bald_InfoOverview")
        self.assertEqual(call.get("condition"), "!$EXP[Bald_InfoTVItem]")
        self.assertTrue(implies(episode, "$EXP[Bald_InfoTVItem]", expressions()))
        overview = ET.tostring(self.pages.find("include[@name='Bald_InfoOverview']"), encoding="unicode")
        self.assertNotIn("Bald_InfoTVIsEpisode", overview)
        poster = self.pages.find(".//control[@id='5204']")
        self.assertEqual(poster.findtext('aspectratio'), 'scale')

    def test_more_like_heading_uses_resolved_recommendation_subject(self):
        label = next(node for node in self.pages.findall("include[@name='Bald_InfoRecommendationsPage']//control[@type='label']") if 'Bald.MoreFor' in (node.findtext('label') or ''))
        self.assertEqual(label.findtext('label'), f"$INFO[Window(movieinformation).Property(Bald.MoreFor),{loc('For')} ,]")

    def test_three_independent_pages_without_section_slides(self):
        for name in ("Bald_InfoOverview", "Bald_InfoCastPage", "Bald_InfoRecommendationsPage"):
            self.assertIsNotNone(self.pages.find(f"include[@name='{name}']"))
            self.assertIn(name, [node.text for node in self.dialog.iter("include")])
        transition = full_motion(self.shared.find("include[@name='Bald_InfoPage']/definition"))
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
        # 288: the rating row, between the flags (275) and the accent line (300).
        self.assertEqual(delays, {"180", "275", "288", "300", "350"})
        art = self.shared.find("variable[@name='Bald_ItemFanart5100']")
        self.assertTrue(all("Container(5100).ListItem.Art" in node.text or node.text.endswith("5100]") for node in art))
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
        group = shared.find("definition/control[@type='group']")
        row = group.findtext("visible")
        # On Home the logo follows the current row; ignore_home_row="true" (used above) lifts that for the dialog.
        self.assertTrue(implies(row, "String.IsEqual(Window(home).Property(Bald.Row),$PARAM[c])",
                                assume={"$PARAM[ignore_home_row]": False, "$PARAM[preview]": False}))
        self.assertFalse(implies(row, "String.IsEqual(Window(home).Property(Bald.Row),$PARAM[c])",
                                 assume={"$PARAM[ignore_home_row]": True}))
        for image in group.findall("control[@type='image']"):
            self.assertTrue(implies(image.findtext("visible"), some_logo))

    def test_reuses_home_blur_and_clears_local_override(self):
        self.assertEqual([n.text for n in self.dialog.findall(".//control[@id='5200']/include")],
                         ["Bald_WindowBase", "Bald_BackdropImage"])
        unloads = [node.text for node in expand_follow(self.dialog) if node.tag == "onunload"]
        for name in ("Bald_InfoToOverview", "Bald_InfoBackToCast"):
            actions = [node.text for node in expand_follow(self.shared.find(f"include[@name='{name}']"))]
            for clear in ("ClearProperty(Bald.FocusContainer,movieinformation)",
                          "ClearProperty(TMDbHelper.WidgetContainer,movieinformation)"):
                self.assertIn(clear, unloads)
                self.assertIn(clear, actions)

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
