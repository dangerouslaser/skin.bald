"""Browse restyle: the Estuary library views, their chrome, the side options menu and the add-on, file manager, event
log, playlist, favourites, programs and smart playlist windows keep Kodi's contracts and use only Bald tokens."""
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import equivalent
from kodi_includes import SKIN, Skin

ROOT = SKIN.parent
ESTUARY = Path("/Applications/Kodi.app/Contents/Resources/Kodi/addons/skin.estuary/xml")

WINDOWS = ("MyVideoNav.xml", "AddonBrowser.xml", "DialogAddonInfo.xml", "FileManager.xml", "EventLog.xml",
           "MyPlaylist.xml", "MyFavourites.xml", "MyPrograms.xml", "SmartPlaylistEditor.xml", "SmartPlaylistRule.xml")
VIEW_FILES = ("View_50_List.xml", "View_51_Poster.xml", "View_52_IconWall.xml", "View_53_Shift.xml",
              "View_54_InfoWall.xml", "View_55_WideList.xml", "View_500_Wall.xml", "View_501_Banner.xml",
              "View_502_FanArt.xml", "View_503_NowPlaying.xml", "View_504_MediaList.xml")
# Whole files restyled by this stream, and the includes restyled inside Includes.xml.
RESTYLED_FILES = WINDOWS[1:] + VIEW_FILES + ("Includes_MediaMenu.xml", "Includes_Bald_Browse.xml")
RESTYLED_INCLUDES = ("CommonScrollbars", "InfoList", "MediaFlag", "MediaFlags", "FileManagerPanel", "TopBar",
                     "TopBarLabels", "BreadcrumbsLabel", "ColoredBackgroundImages", "DefaultBackground", "BottomBar",
                     "ContentPanel")

# Ids Kodi's C++ binds (GUIMediaWindow, GUIWindowVideoNav, GUIWindowAddonBrowser, GUIDialogAddonInfo,
# GUIWindowFileManager, GUIWindowEventLog, GUIWindowVideoPlaylist / MusicPlaylist, GUIDialogSmartPlaylistEditor
# and Rule), plus the menu control and the view containers each window lists.
CONTRACTS = {
    "MyVideoNav.xml": {"3", "4", "8", "10", "11", "16", "19", "9000"},
    "AddonBrowser.xml": {"3", "4", "5", "7", "8", "9", "9000"},
    "DialogAddonInfo.xml": {"6", "7", "8", "9", "10", "12", "13", "14", "50"},
    "FileManager.xml": {"20", "21", "101", "102"},
    "EventLog.xml": {"4", "20", "21", "22", "50"},
    "MyPlaylist.xml": {"3", "4", "20", "21", "22", "26", "9000"},
    "MyFavourites.xml": {"3", "4", "9000"},
    "MyPrograms.xml": {"3", "4", "9000"},
    "SmartPlaylistEditor.xml": {"2", "10", "12", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25"},
    "SmartPlaylistRule.xml": {"2", "15", "16", "17", "18", "19", "20"},
}

COLOR_TAGS = {"textcolor", "focusedcolor", "disabledcolor", "selectedcolor", "shadowcolor", "invalidcolor",
              "colordiffuse"}
DYNAMIC = re.compile(r"\$(PARAM|VAR|INFO)\[")


def bald_colors():
    root = ET.parse(ROOT / "colors" / "defaults.xml").getroot()
    return {node.get("name") for node in root.findall("color") if node.get("name", "").startswith("bald_")}


def bald_fonts():
    root = ET.parse(SKIN / "Font.xml").getroot()
    return {node.findtext("name") for node in root.iter("font") if (node.findtext("name") or "").startswith("Bald_")}


def estuary_names():
    root = ET.parse(ROOT / "colors" / "defaults.xml").getroot()
    colors = {node.get("name") for node in root.findall("color") if not node.get("name", "").startswith("bald_")}
    fonts = {node.findtext("name") for node in ET.parse(SKIN / "Font.xml").getroot().iter("font")} - bald_fonts()
    return colors, fonts


def restyled_roots():
    for name in RESTYLED_FILES:
        yield name, ET.parse(SKIN / name).getroot()
    includes = ET.parse(SKIN / "Includes.xml").getroot()
    for name in RESTYLED_INCLUDES:
        node = includes.find(f"include[@name='{name}']")
        assert node is not None, name
        yield f"Includes.xml:{name}", node


def color_uses(root):
    """(where, colour) for every colour the XML names: colour tags, colordiffuse attributes and [COLOR x] markup."""
    for node in root.iter():
        if node.tag in COLOR_TAGS and node.text and node.text.strip():
            yield node.tag, node.text.strip()
        if node.get("colordiffuse"):
            yield "colordiffuse", node.get("colordiffuse")
        for attr in ("start", "end"):
            pass
        for text in (node.text or "", *node.attrib.values()):
            for color in re.findall(r"\[COLOR ([^\]]+)\]", text):
                yield "[COLOR]", color


class BrowseTokenTests(unittest.TestCase):
    def test_restyled_files_use_only_bald_colours_and_fonts(self):
        colors, fonts = bald_colors(), bald_fonts()
        for name, root in restyled_roots():
            for where, color in color_uses(root):
                if DYNAMIC.search(color):
                    continue
                with self.subTest(file=name, where=where):
                    self.assertIn(color, colors)
            for node in root.iter("font"):
                text = (node.text or "").strip()
                if text and not DYNAMIC.search(text):
                    with self.subTest(file=name, font=text):
                        self.assertIn(text, fonts)
            for param in root.iter("param"):
                if param.get("name") == "font":
                    value = param.get("value", param.text or "")
                    with self.subTest(file=name, font_param=value):
                        self.assertIn(value, fonts)

    def test_no_estuary_colour_or_font_names_remain(self):
        estuary_colors, estuary_fonts = estuary_names()
        for name, root in restyled_roots():
            used = {color for _, color in color_uses(root)} | {(n.text or "").strip() for n in root.iter("font")}
            with self.subTest(file=name):
                self.assertEqual(used & (estuary_colors | estuary_fonts), set())

    def test_restyled_windows_draw_text_in_bald_fonts(self):
        # Defaults.xml gives a label without <font> the generic Bald_InfoPlot body type; each restyled text control
        # names its own role font instead of relying on that default.
        fonts = bald_fonts()
        skin = Skin()
        for name in WINDOWS[1:]:
            root = skin.window(name)
            for control in root.iter("control"):
                if control.get("type") not in ("label", "textbox", "fadelabel"):
                    continue
                with self.subTest(window=name, label=control.findtext("label")):
                    self.assertIn(control.findtext("font"), fonts)

    def test_no_onback_previousmenu(self):
        # docs/NOTES.md: PreviousMenu behaves like Escape in Kodi 22.
        for name, root in restyled_roots():
            for node in root.iter("onback"):
                with self.subTest(file=name):
                    self.assertNotIn("previousmenu", (node.text or "").lower())


class BrowseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skin = Skin()
        cls.windows = {name: cls.skin.window(name) for name in WINDOWS}

    def ids(self, name):
        return {node.get("id") for node in self.windows[name].iter("control") if node.get("id")}

    def test_windows_keep_kodi_bound_ids(self):
        for name, contract in CONTRACTS.items():
            with self.subTest(window=name):
                self.assertLessEqual(contract, self.ids(name))

    def test_windows_resolve_without_unknown_names(self):
        for name, root in self.windows.items():
            with self.subTest(window=name):
                self.assertEqual(self.skin.unknown_references(root), [])
                self.assertNotIn("$PARAM[", ET.tostring(root, encoding="unicode"))

    def test_every_listed_view_has_its_container(self):
        for name, root in self.windows.items():
            views = root.findtext("views")
            if not views:
                continue
            ids = self.ids(name)
            for view in views.split(","):
                if name == "MyPlaylist.xml" and view == "503":
                    continue  # included only while the music playlist is active
                with self.subTest(window=name, view=view):
                    self.assertIn(view.strip(), ids)

    def test_page_controls_exist(self):
        for name, root in self.windows.items():
            ids = self.ids(name)
            for control in root.iter("control"):
                page = (control.findtext("pagecontrol") or "").strip()
                if page:
                    with self.subTest(window=name, control=control.get("id"), page=page):
                        self.assertIn(page, ids)

    def test_side_menu_keeps_media_window_buttons(self):
        # Sort by (3) and order (4) stay hidden-but-present in the menu column; the shared rows keep their actions.
        menu = ET.parse(SKIN / "Includes_MediaMenu.xml").getroot()
        common = menu.find("include[@name='MediaMenuCommon']")
        self.assertEqual({n.get("id") for n in common.iter("control")} & {"3", "4"}, {"3", "4"})
        rows = menu.find("include[@name='MediaMenuListCommon']/definition")
        actions = {n.get("id"): [a.text for a in n.findall("onclick")] for n in rows.iter("control")}
        self.assertEqual(actions["6051"], ["Container.NextViewMode"])
        self.assertEqual(actions["6053"], ["SendClick(3)"])
        self.assertEqual(actions["6052"], ["SendClick(4)"])
        self.assertIn("Filter", actions["199"])
        search = menu.find("include[@name='MediaMenuSearchButton']")
        self.assertIsNotNone(search.find("control[@id='8']"))

    def test_movies_and_tv_still_default_to_bald_views(self):
        nav = ET.parse(SKIN / "MyVideoNav.xml").getroot()
        actions = [(n.get("condition") or "", n.text) for n in nav.findall("onload")]
        for content, view in (("movies", "510"), ("tvshows", "520"), ("seasons", "530"), ("episodes", "540")):
            with self.subTest(content=content):
                self.assertTrue(any(f"Container.Content({content})" in c and a == f"Container.SetViewMode({view})"
                                    for c, a in actions))
        views = nav.findtext("views").split(",")
        self.assertEqual(views[0], "510")


@unittest.skipUnless(ESTUARY.is_dir(), "Kodi 22's bundled Estuary is not installed")
class EstuaryParityTests(unittest.TestCase):
    """The view containers match Estuary's contracts: Kodi's view switching reads their id, <viewtype> and
    <visible>, and their page controls are what Kodi scrolls."""

    @staticmethod
    def containers(path):
        root = ET.parse(path).getroot()
        found = {}
        for control in root.iter("control"):
            if control.find("viewtype") is not None:
                found[control.get("id")] = control
        return found

    def test_view_containers_match_estuary(self):
        for name in VIEW_FILES:
            ours, theirs = self.containers(SKIN / name), self.containers(ESTUARY / name)
            with self.subTest(view=name):
                self.assertEqual(set(ours), set(theirs))
            for view_id, original in theirs.items():
                control = ours[view_id]
                with self.subTest(view=name, id=view_id):
                    self.assertEqual(control.find("viewtype").get("label"), original.find("viewtype").get("label"))
                    self.assertEqual(control.findtext("viewtype"), original.findtext("viewtype"))
                    self.assertEqual(control.findtext("pagecontrol"), original.findtext("pagecontrol"))
                    ours_visible = " + ".join(f"[{v.text}]" for v in control.findall("visible")) or "true"
                    theirs_visible = " + ".join(f"[{v.text}]" for v in original.findall("visible")) or "true"
                    self.assertTrue(equivalent(ours_visible, theirs_visible), (ours_visible, theirs_visible))

    def test_window_ids_from_estuary_are_kept(self):
        # Every control id Estuary's window file names directly (or passes as an id param) is still in the window.
        skin = Skin()
        for name in WINDOWS[1:]:
            original = ET.parse(ESTUARY / name).getroot()
            wanted = {n.get("id") for n in original.iter("control") if n.get("id", "").isdigit()}
            wanted |= {p.get("value", p.text or "") for p in original.iter("param")
                       if p.get("name") in ("id", "control_id", "list_id", "header_id", "scrollbar_id")}
            wanted = {i for i in wanted if i.isdigit()}
            ids = {n.get("id") for n in skin.window(name).iter("control") if n.get("id")}
            with self.subTest(window=name):
                self.assertLessEqual(wanted, ids)


if __name__ == "__main__":
    unittest.main()
