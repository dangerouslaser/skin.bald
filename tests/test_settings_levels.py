"""Settings levels in Bald's own settings windows: Basic, Standard, Advanced and Expert, as Kodi's settings pages have.

The level lives in Skin.String(Bald.SettingsLevel) (unset is Standard) and is cycled by button 9090 under each Bald
settings sidebar. Every row declares a level (Bald_ConfigureRow, Bald_SettingRow) and hides while the chosen level is
lower; a category hides when all of its rows do."""

import re
import unittest
import xml.etree.ElementTree as ET

from conditions import all_of, equivalent, parse
from kodi_includes import SKIN, include_definitions, resolve_window

LEVELS = ("basic", "standard", "advanced", "expert")
LEVEL_LABELS = {"basic": "$LOCALIZE[10036]", "standard": "$LOCALIZE[10037]", "advanced": "$LOCALIZE[10038]",
                "expert": "$LOCALIZE[10039]"}
LEVEL_ATOM = re.compile(r"\$EXP\[Bald_SettingsLevel_(\w+)\]")
# Window, sidebar list, row grouplist (None: the hub, whose detail pane is one Open button).
WINDOWS = {
    "Custom_1115_BaldSettings.xml": ("9000", "9001"),
    "SkinSettings.xml": ("9000", "9001"),
    "Custom_1116_BaldHomeWidgets.xml": ("9100", "9200"),
    "Custom_1117_BaldHomeScreens.xml": ("9300", "9400"),
    "Custom_1118_BaldAppearance.xml": ("9500", "9600"),
    "Custom_1119_BaldPlayback.xml": ("9700", "9800"),
}
ROW_WINDOWS = [name for name, (_, rows) in WINDOWS.items() if rows != "9001"]
ROW_INCLUDES = ("Bald_ConfigureRow", "Bald_SettingRow", "Bald_RatingsSettingRow")
STORED = (None, "basic", "advanced", "expert", "unknown")


def evaluate(tree, stored):
    """A parsed condition's value with Skin.String(Bald.SettingsLevel) holding `stored` (None: unset)."""
    if isinstance(tree, bool):
        return tree
    kind, value = tree
    if kind == "atom":
        if value == "String.IsEmpty(Skin.String(Bald.SettingsLevel))":
            return stored is None
        match = re.fullmatch(r"Skin\.String\(Bald\.SettingsLevel,(\w+)\)", value)
        if not match:
            raise AssertionError(f"unexpected atom {value}")
        return stored is not None and stored.lower() == match.group(1).lower()
    if kind == "not":
        return not evaluate(value, stored)
    results = [evaluate(term, stored) for term in value]
    return all(results) if kind == "and" else any(results)


def shown(condition, stored):
    return evaluate(parse(condition), stored)


def effective(stored):
    """The level Kodi's user has chosen: unset and unknown values are Standard."""
    return stored if stored in LEVELS else "standard"


class SettingsLevelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        definitions = include_definitions()
        cls.windows = {name: resolve_window(name, definitions) for name in WINDOWS}

    def control(self, window, control_id):
        found = [node for node in self.windows[window].iter("control") if node.get("id") == control_id]
        self.assertEqual(len(found), 1, f"{window}: control {control_id}")
        return found[0]

    def rows(self, window):
        return self.control(window, WINDOWS[window][1]).findall("control")

    def row_level(self, row):
        levels = [level for node in row.findall("visible") for level in LEVEL_ATOM.findall(node.text)]
        self.assertEqual(len(levels), 1, f"row {row.get('id')} must declare one settings level, has {levels}")
        self.assertIn(levels[0], LEVELS, row.get("id"))
        return levels[0]

    def test_levels_are_cumulative_and_unset_is_standard(self):
        for stored in STORED:
            with self.subTest(stored=stored):
                visible = [level for level in LEVELS
                           if shown(f"$EXP[Bald_SettingsLevel_{level}]", stored)]
                self.assertEqual(visible, list(LEVELS[:LEVELS.index(effective(stored)) + 1]))

    def test_every_row_declares_a_level(self):
        for name in ROW_WINDOWS:
            rows = self.rows(name)
            self.assertTrue(rows, name)
            for row in rows:
                with self.subTest(window=name, row=row.get("id")):
                    self.row_level(row)

    def test_every_row_include_call_passes_a_level(self):
        # A call without one would resolve to $EXP[Bald_SettingsLevel_], which Kodi cannot resolve.
        for path in sorted(SKIN.glob("*.xml")):
            for call in ET.parse(path).getroot().iter("include"):
                if call.get("content") not in ROW_INCLUDES:
                    continue
                level = call.findtext("param[@name='level']")
                with self.subTest(file=path.name, include=call.get("content")):
                    self.assertIsNotNone(level)
                    self.assertIn(level, LEVELS + ("$PARAM[level]",))

    def test_every_level_has_rows_and_basic_keeps_each_window_usable(self):
        seen = set()
        for name in ROW_WINDOWS:
            levels = [self.row_level(row) for row in self.rows(name)]
            seen |= set(levels)
            self.assertIn("basic", levels, f"{name} shows nothing at Basic")
        self.assertEqual(seen, set(LEVELS))

    def test_level_button_cycles_through_all_four_levels(self):
        for name in WINDOWS:
            with self.subTest(window=name):
                button = self.control(name, "9090")
                self.assertEqual(button.get("type"), "button")
                clicks = [(node.get("condition") or "true", node.text) for node in button.findall("onclick")]
                label = button.findtext("label")
                self.assertEqual(label, "$VAR[Bald_SettingsLevelLabel]")
                stored, visited = None, []
                for _ in range(len(LEVELS)):
                    visited.append(effective(stored))
                    # Kodi decides every condition before it runs the click's actions.
                    run = [action for condition, action in clicks if shown(condition, stored)]
                    self.assertEqual(len(run), 1, (stored, run))
                    action = run[0]
                    if action == "Skin.Reset(Bald.SettingsLevel)":
                        stored = None
                    else:
                        stored = re.fullmatch(r"Skin\.SetString\(Bald\.SettingsLevel,(\w+)\)", action).group(1)
                self.assertIsNone(stored, "four clicks come back to the start")
                self.assertEqual(visited, ["standard", "advanced", "expert", "basic"])
                # An unknown value goes back to Standard.
                run = [action for condition, action in clicks if shown(condition, "unknown")]
                self.assertEqual(run, ["Skin.Reset(Bald.SettingsLevel)"])

    def test_level_label_names_the_chosen_level_with_kodis_strings(self):
        variable = ET.parse(SKIN / "Includes_Bald_Configure.xml").getroot().find(
            "variable[@name='Bald_SettingsLevelLabel']")
        values = [(node.get("condition"), node.text) for node in variable.findall("value")]
        self.assertIsNone(values[-1][0])
        for stored in STORED:
            with self.subTest(stored=stored):
                label = next(text for condition, text in values if condition is None or shown(condition, stored))
                self.assertEqual(label, LEVEL_LABELS[effective(stored)])

    def test_level_button_sits_under_the_sidebar_and_joins_its_navigation(self):
        for name, (sidebar, rows) in WINDOWS.items():
            with self.subTest(window=name):
                button = self.control(name, "9090")
                self.assertEqual((button.findtext("left"), button.findtext("top")), ("96", "938"))
                self.assertEqual(self.control(name, sidebar).findtext("ondown"), "9090")
                self.assertEqual(button.findtext("onup"), sidebar)
                self.assertEqual(button.findtext("onright"), rows)
        # Kodi's own settings pages draw the same level button (control 20, which Kodi labels and cycles).
        kodi = resolve_window("SettingsCategory.xml")
        level = next(node for node in kodi.iter("control") if node.get("id") == "20")
        self.assertEqual((level.findtext("left"), level.findtext("top")), ("96", "938"))

    def test_a_category_hides_when_all_of_its_rows_do(self):
        for name in ("Custom_1118_BaldAppearance.xml", "Custom_1119_BaldPlayback.xml"):
            sidebar = WINDOWS[name][0]
            items = self.control(name, sidebar).findall("content/item")
            for item in items:
                with self.subTest(window=name, category=item.get("id")):
                    focus = f"Container({sidebar}).HasFocus({item.get('id')})"
                    levels = {self.row_level(row) for row in self.rows(name)
                              if any(focus in (node.text or "") for node in row.findall("visible"))}
                    self.assertTrue(levels)
                    lowest = min(levels, key=LEVELS.index)
                    visible = all_of([node.text for node in item.findall("visible")])
                    self.assertTrue(equivalent(visible, f"$EXP[Bald_SettingsLevel_{lowest}]"), visible)


if __name__ == "__main__":
    unittest.main()
