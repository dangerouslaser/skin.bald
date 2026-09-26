"""Startup splash: Home holds a splash over itself until every configured row has loaded (docs/NOTES.md)."""

import importlib.util
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import atoms, implies, parse
from skin_strings import english


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
SCREENS = (("home", 9100), ("movies", 9200), ("tvshows", 9300))
PRELOADING = "!String.IsEmpty(Window(home).Property(Bald.Preload))"


def configured(screen, base):
    rows = json.loads((ROOT / "shortcuts" / f"skinvariables-shortcut-{screen}widgets.json").read_text())
    return [base + index for index in range(1, len(rows) + 1)]


def load_builder():
    spec = importlib.util.spec_from_file_location("build_home_defaults", ROOT / "tools" / "build_home_defaults.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def loading_terms(text):
    """Bald_RowsLoading_<screen>: an "or" seeded with false (valid with no rows), one IsUpdating term per row."""
    if text.strip() == "[false]":
        return []
    kind, terms = parse(text)
    assert (kind, terms[0]) == ("or", False), text
    return terms[1:]


class PreloadSettingTests(unittest.TestCase):
    def test_setting_lives_in_behavior_and_defaults_on(self):
        root = ET.parse(XML / "Custom_1118_BaldAppearance.xml").getroot()
        row = root.find(".//control[@id='9624']")
        self.assertIsNotNone(row)
        self.assertEqual(row.get("type"), "radiobutton")
        # Behavior is category item 3.
        self.assertEqual(row.find("include[@content='Bald_SettingRow']/param[@name='item']").text, "3")
        self.assertEqual(english(row.findtext("label")), "Preload Home at startup")
        # A negatively named bool, so a fresh install (setting unset) preloads.
        self.assertEqual(row.findtext("selected"), "!Skin.HasSetting(Bald.DisablePreload)")
        self.assertEqual(row.findtext("onclick"), "Skin.ToggleSetting(Bald.DisablePreload)")


class PreloadRowsTests(unittest.TestCase):
    def test_every_row_counts_as_visible_while_preloading_and_still_loading(self):
        row = ET.parse(XML / "Includes_Bald_Home.xml").getroot().find(
            "include[@name='Bald_Row']/definition/control[@type='fixedlist']")
        visible = row.findtext("visible")
        # Whatever screen, row or menu state: preloading and still loading is enough.
        self.assertTrue(implies(f"{PRELOADING} + Container($PARAM[id]).IsUpdating", visible))
        # Once its list has fetched, the preload no longer holds the row visible (it hides behind the splash).
        self.assertFalse(implies(PRELOADING, visible))

    def test_fallback_waits_for_every_configured_row(self):
        fallback = ET.parse(XML / "Includes_Bald_HomeDefaults.xml").getroot()
        for screen, base in SCREENS:
            terms = loading_terms(fallback.findtext(f"expression[@name='Bald_RowsLoading_{screen}']"))
            self.assertEqual(terms, [("atom", f"Container({row}).IsUpdating") for row in configured(screen, base)])

    def test_generator_writes_one_loading_term_per_row_for_any_row_count(self):
        builder = load_builder()
        config = json.loads((ROOT / "shortcuts" / "skinvariables-generator.json").read_text())
        for count in (0, 1, 5):
            builder.menu_items = lambda menu, count=count: [
                {"label": f"Row {i}", "path": f"videodb://movies/titles/?r={i}", "target": "videos", "limit": "25",
                 "secondary": "0"} for i in range(count)]
            root = ET.fromstring(builder.build_xml(config))
            for screen, base in SCREENS:
                terms = loading_terms(root.findtext(f"expression[@name='Bald_RowsLoading_{screen}']"))
                self.assertEqual(terms, [("atom", f"Container({base + i}).IsUpdating") for i in range(1, count + 1)],
                                 (screen, count))

    def test_rows_loaded_covers_every_screen_and_waits_out_dialogs(self):
        text = "$EXP[Bald_RowsLoaded]"
        mentioned = atoms(text)
        for screen, base in SCREENS:
            for row in configured(screen, base):
                self.assertIn(f"Container({row}).IsUpdating", mentioned)
        # Under a modal dialog Container(...) reads the dialog, so the rows never count as loaded then.
        self.assertTrue(implies(text, "!System.HasActiveModalDialog"))
        # A Home row still loading keeps the splash up.
        self.assertTrue(implies("Container(9101).IsUpdating", "!" + text))


if __name__ == "__main__":
    unittest.main()
