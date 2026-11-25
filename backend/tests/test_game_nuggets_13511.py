"""Tests for #13511 Step 1 — Game page ranked nuggets, grading deck, and american_odds removal."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from httpx import ASGITransport
import pytest

from app.main import app
from app.routes import admin_ranking_eval as eval_route
from app.routes import events as events_route
from app.services import get_db, get_db_rw
from app.tasks import redis_state
from app.utils.game_nuggets import (
    NUGGET_FIRST_EIGHT,
    NUGGET_KINDS,
    NUGGET_MAX_PER_KIND_FIRST_EIGHT,
    match_claim_template,
    rank_game_nuggets,
    reader_league_name,
)

NOW = datetime(2026, 11, 23, 18, 0, tzinfo=timezone.utc)
_EVENT_INFO = {
    "event_id": 14780582,
    "home_team": "Washington Commanders",
    "away_team": "Cincinnati Bengals",
    "home_logo": "https://cdn.example/was.png",
    "away_logo": "https://cdn.example/cin.png",
    "sport": "americanfootball_nfl",
    "status": "scheduled",
    "commence_time": "2026-11-24T01:15:00+00:00",
}


def _fresh_ts(hours_ago: float = 0.5) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


def _rich_payloads():
    game_markets = {
        "totals": [
            {
                "_market_id": 1001,
                "market_name": "Bengals vs Commanders: O/U 48.5",
                "outcome_name": "Over",
                "over_probability": 0.54,
                "pregame_mark": 0.49,
                "threshold": 48.5,
                "observed_at": _fresh_ts(0.4),
                "source_mark": {"state": "single", "sources": [{"key": "kalshi"}]},
            },
            {
                "_market_id": 1002,
                "market_name": "Bengals vs Commanders: O/U 51.5",
                "outcome_name": "Over",
                "over_probability": 0.39,
                "threshold": 51.5,
                "observed_at": _fresh_ts(0.4),
                "source_mark": {"state": "none", "reason": "monotonic_conflict"},
            },
        ],
        "spreads": [
            {
                "_market_id": 1003,
                "market_name": "Spread: Bengals (-3.5)",
                "outcome_name": "Cincinnati Bengals",
                "probability": 0.58,
                "pregame_mark": 0.52,
                "threshold": -3.5,
                "observed_at": _fresh_ts(0.3),
                "source_mark": {"state": "single", "sources": [{"key": "polymarket"}]},
            }
        ],
        "player_props": [
            {
                "_market_id": 2001,
                "player": {"key": "joe burrow", "name": "Joe Burrow"},
                "player_headshot": "https://cdn.example/burrow.png",
                "player_team": "away",
                "stat": {"key": "passing_yards", "label": "Passing Yards"},
                "line": {"kind": "count_at_least", "value": 275, "label": "275+"},
                "over_probability": 0.61,
                "pregame_mark": 0.51,
                "side": "over",
                "source_count": 2,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "blend"},
            },
            {
                "_market_id": 2002,
                "player": {"key": "jayden daniels", "name": "Jayden Daniels"},
                "player_headshot": "https://cdn.example/daniels.png",
                "player_team": "home",
                "stat": {"key": "rushing_yards", "label": "Rushing Yards"},
                "line": {"kind": "count_at_least", "value": 50, "label": "50+"},
                "over_probability": 0.49,
                "pregame_mark": 0.43,
                "side": "over",
                "source_count": 2,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "blend"},
            },
            {
                "_market_id": 2003,
                "player": {"key": "ja marr chase", "name": "Ja'Marr Chase"},
                "player_headshot": "https://cdn.example/chase.png",
                "player_team": "away",
                "stat": {"key": "receiving_yards", "label": "Receiving Yards"},
                "line": {"kind": "count_at_least", "value": 90, "label": "90+"},
                "over_probability": 0.53,
                "pregame_mark": 0.52,
                "side": "over",
                "source_count": 1,
                "observed_at": _fresh_ts(0.3),
                "source_mark": {"state": "single"},
            },
            # Stale reading (>48h) — must be excluded by Ruling 188, never ranked low.
            {
                "_market_id": 2004,
                "player": {"key": "stale player", "name": "Stale Player"},
                "stat": {"key": "rushing_yards", "label": "Rushing Yards"},
                "line": {"kind": "count_at_least", "value": 40, "label": "40+"},
                "over_probability": 0.5,
                "side": "over",
                "observed_at": _fresh_ts(72.0),
                "source_mark": {"state": "single"},
            },
        ],
        "team_totals": [
            {
                "_market_id": 3001,
                "team_name": "Cincinnati Bengals",
                "team_side": "away",
                "threshold": 26.5,
                "over_probability": 0.56,
                "pregame_mark": 0.50,
                "observed_at": _fresh_ts(0.25),
                "source_mark": {"state": "single"},
            }
        ],
        "period_markets": [
            {
                "_market_id": 4001,
                "market_name": "1Q Spread: Bengals (-0.5) question via Kalshi (+120)",
                "outcome_name": "Cincinnati Bengals",
                "period": "1Q",
                "probability": 0.51,
                "pregame_mark": 0.45,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            }
        ],
        "other": [
            {
                "_market_id": 5001,
                "market_name": "Will the game go to overtime? question on Polymarket (-110)",
                "outcome_name": "Yes",
                "probability": 0.14,
                "pregame_mark": 0.08,
                "observed_at": _fresh_ts(0.3),
                "source_mark": {"state": "single"},
            },
            {
                "_market_id": 5002,
                "market_name": "Match Winner Moneyline",
                "outcome_name": "Bengals",
                "probability": 0.62,
                "observed_at": _fresh_ts(0.3),
                "source_mark": {"state": "single"},
            },
        ],
    }

    related_futures = {
        "home_team_futures": [
            # Game's own prop inside related-futures (same market_id 2001) — MUST be excluded from stakes
            {
                "market_id": 2001,
                "outcome_id": 801,
                "market_name": "Cincinnati Bengals vs Washington Commanders: Passing Yards",
                "clean_label": "Joe Burrow 275+ passing yards",
                "display_category": "player_prop",
                "outcome_name": "Yes",
                "probability": 0.61,
                "opening_probability": 0.51,
                "market_tier": 3,
                "last_updated": _fresh_ts(0.2),
                "bookmaker_count": 2,
                "source_mark": {"state": "single"},
            },
            {
                "market_id": 6001,
                "outcome_id": 802,
                "market_name": "NFC East Division Winner",
                "clean_label": "Commanders win NFC East",
                "display_category": "division",
                "outcome_name": "Washington Commanders",
                "probability": 0.42,
                "opening_probability": 0.35,
                "market_tier": 1,
                "last_updated": _fresh_ts(1.0),
                "bookmaker_count": 4,
                "source_mark": {"state": "blend"},
            },
        ],
        "away_team_futures": [
            {
                "market_id": 6002,
                "outcome_id": 803,
                "market_name": "NFL MVP",
                "clean_label": "Joe Burrow NFL MVP",
                "display_category": "award",
                "outcome_name": "Joe Burrow",
                "probability": 0.19,
                "opening_probability": 0.11,
                "market_tier": 1,
                "last_updated": _fresh_ts(0.8),
                "bookmaker_count": 5,
                "matched_player": {"name": "Joe Burrow", "headshot_url": "https://cdn.example/burrow.png"},
                "source_mark": {"state": "blend"},
            }
        ],
        "series_markets": [],
    }

    team_progression = {
        "home_team": {
            "name": "Washington Commanders",
            "logo_url": "https://cdn.example/was.png",
            "stages": [
                {"key": "playoffs", "label": "Make Playoffs", "probability": 0.67, "trend_24h": 0.05, "sources": [{"source": "betting"}, {"source": "polymarket"}]},
            ],
        },
        "away_team": {
            "name": "Cincinnati Bengals",
            "logo_url": "https://cdn.example/cin.png",
            "stages": [
                {"key": "playoffs", "label": "Make Playoffs", "probability": 0.48, "trend_24h": 0.06, "sources": [{"source": "betting"}]},
            ],
        },
    }
    return game_markets, related_futures, team_progression


def test_six_kinds_diversity_cap_freshness_wording_and_own_prop_exclusion() -> None:
    gm, rf, tp = _rich_payloads()
    res = rank_game_nuggets(
        event_info=_EVENT_INFO,
        game_markets=gm,
        related_futures=rf,
        team_progression=tp,
        limit=12,
        now=NOW,
    )

    nuggets = res["nuggets"]
    assert 8 <= len(nuggets) <= 12
    assert res["first_eight_kinds"] >= 4
    first_eight = nuggets[:NUGGET_FIRST_EIGHT]
    kind_counts = Counter(n["kind"] for n in first_eight)
    assert all(cnt <= NUGGET_MAX_PER_KIND_FIRST_EIGHT for cnt in kind_counts.values())
    assert set(kind_counts).issubset(set(NUGGET_KINDS))

    # Stale player (72h) and monotonic_conflict (1002) omitted
    claims_joined = " | ".join(n["claim"] for n in nuggets)
    assert "Stale Player" not in claims_joined
    assert res["excluded_counts"]["stale"] >= 1
    assert res["excluded_counts"]["game_own_props_in_related"] >= 1
    assert all(n["source_market_id"] != 2001 or n["kind"] != "stakes" for n in nuggets)

    # Wording rules: zero venues, zero 'question', zero American odds, zero 'pts',
    # zero colon venue titles, zero betting-slip 'cover'
    forbidden = re.compile(
        r"\b(?:kalshi|polymarket|draftkings|fanduel|question|pts|cover)\b|[+-]\d{3,5}|:",
        re.I,
    )
    for n in nuggets:
        assert not forbidden.search(n["claim"]), f"forbidden wording in claim: {n['claim']}"
        assert not forbidden.search(n["rank_reason"]), f"forbidden wording in reason: {n['rank_reason']}"
        assert n["form"] != "pregame_vs_now", f"pregame must never emit pregame_vs_now: {n}"
        assert n["pregame_percent"] is None
        assert n["change_since"] != "pregame"
        assert "pregame_mark_source" in n


def test_pregame_ignores_opening_probability_and_uses_plain_claims_only() -> None:
    gm, rf, tp = _rich_payloads()
    # Inject placeholder opening_probability and Fable's exact noisy venue titles
    rf["home_team_futures"][1]["opening_probability"] = 0.99
    rf["away_team_futures"][0]["opening_probability"] = 0.50
    rf["away_team_futures"][0]["probability_change_24h"] = 0.06
    gm["totals"] = [
        {
            "_market_id": 1099,
            "market_name": "Bengals vs Commanders: O/U 53.5",
            "outcome_name": "Over 53.5 points",
            "over_probability": 0.52,
            "pregame_mark": 0.44,
            "pregame_mark_source": "kickoff_pin",
            "threshold": 53.5,
            "observed_at": _fresh_ts(0.2),
            "source_mark": {"state": "single"},
        }
    ]
    gm["period_markets"] = [
        {
            "_market_id": 4099,
            "market_name": "Bengals vs. Commanders: 3Q O/U 13.5 (Under)",
            "outcome_name": "Under",
            "period": "3Q",
            "probability": 0.55,
            "pregame_mark": 0.48,
            "pregame_mark_source": "kickoff_pin",
            "observed_at": _fresh_ts(0.2),
            "source_mark": {"state": "single"},
        }
    ]
    gm["other"] = [
        {
            "_market_id": 5099,
            "market_name": "Cincinnati vs Washington: 1st Touchdown: Mike Gesicki",
            "outcome_name": "Mike Gesicki",
            "probability": 0.08,
            "observed_at": _fresh_ts(0.2),
            "source_mark": {"state": "single"},
        },
        {
            "_market_id": 5100,
            "market_name": "Synthetic Unparseable Venue: Oddity Foo: Bar (Baz)",
            "outcome_name": "Yes",
            "probability": 0.25,
            "observed_at": _fresh_ts(0.2),
            "source_mark": {"state": "single"},
        },
    ]

    pre_res = rank_game_nuggets(
        event_info={**_EVENT_INFO, "status": "scheduled"},
        game_markets=gm,
        related_futures=rf,
        team_progression=tp,
        limit=12,
        now=NOW,
    )
    claims = [n["claim"] for n in pre_res["nuggets"]]
    assert "The total is set at 53.5 points" in claims
    assert "The third quarter total is set at 13.5 points" in claims
    assert "Mike Gesicki scores the first touchdown" in claims
    assert all("Oddity Foo" not in c for c in claims)
    assert pre_res["excluded_counts"]["unreadable_claim"] >= 1
    for n in pre_res["nuggets"]:
        assert n["form"] != "pregame_vs_now"
        assert "pts" not in n["rank_reason"].lower()
    mvp = next(n for n in pre_res["nuggets"] if n["source_market_id"] == 6002)
    assert mvp["change_points"] == 6  # from probability_change_24h, never opening_probability=0.50
    assert mvp["change_since"] == "24h"
    assert "Moved +6 points in 24h" in mvp["rank_reason"]

    # Once game is live: game's own markets use pregame_mark ONLY when pregame_mark_source == "kickoff_pin"
    live_res = rank_game_nuggets(
        event_info={**_EVENT_INFO, "status": "live"},
        game_markets=gm,
        related_futures=rf,
        team_progression=tp,
        limit=12,
        now=NOW,
    )
    total_live = next(n for n in live_res["nuggets"] if n["source_market_id"] == 1099)
    assert total_live["claim"] == "Over 53.5 total points, up 8 points since pregame"
    assert total_live["form"] == "pregame_vs_now"
    assert total_live["change_since"] == "pregame"
    assert total_live["pregame_percent"] == 44
    assert total_live["pregame_mark_source"] == "kickoff_pin"
    assert "Moved +8 points since pregame" in total_live["rank_reason"]
    mvp_live = next(n for n in live_res["nuggets"] if n["source_market_id"] == 6002)
    assert mvp_live["form"] == "history_line"
    assert mvp_live["change_since"] == "24h"

    # Untyped player_prop fallback never emits "Over 50 props", non-Over/Under total row is dropped,
    # and duplicate oddity claims deduplicate
    untyped_res = rank_game_nuggets(
        event_info={**_EVENT_INFO, "status": "scheduled"},
        game_markets={
            "totals": [
                {
                    "_market_id": 1101,
                    "market_name": "Will the game go to overtime? (18)",
                    "outcome_name": "No",
                    "over_probability": 0.14,
                    "observed_at": _fresh_ts(0.2),
                    "source_mark": {"state": "single"},
                }
            ],
            "player_props": [
                {
                    "_market_id": 2101,
                    "market_name": "Jayden Daniels 50+ Rushing Yards",
                    "outcome_name": "Over",
                    "threshold": 50.0,
                    "over_probability": 0.49,
                    "player": None,
                    "stat": None,
                    "line": None,
                    "observed_at": _fresh_ts(0.2),
                    "source_mark": {"state": "single"},
                }
            ],
            "other": [
                {
                    "_market_id": 5101,
                    "market_name": "Cincinnati vs Washington: 1st Touchdown",
                    "outcome_name": "Ja'Marr Chase",
                    "probability": 0.14,
                    "observed_at": _fresh_ts(0.2),
                    "source_mark": {"state": "single"},
                },
                {
                    "_market_id": 5102,
                    "market_name": "Cincinnati vs Washington: 1st Touchdown",
                    "outcome_name": "Ja'Marr Chase",
                    "probability": 0.13,
                    "observed_at": _fresh_ts(0.2),
                    "source_mark": {"state": "single"},
                },
            ],
        },
        related_futures={},
        team_progression={},
        now=NOW,
    )
    untyped_claims = [n["claim"] for n in untyped_res["nuggets"]]
    assert "Jayden Daniels's rushing line is 50 yards" in untyped_claims
    assert all("props" not in c.lower() for c in untyped_claims)
    assert all("no 18" not in c.lower() for c in untyped_claims)
    assert untyped_claims.count("Ja'Marr Chase scores the first touchdown") == 1


def test_number_parity_matches_source_surfaces_and_sparse_sport_never_pads() -> None:
    gm, rf, tp = _rich_payloads()
    res = rank_game_nuggets(
        event_info=_EVENT_INFO,
        game_markets=gm,
        related_futures=rf,
        team_progression=tp,
        limit=12,
        now=NOW,
    )

    # Standing number parity lookup against original source dicts
    source_probs: dict[tuple[str, int | None], list[float]] = {}
    for row in gm["totals"] + gm["team_totals"]:
        p = row.get("over_probability")
        if p is not None:
            source_probs.setdefault(("game_markets", row["_market_id"]), []).append(float(p))
    for row in gm["spreads"] + gm["period_markets"] + gm["other"]:
        p = row.get("probability")
        if p is not None:
            source_probs.setdefault(("game_markets", row["_market_id"]), []).append(float(p))
    for row in gm["player_props"]:
        source_probs.setdefault(("game_markets", row["_market_id"]), []).append(float(row["over_probability"]))
    for row in rf["home_team_futures"] + rf["away_team_futures"]:
        source_probs.setdefault(("related_futures", row["market_id"]), []).append(float(row["probability"]))
    prog_probs = {s["probability"] for t in (tp["home_team"], tp["away_team"]) for s in t["stages"]}

    for n in res["nuggets"]:
        if n["source_surface"] == "team_progression":
            assert n["probability"] in prog_probs
        else:
            candidates = source_probs[(n["source_surface"], n["source_market_id"])]
            assert any(n["probability"] == pytest.approx(cp) for cp in candidates)
        assert n["percent"] == int(round(n["probability"] * 100.0))

    # Sparse EuroLeague fixture with 1 valid total only: never pads!
    sparse = rank_game_nuggets(
        event_info={**_EVENT_INFO, "event_id": 99, "sport": "basketball_euroleague"},
        game_markets={
            "totals": [
                {
                    "_market_id": 9001,
                    "market_name": "Paris vs Besiktas: O/U 164.5",
                    "outcome_name": "Over",
                    "over_probability": 0.51,
                    "threshold": 164.5,
                    "observed_at": _fresh_ts(0.2),
                    "source_mark": {"state": "single"},
                }
            ]
        },
        related_futures={},
        team_progression={},
        now=NOW,
    )
    assert len(sparse["nuggets"]) == 1
    assert sparse["nuggets"][0]["kind"] == "game_flow"


async def test_related_futures_strips_american_odds_from_fresh_and_cached_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached_with_odds = {
        "event_id": 14780582,
        "home_team_futures": [
            {"market_id": 6001, "outcome_id": 1, "probability": 0.42, "american_odds": 138}
        ],
        "away_team_futures": [
            {"market_id": 6002, "outcome_id": 2, "probability": 0.19, "american_odds": 426}
        ],
        "shared_futures": [
            {"market_id": 6003, "outcome_id": 3, "probability": 0.31, "american_odds": 222}
        ],
        "series_markets": [
            {
                "market_id": 6004,
                "american_odds": -115,
                "outcomes": [{"outcome_id": 4, "probability": 0.53, "american_odds": -113}],
            }
        ],
    }
    monkeypatch.setattr(events_route, "_read_related_futures_memo", lambda _eid: cached_with_odds)
    body = await events_route.get_related_futures(14780582, debug=False, db=SimpleNamespace())
    for row in body["home_team_futures"] + body["away_team_futures"] + body["shared_futures"] + body["series_markets"]:
        assert "american_odds" not in row
    assert "american_odds" not in body["series_markets"][0]["outcomes"][0]


async def test_http_nuggets_and_admin_grading_scorecard_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gm, rf, tp = _rich_payloads()
    fake_ev = SimpleNamespace(
        id=14780582,
        home_team_id=10,
        away_team_id=20,
        home_team_name="Washington Commanders",
        away_team_name="Cincinnati Bengals",
        sport=SimpleNamespace(key="americanfootball_nfl"),
        status="scheduled",
        commence_time=NOW + timedelta(hours=6),
    )

    class _FakeScalarResult:
        def __init__(self, one=None, many=None):
            self._one = one
            self._many = many if many is not None else []

        def scalar_one_or_none(self):
            return self._one

        def scalars(self):
            return self

        def all(self):
            return self._many

        def first(self):
            return self._one

    saved_grades: list = []
    e2e_linked_counts = [(14780582, 8)]
    e2e_market_rows = [
        (14780582, "Bengals at Commanders: Total Points O/U 48.5", "KXNFLTOTAL-1"),
        (14780582, "Commanders vs Bengals: Spread -3.5", "KXNFLSPREAD-1"),
        (14780582, "Jayden Daniels: Passing Yards O/U 245.5", "KXNFLPYDS-1"),
        (14780582, "Ja'Marr Chase: Receiving Yards O/U 84.5", "KXNFLRYDS-1"),
        (14780582, "Washington Commanders Team Total Over 24.5", "KXNFLTT-1"),
        (14780582, "1st Quarter Total Points O/U 10.5", "KXNFL1QTOTAL-1"),
        (14780582, "Two-Point Conversion Attempted?", "KXNFL2PT-1"),
        (14780582, "Bengals at Commanders Moneyline", "KXNFLGAME-1"),
    ]

    async def _fake_exec(stmt):
        sql = str(stmt)
        if "FROM ranking_grades" in sql:
            return _FakeScalarResult(many=saved_grades)
        if "FROM teams" in sql:
            return _FakeScalarResult(many=[
                SimpleNamespace(id=10, logo_small="https://cdn.example/was.png", logo_url=None, logo_large=None),
                SimpleNamespace(id=20, logo_small="https://cdn.example/cin.png", logo_url=None, logo_large=None),
            ])
        if "FROM futures_markets" in sql:
            if "count(" in sql.lower() and "group by" in sql.lower():
                return _FakeScalarResult(many=e2e_linked_counts)
            if "distinct" in sql.lower():
                return _FakeScalarResult(many=["football"])
            return _FakeScalarResult(many=e2e_market_rows)
        if "ORDER BY events" in sql:
            return _FakeScalarResult(many=[fake_ev])
        return _FakeScalarResult(one=fake_ev)

    fake_db = SimpleNamespace(
        execute=AsyncMock(side_effect=_fake_exec),
        add=lambda row: saved_grades.append(
            SimpleNamespace(
                id=len(saved_grades) + 1,
                slate_id=row.slate_id,
                surface=row.surface,
                grader=row.grader,
                expert=row.expert,
                position=row.position,
                item_key=row.item_key,
                grade=row.grade,
                note=row.note,
                graded_at=NOW,
            )
        ),
        commit=AsyncMock(),
    )

    async def _db_override():
        yield fake_db

    class _FakeRedis:
        def __init__(self) -> None:
            self.data: dict[str, bytes] = {}

        def get(self, key: str):
            return self.data.get(key)

        def setex(self, key: str, _ttl: int, value):
            self.data[key] = value.encode("utf-8") if isinstance(value, str) else value
            return True

    fake_redis = _FakeRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **kw: fake_redis)
    monkeypatch.setattr(events_route, "resolve_served_event", AsyncMock(return_value=SimpleNamespace(event=fake_ev, event_id=14780582)))
    monkeypatch.setattr(events_route, "get_game_markets", AsyncMock(return_value=gm))
    monkeypatch.setattr(events_route, "_load_fast_nugget_stakes", AsyncMock(return_value=rf))
    monkeypatch.setattr(events_route, "_load_nuggets_team_progression", AsyncMock(return_value=tp))
    monkeypatch.setattr(eval_route, "_check_admin_secret", lambda *_a, **_kw: None)

    from app.utils import game_nuggets_cache
    game_nuggets_cache.clear_l1()

    prior = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_db_rw] = _db_override
    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            r_nug = await client.get("/api/events/14780582/nuggets")
            assert r_nug.status_code == 200, r_nug.text
            nug_body = r_nug.json()
            assert nug_body["first_eight_kinds"] >= 4
            assert len(nug_body["everything_map"]) == 6

            r_deck = await client.get("/api/admin/ranking/game-nuggets/deck?limit=20")
            assert r_deck.status_code == 200, r_deck.text
            deck = r_deck.json()
            assert deck["games_count"] == 1
            assert deck["requested_limit"] == 20
            assert deck["deck_truncated"] is False
            assert deck["games"][0]["sport_name"] == "NFL"
            assert deck["games"][0]["nugget_count"] >= 6
            assert deck["games"][0]["kind_count"] >= 3
            assert "nuggets" not in deck["games"][0]
            # Deck qualifies candidates from grouped SQL counts and never walks games to trigger
            # uncached get_game_markets/_load_fast_nugget_stakes builds.
            assert events_route.get_game_markets.await_count == 1

            # Opening a cached event hits game_nuggets_cache first; clear L1+Redis to test
            # the cold per-game admin read builds via get_game_markets cleanly (#13650).
            r_game_cached = await client.get(
                f"/api/admin/ranking/game-nuggets/games/14780582?limit=8&slate={deck['slate_id']}"
            )
            assert r_game_cached.status_code == 200, r_game_cached.text
            assert events_route.get_game_markets.await_count == 1

            game_nuggets_cache.clear_l1()
            fake_redis.data.clear()
            r_game = await client.get(
                f"/api/admin/ranking/game-nuggets/games/14780582?limit=8&slate={deck['slate_id']}"
            )
            assert r_game.status_code == 200, r_game.text
            assert events_route.get_game_markets.await_count == 2
            game_payload = r_game.json()["game"]
            first8 = game_payload["nuggets"]
            assert len(first8) == 8

            # Grade 6 yes + 2 no => 0.75 (3 in 4 target met!)
            for idx, item in enumerate(first8):
                g_resp = await client.post(
                    "/api/admin/ranking/game-nuggets/grades",
                    json={
                        "slate_id": deck["slate_id"],
                        "event_id": 14780582,
                        "nugget_id": item["id"],
                        "position": item["position"],
                        "grade": "yes" if idx < 6 else "no",
                        "grader": "Alex",
                    },
                )
                assert g_resp.status_code == 200, g_resp.text

            r_grades = await client.get(
                "/api/admin/ranking/game-nuggets/grades",
                params={"slate_id": deck["slate_id"]},
            )
            assert r_grades.status_code == 200, r_grades.text
            summary = r_grades.json()
            assert summary["yes_count"] == 6
            assert summary["no_count"] == 2
            assert summary["repeat_rate"] == pytest.approx(0.75)
            assert summary["meets_target"] is True
    finally:
        app.dependency_overrides = prior


def test_round_three_drops_label_only_claims_and_nfl_btts() -> None:
    gm = {
        "totals": [
            {
                "_market_id": 7101,
                "market_name": "Bengals vs Commanders: O/U 54.5",
                "outcome_name": "Over",
                "over_probability": 0.62,
                "threshold": 54.5,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            }
        ],
        "spreads": [
            {
                "_market_id": 7102,
                "market_name": "Spread: Bengals (-6.5)",
                "outcome_name": "Cincinnati Bengals",
                "probability": 0.50,
                "threshold": None,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            },
            {
                "_market_id": 7103,
                "market_name": "Point Spread",
                "outcome_name": "Cincinnati Bengals",
                "probability": 0.50,
                "threshold": None,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            },
        ],
        "player_props": [
            {
                "_market_id": 7104,
                "market_name": "Fantasy Points (Antonio Williams)",
                "outcome_name": "Yes",
                "over_probability": 0.50,
                "player": None,
                "stat": None,
                "line": None,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            },
            {
                "_market_id": 7105,
                "player": {"key": "antonio williams", "name": "Antonio Williams"},
                "stat": {"key": "fantasy_points", "label": "Fantasy Points"},
                "line": None,
                "threshold": None,
                "over_probability": 0.50,
                "side": "over",
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            },
        ],
        "other": [
            {
                "_market_id": 7106,
                "market_name": "Both teams to score",
                "outcome_name": "Yes",
                "probability": 0.51,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            }
        ],
    }

    nfl_res = rank_game_nuggets(
        event_info={**_EVENT_INFO, "sport": "americanfootball_nfl"},
        game_markets=gm,
        related_futures={},
        team_progression={},
        limit=12,
        now=NOW,
    )
    nfl_claims = [n["claim"] for n in nfl_res["nuggets"]]
    assert "Cincinnati Bengals win by 7 or more" in nfl_claims
    assert all("fantasy points" not in c.lower() for c in nfl_claims)
    assert all("antonio williams" not in c.lower() for c in nfl_claims)
    assert all("point spread" not in c.lower() for c in nfl_claims)
    assert all("both teams to score" not in c.lower() for c in nfl_claims)
    assert nfl_res["excluded_counts"]["unreadable_claim"] >= 4

    soccer_res = rank_game_nuggets(
        event_info={
            **_EVENT_INFO,
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "sport": "soccer_epl",
        },
        game_markets={"other": gm["other"]},
        related_futures={},
        team_progression={},
        limit=12,
        now=NOW,
    )
    assert any(n["claim"] == "Both teams to score" for n in soccer_res["nuggets"])


def test_round_three_eliminates_betting_slip_wording() -> None:
    gm = {
        "spreads": [
            {
                "_market_id": 7201,
                "market_name": "Spread: Bengals (-6.5)",
                "outcome_name": "Cincinnati Bengals",
                "probability": 0.58,
                "threshold": -6.5,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            },
            {
                "_market_id": 7202,
                "market_name": "Spread: Bengals (-3.5)",
                "outcome_name": "Washington Commanders",
                "probability": 0.55,
                "threshold": 3.5,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            },
        ],
        "period_markets": [
            {
                "_market_id": 7203,
                "market_name": "1H Spread: Bengals (-3.5)",
                "outcome_name": "Cincinnati Bengals",
                "period": "1H",
                "threshold": -3.5,
                "probability": 0.50,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            }
        ],
    }
    tp = {
        "home_team": {
            "name": "Washington Commanders",
            "stages": [
                {"key": "conference", "label": "Win Conference", "probability": 0.14},
            ],
        },
        "away_team": {
            "name": "Cincinnati Bengals",
            "stages": [
                {"key": "conference", "label": "Win Conference", "probability": 0.18},
                {"key": "championship", "label": "NFL Super Bowl", "probability": 0.08},
            ],
        },
    }

    res = rank_game_nuggets(
        event_info=_EVENT_INFO,
        game_markets={**gm, "spreads": [gm["spreads"][0]]},
        related_futures={},
        team_progression=tp,
        limit=12,
        now=NOW,
    )
    claims = [n["claim"] for n in res["nuggets"]]
    assert "Cincinnati Bengals win by 7 or more" in claims
    assert "Cincinnati Bengals lead by 4 or more at halftime" in claims
    assert "Cincinnati Bengals win the AFC" in claims
    assert "Washington Commanders win the NFC" in claims
    assert "Cincinnati Bengals win the Super Bowl" in claims
    assert all("cover" not in c.lower() for c in claims)
    assert all("win conference" not in c.lower() for c in claims)
    assert all("nfl super bowl" not in c.lower() for c in claims)

    dog_res = rank_game_nuggets(
        event_info=_EVENT_INFO,
        game_markets={"spreads": [gm["spreads"][1]]},
        related_futures={},
        team_progression={},
        limit=12,
        now=NOW,
    )
    dog_claims = [n["claim"] for n in dog_res["nuggets"]]
    assert "Washington Commanders win or lose by 3 or fewer" in dog_claims
    assert all("cover" not in c.lower() for c in dog_claims)


def test_round_three_caps_even_set_lines_drops_close_to_even_and_states_ou_line() -> None:
    gm = {
        "totals": [
            {
                "_market_id": 7301,
                "market_name": "Bengals vs Commanders: O/U 54.5",
                "outcome_name": "Over",
                "over_probability": 0.50,
                "threshold": 54.5,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            }
        ],
        "spreads": [
            {
                "_market_id": 7302,
                "market_name": "Spread: Bengals (-3.5)",
                "outcome_name": "Cincinnati Bengals",
                "probability": 0.50,
                "threshold": -3.5,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            }
        ],
        "player_props": [
            {
                "_market_id": 7310 + idx,
                "player": {"key": f"player {idx}", "name": f"Player {idx}"},
                "player_headshot": f"https://cdn.example/p{idx}.png",
                "stat": {"key": "passing_yards", "label": "Passing Yards"},
                "line": {"kind": "count_at_least", "value": 250 + idx, "label": f"{250 + idx}+"},
                "over_probability": 0.50 if idx < 5 else 0.16,
                "side": "over",
                "source_count": 2 if idx >= 5 else 1,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            }
            for idx in range(7)
        ],
        "team_totals": [
            {
                "_market_id": 7330,
                "team_name": "Cincinnati Bengals",
                "team_side": "away",
                "threshold": 28.5,
                "over_probability": 0.51,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            },
            {
                "_market_id": 7331,
                "team_name": "Washington Commanders",
                "team_side": "home",
                "threshold": 24.5,
                "over_probability": 0.49,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            },
        ],
        "period_markets": [
            {
                "_market_id": 7340,
                "market_name": "1H Spread: Bengals (-1.5)",
                "outcome_name": "Cincinnati Bengals",
                "period": "1H",
                "threshold": -1.5,
                "probability": 0.50,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            }
        ],
        "other": [
            {
                "_market_id": 7350,
                "market_name": "Cincinnati vs Washington: 1st Touchdown: Mike Gesicki",
                "outcome_name": "Mike Gesicki",
                "probability": 0.14,
                "observed_at": _fresh_ts(0.2),
                "source_mark": {"state": "single"},
            }
        ],
    }
    tp = {
        "home_team": {
            "name": "Washington Commanders",
            "stages": [{"key": "playoffs", "label": "Make Playoffs", "probability": 0.12}],
        },
        "away_team": {
            "name": "Cincinnati Bengals",
            "stages": [
                {"key": "conference", "label": "Win Conference", "probability": 0.18},
                {"key": "championship", "label": "NFL Super Bowl", "probability": 0.08},
            ],
        },
    }

    res = rank_game_nuggets(
        event_info=_EVENT_INFO,
        game_markets=gm,
        related_futures={},
        team_progression=tp,
        limit=12,
        now=NOW,
    )
    first8 = res["nuggets"][:NUGGET_FIRST_EIGHT]
    claims_joined = " | ".join(n["claim"] for n in res["nuggets"])
    assert "Player 5" not in claims_joined
    assert "Player 6" not in claims_joined
    assert res["excluded_counts"]["far_rung_unmoved"] >= 2
    assert all("close to even" not in n["rank_reason"].lower() for n in res["nuggets"])
    assert all("long shot" not in n["rank_reason"].lower() for n in res["nuggets"])
    assert any(n["claim"] == "The total is set at 54.5 points" for n in res["nuggets"])
    assert any(n["claim"] == "Player 0's passing line is 250 yards" for n in res["nuggets"])
    assert any(n["claim"] == "Cincinnati Bengals win the Super Bowl" for n in first8)


def test_round_three_kickoff_pin_source_distinguished_from_opening_fallback() -> None:
    commence = datetime(2026, 11, 24, 1, 15, tzinfo=timezone.utc)
    pinned_mkt = SimpleNamespace(
        market_metadata={
            "pregame_mark": {
                "captured_at": "2026-11-24T01:10:00+00:00",
                "outcomes": {"7": 0.37},
            }
        }
    )
    late_mkt = SimpleNamespace(
        market_metadata={
            "pregame_mark": {
                "captured_at": "2026-11-24T01:30:00+00:00",
                "outcomes": {"7": 0.51},
            }
        }
    )
    bare_mkt = SimpleNamespace(market_metadata=None)
    out = SimpleNamespace(id=7)

    assert events_route._resolve_pregame_mark_with_source(
        pinned_mkt, out, True, False, 0.25, commence
    ) == (0.37, "kickoff_pin")
    assert events_route._resolve_pregame_mark_with_source(
        late_mkt, out, True, False, 0.25, commence
    ) == (0.25, "opening")
    assert events_route._resolve_pregame_mark_with_source(
        bare_mkt, out, True, False, None, commence
    ) == (None, None)

    gm = {
        "player_props": [
            {
                "_market_id": 7401,
                "player": {"key": "joe burrow", "name": "Joe Burrow"},
                "stat": {"key": "passing_yards", "label": "Passing Yards"},
                "line": {"kind": "count_at_least", "value": 300, "label": "300+"},
                "over_probability": 0.535,
                "pregame_mark": 0.37,
                "pregame_mark_source": "opening",
                "side": "over",
                "observed_at": _fresh_ts(0.1),
                "source_mark": {"state": "single"},
            },
            {
                "_market_id": 7402,
                "player": {"key": "jayden daniels", "name": "Jayden Daniels"},
                "stat": {"key": "rushing_yards", "label": "Rushing Yards"},
                "line": {"kind": "count_at_least", "value": 50, "label": "50+"},
                "over_probability": 0.54,
                "pregame_mark": 0.37,
                "pregame_mark_source": "kickoff_pin",
                "side": "over",
                "observed_at": _fresh_ts(0.1),
                "source_mark": {"state": "single"},
            },
            {
                "_market_id": 7403,
                "player": {"key": "terry mclaurin", "name": "Terry McLaurin"},
                "stat": {"key": "receiving_yards", "label": "Receiving Yards"},
                "line": {"kind": "count_at_least", "value": 75, "label": "75+"},
                "over_probability": 0.45,
                "pregame_mark": 0.30,
                "side": "over",
                "observed_at": _fresh_ts(0.1),
                "source_mark": {"state": "single"},
            },
        ]
    }
    live_res = rank_game_nuggets(
        event_info={**_EVENT_INFO, "status": "live"},
        game_markets=gm,
        related_futures={},
        team_progression={},
        limit=12,
        now=NOW,
    )
    by_mid = {n["source_market_id"]: n for n in live_res["nuggets"]}
    assert by_mid[7401]["pregame_mark_source"] == "opening"
    assert by_mid[7401]["change_since"] is None
    assert by_mid[7401]["form"] != "pregame_vs_now"

    assert by_mid[7402]["pregame_mark_source"] == "kickoff_pin"
    assert by_mid[7402]["change_since"] == "pregame"
    assert by_mid[7402]["pregame_percent"] == 37
    assert by_mid[7402]["change_points"] == 17
    assert by_mid[7402]["form"] == "pregame_vs_now"

    assert by_mid[7403]["pregame_mark_source"] is None
    assert by_mid[7403]["change_since"] is None
    assert by_mid[7403]["form"] != "pregame_vs_now"


def test_round_four_bengals_commanders_fixture_middle_of_ladder_and_named_templates() -> None:
    """Fable Round Four (comment-7123124444): one middle rung per ladder, movement exception, named templates."""
    gm = {
        "totals": [
            {"_market_id": 8001, "market_name": "Bengals vs Commanders: O/U 47.5", "outcome_name": "Over", "over_probability": 0.76, "threshold": 47.5, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
            {"_market_id": 8002, "market_name": "Bengals vs Commanders: O/U 53.5", "outcome_name": "Over", "over_probability": 0.50, "threshold": 53.5, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "blend"}},
            {"_market_id": 8003, "market_name": "Bengals vs Commanders: O/U 67.5", "outcome_name": "Over", "over_probability": 0.18, "threshold": 67.5, "pregame_mark": 0.10, "pregame_mark_source": "kickoff_pin", "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
        ],
        "spreads": [
            {"_market_id": 8010, "market_name": "Spread: Bengals (-3.5)", "outcome_name": "Cincinnati Bengals", "probability": 0.51, "threshold": -3.5, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "blend"}},
            # Kalshi phrasing that broke Round Three: must resolve team + negative margin, not leak raw phrase
            {"_market_id": 8011, "market_name": "Spread", "outcome_name": "Washington wins by over 3.5 points", "probability": 0.16, "threshold": 3.5, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
            {"_market_id": 8012, "market_name": "Spread", "outcome_name": "Mystery Club wins by over 3.5 points", "probability": 0.25, "threshold": 3.5, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
        ],
        "team_totals": [
            {"_market_id": 8020, "team_name": "Cincinnati Bengals", "team_side": "away", "threshold": 27.5, "over_probability": 0.50, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "blend"}},
            {"_market_id": 8021, "team_name": "Cincinnati Bengals", "team_side": "away", "threshold": 38.5, "over_probability": 0.20, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
            {"_market_id": 8022, "team_name": "Washington Commanders", "team_side": "home", "threshold": 24.5, "over_probability": 0.49, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "blend"}},
            {"_market_id": 8023, "team_name": "Washington Commanders", "team_side": "home", "threshold": 31.5, "over_probability": 0.19, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
        ],
        "player_props": [
            # Joe Burrow passing yards ladder -> nearest 50% (265.5)
            {"_market_id": 8030, "player": {"key": "joe burrow", "name": "Joe Burrow"}, "player_headshot": "https://cdn.example/burrow.png", "stat": {"key": "passing_yards", "label": "Passing Yards"}, "line": {"kind": "total", "value": 265.5, "label": "265.5"}, "over_probability": 0.50, "side": "over", "source_count": 2, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "blend"}},
            {"_market_id": 8031, "player": {"key": "joe burrow", "name": "Joe Burrow"}, "player_headshot": "https://cdn.example/burrow.png", "stat": {"key": "passing_yards", "label": "Passing Yards"}, "line": {"kind": "count_at_least", "value": 300, "label": "300+"}, "over_probability": 0.22, "side": "over", "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
            # Joe Burrow passing TDs ladder -> picks 1.5 (52%), never 5+ (9%)
            {"_market_id": 8032, "player": {"key": "joe burrow", "name": "Joe Burrow"}, "player_headshot": "https://cdn.example/burrow.png", "stat": {"key": "passing_touchdowns", "label": "Passing Touchdowns"}, "line": {"kind": "total", "value": 1.5, "label": "1.5"}, "over_probability": 0.52, "side": "over", "observed_at": _fresh_ts(0.2), "source_mark": {"state": "blend"}},
            {"_market_id": 8033, "player": {"key": "joe burrow", "name": "Joe Burrow"}, "player_headshot": "https://cdn.example/burrow.png", "stat": {"key": "passing_touchdowns", "label": "Passing Touchdowns"}, "line": {"kind": "count_at_least", "value": 5, "label": "5+"}, "over_probability": 0.09, "side": "over", "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
            # Tail-only unmoved ladders: Daniels 3+ passing TDs (21%), Burrow 20+ rushing yds (20%) -> dropped!
            {"_market_id": 8034, "player": {"key": "jayden daniels", "name": "Jayden Daniels"}, "player_headshot": "https://cdn.example/daniels.png", "stat": {"key": "passing_touchdowns", "label": "Passing Touchdowns"}, "line": {"kind": "count_at_least", "value": 3, "label": "3+"}, "over_probability": 0.21, "side": "over", "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
            {"_market_id": 8035, "player": {"key": "joe burrow", "name": "Joe Burrow"}, "player_headshot": "https://cdn.example/burrow.png", "stat": {"key": "rushing_yards", "label": "Rushing Yards"}, "line": {"kind": "count_at_least", "value": 20, "label": "20+"}, "over_probability": 0.20, "side": "over", "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
        ],
        "period_markets": [
            {"_market_id": 8040, "market_name": "1H Total: O/U 26.5", "outcome_name": "Over", "period": "1H", "threshold": 26.5, "probability": 0.51, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
            # Kalshi 2H far spread: must drop unmoved pregame, and when resolved at middle uses Commanders clean grammar
            {"_market_id": 8041, "market_name": "2H Spread", "outcome_name": "Washington wins by over 4.5 points", "period": "2H", "threshold": 4.5, "probability": 0.20, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
        ],
        "other": [
            {"_market_id": 8050, "market_name": "Weather Delay", "outcome_name": "Yes", "probability": 0.11, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
        ],
    }
    tp = {
        "home_team": {
            "name": "Washington Commanders",
            "stages": [{"key": "playoffs", "label": "Make Playoffs", "probability": 0.12}],
        },
        "away_team": {
            "name": "Cincinnati Bengals",
            "stages": [
                {"key": "playoffs", "label": "Make Playoffs", "probability": 0.98},
                {"key": "championship", "label": "NFL Super Bowl", "probability": 0.08},
            ],
        },
    }

    res = rank_game_nuggets(
        event_info={**_EVENT_INFO, "status": "scheduled"},
        game_markets=gm,
        related_futures={},
        team_progression=tp,
        limit=12,
        now=NOW,
    )
    claims = [n["claim"] for n in res["nuggets"]]
    assert claims
    assert all(match_claim_template(c) is not None for c in claims)
    assert all("long shot" not in n["rank_reason"].lower() for n in res["nuggets"])

    assert "The total is set at 53.5 points" in claims
    assert "Joe Burrow's passing line is 265.5 yards" in claims
    assert "Joe Burrow's passing touchdown line is 1.5" in claims
    assert "Cincinnati Bengals win by 4 or more" in claims
    assert "Cincinnati Bengals team total is set at 27.5 points" in claims
    assert "Washington Commanders team total is set at 24.5 points" in claims
    assert "The first half total is set at 26.5 points" in claims
    assert "Washington Commanders make the playoffs" in claims
    assert "Cincinnati Bengals make the playoffs" in claims
    assert "Cincinnati Bengals win the Super Bowl" in claims

    joined = " | ".join(claims)
    for bad in ("Over 67.5", "38.5", "31.5", "5+ passing touchdowns", "3+ passing touchdowns", "20+ rushing yards", "Weather Delay", "wins by over", "stay within"):
        assert bad not in joined
    assert res["excluded_counts"]["far_rung_unmoved"] >= 3
    assert res["excluded_counts"]["unreadable_claim"] >= 2

    # Kalshi spread phrasing at middle probability resolves cleanly (never Frankenstein double-predicate)
    kalshi_mid = rank_game_nuggets(
        event_info={**_EVENT_INFO, "status": "scheduled"},
        game_markets={
            "spreads": [{**gm["spreads"][1], "probability": 0.50}],
            "period_markets": [{**gm["period_markets"][1], "probability": 0.50}],
        },
        related_futures={},
        team_progression={},
        limit=12,
        now=NOW,
    )
    kalshi_claims = [n["claim"] for n in kalshi_mid["nuggets"]]
    assert "Washington Commanders win by 4 or more" in kalshi_claims
    assert "Washington Commanders win the second half by 5 or more" in kalshi_claims
    assert all(match_claim_template(c) is not None for c in kalshi_claims)

    # Rule 1 movement exception: far rung enters ONLY when moved (pin post-kickoff or dated 24h) and movement IS the claim
    gm_moved = {
        **gm,
        "totals": [
            {**gm["totals"][1]},
            {**gm["totals"][2], "over_probability": 0.22, "pregame_mark": 0.10, "pregame_mark_source": "kickoff_pin"},
        ],
        "player_props": [
            {**gm["player_props"][4], "over_probability": 0.28, "probability_change_24h": 0.07},
        ],
    }
    moved_res = rank_game_nuggets(
        event_info={**_EVENT_INFO, "status": "live"},
        game_markets=gm_moved,
        related_futures={},
        team_progression={},
        limit=12,
        now=NOW,
    )
    moved_claims = [n["claim"] for n in moved_res["nuggets"]]
    assert "Over 67.5 total points, up 12 points since pregame" in moved_claims
    assert "Jayden Daniels 3+ passing touchdowns, up 7 points in 24 hours" in moved_claims
    assert all(match_claim_template(c) is not None for c in moved_claims)

    # Real-data TD edge cases: drop team-first-TD, keep highest-probability 1st TD scorer only,
    # parse "<Player>: Anytime Touchdown", and state 1-TD ladder rung as "{player} scores a touchdown".
    td_res = rank_game_nuggets(
        event_info={**_EVENT_INFO, "status": "scheduled"},
        game_markets={
            "player_props": [
                {
                    "_market_id": 8060,
                    "player": {"key": "blake corum", "name": "Blake Corum"},
                    "stat": {"key": "touchdowns", "label": "Touchdowns"},
                    "line": {"kind": "count_at_least", "value": 1, "label": "1+"},
                    "over_probability": 0.42,
                    "side": "over",
                    "observed_at": _fresh_ts(0.2),
                    "source_mark": {"state": "single"},
                },
            ],
            "other": [
                {"_market_id": 8061, "market_name": "Cincinnati vs Washington: 1st Washington Touchdown", "outcome_name": "Luke McCaffrey", "probability": 0.14, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
                {"_market_id": 8062, "market_name": "Ben Sinnott: Team First TD (Washington Commanders)", "outcome_name": "Yes", "probability": 0.12, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
                {"_market_id": 8063, "market_name": "Cincinnati vs Washington: 1st Touchdown", "outcome_name": "Colbie Young", "probability": 0.02, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
                {"_market_id": 8064, "market_name": "Cincinnati vs Washington: 1st Touchdown", "outcome_name": "Chase Brown", "probability": 0.19, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
                {"_market_id": 8065, "market_name": "Chase Brown: Anytime Touchdown", "outcome_name": "Yes", "probability": 0.56, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
                {"_market_id": 8066, "market_name": "Blake Corum: Anytime Touchdown", "outcome_name": "Yes", "probability": 0.38, "observed_at": _fresh_ts(0.2), "source_mark": {"state": "single"}},
            ],
        },
        related_futures={},
        team_progression={},
        limit=12,
        now=NOW,
    )
    td_claims = [n["claim"] for n in td_res["nuggets"]]
    assert len(td_claims) == len(set(td_claims))
    assert "Blake Corum scores a touchdown" in td_claims
    assert "Chase Brown scores the first touchdown" in td_claims
    assert all("Colbie Young" not in c for c in td_claims)
    assert all("Luke McCaffrey" not in c for c in td_claims)
    assert all("Ben Sinnott" not in c for c in td_claims)
    assert td_res["excluded_counts"]["unreadable_claim"] >= 2
    assert all(match_claim_template(c) is not None for c in td_claims)


def test_reader_league_name_uses_plain_labels() -> None:
    assert reader_league_name(SimpleNamespace(key="basketball_nba", name="basketball_nba")) == "NBA"
    assert reader_league_name(SimpleNamespace(key="americanfootball_nfl", name=None)) == "NFL"
    assert reader_league_name(SimpleNamespace(key="basketball_wncaab", name="basketball_wncaab")) == "Women's College Basketball"
    assert reader_league_name(SimpleNamespace(key="soccer_italy_serie_b", name="soccer_italy_serie_b")) == "Serie B"
    assert reader_league_name(SimpleNamespace(key="tennis_other", name="tennis_other")) == "Tennis"
    assert reader_league_name(SimpleNamespace(key="esports_other", name="esports_other")) == "Esports"
    assert reader_league_name(SimpleNamespace(key="handball_germany_bundesliga", name=None)) == "Handball"


async def test_game_nuggets_deck_deals_qualified_best_covered_first_with_league_cap_and_shorter_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _make_ev(eid: int, sport_key: str, sport_name: str, hours_ahead: int, away: str, home: str):
        return SimpleNamespace(
            id=eid,
            home_team_id=eid * 10 + 1,
            away_team_id=eid * 10 + 2,
            home_team_name=home,
            away_team_name=away,
            sport=SimpleNamespace(key=sport_key, name=sport_name),
            status="scheduled",
            win_probability_sources={"betting": {"value": 0.55}},
            commence_time=NOW + timedelta(hours=hours_ahead),
        )

    events = [
        _make_ev(1001, "esports_other", "esports_other", 1, "PuckChamp", "Zero Tenacity"),
        _make_ev(1002, "soccer_italy_serie_b", "soccer_italy_serie_b", 2, "US Catanzaro", "Juve Stabia"),
        _make_ev(1003, "tennis_other", "tennis_other", 3, "Player A", "Player B"),
        # 5 qualified NBA games (+1 unqualified 1-kind NBA game) -> only 4 may enter deck
        _make_ev(2001, "basketball_nba", "NBA", 6, "Boston Celtics", "Washington Wizards"),
        _make_ev(2002, "basketball_nba", "NBA", 7, "New York Knicks", "Brooklyn Nets"),
        _make_ev(2003, "basketball_nba", "NBA", 8, "Denver Nuggets", "Phoenix Suns"),
        _make_ev(2004, "basketball_nba", "NBA", 9, "Miami Heat", "Orlando Magic"),
        _make_ev(2005, "basketball_nba", "NBA", 10, "Dallas Mavericks", "Houston Rockets"),
        _make_ev(2006, "basketball_nba", "NBA", 72, "Los Angeles Lakers", "San Antonio Spurs"),
        # Later Thursday/Sunday NFL games with rich coverage must still qualify & outrank sparser games
        _make_ev(3001, "americanfootball_nfl", "NFL", 50, "Chicago Bears", "Detroit Lions"),
        _make_ev(3002, "americanfootball_nfl", "NFL", 96, "Kansas City Chiefs", "Buffalo Bills"),
    ]
    linked_rows = [
        (2001, 45), (2002, 30), (2003, 25), (2004, 20), (2005, 18), (2006, 8),
        (3001, 60), (3002, 55), (1002, 4),
    ]
    market_rows = [
        # 1002 (unqualified: 4 markets, <6 items & <3 kinds)
        (1002, "Total Goals O/U 2.5", "KXSBOU-1"),
        (1002, "Total Goals O/U 3.5", "KXSBOU-2"),
        (1002, "Spread -0.5", "KXSBSP-1"),
        (1002, "Moneyline Winner", "KXSBML-1"),
        # 2001 (NBA #1: 5 kinds, 8 nuggets)
        (2001, "Total Points O/U 224.5", "KXNBATOT-2001"),
        (2001, "Spread -6.5", "KXNBASP-2001"),
        (2001, "Jayson Tatum: Points O/U 27.5", "KXNBAPP-2001-1"),
        (2001, "Jaylen Brown: Rebounds O/U 6.5", "KXNBAPP-2001-2"),
        (2001, "Boston Celtics Team Total Over 116.5", "KXNBATT-2001-1"),
        (2001, "Washington Wizards Team Total Over 108.5", "KXNBATT-2001-2"),
        (2001, "1st Quarter Total O/U 56.5", "KXNBA1QTOT-2001"),
        # 2002 (NBA #2: 4 kinds, 7 nuggets)
        (2002, "Total Points O/U 218.5", "KXNBATOT-2002"),
        (2002, "Spread -4.5", "KXNBASP-2002"),
        (2002, "Jalen Brunson: Points O/U 26.5", "KXNBAPP-2002-1"),
        (2002, "Karl-Anthony Towns: Rebounds O/U 11.5", "KXNBAPP-2002-2"),
        (2002, "New York Knicks Team Total Over 111.5", "KXNBATT-2002-1"),
        (2002, "Brooklyn Nets Team Total Over 105.5", "KXNBATT-2002-2"),
        # 2003 (NBA #3: 4 kinds, 7 nuggets)
        (2003, "Total Points O/U 229.5", "KXNBATOT-2003"),
        (2003, "Spread -2.5", "KXNBASP-2003"),
        (2003, "Nikola Jokic: Points O/U 28.5", "KXNBAPP-2003-1"),
        (2003, "Devin Booker: Points O/U 26.5", "KXNBAPP-2003-2"),
        (2003, "Denver Nuggets Team Total Over 115.5", "KXNBATT-2003-1"),
        (2003, "1st Half Total O/U 114.5", "KXNBA1HTOT-2003"),
        # 2004 (NBA #4: 4 kinds, 6 nuggets — qualifies cleanly before 2005)
        (2004, "Total Points O/U 214.5", "KXNBATOT-2004"),
        (2004, "Spread -3.5", "KXNBASP-2004"),
        (2004, "Jimmy Butler: Points O/U 21.5", "KXNBAPP-2004-1"),
        (2004, "Paolo Banchero: Points O/U 24.5", "KXNBAPP-2004-2"),
        (2004, "Miami Heat Team Total Over 108.5", "KXNBATT-2004-1"),
        # 2005 (NBA #5: qualifies too (4 kinds, 6 nuggets), but capped out by <=4/league)
        (2005, "Total Points O/U 222.5", "KXNBATOT-2005"),
        (2005, "Spread -1.5", "KXNBASP-2005"),
        (2005, "Luka Doncic: Points O/U 30.5", "KXNBAPP-2005-1"),
        (2005, "Alperen Sengun: Rebounds O/U 10.5", "KXNBAPP-2005-2"),
        (2005, "Dallas Mavericks Team Total Over 112.5", "KXNBATT-2005-1"),
        # 2006 (NBA #6: only game_flow + stakes => 2 kinds < 3 -> excluded)
        (2006, "Total Points O/U 220.5", "KXNBATOT-2006-1"),
        (2006, "Total Points O/U 221.5", "KXNBATOT-2006-2"),
        (2006, "Spread -5.5", "KXNBASP-2006-1"),
        (2006, "Spread -6.5", "KXNBASP-2006-2"),
        # 3001 (NFL #1: 5 kinds, 8 nuggets)
        (3001, "Total Points O/U 49.5", "KXNFLTOT-3001"),
        (3001, "Spread -7.5", "KXNFLSP-3001"),
        (3001, "Jared Goff: Passing Yards O/U 255.5", "KXNFLPP-3001-1"),
        (3001, "Amon-Ra St. Brown: Receiving Yards O/U 79.5", "KXNFLPP-3001-2"),
        (3001, "Detroit Lions Team Total Over 28.5", "KXNFLTT-3001-1"),
        (3001, "Chicago Bears Team Total Over 20.5", "KXNFLTT-3001-2"),
        (3001, "1st Quarter Total O/U 10.5", "KXNFL1QTOT-3001"),
        # 3002 (NFL #2: 4 kinds, 7 nuggets)
        (3002, "Total Points O/U 52.5", "KXNFLTOT-3002"),
        (3002, "Spread -2.5", "KXNFLSP-3002"),
        (3002, "Patrick Mahomes: Passing Yards O/U 272.5", "KXNFLPP-3002-1"),
        (3002, "Josh Allen: Passing Yards O/U 262.5", "KXNFLPP-3002-2"),
        (3002, "Kansas City Chiefs Team Total Over 27.5", "KXNFLTT-3002-1"),
        (3002, "Buffalo Bills Team Total Over 24.5", "KXNFLTT-3002-2"),
    ]

    class _Res:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    async def _fake_exec(stmt):
        sql = str(stmt)
        if "FROM ranking_grades" in sql:
            return _Res([])
        if "FROM futures_markets" in sql:
            if "count(" in sql.lower() and "group by" in sql.lower():
                return _Res(linked_rows)
            if "distinct" in sql.lower():
                return _Res(["basketball", "football"])
            return _Res(market_rows)
        if "FROM events" in sql:
            return _Res(events)
        return _Res([])

    fake_db = SimpleNamespace(execute=AsyncMock(side_effect=_fake_exec))
    monkeypatch.setattr(
        events_route,
        "build_event_nuggets",
        AsyncMock(side_effect=AssertionError("must not call build_event_nuggets inside /deck")),
    )
    monkeypatch.setattr(eval_route, "_check_admin_secret", lambda *_a, **_kw: None)

    async def _db_override():
        yield fake_db

    prior = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _db_override
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            resp = await client.get("/api/admin/ranking/game-nuggets/deck?limit=20")
            assert resp.status_code == 200, resp.text
            data = resp.json()
    finally:
        app.dependency_overrides = prior

    dealt_ids = [g["event_id"] for g in data["games"]]
    assert data["requested_limit"] == 20
    assert data["deck_truncated"] is False
    # 6 games qualify after max-4 NBA cap: 4 NBA + 2 NFL (shorter deck)
    assert data["games_count"] == 6
    assert len(dealt_ids) == 6
    # Excluded unqualified games (<6 items or <3 kinds or empty)
    for bad_id in (1001, 1002, 1003, 2006):
        assert bad_id not in dealt_ids
    # Max 4 from one league + 5th NBA left out
    nba_dealt = [g for g in data["games"] if g["sport"] == "basketball_nba"]
    assert len(nba_dealt) == 4
    assert 2005 not in dealt_ids
    # Best-covered first: 5-kind NFL & NBA ahead of 4-kind (7-nugget) and 4-kind (6-nugget)
    assert set(dealt_ids[:2]) == {2001, 3001}
    assert set(dealt_ids[2:5]) == {2002, 2003, 3002}
    assert dealt_ids[5] == 2004
    # Plain league names
    assert all(g["sport_name"] in {"NBA", "NFL"} for g in data["games"])


async def test_game_nuggets_deck_timeout_ceiling_returns_short_deck_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ~8s ceiling stops slow /deck work and returns what qualified without caching (#13642)."""
    import asyncio

    ev = SimpleNamespace(
        id=4001,
        home_team_id=401,
        away_team_id=402,
        home_team_name="Kansas City Chiefs",
        away_team_name="Buffalo Bills",
        sport=SimpleNamespace(key="americanfootball_nfl", name="NFL"),
        status="scheduled",
        win_probability_sources={"betting": {"value": 0.52}},
        commence_time=NOW + timedelta(hours=12),
    )

    class _Res:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    async def _slow_exec(stmt):
        sql = str(stmt)
        if "FROM ranking_grades" in sql:
            return _Res([])
        if "FROM events" in sql:
            return _Res([ev])
        if "FROM futures_markets" in sql and "group by" in sql.lower():
            await asyncio.sleep(0.25)
            return _Res([(4001, 10)])
        return _Res([])

    fake_db = SimpleNamespace(execute=AsyncMock(side_effect=_slow_exec))
    monkeypatch.setattr(eval_route, "_GAME_NUGGETS_DECK_BUDGET_SECONDS", 0.05)
    monkeypatch.setattr(eval_route, "_check_admin_secret", lambda *_a, **_kw: None)

    async def _db_override():
        yield fake_db

    prior = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _db_override
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            resp = await client.get("/api/admin/ranking/game-nuggets/deck?limit=20")
            assert resp.status_code == 200, resp.text
            data = resp.json()
    finally:
        app.dependency_overrides = prior

    assert data["deck_truncated"] is True
    assert data["requested_limit"] == 20
    assert data["games_count"] == 0
    assert data["games"] == []
