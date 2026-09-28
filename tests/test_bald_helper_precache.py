"""Bald Helper's art pre-cache (addons/script.bald.helper/resources/lib/precache.py), with xbmc and xbmcvfs replaced by
stand-ins: which art is asked for and in what order, what is skipped, the pace, the logs and the thread."""

import os
import tempfile
import time
import types
import unittest
import zlib
from urllib.parse import unquote

from support import Clock, helper, service

precache = helper("precache", "precache")

JELLYFIN = "https://jf.example:8920/Items/{}/Images/Backdrop/0?tag=abc&api_key=SECRET"


class FakeXbmc:
    LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR = 0, 1, 2, 4

    def __init__(self):
        self.skin = "skin.bald"
        self.conditions = {}
        self.labels = {}
        self.logs = []

    def getSkinDir(self):
        return self.skin

    def getCondVisibility(self, condition):
        return self.conditions.get(condition, False)

    def getInfoLabel(self, label):
        return self.labels.get(label, "")

    def getCacheThumbName(self, path):
        return "%08x.tbn" % (zlib.crc32(path.lower().encode("utf-8")) & 0xFFFFFFFF)

    def log(self, message, level):
        self.logs.append((level, message))


class FakeVfs:
    """xbmcvfs whose File caches like Kodi's CImageFile: opening image://<key>/ writes <key>'s Thumbnails file."""

    def __init__(self, thumbnails, xbmc):
        self.thumbnails, self.xbmc = thumbnails, xbmc
        self.opened = []
        self.broken = set()  # keys whose server does not answer
        vfs = self

        class File:
            def __init__(self, path, mode=None):
                vfs.opened.append(path)
                assert path.startswith("image://") and path.endswith("/"), path
                key = unquote(path[len("image://"):-1])
                self.size_ = 0
                if key not in vfs.broken:
                    name = xbmc.getCacheThumbName(key)[:-4]
                    folder = os.path.join(thumbnails, name[0])
                    os.makedirs(folder, exist_ok=True)
                    with open(os.path.join(folder, name + ".jpg"), "wb") as handle:
                        handle.write(b"jpeg")
                    self.size_ = 4

            def size(self):
                return self.size_

            def close(self):
                pass

        self.File = File

    @staticmethod
    def translatePath(path):
        return path


class Case(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.thumbs = self.directory.name
        self.xbmc = FakeXbmc()
        self.vfs = FakeVfs(self.thumbs, self.xbmc)
        self.clock = Clock()
        self.pre = precache.Precacher(self.xbmc, self.vfs, clock=self.clock, thumbnails=self.thumbs,
                                      current_window=lambda: 10000)
        self.xbmc.conditions[precache.HOME] = True

    def tearDown(self):
        self.directory.cleanup()

    def row(self, row, arts, position=0, current=True):
        """A Home row: its items' fanart, focus at `position`; current makes it Bald.Row."""
        container = f"Container({row})."
        self.xbmc.labels[container + "NumItems"] = str(len(arts))
        self.xbmc.labels[container + "CurrentItem"] = str(position + 1)
        for index, art in enumerate(arts):
            offset = index - position
            if art:
                self.xbmc.labels[self.pre.item(container, offset) + "Art(fanart)"] = art
        if current:
            self.xbmc.labels[precache.ROW] = str(row)

    def keys(self):
        return [unquote(path[len("image://"):-1]) for path in self.vfs.opened]

    def drain(self):
        """Steps until nothing is left to fetch; returns the waits."""
        waits = []
        for _ in range(100):
            wait = self.pre.step()
            waits.append(wait)
            self.clock.advance(wait)
            if wait == precache.POLL_SECONDS:
                break
        return waits


class SelectionTests(Case):
    def test_focus_then_neighbours_alternating_then_the_screens_other_rows(self):
        arts = [f"http://s/{n}.jpg" for n in range(10)]
        self.row(9101, arts, position=5)
        self.row(9102, ["http://s/r2a.jpg", "http://s/r2b.jpg", "http://s/r2c.jpg"], current=False)
        self.row(9103, [], current=False)
        self.xbmc.labels["Container(9103).NumItems"] = "0"
        self.row(9104, ["http://s/r4a.jpg"], current=False)
        self.xbmc.labels[precache.ROW] = "9101"
        self.assertEqual(self.pre.plan("Container(9101).", False), [
            "http://s/5.jpg", "http://s/6.jpg", "http://s/4.jpg", "http://s/7.jpg", "http://s/3.jpg", "http://s/8.jpg",
            "http://s/2.jpg", "http://s/r2a.jpg", "http://s/r2b.jpg", "http://s/r4a.jpg"])

    def test_ambient_looks_further_ahead(self):
        arts = [f"http://s/{n}.jpg" for n in range(20)]
        self.row(9201, arts, position=2)
        self.assertEqual(self.pre.plan("Container(9201).", True),
                         [f"http://s/{n}.jpg" for n in range(2, 2 + precache.AMBIENT_AHEAD + 1)] + ["http://s/1.jpg"])
        self.xbmc.conditions[precache.AMBIENT] = True
        self.pre.step()
        self.assertEqual(self.pre.queue[:3], ["http://s/3.jpg", "http://s/4.jpg", "http://s/5.jpg"])

    def test_a_pass_is_capped(self):
        self.row(9101, [f"http://s/{n}.jpg" for n in range(8)])
        for row in range(9102, 9121):
            self.row(row, [f"http://s/{row}-{n}.jpg" for n in range(3)], current=False)
        self.xbmc.labels[precache.ROW] = "9101"
        self.assertEqual(len(self.pre.plan("Container(9101).", False)), precache.BATCH)

    def test_show_fanart_then_thumb_when_the_item_has_no_fanart(self):
        self.row(9101, [""])
        self.xbmc.labels["Container(9101).ListItem.Art(tvshow.fanart)"] = "http://s/show.jpg"
        self.assertEqual(self.pre.plan("Container(9101).", False), ["http://s/show.jpg"])
        del self.xbmc.labels["Container(9101).ListItem.Art(tvshow.fanart)"]
        self.xbmc.labels["Container(9101).ListItem.Art(thumb)"] = "http://s/thumb.jpg"
        self.assertEqual(self.pre.plan("Container(9101).", False), ["http://s/thumb.jpg"])

    def test_library_view_follows_its_focus_container(self):
        self.xbmc.conditions[precache.HOME] = False
        self.xbmc.labels["Window(10000).Property(Bald.FocusContainer)"] = "55"
        self.row(55, ["http://s/a.jpg", "http://s/b.jpg", "http://s/c.jpg"], position=1, current=False)
        self.assertEqual(self.pre.focus(), "Container(55).")
        self.assertEqual(self.pre.plan("Container(55).", False), ["http://s/b.jpg", "http://s/c.jpg", "http://s/a.jpg"])
        self.assertEqual(self.pre.other_rows("Container(55)."), [], "only Home screens have sibling rows")

    def test_media_window_and_info_dialog(self):
        self.xbmc.conditions[precache.HOME] = False
        self.xbmc.conditions["Window.IsMedia"] = True
        self.assertEqual(self.pre.focus(), "Container.")
        self.xbmc.conditions["Window.IsModalDialogTopmost(movieinformation)"] = True
        self.assertIsNone(self.pre.focus(), "the information dialog's item has no neighbours")

    def test_home_without_a_current_row_falls_back_to_follow(self):
        self.xbmc.labels["Window(10000).Property(Bald.FocusContainer)"] = "9180"
        self.assertEqual(self.pre.focus(), "Container(9180).")

    def test_other_rows_of_each_screen(self):
        self.assertEqual(self.pre.other_rows("Container(9051).")[:2], [9052, 9053])
        self.assertEqual(self.pre.other_rows("Container(9203).")[:3], [9201, 9202, 9204])
        self.assertEqual(self.pre.other_rows("Container(9120).")[-1], 9119)
        self.assertEqual(self.pre.other_rows("Container."), [])


class SkipTests(Case):
    def test_only_art_behind_a_network(self):
        for source, key in (("http://s/a.jpg", "http://s/a.jpg"),
                            ("image://https%3a%2f%2fs%2fb.jpg/", "https://s/b.jpg"),
                            ("smb://nas/art/c.jpg", "smb://nas/art/c.jpg"),
                            ("/storage/art/d.jpg", None), ("C:\\art\\e.jpg", None),
                            ("special://profile/f.jpg", None),
                            ("resource://resource.images.weatherfanart.multi/32/sunny-2.jpg", None),
                            ("image://video@%2fmovies%2fa.mkv/", None), ("plugin://plugin.video.x/?a=1", None)):
            self.assertEqual(precache.cache_key(source), key, source)

    def test_image_url_round_trips(self):
        key = JELLYFIN.format("ab12")
        url = precache.image_url(key)
        self.assertTrue(url.startswith("image://https%3A%2F%2F") and url.endswith("/"))
        self.assertNotIn("?", url, "the query stays inside the encoded path, not image:// options")
        self.assertEqual(unquote(url[len("image://"):-1]), key)

    def test_cached_and_asked_for_art_is_not_asked_again(self):
        self.row(9101, ["http://s/a.jpg", "http://s/b.jpg", "http://s/c.jpg"])
        name = self.xbmc.getCacheThumbName("http://s/a.jpg")[:-4]
        os.makedirs(os.path.join(self.thumbs, name[0]))
        open(os.path.join(self.thumbs, name[0], name + ".png"), "wb").close()
        self.drain()
        self.assertEqual(self.keys(), ["http://s/b.jpg", "http://s/c.jpg"])
        self.vfs.opened.clear()
        for name in os.listdir(self.thumbs):  # even if the files went, what was asked for is remembered
            for file in os.listdir(os.path.join(self.thumbs, name)):
                os.remove(os.path.join(self.thumbs, name, file))
        self.clock.advance(precache.RESCAN_SECONDS)
        self.drain()
        self.assertEqual(self.keys(), [])

    def test_local_and_resource_art_is_never_opened(self):
        self.row(9101, ["/storage/a.jpg", "resource://resource.images.x/b.jpg", "special://skin/c.png"])
        self.drain()
        self.assertEqual(self.vfs.opened, [])

    def test_a_failure_is_tried_again_after_a_while(self):
        self.row(9101, ["http://down/a.jpg"])
        self.vfs.broken.add("http://down/a.jpg")
        self.drain()
        self.clock.advance(precache.RESCAN_SECONDS)
        self.drain()
        self.assertEqual(self.keys(), ["http://down/a.jpg"])
        self.clock.advance(precache.RETRY_SECONDS)
        self.drain()
        self.assertEqual(self.keys(), ["http://down/a.jpg"] * 2)

    def test_the_memory_is_bounded(self):
        for n in range(precache.REMEMBER + 50):
            self.pre.remember(f"http://s/{n}.jpg", True, 0.0)
        self.assertEqual(len(self.pre.asked), precache.REMEMBER)
        self.assertNotIn("http://s/0.jpg", self.pre.asked)


class PaceTests(Case):
    def test_one_image_per_pause(self):
        self.row(9101, [f"http://s/{n}.jpg" for n in range(5)], position=2)
        waits = self.drain()
        self.assertEqual(len(self.vfs.opened), 5)
        self.assertEqual(waits[:5], [precache.PAUSE_SECONDS] * 5)
        self.assertGreaterEqual(precache.PAUSE_SECONDS, 0.25)
        self.assertEqual(waits[5], precache.POLL_SECONDS)

    def test_no_rescan_until_the_viewer_moves(self):
        self.row(9101, ["http://s/a.jpg", "http://s/b.jpg"])
        self.drain()
        calls = []
        original = self.pre.plan
        self.pre.plan = lambda *args: calls.append(args) or original(*args)
        self.pre.step()
        self.assertEqual(calls, [], "same row, same item: no plan")
        self.xbmc.labels["Container(9101).CurrentItem"] = "2"
        self.pre.step()
        self.assertEqual(len(calls), 1, "moving on plans again")
        self.clock.advance(precache.RESCAN_SECONDS)
        self.pre.step()
        self.assertEqual(len(calls), 2, "and so does time")

    def test_a_move_replaces_the_queue_with_the_new_neighbourhood(self):
        self.row(9101, [f"http://s/{n}.jpg" for n in range(12)])
        self.pre.step()
        self.row(9101, [f"http://s/{n}.jpg" for n in range(12)], position=9)
        self.pre.step()
        self.assertEqual(self.keys(), ["http://s/0.jpg", "http://s/9.jpg"])

    def test_rests_under_another_skin_in_fullscreen_video_and_the_screensaver(self):
        self.row(9101, ["http://s/a.jpg", "http://s/b.jpg"])
        self.pre.step()
        self.assertIn("Window.IsActive(fullscreenvideo)", precache.REST)
        self.assertIn("System.ScreenSaverActive", precache.REST)
        for rest in ("skin", precache.REST):
            if rest == "skin":
                self.xbmc.skin = "skin.estuary"
            else:
                self.xbmc.conditions[rest] = True
            self.assertEqual(self.pre.step(), precache.IDLE_SECONDS, rest)
            self.assertEqual(self.pre.queue, [], rest)
            self.xbmc.skin = "skin.bald"
            self.xbmc.conditions.pop(rest, None)
        self.assertEqual(self.keys(), ["http://s/a.jpg"])
        self.drain()
        self.assertEqual(self.keys(), ["http://s/a.jpg", "http://s/b.jpg"], "resumes afterwards")

    def test_a_held_item_keeps_the_queue(self):
        self.row(9101, ["http://s/a.jpg", "http://s/b.jpg"])
        self.pre.step()
        self.xbmc.conditions[precache.HOME] = False
        self.xbmc.conditions[precache.follow.HOLD] = True
        self.pre.step()
        self.assertEqual(self.keys(), ["http://s/a.jpg", "http://s/b.jpg"])

    def test_needs_no_web_server_and_no_json_rpc(self):
        self.row(9101, ["http://s/a.jpg"])
        self.xbmc.executeJSONRPC = lambda request: self.fail("no JSON-RPC")
        self.drain()
        self.assertEqual(self.vfs.opened, ["image://http%3A%2F%2Fs%2Fa.jpg/"])


class LogTests(Case):
    def test_redact(self):
        self.assertEqual(precache.redact(JELLYFIN.format("ab12")), "https://jf.example:8920/Items/ab12/Images/Backdrop/0?...")
        self.assertEqual(precache.redact("image://https%3a%2f%2fuser%3apw%40h%2fa.jpg%3fX-Plex-Token%3dT/"),
                         "https://h/a.jpg?...")
        self.assertEqual(precache.redact("smb://user:pass@nas/a.jpg"), "smb://nas/a.jpg")

    def test_logs_never_carry_tokens_and_a_failing_server_is_logged_once(self):
        self.row(9101, [JELLYFIN.format(n) for n in range(4)])
        self.vfs.broken.update(JELLYFIN.format(n) for n in range(3))
        self.drain()
        text = "\n".join(message for _, message in self.xbmc.logs)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("api_key", text)
        self.assertNotIn("tag=", text)
        warnings = [message for level, message in self.xbmc.logs if level == self.xbmc.LOGWARNING]
        self.assertEqual(warnings, ["script.bald.helper: precache: cannot cache art from https://jf.example "
                                    "(first: https://jf.example:8920/Items/0/Images/Backdrop/0?...)"])

    def test_an_error_is_logged_once_and_the_thread_goes_on(self):
        def broken(*args):
            raise RuntimeError("bad https://h/a.jpg?api_key=SECRET")

        self.xbmc.getInfoLabel = broken

        class Monitor:
            def abortRequested(self):
                return False

        pre = precache.Precacher(self.xbmc, self.vfs, current_window=lambda: 10000, thumbnails=self.thumbs)
        waits = []
        pre._stop.wait = lambda wait: waits.append(wait) or len(waits) >= 3  # three failing steps, then stop
        pre._run(Monitor())
        self.assertEqual(waits, [precache.RESCAN_SECONDS] * 3)
        errors = [message for _, message in self.xbmc.logs]
        self.assertEqual(errors, ["script.bald.helper: precache: RuntimeError: bad https://h/a.jpg"])


class ThreadTests(Case):
    def test_starts_fetches_and_stops(self):
        class Monitor:
            def abortRequested(self):
                return False

        self.row(9101, ["http://s/a.jpg"])
        pre = precache.Precacher(self.xbmc, self.vfs, current_window=lambda: 10000, thumbnails=self.thumbs)
        pre.start(Monitor())
        deadline = time.monotonic() + 5
        while not self.vfs.opened and time.monotonic() < deadline:
            time.sleep(0.02)
        pre.stop()
        self.assertEqual(self.keys(), ["http://s/a.jpg"])
        self.assertIsNone(pre._thread)
        self.assertEqual([m for _, m in self.xbmc.logs][-1], "script.bald.helper: precache: stopped")

    def test_service_starts_and_survives_a_failed_start(self):
        fake = types.SimpleNamespace(LOGERROR=4, logs=[])
        fake.log = lambda message, level: fake.logs.append((level, message))
        modules = {"xbmc": fake, "xbmcgui": types.SimpleNamespace(), "xbmcvfs": types.SimpleNamespace(),
                   "xbmcaddon": types.SimpleNamespace()}
        with service(modules) as entry:
            import resources.lib.precache as live

            def broken(*args, **kwargs):
                raise RuntimeError("no thread")

            live.Precacher = broken
            self.assertIsNone(entry.start_precache())
        self.assertEqual(fake.logs, [(4, "script.bald.helper: art pre-cache did not start: RuntimeError: no thread")])


if __name__ == "__main__":
    unittest.main()
