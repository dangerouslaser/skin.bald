# skin.estuary.lg (Estuary LG)

Kodi's Estuary skin with LG webOS TV integration from
[service.webostv](https://github.com/dangerouslaser/kodi-webos-control).

## Base

- Estuary 4.1.0 from Kodi 22.0 RC1 (`xbmc/xbmc@63063c8e67b1`), imported unchanged.
- LibreELEC's only Estuary patch, `1014-estuary-settings-icon` (LibreELEC.tv master), so the
  Settings screen matches LibreELEC 13 builds.
- Then our changes, kept in separate commits so a newer Estuary can be merged in.

The addon id is `skin.estuary.lg`, so it installs alongside the stock Estuary.

## Changes

| Where | What |
| --- | --- |
| `xml/Home.xml` | No Kodi logo top left; power / settings / search row moved to the bottom of the side menu; the menu starts at the top and its height follows *Main menu size*; moving right into the content collapses the menu to icons (panel slides away, labels and the button row fade, the highlight bar shrinks to the icon square and stays) and slides the content left. Left brings it back |
| `xml/Home.xml` (LG TV) | **LG TV** side menu item (after Add-ons) with two widget rows, *Apps* (TV launcher order) and *Inputs*, from `plugin://service.webostv/`; picking a tile launches it on the TV. Clicking the menu item opens the apps as a full list. Toggle in *Skin settings → Main menu items*. Weather box moved down 20px to line up with the first row of tiles on the other pages |
| `media/icons/sidemenu/lgtv.png` | Side menu icon |
| `xml/Includes_Home.xml` | Widget area (`WidgetGroupListCommon`) reaches 367px past the right edge so rows still fill the screen when collapsed; widget scrollbars counter-slide |
| `xml/SkinSettings.xml` | *Main menu items → Main menu size*: 4–9 rows (default 9, the most that fit above the buttons). Applied when you leave skin settings (the skin reloads once if it changed) |
| `xml/Includes_Custom.xml` | Hand-written includes (menu height per size, `home_menu_collapsed` expression) |
| `xml/Custom_1109_TopBarOverlay.xml` | Live TV: channel logo (`Player.Icon`) at the top left of the OSD, title moved right of it |
| `xml/VideoOSD.xml` | **LG picture mode** button (before video settings) opens the TV's picture preset list; shown while the TV is connected. OSD label shows the current preset (`xml/Variables.xml`) |
| `media/osd/fullscreen/buttons/lg-picture-mode.png` | OSD button icon |
| `xml/VideoOSD.xml` | **Bald Process Info** button (after LG picture mode), shown when script.bald.processinfo is installed and enabled; opens it in its own launch mode (overlay or dialog) |
| `media/osd/fullscreen/buttons/processinfo.png` | Its icon (Bald's PPI icon, scaled to Estuary's OSD icons) |
| `xml/Settings.xml` | Top row holds 5 tiles with **LG TV** last (shown when service.webostv is enabled); the settings grid stays 4 per row, centred |
| `xml/Includes.xml` | `SettingsPanel` tiles scaled to 85% (340×221) so the top row fits 5; includes `Includes_LGTV.xml` |
| `xml/Custom_1120_LGTV.xml` | LG TV page, laid out like Estuary's settings pages: categories on the left (TV, Picture, TV integration, Connection), options on the right, help text for the focused option, TV model and connection at the bottom left |
| `xml/Includes_LGTV.xml` | Variables for the LG TV page |
| `xml/Font.xml`, `fonts/DMSans-*.ttf` | **DM Sans** fontset (*Settings → Interface → Skin → Fonts*): a copy of Default using DM Sans Regular, and DM Sans Bold for the bold-styled fonts. Clock and mono fonts unchanged. Both files carry Noto Sans's superscripts, subscripts and small capitals (ᴺᵉʷ ᴴᴰ ²), merged in by `tools/add_superscripts.py` (from skin.bald), since Kodi has no per-character font fallback. DM Sans covers Latin scripts only |
| `media/icons/sidemenu/tv.png` | TV shows icon redrawn (stacked screens with a play symbol) so it no longer looks like Live TV |
| `media/icons/settings/lgtv.png` | Tile icon (LG logo) |
| `language/resource.language.en_gb/strings.po` | Strings 31900–31999 |

`Custom_1120_LGTV.xml` and `Includes_LGTV.xml` are generated: edit `tools/gen_lgtv.py` and run
`python3 tools/gen_lgtv.py`. Option labels and help text come from the addon's own strings
(`$ADDON[service.webostv …]`), so they stay in sync with its settings.

TV controls are disabled while the TV isn't connected. On TVs whose webOS won't report the picture mode
(`WebOS.PictureSupported` is `false`, e.g. webOS 5.5), the Picture page explains that and greys its
options out, and the OSD picture button is hidden. Needs service.webostv 0.4.5 or newer.

## Dev deploy

`scripts/deploy.sh` copies the skin to the Kodi box over SSH and reloads it
(`KODI_HOST`, default 192.168.1.175).

## Build

```sh
python3 scripts/build_zip.py   # -> dist/skin.estuary.lg-<version>.zip
```

Install from zip in Kodi, then *Settings → Interface → Skin → Estuary LG*.

## License

Same as Estuary: GPL-2.0 for code, CC BY-SA 4.0 for media. DM Sans is under the SIL Open Font
License 1.1 (`fonts/dmsans_license.txt`).
