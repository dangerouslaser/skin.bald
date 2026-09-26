"""Shared components (Includes_Bald_Common.xml): each is defined once and every caller resolves it."""

import unittest
import xml.etree.ElementTree as ET

from kodi_includes import SKIN, _expand_in_place, include_definitions


FLAG_LABELS = ["4K", "1080p", "Dolby Vision", "HDR10", "HDR10+", "HLG", "codec", "7.1", "5.1"]


def expand(call_xml, definitions):
    holder = ET.fromstring(f"<holder>{call_xml}</holder>")
    _expand_in_place(holder, definitions)
    return holder


class MediaFlagsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definitions = include_definitions()

    def flags(self, container="", **params):
        extra = "".join(f'<param name="{k}">{v}</param>' for k, v in params.items())
        call = f'<include content="Bald_MediaFlags"><param name="container">{container}</param>{extra}</include>'
        return expand(call, self.definitions)

    def test_common_file_is_registered(self):
        files = [n.get("file") for n in ET.parse(SKIN / "Includes.xml").getroot().findall("include")]
        self.assertIn("Includes_Bald_Common.xml", files)

    def test_flag_row_reads_the_given_item(self):
        for container, prefix in (("", "ListItem."), ("Container(511).", "Container(511).ListItem.")):
            holder = self.flags(container)
            chips = holder.findall("control[@type='button']")
            self.assertEqual(len(chips), len(FLAG_LABELS))
            self.assertEqual(holder.findtext("visible"), "!Skin.HasSetting(Bald.HideMediaFlags)")
            for chip in chips:
                condition = chip.findtext("visible")
                self.assertIn(prefix, condition)
                if not container:
                    self.assertNotIn("Container(", condition)
            codec = next(c for c in chips if "$MAP[" in c.findtext("label"))
            self.assertEqual(codec.findtext("label"), f"$MAP[DefaultCodecMap, {prefix}AudioCodec]")
            self.assertEqual(codec.findtext("visible"), f"!String.IsEmpty({prefix}AudioCodec)")

    def test_chip_defaults_are_the_caption_chip_and_info_overrides(self):
        caption = self.flags("Container(514).").findall("control[@type='button']")
        self.assertEqual({(c.findtext("height"), c.findtext("font")) for c in caption}, {("26", "Bald_Flag")})
        info = self.flags(height="30", font="Bald_FlagL").findall("control[@type='button']")
        self.assertEqual({(c.findtext("height"), c.findtext("font")) for c in info}, {("30", "Bald_FlagL")})
        chip = caption[0]
        self.assertEqual(chip.findtext("enable"), "false")
        self.assertEqual(chip.find("texturenofocus").get("colordiffuse"), "bald_ink50")

    def test_every_flag_row_uses_the_shared_include(self):
        callers = {}
        for path in sorted(SKIN.glob("*.xml")):
            root = ET.parse(path).getroot()
            for node in root.iter("include"):
                if node.get("content") == "Bald_MediaFlags":
                    callers.setdefault(path.name, []).append(node)
            # No other file builds its own chips.
            if path.name != "Includes_Bald_Common.xml":
                for texture in root.iter("texturenofocus"):
                    self.assertNotEqual(texture.text, "bald/chip.png", path.name)
        for name in ("Includes_Bald_Home.xml", "Includes_Bald_InfoPages.xml", "Includes_Bald_InfoTV.xml",
                     "View_511_Bald_Wall.xml", "View_514_Bald_ArtworkList.xml", "View_520_Bald_TV.xml",
                     "View_521_Bald_TV_Alternates.xml"):
            self.assertIn(name, callers)
        for name, nodes in callers.items():
            for node in nodes:
                container = node.findtext("param[@name='container']") or ""
                self.assertTrue(container == "" or (container.startswith("Container(") and container.endswith(").")),
                                (name, container))
                expand(ET.tostring(node, encoding="unicode"), self.definitions)  # resolves

    def test_info_overview_flags_read_the_dialog_item_at_info_size(self):
        pages = ET.parse(SKIN / "Includes_Bald_InfoPages.xml").getroot()
        call = pages.find("include[@name='Bald_InfoOverview']//include[@content='Bald_MediaFlags']")
        p = {n.get("name"): n.text or "" for n in call.findall("param")}
        self.assertEqual(p.get("container", ""), "")
        self.assertEqual((p["height"], p["font"]), ("30", "Bald_FlagL"))


if __name__ == "__main__":
    unittest.main()
