"""Operation streams: run them, check every step, compare engines.

Used by the Hypothesis tests (``test_streams.py``) and the replay tool
(``replay.py``). A stream is a list of :class:`Submit` and :class:`Cancel`,
stored as JSON lines, one op per line::

    {"op": "submit", "id": 1, "team": 1, "instrument": 0, "side": "bid",
     "type": "limit", "price": 100, "volume": 5}
    {"op": "cancel", "id": 1}

``run`` checks design 4.1 to 4.5 after **every** op on every engine, using
only that engine's snapshot before the op, so it is a statement of what
a correct step looks like rather than a second matching engine. With two
or more engines it also requires them to agree exactly at every step
(the differential test, design 4.5 gate condition 2).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.engine.driver import B, Driver, F, R


@dataclass(frozen=True)
class Submit:
    id: int
    team: int
    instrument: int
    side: str  # "bid" | "ask"
    type: str  # "limit" | "ioc"
    price: int
    volume: int


@dataclass(frozen=True)
class Cancel:
    id: int


Op = Submit | Cancel


class StreamError(AssertionError):
    """A step that broke the spec, or two engines that disagreed.

    ``kind`` is a short stable label (``fill-price``, ``divergence``, ...)
    so the shrinker keeps the same failure while it removes ops.
    """

    def __init__(self, kind: str, step: int, op: Op | None, message: str) -> None:
        self.kind, self.step, self.op = kind, step, op
        where = f"step {step}: {to_json(op)}" if op is not None else "end of stream"
        super().__init__(f"[{kind}] {where}\n{message}")


# --- serialisation --------------------------------------------------------


def to_json(op: Op) -> str:
    kind = "submit" if isinstance(op, Submit) else "cancel"
    return json.dumps({"op": kind, **asdict(op)})


def from_json(line: str) -> Op:
    raw = json.loads(line)
    kind = raw.pop("op")
    return Submit(**raw) if kind == "submit" else Cancel(**raw)


def dump(ops: Iterable[Op], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(to_json(op) + "\n" for op in ops))


def load(path: Path) -> list[Op]:
    return [
        from_json(line)
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


# --- running --------------------------------------------------------------


def run(ops: Sequence[Op], engines: Sequence[str]) -> None:
    """Run ``ops`` through fresh engines, checking every step.

    Raises:
        StreamError: on the first step that breaks the spec on any engine,
            or where the engines' results or books differ.
    """
    __tracebackhide__ = True  # the failure message says it all
    drivers = [Driver(name) for name in engines]
    instruments = sorted({op.instrument for op in ops if isinstance(op, Submit)})
    for step, op in enumerate(ops):
        outcomes = []
        for d in drivers:
            before = {i: d.book(i) for i in instruments}
            try:
                result = (
                    d.submit(
                        op.id,
                        op.side,
                        op.price,
                        op.volume,
                        order_type=op.type,
                        team=op.team,
                        instrument=op.instrument,
                    )
                    if isinstance(op, Submit)
                    else d.cancel(op.id)
                )
            except Exception as exc:
                raise StreamError(
                    f"exception:{type(exc).__name__}", step, op, f"{d}: {exc!r}"
                ) from exc
            after = {i: d.book(i) for i in instruments}
            try:
                check_step(op, result, before, after, d.seq_of.get(op.id))
            except AssertionError as exc:
                kind, _, message = str(exc).partition(": ")
                raise StreamError(
                    kind, step, op, f"{d}: {message}\n{_books(before, after)}"
                ) from None
            outcomes.append((d, result, after))
        _same(step, op, outcomes)


def _same(step: int, op: Op, outcomes) -> None:
    __tracebackhide__ = True
    first, result0, books0 = outcomes[0]
    for d, result, books in outcomes[1:]:
        if result != result0:
            raise StreamError(
                "divergence", step, op, f"{first}: {result0!r}\n{d}: {result!r}"
            )
        if books != books0:
            raise StreamError(
                "divergence", step, op, f"{first}: {books0!r}\n{d}: {books!r}"
            )


def _books(before: dict[int, B], after: dict[int, B]) -> str:
    return "\n".join(
        f"  instrument {i}\n    before {before[i]}\n    after  {after[i]}"
        for i in before
        if before[i] != after[i]
    )


# --- the checks -----------------------------------------------------------
# Each failed check raises AssertionError("<kind>: <message>").


def _fail(kind: str, message: str) -> None:
    raise AssertionError(f"{kind}: {message}")


def _key_bid(r: R) -> tuple[int, int]:
    return (-r.price, r.seq)


def _key_ask(r: R) -> tuple[int, int]:
    return (r.price, r.seq)


def check_book(book: B) -> None:
    """design 4.1 and 4.2: sorted best first, nothing empty, never crossed."""
    for side, key in ((book.bids, _key_bid), (book.asks, _key_ask)):
        keys = [key(r) for r in side]
        if keys != sorted(keys) or len(set(keys)) != len(keys):
            _fail("priority", f"side not in strict price-time order: {side}")
        if any(r.remaining <= 0 for r in side):
            _fail("empty-resting", f"a resting order has no volume: {side}")
    if book.bids and book.asks and book.bids[0].price >= book.asks[0].price:
        _fail("crossed", f"best bid {book.bids[0]} >= best ask {book.asks[0]}")


def check_step(
    op: Op, result, before: dict[int, B], after: dict[int, B], seq: int | None
) -> None:
    for book in after.values():
        check_book(book)
    ids = [r.order_id for b in after.values() for r in (*b.bids, *b.asks)]
    if len(ids) != len(set(ids)):
        _fail("duplicate-id", f"an order id rests twice: {sorted(ids)}")
    if isinstance(op, Submit):
        _check_submit(op, result, before, after, seq)
    else:
        _check_cancel(op, result, before, after)


def _check_submit(op: Submit, fills: list[F], before, after, seq) -> None:
    i = op.instrument
    pre, post = before[i], after[i]
    pre_same, pre_opp = (
        (pre.bids, pre.asks) if op.side == "bid" else (pre.asks, pre.bids)
    )
    post_same, post_opp = (
        (post.bids, post.asks) if op.side == "bid" else (post.asks, post.bids)
    )
    key = _key_bid if op.side == "bid" else _key_ask

    for f in fills:
        if f.taker != op.id or f.instrument != i or f.volume <= 0:
            _fail("fill-fields", f"fill {f} for order {op.id} on instrument {i}")

    # Makers are consumed strictly in priority order, each at most once.
    makers = [f.maker for f in fills]
    if makers != [r.order_id for r in pre_opp[: len(makers)]]:
        _fail(
            "time-priority",
            f"makers {makers}, but the opposite side in priority order was "
            f"{[r.order_id for r in pre_opp]}",
        )
    for k, (f, maker) in enumerate(zip(fills, pre_opp, strict=False)):
        if f.price != maker.price:
            _fail("fill-price", f"{f} is not at the resting price {maker.price}")
        crosses = (
            op.price >= maker.price if op.side == "bid" else op.price <= maker.price
        )
        if not crosses:
            _fail("no-cross", f"{op.side} at {op.price} filled against {maker}")
        last = k == len(fills) - 1
        if f.volume > maker.remaining or (not last and f.volume != maker.remaining):
            _fail("fill-volume", f"{f} against {maker}: only the last may be partial")

    filled = sum(f.volume for f in fills)
    if filled > op.volume:
        _fail("overfill", f"filled {filled} of {op.volume}")
    remainder = op.volume - filled

    # The opposite side lost exactly what was filled, and nothing else.
    expected_opp = list(pre_opp[len(fills) :])
    if fills and fills[-1].volume < pre_opp[len(fills) - 1].remaining:
        m = pre_opp[len(fills) - 1]
        expected_opp.insert(0, m._replace(remaining=m.remaining - fills[-1].volume))
    if list(post_opp) != expected_opp:
        _fail("opposite-side", f"expected {tuple(expected_opp)}, got {post_opp}")

    # Matching stopped only when filled or when nothing crossed any more.
    if remainder and post_opp:
        best = post_opp[0].price
        if (op.side == "bid" and op.price >= best) or (
            op.side == "ask" and op.price <= best
        ):
            _fail("stopped-early", f"{remainder} left but {post_opp[0]} still crosses")

    # A limit remainder rests in priority order; an IOC remainder never does.
    expected_same = list(pre_same)
    if remainder and op.type == "limit":
        expected_same = sorted(
            [*expected_same, R(op.id, op.team, op.price, remainder, seq)], key=key
        )
    if list(post_same) != expected_same:
        _fail("own-side", f"expected {tuple(expected_same)}, got {post_same}")

    for j in before:
        if j != i and before[j] != after[j]:
            _fail("other-instrument", f"instrument {j} changed on an order for {i}")


def _check_cancel(op: Cancel, result, before, after) -> None:
    resting = {
        r.order_id: (i, r) for i, b in before.items() for r in (*b.bids, *b.asks)
    }
    if op.id not in resting:
        if result is not None:
            _fail("cancel-result", f"cancel of non-resting {op.id} returned {result!r}")
        if after != before:
            _fail("cancel-book", "cancel of a non-resting id changed a book")
        return
    i, r = resting[op.id]
    if result != r.remaining:
        _fail("cancel-result", f"cancel of {r} returned {result!r}, not {r.remaining}")
    expected = B(
        tuple(x for x in before[i].bids if x.order_id != op.id),
        tuple(x for x in before[i].asks if x.order_id != op.id),
    )
    if after[i] != expected:
        _fail("cancel-book", f"expected {expected}, got {after[i]}")
    for j in before:
        if j != i and before[j] != after[j]:
            _fail("other-instrument", f"instrument {j} changed on a cancel in {i}")
