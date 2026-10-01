"""Bald Helper's Libraries and tags (resources/lib/libraries.py): rows for one Plex or Jellyfin library, which those
add-ons mark with a tag named after the library."""

import json
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from support import helper

libraries = helper("libraries", "libraries")
plugin = helper("plugin", "libraries")

TAGS = {"tvshow": ["Kids TV", "Anime", "Kids"], "movie": ["Kids", "4K"]}
STRINGS = {32138: "All tags", 32130: "{tag} · {list}", 32131: "Shows with new episodes", 32132: "Recently added unwatched TV shows",
           32133: "All TV shows", 32134: "Recently added unwatched movies", 32135: "In-progress movies",
           32136: "Random movies", 32137: "All movies"}


class FakeXbmc:
    def executeJSONRPC(self, request):
        request = json.loads(request)
        assert request["method"] == "VideoLibrary.GetTags"
        labels = TAGS[request["params"]["type"]]
        return json.dumps({"result": {"tags": [{"label": label, "tagid": n} for n, label in enumerate(labels)]}})


class FakeItem:
    def __init__(self, label, label2="", offscreen=True):
        self.label = label

    def setArt(self, art):
        self.art = art


class FakeGui:
    ListItem = FakeItem


class FakePlugin:
    def addDirectoryItems(self, handle, items, count):
        self.items = items

    def endOfDirectory(self, handle, **kwargs):
        pass


NODE = """<?xml version="1.0" encoding="UTF-8"?>
<node order="1" type="filter"><label>Kids TV</label><content>tvshows</content><match>all</match>
<rule field="tag" operator="is"><value>{tag}</value></rule></node>"""


class FakeVfs:
    """special://profile/... in a temporary folder: a Jellyfin-like library node folder, and a playlist."""

    def __init__(self, folder):
        self.folder = Path(folder)
        node = self.folder / "library" / "video" / "jellyfintvshows1234"
        node.mkdir(parents=True)
        (node / "recent.xml").write_text(NODE.format(tag="Kids TV"), encoding="utf-8")
        (node / "index.xml").write_text("<node order='1'><label>Kids TV</label></node>", encoding="utf-8")
        deeper = node / "deeper" / "still"
        deeper.mkdir(parents=True)
        (deeper / "x.xml").write_text(NODE.format(tag="Anime"), encoding="utf-8")  # too deep: not read
        playlists = self.folder / "playlists" / "video"
        playlists.mkdir(parents=True)
        (playlists / "kids.xsp").write_text(NODE.replace("node", "smartplaylist").format(tag="Kids"), encoding="utf-8")
        (playlists / "broken.xsp").write_text("<smartplaylist", encoding="utf-8")
        (playlists / "unknown.xsp").write_text(NODE.replace("node", "smartplaylist").format(tag="Gone"), encoding="utf-8")

    def translatePath(self, path):
        return str(self.folder / path.replace("special://profile/", ""))


class LibraryTagTests(unittest.TestCase):
    def test_every_tag_once_by_name_with_its_types(self):
        self.assertEqual(libraries.tags(FakeXbmc()),
                         {"4K": ["movie"], "Anime": ["tvshow"], "Kids": ["tvshow", "movie"], "Kids TV": ["tvshow"]})

    def test_the_libraries_are_the_tags_nodes_and_playlists_name(self):
        # Jellyfin copies every keyword in as a tag too: only the tags a library node or a playlist filters on, and
        # that a movie or show has (Gone has none), then every tag in a folder of its own.
        base = "plugin://script.bald.helper/"
        with tempfile.TemporaryDirectory() as folder:
            listing = FakePlugin()
            libraries.list_tags(FakeXbmc(), FakeGui, listing, FakeVfs(folder), 1, base, False, STRINGS.get)
            self.assertEqual([(i.label, url, isfolder) for url, i, isfolder in listing.items],
                             [("Kids", f"{base}?info=library_tag&tag=Kids", True),
                              ("Kids TV", f"{base}?info=library_tag&tag=Kids%20TV", True),
                              ("All tags", f"{base}?info=library_tags&all=1", True)])
            every = FakePlugin()
            libraries.list_tags(FakeXbmc(), FakeGui, every, FakeVfs(folder + "/2"), 1, base, True, STRINGS.get)
            self.assertEqual([i.label for _, i, _ in every.items], ["4K", "Anime", "Kids", "Kids TV"])

    def lists(self, tag):
        """[(label, special path, playlist root)] for a tag's lists, read back from the files written."""
        with tempfile.TemporaryDirectory() as folder:
            vfs = FakeVfs(folder)
            listing = FakePlugin()
            libraries.list_tag(FakeXbmc(), FakeGui, listing, vfs, 1, tag, STRINGS.get)
            self.assertTrue(all(isfolder for _, _, isfolder in listing.items))
            return [(item.label, path, ET.parse(vfs.translatePath(path)).getroot()) for path, item, _ in listing.items]

    def test_a_tags_rows_are_smart_playlists_filtered_to_it(self):
        found = self.lists("Kids TV")
        self.assertEqual([label for label, _, _ in found],
                         ["Kids TV · Shows with new episodes", "Kids TV · Recently added unwatched TV shows",
                          "Kids TV · All TV shows"])
        label, path, root = found[0]
        self.assertTrue(path.startswith("special://profile/addon_data/script.bald.helper/libraries/tvshows_new_episodes_"))
        self.assertEqual((root.get("type"), root.findtext("name"), root.findtext("match"), root.findtext("limit")),
                         ("tvshows", label, "all", "50"))
        # A show with any unwatched episode, the latest added first: one tile per show.
        self.assertEqual([(r.get("field"), r.get("operator"), r.findtext("value")) for r in root.findall("rule")],
                         [("tag", "is", "Kids TV"), ("playcount", "is", "0")])
        self.assertEqual((root.findtext("order"), root.find("order").get("direction")), ("dateadded", "descending"))
        self.assertIsNone(found[2][2].find("limit"))

    def test_a_tag_on_movies_and_shows_lists_both(self):
        found = self.lists("Kids")
        self.assertEqual([root.get("type") for _, _, root in found], ["tvshows"] * 3 + ["movies"] * 4)
        progress = found[4][2]
        self.assertEqual([(r.get("field"), r.get("operator"), r.find("value")) for r in progress.findall("rule")][1],
                         ("inprogress", "true", None))
        # Each tag and list keeps its own file; the same tag writes the same names again.
        self.assertEqual(len({path for _, path, _ in found}), 7)
        self.assertEqual([path for _, path, _ in found], [path for _, path, _ in self.lists("Kids")])
        self.assertNotEqual(found[0][1], self.lists("Kids TV")[0][1])

    def test_an_unknown_tag_lists_nothing(self):
        self.assertEqual(self.lists("Nope"), [])

    def test_the_strings_exist(self):
        from support import ADDON
        po = (ADDON / "resources" / "language" / "resource.language.en_gb" / "strings.po").read_text(encoding="utf-8")
        for number, text in STRINGS.items():
            self.assertIn(f'msgctxt "#{number}"\nmsgid "{text}"', po)


if __name__ == "__main__":
    unittest.main()
