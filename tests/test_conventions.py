"""Repo-wide conventions for the Bald-native XML: named conditions and layout constants."""
import re
import unittest
import xml.etree.ElementTree as ET

from kodi_includes import CONSTANT_TAGS, EXP, NATIVE, SKIN, constants, expressions


def wraps_whole(body):
    """True when the body is one [...] group, ignoring $INFO[...]-style references inside it."""
    body = re.sub(r"\$[A-Z]+\[[^\[\]]*\]", "x", body.strip())
    if not (body.startswith("[") and body.endswith("]")):
        return False
    depth = 0
    for index, char in enumerate(body):
        depth += (char == "[") - (char == "]")
        if depth == 0:
            return index == len(body) - 1
    return False


class ExpressionTests(unittest.TestCase):
    def test_native_expression_bodies_are_bracket_wrapped(self):
        # A wrapped body negates and combines safely wherever $EXP[...] is placed.
        for path in NATIVE:
            root = ET.parse(path).getroot()
            for node in root.iter("expression"):
                with self.subTest(file=path.name, name=node.get("name")):
                    self.assertTrue(wraps_whole(node.text or ""), node.text)

    def test_every_static_expression_reference_resolves(self):
        known = set(expressions())
        for path in NATIVE:
            names = {name for name in EXP.findall(path.read_text()) if "$" not in name}
            with self.subTest(file=path.name):
                self.assertEqual(names - known, set())

    def test_timers_do_not_use_expressions(self):
        # docs/NOTES.md: $EXP in a Timers.xml condition did not trigger in Kodi 22.
        self.assertNotIn("$EXP[", (SKIN / "Timers.xml").read_text())



# Layout values named in Includes_Bald_Constants.xml, by the tag they are used in.
LAYOUT = {("left", "96"): "Bald_SafeLeft", ("top", "954"): "Bald_HintTop", ("left", "1440"): "Bald_RightColumn",
          ("left", "1296"): "Bald_PreviewLeft", ("top", "108"): "Bald_PageTitleTop", ("top", "222"): "Bald_ContentTop"}


class ConstantTests(unittest.TestCase):
    def test_bald_constants_load_at_every_screen_height(self):
        # Constants_720/1080.xml are conditional on the screen height; Bald's 1080i values must not be.
        registered = {node.get("file"): node.get("condition") for node in ET.parse(SKIN / "Includes.xml").getroot().findall("include")
                      if node.get("file")}
        self.assertIn("Includes_Bald_Constants.xml", registered)
        self.assertIsNone(registered["Includes_Bald_Constants.xml"])
        values = constants()
        for (tag, number), name in LAYOUT.items():
            self.assertEqual(values[name], number)

    def test_native_layout_uses_the_named_constants(self):
        values = constants()
        for path in NATIVE:
            root = ET.parse(path).getroot()
            for node in root.iter():
                text = (node.text or "").strip()
                if node.tag not in CONSTANT_TAGS or not text:
                    continue
                with self.subTest(file=path.name, tag=node.tag, value=text):
                    if text.startswith("Bald_"):
                        self.assertIn(text, values)
                    self.assertNotIn((node.tag, text), LAYOUT)


class IdMapTests(unittest.TestCase):
    def test_every_native_control_id_is_in_the_id_map(self):
        # 1080i/IDs lists IDs as numbers and ranges (5303-5999); a number anywhere in it counts as listed.
        text = (SKIN / "IDs").read_text()
        ranges = [(int(low), int(high)) for low, high in re.findall(r"\b(\d+)-(\d+)\b", text)]
        listed = {int(number) for number in re.findall(r"\b\d+\b", text)}

        def covered(number):
            return number in listed or any(low <= number <= high for low, high in ranges)

        for path in NATIVE:
            root = ET.parse(path).getroot()
            ids = {node.get("id") for node in root.iter("control") if node.get("id")}
            ids |= {node.get("value", node.text) for node in root.iter("param")
                    if node.get("name") in ("id", "control_id")}
            for value in sorted(i for i in ids if i and i.isdigit()):
                with self.subTest(file=path.name, id=value):
                    self.assertTrue(covered(int(value)))

if __name__ == "__main__":
    unittest.main()
