"""Bald's Search (Custom_1130_BaldSearch.xml, Includes_Bald_Search.xml): the libraries through Kodi's own paths with a
smart-playlist rule, and Live TV through Bald Helper, in place of Global Search."""

import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from kodi_includes import Skin

ROOT = Path(__file__).resolve().parents[1] / "1080i"
QUERY = "$INFO[Skin.String(Bald.SearchQuery)]"
LIBRARY = {  # list id: (kind, path, field)
    "71": ("movies", "videodb://movies/titles/", "title"),
    "72": ("tvshows", "videodb://tvshows/titles/", "title"),
    "73": ("episodes", "videodb://tvshows/titles/-1/-1/", "title"),
    "74": ("musicvideos", "videodb://musicvideos/titles/", "title"),
    "75": ("artists", "musicdb://artists/", "artist"),
    "76": ("albums", "musicdb://albums/", "album"),
    "77": ("songs", "musicdb://songs/", "title"),
}
ORDER = ["movies", "tvshows", "episodes", "musicvideos", "artists", "albums", "songs", "channels", "programmes"]
IDS = {"movies": 71, "tvshows": 72, "episodes": 73, "musicvideos": 74, "artists": 75, "albums": 76, "songs": 77,
       "channels": 61, "programmes": 62}


def expressions():
    root = ET.parse(ROOT / "Includes_Bald_Search.xml").getroot()
    return {node.get("name"): node.text for node in root.findall("expression")}


class SearchWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.window = Skin().window("Custom_1130_BaldSearch.xml")
        cls.raw = ET.parse(ROOT / "Custom_1130_BaldSearch.xml").getroot()

    def test_library_results_are_kodis_own_paths_filtered_by_the_query(self):
        for list_id, (kind, path, field) in LIBRARY.items():
            node = self.window.find(f".//control[@id='{list_id}']")
            with self.subTest(kind=kind):
                content = node.findtext("content")
                base, rule = content.split("?xsp=", 1)
                self.assertEqual(base, path)
                self.assertEqual(json.loads(rule.replace(QUERY, "q")),
                                 {"rules": {"and": [{"field": field, "operator": "contains", "value": ["q"]}]},
                                  "type": kind})
                # Loaded while hidden (Kodi fills only visible lists): faded out unless it is the one that shows.
                self.assertIsNone(node.find("visible"))
                fade = node.find("animation")
                self.assertEqual(fade.get("condition"), f"!$EXP[Bald_SearchShows_{kind}]")
                self.assertEqual((node.findtext("onup"), node.findtext("ondown"), node.findtext("onleft")),
                                 (list_id, list_id, "9100"))
                self.assertIn(f"SetProperty(Bald.SearchCat,{kind})", [n.text for n in node.findall("onfocus")])

    def test_live_tv_results_from_bald_helper(self):
        channels, programmes = self.window.find(".//control[@id='61']"), self.window.find(".//control[@id='62']")
        self.assertEqual(channels.findtext("content"), f"plugin://script.bald.helper/?info=livetv_channels&query={QUERY}")
        self.assertEqual(programmes.findtext("content"), f"plugin://script.bald.helper/?info=livetv_programmes&query={QUERY}")
        self.assertEqual(channels.find("animation").get("condition"), "![$EXP[Bald_SearchShows_channels]]")
        self.assertIn("SetProperty(Bald.SearchCat,channels)", [n.text for n in channels.findall("onfocus")])

    def test_the_chosen_category_else_the_first_with_results(self):
        found = expressions()
        for n, kind in enumerate(ORDER):
            self.assertEqual(found[f"Bald_SearchHas_{kind}"], f"[Integer.IsGreater(Container({IDS[kind]}).NumItems,0)]")
            earlier = "".join(f" + !$EXP[Bald_SearchHas_{k}]" for k in ORDER[:n])
            self.assertEqual(found[f"Bald_SearchFirst_{kind}"], f"[$EXP[Bald_SearchHas_{kind}]{earlier}]")
            # A chosen category counts only with results (a library view may name one that has none).
            self.assertEqual(found[f"Bald_SearchShows_{kind}"],
                             f"[[String.IsEqual(Window.Property(Bald.SearchCat),{kind}) + $EXP[Bald_SearchHas_{kind}]]"
                             f" | [!$EXP[Bald_SearchChosenHas] + $EXP[Bald_SearchFirst_{kind}]]]")

    def test_focus_moves_to_what_shows_once_results_come_in(self):
        self.assertEqual(self.raw.findtext("defaultcontrol"), "9198")
        timers = ET.parse(ROOT / "Timers.xml").getroot()
        timer = next(t for t in timers.findall("timer") if t.findtext("name") == "bald_search_focus")
        self.assertTrue(timer.findtext("start").startswith("Window.IsActive(1130) + Control.HasFocus(9198) + ["))
        # The expressions written out ($EXP does not work in a timer): each list gets focus when it shows.
        found = expressions()
        starts = timer.findall("onstart")
        self.assertEqual([n.text for n in starts], [f"SetFocus({IDS[k]})" for k in ORDER])
        for node, kind in zip(starts, ORDER):
            self.assertIn(f"String.IsEqual(Window(1130).Property(Bald.SearchCat),{kind}) + "
                          f"Integer.IsGreater(Container({IDS[kind]}).NumItems,0)", node.get("condition"))
            self.assertNotIn("$EXP", node.get("condition"))

    def test_bald_helper_asks_for_the_query_not_the_window(self):
        # A keyboard opened from a window's onload never finished closing in Kodi 22: the helper asks first.
        onload = [(n.get("condition"), n.text) for n in self.raw.findall("onload")]
        self.assertFalse([a for _, a in onload if a.startswith("Skin.SetString")])
        self.assertIn("RunPlugin(plugin://script.bald.helper/?action=search)",
                      [n.text for n in self.window.find(".//control[@id='9198']").findall("onclick")])
        # A library view names the category to start on.
        self.assertIn(("!String.IsEmpty(Window(home).Property(Bald.SearchStart))",
                       "SetProperty(Bald.SearchCat,$INFO[Window(home).Property(Bald.SearchStart)])"), onload)
        # Back to Home's Search entry, as Global Search did.
        unload = [(n.get("condition"), n.text) for n in self.raw.findall("onunload")]
        self.assertIn(("String.IsEqual(Window(home).Property(Bald.SearchOrigin),home)",
                       "SetProperty(Bald.ReturnSearch,true,home)"), unload)

    def test_the_options_list_new_search_and_the_categories_with_results(self):
        options = self.window.find(".//control[@id='9100']")
        items = options.findall("content/item")
        self.assertEqual(items[0].findtext("label"), "$LOCALIZE[31892]")  # New search
        self.assertIn("RunPlugin(plugin://script.bald.helper/?action=search)", [n.text for n in items[0].findall("onclick")])
        for item, kind in zip(items[1:], ORDER):
            with self.subTest(kind=kind):
                self.assertEqual(item.findtext("visible"), f"$EXP[Bald_SearchHas_{kind}]")
                self.assertEqual(item.findtext("label2"), f"$INFO[Container({IDS[kind]}).NumItems]")
                self.assertEqual([n.text for n in item.findall("onclick")],
                                 [f"SetProperty(Bald.SearchCat,{kind})", "ClearProperty(Bald.SearchMenu)",
                                  f"SetFocus({IDS[kind]})"])
        # Leaving the options returns to the list that shows (or where focus waits, with none).
        exits = [(n.get("condition"), n.text) for n in options.findall("onleft")]
        self.assertEqual(exits[0], (None, "ClearProperty(Bald.SearchMenu)"))
        self.assertEqual(exits[1:], [(f"$EXP[Bald_SearchShows_{k}]", str(IDS[k])) for k in ORDER] +
                         [("!$EXP[Bald_SearchAny]", "9198")])

    def test_the_id_map_lists_the_window(self):
        ids = (ROOT / "IDs").read_text(encoding="utf-8")
        self.assertIn("Custom_1130_BaldSearch.xml (window 1130)", ids)
        self.assertIn("Free custom window numbers start at 113", ids)


if __name__ == "__main__":
    unittest.main()
