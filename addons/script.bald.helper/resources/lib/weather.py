"""Tidy forecast values for Bald's weather rows (1080i/Includes_Bald_Weather.xml).

Kodi passes a weather add-on's Daily and Hourly values through as the add-on wrote them, and a skin cannot reformat
a string: Home Assistant Weather sends "10:00:00 AM" and "65 °F", and Kodi's Weather.Data() appends "%" to every
Precipitation value (it assumes a chance), so "0.0 in" reads "0.0 in%". Every TIDY_SECONDS the Tidier reads the
values the rows show and publishes them tidied on Home as Bald.Weather.<field> (for example
Bald.Weather.Hourly.3.Time): times without seconds ("10 AM", "13:00"), temperatures with the degree sign against the
number, and precipitation with its own unit, or as a percentage when it is a bare number. A value that does not
parse is published as it came. Without a weather service the properties are cleared.

With a weather background pack chosen (Skin.String(Bald.WeatherFanart.path)) it also gives each tile its condition's
picture, which the rows cannot find for themselves: a folder pack (Bald.WeatherFanart.ext empty) has a folder of
pictures per fanart code, and an image control cannot show a folder. For every slot a row lists (Current,
Daily.1-7, Day0-6, Hourly.1-24) the slot's FanartCode picks one file, published as Bald.Weather.Art.<slot> (for
example Bald.Weather.Art.Daily.3 or Bald.Weather.Art.Day2): from a folder pack one of the code folder's pictures,
the same all day and another the next (the day of the year modulo the count, over the sorted names), from a pack of
single pictures <path><code><ext>. Folder listings are kept for LIST_SECONDS. A code without a folder, or a slot
without a code, gets no property. Bald.Weather.ArtReady is "1" once the pictures have been resolved for the chosen
pack. The skin cannot read a property whose name holds another infolabel's value
(Property(Bald.Weather.Art.$INFO[...]) does not resolve), hence one property per slot rather than per code.

Nothing here imports xbmc at module level, so the tests drive it with stand-ins.
"""

from __future__ import annotations

import datetime
import re

from .common import SKIN_ID

TIDY_SECONDS = 10.0
DAYS = range(1, 8)     # Daily.1 .. Daily.7, the forecast row's days
HOURS = range(1, 25)   # Hourly.1 .. Hourly.24, the hourly row
PREFIX = "Bald.Weather."
PACK_PATH = "Skin.String(Bald.WeatherFanart.path)"
PACK_EXT = "Skin.String(Bald.WeatherFanart.ext)"
LIST_SECONDS = 3 * 3600.0  # a code folder's listing is read again after this long
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
ART_READY = "ArtReady"

_TIME = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp]\.?[Mm]\.?)?\s*$")
_NUMBER = re.compile(r"^\s*-?\d+(?:[.,]\d+)?\s*$")


def tidy_time(value: str) -> str:
    """"10:00:00 AM" -> "10 AM", "10:30:00 PM" -> "10:30 PM", "13:00:00" -> "13:00"."""
    match = _TIME.match(value)
    if not match:
        return value.strip()
    hour, minute, meridiem = match.groups()
    if meridiem:
        meridiem = meridiem.replace(".", "").upper()
        return f"{int(hour)} {meridiem}" if minute == "00" else f"{int(hour)}:{minute} {meridiem}"
    return f"{int(hour):02d}:{minute}"


def tidy_temperature(value: str, units: str) -> str:
    """"65 °F" -> "65°F"; a bare "65" takes Kodi's units ("65°F")."""
    value = value.strip()
    if _NUMBER.match(value):
        return f"{value}{units}"
    return re.sub(r"(\d)\s+°", r"\1°", value)


def tidy_precipitation(value: str) -> str:
    """"0.0 in" and "3 mm" stay as they are; a bare "40" is a chance, "40%"; "40 %" -> "40%"."""
    value = value.strip()
    if not value:
        return ""
    if _NUMBER.match(value):
        return f"{value}%"
    return re.sub(r"(\d)\s+%", r"\1%", value)


def fields():
    """(Weather.Data field, kind) for every value the rows show that needs tidying."""
    yield "Current.Precipitation", "precipitation"
    for n in DAYS:
        yield f"Daily.{n}.HighTemperature", "temperature"
        yield f"Daily.{n}.LowTemperature", "temperature"
        yield f"Daily.{n}.Precipitation", "precipitation"
    for n in HOURS:
        yield f"Hourly.{n}.Time", "time"
        yield f"Hourly.{n}.Temperature", "temperature"
        yield f"Hourly.{n}.Precipitation", "precipitation"


def art_slots():
    """(slot, Weather.Data field holding its fanart code) for every tile a weather row lists."""
    yield "Current", "Current.FanartCode"
    for n in DAYS:
        yield f"Daily.{n}", f"Daily.{n}.FanartCode"
    for n in range(7):
        yield f"Day{n}", f"Day{n}.FanartCode"
    for n in HOURS:
        yield f"Hourly.{n}", f"Hourly.{n}.FanartCode"


def pick(names: list[str], day: datetime.date) -> str:
    """One of a folder's pictures: the same all day, the next one the next day."""
    names = sorted(names)
    return names[day.timetuple().tm_yday % len(names)]


class Tidier:
    def __init__(self, xbmc, window, clock, xbmcvfs=None, today=datetime.date.today):
        self.xbmc = xbmc
        self.window = window          # Home (10000), where the rows read Bald.Weather.*
        self.clock = clock
        self.xbmcvfs = xbmcvfs        # lists a folder pack's code folders (resource:// paths included)
        self.today = today
        self.next_at = 0.0
        self.published: dict[str, str] = {}
        self.listings: dict[str, tuple[float, list[str]]] = {}  # code folder -> (when listed, picture names)

    def raw(self, field: str) -> str:
        # Window(Weather).Property() is the add-on's value itself; Weather.Data() would add "%" to Precipitation.
        return self.xbmc.getInfoLabel(f"Window(Weather).Property({field})")

    def tick(self) -> None:
        """One step of the service loop."""
        now = self.clock()
        if now < self.next_at:
            return
        self.next_at = now + TIDY_SECONDS
        if self.xbmc.getSkinDir() != SKIN_ID:
            return
        if not self.xbmc.getInfoLabel("Weather.Plugin"):
            self.clear()
            return
        units = self.xbmc.getInfoLabel("System.TemperatureUnits")
        for field, kind in fields():
            value = self.raw(field)
            if kind == "time":
                value = tidy_time(value)
            elif kind == "temperature":
                value = tidy_temperature(value, units) if value.strip() else ""
            else:
                value = tidy_precipitation(value)
            self.publish(field, value)
        self.publish_art()

    # --- weather background pack pictures per tile ---
    def folder_pictures(self, folder: str) -> list[str]:
        """The picture names in a code folder, listed at most every LIST_SECONDS."""
        now = self.clock()
        cached = self.listings.get(folder)
        if cached is not None and now - cached[0] < LIST_SECONDS:
            return cached[1]
        names: list[str] = []
        if self.xbmcvfs is not None:
            try:
                _, files = self.xbmcvfs.listdir(folder)
                names = [name for name in files if name.lower().endswith(IMAGE_EXTENSIONS)]
            except Exception:  # noqa: BLE001 - a missing or unreadable folder is a code without pictures
                names = []
        self.listings[folder] = (now, names)
        return names

    def picture(self, path: str, ext: str, code: str, day: datetime.date) -> str:
        """The file for one fanart code: <path><code><ext> in a pack of single pictures, else one from <path><code>/."""
        if ext:
            return f"{path}{code}{ext}"
        folder = f"{path}{code}/"
        names = self.folder_pictures(folder)
        return folder + pick(names, day) if names else ""

    def publish_art(self) -> None:
        path = self.xbmc.getInfoLabel(PACK_PATH).strip()
        if path and not path.endswith(("/", "\\")):
            path += "/"
        ext = self.xbmc.getInfoLabel(PACK_EXT).strip()
        day = self.today()
        resolved: dict[str, str] = {}
        for slot, field in art_slots():
            code = self.raw(field).strip() if path else ""
            if code and code not in resolved:
                resolved[code] = self.picture(path, ext, code, day)
            self.publish(f"Art.{slot}", resolved.get(code, "") if code else "")
        self.publish(ART_READY, "1" if path else "")

    def publish(self, field: str, value: str) -> None:
        if self.published.get(field) == value:
            return
        self.published[field] = value
        if value:
            self.window.setProperty(PREFIX + field, value)
        else:
            self.window.clearProperty(PREFIX + field)

    def clear(self) -> None:
        for field in list(self.published):
            self.window.clearProperty(PREFIX + field)
        self.published.clear()
