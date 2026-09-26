import re
import unittest
import xml.etree.ElementTree as ET

from conditions import all_of, atoms, implies, same_actions
from kodi_includes import SKIN, Skin, include_definitions, resolve_window
from skin_strings import LOCALIZE, english, loc

ROOT = SKIN.parent

WINDOWS = {
    "Custom_1115_BaldSettings.xml": ("9000", ["9001"]),
    "SkinSettings.xml": ("9000", ["9001"]),
    "Custom_1116_BaldHomeWidgets.xml": ("9100", ["9200", "9201", "9202", "9203", "9204", "9205", "9206", "9207", "9208", "9209"]),
    "Custom_1117_BaldHomeScreens.xml": ("9300", ["9400", "9401", "9402"]),
    "Custom_1118_BaldAppearance.xml": ("9500", ["9600", "9601", "9602", "9603", "9604", "9605", "9606", "9607", "9611", "9612", "9613", "9614", "9615", "9621", "9622", "9623", "9624", "9625"]),
    "Custom_1119_BaldPlayback.xml": ("9700", ["9800", "9801", "9802", "9803", "9811", "9812", "9821", "9822", "9831",
                                              "9832", "9833", "9834", "9835"]),
}

# Estuary settings folded into a Bald setting, the Bald setting, and windows that must read it through it.
FOLDED_ESTUARY_SETTINGS = {
    "hide_mediaflags": ("Bald.HideMediaFlags", ("AddonBrowser.xml", "MyMusicNav.xml")),
    "no_fanart": ("Bald.HideBrowseFanart", ("FileManager.xml", "MyVideoNav.xml")),
    "show_musicvideoposter": ("Bald.MusicVideoPosters", ("MyMusicNav.xml", "MyVideoNav.xml")),
    "MovieGenreFanart": ("Bald.GenreFanart", ("MyVideoNav.xml",)),
    "WeatherFanart": ("Bald.WeatherFanart", ("MyWeather.xml",)),
    "WeatherOutlookIcon": ("Bald.WeatherIcons", ("MyWeather.xml",)),
    "OriginalTitleFormat": ("Bald.OriginalTitle", ("AddonBrowser.xml", "MyVideoNav.xml")),
    "show_profilename": ("Bald.HeaderProfile", ("AddonBrowser.xml", "MyPics.xml")),
    "show_weatherinfo": ("Bald.HeaderWeather", ("AddonBrowser.xml", "MyPics.xml")),
    "autoscroll": ("Bald.ScrollPlots", ("AddonBrowser.xml", "MyGames.xml", "MyVideoNav.xml")),
}
# Folded settings Startup.xml carries over (hide_mediaflags is only cleared: Bald's switch also governs Home).
MIGRATED_ESTUARY_SETTINGS = [old for old in FOLDED_ESTUARY_SETTINGS if old != "hide_mediaflags"]
# Estuary settings retired with Appearance's "Estuary windows" category (docs/NOTES.md), which nothing may read.
RETIRED_ESTUARY_SETTINGS = ("touchmode", "no_slide_animations", "background_overlay", "HomeFanart", "hide_mediaflags",
                            "show_profileavatar", "show_none")
DEAD_ESTUARY_SETTINGS = (
    "HomeMenuNo",
    "home_no_addons_categories_widget",
    "movieset_onclick_",
    "tvshow_onclick_",
    "album_onclick_",
    "settingsdialog_content",
    # The rating circle: its only include (RatingCircle) lost every caller when the library views and music info
    # became Bald, so the setting and the include were removed.
    "circle_userrating",
    "circle_rating",
    "circle_none",
    # Estuary's video OSD auto-close: Bald Settings, Playback (Bald.OSD.AutoClose) replaces it; Startup.xml migrates it.
    "OSDAutoClose",
    # Touch mode: Bald is remote-only (Startup.xml turns mouse input off), so the touch buttons and the footer it hid
    # were retired with it.
    "touchmode",
    # Slide animations: only four Estuary-structured windows read it (games, pictures, music and the playlist editor
    # side panels) and Bald's own windows never did; those windows keep the slide.
    "no_slide_animations",
    # Estuary's background pattern: Bald's pages sit on the plain field (SPEC 5.19), and opening Appearance used to
    # switch pattern 1 on. The pattern textures went with it.
    "background_overlay",
    # The skin fanart pack: Bald's Home never read it; its last reader was the weather page's fallback image.
    "HomeFanart",
    # Estuary's media flags switch duplicated Appearance > Information > Media flags (Bald.HideMediaFlags), which the
    # browse preview and the music window's flags now read.
    "hide_mediaflags",
)


REFERENCE = re.compile(r"\$(VAR|EXP)\[([^\],]+)")


def window_reach(name, definitions=None, skin=None):
    """All markup a window can reach: the window as Kodi resolves it (params substituted, so includes named through a
    param count), every include it calls with the call conditions the resolver drops (each definition once), and the
    variables and expressions any of that names."""
    definitions = definitions if definitions is not None else include_definitions()
    skin = skin if skin is not None else Skin()
    parts, seen, todo = [], set(), [ET.parse(SKIN / name).getroot(), skin.window(name)]
    while todo:
        node = todo.pop()
        parts.append(ET.tostring(node, encoding="unicode"))
        for call in node.iter("include"):
            include = call.get("content") or (call.text or "").strip()
            if include in definitions and include not in seen:
                seen.add(include)
                todo.append(definitions[include])
    text, names = "\n".join(parts), set()
    pending = [text]
    while pending:
        for kind, ref in REFERENCE.findall(pending.pop()):
            if (kind, ref) in names:
                continue
            names.add((kind, ref))
            if kind == "VAR" and ref in skin.variables:
                body = ET.tostring(skin.variables[ref], encoding="unicode")
            else:
                body = skin.expressions.get(ref, "")
            parts.append(body)
            pending.append(body)
    return "\n".join(parts)


def tokens(path, tag):
    return {node.findtext("name") if tag == "font" else node.get("name")
            for node in ET.parse(path).getroot().iter(tag)}


class SettingsScaffoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        definitions = include_definitions()
        cls.windows = {name: resolve_window(name, definitions) for name in WINDOWS}
        cls.fonts = tokens(SKIN / "Font.xml", "font")
        cls.colors = tokens(ROOT / "colors" / "defaults.xml", "color")

    def control(self, window, control_id):
        return self.windows[window].find(f".//control[@id='{control_id}']")

    def test_every_settings_window_keeps_its_control_ids(self):
        for name, (categories, others) in WINDOWS.items():
            for control_id in [categories, *others]:
                self.assertIsNotNone(self.control(name, control_id), f"{name} lost control {control_id}")

    def test_every_settings_window_draws_the_same_frame(self):
        for name in WINDOWS:
            controls = self.windows[name].find("controls")
            images = controls.findall("control[@type='image']")
            textures = [image.findtext("texture") for image in images]
            self.assertIn("bald/white.png", textures[0], name)
            self.assertIn("TMDbHelper.ListItem.BlurImage", textures[1], f"{name} has no Bald backdrop")
            self.assertEqual(images[2].findtext("width"), "590", name)
            title = controls.find("control[@type='label']")
            self.assertEqual((title.findtext("left"), title.findtext("top")), ("96", "96"), name)

    def test_category_lists_share_one_layout(self):
        layouts = set()
        for name, (categories, _) in WINDOWS.items():
            category_list = self.control(name, categories)
            self.assertEqual(category_list.get("type"), "list", name)
            focused = category_list.find("focusedlayout")
            dot = focused.find(".//control[@type='image']/texture")
            self.assertEqual((dot.text, dot.get("colordiffuse")), ("bald/dot.png", "bald_accent"), name)
            unfocused = category_list.find("itemlayout/control[@type='label']")
            self.assertEqual(unfocused.findtext("textcolor"), "bald_ink34", name)
            layout = ET.tostring(category_list.find("itemlayout")) + ET.tostring(focused)
            layouts.add(re.sub(rb"Bald_\w+|HasFocus\(\d+\)", b"", layout))
            expected = "Bald_InfoTagline" if name.startswith("Custom_1116") else "Bald_MenuItem"
            self.assertEqual(unfocused.findtext("font"), expected, name)
        self.assertEqual(len(layouts), 1, "category list layouts differ between settings windows")

    def test_settings_windows_use_only_bald_fonts_and_colors(self):
        for name, root in self.windows.items():
            for node in root.iter("font"):
                self.assertTrue(node.text.startswith("Bald_"), f"{name}: {node.text}")
                self.assertIn(node.text, self.fonts, name)
            for tag in ("textcolor", "focusedcolor", "disabledcolor", "colordiffuse"):
                for node in root.iter(tag):
                    self.assertIn(node.text, self.colors, f"{name}: {tag} {node.text}")
            for node in root.iter():
                if "colordiffuse" in node.attrib:
                    self.assertIn(node.get("colordiffuse"), self.colors, f"{name}: {node.get('colordiffuse')}")

    def test_footer_hints_are_sentence_case_on_the_info_hint_line(self):
        for name, root in self.windows.items():
            hints = [group for group in root.iter("control")
                     if group.get("type") == "group" and group.findtext("top") == "954"]
            self.assertEqual(len(hints), 1, name)
            self.assertEqual(int(hints[0].findtext("left")) + int(hints[0].find("control").findtext("width")), 1824)
            for label in hints[0].iter("label"):
                words = LOCALIZE.sub("", english(label.text))  # Bald strings as en_gb text; core ids carry no case
                self.assertFalse(words.isupper(), f"{name}: {label.text}")
            for label in root.iter("label"):
                self.assertNotIn("  •  ", label.text or "", name)

    def test_configure_skin_opens_the_bald_settings_page_itself(self):
        bald, skin = (self.windows[name].find("controls") for name in ("Custom_1115_BaldSettings.xml", "SkinSettings.xml"))
        self.assertEqual(ET.tostring(bald), ET.tostring(skin))
        self.assertIsNone(self.windows["SkinSettings.xml"].find(".//onload"))
        actions = [node.text for node in self.windows["SkinSettings.xml"].iter("onclick")]
        self.assertFalse(any("ReplaceWindow" in action for action in actions))

    def test_appearance_rows_follow_category_ids_not_labels(self):
        root = self.windows["Custom_1118_BaldAppearance.xml"]
        ids = [item.get("id") for item in root.findall(".//control[@id='9500']/content/item")]
        self.assertEqual(ids, ["1", "2", "3", "5"])
        seen = set()
        for row in self.control("Custom_1118_BaldAppearance.xml", "9600").findall("control"):
            visible = all_of([node.text for node in row.findall("visible")])
            self.assertFalse(any("ListItem.Label" in atom for atom in atoms(visible)), row.get("id"))
            owners = [category for category in ids if implies(visible, f"Container(9500).HasFocus({category})")]
            self.assertEqual(len(owners), 1, f"row {row.get('id')} must belong to one category")
            self.assertIn(owners[0], ids)
            seen.add(owners[0])
        self.assertEqual(seen, set(ids), "every category needs rows")

    def test_appearance_has_only_bald_rows(self):
        # The "Estuary windows" category (item 4) is gone: every row is a Bald row in 9601-9699.
        for row in self.control("Custom_1118_BaldAppearance.xml", "9600").findall("control"):
            self.assertIn(int(row.get("id")), range(9601, 9700), row.get("id"))

    def test_retired_and_folded_estuary_settings_are_read_nowhere(self):
        # Only Startup.xml may name them, to carry a value over or clear it. Skin setting names are case-insensitive.
        names = RETIRED_ESTUARY_SETTINGS + tuple(FOLDED_ESTUARY_SETTINGS)
        pattern = re.compile(r"[(=](" + "|".join(map(re.escape, names)) + r")[.)&_,]", re.I)
        for path in sorted(SKIN.glob("*.xml")):
            if path.name in ("Startup.xml", "script-skinvariables-generator-includes.xml"):
                continue
            with self.subTest(file=path.name):
                self.assertIsNone(pattern.search(path.read_text()))

    def test_folded_estuary_settings_are_read_as_bald_settings(self):
        appearance = ET.tostring(self.windows["Custom_1118_BaldAppearance.xml"], encoding="unicode")
        for old, (setting, readers) in FOLDED_ESTUARY_SETTINGS.items():
            # A bool reads as (Name); an image pack's strings as (Name.path) and its picker as property=Name&.
            new_name = re.compile(r"[(=]" + re.escape(setting) + r"[.)&,]")
            old_name = re.compile(r"[(=]" + re.escape(old) + r"[.)&_]", re.I)
            self.assertRegex(appearance, new_name, f"{setting} is not offered")
            self.assertNotRegex(appearance, old_name)
            for reader in readers:
                with self.subTest(setting=setting, reader=reader):
                    text = window_reach(reader)
                    self.assertRegex(text, new_name)
                    self.assertNotRegex(text, old_name)

    def test_startup_carries_folded_settings_over_once(self):
        loads = [(node.get("condition") or "", node.text or "")
                 for node in ET.parse(SKIN / "Startup.xml").getroot().findall("onload")]
        replace = next(i for i, (_, action) in enumerate(loads) if action.startswith("ReplaceWindow("))
        for old in MIGRATED_ESTUARY_SETTINGS:
            new = FOLDED_ESTUARY_SETTINGS[old][0]
            with self.subTest(setting=old):
                copies = [i for i, (condition, action) in enumerate(loads)
                          if old in condition and new in action and "Reset" not in action]
                resets = [i for i, (condition, action) in enumerate(loads)
                          if old in condition and action.startswith(f"Skin.Reset({old}")]
                self.assertTrue(copies, f"{old} is not carried over to {new}")
                self.assertTrue(resets, f"{old} is not cleared")
                self.assertLess(max(copies), min(resets), "the old value is cleared before it is copied")
                self.assertLess(max(resets), replace)

    def test_dead_estuary_settings_are_gone(self):
        for name in ("SkinSettings.xml", "Custom_1118_BaldAppearance.xml"):
            text = ET.tostring(self.windows[name], encoding="unicode")
            for setting in DEAD_ESTUARY_SETTINGS:
                self.assertNotIn(setting, text, f"{name} still offers {setting}")


    def test_image_pack_buttons_run_install_or_enable_the_picker(self):
        picker = "script.image.resource.select"
        for control_id, setting, kind in (("9605", "Bald.GenreFanart", "moviegenrefanart"), ("9606", "Bald.WeatherFanart", "weatherfanart"),
                                          ("9607", "Bald.WeatherIcons", "weathericons")):
            with self.subTest(control=control_id):
                actions = [(node.get("condition"), node.text)
                           for node in self.control("Custom_1118_BaldAppearance.xml", control_id).findall("onclick")]
                self.assertTrue(same_actions(actions, [
                    (f"System.AddonIsEnabled({picker})", f"RunScript({picker},property={setting}&type=resource.images.{kind})"),
                    (f"System.HasAddon({picker}) + !System.AddonIsEnabled({picker})", f"EnableAddon({picker})"),
                    (f"!System.HasAddon({picker})", f"InstallAddon({picker})"),
                ]), actions)

if __name__ == "__main__":
    unittest.main()
