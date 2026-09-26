"""Small, local-library bridges for the native video-info dialog (Kodi 22).

RunScript(skin.bald,recommendations,movie,123)
RunScript(skin.bald,open,movie,456)
RunScript(skin.bald,tvinfo,episode,789)
RunScript(skin.bald,play,episode,789)
No network requests, library writes, or long-running service.
"""
import json
import sys
import time
import uuid
from urllib.parse import quote


MEDIA = {
    "movie": ("VideoLibrary.GetMovieDetails", "movieid", "moviedetails", "movies"),
    "tvshow": ("VideoLibrary.GetTVShowDetails", "tvshowid", "tvshowdetails", "tvshows"),
}
TV_TYPES = ("tvshow", "season", "episode")
# Native lists in Includes_Bald_InfoTV.xml, and the primary actions shown for an opened episode.
SEASONS, EPISODES = 5301, 5302
EPISODE_ACTIONS = "Control.HasFocus(5001) | Control.HasFocus(5002)"
# Text this script shows, as string ids: Kodi core (Resume, Play) and Bald's en_gb strings.po block. In Kodi the
# ids resolve through xbmc.getLocalizedString; the en_gb wording here is the default when no Kodi is present.
RESUME, PLAY, ONE_SEASON, SEASONS_WORD, YEARS_TO = 13404, 208, 31711, 31712, 31719
STRINGS = {RESUME: "Resume", PLAY: "Play", ONE_SEASON: "1 season", SEASONS_WORD: "seasons", YEARS_TO: "to"}


def recommendation_path(media_type, title, genres):
    """Encode the whole JSON value; builtin argument escaping is not URL encoding."""
    if media_type not in MEDIA or not genres:
        return ""
    library = MEDIA[media_type][3]
    playlist = {
        "type": library,
        "rules": {"and": [
            {"field": "genre", "operator": "is", "value": [genres[0]]},
            {"field": "title", "operator": "isnot", "value": [title]},
        ]},
        "order": {"direction": "descending", "method": "rating"},
    }
    return "videodb://{}/titles/?xsp={}".format(
        library, quote(json.dumps(playlist, ensure_ascii=False, separators=(",", ":")), safe="")
    )


def get_details(xbmc, media_type, dbid, properties):
    method, key, result_key, _ = MEDIA[media_type]
    response = json.loads(xbmc.executeJSONRPC(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method,
        "params": {key: dbid, "properties": properties},
    })))
    if "error" in response:
        raise RuntimeError("Library lookup failed: {}".format(response["error"]))
    return response["result"][result_key]


def recommendation_subject(xbmc, media_type, dbid):
    """Return the movie/show whose genre should drive related library titles."""
    if media_type in MEDIA:
        return media_type, get_details(xbmc, media_type, dbid, ["title", "genre"])
    if media_type != "episode":
        return "", {}
    response = json.loads(xbmc.executeJSONRPC(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.GetEpisodeDetails",
        "params": {"episodeid": dbid, "properties": ["tvshowid"]},
    })))
    if "error" in response:
        raise RuntimeError("Episode parent lookup failed: {}".format(response["error"]))
    tvshowid = response["result"]["episodedetails"].get("tvshowid", 0)
    if not isinstance(tvshowid, int) or tvshowid <= 0:
        return "", {}
    return "tvshow", get_details(xbmc, "tvshow", tvshowid, ["title", "genre"])


def rpc(xbmc, method, params):
    response = json.loads(xbmc.executeJSONRPC(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    })))
    if "error" in response:
        raise RuntimeError("{} failed: {}".format(method, response["error"]))
    return response["result"]


def episode_order(episode):
    return episode.get("season", 0), episode.get("episode", 0)


def is_resumable(episode):
    return episode.get("resume", {}).get("position", 0) > 0


def next_episode(episodes):
    """The episode the show's primary action plays, and whether it resumes.

    The most recently played episode resumes if it is in progress; otherwise the next unwatched episode after it,
    then the first unwatched one, then the first episode (a finished show starts again). Specials only count when
    a show has nothing else."""
    regular = sorted((e for e in episodes if e.get("season", 0) > 0), key=episode_order)
    regular = regular or sorted(episodes, key=episode_order)
    if not regular:
        return None, False
    unwatched = [e for e in regular if not e.get("playcount")]
    played = [e for e in regular if e.get("lastplayed")]
    candidate = None
    if played:
        latest = max(played, key=lambda e: e["lastplayed"])
        if is_resumable(latest):
            return latest, True
        candidate = next((e for e in unwatched if episode_order(e) > episode_order(latest)), None)
    candidate = candidate or (unwatched[0] if unwatched else regular[0])
    return candidate, is_resumable(candidate)


def action_label(episode, resume, text=STRINGS.get):
    return "{} S{} E{}".format(text(RESUME if resume else PLAY), episode.get("season", 0), episode.get("episode", 0))


def years_label(first_year, episodes, text=STRINGS.get):
    aired = [int(e["firstaired"][:4]) for e in episodes if str(e.get("firstaired", ""))[:4].isdigit()]
    start = first_year or (min(aired) if aired else 0)
    if not start:
        return ""
    end = max(aired) if aired else start
    return str(start) if end <= start else "{} {} {}".format(start, text(YEARS_TO), end)


def tv_meta(years, seasons, rating, text=STRINGS.get):
    """The "years, N seasons, rating" header line (docs/SPEC.md 5.3), skipping what the library lacks."""
    parts = [years] if years else []
    if seasons > 0:
        parts.append(text(ONE_SEASON) if seasons == 1 else "{} {}".format(seasons, text(SEASONS_WORD)))
    if rating:
        parts.append(rating)
    return ", ".join(parts)


def tv_subject(xbmc, media_type, dbid):
    """Return (tvshowid, season, episodeid) for a TV info item; season is None for a show."""
    if media_type == "tvshow":
        return dbid, None, 0
    if media_type == "season":
        details = rpc(xbmc, "VideoLibrary.GetSeasonDetails", {
            "seasonid": dbid, "properties": ["tvshowid", "season"]})["seasondetails"]
        episodeid = 0
    else:
        details = rpc(xbmc, "VideoLibrary.GetEpisodeDetails", {
            "episodeid": dbid, "properties": ["tvshowid", "season"]})["episodedetails"]
        episodeid = dbid
    tvshowid, season = details.get("tvshowid", 0), details.get("season")
    if not isinstance(tvshowid, int) or tvshowid <= 0 or not isinstance(season, int):
        return 0, None, 0
    return tvshowid, season, episodeid


def tv_publish(xbmc, window, identity, media_type, dbid):
    """Publish the show header and next-episode action; return (season, episodeid) to open the rows on."""
    tvshowid, season, episodeid = tv_subject(xbmc, media_type, dbid)
    if tvshowid <= 0:
        return None
    show = rpc(xbmc, "VideoLibrary.GetTVShowDetails", {
        "tvshowid": tvshowid, "properties": ["title", "year", "genre", "plot", "mpaa", "season"]})["tvshowdetails"]
    episodes = rpc(xbmc, "VideoLibrary.GetEpisodes", {
        "tvshowid": tvshowid,
        "properties": ["season", "episode", "playcount", "resume", "lastplayed", "firstaired"]}).get("episodes", [])
    upcoming, resume = next_episode(episodes)
    # The dialog may have been replaced while the library answered.
    if window.getProperty("Bald.Identity") != identity:
        return None
    years = years_label(show.get("year", 0), episodes, xbmc.getLocalizedString)
    window.setProperty("Bald.TV.ShowID", str(tvshowid))
    window.setProperty("Bald.TV.Title", show.get("title", ""))
    window.setProperty("Bald.TV.Years", years)
    window.setProperty("Bald.TV.Meta", tv_meta(years, show.get("season", 0), show.get("mpaa", ""), xbmc.getLocalizedString))
    window.setProperty("Bald.TV.Genre", " / ".join(show.get("genre", [])))
    window.setProperty("Bald.TV.Plot", show.get("plot", ""))
    if upcoming:
        window.setProperty("Bald.TV.NextLabel", action_label(upcoming, resume, xbmc.getLocalizedString))
        window.setProperty("Bald.TV.NextID", str(upcoming["episodeid"]))
    # A show opens on the next episode's season at its first episode (prototype); a season or episode on itself.
    if season is None:
        season = upcoming["season"] if upcoming else None
    return None if season is None else (season, episodeid)


def tv_position(xbmc, window, identity, season, episodeid, focus_episode, timeout=5.0):
    """Select the season tab and episode once the native lists have loaded; optionally focus the episode.

    One bounded wait per dialog open that reads the lists' own items (no library query), and gives up quietly if
    the dialog is replaced or closed. A fresh fixedlist starts on its focus position (docs/NOTES.md milestone 2),
    so the episode row is always moved explicitly."""
    monitor = xbmc.Monitor()
    deadline = time.monotonic() + timeout
    label = xbmc.getInfoLabel

    def alive():
        return (window.getProperty("Bald.Identity") == identity
                and xbmc.getCondVisibility("Window.IsVisible(movieinformation)"))

    def settle(ready):
        while not ready():
            if not alive() or time.monotonic() >= deadline or monitor.waitForAbort(0.02):
                return False
        return alive()

    def count(c):
        value = label("Container({}).NumItems".format(c))
        return int(value) if value.isdecimal() else 0

    def loaded(c):
        return count(c) > 0 and not xbmc.getCondVisibility("Container({}).IsUpdating".format(c))

    def item(c, index, field):
        return label("Container({}).ListItemAbsolute({}).{}".format(c, index, field))

    def find(c, field, value):
        return next((i for i in range(count(c)) if item(c, i, field) == value), None)

    def select(c, index):
        current = label("Container({}).CurrentItem".format(c))
        current = int(current) - 1 if current.isdecimal() else 0
        if index != current:
            xbmc.executebuiltin("Control.Move({},{})".format(c, index - current))
        return settle(lambda: label("Container({}).CurrentItem".format(c)) == str(index + 1))

    target = str(season)
    if not settle(lambda: loaded(SEASONS)):
        return False
    tab = find(SEASONS, "Season", target)
    if tab is None or not select(SEASONS, tab):
        return False
    # The episode row follows the selected tab; wait until it holds only that season (not stale or All seasons).
    if not settle(lambda: loaded(EPISODES) and item(EPISODES, 0, "Season") == target
                  and item(EPISODES, count(EPISODES) - 1, "Season") == target):
        return False
    index = find(EPISODES, "DBID", str(episodeid)) if episodeid else None
    if not select(EPISODES, index or 0):
        return False
    # Down from the tabs keeps this selection until the season changes (Includes_Bald_InfoTV.xml).
    window.setProperty("Bald.TV.RowFor", str(tab + 1))
    if focus_episode and xbmc.getCondVisibility(EPISODE_ACTIONS):
        xbmc.executebuiltin("SetFocus({})".format(EPISODES))
    return True


def play_episode(xbmc, episodeid):
    """Close info as Kodi's own Play does, then play (resuming) through the local player API."""
    if xbmc.getCondVisibility("Window.IsVisible(movieinformation)"):
        xbmc.executebuiltin("Dialog.Close(movieinformation)", wait=True)
        monitor = xbmc.Monitor()
        deadline = time.monotonic() + 3
        while xbmc.getCondVisibility("Window.IsVisible(movieinformation)"):
            if time.monotonic() >= deadline or monitor.waitForAbort(0.02):
                return
    rpc(xbmc, "Player.Open", {"item": {"episodeid": episodeid}, "options": {"resume": True}})


def make_item(xbmc, xbmcgui, media_type, dbid, details):
    item = xbmcgui.ListItem(label=details["title"], path=details["file"], offscreen=True)
    item.setIsFolder(media_type == "tvshow")
    item.setArt(details.get("art", {}))
    tag = item.getVideoInfoTag()
    tag.setDbId(dbid)
    tag.setMediaType(media_type)
    tag.setTitle(details["title"])
    tag.setPlot(details.get("plot", ""))
    tag.setYear(details.get("year", 0))
    tag.setGenres(details.get("genre", []))
    tag.setDirectors(details.get("director", []))
    tag.setStudios(details.get("studio", []))
    tag.setMpaa(details.get("mpaa", ""))
    tag.setPlaycount(details.get("playcount", 0))
    tag.setRating(details.get("rating", 0))
    tag.setDateAdded(details.get("dateadded", ""))
    tag.setCast([xbmc.Actor(actor["name"], actor.get("role", ""),
                             actor.get("order", -1), actor.get("thumbnail", ""))
                 for actor in details.get("cast", [])])
    if media_type == "movie":
        tag.setFilenameAndPath(details["file"])
        tag.setDuration(details.get("runtime", 0))
        tag.setWriters(details.get("writer", []))
        tag.setTagLine(details.get("tagline", ""))
        tag.setTrailer(details.get("trailer", ""))
        resume = details.get("resume", {})
        tag.setResumePoint(resume.get("position", 0), resume.get("total", 0))
        streams = details.get("streamdetails", {})
        for stream in streams.get("video", []):
            tag.addVideoStream(xbmc.VideoStreamDetail(
                width=stream.get("width", 0), height=stream.get("height", 0),
                aspect=stream.get("aspect", 0), duration=stream.get("duration", 0),
                codec=stream.get("codec", ""), hdrtype=stream.get("hdrtype", "")))
        for stream in streams.get("audio", []):
            tag.addAudioStream(xbmc.AudioStreamDetail(
                channels=stream.get("channels", 0), codec=stream.get("codec", ""),
                language=stream.get("language", "")))
        for stream in streams.get("subtitle", []):
            tag.addSubtitleStream(xbmc.SubtitleStreamDetail(language=stream.get("language", "")))
    else:
        tag.setPath(details["file"])
        item.setProperty("TotalSeasons", str(details.get("season", 0)))
    return item


def run(action="", media_type="", dbid=""):
    import xbmc
    import xbmcgui

    if action == "letters":
        from letters import publish
        publish(xbmc, xbmcgui, media_type)
        return

    identity = "{}:{}".format(media_type, dbid)
    window = xbmcgui.Window(12003)
    valid_id = dbid.isdecimal() and int(dbid) > 0
    if action == "tvinfo":
        if media_type not in TV_TYPES or not valid_id or window.getProperty("Bald.Identity") != identity:
            return
        target = tv_publish(xbmc, window, identity, media_type, int(dbid))
        if target:
            tv_position(xbmc, window, identity, target[0], target[1], media_type == "episode")
        return
    if action == "play":
        if media_type != "episode" or not valid_id or not xbmc.getCondVisibility("Window.IsActive(movieinformation)"):
            return
        home = xbmcgui.Window(10000)
        # Repeat Select while info closes must not start a second playback.
        if home.getProperty("Bald.InfoPlay"):
            return
        token = uuid.uuid4().hex
        home.setProperty("Bald.InfoPlay", token)
        try:
            play_episode(xbmc, int(dbid))
        finally:
            if home.getProperty("Bald.InfoPlay") == token:
                home.clearProperty("Bald.InfoPlay")
        return
    if action == "recommendations":
        if window.getProperty("Bald.Identity") != identity:
            return
        # Publish the dialog's art without putting paths through builtin argument parsing.
        fanart = next((value for value in (
            xbmc.getInfoLabel("ListItem.Art(fanart)"),
            xbmc.getInfoLabel("ListItem.Art(tvshow.fanart)"),
            xbmc.getInfoLabel("ListItem.Art(thumb)"),
        ) if value), "")
        window.setProperty("Bald.Fanart", fanart)
        window.setProperty("Bald.ArtIdentity", identity)
        if media_type not in (*MEDIA, "episode") or not dbid.isdecimal() or int(dbid) <= 0:
            return
        subject_type, details = recommendation_subject(xbmc, media_type, int(dbid))
        # A slow lookup from the previous item must not replace the new item's list.
        if (xbmc.getCondVisibility("Window.IsVisible(movieinformation)")
                and window.getProperty("Bald.Identity") == identity):
            window.setProperty("Bald.MoreFor", details.get("title", ""))
            window.setProperty("Bald.MorePath", recommendation_path(
                subject_type, details.get("title", ""), details.get("genre", [])))
        return
    if action != "open" or not xbmc.getCondVisibility("Window.IsActive(movieinformation)"):
        return
    if media_type not in MEDIA or not dbid.isdecimal() or int(dbid) <= 0:
        return

    home = xbmcgui.Window(10000)
    # Suppress repeat Select while fetching and exchanging the native dialog.
    if home.getProperty("Bald.InfoSwitch"):
        return
    token = uuid.uuid4().hex
    home.setProperty("Bald.InfoSwitch", token)
    origin = window.getProperty("Bald.Identity")
    try:
        properties = ["title", "file", "art", "plot", "year", "genre",
                      "studio", "mpaa", "playcount", "rating", "dateadded", "cast"]
        properties += (["director", "runtime", "writer", "tagline", "trailer", "resume", "streamdetails"]
                       if media_type == "movie" else ["season"])
        details = get_details(xbmc, media_type, int(dbid), properties)
        item = make_item(xbmc, xbmcgui, media_type, int(dbid), details)
        if (not xbmc.getCondVisibility("Window.IsActive(movieinformation)")
                or window.getProperty("Bald.Identity") != origin):
            return
        xbmc.executebuiltin("Dialog.Close(movieinformation)", wait=True)
        monitor = xbmc.Monitor()
        deadline = time.monotonic() + 3
        while xbmc.getCondVisibility("Window.IsVisible(movieinformation)"):
            if time.monotonic() >= deadline or monitor.waitForAbort(0.02):
                return
        # Home remains zoomed during the exchange. Onload releases this guard.
        xbmcgui.Dialog().info(item)
    finally:
        if home.getProperty("Bald.InfoSwitch") == token:
            home.clearProperty("Bald.InfoSwitch")


if __name__ == "__main__":
    try:
        run(*sys.argv[1:])
    except Exception as error:
        import xbmc
        xbmc.log("Bald info: {}".format(error), xbmc.LOGERROR)
