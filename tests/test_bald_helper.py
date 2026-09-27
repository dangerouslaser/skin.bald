"""Bald Helper (addons/script.bald.helper): Select on a TV show in the video library opens its info page, and the
retired PVR keymap is removed. The blurred backgrounds are tested in test_bald_helper_blur.py.

The helper's keymap maps Select in <videos> to Skin.TimerStart(bald_library_select); the skin timer runs Info on a
focused library TV show and Select otherwise; Appearance, Behavior holds the switch (docs/NOTES.md)."""

import importlib.util
import os
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from skin_strings import english

ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
ADDON = ROOT / "addons" / "script.bald.helper"
SPEC = importlib.util.spec_from_file_location("bald_helper_keymap", ADDON / "resources" / "lib" / "keymap.py")
keymap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(keymap)


class FakeXbmc:
    LOGDEBUG, LOGINFO, LOGERROR = 0, 1, 4

    def __init__(self, skin="skin.bald", setting=False):
        self.skin, self.setting = skin, setting
        self.builtins, self.logs = [], []
        self.fail = None

    def getSkinDir(self):
        if self.fail:
            raise self.fail
        return self.skin

    def getCondVisibility(self, condition):
        assert condition == "Skin.HasSetting(Bald.ShowsOpenInfo)", condition
        return self.setting

    def executebuiltin(self, command):
        self.builtins.append(command)

    def log(self, message, level):
        self.logs.append((level, message))


class FakeMonitor:
    def __init__(self, xbmc, steps):
        self.xbmc, self.steps = xbmc, list(steps)

    def waitForAbort(self, timeout):
        assert timeout <= 2, "reacts within about a second"
        if not self.steps:
            return True
        self.steps.pop(0)(self.xbmc)
        return False


def timer():
    timers = ET.parse(XML / "Timers.xml").getroot()
    matches = [node for node in timers.findall("timer") if node.findtext("name") == keymap.TIMER]
    assert len(matches) == 1
    return matches[0]


class KeymapTests(unittest.TestCase):
    def setUp(self):
        self.root = ET.fromstring(keymap.build_keymap())

    def test_only_the_video_library_section(self):
        self.assertEqual(self.root.tag, "keymap")
        self.assertEqual([child.tag for child in self.root], ["videos"])

    def test_every_default_select_key_starts_bald_timer(self):
        videos = self.root.find("videos")
        expected = {
            ("keyboard", "return"), ("keyboard", "enter"), ("keyboard", "ok"), ("keyboard", "select"),
            ("remote", "select"), ("gamepad", "A"), ("joystick", "a"),
        }
        found = {(device.tag, key.tag) for device in videos for key in device if key.get("holdtime") is None}
        self.assertEqual(found, expected)
        for device in videos:
            for key in device:
                if key.get("holdtime") is None:
                    self.assertEqual(key.text, "Skin.TimerStart(bald_library_select)", (device.tag, key.tag))

    def test_joystick_keeps_long_press_context_menu(self):
        joystick = self.root.find("videos/joystick")
        self.assertEqual(joystick.get("profile"), "game.controller.default")
        hold = joystick.find("a[@holdtime]")
        self.assertEqual((hold.get("holdtime"), hold.text), ("500", "ContextMenu"))

    def test_keys_match_kodi_default_select_bindings(self):
        # Kodi 22's system keymaps, where the machine has them (the Mac this skin is built on).
        system = Path("/Applications/Kodi.app/Contents/Resources/Kodi/system/keymaps")
        if not system.is_dir():
            self.skipTest("Kodi.app not installed")
        for name, device, keys in (("keyboard.xml", "keyboard", keymap.KEYBOARD_KEYS),
                                   ("remote.xml", "remote", keymap.REMOTE_KEYS),
                                   ("gamepad.xml", "gamepad", keymap.GAMEPAD_KEYS)):
            section = ET.parse(system / name).getroot().find(f"global/{device}")
            select = {node.tag for node in section if node.text == "Select" and not node.attrib}
            self.assertEqual(select, set(keys), name)
        joystick = ET.parse(system / "joystick.xml").getroot().find(
            "global/joystick[@profile='game.controller.default']")
        self.assertEqual({node.tag for node in joystick if node.text == "Select" and not node.attrib},
                         set(keymap.JOYSTICK_KEYS))
        holds = {(node.tag, node.get("holdtime"), node.text) for node in joystick if node.get("holdtime")}
        self.assertLessEqual(set(keymap.JOYSTICK_HOLDS), holds)


class ServiceDecisionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.keymaps = os.path.join(self.directory.name, "keymaps")

    def tearDown(self):
        self.directory.cleanup()

    def service(self, **kwargs):
        xbmc = FakeXbmc(**kwargs)
        return xbmc, keymap.Service(xbmc, None, keymap_dir=self.keymaps)

    def test_wanted_only_under_bald_with_the_setting(self):
        self.assertTrue(keymap.wanted("skin.bald", True))
        self.assertFalse(keymap.wanted("skin.bald", False))
        self.assertFalse(keymap.wanted("skin.estuary", True))
        self.assertFalse(keymap.wanted("", True))

    def test_installs_under_bald_with_the_setting_and_reloads(self):
        xbmc, service = self.service(setting=True)
        self.assertTrue(service.sync())
        self.assertEqual(Path(service.path).read_text(encoding="utf-8"), keymap.build_keymap())
        self.assertEqual(xbmc.builtins, ["Action(reloadkeymaps)"])
        self.assertTrue(any(level == xbmc.LOGINFO and "installed" in text for level, text in xbmc.logs))
        # Already in place: nothing to write or reload.
        self.assertFalse(service.sync())
        self.assertEqual(xbmc.builtins, ["Action(reloadkeymaps)"])

    def test_removes_when_the_setting_goes_off(self):
        xbmc, service = self.service(setting=True)
        service.sync()
        xbmc.setting = False
        self.assertTrue(service.sync())
        self.assertFalse(os.path.exists(service.path))
        self.assertEqual(xbmc.builtins, ["Action(reloadkeymaps)"] * 2)

    def test_removes_under_another_skin_without_reading_its_settings(self):
        xbmc, service = self.service(setting=True)
        service.sync()
        xbmc.skin = "skin.estuary"
        self.assertTrue(service.sync())  # FakeXbmc.getCondVisibility would still say on.
        self.assertFalse(os.path.exists(service.path))

    def test_nothing_to_do_without_the_setting(self):
        xbmc, service = self.service(setting=False)
        self.assertFalse(service.sync())
        self.assertEqual(xbmc.builtins, [])
        self.assertFalse(os.path.exists(service.path))

    def test_rewrites_a_stale_keymap(self):
        xbmc, service = self.service(setting=True)
        os.makedirs(self.keymaps)
        Path(service.path).write_text("<keymap/>", encoding="utf-8")
        self.assertTrue(service.sync())
        self.assertEqual(Path(service.path).read_text(encoding="utf-8"), keymap.build_keymap())

    def test_run_follows_changes_and_removes_on_shutdown(self):
        xbmc, service = self.service(setting=True)

        def switch_skin(fake):
            self.assertTrue(os.path.exists(service.path))
            fake.skin = "skin.estuary"

        def back_to_bald(fake):
            self.assertFalse(os.path.exists(service.path))
            fake.skin = "skin.bald"

        service.run(FakeMonitor(xbmc, [switch_skin, back_to_bald]))
        # Back under Bald for the last poll, then abort: the shutdown removes the keymap.
        self.assertFalse(os.path.exists(service.path))
        self.assertEqual(xbmc.builtins.count("Action(reloadkeymaps)"), 4)

    def test_removes_the_retired_pvr_keymap_once(self):
        xbmc, service = self.service(setting=False)
        os.makedirs(self.keymaps)
        retired = Path(self.keymaps, "bald-pvr.xml")
        retired.write_text("<keymap/>", encoding="utf-8")
        other = Path(self.keymaps, "mine.xml")
        other.write_text("<keymap/>", encoding="utf-8")
        self.assertTrue(service.remove_retired())
        self.assertFalse(retired.exists())
        self.assertTrue(other.exists())
        self.assertEqual(xbmc.builtins, ["Action(reloadkeymaps)"])
        # Gone: nothing to do, no reload.
        self.assertFalse(service.remove_retired())
        self.assertEqual(xbmc.builtins, ["Action(reloadkeymaps)"])

    def test_run_removes_the_retired_pvr_keymap_at_start(self):
        xbmc, service = self.service(setting=False)
        os.makedirs(self.keymaps)
        Path(self.keymaps, "bald-pvr.xml").write_text("<keymap/>", encoding="utf-8")
        service.run(FakeMonitor(xbmc, []))
        self.assertFalse(Path(self.keymaps, "bald-pvr.xml").exists())

    def test_errors_do_not_stop_the_service_and_are_logged_once(self):
        xbmc, service = self.service(setting=True)
        xbmc.fail = RuntimeError("boom")

        def recover(fake):
            fake.fail = None

        service.run(FakeMonitor(xbmc, [lambda fake: None, lambda fake: None, recover]))
        errors = [text for level, text in xbmc.logs if level == xbmc.LOGERROR]
        self.assertEqual(errors, ["script.bald.helper: RuntimeError: boom"])
        self.assertFalse(os.path.exists(service.path))


class AddonTests(unittest.TestCase):
    def test_addon_xml(self):
        root = ET.parse(ADDON / "addon.xml").getroot()
        self.assertEqual((root.get("id"), root.get("name"), root.get("version")),
                         ("script.bald.helper", "Bald Helper", "1.4.1"))
        self.assertEqual(root.find("extension[@point='xbmc.service']").get("library"), "service.py")
        self.assertTrue((ADDON / "service.py").is_file())
        metadata = root.find("extension[@point='xbmc.addon.metadata']")
        skin_licence = ET.parse(ROOT / "addon.xml").getroot().findtext(
            "extension[@point='xbmc.addon.metadata']/license")
        self.assertEqual(metadata.findtext("license"), skin_licence)
        icon = metadata.findtext("assets/icon")
        self.assertTrue((ADDON / icon).is_file())

    def test_requires_kodis_pillow(self):
        # The blurred backgrounds need Pillow: script.module.pil at the version Kodi 22 bundles.
        root = ET.parse(ADDON / "addon.xml").getroot()
        pil = root.find("requires/import[@addon='script.module.pil']")
        self.assertIsNotNone(pil)
        self.assertIsNone(pil.get("optional"))
        bundled = Path("/Applications/Kodi.app/Contents/Resources/Kodi/addons/script.module.pil/addon.xml")
        if bundled.is_file():
            self.assertEqual(pil.get("version"), ET.parse(bundled).getroot().get("version"))

    def test_the_repository_publishes_it(self):
        path = ROOT / "packaging" / "repository.bald" / "build_repository.py"
        spec = importlib.util.spec_from_file_location("bald_build_repository", path)
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        self.assertIn("addons/script.bald.helper", build.BUNDLED_ADDONS)
        checks = (ROOT / "packaging" / "repository.bald" / "test_repository.py").read_text()
        self.assertIn('"script.bald.helper/service.py" in names', checks)

    def test_skin_requires_the_helper_at_its_version(self):
        # Bald Helper is required (installed with the skin from the Bald repository) and takes precedence over TMDb
        # Helper; the skin needs at least the helper version it ships with.
        skin = ET.parse(ROOT / "addon.xml").getroot()
        imported = skin.find("requires/import[@addon='script.bald.helper']")
        self.assertIsNotNone(imported)
        self.assertIsNone(imported.get("optional"))
        helper = ET.parse(ADDON / "addon.xml").getroot()
        self.assertEqual(imported.get("version"), helper.get("version"))


class TimerTests(unittest.TestCase):
    def setUp(self):
        self.actions = [(node.get("condition"), node.text) for node in timer().findall("onstart")]

    def test_info_on_a_focused_library_tv_show_select_otherwise(self):
        self.assertEqual([action for _, action in self.actions], ["Action(Info)", "Action(Select)"])
        info, select = (condition for condition, _ in self.actions)
        self.assertEqual(select, f"![{info}]")
        for term in ("Skin.HasSetting(Bald.ShowsOpenInfo)", "Window.IsActive(videos)",
                     "String.IsEqual(ListItem.DBType,tvshow)", "Integer.IsGreater(ListItem.DBID,0)",
                     "!ListItem.IsParentFolder"):
            self.assertIn(term, info)

    def test_focus_condition_is_exactly_the_library_views(self):
        info = self.actions[0][0]
        focused = re.findall(r"Control\.HasFocus\((\d+)\)", info)
        views = ET.parse(XML / "MyVideoNav.xml").getroot().findtext("views").split(",")
        self.assertEqual(sorted(focused), sorted(views))
        # Not the options list, the letter strip or any other control.
        for other in ("9150", "9160", "9000", "5302"):
            self.assertNotIn(other, focused)

    def test_only_the_keymap_starts_it(self):
        node = timer()
        self.assertIsNone(node.find("start"))
        self.assertEqual(node.findtext("stop"), "true")


class SettingRowTests(unittest.TestCase):
    def setUp(self):
        self.root = ET.parse(XML / "Custom_1118_BaldAppearance.xml").getroot()

    def row(self, control_id):
        row = self.root.find(f".//control[@id='{control_id}']")
        self.assertIsNotNone(row)
        # Behavior is category item 3.
        self.assertEqual(row.find("include[@content='Bald_SettingRow']/param[@name='item']").text, "3")
        return row

    def test_switch_while_the_helper_is_enabled(self):
        row = self.row("9627")
        self.assertEqual(row.get("type"), "radiobutton")
        self.assertEqual(english(row.findtext("label")), "Open TV shows on their info page")
        self.assertEqual(row.findtext("selected"), "Skin.HasSetting(Bald.ShowsOpenInfo)")
        self.assertEqual(row.findtext("onclick"), "Skin.ToggleSetting(Bald.ShowsOpenInfo)")
        self.assertEqual(row.findtext("visible"), "System.AddonIsEnabled(script.bald.helper)")

    def test_install_or_enable_otherwise_with_a_note(self):
        row = self.row("9628")
        self.assertEqual(row.findtext("label"), self.row("9627").findtext("label"))
        self.assertEqual(row.findtext("visible"), "!System.AddonIsEnabled(script.bald.helper)")
        actions = {node.get("condition"): node.text for node in row.findall("onclick")}
        self.assertEqual(actions, {
            "!System.HasAddon(script.bald.helper)": "InstallAddon(script.bald.helper)",
            "System.HasAddon(script.bald.helper)": "EnableAddon(script.bald.helper)",
        })
        self.assertEqual(row.findtext("label2"), "$VAR[Bald_HelperNote]")
        note = ET.parse(XML / "Includes_Bald_Configure.xml").getroot().find("variable[@name='Bald_HelperNote']")
        values = [(value.get("condition"), english(value.text)) for value in note.findall("value")]
        self.assertEqual(values, [("!System.HasAddon(script.bald.helper)", "Needs the Bald Helper add-on"),
                                  (None, "Bald Helper is disabled")])


if __name__ == "__main__":
    unittest.main()
