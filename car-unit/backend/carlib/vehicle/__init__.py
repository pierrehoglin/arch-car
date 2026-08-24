"""
Vehicle data: CAN bus and OBD-II.

Unlike the rest of carlib this does not use D-Bus -- CAN goes through
socketcan, so these modules import only carlib.core.

    sudo pacman -S can-utils
    uv add python-can

Bring an interface up before use:

    sudo ip link set can0 type can bitrate 500000
    sudo ip link set can0 up
"""

from carlib.vehicle import can

__all__ = ['can']
