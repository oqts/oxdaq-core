# oxdaq-core: agent guidance

Read `../.github/CLAUDE.md` first (org rules, ownership boundary, house
rules). Human overview is `README.md`.

## The spec

`docs/` is the contract (spec 3.0). Start at `docs/README.md`.
References look like `design 2.4`: file, then section. Do not deviate
from the spec without changing it in the same PR; a new design decision
also gets a row in `docs/decisions.md`. Flag contradictions, never
resolve them silently.

## Layout

```
packages/oqts-client/src/oqts/   published to PyPI as oqts-client, imported as `oqts`
    protocol/                    enums, messages, codec   <- SHARED, frozen
packages/oxdaq/src/oxdaq/        the server, never published
    units.py                     TICK_SCALE, to_wire/from_wire <- SERVER ONLY
packages/oxdaq-engine/           C++ engine (cpp/, Alec's) + CMake, presets; nanobind module in R8
    tests/cpp/                   GoogleTest, picked up with no CMake edit
tests/protocol/                  suites, samples.py
tests/golden/                    one frozen JSON frame per message type
tests/engine/                    the shared engine suite (design 4.5), both engines
    driver.py                    drives any engine through plain ints and tuples
    streams.py                   op streams, per-step spec checks, the differential
    replay.py                    replay or shrink a failing stream
docs/                            the spec
```

- Message shapes are shared (server, client, bots, dashboards all need
  them); integer conversion is server-only (the client is float-native).
- The server depends on the client, not the reverse.
- Everything a participant needs is importable from `oqts` directly.

## The protocol is frozen

`tests/golden/` pins every message byte for byte; `test_codec.py` walks
every outbound model to prove no field can carry a fair value. **A golden
failure is the freeze working.** Never regenerate to make it pass. A
protocol change is all of: bump `PROTOCOL_VERSION`, edit
`docs/protocol.md` in the same PR, update `tests/protocol/samples.py`,
run `uv run python tests/protocol/regenerate_golden.py`.

The schema is at **protocol v2** (D28 to D32, 2026-11-19), and the freeze
now applies to v2.

Ruff does not touch Markdown (it would reformat code blocks in docs).

## Commands

```bash
uv sync                  # also builds packages/oxdaq-engine via scikit-build-core
uv run pytest            # uv run pytest -k book for one area
uv run pytest tests/engine -q                  # where the engine stands
uv run python -m tests.engine.replay F.jsonl --shrink   # minimise a failing stream
uv run ruff check .
uv run ruff format .
cd packages/oxdaq-engine && cmake --workflow --preset dev   # also asan, release
```

Never `pip install` into the venv; never hand-edit `uv.lock`. A new
dependency is a design decision: propose it first. C++ toolchain: build
2.2.

The engine suite fails with one line (`test_engine_exists.py`) and skips
the rest until `oxdaq.engine` exports the design 4.5 names; the cpp runs
skip until R8. CI keeps `tests/engine` non-blocking until milestone 2 is
done: remove its `continue-on-error` then.

## Ownership

Alec writes by hand. Do not write these, and do not sketch them inline
"to illustrate":

- The order book and matching (design 4), Python **and** C++: every line
  under `packages/oxdaq-engine/cpp/`, and the nanobind binding code.
- Accounting and validation (design 5).
- The price process and its maths (design 6).
- Bot strategy logic (design 7.2).
- Every async surface: gateway, order loop, broadcast, disconnect sweep,
  rate limiter, `oqts.aio` and the `Exchange` thread bridge (design 2.3,
  2.4, 5.5; client 3).

Claude writes: packaging, CI, tool config, CMake and presets, the schema
and codec, the shared engine suite and differential test, fuzz and
benchmark harnesses, fixtures, the bot runner, token issuance and auth,
the trade tape writer, dashboards, deployment.

For Alec's parts: give signatures, invariants, failure modes and links to
the exact docs (asyncio, `sortedcontainers`, numpy RNG, C++ and nanobind
features), then offer the test that proves it.

## Invariants

The canonical list is design 8. Breaking one is a correctness bug:

1. One queue, one consumer.
2. Check and reserve atomic: no `await` between them.
3. Priority is the server's arrival sequence; client time affects nothing.
4. Integers inside, decimals only in the codec; no epsilon anywhere.
5. Fill at the resting order's price.
6. Position bounds bind both sides and are invariant under fills.
7. Fair value never crosses the network, admin messages included.
8. Bots are indistinguishable from participants.
9. The server is the source of truth for cash and positions.
10. Rejected orders never reach the engine.
11. The two engines give exactly equal fills and books; engine calls hold
    the GIL and never block.
12. Orders belong to their connection; the disconnect sweep goes through
    the queue and touches only that connection's orders.
13. `trade_tick` is never coalesced or dropped.
14. Seeds are secret until the session ends: server-generated from a
    secure source, never derived, admin-supplied or reused (design 6.7).
15. In memory only; the trade tape is the only persistence.

## Build order

Build 4. Milestone 1 is done at v2; milestone 2 (the Python reference
engine) is current. The engine track (E1, E2)
depends on milestone 2 only. Do not start a milestone before the
previous one is done. Never run a live round with untuned bots (design
7.3).

## Open

- Dashboard stack: decide before milestone 9 (build 2.3).
- Practice exchange parameters are provisional (operations 5.2); confirm
  before milestone 11.
- The bot runner interface with `oxdaq-ops` is not designed; agree it
  before either side is written.
- D38 left items to specify before they are built (design 1.2): linked
  instruments, news calendar format, bot parameter distributions, a risk
  penalty, live leaderboard marking.
- A dashboard subsection of `brand.md` is planned; until then follow
  `brand.md` as written.

## A build session

The build half of the `cpp-oxdaq` learning goal, run like a learning
session (`~/files/Learning/CLAUDE.md`, "A session"). Alec opens this repo
and says "session". Then:

1. **Find the block.** kairos `list_events` for today, Projects key: the
   block now or next titled `☐ Build: ...`. Its task (`list_tasks`, same
   title) has notes starting "Learning goal cpp-oxdaq ..., topic N" saying
   why it is there. A concept topic (no `Build:`) belongs in
   `~/files/Learning`: say so. If no block is running, offer the next.
2. **Five minutes of recall first:** two or three quick questions on the
   last session, read from `~/files/Learning/cpp-oxdaq/log.md`.
3. **State the target:** which tests must go green, from the table below
   (ROUNDS.md "Done when", build 4), and run them once so he sees where
   he starts.
4. **He writes, Claude reviews.** Never write or sketch his code
   (Ownership), even when he is stuck. Point at the failing test and what
   it asserts, the spec section and the exact docs; ask the question that
   leads to the bug. Review what he writes against design 8 and the spec.
   Explain only what he cannot get to, briefly; anything longer goes to
   the tablet as LaTeX (`to_remarkable`).
5. **Close.** Run the target and say what is green. Append three lines to
   `~/files/Learning/cpp-oxdaq/log.md`: the date, the block, what was hard
   (the next recall comes from it). Tell him to check the block in the
   calendar ("done", or "partly, N min left"). When a round or milestone
   completes, update `state.md` and the README build status.

| Build task (kairos) | Target | Command |
| --- | --- | --- |
| Order and OrderBook ... resting and price-time matching (R1) | `test_engine_exists`, `TestResting`, `TestMatching`. Every test reads books through `snapshot`, so it comes first | `uv run pytest tests/engine -k "exists or Resting or Matching"` |
| IOC, cancel and snapshot ... until the shared suite passes (R1) | All of `tests/engine` on `py`. R1 is done when it passes **and** he can explain the bid key and time priority | `uv run pytest tests/engine -q` |
| Ticks, Volume, Side and reject codes (R2) | GoogleTest green under `dev` and `asan`, no `-Wconversion` warnings. The tests are written once he has fixed the types' signatures | `cd packages/oxdaq-engine && cmake --workflow --preset dev && cmake --workflow --preset asan` |
| Later rounds | ROUNDS.md "Done when" and build 4 | |
