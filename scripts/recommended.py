"""Kodi settings Bald recommends, applied with the user's consent.

RunScript(skin.bald,recommended)         Bald Settings > Appearance > Behavior: offer them, or say they are in place.
RunScript(skin.bald,recommended,prompt)  Home, once: offer them only if any differ, and stay quiet otherwise.

Both change core settings through JSON-RPC (Settings.GetSettingValue / SetSettingValue) and only after a yes.
"""
import json

# (setting id, recommended value). Values checked against Kodi 22's settings.xml and the video select action enum
# (KODI::VIDEO::GUILIB::Action: 0 choose, 3 show information, 7 queue, 8 play).
RECOMMENDED = (
    ("filelists.showparentdiritems", False),  # No ".." item at the top of every list
    ("myvideos.selectaction", 3),             # Select on a movie or episode shows its information
)
# Bald's en_gb strings (31837-31841).
TITLE, PROMPT, APPLY, ALREADY, DONE = 31837, 31838, 31839, 31840, 31841
STRING_IDS = (TITLE, PROMPT, APPLY, ALREADY, DONE)


def rpc(xbmc, method, params):
    response = json.loads(xbmc.executeJSONRPC(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})))
    if "error" in response:
        raise RuntimeError("{} failed: {}".format(method, response["error"]))
    return response.get("result")


def pending(xbmc):
    """The recommended settings Kodi does not have yet, as (id, value)."""
    return [(setting, value) for setting, value in RECOMMENDED
            if rpc(xbmc, "Settings.GetSettingValue", {"setting": setting}).get("value") != value]


def apply(xbmc, xbmcgui, mode=""):
    text = xbmc.getLocalizedString
    dialog = xbmcgui.Dialog()
    todo = pending(xbmc)
    if not todo:
        if mode != "prompt":
            dialog.notification(text(TITLE), text(ALREADY))
        return False
    if not dialog.yesno(text(TITLE), text(PROMPT), yeslabel=text(APPLY)):
        return False
    for setting, value in todo:
        rpc(xbmc, "Settings.SetSettingValue", {"setting": setting, "value": value})
    dialog.notification(text(TITLE), text(DONE))
    return True
