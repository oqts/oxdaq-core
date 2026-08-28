"""The integer/decimal boundary. Spec 3.

The milestone 1 definition of done requires the conversion to round-trip
exactly over a property-based test, so that is what most of this file is.
"""

import math
from decimal import Decimal

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from oxdaq.units import (
    MAX_PRICE_TICKS,
    TICK_SCALE,
    TickScale,
    TickSizeError,
    cash_to_wire,
    cash_units_from_decimal,
)

# Every tick size a Phase 1 config could plausibly use, plus awkward ones.
# 0.07 is here on purpose: it is legal and the naive float check rejects it.
TICK_SIZES = [
    "0.0001",
    "0.0002",
    "0.0003",
    "0.001",
    "0.0025",
    "0.01",
    "0.05",
    "0.07",
    "0.1",
    "0.25",
    "0.29",
    "0.5",
    "1.0",
    "2.5",
    "100.0",
    "1000.0",
]

tick_scales = st.sampled_from([TickScale.from_config(t) for t in TICK_SIZES])
price_ticks = st.integers(min_value=1, max_value=MAX_PRICE_TICKS)


# --- the round trip, which is the milestone 1 requirement ------------------


@given(scale=tick_scales, ticks=price_ticks)
def test_price_round_trips_exactly(scale: TickScale, ticks: int) -> None:
    """int ticks -> wire -> int ticks is the identity, over the stated domain.

    This is the property that lets a strategy read the best bid off the
    wire and submit a join order at exactly that price. If it failed, a
    market maker would sit one tick behind the book and never know why.
    """
    assert scale.from_wire(scale.to_wire(ticks)) == ticks


@given(scale=tick_scales, ticks=price_ticks)
def test_to_wire_is_the_nearest_float_to_the_exact_decimal(
    scale: TickScale, ticks: int
) -> None:
    """No compounded rounding.

    ``price_ticks * float(tick_size)`` rounds twice and produces figures a
    participant can see, for example 86.38000000000001 at a 0.07 tick.
    The integer-multiply-then-divide form must land on the float nearest
    the true decimal value.
    """
    exact = Decimal(ticks) * scale.tick_size
    assert scale.to_wire(ticks) == float(exact)


@given(scale=tick_scales, ticks=price_ticks, volume=st.integers(1, 1_000_000))
def test_notional_is_exact_integer_arithmetic(
    scale: TickScale, ticks: int, volume: int
) -> None:
    """Notional must equal the exact decimal, scaled. Spec 3.2.

    This is the figure the leaderboard is decided by, so it is not allowed
    to be approximately right.
    """
    exact = Decimal(ticks) * scale.tick_size * volume * TICK_SCALE
    assert scale.notional(ticks, volume) == int(exact)
    assert scale.notional(ticks, volume) == scale.price_units(ticks) * volume


# --- normalisation ---------------------------------------------------------


@given(scale=tick_scales, ticks=st.integers(1, 10**9))
def test_from_wire_snaps_to_the_nearest_tick(scale: TickScale, ticks: int) -> None:
    """A price a third of a tick above a tick rounds back down to it."""
    third = float(scale.tick_size) / 3.0
    assume(third > 0.0)
    assert scale.from_wire(scale.to_wire(ticks) + third) == ticks


@pytest.mark.parametrize(
    ("tick_size", "price", "expected"),
    [
        ("0.01", 99.505, 9951),  # exact half rounds up, not to even
        ("0.01", 99.515, 9952),  # ... and up again, where banker's would go down
        ("0.01", 99.5049, 9950),
        ("0.01", 99.5051, 9951),
        ("0.5", 0.25, 1),  # half a tick from zero rounds up
        ("1.0", 0.5, 1),
    ],
)
def test_from_wire_rounds_half_up_not_to_even(
    tick_size: str, price: float, expected: int
) -> None:
    """Round half up, deliberately, not Python's banker's rounding.

    ``round(0.5) == 0`` and ``round(1.5) == 2`` is not a rule worth
    explaining in participant documentation. Round half up is one
    sentence, so the codec must not be quietly using ``round``.
    """
    assert TickScale.from_config(tick_size).from_wire(price) == expected


def test_builtin_round_would_have_disagreed() -> None:
    """Guards the choice above by demonstrating the difference is real."""
    scale = TickScale.from_config("1.0")
    assert scale.from_wire(0.5) == 1
    assert round(0.5) == 0


# --- tick size validation. Spec 3.2 ---------------------------------------


@pytest.mark.parametrize("tick_size", TICK_SIZES)
def test_legal_tick_sizes_are_accepted(tick_size: str) -> None:
    scale = TickScale.from_config(tick_size)
    assert scale.tick_units == int(Decimal(tick_size) * TICK_SCALE)


@pytest.mark.parametrize("tick_size", ["0.00005", "0.000123", "0.0000001"])
def test_tick_sizes_finer_than_one_ten_thousandth_are_rejected(tick_size: str) -> None:
    with pytest.raises(TickSizeError, match="exact multiple"):
        TickScale.from_config(tick_size)


@pytest.mark.parametrize("tick_size", ["0", "-0.01", "-1"])
def test_non_positive_tick_sizes_are_rejected(tick_size: str) -> None:
    with pytest.raises(TickSizeError, match="positive"):
        TickScale.from_config(tick_size)


def test_float_tick_size_is_refused_outright() -> None:
    """A float config value cannot be checked reliably, so it is refused.

    ``0.07 * 10_000`` is ``700.0000000000001`` in binary float, so the
    naive multiple-of-1/10000 check rejects a legal tick. Config must
    arrive as a string or a Decimal.
    """
    with pytest.raises(TickSizeError, match="not a float"):
        TickScale.from_config(0.01)


def test_the_float_check_this_guards_against_really_is_broken() -> None:
    """Demonstrates why the refusal above exists, rather than asserting it."""
    naive = 0.07 * TICK_SCALE
    assert naive != int(naive)
    assert Decimal("0.07") * TICK_SCALE == 700


# --- cash. Spec 3.2, 5.7 ---------------------------------------------------


@given(units=st.integers(-(10**15), 10**15))
def test_cash_to_wire_matches_the_exact_decimal(units: int) -> None:
    assert cash_to_wire(units) == float(Decimal(units) / TICK_SCALE)


@given(units=st.integers(-(10**15), 10**15))
def test_cash_survives_a_decimal_round_trip(units: int) -> None:
    """Cash never returns from the wire (spec 5.7), so this is the path
    that matters: config load and reading a trade tape back."""
    exact = Decimal(units) / TICK_SCALE
    assert cash_units_from_decimal(exact) == units


def test_cash_finer_than_an_accounting_unit_is_rejected() -> None:
    with pytest.raises(ValueError, match="finer than"):
        cash_units_from_decimal(Decimal("1.000005"))


def test_float_cash_is_refused() -> None:
    with pytest.raises(ValueError, match="not a float"):
        cash_units_from_decimal(1.5)


# --- the stated domain -----------------------------------------------------


def test_the_round_trip_is_documented_as_bounded_and_the_bound_is_real() -> None:
    """MAX_PRICE_TICKS is measured, not assumed.

    The bound exists because float64 relative error eventually exceeds the
    half tick of slack round-half-up allows. This pins that the constant
    sits below where failures actually begin, so the property test above
    is asserting over a domain it can support.
    """
    scale = TickScale.from_config("0.001")
    assert scale.from_wire(scale.to_wire(MAX_PRICE_TICKS)) == MAX_PRICE_TICKS

    failures = sum(
        scale.from_wire(scale.to_wire(t)) != t for t in range(2**51, 2**51 + 20000)
    )
    assert failures > 0, (
        "no failures found above the documented bound: either float behaviour "
        "changed or MAX_PRICE_TICKS is now needlessly conservative"
    )


def test_price_units_and_cash_units_are_the_same_unit() -> None:
    """A notional and a cash balance must be directly comparable integers.

    Spec 5.5 checks ``notional <= cash - reserved_cash``. That comparison
    is only meaningful if both sides count the same thing.
    """
    scale = TickScale.from_config("0.01")
    assert scale.notional(9950, 10) == cash_units_from_decimal(Decimal("995.00"))
    assert math.isclose(cash_to_wire(scale.notional(9950, 10)), 995.0)
