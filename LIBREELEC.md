# TinyPPI for LibreELEC

This fork ([dangerouslaser/script.tinyppi](https://github.com/dangerouslaser/script.tinyppi), branch `libreelec`) also runs on **LibreELEC** (Kodi 22), including the Intel Dolby Vision build [intel-dv-libreelec](https://github.com/CroqueMr/intel-dv-libreelec). CoreELEC behaviour is unchanged.

LibreELEC has no `Player.Process(amlogic.*)` labels, so `resources/lib/core/platform.py` rebuilds them, in the Amlogic spelling, from:

- `VideoPlayer.HdrDetail`, which the Intel DV build ends with `· HDMI DV` or `· HDR10 output` while its bridge drives the output (profile, FEL and CM version come from the same label);
- the DRM connector's `HDR_OUTPUT_METADATA` blob, read through Kodi's own DRM descriptor, for HDR10 and HLG;
- the DRM debugfs (`state`, and `i915_display_info` on Intel) for the pixel encoding, bit depth, colorimetry and exact mode.

What does not work on LibreELEC:

- **VS10 modes** (the mode dialog and the dashboard's mode buttons): VS10 is the Amlogic Dolby Vision engine. On the Intel DV build, the output mode is Kodi's own *Dolby Vision output* setting.
- **RPU metadata** (L1, L5, L6, the metadata view): Kodi on LibreELEC has no `Player.Process(video.sidedata)` label, so `script.module.sidedata` has nothing to parse. It is an optional dependency here.
- **Dropped frames** in the FPS row: the Amlogic `fps_info` node has no LibreELEC equivalent, so the drop count reads 0.

## Following upstream

`.github/workflows/follow-upstream.yml` runs daily (and on every push to `libreelec`). It replays the fork's commits onto `CE-Repo/script.tinyppi` `main`, runs `tests/`, and ends the branch with a regenerated **Fork metadata (generated)** commit from `tools/fork_metadata.py`. That commit holds the fork's only `addon.xml` edits: the version (upstream's plus `.FORK_REVISION`, e.g. `2.12.0.1`), the provider, the optional `script.module.sidedata` and the source URL. Because the fork's own commits never touch `addon.xml`, an upstream version bump can't conflict with them.

If a replay conflicts or a test fails, the branch isn't pushed. The workflow opens an `upstream-sync` issue assigned to the owner, and the next green run closes it. `tests/test_libreelec.py` also fails when upstream adds an Amlogic-only read in a file that hasn't been reviewed for LibreELEC.

When the fork changes without a new upstream release, raise `FORK_REVISION` in `tools/fork_metadata.py` so Kodi sees a newer version.
