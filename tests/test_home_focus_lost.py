"""Home never strands focus: Kodi cannot focus an empty list, so a Home screen whose rows are all empty (a new install
with no library) left nothing focused after Back from the menu. Timers.xml bald_focus_lost opens the menu on the
current screen's entry after a second with nothing focused."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

XML = Path(__file__).resolve().parents[1] / "1080i"


class FocusLostTests(unittest.TestCase):
    def test_the_timer_opens_the_menu_after_a_second_with_nothing_focused(self):
        timers = {t.findtext("name"): t for t in ET.parse(XML / "Timers.xml").getroot().iter("timer")}
        timer = timers["bald_focus_lost"]
        start = timer.findtext("start")
        for part in ("Window.IsActive(home)", "String.IsEmpty(System.CurrentControlID)",
                     "String.IsEmpty(Window(home).Property(Bald.Preload))", "!System.HasActiveModalDialog"):
            self.assertIn(part, start)
        self.assertIn("Integer.IsGreaterOrEqual(Skin.TimerElapsedSecs(bald_focus_lost),1)", timer.findtext("stop"))
        actions = [node.text for node in timer.findall("onstop")]
        self.assertEqual(actions, ["SetProperty(Bald.Menu,1,home)", "SetFocus($VAR[Bald_ScreenMenuEntry])"])
        for node in timer.findall("onstop"):
            self.assertIn("String.IsEmpty(System.CurrentControlID)", node.get("condition"))

    def test_every_screen_has_its_menu_entry(self):
        root = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        values = root.findall("variable[@name='Bald_ScreenMenuEntry']/value")
        entries = {v.text for v in values if v.get("condition")}
        self.assertEqual(entries, {"9001", "9004"} | {f"901{n}" for n in range(1, 9)})
        self.assertEqual(values[-1].text, "$VAR[Bald_StartMenuEntry]")


if __name__ == "__main__":
    unittest.main()
