# Bald XC Setup

Quick one-shot configurator for Kodi 22 and IPTV Simple 22.x.

It accepts an Xtream Codes server URL, username and password, generates a local extended M3U from the XC live-stream API, and writes that file plus the standard `xmltv.php` EPG URL into an existing IPTV Simple instance. The original instance XML is copied once to `instance-settings-N.xml.bald-xc-backup` before changes are applied.

The helper reads the XC live-category and live-stream APIs and generates a local extended M3U for IPTV Simple. This supports services whose `get.php` endpoint returns account metadata instead of a playlist, without requiring an always-running proxy service.

## Install

Install **Bald XC Setup** from the Bald Add-on Repository and launch it from Program add-ons. The guided setup asks for the server, username, password and stream format, lets you choose an IPTV Simple instance when more than one exists, and shows a final confirmation before changing anything. The add-on's **Configure** page has a single **Launch guided setup** action that opens the same flow.

Credentials are stored by Kodi in this add-on's settings and embedded in IPTV Simple's instance URL. They are redacted from this add-on's logs, but Kodi add-on settings are not an encrypted secret store.
