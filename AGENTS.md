# Bald (skin.bald)

A Kodi 22 skin: minimal, artwork-first, fluid motion. Kodi 22 only. `addon.xml` imports `xbmc.gui` 5.18.0, which does not load on Kodi 21, and that is intended.

## Sources of truth

- `docs/SPEC.md`: the alpha 0.1 handoff spec (layout coordinates, type scale, palette rule, every motion timing and curve, focus maps, Kodi mapping, milestones). Read it before changing anything visual.
- The interactive prototype on the design canvas ("Home v2 with movie and TV info screens"). When the spec is silent, match the prototype's behavior.
- If the two disagree, ask before choosing.

## Repo and Kodi

- This folder is the skin itself. It is symlinked into Kodi on macOS:
  `~/Library/Application Support/Kodi/addons/skin.bald -> /Users/bryanhoban/Projects/skin.bald`
  Do not move or rename the folder.
- Kodi log on macOS: `~/Library/Logs/kodi.log`. Check it after every reload for `ERROR` lines and XML parse failures.
- Reload the skin without restarting Kodi, either:
  - with Kodi's event server (Settings, Services, Control, allow remote control) and `kodi-send --action="ReloadSkin()"` (the script lives in Kodi's source under `tools/EventClients/Clients/KodiSend/`), or
  - with a keymap binding to `ReloadSkin()` in `~/Library/Application Support/Kodi/userdata/keymaps/`.
- `Skin.ToggleDebug` overlays control IDs and window names; use it for focus problems.
- Hardware checks: rsync the repo to `/storage/.kodi/addons/skin.bald/` on a CoreELEC box (Ugoos AM6B+ or AM9 Pro) over SSH, then reload there.

## Conventions

- Coordinates are 1080i (1920 x 1080). Safe margin is 96 px on every side.
- One UI font family at a time: Instrument Sans (default) or DM Sans, chosen skin-wide in Appearance › Typography. Both ship as static TTFs in `fonts/` and are declared as fontsets in `1080i/Font.xml`; a new font name must be added to both fontsets with the same size (DM Sans may differ only in `linespacing`, see `tests/test_fonts.py`).
- Animation curves map exactly as the spec says: move = `tween="cubic" easing="out"`, fade = `tween="sine" easing="inout"`, pop = `tween="back" easing="out"`. Use only fade, slide and zoom.
- Put repeated control groups and animations in `1080i/Includes_*.xml` with params rather than copying them.
- Take control IDs from the ranges in `1080i/IDs` and record new ones there.
- Utility windows (dialogs, player OSD, settings, add-on and file browsers, library and PVR windows) start as copies of Kodi 22's bundled Estuary, taken from
  `/Applications/Kodi.app/Contents/Resources/Kodi/addons/skin.estuary/` so the version matches exactly. Keep Estuary's license notices. The skin is GPL-2.0-or-later.
- Native windows for alpha 0.1: `Home.xml` and `DialogVideoInfo.xml`. Everything else stays Estuary until it is redesigned.
- The movie and TV handoff happens inside `Home.xml`: the fanart frame group zooms on `Window.IsVisible(movieinformation)` (end 153.846, center 274,343, 640 ms, 40 ms delay). The info dialog draws scrims and content only.

## Workflow

- Work milestone by milestone in the order the spec lists. Reload and check the log after each change.
- Small commits with clear messages; push to GitHub at the end of each milestone.
- When something in the spec turns out not to work in Kodi 22, note it in `docs/NOTES.md` with what was tried and what was done instead.

## Kodi development support

- Use the repo-local skill `.agents/skills/kodi-skin-dev/SKILL.md` for skin implementation and runtime diagnosis.
- The development CLI and its limitations are documented in `docs/KODI_DEVELOPMENT.md`. Prefer `python3 tools/kodi_dev.py reload --check-log` for reload evidence and fresh logs.
- Use `kodi_skin_reviewer` for useful independent review and `kodi_runtime_qa` for bounded live verification. Definitions live in `.codex/agents/` and inherit the session model.
- Assign one live Kodi owner at a time, including direct RPC and computer-use tools. Pause skin edits during checks. The CLI lock covers only its own mutating commands.
