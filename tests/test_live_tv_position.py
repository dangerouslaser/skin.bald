"""Live TV's place in the main menu (Home Screens > Live TV > Move up / Move down; Skin.String Bald.LiveTVAfter).

Bald.LiveTVAfter holds after how many hub slots Live TV comes ("0" to "7"; unset, after all eight). Home's menu includes
the entry once, at that place, through include conditions Kodi evaluates as the skin loads (Bald_HomeMenuLiveTVAt), so
it keeps its one id, 9004. Home Screens lists Live TV at the same place and moves it one step per Select."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import kodi_includes
from kodi_includes import Skin, resolve_window


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"


def menu_ids(after):
    kodi_includes.SKIN_STRINGS["Bald.LiveTVAfter"] = after
    try:
        home = Skin().window("Home.xml")
    finally:
        kodi_includes.SKIN_STRINGS.pop("Bald.LiveTVAfter", None)
    menu = next(node for node in home.iter("control") if node.get("id") == "9000")
    return [node.get("id") for node in menu.findall("control") if node.get("type") == "button"]


class LiveTVPositionTests(unittest.TestCase):
    HUBS = [f"901{n}" for n in range(1, 9)]
    TAIL = ["9005", "9006", "9007"]

    def test_unset_puts_live_tv_after_every_hub(self):
        self.assertEqual(menu_ids(""), ["9001"] + self.HUBS + ["9004"] + self.TAIL)

    def test_each_place_puts_live_tv_after_that_many_hub_slots(self):
        for after in range(8):
            with self.subTest(after=after):
                self.assertEqual(menu_ids(str(after)),
                                 ["9001"] + self.HUBS[:after] + ["9004"] + self.HUBS[after:] + self.TAIL)

    def screens(self):
        return resolve_window("Custom_1117_BaldHomeScreens.xml")

    def test_home_screens_lists_live_tv_where_the_menu_has_it(self):
        items = self.screens().findall(".//control[@id='9300']/content/item")
        kinds = [(item.get("id"), item.findtext("property[@name='kind']")) for item in items]
        # A Live TV copy before each hub, and the one after them.
        for n in range(8):
            at = kinds.index((f"1{n}", "hub"))
            self.assertEqual(kinds[at - 1], (f"2{n}", "livetv"))
            copy = items[at - 1]
            visible = copy.findtext("visible")
            self.assertIn(f"String.IsEqual(Skin.String(Bald.LiveTVAfter),{n})", visible)
            self.assertIn(f"Integer.IsGreater(Container(9390).NumItems,{n})", visible)
        self.assertEqual(kinds[-2], ("2", "livetv"))
        self.assertEqual(items[-2].findtext("visible"), "$EXP[Bald_LiveTVAtEnd]")

    def step(self, button_id, stored, hubs):
        """What one Select on a move button stores, given Bald.LiveTVAfter and the number of hubs. Every condition is
        evaluated before any action runs, and the last matching Skin action wins."""
        button = self.screens().find(f".//control[@id='{button_id}']")
        configure = ET.parse(XML / "Includes_Bald_Configure.xml").getroot()
        at_end = stored == "" or int(stored) >= hubs

        def holds(condition):
            for atom in re.split(r"\s*\+\s*", condition):
                negate = atom.startswith("!")
                atom = atom.lstrip("!")
                if atom == "$EXP[Bald_LiveTVAtEnd]":
                    value = at_end
                elif match := re.fullmatch(r"String\.IsEqual\(Skin\.String\(Bald\.LiveTVAfter\),(\d)\)", atom):
                    value = stored == match.group(1)
                elif match := re.fullmatch(r"Integer\.IsEqual\(Container\(9390\)\.NumItems,(\d)\)", atom):
                    value = hubs == int(match.group(1))
                elif match := re.fullmatch(r"Integer\.IsGreater\(Container\(9390\)\.NumItems,(\d)\)", atom):
                    value = hubs > int(match.group(1))
                else:
                    raise AssertionError(atom)
                if value == negate:
                    return False
            return True

        self.assertIsNotNone(configure.find("expression[@name='Bald_LiveTVAtEnd']"))
        result = stored
        for node in button.findall("onclick"):
            condition, action = node.get("condition"), node.text
            if not action.startswith("Skin.") or (condition and not holds(condition)):
                continue
            result = "" if action.startswith("Skin.Reset") else re.search(r",(\d)\)$", action).group(1)
        return result

    def test_move_up_and_down_step_one_place(self):
        for hubs in range(1, 9):
            places = [str(n) for n in range(hubs)] + [""]  # "" is after the last hub
            for index, stored in enumerate(places):
                with self.subTest(hubs=hubs, stored=stored):
                    if index > 0:
                        self.assertEqual(self.step("9410", stored, hubs), places[index - 1])
                    if index < len(places) - 1:
                        self.assertEqual(self.step("9411", stored, hubs), places[index + 1])

    def test_moving_rebuilds_home(self):
        for button_id in ("9410", "9411"):
            button = self.screens().find(f".//control[@id='{button_id}']")
            actions = [node.text for node in button.findall("onclick")]
            self.assertEqual(actions[0], "SetProperty(Bald.WidgetsDirty,1,home)")
            self.assertTrue(actions[-1].startswith("Control.Move(9300,"))


if __name__ == "__main__":
    unittest.main()
