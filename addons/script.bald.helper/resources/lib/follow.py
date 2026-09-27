"""Which item Bald is showing: shared by the blur follower (blur.py) and the ratings follower (ratings.py).

The skin names the container to follow in the Bald.FocusContainer property of the active window, or of the information
dialog while it is open (the include Bald_FollowContainer sets it). Without one, the item is the focused item of a media
window (Container.ListItem) or the information dialog's own item (ListItem). While a modal dialog other than the
information dialog is on top (context menu, select, keyboard, busy), what is shown is held.

Nothing here imports xbmc at module level, so the tests drive it with stand-ins.
"""

from __future__ import annotations

# A modal dialog other than the information dialog (context menu, select, keyboard, busy) is over the window: keep
# what is shown. Container(id) and ListItem resolve in the topmost modal dialog first, then the active window, so
# with nothing else modal on top they read the information dialog or the window below.
HOLD = "System.HasActiveModalDialog + !Window.IsModalDialogTopmost(movieinformation)"
INFO_DIALOG = "Window.IsModalDialogTopmost(movieinformation)"
MEDIA_WINDOW = "Window.IsMedia"
# The container to follow, read from a named window: the information dialog, else the active window (by id, as
# xbmcgui.getCurrentWindowId gives it; Global Search is a script window with an id of its own).
FOCUS_CONTAINER = "Window({}).Property(Bald.FocusContainer)"
INFO_WINDOW = "movieinformation"

# locate() returns HELD while a modal dialog is on top: keep what is shown.
HELD = object()


def follow_prefix(container_id: str, info_dialog: bool, media_window: bool) -> tuple[str | None, str | None]:
    """The infolabel prefix of the item to follow and its scrolling condition; (None, None) for nothing to follow."""
    container_id = container_id.strip()
    if container_id.isdigit():
        return f"Container({container_id}).ListItem.", f"Container({container_id}).Scrolling"
    if info_dialog:
        return "ListItem.", None
    if media_window:
        return "Container.ListItem.", "Container.Scrolling"
    return None, None


def locate(xbmc, current_window):
    """HELD, or (prefix, scrolling condition) of the item Bald shows now; (None, None) where there is none.
    `current_window` is a callable giving the active window's id (xbmcgui.getCurrentWindowId)."""
    if xbmc.getCondVisibility(HOLD):
        return HELD
    info = bool(xbmc.getCondVisibility(INFO_DIALOG))
    container_id = xbmc.getInfoLabel(FOCUS_CONTAINER.format(INFO_WINDOW if info else current_window()))
    media = False
    if not info and not container_id.strip().isdigit():
        media = bool(xbmc.getCondVisibility(MEDIA_WINDOW))
    return follow_prefix(container_id, info, media)
