# Bald Add-on Repository

This Kodi repository add-on points Kodi 22 at the Bald release feed hosted by
GitHub Pages. Install `repository.bald-1.0.0.zip`, then install **Bald** from
**Add-ons → Install from repository → Bald Add-on Repository → Look and feel →
Skin**.

The feed also publishes the separately installable **Bald XC Setup** program
add-on, which configures IPTV Simple from device-local Xtream Codes credentials,
and **Bald Process Info**, a playback info overlay for LibreELEC (a fork of
TinyPPI, which its author doesn't support; on CoreELEC, use TinyPPI from his
repository). It lives in `addons/script.bald.processinfo` as a git subtree of
dangerouslaser/script.bald.processinfo (branch `libreelec`).
`.github/workflows/follow-processinfo.yml` pulls it every morning, after the fork
has followed its upstream. When the fork has moved, it opens a
`processinfo-update` pull request once the feed and tests pass, or an issue
linking the branch if Actions may not open pull requests. If anything fails, it
opens a `processinfo-sync` issue instead.

Only tagged, committed revisions are published. The release workflow rejects a
tag whose version does not match `skin.bald/addon.xml`.
