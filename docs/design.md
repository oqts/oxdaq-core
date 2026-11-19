# OXDAQ design

Spec 3.0, 2026-11-19. How the exchange works and why. The decisions
behind each choice are in [`decisions.md`](decisions.md).

## 1. Purpose

OXDAQ is the OQTS live trading simulator: a real-time exchange for
competition rounds and a strategy incubator.

- 20 to 80 concurrent participants per round.
- Participants write Python against a simple synchronous client
  ([`client.md`](client.md)), never touching asyncio or WebSockets.
- Anonymous bots trade alongside participants, indistinguishable from
  them on the wire.
- Live dashboards for participants (P&L, positions) and the admin
  (leaderboard, round control).
- A trade tape after every round, for scoring.
- A practice exchange that is always up.

**The skill being tested is price discovery.** Each instrument has a
latent fair value that evolves over the round and is never broadcast.
Participants infer it from the order book.

## 2. Architecture

### 2.1 Stack

Python 3.13, FastAPI and asyncio, WebSockets via Starlette. The matching
engine alone also exists in C++20, as the in-process extension module
`oxdaq_engine` (section 4.5). No database and no message broker: all
session state is in memory, and the trade tape is the only persistence.

### 2.2 Components

| Component | Responsibility |
| --- | --- |
| Matching engine | Price-time priority order book, one per instrument. Synchronous, no I/O. A Python reference and a C++ implementation behind one interface (4.5) |
| Session manager | Round lifecycle, instrument configs, accounting, validation, the order queue, the mapping between protocol string ids and engine integer ids |
| WebSocket gateway | One coroutine per connection. Authenticates, decodes, validates and reserves, enqueues, broadcasts |
| Price process | Latent fair values on a 1 second tick. Feeds bots through in-process state only |
| Bot manager | Runs bot coroutines that connect over localhost with the participant protocol |
| Trade tape writer | Writes the round's export bundle at round end |
| `oqts-client` | PyPI package: the synchronous `Exchange` over an async core, `oqts.aio` |
| Dashboards | One web app: student view and admin view, each a protocol client |

The matching engine is stateful (it holds every resting order) but free
of shared state and concurrency, which is the property that matters.

### 2.3 The order loop

**All order processing is serialised through one asyncio queue with
exactly one consumer.** No concurrency inside the engine, no locks, no
second consumer.

```python
async def order_loop():
    while session_active:
        msg, connection = await order_queue.get()
        match msg:
            case SubmitOrder():
                fills = engine.process(msg.order)   # IOC remainder cancelled here
                apply_fills(fills)
                await broadcast_fills_and_ticks(fills)
            case CancelOrder():
                cancelled = engine.cancel(msg.order_id)
                release_reservations(cancelled)
                await send_cancel_ack(connection, cancelled)
            case DisconnectSweep():
                for order_id in orders_of(msg.connection):
                    release_reservations(engine.cancel(order_id))
            case AdminCommand():
                apply_admin(msg)                     # start, end, cancel team orders
        await broadcast_book_update(msg.instrument_ids)
```

Time priority is queue arrival order: each order gets an integer arrival
sequence at enqueue. A server timestamp is recorded alongside, for the
trade tape only. Client timestamps affect nothing.

When a connection closes, the gateway enqueues a **disconnect sweep**,
so cancelling that connection's orders takes its place in sequence like
any other cancel.

### 2.4 Validation happens in the gateway

Validation runs in the gateway coroutine, before enqueue, and the check
and the reservation it justifies are one synchronous step:

```python
# No await between the check and the reservation: under asyncio's
# cooperative scheduling this block is atomic.
if not passes_validation(order, state):
    return reject(order, reason)
state.reserve(order)          # reserved_cash or open_buy/sell_volume
order.seq = next_seq()
order_queue.put_nowait((order, connection))
```

If the check read state in the gateway but the reservation happened
later in the consumer, two orders could both pass against the same cash
before either was processed.

**Rule: any validation that reads mutable participant state takes its
reservation in the same synchronous step, with no `await` between them.**

Cancels are the mirror image: reservations are released **in the
consumer**, after the book removal succeeds, never on receipt. Reserving
early and releasing late both err on the safe side.

## 3. Numbers

### 3.1 Why integers

Binary floating point cannot represent 0.01. Float prices would mean
approximate comparisons in the book's sort key and cash drifting over
thousands of fills, in a competition decided by a cash figure.

### 3.2 Representation

| Quantity | Type | Meaning |
| --- | --- | --- |
| Price | `int` | Count of ticks, `price_ticks` |
| Cash, notional, P&L | `int` | Accounting units: 1/10000 of a currency unit |
| Volume, position | `int` | Units |

`TICK_SCALE = 10_000`. Every `tick_size` must be an exact multiple of
1/10000; config load rejects anything finer.

```python
tick_units  = round(tick_size * TICK_SCALE)   # 0.01 -> 100, exact
price_units = price_ticks * tick_units        # exact
notional    = price_units * volume            # exact
```

Python integers do not overflow. The C++ engine uses 64-bit integers;
`MAX_PRICE_TICKS` (3.3) keeps every product in range.

### 3.3 The wire boundary

Conversion happens only in the codec. No other module touches a float.

```python
to_wire   = (price_ticks * tick_units) / TICK_SCALE       # one rounding
from_wire = floor(price * TICK_SCALE / tick_units + 0.5)  # round half up
```

Each does its multiply in exact integers and leaves one correctly
rounded float operation. The obvious `price_ticks * tick_size` rounds
twice and serialises visibly wrong figures (1234 ticks at 0.07 becomes
`86.38000000000001`).

`from_wire(to_wire(t)) == t` holds exactly up to `2**50` (measured over
sixteen tick sizes). `MAX_PRICE_TICKS = 2**48` is enforced, and anything
above it is rejected as `invalid_price`.

Participants send and see ordinary decimals. Round half up is used, not
banker's rounding, because it is easy to state. The trade tape uses exact
decimal strings, so the score is reproducible byte for byte.

## 4. Matching engine

### 4.1 Algorithm

Price-time priority. Per instrument, bids sorted by price descending and
asks by price ascending, each then by arrival sequence. An incoming order
that crosses the spread matches against resting orders in priority order
until it is filled or nothing matchable remains.

Two order types:

- **Limit:** any unmatched remainder rests.
- **IOC** (immediate or cancel): matches identically; the remainder is
  cancelled at once and never enters the book.

### 4.2 Data structures (reference engine)

```python
@dataclass(slots=True)
class Order:
    order_id: int             # integer ids; the session manager maps
    team_id: int              # them to and from protocol strings
    instrument_id: int
    side: Side                # BID | ASK
    order_type: OrderType     # LIMIT | IOC
    price_ticks: int
    volume: int
    remaining_volume: int
    seq: int                  # arrival sequence: time priority

class OrderBook:
    # Exact integer keys: no epsilon comparison anywhere.
    #   bids: key = (-price_ticks, seq)
    #   asks: key = ( price_ticks, seq)
    bids: SortedList[Order]
    asks: SortedList[Order]
```

`sortedcontainers.SortedList` keeps itself ordered by its `key`.
Negating the bid price makes "highest first" fall out of an ascending
sort, so both sides share traversal code: index 0 is always the best.
`client_order_id` never enters the engine.

### 4.3 Fill price

Always the **resting** order's price. An aggressor with a better limit
gets price improvement; the maker's limit is honoured exactly.

### 4.4 Partial fills

One order may match several resting orders across several levels. Each
match produces a `fill` to both counterparties and a public `trade_tick`
to everyone ([`protocol.md`](protocol.md) 6, 7).

### 4.5 Two implementations

The engine is the one component written twice, behind one interface (a
`typing.Protocol` in Python): submit an order and get its fills; cancel
by id and get the remainder or a failure; snapshot a book. Both take and
return integers only. Sections 4.1 to 4.4 bind both identically.

- **Reference engine** (Python, 4.2). Built first; the rest of the
  system is built and run on it. Kept permanently as the test oracle and
  the live fallback.
- **C++ engine.** A pure C++20 library with no Python dependency, plus a
  thin nanobind module, `oxdaq_engine`, in `packages/oxdaq-engine`. A
  Python-free core can later sit behind a C++ order loop unchanged.

**In process.** The single consumer calls the engine directly. The GIL is
held for every engine call: the consumer is already the serialisation
point, and releasing it would only admit a second thread to the book.
No engine call blocks or does I/O. The C++ engine owns its resting
orders; fills and snapshots cross the boundary as value copies.

A separate engine process was rejected: if it crashed the book would be
lost while the session manager still held reservations against it, so
it isolates less than it seems, and it needs a second internal protocol.

**The equivalence gate.** The C++ engine may run a live round only when:

1. the shared correctness suite passes against both engines;
2. a differential test passes: random streams of submits and cancels
   across instruments, through both engines, give exactly equal fills in
   the same order and exactly equal books (everything is integer, so
   equal means equal);
3. both pass again against an AddressSanitizer and
   UndefinedBehaviorSanitizer build.

**Selection** is configuration, `engine = "py" | "cpp"`, read at start.
Both engines always ship, so falling back needs no deploy.

## 5. Accounting

### 5.1 Model

One cash pool per participant across all instruments.

### 5.2 State per participant

```python
@dataclass
class ParticipantState:
    team_id: str
    starting_cash: int                 # accounting units
    cash: int                          # realised; changes on fills only
    reserved_cash: int                 # committed by open buys
    positions: dict[str, int]          # net units per instrument
    open_buy_volume: dict[str, int]    # resting buy volume per instrument
    open_sell_volume: dict[str, int]   # resting sell volume per instrument
    open_orders: dict[str, Order]
```

### 5.3 Position limits

Two worst-case bounds, holding at all times:

```
positions[i] + open_buy_volume[i]   <=  +position_limit
positions[i] - open_sell_volume[i]  >=  -position_limit
```

A single net projection (`position + buys - sells`) is not a substitute:
long 10 with 10 open buys and 10 open sells nets to 10, but reaches 20 if
the buys fill first.

Two properties make this cheap:

1. A buy can only breach the long bound and a sell only the short bound,
   so each order is checked against one bound.
2. Both bounded quantities are **invariant under fills** (a buy fill of
   `f` adds `f` to the position and removes `f` from open buys). They
   move only on accept and on cancel. After any sequence of fills, each
   must equal its value before them: that is the test.

### 5.4 Buying power

For buys: `notional <= cash - reserved_cash`.

Short sale proceeds credit cash and so fund later purchases: real
cross-instrument leverage. **This is deliberate.** With both position
bounds binding, risk per instrument is capped for everyone however much
leverage is used, so the leaderboard stays comparable. Participant
documentation states it.

### 5.5 Validation

Runs in the gateway, pre-queue (2.4). Rejected orders never reach the
engine. On receipt:

1. Parse and schema-check (failures are `error`, [`protocol.md`](protocol.md) 9).
2. **Normalise:** round the price to the nearest tick (3.3).
3. **Validate** using the normalised price.
4. Reserve, assign the arrival sequence, enqueue.

Normalising first matters: validating the submitted price and then
rounding up would reserve more cash than was checked.

| Check | Passes when | Reason |
| --- | --- | --- |
| Rate | Within the connection's order-message budget | `rate_limited` |
| Session active | `session.state == RUNNING` | `round_not_active` |
| Instrument known | Configured for this session | `unknown_instrument` |
| Price | `1 <= price_ticks <= MAX_PRICE_TICKS`, after normalising | `invalid_price` |
| Volume | `volume >= lot_size` and `volume % lot_size == 0` | `invalid_volume` |
| Buying power (buys) | `notional <= cash - reserved_cash` | `insufficient_buying_power` |
| Long bound (buys) | `position + open_buy_volume + volume <= limit` | `position_limit_breached` |
| Short bound (sells) | `position - open_sell_volume - volume >= -limit` | `position_limit_breached` |

**Rate limit.** Each connection has a token bucket for order messages
(submits and cancels together), refilled at `max_order_msgs_per_s` from
the round config (default 25) with an equal burst. Over budget, the
message is refused with `rate_limited`; the connection stays open. Bots
have the same budget, since anything else would be a timing tell.

`lot_size` is enforced, not rounded: rounding a volume changes risk.
Phase 1 configs use `lot_size: 1`.

### 5.6 Accounting on events

| Event | Update |
| --- | --- |
| Buy accepted | `reserved_cash += notional`; `open_buy_volume[i] += volume` |
| Sell accepted | `open_sell_volume[i] += volume` |
| Buy fill | `cash -= fill_notional`; `reserved_cash -= order_price_notional`; `positions[i] += f`; `open_buy_volume[i] -= f` |
| Sell fill | `cash += fill_notional`; `positions[i] -= f`; `open_sell_volume[i] -= f` |
| Cancel, IOC remainder, disconnect sweep | Release `reserved_cash` and `open_*_volume` for the remaining volume |
| Round end | Queue drained, all open orders cancelled, reservations released, state locked |

On a buy fill, `cash` falls by the **fill** price and `reserved_cash` by
the **order** price, so price improvement returns to buying power.

### 5.7 The server is the source of truth

Every `fill` carries the participant's cash and full position map after
the fill. The client overwrites its cache from them, so it cannot drift.
Client-side estimates never feed validation.

## 6. Price process

### 6.1 Fair values

Each instrument has a latent fair value. Bots quote around it;
participants cannot see it. Fair values are floats: they never enter the
book, the accounting or the wire. A bot converts fair value to integer
ticks at the moment it quotes.

### 6.2 Market factor

Correlation comes from one shared factor, so each instrument has one
loading instead of a correlation matrix:

```
dS_i = mu_i dt + sigma_i (rho_i dW_market + sqrt(1 - rho_i^2) dW_i)
```

`dW_market` is shared by every instrument in a tick; `dW_i` is
idiosyncratic; `rho_i` is in [-1, 1].

### 6.3 Processes

| Process | Parameters | Use |
| --- | --- | --- |
| GBM | `mu, sigma, rho` | Standard equity |
| GBM with jumps | `mu, sigma, rho, jump_times, jump_sizes` | Scheduled or admin-triggered shocks, news rounds |
| Ornstein-Uhlenbeck | `theta, mu_bar, sigma, rho` | Mean reverting. Market-making rounds and the practice exchange |

### 6.4 Instrument configuration

```python
@dataclass
class InstrumentConfig:
    id: str
    process: Literal["GBM", "GBM_jump", "OU"]
    S0: float                  # starting fair value
    mu: float                  # drift, annualised
    sigma: float               # volatility, annualised
    rho: float                 # market factor loading
    tick_size: float           # exact multiple of 1/10000
    lot_size: int              # 1 in Phase 1
    position_limit: int        # both directions
    jump_times: list[float]    # GBM_jump: seconds since start
    jump_sizes: list[float]    # GBM_jump: fractional, 0.05 = +5%
    theta: float               # OU: reversion speed
    mu_bar: float              # OU: long-run mean
```

### 6.5 Tick rate and secrecy

An asyncio task advances every fair value once a second by
`dt = 1 / 252 / 6.5 / 3600` (one second of trading time, annualised).
Fair values reach bots through in-process shared state. **They are never
sent over the network, in any message, under any condition.**

### 6.6 Staying positive

A fair value at or below zero makes bots quote prices the gateway
rejects, and the market maker silently stops. GBM cannot reach zero;
GBM with a jump `<= -1.0` can; OU can, since it is additive. OU matters
most because the practice exchange runs it for days.

1. Config load rejects any `jump_size <= -1.0`.
2. Config load rejects OU unless `mu_bar - 4 * sigma / sqrt(2 * theta) > 0`
   (four stationary standard deviations above zero).
3. At runtime every fair value is floored at one tick, and **a hit floor
   emits an `admin_event` at `warn`**: a silent floor would turn a config
   error into an unexplained flat market.

## 7. Bots

### 7.1 Architecture

Bots are server-side coroutines using `oqts.aio` over localhost, with the
same protocol, rate limit and team-id namespace as participants. Bot ids
are assigned randomly each session.

**Anonymity.** No flag, field, id pattern or timing characteristic in
any outbound message identifies a bot. The bot-to-id mapping is written
to an admin-only file that is never published
([`operations.md`](operations.md) 2).

### 7.2 Types

| Type | Behaviour |
| --- | --- |
| Market maker | Quotes around fair value, requotes on a schedule, shrinks quotes as inventory grows |
| Trend follower | Trades in the direction of fair value momentum over a lookback window |
| Noise trader | Random limit orders near the book, randomly cancelled |

Implementations and tuned parameters live in the private `oxdaq-ops`;
the runner harness and config loading live here. The interface between
them is agreed before either side is written.

### 7.3 Dry run

Before any live round, all configured bots trade for at least 5 minutes
with no humans. Check: a two-sided market within 30 seconds; spread in
the expected range; no bot at its position limit within 2 minutes; trade
volume above the configured minimum. Re-tune on any failure. **Never run
a live round with untested bot configurations.**

## 8. Invariants

Breaking any of these is a correctness bug.

1. **One queue, one consumer** (2.3).
2. **Check and reserve are atomic**, no `await` between them (2.4).
3. **Server order only:** priority is the arrival sequence (2.3).
4. **Integers inside, decimals at the boundary** (3).
5. **Fill at the resting order's price** (4.3).
6. **Position bounds bind on both sides** and are invariant under fills (5.3).
7. **Fair value never crosses the network**, admin messages included (6.5).
8. **Bots are indistinguishable from participants** (7.1).
9. **The server is the source of truth** for cash and positions (5.7).
10. **Rejected orders never reach the engine** (5.5).
11. **The two engines are equivalent:** exactly equal fills and books (4.5).
12. **Orders belong to their connection** and are swept, through the
    queue, when it closes ([`protocol.md`](protocol.md) 2).
13. **`trade_tick` is never coalesced or dropped** ([`protocol.md`](protocol.md) 7).
14. **In memory only.** The trade tape is the only persistence.
