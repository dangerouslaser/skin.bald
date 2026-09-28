"""Ratings in media views (Includes_Bald_Ratings.xml) and their settings in Appearance > Ratings (window 1118)."""

import re
import unittest
import xml.etree.ElementTree as ET

from conditions import atoms, equivalent, implies
from kodi_includes import SKIN, expand_call, expand_follow, include_definitions, resolve_window
from skin_strings import RATINGS_RANGE, strings
from support import load_file

ROOT = SKIN.parent
RATINGS = SKIN / "Includes_Bald_Ratings.xml"
APPEARANCE = "Custom_1118_BaldAppearance.xml"
GLYPHS = ROOT / "media" / "bald" / "ratings"

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
SOURCE_ROW = "9656"  # Default rating source: a cycle over Skin.String(Bald.Ratings.DefaultSource)
ONLINE_ROW = "9657"  # Online ratings from TMDb Helper (Bald.Ratings.NoOnline), also switching TMDbHelper.Service
HELPER_SETTINGS_ROW = "9658"  # Opens TMDb Helper's settings, where the API keys go
# Sources only TMDb Helper supplies: row -> (skin bool, on by default).
HELPER_ROWS = {
    "9659": ("Bald.Ratings.NoLetterboxd", True),
    "9660": ("Bald.Ratings.ShowMetacriticUser", False),
    "9661": ("Bald.Ratings.ShowMyAnimeList", False),
    "9662": ("Bald.Ratings.ShowRogerEbert", False),
    "9663": ("Bald.Ratings.ShowMDbList", False),
}
ALL_ROWS = [*ROWS, SOURCE_ROW, ONLINE_ROW, HELPER_SETTINGS_ROW, *HELPER_ROWS]
DEFAULT_SOURCE = "Skin.String(Bald.Ratings.DefaultSource)"
# Default rating source value, in cycle order -> (glyph, unit after the 0-100 score, or None for Kodi's 0-10 value);
# "" is Generic.
DEFAULT_SOURCES = {"": ("rating", None), "imdb": ("imdb", None), "tmdb": ("tmdb", "%"), "rt": ("rt", "%"),
                   "rtaudience": ("rt_audience", "%"), "metacritic": ("metacritic", ""), "trakt": ("trakt", "%"),
                   "jellyfin": ("jellyfin", None), "kodi": ("kodi", None)}
# Default rating source value -> the TMDb Helper value it stands in for (hidden when the default pill shows).
FALLBACK_SOURCES = {"imdb": "imdb_rating", "tmdb": "percent_tmdb_rating", "rt": "rottentomatoes_rating",
                    "rtaudience": "rottentomatoes_usermeter", "metacritic": "metacritic_rating",
                    "trakt": "percent_trakt_rating"}
# Every rating TMDb Helper publishes (its ratings table, read from TMDb Helper 6.17's source) and how Bald shows it:
# property key -> (glyph, toggle expression, unit, library rating names that win over it).
HELPER = {
    "imdb_rating": ("imdb", "Bald_RatingIMDb", "", ["imdb"]),
    "percent_tmdb_rating": ("tmdb", "Bald_RatingTMDb", "%", ["themoviedb", "tmdb"]),
    "rottentomatoes_rating": ("rt", "Bald_RatingRTCritics", "%", ["tomatometerallcritics"]),
    "rottentomatoes_usermeter": ("rt_audience", "Bald_RatingRTAudience", "%", ["tomatometerallaudience"]),
    "metacritic_rating": ("metacritic", "Bald_RatingMetacritic", "", ["metacritic"]),
    "metacriticuser_rating": ("metacritic_user", "Bald_RatingMetacriticUser", "", []),
    "percent_trakt_rating": ("trakt", "Bald_RatingTrakt", "%", ["trakt"]),
    "letterboxd_rating": ("letterboxd", "Bald_RatingLetterboxd", "", []),
    "myanimelist_rating": ("myanimelist", "Bald_RatingMyAnimeList", "", []),
    "rogerebert_rating": ("rogerebert", "Bald_RatingRogerEbert", "", []),
    "mdblist_rating": ("mdblist", "Bald_RatingMDbList", "", []),
}
LISTITEM = "Window(Home).Property(TMDbHelper.ListItem.{})"
PLAYER = "Window(Home).Property(TMDbHelper.Player.{})"
# Bald Helper's MDbList ratings (script.bald.helper, resources/lib/ratings.py): its key -> the TMDb Helper key it stands
# beside, so glyph, switch, unit and library names are the same.
BALD = {"imdb": "imdb_rating", "tmdb": "percent_tmdb_rating", "rt": "rottentomatoes_rating",
        "rtaudience": "rottentomatoes_usermeter", "metacritic": "metacritic_rating",
        "metacriticuser": "metacriticuser_rating", "trakt": "percent_trakt_rating", "letterboxd": "letterboxd_rating",
        "myanimelist": "myanimelist_rating", "rogerebert": "rogerebert_rating", "mdblist": "mdblist_rating"}
BALD_LISTITEM = "Window(Home).Property(Bald.Ratings.{})"
BALD_PLAYER = "Window(Home).Property(Bald.Player.Ratings.{})"


def guard(container):
    """What must hold for a TMDb Helper pill: online ratings on, the monitor idle, and its identity this item."""
    item = f"{container}ListItem"
    w = LISTITEM.format
    return (f"$EXP[Bald_RatingsOnline] + String.IsEmpty(Window(Home).Property(TMDbHelper.IsUpdating))"
            f" + String.IsEmpty(Window(Home).Property(TMDbHelper.IsUpdatingRatings)) + ["
            f"[!String.IsEmpty({w('imdb_id')}) + String.IsEqual({w('imdb_id')},{item}.UniqueID(imdb))]"
            f" | [!String.IsEmpty({w('tmdb_id')}) + !String.IsEqual({item}.DBType,episode)"
            f" + !String.IsEqual({item}.DBType,season) + String.IsEqual({w('tmdb_id')},{item}.UniqueID(tmdb))]"
            f" | [String.IsEqual({item}.DBType,episode) + !String.IsEmpty({w('episode')})"
            f" + String.IsEqual({w('tvshowtitle')},{item}.TVShowTitle) + String.IsEqual({w('season')},{item}.Season)"
            f" + String.IsEqual({w('episode')},{item}.Episode)]"
            f" | [!String.IsEmpty({w('title')}) + String.IsEqual({w('title')},{item}.Title)"
            f" + String.IsEqual({w('year')},{item}.Year)]]")


def bald_guard(container):
    """What must hold for a Bald Helper pill: its ratings in use, and its identity (written last) this item's."""
    item = f"{container}ListItem"
    w = BALD_LISTITEM.format
    return (f"$EXP[Bald_HelperRatings] + !String.IsEmpty({w('DBType')}) + String.IsEqual({w('DBType')},{item}.DBType) + ["
            f"[!String.IsEmpty({w('DBID')}) + String.IsEqual({w('DBID')},{item}.DBID)]"
            f" | [String.IsEmpty({w('DBID')}) + !String.IsEmpty({w('IMDbID')}) + String.IsEqual({w('IMDbID')},{item}.UniqueID(imdb))]"
            f" | [String.IsEmpty({w('DBID')}) + String.IsEmpty({w('IMDbID')}) + !String.IsEmpty({w('TMDbID')})"
            f" + String.IsEqual({w('TMDbID')},{item}.UniqueID(tmdb))]]")


def mismatch(condition):
    """Every comparison of TMDb Helper's published identity with the item fails (another item, or none yet)."""
    prefix = "String.IsEqual(Window(Home).Property(TMDbHelper.ListItem."
    return {a: False for a in atoms(condition) if a.startswith(prefix)}
# Rating name read from the library -> (source expression, glyph, shown as a 0-100 score through the map).
SOURCES = {
    "imdb": ("Bald_RatingIMDb", "imdb", False),
    "themoviedb": ("Bald_RatingTMDb", "tmdb", True),
    "tmdb": ("Bald_RatingTMDb", "tmdb", True),
    "tomatometerallcritics": ("Bald_RatingRTCritics", "rt", True),
    "tomatometerallaudience": ("Bald_RatingRTAudience", "rt_audience", True),
    "metacritic": ("Bald_RatingMetacritic", "metacritic", True),
    "trakt": ("Bald_RatingTrakt", "trakt", True),
    "tvdb": ("Bald_RatingTVDb", "tvdb", False),
}
SURFACES = ("Bald_RatingsInfo", "Bald_RatingsHome", "Bald_RatingsLibrary", "Bald_RatingsOSD")
DEFAULT_GLYPH = "$VAR[Bald_RatingDefaultGlyph]"


class Pill:
    """One rating pill: the small grouplist Bald_RatingFrame draws (left end, glyph, value buttons)."""

    def __init__(self, node):
        self.node = node
        self.visible = node.findtext("visible")
        children = node.findall("control")
        self.lead, self.glyph_image = children[0], children[1]
        self.glyph = self.glyph_image.findtext("texture")
        self.values = [c for c in children[2:] if c.get("type") == "button"]

    def label(self):
        """The plain value's label (the first value button)."""
        return self.values[0].findtext("label")

    def shows(self, button):
        """When this value button shows: the pill's condition and its own."""
        return f"[{self.visible}] + [{button.findtext('visible')}]"


def pills(nodes):
    return [Pill(g) for node in nodes for g in node.iter("control")
            if g.get("type") == "grouplist" and g.findtext("usecontrolcoords") == "true"]


def glyph_names():
    return load_file("rating_glyphs", ROOT / "tools" / "rating_glyphs.py")


class RatingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definitions = include_definitions()
        cls.root = ET.parse(RATINGS).getroot()
        cls.appearance = resolve_window(APPEARANCE, cls.definitions)
        cls.pills = pills(expand_call("Bald_Ratings", {"container": "Container(510)."}, cls.definitions))
        cls.player = pills(expand_call("Bald_RatingsPlayer", {}, cls.definitions))

    def named(self, pills=None):
        return [p for p in (pills or self.pills) if p.glyph != DEFAULT_GLYPH]

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

    def test_default_rating_source_row_cycles_every_choice(self):
        row = self.appearance.find(f".//control[@id='{SOURCE_ROW}']")
        self.assertEqual(row.get("type"), "button")
        self.assertEqual(row.findtext("label"), "$LOCALIZE[31319]")
        self.assertEqual(row.findtext("label2"), "$VAR[Bald_RatingDefaultSourceName]")
        self.assertTrue(implies(" + ".join(n.text for n in row.findall("visible")), "Container(9500).HasFocus(6)"))
        self.assertTrue(equivalent(row.findtext("enable"),
                                   "!Skin.HasSetting(Bald.Ratings.Hide) + !Skin.HasSetting(Bald.Ratings.NoDefault)"))
        # It sits right under the default rating's switch.
        ids = [c.get("id") for c in self.appearance.find(".//control[@id='9600']").findall("control")]
        self.assertEqual(ids.index(SOURCE_ROW), ids.index("9650") + 1)
        # Kodi checks every onclick condition before running any, so exactly one fires per value, stepping in order.
        order = list(DEFAULT_SOURCES)
        clicks = row.findall("onclick")
        for index, value in enumerate(order + ["stale"]):
            state = "" if value == "stale" else value
            with self.subTest(value=value):
                fired = []
                for click in clicks:
                    condition = click.get("condition")
                    atoms = {f"String.IsEqual({DEFAULT_SOURCE},{v})": (state == v) for v in order if v}
                    atoms[f"String.IsEmpty({DEFAULT_SOURCE})"] = state == ""
                    if value == "stale":  # a value this version does not know
                        atoms = {k: False for k in atoms}
                    if implies("true", condition, assume=atoms):
                        fired.append(click.text)
                nxt = "" if value == "stale" else order[(index + 1) % len(order)]
                expected = "Skin.Reset(Bald.Ratings.DefaultSource)" if nxt == "" else f"Skin.SetString(Bald.Ratings.DefaultSource,{nxt})"
                self.assertEqual(fired, [expected])
        # The row's value names the choice; empty is Generic.
        variable = self.root.find("variable[@name='Bald_RatingDefaultSourceName']")
        values = {v.get("condition"): v.text for v in variable.findall("value")}
        self.assertEqual(values[None], "$LOCALIZE[31320]")
        for value in order[1:]:
            self.assertIn(f"String.IsEqual({DEFAULT_SOURCE},{value})", values)

    def test_every_rating_setting_is_read_and_offered(self):
        text = RATINGS.read_text()
        read = set(re.findall(r"Skin\.HasSetting\((Bald\.Ratings\.[A-Za-z]+)\)", text))
        self.assertEqual(read, set(ROWS.values()) | {s for s, _on in HELPER_ROWS.values()} | {"Bald.Ratings.NoOnline"})
        self.assertEqual(set(re.findall(r"Skin\.String\((Bald\.Ratings\.[A-Za-z]+)\)", text)), {"Bald.Ratings.DefaultSource"})
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
        # The player's pills all need the OSD surface; the info line in the OSD includes them.
        self.assertTrue(self.player)
        for pill in self.player:
            self.assertTrue(implies(pill.visible, "$EXP[Bald_RatingsOSD]"))
        self.assertIn('<include content="Bald_RatingsPlayer" />', (SKIN / "Includes_Bald_OSD.xml").read_text())
        # Home's caption defaults to the Home surface; library and More like this override it.
        home = ET.parse(SKIN / "Includes_Bald_Home.xml").getroot().find("include[@name='Bald_Caption']")
        self.assertEqual(home.findtext("param[@name='ratings']"), "$EXP[Bald_RatingsHome]")

    def test_items_read_each_named_source_under_its_toggle(self):
        named = self.named()
        for name, (expression, glyph, percent) in SOURCES.items():
            with self.subTest(source=name):
                info = f"Container(510).ListItem.Rating({name})"
                found = [p for p in named if info in p.label()]
                self.assertEqual(len(found), 1)
                pill = found[0]
                self.assertEqual(pill.glyph, f"bald/ratings/{glyph}.png")
                self.assertEqual(f"$MAP[Bald_RatingPercent, {info}]" in pill.label(), percent)
                self.assertNotIn("[COLOR bald_accent]", pill.label(), "the source is the glyph, not a text mark")
                self.assertTrue(implies(pill.visible, f"$EXP[{expression}]"))
                self.assertTrue(implies(pill.visible, f"!String.IsEmpty({info})"))
        # "tmdb" only stands in when there is no "themoviedb".
        tmdb = next(p for p in named if "Rating(tmdb)" in p.label())
        self.assertTrue(implies(tmdb.visible, "String.IsEmpty(Container(510).ListItem.Rating(themoviedb))"))
        user = next(p for p in named if "ListItem.UserRating" in p.label())
        self.assertEqual(user.glyph, "bald/ratings/you.png")
        self.assertTrue(implies(user.visible, "$EXP[Bald_RatingUser]"))

    def test_default_rating_only_when_no_named_source_has_one(self):
        for pills, rating, others in (
            (self.pills, "Container(510).ListItem.Rating", [f"Container(510).ListItem.Rating({n})" for n in SOURCES]),
            # The player's default rating gives way to any TMDb Helper value, while online ratings are on.
            (self.player, "VideoPlayer.Rating",
             [f"!$EXP[Bald_RatingsOnlinePlayer] | String.IsEmpty({PLAYER.format(k)})" for k in HELPER]
             + [f"!$EXP[Bald_HelperPlayerRatings] | String.IsEmpty({BALD_PLAYER.format(k)})" for k in BALD]),
        ):
            with self.subTest(rating=rating):
                default = [p for p in pills if p.glyph == DEFAULT_GLYPH]
                self.assertEqual(len(default), 1)
                default = default[0]
                self.assertTrue(implies(default.visible, "$EXP[Bald_RatingDefault]"))
                for other in others:
                    condition = other if "|" in other else f"String.IsEmpty({other})"
                    self.assertTrue(implies(default.visible, condition), condition)
                # The source setting picks the format: a 0-100 score (with its unit) or the value as Kodi prints it.
                plain = [b for b in default.values if b.findtext("label").startswith(f"$INFO[{rating}]")]
                score = [b for b in default.values
                         if b.findtext("label").startswith(f"$MAP[Bald_RatingPercent, {rating}]$VAR[Bald_RatingDefaultUnit]")]
                self.assertEqual((len(plain), len(score)), (2, 2))
                for button in plain:
                    self.assertTrue(implies(button.findtext("visible"), "!$EXP[Bald_RatingDefaultScore]"))
                for button in score:
                    self.assertTrue(implies(button.findtext("visible"), "$EXP[Bald_RatingDefaultScore]"))

    def test_default_source_picks_glyph_and_format(self):
        def values(name):
            return [(v.get("condition"), v.text or "") for v in self.root.find(f"variable[@name='{name}']").findall("value")]

        def pick(name, atoms):
            """The first value whose condition holds, as Kodi picks it."""
            return next(text for condition, text in values(name) if condition is None or implies("true", condition, assume=atoms))

        score = self.root.find("expression[@name='Bald_RatingDefaultScore']").text
        for value, (glyph, unit) in DEFAULT_SOURCES.items():
            with self.subTest(value=value):
                atoms = {f"String.IsEqual({DEFAULT_SOURCE},{v})": v == value for v in DEFAULT_SOURCES if v}
                self.assertEqual(pick("Bald_RatingDefaultGlyph", atoms), f"bald/ratings/{glyph}.png")
                self.assertEqual(implies("true", score, assume=atoms), unit is not None)
                self.assertEqual(implies(score, "false", assume=atoms), unit is None)
                if unit is not None:
                    self.assertEqual(pick("Bald_RatingDefaultUnit", atoms), unit)
                name = pick("Bald_RatingDefaultSourceName", atoms)
                self.assertRegex(name, r"^\$LOCALIZE\[\d+\]$")
        names = [text for _condition, text in values("Bald_RatingDefaultSourceName")]
        self.assertEqual(len(set(names)), len(DEFAULT_SOURCES))

    def test_one_pill_per_source_with_a_named_default(self):
        """A named default source never shows next to TMDb Helper's value for the same source."""
        asked = pills(expand_call("Bald_Ratings", {"container": "Container(5000)."}, self.definitions))
        default = next(p for p in asked if p.glyph == DEFAULT_GLYPH)
        for value, key in FALLBACK_SOURCES.items():
            with self.subTest(value=value):
                helper = next(p for p in asked if f"TMDbHelper.ListItem.{key})" in p.label())
                same = f"String.IsEqual({DEFAULT_SOURCE},{value})"
                self.assertTrue(implies(f"[{helper.visible}] + [{default.visible}] + {same}", "false"))
                # With another choice both can show (they are different sources).
                self.assertFalse(implies(f"[{helper.visible}] + [{default.visible}] + !{same}", "false"))

    def test_vote_counts_are_an_option_and_never_show_zero(self):
        with_votes = [(p, b) for p in self.pills for b in p.values if "· $INFO[" in b.findtext("label")]
        self.assertTrue(with_votes)
        for pill, button in with_votes:
            shows = pill.shows(button)
            votes = re.search(r"· \$INFO\[(.+?)\]\[/COLOR\]", button.findtext("label")).group(1)
            self.assertTrue(implies(shows, "$EXP[Bald_RatingVotes]"))
            # Kodi prints "0" without votes; TMDb Helper and Bald Helper publish no vote property at all then.
            empty = f"!String.IsEmpty({votes})" if "Window(Home)" in votes else f"!String.IsEqual({votes},0)"
            self.assertTrue(implies(shows, empty), votes)
        for pill in self.named():
            self.assertEqual(len(pill.values), 2)
            plain, votes = (b.findtext("visible") for b in pill.values)
            # Without the vote option every pill shows its plain value, and exactly one of the two always shows.
            self.assertTrue(implies("!$EXP[Bald_RatingVotes]", plain))
            self.assertTrue(implies(f"[{plain}] + [{votes}]", "false"))
            self.assertTrue(equivalent(f"[{plain}] | [{votes}]", "true"))

    def helper_pills(self, found, prefix="ListItem"):
        return [p for p in found if p.values and f"TMDbHelper.{prefix}." in p.label()]

    def test_every_tmdb_helper_rating_has_a_pill(self):
        """One pill per published rating, with its glyph, format and switch, only where the library has none."""
        found = self.helper_pills(self.pills)
        self.assertEqual(len(found), len(HELPER))
        for key, (glyph, toggle, unit, names) in HELPER.items():
            with self.subTest(key=key):
                pill = next(p for p in found if f"{LISTITEM.format(key)}]" in p.label())
                self.assertEqual(pill.glyph, f"bald/ratings/{glyph}.png")
                self.assertEqual(pill.label(), f"$INFO[{LISTITEM.format(key)}]{unit}")
                self.assertTrue(implies(pill.visible, f"$EXP[{toggle}]"))
                self.assertTrue(implies(pill.visible, f"!String.IsEmpty({LISTITEM.format(key)})"))
                for name in names:
                    self.assertTrue(implies(pill.visible, f"String.IsEmpty(Container(510).ListItem.Rating({name}))"))
        # The player shows the same sources from its own monitor, under the same switches.
        player = self.helper_pills(self.player, "Player")
        self.assertEqual(len(player), len(HELPER))
        for key, (glyph, toggle, unit, _names) in HELPER.items():
            pill = next(p for p in player if f"{PLAYER.format(key)}]" in p.label())
            self.assertEqual(pill.glyph, f"bald/ratings/{glyph}.png")
            self.assertTrue(implies(pill.visible, f"$EXP[{toggle}] + $EXP[Bald_RatingsOnlinePlayer]"))

    def test_tmdb_helper_pills_are_guarded_on_every_surface(self):
        """A TMDb Helper value shows only for the item it belongs to: never mid-update, never on an identity mismatch."""
        surfaces = {
            # Home's caption, shared by the library views (510, 512, 513, 515, 520-523, 530, 531) and More like this.
            "Home and library caption": (expand_call("Bald_Caption", {"c": "9101", "p": "Odd"}, self.definitions),
                                         "Container(9101)."),
            "artwork list 514": (expand_call("Bald_RatingsRow", {"container": "Container(514)."}, self.definitions),
                                 "Container(514)."),
            "browse preview and info screens": (expand_call("Bald_RatingsRow", {}, self.definitions), ""),
            "TV info episode line": (expand_call("Bald_Ratings", {"container": "Container(5302)."}, self.definitions),
                                     "Container(5302)."),
        }
        for surface, (nodes, container) in surfaces.items():
            found = self.helper_pills(pills(nodes))
            with self.subTest(surface=surface):
                self.assertEqual(len(found), len(HELPER))
                for pill in found:
                    self.assertTrue(implies(pill.visible, guard(container)), pill.label())
                    self.assertTrue(implies(pill.visible, "$EXP[Bald_HasTMDbHelper]"))
                    # Loading: the previous item's ratings are still published.
                    for busy in ("IsUpdating", "IsUpdatingRatings"):
                        loading = f"[{pill.visible}] + !String.IsEmpty(Window(Home).Property(TMDbHelper.{busy}))"
                        self.assertTrue(implies(loading, "false"))
                    # Mismatched: TMDb Helper's identity is another item's.
                    self.assertTrue(implies(pill.visible, "false", assume=mismatch(pill.visible)), pill.label())
        # fallback false turns them off; no caller does.
        off = self.helper_pills(pills(expand_call("Bald_Ratings", {"container": "Container(510).", "fallback": "false"},
                                                  self.definitions)))
        for pill in off:
            self.assertTrue(implies(pill.visible, "false"))
        for path in SKIN.glob("*.xml"):
            self.assertNotIn('<param name="fallback">false</param>', path.read_text(), path.name)
        # Bald_Ratings and Bald_RatingsRow build the same guard.
        text = RATINGS.read_text()
        helpers = re.findall(r'<param name="helper">(\[\$PARAM\[fallback\]\][^<]+)</param>', text)
        self.assertEqual(len(helpers), 2)
        self.assertEqual(helpers[0], helpers[1])

    def test_home_keeps_tmdb_helper_on_the_focused_row(self):
        """The Home caption follows the focused row, so TMDb Helper must too while online ratings are on (even with
        Bald Helper making the blur): every row sets the widget container when it gains focus (row to row, from the
        menu, back from a dialog), and Home starts on row 9101."""
        row = include_definitions()["Bald_Row"]
        fixedlist = next(c for c in row.iter("control") if c.get("type") == "fixedlist")
        focus = {n.text: n.get("condition") for n in expand_follow(fixedlist) if n.tag == "onfocus"}
        condition = focus["SetProperty(TMDbHelper.WidgetContainer,$PARAM[id],home)"]
        # (An enabled row: Home's rows while Home is hidden set nothing.)
        self.assertTrue(implies("$EXP[Bald_RatingsOnline] + !$EXP[Bald_ReturningToMenu] + $PARAM[enabled]", condition))
        home = ET.parse(SKIN / "Home.xml").getroot()
        loads = {n.text: n.get("condition") for n in expand_follow(home) if n.tag == "onload"}
        self.assertTrue(implies("$EXP[Bald_RatingsOnline] + !$EXP[Bald_ReturningToMenu]",
                                loads["SetProperty(TMDbHelper.WidgetContainer,$VAR[Bald_StartRow],home)"]))
        import home_menu
        self.assertEqual(home_menu.variable_value("Bald_StartRow", home_menu.HOME_SHOWN), "9101")
        self.assertEqual(home.findtext("defaultcontrol"), "9101")

    def test_home_runs_tmdb_helpers_monitor_with_online_ratings(self):
        """TMDb Helper's ListItem monitor idles unless the skin sets TMDbHelper.Service."""
        home = ET.parse(SKIN / "Home.xml").getroot()
        actions = {(n.get("condition"), n.text) for n in home.findall("onload")}
        self.assertIn(("$EXP[Bald_RatingsOnline] + !Skin.HasSetting(TMDbHelper.Service)",
                       "Skin.SetBool(TMDbHelper.Service)"), actions)
        self.assertIn(("!$EXP[Bald_RatingsOnline] + Skin.HasSetting(TMDbHelper.Service)",
                       "Skin.Reset(TMDbHelper.Service)"), actions)
        online = self.root.find("expression[@name='Bald_RatingsOnline']").text
        self.assertTrue(equivalent(online, "$EXP[Bald_HasTMDbHelper] + !Skin.HasSetting(Bald.Ratings.NoOnline)"
                                           " + !$EXP[Bald_HelperRatings]"))

    def test_online_ratings_rows(self):
        row = self.appearance.find(f".//control[@id='{ONLINE_ROW}']")
        self.assertEqual(row.get("type"), "radiobutton")
        self.assertEqual(row.findtext("label"), "$VAR[Bald_RatingsOnlineLabel]")
        either = "[$EXP[Bald_HasHelper] | $EXP[Bald_HasTMDbHelper]]"
        self.assertTrue(equivalent(row.findtext("selected"), f"!Skin.HasSetting(Bald.Ratings.NoOnline) + {either}"))
        # Greyed without either helper (and with ratings off).
        self.assertTrue(equivalent(row.findtext("enable"), f"!Skin.HasSetting(Bald.Ratings.Hide) + {either}"))
        self.assertTrue(implies(" + ".join(n.text for n in row.findall("visible")), "Container(9500).HasFocus(6)"))
        # Kodi checks every onclick condition first: TMDb Helper's service follows the value the toggle is about to
        # set, but is not started while Bald Helper supplies the ratings.
        clicks = [(n.get("condition"), n.text) for n in row.findall("onclick")]
        self.assertEqual(clicks, [("Skin.HasSetting(Bald.Ratings.NoOnline) + !$EXP[Bald_HelperRatingsReady]",
                                   "Skin.SetBool(TMDbHelper.Service)"),
                                  ("!Skin.HasSetting(Bald.Ratings.NoOnline)", "Skin.Reset(TMDbHelper.Service)"),
                                  (None, "Skin.ToggleSetting(Bald.Ratings.NoOnline)")])
        # The next row opens the provider's settings, where the key is entered: Bald Helper's when it is installed.
        button = self.appearance.find(f".//control[@id='{HELPER_SETTINGS_ROW}']")
        self.assertEqual(button.get("type"), "button")
        self.assertEqual([(n.get("condition"), n.text) for n in button.findall("onclick")],
                         [("$EXP[Bald_HasHelper]", "Addon.OpenSettings(script.bald.helper)"),
                          ("!$EXP[Bald_HasHelper]", "Addon.OpenSettings(plugin.video.themoviedb.helper)")])
        self.assertTrue(equivalent(button.findtext("enable"), either))
        self.assertEqual((button.findtext("label"), button.findtext("label2")),
                         ("$VAR[Bald_RatingsProviderLabel]", "$VAR[Bald_RatingsProviderKey]"))
        for name, helper, tmdb in (("Bald_RatingsOnlineLabel", 31331, 31323), ("Bald_RatingsProviderLabel", 31332, 31324),
                                   ("Bald_RatingsProviderKey", 31333, 31325)):
            values = [(v.get("condition"), v.text) for v in self.root.find(f"variable[@name='{name}']")]
            self.assertEqual(values, [("$EXP[Bald_HasHelper]", f"$LOCALIZE[{helper}]"), (None, f"$LOCALIZE[{tmdb}]")])
        self.assertEqual(strings()[31333], "MDbList API key")
        ids = [c.get("id") for c in self.appearance.find(".//control[@id='9600']").findall("control")]
        self.assertEqual(ids.index(ONLINE_ROW), ids.index("9641") + 1)
        self.assertEqual(ids.index(HELPER_SETTINGS_ROW), ids.index(ONLINE_ROW) + 1)
        # The category note says where the key goes for either provider.
        note = strings()[31301]
        for words in ("Bald Helper", "MDbList API key", "TMDb Helper", "Use online ratings in details monitor"):
            self.assertIn(words, note)
        # Bald never asks for a key or calls a ratings API itself.
        skin = "\n".join(p.read_text() for p in SKIN.glob("*.xml"))
        for word in ("omdb_apikey", "mdblist_apikey", "apikey=", "mdblist_key"):
            self.assertNotIn(word, skin)

    def test_tmdb_helper_source_rows(self):
        for control_id, (setting, on_by_default) in HELPER_ROWS.items():
            with self.subTest(row=control_id):
                row = self.appearance.find(f".//control[@id='{control_id}']")
                self.assertEqual(row.get("type"), "radiobutton")
                self.assertEqual([n.text for n in row.findall("onclick")], [f"Skin.ToggleSetting({setting})"])
                expected = f"!Skin.HasSetting({setting})" if on_by_default else f"Skin.HasSetting({setting})"
                self.assertTrue(equivalent(row.findtext("selected"), expected))
                self.assertTrue(equivalent(row.findtext("enable"),
                                           "!Skin.HasSetting(Bald.Ratings.Hide) + $EXP[Bald_RatingsOnlineAny]"))
                self.assertTrue(implies(" + ".join(n.text for n in row.findall("visible")), "Container(9500).HasFocus(6)"))
                expression = next(toggle for _g, toggle, _u, _n in HELPER.values()
                                  if setting in self.root.find(f"expression[@name='{toggle}']").text)
                self.assertTrue(equivalent(f"$EXP[{expression}]", expected))
        ids = [c.get("id") for c in self.appearance.find(".//control[@id='9600']").findall("control")]
        self.assertEqual(ids[ids.index("9648") + 1:ids.index("9648") + 6], list(HELPER_ROWS))

    def bald_pills(self, found, prefix="Ratings"):
        return [p for p in found if p.values and f"Bald.{prefix}." in p.label()]

    def test_every_bald_helper_rating_has_a_pill(self):
        """Beside each TMDb Helper pill, Bald Helper's for the same source: same glyph, format, switch and library rule."""
        found = self.bald_pills(self.pills)
        self.assertEqual(len(found), len(BALD))
        for key, tmdb_key in BALD.items():
            glyph, toggle, unit, names = HELPER[tmdb_key]
            with self.subTest(key=key):
                pill = next(p for p in found if f"{BALD_LISTITEM.format(key)}]" in p.label())
                self.assertEqual(pill.glyph, f"bald/ratings/{glyph}.png")
                self.assertEqual(pill.label(), f"$INFO[{BALD_LISTITEM.format(key)}]{unit}")
                self.assertTrue(implies(pill.visible, f"$EXP[{toggle}]"))
                self.assertTrue(implies(pill.visible, f"!String.IsEmpty({BALD_LISTITEM.format(key)})"))
                for name in names:
                    self.assertTrue(implies(pill.visible, f"String.IsEmpty(Container(510).ListItem.Rating({name}))"))
                # It sits right after TMDb Helper's pill for the source.
                tmdb = next(i for i, p in enumerate(self.pills) if f"{LISTITEM.format(tmdb_key)}]" in p.label())
                self.assertIs(self.pills[tmdb + 1], pill)
        player = self.bald_pills(self.player, "Player.Ratings")
        self.assertEqual(len(player), len(BALD))
        for key, tmdb_key in BALD.items():
            glyph, toggle, _unit, _names = HELPER[tmdb_key]
            pill = next(p for p in player if f"{BALD_PLAYER.format(key)}]" in p.label())
            self.assertEqual(pill.glyph, f"bald/ratings/{glyph}.png")
            self.assertTrue(implies(pill.visible, f"$EXP[{toggle}] + $EXP[Bald_RatingsOSD] + $EXP[Bald_HelperPlayerRatings]"))

    def test_bald_helper_pills_are_guarded_on_every_surface(self):
        """A Bald Helper value shows only for the item whose identity it carries, and never while that is cleared."""
        surfaces = {
            "Home and library caption": (expand_call("Bald_Caption", {"c": "9101", "p": "Odd"}, self.definitions),
                                         "Container(9101)."),
            "artwork list 514": (expand_call("Bald_RatingsRow", {"container": "Container(514)."}, self.definitions),
                                 "Container(514)."),
            "browse preview and info screens": (expand_call("Bald_RatingsRow", {}, self.definitions), ""),
            "TV info episode line": (expand_call("Bald_Ratings", {"container": "Container(5302)."}, self.definitions),
                                     "Container(5302)."),
        }
        for surface, (nodes, container) in surfaces.items():
            found = self.bald_pills(pills(nodes))
            with self.subTest(surface=surface):
                self.assertEqual(len(found), len(BALD))
                for pill in found:
                    self.assertTrue(implies(pill.visible, bald_guard(container)), pill.label())
                    self.assertTrue(implies(pill.visible, "$EXP[Bald_HasHelper]"))
                    # The helper clears DBType first when the item changes and writes it last.
                    cleared = f"[{pill.visible}] + String.IsEmpty(Window(Home).Property(Bald.Ratings.DBType))"
                    self.assertTrue(implies(cleared, "false"))
                    # Another item's identity: every comparison fails.
                    other = {a: False for a in atoms(pill.visible)
                             if a.startswith("String.IsEqual(Window(Home).Property(Bald.Ratings.")}
                    self.assertTrue(implies(pill.visible, "false", assume=other), pill.label())
        # fallback false turns them off too.
        off = self.bald_pills(pills(expand_call("Bald_Ratings", {"container": "Container(510).", "fallback": "false"},
                                                self.definitions)))
        self.assertTrue(off)
        for pill in off:
            self.assertTrue(implies(pill.visible, "false"))
        # Bald_Ratings and Bald_RatingsRow build the same guard.
        guards = re.findall(r'<param name="bald">(\[\$PARAM\[fallback\]\][^<]+)</param>', RATINGS.read_text())
        self.assertEqual(len(guards), 2)
        self.assertEqual(guards[0], guards[1])

    def test_one_provider_at_a_time(self):
        """With Bald Helper's ratings in use every TMDb Helper pill is off, and without them every Bald Helper pill."""
        for pill in self.helper_pills(self.pills):
            self.assertTrue(implies(f"[{pill.visible}] + $EXP[Bald_HelperRatings]", "false"), pill.label())
        for pill in self.helper_pills(self.player, "Player"):
            self.assertTrue(implies(f"[{pill.visible}] + $EXP[Bald_HelperPlayerRatings]", "false"), pill.label())
        for pill in self.bald_pills(self.pills) + self.bald_pills(self.player, "Player.Ratings"):
            self.assertTrue(implies(f"[{pill.visible}] + !$EXP[Bald_HelperRatings]", "false"), pill.label())
        # The player keeps TMDb Helper's values while Bald Helper has none for what is playing (an episode).
        tmdb = next(p for p in self.helper_pills(self.player, "Player") if "imdb_rating" in p.label())
        self.assertFalse(implies(f"[{tmdb.visible}] + $EXP[Bald_HelperRatings]", "false"))
        # Bald Helper's readiness is its service's property plus the add-on being there and enabled.
        ready = self.root.find("expression[@name='Bald_HelperRatingsReady']").text
        self.assertTrue(equivalent(ready, "$EXP[Bald_HasHelper]"
                                          " + String.IsEqual(Window(home).Property(Bald.Helper.Ratings),1)"))
        helper = self.root.find("expression[@name='Bald_HelperRatings']").text
        self.assertTrue(equivalent(helper, "$EXP[Bald_HelperRatingsReady] + !Skin.HasSetting(Bald.Ratings.NoOnline)"))

    def test_one_pill_per_source_with_bald_helper(self):
        asked = pills(expand_call("Bald_Ratings", {"container": "Container(5000)."}, self.definitions))
        default = next(p for p in asked if p.glyph == DEFAULT_GLYPH)
        for value, tmdb_key in FALLBACK_SOURCES.items():
            key = next(k for k, v in BALD.items() if v == tmdb_key)
            with self.subTest(value=value):
                pill = next(p for p in asked if f"Bald.Ratings.{key})" in p.label())
                same = f"String.IsEqual({DEFAULT_SOURCE},{value})"
                self.assertTrue(implies(f"[{pill.visible}] + [{default.visible}] + {same}", "false"))
                self.assertFalse(implies(f"[{pill.visible}] + [{default.visible}] + !{same}", "false"))

    def test_row_hides_when_nothing_shows(self):
        row = expand_call("Bald_RatingsRow", {"container": "Container(510).", "visible": "$EXP[Bald_RatingsLibrary]"},
                          self.definitions)[0]
        visible = row.findtext("visible")
        self.assertTrue(implies(visible, "$EXP[Bald_RatingsLibrary]"))
        # Any pill that can show implies the row shows.
        found = pills([row])
        self.assertEqual(len(found), len(self.pills))
        for pill in found:
            self.assertTrue(implies(f"[{pill.visible}] + $EXP[Bald_RatingsLibrary]", visible), pill.label())

    def test_percent_map_turns_kodis_tenths_back_into_scores(self):
        entries = {e.get("key"): e.text for e in self.root.find("map[@name='Bald_RatingPercent']")}
        self.assertEqual(len(entries), 202)
        for key, value in (("7.8", "78"), ("7,8", "78"), ("10.0", "100"), ("10,0", "100"), ("0.5", "5"), ("9.1", "91")):
            self.assertEqual(entries[key], value, key)

    def test_pill_is_quiet_and_uses_shipped_tokens(self):
        pill = self.pills[0]
        # The left end and the value's fill are the two halves of one 10% ink pill.
        self.assertEqual(pill.lead.find("texture").get("colordiffuse"), "bald_ink10")
        self.assertEqual(pill.lead.findtext("texture"), "bald/chip_fill_l.png")
        for button in pill.values:
            self.assertEqual(button.findtext("enable"), "false")
            self.assertEqual(button.findtext("width"), "auto")
            self.assertEqual(button.find("texturenofocus").get("colordiffuse"), "bald_ink10")
            self.assertEqual(button.findtext("texturenofocus"), "bald/chip_fill_r.png")
        # The glyph is tinted with a palette token, never a brand colour.
        self.assertEqual(pill.glyph_image.find("texture").get("colordiffuse"), "bald_accent")
        self.assertEqual(pill.glyph_image.findtext("aspectratio"), "keep")
        text = RATINGS.read_text()
        for texture in set(re.findall(r">(bald/[\w/]+\.png)<", text)):
            self.assertTrue((ROOT / "media" / texture).exists(), texture)
        colors = {c.get("name") for c in ET.parse(ROOT / "colors" / "defaults.xml").getroot()}
        for token in re.findall(r"\[COLOR (\w+)\]", text) + re.findall(r'colordiffuse="(\w+)"', text):
            self.assertIn(token, colors)
        fonts = {f.findtext("name") for f in ET.parse(SKIN / "Font.xml").getroot().iter("font")}
        for font in set(re.findall(r'<param name="font">(\w+)</param>', text)):
            self.assertIn(font, fonts)

    def test_pill_geometry_follows_its_height(self):
        """Constants by pill height: 8 px, the glyph, then the value; the glyph centred and pulled back over the end."""
        for height in ("26", "30"):
            with self.subTest(height=height):
                frame = pills(expand_call("Bald_RatingFrame", {"glyph": "bald/ratings/imdb.png", "height": height},
                                          self.definitions))[0]
                size = int(frame.glyph_image.findtext("width"))
                self.assertEqual(int(frame.glyph_image.findtext("height")), size)
                self.assertEqual(int(frame.lead.findtext("width")), 8 + size)
                self.assertEqual(int(frame.glyph_image.findtext("left")), -size)
                self.assertEqual(int(frame.glyph_image.findtext("top")) * 2 + size, int(height))
                self.assertEqual(frame.node.findtext("height"), height)
        # Every caller's pill height has its constants.
        heights = set(re.findall(r'<param name="height">(\d+)</param>', "\n".join(
            p.read_text() for p in SKIN.glob("*.xml") if "Rating" in p.read_text())))
        for height in heights & {"26", "30"}:
            self.assertIn(f"Bald_RatingGlyph{height}", (SKIN / "Includes_Bald_Constants.xml").read_text())

    def test_every_glyph_is_shipped_and_generated(self):
        referenced = set(re.findall(r"bald/ratings/(\w+)\.png", RATINGS.read_text()))
        tool = glyph_names()
        self.assertEqual(referenced, set(tool.GLYPHS), "every glyph the skin uses comes from tools/rating_glyphs.py")
        for name, (svg, slug) in tool.GLYPHS.items():
            with self.subTest(glyph=name):
                self.assertTrue((GLYPHS / f"{name}.png").exists())
                self.assertTrue((tool.SRC / svg).exists())
                if slug:  # a Simple Icons mark, kept as downloaded
                    self.assertIn('viewBox="0 0 24 24"', (tool.SRC / svg).read_text())
        self.assertEqual({p.stem for p in GLYPHS.glob("*.png")}, set(tool.GLYPHS))
        # The licence note ships next to the glyphs.
        note = (GLYPHS / "README.md").read_text()
        self.assertIn("CC0", note)
        self.assertIn("trademark", note)

    def test_strings_are_in_the_ratings_block(self):
        texts = strings()
        used = {int(n) for n in re.findall(r"\$LOCALIZE\[(\d+)\]", RATINGS.read_text())}
        rows = "".join(ET.tostring(self.appearance.find(f".//control[@id='{i}']"), encoding="unicode")
                       for i in ALL_ROWS)
        rows += ET.tostring(self.appearance.find(".//control[@id='9500']/content/item[@id='6']"), encoding="unicode")
        used |= {int(n) for n in re.findall(r"\$LOCALIZE\[(\d+)\]", rows)}
        for num in used:
            with self.subTest(string=num):
                # Bald's own ratings strings, or a Kodi core string reused (563 Rating, 38018 My rating).
                self.assertTrue(num in RATINGS_RANGE or not 31000 <= num <= 31999, num)
                if num in RATINGS_RANGE:
                    self.assertIn(num, texts)
        # Home hubs (31200-31299) and music (31400-31499) share Estuary's unused gap; every other string there is a
        # ratings string.
        ours = [num for num in texts if 31178 <= num <= 31596 and not 31200 <= num < 31300 and not 31400 <= num < 31500]
        self.assertTrue(ours)
        self.assertTrue(all(num in RATINGS_RANGE for num in ours), ours)

    def test_control_ids_are_recorded(self):
        ids = (SKIN / "IDs").read_text()
        self.assertIn("9641-9663", ids)
        self.assertIn("1, 2, 6, 3, 7 and 5", ids)
        for control_id in ALL_ROWS:
            self.assertIn(control_id, ids)


if __name__ == "__main__":
    unittest.main()
