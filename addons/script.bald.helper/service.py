"""Bald Helper service: Bald's keymaps (resources/lib/keymap.py), its blurred backgrounds (resources/lib/blur.py),
its latency-sensitive skin actions (resources/lib/actions.py), its online ratings (resources/lib/ratings.py), its
spoiler stills (resources/lib/spoilers.py), its typeface choice (resources/lib/fontset.py) and its tidied
weather values (resources/lib/weather.py).

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
        from resources.lib.blur import Follower, Warmer

        follower = Follower(xbmc, xbmcvfs, xbmcgui)
        follower.warmer = Warmer(xbmc, follower)  # Home rows' backdrops blurred ahead
        follower.start()
    except Exception as error:  # noqa: BLE001 - the keymaps must not depend on the blur
        xbmc.log(f"script.bald.helper: blur did not start: {type(error).__name__}: {error}", xbmc.LOGERROR)
        return None
    try:
        follower.warmer.start()
    except Exception as error:  # noqa: BLE001 - the follower works without the warm-up
        xbmc.log(f"script.bald.helper: blur warm-up did not start: {type(error).__name__}: {error}", xbmc.LOGWARNING)
    return follower


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


def start_fontset():
    """The keeper of Bald's typeface choice; its step runs in the keymap loop."""
    try:
        from resources.lib.fontset import Keeper

        return Keeper(xbmc)
    except Exception as error:  # noqa: BLE001 - the fontset stays whatever Kodi has
        xbmc.log(f"script.bald.helper: fontset keeper did not start: {type(error).__name__}: {error}", xbmc.LOGERROR)
        return None


def start_weather():
    """The tidier of forecast values for Bald's weather rows; its step runs in the keymap loop."""
    try:
        import time

        from resources.lib.weather import Tidier

        return Tidier(xbmc, xbmcgui.Window(10000), time.monotonic)
    except Exception as error:  # noqa: BLE001 - the rows show the add-on's own values
        xbmc.log(f"script.bald.helper: weather tidier did not start: {type(error).__name__}: {error}", xbmc.LOGERROR)
        return None


if __name__ == "__main__":
    blur = start_blur()
    ratings, player = start_ratings()
    spoilers, spoilers_monitor = start_spoilers()
    actions, monitor = start_actions()
    fontset = start_fontset()
    weather = start_weather()
    loop_steps = tuple(step.tick for step in (fontset, weather) if step is not None)
    try:
        if actions is not None:
            from resources.lib.actions import WAKE_SECONDS

            Service(xbmc, xbmcvfs).run(monitor, wake=WAKE_SECONDS, each=(actions.refresh, *loop_steps))
        else:
            Service(xbmc, xbmcvfs).run(wake=POLL_SECONDS, each=loop_steps)
    finally:
        if actions is not None:
            actions.stop()
        if ratings is not None:
            ratings.stop()
        if blur is not None:
            blur.warmer.stop()
            blur.stop()
        if spoilers is not None:
            spoilers.stop()
