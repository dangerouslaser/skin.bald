"""Per-row clearlogo on the Home art frame: the row field "logo" (empty or on shows it, off hides it), the generator's
frame-logo branches, the fallback and the widget editor's Clearlogo on artwork choice."""

import importlib.util
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import implies
from kodi_includes import Skin
from skin_strings import bald_strings


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
FALLBACK = XML / "Includes_Bald_HomeDefaults.xml"
SCREENS = (("home", "Home", "homewidgets"), ("movies", "Movies", "movieswidgets"), ("tvshows", "TVShows", "tvshowswidgets"))


def load_builder():
    spec = importlib.util.spec_from_file_location("build_home_defaults", ROOT / "tools" / "build_home_defaults.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(rows_by_menu):
    builder = load_builder()
    builder.menu_items = lambda menu: rows_by_menu.get(menu, [])
    return ET.fromstring(builder.fallback_text().split("\n", 1)[1])


def row(label, **fields):
    return {"label": label, "path": f"videodb://{label}/", "target": "videos", "limit": "5", "secondary": "0", **fields}


def row_ids(root, title):
    return [node.findtext("param[@name='id']")
            for node in root.findall(f"include[@name='Bald_Generated_{title}Widgets']/definition/include")]


def art_logo_rows(root, screen):
    calls = root.findall(f"include[@name='Bald_ConfiguredArtLogos_{screen}']/definition/include[@content='Bald_ArtLogo']")
    return [call.findtext("param[@name='c']") for call in calls]


def expression_rows(root, name):
    return set(re.findall(r"Container\((\d+)\)", root.findtext(f"expression[@name='{name}']")))


def logo_values(root):
    return [(value.get("condition"), value.text) for value in root.findall("variable[@name='Bald_Logo']/value")]


class GeneratedRowLogoTests(unittest.TestCase):
    def test_every_row_shows_its_logo_by_default(self):
        # The shipped rows have no logo field, so the fallback binds the frame logo for every row.
        root = ET.parse(FALLBACK).getroot()
        for screen, title, _ in SCREENS:
            ids = row_ids(root, title)
            self.assertTrue(ids, title)
            self.assertEqual(art_logo_rows(root, screen), [i for i in ids for _ in ("Odd", "Even")], screen)
            self.assertEqual(expression_rows(root, f"Bald_HasLogo_{screen}"), set(ids), screen)
            self.assertEqual(expression_rows(root, f"Bald_PreviewHasLogo_{screen}"), set(ids), screen)
            for i in ids:
                self.assertTrue(any(text and f"Container({i}).ListItem.Art(clearlogo)" in text for _, text in logo_values(root)), i)

    def test_a_row_with_logo_off_has_no_frame_logo_branches(self):
        rows = [row("a"), row("b", logo="off"), row("c", logo="on"), row("d", logo="")]
        root = build({"homewidgets": rows, "movieswidgets": [row("m", logo="off")]})
        home = row_ids(root, "Home")
        self.assertEqual(len(home), 4)
        off, shown = home[1], {home[0], home[2], home[3]}
        self.assertEqual(set(art_logo_rows(root, "home")), shown)
        self.assertEqual(expression_rows(root, "Bald_HasLogo_home"), shown)
        self.assertEqual(expression_rows(root, "Bald_PreviewHasLogo_home"), shown)
        # A screen whose only row is off has no logo at all, and its expressions stay [false].
        self.assertEqual(art_logo_rows(root, "movies"), [])
        self.assertEqual(root.findtext("expression[@name='Bald_HasLogo_movies']"), "[false]")
        self.assertEqual(root.findtext("expression[@name='Bald_PreviewHasLogo_movies']"), "[false]")
        # Bald_Logo (the dialog-over logo): the off row, current or previewed, resolves to an empty value.
        values = logo_values(root)
        for condition in (f"String.IsEqual(Window(home).Property(Bald.Row),{off})",
                          f"$EXP[Bald_PreviewHome] + String.IsEqual(Window(home).Property(Bald.Row.home),{off})"):
            mine = [(c, text) for c, text in values if c and f",{off})" in c and implies(c, condition) and implies(condition, c)]
            self.assertEqual(mine, [(condition, None)], condition)
        self.assertFalse(any(text and f"Container({off})" in text for _, text in values))
        # Fanart and everything else about the row are unaffected.
        fanart = [value.text for value in root.findall("variable[@name='Bald_Fanart']/value")]
        self.assertTrue(any(text and f"Container({off}).ListItem.Art(fanart)" in text for text in fanart))
        captions = root.findall("include[@name='Bald_ConfiguredCaptions_home']/definition/include")
        self.assertIn(off, [call.findtext("param[@name='c']") for call in captions])


class FrameLogoWiringTests(unittest.TestCase):
    def test_the_frame_logo_scrim_and_dialog_logo_use_the_generated_names(self):
        home = Skin().window("Home.xml")
        raw = ET.parse(XML / "Home.xml").getroot()
        self.assertIn("Bald_ConfiguredArtLogos", [node.text for node in raw.iter("include")])
        images = [node for node in home.iter("control") if node.get("type") == "image"]
        scrims = [node for node in images if node.findtext("texture") == "bald/scrim_logo.png" and node.findtext("visible")]
        self.assertTrue(any(implies(node.findtext("visible"), "$EXP[Bald_EffectiveHasLogo]") for node in scrims))
        # The global setting still hides every frame logo, the dialog-over one included.
        dialog = [node for node in images if node.findtext("texture") == "$VAR[Bald_Logo]"]
        self.assertEqual(len(dialog), 1)
        self.assertTrue(implies(dialog[0].findtext("visible"), "$EXP[Bald_ShowClearlogo]"))


class EditorLogoTests(unittest.TestCase):
    def test_the_widget_editor_has_a_clearlogo_choice_after_style(self):
        root = ET.parse(XML / "Custom_1116_BaldHomeWidgets.xml").getroot()
        ids = [node.get("id") for node in root.findall(".//control[@id='9200']/control")]
        self.assertEqual(ids.index("9209"), ids.index("9208") + 1)
        button = root.find(".//control[@id='9209']")
        self.assertEqual(button.findtext("label"), "$LOCALIZE[31768]")
        self.assertEqual(button.findtext("label2"), "$VAR[Bald_WidgetLogoLabel]")
        match = re.fullmatch(r"RunPlugin\(\$INFO\[Container\(9100\)\.ListItem\.Property\(url\)\]&func=do_edit"
                             r"&&logo&&(?P<pairs>[^,]+?)&&(?P<heading>[^&]+)&&True\)", button.findtext("onclick"))
        self.assertIsNotNone(match, button.findtext("onclick"))
        pairs = [pair.split("=") for pair in match.group("pairs").split("&")]
        self.assertEqual([value for _, value in pairs], ["on", "off"])
        names = bald_strings()
        for label in [label for label, _ in pairs] + [match.group("heading")]:
            number = int(re.fullmatch(r"\$LOCALIZE\[(\d+)\]", label).group(1))
            self.assertNotRegex(names[number], r"[&=,+]")
        # Worded apart from the tile logo style ("Fanart with logo").
        self.assertEqual(names[31768], "Clearlogo on artwork")
        values = [(value.get("condition"), value.text) for value in ET.parse(XML / "Includes_Bald_Configure.xml")
                  .getroot().findall("variable[@name='Bald_WidgetLogoLabel']/value")]
        labels = dict((value, label) for label, value in pairs)
        self.assertEqual(values, [("String.IsEqual(Container(9100).ListItem.Property(logo),off)", labels["off"]),
                                  (None, labels["on"])])


if __name__ == "__main__":
    unittest.main()
