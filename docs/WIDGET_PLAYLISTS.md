# Default widget sources

Bald ships a small video-library catalog for the configurable Home experience. The
catalog is independently authored for Bald. Arctic Fuse 3 was inspected only as a
behavioral reference for the useful categories a skin can expose.

Use Kodi library paths when Kodi already owns the exact query. Use a bundled smart
playlist only when the widget needs filtering or a non-native order. This keeps the
defaults fast, predictable and usable without a metadata add-on.

## Fixed-layout defaults

A fresh install starts with these rows. They come from `shortcuts/skinvariables-shortcut-*widgets.json`,
which `tools/build_home_defaults.py` bakes into `1080i/Includes_Bald_HomeDefaults.xml`; keep this
table in step with those files:

| Screen | Widget | Source |
| --- | --- | --- |
| Home | Recently added movies | `videodb://recentlyaddedmovies/` |
| Home | Continue watching | `special://skin/playlists/inprogress_movies.xsp` plus `special://skin/playlists/inprogress_episodes.xsp` |
| Home | Next up | `videodb://inprogresstvshows/` |
| Movies | Recently added movies | `videodb://recentlyaddedmovies/` |
| Movies | Top rated movies | `special://skin/playlists/top_rated_movies.xsp` |
| TV shows | Recently added episodes | `videodb://recentlyaddedepisodes/` |
| TV shows | Top rated TV shows | `special://skin/playlists/top_rated_tvshows.xsp` |

Kodi smart playlists cannot safely combine movies and episodes. Continue watching
therefore remains two typed content sources in one widget. Kodi concatenates those
sources rather than interleaving them by last played.

## Bundled catalog

The settings content picker can expose these sources under Movies, TV shows and
Episodes:

| Media | Bundled choices |
| --- | --- |
| Movies | In progress, Movies in 4K, Random, Recently added unwatched, Recently played, Top 250, Top rated, Unwatched |
| TV shows | Random, Recently added unwatched, Recently played, Top rated, Unwatched |
| Episodes | In progress, Random, Recently added unwatched, Recently played, Top rated, Unwatched |

Native library nodes should also remain available through the content picker. In
particular, do not add `All movies`, `All TV shows`, `Recently added movies` or
`In-progress TV shows` XSP files merely to alias an existing `videodb://` route.

## Kodi 22 contracts

- Every bundled video playlist has one content type: `movies`, `tvshows` or
  `episodes`. The only supported Kodi mixed type combines music and music videos,
  so it is not applicable here.
- Playlist results are capped at 50. The widget's own item limit chooses the smaller
  visible subset; the current Continue watching row still requests 15 from each
  source.
- Recently played means played within the last 28 days, newest first.
- Recently added unwatched widgets filter watch state and sort by `dateadded`; they
  do not impose a fixed calendar cutoff.
- Kodi 22 maps a `videoresolution is 2160` rule to its 4K-or-higher width bucket.
  `videoresolution` is valid for movies and episodes, but not TV-show playlists.

The field and ordering contracts were checked against Kodi 22 Beta 1's
[`CSmartPlaylistRule`](https://github.com/xbmc/xbmc/blob/22.0b1-Piers/xbmc/playlists/SmartPlayList.cpp).

