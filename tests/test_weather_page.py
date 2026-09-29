"""The weather page (MyWeather.xml, Includes_Weather.xml): a tab row picks one of four views over a blurred backdrop.

Now, Daily, Hourly and Maps (Hourly and Maps only when the service has them); Down enters the selected view, Up returns
to the tabs. The backdrop is Bald Helper's blur of the followed tile's weather picture (the current conditions, or the
focused day or hour), never another window's last blur."""

import unittest

from kodi_includes import resolve_window


class WeatherPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.window = resolve_window("MyWeather.xml")

    def control(self, control_id):
        return self.window.find(f".//control[@id='{control_id}']")

    def test_the_tab_row_picks_a_view_and_down_enters_it(self):
        self.assertEqual(self.window.findtext("defaultcontrol"), "9100")
        tabs = self.control("9100")
        views = [item.findtext("property[@name='view']") for item in tabs.findall("content/item")]
        self.assertEqual(views, ["now", "daily", "hourly", "maps"])
        downs = {node.get("condition"): node.text for node in tabs.findall("ondown")}
        self.assertEqual(downs, {"$EXP[Bald_WeatherView_now]": "SetFocus(20)",
                                 "$EXP[Bald_WeatherView_daily]": "SetFocus(15100)",
                                 "$EXP[Bald_WeatherView_hourly]": "SetFocus(15200)",
                                 "$EXP[Bald_WeatherView_maps]": "SetFocus(70010)"})
        for control_id in ("20", "15100", "15200", "70010"):
            with self.subTest(control=control_id):
                self.assertEqual(self.control(control_id).findtext("onup"), "9100")

    def test_the_backdrop_follows_the_weather_tiles(self):
        followed = {self.control(i).find("onfocus[.='SetProperty(Bald.FocusContainer,{},weather)']".format(f))
                    is not None for i, f in (("9100", "9170"), ("20", "9170"), ("15100", "15100"), ("15200", "15200"))}
        self.assertEqual(followed, {True})
        hidden = self.control("9170")
        self.assertEqual((hidden.findtext("width"), hidden.findtext("height")), ("1", "1"))
        backdrop = [node for node in self.window.iter("control") if node.get("type") == "image"
                    and "Bald_WeatherBlurImage" in (node.findtext("texture") or "")]
        self.assertEqual(len(backdrop), 1)
        self.assertIn("$EXP[Bald_WeatherBlur]", backdrop[0].findtext("visible"))

    def test_each_figure_is_named_for_what_it_shows(self):
        stats = {}
        for group in self.window.iter("control"):
            labels = group.findall("control[@type='label']")
            if group.get("type") == "group" and len(labels) == 2 and "String.IsEmpty(Weather.Data(" in (group.findtext("visible") or ""):
                stats[labels[0].findtext("label")] = group.findtext("visible")
        self.assertEqual(stats, {
            "$LOCALIZE[404]": "!String.IsEmpty(Weather.Data(Current.Wind))",
            "$LOCALIZE[406]": "!String.IsEmpty(Weather.Data(Current.Humidity))",
            "$LOCALIZE[33021]": "!String.IsEmpty(Weather.Data(Current.Precipitation))",
            "$LOCALIZE[387]": "!String.IsEmpty(Weather.Data(Current.Cloudiness))",
            "$LOCALIZE[405]": "!String.IsEmpty(Weather.Data(Current.DewPoint))",
            "$LOCALIZE[403]": "!String.IsEmpty(Weather.Data(Current.UVIndex))",
            "$LOCALIZE[1376]": "!String.IsEmpty(Weather.Data(Current.Pressure))",
            "$LOCALIZE[33027]": "!String.IsEmpty(Weather.Data(Today.Sunrise))",
            "$LOCALIZE[33028]": "!String.IsEmpty(Weather.Data(Today.Sunset))",
        })

    def test_forecast_cards_draw_the_icon_not_the_photo(self):
        for control_id in ("15100", "15200"):
            panel = self.control(control_id)
            paths = [node.findtext("imagepath") for node in panel.iter("control") if node.get("type") == "multiimage"]
            self.assertTrue(paths)
            self.assertEqual(set(paths), {"$INFO[ListItem.Art(icon)]"})
            self.assertEqual([node.text for node in panel.findall("onclick")], ["noop"])


if __name__ == "__main__":
    unittest.main()
