from pathlib import Path
import http.client
import sys
import tempfile
import types
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

from support import load_file, service


MODULE = Path(__file__).resolve().parents[1] / "addons/script.bald.xcsetup/resources/lib/config.py"
SETUP = MODULE.parents[2] / "default.py"
config = load_file("bald_xc_config", MODULE)


class XCSetupTests(unittest.TestCase):
    def test_applying_credentials_enables_the_selected_pvr_instance(self):
        source = SETUP.read_text()
        self.assertIn(
            '_set(root, "kodi_addon_instance_enabled", "true")',
            source,
        )

    def test_applying_credentials_turns_on_the_daily_reload(self):
        self.assertIn('_set(root, "m3uRefreshMode", REFRESH_ONCE_PER_DAY)', SETUP.read_text())

    def test_the_service_is_registered(self):
        root = ET.parse(SETUP.parent / "addon.xml").getroot()
        service = root.find("extension[@point='xbmc.service']")
        self.assertIsNotNone(service)
        self.assertEqual(service.get("library"), "service.py")

    def test_kodi_settings_expose_the_setup_and_refresh_actions(self):
        root = ET.parse(MODULE.parents[1] / "settings.xml").getroot()
        for setting_id in ("launch", "refresh", "server", "username", "password", "output"):
            setting = root.find(f".//setting[@id='{setting_id}']")
            self.assertIsNotNone(setting, setting_id)
            self.assertIsNotNone(setting.find("control"), setting_id)
        launch = root.find(".//setting[@id='launch']")
        self.assertEqual(launch.get("type"), "action")
        self.assertEqual(launch.get("label"), "32001")
        self.assertEqual(launch.findtext("data"), "RunScript(script.bald.xcsetup,wizard)")
        self.assertEqual(launch.findtext("control/close"), "true")
        refresh = root.find(".//setting[@id='refresh']")
        self.assertEqual(refresh.get("type"), "action")
        self.assertEqual(refresh.findtext("data"), "RunScript(script.bald.xcsetup,refresh)")
        for setting_id in ("server", "username", "password", "output"):
            setting = root.find(f".//setting[@id='{setting_id}']")
            self.assertEqual(setting.findtext("level"), "4")

    def test_builds_standard_playlist_and_epg_urls(self):
        playlist, epg = config.build_urls("https://iptv.example:8443/panel/", "a+b", "p&x")
        self.assertEqual(
            playlist,
            "https://iptv.example:8443/panel/get.php?username=a%2Bb&password=p%26x&type=m3u_plus&output=ts",
        )
        self.assertEqual(epg, "https://iptv.example:8443/panel/xmltv.php?username=a%2Bb&password=p%26x")

    def test_adds_http_when_scheme_is_omitted(self):
        playlist, _ = config.build_urls("iptv.example:8080", "user", "pass", "m3u8")
        self.assertTrue(playlist.startswith("http://iptv.example:8080/get.php?"))
        self.assertIn("output=m3u8", playlist)

    def test_rejects_invalid_or_incomplete_input(self):
        for args in (("", "u", "p"), ("ftp://example.test", "u", "p"), ("http://x/?bad=1", "u", "p"), ("http://x", "", "p")):
            with self.subTest(args=args), self.assertRaises(config.ConfigError):
                config.build_urls(*args)

    def test_redacts_both_credentials(self):
        redacted = config.redact_url("https://x/get.php?username=alice&password=secret&type=m3u_plus")
        self.assertNotIn("alice", redacted)
        self.assertNotIn("secret", redacted)
        self.assertIn("username=%2A%2A%2A", redacted)
        self.assertIn("password=%2A%2A%2A", redacted)

    def test_builds_local_m3u_from_xc_api_records(self):
        playlist = config.build_m3u(
            "https://iptv.example:8443/panel",
            "a+b",
            "p/x",
            "ts",
            [{"category_id": "7", "category_name": "News"}],
            [{"stream_id": 42, "name": "World News", "category_id": "7", "epg_channel_id": "news.example", "stream_icon": "https://img/icon.png", "direct_source": ""}],
        )
        self.assertTrue(playlist.startswith("#EXTM3U\n"))
        self.assertIn('tvg-id="news.example"', playlist)
        self.assertIn('group-title="News"', playlist)
        self.assertIn("https://iptv.example:8443/panel/live/a%2Bb/p%2Fx/42.ts", playlist)


class DownloadTests(unittest.TestCase):
    def test_a_cut_off_answer_is_a_config_error_not_a_traceback(self):
        addon = types.SimpleNamespace(getAddonInfo=lambda key: "script.bald.xcsetup")
        fakes = {"xbmc": types.SimpleNamespace(LOGINFO=1, log=lambda *a: None),
                 "xbmcaddon": types.SimpleNamespace(Addon=lambda *a: addon),
                 "xbmcgui": types.SimpleNamespace(), "xbmcvfs": types.SimpleNamespace()}
        with service(fakes, SETUP.parent, "default.py") as setup:
            refresh = sys.modules["resources.lib.refresh"]
            for error in (http.client.IncompleteRead(b"[{"), http.client.RemoteDisconnected("closed")):
                with self.subTest(error=type(error).__name__), \
                        mock.patch("urllib.request.urlopen", side_effect=error), \
                        self.assertRaises(setup.ConfigError):
                    refresh.xc_data("http://example.invalid", "user", "pass", "get_live_streams")


INSTANCE = """<settings version="2">
    <setting id="m3uPathType">0</setting>
    <setting id="m3uPath">{playlist}</setting>
    <setting id="m3uRefreshMode" default="true">0</setting>
    <setting id="m3uRefreshHour" default="true">4</setting>
</settings>
"""


class RefreshTests(unittest.TestCase):
    """The service keeps the local playlist current and IPTV Simple rereading it."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.profile = Path(self.temporary.name)
        (self.profile / "pvr.iptvsimple").mkdir()
        self.playlist = self.profile / "script.bald.xcsetup" / "live.m3u"
        self.restarts = []
        self.playing = False
        settings = {"server": "http://xc.example", "username": "u", "password": "p", "output": "ts"}
        addon = types.SimpleNamespace(getAddonInfo=lambda key: "script.bald.xcsetup",
                                      getSettingString=lambda key: settings.get(key, ""))
        prefix = "special://profile/addon_data/"
        self.fakes = {
            "xbmc": types.SimpleNamespace(
                LOGINFO=1, LOGWARNING=2, log=lambda *a: None, sleep=lambda ms: None,
                executeJSONRPC=lambda request: self.restarts.append(request) or '{"result": "OK"}',
                Player=lambda: types.SimpleNamespace(isPlaying=lambda: self.playing),
                getCondVisibility=lambda condition: False),
            "xbmcaddon": types.SimpleNamespace(Addon=lambda *a: addon),
            "xbmcvfs": types.SimpleNamespace(
                translatePath=lambda path: str(self.profile / path[len(prefix):])),
        }

    def tearDown(self):
        self.temporary.cleanup()

    def _instance(self, playlist=None):
        path = self.profile / "pvr.iptvsimple" / "instance-settings-1.xml"
        path.write_text(INSTANCE.format(playlist=playlist or self.playlist))
        return path

    def _fetch(self, names):
        def fetch(server, username, password, action):
            if action == "get_live_categories":
                return [{"category_id": "1", "category_name": "News"}]
            return [{"stream_id": index, "name": name, "category_id": "1"} for index, name in enumerate(names, 1)]
        return fetch

    def test_only_instances_reading_the_bald_playlist_are_managed(self):
        with service(self.fakes, SETUP.parent):
            refresh = sys.modules["resources.lib.refresh"]
            self._instance(playlist="/elsewhere/other.m3u")
            self.assertEqual(refresh.managed_instances(), [])
            path = self._instance()
            self.assertEqual(refresh.managed_instances(), [str(path)])

    def test_daily_refresh_is_turned_on_once(self):
        with service(self.fakes, SETUP.parent):
            refresh = sys.modules["resources.lib.refresh"]
            path = self._instance()
            self.assertTrue(refresh.ensure_daily_refresh(str(path)))
            node = ET.parse(path).getroot().find("setting[@id='m3uRefreshMode']")
            self.assertEqual(node.text, "2")
            self.assertNotIn("default", node.attrib)
            self.assertFalse(refresh.ensure_daily_refresh(str(path)))
            self.assertEqual(refresh.refresh_hour(str(path)), 4)

    def test_startup_rebuilds_and_restarts_only_when_something_changed(self):
        with service(self.fakes, SETUP.parent) as entry:
            refresh = sys.modules["resources.lib.refresh"]
            path = self._instance()
            monitor = types.SimpleNamespace(waitForAbort=lambda seconds: False)
            with mock.patch.object(refresh, "xc_data", self._fetch(["One", "Two"])):
                entry._startup(monitor, [str(path)])
                self.assertIn(",Two", self.playlist.read_text())
                self.assertEqual(len(self.restarts), 2)  # disable, enable
                self.restarts.clear()
                entry._startup(monitor, [str(path)])
                self.assertEqual(self.restarts, [])
            with mock.patch.object(refresh, "xc_data", self._fetch(["One", "Three"])):
                entry._startup(monitor, [str(path)])
                self.assertNotIn(",Two", self.playlist.read_text())
                self.assertEqual(len(self.restarts), 2)

    def test_restart_waits_for_playback_to_stop(self):
        with service(self.fakes, SETUP.parent) as entry:
            self.playing = True
            waits = []
            def wait(seconds):
                waits.append(seconds)
                self.playing = False
                return False
            entry._restart_when_idle(types.SimpleNamespace(waitForAbort=wait))
            self.assertEqual(len(waits), 1)
            self.assertEqual(len(self.restarts), 2)

    def test_a_failed_rebuild_keeps_the_last_playlist(self):
        with service(self.fakes, SETUP.parent) as entry:
            refresh = sys.modules["resources.lib.refresh"]
            self.playlist.parent.mkdir()
            self.playlist.write_text("#EXTM3U\nold\n")
            with mock.patch.object(refresh, "xc_data", side_effect=refresh.ConfigError("down")):
                self.assertFalse(entry._rebuild())
            self.assertEqual(self.playlist.read_text(), "#EXTM3U\nold\n")


if __name__ == "__main__":
    unittest.main()
