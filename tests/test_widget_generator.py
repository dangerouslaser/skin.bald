import fnmatch
import importlib.util
import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHORTCUTS = ROOT / "shortcuts"
FALLBACK = ROOT / "1080i" / "Includes_Bald_HomeDefaults.xml"
SCREENS = (("home", "Home", 9100), ("movies", "Movies", 9200), ("tvshows", "TVShows", 9300))


def load_builder():
    spec = importlib.util.spec_from_file_location("build_home_defaults", ROOT / "tools" / "build_home_defaults.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def defaults(screen):
    return json.loads((SHORTCUTS / f"skinvariables-shortcut-{screen}widgets.json").read_text())


def fallback():
    return ET.parse(FALLBACK).getroot()


def definition(root, name):
    node = root.find(f"include[@name='{name}']/definition")
    if node is None:
        raise AssertionError(f"{name} is not defined")
    return node


def param(node, name):
    return node.findtext(f"param[@name='{name}']")


def expression_rows(root, name):
    text = root.findtext(f"expression[@name='{name}']")
    return [int(row) for row in re.findall(r"Container\((\d+)\)", text)]


class WidgetGeneratorTests(unittest.TestCase):
    def test_skinvariables_224_is_a_required_dependency(self):
        root = ET.parse(ROOT / "addon.xml").getroot()
        imports = {node.get("addon"): node for node in root.findall("./requires/import")}
        dependency = imports["script.skinvariables"]
        self.assertEqual(dependency.get("version"), "2.2.4")
        self.assertIsNone(dependency.get("optional"))

    def test_default_widget_schema_preserves_current_home(self):
        self.assertEqual(defaults("home"), [
            {
                "label": "Recently added movies",
                "path": "videodb://recentlyaddedmovies/",
                "path2": "",
                "secondary": "0",
                "target": "videos",
                "limit": "25",
            },
            {
                "label": "Continue watching",
                "path": "special://skin/playlists/inprogress_movies.xsp",
                "path2": "special://skin/playlists/inprogress_episodes.xsp",
                "secondary": "1",
                "target": "videos",
                "limit": "15",
            },
            {
                "label": "Next up",
                "path": "videodb://inprogresstvshows/",
                "path2": "",
                "secondary": "0",
                "target": "videos",
                "limit": "25",
            },
        ])

    def test_generator_uses_skinvariables_node_contract(self):
        config = json.loads((SHORTCUTS / "skinvariables-generator.json").read_text())
        self.assertEqual(config["skinid"], "skin.bald")
        self.assertEqual(config["folder"], "1080i")
        self.assertEqual(config["output"], "script-skinvariables-generator-includes{skinuser}.xml")
        datafiles = [part["datafile"] for part in config["genxml"] if "datafile" in part]
        self.assertTrue(datafiles)
        for names in datafiles:
            self.assertEqual(names[0], "generator/screens.xml")
            for name in names:
                self.assertTrue((SHORTCUTS / name).is_file(), name)

        lists = ET.parse(SHORTCUTS / "generator" / "screens.xml").getroot().findall("lists/list")
        self.assertEqual(
            [(node.get("name"), node.findtext("value[@name='menu']"), node.findtext("value[@name='title']"),
              int(node.findtext("value[@name='base']"))) for node in lists],
            [(screen, f"{screen}widgets", title, base) for screen, title, base in SCREENS],
        )
        for path in (SHORTCUTS / "generator").glob("*.xml"):
            for items in ET.parse(path).getroot().iter("items"):
                if items.get("menu"):
                    self.assertEqual(items.get("menu"), "{menu}", path.name)
                    self.assertEqual(items.get("mode"), "submenu", path.name)

    def test_generator_conditions_do_not_need_kodi(self):
        # Skin Variables compares a==b and a!=b itself; anything else is a Kodi condition, which the fallback
        # builder cannot reproduce.
        for path in (SHORTCUTS / "generator").glob("*.xml"):
            for node in ET.parse(path).getroot().iter("condition"):
                self.assertRegex(node.text, r"==|!=", path.name)

    def test_fallback_and_build_version_are_current(self):
        builder = load_builder()
        self.assertEqual(FALLBACK.read_text(), builder.fallback_text(),
                         "run python3 tools/build_home_defaults.py")
        self.assertEqual((SHORTCUTS / "skinvariables-generator.json").read_text(), builder.stamped_config_text(),
                         "run python3 tools/build_home_defaults.py")

    def test_fallback_rows_match_the_shipped_defaults(self):
        root = fallback()
        for screen, title, base in SCREENS:
            items = defaults(screen)
            rows = definition(root, f"Bald_Generated_{title}Widgets").findall("include")
            self.assertTrue(all(row.get("content") == "Bald_Row" for row in rows))
            ids = [base + index for index in range(1, len(items) + 1)]
            self.assertEqual([int(param(row, "id")) for row in rows], ids)
            self.assertEqual([param(row, "label") for row in rows], [item["label"] for item in items])
            self.assertEqual([int(param(row, "index")) for row in rows], list(range(1, len(items) + 1)))
            self.assertTrue(all(param(row, "screen") == screen for row in rows))
            for position, (row, item) in enumerate(zip(rows, items)):
                paths = [item["path"]] + ([item["path2"]] if item["secondary"] == "1" else [])
                contents = row.findall("content")
                self.assertEqual([node.text for node in contents], paths)
                self.assertTrue(all(node.get("limit") == item["limit"] for node in contents))
                self.assertTrue(all(node.get("target") == item["target"] for node in contents))
                up = "SetFocus(9000,0,absolute)" if position == 0 else str(ids[position - 1])
                down = str(ids[position + 1]) if position + 1 < len(ids) else ""
                self.assertEqual(param(row, "up"), up)
                self.assertEqual(param(row, "down"), down)

    def test_bindings_exist_only_for_configured_rows(self):
        root = fallback()
        for screen, title, base in SCREENS:
            ids = [base + index for index in range(1, len(defaults(screen)) + 1)]
            for name in ("Bald_ConfiguredArtLogos", "Bald_ConfiguredCaptions"):
                instances = definition(root, f"{name}_{screen}").findall("include")
                self.assertEqual([(int(param(node, "c")), param(node, "p")) for node in instances],
                                 [(row, parity) for row in ids for parity in ("Odd", "Even")])
                for node in instances:
                    self.assertEqual(
                        param(node, "preview"),
                        f"$EXP[Bald_Preview{title}] + String.IsEqual(Window(home).Property(Bald.Row.{screen}),{param(node, 'c')})",
                    )
            for name in ("ItemOdd", "HasLogo", "PreviewItemOdd", "PreviewHasLogo"):
                self.assertEqual(sorted(set(expression_rows(root, f"Bald_{name}_{screen}"))), ids)
                self.assertTrue(root.findtext(f"expression[@name='Bald_{name}_{screen}']").startswith("[false]"))

    def test_art_variables_prefer_the_previewed_screen_then_the_current_row(self):
        root = fallback()
        configured = [base + index for screen, _, base in SCREENS for index in range(1, len(defaults(screen)) + 1)]
        for name, per_row in (("Bald_Fanart", 3), ("Bald_Logo", 2)):
            values = root.findall(f"variable[@name='{name}']/value")
            conditions = [value.get("condition") for value in values]
            catch_all = conditions.index("$EXP[Bald_WidgetPreview]")
            self.assertEqual(catch_all, per_row * len(configured))
            self.assertTrue(all("$EXP[Bald_Preview" in c for c in conditions[:catch_all]))
            self.assertTrue(all(c.startswith("String.IsEqual(Window(home).Property(Bald.Row),") for c in conditions[catch_all + 1:-1]))
            self.assertIsNone(conditions[-1])
            rows = [int(row) for row in re.findall(r"Container\((\d+)\)", " ".join(value.text or "" for value in values))]
            self.assertEqual(sorted(set(rows)), configured)

    def test_generated_output_is_not_tracked(self):
        patterns = [line.strip() for line in (ROOT / ".gitignore").read_text().splitlines() if line.strip() and not line.startswith("#")]
        self.assertTrue(any(fnmatch.fnmatch("1080i/script-skinvariables-generator-includes.xml", pattern) for pattern in patterns))
        self.assertFalse(any(fnmatch.fnmatch(FALLBACK.relative_to(ROOT).as_posix(), pattern) for pattern in patterns))


if __name__ == "__main__":
    unittest.main()
