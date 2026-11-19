# Running OXDAQ

Spec 3.0, 2026-11-19. Scoring, the trade tape, tokens, dashboards, the
practice exchange, and what must be true before a live round.

## 1. Scoring

### 1.1 The score

**Open positions are valued at the true price, revealed after the
round:**

```
score = final_cash - starting_cash + sum_i positions[i] * final_fair_value[i]
```

`final_fair_value[i]` is the instrument's fair value at the round's
last price process tick, rounded once to the nearest tick and written to
the tape (2). It never depends on a thin or unstable mid, and a position
opened in the last second is worth exactly what it is worth, so selling
short at the bell gains nothing. Every term is an exact integer
([`design.md`](design.md) 3), so the score is exactly reproducible from
the tape.

During a round only cash P&L is known (`round_ended.realised_pnl`, the
live leaderboard); the score is computed from the tape after the round
and announced then. Whether to add a penalty for risk or leftover
inventory is open ([`design.md`](design.md) 1.2).

### 1.2 Rounds and events

A competition event runs **several short rounds**, so luck averages
out, each a session with its own seed and parameter draw. An event
follows the curriculum ([`design.md`](design.md) 1.1): market making,
market making against informed traders, relative value, news, then a
mixed final round. Results are reported **per round type and per
instrument** as well as overall, so different styles visibly win in
different places.

## 2. Trade tape

The only persistence, and the artefact rounds are scored from. One
directory per round, written at round end.

```
tape/<round_id>/
    trades.csv          one row per trade
    participants.csv    starting and final state per team
    instruments.json    the round config exactly as run, with the seed,
                        the bot parameter draw and final fair values
    news.csv            headlines and the jump actually applied
    orders.csv          every order and its outcome      [confidential]
    bots.csv            bot to team_id mapping           [admin only]
```

Numeric columns are **exact decimal strings**, never floats.

| File | Columns |
| --- | --- |
| `trades.csv` | `round_id, seq, timestamp, instrument_id, price, volume, aggressor_team_id, resting_team_id, aggressor_side` |
| `participants.csv` | `round_id, team_id, starting_cash, final_cash, realised_pnl, final_positions` (JSON map), `score` (1.1) |
| `instruments.json` | Full `InstrumentConfig` per instrument, process parameters and RNG seed included; `final_fair_value` per instrument; the bot parameters drawn ([`design.md`](design.md) 7.4) |
| `news.csv` | `event_id, timestamp, headline, affected_instruments, jump_applied` |
| `orders.csv` | `order_id, client_order_id, team_id, instrument_id, side, order_type, price, volume, submitted_at, outcome, filled_volume` |
| `bots.csv` | `team_id, bot_type, parameter_set_id` |

Without the parameters and seed in `instruments.json`, nobody can tell
afterwards whether a strategy was skilled or lucky, and the round cannot
be replayed.

**Confidentiality.**

1. `orders.csv` is every participant's full order flow, so their
   strategy. It is kept for society analysis and research use and
   **stripped from anything given to a sponsor or published**.
2. `bots.csv` is **never published**. Bot rows stay unlabelled in
   `trades.csv`; publishing the mapping would break bot anonymity for
   every later round using the same bots.

**Published as research data.** After an event, each round's
`trades.csv`, `instruments.json` and `news.csv` are published to members
as a dataset, with team ids replaced by per-round pseudonyms. This is
where signal research happens ([`design.md`](design.md) 1.1): members
study past rounds offline, and the next live round tests their ideas on
data they have not seen. Publishing parameter draws reveals the bot
distributions over time, which is acceptable: the edge is meant to come
from the market, not from knowing the bots.

## 3. Tokens

### 3.1 Model

Every connection authenticates with a bearer token in its first message
([`protocol.md`](protocol.md) 2): cryptographically random, URL-safe,
at least 32 bytes.

| Token | Scope | Lifetime |
| --- | --- | --- |
| Team | One team's state; shared by its algorithm and dashboard | One competition event |
| Bot | One bot instance | One session |
| Admin | Leaderboard and round control | One event, rotated |
| Practice | One member's practice state | Persistent, revocable |

Team and practice tokens are issued from the society's member records:
one list of humans, the same one the web app keeps.

### 3.2 Distribution

Team tokens are generated just before the round and handed over so they
cannot be intercepted or shared: on a projector in the room, or privately
to each team's contact. **Never email tokens in advance.** Members fetch
practice tokens themselves from the web app.

## 4. Dashboards

One web app with two views, deployed with OXDAQ behind Caddy. Each view
opens its own WebSocket and uses the protocol like any client. Styling
comes from `oqts-design`; no hex value is hand-coded.

### 4.1 Student view

| Panel | Updates on |
| --- | --- |
| Cash P&L (`cash - starting_cash`), labelled as not the score (1.1) | Every fill |
| Positions, with average entry price | Every fill |
| Cash | Every fill |
| Round timer, from `ends_at` and the clock offset | Every second |
| News feed | `news_event` |

### 4.2 Admin view

| Panel | Description |
| --- | --- |
| Leaderboard | All teams by cash P&L, every 250 ms. Indicative: the score comes from the tape (1.1) |
| Round controls | Start with config, end, inject news |
| Connections | Teams and bots, connection time, order counts |
| Practice controls | Pause, resume, reset |

### 4.3 Design

`oqts-design/brand.md` governs. A dashboard subsection of it (tabular
density, live numeric cells, status) is planned. Figures in Latin Modern
Mono with tabular numerals; the sign of a number is never carried by hue
alone.

## 5. Practice exchange

### 5.1 What it is

Always up, so members can develop and test whenever they like. A
long-lived session (`RUNNING`, `ends_at == null`) in a **separate process
and container** from the competition exchange, sharing no event loop,
port or state, so nothing in practice can touch a live round.

### 5.2 Parameters (provisional, to confirm before milestone 11)

| Parameter | Value | Why |
| --- | --- | --- |
| Reset | Daily, 04:00 UK | Bounds memory, writes a tape, clean start |
| Bots | A separate practice parameter set | The competition bots must not be reverse-engineered in advance |
| Instruments | Competition-like, a fresh seed at every reset ([`design.md`](design.md) 6.7) | Practice should transfer; exact configs should not |
| Leaderboard | Not shown | Practice is for experiments |
| During a live round | Paused | Frees resources on the day |
| Price process | Ornstein-Uhlenbeck | Stays in range over days, where GBM wanders |

### 5.3 For participants

An algorithm left running keeps trading until the daily reset. One that
dies or sleeps loses its resting orders when its connection drops;
positions remain until the reset.

## 6. Before the first live round

Milestones 1 to 12 complete ([`build.md`](build.md) 4), plus:

- Token distribution plan confirmed.
- Bot dry run passed on the exact configuration ([`design.md`](design.md) 7.3).
- At least one participant has run a test algorithm from their own
  machine against the server.
- If running the C++ engine: E1 done, and the practice exchange has run
  on `engine = "cpp"` for 72 hours without fault. The reference engine
  stays selectable.
- **Participant laptops set not to sleep.** A sleeping laptop loses its
  orders and stops trading silently: still the most likely failure on
  the day.

## 7. Fair play

The engine, protocol and client are public so that every competitor
reads the same rules. What decides a round stays private: fair values,
process parameters and seeds, bot code and parameters, the news
schedule, and which counterparties are bots. These rules go in the
participant documentation and are read out before every round.

- **Anything through the protocol is fair.** The market is built so
  that studying it (the book, the flow, the news, the links between
  instruments) pays, and studying the bots does not: their parameters
  are redrawn every round ([`design.md`](design.md) 1.1).
- **Exploiting a bug is not.** A strategy that profits from behaviour
  contrary to these documents (a validation hole, an accounting error, a
  leak) is disqualified from the round, and the round is rescored from
  the trade tape without the exploited trades.
- **Reporting a bug earns credit.** Tell the organisers privately; it is
  fixed and the reporter acknowledged. Reports during a round are acted
  on after it.
- **Leave the infrastructure alone.** No attempts at other teams' tokens,
  admin access, or loading the server beyond the rate limit.
- **Latency is part of the game.** Participants run their strategies
  wherever they like, including a server near the exchange. The server's
  location is not a secret.

The tape makes all of this checkable: every order, fill and the seed are
recorded, so any result can be recomputed after the round.
