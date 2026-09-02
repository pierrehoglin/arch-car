"""
The shared weather data model.

Everything above the provider layer deals in these types, never in a
particular service's JSON. That is what makes providers swappable.

The interesting part is `Condition`. Services describe the sky in
mutually incompatible ways -- MET Norway sends strings like
"partlycloudy_day", SMHI sends integers 1-27, Open-Meteo sends WMO
codes -- so each provider maps its own vocabulary onto this set and
keeps the original in `symbol` for anyone who wants it.
"""

from enum import StrEnum
from datetime import datetime, date as dt_date
from dataclasses import dataclass, field, asdict


class Condition(StrEnum):
    """
    Normalised sky condition.

    Deliberately coarse. A finer set would be harder to map onto
    consistently, and for a dashboard the difference between "light
    rain" and "rain" is not worth a wrong icon.
    """

    CLEAR = 'clear'
    PARTLY_CLOUDY = 'partly-cloudy'
    CLOUDY = 'cloudy'
    FOG = 'fog'
    DRIZZLE = 'drizzle'
    RAIN = 'rain'
    SLEET = 'sleet'
    SNOW = 'snow'
    THUNDER = 'thunder'
    UNKNOWN = 'unknown'


# Nerd Font glyphs, for a status bar or a dashboard.
CONDITION_GLYPHS = {
    Condition.CLEAR: '\U000e30d0',          # weather-sunny
    Condition.PARTLY_CLOUDY: '\U000e30c6',  # weather-partly-cloudy
    Condition.CLOUDY: '\U000e312f',         # weather-cloudy
    Condition.FOG: '\U000e313b',            # weather-fog
    Condition.DRIZZLE: '\U000e309d',        # weather-rainy
    Condition.RAIN: '\U000e318b',           # weather-pouring
    Condition.SLEET: '\U000e3193',          # weather-snowy-rainy
    Condition.SNOW: '\U000e30a3',           # weather-snowy
    Condition.THUNDER: '\U000e31a4',        # weather-lightning
    Condition.UNKNOWN: '\U000e374a',        # help
}


@dataclass
class Conditions:
    """
    Weather at one moment, or over one forecast period.

    Every measurement is optional. Providers differ in what they
    supply, and a missing humidity should not stop the temperature
    being useful -- so None means "not provided", never zero.
    """

    time: datetime | None = None

    temperature: float | None = None        # C
    feels_like: float | None = None         # C

    # The forecast's own uncertainty for this moment, from the 10th
    # and 90th percentiles. A wide spread means the models disagree.
    #
    # Not the same thing as a high and a low over a period -- those
    # are temperature_high/low below. Conflating them made daily()
    # widen a day's range by the hourly uncertainty.
    temperature_p10: float | None = None    # C
    temperature_p90: float | None = None    # C

    # Actual extremes over the period, for entries that cover one --
    # a provider's own daily summary. None for an instantaneous
    # reading.
    temperature_high: float | None = None   # C
    temperature_low: float | None = None    # C
    humidity: float | None = None           # %
    pressure: float | None = None           # hPa
    dew_point: float | None = None          # C

    wind_speed: float | None = None         # m/s
    wind_gust: float | None = None          # m/s
    wind_direction: float | None = None     # degrees, meteorological
    wind_speed_p10: float | None = None     # m/s
    wind_speed_p90: float | None = None     # m/s

    cloud_cover: float | None = None        # %
    cloud_low: float | None = None          # %
    cloud_medium: float | None = None       # %
    cloud_high: float | None = None         # %
    fog: float | None = None                # %
    uv_index: float | None = None
    # Reported by OpenWeather, not by MET. Providers differ in what
    # they supply, which is why every field is optional.
    visibility: float | None = None         # metres

    precipitation: float | None = None      # mm over the period
    precipitation_min: float | None = None  # mm, low estimate
    precipitation_max: float | None = None  # mm, high estimate
    precipitation_probability: float | None = None      # %
    thunder_probability: float | None = None            # %

    condition: Condition = Condition.UNKNOWN
    symbol: str = ''                        # the provider's own code

    # Hours this entry covers. 0 for an instantaneous reading.
    period_hours: int = 0

    def to_dict(self) -> dict:
        data = asdict(self)
        data['time'] = self.time.isoformat() if self.time else None
        data['condition'] = str(self.condition)
        return data

    @property
    def glyph(self) -> str:
        return CONDITION_GLYPHS.get(self.condition,
                                    CONDITION_GLYPHS[Condition.UNKNOWN])

    @property
    def temperature_spread(self) -> float | None:
        """
        How uncertain the temperature is, in degrees.

        None when the provider gives no percentiles.
        """
        if self.temperature_p10 is None or self.temperature_p90 is None:
            return None
        return round(self.temperature_p90 - self.temperature_p10, 1)

    @property
    def wind_spread(self) -> float | None:
        if self.wind_speed_p10 is None or self.wind_speed_p90 is None:
            return None
        return round(self.wind_speed_p90 - self.wind_speed_p10, 1)

    @property
    def wind_arrow(self) -> str:
        """
        Arrow pointing where the wind is going.

        Meteorological direction is where it comes *from*, so the
        arrow is rotated 180 degrees -- which is what a map wants.
        """
        if self.wind_direction is None:
            return ''
        arrows = '\u2193\u2199\u2190\u2196\u2191\u2197\u2192\u2198'
        index = int((self.wind_direction % 360) / 45 + 0.5) % 8
        return arrows[index]

    @property
    def wind_compass(self) -> str:
        if self.wind_direction is None:
            return ''
        points = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')
        index = int((self.wind_direction % 360) / 45 + 0.5) % 8
        return points[index]

    @property
    def summary(self) -> str:
        bits = []
        if self.temperature is not None:
            bits.append(f'{self.temperature:.0f}\u00b0C')
        bits.append(str(self.condition).replace('-', ' '))
        if self.precipitation:
            bits.append(f'{self.precipitation:.1f} mm')
        if self.wind_speed is not None:
            bits.append(f'{self.wind_speed:.0f} m/s '
                        f'{self.wind_compass}')
        return '  '.join(bits)


# How noteworthy each condition is, for picking one to represent a
# whole day. A day with six hours of sun and one of thunder is a
# thunder day: the exception is what you need to know about.
CONDITION_SEVERITY = {
    Condition.UNKNOWN: 0,
    Condition.CLEAR: 1,
    Condition.PARTLY_CLOUDY: 2,
    Condition.CLOUDY: 3,
    Condition.FOG: 4,
    Condition.DRIZZLE: 5,
    Condition.RAIN: 6,
    Condition.SLEET: 7,
    Condition.SNOW: 8,
    Condition.THUNDER: 9,
}


@dataclass
class Day:
    """
    One day, summarised from the hourly entries.

    What a forecast list actually needs beyond the next few hours: a
    high, a low, how much rain, and one icon.
    """

    date: dt_date | None = None
    high: float | None = None
    low: float | None = None
    precipitation: float = 0.0
    wind_max: float | None = None
    condition: Condition = Condition.UNKNOWN
    entries: int = 0

    def to_dict(self) -> dict:
        return {
            'date': self.date.isoformat() if self.date else None,
            'high': self.high,
            'low': self.low,
            'precipitation': self.precipitation,
            'wind_max': self.wind_max,
            'condition': str(self.condition),
            'entries': self.entries,
        }

    @property
    def glyph(self) -> str:
        return CONDITION_GLYPHS.get(self.condition,
                                    CONDITION_GLYPHS[Condition.UNKNOWN])

    @property
    def summary(self) -> str:
        bits = []
        if self.high is not None and self.low is not None:
            bits.append(f'{self.high:.0f}\u00b0 / {self.low:.0f}\u00b0')
        bits.append(str(self.condition).replace('-', ' '))
        if self.precipitation:
            bits.append(f'{self.precipitation:.1f} mm')
        return '  '.join(bits)


@dataclass
class Forecast:
    """A provider's answer for one location."""

    provider: str = ''
    place: str = ''                 # name asked for, if any
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float | None = None

    updated: datetime | None = None
    expires: datetime | None = None

    current: Conditions | None = None
    hourly: list[Conditions] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'provider': self.provider,
            'place': self.place,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'altitude': self.altitude,
            'updated': self.updated.isoformat() if self.updated else None,
            'expires': self.expires.isoformat() if self.expires else None,
            'current': self.current.to_dict() if self.current else None,
            'hourly': [h.to_dict() for h in self.hourly],
        }

    @property
    def stale(self) -> bool:
        """
        Whether the provider says this should be refetched.

        Honouring the Expires header is part of MET Norway's terms,
        not merely polite -- they block clients that poll regardless.
        """
        if self.expires is None:
            return True
        return datetime.now(self.expires.tzinfo) >= self.expires

    def at(self, when: datetime) -> Conditions | None:
        """The forecast period covering a given time."""
        best = None
        for entry in self.hourly:
            if entry.time is None or entry.time > when:
                continue
            best = entry
        return best

    def daily(self, days: int = 0) -> list['Day']:
        """
        The hourly entries collapsed to one row per day.

        Precipitation is weighted by each entry's period. MET sends
        hourly blocks for the first couple of days and six-hourly
        after that, so summing them naively would undercount the far
        end of the forecast by a factor of six.

        Partial days are included -- today usually starts mid-morning
        -- with `entries` saying how much of the day is covered.
        """
        buckets: dict = {}

        for entry in self.hourly:
            if entry.time is None:
                continue
            key = entry.time.date()
            day = buckets.get(key)
            if day is None:
                day = Day(date=key)
                buckets[key] = day

            day.entries += 1

            # An entry covering a period may carry its own extremes --
            # a provider's daily summary does. Use those; otherwise
            # the instantaneous temperature is both the high and the
            # low for that moment.
            #
            # Deliberately not the percentiles: those describe how
            # uncertain one reading is, and folding them in here would
            # widen every day by the forecast error.
            high = (entry.temperature_high
                    if entry.temperature_high is not None
                    else entry.temperature)
            low = (entry.temperature_low
                   if entry.temperature_low is not None
                   else entry.temperature)

            if high is not None:
                if day.high is None or high > day.high:
                    day.high = high
            if low is not None:
                if day.low is None or low < day.low:
                    day.low = low

            if entry.wind_speed is not None:
                if day.wind_max is None or entry.wind_speed > day.wind_max:
                    day.wind_max = entry.wind_speed

            if entry.precipitation:
                # The amount already covers period_hours, so add it
                # once rather than multiplying by the period.
                day.precipitation += entry.precipitation

            if (CONDITION_SEVERITY.get(entry.condition, 0)
                    > CONDITION_SEVERITY.get(day.condition, 0)):
                day.condition = entry.condition

        ordered = [buckets[k] for k in sorted(buckets)]
        for day in ordered:
            day.precipitation = round(day.precipitation, 1)

        return ordered[:days] if days else ordered

    def next_hours(self, hours: int = 12) -> list[Conditions]:
        if not self.hourly:
            return []
        start = self.hourly[0].time
        if start is None:
            return self.hourly[:hours]
        return [h for h in self.hourly
                if h.time is not None
                and (h.time - start).total_seconds() <= hours * 3600]
