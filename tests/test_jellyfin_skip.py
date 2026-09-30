"""Jellyfin's skip intro / credits prompt (script-jellyfin-skip.xml, for plugin.video.jellyfin's dialogs/skip.py).

The add-on binds 3012 (Skip) and 3013 (Close) by number and writes the skip text into the skip_label window property;
Bald draws them as its pills bottom-right on the safe margin."""

import unittest

from kodi_includes import resolve_window


class JellyfinSkipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.window = resolve_window("script-jellyfin-skip.xml")

    def button(self, control_id):
        return self.window.find(f".//control[@id='{control_id}']")

    def test_the_add_ons_contract(self):
        self.assertEqual(self.window.findtext("defaultcontrol"), "3012")
        self.assertEqual(self.button("3012").findtext("label"), "$INFO[Window.Property(skip_label)]")
        self.assertEqual(self.button("3013").findtext("label"), "$LOCALIZE[15067]")
        for control_id in ("3012", "3013"):
            self.assertEqual(self.button(control_id).get("type"), "button")

    def test_bald_pills_on_the_safe_margin(self):
        row = next(node for node in self.window.iter("control") if node.get("type") == "grouplist")
        self.assertEqual(int(row.findtext("left")) + int(row.findtext("width")), 1824)
        self.assertEqual(int(row.findtext("top")) + int(row.findtext("height")), 1080 - 96)
        self.assertEqual(row.findtext("align"), "right")
        for control_id in ("3012", "3013"):
            button = self.button(control_id)
            self.assertEqual(button.find("texturefocus").text, "bald/pill.png")
            self.assertEqual(button.find("texturefocus").get("colordiffuse"), "bald_ink")
            self.assertEqual(button.find("texturenofocus").get("colordiffuse"), "bald_field60")
            self.assertEqual(button.findtext("font"), "Bald_Section")

    def test_it_clears_the_osd_as_up_next_does(self):
        loads = [node.text for node in self.window.findall("onload")]
        self.assertIn("Dialog.Close(fullscreeninfo,true)", loads)
        self.assertIn("Dialog.Close(videoosd,true)", loads)


if __name__ == "__main__":
    unittest.main()
