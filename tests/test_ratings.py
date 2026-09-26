"""Ratings in media views (Includes_Bald_Ratings.xml) and their settings in Appearance > Ratings (window 1118)."""

import importlib.util
import re
import unittest
import xml.etree.ElementTree as ET

from conditions import equivalent, implies
from kodi_includes import SKIN, expand_call, include_definitions, resolve_window
from skin_strings import RATINGS_RANGE, strings

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
DEFAULT_SOURCE = "Skin.String(Bald.Ratings.DefaultSource)"
# Default rating source value, in cycle order -> (glyph, unit after the 0-100 score, or None for Kodi's 0-10 value);
# "" is Generic.
DEFAULT_SOURCES = {"": ("rating", None), "imdb": ("imdb", None), "tmdb": ("tmdb", "%"), "rt": ("rt", "%"),
                   "rtaudience": ("rt_audience", "%"), "metacritic": ("metacritic", ""), "trakt": ("trakt", "%"),
                   "jellyfin": ("jellyfin", None), "kodi": ("kodi", None)}
# Default rating source value -> the TMDb Helper fallback it stands in for (hidden when the default pill shows).
FALLBACK_SOURCES = {"rt": "rottentomatoes_rating", "rtaudience": "rottentomatoes_usermeter",
                    "metacritic": "metacritic_rating", "trakt": "trakt_rating"}
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
    spec = importlib.util.spec_from_file_location("rating_glyphs", ROOT / "tools" / "rating_glyphs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        self.assertEqual(read, set(ROWS.values()))
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
            (self.player, "VideoPlayer.Rating", ["Window(Home).Property(TMDbHelper.Player.imdb_rating)"]),
        ):
            with self.subTest(rating=rating):
                default = [p for p in pills if p.glyph == DEFAULT_GLYPH]
                self.assertEqual(len(default), 1)
                default = default[0]
                self.assertTrue(implies(default.visible, "$EXP[Bald_RatingDefault]"))
                for other in others:
                    self.assertTrue(implies(default.visible, f"String.IsEmpty({other})"))
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
        asked = pills(expand_call("Bald_Ratings", {"container": "Container(5000).", "fallback": "true"}, self.definitions))
        default = next(p for p in asked if p.glyph == DEFAULT_GLYPH)
        for value, key in FALLBACK_SOURCES.items():
            with self.subTest(value=value):
                helper = next(p for p in asked if f"TMDbHelper.ListItem.{key}" in p.label())
                same = f"String.IsEqual({DEFAULT_SOURCE},{value})"
                self.assertTrue(implies(f"[{helper.visible}] + [{default.visible}] + {same}", "false"))
                # With another choice both can show (they are different sources).
                self.assertFalse(implies(f"[{helper.visible}] + [{default.visible}] + !{same}", "false"))

    def test_vote_counts_are_an_option_and_never_show_zero(self):
        with_votes = [(p, b) for p in self.pills for b in p.values if "· $INFO[" in b.findtext("label")]
        self.assertTrue(with_votes)
        for pill, button in with_votes:
            shows = pill.shows(button)
            votes = re.search(r"\$INFO\[([^\]]+Votes[^\]]*)\]", button.findtext("label")).group(1)
            self.assertTrue(implies(shows, "$EXP[Bald_RatingVotes]"))
            self.assertTrue(implies(shows, f"!String.IsEqual({votes},0)"))
        for pill in self.named():
            self.assertEqual(len(pill.values), 2)
            plain, votes = (b.findtext("visible") for b in pill.values)
            # Without the vote option every pill shows its plain value, and exactly one of the two always shows.
            self.assertTrue(implies("!$EXP[Bald_RatingVotes]", plain))
            self.assertTrue(implies(f"[{plain}] + [{votes}]", "false"))
            self.assertTrue(equivalent(f"[{plain}] | [{votes}]", "true"))

    def test_tmdb_helper_fallback_only_when_asked_for_and_installed(self):
        fallback = [p for p in self.pills if "TMDbHelper.ListItem" in p.label()]
        self.assertEqual(len(fallback), 4)  # RT critics and audience, Metacritic, Trakt
        for pill in fallback:
            self.assertTrue(implies(pill.visible, "false"), "the default call must not show TMDb Helper values")
        asked = pills(expand_call("Bald_Ratings", {"fallback": "true"}, self.definitions))
        for pill in asked:
            if "TMDbHelper.ListItem" in pill.label():
                self.assertTrue(implies(pill.visible, "$EXP[Bald_HasTMDbHelper]"))
        info = (SKIN / "Includes_Bald_InfoPages.xml").read_text()
        self.assertEqual(info.count('<param name="fallback">true</param>'), 1)
        for name in ("Includes_Bald_Home.xml", "Includes_Bald_Browse.xml", "View_510_Bald_Posters.xml"):
            self.assertNotIn('<param name="fallback">true</param>', (SKIN / name).read_text())

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
                       for i in [*ROWS, SOURCE_ROW])
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
        self.assertIn("9641-9656", ids)
        self.assertIn("1, 2, 6, 3 and 5", ids)
        for control_id in [*ROWS, SOURCE_ROW]:
            self.assertIn(control_id, ids)


if __name__ == "__main__":
    unittest.main()
