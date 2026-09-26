"""Structural regressions for the TV info Overview (docs/SPEC.md 5.3); no Kodi instance required."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

from scripts import info


ROOT = Path(__file__).resolve().parents[1] / "1080i"
TV_ITEM = "$EXP[Bald_InfoTVItem]"


def include_def(root, name):
    node = root.find(f"include[@name='{name}']")
    return node.find("definition") if node.find("definition") is not None else node


def params(node):
    return {p.get("name"): (p.text or "") for p in node.findall("param")}


class InfoTvTests(unittest.TestCase):
    def setUp(self):
        self.dialog = ET.parse(ROOT / "DialogVideoInfo.xml").getroot()
        self.tv = ET.parse(ROOT / "Includes_Bald_InfoTV.xml").getroot()
        self.shared = ET.parse(ROOT / "Includes_Bald_Info.xml").getroot()
        self.home = ET.parse(ROOT / "Includes_Bald_Home.xml").getroot()
        self.page = include_def(self.tv, "Bald_InfoTVOverview")

    def control(self, control_id):
        node = self.page.find(f".//control[@id='{control_id}']")
        self.assertIsNotNone(node, control_id)
        return node

    def test_registered_and_chosen_by_item_type(self):
        files = [node.get("file") for node in ET.parse(ROOT / "Includes.xml").getroot().findall("include")]
        self.assertIn("Includes_Bald_InfoTV.xml", files)
        kind = self.tv.find("expression[@name='Bald_InfoTVItem']").text
        for dbtype in ("tvshow", "season", "episode"):
            self.assertIn(f"String.IsEqual(ListItem.DBType,{dbtype})", kind)
        self.assertNotIn("movie", kind)
        chosen = {node.text: node.get("condition") for node in self.dialog.iter("include") if node.get("condition")}
        self.assertEqual(chosen["Bald_InfoOverview"], "!" + TV_ITEM)
        self.assertEqual(chosen["Bald_InfoMovieOnLoad"], "!" + TV_ITEM)
        for name in ("Bald_InfoTVOverview", "Bald_InfoTVOnLoad", "Bald_InfoTVDim", "Bald_InfoTVHints"):
            self.assertEqual(chosen[name], TV_ITEM)
        # Movie info keeps its own onload focus and paged includes.
        movie_focus = [n.text for n in self.shared.find("include[@name='Bald_InfoMovieOnLoad']")]
        self.assertEqual(movie_focus, ["SetFocus(5001)", "SetFocus(5003)"])
        self.assertNotIn("SetFocus(5003)", [n.text for n in self.dialog.findall("onload")])

    def test_onload_runs_the_bridge_and_focuses_an_existing_action(self):
        onload = self.tv.find("include[@name='Bald_InfoTVOnLoad']").findall("onload")
        texts = [node.text for node in onload]
        self.assertIn("RunScript(skin.bald,tvinfo,$INFO[ListItem.DBType],$INFO[ListItem.DBID])", texts)
        focus_ids = {re.fullmatch(r"SetFocus\((\d+)\)", t).group(1) for t in texts if t.startswith("SetFocus")}
        action_ids = {p["id"] for p in map(params, self.control("5000").findall("include[@content='Bald_InfoAction']"))}
        self.assertEqual(focus_ids, {"5001", "5002", "5003"})
        self.assertTrue(focus_ids <= action_ids)
        # Every TV property the page reads is cleared when the dialog loads.
        cleared = {re.match(r"ClearProperty\(([^,]+),", n.text).group(1)
                   for n in self.tv.find("include[@name='Bald_InfoTVClear']").findall("onload")}
        read = set(re.findall(r"Property\((Bald\.(?:TV\.\w+|InfoTV))\)", ET.tostring(self.tv, encoding="unicode")))
        self.assertTrue(read <= cleared, read - cleared)
        self.assertIn("Bald_InfoTVClear", [n.text for n in self.dialog.findall("include")])

    def test_actions_reuse_the_pill_and_lead_to_the_tabs(self):
        actions = [params(n) for n in self.control("5000").findall("include[@content='Bald_InfoAction']")]
        self.assertEqual([a["id"] for a in actions], ["5001", "5002", "5003", "5004"])
        self.assertTrue(all(a["down"] == "Bald_InfoTVActionDown" for a in actions))
        by_id = {a["id"]: a for a in actions}
        self.assertEqual(by_id["5001"]["onclick"], "SendClick(9)")
        self.assertEqual(by_id["5002"]["onclick"], "SendClick(8)")
        self.assertEqual(by_id["5003"]["onclick"],
                         "RunScript(skin.bald,play,episode,$INFO[Window(movieinformation).Property(Bald.TV.NextID)])")
        self.assertEqual(by_id["5004"]["onclick"], "SendClick(11)")
        down = [n.text for n in self.tv.find("include[@name='Bald_InfoTVActionDown']")]
        self.assertEqual(down[0], "SetFocus(5301)")
        # Movie actions keep their original Down route through the default parameter.
        action = self.shared.find("include[@name='Bald_InfoAction']")
        self.assertEqual(params(action)["down"], "Bald_InfoActionToCast")
        self.assertEqual(action.find("definition/control/include").text, "$PARAM[down]")
        to_cast = [n.text for n in self.shared.find("include[@name='Bald_InfoActionToCast']")]
        self.assertEqual(to_cast, ["SetProperty(Bald.InfoSec,1,home)",
                                   "ClearProperty(TMDbHelper.WidgetContainer,movieinformation)",
                                   "SetFocus(50)", "SetFocus(5050)"])
        movie = ET.parse(ROOT / "Includes_Bald_InfoPages.xml").getroot()
        for node in movie.findall("include[@name='Bald_InfoOverview']//include[@content='Bald_InfoAction']"):
            self.assertNotIn("down", params(node))

    def test_seasons_are_native_tabs_for_the_show(self):
        seasons = self.control("5301")
        self.assertEqual(seasons.get("type"), "list")
        self.assertEqual(seasons.findtext("orientation"), "horizontal")
        self.assertEqual(seasons.findtext("content"), "$VAR[Bald_InfoTVSeasonsPath]")
        path = self.tv.find("variable[@name='Bald_InfoTVSeasonsPath']").findall("value")
        for value in path:
            # Never an unconditional value: an empty id would list every show.
            self.assertIn("!String.IsEmpty(", value.get("condition") or "")
            self.assertRegex(value.text, r"^videodb://tvshows/titles/\$INFO\[[^\]]+\]/$")
        tab = include_def(self.tv, "Bald_InfoTVSeasonTab")
        underline = tab.find("control[@type='group']")
        grow = underline.find("animation[@type='Focus']/effect")
        self.assertEqual((grow.get("type"), grow.get("start"), grow.get("time"), grow.get("tween"), grow.get("easing")),
                         ("zoom", "1,100", "300", "cubic", "out"))
        self.assertTrue(grow.get("center").startswith("0,"))
        widths = [params(n)["w"] for n in underline.findall("include[@content='Bald_InfoTVUnderline']")]
        self.assertEqual(len(widths), 6)
        slot = int(seasons.find("itemlayout").get("width"))
        self.assertTrue(all(int(w) < slot for w in widths))
        self.assertEqual(self.tv.find("include[@name='Bald_InfoTVUnderline']//texture").get("colordiffuse"), "bald_accent")

    def test_episode_row_follows_the_focused_season(self):
        row = self.control("5302")
        self.assertEqual(row.get("type"), "fixedlist")
        self.assertEqual((row.findtext("focusposition"), row.findtext("movement")), ("2", "2"))
        self.assertEqual(row.findtext("content"), "$INFO[Container(5301).ListItem.FolderPath]")
        scroll = row.find("scrolltime")
        self.assertEqual((scroll.text, scroll.get("tween"), scroll.get("easing")), ("440", "cubic", "out"))
        self.assertEqual(row.findtext("onclick"), "RunScript(skin.bald,play,episode,$INFO[Container(5302).ListItem.DBID])")
        self.assertIn("Bald_InfoActionToCast", [n.text for n in row.findall("include")])
        # The season change fades the row out 140 while it updates, then in 340 / rises 420.
        group = next(g for g in self.page.iter("control") if g.find("control[@id='5302']") is not None)
        swaps = {a.get("condition"): [(e.get("type"), e.get("time")) for e in a] for a in group.findall("animation[@type='Conditional']")}
        self.assertEqual(swaps["Container(5302).IsUpdating"], [("fade", "140"), ("slide", "140")])
        self.assertEqual(swaps["!Container(5302).IsUpdating"], [("fade", "340"), ("slide", "420")])
        # Tabs reset the row only after a season change; the script and row share the same marker.
        down = [(n.get("condition") or "", n.text) for n in self.tv.find("include[@name='Bald_InfoTVSeasonsDown']")]
        self.assertIn("SetFocus(5302,0,absolute)", [text for _, text in down])
        self.assertIn("SetProperty(Bald.TV.RowFor,$INFO[Container(5301).CurrentItem],movieinformation)",
                      [n.text for n in row.findall("onfocus")])

    def test_episode_cards_are_320_by_180_with_a_24_gap(self):
        row = self.control("5302")
        slot = int(row.find("itemlayout").get("width"))
        card = include_def(self.tv, "Bald_InfoTVEpisodeCard")
        tile = card.find(".//include[@content='Bald_LandscapeTile']")
        p = params(tile)
        self.assertEqual((p["w"], p["h"]), ("320", "180"))
        self.assertEqual(slot - int(p["w"]), 24)
        self.assertEqual(int(p["x"]) * 2, slot - int(p["w"]))
        self.assertEqual((int(p["ring_x"]), int(p["ring_w"])), (int(p["x"]) - 3, int(p["w"]) + 6))
        self.assertEqual(p["art"], "$VAR[Bald_InfoTVEpisodeArt]")
        pop = card.find(".//animation[@type='Focus']/effect")
        self.assertEqual((pop.get("end"), pop.get("time"), pop.get("tween")), ("105", "280", "back"))
        visible = {n.findtext("visible") for n in card.iter("control") if n.findtext("visible")}
        self.assertIn("Integer.IsGreater(ListItem.PlayCount,0)", visible)
        self.assertIn("ListItem.IsResumable", visible)
        self.assertEqual(card.find(".//control[@type='progress']").findtext("info"), "ListItem.PercentPlayed")
        # Episode detail reuses Home's flag items on the episode row.
        flags = self.page.find(".//include[@content='Bald_MediaFlagItems']")
        self.assertEqual(params(flags)["c"], "5302")

    def test_landscape_tile_defaults_are_homes_row_tile(self):
        tile = self.home.find("include[@name='Bald_LandscapeTile']")
        p = params(tile)
        self.assertEqual(p["art"], "$VAR[Bald_TileArt]")
        self.assertEqual([p[k] for k in ("x", "y", "w", "h", "ring_x", "ring_y", "ring_w", "ring_h")],
                         ["10", "10", "176", "99", "7", "7", "182", "105"])

    def test_page_model_and_stagger(self):
        page = self.page.find("control")
        self.assertEqual(params(page.find("include[@content='Bald_InfoPage']"))["page"], "0")
        delays = sorted(int(params(n)["delay"]) for n in page.iter("include") if n.get("content") == "Bald_AnimInfoIn")
        # Base 380 plus the prototype stagger 0, 60, 100, 180, 220, 270, 310.
        self.assertEqual(delays, [380, 440, 480, 560, 600, 650, 690])
        dim = include_def(self.tv, "Bald_InfoTVDim").find("control")
        self.assertEqual(dim.find("texture").get("colordiffuse"), "bald_field60")
        self.assertEqual(dim.find("animation").get("end"), "70")
        # Up from Cast returns to the lowest filled TV row; movies fall through to their actions.
        up = [(n.get("condition"), n.text) for n in self.shared.find("include[@name='Bald_InfoToOverview']").findall("onup")]
        self.assertIn(("$EXP[Bald_InfoTVHasEpisodes]", "SetFocus(5302)"), up)
        self.assertEqual(up[-1][1], "SetFocus(5000)")

    def test_script_contract_matches_the_xml(self):
        self.assertEqual(self.control(str(info.SEASONS)).get("type"), "list")
        self.assertEqual(self.control(str(info.EPISODES)).get("type"), "fixedlist")
        action_ids = {params(n)["id"] for n in self.page.iter("include") if n.get("content") == "Bald_InfoAction"}
        self.assertEqual(set(re.findall(r"Control\.HasFocus\((\d+)\)", info.EPISODE_ACTIONS)), {"5001", "5002"})
        self.assertTrue({"5001", "5002"} <= action_ids)
        self.assertEqual(set(info.TV_TYPES), {"tvshow", "season", "episode"})


if __name__ == "__main__":
    unittest.main()
