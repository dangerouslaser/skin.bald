"""Bald Helper's keymap and the service that keeps it in step with the skin.

While Bald is the active skin and its setting Bald.ShowsOpenInfo is on, the keymap maps Select in the video library
(the <videos> section, MyVideoNav) to Skin.TimerStart(bald_library_select). Bald's timer of that name (1080i/Timers.xml)
opens a focused library TV show's information page and passes anything else on as Select. The keymap is removed under
any other skin, while the setting is off, and when the service stops.

Nothing here imports xbmc at module level, so the tests can drive it with stand-ins.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

ADDON_ID = "script.bald.helper"
SKIN_ID = "skin.bald"
SETTING = "Bald.ShowsOpenInfo"
TIMER = "bald_library_select"
ACTION = f"Skin.TimerStart({TIMER})"
KEYMAP_DIR = "special://profile/keymaps"
KEYMAP_FILE = "bald-helper.xml"
# Bald's retired TV guide Left override: the service deletes it when it starts (a no-op once gone), in place of
# the skin script the guide used to run on every open.
RETIRED_KEYMAP_FILES = ("bald-pvr.xml",)
POLL_SECONDS = 1.0

# The keys Kodi 22's default keymaps (system/keymaps) bind to Select in <global>, by device. CEC remotes arrive as
# <remote> buttons. "enter" is the keypad Enter; "return" the main one.
KEYBOARD_KEYS = ("return", "enter", "ok", "select")
REMOTE_KEYS = ("select",)
GAMEPAD_KEYS = ("A",)
JOYSTICK_PROFILE = "game.controller.default"
JOYSTICK_KEYS = ("a",)
# joystick.xml: a single press mapped in a section hides the global holdtime overload, so it is repeated here.
JOYSTICK_HOLDS = (("a", "500", "ContextMenu"),)


def build_keymap() -> str:
    """The keymap file's text (pure: the tests read it)."""
    root = ET.Element("keymap")
    videos = ET.SubElement(root, "videos")
    for device, keys in (("keyboard", KEYBOARD_KEYS), ("remote", REMOTE_KEYS), ("gamepad", GAMEPAD_KEYS)):
        section = ET.SubElement(videos, device)
        for key in keys:
            ET.SubElement(section, key).text = ACTION
    joystick = ET.SubElement(videos, "joystick", profile=JOYSTICK_PROFILE)
    for key in JOYSTICK_KEYS:
        ET.SubElement(joystick, key).text = ACTION
    for key, holdtime, action in JOYSTICK_HOLDS:
        ET.SubElement(joystick, key, holdtime=holdtime).text = action
    ET.indent(root, space="  ")
    comment = (
        "<!-- Written by Bald Helper (script.bald.helper) while Bald is the skin and \"Open TV shows on their info\n"
        "     page\" is on; removed otherwise. Do not edit: the add-on rewrites or deletes this file. -->\n"
    )
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + comment + ET.tostring(root, encoding="unicode") + "\n"


def wanted(skin_dir: str, setting_on: bool) -> bool:
    """Install the keymap only under Bald with its setting on."""
    return skin_dir == SKIN_ID and bool(setting_on)


class Service:
    """Polls the skin and the setting and writes or removes the keymap, reloading keymaps on each change."""

    def __init__(self, xbmc, xbmcvfs, keymap_dir: str | None = None):
        self.xbmc = xbmc
        self.keymap_dir = keymap_dir or xbmcvfs.translatePath(KEYMAP_DIR)
        self.path = os.path.join(self.keymap_dir, KEYMAP_FILE)
        self.content = build_keymap()
        self._last_error = None

    def log(self, message: str, level=None) -> None:
        self.xbmc.log(f"{ADDON_ID}: {message}", self.xbmc.LOGDEBUG if level is None else level)

    def current(self) -> str | None:
        try:
            with open(self.path, encoding="utf-8") as handle:
                return handle.read()
        except FileNotFoundError:
            return None

    def reload(self) -> None:
        self.xbmc.executebuiltin("Action(reloadkeymaps)")

    def install(self) -> bool:
        if self.current() == self.content:
            return False
        os.makedirs(self.keymap_dir, exist_ok=True)
        temporary = self.path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(self.content)
        os.replace(temporary, self.path)
        self.reload()
        self.log(f"installed {self.path}: Select on a TV show in the video library opens its info page",
                 self.xbmc.LOGINFO)
        return True

    def remove(self, reason: str) -> bool:
        try:
            os.remove(self.path)
        except FileNotFoundError:
            return False
        self.reload()
        self.log(f"removed {self.path} ({reason})", self.xbmc.LOGINFO)
        return True

    def remove_retired(self) -> bool:
        """Delete keymap files Bald no longer writes. Returns whether any was removed (then keymaps are reloaded)."""
        removed = []
        for name in RETIRED_KEYMAP_FILES:
            path = os.path.join(self.keymap_dir, name)
            try:
                os.remove(path)
            except FileNotFoundError:
                continue
            removed.append(path)
        if removed:
            self.reload()
            self.log(f"removed retired {', '.join(removed)}", self.xbmc.LOGINFO)
        return bool(removed)

    def sync(self) -> bool:
        """One check. Returns whether the keymap changed."""
        skin_dir = self.xbmc.getSkinDir()
        setting_on = bool(self.xbmc.getCondVisibility(f"Skin.HasSetting({SETTING})")) if skin_dir == SKIN_ID else False
        if wanted(skin_dir, setting_on):
            return self.install()
        return self.remove(f"skin {skin_dir}" if skin_dir != SKIN_ID else "setting off")

    def safe(self, step, *args) -> None:
        """Run a step without letting an error end the service; log each distinct error once."""
        try:
            step(*args)
            self._last_error = None
        except Exception as error:  # noqa: BLE001 - a service must outlive any single failure
            text = f"{type(error).__name__}: {error}"
            if text != self._last_error:
                self.log(text, self.xbmc.LOGERROR)
                self._last_error = text

    def run(self, monitor=None) -> None:
        monitor = monitor or self.xbmc.Monitor()
        self.log("started")
        try:
            self.safe(self.remove_retired)
            self.safe(self.sync)
            while not monitor.waitForAbort(POLL_SECONDS):
                self.safe(self.sync)
        finally:
            # Kodi exit, add-on disabled or uninstalled: never leave a keymap that points at Bald's timer.
            self.safe(self.remove, "service stopped")
            self.log("stopped")
