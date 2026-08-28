# OXDAQ: core exchange engine

**OXDAQ** is the Oxford Quantitative Trading Society (OQTS) live trading simulator: a real-time exchange where members write Python trading algorithms and compete in live rounds against each other and a configurable ecosystem of market-making, trend-following and noise-trading bots.

This repository holds the **public, open-source core**: the matching engine, the WebSocket protocol, the `oqts-client` SDK that participants build against, and both dashboards. Bot parameters, round configurations and deployment live in separate private repositories, because the bots are meant to be reverse-engineered during a round, not before it.

> **Status: Phase 1, in build.** Milestone 1 (the wire protocol) is complete and frozen at protocol version 1. Milestone 2 (the matching engine) is in progress. See [build status](#build-status).

## What it is

A centralised exchange server with WebSocket-connected clients. All matching, accounting and state live server-side. Clients are thin: they send orders and receive market data, with no privileged access to server state beyond what is explicitly broadcast.

The skill the simulator tests is **price discovery**. Each instrument has a latent fair value that evolves over the round and is never broadcast, in any message, under any condition. Participants must infer it from order book dynamics.

## Architecture

Python 3.13, FastAPI and asyncio. All state is in memory per round. No database and no message broker in Phase 1; the trade tape export is the only persistence.

| Component | Responsibility |
| --- | --- |
| **Matching engine** | Price-time priority CLOB. One order book per instrument. Pure synchronous Python, no async, no I/O. |
| **Session manager** | Round lifecycle, instrument configs, cash and position accounting, order validation, the event queue. |
| **WebSocket gateway** | FastAPI and asyncio. One coroutine per connection. Authenticates, deserialises, validates, enqueues, dispatches broadcasts. |
| **Price process engine** | Latent fair values (GBM, GBM with jumps, Ornstein-Uhlenbeck) driven by a shared market factor. Reaches bots through in-process shared state only, never the network. |
| **Bot manager** | Runs server-side bot coroutines that connect over localhost using the same protocol as external participants. |
| **`oqts-client`** | PyPI package. WebSocket connection, local state cache, event dispatch. Exposes `BaseAlgorithm`. |
| **Dashboards** | One Next.js app. Student view for P&L, positions and news; admin view for the leaderboard and round control. |

### The core correctness invariant

All order processing is serialised through **a single asyncio queue with exactly one consumer**. There is no concurrency inside the matching engine, no locks and no second consumer. Time priority is the server's queue arrival order; client timestamps are read for nothing that affects ordering.

Validation happens in the **gateway coroutine, before the order is enqueued**, not in the consumer:

```python
# Gateway coroutine. No await between the check and the reservation, so
# under asyncio's cooperative scheduling this is atomic.
if not passes_validation(order, state):
    return reject(order, reason)
state.reserve(order)                    # reserved_cash or open_buy/sell_volume
order.server_timestamp = now()
order_queue.put_nowait((order, connection))
```

```python
# The single consumer. Everything here is already known to be legal.
async def order_loop():
    while session_active:
        msg, connection = await order_queue.get()
        fills = matching_engine.process(msg.order)
        apply_fills(fills)
        await broadcast_fills(fills)
        await broadcast_book_update(msg.instrument_id)
```

If the check read state in the gateway but the reservation happened later in the consumer, two orders could both validate against the same cash before either was processed, and both would be accepted. The reservation must be taken at the moment of the check.

### Integers inside, decimals at the boundary

Binary floating point cannot represent 0.01. The competition is decided by a cash figure, so prices are integer tick counts and cash is an integer count of 1/10000 of a currency unit. Conversion happens only in the codec, at serialisation and deserialisation. No epsilon comparison exists anywhere in the engine, and the scoring figure is reproducible exactly from the trade tape.

Participants see and send ordinary decimal prices and never know the server is working in integers.

## Repository layout

A [uv](https://docs.astral.sh/uv/) workspace with two packages.

```
packages/oqts-client/src/oqts/     published to PyPI, imported as `oqts`
    protocol/                      enums, messages, codec  (shared, frozen)
packages/oxdaq/src/oxdaq/          the server, never published
    units.py                       the integer/decimal boundary (server only)
tests/golden/                      one frozen JSON frame per message type
docs/protocol.md                   the wire protocol, for humans
```

Message shapes are shared, because the server, the client, the bots and both dashboards all need them. The integer conversion is server-only, because the client is float-native throughout. The server depends on the client rather than the reverse, since bots connect over localhost using the participant protocol, which makes the two definitions structurally unable to drift apart.

## Writing a strategy

Install the client and subclass `BaseAlgorithm`, overriding the handlers you need. The library owns the connection, authentication, reconnection, the local cache and event dispatch. You never touch asyncio or WebSocket directly.

```bash
pip install oqts-client
python my_strategy.py --token <team_token> --host oxdaq.oqts.org
```

```python
from oqts import BaseAlgorithm, Side

class MyStrategy(BaseAlgorithm):
    def on_book_updated(self, instrument_id, book):
        # book.bids / book.asks: price-ordered levels
        ...

    def on_fill(self, fill):
        # fill.cash and fill.positions are authoritative, server-supplied
        ...

if __name__ == '__main__':
    MyStrategy().run()
```

`submit_order()` is **non-blocking**: it returns immediately and does not wait for the ack. State accessors (`get_book`, `get_positions`, `get_cash`) are O(1) cache reads, and the cache is overwritten from authoritative server state on every fill, so it cannot permanently diverge.

The wire protocol is documented in [`docs/protocol.md`](./docs/protocol.md). Read the "six things that surprise people" section before your first round; the most important is that **your resting orders survive a disconnection** and can fill while your process is asleep or dead.

## The practice exchange

The competition itself is about twenty minutes on the day, which is no way to develop a strategy. A practice exchange runs continuously so members can build and test whenever they like. It is a separate process and container from the competition exchange, sharing no event loop, port or state object, so nothing happening in practice can touch a live round.

## Development

```bash
uv sync                  # create or refresh .venv from uv.lock
uv run pytest            # full suite
uv run ruff check .      # lint
uv run ruff format .     # format
```

Python is pinned to 3.13 and production containers run `python:3.13-slim`, so local, CI and server match exactly. Never `pip install` into the venv directly and never hand-edit `uv.lock`.

**The wire protocol is frozen.** `tests/golden/` pins every message byte for byte, and a test walks every outbound model to guarantee no field could carry a latent fair value. A failure there is not a broken test; it means the wire shape changed, which requires a `PROTOCOL_VERSION` bump and a matching specification change.

## Build status

Strictly by dependency: a later milestone cannot be meaningfully tested without the ones before it.

- [x] 1. Message schema and codec, frozen before any other code
- [ ] 2. Matching engine (`OrderBook` correctness suite)
- [ ] 3. Session manager, accounting and validation
- [ ] 4. WebSocket gateway (orders and fills over the wire, auth, resync)
- [ ] 5. Price process engine (three processes, market-factor correlation)
- [ ] 6. `oqts-client` library (`BaseAlgorithm`)
- [ ] 7. Bot ecosystem (market maker, trend follower, noise trader; dry-run protocol)
- [ ] 8. Trade tape export
- [ ] 9. Student dashboard
- [ ] 10. Admin dashboard
- [ ] 11. Continuous practice exchange
- [ ] 12. Full integration test, 20+ concurrent connections

## Scope

Phase 1 scores **realised P&L only**: `final_cash - starting_cash`. Open positions are not marked to market, which avoids any dependence on mid-price stability in thin or early books.

Deferred to Phase 2: mark to market P&L, a real margin model, order book visualisation, per-instrument position limits, server-side strategy hosting, and persistent storage with replay.

## Contributing

See the org-wide [CONTRIBUTING guide](https://github.com/oqts/.github/blob/main/CONTRIBUTING.md). PRs into `main` require a code-owner review. Never commit secrets.

## Licence

[MIT](./LICENSE), Oxford Quantitative Trading Society.
