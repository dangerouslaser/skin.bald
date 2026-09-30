# Bald Process Info

`script.bald.processinfo` is a Kodi add-on that shows what the player is doing. It covers the codec, video, audio, HDR and Dolby Vision details of what's playing, and what the box is sending to the display. It runs on **LibreELEC**, including the Intel Dolby Vision build [intel-dv-libreelec](https://github.com/CroqueMr/intel-dv-libreelec), and on CoreELEC. It's published in the [Bald repository](https://dangerouslaser.github.io/skin.bald/).

It's a fork of [TinyPPI](https://github.com/CE-Repo/script.tinyppi) by U3knOwn, whose code is AGPL-3.0-or-later. It's **not TinyPPI**, and TinyPPI's author doesn't support it. Report problems with this add-on [here](https://github.com/dangerouslaser/script.bald.processinfo/issues), not upstream. **On CoreELEC, use TinyPPI from its author's repository** for official support. This fork exists for LibreELEC.

## What's different from TinyPPI

LibreELEC has no `Player.Process(amlogic.*)` labels, so `resources/lib/core/platform.py` rebuilds them, in the Amlogic spelling, from:

- `VideoPlayer.HdrDetail`, which the Intel DV build ends with `· HDMI DV` or `· HDR10 output` while its bridge drives the output (profile, FEL and CM version come from the same label);
- the DRM connector's `HDR_OUTPUT_METADATA` blob, read through Kodi's own DRM descriptor, for HDR10 and HLG;
- the DRM debugfs (`state`, and `i915_display_info` on Intel) for the pixel encoding, bit depth, colorimetry and exact mode.

On LibreELEC:

- **VS10 modes** aren't available, because VS10 is the Amlogic Dolby Vision engine. A launch mode or keymap set to the VS10 dialog opens the overlay instead. On the Intel DV build, the output mode is Kodi's own *Dolby Vision output* setting.
- **RPU metadata** (L1, L5, L6, the metadata view) stays empty. Kodi on LibreELEC has no `Player.Process(video.sidedata)` label, so `script.module.sidedata` has nothing to parse. It's an optional dependency.
- **Dropped frames** in the FPS row read 0. The Amlogic `fps_info` node has no LibreELEC equivalent.

The name, icon, fanart and interface artwork are this fork's own (see `LICENSE-ASSETS`).

## How the fork follows upstream

The fork's own commits change code only and never rename anything. `.github/workflows/follow-upstream.yml` runs daily and on every push to `libreelec`. It replays those commits onto TinyPPI's `main`, then runs `tools/fork_branding.py` and commits the result as **Fork branding (generated)**. That step copies `branding/` over the tree (artwork and these docs), renames the add-on, and sets the version to upstream's plus `.FORK_REVISION` (e.g. `2.13.0.3`). `tools/make_branding.py` draws the artwork in `branding/`.

If a replay conflicts or a test fails, the branch isn't pushed. The workflow opens an `upstream-sync` issue assigned to the owner, and the next green run closes it. `tests/` also fails in two cases: when upstream adds an Amlogic-only read in a file that hasn't been reviewed for LibreELEC, and when any of TinyPPI's original artwork is left in the generated tree.

When the fork changes without a new upstream release, raise `FORK_REVISION` in `tools/fork_branding.py`.

## Licence

Code: GNU Affero General Public License v3.0 or later (`LICENSE`), as upstream. Artwork: see `LICENSE-ASSETS`.
