"""What Bald Helper's modules share: the ids, the add-on's data folder, one JSON-RPC call, log-safe sources and the
poller and worker threads of the blur, ratings and spoiler followers.

Nothing here imports xbmc at module level, so the tests drive it with stand-ins.
"""

from __future__ import annotations

import json
import re
import threading

ADDON_ID = "script.bald.helper"
SKIN_ID = "skin.bald"
HOME_WINDOW = 10000
DATA_DIR = f"special://profile/addon_data/{ADDON_ID}"
DATABASE = "ratings.db"        # the MDbList cache (mdblist.Cache) under DATA_DIR
KEY_SETTING = "mdblist_key"    # the MDbList API key setting


def jsonrpc(xbmc, method: str, params: dict, strict: bool = False):
    """One JSON-RPC call through Kodi: its result, or {} when it has none. An error answer, or one that is not
    JSON, gives {} too, unless `strict`: then an error answer raises RuntimeError and a bad answer ValueError."""
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    try:
        answer = json.loads(xbmc.executeJSONRPC(request))
    except (TypeError, ValueError):
        if strict:
            raise
        return {}
    if not isinstance(answer, dict):
        return {}
    if strict and "error" in answer:
        error = answer["error"]
        raise RuntimeError(f"{method}: {error.get('message', error) if isinstance(error, dict) else error}")
    return answer.get("result") or {}


# scheme://user:password@host, plain or percent-encoded (as inside image://smb%3a%2f%2fuser%3apass%40nas%2f...).
_USERINFO = re.compile(r"(?i)([a-z][a-z0-9+.-]*(?::|%3a)(?:/|%2f){2})(?:(?!%2f)[^/@\s])*?(?:@|%40)")


def log_safe(source: str) -> str:
    """A path or URL fit for the log: any user name and password in it (smb://user:pass@nas/...) removed."""
    return _USERINFO.sub(r"\1", source)


class Threads:
    """The follower pattern: a poller thread that calls tick() and waits what it returns, and a worker thread that
    runs the jobs next_job() hands it. Also the log helpers. A subclass sets NAME (the log tag and thread name) and
    calls init_threads(xbmc) from its constructor."""

    NAME = ""
    POLL_SECONDS = 0.15
    IDLE_SECONDS = 1.0
    ONCE_LEVEL = "LOGERROR"  # the level log_once logs at by default

    def init_threads(self, xbmc) -> None:
        self.xbmc = xbmc
        self.condition = threading.Condition()  # guards the jobs; notified when one arrives and on stop
        self._stop = threading.Event()
        self._threads = []
        self._logged = set()

    # --- logging ---
    def log(self, text: str, level=None) -> None:
        self.xbmc.log(f"{ADDON_ID}: {self.NAME}: {text}", self.xbmc.LOGDEBUG if level is None else level)

    def log_once(self, text: str, level=None) -> None:
        """Each distinct problem once per session (bounded, so a long session cannot grow it without limit)."""
        if text in self._logged:
            return
        if len(self._logged) > 200:
            self._logged.clear()
        self._logged.add(text)
        self.log(text, getattr(self.xbmc, self.ONCE_LEVEL, None) if level is None else level)

    def describe(self, error: Exception) -> str:
        """An error as logged."""
        return f"{type(error).__name__}: {error}"

    # --- the subclass's part ---
    def tick(self) -> float:
        raise NotImplementedError

    def next_job(self):
        """The next job, or None (called with the condition held)."""
        raise NotImplementedError

    def work(self, job) -> None:
        raise NotImplementedError

    def before_polling(self) -> None:
        """Runs once on the poller thread before the first tick."""

    def after_stop(self) -> None:
        """Runs once the threads have stopped."""

    # --- threads ---
    def _worker(self) -> None:
        while not self._stop.is_set():
            with self.condition:
                job = self.next_job()
                while job is None and not self._stop.is_set():
                    self.condition.wait(1.0)
                    job = self.next_job()
            if job is not None and not self._stop.is_set():
                self.work(job)

    def _poller(self, monitor) -> None:
        self.before_polling()
        while not self._stop.is_set() and not monitor.abortRequested():
            try:
                wait = self.tick()
            except Exception as error:  # noqa: BLE001 - the follower outlives any single failure
                self.log_once(self.describe(error))
                wait = self.IDLE_SECONDS
            if self._stop.wait(wait):
                break

    def start(self, monitor=None) -> None:
        monitor = monitor or self.xbmc.Monitor()
        for target, args in ((self._worker, ()), (self._poller, (monitor,))):
            thread = threading.Thread(target=target, args=args, name=f"{ADDON_ID}.{self.NAME}", daemon=True)
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
            self.after_stop()
        except Exception:  # noqa: BLE001 - shutting down
            pass
        self.log("stopped")
