import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


XML = Path(__file__).resolve().parents[1] / "1080i"


class HomeGeneratedIntegrationTests(unittest.TestCase):
    def test_generated_widget_file_is_registered_and_consumed(self):
        includes = ET.parse(XML / "Includes.xml").getroot()
        files = [node.get("file") for node in includes.findall("include")]
        self.assertIn("script-skinvariables-generator-includes.xml", files)

        home = ET.parse(XML / "Home.xml").getroot()
        self.assertIsNotNone(home.find(".//include[.='Bald_Generated_HomeWidgets']"))
        self.assertFalse(any(node.get("content") == "Bald_Row"
                             for node in home.findall(".//include")))

    def test_generated_rows_keep_stable_control_contract(self):
        generated = ET.parse(
            XML / "script-skinvariables-generator-includes.xml"
        ).getroot()
        definition = generated.find(
            "include[@name='Bald_Generated_HomeWidgets']/definition"
        )
        self.assertIsNotNone(definition)
        rows = [node for node in definition.findall("include")
                if node.get("content") == "Bald_Row"]
        self.assertEqual(
            [row.findtext("param[@name='id']") for row in rows],
            ["9101", "9102", "9103"],
        )
        self.assertTrue(all(row.findtext("param[@name='label']") for row in rows))
        self.assertTrue(all(row.findall("content") for row in rows))


if __name__ == "__main__":
    unittest.main()
