"""#999 B3 / L2-84: event-concept feed candidates (UFC cards on /sports).

Covers the self-contained concept scorer + headline (pure) and the DB-backed
card enumeration (list_ufc_card_concepts) — the additive candidate plumbing that
makes "UFC 329" bubble on the sports tab. No existing scorer is touched, so these
never perturb the RANK-frozen futures path."""

from datetime import datetime, timezone, timedelta

import pytest

from app.routes.feed import _score_event_concept, _concept_headline, _concept_reason
from app.utils.event_ufc import list_ufc_card_concepts

NOW = datetime(2026, 7, 12, 18, 0, tzinfo=timezone.utc)


def _concept(**kw):
    base = {
        "is_major": False,
        "status": "upcoming",
        "latest_commence": NOW + timedelta(days=14),
        "fight_count": 1,
    }
    base.update(kw)
    return base


class TestScoreEventConcept:
    def test_major_card_scores_above_unnumbered(self):
        major = _score_event_concept(_concept(is_major=True), NOW)
        minor = _score_event_concept(_concept(is_major=False), NOW)
        assert major > minor

    def test_live_card_boosted(self):
        live = _score_event_concept(_concept(status="live"), NOW)
        upcoming = _score_event_concept(_concept(status="upcoming"), NOW)
        assert live > upcoming

    def test_soon_card_beats_far_off(self):
        soon = _score_event_concept(
            _concept(latest_commence=NOW + timedelta(days=2)), NOW
        )
        far = _score_event_concept(
            _concept(latest_commence=NOW + timedelta(days=30)), NOW
        )
        assert soon > far

    def test_bigger_card_scores_higher(self):
        big = _score_event_concept(_concept(fight_count=12), NOW)
        small = _score_event_concept(_concept(fight_count=1), NOW)
        assert big > small

    def test_score_bounded(self):
        s = _score_event_concept(
            _concept(is_major=True, status="live", fight_count=12,
                     latest_commence=NOW),
            NOW,
        )
        assert 0 <= s <= 100


class TestConceptHeadline:
    def test_live(self):
        assert _concept_headline(_concept(status="live"), NOW) == "Live"

    def test_today_tomorrow_week(self):
        assert _concept_headline(_concept(latest_commence=NOW), NOW) == "Today"
        assert _concept_headline(
            _concept(latest_commence=NOW + timedelta(days=1)), NOW
        ) == "Tomorrow"
        assert _concept_headline(
            _concept(latest_commence=NOW + timedelta(days=5)), NOW
        ) == "This week"

    def test_far_off_none(self):
        assert _concept_headline(
            _concept(latest_commence=NOW + timedelta(days=30)), NOW
        ) is None


class TestConceptReason:
    """L2-86: the reason line is domain-aware (UFC fights vs F1 weekend markets)."""

    def test_ufc_reason(self):
        assert _concept_reason({"domain": "ufc", "fight_count": 12}) == "12 fights on the card"
        assert _concept_reason({"domain": "ufc", "fight_count": 1}) == "1 fight on the card"

    def test_f1_reason(self):
        assert _concept_reason({"domain": "f1", "entry_count": 6}) == "6 weekend markets"
        assert _concept_reason({"domain": "f1", "entry_count": 1}) == "1 weekend market"
        assert _concept_reason({"domain": "f1", "entry_count": 0}) == "Grand Prix race winner"


class _MockScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _MockResult:
    # Kalshi FuturesMarket query reads via .all() (tuples); the events-table query
    # reads via .scalars().all() (Event-likes).
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
class TestListUfcCardConcepts:
    async def test_groups_fights_by_card_and_names_numbered(self):
        # Two fights on the JUL11 card (one numbered) + a prop ticker (ignored).
        # Noon-anchored so the undercard (headline -2h) stays on the same UTC day;
        # a raw datetime.now() run at 00:00–02:00 UTC splits the card (midnight flake).
        soon = datetime.now(timezone.utc).replace(
            hour=12, minute=0, second=0, microsecond=0
        ) + timedelta(days=10)
        rows = [
            (201, "kalshi:KXUFCFIGHT-26JUL11MCGHOL",
             "UFC 329: McGregor vs. Holloway 2", soon,
             {"event_title": "UFC 329: McGregor vs. Holloway 2"}),
            (202, "kalshi:KXUFCFIGHT-26JUL11UNDER",
             "Undercard A vs B", soon - timedelta(hours=2), {}),
            # A prop ticker — NOT a fight, must not create/pollute a card.
            (203, "kalshi:KXUFCMOV-26JUL11MCGHOL", "Method of Victory", soon, {}),
        ]
        concepts = await list_ufc_card_concepts(_MockDB(rows))
        assert len(concepts) == 1
        c = concepts[0]
        assert c["key"] == "event:ufc:26jul11"
        assert c["name"] == "UFC 329: McGregor vs. Holloway 2"
        assert c["is_major"] is True
        assert c["fight_count"] == 2
        assert c["status"] == "upcoming"

    async def test_empty_when_no_fights(self):
        rows = [(1, "kalshi:KXUFCMOV-26JUL11X", "Method", None, {})]
        assert await list_ufc_card_concepts(_MockDB(rows)) == []

    async def test_events_source_surfaces_ufc_card_before_kalshi(self):
        # The events-table schedule surfaces a UFC card T-5, before Kalshi lists it.
        from app.utils.event_combat import event_commence_token

        # Anchor both bouts to the SAME UTC calendar day (a real card shares one
        # Kalshi ticker date). Normalizing to noon makes the prelim (main -2h)
        # land on the same date no matter when the suite runs — otherwise a run
        # near 00:00 UTC splits the two bouts across midnight into two card tokens
        # and the assertion fails (the #1093 midnight combat-test flake).
        card_day = (datetime.now(timezone.utc) + timedelta(days=8)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        token = event_commence_token(card_day)
        bouts = [
            _FakeBout(1, "Dricus Du Plessis", "Kamaru Usman", card_day),
            _FakeBout(2, "Undercard A", "Undercard B", card_day - timedelta(hours=2)),
        ]
        concepts = await list_ufc_card_concepts(_MockDB([], event_rows=bouts))
        assert len(concepts) == 1
        c = concepts[0]
        assert c["key"] == f"event:ufc:{token}"
        assert c["fight_count"] == 2
        assert c["main_event_id"] is None
        assert "Du Plessis" in c["name"] and "Usman" in c["name"]

    async def test_events_commence_overrides_kalshi_close_date(self):
        # Real Du Plessis/Usman shape (gotcha #14): the Kalshi fight's commence is a
        # far-future close date; the scheduled bout's time is authoritative.
        from app.utils.event_combat import event_commence_token

        # Noon-anchored: keeps the derived date-token stable across near-midnight runs.
        fight_time = datetime.now(timezone.utc).replace(
            hour=12, minute=0, second=0, microsecond=0
        ) + timedelta(days=5)
        token = event_commence_token(fight_time)
        close_date = fight_time + timedelta(days=15)
        rows = [
            (301, f"kalshi:KXUFCFIGHT-{token.upper()}DUPUSM",
             "Fight Night: Du Plessis vs Usman", close_date, {}),
        ]
        bouts = [_FakeBout(1, "Dricus Du Plessis", "Kamaru Usman", fight_time)]
        concepts = await list_ufc_card_concepts(_MockDB(rows, event_rows=bouts))
        assert len(concepts) == 1
        c = concepts[0]
        assert c["latest_commence"] == fight_time  # not the Kalshi close date
        assert c["main_event_id"] == 301


class TestResolveConceptChampion:
    """#1219 — the WHAT-HIT card names the graded champion of a settled concept.

    ``_resolve_concept_champion`` mirrors the settled-concept sentinel's crown
    (exactly one competitor with ``won=True``) so a settled marquee card can lead
    with "Tadej Pogačar — Won" instead of a bare recap invite. Best-effort: an
    ambiguous / absent crown, or any failure, returns None (the recap fallback);
    it never fabricates a winner."""

    class _FakeAdapter:
        def __init__(self, envelope):
            self._envelope = envelope

        async def build_event(self, slug, db):
            return self._envelope

    @staticmethod
    def _patch(monkeypatch, envelope):
        import app.utils.event_concept as ec

        monkeypatch.setattr(
            ec, "get_adapter",
            lambda domain: TestResolveConceptChampion._FakeAdapter(envelope),
        )

        # Force a cold envelope cache so the adapter path runs deterministically.
        def _boom(*a, **k):
            raise RuntimeError("no redis in test")

        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", _boom)

    @pytest.mark.asyncio
    async def test_single_crown_returns_winner(self, monkeypatch):
        from app.routes.feed import _resolve_concept_champion

        self._patch(monkeypatch, {"primary": {"competitors": [
            {"name": "Tadej Pogačar", "won": True, "probability": 0.99},
            {"name": "Jonas Vingegaard", "won": False, "probability": 0.4},
        ]}})
        result = await _resolve_concept_champion(
            None, "event:cycling:tour-de-france-2026"
        )
        assert result == {"winner": "Tadej Pogačar", "result_summary": None}

    @pytest.mark.asyncio
    async def test_ambiguous_crown_returns_none(self, monkeypatch):
        from app.routes.feed import _resolve_concept_champion

        self._patch(monkeypatch, {"primary": {"competitors": [
            {"name": "A", "won": True},
            {"name": "B", "won": True},
        ]}})
        result = await _resolve_concept_champion(None, "event:f1:british-gp-2026")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_crown_returns_none(self, monkeypatch):
        from app.routes.feed import _resolve_concept_champion

        self._patch(monkeypatch, {"primary": {"competitors": [
            {"name": "A", "won": False},
            {"name": "B", "won": False},
        ]}})
        result = await _resolve_concept_champion(None, "event:cycling:tour-de-france-2026")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_envelope_returns_none(self, monkeypatch):
        from app.routes.feed import _resolve_concept_champion

        self._patch(monkeypatch, None)
        result = await _resolve_concept_champion(None, "event:cycling:tour-de-france-2026")
        assert result is None
