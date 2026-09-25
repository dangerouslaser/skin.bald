# Remote installation and updates

Bald publishes a Kodi repository feed from committed release tags. Development
work in an uncommitted checkout is never included.

## User installation

1. Visit `https://dangerouslaser.github.io/skin.bald/` and download
   `repository.bald-1.0.1.zip`.
2. In Kodi 22, choose **Add-ons → Install from zip file** and select that ZIP.
3. Choose **Install from repository → Bald Add-on Repository → Look and feel →
   Skin → Bald**.

The same repository also contains **Program add-ons → Bald XC Setup**. It asks
for device-local Xtream Codes credentials and configures a selected IPTV Simple
instance; credentials are never part of the repository feed or release ZIPs.

Kodi will subsequently discover new versions from the same feed according to
its normal add-on update settings.

## Publishing a skin update

1. Finish and validate the milestone, then commit and push it.
2. Update the version in `addon.xml` using Kodi's numeric `major.minor.patch`
   format and commit that change.
3. Create and push a matching tag, for example `v0.2.0`.
4. The `Publish Kodi repository` workflow packages that exact commit, validates
   the ZIPs and deploys the feed to GitHub Pages.

The workflow rejects mismatched tag and add-on versions. Enable GitHub Pages
with **Source: GitHub Actions** once for the repository if it is not already
enabled.

## Local validation

Run from the skin repository root:

```sh
python3 packaging/repository.bald/build_repository.py --output /tmp/bald-kodi-repo
python3 packaging/repository.bald/test_repository.py /tmp/bald-kodi-repo
```
