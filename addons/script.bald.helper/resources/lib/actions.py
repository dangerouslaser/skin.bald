"""Bald Helper's skin actions: the info page, episode play, More like this, the Series page line and the letter bar,
run in this resident service instead of a new Python interpreter per RunScript.

The skin signals with Kodi's NotifyAll builtin. NotifyAll(sender,data) announces data as an "Other" notification,
which reaches every xbmc.Monitor as onNotification(sender, "Other.<data>", "null"). Bald sends

    NotifyAll(skin.bald,bald.<action>|<type>|<id>)

with only safe values (a library type, a database id or a view id; never a title or a path). Actions:

    bald.info|<type>|<id>       DialogVideoInfo onload: recommendations and, for TV items, tvinfo (info.handle)
    bald.play|episode|<id>      episode Select on the info page and the Series page
    bald.open|<type>|<id>       More like this: swap the info dialog
    bald.seriesmeta             Series page header line (view 532)
    bald.letters|<view id>      the letter bar's available groups

The work itself is the skin's own scripts/info.py and scripts/letters.py, loaded from the installed skin, so the
RunScript fallback and this service run the same code. The skin uses this path only while Home's property
Bald.Helper.Actions is PROTOCOL, which the service sets once it has loaded those scripts and clears when it stops;
otherwise it keeps RunScript.

One worker runs the requests. The latest wins: a request that has not started yet is replaced by a newer one, and a
running one is told through its `cancelled` check, which ends its waits early. Letter scans are cached per view,
folder, size and sort, and the cache is dropped whenever the video library changes.

Nothing here imports xbmc at module level, so the tests drive it with stand-ins.
"""

from __future__ import annotations

import importlib.util
import os
import re
import threading
import time
from collections import OrderedDict, namedtuple

ADDON_ID = "script.bald.helper"
SKIN_ID = "skin.bald"
HOME_WINDOW = 10000

SENDER = SKIN_ID
PREFIX = "Other.bald."
PROTOCOL = "1"
PROPERTY_READY = "Bald.Helper.Actions"
PROPERTY_LAST = "Bald.Helper.Last"  # "<action>|<type>|<id>|<ms>" of the last finished request (for live checks)
# The skin API this service needs from scripts/info.py (info.SERVICE_API).
SERVICE_API = 1

# The main thread's wait slice: Kodi delivers onNotification to it between slices (xbmc.Monitor.waitForAbort runs
# pending callbacks at most every 100 ms), so this bounds the added latency.
WAKE_SECONDS = 0.05

# Any of these drops the letter cache.
LIBRARY_CHANGES = frozenset((
    "VideoLibrary.OnUpdate", "VideoLibrary.OnRemove", "VideoLibrary.OnScanFinished",
    "VideoLibrary.OnCleanFinished",
))
LETTER_CACHE_SIZE = 64

TYPE = re.compile(r"[a-z]{1,16}")
DBID = re.compile(r"[0-9]{1,10}")
VIEW = re.compile(r"5[0-9]{2}")

Request = namedtuple("Request", "action media_type dbid")


def _optional(pattern, value):
    return value == "" or bool(pattern.fullmatch(value))


def parse(sender: str, method: str) -> Request | None:
    """The request in a notification, or None for anything else (other senders, unknown or unsafe arguments)."""
    if sender != SENDER or not method.startswith(PREFIX):
        return None
    parts = method[len(PREFIX):].split("|")
    if len(parts) > 3:
        return None
    action, media_type, dbid = (parts + ["", ""])[:3]
    if action == "info":
        # Add-on items have no database id; the art is still published.
        ok = _optional(TYPE, media_type) and _optional(DBID, dbid)
    elif action == "play":
        ok = media_type == "episode" and bool(DBID.fullmatch(dbid))
    elif action == "open":
        ok = bool(TYPE.fullmatch(media_type)) and bool(DBID.fullmatch(dbid))
    elif action == "seriesmeta":
        ok = media_type == dbid == "" and len(parts) == 1
    elif action == "letters":
        ok = bool(VIEW.fullmatch(media_type)) and dbid == "" and len(parts) == 2
    else:
        ok = False
    return Request(action, media_type, dbid) if ok else None


class LetterCache:
    """A small least-recently-used map for letter scans; get and put from the worker, clear from the monitor."""

    def __init__(self, size: int = LETTER_CACHE_SIZE):
        self.size = size
        self.lock = threading.Lock()
        self.entries = OrderedDict()

    def get(self, key):
        with self.lock:
            value = self.entries.get(key)
            if value is not None:
                self.entries.move_to_end(key)
            return value

    def put(self, key, value) -> None:
        with self.lock:
            self.entries[key] = value
            self.entries.move_to_end(key)
            while len(self.entries) > self.size:
                self.entries.popitem(last=False)

    def clear(self) -> None:
        with self.lock:
            self.entries.clear()

    def __len__(self):
        return len(self.entries)


class SkinScripts:
    """The installed skin's scripts/info.py and scripts/letters.py, reloaded when a skin update changes them."""

    NAMES = ("info", "letters")

    def __init__(self, directory_of):
        self.directory_of = directory_of  # () -> the skin's scripts directory, or raises when Bald is missing
        self.directory = None
        self.modules = {}
        self.stamps = {}
        self.lock = threading.Lock()

    def load(self):
        """(info, letters), or None when a usable version of the skin's scripts is missing. Raises when the skin
        or a script cannot be found or read. Costs two stats once loaded."""
        with self.lock:
            if self.directory is None:
                self.directory = self.directory_of()
            paths = {name: os.path.join(self.directory, f"{name}.py") for name in self.NAMES}
            try:
                stamps = {name: os.stat(path).st_mtime_ns for name, path in paths.items()}
            except OSError:
                self.directory = None  # moved or uninstalled: look the skin up again next time
                raise
            if stamps != self.stamps:
                modules = {}
                for name, path in paths.items():
                    spec = importlib.util.spec_from_file_location(f"bald_skin_{name}", path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    modules[name] = module
                self.modules, self.stamps = modules, stamps
            info, letters = self.modules["info"], self.modules["letters"]
        if getattr(info, "SERVICE_API", 0) < SERVICE_API or not hasattr(info, "handle"):
            return None
        return info, letters


class Dispatcher:
    """Receives the skin's requests on Kodi's monitor thread and runs the latest on one worker thread."""

    def __init__(self, xbmc, xbmcgui, scripts: SkinScripts, window=None, threaded: bool = True,
                 clock=time.monotonic):
        self.xbmc = xbmc
        self.xbmcgui = xbmcgui
        self.scripts = scripts
        self.window = window if window is not None else xbmcgui.Window(HOME_WINDOW)
        self.threaded = threaded
        self.clock = clock
        self.letters = LetterCache()
        self.ready = False
        self.serial = 0         # of the newest request
        self.pending = None     # (serial, request, received) not yet started
        self.condition = threading.Condition()
        self._stop = threading.Event()
        self._thread = None
        self._last_error = None

    # --- logging ---
    def log(self, text: str, level=None) -> None:
        self.xbmc.log(f"{ADDON_ID}: actions: {text}", self.xbmc.LOGDEBUG if level is None else level)

    def log_error(self, text: str) -> None:
        if text != self._last_error:
            self._last_error = text
            self.log(text, self.xbmc.LOGERROR)

    # --- advertising to the skin ---
    def refresh(self) -> bool:
        """Set or clear Bald.Helper.Actions from whether the skin's scripts load. Called about once a second."""
        try:
            ready = self.scripts.load() is not None
        except Exception as error:  # noqa: BLE001 - a missing or broken skin script means RunScript, not a crash
            self.log_error(f"skin scripts unavailable: {type(error).__name__}: {error}")
            ready = False
        if ready:
            if self.window.getProperty(PROPERTY_READY) != PROTOCOL:  # also after a skin reload or switch
                self.window.setProperty(PROPERTY_READY, PROTOCOL)
        elif self.ready or self.window.getProperty(PROPERTY_READY):
            self.window.clearProperty(PROPERTY_READY)
        if ready != self.ready:
            self.log("ready" if ready else "not ready: the skin runs its scripts", self.xbmc.LOGINFO)
        self.ready = ready
        return ready

    # --- receiving (Kodi's monitor thread: parse and hand over, nothing slow) ---
    def notify(self, sender: str, method: str, data: str = "") -> None:
        if method in LIBRARY_CHANGES:
            self.letters.clear()
            return
        request = parse(sender, method)
        if request is None:
            if sender == SENDER and method.startswith(PREFIX):
                self.log(f"ignored {method!r}", getattr(self.xbmc, "LOGWARNING", None))
            return
        self.submit(request)

    def submit(self, request: Request) -> None:
        with self.condition:
            self.serial += 1
            self.pending = (self.serial, request, self.clock())
            self.condition.notify()
        if not self.threaded:
            self.run_pending()

    # --- working (the worker thread) ---
    def cancelled_for(self, serial: int):
        return lambda: self.serial != serial or self._stop.is_set()

    def show(self, item) -> None:
        """Open the info dialog for More like this. Dialog().info returns only when that dialog closes, so it runs
        on a thread of its own and the worker stays free for the new dialog's own request."""
        thread = threading.Thread(target=lambda: self.xbmcgui.Dialog().info(item),
                                  name=f"{ADDON_ID}.info", daemon=True)
        thread.start()

    def run_pending(self) -> None:
        with self.condition:
            job, self.pending = self.pending, None
        if job is None:
            return
        serial, request, received = job
        if serial != self.serial:
            return  # superseded before it started
        self.execute(serial, request, received)

    def execute(self, serial: int, request: Request, received: float) -> None:
        cancelled = self.cancelled_for(serial)
        try:
            modules = self.scripts.load()
            if modules is None:
                raise RuntimeError("the skin's scripts are too old for Bald Helper")
            info, letters = modules
            if request.action == "letters":
                letters.publish(self.xbmc, self.xbmcgui, request.media_type, cache=self.letters, cancelled=cancelled)
            else:
                info.handle(self.xbmc, self.xbmcgui, request.action, request.media_type, request.dbid,
                            cancelled=cancelled, show=self.show)
        except Exception as error:  # noqa: BLE001 - one failing request must not end the worker
            self.log_error(f"{request.action}: {type(error).__name__}: {error}")
        elapsed = int((self.clock() - received) * 1000)
        self.window.setProperty(PROPERTY_LAST, "|".join((*request, str(elapsed))))
        self.log(f"{'|'.join(request)}: {elapsed} ms{' (superseded)' if cancelled() else ''}")

    def _worker(self) -> None:
        while not self._stop.is_set():
            with self.condition:
                while self.pending is None and not self._stop.is_set():
                    self.condition.wait(1.0)
            if not self._stop.is_set():
                self.run_pending()

    def start(self) -> None:
        self.refresh()
        if self.threaded:
            self._thread = threading.Thread(target=self._worker, name=f"{ADDON_ID}.actions", daemon=True)
            self._thread.start()
        self.log("started")

    def stop(self) -> None:
        self._stop.set()
        # Kodi exit or the add-on disabled: the skin goes back to RunScript.
        try:
            self.window.clearProperty(PROPERTY_READY)
        except Exception:  # noqa: BLE001 - shutting down
            pass
        with self.condition:
            self.condition.notify_all()
        if self._thread is not None:
            self._thread.join(2.0)
            self._thread = None
        self.log("stopped")


def make_monitor(xbmc, dispatcher: Dispatcher):
    """An xbmc.Monitor that hands notifications to the dispatcher. Kodi runs onNotification on the thread that made
    the monitor, while that thread waits in waitForAbort, so create it on the thread that runs the service loop."""

    class ActionMonitor(xbmc.Monitor):
        def onNotification(self, sender, method, data):  # noqa: N802 - Kodi's name
            try:
                dispatcher.notify(sender, method, data)
            except Exception as error:  # noqa: BLE001 - never raise into Kodi's callback
                dispatcher.log_error(f"notification: {type(error).__name__}: {error}")

    return ActionMonitor()


def skin_scripts_directory(xbmcaddon):
    """The installed Bald's scripts directory (raises when Bald is not installed)."""
    return lambda: os.path.join(xbmcaddon.Addon(SKIN_ID).getAddonInfo("path"), "scripts")
