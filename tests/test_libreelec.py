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
import fork_metadata  # noqa: E402


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


class ForkMetadata(unittest.TestCase):
    upstream = (
        '<addon id="script.tinyppi" name="TinyPPI" version="2.13.0" provider-name="jamal2362">\n'
        '    <requires>\n'
        '        <import addon="script.module.sidedata" version="1.6.0"/>\n'
        '    </requires>\n'
        '        <source>https://github.com/CE-Repo/script.tinyppi</source>\n'
        '        <description lang="de">Deutsch.</description>\n'
        '        <description lang="en">Opens a window.</description>\n'
    )

    def test_apply(self):
        text = fork_metadata.apply(self.upstream)
        self.assertIn(f'version="2.13.0.{fork_metadata.FORK_REVISION}"', text)
        self.assertIn('provider-name="jamal2362, dangerouslaser"', text)
        self.assertIn('version="1.6.0" optional="true"/>', text)
        self.assertIn("<source>https://github.com/dangerouslaser/script.tinyppi</source>", text)
        self.assertIn("Opens a window. This build also runs on LibreELEC", text)
        self.assertIn('<description lang="de">Deutsch.</description>', text)

    def test_idempotent(self):
        once = fork_metadata.apply(self.upstream)
        self.assertEqual(fork_metadata.apply(once), once)

    def test_real_addon_xml(self):
        fork_metadata.apply((ROOT / "addon.xml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
