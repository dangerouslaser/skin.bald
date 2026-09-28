"""Short Home rows start at the safe margin (Bald_Row, Includes_Bald_Home.xml): the row's fixedlist has
<aligny>top</aligny>, and row start brings a short row's fresh selection (its last item) back to item 1.

The fixedlist below is a port of Kodi 22's CGUIFixedListContainer (GetCursorRange with the center and top
alignments, ValidateOffset, SelectItem, MoveUp/MoveDown) and the first fill in CGUIBaseContainer::UpdateListProvider.
Each row style is checked with its own focus slot, slot width and page, for every length from one item to well past
the focus range, through the row-start actions the skin really runs: Bald_Row's own onfocus, the generated
Bald_RowStart_<id> the row above runs, and the Timers.xml timers."""

import re
import unittest
from functools import lru_cache
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import parse
from kodi_includes import expand_call


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
STYLES = {"fanart": 2, "thumbnail": 2, "logo": 2, "text": 2, "poster": 5, "square": 2, "weather": 2}


class FixedList:
    """CGUIFixedListContainer, horizontal, as Bald_Row sets it up (focusposition = movement = slot)."""

    def __init__(self, slot, per_page, align):
        self.fixed, self.start_range, self.end_range = slot, slot, slot
        self.per_page, self.align = per_page, align
        self.cursor, self.offset, self.items = slot, 0, 0

    def cursor_range(self):
        low = max(self.fixed - self.start_range, 0)
        high = min(self.fixed + self.end_range, self.per_page)
        if not self.items:
            return self.fixed, self.fixed
        while high - low > self.items - 1:
            if self.align == "top":
                high -= 1
            elif high - self.fixed > self.fixed - low:
                high -= 1
            else:
                low += 1
        return low, high

    def validate(self):
        low, high = self.cursor_range()
        self.cursor = min(max(self.cursor, low), high)
        min_offset, max_offset = -low, self.items - high - 1
        if self.offset > max_offset:
            self.offset = max(-low, max_offset)
        if self.offset < min_offset:
            self.offset = min_offset

    def select(self, item):
        self.validate()
        if 0 <= item < self.items:
            low, high = self.cursor_range()
            if self.items - 1 - item <= high - self.fixed:
                cursor = max(self.fixed, high + item - self.items + 1)
            elif item <= self.fixed - low:
                cursor = min(self.fixed, low + item)
            else:
                cursor = self.fixed
            self.cursor = cursor
            self.offset = item - cursor

    def fill(self, count):
        """The first fetch: the selection (cursor + offset, the focus slot) is kept unless it is past the end."""
        current = self.offset + self.cursor
        self.items = count
        if current >= count:
            self.select(count - 1)
        self.validate()

    @property
    def selected(self):
        return self.offset + self.cursor

    def move(self, amount):
        """Control.Move: MoveUp/MoveDown with wrap around, once per step."""
        for _ in range(abs(amount)):
            item = self.selected
            if amount < 0:
                self.select(item - 1 if item > 0 else self.items - 1)
            else:
                self.select(item + 1 if item < self.items - 1 else 0)

    def right(self):
        """Right on the row: false at the last item (the row's onright, the edge nudge, runs instead)."""
        if self.selected < self.items - 1:
            self.select(self.selected + 1)
            return True
        return False


def number(text):
    return int(text)


class State:
    """Infolabels and conditions the row-start actions read, for one container."""

    def __init__(self, row_id, fixedlist):
        self.id, self.list, self.started = str(row_id), fixedlist, False

    def info(self, label):
        container = f"Container({self.id})."
        values = {container + "NumItems": self.list.items, container + "CurrentItem": self.list.selected + 1,
                  container + "Position": self.list.cursor}
        if label in values:
            return values[label]
        return int(label)

    def atom(self, text):
        match = re.fullmatch(r"(String|Integer)\.(IsEqual|IsGreater|IsEmpty)\((.*)\)", text)
        if text == "Window.IsActive(home)":
            return True
        if text == f"Container({self.id}).IsUpdating":
            return False
        if not match:
            raise AssertionError(f"unexpected atom {text}")
        kind, test, args = match.groups()
        if test == "IsEmpty":
            self.assertEqualArg(args, f"Window(home).Property(Bald.Start{self.id})")
            return not self.started
        left, right = args.split(",", 1)
        left, right = self.info(left), self.info(right)
        return left == right if test == "IsEqual" else left > right

    @staticmethod
    def assertEqualArg(actual, expected):
        if actual != expected:
            raise AssertionError(f"{actual} is not {expected}")

    def holds(self, condition):
        def evaluate(tree):
            if tree is True or tree is False:
                return tree
            kind, value = tree
            if kind == "atom":
                return self.atom(value)
            if kind == "not":
                return not evaluate(value)
            results = [evaluate(term) for term in value]
            return all(results) if kind == "and" else any(results)
        return evaluate(parse(condition or "true"))

    def run(self, actions):
        """Kodi evaluates every condition first, then runs the actions that held, in order (CGUIAction)."""
        chosen = [action for condition, action in actions if self.holds(condition)]
        for action in chosen:
            move = re.fullmatch(rf"Control\.Move\({self.id},(-?\d+)\)", action)
            if move:
                self.list.move(int(move.group(1)))
            elif action == f"SetProperty(Bald.Start{self.id},1,home)":
                self.started = True
        return chosen


@lru_cache(maxsize=None)
def row_geometry(style):
    """The row's slot width and Kodi's items per page for it (CGUIBaseContainer::CalculateLayout)."""
    holder = ET.Element("fixedlist")
    holder.extend(expand_call(f"Bald_RowTiles_{style}"))
    width = float(holder.findtext("width"))
    item = float(holder.find("itemlayout").get("width"))
    focused = float(holder.find("focusedlayout").get("width"))
    return item, max(int((width - focused) / item) + 1, 1), holder


@lru_cache(maxsize=None)
def row_list(style, row_id=9150):
    """Bald_Row's fixedlist for a style, expanded."""
    slot = STYLES[style]
    parts = expand_call("Bald_Row", {"id": str(row_id), "style": style, "slot": str(slot), "start": str(slot + 1),
                                     "label": "Row", "index": "2"})
    return next(node for node in parts if node.get("type") == "fixedlist")


@lru_cache(maxsize=None)
def alignment(style):
    """What Bald_Row's fixedlist asks for: <aligny>, else Kodi's default, center."""
    return row_list(style).findtext("aligny") or "center"


def onfocus(control):
    return [(node.get("condition"), node.text) for node in control.findall("onfocus")
            if "Bald.Start" in (node.get("condition") or "") or "Control.Move" in (node.text or "")]


class ShortRowTests(unittest.TestCase):
    def test_rows_align_their_items_to_the_start(self):
        for style in STYLES:
            control = row_list(style)
            with self.subTest(style=style):
                self.assertEqual(control.findtext("aligny"), "top")
                self.assertEqual(control.findtext("focusposition"), str(STYLES[style]))
                self.assertEqual(control.findtext("movement"), str(STYLES[style]))

    def test_every_length_starts_at_the_margin_through_the_rows_own_start(self):
        for style, slot in STYLES.items():
            item, per_page, _ = row_geometry(style)
            actions = onfocus(row_list(style))
            for count in range(1, 2 * slot + 4):
                with self.subTest(style=style, items=count):
                    fixed = FixedList(slot, per_page, alignment(style))
                    fixed.fill(count)
                    state = State(9150, fixed)
                    state.run(actions)
                    self.assertEqual((fixed.selected, fixed.cursor, fixed.offset), (0, 0, 0))
                    # The first tile's slot is the list's left edge: no empty slots before it.
                    self.assertEqual(-fixed.offset * item, 0)
                    # A second focus (the row marked as started) moves nothing.
                    fixed.right()
                    before = (fixed.selected, fixed.cursor, fixed.offset)
                    state.run(actions)
                    self.assertEqual((fixed.selected, fixed.cursor, fixed.offset), before)

    def test_short_rows_walk_right_without_scrolling_and_nudge_at_the_end(self):
        for style, slot in STYLES.items():
            _, per_page, _ = row_geometry(style)
            for count in range(1, slot + 2):
                with self.subTest(style=style, items=count):
                    fixed = FixedList(slot, per_page, alignment(style))
                    fixed.fill(count)
                    State(9150, fixed).run(onfocus(row_list(style)))
                    for step in range(1, count):
                        self.assertTrue(fixed.right())
                        self.assertEqual((fixed.selected, fixed.cursor, fixed.offset), (step, step, 0))
                    self.assertFalse(fixed.right())  # The edge nudge (onright) runs here.

    def test_long_rows_move_exactly_as_before(self):
        # A row that fills the focus range never narrows it, so the alignment changes nothing: same cursor and
        # offset at every step as Kodi's default (center) alignment.
        for style, slot in STYLES.items():
            _, per_page, _ = row_geometry(style)
            reach = min(2 * slot, per_page)
            for count in range(reach + 1, reach + 8):
                with self.subTest(style=style, items=count):
                    top, center = FixedList(slot, per_page, alignment(style)), FixedList(slot, per_page, "center")
                    for fixed in (top, center):
                        fixed.fill(count)
                        State(9150, fixed).run(onfocus(row_list(style)))
                    self.assertEqual((top.selected, top.offset), (0, 0))
                    while True:
                        self.assertEqual((top.selected, top.cursor, top.offset),
                                         (center.selected, center.cursor, center.offset))
                        if not (top.right() & center.right()):
                            break

    def test_the_default_alignment_is_what_went_wrong(self):
        # Kodi's center alignment narrows the focus range from both sides: a lone tile sits at the focus slot.
        for slot, per_page in ((2, 6), (5, 8)):
            fixed = FixedList(slot, per_page, "center")
            fixed.fill(1)
            self.assertEqual((fixed.selected, fixed.cursor, fixed.offset), (0, slot, -slot))

    def test_the_short_start_moves_are_exact(self):
        # One action per item count from 2 to the slot, n - 1 items back (Control.Move wraps past item 1).
        for slot, counts in ((2, [2]), (5, [2, 3, 4, 5])):
            parts = expand_call(f"Bald_RowStartShort_{slot}", {"id": "9150"})
            moves = [(node.get("condition"), node.text) for node in parts if "Control.Move" in node.text]
            self.assertEqual([action for _, action in moves], [f"Control.Move(9150,-{n - 1})" for n in counts])
            for (condition, _), n in zip(moves, counts):
                self.assertIn(f"Integer.IsEqual(Container(9150).NumItems,{n})", condition)
                self.assertIn(f"Integer.IsEqual(Container(9150).CurrentItem,{n})", condition)

    def test_the_row_above_starts_the_next_row_the_same_way(self):
        template = (ROOT / "shortcuts" / "generator" / "row-parts.xmltemplate").read_text(encoding="utf-8")
        self.assertIn('<include content="Bald_RowStartShort_{row_slot}"><param name="id">{row_id}</param></include>',
                      template)
        fallback = ET.parse(XML / "Includes_Bald_HomeDefaults.xml").getroot()
        rows = {row.findtext("param[@name='id']"): row.findtext("param[@name='slot']")
                for row in fallback.iter("include") if row.get("content") == "Bald_Row"}
        starts = [node for node in fallback.findall("include") if node.get("name", "").startswith("Bald_RowStart_")]
        self.assertTrue(starts)
        for node in starts:
            row_id = node.get("name").rsplit("_", 1)[1]
            slot = rows[row_id]
            with self.subTest(row=row_id):
                calls = [call for call in node.find("definition").findall("include")]
                self.assertEqual([(call.get("content"), call.findtext("param[@name='id']")) for call in calls],
                                 [(f"Bald_RowStartShort_{slot}", row_id)])
                style = "poster" if slot == "5" else "fanart"
                _, per_page, _ = row_geometry(style)
                actions = [(child.get("condition"), child.text) for child in expand_call(node.get("name"))]
                for count in range(1, 2 * int(slot) + 4):
                    fixed = FixedList(int(slot), per_page, alignment(style))
                    fixed.fill(count)
                    State(row_id, fixed).run(actions)
                    self.assertEqual((fixed.selected, fixed.offset), (0, 0), count)

    def test_timers_start_rows_of_either_slot_at_any_length(self):
        timers = ET.parse(XML / "Timers.xml").getroot()
        found = 0
        for timer in timers.findall("timer"):
            name = timer.findtext("name")
            if not name.startswith("bald_rowstart_"):
                continue
            found += 1
            row_id = name.rsplit("_", 1)[1]
            actions = [(node.get("condition"), node.text) for node in timer.findall("onstart")]
            for style in ("fanart", "poster", "square"):
                slot = STYLES[style]
                _, per_page, _ = row_geometry(style)
                for count in range(1, 2 * slot + 4):
                    with self.subTest(timer=name, style=style, items=count):
                        fixed = FixedList(slot, per_page, alignment(style))
                        fixed.fill(count)
                        state = State(row_id, fixed)
                        if count == 1:
                            # Nothing to move; the row marks itself when it is focused.
                            self.assertFalse(state.holds(timer.findtext("start")))
                            continue
                        self.assertTrue(state.holds(timer.findtext("start")))
                        chosen = state.run(actions)
                        self.assertEqual(len([a for a in chosen if a.startswith("Control.Move")]), 1)
                        self.assertEqual((fixed.selected, fixed.offset), (0, 0))
                        self.assertFalse(state.holds(timer.findtext("start")))
        self.assertEqual(found, 12)

    def test_the_weather_row_needs_no_slide_of_its_own(self):
        weather = next(node for node in ET.parse(XML / "Includes_Bald_Home.xml").getroot().findall("include")
                       if node.get("name") == "Bald_RowTiles_weather")
        self.assertEqual(weather.findall("animation"), [])


if __name__ == "__main__":
    unittest.main()
