"""#9081 — the Bain Luck line and the hero caption follow the hero's admission rule.

THE SPECIMEN, read on production by lane1 at 06:50Z 2026-09-27 (390px):

    /events/14870012 — Clemson v Miami, NCAAF, pregame (Oct 3).

    hero     13% – 87%, captioned "4 sportsbooks"
    bag      {"kalshi": 0.13 (verified), "betting_book_count": 2}
    chart    Bain Luck line ending at 0.1045

Ruling 051 dropped `betting` because only two books quoted the 06:40Z poll
(betmgm 0.1024, draftkings 0.1066 — mean 0.1045), so the hero is Kalshi alone.
The chart's sportsbook series averaged those same two books and, before kickoff,
nothing decays (#4976): a two-source weighted median returns the heavier source
verbatim, so the line ended on the number the hero was forbidden to show. The
caption counted every served sportsbook row, a 53-day-old quote included.

Route-level for the chart (the #6863 lesson: a unit guard on the helper passes
just as happily when the call site never asks it), unit-level for the engine
marker and the caption count.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.routes.events import _sportsbook_withdrawal, get_event_odds_history
from app.utils.aggregation import TimestampedProb, compute_aggregated_probability
from app.utils.hero_probability import hero_sportsbook_count
from tests.test_history_end_cap_hides_every_point import _DispatchingSession

UTC = timezone.utc
_SPECIMEN_ID = 14870012

#: The specimen's market reading is Kalshi's. The fixture carries it as
#: Polymarket (same 0.8 weight, same eligibility stamp) because a pre-kickoff
#: Kalshi series also asks `KALSHI_BOOK_SILENT_FOR_EVENT_SQL`, which the shared
#: dispatching harness does not answer — the route's try swallows that and
#: serves no market series at all, which would make every arm here vacuous.
_ELIGIBLE = {
    "v": 1,
    "rule": "live_blend.admissible_as_blend_speaker@5031",
    "scope": "full_event_winner",
    "status": "verified",
}


def _market_block(now, value=0.13):
    return {
        "value": value,
        "updated_at": (now - timedelta(hours=34)).isoformat(),
        "eligibility": dict(_ELIGIBLE),
    }


def _refused_bag(now):
    """The specimen's bag: Kalshi speaks, the books were dropped under the floor."""
    return {"polymarket": _market_block(now), "betting_book_count": 2}


def _admitted_bag(now):
    """The control: three books quoted, so `betting` is in the hero."""
    return {
        "polymarket": _market_block(now),
        # Stamped BEFORE the series' last bucket so the pre-match pin stands
        # down (`_blend_outlives_edge`): a pinned edge would print the hero
        # whether or not the books were withdrawn, and this control would pass
        # against a withdrawal that always fires.
        "betting": {
            "value": 0.1109,
            "updated_at": (now - timedelta(hours=2)).isoformat(),
        },
        "betting_book_count": 3,
    }


def _event(sources, *, status="scheduled"):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=_SPECIMEN_ID,
        status=status,
        commence_time=now + timedelta(days=6, hours=16),
        completed_at=None,
        home_team_name="Clemson Tigers",
        away_team_name="Miami Hurricanes",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key="americanfootball_ncaaf"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources=sources,
        opening_home_probability=None,
        opening_away_probability=None,
    )


def _wp(when, prob, source="polymarket"):
    return SimpleNamespace(
        event_id=_SPECIMEN_ID,
        captured_at=when,
        source=source,
        home_win_probability=prob,
        away_win_probability=round(1.0 - prob, 4),
        draw_probability=None,
        game_state=None,
    )


_BOOK_IDS = iter(range(1, 10_000))


def _book(bookmaker, captured, until, prob):
    return SimpleNamespace(
        id=next(_BOOK_IDS),
        event_id=_SPECIMEN_ID,
        bookmaker=bookmaker,
        captured_at=captured,
        valid_until=until,
        home_win_probability=prob,
        away_win_probability=round(1.0 - prob, 4),
        home_spread=None,
        away_spread=None,
        over_under=None,
        projected_home_score=None,
        projected_away_score=None,
        home_moneyline=None,
        away_moneyline=None,
        reading_count=1,
    )


def _specimen_rows(now):
    """The market flat at 0.13; three books early at ~0.126, then two at 0.1045."""
    early = now - timedelta(hours=20)
    drop = now - timedelta(minutes=10)
    wp = [_wp(now - timedelta(hours=40), 0.13), _wp(now - timedelta(hours=34), 0.13)]
    odds = [
        _book("fanduel", early, early + timedelta(hours=5), 0.1260),
        _book("betmgm", early, drop, 0.1260),
        _book("draftkings", early, drop, 0.1260),
        _book("betmgm", drop, None, 0.1024),
        _book("draftkings", drop, None, 0.1066),
    ]
    return wp, odds


async def _serve(event, wp_rows, odds_rows):
    session = _DispatchingSession(event, wp_rows, odds_rows)
    return await get_event_odds_history(
        event_id=event.id, hours=720, response=MagicMock(headers={}), db=session
    )


# ---------------------------------------------------------------------------
# The ship — the chart's right edge is the hero's number
# ---------------------------------------------------------------------------


async def test_a_refused_sportsbook_consensus_does_not_end_the_line():
    now = datetime.now(UTC)
    wp, odds = _specimen_rows(now)
    payload = await _serve(_event(_refused_bag(now)), wp, odds)

    line = payload["aggregate_line"]
    assert line, "the market plus the books must still draw a Bain Luck line"
    assert line[-1]["home_probability"] == pytest.approx(0.13), (
        "the line ended on the sportsbook mean ruling 051 refused"
    )


async def test_the_books_still_draw_the_history_they_were_admitted_for():
    """Earlier buckets keep the sportsbooks — this ends their say, not their past."""
    now = datetime.now(UTC)
    wp, odds = _specimen_rows(now)
    payload = await _serve(_event(_refused_bag(now)), wp, odds)

    values = [p["home_probability"] for p in payload["aggregate_line"]]
    assert pytest.approx(0.126) in values


async def test_control_an_admitted_consensus_still_ends_the_line():
    """Three books quoted, `betting` is in the hero — the line is unchanged."""
    now = datetime.now(UTC)
    wp, odds = _specimen_rows(now)
    payload = await _serve(_event(_admitted_bag(now)), wp, odds)

    assert payload["aggregate_line"][-1]["home_probability"] == pytest.approx(0.1045)


# ---------------------------------------------------------------------------
# The engine marker
# ---------------------------------------------------------------------------


def _tp(when, prob):
    return TimestampedProb(timestamp=when, home_probability=prob)


def test_a_withdrawal_stops_the_pregame_carry_forward():
    t0 = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    sources = {
        "betting": [_tp(t0, 0.10), _tp(t0 + timedelta(hours=1), None)],
        "kalshi": [_tp(t0, 0.13)],
    }
    out = compute_aggregated_probability(
        sources, bucket_seconds=60, pregame_until=t0 + timedelta(days=5)
    )
    assert out[0].home_probability == pytest.approx(0.10)
    assert out[-1].timestamp == t0 + timedelta(hours=1)
    assert out[-1].home_probability == pytest.approx(0.13)


def test_without_the_marker_the_heavier_source_carries_on():
    """Strawman: the same inputs minus the withdrawal end on the books."""
    t0 = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    sources = {
        "betting": [_tp(t0, 0.10), _tp(t0 + timedelta(hours=1), 0.10)],
        "kalshi": [_tp(t0, 0.13)],
    }
    out = compute_aggregated_probability(
        sources, bucket_seconds=60, pregame_until=t0 + timedelta(days=5)
    )
    assert out[-1].home_probability == pytest.approx(0.10)


def test_a_source_that_speaks_again_after_withdrawing_is_heard():
    t0 = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    sources = {
        "betting": [
            _tp(t0, 0.10),
            _tp(t0 + timedelta(hours=1), None),
            _tp(t0 + timedelta(hours=2), 0.11),
        ],
        "kalshi": [_tp(t0, 0.13)],
    }
    out = compute_aggregated_probability(
        sources, bucket_seconds=60, pregame_until=t0 + timedelta(days=5)
    )
    assert out[-1].home_probability == pytest.approx(0.11)


# ---------------------------------------------------------------------------
# `_sportsbook_withdrawal`
# ---------------------------------------------------------------------------


def _history_at(when):
    return [{"timestamp": when.isoformat(), "home_probability": 0.1}]


def test_withdrawal_lands_on_the_latest_measurement():
    now = datetime(2026, 9, 27, 6, 50, tzinfo=UTC)
    seen = now - timedelta(minutes=2)
    snaps = [
        _book("betmgm", now - timedelta(hours=1), seen, 0.10),
        _book("draftkings", now - timedelta(minutes=10), None, 0.10),
    ]
    got = _sportsbook_withdrawal(
        snaps, _history_at(now - timedelta(minutes=10)),
        hero_sources=["polymarket"], is_finished=False, status="scheduled",
    )
    assert got == seen


def test_withdrawal_never_lands_before_the_last_history_point():
    now = datetime(2026, 9, 27, 6, 50, tzinfo=UTC)
    snaps = [_book("betmgm", now - timedelta(hours=1), None, 0.10)]
    got = _sportsbook_withdrawal(
        snaps, _history_at(now),
        hero_sources=["polymarket"], is_finished=False, status="scheduled",
    )
    assert got == now


@pytest.mark.parametrize(
    "hero_sources,is_finished,status",
    [
        (["polymarket", "betting"], False, "scheduled"),  # the hero counts the books
        (None, False, "scheduled"),  # folded: the hero could not be asked
        (["polymarket"], True, "scheduled"),  # the terminal point owns the edge
        (["polymarket"], False, "completed"),  # settled: not today's bag
    ],
)
def test_no_withdrawal_where_the_line_is_not_ours_to_move(
    hero_sources, is_finished, status
):
    now = datetime(2026, 9, 27, 6, 50, tzinfo=UTC)
    snaps = [_book("betmgm", now - timedelta(hours=1), now, 0.10)]
    assert (
        _sportsbook_withdrawal(
            snaps, _history_at(now - timedelta(hours=1)),
            hero_sources=hero_sources, is_finished=is_finished, status=status,
        )
        is None
    )


# ---------------------------------------------------------------------------
# The caption count
# ---------------------------------------------------------------------------


def test_no_book_stands_behind_a_hero_the_floor_emptied():
    now = datetime.now(UTC)
    assert hero_sportsbook_count(_event(_refused_bag(now))) == 0


def test_the_count_is_the_one_stored_beside_an_admitted_consensus():
    now = datetime.now(UTC)
    assert hero_sportsbook_count(_event(_admitted_bag(now))) == 3


def test_an_admitted_consensus_with_no_count_is_unknown_not_zero():
    now = datetime.now(UTC)
    bag = _admitted_bag(now)
    del bag["betting_book_count"]
    assert hero_sportsbook_count(_event(bag)) is None


# ---------------------------------------------------------------------------
# The caption count, as the detail route serves it
# ---------------------------------------------------------------------------

from tests.test_blend_fold_chart_pin_parity_3911 import (  # noqa: E402
    CANON_ID as _CANON_ID,
    _now as _route_now,
    both_routes as _shared_both_routes,
)


@pytest.fixture
def detail_route(monkeypatch):
    routes = _shared_both_routes.__wrapped__(monkeypatch)
    routes.cache.clear()
    yield routes
    routes.cache.clear()


def _detail(routes, sources):
    now = _route_now()
    session = routes.session(now, sources=sources, twin_sources={})
    session.event.status = "scheduled"
    session.event.commence_time = now + timedelta(days=6)
    return routes.detail(session)


def test_the_detail_route_serves_no_books_behind_a_floor_emptied_hero(detail_route):
    now = _route_now()
    detail = _detail(
        detail_route,
        {"polymarket": {"value": 0.13, "updated_at": now.isoformat()},
         "betting_book_count": 2},
    )
    assert detail["hero_probability_source"] == "blend"
    assert detail["hero_sportsbook_count"] == 0


def test_the_detail_route_serves_the_books_behind_an_admitted_consensus(detail_route):
    now = _route_now()
    detail = _detail(
        detail_route,
        {"polymarket": {"value": 0.13, "updated_at": now.isoformat()},
         "betting": {"value": 0.11, "updated_at": now.isoformat()},
         "betting_book_count": 3},
    )
    assert detail["hero_probability_source"] == "blend"
    assert detail["hero_sportsbook_count"] == 3
