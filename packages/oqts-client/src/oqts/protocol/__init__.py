"""The OXDAQ wire protocol: message definitions, enums and codec.

Shared by the server, the client library, the bots and both dashboards.
Frozen: see ``messages.py``.
"""

from .codec import (
    ADMIN_MESSAGE_TYPES,
    ALL_MESSAGE_TYPES,
    AdminCommand,
    ClientMessage,
    DecodeError,
    Encoder,
    ServerMessage,
    decode_client_message,
    decode_server_message,
    encode,
)
from .enums import (
    AdminAction,
    AdminEventCategory,
    AdminRejectReason,
    AdminSeverity,
    CancelRejectReason,
    CloseCode,
    ErrorCode,
    PracticeAction,
    RejectReason,
    Role,
    SessionState,
    Side,
)
from .messages import PROTOCOL_VERSION

__all__ = [
    "ADMIN_MESSAGE_TYPES",
    "ALL_MESSAGE_TYPES",
    "PROTOCOL_VERSION",
    "AdminAction",
    "AdminCommand",
    "AdminEventCategory",
    "AdminRejectReason",
    "AdminSeverity",
    "CancelRejectReason",
    "ClientMessage",
    "CloseCode",
    "DecodeError",
    "Encoder",
    "ErrorCode",
    "PracticeAction",
    "RejectReason",
    "Role",
    "ServerMessage",
    "SessionState",
    "Side",
    "decode_client_message",
    "decode_server_message",
    "encode",
]
