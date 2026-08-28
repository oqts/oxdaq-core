"""Closed vocabularies of the OXDAQ wire protocol.

Every value here appears verbatim in JSON on the wire. Changing a member
name is a protocol change: bump ``PROTOCOL_VERSION`` and update
``planning/OXDAQ-PLAN.md`` in the same change set (spec 15.2).

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
    "PracticeAction",
    "RejectReason",
    "Role",
    "SessionState",
    "Side",
]


class Side(StrEnum):
    """Order side. Spec 9.3."""

    BID = "bid"
    ASK = "ask"

    @property
    def opposite(self) -> "Side":
        return Side.ASK if self is Side.BID else Side.BID

    @property
    def sign(self) -> int:
        """+1 for a buy, -1 for a sell.

        The sign a fill applies to a position: buys increase it, sells
        decrease it (spec 5.6).
        """
        return 1 if self is Side.BID else -1


class SessionState(StrEnum):
    """Spec 9.5."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    ENDED = "ENDED"


class Role(StrEnum):
    """Authorisation role, carried in ``auth_ok``. Spec 9.2.

    There are exactly two, and ``bot`` is deliberately not one of them.
    Spec 12.1 lists four *token* types, but only one distinction is
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
    """Business rejection of a well-formed order. Spec 9.4, 5.5.

    Distinct from ``ErrorCode``, which covers frames that could not be
    understood at all.
    """

    INSUFFICIENT_BUYING_POWER = "insufficient_buying_power"
    POSITION_LIMIT_BREACHED = "position_limit_breached"
    ROUND_NOT_ACTIVE = "round_not_active"
    UNKNOWN_INSTRUMENT = "unknown_instrument"
    INVALID_VOLUME = "invalid_volume"
    INVALID_PRICE = "invalid_price"


class CancelRejectReason(StrEnum):
    """Spec 9.4."""

    UNKNOWN_ORDER = "unknown_order"
    NOT_YOUR_ORDER = "not_your_order"
    ROUND_NOT_ACTIVE = "round_not_active"


class ErrorCode(StrEnum):
    """Protocol-level failure. Spec 9.9.

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
    """WebSocket close codes in the private-use range. Spec 9.9."""

    INVALID_TOKEN = 4001
    AUTH_TIMEOUT = 4002
    UNAUTHENTICATED_MESSAGE = 4003
    ERROR_RATE_EXCEEDED = 4008
    ADMIN_DISCONNECT = 4009


class PracticeAction(StrEnum):
    """Spec 9.10 ``admin_practice_control``."""

    PAUSE = "pause"
    RESUME = "resume"
    RESET = "reset"


class AdminAction(StrEnum):
    """The admin commands, for use in ``admin_ack.command``. Spec 9.10."""

    START_ROUND = "admin_start_round"
    END_ROUND = "admin_end_round"
    INJECT_NEWS = "admin_inject_news"
    PRACTICE_CONTROL = "admin_practice_control"
    CANCEL_TEAM_ORDERS = "admin_cancel_team_orders"
    DISCONNECT = "admin_disconnect"


class AdminRejectReason(StrEnum):
    """Spec 9.10 ``admin_rejected``."""

    ROUND_ALREADY_RUNNING = "round_already_running"
    NO_ROUND_RUNNING = "no_round_running"
    ROUND_ID_MISMATCH = "round_id_mismatch"
    UNKNOWN_TEAM = "unknown_team"
    UNKNOWN_CONNECTION = "unknown_connection"
    INVALID_CONFIG = "invalid_config"
    PRACTICE_NOT_RUNNING = "practice_not_running"
    DUPLICATE_EVENT_ID = "duplicate_event_id"


class AdminSeverity(StrEnum):
    """Spec 9.10 ``admin_event``."""

    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class AdminEventCategory(StrEnum):
    """Spec 9.10 ``admin_event``."""

    SESSION = "session"
    CONNECTION = "connection"
    ORDER = "order"
    BOT = "bot"
    PRACTICE = "practice"
    SYSTEM = "system"
