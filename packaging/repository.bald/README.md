# Bald Add-on Repository

This Kodi repository add-on points Kodi 22 at the Bald release feed hosted by
GitHub Pages. Install `repository.bald-1.0.0.zip`, then install **Bald** from
**Add-ons → Install from repository → Bald Add-on Repository → Look and feel →
Skin**.

The feed also publishes the separately installable **Bald XC Setup** program
add-on, which configures IPTV Simple from device-local Xtream Codes credentials,
and **TinyPPI**, the player process info overlay, from the LibreELEC fork
(dangerouslaser/script.tinyppi, branch `libreelec`). It lives in
`addons/script.tinyppi` as a git subtree; update it with
`git subtree pull --prefix=addons/script.tinyppi https://github.com/dangerouslaser/script.tinyppi.git libreelec --squash`.
`.github/workflows/follow-tinyppi.yml` does that pull every morning, after the
fork has followed its upstream. When the fork has moved, it opens a
`tinyppi-update` pull request once the feed and tests pass. If anything fails, it
opens a `tinyppi-sync` issue instead.

Only tagged, committed revisions are published. The release workflow rejects a
tag whose version does not match `skin.bald/addon.xml`.
