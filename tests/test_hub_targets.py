"""Hub targets and row content beyond the video library (docs/NOTES.md, Music, favourites and weather hubs).

The hub editor (Home Screens: Add hub and Opens) browses Skin Variables' grouping://hubs/, the widget editor's Choose
content grouping://shortcuts/ (shortcuts/skinvariables-shortcut-config.json). The generator turns a hub's stored path
and target into the bridge's action (Bald_HubOpen_<screen>, shortcuts/generator/screen.xml)."""

import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from test_home_hubs import build, row


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
CONFIG = json.loads((ROOT / "shortcuts" / "skinvariables-shortcut-config.json").read_text(encoding="utf-8"))


def grouping_entries(path):
    """A grouping's entries as Skin Variables' GetDirectoryGrouping lists them: dicts as they are, and a string entry
    (another grouping) replaced by that grouping's own entries, in place."""
    entries = []
    for entry in CONFIG[path]:
        if isinstance(entry, str):
            entries += grouping_entries(entry)
        else:
            entries.append(entry)
    return entries


def browse_result(entry):
    """What the browser stores for a chosen entry with use_rawpath (the editors pass it): a link entry's path with an
    empty target; a folder's path (its "use this folder" item, or a folder inside it) with the entry's node as target
    (browser.GetDirectoryBrowser.get_formatted_item)."""
    if entry["link"] == "true":
        return {"path": entry["path"], "target": ""}
    return {"path": entry["path"], "target": entry.get("node", "")}


def hub_actions(hubs):
    root = ET.fromstring(build({"hubs": hubs}).split("\n", 1)[1])
    return [root.findtext(f"include[@name='Bald_HubOpen_hub{n}']/definition/onfocus") for n in range(1, len(hubs) + 1)]


class PickerTests(unittest.TestCase):
    def test_rows_can_come_from_video_music_favourites_and_channel_groups(self):
        entries = {e["name"]: e for e in grouping_entries("grouping://shortcuts/")}
        expected = {
            "Video library": ("library://video/", "videos"),
            "Bald playlists": ("special://skin/playlists/", "videos"),
            "Video add-ons": ("addons://sources/video/", "videos"),
            "Music library": ("library://music/", "music"),
            "Bald music playlists": ("grouping://bald/musicplaylists/", "music"),
            "Music add-ons": ("addons://sources/audio/", "music"),
            "Favourites": ("favourites://", "favouritesbrowser"),
            "Live TV channel groups": ("pvr://channels/tv/", "tvchannels"),
            "Radio channel groups": ("pvr://channels/radio/", "radiochannels"),
        }
        self.assertEqual({name: (e["path"], e["node"]) for name, e in entries.items()}, expected)
        # Rows need folders (a row is a list's content): no builtins here.
        self.assertTrue(all(e["link"] == "false" for e in entries.values()))

    def test_hubs_can_open_music_favourites_weather_pictures_programs_and_radio(self):
        entries = {e["name"]: e for e in grouping_entries("grouping://hubs/")}
        builtins = {name: e["path"] for name, e in entries.items() if e["link"] == "true"}
        self.assertEqual(builtins, {
            "Favourites": "ActivateWindow(FavouritesBrowser)",
            "Pictures": "ActivateWindow(Pictures)",
            "Programs": "ActivateWindow(Programs)",
            "Add-ons": "ActivateWindow(AddonBrowser)",
            "Weather": "ActivateWindow(Weather)",
            "Radio": "ActivateWindow(RadioChannels)",
        })
        for name in ("Video library", "Music library", "Music add-ons", "Bald music playlists", "Live TV channel groups"):
            self.assertIn(name, entries)
        # Favourites appears once: the window as a hub target (the folder is for rows).
        self.assertEqual([e["name"] for e in grouping_entries("grouping://hubs/")].count("Favourites"), 1)

    def test_bald_music_playlists_are_music_nodes(self):
        playlists = CONFIG["grouping://bald/musicplaylists/"]
        for entry in playlists:
            with self.subTest(entry=entry["name"]):
                self.assertEqual((entry["node"], entry["link"]), ("music", "false"))
                path = ROOT / "playlists" / entry["path"].rsplit("/", 1)[1]
                kind = ET.parse(path).getroot().get("type")
                self.assertIn(kind, {"albums", "artists", "songs"})

    def test_every_grouping_named_is_defined(self):
        for key, entries in CONFIG.items():
            for entry in entries:
                ref = entry if isinstance(entry, str) else entry["path"]
                if ref.startswith("grouping://"):
                    self.assertIn(ref, CONFIG, key)

    def test_the_hub_editor_browses_the_hub_grouping(self):
        screens = (XML / "Custom_1117_BaldHomeScreens.xml").read_text(encoding="utf-8")
        configure = (XML / "Includes_Bald_Configure.xml").read_text(encoding="utf-8")
        self.assertIn("func=do_action&amp;&amp;grouping::grouping://hubs/&amp;&amp;use_rawpath::True", screens)
        self.assertIn("func=do_choose&amp;&amp;grouping::grouping://hubs/&amp;&amp;use_rawpath::True", configure)
        self.assertIn("func=do_new&amp;&amp;grouping::grouping://hubs/&amp;&amp;use_rawpath::True", configure)
        # The widget editor keeps the default grouping (rows only).
        self.assertNotIn("grouping::", (XML / "Custom_1116_BaldHomeWidgets.xml").read_text(encoding="utf-8"))


class OpenActionTests(unittest.TestCase):
    """The bridge's action for each kind of target, as the generator writes it."""

    CASES = [
        # Browse results, straight from the picker entries.
        ({"path": "videodb://movies/titles/", "target": "videos"}, "ActivateWindow(videos,videodb://movies/titles/,return)"),
        ({"path": "library://music/", "target": "music"}, "ActivateWindow(music,library://music/,return)"),
        ({"path": "library://music/albums.xml/", "target": "music"}, "ActivateWindow(music,library://music/albums.xml/,return)"),
        ({"path": "special://skin/playlists/random_albums.xsp", "target": "music"},
         "ActivateWindow(music,special://skin/playlists/random_albums.xsp,return)"),
        ({"path": "addons://sources/audio/", "target": "music"}, "ActivateWindow(music,addons://sources/audio/,return)"),
        ({"path": "ActivateWindow(FavouritesBrowser)", "target": ""}, "ActivateWindow(FavouritesBrowser)"),
        ({"path": "ActivateWindow(Weather)", "target": ""}, "ActivateWindow(Weather)"),
        ({"path": "ActivateWindow(Pictures)", "target": ""}, "ActivateWindow(Pictures)"),
        ({"path": "ActivateWindow(Programs)", "target": ""}, "ActivateWindow(Programs)"),
        ({"path": "ActivateWindow(RadioChannels)", "target": ""}, "ActivateWindow(RadioChannels)"),
        ({"path": "pvr://channels/tv/Kids/", "target": "tvchannels"}, "ActivateWindow(tvchannels,pvr://channels/tv/Kids/,return)"),
        # Edit keeps the old target: a typed builtin, or a music, picture or program path on a hub first set to videos.
        ({"path": "ActivateWindow(Weather)", "target": "videos"}, "ActivateWindow(Weather)"),
        ({"path": "ActivateWindow(Videos,videodb://movies/genres/,return)", "target": "videos"},
         "ActivateWindow(Videos,videodb://movies/genres/,return)"),
        ({"path": "PlayMedia(special://skin/playlists/random_movies.xsp)", "target": "videos"},
         "PlayMedia(special://skin/playlists/random_movies.xsp)"),
        ({"path": "musicdb://artists/", "target": "videos"}, "ActivateWindow(music,musicdb://artists/,return)"),
        ({"path": "addons://sources/image/", "target": "videos"}, "ActivateWindow(pictures,addons://sources/image/,return)"),
        ({"path": "addons://sources/executable/", "target": "videos"},
         "ActivateWindow(programs,addons://sources/executable/,return)"),
        # Bald's album playlists listed under "Bald playlists" (a video grouping entry) still open in the music window.
        ({"path": "special://skin/playlists/unplayed_albums.xsp", "target": "videos"},
         "ActivateWindow(music,special://skin/playlists/unplayed_albums.xsp,return)"),
        ({"path": "special://skin/playlists/random_artists.xsp", "target": "videos"},
         "ActivateWindow(music,special://skin/playlists/random_artists.xsp,return)"),
        ({"path": "special://skin/playlists/random_musicvideo_artists.xsp", "target": "videos"},
         "ActivateWindow(videos,special://skin/playlists/random_musicvideo_artists.xsp,return)"),
        # A URL with no target at all opens in the video library.
        ({"path": "videodb://tvshows/titles/", "target": ""}, "ActivateWindow(videos,videodb://tvshows/titles/,return)"),
    ]

    def test_each_kind_of_target_opens_the_right_window(self):
        hubs = [{"label": f"Hub {i}", **target} for i, (target, _) in enumerate(self.CASES)]
        actions = []
        for start in range(0, len(hubs), 8):  # eight slots per build
            actions += hub_actions(hubs[start:start + 8])
        for (target, expected), action in zip(self.CASES, actions):
            with self.subTest(target=target):
                self.assertEqual(action, expected)

    def test_every_picker_entry_opens_in_a_window_that_shows_it(self):
        for entry in grouping_entries("grouping://hubs/"):
            if entry["path"].startswith("grouping://"):
                continue
            with self.subTest(entry=entry["name"]):
                action = hub_actions([{"label": "x", **browse_result(entry)}])[0]
                if entry["link"] == "true":
                    self.assertEqual(action, entry["path"])
                else:
                    self.assertEqual(action, f"ActivateWindow({entry['node']},{entry['path']},return)")

    def test_no_target_builds_no_bridge_action(self):
        self.assertEqual(hub_actions([{"label": "Rows only", "widgets": [row("a")]}]), [None])


class MusicRowTests(unittest.TestCase):
    def test_the_art_frame_falls_back_to_the_artist_fanart_then_the_thumb(self):
        template = (ROOT / "shortcuts" / "generator" / "fanart.xmltemplate").read_text(encoding="utf-8")
        order = [template.index(f"ListItem.Art({art})]") for art in ("fanart", "tvshow.fanart", "artist.fanart", "thumb")]
        self.assertEqual(order, sorted(order))

    def test_album_tiles_show_their_square_cover_and_artist_fanart(self):
        home = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        art = [(v.get("condition"), v.text) for v in home.findall("variable[@name='Bald_RowItemArt']/value")]
        self.assertEqual([text for _, text in art], ["$INFO[ListItem.Art(fanart)]", "$INFO[ListItem.Art(tvshow.fanart)]",
                                                     "$INFO[ListItem.Art(artist.fanart)]", "$INFO[ListItem.Art(thumb)]"])
        cover = home.find("include[@name='Bald_TileCover']/definition/control")
        self.assertEqual((cover.findtext("width"), cover.findtext("height")), ("99", "99"))
        self.assertEqual(cover.findtext("visible"), "$PARAM[shown] + $EXP[Bald_MusicCoverItem]")
        self.assertIn("String.IsEqual(ListItem.DBType,album)", home.findtext("expression[@name='Bald_MusicCoverItem']"))
        landscape = ET.tostring(home.find("include[@name='Bald_RowLandscape']"), encoding="unicode")
        self.assertEqual(landscape.count('content="Bald_TileCover"'), 2)
        text = home.find("include[@name='Bald_RowTiles_text']/include")
        self.assertEqual(text.findtext("param[@name='cover']"), "false")

    def test_the_caption_names_the_artist(self):
        home = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        metas = {call.findtext("param[@name='visible']"): call.findtext("param[@name='label']")
                 for call in home.iter("include") if call.get("content") == "Bald_CaptionMeta"}
        self.assertIn("ListItem.Artist]", metas["String.IsEqual(Container($PARAM[c]).ListItem.DBType,album)"])
        self.assertIn("ListItem.Album,", metas["String.IsEqual(Container($PARAM[c]).ListItem.DBType,song)"])

    def test_a_favourite_in_a_row_runs_itself(self):
        home = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        self.assertEqual(home.findtext("expression[@name='Bald_FavouriteItem']"),
                         "[String.StartsWith(ListItem.FolderPath,favourites://)]")
        row_list = next(c for c in home.iter("control") if c.get("type") == "fixedlist" and c.get("id") == "$PARAM[id]")
        info = [n.get("condition") for n in row_list.findall("onclick") if n.text == "Action(Info)"]
        self.assertEqual(len(info), 1)
        self.assertIn("!$EXP[Bald_FavouriteItem]", info[0])


if __name__ == "__main__":
    unittest.main()
