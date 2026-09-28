from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

SKIN = Path(__file__).resolve().parents[1] / "1080i"


class OSDClockTests(unittest.TestCase):
    def test_setting_row_toggles_the_clock(self):
        row = ET.parse(SKIN / "Custom_1119_BaldPlayback.xml").getroot().find(".//control[@id='9809']")
        self.assertEqual(row.get("type"), "radiobutton")
        self.assertEqual(row.findtext("label"), "$LOCALIZE[31416]")
        self.assertEqual(row.findtext("selected"), "!Skin.HasSetting(Bald.OSD.HideClock)")
        self.assertEqual(row.findtext("onclick"), "Skin.ToggleSetting(Bald.OSD.HideClock)")

    def test_hidden_clock_lifts_the_finish_time(self):
        root = ET.parse(SKIN / "Includes_Bald_Playback.xml").getroot()
        group = root.find("include[@name='Bald_PlaybackClock']/control")
        clock = group.find("control[@type='label']")
        self.assertEqual(clock.findtext("label"), "$VAR[Bald_Clock]")
        self.assertEqual(clock.findtext("visible"), "!Skin.HasSetting(Bald.OSD.HideClock)")
        line = group.find("control[@type='grouplist']")
        lift = line.find("animation")
        self.assertEqual((lift.text, lift.get("end"), lift.get("condition")),
                         ("Conditional", "0,-144", "Skin.HasSetting(Bald.OSD.HideClock)"))
        self.assertEqual(line.findtext("top"), "144")


if __name__ == "__main__":
    unittest.main()
