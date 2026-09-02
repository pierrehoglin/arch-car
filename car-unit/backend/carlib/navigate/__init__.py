"""
Routing and guidance.

    routing    ask Valhalla for a route between points
    guidance   follow one: where we are along it, and when we leave it

Valhalla rather than OSRM because it does both jobs. Its /route gives
turn-by-turn maneuvers, and /trace_route snaps a GPS trace to the road
network -- which is what stops the position marker wandering into
fields beside the carriageway.

The public FOSSGIS server carries a full planet graph and is fine to
start with. Its fair-usage limit is one call per second, which the
client enforces. Point `navigation.url` at a local instance for
routing that works without signal, which is exactly when you need it.
"""
