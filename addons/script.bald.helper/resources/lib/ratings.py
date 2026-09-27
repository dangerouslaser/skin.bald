"""Bald Helper's online ratings: follow the item Bald shows (and the playing movie) and publish its MDbList ratings.

The item is the one the blur follows (follow.py). Once it has stayed the same for SETTLE_SECONDS and its container is
not scrolling, and it is a movie or TV show with an IMDb, TMDb or (shows) TVDb id, its ratings are looked up
(mdblist.py: the SQLite cache first, then the API within the day's quota) on one worker thread and published only
if it is still the current item. Ratings already in the cache are published after FAST_SETTLE_SECONDS, even while
the container scrolls. Episodes and seasons are not looked up: MDbList has no episode or season ratings.

Home window properties (10000), <key> one of mdblist.KEYS:

    Bald.Ratings.<key>             the value as Bald shows it ("7.8", "91", "3.9")
    Bald.Ratings.<key>.Votes       the vote count ("12,345"), when MDbList has one
    Bald.Ratings.IMDbID / TMDbID   the ids the ratings belong to
    Bald.Ratings.DBID              the library id, empty for add-on items
    Bald.Ratings.DBType            movie or tvshow; written last, cleared first
    Bald.Player.Ratings.*          the same for the playing movie (identity DBType, DBID, IMDbID, TMDbID)
    Bald.Helper.Ratings            "1" while an API key is set and not refused (the skin's readiness check)
    Bald.Helper.Ratings.Last       "<how>|<type>|<id>|<ms>" of the last lookup (for live checks)

The identity goes last and is cleared first: when the followed item changes, DBType is cleared at once, the values
are replaced, and the identity is written only after them, so the skin (which compares the identity with the item it
shows) never shows one item's score on another. The API key is never written to a property or the log.

Nothing here imports xbmc at module level, so the tests drive it with stand-ins.
"""

from __future__ import annotations

import json
import os
import threading
import time

try:
    from . import follow, mdblist
except ImportError:  # loaded by file path (the tests): load the siblings the same way
    import importlib.util as _util

    def _sibling(name):
        spec = _util.spec_from_file_location(f"bald_helper_{name}", os.path.join(os.path.dirname(__file__), f"{name}.py"))
        module = _util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    follow, mdblist = _sibling("follow"), _sibling("mdblist")

ADDON_ID = "script.bald.helper"
SKIN_ID = "skin.bald"
HOME_WINDOW = 10000
DATA_DIR = "special://profile/addon_data/script.bald.helper"
DATABASE = "ratings.db"
KEY_SETTING = "mdblist_key"

POLL_SECONDS = 0.15
IDLE_SECONDS = 1.0
SETTLE_SECONDS = 0.4
FAST_SETTLE_SECONDS = 0.1
KEY_SECONDS = 2.0          # how often the API key setting is read again

PREFIX = "Bald.Ratings"
PLAYER_PREFIX = "Bald.Player.Ratings"
PROPERTY_READY = "Bald.Helper.Ratings"
PROPERTY_LAST = "Bald.Helper.Ratings.Last"
# Written in this order; DBType, which every skin guard compares, last.
IDENTITY = ("IMDbID", "TMDbID", "DBID", "DBType")

# Online ratings off, ratings off, fullscreen video or the screensaver: no lookups.
OFF = "Skin.HasSetting(Bald.Ratings.Hide) | Skin.HasSetting(Bald.Ratings.NoOnline)"
REST = "Window.IsActive(fullscreenvideo) | System.ScreenSaverActive"
PLAYER_OFF = "Skin.HasSetting(Bald.Ratings.Hide) | Skin.HasSetting(Bald.Ratings.NoOnline) | Skin.HasSetting(Bald.Ratings.NoOSD)"
ITEM = ("DBType", "DBID", "UniqueID(imdb)", "UniqueID(tmdb)", "UniqueID(tvdb)")


class Publisher:
    """Writes one item's ratings under a prefix, the identity last; clears the identity first."""

    def __init__(self, window, prefix: str):
        self.window = window
        self.prefix = prefix

    def name(self, suffix: str) -> str:
        return f"{self.prefix}.{suffix}"

    def clear_identity(self) -> None:
        for suffix in reversed(IDENTITY):  # DBType first
            self.window.clearProperty(self.name(suffix))

    def clear(self) -> None:
        self.clear_identity()
        for key in mdblist.KEYS:
            self.window.clearProperty(self.name(key))
            self.window.clearProperty(self.name(f"{key}.Votes"))

    def publish(self, identity: dict, values: dict | None) -> None:
        self.clear_identity()
        values = values or {}
        for key in mdblist.KEYS:
            for suffix in (key, f"{key}.Votes"):
                if values.get(suffix):
                    self.window.setProperty(self.name(suffix), values[suffix])
                else:
                    self.window.clearProperty(self.name(suffix))
        for suffix in IDENTITY:
            if identity.get(suffix):
                self.window.setProperty(self.name(suffix), identity[suffix])
            else:
                self.window.clearProperty(self.name(suffix))


class Follower:
    """Polls the item Bald shows and publishes its ratings (see the module docstring)."""

    def __init__(self, xbmc, ratings: mdblist.Ratings, window, key_reader, current_window,
                 clock=time.monotonic, threaded: bool = True):
        self.xbmc = xbmc
        self.ratings = ratings
        self.window = window
        self.key_reader = key_reader          # () -> the API key setting, read fresh
        self.current_window = current_window
        self.clock = clock
        self.threaded = threaded
        self.publisher = Publisher(window, PREFIX)
        self.key = ""
        self.last_key = ""      # the last non-empty key (in memory only)
        self.key_read_at = None
        self.ready = False
        self.lock = threading.Lock()
        self.candidate = None   # the item seen on the last tick (a Ref, or None)
        self.since = 0.0
        self.shown = None       # the item whose identity is published
        self.wanted = None      # the item being looked up on the worker
        self.dirty = False      # something may be published (cleared when resting off)
        self._job = None
        self._job_ready = threading.Condition()
        self._stop = threading.Event()
        self._threads = []
        self._logged = set()

    # --- logging ---
    def log(self, text: str, level=None) -> None:
        self.xbmc.log(f"{ADDON_ID}: ratings: {text}", self.xbmc.LOGDEBUG if level is None else level)

    def log_once(self, text: str, level=None) -> None:
        if text in self._logged:
            return
        if len(self._logged) > 200:
            self._logged.clear()
        self._logged.add(text)
        self.log(text, self.xbmc.LOGERROR if level is None else level)

    def api_log(self, text: str, error: bool = False) -> None:
        text = mdblist.redact(text, self.key)
        if error:
            self.log_once(text, getattr(self.xbmc, "LOGWARNING", None))
        else:
            self.log(text)

    # --- the key and readiness ---
    def current_key(self) -> str:
        return self.key

    def refresh_key(self, force: bool = False) -> None:
        now = self.clock()
        if not force and self.key_read_at is not None and now - self.key_read_at < KEY_SECONDS:
            return
        self.key_read_at = now
        try:
            key = (self.key_reader() or "").strip()
        except Exception as error:  # noqa: BLE001 - a settings read must not stop the follower
            self.log_once(f"cannot read the key setting: {type(error).__name__}")
            return
        if key != self.key:
            if key and self.last_key and key != self.last_key:
                self.ratings.key_changed()  # another account: its quota and a refusal were the old key's
            self.key = key
            self.last_key = key or self.last_key
            with self.lock:
                self.shown = None  # look the item up again with the new key
            self.log("API key set" if key else "no API key", self.xbmc.LOGINFO)
        ready = self.ratings.key_usable(self.key)
        if ready:
            if self.window.getProperty(PROPERTY_READY) != "1":  # also after a skin reload
                self.window.setProperty(PROPERTY_READY, "1")
        elif self.ready or self.window.getProperty(PROPERTY_READY):
            self.window.clearProperty(PROPERTY_READY)
        self.ready = ready

    # --- reading Kodi ---
    def read(self, prefix: str):
        labels = [self.xbmc.getInfoLabel(prefix + name) for name in ITEM]
        return mdblist.make_ref(*labels)

    def clear_all(self) -> None:
        with self.lock:
            self.wanted = None
            self.shown = None
            self.candidate = None
            if self.dirty:
                self.publisher.clear()
                self.dirty = False

    # --- one poll ---
    def tick(self) -> float:
        self.refresh_key()
        if self.xbmc.getSkinDir() != SKIN_ID or not self.ready or self.xbmc.getCondVisibility(OFF):
            self.clear_all()
            return IDLE_SECONDS
        if self.xbmc.getCondVisibility(REST):
            self.candidate = None
            return IDLE_SECONDS
        located = follow.locate(self.xbmc, self.current_window)
        if located is follow.HELD:
            return POLL_SECONDS
        prefix, scrolling = located
        ref = self.read(prefix) if prefix else None
        now = self.clock()
        if ref != self.candidate:
            self.candidate, self.since = ref, now
            with self.lock:
                if self.shown is not None and ref != self.shown:
                    self.publisher.clear_identity()  # the item changed: nothing shown may match it any more
                    self.shown = None
            return FAST_SETTLE_SECONDS
        with self.lock:
            if ref is not None and ref == self.wanted:
                return POLL_SECONDS
            if ref == self.shown:
                self.wanted = None
                return POLL_SECONDS
        if ref is None:
            return POLL_SECONDS  # nothing to rate: its identity was cleared when the item changed
        elapsed = now - self.since
        if elapsed < FAST_SETTLE_SECONDS - 0.01:
            return POLL_SECONDS
        found, values = self.ratings.cached(ref)
        if found:
            with self.lock:
                self.wanted = None
                self.show(ref, values, "cache", 0)
            return POLL_SECONDS
        if elapsed < SETTLE_SECONDS - 0.01:
            return POLL_SECONDS
        if scrolling and self.xbmc.getCondVisibility(scrolling):
            return POLL_SECONDS
        self.request(ref)
        return POLL_SECONDS

    def show(self, ref, values, how: str, started: float) -> None:
        """Publish (lock held). A lookup that could not be made (quota, no key, network) publishes nothing, but the
        item counts as handled, so it is not asked again until the viewer comes back to it."""
        if how in ("cache", "api", "missing"):
            self.publisher.publish(ref.identity(), values)
            self.dirty = True
        self.shown = ref
        elapsed = int((self.clock() - started) * 1000) if started else 0
        self.window.setProperty(PROPERTY_LAST, f"{how}|{ref.dbtype}|{ref.dbid or ref.imdb or ref.tmdb or ref.tvdb}|{elapsed}")

    def request(self, ref) -> None:
        with self.lock:
            self.wanted = ref
        if not self.threaded:
            self.work(ref)
            return
        with self._job_ready:
            self._job = ref
            self._job_ready.notify()

    def work(self, ref) -> None:
        started = self.clock()
        try:
            values, how = self.ratings.get(ref, cancelled=lambda: self.wanted != ref or self._stop.is_set())
        except Exception as error:  # noqa: BLE001 - one bad answer must not end the worker
            self.log_once(mdblist.redact(f"{type(error).__name__}: {error}", self.key))
            values, how = None, "error"
        with self.lock:
            if self.wanted != ref:
                return  # the viewer has moved on
            self.wanted = None
            self.show(ref, values, how, started)
        self.log(f"{ref!r}: {how}")

    # --- threads ---
    def _worker(self) -> None:
        while not self._stop.is_set():
            with self._job_ready:
                while self._job is None and not self._stop.is_set():
                    self._job_ready.wait(1.0)
                ref, self._job = self._job, None
            if ref is not None and not self._stop.is_set():
                self.work(ref)

    def _poller(self, monitor) -> None:
        wait = POLL_SECONDS
        while not self._stop.is_set() and not monitor.abortRequested():
            try:
                wait = self.tick()
            except Exception as error:  # noqa: BLE001 - the follower outlives any single failure
                self.log_once(mdblist.redact(f"{type(error).__name__}: {error}", self.key))
                wait = IDLE_SECONDS
            if self._stop.wait(wait):
                break

    def start(self, monitor=None) -> None:
        monitor = monitor or self.xbmc.Monitor()
        for target, args in ((self._worker, ()), (self._poller, (monitor,))):
            thread = threading.Thread(target=target, args=args, name=f"{ADDON_ID}.ratings", daemon=True)
            thread.start()
            self._threads.append(thread)
        self.log("started")

    def stop(self) -> None:
        self._stop.set()
        with self._job_ready:
            self._job_ready.notify_all()
        for thread in self._threads:
            thread.join(2.0)
        self._threads = []
        try:
            self.window.clearProperty(PROPERTY_READY)
            self.publisher.clear()
        except Exception:  # noqa: BLE001 - shutting down
            pass
        self.log("stopped")


def jsonrpc(xbmc, method: str, params: dict) -> dict:
    """One JSON-RPC call through Kodi; {} on any error."""
    try:
        answer = json.loads(xbmc.executeJSONRPC(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                                                            "params": params})))
    except (TypeError, ValueError):
        return {}
    return answer.get("result") or {} if isinstance(answer, dict) else {}


class PlayerRatings:
    """The playing movie's ratings as Bald.Player.Ratings.*: resolved on onAVStarted, cleared on stop or change.
    Episodes are not looked up (MDbList has no episode ratings); the skin then keeps TMDb Helper's player values."""

    def __init__(self, xbmc, ratings: mdblist.Ratings, window, follower: Follower, threaded: bool = True,
                 clock=time.monotonic):
        self.xbmc = xbmc
        self.ratings = ratings
        self.follower = follower
        self.threaded = threaded
        self.clock = clock
        self.publisher = Publisher(window, PLAYER_PREFIX)
        self.lock = threading.Lock()
        self.serial = 0

    def active(self) -> bool:
        return (self.xbmc.getSkinDir() == SKIN_ID and self.follower.ready
                and not self.xbmc.getCondVisibility(PLAYER_OFF))

    def resolve(self):
        """The playing item as a Ref, or None (not a movie, or no id)."""
        if not self.xbmc.getCondVisibility("VideoPlayer.Content(movies)"):
            return None
        dbid = self.xbmc.getInfoLabel("VideoPlayer.DBID").strip()
        if dbid.isdigit() and int(dbid) > 0:
            details = jsonrpc(self.xbmc, "VideoLibrary.GetMovieDetails",
                              {"movieid": int(dbid), "properties": ["uniqueid"]}).get("moviedetails") or {}
            ids = details.get("uniqueid") or {}
            ref = mdblist.make_ref("movie", dbid, str(ids.get("imdb") or ""), str(ids.get("tmdb") or ""))
            if ref is not None:
                return ref
        return mdblist.make_ref("movie", dbid if dbid.isdigit() and int(dbid) > 0 else "",
                                self.xbmc.getInfoLabel("VideoPlayer.UniqueID(imdb)"),
                                self.xbmc.getInfoLabel("VideoPlayer.UniqueID(tmdb)"))

    def stopped(self) -> None:
        with self.lock:
            self.serial += 1
            self.publisher.clear()

    def started(self) -> None:
        with self.lock:
            self.serial += 1
            serial = self.serial
            self.publisher.clear()
        if not self.active():
            return
        if not self.threaded:
            self.work(serial)
            return
        threading.Thread(target=self.work, args=(serial,), name=f"{ADDON_ID}.player", daemon=True).start()

    def work(self, serial: int) -> None:
        try:
            ref = self.resolve()
            if ref is None:
                return
            values, how = self.ratings.get(ref, cancelled=lambda: self.serial != serial)
        except Exception as error:  # noqa: BLE001
            self.follower.log_once(mdblist.redact(f"player: {type(error).__name__}: {error}", self.follower.key))
            return
        with self.lock:
            if self.serial != serial:
                return  # stopped or another item started meanwhile
            if how in ("cache", "api", "missing"):
                self.publisher.publish(ref.identity(), values)
        self.follower.log(f"player {ref!r}: {how}")


def make_player(xbmc, watcher: PlayerRatings):
    """An xbmc.Player that hands playback events to the watcher. Kodi runs its callbacks on the thread that made it,
    while that thread waits, so create it on the thread that runs the service loop."""

    class RatingsPlayer(xbmc.Player):
        def _call(self, step):
            try:
                step()
            except Exception as error:  # noqa: BLE001 - never raise into Kodi's callback
                watcher.follower.log_once(f"player callback: {type(error).__name__}: {error}")

        def onAVStarted(self):  # noqa: N802 - Kodi's names
            self._call(watcher.started)

        def onPlayBackStarted(self):  # noqa: N802
            self._call(watcher.stopped)  # a new item is loading: the old one's values go

        def onPlayBackStopped(self):  # noqa: N802
            self._call(watcher.stopped)

        def onPlayBackEnded(self):  # noqa: N802
            self._call(watcher.stopped)

        def onPlayBackError(self):  # noqa: N802
            self._call(watcher.stopped)

    return RatingsPlayer()


def data_directory(xbmcvfs) -> str:
    path = xbmcvfs.translatePath(DATA_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def key_reader(xbmcaddon):
    """Reads the key setting fresh each time (a new Addon object sees a changed setting)."""
    return lambda: xbmcaddon.Addon(ADDON_ID).getSettingString(KEY_SETTING)


def start(xbmc, xbmcgui, xbmcvfs, xbmcaddon):
    """The follower (started) and the player watcher, sharing one cache and quota."""
    cache = mdblist.Cache(os.path.join(data_directory(xbmcvfs), DATABASE))
    try:
        cache.prune(time.time())
    except Exception:  # noqa: BLE001 - a prune is housekeeping
        pass
    window = xbmcgui.Window(HOME_WINDOW)
    ratings = mdblist.Ratings(cache, key_source=lambda: "")
    follower = Follower(xbmc, ratings, window, key_reader(xbmcaddon), xbmcgui.getCurrentWindowId)
    ratings.key_source = follower.current_key
    ratings.log = follower.api_log
    follower.refresh_key(force=True)
    follower.start()
    watcher = PlayerRatings(xbmc, ratings, window, follower)
    return follower, watcher
