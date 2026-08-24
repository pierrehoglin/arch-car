"""
System control: services, radios, network and audio.

Unlike the other subpackages this one is not tied to a single
transport. Service and Bluetooth control go over D-Bus; wifi and audio
shell out to nmcli and wpctl, because NetworkManager's connection
settings and PipeWire's volume have no practical D-Bus surface. Each
module says why in its docstring.
"""
