import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAYLISTS = ROOT / "playlists"

CATALOG = {
    "movies": {
        "inprogress_movies.xsp",
        "movies_4k.xsp",
        "random_movies.xsp",
        "recent_unwatched_movies.xsp",
        "recently_played_movies.xsp",
        "top_250_movies.xsp",
        "top_rated_movies.xsp",
        "unwatched_movies.xsp",
    },
    "tvshows": {
        "random_tvshows.xsp",
        "recent_unwatched_tvshows.xsp",
        "recently_played_tvshows.xsp",
        "top_rated_tvshows.xsp",
        "unwatched_tvshows.xsp",
    },
    "episodes": {
        "inprogress_episodes.xsp",
        "random_episodes.xsp",
        "recent_unwatched_episodes.xsp",
        "recently_played_episodes.xsp",
        "top_rated_episodes.xsp",
        "unwatched_episodes.xsp",
    },
}

# Kodi 22 Beta 1's CSmartPlaylistRule::GetFields/GetOrders contract, narrowed
# to the fields used by Bald's bundled video catalog.
FIELDS = {
    "movies": {"dateadded", "inprogress", "lastplayed", "playcount", "top250",
               "videoresolution"},
    "tvshows": {"dateadded", "lastplayed", "numepisodes", "numwatched"},
    "episodes": {"dateadded", "inprogress", "lastplayed", "playcount"},
}
ORDERS = {
    "movies": {"dateadded", "lastplayed", "random", "rating", "top250"},
    "tvshows": {"dateadded", "lastplayed", "random", "rating"},
    "episodes": {"dateadded", "lastplayed", "random", "rating"},
}


def playlist(name):
    return ET.parse(PLAYLISTS / name).getroot()


def rules(root):
    return [
        (node.get("field"), node.get("operator"), [value.text for value in node.findall("value")])
        for node in root.findall("rule")
    ]


class WidgetPlaylistTests(unittest.TestCase):
    def test_catalog_is_content_specific_and_kodi_22_compatible(self):
        for media_type, names in CATALOG.items():
            for name in names:
                with self.subTest(name=name):
                    root = playlist(name)
                    self.assertEqual(root.tag, "smartplaylist")
                    self.assertEqual(root.get("type"), media_type)
                    self.assertIn(media_type, name)
                    self.assertTrue((root.findtext("name") or "").strip())
                    self.assertEqual(root.findtext("match"), "all")
                    self.assertEqual(root.findtext("limit"), "50")

                    for rule in root.findall("rule"):
                        self.assertIn(rule.get("field"), FIELDS[media_type])

                    order = root.find("order")
                    self.assertIsNotNone(order)
                    self.assertIn(order.text, ORDERS[media_type])
                    self.assertIn(order.get("direction"), {"ascending", "descending"})

    def test_continue_watching_keeps_two_typed_inprogress_sources(self):
        movies = playlist("inprogress_movies.xsp")
        episodes = playlist("inprogress_episodes.xsp")
        self.assertEqual(movies.get("type"), "movies")
        self.assertEqual(episodes.get("type"), "episodes")
        self.assertEqual(rules(movies), [("inprogress", "true", [])])
        self.assertEqual(rules(episodes), [("inprogress", "true", [])])
        self.assertEqual(movies.findtext("order"), "lastplayed")
        self.assertEqual(episodes.findtext("order"), "lastplayed")
        self.assertEqual(movies.find("order").get("direction"), "descending")
        self.assertEqual(episodes.find("order").get("direction"), "descending")

    def test_movies_in_4k_uses_kodi_resolution_bucket(self):
        root = playlist("movies_4k.xsp")
        self.assertEqual(rules(root), [("videoresolution", "is", ["2160"])])
        self.assertEqual(root.findtext("order"), "dateadded")
        self.assertEqual(root.find("order").get("direction"), "descending")

    def test_recent_unwatched_filters_have_no_calendar_cutoff(self):
        for name in (
            "recent_unwatched_movies.xsp",
            "recent_unwatched_tvshows.xsp",
            "recent_unwatched_episodes.xsp",
        ):
            with self.subTest(name=name):
                root = playlist(name)
                self.assertNotIn("dateadded", {rule.get("field") for rule in root.findall("rule")})
                self.assertEqual(root.findtext("order"), "dateadded")
                self.assertEqual(root.find("order").get("direction"), "descending")

    def test_recently_played_is_bounded_to_four_weeks(self):
        for media_type in CATALOG:
            name = f"recently_played_{media_type}.xsp"
            with self.subTest(name=name):
                self.assertEqual(
                    rules(playlist(name)),
                    [("lastplayed", "inthelast", ["28 days"])],
                )


if __name__ == "__main__":
    unittest.main()
