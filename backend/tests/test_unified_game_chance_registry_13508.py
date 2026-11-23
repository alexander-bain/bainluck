"""Standing registry + unit tests for the unified game-chance reader (#13508 / #13502).

Fails CI if any mounted non-admin GET route serves game chances without
routing through :func:`app.utils.unified_game_read.load_unified_game_reads`, or if
any registered handler re-introduces duplicated snapshot aggregation.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.routing import APIRoute

from app.main import app
from app.utils.unified_game_read import (
    UNIFIED_GAME_CHANCE_ADDRESSES,
    UNIFIED_GAME_CHANCE_EXEMPTIONS,
    load_unified_game_reads,
    resolve_unified_card_chance,
)

_GAME_CHANCE_KEYS = frozenset({
    "hero_probability",
    "home_win_probability",
    "win_probability",
    "current_odds",
    "prob_home",
    "draw_probability",
})


def _resolve_target(module_name: str, func_name: str):
    mod = importlib.import_module(module_name)
    return getattr(mod, func_name)


def _calls_in_ast(fn) -> set[str]:
    src = inspect.getsource(fn)
    tree = ast.parse(src.lstrip())
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    return calls


def _source_mentions_event_and_chance(fn) -> bool:
    try:
        src = inspect.getsource(fn)
    except (OSError, TypeError):
        return False
    return ("Event" in src or "OddsSnapshot" in src) and any(
        f'"{key}"' in src or f"'{key}'" in src for key in _GAME_CHANCE_KEYS
    )


def test_every_registered_game_chance_handler_calls_unified_loader():
    assert UNIFIED_GAME_CHANCE_ADDRESSES
    for address, (module_name, func_name) in UNIFIED_GAME_CHANCE_ADDRESSES.items():
        fn = _resolve_target(module_name, func_name)
        calls = _calls_in_ast(fn)
        assert "load_unified_game_reads" in calls, (
            f"{address} ({module_name}:{func_name}) no longer calls load_unified_game_reads"
        )
        assert "aggregate_bookmaker_odds" not in calls, (
            f"{address} ({module_name}:{func_name}) duplicated aggregate_bookmaker_odds"
        )
        assert "group_latest_snapshots_by_event" not in calls, (
            f"{address} ({module_name}:{func_name}) duplicated group_latest_snapshots_by_event"
        )


def test_no_mounted_non_admin_get_route_serves_game_chances_outside_registry():
    unregistered: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if "GET" not in (route.methods or set()):
            continue
        path = route.path
        if not path.startswith("/api/") or path.startswith("/api/admin"):
            continue
        key = f"GET {path}"
        if key in UNIFIED_GAME_CHANCE_ADDRESSES or key in UNIFIED_GAME_CHANCE_EXEMPTIONS:
            continue
        if not _source_mentions_event_and_chance(route.endpoint):
            continue
        # Endpoints whose helpers are registered under UNIFIED_GAME_CHANCE_ADDRESSES
        # (e.g. feed router mounting `_score_events`) are matched above via `key`.
        unregistered.append(f"{key} -> {route.endpoint.__module__}:{route.endpoint.__name__}")

    assert not unregistered, (
        "Mounted game-chance GET routes must join UNIFIED_GAME_CHANCE_ADDRESSES "
        f"(or justify non-chance status in UNIFIED_GAME_CHANCE_EXEMPTIONS): {unregistered}"
    )


def _mock_db(sports: list[Any], extras: list[Any], snapshots: list[Any]):
    def _res(rows=(), *, scalars=()):
        r = MagicMock()
        r.all.return_value = list(rows)
        r.scalars.return_value.all.return_value = list(scalars)
        return r

    async def execute(stmt, *args, **kwargs):
        sql = str(stmt).lower()
        if "from sports" in sql:
            return _res(
                rows=[(s.id, s.key) for s in sports],
                scalars=sports,
            )
        if "from odds_snapshots" in sql or "odds_bookmakers" in sql or "with recursive" in sql:
            return _res(scalars=snapshots)
        if "events.id !=" in sql or "events.id not in" in sql or "contains" in sql or "events.event_tags" in sql:
            if "events.home_team_name" in sql and "events.commence_time" not in sql:
                # Tagged duplicate queries
                return _res(rows=[])
            return _res(scalars=extras)
        return _res()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=execute)
    return db


@pytest.mark.asyncio
async def test_unified_read_merges_catchall_blackpool_and_asvel_shapes():
    now = datetime.now(timezone.utc)
    commence = now + timedelta(hours=3)
    l1 = SimpleNamespace(id=101, key="soccer_england_league1", name="League One")
    other_s = SimpleNamespace(id=102, key="soccer_other", name="Soccer Other")
    el = SimpleNamespace(id=201, key="basketball_euroleague", name="EuroLeague")
    other_b = SimpleNamespace(id=202, key="basketball_other", name="Basketball Other")

    # 1. Blackpool: canonical on L1 has betting (0.2308) + 7 books + stale opening (0.23, 0.25);
    # untagged twin on soccer_other holds Polymarket (0.23) + 2 additional books (0.2308 / 0.2292 / draw ~0.54 -> 0.54? Wait: away=0.54, draw=0.23).
    bp_canon = SimpleNamespace(
        id=15350517,
        sport_id=101,
        sport=l1,
        home_team_name="Blackpool",
        away_team_name="Leicester City",
        commence_time=commence,
        status="scheduled",
        home_score=None,
        away_score=None,
        completed_at=None,
        win_probability_sources={
            "betting": {"value": 0.2308, "updated_at": now.isoformat()},
            "betting_book_count": 7,
        },
        opening_home_probability=0.23,
        opening_away_probability=0.25,
        espn_id="bp-1",
        external_id="oa-bp-1",
        statpal_fixture_id=None,
        event_tags=None,
    )
    bp_twin = SimpleNamespace(
        id=990517,
        sport_id=102,
        sport=other_s,
        home_team_name="Blackpool FC",
        away_team_name="Leicester",
        commence_time=commence,
        status="scheduled",
        home_score=None,
        away_score=None,
        completed_at=None,
        win_probability_sources={
            "polymarket": {"value": 0.23, "updated_at": now.isoformat()},
        },
        opening_home_probability=None,
        opening_away_probability=None,
        espn_id=None,
        external_id=None,
        statpal_fixture_id=None,
        event_tags=None,
    )

    # 2. ASVEL: canonical has Kalshi (0.49) + 5 books; untagged basketball_other twin holds Polymarket + 2 books.
    as_canon = SimpleNamespace(
        id=15351540,
        sport_id=201,
        sport=el,
        home_team_name="ASVEL",
        away_team_name="Olimpia Milano",
        commence_time=commence,
        status="scheduled",
        home_score=None,
        away_score=None,
        completed_at=None,
        win_probability_sources={
            "kalshi": {"value": 0.49, "updated_at": now.isoformat()},
            "betting": {"value": 0.5021, "updated_at": now.isoformat()},
            "betting_book_count": 5,
        },
        opening_home_probability=0.50,
        opening_away_probability=0.50,
        espn_id="as-1",
        external_id="oa-as-1",
        statpal_fixture_id=None,
        event_tags=None,
    )
    as_twin = SimpleNamespace(
        id=991540,
        sport_id=202,
        sport=other_b,
        home_team_name="ASVEL Lyon Villeurbanne",
        away_team_name="Pallacanestro Olimpia Milano",
        commence_time=commence,
        status="scheduled",
        home_score=None,
        away_score=None,
        completed_at=None,
        win_probability_sources={
            "polymarket": {"value": 0.485, "updated_at": now.isoformat()},
        },
        opening_home_probability=None,
        opening_away_probability=None,
        espn_id=None,
        external_id=None,
        statpal_fixture_id=None,
        event_tags=None,
    )

    def _snap(eid, bk, hp, ap):
        return SimpleNamespace(
            id=eid * 100 + hash(bk) % 90,
            event_id=eid,
            bookmaker=bk,
            home_win_probability=hp,
            away_win_probability=ap,
            home_moneyline=None,
            away_moneyline=None,
            home_spread=None,
            over_under=None,
            projected_home_score=None,
            projected_away_score=None,
            captured_at=now - timedelta(minutes=1),
            valid_until=now + timedelta(minutes=5),
        )

    snaps = [
        *[_snap(15350517, f"bk{i}", 0.2308, 0.5392) for i in range(7)],
        *[_snap(990517, f"extra{i}", 0.2308, 0.5392) for i in range(2)],
        *[_snap(15351540, f"ebk{i}", 0.502, 0.498) for i in range(5)],
        *[_snap(991540, f"eextra{i}", 0.505, 0.495) for i in range(2)],
    ]

    db = _mock_db([l1, other_s, el, other_b], [bp_twin, as_twin], snaps)
    batch = await load_unified_game_reads(
        db,
        [bp_canon, as_canon],
        collapse_in_page=False,
        include_same_league_external=True,
        include_odds=True,
        now=now,
    )

    bp_read = batch.by_id[15350517]
    assert sorted(k for k in bp_read.folded_sources if k in ("betting", "polymarket", "kalshi")) == [
        "betting",
        "polymarket",
    ]
    assert bp_read.bookmaker_count == 9
    bp_chance = resolve_unified_card_chance(
        bp_read, sport_key="soccer_england_league1", served_status="scheduled"
    )
    # Away = 0.5392 -> ~54%, draw ~23%, home ~23% (current books beat stale opening 0.25!)
    assert (
        bp_chance.home_rendered_percent,
        bp_chance.draw_rendered_percent,
        bp_chance.away_rendered_percent,
    ) == (23, 23, 54)
    assert bp_chance.source_mark["state"] == "blend"
    assert [s["key"] for s in bp_chance.source_mark["sources"]] == ["polymarket", "betting"]

    as_read = batch.by_id[15351540]
    assert as_read.bookmaker_count == 7
    as_chance = resolve_unified_card_chance(
        as_read, sport_key="basketball_euroleague", served_status="scheduled"
    )
    assert as_chance.source_mark["state"] == "blend"
    assert [s["key"] for s in as_chance.source_mark["sources"]] == [
        "kalshi",
        "polymarket",
        "betting",
    ]


@pytest.mark.asyncio
async def test_unified_read_syncs_twin_betting_book_count_and_excludes_flipped_snapshots():
    now = datetime.now(timezone.utc)
    commence = now + timedelta(hours=2)
    l2 = SimpleNamespace(id=301, key="soccer_england_league2", name="League Two")

    # Canonical has only Polymarket; same-league twin has Betting + 10 bookmakers + betting_book_count=10
    pv_canon = SimpleNamespace(
        id=15315471,
        sport_id=301,
        sport=l2,
        home_team_name="Port Vale",
        away_team_name="Northampton Town",
        commence_time=commence,
        status="scheduled",
        home_score=None,
        away_score=None,
        completed_at=None,
        win_probability_sources={"polymarket": {"value": 0.46, "updated_at": now.isoformat()}},
        opening_home_probability=None,
        opening_away_probability=None,
        espn_id="pv-1",
        external_id=None,
        statpal_fixture_id=None,
        event_tags=None,
    )
    pv_twin = SimpleNamespace(
        id=995471,
        sport_id=301,
        sport=l2,
        home_team_name="Port Vale FC",
        away_team_name="Northampton",
        commence_time=commence,
        status="scheduled",
        home_score=None,
        away_score=None,
        completed_at=None,
        win_probability_sources={
            "betting": {"value": 0.4492, "updated_at": now.isoformat()},
            "betting_book_count": 10,
        },
        opening_home_probability=0.4492,
        opening_away_probability=0.2624,
        espn_id=None,
        external_id="oa-pv-1",
        statpal_fixture_id=None,
        event_tags=None,
    )

    # Flipped two-way twin for another allowlisted EuroLeague event (id-less claim)
    el = SimpleNamespace(id=302, key="basketball_euroleague", name="EuroLeague")
    el_canon = SimpleNamespace(
        id=88001,
        sport_id=302,
        sport=el,
        home_team_name="Maccabi Tel Aviv",
        away_team_name="FC Bayern Munich",
        commence_time=commence,
        status="scheduled",
        home_score=None,
        away_score=None,
        completed_at=None,
        win_probability_sources={"kalshi": {"value": 0.60, "updated_at": now.isoformat()}},
        opening_home_probability=0.60,
        opening_away_probability=0.40,
        espn_id="el-1",
        external_id=None,
        statpal_fixture_id=None,
        event_tags=None,
    )
    el_flipped = SimpleNamespace(
        id=88002,
        sport_id=302,
        sport=el,
        home_team_name="FC Bayern Munich",
        away_team_name="Maccabi Tel Aviv",
        commence_time=commence + timedelta(minutes=180),
        status="scheduled",
        home_score=None,
        away_score=None,
        completed_at=None,
        commence_time_source="kalshi",
        win_probability_sources={"polymarket": {"value": 0.35, "updated_at": now.isoformat()}},
        opening_home_probability=0.35,
        opening_away_probability=0.65,
        espn_id=None,
        external_id=None,
        statpal_fixture_id=None,
        event_tags=None,
    )

    snaps = [
        *[
            SimpleNamespace(
                id=1000 + i,
                event_id=995471,
                bookmaker=f"bk{i}",
                home_win_probability=0.4492,
                away_win_probability=0.2624,
                home_moneyline=None,
                away_moneyline=None,
                home_spread=None,
                over_under=None,
                projected_home_score=None,
                projected_away_score=None,
                captured_at=now - timedelta(minutes=1),
                valid_until=now + timedelta(minutes=5),
            )
            for i in range(10)
        ],
        SimpleNamespace(
            id=2001,
            event_id=88002,
            bookmaker="flipped_bk",
            home_win_probability=0.35,
            away_win_probability=0.65,
            home_moneyline=None,
            away_moneyline=None,
            home_spread=None,
            over_under=None,
            projected_home_score=None,
            projected_away_score=None,
            captured_at=now - timedelta(minutes=1),
            valid_until=now + timedelta(minutes=5),
        ),
    ]
    db = _mock_db([l2, el], [pv_twin, el_flipped], snaps)
    batch = await load_unified_game_reads(
        db,
        [pv_canon, el_canon],
        collapse_in_page=False,
        include_same_league_external=True,
        include_odds=True,
        now=now,
    )

    pv_read = batch.by_id[15315471]
    assert pv_read.bookmaker_count == 10
    assert pv_read.folded_sources["betting_book_count"] == 10
    pv_chance = resolve_unified_card_chance(
        pv_read, sport_key="soccer_england_league2", served_status="scheduled"
    )
    betting_src = next(s for s in pv_chance.source_mark["sources"] if s["key"] == "betting")
    assert betting_src["count"] == 10

    nba_read = batch.by_id[88001]
    assert nba_read.folded_sources["polymarket"]["value"] == pytest.approx(0.65)
    assert nba_read.bookmaker_count == 0
    assert 88002 not in nba_read.absorbed_ids
