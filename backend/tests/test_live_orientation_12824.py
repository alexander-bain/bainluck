"""A pregame line cannot decide the side of an in-game venue quote."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.tasks.prediction_market_matching import (
    _check_and_fix_inversion,
    _phase2_persist_group_reading,
)
from app.utils.aggregation import stamp_source_reading
from app.utils.hero_probability import resolve_hero
from tests.test_phase2_writer_group_reading_cert767 import (
    _EventRow,
    _FakeSession,
    _Outcome,
    _ref,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("opening", "team", "quote"),
    [
        pytest.param(0.88, "Alex Michelsen", 0.92, id="opener-cannot-invert-away-quote"),
        pytest.param(None, "Alex Michelsen", 0.92, id="no-opener-control"),
        pytest.param(0.88, "Brandon Nakashima", 0.08, id="named-home-control"),
    ],
)
async def test_live_matcher_to_hero(opening, team, quote):
    now = datetime.now(timezone.utc)
    event = _EventRow(15299603, opening=opening)
    event.status = "live"
    event.commence_time = now - timedelta(minutes=30)
    event.completed_at = None
    outcome = _Outcome(9, 1, team, quote)
    outcome.id = 42
    outcome.last_updated = now - timedelta(seconds=1)
    group = [_ref(9, "US Open ATP: Brandon Nakashima vs Alex Michelsen")]
    session = _FakeSession([outcome], event)
    stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

    assert await _phase2_persist_group_reading(session, group, stats) == 9
    event.win_probability_sources = session.stamped_sources()
    hero = resolve_hero(event)
    assert hero.source == "blend"
    assert hero.home_probability == pytest.approx(0.08)
    assert event.win_probability_sources["polymarket"]["value"] == pytest.approx(0.08)
    assert session.added[0].home_win_probability == pytest.approx(0.08)


def _comparison_session(now, *, status="live", opening=None, snap=None, sources=None):
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(
        status=status,
        commence_time=now - timedelta(minutes=30),
        completed_at=None,
        opening_home_probability=opening,
        win_probability_sources=sources,
    )
    session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=snap))
    return session


def _witness(sources, source, value, at):
    return stamp_source_reading(sources, source, value, now=at, price_read_at=at)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["live", "scheduled"])
async def test_a_pregame_book_cannot_orient_a_quote_after_kickoff(status):
    now = datetime.now(timezone.utc)
    # Only a pregame row exists in odds_snapshots. Lack of a post-kickoff
    # consensus must leave the venue's computed side intact.
    session = _comparison_session(now, status=status, snap=0.88)
    assert await _check_and_fix_inversion(session, 1, 0.08, "polymarket") == 0.08


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("game_seconds", "seen_seconds", "book_count", "expected"),
    [
        pytest.param(120, -1, 5, 0.08, id="pregame"),
        pytest.param(120, 0, 5, 0.92, id="at-kickoff"),
        pytest.param(600, 301, 5, 0.92, id="299-seconds-old"),
        pytest.param(600, 300, 5, 0.08, id="300-seconds-old"),
        pytest.param(1800, 0, 5, 0.08, id="30-minutes-old"),
        pytest.param(120, 119, 2, 0.08, id="below-book-floor"),
        pytest.param(120, 121, 5, 0.08, id="future-read"),
    ],
)
async def test_only_admitted_recent_post_kickoff_betting_can_orient_live(
    game_seconds, seen_seconds, book_count, expected,
):
    now = datetime.now(timezone.utc)
    kickoff = now - timedelta(seconds=game_seconds)
    read_at = kickoff + timedelta(seconds=seen_seconds)
    sources = _witness({"betting_book_count": book_count}, "betting", 0.88, read_at)
    session = _comparison_session(now, sources=sources)
    session.get.return_value.commence_time = kickoff
    out = await _check_and_fix_inversion(session, 1, 0.08, "polymarket")
    assert out == pytest.approx(expected)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("peer_witnesses", "expected"),
    [
        pytest.param({}, 0.08, id="publication-stamps-cannot-vote"),
        pytest.param({"espn": -1, "mlb": -1}, 0.08, id="pregame-witnesses-cannot-vote"),
        pytest.param({"espn": 1790, "mlb": 1501}, 0.92, id="two-live-witnesses-correct-a-mirror"),
        pytest.param({"espn": 1790}, 0.08, id="one-live-witness-cannot-vote-alone"),
        pytest.param({"espn": 1790, "mlb": 1500}, 0.08, id="expired-witness-cannot-vote"),
        pytest.param({"espn": 1790, "mlb": 1790, "stat_model": 1790}, 0.08, id="split-vote"),
    ],
)
async def test_only_witnessed_side_votes_count_in_play(peer_witnesses, expected):
    now = datetime.now(timezone.utc)
    kickoff = now - timedelta(minutes=30)
    sources = {
        source: {"value": value, "updated_at": now.isoformat()}
        for source, value in [("espn", 0.96), ("mlb", 0.9)]
    }
    if "stat_model" in peer_witnesses:
        sources["stat_model"] = {"value": 0.10}
    for source, seconds in peer_witnesses.items():
        sources = _witness(sources, source, sources[source]["value"],
                           kickoff + timedelta(seconds=seconds))
    session = _comparison_session(now, sources=sources)
    out = await _check_and_fix_inversion(session, 1, 0.08, "polymarket")
    assert out == pytest.approx(expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["scheduled", "completed"])
async def test_pregame_and_completed_legacy_orientation_keep_the_opener(status):
    now = datetime.now(timezone.utc)
    session = _comparison_session(now, status=status, opening=0.88)
    if status == "scheduled":
        session.get.return_value.commence_time = now + timedelta(minutes=30)
    out = await _check_and_fix_inversion(session, 1, 0.08, "polymarket")
    assert out == pytest.approx(0.92)
