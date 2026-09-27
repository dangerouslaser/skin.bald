"""Bald Helper's blurred backdrops: follow the item Bald's background shows, blur its fanart and publish the file.

The skin names the container to follow in the Bald.FocusContainer property of the active window, or of the information
dialog while it is open (the include Bald_FollowContainer sets it where it also sets TMDb Helper's widget container).
Without one, the follower uses the
focused item of a media window (Container.ListItem) or the information dialog's own item (ListItem). Its fanart, else
the show's fanart, else its thumb, is cut to 480 x 270, blurred and written once to this add-on's cache; the path goes
to Home's window properties:

    Bald.Blur       the current blurred file; empty for an item without art or where there is nothing to follow
    Bald.Blur.Last  the last non-empty Bald.Blur (for windows without an item of their own)
    Bald.Blur.For   the source image Bald.Blur was made from; written last

It works only while Bald is the skin and its blur is on, and rests during fullscreen video and the screensaver.
A source whose blur is already cached is published once it has stayed the same for FAST_SETTLE_SECONDS, even while
its container scrolls (switching to a known image costs one file check). Anything else waits until the source has
stayed the same for SETTLE_SECONDS and its container is not scrolling, so fast scrolling makes no work; it is then
blurred on one worker thread and published only if it is still the current source. Pillow (script.module.pil) is imported only when first needed; without it nothing is
published and the skin keeps its plain field.

Written from Pillow's documentation and Kodi's Python API. Nothing here imports xbmc at module level, so the tests
drive it with stand-ins.
"""

from __future__ import annotations

import hashlib
import io
import os
import threading
import time
from urllib.parse import unquote

ADDON_ID = "script.bald.helper"
SKIN_ID = "skin.bald"
HOME_WINDOW = 10000

# Output: a cover-cropped 480 x 270 copy (a quarter of 1080p, drawn stretched to 1920 x 1080) blurred at RADIUS.
SIZE = (480, 270)
RADIUS = 40
QUALITY = 90
CACHE_DIR = "special://profile/addon_data/script.bald.helper/blur"
CACHE_MAX_BYTES = 60 * 1024 * 1024
CACHE_MAX_FILES = 3000
PRUNE_EVERY = 100  # writes between prunes (the cache is also pruned at startup)

POLL_SECONDS = 0.15
IDLE_SECONDS = 1.0  # while resting: another skin, blur off, fullscreen video, screensaver
SETTLE_SECONDS = 0.25
FAST_SETTLE_SECONDS = 0.1  # a cached blur: only this long, and scrolling does not hold it back

PROPERTY_BLUR = "Bald.Blur"
PROPERTY_LAST = "Bald.Blur.Last"
PROPERTY_FOR = "Bald.Blur.For"

# One condition per tick decides whether to rest. Bald.DisableBlur is Appearance's "Blurred background" switch.
REST = "Skin.HasSetting(Bald.DisableBlur) | Window.IsActive(fullscreenvideo) | System.ScreenSaverActive"
# A modal dialog other than the information dialog (context menu, select, keyboard, busy) is over the window: keep
# what is shown. Container(id) and ListItem resolve in the topmost modal dialog first, then the active window, so
# with nothing else modal on top they read the information dialog or the window below.
HOLD = "System.HasActiveModalDialog + !Window.IsModalDialogTopmost(movieinformation)"
INFO_DIALOG = "Window.IsModalDialogTopmost(movieinformation)"
MEDIA_WINDOW = "Window.IsMedia"
# The container to follow, read from a named window: the information dialog, else the active window (by id, as
# xbmcgui.getCurrentWindowId gives it; Global Search is a script window with an id of its own).
FOCUS_CONTAINER = "Window({}).Property(Bald.FocusContainer)"
INFO_WINDOW = "movieinformation"
ART = ("Art(fanart)", "Art(tvshow.fanart)", "Art(thumb)")

THUMBNAILS = "special://thumbnails/"
THUMB_EXTENSIONS = (".jpg", ".png")


def cache_name(source: str, radius: int = RADIUS) -> str:
    """The blur's file name: the source's md5 and the radius, so a new radius never reuses an old file."""
    return f"{hashlib.md5(source.encode('utf-8')).hexdigest()}-r{radius}.jpg"


def unwrap(source: str) -> tuple[str, bool]:
    """(path, readable): image://<url-encoded path>/ gives the path. A typed wrapper (image://video@...,
    image://music@...) names an image Kodi generates, which only its thumbnail cache holds."""
    if not source.startswith("image://"):
        return source, True
    inner = source[len("image://"):]
    if "/?" in inner:
        inner = inner.split("/?", 1)[0] + "/"
    inner = inner[:-1] if inner.endswith("/") else inner
    kind, at, rest = inner.partition("@")
    if at and "%" not in kind and "/" not in kind:
        return unquote(rest), False
    return unquote(inner), True


def follow_prefix(container_id: str, info_dialog: bool, media_window: bool) -> tuple[str | None, str | None]:
    """The infolabel prefix of the item to follow and its scrolling condition; (None, None) for nothing to follow."""
    container_id = container_id.strip()
    if container_id.isdigit():
        return f"Container({container_id}).ListItem.", f"Container({container_id}).Scrolling"
    if info_dialog:
        return "ListItem.", None
    if media_window:
        return "Container.ListItem.", "Container.Scrolling"
    return None, None


class Blurrer:
    """Finds a source image, blurs it and keeps the results in a size-capped cache."""

    def __init__(self, xbmc, xbmcvfs, cache_dir: str | None = None, thumbnails: str | None = None, log=None):
        self.xbmc = xbmc
        self.xbmcvfs = xbmcvfs
        self.cache_dir = cache_dir or xbmcvfs.translatePath(CACHE_DIR)
        self.thumbnails = thumbnails if thumbnails is not None else xbmcvfs.translatePath(THUMBNAILS)
        self.log = log or (lambda text, level=None: None)
        self.writes = 0
        self._pil = None
        self._pil_failed = False

    # --- Pillow, imported lazily ---
    def pil(self):
        if self._pil is None and not self._pil_failed:
            try:
                from PIL import Image, ImageFilter, ImageOps  # noqa: PLC0415 - optional until first used

                self._pil = (Image, ImageFilter, ImageOps)
            except Exception as error:  # noqa: BLE001 - any import failure means no blur
                self._pil_failed = True
                self.log(f"Pillow unavailable, no blurred backgrounds: {type(error).__name__}: {error}")
        return self._pil

    def available(self) -> bool:
        return self.pil() is not None

    # --- the cache ---
    def path_for(self, source: str) -> str:
        return os.path.join(self.cache_dir, cache_name(source))

    def has(self, source: str) -> bool:
        """Whether the source's blur is in the cache (one stat; does not count as use)."""
        return os.path.isfile(self.path_for(source))

    def cached(self, source: str) -> str | None:
        path = self.path_for(source)
        try:
            os.utime(path)  # most recently used: pruning removes the oldest first
        except OSError:
            return None
        return path

    def prune(self, max_bytes: int = CACHE_MAX_BYTES, max_files: int = CACHE_MAX_FILES) -> int:
        """Delete the least recently used blurs until the cache fits both limits, and leftover temporary files.
        Returns how many files were removed."""
        try:
            names = os.listdir(self.cache_dir)
        except FileNotFoundError:
            return 0
        entries, removed = [], 0
        for name in names:
            path = os.path.join(self.cache_dir, name)
            if ".tmp" in name:
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass
                continue
            if not name.endswith(".jpg"):
                continue
            try:
                stat = os.stat(path)
            except OSError:
                continue
            entries.append((stat.st_mtime, stat.st_size, path))
        entries.sort()
        total = sum(size for _, size, _ in entries)
        count = len(entries)
        for _, size, path in entries:
            if total <= max_bytes and count <= max_files:
                break
            try:
                os.remove(path)
            except OSError:
                continue
            total -= size
            count -= 1
            removed += 1
        return removed

    # --- reading the source ---
    def thumbnail_candidates(self, source: str) -> list[str]:
        """Kodi's texture cache keeps each image it has shown at special://thumbnails/<c>/<crc>.jpg or .png, the crc
        taken from the lower-cased image path (unwrapped from image://), as xbmc.getCacheThumbName computes it."""
        if not self.thumbnails:
            return []
        path, _ = unwrap(source)
        keys = [path] + ([source] if source != path else [])
        found = []
        for key in keys:
            name = self.xbmc.getCacheThumbName(key)
            name = name[:-4] if name.endswith(".tbn") else name
            if not name:
                continue
            for extension in THUMB_EXTENSIONS:
                found.append(os.path.join(self.thumbnails, name[0], name + extension))
        return found

    def read(self, source: str) -> bytes | None:
        for candidate in self.thumbnail_candidates(source):
            try:
                with open(candidate, "rb") as handle:
                    data = handle.read()
            except OSError:
                continue
            if data:
                return data
        path, readable = unwrap(source)
        if not readable or not path:
            return None
        handle = self.xbmcvfs.File(path)
        try:
            data = handle.readBytes()
        finally:
            handle.close()
        return bytes(data) if data else None

    # --- blurring ---
    def render(self, data: bytes) -> bytes:
        """The blurred JPEG for one source image (pure, apart from Pillow)."""
        Image, ImageFilter, ImageOps = self.pil()
        with Image.open(io.BytesIO(data)) as image:
            # JPEG: decode at the smallest DCT scale that still covers SIZE (a 1920 x 1080 source decodes at 480 x 270).
            image.draft("RGB", SIZE)
            image = image.convert("RGB")
        resample = getattr(getattr(Image, "Resampling", Image), "BILINEAR")
        image = ImageOps.fit(image, SIZE, method=resample, centering=(0.5, 0.5))
        image = image.filter(ImageFilter.GaussianBlur(RADIUS))
        out = io.BytesIO()
        image.save(out, "JPEG", quality=QUALITY, subsampling=0)
        return out.getvalue()

    def make(self, source: str) -> str | None:
        """The blur's path, made and cached now if needed; None when the source cannot be read."""
        hit = self.cached(source)
        if hit:
            return hit
        if not self.available():
            return None
        data = self.read(source)
        if not data:
            self.log(f"cannot read {source}", getattr(self.xbmc, "LOGWARNING", None))
            return None
        blurred = self.render(data)
        os.makedirs(self.cache_dir, exist_ok=True)
        path = self.path_for(source)
        temporary = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
        with open(temporary, "wb") as handle:
            handle.write(blurred)
        os.replace(temporary, path)
        self.writes += 1
        if self.writes % PRUNE_EVERY == 0:
            self.prune()
        return path


class Follower:
    """Polls the item Bald's background shows and publishes its blur (see the module docstring)."""

    def __init__(self, xbmc, xbmcvfs, xbmcgui=None, blurrer: Blurrer | None = None, window=None,
                 clock=time.monotonic, threaded: bool = True, current_window=None):
        self.xbmc = xbmc
        self.window = window if window is not None else xbmcgui.Window(HOME_WINDOW)
        self.current_window = current_window or xbmcgui.getCurrentWindowId
        self.clock = clock
        self.threaded = threaded
        self._logged = set()
        self.blurrer = blurrer or Blurrer(xbmc, xbmcvfs)
        self.blurrer.log = self.log_once
        self.lock = threading.Lock()
        self.candidate = None   # the source seen on the last tick
        self.since = 0.0        # when it was first seen
        self.published = None   # the source Bald.Blur was last published for
        self.wanted = None      # the source being blurred on the worker
        self._job = None
        self._job_ready = threading.Condition()
        self._stop = threading.Event()
        self._threads = []

    # --- logging ---
    def log(self, text: str, level=None) -> None:
        self.xbmc.log(f"{ADDON_ID}: blur: {text}", self.xbmc.LOGDEBUG if level is None else level)

    def log_once(self, text: str, level=None) -> None:
        """Each distinct problem once per session (bounded, so a long session cannot grow it without limit)."""
        if text in self._logged:
            return
        if len(self._logged) > 200:
            self._logged.clear()
        self._logged.add(text)
        self.log(text, self.xbmc.LOGERROR if level is None else level)

    # --- reading Kodi ---
    def resting(self) -> bool:
        if self.xbmc.getSkinDir() != SKIN_ID:
            self.published = None  # republish when Bald is back
            return True
        return bool(self.xbmc.getCondVisibility(REST))

    def source(self) -> tuple[str | None, str | None]:
        """(source, scrolling condition) for this tick; source is None to keep what is shown, '' for no art."""
        if self.xbmc.getCondVisibility(HOLD):
            return None, None
        info = bool(self.xbmc.getCondVisibility(INFO_DIALOG))
        container_id = self.xbmc.getInfoLabel(FOCUS_CONTAINER.format(INFO_WINDOW if info else self.current_window()))
        media = False
        if not info and not container_id.strip().isdigit():
            media = bool(self.xbmc.getCondVisibility(MEDIA_WINDOW))
        prefix, scrolling = follow_prefix(container_id, info, media)
        if prefix is None:
            return "", None
        for art in ART:
            value = self.xbmc.getInfoLabel(prefix + art)
            if value:
                return value, scrolling
        return "", scrolling

    # --- publishing ---
    def publish(self, source: str, blur: str) -> None:
        self.window.setProperty(PROPERTY_BLUR, blur)
        if blur:
            self.window.setProperty(PROPERTY_LAST, blur)
        self.window.setProperty(PROPERTY_FOR, source)
        self.published = source

    def tick(self) -> float:
        """One poll. Returns how long to wait before the next."""
        if self.resting():
            self.candidate = None
            return IDLE_SECONDS
        if not self.blurrer.available():
            return IDLE_SECONDS
        source, scrolling = self.source()
        if source is None:
            return POLL_SECONDS
        now = self.clock()
        if source != self.candidate:
            self.candidate, self.since = source, now
            return FAST_SETTLE_SECONDS  # look again as soon as a cached blur could be shown
        with self.lock:
            if source == self.wanted:
                return POLL_SECONDS
            if source == self.published:
                self.wanted = None  # back on the shown item: a blur still in flight is no longer wanted
                return POLL_SECONDS
        elapsed = now - self.since
        if elapsed < FAST_SETTLE_SECONDS - 0.01:  # a timed wait may wake a hair early
            return POLL_SECONDS
        if source and self.blurrer.has(source):
            self.request(source)  # cached: publish now, scrolling or not
            return POLL_SECONDS
        if elapsed < SETTLE_SECONDS:
            return POLL_SECONDS
        if scrolling and self.xbmc.getCondVisibility(scrolling):
            return POLL_SECONDS
        self.request(source)
        return POLL_SECONDS

    def request(self, source: str) -> None:
        if not source:
            with self.lock:
                self.wanted = None
                self.publish("", "")
            return
        hit = self.blurrer.cached(source)
        if hit:
            with self.lock:
                self.wanted = None
                self.publish(source, hit)
            return
        with self.lock:
            self.wanted = source
        if not self.threaded:
            self.work(source)
            return
        with self._job_ready:
            self._job = source
            self._job_ready.notify()

    def work(self, source: str) -> None:
        """Blur one source (on the worker) and publish it if it is still the one wanted."""
        try:
            path = self.blurrer.make(source)
        except Exception as error:  # noqa: BLE001 - a bad image must not end the worker
            self.log_once(f"{type(error).__name__}: {error}")
            path = None
        with self.lock:
            if self.wanted != source:
                return  # stale: the viewer has moved on
            self.wanted = None
            if path is None and not self.blurrer.available():
                return  # no Pillow: publish nothing
            self.publish(source, path or "")

    # --- threads ---
    def _worker(self) -> None:
        while not self._stop.is_set():
            with self._job_ready:
                while self._job is None and not self._stop.is_set():
                    self._job_ready.wait(1.0)
                source, self._job = self._job, None
            if source is not None and not self._stop.is_set():
                self.work(source)

    def _poller(self, monitor) -> None:
        try:
            self.blurrer.prune()
        except Exception as error:  # noqa: BLE001
            self.log_once(f"prune: {type(error).__name__}: {error}")
        wait = POLL_SECONDS
        while not self._stop.is_set() and not monitor.abortRequested():
            try:
                wait = self.tick()
            except Exception as error:  # noqa: BLE001 - the follower outlives any single failure
                self.log_once(f"{type(error).__name__}: {error}")
                wait = IDLE_SECONDS
            if self._stop.wait(wait):
                break

    def start(self, monitor=None) -> None:
        monitor = monitor or self.xbmc.Monitor()
        for target, args in ((self._worker, ()), (self._poller, (monitor,))):
            thread = threading.Thread(target=target, args=args, name=f"{ADDON_ID}.blur", daemon=True)
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
        self.log("stopped")
