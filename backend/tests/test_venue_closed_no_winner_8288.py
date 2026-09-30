"""#8288 — a tennis match the venue says was never completed stops looking unfinished.

## What a reader saw

``/events/15320659`` (Sherif v Kudermetova, WTA China Open, 2026-09-30): Sherif
withdrew before play. The hero read "No result reported", and set props and
games lines printed 50%, which is Polymarket's void payout, not a price (#9798).
The Polymarket copy of the match, ``15320785``, carried the venue's own verdict:
"China Open: Completed Match: Mayar Sherif vs Polina Kudermetova" graded **No**
(``clob_authoritative``). Nothing served it. 60+ such legs were graded No in the
three days to 2026-09-30, every attached row ``suspended`` with no score.

## What this file guards (producer half; ux renders the void on #9798)

1. The rule: the Completed Match **No** graded by a tier-3 source, and no winner
   anywhere else. Each refusal is a counter-example.
2. It is served under #5811's ``venue_closed_no_winner`` key through the same
   reader, so every door that serves the pair serves it.
3. The pair (``venue_settled`` / ``venue_settled_result``) is byte-identical. A
   void is never a result.
4. A failed read is a MISSING key, never a claim.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
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
from app.routes.events import _names_completed_match, _venue_settlement_served  # noqa: E402
from app.routes.feed import _attach_feed_venue_settlement  # noqa: E402
from app.utils.venue_settlement import (  # noqa: E402
    VENUE_CLOSED_NO_WINNER_KEY,
    names_completed_match,
    venue_declared_not_completed,
)
from app.utils.venue_settlement_reader import venue_settlements_for_events  # noqa: E402

S_TENNIS = 41
SHERIF = 15320785  # the specimen: PM copy of #9798's page, Completed Match graded No
HOME, AWAY = "Mayar Sherif", "Polina Kudermetova"
KEY = VENUE_CLOSED_NO_WINNER_KEY
CM_NAME = "China Open: Completed Match: Mayar Sherif vs Polina Kudermetova"
VOIDED = {"venue_voided": True, "venue_voided_at": "2026-09-30T06:12:00+00:00"}


def _ago(hours):
    """Offset from the clock, never a literal stamp (gotcha #44)."""
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _event(event_id=SHERIF, *, scores=(None, None)):
    return Event(
        id=event_id,
        sport_id=S_TENNIS,
        home_team_name=HOME,
        away_team_name=AWAY,
        commence_time=_ago(8),
        status="suspended",
        home_score=scores[0],
        away_score=scores[1],
        win_probability_sources={"betting_book_count": 0},
        event_tags=[],
    )


def _market(market_id, *, name, legs, winner=None, source=None,
            venue="polymarket", metadata=None, event_id=SHERIF):
    """One market; ``winner`` names the leg graded TRUE with ``source``."""
    rows = [
        FuturesMarket(
            id=market_id,
            event_id=event_id,
            source=venue,
            external_id=f"0x{market_id:x}",
            sport_id=S_TENNIS,
            name=name,
            status="resolved",
            market_metadata=dict(metadata) if metadata is not None else None,
        )
    ]
    for n, leg in enumerate(legs):
        rows.append(
            FuturesOutcome(
                id=market_id * 10 + n,
                market_id=market_id,
                external_id=f"0x{market_id:x}_{leg.lower()}",
                name=leg,
                is_winner=True if winner == leg else None,
                resolution_source=source if winner == leg else None,
            )
        )
    return rows


def _completed_match(market_id=1, *, winner="No", source="clob_authoritative", name=CM_NAME, **kw):
    return _market(market_id, name=name, legs=("Yes", "No"), winner=winner, source=source, **kw)


def _void_siblings(**set1_override):
    """The match winner and two props, all paid 0.5/0.5, so none graded."""
    return [
        *_market(2, name=f"China Open: {HOME} vs {AWAY}", legs=(HOME, AWAY)),
        *_market(3, name=f"Set 1 Winner: {HOME} vs {AWAY}", legs=(HOME, AWAY), **set1_override),
        *_market(4, name="Sherif vs. Kudermetova: Match O/U 21.5", legs=("Over", "Under")),
    ]


def _engine(*rows):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_TENNIS, key="tennis_wta", name="WTA", group="Tennis"))
        for r in rows:
            s.add(r)
        s.commit()
    return eng


class _Session:
    """A real engine behind the async surface; optionally refuses the void read."""

    def __init__(self, session, *, fail_void_read=False):
        self._s = session
        self._fail = fail_void_read

    async def execute(self, statement, *args, **kwargs):
        if self._fail and "market_metadata" in str(statement):
            raise RuntimeError("void read refused")
        return self._s.execute(statement, *args)


def _read(*rows, event=None):
    event = event if event is not None else _event()
    # Scalars read BEFORE the commit expires the ORM row (gotcha #6).
    ev = SimpleNamespace(id=event.id, home_team_name=HOME, away_team_name=AWAY)
    with Session(_engine(event, *rows)) as s:
        return asyncio.run(venue_settlements_for_events(_Session(s), [ev]))[ev.id]


UNSETTLED = {"venue_settled": False, "venue_settled_result": None}


# ── 1. the rule ──────────────────────────────────────────────────────────────


class TestTheRule:
    def test_the_venue_graded_no_and_nothing_else_won(self):
        assert venue_declared_not_completed([(True, False)], False) is True

    def test_no_completed_match_market_said_nothing(self):
        assert venue_declared_not_completed([], False) is False

    def test_a_no_the_venue_did_not_grade_is_not_the_verdict(self):
        assert venue_declared_not_completed([(False, False)], False) is False

    def test_a_yes_winner_contradicts_it(self):
        assert venue_declared_not_completed([(True, True)], False) is False

    def test_a_second_copy_saying_yes_contradicts_it(self):
        assert venue_declared_not_completed([(True, False), (False, True)], False) is False

    def test_one_copy_graded_no_and_one_not_yet_graded_is_the_verdict(self):
        assert venue_declared_not_completed([(True, False), (False, False)], False) is True

    @pytest.mark.parametrize("other", [True, None], ids=["winner", "unanswered"])
    def test_another_markets_winner_or_an_unanswered_read_refuses(self, other):
        assert venue_declared_not_completed([(True, False)], other) is False

    def test_the_name_test_is_one_definition(self):
        """The #8874 fold and this arm cannot disagree about which market it is."""
        assert _names_completed_match is names_completed_match
        assert names_completed_match(CM_NAME)
        assert not names_completed_match("Completed Matches Tonight: A vs B")


# ── 2. the shared reader: every door's source ────────────────────────────────


class TestTheSharedReader:
    """Feed, rails, ``/api/events``, search, the dropdown and the detail payload
    all take the key from ``mark_venue_closed_no_winner`` over this reader."""

    @pytest.mark.parametrize("source", ["clob_authoritative", "api_settlement"])
    def test_the_specimen_carries_the_void_and_the_pair_is_untouched(self, source):
        out = _read(*_completed_match(source=source), *_void_siblings())
        assert out == {**UNSETTLED, KEY: True}

    @pytest.mark.parametrize("source", ["pass2_guess", "clean_resolution", None])
    def test_a_no_the_venue_did_not_grade_withholds_it(self, source):
        assert _read(*_completed_match(source=source), *_void_siblings()) == UNSETTLED

    def test_played_says_nothing(self):
        assert _read(*_completed_match(winner="Yes", source="api_settlement"), *_void_siblings()) == UNSETTLED

    @pytest.mark.parametrize("source", ["api_settlement", "game_score", "pass2_guess"])
    def test_a_winner_on_any_other_market_from_any_source_refuses(self, source):
        out = _read(*_completed_match(), *_void_siblings(winner=HOME, source=source))
        assert KEY not in out

    def test_without_a_completed_match_market_nothing_is_said(self):
        assert _read(*_void_siblings()) == UNSETTLED

    def test_a_kalshi_market_is_never_the_polymarket_verdict(self):
        """Its No winner is an ordinary winner, and it refuses."""
        out = _read(*_completed_match(venue="kalshi"), *_void_siblings())
        assert out == UNSETTLED

    def test_a_name_that_only_contains_the_words_is_not_the_verdict(self):
        out = _read(
            *_completed_match(name="Completed Matches Tonight: Sherif vs Kudermetova"),
            *_void_siblings(),
        )
        assert out == UNSETTLED

    def test_the_verdict_beside_kalshi_voids_carries_it(self):
        """#9798's page holds both: Kalshi's voided markets and Polymarket's.
        #5811's arm refuses the mix (the No is a winner, the PM market carries
        no void stamp); this arm is what serves it."""
        kalshi = [
            row
            for i in range(3)
            for row in _market(10 + i, name=f"{HOME} vs {AWAY}", legs=(HOME, AWAY),
                               venue="kalshi", metadata=VOIDED)
        ]
        out = _read(*kalshi, *_completed_match(), *_void_siblings())
        assert out == {**UNSETTLED, KEY: True}

    def test_a_graded_match_is_byte_identical(self):
        out = _read(
            *_completed_match(winner="Yes", source="api_settlement"),
            *_market(2, name=f"China Open: {HOME} vs {AWAY}", legs=(HOME, AWAY),
                     winner=HOME, source="api_settlement"),
        )
        assert out == {"venue_settled": True, "venue_settled_result": f"{HOME} wins"}

    def test_a_row_holding_our_own_score_is_never_asked(self):
        items = [{"type": "event", "data": {
            "id": SHERIF, "status": "suspended", "home_score": 2, "away_score": 0,
            "commence_time": _ago(8).isoformat(),
        }}]
        with Session(_engine(_event(scores=(2, 0)), *_completed_match(), *_void_siblings())) as s:
            asyncio.run(_attach_feed_venue_settlement(_Session(s), items, datetime.now(timezone.utc)))
        assert KEY not in items[0]["data"]


# ── 3. doors ─────────────────────────────────────────────────────────────────


class TestTheDoors:
    def _feed(self, *rows, fail_void_read=False):
        items = [{"type": "event", "data": {
            "id": SHERIF, "status": "suspended", "home_score": None, "away_score": None,
            "commence_time": _ago(8).isoformat(),
        }}]
        with Session(_engine(_event(), *rows)) as s:
            asyncio.run(_attach_feed_venue_settlement(
                _Session(s, fail_void_read=fail_void_read), items, datetime.now(timezone.utc)
            ))
        return items[0]["data"]

    def _served(self, *rows, **session_kw):
        with Session(_engine(_event(), *rows)) as s:
            ev = SimpleNamespace(id=SHERIF, home_team_name=HOME, away_team_name=AWAY)
            return asyncio.run(_venue_settlement_served(_Session(s, **session_kw), ev))

    def test_the_feed_card_carries_it(self):
        card = self._feed(*_completed_match(), *_void_siblings())
        assert card[KEY] is True
        assert card["venue_settled"] is False and card["venue_settled_result"] is None

    def test_the_event_page_carries_it(self):
        assert self._served(*_completed_match(), *_void_siblings()) == {**UNSETTLED, KEY: True}

    def test_a_failed_void_read_is_a_missing_key_not_a_claim(self):
        card = self._feed(*_completed_match(), *_void_siblings(), fail_void_read=True)
        assert KEY not in card
        assert self._served(*_completed_match(), *_void_siblings(), fail_void_read=True) == UNSETTLED
