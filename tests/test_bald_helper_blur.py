"""Bald Helper's blurred backgrounds (addons/script.bald.helper/resources/lib/blur.py), with xbmc, xbmcvfs and the Home
window replaced by stand-ins and real Pillow images. Also a benchmark: BALD_BLUR_BENCH=1 prints ms per image."""

import io
import os
import tempfile
import time
import types
import unittest
import zlib
from pathlib import Path

from support import Clock, helper, service

ROOT = Path(__file__).resolve().parents[1]
blur = helper("blur", "blur")

try:
    from PIL import Image
except ImportError:  # pragma: no cover - the Mac this is built on has Pillow
    Image = None

needs_pillow = unittest.skipIf(Image is None, "Pillow not installed")


def jpeg(size=(1920, 1080), colour=(40, 90, 160), noise=True):
    """A representative backdrop: a gradient with some detail, as JPEG bytes."""
    width, height = size
    image = Image.linear_gradient("L").resize(size).convert("RGB")
    overlay = Image.new("RGB", size, colour)
    image = Image.blend(image, overlay, 0.5)
    if noise:
        image = Image.blend(image, Image.effect_noise(size, 60).convert("RGB"), 0.25)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=90)
    return out.getvalue()


class FakeXbmc:
    LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR = 0, 1, 2, 4

    def __init__(self):
        self.skin = "skin.bald"
        self.conditions = {}
        self.labels = {}
        self.logs = []
        self.fail = None

    def getSkinDir(self):
        return self.skin

    def getCondVisibility(self, condition):
        return self.conditions.get(condition, False)

    def getInfoLabel(self, label):
        if self.fail:
            raise self.fail
        return self.labels.get(label, "")

    def getCacheThumbName(self, path):
        # Kodi's own CRC differs; any stable hash of the lower-cased path stands in for it here.
        return "%08x.tbn" % (zlib.crc32(path.lower().encode("utf-8")) & 0xFFFFFFFF)

    def log(self, message, level):
        self.logs.append((level, message))


class FakeFile:
    files = {}

    def __init__(self, path, mode=None):
        self.path = path

    def readBytes(self):
        return bytearray(self.files.get(self.path, b""))

    def close(self):
        pass


class FakeVfs:
    File = FakeFile

    @staticmethod
    def translatePath(path):
        return path


class FakeWindow:
    def __init__(self):
        self.properties = {}
        self.writes = []

    def setProperty(self, key, value):
        self.properties[key] = value
        self.writes.append((key, value))

    def get(self, key):
        return self.properties.get(key, "")


class Case(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.cache = os.path.join(self.directory.name, "blur")
        self.thumbs = os.path.join(self.directory.name, "Thumbnails")
        FakeFile.files = {}
        self.xbmc = FakeXbmc()
        self.window = FakeWindow()
        self.clock = Clock()
        self.blurrer = blur.Blurrer(self.xbmc, FakeVfs, cache_dir=self.cache, thumbnails=self.thumbs)
        self.follower = blur.Follower(self.xbmc, FakeVfs, blurrer=self.blurrer, window=self.window,
                                      clock=self.clock, threaded=False, current_window=lambda: 10000)

    def tearDown(self):
        self.directory.cleanup()

    def focus(self, container, fanart="", window="home", thumb=""):
        """The skin follows `container` in the active window and its focused item has this art."""
        self.xbmc.labels = {"Window(10000).Property(Bald.FocusContainer)": container,
                            f"Container({container}).ListItem.Art(fanart)": fanart,
                            f"Container({container}).ListItem.Art(thumb)": thumb}

    def settle(self, ticks=3):
        for _ in range(ticks):
            self.follower.tick()
            self.clock.advance(0.15)


class NamingTests(unittest.TestCase):
    def test_cache_name_is_md5_and_radius(self):
        name = blur.cache_name("/movies/Heat (1995)/fanart.jpg")
        self.assertRegex(name, r"^[0-9a-f]{32}-r40\.jpg$")
        self.assertNotEqual(name, blur.cache_name("/movies/Heat (1995)/fanart.jpg", radius=20))
        self.assertEqual(blur.RADIUS, 40)
        self.assertEqual(blur.SIZE, (480, 270))
        self.assertEqual(blur.CACHE_DIR, "special://profile/addon_data/script.bald.helper/blur")

    def test_unwrap(self):
        self.assertEqual(blur.unwrap("/a/fanart.jpg"), ("/a/fanart.jpg", True))
        self.assertEqual(blur.unwrap("https://image.tmdb.org/t/p/original/x.jpg"),
                         ("https://image.tmdb.org/t/p/original/x.jpg", True))
        self.assertEqual(blur.unwrap("image://https%3a%2f%2fimage.tmdb.org%2fx.jpg/"),
                         ("https://image.tmdb.org/x.jpg", True))
        self.assertEqual(blur.unwrap("image://smb%3a%2f%2fnas%2fmovies%2ffan%20art.jpg/"),
                         ("smb://nas/movies/fan art.jpg", True))
        # Generated images (video frames, music embeds) exist only in Kodi's thumbnail cache.
        self.assertEqual(blur.unwrap("image://video@%2fmovies%2fheat.mkv/"), ("/movies/heat.mkv", False))

    def test_follow_prefix_per_window(self):
        # Home rows, library views, More like this (5100), Global Search (50): the container the skin names.
        self.assertEqual(blur.follow.follow_prefix("9101", False, False),
                         ("Container(9101).ListItem.", "Container(9101).Scrolling"))
        self.assertEqual(blur.follow.follow_prefix("5100", True, False)[0], "Container(5100).ListItem.")
        # The information dialog's own item.
        self.assertEqual(blur.follow.follow_prefix("", True, False), ("ListItem.", None))
        # A media window's view.
        self.assertEqual(blur.follow.follow_prefix("", False, True), ("Container.ListItem.", "Container.Scrolling"))
        # Settings and other windows: nothing (the skin shows Bald.Blur.Last there).
        self.assertEqual(blur.follow.follow_prefix("", False, False), (None, None))
        self.assertEqual(blur.follow.follow_prefix("$INFO[x]", False, False), (None, None))


@needs_pillow
class PipelineTests(Case):
    def test_render_is_a_480_by_270_jpeg(self):
        data = self.blurrer.render(jpeg())
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual((image.format, image.size, image.mode), ("JPEG", (480, 270), "RGB"))

    def test_cover_crop_keeps_the_centre_of_a_poster(self):
        data = self.blurrer.render(jpeg((1000, 1500), noise=False))
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.size, (480, 270))

    def test_png_with_alpha(self):
        out = io.BytesIO()
        Image.new("RGBA", (800, 450), (200, 10, 10, 128)).save(out, "PNG")
        with Image.open(io.BytesIO(self.blurrer.render(out.getvalue()))) as image:
            self.assertEqual((image.size, image.mode), ((480, 270), "RGB"))

    def test_make_writes_atomically_into_the_cache(self):
        FakeFile.files["/movies/a/fanart.jpg"] = jpeg()
        path = self.blurrer.make("/movies/a/fanart.jpg")
        self.assertEqual(path, os.path.join(self.cache, blur.cache_name("/movies/a/fanart.jpg")))
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(os.listdir(self.cache), [os.path.basename(path)])  # no temporary file left
        self.assertEqual(self.blurrer.cached("/movies/a/fanart.jpg"), path)
        self.assertIsNone(self.blurrer.cached("/movies/b/fanart.jpg"))

    def test_reads_kodis_thumbnail_cache_first(self):
        source = "image://https%3a%2f%2fimage.tmdb.org%2fx.jpg/"
        name = self.xbmc.getCacheThumbName("https://image.tmdb.org/x.jpg")[:-4]
        cached = os.path.join(self.thumbs, name[0], name + ".png")
        os.makedirs(os.path.dirname(cached))
        Path(cached).write_bytes(b"from the thumbnail cache")
        FakeFile.files["https://image.tmdb.org/x.jpg"] = b"from the network"
        self.assertEqual(self.blurrer.read(source), b"from the thumbnail cache")
        os.remove(cached)
        self.assertEqual(self.blurrer.read(source), b"from the network")

    def test_thumbnail_candidates_are_jpg_then_png_under_the_first_character(self):
        found = self.blurrer.thumbnail_candidates("/a.jpg")
        name = self.xbmc.getCacheThumbName("/a.jpg")[:-4]
        self.assertEqual(found, [os.path.join(self.thumbs, name[0], name + ".jpg"),
                                 os.path.join(self.thumbs, name[0], name + ".png")])

    def test_generated_images_are_not_read_directly(self):
        FakeFile.files["/movies/heat.mkv"] = b"video"
        self.assertIsNone(self.blurrer.read("image://video@%2fmovies%2fheat.mkv/"))

    def test_unreadable_source_makes_nothing(self):
        self.assertIsNone(self.blurrer.make("/missing.jpg"))
        self.assertFalse(os.path.exists(self.cache) and os.listdir(self.cache))


    def test_log_lines_never_carry_credentials(self):
        for source in ("smb://user:secret@nas/movies/fanart.jpg",
                       "image://smb%3a%2f%2fuser%3asecret%40nas%2fmovies%2ffanart.jpg/"):
            with self.subTest(source=source):
                self.xbmc.logs.clear()
                self.blurrer.log = lambda text, level=None: self.xbmc.logs.append((level, text))
                self.assertIsNone(self.blurrer.make(source))
                self.assertTrue(self.xbmc.logs)
                self.assertFalse(any("secret" in text or "user" in text for _, text in self.xbmc.logs), self.xbmc.logs)

    def test_log_safe(self):
        safe = blur.common.log_safe
        self.assertEqual(safe("smb://user:pass@nas/a.jpg"), "smb://nas/a.jpg")
        self.assertEqual(safe("image://smb%3a%2f%2fuser%3apass%40nas%2fa.jpg/"), "image://smb%3a%2f%2fnas%2fa.jpg/")
        self.assertEqual(safe("image://https%3a%2f%2fimage.tmdb.org%2fa%40b.jpg/"),
                         "image://https%3a%2f%2fimage.tmdb.org%2fa%40b.jpg/")  # an @ in the path is not a login
        self.assertEqual(safe("/storage/a@b/fanart.jpg"), "/storage/a@b/fanart.jpg")
        self.assertEqual(safe("nfs://nas/export/a.jpg"), "nfs://nas/export/a.jpg")

class PruneTests(Case):
    def fill(self, count, size=1000):
        os.makedirs(self.cache, exist_ok=True)
        paths = []
        for index in range(count):
            path = os.path.join(self.cache, f"{index:032x}-r40.jpg")
            Path(path).write_bytes(b"x" * size)
            os.utime(path, (1000 + index, 1000 + index))
            paths.append(path)
        return paths

    def test_keeps_the_most_recent_within_the_file_limit(self):
        paths = self.fill(10)
        self.assertEqual(self.blurrer.prune(max_bytes=10 ** 9, max_files=4), 6)
        self.assertEqual(sorted(os.listdir(self.cache)), sorted(os.path.basename(p) for p in paths[-4:]))

    def test_keeps_within_the_byte_limit(self):
        paths = self.fill(10, size=1000)
        self.blurrer.prune(max_bytes=3500, max_files=100)
        self.assertEqual(sorted(os.listdir(self.cache)), sorted(os.path.basename(p) for p in paths[-3:]))

    def test_a_cache_hit_counts_as_use(self):
        paths = self.fill(3)
        source_path = paths[0]
        # cached() touches the file, so the oldest becomes the newest.
        self.blurrer.path_for = lambda source: source_path
        self.assertEqual(self.blurrer.cached("any"), source_path)
        self.blurrer.prune(max_bytes=10 ** 9, max_files=1)
        self.assertEqual(os.listdir(self.cache), [os.path.basename(source_path)])

    def test_removes_leftover_temporary_files_and_ignores_others(self):
        self.fill(1)
        old = Path(self.cache, "abc-r40.jpg.1.2.tmp")
        old.write_bytes(b"x")
        stale = time.time() - blur.TMP_STALE_SECONDS - 5
        os.utime(old, (stale, stale))
        # A temporary file being written right now (the other writer thread) stays.
        Path(self.cache, "def-r40.jpg.3.4.tmp").write_bytes(b"x")
        Path(self.cache, "notes.txt").write_bytes(b"x")
        self.blurrer.prune()
        self.assertEqual(sorted(os.listdir(self.cache)),
                         ["00000000000000000000000000000000-r40.jpg", "def-r40.jpg.3.4.tmp", "notes.txt"])

    def test_no_cache_yet(self):
        self.assertEqual(self.blurrer.prune(), 0)

    def test_limits(self):
        self.assertEqual((blur.CACHE_MAX_BYTES, blur.CACHE_MAX_FILES), (60 * 1024 * 1024, 3000))


@needs_pillow
class FollowerTests(Case):
    def test_waits_for_the_source_to_settle(self):
        FakeFile.files["/a.jpg"] = jpeg()
        self.focus("9101", "/a.jpg")
        self.follower.tick()
        self.assertEqual(self.window.writes, [])
        self.clock.advance(0.15)
        self.follower.tick()
        self.assertEqual(self.window.writes, [])
        self.clock.advance(0.15)
        self.follower.tick()
        blurred = self.blurrer.path_for("/a.jpg")
        self.assertEqual(self.window.writes, [("Bald.Blur", blurred), ("Bald.Blur.Last", blurred),
                                              ("Bald.Blur.For", "/a.jpg")])

    def test_moving_on_restarts_the_wait(self):
        FakeFile.files.update({"/a.jpg": jpeg(), "/b.jpg": jpeg(colour=(200, 0, 0))})
        self.focus("9101", "/a.jpg")
        self.follower.tick()
        self.clock.advance(0.2)
        self.focus("9101", "/b.jpg")
        self.follower.tick()
        self.clock.advance(0.2)
        self.follower.tick()
        self.assertEqual(self.window.writes, [])
        self.clock.advance(0.1)
        self.follower.tick()
        self.assertEqual(self.window.get("Bald.Blur.For"), "/b.jpg")
        self.assertFalse(os.path.exists(self.blurrer.path_for("/a.jpg")))  # never blurred

    def test_not_while_the_container_scrolls(self):
        FakeFile.files["/a.jpg"] = jpeg()
        self.focus("9101", "/a.jpg")
        self.xbmc.conditions["Container(9101).Scrolling"] = True
        self.settle(5)
        self.assertEqual(self.window.writes, [])
        self.xbmc.conditions["Container(9101).Scrolling"] = False
        self.follower.tick()
        self.assertEqual(self.window.get("Bald.Blur.For"), "/a.jpg")

    def test_a_cache_hit_publishes_without_blurring(self):
        FakeFile.files["/a.jpg"] = jpeg()
        self.blurrer.make("/a.jpg")
        self.blurrer.render = None  # would fail if called
        self.blurrer.read = None
        self.focus("9101", "/a.jpg")
        self.settle()
        self.assertEqual(self.window.get("Bald.Blur"), self.blurrer.path_for("/a.jpg"))

    def test_blur_strength_follows_the_skin_setting_and_republishes(self):
        FakeFile.files["/a.jpg"] = jpeg()
        self.focus("9101", "/a.jpg")
        self.settle()
        self.assertTrue(self.window.get("Bald.Blur").endswith("-r40.jpg"))
        labels = dict(self.xbmc.labels)
        labels[blur.STRENGTH_SETTING] = "strong"
        self.xbmc.labels = labels
        self.clock.advance(blur.STRENGTH_SECONDS)
        self.settle()
        self.assertEqual(self.blurrer.radius, blur.STRENGTHS["strong"])
        self.assertTrue(self.window.get("Bald.Blur").endswith("-r70.jpg"))
        labels[blur.STRENGTH_SETTING] = ""
        self.clock.advance(blur.STRENGTH_SECONDS)
        self.settle()
        self.assertEqual(self.blurrer.radius, blur.RADIUS)
        self.assertTrue(self.window.get("Bald.Blur").endswith("-r40.jpg"))

    def test_a_cache_hit_is_published_after_100_ms_even_while_scrolling(self):
        FakeFile.files.update({"/a.jpg": jpeg(), "/b.jpg": jpeg(colour=(200, 0, 0))})
        self.blurrer.make("/b.jpg")
        self.blurrer.render = None  # would fail if called
        self.focus("9101", "/a.jpg")
        self.xbmc.conditions["Container(9101).Scrolling"] = True
        self.follower.tick()
        self.clock.advance(0.05)
        self.focus("9101", "/b.jpg")
        # A new source: the next look comes after 100 ms, when a cached blur may already be shown.
        self.assertEqual(self.follower.tick(), blur.FAST_SETTLE_SECONDS)
        self.clock.advance(0.05)
        self.follower.tick()
        self.assertEqual(self.window.writes, [])
        self.clock.advance(0.05)
        self.follower.tick()
        blurred = self.blurrer.path_for("/b.jpg")
        self.assertEqual(self.window.writes, [("Bald.Blur", blurred), ("Bald.Blur.Last", blurred),
                                              ("Bald.Blur.For", "/b.jpg")])

    def test_a_cache_miss_keeps_the_full_wait_and_waits_for_scrolling_to_stop(self):
        FakeFile.files["/a.jpg"] = jpeg()
        made = []
        make = self.blurrer.make
        self.blurrer.make = lambda source: made.append(source) or make(source)
        self.focus("9101", "/a.jpg")
        self.follower.tick()
        self.clock.advance(0.1)
        self.follower.tick()  # 100 ms: not cached, so nothing yet
        self.clock.advance(0.1)
        self.follower.tick()  # 200 ms: still inside the full wait
        self.assertEqual((made, self.window.writes), ([], []))
        self.xbmc.conditions["Container(9101).Scrolling"] = True
        self.clock.advance(0.1)
        self.follower.tick()  # 300 ms but scrolling: fast scrolling makes no work
        self.assertEqual((made, self.window.writes), ([], []))
        self.xbmc.conditions["Container(9101).Scrolling"] = False
        self.follower.tick()
        self.assertEqual(made, ["/a.jpg"])
        self.assertEqual(self.window.get("Bald.Blur.For"), "/a.jpg")

    def test_the_fast_look_does_not_count_as_use(self):
        FakeFile.files["/a.jpg"] = jpeg()
        self.blurrer.make("/a.jpg")
        path = self.blurrer.path_for("/a.jpg")
        os.utime(path, (1, 1))
        self.assertTrue(self.blurrer.has("/a.jpg"))
        self.assertEqual(os.stat(path).st_mtime, 1)
        self.assertFalse(self.blurrer.has("/other.jpg"))

    def test_a_stale_blur_is_not_published(self):
        FakeFile.files.update({"/a.jpg": jpeg(), "/b.jpg": jpeg()})
        make = self.blurrer.make

        def slow_make(source):
            # While /a.jpg is being blurred the viewer moves to /b.jpg, which the poller then asks for.
            if source == "/a.jpg":
                self.follower.wanted = "/b.jpg"
            return make(source)

        self.blurrer.make = slow_make
        self.focus("9101", "/a.jpg")
        self.settle()
        self.assertEqual(self.window.writes, [])
        self.assertTrue(os.path.exists(self.blurrer.path_for("/a.jpg")))  # kept for next time

    def test_back_on_the_shown_item_drops_the_blur_in_flight(self):
        FakeFile.files.update({"/a.jpg": jpeg(), "/b.jpg": jpeg()})
        self.focus("9101", "/a.jpg")
        self.settle()
        self.follower.threaded = True  # queue /b.jpg without a worker to run it yet
        self.focus("9101", "/b.jpg")
        self.settle()
        self.assertEqual(self.follower.wanted, "/b.jpg")
        self.focus("9101", "/a.jpg")
        self.settle()
        self.assertIsNone(self.follower.wanted)
        self.follower.work("/b.jpg")  # the worker finishes late
        self.assertEqual(self.window.get("Bald.Blur.For"), "/a.jpg")

    def test_info_dialog_reads_its_own_container(self):
        # More like this (5100) names its container on the dialog; the window below names another.
        FakeFile.files.update({"/similar.jpg": jpeg(), "/row.jpg": jpeg()})
        self.xbmc.conditions = {blur.follow.INFO_DIALOG: True}
        self.xbmc.labels = {"Window(movieinformation).Property(Bald.FocusContainer)": "5100",
                            "Window(10000).Property(Bald.FocusContainer)": "9101",
                            "Container(5100).ListItem.Art(fanart)": "/similar.jpg",
                            "Container(9101).ListItem.Art(fanart)": "/row.jpg"}
        self.settle()
        self.assertEqual(self.window.get("Bald.Blur.For"), "/similar.jpg")

    def test_item_without_art_clears_blur_but_keeps_the_last(self):
        FakeFile.files["/a.jpg"] = jpeg()
        self.focus("9101", "/a.jpg")
        self.settle()
        blurred = self.window.get("Bald.Blur")
        self.focus("9101", "")
        self.settle()
        self.assertEqual(self.window.get("Bald.Blur"), "")
        self.assertEqual(self.window.get("Bald.Blur.For"), "")
        self.assertEqual(self.window.get("Bald.Blur.Last"), blurred)
        self.assertEqual(self.window.writes[-1], ("Bald.Blur.For", ""))

    def test_art_order_fanart_then_show_fanart_then_thumb(self):
        FakeFile.files["/thumb.jpg"] = jpeg()
        self.focus("9101", "", thumb="/thumb.jpg")
        self.settle()
        self.assertEqual(self.window.get("Bald.Blur.For"), "/thumb.jpg")
        FakeFile.files["/show.jpg"] = jpeg()
        self.xbmc.labels["Container(9101).ListItem.Art(tvshow.fanart)"] = "/show.jpg"
        self.settle()
        self.assertEqual(self.window.get("Bald.Blur.For"), "/show.jpg")

    def test_a_skin_icon_name_is_not_art(self):
        # The add-on browser's items carry Kodi's own icons as bare names; there is nothing to blur.
        self.focus("9101", "", thumb="DefaultAddonSkin.png")
        self.settle()
        self.assertEqual(self.window.get("Bald.Blur"), "")

    def test_info_dialog_and_media_window_fallbacks(self):
        FakeFile.files.update({"/info.jpg": jpeg(), "/view.jpg": jpeg()})
        self.xbmc.labels = {"ListItem.Art(fanart)": "/info.jpg", "Container.ListItem.Art(fanart)": "/view.jpg"}
        self.xbmc.conditions = {blur.follow.INFO_DIALOG: True, blur.follow.MEDIA_WINDOW: True}
        self.settle()
        self.assertEqual(self.window.get("Bald.Blur.For"), "/info.jpg")
        self.xbmc.conditions = {blur.follow.MEDIA_WINDOW: True}
        self.settle()
        self.assertEqual(self.window.get("Bald.Blur.For"), "/view.jpg")
        # Settings: nothing to follow.
        self.xbmc.conditions = {}
        self.settle()
        self.assertEqual((self.window.get("Bald.Blur"), self.window.get("Bald.Blur.For")), ("", ""))
        self.assertEqual(self.window.get("Bald.Blur.Last"), self.blurrer.path_for("/view.jpg"))

    def test_holds_under_a_modal_dialog(self):
        FakeFile.files["/a.jpg"] = jpeg()
        self.focus("9101", "/a.jpg")
        self.settle()
        writes = list(self.window.writes)
        # A context menu: Container(9101) would resolve in the dialog and read empty.
        self.xbmc.conditions[blur.follow.HOLD] = True
        self.xbmc.labels = {}
        self.settle(5)
        self.assertEqual(self.window.writes, writes)

    def test_rests_under_another_skin_with_blur_off_in_fullscreen_and_the_screensaver(self):
        FakeFile.files["/a.jpg"] = jpeg()
        self.focus("9101", "/a.jpg")
        self.xbmc.conditions[blur.REST] = True
        self.assertEqual(self.follower.tick(), blur.IDLE_SECONDS)
        self.settle(5)
        self.assertEqual(self.window.writes, [])
        self.xbmc.conditions[blur.REST] = False
        self.xbmc.skin = "skin.estuary"
        self.settle(5)
        self.assertEqual(self.window.writes, [])
        self.xbmc.skin = "skin.bald"
        self.settle()
        self.assertEqual(self.window.get("Bald.Blur.For"), "/a.jpg")
        self.assertIn("Window.IsActive(fullscreenvideo)", blur.REST)
        self.assertIn("System.ScreenSaverActive", blur.REST)
        self.assertIn("Skin.HasSetting(Bald.DisableBlur)", blur.REST)

    def test_publishes_nothing_without_pillow(self):
        self.blurrer._pil_failed = True
        self.blurrer._pil = None
        self.focus("9101", "/a.jpg")
        self.settle(5)
        self.assertEqual(self.window.writes, [])

    def test_unreadable_source_publishes_empty_and_logs_once(self):
        self.focus("9101", "/missing.jpg")
        self.settle()
        self.assertEqual((self.window.get("Bald.Blur"), self.window.get("Bald.Blur.For")), ("", "/missing.jpg"))

    def test_errors_are_logged_once_and_do_not_stop_the_poller(self):
        self.xbmc.fail = RuntimeError("boom")
        self.follower.IDLE_SECONDS = 0

        class Monitor:
            count = 0

            def abortRequested(self):
                Monitor.count += 1
                return Monitor.count > 4

        self.follower._poller(Monitor())
        errors = [text for level, text in self.xbmc.logs if level == self.xbmc.LOGERROR]
        self.assertEqual(errors, ["script.bald.helper: blur: RuntimeError: boom"])

    def test_a_bad_image_is_logged_and_the_worker_goes_on(self):
        FakeFile.files["/bad.jpg"] = b"not an image"
        self.focus("9101", "/bad.jpg")
        self.settle()
        self.assertEqual(self.window.get("Bald.Blur"), "")
        self.assertEqual(len([1 for level, _ in self.xbmc.logs if level == self.xbmc.LOGERROR]), 1)

    def test_threads_start_and_stop(self):
        follower = blur.Follower(self.xbmc, FakeVfs, blurrer=self.blurrer, window=self.window,
                                 current_window=lambda: 10000)

        class Monitor:
            def abortRequested(self):
                return False

        FakeFile.files["/a.jpg"] = jpeg()
        self.focus("9101", "/a.jpg")
        follower.start(Monitor())
        deadline = time.monotonic() + 5
        while not self.window.get("Bald.Blur.For") and time.monotonic() < deadline:
            time.sleep(0.05)
        follower.stop()
        self.assertEqual(self.window.get("Bald.Blur.For"), "/a.jpg")
        self.assertEqual(follower._threads, [])


class ServiceEntryTests(unittest.TestCase):
    def test_keymaps_run_even_if_the_blur_cannot_start(self):
        fake = types.SimpleNamespace(LOGERROR=4, logs=[])
        fake.log = lambda message, level: fake.logs.append((level, message))
        modules = {"xbmc": fake, "xbmcgui": types.SimpleNamespace(), "xbmcvfs": types.SimpleNamespace(),
                   "xbmcaddon": types.SimpleNamespace()}
        with service(modules) as entry:
            import resources.lib.blur as live_blur

            def broken(*args, **kwargs):
                raise RuntimeError("no window")

            live_blur.Follower = broken
            self.assertIsNone(entry.start_blur())
        self.assertEqual(fake.logs, [(4, "script.bald.helper: blur did not start: RuntimeError: no window")])


@needs_pillow
class WarmerTests(Case):
    def setUp(self):
        super().setUp()
        self.warmer = blur.Warmer(self.xbmc, self.follower, clock=self.clock)
        self.xbmc.conditions[blur.WARM_WHEN] = True
        self.remote = set()  # sources not on this device (not in the texture cache, not a local file)
        self.blurrer.local = lambda source: source not in self.remote

    def rows(self, **rows):
        """Home rows: row id -> list of fanart paths (the selected item first)."""
        for row, arts in rows.items():
            row = row.lstrip("r")
            self.xbmc.labels[f"Container({row}).NumItems"] = str(len(arts))
            for index, art in enumerate(arts):
                prefix = f"Container({row}).ListItem." if index == 0 else f"Container({row}).ListItemNoWrap({index})."
                self.xbmc.labels[prefix + "Art(fanart)"] = art

    def test_scans_every_screens_rows_nearest_items_first(self):
        self.rows(r9101=["/a.jpg", "/b.jpg", "/c.jpg", "/d.jpg"], r9102=["/e.jpg"], r9201=["/f.jpg"], r9601=[])
        self.xbmc.labels["Container(9601).NumItems"] = "0"
        self.assertEqual(self.warmer.sources(), ["/a.jpg", "/b.jpg", "/c.jpg", "/e.jpg", "/f.jpg"])

    def test_skips_cached_and_failed_sources(self):
        self.rows(r9101=["/a.jpg", "/b.jpg"])
        os.makedirs(self.cache, exist_ok=True)
        open(self.blurrer.path_for("/a.jpg"), "wb").close()
        self.warmer.failed["/b.jpg"] = self.clock()
        self.assertEqual(self.warmer.sources(), [])
        # A failure is tried again after a while.
        self.clock.advance(blur.WARM_RETRY_SECONDS + 1)
        self.assertEqual(self.warmer.sources(), ["/b.jpg"])

    def test_never_downloads_art_ahead(self):
        self.rows(r9101=["https://example/a.jpg", "/b.jpg"])
        self.remote.add("https://example/a.jpg")
        self.assertEqual(self.warmer.sources(), ["/b.jpg"])

    def test_a_queue_stops_when_home_is_left(self):
        self.warmer.queue = ["/a.jpg", "/b.jpg"]
        self.xbmc.conditions[blur.WARM_WHEN] = False  # playback started, another window
        self.assertEqual(self.warmer.step(), blur.WARM_PRELOAD_SECONDS)
        self.assertEqual(self.warmer.queue, [])

    def test_blurs_behind_the_splash_without_publishing(self):
        FakeFile.files["/a.jpg"] = jpeg()
        self.rows(r9201=["/a.jpg"])
        self.xbmc.conditions[blur.WARM_PRELOADING] = True
        self.assertEqual(self.warmer.step(), 0.0)  # scanned: one to warm
        self.warmer.step()
        self.assertTrue(self.blurrer.has("/a.jpg"))
        self.assertEqual(self.window.writes, [])

    def test_waits_for_the_remote_to_rest_after_the_splash(self):
        self.rows(r9101=["/a.jpg"])
        self.warmer.step()
        self.assertEqual(self.warmer.queue, [])
        self.xbmc.conditions[blur.WARM_IDLE] = True
        self.clock.advance(blur.WARM_PRELOAD_SECONDS)
        self.warmer.step()
        self.assertEqual(self.warmer.queue, ["/a.jpg"])

    def test_not_off_home_and_not_while_the_follower_is_busy(self):
        self.rows(r9101=["/a.jpg"])
        self.xbmc.conditions[blur.WARM_PRELOADING] = True
        self.xbmc.conditions[blur.WARM_WHEN] = False
        self.warmer.step()
        self.assertEqual(self.warmer.queue, [])
        self.warmer.queue = ["/a.jpg"]
        self.follower.wanted = "/x.jpg"
        self.assertEqual(self.warmer.step(), blur.WARM_PAUSE_SECONDS)
        self.assertEqual(self.warmer.queue, ["/a.jpg"])

    def test_an_unreadable_source_is_not_tried_again(self):
        self.warmer.queue = ["/missing.jpg"]
        self.warmer.step()
        self.assertIn("/missing.jpg", self.warmer.failed)


class BenchTests(unittest.TestCase):
    """Blur time per 1920 x 1080 JPEG; the timing is printed with BALD_BLUR_BENCH=1."""

    def test_blur_time_per_image(self):
        data = jpeg()
        blurrer = blur.Blurrer(FakeXbmc(), FakeVfs, cache_dir=tempfile.gettempdir(), thumbnails="")
        blurrer.render(data)  # warm up (imports)
        runs = 10
        start = time.perf_counter()
        for _ in range(runs):
            blurrer.render(data)
        per_image = (time.perf_counter() - start) / runs * 1000
        if os.environ.get("BALD_BLUR_BENCH"):
            print(f"\nblur: {per_image:.1f} ms per 1920x1080 JPEG ({len(data) // 1024} KB) -> 480x270, "
                  f"radius {blur.RADIUS}")
        self.assertLess(per_image, 1000)


if __name__ == "__main__":
    unittest.main()
