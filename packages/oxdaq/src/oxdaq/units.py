"""The integer/decimal boundary. design.md 3.

Integers inside, decimals on the wire. This module is the **only** place
in the server where a price or a cash figure is allowed to be a float
(design.md 3.3). Everything upstream of it, the order book, the accounting and
the session manager, works in integers, which is why no epsilon
comparison exists anywhere in the engine.

Server-side only. The client library is float-native throughout: a
participant never sees a tick count.

Three representations, per design.md 3.2:

===============  ==========  ==============================================
Quantity         Internal    Meaning
===============  ==========  ==============================================
Price            ``int``     ``price_ticks``, a count of ticks
Cash, notional   ``int``     accounting units, 1 unit = 1/10000 currency
Volume, position ``int``     units, already integral
===============  ==========  ==============================================
"""

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

__all__ = [
    "MAX_PRICE_TICKS",
    "TICK_SCALE",
    "TickScale",
    "cash_to_wire",
    "cash_units_from_decimal",
]

TICK_SCALE: Final[int] = 10_000
"""Accounting units per currency unit. design.md 3.2."""

MAX_PRICE_TICKS: Final[int] = 2**48
"""Largest tick count for which the wire round trip is guaranteed exact.

The round trip ``from_wire(to_wire(t)) == t`` is what lets a strategy read
``book.bids[0].price`` off the wire and submit a join order at exactly
that price. If it failed, a market maker would sit one tick behind the
book forever and never know why. So it is a property worth stating a
domain for rather than assuming.

Measured, not derived. Sampling random tick counts by magnitude across
sixteen tick sizes: clean through ``2**50``, first failures at ``2**51``.
The cause is ordinary float64 relative error of about ``2**-53``, which
eventually exceeds the half tick of slack that round-half-up allows.

``2**48`` is the enforced bound, three binary orders of magnitude below
the first observed failure. At the finest permitted tick it is a price of
about 2.8e10 currency units, so nothing real approaches it. It exists so
the property-based test asserts over a domain it can actually support,
and so validation can refuse anything outside it rather than silently
misbehaving.
"""


class TickSizeError(ValueError):
    """A ``tick_size`` that is not an exact positive multiple of 1/10000."""


@dataclass(frozen=True, slots=True)
class TickScale:
    """The conversion between one instrument's tick prices and the wire.

    Constructed once per instrument at config load and then read-only, so
    the parsing cost is paid once and never on the order path.

    Attributes:
        tick_size: The instrument's tick, as an exact ``Decimal``.
        tick_units: Accounting units per tick. ``0.01`` -> ``100``.
    """

    tick_size: Decimal
    tick_units: int

    @classmethod
    def from_config(cls, tick_size: str | Decimal | int) -> "TickScale":
        """Build from a config value, rejecting anything finer than 1/10000.

        design.md 3.2: every ``tick_size`` must be an exact integer multiple of
        1/10000, which permits ticks from 0.0001 upward.

        A ``float`` is refused outright, and that is the point. The naive
        check ``tick_size * 10_000 == int(tick_size * 10_000)`` rejects
        ``0.07``, which is a perfectly legal tick, because
        ``0.07 * 10_000`` is ``700.0000000000001`` in binary float. Config
        must therefore reach here as a string or a ``Decimal``, never
        through ``float``.

        Raises:
            TickSizeError: Not positive, not exactly representable, or
                finer than 1/10000.
        """
        if isinstance(tick_size, float):
            raise TickSizeError(
                "tick_size must be given as a string or Decimal, not a float: "
                "a float cannot represent 0.01 exactly and the multiple-of-1/10000 "
                "check is unreliable against one (design.md 3.2)"
            )
        try:
            value = Decimal(tick_size)
        except InvalidOperation as exc:
            raise TickSizeError(f"tick_size is not a number: {tick_size!r}") from exc

        if not value.is_finite() or value <= 0:
            raise TickSizeError(f"tick_size must be positive and finite: {value}")

        scaled = value * TICK_SCALE
        if scaled != scaled.to_integral_value():
            raise TickSizeError(
                f"tick_size {value} is not an exact multiple of 1/{TICK_SCALE}"
            )
        return cls(tick_size=value, tick_units=int(scaled))

    # --- outbound: integer ticks -> decimal on the wire (design.md 3.3) ---

    def to_wire(self, price_ticks: int) -> float:
        """Convert a tick count to the decimal price a participant sees.

        Integer multiply, then one divide, rather than the more obvious
        ``price_ticks * float(tick_size)``. The obvious form rounds twice,
        once converting the tick size to binary and once multiplying, and
        the two errors compound into a visibly wrong figure: at a 0.07
        tick, 1234 ticks comes out as ``86.38000000000001`` instead of
        ``86.38``. Participants would see that on their dashboards.

        This form does the multiply in exact integer arithmetic and leaves
        exactly one correctly-rounded float operation, so the result is
        always the float nearest the true decimal value. Verified over
        1.9M tick/tick-size pairs.
        """
        return (price_ticks * self.tick_units) / TICK_SCALE

    # --- inbound: decimal from the wire -> integer ticks (design.md 3.3) ---

    def from_wire(self, price: float) -> int:
        """Normalise a submitted price to the nearest tick, half rounding up.

        ``math.floor(x + 0.5)`` rather than ``round(x)``: Python's builtin
        is banker's rounding, so ``round(0.5) == 0``, which is not a rule
        you want to explain in participant documentation. Round half up is
        one sentence.

        design.md 5.5 normalises **before** validating, so buying power is
        checked against the price that will actually be reserved (D4).
        """
        return math.floor(price * TICK_SCALE / self.tick_units + 0.5)

    # --- integer arithmetic, exact (design.md 3.2) ---

    def price_units(self, price_ticks: int) -> int:
        """Price in accounting units. Exact."""
        return price_ticks * self.tick_units

    def notional(self, price_ticks: int, volume: int) -> int:
        """Total consideration in accounting units. Exact."""
        return price_ticks * self.tick_units * volume


def cash_to_wire(cash_units: int) -> float:
    """Convert accounting units to the decimal figure a participant sees.

    One way only. Cash never returns from the wire: the server is the sole
    source of truth for cash and positions, and client state never feeds
    validation (design.md 5.7). So this conversion has no round-trip
    obligation, unlike prices, which a strategy really does read off the
    book and send straight back.

    The trade tape does not use this. It writes exact decimal strings, so
    the scoring figure is reproducible byte for byte (operations.md 2).
    """
    return cash_units / TICK_SCALE


def cash_units_from_decimal(cash: str | Decimal | int) -> int:
    """Convert an exact decimal cash figure to accounting units.

    For config load (``starting_cash``) and for reading a trade tape back.
    Not for the order path: no cash figure arrives from a client.

    Raises:
        ValueError: If finer than 1/10000 and would therefore lose value.
    """
    if isinstance(cash, float):
        raise ValueError(
            "cash must be given as a string or Decimal, not a float (design.md 3.2)"
        )
    scaled = Decimal(cash) * TICK_SCALE
    if scaled != scaled.to_integral_value():
        raise ValueError(f"cash {cash} is finer than 1/{TICK_SCALE} and would round")
    return int(scaled)
