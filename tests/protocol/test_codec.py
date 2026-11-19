"""Encoding, decoding and the failure paths. docs/protocol.md."""

import json

import pytest

from oqts.protocol import messages as m
from oqts.protocol.codec import (
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
from oqts.protocol.enums import ErrorCode
from tests.protocol.samples import SAMPLES

CLIENT_TYPES = {c.model_fields["type"].default for c in ClientMessage.__args__}
SERVER_TYPES = {c.model_fields["type"].default for c in ServerMessage.__args__}


def _decoder_for(name: str):
    return decode_client_message if name in CLIENT_TYPES else decode_server_message


# --- round trip -----------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_every_message_type_round_trips(name: str) -> None:
    original = SAMPLES[name]
    assert _decoder_for(name)(encode(original)) == original


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_encoding_is_stable(name: str) -> None:
    """Encoding the decoded form must reproduce the same bytes.

    Without this, the golden corpus would only pin the first encode, not
    the shape of what comes back off the wire.
    """
    frame = encode(SAMPLES[name])
    assert encode(_decoder_for(name)(frame)) == frame


def test_client_and_server_message_sets_are_disjoint() -> None:
    """No type may travel in both directions.

    If one did, the discriminated union could resolve a client frame to a
    server model, and the gateway would trust a field a participant sent.
    """
    assert not (CLIENT_TYPES & SERVER_TYPES)
    assert CLIENT_TYPES | SERVER_TYPES == ALL_MESSAGE_TYPES


def test_a_server_message_is_not_accepted_from_a_client() -> None:
    with pytest.raises(DecodeError) as exc:
        decode_client_message(encode(SAMPLES["fill"]))
    assert exc.value.code is ErrorCode.SCHEMA_VIOLATION


# --- failure paths. protocol.md 9 -----------------------------------------


@pytest.mark.parametrize("raw", ["", "{", "not json", "[1,2,3]", '"a string"', "null"])
def test_unparseable_frames_are_malformed(raw: str) -> None:
    with pytest.raises(DecodeError) as exc:
        decode_client_message(raw)
    assert exc.value.code is ErrorCode.MALFORMED_FRAME


def test_a_frame_with_no_type_is_malformed() -> None:
    with pytest.raises(DecodeError) as exc:
        decode_client_message('{"timestamp": 1.0, "seq": 0}')
    assert exc.value.code is ErrorCode.MALFORMED_FRAME


def test_a_non_string_type_is_malformed() -> None:
    with pytest.raises(DecodeError) as exc:
        decode_client_message('{"type": 7}')
    assert exc.value.code is ErrorCode.MALFORMED_FRAME


def test_an_unknown_type_is_reported_as_such() -> None:
    with pytest.raises(DecodeError) as exc:
        decode_client_message('{"type": "submit_ordr", "seq": 0, "timestamp": 1.0}')
    assert exc.value.code is ErrorCode.UNKNOWN_MESSAGE_TYPE
    assert "submit_ordr" in exc.value.message


def test_a_known_type_with_bad_fields_is_a_schema_violation() -> None:
    bad = json.loads(encode(SAMPLES["submit_order"]))
    bad["volume"] = -5
    with pytest.raises(DecodeError) as exc:
        decode_client_message(json.dumps(bad))
    assert exc.value.code is ErrorCode.SCHEMA_VIOLATION


def test_a_negative_price_never_decodes() -> None:
    """design.md 5.5, D11. Belt and braces with the gateway's invalid_price check.

    A resting buy at a negative price would decrease reserved_cash and
    manufacture buying power (design.md 5.6), so the schema refuses one too.
    """
    for price in (-1.0, 0.0):
        bad = json.loads(encode(SAMPLES["submit_order"]))
        bad["price"] = price
        with pytest.raises(DecodeError) as exc:
            decode_client_message(json.dumps(bad))
        assert exc.value.code is ErrorCode.SCHEMA_VIOLATION


def test_an_unknown_field_is_rejected_rather_than_ignored() -> None:
    """extra="forbid". A field we do not know about is a version mismatch
    or an attack, and silently dropping it hides both."""
    bad = json.loads(encode(SAMPLES["submit_order"]))
    bad["stop_price"] = 99.0
    with pytest.raises(DecodeError) as exc:
        decode_client_message(json.dumps(bad))
    assert exc.value.code is ErrorCode.SCHEMA_VIOLATION


def test_client_order_id_is_recovered_for_the_error_echo() -> None:
    """So a participant can correlate the error with the order they sent."""
    bad = json.loads(encode(SAMPLES["submit_order"]))
    bad["volume"] = 0
    with pytest.raises(DecodeError) as exc:
        decode_client_message(json.dumps(bad))
    assert exc.value.client_order_id == "c-0001"


def test_error_detail_never_leaks_the_offending_input() -> None:
    """A malformed `auth` frame must not put the token in an error reply.

    Pydantic's raw errors carry the rejected input value. If that reached
    `error.detail`, a bad auth frame would echo the token back over the
    wire and into logs, which is the exact exposure D7 removed.
    """
    with pytest.raises(DecodeError) as exc:
        decode_client_message('{"type":"auth","timestamp":1.0,"seq":0,"token":""}')
    serialised = json.dumps(exc.value.detail)
    assert "input" not in serialised
    payload = json.dumps(
        {"type": "auth", "timestamp": 1.0, "seq": 0, "token": "s3cret"}
    )
    with pytest.raises(DecodeError) as exc2:
        decode_client_message(payload.replace('"seq": 0', '"seq": "x"'))
    assert "s3cret" not in json.dumps(exc2.value.detail)


# --- admin gating. protocol.md 10 -----------------------------------------


def test_admin_types_are_exactly_the_admin_commands() -> None:
    """The gateway gates on this set, so it must not drift from the union."""
    assert {
        c.model_fields["type"].default for c in AdminCommand.__args__
    } == ADMIN_MESSAGE_TYPES
    assert ADMIN_MESSAGE_TYPES < CLIENT_TYPES


def test_every_admin_command_carries_a_request_id() -> None:
    """admin_ack and admin_rejected echo it, so a command without one
    could not be correlated with its result."""
    for cls in AdminCommand.__args__:
        assert "request_id" in cls.model_fields


def test_no_server_to_admin_message_is_an_admin_command() -> None:
    """admin_snapshot and friends travel outbound only."""
    assert not (ADMIN_MESSAGE_TYPES & SERVER_TYPES)


# --- invariant 7: fair value never crosses the network. design.md 6.5 -----

_FORBIDDEN_OUTBOUND = {
    "fair_value",
    "fair_values",
    "s0",
    "mu",
    "sigma",
    "rho",
    "theta",
    "mu_bar",
    "seed",
    "jump_size",
    "jump_sizes",
    "jump_times",
    "jumps",
    "process",
}


@pytest.mark.parametrize(
    "cls", sorted(ServerMessage.__args__, key=lambda c: c.__name__)
)
def test_no_server_to_client_message_can_carry_a_fair_value(cls) -> None:
    """Invariant 7, enforced structurally rather than by discipline.

    There must be no field on any outbound message into which a latent
    fair value, a process parameter or a news jump magnitude could be put,
    at any depth. A future contributor adding one for debugging fails here.
    """
    seen: set[type] = set()

    def walk(model, path: str) -> None:
        if model in seen:
            return
        seen.add(model)
        for name, field in model.model_fields.items():
            assert name not in _FORBIDDEN_OUTBOUND, (
                f"{path}.{name} would let a fair value or process parameter "
                f"reach a participant. design.md 6.5, invariant 7."
            )
            for arg in (field.annotation, *getattr(field.annotation, "__args__", ())):
                if isinstance(arg, type) and hasattr(arg, "model_fields"):
                    walk(arg, f"{path}.{name}")

    walk(cls, cls.__name__)


def test_process_parameters_are_inbound_only() -> None:
    """The one model that carries them travels admin-to-server only.

    admin_snapshot deliberately echoes InstrumentPublic instead, so the
    seed and the process parameters never come back to a browser.
    """
    assert set(_FORBIDDEN_OUTBOUND) & set(m.InstrumentConfigWire.model_fields)
    assert (
        m.AdminSnapshot.model_fields["instruments"].annotation
        == list[m.InstrumentPublic]
    )


def test_news_event_has_no_magnitude_field() -> None:
    """The jump is inferred, never sent. protocol.md 8, design.md 1.1."""
    assert set(m.NewsEvent.model_fields) == {
        "timestamp",
        "seq",
        "type",
        "event_id",
        "headline",
        "affected_instruments",
    }


# --- envelope. protocol.md 1 ----------------------------------------------


def test_encoder_issues_monotonic_sequence_numbers() -> None:
    clock = iter([1.0, 2.0, 3.0])
    enc = Encoder(lambda: next(clock))
    seqs = [enc.stamp(m.Resync).seq for _ in range(3)]
    assert seqs == [0, 1, 2]


def test_encoder_stamps_the_injected_clock() -> None:
    enc = Encoder(lambda: 1714300000.5)
    assert enc.stamp(m.Resync).timestamp == 1714300000.5


def test_encoder_frame_matches_encode_of_stamp() -> None:
    a = Encoder(lambda: 1.0).frame(m.CancelOrder, order_id="o-1")
    b = encode(Encoder(lambda: 1.0).stamp(m.CancelOrder, order_id="o-1"))
    assert a == b


def test_every_message_carries_the_envelope() -> None:
    for cls in (*ClientMessage.__args__, *ServerMessage.__args__):
        assert {"timestamp", "seq"} <= set(cls.model_fields), cls.__name__


def test_messages_are_immutable() -> None:
    """A message is a record of what crossed the wire. Mutating one after
    the fact would make the trade tape and the logs disagree."""
    order = SAMPLES["submit_order"]
    with pytest.raises(ValueError, match="frozen"):
        order.volume = 99


def test_nulls_are_kept_rather_than_omitted() -> None:
    """`last_trade_price: null` means "no trade yet". Omitting the key
    would force every consumer to distinguish absent from null."""
    frame = json.loads(
        encode(m.BookUpdate(timestamp=1.0, seq=0, instrument_id="A", bids=[], asks=[]))
    )
    assert "last_trade_price" in frame
    assert frame["last_trade_price"] is None


# --- protocol v2. D28 to D32 ------------------------------------------------


@pytest.mark.parametrize("order_type", ["limit", "ioc"])
def test_both_order_types_decode(order_type: str) -> None:
    frame = json.loads(encode(SAMPLES["submit_order"]))
    frame["order_type"] = order_type
    assert decode_client_message(json.dumps(frame)).order_type == order_type


def test_order_type_is_required() -> None:
    """No default on the wire: a v1 client that omits it fails loudly rather
    than having the server guess what it meant (protocol.md 3)."""
    frame = json.loads(encode(SAMPLES["submit_order"]))
    del frame["order_type"]
    with pytest.raises(DecodeError) as exc:
        decode_client_message(json.dumps(frame))
    assert exc.value.code is ErrorCode.SCHEMA_VIOLATION


@pytest.mark.parametrize("order_type", ["market", "fok", "LIMIT", ""])
def test_an_unknown_order_type_is_a_schema_violation(order_type: str) -> None:
    frame = json.loads(encode(SAMPLES["submit_order"]))
    frame["order_type"] = order_type
    with pytest.raises(DecodeError) as exc:
        decode_client_message(json.dumps(frame))
    assert exc.value.code is ErrorCode.SCHEMA_VIOLATION


def test_trade_tick_is_anonymous() -> None:
    """Invariant 8 and protocol.md 7: nothing in a public trade can identify
    either side, so it cannot single out a bot."""
    assert set(m.TradeTick.model_fields) == {
        "timestamp",
        "seq",
        "type",
        "instrument_id",
        "price",
        "volume",
        "aggressor_side",
    }


def test_rate_limited_is_a_reason_for_orders_and_cancels() -> None:
    """D30: submits and cancels share one budget, and both are refused with
    a reason rather than an error or a disconnection."""
    for cls in (m.OrderRejected, m.CancelRejected):
        frame = json.loads(encode(SAMPLES[cls.model_fields["type"].default]))
        frame["reason"] = "rate_limited"
        assert decode_server_message(json.dumps(frame)).reason == "rate_limited"


def test_admin_start_round_has_no_seed() -> None:
    """design.md 6.7, D32: the server generates the seed. A frame that tries
    to supply one is refused, not silently ignored."""
    assert "seed" not in m.AdminStartRound.model_fields
    frame = json.loads(encode(SAMPLES["admin_start_round"]))
    frame["seed"] = 20260828
    with pytest.raises(DecodeError) as exc:
        decode_client_message(json.dumps(frame))
    assert exc.value.code is ErrorCode.SCHEMA_VIOLATION
