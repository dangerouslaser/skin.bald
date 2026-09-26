"""Bald's own UI text lives in en_gb strings.po (31700-31999) and reaches the XML through $LOCALIZE."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts import info
from skin_strings import BALD_RANGE, PO, bald_strings, strings


XML = Path(__file__).resolve().parents[1] / "1080i"
# Per-install Skin Variables output and the generated shipped defaults carry user-editable row names (data).
GENERATED = {"script-skinvariables-generator-includes.xml", "Includes_Bald_HomeDefaults.xml"}
# Windows and includes Bald wrote itself; copied Estuary files are checked through the id rules only.
BALD_FILES = sorted(
    path for path in XML.glob("*.xml")
    if path.name not in GENERATED and (
        path.name.startswith(("Includes_Bald_", "View_51", "View_52", "Custom_111", "Custom_112", "script-upnext"))
        or path.name in {"Home.xml", "DialogVideoInfo.xml", "MyPVRGuide.xml", "script-globalsearch.xml",
                         "Settings.xml", "SettingsCategory.xml", "SettingsProfile.xml",
                         "SettingsSystemInfo.xml"}
    )
)
# Names that are the same in every language.
PROPER_NOUNS = ("CoreELEC", "LibreELEC", "Dolby Vision", "HDR10+", "HDR10", "HLG", "Jellyfin")
TEXT_PARAMS = re.compile(r"^(label|label2|title|first|second|third|note|hint|[a-z_]+_hint)$")
TOKEN = re.compile(r"\$(INFO|ESCINFO|VAR|ESCVAR|EXP|PARAM|LOCALIZE|ADDON|NUMBER|MAP)\[")


def skin_ids(text):
    """Skin-range string ids a file shows: $LOCALIZE[...], numeric viewtype labels and fontset labels (idloc)."""
    ids = [int(n) for n in re.findall(r"\$LOCALIZE\[(\d+)\]", text)]
    ids += [int(n) for n in re.findall(r'<viewtype label="(\d+)"', text)]
    ids += [int(n) for n in re.findall(r'<fontset id="[^"]*" idloc="(\d+)"', text)]
    return [n for n in ids if 31000 <= n <= 31999]


def literal_text(text):
    """What a label shows besides its info values: $X[...] tokens removed, but $INFO/$VAR prefix and suffix kept."""
    out, i = [], 0
    while i < len(text):
        match = TOKEN.match(text, i)
        if not match:
            out.append(text[i])
            i += 1
            continue
        depth, j = 0, match.end() - 1
        while j < len(text):
            depth += {"[": 1, "]": -1}.get(text[j], 0)
            if depth == 0:
                break
            j += 1
        if match.group(1) in ("INFO", "ESCINFO", "VAR", "ESCVAR"):
            args = re.split(r",(?![^\[]*\])", text[match.end():j])[1:]
            out.append(" ".join(literal_text(arg) for arg in args))
        i = j + 1
    shown = re.sub(r"\[/?(COLOR[^\]]*|B|I|CR|UPPERCASE|LOWERCASE|CAPITALIZE|LIGHT)\]", "", "".join(out))
    for noun in PROPER_NOUNS:
        shown = shown.replace(noun, "")
    return shown.replace("$COMMA", ",")


def shown_texts(root):
    """(where, text) for every element whose text Kodi renders as a label."""
    for node in root.iter():
        text = (node.text or "").strip()
        if node.tag == "param":
            name = node.get("name", "")
            text = (node.get("value") or text).strip()
            if not TEXT_PARAMS.match(name):
                continue
        elif node.tag == "property":
            if node.get("name") != "note":
                continue
        elif node.tag == "value":
            # Variable values also hold paths and textures; those have no spaces around words.
            if "/" in text and " " not in text:
                continue
        elif node.tag not in ("label", "label2", "altlabel", "hinttext"):
            continue
        if text:
            yield node.tag, text
    for node in root.iter("viewtype"):
        yield "viewtype@label", node.get("label", "")


class LocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.po = PO.read_text(encoding="utf-8")
        cls.strings = strings()
        cls.bald = bald_strings()
        cls.uses = {}
        for path in XML.glob("*.xml"):
            if path.name == "script-skinvariables-generator-includes.xml":
                continue
            for num in skin_ids(path.read_text(encoding="utf-8")):
                cls.uses.setdefault(num, set()).add(path.name)
        cls.script_uses = {num for num in info.STRINGS if num in BALD_RANGE}

    def test_every_skin_string_the_xml_shows_is_defined(self):
        missing = sorted(num for num in self.uses if num not in self.strings)
        self.assertEqual(missing, [], "undefined skin string ids")

    def test_bald_strings_are_used_unique_and_cite_their_sources(self):
        self.assertTrue(self.bald, "no Bald strings in en_gb")
        unused = sorted(num for num in self.bald if num not in self.uses and num not in self.script_uses)
        self.assertEqual(unused, [], "unused Bald strings")
        texts = list(self.bald.values())
        self.assertEqual(sorted({t for t in texts if texts.count(t) > 1}), [], "one id per Bald string")
        for num in self.bald:
            block = self.po.split(f'msgctxt "#{num}"')[0].rsplit("\n\n", 1)[-1]
            cited = set(re.findall(r"^#: /1080i/(\S+)$", block, re.M))
            self.assertEqual(cited, self.uses.get(num, set()), f"#{num} source comments")
            self.assertEqual("#: /scripts/info.py" in block.split("\n"), num in self.script_uses, f"#{num} script source")

    def test_script_text_matches_en_gb(self):
        for num in self.script_uses:
            self.assertEqual(info.STRINGS[num], self.bald[num], f"#{num}")

    def test_bald_block_does_not_overlap_estuary(self):
        estuary = [num for num in self.strings if 31000 <= num < BALD_RANGE.start]
        self.assertTrue(estuary)
        self.assertLess(max(estuary), BALD_RANGE.start)

    def test_bald_windows_have_no_hardcoded_english(self):
        for path in BALD_FILES:
            root = ET.parse(path).getroot()
            for where, text in shown_texts(root):
                self.assertNotRegex(literal_text(text), r"[A-Za-z]{2,}", f"{path.name} {where}: {text}")


if __name__ == "__main__":
    unittest.main()
