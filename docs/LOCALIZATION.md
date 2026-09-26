# Localization

Bald's own UI text lives in `language/resource.language.en_gb/strings.po`, after Estuary's strings, and the XML
shows it through `$LOCALIZE[id]`.

## ID block

| Range       | Owner                                                                                  |
|-------------|----------------------------------------------------------------------------------------|
| 31000-31699 | Estuary's strings, kept for the copied utility windows (currently up to 31615)          |
| 31616-31649 | Bald playback windows restyled from Estuary (Includes_Bald_Playback.xml; tests/test_playback.py) |
| 31650-31659 | Bald global overlays (Includes_Bald_Overlays.xml; tests/test_overlays.py)             |
| 31660-31679 | Bald Live TV windows restyled from Estuary (Includes_Bald_PVR.xml; tests/test_pvr.py)  |
| 31680-31684 | Reserved for the shared foundations pass (unused)                                      |
| 31685-31699 | Bald browse windows restyled from Estuary (Includes_Bald_Browse.xml; tests/test_browse.py) |
| 31700-31999 | Bald                                                                                    |

Kodi keeps skin strings in 31000-31999 and clears that range when the skin reloads, so Bald stays inside it.
Within Bald's block, IDs are grouped by area with room to grow:

| Range       | Area                                               |
|-------------|----------------------------------------------------|
| 31700-31729 | Home, its menu, and short metadata fragments       |
| 31730-31769 | Bald Settings, Home Screens, widgets, Appearance   |
| 31770-31799 | Movie and TV info                                  |
| 31800-31849 | Library views: options, notes, hints               |
| 31850-31869 | Library layout names (`<viewtype label="…">`)      |
| 31870-31889 | Live TV guide                                      |
| 31890-31899 | Global Search                                      |
| 31900-31949 | Context menu notes                                 |
| 31950-31969 | Kodi settings windows (hub, pages, profiles, info) |
| 31980-31999 | Media utility windows (Includes_Bald_Media.xml)    |

## Rules

- Add new strings to en_gb only, with a `#: /1080i/<file>` line for every file that uses the ID (and
  `#: /scripts/info.py` for text the script shows). Other languages fall back to en_gb until someone translates them.
- Reuse a Kodi core string when its wording and meaning are the same (for example `$LOCALIZE[342]` Movies,
  `$LOCALIZE[13404]` Resume). Do not reuse one whose meaning only looks the same: core 21483 "View" is a verb, so
  Bald's layout option has its own "View".
- Text that goes inside `$INFO[info,prefix,suffix]` must not contain a comma. Kodi splits those arguments on commas
  after it replaces `$LOCALIZE`, so a comma in a translation would cut the text. Such strings carry a `#.` note
  for translators, and whole sentences are built outside `$INFO` instead (see `Bald_LibraryMenuNote`).
- Proper names (CoreELEC, LibreELEC, Dolby Vision, HDR10, HLG) and the S/E, h/m and p unit letters stay literal.
- Don't localize Home row names. They come from the Skin Variables shortcut files
  (`shortcuts/skinvariables-shortcut-*.json`), and the user can rename them, so they are data.
- `scripts/info.py` resolves its IDs with `xbmc.getLocalizedString` and keeps the en_gb wording in `STRINGS` for runs
  without Kodi.

`tests/test_localization.py` checks that every ID the skin shows is defined, that every Bald string is used and cites
its files, that no Bald string is duplicated, and that Bald's own windows have no hardcoded English left.
