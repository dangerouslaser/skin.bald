"""Bald Helper service: Bald's keymaps (resources/lib/keymap.py), its blurred backgrounds (resources/lib/blur.py) and
its latency-sensitive skin actions (resources/lib/actions.py).

The blur follower and the action worker run on their own threads; the keymap manager runs here, on the thread whose
monitor receives the skin's notifications, and keeps working if either of the others cannot start.
"""

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib.keymap import POLL_SECONDS, Service


def start_blur():
    try:
        from resources.lib.blur import Follower

        follower = Follower(xbmc, xbmcvfs, xbmcgui)
        follower.start()
        return follower
    except Exception as error:  # noqa: BLE001 - the keymaps must not depend on the blur
        xbmc.log(f"script.bald.helper: blur did not start: {type(error).__name__}: {error}", xbmc.LOGERROR)
        return None


def start_actions():
    """The skin-action dispatcher and the monitor that feeds it (made on this thread, which runs the loop)."""
    try:
        from resources.lib.actions import Dispatcher, SkinScripts, make_monitor, skin_scripts_directory

        dispatcher = Dispatcher(xbmc, xbmcgui, SkinScripts(skin_scripts_directory(xbmcaddon)))
        monitor = make_monitor(xbmc, dispatcher)
        dispatcher.start()
        return dispatcher, monitor
    except Exception as error:  # noqa: BLE001 - the skin falls back to RunScript
        xbmc.log(f"script.bald.helper: actions did not start: {type(error).__name__}: {error}", xbmc.LOGERROR)
        return None, None


if __name__ == "__main__":
    blur = start_blur()
    actions, monitor = start_actions()
    try:
        if actions is not None:
            from resources.lib.actions import WAKE_SECONDS

            Service(xbmc, xbmcvfs).run(monitor, wake=WAKE_SECONDS, each=actions.refresh)
        else:
            Service(xbmc, xbmcvfs).run(wake=POLL_SECONDS)
    finally:
        if actions is not None:
            actions.stop()
        if blur is not None:
            blur.stop()
