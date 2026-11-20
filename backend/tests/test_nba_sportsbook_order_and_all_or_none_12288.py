"""Tests for Goal Step 7 (#12288):
1. NBA (and sports) groupings never lead with thin prediction-market/ESPN-only
   games when sportsbook-priced games exist on the slate.
2. In the first minutes after a restart, Discover shows all five groupings or
   none (never a partial 2/5 or 3/5 set), while keeping standing round-ups intact.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.utils.container_machinery import (
    _event_has_sportsbook,
    produce_container_machinery,
)
from app.utils.roundup_containers import (
    RoundupMembers,
    RoundupProducer,
    add_roundup_feed_items,
    reset_roundup_cache_for_tests,
)

NOW = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)
NBA_DEF_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "groupings"
    / "candidates"
    / "machinery-nba-night.json"
)


def _nba_event(
    eid: int,
    away: str,
    home: str,
    *,
    home_prob: float,
    hours_ahead: float,
    wps: dict[str, Any],
    bookmaker_count: int = 0,
) -> dict[str, Any]:
    away_prob = round(1.0 - home_prob, 4)
    return {
        "id": eid,
        "sport": "basketball_nba",
        "sport_name": "NBA",
        "away_team": away,
        "home_team": home,
        "commence_time": (NOW + timedelta(hours=hours_ahead)).isoformat(),
        "status": "scheduled",
        "hero_probability": home_prob,
        "hero_probability_away": away_prob,
        "hero_source": "blend",
        "bookmaker_count": bookmaker_count,
        "win_probability_sources": wps,
        "current_odds": {
            "home_probability": home_prob,
            "away_probability": away_prob,
            "home_rendered_percent": round(home_prob * 100),
            "away_rendered_percent": round(away_prob * 100),
            "bookmaker_count": bookmaker_count,
        },
    }


def _nba_support_markets() -> list[dict[str, Any]]:
    def _mkt(mid: int, name: str, lead: str, prob: float) -> dict[str, Any]:
        return {
            "id": mid,
            "name": name,
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "basketball",
            "volume": 50000.0,
            "top_outcomes": [
                {"id": mid * 10 + 1, "name": lead, "probability": prob, "rendered_percent": round(prob * 100)},
                {"id": mid * 10 + 2, "name": "Field Contender", "probability": 0.25, "rendered_percent": 25},
                {"id": mid * 10 + 3, "name": "Other Contender", "probability": 0.15, "rendered_percent": 15},
            ],
        }

    return [
        _mkt(7001, "Pro Basketball Points Per Game (PPG) Leader", "Luka Doncic", 0.55),
        _mkt(7002, "Pro Basketball Rebounds Per Game (RPG) Leader", "Karl-Anthony Towns", 0.46),
        _mkt(7003, "Pro Basketball Assists Per Game (APG) Leader", "Nikola Jokic", 0.39),
        _mkt(7004, "Pro Basketball MVP Winner", "Victor Wembanyama", 0.42),
        _mkt(7005, "Pro Basketball Defensive Player of the Year Winner", "Victor Wembanyama", 0.64),
        _mkt(7006, "Pro Basketball Sixth Man of the Year Winner", "Payton Pritchard", 0.31),
    ]


@pytest.mark.asyncio
async def test_nba_grouping_prefers_sportsbook_games_over_thin_venue_only_games() -> None:
    definition = json.loads(NBA_DEF_PATH.read_text(encoding="utf-8"))

    thin_kalshi_poly = _nba_event(
        15349648,
        "Dallas Mavericks",
        "Utah Jazz",
        home_prob=0.5075,
        hours_ahead=60,
        wps={"kalshi": {"home": 0.51}, "polymarket": {"home": 0.505}},
        bookmaker_count=0,
    )
    thin_espn = _nba_event(
        15351148,
        "Chicago Bulls",
        "Charlotte Hornets",
        home_prob=0.5088,
        hours_ahead=72,
        wps={"espn": {"home": 0.5088}},
        bookmaker_count=0,
    )
    sb_rockets = _nba_event(
        15197756,
        "Houston Rockets",
        "Denver Nuggets",
        home_prob=0.54,
        hours_ahead=15,
        wps={"betting": {"home": 0.54}, "betting_book_count": 18, "kalshi": {"home": 0.53}},
        bookmaker_count=18,
    )
    sb_hawks = _nba_event(
        15351618,
        "Charlotte Hornets",
        "Atlanta Hawks",
        home_prob=0.57,
        hours_ahead=12,
        wps={"betting": {"home": 0.57}, "betting_book_count": 19, "kalshi": {"home": 0.56}},
        bookmaker_count=19,
    )
    sb_pistons = _nba_event(
        15321150,
        "Toronto Raptors",
        "Detroit Pistons",
        home_prob=0.61,
        hours_ahead=12.5,
        wps={"betting": {"home": 0.61}, "betting_book_count": 19},
        bookmaker_count=19,
    )

    assert _event_has_sportsbook(thin_kalshi_poly) is False
    assert _event_has_sportsbook(thin_espn) is False
    assert _event_has_sportsbook(sb_rockets) is True
    assert _event_has_sportsbook(sb_hawks) is True

    outcome = await produce_container_machinery(
        {"events": [thin_kalshi_poly, thin_espn, sb_rockets, sb_hawks, sb_pistons], "markets": _nba_support_markets()},
        definition,
        now=NOW,
    )
    assert isinstance(outcome, RoundupMembers)
    assert outcome.sections
    lead_sec = outcome.sections[0]
    lead_ids = [int(m["event_id"]) for m in lead_sec["members"]]
    # Sportsbook-backed games lead; zero-bookmaker thin-trading games are excluded when >= min_items sportsbook games exist.
    assert lead_ids == [15197756, 15351618, 15321150]
    assert 15349648 not in lead_ids
    assert 15351148 not in lead_ids
    assert "Rockets at Nuggets" in (outcome.title or "")

    # When only 1 sportsbook game exists in the closeness band (below min_items=2), it STILL leads in slot 1.
    blowout_1 = _nba_event(
        15399001, "Washington Wizards", "Boston Celtics",
        home_prob=0.82, hours_ahead=14,
        wps={"betting": {"home": 0.82}, "betting_book_count": 18}, bookmaker_count=18,
    )
    blowout_2 = _nba_event(
        15399002, "Portland Trail Blazers", "Oklahoma City Thunder",
        home_prob=0.84, hours_ahead=16,
        wps={"betting": {"home": 0.84}, "betting_book_count": 18}, bookmaker_count=18,
    )
    outcome_one_sb = await produce_container_machinery(
        {"events": [thin_kalshi_poly, thin_espn, sb_rockets, blowout_1, blowout_2], "markets": _nba_support_markets()},
        definition,
        now=NOW,
    )
    assert isinstance(outcome_one_sb, RoundupMembers)
    lead_ids_one = [int(m["event_id"]) for m in outcome_one_sb.sections[0]["members"]]
    assert lead_ids_one[0] == 15197756


def _ordinary_deck(n: int = 35) -> list[dict[str, Any]]:
    return [
        {
            "type": "futures",
            "score": 90 - i,
            "reason": "test",
            "headline": f"Ordinary {i}",
            "data": {"id": 60000 + i, "name": f"Ordinary {i}", "llm_sport_category": "politics"},
        }
        for i in range(n)
    ]


def _make_members(seed: int, label: str) -> RoundupMembers:
    return RoundupMembers(
        members=[
            {"id": seed, "name": f"{label} A", "top_outcome": "Yes", "probability": 0.6, "status": "open"},
            {"id": seed + 1, "name": f"{label} B", "top_outcome": "No", "probability": 0.55, "status": "open"},
        ],
        title=f"{label} title",
        footer=f"{label} footer",
    )


@pytest.mark.asyncio
async def test_cold_restart_shows_five_or_none_never_partial_machinery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
    monkeypatch.setattr("app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.05)

    hang_rest = True

    def _make_mach_prod(idx: int) -> RoundupProducer:
        slug = f"machinery-g{idx}"

        async def _prod(_db: Any) -> Any:
            if hang_rest and idx >= 3:
                await asyncio.sleep(0.25)
                return None
            return _make_members(81000 + idx * 10, f"Mach {idx}")

        return RoundupProducer(
            slug=slug,
            name=f"Mach {idx}",
            kind="roundup",
            category="sports",
            section_title="Sec",
            footer="",
            produce=_prod,
        )

    standing = RoundupProducer(
        slug="roundup-standing-keep",
        name="Standing Round-Up",
        kind="roundup",
        category="economics",
        section_title="Sec",
        footer="Standing footer",
        produce=lambda _db: _make_members(82000, "Standing"),
    )

    producers = {standing.slug: standing}
    for i in range(1, 6):
        p = _make_mach_prod(i)
        producers[p.slug] = p

    monkeypatch.setattr("app.utils.roundup_containers.ROUNDUP_PRODUCERS", producers)
    monkeypatch.setattr("app.utils.roundup_containers.ensure_optional_roundup_candidates", lambda: None)

    class _DummySession:
        async def rollback(self) -> None:
            return None

    # 1. Cold restart: 2/5 machinery ready, 3/5 time out -> 0/5 machinery served, standing round-up STILL kept!
    out_partial = await add_roundup_feed_items(
        _DummySession(),
        _ordinary_deck(),
        budget_seconds=5.0,
        stage_budget_seconds=5.0,
        now=NOW,
        include_machinery=True,
    )
    slugs_partial = [
        it["data"]["collection_ref"]["slug"]
        for it in out_partial
        if it.get("type") == "bundle" and it.get("data", {}).get("kind") == "roundup"
    ]
    assert "roundup-standing-keep" in slugs_partial
    assert [s for s in slugs_partial if s.startswith("machinery-")] == []

    # 2. Same on machinery_only=True splice -> 0/5 machinery served.
    out_splice_partial = await add_roundup_feed_items(
        _DummySession(),
        _ordinary_deck(),
        budget_seconds=5.0,
        stage_budget_seconds=5.0,
        now=NOW,
        include_machinery=True,
        machinery_only=True,
    )
    assert [
        it["data"]["collection_ref"]["slug"]
        for it in out_splice_partial
        if it.get("type") == "bundle"
        and str(it.get("data", {}).get("collection_ref", {}).get("slug") or "").startswith("machinery-")
    ] == []

    # 3. Once all 5/5 are ready -> all 5/5 machinery cards are served!
    hang_rest = False
    out_all = await add_roundup_feed_items(
        _DummySession(),
        _ordinary_deck(),
        budget_seconds=5.0,
        stage_budget_seconds=5.0,
        now=NOW,
        include_machinery=True,
    )
    mach_slugs_all = [
        it["data"]["collection_ref"]["slug"]
        for it in out_all
        if it.get("type") == "bundle"
        and str(it.get("data", {}).get("collection_ref", {}).get("slug") or "").startswith("machinery-")
    ]
    assert len(mach_slugs_all) == 5
