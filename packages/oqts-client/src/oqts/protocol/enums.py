"""Closed vocabularies of the OXDAQ wire protocol.

Every value here appears verbatim in JSON on the wire. Changing a member
name is a protocol change: bump ``PROTOCOL_VERSION`` and update
``docs/protocol.md`` in the same change set (build.md 2.1).

All members subclass ``str`` so that ``Side.BID == "bid"`` holds and
pydantic serialises them without a custom encoder.
"""

from enum import IntEnum, StrEnum

__all__ = [
    "AdminAction",
    "AdminEventCategory",
    "AdminRejectReason",
    "AdminSeverity",
    "CancelRejectReason",
    "CloseCode",
    "ErrorCode",
    "OrderType",
    "PracticeAction",
    "RejectReason",
    "Role",
    "SessionState",
    "Side",
]


class Side(StrEnum):
    """Order side. protocol.md 3."""

    BID = "bid"
    ASK = "ask"

    @property
    def opposite(self) -> "Side":
        return Side.ASK if self is Side.BID else Side.BID

    @property
    def sign(self) -> int:
        """+1 for a buy, -1 for a sell.

        The sign a fill applies to a position: buys increase it, sells
        decrease it (design.md 5.6).
        """
        return 1 if self is Side.BID else -1


class OrderType(StrEnum):
    """protocol.md 3, design.md 4.1. Added in protocol v2 (D28).

    A limit order's unmatched remainder rests. An IOC (immediate or
    cancel) matches identically, then its remainder is cancelled at once
    and never enters the book.
    """

    LIMIT = "limit"
    IOC = "ioc"


class SessionState(StrEnum):
    """protocol.md 5."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    ENDED = "ENDED"


class Role(StrEnum):
    """Authorisation role, carried in ``auth_ok``. protocol.md 2.

    There are exactly two, and ``bot`` is deliberately not one of them.
    operations.md 3.1 lists four *token* types, but only one distinction is
    authorisation relevant: whether the connection may send ``admin_*``
    messages. Team, bot and practice tokens all grant ``PARTICIPANT``.

    This is what makes invariant 8 (bots are indistinguishable from
    participants) structural rather than a matter of discipline. There is
    no bot role on the wire, so no message can carry one and no code path
    can branch on it.
    """

    PARTICIPANT = "participant"
    ADMIN = "admin"


class RejectReason(StrEnum):
    """Business rejection of a well-formed order. protocol.md 4, design.md 5.5.

    Distinct from ``ErrorCode``, which covers frames that could not be
    understood at all.
    """

    INSUFFICIENT_BUYING_POWER = "insufficient_buying_power"
    POSITION_LIMIT_BREACHED = "position_limit_breached"
    ROUND_NOT_ACTIVE = "round_not_active"
    UNKNOWN_INSTRUMENT = "unknown_instrument"
    INVALID_VOLUME = "invalid_volume"
    INVALID_PRICE = "invalid_price"
    RATE_LIMITED = "rate_limited"  # v2, D30. The connection stays open


class CancelRejectReason(StrEnum):
    """protocol.md 4."""

    UNKNOWN_ORDER = "unknown_order"
    NOT_YOUR_ORDER = "not_your_order"
    ROUND_NOT_ACTIVE = "round_not_active"
    RATE_LIMITED = "rate_limited"  # v2, D30. Cancels share the order budget


class ErrorCode(StrEnum):
    """Protocol-level failure. protocol.md 9.

    The frame could not be understood, or the sender was not entitled to
    send it. A business rejection of a *valid* order is ``RejectReason``.
    """

    MALFORMED_FRAME = "malformed_frame"
    UNKNOWN_MESSAGE_TYPE = "unknown_message_type"
    SCHEMA_VIOLATION = "schema_violation"
    NOT_AUTHORISED = "not_authorised"
    NOT_ADMIN = "not_admin"
    INTERNAL_ERROR = "internal_error"


class CloseCode(IntEnum):
    """WebSocket close codes in the private-use range. protocol.md 9."""

    INVALID_TOKEN = 4001
    AUTH_TIMEOUT = 4002
    UNAUTHENTICATED_MESSAGE = 4003
    ERROR_RATE_EXCEEDED = 4008
    ADMIN_DISCONNECT = 4009


class PracticeAction(StrEnum):
    """protocol.md 10 ``admin_practice_control``."""

    PAUSE = "pause"
    RESUME = "resume"
    RESET = "reset"


class AdminAction(StrEnum):
    """The admin commands, for use in ``admin_ack.command``. protocol.md 10."""

    START_ROUND = "admin_start_round"
    END_ROUND = "admin_end_round"
    INJECT_NEWS = "admin_inject_news"
    PRACTICE_CONTROL = "admin_practice_control"
    CANCEL_TEAM_ORDERS = "admin_cancel_team_orders"
    DISCONNECT = "admin_disconnect"


class AdminRejectReason(StrEnum):
    """protocol.md 10 ``admin_rejected``."""

    ROUND_ALREADY_RUNNING = "round_already_running"
    NO_ROUND_RUNNING = "no_round_running"
    ROUND_ID_MISMATCH = "round_id_mismatch"
    UNKNOWN_TEAM = "unknown_team"
    UNKNOWN_CONNECTION = "unknown_connection"
    INVALID_CONFIG = "invalid_config"
    PRACTICE_NOT_RUNNING = "practice_not_running"
    DUPLICATE_EVENT_ID = "duplicate_event_id"


class AdminSeverity(StrEnum):
    """protocol.md 10 ``admin_event``."""

    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class AdminEventCategory(StrEnum):
    """protocol.md 10 ``admin_event``."""

    SESSION = "session"
    CONNECTION = "connection"
    ORDER = "order"
    BOT = "bot"
    PRACTICE = "practice"
    SYSTEM = "system"
