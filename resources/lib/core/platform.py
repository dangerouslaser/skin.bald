# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 U3knOwn

"""Where the output-side readings come from on this box.

CoreELEC's Kodi answers ``Player.Process(amlogic.pixformat)``,
``amlogic.displaymode`` and ``amlogic.eoft_gamut`` from the Amlogic HDMI
driver's ``config`` node.  Other Linux builds -- LibreELEC, and the Intel Dolby
Vision build of it (``intel-dv-libreelec``) -- have no such labels, so the same
three readings are rebuilt here, in the Amlogic spelling, from what those builds
do have:

* ``VideoPlayer.HdrDetail``, which the Intel DV build suffixes with
  ``· HDMI DV`` or ``· HDR10 output`` while its bridge is driving the output;
* the DRM connector's ``HDR_OUTPUT_METADATA`` blob, read through Kodi's own DRM
  descriptor (see ``core.display``), for the HDR10 / HLG signalling stock Kodi
  sets up itself;
* the DRM debugfs (``state``, and i915's ``i915_display_info``) for the pixel
  encoding, bit depth, colorimetry and exact mode on the wire.

Spelling them the Amlogic way keeps every parser, skin condition and dashboard
field downstream unchanged: ``EOTF Colourimetry`` (``DV-Std BT.2020nc``,
``HDR10 BT.2020nc``, ``SDR BT.709``), ``<depth>-bit, <encoding>``
(``8-bit, RGB``) and ``<lines><scan><rate>hz`` (``2160p23.976hz``).

Everything here is best effort: a missing debugfs, a driver without a
property, or a Kodi without DRM leaves a field empty, never an error.
"""

import ctypes
import os
import re
import time

import xbmc

from core import display

# --- Platform --------------------------------------------------------------

_amlogic: bool | None = None


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def is_coreelec() -> bool:
    """Return True when running on a CoreELEC installation."""
    if os.path.isdir("/etc/coreelec"):
        return True
    return "coreelec" in _read_text("/etc/os-release").lower()


def is_amlogic() -> bool:
    """Return whether the Amlogic labels and sysfs nodes are there to read.

    CoreELEC is the only Kodi that exposes them, and only on Amlogic hardware,
    so either sign is enough.  Answered once: neither changes while Kodi runs.
    """
    global _amlogic
    if _amlogic is None:
        _amlogic = os.path.isdir("/sys/class/amhdmitx") or is_coreelec()
    return _amlogic


def is_supported() -> bool:
    """Return whether the overlay has a source for its output readings here:
    an Amlogic box, or any Linux with DRM (LibreELEC and its Intel DV build)."""
    return is_amlogic() or os.path.isdir("/sys/class/drm")


# --- Kodi's own labels -----------------------------------------------------

def _label(name: str) -> str:
    # Imported late: core.utils imports nothing from here, but keeping the
    # read-pass cache in one place means going through its ``info``.
    from core.utils import info
    return info(name)


_DV_BRIDGE_DV    = "hdmi dv"
_DV_BRIDGE_HDR10 = "hdr10 output"


def dv_bridge_output() -> str:
    """Return what the Intel DV bridge is sending: ``'dv'``, ``'hdr10'`` or
    ``''`` when it is not driving the output (or this is not that build).

    Read from ``VideoPlayer.HdrDetail``, which that build suffixes only while
    the bridge has actually committed the signal -- the label is output
    telemetry there, not a claim about the source.
    """
    detail = _label("VideoPlayer.HdrDetail").lower()
    if detail.endswith(_DV_BRIDGE_DV):
        return "dv"
    if detail.endswith(_DV_BRIDGE_HDR10):
        return "hdr10"
    return ""


# --- DRM debugfs -----------------------------------------------------------

_DEBUGFS_DRI = "/sys/kernel/debug/dri"

# The readings below change with a mode switch at most, so they are held
# briefly: every row of one polling pass shares a single set of file reads.
_CACHE_TTL = 1.0
_cache: dict | None = None
_cache_until = 0.0


def _debugfs_dirs() -> list[str]:
    """Return the DRM debugfs directories to look in, Kodi's own card first."""
    dirs = []
    for fd in display._drm_fds():
        try:
            target = os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            continue
        minor = target.rsplit("card", 1)[-1]
        path = os.path.join(_DEBUGFS_DRI, minor)
        if minor.isdigit() and path not in dirs:
            dirs.append(path)
    try:
        for entry in sorted(os.listdir(_DEBUGFS_DRI)):
            path = os.path.join(_DEBUGFS_DRI, entry)
            if entry.isdigit() and path not in dirs:
                dirs.append(path)
    except OSError:
        pass
    return dirs


_CONNECTOR_RE = re.compile(r"^connector\[(\d+)\]: (\S+)\n((?:\t.*\n?)*)", re.M)
_CRTC_RE      = re.compile(r"^crtc\[(\d+)\]: (.+)\n((?:\t.*\n?)*)", re.M)
_FIELD_RE     = re.compile(r"^\t(\w+)=(.*)$", re.M)
_MODE_RE      = re.compile(
    r'mode[:=] ?"[^"]*": (\d+) (\d+) \d+ \d+ \d+ (\d+) (\d+) \d+ \d+ (\d+) 0x[0-9a-f]+ (0x[0-9a-f]+)'
)
_PIPE_RE      = re.compile(r"^\[CRTC:\d+:([^\]]+)\]:\n((?:\t.*\n?)*)", re.M)
_BPP_RE       = re.compile(r"\bbpp=(\d+)")

# DRM_MODE_FLAG_INTERLACE
_FLAG_INTERLACE = 0x10


def _active_output(state: str) -> dict | None:
    """Return the connector the picture leaves through, from the atomic state.

    The one bound to a CRTC; a connector with ``crtc=(null)`` is idle.
    """
    for match in _CONNECTOR_RE.finditer(state):
        fields = dict(_FIELD_RE.findall(match.group(3)))
        crtc = fields.get("crtc", "(null)")
        if crtc and crtc != "(null)":
            fields["id"] = match.group(1)
            fields["name"] = match.group(2)
            return fields
    return None


def _crtc_mode(state: str, crtc: str) -> tuple[float, int, bool] | None:
    """Return ``(refresh, lines, interlaced)`` of ``crtc``'s mode, or None.

    The rate is computed from the pixel clock and totals rather than taken from
    the rounded ``vrefresh``, so 23.976 reads as such and not as 24.
    """
    for match in _CRTC_RE.finditer(state):
        if match.group(2).strip() != crtc:
            continue
        mode = _MODE_RE.search(match.group(3))
        if not mode:
            return None
        clock, htotal, vdisplay, vtotal = (int(mode.group(i)) for i in (2, 3, 4, 5))
        flags = int(mode.group(6), 16)
        if not clock or not htotal or not vtotal:
            return None
        refresh = clock * 1000.0 / (htotal * vtotal)
        interlaced = bool(flags & _FLAG_INTERLACE)
        if interlaced:
            refresh *= 2
        return refresh, vdisplay, interlaced
    return None


def _pipe_bpp(display_info: str, crtc: str) -> int:
    """Return the i915 pipe's bits per pixel (24 = 8 bits per component)."""
    for match in _PIPE_RE.finditer(display_info):
        if match.group(1).strip() == crtc:
            bpp = _BPP_RE.search(match.group(2))
            return int(bpp.group(1)) if bpp else 0
    return 0


def _read_debugfs() -> dict:
    """Collect the output facts debugfs offers, keyed as the Amlogic node is."""
    for base in _debugfs_dirs():
        state = _read_text(os.path.join(base, "state"))
        if not state:
            continue
        output = _active_output(state)
        if not output:
            continue
        crtc = output.get("crtc", "")
        facts = {
            "connector_id": output.get("id", ""),
            "colorspace":   output.get("colorspace", ""),
            "format":       output.get("output_format", ""),
            "bpc":          output.get("output_bpc", "0"),
        }
        mode = _crtc_mode(state, crtc)
        if mode:
            facts["mode"] = mode
        bpp = _pipe_bpp(_read_text(os.path.join(base, "i915_display_info")), crtc)
        if bpp:
            facts["bpc"] = str(bpp // 3)
        return facts
    return {}


# --- DRM connector: HDR_OUTPUT_METADATA ------------------------------------

class _GetBlob(ctypes.Structure):
    _fields_ = [
        ("blob_id", ctypes.c_uint32),
        ("length", ctypes.c_uint32),
        ("data", ctypes.c_uint64),
    ]


_IOCTL_GETPROPBLOB = display._iowr(0xAC, ctypes.sizeof(_GetBlob))

# hdr_output_metadata.hdmi_metadata_type1.eotf (CTA-861-G table 45).
_EOTF_NAMES = {0: "SDR", 1: "HDR", 2: "HDR10", 3: "HLG"}


def _connector_property(fd: int, connector_id: int, name: bytes) -> int | None:
    """Return the current value of a connector property, or None."""
    props = display._ObjGetProperties(
        obj_id=connector_id, obj_type=display._DRM_MODE_OBJECT_CONNECTOR
    )
    if not display._ioctl(fd, display._IOCTL_OBJ_GETPROPERTIES, props):
        return None
    count = props.count_props
    if not count:
        return None
    prop_ids = (ctypes.c_uint32 * count)()
    values = (ctypes.c_uint64 * count)()
    props = display._ObjGetProperties(
        props_ptr=ctypes.cast(prop_ids, ctypes.c_void_p).value,
        prop_values_ptr=ctypes.cast(values, ctypes.c_void_p).value,
        count_props=count,
        obj_id=connector_id,
        obj_type=display._DRM_MODE_OBJECT_CONNECTOR,
    )
    if not display._ioctl(fd, display._IOCTL_OBJ_GETPROPERTIES, props):
        return None
    for index in range(min(count, props.count_props)):
        prop = display._GetProperty(prop_id=prop_ids[index])
        if display._ioctl(fd, display._IOCTL_GETPROPERTY, prop) and prop.name.upper() == name:
            return values[index]
    return None


def _hdr_eotf(connector_id: int) -> str | None:
    """Return the EOTF the connector is signalling (``SDR`` / ``HDR10`` /
    ``HLG``), or None when it cannot be read.  No blob means no DRM infoframe,
    i.e. SDR."""
    for fd in display._drm_fds():
        blob_id = _connector_property(fd, connector_id, b"HDR_OUTPUT_METADATA")
        if blob_id is None:
            continue
        if not blob_id:
            return "SDR"
        # struct hdr_output_metadata: __u32 metadata_type, then the infoframe
        # whose first byte is the EOTF.
        data = (ctypes.c_uint8 * 32)()
        blob = _GetBlob(
            blob_id=int(blob_id),
            length=ctypes.sizeof(data),
            data=ctypes.cast(data, ctypes.c_void_p).value,
        )
        if display._ioctl(fd, _IOCTL_GETPROPBLOB, blob) and blob.length >= 5:
            return _EOTF_NAMES.get(data[4], "SDR")
    return None


# --- The readings ----------------------------------------------------------

def _facts() -> dict:
    """Return the cached debugfs facts plus the connector's EOTF."""
    global _cache, _cache_until
    now = time.monotonic()
    if _cache is not None and now < _cache_until:
        return _cache
    facts = _read_debugfs()
    connector = facts.get("connector_id", "")
    if connector.isdigit():
        eotf = _hdr_eotf(int(connector))
        if eotf:
            facts["eotf"] = eotf
    _cache = facts
    _cache_until = now + _CACHE_TTL
    return facts


# DRM "Colorspace" enum names -> the Amlogic node's colourimetry spelling.
def _colourimetry(colorspace: str) -> str:
    low = colorspace.lower()
    if "bt2020" in low:
        return "BT.2020nc"
    if "dci-p3" in low or "p3" in low:
        return "P3 D65"
    if "601" in low or "170m" in low:
        return "BT.601"
    if "709" in low or "srgb" in low:
        return "BT.709"
    # "Default": no colorimetry in the AVI infoframe, which for the HD and UHD
    # modes means BT.709.  Stock Kodi sets BT.2020 explicitly for HDR, and the
    # Intel DV tunnel leaves it at default, so this is what is on the wire.
    return "BT.709"


_ENCODINGS = {
    "rgb": "RGB",
    "ycbcr444": "YUV444",
    "ycbcr422": "YUV422",
    "ycbcr420": "YUV420",
    "yuv444": "YUV444",
    "yuv422": "YUV422",
    "yuv420": "YUV420",
}


def eoft_gamut() -> str:
    """Return ``Player.Process(amlogic.eoft_gamut)``, or its DRM equivalent."""
    if is_amlogic():
        return _label("Player.Process(amlogic.eoft_gamut)")

    facts = _facts()
    bridge = dv_bridge_output()
    if bridge == "dv":
        # The Intel bridge tunnels ICtCp through 8-bit RGB: the TV-led
        # (standard) Dolby Vision signal, as the Amlogic node names it.
        eotf = "DV-Std"
    elif bridge == "hdr10":
        eotf = "HDR10"
    else:
        eotf = facts.get("eotf", "")
    if not eotf:
        return ""
    return f"{eotf} {_colourimetry(facts.get('colorspace', ''))}"


def pixformat() -> str:
    """Return ``Player.Process(amlogic.pixformat)``, or its DRM equivalent."""
    if is_amlogic():
        return _label("Player.Process(amlogic.pixformat)")

    facts = _facts()
    if dv_bridge_output() == "dv":
        return "8-bit, RGB"
    encoding = _ENCODINGS.get(facts.get("format", "").lower().replace("_", ""), "")
    bpc = facts.get("bpc", "0")
    if not encoding or not bpc.isdigit() or not int(bpc):
        return ""
    return f"{bpc}-bit, {encoding}"


_SCREEN_RE = re.compile(r"(\d+)x(\d+)\s*@\s*([\d.]+)\s*Hz", re.I)


def displaymode() -> str:
    """Return ``Player.Process(amlogic.displaymode)``, or its DRM equivalent.

    The mode on the wire from debugfs when it is readable, Kodi's own
    ``System.ScreenResolution`` otherwise.
    """
    if is_amlogic():
        return _label("Player.Process(amlogic.displaymode)")

    mode = _facts().get("mode")
    if mode:
        refresh, lines, interlaced = mode
        scan = "i" if interlaced else "p"
        return f"{lines}{scan}{refresh:.3f}hz"

    screen = _SCREEN_RE.search(_label("System.ScreenResolution"))
    if not screen:
        return ""
    return f"{screen.group(2)}p{screen.group(3)}hz"


def is_dv_tunnel() -> bool:
    """Return whether Dolby Vision is leaving the box tunnelled in 8-bit RGB."""
    if is_amlogic():
        return False  # answered from sysfs by the caller
    return dv_bridge_output() == "dv"


def log_summary() -> None:
    """Log where the output readings come from, once per overlay opening."""
    if is_amlogic():
        return
    xbmc.log(
        f"TinyPPI: output readings from DRM: eotf/gamut='{eoft_gamut()}' "
        f"pixformat='{pixformat()}' mode='{displaymode()}'",
        xbmc.LOGINFO,
    )
