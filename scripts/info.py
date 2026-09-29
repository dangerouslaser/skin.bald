"""Small, local-library bridges for the native video-info dialog (Kodi 22).

RunScript(skin.bald,recommendations,movie,123)
RunScript(skin.bald,open,movie,456)
RunScript(skin.bald,tvinfo,episode,789)
RunScript(skin.bald,play,episode,789)
RunScript(skin.bald,seriesmeta)  (library Series page, view 532)
RunScript(skin.bald,font,InstrumentSans)
RunScript(skin.bald,textsize,8)
RunScript(skin.bald,hubs)  (one-time Home hubs migration, see hubs.py)
RunScript(skin.bald,recommended[,prompt])  (Kodi settings Bald recommends, see recommended.py)
No network requests or library writes.

Bald Helper (addons/script.bald.helper) runs the latency-sensitive actions in its resident service instead: the skin
sends NotifyAll(skin.bald,bald.<action>|<type>|<id>) and the service calls handle() below, the same code RunScript
runs, with a `cancelled` check so a newer request ends a wait early. SERVICE_API tells the helper which calls this
file offers; the helper advertises itself to the skin only when it can load them.
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
# The library Series page (View_521_Bald_TV_Alternates.xml): the seasons view list in the video library window.
SERIES_PAGE, VIDEO_NAV = 532, 10025
# Windows whose episode rows play through RunScript(skin.bald,play,episode,<id>).
PLAY_WINDOWS = "Window.IsActive(movieinformation) | Window.IsActive(videos)"
# Text this script shows, as string ids: Kodi core (Resume, Play) and Bald's en_gb strings.po block. In Kodi the
# ids resolve through xbmc.getLocalizedString; the en_gb wording here is the default when no Kodi is present.
RESUME, PLAY, ONE_SEASON, SEASONS_WORD, YEARS_TO = 13404, 208, 31711, 31712, 31719
STRINGS = {RESUME: "Resume", PLAY: "Play", ONE_SEASON: "1 season", SEASONS_WORD: "seasons", YEARS_TO: "to"}
# Bald Helper's contract with this file: handle(xbmc, xbmcgui, action, media_type, dbid, cancelled=, show=) for the
# actions handle() takes, and letters.publish(xbmc, xbmcgui, container, cache=, cancelled=).
SERVICE_API = 1


def never():
    return False


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


def rpc(xbmc, method, params):
    """One JSON-RPC call through Kodi: its result (None when it has none). An error answer raises RuntimeError.
    The skin's scripts share this one (recommended.py imports it)."""
    response = json.loads(xbmc.executeJSONRPC(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    })))
    if "error" in response:
        raise RuntimeError("{} failed: {}".format(method, response["error"]))
    return response.get("result")


def get_details(xbmc, media_type, dbid, properties):
    method, key, result_key, _ = MEDIA[media_type]
    return rpc(xbmc, method, {key: dbid, "properties": properties})[result_key]


def recommendation_subject(xbmc, media_type, dbid):
    """Return the movie/show whose genre should drive related library titles."""
    if media_type in MEDIA:
        return media_type, get_details(xbmc, media_type, dbid, ["title", "genre"])
    if media_type != "episode":
        return "", {}
    episode = rpc(xbmc, "VideoLibrary.GetEpisodeDetails", {"episodeid": dbid, "properties": ["tvshowid"]})
    tvshowid = episode["episodedetails"].get("tvshowid", 0)
    if not isinstance(tvshowid, int) or tvshowid <= 0:
        return "", {}
    return "tvshow", get_details(xbmc, "tvshow", tvshowid, ["title", "genre"])


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


def series_publish(xbmc, window, timeout=3.0, cancelled=never):
    """Publish the Series page header line ("years, N seasons, rating") for the seasons folder in view.

    Kodi's seasons listing has the show's title, plot and art but no show years or season count. The show comes
    from the view's own items (TVShowDBID); the values are keyed by the folder path they were read for
    (Bald.Series.For, written last), and nothing is written if the folder changes meanwhile."""
    label = xbmc.getInfoLabel
    folder = label("Container.FolderPath")
    if not folder or not xbmc.getCondVisibility("Container.Content(seasons)"):
        return False
    monitor = xbmc.Monitor()
    deadline = time.monotonic() + timeout

    def show_id():
        count = label("Container({}).NumItems".format(SERIES_PAGE))
        for index in range(min(int(count), 4) if count.isdecimal() else 0):
            value = label("Container({}).ListItemAbsolute({}).TVShowDBID".format(SERIES_PAGE, index))
            if value.isdecimal() and int(value) > 0:
                return int(value)
        return 0

    tvshowid = show_id()
    while not tvshowid:
        if (label("Container.FolderPath") != folder or time.monotonic() >= deadline or cancelled()
                or monitor.waitForAbort(0.05)):
            return False
        tvshowid = show_id()
    show = rpc(xbmc, "VideoLibrary.GetTVShowDetails", {
        "tvshowid": tvshowid, "properties": ["year", "genre", "mpaa", "season"]})["tvshowdetails"]
    episodes = rpc(xbmc, "VideoLibrary.GetEpisodes", {
        "tvshowid": tvshowid, "properties": ["firstaired"]}).get("episodes", [])
    if label("Container.FolderPath") != folder:
        return False
    years = years_label(show.get("year", 0), episodes, xbmc.getLocalizedString)
    window.setProperty("Bald.Series.Meta",
                       tv_meta(years, show.get("season", 0), show.get("mpaa", ""), xbmc.getLocalizedString))
    window.setProperty("Bald.Series.Genre", " / ".join(show.get("genre", [])))
    window.setProperty("Bald.Series.For", folder)
    return True


def tv_position(xbmc, window, identity, season, episodeid, focus_episode, timeout=5.0, cancelled=never):
    """Select the season tab and episode once the native lists have loaded; optionally focus the episode.

    One bounded wait per dialog open that reads the lists' own items (no library query), and gives up quietly if
    the dialog is replaced or closed. A fresh fixedlist starts on its focus position (docs/NOTES.md milestone 2),
    so the episode row is always moved explicitly."""
    monitor = xbmc.Monitor()
    deadline = time.monotonic() + timeout
    label = xbmc.getInfoLabel

    def alive():
        return (not cancelled() and window.getProperty("Bald.Identity") == identity
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
    # Named ratings (the Overview's ratings row) and the ids the TMDb Helper identity guard matches on.
    ratings = details.get("ratings") or {}
    default = next((name for name, value in ratings.items() if value.get("default")), "")
    if ratings:
        tag.setRatings({name: (value.get("rating", 0), value.get("votes", 0)) for name, value in ratings.items()},
                       default)
    uniqueids = details.get("uniqueid") or {}
    if uniqueids:
        tag.setUniqueIDs(uniqueids, "imdb" if "imdb" in uniqueids else next(iter(uniqueids)))
    tag.setUserRating(details.get("userrating", 0))
    votes = str(details.get("votes") or "0").replace(",", "").replace(".", "")
    tag.setVotes(int(votes) if votes.isdigit() else 0)  # JSON-RPC gives votes as text, e.g. "12,345"
    tag.setPremiered(details.get("premiered", ""))
    tag.setCountries(details.get("country", []))
    tag.setOriginalTitle(details.get("originaltitle", ""))
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
        if details.get("set"):
            tag.setSet(details["set"])
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
        total, watched = details.get("episode", 0), details.get("watchedepisodes", 0)
        item.setProperty("TotalEpisodes", str(total))
        item.setProperty("WatchedEpisodes", str(watched))
        item.setProperty("UnWatchedEpisodes", str(max(total - watched, 0)))
    return item


def disable_mouse(xbmc):
    """Bald is remote-only: hover focus and clicks break its focus model, so turn Kodi's mouse input off."""
    rpc(xbmc, "Settings.SetSettingValue", {"setting": "input.enablemouse", "value": False})


# Font.xml fontset ids Bald Settings > Appearance offers, in file order: DM Sans (Default, lookandfeel.font's
# default), Instrument Sans, Onest (id Arial, see Font.xml).
FONTSETS = ("Default", "InstrumentSans", "Arial")
# The skin's own copy of the choice; Bald Helper (resources/lib/lookandfeel.py) re-applies it when the setting was
# lost.
FONTSET_SKIN_STRING = "Bald.Fontset"
# Text size: Kodi's lookandfeel.skinzoom, a per-cent zoom (-30 to 30) of the whole interface about the centre of the
# screen. Bald Settings > Appearance > Typography offers Default, Large and Larger. A zoom z crops z / (2 (1 + z)) of
# the width and height off each side: 37 and 21 px at 4, 71 and 40 px at 8, all inside Bald's 96 px safe margin.
# A negative zoom would frame every full-screen background in black, so there is no smaller size.
TEXT_SIZES = (0, 4, 8)
TEXT_SIZE_SKIN_STRING = "Bald.TextSize"


def set_fontset(xbmc, fontset):
    """Select a Font.xml fontset; Kodi reloads the skin itself when lookandfeel.font changes.

    JSON-RPC's Settings.SetSettingValue changes the setting without writing guisettings.xml, so a Kodi killed or
    powered off before a clean exit forgets it. Any Skin.SetString saves Kodi's settings at once, and keeps a copy
    in the skin's settings that survives skin updates."""
    if fontset not in FONTSETS:
        raise ValueError("Unknown fontset: {!r}".format(fontset))
    rpc(xbmc, "Settings.SetSettingValue", {"setting": "lookandfeel.font", "value": fontset})
    xbmc.executebuiltin("Skin.SetString({},{})".format(FONTSET_SKIN_STRING, fontset))


def set_text_size(xbmc, zoom):
    """Set Kodi's interface zoom (a TEXT_SIZES value, as text). Kodi re-lays every window and redraws its fonts at
    the new size at once, without a skin reload. The copy in Skin.String(Bald.TextSize) saves the setting at once
    and lets Bald Helper re-apply it, as for the fontset."""
    if zoom not in [str(size) for size in TEXT_SIZES]:
        raise ValueError("Unknown text size: {!r}".format(zoom))
    rpc(xbmc, "Settings.SetSettingValue", {"setting": "lookandfeel.skinzoom", "value": int(zoom)})
    xbmc.executebuiltin("Skin.SetString({},{})".format(TEXT_SIZE_SKIN_STRING, zoom))


def run(action="", media_type="", dbid=""):
    import xbmc
    import xbmcgui

    if action == "letters":
        from letters import publish
        publish(xbmc, xbmcgui, media_type)
        return
    if action == "mouse":
        disable_mouse(xbmc)
        return
    if action == "hubs":
        import xbmcvfs
        from hubs import migrate
        migrate(xbmc, xbmcgui, xbmcvfs)
        return
    if action == "recommended":
        # RunScript(skin.bald,recommended[,prompt]): see recommended.py.
        from recommended import apply
        apply(xbmc, xbmcgui, media_type)
        return
    if action == "font":
        # RunScript(skin.bald,font,<fontset id>): the id arrives in the second argument.
        set_fontset(xbmc, media_type)
        return
    if action == "textsize":
        # RunScript(skin.bald,textsize,<zoom>): 0, 4 or 8.
        set_text_size(xbmc, media_type)
        return
    if action == "keepfocus":
        # RunScript(skin.bald,keepfocus,<list>|<button>|<other>|<property>|<value>|<old>): see focus.py.
        from focus import keep
        keep(xbmc, media_type)
        return

    handle(xbmc, xbmcgui, action, media_type, dbid)


def valid_dbid(dbid):
    return dbid.isdecimal() and int(dbid) > 0


def publish_art(xbmc, window, identity):
    """Publish the dialog's art without putting paths through builtin argument parsing."""
    fanart = next((value for value in (
        xbmc.getInfoLabel("ListItem.Art(fanart)"),
        xbmc.getInfoLabel("ListItem.Art(tvshow.fanart)"),
        xbmc.getInfoLabel("ListItem.Art(thumb)"),
    ) if value), "")
    window.setProperty("Bald.Fanart", fanart)
    window.setProperty("Bald.ArtIdentity", identity)


def publish_recommendations(xbmc, window, identity, media_type, dbid):
    """More like this: the library titles sharing the movie's or show's first genre."""
    if media_type not in (*MEDIA, "episode") or not valid_dbid(dbid):
        return
    subject_type, details = recommendation_subject(xbmc, media_type, int(dbid))
    # A slow lookup from the previous item must not replace the new item's list.
    if (xbmc.getCondVisibility("Window.IsVisible(movieinformation)")
            and window.getProperty("Bald.Identity") == identity):
        window.setProperty("Bald.MoreFor", details.get("title", ""))
        window.setProperty("Bald.MorePath", recommendation_path(
            subject_type, details.get("title", ""), details.get("genre", [])))


def recommendations(xbmc, xbmcgui, media_type, dbid):
    """RunScript(skin.bald,recommendations,<type>,<id>): every info open."""
    identity = "{}:{}".format(media_type, dbid)
    window = xbmcgui.Window(12003)
    if window.getProperty("Bald.Identity") != identity:
        return
    publish_art(xbmc, window, identity)
    publish_recommendations(xbmc, window, identity, media_type, dbid)


def tv_info(xbmc, xbmcgui, media_type, dbid, cancelled=never):
    """RunScript(skin.bald,tvinfo,<type>,<id>): a TV item's header, next episode and rows."""
    identity = "{}:{}".format(media_type, dbid)
    window = xbmcgui.Window(12003)
    if media_type not in TV_TYPES or not valid_dbid(dbid) or window.getProperty("Bald.Identity") != identity:
        return
    target = tv_publish(xbmc, window, identity, media_type, int(dbid))
    if target:
        tv_position(xbmc, window, identity, target[0], target[1], media_type == "episode", cancelled=cancelled)


def info_opened(xbmc, xbmcgui, media_type, dbid, cancelled=never):
    """Bald Helper's single "info opened" request: recommendations and, for a TV item, tvinfo.

    The same steps as the two RunScript calls, ordered for what shows first: the art, the TV header, More like
    this, then the (waiting) season and episode positioning. A failing step is logged and the next still runs, as
    it would with the two separate scripts."""
    identity = "{}:{}".format(media_type, dbid)
    window = xbmcgui.Window(12003)
    if window.getProperty("Bald.Identity") != identity:
        return

    def step(name, call, *args):
        try:
            return call(*args)
        except Exception as error:  # noqa: BLE001 - one lookup failing must not hide the others
            xbmc.log("Bald info: {}: {}".format(name, error), xbmc.LOGERROR)
            return None

    publish_art(xbmc, window, identity)
    target = None
    if media_type in TV_TYPES and valid_dbid(dbid):
        target = step("tvinfo", tv_publish, xbmc, window, identity, media_type, int(dbid))
    if not cancelled():
        step("recommendations", publish_recommendations, xbmc, window, identity, media_type, dbid)
    if target and not cancelled():
        step("tvinfo", tv_position, xbmc, window, identity, target[0], target[1], media_type == "episode",
             5.0, cancelled)


def play(xbmc, xbmcgui, media_type, dbid):
    """RunScript(skin.bald,play,episode,<id>): episode Select on the info page and the Series page."""
    if media_type != "episode" or not valid_dbid(dbid) or not xbmc.getCondVisibility(PLAY_WINDOWS):
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


def open_item(xbmc, xbmcgui, media_type, dbid, show=None):
    """RunScript(skin.bald,open,<type>,<id>): More like this swaps the info dialog for the chosen title.

    `show` opens the new dialog. xbmcgui.Dialog().info returns only when that dialog closes, so Bald Helper passes
    one that calls it on a thread of its own and keeps its worker free."""
    if not xbmc.getCondVisibility("Window.IsActive(movieinformation)"):
        return
    if media_type not in MEDIA or not valid_dbid(dbid):
        return
    window = xbmcgui.Window(12003)
    home = xbmcgui.Window(10000)
    # Suppress repeat Select while fetching and exchanging the native dialog.
    if home.getProperty("Bald.InfoSwitch"):
        return
    token = uuid.uuid4().hex
    home.setProperty("Bald.InfoSwitch", token)
    origin = window.getProperty("Bald.Identity")
    try:
        properties = ["title", "file", "art", "plot", "year", "genre", "studio", "mpaa", "playcount", "rating",
                      "dateadded", "cast", "ratings", "uniqueid", "userrating", "votes", "premiered", "country",
                      "originaltitle"]
        properties += (["director", "runtime", "writer", "tagline", "trailer", "resume", "streamdetails", "set"]
                       if media_type == "movie" else ["season", "episode", "watchedepisodes"])
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
        (show or xbmcgui.Dialog().info)(item)
    finally:
        if home.getProperty("Bald.InfoSwitch") == token:
            home.clearProperty("Bald.InfoSwitch")


def handle(xbmc, xbmcgui, action, media_type="", dbid="", cancelled=never, show=None):
    """The latency-sensitive actions, shared by RunScript and Bald Helper's service (see the module docstring)."""
    if action == "seriesmeta":
        series_publish(xbmc, xbmcgui.Window(VIDEO_NAV), cancelled=cancelled)
    elif action == "info":
        info_opened(xbmc, xbmcgui, media_type, dbid, cancelled)
    elif action == "tvinfo":
        tv_info(xbmc, xbmcgui, media_type, dbid, cancelled)
    elif action == "recommendations":
        recommendations(xbmc, xbmcgui, media_type, dbid)
    elif action == "play":
        play(xbmc, xbmcgui, media_type, dbid)
    elif action == "open":
        open_item(xbmc, xbmcgui, media_type, dbid, show)


if __name__ == "__main__":
    try:
        run(*sys.argv[1:])
    except Exception as error:
        import xbmc
        xbmc.log("Bald info: {}".format(error), xbmc.LOGERROR)
