"""Bald Helper service: Bald's keymaps (resources/lib/keymap.py) and its blurred backgrounds (resources/lib/blur.py).

The blur follower runs on its own threads; the keymap manager runs here and keeps working if the blur cannot start.
"""

import xbmc
import xbmcgui
import xbmcvfs

from resources.lib.keymap import Service


def start_blur():
    try:
        from resources.lib.blur import Follower

        follower = Follower(xbmc, xbmcvfs, xbmcgui)
        follower.start()
        return follower
    except Exception as error:  # noqa: BLE001 - the keymaps must not depend on the blur
        xbmc.log(f"script.bald.helper: blur did not start: {type(error).__name__}: {error}", xbmc.LOGERROR)
        return None


if __name__ == "__main__":
    blur = start_blur()
    try:
        Service(xbmc, xbmcvfs).run()
    finally:
        if blur is not None:
            blur.stop()
