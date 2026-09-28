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


if __name__ == "__main__":
    unittest.main()
