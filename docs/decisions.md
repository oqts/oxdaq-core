# OXDAQ decisions

Spec 3.0, 2026-11-19. Every design decision that shaped the spec, oldest
first. The other documents describe the current design only; this is
where the history lives. A new decision gets the next number and a row
here, in the same pull request as the change it makes.

| # | Date | Problem | Decision | Shapes |
| --- | --- | --- | --- | --- |
| D1 | 2026-08-28 | Position limit checked on sells only, so longs were bounded by cash alone | Two worst-case bounds, each order checked against the one its side can breach | design 5.3 |
| D2 | 2026-08-28 | `lot_size` in the protocol but not validated | Enforced, rejected as `invalid_volume`; Phase 1 uses lot size 1 | design 5.5 |
| D3 | 2026-08-28 | `reserved_short` defined inconsistently with how it was updated | Replaced by unconditional `open_buy_volume` and `open_sell_volume` | design 5.2 |
| D4 | 2026-08-28 | Unclear whether buying power checks the submitted or rounded price | Normalise, then validate, then reserve and enqueue | design 5.5 |
| D5 | 2026-08-28 | `round_started` had no duration, yet the dashboard showed a countdown | `duration_s`, `ends_at`, `server_time`; client corrects clock skew | protocol 8 |
| D6 | 2026-08-28 | The trade tape, the only persistence, had no schema | Six-file CSV bundle, exact decimal strings, order flow and bot mapping confidential | operations 2 |
| D7 | 2026-08-28 | Tokens in the URL query string | First-message `auth` frame, 5 second deadline, defined close codes | protocol 2 |
| D8 | 2026-08-28 | Short proceeds create undocumented leverage | Permitted and documented; safe because D1 caps risk on both sides | design 5.4 |
| D9 | 2026-08-28 | `seq` gap detection with no recovery, and no reconnection story | `seq` diagnostic only; `resync` and `state_snapshot` for recovery | protocol 1, 5 |
| D10 | 2026-08-28 | Float prices and cash deciding a leaderboard | Integer ticks and accounting units inside, decimals at the boundary | design 3 |
| D11 | 2026-08-28 | No price positivity check; a negative buy price manufactured buying power | `price_ticks >= 1` after normalising (`invalid_price`); fair value floored, configs guarded | design 5.5, 6.6 |
| D12 | 2026-08-28 | The admin dashboard was a protocol client with no admin messages | Admin protocol, an `admin` role, mutating commands through the order queue | protocol 10 |
| D13 | 2026-08-28 | A malformed frame had no defined response | `error`, distinct from `order_rejected`, non-closing, rate limited (`4008`) | protocol 9 |
| D14 | 2026-08-28 | `auth_ok` fields unspecified | Seven fields, including `protocol_version` and exactly two roles | protocol 2 |
| D15 | 2026-08-28 | No decision on how wire models are written | Pydantic v2 at the boundary, dataclasses inside, joined in the codec | build 2.1 |
| D16 | 2026-08-28 | A full sorted leaderboard pushed per fill | Reflects every fill, pushed every 250 ms as a full snapshot | protocol 10 |
| D17 | 2026-08-28 | The schema freeze was unenforced | `PROTOCOL_VERSION` and a golden corpus compared byte for byte in CI | build 2.1 |
| D18 | 2026-08-28 | `price_ticks * tick_size` rounds twice; round trip had no stated domain | Integer multiply then one rounded divide; `MAX_PRICE_TICKS = 2**48` | design 3.3 |
| D19 | 2026-11-19 | What moves to C++ | The matching engine only. Accounting stays Python beside the check-and-reserve invariant; everything else stays Python | design 4.5, build 5 |
| D20 | 2026-11-19 | Where the C++/Python boundary sits | In process: a pure C++ library and a nanobind module, called by the single consumer with the GIL held | design 4.5 |
| D21 | 2026-11-19 | Whether a Python engine survives | Yes, permanently: built first, then oracle and live fallback, selected by `engine = "py" \| "cpp"` | design 4.5 |
| D22 | 2026-11-19 | When the C++ engine may run live | The equivalence gate (shared suite, exact differential test, both under sanitizers) plus a 72 hour practice soak | design 4.5, operations 6 |
| D23 | 2026-11-19 | C++ toolchain | C++20, CMake presets, scikit-build-core, nanobind, GoogleTest, Google Benchmark, sanitizers, libFuzzer, in `packages/oxdaq-engine` | build 2.2 |
| D24 | 2026-11-19 | Build schedule | Engine track E1 and E2 alongside milestones 3 to 12; `book_update` coalescing in milestone 4 | build 4 |
| D25 | 2026-11-19 | Time priority on a float timestamp, hard to mirror exactly in C++ | An integer arrival sequence assigned at enqueue; the timestamp stays for the tape | design 2.3, 4.2 |
| D26 | 2026-11-19 | String ids inside the engine | Integer ids in both engines, mapped by the session manager | design 4.2, 4.5 |
| D27 | 2026-11-19 | Callback client: inverted control flow, no notebooks, no cancel before the ack | A synchronous `Exchange` on the Optibook model, over `oqts.aio` on a background thread | client 2, 3 |
| D28 | 2026-11-19 | Limit orders only, so taking liquidity meant submit then cancel | IOC orders; the remainder reported by an unprompted `cancel_ack` | design 4.1, protocol 3, 4 |
| D29 | 2026-11-19 | Orders survived disconnection, so a sleeping laptop traded blind | Orders belong to their connection and are swept through the queue when it closes | design 2.3, protocol 2, client 4 |
| D30 | 2026-11-19 | Nothing bounded one connection's order rate | Token bucket, default 25 a second, `rate_limited` without disconnecting; bots included | design 5.5 |
| D31 | 2026-11-19 | The old client promised public trades that no message carried | `trade_tick` for every match, anonymous, never coalesced | protocol 7 |
| D32 | 2026-11-19 | The admin chose the seed, and the public generator replays any known seed | The server generates every seed from a secure source, never derived, supplied or reused, revealed only in the tape after the session | design 6.7, protocol 10 |
| D33 | 2026-11-19 | No rule for bug exploitation, reporting or latency in a public-code competition | A fair-play section: exploits disqualify and the round is rescored from the tape, reports earn credit, latency is allowed | operations 7 |

D1 to D10 resolved problems in the first draft of the spec; D11 to D18
were found while writing the milestone 1 schema; D19 to D31 came from
the November 2026 replanning that added the C++ engine and redesigned
the client; D32 and D33 from a review of what the public spec reveals.
