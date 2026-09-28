"""Idle after (Appearance › Behavior, Skin.String(Bald.IdleTime)): how long Home and Now Playing wait before the idle
state. One expression, Bald_IdleReached, decides it everywhere (Home's dims and hints, Now Playing's dim, the idle and
ambient timers); the burn-in drift follows it too but keeps running, after the default minute, with idle off."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import parse
from skin_strings import loc

ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
VALUES = ("", "2", "5", "10", "off", "junk")
# Seconds before idle for each stored value (None: never).
THRESHOLD = {"": 60, "2": 120, "5": 300, "10": 600, "off": None, "junk": 60}


def root(name):
    return ET.parse(XML / name).getroot()


def expression(name):
    for file in XML.glob("Includes*.xml"):
        body = root(file.name).findtext(f"expression[@name='{name}']")
        if body is not None:
            return body
    raise AssertionError(name)


def evaluate(tree, stored, seconds):
    """A parsed condition with Skin.String(Bald.IdleTime) = `stored` and `seconds` since the last key."""
    if isinstance(tree, bool):
        return tree
    kind, value = tree
    if kind == "atom":
        if value == "String.IsEmpty(Skin.String(Bald.IdleTime))":
            return stored == ""
        match = re.fullmatch(r"Skin\.String\(Bald\.IdleTime,(\w+)\)", value)
        if match:
            return stored.lower() == match.group(1).lower()
        match = re.fullmatch(r"System\.IdleTime\((\d+)\)", value)
        if match:
            return seconds >= int(match.group(1))
        raise AssertionError(f"unexpected atom {value}")
    if kind == "not":
        return not evaluate(value, stored, seconds)
    results = [evaluate(term, stored, seconds) for term in value]
    return all(results) if kind == "and" else any(results)


def threshold(condition, stored):
    """The first whole second (up to an hour) at which the condition holds, or None."""
    tree = parse(condition)
    for seconds in (0, 59, 60, 119, 120, 299, 300, 599, 600, 3600):
        if evaluate(tree, stored, seconds):
            return seconds
    return None


class IdleTests(unittest.TestCase):
    def test_every_setting_value_has_its_threshold(self):
        body = expression("Bald_IdleReached")
        for stored, seconds in THRESHOLD.items():
            with self.subTest(stored=stored):
                self.assertEqual(threshold(body, stored), seconds)

    def test_the_drift_keeps_guarding_with_idle_off(self):
        body = expression("Bald_DriftIdle")
        for stored, seconds in THRESHOLD.items():
            with self.subTest(stored=stored):
                self.assertEqual(threshold(body, stored), 60 if seconds is None else seconds)

    def test_home_and_now_playing_use_the_one_expression(self):
        self.assertEqual(expression("Bald_Idle"), "[$EXP[Bald_IdleReached] + Window.IsActive(home)]")
        self.assertEqual(expression("Bald_NowPlayingIdle"), "[$EXP[Bald_IdleReached] + !Window.IsVisible(musicosd)]")
        # No fixed idle time is left anywhere else in the skin (the OSD's pause delay counts seconds, not idle).
        for path in XML.glob("*.xml"):
            if "generator" in path.name or path.name == "Timers.xml":
                continue
            text = path.read_text(encoding="utf-8")
            for body in (expression("Bald_DriftIdle"), expression("Bald_IdleReached")):
                text = text.replace(body, "")
            for seconds in re.findall(r"System\.IdleTime\((\d+)\)", text):
                self.assertLess(int(seconds), 10, path.name)

    def test_timers_spell_out_the_expressions(self):
        # $EXP does not trigger in Timers.xml, so the bodies are written out; they must stay the same.
        idle, drift = expression("Bald_IdleReached"), expression("Bald_DriftIdle")
        timers = {t.findtext("name"): t for t in root("Timers.xml").iter("timer")}
        home = timers["bald_idle"]
        self.assertIn(f"+ {idle} +", home.findtext("start"))
        self.assertTrue(home.findtext("stop").startswith(f"!{idle} |"))
        ambient = timers["bald_ambient"]
        self.assertIn(f"+ {idle} +", ambient.findtext("start"))
        self.assertIn(f"| !{idle}", ambient.findtext("stop"))
        self.assertTrue(ambient.find("onstop").get("condition").startswith(f"{idle} +"))
        drifting = timers["bald_drift"]
        self.assertTrue(drifting.findtext("start").startswith(f"{drift} +"))
        self.assertTrue(drifting.findtext("stop").startswith(f"!{drift} |"))
        text = (XML / "Timers.xml").read_text(encoding="utf-8").replace(drift, "").replace(idle, "")
        self.assertNotIn("System.IdleTime", text)
        for timer in (home, ambient, drifting):
            conditions = [timer.findtext("start"), timer.findtext("stop")] + [
                n.get("condition") or "" for n in timer if n.tag in ("onstart", "onstop")]
            self.assertNotIn("$EXP", " ".join(conditions))

    def test_the_setting_row_cycles_every_value(self):
        row = root("Custom_1118_BaldAppearance.xml").find(".//control[@id='9680']")
        self.assertEqual(row.get("type"), "button")
        self.assertEqual(row.findtext("label"), loc("Idle after"))
        self.assertEqual(row.findtext("label2"), "$VAR[Bald_IdleTimeLabel]")
        self.assertEqual(row.find("include/param[@name='item']").text, "3")  # Behavior
        actions = [(parse(n.get("condition")), n.text) for n in row.findall("onclick")]

        def click(stored):
            # Kodi checks every condition before it runs the actions.
            chosen = [text for tree, text in actions if evaluate(tree, stored, 0)]
            self.assertEqual(len(chosen), 1, stored)
            if chosen[0] == "Skin.Reset(Bald.IdleTime)":
                return ""
            return re.fullmatch(r"Skin\.SetString\(Bald\.IdleTime,(\w+)\)", chosen[0]).group(1)

        seen, stored = [], ""
        for _ in range(5):
            stored = click(stored)
            seen.append(stored)
        self.assertEqual(seen, ["2", "5", "10", "off", ""])
        self.assertEqual(click("junk"), "")
        # The label names each value; anything unknown reads as the default it behaves as.
        labels = [(n.get("condition"), n.text) for n in root("Includes_Bald_Common.xml").findall(
            "variable[@name='Bald_IdleTimeLabel']/value")]
        self.assertEqual(labels, [("Skin.String(Bald.IdleTime,off)", "$LOCALIZE[351]"),
                                  ("Skin.String(Bald.IdleTime,2)", "2 $LOCALIZE[31710]"),
                                  ("Skin.String(Bald.IdleTime,5)", "5 $LOCALIZE[31710]"),
                                  ("Skin.String(Bald.IdleTime,10)", "10 $LOCALIZE[31710]"),
                                  (None, "1 $LOCALIZE[31710]")])

    def test_ambient_movement_greys_out_with_idle_off(self):
        row = root("Custom_1118_BaldAppearance.xml").find(".//control[@id='9621']")
        self.assertEqual(row.findtext("enable"), "!Skin.String(Bald.IdleTime,off)")

    def test_id_and_german_string(self):
        self.assertRegex((XML / "IDs").read_text(encoding="utf-8"), r"(?m)^9680\tBehavior: idle after")
        german = (ROOT / "language" / "resource.language.de_de" / "strings.po").read_text(encoding="utf-8")
        self.assertIn('msgctxt "#31370"\nmsgid "Idle after"\nmsgstr "Leerlauf nach"', german)


if __name__ == "__main__":
    unittest.main()
