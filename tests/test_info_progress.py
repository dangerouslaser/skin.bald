"""The info pages' progress bars (Includes_Bald_InfoPages.xml, Includes_Bald_InfoTV.xml) match Home's caption: one
progress control whose own background is the track (a separate track image under it drew the fill offset), and on the
movie page the time left from Bald Helper (Bald.Remaining), not the percentage watched."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

XML = Path(__file__).resolve().parents[1] / "1080i"


def progress_groups(name):
    root = ET.parse(XML / name).getroot()
    for group in root.iter("control"):
        children = list(group.findall("control"))
        if any(c.get("type") == "progress" and c.findtext("info") == "ListItem.PercentPlayed" for c in children):
            yield group, children


class InfoProgressTests(unittest.TestCase):
    def test_the_track_is_the_progress_controls_own_background(self):
        found = 0
        for name in ("Includes_Bald_InfoPages.xml", "Includes_Bald_InfoTV.xml"):
            for group, children in progress_groups(name):
                found += 1
                bar = next(c for c in children if c.get("type") == "progress")
                self.assertEqual(bar.find("texturebg").get("colordiffuse"), "bald_mark_track")
                self.assertFalse([c for c in children if c.get("type") == "image"
                                  and c.findtext("texture") == "bald/bar.png"], name)
        self.assertEqual(found, 2)

    def test_the_movie_page_shows_the_time_left(self):
        group, children = next(progress_groups("Includes_Bald_InfoPages.xml"))
        labels = {c.findtext("label"): c.findtext("visible") for c in children if c.get("type") == "label"}
        self.assertIn("$INFO[Window(home).Property(Bald.Remaining),, $LOCALIZE[31417]]", labels)
        self.assertIn("Bald.Remaining.For", labels["$INFO[Window(home).Property(Bald.Remaining),, $LOCALIZE[31417]]"])
        # The percentage only without Bald Helper.
        self.assertEqual(labels["$INFO[ListItem.PercentPlayed,,% $LOCALIZE[31715]]"], "!$EXP[Bald_HasHelper]")


if __name__ == "__main__":
    unittest.main()
