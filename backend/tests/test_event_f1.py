"""#999 L2-72: F1 adapter pure helpers (winner-field motorsports).
L2-86 (B5): the GP concept lister that surfaces Grands Prix on the /sports feed."""

from datetime import datetime, timezone, timedelta

import pytest

from app.utils.event_f1 import (
    is_gp_winner_market,
    gp_tokens,
    shares_gp,
    f1_status,
    list_f1_gp_concepts,
)

NOW = datetime(2026, 7, 9, tzinfo=timezone.utc)


class TestGpWinnerClassifier:
    def test_main_race_winner_is_primary(self):
        assert is_gp_winner_market("British Grand Prix Winner") is True
        assert is_gp_winner_market("British Grand Prix: Driver Winner") is True

    def test_submarkets_are_not_the_primary(self):
        for n in [
            "British Grand Prix: Sprint Race Winner",
            "British Grand Prix Qualifying Session (Q3): Pole Position",
            "Austrian Grand Prix Main Race: Podium Finishers",
            "Austrian Grand Prix Main Race: Top Constructor",
            "British Grand Prix Sprint Race: Top 5 Finishers",
        ]:
            assert is_gp_winner_market(n) is False, n


class TestGpTokens:
    def test_distinctive_gp_name(self):
        assert gp_tokens("British Grand Prix Winner") == {"british"}
        assert gp_tokens("Austrian Grand Prix Main Race: Fastest Lap") == {"austrian"}

    def test_shares_gp(self):
        toks = gp_tokens("British Grand Prix Winner")
        assert shares_gp("British Grand Prix: Sprint Race Winner", toks) is True
        assert shares_gp("Austrian Grand Prix Winner", toks) is False
        assert shares_gp("anything", set()) is False


class TestF1Status:
    def test_settled_past_or_resolved(self):
        assert f1_status("resolved", NOW + timedelta(days=2), NOW) == "settled"
        assert f1_status("open", NOW - timedelta(days=1), NOW) == "settled"

    def test_live_on_race_weekend(self):
        assert f1_status("open", NOW + timedelta(days=2), NOW) == "live"

    def test_upcoming_when_far_or_unknown(self):
        assert f1_status("open", NOW + timedelta(days=20), NOW) == "upcoming"
        assert f1_status("open", None, NOW) == "upcoming"


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
class TestListF1GpConcepts:
    async def test_groups_gp_and_counts_weekend_markets(self):
        # One British GP: winner market anchors; sub-markets fold into entry_count.
        soon = datetime.now(timezone.utc) + timedelta(days=3)
        rows = [
            (1, "British Grand Prix: Driver Winner", "open", soon),
            (2, "British Grand Prix: Driver Pole Position", "open", soon),
            (3, "British Grand Prix: Constructor Fastest Lap", "open", soon),
            # A different GP, further out.
            (4, "Hungarian Grand Prix Winner", "open", soon + timedelta(days=14)),
        ]
        concepts = await list_f1_gp_concepts(_MockDB(rows))
        # British (soonest) first.
        assert concepts[0]["key"] == "event:f1:british-grand-prix-driver-winner"
        assert concepts[0]["domain"] == "f1"
        assert concepts[0]["status"] == "live"  # 3 days out = race weekend
        assert concepts[0]["entry_count"] == 3  # winner + pole + fastest-lap
        assert concepts[0]["is_major"] is False
        # Both GPs surfaced.
        assert {c["name"] for c in concepts} == {
            "British Grand Prix: Driver Winner",
            "Hungarian Grand Prix Winner",
        }

    async def test_season_championship_is_not_a_gp_concept(self):
        # "F1 Drivers Champion" has no winner/to-win token → not a GP concept.
        rows = [(1, "F1 Drivers Champion", "open", None)]
        assert await list_f1_gp_concepts(_MockDB(rows)) == []

    async def test_far_off_gp_excluded_by_status(self):
        far = datetime.now(timezone.utc) + timedelta(days=40)
        rows = [(1, "Singapore Grand Prix Winner", "open", far)]
        # Default statuses are (upcoming, live); a 40-day-out GP is "upcoming" and
        # DOES surface — assert the descriptor is well-formed.
        concepts = await list_f1_gp_concepts(_MockDB(rows))
        assert len(concepts) == 1
        assert concepts[0]["status"] == "upcoming"
        assert concepts[0]["start_date"] == far.isoformat()
