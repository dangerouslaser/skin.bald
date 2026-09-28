import datetime
from pathlib import Path
import sys
import unittest

ADDON = Path(__file__).resolve().parents[1] / "addons" / "script.bald.helper"
sys.path.insert(0, str(ADDON))

from resources.lib import weather  # noqa: E402


class FormatTests(unittest.TestCase):
    def test_times(self):
        for raw, tidy in (("10:00:00 AM", "10 AM"), ("10:30:00 PM", "10:30 PM"), ("09:00 am", "9 AM"),
                          ("1:00 p.m.", "1 PM"), ("13:00:00", "13:00"), ("7:05", "07:05"), ("Noon", "Noon"), ("", "")):
            self.assertEqual(weather.tidy_time(raw), tidy, raw)

    def test_temperatures(self):
        for raw, tidy in (("65 °F", "65°F"), ("-3 °C", "-3°C"), ("63°F", "63°F"), ("65", "65°F"), ("12.5", "12.5°F")):
            self.assertEqual(weather.tidy_temperature(raw, "°F"), tidy, raw)

    def test_precipitation(self):
        for raw, tidy in (("0.0 in", "0.0 in"), ("3 mm", "3 mm"), ("40", "40%"), ("40 %", "40%"), ("40%", "40%"), ("", "")):
            self.assertEqual(weather.tidy_precipitation(raw), tidy, raw)


class Xbmc:
    def __init__(self, labels, skin="skin.bald"):
        self.labels, self.skin, self.reads = labels, skin, 0

    def getSkinDir(self):
        return self.skin

    def getInfoLabel(self, label):
        self.reads += 1
        return self.labels.get(label, "")


class Window:
    def __init__(self):
        self.props, self.writes = {}, 0

    def setProperty(self, key, value):
        self.props[key] = value
        self.writes += 1

    def clearProperty(self, key):
        self.props.pop(key, None)
        self.writes += 1


def raw(field):
    return f"Window(Weather).Property({field})"


class TidierTests(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.xbmc = Xbmc({"Weather.Plugin": "weather.ha", "System.TemperatureUnits": "°F",
                          raw("Hourly.1.Time"): "10:00:00 AM", raw("Hourly.1.Temperature"): "62 °F",
                          raw("Hourly.1.Precipitation"): "0.0 in", raw("Daily.1.HighTemperature"): "65 °F",
                          raw("Daily.1.LowTemperature"): "58 °F", raw("Current.Precipitation"): "20"})
        self.window = Window()
        self.tidier = weather.Tidier(self.xbmc, self.window, lambda: self.now[0])

    def test_publishes_tidied_values_on_home(self):
        self.tidier.tick()
        p = self.window.props
        self.assertEqual(p["Bald.Weather.Hourly.1.Time"], "10 AM")
        self.assertEqual(p["Bald.Weather.Hourly.1.Temperature"], "62°F")
        self.assertEqual(p["Bald.Weather.Hourly.1.Precipitation"], "0.0 in")
        self.assertEqual(p["Bald.Weather.Daily.1.HighTemperature"], "65°F")
        self.assertEqual(p["Bald.Weather.Daily.1.LowTemperature"], "58°F")
        self.assertEqual(p["Bald.Weather.Current.Precipitation"], "20%")
        self.assertNotIn("Bald.Weather.Hourly.2.Time", p, "empty values are not published")

    def test_runs_every_ten_seconds_and_writes_only_changes(self):
        self.tidier.tick()
        writes, reads = self.window.writes, self.xbmc.reads
        self.now[0] += 5
        self.tidier.tick()
        self.assertEqual(self.xbmc.reads, reads, "not before TIDY_SECONDS")
        self.now[0] += weather.TIDY_SECONDS
        self.tidier.tick()
        self.assertEqual(self.window.writes, writes, "nothing changed, nothing written")
        self.xbmc.labels[raw("Hourly.1.Time")] = "11:00:00 AM"
        self.now[0] += weather.TIDY_SECONDS
        self.tidier.tick()
        self.assertEqual(self.window.props["Bald.Weather.Hourly.1.Time"], "11 AM")
        self.assertEqual(self.window.writes, writes + 1)

    def test_clears_without_a_weather_service_and_rests_under_another_skin(self):
        self.tidier.tick()
        self.xbmc.labels["Weather.Plugin"] = ""
        self.now[0] += weather.TIDY_SECONDS
        self.tidier.tick()
        self.assertEqual(self.window.props, {})
        self.xbmc.skin = "skin.estuary"
        self.xbmc.labels["Weather.Plugin"] = "weather.ha"
        self.now[0] += weather.TIDY_SECONDS
        self.tidier.tick()
        self.assertEqual(self.window.props, {})

    def test_fields_cover_what_the_rows_read(self):
        fields = dict(weather.fields())
        for n in (1, 7):
            for f in ("HighTemperature", "LowTemperature"):
                self.assertEqual(fields[f"Daily.{n}.{f}"], "temperature")
        for n in (1, 24):
            self.assertEqual(fields[f"Hourly.{n}.Time"], "time")
            self.assertEqual(fields[f"Hourly.{n}.Precipitation"], "precipitation")
        self.assertEqual(fields["Current.Precipitation"], "precipitation")


PACK = "resource://resource.images.weatherfanart.multi/"


class Vfs:
    """xbmcvfs.listdir over a dict of folder -> file names; a folder not in it does not exist."""

    def __init__(self, folders):
        self.folders, self.listed = folders, []

    def listdir(self, path):
        self.listed.append(path)
        if path not in self.folders:
            raise OSError(path)
        return [], list(self.folders[path])


class ArtTests(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.day = [datetime.date(2026, 1, 1)]  # day of the year 1
        self.xbmc = Xbmc({"Weather.Plugin": "weather.multi", "Skin.String(Bald.WeatherFanart.path)": PACK,
                          raw("Current.FanartCode"): "26", raw("Daily.1.FanartCode"): "32",
                          raw("Daily.2.FanartCode"): "32", raw("Hourly.5.FanartCode"): "11",
                          raw("Day2.FanartCode"): "26", raw("Daily.3.FanartCode"): "99"})
        self.vfs = Vfs({PACK + "26/": ["a.jpg", "c.jpg", "b.png", "notes.txt", "Thumbs.db"],
                        PACK + "32/": ["sun.JPG"], PACK + "11/": ["rain-1.jpg", "rain-2.jpg"]})
        self.window = Window()
        self.tidier = weather.Tidier(self.xbmc, self.window, lambda: self.now[0], self.vfs, lambda: self.day[0])

    def tick(self, seconds=weather.TIDY_SECONDS):
        self.now[0] += seconds
        self.tidier.tick()

    def test_each_slot_gets_its_conditions_picture_from_a_folder_pack(self):
        self.tidier.tick()
        p = self.window.props
        # Code 26's pictures, sorted: a.jpg, b.png, c.jpg (not the text file); day 1 -> index 1.
        self.assertEqual(p["Bald.Weather.Art.Current"], PACK + "26/b.png")
        self.assertEqual(p["Bald.Weather.Art.Day2"], PACK + "26/b.png")
        self.assertEqual(p["Bald.Weather.Art.Daily.1"], PACK + "32/sun.JPG")
        self.assertEqual(p["Bald.Weather.Art.Daily.2"], PACK + "32/sun.JPG")
        self.assertEqual(p["Bald.Weather.Art.Hourly.5"], PACK + "11/rain-2.jpg")
        self.assertEqual(p["Bald.Weather.ArtReady"], "1")
        # A code without a folder, and slots without a code, get no picture.
        self.assertNotIn("Bald.Weather.Art.Daily.3", p)
        self.assertNotIn("Bald.Weather.Art.Hourly.1", p)
        # Each code folder listed once, however many slots share it.
        self.assertEqual(sorted(self.vfs.listed), sorted([PACK + "26/", PACK + "32/", PACK + "11/", PACK + "99/"]))

    def test_the_picture_stays_all_day_and_moves_on_the_next(self):
        self.tidier.tick()
        self.tick()
        self.assertEqual(self.window.props["Bald.Weather.Art.Current"], PACK + "26/b.png")
        self.day[0] = datetime.date(2026, 1, 2)
        self.tick()
        self.assertEqual(self.window.props["Bald.Weather.Art.Current"], PACK + "26/c.jpg")
        self.assertEqual(self.window.props["Bald.Weather.Art.Hourly.5"], PACK + "11/rain-1.jpg")
        self.day[0] = datetime.date(2026, 1, 3)
        self.tick()
        self.assertEqual(self.window.props["Bald.Weather.Art.Current"], PACK + "26/a.jpg")

    def test_folders_are_listed_again_only_after_a_few_hours(self):
        self.tidier.tick()
        listed = len(self.vfs.listed)
        self.tick()
        self.assertEqual(len(self.vfs.listed), listed)
        self.vfs.folders[PACK + "99/"] = ["storm.jpg"]
        self.tick(weather.LIST_SECONDS)
        self.assertEqual(len(self.vfs.listed), 2 * listed)
        self.assertEqual(self.window.props["Bald.Weather.Art.Daily.3"], PACK + "99/storm.jpg")

    def test_a_pack_of_single_pictures_names_the_file(self):
        self.xbmc.labels["Skin.String(Bald.WeatherFanart.ext)"] = ".jpg"
        self.xbmc.labels["Skin.String(Bald.WeatherFanart.path)"] = "special://home/weather"  # no trailing slash
        self.tidier.tick()
        p = self.window.props
        self.assertEqual(p["Bald.Weather.Art.Current"], "special://home/weather/26.jpg")
        self.assertEqual(p["Bald.Weather.Art.Daily.3"], "special://home/weather/99.jpg")
        self.assertEqual(self.vfs.listed, [], "nothing to list")

    def test_stale_pictures_are_cleared(self):
        self.tidier.tick()
        # The forecast moves on: Hourly.5 has no code any more, Daily.1 another one.
        del self.xbmc.labels[raw("Hourly.5.FanartCode")]
        self.xbmc.labels[raw("Daily.1.FanartCode")] = "11"
        self.tick()
        p = self.window.props
        self.assertNotIn("Bald.Weather.Art.Hourly.5", p)
        self.assertEqual(p["Bald.Weather.Art.Daily.1"], PACK + "11/rain-2.jpg")
        # The pack is removed: every picture goes, and the ready flag with them.
        self.xbmc.labels["Skin.String(Bald.WeatherFanart.path)"] = ""
        self.tick()
        self.assertEqual([key for key in self.window.props if key.startswith("Bald.Weather.Art")], [])
        # Without a weather service as well.
        self.xbmc.labels["Skin.String(Bald.WeatherFanart.path)"] = PACK
        self.tick()
        self.xbmc.labels["Weather.Plugin"] = ""
        self.tick()
        self.assertEqual(self.window.props, {})

    def test_slots_cover_every_tile(self):
        slots = dict(weather.art_slots())
        self.assertEqual(len(slots), 1 + 7 + 7 + 24)
        self.assertEqual(slots["Current"], "Current.FanartCode")
        self.assertEqual(slots["Daily.7"], "Daily.7.FanartCode")
        self.assertEqual(slots["Day0"], "Day0.FanartCode")
        self.assertEqual(slots["Hourly.24"], "Hourly.24.FanartCode")

    def test_without_xbmcvfs_a_folder_pack_has_no_pictures(self):
        tidier = weather.Tidier(self.xbmc, self.window, lambda: self.now[0])
        tidier.tick()
        self.assertNotIn("Bald.Weather.Art.Current", self.window.props)


if __name__ == "__main__":
    unittest.main()
