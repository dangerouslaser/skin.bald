"""Appearance's clock, tile title and watch-mark options (Custom_1118_BaldAppearance.xml): the rows, what each Select
does in every state, the labels they show, and that the skin reads each setting where it draws the thing it names."""

import re
import unittest
import xml.etree.ElementTree as ET

from conditions import equivalent, implies, parse
from kodi_includes import SKIN, Skin, include_definitions, resolve_window
from skin_strings import PO

APPEARANCE = "Custom_1118_BaldAppearance.xml"
DE = PO.parents[1] / "resource.language.de_de" / "strings.po"
GENERATED = "script-skinvariables-generator-includes.xml"
# Row, category item, settings level.
ROWS = {"9632": ("7", "basic"), "9633": ("7", "standard"), "9634": ("7", "standard"),
        "9635": ("2", "standard"), "9636": ("2", "advanced"), "9637": ("2", "advanced")}
STRING_IDS = range(31334, 31341)


def evaluate(tree, atom):
    """A parsed condition's value, each atom's truth given by `atom(text)`."""
    if isinstance(tree, bool):
        return tree
    kind, value = tree
    if kind == "atom":
        return atom(value)
    if kind == "not":
        return not evaluate(value, atom)
    results = [evaluate(term, atom) for term in value]
    return all(results) if kind == "and" else any(results)


def string_state(setting, stored):
    """Atoms of Skin.String(`setting`) holding `stored` (None: unset); anything else is an error."""
    name = re.escape(setting)

    def atom(text):
        if text == f"String.IsEmpty(Skin.String({setting}))":
            return stored is None
        match = re.fullmatch(rf"(?:String\.IsEqual\(Skin\.String\({name}\),(\w+)\)|Skin\.String\({name},(\w+)\))", text)
        if not match:
            raise AssertionError(f"unexpected atom {text}")
        return stored == (match.group(1) or match.group(2))
    return atom


def minute_state(minute):
    """Atoms of System.Time(start,end) at `minute` of the day, as Kodi reads them (minute of day, end exclusive,
    wrapping when end is before start)."""
    def atom(text):
        match = re.fullmatch(r"System\.Time\((\d\d):(\d\d),(\d\d):(\d\d)\)", text)
        if not match:
            raise AssertionError(f"unexpected atom {text}")
        start, end = int(match.group(1)) * 60 + int(match.group(2)), int(match.group(3)) * 60 + int(match.group(4))
        return start <= minute < end if start <= end else minute >= start or minute < end
    return atom


class AppearanceOptionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        definitions = include_definitions()
        cls.window = resolve_window(APPEARANCE, definitions)
        cls.skin = Skin()

    def row(self, control_id):
        found = [node for node in self.window.iter("control") if node.get("id") == control_id]
        self.assertEqual(len(found), 1, control_id)
        return found[0]

    def values(self, name):
        return [(node.get("condition"), node.text or "") for node in self.skin.variables[name].findall("value")]

    def pick(self, name, atom):
        """What variable `name` shows: its first value whose condition holds, as Kodi picks it."""
        for condition, text in self.values(name):
            if condition is None or evaluate(parse(condition), atom):
                return text
        return ""

    def cycle(self, control_id, setting, order):
        """Stored values Select steps through from unset, checked in every state including an unknown value: exactly one
        onclick fires (Kodi evaluates every condition before it runs any action)."""
        clicks = [(node.get("condition"), node.text) for node in self.row(control_id).findall("onclick")]
        states = [None, *order, "unknown"]
        for stored in states:
            fired = [action for condition, action in clicks if evaluate(parse(condition), string_state(setting, stored))]
            self.assertEqual(len(fired), 1, f"{control_id} with {stored}: {fired}")
            if stored in order[:-1]:
                self.assertEqual(fired[0], f"Skin.SetString({setting},{order[order.index(stored) + 1]})")
            elif stored is None:
                self.assertEqual(fired[0], f"Skin.SetString({setting},{order[0]})")
            else:
                self.assertEqual(fired[0], f"Skin.Reset({setting})", stored)

    # ---- rows ----

    def test_rows_sit_in_their_category_at_their_level(self):
        items = [item.get("id") for item in self.window.findall(".//control[@id='9500']/content/item")]
        self.assertEqual(items.index("7"), items.index("3") + 1, "Date & time follows Behavior")
        date_time = self.window.find(".//control[@id='9500']/content/item[@id='7']")
        self.assertEqual(date_time.findtext("label"), "$LOCALIZE[14063]")  # Kodi's "Date & time"
        self.assertIsNone(date_time.find("visible"), "the time format row is Basic, so the category always shows")
        for control_id, (item, level) in ROWS.items():
            with self.subTest(row=control_id):
                visible = " + ".join(node.text for node in self.row(control_id).findall("visible"))
                self.assertTrue(implies(visible, f"Container(9500).HasFocus({item})"))
                self.assertIn(f"$EXP[Bald_SettingsLevel_{level}]", visible)

    def test_ids_are_recorded(self):
        ids = (SKIN / "IDs").read_text()
        self.assertIn("9632-9634", ids)
        self.assertIn("9635-9637", ids)

    # ---- time format ----

    def test_time_format_cycles_region_12_24(self):
        self.cycle("9632", "Bald.ClockFormat", ["12", "24"])
        row = self.row("9632")
        self.assertEqual(row.findtext("label"), "$LOCALIZE[14107]")  # Kodi's "Time format"
        self.assertEqual(row.findtext("label2"), "$VAR[Bald_ClockFormatLabel]")
        # Kodi's "Region default format", "12-hour clock", "24-hour clock"; an unknown value reads as the region.
        for stored, label in ((None, "14271"), ("12", "12383"), ("24", "12384"), ("unknown", "14271")):
            self.assertEqual(self.pick("Bald_ClockFormatLabel", string_state("Bald.ClockFormat", stored)),
                             f"$LOCALIZE[{label}]")

    def test_clock_variables_follow_the_format(self):
        cases = {
            "Bald_Clock": {None: "$INFO[System.Time(hh:mm)]", "12": "$INFO[System.Time(h)]:$INFO[System.Time(mm)]",
                           "24": "$VAR[Bald_Clock24]", "unknown": "$INFO[System.Time(hh:mm)]"},
            "Bald_ClockTime": {None: "$INFO[System.Time]", "24": "$VAR[Bald_Clock24]", "unknown": "$INFO[System.Time]"},
        }
        for name, expected in cases.items():
            for stored, text in expected.items():
                with self.subTest(variable=name, stored=stored):
                    atom = string_state("Bald.ClockFormat", stored)
                    self.assertEqual(self.pick(name, lambda a: False if a.startswith("System.Time(") else atom(a)), text)

    def test_twelve_hour_header_clock_adds_kodis_am_and_pm(self):
        def at(minute):
            fmt = string_state("Bald.ClockFormat", "12")
            clock = minute_state(minute)
            return self.pick("Bald_ClockTime", lambda a: clock(a) if a.startswith("System.Time(") else fmt(a))
        self.assertTrue(at(0).endswith(" $LOCALIZE[378]"))       # 00:00 is 12 AM
        self.assertTrue(at(11 * 60 + 59).endswith(" $LOCALIZE[378]"))
        self.assertTrue(at(12 * 60).endswith(" $LOCALIZE[379]"))  # noon is 12 PM
        self.assertTrue(at(23 * 60 + 59).endswith(" $LOCALIZE[379]"))

    def test_24_hour_clock_names_every_hour_of_the_day(self):
        conditioned = [condition for condition, _ in self.values("Bald_Clock24") if condition]
        self.assertEqual(len(conditioned), 24)
        for minute in range(0, 24 * 60):
            clock = minute_state(minute)
            held = [condition for condition in conditioned if evaluate(parse(condition), clock)]
            self.assertEqual(len(held), 1, minute)
            self.assertEqual(self.pick("Bald_Clock24", clock), f"{minute // 60:02d}:$INFO[System.Time(mm)]")

    def test_every_clock_bald_draws_reads_the_clock_variables(self):
        # No label shows System.Time directly outside the clock variables; timestamps in actions are not clocks.
        for path in sorted(SKIN.glob("*.xml")):
            if path.name == GENERATED:
                continue
            root = ET.parse(path).getroot()
            clock_values = {id(value) for var in root.iter("variable") if var.get("name", "").startswith("Bald_Clock")
                            for value in var}
            for node in root.iter():
                if node.tag in ("label", "label2", "value") and id(node) not in clock_values:
                    with self.subTest(file=path.name):
                        self.assertNotIn("System.Time", node.text or "")
        uses = {"Includes_Bald_Home.xml": "$VAR[Bald_Clock]", "Includes_Bald_Playback.xml": "$VAR[Bald_Clock]",
                "Includes_Bald_PVR.xml": "$VAR[Bald_ClockDateTime]$VAR[Bald_HeaderWeatherSuffix]",
                "MyPVRGuide.xml": "$VAR[Bald_ClockDateTime]",
                "LoginScreen.xml": "$VAR[Bald_ClockTime]"}
        for name, label in uses.items():
            self.assertIn(f"<label>{label}</label>", (SKIN / name).read_text(), name)

    # ---- date and Home's clock ----

    def test_date_and_home_clock_switches(self):
        for control_id, setting in (("9633", "Bald.HideClockDate"), ("9634", "Bald.HideHomeClock")):
            row = self.row(control_id)
            self.assertEqual(row.get("type"), "radiobutton")
            self.assertEqual(row.findtext("onclick"), f"Skin.ToggleSetting({setting})")
            self.assertTrue(equivalent(row.findtext("selected"), f"!Skin.HasSetting({setting})"), "on by default")
        home = resolve_window("Home.xml")
        clock = [node for node in home.iter("control") if node.findtext("label") == "$VAR[Bald_Clock]"]
        self.assertEqual(len(clock), 1)
        group = next(parent for parent in home.iter("control") if clock[0] in list(parent))
        self.assertTrue(equivalent(group.findtext("visible"), "!Skin.HasSetting(Bald.HideHomeClock)"))
        date = next(node for node in group.findall("control") if node.findtext("font") == "Bald_Date")
        self.assertTrue(equivalent(date.findtext("visible"), "!Skin.HasSetting(Bald.HideClockDate)"))
        # Three steps down in size and ink (Bald_HomeClock): clock 132 ink, date 22 ink70 at 148. The clock sits 5 px
        # left so its digits' side bearing lines their ink up with the date's; its right edge stays on the margin.
        self.assertEqual((clock[0].findtext("font"), clock[0].findtext("textcolor")), ("Bald_Clock", "bald_ink"))
        self.assertEqual((clock[0].findtext("left"), clock[0].findtext("width")), ("-5", "389"))
        self.assertEqual((date.findtext("top"), date.findtext("textcolor")), ("148", "bald_ink70"))
        self.assertEqual((group.findtext("left"), group.findtext("top"), group.findtext("width")),
                         ("1440", "104", "384"))
        self.assertEqual(self.pick("Bald_ClockDateTime", lambda a: a == "Skin.HasSetting(Bald.HideClockDate)"),
                         "$VAR[Bald_ClockTime]")
        self.assertEqual(self.pick("Bald_ClockDateTime", lambda a: False), "$INFO[System.Date] · $VAR[Bald_ClockTime]")

    # ---- weather in headers and on Home ----

    def test_header_weather_reaches_the_bald_headers_and_home(self):
        # Bald's library views hide Estuary's TopBar, so the setting must reach Bald's own header meta lines.
        for name in ("View_510_Bald_Posters.xml", "View_520_Bald_TV.xml", "Includes_Bald_PVR.xml"):
            self.assertIn("$VAR[Bald_HeaderWeatherSuffix]</label>", (SKIN / name).read_text(), name)
        # The guide's date and time fill its header line, so the weather has a line of its own under them, as on Home.
        guide = ET.parse(SKIN / "MyPVRGuide.xml").getroot()
        line = next(n for n in guide.iter("control") if n.findtext("label") == "$VAR[Bald_HeaderWeather]")
        self.assertEqual((line.findtext("font"), line.findtext("textcolor"), line.findtext("align")),
                         ("Bald_Hint", "bald_ink45", "right"))
        home = resolve_window("Home.xml")
        weather = [node for node in home.iter("control") if node.findtext("label") == "$VAR[Bald_HeaderWeather]"]
        self.assertEqual(len(weather), 2, "under the date, or in its place")
        for node in weather:
            self.assertIn("$EXP[Bald_HeaderWeatherOn]", node.findtext("visible"))
            # Smaller and dimmer than the date line (Bald_Date 22, bald_ink70), so the two never read as one.
            self.assertEqual((node.findtext("font"), node.findtext("textcolor")), ("Bald_Hint", "bald_ink45"))
        tops = {("!" in node.findtext("visible").split("+")[-1]): node.findtext("top") for node in weather}
        self.assertEqual(tops, {False: "181", True: "150"}, "28 px baseline step under the date; else in its place")
        clock = next(parent for parent in home.iter("control") if weather[0] in list(parent))
        self.assertTrue(all(node in list(clock) for node in weather), "in the clock group, hidden with Home's clock")
        # The block ends above the caption title's highest line (332) and so the menu (395).
        self.assertLessEqual(max(int(clock.findtext("top")) + int(node.findtext("top")) + int(node.findtext("height"))
                                 for node in weather), 332)
        common = (SKIN / "Includes_Bald_Common.xml").read_text()
        self.assertRegex(common, r'name="Bald_HeaderWeatherOn">\[Skin.HasSetting\(Bald.HeaderWeather\)')

    # ---- titles on Home tiles ----

    def test_tile_titles_cycle_none_focus_always(self):
        self.cycle("9635", "Bald.TileTitles", ["focus", "always"])
        self.assertEqual(self.row("9635").findtext("label2"), "$VAR[Bald_TileTitlesLabel]")
        for stored, label in ((None, "$LOCALIZE[20420]"), ("focus", "$LOCALIZE[31338]"), ("always", "$LOCALIZE[20422]"),
                              ("unknown", "$LOCALIZE[20420]")):
            self.assertEqual(self.pick("Bald_TileTitlesLabel", string_state("Bald.TileTitles", stored)), label)

    def test_every_home_row_style_offers_titles_except_logo_and_text(self):
        home = (SKIN / "Includes_Bald_Home.xml").read_text()
        root = ET.fromstring(home)
        tiles = {node.get("name"): node for node in root.findall("include") if node.get("name", "").startswith("Bald_RowTiles_")}
        landscape = root.find("include[@name='Bald_RowLandscape']")
        # Square and weather rows share Bald_RowSquare; weather passes an empty include as its title (the tile's face
        # already names the day or hour).
        square = root.find("include[@name='Bald_RowSquare']")
        self.assertEqual(square.findtext("param[@name='caption']"), "Bald_TileTitle")
        weather = tiles["Bald_RowTiles_weather"].find("include[@content='Bald_RowSquare']")
        self.assertEqual(weather.findtext("param[@name='caption']"), "Bald_TileOverlayNone")
        for style, node, content in (("poster", tiles["Bald_RowTiles_poster"], "Bald_TileTitle"),
                                     ("square", square.find("definition"), "$PARAM[caption]")):
            with self.subTest(style=style):
                item = node.find(f"itemlayout/include[@content='{content}']")
                focused = node.find(f"focusedlayout//include[@content='{content}']")
                self.assertEqual(item.findtext("param[@name='visible']"), "$EXP[Bald_TileTitlesAlways]")
                self.assertEqual(focused.findtext("param[@name='visible']"), "$EXP[Bald_TileTitlesFocused]")
                self.assertEqual(focused.findtext("param[@name='pop']"), "102.5", "the title pops with the tile")
        item = landscape.find("definition/itemlayout/include[@content='Bald_TileTitle']")
        focused = landscape.find("definition/focusedlayout//include[@content='Bald_TileTitle']")
        self.assertIn("$EXP[Bald_TileTitlesAlways]", item.findtext("param[@name='visible']"))
        self.assertIn("$EXP[Bald_TileTitlesFocused]", focused.findtext("param[@name='visible']"))
        for style in ("logo", "text"):
            call = tiles[f"Bald_RowTiles_{style}"].find("include[@content='Bald_RowLandscape']")
            self.assertEqual(call.findtext("param[@name='show_title']"), "false", style)
        # Unset draws no titles (Bald's default); focus only on the focused tile while no overlay is open.
        self.assertTrue(implies("$EXP[Bald_TileTitlesAlways]", "String.IsEqual(Skin.String(Bald.TileTitles),always)"))
        self.assertTrue(equivalent("$EXP[Bald_TileTitlesFocused]",
                                   "String.IsEqual(Skin.String(Bald.TileTitles),always) | "
                                   "[String.IsEqual(Skin.String(Bald.TileTitles),focus) + !$EXP[Bald_OverlayOpen]]"))

    # ---- watch-state marks ----

    def test_watch_marks_switches_reach_cards_and_list_rows(self):
        for control_id, setting, expression in (("9636", "Bald.HideWatchedMarks", "Bald_ShowWatchedMarks"),
                                                ("9637", "Bald.HideProgressMarks", "Bald_ShowProgressMarks")):
            row = self.row(control_id)
            self.assertEqual(row.findtext("onclick"), f"Skin.ToggleSetting({setting})")
            self.assertTrue(equivalent(row.findtext("selected"), f"$EXP[{expression}]"), "on by default")
            for name in ("Includes_Bald_InfoTV.xml", "Includes_Bald_LibraryList.xml"):
                self.assertIn(f"$EXP[{expression}]", (SKIN / name).read_text(), name)

    # ---- strings ----

    def test_new_strings_are_translated_in_german(self):
        for path in (PO, DE):
            text = path.read_text(encoding="utf-8")
            for num in STRING_IDS:
                entry = re.search(rf'msgctxt "#{num}"\nmsgid "([^"]+)"\nmsgstr "([^"]*)"', text)
                self.assertIsNotNone(entry, f"{path.parent.name} #{num}")
                if path == DE:
                    self.assertTrue(entry.group(2), f"#{num} has no German")
            order = [int(n) for n in re.findall(r'msgctxt "#(313\d\d)"', text)]
            self.assertEqual(order, sorted(order), path.parent.name)


if __name__ == "__main__":
    unittest.main()
