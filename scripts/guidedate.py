"""The day in the TV guide's corner (MyPVRGuide.xml, Bald_EpgGrid): the focused programme's short date, "9/30/2026".

RunScript(skin.bald,guidedate), from the guide's onload.

Kodi has no infolabel for a programme's date alone in the short form: ListItem.StartDate is the long regional date
("Wednesday, September 30, 2026", too long for the 178 px corner), and ListItem.Date is the short date with the start
time ("09/30/2026 2:00 PM"). While the guide is open, this keeps the date part of ListItem.Date, without leading zeros
and in the region's own order, in Window(home).Property(Bald.GuideDate), writing only when it changes. It stops when
the guide closes; a second start while one runs returns at once.
"""

import re

GUIDES = "Window.IsActive(tvguide) | Window.IsActive(radioguide)"
PROPERTY = "Bald.GuideDate"
RUNNING = "Bald.GuideDate.Running"
STEP = 0.3


def short_date(value):
    """ "09/30/2026 2:00 PM" -> "9/30/2026"; "30.09.2026 14:00" -> "30.9.2026". The first word, zeros dropped."""
    date = value.strip().split(" ")[0] if value.strip() else ""
    return re.sub(r"\b0+(\d)", r"\1", date)


def follow(xbmc, xbmcgui):
    home = xbmcgui.Window(10000)
    if home.getProperty(RUNNING):
        return
    home.setProperty(RUNNING, "1")
    monitor = xbmc.Monitor()
    shown = None
    try:
        # Kodi runs onload before the window counts as active: allow it a moment.
        for _ in range(10):
            if xbmc.getCondVisibility(GUIDES) or monitor.waitForAbort(0.1):
                break
        while xbmc.getCondVisibility(GUIDES):
            date = short_date(xbmc.getInfoLabel("ListItem.Date"))
            if date != shown:
                home.setProperty(PROPERTY, date)
                shown = date
            if monitor.waitForAbort(STEP):
                break
    finally:
        home.clearProperty(RUNNING)
        home.clearProperty(PROPERTY)
