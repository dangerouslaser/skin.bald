"""Bald Helper's look-and-feel keeper (addons/script.bald.helper/resources/lib/lookandfeel.py): once per Kodi start,
under Bald with Home up and nothing playing, Skin.String(Bald.Fontset) goes back into lookandfeel.font and
Skin.String(Bald.TextSize) into lookandfeel.skinzoom when they differ; after that, a value chosen elsewhere is copied
into the skin string."""

import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from support import helper

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addons" / "script.bald.helper"
lookandfeel = helper("lookandfeel", "lookandfeel")
keymap = helper("keymap", "lookandfeel")

FONT, ZOOM = "lookandfeel.font", "lookandfeel.skinzoom"


class FakeXbmc:
    LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR = 0, 1, 2, 4

    def __init__(self, font="Default", stored="", zoom=0, stored_size="", home=True, playing=False,
                 skin="skin.bald"):
        self.settings = {FONT: font, ZOOM: zoom}
        self.strings = {"Bald.Fontset": stored, "Bald.TextSize": stored_size}
        self.home, self.playing, self.skin = home, playing, skin
        self.requests, self.builtins, self.logs = [], [], []

    @property
    def font(self):
        return self.settings[FONT]

    @font.setter
    def font(self, value):
        self.settings[FONT] = value

    def getSkinDir(self):
        return self.skin

    def getCondVisibility(self, condition):
        assert condition == "Window.IsVisible(home) + !Player.HasMedia", condition
        return self.home and not self.playing

    def getInfoLabel(self, label):
        if label == "Skin.Font":
            return self.font
        assert label.startswith("Skin.String(") and label.endswith(")"), label
        return self.strings[label[len("Skin.String("):-1]]

    def executeJSONRPC(self, text):
        request = json.loads(text)
        method, params = request["method"], request["params"]
        self.requests.append((method, params))
        assert params["setting"] in self.settings, params
        if method == "Settings.GetSettingValue":
            return json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"value": self.settings[params["setting"]]}})
        assert method == "Settings.SetSettingValue", method
        # Kodi's JSON-RPC refuses a value of the wrong type (SettingsOperations.cpp).
        assert isinstance(params["value"], type(self.settings[params["setting"]])), params
        self.settings[params["setting"]] = params["value"]
        return json.dumps({"jsonrpc": "2.0", "id": 1, "result": True})

    def executebuiltin(self, command):
        self.builtins.append(command)
        assert command.startswith("Skin.SetString(") and command.endswith(")"), command
        name, value = command[len("Skin.SetString("):-1].split(",", 1)
        self.strings[name] = value

    def log(self, message, level):
        self.logs.append((level, message))


def sets(xbmc, setting=FONT):
    return [p["value"] for method, p in xbmc.requests if method == "Settings.SetSettingValue" and p["setting"] == setting]


class FontsetTests(unittest.TestCase):
    def test_a_lost_choice_is_put_back_once_home_is_up(self):
        for stored in ("InstrumentSans", "Arial"):
            with self.subTest(stored=stored):
                xbmc = FakeXbmc(font="Default", stored=stored)
                keeper = lookandfeel.Keeper(xbmc)
                keeper.tick()
                self.assertEqual(sets(xbmc), [stored])
                self.assertEqual(xbmc.font, stored)
                self.assertTrue(any(stored in message for _, message in xbmc.logs))

    def test_the_same_choice_is_left_alone(self):
        xbmc = FakeXbmc(font="Arial", stored="Arial", stored_size="0")
        lookandfeel.Keeper(xbmc).tick()
        self.assertEqual(sets(xbmc), [])
        self.assertEqual(xbmc.builtins, [])

    def test_no_or_unknown_copy_changes_nothing(self):
        for stored in ("", "DMSans", "arial", "Default,InstrumentSans"):
            with self.subTest(stored=stored):
                xbmc = FakeXbmc(font="InstrumentSans", stored=stored)
                lookandfeel.Keeper(xbmc).tick()
                self.assertEqual(sets(xbmc), [])

    def test_waits_for_home_and_for_playback_to_end(self):
        xbmc = FakeXbmc(font="Default", stored="Arial", home=False)
        keeper = lookandfeel.Keeper(xbmc)
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
        keeper = lookandfeel.Keeper(xbmc)
        keeper.tick()
        self.assertEqual(xbmc.requests, [])
        xbmc.skin = "skin.bald"
        keeper.tick()
        self.assertEqual(sets(xbmc), ["Arial"])

    def test_restores_once_per_start_however_often_it_is_lost(self):
        xbmc = FakeXbmc(font="Default", stored="Arial")
        keeper = lookandfeel.Keeper(xbmc)
        for _ in range(5):
            keeper.tick()
            xbmc.font = "Default"  # something keeps resetting it
            xbmc.strings["Bald.Fontset"] = "Arial"
        self.assertEqual(sets(xbmc), ["Arial"])

    def test_an_error_does_not_make_it_try_again(self):
        xbmc = FakeXbmc(font="Default", stored="Arial")
        xbmc.executeJSONRPC = lambda text: json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"message": "no"}})
        keeper = lookandfeel.Keeper(xbmc)
        with self.assertRaises(RuntimeError):
            keeper.tick()
        calls = []
        xbmc.executeJSONRPC = lambda text: calls.append(text) or json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})
        keeper.tick()
        self.assertEqual([json.loads(c)["method"] for c in calls], ["Settings.GetSettingValue"])  # the zoom follow

    def test_after_the_check_a_fontset_chosen_elsewhere_becomes_the_choice(self):
        # Kodi's own Settings > Interface > Skin > Fonts; without this the next start would undo it.
        xbmc = FakeXbmc(font="InstrumentSans", stored="InstrumentSans", stored_size="0")
        keeper = lookandfeel.Keeper(xbmc)
        keeper.tick()
        xbmc.font = "Arial"
        keeper.tick()
        self.assertEqual(xbmc.builtins, ["Skin.SetString(Bald.Fontset,Arial)"])
        keeper.tick()  # in step: nothing more to save
        self.assertEqual(xbmc.builtins, ["Skin.SetString(Bald.Fontset,Arial)"])
        self.assertEqual(sets(xbmc), [])

    def test_a_first_start_without_a_copy_seeds_it_from_the_setting(self):
        xbmc = FakeXbmc(font="InstrumentSans", stored="", stored_size="0")
        keeper = lookandfeel.Keeper(xbmc)
        keeper.tick()
        keeper.tick()
        self.assertEqual(xbmc.builtins, ["Skin.SetString(Bald.Fontset,InstrumentSans)"])

    def test_a_fontset_bald_does_not_offer_is_not_copied(self):
        xbmc = FakeXbmc(font="DMSans", stored="Default", stored_size="0")
        keeper = lookandfeel.Keeper(xbmc)
        keeper.tick()
        keeper.tick()
        self.assertEqual(xbmc.builtins, [])

    def test_the_ids_are_font_xmls_and_the_skin_scripts(self):
        from scripts import info
        ids = [node.get("id") for node in ET.parse(ROOT / "1080i" / "Font.xml").getroot().findall("fontset")]
        self.assertEqual(list(lookandfeel.Fontset.CHOICES), ids)
        self.assertEqual(lookandfeel.Fontset.CHOICES, info.FONTSETS)
        self.assertEqual(lookandfeel.Fontset.skin_string, info.FONTSET_SKIN_STRING)


class TextSizeTests(unittest.TestCase):
    def test_a_lost_size_is_put_back_as_a_number(self):
        for stored, zoom in (("4", 4), ("8", 8), ("0", 0), ("-6", -6), ("30", 30)):
            with self.subTest(stored=stored):
                xbmc = FakeXbmc(zoom=0 if zoom else 8, stored_size=stored)
                lookandfeel.Keeper(xbmc).tick()
                self.assertEqual(sets(xbmc, ZOOM), [zoom])
                self.assertEqual(xbmc.settings[ZOOM], zoom)
                self.assertTrue(any("text size" in message for _, message in xbmc.logs))

    def test_the_same_size_is_left_alone(self):
        xbmc = FakeXbmc(zoom=4, stored_size="4")
        lookandfeel.Keeper(xbmc).tick()
        self.assertEqual(sets(xbmc, ZOOM), [])

    def test_no_or_unknown_copy_changes_nothing(self):
        for stored in ("", "large", "4.5", "+4", "32", "-31", "٤", "4,8"):
            with self.subTest(stored=stored):
                xbmc = FakeXbmc(zoom=8, stored_size=stored)
                lookandfeel.Keeper(xbmc).tick()
                self.assertEqual(sets(xbmc, ZOOM), [])

    def test_font_and_size_are_both_put_back_in_one_check(self):
        xbmc = FakeXbmc(font="Default", stored="Arial", zoom=0, stored_size="8")
        keeper = lookandfeel.Keeper(xbmc)
        keeper.tick()
        keeper.tick()
        self.assertEqual((sets(xbmc), sets(xbmc, ZOOM)), (["Arial"], [8]))
        self.assertEqual(xbmc.builtins, [])  # both in step afterwards: nothing copied back

    def test_a_failing_fontset_does_not_keep_the_size_from_coming_back(self):
        xbmc = FakeXbmc(font="Default", stored="Arial", zoom=0, stored_size="4")
        answer = xbmc.executeJSONRPC

        def refuse_fonts(text):
            if json.loads(text)["params"]["setting"] == FONT:
                return json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"message": "no"}})
            return answer(text)

        xbmc.executeJSONRPC = refuse_fonts
        with self.assertRaises(RuntimeError):
            lookandfeel.Keeper(xbmc).tick()
        self.assertEqual(xbmc.settings[ZOOM], 4)

    def test_after_the_check_a_zoom_set_elsewhere_becomes_the_choice(self):
        # Kodi's own Settings > Interface > Skin > Zoom.
        xbmc = FakeXbmc(font="Default", stored="Default", zoom=4, stored_size="4")
        keeper = lookandfeel.Keeper(xbmc)
        keeper.tick()
        xbmc.settings[ZOOM] = 10
        keeper.tick()
        keeper.tick()
        self.assertEqual(xbmc.builtins, ["Skin.SetString(Bald.TextSize,10)"])
        self.assertEqual(sets(xbmc, ZOOM), [])

    def test_a_first_start_without_a_copy_seeds_it_from_the_setting(self):
        xbmc = FakeXbmc(font="Default", stored="Default", zoom=0, stored_size="")
        keeper = lookandfeel.Keeper(xbmc)
        keeper.tick()
        self.assertEqual(sets(xbmc, ZOOM), [])
        keeper.tick()
        self.assertEqual(xbmc.builtins, ["Skin.SetString(Bald.TextSize,0)"])

    def test_an_unreadable_zoom_is_not_copied(self):
        xbmc = FakeXbmc(font="Default", stored="Default", zoom=0, stored_size="8")
        keeper = lookandfeel.Keeper(xbmc)
        keeper.checked = True
        for answer in ({"error": {"message": "no"}}, {"result": {}}, {"result": {"value": "4"}},
                       {"result": {"value": True}}, "not json"):
            with self.subTest(answer=answer):
                xbmc.executeJSONRPC = lambda text, a=answer: a if isinstance(a, str) else json.dumps(
                    {"jsonrpc": "2.0", "id": 1, **a})
                keeper.tick()
                self.assertEqual(xbmc.builtins, [])

    def test_the_keeper_covers_what_the_skin_script_offers(self):
        from scripts import info
        size = lookandfeel.TextSize()
        self.assertEqual(size.skin_string, info.TEXT_SIZE_SKIN_STRING)
        self.assertEqual(size.setting, "lookandfeel.skinzoom")
        for zoom in info.TEXT_SIZES:
            self.assertEqual(size.value(str(zoom)), zoom)

    def test_the_range_is_kodis(self):
        # Kodi's system/settings/settings.xml: lookandfeel.skinzoom, minimum -30, maximum 30.
        size = lookandfeel.TextSize()
        self.assertEqual((size.LOWEST, size.HIGHEST), (-30, 30))


class ServiceTests(unittest.TestCase):
    def test_the_service_runs_the_keeper_in_its_loop(self):
        text = (ADDON / "service.py").read_text(encoding="utf-8")
        self.assertIn("from resources.lib.lookandfeel import Keeper", text)
        self.assertIn("each=(actions.refresh, *lookandfeel_steps)", text)
        self.assertIn("each=lookandfeel_steps", text)

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
