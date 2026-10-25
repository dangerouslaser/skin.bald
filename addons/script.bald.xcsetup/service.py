from __future__ import annotations

import datetime
import os
import xml.etree.ElementTree as ET

import xbmc
import xbmcaddon

from resources.lib.config import ConfigError
from resources.lib.refresh import ensure_daily_refresh, managed_instances, rebuild, refresh_hour, restart_iptv_simple


# Give the network a moment after login before the first XC request.
STARTUP_DELAY_SECONDS = 20
CHECK_SECONDS = 60


def _log(message: str, level: int = xbmc.LOGINFO) -> None:
    xbmc.log(f"script.bald.xcsetup service: {message}", level)


def _busy() -> bool:
    return xbmc.Player().isPlaying() or xbmc.getCondVisibility("PVR.IsRecording")


def _rebuild() -> bool:
    """Regenerate live.m3u. True when it changed. Failures are logged; the last good playlist stays."""
    try:
        changed, count = rebuild(xbmcaddon.Addon())
    except (ConfigError, OSError) as exc:
        _log(f"Playlist refresh failed: {exc}", xbmc.LOGWARNING)
        return False
    _log(f"Rebuilt playlist from {count} XC live streams ({'changed' if changed else 'unchanged'})")
    return changed


def _restart_when_idle(monitor: xbmc.Monitor) -> None:
    # Restarting IPTV Simple stops live playback, so wait until nothing is playing or recording.
    while _busy():
        if monitor.waitForAbort(CHECK_SECONDS):
            return
    try:
        restart_iptv_simple()
        _log("Restarted IPTV Simple to load the new channels and guide")
    except ConfigError as exc:
        _log(str(exc), xbmc.LOGWARNING)


def _startup(monitor: xbmc.Monitor, instances: list[str]) -> None:
    # IPTV Simple has usually loaded the previous playlist by now, so reload it when anything changed.
    needs_restart = False
    for path in instances:
        try:
            if ensure_daily_refresh(path):
                _log(f"Turned on daily refresh for {os.path.basename(path)}")
                needs_restart = True
        except (ET.ParseError, OSError) as exc:
            _log(f"Could not update {os.path.basename(path)}: {exc}", xbmc.LOGWARNING)
    if _rebuild() or needs_restart:
        _restart_when_idle(monitor)


def main() -> None:
    monitor = xbmc.Monitor()
    if monitor.waitForAbort(STARTUP_DELAY_SECONDS):
        return
    instances = managed_instances()
    if not instances:
        return  # Guided setup has not been applied; nothing to keep fresh.
    _startup(monitor, instances)
    last_daily = datetime.date.today()
    while not monitor.waitForAbort(CHECK_SECONDS):
        instances = managed_instances()
        if not instances:
            continue
        # Rebuild in the hour before IPTV Simple's daily refresh, which then rereads
        # the playlist and the XMLTV without a restart.
        now = datetime.datetime.now()
        if now.hour == (refresh_hour(instances[0]) - 1) % 24 and now.date() != last_daily:
            last_daily = now.date()
            _rebuild()


if __name__ == "__main__":
    main()
