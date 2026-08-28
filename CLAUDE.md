# oxdaq-core: agent guidance

Read `../.github/CLAUDE.md` first (org rules, ownership boundary, house
rules). This file adds what is specific to the OXDAQ engine. Human
overview is `README.md`.

## Authoritative spec

`../planning/OXDAQ-PLAN.md` **v2.0** is the contract. All section
numbers below are v2.0 numbering. It states: do not deviate from these
decisions without updating this document first. Treat that literally.

v1.0 section numbers appear in older documents and are **not** valid
here. `../planning/CLAUDE.md` records which documents still carry them.

Related: `../planning/ARCHITECTURE.md` (where OXDAQ sits in the estate),
`../oqts-design/brand.md` (all dashboard styling).

## Toolchain

uv for environments and locking, Python pinned to 3.13, pytest for the
correctness suites, ruff for lint and format. Production containers use
`python:3.13-slim` so local and server match.

```bash
uv sync                  # create/refresh .venv from uv.lock
uv run pytest            # full suite
uv run pytest -k book    # one area
uv run ruff check .      # lint
uv run ruff format .     # format
```

Never `pip install` into the venv directly and never edit `uv.lock` by
hand. Adding a dependency is a design decision: propose it first.

## Ownership in this repo

Alec hand-writes, in neovim. Do not write these, do not sketch them
inline "to illustrate":

- The order book and matching logic (spec 4).
- Cash and position accounting, and order validation (spec 5).
- The price process engine and its maths (spec 6).
- Bot strategy logic (spec 7.2). The bot runner harness is Claude's.
- Every async surface: the WebSocket gateway, the single-consumer order
  loop, broadcast dispatch, and the client library's connection and
  event dispatch (spec 2.3, 2.4, 8).

Claude writes: packaging, CI, ruff/pytest config, the message schema and
codec (spec 3, 9), test harnesses and fixtures, the trade tape writer
(spec 11), token issuance and auth (spec 12), both dashboards (spec 13),
and anything that ships to a browser or a server.

When Alec is about to write one of his: supply the type signatures, the
invariants, the failure modes, and links to the exact docs needed
(asyncio queue and task semantics, `sortedcontainers.SortedList` key
behaviour, numpy RNG usage, dataclass and typing constructs). Then offer
the test that proves it.

## Invariants that must never be broken

Violating any of these is a correctness bug, not a style question.

1. **One queue, one consumer.** All order processing serialises through a
   single asyncio queue with exactly one consumer coroutine. No locks, no
   concurrency inside the matching engine, no second consumer (spec 2.3).
2. **Check and reserve are atomic.** Any validation that reads mutable
   participant state must take its reservation in the same synchronous
   step, with **no `await` between them**. Otherwise two orders validate
   against the same cash before either is processed and both are
   accepted. This is the single easiest way to break the system (spec 2.4).
3. **Server time only.** Time priority comes from server enqueue order.
   Client timestamps are read for nothing that affects ordering (spec 2.3).
4. **Integers inside, decimals at the boundary.** Prices are integer
   ticks, cash is integer accounting units. Only the codec touches a
   float. No epsilon comparison exists anywhere in the engine (spec 3).
5. **Fill price is the resting order's price**, never the aggressor's
   (spec 4.3).
6. **Position limits bind on both sides** as worst-case projections. The
   bounded quantities are invariant under fills and move only on accept
   and cancel (spec 5.3).
7. **Fair value never crosses the network.** Latent fair values reach bots
   through in-process shared state only. No message type carries them, and
   no news event discloses jump magnitude (spec 6.5, 9.8).
8. **Bots are indistinguishable from participants.** Same protocol, same
   ID namespace, randomly assigned per session. No flag, field, ID
   pattern or timing tell identifies a bot (spec 7.1).
9. **The server is the sole source of truth** for cash and positions.
   Every fill carries authoritative cash and the full position map; the
   client cache overwrites from it. Client state never feeds validation
   (spec 5.7).
10. **Rejected orders never reach the matching engine.** Validation is
    synchronous and pre-queue (spec 5.5).
11. **In-memory only in Phase 1.** No database, no message broker. The
    trade tape export is the only persistence (spec 16).

## Build order

Strictly sequential; a later milestone cannot be tested without the
earlier ones (spec 15.4).

1. Message schema and codec, frozen before any other code is written
2. Matching engine + correctness suite
3. Session manager, accounting, validation + suite
4. WebSocket gateway, auth, resync
5. Price process engine
6. `oqts-client` library
7. Bot ecosystem + dry-run protocol (spec 7.3)
8. Trade tape export
9. Student dashboard
10. Admin dashboard
11. Continuous practice exchange
12. Full integration test, 20+ connections

Do not start a milestone before the previous one's definition of done is
met. Do not run a live round with untuned bots (spec 7.3).

## Open items

Not blocking milestone 1, but unresolved. Raise rather than assume.

- **Practice exchange parameters** (spec 14.3) are provisional and need
  confirmation before milestone 11. The substantive one: whether the
  practice exchange runs a separate bot parameter set from competition.
- **The bot manager interface** between `oxdaq-core` (runner harness) and
  `oxdaq-ops` (implementations and parameters) is not designed. Agree the
  contract before writing either side.
- **A dashboard subsection of `brand.md`** is planned, covering tabular
  density, live-updating numeric cells and status treatment. Until it
  exists, follow `brand.md` as written.
