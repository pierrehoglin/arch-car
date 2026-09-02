"""
Weather forecasts.

Providers are pluggable: `weather.provider` in settings picks one, and
adding another means writing a class and registering it. The shared
data model in types.py is what makes that work -- everything above the
provider deals in Conditions and Forecast, never in a particular
service's JSON.

MET Norway is the default. It is free without a key, covers the world
with most detail for Scandinavia, and is coordinate-based, which suits
a moving car better than a station lookup.
"""
