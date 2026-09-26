import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
SCREENS = (("home", "Home", 9100), ("movies", "Movies", 9200), ("tvshows", "TVShows", 9300))
PRISTINE = ("String.IsEmpty(Window(home).Property(Bald.Start{id})) + String.IsEqual(Container({id}).CurrentItem,3)"
            " + String.IsEqual(Container({id}).Position,2)")


def configured(screen, base):
    rows = json.loads((ROOT / "shortcuts" / f"skinvariables-shortcut-{screen}widgets.json").read_text())
    return [base + index for index in range(1, len(rows) + 1)]


class HomeRowStartTests(unittest.TestCase):
    def setUp(self):
        self.fallback = ET.parse(XML / "Includes_Bald_HomeDefaults.xml").getroot()

    def test_each_row_moves_the_next_row_to_its_first_item_while_that_row_is_hidden(self):
        for screen, title, base in SCREENS:
            ids = configured(screen, base)
            rows = self.fallback.findall(f"include[@name='Bald_Generated_{title}Widgets']/definition/include")
            for row_id, row in zip(ids, rows):
                actions = [(node.get("condition"), node.text) for node in row.findall("onfocus")]
                following = row_id + 1
                if following not in ids:
                    self.assertEqual(actions, [])
                    continue
                condition = PRISTINE.format(id=following)
                self.assertEqual(sorted(actions), sorted([
                    (condition, f"SetProperty(Bald.Start{following},1,home)"),
                    (condition, f"Control.Move({following},-2)"),
                ]))

    def test_home_clears_the_start_mark_of_every_configured_row(self):
        for screen, _, base in SCREENS:
            reset = self.fallback.find(f"include[@name='Bald_RowStartReset_{screen}']/definition")
            self.assertEqual([node.text for node in reset.findall("onload")],
                             [f"ClearProperty(Bald.Start{row},home)" for row in configured(screen, base)])
        home = ET.parse(XML / "Home.xml").getroot()
        self.assertIn("Bald_RowStartReset", [(node.text or "").strip() for node in home.findall("include")])
        self.assertFalse([node.text for node in home.findall("onload") if "Bald.Start" in node.text])
        combined = ET.parse(XML / "Includes_Bald_Home.xml").getroot().find("include[@name='Bald_RowStartReset']")
        self.assertEqual([node.text for node in combined.findall("include")],
                         [f"Bald_RowStartReset_{screen}" for screen, _, _ in SCREENS])

    def test_a_row_still_pristine_when_focused_moves_itself_once(self):
        row = ET.parse(XML / "Includes_Bald_Home.xml").getroot().find(
            "include[@name='Bald_Row']/definition/control[@type='fixedlist']"
        )
        actions = [(node.get("condition"), node.text) for node in row.findall("onfocus")]
        self.assertIn((PRISTINE.format(id="$PARAM[id]"), "Control.Move($PARAM[id],-2)"), actions)
        self.assertIn(("Integer.IsGreater(Container($PARAM[id]).NumItems,0)", "SetProperty(Bald.Start$PARAM[id],1,home)"),
                      actions)

    def test_rows_shown_before_focus_keep_their_timers(self):
        timers = ET.parse(XML / "Timers.xml").getroot()
        names = {timer.findtext("name") for timer in timers.findall("timer")}
        for row in (9101, 9102, 9103, 9201, 9301):
            self.assertIn(f"bald_rowstart_{row}", names)


if __name__ == "__main__":
    unittest.main()
