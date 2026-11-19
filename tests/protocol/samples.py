"""One canonical instance of every wire message. docs/protocol.md.

This is the freeze mechanism (build.md 2.1, D17). ``test_golden.py`` encodes
each of these and compares byte for byte against ``tests/golden/``, and
asserts that every type in ``ALL_MESSAGE_TYPES`` appears here. So a field
cannot be added, removed, renamed or retyped, and a message type cannot be
introduced, without CI failing with a readable diff.

Values are fixed, never generated: a golden corpus that changes between
runs proves nothing. Regenerate with::

    uv run python tests/protocol/regenerate_golden.py
"""

from oqts.protocol import messages as m

_T = 1_714_300_000.123  # fixed timestamp, so frames are byte-stable

_BOOK = m.BookSnapshot(
    bids=[m.BookLevel(price=99.5, volume=40), m.BookLevel(price=99.49, volume=15)],
    asks=[m.BookLevel(price=99.52, volume=25)],
    last_trade_price=99.51,
)

_INSTRUMENT = m.InstrumentPublic(
    id="STOCK_A", starting_price=100.0, tick_size=0.01, lot_size=1
)

_TEAM_ROW = m.TeamRow(
    rank=1,
    team_id="team_07",
    display_name="Merton Micro",
    realised_pnl=1234.5678,
    cash=101234.5678,
    positions={"STOCK_A": 12, "STOCK_B": -5},
    open_order_count=3,
    order_count=141,
    fill_count=58,
)

_CONNECTION_ROW = m.ConnectionRow(
    connection_id="conn_9f2a",
    team_id="team_07",
    display_name="Merton Micro",
    role="participant",
    connected_at=_T - 300.0,
    last_seen=_T,
    orders_submitted=141,
    orders_rejected=2,
    fills=58,
    errors=0,
)

SAMPLES: dict[str, m._Message] = {
    # --- client to server, protocol.md 3 ---
    "auth": m.Auth(timestamp=_T, seq=0, token="tok_abc123"),
    "submit_order": m.SubmitOrder(
        timestamp=_T,
        seq=1,
        client_order_id="c-0001",
        instrument_id="STOCK_A",
        side="bid",
        price=99.5,
        volume=10,
    ),
    "cancel_order": m.CancelOrder(timestamp=_T, seq=2, order_id="o-0001"),
    "resync": m.Resync(timestamp=_T, seq=3),
    # --- server to client, acks, protocol.md 4 ---
    "auth_ok": m.AuthOk(
        timestamp=_T,
        seq=0,
        protocol_version=m.PROTOCOL_VERSION,
        connection_id="conn_9f2a",
        team_id="team_07",
        display_name="Merton Micro",
        role="participant",
        session_id="sess_r3",
        server_time=_T,
    ),
    "order_ack": m.OrderAck(
        timestamp=_T,
        seq=1,
        order_id="o-0001",
        client_order_id="c-0001",
        instrument_id="STOCK_A",
        side="bid",
        price=99.5,
        volume=10,
    ),
    "order_rejected": m.OrderRejected(
        timestamp=_T,
        seq=2,
        client_order_id="c-0002",
        reason="insufficient_buying_power",
    ),
    "cancel_ack": m.CancelAck(
        timestamp=_T,
        seq=3,
        order_id="o-0001",
        instrument_id="STOCK_A",
        cancelled_volume=4,
    ),
    "cancel_rejected": m.CancelRejected(
        timestamp=_T, seq=4, order_id="o-0009", reason="unknown_order"
    ),
    # --- server to client, state, protocol.md 5 ---
    "state_snapshot": m.StateSnapshot(
        timestamp=_T,
        seq=5,
        session_id="sess_r3",
        session_state="RUNNING",
        server_time=_T,
        ends_at=_T + 1200.0,
        instruments=[_INSTRUMENT],
        cash=101234.5678,
        positions={"STOCK_A": 12},
        open_orders=[
            m.OpenOrder(
                order_id="o-0001",
                client_order_id="c-0001",
                instrument_id="STOCK_A",
                side="bid",
                price=99.5,
                volume=10,
                remaining_volume=6,
            )
        ],
        books={"STOCK_A": _BOOK},
    ),
    # --- server to client, fills, protocol.md 6 ---
    "fill": m.Fill(
        timestamp=_T,
        seq=6,
        order_id="o-0001",
        client_order_id="c-0001",
        instrument_id="STOCK_A",
        side="bid",
        price=99.5,
        volume=4,
        remaining_volume=6,
        aggressor=True,
        cash=100836.5678,
        positions={"STOCK_A": 16},
    ),
    # --- server to all, market data, protocol.md 7 ---
    "book_update": m.BookUpdate(
        timestamp=_T,
        seq=7,
        instrument_id="STOCK_A",
        bids=list(_BOOK.bids),
        asks=list(_BOOK.asks),
        last_trade_price=99.51,
    ),
    # --- server to all, lifecycle, protocol.md 8 ---
    "round_started": m.RoundStarted(
        timestamp=_T,
        seq=8,
        round_id="round_2026_t2_a",
        instruments=[_INSTRUMENT],
        starting_cash=100000.0,
        position_limit=100,
        duration_s=1200.0,
        ends_at=_T + 1200.0,
        server_time=_T,
    ),
    "news_event": m.NewsEvent(
        timestamp=_T,
        seq=9,
        event_id="news_001",
        headline="Q3 earnings significantly beat expectations.",
        affected_instruments=["STOCK_A"],
    ),
    "round_ended": m.RoundEnded(
        timestamp=_T,
        seq=10,
        round_id="round_2026_t2_a",
        final_cash=101234.5678,
        final_positions={"STOCK_A": 0},
        realised_pnl=1234.5678,
    ),
    # --- server to client, protocol errors, protocol.md 9 ---
    "error": m.Error(
        timestamp=_T,
        seq=11,
        code="schema_violation",
        message="message 'submit_order' does not match the schema",
        detail={"errors": [{"field": "volume", "problem": "Input should be > 0"}]},
        client_order_id="c-0003",
    ),
    # --- admin, client to server, protocol.md 10 ---
    "admin_start_round": m.AdminStartRound(
        timestamp=_T,
        seq=0,
        request_id="req-001",
        round_id="round_2026_t2_a",
        instruments=[
            m.InstrumentConfigWire(
                id="STOCK_A",
                process="OU",
                s0=100.0,
                mu=0.0,
                sigma=0.25,
                rho=0.6,
                tick_size="0.01",
                lot_size=1,
                position_limit=100,
                theta=2.0,
                mu_bar=100.0,
            )
        ],
        starting_cash=100000.0,
        position_limit=100,
        duration_s=1200.0,
        seed=20260828,
    ),
    "admin_end_round": m.AdminEndRound(
        timestamp=_T, seq=1, request_id="req-002", round_id="round_2026_t2_a"
    ),
    "admin_inject_news": m.AdminInjectNews(
        timestamp=_T,
        seq=2,
        request_id="req-003",
        event_id="news_001",
        headline="Q3 earnings significantly beat expectations.",
        affected_instruments=["STOCK_A"],
        jumps={"STOCK_A": 0.05},
    ),
    "admin_practice_control": m.AdminPracticeControl(
        timestamp=_T, seq=3, request_id="req-004", action="pause"
    ),
    "admin_cancel_team_orders": m.AdminCancelTeamOrders(
        timestamp=_T, seq=4, request_id="req-005", team_id="team_07"
    ),
    "admin_disconnect": m.AdminDisconnect(
        timestamp=_T,
        seq=5,
        request_id="req-006",
        connection_id="conn_9f2a",
        reason="runaway order rate",
    ),
    # --- admin, server to client, protocol.md 10 ---
    "admin_snapshot": m.AdminSnapshot(
        timestamp=_T,
        seq=0,
        session=m.AdminSessionInfo(
            session_id="sess_r3",
            session_state="RUNNING",
            ends_at=_T + 1200.0,
            round_id="round_2026_t2_a",
            starting_cash=100000.0,
            position_limit=100,
        ),
        instruments=[_INSTRUMENT],
        teams=[_TEAM_ROW],
        connections=[_CONNECTION_ROW],
    ),
    "admin_leaderboard": m.AdminLeaderboard(
        timestamp=_T, seq=1, as_of=_T, entries=[_TEAM_ROW]
    ),
    "admin_connections": m.AdminConnections(
        timestamp=_T, seq=2, connections=[_CONNECTION_ROW]
    ),
    "admin_health": m.AdminHealth(
        timestamp=_T,
        seq=3,
        instrument_id="STOCK_A",
        best_bid=99.5,
        best_ask=99.52,
        spread_ticks=2,
        bid_depth=55,
        ask_depth=25,
        trades_last_60s=87,
        quoting_ok=True,
    ),
    "admin_event": m.AdminEvent(
        timestamp=_T,
        seq=4,
        event_id="ev_0001",
        severity="warn",
        category="system",
        message="fair value floor hit on STOCK_B",
        detail={"instrument_id": "STOCK_B"},
    ),
    "admin_ack": m.AdminAck(
        timestamp=_T,
        seq=5,
        request_id="req-001",
        command="admin_start_round",
        detail={"round_id": "round_2026_t2_a"},
    ),
    "admin_rejected": m.AdminRejected(
        timestamp=_T,
        seq=6,
        request_id="req-002",
        command="admin_end_round",
        reason="round_id_mismatch",
    ),
}
