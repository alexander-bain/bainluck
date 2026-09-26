"""#8881 — a UFC card stops wearing the LIVE pill hours before its first bout
because other promotions fought earlier on the same date.

═══ THE DEFECT ═══

Discover, 2026-09-26 18:00Z: "Fight Night: Rosas Jr vs Barcelos"
(`event:ufc:26sep26`) wore the red ● LIVE pill; `/api/event/event:ufc:26sep26`
said `status: live` too. The first bout the venue lists on that card, Jauregui
vs Demopoulos (15314294, `KXUFCFIGHT-26SEP26DEMJAU`), was at 21:10Z.

Cause. `_list_event_bouts` groups every MMA row by DATE token, so the card also
held six bouts from other promotions stamped 16:00Z and `live` (Holloway vs
Jungwirth 15317028, Lemberanskij vs Paulus 15317030, ...). They are real fights
— #5603's called-off filter rightly keeps them — so `card_status_span` opened
the window at 16:00Z. None of them carries a market on the UFC card.

═══ THE RULE ═══

When the caller knows which bouts a venue prices ON THIS CARD, the window
OPENS at the earliest of those. The closing arm keeps the full span, so no card
settles earlier than before. Market STATUS is not consulted: on the specimen
Gall vs Dumas's fight market (15314290) was already `resolved` hours before the
main card, and a finished prelim must keep the card live (#5603's false
negative, the other direction).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_combat import (
    CombatEventAdapter,
    card_status_from_bouts,
    card_status_span,
    list_card_concepts,
)
from app.utils.event_ufc import UFC_CONFIG
from tests.test_combat_card_live_span_5603 import _FakeBout, _FakeMarket, _MockDB


def _at(hour, *, day=26, minute=0):
    return datetime(2026, 9, day, hour, minute, tzinfo=timezone.utc)


def _other_promotions():
    """Real fights, other promotions, same UTC date — live at the read."""
    return [
        _FakeBout(15317028, "Christian Jungwirth", "Max Holloway", _at(16), "live"),
        _FakeBout(15317030, "Roman Paulus", "Raul Lemberanskij", _at(16), "live"),
        _FakeBout(
            15318010, "Damien McKenna", "Miguel Haro", _at(17, minute=45), "live"
        ),
    ]


def _ufc_card():
    return [
        _FakeBout(
            15314294, "Vanessa Demopoulos", "Yazmin Jauregui", _at(21, minute=10)
        ),
        _FakeBout(15314291, "Montel Jackson", "Ricky Simon", _at(22)),
        _FakeBout(
            15314292, "Raul Rosas Jr", "Raoni Barcelos", _at(2, day=27, minute=15)
        ),
    ]


def _bouts():
    return sorted(
        _other_promotions() + _ufc_card(), key=lambda b: (b.commence_time, b.id)
    )


def _markets(prefix="KXUFCFIGHT"):
    out = []
    for i, (ev_id, suffix, name, fighters, when) in enumerate(
        [
            (
                15314294,
                "DEMJAU",
                "Demopoulos vs Jauregui",
                ("Vanessa Demopoulos", "Yazmin Jauregui"),
                _at(21, minute=10),
            ),
            (
                15314291,
                "JACSIM",
                "Jackson vs Simon",
                ("Montel Jackson", "Ricky Simon"),
                _at(22),
            ),
            (
                15314292,
                "ROSBAR",
                "Rosas Jr vs Barcelos",
                ("Raul Rosas Jr", "Raoni Barcelos"),
                _at(2, day=27, minute=15),
            ),
        ]
    ):
        m = _FakeMarket(900 + i, f"{prefix}-26SEP26{suffix}", name, when, fighters)
        m.event_id = ev_id
        out.append(m)
    return out


UFC_IDS = {b.id for b in _ufc_card()}
READ_AT = _at(18)  # the Discover read


class TestTheSpan:
    def test_anchored_bouts_open_the_window(self):
        first, last = card_status_span(_bouts(), UFC_IDS)
        assert first == _at(21, minute=10)
        assert last == _at(2, day=27, minute=15)

    def test_the_card_reads_upcoming_at_the_read(self):
        assert (
            card_status_from_bouts(_bouts(), READ_AT, anchored_ids=UFC_IDS)
            == "upcoming"
        )

    def test_and_it_really_did_say_live_before_this(self):
        """The strawman: no anchor set is the old date-token span."""
        assert card_status_span(_bouts()) == (_at(16), _at(2, day=27, minute=15))
        assert card_status_from_bouts(_bouts(), READ_AT) == "live"

    def test_the_pill_lights_at_the_first_priced_bout(self):
        assert (
            card_status_from_bouts(_bouts(), _at(21, minute=10), anchored_ids=UFC_IDS)
            == "live"
        )
        assert (
            card_status_from_bouts(_bouts(), _at(21, minute=9), anchored_ids=UFC_IDS)
            == "upcoming"
        )

    def test_the_closing_arm_keeps_the_full_span(self):
        """A later unpriced row still holds the card open — no earlier settle."""
        late = _FakeBout(15315974, "Osmanli", "Uulu", _at(5, day=27, minute=40))
        _, last = card_status_span(_bouts() + [late], UFC_IDS)
        assert last == _at(5, day=27, minute=40)

    def test_a_called_off_anchored_bout_does_not_open_the_window(self):
        bouts = _bouts()
        for b in bouts:
            if b.id == 15314294:
                b.status = "cancelled"
        first, _ = card_status_span(bouts, UFC_IDS)
        assert first == _at(22)

    def test_all_anchored_bouts_called_off_falls_back_to_the_date_span(self):
        """Anchors that are all off say nothing about when the night opens;
        the rows still going ahead do — the pre-#8881 answer, not an empty one."""
        bouts = _bouts()
        for b in bouts:
            if b.id in UFC_IDS:
                b.status = "cancelled"
        assert card_status_span(bouts, UFC_IDS)[0] == _at(16)

    @pytest.mark.parametrize("anchors", [None, set(), {424242}])
    def test_no_anchor_on_the_card_is_the_old_rule(self, anchors):
        assert card_status_span(_bouts(), anchors)[0] == _at(16)

    def test_no_minute_before_the_first_priced_bout_is_live(self):
        start = _at(0)
        for minutes in range(0, 21 * 60 + 10, 13):
            now = start + timedelta(minutes=minutes)
            assert (
                card_status_from_bouts(_bouts(), now, anchored_ids=UFC_IDS)
                == "upcoming"
            ), now


def _freeze(monkeypatch, at):
    """Both serve paths read `datetime.now` through a function-local import, so
    the clock is pinned on the module attribute that import resolves."""
    import datetime as _dt

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return at

    monkeypatch.setattr(_dt, "datetime", _Clock)


def _concept_rows(markets):
    return [(m.id, m.external_id, m.name, m.commence_time, {}) for m in markets]


def _the_card(concepts):
    card = [c for c in concepts if c["key"].endswith("26sep26")]
    assert card, [c["key"] for c in concepts]
    return card[0]


class TestEveryServePath:
    """The lister (the Discover card) and the Kalshi-backed page must agree."""

    @pytest.mark.asyncio
    async def test_the_concept_lister_serves_it_upcoming(self, monkeypatch):
        markets = _markets()
        rows = _concept_rows(markets)
        db = _MockDB(rows, event_rows=_bouts(), market_rows=markets)
        _freeze(monkeypatch, READ_AT)
        concepts = await list_card_concepts(
            UFC_CONFIG, db, statuses=("upcoming", "live", "settled"), rows=rows
        )
        assert _the_card(concepts)["status"] == "upcoming"

    @pytest.mark.asyncio
    async def test_the_concept_lister_is_live_once_the_card_starts(self, monkeypatch):
        """The first prelim's market already RESOLVED (15314290 was, on the
        specimen) — it still anchors the card, so the card stays live."""
        markets = _markets()
        markets[0].status = "resolved"
        rows = _concept_rows(markets[1:])  # a resolved row leaves the open scan
        db = _MockDB(rows, event_rows=_bouts(), market_rows=markets)
        _freeze(monkeypatch, _at(21, minute=30))
        concepts = await list_card_concepts(UFC_CONFIG, db, rows=rows)
        assert _the_card(concepts)["status"] == "live"

    @pytest.mark.asyncio
    async def test_the_kalshi_backed_page_serves_it_upcoming(self, monkeypatch):
        db = _MockDB([], event_rows=_bouts(), market_rows=_markets())
        _freeze(monkeypatch, READ_AT)
        env = await CombatEventAdapter(UFC_CONFIG).build_event("26sep26", db)
        assert env is not None
        assert env["primary"]["evolution_market_id"] is not None  # Kalshi branch
        assert env["event"]["status"] == "upcoming"

    @pytest.mark.asyncio
    async def test_the_kalshi_backed_page_goes_live_at_the_first_priced_bout(
        self, monkeypatch
    ):
        db = _MockDB([], event_rows=_bouts(), market_rows=_markets())
        _freeze(monkeypatch, _at(21, minute=30))
        env = await CombatEventAdapter(UFC_CONFIG).build_event("26sep26", db)
        assert env["event"]["status"] == "live"

    @pytest.mark.asyncio
    async def test_an_events_only_card_is_unchanged(self, monkeypatch):
        """No venue market on the card ⇒ no anchors ⇒ the date-token window."""
        db = _MockDB([], event_rows=_bouts(), market_rows=[])
        _freeze(monkeypatch, READ_AT)
        concepts = await list_card_concepts(UFC_CONFIG, db, rows=[])
        assert _the_card(concepts)["status"] == "live"


class TestTheAnchorReadIgnoresMarketStatus:
    """The mocks above answer every status alike, so they cannot see an `open`
    filter creep into the anchor read. This reads the statement itself."""

    @pytest.mark.asyncio
    async def test_the_statement_has_no_status_filter(self):
        from app.utils.event_combat import _card_tokens_by_bout

        seen = []

        class _Recorder(_MockDB):
            async def execute(self, statement=None, *a, **k):
                seen.append(str(statement))
                return await super().execute(statement, *a, **k)

        await _card_tokens_by_bout(
            UFC_CONFIG, _Recorder([], market_rows=_markets()), [1]
        )
        assert len(seen) == 1
        where = seen[0].split("WHERE", 1)[1]
        assert "event_id" in where
        assert "status" not in where
