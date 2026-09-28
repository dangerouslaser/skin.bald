"""Bald's typeface and text size, kept across a lost lookandfeel.font or lookandfeel.skinzoom.

Bald Settings > Appearance > Typography (the skin's scripts/info.py, font and textsize actions) sets Kodi's
lookandfeel.font and lookandfeel.skinzoom and keeps a copy of each in a skin string, Bald.Fontset and Bald.TextSize.
Kodi loses a setting changed through JSON-RPC when it is killed or powered off before it saves its settings, and falls
back to the first fontset (DM Sans) when the stored id is not in Font.xml. Once per Kodi start, when Bald's Home is up
and nothing plays, the Keeper puts each copy back if it differs from the setting; Kodi then reloads the skin (a
fontset) or re-lays its windows (a zoom). After that one check it only follows: a value chosen elsewhere (Kodi's
Settings > Interface > Skin > Fonts or Zoom) is copied into the skin string, so a later start does not undo it.

Nothing here imports xbmc at module level, so the tests drive it with stand-ins.
"""

from __future__ import annotations

from .common import ADDON_ID, SKIN_ID, jsonrpc

# The moment to act: Bald's Home is showing and nothing is playing (a skin reload would interrupt nothing).
READY = "Window.IsVisible(home) + !Player.HasMedia"


class Fontset:
    """lookandfeel.font, one of Font.xml's fontset ids: DM Sans, Instrument Sans, Onest (whose id is Arial)."""

    name = "fontset"
    setting = "lookandfeel.font"
    skin_string = "Bald.Fontset"
    CHOICES = ("Default", "InstrumentSans", "Arial")

    def value(self, text):
        """The setting value a skin-string text stands for, or None for one Bald does not keep."""
        return text if text in self.CHOICES else None

    def current(self, xbmc) -> str:
        """The setting now, as skin-string text; Skin.Font is lookandfeel.font, and cheap to read every step."""
        return xbmc.getInfoLabel("Skin.Font")


class TextSize:
    """lookandfeel.skinzoom, Kodi's interface zoom in per cent (settings.xml allows -30 to 30). Bald's settings offer
    0, 4 and 8; any zoom in Kodi's range is kept, so one set in Kodi's own settings survives too."""

    name = "text size"
    setting = "lookandfeel.skinzoom"
    skin_string = "Bald.TextSize"
    LOWEST, HIGHEST = -30, 30

    def value(self, text):
        text = text.strip() if isinstance(text, str) else ""
        digits = text[1:] if text.startswith("-") else text
        if not (digits.isascii() and digits.isdigit()):
            return None
        zoom = int(text)
        return zoom if self.LOWEST <= zoom <= self.HIGHEST else None

    def current(self, xbmc) -> str:
        """No info label shows the zoom, so it is read through JSON-RPC (in-process, once a step)."""
        zoom = jsonrpc(xbmc, "Settings.GetSettingValue", {"setting": self.setting}).get("value")
        return str(zoom) if isinstance(zoom, int) and not isinstance(zoom, bool) else ""


KEPT = (Fontset(), TextSize())


class Keeper:
    def __init__(self, xbmc, kept=KEPT):
        self.xbmc = xbmc
        self.kept = kept
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

    def stored(self, kept) -> str:
        return self.xbmc.getInfoLabel(f"Skin.String({kept.skin_string})")

    def restore(self) -> None:
        """Put each skin string back into its setting when they differ. One failing does not stop the other; the
        first error is raised once both have been tried."""
        error = None
        for kept in self.kept:
            try:
                self.restore_one(kept)
            except Exception as failure:  # noqa: BLE001 - raised below, after the rest
                error = error or failure
        if error is not None:
            raise error

    def restore_one(self, kept) -> None:
        wanted = kept.value(self.stored(kept))
        if wanted is None:
            return
        current = jsonrpc(self.xbmc, "Settings.GetSettingValue", {"setting": kept.setting}, strict=True).get("value")
        if current == wanted:
            return
        jsonrpc(self.xbmc, "Settings.SetSettingValue", {"setting": kept.setting, "value": wanted}, strict=True)
        self.log(f"{kept.name} {current!r} restored to Bald's choice {wanted!r}")

    def follow(self) -> None:
        """Copy a value chosen outside Bald's settings into its skin string."""
        for kept in self.kept:
            current = kept.value(kept.current(self.xbmc))
            if current is not None and current != kept.value(self.stored(kept)):
                self.xbmc.executebuiltin(f"Skin.SetString({kept.skin_string},{current})")
