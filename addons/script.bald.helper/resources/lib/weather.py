"""Tidy forecast values for Bald's weather rows (1080i/Includes_Bald_Weather.xml).

Kodi passes a weather add-on's Daily and Hourly values through as the add-on wrote them, and a skin cannot reformat
a string: Home Assistant Weather sends "10:00:00 AM" and "65 °F", and Kodi's Weather.Data() appends "%" to every
Precipitation value (it assumes a chance), so "0.0 in" reads "0.0 in%". Every TIDY_SECONDS the Tidier reads the
values the rows show and publishes them tidied on Home as Bald.Weather.<field> (for example
Bald.Weather.Hourly.3.Time): times without seconds ("10 AM", "13:00"), temperatures with the degree sign against the
number, and precipitation with its own unit, or as a percentage when it is a bare number. A value that does not
parse is published as it came. Without a weather service the properties are cleared.

Nothing here imports xbmc at module level, so the tests drive it with stand-ins.
"""

from __future__ import annotations

import re

from .common import SKIN_ID

TIDY_SECONDS = 10.0
DAYS = range(1, 8)     # Daily.1 .. Daily.7, the forecast row's days
HOURS = range(1, 25)   # Hourly.1 .. Hourly.24, the hourly row
PREFIX = "Bald.Weather."

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


class Tidier:
    def __init__(self, xbmc, window, clock):
        self.xbmc = xbmc
        self.window = window          # Home (10000), where the rows read Bald.Weather.*
        self.clock = clock
        self.next_at = 0.0
        self.published: dict[str, str] = {}

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
