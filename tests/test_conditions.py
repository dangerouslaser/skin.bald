"""The condition logic the structural tests rely on (tests/conditions.py)."""
import unittest
import xml.etree.ElementTree as ET

from kodi_includes import SKIN
from conditions import ConditionError, atoms, equivalent, implies, parse, same_actions


BODIES = {"Open": "[Skin.HasSetting(a) + !Skin.HasSetting(b)]", "Bare": "x | y", "Rows": "[false]| [true]"}


class ConditionLogicTests(unittest.TestCase):
    def test_precedence_is_not_then_and_then_or(self):
        self.assertEqual(parse("!a + b | c"), ("or", [("and", [("not", ("atom", "a")), ("atom", "b")]), ("atom", "c")]))
        self.assertTrue(equivalent("a + b | c", "[a + b] | c"))
        self.assertFalse(equivalent("a + b | c", "a + [b | c]"))

    def test_spelling_differences_compare_equal(self):
        self.assertTrue(equivalent("[a + b] | c", "c | b + a"))
        self.assertTrue(equivalent("!!a", "a"))
        self.assertTrue(equivalent("!Skin.HasSetting(b) + Skin.HasSetting(a)", "$EXP[Open]", BODIES))
        self.assertTrue(equivalent("String.IsEqual(Window(home).Property(x), 1)", "String.IsEqual(Window(home).Property(x),1)"))

    def test_expression_bodies_group_as_kodi_flattens_them(self):
        # "!$EXP[Bare]" is !(x | y), not !x | y.
        self.assertTrue(equivalent("!$EXP[Bare]", "!x + !y", BODIES))
        self.assertTrue(equivalent("!$EXP[Rows]", "false", BODIES))

    def test_references_and_parentheses_stay_inside_one_atom(self):
        self.assertEqual(atoms("String.IsEqual(Container($PARAM[c]).ListItem.Label,a+b|c) + $INFO[x,[,]]"),
                         {"String.IsEqual(Container($PARAM[c]).ListItem.Label,a+b|c)", "$INFO[x,[,]]"})

    def test_implication(self):
        self.assertTrue(implies("a + [b | c]", "a"))
        self.assertFalse(implies("a | b", "a"))
        self.assertTrue(implies("$EXP[Open] + z", "!Skin.HasSetting(b)", BODIES))
        self.assertTrue(implies("p | x + y", "y", assume={"p": False}))
        self.assertFalse(implies("p | x + y", "y"))

    def test_actions_compare_conditions_by_meaning(self):
        self.assertTrue(same_actions([("[a]", "Go"), (None, "Stop")], [("a", "Go"), ("true", "Stop")]))
        self.assertFalse(same_actions([("a", "Go")], [("!a", "Go")]))
        self.assertFalse(same_actions([("a", "Go")], [("a", "Go"), (None, "Stop")]))

    def test_malformed_conditions_are_errors(self):
        for text in ("", "a +", "[a", "a ]", "+ a"):
            with self.subTest(text=text), self.assertRaises(ConditionError):
                parse(text)


class SkinConditionsParseTests(unittest.TestCase):
    def test_every_condition_in_the_skin_parses(self):
        # Balanced brackets and no dangling operator in every <visible>, <expression> and condition attribute.
        for path in sorted(SKIN.glob("*.xml")):
            for node in ET.parse(path).getroot().iter():
                texts = [node.text] if node.tag in ("visible", "expression") else []
                for text in texts + [node.get("condition")]:
                    if text and text.strip():
                        with self.subTest(file=path.name, tag=node.tag, condition=text[:80]):
                            parse(text)


if __name__ == "__main__":
    unittest.main()
