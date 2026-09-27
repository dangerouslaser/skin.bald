"""The skin's side of Bald Helper's actions: every call site of a moved action sends NotifyAll while the helper
serves ($EXP[Bald_HelperActions]) and keeps its RunScript otherwise; the requests carry only safe values and parse
as the service expects. The service itself is tested in test_bald_helper_actions.py."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import equivalent, implies
from support import helper

ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
actions = helper("actions", "actions_skin")

SERVES = "$EXP[Bald_HelperActions]"
MOVED = ("tvinfo", "recommendations", "play", "open", "seriesmeta", "letters")
KEPT = ("mouse", "font", "hubs", "recommended")
# The only values a request may carry: library types and ids, and literal view ids.
SAFE_INFO = {
    "$INFO[ListItem.DBType]": "episode", "$INFO[ListItem.DBID]": "22",
    "$INFO[Container(5302).ListItem.DBID]": "23", "$INFO[Container(5100).ListItem.DBType]": "movie",
    "$INFO[Container(5100).ListItem.DBID]": "24", "$INFO[Window(movieinformation).Property(Bald.TV.NextID)]": "25",
}


def skin_files():
    # Skin Variables' generated includes are per install and never edited (docs/NOTES.md).
    return [path for path in sorted(XML.glob("*.xml")) if not path.name.startswith("script-skinvariables-generator")]


def sites():
    """(file, parent, element) for every action element in the skin."""
    for path in skin_files():
        root = ET.parse(path).getroot()
        for parent in root.iter():
            for element in parent:
                yield path.name, parent, element


def runscript_action(text):
    match = re.match(r"RunScript\(skin\.bald,(\w+)", (text or "").strip())
    return match.group(1) if match else None


def request(text):
    """The notification a NotifyAll element sends, with its $INFO values filled in as Kodi would."""
    match = re.fullmatch(r"NotifyAll\((skin\.bald),([^,()]*(?:\$INFO\[[^\]]*\][^,()]*)*)\)", text.strip())
    assert match, text
    data = match.group(2)
    for info in re.findall(r"\$INFO\[[^\]]*\]", data):
        assert info in SAFE_INFO, f"unsafe value in a request: {info}"
        data = data.replace(info, SAFE_INFO[info])
    return actions.parse(match.group(1), "Other." + data)


class ExpressionTests(unittest.TestCase):
    def test_serves_means_enabled_and_advertising_this_protocol(self):
        root = ET.parse(XML / "Includes_Bald_Common.xml").getroot()
        body = root.findtext("expression[@name='Bald_HelperActions']")
        self.assertTrue(equivalent(body, "$EXP[Bald_HasHelper] + String.IsEqual(Window(home).Property("
                                         f"{actions.PROPERTY_READY}),{actions.PROTOCOL})"), body)


class CallSiteTests(unittest.TestCase):
    def test_every_moved_runscript_is_the_fallback_beside_a_notifyall(self):
        found = {}
        for name, parent, element in sites():
            action = runscript_action(element.text)
            if action not in MOVED or element.tag == "param":
                continue
            with self.subTest(file=name, action=action, text=element.text):
                condition = element.get("condition")
                self.assertTrue(condition and implies(condition, f"!{SERVES}"), condition)
                found.setdefault(action, []).append(name)
                if action == "tvinfo":
                    continue  # DialogVideoInfo's bald.info request covers it (below)
                helper = [n for n in parent if n.tag == element.tag and (n.text or "").startswith("NotifyAll(")]
                self.assertEqual(len(helper), 1)
                # The same condition with the helper serving instead.
                base = condition.replace(f"!{SERVES}", "true")
                self.assertTrue(equivalent(helper[0].get("condition"), f"[{base}] + {SERVES}"),
                                helper[0].get("condition"))
                sent = request(helper[0].text)
                expected = "play" if action == "play" else ("info" if action == "recommendations" else action)
                self.assertEqual(sent.action, expected)
        self.assertEqual(set(found), set(MOVED))
        self.assertEqual(len(found["letters"]), 21)  # 15 video call sites, Right and Down on each music view

    def test_every_notifyall_needs_the_helper_and_parses(self):
        sent = set()
        for name, _, element in sites():
            text = (element.text or "").strip()
            if not text.startswith("NotifyAll(") or element.tag == "param":
                continue  # the pill's helper param: test_the_next_episode_action_uses_the_pills_helper_params
            with self.subTest(file=name, text=text):
                self.assertTrue(implies(element.get("condition") or "true", SERVES))
                parsed = request(text)
                self.assertIsNotNone(parsed)
                sent.add(parsed.action)
        self.assertEqual(sent, {"info", "play", "open", "seriesmeta", "letters"})

    def test_info_opened_sends_one_request_for_recommendations_and_tvinfo(self):
        dialog = ET.parse(XML / "DialogVideoInfo.xml").getroot()
        onload = [(n.get("condition"), n.text) for n in dialog.findall("onload")]
        self.assertIn((SERVES, "NotifyAll(skin.bald,bald.info|$INFO[ListItem.DBType]|$INFO[ListItem.DBID])"),
                      onload)
        # It comes after the identity it is checked against is set.
        texts = [text for _, text in onload]
        identity = next(i for i, t in enumerate(texts) if t.startswith("SetProperty(Bald.Identity,"))
        self.assertLess(identity, texts.index("NotifyAll(skin.bald,bald.info|$INFO[ListItem.DBType]|$INFO[ListItem.DBID])"))
        tv = ET.parse(XML / "Includes_Bald_InfoTV.xml").getroot().find("include[@name='Bald_InfoTVOnLoad']")
        self.assertEqual([n.text for n in tv.findall("onload") if "NotifyAll" in n.text], [])
        # The TV onload is used only by the dialog that sends bald.info.
        users = [path.name for path in skin_files() if "<include condition=\"$EXP[Bald_InfoTVItem]\">Bald_InfoTVOnLoad"
                 in path.read_text()]
        self.assertEqual(users, ["DialogVideoInfo.xml"])

    def test_the_next_episode_action_uses_the_pills_helper_params(self):
        tv = ET.parse(XML / "Includes_Bald_InfoTV.xml").getroot()
        pill = next(n for n in tv.iter("include") if n.get("content") == "Bald_InfoAction"
                    and n.findtext("param[@name='id']") == "5003")
        params = {p.get("name"): p.text for p in pill.findall("param")}
        self.assertEqual(params["helper_if"], SERVES)
        self.assertEqual(request(params["helper"]), actions.Request("play", "episode", "25"))
        self.assertEqual(runscript_action(params["onclick"]), "play")
        info = ET.parse(XML / "Includes_Bald_Info.xml").getroot().find("include[@name='Bald_InfoAction']")
        defaults = {p.get("name"): p.text for p in info.findall("param")}
        self.assertEqual((defaults["helper"], defaults["helper_if"]), ("noop", "false"))
        clicks = [(n.get("condition"), n.text) for n in info.iter("onclick")]
        self.assertEqual(clicks, [("![$PARAM[helper_if]]", "$PARAM[onclick]"),
                                  ("$PARAM[helper_if]", "$PARAM[helper]")])

    def test_rare_actions_stay_runscript(self):
        for name, _, element in sites():
            action = runscript_action(element.text)
            if action in KEPT:
                with self.subTest(file=name, action=action):
                    self.assertNotIn(SERVES, element.get("condition") or "")


if __name__ == "__main__":
    unittest.main()
