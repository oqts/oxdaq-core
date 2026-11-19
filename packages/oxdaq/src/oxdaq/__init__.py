"""``oxdaq``: the OXDAQ exchange server.

Matching engine, session manager, WebSocket gateway, price process, bot
runner and trade tape. Wire definitions live in ``oqts.protocol``, which
this package depends on: bots connect over localhost using the
participant protocol, so the server needs the client package anyway
(design.md 7.1).
"""

__version__ = "0.1.0.dev0"
