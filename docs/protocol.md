# The OXDAQ wire protocol

Spec 3.0, 2026-11-19. **Protocol version 2.** The single reference for
the wire format, for anyone writing against OXDAQ directly rather than
through `oqts-client`.

Version 2 added `order_type` (IOC orders), `trade_tick`, the
`rate_limited` reason and cancel on disconnect, and removed the admin
`seed` field ([`decisions.md`](decisions.md) D28 to D32). The schema
implements version 2; cancel on disconnect is server behaviour, built at
milestone 4.

The machine-readable definition is
[`messages.py`](../packages/oqts-client/src/oqts/protocol/messages.py),
and every message is pinned byte for byte in [`tests/golden/`](../tests/golden).
A wire change means: bump `PROTOCOL_VERSION`, change this document in
the same pull request, update `tests/protocol/samples.py`, regenerate the
golden corpus.

## 1. Envelope

WebSocket, JSON, one frame per message. Every message in both directions:

```json
{ "type": "...", "timestamp": 1714300000.123, "seq": 4821 }
```

- `type`: the message discriminator.
- `timestamp`: Unix seconds, millisecond precision. Server-assigned
  outbound; **ignored inbound**. Your clock never affects priority.
- `seq`: increases per connection. **Diagnostic only:** TCP neither drops
  nor reorders within a connection, so a gap means a server bug. Recovery
  from a lost connection is `resync` (5), not `seq`.

## 2. Connecting

```
client connects  ->  wss://oxdaq.oqts.org/ws
client sends     ->  {"type": "auth", "token": "..."}
server replies   ->  {"type": "auth_ok", ...}
server follows   ->  {"type": "state_snapshot", ...}
```

The token goes in the first message, never in the URL (where it would
land in proxy logs and shell history). Anything else while
unauthenticated closes with `4003`; no `auth` within 5 seconds closes
with `4002`; a bad token closes with `4001`.

One team token may hold several connections: a team's algorithm and its
dashboard share one.

**Orders belong to the connection that submitted them.** When a
connection closes, for any reason, the server cancels every order that
connection submitted and releases their reservations, through the order
queue ([`design.md`](design.md) 2.3), then broadcasts the new book.
Closing a dashboard never touches the algorithm's orders. No
`cancel_ack` is sent; the next `state_snapshot` shows the result.

#### `auth_ok`
| Field | Type | Description |
| --- | --- | --- |
| `protocol_version` | int | A client whose version differs must fail loudly at startup |
| `connection_id` | string | Unique per connection. Quoted in support and admin telemetry |
| `team_id` | string | The authenticated identity |
| `display_name` | string | For dashboards |
| `role` | string | `participant` \| `admin` |
| `session_id` | string | The session this connection is attached to |
| `server_time` | float | For clock offset |

**There are exactly two roles, and `bot` is not one.** Team, bot and
practice tokens all grant `participant`; only admin tokens grant
`admin`. With no bot role on the wire, nothing can leak one.

## 3. Client to server

#### `auth`
| Field | Type | Description |
| --- | --- | --- |
| `token` | string | Team, bot, practice or admin token |

#### `submit_order`
| Field | Type | Description |
| --- | --- | --- |
| `client_order_id` | string | Unique per connection per session. Echoed in ack and fills |
| `instrument_id` | string | Configured for this session |
| `side` | string | `"bid"` \| `"ask"` |
| `order_type` | string | `"limit"` \| `"ioc"`. An IOC remainder never rests |
| `price` | float | Limit price. Rounded to the tick on receipt |
| `volume` | int | Positive, a multiple of `lot_size` |

#### `cancel_order`
| Field | Type | Description |
| --- | --- | --- |
| `order_id` | string | From the `order_ack`, not the `client_order_id` |

#### `resync`
No payload. Requests a fresh `state_snapshot`.

## 4. Acknowledgements

#### `order_ack`
| Field | Type | Description |
| --- | --- | --- |
| `order_id` | string | Server-assigned. Use for cancellation |
| `client_order_id` | string | Echoed |
| `instrument_id` | string | Echoed |
| `side` | string | Echoed |
| `price` | float | **After** tick rounding |
| `volume` | int | Echoed |

#### `order_rejected`
| Field | Type | Description |
| --- | --- | --- |
| `client_order_id` | string | Echoed |
| `reason` | string | `insufficient_buying_power` \| `position_limit_breached` \| `round_not_active` \| `unknown_instrument` \| `invalid_volume` \| `invalid_price` \| `rate_limited` |

#### `cancel_ack`
| Field | Type | Description |
| --- | --- | --- |
| `order_id` | string | The cancelled order |
| `instrument_id` | string | For book reconciliation |
| `cancelled_volume` | int | Remaining volume released; zero if it had fully filled |

An IOC whose remainder is cancelled after matching receives an
unprompted `cancel_ack` for it, after its fills. An IOC that fully fills
receives none.

#### `cancel_rejected`
| Field | Type | Description |
| --- | --- | --- |
| `order_id` | string | Echoed |
| `reason` | string | `unknown_order` \| `not_your_order` \| `round_not_active` \| `rate_limited` |

## 5. State

#### `state_snapshot`
Sent after `auth_ok` and on `resync`. This is how a client recovers.

| Field | Type | Description |
| --- | --- | --- |
| `session_id` | string | Current session |
| `session_state` | string | `PENDING` \| `RUNNING` \| `ENDED` |
| `server_time` | float | For clock offset |
| `ends_at` | float \| null | Server time the session ends; null if unbounded |
| `instruments` | array | Instrument config as visible to participants |
| `cash` | float | Authoritative |
| `positions` | object | Authoritative, full map |
| `open_orders` | array | Your resting orders |
| `books` | object | Full book for every instrument |

## 6. Fills

#### `fill`
Sent only to the two counterparties of a match.

| Field | Type | Description |
| --- | --- | --- |
| `order_id` | string | Your filled order |
| `client_order_id` | string | Echoed |
| `instrument_id` | string | |
| `side` | string | Your side |
| `price` | float | Always the resting order's price |
| `volume` | int | Filled in this event; may be partial |
| `remaining_volume` | int | Still resting; zero means done |
| `aggressor` | bool | True if your order was the incoming one |
| `cash` | float | Your cash after this fill. Authoritative |
| `positions` | object | Your full position map after this fill. Authoritative |

## 7. Market data

#### `book_update`
Broadcast after any book change.

| Field | Type | Description |
| --- | --- | --- |
| `instrument_id` | string | Which book |
| `bids` | array | Price descending, `{"price": 99.5, "volume": 40}` aggregated per level |
| `asks` | array | Price ascending, same shape |
| `last_trade_price` | float \| null | Null before the first trade |

A full snapshot, never a delta: simple and self-healing. Under load the
server may coalesce several changes into one update; the latest state is
always sent.

#### `trade_tick`
Broadcast for every match, to every connection. Anonymous: no order, team
or connection id.

| Field | Type | Description |
| --- | --- | --- |
| `instrument_id` | string | |
| `price` | float | Execution price |
| `volume` | int | Traded in this match |
| `aggressor_side` | string | `"bid"` \| `"ask"`: the incoming order's side |

`trade_tick` is never coalesced, so the public tape is complete.

## 8. Session lifecycle

#### `round_started`
| Field | Type | Description |
| --- | --- | --- |
| `round_id` | string | Appears in the trade tape |
| `instruments` | array | `{id, starting_price, tick_size, lot_size}`. Never fair value or process parameters |
| `starting_cash` | float | Same for everyone |
| `position_limit` | int | Per instrument, both directions |
| `duration_s` | float | Planned length |
| `ends_at` | float | Server time it ends |
| `server_time` | float | Server time now |

Clients compute `offset = server_time - local_now` once, then
`remaining = ends_at - (local_now + offset)`, which survives a laptop
with a wrong clock.

#### `news_event`
| Field | Type | Description |
| --- | --- | --- |
| `event_id` | string | Stable, for deduplication across a resync |
| `headline` | string | Admin-authored |
| `affected_instruments` | array | |

The fair value jump is applied server-side and never broadcast.
Interpreting the news and inferring the jump from it and the book is
part of what is being tested ([`design.md`](design.md) 1.1).

#### `round_ended`
| Field | Type | Description |
| --- | --- | --- |
| `round_id` | string | Matches `round_started` |
| `final_cash` | float | |
| `final_positions` | object | |
| `realised_pnl` | float | `final_cash - starting_cash`. Exact cash P&L, not the score: the score adds open positions at the final fair value, computed from the tape after the round ([`operations.md`](operations.md) 1) |

When the admin ends a round, new submissions stop, every order already
queued is processed, all open orders are cancelled, then `round_ended`
is sent.

## 9. Protocol errors

#### `error`
`order_rejected` is a business refusal of a well-formed order. `error`
is a protocol failure: the frame could not be understood, or the sender
was not entitled to send it.

| Field | Type | Description |
| --- | --- | --- |
| `code` | string | `malformed_frame` \| `unknown_message_type` \| `schema_violation` \| `not_authorised` \| `not_admin` \| `internal_error` |
| `message` | string | Safe to display. Never a stack trace |
| `detail` | object \| null | Structured context, such as the offending field |
| `client_order_id` | string \| null | Echoed when recoverable |

**An `error` does not close the connection,** except for authentication
failures (2), and a client sending more than 20 errors in 10 seconds,
which is closed with `4008`.

#### Close codes

| Code | Meaning |
| --- | --- |
| `4001` | Invalid or expired token |
| `4002` | No `auth` within 5 seconds |
| `4003` | Non-`auth` message while unauthenticated |
| `4008` | Protocol error rate exceeded |
| `4009` | Disconnected by the admin |

## 10. Admin protocol

The admin dashboard is an ordinary protocol client; admin capability is
`role == "admin"` in `auth_ok`. Any message here from a `participant`
connection gets `error.code = not_admin` and has no effect.

**The admin never sees fair value either.** No admin message carries a
fair value, a process parameter or a jump size: the admin screen is
often on a projector. `admin_health` gives derived signals instead.

**Serialisation.** `admin_start_round`, `admin_end_round` and
`admin_cancel_team_orders` go through the same order queue as orders, so
"end the round" can never race a fill. `admin_inject_news` changes fair
value, not the book, so it goes to the price process and applies at its
next tick.

Every admin command carries a client-assigned `request_id`, echoed in
`admin_ack` or `admin_rejected`.

### Admin to server

#### `admin_start_round`
| Field | Type | Description |
| --- | --- | --- |
| `round_id` | string | |
| `instruments` | array | Full `InstrumentConfig` each ([`design.md`](design.md) 6.4) |
| `starting_cash` | float | |
| `position_limit` | int | Uniform across instruments |
| `duration_s` | float | |

No seed: the server generates one ([`design.md`](design.md) 6.7). Version
1 had a `seed` field here; version 2 removed it.

#### `admin_end_round`
| Field | Type | Description |
| --- | --- | --- |
| `round_id` | string | Must match the running round |

#### `admin_inject_news`
| Field | Type | Description |
| --- | --- | --- |
| `event_id` | string | Idempotent: a repeat is acknowledged and ignored |
| `headline` | string | |
| `affected_instruments` | array | Broadcast |
| `jumps` | object | `instrument_id` to fractional jump. **Never broadcast** |

#### `admin_practice_control`
| Field | Type | Description |
| --- | --- | --- |
| `action` | string | `pause` \| `resume` \| `reset` |

#### `admin_cancel_team_orders`
| Field | Type | Description |
| --- | --- | --- |
| `team_id` | string | Every resting order of that team is cancelled |

The valve for a runaway algorithm: it stops the damage without
disconnecting the team.

#### `admin_disconnect`
| Field | Type | Description |
| --- | --- | --- |
| `connection_id` | string | Closed with `4009` |
| `reason` | string | Logged and sent in the close frame |

Closing the connection cancels the orders it submitted (2). The team's
other connections keep theirs; `admin_cancel_team_orders` clears all.

### Server to admin

#### `admin_snapshot`
Sent after `auth_ok` for an admin, and on `resync`.

| Field | Type | Description |
| --- | --- | --- |
| `session` | object | `{session_id, session_state, ends_at, round_id, starting_cash, position_limit}` |
| `instruments` | array | Config as run, **less** process parameters and seed |
| `teams` | array | As in `admin_leaderboard` |
| `connections` | array | As in `admin_connections` |

#### `admin_leaderboard`
| Field | Type | Description |
| --- | --- | --- |
| `as_of` | float | Server time computed |
| `entries` | array | `{rank, team_id, display_name, realised_pnl, cash, positions, open_order_count, order_count, fill_count}`, by `realised_pnl` descending |

Reflects every fill, pushed every **250 ms** as a full snapshot.

#### `admin_connections`
| Field | Type | Description |
| --- | --- | --- |
| `connections` | array | `{connection_id, team_id, display_name, role, connected_at, last_seen, orders_submitted, orders_rejected, fills, errors}` |

Same cadence. Bot connections appear here: the one place bots are
visible, which is why admin messages must never reach a participant.

#### `admin_health`
Per-instrument signals with nothing from which fair value could be
recovered.

| Field | Type | Description |
| --- | --- | --- |
| `instrument_id` | string | |
| `best_bid` / `best_ask` | float \| null | Already public |
| `spread_ticks` | int \| null | Null when a side is empty |
| `bid_depth` / `ask_depth` | int | Resting volume per side |
| `trades_last_60s` | int | Activity check |
| `quoting_ok` | bool | A two-sided market for the last 10 seconds |

#### `admin_event`
Append-only operational log.

| Field | Type | Description |
| --- | --- | --- |
| `event_id` | string | Stable, for deduplication |
| `timestamp` | float | |
| `severity` | string | `info` \| `warn` \| `error` |
| `category` | string | `session` \| `connection` \| `order` \| `bot` \| `practice` \| `system` |
| `message` | string | |
| `detail` | object \| null | |

#### `admin_ack`
| Field | Type | Description |
| --- | --- | --- |
| `request_id` | string | Echoed |
| `command` | string | The command acknowledged |
| `detail` | object \| null | Command-specific result |

#### `admin_rejected`
| Field | Type | Description |
| --- | --- | --- |
| `request_id` | string | Echoed |
| `command` | string | Echoed |
| `reason` | string | `round_already_running` \| `no_round_running` \| `round_id_mismatch` \| `unknown_team` \| `unknown_connection` \| `invalid_config` \| `practice_not_running` \| `duplicate_event_id` |

## 11. Things that surprise people

1. **If your connection drops, your resting orders are cancelled.**
   Positions and cash remain. A sleeping laptop stops trading silently,
   so keep it awake during a round.
2. **Prices are snapped to the tick, volumes are not.** A price between
   ticks rounds to the nearest (half up) and the ack echoes it. A volume
   that is not a multiple of the lot size is rejected.
3. **You trade at the resting order's price.** A buy limit above the
   best ask gets price improvement.
4. **Short sale proceeds count toward buying power.** That is real
   leverage, and deliberate; the position limit still caps your risk.
5. **Position limits use the worst case:** your position plus all your
   resting volume on that side. Long 10 with 10 open buys is already at a
   limit of 20.
6. **The server is the only source of truth.** Every `fill` carries your
   cash and full positions; overwrite your state from it.
7. **Order messages are rate limited** (25 a second by default). Over the
   limit you get `rate_limited`, not a disconnection.
8. **The score values open positions at the true fair value**, revealed
   only after the round ([`operations.md`](operations.md) 1). Selling
   short at the bell gains nothing; `realised_pnl` is cash P&L, not the
   score.
