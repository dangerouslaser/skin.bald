"""Bald Helper service: Bald's keymaps (resources/lib/keymap.py), its blurred backgrounds (resources/lib/blur.py),
its latency-sensitive skin actions (resources/lib/actions.py), its online ratings (resources/lib/ratings.py) and its
spoiler stills (resources/lib/spoilers.py).

The blur follower, the ratings follower and the action worker run on their own threads; the keymap manager runs here,
on the thread whose monitor receives the skin's notifications (and whose player receives playback events), and keeps
working if any of the others cannot start.
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


def start_ratings():
    """The ratings follower (started) and the player that feeds the playing movie's ratings (made on this thread,
    which runs the loop, so that Kodi delivers its callbacks)."""
    try:
        from resources.lib.ratings import make_player, start

        follower, watcher = start(xbmc, xbmcgui, xbmcvfs, xbmcaddon)
        player = make_player(xbmc, watcher)
        if xbmc.Player().isPlayingVideo():
            watcher.started()  # the service (re)started during playback
        return follower, player
    except Exception as error:  # noqa: BLE001 - the skin keeps TMDb Helper's ratings
        xbmc.log(f"script.bald.helper: ratings did not start: {type(error).__name__}: {error}", xbmc.LOGERROR)
        return None, None


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


def start_spoilers():
    """The spoiler stills (resources/lib/spoilers.py) and their library monitor (made on this thread, which runs the
    loop, so Kodi delivers its notifications)."""
    try:
        from resources.lib.spoilers import Spoilers, make_monitor

        spoilers = Spoilers(xbmc, xbmcvfs, xbmcgui)
        spoilers_monitor = make_monitor(xbmc, spoilers)
        spoilers.start()
        return spoilers, spoilers_monitor
    except Exception as error:  # noqa: BLE001 - Bald draws its placeholders without the stills
        xbmc.log(f"script.bald.helper: spoilers did not start: {type(error).__name__}: {error}", xbmc.LOGERROR)
        return None, None


if __name__ == "__main__":
    blur = start_blur()
    ratings, player = start_ratings()
    spoilers, spoilers_monitor = start_spoilers()
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
        if ratings is not None:
            ratings.stop()
        if blur is not None:
            blur.stop()
        if spoilers is not None:
            spoilers.stop()
