"""
OpenWeather One Call 4.0.

    https://openweathermap.org/api/one-call-4

Modular, unlike 3.0: current conditions, hourly and daily each come
from their own endpoint, so one Forecast costs three calls.

The response limits shape that choice. The 1h timeline returns at most
20 records and 1day at most 10, with further pages costing an extra
call each. Two extra pages bring the hourly window to 48 hours, making
a full fetch five calls -- roughly 240 a day against the 1,000 free,
which a car that is not running constantly will not approach.

Requires a "One Call by Call" subscription. A 3.0 subscription does
not cover 4.0; they are separate, and the key returns 401 until you
subscribe.

    settings set weather.openweather.key YOUR_KEY

Entry fields are unchanged from 3.0 -- temp, feels_like, dew_point,
uvi, wind_gust, pop, rain.1h -- so only the envelope differs. Every
endpoint wraps its records in a `data` array.

Daily entries are appended to the hourly list with a 24 hour period
rather than kept separately. Everything above the provider reads
Forecast.hourly and groups it with daily(), so a forecast that gets
coarser further out is already the normal shape.
"""

import asyncio
from datetime import datetime, timezone

from carlib.core import settings
from carlib.core.errors import NotAvailableError
from carlib.weather.base import Provider, register
from carlib.weather.types import Condition, Conditions, Forecast

BASE = 'https://api.openweathermap.org/data/4.0/onecall'

CURRENT_URL = f'{BASE}/current'
HOURLY_URL = f'{BASE}/timeline/1h'
DAILY_URL = f'{BASE}/timeline/1day'

# One Call gives instantaneous current conditions, hourly steps, and
# daily summaries.
CURRENT_HOURS = 0
HOURLY_HOURS = 1
DAILY_HOURS = 24

# Endpoints we do not call. 1min and 15min are finer than anything
# here shows, and alerts need a second request per alert id.

# The 1h timeline returns 20 records at a time, so 48 hours takes
# three requests. Each page counts against the quota, making a full
# fetch five calls rather than three -- about 240 a day against the
# 1,000 free, which is fine for a car that is not running constantly.
HOURLY_HOURS_WANTED = 48
HOURLY_PAGE_LIMIT = 3


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
    description = ('OpenWeather One Call 4.0 -- 48h hourly, 10 day '
                   'daily; needs a One Call by Call subscription')
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
        }

        # Fetched together. Sequentially this would be several round
        # trips on a link that may be cellular.
        current, hourly, daily = await asyncio.gather(
            self._get_json(CURRENT_URL, params=params),
            self._hourly_pages(params),
            self._get_json(DAILY_URL, params=params),
            return_exceptions=True,
        )

        # The current endpoint is the only one worth failing over:
        # without the timelines there is still something to show, but
        # a forecast with no conditions at all is not useful.
        if isinstance(current, BaseException):
            raise current

        return self.parse(
            current[0],
            hourly if not isinstance(hourly, BaseException) else {},
            daily[0] if not isinstance(daily, BaseException) else {},
            latitude, longitude, altitude)

    async def _hourly_pages(self, params: dict) -> dict:
        """
        Follow `next` until we have enough hours.

        The endpoint returns 20 records per response and hands back a
        prepared URL for the following page. That URL already carries
        the key and coordinates, so it is fetched as-is.

        Pages are sequential by necessity -- each one names the next.
        Failures partway are kept rather than discarded: 20 hours of
        forecast beats none.
        """
        body, _ = await self._get_json(HOURLY_URL, params=params)
        rows = list(body.get('data') or [])

        for _ in range(HOURLY_PAGE_LIMIT - 1):
            if len(rows) >= HOURLY_HOURS_WANTED:
                break
            following = body.get('next')
            if not following:
                break
            try:
                body, _ = await self._get_json(following)
            except NotAvailableError:
                break
            page = body.get('data') or []
            if not page:
                break
            rows.extend(page)

        return {**body, 'data': rows[:HOURLY_HOURS_WANTED]}

    def parse(self, current: dict, hourly: dict, daily: dict,
              latitude: float, longitude: float,
              altitude: float | None = None) -> Forecast:
        """
        Combine the three responses into one Forecast.

        Separate from fetch so it can be tested without the network.
        Every 4.0 endpoint wraps its records in a `data` array, so the
        shape is the same for all three.
        """
        current_rows = current.get('data') or []
        hourly_rows = hourly.get('data') or []
        daily_rows = daily.get('data') or []

        if not current_rows and not hourly_rows and not daily_rows:
            message = (current.get('message') or hourly.get('message')
                       or daily.get('message')
                       or 'no forecast in the response')
            raise NotAvailableError(f'{self.name}: {message}')

        entries = [parse_point(row) for row in hourly_rows]

        # Daily records extend the list past the hourly window.
        # Anything already covered is skipped so the two do not
        # overlap on the first day.
        last_hour = entries[-1].time if entries else None
        for row in daily_rows:
            day = parse_day(row)
            if (last_hour is not None and day.time is not None
                    and day.time <= last_hour):
                continue
            entries.append(day)

        now = (parse_point(current_rows[0], CURRENT_HOURS)
               if current_rows else (entries[0] if entries else None))

        return Forecast(
            provider=self.name,
            latitude=float(current.get('lat', latitude)),
            longitude=float(current.get('lon', longitude)),
            altitude=altitude,
            updated=(now.time if now is not None
                     else datetime.now(timezone.utc)),
            # No useful Expires header, so the service falls back to
            # its own TTL. OpenWeather update every 10 minutes.
            expires=None,
            current=now,
            hourly=entries,
        )
