"""Read Home's main menu (grouplist 9000) the way Kodi resolves it, for tests.

Entries are the resolved buttons (Bald_HomeMenuButton, directly or through Bald_HomeMenuHub and
Bald_HomeMenuLiveTV), with includes expanded and parameters substituted from the shipped files alone (the
fallback in Includes_Bald_HomeDefaults.xml stands in for the per-install build)."""

import re
from functools import lru_cache

from kodi_includes import Skin


PREVIEW = re.compile(r"^SetProperty\(Bald\.MenuPreview,([^,]+),home\)$")


@lru_cache(maxsize=1)
def _home():
    return Skin().window("Home.xml")


def menu():
    return next(node for node in _home().iter("control") if node.get("id") == "9000")


def entries():
    """The menu's buttons in their menu order."""
    return [node for node in menu().findall("control") if node.get("type") == "button"]


def previewed(node):
    """The screen a button previews (its Bald.MenuPreview value); labels are localized, so they are not a stable key."""
    return next(PREVIEW.match(child.text).group(1) for child in node.findall("onfocus") if PREVIEW.match(child.text or ""))


def entry(preview):
    for node in entries():
        if previewed(node) == preview:
            return node
    raise AssertionError(f"no menu entry {preview}")


def control(control_id):
    return next(node for node in _home().iter("control") if node.get("id") == str(control_id))


def actions(node, tag):
    return [(child.get("condition"), child.text) for child in node.findall(tag)]


def select_actions(node):
    return actions(node, "onclick")


def setting(on):
    """Expression bodies with Appearance > Behavior "Select on a hub opens its library" (Bald.HubSelectOpens) fixed on
    or off, for conditions.equivalent / implies.
    Only Includes_Bald_Home.xml's expressions are expanded: the generated per-slot names (Bald_HasRows_hub1 and so on,
    constants in the shipped fallback) stay atoms, so a condition is compared for every hub, with or without rows."""
    import xml.etree.ElementTree as ET
    from kodi_includes import SKIN
    root = ET.parse(SKIN / "Includes_Bald_Home.xml").getroot()
    bodies = {node.get("name"): node.text or "" for node in root.findall("expression")}
    bodies["Bald_SelectOpens"] = "true" if on else "false"
    return bodies


def live(pairs, bodies):
    """The (condition, action) pairs whose condition can hold under these bodies."""
    from conditions import implies
    return [(cond, action) for cond, action in pairs if not implies(cond or "true", "false", bodies)]
