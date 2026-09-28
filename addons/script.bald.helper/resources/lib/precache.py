"""Bald Helper's art pre-caching: get the fanart Bald is about to show into Kodi's texture cache before it is shown, so
a remote backdrop (a Jellyfin or Emby server, a plugin's http art) does not arrive late and pop in the first time.

How: Kodi's VFS serves image://<url-encoded path>/ through CImageFile (xbmc/filesystem/ImageFile.cpp), whose Open()
looks the image up in the texture cache (CTextureCache::CheckCachedImage) and, when it is missing, caches it there and
then (CTextureCache::CacheImage: download, scale, write userdata/Thumbnails/<c>/<crc>.jpg and the Textures13.db row).
So opening xbmcvfs.File("image://.../") is the same caching the GUI does on first display, under the same cache key
(the unwrapped path), without drawing anything and without Kodi's web server. xbmcvfs.File releases the Python lock
while Kodi opens it, so a slow server holds up only this thread.

What, in order, at most BATCH per pass (see plan()):
    - the item Bald shows and its neighbours: on Home the current row (Window(home).Property(Bald.Row)), elsewhere the
      container follow.py locates (a library view's Bald.FocusContainer, or a media window's focused list); the focused
      item, then 1 ahead, 1 behind, 2 ahead, 2 behind, 3 ahead, 3 behind
    - while Home's ambient mode runs (idle: focus parked on the wake button 9199), the next AMBIENT_AHEAD items of the
      current row instead, since the row advances by itself
    - on Home, every other row of the screen: its selected item and the one after it
Each item's art is its fanart, else the show's fanart, else its thumb (the order the blur uses).

Skipped: art with no network behind it (local files, special://, resource://, Kodi-generated image://video@...
pictures), art already in the texture cache (one stat of its Thumbnails file), and art asked for already this session
(a bounded LRU; a failure is tried again after RETRY_SECONDS). One image at a time, at most one every PAUSE_SECONDS,
only while Bald is the skin, never during fullscreen video or the screensaver. Logs never carry credentials or query
strings (a Jellyfin URL may carry api_key).

Nothing here imports xbmc at module level, so the tests drive it with stand-ins.
"""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from urllib.parse import quote, urlsplit

from . import common, follow
from .blur import ART, THUMB_EXTENSIONS, THUMBNAILS, WARM_BASES, WARM_MAX_ROWS, unwrap
from .common import ADDON_ID, SKIN_ID

REST = "Window.IsActive(fullscreenvideo) | System.ScreenSaverActive"
HOME = "Window.IsActive(home)"
# Ambient mode (1080i/Timers.xml bald_ambient): Home idle, focus on the wake button, the row advancing every 8 s.
AMBIENT = "Window.IsActive(home) + Control.HasFocus(9199) + !Skin.HasSetting(Bald.AmbientOff)"
ROW = "Window(home).Property(Bald.Row)"

AROUND = 3          # neighbours each side of the focused item
AMBIENT_AHEAD = 8   # items ahead of the current row's item in ambient mode
OTHER_ROW_ITEMS = 2  # each other row of the screen: its selected item and the next
BATCH = 20          # images per pass, at most
PAUSE_SECONDS = 0.25  # between two requests: at most 4 images a second
POLL_SECONDS = 0.5  # how often to look whether the viewer has moved
IDLE_SECONDS = 1.0  # while resting
RESCAN_SECONDS = 10.0  # look again even without a move (rows still loading, new items)
RETRY_SECONDS = 1800.0  # a failed image is asked for again after this long
REMEMBER = 512      # images remembered as asked for (LRU)

# Where the texture cache's work is worth it: art behind a network. Everything else is local already.
REMOTE_SCHEMES = ("http", "https", "smb", "nfs", "ftp", "ftps", "sftp", "dav", "davs", "upnp")


def cache_key(source: str) -> str | None:
    """The texture cache's key for a piece of art (the unwrapped path), or None when it has nothing to fetch: a
    Kodi-generated image (image://video@...), or a path without a network scheme."""
    path, readable = unwrap(source)
    if not readable or "://" not in path:
        return None
    if path.split("://", 1)[0].lower() not in REMOTE_SCHEMES:
        return None
    return path


def image_url(key: str) -> str:
    """The image:// VFS path Kodi caches on open (CImageFile), as CImageFileURL::ToString writes it."""
    return f"image://{quote(key, safe='')}/"


def redact(source: str) -> str:
    """Art fit for the log: scheme, host and path only; no user, password, query string or fragment."""
    path, _ = unwrap(source)
    try:
        parts = urlsplit(path)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return common.log_safe(path.split("?", 1)[0])
    if not parts.scheme or not host:
        return common.log_safe(path.split("?", 1)[0])
    return f"{parts.scheme}://{host}{port}{parts.path}" + ("?..." if parts.query else "")


def server(key: str) -> str:
    """The scheme and host of a key (what a failure is logged once per)."""
    try:
        parts = urlsplit(key)
        return f"{parts.scheme}://{parts.hostname or ''}"
    except ValueError:
        return "?"


class Precacher:
    """Keeps the upcoming fanart in Kodi's texture cache (see the module docstring), on its own daemon thread."""

    NAME = "precache"

    def __init__(self, xbmc, xbmcvfs, xbmcgui=None, clock=time.monotonic, thumbnails: str | None = None,
                 current_window=None):
        self.xbmc = xbmc
        self.xbmcvfs = xbmcvfs
        self.clock = clock
        self.thumbnails = thumbnails if thumbnails is not None else xbmcvfs.translatePath(THUMBNAILS)
        self.current_window = current_window or xbmcgui.getCurrentWindowId
        self.queue: list[str] = []
        self.asked: OrderedDict[str, tuple[bool, float]] = OrderedDict()  # key -> (cached, when)
        self.signature = None
        self.next_scan = 0.0
        self._logged: set[str] = set()
        self._stop = threading.Event()
        self._thread = None

    # --- logging ---
    def log(self, text: str, level=None) -> None:
        self.xbmc.log(f"{ADDON_ID}: {self.NAME}: {text}", self.xbmc.LOGDEBUG if level is None else level)

    def log_once(self, text: str, level=None, cause: str | None = None) -> None:
        """Each cause (by default the text itself) once per session; bounded."""
        cause = text if cause is None else cause
        if cause in self._logged:
            return
        if len(self._logged) > 200:
            self._logged.clear()
        self._logged.add(cause)
        self.log(text, getattr(self.xbmc, "LOGWARNING", None) if level is None else level)

    # --- reading Kodi ---
    def resting(self) -> bool:
        return self.xbmc.getSkinDir() != SKIN_ID or bool(self.xbmc.getCondVisibility(REST))

    def focus(self) -> str | None:
        """The container whose items come first, as an infolabel prefix ("Container(9101)." or "Container."), or None."""
        if self.xbmc.getCondVisibility(HOME):
            row = self.xbmc.getInfoLabel(ROW).strip()
            if row.isdigit():
                return f"Container({row})."
        located = follow.locate(self.xbmc, self.current_window)
        if located is follow.HELD:
            return None
        prefix, _ = located
        if prefix and prefix.startswith("Container") and prefix.endswith("ListItem."):
            return prefix[:-len("ListItem.")]
        return None  # nothing to follow, or the information dialog's own item (no neighbours)

    def moved(self, container: str | None, ambient: bool) -> tuple:
        """What, if it changes, calls for a new plan: the container, its position and size, and ambient mode."""
        if container is None:
            return (None, ambient)
        return (container, self.xbmc.getInfoLabel(container + "CurrentItem"),
                self.xbmc.getInfoLabel(container + "NumItems"), ambient)

    def art(self, prefix: str) -> str:
        for name in ART:
            value = self.xbmc.getInfoLabel(prefix + name)
            if value and ("/" in value or "\\" in value):  # a bare name (DefaultVideo.png) is a skin icon
                return value
        return ""

    @staticmethod
    def item(container: str, offset: int) -> str:
        return f"{container}ListItem." if offset == 0 else f"{container}ListItemNoWrap({offset})."

    @staticmethod
    def offsets(ambient: bool) -> list[int]:
        if ambient:
            return [0, *range(1, AMBIENT_AHEAD + 1), -1]
        order = [0]
        for step in range(1, AROUND + 1):
            order += [step, -step]
        return order

    @staticmethod
    def other_rows(container: str) -> list[int]:
        """The ids of the other rows on a Home screen (1080i/IDs: base + 1 onward, numbered without gaps)."""
        digits = container[len("Container("):-len(").")] if container.startswith("Container(") else ""
        if not digits.isdigit():
            return []
        row = int(digits)
        base = (row - 1) // 50 * 50
        if base not in WARM_BASES:
            return []
        return [other for other in range(base + 1, base + WARM_MAX_ROWS + 1) if other != row]

    def cached(self, key: str) -> bool:
        """Whether Kodi's texture cache holds the image: special://thumbnails/<c>/<crc>.jpg or .png, the crc of the
        lower-cased key as xbmc.getCacheThumbName computes it (CTextureCache::GetCacheFile)."""
        if not self.thumbnails:
            return False
        name = self.xbmc.getCacheThumbName(key)
        name = name[:-4] if name.endswith(".tbn") else name
        if not name:
            return False
        return any(os.path.isfile(os.path.join(self.thumbnails, name[0], name + extension))
                   for extension in THUMB_EXTENSIONS)

    def wanted(self, source: str, now: float) -> str | None:
        """The cache key to fetch for a piece of art, or None to skip it."""
        key = cache_key(source)
        if key is None:
            return None
        seen = self.asked.get(key)
        if seen is not None and (seen[0] or now - seen[1] < RETRY_SECONDS):
            return None
        if self.cached(key):
            self.remember(key, True, now)
            return None
        return key

    def plan(self, container: str | None, ambient: bool) -> list[str]:
        """The keys to fetch now, nearest first, at most BATCH."""
        if container is None:
            return []
        now = self.clock()
        prefixes = [self.item(container, offset) for offset in self.offsets(ambient)]
        for row in self.other_rows(container):
            count = self.xbmc.getInfoLabel(f"Container({row}).NumItems")
            if not count:
                break  # no such row
            if count != "0":
                prefixes += [self.item(f"Container({row}).", offset) for offset in range(OTHER_ROW_ITEMS)]
        found: list[str] = []
        for prefix in prefixes:
            source = self.art(prefix)
            key = self.wanted(source, now) if source else None
            if key and key not in found:
                found.append(key)
                if len(found) >= BATCH:
                    break
        return found

    # --- fetching ---
    def remember(self, key: str, cached: bool, now: float) -> None:
        self.asked[key] = (cached, now)
        self.asked.move_to_end(key)
        while len(self.asked) > REMEMBER:
            self.asked.popitem(last=False)

    def fetch(self, key: str) -> bool:
        """Have Kodi cache one image (see the module docstring); True when it is in the cache afterwards."""
        size = 0
        try:
            handle = self.xbmcvfs.File(image_url(key))
            try:
                size = handle.size()
            finally:
                handle.close()
        except Exception as error:  # noqa: BLE001 - one bad image must not end the thread
            self.log_once(f"cannot cache art from {server(key)}: {type(error).__name__}",
                          cause=f"{server(key)} {type(error).__name__}")
        ok = bool(size and size > 0)
        self.remember(key, ok, self.clock())
        if ok:
            self.log(f"cached {redact(key)}")
        else:
            self.log_once(f"cannot cache art from {server(key)} (first: {redact(key)})", cause=server(key))
        return ok

    # --- the loop ---
    def step(self) -> float:
        """One unit of work. Returns how long to wait before the next."""
        if self.resting():
            self.queue = []
            self.signature = None
            return IDLE_SECONDS
        ambient = bool(self.xbmc.getCondVisibility(AMBIENT))
        container = self.focus()
        signature = self.moved(container, ambient)
        now = self.clock()
        # Nothing to follow (a dialog holds the item, the information dialog, a window without a list): the queue
        # stands, as what it holds is still what comes next.
        if container is not None and (signature != self.signature or now >= self.next_scan):
            self.queue = self.plan(container, ambient)
            if self.queue:
                self.log(f"precaching {len(self.queue)} images")
            self.signature = signature
            self.next_scan = now + RESCAN_SECONDS
        if not self.queue:
            return POLL_SECONDS
        self.fetch(self.queue.pop(0))
        return PAUSE_SECONDS

    def _run(self, monitor) -> None:
        while not self._stop.is_set() and not monitor.abortRequested():
            try:
                wait = self.step()
            except Exception as error:  # noqa: BLE001 - the pre-cache outlives any single failure
                # The message cut at any query string, in case it quotes a URL with a token.
                self.log_once(f"{type(error).__name__}: {common.log_safe(str(error)).split('?', 1)[0]}")
                wait = RESCAN_SECONDS
            if self._stop.wait(wait):
                break

    def start(self, monitor=None) -> None:
        monitor = monitor or self.xbmc.Monitor()
        self._thread = threading.Thread(target=self._run, args=(monitor,), name=f"{ADDON_ID}.{self.NAME}",
                                        daemon=True)
        self._thread.start()
        self.log("started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(2.0)
        self._thread = None
        self.log("stopped")
