"""Drive any engine that implements design 4.5, in plain integers and tuples.

The shared suite never touches an engine's own classes directly. It goes
through :class:`Driver`, which builds each ``Order`` from the engine's
module and reads every ``Fill``, ``Resting`` and ``Book`` back into the
tuples below by attribute name. So the same tests run against the Python
reference engine now and the C++ module in R8, and compare them exactly.

The driver plays the session manager's part and nothing more: it assigns
each order an increasing arrival sequence (design 2.3).
"""

from __future__ import annotations

import importlib
from typing import NamedTuple

# name -> (module, engine class). design 4.5.
ENGINES: dict[str, tuple[str, str]] = {
    "py": ("oxdaq.engine", "ReferenceEngine"),
    "cpp": ("oxdaq_engine", "Engine"),
}
_TYPES = ("Side", "OrderType", "Order")


class F(NamedTuple):
    """A fill, as the suite compares it. design 4.5 ``Fill``."""

    maker: int
    taker: int
    instrument: int
    price: int
    volume: int


class R(NamedTuple):
    """A resting order, as the suite compares it. design 4.5 ``Resting``."""

    order_id: int
    team: int
    price: int
    remaining: int
    arrival_seq: int


class B(NamedTuple):
    """One instrument's book, each side best first. design 4.5 ``Book``."""

    bids: tuple[R, ...]
    asks: tuple[R, ...]


class EngineMissingError(Exception):
    """The engine, or a name design 4.5 requires of it, does not exist yet."""


def load(name: str):
    """Import an engine's module and check it has every name design 4.5 pins.

    Raises:
        EngineMissingError: with a message saying exactly what to write. Any
            other import failure (a bug inside the engine) propagates with
            its traceback, because that is the useful thing to see.
    """
    module_name, cls_name = ENGINES[name]
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name not in (module_name, module_name.split(".")[0]):
            raise
        if name == "cpp":
            raise EngineMissingError(
                "the C++ engine arrives in R8 (E1): oxdaq_engine is not built"
            ) from None
        raise EngineMissingError(
            f"no engine yet: write {module_name} (design 4.5), exporting "
            f"{', '.join((*_TYPES, cls_name))}"
        ) from None
    missing = [n for n in (*_TYPES, cls_name) if not hasattr(module, n)]
    if missing:
        if name == "cpp":
            raise EngineMissingError(
                f"the C++ engine arrives in R8 (E1): oxdaq_engine has no "
                f"{', '.join(missing)} yet"
            )
        raise EngineMissingError(
            "no engine yet: write "
            + ", ".join(f"{module_name}.{n}" for n in missing)
            + " (design 4.5)"
        )
    return module, getattr(module, cls_name)


class Driver:
    """One fresh engine, driven the way the session manager will drive it."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.module, engine_cls = load(name)
        self.engine = engine_cls()
        self.arrival_seq_of: dict[int, int] = {}
        self._arrival_seq = 0

    def __repr__(self) -> str:
        return f"Driver({self.name!r})"

    def submit(
        self,
        order_id: int,
        side: str,
        price: int,
        volume: int,
        *,
        order_type: str = "limit",
        team: int = 1,
        instrument: int = 0,
    ) -> list[F]:
        """Process one order and return its fills. ``side`` is "bid" or "ask"."""
        self._arrival_seq += 1
        self.arrival_seq_of[order_id] = self._arrival_seq
        m = self.module
        order = m.Order(
            order_id=order_id,
            team_id=team,
            instrument_id=instrument,
            side=m.Side.BID if side == "bid" else m.Side.ASK,
            order_type=m.OrderType.LIMIT if order_type == "limit" else m.OrderType.IOC,
            price_ticks=price,
            volume=volume,
            remaining_volume=volume,
            arrival_seq=self._arrival_seq,
        )
        return [
            F(
                f.maker_order_id,
                f.taker_order_id,
                f.instrument_id,
                f.price_ticks,
                f.volume,
            )
            for f in self.engine.process(order)
        ]

    def cancel(self, order_id: int) -> int | None:
        return self.engine.cancel(order_id)

    def book(self, instrument: int = 0) -> B:
        snap = self.engine.snapshot(instrument)
        return B(_side(snap.bids), _side(snap.asks))


def _side(orders) -> tuple[R, ...]:
    return tuple(
        R(o.order_id, o.team_id, o.price_ticks, o.remaining_volume, o.arrival_seq)
        for o in orders
    )
