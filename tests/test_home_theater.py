"""The home theater: the LG TV, Denon and Sonos add-ons' pages (tools/home_theater.py), and the setup that shows them."""

import importlib.util
import re
import unittest
import xml.etree.ElementTree as ET

from kodi_includes import SKIN, resolve_window

ROOT = SKIN.parent
SPEC = importlib.util.spec_from_file_location("home_theater", ROOT / "tools" / "home_theater.py")
home_theater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(home_theater)

PAGES = {window_id: name for window_id, name, *_ in home_theater.PAGES}
SETUP = {1132: "Bald_SetupLG", 1133: "Bald_SetupDenon", 1134: "Bald_SetupSonos"}


class GeneratorTests(unittest.TestCase):
    def test_generated_files_are_current(self):
        for path, text in home_theater.outputs().items():
            with self.subTest(file=path.name):
                self.assertEqual(path.read_text(encoding="utf-8"), text, "run python3 tools/home_theater.py")


class PageTests(unittest.TestCase):
    def test_each_row_belongs_to_one_category(self):
        for window_id, name in PAGES.items():
            root = ET.parse(SKIN / name).getroot()
            self.assertEqual(root.get("id"), str(window_id))
            items = [item.get("id") for item in root.find(".//control[@id='9700']/content")]
            self.assertEqual(items, [str(i) for i in range(1, len(items) + 1)])
            ids = [node.get("id") for node in root.iter("control") if node.get("id")]
            self.assertEqual(sorted({i for i in ids if ids.count(i) > 1}), [], name)
            for row in root.find(".//control[@id='9800']"):
                if row.tag != "control":
                    continue
                with self.subTest(page=name, row=row.get("id")):
                    shown = re.findall(r"Container\(9700\)\.HasFocus\((\d+)\)", row.findtext("visible"))
                    self.assertEqual(len(shown), 1)
                    self.assertIn(shown[0], items)

    def test_rows_act_through_their_add_on(self):
        addons = {1132: "service.webostv", 1133: "service.denonavr", 1134: "service.sonos"}
        for window_id, name in PAGES.items():
            root = ET.parse(SKIN / name).getroot()
            for click in root.iter("onclick"):
                if click.text.startswith("SetFocus("):
                    continue
                with self.subTest(page=name, action=click.text):
                    target = re.match(r"(?:RunScript|Addon\.OpenSettings)\(([\w.]+)", click.text).group(1)
                    # The Denon and Sonos pages carry service.webostv's switch for the TV remote's volume buttons.
                    self.assertIn(target, {addons[window_id], "service.webostv"})

    def test_help_follows_the_focused_row(self):
        variables = {node.get("name"): node
                     for node in ET.parse(SKIN / "Includes_Bald_HomeTheater.xml").getroot().iter("variable")}
        for window_id, name, _title, categories, help_var, *_ in home_theater.PAGES:
            values = variables[help_var].findall("value")
            for value in values:
                with self.subTest(page=name, condition=value.get("condition")):
                    self.assertRegex(value.get("condition"), r"^Control\.HasFocus\(\d+\)$")
                    self.assertNotIn("Addon.Setting", value.text)

    def test_settings_hub_lists_each_page_for_its_device(self):
        hub = resolve_window("Settings.xml")
        items = {item.findtext("onclick"): item.findtext("visible") for item in hub.iter("item")}
        for window_id, expression in SETUP.items():
            with self.subTest(window=window_id):
                self.assertEqual(items[f"ActivateWindow({window_id})"], f"$EXP[{expression}]")

    def test_setup_keeps_the_names_service_webostv_reads(self):
        includes = (SKIN / "Includes_Bald_HomeTheater.xml").read_text()
        for setting in ("setup_tv_lg", "setup_receiver_denon", "setup_receiver_sonos"):
            self.assertIn(f"Skin.HasSetting({setting})", includes)
        playback = (SKIN / "Custom_1119_BaldPlayback.xml").read_text()
        for setting in ("setup_tv_lg", "setup_receiver_denon", "setup_receiver_sonos", "setup_chosen",
                        "setup_receiver_chosen"):
            self.assertIn(setting, playback)

    def test_settings_transitions_know_the_pages(self):
        configure = (SKIN / "Includes_Bald_Configure.xml").read_text()
        back_in = re.search(r'<expression name="Bald_SettingsBackIn">(.*?)</expression>', configure).group(1)
        for window_id in PAGES:
            self.assertIn(f"Window.Previous({window_id})", back_in)


if __name__ == "__main__":
    unittest.main()
