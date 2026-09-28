"""Repo-wide conventions for the Bald-native XML: named conditions and layout constants."""
import re
import unittest
import xml.etree.ElementTree as ET

from kodi_includes import CONSTANT_TAGS, EXP, GENERATED, NATIVE, SKIN, constants, expressions


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
          ("left", "1296"): "Bald_PreviewLeft", ("top", "108"): "Bald_PageTitleTop", ("top", "222"): "Bald_ContentTop",
          ("top", "738"): "Bald_LowRailTop"}


class ConstantTests(unittest.TestCase):
    def test_bald_constants_load_at_every_screen_height(self):
        # Bald's 1080i values load at every screen height (no condition on their include).
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
                    if text.startswith("Bald_") and "$PARAM[" in text:
                        # A constant chosen by a parameter (Bald_RatingGlyph$PARAM[height]): Kodi resolves constants
                        # after the include's parameters, so the name only has to start a family of constants.
                        prefix = text.split("$PARAM[")[0]
                        self.assertTrue(any(name.startswith(prefix) for name in values), text)
                    elif text.startswith("Bald_"):
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

        # Bald_* includes that live in Estuary's include files (the TV guide's grid and tools drawer) are Bald's
        # own too; the generated Skin Variables output is per install and left out.
        sources = [(path.name, ET.parse(path).getroot()) for path in NATIVE]
        for path in sorted(set(SKIN.glob("Includes*.xml")) - set(NATIVE) - {SKIN / GENERATED}):
            sources += [(f"{path.name}:{node.get('name')}", node) for node in ET.parse(path).getroot().findall("include")
                        if (node.get("name") or "").startswith("Bald_")]
        for name, root in sources:
            ids = {node.get("id") for node in root.iter("control") if node.get("id")}
            ids |= {node.get("value", node.text) for node in root.iter("param")
                    if node.get("name") in ("id", "control_id")}
            for value in sorted(i for i in ids if i and i.isdigit()):
                with self.subTest(file=name, id=value):
                    self.assertTrue(covered(int(value)))

if __name__ == "__main__":
    unittest.main()


class FocusFadeTests(unittest.TestCase):
    """Kodi reverses a reversible Focus animation from wherever it stopped when focus leaves early, so a fading
    focus animation can leave a quickly passed label at a stray opacity (Home menu, settings lists). Every Focus
    animation that fades must be reversible="false", so an interrupted one resets instead."""

    def test_fading_focus_animations_are_not_reversible(self):
        import glob
        import xml.etree.ElementTree as ET
        from pathlib import Path
        skin = Path(__file__).resolve().parents[1] / '1080i'
        for path in sorted(skin.glob('*.xml')):
            if path.name.startswith('script-skinvariables'):
                continue
            text = path.read_text(encoding='utf-8')
            if 'Bald' not in text and 'bald' not in text:
                continue
            for anim in ET.parse(path).getroot().iter('animation'):
                if anim.get('type') != 'Focus' or anim.find("effect[@type='fade']") is None:
                    continue
                with self.subTest(file=path.name):
                    self.assertEqual(anim.get('reversible'), 'false')


class StaticItemNumberTests(unittest.TestCase):
    """Kodi reads a static list item's label or property that is a plain number as a string id (CGUIControlFactory::
    GetInfoLabelFromElement), so a property meant as the number 2 reads "Music". Bald's static item properties must
    not be bare numbers or a bare $PARAM that a caller fills with one ($NUMBER[] resolves to nothing there either)."""

    def test_static_item_properties_are_not_bare_numbers(self):
        for path in sorted(SKIN.glob('*.xml')):
            if path.name.startswith('script-skinvariables'):
                continue
            for item in ET.parse(path).getroot().iter('item'):
                for prop in item.findall('property'):
                    value = (prop.text or '').strip()
                    with self.subTest(file=path.name, property=prop.get('name')):
                        self.assertFalse(value.isdigit() or re.fullmatch(r'\$PARAM\[\w+\]', value), value)


class MapOrderTests(unittest.TestCase):
    """Kodi resolves a skin map's ref when it loads the map (CSkinMapManager::LoadMaps logs "references unknown map"
    otherwise), so a map that extends another must load after it: in a later included file, or later in the same file."""

    def test_referenced_maps_load_first(self):
        files = [node.get('file') for node in ET.parse(SKIN / 'Includes.xml').getroot().findall('include')
                 if node.get('file')]
        maps = [(node.get('name'), node.get('ref')) for name in files
                for node in ET.parse(SKIN / name).getroot().iter('map')]
        loaded = set()
        for name, ref in maps:
            if ref:
                with self.subTest(map=name):
                    self.assertIn(ref, loaded)
            loaded.add(name)


class InfoLabelNameTests(unittest.TestCase):
    """Infobools Kodi 22 does not have are silently false. ListItem.IsEpisode is one: episodes are
    String.IsEqual(ListItem.DBType,episode)."""

    def test_no_listitem_isepisode(self):
        for path in sorted(SKIN.glob('*.xml')):
            if path.name.startswith('script-skinvariables'):
                continue
            with self.subTest(file=path.name):
                self.assertNotRegex(path.read_text(encoding='utf-8'), r'ListItem\.IsEpisode\b')


class MotionCurveTests(unittest.TestCase):
    """CLAUDE.md's curves: fade = sine in-out, move (slide, and a zoom that settles back) = cubic out, pop = back out.
    The shared dialog animations in Includes_Animations.xml follow them, and so does every zoom that settles back
    when focus leaves (Unfocus), across the skin."""

    FADE = {("sine", "inout")}
    MOVE = {("cubic", "out"), ("back", "out")}

    @staticmethod
    def effects(anim):
        if anim.get("effect"):
            return [(anim.get("effect"), anim)]
        return [(effect.get("type"), effect) for effect in anim.iter("effect")]

    @staticmethod
    def curve(node):
        return node.get("tween"), node.get("easing")

    def test_shared_dialog_animations_use_the_spec_curves(self):
        root = ET.parse(SKIN / "Includes_Animations.xml").getroot()
        for anim in root.iter("animation"):
            for kind, node in self.effects(anim):
                if int(node.get("time", "0")) == 0:
                    continue
                with self.subTest(effect=kind, curve=self.curve(node)):
                    self.assertIn(kind, ("fade", "slide", "zoom"))
                    self.assertIn(self.curve(node), self.FADE if kind == "fade" else self.MOVE)

    def test_unfocus_zooms_settle_with_cubic_out(self):
        for path in sorted(SKIN.glob("*.xml")):
            if path.name.startswith("script-skinvariables"):
                continue
            for anim in ET.parse(path).getroot().iter("animation"):
                if (anim.get("type") or anim.text or "").strip().lower() != "unfocus":
                    continue
                for kind, node in self.effects(anim):
                    if kind != "zoom" or int(node.get("time", "0")) == 0:
                        continue
                    with self.subTest(file=path.name, curve=self.curve(node)):
                        self.assertEqual(self.curve(node), ("cubic", "out"))
