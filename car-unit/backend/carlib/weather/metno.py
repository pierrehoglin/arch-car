"""
MET Norway Locationforecast 2.0.

Free, no API key, worldwide with most detail for Scandinavia. Data is
Creative Commons licensed including commercial use.

Uses the `complete` endpoint. `compact` omits wind gust, dew point,
UV, fog, cloud layers and the forecast percentiles, which are worth
the larger response.

Locationforecast reports no visibility, so Conditions has no such
field -- one that nothing ever sets would show as null and read like
missing data.

`complete` reports apparent_air_temperature. MET's own FAQ predates
that field and still says to calculate one, so this module computes a
fallback for responses that lack it.

    https://api.met.no/weatherapi/locationforecast/2.0/documentation

Two rules from their terms, both enforced:

The User-Agent must identify you. Locationforecast 2.0 blocks rather
than throttles when it is missing or generic, so `weather.contact`
should be set to an email or site.

Requests must respect the Expires header rather than polling. The
service layer caches on it; this module just reports it.

Coordinates are rounded to four decimals. Their changelog once
threatened a 403 for more, which does not appear to be enforced, but
rounding improves their cache hit rate and costs nothing -- four
decimals is about 11 metres.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from carlib.core.errors import NotAvailableError
from carlib.weather.base import Provider, register
from carlib.weather.types import Condition, Conditions, Forecast

# `complete` rather than `compact`. The extra instant fields are the
# reason: wind gust, dew point, UV index, fog fraction and cloud cover
# by altitude are complete-only, and reading them from a compact
# response silently yields None.
BASE_URL = 'https://api.met.no/weatherapi/locationforecast/2.0/complete'

# Their symbol codes are compound: a base word, sometimes a modifier,
# and a _day/_night/_polartwilight suffix.
#
# Order matters twice over. Precipitation before cloud, so
# "lightrainshowers_day" is rain rather than being missed. And
# "partlycloudy" before "cloudy", because the latter is a substring of
# the former -- checking "cloudy" first turns every partly cloudy sky
# into an overcast one.
SYMBOLS = (
    ('thunder', Condition.THUNDER),
    ('sleet', Condition.SLEET),
    ('snow', Condition.SNOW),
    ('drizzle', Condition.DRIZZLE),
    ('rain', Condition.RAIN),
    ('fog', Condition.FOG),
    ('partlycloudy', Condition.PARTLY_CLOUDY),
    ('cloudy', Condition.CLOUDY),
    ('fair', Condition.PARTLY_CLOUDY),
    ('clearsky', Condition.CLEAR),
)


def parse_symbol(code: str) -> Condition:
    """
    Map a MET symbol code onto our vocabulary.

    First match wins, so SYMBOLS is ordered deliberately:
    "lightrainandthunder" contains both "rain" and "thunder", and
    thunder is the more useful thing to show.
    """
    if not code:
        return Condition.UNKNOWN

    lowered = code.lower()
    for needle, condition in SYMBOLS:
        if needle in lowered:
            return condition
    return Condition.UNKNOWN


def apparent_temperature(temperature: float | None,
                         wind_speed: float | None,
                         humidity: float | None) -> float | None:
    """
    How cold or hot it feels, when the service does not say.

    Only a fallback: `complete` now reports apparent_air_temperature,
    which is preferred wherever it appears.

    Thresholds follow the ones MET documents for Yr, so a computed
    value stays close to what Yr shows: wind chill below 10 C with
    wind above 1.33 m/s, heat index above 26 C with humidity above
    40 %, and the plain temperature between.

    There is no standard formula for apparent temperature -- it
    differs between services, and ideally would account for solar
    radiation, which forecasts do not carry.
    """
    if temperature is None:
        return None

    if temperature < 10.0 and wind_speed is not None:
        if wind_speed <= 1.33:
            return round(temperature, 1)
        # The JAG/TI formula takes km/h; MET reports m/s.
        kmh = wind_speed * 3.6
        factor = kmh ** 0.16
        chill = (13.12 + 0.6215 * temperature
                 - 11.37 * factor + 0.3965 * temperature * factor)
        return round(chill, 1)

    if temperature > 26.0 and humidity is not None and humidity > 40.0:
        t = temperature
        h = humidity
        index = (-8.784695 + 1.61139411 * t + 2.338549 * h
                 - 0.14611605 * t * h - 0.012308094 * t * t
                 - 0.016424828 * h * h + 0.002211732 * t * t * h
                 + 0.00072546 * t * h * h
                 - 0.000003582 * t * t * h * h)
        return round(index, 1)

    return round(temperature, 1)


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None


def _http_time(value: str | None) -> datetime | None:
    """Parse an HTTP date header, e.g. Expires."""
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def parse_entry(entry: dict) -> Conditions:
    """
    One timeseries entry.

    The shape is an instantaneous reading plus optional forward-looking
    blocks. next_1_hours is preferred for the symbol and precipitation
    because it is the finest resolution; it stops being present a few
    days out, where only next_6_hours remains.
    """
    data = entry.get('data') or {}
    instant = ((data.get('instant') or {}).get('details') or {})

    result = Conditions(
        time=_time(entry.get('time')),
        temperature=instant.get('air_temperature'),
        humidity=instant.get('relative_humidity'),
        pressure=instant.get('air_pressure_at_sea_level'),
        dew_point=instant.get('dew_point_temperature'),
        temperature_min=instant.get('air_temperature_percentile_10'),
        temperature_max=instant.get('air_temperature_percentile_90'),
        wind_speed=instant.get('wind_speed'),
        wind_gust=instant.get('wind_speed_of_gust'),
        wind_speed_min=instant.get('wind_speed_percentile_10'),
        wind_speed_max=instant.get('wind_speed_percentile_90'),
        wind_direction=instant.get('wind_from_direction'),
        cloud_cover=instant.get('cloud_area_fraction'),
        cloud_low=instant.get('cloud_area_fraction_low'),
        cloud_medium=instant.get('cloud_area_fraction_medium'),
        cloud_high=instant.get('cloud_area_fraction_high'),
        fog=instant.get('fog_area_fraction'),
        uv_index=instant.get('ultraviolet_index_clear_sky'),
    )

    # Prefer what the service reports. apparent_air_temperature is
    # newer than MET's own FAQ, which still says to calculate it, so
    # fall back to computing when it is absent -- older responses and
    # other providers will not have it.
    reported = instant.get('apparent_air_temperature')
    if reported is not None:
        result.feels_like = reported
    else:
        result.feels_like = apparent_temperature(
            result.temperature, result.wind_speed, result.humidity)

    for key, hours in (('next_1_hours', 1),
                       ('next_6_hours', 6),
                       ('next_12_hours', 12)):
        block = data.get(key)
        if not block:
            continue

        summary = block.get('summary') or {}
        details = block.get('details') or {}

        result.symbol = summary.get('symbol_code', '')
        result.condition = parse_symbol(result.symbol)
        result.precipitation = details.get('precipitation_amount')
        result.precipitation_min = details.get(
            'precipitation_amount_min')
        result.precipitation_max = details.get(
            'precipitation_amount_max')
        result.precipitation_probability = details.get(
            'probability_of_precipitation')
        result.thunder_probability = details.get(
            'probability_of_thunder')
        result.period_hours = hours
        break

    return result


@register
class MetNoProvider(Provider):
    name = 'metno'
    description = ('MET Norway Locationforecast 2.0 -- free, no key, '
                   'best detail in Scandinavia')
    global_coverage = True

    async def fetch(self, latitude: float, longitude: float,
                    altitude: float | None = None) -> Forecast:
        params = {
            'lat': round(latitude, 4),
            'lon': round(longitude, 4),
        }
        if altitude is not None:
            # They want metres as an integer, and use it to correct
            # the temperature for elevation.
            params['altitude'] = int(round(altitude))

        body, headers = await self._get_json(BASE_URL, params=params)
        return self.parse(body, headers, latitude, longitude, altitude)

    def parse(self, body: dict, headers: dict,
              latitude: float, longitude: float,
              altitude: float | None = None) -> Forecast:
        """
        Turn a Locationforecast response into a Forecast.

        Separate from fetch so it can be tested without the network.
        """
        properties = body.get('properties') or {}
        series = properties.get('timeseries') or []

        if not series:
            raise NotAvailableError(
                f'{self.name}: no forecast in the response')

        meta = properties.get('meta') or {}

        # The response geometry is the grid point actually used, which
        # can differ from what was asked for.
        coords = ((body.get('geometry') or {}).get('coordinates')
                  or [longitude, latitude])

        entries = [parse_entry(e) for e in series]

        return Forecast(
            provider=self.name,
            longitude=float(coords[0]) if len(coords) > 0 else longitude,
            latitude=float(coords[1]) if len(coords) > 1 else latitude,
            altitude=(float(coords[2]) if len(coords) > 2
                      else altitude),
            updated=_time(meta.get('updated_at')),
            expires=_http_time(headers.get('expires')),
            current=entries[0] if entries else None,
            hourly=entries,
        )
