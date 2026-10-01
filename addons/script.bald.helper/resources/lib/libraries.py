"""Rows for one library: the library's tags, and a few lists filtered to one tag, for the content picker.

PlexKodiConnect and Jellyfin for Kodi tag every movie and show with the name of the library it came from ("Kids TV",
"Anime"), and write their own library nodes and video playlists with a rule on that tag. They also copy each item's
keywords in as tags ("1970s", "heist"), hundreds of them, so the libraries are the tags those nodes and playlists name
(any of the user's own playlists with a tag rule counts too). A skin playlist cannot name a library it does not know,
so the picker's "Libraries and tags" browses these instead:

    ?info=library_tags              the libraries, then "All tags" (every movie and TV show tag), as folders.
    ?info=library_tags&all=1        every movie and TV show tag, as folders.
    ?info=library_tag&tag=T         the lists for tag T, as folders: smart playlists the helper writes to its data
                                    folder (libraries/), so a row chosen here needs no helper to list it.

The lists are files, not Kodi's library paths with the rules in the URL (videodb://movies/titles/?xsp=...): a movie
path's order and limit are dropped there (with movie sets grouped, Kodi sorts the titles itself), and a file's are not.
"""

from __future__ import annotations

import hashlib
import os
import xml.etree.ElementTree as ET
from urllib.parse import quote

from . import common

KINDS = {  # tag type: (smart playlist type, icon)
    "tvshow": ("tvshows", "DefaultTVShows.png"),
    "movie": ("movies", "DefaultMovies.png"),
}
LIMIT = 50
FOLDER = f"{common.DATA_DIR}/libraries/"

# Where the library add-ons write their nodes (a folder per library) and playlists.
RULE_FOLDERS = ("special://profile/library/video/", "special://profile/playlists/video/")

# The helper's strings (resources/language/resource.language.en_gb/strings.po).
S_IN_TAG = 32130
S_ALL_TAGS = 32138
LISTS = {  # tag type: [(file key, string, rules, order, direction, limited)]
    "tvshow": [
        ("new_episodes", 32131, [("playcount", "is", "0")], "dateadded", "descending", True),
        ("recent_unwatched", 32132, [("numwatched", "is", "0")], "dateadded", "descending", True),
        ("all", 32133, [], "sorttitle", "ascending", False),
    ],
    "movie": [
        ("recent_unwatched", 32134, [("playcount", "is", "0")], "dateadded", "descending", True),
        ("inprogress", 32135, [("inprogress", "true", None)], "lastplayed", "descending", True),
        ("random", 32136, [], "random", "ascending", True),
        ("all", 32137, [], "sorttitle", "ascending", False),
    ],
}


def tags(xbmc) -> dict:
    """{tag: [tag types]} for every tag on a movie or a TV show, the types in KINDS order."""
    found = {}
    for kind in KINDS:
        for tag in common.jsonrpc(xbmc, "VideoLibrary.GetTags", {"type": kind}).get("tags") or []:
            label = str(tag.get("label") or "").strip() if isinstance(tag, dict) else ""
            if label:
                found.setdefault(label, []).append(kind)
    return dict(sorted(found.items(), key=lambda pair: pair[0].casefold()))


def named_tags(xbmcvfs) -> set:
    """The tags that library nodes and video playlists filter on (<rule field="tag" operator="is">), two folders deep."""
    found = set()
    for folder in RULE_FOLDERS:
        root = xbmcvfs.translatePath(folder)
        for directory, subfolders, files in os.walk(root):
            if os.path.relpath(directory, root).count(os.sep) >= 1:
                subfolders[:] = []
            for name in files:
                if not name.endswith((".xml", ".xsp")):
                    continue
                try:
                    tree = ET.parse(os.path.join(directory, name)).getroot()
                except (ET.ParseError, OSError):
                    continue
                for rule in tree.iter("rule"):
                    if rule.get("field") == "tag" and rule.get("operator") == "is":
                        found |= {value.text.strip() for value in rule.findall("value") if value.text and value.text.strip()}
    return found


def playlist(kind: str, tag: str, key: str, name: str, rules, order: str, direction: str, limited: bool) -> tuple:
    """(file name, XML) of the smart playlist for one list: `kind` filtered to `tag` and `rules`, sorted. The name
    keeps the tag's hash, not the tag, so any tag makes a safe file name and each keeps its own file."""
    xsp_type = KINDS[kind][0]
    root = ET.Element("smartplaylist", type=xsp_type)
    ET.SubElement(root, "name").text = name
    ET.SubElement(root, "match").text = "all"
    for field, operator, value in [("tag", "is", tag)] + list(rules):
        rule = ET.SubElement(root, "rule", field=field, operator=operator)
        if value is not None:
            ET.SubElement(rule, "value").text = value
    if limited:
        ET.SubElement(root, "limit").text = str(LIMIT)
    ET.SubElement(root, "order", direction=direction).text = order
    digest = hashlib.sha1(tag.encode("utf-8")).hexdigest()[:12]
    return f"{xsp_type}_{key}_{digest}.xsp", ET.tostring(root, encoding="unicode", xml_declaration=True)


def write(xbmcvfs, file_name: str, text: str) -> str:
    """Writes the playlist to FOLDER (only when it changed); returns its special:// path."""
    folder = xbmcvfs.translatePath(FOLDER)
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, file_name)
    try:
        with open(target, encoding="utf-8") as current:
            unchanged = current.read() == text
    except OSError:
        unchanged = False
    if not unchanged:
        with open(target, "w", encoding="utf-8") as out:
            out.write(text)
    return FOLDER + file_name


def list_tags(xbmc, xbmcgui, xbmcplugin, xbmcvfs, handle: int, base: str, every: bool, strings) -> int:
    """The libraries (the tags named in nodes and playlists that some movie or show has), then "All tags"; or, with
    `every`, every tag."""
    found = tags(xbmc)
    shown = list(found) if every else [tag for tag in found if tag in named_tags(xbmcvfs)]
    items = []
    for tag in shown:
        item = xbmcgui.ListItem(tag, offscreen=True)
        item.setArt({"icon": "DefaultTags.png"})
        items.append((f"{base}?info=library_tag&tag={quote(tag, safe='')}", item, True))
    if not every and found:
        item = xbmcgui.ListItem(strings(S_ALL_TAGS), offscreen=True)
        item.setArt({"icon": "DefaultTags.png"})
        items.append((f"{base}?info=library_tags&all=1", item, True))
    xbmcplugin.addDirectoryItems(handle, items, len(items))
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    return len(items)


def list_tag(xbmc, xbmcgui, xbmcplugin, xbmcvfs, handle: int, tag: str, strings) -> int:
    """The lists for one tag, for each type the tag is on, written as playlists. `strings` is the helper's
    getLocalizedString."""
    items = []
    for kind in tags(xbmc).get(tag, []):
        icon = KINDS[kind][1]
        for key, string, rules, order, direction, limited in LISTS[kind]:
            label = strings(S_IN_TAG).format(list=strings(string), tag=tag)
            item = xbmcgui.ListItem(label, offscreen=True)
            item.setArt({"icon": icon})
            path = write(xbmcvfs, *playlist(kind, tag, key, label, rules, order, direction, limited))
            items.append((path, item, True))
    xbmcplugin.addDirectoryItems(handle, items, len(items))
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    return len(items)
