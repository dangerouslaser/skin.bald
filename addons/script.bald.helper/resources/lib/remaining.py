"""Time left on the focused item, for the caption's progress line (Bald_Caption in 1080i/Includes_Bald_Home.xml).

Kodi gives a list item its runtime (ListItem.Duration(mins)) and how far it was watched (ListItem.PercentPlayed) but
not the time left, and a skin cannot do arithmetic. Each step of the service loop the Remaining step reads the item
Bald's background follows (follow.py, the same item as the blur and the caption) and publishes on Home:

    Bald.Remaining      "36m" or "1h 12m", the runtime not yet watched; empty unless the item is part way through
    Bald.Remaining.For  that item's ListItem.FileNameAndPath, so the caption shows the value only once it is the
                        focused item's (no stale time from the item before while focus moves)

PercentPlayed is a whole percent, so the value is good to about a minute. It is written only when it changes.

Nothing here imports xbmc at module level, so the tests drive it with stand-ins.
"""

from __future__ import annotations

from . import follow
from .common import SKIN_ID

PROPERTY = "Bald.Remaining"
PROPERTY_FOR = "Bald.Remaining.For"


def left(minutes: str, percent: str) -> str:
    """"119", "70" -> "36m"; "150", "20" -> "2h 0m"; "" unless both are whole numbers and 0 < percent < 100."""
    try:
        total, played = int(minutes), int(percent)
    except (TypeError, ValueError):
        return ""
    if total <= 0 or not 0 < played < 100:
        return ""
    rest = max(1, round(total * (100 - played) / 100))
    hours, mins = divmod(rest, 60)
    return f"{hours}h {mins}m" if hours else f"{mins}m"


class Remaining:
    def __init__(self, xbmc, window, current_window):
        self.xbmc = xbmc
        self.window = window                  # Home (10000), where the caption reads Bald.Remaining
        self.current_window = current_window  # xbmcgui.getCurrentWindowId, as the blur follower uses
        self.published = None

    def tick(self) -> None:
        """One step of the service loop."""
        if self.xbmc.getSkinDir() != SKIN_ID:
            return
        located = follow.locate(self.xbmc, self.current_window)
        if located is follow.HELD:
            return
        prefix, _scrolling = located
        value, item = "", ""
        if prefix is not None:
            value = left(self.xbmc.getInfoLabel(prefix + "Duration(mins)"), self.xbmc.getInfoLabel(prefix + "PercentPlayed"))
            item = self.xbmc.getInfoLabel(prefix + "FileNameAndPath") if value else ""
        if (value, item) == self.published:
            return
        self.published = (value, item)
        if value:
            self.window.setProperty(PROPERTY, value)
            self.window.setProperty(PROPERTY_FOR, item)  # after the value: the caption shows it once this matches
        else:
            self.window.clearProperty(PROPERTY_FOR)
            self.window.clearProperty(PROPERTY)
