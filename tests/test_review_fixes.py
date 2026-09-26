"""Follow-ups from the restyle-streams review (docs/NOTES.md, "Restyle review fixes"): shared pieces the streams each
left to another, checked structurally in the resolved windows."""
import unittest
import xml.etree.ElementTree as ET

from kodi_includes import SKIN, Skin, expand_call
from test_media import DYNAMIC, colours_in, fonts, tokens


def holder(elements):
    root = ET.Element("holder")
    root.extend(elements)
    return root


class PlaylistEditorFooterTests(unittest.TestCase):
    def test_two_list_counters_are_bald_hint_labels(self):
        root = holder(expand_call("BottomBarTwoListInfo", {"left_container_id": "50", "right_container_id": "100"}))
        labels = [node for node in root.iter("control") if node.get("type") == "label"]
        self.assertEqual(len(labels), 2)
        for label in labels:
            with self.subTest(label=label.findtext("label")):
                self.assertEqual(label.findtext("font"), "Bald_Hint")
                self.assertEqual(label.findtext("textcolor"), "bald_ink60")
                self.assertEqual(label.findtext("top"), "954")
        self.assertEqual({"50", "100"}, {c for label in labels for c in ("50", "100")
                                         if f"Container({c})" in label.findtext("label")})
        self.assertFalse([n for n in root.iter() if n.tag.startswith("texture")])
        for where, value in colours_in(root):
            if not DYNAMIC.search(value):
                with self.subTest(where=where):
                    self.assertIn(value, tokens())
        for animation in root.iter("animation"):
            with self.subTest(animation=animation.text):
                self.assertEqual((animation.get("tween"), animation.get("easing")), ("sine", "inout"))

    def test_editor_footer_counts_do_not_overlap(self):
        # BottomBar's own count would sit under the left counter, so the editor passes it empty.
        root = Skin().window("MyMusicPlaylistEditor.xml")
        hint_labels = [node for node in root.iter("control") if node.get("type") == "label"
                       and node.findtext("top") == "954" and node.findtext("left") == "96"]
        shown = [node.findtext("label") for node in hint_labels if (node.findtext("label") or "").strip()]
        self.assertEqual(len(shown), 1, shown)
        self.assertIn("Container(50)", shown[0])


class TimerIconTests(unittest.TestCase):
    def test_pvr_timer_icons_are_tinted_with_bald_tokens(self):
        # Estuary's icons stay but take a Bald tint (recording in the accent, the reminder bell in ink).
        known = tokens()
        for name in ("DialogSelect.xml",):
            root = Skin().window(name)
            icons = [node for node in root.iter("texture") if "icons/pvr/timers/" in (node.text or "")]
            self.assertTrue(icons)
            for node in icons:
                with self.subTest(window=name, texture=node.text):
                    self.assertIn(node.get("colordiffuse"), known)
                    if node.text.endswith("recording.png"):
                        self.assertEqual(node.get("colordiffuse"), "bald_accent")
        for name in ("Includes.xml", "Includes_Bald_Foundations.xml"):
            root = ET.parse(SKIN / name).getroot()
            for node in root.iter("texture"):
                if "icons/pvr/timers/" in (node.text or ""):
                    with self.subTest(file=name, texture=node.text):
                        self.assertTrue(node.get("colordiffuse"))


class PopupFocusRowTests(unittest.TestCase):
    def test_unfocused_popup_list_rows_all_dim_to_half(self):
        rows = {
            "Bald_SelectFocusRow": {},
            "Bald_PVRManagerFocus": {"list_id": "20"},
        }
        for name, params in rows.items():
            root = holder(expand_call(name, params))
            ends = {node.get("end") for node in root.iter() if node.tag in ("animation", "effect")
                    and (node.get("effect") or node.get("type")) == "fade"}
            with self.subTest(include=name):
                self.assertEqual(ends, {"50"})


class PlaybackHintSeparatorTests(unittest.TestCase):
    def test_help_parts_carry_no_inline_separator(self):
        # The hint line's parts are joined by Bald_InfoHintPair's 20 px dot, so no part carries its own.
        root = ET.parse(SKIN / "Includes_Bald_Playback.xml").getroot()
        for name in ("Bald_PlaybackHelp", "Bald_PlaybackHelpDetail", "Bald_PlaybackHint"):
            variable = root.find(f"variable[@name='{name}']")
            self.assertIsNotNone(variable, name)
            for value in variable.findall("value"):
                with self.subTest(variable=name, value=value.text):
                    self.assertNotIn("·", value.text or "")

    def test_osd_hint_line_shows_the_state_as_its_own_part(self):
        # The video OSD has its own hints (Bald_OSDHints, tests/test_osd.py).
        for name in ("MusicOSD.xml",):
            root = Skin().window(name)
            labels = [node for node in root.iter("control") if node.get("type") == "label"
                      and "Bald_PlaybackHelp" in (node.findtext("label") or "")]
            with self.subTest(window=name):
                self.assertEqual([node.findtext("label") for node in labels], ["$VAR[Bald_PlaybackHelp]"])
                texts = [node.findtext("label") for node in root.iter("control") if node.get("type") == "label"]
                self.assertIn("$VAR[Bald_PlaybackHintAfterHelp]", texts)
                self.assertIn("$VAR[Bald_PlaybackHint]", texts)

    def test_player_controls_caption_uses_the_dot_separator(self):
        root = Skin().window("PlayerControls.xml")
        texts = [node.findtext("label") for node in root.iter("control") if node.get("type") == "label"]
        self.assertIn("$VAR[Bald_PlaybackHelp]", texts)
        self.assertIn("$VAR[Bald_PlaybackHelpDetail]", texts)
        self.assertIn("·", texts)


class GuideScrollbarTests(unittest.TestCase):
    def test_guide_scrollbar_sets_every_texture_itself(self):
        root = Skin().window("MyPVRGuide.xml")
        bar = next(node for node in root.iter("control") if node.get("type") == "scrollbar" and node.get("id") == "60")
        known = tokens()
        for tag in ("texturesliderbackground", "texturesliderbar", "texturesliderbarfocus", "textureslidernib",
                    "textureslidernibfocus"):
            node = bar.find(tag)
            with self.subTest(texture=tag):
                self.assertIsNotNone(node)
                self.assertEqual(node.text, "bald/white.png")
                self.assertIn(node.get("colordiffuse"), known)


class PreviewInfoListTests(unittest.TestCase):
    WINDOWS = ("AddonBrowser.xml", "MyPrograms.xml", "MyPics.xml", "MyMusicNav.xml", "MyFavourites.xml",
               "MyGames.xml", "MyVideoNav.xml")

    def test_preview_movie_set_list_does_not_repeat_an_id(self):
        # Bald_BrowsePreview is included by several views per window; its InfoList must not define 5000 each time.
        for name in self.WINDOWS:
            root = Skin().window(name)
            ids = [node.get("id") for node in root.iter("control") if node.get("id") == "5000"]
            with self.subTest(window=name):
                self.assertLessEqual(len(ids), 1)

    def test_preview_still_lists_a_movie_set(self):
        root = holder(expand_call("Bald_BrowsePreview"))
        panels = [node for node in root.iter("control") if node.get("type") == "panel"]
        self.assertEqual(len(panels), 1)
        self.assertEqual(panels[0].findtext("content"), "$VAR[InfoListPathVar]")
        self.assertFalse(panels[0].get("id"))

if __name__ == "__main__":
    unittest.main()
