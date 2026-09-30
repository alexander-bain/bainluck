"""#5811 — a feed game card the venue already graded stops saying "No result reported".

## What a reader saw, production 2026-09-30 ~04:05Z, `/sports` at 390px

**Live & Paused** listed *Luca Borando / Ian Escuza* reading
`No result reported · Sep 29`, four hours after the bout. One tap later
`/events/15320966` read `Settled · Ian Escuza wins` — its own Kalshi
`KXUFCFIGHT-26SEP29ESCBOR` leg graded Escuza `is_winner=true`
(`api_settlement`). `/api/feed?mode=sports` served the row `status: suspended`
with the `venue_settled` / `venue_settled_result` keys ABSENT: every other door
onto the shared card attaches them (#6381 detail, #6739 rails, #7092 list and
search, #9550 dropdown); the feed did not.

## What this file guards (producer half; the section and the card are ux's)

1. The feed card carries the SAME sentence the detail route serves, from the
   same shared reader and gate.
2. The gate reads the ROW, not the card — a card that looks scoreless over a
   row holding a score is refused.
3. The ordinary page pays nothing: no askable card, no query.
4. A failed read is a MISSING KEY, never a present `False`.
5. `get_feed` calls it over the page base, before the Redis write.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.models import Base, Event, FuturesMarket, FuturesOutcome, Sport  # noqa: E402
from app.routes import feed as feed_route  # noqa: E402
from app.routes.feed import (  # noqa: E402
    _attach_feed_venue_settlement,
    _feed_item_may_be_askable,
)

S_MMA = 29
SPORT_KEY = "mma_mixed_martial_arts"

#: The production rows (`/api/events/15320966`, 2026-09-30 04:0xZ).
ESCUZA = 15320966  # graded: Escuza is_winner=true, api_settlement
VISCONDE = 15320964  # every leg resolved with is_winner null — the control

SOURCES = {"betting_book_count": 2}


def _ago(hours):
    """Offset from the clock, never a literal stamp (gotcha #44)."""
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _event(event_id, *, status="suspended", scores=(None, None), when=None, home="Ian Escuza", away="Luca Borando"):
    return Event(
        id=event_id,
        sport_id=S_MMA,
        home_team_name=home,
        away_team_name=away,
        commence_time=when or _ago(4),
        status=status,
        home_score=scores[0],
        away_score=scores[1],
        win_probability_sources=SOURCES,
        event_tags=["provenance:unanchored"],
    )


def _fight(market_id, event_id, *, winner="Ian Escuza", source="api_settlement"):
    return (
        FuturesMarket(
            id=market_id,
            event_id=event_id,
            source="kalshi",
            external_id="KXUFCFIGHT-26SEP29ESCBOR",
            sport_id=S_MMA,
            name="Ian Escuza vs Luca Borando",
            status="resolved",
        ),
        FuturesOutcome(
            id=market_id,
            market_id=market_id,
            external_id=f"{market_id}-win",
            name=winner,
            is_winner=True,
            resolution_source=source,
        ),
    )


def _engine(*rows):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_MMA, key=SPORT_KEY, name="MMA", group="Combat"))
        for r in rows:
            s.add(r)
        s.commit()
    return eng


class _Session:
    """A real engine behind the async surface the helper calls; counts reads."""

    def __init__(self, session):
        self._s = session
        self.statements = 0

    async def execute(self, statement, *args, **kwargs):
        self.statements += 1
        return self._s.execute(statement, *args)


def _card(event_id, *, status="suspended", scores=(None, None), when=None):
    """A feed event item, in the shape `/api/feed` serves (`type` + `data`)."""
    return {
        "type": "event",
        "data": {
            "id": event_id,
            "status": status,
            "home_score": scores[0],
            "away_score": scores[1],
            "commence_time": (when or _ago(4)).isoformat(),
            "home_team": "Ian Escuza",
            "away_team": "Luca Borando",
        },
    }


def _run(items, *rows):
    eng = _engine(*rows)
    with Session(eng) as s:
        db = _Session(s)
        asyncio.run(_attach_feed_venue_settlement(db, items, datetime.now(timezone.utc)))
    return db


class TestTheFeedCardNamesTheWinner:
    def test_the_photographed_card_carries_the_detail_routes_sentence(self):
        market, outcome = _fight(1, ESCUZA)
        items = [_card(ESCUZA)]
        _run(items, _event(ESCUZA), market, outcome)

        assert items[0]["data"]["venue_settled"] is True
        assert items[0]["data"]["venue_settled_result"] == "Ian Escuza wins"

    def test_without_the_grade_the_card_says_no_venue_result(self):
        """The control: same row, grade removed — no sentence."""
        items = [_card(ESCUZA)]
        _run(items, _event(ESCUZA))

        assert items[0]["data"]["venue_settled"] is False
        assert items[0]["data"]["venue_settled_result"] is None

    def test_a_grade_from_a_weaker_source_is_not_the_venues_word(self):
        market, outcome = _fight(1, ESCUZA, source="game_score")
        items = [_card(ESCUZA)]
        _run(items, _event(ESCUZA), market, outcome)

        assert items[0]["data"]["venue_settled_result"] is None

    def test_cards_are_matched_to_their_rows_by_id(self):
        """The graded bout keeps its own result; the void neighbour gains none."""
        market, outcome = _fight(1, ESCUZA)
        items = [
            _card(VISCONDE),
            _card(ESCUZA),
        ]
        _run(
            items,
            _event(VISCONDE, home="Ilias Bulaid", away="Erick Visconde"),
            _event(ESCUZA),
            market,
            outcome,
        )

        assert items[1]["data"]["venue_settled_result"] == "Ian Escuza wins"
        assert items[0]["data"]["venue_settled_result"] is None

    def test_a_scheduled_row_long_past_its_start_is_asked_too(self):
        """started-without-result is the gate's second arm (#6381)."""
        market, outcome = _fight(1, ESCUZA)
        when = _ago(6)
        items = [_card(ESCUZA, status="scheduled", when=when)]
        _run(items, _event(ESCUZA, status="scheduled", when=when), market, outcome)

        assert items[0]["data"]["venue_settled_result"] == "Ian Escuza wins"


class TestTheGateReadsTheRow:
    def test_a_scoreless_card_over_a_scored_row_is_refused(self):
        market, outcome = _fight(1, ESCUZA)
        items = [_card(ESCUZA)]
        _run(items, _event(ESCUZA, scores=(1, 0)), market, outcome)

        assert "venue_settled" not in items[0]["data"]

    def test_a_live_card_is_never_asked(self):
        market, outcome = _fight(1, ESCUZA)
        items = [_card(ESCUZA, status="live")]
        db = _run(items, _event(ESCUZA, status="live"), market, outcome)

        assert "venue_settled" not in items[0]["data"]
        assert db.statements == 0


class TestTheOrdinaryPagePaysNothing:
    def test_no_askable_card_issues_no_query(self):
        items = [
            _card(1, status="live"),
            _card(2, status="completed", scores=(3, 1)),
            _card(3, status="scheduled", when=datetime.now(timezone.utc) + timedelta(hours=3)),
            {"type": "futures", "data": {"id": 4, "status": "suspended"}},
        ]
        db = _run(items)

        assert db.statements == 0
        assert all("venue_settled" not in i["data"] for i in items)

    def test_the_prefilter_is_a_superset_of_the_gate(self):
        now = datetime.now(timezone.utc)
        assert _feed_item_may_be_askable({"status": "suspended"}, now)
        assert _feed_item_may_be_askable(
            {"status": "scheduled", "commence_time": (now - timedelta(hours=3)).isoformat()}, now
        )
        assert _feed_item_may_be_askable({"status": "scheduled", "commence_time": "garbage"}, now)
        assert not _feed_item_may_be_askable(
            {"status": "scheduled", "commence_time": (now + timedelta(hours=1)).isoformat()}, now
        )
        assert not _feed_item_may_be_askable({"status": "suspended", "home_score": 0}, now)
        assert not _feed_item_may_be_askable({"status": "live"}, now)


class TestAFailedReadIsAMissingKey:
    def test_a_raising_read_leaves_every_card_untouched(self):
        items = [_card(ESCUZA)]
        db = AsyncMock()
        db.execute.side_effect = RuntimeError("db down")
        asyncio.run(_attach_feed_venue_settlement(db, items, datetime.now(timezone.utc)))

        assert "venue_settled" not in items[0]["data"]
        assert "venue_settled_result" not in items[0]["data"]


class TestGetFeedCallsItAtThePublishBoundary:
    def test_called_over_the_page_base_before_the_redis_write(self):
        src = inspect.getsource(feed_route.get_feed)
        call = src.find("await _attach_feed_venue_settlement(db, feed_items, now)")
        assert call != -1
        scrub = src.find("# Remove internal sort/debug keys.")
        payload = src.find('"items": paginated,')
        assert -1 < call < scrub < payload
