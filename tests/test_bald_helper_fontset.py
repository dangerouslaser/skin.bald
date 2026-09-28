"""Bald Helper's fontset keeper (addons/script.bald.helper/resources/lib/fontset.py): once per Kodi start, under Bald
with Home up and nothing playing, Skin.String(Bald.Fontset) goes back into lookandfeel.font when the two differ; after
that, a fontset chosen elsewhere is copied into Bald.Fontset."""

import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from support import helper

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addons" / "script.bald.helper"
fontset = helper("fontset", "fontset")
keymap = helper("keymap", "fontset")


class FakeXbmc:
    LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR = 0, 1, 2, 4

    def __init__(self, font="Default", stored="", home=True, playing=False, skin="skin.bald"):
        self.font, self.stored, self.home, self.playing, self.skin = font, stored, home, playing, skin
        self.requests, self.builtins, self.logs = [], [], []

    def getSkinDir(self):
        return self.skin

    def getCondVisibility(self, condition):
        assert condition == "Window.IsVisible(home) + !Player.HasMedia", condition
        return self.home and not self.playing

    def getInfoLabel(self, label):
        return {"Skin.String(Bald.Fontset)": self.stored, "Skin.Font": self.font}[label]

    def executeJSONRPC(self, text):
        request = json.loads(text)
        self.requests.append((request["method"], request["params"]))
        if request["method"] == "Settings.GetSettingValue":
            assert request["params"] == {"setting": "lookandfeel.font"}
            return json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"value": self.font}})
        assert request["method"] == "Settings.SetSettingValue"
        assert request["params"]["setting"] == "lookandfeel.font"
        self.font = request["params"]["value"]
        return json.dumps({"jsonrpc": "2.0", "id": 1, "result": True})

    def executebuiltin(self, command):
        self.builtins.append(command)
        prefix = "Skin.SetString(Bald.Fontset,"
        if command.startswith(prefix):
            self.stored = command[len(prefix):-1]

    def log(self, message, level):
        self.logs.append((level, message))


def sets(xbmc):
    return [params["value"] for method, params in xbmc.requests if method == "Settings.SetSettingValue"]


class KeeperTests(unittest.TestCase):
    def test_a_lost_choice_is_put_back_once_home_is_up(self):
        for stored in ("InstrumentSans", "Arial"):
            with self.subTest(stored=stored):
                xbmc = FakeXbmc(font="Default", stored=stored)
                keeper = fontset.Keeper(xbmc)
                keeper.tick()
                self.assertEqual(sets(xbmc), [stored])
                self.assertEqual(xbmc.font, stored)
                self.assertTrue(any(stored in message for _, message in xbmc.logs))

    def test_the_same_choice_is_left_alone(self):
        xbmc = FakeXbmc(font="Arial", stored="Arial")
        fontset.Keeper(xbmc).tick()
        self.assertEqual(sets(xbmc), [])
        self.assertEqual(xbmc.builtins, [])

    def test_no_or_unknown_copy_changes_nothing(self):
        for stored in ("", "DMSans", "arial", "Default,InstrumentSans"):
            with self.subTest(stored=stored):
                xbmc = FakeXbmc(font="InstrumentSans", stored=stored)
                fontset.Keeper(xbmc).tick()
                self.assertEqual(sets(xbmc), [])

    def test_waits_for_home_and_for_playback_to_end(self):
        xbmc = FakeXbmc(font="Default", stored="Arial", home=False)
        keeper = fontset.Keeper(xbmc)
        keeper.tick()
        xbmc.home, xbmc.playing = True, True
        keeper.tick()
        self.assertEqual(xbmc.requests, [])
        self.assertEqual(xbmc.builtins, [])  # nor does it copy the reset fontset over the choice while it waits
        xbmc.playing = False
        keeper.tick()
        self.assertEqual(sets(xbmc), ["Arial"])

    def test_only_under_bald(self):
        xbmc = FakeXbmc(font="Default", stored="Arial", skin="skin.estuary")
        keeper = fontset.Keeper(xbmc)
        keeper.tick()
        self.assertEqual(xbmc.requests, [])
        xbmc.skin = "skin.bald"
        keeper.tick()
        self.assertEqual(sets(xbmc), ["Arial"])

    def test_restores_once_per_start_however_often_it_is_lost(self):
        xbmc = FakeXbmc(font="Default", stored="Arial")
        keeper = fontset.Keeper(xbmc)
        for _ in range(5):
            keeper.tick()
            xbmc.font = "Default"  # something keeps resetting it
            xbmc.stored = "Arial"
        self.assertEqual(sets(xbmc), ["Arial"])

    def test_an_error_does_not_make_it_try_again(self):
        xbmc = FakeXbmc(font="Default", stored="Arial")
        xbmc.executeJSONRPC = lambda text: json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"message": "no"}})
        keeper = fontset.Keeper(xbmc)
        with self.assertRaises(RuntimeError):
            keeper.tick()
        calls = []
        xbmc.executeJSONRPC = lambda text: calls.append(text)
        keeper.tick()
        self.assertEqual(calls, [])

    def test_after_the_check_a_fontset_chosen_elsewhere_becomes_the_choice(self):
        # Kodi's own Settings > Interface > Skin > Fonts; without this the next start would undo it.
        xbmc = FakeXbmc(font="InstrumentSans", stored="InstrumentSans")
        keeper = fontset.Keeper(xbmc)
        keeper.tick()
        xbmc.font = "Arial"
        keeper.tick()
        self.assertEqual(xbmc.builtins, ["Skin.SetString(Bald.Fontset,Arial)"])
        keeper.tick()  # in step: nothing more to save
        self.assertEqual(xbmc.builtins, ["Skin.SetString(Bald.Fontset,Arial)"])
        self.assertEqual(sets(xbmc), [])

    def test_a_first_start_without_a_copy_seeds_it_from_the_setting(self):
        xbmc = FakeXbmc(font="InstrumentSans", stored="")
        keeper = fontset.Keeper(xbmc)
        keeper.tick()
        keeper.tick()
        self.assertEqual(xbmc.builtins, ["Skin.SetString(Bald.Fontset,InstrumentSans)"])

    def test_a_fontset_bald_does_not_offer_is_not_copied(self):
        xbmc = FakeXbmc(font="DMSans", stored="Default")
        keeper = fontset.Keeper(xbmc)
        keeper.tick()
        keeper.tick()
        self.assertEqual(xbmc.builtins, [])

    def test_the_ids_are_font_xmls_and_the_skin_scripts(self):
        from scripts import info
        ids = [node.get("id") for node in ET.parse(ROOT / "1080i" / "Font.xml").getroot().findall("fontset")]
        self.assertEqual(list(fontset.FONTSETS), ids)
        self.assertEqual(fontset.FONTSETS, info.FONTSETS)
        self.assertEqual(fontset.SKIN_STRING, info.FONTSET_SKIN_STRING)


class ServiceTests(unittest.TestCase):
    def test_the_service_runs_the_keeper_in_its_loop(self):
        text = (ADDON / "service.py").read_text(encoding="utf-8")
        self.assertIn("from resources.lib.fontset import Keeper", text)
        self.assertIn("each=(actions.refresh, *fontset_steps)", text)
        self.assertIn("each=fontset_steps", text)

    def test_each_step_is_guarded_on_its_own(self):
        class Xbmc:
            LOGDEBUG, LOGINFO, LOGERROR = 0, 1, 4

            def __init__(self):
                self.logs = []

            def getSkinDir(self):
                return "skin.estuary"

            def executebuiltin(self, command):
                pass

            def log(self, message, level):
                self.logs.append((level, message))

        class Monitor:
            def __init__(self):
                self.left = 3

            def waitForAbort(self, timeout):
                self.left -= 1
                return self.left < 0

        runs = []

        def failing():
            raise RuntimeError("boom")

        xbmc = Xbmc()
        service = keymap.Service(xbmc, None, keymap_dir="/nonexistent/bald-test")
        service.run(Monitor(), wake=1.0, each=(failing, lambda: runs.append(1)))
        self.assertEqual(len(runs), 3)
        self.assertEqual([m for level, m in xbmc.logs if level == xbmc.LOGERROR], ["script.bald.helper: RuntimeError: boom"])


if __name__ == "__main__":
    unittest.main()
