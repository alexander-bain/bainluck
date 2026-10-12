"""#1010 — tennis and MMA over/under and handicap lines are not graded from a
score that cannot settle them.

The spreads/totals curves grade every event as ``home + away > line`` /
``(home - away) + spread > 0``. For tennis the stored score counts SETS (sum
2..5) while the lines count GAMES (O/U 15.5..42.5); for MMA the stored score is a
1-0 WINNER FLAG while the lines count ROUNDS. Measured on the 2026-10-11 23:08Z
publish: tennis ``odds_api_totals`` winner rate 0.000 in all nine tournaments
(ECE ~50 each), MMA totals 0.020 over n=100.

Specimen numbers below are those published cells, so the arithmetic the guard
checks is the arithmetic a reader was shown.
"""

from types import SimpleNamespace

import pytest

from app.routes import calibration as calibration_route
from app.tasks import precompute_calibration as pc
from tests.test_calibration_spreads_totals import (  # noqa: F401 — autouse fixture
    _bucket_row,
    _disable_sample_gate,
    _FakeDB,
)


class TestFamilyRule:
    @pytest.mark.parametrize(
        "category",
        ["tennis_atp_us_open", "tennis_wta_canadian_open", "mma_mixed_martial_arts", "tennis"],
    )
    def test_ungradeable_families(self, category):
        assert pc.category_has_score_unit_mismatch(category) is True

    @pytest.mark.parametrize(
        "category",
        [
            # Score and line share a unit (points, runs, goals): kept.
            "basketball_nba",
            "americanfootball_nfl",
            "baseball_mlb",
            "icehockey_nhl",
            "soccer_epl",
            # A family is the first `_` segment, never a substring.
            "table_tennis",
            "mmax_league",
            "",
            None,
        ],
    )
    def test_gradeable_families(self, category):
        assert pc.category_has_score_unit_mismatch(category) is False

    def test_sql_form_names_the_same_families(self):
        assert pc.score_unit_mismatch_sql("s.key") == "split_part(s.key, '_', 1) IN ('mma', 'tennis')"
        for family in pc.SCORE_UNIT_MISMATCH_FAMILIES:
            assert f"'{family}'" in pc.score_unit_mismatch_sql("s.key")

    def test_split_counts_outcomes_not_rows(self):
        rows = [
            SimpleNamespace(category="tennis_wta_canadian_open", n=41),
            SimpleNamespace(category="basketball_nba", n=300),
            SimpleNamespace(category="mma_mixed_martial_arts", n=7),
        ]
        kept, excluded = pc.split_score_unit_mismatch(rows)
        assert [r.category for r in kept] == ["basketball_nba"]
        assert excluded == 48


def _row(source, category, bucket_idx, n, winners, avg_prob):
    return _bucket_row(
        bucket_idx=bucket_idx,
        source=source,
        category=category,
        n=n,
        winners=winners,
        avg_prob=avg_prob,
        sum_prob=avg_prob * n,
        sum_sq_err=winners * (1 - avg_prob) ** 2 + (n - winners) * avg_prob**2,
    )


# The published tennis_wta_canadian_open totals cells (bucket 4: 30 rows, 0
# winners; bucket 5: 41 rows, 0 winners), the MMA totals cell, and the matching
# spreads cells — next to NBA cells that must pass through untouched.
SPREADS = [
    _row("odds_api_spreads", "tennis_wta_canadian_open", 4, 25, 16, 0.4703),
    _row("odds_api_spreads", "mma_mixed_martial_arts", 5, 67, 25, 0.512),
    _row("odds_api_spreads", "basketball_nba", 5, 565, 293, 0.500),
]
TOTALS = [
    _row("odds_api_totals", "tennis_wta_canadian_open", 4, 30, 0, 0.4792),
    _row("odds_api_totals", "tennis_wta_canadian_open", 5, 41, 0, 0.5086),
    _row("odds_api_totals", "mma_mixed_martial_arts", 5, 100, 2, 0.545),
    _row("odds_api_totals", "basketball_nba", 5, 565, 295, 0.501),
]
# CONTROL: the moneyline for the same tennis tournament. Who won the match is
# what the stored score DOES say, so the rule must not touch this row.
EVENTS = [
    _row("odds_api", "tennis_wta_canadian_open", 5, 27, 14, 0.5434),
]


@pytest.fixture
async def payload():
    db = _FakeDB(events_rows=EVENTS, spreads_rows=SPREADS, totals_rows=TOTALS)
    return await pc.compute_calibration_payload(db)


class TestPublishedCurve:
    @pytest.mark.asyncio
    async def test_no_tennis_or_mma_spreads_or_totals_bucket_is_published(self, payload):
        leaked = [
            (b["source"], b["category"])
            for b in payload["buckets"]
            if b["source"] in ("odds_api_spreads", "odds_api_totals")
            and pc.category_has_score_unit_mismatch(b["category"])
        ]
        assert leaked == []

    @pytest.mark.asyncio
    async def test_gradeable_spreads_and_totals_pass_through_unchanged(self, payload):
        nba = {
            b["source"]: (b["n"], b["winners"])
            for b in payload["buckets"]
            if b["category"] == "basketball_nba"
        }
        assert nba == {"odds_api_spreads": (565, 293), "odds_api_totals": (565, 295)}

    @pytest.mark.asyncio
    async def test_tennis_moneyline_is_kept(self, payload):
        ml = [
            (b["n"], b["winners"])
            for b in payload["buckets"]
            if b["source"] == "odds_api" and b["category"] == "tennis_wta_canadian_open"
        ]
        assert ml == [(27, 14)]

    @pytest.mark.asyncio
    async def test_the_exclusion_is_named_and_counted(self, payload):
        block = payload["score_unit_filter"]
        assert block["spreads_excluded"] == 25 + 67
        assert block["totals_excluded"] == 30 + 41 + 100
        assert block["excluded"] == 25 + 67 + 30 + 41 + 100
        assert block["rule"] == pc.SCORE_UNIT_MISMATCH_RULE_TEXT

    @pytest.mark.asyncio
    async def test_excluded_rows_leave_the_outcome_total(self, payload):
        assert payload["total_outcomes"] == 27 + 565 + 565
        assert payload["totals_summary"]["outcomes"] == 565
        assert payload["spreads_summary"]["outcomes"] == 565

    @pytest.mark.asyncio
    async def test_a_build_with_no_such_rows_reports_a_checked_zero(self):
        db = _FakeDB(spreads_rows=SPREADS[2:], totals_rows=TOTALS[3:])
        payload = await pc.compute_calibration_payload(db)
        assert payload["score_unit_filter"]["excluded"] == 0

    def test_the_corrections_log_points_at_the_live_count(self):
        entry = [c for c in pc.CALIBRATION_CORRECTIONS if c["date"] == "2026-10-11"]
        assert len(entry) == 1
        assert entry[0]["rows"] is None


class _CapturingDB:
    def __init__(self):
        self.statements = []

    async def execute(self, statement, params=None):
        self.statements.append(str(statement))
        return SimpleNamespace(all=lambda: [])


class TestDrillDownSamples:
    """A reader clicking a spreads/totals bucket must not be shown a row the
    curve no longer counts."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("source", ["odds_api_spreads", "odds_api_totals"])
    async def test_spreads_and_totals_samples_exclude_the_families(self, source, monkeypatch):
        monkeypatch.setattr(calibration_route, "_examples_cache", {})
        db = _CapturingDB()
        await calibration_route.calibration_examples(
            db=db, source=source, bucket=5, well_traded=1, limit=5
        )
        assert len(db.statements) == 1
        assert f"NOT ({pc.score_unit_mismatch_sql('s.key')})" in db.statements[0]

    @pytest.mark.asyncio
    async def test_moneyline_samples_are_untouched(self, monkeypatch):
        monkeypatch.setattr(calibration_route, "_examples_cache", {})
        db = _CapturingDB()
        await calibration_route.calibration_examples(
            db=db, source="odds_api", bucket=5, well_traded=1, limit=5
        )
        assert len(db.statements) == 1
        assert "split_part(s.key" not in db.statements[0]
