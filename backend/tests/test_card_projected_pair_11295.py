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
    "sport",
    [
        "baseball_mlb",
        "mma_mixed_martial_arts",
        "boxing_boxing",
        # C2 (lane1b on c3fe360688): the writer's margin gate says yes to these,
        # but the pair is no final score. Puck line pinned at ±1.5 (NHL
        # 15333056 / 15332424 "4 – 3" whatever the price; AHL 15327140
        # "0.0 – 1.5"); tennis is games under a sets scoreboard (15326853).
        "icehockey_nhl",
        "icehockey_ahl",
        "tennis_atp_shanghai",
        # undeclared: no measured fixture says its pair is a scoreline
        "cricket_ipl",
        "rugbyleague_nrl",
        "aussierules_afl",
        "",
        None,
    ],
)
def test_a_sport_whose_pair_is_not_a_final_score_carries_no_pair(sport):
    assert _pair(_board(), sport=sport) is None
    assert not cpp.card_projection_wanted("scheduled", sport)
    assert not cpp.card_projection_wanted("live", sport)


@pytest.mark.parametrize(
    "sport",
    ["americanfootball_nfl", "americanfootball_ncaaf", "basketball_nba", "soccer_epl"],
)
def test_football_basketball_and_soccer_are_admitted(sport):
    assert cpp.card_projection_wanted("scheduled", sport)
    assert _pair(_board(), sport=sport) is not None


def test_the_card_admits_less_than_the_writers_margin_gate():
    """UX's table, not `sportsbook_spread_is_a_margin` (which the writer and the
    web still read, and which says yes to hockey and tennis)."""
    from app.utils.odds_math import sportsbook_spread_is_a_margin

    assert cpp.CARD_PROJECTION_SPORT_PREFIXES == (
        "americanfootball_",
        "basketball_",
        "soccer_",
    )
    for sport in ("icehockey_nhl", "tennis_atp_shanghai", "cricket_ipl"):
        assert sportsbook_spread_is_a_margin(sport)  # the control
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
        *[
            {
                "id": event_id,
                "stored_status": "scheduled",
                "served_status": "scheduled",
                "commence_time": _KICKOFF,
                "sport_key": sport,
            }
            for event_id, sport in (
                (15333056, "icehockey_nhl"),
                (15327140, "icehockey_ahl"),
                (15326853, "tennis_atp_shanghai"),
                (9, "cricket_ipl"),
            )
        ],
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
    """A savepoint: `async with` + an explicit `rollback()`; never released here."""

    def __init__(self, db):
        self.db = db
        self.done = False

    async def __aenter__(self):
        self.db.savepoints += 1
        self.db.log.append("SAVEPOINT")
        return self

    async def rollback(self):
        self.done = True
        self.db.rolled_back += 1
        self.db.log.append("ROLLBACK TO SAVEPOINT")
        await self.db.round_trip()

    async def __aexit__(self, exc_type, exc, tb):
        if self.done:
            return False
        if exc_type is not None:
            await self.rollback()
        else:
            self.db.log.append("RELEASE SAVEPOINT")
        return False


class _FeedDB(_DB):
    """The request session, modelling the server's `statement_timeout`.

    Every round trip costs ``rtt`` seconds; the read takes ``read_s`` and, past
    the SET LOCAL bound, is cancelled BY THE SERVER at the bound.
    """

    def __init__(self, rows, fail=None, *, read_s=0.0, rtt=0.0):
        super().__init__(rows)
        self.fail = fail
        self.read_s, self.rtt = read_s, rtt
        self.savepoints = 0
        self.rolled_back = 0
        self.settings: list[str] = []
        self.log: list[str] = []
        self.timeout_ms: int | None = None

    def begin_nested(self):
        return _Nested(self)

    async def round_trip(self):
        if self.rtt:
            await asyncio.sleep(self.rtt)

    async def execute(self, stmt):
        sql = str(stmt)
        if sql.startswith("SET LOCAL statement_timeout"):
            self.settings.append(sql)
            self.log.append(sql)
            self.timeout_ms = int(sql.split("'")[1].removesuffix("ms"))
            await self.round_trip()
            return _Result([])
        if self.fail is not None:
            raise self.fail
        self.log.append("READ")
        if self.read_s:
            bound = None if self.timeout_ms is None else self.timeout_ms / 1000
            if bound is not None and self.read_s > bound:
                await asyncio.sleep(bound)
                raise _QueryCanceled("canceling statement due to statement timeout")
            await asyncio.sleep(self.read_s)
        return await super().execute(stmt)


class _QueryCanceled(Exception):
    """Stands in for asyncpg's QueryCanceledError (SQLSTATE 57014)."""


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
    # No request budget passed: the cap alone. Rolled back, never released.
    assert db.log == [
        "SAVEPOINT",
        f"SET LOCAL statement_timeout = '{cpp.CARD_PROJECTION_READ_CAP_MS}ms'",
        "READ",
        "ROLLBACK TO SAVEPOINT",
    ]
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
    attach = src.index("await _attach_card_projected_pairs(")
    assert attach > loop_end
    assert (
        "remaining_s=projection_budget_s() if projection_budget_s else None"
        in src[attach:]
    )
    assert src.rstrip().endswith("return scored_items")


def test_the_events_stage_hands_the_attach_its_remaining_budget():
    """The one `_score_events` call under `_events_deadline` passes the live
    budget function, so the bound is read at attach time, not at stage start."""
    import inspect

    from app.routes import feed

    src = inspect.getsource(feed)
    stage = src.index("async with _events_deadline:")
    call_end = src.index("feed_items.extend(event_items)", stage)
    assert "projection_budget_s=_feed_budget_remaining_s," in src[stage:call_end]


# ── C1: the optional read is bounded inside the events budget ──────────────


@pytest.mark.parametrize(
    ("remaining_s", "expected"),
    [
        (None, cpp.CARD_PROJECTION_READ_CAP_MS),
        (20.0, cpp.CARD_PROJECTION_READ_CAP_MS),
        (1.2, 1200 - cpp.CARD_PROJECTION_DEADLINE_MARGIN_MS),
        (0.6255, 125),
        ((cpp.CARD_PROJECTION_DEADLINE_MARGIN_MS + 49) / 1000, 0),
        (0.0, 0),
    ],
)
def test_the_read_bound_is_the_cap_or_what_is_left_less_the_margin(
    remaining_s, expected
):
    got = cpp.card_projection_read_timeout_ms(remaining_s)
    assert got == expected and isinstance(got, int)


def test_no_wanted_card_or_no_time_left_means_no_round_trip():
    db = _FeedDB(_board())
    hockey = {
        "id": 15333056,
        "stored_status": "scheduled",
        "served_status": "scheduled",
        "commence_time": _KICKOFF,
        "sport_key": "icehockey_nhl",
    }
    assert (
        asyncio.run(cpp.read_card_projected_pairs_bounded(db, [hockey], timeout_ms=900))
        == {}
    )
    nfl = {**hockey, "id": 14780563, "sport_key": "americanfootball_nfl"}
    assert (
        asyncio.run(cpp.read_card_projected_pairs_bounded(db, [nfl], timeout_ms=0))
        == {}
    )
    assert db.log == []


def _run_on_virtual_clock(make_coro):
    """Run on a loop whose clock jumps to the next timer (no wall-clock sleeps)."""
    import selectors

    class _Jumping:
        def __init__(self, selector, loop):
            self._selector, self._loop = selector, loop

        def select(self, timeout=None):
            if timeout is not None and timeout > 0:
                self._loop.virtual_now += timeout
                timeout = 0
            return self._selector.select(timeout)

        def __getattr__(self, name):
            return getattr(self._selector, name)

    class _Loop(asyncio.SelectorEventLoop):
        def __init__(self):
            super().__init__(selectors.DefaultSelector())
            self.virtual_now = 0.0
            self._selector = _Jumping(self._selector, self)

        def time(self):
            return self.virtual_now

    loop = _Loop()
    try:
        return loop.run_until_complete(make_coro(loop))
    finally:
        loop.close()


def _attach_under_the_events_deadline(db, *, budget_s):
    """The events stage's shape: `asyncio.timeout(remaining)` around the build,
    with the remaining budget read live when the attach runs."""
    from app.routes.feed import _attach_card_projected_pairs

    items = [_feed_item(14780563)]

    async def _stage(loop):
        ends_at = loop.time() + budget_s
        deadline = asyncio.timeout(budget_s)
        async with deadline:
            await _attach_card_projected_pairs(
                db,
                items,
                [_event(14780563)],
                remaining_s=max(0.0, ends_at - loop.time()),
            )
        return deadline.expired(), loop.time()

    expired, finished_at = _run_on_virtual_clock(_stage)
    return items, expired, finished_at


def test_a_read_outlasting_its_bound_keeps_the_cards_and_the_events_stage_whole():
    """lane1b's C1. 1.2 s of budget left; the read would take 30 s. The server's
    bound (700 ms) cancels it, the savepoint takes the failure, and the stage
    finishes inside its deadline with the card and no pair.

    Mutants this bites: the SET LOCAL removed (the read runs 30 s → the events
    deadline expires); the bound set to the whole remaining budget, or the cap
    alone (the cancel lands at or past the deadline → expired)."""
    db = _FeedDB(_board(), read_s=30.0, rtt=0.05)
    items, expired, finished_at = _attach_under_the_events_deadline(db, budget_s=1.2)
    assert expired is False
    assert db.settings == ["SET LOCAL statement_timeout = '700ms'"]
    assert db.log[-2:] == ["READ", "ROLLBACK TO SAVEPOINT"]
    assert finished_at < 1.2
    assert items[0]["data"]["current_odds"] == {
        "home_probability": 0.7,
        "away_probability": 0.3,
    }


def test_a_read_inside_its_bound_still_carries_the_pair_under_the_deadline():
    """The control for the test above: same deadline, a read that fits."""
    db = _FeedDB(_board(), read_s=0.3, rtt=0.05)
    items, expired, _ = _attach_under_the_events_deadline(db, budget_s=1.2)
    assert expired is False
    odds = items[0]["data"]["current_odds"]
    assert (odds["projected_home_score"], odds["projected_away_score"]) == (29.7, 22.3)


def test_with_less_than_the_margin_left_the_read_is_not_started():
    db = _FeedDB(_board(), read_s=0.3, rtt=0.05)
    items, expired, _ = _attach_under_the_events_deadline(db, budget_s=0.5)
    assert expired is False and db.log == []
    assert "projected_home_score" not in items[0]["data"]["current_odds"]


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
