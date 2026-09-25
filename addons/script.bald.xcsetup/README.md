# Bald XC Setup

Quick one-shot configurator for Kodi 22 and IPTV Simple 22.x.

It accepts an Xtream Codes server URL, username and password, then writes the standard `get.php` M3U and `xmltv.php` EPG URLs into an existing IPTV Simple instance. The original instance XML is copied once to `instance-settings-N.xml.bald-xc-backup` before changes are applied.

This is intentionally not a streaming proxy. IPTV Simple can consume standard XC URLs directly, avoiding another always-running service and another place to expose credentials.

## Install

Zip the `script.bald.xcsetup` folder so `addon.xml` is at the top level of the archive, then use Kodi's **Install from zip file**. Launch **Bald XC Setup** from Program add-ons, enter the credentials, close Settings, and approve the confirmation.

Credentials are stored by Kodi in this add-on's settings and embedded in IPTV Simple's instance URL. They are redacted from this add-on's logs, but Kodi add-on settings are not an encrypted secret store.
