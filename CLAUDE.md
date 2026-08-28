# oxdaq-core: agent guidance

Read `../.github/CLAUDE.md` first (org rules, ownership boundary, house
rules). This file adds what is specific to the OXDAQ engine. Human
overview is `README.md`.

## Authoritative spec

`../planning/OXDAQ-PLAN.md` is the contract. Section numbers referenced
below are its sections. It states: do not deviate from these decisions
without updating this document first. Treat that literally.

Related: `../planning/ARCHITECTURE.md` (where OXDAQ sits in the estate),
`../oqts-design/brand.md` (all dashboard styling).

## Toolchain

Decided 2026-08-26. uv for environments and locking, Python pinned to
3.13, pytest for the correctness suites, ruff for lint and format.
Production containers use `python:3.13-slim` so local and server match.

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

Alec hand-writes, in neovim. Do not write these, do not "helpfully"
sketch them inline:

- The order book and matching logic (spec 3).
- Cash and position accounting, and order validation (spec 4).
- The price process engine and its maths (spec 5).
- Bot strategy logic (spec 6.2). The bot runner harness is Claude's.
- Every async surface: the WebSocket gateway, the single-consumer order
  loop, broadcast dispatch, and the client library's connection and
  event dispatch (spec 2.3, 7).

Claude writes: packaging, CI, ruff/pytest config, message schema types
and (de)serialisation (spec 8), test harnesses and fixtures, the trade
tape exporter, token issuance and auth, both dashboards, and anything
that ships to a browser or a server.

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
2. **Server time only.** Time priority comes from server enqueue order.
   Client timestamps are read for nothing that affects ordering (spec 2.3).
3. **Fill price is the resting order's price**, never the aggressor's
   (spec 3.3).
4. **Fair value never crosses the network.** Latent fair values reach bots
   through in-process shared state only. No message type carries them, and
   no news event discloses jump magnitude (spec 5.5, 8.6).
5. **Bots are indistinguishable from participants.** Same protocol, same
   ID namespace, randomly assigned per round. No flag, field, or timing
   tell in any outbound message identifies a bot (spec 6.1).
6. **The server is the sole source of truth** for cash and positions.
   Every fill carries authoritative cash and the full position map; the
   client cache overwrites from it. Client state never feeds validation
   (spec 4.5, 7.4).
7. **Rejected orders never reach the matching engine.** Validation is
   synchronous and pre-queue (spec 4.3).
8. **In-memory only in Phase 1.** No database, no message broker. The
   trade tape export is the only persistence (spec 12).

## Build order

Strictly sequential; a later milestone cannot be tested without the
earlier ones (spec 11).

1. Message schema, frozen before any other code is written
2. Matching engine + correctness suite
3. Session manager + accounting + suite
4. WebSocket gateway
5. Price process engine
6. `oqts-client` library
7. Bot ecosystem + dry-run protocol (spec 6.3)
8. Student dashboard
9. Admin dashboard
10. Full integration test, 20+ connections, trade tape validated

Do not start a milestone before the previous one's definition of done is
met. Do not run a live round with untuned bots (spec 6.3).

## Agreed deviations from the spec

Recorded here when agreed; the spec must be updated to match before the
code lands.

- **Dashboards are Next.js**, not a bundle served by FastAPI as spec 9.1
  says. Decided 2026-08-26 for reuse with `oqts-site` and standard
  patterns. Spec 9.1 and `ARCHITECTURE.md` Stack 2 need updating.

## Open spec questions

Unresolved. Do not paper over these in code: raise them.

Carried in the spec itself, marked for v1.1:

- Matching engine described as stateless in 2.2 but holds resting orders.
- Short-sale proceeds credit `cash`, which feeds buying-power validation
  for new buys, creating undocumented leverage (4.4).
- Full-snapshot `book_update` plus per-connection `seq` gap detection have
  no documented recovery action (8.5).

Found since, all blocking milestone 1 because they are schema-shaped:

- No `position_limit` check on buy orders. Section 4.3 checks it on sells
  only, so long positions are unbounded.
- `lot_size` is a stated constraint in 8.2 but absent from the validation
  table in 4.3, and `invalid_volume` is the only rejection reason.
- `reserved_short` is defined in 4.2 as units beyond the position, but
  4.4 increments it by the whole order volume. Pick one.
- Tick rounding (3.4) happens on receipt; 4.3 validates buying power on
  `price * volume`. Undefined whether validation uses the rounded price.
- `round_started` carries no round duration, but the dashboard shows a
  countdown derived from it (8.6, 9.1).
- The trade tape is a Phase 1 deliverable with no schema anywhere.
- Tokens travel as a URL query parameter (10.1), which lands them in
  access logs and proxy logs. Prefer the WebSocket subprotocol header or
  a first-message auth frame. Claude owns auth: propose before building.
