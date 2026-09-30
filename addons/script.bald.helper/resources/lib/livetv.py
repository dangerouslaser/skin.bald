"""Live TV in Bald's Search: the channels and the programmes that match what was searched for.

Global Search (script.globalsearch) searches the libraries; its own Live TV option reads every channel's schedule
before it shows anything, and never looks at channel names. Bald's Search window (script-globalsearch.xml) lists these
two from Bald Helper's plugin instead, with Global Search's query (its window property GlobalSearch.SearchString):

    plugin://script.bald.helper/?info=livetv_channels&query=Q     channels whose name has Q, or whose number is Q
    plugin://script.bald.helper/?info=livetv_programmes&query=Q   programmes on now or later whose title has Q

Channels come from one PVR.GetChannels call per kind (TV, radio), with what is on now. Programmes need every channel's
schedule (PVR.GetBroadcasts, one call a channel), so the channels and their programmes' titles and times are kept in
DATA_DIR/livetv.json for CACHE_SECONDS and a second search in that time reads the file. Opening Search from Home
refreshes it in the background (?action=warm_livetv) while the query is typed. Nothing here imports xbmc at module level, so the tests drive it with
stand-ins.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from . import common

GROUPS = (("alltv", "tv"), ("allradio", "radio"))
CACHE_FILE = "livetv.json"
CACHE_SECONDS = 600
MAX_CHANNELS = 40
MAX_PROGRAMMES = 60
PROGRAMME_KEYS = ("title", "start", "end", "broadcast", "channel", "plot")
PLOT_CHARS = 300  # a preview shows about this much; the cache keeps no more
EPG_TIME = "%Y-%m-%d %H:%M:%S"  # PVR.GetBroadcasts' starttime and endtime, in UTC
NOW_LABEL = 19030  # Kodi's "Now"
SHORT_DAYS = 41    # Kodi's Mon, Tue ... Sun: 41 to 47


def channels(xbmc) -> list[dict]:
    """Every visible TV and radio channel: {id, name, number, logo, now, kind}."""
    found = []
    for group, kind in GROUPS:
        result = common.jsonrpc(xbmc, "PVR.GetChannels", {
            "channelgroupid": group, "properties": ["channelnumber", "thumbnail", "broadcastnow", "hidden"]})
        for channel in result.get("channels") or []:
            if not isinstance(channel, dict) or channel.get("hidden"):
                continue
            now = channel.get("broadcastnow") if isinstance(channel.get("broadcastnow"), dict) else {}
            found.append({"id": channel.get("channelid"), "name": str(channel.get("label") or ""),
                          "number": str(channel.get("channelnumber") or ""), "logo": str(channel.get("thumbnail") or ""),
                          "now": str(now.get("title") or ""), "kind": kind})
    return [c for c in found if isinstance(c["id"], int)]


def match_channels(found: list[dict], query: str) -> list[dict]:
    """Channels for a query: the one with that number first, then names that start with it, then names that have it."""
    query = query.strip().casefold()
    if not query:
        return []
    ranked = []
    for channel in found:
        name = channel["name"].casefold()
        if channel["number"] and channel["number"] == query:
            rank = 0
        elif name.startswith(query):
            rank = 1
        elif query in name:
            rank = 2
        else:
            continue
        ranked.append((rank, _number_key(channel["number"]), channel["name"].casefold(), channel))
    ranked.sort(key=lambda entry: entry[:3])
    return [entry[3] for entry in ranked[:MAX_CHANNELS]]


def _number_key(number: str):
    parts = number.replace("-", ".").split(".")
    return tuple(int(p) if p.isdigit() else 1 << 30 for p in parts)


def guide(xbmc, cache_dir: str | None = None, clock=time.time) -> tuple[list[dict], list[dict]]:
    """(channels, programmes) for the programme search. Programmes are {title, start, end, broadcast, channel, plot},
    start and end UTC EPG times, plots cut to PLOT_CHARS. Both from the cache when it is under CACHE_SECONDS old; the
    file keeps rows rather than keyed objects, to stay small (a few hundred channels' week is a few MB)."""
    path = os.path.join(cache_dir, CACHE_FILE) if cache_dir else None
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as handle:
                cached = json.load(handle)
            if cached.get("version") == 2 and clock() - cached.get("time", 0) < CACHE_SECONDS:
                return cached["channels"], [dict(zip(PROGRAMME_KEYS, row)) for row in cached["programmes"]]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    found = channels(xbmc)
    programmes = []
    for channel in found:
        result = common.jsonrpc(xbmc, "PVR.GetBroadcasts", {
            "channelid": channel["id"], "properties": ["title", "starttime", "endtime", "plot"]})
        for broadcast in result.get("broadcasts") or []:
            if not isinstance(broadcast, dict):
                continue
            title = str(broadcast.get("title") or broadcast.get("label") or "")
            if title and broadcast.get("starttime") and broadcast.get("endtime"):
                programmes.append({"title": title, "start": broadcast["starttime"], "end": broadcast["endtime"],
                                   "broadcast": broadcast.get("broadcastid"), "channel": channel["id"],
                                   "plot": str(broadcast.get("plot") or "")[:PLOT_CHARS]})
    if path:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"version": 2, "time": clock(), "channels": found,
                           "programmes": [[p[key] for key in PROGRAMME_KEYS] for p in programmes]},
                          handle, separators=(",", ":"))
        except OSError:
            pass
    return found, programmes


def _utc(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, EPG_TIME).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def match_programmes(programmes: list[dict], query: str, now: datetime) -> list[dict]:
    """Programmes whose title has the query and that have not ended, soonest first (what is on now leads). The EPG
    times sort as text, so only the matches' times are parsed."""
    query = query.strip().casefold()
    if not query:
        return []
    now_text = now.astimezone(timezone.utc).strftime(EPG_TIME)
    found = []
    for programme in programmes:
        if query not in programme["title"].casefold() or programme["end"] <= now_text:
            continue
        start, end = _utc(programme["start"]), _utc(programme["end"])
        if start and end:
            found.append((programme["start"], programme["title"].casefold(), programme, start, end))
    found.sort(key=lambda entry: entry[:2])
    return [dict(entry[2], start_time=entry[3], end_time=entry[4]) for entry in found[:MAX_PROGRAMMES]]


def when(start: datetime, end: datetime, now: datetime, time_format: str, now_label: str, day_name) -> str:
    """now_label for what is on, else the local start time, with the short day name when it is not today: "2:00 PM",
    "Thu 2:00 PM". time_format is Kodi's regional time format (xbmc.getRegion('time')), seconds dropped;
    day_name(weekday) is Kodi's short day name (0 Monday)."""
    if start <= now < end:
        return now_label
    local, today = start.astimezone(), now.astimezone()
    clock = local.strftime(time_format.replace(":%S", "")).strip()
    if "%I" in time_format:  # 12-hour clocks read "2:00 PM", not "02:00 PM"
        clock = clock.lstrip("0")
    if local.date() == today.date():
        return clock
    return f"{day_name(local.weekday())} {clock}"
