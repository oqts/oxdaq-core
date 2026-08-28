"""The schema freeze. Spec 15.2, D17.

Section 15.4 requires the message schema to be frozen before any other
code is written. Enforcing that by memory would not survive milestone 7,
so it is enforced here: every message type has a checked-in golden frame,
compared byte for byte.

A failure in this file is not a broken test. It is the freeze working. If
the change is intended, it is a protocol change, which means all four of:

1. bump ``PROTOCOL_VERSION``,
2. update ``planning/OXDAQ-PLAN.md`` section 9 in the same change set,
3. update ``samples.py``,
4. ``uv run python tests/protocol/regenerate_golden.py``.
"""

import json
import pathlib

import pytest

from oqts.protocol.codec import ALL_MESSAGE_TYPES, encode
from oqts.protocol.messages import PROTOCOL_VERSION
from tests.protocol.samples import SAMPLES

GOLDEN_DIR = pathlib.Path(__file__).resolve().parents[1] / "golden"


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_frame_matches_the_frozen_golden(name: str) -> None:
    path = GOLDEN_DIR / f"{name}.json"
    assert path.exists(), (
        f"no golden frame for {name!r}. If this is a new message type, it is a "
        f"protocol change: see this module's docstring."
    )
    assert json.loads(encode(SAMPLES[name])) == json.loads(path.read_text()), (
        f"the wire shape of {name!r} has changed. See this module's docstring."
    )


def test_every_message_type_has_a_sample() -> None:
    """A type without a sample is a type nothing pins."""
    assert set(SAMPLES) == ALL_MESSAGE_TYPES


def test_there_are_no_orphan_golden_files() -> None:
    """A removed message type must not leave its frame behind."""
    on_disk = {p.stem for p in GOLDEN_DIR.glob("*.json")}
    assert on_disk == set(SAMPLES)


def test_sample_type_field_matches_its_key() -> None:
    for name, message in SAMPLES.items():
        assert message.type == name


def test_protocol_version_is_pinned() -> None:
    """Changing this is a deliberate act, so it should require editing a test.

    Bumping the version without touching the corpus is the failure mode
    this catches: a version that moves without the shape moving tells
    clients to expect a change that did not happen.
    """
    assert PROTOCOL_VERSION == 1


def test_the_message_type_inventory_is_pinned() -> None:
    """Spec 9 defines exactly these. Adding one silently is the thing the
    freeze exists to prevent."""
    assert {
        # client to server, spec 9.3
        "auth",
        "submit_order",
        "cancel_order",
        "resync",
        # server to client, spec 9.4, 9.5, 9.6
        "auth_ok",
        "order_ack",
        "order_rejected",
        "cancel_ack",
        "cancel_rejected",
        "state_snapshot",
        "fill",
        # server to all, spec 9.7, 9.8
        "book_update",
        "round_started",
        "news_event",
        "round_ended",
        # protocol errors, spec 9.9
        "error",
        # admin, client to server, spec 9.10
        "admin_start_round",
        "admin_end_round",
        "admin_inject_news",
        "admin_practice_control",
        "admin_cancel_team_orders",
        "admin_disconnect",
        # admin, server to client, spec 9.10
        "admin_snapshot",
        "admin_leaderboard",
        "admin_connections",
        "admin_health",
        "admin_event",
        "admin_ack",
        "admin_rejected",
    } == ALL_MESSAGE_TYPES
