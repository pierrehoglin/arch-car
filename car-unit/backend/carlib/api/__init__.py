"""
HTTP API and client.

A single long-running process owns the runtime state and serves it to
everything else. The CLIs become thin clients; a browser UI can use
the same routes.

State ownership is the point. With files under XDG_RUNTIME_DIR, two
processes doing read-modify-write lose each other's updates -- that is
what made a traffic-announcement timeout never expire. One owner and
no files removes the class of bug entirely.

The server listens on a Unix socket by default, so the CLIs never go
over the network. A TCP listener can be added for a browser UI, but
bind it to localhost: the hotspot is on the same machine, and
passengers should not be able to change stations.
"""
