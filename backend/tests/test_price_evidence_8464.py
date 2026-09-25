"""#8464 / CERT-3408 — a verified question is not a tradeable price.

`/events/15316415` (Cubs @ Red Sox, 2026-09-25) served one source, Polymarket
0.500 `verified`, over a 0.49/0.51 book, and the page read "No price yet". The
first repair trusted `verified` alone; CERT-3408 blocked it with two production
counterexamples — verified 0.500s over books nobody trades inside:

    15314872  0.06/0.95 + 0.05/0.94
    15316031  0.09/0.90 + 0.10/0.91

`price_evidence` is the server's answer to the PRICE question, read from the
stored `futures_outcomes` book written with the reading. Every row below is the
production value read 2026-09-25 00:40Z (db-query), not a hand-built shape.

Both directions (gotcha #43): the specimen proves `tradeable_book`; both wide
books, a stale book, a book that does not bracket the reading, a composite with
one wide leg and an entry naming no market all read `unproven`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.models import Event, Sport
from app.utils.price_evidence import (
    TRADEABLE_BOOK,
    UNPROVEN,
    classify_price_evidence,
    load_price_evidence,
)
from tests.test_series_fold_3810 import blend_fold_row, is_blend_fold, is_series_fold

RULE = "live_blend.admissible_as_blend_speaker@5031"


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _entry(updated_at: str, market_id: int, contributors=None, value=0.5):
    eligibility = {
        "v": 1,
        "rule": RULE,
        "scope": "full_event_winner",
        "status": "verified",
        "market_id": market_id,
        "source_market_id": "x",
    }
    if contributors:
        eligibility["contributors"] = [
            {"market_id": m, "source_market_id": "x"} for m in contributors
        ]
    return {"value": value, "updated_at": updated_at, "eligibility": eligibility}


def _row(market_id, bid, ask, at):
    return (market_id, Decimal(bid), Decimal(ask), _ts(at))


# ── the production specimens ──────────────────────────────────────────────────

CUBS_AT = "2026-09-24T20:28:18.947285+00:00"
CUBS_ENTRY = _entry(CUBS_AT, 61799932, contributors=[61799932, 62236432])
CUBS_BOOKS = [
    _row(61799932, "0.4900", "0.5100", CUBS_AT),
    _row(62236432, "0.4900", "0.5100", CUBS_AT),
    _row(62236432, "0.4900", "0.5100", CUBS_AT),
]

GALATASARAY_AT = "2026-09-22T08:39:06.291368+00:00"
GALATASARAY_ENTRY = _entry(GALATASARAY_AT, 61478582)
GALATASARAY_BOOKS = [
    _row(61478582, "0.0600", "0.9500", GALATASARAY_AT),
    _row(61478582, "0.0500", "0.9400", GALATASARAY_AT),
]

VECHTA_AT = "2026-09-24T03:40:21.275765+00:00"
VECHTA_ENTRY = _entry(VECHTA_AT, 61630175)
VECHTA_BOOKS = [
    _row(61630175, "0.1000", "0.9100", VECHTA_AT),
    _row(61630175, "0.0900", "0.9000", VECHTA_AT),
]

# A three-way soccer market: the draw's book does not bracket 0.5, the home
# side's does. 15313492 Finland v Belarus.
FINLAND_AT = "2026-09-24T21:44:23.252039+00:00"
FINLAND_ENTRY = _entry(FINLAND_AT, 61207264)
FINLAND_BOOKS = [
    _row(61207264, "0.2500", "0.3100", FINLAND_AT),
    _row(61207264, "0.4700", "0.5300", FINLAND_AT),
    _row(61207264, "0.1700", "0.2200", FINLAND_AT),
]


class TestClassifier:
    def test_the_cubs_red_sox_pickem_is_a_tradeable_book(self):
        assert classify_price_evidence(CUBS_ENTRY, CUBS_BOOKS) == TRADEABLE_BOOK

    def test_three_way_market_passes_on_the_outcome_that_brackets_it(self):
        assert classify_price_evidence(FINLAND_ENTRY, FINLAND_BOOKS) == TRADEABLE_BOOK

    def test_cert_3408_galatasaray_wide_book_is_unproven(self):
        assert classify_price_evidence(GALATASARAY_ENTRY, GALATASARAY_BOOKS) == UNPROVEN

    def test_cert_3408_vechta_wide_book_is_unproven(self):
        assert classify_price_evidence(VECHTA_ENTRY, VECHTA_BOOKS) == UNPROVEN

    def test_a_book_stored_in_a_different_write_is_not_the_readings_book(self):
        later = (_ts(CUBS_AT) + timedelta(minutes=2)).isoformat()
        books = [(m, b, a, _ts(later)) for m, b, a, _ in CUBS_BOOKS]
        assert classify_price_evidence(CUBS_ENTRY, books) == UNPROVEN

    def test_a_tight_book_that_does_not_bracket_the_reading_is_unproven(self):
        books = [_row(61478582, "0.3000", "0.3200", GALATASARAY_AT)]
        assert classify_price_evidence(GALATASARAY_ENTRY, books) == UNPROVEN

    def test_a_composite_is_only_as_good_as_its_widest_leg(self):
        books = [
            _row(61799932, "0.4900", "0.5100", CUBS_AT),
            _row(62236432, "0.0600", "0.9500", CUBS_AT),
        ]
        assert classify_price_evidence(CUBS_ENTRY, books) == UNPROVEN

    def test_a_cited_market_with_no_stored_book_is_unproven(self):
        books = [_row(61799932, "0.4900", "0.5100", CUBS_AT)]
        assert classify_price_evidence(CUBS_ENTRY, books) == UNPROVEN

    def test_a_one_sided_book_is_unproven(self):
        books = [(61478582, None, Decimal("0.5100"), _ts(GALATASARAY_AT))]
        assert classify_price_evidence(GALATASARAY_ENTRY, books) == UNPROVEN

    def test_an_entry_naming_no_market_is_unproven(self):
        assert classify_price_evidence({"value": 0.5, "updated_at": CUBS_AT}, CUBS_BOOKS) == UNPROVEN
        assert classify_price_evidence(0.5, CUBS_BOOKS) == UNPROVEN

    def test_an_entry_with_no_timestamp_is_unproven(self):
        entry = dict(CUBS_ENTRY)
        entry.pop("updated_at")
        assert classify_price_evidence(entry, CUBS_BOOKS) == UNPROVEN


# ── the loader asks for the cited markets and no others ───────────────────────


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


def _requested_market_ids(statement):
    for key, value in statement.compile().params.items():
        if key.startswith("market_id") and isinstance(value, (list, tuple, set)):
            return set(value)
    return None


class _BookSession:
    """Answers the outcome-book read, honouring its market-id filter."""

    def __init__(self, books):
        self.books = list(books)
        self.asked: list[set | None] = []

    async def execute(self, statement, *_a, **_kw):
        sql = " ".join(str(statement).split())
        if "FROM futures_outcomes" in sql:
            ids = _requested_market_ids(statement)
            self.asked.append(ids)
            return _Result([r for r in self.books if ids is not None and r[0] in ids])
        return _Result([])


class TestLoader:
    def test_reads_every_cited_market(self):
        session = _BookSession(CUBS_BOOKS + GALATASARAY_BOOKS)
        assert asyncio.run(load_price_evidence(session, CUBS_ENTRY)) == TRADEABLE_BOOK
        assert session.asked == [{61799932, 62236432}]

    def test_the_wide_book_loads_unproven(self):
        session = _BookSession(CUBS_BOOKS + GALATASARAY_BOOKS)
        assert asyncio.run(load_price_evidence(session, GALATASARAY_ENTRY)) == UNPROVEN

    def test_no_market_means_no_query(self):
        session = _BookSession(CUBS_BOOKS)
        assert asyncio.run(load_price_evidence(session, 0.5)) == UNPROVEN
        assert session.asked == []


# ── the real route stamps it on the served entry ──────────────────────────────

S_MLB = 90_008_464


class _RouteSession(_BookSession):
    def __init__(self, event, books):
        super().__init__(books)
        self.event = event

    async def execute(self, statement, *_a, **_kw):
        sql = " ".join(str(statement).split())
        if "FROM futures_outcomes" in sql:
            return await super().execute(statement)
        # Before "FROM events": the odds CTE selects from events too.
        if "odds_snapshots" in sql:
            return _Result([])
        if is_blend_fold(sql):
            return _Result([blend_fold_row(self.event)])
        if is_series_fold(sql):
            return _Result([])
        if "FROM events" in sql:
            return _Result([self.event])
        return _Result([])


@pytest.fixture()
def serve(monkeypatch):
    from app.routes import events as events_route

    async def _none(*_a, **_kw):
        return {}

    async def _no_drain(_db, _event_id):
        return None

    monkeypatch.setattr(events_route, "_load_gei_percentiles", _none)
    monkeypatch.setattr(events_route, "_build_team_lookup", _none)
    monkeypatch.setattr(events_route, "resolve_market_born_duplicate", _no_drain)

    def _serve(event_id, entry, books):
        event = Event(
            id=event_id,
            sport_id=S_MLB,
            home_team_name="Boston Red Sox",
            away_team_name="Chicago Cubs",
            commence_time=datetime(2026, 9, 25, 17, 5, tzinfo=timezone.utc),
            status="scheduled",
            win_probability_sources={"polymarket": entry},
        )
        event.sport = Sport(id=S_MLB, key="baseball_mlb", name="MLB")
        events_route._event_detail_cache.clear()
        payload = asyncio.run(
            events_route.get_event(event_id, db=_RouteSession(event, books))
        )
        events_route._event_detail_cache.clear()
        return payload["win_probability_sources"]["polymarket"]

    return _serve


class TestTheRealRoute:
    def test_the_specimen_is_served_tradeable_and_verified(self, serve):
        served = serve(15316415, CUBS_ENTRY, CUBS_BOOKS)
        assert served["value"] == 0.5
        assert served["evidence_status"] == "verified"
        assert served["price_evidence"] == TRADEABLE_BOOK

    def test_cert_3408_wide_books_are_served_unproven(self, serve):
        assert serve(15314872, GALATASARAY_ENTRY, GALATASARAY_BOOKS)["price_evidence"] == UNPROVEN
        assert serve(15316031, VECHTA_ENTRY, VECHTA_BOOKS)["price_evidence"] == UNPROVEN
