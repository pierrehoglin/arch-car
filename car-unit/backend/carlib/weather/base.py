"""
The provider interface and registry.

Adding a service means subclassing Provider, mapping its vocabulary
onto carlib.weather.types, and calling register(). Removing one means
deleting the module and its registration -- nothing else refers to a
provider by name except the `weather.provider` setting.
"""

from abc import ABC, abstractmethod

from carlib.core import settings
from carlib.core.errors import NotAvailableError, NotFoundError
from carlib.weather.types import Forecast

# Sent to every provider so they can identify us. MET Norway blocks
# requests with a missing or generic User-Agent rather than throttling
# them, and other services are heading the same way.
#
# Set `weather.contact` to your email or site. Providers are within
# their rights to block traffic they cannot attribute.
DEFAULT_CONTACT = 'https://github.com/unknown/car-unit'

REQUEST_TIMEOUT = 15.0

_providers: dict[str, type['Provider']] = {}


def register(cls: type['Provider']) -> type['Provider']:
    """Make a provider selectable by name. Usable as a decorator."""
    _providers[cls.name] = cls
    return cls


def available() -> list[str]:
    return sorted(_providers)


def get(name: str | None = None) -> 'Provider':
    """
    The configured provider, or one by name.

    Falls back to the default rather than raising when the setting
    names something unknown -- a typo in a config file should not
    leave a car with no weather at all.
    """
    if name is None:
        name = settings.get_str('weather.provider', DEFAULT_PROVIDER)

    cls = _providers.get(name)
    if cls is None:
        if not _providers:
            raise NotAvailableError('no weather providers registered')
        cls = _providers.get(DEFAULT_PROVIDER)
        if cls is None:
            raise NotFoundError('weather provider', name, available())

    return cls()


def user_agent() -> str:
    """
    Identification for outgoing requests.

    Providers ask for something that reaches a human. `contact`
    identifies this unit to any external service; `weather.contact`
    overrides it for weather only.
    """
    contact = (settings.get_str('weather.contact', '')
               or settings.get_str('contact', '')
               or DEFAULT_CONTACT)
    return f'carlib-car-unit/0.1 {contact}'


class Provider(ABC):
    """
    A weather service.

    Implementations are cheap to construct -- one is made per request
    -- so keep any expensive setup out of __init__.
    """

    #: Name used in the `weather.provider` setting.
    name: str = ''

    #: Shown by `weather providers`.
    description: str = ''

    #: Whether the service covers the whole world or one region.
    global_coverage: bool = True

    @abstractmethod
    async def fetch(self, latitude: float, longitude: float,
                    altitude: float | None = None) -> Forecast:
        """
        A forecast for one point.

        Should raise NotAvailableError for anything the caller cannot
        fix -- network failures, rate limits, a service being down --
        so that every provider fails the same way.
        """
        raise NotImplementedError

    async def _get_json(self, url: str, params: dict | None = None,
                        headers: dict | None = None) -> tuple[dict, dict]:
        """
        Fetch JSON, returning (body, response headers).

        The headers matter: several services put cache lifetime in
        Expires, and honouring it is part of their terms rather than a
        nicety.
        """
        try:
            import httpx
        except ImportError as exc:
            raise NotAvailableError(
                'httpx is not installed',
                hint='uv sync') from exc

        request_headers = {'User-Agent': user_agent(),
                           'Accept': 'application/json'}
        request_headers.update(headers or {})

        try:
            async with httpx.AsyncClient(
                    timeout=REQUEST_TIMEOUT,
                    follow_redirects=True) as client:
                response = await client.get(url, params=params,
                                            headers=request_headers)
        except Exception as exc:
            raise NotAvailableError(
                f'{self.name}: cannot reach the service: {exc}',
                hint='check the network connection') from exc

        if response.status_code == 403:
            raise NotAvailableError(
                f'{self.name}: refused the request (403)',
                hint='most services require a User-Agent that '
                     'identifies you; set weather.contact')
        if response.status_code == 429:
            raise NotAvailableError(
                f'{self.name}: rate limited (429)',
                hint='requests are being made too often; the cache '
                     'should normally prevent this')
        if response.status_code >= 400:
            raise NotAvailableError(
                f'{self.name}: request failed '
                f'({response.status_code})')

        try:
            return response.json(), dict(response.headers)
        except ValueError as exc:
            raise NotAvailableError(
                f'{self.name}: response was not JSON') from exc


# Set after the built-in providers register themselves.
DEFAULT_PROVIDER = 'metno'
