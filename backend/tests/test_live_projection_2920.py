"""#2920 — `current_odds.live_projection`: one marked in-play pair on all four routes.

The cards' admission (`card_projected_pair`, #11295) plus a scheduled,
non-placeholder start, per-book pairs that solve their own lines, and soccer
only in regulation. Pure rules first, then each route's wiring with fakes.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils import card_projected_pair as cpp
from app.utils.odds_math import project_scores
from app.utils.start_placeholder import start_placeholder_tag

# gotcha #44 — a fixed anchor, offsets only.
_KICKOFF = datetime(2026, 10, 19, 20, 25, tzinfo=timezone.utc)
_EVENT_ID = 15332758


@pytest.fixture(autouse=True)
def _now_is_mid_game(monkeypatch):
    # The stale filter compares the start to wall-clock now; pin it after the rows.
    monkeypatch.setattr(
        "app.utils.odds_filtering.datetime",
        SimpleNamespace(now=lambda tz=None: _KICKOFF + timedelta(minutes=50)),
    )


def _snap(book, spread, total, *, minutes=40, valid_minutes=None, home_prob=0.8,
          pair=None, event_id=_EVENT_ID):
    proj_home, proj_away = pair if pair is not None else project_scores(spread, total)
    return SimpleNamespace(
        id=hash(book) % 10_000,
        event_id=event_id,
        bookmaker=book,
        home_win_probability=home_prob,
        away_win_probability=None if home_prob is None else round(1 - home_prob, 4),
        home_spread=spread,
        over_under=total,
        projected_home_score=proj_home,
        projected_away_score=proj_away,
        captured_at=_KICKOFF + timedelta(minutes=minutes),
        valid_until=(
            None if valid_minutes is None else _KICKOFF + timedelta(minutes=valid_minutes)
        ),
    )


def _in_game():
    return [
        _snap("draftkings", -10.5, 48.5, minutes=30, valid_minutes=44),
        _snap("fanduel", -10.5, 48.5, minutes=41),
    ]


def _event(*, status="live", source="espn", tags=(), period="Q3", commence=_KICKOFF,
           event_id=_EVENT_ID):
    return SimpleNamespace(
        id=event_id,
        status=status,
        commence_time=commence,
        commence_time_source=source,
        event_tags=list(tags),
        period=period,
    )


def _live(snaps, event=None, *, served="live", sport="americanfootball_nfl"):
    return cpp.event_live_projection(
        snaps, event or _event(), served_status=served, sport_key=sport
    )


# ── the object ──────────────────────────────────────────────────────────────


def test_a_live_game_carries_one_marked_in_play_pair_with_its_provenance():
    live = _live(_in_game())
    assert live == {
        "projected_home_score": 29.5,
        "projected_away_score": 19.0,
        "kind": "in_play",
        "boundary": "commence_time",
        "boundary_at": _KICKOFF.isoformat(),
        # draftkings' effective time is its valid_until (44), fanduel's its
        # captured_at (41): the oldest confirmation, not the oldest capture (30).
        "earliest_confirmed_at": (_KICKOFF + timedelta(minutes=41)).isoformat(),
        "latest_captured_at": (_KICKOFF + timedelta(minutes=41)).isoformat(),
        "source": "sportsbooks",
        "basis": "consensus_spread_total",
        "bookmaker_count": 2,
        "unit": "points",
        "period": "full_game",
    }


def test_the_marked_pair_is_the_cards_bare_pair_on_an_ordinary_board():
    pair = cpp.card_projected_pair(
        _in_game(),
        stored_status="live",
        served_status="live",
        commence_time=_KICKOFF,
        sport_key="americanfootball_nfl",
        live_boundary_at=_KICKOFF,
        period="Q3",
    )
    live = pair[cpp.LIVE_PROJECTION_KEY]
    assert (live["projected_home_score"], live["projected_away_score"]) == (
        pair["projected_home_score"],
        pair["projected_away_score"],
    )


def test_without_the_live_inputs_the_card_pair_is_exactly_what_it_was():
    pair = cpp.card_projected_pair(
        _in_game(),
        stored_status="live",
        served_status="live",
        commence_time=_KICKOFF,
        sport_key="americanfootball_nfl",
    )
    assert set(pair) == {
        "projected_home_score",
        "projected_away_score",
        "projection_captured_at",
    }


# ── never a pregame pair as in-play ─────────────────────────────────────────


def test_books_frozen_at_kickoff_never_become_in_play_evidence():
    frozen = [
        _snap("draftkings", -7.5, 52.0, minutes=-30, valid_minutes=-1),
        _snap("fanduel", -7.0, 51.5, minutes=-25, valid_minutes=-1),
    ]
    assert _live(frozen) is None


def test_one_frozen_book_beside_live_ones_is_filtered_and_never_counted():
    snaps = [*_in_game(), _snap("betmgm", -7.5, 52.0, minutes=-30, valid_minutes=-1)]
    live = _live(snaps)
    assert live["bookmaker_count"] == 2
    assert live["earliest_confirmed_at"] >= live["boundary_at"]


@pytest.mark.parametrize("source", [None, "kalshi_ticker", "polymarket_venue"])
def test_a_start_no_schedule_published_withholds_the_object(source):
    assert _live(_in_game(), _event(source=source)) is None


def test_a_placeholder_start_withholds_the_object():
    tagged = _event(tags=[start_placeholder_tag(_KICKOFF)])
    assert _live(_in_game(), tagged) is None


def test_no_start_withholds_the_object():
    assert _live(_in_game(), _event(commence=None)) is None


@pytest.mark.parametrize("served", ["scheduled", "completed", "closed", "suspended", None])
def test_only_a_served_live_game_carries_the_object(served):
    assert _live(_in_game(), served=served) is None


@pytest.mark.parametrize("sport", ["icehockey_nhl", "baseball_mlb", "tennis_atp", None])
def test_a_sport_whose_pair_is_not_a_final_score_withholds_it(sport):
    assert _live(_in_game(), sport=sport) is None


# ── a pair is one book's pair ───────────────────────────────────────────────


def test_a_book_whose_pair_does_not_solve_its_own_lines_is_not_a_contributor():
    snaps = [
        *_in_game(),
        _snap("caesars", -10.5, 48.5, minutes=42, pair=(40.0, 10.0)),
    ]
    live = _live(snaps)
    assert live["bookmaker_count"] == 2
    assert (live["projected_home_score"], live["projected_away_score"]) == (29.5, 19.0)


def test_no_book_with_its_own_pair_means_no_object():
    snaps = [_snap("draftkings", -10.5, 48.5, pair=(40.0, 10.0))]
    assert _live(snaps) is None


# ── soccer: regulation only ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "period",
    ["1'", "45'", "45'+2'", "67'", "67", "90'", "90'+4'", "90+3", "HT", "Halftime",
     "1st Half", "2nd Half"],
)
def test_soccer_in_regulation_is_admitted(period):
    assert cpp.soccer_regulation_in_play(period) is True


@pytest.mark.parametrize(
    "period",
    [None, "", "91'", "105'", "105'+1'", "120'", "46'+1'", "ET", "AET", "Pen.",
     "Penalties", "FT", "Halftime ET", "End of 2nd Half", "Q3", "22:00"],
)
def test_soccer_outside_regulation_or_unknown_is_withheld(period):
    assert cpp.soccer_regulation_in_play(period) is False


def test_a_soccer_match_in_regulation_carries_goals_on_the_regulation_basis():
    snaps = [
        _snap("draftkings", -0.5, 2.5, home_prob=0.55),
        _snap("fanduel", -0.5, 2.5, home_prob=0.56),
    ]
    live = _live(snaps, _event(period="67'"), sport="soccer_epl")
    assert (live["unit"], live["period"]) == ("goals", "regulation")
    assert _live(snaps, _event(period="105'"), sport="soccer_epl") is None
    assert _live(snaps, _event(period=None), sport="soccer_epl") is None


# ── the four routes: one object per game ────────────────────────────────────


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _Result(self.rows)


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def rollback(self):
        return None


class _SavepointDB(_DB):
    def begin_nested(self):
        return _Nested()


def _card(status="live", sport="americanfootball_nfl"):
    return {
        "id": _EVENT_ID,
        "status": status,
        "sport": sport,
        "current_odds": {"home_probability": 0.8, "away_probability": 0.2},
    }


def test_feed_and_league_cards_carry_the_same_object_detail_and_search_compute():
    from app.routes.feed import _attach_card_projected_pairs as feed_attach
    from app.routes.league_futures import _attach_card_projected_pairs as league_attach

    expected = _live(_in_game())
    assert expected is not None

    item = {"type": "event", "data": _card()}
    db = _SavepointDB(_in_game())
    asyncio.run(feed_attach(db, [item], [_event()]))
    assert len(db.statements) == 2  # SET LOCAL + the one read: no new statement
    assert item["data"]["current_odds"][cpp.LIVE_PROJECTION_KEY] == expected

    brief = _card()
    db = _DB(_in_game())
    asyncio.run(league_attach(db, [_event()], [brief]))
    assert len(db.statements) == 1
    assert brief["current_odds"][cpp.LIVE_PROJECTION_KEY] == expected


def test_a_scheduled_card_gains_its_pair_and_no_marked_object():
    from app.routes.league_futures import _attach_card_projected_pairs as league_attach

    brief = _card(status="scheduled")
    pregame = [_snap("draftkings", -7.5, 52.0, minutes=-30)]
    asyncio.run(league_attach(_DB(pregame), [_event(status="scheduled")], [brief]))
    assert "projected_home_score" in brief["current_odds"]
    assert cpp.LIVE_PROJECTION_KEY not in brief["current_odds"]


def test_attach_never_overwrites_and_never_writes_an_absent_object():
    odds = {"home_probability": 0.8}
    cpp.attach_card_projected_pair(odds, {cpp.LIVE_PROJECTION_KEY: None})
    assert odds == {"home_probability": 0.8}
    odds[cpp.LIVE_PROJECTION_KEY] = "kept"
    cpp.attach_card_projected_pair(odds, {cpp.LIVE_PROJECTION_KEY: {"x": 1}})
    assert odds[cpp.LIVE_PROJECTION_KEY] == "kept"


def test_detail_and_search_ask_with_the_status_they_serve_and_the_rows_they_read():
    from app.routes import events

    detail = inspect.getsource(events.get_event)
    assert "event_live_projection(\n                        all_latest_snapshots," in detail
    assert 'served_status=response.get("status")' in detail

    search = inspect.getsource(events.search_events)
    assert 'event_live_projection(\n                            _odds_entry["all_snapshots"],' in search
    assert 'served_status=formatted.get("status")' in search


def test_the_detail_attach_sits_on_the_current_odds_it_extends():
    from app.routes import events

    detail = inspect.getsource(events.get_event)
    built = detail.index('response["current_odds"] = {')
    attach = detail.index("event_live_projection(")
    assert built < attach
