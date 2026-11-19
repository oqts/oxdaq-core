# OXDAQ

**OXDAQ** is the Oxford Quantitative Trading Society's live trading simulator: a real-time exchange where members write Python trading algorithms and compete in live rounds against each other and an ecosystem of market-making, informed, trend-following and noise-trading bots.

This repository is the **open-source core**: the matching engine, the wire protocol, the `oqts-client` library participants build against, and the dashboards. Bot parameters and round configurations live in a private repository, and bot parameters are redrawn every round, so strategies win by reading the market rather than the bots.

> **Status: in build.** The wire protocol is done (version 2). The Python reference matching engine is next, against a ready test suite. See [build status](#build-status).

## How it works

A central exchange server with WebSocket clients. All matching, accounting and state live on the server; clients send orders and receive market data.

Every instrument has a hidden fair value that moves during the round and is never broadcast. The market is built so that **every edge comes from information or modelling a real trader would have, never from knowing how the bots work**: market making against informed traders, relative value between linked instruments, and interpreting news. Bot parameters are redrawn every round, open positions are scored at the true price revealed afterwards, and past rounds' trade tapes are published for offline signal research.

- **One queue, one consumer.** Every order goes through a single queue processed by one consumer, so the engine needs no locks and time priority is simply arrival order.
- **Integers inside.** Prices are integer ticks and cash is an integer count of 1/10000 of a unit, so scores are exact and reproducible from the trade tape.
- **Two matching engines.** A Python reference engine and a C++20 engine, loaded into the same process, held to exactly equal behaviour by a differential test. Either can run a round.

The full design is in [`docs/`](docs/README.md).

## Writing a strategy

Strategies are plain Python scripts or notebooks. Connect, then loop: read the book, place and cancel orders, check what happened since you last looked. If you have used Optiver's Optibook, this will feel familiar.

```bash
pip install oqts-client
export OQTS_TOKEN=<team_token>
python my_strategy.py
```

```python
from oqts import Exchange

ex = Exchange(host="oxdaq.oqts.org")
ex.connect()

while ex.round_active():
    book = ex.get_book("ABC")                     # bids and asks, best first
    if book.best_bid and book.best_ask:
        r = ex.insert_order("ABC", price=book.best_bid.price, volume=5,
                            side="bid", order_type="limit")
        # r.order_id is usable at once: ex.cancel_order(r.order_id)
    for fill in ex.poll_new_trades("ABC"):        # your fills since last call
        print(fill.price, fill.volume)
    ex.wait_for_update(timeout=1.0)               # wake as soon as anything changes
```

Two rules worth knowing before your first round:

- **If your connection drops, your resting orders are cancelled.** Positions and cash stay. The client reconnects by itself; requote when it does.
- **Order messages are rate limited** (25 a second by default). Pause each loop with `wait_for_update` rather than spinning.

The client is described in [`docs/client.md`](docs/client.md) and the wire protocol in [`docs/protocol.md`](docs/protocol.md).

## The practice exchange

A competition round lasts about twenty minutes, which is no way to develop a strategy. A practice exchange runs continuously, in a separate process from the competition exchange, so members can build and test whenever they like.

## Development

```bash
uv sync                  # create or refresh .venv from uv.lock
uv run pytest            # full suite
uv run ruff check .      # lint
uv run ruff format .     # format
```

Python is pinned to 3.13.

**Where the matching engine stands:**

```bash
uv run pytest tests/engine -q
```

This is the shared correctness suite, run against each engine ([`docs/design.md`](docs/design.md) 4.5). Until the reference engine exists it reports one failure naming what to write. A failing random stream is saved to `.oxdaq/failures/`; `uv run python -m tests.engine.replay <file> --shrink` cuts it down to the fewest orders that still fail.

**The C++ engine** lives in `packages/oxdaq-engine`. It builds with CMake presets (`dev`, `asan`, `release`) and is packaged into the workspace by scikit-build-core ([`docs/build.md`](docs/build.md) 2.2). It needs CMake 3.25+ and Ninja (`brew install cmake ninja`); clang-format, clang-tidy and clangd come with `brew install llvm`.

```bash
cd packages/oxdaq-engine
cmake --workflow --preset dev     # configure, build, run GoogleTest
cmake --workflow --preset asan    # the same under AddressSanitizer and UBSan
```

**The wire protocol is frozen.** `tests/golden/` pins every message byte for byte. A failure there means the wire shape changed, which requires a `PROTOCOL_VERSION` bump and a matching change to `docs/protocol.md`.

## Build status

- [x] 1. Message schema and codec (protocol v1)
- [x] 1b. Protocol v2: IOC orders, `trade_tick`, rate limit, cancel on disconnect (schema; the disconnect sweep is built in 4)
- [ ] 2. Python reference matching engine
- [ ] 3. Session manager, accounting and validation
- [ ] 4. WebSocket gateway
- [ ] 5. Price process
- [ ] 6. `oqts-client` (`Exchange` and `oqts.aio`)
- [ ] 7. Bots
- [ ] 8. Trade tape
- [ ] 9. Student dashboard
- [ ] 10. Admin dashboard
- [ ] 11. Practice exchange
- [ ] 12. Integration test, 20+ connections

Alongside milestones 3 to 12, the C++ engine:

- [ ] E1. C++ engine, selectable, proved equal to the reference
- [ ] E2. C++ engine rewritten for latency, behind the same test

## Scope

Rounds score **realised P&L only**: `final_cash - starting_cash`. Phase 2 ideas, from mark-to-market P&L to a fully C++ exchange, are listed in [`docs/build.md`](docs/build.md).

## Contributing

See the org-wide [CONTRIBUTING guide](https://github.com/oqts/.github/blob/main/CONTRIBUTING.md). PRs into `main` need a code-owner review. Never commit secrets.

## Licence

[MIT](./LICENSE), Oxford Quantitative Trading Society.
