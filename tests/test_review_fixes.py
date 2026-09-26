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


if __name__ == "__main__":
    unittest.main()
