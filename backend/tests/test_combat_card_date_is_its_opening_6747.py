"""#6747 — a fight card is dated by the night it opens, not by its main event.

═══ THE DEFECT ═══

2026-09-26 20:22Z, 48 minutes before its first bout: "Fight Night: Rosas Jr vs
Barcelos" (`event:ufc:26sep26`) read **UPCOMING · STARTS IN 1 DAY · Sep 27** on
its page and "Tomorrow" on Discover. Its first priced bout (Jauregui vs
Demopoulos, 15314294) was 21:10Z Saturday; the main event walks 05:40Z Sunday.
UFC 331 (first bout 23:45Z Sat Sep 19, main event 07:20Z Sun Sep 20) read
"Sun, Sep 20" on /hub/mma for the same reason: every serve path dated the card
by ``latest``.

═══ THE RULE ═══

The card's date and countdown are the OPENING of its LIVE window — the same
pair `card_status_from_bouts` decides the pill on (#4505, #5603, #8881). The
sort key (`latest_commence`) and the headline fight stay on the main event, so
rail order does not move.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.routes.feed import _concept_headline
from app.utils.event_combat import (
    CombatEventAdapter,
    card_opens_at,
    card_status_from_bouts,
    list_card_concepts,
)
from app.utils.event_ufc import UFC_CONFIG
from tests.test_combat_card_cross_promotion_live_8881 import (
    UFC_IDS,
    _at,
    _bouts,
    _concept_rows,
    _freeze,
    _markets,
    _the_card,
)
from tests.test_combat_card_live_span_5603 import _FakeBout, _MockDB

READ_AT = _at(20, minute=22)  # the read that filed the fresh specimen
FIRST_PRICED = _at(21, minute=10)
MAIN_EVENT = _at(2, day=27, minute=15)


class TestTheOpening:
    def test_the_anchored_card_opens_at_its_first_priced_bout(self):
        assert card_opens_at(_bouts(), anchored_ids=UFC_IDS) == FIRST_PRICED

    def test_the_opening_is_the_instant_the_pill_lights(self):
        """One clock: a minute before the opening is upcoming, the opening is live."""
        opens = card_opens_at(_bouts(), anchored_ids=UFC_IDS)
        assert card_status_from_bouts(_bouts(), opens, anchored_ids=UFC_IDS) == "live"
        before = opens.replace(minute=opens.minute - 1)
        assert (
            card_status_from_bouts(_bouts(), before, anchored_ids=UFC_IDS)
            == "upcoming"
        )

    def test_no_anchor_opens_with_the_date_span_like_the_pill(self):
        assert card_opens_at(_bouts()) == _at(16)

    def test_a_called_off_first_bout_does_not_date_the_card(self):
        bouts = _bouts()
        for b in bouts:
            if b.id == 15314294:
                b.status = "cancelled"
        assert card_opens_at(bouts, anchored_ids=UFC_IDS) == _at(22)

    def test_no_rows_falls_back_to_the_callers_first(self):
        assert (
            card_opens_at([], fallback_first=_at(23), fallback_last=MAIN_EVENT)
            == _at(23)
        )

    def test_no_first_falls_back_to_the_last(self):
        assert card_opens_at([], fallback_last=MAIN_EVENT) == MAIN_EVENT

    def test_a_first_after_the_last_is_bad_data_not_an_opening(self):
        assert (
            card_opens_at([], fallback_first=MAIN_EVENT, fallback_last=_at(23))
            == _at(23)
        )

    def test_ufc_331_is_a_saturday_card(self):
        """The issue's first specimen: a main event past UTC midnight."""
        bouts = [
            _FakeBout(1, "A", "B", datetime(2026, 9, 19, 23, 45, tzinfo=timezone.utc)),
            _FakeBout(2, "Van", "Pantoja", datetime(2026, 9, 20, 7, 20, tzinfo=timezone.utc)),
        ]
        assert card_opens_at(bouts).date().isoformat() == "2026-09-19"


class TestEveryServePath:
    @pytest.mark.asyncio
    async def test_the_lister_dates_the_card_by_its_opening(self, monkeypatch):
        markets = _markets()
        rows = _concept_rows(markets)
        db = _MockDB(rows, event_rows=_bouts(), market_rows=markets)
        _freeze(monkeypatch, READ_AT)
        card = _the_card(await list_card_concepts(UFC_CONFIG, db, rows=rows))
        assert card["start_date"] == FIRST_PRICED.isoformat()
        assert card["opens_at"] == FIRST_PRICED

    @pytest.mark.asyncio
    async def test_the_lister_keeps_its_sort_key_on_the_main_event(self, monkeypatch):
        """Rail order is ranking; this change does not touch it."""
        markets = _markets()
        rows = _concept_rows(markets)
        db = _MockDB(rows, event_rows=_bouts(), market_rows=markets)
        _freeze(monkeypatch, READ_AT)
        card = _the_card(await list_card_concepts(UFC_CONFIG, db, rows=rows))
        # The fixture's 02:15Z bout dates into the next token on this path, so
        # the card's last bout here is 22:00Z — still the LAST, never the opening.
        assert card["latest_commence"] == _at(22)
        assert card["opens_at"] < card["latest_commence"]

    @pytest.mark.asyncio
    async def test_the_kalshi_backed_page_dates_the_card_by_its_opening(
        self, monkeypatch
    ):
        db = _MockDB([], event_rows=_bouts(), market_rows=_markets())
        _freeze(monkeypatch, READ_AT)
        env = await CombatEventAdapter(UFC_CONFIG).build_event("26sep26", db)
        assert env["primary"]["evolution_market_id"] is not None  # Kalshi branch
        assert env["event"]["start_date"] == FIRST_PRICED.isoformat()

    @pytest.mark.asyncio
    async def test_the_events_only_page_dates_the_card_by_its_opening(
        self, monkeypatch
    ):
        """No venue market ⇒ no anchors ⇒ the date-token opening, like its pill."""
        db = _MockDB([], event_rows=_bouts(), market_rows=[])
        _freeze(monkeypatch, READ_AT)
        env = await CombatEventAdapter(UFC_CONFIG).build_event("26sep26", db)
        assert env["event"]["start_date"] == _at(16).isoformat()
        assert env["event"]["status"] == "live"


class TestTheDiscoverHeadline:
    def test_the_card_reads_today_on_the_day_it_opens(self):
        c = {"status": "upcoming", "opens_at": FIRST_PRICED, "latest_commence": MAIN_EVENT}
        assert _concept_headline(c, READ_AT) == "Today"

    def test_and_it_really_did_read_tomorrow_before(self):
        """The strawman: the main event alone is what the headline read."""
        c = {"status": "upcoming", "latest_commence": MAIN_EVENT}
        assert _concept_headline(c, READ_AT) == "Tomorrow"
