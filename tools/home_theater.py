#!/usr/bin/env python3
"""Build Bald's home theater windows: the LG TV, Denon and Sonos settings pages, and their shared variables.

Bald works with three add-ons from dangerouslaser's repository (listed by repository.bald):
  service.webostv   LG webOS TV Control: inputs, picture presets per video type, motion and sound rules, the Remote
                    Bridge (Magic Remote pointer and buttons)
  service.denonavr  Denon AVR Control: power, input, incoming audio, volume
  service.sonos     Sonos Control: incoming audio, night mode, speech enhancement, volume
Each publishes its state as Window(Home) properties (WebOS.*, Denon.*, Sonos.*) and takes commands through
RunScript(<addon>,...) or the NotifyAll builtin. The pages, rows and help texts come from Estuary YBLOD
(skin.estuary.yblod, tools/gen_lgtv.py, gen_denon.py and gen_sonos.py), redrawn in Bald's settings scaffold
(Includes_Bald_Configure.xml): the category list in the sidebar, the rows at Kodi's settings pages' width
(SettingsCategory.xml), the focused row's help under them, and the device's name and connection where Bald's own
pages have the settings level button. Option labels and help texts are the add-ons' own strings ($ADDON[...]), so they
stay in step with the add-ons' settings.

In the video OSD (Includes_Bald_OSD.xml) each device in use has a button after process info: LG TV (70064) and the
audio system (70065). Focusing one opens its companion panel (1135, 1136) with the live values; the rows send commands
to the running add-on with the NotifyAll builtin (Denon, Sonos), or open one of the add-on's lists (LG TV), so the panel
stays open while they act. A short capsule (1137) shows the receiver's or player's volume whenever it changes, in
the place and look of Kodi's volume bar (DialogVolumeBar.xml).

Bald is remote-only and draws no mouse pointer, except for the LG TV's Magic Remote through service.webostv's Remote
Bridge, which is a mouse to Kodi: while it is in use (Bald_WebOSPointer) Startup.xml and Home.xml keep Kodi's mouse
input on, and Pointer.xml shows the TV's own webOS pointer, which the add-on saves to its data folder, and its
animations (Estuary YBLOD's tools/gen_pointer.py): while WebOS.PointerLook names one (the wheel scrolling: down, up,
downx and upx when it turns back, end as it rests; enter as the pointer appears, exit as it goes) the pointer plays it,
and the click pointer plays anim_press once WebOS.PointerAnimated is set. Kodi loads pointer textures with the skin and
ignores $INFO there, so the add-on reloads the skin when the images change. Without them, the webOS-style pointers in
media/bald (Estuary YBLOD's tools/make_pointer.py) stand in. All are 256 x 256 with the hotspot in the middle.

Which devices are in use is the user's choice (Bald Settings, Playback, Home theater; Custom_1119_BaldPlayback.xml),
kept in the skin settings Estuary YBLOD used, setup_tv_lg, setup_receiver_denon and setup_receiver_sonos, because
service.webostv reads setup_receiver_sonos to pick where the TV remote's volume buttons go.

This script also owns the en_gb strings 31500-31596 (STRINGS): it rewrites that block of strings.po with each string's
source comments, found by scanning 1080i, so hand-written windows may use these strings too.

  python3 tools/home_theater.py          write the windows, the includes and the strings
  python3 tools/home_theater.py --check  exit 1 if any of them is out of date
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
PO = ROOT / "language" / "resource.language.en_gb" / "strings.po"
P = "Window(Home).Property"
FIRST_STRING, LAST_STRING = 31500, 31596

# Bald's own strings for the home theater windows (Estuary YBLOD's wording). Kodi's own strings where they say the
# same: 126 Status, 13376 Volume, 14125 Input, 10140 Add-on settings, 19020 TV, 16018 None, 33060 Power.
STRINGS = {
    31500: ("LG TV", "Settings hub, Playback and the OSD: the LG webOS TV (service.webostv)"),
    31501: ("Denon", "Settings hub, Playback and the OSD: the Denon receiver (service.denonavr)"),
    31502: ("Sonos", "Settings hub, Playback and the OSD: the Sonos player (service.sonos)"),
    31503: ("Picture preset", None),
    31504: ("Apps", None),
    31505: ("Sound output", None),
    31506: ("Mute", None),
    31507: ("Screen", None),
    31508: ("Turn TV off", None),
    31509: ("Remote buttons", None),
    31510: ("Connection", None),
    31511: ("Find TV on the network", None),
    31512: ("Re-pair", None),
    31513: ("Picture", None),
    31514: ("Send a message to the TV", None),
    31515: ("Turning the screen off keeps the sound playing. Press any button on the TV remote to turn it back on.", None),
    31516: ("Picture preset for what's on screen now. The list shows the presets the TV offers for the current signal.",
            None),
    31517: ("Preset to switch to when a video of this type starts. Pick from the presets the TV offers.", None),
    31518: ("This TV's webOS doesn't report its picture preset, so presets come from a built-in list and the current one "
            "shown is the last one set from Kodi.", None),
    31519: ("Receiver", None),
    31520: ("Find receiver on the network", None),
    31521: ("Receiver address", None),
    31522: ("Incoming audio", None),
    31523: ("Playing as", None),
    31524: ("Volume step", None),
    31525: ("Maximum volume", None),
    31526: ("TV remote", None),
    31527: ("Looks for Denon receivers on your network and uses the one you pick. Denon receivers need no pairing.",
            None),
    31528: ("Type the receiver's IP address if it isn't found on the network.", None),
    31529: ("How much one volume up or down press changes the receiver's volume.", None),
    31530: ("Nothing in Kodi turns the receiver up past this, a safety cap. 0 dB is reference level (80 on the "
            "receiver's display).", None),
    31531: ("Turns the receiver on, or puts it in standby.", None),
    31532: ("Standby", None),
    31533: ("Select to open the receiver menu: incoming audio, how it plays, volume and mute.", None),
    31534: ("The audio format coming in from Kodi, and how the receiver decodes it, as the receiver reports them. Its "
            "calibrated sound modes are never changed.", None),
    31535: ("No signal", None),
    31536: ("Find player on the network", None),
    31537: ("Player address", None),
    31538: ("Night mode", None),
    31539: ("Speech enhancement", None),
    31540: ("Not the TV", None),
    31541: ("Looks for Sonos players on your network and uses the one you pick. Home-theater players (Arc, Beam, Ray, "
            "Amp) come first. Sonos needs no pairing.", None),
    31542: ("Type the player's IP address if it isn't found on the network.", None),
    31543: ("Select to open the Sonos menu: incoming audio, volume, mute, night mode and speech enhancement.", None),
    31544: ("The audio format coming in from the TV, as the player reports it.", None),
    31545: ("Night mode: softer loud sounds and clearer dialogue at low volume.", None),
    31546: ("Speech enhancement: clearer dialogue.", None),
    31547: ("How much one volume up or down press changes the player's volume (0 to 100).", None),
    31548: ("Nothing in Kodi turns the player up past this, a safety cap (0 to 100).", None),
    31549: ("Player", None),
    31550: ("Volume up", None),
    31551: ("Volume down", None),
    31552: ("More settings", None),
    31553: ("Home theater", "Bald Settings, Playback: the category for the TV and audio system"),
    31554: ("The TV and audio system Kodi controls through their add-ons. Each adds its page to Settings and its button "
            "to the video controls.", "Bald Settings, Playback: note for Home theater"),
    31555: ("Audio system", "Bald Settings, Playback: the receiver or soundbar in use"),
    31556: ("LG (webOS)", None),
    31557: ("add-on not installed", "After a home theater choice whose add-on is missing"),
    31558: ("Your LG TV: inputs and apps, picture presets for each kind of video, motion and sound rules, and the Remote "
            "Bridge.", "Settings hub: note for LG TV"),
    31559: ("Your Denon receiver: power, input, incoming audio and volume.", "Settings hub: note for Denon"),
    31560: ("Your Sonos player: incoming audio, night mode, speech enhancement and volume.",
            "Settings hub: note for Sonos"),
    31561: ("Inputs", None),
}


def s(n: int) -> str:
    return f"$LOCALIZE[{n}]"


def a(addon: str, n: int) -> str:
    return f"$ADDON[{addon} {n}]"


def run(addon: str, *args: str) -> str:
    return f"RunScript({addon},{','.join(args)})"


# ============ Pages ============
# A page is (window id, file, title, categories, help variable, status label, model label). A category is
# (label, rows). Rows:
#   ("button", id, label, onclick, label2, enable, help[, visible])
#   ("radio", id, label, selected, [(condition, onclick)], enable, help)
#   ("header", id, label)
#   ("note", id, label, visible)

WEBOS = "service.webostv"
W_CONNECTED = f"String.IsEqual({P}(WebOS.Connected),true)"
# Older webOS (e.g. 5.5) won't report the picture mode, so presets are off there.
W_PICTURE_OK = f"!String.IsEqual({P}(WebOS.PictureSupported),false)"


def w(n: int) -> str:
    return a(WEBOS, n)


def wrun(*args: str) -> str:
    return run(WEBOS, *args)


def wbool(key: str) -> str:
    return f"Addon.SettingBool({WEBOS},{key})"


# Source quality: one row per source, then (when it is set to Custom) a row per cleanup. Source: (row id, setting,
# label, help, variable, the setting's Custom index).
CUSTOM_FIRST_ID = 561
QUALITY_SOURCES = (
    (506, "livetv", 32521, 32571, "Bald_LGTVQualityLiveTV", 5),
    (507, "sd", 32522, 32572, "Bald_LGTVQualitySD", 5),
    (508, "hd", 32523, 32573, "Bald_LGTVQualityHD", 5),
    (509, "uhd", 32525, 32575, "Bald_LGTVQualityUHD", 6),
    (557, "restore", 32524, 32574, "Bald_LGTVQualityRestore", 5),
)
# Custom cleanups: (short name, label, value labels: leave unchanged, off, low, medium, high[, auto]).
QUALITY_CUSTOM = (
    ("nr", 32502, (32530, 32510, 32512, 32513, 32514, 32515)),
    ("mpeg", 32503, (32530, 32510, 32512, 32513, 32514, 32515)),
    ("grad", 32504, (32530, 32510, 32512, 32513, 32514)),
    ("sr", 32505, (32530, 32510, 32512, 32513, 32514)),
)
QUALITY_LABELS = {  # each source setting's value labels
    "uhd": (32536, 32530, 32531, 32532, 32533, 32534, 32537),
    "restore": (32535, 32531, 32532, 32533, 32534, 32537),
}
QUALITY_LEVEL_LABELS = (32530, 32531, 32532, 32533, 32534, 32537)


def quality_rows() -> list[tuple]:
    rows = []
    for n, (cid, source, label, help_id, var, custom) in enumerate(QUALITY_SOURCES):
        rows.append(("button", cid, w(label), wrun("setting", f"quality_{source}"), f"$VAR[{var}]", "", w(help_id)))
        shown = f"Integer.IsEqual(Addon.SettingInt({WEBOS},quality_{source}),{custom})"
        for m, (short, sub_label, _values) in enumerate(QUALITY_CUSTOM):
            rows.append(("button", CUSTOM_FIRST_ID + n * 4 + m, "      " + w(sub_label),
                         wrun("setting", f"quality_{source}_{short}"), f"$VAR[Bald_LGTVQ_{source}_{short}]", "",
                         w(32576), shown))
    return rows


RULES_ON = f"{wbool('rules_enabled')} + {W_PICTURE_OK}"
POINTER_ON = wbool("bridge_pointer")
BRIDGE_ON = wbool("remote_bridge")

LGTV = [
    (s(19020), [
        ("button", 100, s(14125), wrun("ui", "input"), f"$INFO[{P}(WebOS.AppTitle)]", W_CONNECTED, ""),
        ("button", 101, s(31504), wrun("ui", "app"), "", W_CONNECTED, ""),
        ("button", 102, s(31505), wrun("ui", "sound_output"), f"$INFO[{P}(WebOS.SoundOutputLabel)]", W_CONNECTED, ""),
        ("button", 103, s(13376), wrun("ui", "volume"), f"$INFO[{P}(WebOS.Volume)]", W_CONNECTED, ""),
        ("radio", 104, s(31506), f"String.IsEqual({P}(WebOS.Muted),true)", [("", wrun("mute", "toggle"))],
         W_CONNECTED, ""),
        ("radio", 105, s(31507), f"String.IsEqual({P}(WebOS.ScreenOn),true)",
         [(f"String.IsEqual({P}(WebOS.ScreenOn),true)", wrun("screen", "off")),
          (f"!String.IsEqual({P}(WebOS.ScreenOn),true)", wrun("screen", "on"))], W_CONNECTED, s(31515)),
        ("button", 106, s(31509), wrun("ui", "remote"), "", W_CONNECTED, ""),
        ("button", 107, s(31514), wrun("ui", "toast"), "", W_CONNECTED, ""),
        ("button", 108, s(31508), wrun("power_off"), "", W_CONNECTED, ""),
    ]),
    (s(31513), [
        ("note", 290, s(31518), f"String.IsEqual({P}(WebOS.PictureReadable),false)"),
        ("button", 200, s(31503), wrun("ui", "picture_preset"), f"$INFO[{P}(WebOS.PicturePresetLabel)]",
         f"{W_CONNECTED} + {W_PICTURE_OK}", s(31516)),
        ("header", 291, s(14086)),
        ("radio", 201, w(32031), wbool("rules_enabled"), [("", wrun("setting", "rules_enabled"))], W_PICTURE_OK,
         w(32081)),
        ("button", 202, w(32032), wrun("choose_preset", "sdr", "stay"), f"$INFO[{P}(WebOS.Rule.SDR)]", RULES_ON,
         s(31517)),
        ("button", 203, w(32033), wrun("choose_preset", "hdr10", "stay"), f"$INFO[{P}(WebOS.Rule.HDR10)]", RULES_ON,
         s(31517)),
        ("button", 204, w(32034), wrun("choose_preset", "hlg", "stay"), f"$INFO[{P}(WebOS.Rule.HLG)]", RULES_ON,
         s(31517)),
        ("button", 205, w(32035), wrun("choose_preset", "dolbyvision", "stay"), f"$INFO[{P}(WebOS.Rule.DolbyVision)]",
         RULES_ON, s(31517)),
        ("radio", 206, w(32036), wbool("restore_on_stop"), [("", wrun("setting", "restore_on_stop"))], RULES_ON,
         w(32086)),
    ]),
    (w(32400), [
        ("header", 590, w(32407)),
        ("button", 500, w(32401), wrun("setting", "motion_film"), "$VAR[Bald_LGTVMotionFilm]", "", w(32451)),
        ("button", 501, w(32402), wrun("setting", "motion_video"), "$VAR[Bald_LGTVMotionVideo]", "", w(32452)),
        ("button", 502, w(32403), wrun("setting", "motion_restore"), "$VAR[Bald_LGTVMotionRestore]", "", w(32453)),
        ("header", 592, w(32520)),
        *quality_rows(),
        ("header", 591, w(32408)),
        ("button", 503, w(32404), wrun("setting", "sound_video"), "$VAR[Bald_LGTVSoundVideo]", "", w(32454)),
        ("button", 504, w(32405), wrun("setting", "sound_livetv"), "$VAR[Bald_LGTVSoundLiveTV]", "", w(32455)),
        ("button", 505, w(32406), wrun("setting", "sound_music"), "$VAR[Bald_LGTVSoundMusic]", "", w(32456)),
    ]),
    (w(32200), [
        ("button", 300, w(32201), wrun("choose_kodi_input", "stay"), "$VAR[Bald_LGTVKodiInput]", "", w(32251)),
        ("button", 301, w(32203), wrun("setting", "on_tv_off"), "$VAR[Bald_LGTVOnTvOff]", "", w(32253)),
        ("button", 302, w(32204), wrun("setting", "on_switch_away"), "$VAR[Bald_LGTVOnSwitchAway]", "", w(32254)),
        ("radio", 303, w(32205), wbool("resume_on_return"), [("", wrun("setting", "resume_on_return"))],
         f"Integer.IsEqual(Addon.SettingInt({WEBOS},on_switch_away),1)", w(32255)),
        ("radio", 304, w(32206), wbool("transparent_control"), [("", wrun("setting", "transparent_control"))], "",
         w(32256)),
        ("header", 390, w(32600)),
        ("button", 305, "$VAR[Bald_LGTVRemoteBridgeAction]", wrun("bridge_setup"), "$VAR[Bald_LGTVRemoteBridge]",
         W_CONNECTED, w(32652)),
        ("radio", 306, w(32601), BRIDGE_ON, [("", wrun("setting", "remote_bridge"))], "", w(32651)),
        ("radio", 308, w(32605), POINTER_ON, [("", wrun("setting", "bridge_pointer"))], BRIDGE_ON, w(32655)),
        ("button", 316, w(32609), wrun("setting", "bridge_wheel_speed"), "$VAR[Bald_LGTVWheelSpeed]", BRIDGE_ON,
         w(32659)),
        ("radio", 317, w(32635), wbool("bridge_volume_receiver"), [("", wrun("setting", "bridge_volume_receiver"))],
         f"{BRIDGE_ON} + $EXP[Bald_SetupReceiver]", w(32685)),
        ("button", 318, w(32694), wrun("setting", "kodi_buttons"), "$VAR[Bald_LGTVKodiButtons]", BRIDGE_ON, w(32695)),
        ("button", 309, w(32606), wrun("setting", "bridge_pointer_wake"), "$VAR[Bald_LGTVPointerWake]", POINTER_ON,
         w(32656)),
        ("radio", 310, w(32607), wbool("bridge_pointer_return"), [("", wrun("setting", "bridge_pointer_return"))],
         POINTER_ON, w(32657)),
        ("radio", 319, w(32697), wbool("bridge_pointer_arrows"), [("", wrun("setting", "bridge_pointer_arrows"))],
         POINTER_ON, w(32698)),
        ("button", 311, w(32630), wrun("setting", "tv_pointer_speed"), "$VAR[Bald_LGTVPointerSpeed]", POINTER_ON,
         w(32680)),
        ("button", 312, w(32631), wrun("setting", "tv_pointer_size"), "$VAR[Bald_LGTVPointerSize]", POINTER_ON,
         w(32681)),
        ("button", 313, w(32632), wrun("setting", "tv_pointer_shape"), "$VAR[Bald_LGTVPointerShape]", POINTER_ON,
         w(32682)),
        ("radio", 314, w(32633), wbool("tv_pointer_align"), [("", wrun("setting", "tv_pointer_align"))], POINTER_ON,
         w(32683)),
        ("radio", 315, w(32634), wbool("tv_pointer_autohide"), [("", wrun("setting", "tv_pointer_autohide"))],
         POINTER_ON, w(32684)),
        ("button", 307, w(32603), wrun("bridge_remove"), "", W_CONNECTED, w(32653)),
    ]),
    (s(31510), [
        ("button", 400, s(126), wrun("ui", "status"), "$VAR[Bald_LGTVConnectionText]", "", ""),
        ("button", 401, s(31511), wrun("ui", "find_tv"), f"$INFO[{P}(WebOS.ConfiguredHost)]", "", w(32056)),
        ("radio", 402, w(32011), wbool("toast_on_connect"), [("", wrun("setting", "toast_on_connect"))], "", w(32061)),
        ("button", 403, s(31512), wrun("ui", "repair"), "", "", w(32071)),
        ("button", 404, s(10140), f"Addon.OpenSettings({WEBOS})", "", "", ""),
    ]),
]

DENON = "service.denonavr"
D_CONNECTED = f"String.IsEqual({P}(Denon.Connected),true)"
D_ON = f"{D_CONNECTED} + String.IsEqual({P}(Denon.Power),true)"
D_HOST = f"$INFO[{P}(Denon.Host)]"


def drun(*args: str) -> str:
    return run(DENON, *args)


# Volume buttons on the TV remote: service.webostv's switch, shared by the Denon and Sonos pages.
REMOTE_VOLUME = ("radio", 204, w(32635), wbool("bridge_volume_receiver"),
                 [("", wrun("setting", "bridge_volume_receiver"))], f"$EXP[Bald_SetupLG] + {BRIDGE_ON}", w(32685))

DENON_PAGE = [
    (s(31519), [
        ("button", 100, s(126), drun("osd"), "$VAR[Bald_DenonStatusText]", D_CONNECTED, s(31533)),
        ("radio", 101, s(33060), f"String.IsEqual({P}(Denon.Power),true)", [("", drun("power", "toggle"))],
         D_CONNECTED, s(31531)),
        ("button", 102, s(14125), drun("osd"), f"$INFO[{P}(Denon.InputName)]", D_ON, s(31533)),
        ("button", 103, s(31522), drun("osd"), "$VAR[Bald_DenonSignalText]", D_ON, s(31534)),
        ("button", 104, s(31523), drun("osd"), f"$INFO[{P}(Denon.SoundMode)]", D_ON, s(31534)),
    ]),
    (s(13376), [
        ("button", 200, s(13376), drun("osd"), "$VAR[Bald_DenonVolumeText]", D_ON, s(31533)),
        ("radio", 201, s(31506), f"String.IsEqual({P}(Denon.Mute),true)", [("", drun("mute", "toggle"))], D_ON, ""),
        ("button", 202, s(31524), drun("setting", "volume_step"), "$VAR[Bald_DenonVolumeStep]", "", s(31529)),
        ("button", 203, s(31525), drun("setting", "max_volume"), f"$INFO[{P}(Denon.MaxVolume),, dB]", "", s(31530)),
        ("header", 290, s(31526)),
        REMOTE_VOLUME,
    ]),
    (s(31510), [
        ("button", 300, s(31520), drun("find_receiver"), D_HOST, "", s(31527)),
        ("button", 301, s(31521), drun("setting", "host"), D_HOST, "", s(31528)),
        ("button", 302, s(10140), f"Addon.OpenSettings({DENON})", "", "", ""),
    ]),
]

SONOS = "service.sonos"
S_CONNECTED = f"String.IsEqual({P}(Sonos.Connected),true)"
S_HOST = f"$INFO[{P}(Sonos.Host)]"


def srun(*args: str) -> str:
    return run(SONOS, *args)


def shas(prop: str) -> str:
    return f"!String.IsEmpty({P}(Sonos.{prop}))"


SONOS_PAGE = [
    (s(31549), [
        ("button", 100, s(126), srun("osd"), "$VAR[Bald_SonosStatusText]", S_CONNECTED, s(31543)),
        ("button", 101, s(21870), srun("osd"), "$VAR[Bald_SonosSourceText]", S_CONNECTED, s(31543)),
        ("button", 102, s(31522), srun("osd"), "$VAR[Bald_SonosFormatText]", S_CONNECTED, s(31544)),
        ("radio", 103, s(31538), f"String.IsEqual({P}(Sonos.Night),true)", [("", srun("night", "toggle"))],
         f"{S_CONNECTED} + {shas('Night')}", s(31545)),
        ("radio", 104, s(31539), f"String.IsEqual({P}(Sonos.Speech),true)", [("", srun("speech", "toggle"))],
         f"{S_CONNECTED} + {shas('Speech')}", s(31546)),
    ]),
    (s(13376), [
        ("button", 200, s(13376), srun("osd"), "$VAR[Bald_SonosVolumeText]", S_CONNECTED, s(31543)),
        ("radio", 201, s(31506), f"String.IsEqual({P}(Sonos.Mute),true)", [("", srun("mute", "toggle"))],
         S_CONNECTED, ""),
        ("button", 202, s(31524), srun("setting", "volume_step"), "$VAR[Bald_SonosVolumeStep]", "", s(31547)),
        ("button", 203, s(31525), srun("setting", "max_volume"), f"$INFO[{P}(Sonos.MaxVolume)]", "", s(31548)),
        ("header", 290, s(31526)),
        REMOTE_VOLUME,
    ]),
    (s(31510), [
        ("button", 300, s(31536), srun("find_player"), S_HOST, "", s(31541)),
        ("button", 301, s(31537), srun("setting", "host"), S_HOST, "", s(31542)),
        ("button", 302, s(10140), f"Addon.OpenSettings({SONOS})", "", "", ""),
    ]),
]

PAGES = (
    (1132, "Custom_1132_LGTV.xml", s(31500), LGTV, "Bald_LGTVHelp", "$VAR[Bald_LGTVConnectionText]",
     f"$INFO[{P}(WebOS.Model)]", "service.webostv (LG webOS TV Control)"),
    (1133, "Custom_1133_Denon.xml", s(31501), DENON_PAGE, "Bald_DenonHelp", "$VAR[Bald_DenonConnectionText]",
     f"$INFO[{P}(Denon.Model),Denon ,]", "service.denonavr (Denon AVR Control)"),
    (1134, "Custom_1134_Sonos.xml", s(31502), SONOS_PAGE, "Bald_SonosHelp", "$VAR[Bald_SonosConnectionText]",
     f"$INFO[{P}(Sonos.Room)]", "service.sonos (Sonos Control)"),
)
PAGE_IDS = tuple(page[0] for page in PAGES)


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def row(r: tuple, item: int, t: str) -> str:
    """One row of category <item>: shown while that category is selected in the sidebar (list 9700)."""
    kind, cid = r[0], r[1]
    shown = f"Container(9700).HasFocus({item})"
    if kind == "note":
        return (f'{t}<control type="label" id="{cid}"><include>Bald_HomeTheaterNote</include>'
                f"<label>{esc(r[2])}</label><visible>{shown} + {r[3]}</visible></control>")
    if kind == "header":
        return (f'{t}<control type="label" id="{cid}"><include>Bald_SettingsGroupTitle</include>'
                f"<label>{esc(r[2])}</label><visible>{shown}</visible></control>")
    if kind == "button":
        _, _, label, onclick, label2, enable, _help, *more = r
        lines = [f'<control type="button" id="{cid}">', "\t<include>Bald_SettingsTemplate</include>",
                 f"\t<label>{esc(label)}</label>"]
        if label2:
            lines.append(f"\t<label2>{esc(label2)}</label2>")
        lines.append(f"\t<onclick>{esc(onclick)}</onclick>")
        visible = f"{shown} + {more[0]}" if more else shown
    else:
        _, _, label, selected, onclicks, enable, _help = r
        lines = [f'<control type="radiobutton" id="{cid}">', "\t<include>Bald_SettingsTemplate</include>",
                 f"\t<label>{esc(label)}</label>", f"\t<selected>{esc(selected)}</selected>"]
        for cond, action in onclicks:
            c = f' condition="{esc(cond)}"' if cond else ""
            lines.append(f"\t<onclick{c}>{esc(action)}</onclick>")
        visible = shown
    if enable:
        lines.append(f"\t<enable>{esc(enable)}</enable>")
    lines += [f"\t<visible>{esc(visible)}</visible>", "</control>"]
    return "\n".join(t + line for line in lines)


def page(window_id: int, name: str, title: str, categories: list, help_var: str, status: str, model: str,
         addon: str) -> str:
    ids = [r[1] for _l, rows in categories for r in rows]
    clashes = sorted({i for i in ids if ids.count(i) > 1} | ({60, 9700, 9800} & set(ids)))
    if clashes:
        raise SystemExit(f"{name}: duplicate control ids {clashes}")
    items = "\n".join(f'\t\t\t\t<item id="{i}"><label>{esc(label)}</label><onclick>SetFocus(9800)</onclick></item>'
                      for i, (label, _rows) in enumerate(categories, 1))
    rows = "\n".join(row(r, i, "\t\t\t") for i, (_l, rs) in enumerate(categories, 1) for r in rs)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- GENERATED by tools/home_theater.py; edit that and re-run. The {addon} page (Settings, {name[12:-4]}):
     categories in the sidebar, the selected one's rows at Kodi's settings pages' width with the focused row's help
     under them, and the device and its connection at the foot of the sidebar. -->
<window type="window" id="{window_id}">
	<include>Bald_CurtainHandoff</include>
	<defaultcontrol always="true">9700</defaultcontrol>
	<backgroundcolor>bald_field</backgroundcolor>
	<controls>
		<include content="Bald_SettingsFrame"><param name="title">{title}</param></include>
		<control type="list" id="9700">
			<include content="Bald_SettingsCategories"><param name="id">9700</param><param name="right">9800</param></include>
			<content>
{items}
			</content>
		</control>
		<include content="Bald_HomeTheaterStatus"><param name="model">{esc(model)}</param><param name="status">{status}</param></include>
		<control type="grouplist" id="9800">
			<include>Bald_HomeTheaterRows</include>
{rows}
		</control>
		<control type="scrollbar" id="60">
			<include>Bald_SettingsScrollbar</include>
			<onleft>9800</onleft>
		</control>
		<control type="textbox">
			<description>help for the focused row</description>
			<include>Bald_SettingsHelp</include>
			<label>$VAR[{help_var}]</label>
			<visible>ControlGroup(9800).HasFocus</visible>
		</control>
		<include content="Bald_SettingsHints"><param name="first">$VAR[Bald_KeyBack]$LOCALIZE[31738]</param><param name="second">$VAR[Bald_KeySelect]$LOCALIZE[31747]</param></include>
	</controls>
</window>
"""


# ============ OSD panels (1135 LG TV, 1136 the audio system) ============
# Panel rows: ("button", id, label, label2, onclick or [actions], visible[, (onleft, onright)])
#             ("radio", id, label, selected, onclick, visible)


def notify(addon: str, command: str) -> str:
    return f"NotifyAll({addon},{command})"


def more_settings(window_id: int) -> list[str]:
    """The device's settings page. The panel and the OSD under it close first, or the page would open beneath them."""
    return ["Dialog.Close(all,true)", f"ActivateWindow({window_id})"]


ADJUSTMENTS = (("backlight", 32500), ("hdrDynamicToneMapping", 32501), ("noiseReduction", 32502),
               ("mpegNoiseReduction", 32503), ("smoothGradation", 32504), ("superResolution", 32505),
               ("eyeComfortMode", 32506))  # OSD_ADJUSTMENTS in service.webostv's ui.py, each shown once reported


def lgtv_panel_rows() -> list[tuple]:
    def osd(key: str) -> str:
        return f"$INFO[{P}(WebOS.OSD.{key})]"

    return [
        ("button", 8201, w(32117), f"$INFO[{P}(WebOS.PicturePresetLabel)]", wrun("ui", "picture_preset"), ""),
        ("button", 8202, w(32430), osd("Motion"), wrun("ui", "motion"), ""),
        *(("button", 8203 + i, w(label), osd(key), wrun("ui", "adjust", key), f"!String.IsEmpty({P}(WebOS.OSD.{key}))")
          for i, (key, label) in enumerate(ADJUSTMENTS)),
        ("button", 8210, w(32102), f"$INFO[{P}(WebOS.SoundOutputLabel)]", wrun("ui", "sound_output"), ""),
        ("button", 8211, w(32432), "", ["Dialog.Close(all,true)", wrun("screen", "off")], ""),
        ("button", 8212, s(31552), "", more_settings(1132), ""),
    ]


def audio_panel_rows() -> list[tuple]:
    denon, sonos = "$EXP[Bald_SetupDenon]", "$EXP[Bald_SetupSonos]"
    on = f"{denon} + String.IsEqual({P}(Denon.Power),true)"
    return [
        ("button", 8221, s(31522), "$VAR[Bald_DenonSignalText]", "", on),
        ("button", 8222, s(31523), f"$INFO[{P}(Denon.SoundMode)]", "", on),
        ("button", 8223, s(14125), f"$INFO[{P}(Denon.InputName)]", "", on),
        ("button", 8225, s(13376), "$VAR[Bald_DenonVolumeText]", "", on,
         (notify(DENON, "volume_down"), notify(DENON, "volume_up"))),
        ("radio", 8226, s(31506), f"String.IsEqual({P}(Denon.Mute),true)", notify(DENON, "mute"), on),
        ("radio", 8227, s(33060), f"String.IsEqual({P}(Denon.Power),true)", notify(DENON, "power"), denon),
        ("button", 8228, s(31552), "", more_settings(1133), denon),
        ("button", 8229, s(31522), "$VAR[Bald_SonosFormatText]", "", sonos),
        ("button", 8230, s(13376), "$VAR[Bald_SonosVolumeText]", "", sonos,
         (notify(SONOS, "volume_down"), notify(SONOS, "volume_up"))),
        ("radio", 8231, s(31506), f"String.IsEqual({P}(Sonos.Mute),true)", notify(SONOS, "mute"), sonos),
        ("radio", 8232, s(31538), f"String.IsEqual({P}(Sonos.Night),true)", notify(SONOS, "night"),
         f"{sonos} + {shas('Night')}"),
        ("radio", 8233, s(31539), f"String.IsEqual({P}(Sonos.Speech),true)", notify(SONOS, "speech"),
         f"{sonos} + {shas('Speech')}"),
        ("button", 8234, s(31552), "", more_settings(1134), sonos),
    ]


# Window id, file, the panel's grouplist, its OSD button, the OSD row's slot, heading, rows, onload, comment.
OSD_PANELS = (
    (1135, "Custom_1135_OSDLGTV.xml", 8200, 70064, "lgtv", "$LOCALIZE[31500]$INFO[" + P + "(WebOS.Model), · ,]",
     lgtv_panel_rows, wrun("ui", "osd_values"),
     "LG TV (service.webostv): picture preset, motion and the picture settings the TV reports\n"
     "     for the preset in use, sound output, screen off. Each row opens the add-on's list for it; the add-on updates\n"
     "     the values when the pick is made, and when the panel opens for those the TV doesn't push."),
    (1136, "Custom_1136_OSDAudioSystem.xml", 8220, 70065, "receiver", "$VAR[Bald_OSDAudioHeading]",
     audio_panel_rows, "",
     "the audio system: Denon (service.denonavr: incoming audio, how it plays,\n"
     "     input, volume, mute, power) or Sonos (service.sonos: incoming audio, volume, mute, night mode, speech\n"
     "     enhancement). Left and Right on Volume turn it down and up; every row acts through NotifyAll, so the panel\n"
     "     stays open."),
)
OSD_PANEL_ROWS = 7  # rows on show; more scroll


def panel_row(r: tuple, owner: int, t: str) -> str:
    kind, cid, label = r[0], r[1], r[2]
    if kind == "button":
        _, _, _, label2, onclick, visible, *sides = r
        lines = [f'<control type="button" id="{cid}">', "\t<include>Bald_OSDHomeTheaterRow</include>",
                 f"\t<label>{esc(label)}</label>"]
        if label2:
            lines.append(f"\t<label2>{esc(label2)}</label2>")
        for action in ([onclick] if isinstance(onclick, str) else onclick):
            if action:
                lines.append(f"\t<onclick>{esc(action)}</onclick>")
        left, right = sides[0] if sides else (str(owner), str(owner))
    else:
        _, _, _, selected, onclick, visible = r
        lines = [f'<control type="radiobutton" id="{cid}">', "\t<include>Bald_OSDHomeTheaterRow</include>",
                 f"\t<label>{esc(label)}</label>", f"\t<selected>{esc(selected)}</selected>",
                 f"\t<onclick>{esc(onclick)}</onclick>"]
        left = right = str(owner)
    lines += [f"\t<onleft>{esc(left)}</onleft>", f"\t<onright>{esc(right)}</onright>"]
    if visible:
        lines.append(f"\t<visible>{esc(visible)}</visible>")
    lines.append("</control>")
    return "\n".join(t + line for line in lines)


def osd_panel(window_id: int, name: str, list_id: int, owner: int, slot: str, heading: str, rows, onload: str,
              comment: str) -> str:
    body = "\n".join(panel_row(r, owner, "\t\t\t\t\t") for r in rows())
    load = f"\n\t<onload>{onload}</onload>" if onload else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- GENERATED by tools/home_theater.py; edit that and re-run.
     Bald video OSD, {comment}
     A companion panel of the video OSD (docs/SPEC.md 5.16, "Video OSD"; Includes_Bald_OSD.xml): VideoOSD opens it when
     its button ({owner}) takes focus, and Up from the button enters it. The row is repeated with that button real and the
     others as stand-ins that close this panel and focus the OSD's own button. -->
<window type="dialog" id="{window_id}">
	<defaultcontrol always="true">{owner}</defaultcontrol>{load}
	<zorder>1</zorder>
	<depth>DepthOSD</depth>
	<controls>
		<control type="group">
			<include>Bald_OSDCompanionHide</include>
			<include content="Bald_OSDHomeTheaterPanel">
				<param name="heading">{esc(heading)}</param>
				<param name="list">{list_id}</param>
				<param name="owner">{owner}</param>
{body}
			</include>
			<include content="Bald_OSDCompanionRow">
				<param name="owner">{window_id}</param>
				<param name="{slot}">Panel</param>
			</include>
			<include>Bald_OSDHints</include>
		</control>
	</controls>
</window>
"""


# ============ Volume capsule (1137) ============

def volume_capsule() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<!-- GENERATED by tools/home_theater.py; edit that and re-run. The audio system's volume, shown for a moment whenever
     it changes (service.denonavr and service.sonos set Denon.VolumeShow / Sonos.VolumeShow for a few seconds): the TV
     remote's volume buttons through the Remote Bridge, the receiver's or player's own remote, its app. Kodi's volume
     bar's capsule and place (DialogVolumeBar.xml) with the device's icon and name and the volume at the right; muted,
     the volume reads "Muted". Kodi opens and closes it by its <visible>. -->
<window type="dialog" id="1137">
	<visible>$EXP[Bald_ReceiverVolumeShow] + !Window.IsActive(startup)</visible>
	<zorder>4</zorder>
	<controls>
		<control type="group">
			<centerleft>50%</centerleft>
			<width>420</width>
			<top>Bald_OverlayBandTop</top>
			<height>54</height>
			<include content="Bald_OverlayOpenClose">
				<param name="offset" value="0,-14" />
			</include>
			<include content="Bald_OverlaySurface">
				<param name="width" value="420" />
				<param name="height" value="54" />
				<param name="texture" value="bald/pill.png" />
				<param name="border" value="27" />
			</include>
			<control type="image">
				<left>22</left>
				<top>13</top>
				<width>28</width>
				<height>28</height>
				<aspectratio>keep</aspectratio>
				<texture colordiffuse="bald_ink">$VAR[Bald_ReceiverVolumeIcon]</texture>
			</control>
			<control type="label">
				<left>66</left>
				<top>0</top>
				<width>240</width>
				<height>54</height>
				<font>Bald_Progress</font>
				<textcolor>bald_ink</textcolor>
				<aligny>center</aligny>
				<label>$VAR[Bald_ReceiverVolumeName]</label>
			</control>
			<control type="label">
				<left>238</left>
				<top>0</top>
				<width>160</width>
				<height>54</height>
				<font>Bald_Progress</font>
				<textcolor>bald_ink60</textcolor>
				<align>right</align>
				<aligny>center</aligny>
				<label>$VAR[Bald_ReceiverVolumeValue]</label>
			</control>
		</control>
	</controls>
</window>
"""


def osd_includes() -> str:
    sonos_shows = f"$EXP[Bald_SetupSonos] + String.IsEqual({P}(Sonos.VolumeShow),true)"
    denon_shows = f"$EXP[Bald_SetupDenon] + String.IsEqual({P}(Denon.VolumeShow),true)"
    height = OSD_PANEL_ROWS * 64 - 8
    return f"""
	<!-- ============ OSD panels (1135 LG TV, 1136 the audio system) ============ -->
	<!-- The panel: a companion panel's field surface and heading (Bald_OSDPanelSurface) over the row, ending at the
	     right safe edge with its bottom at y 712, and the rows' grouplist <list> ({OSD_PANEL_ROWS} rows on show; more
	     scroll). Down from the last row returns to the OSD button <owner>. -->
	<include name="Bald_OSDHomeTheaterPanel">
		<param name="heading" />
		<param name="list" />
		<param name="owner" />
		<definition>
			<control type="group">
				<left>1104</left>
				<top>{712 - height - 104}</top>
				<width>720</width>
				<height>{height + 104}</height>
				<include>Bald_OSDAnimCompanion</include>
				<include>Bald_OSDCompanionHide</include>
				<include content="Bald_OSDPanelSurface"><param name="height">{height + 104}</param><param name="heading">$PARAM[heading]</param></include>
			</control>
			<!-- Its own top-level control: Kodi fills <nested /> only in an include's top-level controls and their
			     direct children (CGUIIncludes::InsertNested). -->
			<control type="grouplist" id="$PARAM[list]">
				<left>1120</left>
				<top>{712 - height - 16}</top>
				<width>688</width>
				<height>{height}</height>
				<orientation>vertical</orientation>
				<itemgap>8</itemgap>
				<scrolltime tween="cubic" easing="out">320</scrolltime>
				<usecontrolcoords>true</usecontrolcoords>
				<onup>noop</onup>
				<ondown>$PARAM[owner]</ondown>
				<include>Bald_OSDAnimCompanion</include>
				<include>Bald_OSDCompanionHide</include>
				<nested />
			</control>
		</definition>
	</include>
	<!-- A panel row: the video panel's row (8131) with the settings rows' radio dot at its end. -->
	<include name="Bald_OSDHomeTheaterRow">
		<width>688</width>
		<height>56</height>
		<font>Bald_Section</font>
		<textoffsetx>32</textoffsetx>
		<aligny>center</aligny>
		<textcolor>bald_ink70</textcolor>
		<focusedcolor>bald_ink</focusedcolor>
		<disabledcolor>bald_ink28</disabledcolor>
		<texturefocus border="12,0,0,0" colordiffuse="bald_accent">bald/menu_dot.png</texturefocus>
		<texturenofocus />
		<radioposx>644</radioposx>
		<radiowidth>12</radiowidth>
		<radioheight>12</radioheight>
		<textureradioonfocus colordiffuse="bald_accent">bald/dot.png</textureradioonfocus>
		<textureradioonnofocus colordiffuse="bald_accent">bald/dot.png</textureradioonnofocus>
		<textureradioofffocus colordiffuse="bald_ink34">bald/dot.png</textureradioofffocus>
		<textureradiooffnofocus colordiffuse="bald_ink28">bald/dot.png</textureradiooffnofocus>
		<textureradioondisabled colordiffuse="bald_ink28">bald/dot.png</textureradioondisabled>
		<textureradiooffdisabled colordiffuse="bald_ink10">bald/dot.png</textureradiooffdisabled>
	</include>
	<variable name="Bald_OSDAudioHeading">
		<value condition="$EXP[Bald_SetupSonos]">{s(31502)}$INFO[{P}(Sonos.Room), · ,]</value>
		<value>{s(31501)}$INFO[{P}(Denon.Model), · ,]</value>
	</variable>

	<!-- ============ Volume capsule (1137) ============ -->
	<!-- Sonos while it is the one that changed volume, else Denon. -->
	<expression name="Bald_ReceiverVolumeSonos">[{sonos_shows}]</expression>
	<expression name="Bald_ReceiverVolumeShow">[[{sonos_shows}] | [{denon_shows}]]</expression>
	<variable name="Bald_ReceiverVolumeIcon">
		<value condition="$EXP[Bald_ReceiverVolumeSonos]">bald/osd_sonos.png</value>
		<value>bald/osd_receiver.png</value>
	</variable>
	<variable name="Bald_ReceiverVolumeName">
		<value condition="$EXP[Bald_ReceiverVolumeSonos]">{s(31502)}</value>
		<value>{s(31501)}</value>
	</variable>
	<variable name="Bald_ReceiverVolumeValue">
		<value condition="$EXP[Bald_ReceiverVolumeSonos] + String.IsEqual({P}(Sonos.Mute),true)">{s(31650)}</value>
		<value condition="$EXP[Bald_ReceiverVolumeSonos]">$INFO[{P}(Sonos.Volume)]</value>
		<value condition="String.IsEqual({P}(Denon.Mute),true)">{s(31650)}</value>
		<value>$INFO[{P}(Denon.VolumeDisplay)]</value>
	</variable>"""


# ============ Pointer (Pointer.xml) ============
POINTER_DATA = "special://profile/addon_data/service.webostv/pointer"
POINTER_LOOK = f"{P}(WebOS.PointerLook)"
POINTER_ANIMATED = f"String.IsEqual({P}(WebOS.PointerAnimated),true)"
POINTER_LOOKS = ("down", "up", "downx", "upx", "end", "enter", "exit")
# Kodi's pointer states: control id, description, the add-on's image, the fallback.
POINTER_STATES = ((1, "Pointer", "point", "bald/pointer_arrow.png"), (2, "Pointer Focus", "hover", "bald/pointer_focus.png"),
                  (3, "Pointer Drag", "drag", "bald/pointer_arrow.png"), (4, "pointer_click", "hold", "bald/pointer_click.png"))


def pointer_image(texture: str, visible: str = "") -> str:
    lines = ['<control type="image">', "\t<left>-128</left>", "\t<top>-128</top>", "\t<width>256</width>",
             "\t<height>256</height>", f"\t{texture}"]
    if visible:
        lines.append(f"\t<visible>{esc(visible)}</visible>")
    lines.append("</control>")
    return "\n".join("\t\t" + line for line in lines)


def pointer_includes() -> str:
    """Each pointer state's images (Includes_Bald_HomeTheater.xml), which Pointer.xml includes only while the pointer is
    in use: Kodi loads pointer textures with the skin, hidden or not, and logs every missing one."""
    out = []
    for _cid, _description, kind, fallback in POINTER_STATES:
        still = f'<texture fallback="{fallback}">{POINTER_DATA}/{kind}.png</texture>'
        if kind in ("point", "hover"):
            parts = [pointer_image(still, f"String.IsEmpty({POINTER_LOOK})"),
                     *(pointer_image(f"<texture>{POINTER_DATA}/anim_{look}.apng</texture>",
                                     f"String.IsEqual({POINTER_LOOK},{look})") for look in POINTER_LOOKS)]
        elif kind == "hold":
            parts = [pointer_image(still, f"!{POINTER_ANIMATED}"),
                     pointer_image(f"<texture>{POINTER_DATA}/anim_press.apng</texture>", POINTER_ANIMATED)]
        else:
            parts = [pointer_image(still)]
        out.append(f'\t<include name="Bald_WebOSPointer_{kind}">\n' + "\n".join(parts) + "\n\t</include>")
    return "\n".join(out)


def pointer() -> str:
    states = "\n".join(
        f'\t\t<control type="group" id="{cid}">\n\t\t\t<description>{description}</description>\n'
        f'\t\t\t<include condition="$EXP[Bald_WebOSPointer]">Bald_WebOSPointer_{kind}</include>\n\t\t</control>'
        for cid, description, kind, _fallback in POINTER_STATES)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- GENERATED by tools/home_theater.py; edit that and re-run. Bald is remote-only and draws no pointer, but for the LG
     TV's Magic Remote through service.webostv's Remote Bridge (Bald_WebOSPointer): then the TV's own webOS pointer and
     its animations, which the add-on saves to its data folder, with Bald's webOS-style ones standing in. Kodi shows the
     group whose id is the pointer's state. The images are included only while the pointer is in use when the skin
     loads (Kodi loads pointer textures then, and logs each missing one), so turning the pointer on takes a skin reload,
     as the add-on's new pointer images do. -->
<window>
	<controls>
{states}
	</controls>
</window>
"""


# ============ Includes ============

def help_variable(name: str, categories: list) -> str:
    helps = [(r[1], r[6]) for _l, rows in categories for r in rows if r[0] in ("button", "radio") and r[6]]
    values = "\n".join(f'\t\t<value condition="Control.HasFocus({cid})">{esc(text)}</value>' for cid, text in helps)
    return f'\t<variable name="{name}">\n{values}\n\t</variable>'


def setting_labels(name: str, addon: str, key: str, labels: tuple, label=None) -> str:
    label = label or (lambda n: a(addon, n))
    values = "\n".join(
        f'\t\t<value condition="Integer.IsEqual(Addon.SettingInt({addon},{key}),{i})">{esc(label(n))}</value>'
        for i, n in enumerate(labels))
    return f'\t<variable name="{name}">\n{values}\n\t</variable>'


def lgtv_variables() -> str:
    def options(name: str, key: str, first: int, count: int) -> str:
        return setting_labels(name, WEBOS, key, tuple(range(first, first + count)))

    return "\n".join([
        f"""\t<variable name="Bald_LGTVConnectionText">
		<value condition="{W_CONNECTED}">{s(13296)}$INFO[{P}(WebOS.Host), · ]</value>
		<value>{s(15208)}</value>
	</variable>
	<variable name="Bald_LGTVKodiInput">
		<value condition="!String.IsEmpty({P}(WebOS.KodiInput))">$INFO[{P}(WebOS.KodiInput)]</value>
		<value>{w(32309)}</value>
	</variable>
	<variable name="Bald_LGTVKodiButtons">
		<value condition="!String.IsEmpty({P}(WebOS.KodiButtons))">$INFO[{P}(WebOS.KodiButtons)]</value>
		<value>{w(32696)}</value>
	</variable>
	<variable name="Bald_LGTVRemoteBridgeAction">
		<value condition="String.IsEqual({P}(WebOS.RemoteBridge),outdated)">{w(32636)}</value>
		<value>{w(32602)}</value>
	</variable>
	<variable name="Bald_LGTVRemoteBridge">
		<value condition="String.IsEqual({P}(WebOS.RemoteBridge),connected)">{w(32620)}$INFO[{P}(WebOS.Remote), · ]</value>
		<value condition="String.IsEqual({P}(WebOS.RemoteBridge),outdated)">{w(32620)}$INFO[{P}(WebOS.Remote), · ] · {w(32627)}</value>
		<value condition="String.IsEqual({P}(WebOS.RemoteBridge),waiting)">{w(32621)}</value>
		<value>{w(32622)}</value>
	</variable>""",
        setting_labels("Bald_LGTVOnTvOff", WEBOS, "on_tv_off", (32210, 32211, 32212, 32213)),
        setting_labels("Bald_LGTVOnSwitchAway", WEBOS, "on_switch_away", (32210, 32211, 32212)),
        options("Bald_LGTVMotionFilm", "motion_film", 32410, 5),
        options("Bald_LGTVMotionVideo", "motion_video", 32410, 5),
        options("Bald_LGTVMotionRestore", "motion_restore", 32410, 5),
        *(setting_labels(var, WEBOS, f"quality_{source}", QUALITY_LABELS.get(source, QUALITY_LEVEL_LABELS))
          for _cid, source, _l, _h, var, _c in QUALITY_SOURCES),
        *(setting_labels(f"Bald_LGTVQ_{source}_{short}", WEBOS, f"quality_{source}_{short}", values)
          for _cid, source, _l, _h, _v, _c in QUALITY_SOURCES for short, _sl, values in QUALITY_CUSTOM),
        options("Bald_LGTVSoundVideo", "sound_video", 32420, 6),
        options("Bald_LGTVSoundLiveTV", "sound_livetv", 32420, 6),
        options("Bald_LGTVSoundMusic", "sound_music", 32420, 6),
        options("Bald_LGTVPointerWake", "bridge_pointer_wake", 32640, 4),
        options("Bald_LGTVWheelSpeed", "bridge_wheel_speed", 32690, 4),
        options("Bald_LGTVPointerSpeed", "tv_pointer_speed", 32660, 3),
        options("Bald_LGTVPointerSize", "tv_pointer_size", 32663, 3),
        options("Bald_LGTVPointerShape", "tv_pointer_shape", 32666, 5),
    ])


def denon_variables() -> str:
    return "\n".join([f"""\t<variable name="Bald_DenonConnectionText">
		<value condition="{D_ON}">{s(13296)}$INFO[{P}(Denon.InputName), · ]</value>
		<value condition="{D_CONNECTED}">{s(13296)} · {s(31532)}</value>
		<value condition="String.IsEmpty({P}(Denon.Host))">{s(31520)}</value>
		<value>{s(15208)}</value>
	</variable>
	<variable name="Bald_DenonStatusText">
		<value condition="{D_ON}">$INFO[{P}(Denon.Model)]$INFO[{P}(Denon.Format), · ]</value>
		<value condition="{D_CONNECTED}">$INFO[{P}(Denon.Model)] · {s(31532)}</value>
		<value>{s(15208)}</value>
	</variable>
	<variable name="Bald_DenonSignalText">
		<value condition="!String.IsEmpty({P}(Denon.Signal))">$INFO[{P}(Denon.Signal)]</value>
		<value>{s(31535)}</value>
	</variable>
	<variable name="Bald_DenonVolumeText">
		<value condition="String.IsEqual({P}(Denon.Mute),true)">$INFO[{P}(Denon.VolumeDisplay)]$INFO[{P}(Denon.Volume), (, dB)] · {s(31506)}</value>
		<value>$INFO[{P}(Denon.VolumeDisplay)]$INFO[{P}(Denon.Volume), (, dB)]</value>
	</variable>""",
        setting_labels("Bald_DenonVolumeStep", DENON, "volume_step", ("0.5 dB", "1 dB", "2 dB"), label=str)])


def sonos_variables() -> str:
    return "\n".join([f"""\t<variable name="Bald_SonosConnectionText">
		<value condition="{S_CONNECTED}">{s(13296)}$INFO[{P}(Sonos.Model), · ]</value>
		<value condition="String.IsEmpty({P}(Sonos.Host))">{s(31536)}</value>
		<value>{s(15208)}</value>
	</variable>
	<variable name="Bald_SonosStatusText">
		<value condition="{S_CONNECTED}">$INFO[{P}(Sonos.Model)]$INFO[{P}(Sonos.Format), · ]</value>
		<value>{s(15208)}</value>
	</variable>
	<variable name="Bald_SonosSourceText">
		<value condition="String.IsEqual({P}(Sonos.TV),true)">{s(19020)}</value>
		<value>{s(31540)}</value>
	</variable>
	<variable name="Bald_SonosFormatText">
		<value condition="{shas('Format')}">$INFO[{P}(Sonos.Format)]</value>
		<value>{s(31535)}</value>
	</variable>
	<variable name="Bald_SonosVolumeText">
		<value condition="String.IsEqual({P}(Sonos.Mute),true)">$INFO[{P}(Sonos.Volume)] · {s(31506)}</value>
		<value>$INFO[{P}(Sonos.Volume)]</value>
	</variable>""",
        setting_labels("Bald_SonosVolumeStep", SONOS, "volume_step", ("1", "2", "5"), label=str)])


def includes() -> str:
    helps = "\n".join(help_variable(help_var, categories) for _i, _n, _t, categories, help_var, *_ in PAGES)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- GENERATED by tools/home_theater.py; edit that and re-run. Bald's home theater: the LG TV, Denon and Sonos
     add-ons (service.webostv, service.denonavr, service.sonos). Which are in use is chosen in Bald Settings,
     Playback, Home theater; the skin settings keep Estuary YBLOD's names, which service.webostv reads. -->
<includes>
	<!-- ============ Setup ============ -->
	<!-- The device is chosen and its add-on is enabled. -->
	<expression name="Bald_SetupLG">[Skin.HasSetting(setup_tv_lg) + System.AddonIsEnabled({WEBOS})]</expression>
	<expression name="Bald_SetupDenon">[Skin.HasSetting(setup_receiver_denon) + System.AddonIsEnabled({DENON})]</expression>
	<expression name="Bald_SetupSonos">[Skin.HasSetting(setup_receiver_sonos) + System.AddonIsEnabled({SONOS})]</expression>
	<expression name="Bald_SetupReceiver">[$EXP[Bald_SetupDenon] | $EXP[Bald_SetupSonos]]</expression>
	<!-- The LG TV's Magic Remote pointer is in use (Settings > LG TV > TV integration: Remote Bridge and its pointer on):
	     Kodi's mouse input stays on and Pointer.xml draws the TV's pointer. -->
	<expression name="Bald_WebOSPointer">[$EXP[Bald_SetupLG] + {BRIDGE_ON} + {POINTER_ON}]</expression>
	<!-- The choices' values (Custom_1119_BaldPlayback.xml), noting an add-on that is not installed. -->
	<variable name="Bald_SetupTVLabel">
		<value condition="Skin.HasSetting(setup_tv_lg) + !System.HasAddon({WEBOS})">{s(31556)} · {s(31557)}</value>
		<value condition="Skin.HasSetting(setup_tv_lg)">{s(31556)}</value>
		<value>{s(16018)}</value>
	</variable>
	<variable name="Bald_SetupReceiverLabel">
		<value condition="Skin.HasSetting(setup_receiver_denon) + !System.HasAddon({DENON})">{s(31501)} · {s(31557)}</value>
		<value condition="Skin.HasSetting(setup_receiver_denon)">{s(31501)}</value>
		<value condition="Skin.HasSetting(setup_receiver_sonos) + !System.HasAddon({SONOS})">{s(31502)} · {s(31557)}</value>
		<value condition="Skin.HasSetting(setup_receiver_sonos)">{s(31502)}</value>
		<value>{s(16018)}</value>
	</variable>

	<!-- ============ Pointer (Pointer.xml) ============ -->
{pointer_includes()}

	<!-- ============ Settings pages (1132 LG TV, 1133 Denon, 1134 Sonos) ============ -->
	<!-- The rows: Kodi's settings pages' grouplist (SettingsCategory.xml 5), Left back to the categories. -->
	<include name="Bald_HomeTheaterRows">
		<include>Bald_AnimSettingsWindow</include>
		<left>686</left>
		<top>192</top>
		<width>1106</width>
		<height>628</height>
		<orientation>vertical</orientation>
		<itemgap>6</itemgap>
		<scrolltime tween="cubic" easing="out">320</scrolltime>
		<usecontrolcoords>true</usecontrolcoords>
		<pagecontrol>60</pagecontrol>
		<onleft>9700</onleft>
		<onright>noop</onright>
		<onup>9800</onup>
		<ondown>9800</ondown>
	</include>
	<!-- A note over a category's rows (older webOS's picture presets), aligned with the row text. -->
	<include name="Bald_HomeTheaterNote">
		<width>1106</width>
		<height>84</height>
		<textoffsetx>26</textoffsetx>
		<aligny>center</aligny>
		<wrapmultiline>true</wrapmultiline>
		<font>Bald_MenuNote</font>
		<textcolor>bald_ink60</textcolor>
	</include>
	<!-- The device and its connection at the foot of the sidebar, where Bald's own pages have the settings level. -->
	<include name="Bald_HomeTheaterStatus">
		<param name="model" />
		<param name="status" />
		<definition>
			<control type="group">
				<include>Bald_AnimSettingsWindow</include>
				<control type="label">
					<left>122</left>
					<top>908</top>
					<width>372</width>
					<height>24</height>
					<aligny>center</aligny>
					<font>Bald_Hint</font>
					<textcolor>bald_ink45</textcolor>
					<label>$PARAM[model]</label>
				</control>
				<control type="label">
					<left>122</left>
					<top>938</top>
					<width>372</width>
					<height>56</height>
					<aligny>center</aligny>
					<font>Bald_Section</font>
					<textcolor>bald_ink60</textcolor>
					<label>$PARAM[status]</label>
				</control>
			</control>
		</definition>
	</include>
{osd_includes()}
{helps}
{lgtv_variables()}
{denon_variables()}
{sonos_variables()}
</includes>
"""


# ============ Strings ============

def po_block(uses: dict[int, set[str]]) -> str:
    """The en_gb entries for every string some window uses (a string nothing uses stays out of strings.po)."""
    entries = []
    for num, (text, note) in sorted(STRINGS.items()):
        if num not in uses:
            continue
        lines = [f"#: /1080i/{name}" for name in sorted(uses[num])]
        if note:
            lines.append(f"#. {note}")
        lines += [f'msgctxt "#{num}"', f'msgid "{text}"', 'msgstr ""']
        entries.append("\n".join(lines))
    return "\n\n".join(entries) + "\n\n"


def string_uses(outputs: dict[Path, str]) -> dict[int, set[str]]:
    uses: dict[int, set[str]] = {}
    for path in sorted(set(XML.glob("*.xml")) | {path for path in outputs if path.parent == XML}):
        text = outputs[path] if path in outputs else path.read_text(encoding="utf-8")
        for num in re.findall(r"\$LOCALIZE\[(\d+)\]", text):
            if int(num) in STRINGS:
                uses.setdefault(int(num), set()).add(path.name)
    return uses


def cite(entry: str, names: set[str]) -> str:
    """A strings.po entry with a "#: /1080i/<name>" source line for each of <names> (missing ones go after the
    entry's other source lines)."""
    lines = entry.split("\n")
    missing = [f"#: /1080i/{n}" for n in sorted(names) if f"#: /1080i/{n}" not in lines]
    at = next(i for i, line in enumerate(lines) if not line.startswith(("#: ", "\n")) and line.strip())
    while at < len(lines) and lines[at].startswith("#: "):
        at += 1
    return "\n".join(lines[:at] + missing + lines[at:])


def updated_po(text: str, block: str, generated: dict[int, set[str]]) -> str:
    """strings.po with the 31500-31596 entries replaced by <block> (entries are blank-line separated, in id order),
    and the generated windows cited by the other skin strings they show."""
    entries = text.split("\n\n")
    def num(entry: str) -> int | None:
        match = re.search(r'^msgctxt "#(\d+)"', entry, re.M)
        return int(match.group(1)) if match else None
    entries = [cite(e, generated[num(e)]) if num(e) in generated else e for e in entries]
    kept = [e for e in entries if not (num(e) is not None and FIRST_STRING <= num(e) <= LAST_STRING)]
    at = next(i for i, e in enumerate(kept) if num(e) is not None and num(e) > LAST_STRING)
    return "\n\n".join(kept[:at]) + "\n\n" + block + "\n\n".join(kept[at:])


def outputs() -> dict[Path, str]:
    files = {XML / name: page(window_id, name, title, categories, help_var, status, model, addon)
             for window_id, name, title, categories, help_var, status, model, addon in PAGES}
    for window_id, name, *rest in OSD_PANELS:
        files[XML / name] = osd_panel(window_id, name, *rest)
    files[XML / "Custom_1137_ReceiverVolume.xml"] = volume_capsule()
    files[XML / "Pointer.xml"] = pointer()
    files[XML / "Includes_Bald_HomeTheater.xml"] = includes()
    generated: dict[int, set[str]] = {}
    for path, text in files.items():
        for n in re.findall(r"\$LOCALIZE\[(\d+)\]", text):
            if 31000 <= int(n) <= 31999 and int(n) not in STRINGS:
                generated.setdefault(int(n), set()).add(path.name)
    files[PO] = updated_po(PO.read_text(encoding="utf-8"), po_block(string_uses(files)), generated)
    return files


def main(argv: list[str]) -> int:
    stale = []
    for path, text in outputs().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        if "--check" in argv:
            stale.append(path.relative_to(ROOT))
        else:
            path.write_text(text, encoding="utf-8")
            print(path.relative_to(ROOT))
    if stale:
        print("out of date (run python3 tools/home_theater.py):", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
