"""The Home screens with rows (shortcuts/generator/screens.xml) and their shipped rows, for tests."""

import json
from pathlib import Path


SHORTCUTS = Path(__file__).resolve().parents[1] / "shortcuts"
HUB_SLOTS = 8
# (screen, title, row base, main-menu entry)
SCREENS = (
    ("home", "Home", 9100, 9001),
    ("livetv", "LiveTV", 9050, 9004),
) + tuple((f"hub{n}", f"Hub{n}", 9100 + 100 * n, 9010 + n) for n in range(1, HUB_SLOTS + 1))


def menu(name):
    return json.loads((SHORTCUTS / f"skinvariables-shortcut-{name}.json").read_text())


def hubs():
    """The shipped hubs list: Movies and TV shows, each with its rows in "widgets"."""
    return menu("hubs")


def rows(screen):
    """A screen's shipped rows: Home's and Live TV's own menus, or the widgets of the hub in that slot (none past the
    end of the hubs list)."""
    if screen == "home":
        return menu("homewidgets")
    if screen == "livetv":
        return menu("livetvwidgets")
    position = int(screen[3:]) - 1
    listed = hubs()
    return listed[position].get("widgets", []) if position < len(listed) else []


def row_ids(screen):
    base = next(base for name, _, base, _ in SCREENS if name == screen)
    return [base + index for index in range(1, len(rows(screen)) + 1)]
