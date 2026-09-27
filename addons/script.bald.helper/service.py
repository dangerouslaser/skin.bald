"""Bald Helper service: keeps Bald's "Open TV shows on their info page" keymap in step with the skin."""

import xbmc
import xbmcvfs

from resources.lib.keymap import Service


if __name__ == "__main__":
    Service(xbmc, xbmcvfs).run()
