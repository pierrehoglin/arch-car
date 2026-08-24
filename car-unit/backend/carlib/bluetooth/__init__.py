"""
Bluetooth domain: calls, media, contacts, messages.

Requires bluez, ofono and bluez-obex. HFP additionally needs
WirePlumber configured to defer to oFono -- see HFP_SERVICE_ORDERING.md.
"""

from carlib.bluetooth import calls, media, phonebook, messages

__all__ = ['calls', 'media', 'phonebook', 'messages']
