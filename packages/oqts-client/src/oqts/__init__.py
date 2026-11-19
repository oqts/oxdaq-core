"""``oqts``: the client library for OXDAQ, the OQTS live trading simulator.

Everything a participant needs is importable from here directly::

    from oqts import Exchange

    ex = Exchange(host="oxdaq.oqts.org")
    ex.connect()

Nothing below the top level should ever need to be imported by a
strategy. If it does, that is a bug in this package's ergonomics, not in
the strategy.

At milestone 1 only the protocol layer exists. ``Exchange``, ``oqts.aio``
and the participant-facing types arrive at milestone 6 (docs/client.md).
"""

from .protocol import PROTOCOL_VERSION, OrderType, Side

__all__ = ["PROTOCOL_VERSION", "OrderType", "Side"]
__version__ = "0.1.0.dev0"
