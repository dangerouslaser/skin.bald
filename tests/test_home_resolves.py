import unittest
import xml.etree.ElementTree as ET

from kodi_includes import Skin


def control(root, control_id):
    return next(node for node in root.iter("control") if node.get("id") == str(control_id))


class HomeResolvesTests(unittest.TestCase):
    def test_home_resolves_from_the_shipped_files_alone(self):
        # A fresh install: no Skin Variables output yet, so every generated name comes from the fallback.
        skin = Skin()
        home = skin.window("Home.xml")
        self.assertEqual(skin.unknown_references(home), [])
        self.assertNotIn("$PARAM[", ET.tostring(home, encoding="unicode"))
        self.assertIsNone(home.find(".//nested"))
        ids = {int(node.get("id")) for node in home.iter("control") if (node.get("id") or "").isdigit()}
        # Home, Live TV and the two seeded hubs (Movies in slot 1, TV shows in slot 2) have rows; slots 3-8 build none.
        self.assertLessEqual({9051, 9052, 9053, 9101, 9102, 9103, 9201, 9202, 9301, 9302}, ids)
        self.assertFalse({9054, 9104, 9203, 9303} & ids)
        self.assertFalse({row for base in range(9400, 10000, 100) for row in range(base + 1, base + 21)} & ids)
        self.assertLessEqual({9000, 9001, 9004, 9005, 9006, 9199} | set(range(9011, 9019)) | set(range(9021, 9030)), ids)
        self.assertFalse({9002, 9003, 9196, 9197} & ids)

    def test_resolved_rows_and_menu_carry_their_actions(self):
        home = Skin().window("Home.xml")
        movies = control(home, 9011)
        self.assertEqual([node.text for node in movies.findall("onleft")], ["Action(Select)"])
        self.assertIn("SetProperty(Bald.Screen,hub1,home)", [node.text for node in movies.findall("onclick")])
        row = control(home, 9102)
        self.assertEqual(len(row.findall("content")), 2)
        self.assertIn("Control.Move(9103,-2)", [node.text for node in row.findall("onfocus")])
        self.assertIn("ClearProperty(Bald.Start9302,home)", [node.text for node in home.findall("onload")])


if __name__ == "__main__":
    unittest.main()
