"""L2-86 (B5): boxing adapter — proves the "config drop" works end-to-end on the
shared combat engine. Boxing is unnumbered (no "UFC 329" analogue), so card labels
are the headline bout and is_major is always False; card grouping by date-token and
prop classification mirror UFC. Verified against real KXBOXING-* ticker shapes."""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_boxing import (
    BOXING_CONFIG,
    classify_boxing_prop,
    derive_boxing_concept,
    list_boxing_card_concepts,
)
from app.utils.event_combat import card_label, card_token, combat_status

NOW = datetime(2026, 7, 12, 18, 0, tzinfo=timezone.utc)


class TestBoxingCardToken:
    def test_extracts_date_token_from_fight_ticker(self):
        # Real live shapes: KXBOXING-<YYMONDD><FIGHTERS>.
        assert card_token(BOXING_CONFIG, "KXBOXING-26JUL04MASONBELL") == "26jul04"
        assert card_token(BOXING_CONFIG, "kalshi:KXBOXING-26SEP12CALVARMBILLI") == "26sep12"

    def test_same_card_shares_token(self):
        a = card_token(BOXING_CONFIG, "KXBOXING-26JUL04MASONBELL")
        b = card_token(BOXING_CONFIG, "KXBOXING-26JUL04DAVISRAMOS")
        assert a == b == "26jul04"

    def test_prop_ticker_is_not_a_fight(self):
        # Props (KXBOXINGMOV-, KXBOXINGDISTANCE-) must NOT be read as card fights.
        assert card_token(BOXING_CONFIG, "KXBOXINGMOV-26JUL04MASONBELL") is None
        assert card_token(BOXING_CONFIG, "KXBOXINGDISTANCE-26JUL04MASONBELL") is None
        assert card_token(BOXING_CONFIG, "KXBOXINGKNOCKOUT-26JUL04X") is None

    def test_futures_and_foreign_tickers_none(self):
        for ext in [
            "KXWBCHEAVYWEIGHTTITLE-27",  # title future
            "KXFURYJOSHUA-26",           # will-they-fight future
            "KXITFMATCH-26JUL01CONJAN",  # mis-categorized tennis — excluded by prefix
            None,
            "",
        ]:
            assert card_token(BOXING_CONFIG, ext) is None


class TestBoxingCardLabel:
    def test_unnumbered_card_uses_headline_and_is_not_major(self):
        # Boxing has no "UFC 329" numbering → headline bout is the label, never major.
        label, is_major = card_label(BOXING_CONFIG, "Canelo Alvarez vs Christian Mbilli")
        assert label == "Canelo Alvarez vs Christian Mbilli"
        assert is_major is False

    def test_event_prefixed_name_kept(self):
        # "La Velada del Año VI: X vs Y" is kept intact (no numbering to strip).
        label, is_major = card_label(
            BOXING_CONFIG, "La Velada del Año VI: Alondrissa vs Angie Velasco"
        )
        assert label == "La Velada del Año VI: Alondrissa vs Angie Velasco"
        assert is_major is False

    def test_ufc_numbering_does_not_leak_into_boxing(self):
        # Even a name that mentions a number stays unnumbered for boxing.
        label, is_major = card_label(BOXING_CONFIG, "Fight 12: A vs B")
        assert is_major is False
        assert label == "Fight 12: A vs B"


class TestBoxingClassifyProp:
    def test_kalshi_prop_tickers(self):
        assert classify_boxing_prop("KXBOXINGMOV-26JUL04X", "Method of victory") == "method"
        assert classify_boxing_prop("KXBOXINGKNOCKOUT-26JUL04X", "Knockout?") == "method"
        assert classify_boxing_prop("KXBOXINGROUNDS-26JUL04X", "Total rounds") == "rounds"
        assert classify_boxing_prop("KXBOXINGVICROUND-26JUL04X", "Victory in round") == "rounds"
        assert classify_boxing_prop("KXBOXINGDISTANCE-26JUL04X", "Go the distance") == "distance"
        assert classify_boxing_prop("KXBOXING1MIN-26JUL04X", "One minute fight") == "occurrence"

    def test_plain_fight_is_not_a_prop(self):
        assert classify_boxing_prop("KXBOXING-26JUL04MASONBELL", "Abdullah Mason vs Albert Bell") is None


class TestBoxingDeriveConcept:
    def test_fight_market_yields_card_concept(self):
        c = derive_boxing_concept("KXBOXING-26SEP12CALVARMBILLI", "Canelo Alvarez vs Christian Mbilli", 2)
        assert c is not None
        assert c["key"] == "event:boxing:26sep12"
        assert c["domain"] == "boxing"
        assert c["is_major"] is False

    def test_prop_returns_none(self):
        assert derive_boxing_concept("KXBOXINGMOV-26JUL04X", "Method of victory", 4) is None


class TestCombatStatusSharedByBoxing:
    def test_upcoming_live_settled(self):
        assert combat_status(NOW + timedelta(hours=48), NOW) == "upcoming"
        assert combat_status(NOW + timedelta(hours=2), NOW) == "live"
        assert combat_status(NOW - timedelta(hours=10), NOW) == "settled"


class _MockScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _MockResult:
    # Kalshi FuturesMarket query reads via .all() (tuples); the events-table query
    # reads via .scalars().all() (Event-likes) — the two access paths keep them apart.
    def __init__(self, rows, event_rows):
        self._rows = rows
        self._event_rows = event_rows

    def all(self):
        return self._rows

    def scalars(self):
        return _MockScalars(self._event_rows)


class _MockDB:
    def __init__(self, rows, event_rows=None):
        self._rows = rows
        self._event_rows = event_rows or []

    async def execute(self, *_a, **_k):
        return _MockResult(self._rows, self._event_rows)


class _FakeBout:
    """Minimal Event stand-in for the events-table schedule source."""

    def __init__(self, id, home, away, commence, status="scheduled"):
        self.id = id
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence
        self.status = status


@pytest.mark.asyncio
class TestListBoxingCardConcepts:
    async def test_groups_fights_by_card(self):
        # Anchor to noon so the prelim (headline -1h) stays on the same UTC day.
        # A raw datetime.now() run at 00:00–02:00 UTC splits the two bouts across
        # midnight into two card tokens and fails fight_count (the midnight flake).
        soon = datetime.now(timezone.utc).replace(
            hour=12, minute=0, second=0, microsecond=0
        ) + timedelta(days=10)
        rows = [
            (1, "KXBOXING-26JUL04MASONBELL", "Abdullah Mason vs Albert Bell", soon, {}),
            (2, "KXBOXING-26JUL04DAVISRAMOS", "Deric Davis vs Carlos Ramos",
             soon - timedelta(hours=1), {}),
            # A prop ticker + a title future — neither creates/pollutes a card.
            (3, "KXBOXINGMOV-26JUL04MASONBELL", "Method of victory", soon, {}),
            (4, "KXWBCHEAVYWEIGHTTITLE-27", "WBC Heavyweight Title", soon, {}),
        ]
        concepts = await list_boxing_card_concepts(_MockDB(rows))
        assert len(concepts) == 1
        c = concepts[0]
        assert c["key"] == "event:boxing:26jul04"
        assert c["domain"] == "boxing"
        assert c["fight_count"] == 2
        assert c["is_major"] is False
        assert c["status"] == "upcoming"

    async def test_empty_when_no_fights(self):
        rows = [(1, "KXBOXINGMOV-26JUL04X", "Method", None, {})]
        assert await list_boxing_card_concepts(_MockDB(rows)) == []

    async def test_events_source_surfaces_card_before_kalshi(self):
        # No Kalshi markets yet — the events-table schedule alone must surface the
        # card (the T-5 "before Kalshi floods" gap), keyed by the bout's commence
        # date-token so it later UNIFIES with the Kalshi-derived card.
        from app.utils.event_combat import event_commence_token

        # Noon-anchored so the prelim (headline -1h) never crosses midnight into a
        # second card token no matter when the suite runs (midnight flake guard).
        soon = datetime.now(timezone.utc).replace(
            hour=12, minute=0, second=0, microsecond=0
        ) + timedelta(days=10)
        token = event_commence_token(soon)
        bouts = [
            _FakeBout(1, "Abdullah Mason", "Albert Bell", soon),
            _FakeBout(2, "Deric Davis", "Carlos Ramos", soon - timedelta(hours=1)),
        ]
        concepts = await list_boxing_card_concepts(_MockDB([], event_rows=bouts))
        assert len(concepts) == 1
        c = concepts[0]
        assert c["key"] == f"event:boxing:{token}"
        assert c["fight_count"] == 2
        assert c["main_event_id"] is None  # no futures market yet
        # Headline = latest-commence bout (Mason vs Bell caps the night).
        assert "Mason" in c["name"] and "Bell" in c["name"]

    async def test_events_commence_overrides_kalshi_close_date(self):
        # Kalshi's commence is often the resolution/close date (gotcha #14). When a
        # scheduled bout shares the card token, its fight-start time is authoritative.
        from app.utils.event_combat import event_commence_token

        # Noon-anchored: keeps the derived date-token stable across near-midnight runs.
        fight_time = datetime.now(timezone.utc).replace(
            hour=12, minute=0, second=0, microsecond=0
        ) + timedelta(days=5)
        token = event_commence_token(fight_time)
        close_date = fight_time + timedelta(days=15)  # bogus Kalshi close date
        rows = [
            (1, f"KXBOXING-{token.upper()}MASONBELL", "Abdullah Mason vs Albert Bell",
             close_date, {}),
        ]
        bouts = [_FakeBout(9, "Abdullah Mason", "Albert Bell", fight_time)]
        concepts = await list_boxing_card_concepts(
            _MockDB(rows, event_rows=bouts)
        )
        assert len(concepts) == 1
        c = concepts[0]
        assert c["key"] == f"event:boxing:{token}"
        # Authoritative start = the real fight time, NOT the Kalshi close date.
        assert c["latest_commence"] == fight_time
        assert c["main_event_id"] == 1  # Kalshi still supplies the fight market
