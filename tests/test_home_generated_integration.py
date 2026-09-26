import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


XML = Path(__file__).resolve().parents[1] / "1080i"
GENERATED = "script-skinvariables-generator-includes.xml"
FALLBACK = "Includes_Bald_HomeDefaults.xml"


def file_includes():
    includes = ET.parse(XML / "Includes.xml").getroot()
    return [node.get("file") for node in includes.findall("include") if node.get("file")]


def defined_names(root):
    return {(node.tag, node.get("name")) for node in root if node.get("name")}


class HomeGeneratedIntegrationTests(unittest.TestCase):
    def test_generated_file_loads_before_the_shipped_fallback(self):
        # Kodi keeps the first definition of a name, so the per-install build must come first and the fallback last.
        files = file_includes()
        self.assertIn(GENERATED, files)
        self.assertEqual(files[-1], FALLBACK)
        self.assertLess(files.index(GENERATED), files.index(FALLBACK))
        self.assertNotIn("Includes_Bald_HomeRows.xml", files)
        self.assertFalse((XML / "Includes_Bald_HomeRows.xml").exists())

    def test_home_consumes_the_generated_rows_and_bindings(self):
        home = ET.parse(XML / "Home.xml").getroot()
        used = {(node.text or "").strip() for node in home.iter("include")} | {node.get("content") for node in home.iter("include")}
        for name in ("Bald_Generated_HomeWidgets", "Bald_Generated_MoviesWidgets", "Bald_Generated_TVShowsWidgets",
                     "Bald_ConfiguredArtLogos", "Bald_ConfiguredCaptions"):
            self.assertIn(name, used)
        self.assertFalse(any(node.get("content") == "Bald_Row" for node in home.iter("include")))

    def test_names_the_skin_expects_from_the_generator_exist_in_the_fallback(self):
        fallback = defined_names(ET.parse(XML / FALLBACK).getroot())
        home = (XML / "Includes_Bald_Home.xml").read_text() + (XML / "Home.xml").read_text()
        wanted = set()
        for screen in ("home", "movies", "tvshows"):
            for name in ("ItemOdd", "HasLogo", "PreviewItemOdd", "PreviewHasLogo"):
                self.assertIn(f"$EXP[Bald_{name}_{screen}]", home)
                wanted.add(("expression", f"Bald_{name}_{screen}"))
            for name in ("ConfiguredArtLogos", "ConfiguredCaptions"):
                self.assertIn(f"Bald_{name}_{screen}", home)
                wanted.add(("include", f"Bald_{name}_{screen}"))
        wanted |= {("variable", "Bald_Fanart"), ("variable", "Bald_Logo")}
        self.assertLessEqual(wanted, fallback)

    def test_every_generated_name_is_defined_nowhere_else(self):
        fallback = defined_names(ET.parse(XML / FALLBACK).getroot())
        for path in XML.glob("*.xml"):
            if path.name in {FALLBACK, GENERATED}:
                continue
            root = ET.parse(path).getroot()
            if root.tag != "includes":
                continue
            clash = fallback & {(node.tag, node.get("name")) for node in root.iter() if node.get("name")
                                and node.tag in {"include", "variable", "expression"}}
            self.assertFalse(clash, path.name)

    def test_expressions_break_lines_only_after_operators(self):
        # Kodi's condition parser skips whitespace after an operator only; a newline inside an operand breaks it.
        root = ET.parse(XML / FALLBACK).getroot()
        for node in root.findall("expression"):
            for line in node.text.split("\n")[:-1]:
                self.assertTrue(re.search(r"[\]|+!\[]\s*$", line), node.get("name"))


if __name__ == "__main__":
    unittest.main()
