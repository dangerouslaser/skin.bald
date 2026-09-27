"""Bald Helper's skin actions (addons/script.bald.helper/resources/lib/actions.py): the skin's NotifyAll requests,
their parsing, latest-wins dispatch, the letter cache and the ready property, with xbmc replaced by stand-ins.
The skin's call sites are checked in test_bald_helper_actions_skin.py."""

import importlib.util
import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addons" / "script.bald.helper"
SPEC = importlib.util.spec_from_file_location("bald_helper_actions", ADDON / "resources" / "lib" / "actions.py")
actions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(actions)
KEYMAP_SPEC = importlib.util.spec_from_file_location("bald_helper_keymap_run", ADDON / "resources" / "lib" / "keymap.py")
keymap = importlib.util.module_from_spec(KEYMAP_SPEC)
KEYMAP_SPEC.loader.exec_module(keymap)

Request = actions.Request


class FakeWindow:
    def __init__(self):
        self.properties = {}

    def getProperty(self, key):
        return self.properties.get(key, "")

    def setProperty(self, key, value):
        self.properties[key] = value

    def clearProperty(self, key):
        self.properties.pop(key, None)


class FakeXbmc:
    LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR = 0, 1, 2, 4

    def __init__(self):
        self.logs = []

    def log(self, message, level):
        self.logs.append((level, message))


class FakeScripts:
    """Stands in for the skin's info.py and letters.py; records what the dispatcher calls."""

    def __init__(self):
        self.calls = []
        self.info = types.SimpleNamespace(handle=self.handle, SERVICE_API=1)
        self.letters = types.SimpleNamespace(publish=self.publish)
        self.hook = None
        self.fail = None

    def load(self):
        if self.fail:
            raise self.fail
        return self.info, self.letters

    def handle(self, xbmc, xbmcgui, action, media_type, dbid, cancelled, show):
        self.calls.append((action, media_type, dbid))
        if self.hook:
            self.hook(action, cancelled, show)

    def publish(self, xbmc, xbmcgui, container, cache, cancelled):
        self.calls.append(("letters", container, cache))


class ParseTests(unittest.TestCase):
    def test_requests(self):
        cases = {
            "Other.bald.info|episode|22": Request("info", "episode", "22"),
            "Other.bald.info|movie|": Request("info", "movie", ""),  # an add-on item: art only
            "Other.bald.info||": Request("info", "", ""),
            "Other.bald.play|episode|7": Request("play", "episode", "7"),
            "Other.bald.open|tvshow|3": Request("open", "tvshow", "3"),
            "Other.bald.seriesmeta": Request("seriesmeta", "", ""),
            "Other.bald.letters|521": Request("letters", "521", ""),
        }
        for method, request in cases.items():
            with self.subTest(method=method):
                self.assertEqual(actions.parse("skin.bald", method), request)

    def test_rejects_other_senders_unknown_actions_and_unsafe_values(self):
        for sender, method in (
            ("xbmc", "Other.bald.info|movie|1"),
            ("skin.other", "Other.bald.info|movie|1"),
            ("skin.bald", "bald.info|movie|1"),                 # not an Other notification
            ("skin.bald", "Other.info|movie|1"),                # not Bald's namespace
            ("skin.bald", "Other.bald.mouse"),                  # stays RunScript
            ("skin.bald", "Other.bald.font|Default"),
            ("skin.bald", "Other.bald.info|movie|1|x"),
            ("skin.bald", "Other.bald.info|Movie|1"),
            ("skin.bald", "Other.bald.info|movie|-1"),
            ("skin.bald", "Other.bald.info|movie|1)"),
            ("skin.bald", "Other.bald.play|movie|1"),
            ("skin.bald", "Other.bald.play|episode|"),
            ("skin.bald", "Other.bald.open|movie|"),
            ("skin.bald", "Other.bald.open||4"),
            ("skin.bald", "Other.bald.seriesmeta|x"),
            ("skin.bald", "Other.bald.letters|9160"),
            ("skin.bald", "Other.bald.letters|499"),
            ("skin.bald", "Other.bald.letters|"),
            ("skin.bald", "Other.bald.letters|510|1"),
            ("skin.bald", "Other.bald.info|/storage/movies/a.mkv|1"),
        ):
            with self.subTest(sender=sender, method=method):
                self.assertIsNone(actions.parse(sender, method))


class Case(unittest.TestCase):
    def setUp(self):
        self.xbmc = FakeXbmc()
        self.gui = Mock()
        self.window = FakeWindow()
        self.scripts = FakeScripts()
        self.dispatcher = actions.Dispatcher(self.xbmc, self.gui, self.scripts, window=self.window, threaded=False)


class DispatchTests(Case):
    def test_each_action_reaches_the_skins_code(self):
        self.dispatcher.notify("skin.bald", "Other.bald.info|episode|22", "null")
        self.dispatcher.notify("skin.bald", "Other.bald.letters|510", "null")
        self.assertEqual(self.scripts.calls[0], ("info", "episode", "22"))
        self.assertEqual(self.scripts.calls[1][:2], ("letters", "510"))
        self.assertIs(self.scripts.calls[1][2], self.dispatcher.letters)
        self.assertTrue(self.window.getProperty(actions.PROPERTY_LAST).startswith("letters|510||"))

    def test_other_notifications_do_nothing(self):
        self.dispatcher.notify("xbmc", "Player.OnPlay", "{}")
        self.dispatcher.notify("skin.bald", "Other.bald.mouse", "null")
        self.assertEqual(self.scripts.calls, [])
        warnings = [text for level, text in self.xbmc.logs if level == self.xbmc.LOGWARNING]
        self.assertEqual(len(warnings), 1)  # Bald's namespace with a bad request is worth a line

    def test_a_request_replaced_before_it_starts_never_runs(self):
        self.dispatcher.threaded = True  # queue without running
        self.dispatcher.notify("skin.bald", "Other.bald.info|movie|1", "null")
        self.dispatcher.notify("skin.bald", "Other.bald.info|movie|2", "null")
        self.dispatcher.run_pending()
        self.dispatcher.run_pending()
        self.assertEqual(self.scripts.calls, [("info", "movie", "2")])

    def test_a_newer_request_cancels_the_running_one(self):
        seen = {}

        def hook(action, cancelled, show):
            if action == "info":
                seen["before"] = cancelled()
                self.dispatcher.threaded = True
                self.dispatcher.notify("skin.bald", "Other.bald.play|episode|9", "null")
                seen["after"] = cancelled()

        self.scripts.hook = hook
        self.dispatcher.notify("skin.bald", "Other.bald.info|tvshow|5", "null")
        self.assertEqual(seen, {"before": False, "after": True})
        self.assertTrue(self.xbmc.logs[-1][1].endswith("(superseded)"))
        self.dispatcher.run_pending()
        self.assertEqual(self.scripts.calls[-1], ("play", "episode", "9"))

    def test_the_dialog_swap_opens_the_new_dialog_off_the_worker(self):
        opened = threading.Event()
        self.gui.Dialog.return_value.info.side_effect = lambda item: opened.set()
        self.scripts.hook = lambda action, cancelled, show: show("item")
        self.dispatcher.notify("skin.bald", "Other.bald.open|movie|4", "null")
        self.assertTrue(opened.wait(2))
        self.gui.Dialog.return_value.info.assert_called_once_with("item")

    def test_a_failing_request_is_logged_once_and_the_next_still_runs(self):
        def hook(action, cancelled, show):
            if action == "info":
                raise RuntimeError("library busy")

        self.scripts.hook = hook
        for _ in range(2):
            self.dispatcher.notify("skin.bald", "Other.bald.info|movie|1", "null")
        self.dispatcher.notify("skin.bald", "Other.bald.seriesmeta", "null")
        errors = [text for level, text in self.xbmc.logs if level == self.xbmc.LOGERROR]
        self.assertEqual(errors, ["script.bald.helper: actions: info: RuntimeError: library busy"])
        self.assertEqual(self.scripts.calls[-1], ("seriesmeta", "", ""))

    def test_the_worker_thread_runs_requests(self):
        done = threading.Event()
        self.scripts.hook = lambda action, cancelled, show: done.set()
        dispatcher = actions.Dispatcher(self.xbmc, self.gui, self.scripts, window=self.window)
        dispatcher.start()
        try:
            dispatcher.notify("skin.bald", "Other.bald.seriesmeta", "null")
            self.assertTrue(done.wait(2))
        finally:
            dispatcher.stop()
        self.assertFalse(dispatcher._thread)


class LetterCacheTests(Case):
    def test_library_changes_drop_the_cache(self):
        for method in ("VideoLibrary.OnUpdate", "VideoLibrary.OnRemove", "VideoLibrary.OnScanFinished",
                       "VideoLibrary.OnCleanFinished", "AudioLibrary.OnUpdate", "AudioLibrary.OnRemove",
                       "AudioLibrary.OnScanFinished", "AudioLibrary.OnCleanFinished"):
            with self.subTest(method=method):
                self.dispatcher.letters.put(("key",), ";A;")
                self.dispatcher.notify("xbmc", method, "{}")
                self.assertIsNone(self.dispatcher.letters.get(("key",)))
        self.assertEqual(self.scripts.calls, [])

    def test_other_notifications_keep_it(self):
        self.dispatcher.letters.put(("key",), ";A;")
        self.dispatcher.notify("xbmc", "Player.OnStop", "{}")
        self.dispatcher.notify("xbmc", "AudioLibrary.OnExport", "{}")
        self.assertEqual(self.dispatcher.letters.get(("key",)), ";A;")

    def test_least_recently_used_goes_first(self):
        cache = actions.LetterCache(size=2)
        cache.put("a", ";A;")
        cache.put("b", ";B;")
        cache.get("a")
        cache.put("c", ";C;")
        self.assertEqual((cache.get("a"), cache.get("b"), cache.get("c")), (";A;", None, ";C;"))

    def test_with_the_skins_letters_script(self):
        # The real letters.publish with the service's cache: the second visit reads no items.
        from scripts import letters
        xbmc, gui, window = Mock(), Mock(), FakeWindow()
        gui.Window.return_value = window
        xbmc.getCondVisibility.return_value = True
        labels = {"Container(510).NumAllItems": "2", "Container.FolderPath": "videodb://movies/titles/",
                  "Container(510).ListItemAbsolute(0).SortLetter": "A",
                  "Container(510).ListItemAbsolute(1).SortLetter": "7"}
        xbmc.getInfoLabel.side_effect = lambda label: labels.get(label, "")
        scripts = types.SimpleNamespace(load=lambda: (None, letters))
        dispatcher = actions.Dispatcher(xbmc, gui, scripts, window=FakeWindow(), threaded=False)
        dispatcher.notify("skin.bald", "Other.bald.letters|510", "null")
        self.assertEqual(window.getProperty("Bald.AvailableLetters"), ";0;A;")

        def item_reads():
            return sum("SortLetter" in call.args[0] for call in xbmc.getInfoLabel.call_args_list)

        self.assertEqual(item_reads(), 2)
        dispatcher.notify("skin.bald", "Other.bald.letters|510", "null")
        self.assertEqual(window.getProperty("Bald.AvailableLetters"), ";0;A;")
        self.assertEqual(item_reads(), 2)
        dispatcher.notify("xbmc", "VideoLibrary.OnUpdate", "{}")
        dispatcher.notify("skin.bald", "Other.bald.letters|510", "null")
        self.assertEqual(item_reads(), 4)


class ReadyTests(Case):
    def test_ready_only_while_the_skin_scripts_load(self):
        self.assertTrue(self.dispatcher.refresh())
        self.assertEqual(self.window.getProperty("Bald.Helper.Actions"), "1")
        self.scripts.fail = FileNotFoundError("no skin.bald")
        self.assertFalse(self.dispatcher.refresh())
        self.assertEqual(self.window.getProperty("Bald.Helper.Actions"), "")
        self.scripts.fail = None
        self.dispatcher.refresh()
        self.window.properties.clear()  # a skin reload
        self.dispatcher.refresh()
        self.assertEqual(self.window.getProperty("Bald.Helper.Actions"), "1")

    def test_an_older_skin_keeps_runscript(self):
        self.scripts.info.SERVICE_API = 0
        self.scripts.load = lambda: None
        self.assertFalse(self.dispatcher.refresh())
        self.assertEqual(self.window.getProperty("Bald.Helper.Actions"), "")

    def test_stop_hands_back_to_runscript(self):
        self.dispatcher.start()
        self.assertEqual(self.window.getProperty("Bald.Helper.Actions"), "1")
        self.dispatcher.stop()
        self.assertEqual(self.window.getProperty("Bald.Helper.Actions"), "")


class SkinScriptsTests(unittest.TestCase):
    def test_loads_the_skins_scripts_and_their_api(self):
        scripts = actions.SkinScripts(lambda: str(ROOT / "scripts"))
        info, letters = scripts.load()
        self.assertEqual(info.SERVICE_API, actions.SERVICE_API)
        self.assertTrue(callable(info.handle) and callable(letters.publish))
        self.assertIs(scripts.load()[0], info)  # unchanged files are not reloaded

    def test_reloads_after_a_skin_update_and_refuses_an_old_api(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("info", "letters"):
                Path(directory, f"{name}.py").write_text("SERVICE_API = 1\ndef handle(*a, **k): pass\n"
                                                         "def publish(*a, **k): pass\n")
            scripts = actions.SkinScripts(lambda: directory)
            first = scripts.load()[0]
            path = Path(directory, "info.py")
            path.write_text("SERVICE_API = 0\n")
            os.utime(path, ns=(1, 1))
            self.assertIsNone(scripts.load())
            path.write_text("SERVICE_API = 2\ndef handle(*a, **k): pass\n")
            os.utime(path, ns=(2, 2))
            self.assertIsNot(scripts.load()[0], first)

    def test_a_missing_skin_is_looked_up_again(self):
        found = iter(["/nowhere", str(ROOT / "scripts")])
        scripts = actions.SkinScripts(lambda: next(found))
        with self.assertRaises(OSError):
            scripts.load()
        self.assertIsNotNone(scripts.load())


class MonitorTests(unittest.TestCase):
    def test_the_monitor_hands_notifications_over_and_never_raises(self):
        base = type("Monitor", (), {})
        dispatcher = Mock()
        monitor = actions.make_monitor(types.SimpleNamespace(Monitor=base), dispatcher)
        monitor.onNotification("skin.bald", "Other.bald.seriesmeta", "null")
        dispatcher.notify.assert_called_once_with("skin.bald", "Other.bald.seriesmeta", "null")
        dispatcher.notify.side_effect = RuntimeError("boom")
        monitor.onNotification("skin.bald", "Other.bald.seriesmeta", "null")
        dispatcher.log_error.assert_called_once()


class ServiceLoopTests(unittest.TestCase):
    def test_short_wakes_sync_about_once_a_second_and_refresh_with_it(self):
        xbmc = types.SimpleNamespace(LOGDEBUG=0, LOGINFO=1, LOGERROR=4, log=lambda *a: None)
        service = keymap.Service(xbmc, None, keymap_dir=tempfile.mkdtemp())
        syncs, refreshes, waits = [], [], []
        service.sync = lambda: syncs.append(1)
        service.remove_retired = lambda: None

        class Monitor:
            def waitForAbort(self, timeout):
                waits.append(timeout)
                return len(waits) > 45

        service.run(Monitor(), wake=0.05, each=lambda: refreshes.append(1))
        self.assertEqual(set(waits), {0.05})
        self.assertEqual((len(syncs), len(refreshes)), (1 + 2, 2))  # at start, then every 20 wakes


class ServiceEntryTests(unittest.TestCase):
    def test_the_keymaps_run_even_if_the_actions_cannot_start(self):
        fake = types.SimpleNamespace(LOGERROR=4, logs=[])
        fake.log = lambda message, level: fake.logs.append((level, message))
        modules = {"xbmc": fake, "xbmcgui": types.SimpleNamespace(), "xbmcvfs": types.SimpleNamespace(),
                   "xbmcaddon": types.SimpleNamespace()}
        names = ("resources", "resources.lib", "resources.lib.keymap", "resources.lib.actions")
        saved = {name: sys.modules.get(name) for name in (*modules, *names)}
        sys.modules.update(modules)
        sys.path.insert(0, str(ADDON))
        try:
            for name in names:
                sys.modules.pop(name, None)
            spec = importlib.util.spec_from_file_location("bald_helper_service_actions", ADDON / "service.py")
            service = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(service)
            self.assertEqual(service.start_actions(), (None, None))  # no Window in the stand-in xbmcgui
            self.assertEqual(len(fake.logs), 1)
            self.assertTrue(fake.logs[0][1].startswith("script.bald.helper: actions did not start: "))
        finally:
            sys.path.remove(str(ADDON))
            for name, module in saved.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module


if __name__ == "__main__":
    unittest.main()
