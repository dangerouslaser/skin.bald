"""Home's row hints (Bald_RowHints, Includes_Bald_Home.xml; chains from shortcuts/generator/screen.xml).

The label line names, at its right, the row Up reaches (or "Menu" from the first row) and the row Down reaches (none
from the last). Kodi's CGUIWindow::OnMove passes over a row it cannot focus (an empty or loading list) by following
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
    def test_the_generator_passes_names_the_include_wraps(self):
        # has_next is an expression name: the include must read it as $EXP[...], or Kodi reads it as false.
        root = generated(["A", "B"])
        first = root.find("include[@name='Bald_Generated_HomeWidgets']/definition/include")
        for name in ("prev", "next", "has_next"):
            self.assertNotIn("$", param(first, name))
        _, hints = self.label_line()
        self.assertIn("$EXP[H]", [node.findtext("visible") for node in hints.findall("control")])

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

    def label_line(self, style="fanart"):
        holder = ET.Element("holder")
        # Names, as the generator passes them (shortcuts/generator/row.xmltemplate).
        holder.extend(expand_call("Bald_Row", {"id": "9101", "style": style, "prev": "P", "next": "N",
                                               "has_next": "H"}, include_definitions()))
        group = holder.find("control")
        hints = [node for node in group.findall("control") if node.get("type") == "grouplist"][1]
        return group, hints

    def test_the_hints_sit_right_aligned_on_the_label_line(self):
        for style in ("fanart", "poster", "square"):
            group, hints = self.label_line(style)
            line = [node for node in group.findall("control") if node.get("type") == "grouplist"][0]
            with self.subTest(style=style):
                # Same line as the label, whatever the style moves it to; right edge on the art frame's (96 + 1248).
                self.assertEqual(hints.findtext("top"), line.findtext("top"))
                self.assertEqual(int(hints.findtext("left").replace("Bald_SafeLeft", "96")) + int(hints.findtext("width")), 1344)
                self.assertEqual(hints.findtext("align"), "right")

    def test_previous_first_then_next_with_the_designed_gaps(self):
        _, hints = self.label_line()
        kinds = []
        for node in hints.findall("control"):
            if node.get("type") == "image":
                kinds.append(node.findtext("texture"))
            elif node.get("type") == "label":
                kinds.append(node.findtext("label"))
            else:
                kinds.append(int(node.findtext("width")))
        self.assertEqual(kinds, ["bald/chevron_up.png", 8, "$VAR[P]", 28, "bald/chevron_down.png", 8, "$VAR[N]"])
        for node in hints.findall("control"):
            if node.get("type") == "label":
                self.assertEqual((node.findtext("font"), node.findtext("textcolor")), ("Bald_Hint", "bald_ink60"))
                self.assertEqual(node.find("width").get("max"), "260")
            if node.get("type") == "image":
                self.assertEqual((node.findtext("width"), node.findtext("height")), ("12", "12"))
                self.assertEqual(node.find("texture").get("colordiffuse"), "bald_ink60")
        # The next pair (gap, chevron, gap, name) hides when Down goes nowhere.
        self.assertEqual([node.findtext("visible") for node in hints.findall("control")][3:],
                         ["$EXP[H]"] * 4)

    def test_hidden_under_the_menu_and_dialogs_and_fading_when_idle(self):
        _, hints = self.label_line()
        self.assertEqual(hints.findtext("visible"), "!$EXP[Bald_MenuOpen] + !$EXP[Bald_DialogOver]")
        idle = [a for a in hints.findall("animation") if a.get("condition") == "$EXP[Bald_Idle]"]
        self.assertEqual(len(idle), 1)
        self.assertEqual(idle[0].find("effect").get("time"), "600")

    def test_nothing_can_collide(self):
        group, hints = self.label_line()
        line = [node for node in group.findall("control") if node.get("type") == "grouplist"][0]
        label = line.find("control")
        self.assertEqual(label.find("width").get("max"), "560")
        widest_hints = sum(int(n.findtext("width")) if n.get("type") != "label" else int(n.find("width").get("max"))
                           for n in hints.findall("control"))
        # Label, gap and the widest count ("25 of 25") at the left, the hints at the right, in 1248 px.
        self.assertLessEqual(560 + 14 + 80 + widest_hints, 1248)

    def test_no_row_dots_are_left(self):
        root = generated(["A", "B"])
        text = ET.tostring(root, encoding="unicode")
        self.assertNotIn("Bald_RowDots", text)
        self.assertNotIn("dots", text)


if __name__ == "__main__":
    unittest.main()
