"""
Bluetooth domain.

    agent      answers BlueZ during pairing
    pairing    the daemon's pairing window and agent upkeep
    calls      HFP, through oFono
    media      AVRCP playback
    phonebook  PBAP, through obexd
    messages   MAP, through obexd

Deliberately no eager imports, as with carlib.location. The daemon
imports `pairing` at startup, and pairing needs only BlueZ -- it
should not also require oFono and obexd to be importable. Import the
submodule you need:

    from carlib.bluetooth import calls

Calls need bluez and ofono; contacts and messages need bluez-obex; HFP
additionally needs WirePlumber configured to defer to oFono -- see
HFP_SERVICE_ORDERING.md.
"""

__all__ = ['agent', 'pairing', 'calls', 'media', 'phonebook', 'messages']
