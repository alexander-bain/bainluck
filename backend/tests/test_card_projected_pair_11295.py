"""#11295 — the list cards' projected pair: same consensus as detail, narrower admission.

The real-Postgres half (the batched read against `/api/events/{id}` on one seeded
game) is `tests/integration/test_card_projected_pair_11295_pg.py`. This file pins
the pure rules and the two route wirings with fakes.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils import card_projected_pair as cpp
from app.utils.odds_math import aggregate_bookmaker_odds, project_scores

# gotcha #44 — a fixed anchor, offsets only.
_KICKOFF = datetime(2026, 10, 19, 20, 25, tzinfo=timezone.utc)


def _snap(
    book: str,
    home_prob: float | None,
    spread: float | None,
    total: float | None,
    *,
    minutes: int = -60,
    valid_minutes: int | None = None,
    event_id: int = 14780563,
):
    """One `odds_snapshots` row shaped as the writer stores it."""
    proj_home = proj_away = None
    if spread is not None and total is not None:
        proj_home, proj_away = project_scores(spread, total)
    captured = _KICKOFF + timedelta(minutes=minutes)
    return SimpleNamespace(
        event_id=event_id,
        bookmaker=book,
        home_win_probability=home_prob,
        away_win_probability=None if home_prob is None else round(1 - home_prob, 4),
        home_spread=spread,
        over_under=total,
        projected_home_score=proj_home,
        projected_away_score=proj_away,
        captured_at=captured,
        valid_until=(
            None
            if valid_minutes is None
            else _KICKOFF + timedelta(minutes=valid_minutes)
        ),
    )


def _board():
    # 49ers (home) favoured by ~7 with a total near 52 — UX's 14780563 shape.
    return [
        _snap("draftkings", 0.70, -7.5, 52.0, minutes=-30),
        _snap("fanduel", 0.71, -7.0, 51.5, minutes=-25),
        _snap("betmgm", 0.69, -7.5, 52.5, minutes=-20),
    ]


def _pair(
    snaps, *, stored="scheduled", served="scheduled", sport="americanfootball_nfl"
):
    return cpp.card_projected_pair(
        snaps,
        stored_status=stored,
        served_status=served,
        commence_time=_KICKOFF,
        sport_key=sport,
    )


# ── positive: the detail consensus, unchanged ──────────────────────────────


def test_scheduled_card_carries_the_detail_consensus_pair_and_its_capture_time():
    snaps = _board()
    pair = _pair(snaps)
    detail = aggregate_bookmaker_odds(snaps)
    assert pair == {
        "projected_home_score": detail["projected_home_score"],
        "projected_away_score": detail["projected_away_score"],
        "projection_captured_at": (_KICKOFF + timedelta(minutes=-20)).isoformat(),
    }
    # Literal, so the assertion cannot pass by reading the same function twice.
    assert pair["projected_home_score"] == 29.7
    assert pair["projected_away_score"] == 22.3


def test_home_and_away_keep_their_named_sides():
    # Away favoured: the larger number must land on the AWAY key.
    snaps = [
        _snap("draftkings", 0.30, 6.5, 44.0),
        _snap("fanduel", 0.31, 6.0, 44.5),
        _snap("betmgm", 0.29, 6.5, 43.5),
    ]
    pair = _pair(snaps)
    assert pair["projected_home_score"] < pair["projected_away_score"]
    assert (pair["projected_home_score"], pair["projected_away_score"]) == (18.8, 25.1)


def test_a_reversed_book_is_left_out_exactly_as_detail_leaves_it_out():
    honest = [
        _snap("draftkings", 0.80, -10.0, 48.0),
        _snap("fanduel", 0.81, -10.0, 48.0),
        _snap("betmgm", 0.79, -10.0, 48.0),
        _snap("caesars", 0.80, -10.0, 48.0),
    ]
    # Its moneyline is mirrored, so detail drops it; its pair would drag the mean.
    mirrored = _snap("bovada", 0.20, 10.0, 48.0)
    pair = _pair([*honest, mirrored])
    assert (pair["projected_home_score"], pair["projected_away_score"]) == (29.0, 19.0)


# ── refusals ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "served", ["completed", "closed", "suspended", "postponed", None]
)
def test_a_terminal_or_unknown_state_carries_no_pair(served):
    assert _pair(_board(), stored=served or "completed", served=served) is None


@pytest.mark.parametrize(
    "sport", ["baseball_mlb", "mma_mixed_martial_arts", "boxing_boxing"]
)
def test_a_sport_whose_spread_is_not_a_margin_carries_no_pair(sport):
    assert _pair(_board(), sport=sport) is None
    assert not cpp.card_projection_wanted("scheduled", sport)


def test_no_book_with_a_spread_and_total_means_no_pair_never_zero_zero():
    snaps = [_snap("draftkings", 0.6, None, 48.0), _snap("fanduel", 0.6, -3.0, None)]
    assert _pair(snaps) is None
    assert _pair([]) is None


@pytest.mark.parametrize(
    "home, away",
    [
        (None, 21.0),  # one half only
        (24.0, None),
        (float("nan"), 21.0),
        (24.0, float("inf")),
        (-1.8, 5.8),  # #9006's "Proj 6--2" shape
    ],
)
def test_an_unpaired_nonfinite_or_negative_consensus_is_refused(
    monkeypatch, home, away
):
    monkeypatch.setattr(
        cpp,
        "aggregate_bookmaker_odds",
        lambda _s: {"projected_home_score": home, "projected_away_score": away},
    )
    assert _pair(_board()) is None


def test_a_live_card_never_carries_a_pregame_only_pair():
    # Every book froze at kickoff. The stale filter falls back to all of them
    # and detail would serve this pair under a live game; a card does not.
    pregame_only = [
        _snap("draftkings", 0.70, -7.5, 52.0, minutes=-30, valid_minutes=-1),
        _snap("fanduel", 0.71, -7.0, 51.5, minutes=-25, valid_minutes=-1),
    ]
    assert _pair(pregame_only, stored="live", served="live") is None


def test_a_live_card_carries_the_in_game_pair_from_books_quoting_since_kickoff(
    monkeypatch,
):
    in_game = [
        _snap("draftkings", 0.85, -10.5, 48.5, minutes=40),
        _snap("fanduel", 0.86, -10.5, 48.5, minutes=41),
    ]
    frozen = _snap("betmgm", 0.70, -7.5, 52.0, minutes=-30, valid_minutes=-1)
    # The filter compares to wall-clock now; pin it after the in-game rows.
    monkeypatch.setattr(
        "app.utils.odds_filtering.datetime",
        SimpleNamespace(now=lambda tz=None: _KICKOFF + timedelta(minutes=45)),
    )
    pair = _pair([*in_game, frozen], stored="live", served="live")
    assert (pair["projected_home_score"], pair["projected_away_score"]) == (29.5, 19.0)
    assert (
        pair["projection_captured_at"] == (_KICKOFF + timedelta(minutes=41)).isoformat()
    )


def test_a_live_card_with_no_start_time_carries_no_pair():
    assert (
        cpp.card_projected_pair(
            _board(),
            stored_status="live",
            served_status="live",
            commence_time=None,
            sport_key="americanfootball_nfl",
        )
        is None
    )


# ── attach: additive only ──────────────────────────────────────────────────


def test_attach_adds_the_keys_and_leaves_the_probabilities_alone():
    odds = {"home_probability": 0.62, "away_probability": 0.38, "source": "blend"}
    before = dict(odds)
    pair = _pair(_board())
    cpp.attach_card_projected_pair(odds, pair)
    assert {k: odds[k] for k in before} == before
    assert odds["projected_home_score"] == pair["projected_home_score"]
    assert "captured_at" not in odds  # the blend is not re-dated (#7221)


def test_attach_never_creates_current_odds_and_never_overwrites():
    cpp.attach_card_projected_pair(None, {"projected_home_score": 1.0})
    odds = {"home_probability": 0.5, "projected_home_score": 17.0}
    cpp.attach_card_projected_pair(
        odds, {"projected_home_score": 30.0, "projected_away_score": 20.0}
    )
    assert odds["projected_home_score"] == 17.0
    assert odds["projected_away_score"] == 20.0
    empty = {"home_probability": 0.5}
    cpp.attach_card_projected_pair(empty, None)
    assert empty == {"home_probability": 0.5}


# ── the batched read: one statement, only wanted ids ───────────────────────


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


def test_one_statement_for_many_cards_and_refused_cards_are_not_read(monkeypatch):
    seen_ids = []
    import app.routes.events as events_route

    real = events_route.latest_odds_per_bookmaker_query

    def _spy(ids):
        seen_ids.append(list(ids))
        return real(ids)

    monkeypatch.setattr(events_route, "latest_odds_per_bookmaker_query", _spy)
    rows = [
        *_board(),
        *[_snap(s.bookmaker, 0.6, -3.0, 44.0, event_id=2) for s in _board()],
    ]
    db = _DB(rows)
    cards = [
        {
            "id": 14780563,
            "stored_status": "scheduled",
            "served_status": "scheduled",
            "commence_time": _KICKOFF,
            "sport_key": "americanfootball_nfl",
        },
        {
            "id": 2,
            "stored_status": "scheduled",
            "served_status": "scheduled",
            "commence_time": _KICKOFF,
            "sport_key": "basketball_nba",
        },
        {
            "id": 3,
            "stored_status": "completed",
            "served_status": "completed",
            "commence_time": _KICKOFF,
            "sport_key": "americanfootball_nfl",
        },
        {
            "id": 4,
            "stored_status": "scheduled",
            "served_status": "scheduled",
            "commence_time": _KICKOFF,
            "sport_key": "baseball_mlb",
        },
    ]
    pairs = asyncio.run(cpp.read_card_projected_pairs(db, cards))
    assert len(db.statements) == 1
    assert seen_ids == [[2, 14780563]]
    assert set(pairs) == {2, 14780563}
    assert pairs[2]["projected_home_score"] == 23.5


def test_no_wanted_card_means_no_statement():
    db = _DB([])
    cards = [
        {
            "id": 3,
            "stored_status": "completed",
            "served_status": "completed",
            "commence_time": _KICKOFF,
            "sport_key": "americanfootball_nfl",
        }
    ]
    assert asyncio.run(cpp.read_card_projected_pairs(db, cards)) == {}
    assert db.statements == []


# ── the two route wirings ──────────────────────────────────────────────────


class _Nested:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        self.db.savepoints += 1

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.db.rolled_back += 1
        return False


class _FeedDB(_DB):
    def __init__(self, rows, fail=None):
        super().__init__(rows)
        self.fail = fail
        self.savepoints = 0
        self.rolled_back = 0

    def begin_nested(self):
        return _Nested(self)

    async def execute(self, stmt):
        if self.fail is not None:
            raise self.fail
        return await super().execute(stmt)


def _feed_item(event_id, status="scheduled", sport="americanfootball_nfl", odds=True):
    data = {"id": event_id, "status": status, "sport": sport}
    if odds:
        data["current_odds"] = {"home_probability": 0.7, "away_probability": 0.3}
    return {"type": "event", "data": data}


def _event(event_id, status="scheduled"):
    return SimpleNamespace(id=event_id, status=status, commence_time=_KICKOFF)


def test_feed_cards_gain_the_pair_in_one_savepointed_read():
    from app.routes.feed import _attach_card_projected_pairs

    items = [
        _feed_item(14780563),
        _feed_item(5, status="completed"),
        _feed_item(6, odds=False),
        {"type": "futures", "data": {"id": 14780563, "current_odds": {}}},
    ]
    db = _FeedDB(_board())
    asyncio.run(
        _attach_card_projected_pairs(
            db, items, [_event(14780563), _event(5, "completed"), _event(6)]
        )
    )
    assert db.savepoints == 1 and len(db.statements) == 1
    odds = items[0]["data"]["current_odds"]
    assert (odds["projected_home_score"], odds["projected_away_score"]) == (29.7, 22.3)
    assert odds["home_probability"] == 0.7
    assert "projected_home_score" not in items[1]["data"]["current_odds"]
    assert "current_odds" not in items[2]["data"]
    assert items[3]["data"]["current_odds"] == {}


def test_a_failed_feed_read_costs_the_cards_their_pair_and_nothing_else():
    from app.routes.feed import _attach_card_projected_pairs

    items = [_feed_item(14780563)]
    db = _FeedDB(_board(), fail=RuntimeError("statement failed"))
    asyncio.run(_attach_card_projected_pairs(db, items, [_event(14780563)]))
    assert db.rolled_back == 1
    assert items[0]["data"]["current_odds"] == {
        "home_probability": 0.7,
        "away_probability": 0.3,
    }


def test_a_cancelled_feed_read_propagates_as_itself():
    from app.routes.feed import _attach_card_projected_pairs

    items = [_feed_item(14780563)]
    db = _FeedDB(_board(), fail=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_attach_card_projected_pairs(db, items, [_event(14780563)]))


def test_score_events_calls_the_attach_after_its_loop():
    import inspect

    from app.routes import feed

    src = inspect.getsource(feed._score_events)
    loop_end = src.index("scored_items.append(item)")
    attach = src.index("await _attach_card_projected_pairs(db, scored_items, events)")
    assert attach > loop_end
    assert src.rstrip().endswith("return scored_items")


def test_league_upcoming_cards_gain_the_pair_matched_by_id():
    from app.routes.league_futures import _attach_card_projected_pairs

    briefs = [
        {
            "id": 7,
            "status": "scheduled",
            "sport": "americanfootball_nfl",
            "current_odds": {"home_probability": 0.4, "away_probability": 0.6},
        },
        {
            "id": 14780563,
            "status": "scheduled",
            "sport": "americanfootball_nfl",
            "current_odds": {"home_probability": 0.7, "away_probability": 0.3},
        },
        {"id": 8, "status": "scheduled", "sport": "americanfootball_nfl"},
    ]
    db = _DB(_board())
    # Rows out of brief order: matched by id, never by position.
    asyncio.run(
        _attach_card_projected_pairs(
            db, [_event(14780563), _event(7), _event(8)], briefs
        )
    )
    assert len(db.statements) == 1
    assert briefs[1]["current_odds"]["projected_home_score"] == 29.7
    assert "projected_home_score" not in briefs[0]["current_odds"]
    assert "current_odds" not in briefs[2]


def test_league_route_attaches_after_the_settlement_read_on_the_capped_rail():
    import inspect

    from app.routes import league_futures

    src = inspect.getsource(league_futures)
    settlement = src.index("_attach_venue_settlement(\n                        db,")
    attach = src.index("_attach_card_projected_pairs(db, _g_events, upcoming_games)")
    cap = src.index("upcoming_games = _grows[:UPCOMING_GAMES_LIMIT]")
    assert cap < settlement < attach


def test_card_keys_are_the_detail_names_the_clients_already_read():
    # `frontend/lib/projectedFinalPair.ts` and the native decoders read these.
    assert cpp.CARD_PROJECTION_KEYS[:2] == (
        "projected_home_score",
        "projected_away_score",
    )
    assert math.isfinite(_pair(_board())["projected_away_score"])
