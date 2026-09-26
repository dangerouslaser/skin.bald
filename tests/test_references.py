"""Every name a Bald-native file uses is defined, and every control a Bald-native window moves focus to exists."""
import re
import unittest
import xml.etree.ElementTree as ET

from kodi_includes import GENERATED, NATIVE, SKIN, Skin


# Bald-native windows (the NATIVE files that are windows rather than include files).
WINDOWS = sorted(path.name for path in NATIVE if ET.parse(path).getroot().tag == "window")

# Focus targets a window names without defining the control itself, and why that is right.
NATIVE_TARGETS = {
    # The next item card's forward button closes the card first (Dialog.Close(1124,true)), so SetFocus(87) lands on
    # the video OSD's seek slider underneath (Includes_Bald_OSD.xml, Bald_OSDSlot_Panel_Forward).
    "Custom_1124_OSDNextItem.xml": {"87"},
}

NAVIGATION = ("onup", "ondown", "onleft", "onright", "onback")
# Builtins whose first argument is a control id in the current window.
FOCUS_ACTION = re.compile(r"^(?:Control\.)?(?:SetFocus|Move|SendClick)\(([^,)]+)", re.I)
VAR = re.compile(r"\$(?:ESC)?VAR\[([^,\]]+)")


def defined(tag):
    """Names of every <include>, <variable> or <expression> in the include files, the shipped fallback included and
    the per-install Skin Variables output skipped, as on a fresh install."""
    names = set()
    for path in SKIN.glob("*.xml"):
        root = ET.parse(path).getroot()
        if path.name != GENERATED and root.tag == "includes":
            names |= {node.get("name") for node in root.iter(tag) if node.get("name")}
    return names


def include_calls(root):
    for node in root.iter("include"):
        if node.get("name") or node.get("file"):
            continue
        yield node.get("content") or (node.text or "").strip()


class NameResolutionTests(unittest.TestCase):
    def test_every_static_include_and_variable_in_native_files_is_defined(self):
        includes, variables = defined("include"), defined("variable")
        for path in NATIVE:
            root = ET.parse(path).getroot()
            # Names built from $PARAM[...] are checked where they resolve, by the window tests below.
            called = {name for name in include_calls(root) if name and "$" not in name}
            used = {name for name in VAR.findall(path.read_text()) if "$" not in name}
            with self.subTest(file=path.name):
                self.assertEqual(called - includes, set(), "undefined includes")
                self.assertEqual(used - variables, set(), "undefined variables")

    def test_native_windows_resolve_completely(self):
        # Expanding every include (params, nested content, dynamic names) leaves no unknown name and no $PARAM.
        self.assertTrue(WINDOWS)
        for name in WINDOWS:
            skin = Skin()
            root = skin.window(name)
            with self.subTest(window=name):
                self.assertEqual(skin.unknown_references(root), [])
                self.assertNotIn("$PARAM[", ET.tostring(root, encoding="unicode"))


class FocusTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        skin = Skin()
        cls.variables = skin.variables
        cls.windows = {name: Skin().window(name) for name in WINDOWS}

    def targets(self, text):
        """The control ids an action or a bare navigation id can move to; $VAR targets give each of their values."""
        text = text.strip()
        match = FOCUS_ACTION.match(text)
        target = match.group(1).strip() if match else text
        variable = re.fullmatch(r"\$VAR\[([^,\]]+)\]", target)
        if variable:
            values = self.variables[variable.group(1)].findall("value")
            return [value.text.strip() for value in values if (value.text or "").strip().isdigit()]
        return [target] if target.isdigit() else []

    def focus_moves(self, root):
        """(tag, action, target id) for every navigation tag and focus-moving action in a resolved window."""
        for node in root.iter():
            text = (node.text or "").strip()
            if node.tag in NAVIGATION or FOCUS_ACTION.match(text):
                for target in self.targets(text):
                    yield node.tag, text, target

    def test_every_numeric_focus_target_exists_in_its_window(self):
        checked = 0
        for name, root in self.windows.items():
            ids = {node.get("id") for node in root.iter("control") if node.get("id")}
            allowed = NATIVE_TARGETS.get(name, set())
            for tag, action, target in self.focus_moves(root):
                checked += 1
                with self.subTest(window=name, tag=tag, action=action):
                    self.assertTrue(target in ids or target in allowed, f"no control {target}")
        # Guards against passing vacuously (a resolver change that drops the actions).
        self.assertGreater(checked, 200)

    def test_the_allowlist_is_still_needed(self):
        for name, allowed in NATIVE_TARGETS.items():
            ids = {node.get("id") for node in self.windows[name].iter("control")}
            used = {target for _, _, target in self.focus_moves(self.windows[name])}
            self.assertFalse(allowed & ids, f"{name}: allowlisted ids now exist")
            self.assertLessEqual(allowed, used, f"{name}: allowlisted ids are no longer targeted")

    def test_home_targets_come_from_its_includes_and_variables(self):
        # The menu and rows are defined in includes and Back from a row reaches the menu through $VAR[Bald_RowFocus].
        ids = {node.get("id") for node in self.windows["Home.xml"].iter("control")}
        self.assertLessEqual({"9000", "9001", "9101", "9199"}, ids)
        wake = [target for tag, action, target in self.focus_moves(self.windows["Home.xml"]) if "Bald_RowFocus" in action]
        self.assertIn("9001", wake)

if __name__ == "__main__":
    unittest.main()
