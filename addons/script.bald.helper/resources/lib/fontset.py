"""Bald's typeface choice, kept across a lost lookandfeel.font.

Bald Settings > Appearance > Typography (the skin's scripts/info.py, font action) sets Kodi's lookandfeel.font and
keeps a copy in Skin.String(Bald.Fontset). Kodi loses the setting when it is killed or powered off before it saves
its settings, and falls back to the first fontset (DM Sans) when the stored id is not in Font.xml. Once per Kodi start,
when Bald's Home is up and nothing plays, the Keeper puts the copy back if the two differ; Kodi then reloads the skin.
After that one check it only follows: a fontset chosen elsewhere (Kodi's Settings > Interface > Skin > Fonts) is
copied into Bald.Fontset, so a later start does not undo it.

Nothing here imports xbmc at module level, so the tests drive it with stand-ins.
"""

from __future__ import annotations

from .common import ADDON_ID, SKIN_ID, jsonrpc

SETTING = "lookandfeel.font"
SKIN_STRING = "Bald.Fontset"
# Font.xml's fontset ids: DM Sans, Instrument Sans, Onest (whose id is Arial).
FONTSETS = ("Default", "InstrumentSans", "Arial")
# The moment to act: Bald's Home is showing and nothing is playing (a skin reload would interrupt nothing).
READY = "Window.IsVisible(home) + !Player.HasMedia"


class Keeper:
    def __init__(self, xbmc):
        self.xbmc = xbmc
        self.checked = False  # the start-up check has run; it never runs twice in one Kodi session

    def log(self, message: str) -> None:
        self.xbmc.log(f"{ADDON_ID}: {message}", self.xbmc.LOGINFO)

    def tick(self) -> None:
        """One step of the service loop."""
        if self.xbmc.getSkinDir() != SKIN_ID:
            return
        if not self.checked:
            if self.xbmc.getCondVisibility(READY):
                self.checked = True  # before acting, so an error or the reload it causes cannot repeat it
                self.restore()
            return
        self.follow()

    def restore(self) -> None:
        """Put Bald.Fontset back into lookandfeel.font when they differ."""
        wanted = self.xbmc.getInfoLabel(f"Skin.String({SKIN_STRING})")
        if wanted not in FONTSETS:
            return
        current = jsonrpc(self.xbmc, "Settings.GetSettingValue", {"setting": SETTING}, strict=True).get("value")
        if current == wanted:
            return
        jsonrpc(self.xbmc, "Settings.SetSettingValue", {"setting": SETTING, "value": wanted}, strict=True)
        self.log(f"fontset {current!r} restored to Bald's choice {wanted!r}")

    def follow(self) -> None:
        """Copy a fontset chosen outside Bald's settings into Bald.Fontset (Skin.Font is lookandfeel.font)."""
        current = self.xbmc.getInfoLabel("Skin.Font")
        if current in FONTSETS and current != self.xbmc.getInfoLabel(f"Skin.String({SKIN_STRING})"):
            self.xbmc.executebuiltin(f"Skin.SetString({SKIN_STRING},{current})")
