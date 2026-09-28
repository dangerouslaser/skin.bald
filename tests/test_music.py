"""The Bald music library (MyMusicNav.xml, View_550_Bald_Music.xml, Includes_Bald_Music.xml), Now Playing
(MusicVisualisation.xml) and music information: registered views, Kodi's control-id contract, the shared library
pieces used with the music window's params, the curtain, the blur follow, and strings in the music block."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import equivalent, implies
from kodi_includes import expand_call, expand_follow, expressions, resolve_window
from skin_strings import MUSIC_RANGE, strings

ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
VIEWS = ("550", "551", "552")


def ids(root):
    return {c.get("id") for c in root.iter("control") if c.get("id")}


class MusicLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nav = ET.parse(XML / "MyMusicNav.xml").getroot()
        cls.window = resolve_window("MyMusicNav.xml")
        cls.views = ET.parse(XML / "View_550_Bald_Music.xml").getroot()

    def test_bald_views_lead_the_views_list(self):
        views = self.nav.findtext("views").split(",")
        self.assertEqual(views[:3], list(VIEWS))
        # Estuary's views stay for files, sources, add-ons, playlists and music videos.
        self.assertLessEqual({"50", "52", "53", "54", "55", "500"}, set(views))
        for view in views:
            with self.subTest(view=view):
                self.assertIn(view, ids(self.window))

    def test_each_view_is_a_list_type_view_for_its_content(self):
        # All three are "list" views: Kodi's default list view for a content type is the first visible one.
        content = {"550": "$EXP[Bald_MusicCoverContent]", "551": "$EXP[Bald_MusicListContent]",
                   "552": "$EXP[Bald_MusicCoverContent]"}
        for view in VIEWS:
            with self.subTest(view=view):
                control = self.views.find(f".//control[@id='{view}']")
                viewtype = control.find("viewtype")
                self.assertEqual(viewtype.text, "list")
                self.assertIn(int(viewtype.get("label")), strings())
                self.assertEqual(control.findtext("visible"), content[view])
        bodies = expressions()
        for kind in ("artists", "albums"):
            self.assertIn(f"Container.Content({kind})", bodies["Bald_MusicCoverContent"])
        for kind in ("songs", "genres", "years", "roles"):
            self.assertIn(f"Container.Content({kind})", bodies["Bald_MusicListContent"])

    def test_library_content_always_enters_a_bald_view(self):
        loads = {n.text: n.get("condition") for n in self.nav.findall("onload") if (n.text or "").startswith("Container.SetViewMode")}
        self.assertEqual(loads["Container.SetViewMode(550)"], "$EXP[Bald_MusicCoverContent] + !$EXP[Bald_MusicViewActive]")
        self.assertIn("!$EXP[Bald_MusicCoverContent]", loads["Container.SetViewMode(551)"])

    def test_kodi_contract_ids_are_present(self):
        # CGUIWindowMusicNav / CGUIWindowMusicBase / CGUIMediaWindow: the Bald options click 3, 4, 8, 16 and 19.
        found = ids(self.window)
        self.assertLessEqual({"3", "4", "8", "16", "19", "9000", "9150", "9151", "9160"}, found)
        self.assertEqual(self.nav.findtext("menucontrol"), "9151")
        router = self.nav.find(".//control[@id='9151']")
        self.assertEqual([(n.get("condition"), n.text) for n in router.findall("onfocus")],
                         [("$EXP[Bald_MusicViewActive]", "SetFocus(9150)"), ("!$EXP[Bald_MusicViewActive]", "SetFocus(9000)")])

    def test_options_cycle_views_and_use_native_actions(self):
        holder = ET.Element("holder")
        holder.extend(expand_call("Bald_LibraryOptions", {"items": "Bald_MusicOptionItems"}))
        items = holder.findall(".//control[@id='9150']/content/item")
        cycle = {}
        for item in items:
            actions = [n.text for n in item.findall("onclick")]
            if actions[0].startswith("Container.SetViewMode("):
                self.assertEqual(actions[-1], "SetFocus(9150)")
                source = re.search(r"Control\.IsVisible\((\d+)\)", item.findtext("visible")).group(1)
                cycle[source] = re.search(r"\((\d+)\)", actions[0]).group(1)
        self.assertEqual(cycle, {"550": "551", "551": "552", "552": "550"})
        clicks = {n.text for item in items for n in item.findall("onclick")}
        self.assertLessEqual({"SendClick(3)", "SendClick(4)", "SendClick(8)", "SendClick(16)", "UpdateLibrary(music)",
                              "ActivateWindow(visualisation)", "ActivateWindow(musicplaylist)"}, clicks)
        self.assertNotIn("UpdateLibrary(video)", clicks)
        # 551 to 552 only where the artwork list serves the content.
        to_artwork = next(i for i in items if (i.findtext("onclick") or "") == "Container.SetViewMode(552)")
        self.assertTrue(implies(to_artwork.findtext("visible"), "$EXP[Bald_MusicCoverContent]"))

    def test_letters_read_the_music_window(self):
        call = self.nav.find(".//include[@content='Bald_LibraryLetters']")
        params = {p.get("name"): p.text for p in call.findall("param")}
        self.assertEqual(params["window"], "music")
        self.assertEqual(params["sorted"], "$EXP[Bald_MusicLettersSorted]")
        holder = ET.Element("holder")
        holder.extend(expand_call("Bald_LibraryLetters", params))
        text = ET.tostring(holder, encoding="unicode")
        self.assertIn("Window(music).Property(Bald.AvailableLetters)", text)
        self.assertNotIn("Window(videos)", text)
        for view in VIEWS:
            control = self.views.find(f".//control[@id='{view}']")
            self.assertIn(f"RunScript(skin.bald,letters,{view})", [n.text for n in control.findall("ondown")])

    def test_views_follow_their_container_for_the_blur(self):
        for view in VIEWS:
            with self.subTest(view=view):
                control = next(c for c in self.window.iter("control") if c.get("id") == view)
                actions = [(n.tag, n.text) for n in control]
                self.assertIn(("onfocus", f"SetProperty(Bald.FocusContainer,{view},music)"), actions)
                self.assertIn(("onfocus", f"SetProperty(Bald.LibraryContainer,{view},music)"), actions)
                self.assertIn(("onunfocus", "ClearProperty(Bald.FocusContainer,music)"), actions)
        loads = {(n.tag, n.text) for n in expand_follow(self.nav)}
        for tag in ("onload", "onunload"):
            self.assertIn((tag, "ClearProperty(Bald.FocusContainer,music)"), loads)

    def test_music_background_never_falls_back_to_the_last_blur(self):
        blur = ET.parse(XML / "Includes_Bald_Music.xml").getroot().find("variable[@name='Bald_MusicBlur']")
        text = ET.tostring(blur, encoding="unicode")
        self.assertIn("Bald.Blur)", text)
        self.assertNotIn("Bald.Blur.Last", text)
        self.assertNotIn("LastBlur", text)

    def test_curtain_and_window_motion(self):
        common = ET.parse(XML / "Includes_Bald_Common.xml").getroot()
        self.assertIn("Window.IsActive(music)", common.findtext("expression[@name='Bald_CurtainWindow']"))
        self.assertIn("Window.Next(music)", common.findtext("expression[@name='Bald_CurtainNext']"))
        self.assertIn("Bald_CurtainHandoff", [n.text for n in self.nav.findall("include")])
        depth = self.nav.find(".//include[@content='Bald_AnimWindowDepth']")
        params = {p.get("name"): p.text for p in depth.findall("param")}
        self.assertEqual(params, {"back_in": "!Window.Previous(home)", "back_out": "Window.Next(home)"})

    def test_tmdb_blur_only_without_the_helper(self):
        loads = [(n.get("condition"), n.text) for n in self.nav.findall("onload")]
        self.assertIn(("$EXP[Bald_HasTMDbHelper] + !$EXP[Bald_HasHelper] + !Skin.HasSetting(TMDbHelper.EnableBlur)", "Skin.SetBool(TMDbHelper.EnableBlur)"), loads)
        self.assertIn(("$EXP[Bald_HasHelper] + Skin.HasSetting(TMDbHelper.EnableBlur)", "Skin.Reset(TMDbHelper.EnableBlur)"), loads)


class NowPlayingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = ET.parse(XML / "MusicVisualisation.xml").getroot()
        cls.window = resolve_window("MusicVisualisation.xml")

    def test_kodi_binds_the_visualisation(self):
        vis = next(c for c in self.window.iter("control") if c.get("id") == "2")
        self.assertEqual(vis.get("type"), "visualisation")

    def test_the_blur_follows_the_playing_item(self):
        loads = [(n.tag, n.text) for n in expand_follow(self.raw)]
        self.assertIn(("onload", "SetProperty(Bald.FocusContainer,5500,visualisation)"), loads)
        self.assertIn(("onunload", "ClearProperty(Bald.FocusContainer,visualisation)"), loads)
        follow = next(c for c in self.window.iter("control") if c.get("id") == "5500")
        self.assertEqual(follow.get("type"), "list")
        # Off screen but not hidden: Kodi updates a static item's $INFO only while its container is visible.
        self.assertIsNone(follow.find("visible"))
        # Disabled: it must never take the window's keys.
        self.assertEqual(follow.findtext("enable"), "false")
        self.assertEqual(follow.findtext("content/item/thumb"), "$VAR[Bald_NowPlayingBlurSource]")

    def test_shows_what_the_brief_asks_for(self):
        text = ET.tostring(self.window, encoding="unicode")
        for info in ("MusicPlayer.Cover", "Player.Title", "MusicPlayer.Artist", "Bald_NowPlayingAlbum", "Player.Progress",
                     "MusicPlayer.Time", "MusicPlayer.TimeRemaining", "MusicPlayer.offset(1).Title", "MusicPlayer.Codec",
                     "MusicPlayer.BitRate", "MusicPlayer.SampleRate"):
            self.assertIn(info, text)

    def test_the_bar_gives_way_to_the_seek_layer(self):
        progress = next(c for c in self.window.iter("control") if c.get("type") == "progress")
        holder = next(g for g in self.window.iter("control") if progress in list(g))
        self.assertEqual(holder.findtext("visible"), "!$EXP[Bald_NowPlayingSeekLayer]")
        self.assertEqual(expressions()["Bald_NowPlayingSeekLayer"], "[Window.IsVisible(seekbar)]")

    def test_visualisation_dims_under_the_full_screen_and_has_it_alone_otherwise(self):
        body = expressions()["Bald_NowPlayingFull"]
        self.assertTrue(equivalent(body, "!Visualisation.Enabled | Player.ShowInfo | Window.IsVisible(musicosd)"))
        title = ET.parse(XML / "Includes_Bald_OSD.xml").getroot().find("include[@name='Bald_OSDMusicTitle']")
        self.assertIn("!$EXP[Bald_NowPlayingFull]", title.findtext(".//visible"))

    def test_idle_drift_and_dim(self):
        idle = [a for a in self.raw.iter("animation") if a.get("condition") == "$EXP[Bald_NowPlayingIdle]"]
        self.assertTrue(any(e.get("type") == "fade" for a in idle for e in a))
        # The drift steps (Bald_IdleDrift), it never pulses: a pulsing drift redrew the whole screen every frame.
        self.assertFalse(any(a.get("pulse") == "true" for a in self.raw.iter("animation")))
        drift = [i for i in self.raw.iter("include") if i.get("content") == "Bald_IdleDrift"]
        self.assertEqual([{p.get("name"): p.text for p in i.findall("param")} for i in drift], [{"x": "12", "y": "8"}])

    def test_motion_uses_only_the_spec_curves(self):
        for path in ("MusicVisualisation.xml", "Includes_Bald_Music.xml", "View_550_Bald_Music.xml", "MyMusicNav.xml"):
            root = ET.parse(XML / path).getroot()
            for node in list(root.iter("effect")) + list(root.iter("animation")):
                kind = node.get("type") if node.tag == "effect" else node.get("effect")
                if kind is None:
                    continue
                with self.subTest(file=path, effect=kind):
                    self.assertIn(kind, ("fade", "slide", "zoom"))
                    tween = (node.get("tween"), node.get("easing"))
                    if kind == "fade" and node.get("time") not in (None, "0"):
                        self.assertEqual(tween[0], "sine")
                    if kind == "slide":
                        self.assertIn(tween, (("cubic", "out"), ("sine", "inout")))


class MusicInfoTests(unittest.TestCase):
    def test_contract_and_own_ids(self):
        window = resolve_window("DialogMusicInfo.xml")
        self.assertLessEqual({"6", "7", "8", "10", "12", "50", "13"}, ids(window))
        play_next = next(c for c in window.iter("control") if c.get("id") == "13")
        self.assertEqual(play_next.findtext("onclick"), "QueueMedia(musicdb://albums/$INFO[ListItem.DBID]/,isdir,playnext)")
        self.assertIn("String.IsEqual(ListItem.DBType,album)", play_next.findtext("visible"))

    def test_discography_is_covers(self):
        panel = ET.parse(XML / "DialogMusicInfo.xml").getroot().find(".//control[@id='50']")
        layouts = [(l.tag, l.get("condition")) for l in panel if l.tag in ("itemlayout", "focusedlayout")]
        self.assertEqual(layouts[:2], [("itemlayout", "Container.Content(albums)"), ("focusedlayout", "Container.Content(albums)")])


class MusicStringTests(unittest.TestCase):
    def test_new_music_strings_are_in_the_music_block(self):
        texts = strings()
        music_files = ("Includes_Bald_Music.xml", "View_550_Bald_Music.xml", "MyMusicNav.xml", "MusicVisualisation.xml")
        for name in music_files:
            text = (XML / name).read_text(encoding="utf-8")
            used = {int(n) for n in re.findall(r"\$LOCALIZE\[(\d+)\]", text)}
            used |= {int(n) for n in re.findall(r'<viewtype label="(\d+)"', text)}
            for num in sorted(n for n in used if 31000 <= n <= 31999):
                with self.subTest(file=name, string=num):
                    self.assertIn(num, texts)
        ours = [num for num in texts if num in MUSIC_RANGE]
        self.assertTrue(ours)
        self.assertEqual(ours, sorted(ours))


if __name__ == "__main__":
    unittest.main()
