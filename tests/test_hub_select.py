"""Appearance > Behavior, "Select on a hub opens its library" (Bald.HubSelectOpens, row 9629).

Off (unset, the default): Select on a hub or Live TV enters its rows and Right opens its target (the guide). On: for an
entry with both rows and a target the two swap, and Left enters the rows too; an entry with only one of them behaves as
before. Home has no target and never changes (docs/NOTES.md, Music, favourites and weather hubs)."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import home_menu
from conditions import equivalent


XML = Path(__file__).resolve().parents[1] / "1080i"
HUBS = [f"hub{n}" for n in range(1, 9)]
ON, OFF = home_menu.setting(True), home_menu.setting(False)


def condition_of(pairs, action, bodies):
    """The condition under which `action` runs, all its (condition, action) pairs or'ed ("false" when none)."""
    conds = [f"[{cond or 'true'}]" for cond, text in pairs if text == action]
    return " | ".join(conds) if conds else "false"


def enter(screen):
    return f"SetFocus($INFO[Window(home).Property(Bald.Row.{screen})])"


class HubSelectTests(unittest.TestCase):
    def check(self, entry, bodies, expected):
        for tag, action, want in expected:
            with self.subTest(tag=tag, action=action):
                got = condition_of(home_menu.actions(entry, tag), action, bodies)
                self.assertTrue(equivalent(got, want, bodies), (got, want))

    def test_off_select_enters_and_right_opens(self):
        for n, hub in enumerate(HUBS, start=1):
            rows, target = f"$EXP[Bald_HasRows_{hub}]", f"$EXP[Bald_HubHasOpen_{hub}]"
            self.check(home_menu.entry(preview=hub), OFF, [
                ("onclick", enter(hub), rows),
                ("onclick", f"SetFocus(902{n})", f"{target} + !{rows}"),
                ("onright", enter(hub), "false"),
                ("onright", f"902{n}", target),
                ("onleft", enter(hub), "false"),
                ("onleft", "Action(Select)", "true"),
            ])

    def test_on_select_opens_and_right_and_left_enter(self):
        for n, hub in enumerate(HUBS, start=1):
            rows, target = f"$EXP[Bald_HasRows_{hub}]", f"$EXP[Bald_HubHasOpen_{hub}]"
            self.check(home_menu.entry(preview=hub), ON, [
                # With no target Select still enters the rows; with no rows it opens the target, as before.
                ("onclick", enter(hub), f"{rows} + !{target}"),
                ("onclick", f"SetFocus(902{n})", target),
                ("onright", enter(hub), f"{rows} + {target}"),
                ("onright", f"902{n}", f"{target} + !{rows}"),
                ("onleft", enter(hub), f"{rows} + {target}"),
                ("onleft", "Action(Select)", f"![{rows} + {target}]"),
            ])

    def test_every_entering_action_is_the_same_on_each_key(self):
        entry = home_menu.entry(preview="hub1")
        steps = lambda tag: [text for cond, text in home_menu.actions(entry, tag) if "Bald.Row.hub1" in text or "Bald.Screen" in text]
        self.assertEqual(steps("onright"), steps("onleft"))
        self.assertEqual(steps("onright"), steps("onclick"))
        self.assertEqual(len(steps("onright")), 3)

    def test_live_tv_swaps_its_rows_and_the_guide(self):
        live = home_menu.entry(preview="livetv")
        rows = "$EXP[Bald_LiveTVRows]"
        self.check(live, OFF, [
            ("onclick", enter("livetv"), rows),
            ("onclick", "ActivateWindow(TVGuide)", f"!{rows}"),
            ("onright", "9029", "true"),
            ("onright", enter("livetv"), "false"),
            ("onleft", "Action(Select)", "true"),
        ])
        self.check(live, ON, [
            ("onclick", enter("livetv"), "false"),
            ("onclick", "ActivateWindow(TVGuide)", "true"),
            ("onclick", "SetProperty(Bald.ReturnMenu,9004,home)", "true"),
            ("onright", enter("livetv"), rows),
            ("onright", "9029", f"!{rows}"),
            ("onleft", enter("livetv"), rows),
            ("onleft", "Action(Select)", f"!{rows}"),
        ])

    def test_home_is_unchanged(self):
        home = home_menu.entry(preview="home")
        for bodies in (ON, OFF):
            self.check(home, bodies, [
                ("onclick", enter("home"), "$EXP[Bald_HasRows_home]"),
                ("onright", enter("home"), "false"),
                ("onleft", "Action(Select)", "true"),
            ])

    def test_the_bridges_still_remember_the_entry_for_the_return(self):
        for n in range(1, 9):
            texts = [node.text for node in home_menu.control(f"902{n}").findall("onfocus")]
            self.assertEqual(texts[0], f"SetProperty(Bald.ReturnMenu,901{n},home)")

    def test_the_setting_is_a_behavior_row_and_unset_means_off(self):
        root = ET.parse(XML / "Custom_1118_BaldAppearance.xml").getroot()
        row = root.find(".//control[@id='9629']")
        self.assertEqual(row.get("type"), "radiobutton")
        self.assertEqual(row.findtext("selected"), "Skin.HasSetting(Bald.HubSelectOpens)")
        self.assertEqual(row.findtext("onclick"), "Skin.ToggleSetting(Bald.HubSelectOpens)")
        self.assertEqual(row.find("include").findtext("param[@name='item']"), "3")  # Behavior
        home = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        self.assertEqual(home.findtext("expression[@name='Bald_SelectOpens']"), "[Skin.HasSetting(Bald.HubSelectOpens)]")
        self.assertIn("9629", (XML / "IDs").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
