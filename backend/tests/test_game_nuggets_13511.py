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
from app.utils.game_nuggets import (
    NUGGET_FIRST_EIGHT,
    NUGGET_KINDS,
    NUGGET_MAX_PER_KIND_FIRST_EIGHT,
    rank_game_nuggets,
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

    # Wording rules: zero venues, zero 'question', zero American odds, zero 'pts', zero colon venue titles
    forbidden = re.compile(r"\b(?:kalshi|polymarket|draftkings|fanduel|question|pts)\b|[+-]\d{3,5}|:", re.I)
    for n in nuggets:
        assert not forbidden.search(n["claim"]), f"forbidden wording in claim: {n['claim']}"
        assert not forbidden.search(n["rank_reason"]), f"forbidden wording in reason: {n['rank_reason']}"
        assert n["form"] != "pregame_vs_now", f"pregame must never emit pregame_vs_now: {n}"
        assert n["pregame_percent"] is None
        assert n["change_since"] != "pregame"


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
    assert "Over 53.5 total points" in claims
    assert "Under 13.5 points in the third quarter" in claims
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

    # Once game is live: game's own markets may use pregame_mark, while stakes stay 24h-only
    live_res = rank_game_nuggets(
        event_info={**_EVENT_INFO, "status": "live"},
        game_markets=gm,
        related_futures=rf,
        team_progression=tp,
        limit=12,
        now=NOW,
    )
    total_live = next(n for n in live_res["nuggets"] if n["source_market_id"] == 1099)
    assert total_live["form"] == "pregame_vs_now"
    assert total_live["change_since"] == "pregame"
    assert total_live["pregame_percent"] == 44
    assert "Moved +8 points since pregame" in total_live["rank_reason"]
    mvp_live = next(n for n in live_res["nuggets"] if n["source_market_id"] == 6002)
    assert mvp_live["form"] == "history_line"
    assert mvp_live["change_since"] == "24h"


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

    async def _fake_exec(stmt):
        sql = str(stmt)
        if "FROM ranking_grades" in sql:
            return _FakeScalarResult(many=saved_grades)
        if "FROM teams" in sql:
            return _FakeScalarResult(many=[
                SimpleNamespace(id=10, logo_small="https://cdn.example/was.png", logo_url=None, logo_large=None),
                SimpleNamespace(id=20, logo_small="https://cdn.example/cin.png", logo_url=None, logo_large=None),
            ])
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

    monkeypatch.setattr(events_route, "resolve_served_event", AsyncMock(return_value=SimpleNamespace(event=fake_ev, event_id=14780582)))
    monkeypatch.setattr(events_route, "get_game_markets", AsyncMock(return_value=gm))
    monkeypatch.setattr(events_route, "get_related_futures", AsyncMock(return_value=rf))
    monkeypatch.setattr(events_route, "get_team_progression", AsyncMock(return_value=tp))
    monkeypatch.setattr(eval_route, "_check_admin_secret", lambda *_a, **_kw: None)

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
            assert "nuggets" not in deck["games"][0]
            # Deck must never walk games or trigger get_game_markets/related_futures builds
            assert events_route.get_game_markets.await_count == 1

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
