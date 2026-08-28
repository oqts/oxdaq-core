"""``oqts``: the client library for OXDAQ, the OQTS live trading simulator.

Everything a participant needs is importable from here directly::

    from oqts import BaseAlgorithm, Side

    class MyStrategy(BaseAlgorithm):
        def on_book_updated(self, instrument_id, book):
            ...

    if __name__ == "__main__":
        MyStrategy().run()

Nothing below the top level should ever need to be imported by a
strategy. If it does, that is a bug in this package's ergonomics, not in
the strategy.

At milestone 1 only the protocol layer exists. ``BaseAlgorithm`` and the
participant-facing types arrive at milestone 6.
"""

from .protocol import PROTOCOL_VERSION, Side

__all__ = ["PROTOCOL_VERSION", "Side"]
__version__ = "0.1.0.dev0"
