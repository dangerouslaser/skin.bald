"""Home's row hints (Bald_RowHints, Includes_Bald_Home.xml; chains from shortcuts/generator/screen.xml).

Home's hint line, bottom right like every other Bald footer, names the row Up reaches (or "Menu" from the first row)
and the row Down reaches (none from the last), each after its chevron. Kodi's CGUIWindow::OnMove passes over a row it cannot focus (an empty or loading list) by following
that row's own Up or Down, so the hints skip empty rows the same way. These tests evaluate the generated chains for
every combination of empty rows and compare them with that navigation."""

import itertools
import re
import unittest
import xml.etree.ElementTree as ET

from kodi_includes import expand_call, include_definitions
from test_home_hubs import build, row

MENU = "$LOCALIZE[31787]"


def generated(labels):
    return ET.fromstring(build({"homewidgets": [row(label) for label in labels]}).split("\n", 1)[1])


class Chains:
    """Evaluates the generated Bald_RowPrevFrom / Bald_RowNextFrom variables and Bald_RowHasNextFrom expressions, given
    which row ids have items."""

    def __init__(self, root, full):
        self.variables = {node.get("name"): node for node in root.iter("variable")}
        self.expressions = {node.get("name"): node.text for node in root.iter("expression")}
        self.full = full

    def holds(self, condition):
        match = re.fullmatch(r"Integer\.IsGreater\(Container\((\d+)\)\.NumItems,0\)", condition)
        assert match, condition
        return int(match.group(1)) in self.full

    def var(self, name):
        for value in self.variables[name].findall("value"):
            condition = value.get("condition")
            if condition is None or self.holds(condition):
                text = value.text or ""
                inner = re.fullmatch(r"\$VAR\[([^\]]+)\]", text)
                return self.var(inner.group(1)) if inner else text
        return ""

    def exp(self, name):
        body = self.expressions[name].strip()
        if body == "[false]":
            return False
        match = re.fullmatch(r"\[(Integer\.IsGreater\(Container\(\d+\)\.NumItems,0\)) \| \$EXP\[([^\]]+)\]\]", body)
        assert match, body
        return self.holds(match.group(1)) or self.exp(match.group(2))


def param(node, name):
    return node.findtext(f"param[@name='{name}']")


class RowHintTests(unittest.TestCase):
    def test_the_hints_name_the_row_up_and_down_reach(self):
        labels = ["In progress", "Recently added", "Top rated", "Random"]
        root = generated(labels)
        rows = root.find("include[@name='Bald_Generated_HomeWidgets']/definition").findall("include")
        ids = [int(param(r, "id")) for r in rows]
        self.assertEqual(ids, [9101, 9102, 9103, 9104])
        for empty in itertools.product((False, True), repeat=len(ids)):
            full = {i for i, e in zip(ids, empty) if not e}
            chains = Chains(root, full)
            for n, r in enumerate(rows):
                if ids[n] not in full:
                    continue  # an empty row never has focus
                # Kodi's navigation: the nearest row with items, else the menu (Up) or nowhere (Down).
                up = next((labels[k] for k in range(n - 1, -1, -1) if ids[k] in full), MENU)
                down = next((labels[k] for k in range(n + 1, len(ids)) if ids[k] in full), None)
                with self.subTest(row=n + 1, empty=empty):
                    self.assertEqual(chains.var(param(r, "prev")), up)
                    self.assertEqual(chains.exp(param(r, "has_next")), down is not None)
                    if down is not None:
                        self.assertEqual(chains.var(param(r, "next")), down)

    def test_a_single_row_says_menu_and_has_no_next(self):
        root = generated(["Only row"])
        only = root.find("include[@name='Bald_Generated_HomeWidgets']/definition/include")
        chains = Chains(root, {9101})
        self.assertEqual(chains.var(param(only, "prev")), MENU)
        self.assertFalse(chains.exp(param(only, "has_next")))

    def row(self, style="fanart"):
        holder = ET.Element("holder")
        # Names, as the generator passes them (shortcuts/generator/row.xmltemplate).
        holder.extend(expand_call("Bald_Row", {"id": "9101", "style": style, "prev": "P", "next": "N",
                                               "has_next": "H", "screen": "movies"}, include_definitions()))
        return list(holder)

    def hint_line(self, style="fanart"):
        return next(node for node in self.row(style) if node.get("type") == "grouplist")

    def test_the_generator_passes_names_the_include_wraps(self):
        # has_next is an expression name: the include must read it as $EXP[...], or Kodi reads it as false.
        root = generated(["A", "B"])
        first = root.find("include[@name='Bald_Generated_HomeWidgets']/definition/include")
        for name in ("prev", "next", "has_next"):
            self.assertNotIn("$", param(first, name))
        self.assertIn("$EXP[H]", [node.findtext("visible") for node in self.hint_line().findall("control")])

    def test_the_hints_sit_bottom_right_like_the_rest_of_the_skin(self):
        for style in ("fanart", "poster", "square"):
            hints = self.hint_line(style)
            with self.subTest(style=style):
                # Beside the row's group, not in it: the same place whatever the row style, ending on the safe edge.
                # The right column (1440), on the hint line every other screen uses (y 954).
                self.assertEqual((hints.findtext("left"), hints.findtext("top")), ("1440", "954"))
                self.assertEqual(hints.findtext("width"), "384")  # 1440 + 384 = 1824
                self.assertEqual(hints.findtext("align"), "right")
        # The row label line keeps only the label and the count.
        group = next(node for node in self.row() if node.get("type") == "group")
        text = ET.tostring(group, encoding="unicode")
        self.assertNotIn("Bald_Key", text)

    def test_up_first_then_down_joined_by_the_dot(self):
        labels = self.hint_line().findall("control")
        self.assertEqual([node.findtext("label") for node in labels],
                         ["$VAR[Bald_KeyUp]$VAR[P]", "·", "$VAR[Bald_KeyDown]$VAR[N]"])
        self.assertEqual(labels[1].findtext("width"), "20")
        for node in labels:
            self.assertEqual((node.findtext("font"), node.findtext("textcolor")), ("Bald_Hint", "bald_ink60"))
        # The next pair (dot and name) hides when Down goes nowhere.
        self.assertEqual([node.findtext("visible") for node in labels], [None, "$EXP[H]", "$EXP[H]"])

    def test_shown_for_the_focused_row_only_and_not_under_the_menu_or_a_dialog(self):
        hints = self.hint_line()
        visible = hints.findtext("visible")
        for part in ("String.IsEqual(Window(home).Property(Bald.Row),9101)",
                     "String.IsEqual(Window(home).Property(Bald.Screen),movies)", "!$EXP[Bald_MenuOpen]",
                     "!$EXP[Bald_DialogOver]", "$EXP[Bald_HomeHintsShown]"):
            self.assertIn(part, visible)
        idle = [a for a in hints.findall("animation") if a.get("condition") == "$EXP[Bald_Idle]"]
        self.assertEqual(len(idle), 1)
        self.assertEqual(idle[0].find("effect").get("time"), "600")

    def test_nothing_can_run_past_the_column(self):
        labels = self.hint_line().findall("control")
        widths = [int(n.findtext("width")) if n.find("width").get("max") is None else int(n.find("width").get("max"))
                  for n in labels]
        self.assertLessEqual(sum(widths), 384)

    def test_no_row_dots_are_left(self):
        root = generated(["A", "B"])
        text = ET.tostring(root, encoding="unicode")
        self.assertNotIn("Bald_RowDots", text)
        self.assertNotIn("dots", text)


if __name__ == "__main__":
    unittest.main()
