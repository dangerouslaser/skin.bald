"""Ratings in media views (Includes_Bald_Ratings.xml) and their settings in Appearance > Ratings (window 1118)."""

import re
import unittest
import xml.etree.ElementTree as ET

from conditions import equivalent, implies
from kodi_includes import SKIN, expand_call, include_definitions, resolve_window
from skin_strings import RATINGS_RANGE, strings

ROOT = SKIN.parent
RATINGS = SKIN / "Includes_Bald_Ratings.xml"
APPEARANCE = "Custom_1118_BaldAppearance.xml"

# Appearance row -> the skin bool it toggles; all negative except vote counts.
ROWS = {
    "9641": "Bald.Ratings.Hide",
    "9642": "Bald.Ratings.NoIMDb",
    "9643": "Bald.Ratings.NoTMDb",
    "9644": "Bald.Ratings.NoRTCritics",
    "9645": "Bald.Ratings.NoRTAudience",
    "9646": "Bald.Ratings.NoMetacritic",
    "9647": "Bald.Ratings.NoTrakt",
    "9648": "Bald.Ratings.NoTVDb",
    "9649": "Bald.Ratings.NoUser",
    "9650": "Bald.Ratings.NoDefault",
    "9651": "Bald.Ratings.NoInfo",
    "9652": "Bald.Ratings.NoHome",
    "9653": "Bald.Ratings.NoLibrary",
    "9654": "Bald.Ratings.NoOSD",
    "9655": "Bald.Ratings.ShowVotes",
}
# Rating name read from the library -> (source expression, mark string, shown as a 0-100 score through the map).
SOURCES = {
    "imdb": ("Bald_RatingIMDb", 31303, False),
    "themoviedb": ("Bald_RatingTMDb", 31304, True),
    "tmdb": ("Bald_RatingTMDb", 31304, True),
    "tomatometerallcritics": ("Bald_RatingRTCritics", 31305, True),
    "tomatometerallaudience": ("Bald_RatingRTAudience", 31306, True),
    "metacritic": ("Bald_RatingMetacritic", 31307, True),
    "trakt": ("Bald_RatingTrakt", 31308, True),
    "tvdb": ("Bald_RatingTVDb", 31309, False),
}
SURFACES = ("Bald_RatingsInfo", "Bald_RatingsHome", "Bald_RatingsLibrary", "Bald_RatingsOSD")


def buttons(nodes):
    return [b for node in nodes for b in node.iter("control") if b.get("type") == "button"]


class RatingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definitions = include_definitions()
        cls.root = ET.parse(RATINGS).getroot()
        cls.appearance = resolve_window(APPEARANCE, cls.definitions)
        cls.items = buttons(expand_call("Bald_Ratings", {"container": "Container(510)."}, cls.definitions))
        cls.player = buttons(expand_call("Bald_RatingsPlayer", {}, cls.definitions))

    def plain(self, items=None):
        """The items without their vote count (the first of each pair)."""
        return [b for b in (items or self.items) if "· $INFO[" not in b.findtext("label")]

    def test_file_is_registered_after_the_common_includes(self):
        files = [n.get("file") for n in ET.parse(SKIN / "Includes.xml").getroot().findall("include")]
        self.assertIn("Includes_Bald_Ratings.xml", files)
        self.assertGreater(files.index("Includes_Bald_Ratings.xml"), files.index("Includes_Bald_Common.xml"))

    def test_every_appearance_row_toggles_its_setting_in_the_ratings_category(self):
        for control_id, setting in ROWS.items():
            with self.subTest(row=control_id):
                row = self.appearance.find(f".//control[@id='{control_id}']")
                self.assertIsNotNone(row)
                self.assertEqual(row.get("type"), "radiobutton")
                self.assertEqual([n.text for n in row.findall("onclick")], [f"Skin.ToggleSetting({setting})"])
                selected = row.findtext("selected")
                expected = f"Skin.HasSetting({setting})" if setting.endswith("ShowVotes") else f"!Skin.HasSetting({setting})"
                self.assertTrue(equivalent(selected, expected), selected)
                visible = " + ".join(n.text for n in row.findall("visible"))
                self.assertTrue(implies(visible, "Container(9500).HasFocus(6)"))
                enable = row.findtext("enable")
                if control_id == "9641":
                    self.assertEqual(enable, "true")
                else:
                    self.assertTrue(equivalent(enable, "!Skin.HasSetting(Bald.Ratings.Hide)"), enable)
        category = self.appearance.find(".//control[@id='9500']/content/item[@id='6']")
        self.assertEqual(category.findtext("label"), "$LOCALIZE[31300]")

    def test_every_rating_setting_is_read_and_offered(self):
        text = RATINGS.read_text()
        read = set(re.findall(r"Skin\.HasSetting\((Bald\.Ratings\.[A-Za-z]+)\)", text))
        self.assertEqual(read, set(ROWS.values()))
        # Each source and surface expression is used by the items, the row or a caller.
        skin_text = "\n".join(p.read_text() for p in SKIN.glob("*.xml") if p.name != "Includes_Bald_Ratings.xml")
        for name in re.findall(r'<expression name="(Bald_Rating[A-Za-z]*)"', text):
            with self.subTest(expression=name):
                uses = text.count(f"$EXP[{name}]") + skin_text.count(f"$EXP[{name}]")
                self.assertGreater(uses, 0, f"{name} is never used")

    def test_each_surface_shows_ratings_under_its_setting(self):
        callers = {
            "Bald_RatingsHome": ["Includes_Bald_Home.xml"],
            "Bald_RatingsInfo": ["Includes_Bald_InfoPages.xml", "Includes_Bald_InfoTV.xml"],
            "Bald_RatingsLibrary": ["View_510_Bald_Posters.xml", "View_514_Bald_ArtworkList.xml", "View_515_Bald_PosterLow.xml",
                                    "View_520_Bald_TV.xml", "View_521_Bald_TV_Alternates.xml", "Includes_Bald_Browse.xml"],
        }
        for surface, files in callers.items():
            for name in files:
                with self.subTest(surface=surface, file=name):
                    self.assertIn(f"$EXP[{surface}]", (SKIN / name).read_text())
        # The player's items all need the OSD surface; the info line in the OSD includes them.
        for item in self.player:
            self.assertTrue(implies(item.findtext("visible"), "$EXP[Bald_RatingsOSD]"))
        self.assertIn('<include content="Bald_RatingsPlayer" />', (SKIN / "Includes_Bald_OSD.xml").read_text())
        # Home's caption defaults to the Home surface; library and More like this override it.
        home = ET.parse(SKIN / "Includes_Bald_Home.xml").getroot().find("include[@name='Bald_Caption']")
        self.assertEqual(home.findtext("param[@name='ratings']"), "$EXP[Bald_RatingsHome]")

    def test_items_read_each_named_source_under_its_toggle(self):
        plain = self.plain()
        for name, (expression, mark, percent) in SOURCES.items():
            with self.subTest(source=name):
                info = f"Container(510).ListItem.Rating({name})"
                found = [b for b in plain if info in b.findtext("label")]
                self.assertEqual(len(found), 1)
                label, visible = found[0].findtext("label"), found[0].findtext("visible")
                self.assertTrue(label.startswith(f"[COLOR bald_accent]$LOCALIZE[{mark}][/COLOR] "), label)
                self.assertEqual(f"$MAP[Bald_RatingPercent, {info}]" in label, percent)
                self.assertTrue(implies(visible, f"$EXP[{expression}]"))
                self.assertTrue(implies(visible, f"!String.IsEmpty({info})"))
        # "tmdb" only stands in when there is no "themoviedb".
        tmdb = next(b for b in plain if "Rating(tmdb)" in b.findtext("label"))
        self.assertTrue(implies(tmdb.findtext("visible"), "String.IsEmpty(Container(510).ListItem.Rating(themoviedb))"))

    def test_default_rating_only_when_no_named_source_has_one(self):
        default = next(b for b in self.plain() if b.findtext("label").endswith("$INFO[Container(510).ListItem.Rating]"))
        self.assertIn("$LOCALIZE[563]", default.findtext("label"))
        for name in SOURCES:
            self.assertTrue(implies(default.findtext("visible"), f"String.IsEmpty(Container(510).ListItem.Rating({name}))"))
        user = next(b for b in self.plain() if "ListItem.UserRating" in b.findtext("label"))
        self.assertTrue(implies(user.findtext("visible"), "$EXP[Bald_RatingUser]"))

    def test_vote_counts_are_an_option_and_never_show_zero(self):
        with_votes = [b for b in self.items if "· $INFO[" in b.findtext("label")]
        self.assertTrue(with_votes)
        for item in with_votes:
            visible = item.findtext("visible")
            votes = re.search(r"\$INFO\[([^\]]+Votes[^\]]*)\]", item.findtext("label")).group(1)
            self.assertTrue(implies(visible, "$EXP[Bald_RatingVotes]"))
            self.assertTrue(implies(visible, f"!String.IsEqual({votes},0)"))
        for item in self.plain():
            # Without the vote option every item shows as its plain pill.
            self.assertFalse(implies("$EXP[Bald_RatingVotes]", item.findtext("visible")))

    def test_tmdb_helper_fallback_only_when_asked_for_and_installed(self):
        fallback = [b for b in self.plain() if "TMDbHelper.ListItem" in b.findtext("label")]
        self.assertEqual(len(fallback), 4)  # RT critics and audience, Metacritic, Trakt
        for item in fallback:
            visible = item.findtext("visible")
            self.assertTrue(implies(visible, "false"), "the default call must not show TMDb Helper values")
        asked = buttons(expand_call("Bald_Ratings", {"fallback": "true"}, self.definitions))
        for item in asked:
            if "TMDbHelper.ListItem" in item.findtext("label"):
                self.assertTrue(implies(item.findtext("visible"), "$EXP[Bald_HasTMDbHelper]"))
        info = (SKIN / "Includes_Bald_InfoPages.xml").read_text()
        self.assertEqual(info.count('<param name="fallback">true</param>'), 1)
        for name in ("Includes_Bald_Home.xml", "Includes_Bald_Browse.xml", "View_510_Bald_Posters.xml"):
            self.assertNotIn('<param name="fallback">true</param>', (SKIN / name).read_text())

    def test_row_hides_when_nothing_shows(self):
        row = expand_call("Bald_RatingsRow", {"container": "Container(510).", "visible": "$EXP[Bald_RatingsLibrary]"},
                          self.definitions)[0]
        visible = row.findtext("visible")
        self.assertTrue(implies(visible, "$EXP[Bald_RatingsLibrary]"))
        # Any item that can show implies the row shows.
        for item in buttons([row]):
            self.assertTrue(implies(f"[{item.findtext('visible')}] + $EXP[Bald_RatingsLibrary]", visible),
                            item.findtext("label"))

    def test_percent_map_turns_kodis_tenths_back_into_scores(self):
        entries = {e.get("key"): e.text for e in self.root.find("map[@name='Bald_RatingPercent']")}
        self.assertEqual(len(entries), 202)
        for key, value in (("7.8", "78"), ("7,8", "78"), ("10.0", "100"), ("10,0", "100"), ("0.5", "5"), ("9.1", "91")):
            self.assertEqual(entries[key], value, key)

    def test_pill_is_quiet_and_uses_shipped_tokens(self):
        pill = self.items[0]
        self.assertEqual(pill.findtext("enable"), "false")
        self.assertEqual(pill.findtext("width"), "auto")
        self.assertEqual(pill.find("texturenofocus").get("colordiffuse"), "bald_ink10")
        self.assertTrue((ROOT / "media" / pill.findtext("texturenofocus")).exists())
        colors = {c.get("name") for c in ET.parse(ROOT / "colors" / "defaults.xml").getroot()}
        for token in re.findall(r"\[COLOR (\w+)\]", RATINGS.read_text()) + re.findall(r'colordiffuse="(\w+)"', RATINGS.read_text()):
            self.assertIn(token, colors)
        fonts = {f.findtext("name") for f in ET.parse(SKIN / "Font.xml").getroot().iter("font")}
        for font in set(re.findall(r'<param name="font">(\w+)</param>', RATINGS.read_text())):
            self.assertIn(font, fonts)

    def test_strings_are_in_the_ratings_block(self):
        texts = strings()
        used = {int(n) for n in re.findall(r"\$LOCALIZE\[(\d+)\]", RATINGS.read_text())}
        rows = "".join(ET.tostring(self.appearance.find(f".//control[@id='{i}']"), encoding="unicode") for i in ROWS)
        rows += ET.tostring(self.appearance.find(".//control[@id='9500']/content/item[@id='6']"), encoding="unicode")
        used |= {int(n) for n in re.findall(r"\$LOCALIZE\[(\d+)\]", rows)}
        for num in used:
            with self.subTest(string=num):
                # Bald's own ratings strings, or a Kodi core string reused (563 Rating, 38018 My rating).
                self.assertTrue(num in RATINGS_RANGE or not 31000 <= num <= 31999, num)
                if num in RATINGS_RANGE:
                    self.assertIn(num, texts)
        # Home hubs share Estuary's unused gap (31200-31299); every other string there is a ratings string.
        ours = [num for num in texts if 31178 <= num <= 31596 and not 31200 <= num < 31300]
        self.assertTrue(ours)
        self.assertTrue(all(num in RATINGS_RANGE for num in ours), ours)

    def test_control_ids_are_recorded(self):
        ids = (SKIN / "IDs").read_text()
        self.assertIn("9641-9655", ids)
        self.assertIn("1, 2, 6, 3 and 5", ids)
        for control_id in ROWS:
            self.assertIn(control_id, ids)


if __name__ == "__main__":
    unittest.main()
