"""Small, local-library bridges for the native video-info dialog (Kodi 22).

RunScript(skin.bald,recommendations,movie,123)
RunScript(skin.bald,open,movie,456)
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
        publish(xbmc, xbmcgui)
        return

    identity = "{}:{}".format(media_type, dbid)
    window = xbmcgui.Window(12003)
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
        if media_type not in MEDIA or not dbid.isdecimal() or int(dbid) <= 0:
            return
        details = get_details(xbmc, media_type, int(dbid), ["title", "genre"])
        # A slow lookup from the previous item must not replace the new item's list.
        if (xbmc.getCondVisibility("Window.IsVisible(movieinformation)")
                and window.getProperty("Bald.Identity") == identity):
            window.setProperty("Bald.MorePath", recommendation_path(
                media_type, details["title"], details.get("genre", [])))
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
