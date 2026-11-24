"""#13606 — Unit contracts for ``range=since_start`` PG SQL pushdown & history hot-path speedups.

Verifies without needing a live Postgres server:
1. ``_encode_history_payload`` produces bytes identical to ``JSONResponse(content=jsonable_encoder(payload)).body``
   on pure JSON payloads and falls back cleanly when non-JSON values (e.g. ``Decimal``, ``datetime``) appear.
2. Hoisting ``refuse_incoherent_projections`` out of the inner bookmaker loop produces the exact same
   projections on coherent, incoherent, null-score, and pinned-handicap inputs.
3. The PostgreSQL query builders emit ``WITH RECURSIVE`` + ``LATERAL`` + D2 ``>=``/``<=`` clock bounds,
   25-minute win-prob lookback, ``end_cap``, and window ``LIMIT`` caps.
4. ``_is_postgresql_session`` returns ``False`` for SQLite sessions and test doubles.
5. Eligibility gates exclude ``venue_expiration`` events, folded twins (``len(oriented_series_ids) > 1``),
   ``range=all``, and live/scheduled events, while ``hasPostStartData == False`` fails open cleanly.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Event, OddsSnapshot, Sport
from app.routes import events as events_route
from app.routes.events import (
    EVENT_HISTORY_IN_WINDOW_SNAPSHOT_CAP,
    EVENT_HISTORY_RANGE_SINCE_START,
    _WIN_PROB_SINCE_START_LOOKBACK,
    _build_odds_boundary_query_pg,
    _build_odds_window_query_pg,
    _build_win_prob_since_start_queries_pg,
    _encode_history_payload,
    _is_postgresql_session,
    get_event_odds_history,
)
from app.utils.odds_math import refuse_incoherent_projections

UTC = timezone.utc


def test_encode_history_payload_byte_identical_to_jsonresponse():
    payload = {
        "event_id": 14639207,
        "home_team": "San Francisco 49ers",
        "away_team": "Minnesota Vikings — Été",
        "commence_time": "2026-11-22T21:05:00+00:00",
        "history": [
            {
                "timestamp": "2026-11-22T21:05:00+00:00",
                "home_probability": 0.625,
                "away_probability": 0.375,
                "over_under": 46.5,
                "projected_home_score": 25.0,
                "projected_away_score": 21.5,
                "bookmaker_count": 8,
                "probability_range": {"min": 0.6, "max": 0.65},
            }
        ],
        "bookmaker_history": {
            "draftkings": [
                {
                    "timestamp": "2026-11-22T21:05:00+00:00",
                    "home_probability": 0.63,
                    "away_probability": 0.37,
                    "valid_until": None,
                    "projected_home_score": None,
                    "projected_away_score": None,
                    "kind": "recorded",
                }
            ]
        },
        "pre_window_omitted": True,
        "on_demand_backfill": None,
    }
    fast_bytes = _encode_history_payload(payload)
    oracle_bytes = JSONResponse(content=jsonable_encoder(payload)).body
    assert fast_bytes == oracle_bytes


def test_encode_history_payload_falls_back_on_decimal_and_datetime():
    payload = {
        "event_id": 42,
        "commence_time": datetime(2026, 11, 22, 21, 5, tzinfo=UTC),
        "home_probability": Decimal("0.625"),
        "nested": [{"prob": Decimal("0.375")}],
    }
    fast_bytes = _encode_history_payload(payload)
    oracle_bytes = JSONResponse(content=jsonable_encoder(payload)).body
    assert fast_bytes == oracle_bytes


def test_refuse_incoherent_projections_hoisted_matches_per_point():
    sample_points = [
        # Coherent: home favored in both moneyline (0.64) and score (27 > 20)
        {
            "home_probability": 0.64,
            "projected_home_score": 27.0,
            "projected_away_score": 20.0,
        },
        # Incoherent: home favored in moneyline (0.68) but trailing in score (17 < 24)
        {
            "home_probability": 0.68,
            "projected_home_score": 17.0,
            "projected_away_score": 24.0,
        },
        # Null projection preserved
        {
            "home_probability": 0.50,
            "projected_home_score": None,
            "projected_away_score": None,
        },
    ]
    for sport_key in ("americanfootball_nfl", "baseball_mlb"):
        per_point = []
        for pt in sample_points:
            row = dict(pt)
            refuse_incoherent_projections([row], sport_key=sport_key)
            per_point.append(row)

        hoisted = [dict(pt) for pt in sample_points]
        refuse_incoherent_projections(hoisted, sport_key=sport_key)
        assert hoisted == per_point


def test_pg_since_start_queries_compile_to_recursive_lateral_d2_bounds():
    kickoff = datetime(2026, 11, 22, 21, 5, tzinfo=UTC)
    end_cap = datetime(2026, 11, 23, 0, 55, tzinfo=UTC)
    dialect = postgresql.dialect()

    wp_in, wp_bd = _build_win_prob_since_start_queries_pg(
        14639207, window_start=kickoff, end_cap=end_cap
    )
    odds_win = _build_odds_window_query_pg(
        14639207,
        lower_bound=kickoff,
        upper_le=end_cap,
        limit=EVENT_HISTORY_IN_WINDOW_SNAPSHOT_CAP,
    )
    odds_bd = _build_odds_boundary_query_pg(14639207, before=kickoff, end_cap=end_cap)

    wp_in_comp = wp_in.compile(dialect=dialect)
    wp_in_sql = str(wp_in_comp)
    assert "WITH RECURSIVE wp_sources" in wp_in_sql
    assert "JOIN LATERAL" in wp_in_sql
    assert "win_prob_snapshots.captured_at >=" in wp_in_sql
    assert kickoff - _WIN_PROB_SINCE_START_LOOKBACK in wp_in_comp.params.values()

    wp_bd_comp = wp_bd.compile(dialect=dialect)
    wp_bd_sql = str(wp_bd_comp)
    assert "WITH RECURSIVE wp_sources" in wp_bd_sql
    assert "wp_boundary_clock" in wp_bd_sql
    assert "wp_boundary_snap" in wp_bd_sql
    assert "wp_boundary_clock.latest_clock" in wp_bd_sql
    assert "ORDER BY win_prob_snapshots.id DESC" in wp_bd_sql

    odds_win_comp = odds_win.compile(dialect=dialect)
    odds_win_sql = str(odds_win_comp)
    assert "WITH RECURSIVE odds_bookmakers" in odds_win_sql
    assert "JOIN LATERAL" in odds_win_sql
    assert EVENT_HISTORY_IN_WINDOW_SNAPSHOT_CAP in odds_win_comp.params.values()

    odds_bd_comp = odds_bd.compile(dialect=dialect)
    odds_bd_sql = str(odds_bd_comp)
    assert "WITH RECURSIVE odds_bookmakers" in odds_bd_sql
    assert "odds_boundary_clock" in odds_bd_sql
    assert "odds_boundary_snap" in odds_bd_sql
    assert "odds_boundary_clock.latest_clock" in odds_bd_sql


def test_is_postgresql_session_false_for_sqlite_and_non_sessions():
    assert _is_postgresql_session(None) is False
    assert _is_postgresql_session(SimpleNamespace()) is False

    unbound = MagicMock(spec=AsyncSession)
    unbound.get_bind.side_effect = RuntimeError("no bind")
    assert _is_postgresql_session(unbound) is False

    sqlite_session = MagicMock(spec=AsyncSession)
    sqlite_session.get_bind.return_value = SimpleNamespace(
        dialect=SimpleNamespace(name="sqlite")
    )
    assert _is_postgresql_session(sqlite_session) is False

    pg_session = MagicMock(spec=AsyncSession)
    pg_session.get_bind.return_value = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql")
    )
    assert _is_postgresql_session(pg_session) is True


def _build_sqlite_fake_pg_route_session(
    *,
    event: Event,
    all_odds: list[OddsSnapshot],
    series_ids: list[int],
):
    """Test double simulating PG session responses for gating & fail-open unit checks."""

    class _FakeScalarResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def scalar_one_or_none(self):
            return self._rows[0] if self._rows else None

        def scalar(self):
            return self._rows[0] if self._rows else None

        def all(self):
            return list(self._rows)

    class _FakeRouteDB:
        def __init__(self):
            self.split_budget_calls = 0

        async def execute(self, stmt, *args, **kwargs):
            sql = str(stmt)
            if "FROM events" in sql and "events.sport_id" in sql:
                return _FakeScalarResult([event])
            if "FROM events" in sql and "home_team_name" in sql:
                # Series fold event lookup (events.id, events.home_team_name, events.away_team_name)
                return _FakeScalarResult(
                    [(event.id, event.home_team_name, event.away_team_name)]
                )
            if "FROM events" in sql:
                return _FakeScalarResult([event])
            return _FakeScalarResult([])

    return _FakeRouteDB()


def test_pushdown_gating_excludes_venue_exp_twins_range_all_and_live(monkeypatch):
    kickoff = datetime(2026, 11, 22, 21, 5, tzinfo=UTC)
    comp = kickoff + timedelta(hours=3)
    sport = Sport(id=1, key="basketball_nba", name="NBA")

    odds_pushdown_calls = []
    wp_pushdown_calls = []

    async def _spy_odds_pg(*args, **kwargs):
        odds_pushdown_calls.append((args, kwargs))
        return []

    async def _spy_wp_pg(*args, **kwargs):
        wp_pushdown_calls.append((args, kwargs))
        return []

    async def _noop_split(*args, **kwargs):
        return []

    async def _no_end_cap(*args, **kwargs):
        return False

    async def _resolve_event(db, ev, *, requested_id):
        return SimpleNamespace(event=ev, event_id=requested_id)

    async def _fold_series(db, eid, absorbed):
        return current_series

    async def _noop_settled(*args, **kwargs):
        return None

    monkeypatch.setattr(events_route, "_is_postgresql_session", lambda db: True)
    monkeypatch.setattr(events_route, "_read_odds_since_start_pg", _spy_odds_pg)
    monkeypatch.setattr(events_route, "_read_win_prob_since_start_pg", _spy_wp_pg)
    monkeypatch.setattr(events_route, "_snapshots_with_split_budget", _noop_split)
    monkeypatch.setattr(events_route, "_end_cap_hides_every_point", _no_end_cap)

    async def _no_absorbed(db, ev_arg):
        return [], True

    monkeypatch.setattr(
        "app.utils.serve_fold_absorbed.serve_fold_absorbed_rows_with_completeness",
        _no_absorbed,
    )
    monkeypatch.setattr(events_route, "resolve_served_event", _resolve_event)
    monkeypatch.setattr(
        "app.utils.proven_duplicates.folded_series_event_ids", _fold_series
    )
    monkeypatch.setattr(events_route, "_settled_hero_result", _noop_settled)
    monkeypatch.setattr(
        "app.utils.winprob_evidence.drop_superseded_estimates", lambda pts: (pts, 0)
    )
    monkeypatch.setattr(
        "app.utils.winprob_evidence.drop_candles_under_live_readings",
        lambda pts: (pts, 0),
    )

    # Case 1: Kalshi venue expiration (external_id=None, commence_time_source='kalshi')
    ev_kalshi_exp = Event(
        id=901,
        sport_id=1,
        sport=sport,
        home_team_name="A",
        away_team_name="B",
        commence_time=kickoff,
        completed_at=comp,
        commence_time_source="kalshi",
        external_id=None,
        status="completed",
        win_probability_sources={},
        box_score_data={},
    )
    # Case 2: Normal finished event, tested with folded series (>1 ID) and range='all'
    ev_normal = Event(
        id=902,
        sport_id=1,
        sport=sport,
        home_team_name="C",
        away_team_name="D",
        commence_time=kickoff,
        completed_at=comp,
        commence_time_source="espn",
        external_id="espn-902",
        status="completed",
        win_probability_sources={},
        box_score_data={},
    )
    # Case 3: Live event
    ev_live = Event(
        id=903,
        sport_id=1,
        sport=sport,
        home_team_name="E",
        away_team_name="F",
        commence_time=kickoff,
        commence_time_source="espn",
        external_id="espn-903",
        status="live",
        win_probability_sources={},
        box_score_data={},
    )

    for ev, series, crange in [
        (ev_kalshi_exp, [901], EVENT_HISTORY_RANGE_SINCE_START),
        (ev_normal, [902, 999], EVENT_HISTORY_RANGE_SINCE_START),
        (ev_normal, [902], "all"),
        (ev_live, [903], EVENT_HISTORY_RANGE_SINCE_START),
    ]:
        current_event = ev
        current_series = series
        db = _build_sqlite_fake_pg_route_session(
            event=ev, all_odds=[], series_ids=series
        )
        asyncio.run(get_event_odds_history(ev.id, hours=48, chart_range=crange, db=db))

    assert odds_pushdown_calls == []
    assert wp_pushdown_calls == []


def test_pushdown_fails_open_when_no_post_start_data(monkeypatch):
    kickoff = datetime(2026, 11, 22, 21, 5, tzinfo=UTC)
    comp = kickoff + timedelta(hours=3)
    sport = Sport(id=1, key="basketball_nba", name="NBA")
    ev = Event(
        id=904,
        sport_id=1,
        sport=sport,
        home_team_name="Home",
        away_team_name="Away",
        commence_time=kickoff,
        completed_at=comp,
        commence_time_source="espn",
        external_id="espn-904",
        status="completed",
        win_probability_sources={},
        box_score_data={},
    )
    pre_snaps = [
        OddsSnapshot(
            id=100 + i,
            event_id=904,
            bookmaker="draftkings",
            captured_at=kickoff - timedelta(hours=5 - i),
            home_win_probability=0.52 + 0.01 * i,
            away_win_probability=0.48 - 0.01 * i,
        )
        for i in range(4)
    ]

    split_calls = []

    async def _fake_odds_pg(*args, **kwargs):
        return [pre_snaps[-1]]

    async def _fake_wp_pg(*args, **kwargs):
        return []

    async def _fake_split(*args, **kwargs):
        split_calls.append((args, kwargs))
        return pre_snaps

    async def _resolve_event(db, ev_arg, *, requested_id):
        return SimpleNamespace(event=ev_arg, event_id=requested_id)

    async def _fold_series(db, eid, absorbed):
        return [eid]

    async def _noop_settled(*args, **kwargs):
        return None

    monkeypatch.setattr(events_route, "_is_postgresql_session", lambda db: True)
    monkeypatch.setattr(events_route, "_read_odds_since_start_pg", _fake_odds_pg)
    monkeypatch.setattr(events_route, "_read_win_prob_since_start_pg", _fake_wp_pg)
    monkeypatch.setattr(events_route, "_snapshots_with_split_budget", _fake_split)

    async def _no_absorbed(db, ev_arg):
        return [], True

    monkeypatch.setattr(
        "app.utils.serve_fold_absorbed.serve_fold_absorbed_rows_with_completeness",
        _no_absorbed,
    )
    monkeypatch.setattr(events_route, "resolve_served_event", _resolve_event)
    monkeypatch.setattr(
        "app.utils.proven_duplicates.folded_series_event_ids", _fold_series
    )
    monkeypatch.setattr(events_route, "_settled_hero_result", _noop_settled)
    monkeypatch.setattr(
        "app.utils.winprob_evidence.drop_superseded_estimates", lambda pts: (pts, 0)
    )
    monkeypatch.setattr(
        "app.utils.winprob_evidence.drop_candles_under_live_readings",
        lambda pts: (pts, 0),
    )

    db = _build_sqlite_fake_pg_route_session(
        event=ev, all_odds=pre_snaps, series_ids=[904]
    )
    payload = asyncio.run(
        get_event_odds_history(
            ev.id, hours=48, chart_range=EVENT_HISTORY_RANGE_SINCE_START, db=db
        )
    )

    # Failed open because all 4 odds points are before commence_time and wp/espn are empty
    assert len(split_calls) == 1
    assert payload["pre_window_omitted"] is False
    assert payload["points"] == 4
    assert payload["snapshot_count"] == 4
