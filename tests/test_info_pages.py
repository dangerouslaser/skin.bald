"""Structural regressions for the native Kodi paged info dialog."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1] / "1080i"


class InfoPagesTests(unittest.TestCase):
    def setUp(self):
        self.dialog = ET.parse(ROOT / "DialogVideoInfo.xml").getroot()
        self.pages = ET.parse(ROOT / "Includes_Bald_InfoPages.xml").getroot()
        self.shared = ET.parse(ROOT / "Includes_Bald_Info.xml").getroot()

    def test_native_playback_and_cast_contracts(self):
        for control_id in ("8", "9", "11"):
            self.assertIsNotNone(self.dialog.find(f".//control[@id='{control_id}']"))
        cast = self.pages.find(".//control[@id='50']")
        self.assertEqual(cast.get("type"), "list")
        self.assertEqual(int(cast.findtext("width")), 5 * int(cast.find("itemlayout").get("width")))

    def test_three_independent_pages_without_section_slides(self):
        for name in ("Bald_InfoOverview", "Bald_InfoCastPage", "Bald_InfoRecommendationsPage"):
            self.assertIsNotNone(self.pages.find(f"include[@name='{name}']"))
            self.assertIn(name, [node.text for node in self.dialog.iter("include")])
        transition = self.shared.find("include[@name='Bald_InfoPage']/definition")
        self.assertEqual(transition.find("visible").get("allowhiddenfocus"), "true")
        self.assertEqual([node.get("type") for node in transition.findall("animation")], ["Visible", "Hidden"])
        self.assertEqual(transition.find("animation/effect[@type='slide']").get("start"), "0,18")

    def test_preview_is_scoped_to_recommendation_container(self):
        for control_id, label in (("5210", "Title"), ("5212", "Plot")):
            self.assertEqual(self.pages.findtext(f".//control[@id='{control_id}']/label"), f"$INFO[Container(5100).ListItem.{label}]")
        art = self.shared.find("variable[@name='Bald_MorePreviewArt']")
        self.assertTrue(all("Container(5100).ListItem.Art" in node.text for node in art))
        self.assertEqual(self.pages.findtext(".//control[@id='5204']/texture"), "$VAR[Bald_InfoPoster]")

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
        condition = timer.findtext("start")
        for required in ("Control.HasFocus(5150)", "Window.IsActive(movieinformation)", "Integer.IsGreater(Container(5100).NumItems,0)"):
            self.assertIn(required, condition)
        self.assertNotIn("$EXP", condition)  # Not expanded by the skin timer loader.
        self.assertEqual(timer.findtext("onstart"), "SetFocus(5100)")


if __name__ == "__main__":
    unittest.main()
