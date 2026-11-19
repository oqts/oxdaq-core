"""The OXDAQ wire protocol. docs/protocol.md.

Every message that crosses the network, in both directions, is defined
here and nowhere else. This module is **frozen**: adding, removing,
renaming or retyping a field is a protocol change, which means bumping
``PROTOCOL_VERSION``, regenerating the golden corpus under
``tests/golden/``, and updating ``docs/protocol.md`` in the same
change set (build.md 2.1).

Pydantic at the boundary, plain dataclasses inside (build.md 2.1, D15).
Validation belongs here and nowhere else: by the time a message reaches
the session manager it is already known to be well-formed, and by the
time it reaches the matching engine it is already known to be legal.

Prices and cash appear here as ``float``, because that is what a
participant sees. The conversion to and from integer ticks and accounting
units happens in ``oxdaq.units`` and nowhere else (design.md 3.3).
"""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    AdminAction,
    AdminEventCategory,
    AdminRejectReason,
    AdminSeverity,
    CancelRejectReason,
    ErrorCode,
    OrderType,
    PracticeAction,
    RejectReason,
    Role,
    SessionState,
    Side,
)

PROTOCOL_VERSION: Final[int] = 2
"""Sent in ``auth_ok``. A client whose version differs must fail loudly at
startup rather than degrade silently (protocol.md 2)."""


class _Message(BaseModel):
    """Envelope common to every message in both directions. protocol.md 1."""

    model_config = ConfigDict(
        extra="forbid",  # an unknown field is a schema violation, not a courtesy
        frozen=True,
        use_enum_values=False,
        validate_assignment=True,
    )

    timestamp: float = Field(
        description="Unix seconds, millisecond precision. Server-assigned "
        "outbound. Ignored for ordering inbound: time priority is server "
        "enqueue order (design.md 2.3)."
    )
    seq: int = Field(
        ge=0,
        description="Monotonic per connection. Diagnostic only: WebSocket "
        "runs over TCP, so a gap can only mean a server bug. Recovery from "
        "a lost connection is `resync`, not seq replay (protocol.md 1).",
    )


# ---------------------------------------------------------------------------
# Shared value objects
# ---------------------------------------------------------------------------

Price = Annotated[float, Field(gt=0.0)]
Volume = Annotated[int, Field(gt=0)]
InstrumentId = Annotated[str, Field(min_length=1, max_length=64)]
TeamId = Annotated[str, Field(min_length=1, max_length=64)]
OrderId = Annotated[str, Field(min_length=1, max_length=64)]
ClientOrderId = Annotated[str, Field(min_length=1, max_length=64)]


class _Value(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BookLevel(_Value):
    """One aggregated price level. protocol.md 7."""

    price: Price
    volume: Volume


class BookSnapshot(_Value):
    """One instrument's full book. protocol.md 7.

    A full snapshot, never a delta: simpler to implement and to consume,
    self-healing, and negligible at 20 to 80 participants.
    """

    bids: list[BookLevel] = Field(description="Descending price")
    asks: list[BookLevel] = Field(description="Ascending price")
    last_trade_price: float | None = Field(
        default=None, description="Null before the first trade"
    )


class OpenOrder(_Value):
    """A resting order of yours, as it appears in `state_snapshot`. protocol.md 5."""

    order_id: OrderId
    client_order_id: ClientOrderId
    instrument_id: InstrumentId
    side: Side
    price: Price
    volume: Volume
    remaining_volume: int = Field(ge=0)


class InstrumentPublic(_Value):
    """Instrument config as visible to participants. protocol.md 8.

    Fair value and process parameters are **never** exposed. This model is
    the reason invariant 7 survives: there is no field here to put them in.
    """

    id: InstrumentId
    starting_price: Price
    tick_size: float = Field(gt=0.0)
    lot_size: int = Field(gt=0)


# ---------------------------------------------------------------------------
# Client to server. protocol.md 3
# ---------------------------------------------------------------------------


class Auth(_Message):
    """First message on every connection. protocol.md 2.

    Tokens never appear in the URL: that would place them in Caddy access
    logs, proxy logs, browser history and shell history, and the student
    dashboard displays them in a room (D7).
    """

    type: Literal["auth"] = "auth"
    token: str = Field(min_length=1, max_length=512)


class SubmitOrder(_Message):
    type: Literal["submit_order"] = "submit_order"
    client_order_id: ClientOrderId
    instrument_id: InstrumentId
    side: Side
    order_type: OrderType = Field(
        description="limit or ioc. An IOC remainder never rests (design.md 4.1)"
    )
    price: Price = Field(description="Limit price. Rounded to the tick on receipt")
    volume: Volume


class CancelOrder(_Message):
    type: Literal["cancel_order"] = "cancel_order"
    order_id: OrderId = Field(
        description="Server-assigned ID from the order_ack, not the client_order_id"
    )


class Resync(_Message):
    """Requests a full `state_snapshot`. protocol.md 3."""

    type: Literal["resync"] = "resync"


# ---------------------------------------------------------------------------
# Server to client: acknowledgements. protocol.md 4
# ---------------------------------------------------------------------------


class AuthOk(_Message):
    """protocol.md 2."""

    type: Literal["auth_ok"] = "auth_ok"
    protocol_version: int
    connection_id: str = Field(min_length=1, max_length=64)
    team_id: TeamId
    display_name: str = Field(min_length=1, max_length=128)
    role: Role
    session_id: str = Field(min_length=1, max_length=64)
    server_time: float


class OrderAck(_Message):
    type: Literal["order_ack"] = "order_ack"
    order_id: OrderId = Field(description="Canonical. Use this to cancel")
    client_order_id: ClientOrderId
    instrument_id: InstrumentId
    side: Side
    price: Price = Field(description="After tick rounding. The canonical price")
    volume: Volume


class OrderRejected(_Message):
    type: Literal["order_rejected"] = "order_rejected"
    client_order_id: ClientOrderId
    reason: RejectReason


class CancelAck(_Message):
    """protocol.md 4. Also sent unprompted for an IOC remainder, after its fills."""

    type: Literal["cancel_ack"] = "cancel_ack"
    order_id: OrderId
    instrument_id: InstrumentId
    cancelled_volume: int = Field(
        ge=0, description="Remaining volume released. Zero if it had fully filled"
    )


class CancelRejected(_Message):
    type: Literal["cancel_rejected"] = "cancel_rejected"
    order_id: OrderId
    reason: CancelRejectReason


# ---------------------------------------------------------------------------
# Server to client: state. protocol.md 5
# ---------------------------------------------------------------------------


class StateSnapshot(_Message):
    """Sent after `auth_ok` and on `resync`. The reconnection mechanism.

    protocol.md 5. On reconnect the client rebuilds its cache from this
    authoritative state rather than assuming anything survived.
    """

    type: Literal["state_snapshot"] = "state_snapshot"
    session_id: str
    session_state: SessionState
    server_time: float
    ends_at: float | None = Field(default=None, description="Null if unbounded")
    instruments: list[InstrumentPublic]
    cash: float
    positions: dict[str, int]
    open_orders: list[OpenOrder]
    books: dict[str, BookSnapshot]


# ---------------------------------------------------------------------------
# Server to client: fills. protocol.md 6
# ---------------------------------------------------------------------------


class Fill(_Message):
    """Sent only to the two counterparties of a trade. protocol.md 6.

    Carries authoritative `cash` and the **full** position map. The client
    overwrites its cache from these, so client state self-corrects on every
    fill and cannot permanently diverge, even if a participant's algorithm
    mishandles an event (design.md 5.7).
    """

    type: Literal["fill"] = "fill"
    order_id: OrderId
    client_order_id: ClientOrderId
    instrument_id: InstrumentId
    side: Side
    price: Price = Field(description="Always the resting order's price (design.md 4.3)")
    volume: Volume = Field(description="Units filled in this event. May be partial")
    remaining_volume: int = Field(ge=0)
    aggressor: bool
    cash: float = Field(description="Your cash after this fill. Authoritative")
    positions: dict[str, int] = Field(description="Full map after this fill")


# ---------------------------------------------------------------------------
# Server to all: market data. protocol.md 7
# ---------------------------------------------------------------------------


class BookUpdate(_Message):
    type: Literal["book_update"] = "book_update"
    instrument_id: InstrumentId
    bids: list[BookLevel]
    asks: list[BookLevel]
    last_trade_price: float | None = None


class TradeTick(_Message):
    """One match, broadcast to every connection. protocol.md 7, D31.

    Anonymous: no order, team or connection id, so it cannot identify a
    bot (invariant 8). Never coalesced or dropped (invariant 13), so the
    public tape is complete.
    """

    type: Literal["trade_tick"] = "trade_tick"
    instrument_id: InstrumentId
    price: Price = Field(description="Execution price: the resting order's")
    volume: Volume = Field(description="Traded in this match")
    aggressor_side: Side = Field(description="The incoming order's side")


# ---------------------------------------------------------------------------
# Server to all: session lifecycle. protocol.md 8
# ---------------------------------------------------------------------------


class RoundStarted(_Message):
    type: Literal["round_started"] = "round_started"
    round_id: str
    instruments: list[InstrumentPublic]
    starting_cash: float
    position_limit: int = Field(gt=0)
    duration_s: float = Field(gt=0.0)
    ends_at: float
    server_time: float = Field(
        description="The client computes its clock offset once as "
        "server_time - local_now, then remaining = ends_at - (local_now + "
        "offset). Corrects for a participant laptop whose clock is wrong."
    )


class NewsEvent(_Message):
    """protocol.md 8.

    Information asymmetry is the point. The fair value jump is applied
    server-side and never broadcast: participants get the headline and the
    affected instruments, and inferring the magnitude from book dynamics
    is the skill being tested. There is deliberately no magnitude field.
    """

    type: Literal["news_event"] = "news_event"
    event_id: str = Field(description="Stable, for deduplication across a resync")
    headline: str = Field(min_length=1, max_length=512)
    affected_instruments: list[str]


class RoundEnded(_Message):
    type: Literal["round_ended"] = "round_ended"
    round_id: str
    final_cash: float
    final_positions: dict[str, int]
    realised_pnl: float = Field(
        description="final_cash - starting_cash. Authoritative for scoring"
    )


# ---------------------------------------------------------------------------
# Server to client: protocol errors. protocol.md 9
# ---------------------------------------------------------------------------


class Error(_Message):
    """A frame that could not be understood, or was not permitted. protocol.md 9.

    Not to be confused with `order_rejected`, which is a *business*
    rejection of a well-formed order. This does not close the connection:
    a strategy that emits one malformed frame nineteen minutes into a
    twenty minute round should get a diagnostic, not a disconnection.
    """

    type: Literal["error"] = "error"
    code: ErrorCode
    message: str = Field(
        min_length=1,
        max_length=512,
        description="Safe to display. Never a stack trace or server internal",
    )
    detail: dict[str, object] | None = None
    client_order_id: str | None = Field(
        default=None,
        description="Echoed when the frame parsed far enough to recover it",
    )


# ---------------------------------------------------------------------------
# Admin protocol. protocol.md 10
#
# Admin capability is carried entirely by role == "admin" in auth_ok. Any
# of these sent from a participant connection is answered with
# error.code = not_admin and has no effect.
#
# Invariant 7 binds the admin too: nothing here carries a latent fair
# value, a process parameter, or a news jump magnitude. The admin
# dashboard runs in a browser, in a room, frequently on a projector, and
# the whole round turns on whether participants can infer fair value.
# ---------------------------------------------------------------------------


class _AdminCommand(_Message):
    """Common to every admin client-to-server message. protocol.md 10."""

    request_id: str = Field(
        min_length=1, max_length=64, description="Echoed in admin_ack/admin_rejected"
    )


class InstrumentConfigWire(_Value):
    """Full instrument config, admin to server only. design.md 6.4.

    This is the one place process parameters cross the network, and the
    direction is inbound: the admin is configuring the round. Nothing
    server-to-client ever echoes these fields back, which is why
    `admin_snapshot.instruments` carries `InstrumentPublic` instead.

    `tick_size` is a **string**, deliberately. A float cannot represent
    0.01, and the design.md 3.2 check that a tick is an exact multiple of
    1/10000 is unreliable against one: 0.07 is a legal tick that the naive
    float check rejects, because 0.07 * 10_000 is 700.0000000000001.
    """

    id: InstrumentId
    process: Literal["GBM", "GBM_jump", "OU"]
    s0: float = Field(gt=0.0, description="Starting fair value")
    mu: float = Field(description="Drift, annualised")
    sigma: float = Field(ge=0.0, description="Volatility, annualised")
    rho: float = Field(ge=-1.0, le=1.0, description="Market factor loading")
    tick_size: str = Field(description="Exact decimal string, multiple of 1/10000")
    lot_size: int = Field(gt=0)
    position_limit: int = Field(gt=0)
    # GBM_jump only
    jump_times: list[float] = Field(
        default_factory=list, description="Seconds since session start"
    )
    jump_sizes: list[float] = Field(
        default_factory=list, description="Fractional. Must be > -1.0 (design.md 6.6)"
    )
    # OU only
    theta: float | None = Field(default=None, description="Mean reversion speed")
    mu_bar: float | None = Field(default=None, description="Long run mean")


class AdminStartRound(_AdminCommand):
    type: Literal["admin_start_round"] = "admin_start_round"
    round_id: str = Field(min_length=1, max_length=64)
    instruments: list[InstrumentConfigWire] = Field(min_length=1)
    starting_cash: float = Field(gt=0.0)
    position_limit: int = Field(gt=0)
    duration_s: float = Field(gt=0.0)
    # No seed: the server generates one from a secure source (design.md 6.7,
    # D32). An admin-supplied seed would let whoever chose it replay the
    # round's fair values.


class AdminEndRound(_AdminCommand):
    type: Literal["admin_end_round"] = "admin_end_round"
    round_id: str = Field(description="Must match the running round")


class AdminInjectNews(_AdminCommand):
    type: Literal["admin_inject_news"] = "admin_inject_news"
    event_id: str = Field(min_length=1, max_length=64)
    headline: str = Field(min_length=1, max_length=512)
    affected_instruments: list[str]
    jumps: dict[str, float] = Field(
        default_factory=dict,
        description="instrument_id -> fractional jump. Applied server-side, "
        "NEVER broadcast. Values must be > -1.0 (design.md 6.6).",
    )


class AdminPracticeControl(_AdminCommand):
    type: Literal["admin_practice_control"] = "admin_practice_control"
    action: PracticeAction


class AdminCancelTeamOrders(_AdminCommand):
    """The operational valve for a runaway algorithm. protocol.md 10.

    Stops the damage without disconnecting the team, so they can fix and
    continue. Routed through the order queue, so the cancels take their
    place in sequence like any other.
    """

    type: Literal["admin_cancel_team_orders"] = "admin_cancel_team_orders"
    team_id: TeamId


class AdminDisconnect(_AdminCommand):
    """Closes one connection with code 4009. protocol.md 10.

    Closing the connection sweeps its resting orders through the queue
    (protocol.md 2, D29). The team's other connections keep theirs:
    `admin_cancel_team_orders` clears all.
    """

    type: Literal["admin_disconnect"] = "admin_disconnect"
    connection_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=256)


class TeamRow(_Value):
    """One team's state, for the leaderboard and the admin snapshot."""

    rank: int = Field(ge=1)
    team_id: TeamId
    display_name: str
    realised_pnl: float
    cash: float
    positions: dict[str, int]
    open_order_count: int = Field(ge=0)
    order_count: int = Field(ge=0)
    fill_count: int = Field(ge=0)


class ConnectionRow(_Value):
    """One connection. Admin only.

    This is the single place bots are visible, which is exactly why
    `admin_*` must never be reachable with a participant token
    (invariant 8).
    """

    connection_id: str
    team_id: TeamId
    display_name: str
    role: Role
    connected_at: float
    last_seen: float
    orders_submitted: int = Field(ge=0)
    orders_rejected: int = Field(ge=0)
    fills: int = Field(ge=0)
    errors: int = Field(ge=0)


class AdminSessionInfo(_Value):
    session_id: str
    session_state: SessionState
    ends_at: float | None = None
    round_id: str | None = None
    starting_cash: float | None = None
    position_limit: int | None = None


class AdminSnapshot(_Message):
    """The admin equivalent of `state_snapshot`. protocol.md 10.

    `instruments` is `InstrumentPublic`, not `InstrumentConfigWire`: the
    process parameters the admin sent in are deliberately not echoed back
    to a browser, and the server-generated seed never leaves the server
    during a session (design.md 6.7).
    """

    type: Literal["admin_snapshot"] = "admin_snapshot"
    session: AdminSessionInfo
    instruments: list[InstrumentPublic]
    teams: list[TeamRow]
    connections: list[ConnectionRow]


class AdminLeaderboard(_Message):
    """protocol.md 10.

    Reflects every fill, pushed on a 250 ms cadence, coalescing everything
    in between. A full sorted table per fill at 80 participants is a large
    multiple of the useful update rate, and no human reads a leaderboard
    faster than 4 Hz. Nothing is lost: this is a full snapshot, so the next
    push carries the net effect of every fill since the last (D16).
    """

    type: Literal["admin_leaderboard"] = "admin_leaderboard"
    as_of: float
    entries: list[TeamRow] = Field(description="Sorted by realised_pnl descending")


class AdminConnections(_Message):
    type: Literal["admin_connections"] = "admin_connections"
    connections: list[ConnectionRow]


class AdminHealth(_Message):
    """Derived per-instrument operational signals. protocol.md 10.

    Contains no fair value and nothing from which one could be recovered.
    `quoting_ok` is what replaces "show me the fair value next to the mid":
    it answers the operational question, which is whether the market maker
    is alive and quoting, and it is a boolean, so it cannot be inverted
    into a price.
    """

    type: Literal["admin_health"] = "admin_health"
    instrument_id: InstrumentId
    best_bid: float | None = None
    best_ask: float | None = None
    spread_ticks: int | None = Field(
        default=None, description="Null when either side is empty"
    )
    bid_depth: int = Field(ge=0)
    ask_depth: int = Field(ge=0)
    trades_last_60s: int = Field(ge=0)
    quoting_ok: bool = Field(
        description="Two-sided market continuously present for the last 10 seconds"
    )


class AdminEvent(_Message):
    """Append-only operational log. protocol.md 10."""

    type: Literal["admin_event"] = "admin_event"
    event_id: str
    severity: AdminSeverity
    category: AdminEventCategory
    message: str = Field(min_length=1, max_length=1024)
    detail: dict[str, object] | None = None


class AdminAck(_Message):
    type: Literal["admin_ack"] = "admin_ack"
    request_id: str
    command: AdminAction
    detail: dict[str, object] | None = None


class AdminRejected(_Message):
    type: Literal["admin_rejected"] = "admin_rejected"
    request_id: str
    command: AdminAction
    reason: AdminRejectReason
