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
packages/oxdaq-engine/           C++ engine + nanobind module (arrives with E1)
tests/protocol/                  suites, samples.py
tests/golden/                    one frozen JSON frame per message type
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

**Protocol v2 is authorised** (D28 to D31): `order_type`, `trade_tick`,
`rate_limited`, `PROTOCOL_VERSION = 2`. Claude implements it once,
before milestone 2. After that the freeze applies to v2.

Ruff does not touch Markdown (it would reformat code blocks in docs).

## Commands

```bash
uv sync
uv run pytest            # uv run pytest -k book for one area
uv run ruff check .
uv run ruff format .
```

Never `pip install` into the venv; never hand-edit `uv.lock`. A new
dependency is a design decision: propose it first. C++ commands: build
2.2.

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
14. In memory only; the trade tape is the only persistence.

## Build order

Build 4. Milestone 1 is done at v1 and reopens once for v2; milestone 2
(the Python reference engine) is current. The engine track (E1, E2)
depends on milestone 2 only. Do not start a milestone before the
previous one is done. Never run a live round with untuned bots (design
7.3).

## Open

- Dashboard stack: decide before milestone 9 (build 2.3).
- Practice exchange parameters are provisional (operations 5.2); confirm
  before milestone 11.
- The bot runner interface with `oxdaq-ops` is not designed; agree it
  before either side is written.
- A dashboard subsection of `brand.md` is planned; until then follow
  `brand.md` as written.
