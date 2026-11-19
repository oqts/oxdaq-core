# Building OXDAQ

Spec 3.0, 2026-11-19. Repositories, toolchain, who writes what, the
build order, and what waits for Phase 2.

## 1. Repositories

| Repo | Visibility | Holds |
| --- | --- | --- |
| `oxdaq-core` | public | Engine (Python and C++), session manager, gateway, price process, protocol, `oqts-client`, bot runner, dashboards, this spec |
| `oxdaq-ops` | private | Bot implementations and parameter distributions, round and instrument configs, news schedules, admin tooling |
| `oqts-infra` | private | The society server: Caddy, compose files, deploy |

Open engine, closed configuration: participants may read how the
exchange works, but not the bots, their parameter distributions or the
news schedule, so the edge comes from the market ([`design.md`](design.md) 1.1).

`oxdaq-core` is a uv workspace:

```
packages/oqts-client/    published to PyPI as oqts-client, imported as `oqts`
packages/oxdaq/          the server, never published
packages/oxdaq-engine/   the C++ engine and its nanobind module (arrives with E1)
```

The server depends on the client, not the reverse: bots connect with the
participant protocol, so the wire definitions cannot drift apart.

## 2. Toolchain

### 2.1 Python

uv, Python 3.13 (production containers run `python:3.13-slim`), pytest,
Hypothesis, ruff.

```bash
uv sync              # create or refresh .venv from uv.lock
uv run pytest
uv run ruff check .
uv run ruff format .
```

Never `pip install` into the venv, never hand-edit `uv.lock`. **Adding a
dependency is a design decision.**

Wire models are pydantic v2; internal types (`Order`,
`ParticipantState`) are plain dataclasses, since they sit on the hot path.
The two meet only in the codec.

**The protocol freeze is mechanical.** `PROTOCOL_VERSION` is sent in
`auth_ok`, and `tests/golden/` holds one JSON frame per message type,
compared byte for byte. Any wire change fails CI until it is made
deliberately ([`protocol.md`](protocol.md), top).

### 2.2 C++ (`packages/oxdaq-engine`)

| Concern | Choice |
| --- | --- |
| Language | C++20 |
| Build | CMake presets `dev`, `asan` (AddressSanitizer and UndefinedBehaviorSanitizer), `release`; `compile_commands.json` for clangd |
| Into uv | scikit-build-core as the package's build backend; built from source locally and in the Docker build stage; `tool.uv.cache-keys` covers the C++ sources |
| Bindings | nanobind |
| Compilers | Apple clang locally; GCC 14 and clang 18 in CI. `-Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror`; release `-O2`, no `-march=native` |
| Tests | GoogleTest via `ctest`, plus the shared Python suite and differential test against the built module |
| Fuzzing | libFuzzer on Linux clang: random operation streams with book invariants checked |
| Benchmarks | Google Benchmark and a replay harness (p50, p99, p99.9 per operation). Run by hand, never a CI gate |
| Lint | clang-format, clang-tidy |
| Dependencies | CMake `FetchContent`, pinned by tag |
| CI | GitHub Actions on macOS and Ubuntu (GCC, clang): ctest, sanitizer build, pytest on both engines, differential test |

```bash
cd packages/oxdaq-engine
cmake --workflow --preset dev                # configure, build, ctest (also asan, release)
uv sync --reinstall-package oxdaq-engine     # rebuild the module for Python
```

`cpp/` holds the engine (headers in `cpp/include/oxdaq/`, sources in
`cpp/src/`) and `tests/cpp/` its GoogleTest suite; CMake picks up new
files in either with no edit. GoogleTest is pinned to v1.17.0 by URL and
SHA-256.

### 2.3 Dashboards

**Open: the stack is decided before milestone 9.** Next.js was chosen
for reuse with the society's website, which is being rewritten as a
Django app, so that reason no longer holds.

## 3. Who writes what

OXDAQ is built by one engineer who intends to understand it end to end;
that goal outranks speed.

| Written by hand (Alec) | Written by Claude |
| --- | --- |
| Order book and matching, Python and C++, and the nanobind binding code | Scaffolding, packaging, CMake and presets, CI, tooling |
| Accounting and validation | Message schema, codec, integer/decimal conversion |
| Price process and its maths | Correctness suites, the differential test, fuzz target, benchmark harnesses, fixtures |
| Bot strategy logic | Bot runner harness, config loading |
| Every async surface: gateway, order loop, broadcast, disconnect sweep, rate limiter, `oqts.aio` and the `Exchange` thread bridge | Auth and token issuance, trade tape writer, dashboards, deployment and anything security-facing |

The concurrency model and the maths are the system, so they are written
by hand. Auth, deployment and frontend are where a hand-rolled version
is a liability.

## 4. Build order

Strictly by dependency. A milestone starts when the previous one's
definition of done is met. The build is scheduled in rounds outside this
repo; this is the order those rounds respect.

| # | Deliverable | Done when |
| --- | --- | --- |
| 1 | Message schema and codec | Every message defined; integer/decimal round trip exact under a property test; frozen in the golden corpus. **Done at v1; reopens once for v2** (`order_type`, `trade_tick`, `rate_limited`, `PROTOCOL_VERSION = 2`) before milestone 2, since IOC is part of the engine interface |
| 2 | Reference matching engine (Python) | Shared suite passes: partial and full fills, price-time priority, price improvement, IOC, multiple instruments, every rejection path |
| 3 | Session manager and accounting | Suite covers buying power, both position bounds, the fill-invariance property, short selling, cancel release, round-end drain |
| 4 | WebSocket gateway | Two processes authenticate, trade and receive fills and ticks; `resync` correct after a forced disconnect, and the disconnected connection's orders are gone; rate limit enforced; `book_update` coalesced under load |
| 5 | Price process | All three processes valid; market-factor correlation verified statistically; linked instruments once specified ([`design.md`](design.md) 1.2) |
| 6 | `oqts-client` | `Exchange` and `oqts.aio` connect, trade, keep correct state and recover from a forced disconnect, as a script and in a notebook |
| 7 | Bots | All four types, informed trader included, pass the dry run together across the parameter distributions; parameters drawn per round from the seed |
| 8 | Trade tape | Bundle written and validated; cash P&L recomputed from `trades.csv` and the score from it plus `final_fair_value` both match `participants.csv` exactly |
| 9 | Student dashboard | P&L, positions, cash, timer and news correct in a test session |
| 10 | Admin dashboard | Live leaderboard; start, end and news injection work |
| 11 | Practice exchange | 72 hours unattended; daily reset fires, tape written, memory flat |
| 12 | Integration | 20+ connections, bots and test algorithms, a full round without error, tape validated |

The full-book broadcast fanned out to every connection, not matching, is
the expected bottleneck at 80 participants; hence coalescing in 4.

**Engine track,** depending on milestone 2 only, alongside 3 to 12:

| # | Deliverable | Done when |
| --- | --- | --- |
| E1 | C++ engine, selectable | Passes the equivalence gate ([`design.md`](design.md) 4.5); `engine = "cpp"` runs a practice session end to end |
| E2 | C++ engine for latency | Rewritten for cache behaviour and allocation (price-indexed arrays, intrusive lists, pooled orders) behind the same gate; p50, p99, p99.9 reported for E1 and E2 |

## 5. Phase 2

Not built until Phase 2 is scoped.

| Item | Why it waits |
| --- | --- |
| A full C++ exchange | The order loop, then the gateway, in C++ around the engine core, with threads, a lock-free single-producer single-consumer queue and a socket or shared-memory boundary. Phase 1 keeps C++ to the engine, where nothing is threaded |
| Live mark-to-market P&L | Needs a stable mid; `(best_bid + best_ask) / 2` with a minimum liquidity rule. The final score already values positions at fair value ([`operations.md`](operations.md) 1) |
| Regime-switching price process | Unannounced switches between trending and mean-reverting, for in-round signal research. The Phase 1 edges come first ([`design.md`](design.md) 1.1) |
| Real margin model | Margin calls and liquidation are a long tail; Phase 1 documents its leverage instead ([`design.md`](design.md) 5.4) |
| Amending orders | Volume amend keeping priority on a reduction. Cancel and replace covers Phase 1 |
| Local sandbox | `Exchange(local=True)`: the reference engine and bots in process, offline |
| Order book visualisation | P&L and positions suffice for Phase 1 |
| Per-instrument position limits | Phase 1 uses one uniform limit |
| Server-side strategy hosting | Member algorithms on society compute, on a separate machine for trust reasons |
| Persistent storage and replay | The tape carries the seed, so replay needs no schema change |
| Rejecting un-ticked prices | Phase 1 normalises; `order_rejected` already has a reason field |
| A `book_update` depth limit | Watch at milestone 12; `protocol_version` makes adding one a detectable change |
