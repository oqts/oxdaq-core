# The OXDAQ wire protocol

**Protocol version 1.** Reference for anyone writing against OXDAQ
directly rather than through `oqts-client`.

The binding specification is `planning/OXDAQ-PLAN.md` section 9. This
document is the readable companion; where they differ, the spec wins.
The machine-readable definition is
[`packages/oqts-client/src/oqts/protocol/messages.py`](../packages/oqts-client/src/oqts/protocol/messages.py),
and every message shape is pinned byte for byte in
[`tests/golden/`](../tests/golden).

## Transport

WebSocket, JSON frames, one frame per message. Every message in both
directions carries the same envelope:

```json
{ "type": "...", "timestamp": 1714300000.123, "seq": 4821 }
```

`seq` is **diagnostic only**. WebSocket runs over TCP, so within a live
connection nothing is dropped or reordered, and a gap can only mean a
server bug. Recovery from a genuinely lost connection is `resync`, not
sequence replay.

`timestamp` is server-assigned outbound and **ignored inbound**. Time
priority is the server's queue arrival order, stamped at enqueue. Your
clock has no effect on where your order sits in the book.

## Connecting

```
you connect  ->  wss://oxdaq.oqts.org/ws
you send     ->  {"type": "auth", "token": "..."}
server sends ->  {"type": "auth_ok", ...}
server sends ->  {"type": "state_snapshot", ...}
```

The token goes in the first message, never in the URL. Any other message
while unauthenticated closes the connection, and so does taking longer
than 5 seconds to send one.

| Close code | Meaning |
| --- | --- |
| 4001 | Invalid or expired token |
| 4002 | No `auth` within 5 seconds |
| 4003 | Sent something other than `auth` while unauthenticated |
| 4008 | More than 20 protocol errors in 10 seconds |
| 4009 | Disconnected by the admin |

A team token may hold several connections at once: your algorithm and
your dashboard share one by design.

## Messages you send

| Type | Purpose |
| --- | --- |
| `auth` | First message. Always |
| `submit_order` | Limit order. `side` is `"bid"` or `"ask"` |
| `cancel_order` | By `order_id` from the `order_ack`, not your `client_order_id` |
| `resync` | Asks for a fresh `state_snapshot` |

## Messages you receive

| Type | Sent to | When |
| --- | --- | --- |
| `auth_ok` | You | After a valid `auth` |
| `state_snapshot` | You | After `auth_ok`, and on `resync` |
| `order_ack` | You | Order accepted. Carries the canonical `order_id` and the tick-rounded price |
| `order_rejected` | You | Order refused. See the reasons below |
| `cancel_ack` | You | Cancel applied. `cancelled_volume` is what was released |
| `cancel_rejected` | You | Cancel refused |
| `fill` | Both counterparties | A trade happened. Carries your authoritative cash and full position map |
| `book_update` | Everyone | Any book change. A full snapshot, never a delta |
| `round_started` | Everyone | Round begins |
| `news_event` | Everyone | A headline. No magnitude: inferring it is the point |
| `round_ended` | Everyone | Round over, with your final figures |
| `error` | You | A frame the server could not understand |

### Rejection reasons

`order_rejected.reason` is one of `insufficient_buying_power`,
`position_limit_breached`, `round_not_active`, `unknown_instrument`,
`invalid_volume`, `invalid_price`.

`cancel_rejected.reason` is one of `unknown_order`, `not_your_order`,
`round_not_active`.

`error` is a different thing: it means the frame itself was wrong, not
that a well-formed request was refused. It does not close your
connection.

## Six things that surprise people

**1. Your resting orders survive a disconnection.** There is no
cancel-on-disconnect. An order you placed keeps resting in the book and
can fill while your process is disconnected, asleep, or dead. This
matches real venue behaviour, and on the practice exchange it means an
algorithm you killed last night may have traded overnight. **Set your
machine not to sleep during a round.**

**2. Prices are snapped to the tick, not rejected.** A price between
ticks is rounded to the nearest one, half rounding up, and the
`order_ack` echoes the canonical price. Volumes are *not* rounded: a
volume that is not a multiple of the lot size is rejected outright,
because changing a volume changes your risk.

**3. You are filled at the resting order's price, never yours.** Buy with
a limit above the best ask and you get price improvement, at the maker's
limit.

**4. Short sale proceeds count toward your buying power.** Selling short
credits cash immediately, and that cash can fund a purchase in another
instrument. This is real leverage and it is deliberate. Your total risk
is still capped, because the position limit binds on both sides.

**5. Position limits are checked against the worst case.** The bound is
your position plus *all* your resting volume on that side, not your
current position. Long 10 with 10 open buys is already at a limit of 20.

**6. The server is the only source of truth.** Every `fill` carries your
cash and your entire position map after that fill. Overwrite your local
state from it. If your bookkeeping and the server's disagree, you are
wrong.

## Scoring

Realised P&L only: `final_cash - starting_cash`. Open positions are not
marked to market in Phase 1, so a large open position at the bell is
worth nothing to you.

Cash is held server-side as an exact integer count of 1/10000 of a
currency unit, so the scoring figure is reproducible exactly from the
trade tape.
