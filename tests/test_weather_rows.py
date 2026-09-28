"""Weather rows on Home (1080i/Includes_Bald_Weather.xml): offered by the widget editor's Choose content, built by the
generator as a Bald_Row of static tiles in the weather style, and driven only by Kodi's own weather infolabels, with a
set-up tile when no weather service is chosen."""

import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from conditions import all_of, implies
from kodi_includes import Skin, expand_call, include_definitions
from skin_strings import strings
from test_home_hubs import build


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
WEATHER = XML / "Includes_Bald_Weather.xml"
CONFIG = json.loads((ROOT / "shortcuts" / "skinvariables-shortcut-config.json").read_text(encoding="utf-8"))
PATHS = {"weather://daily": "Bald_WeatherDailyContent", "weather://hourly": "Bald_WeatherHourlyContent"}
# Kodi's weather infolabels (GUIInfoManager): Weather.Data(<key>) reads what the weather add-on publishes.
NATIVE_INFO = re.compile(r"^(Weather\.(Plugin|IsFetched|Data\(("
                         r"Current\.(Temperature|Condition|FeelsLike|Location|Humidity|Wind|Precipitation|FanartCode)"
                         r"|Daily\.IsFetched|Hourly\.IsFetched"
                         r"|Daily\.\d+\.(ShortDay|LongDay|HighTemperature|LowTemperature|Outlook|ShortDate|FanartCode)"
                         r"|Day\d\.(Title|HighTemp|LowTemp|Outlook|FanartCode)"
                         r"|Hourly\.\d+\.(Time|Temperature|Precipitation|Outlook|ShortDate|FanartCode)"
                         r")\))"
                         r"|Skin\.String\(Bald\.Weather(Fanart|Icons)\.(path|ext)\)"
                         r"|Window\(home\)\.Property\(Bald\.(Row|RowStyle)\)"
                         r"|(Container\(\d+\)\.)?ListItem\.(Label|Label2|Icon|CurrentItem|Art\(thumb\)|Property\(Bald\.[A-Za-z]+\)))$")


def helper_weather():
    """Bald Helper's weather module (the slot names it publishes)."""
    import sys
    sys.path.insert(0, str(ROOT / "addons" / "script.bald.helper"))
    from resources.lib import weather
    return weather


def row(label, path, **fields):
    return {"label": label, "path": path, "target": "", "limit": "25", "secondary": "0", "path2": "", **fields}


def generated(rows):
    return ET.fromstring(build({"homewidgets": rows}).split("\n", 1)[1])


def param(node, name):
    return node.findtext(f"param[@name='{name}']")


def expanded_items(name):
    """The static items one of the row content includes lists, parameters filled in."""
    holder = ET.Element("holder")
    holder.extend(expand_call(name))
    return holder.findall(".//item")


def infolabels(text):
    """The infolabels a text reads: inside $INFO[...] (up to the first comma), and every Weather.* one, conditions
    included. Comments are left out."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    found = [match.split(",")[0] for match in re.findall(r"\$(?:ESC)?INFO\[((?:[^\[\]]|\[[^\[\]]*\])*)\]", text)]
    return found + re.findall(r"Weather\.(?:Data\([^()]*\)|[A-Za-z]+)", text)


class PickerTests(unittest.TestCase):
    def test_choose_content_offers_the_two_weather_rows(self):
        folder = next(entry for entry in CONFIG["grouping://shortcuts/"]
                      if isinstance(entry, dict) and entry["path"] == "grouping://bald/weather/")
        self.assertEqual(folder["link"], "false")
        entries = CONFIG["grouping://bald/weather/"]
        # Picked directly: the browser stores the path as it is, with an empty target (use_rawpath).
        self.assertEqual({entry["path"]: entry["link"] for entry in entries},
                         {"weather://daily": "true", "weather://hourly": "true"})
        self.assertEqual([entry["name"] for entry in entries], ["Weather forecast", "Hourly weather"])
        # The widget editor browses the default grouping (grouping://shortcuts/).
        self.assertIn("func=do_choose", (XML / "Custom_1116_BaldHomeWidgets.xml").read_text(encoding="utf-8"))


class GeneratorTests(unittest.TestCase):
    def test_a_weather_row_lists_static_tiles_in_the_weather_style(self):
        rows = [row("Weather forecast", "weather://daily", style="poster", logo="on"),
                row("Hourly weather", "weather://hourly"),
                {"label": "Movies", "path": "videodb://movies/titles/", "target": "videos", "limit": "25",
                 "secondary": "0", "style": "square"}]
        root = generated(rows)
        calls = root.findall("include[@name='Bald_Generated_HomeWidgets']/definition/include")
        self.assertEqual([param(call, "style") for call in calls], ["weather", "weather", "square"])
        for call, path in zip(calls, PATHS):
            # The weather style wins over a style field left from earlier content, and the row has no path content.
            self.assertEqual(call.findall("content"), [])
            self.assertIn(PATHS[path], [node.text for node in call.findall("include")])
            self.assertEqual((param(call, "slot"), param(call, "start")), ("2", "3"))
        self.assertEqual([node.text for node in calls[2].findall("content")], ["videodb://movies/titles/"])
        styles = {value.text for value in root.findall("variable[@name='Bald_RowStyle_home']/value")}
        self.assertEqual(styles, {"weather", "square", "fanart"})

    def test_weather_rows_bind_their_own_caption_and_art_icon(self):
        root = generated([row("Weather forecast", "weather://daily"),
                          {"label": "Movies", "path": "videodb://movies/titles/", "target": "videos", "limit": "25",
                           "secondary": "0"}])
        captions = root.findall("include[@name='Bald_ConfiguredCaptions_home']/definition/include")
        self.assertEqual([(node.get("content"), param(node, "c")) for node in captions],
                         [("Bald_WeatherCaption", "9101"), ("Bald_WeatherCaption", "9101"),
                          ("Bald_Caption", "9102"), ("Bald_Caption", "9102")])
        logos = root.findall("include[@name='Bald_ConfiguredArtLogos_home']/definition/include")
        self.assertEqual([(node.get("content"), param(node, "c")) for node in logos],
                         [("Bald_WeatherArtIcon", "9101"), ("Bald_WeatherArtIcon", "9101"),
                          ("Bald_ArtLogo", "9102"), ("Bald_ArtLogo", "9102")])

    def test_the_weather_background_pack_is_the_rows_art(self):
        root = generated([row("Weather forecast", "weather://daily")])
        values = [(value.get("condition"), value.text) for value in root.findall("variable[@name='Bald_Fanart']/value")]
        current = [(c, t) for c, t in values if c and c.startswith("String.IsEqual(Window(home).Property(Bald.Row),9101)")]
        self.assertEqual(len(current), 3)
        # The focused tile's own picture, its thumb (Bald Helper's Bald.Weather.Art.<slot>), for either kind of pack.
        condition, texture = current[0]
        self.assertTrue(implies(condition, "!String.IsEmpty(Skin.String(Bald.WeatherFanart.path))"))
        self.assertTrue(implies(condition, "!String.IsEmpty(Container(9101).ListItem.Art(thumb))"))
        self.assertEqual(texture, "$INFO[Container(9101).ListItem.Art(thumb)]")
        # Until then a pack of single pictures (it has a file extension) names the tile's file from its code.
        condition, texture = current[1]
        self.assertTrue(implies(condition, "!String.IsEmpty(Skin.String(Bald.WeatherFanart.ext))"))
        self.assertEqual(texture, "$INFO[Skin.String(Bald.WeatherFanart.path)]"
                                  "$INFO[Container(9101).ListItem.Property(Bald.WeatherCode)]"
                                  "$INFO[Skin.String(Bald.WeatherFanart.ext)]")
        self.assertIsNone(current[2][1])
        # Never the media art chain on a weather row (fanart, landscape, poster): only the tile's thumb.
        arts = set(re.findall(r"Art\((\w[\w.]*)\)", " ".join(f"{c} {t}" for c, t in values if c and "9101" in c)))
        self.assertEqual(arts, {"thumb"})

    def test_every_tile_carries_its_slots_picture_as_its_thumb(self):
        slots = {"Bald_WeatherDailyContent": ["Current"] + [f"Daily.{n}" for n in range(1, 8)]
                 + [f"Day{n}" for n in range(7)],
                 "Bald_WeatherHourlyContent": ["Current"] + [f"Hourly.{n}" for n in range(1, 25)]}
        for name, expected in slots.items():
            items = [item for item in expanded_items(name)
                     if item.findtext("property[@name='Bald.Weather']") in ("now", "day", "hour")]
            self.assertEqual([item.findtext("thumb") for item in items],
                             [f"$INFO[Window(home).Property(Bald.Weather.Art.{slot})]" for slot in expected])
            # The set-up and fetching tiles have no picture.
            for item in expanded_items(name):
                if item.findtext("property[@name='Bald.Weather']") in ("setup", "fetching"):
                    self.assertIsNone(item.find("thumb"))
        # The same slot names Bald Helper publishes.
        published = {slot for slot, _ in helper_weather().art_slots()}
        self.assertEqual(published, set(slots["Bald_WeatherDailyContent"] + slots["Bald_WeatherHourlyContent"]))

    def test_the_big_icon_steps_aside_for_a_picture(self):
        icon = ET.parse(WEATHER).getroot().find("include[@name='Bald_WeatherArtIcon']")
        visible = [node.findtext("visible") for node in icon.iter("control") if node.get("type") == "image"][0]
        # No pack, or no code: the icon. A folder pack whose pictures Bald Helper has resolved but found none for the
        # tile: the icon too. A tile with a picture: never.
        self.assertIn("String.IsEmpty(Skin.String(Bald.WeatherFanart.path))", visible)
        self.assertIn("String.IsEmpty(Container($PARAM[c]).ListItem.Property(Bald.WeatherCode))", visible)
        self.assertIn("[String.IsEmpty(Container($PARAM[c]).ListItem.Art(thumb)) + String.IsEmpty(Skin.String("
                      "Bald.WeatherFanart.ext)) + !String.IsEmpty(Window(home).Property(Bald.Weather.ArtReady))]", visible)

    def test_the_folder_pack_slideshow_is_only_a_stopgap(self):
        body = ET.parse(WEATHER).getroot().findtext("expression[@name='Bald_WeatherFolderArt']")
        self.assertIn("String.IsEmpty(Window(home).Property(Bald.Weather.ArtReady))", body)
        self.assertIn("String.IsEmpty(Skin.String(Bald.WeatherFanart.ext))", body)


class InfolabelTests(unittest.TestCase):
    def test_everything_shown_is_a_native_weather_infolabel(self):
        text = WEATHER.read_text(encoding="utf-8")
        # Bald Helper's tidied values (resources/lib/weather.py) are the one exception: only the fields it publishes.
        tidied = set(re.findall(r"Window\(home\)\.Property\(Bald\.Weather\.([^)]+)\)", text))
        self.assertEqual(tidied, {"Current.Precipitation", "Daily.$PARAM[n].HighTemperature",
                                  "Daily.$PARAM[n].LowTemperature", "Hourly.$PARAM[n].Time",
                                  "Hourly.$PARAM[n].Temperature", "Hourly.$PARAM[n].Precipitation",
                                  "Art.Current", "Art.Daily.$PARAM[n]", "Art.Day$PARAM[n]", "Art.Hourly.$PARAM[n]",
                                  "ArtReady"})
        text = re.sub(r"Window\(home\)\.Property\(Bald\.Weather\.[^)]+\)", "Weather.Data(Current.Temperature)", text)
        labels = set(infolabels(text))
        self.assertTrue(labels)
        for label in sorted(labels):
            label = re.sub(r"\$PARAM\[\w+\]", "1", label)
            with self.subTest(label=label):
                self.assertRegex(label, NATIVE_INFO)
        # Not the weather window's properties (the older Window(Weather).Property(...) route).
        self.assertIsNone(re.search(r"Window\(weather\)\.Property", text, re.I))
        for helper in ("TMDbHelper", "script.", "plugin://", "RunScript"):
            self.assertNotIn(helper, text)

    def test_every_forecast_tile_uses_the_chosen_icon_pack(self):
        prefix = "$VAR[WeatherOutlookIconPrefixVar]"
        for name in PATHS.values():
            for item in expanded_items(name):
                icon = item.findtext("icon")
                self.assertTrue(icon.startswith(prefix) and icon.endswith("$VAR[WeatherOutlookIconPostfixVar]"), icon)
        values = [value.text for value in ET.parse(XML / "Variables.xml").getroot()
                  .findall("variable[@name='WeatherOutlookIconPrefixVar']/value")]
        # A chosen pack, else Bald's own icons (media/bald/weather) as <code>.png.
        self.assertEqual(values, ["$INFO[Skin.String(Bald.WeatherIcons.path)]", "special://skin/media/bald/weather/"])
        postfix = [value.text for value in ET.parse(XML / "Variables.xml").getroot()
                   .findall("variable[@name='WeatherOutlookIconPostfixVar']/value")]
        self.assertEqual(postfix, ["$INFO[Skin.String(Bald.WeatherIcons.ext)]", ".png"])

    def test_bald_ships_an_icon_for_every_weather_code(self):
        icons = ROOT / "media" / "bald" / "weather"
        codes = [str(code) for code in range(48)] + ["na"]
        self.assertEqual(sorted(p.stem for p in icons.glob("*.png")), sorted(codes))
        for code in codes:
            with self.subTest(code=code):
                with Image.open(icons / f"{code}.png") as im:
                    self.assertEqual(im.mode, "RGBA")
                    self.assertEqual(im.size, (256, 256))
                    # White line art on transparency, so colordiffuse tints it: every pixel white, drawn by alpha.
                    self.assertEqual(im.getchannel("R").getextrema(), (255, 255))
                    self.assertEqual(im.getchannel("G").getextrema(), (255, 255))
                    self.assertEqual(im.getchannel("B").getextrema(), (255, 255))
                    alpha = im.getchannel("A")
                    self.assertEqual(alpha.getextrema(), (0, 255))
                    self.assertEqual(alpha.getpixel((0, 0)), 0)
        licence = (icons / "LICENSE-Meteocons.txt").read_text()
        self.assertIn("MIT License", licence)
        self.assertIn("Bas Milius", licence)

    def test_the_default_weather_icons_are_named_in_appearance(self):
        values = [(value.get("condition"), value.text) for value in ET.parse(XML / "Includes_Bald_Configure.xml")
                  .getroot().findall("variable[@name='Bald_WeatherIconsName']/value")]
        self.assertEqual(values[-1], (None, "$LOCALIZE[31433]"))
        self.assertEqual(strings()[31433], "Meteocons")


class FallbackTests(unittest.TestCase):
    def items(self, name):
        return [(item.findtext("property[@name='Bald.Weather']"), item.findtext("visible"), item.findall("onclick"), item)
                for item in expanded_items(name)]

    def test_without_a_weather_service_one_tile_opens_the_weather_settings(self):
        for name in PATHS.values():
            items = self.items(name)
            setup = [entry for entry in items if entry[0] == "setup"]
            self.assertEqual(len(setup), 1, name)
            _, visible, clicks, item = setup[0]
            self.assertEqual(visible, "String.IsEmpty(Weather.Plugin)")
            self.assertEqual([click.text for click in clicks], ["ActivateWindow(servicesettings,weather)"])
            # Nothing else shows then: every other tile needs a weather service.
            for kind, other, _, _ in items:
                if kind != "setup":
                    self.assertTrue(implies(other, "!String.IsEmpty(Weather.Plugin)",
                                            bodies={"Bald_WeatherReady": "[!String.IsEmpty(Weather.Plugin) + Weather.IsFetched]"}),
                                    kind)
            self.assertEqual(item.findtext("label2"), "$LOCALIZE[31451]")
            self.assertEqual(item.findtext("property[@name='Bald.Note']"), "$LOCALIZE[31450]", "the hint wraps on the note line")

    def test_while_fetching_one_quiet_tile_waits(self):
        bodies = {"Bald_WeatherReady": "[!String.IsEmpty(Weather.Plugin) + Weather.IsFetched]"}
        for name in PATHS.values():
            items = self.items(name)
            fetching = [entry for entry in items if entry[0] == "fetching"]
            self.assertEqual(len(fetching), 1)
            self.assertEqual(fetching[0][1], "!String.IsEmpty(Weather.Plugin) + !Weather.IsFetched")
            self.assertEqual(fetching[0][3].findtext("property[@name='Bald.Meta']"), "$LOCALIZE[410]")
            for kind, visible, _, _ in items:
                if kind in ("now", "day", "hour"):
                    self.assertTrue(implies(visible, "Weather.IsFetched", bodies=bodies), kind)

    def test_forecast_tiles_open_the_weather_page_and_the_row_does_not_open_info(self):
        for name in PATHS.values():
            for kind, _, clicks, _ in self.items(name):
                if kind != "setup":
                    self.assertEqual([click.text for click in clicks], ["ActivateWindow(Weather)"], kind)
        kinds = [entry[0] for entry in self.items("Bald_WeatherDailyContent")]
        self.assertEqual(kinds, ["setup", "fetching", "now"] + ["day"] * 14)
        kinds = [entry[0] for entry in self.items("Bald_WeatherHourlyContent")]
        self.assertEqual(kinds, ["setup", "fetching", "now"] + ["hour"] * 24)
        # Daily.<n> when the add-on has it, else the older Day<n>: never both.
        daily = [entry[1] for entry in self.items("Bald_WeatherDailyContent") if entry[0] == "day"]
        self.assertTrue(all("!String.IsEmpty(Weather.Data(Daily.IsFetched))" in v for v in daily[:7]))
        self.assertTrue(all(" String.IsEmpty(Weather.Data(Daily.IsFetched))" in v for v in daily[7:]))
        # Select on a weather tile is the tile's own onclick: Bald_Row's Info is left out for it.
        home = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        fixedlist = next(c for c in home.iter("control") if c.get("type") == "fixedlist" and c.get("id") == "$PARAM[id]")
        info = [n.get("condition") for n in fixedlist.findall("onclick") if n.text == "Action(Info)"]
        self.assertEqual(len(info), 1)
        self.assertTrue(implies(info[0], "!$EXP[Bald_WeatherTileItem]"))
        self.assertEqual(ET.parse(WEATHER).getroot().findtext("expression[@name='Bald_WeatherTileItem']"),
                         "[!String.IsEmpty(ListItem.Property(Bald.Weather))]")


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definitions = include_definitions()

    def fixedlist(self, style):
        holder = ET.Element("holder")
        holder.extend(expand_call("Bald_Row", {"id": "9101", "style": style}, self.definitions))
        return holder, next(node for node in holder.iter("control") if node.get("type") == "fixedlist")

    def test_weather_tiles_sit_on_the_square_rail_under_the_poster_frame(self):
        square_holder, square = self.fixedlist("square")
        holder, weather = self.fixedlist("weather")
        for tag in ("left", "top", "width", "height"):
            self.assertEqual(weather.findtext(tag), square.findtext(tag))
        for layout in ("itemlayout", "focusedlayout"):
            node = weather.find(layout)
            self.assertEqual((node.get("width"), node.get("height")), ("208", "234"))
            labels = [label.findtext("label") for label in node.iter("control") if label.get("type") == "label"]
            self.assertEqual(labels, ["$INFO[ListItem.Label]", "$INFO[ListItem.Label2]"])
            self.assertIn("$INFO[ListItem.Icon]", [texture.text for texture in node.iter("texture")])
            # The tile face keeps the icon: the item's thumb (its background picture) is never drawn on the tile.
            textures = " ".join(texture.text or "" for texture in node.iter("texture"))
            for art in ("Art(thumb)", "ListItem.Thumb", "Bald_SquareArt"):
                self.assertNotIn(art, textures)
            # The square tile's pop and ring, not a copy of them.
            self.assertEqual(len([a for a in node.iter("animation") if a.get("type") == "Focus"]), 1)
        self.assertIn("bald/focus_ring.png", [t.text for t in weather.find("focusedlayout").iter("texture")])
        label_line = next(node for node in holder.iter("control") if node.get("type") == "grouplist")
        self.assertEqual(label_line.findtext("top"), "712")
        body = ET.parse(XML / "Includes_Bald_Home.xml").getroot().findtext("expression[@name='Bald_PosterRow']")
        self.assertIn("Property(Bald.RowStyle),weather)", body)

    def test_home_resolves_with_a_weather_row(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "generated.xml"
            path.write_text(build({"homewidgets": [row("Weather forecast", "weather://daily")]}), encoding="utf-8")
            skin = Skin(generated=path)
            home = skin.window("Home.xml")
        self.assertEqual(skin.missing, [])
        fixedlist = home.find(".//control[@id='9101']")
        items = fixedlist.findall("content/item")
        self.assertEqual(len(items), 17)
        self.assertEqual(items[0].findtext("onclick"), "ActivateWindow(servicesettings,weather)")
        self.assertIn("Bald.RowStyle,weather,home", " ".join(node.text or "" for node in fixedlist.findall("onfocus")))
        # The folder-pack picture in the art frame, and the big icon over it.
        self.assertTrue([node for node in home.iter("control") if node.get("type") == "multiimage"
                         and "Bald.WeatherFanart.path" in (node.findtext("imagepath") or "")])
        self.assertIn("$INFO[Container(9101).ListItem.Icon]", [t.text for t in home.iter("texture")])


class EditorTests(unittest.TestCase):
    def test_the_widget_editor_hides_what_a_weather_row_does_not_have(self):
        editor = ET.parse(XML / "Custom_1116_BaldHomeWidgets.xml").getroot()
        for control_id in ("9203", "9208", "9209", "9210", "9211"):
            visible = all_of([node.text for node in editor.find(f".//control[@id='{control_id}']").findall("visible")])
            self.assertTrue(implies(visible, "!$EXP[Bald_WidgetIsWeather]"), control_id)
        for control_id in ("9201", "9202", "9204", "9205", "9207"):
            control = editor.find(f".//control[@id='{control_id}']")
            self.assertNotIn("Bald_WidgetIsWeather", ET.tostring(control, encoding="unicode"), control_id)
        configure = ET.parse(XML / "Includes_Bald_Configure.xml").getroot()
        self.assertEqual(configure.findtext("expression[@name='Bald_WidgetIsWeather']"),
                         "[String.StartsWith(Container(9100).ListItem.Property(path),weather://)]")
        notes = [(v.get("condition"), v.text) for v in configure.findall("variable[@name='Bald_WidgetNote']/value")]
        self.assertEqual(notes[-1], (None, "$INFO[Container(9100).ListItem.Property(path)]"))
        self.assertEqual([text for _, text in notes[:2]], ["$LOCALIZE[31452]", "$LOCALIZE[31453]"])

    def test_weather_strings_are_in_the_weather_block_in_both_languages(self):
        english = strings()
        for number in range(31450, 31454):
            self.assertIn(number, english)
        german = (ROOT / "language" / "resource.language.de_de" / "strings.po").read_text(encoding="utf-8")
        for number in range(31450, 31454):
            block = german.split(f'msgctxt "#{number}"')[1].split("\n\n")[0]
            self.assertRegex(block, r'msgstr "[^"]+"', number)
        used = {int(n) for n in re.findall(r"\$LOCALIZE\[(\d+)\]", WEATHER.read_text(encoding="utf-8"))}
        self.assertTrue({31450, 31451} <= used)
        # Kodi's own strings where they exist; Bald's only from the weather block.
        self.assertTrue(all(not 31000 <= n <= 31999 or 31450 <= n <= 31499 for n in used), used)


if __name__ == "__main__":
    unittest.main()
