"""
OpenWeather One Call 3.0.

    https://openweathermap.org/api/one-call-3

Hourly for 48 hours, then daily for 8 days, plus current conditions.
UV index, dew point and per-period precipitation probability come with
it, which the older 5-day endpoint does not carry.

Requires an API key AND an active One Call subscription. The free tier
is 1,000 calls a day, but OpenWeather ask for card details even for
that -- worth setting a daily cap in their billing page so it can
never be exceeded.

    settings set weather.openweather.key YOUR_KEY

The daily entries are appended to the hourly list with a 24 hour
period rather than kept separately. Everything above the provider
reads Forecast.hourly and groups it with daily(), so a forecast that
gets coarser further out is already the normal shape -- MET moves from
1 to 6 hour steps the same way.
"""

from datetime import datetime, timezone

from carlib.core import settings
from carlib.core.errors import NotAvailableError
from carlib.weather.base import Provider, register
from carlib.weather.types import Condition, Conditions, Forecast

BASE_URL = 'https://api.openweathermap.org/data/3.0/onecall'

# One Call gives instantaneous current conditions, hourly steps, and
# daily summaries.
CURRENT_HOURS = 0
HOURLY_HOURS = 1
DAILY_HOURS = 24

# Blocks we do not use. minutely is 60 minutes of precipitation
# intensity with no equivalent in other providers; alerts are free
# text. Excluding them keeps the response smaller.
EXCLUDE = 'minutely,alerts'


# Condition codes, grouped by leading digit.
#
#   2xx thunderstorm   3xx drizzle   5xx rain
#   6xx snow           7xx atmosphere (mist, fog, dust)
#   800 clear          80x clouds
#
# https://openweathermap.org/weather-conditions
SPECIAL = {
    511: Condition.SLEET,       # freezing rain
    611: Condition.SLEET,
    612: Condition.SLEET,
    613: Condition.SLEET,
    615: Condition.SLEET,
    616: Condition.SLEET,
    620: Condition.SLEET,
    621: Condition.SLEET,
    622: Condition.SLEET,
    800: Condition.CLEAR,
    801: Condition.PARTLY_CLOUDY,       # few clouds, 11-25%
    802: Condition.PARTLY_CLOUDY,       # scattered, 25-50%
    803: Condition.CLOUDY,
    804: Condition.CLOUDY,
}

GROUPS = {
    2: Condition.THUNDER,
    3: Condition.DRIZZLE,
    5: Condition.RAIN,
    6: Condition.SNOW,
    7: Condition.FOG,           # mist, smoke, haze, dust, fog, squall
}


def parse_code(code) -> Condition:
    """
    Map an OpenWeather condition code onto our vocabulary.

    Exceptions first: 511 is freezing rain despite being a 5xx, and
    the 61x/62x sleet codes sit inside the snow group.
    """
    try:
        number = int(code)
    except (TypeError, ValueError):
        return Condition.UNKNOWN

    if number in SPECIAL:
        return SPECIAL[number]
    return GROUPS.get(number // 100, Condition.UNKNOWN)


def _time(value) -> datetime | None:
    """One Call sends Unix timestamps."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _precipitation(entry: dict) -> float:
    """
    Rain and snow, however this block spells it.

    Current and hourly entries nest the amount under a period key --
    {"rain": {"1h": 0.5}} -- while daily entries give a bare number.
    """
    total = 0.0
    for kind in ('rain', 'snow'):
        block = entry.get(kind)
        if isinstance(block, dict):
            for value in block.values():
                try:
                    total += float(value)
                except (TypeError, ValueError):
                    continue
        elif block is not None:
            try:
                total += float(block)
            except (TypeError, ValueError):
                continue
    return round(total, 2)


def _common(entry: dict, result: Conditions) -> None:
    """Fields that sit in the same place in every block."""
    weather = (entry.get('weather') or [{}])[0]

    result.time = _time(entry.get('dt'))
    result.humidity = entry.get('humidity')
    result.pressure = entry.get('pressure')
    result.dew_point = entry.get('dew_point')
    result.wind_speed = entry.get('wind_speed')
    result.wind_gust = entry.get('wind_gust')
    result.wind_direction = entry.get('wind_deg')
    result.cloud_cover = entry.get('clouds')
    result.uv_index = entry.get('uvi')
    result.visibility = entry.get('visibility')
    result.condition = parse_code(weather.get('id'))
    result.symbol = str(weather.get('icon', ''))
    result.precipitation = _precipitation(entry)

    # pop is a fraction here; everything else is a percentage.
    pop = entry.get('pop')
    if pop is not None:
        try:
            result.precipitation_probability = round(float(pop) * 100, 1)
        except (TypeError, ValueError):
            pass


def parse_point(entry: dict, period: int = HOURLY_HOURS) -> Conditions:
    """A current or hourly entry, where temp is a single number."""
    result = Conditions(period_hours=period)
    _common(entry, result)
    result.temperature = entry.get('temp')
    result.feels_like = entry.get('feels_like')
    return result


def parse_day(entry: dict) -> Conditions:
    """
    A daily entry, where temp and feels_like are objects.

    The day's extremes go into temperature_high/low, and the
    temperature itself is the daytime value -- the one a forecast row
    should show.
    """
    result = Conditions(period_hours=DAILY_HOURS)
    _common(entry, result)

    temp = entry.get('temp')
    if isinstance(temp, dict):
        result.temperature = temp.get('day')
        result.temperature_low = temp.get('min')
        result.temperature_high = temp.get('max')
    elif temp is not None:
        result.temperature = temp

    feels = entry.get('feels_like')
    if isinstance(feels, dict):
        result.feels_like = feels.get('day')
    elif feels is not None:
        result.feels_like = feels

    return result


@register
class OpenWeatherProvider(Provider):
    name = 'openweather'
    description = ('OpenWeather 5 day / 3 hour -- needs a free API '
                   'key, no card')
    global_coverage = True

    def api_key(self) -> str:
        key = settings.get_str('weather.openweather.key', '')
        if not key:
            raise NotAvailableError(
                'no OpenWeather API key',
                hint='settings set weather.openweather.key YOUR_KEY, '
                     'from https://home.openweathermap.org/api_keys')
        return key

    async def fetch(self, latitude: float, longitude: float,
                    altitude: float | None = None) -> Forecast:
        params = {
            'lat': round(latitude, 4),
            'lon': round(longitude, 4),
            'appid': self.api_key(),
            # Celsius and m/s, matching the shared model. Without this
            # temperatures come back in Kelvin.
            'units': 'metric',
            'exclude': EXCLUDE,
        }

        body, headers = await self._get_json(BASE_URL, params=params)
        return self.parse(body, headers, latitude, longitude, altitude)

    def parse(self, body: dict, headers: dict,
              latitude: float, longitude: float,
              altitude: float | None = None) -> Forecast:
        """
        Turn a One Call response into a Forecast.

        Separate from fetch so it can be tested without the network.
        """
        current = body.get('current')
        hourly = body.get('hourly') or []
        daily = body.get('daily') or []

        if not current and not hourly and not daily:
            message = body.get('message') or 'no forecast in the response'
            raise NotAvailableError(f'{self.name}: {message}')

        entries = [parse_point(e) for e in hourly]

        # Daily entries extend the list past the 48 hour hourly limit.
        # Anything already covered by an hourly entry is skipped, so
        # the two do not overlap on the first two days.
        last_hour = entries[-1].time if entries else None
        for raw in daily:
            day = parse_day(raw)
            if (last_hour is not None and day.time is not None
                    and day.time <= last_hour):
                continue
            entries.append(day)

        return Forecast(
            provider=self.name,
            latitude=float(body.get('lat', latitude)),
            longitude=float(body.get('lon', longitude)),
            altitude=altitude,
            updated=_time((current or {}).get('dt'))
            or datetime.now(timezone.utc),
            # No useful Expires header, so the service falls back to
            # its own TTL. OpenWeather update roughly every 10 minutes.
            expires=None,
            current=(parse_point(current, CURRENT_HOURS)
                     if current else (entries[0] if entries else None)),
            hourly=entries,
        )
