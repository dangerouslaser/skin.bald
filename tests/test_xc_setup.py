from pathlib import Path
import importlib.util
import unittest
import xml.etree.ElementTree as ET


MODULE = Path(__file__).resolve().parents[1] / "addons/script.bald.xcsetup/resources/lib/config.py"
SETUP = MODULE.parents[2] / "default.py"
SPEC = importlib.util.spec_from_file_location("bald_xc_config", MODULE)
config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(config)


class XCSetupTests(unittest.TestCase):
    def test_applying_credentials_enables_the_selected_pvr_instance(self):
        source = SETUP.read_text()
        self.assertIn(
            '_set(root, "kodi_addon_instance_enabled", "true")',
            source,
        )

    def test_kodi_settings_expose_only_the_guided_setup_action(self):
        root = ET.parse(MODULE.parents[1] / "settings.xml").getroot()
        for setting_id in ("launch", "server", "username", "password", "output"):
            setting = root.find(f".//setting[@id='{setting_id}']")
            self.assertIsNotNone(setting, setting_id)
            self.assertIsNotNone(setting.find("control"), setting_id)
        launch = root.find(".//setting[@id='launch']")
        self.assertEqual(launch.get("type"), "action")
        self.assertEqual(launch.get("label"), "32001")
        self.assertEqual(launch.findtext("data"), "RunScript(script.bald.xcsetup,wizard)")
        self.assertEqual(launch.findtext("control/close"), "true")
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


if __name__ == "__main__":
    unittest.main()
