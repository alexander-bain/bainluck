"""#5811 — a fight the venue closed with NO winner stops looking like a fight in progress.

## What a reader saw, production 2026-09-30 09:39Z, `/sports` at 390px

**Live & Paused**, one card: `MMA · No result reported · Sep 29 · Erick
Visconde / Ilias Bulaid` (``15320964``, ``suspended``). The fight was over:
Kalshi finalised ``KXUFCFIGHT-26SEP29BULVIS-VIS`` / ``-BUL`` both
``result: "scalar"`` — closed, no winner. All six attached Kalshi markets were
``resolved``, every outcome ``is_winner`` NULL, and every market already
carried #7035's ``market_metadata.venue_voided = true`` (read 09:53Z). So
``venue_settled`` was correctly ``false`` and the card got the same input as a
bout still running.

## What this file guards (producer half; "Ended · no winner" is ux's card)

1. The rule: EVERY market voided, nothing graded — and each refusal as a
   counter-example.
2. Every door that serves the pair serves the new key from the same rule: the
   feed, the shared list reader (rails, ``/api/events``, search), the dropdown,
   and the detail payload.
3. The pair (``venue_settled`` / ``venue_settled_result``) is byte-identical —
   the key is an addition, present only when ``True``.
4. A failed void read is a MISSING key, never a claim.
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
from app.routes.events import (  # noqa: E402
    _typeahead_attach_venue_settlement,
    _venue_settlement_served,
)
from app.routes.feed import _attach_feed_venue_settlement  # noqa: E402
from app.utils.venue_settlement import (  # noqa: E402
    VENUE_CLOSED_NO_WINNER_KEY,
    venue_closed_without_winner,
)
from app.utils.venue_settlement_reader import venue_settlements_for_events  # noqa: E402

S_MMA = 29
VISCONDE = 15320964  # the specimen: six Kalshi markets, all venue_voided, none graded
ESCUZA = 15320966  # the sibling bout: graded Escuza, the pair's own case
KEY = VENUE_CLOSED_NO_WINNER_KEY
VOIDED = {"venue_voided": True, "venue_voided_at": "2026-09-30T06:12:00+00:00"}


def _ago(hours):
    """Offset from the clock, never a literal stamp (gotcha #44)."""
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _event(event_id, *, home="Ilias Bulaid", away="Erick Visconde", scores=(None, None)):
    return Event(
        id=event_id,
        sport_id=S_MMA,
        home_team_name=home,
        away_team_name=away,
        commence_time=_ago(12),
        status="suspended",
        home_score=scores[0],
        away_score=scores[1],
        win_probability_sources={"betting_book_count": 2},
        event_tags=["provenance:unanchored"],
    )


def _market(market_id, event_id, *, metadata=VOIDED, winner=None, source=None):
    """One Kalshi market with two legs; ``winner`` names the leg graded TRUE."""
    rows = [
        FuturesMarket(
            id=market_id,
            event_id=event_id,
            source="kalshi",
            external_id=f"KXUFCFIGHT-26SEP29BULVIS-{market_id}",
            sport_id=S_MMA,
            name="Ilias Bulaid vs Erick Visconde",
            status="resolved",
            market_metadata=dict(metadata) if metadata is not None else None,
        )
    ]
    for n, name in enumerate(("Ilias Bulaid", "Erick Visconde")):
        rows.append(
            FuturesOutcome(
                id=market_id * 10 + n,
                market_id=market_id,
                external_id=f"{market_id}-{n}",
                name=name,
                is_winner=True if winner == name else None,
                resolution_source=source if winner == name else None,
            )
        )
    return rows


def _six_voided(event_id=VISCONDE, **override_first):
    """The specimen's six markets; ``override_first`` changes market 1 only."""
    rows = []
    for i in range(1, 7):
        rows += _market(event_id * 10 + i, event_id, **(override_first if i == 1 else {}))
    return rows


def _engine(*rows):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_MMA, key="mma_mixed_martial_arts", name="MMA", group="Combat"))
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


def _feed_card(event_id):
    return {
        "type": "event",
        "data": {
            "id": event_id,
            "status": "suspended",
            "home_score": None,
            "away_score": None,
            "commence_time": _ago(12).isoformat(),
        },
    }


def _feed(event_ids, *rows, fail_void_read=False):
    items = [_feed_card(i) for i in event_ids]
    with Session(_engine(*rows)) as s:
        asyncio.run(
            _attach_feed_venue_settlement(
                _Session(s, fail_void_read=fail_void_read),
                items,
                datetime.now(timezone.utc),
            )
        )
    return [item["data"] for item in items]


# ── 1. the rule ──────────────────────────────────────────────────────────────


class TestTheRule:
    def test_every_market_voided_and_nothing_graded_is_closed_without_winner(self):
        assert venue_closed_without_winner([VOIDED] * 6, False) is True

    def test_no_markets_is_not_a_void(self):
        """``all([])`` is True — a legless event was never asked."""
        assert venue_closed_without_winner([], False) is False

    @pytest.mark.parametrize(
        "odd_one",
        [
            None,
            {},
            {"venue_void_checked_at": "2026-09-30T06:12:00+00:00"},
            {"venue_voided": "true"},
            {"venue_voided": 1},
            {"venue_voided": False},
        ],
        ids=["null-metadata", "unasked", "venue-named-a-result", "string", "one", "false"],
    )
    def test_one_market_that_is_not_a_boolean_void_refuses(self, odd_one):
        assert venue_closed_without_winner([VOIDED] * 5 + [odd_one], False) is False

    @pytest.mark.parametrize("winner", [True, None], ids=["graded", "unknown"])
    def test_a_winner_or_an_unanswered_winner_read_refuses(self, winner):
        assert venue_closed_without_winner([VOIDED] * 6, winner) is False


# ── 2. every door ────────────────────────────────────────────────────────────


class TestTheFeedCard:
    def test_the_photographed_card_says_the_venue_closed_it(self):
        (card,) = _feed([VISCONDE], _event(VISCONDE), *_six_voided())
        assert card[KEY] is True
        assert card["venue_settled"] is False
        assert card["venue_settled_result"] is None

    def test_one_market_the_capture_has_not_answered_withholds_it(self):
        (card,) = _feed([VISCONDE], _event(VISCONDE), *_six_voided(metadata={}))
        assert KEY not in card
        assert card["venue_settled"] is False

    def test_a_winner_from_any_source_contradicts_the_void(self):
        """``game_score`` is not the venue's grade, so the pair stays unsettled —
        and the void is STILL refused, because the arm reads any winner."""
        (card,) = _feed(
            [VISCONDE],
            _event(VISCONDE),
            *_six_voided(winner="Ilias Bulaid", source="game_score"),
        )
        assert card["venue_settled"] is False
        assert KEY not in card

    def test_a_graded_neighbour_keeps_its_pair_and_gains_no_void(self):
        escuza = _market(
            ESCUZA * 10 + 1, ESCUZA, metadata={}, winner="Ilias Bulaid", source="api_settlement"
        )
        visconde, graded = _feed(
            [VISCONDE, ESCUZA],
            _event(VISCONDE),
            _event(ESCUZA),
            *_six_voided(),
            *escuza,
        )
        assert visconde[KEY] is True
        assert graded == {
            **graded,
            "venue_settled": True,
            "venue_settled_result": "Ilias Bulaid wins",
        }
        assert KEY not in graded

    def test_a_failed_void_read_is_a_missing_key_not_a_claim(self):
        (card,) = _feed(
            [VISCONDE], _event(VISCONDE), *_six_voided(), fail_void_read=True
        )
        assert KEY not in card
        assert card["venue_settled"] is False  # the pair's own read still answered

    def test_a_row_holding_our_own_score_is_never_asked(self):
        (card,) = _feed([VISCONDE], _event(VISCONDE, scores=(1, 0)), *_six_voided())
        assert KEY not in card and "venue_settled" not in card


class TestTheSharedListReader:
    """Rails (#6739), ``/api/events`` and search (#7092) all go through it."""

    def _read(self, event, *rows):
        # Scalars read BEFORE the commit expires the ORM row (gotcha #6).
        ev = SimpleNamespace(
            id=event.id,
            home_team_name=event.home_team_name,
            away_team_name=event.away_team_name,
        )
        with Session(_engine(event, *rows)) as s:
            return asyncio.run(venue_settlements_for_events(_Session(s), [ev]))

    def test_the_void_reaches_every_list_door(self):
        out = self._read(_event(VISCONDE), *_six_voided())
        assert out == {
            VISCONDE: {"venue_settled": False, "venue_settled_result": None, KEY: True}
        }

    def test_a_graded_event_is_byte_identical(self):
        out = self._read(
            _event(ESCUZA),
            *_market(1, ESCUZA, winner="Ilias Bulaid", source="api_settlement"),
        )
        assert out == {
            ESCUZA: {"venue_settled": True, "venue_settled_result": "Ilias Bulaid wins"}
        }


class TestTheDropdown:
    def test_the_dropdown_row_carries_the_void(self):
        now = datetime.now(timezone.utc)
        suggestions = [{"type": "event", "event_id": VISCONDE}]
        fact = SimpleNamespace(
            id=VISCONDE,
            status="suspended",
            commence_time=_ago(12),
            home_score=None,
            away_score=None,
            home_team_name="Ilias Bulaid",
            away_team_name="Erick Visconde",
            win_probability_sources={"betting_book_count": 2},
        )
        with Session(_engine(_event(VISCONDE), *_six_voided())) as s:
            asyncio.run(
                _typeahead_attach_venue_settlement(
                    _Session(s), suggestions, {VISCONDE: fact}, now
                )
            )
        assert suggestions[0][KEY] is True
        assert suggestions[0]["venue_settled"] is False


class TestTheDetailPayload:
    def _served(self, *rows, **session_kw):
        with Session(_engine(_event(VISCONDE), *rows)) as s:
            ev = SimpleNamespace(
                id=VISCONDE, home_team_name="Ilias Bulaid", away_team_name="Erick Visconde"
            )
            return asyncio.run(_venue_settlement_served(_Session(s, **session_kw), ev))

    def test_the_event_page_carries_the_void(self):
        assert self._served(*_six_voided()) == {
            "venue_settled": False,
            "venue_settled_result": None,
            KEY: True,
        }

    def test_without_the_void_the_page_is_what_it_was(self):
        assert self._served(*_six_voided(metadata={})) == {
            "venue_settled": False,
            "venue_settled_result": None,
        }

    def test_a_failed_void_read_leaves_the_pair_alone(self):
        assert self._served(*_six_voided(), fail_void_read=True) == {
            "venue_settled": False,
            "venue_settled_result": None,
        }
