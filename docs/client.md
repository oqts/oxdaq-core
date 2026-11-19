# The Python client

Spec 3.0, 2026-11-19. `oqts-client`, the library participants write
strategies with.

A strategy is a plain script or notebook: connect, then loop, reading
state and placing orders when you choose. No callbacks to override, no
asyncio or WebSocket in sight. Members who have used Optiver's Optibook
will recognise the model.

## 1. Install and run

```bash
pip install oqts-client
export OQTS_TOKEN=<team_token>
python my_strategy.py
```

## 2. The `Exchange` object

```python
from oqts import Exchange

ex = Exchange(host="oxdaq.oqts.org")   # token from $OQTS_TOKEN, or token=
ex.connect()                           # authenticates; returns once state is loaded

# State: local cache reads, never a network call
ex.get_instruments()      # dict[str, Instrument]: tick_size, lot_size, position_limit
ex.round_active()         # bool
ex.time_remaining()       # seconds, or None on the practice exchange
ex.get_book(iid)          # Book: .bids, .asks best first; .best_bid, .best_ask, .mid, .spread
ex.get_positions()        # dict[str, int], every instrument present
ex.get_cash()             # float, authoritative as of the last fill
ex.get_pnl()              # float, indicative (below)
ex.get_outstanding_orders(iid=None)   # dict[str, Order]
ex.connected()            # bool

# Orders: each blocks until the server answers
r = ex.insert_order(iid, price=99.5, volume=5, side="bid", order_type="limit")
r.accepted, r.order_id, r.price, r.reason      # price after tick rounding
ex.cancel_order(r.order_id)                    # CancelResponse
ex.cancel_all(iid=None)                        # every resting order

# Events since your last call, oldest first
ex.poll_new_trades(iid=None)          # list[Fill]: your fills
ex.poll_new_trade_ticks(iid=None)     # list[TradeTick]: every public trade
ex.poll_news()                        # list[News]

ex.wait_for_update(timeout=None)      # block until anything changes; True if it did
ex.disconnect()
```

A typical strategy:

```python
while ex.round_active():
    book = ex.get_book("ABC")
    if book.best_bid and book.best_ask:
        ...                                    # decide, then insert or cancel
    for fill in ex.poll_new_trades("ABC"):
        ...
    ex.wait_for_update(timeout=1.0)
```

- **Arguments after the instrument are keyword-only,** so an order reads
  as what it does. `side` takes `"bid"`/`"ask"` or `Side`; `order_type`
  takes `"limit"`/`"ioc"` or `OrderType`.
- **`insert_order` blocks for one round trip** and returns the ack or the
  rejection. The `order_id` can be cancelled at once.
- **An IOC that does not fully fill** reports its unfilled volume as
  `r.cancelled_volume` once matching completes.
- **`get_pnl()` is indicative:** the change in cash plus open positions
  at each instrument's last trade price. The competition scores realised
  P&L only ([`operations.md`](operations.md) 1), which is `get_cash()`
  minus starting cash.
- **`wait_for_update` is the recommended pause.** It returns as soon as a
  book, fill, trade or news item arrives. A loop that never pauses meets
  the rate limit.
- **Works in Jupyter:** every call is synchronous.

## 3. Inside the client

The connection runs on a **background thread** with its own asyncio
loop: `oqts.aio`, an async client with the same operations as `async`
methods. `Exchange` methods are thread-safe: reads take a short lock on
the cache; requests are handed to the loop with
`asyncio.run_coroutine_threadsafe` and wait on the result. A slow
strategy cannot stall the connection, and Jupyter's own event loop is
never asked to run a second one.

The cache (books, positions, cash, open orders) is updated from each
inbound message before anything is visible to the strategy, and
overwritten from authoritative state on every fill and snapshot. Poll
queues are bounded; on overflow the oldest events are dropped with a
warning.

Server-side bots use `oqts.aio` directly.

## 4. Disconnection

When a connection closes, the server cancels every order that connection
submitted ([`protocol.md`](protocol.md) 2). The client reconnects with
exponential backoff, re-authenticates and rebuilds its cache from the
`state_snapshot`. Orders are gone; positions and cash are not. A strategy
that cares checks `ex.connected()` each loop and requotes after a
reconnect.
