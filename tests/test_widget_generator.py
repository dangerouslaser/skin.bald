import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHORTCUTS = ROOT / "shortcuts"
GENERATED = ROOT / "1080i" / "script-skinvariables-generator-includes.xml"


class WidgetGeneratorTests(unittest.TestCase):
    def test_skinvariables_224_is_a_required_dependency(self):
        root = ET.parse(ROOT / "addon.xml").getroot()
        imports = {node.get("addon"): node for node in root.findall("./requires/import")}
        dependency = imports["script.skinvariables"]
        self.assertEqual(dependency.get("version"), "2.2.4")
        self.assertIsNone(dependency.get("optional"))

    def test_default_widget_schema_preserves_current_home(self):
        defaults = json.loads(
            (SHORTCUTS / "skinvariables-shortcut-homewidgets.json").read_text()
        )
        self.assertEqual(defaults, [
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
        self.assertEqual(datafiles, [
            "generator/home-widgets.xml",
            "generator/movies-widgets.xml",
            "generator/tvshows-widgets.xml",
        ])

        data = ET.parse(SHORTCUTS / "generator" / "home-widgets.xml").getroot()
        items = data.find("items")
        self.assertEqual(items.get("menu"), "homewidgets")
        self.assertEqual(items.get("mode"), "submenu")
        self.assertEqual(items.findtext("item/template"), "generator/home-widget.xmltemplate")

    def test_generated_home_include_keeps_runtime_contract(self):
        root = ET.parse(GENERATED).getroot()
        include = root.find("./include[@name='Bald_Generated_HomeWidgets']/definition")
        rows = include.findall("include")
        self.assertEqual([row.find("param[@name='id']").text for row in rows], ["9101", "9102", "9103"])
        self.assertTrue(all(row.findtext("param[@name='label']") for row in rows))
        self.assertTrue(all(row.findall("content") for row in rows))
        self.assertTrue(all(content.get("limit") for row in rows for content in row.findall("content")))

    def test_generated_media_screens_use_independent_row_ranges(self):
        root = ET.parse(GENERATED).getroot()
        movies = root.find("./include[@name='Bald_Generated_MoviesWidgets']/definition")
        tvshows = root.find("./include[@name='Bald_Generated_TVShowsWidgets']/definition")
        self.assertIsNotNone(movies)
        self.assertIsNotNone(tvshows)
        self.assertTrue(all(row.find("param[@name='id']").text.startswith("92") for row in movies.findall("include")))
        self.assertTrue(all(row.find("param[@name='id']").text.startswith("93") for row in tvshows.findall("include")))
        self.assertTrue(all(row.find("param[@name='screen']").text == "movies" for row in movies.findall("include")))
        self.assertTrue(all(row.find("param[@name='screen']").text == "tvshows" for row in tvshows.findall("include")))


if __name__ == "__main__":
    unittest.main()
