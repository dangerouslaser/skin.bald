"""MDbList ratings for Bald Helper: the API client, the mapping to Bald's rating sources, and a SQLite cache that
also counts the day's requests.

Written from MDbList's public API documentation (https://api.mdblist.com/docs/, its OpenAPI schema at
https://api.mdblist.com/schema/ and the API Blueprint at https://mdblist.docs.apiary.io/, read 2026-09-27):

- GET https://api.mdblist.com/{provider}/{media_type}/{id}?apikey=KEY, provider imdb, tmdb, trakt, tvdb, mal or
  mdblist; media_type movie, show or any. The answer holds `title`, `year`, `released` ("YYYY-MM-DD"), `score`
  (MDbList's own 0-100), `ids` and `ratings`: a list of {source, value, score, votes, url}, where `value` is the
  source's own scale and `score` 0-100 (null when MDbList has none).
- There is no episode or season lookup: shows only (`append_to_response=episode_ratings` gives per-episode critic
  ratings to Supporters only, with no source named), so Bald Helper looks up movies and shows.
- The API key goes in the `apikey` query parameter. GET /user reports the account and its limits.
- Limits apply per account: a daily limit (1,000 requests on the free tier) that resets at 00:00 UTC, reported on
  successful responses as X-RateLimit-Limit, X-RateLimit-Remaining and X-RateLimit-Reset (a Unix time); and at most
  1,000 reads per fixed 5-minute window. Over either, the answer is 429 with Retry-After (seconds) and an `error` of
  "Daily API limit exceeded!" or "API rate limit exceeded!".

The key never reaches the log or a window property: request URLs are never logged, and any error text that could
carry the key is redacted first.

Nothing here imports xbmc, so the tests drive it with canned responses; no test calls the real API.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

API = "https://api.mdblist.com"
USER_AGENT = "script.bald.helper (Kodi; https://github.com/dangerouslaser/skin.bald)"
TIMEOUT = 10

DAY = 24 * 60 * 60
TTL = 7 * DAY              # a title released more than RECENT ago
TTL_RECENT = DAY           # newer (or unreleased) titles: their scores still move
RECENT = 60 * DAY
TTL_MISSING = DAY          # MDbList does not know the id
FREE_DAILY_LIMIT = 1000    # until the first response reports the account's limit
RETRY_AFTER = 60           # a 429 or a network failure without Retry-After
DAILY_EXCEEDED = "Daily API limit exceeded"

# Bald's rating keys, in the skin's pill order, with how each is shown. The formats are the ones Bald's pills already
# use (Includes_Bald_Ratings.xml): IMDb, Metacritic users and MyAnimeList "7.8" of 10; TMDb, Trakt and both Rotten
# Tomatoes scores the 0-100 number (the skin adds "%"); Metacritic and MDbList's score the 0-100 number; Letterboxd
# "3.9" of 5; Roger Ebert "3.5" of 4.
KEYS = ("imdb", "tmdb", "rt", "rtaudience", "metacritic", "metacriticuser", "trakt", "letterboxd", "myanimelist",
        "rogerebert", "mdblist")
# MDbList `source` -> Bald key. "popcorn" is what MDbList calls Rotten Tomatoes' audience score (the API's filters
# name it "RT Audience (Popcorn)"); "audience" and "tomatoesaudience" are accepted too, since the documented
# example response does not include that source.
SOURCES = {
    "imdb": "imdb", "tmdb": "tmdb", "trakt": "trakt", "tomatoes": "rt", "popcorn": "rtaudience",
    "audience": "rtaudience", "tomatoesaudience": "rtaudience", "metacritic": "metacritic",
    "metacriticuser": "metacriticuser", "letterboxd": "letterboxd", "rogerebert": "rogerebert",
    "myanimelist": "myanimelist", "mdblist": "mdblist",
}


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _tenths(number: float) -> str:
    return f"{number:.1f}"


def _whole(number: float) -> str:
    return str(int(round(number)))


def format_rating(key: str, value, score):
    """The text Bald shows for one MDbList rating, or None when there is nothing to show."""
    value, score = _number(value), _number(score)
    if key in ("imdb", "myanimelist"):
        return _tenths(value) if value and value <= 10 else (_tenths(score / 10) if score else None)
    if key == "metacriticuser":
        if value:
            return _tenths(value / 10 if value > 10 else value)
        return _tenths(score / 10) if score else None
    if key == "letterboxd":
        # Out of 5. The score (0-100) is unambiguous; the documented example's `value` is not on a 5-point scale.
        if score:
            return _tenths(score / 20)
        return _tenths(value) if value and value <= 5 else None
    if key == "rogerebert":
        if value and value <= 4:
            return _tenths(value)
        return _tenths(score / 25) if score else None
    # 0-100: TMDb, Trakt, Rotten Tomatoes critics and audience, Metacritic, MDbList.
    number = score or value
    return _whole(number) if number and number <= 100 else None


def format_votes(votes):
    number = _number(votes)
    return f"{int(number):,}" if number else None


def bald_values(document: dict) -> dict:
    """An MDbList media response -> Bald's values: {"imdb": "8.1", "imdb.Votes": "673,852", ...}. Only sources with a
    value appear; a source listed twice keeps its first value."""
    values = {}
    for rating in document.get("ratings") or ():
        if not isinstance(rating, dict):
            continue
        key = SOURCES.get(str(rating.get("source", "")).lower())
        if key is None or key in values:
            continue
        text = format_rating(key, rating.get("value"), rating.get("score"))
        if text is None:
            continue
        values[key] = text
        votes = format_votes(rating.get("votes"))
        if votes:
            values[f"{key}.Votes"] = votes
    score = _number(document.get("score"))
    if score and score <= 100:
        values["mdblist"] = _whole(score)  # MDbList's own score is top-level; it wins over a ratings entry
    return values


def released_on(document: dict):
    """The release date as a Unix time (UTC midnight), from `released`, else 1 January of `year`; None if unknown."""
    text = str(document.get("released") or "")[:10]
    try:
        day = date.fromisoformat(text)
    except ValueError:
        try:
            day = date(int(document.get("year")), 1, 1)
        except (TypeError, ValueError):
            return None
    return calendar.timegm(day.timetuple())


def ttl_for(document: dict, now: float) -> int:
    """7 days, or 1 day for a title released in the last RECENT days, not yet released or of unknown date."""
    released = released_on(document)
    if released is None or now - released < RECENT:
        return TTL_RECENT
    return TTL


def utc_day(now: float) -> str:
    return datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")


def next_utc_midnight(now: float) -> float:
    return (int(now) // DAY + 1) * DAY


class Cache:
    """SQLite under addon_data: ratings by lookup key, and the day's request count and any back-off.

    ratings(key, data, expires): data is the JSON of bald_values(), or NULL for a title MDbList does not know.
    quota(day, requests, daily_limit, blocked_until, reason): one row per UTC day.
    One connection, shared by the follower's worker, the player thread and the plugin's own process (SQLite locks
    the file), guarded by a lock in this process.
    """

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, timeout=5, check_same_thread=False, isolation_level=None)
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("CREATE TABLE IF NOT EXISTS ratings (key TEXT PRIMARY KEY, data TEXT, expires REAL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS quota (day TEXT PRIMARY KEY, requests INTEGER NOT NULL,"
                            " daily_limit INTEGER, blocked_until REAL NOT NULL DEFAULT 0, reason TEXT)")

    def close(self) -> None:
        with self.lock:
            self.db.close()

    # --- ratings ---
    def get(self, key: str, now: float):
        """(found, values): values is None for a cached miss. Expired rows count as not found."""
        with self.lock:
            row = self.db.execute("SELECT data, expires FROM ratings WHERE key = ?", (key,)).fetchone()
        if row is None or row[1] <= now:
            return False, None
        return True, (json.loads(row[0]) if row[0] is not None else None)

    def put(self, key: str, values, expires: float) -> None:
        data = None if values is None else json.dumps(values, separators=(",", ":"), sort_keys=True)
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO ratings (key, data, expires) VALUES (?, ?, ?)",
                            (key, data, expires))

    def prune(self, now: float) -> int:
        with self.lock:
            removed = self.db.execute("DELETE FROM ratings WHERE expires <= ?", (now,)).rowcount
            self.db.execute("DELETE FROM quota WHERE day < ?", (utc_day(now - 7 * DAY),))
        return removed

    def clear(self) -> int:
        """Forget every rating (the quota count stays: the requests were made)."""
        with self.lock:
            return self.db.execute("DELETE FROM ratings").rowcount

    # --- the day's quota ---
    def quota(self, now: float) -> dict:
        day = utc_day(now)
        with self.lock:
            row = self.db.execute("SELECT requests, daily_limit, blocked_until, reason FROM quota WHERE day = ?",
                                  (day,)).fetchone()
        if row is None:
            return {"day": day, "requests": 0, "limit": None, "blocked_until": 0.0, "reason": None}
        return {"day": day, "requests": row[0], "limit": row[1], "blocked_until": row[2], "reason": row[3]}

    def count_request(self, now: float, limit=None) -> None:
        day = utc_day(now)
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO quota (day, requests) VALUES (?, 0)", (day,))
            self.db.execute("UPDATE quota SET requests = requests + 1, daily_limit = COALESCE(?, daily_limit)"
                            " WHERE day = ?", (limit, day))

    def block(self, now: float, until: float, reason: str) -> None:
        day = utc_day(now)
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO quota (day, requests) VALUES (?, 0)", (day,))
            self.db.execute("UPDATE quota SET blocked_until = MAX(blocked_until, ?), reason = ? WHERE day = ?",
                            (until, reason, day))

    def unblock(self, now: float) -> None:
        with self.lock:
            self.db.execute("UPDATE quota SET blocked_until = 0, reason = NULL WHERE day = ?", (utc_day(now),))


class Response:
    """What one API call returned: status (0 for no answer), the parsed JSON (or None) and the headers."""

    def __init__(self, status: int, data=None, headers=None):
        self.status = status
        self.data = data
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}

    def header_number(self, name: str):
        try:
            return float(self.headers.get(name.lower(), ""))
        except ValueError:
            return None


def http_get(url: str, timeout: float = TIMEOUT) -> Response:
    """GET url and parse JSON. Never raises for HTTP or network errors; never puts the URL in a message."""
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310 - fixed https host
            status, headers, body = answer.status, dict(answer.headers.items()), answer.read()
    except urllib.error.HTTPError as error:
        status, headers = error.code, dict(error.headers.items()) if error.headers else {}
        try:
            body = error.read()
        except Exception:  # noqa: BLE001
            body = b""
    except Exception:  # noqa: BLE001 - network, TLS, timeout: no answer
        return Response(0)
    try:
        data = json.loads(body.decode("utf-8")) if body else None
    except (UnicodeDecodeError, ValueError):
        data = None
    return Response(status, data, headers)


def redact(text: str, key: str) -> str:
    return text.replace(key, "***") if key else text


class Ref:
    """One item to rate: its Kodi type (movie or tvshow) and ids; `lookups` are the MDbList paths to try in order."""

    __slots__ = ("dbtype", "dbid", "imdb", "tmdb", "tvdb")

    def __init__(self, dbtype: str, dbid: str = "", imdb: str = "", tmdb: str = "", tvdb: str = ""):
        self.dbtype, self.dbid = dbtype, dbid
        self.imdb = imdb if imdb.startswith("tt") and imdb[2:].isdigit() else ""
        self.tmdb = tmdb if tmdb.isdigit() else ""
        self.tvdb = tvdb if tvdb.isdigit() else ""

    def key(self):
        return (self.dbtype, self.dbid, self.imdb, self.tmdb, self.tvdb)

    def __eq__(self, other):
        return isinstance(other, Ref) and self.key() == other.key()

    def __hash__(self):
        return hash(self.key())

    def __repr__(self):
        return "Ref(%s)" % "|".join(self.key())

    def lookups(self) -> list[str]:
        media = {"movie": "movie", "tvshow": "show"}.get(self.dbtype)
        if media is None:
            return []
        found = []
        if self.imdb:
            found.append(f"imdb/{media}/{self.imdb}")
        if self.tmdb:
            found.append(f"tmdb/{media}/{self.tmdb}")
        if self.tvdb and media == "show":
            found.append(f"tvdb/{media}/{self.tvdb}")
        return found

    def identity(self) -> dict:
        return {"DBType": self.dbtype, "DBID": self.dbid, "IMDbID": self.imdb, "TMDbID": self.tmdb}


def make_ref(dbtype: str, dbid: str = "", imdb: str = "", tmdb: str = "", tvdb: str = ""):
    """A Ref for a movie or TV show with at least one id MDbList can look up; None for anything else (episodes and
    seasons have no MDbList lookup)."""
    ref = Ref(dbtype.strip().lower(), dbid.strip() if dbid.strip().isdigit() else "", imdb.strip(), tmdb.strip(),
              tvdb.strip())
    return ref if ref.lookups() else None


class Ratings:
    """Cached MDbList lookups within the day's quota. Thread-safe; `get` is what the followers call."""

    def __init__(self, cache: Cache, key_source, fetch=http_get, clock=time.time, log=None):
        self.cache = cache
        self.key_source = key_source   # () -> the current API key ("" when none)
        self.fetch = fetch
        self.clock = clock
        self.log = log or (lambda text, error=False: None)
        self.lock = threading.Lock()   # one request at a time
        self.network_until = 0.0       # in-memory back-off after a network failure
        self.rejected_key = None       # a fingerprint of a key MDbList refused (never the key itself)

    @staticmethod
    def fingerprint(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]

    def key_usable(self, key: str) -> bool:
        return bool(key) and self.fingerprint(key) != self.rejected_key

    def cached(self, ref: Ref):
        """(found, values) from the cache only (no request): found when any of the ref's lookups is cached fresh."""
        now = self.clock()
        for path in ref.lookups():
            found, values = self.cache.get(path, now)
            if found and values is not None:
                return True, values
        # Every lookup cached as missing counts as a cached miss.
        paths = ref.lookups()
        if paths and all(self.cache.get(path, now)[0] for path in paths):
            return True, None
        return False, None

    def allowed(self, now: float) -> bool:
        if now < self.network_until:
            return False
        quota = self.cache.quota(now)
        if quota["blocked_until"] > now:
            return False
        limit = quota["limit"] or FREE_DAILY_LIMIT
        if quota["requests"] >= limit:
            self.cache.block(now, next_utc_midnight(now), "daily")
            self.log(f"stopping for the day: {quota['requests']} of {limit} requests used", error=True)
            return False
        return True

    def get(self, ref: Ref, cancelled=lambda: False):
        """(values or None, how): how is "cache", "api", "missing", "quota", "nokey", "error" or "cancelled"."""
        found, values = self.cached(ref)
        if found:
            return values, "cache"
        key = self.key_source()
        if not self.key_usable(key):
            return None, "nokey"
        with self.lock:
            for path in ref.lookups():
                if cancelled():
                    return None, "cancelled"
                now = self.clock()
                found, values = self.cache.get(path, now)
                if found:
                    if values is not None:
                        return values, "cache"
                    continue  # known missing under this id: try the next id
                if not self.allowed(now):
                    return None, "quota"
                values, how = self.request(path, key, now)
                if how == "missing":
                    continue
                return values, how
        return None, "missing"

    def request(self, path: str, key: str, now: float):
        url = f"{API}/{path}?{urllib.parse.urlencode({'apikey': key})}"
        response = self.fetch(url)
        if response.status == 0:
            self.network_until = now + RETRY_AFTER
            self.log(f"{path}: no answer from MDbList; retrying in {RETRY_AFTER} s", error=True)
            return None, "error"
        limit = response.header_number("X-RateLimit-Limit")
        self.cache.count_request(now, int(limit) if limit else None)
        if response.status == 200 and isinstance(response.data, dict):
            remaining = response.header_number("X-RateLimit-Remaining")
            if remaining is not None and remaining <= 0:
                reset = response.header_number("X-RateLimit-Reset") or next_utc_midnight(now)
                self.cache.block(now, reset, "daily")
                self.log("MDbList daily limit reached: stopping until it resets", error=True)
            if response.data.get("error"):  # an error answered with 200
                self.log(f"{path}: {redact(str(response.data.get('error'))[:200], key)}", error=True)
                return None, "error"
            values = bald_values(response.data)
            self.cache.put(path, values, now + ttl_for(response.data, now))
            return values, "api"
        if response.status == 404:
            self.cache.put(path, None, now + TTL_MISSING)
            return None, "missing"
        if response.status in (401, 403):
            self.rejected_key = self.fingerprint(key)
            self.log("MDbList rejected the API key; online ratings stop until the key changes", error=True)
            return None, "nokey"
        if response.status == 429:
            error = str((response.data or {}).get("error", "")) if isinstance(response.data, dict) else ""
            retry = response.header_number("Retry-After") or RETRY_AFTER
            if DAILY_EXCEEDED.lower() in error.lower():
                until = response.header_number("X-RateLimit-Reset") or max(now + retry, next_utc_midnight(now))
                self.cache.block(now, until, "daily")
                self.log("MDbList daily limit exceeded: stopping until it resets", error=True)
            else:
                self.cache.block(now, now + retry, "rate")
                self.log(f"MDbList rate limit: waiting {int(retry)} s", error=True)
            return None, "quota"
        self.network_until = now + RETRY_AFTER
        self.log(f"{path}: MDbList answered {response.status}", error=True)
        return None, "error"

    def key_changed(self) -> None:
        """A new key: forget a rejected one and a back-off that belonged to the old account."""
        self.rejected_key = None
        self.network_until = 0.0
        self.cache.unblock(self.clock())


def check_key(key: str, fetch=http_get) -> tuple[str, dict]:
    """Test a key with GET /user: ("ok", {username, limit, remaining}), ("rejected", {}), ("empty", {}),
    ("unreachable", {}) or ("error", {"status": n})."""
    if not key.strip():
        return "empty", {}
    response = fetch(f"{API}/user?{urllib.parse.urlencode({'apikey': key.strip()})}")
    if response.status == 0:
        return "unreachable", {}
    if response.status in (401, 403):
        return "rejected", {}
    if response.status == 200 and isinstance(response.data, dict) and not response.data.get("error"):
        data = response.data
        limit = data.get("rate_limit") or data.get("api_requests") or response.header_number("X-RateLimit-Limit")
        remaining = data.get("rate_limit_remaining")
        if remaining is None:
            remaining = response.header_number("X-RateLimit-Remaining")
        return "ok", {"username": str(data.get("username") or ""),
                      "limit": int(limit) if limit else None,
                      "remaining": int(remaining) if remaining is not None else None}
    if isinstance(response.data, dict) and "invalid" in str(response.data.get("error", "")).lower():
        return "rejected", {}
    return "error", {"status": response.status}
