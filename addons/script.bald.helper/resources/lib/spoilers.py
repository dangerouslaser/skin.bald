"""Bald Helper's spoiler stills: frosted copies of unwatched episodes' thumbnails, one file per episode, for Bald's
spoiler protection (Bald Settings, Appearance, Information, "Hide spoilers for unwatched items").

Kodi's skin engine cannot blur an image, and a skin cannot name a file after a hash. It can build a texture path from
an item's database id, so this service keeps

    <cache>/<episode id>.jpg     a 320 x 180 copy of the episode's thumb, reduced to a 16 x 9 colour field and blurred

and Bald draws $INFO[Window(home).Property(Bald.Spoilers.Path)]$INFO[ListItem.DBID,,.jpg] over the tile of an
unwatched episode. Nothing is written to the video library: the stills live in this add-on's profile folder, and the
whole folder is deleted when the protection is turned off (see NOTES, "Spoiler protection").

"Unwatched" is Bald's rule: play count 0 and no resume point. A partly watched episode is shown as it is.

Which episodes, since a library can hold tens of thousands (all incremental, never a full backfill):
  - warm-up, when the protection turns on and after a library scan: the most recently added unwatched episodes and the
    next few of every TV show in progress (Home's Next up and Recently added rows);
  - follow: the TV show, season or episode the viewer settles on (the container Bald names in Bald.FocusContainer,
    as the blur follower reads it); a show gives its next unwatched episodes, a season or an episode the season's;
  - an episode marked unwatched again.
An episode that becomes watched loses its still (VideoLibrary.OnUpdate), and the folder is capped at MAX_FILES,
oldest first.

Home properties:
    Bald.Spoilers.Path   the folder, with a trailing separator, while the service keeps stills (Bald only draws the
                         layer while it is set). After a batch it switches between the special:// and the native
                         spelling of the same folder, so textures that failed while their still was missing are
                         looked up again (Kodi does not retry a failed texture until its path changes).

Nothing here imports xbmc at module level, so the tests drive it with stand-ins.
"""

from __future__ import annotations

import io
import json
import os
import threading
import time
from collections import deque

ADDON_ID = "script.bald.helper"
SKIN_ID = "skin.bald"
HOME_WINDOW = 10000

CACHE_DIR = "special://profile/addon_data/script.bald.helper/spoilers/"
INDEX = "index.json"
SIZE = (320, 180)
FIELD = (16, 9)  # the colour field the still is reduced to before the blur: no shape survives it
RADIUS = 14
QUALITY = 85
MAX_FILES = 6000  # about 40 MB

PROPERTY_PATH = "Bald.Spoilers.Path"

# The skin's Bald_SpoilerThumbsOn: Bald's own switch, or Kodi's "Show information for unwatched items" without
# "Episode thumb" (System.Setting(hideunwatchedepisodethumbs)).
ACTIVE = ("[Skin.HasSetting(Bald.Spoilers) + !Skin.HasSetting(Bald.Spoilers.ShowThumbs)]"
          " | System.Setting(hideunwatchedepisodethumbs)")
REST = "Window.IsActive(fullscreenvideo) | System.ScreenSaverActive"
# While a dialog other than the information dialog is over the window, keep the last scope (as the blur does).
HOLD = "System.HasActiveModalDialog + !Window.IsModalDialogTopmost(movieinformation)"
INFO_DIALOG = "Window.IsModalDialogTopmost(movieinformation)"
MEDIA_WINDOW = "Window.IsMedia"
FOCUS_CONTAINER = "Window({}).Property(Bald.FocusContainer)"
INFO_WINDOW = "movieinformation"

POLL_SECONDS = 0.4
IDLE_SECONDS = 1.0
SETTLE_SECONDS = 0.6       # a scope must stay focused this long before it is fetched
SCOPE_TTL_SECONDS = 900    # a scope done this recently is not fetched again (library changes forget them all)
REFRESH_GAP_SECONDS = 2.0  # at most one path switch this often

RECENT_LIMIT = 60
NEXT_UP_SHOWS = 25
NEXT_UP_EPISODES = 4
SHOW_LIMIT = 40
SEASON_LIMIT = 200

UNWATCHED = {"field": "playcount", "operator": "is", "value": "0"}
PROPERTIES = ["thumb", "playcount", "resume", "tvshowid", "season"]
LIBRARY_SCANS = frozenset(("VideoLibrary.OnScanFinished", "VideoLibrary.OnCleanFinished"))


def still_name(episode_id: int) -> str:
    return f"{int(episode_id)}.jpg"


def unwatched(episode: dict) -> bool:
    """Bald's rule: never played and not in progress."""
    if int(episode.get("playcount") or 0) > 0:
        return False
    resume = episode.get("resume") or {}
    return not float(resume.get("position") or 0) > 0


def scope_for(media_type: str, dbid: str, tvshow_id: str, season: str):
    """The library scope a focused item asks for: ("show", id), ("season", id, season), or None."""
    def number(text):
        text = (text or "").strip()
        return int(text) if text.lstrip("-").isdigit() else -1

    if media_type == "tvshow" and number(dbid) > 0:
        return ("show", number(dbid))
    if media_type in ("season", "episode") and number(tvshow_id) > 0 and number(season) >= 0:
        return ("season", number(tvshow_id), number(season))
    return None


def library_update(data: str):
    """(episode id, play count) from a VideoLibrary.OnUpdate notification about an episode's play count, else None."""
    try:
        payload = json.loads(data or "{}")
    except ValueError:
        return None
    item = payload.get("item") or {}
    if item.get("type") != "episode" or "playcount" not in payload:
        return None
    try:
        return int(item["id"]), int(payload["playcount"])
    except (KeyError, TypeError, ValueError):
        return None


def render(pil, data: bytes) -> bytes:
    """The frosted still for one thumbnail: cover-cropped to SIZE, reduced to FIELD and blurred back up."""
    Image, ImageFilter, ImageOps = pil
    with Image.open(io.BytesIO(data)) as image:
        image.draft("RGB", SIZE)  # JPEG: decode at the smallest scale that still covers SIZE
        image = image.convert("RGB")
    resampling = getattr(Image, "Resampling", Image)
    image = ImageOps.fit(image, SIZE, method=resampling.BILINEAR, centering=(0.5, 0.5))
    image = image.resize(FIELD, resampling.BOX).resize(SIZE, resampling.BICUBIC)
    image = image.filter(ImageFilter.GaussianBlur(RADIUS))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=QUALITY)
    return out.getvalue()


def _blur_module():
    """Bald Helper's blur module (for its image reader and the focus rules), however this module was loaded."""
    try:
        from resources.lib import blur  # noqa: PLC0415 - the service's package
        return blur
    except ImportError:
        import importlib.util  # noqa: PLC0415

        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blur.py")
        spec = importlib.util.spec_from_file_location("bald_helper_blur_for_spoilers", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class Stills:
    """The still files and their index (episode id -> the thumb they were made from)."""

    def __init__(self, folder: str, reader, log=None):
        self.folder = folder
        self.reader = reader  # .read(source) -> bytes | None and .pil() -> (Image, ImageFilter, ImageOps) | None
        self.log = log or (lambda text, level=None: None)
        self.lock = threading.Lock()
        self.index = None

    def path(self, episode_id: int) -> str:
        return os.path.join(self.folder, still_name(episode_id))

    def load(self) -> dict:
        if self.index is None:
            try:
                with open(os.path.join(self.folder, INDEX), encoding="utf-8") as handle:
                    self.index = {str(k): str(v) for k, v in json.load(handle).items()}
            except (OSError, ValueError, AttributeError):
                self.index = {}
        return self.index

    def save(self) -> None:
        with self.lock:
            index = dict(self.load())
        os.makedirs(self.folder, exist_ok=True)
        target = os.path.join(self.folder, INDEX)
        temporary = f"{target}.{os.getpid()}.{threading.get_ident()}.tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(index, handle)
        os.replace(temporary, target)

    def current(self, episode_id: int, source: str) -> bool:
        with self.lock:
            made_from = self.load().get(str(episode_id))
        return made_from == source and os.path.isfile(self.path(episode_id))

    def make(self, episode_id: int, source: str) -> bool:
        """Write the still for one episode. Returns whether a new file was written."""
        if not source or self.current(episode_id, source):
            return False
        pil = self.reader.pil()
        if pil is None:
            return False
        data = self.reader.read(source)
        if not data:
            self.log(f"cannot read {source}")
            return False
        still = render(pil, data)
        os.makedirs(self.folder, exist_ok=True)
        target = self.path(episode_id)
        temporary = f"{target}.{os.getpid()}.{threading.get_ident()}.tmp"
        with open(temporary, "wb") as handle:
            handle.write(still)
        os.replace(temporary, target)
        with self.lock:
            self.load()[str(episode_id)] = source
        return True

    def remove(self, episode_id: int) -> bool:
        with self.lock:
            known = self.load().pop(str(episode_id), None) is not None
        try:
            os.remove(self.path(episode_id))
            return True
        except OSError:
            return known

    def clear(self) -> int:
        """Delete every still, the index and leftovers; the folder too. Returns how many files went."""
        removed = 0
        try:
            names = os.listdir(self.folder)
        except OSError:
            names = []
        for name in names:
            try:
                os.remove(os.path.join(self.folder, name))
                removed += 1
            except OSError:
                pass
        try:
            os.rmdir(self.folder)
        except OSError:
            pass
        with self.lock:
            self.index = {}
        return removed

    def prune(self, max_files: int = MAX_FILES) -> int:
        """Delete the oldest stills beyond max_files, and leftover temporary files."""
        try:
            names = os.listdir(self.folder)
        except OSError:
            return 0
        stills, removed = [], 0
        for name in names:
            path = os.path.join(self.folder, name)
            if ".tmp" in name:
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass
            elif name.endswith(".jpg") and name[:-4].isdigit():
                try:
                    stills.append((os.stat(path).st_mtime, name[:-4]))
                except OSError:
                    pass
        stills.sort()
        for _, episode_id in stills[:max(0, len(stills) - max_files)]:
            if self.remove(int(episode_id)):
                removed += 1
        return removed


class Library:
    """The video library over JSON-RPC (xbmc.executeJSONRPC)."""

    def __init__(self, xbmc):
        self.xbmc = xbmc

    def call(self, method: str, params: dict) -> dict:
        request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        reply = json.loads(self.xbmc.executeJSONRPC(json.dumps(request)))
        if "error" in reply:
            raise RuntimeError(f"{method}: {reply['error'].get('message', reply['error'])}")
        return reply.get("result") or {}

    def episodes(self, params: dict) -> list:
        params = dict(params, properties=PROPERTIES)
        params.setdefault("filter", UNWATCHED)
        return [e for e in self.call("VideoLibrary.GetEpisodes", params).get("episodes") or [] if unwatched(e)]

    def recent(self) -> list:
        return self.episodes({"sort": {"method": "dateadded", "order": "descending"},
                              "limits": {"start": 0, "end": RECENT_LIMIT}})

    def next_up(self) -> list:
        shows = self.call("VideoLibrary.GetInProgressTVShows", {"limits": {"start": 0, "end": NEXT_UP_SHOWS}})
        found = []
        for show in shows.get("tvshows") or []:
            found += self.show(show["tvshowid"], NEXT_UP_EPISODES)
        return found

    def show(self, tvshow_id: int, limit: int = SHOW_LIMIT) -> list:
        return self.episodes({"tvshowid": int(tvshow_id), "sort": {"method": "episode", "order": "ascending"},
                              "limits": {"start": 0, "end": limit}})

    def season(self, tvshow_id: int, season: int) -> list:
        return self.episodes({"tvshowid": int(tvshow_id), "season": int(season),
                              "sort": {"method": "episode", "order": "ascending"},
                              "limits": {"start": 0, "end": SEASON_LIMIT}})

    def episode(self, episode_id: int) -> list:
        details = self.call("VideoLibrary.GetEpisodeDetails",
                            {"episodeid": int(episode_id), "properties": PROPERTIES}).get("episodedetails")
        return [details] if details and unwatched(details) else []


class Spoilers:
    """Keeps the stills for what the viewer is about to see, while Bald is the skin and the protection is on."""

    def __init__(self, xbmc, xbmcvfs, xbmcgui=None, stills: Stills | None = None, library: Library | None = None,
                 window=None, current_window=None, clock=time.monotonic, threaded: bool = True):
        self.xbmc = xbmc
        self.window = window if window is not None else xbmcgui.Window(HOME_WINDOW)
        self.current_window = current_window or xbmcgui.getCurrentWindowId
        self.clock = clock
        self.threaded = threaded
        self.special = CACHE_DIR
        folder = xbmcvfs.translatePath(CACHE_DIR)
        self.native = folder if folder.endswith(os.sep) else folder + os.sep
        if stills is None:
            blur = _blur_module()
            stills = Stills(self.native, blur.Blurrer(xbmc, xbmcvfs, cache_dir=self.native, log=self.log_once))
        self.stills = stills
        self.library = library or Library(xbmc)
        self.active = None       # unknown until the first tick
        self.cleared = False     # the folder was emptied since the protection was last on
        self.candidate = None    # the scope seen on the last tick
        self.since = 0.0
        self.done = {}           # scope -> when it was fetched
        self.jobs = deque()      # newest first
        self.condition = threading.Condition()
        self.dirty = False       # new stills since the path last switched
        self.switched = 0.0
        self.path = ""
        self._stop = threading.Event()
        self._threads = []
        self._logged = set()

    # --- logging ---
    def log(self, text: str, level=None) -> None:
        self.xbmc.log(f"{ADDON_ID}: spoilers: {text}", self.xbmc.LOGDEBUG if level is None else level)

    def log_once(self, text: str, level=None) -> None:
        if text in self._logged:
            return
        if len(self._logged) > 200:
            self._logged.clear()
        self._logged.add(text)
        self.log(text, getattr(self.xbmc, "LOGWARNING", None) if level is None else level)

    # --- the skin's property ---
    def publish(self, path: str) -> None:
        if path != self.path or self.window.getProperty(PROPERTY_PATH) != path:
            if path:
                self.window.setProperty(PROPERTY_PATH, path)
            else:
                self.window.clearProperty(PROPERTY_PATH)
            self.path = path

    def refresh(self) -> None:
        """Switch the folder's spelling once new stills exist, so textures that failed are looked up again."""
        now = self.clock()
        if not self.dirty or now - self.switched < REFRESH_GAP_SECONDS:
            return
        self.dirty = False
        self.switched = now
        self.publish(self.native if self.path == self.special else self.special)

    # --- turning on and off ---
    def wanted(self) -> bool:
        return self.xbmc.getSkinDir() == SKIN_ID and bool(self.xbmc.getCondVisibility(ACTIVE))

    def turn_on(self) -> None:
        self.active = True
        self.cleared = False
        self.publish(self.special)
        self.switched = self.clock()
        self.done.clear()
        self.enqueue(("warm",))
        self.log("on", self.xbmc.LOGINFO)

    def turn_off(self) -> None:
        if self.active is not False:
            self.active = False
            self.publish("")
            with self.condition:
                self.jobs.clear()
        # Reversible: under Bald with the protection off, nothing is left behind (once per switch-off, and at
        # startup). Another skin only pauses.
        if not self.cleared and self.xbmc.getSkinDir() == SKIN_ID:
            self.cleared = True
            removed = self.stills.clear()
            if removed:
                self.log(f"off: removed {removed} files", self.xbmc.LOGINFO)

    # --- polling (the poller thread) ---
    def focused_scope(self):
        if self.xbmc.getCondVisibility(HOLD):
            return self.candidate
        info = bool(self.xbmc.getCondVisibility(INFO_DIALOG))
        container = self.xbmc.getInfoLabel(FOCUS_CONTAINER.format(INFO_WINDOW if info else self.current_window()))
        container = container.strip()
        if container.isdigit():
            prefix = f"Container({container}).ListItem."
        elif info:
            prefix = "ListItem."
        elif self.xbmc.getCondVisibility(MEDIA_WINDOW):
            prefix = "Container.ListItem."
        else:
            return None
        label = self.xbmc.getInfoLabel
        return scope_for(label(prefix + "DBType"), label(prefix + "DBID"), label(prefix + "TvShowDBID"),
                         label(prefix + "Season"))

    def tick(self) -> float:
        if not self.wanted():
            self.turn_off()
            return IDLE_SECONDS
        if not self.active:
            self.turn_on()
        if self.stills.reader.pil() is None:
            self.publish("")
            return IDLE_SECONDS
        if not self.path:
            self.publish(self.special)
        self.refresh()
        if self.xbmc.getCondVisibility(REST):
            return IDLE_SECONDS
        scope = self.focused_scope()
        now = self.clock()
        if scope != self.candidate:
            self.candidate, self.since = scope, now
            return POLL_SECONDS
        if scope is None or now - self.since < SETTLE_SECONDS - 0.01:  # a timed wait may wake a hair early
            return POLL_SECONDS
        fetched = self.done.get(scope)
        if fetched is None or now - fetched > SCOPE_TTL_SECONDS:
            self.done[scope] = now
            self.enqueue(scope)
        return POLL_SECONDS

    # --- notifications (Kodi's monitor thread: hand over, nothing slow) ---
    def notify(self, sender: str, method: str, data: str = "") -> None:
        if method in LIBRARY_SCANS:
            self.done.clear()
            if self.active:
                self.enqueue(("warm",))
            return
        if method != "VideoLibrary.OnUpdate":
            return
        update = library_update(data)
        if update is None:
            return
        episode_id, playcount = update
        if playcount > 0:
            self.enqueue(("watched", episode_id))
        elif self.active:
            self.enqueue(("episode", episode_id))

    # --- work (the worker thread) ---
    def enqueue(self, job) -> None:
        with self.condition:
            if job in self.jobs:
                self.jobs.remove(job)
            self.jobs.appendleft(job)
            self.condition.notify()
        if not self.threaded:
            self.run_jobs()

    def episodes_for(self, job) -> list:
        kind = job[0]
        if kind == "warm":
            return self.library.next_up() + self.library.recent()
        if kind == "show":
            return self.library.show(job[1])
        if kind == "season":
            return self.library.season(job[1], job[2])
        if kind == "episode":
            return self.library.episode(job[1])
        return []

    def run(self, job) -> int:
        """One job. Returns how many stills were written."""
        if job[0] == "watched":
            if self.stills.remove(job[1]):
                self.stills.save()
            return 0
        if not self.active:
            return 0
        made = 0
        for episode in self.episodes_for(job):
            if self._stop.is_set() or not self.active:
                break
            try:
                if self.stills.make(int(episode["episodeid"]), episode.get("thumb") or ""):
                    made += 1
            except Exception as error:  # noqa: BLE001 - one bad image must not end the batch
                self.log_once(f"{type(error).__name__}: {error}")
        if made:
            self.stills.save()
            if self.stills.prune():
                self.stills.save()
            self.dirty = True
            self.log(f"{job}: {made} stills")
        return made

    def run_jobs(self) -> None:
        while not self._stop.is_set():
            with self.condition:
                if not self.jobs:
                    return
                job = self.jobs.popleft()
            try:
                self.run(job)
            except Exception as error:  # noqa: BLE001 - the worker outlives any single failure
                self.log_once(f"{job[0]}: {type(error).__name__}: {error}")

    def _worker(self) -> None:
        while not self._stop.is_set():
            with self.condition:
                while not self.jobs and not self._stop.is_set():
                    self.condition.wait(1.0)
            self.run_jobs()

    def _poller(self, monitor) -> None:
        wait = POLL_SECONDS
        while not self._stop.is_set() and not monitor.abortRequested():
            try:
                wait = self.tick()
            except Exception as error:  # noqa: BLE001
                self.log_once(f"{type(error).__name__}: {error}")
                wait = IDLE_SECONDS
            if self._stop.wait(wait):
                break

    def start(self, monitor=None) -> None:
        monitor = monitor or self.xbmc.Monitor()
        for target, args in ((self._worker, ()), (self._poller, (monitor,))):
            thread = threading.Thread(target=target, args=args, name=f"{ADDON_ID}.spoilers", daemon=True)
            thread.start()
            self._threads.append(thread)
        self.log("started")

    def stop(self) -> None:
        self._stop.set()
        with self.condition:
            self.condition.notify_all()
        for thread in self._threads:
            thread.join(2.0)
        self._threads = []
        try:
            self.window.clearProperty(PROPERTY_PATH)
        except Exception:  # noqa: BLE001 - shutting down
            pass
        self.log("stopped")


def make_monitor(xbmc, spoilers: Spoilers):
    """An xbmc.Monitor for the library notifications. Kodi runs onNotification on the thread that made the monitor,
    while that thread waits in waitForAbort, so create it on the thread that runs the service loop."""

    class SpoilerMonitor(xbmc.Monitor):
        def onNotification(self, sender, method, data):  # noqa: N802 - Kodi's name
            try:
                spoilers.notify(sender, method, data)
            except Exception as error:  # noqa: BLE001 - never raise into Kodi's callback
                spoilers.log_once(f"notification: {type(error).__name__}: {error}")

    return SpoilerMonitor()
