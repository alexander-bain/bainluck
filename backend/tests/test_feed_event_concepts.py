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


class _MockResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _MockDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_a, **_k):
        return _MockResult(self._rows)


@pytest.mark.asyncio
class TestListUfcCardConcepts:
    async def test_groups_fights_by_card_and_names_numbered(self):
        # Two fights on the JUL11 card (one numbered) + a prop ticker (ignored).
        soon = datetime.now(timezone.utc) + timedelta(days=10)
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
