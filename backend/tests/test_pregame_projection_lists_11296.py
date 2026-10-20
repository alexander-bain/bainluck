"""#11296 — `/api/feed` and `/api/leagues/{sport}` carry the same pregame projection as the page.

Stacked on #11295 (D1), whose attach puts the CURRENT sportsbook pair on
scheduled and live cards. This one puts the PREGAME projection on finished
cards. Both choose by the status the card prints, so a card carries at most one
of the two pairs (Discover's clearance condition 1). That is asserted here by
running both attaches over one mixed set of cards.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.utils.odds_math import project_scores

KICK = datetime(2026, 10, 18, 17, 0, tzinfo=timezone.utc)
FUTURE = datetime(2099, 1, 1, 20, 0, tzinfo=timezone.utc)
FINAL, UPCOMING, TENNIS, VENUE = 15_328_569, 14_780_563, 15_326_853, 15_328_571


def _snap(event_id, book, minutes, spread, total, home_p, *, start=KICK, rid):
    home, away = project_scores(spread, total)
    return SimpleNamespace(
        id=rid, event_id=event_id, bookmaker=book,
        captured_at=start + timedelta(minutes=minutes),
        valid_until=start + timedelta(minutes=minutes),
        home_win_probability=home_p, away_win_probability=round(1 - home_p, 4),
        home_spread=spread, over_under=total,
        projected_home_score=home, projected_away_score=away,
    )


#: What PREGAME_PROJECTION_SQL returns for the final: each book's last row
#: before 17:00Z (25.8/22.2 and 25.0/22.5 → 25.4/22.4).
PREGAME = [
    _snap(FINAL, "draftkings", -10, -3.5, 48.0, 0.6, rid=1),
    _snap(FINAL, "fanduel", -30, -2.5, 47.5, 0.58, rid=2),
]
#: What #11295's latest-per-book read returns: the upcoming game's board, and
#: the final's in-play 20:25Z rows (31.2/23.8), which must reach no card.
LATEST = [
    _snap(UPCOMING, "draftkings", -30, -7.0, 52.0, 0.72, start=FUTURE, rid=11),
    _snap(UPCOMING, "fanduel", -25, -7.5, 51.5, 0.73, start=FUTURE, rid=12),
    _snap(FINAL, "draftkings", 205, -7.4, 55.0, 0.9, rid=13),
    _snap(FINAL, "fanduel", 205, -7.4, 55.0, 0.9, rid=14),
]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __await__(self):  # the helper awaits begin_nested() directly
        async def _self():
            return self

        return _self().__await__()

    async def commit(self):
        return None

    async def rollback(self):
        return None


class _DB:
    """Answers #11295's ORM read and #11296's text read, and counts each."""

    def __init__(self):
        self.projection_reads: list[dict] = []
        self.pair_reads = 0
        #: Every statement in order, so a bound can be placed before its read.
        self.statements: list[str] = []

    def begin_nested(self):
        return _Nested()

    async def execute(self, stmt, params=None):
        self.statements.append(str(stmt))
        if str(stmt).startswith("SET LOCAL statement_timeout"):
            return _Result([])
        if "WITH RECURSIVE bounds" in str(stmt):
            self.projection_reads.append(params)
            return _Result([r for r in PREGAME if r.event_id in params["ids"]])
        self.pair_reads += 1
        return _Result(LATEST)


def _event(event_id, status, *, start=KICK, source="odds_api"):
    return SimpleNamespace(
        id=event_id, status=status, commence_time=start,
        commence_time_source=source, event_tags=[],
    )


EVENTS = [
    _event(FINAL, "completed"),
    _event(UPCOMING, "scheduled", start=FUTURE),
    _event(TENNIS, "completed"),
    _event(VENUE, "completed", source="kalshi"),
]


def _card(event_id, status, sport="americanfootball_nfl"):
    return {
        "id": event_id, "status": status, "sport": sport,
        "current_odds": {"home_probability": 0.6, "away_probability": 0.4},
    }


def _cards():
    return [
        _card(FINAL, "completed"),
        _card(UPCOMING, "scheduled"),
        _card(TENNIS, "completed", sport="tennis_atp_shanghai_masters"),
        _card(VENUE, "completed"),
    ]


def _assert_one_pair_per_card(cards):
    by_id = {c["id"]: c for c in cards}
    final = by_id[FINAL]
    assert (
        final["pregame_projection"]["projected_home_score"],
        final["pregame_projection"]["projected_away_score"],
    ) == (25.4, 22.4)
    assert final["pregame_projection"]["kind"] == "last_before_scheduled_start"
    # The in-play 31.2/23.8 reached neither key on the final.
    assert "projected_home_score" not in final["current_odds"]
    upcoming = by_id[UPCOMING]
    assert upcoming["current_odds"]["projected_home_score"] is not None
    assert "pregame_projection" not in upcoming
    assert "pregame_projection_unavailable" not in upcoming
    assert by_id[TENNIS]["pregame_projection_unavailable"] == "format_unsupported"
    assert by_id[VENUE]["pregame_projection_unavailable"] == "start_not_from_schedule"
    for card in cards:
        has_current = card.get("current_odds", {}).get("projected_home_score") is not None
        assert not (has_current and "pregame_projection" in card), card["id"]


# ── /api/feed ────────────────────────────────────────────────────────────────


def test_feed_cards_carry_at_most_one_pair_and_the_final_its_pregame_projection():
    from app.routes.feed import _attach_card_projected_pairs, _attach_pregame_projections

    items = [{"type": "event", "data": c} for c in _cards()]
    items.append({"type": "futures", "data": {"id": FINAL, "status": "completed"}})
    db = _DB()

    async def _both():
        await _attach_card_projected_pairs(db, items, EVENTS)
        await _attach_pregame_projections(db, items, EVENTS)

    asyncio.run(_both())
    assert len(db.projection_reads) == 1 and db.projection_reads[0]["ids"] == [FINAL]
    _assert_one_pair_per_card([i["data"] for i in items if i["type"] == "event"])
    # A futures item sharing an id is not a game card and gains nothing.
    assert "pregame_projection" not in items[-1]["data"]


def test_feed_chooses_by_the_status_the_card_prints():
    from app.routes.feed import _attach_pregame_projections

    # Stored completed, printed live: not asked. The reverse: asked.
    items = [{"type": "event", "data": _card(FINAL, "live")}]
    db = _DB()
    asyncio.run(_attach_pregame_projections(db, items, [_event(FINAL, "completed")]))
    assert db.projection_reads == []
    assert "pregame_projection" not in items[0]["data"]


def test_score_events_attaches_the_projection_after_the_current_pair():
    from app.routes import feed

    src = "".join(inspect.getsource(feed._score_events).split())
    budget = "remaining_s=projection_budget_s()ifprojection_budget_selseNone,)"
    current = src.index("await_attach_card_projected_pairs(db,scored_items,events," + budget)
    pregame = src.index("await_attach_pregame_projections(db,scored_items,events," + budget)
    # Each call reads the budget when IT runs, so the second sees what the first left.
    assert current < pregame
    assert src.endswith("returnscored_items")


def _projection_bound(db):
    """The SET LOCAL issued for the projection read, or None if it was not read."""
    for i, stmt in enumerate(db.statements):
        if "WITH RECURSIVE bounds" in stmt:
            before = db.statements[i - 1] if i else ""
            return before if before.startswith("SET LOCAL") else "unbounded"
    return None


def test_feed_projection_read_is_bounded_inside_what_is_left():
    """#11295's C1 applied to D2: the feed's read never spends the events deadline."""
    from app.routes.feed import _attach_pregame_projections

    def _run(remaining_s):
        item = {"type": "event", "data": _card(FINAL, "completed")}
        db = _DB()
        asyncio.run(
            _attach_pregame_projections(
                db, [item], [_event(FINAL, "completed")], remaining_s=remaining_s
            )
        )
        return db, item["data"]

    # 1.2 s left: 1200 − 500 margin = 700 ms, issued before the read.
    db, card = _run(1.2)
    assert _projection_bound(db) == "SET LOCAL statement_timeout = '700ms'"
    assert card["pregame_projection"]["projected_home_score"] == 25.4
    # No request budget (admin/trace callers): the 1500 ms cap, never unbounded.
    db, card = _run(None)
    assert _projection_bound(db) == "SET LOCAL statement_timeout = '1500ms'"
    assert card["pregame_projection"]["projected_away_score"] == 22.4
    # Under the margin + floor: no round trip; the key is withheld, the card kept.
    db, card = _run(0.3)
    assert db.statements == [] and _projection_bound(db) is None
    assert "pregame_projection" not in card
    assert card["pregame_projection_unavailable"] == "read_failed"
    assert card["current_odds"] == {"home_probability": 0.6, "away_probability": 0.4}


# ── /api/leagues/{sport} ─────────────────────────────────────────────────────


def test_league_rails_carry_at_most_one_pair_and_the_final_its_pregame_projection():
    from app.routes.league_futures import (
        _attach_card_projected_pairs,
        _attach_pregame_projections,
    )

    cards = _cards()
    upcoming = [c for c in cards if c["status"] == "scheduled"]
    results = [c for c in cards if c["status"] == "completed"]
    db = _DB()

    async def _both():
        await _attach_card_projected_pairs(db, EVENTS, upcoming)
        await _attach_pregame_projections(db, EVENTS, results)

    asyncio.run(_both())
    assert len(db.projection_reads) == 1
    _assert_one_pair_per_card(cards)


def test_league_route_attaches_to_the_capped_results_rail_after_the_current_pair():
    from app.routes import league_futures

    src = inspect.getsource(league_futures.build_league)
    cap = src.index("recent_results = _rrows[:RESULTS_LIMIT]")
    current = src.index("_attach_card_projected_pairs(db, _g_events, upcoming_games)")
    pregame = src.index("_attach_pregame_projections(db, _r_events, recent_results)")
    assert cap < current < pregame


def test_the_feed_and_league_objects_equal_the_event_pages():
    """One helper, one object: the list cards carry exactly what detail serves."""
    from app.routes.feed import _attach_pregame_projections as feed_attach
    from app.routes.league_futures import _attach_pregame_projections as league_attach
    from app.utils.pregame_projection import PROJECTION_KEY, read_pregame_projections

    page = asyncio.run(
        read_pregame_projections(_DB(), [_event(FINAL, "completed")],
                                 lambda e: "americanfootball_nfl")
    )[FINAL][PROJECTION_KEY]
    item = {"type": "event", "data": _card(FINAL, "completed")}
    brief = _card(FINAL, "completed")
    asyncio.run(feed_attach(_DB(), [item], [_event(FINAL, "completed")]))
    asyncio.run(league_attach(_DB(), [_event(FINAL, "completed")], [brief]))
    assert item["data"]["pregame_projection"] == page == brief["pregame_projection"]
