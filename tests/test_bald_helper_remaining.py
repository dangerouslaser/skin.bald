from pathlib import Path
import sys
import unittest

ADDON = Path(__file__).resolve().parents[1] / "addons" / "script.bald.helper"
sys.path.insert(0, str(ADDON))

from resources.lib import follow, remaining  # noqa: E402


class LeftTests(unittest.TestCase):
    def test_minutes_and_hours(self):
        for mins, pct, text in (("119", "70", "36m"), ("150", "20", "2h 0m"), ("161", "14", "2h 18m"),
                                ("45", "99", "1m"), ("119", "0", ""), ("119", "100", ""), ("", "50", ""), ("0", "50", "")):
            self.assertEqual(remaining.left(mins, pct), text, (mins, pct))


class Xbmc:
    def __init__(self, labels, skin="skin.bald"):
        self.labels, self.skin = labels, skin

    def getSkinDir(self):
        return self.skin

    def getInfoLabel(self, label):
        return self.labels.get(label, "")


class Window:
    def __init__(self):
        self.props = {}

    def setProperty(self, key, value):
        self.props[key] = value

    def clearProperty(self, key):
        self.props.pop(key, None)


class RemainingTests(unittest.TestCase):
    def test_publishes_the_located_items_time_left_and_clears_it(self):
        xbmc = Xbmc({"Container(9201).ListItem.Duration(mins)": "119", "Container(9201).ListItem.PercentPlayed": "70",
                     "Container(9201).ListItem.FileNameAndPath": "/movies/1917.mkv"})
        window = Window()
        step = remaining.Remaining(xbmc, window, lambda: 10000)
        located = [("Container(9201).ListItem.", None)]
        original = follow.locate
        follow.locate = lambda *_: located[0]
        try:
            step.tick()
            self.assertEqual(window.props, {"Bald.Remaining": "36m", "Bald.Remaining.For": "/movies/1917.mkv"})
            located[0] = (None, None)
            step.tick()
            self.assertEqual(window.props, {})
            located[0] = follow.HELD
            window.props["Bald.Remaining"] = "held"
            step.tick()
            self.assertEqual(window.props, {"Bald.Remaining": "held"}, "held: nothing changes")
            xbmc.skin = "skin.estuary"
            located[0] = ("Container(9201).ListItem.", None)
            step.tick()
            self.assertEqual(window.props, {"Bald.Remaining": "held"}, "rests under another skin")
        finally:
            follow.locate = original


if __name__ == "__main__":
    unittest.main()
