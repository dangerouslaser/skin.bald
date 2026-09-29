"""scripts/focus.py: after a Move, select the moved entry again and keep focus on a Move button."""

import unittest

from kodi_includes import resolve_window
from scripts import focus


class FakeKodi:
    """A sidebar list whose entries change after `settle_after` waits, and which controls are visible."""

    def __init__(self, before, after, settle_after=3, visible=("9406", "9407"), focused=None):
        self.before, self.after, self.settle_after = before, after, settle_after
        self.visible, self.focused, self.waits, self.builtins = set(visible), focused, 0, []

    def entries(self):
        return self.after if self.waits >= self.settle_after else self.before

    def getInfoLabel(self, label):
        if label.endswith(".NumItems"):
            return str(len(self.entries()))
        index = int(label.split("ListItemAbsolute(")[1].split(")")[0])
        entry = self.entries()[index]
        return entry["label"] if label.endswith(".Label") else entry.get(label.split("Property(")[1].rstrip(")"), "")

    def getCondVisibility(self, condition):
        control = condition.split("(")[1].rstrip(")")
        if condition.startswith("Control.HasFocus"):
            return self.focused == control and self.waits >= self.settle_after
        return control in self.visible

    def executebuiltin(self, action):
        self.builtins.append(action)

    def wait(self, seconds):
        self.waits += 1
        return False


def hubs(*names):
    return [{"label": "Home", "kind": "home"}] + [{"label": n, "kind": "hub", "guid": "g-" + n} for n in names]


class KeepFocusTests(unittest.TestCase):
    def test_a_moved_hub_is_selected_again_once_the_list_settles(self):
        kodi = FakeKodi(hubs("Movies", "Anime"), hubs("Anime", "Movies"))
        focus.keep(kodi, "9300|9406|9407|guid|g-Anime|3", wait=kodi.wait)
        self.assertEqual(kodi.builtins, ["SetFocus(9300,1,absolute)", "SetFocus(9406)"])

    def test_the_other_button_takes_focus_when_the_entry_reached_an_end(self):
        kodi = FakeKodi(hubs("Movies", "Anime"), hubs("Anime", "Movies"), visible=("9407",))
        focus.keep(kodi, "9300|9406|9407|guid|g-Anime|3", wait=kodi.wait)
        self.assertEqual(kodi.builtins[-1], "SetFocus(9407)")

    def test_a_hub_without_a_guid_is_found_by_name(self):
        kodi = FakeKodi(hubs("Movies", "Anime"), hubs("Anime", "Movies"))
        focus.keep(kodi, "9300|9406|9407|Label|Movies|2", wait=kodi.wait)
        self.assertEqual(kodi.builtins[0], "SetFocus(9300,2,absolute)")

    def test_the_widget_editor_waits_for_skin_variables_to_refocus_the_list(self):
        kodi = FakeKodi([], [], visible=("9204", "9205"), focused="9100")
        focus.keep(kodi, "9100|9204|9205", wait=kodi.wait)
        self.assertEqual(kodi.builtins, ["SetFocus(9204)"])
        self.assertGreaterEqual(kodi.waits, 3)

    def test_it_gives_up_waiting_and_still_returns_focus(self):
        kodi = FakeKodi(hubs("Movies"), hubs("Movies"), settle_after=999)
        focus.keep(kodi, "9300|9406|9407|guid|g-Movies|2", wait=kodi.wait)
        self.assertEqual(kodi.builtins, ["SetFocus(9406)"])

    def test_every_move_button_keeps_focus(self):
        screens = resolve_window("Custom_1117_BaldHomeScreens.xml")
        widgets = resolve_window("Custom_1116_BaldHomeWidgets.xml")
        for window, button in ((screens, "9406"), (screens, "9407"), (screens, "9410"), (screens, "9411"),
                               (widgets, "9204"), (widgets, "9205")):
            clicks = [n.text for n in window.find(f".//control[@id='{button}']").findall("onclick")]
            with self.subTest(button=button):
                self.assertTrue(any(c.startswith(f"RunScript(skin.bald,keepfocus,") and f"|{button}|" in c
                                    for c in clicks), clicks)
                self.assertFalse(any(c.startswith("Control.Move(") for c in clicks))


if __name__ == "__main__":
    unittest.main()
