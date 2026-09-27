"""The curtain (Custom_1129_BaldCurtain.xml): a modeless dialog that covers changes between Bald's full windows."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

XML = Path(__file__).resolve().parents[1] / "1080i"
WINDOWS = ["Home.xml", "MyVideoNav.xml", "MyPVRGuide.xml", "Settings.xml", "SettingsCategory.xml", "SettingsProfile.xml",
           "SettingsSystemInfo.xml", "Custom_1115_BaldSettings.xml", "Custom_1116_BaldHomeWidgets.xml",
           "Custom_1117_BaldHomeScreens.xml", "Custom_1118_BaldAppearance.xml", "Custom_1119_BaldPlayback.xml"]


class CurtainTests(unittest.TestCase):
    def setUp(self):
        self.common = ET.parse(XML / "Includes_Bald_Common.xml").getroot()
        self.curtain = ET.parse(XML / "Custom_1129_BaldCurtain.xml").getroot()

    def test_curtain_is_a_modeless_dialog_shown_for_a_change_or_while_held(self):
        self.assertEqual((self.curtain.get("type"), self.curtain.get("id")), ("dialog", "1129"))
        self.assertEqual(self.curtain.findtext("visible"),
                         "$EXP[Bald_CurtainChange] | !String.IsEmpty(Window(home).Property(Bald.Curtain))")

    def test_curtain_always_lifts_within_two_seconds(self):
        loads = [n.text for n in self.curtain.findall("onload")]
        self.assertIn("AlarmClock(bald_curtain,ClearProperty(Bald.Curtain,home),00:02,silent)", loads)
        self.assertLess(loads.index("CancelAlarm(bald_curtain,true)"),
                        loads.index("AlarmClock(bald_curtain,ClearProperty(Bald.Curtain,home),00:02,silent)"))
        self.assertIn("CancelAlarm(bald_curtain,true)", [n.text for n in self.curtain.findall("onunload")])

    def test_every_curtain_window_hands_off(self):
        names = re.findall(r"Window\.IsActive\((\w+)\)", self.common.findtext("expression[@name='Bald_CurtainWindow']"))
        nexts = re.findall(r"Window\.Next\((\w+)\)", self.common.findtext("expression[@name='Bald_CurtainNext']"))
        self.assertEqual(names, nexts)
        for name in WINDOWS:
            with self.subTest(window=name):
                root = ET.parse(XML / name).getroot()
                self.assertIn("Bald_CurtainHandoff", [n.text for n in root.findall("include")])
        handoff = self.common.find("include[@name='Bald_CurtainHandoff']")
        self.assertEqual(handoff.findtext("onload"), "ClearProperty(Bald.Curtain,home)")
        self.assertEqual(handoff.find("onunload").get("condition"), "$EXP[Bald_CurtainNext]")

    def test_windows_skip_their_open_under_the_curtain(self):
        depth = self.common.find("include[@name='Bald_AnimWindowDepth']/definition")
        for anim in depth.findall("animation[@type='WindowOpen']"):
            self.assertIn("String.IsEmpty(Window(home).Property(Bald.Curtain))", anim.get("condition"))
        guide = ET.parse(XML / "MyPVRGuide.xml").getroot()
        for anim in guide.iter("animation"):
            if anim.text == "WindowOpen":
                self.assertEqual(anim.get("condition"), "String.IsEmpty(Window(home).Property(Bald.Curtain))")

    def test_windows_without_a_blur_show_the_last_one(self):
        home = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        blur = [(v.get("condition"), v.text) for v in home.find("variable[@name='Bald_BlurImage']")]
        self.assertEqual(blur[0], ("$EXP[Bald_BlurFallback]", "$INFO[Window(home).Property(Bald.LastBlur)]"))
        fallback = home.findtext("expression[@name='Bald_BlurFallback']")
        self.assertIn("!Window.IsActive(home) + !Window.IsActive(videos)", fallback)
        handoff = self.common.find("include[@name='Bald_CurtainHandoff']")
        self.assertIn("SetProperty(Bald.LastBlur,", " ".join(n.text for n in handoff.findall("onunload")))
