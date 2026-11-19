"""Replay an op stream through the engines, and shrink a failing one.

    uv run python -m tests.engine.replay STREAM.jsonl            # check it
    uv run python -m tests.engine.replay STREAM.jsonl --trace    # every step
    uv run python -m tests.engine.replay STREAM.jsonl --shrink   # minimise

A stream is JSON lines (``streams.py``). It may come from a failing
Hypothesis run (``.oxdaq/failures/``), the libFuzzer target (R7), or be
written by hand. Engines default to every one that exists; choose with
``--engine py --engine cpp``.

``--shrink`` removes ops while the stream still fails **the same way**
(same failure kind), by delta debugging (Zeller and Hildebrandt, 2002),
then writes the minimal stream beside the original as ``*.min.jsonl``.
Removing a submit leaves any cancel of its id as a cancel of an unknown
id, which is still a valid stream.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from tests.engine import streams
from tests.engine.driver import ENGINES, Driver, EngineMissingError, load
from tests.engine.streams import Op, StreamError, Submit


def failure_of(ops: Sequence[Op], engines: Sequence[str]) -> StreamError | None:
    try:
        streams.run(ops, engines)
    except StreamError as exc:
        return exc
    return None


def shrink(ops: list[Op], engines: Sequence[str], kind: str) -> list[Op]:
    """ddmin: the smallest subsequence found that still fails with ``kind``.

    1-minimal: removing any single op makes the failure go away or change.
    """

    def fails(candidate: list[Op]) -> bool:
        exc = failure_of(candidate, engines)
        return exc is not None and exc.kind == kind

    n = 2
    while len(ops) >= 2:
        size = len(ops) // n
        chunks = [ops[i : i + size] for i in range(0, len(ops), size)]
        reduced = False
        for i, chunk in enumerate(chunks):
            complement = [op for j, c in enumerate(chunks) if j != i for op in c]
            if fails(chunk):
                ops, n, reduced = chunk, 2, True
                break
            if fails(complement):
                ops, n, reduced = complement, max(n - 1, 2), True
                break
        if not reduced:
            if n >= len(ops):
                break
            n = min(n * 2, len(ops))
    return ops


def trace(ops: Sequence[Op], engine: str) -> None:
    """Print each op, its result and the book it touched, for one engine."""
    d = Driver(engine)
    for step, op in enumerate(ops):
        if isinstance(op, Submit):
            result = d.submit(
                op.id,
                op.side,
                op.price,
                op.volume,
                order_type=op.type,
                team=op.team,
                instrument=op.instrument,
            )
            book = d.book(op.instrument)
        else:
            result = d.cancel(op.id)
            book = None
        print(f"{step:>4}  {streams.to_json(op)}")
        print(f"      -> {result!r}")
        if book is not None:
            print(
                f"      bids {[(r.order_id, r.price, r.remaining) for r in book.bids]}"
            )
            print(
                f"      asks {[(r.order_id, r.price, r.remaining) for r in book.asks]}"
            )


def _available(requested: list[str] | None) -> list[str]:
    found = []
    for name in requested or list(ENGINES):
        try:
            load(name)
            found.append(name)
        except EngineMissingError as exc:
            if requested:
                sys.exit(str(exc))
    if not found:
        sys.exit("no engine to run: write oxdaq.engine first (design 4.5)")
    return found


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.engine.replay")
    parser.add_argument("stream", type=Path)
    parser.add_argument("--engine", action="append", choices=sorted(ENGINES))
    parser.add_argument("--shrink", action="store_true")
    parser.add_argument("--trace", action="store_true", help="print every step")
    parser.add_argument("--out", type=Path, help="where --shrink writes")
    args = parser.parse_args(argv)

    engines = _available(args.engine)
    ops = streams.load(args.stream)
    print(f"{len(ops)} ops through {', '.join(engines)}")
    if args.trace:
        trace(ops, engines[0])

    exc = failure_of(ops, engines)
    if exc is None:
        print("passes: every step keeps the spec, and the engines agree")
        return 0
    print(f"fails\n{exc}")
    if not args.shrink:
        return 1

    minimal = shrink(list(ops), engines, exc.kind)
    out = args.out or args.stream.with_suffix(".min.jsonl")
    streams.dump(minimal, out)
    print(f"\nshrunk {len(ops)} -> {len(minimal)} ops, written to {out}")
    for op in minimal:
        print(f"  {streams.to_json(op)}")
    print(f"\n{failure_of(minimal, engines)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
