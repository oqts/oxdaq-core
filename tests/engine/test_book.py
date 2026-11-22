"""The shared OrderBook correctness suite. design 4.1 to 4.5, build 4 (M2).

Every test runs once per engine (``conftest.py``). The classes are a
ladder, in the order the engine is easiest to build, so a session's
target is one class going green (``uv run pytest tests/engine -k Resting``):

1. ``TestResting``     orders rest, sorted best first, priority by arrival
2. ``TestMatching``    limit orders cross, partial fills, price improvement
3. ``TestIOC``         the remainder never rests
4. ``TestCancel``      remove by id; ``None`` when not resting
5. ``TestInstruments`` books are independent
6. ``TestBadInput``    ``ValueError``, book unchanged
7. ``test_streams.py`` every invariant on random streams, and the engines
   compared (the differential test)

Prices are integer ticks and ids are integers (design 3, 4.2). ``F`` is a
fill ``(maker, taker, instrument, price, volume)``; ``R`` a resting order
``(order_id, team, price, remaining, arrival_seq)``.
"""

import pytest

from tests.engine.driver import B, Driver, F, R


def ids(side) -> list[int]:
    return [r.order_id for r in side]


class TestResting:
    def test_an_empty_book_has_no_orders(self, engine: Driver) -> None:
        assert engine.book() == B((), ())

    def test_a_book_never_traded_is_empty(self, engine: Driver) -> None:
        """design 4.5: a book exists from its first order."""
        assert engine.book(instrument=7) == B((), ())

    def test_a_bid_that_does_not_cross_rests(self, engine: Driver) -> None:
        assert engine.submit(1, "bid", 100, 5, team=3) == []
        assert engine.book() == B((R(1, 3, 100, 5, engine.arrival_seq_of[1]),), ())

    def test_an_ask_that_does_not_cross_rests(self, engine: Driver) -> None:
        assert engine.submit(1, "ask", 101, 5, team=4) == []
        assert engine.book() == B((), (R(1, 4, 101, 5, engine.arrival_seq_of[1]),))

    def test_bids_are_highest_price_first(self, engine: Driver) -> None:
        for oid, price in [(1, 99), (2, 101), (3, 100)]:
            engine.submit(oid, "bid", price, 1)
        assert [r.price for r in engine.book().bids] == [101, 100, 99]

    def test_asks_are_lowest_price_first(self, engine: Driver) -> None:
        for oid, price in [(1, 103), (2, 101), (3, 102)]:
            engine.submit(oid, "ask", price, 1)
        assert [r.price for r in engine.book().asks] == [101, 102, 103]

    def test_at_one_price_earlier_arrival_comes_first(self, engine: Driver) -> None:
        """Time priority is the arrival sequence (design 2.3, D25)."""
        for oid in (5, 2, 9):
            engine.submit(oid, "bid", 100, 1)
        for oid in (8, 1, 4):
            engine.submit(oid, "ask", 101, 1)
        book = engine.book()
        assert ids(book.bids) == [5, 2, 9]
        assert ids(book.asks) == [8, 1, 4]

    def test_the_snapshot_carries_each_orders_arrival_sequence(
        self, engine: Driver
    ) -> None:
        engine.submit(1, "bid", 100, 1)
        engine.submit(2, "bid", 100, 1)
        assert [r.arrival_seq for r in engine.book().bids] == [
            engine.arrival_seq_of[1],
            engine.arrival_seq_of[2],
        ]

    def test_resting_volume_is_not_aggregated(self, engine: Driver) -> None:
        """The snapshot lists orders, not levels (design 4.5)."""
        engine.submit(1, "bid", 100, 3)
        engine.submit(2, "bid", 100, 4)
        assert [(r.price, r.remaining) for r in engine.book().bids] == [
            (100, 3),
            (100, 4),
        ]

    def test_a_snapshot_is_a_value(self, engine: Driver) -> None:
        """Later activity must not change a snapshot already taken (design 4.5)."""
        engine.submit(1, "bid", 100, 5)
        raw = engine.engine.snapshot(0)
        taken = engine.book()
        engine.submit(2, "ask", 100, 2)
        engine.submit(3, "bid", 101, 1)
        assert (
            B(
                tuple(
                    R(
                        o.order_id,
                        o.team_id,
                        o.price_ticks,
                        o.remaining_volume,
                        o.arrival_seq,
                    )
                    for o in raw.bids
                ),
                tuple(
                    R(
                        o.order_id,
                        o.team_id,
                        o.price_ticks,
                        o.remaining_volume,
                        o.arrival_seq,
                    )
                    for o in raw.asks
                ),
            )
            == taken
        )


class TestMatching:
    def test_a_crossing_bid_fills_against_the_resting_ask(self, engine: Driver) -> None:
        engine.submit(1, "ask", 100, 5)
        assert engine.submit(2, "bid", 100, 5) == [F(1, 2, 0, 100, 5)]
        assert engine.book() == B((), ())

    def test_a_crossing_ask_fills_against_the_resting_bid(self, engine: Driver) -> None:
        engine.submit(1, "bid", 100, 5)
        assert engine.submit(2, "ask", 100, 5) == [F(1, 2, 0, 100, 5)]
        assert engine.book() == B((), ())

    def test_a_buyer_above_the_ask_pays_the_ask(self, engine: Driver) -> None:
        """design 4.3: the resting price, so the aggressor gets the improvement."""
        engine.submit(1, "ask", 100, 5)
        assert engine.submit(2, "bid", 105, 5) == [F(1, 2, 0, 100, 5)]

    def test_a_seller_below_the_bid_receives_the_bid(self, engine: Driver) -> None:
        engine.submit(1, "bid", 100, 5)
        assert engine.submit(2, "ask", 95, 5) == [F(1, 2, 0, 100, 5)]

    def test_orders_that_do_not_cross_both_rest(self, engine: Driver) -> None:
        engine.submit(1, "bid", 99, 5)
        assert engine.submit(2, "ask", 100, 5) == []
        assert (ids(engine.book().bids), ids(engine.book().asks)) == ([1], [2])

    def test_a_large_aggressor_leaves_its_remainder_resting(
        self, engine: Driver
    ) -> None:
        engine.submit(1, "ask", 100, 3)
        assert engine.submit(2, "bid", 101, 10) == [F(1, 2, 0, 100, 3)]
        assert engine.book() == B((R(2, 1, 101, 7, engine.arrival_seq_of[2]),), ())

    def test_a_partly_filled_maker_keeps_its_place(self, engine: Driver) -> None:
        engine.submit(1, "ask", 100, 10)
        engine.submit(2, "ask", 100, 10)
        assert engine.submit(3, "bid", 100, 4) == [F(1, 3, 0, 100, 4)]
        asks = engine.book().asks
        assert [(r.order_id, r.remaining) for r in asks] == [(1, 6), (2, 10)]
        assert asks[0].arrival_seq == engine.arrival_seq_of[1]

    def test_makers_at_one_price_fill_in_arrival_order(self, engine: Driver) -> None:
        engine.submit(1, "ask", 100, 2)
        engine.submit(2, "ask", 100, 2)
        engine.submit(3, "ask", 100, 2)
        assert engine.submit(4, "bid", 100, 5) == [
            F(1, 4, 0, 100, 2),
            F(2, 4, 0, 100, 2),
            F(3, 4, 0, 100, 1),
        ]
        assert [(r.order_id, r.remaining) for r in engine.book().asks] == [(3, 1)]

    def test_an_aggressor_sweeps_levels_best_first(self, engine: Driver) -> None:
        engine.submit(1, "ask", 102, 2)
        engine.submit(2, "ask", 100, 2)
        engine.submit(3, "ask", 101, 2)
        assert engine.submit(4, "bid", 102, 5) == [
            F(2, 4, 0, 100, 2),
            F(3, 4, 0, 101, 2),
            F(1, 4, 0, 102, 1),
        ]

    def test_a_sweep_stops_at_the_aggressors_limit(self, engine: Driver) -> None:
        engine.submit(1, "bid", 100, 2)
        engine.submit(2, "bid", 99, 2)
        engine.submit(3, "bid", 98, 2)
        assert engine.submit(4, "ask", 99, 10) == [
            F(1, 4, 0, 100, 2),
            F(2, 4, 0, 99, 2),
        ]
        book = engine.book()
        assert ids(book.bids) == [3]
        assert book.asks == (R(4, 1, 99, 6, engine.arrival_seq_of[4]),)

    def test_each_fill_is_at_its_own_makers_price(self, engine: Driver) -> None:
        engine.submit(1, "bid", 103, 1)
        engine.submit(2, "bid", 101, 1)
        fills = engine.submit(3, "ask", 100, 2)
        assert [f.price for f in fills] == [103, 101]

    def test_fills_name_the_teams_orders_not_the_teams(self, engine: Driver) -> None:
        """Fills carry order ids; the session manager maps them to teams."""
        engine.submit(10, "ask", 100, 1, team=7)
        assert engine.submit(11, "bid", 100, 1, team=8) == [F(10, 11, 0, 100, 1)]

    def test_a_team_can_trade_against_itself(self, engine: Driver) -> None:
        """The spec has no self-trade prevention, so none is applied."""
        engine.submit(1, "ask", 100, 1, team=5)
        assert engine.submit(2, "bid", 100, 1, team=5) == [F(1, 2, 0, 100, 1)]

    def test_a_fully_filled_maker_leaves_the_book(self, engine: Driver) -> None:
        engine.submit(1, "bid", 100, 5)
        engine.submit(2, "ask", 100, 5)
        assert engine.book() == B((), ())
        assert engine.cancel(1) is None


class TestIOC:
    def test_an_ioc_that_does_not_cross_never_rests(self, engine: Driver) -> None:
        engine.submit(1, "ask", 101, 5)
        assert engine.submit(2, "bid", 100, 5, order_type="ioc") == []
        assert ids(engine.book().bids) == []

    def test_an_ioc_into_an_empty_book_does_nothing(self, engine: Driver) -> None:
        assert engine.submit(1, "ask", 100, 5, order_type="ioc") == []
        assert engine.book() == B((), ())

    def test_an_ioc_fills_like_a_limit_order(self, engine: Driver) -> None:
        engine.submit(1, "ask", 100, 5)
        assert engine.submit(2, "bid", 102, 5, order_type="ioc") == [F(1, 2, 0, 100, 5)]
        assert engine.book() == B((), ())

    def test_an_ioc_remainder_is_cancelled(self, engine: Driver) -> None:
        engine.submit(1, "ask", 100, 3)
        engine.submit(2, "ask", 101, 3)
        assert engine.submit(3, "bid", 100, 10, order_type="ioc") == [
            F(1, 3, 0, 100, 3)
        ]
        assert engine.book() == B((), (R(2, 1, 101, 3, engine.arrival_seq_of[2]),))

    def test_an_ioc_sweeps_levels(self, engine: Driver) -> None:
        engine.submit(1, "bid", 101, 2)
        engine.submit(2, "bid", 100, 2)
        assert engine.submit(3, "ask", 100, 5, order_type="ioc") == [
            F(1, 3, 0, 101, 2),
            F(2, 3, 0, 100, 2),
        ]
        assert engine.book() == B((), ())

    def test_a_partly_filled_ioc_leaves_the_maker_remainder(
        self, engine: Driver
    ) -> None:
        engine.submit(1, "ask", 100, 10)
        assert engine.submit(2, "bid", 100, 4, order_type="ioc") == [F(1, 2, 0, 100, 4)]
        assert [(r.order_id, r.remaining) for r in engine.book().asks] == [(1, 6)]

    def test_an_ioc_cannot_be_cancelled_afterwards(self, engine: Driver) -> None:
        engine.submit(1, "ask", 100, 2)
        engine.submit(2, "bid", 100, 5, order_type="ioc")
        assert engine.cancel(2) is None


class TestCancel:
    def test_cancel_returns_the_remaining_volume(self, engine: Driver) -> None:
        engine.submit(1, "bid", 100, 5)
        assert engine.cancel(1) == 5
        assert engine.book() == B((), ())

    def test_cancel_after_a_partial_fill_returns_the_rest(self, engine: Driver) -> None:
        engine.submit(1, "ask", 100, 10)
        engine.submit(2, "bid", 100, 4)
        assert engine.cancel(1) == 6
        assert engine.book() == B((), ())

    def test_cancel_of_an_unknown_id_returns_none(self, engine: Driver) -> None:
        assert engine.cancel(42) is None

    def test_a_second_cancel_returns_none(self, engine: Driver) -> None:
        engine.submit(1, "bid", 100, 5)
        engine.cancel(1)
        assert engine.cancel(1) is None

    def test_cancel_leaves_the_other_orders_in_order(self, engine: Driver) -> None:
        for oid in (1, 2, 3, 4):
            engine.submit(oid, "ask", 100 + oid % 2, 1)
        engine.cancel(3)
        assert ids(engine.book().asks) == [2, 4, 1]

    def test_a_cancelled_order_cannot_fill(self, engine: Driver) -> None:
        engine.submit(1, "ask", 100, 5)
        engine.submit(2, "ask", 101, 5)
        engine.cancel(1)
        assert engine.submit(3, "bid", 101, 5) == [F(2, 3, 0, 101, 5)]

    def test_cancel_finds_an_order_on_any_instrument(self, engine: Driver) -> None:
        """One engine, one id index across books (design 4.5)."""
        engine.submit(1, "bid", 100, 5, instrument=0)
        engine.submit(2, "ask", 200, 7, instrument=3)
        assert engine.cancel(2) == 7
        assert engine.book(3) == B((), ())
        assert ids(engine.book(0).bids) == [1]

    def test_cancel_of_a_best_order_exposes_the_next(self, engine: Driver) -> None:
        engine.submit(1, "bid", 101, 1)
        engine.submit(2, "bid", 100, 1)
        engine.cancel(1)
        assert engine.submit(3, "ask", 100, 1) == [F(2, 3, 0, 100, 1)]


class TestInstruments:
    def test_orders_on_different_instruments_never_match(self, engine: Driver) -> None:
        engine.submit(1, "ask", 100, 5, instrument=0)
        assert engine.submit(2, "bid", 100, 5, instrument=1) == []
        assert ids(engine.book(0).asks) == [1]
        assert ids(engine.book(1).bids) == [2]

    def test_fills_carry_their_instrument(self, engine: Driver) -> None:
        engine.submit(1, "ask", 100, 5, instrument=2)
        assert engine.submit(2, "bid", 100, 5, instrument=2) == [F(1, 2, 2, 100, 5)]

    def test_priority_is_per_book(self, engine: Driver) -> None:
        engine.submit(1, "ask", 100, 1, instrument=0)
        engine.submit(2, "ask", 100, 1, instrument=1)
        engine.submit(3, "ask", 100, 1, instrument=1)
        assert engine.submit(4, "bid", 100, 2, instrument=1) == [
            F(2, 4, 1, 100, 1),
            F(3, 4, 1, 100, 1),
        ]
        assert ids(engine.book(0).asks) == [1]


class TestBadInput:
    """design 4.5: ValueError, and the book is unchanged."""

    @pytest.fixture
    def seeded(self, engine: Driver) -> Driver:
        engine.submit(1, "bid", 99, 5)
        engine.submit(2, "ask", 101, 5)
        return engine

    @pytest.mark.parametrize(
        ("side", "price", "volume"),
        [
            ("bid", 100, 0),
            ("ask", 100, -3),
            ("bid", 0, 5),
            ("ask", -1, 5),
        ],
    )
    def test_a_price_or_volume_below_one_is_refused(
        self, seeded: Driver, side: str, price: int, volume: int
    ) -> None:
        before = seeded.book()
        with pytest.raises(ValueError):
            seeded.submit(3, side, price, volume)
        assert seeded.book() == before

    @pytest.mark.parametrize("order_type", ["limit", "ioc"])
    def test_an_id_that_is_resting_is_refused(
        self, seeded: Driver, order_type: str
    ) -> None:
        """Even when the duplicate would cross and fill."""
        before = seeded.book()
        with pytest.raises(ValueError):
            seeded.submit(1, "ask", 99, 1, order_type=order_type)
        assert seeded.book() == before

    def test_the_engine_still_works_after_a_refusal(self, seeded: Driver) -> None:
        with pytest.raises(ValueError):
            seeded.submit(3, "bid", 101, 0)
        assert seeded.submit(4, "bid", 101, 2) == [F(2, 4, 0, 101, 2)]
