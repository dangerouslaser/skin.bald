"""Spoiler protection (Includes_Bald_Spoilers.xml): the opt-in setting, the per-item rule (play count 0 and no resume
point), and every place Bald shows a plot or an episode still honouring it. Bald Helper's side is
tests/test_bald_helper_spoilers.py; here only the names the two share."""

import importlib.util
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import equivalent, implies
from kodi_includes import NATIVE, SKIN, expressions, resolve_window
from skin_strings import loc

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "bald_helper_spoilers_names", ROOT / "addons" / "script.bald.helper" / "resources" / "lib" / "spoilers.py")
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)

SPOILERS = ET.parse(SKIN / "Includes_Bald_Spoilers.xml").getroot()
PLOT_ATOMS = ("Skin.HasSetting(Bald.Spoilers)", "Skin.HasSetting(Bald.Spoilers.ShowPlots)",
              "Skin.HasSetting(Bald.Spoilers.Movies)", "Skin.HasSetting(Bald.Spoilers.LiveTV)")
SUFFIXES = {"": "ListItem.", "0": "Container(0).ListItem.", "540": "Container(540).ListItem.",
            "541": "Container(541).ListItem.", "542": "Container(542).ListItem.", "50": "Container(50).ListItem.",
            "5100": "Container(5100).ListItem.", "8140": "Container(8140).ListItem.",
            "8150": "Container(8150).ListItem."}


def unwatched(p):
    return f"!Integer.IsGreater({p}PlayCount,0) + !{p}IsResumable"


def plot_rule(p):
    """What "this item's plot is hidden" means, written out once for any item prefix."""
    return (f"[Skin.HasSetting(Bald.Spoilers) + !Skin.HasSetting(Bald.Spoilers.ShowPlots) + String.IsEqual({p}DBType,episode) + {unwatched(p)}]"
            f" | [Skin.HasSetting(Bald.Spoilers) + Skin.HasSetting(Bald.Spoilers.Movies) + String.IsEqual({p}DBType,movie) + {unwatched(p)}]"
            f" | [Skin.HasSetting(Bald.Spoilers) + Skin.HasSetting(Bald.Spoilers.LiveTV) + [{p}HasEpg | [String.StartsWith({p}FileNameAndPath,pvr://recordings/) + {unwatched(p)}]]]"
            f" | String.IsEqual({p}Plot,$LOCALIZE[20370])")


def thumb_rule(p):
    return (f"[[[Skin.HasSetting(Bald.Spoilers) + !Skin.HasSetting(Bald.Spoilers.ShowThumbs)] | System.Setting(hideunwatchedepisodethumbs)] + String.IsEqual({p}DBType,episode) + {unwatched(p)}]"
            f" | [Skin.HasSetting(Bald.Spoilers) + Skin.HasSetting(Bald.Spoilers.LiveTV) + String.StartsWith({p}FileNameAndPath,pvr://recordings/) + {unwatched(p)}]")


def variable(root, name):
    node = root.find(f"variable[@name='{name}']")
    if node is None:
        raise AssertionError(f"no variable {name}")
    return [(value.get("condition"), value.text or "") for value in node.findall("value")]


def all_variables():
    found = {}
    for path in sorted(SKIN.glob("*.xml")):
        root = ET.parse(path).getroot()
        if root.tag == "includes":
            for node in root.findall("variable"):
                found.setdefault(node.get("name"), [(v.get("condition"), v.text or "") for v in node.findall("value")])
    return found


class RuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bodies = expressions()

    def test_settings_are_opt_in(self):
        off = "!Skin.HasSetting(Bald.Spoilers)"
        for name in ("Bald_SpoilerPlotsOn", "Bald_SpoilerMoviesOn", "Bald_SpoilerLiveTVOn", "Bald_SpoilersOn"):
            self.assertTrue(implies(off, f"!$EXP[{name}]", self.bodies), name)
        # Only Kodi's own "Episode thumb" option turns the stills on without Bald's switch.
        self.assertTrue(implies(f"{off} + !System.Setting(hideunwatchedepisodethumbs)", "!$EXP[Bald_SpoilerThumbsOn]",
                                self.bodies))
        self.assertTrue(implies("System.Setting(hideunwatchedepisodethumbs)", "$EXP[Bald_SpoilerThumbsOn]", self.bodies))
        # Under the switch, episode stills and plots are on until turned off; movies and Live TV off until asked for.
        on = "Skin.HasSetting(Bald.Spoilers)"
        self.assertTrue(implies(f"{on} + !Skin.HasSetting(Bald.Spoilers.ShowThumbs)", "$EXP[Bald_SpoilerThumbsOn]", self.bodies))
        self.assertTrue(implies(f"{on} + !Skin.HasSetting(Bald.Spoilers.ShowPlots)", "$EXP[Bald_SpoilerPlotsOn]", self.bodies))
        self.assertTrue(implies(f"{on} + !Skin.HasSetting(Bald.Spoilers.Movies)", "!$EXP[Bald_SpoilerMoviesOn]", self.bodies))
        self.assertTrue(implies(f"{on} + !Skin.HasSetting(Bald.Spoilers.LiveTV)", "!$EXP[Bald_SpoilerLiveTVOn]", self.bodies))

    def test_every_item_prefix_has_the_same_rule(self):
        for suffix, prefix in SUFFIXES.items():
            with self.subTest(prefix=prefix):
                self.assertTrue(equivalent(f"$EXP[Bald_SpoilerPlot{suffix}]", plot_rule(prefix), self.bodies))
                self.assertTrue(equivalent(f"$EXP[Bald_SpoilerThumb{suffix}]", thumb_rule(prefix), self.bodies))

    def test_the_includes_repeat_the_rule_for_any_prefix(self):
        def visible(name):
            return SPOILERS.find(f"include[@name='{name}']/definition/visible").text

        self.assertTrue(equivalent(visible("Bald_SpoilerPlotHidden"), plot_rule("$PARAM[item]"), self.bodies))
        self.assertTrue(equivalent(visible("Bald_SpoilerPlotShown"), f"![{plot_rule('$PARAM[item]')}]", self.bodies))
        still = SPOILERS.find("include[@name='Bald_SpoilerStill']/definition/control").findtext("visible")
        self.assertTrue(equivalent(still, f"[$PARAM[visible]] + [{thumb_rule('$PARAM[item]')}]", self.bodies))

    def test_partly_watched_and_watched_items_are_shown(self):
        p = "ListItem."
        everything_on = ("Skin.HasSetting(Bald.Spoilers) + Skin.HasSetting(Bald.Spoilers.Movies) + "
                         "Skin.HasSetting(Bald.Spoilers.LiveTV) + System.Setting(hideunwatchedepisodethumbs) + "
                         "!ListItem.HasEpg + !String.IsEqual(ListItem.Plot,$LOCALIZE[20370])")
        for state in ("ListItem.IsResumable", "Integer.IsGreater(ListItem.PlayCount,0)"):
            self.assertTrue(implies(f"{everything_on} + {state}", "!$EXP[Bald_SpoilerPlot]", self.bodies), state)
            self.assertTrue(implies(f"{everything_on} + {state}", "!$EXP[Bald_SpoilerThumb]", self.bodies), state)
        fresh = f"String.IsEqual({p}DBType,episode) + {unwatched(p)} + Skin.HasSetting(Bald.Spoilers)"
        self.assertTrue(implies(f"{fresh} + !Skin.HasSetting(Bald.Spoilers.ShowPlots)", "$EXP[Bald_SpoilerPlot]", self.bodies))
        self.assertTrue(implies(f"{fresh} + !Skin.HasSetting(Bald.Spoilers.ShowThumbs)", "$EXP[Bald_SpoilerThumb]", self.bodies))

    def test_live_tv_hides_programmes_but_never_the_channel_logo(self):
        self.assertTrue(implies("Skin.HasSetting(Bald.Spoilers) + Skin.HasSetting(Bald.Spoilers.LiveTV) + ListItem.HasEpg",
                                "$EXP[Bald_SpoilerPlot] + $EXP[Bald_SpoilerEpgArt] + !$EXP[Bald_PVRHasArt]", self.bodies))
        self.assertEqual(variable(ET.parse(SKIN / "Includes_Bald_PVR.xml").getroot(), "Bald_PVRLogo")[0][1],
                         "$INFO[ListItem.ChannelLogo]")

    def test_kodis_own_hidden_plot_shows_balds_note(self):
        self.assertTrue(implies("String.IsEqual(ListItem.Plot,$LOCALIZE[20370])", "$EXP[Bald_SpoilerPlot]", self.bodies))


class SettingsTests(unittest.TestCase):
    def test_rows_in_appearance_information(self):
        root = resolve_window("Custom_1118_BaldAppearance.xml")
        rows = {
            "9616": ("Hide spoilers for unwatched items", "Skin.HasSetting(Bald.Spoilers)", "Bald.Spoilers"),
            "9617": ("Blur episode thumbnails", "!Skin.HasSetting(Bald.Spoilers.ShowThumbs)", "Bald.Spoilers.ShowThumbs"),
            "9618": ("Hide episode plots", "!Skin.HasSetting(Bald.Spoilers.ShowPlots)", "Bald.Spoilers.ShowPlots"),
            "9619": ("Hide movie plots", "Skin.HasSetting(Bald.Spoilers.Movies)", "Bald.Spoilers.Movies"),
            "9620": ("Hide Live TV descriptions and recordings", "Skin.HasSetting(Bald.Spoilers.LiveTV)",
                     "Bald.Spoilers.LiveTV"),
        }
        for row_id, (label, selected, setting) in rows.items():
            with self.subTest(row=row_id):
                row = root.find(f".//control[@id='{row_id}']")
                self.assertEqual(row.get("type"), "radiobutton")
                self.assertEqual(row.findtext("label"), loc(label))
                self.assertTrue(equivalent(row.findtext("selected"), selected))
                self.assertEqual(row.findtext("onclick"), f"Skin.ToggleSetting({setting})")
                # Information category (item 2).
                self.assertTrue(any("Container(9500).HasFocus(2)" in (v.text or "") for v in row.findall("visible")))
                if row_id != "9616":
                    self.assertEqual(row.findtext("enable"), "Skin.HasSetting(Bald.Spoilers)")

    def test_notes_are_bald_strings(self):
        self.assertIn(loc("Plot hidden, not watched yet"), ET.tostring(SPOILERS, encoding="unicode"))
        self.assertIn(loc("Description hidden to avoid spoilers"), ET.tostring(SPOILERS, encoding="unicode"))


class HelperNamesTests(unittest.TestCase):
    def test_the_helper_turns_on_with_the_skins_still_condition(self):
        self.assertTrue(equivalent(helper.ACTIVE, "$EXP[Bald_SpoilerThumbsOn]", expressions()))

    def test_the_skin_reads_the_helpers_folder_property(self):
        text = ET.tostring(SPOILERS, encoding="unicode")
        self.assertIn(f"Window(home).Property({helper.PROPERTY_PATH})", text)
        self.assertEqual(helper.still_name(12), "12.jpg")
        still = SPOILERS.find("include[@name='Bald_SpoilerStill']//control[@type='image']")
        self.assertEqual(still.findtext("texture"),
                         f"$INFO[Window(home).Property({helper.PROPERTY_PATH})]$INFO[$PARAM[item]DBID,,.jpg]")
        self.assertTrue(implies(still.findtext("visible"), "$EXP[Bald_HasHelper]", expressions()))


class PlotSitesTests(unittest.TestCase):
    """Every plot label in Bald's own windows gives way to the note for the same item."""

    PLOT = re.compile(r"^\$INFO\[((?:Container\([^)]*\)\.)?ListItem\.)Plot\]$")

    def test_every_plot_label_has_the_rule_and_a_note_beside_it(self):
        seen = set()
        for path in NATIVE:
            root = ET.parse(path).getroot()
            parents = {child: parent for parent in root.iter() for child in parent}
            for label in root.iter("label"):
                match = self.PLOT.match((label.text or "").strip())
                if not match:
                    continue
                prefix = match.group(1)
                control = parents[label]
                with self.subTest(file=path.name, item=prefix):
                    shown = [i for i in control.findall("include") if i.get("content") == "Bald_SpoilerPlotShown"]
                    self.assertEqual(len(shown), 1)
                    self.assertEqual(shown[0].findtext("param[@name='item']") or "ListItem.", prefix)
                    notes = [i for i in parents[control].iter("include") if i.get("content") == "Bald_SpoilerNote"
                             and (i.findtext("param[@name='item']") or "ListItem.") == prefix]
                    self.assertTrue(notes)
                seen.add((path.name, prefix))
        for site in (("Includes_Bald_Home.xml", "Container($PARAM[c]).ListItem."),
                     ("View_520_Bald_TV.xml", "Container(540).ListItem."),
                     ("View_521_Bald_TV_Alternates.xml", "Container($PARAM[c]).ListItem."),
                     ("View_514_Bald_ArtworkList.xml", "Container(514).ListItem."),
                     ("Includes_Bald_InfoTV.xml", "Container(5302).ListItem."),
                     ("Includes_Bald_InfoPages.xml", "ListItem."), ("Includes_Bald_PVR.xml", "ListItem."),
                     ("DialogPVRInfo.xml", "ListItem."), ("MyPVRGuide.xml", "ListItem."),
                     ("DialogPVRChannelGuide.xml", "Container(11).ListItem."),
                     ("script-globalsearch.xml", "Container(50).ListItem.")):
            self.assertIn(site, seen)

    def test_plot_variables_start_with_the_note(self):
        found = all_variables()
        for name in ("Bald_BrowsePlot", "PlotTextBoxVar", "ShiftRightTextBoxVar", "ListBoxInfoVar", "VideoInfoPlotVar"):
            with self.subTest(variable=name):
                self.assertEqual(found[name][0], ("$EXP[Bald_SpoilerPlot]", "$VAR[Bald_SpoilerNoteText]"))
        self.assertEqual(found["Bald_OSDPlaylistPlot"][0], ("$EXP[Bald_SpoilerPlot8150]", "$VAR[Bald_SpoilerNoteText]"))

    def test_up_next_hides_an_unwatched_episodes_plot(self):
        bodies = expressions()
        self.assertTrue(implies("Skin.HasSetting(Bald.Spoilers) + !Skin.HasSetting(Bald.Spoilers.ShowPlots) + "
                                "!Integer.IsGreater(Window.Property(playcount),0)", "$EXP[Bald_OSDUpNextPlotHidden]", bodies))
        osd = ET.tostring(ET.parse(SKIN / "Includes_Bald_OSD.xml").getroot(), encoding="unicode")
        self.assertIn("<visible>!$EXP[Bald_OSDUpNextPlotHidden]</visible>", osd)


class StillSitesTests(unittest.TestCase):
    """Episode stills fall back to the show's art, and the frosted still goes over them."""

    @classmethod
    def setUpClass(cls):
        cls.variables = all_variables()

    def spoiler_before_thumb(self, name, condition, art, thumb="Art(thumb)"):
        values = self.variables[name]
        thumbs = [i for i, (_, value) in enumerate(values) if thumb in value]
        spoiler = [i for i, (c, value) in enumerate(values) if c and condition in c and value == art]
        self.assertTrue(spoiler, name)
        self.assertLess(spoiler[0], thumbs[0], name)

    def test_art_variables_hide_the_still(self):
        self.spoiler_before_thumb("Bald_EpisodeThumb", "$EXP[Bald_SpoilerThumb]", "$VAR[Bald_SpoilerArt]")
        self.spoiler_before_thumb("Bald_ItemFanart", "$EXP[Bald_SpoilerThumb]", "$VAR[Bald_SpoilerArt]")
        self.spoiler_before_thumb("Bald_ItemFanart5100", "$EXP[Bald_SpoilerThumb5100]", "$VAR[Bald_SpoilerArt5100]")
        self.spoiler_before_thumb("Bald_LibraryFanart", "$EXP[Bald_SpoilerThumb0]", "$VAR[Bald_SpoilerArt0]")
        for container in (540, 541, 542):
            self.spoiler_before_thumb(f"Bald_EpisodeThumb{container}", f"$EXP[Bald_SpoilerThumb{container}]",
                                      f"$VAR[Bald_SpoilerArt{container}]")
        self.spoiler_before_thumb("Bald_OSDPanelArt", "$EXP[Bald_SpoilerThumb]", "$VAR[Bald_SpoilerArt]")
        self.spoiler_before_thumb("Bald_OSDNextArt", "$EXP[Bald_SpoilerThumb8140]", "$VAR[Bald_SpoilerArt8140]",
                                  "Container(8140).ListItem.Art(thumb)")
        self.spoiler_before_thumb("Bald_OSDNextArt", "$EXP[Bald_OSDNextSpoiler]",
                                  "$INFO[VideoPlayer.offset(1).Art(tvshow.fanart)]", "offset(1).Art(thumb)")
        self.spoiler_before_thumb("Bald_OSDUpNextArt", "$EXP[Bald_OSDUpNextThumbHidden]", "$INFO[Window.Property(fanart)]",
                                  "Window.Property(thumb)")
        self.spoiler_before_thumb("Bald_InfoPoster", "$EXP[Bald_SpoilerThumb]", "")
        self.spoiler_before_thumb("Bald_PVRLogo", "$EXP[Bald_SpoilerThumb]", "", "ListItem.Icon")
        for name in ("ShiftThumbVar", "InfoWallThumbVar"):
            self.spoiler_before_thumb(name, "$EXP[Bald_SpoilerThumb]", "$VAR[Bald_SpoilerArt]")

    def test_spoiler_art_is_never_the_still(self):
        for suffix, prefix in SUFFIXES.items():
            for _, value in self.variables[f"Bald_SpoilerArt{suffix}"]:
                self.assertNotIn("Art(thumb)", value)
                self.assertNotIn("Icon", value)

    def test_stills_are_frosted_where_they_show(self):
        def calls(path, include):
            root = ET.parse(SKIN / path).getroot()
            return [(node.findtext("param[@name='item']") or "ListItem.") for node in root.iter("include")
                    if node.get("content") == include]

        self.assertIn("ListItem.", calls("Includes_Bald_Home.xml", "Bald_SpoilerStill"))          # tiles and cards
        self.assertIn("ListItem.", calls("View_521_Bald_TV_Alternates.xml", "Bald_SpoilerStill"))  # 542 wall
        self.assertIn("ListItem.", calls("Includes_Bald_OSD.xml", "Bald_SpoilerStill"))           # playlist panel
        self.assertIn("Container(8140).ListItem.", calls("Includes_Bald_OSD.xml", "Bald_SpoilerStill"))  # next card
        self.assertIn("Container(540).ListItem.", calls("View_520_Bald_TV.xml", "Bald_SpoilerFrame"))
        self.assertIn("Container($PARAM[c]).ListItem.", calls("View_521_Bald_TV_Alternates.xml", "Bald_SpoilerFrame"))

    def test_home_thumbnail_rows_and_episode_cards_ask_for_the_frost(self):
        home = ET.parse(SKIN / "Includes_Bald_Home.xml").getroot()
        row = home.find("include[@name='Bald_RowTiles_thumbnail']/include")
        self.assertEqual(row.findtext("param[@name='spoiler']"), "String.IsEqual(ListItem.DBType,episode)")
        card = ET.parse(SKIN / "Includes_Bald_InfoTV.xml").getroot().find(
            "include[@name='Bald_InfoTVEpisodeCard']//include[@content='Bald_LandscapeTile']")
        self.assertEqual(card.findtext("param[@name='spoiler']"), "true")
        self.assertEqual(card.findtext("param[@name='spoiler_number']"), "false")

    def test_live_tv_previews_drop_programme_art(self):
        bodies = expressions()
        self.assertTrue(implies("$EXP[Bald_SpoilerEpgArt]", "!$EXP[Bald_PVRHasArt]", bodies))
        self.assertTrue(implies("$EXP[Bald_SpoilerThumb]", "!$EXP[Bald_PVRHasArt]", bodies))

    def test_global_search_icon_fallback_hides_the_still(self):
        search = ET.parse(SKIN / "script-globalsearch.xml").getroot()
        icon = next(node for node in search.iter("control") if node.findtext("texture") == "$INFO[Container(50).ListItem.Icon]")
        self.assertTrue(implies(icon.findtext("visible"), "!$EXP[Bald_SpoilerThumb50]", expressions()))


if __name__ == "__main__":
    unittest.main()
