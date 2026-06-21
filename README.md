# OXDAQ — core exchange engine

**OXDAQ** is the Oxford Quantitative Trading Strategies (OQTS) live trading simulator: a real-time, low-latency exchange where members write Python trading algorithms and compete in live rounds against each other and a configurable ecosystem of market-making, trend-following, and noise-trading bots.

This repository holds the **public, open-source core** — the matching engine, the WebSocket protocol, and the `oqts-client` SDK that participants build against. Bot parameters, round configurations, and deployment live in separate (private) repositories.

> Status: **Phase 1 — pre-build.** This README describes the system as specified; build is proceeding against the milestones below.

## What it is

A centralised exchange server with WebSocket-connected clients. All matching, accounting, and state live server-side; clients are thin — they send orders and receive market data, with no privileged access to server state beyond what is explicitly broadcast.

The skill the simulator tests is **price discovery**: each instrument has a latent fair value that evolves over the round and is never broadcast. Participants must infer it from order-book dynamics.

## Architecture

Python 3.11+, FastAPI, and asyncio. All state is in-memory per round; no database or message broker in Phase 1.

| Component | Responsibility |
| --- | --- |
| **Matching engine** | Price-time priority CLOB. One order book per instrument. Pure, synchronous Python. |
| **Session manager** | Round lifecycle, instrument configs, cash/position accounting, the event queue. |
| **WebSocket gateway** | FastAPI + asyncio. One coroutine per connection; deserialises messages, enqueues orders, dispatches broadcasts. |
| **Price process engine** | Generates latent fair values (GBM / GBM+jumps / Ornstein–Uhlenbeck) with a shared market factor. Fed to bots only — never sent over the wire. |
| **Bot manager** | Runs server-side bot coroutines that connect over localhost using the same protocol as external participants. |
| **`oqts-client`** | PyPI package. Manages the WebSocket connection, local state cache, and event dispatch; exposes `BaseAlgorithm`. |

### The core correctness invariant

All order processing is serialised through a **single asyncio queue with a single consumer** — there is no concurrency inside the matching engine. Time priority is set by server queue-arrival order; client timestamps are ignored for ordering.

```python
async def order_loop():
    while round_active:
        msg, connection = await order_queue.get()
        validate(msg, connection)          # buying power, position limits
        fills = matching_engine.process(msg)
        update_accounting(fills)
        await send_ack(connection, msg)
        await broadcast_fills(fills)
        await broadcast_book_update(msg.instrument_id)
```

## Writing a strategy

Participants install the client and subclass `BaseAlgorithm`, overriding the event handlers they need. The library handles WebSocket, caching, and dispatch — you never touch asyncio directly.

```bash
pip install oqts-client
python my_strategy.py --token <team_token> --host oqts.ox.ac.uk
```

```python
from oqts import BaseAlgorithm, Side

class MyStrategy(BaseAlgorithm):
    def on_book_updated(self, instrument_id, book):
        # book.bids / book.asks: price-ordered levels
        ...

    def on_fill(self, fill):
        # fill.cash and fill.position are authoritative, server-supplied
        ...

if __name__ == '__main__':
    MyStrategy().run()
```

`submit_order()` is **non-blocking** — it returns a `client_order_id` immediately and does not wait for the ack. State accessors (`get_book`, `get_positions`, `get_cash`) are O(1) cache reads; the cache self-corrects from authoritative server state on every fill.

The full WebSocket message schema (envelope, order/cancel, acks, fills, book updates, round lifecycle, news events) is the protocol contract — see [`docs/`](./docs) *(to be added)*.

## Build status

Milestones, in dependency order (a later step can't be tested without the earlier ones):

- [ ] 1. Message schema — frozen before any other code
- [ ] 2. Matching engine (`OrderBook` correctness suite)
- [ ] 3. Session manager + accounting
- [ ] 4. WebSocket gateway (orders/fills over the wire)
- [ ] 5. Price process engine (3 process types + market-factor correlation)
- [ ] 6. `oqts-client` library (`BaseAlgorithm`)
- [ ] 7. Bot ecosystem (market maker, trend follower, noise trader; dry-run protocol)
- [ ] 8. Student dashboard
- [ ] 9. Admin dashboard
- [ ] 10. Full integration test (20+ concurrent connections; trade-tape export)

## Scope

Phase 1 only: matching engine, session manager, client library, bot ecosystem, and dashboards. Mark-to-market P&L and a local mock exchange are deferred to Phase 2. Scoring is realised P&L (`final_cash − starting_cash`).

## Contributing

See the org-wide [CONTRIBUTING guide](https://github.com/oqts/.github/blob/main/CONTRIBUTING.md). PRs into `main` require a code-owner review; never commit secrets.

## License

[MIT](./LICENSE) © Oxford Quantitative Trading Strategies
