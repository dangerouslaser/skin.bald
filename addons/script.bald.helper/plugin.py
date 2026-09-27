"""Bald Helper's plugin entry: the OSD cast panel's list and the settings actions (resources/lib/plugin.py)."""

import sys

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from resources.lib.plugin import run

if __name__ == "__main__":
    run(sys.argv, xbmc, xbmcgui, xbmcplugin, xbmcaddon, xbmcvfs)
