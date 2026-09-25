---
name: kodi-skin-dev
description: Develop and debug the Bald Kodi 22 skin, including skin XML, focus navigation, artwork transitions, and macOS runtime verification. Use for skin implementation or Kodi UI diagnosis in this repository.
---

# Kodi skin development

Work from the repository root. Read `AGENTS.md`, `docs/SPEC.md` before visual changes, and relevant sections of `docs/NOTES.md` before choosing Kodi mechanisms. Notes contain superseded approaches: find the current outcome. Ask when spec and prototype conflict. Preserve existing user edits.

## Implementation

- Target Kodi 22 and GUI API 5.18.0. Skin files live in `1080i/`; bundled Estuary uses its own `xml/` directory.
- Follow spec coordinates, font tokens and motion curves. Share groups through parameterized includes. Preserve native control IDs and action dispatch when redesigning utility windows.
- Inspect installed Kodi 22 Estuary for window contracts. Verify uncertain behavior against matching Kodi source or official docs; browser/CSS behavior does not establish Kodi behavior.
- Visibility edges, retained outgoing artwork, container scope, asynchronous content and focus restoration require runtime checks. XML parsing alone cannot establish correctness. Test meaningful contracts instead of duplicating every XML value.

## Development loop

See `docs/KODI_DEVELOPMENT.md` for commands and limitations.

1. Run `python3 tools/kodi_dev.py doctor` when starting runtime work or diagnosing environment trouble.
2. Make the scoped change and run `python3 tools/kodi_dev.py validate`.
3. Run `python3 tools/kodi_dev.py reload --check-log`. Inspect all fresh errors and distinguish unrelated issues with evidence.
4. Exercise the changed flow and inspect screenshots. `capture` saves a Kodi-only PNG and state; `smoke home-info-back` checks the basic Info/Back route. Other flows use focused navigation through `tools/kodi_rpc.py` or computer-use tools.
5. Check focus entry, directions, Back, empty/loading states and repeated input as relevant. Inspect transitions in motion; screenshots cannot establish fluidity or timing.
6. Record newly demonstrated Kodi limitations in `docs/NOTES.md`, including what was tried and the replacement. Distinguish macOS checks from outstanding CoreELEC checks.

The CLI targets local macOS Kodi. UDP send is not execution confirmation: reload waits for fresh log evidence and capture waits for a complete PNG. If shell sandboxing blocks local sockets, use normal narrow execution escalation; do not alter settings or sandbox configuration.

## Specialized roles

Use `kodi_skin_reviewer` for independent review when useful and `kodi_runtime_qa` for bounded runtime checks. Definitions live in `.codex/agents/`. Supply the reviewer with diff scope and acceptance criteria; supply QA with exact steps, expected states and artifact location.

Assign only one live Kodi owner at a time. The CLI locks its mutating commands; raw RPC and computer-use actions need explicit coordination. Pause skin edits during verification so evidence refers to a stable revision. The parent integrates findings and owns commits. Roles do not authorize unrelated playback, library/settings changes or deployment.
