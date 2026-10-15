# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fork (Bald Process Info): the LibreELEC code paths, for the unit coverage.

core.platform end to end against a simulated DRM device and debugfs, and the
branches the fork adds to code upstream tests (main, overlay, properties,
dvfields).  The scenario tests stay in tests/test_libreelec.py.
"""

import ctypes
import importlib
import os
import sys

import pytest

import xbmc
from core import display, platform
from core import vs10 as core_vs10
from core.platform import has_drm as real_has_drm
from info import dvfields, properties
from ui import overlay

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STATE = """\
crtc[80]: pipe A
\tenable=1
\tmode: "3840x2160": 60 594000 3840 4016 4104 4400 2160 2168 2178 2250 0x40 0x5
crtc[81]: pipe B
\tenable=0
connector[600]: HDMI-A-1
\tcrtc=(null)
connector[609]: HDMI-A-2
\tcrtc=pipe A
\tcolorspace=BT2020_RGB
\toutput_format=YCBCR420
\toutput_bpc=10
"""

DISPLAY_INFO = """\
[CRTC:80:pipe A]:
\tuapi: enable=yes, active=yes, mode="3840x2160": 60 594000
\thw: enable=yes, active=yes, adjusted_mode="3840x2160", bpp=36, dither=no
[CRTC:81:pipe B]:
\tuapi: enable=no
"""


@pytest.fixture
def libreelec(monkeypatch):
    """Not Amlogic: the readings come from DRM, with a fresh cache."""
    monkeypatch.setattr(platform, "_amlogic", False)
    monkeypatch.setattr(platform, "_cache", None)
    monkeypatch.setattr(platform, "_cache_until", 0.0)


# --- Platform ----------------------------------------------------------------

def test_an_unreadable_file_reads_as_empty(tmp_path):
    assert platform._read_text(str(tmp_path / "missing")) == ""
    (tmp_path / "there").write_text("text")
    assert platform._read_text(str(tmp_path / "there")) == "text"


@pytest.mark.parametrize(("has_dir", "os_release", "expected"), [
    (True, "", True),
    (False, 'NAME="CoreELEC"\n', True),
    (False, 'NAME="LibreELEC"\n', False),
])
def test_coreelec_is_told_from_its_folder_or_os_release(monkeypatch, has_dir, os_release,
                                                       expected):
    monkeypatch.setattr(platform.os.path, "isdir", lambda path: has_dir)
    monkeypatch.setattr(platform, "_read_text", lambda path: os_release)
    assert platform.is_coreelec() is expected


def test_amlogic_is_answered_once(monkeypatch):
    looked = []
    monkeypatch.setattr(platform, "_amlogic", None)
    monkeypatch.setattr(platform.os.path, "isdir", lambda path: looked.append(path) or False)
    monkeypatch.setattr(platform, "is_coreelec", lambda: False)
    assert platform.is_amlogic() is False
    assert platform.is_amlogic() is False
    assert looked == ["/sys/class/amhdmitx"]


@pytest.mark.parametrize("present", [True, False])
def test_drm_is_told_from_its_sysfs_class(monkeypatch, present):
    monkeypatch.setattr(platform.os.path, "isdir", lambda path: present and path == "/sys/class/drm")
    assert real_has_drm() is present


@pytest.mark.parametrize(("detail", "bridge"), [
    ("8.1 · CM2.9 · HDMI DV", "dv"),
    ("8.1 · CM2.9 · HDR10 output", "hdr10"),
    ("8.1", ""),
    ("", ""),
])
def test_the_dv_bridge_output_is_read_from_hdr_detail(detail, bridge):
    xbmc.INFO["VideoPlayer.HdrDetail"] = detail
    assert platform.dv_bridge_output() == bridge


# --- DRM debugfs ---------------------------------------------------------------

def test_debugfs_dirs_put_kodis_own_card_first(monkeypatch):
    links = {3: "/dev/dri/card1", 4: OSError, 5: "/dev/dri/renderD128", 6: "/dev/dri/card1"}

    def readlink(path):
        target = links[int(path.rsplit("/", 1)[1])]
        if target is OSError:
            raise OSError(path)
        return target

    monkeypatch.setattr(display, "_drm_fds", lambda: list(links))
    monkeypatch.setattr(platform.os, "readlink", readlink)
    monkeypatch.setattr(platform.os, "listdir", lambda path: ["1", "0", "128", "clients"])
    dri = platform._DEBUGFS_DRI
    assert platform._debugfs_dirs() == [f"{dri}/1", f"{dri}/0", f"{dri}/128"]


def test_debugfs_dirs_without_debugfs(monkeypatch):
    def listdir(path):
        raise OSError(path)

    monkeypatch.setattr(display, "_drm_fds", list)
    monkeypatch.setattr(platform.os, "listdir", listdir)
    assert platform._debugfs_dirs() == []


def test_the_active_connector_is_the_one_bound_to_a_crtc():
    output = platform._active_output(STATE)
    assert output is not None
    assert (output["id"], output["name"], output["crtc"]) == ("609", "HDMI-A-2", "pipe A")
    assert platform._active_output("connector[600]: HDMI-A-1\n\tcrtc=(null)\n") is None


def test_crtc_modes():
    assert platform._crtc_mode(STATE, "pipe A") == (60.0, 2160, False)
    assert platform._crtc_mode(STATE, "pipe B") is None              # no mode line
    assert platform._crtc_mode(STATE, "pipe C") is None              # no such CRTC
    interlaced = 'crtc[1]: pipe A\n\tmode: "1920x1080": 30 74250 1920 2008 2052 2200 1080 1084 1094 1125 0x40 0x15\n'
    assert platform._crtc_mode(interlaced, "pipe A") == (60.0, 1080, True)
    no_clock = 'crtc[1]: pipe A\n\tmode: "1920x1080": 30 0 1920 2008 2052 2200 1080 1084 1094 1125 0x40 0x5\n'
    assert platform._crtc_mode(no_clock, "pipe A") is None


def test_pipe_bits_per_pixel():
    assert platform._pipe_bpp(DISPLAY_INFO, "pipe A") == 36
    assert platform._pipe_bpp(DISPLAY_INFO, "pipe B") == 0           # no bpp
    assert platform._pipe_bpp(DISPLAY_INFO, "pipe C") == 0           # no such pipe


def debugfs(monkeypatch, files):
    """Serve *files* ({path: text}) as the debugfs, in that order of directories."""
    dirs = sorted({os.path.dirname(path) for path in files})
    monkeypatch.setattr(platform, "_debugfs_dirs", lambda: dirs)
    monkeypatch.setattr(platform, "_read_text", lambda path: files.get(path, ""))


def test_debugfs_facts_from_the_first_card_with_an_active_output(monkeypatch):
    debugfs(monkeypatch, {
        "/dri/0/state": "",                                         # nothing there
        "/dri/1/state": "connector[600]: HDMI-A-1\n\tcrtc=(null)\n",  # idle
        "/dri/2/state": STATE,
        "/dri/2/i915_display_info": DISPLAY_INFO,
    })
    assert platform._read_debugfs() == {
        "connector_id": "609", "colorspace": "BT2020_RGB", "format": "YCBCR420",
        "bpc": "12", "mode": (60.0, 2160, False),
    }


def test_debugfs_facts_without_a_mode_or_the_i915_file(monkeypatch):
    debugfs(monkeypatch, {"/dri/0/state": "connector[7]: DP-1\n\tcrtc=pipe Z\n"})
    assert platform._read_debugfs() == {
        "connector_id": "7", "colorspace": "", "format": "", "bpc": "0",
    }


def test_no_debugfs_no_facts(monkeypatch):
    debugfs(monkeypatch, {})
    assert platform._read_debugfs() == {}


# --- DRM connector: HDR_OUTPUT_METADATA --------------------------------------------

class FakeDrm:
    """Answer the connector-property and blob ioctls as the kernel would.

    *props* maps a property name to its value on the connector; *blob* is the
    HDR_OUTPUT_METADATA blob's bytes; *refuse* lists the call numbers (1-based)
    that fail.
    """

    def __init__(self, props, blob=b"", refuse=()):
        self.props = list(props.items())
        self.blob = blob
        self.refuse = set(refuse)
        self.calls = 0

    def ioctl(self, fd, request, payload):
        self.calls += 1
        if self.calls in self.refuse:
            return False
        if request == display._IOCTL_OBJ_GETPROPERTIES:
            if payload.props_ptr:
                ids = (ctypes.c_uint32 * payload.count_props).from_address(payload.props_ptr)
                values = (ctypes.c_uint64 * payload.count_props).from_address(
                    payload.prop_values_ptr)
                for index, (_name, value) in enumerate(self.props[:payload.count_props]):
                    ids[index], values[index] = index + 1, value
            payload.count_props = len(self.props)
        elif request == display._IOCTL_GETPROPERTY:
            payload.name = self.props[payload.prop_id - 1][0]
        elif request == platform._IOCTL_GETPROPBLOB:
            ctypes.memmove(payload.data, self.blob, min(len(self.blob), payload.length))
            payload.length = len(self.blob)
        return True


def drm(monkeypatch, fake, fds=(7,)):
    monkeypatch.setattr(display, "_drm_fds", lambda: list(fds))
    monkeypatch.setattr(display, "_ioctl", fake.ioctl)
    return fake


def hdr_blob(eotf):
    return bytes([0, 0, 0, 0, eotf, 0, 0, 0])


def test_a_connector_property_is_found_by_name(monkeypatch):
    drm(monkeypatch, FakeDrm({b"Colorspace": 9, b"HDR_OUTPUT_METADATA": 42}))
    assert platform._connector_property(7, 609, b"HDR_OUTPUT_METADATA") == 42
    assert platform._connector_property(7, 609, b"MISSING") is None


@pytest.mark.parametrize(("props", "refuse"), [
    ({b"HDR_OUTPUT_METADATA": 42}, {1}),   # the count is refused
    ({}, ()),                              # no properties
    ({b"HDR_OUTPUT_METADATA": 42}, {2}),   # the values are refused
    ({b"HDR_OUTPUT_METADATA": 42}, {3}),   # the name is refused
])
def test_an_unreadable_connector_property_is_none(monkeypatch, props, refuse):
    drm(monkeypatch, FakeDrm(props, refuse=refuse))
    assert platform._connector_property(7, 609, b"HDR_OUTPUT_METADATA") is None


@pytest.mark.parametrize(("blob", "eotf"), [
    (hdr_blob(2), "HDR10"),
    (hdr_blob(3), "HLG"),
    (hdr_blob(0), "SDR"),
    (hdr_blob(9), "SDR"),           # not a CTA-861 EOTF
])
def test_the_signalled_eotf_is_read_from_the_blob(monkeypatch, blob, eotf):
    drm(monkeypatch, FakeDrm({b"HDR_OUTPUT_METADATA": 42}, blob))
    assert platform._hdr_eotf(609) == eotf


def test_no_metadata_blob_is_sdr(monkeypatch):
    drm(monkeypatch, FakeDrm({b"HDR_OUTPUT_METADATA": 0}))
    assert platform._hdr_eotf(609) == "SDR"


def test_an_unreadable_eotf_is_none(monkeypatch):
    # The first card has no such property; the second refuses the blob; a
    # short blob on the third says nothing.
    fakes = iter([FakeDrm({}), FakeDrm({b"HDR_OUTPUT_METADATA": 42}, refuse={4}),
                  FakeDrm({b"HDR_OUTPUT_METADATA": 42}, b"\0\0")])
    current = {}

    def ioctl(fd, request, payload):
        if fd not in current:
            current[fd] = next(fakes)
        return current[fd].ioctl(fd, request, payload)

    monkeypatch.setattr(display, "_drm_fds", lambda: [1, 2, 3])
    monkeypatch.setattr(display, "_ioctl", ioctl)
    assert platform._hdr_eotf(609) is None


# --- The readings ----------------------------------------------------------------

def test_facts_join_debugfs_and_the_eotf_and_are_held_briefly(monkeypatch, libreelec):
    reads = []
    monkeypatch.setattr(platform, "_read_debugfs", lambda: reads.append(1) or {"connector_id": "609"})
    monkeypatch.setattr(platform, "_hdr_eotf", lambda connector: "HDR10")
    now = [100.0]
    monkeypatch.setattr(platform.time, "monotonic", lambda: now[0])
    assert platform._facts() == {"connector_id": "609", "eotf": "HDR10"}
    now[0] += 0.5
    platform._facts()
    assert len(reads) == 1
    now[0] += 1
    platform._facts()
    assert len(reads) == 2


@pytest.mark.parametrize(("facts", "eotf"), [({"connector_id": "609"}, None), ({}, "HDR10")])
def test_facts_without_an_eotf(monkeypatch, libreelec, facts, eotf):
    monkeypatch.setattr(platform, "_read_debugfs", lambda: dict(facts))
    monkeypatch.setattr(platform, "_hdr_eotf", lambda connector: eotf)
    assert platform._facts() == facts


@pytest.mark.parametrize(("colorspace", "shown"), [
    ("BT2020_RGB", "BT.2020nc"),
    ("DCI-P3_RGB_D65", "P3 D65"),
    ("P3", "P3 D65"),
    ("SMPTE_170M_YCC", "BT.601"),
    ("BT601_YCC", "BT.601"),
    ("BT709_YCC", "BT.709"),
    ("sRGB", "BT.709"),
    ("Default", "BT.709"),
])
def test_colourimetry_in_the_amlogic_spelling(colorspace, shown):
    assert platform._colourimetry(colorspace) == shown


def readings(monkeypatch, facts, detail=""):
    xbmc.INFO["VideoPlayer.HdrDetail"] = detail
    monkeypatch.setattr(platform, "_facts", lambda: facts)
    return platform.eoft_gamut(), platform.pixformat(), platform.displaymode()


def test_on_amlogic_the_labels_are_passed_through(monkeypatch):
    monkeypatch.setattr(platform, "_amlogic", True)
    xbmc.INFO["Player.Process(amlogic.eoft_gamut)"] = "HDR10 BT.2020nc"
    xbmc.INFO["Player.Process(amlogic.pixformat)"] = "10-bit, YUV420"
    xbmc.INFO["Player.Process(amlogic.displaymode)"] = "2160p23.976hz"
    assert (platform.eoft_gamut(), platform.pixformat(), platform.displaymode()) == (
        "HDR10 BT.2020nc", "10-bit, YUV420", "2160p23.976hz")
    assert platform.is_dv_tunnel() is False
    platform.log_summary()
    assert xbmc.LOG == []


def test_the_intel_dv_tunnel(monkeypatch, libreelec):
    facts = {"colorspace": "Default", "format": "RGB", "bpc": "8", "mode": (23.976, 2160, False)}
    assert readings(monkeypatch, facts, "7.6 FEL · CM4 · HDMI DV") == (
        "DV-Std BT.709", "8-bit, RGB", "2160p23.976hz")
    assert platform.is_dv_tunnel() is True


def test_the_intel_bridge_sending_hdr10(monkeypatch, libreelec):
    facts = {"colorspace": "BT2020_YCC", "format": "YCBCR420", "bpc": "10"}
    xbmc.INFO["System.ScreenResolution"] = "3840x2160 @ 24.00 Hz - Full screen"
    assert readings(monkeypatch, facts, "8.1 · CM2.9 · HDR10 output") == (
        "HDR10 BT.2020nc", "10-bit, YUV420", "2160p24.00hz")
    assert platform.is_dv_tunnel() is False


def test_stock_kodi_signalling(monkeypatch, libreelec):
    facts = {"eotf": "HLG", "colorspace": "BT2020_RGB", "format": "rgb", "bpc": "10",
             "mode": (50.0, 1080, True)}
    assert readings(monkeypatch, facts) == ("HLG BT.2020nc", "10-bit, RGB", "1080i50.000hz")


@pytest.mark.parametrize("facts", [
    {},
    {"format": "RGB", "bpc": "x"},
    {"format": "RGB", "bpc": "0"},
    {"format": "weird", "bpc": "8"},
])
def test_nothing_readable_reads_as_empty(monkeypatch, libreelec, facts):
    assert readings(monkeypatch, facts) == ("", "", "")


def test_the_summary_is_logged_off_amlogic(monkeypatch, libreelec):
    readings(monkeypatch, {"eotf": "SDR", "colorspace": "Default", "format": "RGB", "bpc": "8"})
    platform.log_summary()
    assert xbmc.LOG == [(xbmc.LOGINFO, "BaldPI: output readings from DRM: "
                                       "eotf/gamut='SDR BT.709' pixformat='8-bit, RGB' mode=''")]


# --- The fork's branches in upstream's code -----------------------------------------

@pytest.mark.parametrize(("decoder", "shown"), [
    ("ff-hevc-vaapi", "VAAPI-"),
    ("ff-hevc-drm_prime", "DRM-"),
    ("ff-hevc-v4l2m2m", "V4L2-"),
    ("ff-hevc", "FF-"),
])
def test_the_hardware_back_end_names_the_decoder(decoder, shown):
    xbmc.INFO["Player.Process(videodecoder)"] = decoder
    assert properties.get_VideoDecoderNameVar() == shown


@pytest.mark.parametrize(("tunnel", "shown"), [(True, "DV Tunnel"), (False, "")])
def test_the_dv_tunnel_off_amlogic(monkeypatch, tunnel, shown):
    monkeypatch.setattr(platform, "_amlogic", False)
    monkeypatch.setattr(platform, "is_dv_tunnel", lambda: tunnel)
    assert properties.get_DoviTunnelVar() == shown


@pytest.mark.parametrize(("detail", "parts"), [
    ("8.1", ("8.1", "", "")),
    ("8.1 · CM2.9 · HDMI DV", ("8.1", "", "CMv2.9")),
    ("7.6 FEL · CM4 · HDMI DV", ("7.6", "FEL", "CMv4.0")),
    ("7.6 mel · CMv4.0", ("7.6", "MEL", "CMv4.0")),
    ("Dolby Vision · HDMI DV", ("", "", "")),
    ("", ("", "", "")),
])
def test_hdr_detail_parts(detail, parts):
    assert dvfields._detail_parts(detail) == parts


def test_without_side_data_hdr_detail_names_the_layers():
    info = dvfields.build_info({}, "dolbyvision", "7.6 FEL · CM4 · HDMI DV")
    assert info["output_mode"] == "Dolby Vision Profile 7.6 FEL"
    assert (info["cm_version"], info["bit_depth"]) == ("CMv4.0", "12")


def test_the_vs10_dialog_off_amlogic_opens_the_overlay(monkeypatch):
    monkeypatch.setattr(platform, "_amlogic", False)
    opened = []
    monkeypatch.setattr(overlay, "open_baldpi", lambda: opened.append("overlay"))
    overlay.open_dialog_mode()
    assert opened == ["overlay"]
    assert (xbmc.LOGINFO, "BaldPI: no VS10 here -- opening the overlay instead of the dialog") in xbmc.LOG


def test_a_vs10_mode_is_not_set_off_amlogic(monkeypatch):
    monkeypatch.syspath_prepend(ROOT)
    main = importlib.import_module("main")
    monkeypatch.setattr(platform, "_amlogic", False)
    seen = []
    monkeypatch.setattr(core_vs10, "set_mode", seen.append)
    monkeypatch.setattr(sys, "argv", ["main.py", "run_mode,dv"])
    main.main()
    assert seen == []
