# Bald XC Setup

Quick one-shot configurator for Kodi 22 and IPTV Simple 22.x.

It accepts an Xtream Codes server URL, username and password, then writes the standard `get.php` M3U and `xmltv.php` EPG URLs into an existing IPTV Simple instance. The original instance XML is copied once to `instance-settings-N.xml.bald-xc-backup` before changes are applied.

This is intentionally not a streaming proxy. IPTV Simple can consume standard XC URLs directly, avoiding another always-running service and another place to expose credentials.

## Install

Install **Bald XC Setup** from the Bald Add-on Repository and launch it from Program add-ons. The guided setup asks for the server, username, password and stream format, lets you choose an IPTV Simple instance when more than one exists, and shows a final confirmation before changing anything. The add-on's **Configure** page has a single **Launch guided setup** action that opens the same flow.

Credentials are stored by Kodi in this add-on's settings and embedded in IPTV Simple's instance URL. They are redacted from this add-on's logs, but Kodi add-on settings are not an encrypted secret store.
