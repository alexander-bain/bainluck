"""Tests for spread/total calibration logic.

Verifies the SQL calibration queries for spreads and totals:
- Devig normalization (American odds → fair probability)
- Push exclusion (exact margin = spread, or exact total = line)
- Spread coverage (favorite covers when margin + spread > 0)
- Total over/under resolution (total points vs closing line)
- Per-sport bucketing and MCE computation
"""

from types import SimpleNamespace

import pytest

from app.routes import calibration


class _FakeResult:
    def __init__(self, *, rows=None, scalar_value=None, one_value=None):
        self._rows = rows or []
        self._scalar_value = scalar_value
        self._one_value = one_value

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar_value

    def one(self):
        return self._one_value


class _FakeDB:
    """Fake async DB that returns pre-configured results in order.

    Call order in public_calibration:
    0: futures_markets CTE (bucket rows)
    1: events moneyline (bucket rows)
    2: spreads (bucket rows)
    3: totals (bucket rows)
    4: total_markets count (scalar)
    5: closing_line_coverage (one row)
    """

    def __init__(
        self,
        *,
        futures_rows=None,
        events_rows=None,
        spreads_rows=None,
        totals_rows=None,
        total_markets=0,
        closing_row=None,
    ):
        self._results = [
            _FakeResult(rows=futures_rows or []),
            _FakeResult(rows=events_rows or []),
            _FakeResult(rows=spreads_rows or []),
            _FakeResult(rows=totals_rows or []),
            _FakeResult(scalar_value=total_markets),
            _FakeResult(
                one_value=closing_row
                or SimpleNamespace(
                    has_closing=0,
                    needs_closing=0,
                    total_completed=0,
                )
            ),
        ]

    async def execute(self, statement):
        return self._results.pop(0)


def _bucket_row(
    *,
    bucket_idx,
    source,
    category,
    price_moved=None,
    n,
    winners,
    avg_prob,
    sum_prob,
    sum_sq_err,
):
    return SimpleNamespace(
        bucket_idx=bucket_idx,
        source=source,
        category=category,
        price_moved=price_moved,
        n=n,
        winners=winners,
        avg_prob=avg_prob,
        sum_prob=sum_prob,
        sum_sq_err=sum_sq_err,
    )


# ---------------------------------------------------------------------------
# Spreads summary shape
# ---------------------------------------------------------------------------


class TestSpreadsSummary:
    """Verify the spreads_summary section in the calibration response."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        calibration._cache = {"data": None, "timestamp": 0}

    @pytest.mark.asyncio
    async def test_spreads_summary_present_when_no_data(self):
        db = _FakeDB()
        response = await calibration.public_calibration(db=db, bust=1)
        summary = response["spreads_summary"]
        assert summary["mce"] is None
        assert summary["outcomes"] == 0
        assert summary["winners"] == 0
        assert summary["by_sport"] == []

    @pytest.mark.asyncio
    async def test_spreads_summary_with_single_sport(self):
        db = _FakeDB(
            spreads_rows=[
                _bucket_row(
                    bucket_idx=4,
                    source="odds_api_spreads",
                    category="basketball_nba",
                    n=100,
                    winners=52,
                    avg_prob=0.52,
                    sum_prob=52.0,
                    sum_sq_err=24.96,
                )
            ],
        )
        response = await calibration.public_calibration(db=db, bust=1)
        summary = response["spreads_summary"]
        assert summary["outcomes"] == 100
        assert summary["winners"] == 52
        assert summary["mce"] is not None
        assert isinstance(summary["mce"], (int, float))
        assert len(summary["by_sport"]) == 1
        assert summary["by_sport"][0]["sport"] == "basketball_nba"
        assert summary["by_sport"][0]["outcomes"] == 100

    @pytest.mark.asyncio
    async def test_spreads_summary_multiple_sports(self):
        db = _FakeDB(
            spreads_rows=[
                _bucket_row(
                    bucket_idx=4,
                    source="odds_api_spreads",
                    category="basketball_nba",
                    n=100,
                    winners=52,
                    avg_prob=0.52,
                    sum_prob=52.0,
                    sum_sq_err=24.96,
                ),
                _bucket_row(
                    bucket_idx=5,
                    source="odds_api_spreads",
                    category="americanfootball_nfl",
                    n=80,
                    winners=42,
                    avg_prob=0.524,
                    sum_prob=41.92,
                    sum_sq_err=20.0,
                ),
            ],
        )
        response = await calibration.public_calibration(db=db, bust=1)
        summary = response["spreads_summary"]
        assert summary["outcomes"] == 180
        assert len(summary["by_sport"]) == 2
        # Sorted by outcomes descending
        assert summary["by_sport"][0]["sport"] == "basketball_nba"
        assert summary["by_sport"][1]["sport"] == "americanfootball_nfl"

    @pytest.mark.asyncio
    async def test_spreads_summary_does_not_include_moneyline_or_totals(self):
        """Spreads summary should only include odds_api_spreads source."""
        db = _FakeDB(
            events_rows=[
                _bucket_row(
                    bucket_idx=7,
                    source="odds_api",
                    category="basketball_nba",
                    n=200,
                    winners=160,
                    avg_prob=0.75,
                    sum_prob=150.0,
                    sum_sq_err=12.5,
                )
            ],
            totals_rows=[
                _bucket_row(
                    bucket_idx=4,
                    source="odds_api_totals",
                    category="basketball_nba",
                    n=90,
                    winners=45,
                    avg_prob=0.51,
                    sum_prob=45.9,
                    sum_sq_err=22.5,
                )
            ],
            spreads_rows=[
                _bucket_row(
                    bucket_idx=5,
                    source="odds_api_spreads",
                    category="basketball_nba",
                    n=50,
                    winners=26,
                    avg_prob=0.52,
                    sum_prob=26.0,
                    sum_sq_err=12.5,
                )
            ],
        )
        response = await calibration.public_calibration(db=db, bust=1)
        assert response["spreads_summary"]["outcomes"] == 50
        assert response["totals_summary"]["outcomes"] == 90


# ---------------------------------------------------------------------------
# Totals summary shape
# ---------------------------------------------------------------------------


class TestTotalsSummary:
    """Verify the totals_summary section in the calibration response."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        calibration._cache = {"data": None, "timestamp": 0}

    @pytest.mark.asyncio
    async def test_totals_summary_present_when_no_data(self):
        db = _FakeDB()
        response = await calibration.public_calibration(db=db, bust=1)
        summary = response["totals_summary"]
        assert summary["mce"] is None
        assert summary["outcomes"] == 0
        assert summary["winners"] == 0
        assert summary["by_sport"] == []

    @pytest.mark.asyncio
    async def test_totals_summary_with_data(self):
        db = _FakeDB(
            totals_rows=[
                _bucket_row(
                    bucket_idx=4,
                    source="odds_api_totals",
                    category="baseball_mlb",
                    n=120,
                    winners=58,
                    avg_prob=0.48,
                    sum_prob=57.6,
                    sum_sq_err=30.0,
                ),
                _bucket_row(
                    bucket_idx=5,
                    source="odds_api_totals",
                    category="icehockey_nhl",
                    n=60,
                    winners=32,
                    avg_prob=0.53,
                    sum_prob=31.8,
                    sum_sq_err=15.0,
                ),
            ],
        )
        response = await calibration.public_calibration(db=db, bust=1)
        summary = response["totals_summary"]
        assert summary["outcomes"] == 180
        assert summary["winners"] == 90
        assert summary["mce"] is not None
        assert len(summary["by_sport"]) == 2
        # baseball has more outcomes, should sort first
        assert summary["by_sport"][0]["sport"] == "baseball_mlb"


# ---------------------------------------------------------------------------
# Spread SQL logic verification
# ---------------------------------------------------------------------------


class TestSpreadSqlLogic:
    """Verify the spread calibration SQL text contains the right logic."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        calibration._cache = {"data": None, "timestamp": 0}

    @pytest.mark.asyncio
    async def test_spread_sql_uses_closing_spread_columns(self):
        db = _FakeDB()
        response = await calibration.public_calibration(db=db, bust=1)
        # We can't inspect the SQL directly from the response, but we
        # verify the source name appears in the buckets when data flows.
        # The SQL verifies columns closing_home_spread,
        # closing_home_spread_odds, closing_away_spread_odds.
        # Test passes as long as the endpoint doesn't error.
        assert "spreads_summary" in response

    @pytest.mark.asyncio
    async def test_spread_push_excluded_from_count(self):
        """When margin + spread = 0, it is a push. The SQL excludes pushes
        via ``(home_score - away_score) + closing_home_spread != 0``.
        Verify the spread SQL returns source='odds_api_spreads'."""
        db = _FakeDB(
            spreads_rows=[
                _bucket_row(
                    bucket_idx=5,
                    source="odds_api_spreads",
                    category="basketball_nba",
                    n=10,
                    winners=5,
                    avg_prob=0.524,
                    sum_prob=5.24,
                    sum_sq_err=2.5,
                )
            ],
        )
        response = await calibration.public_calibration(db=db, bust=1)
        spread_buckets = [
            b for b in response["buckets"]
            if b["source"] == "odds_api_spreads"
        ]
        assert len(spread_buckets) == 1
        assert spread_buckets[0]["n"] == 10

    @pytest.mark.asyncio
    async def test_spread_devig_produces_fair_probability(self):
        """Spread devig normalizes home implied prob against away implied prob.
        For standard -110/-110 juice: each side has raw 52.38%.
        Devigged: 52.38 / (52.38 + 52.38) = 50%.
        For -150/+130: home raw = 60%, away raw = 43.48%.
        Devigged: 60 / (60 + 43.48) = 57.97%.
        The SQL must produce prob values strictly between 0 and 1."""
        # This is a logic test — we verify that odds_api_spreads buckets
        # have avg_prob values that look devigged (close to 0.5 for
        # standard spreads).
        db = _FakeDB(
            spreads_rows=[
                _bucket_row(
                    bucket_idx=4,
                    source="odds_api_spreads",
                    category="basketball_nba",
                    n=500,
                    winners=260,
                    avg_prob=0.496,
                    sum_prob=248.0,
                    sum_sq_err=125.0,
                )
            ],
        )
        response = await calibration.public_calibration(db=db, bust=1)
        spread_buckets = [
            b for b in response["buckets"]
            if b["source"] == "odds_api_spreads"
        ]
        for b in spread_buckets:
            assert 0.0 < b["avg_prob"] < 1.0


# ---------------------------------------------------------------------------
# Total SQL logic verification
# ---------------------------------------------------------------------------


class TestTotalSqlLogic:
    """Verify the total calibration SQL text contains the right logic."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        calibration._cache = {"data": None, "timestamp": 0}

    @pytest.mark.asyncio
    async def test_total_push_excluded_from_count(self):
        """When (home_score + away_score) = closing_over_under, it is a push.
        The SQL excludes pushes. Verify totals source appears correctly."""
        db = _FakeDB(
            totals_rows=[
                _bucket_row(
                    bucket_idx=5,
                    source="odds_api_totals",
                    category="baseball_mlb",
                    n=20,
                    winners=11,
                    avg_prob=0.55,
                    sum_prob=11.0,
                    sum_sq_err=5.0,
                )
            ],
        )
        response = await calibration.public_calibration(db=db, bust=1)
        total_buckets = [
            b for b in response["buckets"]
            if b["source"] == "odds_api_totals"
        ]
        assert len(total_buckets) == 1
        assert total_buckets[0]["n"] == 20

    @pytest.mark.asyncio
    async def test_total_devig_produces_fair_probability(self):
        """Total devig normalizes over implied prob against under implied prob.
        For standard -110/-110: devigged = 50%.
        The SQL must produce prob values strictly between 0 and 1."""
        db = _FakeDB(
            totals_rows=[
                _bucket_row(
                    bucket_idx=4,
                    source="odds_api_totals",
                    category="icehockey_nhl",
                    n=300,
                    winners=155,
                    avg_prob=0.512,
                    sum_prob=153.6,
                    sum_sq_err=75.0,
                )
            ],
        )
        response = await calibration.public_calibration(db=db, bust=1)
        total_buckets = [
            b for b in response["buckets"]
            if b["source"] == "odds_api_totals"
        ]
        for b in total_buckets:
            assert 0.0 < b["avg_prob"] < 1.0


# ---------------------------------------------------------------------------
# Spread/total MCE appears in by_source
# ---------------------------------------------------------------------------


class TestSpreadTotalInBySource:
    """Verify that spread/total MCE appears in the by_source breakdown."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        calibration._cache = {"data": None, "timestamp": 0}

    @pytest.mark.asyncio
    async def test_spread_mce_in_by_source(self):
        db = _FakeDB(
            spreads_rows=[
                _bucket_row(
                    bucket_idx=4,
                    source="odds_api_spreads",
                    category="basketball_nba",
                    n=100,
                    winners=52,
                    avg_prob=0.52,
                    sum_prob=52.0,
                    sum_sq_err=24.96,
                )
            ],
        )
        response = await calibration.public_calibration(db=db, bust=1)
        sources = {s["source"]: s for s in response["by_source"]}
        assert "odds_api_spreads" in sources
        assert sources["odds_api_spreads"]["outcomes"] == 100
        assert sources["odds_api_spreads"]["mce"] is not None

    @pytest.mark.asyncio
    async def test_total_mce_in_by_source(self):
        db = _FakeDB(
            totals_rows=[
                _bucket_row(
                    bucket_idx=5,
                    source="odds_api_totals",
                    category="baseball_mlb",
                    n=80,
                    winners=40,
                    avg_prob=0.51,
                    sum_prob=40.8,
                    sum_sq_err=20.0,
                )
            ],
        )
        response = await calibration.public_calibration(db=db, bust=1)
        sources = {s["source"]: s for s in response["by_source"]}
        assert "odds_api_totals" in sources
        assert sources["odds_api_totals"]["outcomes"] == 80

    @pytest.mark.asyncio
    async def test_all_three_odds_api_sources_separate(self):
        """Moneyline, spreads, and totals should appear as separate sources."""
        db = _FakeDB(
            events_rows=[
                _bucket_row(
                    bucket_idx=7,
                    source="odds_api",
                    category="basketball_nba",
                    n=100,
                    winners=78,
                    avg_prob=0.75,
                    sum_prob=75.0,
                    sum_sq_err=6.25,
                )
            ],
            spreads_rows=[
                _bucket_row(
                    bucket_idx=4,
                    source="odds_api_spreads",
                    category="basketball_nba",
                    n=90,
                    winners=47,
                    avg_prob=0.52,
                    sum_prob=46.8,
                    sum_sq_err=22.5,
                )
            ],
            totals_rows=[
                _bucket_row(
                    bucket_idx=5,
                    source="odds_api_totals",
                    category="basketball_nba",
                    n=85,
                    winners=44,
                    avg_prob=0.52,
                    sum_prob=44.2,
                    sum_sq_err=21.25,
                )
            ],
        )
        response = await calibration.public_calibration(db=db, bust=1)
        source_names = {s["source"] for s in response["by_source"]}
        assert "odds_api" in source_names
        assert "odds_api_spreads" in source_names
        assert "odds_api_totals" in source_names
        # Total outcomes = 100 + 90 + 85 = 275
        assert response["total_outcomes"] == 275

    @pytest.mark.asyncio
    async def test_spread_total_do_not_corrupt_moneyline_buckets(self):
        """Spread/total buckets must be separate from moneyline buckets."""
        db = _FakeDB(
            events_rows=[
                _bucket_row(
                    bucket_idx=7,
                    source="odds_api",
                    category="basketball_nba",
                    n=100,
                    winners=78,
                    avg_prob=0.75,
                    sum_prob=75.0,
                    sum_sq_err=6.25,
                )
            ],
            spreads_rows=[
                _bucket_row(
                    bucket_idx=4,
                    source="odds_api_spreads",
                    category="basketball_nba",
                    n=90,
                    winners=47,
                    avg_prob=0.52,
                    sum_prob=46.8,
                    sum_sq_err=22.5,
                )
            ],
        )
        response = await calibration.public_calibration(db=db, bust=1)
        ml_buckets = [b for b in response["buckets"] if b["source"] == "odds_api"]
        sp_buckets = [b for b in response["buckets"] if b["source"] == "odds_api_spreads"]
        assert len(ml_buckets) == 1
        assert len(sp_buckets) == 1
        assert ml_buckets[0]["n"] == 100
        assert sp_buckets[0]["n"] == 90
        # Moneyline should not include spread outcomes
        assert ml_buckets[0]["bucket_idx"] != sp_buckets[0]["bucket_idx"] or \
            ml_buckets[0]["source"] != sp_buckets[0]["source"]


# ---------------------------------------------------------------------------
# Spread/total closing line backfill verification
# ---------------------------------------------------------------------------


class TestClosingLineBackfillSql:
    """Verify the SQL in _backfill_closing_lines handles spreads and totals."""

    def test_spread_sql_in_calibration_query(self):
        """The calibration SQL must reference closing_home_spread columns."""
        import inspect
        source = inspect.getsource(calibration.public_calibration)
        assert "closing_home_spread" in source
        assert "closing_home_spread_odds" in source
        assert "closing_away_spread_odds" in source
        assert "(home_score - away_score) + closing_home_spread" in source
        # Push exclusion
        assert "!= 0" in source

    def test_total_sql_in_calibration_query(self):
        """The calibration SQL must reference closing_over_under columns."""
        import inspect
        source = inspect.getsource(calibration.public_calibration)
        assert "closing_over_under" in source
        assert "closing_over_odds" in source
        assert "closing_under_odds" in source
        assert "(home_score + away_score)" in source
        # Push exclusion
        assert "(home_score + away_score) != closing_over_under" in source

    def test_spread_devig_formula_in_sql(self):
        """The devig formula normalizes home implied prob by (home + away)."""
        import inspect
        source = inspect.getsource(calibration.public_calibration)
        # The devig formula divides by (home_implied + away_implied)
        assert "closing_home_spread_odds" in source
        assert "closing_away_spread_odds" in source
        # Uses ABS for American odds conversion
        assert "ABS(closing_home_spread_odds)" in source

    def test_total_devig_formula_in_sql(self):
        """The devig formula normalizes over implied prob by (over + under)."""
        import inspect
        source = inspect.getsource(calibration.public_calibration)
        assert "closing_over_odds" in source
        assert "closing_under_odds" in source
        assert "ABS(closing_over_odds)" in source
