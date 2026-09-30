# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the LibreELEC fork: the DRM output readings, the HdrDetail parse,
and the addon.xml edits.  Run with ``python3 -m unittest discover -s tests``."""

import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path[:0] = [str(Path(__file__).resolve().parent / "stubs"), str(ROOT / "resources" / "lib"), str(ROOT / "tools")]

import xbmc  # noqa: E402  (the stub)
from core import platform  # noqa: E402
from info import dvinfo  # noqa: E402
import fork_branding  # noqa: E402


def _facts(**overrides):
    facts = {"connector_id": "609", "colorspace": "Default", "format": "RGB", "bpc": "8",
             "mode": (60.0, 2160, False), "eotf": "SDR"}
    facts.update(overrides)
    return facts


class DebugfsParsing(unittest.TestCase):
    state = (FIXTURES / "drm_state.txt").read_text()
    display_info = (FIXTURES / "i915_display_info.txt").read_text()

    def test_active_connector(self):
        output = platform._active_output(self.state)
        self.assertEqual(output["name"], "HDMI-A-2")
        self.assertEqual(output["id"], "609")
        self.assertEqual(output["crtc"], "pipe A")
        self.assertEqual(output["output_format"], "RGB")

    def test_crtc_mode(self):
        self.assertEqual(platform._crtc_mode(self.state, "pipe A"), (60.0, 2160, False))
        self.assertIsNone(platform._crtc_mode(self.state, "pipe B"))

    def test_fractional_rate(self):
        state = 'crtc[1]: pipe A\n\tmode: "3840x2160": 24 296703 3840 5116 5204 5500 2160 2168 2178 2250 0x48 0x5\n'
        refresh, lines, interlaced = platform._crtc_mode(state, "pipe A")
        self.assertAlmostEqual(refresh, 23.976, places=3)
        self.assertEqual((lines, interlaced), (2160, False))

    def test_pipe_bpp(self):
        self.assertEqual(platform._pipe_bpp(self.display_info, "pipe A"), 24)


class Readings(unittest.TestCase):
    def setUp(self):
        patches = [mock.patch.object(platform, "is_amlogic", return_value=False)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        platform._cache = None
        xbmc.LABELS.clear()

    def read(self, facts, detail=""):
        xbmc.LABELS["VideoPlayer.HdrDetail"] = detail
        with mock.patch.object(platform, "_facts", return_value=facts):
            return platform.eoft_gamut(), platform.pixformat(), platform.displaymode()

    def test_dv_tunnel(self):
        self.assertEqual(self.read(_facts(), "8.1 · CM2.9 · HDMI DV"),
                         ("DV-Std BT.709", "8-bit, RGB", "2160p60.000hz"))
        self.assertTrue(platform.is_dv_tunnel())

    def test_bridge_hdr10(self):
        facts = _facts(colorspace="BT2020_RGB", bpc="10")
        self.assertEqual(self.read(facts, "8.1 · CM2.9 · HDR10 output")[:2],
                         ("HDR10 BT.2020nc", "10-bit, RGB"))

    def test_stock_hdr10_and_hlg(self):
        self.assertEqual(self.read(_facts(eotf="HDR10", colorspace="BT2020_RGB"), "8.1")[0], "HDR10 BT.2020nc")
        self.assertEqual(self.read(_facts(eotf="HLG", colorspace="BT2020_YCC", format="YCBCR420"))[:2],
                         ("HLG BT.2020nc", "8-bit, YUV420"))

    def test_sdr(self):
        self.assertEqual(self.read(_facts()), ("SDR BT.709", "8-bit, RGB", "2160p60.000hz"))

    def test_no_debugfs_falls_back_to_kodi(self):
        xbmc.LABELS["System.ScreenResolution"] = "1920x1080 @ 23.98 Hz - Full screen"
        self.assertEqual(self.read({}), ("", "", "1080p23.98hz"))


class HdrDetail(unittest.TestCase):
    def test_parts(self):
        cases = {
            "8.1": ("8.1", "", ""),
            "8.1 · CM2.9 · HDMI DV": ("8.1", "", "CMv2.9"),
            "7.6 FEL · CM4 · HDMI DV": ("7.6", "FEL", "CMv4.0"),
            "": ("", "", ""),
        }
        for detail, expected in cases.items():
            self.assertEqual(dvinfo._detail_parts(detail), expected, detail)

    def test_build_info_without_side_data(self):
        info = dvinfo._build_info({}, "dolbyvision", "7.6 FEL · CM4 · HDMI DV")
        self.assertEqual(info["output_mode"], "Dolby Vision Profile 7.6 FEL")
        self.assertEqual(info["cm_version"], "CMv4.0")
        self.assertEqual(info["bit_depth"], "12")


class UpstreamDrift(unittest.TestCase):
    """Fails when upstream starts reading an Amlogic-only source somewhere the
    fork has not reviewed: each file below was checked for what it does off
    Amlogic (gated, rebuilt in core.platform, or harmlessly empty)."""

    PATTERN = re.compile(
        r"Player\.Process\(amlogic\.[a-z_]+\)|/sys/module/aml_media|/sys/class/amdolby"
        r"|/sys/class/video/|/sys/class/amhdmitx|video\.sidedata"
    )
    REVIEWED = {
        "resources/lib/core/helpers.py": {"/sys/class/video/"},            # fps_info: drop reads 0
        "resources/lib/core/platform.py": {"Player.Process(amlogic.eoft_gamut)",
                                           "Player.Process(amlogic.pixformat)",
                                           "Player.Process(amlogic.displaymode)",
                                           "/sys/class/amhdmitx"},
        "resources/lib/info/dvinfo.py": {"video.sidedata"},                # empty: HdrDetail fallback
        "resources/lib/info/properties.py": {"/sys/module/aml_media"},     # DV tunnel, Amlogic-gated
        "resources/lib/ui/mode_select.py": {"/sys/module/aml_media", "/sys/class/amdolby"},  # VS10, gated
    }

    def test_amlogic_sources_are_reviewed(self):
        found = {}
        for path in [ROOT / "main.py", *sorted((ROOT / "resources").rglob("*"))]:
            if path.suffix not in (".py", ".xml") or not path.is_file():
                continue
            hits = set(self.PATTERN.findall(path.read_text(encoding="utf-8", errors="ignore")))
            if hits:
                found[str(path.relative_to(ROOT))] = hits
        unreviewed = {
            name: sorted(hits - self.REVIEWED.get(name, set()))
            for name, hits in found.items()
            if hits - self.REVIEWED.get(name, set())
        }
        self.assertEqual(unreviewed, {}, "new Amlogic-only reads upstream; check them on LibreELEC")


class ForkBranding(unittest.TestCase):
    upstream = (
        '<addon id="script.tinyppi" name="TinyPPI" version="2.13.0" provider-name="jamal2362">\n'
        '    <requires>\n'
        '        <import addon="script.module.sidedata" version="1.6.0"/>\n'
        '    </requires>\n'
        '        <source>https://github.com/CE-Repo/script.tinyppi</source>\n'
        '        <summary lang="de">Deutsch.</summary>\n'
        '        <summary lang="en">Displays info.</summary>\n'
        '        <description lang="de">Deutsch.</description>\n'
        '        <description lang="en">Opens a window.</description>\n'
    )

    def test_addon_xml(self):
        text = fork_branding.addon_xml(self.upstream)
        self.assertIn('id="script.bald.processinfo"', text)
        self.assertIn('name="Bald Process Info"', text)
        self.assertIn(f'version="2.13.0.{fork_branding.FORK_REVISION}"', text)
        self.assertIn('provider-name="dangerouslaser"', text)
        self.assertIn('version="1.6.0" optional="true"/>', text)
        self.assertIn("<source>https://github.com/dangerouslaser/script.bald.processinfo</source>", text)
        self.assertNotIn('lang="de"', text)
        self.assertIn("not affiliated with or supported by TinyPPI's author", text)
        self.assertEqual(fork_branding.addon_xml(text), text)

    def test_rename_text(self):
        code = ('xbmcaddon.Addon("script.tinyppi"); "script-tinyppi-main.xml"; '
                'Window(10000).getProperty("TinyPPI.Running"); log("TinyPPI: x"); open_tinyppi()')
        self.assertEqual(
            fork_branding.rename_text(code),
            'xbmcaddon.Addon("script.bald.processinfo"); "script-baldpi-main.xml"; '
            'Window(10000).getProperty("BaldPI.Running"); log("BaldPI: x"); open_baldpi()',
        )
        self.assertEqual(fork_branding.rename_text('msgid "TinyPPI settings"', display=True),
                         'msgid "Bald Process Info settings"')
        upstream_link = "https://github.com/CE-Repo/script.tinyppi"
        self.assertEqual(fork_branding.rename_text(upstream_link), upstream_link)


class GeneratedTree(unittest.TestCase):
    """Checks on the tree as the generated branding commit leaves it."""

    def setUp(self):
        if 'id="script.bald.processinfo"' not in (ROOT / "addon.xml").read_text(encoding="utf-8"):
            self.skipTest("branding not applied (run tools/fork_branding.py)")

    def test_no_upstream_name_left(self):
        allowed = ("CE-Repo/script.tinyppi", "ce-repo.github.io", "TinyPPI's author",
                   "TinyPPI code by U3knOwn")
        ours = {Path(p) for p in ("README.md", "NOTICE", "LICENSE-ASSETS")}
        hits = []
        for path in fork_branding._files(ROOT):
            rel = path.relative_to(ROOT)
            if rel in ours or path.suffix not in fork_branding.TEXT_SUFFIXES or path.name == "LICENSE":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for token in allowed:
                text = text.replace(token, "")
            if re.search("tinyppi", text, re.IGNORECASE) or "tinyppi" in path.name.lower():
                hits.append(str(rel))
        self.assertEqual(hits, [])

    # Upstream's LICENSE-ASSETS covers these; every file in them must be ours.
    COVERED = ("icon.png", "fanart.png", "resources/skins/Default/media", "resources/web/icons")
    THIRD_PARTY = ("resources/skins/Default/media/codecs/",
                   "resources/skins/Default/media/icons/dv-logo.png",
                   "resources/skins/Default/media/icons/dv-name.png")

    def test_artwork_is_ours(self):
        foreign = []
        for covered in self.COVERED:
            base = ROOT / covered
            for path in ([base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())):
                rel = path.relative_to(ROOT).as_posix()
                if rel.startswith(self.THIRD_PARTY):
                    continue
                ours = ROOT / "branding" / rel
                if not ours.is_file() or ours.read_bytes() != path.read_bytes():
                    foreign.append(rel)
        self.assertEqual(foreign, [], "artwork not from branding/: draw it in tools/make_branding.py")


if __name__ == "__main__":
    unittest.main()
