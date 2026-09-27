"""Bald Helper's online ratings (resources/lib/mdblist.py, ratings.py) and its cast plugin (resources/lib/plugin.py),
with xbmc, the Home window, JSON-RPC and the MDbList API replaced by stand-ins. No test makes a network request."""

import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import types
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addons" / "script.bald.helper"
LIB = ADDON / "resources" / "lib"


def load(name):
    spec = importlib.util.spec_from_file_location(f"bald_helper_{name}_test", LIB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ratings = load("ratings")
mdblist = ratings.mdblist  # the same module object ratings.py uses
plugin = load("plugin")

KEY = "k3y-SECRET-0123456789"
DAY = 24 * 60 * 60
NOW = 1_790_000_000.0  # 2026-09-22 UTC

# Modelled on the documented "Get Media Info" response (api.mdblist.com docs, the Jaws example), plus the Rotten
# Tomatoes audience entry ("popcorn") and MDbList's own rating entry, which that example leaves out.
JAWS = {
    "title": "Jaws", "year": 1975, "released": "1975-06-20", "released_digital": "1997-11-01", "runtime": 124,
    "score": 86, "score_average": 86,
    "ids": {"imdb": "tt0073195", "trakt": 457, "tmdb": 578, "tvdb": None, "mal": None, "mdblist": "om"},
    "type": "movie",
    "ratings": [
        {"source": "imdb", "value": 8.1, "score": 81, "votes": 673852, "url": 99},
        {"source": "metacritic", "value": 87, "score": 87, "votes": 21, "url": "/jaws"},
        {"source": "metacriticuser", "value": None, "score": None, "votes": None, "url": None},
        {"source": "trakt", "value": 78, "score": 78, "votes": 14033, "url": None},
        {"source": "tomatoes", "value": 97, "score": 97, "votes": 102, "url": "/m/jaws"},
        {"source": "popcorn", "value": 90, "score": 90, "votes": 250000, "url": "/m/jaws"},
        {"source": "tmdb", "value": 76, "score": 76, "votes": 10114, "url": None},
        {"source": "letterboxd", "value": 8, "score": 80, "votes": 876082, "url": "/film/jaws/"},
        {"source": "rogerebert", "value": 4, "score": None, "votes": None, "url": "great-movie-jaws-1975"},
        {"source": "myanimelist", "value": None, "score": None, "votes": None, "url": None},
        {"source": "mdblist", "value": None, "score": 85, "votes": None},
    ],
}
JAWS_VALUES = {
    "imdb": "8.1", "imdb.Votes": "673,852",
    "metacritic": "87", "metacritic.Votes": "21",
    "trakt": "78", "trakt.Votes": "14,033",
    "rt": "97", "rt.Votes": "102",
    "rtaudience": "90", "rtaudience.Votes": "250,000",
    "tmdb": "76", "tmdb.Votes": "10,114",
    "letterboxd": "4.0", "letterboxd.Votes": "876,082",
    "rogerebert": "4.0",
    "mdblist": "86",
}


class Fetch:
    """The API stand-in: answers queued per path, records every URL."""

    def __init__(self):
        self.answers = {}
        self.urls = []

    def add(self, path, status=200, data=None, headers=None):
        self.answers.setdefault(path, []).append(mdblist.Response(status, data, headers))

    def __call__(self, url):
        self.urls.append(url)
        path = url.split("api.mdblist.com/", 1)[1].split("?", 1)[0]
        queue = self.answers.get(path) or [mdblist.Response(0)]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def paths(self):
        return [u.split("api.mdblist.com/", 1)[1].split("?", 1)[0] for u in self.urls]


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Window:
    def __init__(self):
        self.properties = {}
        self.log = []

    def setProperty(self, key, value):
        self.properties[key.lower()] = value
        self.log.append(("set", key, value))

    def clearProperty(self, key):
        self.properties.pop(key.lower(), None)
        self.log.append(("clear", key))

    def getProperty(self, key):
        return self.properties.get(key.lower(), "")

    def get(self, key):
        return self.getProperty(key)


class FakeXbmc:
    LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR = 0, 1, 2, 4

    def __init__(self):
        self.skin = "skin.bald"
        self.conditions = {}
        self.labels = {}
        self.logs = []
        self.rpc = {}
        self.calls = []

    def getSkinDir(self):
        return self.skin

    def getCondVisibility(self, condition):
        return self.conditions.get(condition, False)

    def getInfoLabel(self, label):
        return self.labels.get(label, "")

    def log(self, message, level):
        self.logs.append((level, message))

    def executeJSONRPC(self, request):
        request = json.loads(request)
        self.calls.append(request)
        key = (request["method"], json.dumps(request["params"], sort_keys=True))
        return json.dumps({"jsonrpc": "2.0", "id": 1, "result": self.rpc.get(key, {})})

    def answer(self, method, params, result):
        self.rpc[(method, json.dumps(params, sort_keys=True))] = result

    def getLocalizedString(self, number):
        return {20339: "Director", 20417: "Writer"}.get(number, str(number))


class Base(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.cache = mdblist.Cache(os.path.join(self.directory.name, "ratings.db"))
        self.fetch = Fetch()
        self.clock = Clock()
        self.logs = []
        self.key = KEY
        self.ratings = mdblist.Ratings(self.cache, lambda: self.key, fetch=self.fetch, clock=self.clock,
                                       log=lambda text, error=False: self.logs.append(text))

    def tearDown(self):
        self.cache.close()
        self.directory.cleanup()


class MappingTests(unittest.TestCase):
    def test_documented_response_to_bald_values(self):
        self.assertEqual(mdblist.bald_values(JAWS), JAWS_VALUES)

    def test_formats_follow_the_existing_pills(self):
        f = mdblist.format_rating
        self.assertEqual(f("imdb", 7.85, 79), "7.8" if f"{7.85:.1f}" == "7.8" else "7.9")
        self.assertEqual(f("metacriticuser", 7.8, 78), "7.8")
        self.assertEqual(f("metacriticuser", 78, None), "7.8")    # a 0-100 value is brought back to 10
        self.assertEqual(f("letterboxd", 3.9, None), "3.9")        # no score: a value out of 5
        self.assertEqual(f("letterboxd", 8, 78), "3.9")            # the score wins: 78 / 20
        self.assertEqual(f("rogerebert", 3.5, None), "3.5")
        self.assertEqual(f("myanimelist", 8.12, 81), "8.1")
        self.assertEqual(f("tmdb", 75.6, None), "76")
        for key in mdblist.KEYS:
            self.assertIsNone(f(key, None, None))
            self.assertIsNone(f(key, 0, 0))
            self.assertIsNone(f(key, "n/a", None))

    def test_unknown_sources_and_empty_answers(self):
        self.assertEqual(mdblist.bald_values({}), {})
        self.assertEqual(mdblist.bald_values({"ratings": [{"source": "someone", "value": 5}], "score": 0}), {})
        document = {"ratings": [{"source": "tomatoesaudience", "value": 88, "score": 88},
                                {"source": "audience", "value": 12, "score": 12}]}
        self.assertEqual(mdblist.bald_values(document), {"rtaudience": "88"})  # first one wins
        self.assertEqual(set(mdblist.SOURCES.values()), set(mdblist.KEYS))

    def test_expiry_by_release(self):
        self.assertEqual(mdblist.ttl_for(JAWS, NOW), 7 * DAY)
        recent = {"released": time.strftime("%Y-%m-%d", time.gmtime(NOW - 30 * DAY))}
        self.assertEqual(mdblist.ttl_for(recent, NOW), DAY)
        self.assertEqual(mdblist.ttl_for({"released": "2031-01-01"}, NOW), DAY)  # not out yet
        self.assertEqual(mdblist.ttl_for({}, NOW), DAY)  # unknown
        self.assertEqual(mdblist.ttl_for({"year": 1999}, NOW), 7 * DAY)

    def test_refs(self):
        self.assertEqual(mdblist.make_ref("movie", "12", "tt0073195", "578").lookups(),
                         ["imdb/movie/tt0073195", "tmdb/movie/578"])
        self.assertEqual(mdblist.make_ref("tvshow", "3", "", "1399", "121361").lookups(),
                         ["tmdb/show/1399", "tvdb/show/121361"])
        for dbtype in ("episode", "season", "set", ""):
            self.assertIsNone(mdblist.make_ref(dbtype, "4", "tt1", "5", "6"))
        self.assertIsNone(mdblist.make_ref("movie", "12", "nm123", "", ""))  # not a title id
        self.assertEqual(mdblist.make_ref("movie", "", "tt1", "").identity(),
                         {"DBType": "movie", "DBID": "", "IMDbID": "tt1", "TMDbID": ""})


class CacheTests(Base):
    def test_lookup_is_cached_until_it_expires(self):
        self.fetch.add("imdb/movie/tt0073195", data=JAWS)
        ref = mdblist.make_ref("movie", "12", "tt0073195", "578")
        self.assertEqual(self.ratings.get(ref), (JAWS_VALUES, "api"))
        self.assertEqual(self.ratings.get(ref), (JAWS_VALUES, "cache"))
        self.assertEqual(self.ratings.cached(ref), (True, JAWS_VALUES))
        self.assertEqual(len(self.fetch.urls), 1)
        self.clock.advance(7 * DAY - 60)
        self.assertEqual(self.ratings.get(ref)[1], "cache")
        self.clock.advance(120)
        self.assertEqual(self.ratings.get(ref)[1], "api")
        self.assertEqual(len(self.fetch.urls), 2)

    def test_recent_titles_expire_after_a_day(self):
        recent = dict(JAWS, released=time.strftime("%Y-%m-%d", time.gmtime(NOW - 10 * DAY)))
        self.fetch.add("imdb/movie/tt0073195", data=recent)
        ref = mdblist.make_ref("movie", "12", "tt0073195")
        self.ratings.get(ref)
        self.clock.advance(DAY + 1)
        self.assertEqual(self.ratings.cached(ref), (False, None))

    def test_negative_cache_and_the_next_id(self):
        self.fetch.add("imdb/movie/tt9999999", status=404, data={"error": "Not found"})
        self.fetch.add("tmdb/movie/578", data=JAWS)
        ref = mdblist.make_ref("movie", "12", "tt9999999", "578")
        self.assertEqual(self.ratings.get(ref), (JAWS_VALUES, "api"))
        self.assertEqual(self.fetch.paths(), ["imdb/movie/tt9999999", "tmdb/movie/578"])
        # The imdb miss is remembered for a day: the next lookup goes straight to the cached tmdb answer.
        self.assertEqual(self.ratings.get(ref), (JAWS_VALUES, "cache"))
        self.assertEqual(len(self.fetch.urls), 2)
        only = mdblist.make_ref("movie", "13", "tt9999999")
        self.assertEqual(self.ratings.get(only), (None, "cache"))  # a cached miss
        self.clock.advance(DAY + 1)
        self.assertEqual(self.ratings.get(only), (None, "missing"))
        self.assertEqual(len(self.fetch.urls), 3)

    def test_clear_and_prune(self):
        self.cache.put("a", {"imdb": "1.0"}, NOW + 10)
        self.cache.put("b", None, NOW - 10)
        self.assertEqual(self.cache.prune(NOW), 1)
        self.assertEqual(self.cache.clear(), 1)
        self.assertEqual(self.cache.get("a", NOW), (False, None))


class QuotaTests(Base):
    ref = mdblist.make_ref("movie", "12", "tt0073195")

    def test_requests_are_counted_per_utc_day(self):
        self.fetch.add("imdb/movie/tt0073195", data=JAWS, headers={"X-RateLimit-Limit": "1000",
                                                                   "X-RateLimit-Remaining": "999"})
        self.ratings.get(self.ref)
        quota = self.cache.quota(NOW)
        self.assertEqual((quota["requests"], quota["limit"]), (1, 1000))
        self.assertEqual(self.cache.quota(NOW + DAY)["requests"], 0)

    def test_stops_when_the_counted_quota_is_used(self):
        for _ in range(3):
            self.cache.count_request(NOW, 3)
        self.fetch.add("imdb/movie/tt0073195", data=JAWS)
        self.assertEqual(self.ratings.get(self.ref), (None, "quota"))
        self.assertEqual(self.fetch.urls, [])
        self.assertGreater(self.cache.quota(NOW)["blocked_until"], NOW)
        # A new UTC day starts afresh.
        self.clock.now = mdblist.next_utc_midnight(NOW) + 1
        self.assertEqual(self.ratings.get(self.ref)[1], "api")

    def test_no_remaining_requests_stops_until_reset(self):
        reset = NOW + 5000
        self.fetch.add("imdb/movie/tt0073195", data=JAWS, headers={"X-RateLimit-Remaining": "0",
                                                                   "X-RateLimit-Reset": str(int(reset))})
        self.assertEqual(self.ratings.get(self.ref)[1], "api")  # this answer is still good
        other = mdblist.make_ref("movie", "13", "tt0000002")
        self.assertEqual(self.ratings.get(other), (None, "quota"))
        self.assertEqual(len(self.fetch.urls), 1)
        self.clock.now = reset + 1
        self.fetch.add("imdb/movie/tt0000002", data=JAWS)
        self.assertEqual(self.ratings.get(other)[1], "api")

    def test_daily_429_stops_for_the_day(self):
        self.fetch.add("imdb/movie/tt0073195", status=429, data={"error": "Daily API limit exceeded!"},
                       headers={"Retry-After": "43200", "X-RateLimit-Reset": str(int(NOW + 43200))})
        self.assertEqual(self.ratings.get(self.ref), (None, "quota"))
        self.clock.advance(3600)
        self.assertEqual(self.ratings.get(self.ref), (None, "quota"))
        self.assertEqual(len(self.fetch.urls), 1)
        self.assertEqual(self.cache.quota(NOW)["reason"], "daily")

    def test_rate_429_backs_off_for_retry_after(self):
        self.fetch.add("imdb/movie/tt0073195", status=429, data={"error": "API rate limit exceeded!"},
                       headers={"Retry-After": "120"})
        self.fetch.add("imdb/movie/tt0073195", data=JAWS)
        self.assertEqual(self.ratings.get(self.ref), (None, "quota"))
        self.clock.advance(60)
        self.assertEqual(self.ratings.get(self.ref), (None, "quota"))
        self.clock.advance(61)
        self.assertEqual(self.ratings.get(self.ref), (JAWS_VALUES, "api"))
        self.assertEqual(len(self.fetch.urls), 2)

    def test_network_failure_backs_off(self):
        self.assertEqual(self.ratings.get(self.ref), (None, "error"))  # no answer queued: no network
        self.assertEqual(self.ratings.get(self.ref), (None, "quota"))
        self.assertEqual(len(self.fetch.urls), 1)
        self.assertEqual(self.cache.quota(NOW)["requests"], 0)  # nothing reached MDbList
        self.clock.advance(mdblist.RETRY_AFTER + 1)
        self.fetch.add("imdb/movie/tt0073195", data=JAWS)
        self.assertEqual(self.ratings.get(self.ref)[1], "api")

    def test_a_refused_key_stops_until_the_key_changes(self):
        self.fetch.add("imdb/movie/tt0073195", status=401, data={"error": "Invalid API key!"})
        self.assertEqual(self.ratings.get(self.ref), (None, "nokey"))
        self.assertFalse(self.ratings.key_usable(KEY))
        self.assertEqual(self.ratings.get(self.ref), (None, "nokey"))
        self.assertEqual(len(self.fetch.urls), 1)
        self.key = "another-key"
        self.assertTrue(self.ratings.key_usable(self.key))
        self.fetch.answers["imdb/movie/tt0073195"] = [mdblist.Response(200, JAWS)]
        self.assertEqual(self.ratings.get(self.ref)[1], "api")

    def test_the_key_is_only_in_the_request(self):
        self.fetch.add("imdb/movie/tt0073195", status=500, data={"error": f"bad key {KEY}"})
        self.ratings.get(self.ref)
        self.assertIn(f"apikey={KEY}", self.fetch.urls[0])
        self.assertTrue(self.fetch.urls[0].startswith("https://api.mdblist.com/imdb/movie/tt0073195?"))
        self.assertFalse(any(KEY in text for text in self.logs), self.logs)
        # An error field on a 200 is redacted too.
        self.fetch.answers["imdb/movie/tt0073195"] = [mdblist.Response(200, {"error": f"key {KEY} expired"})]
        self.clock.advance(3600)
        self.ratings.get(mdblist.make_ref("movie", "12", "tt0073195"))
        self.assertFalse(any(KEY in text for text in self.logs), self.logs)


class HttpTests(unittest.TestCase):
    """http_get with urllib's urlopen replaced: status, headers and JSON, and no exception or URL in failures."""

    def test_success_and_http_errors(self):
        class Answer:
            status = 200
            headers = {"X-RateLimit-Remaining": "5"}

            def read(self):
                return json.dumps(JAWS).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch.object(mdblist.urllib.request, "urlopen", return_value=Answer()) as opened:
            response = mdblist.http_get("https://api.mdblist.com/imdb/movie/tt0073195?apikey=x")
        self.assertEqual((response.status, response.data["title"], response.header_number("x-ratelimit-remaining")),
                         (200, "Jaws", 5.0))
        request = opened.call_args[0][0]
        self.assertEqual(request.get_header("Accept"), "application/json")
        error = urllib.error.HTTPError("https://x", 429, "Too Many", {"Retry-After": "30"},
                                       io.BytesIO(b'{"error": "API rate limit exceeded!"}'))
        self.addCleanup(error.close)
        with mock.patch.object(mdblist.urllib.request, "urlopen", side_effect=error):
            response = mdblist.http_get("https://api.mdblist.com/x")
        self.assertEqual((response.status, response.header_number("Retry-After")), (429, 30.0))
        with mock.patch.object(mdblist.urllib.request, "urlopen", side_effect=OSError("down")):
            self.assertEqual(mdblist.http_get("https://api.mdblist.com/x").status, 0)

    def test_check_key(self):
        fetch = Fetch()
        fetch.add("user", data={"username": "bryan", "rate_limit": 1000, "rate_limit_remaining": 990})
        self.assertEqual(mdblist.check_key(KEY, fetch), ("ok", {"username": "bryan", "limit": 1000, "remaining": 990}))
        self.assertEqual(mdblist.check_key("  ", fetch)[0], "empty")
        fetch.answers["user"] = [mdblist.Response(403, {"error": "Invalid API key!"})]
        self.assertEqual(mdblist.check_key(KEY, fetch)[0], "rejected")
        fetch.answers["user"] = [mdblist.Response(0)]
        self.assertEqual(mdblist.check_key(KEY, fetch)[0], "unreachable")
        fetch.answers["user"] = [mdblist.Response(502)]
        self.assertEqual(mdblist.check_key(KEY, fetch), ("error", {"status": 502}))


class PublisherTests(unittest.TestCase):
    def test_identity_is_cleared_first_and_written_last(self):
        window = Window()
        publisher = ratings.Publisher(window, "Bald.Ratings")
        ref = mdblist.make_ref("movie", "12", "tt0073195", "578")
        publisher.publish(ref.identity(), JAWS_VALUES)
        writes = [entry for entry in window.log if entry[0] == "set"]
        self.assertEqual(writes[-1], ("set", "Bald.Ratings.DBType", "movie"))
        self.assertEqual([w[1] for w in writes[-4:]], ["Bald.Ratings.IMDbID", "Bald.Ratings.TMDbID", "Bald.Ratings.DBID",
                                                       "Bald.Ratings.DBType"])
        self.assertEqual(window.get("Bald.Ratings.imdb"), "8.1")
        self.assertEqual(window.get("Bald.Ratings.imdb.Votes"), "673,852")
        self.assertEqual(window.get("Bald.Ratings.DBID"), "12")
        # The next item: DBType goes first, before any value changes.
        window.log.clear()
        other = mdblist.make_ref("movie", "13", "tt0000002")
        publisher.publish(other.identity(), {"imdb": "5.0"})
        self.assertEqual(window.log[0], ("clear", "Bald.Ratings.DBType"))
        first_value = next(i for i, e in enumerate(window.log) if e[1] == "Bald.Ratings.imdb")
        identity_writes = [i for i, e in enumerate(window.log) if e[0] == "set" and e[1] in
                           ("Bald.Ratings.DBType", "Bald.Ratings.DBID", "Bald.Ratings.IMDbID")]
        self.assertTrue(all(i > first_value for i in identity_writes))
        self.assertEqual(window.get("Bald.Ratings.rt"), "")  # the old item's other values are gone
        self.assertEqual(window.get("Bald.Ratings.TMDbID"), "")

    def test_identity_names_never_collide_with_rating_keys(self):
        names = {f"{k}".lower() for k in mdblist.KEYS} | {f"{k}.votes" for k in mdblist.KEYS}
        self.assertFalse(names & {n.lower() for n in ratings.IDENTITY})


class FollowerTests(Base):
    def setUp(self):
        super().setUp()
        self.xbmc = FakeXbmc()
        self.window = Window()
        self.mono = Clock(1000.0)
        self.setting = KEY
        self.follower = ratings.Follower(self.xbmc, self.ratings, self.window, lambda: self.setting,
                                         lambda: 10000, clock=self.mono, threaded=False)
        self.ratings.key_source = self.follower.current_key

    def focus(self, container, dbtype, dbid="", imdb="", tmdb="", tvdb=""):
        self.xbmc.labels["Window(10000).Property(Bald.FocusContainer)"] = container
        prefix = f"Container({container}).ListItem."
        for name, value in zip(ratings.ITEM, (dbtype, dbid, imdb, tmdb, tvdb)):
            self.xbmc.labels[prefix + name] = value

    def run_for(self, seconds, step=0.05):
        end = self.mono.now + seconds
        while self.mono.now < end:
            self.follower.tick()
            self.mono.advance(step)

    def test_publishes_after_the_item_settles(self):
        self.fetch.add("imdb/movie/tt0073195", data=JAWS)
        self.focus("9101", "movie", "12", "tt0073195", "578")
        self.follower.tick()
        self.assertEqual(self.window.get("Bald.Helper.Ratings"), "1")
        self.run_for(0.3)
        self.assertEqual(self.fetch.urls, [])  # still settling
        self.run_for(0.2)
        self.assertEqual(len(self.fetch.urls), 1)
        self.assertEqual(self.window.get("Bald.Ratings.imdb"), "8.1")
        self.assertEqual((self.window.get("Bald.Ratings.DBType"), self.window.get("Bald.Ratings.DBID")), ("movie", "12"))
        self.assertTrue(self.window.get("Bald.Helper.Ratings.Last").startswith("api|movie|12|"))

    def test_scrolling_holds_a_lookup_but_not_a_cached_answer(self):
        self.focus("9101", "movie", "12", "tt0073195")
        self.xbmc.conditions["Container(9101).Scrolling"] = True
        self.fetch.add("imdb/movie/tt0073195", data=JAWS)
        self.run_for(1.0)
        self.assertEqual(self.fetch.urls, [])
        self.cache.put("imdb/movie/tt0073195", JAWS_VALUES, NOW + DAY)
        self.focus("9101", "movie", "13", "tt0073195")  # another library copy, same film: cached
        self.run_for(0.2)
        self.assertEqual(self.window.get("Bald.Ratings.DBID"), "13")
        self.assertEqual(self.fetch.urls, [])

    def test_a_new_item_clears_the_identity_at_once(self):
        self.cache.put("imdb/movie/tt0073195", JAWS_VALUES, NOW + DAY)
        self.focus("9101", "movie", "12", "tt0073195")
        self.run_for(0.3)
        self.assertEqual(self.window.get("Bald.Ratings.DBType"), "movie")
        self.focus("9101", "movie", "14", "tt0000014")
        self.follower.tick()
        self.assertEqual(self.window.get("Bald.Ratings.DBType"), "")
        self.assertEqual(self.window.get("Bald.Ratings.DBID"), "")
        # Back on the first item: shown again from the cache.
        self.focus("9101", "movie", "12", "tt0073195")
        self.run_for(0.3)
        self.assertEqual((self.window.get("Bald.Ratings.DBID"), self.window.get("Bald.Ratings.DBType")), ("12", "movie"))

    def test_episodes_and_items_without_ids_are_not_looked_up(self):
        self.cache.put("imdb/movie/tt0073195", JAWS_VALUES, NOW + DAY)
        self.focus("9101", "movie", "12", "tt0073195")
        self.run_for(0.3)
        self.focus("9101", "episode", "55", "", "", "81189")
        self.run_for(1.0)
        self.assertEqual(self.fetch.urls, [])
        self.assertEqual(self.window.get("Bald.Ratings.DBType"), "")

    def test_add_on_items_carry_their_imdb_id(self):
        self.fetch.add("imdb/movie/tt0073195", data=JAWS)
        self.focus("9101", "movie", "", "tt0073195")
        self.run_for(0.6)
        self.assertEqual((self.window.get("Bald.Ratings.DBID"), self.window.get("Bald.Ratings.IMDbID")),
                         ("", "tt0073195"))

    def test_hold_under_a_modal_dialog(self):
        self.cache.put("imdb/movie/tt0073195", JAWS_VALUES, NOW + DAY)
        self.focus("9101", "movie", "12", "tt0073195")
        self.run_for(0.3)
        self.xbmc.conditions[ratings.follow.HOLD] = True
        self.focus("9101", "", "", "")  # the context menu: nothing readable
        self.run_for(0.5)
        self.assertEqual(self.window.get("Bald.Ratings.DBID"), "12")

    def test_no_key_online_off_or_another_skin(self):
        self.setting = ""
        self.focus("9101", "movie", "12", "tt0073195")
        self.run_for(0.6)
        self.assertEqual(self.window.get("Bald.Helper.Ratings"), "")
        self.assertEqual(self.fetch.urls, [])
        self.setting = KEY
        self.mono.advance(ratings.KEY_SECONDS)
        self.cache.put("imdb/movie/tt0073195", JAWS_VALUES, NOW + DAY)
        self.run_for(0.3)
        self.assertEqual(self.window.get("Bald.Helper.Ratings"), "1")
        self.assertEqual(self.window.get("Bald.Ratings.DBID"), "12")
        self.xbmc.conditions[ratings.OFF] = True
        self.follower.tick()
        self.assertEqual((self.window.get("Bald.Ratings.DBID"), self.window.get("Bald.Ratings.imdb")), ("", ""))
        self.xbmc.conditions[ratings.OFF] = False
        self.xbmc.skin = "skin.estuary"
        self.run_for(0.3)
        self.assertEqual(self.window.get("Bald.Ratings.DBID"), "")

    def test_a_refused_key_clears_readiness(self):
        self.fetch.add("imdb/movie/tt0073195", status=401, data={"error": "Invalid API key!"})
        self.focus("9101", "movie", "12", "tt0073195")
        self.run_for(0.6)
        self.mono.advance(ratings.KEY_SECONDS)
        self.follower.tick()
        self.assertEqual(self.window.get("Bald.Helper.Ratings"), "")
        self.assertEqual(self.window.get("Bald.Ratings.DBID"), "")

    def test_stale_answers_are_dropped(self):
        ref = mdblist.make_ref("movie", "12", "tt0073195")
        self.follower.wanted = mdblist.make_ref("movie", "99", "tt0000099")
        self.cache.put("imdb/movie/tt0073195", JAWS_VALUES, NOW + DAY)
        self.follower.work(ref)
        self.assertEqual(self.window.get("Bald.Ratings.DBID"), "")

    def test_key_never_reaches_properties_or_log(self):
        self.fetch.add("imdb/movie/tt0073195", status=500, data={"error": KEY})
        self.focus("9101", "movie", "12", "tt0073195")
        self.run_for(0.6)
        self.assertFalse(any(KEY in value for value in self.window.properties.values()))
        self.assertFalse(any(KEY in message for _level, message in self.xbmc.logs), self.xbmc.logs)


class PlayerTests(Base):
    def setUp(self):
        super().setUp()
        self.xbmc = FakeXbmc()
        self.window = Window()
        self.follower = ratings.Follower(self.xbmc, self.ratings, self.window, lambda: KEY, lambda: 12005,
                                         clock=Clock(1000.0), threaded=False)
        self.follower.refresh_key(force=True)
        self.ratings.key_source = self.follower.current_key
        self.watcher = ratings.PlayerRatings(self.xbmc, self.ratings, self.window, self.follower, threaded=False)

    def play_movie(self, dbid="12", ids=None):
        self.xbmc.conditions["VideoPlayer.Content(movies)"] = True
        self.xbmc.labels["VideoPlayer.DBID"] = dbid
        self.xbmc.answer("VideoLibrary.GetMovieDetails", {"movieid": int(dbid), "properties": ["uniqueid"]},
                         {"moviedetails": {"movieid": int(dbid), "uniqueid": ids or {"imdb": "tt0073195", "tmdb": "578"}}})

    def test_library_movie_resolved_over_json_rpc(self):
        self.play_movie()
        self.fetch.add("imdb/movie/tt0073195", data=JAWS)
        self.watcher.started()
        self.assertEqual(self.window.get("Bald.Player.Ratings.imdb"), "8.1")
        self.assertEqual((self.window.get("Bald.Player.Ratings.DBType"), self.window.get("Bald.Player.Ratings.DBID"),
                          self.window.get("Bald.Player.Ratings.TMDbID")), ("movie", "12", "578"))
        self.assertEqual(self.xbmc.calls[0]["method"], "VideoLibrary.GetMovieDetails")
        # The list item's properties are untouched.
        self.assertEqual(self.window.get("Bald.Ratings.imdb"), "")
        self.watcher.stopped()
        self.assertEqual((self.window.get("Bald.Player.Ratings.imdb"), self.window.get("Bald.Player.Ratings.DBType")),
                         ("", ""))

    def test_non_library_movie_uses_the_players_ids(self):
        self.xbmc.conditions["VideoPlayer.Content(movies)"] = True
        self.xbmc.labels["VideoPlayer.UniqueID(imdb)"] = "tt0073195"
        self.fetch.add("imdb/movie/tt0073195", data=JAWS)
        self.watcher.started()
        self.assertEqual((self.window.get("Bald.Player.Ratings.DBID"), self.window.get("Bald.Player.Ratings.IMDbID")),
                         ("", "tt0073195"))
        self.assertEqual(self.xbmc.calls, [])

    def test_episodes_and_off_settings_publish_nothing(self):
        self.xbmc.conditions["VideoPlayer.Content(episodes)"] = True
        self.xbmc.labels["VideoPlayer.DBID"] = "55"
        self.watcher.started()
        self.assertEqual(self.fetch.urls, [])
        self.play_movie()
        self.xbmc.conditions[ratings.PLAYER_OFF] = True
        self.watcher.started()
        self.assertEqual(self.fetch.urls, [])
        self.assertEqual(self.window.get("Bald.Player.Ratings.DBType"), "")

    def test_a_lookup_that_ends_after_a_stop_is_dropped(self):
        self.play_movie()
        self.cache.put("imdb/movie/tt0073195", JAWS_VALUES, NOW + DAY)
        original = self.watcher.resolve

        def resolve_then_stop():
            ref = original()
            self.watcher.stopped()  # playback stopped while the lookup ran
            return ref

        self.watcher.resolve = resolve_then_stop
        self.watcher.started()
        self.assertEqual(self.window.get("Bald.Player.Ratings.DBType"), "")

    def test_player_callbacks(self):
        events = []
        watcher = types.SimpleNamespace(started=lambda: events.append("start"), stopped=lambda: events.append("stop"),
                                        follower=self.follower)

        class Player:
            pass

        player = ratings.make_player(types.SimpleNamespace(Player=Player), watcher)
        player.onPlayBackStarted()
        player.onAVStarted()
        player.onPlayBackEnded()
        player.onPlayBackStopped()
        player.onPlayBackError()
        self.assertEqual(events, ["stop", "start", "stop", "stop", "stop"])


class StartTests(unittest.TestCase):
    def test_start_wires_the_follower_and_the_player(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        xbmc = FakeXbmc()
        xbmc.Monitor = lambda: types.SimpleNamespace(abortRequested=lambda: False)
        window = Window()
        xbmcgui = types.SimpleNamespace(Window=lambda wid: window, getCurrentWindowId=lambda: 10000)
        xbmcvfs = types.SimpleNamespace(translatePath=lambda path: os.path.join(directory.name, "data"))
        addon = types.SimpleNamespace(getSettingString=lambda name: KEY if name == "mdblist_key" else "")
        xbmcaddon = types.SimpleNamespace(Addon=lambda addon_id: addon)
        follower, watcher = ratings.start(xbmc, xbmcgui, xbmcvfs, xbmcaddon)
        try:
            self.assertEqual(window.get("Bald.Helper.Ratings"), "1")
            self.assertIs(watcher.follower, follower)
            self.assertTrue(os.path.isfile(os.path.join(directory.name, "data", "ratings.db")))
            self.assertEqual(follower.ratings.key_source(), KEY)
        finally:
            follower.stop()
            follower.ratings.cache.close()
        self.assertEqual(window.get("Bald.Helper.Ratings"), "")
        self.assertFalse(any(KEY in message for _level, message in xbmc.logs))


class CastPluginTests(unittest.TestCase):
    def setUp(self):
        self.xbmc = FakeXbmc()

    def test_movie_cast_in_billing_order(self):
        self.xbmc.answer("VideoLibrary.GetMovieDetails", {"movieid": 12, "properties": ["cast"]},
                         {"moviedetails": {"cast": [
                             {"name": "Robert Shaw", "role": "Quint", "order": 1, "thumbnail": "image://shaw/"},
                             {"name": "Roy Scheider", "role": "Brody", "order": 0, "thumbnail": ""},
                             {"name": "", "role": "Nobody", "order": 2}]}})
        self.assertEqual(plugin.cast(self.xbmc, "movie", 12), [
            {"name": "Roy Scheider", "role": "Brody", "thumbnail": "", "order": 0},
            {"name": "Robert Shaw", "role": "Quint", "thumbnail": "image://shaw/", "order": 1}])

    def test_episode_cast_merges_the_shows(self):
        self.xbmc.answer("VideoLibrary.GetEpisodeDetails", {"episodeid": 55, "properties": ["cast", "tvshowid"]},
                         {"episodedetails": {"tvshowid": 7, "cast": [
                             {"name": "Guest Star", "role": "Visitor", "order": 0, "thumbnail": "g"},
                             {"name": "Lead", "role": "Hero", "order": 1, "thumbnail": "l"}]}})
        self.xbmc.answer("VideoLibrary.GetTVShowDetails", {"tvshowid": 7, "properties": ["cast"]},
                         {"tvshowdetails": {"cast": [
                             {"name": "Lead", "role": "Hero", "order": 0, "thumbnail": "l"},
                             {"name": "Second", "role": "Sidekick", "order": 1, "thumbnail": "s"}]}})
        names = [p["name"] for p in plugin.cast(self.xbmc, "episode", 55)]
        self.assertEqual(names, ["Guest Star", "Lead", "Second"])
        self.assertEqual([p["order"] for p in plugin.cast(self.xbmc, "episode", 55)], [0, 1, 2])

    def test_crew_names_without_photos(self):
        self.xbmc.answer("VideoLibrary.GetMovieDetails", {"movieid": 12, "properties": ["director", "writer"]},
                         {"moviedetails": {"director": ["Steven Spielberg"],
                                           "writer": ["Peter Benchley", "Carl Gottlieb", "Steven Spielberg"]}})
        self.assertEqual(plugin.crew(self.xbmc, "movie", 12), [
            {"name": "Steven Spielberg", "role_id": 20339}, {"name": "Peter Benchley", "role_id": 20417},
            {"name": "Carl Gottlieb", "role_id": 20417}])
        self.assertEqual(plugin.crew(self.xbmc, "tvshow", 7), [])

    def test_directory_listing(self):
        self.xbmc.answer("VideoLibrary.GetMovieDetails", {"movieid": 12, "properties": ["cast"]},
                         {"moviedetails": {"cast": [{"name": "Roy Scheider", "role": "Brody", "order": 0,
                                                     "thumbnail": "image://roy/"}]}})
        made, added, ended = [], [], []

        class ListItem:
            def __init__(self, label="", label2="", offscreen=False):
                self.label, self.label2, self.art, self.props = label, label2, {}, {}
                made.append(self)

            def setArt(self, art):
                self.art = art

            def setProperty(self, key, value):
                self.props[key] = value

        xbmcgui = types.SimpleNamespace(ListItem=ListItem)
        xbmcplugin = types.SimpleNamespace(addDirectoryItems=lambda h, items, n: added.extend(items),
                                           endOfDirectory=lambda h, **kw: ended.append(kw))
        plugin.run(["plugin://script.bald.helper/", "7", "?info=cast&dbtype=movie&dbid=12"], self.xbmc, xbmcgui,
                   xbmcplugin, None, None)
        self.assertEqual([(i.label, i.label2, i.art["thumb"]) for _u, i, _f in added], [("Roy Scheider", "Brody", "image://roy/")])
        self.assertEqual(ended, [{"cacheToDisc": False}])
        # Bad arguments end the directory without an item, and never reach JSON-RPC.
        calls = len(self.xbmc.calls)
        ended.clear()
        plugin.run(["plugin://script.bald.helper/", "7", "?info=cast&dbtype=movie&dbid=x"], self.xbmc, xbmcgui,
                   xbmcplugin, None, None)
        self.assertEqual((ended, len(self.xbmc.calls)), ([{"succeeded": False}], calls))

    def test_test_key_notification_never_shows_the_key(self):
        shown = []
        strings = {32100: "Bald Helper", 32111: "MDbList key works ({user}): {remaining} of {limit} requests left today",
                   32112: "MDbList refused the key."}

        class Addon:
            def __init__(self, addon_id):
                pass

            def getLocalizedString(self, number):
                return strings.get(number, "")

            def getSettingString(self, setting):
                return KEY if setting == "mdblist_key" else ""

        dialog = types.SimpleNamespace(notification=lambda *args: shown.append(args))
        xbmcgui = types.SimpleNamespace(Dialog=lambda: dialog, NOTIFICATION_INFO="info", NOTIFICATION_WARNING="warning")
        fetch = Fetch()
        fetch.add("user", data={"username": "bryan", "rate_limit": 1000, "rate_limit_remaining": 990})
        self.assertEqual(plugin.test_key(types.SimpleNamespace(Addon=Addon), xbmcgui, fetch=fetch), "ok")
        self.assertEqual(shown[-1][1], "MDbList key works (bryan): 990 of 1000 requests left today")
        fetch.answers["user"] = [mdblist.Response(401)]
        self.assertEqual(plugin.test_key(types.SimpleNamespace(Addon=Addon), xbmcgui, fetch=fetch), "rejected")
        self.assertFalse(any(KEY in str(part) for args in shown for part in args))


class PackagingTests(unittest.TestCase):
    def test_addon_declares_service_and_plugin(self):
        root = ET.parse(ADDON / "addon.xml").getroot()
        self.assertEqual(root.get("version"), "1.3.0")
        points = {e.get("point"): e.get("library") for e in root.findall("extension")}
        self.assertEqual(points["xbmc.service"], "service.py")
        self.assertEqual(points["xbmc.python.pluginsource"], "plugin.py")
        self.assertTrue((ADDON / "plugin.py").is_file())

    def test_settings_and_strings(self):
        settings = ET.parse(ADDON / "resources" / "settings.xml").getroot()
        self.assertEqual(settings.get("version"), "1")
        key = settings.find(".//setting[@id='mdblist_key']")
        self.assertEqual(key.get("type"), "string")
        self.assertEqual(key.findtext("control/hidden"), "true")
        actions = {s.get("id"): s.findtext("data") for s in settings.iter("setting") if s.get("type") == "action"}
        self.assertEqual(actions, {"test_key": "RunPlugin(plugin://script.bald.helper/?action=test_key)",
                                   "clear_cache": "RunPlugin(plugin://script.bald.helper/?action=clear_cache)"})
        po = (ADDON / "resources" / "language" / "resource.language.en_gb" / "strings.po").read_text(encoding="utf-8")
        defined = {int(n) for n in __import__("re").findall(r'msgctxt "#(\d+)"', po)}
        used = {int(settings_id) for node in settings.iter() for attr in ("label", "help")
                if (settings_id := node.get(attr))} | {int(h) for h in (n.text for n in settings.iter("heading"))}
        used |= {getattr(plugin, name) for name in dir(plugin) if name.startswith("S_")}
        self.assertEqual(used - defined, set())
        self.assertEqual(defined - used, set())

    def test_service_entry_starts_ratings_beside_the_rest(self):
        text = (ADDON / "service.py").read_text(encoding="utf-8")
        self.assertIn("start_ratings()", text)
        self.assertIn("ratings.stop()", text)


if __name__ == "__main__":
    unittest.main()
