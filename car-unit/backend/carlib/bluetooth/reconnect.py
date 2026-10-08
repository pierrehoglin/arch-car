"""
Connecting the phones on start.

Phones rarely reach out to a car on their own when it comes on -- the
car is expected to page them, as every head unit does. So when the
daemon starts, and whenever Bluetooth is switched back on, the phones
that were connected the last time the car was used are asked to
connect -- once each. A phone that is not there to answer is left
as it is: no retrying in the background, and connecting it later is
done by hand, or by the phone itself.

Nothing is asked after that, so a phone disconnected during the drive,
from the car's screen or from the phone, stays disconnected. A link
that simply drops is BlueZ's to recover (its ReconnectAttempts
policy), not this.

"The last time" is the phones seen connected during the last drive in
which any phone connected. Written as soon as one does, since the car
gives no warning before the power goes. A phone that came along once,
weeks ago, is not paged on every start for ever.

Bluetooth switched off is left off: nothing here talks to BlueZ until
the service is running, because asking BlueZ would start it. The one
attempt waits for the adapter to be powered, so it is not spent on a
bluetoothd still coming up.

Connecting the device is all it takes for calls too: BlueZ brings up
HFP along with the rest, oFono powers that phone's modem once the
link is up, and the call watcher takes it from there.
"""

import asyncio
import logging

from carlib.core import settings
from carlib.core.errors import CarError
from carlib.system import bluetooth

log = logging.getLogger('carlib')

SETTING = 'bluetooth.auto_connect'
REMEMBERED = 'bluetooth.last_phones'

CHECK_SECONDS = 3.0

# A page to a phone that is not there gives up after about five
# seconds; anything far past that is BlueZ stuck, not the phone.
CONNECT_TIMEOUT = 30.0


def _is_phone(device) -> bool:
    return device.paired and (device.supports_hfp
                              or device.icon.startswith('phone'))


class Reconnect:

    def __init__(self) -> None:
        # Whether Bluetooth was up at the last look.
        self._up = False
        # Whether this start's one attempt has been made.
        self._done = False
        # The phones from last time, read as Bluetooth came on -- before
        # anything connecting this time can overwrite the list.
        self._wanted: list[str] = []
        # Phones that have connected since Bluetooth came on.
        self._seen: list[str] = []

    def _remember(self, address: str) -> None:
        """Note a phone as connected this drive, and save the list."""
        if address in self._seen:
            return
        self._seen.append(address)
        settings.set(REMEMBERED, list(self._seen))

    async def _connect_once(self, phones: dict) -> None:
        """Ask each phone from last time to connect, once."""
        self._done = True
        if not settings.get_bool(SETTING, True):
            return

        for address in self._wanted:
            device = phones.get(address)
            if device is None or device.connected:
                # Forgotten since, or here already.
                continue
            try:
                await asyncio.wait_for(bluetooth.connect(device.address),
                                       CONNECT_TIMEOUT)
                log.info('reconnect: connected %s', device.name)
            except (CarError, asyncio.TimeoutError) as exc:
                log.info('reconnect: %s not there (%s), left as it is',
                         device.name, exc)

    async def _tick(self) -> None:
        try:
            adapter = await bluetooth.status()
        except Exception:
            adapter = None

        if adapter is None or not adapter.service_active:
            # Off: the next time it comes on counts as a start.
            self._up = self._done = False
            return

        if not self._up:
            self._up = True
            self._seen = []
            self._wanted = [a.upper() for a in settings.get_list(REMEMBERED)]

        phones = {d.address.upper(): d
                  for d in await bluetooth.devices() if _is_phone(d)}

        if not self._done and adapter.powered:
            await self._connect_once(phones)
            phones = {d.address.upper(): d
                      for d in await bluetooth.devices() if _is_phone(d)}

        for address, device in phones.items():
            if device.connected:
                self._remember(address)

    async def run(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception('reconnect failed')
            await asyncio.sleep(CHECK_SECONDS)


current = Reconnect()
