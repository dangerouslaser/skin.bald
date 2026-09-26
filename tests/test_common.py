"""Shared components (Includes_Bald_Common.xml): each is defined once and every caller resolves it."""

import re
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


class ArtworkFallbackTest(unittest.TestCase):
    """Each ListItem.* fallback chain is defined once; per-container copies differ only by their container."""

    @classmethod
    def setUpClass(cls):
        cls.variables = {}
        for path in sorted(SKIN.glob("*.xml")):
            root = ET.parse(path).getroot()
            if root.tag == "includes":
                for node in root.findall("variable"):
                    cls.variables.setdefault(node.get("name"), []).append((path.name, node))

    def chain(self, name):
        (_, node), = self.variables[name]
        return [(value.get("condition"), value.text) for value in node.findall("value")]

    def test_shared_chains_live_in_common_and_are_defined_once(self):
        for name in ("Bald_ItemFanart", "Bald_ItemLogo", "Bald_EpisodeThumb"):
            self.assertEqual([f for f, _ in self.variables[name]], ["Includes_Bald_Common.xml"])
        self.assertEqual([v for _, v in self.chain("Bald_ItemFanart")],
                         ["$INFO[ListItem.Art(fanart)]", "$INFO[ListItem.Art(tvshow.fanart)]", "$INFO[ListItem.Art(thumb)]"])
        self.assertEqual([v for _, v in self.chain("Bald_ItemLogo")],
                         ["$INFO[ListItem.Art(clearlogo)]", "$INFO[ListItem.Art(tvshow.clearlogo)]"])

    def test_no_other_variable_repeats_a_shared_chain(self):
        shared = {name: self.chain(name) for name in ("Bald_ItemFanart", "Bald_ItemLogo", "Bald_EpisodeThumb")}
        for name, defs in self.variables.items():
            if name in shared:
                continue
            for _, node in defs:
                chain = [(value.get("condition"), value.text) for value in node.findall("value")]
                self.assertNotIn(chain, shared.values(), name)

    def test_container_variants_match_the_listitem_chain(self):
        fanart = self.chain("Bald_ItemFanart")
        self.assertEqual(self.chain("Bald_ItemFanart5100"),
                         [(c and c.replace("ListItem.", "Container(5100).ListItem."), v.replace("ListItem.", "Container(5100).ListItem."))
                          for c, v in fanart])
        for container in (540, 541, 542):
            values = [v for _, v in self.chain(f"Bald_EpisodeThumb{container}")]
            self.assertEqual(values, [f"$INFO[Container({container}).ListItem.Art(thumb)]",
                                      f"$INFO[Container({container}).ListItem.Art(fanart)]",
                                      "$INFO[Container.Art(tvshow.fanart)]"])

    def test_every_art_reference_resolves(self):
        pattern = re.compile(r"\$VAR\[(Bald_(?:ItemFanart|ItemLogo|EpisodeThumb)(?:\w|\$PARAM\[c\])*)\]")
        for path in sorted(SKIN.glob("*.xml")):
            for name in pattern.findall(path.read_text()):
                name = name.replace("$PARAM[c]", "541")
                self.assertIn(name, self.variables, (path.name, name))


if __name__ == "__main__":
    unittest.main()
