"""Keep focus on a Move button after it moves an entry (Home Screens 1117, the widget editor 1116).

RunScript(skin.bald,keepfocus,<list>|<button>|<other button>|<property>|<value>|<old position>)

Moving an entry changes the sidebar list under the detail pane: Skin Variables rewrites and reloads the hubs or rows
list (the entries vanish for a moment), and Live TV's entry reappears at its new place. The list's selection then lands
on another entry, the Move button hides for it, and Kodi returns focus to the window's default control, the sidebar.
The widget editor asks Skin Variables to refocus the list on the moved row (refocus::9100), which selects it but also
focuses the list.

So after a move this waits for the list to settle, selects the moved entry again and focuses the Move button, or the
other Move button when the entry reached an end (Move up hides at the top). With <property> empty (the widget editor)
the list is already on the moved entry once it has focus; otherwise the entry is the one whose Property(<property>) is
<value> (a hub's guid, Live TV's kind; <property> Label matches the name), once it is no longer at <old position>
(1-based, as Container.CurrentItem).
"""

TIMEOUT = 3.0
STEP = 0.1
SETTLE = 0.2


def parse(spec):
    parts = (spec.split("|") + [""] * 6)[:6]
    list_id, button, other, prop, value, old = (part.strip() for part in parts)
    return list_id, button, other, prop, value, old


def find(xbmc, list_id, prop, value):
    """1-based position of the entry whose Property(prop) is value, or None."""
    count = xbmc.getInfoLabel("Container({}).NumItems".format(list_id))
    for index in range(int(count) if count.isdigit() else 0):
        field = "Label" if prop == "Label" else "Property({})".format(prop)
        label = "Container({}).ListItemAbsolute({}).{}".format(list_id, index, field)
        if xbmc.getInfoLabel(label) == value:
            return index + 1
    return None


def keep(xbmc, spec, wait=None):
    """Select the moved entry in the list and focus the Move button (see the module docstring)."""
    list_id, button, other, prop, value, old = parse(spec)
    if not list_id or not button:
        return
    if wait is None:
        monitor = xbmc.Monitor()
        wait = monitor.waitForAbort
    waited = 0.0
    while waited < TIMEOUT:
        if prop:
            position = find(xbmc, list_id, prop, value)
            if position is not None and str(position) != old:
                xbmc.executebuiltin("SetFocus({},{},absolute)".format(list_id, position - 1))
                break
        elif xbmc.getCondVisibility("Control.HasFocus({})".format(list_id)):
            break
        if wait(STEP):
            return
        waited += STEP
    # The detail pane follows the new selection a frame later: let its buttons show or hide first.
    if wait(SETTLE):
        return
    for target in (button, other):
        if target and xbmc.getCondVisibility("Control.IsVisible({})".format(target)):
            xbmc.executebuiltin("SetFocus({})".format(target))
            return
