# Kodi development tools

Run from the repository root with Python 3.11 or later. The CLI uses the standard
library and `tools/kodi_rpc.py`. Runtime commands target local macOS Kodi on TCP
9090 and EventServer UDP 9777.

```sh
python3 tools/kodi_dev.py doctor
python3 tools/kodi_dev.py validate
python3 tools/kodi_dev.py state
python3 tools/kodi_dev.py reload --check-log
python3 tools/kodi_dev.py capture
python3 tools/kodi_dev.py smoke home-info-back
```

`doctor` checks the skin symlink, log readability, bundled Estuary's GUI API,
running Kodi version, active skin and EventServer setting. It never enables settings.
Reload/capture provide actual EventServer delivery evidence.

`validate` parses XML/playlists, warns about unresolved literal include names, and
runs unit tests. Conditional include loading, expressions and dynamic assets still
need runtime review. Advisory reference warnings do not fail the command.

`state` collects window, skin, title/index, dimensions and focus. Focus checks use
`Control.HasFocus` for literal control IDs and `id` include parameters in `1080i/*.xml`; dynamically generated
IDs may be absent. Kodi's current-control label can be empty.

`reload` records the log offset, sends `ReloadSkin()`, waits up to 12 seconds for
a fresh `skin loaded...` marker, observes for two seconds and verifies Bald remains
active. Log checking is always on; `--check-log` is an optional readability flag.
Log rotation/truncation fails the check instead of trusting old entries. All fresh
error/fatal lines are reported. Background errors can produce a nonzero exit even
when reload succeeds; inspect context in the saved log.

`capture` calls Kodi's `TakeScreenshot`, waits for a complete PNG and saves GUI state.
It captures Kodi's rendered image, not the desktop. Inspect the image before making
visual claims. Use a 16:9 window for comparison with the 1920×1080 spec. The CLI sends
EventServer actions without HELO announcements so connection toasts do not obscure
captures; the raw RPC helper retains its previous announcing behavior by default.
Kodi 22 removed the older screenshot `sync` argument, so the tool waits for the file.

`smoke home-info-back` navigates to Home, waits for a selected title, opens Info,
then goes Back and checks selection and focus restoration. Each stage is captured,
along with fresh logs. It requires a populated Home row, Bald active and no playback.
It leaves Kodi at Home on success and stops at the failing state on failure.
It does not play media or edit library data. This verifies a basic route, not all
info pages, artwork loading, visual details or motion.

`reload`, `capture` and `smoke` share a per-user lock. Raw RPC and computer-use
tools bypass it: assign one runtime owner and pause edits during verification.

Artifact commands print a fresh temporary output directory and save `report.json`.
Use `--output /path/new-run` to choose a new directory (existing directories are
refused). Reload and smoke accept `--settle 0..30` seconds. Errors return nonzero.
Logs/screenshots may contain local media information; inspect before sharing.

## Codex setup

Use `$kodi-skin-dev` for the skill at `.agents/skills/kodi-skin-dev/SKILL.md`.
The `.codex/agents/` roles are `kodi_skin_reviewer` and `kodi_runtime_qa`.
They inherit session model choices. Start a new Codex session if added roles are
not visible in the current session.

Example: “Use $kodi-skin-dev to fix focus restoration. Have kodi_skin_reviewer
review it, then give kodi_runtime_qa exclusive control to verify Info → Back.”

CoreELEC remains the SSH/rsync workflow in `AGENTS.md`. These tools neither deploy
to nor establish performance on that hardware.

References: [Codex skills](https://learn.chatgpt.com/docs/build-skills),
[custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents),
[Kodi builtins](https://kodi.wiki/view/List_of_built-in_functions),
[JSON-RPC](https://kodi.wiki/view/JSON-RPC_API).
