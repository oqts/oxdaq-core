"""Encode and decode wire frames. docs/protocol.md.

The only place JSON becomes a message or a message becomes JSON. Both
directions are total: ``decode_*`` either returns a valid message or
raises :class:`DecodeError`, which already carries the ``ErrorCode`` the
gateway should reply with (protocol.md 9). Callers never inspect a pydantic
exception.
"""

import json
from typing import Annotated, Final

from pydantic import Field, TypeAdapter, ValidationError

from .enums import ErrorCode
from .messages import (
    AdminAck,
    AdminCancelTeamOrders,
    AdminConnections,
    AdminDisconnect,
    AdminEndRound,
    AdminEvent,
    AdminHealth,
    AdminInjectNews,
    AdminLeaderboard,
    AdminPracticeControl,
    AdminRejected,
    AdminSnapshot,
    AdminStartRound,
    Auth,
    AuthOk,
    BookUpdate,
    CancelAck,
    CancelOrder,
    CancelRejected,
    Error,
    Fill,
    NewsEvent,
    OrderAck,
    OrderRejected,
    Resync,
    RoundEnded,
    RoundStarted,
    StateSnapshot,
    SubmitOrder,
    TradeTick,
)

__all__ = [
    "ADMIN_MESSAGE_TYPES",
    "ALL_MESSAGE_TYPES",
    "AdminCommand",
    "ClientMessage",
    "DecodeError",
    "Encoder",
    "ServerMessage",
    "decode_client_message",
    "decode_server_message",
    "encode",
]

# Participant messages. protocol.md 3.
ParticipantMessage = Auth | SubmitOrder | CancelOrder | Resync

# Admin commands. protocol.md 10. A subset of client to server, gated on role.
AdminCommand = (
    AdminStartRound
    | AdminEndRound
    | AdminInjectNews
    | AdminPracticeControl
    | AdminCancelTeamOrders
    | AdminDisconnect
)

ClientMessage = ParticipantMessage | AdminCommand

ServerMessage = (
    AuthOk
    | StateSnapshot
    | OrderAck
    | OrderRejected
    | CancelAck
    | CancelRejected
    | Fill
    | BookUpdate
    | TradeTick
    | RoundStarted
    | NewsEvent
    | RoundEnded
    | Error
    | AdminSnapshot
    | AdminLeaderboard
    | AdminConnections
    | AdminHealth
    | AdminEvent
    | AdminAck
    | AdminRejected
)

_CLIENT_ADAPTER: Final = TypeAdapter(
    Annotated[ClientMessage, Field(discriminator="type")]
)
_SERVER_ADAPTER: Final = TypeAdapter(
    Annotated[ServerMessage, Field(discriminator="type")]
)

ADMIN_MESSAGE_TYPES: Final[frozenset[str]] = frozenset(
    m.model_fields["type"].default for m in AdminCommand.__args__
)
"""Client-to-server types that require ``role == admin`` (protocol.md 10)."""

ALL_MESSAGE_TYPES: Final[frozenset[str]] = frozenset(
    m.model_fields["type"].default
    for m in (*ClientMessage.__args__, *ServerMessage.__args__)
)


class DecodeError(Exception):
    """A frame that could not be turned into a message.

    Carries the ``ErrorCode`` to put in the reply, so the gateway maps
    nothing itself.

    Attributes:
        code: What to send in ``error.code``.
        message: Safe to show a participant. Never a stack trace.
        detail: Structured context, for example the offending field path.
        client_order_id: Recovered best-effort, so an ``error`` can be
            correlated with the order the participant thought they sent.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        detail: dict[str, object] | None = None,
        client_order_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
        self.client_order_id = client_order_id


def _parse_json(raw: str | bytes) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DecodeError(ErrorCode.MALFORMED_FRAME, "frame is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise DecodeError(ErrorCode.MALFORMED_FRAME, "frame must be a JSON object")
    return payload


def _recover_client_order_id(payload: dict[str, object]) -> str | None:
    """Best-effort echo value for an `error` reply.

    A malformed `submit_order` still usually carries a readable
    `client_order_id`, and echoing it is the difference between a
    participant being able to correlate the error with the order they sent
    and not. Deliberately tolerant: this is diagnostics, not validation.
    """
    value = payload.get("client_order_id")
    return value if isinstance(value, str) and value else None


def _validation_detail(exc: ValidationError) -> dict[str, object]:
    """Field paths and reasons, with no server internals.

    Pydantic's `input` values are dropped: they can contain a token.
    """
    return {
        "errors": [
            {"field": ".".join(str(p) for p in e["loc"]), "problem": e["msg"]}
            for e in exc.errors()[:8]
        ]
    }


def _decode(raw: str | bytes, adapter: TypeAdapter) -> object:
    payload = _parse_json(raw)
    msg_type = payload.get("type")
    if not isinstance(msg_type, str):
        raise DecodeError(
            ErrorCode.MALFORMED_FRAME,
            "frame has no string 'type' field",
            client_order_id=_recover_client_order_id(payload),
        )
    if msg_type not in ALL_MESSAGE_TYPES:
        raise DecodeError(
            ErrorCode.UNKNOWN_MESSAGE_TYPE,
            f"unknown message type {msg_type!r}",
            client_order_id=_recover_client_order_id(payload),
        )
    try:
        return adapter.validate_python(payload)
    except ValidationError as exc:
        raise DecodeError(
            ErrorCode.SCHEMA_VIOLATION,
            f"message {msg_type!r} does not match the schema",
            detail=_validation_detail(exc),
            client_order_id=_recover_client_order_id(payload),
        ) from exc


def decode_client_message(raw: str | bytes) -> ClientMessage:
    """Decode a frame from a participant, a bot or the admin. Server side."""
    return _decode(raw, _CLIENT_ADAPTER)  # type: ignore[return-value]


def decode_server_message(raw: str | bytes) -> ServerMessage:
    """Decode a frame from the server. Client and dashboard side."""
    return _decode(raw, _SERVER_ADAPTER)  # type: ignore[return-value]


def encode(message: ServerMessage | ClientMessage) -> str:
    """Serialise a message to a JSON frame.

    ``exclude_none`` is deliberately **off**: a null is meaningful in this
    protocol. ``last_trade_price: null`` says "no trade yet", and omitting
    the key would force every consumer to distinguish absent from null.
    """
    return message.model_dump_json()


class Encoder:
    """Stamps the envelope for one connection. protocol.md 1.

    ``seq`` is per connection and monotonic, so this is deliberately
    stateful and deliberately one instance per connection. It is not
    thread safe and does not need to be: one coroutine owns each
    connection (design.md 2.2).
    """

    __slots__ = ("_clock", "_seq")

    def __init__(self, clock, start_seq: int = 0) -> None:
        """Args:
        clock: Zero-argument callable returning Unix seconds. Injected
            rather than calling ``time.time()`` directly so tests can
            produce byte-stable golden frames.
        start_seq: First sequence number to issue.
        """
        self._clock = clock
        self._seq = start_seq

    @property
    def next_seq(self) -> int:
        return self._seq

    def stamp(self, message_cls, **fields):
        """Build a message with the envelope filled in.

        Returns:
            The constructed message, with ``timestamp`` and ``seq`` set.
        """
        msg = message_cls(timestamp=self._clock(), seq=self._seq, **fields)
        self._seq += 1
        return msg

    def frame(self, message_cls, **fields) -> str:
        """Build and serialise in one step. The common case."""
        return encode(self.stamp(message_cls, **fields))
