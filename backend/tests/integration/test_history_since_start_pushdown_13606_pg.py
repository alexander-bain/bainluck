"""#13606 — Real-Postgres plan & oracle equivalence contract for ``range=since_start`` pushdown.

Drives real PostgreSQL query planning (`EXPLAIN (FORMAT JSON)`) and the full
``get_event_odds_history_cached`` route against production index shapes (including
dense minute-aligned timestamps across multiple events, WITHOUT adding any new
`(event_id, captured_at)` index).

Runs on ``DELAY_CONTRACT_DATABASE_URL`` (CI ``database-integration`` ``isolated`` group).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.routes import events as events_route
from app.routes.events import (
    EVENT_HISTORY_IN_WINDOW_SNAPSHOT_CAP,
    EVENT_HISTORY_RANGE_SINCE_START,
    _build_odds_boundary_query_pg,
    _build_odds_window_query_pg,
    _build_win_prob_since_start_queries_pg,
    get_event_odds_history_cached,
)
from app.utils import event_history_cache as ehc

DB_URL = os.environ.get("DELAY_CONTRACT_DATABASE_URL")
UTC = timezone.utc

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set DELAY_CONTRACT_DATABASE_URL to run the #13606 real-Postgres "
            "history pushdown contract (CI `isolated` group provides one)"
        ),
    ),
]

_WANTED_TABLES = {
    "sports",
    "teams",
    "venues",
    "events",
    "odds_snapshots",
    "score_snapshots",
    "espn_snapshots",
    "win_prob_snapshots",
    "scoring_plays",
    "futures_markets",
    "futures_outcomes",
    "futures_odds_snapshots",
    "game_moments",
}

_EQUIVALENCE_KEYS = (
    "history",
    "bookmaker_history",
    "win_prob_history",
    "win_prob_sources",
    "aggregate_line",
    "espn_history",
    "score_history",
    "period_markers",
    "time_domain",
    "pre_window_omitted",
    "points",
    "bookmaker_count",
    "on_demand_backfill",
)


def _walk_plan_nodes(node: dict):
    yield node
    for child in node.get("Plans", ()):
        yield from _walk_plan_nodes(child)


async def _engine_with_tables():
    import app.models.models  # noqa: F401
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    wanted = [t for t in Base.metadata.sorted_tables if t.name in _WANTED_TABLES]
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        for table in reversed(wanted):
            await conn.execute(text(f'DROP TABLE IF EXISTS "{table.name}" CASCADE'))
        await conn.run_sync(Base.metadata.create_all, tables=wanted)
        # Ensure exact production indexes exist (and NO (event_id, captured_at) index),
        # INCLUDING the dangerous single-column captured_at indexes that must NOT be chosen.
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_winprob_event_source "
                "ON win_prob_snapshots (event_id, source)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_winprob_captured "
                "ON win_prob_snapshots (captured_at)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_winprob_event_source_captured "
                "ON win_prob_snapshots (event_id, source, captured_at)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_odds_snap_evt_bk_time "
                "ON odds_snapshots (event_id, bookmaker, captured_at)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_odds_snapshots_captured_at "
                "ON odds_snapshots (captured_at)"
            )
        )
    return engine


async def _seed_fixture_db(engine):
    """Seed five realistic events + dense shared-minute background rows."""
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    kickoff = now - timedelta(hours=10)
    completed = kickoff + timedelta(hours=3, minutes=10)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                'INSERT INTO sports (id, key, name, "group", active) VALUES '
                "(1, 'americanfootball_nfl', 'NFL', 'American Football', true), "
                "(2, 'basketball_nba', 'NBA', 'Basketball', true)"
            )
        )

        # Background events sharing minute-aligned timestamps so planner MCV stats are realistic
        for i in range(1, 151):
            await conn.execute(
                text(
                    "INSERT INTO events (id, sport_id, home_team_name, away_team_name, commence_time, "
                    "status, commence_time_source, completed_at, win_probability_sources, box_score_data) "
                    "VALUES (:id, 1, :h, :a, :ct, 'completed', 'espn', :comp, '{}'::jsonb, '{}'::jsonb)"
                ),
                {
                    "id": 9000 + i,
                    "h": f"BG Home {i}",
                    "a": f"BG Away {i}",
                    "ct": kickoff,
                    "comp": completed,
                },
            )

        wps_final = json.dumps(
            {
                "betting": {"prob": 0.68, "updated_at": completed.isoformat()},
                "kalshi": {"prob": 0.70, "updated_at": completed.isoformat()},
                "espn": {"prob": 0.69, "updated_at": completed.isoformat()},
            }
        )
        box_scores = json.dumps(
            {
                "scoring_plays": [
                    {
                        "period": "Q1",
                        "clock": "09:30",
                        "home_score": 7,
                        "away_score": 0,
                        "text": "Touchdown",
                    }
                ]
            }
        )

        # Event 1360601: normal finished NFL game (<3000 pre-kickoff odds, cross-kickoff carry-forward & #9111 candle)
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, external_id, espn_id, home_team_name, away_team_name, "
                "commence_time, status, commence_time_source, home_score, away_score, completed_at, "
                "win_probability_sources, box_score_data) "
                "VALUES (1360601, 1, 'ext_1', 'espn_1', 'San Francisco 49ers', 'Minnesota Vikings', "
                ":ct, 'completed', 'espn', 27, 20, :comp, CAST(:wps AS jsonb), CAST(:box AS jsonb))"
            ),
            {"ct": kickoff, "comp": completed, "wps": wps_final, "box": box_scores},
        )
        # Event 1360602: has an 'espn' win_prob source that stopped BEFORE kickoff - 25m
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, external_id, espn_id, home_team_name, away_team_name, "
                "commence_time, status, commence_time_source, home_score, away_score, completed_at, "
                "win_probability_sources, box_score_data) "
                "VALUES (1360602, 2, 'ext_2', 'espn_2', 'Golden State Warriors', 'Boston Celtics', "
                ":ct, 'completed', 'espn', 112, 106, :comp, CAST(:wps AS jsonb), '{}'::jsonb)"
            ),
            {"ct": kickoff, "comp": completed, "wps": wps_final},
        )
        # Event 1360603: zero post-kickoff data anywhere (and no score -> no synthetic final point -> hasPostStartData == False -> fail open)
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, external_id, home_team_name, away_team_name, "
                "commence_time, status, commence_time_source, home_score, away_score, completed_at, "
                "win_probability_sources, box_score_data) "
                "VALUES (1360603, 1, 'ext_3', 'Kansas City Chiefs', 'Buffalo Bills', "
                ":ct, 'completed', 'odds_api', NULL, NULL, :comp, '{}'::jsonb, '{}'::jsonb)"
            ),
            {"ct": kickoff, "comp": completed},
        )
        # Event 1360604: pre-kickoff rich (140 kalshi points) + thin in-game (12 kalshi points) -> no backfill trigger
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, external_id, home_team_name, away_team_name, "
                "commence_time, status, commence_time_source, home_score, away_score, completed_at, "
                "win_probability_sources, box_score_data) "
                "VALUES (1360604, 2, 'ext_4', 'Miami Heat', 'New York Knicks', "
                ":ct, 'completed', 'espn', 104, 99, :comp, CAST(:wps AS jsonb), '{}'::jsonb)"
            ),
            {"ct": kickoff, "comp": completed, "wps": wps_final},
        )
        await conn.execute(
            text(
                "INSERT INTO futures_markets (id, source, external_id, sport_id, event_id, name, category, "
                "mutually_exclusive, status, created_at) "
                "VALUES (77001, 'kalshi', 'KXNBA-TEST', 2, 1360604, 'Heat vs Knicks', 'winner', true, 'closed', :created)"
            ),
            {"created": kickoff - timedelta(days=5)},
        )

        # Shared minute-aligned background rows across 150 events (both pre-lookback and in-game)
        await conn.execute(
            text(
                """
                INSERT INTO win_prob_snapshots (event_id, source, captured_at, home_win_probability, away_win_probability, reading_count)
                SELECT 9001 + (g % 150),
                       CASE WHEN g % 2 = 0 THEN 'kalshi' ELSE 'polymarket' END,
                       CAST(:ts AS timestamptz) + ((g / 150) * interval '10 minutes'),
                       0.50, 0.50, 1
                FROM generate_series(0, 2999) g
            """
            ),
            {"ts": kickoff - timedelta(hours=3)},
        )
        await conn.execute(
            text(
                """
                INSERT INTO odds_snapshots (event_id, bookmaker, captured_at, home_win_probability, away_win_probability, reading_count)
                SELECT 9001 + (g % 150),
                       (ARRAY['draftkings','fanduel','betmgm','caesars'])[1 + (g % 4)],
                       CAST(:ts AS timestamptz) + ((g / 150) * interval '15 minutes'),
                       0.52, 0.48, 1
                FROM generate_series(0, 2399) g
            """
            ),
            {"ts": kickoff - timedelta(hours=4)},
        )

        # Event 1360601: rich pre-kickoff + 25m lookback + in-game + coherent/incoherent scores + #9111 candle
        for b_idx, bk in enumerate(
            ("draftkings", "fanduel", "betmgm", "caesars", "betrivers")
        ):
            for step in range(30):
                ts = kickoff - timedelta(hours=48) + timedelta(minutes=step * 90)
                await conn.execute(
                    text(
                        "INSERT INTO odds_snapshots (event_id, bookmaker, captured_at, home_moneyline, away_moneyline, "
                        "home_win_probability, away_win_probability, projected_home_score, projected_away_score, "
                        "reading_count, valid_until) "
                        "VALUES (1360601, :bk, :ts, -135, 115, :hp, :ap, 24.5, 20.5, 1, :vu)"
                    ),
                    {
                        "bk": bk,
                        "ts": ts,
                        "hp": round(0.55 + (step % 5) * 0.01, 4),
                        "ap": round(0.45 - (step % 5) * 0.01, 4),
                        "vu": ts + timedelta(minutes=90),
                    },
                )
            for m in range(0, 180, 5):
                ts = kickoff + timedelta(minutes=m)
                hp = round(0.56 + (m / 180.0) * 0.25 - (b_idx * 0.01), 4)
                await conn.execute(
                    text(
                        "INSERT INTO odds_snapshots (event_id, bookmaker, captured_at, home_moneyline, away_moneyline, "
                        "home_win_probability, away_win_probability, projected_home_score, projected_away_score, reading_count) "
                        "VALUES (1360601, :bk, :ts, -145, 125, :hp, :ap, :phs, :pas, 1)"
                    ),
                    {
                        "bk": bk,
                        "ts": ts,
                        "hp": hp,
                        "ap": round(1.0 - hp, 4),
                        # Include an incoherent score on betrivers minute 0 to prove hoisted refusal matches
                        "phs": 17.0 if (bk == "betrivers" and m == 0) else 27.0,
                        "pas": 24.0 if (bk == "betrivers" and m == 0) else 20.0,
                    },
                )

        # Event 1360601 win_prob_snapshots: old pre-kickoff, 25m lookback carry-forward, #9111 candle, in-game
        await conn.execute(
            text(
                "INSERT INTO win_prob_snapshots (event_id, source, captured_at, home_win_probability, away_win_probability, game_state, reading_count) "
                "VALUES "
                "(1360601, 'kalshi', :old_k, 0.54, 0.46, '{\"poll_type\":\"live_fast\"}', 1), "
                "(1360601, 'kalshi', :lb_live, 0.57, 0.43, '{\"poll_type\":\"ws_fast_lane\"}', 1), "
                "(1360601, 'kalshi', :candle, 0.41, 0.59, '{\"poll_type\":\"history_backfill\"}', 1), "
                '(1360601, \'kalshi\', :in_live, 0.62, 0.38, \'{"period":"Q1","poll_type":"ws_fast_lane"}\', 1), '
                "(1360601, 'espn', :old_k, 0.55, 0.45, '{}', 1), "
                "(1360601, 'espn', :in_espn, 0.66, 0.34, '{\"period\":\"Q2\"}', 1)"
            ),
            {
                "old_k": kickoff - timedelta(hours=3),
                "lb_live": kickoff - timedelta(minutes=6),
                "candle": kickoff + timedelta(minutes=1),
                "in_live": kickoff + timedelta(minutes=5),
                "in_espn": kickoff + timedelta(minutes=40),
            },
        )
        await conn.execute(
            text(
                "INSERT INTO espn_snapshots (event_id, captured_at, home_win_probability, away_win_probability, home_score, away_score, game_clock, period) "
                "VALUES (1360601, :t1, 0.60, 0.40, 7, 0, '09:30', 'Q1')"
            ),
            {"t1": kickoff + timedelta(minutes=12)},
        )

        # Event 1360602: espn exists ONLY at -2h (pre-lookback), kalshi spans in-game
        await conn.execute(
            text(
                "INSERT INTO win_prob_snapshots (event_id, source, captured_at, home_win_probability, away_win_probability, reading_count) "
                "VALUES "
                "(1360602, 'espn', :pre_only, 0.53, 0.47, 1), "
                "(1360602, 'kalshi', :pre_only, 0.52, 0.48, 1), "
                "(1360602, 'kalshi', :g1, 0.60, 0.40, 1), "
                "(1360602, 'kalshi', :g2, 0.72, 0.28, 1)"
            ),
            {
                "pre_only": kickoff - timedelta(hours=2),
                "g1": kickoff + timedelta(minutes=15),
                "g2": kickoff + timedelta(minutes=90),
            },
        )

        # Event 1360603: ONLY pre-kickoff odds & win_prob (zero post-kickoff rows)
        for step in range(5):
            ts = kickoff - timedelta(hours=10 - step)
            await conn.execute(
                text(
                    "INSERT INTO odds_snapshots (event_id, bookmaker, captured_at, home_win_probability, away_win_probability, reading_count) "
                    "VALUES (1360603, 'draftkings', :ts, :hp, :ap, 1)"
                ),
                {"ts": ts, "hp": 0.51 + step * 0.01, "ap": 0.49 - step * 0.01},
            )
            await conn.execute(
                text(
                    "INSERT INTO win_prob_snapshots (event_id, source, captured_at, home_win_probability, away_win_probability, reading_count) "
                    "VALUES (1360603, 'kalshi', :ts, :hp, :ap, 1)"
                ),
                {"ts": ts, "hp": 0.52 + step * 0.01, "ap": 0.48 - step * 0.01},
            )

        # Event 1360604: 140 pre-kickoff kalshi rows + 12 in-game kalshi rows (total 152 >= 120)
        await conn.execute(
            text(
                """
                INSERT INTO win_prob_snapshots (event_id, source, captured_at, home_win_probability, away_win_probability, reading_count)
                SELECT 1360604, 'kalshi', CAST(:ts AS timestamptz) + (g * interval '15 minutes'), 0.55, 0.45, 1
                FROM generate_series(0, 139) g
            """
            ),
            {"ts": kickoff - timedelta(days=3)},
        )
        await conn.execute(
            text(
                """
                INSERT INTO win_prob_snapshots (event_id, source, captured_at, home_win_probability, away_win_probability, reading_count)
                SELECT 1360604, 'kalshi', CAST(:ts AS timestamptz) + (g * interval '10 minutes'), 0.65, 0.35, 1
                FROM generate_series(0, 11) g
            """
            ),
            {"ts": kickoff + timedelta(minutes=5)},
        )

    async with engine.connect() as conn:
        ac = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await ac.execute(text("VACUUM ANALYZE"))

    return kickoff, completed


@pytest.fixture
async def pg_seeded():
    engine = await _engine_with_tables()
    try:
        kickoff, completed = await _seed_fixture_db(engine)
        yield engine, kickoff, completed
    finally:
        await engine.dispose()


async def _fetch_history_payload(maker, event_id: int, chart_range: str) -> dict:
    ehc._reset_for_tests()
    async with maker() as db:
        resp = await get_event_odds_history_cached(
            event_id,
            hours=48,
            chart_range=chart_range,
            response=None,
            db=db,
            fresh=False,
        )
    return json.loads(resp.body)


async def test_explain_uses_composite_indexes_and_avoids_captured_at_traps(pg_seeded):
    engine, kickoff, completed = pg_seeded
    end_cap = completed + timedelta(minutes=30)

    wp_in, wp_bd = _build_win_prob_since_start_queries_pg(
        1360601, window_start=kickoff, end_cap=end_cap
    )
    odds_win = _build_odds_window_query_pg(
        1360601,
        lower_bound=kickoff,
        upper_le=end_cap,
        limit=EVENT_HISTORY_IN_WINDOW_SNAPSHOT_CAP,
    )
    odds_bd = _build_odds_boundary_query_pg(1360601, before=kickoff, end_cap=end_cap)

    statements = [
        (
            "wp_in",
            wp_in,
            {"ix_winprob_event_source", "ix_winprob_event_source_captured"},
        ),
        (
            "wp_boundary",
            wp_bd,
            {"ix_winprob_event_source", "ix_winprob_event_source_captured"},
        ),
        (
            "odds_window",
            odds_win,
            {"ix_odds_snap_evt_bk_time", "ix_odds_snapshots_event_bookmaker_captured"},
        ),
        (
            "odds_boundary",
            odds_bd,
            {"ix_odds_snap_evt_bk_time", "ix_odds_snapshots_event_bookmaker_captured"},
        ),
    ]

    async with engine.connect() as conn:
        for label, stmt, allowed_indexes in statements:
            compiled = stmt.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
            res = await conn.exec_driver_sql("EXPLAIN (FORMAT JSON) " + str(compiled))
            plan_root = res.scalar_one()[0]["Plan"]
            nodes = list(_walk_plan_nodes(plan_root))

            seq_scans = [
                n.get("Relation Name")
                for n in nodes
                if n.get("Node Type") == "Seq Scan"
                and n.get("Relation Name") in ("win_prob_snapshots", "odds_snapshots")
            ]
            assert not seq_scans, f"{label} regressed to Seq Scan: {seq_scans}"

            indexes = {n.get("Index Name") for n in nodes if n.get("Index Name")}
            assert (
                "ix_winprob_captured" not in indexes
            ), f"{label} hit ix_winprob_captured: {indexes}"
            assert (
                "ix_odds_snapshots_captured_at" not in indexes
            ), f"{label} hit ix_odds_snapshots_captured_at: {indexes}"
            assert (
                indexes & allowed_indexes
            ), f"{label} did not use composite index: {indexes}"


async def test_since_start_pushdown_matches_full_oracle_on_normal_game(
    pg_seeded, monkeypatch
):
    engine, _, _ = pg_seeded
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    pushed = await _fetch_history_payload(
        maker, 1360601, EVENT_HISTORY_RANGE_SINCE_START
    )
    monkeypatch.setattr(events_route, "_is_postgresql_session", lambda db: False)
    oracle = await _fetch_history_payload(
        maker, 1360601, EVENT_HISTORY_RANGE_SINCE_START
    )

    assert pushed["pre_window_omitted"] is True
    for key in _EQUIVALENCE_KEYS:
        assert pushed[key] == oracle[key], f"Mismatch on key {key}"


async def test_since_start_pushdown_preserves_pre_only_source_and_fails_open(
    pg_seeded, monkeypatch
):
    engine, _, _ = pg_seeded
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Event 1360602: espn had pre-kickoff-only readings, kalshi had in-game readings
    pushed_pre_src = await _fetch_history_payload(
        maker, 1360602, EVENT_HISTORY_RANGE_SINCE_START
    )
    # Event 1360603: hasPostStartData == False -> must fail open cleanly with full pre-kickoff journey
    pushed_no_post = await _fetch_history_payload(
        maker, 1360603, EVENT_HISTORY_RANGE_SINCE_START
    )

    monkeypatch.setattr(events_route, "_is_postgresql_session", lambda db: False)
    oracle_pre_src = await _fetch_history_payload(
        maker, 1360602, EVENT_HISTORY_RANGE_SINCE_START
    )
    oracle_no_post = await _fetch_history_payload(
        maker, 1360603, EVENT_HISTORY_RANGE_SINCE_START
    )

    assert "espn" in pushed_pre_src["win_prob_history"]
    assert pushed_pre_src["win_prob_history"]["espn"] == []
    assert pushed_pre_src["win_prob_sources"]["espn"]["snapshot_count"] == 0
    for key in _EQUIVALENCE_KEYS:
        assert pushed_pre_src[key] == oracle_pre_src[key], f"1360602 mismatch on {key}"

    assert pushed_no_post["pre_window_omitted"] is False
    assert pushed_no_post["points"] == 5
    for key in _EQUIVALENCE_KEYS:
        assert pushed_no_post[key] == oracle_no_post[key], f"1360603 mismatch on {key}"


async def test_since_start_pushdown_does_not_false_trigger_on_demand_backfill(
    pg_seeded, monkeypatch
):
    engine, _, _ = pg_seeded
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Event 1360604 has 140 pre-kickoff kalshi rows and only 12 in-game kalshi rows.
    # Both pushdown and oracle must see total >= THIN_MAX_EXPECTED_POINTS (120) and return None.
    pushed = await _fetch_history_payload(
        maker, 1360604, EVENT_HISTORY_RANGE_SINCE_START
    )
    monkeypatch.setattr(events_route, "_is_postgresql_session", lambda db: False)
    oracle = await _fetch_history_payload(
        maker, 1360604, EVENT_HISTORY_RANGE_SINCE_START
    )

    assert pushed["on_demand_backfill"] is None
    assert oracle["on_demand_backfill"] is None
    for key in _EQUIVALENCE_KEYS:
        assert pushed[key] == oracle[key], f"1360604 mismatch on {key}"


async def test_snapshots_with_split_budget_pg_matches_range_all_oracle(
    pg_seeded, monkeypatch
):
    engine, _, _ = pg_seeded
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    pushed_all = await _fetch_history_payload(maker, 1360601, "all")
    monkeypatch.setattr(events_route, "_is_postgresql_session", lambda db: False)
    oracle_all = await _fetch_history_payload(maker, 1360601, "all")

    assert pushed_all["pre_window_omitted"] is False
    assert pushed_all["snapshot_count"] == oracle_all["snapshot_count"]
    for key in _EQUIVALENCE_KEYS:
        assert pushed_all[key] == oracle_all[key], f"range=all mismatch on {key}"
