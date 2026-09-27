"""Bald Helper's spoiler stills (addons/script.bald.helper/resources/lib/spoilers.py), with xbmc, the library and the
Home window replaced by stand-ins and real Pillow images."""

import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "addons" / "script.bald.helper" / "resources" / "lib"
SPEC = importlib.util.spec_from_file_location("bald_helper_spoilers", LIB / "spoilers.py")
spoilers = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(spoilers)

try:
    from PIL import Image, ImageFilter, ImageOps
except ImportError:  # pragma: no cover - the Mac this is built on has Pillow
    Image = None

needs_pillow = unittest.skipIf(Image is None, "Pillow not installed")


def jpeg(size=(1280, 720)):
    """A still with sharp detail: black and white stripes."""
    image = Image.new("RGB", size, (255, 255, 255))
    for x in range(0, size[0], 16):
        image.paste((0, 0, 0), (x, 0, x + 8, size[1]))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=95)
    return out.getvalue()


class FakeXbmc:
    LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR = 0, 1, 2, 4

    def __init__(self):
        self.skin = "skin.bald"
        self.conditions = {spoilers.ACTIVE: True}
        self.labels = {}
        self.logs = []

    def getSkinDir(self):
        return self.skin

    def getCondVisibility(self, condition):
        return self.conditions.get(condition, False)

    def getInfoLabel(self, label):
        return self.labels.get(label, "")

    def log(self, message, level):
        self.logs.append((level, message))


class FakeVfs:
    root = ""

    @classmethod
    def translatePath(cls, path):
        return os.path.join(cls.root, "spoilers") + os.sep


class FakeWindow:
    def __init__(self):
        self.properties = {}

    def setProperty(self, key, value):
        self.properties[key] = value

    def clearProperty(self, key):
        self.properties.pop(key, None)

    def getProperty(self, key):
        return self.properties.get(key, "")


class FakeReader:
    """The blur module's Blurrer stand-in: images by source, and Pillow."""

    def __init__(self):
        self.images = {}
        self.reads = []

    def pil(self):
        return (Image, ImageFilter, ImageOps) if Image else None

    def read(self, source):
        self.reads.append(source)
        return self.images.get(source)


class FakeLibrary:
    def __init__(self):
        self.calls = []
        self.answers = {}

    def _answer(self, *key):
        self.calls.append(key)
        return list(self.answers.get(key, []))

    def next_up(self):
        return self._answer("next_up")

    def recent(self):
        return self._answer("recent")

    def show(self, tvshow_id):
        return self._answer("show", tvshow_id)

    def season(self, tvshow_id, season):
        return self._answer("season", tvshow_id, season)

    def episode(self, episode_id):
        return self._answer("episode", episode_id)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def episode(episode_id, thumb=None, playcount=0, position=0):
    return {"episodeid": episode_id, "art": {"thumb": thumb or f"image://still{episode_id}.jpg/"}, "playcount": playcount,
            "resume": {"position": position, "total": 1500}}


class PureTests(unittest.TestCase):
    def test_unwatched_means_never_played_and_not_in_progress(self):
        self.assertTrue(spoilers.unwatched(episode(1)))
        self.assertFalse(spoilers.unwatched(episode(1, playcount=1)))
        self.assertFalse(spoilers.unwatched(episode(1, position=300)))
        self.assertTrue(spoilers.unwatched({"episodeid": 1}))

    def test_scope_for_a_focused_item(self):
        self.assertEqual(spoilers.scope_for("tvshow", "12", "", ""), ("show", 12))
        self.assertEqual(spoilers.scope_for("season", "40", "12", "2"), ("season", 12, 2))
        self.assertEqual(spoilers.scope_for("episode", "900", "12", "0"), ("season", 12, 0))
        for args in (("movie", "3", "", ""), ("episode", "", "", ""), ("tvshow", "", "", ""), ("", "", "", ""),
                     ("season", "40", "12", "")):
            self.assertIsNone(spoilers.scope_for(*args), args)

    def test_library_update_reads_episode_play_counts_only(self):
        self.assertEqual(spoilers.library_update('{"item":{"id":7,"type":"episode"},"playcount":1}'), (7, 1))
        self.assertEqual(spoilers.library_update('{"item":{"id":7,"type":"episode"},"playcount":0}'), (7, 0))
        self.assertIsNone(spoilers.library_update('{"item":{"id":7,"type":"movie"},"playcount":1}'))
        self.assertIsNone(spoilers.library_update('{"item":{"id":7,"type":"episode"}}'))
        self.assertIsNone(spoilers.library_update("not json"))

    def test_the_still_name_is_the_episode_id(self):
        self.assertEqual(spoilers.still_name(1234), "1234.jpg")

    @needs_pillow
    def test_render_leaves_only_a_colour_field(self):
        data = spoilers.render((Image, ImageFilter, ImageOps), jpeg())
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.size, spoilers.SIZE)
            self.assertEqual(image.format, "JPEG")
            grey = image.convert("L")
            low, high = grey.getextrema()
            steps = [abs(grey.getpixel((x, 90)) - grey.getpixel((x + 1, 90))) for x in range(319)]
        # The stripes (0 and 255, eight pixels apart) are gone: a soft mid-grey field without an edge.
        self.assertLess(high - low, 64)
        self.assertLess(max(steps), 6)


class Case(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        FakeVfs.root = self.directory.name
        self.folder = FakeVfs.translatePath("")
        self.xbmc = FakeXbmc()
        self.window = FakeWindow()
        self.reader = FakeReader()
        self.library = FakeLibrary()
        self.clock = Clock()
        self.stills = spoilers.Stills(self.folder, self.reader)
        self.service = spoilers.Spoilers(self.xbmc, FakeVfs, stills=self.stills, library=self.library,
                                         window=self.window, current_window=lambda: 10000, clock=self.clock,
                                         threaded=False)

    def tearDown(self):
        self.directory.cleanup()

    def files(self):
        try:
            return sorted(os.listdir(self.folder))
        except FileNotFoundError:
            return []

    def focus(self, container, **labels):
        self.xbmc.labels = {"Window(10000).Property(Bald.FocusContainer)": container}
        for name, value in labels.items():
            self.xbmc.labels[f"Container({container}).ListItem.{name}"] = value

    def settle(self, ticks=4):
        for _ in range(ticks):
            self.service.tick()
            self.clock.advance(spoilers.POLL_SECONDS)


@needs_pillow
class StillsTests(Case):
    def test_make_writes_once_per_source_and_remembers_it(self):
        self.reader.images["image://a/"] = jpeg()
        self.assertTrue(self.stills.make(5, "image://a/"))
        self.assertFalse(self.stills.make(5, "image://a/"))
        self.assertEqual(self.reader.reads, ["image://a/"])
        self.stills.save()
        self.assertEqual(self.files(), ["5.jpg", "index.json"])
        with open(os.path.join(self.folder, "index.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), {"5": "image://a/"})

    def test_new_art_makes_a_new_still(self):
        self.reader.images.update({"image://a/": jpeg(), "image://b/": jpeg((640, 360))})
        self.stills.make(5, "image://a/")
        self.assertTrue(self.stills.make(5, "image://b/"))

    def test_unreadable_or_empty_source_writes_nothing(self):
        self.assertFalse(self.stills.make(5, "image://missing/"))
        self.assertFalse(self.stills.make(6, ""))
        self.assertEqual(self.files(), [])

    def test_index_survives_a_restart(self):
        self.reader.images["image://a/"] = jpeg()
        self.stills.make(5, "image://a/")
        self.stills.save()
        again = spoilers.Stills(self.folder, self.reader)
        self.assertTrue(again.current(5, "image://a/"))
        self.assertFalse(again.make(5, "image://a/"))

    def test_prune_removes_the_oldest_beyond_the_cap(self):
        self.reader.images["image://a/"] = jpeg((320, 180))
        for number in range(1, 5):
            self.stills.make(number, "image://a/")
            os.utime(self.stills.path(number), (number, number))
        open(os.path.join(self.folder, "9.jpg.1.2.tmp"), "wb").close()
        self.assertEqual(self.stills.prune(max_files=2), 3)
        self.assertEqual(self.files(), ["3.jpg", "4.jpg"])
        self.assertEqual(sorted(self.stills.load()), ["3", "4"])

    def test_clear_removes_the_folder(self):
        self.reader.images["image://a/"] = jpeg()
        self.stills.make(5, "image://a/")
        self.stills.save()
        self.assertEqual(self.stills.clear(), 2)
        self.assertFalse(os.path.exists(self.folder))
        self.assertEqual(self.stills.load(), {})


@needs_pillow
class ServiceTests(Case):
    def test_turning_on_publishes_the_folder_and_warms_up(self):
        self.library.answers[("next_up",)] = [episode(1)]
        self.library.answers[("recent",)] = [episode(2)]
        self.reader.images.update({"image://still1.jpg/": jpeg(), "image://still2.jpg/": jpeg()})
        self.service.tick()
        self.assertEqual(self.window.getProperty(spoilers.PROPERTY_PATH), spoilers.CACHE_DIR)
        self.assertEqual(self.files(), ["1.jpg", "2.jpg", "index.json"])

    def test_off_under_bald_deletes_every_still_and_the_property(self):
        self.library.answers[("recent",)] = [episode(1)]
        self.reader.images["image://still1.jpg/"] = jpeg()
        self.service.tick()
        self.assertTrue(self.files())
        self.xbmc.conditions[spoilers.ACTIVE] = False
        self.service.tick()
        self.assertEqual(self.files(), [])
        self.assertEqual(self.window.getProperty(spoilers.PROPERTY_PATH), "")

    def test_off_at_startup_removes_leftovers(self):
        os.makedirs(self.folder)
        open(os.path.join(self.folder, "3.jpg"), "wb").close()
        self.xbmc.conditions[spoilers.ACTIVE] = False
        self.service.tick()
        self.assertFalse(os.path.exists(self.folder))

    def test_another_skin_pauses_without_deleting(self):
        self.library.answers[("recent",)] = [episode(1)]
        self.reader.images["image://still1.jpg/"] = jpeg()
        self.service.tick()
        self.xbmc.skin = "skin.estuary"
        self.service.tick()
        self.assertEqual(self.window.getProperty(spoilers.PROPERTY_PATH), "")
        self.assertIn("1.jpg", self.files())

    def test_the_active_condition_is_the_skins(self):
        self.assertIn("Skin.HasSetting(Bald.Spoilers)", spoilers.ACTIVE)
        self.assertIn("!Skin.HasSetting(Bald.Spoilers.ShowThumbs)", spoilers.ACTIVE)
        self.assertIn("System.Setting(hideunwatchedepisodethumbs)", spoilers.ACTIVE)

    def test_a_settled_season_is_fetched_once(self):
        self.service.tick()  # on, warm-up
        self.focus("540", DBType="episode", DBID="900", TvShowDBID="12", Season="3")
        self.settle(4)
        self.settle(4)
        self.assertEqual(self.library.calls.count(("season", 12, 3)), 1)

    def test_a_passing_item_is_not_fetched(self):
        self.service.tick()
        self.focus("9101", DBType="tvshow", DBID="12")
        self.service.tick()
        self.focus("9101", DBType="tvshow", DBID="13")
        self.service.tick()
        self.clock.advance(spoilers.SETTLE_SECONDS)
        self.service.tick()
        self.assertNotIn(("show", 12), self.library.calls)
        self.assertIn(("show", 13), self.library.calls)

    def test_the_information_dialogs_own_item(self):
        self.service.tick()
        self.xbmc.conditions[spoilers.INFO_DIALOG] = True
        self.xbmc.labels = {"ListItem.DBType": "tvshow", "ListItem.DBID": "44"}
        self.settle(4)
        self.assertIn(("show", 44), self.library.calls)

    def test_new_stills_switch_the_folder_spelling_once(self):
        self.service.tick()
        self.library.answers[("season", 12, 1)] = [episode(1)]
        self.reader.images["image://still1.jpg/"] = jpeg()
        self.focus("540", DBType="episode", DBID="1", TvShowDBID="12", Season="1")
        self.settle(4)
        self.clock.advance(spoilers.REFRESH_GAP_SECONDS)
        self.service.tick()
        self.assertEqual(self.window.getProperty(spoilers.PROPERTY_PATH), self.folder)
        self.clock.advance(spoilers.REFRESH_GAP_SECONDS)
        self.service.tick()
        self.assertEqual(self.window.getProperty(spoilers.PROPERTY_PATH), self.folder)

    def test_watched_episode_loses_its_still(self):
        self.library.answers[("recent",)] = [episode(1)]
        self.reader.images["image://still1.jpg/"] = jpeg()
        self.service.tick()
        self.service.notify("xbmc", "VideoLibrary.OnUpdate", '{"item":{"id":1,"type":"episode"},"playcount":1}')
        self.assertNotIn("1.jpg", self.files())
        with open(os.path.join(self.folder, "index.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), {})

    def test_marked_unwatched_again_gets_a_still(self):
        self.service.tick()
        self.library.answers[("episode", 8)] = [episode(8)]
        self.reader.images["image://still8.jpg/"] = jpeg()
        self.service.notify("xbmc", "VideoLibrary.OnUpdate", '{"item":{"id":8,"type":"episode"},"playcount":0}')
        self.assertIn("8.jpg", self.files())

    def test_a_scan_forgets_what_was_fetched_and_warms_up_again(self):
        self.service.tick()
        self.focus("540", DBType="episode", DBID="900", TvShowDBID="12", Season="3")
        self.settle(4)
        self.service.notify("xbmc", "VideoLibrary.OnScanFinished", "")
        self.assertEqual(self.library.calls.count(("next_up",)), 2)
        self.settle(4)
        self.assertEqual(self.library.calls.count(("season", 12, 3)), 2)

    def test_rests_during_fullscreen_video(self):
        self.service.tick()
        self.xbmc.conditions[spoilers.REST] = True
        self.focus("540", DBType="episode", DBID="900", TvShowDBID="12", Season="3")
        self.settle(6)
        self.assertNotIn(("season", 12, 3), self.library.calls)

    def test_without_pillow_nothing_is_published(self):
        self.reader.pil = lambda: None
        self.service.tick()
        self.assertEqual(self.window.getProperty(spoilers.PROPERTY_PATH), "")

    def test_stop_clears_the_property(self):
        self.service.tick()
        self.service.stop()
        self.assertEqual(self.window.getProperty(spoilers.PROPERTY_PATH), "")


class LibraryTests(unittest.TestCase):
    class Rpc:
        LOGDEBUG = 0

        def __init__(self, replies):
            self.replies = replies
            self.requests = []

        def executeJSONRPC(self, text):
            request = json.loads(text)
            self.requests.append(request)
            return json.dumps({"id": 1, "jsonrpc": "2.0", "result": self.replies.get(request["method"], {})})

    def test_season_asks_for_unwatched_episodes_and_drops_ones_in_progress(self):
        rpc = self.Rpc({"VideoLibrary.GetEpisodes": {"episodes": [episode(1), episode(2, position=90)]}})
        found = spoilers.Library(rpc).season(12, 3)
        self.assertEqual([e["episodeid"] for e in found], [1])
        params = rpc.requests[0]["params"]
        self.assertEqual((params["tvshowid"], params["season"]), (12, 3))
        self.assertEqual(params["filter"], spoilers.UNWATCHED)
        # Kodi 22's schema: "thumb" is not an episode field (Invalid params); the still is in art.
        self.assertIn("art", params["properties"])
        self.assertNotIn("thumb", params["properties"])
        self.assertIn("resume", params["properties"])

    def test_next_up_follows_the_shows_in_progress(self):
        rpc = self.Rpc({"VideoLibrary.GetInProgressTVShows": {"tvshows": [{"tvshowid": 4}, {"tvshowid": 5}]},
                        "VideoLibrary.GetEpisodes": {"episodes": [episode(1)]}})
        spoilers.Library(rpc).next_up()
        asked = [r["params"].get("tvshowid") for r in rpc.requests if r["method"] == "VideoLibrary.GetEpisodes"]
        self.assertEqual(asked, [4, 5])
        limits = [r["params"]["limits"]["end"] for r in rpc.requests if r["method"] == "VideoLibrary.GetEpisodes"]
        self.assertEqual(limits, [spoilers.NEXT_UP_EPISODES] * 2)

    def test_errors_raise(self):
        class Broken(self.Rpc):
            def executeJSONRPC(self, text):
                return json.dumps({"id": 1, "jsonrpc": "2.0", "error": {"code": -32602, "message": "Invalid params"}})

        with self.assertRaises(RuntimeError):
            spoilers.Library(Broken({})).recent()


class ServiceWiringTests(unittest.TestCase):
    def test_the_service_starts_and_stops_the_spoilers(self):
        text = (ROOT / "addons" / "script.bald.helper" / "service.py").read_text()
        self.assertIn("from resources.lib.spoilers import Spoilers, make_monitor", text)
        self.assertIn("spoilers.stop()", text)
        # The monitor is made on the main thread, before the loop that waits in waitForAbort.
        self.assertLess(text.index("start_spoilers()\n"), text.index("Service(xbmc, xbmcvfs).run("))


if __name__ == "__main__":
    unittest.main()
