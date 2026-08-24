"""CAL-P008 (#683) — the Kalshi trade backfill must spend its budget on data that exists.

The production run this pins was measured on 2026-08-07:

    {"candidates": 500, "fetched": 500, "pregame_snaps": 0, "no_pregame": 0,
     "api_empty": 500, "trade_pages": 500, "errors": []}
    last_verdict: "unverified"  (recorded as a SUCCESS)

Every one of those 500 markets had been purged by Kalshi. The rail walked
oldest-id-first into a tail of ~150K permanently dead rows, tagged none of them
(so they stayed candidates forever), created zero snapshots, and reported healthy
every six hours while #683 stayed open as a P0.

Three defects are pinned here:
  1. no retention bound on the candidate set — the budget could never reach the
     rows that still have data, and those rows have a deadline;
  2. the ``no_pregame_trading`` write had no authority guard, so a capture-side
     observation could overwrite a cited settlement;
  3. the summary carried no terminal, so a 100%-waste run classified as a legacy
     "it returned, so it ran" success.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.kalshi import _backfill_trade_history, _trade_backfill_terminal
from app.utils import task_verdict
from app.utils.kalshi_retention import (
    AT_RISK_AGE_DAYS,
    OBSERVED_PRESENT_MAX_AGE_DAYS,
    OBSERVED_PURGED_MIN_AGE_DAYS,
    OBSERVED_PURGED_MIN_AGE_DAYS_ANY_SERIES,
    PROVABLY_PURGED_AGE_DAYS,
    days_until_purge,
    is_at_risk,
    is_provably_purged,
    recovery_window_start,
)
from app.utils.resolution_authority import (
    OVERWRITABLE_WINNER_SOURCES,
    authority_tier,
)

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def _aged(days: float) -> datetime:
    return NOW - timedelta(days=days)


class TestRetentionBounds:
    """The horizon is a measurement, and the two bounds are used for opposite jobs."""

    def test_bounds_bracket_the_measured_cliff(self):
        # 2026-05-25 (74d) was still present; 2026-05-13 (86d) was already 404.
        assert OBSERVED_PRESENT_MAX_AGE_DAYS < OBSERVED_PURGED_MIN_AGE_DAYS

    def test_skip_work_stays_conservative_and_warning_stays_eager(self):
        """The two jobs, asserted as jobs rather than as a pair of numbers.

        2026-08-24: the warning bound used to be ``OBSERVED_PRESENT_MAX_AGE_DAYS``
        (74). C-KALSHI-RETENTION-1 confirmed purges from 47 days, so that alarm
        rang 27 days after the data was already gone — an eager bound in name only.
        The warning is now anchored to the youngest CONFIRMED purge; the skip-work
        bound is untouched, because every definitive read at 85-86d was purged and
        refusing to spend a call there is still fail-open.
        """
        # Skipping must be conservative: only refuse what is provably gone.
        assert PROVABLY_PURGED_AGE_DAYS == OBSERVED_PURGED_MIN_AGE_DAYS
        # Warning must be eager: fire at the first CONFIRMED loss, not after it.
        assert AT_RISK_AGE_DAYS == OBSERVED_PURGED_MIN_AGE_DAYS_ANY_SERIES
        assert AT_RISK_AGE_DAYS < PROVABLY_PURGED_AGE_DAYS
        # And the survivor observation no longer drives either job.
        assert AT_RISK_AGE_DAYS != OBSERVED_PRESENT_MAX_AGE_DAYS

    @pytest.mark.parametrize(
        "age_days,expected",
        [
            (154, True),   # 2026-03-07 — measured 404
            (87, True),    # 2026-05-13 — measured 404
            (86, True),    # the bound itself
            (80, False),   # inside the uncertain band: still attempted
            (74, False),   # 2026-05-25 — measured present
            (41, False),   # 2026-06-27 — measured present
            (0, False),
        ],
    )
    def test_is_provably_purged(self, age_days, expected):
        assert is_provably_purged(_aged(age_days), NOW) is expected

    def test_unknown_settlement_fails_open(self):
        """A row with no date must still be attempted, never written off."""
        assert is_provably_purged(None, NOW) is False
        assert days_until_purge(None, NOW) is None
        assert is_at_risk(None, NOW) is False

    def test_naive_datetimes_are_treated_as_utc(self):
        naive = datetime(2026, 3, 7, 12, 0)
        assert is_provably_purged(naive, NOW) is True

    def test_recovery_window_start_matches_the_skip_bound(self):
        assert recovery_window_start(NOW) == NOW - timedelta(days=PROVABLY_PURGED_AGE_DAYS)


class TestAtRiskWarning:
    """The early warning has to fire BEFORE the loss, and stop after it."""

    def test_fires_inside_the_last_fortnight_of_the_window(self):
        assert is_at_risk(_aged(AT_RISK_AGE_DAYS - 3), NOW) is True

    def test_silent_when_there_is_plenty_of_time(self):
        assert is_at_risk(_aged(10), NOW) is False

    def test_already_purged_rows_are_not_at_risk(self):
        """Nothing left to lose — counting these would drown the real signal."""
        assert is_at_risk(_aged(154), NOW) is False
        assert is_at_risk(_aged(PROVABLY_PURGED_AGE_DAYS + 1), NOW) is False

    def test_the_uncertain_band_still_counts_as_at_risk(self):
        assert is_at_risk(_aged(OBSERVED_PRESENT_MAX_AGE_DAYS + 4), NOW) is True

    def test_days_until_purge_goes_negative_past_the_window(self):
        assert days_until_purge(_aged(AT_RISK_AGE_DAYS + 10), NOW) == pytest.approx(-10)


class TestTerminalContract:
    """A run that banked nothing must be able to say so."""

    def test_the_measured_production_run_is_a_failure(self):
        """The exact 2026-08-07 summary. This is the shape that read healthy."""
        observed = {
            "candidates": 500, "fetched": 500, "pregame_snaps": 0,
            "no_pregame": 0, "api_empty": 500, "trade_pages": 500, "errors": [],
        }
        assert _trade_backfill_terminal(observed) == "failed"

    def test_drained_backlog_is_complete_not_a_no_op(self):
        assert _trade_backfill_terminal({"candidates": 0, "fetched": 0}) == "complete"

    def test_budget_stopped_before_any_fetch_is_partial(self):
        assert _trade_backfill_terminal({"candidates": 500, "fetched": 0}) == "partial"

    def test_truncated_mid_batch_is_partial(self):
        assert _trade_backfill_terminal(
            {"candidates": 500, "fetched": 200, "pregame_snaps": 40, "api_empty": 10}
        ) == "partial"

    def test_full_batch_with_snapshots_is_complete(self):
        assert _trade_backfill_terminal(
            {"candidates": 500, "fetched": 500, "pregame_snaps": 120, "api_empty": 380}
        ) == "complete"

    def test_all_empty_but_genuinely_untraded_markets_are_not_a_failure(self):
        """Markets that EXIST and simply never traded are real information.

        Only the all-empty case is a failure; `no_pregame` means the market was
        found and answered, which is a completed unit of work.
        """
        assert _trade_backfill_terminal(
            {"candidates": 300, "fetched": 300, "pregame_snaps": 0,
             "no_pregame": 300, "api_empty": 0}
        ) == "complete"


class TestVerdictIsNowEnforced:
    """Without enforcement the terminal is computed and then thrown away."""

    def test_kalshi_trades_is_enforced(self):
        assert "kalshi_trades" in task_verdict.ENFORCED_TASKS

    def test_the_measured_run_now_reads_red_authoritatively(self):
        observed = {
            "candidates": 500, "fetched": 500, "pregame_snaps": 0,
            "no_pregame": 0, "api_empty": 500, "trade_pages": 500, "errors": [],
        }
        # Terminal derived by the task's own classifier, not hardcoded, so this
        # covers the whole chain: summary -> terminal -> verdict -> health.
        observed["terminal"] = _trade_backfill_terminal(observed)
        verdict = task_verdict.verdict_for("kalshi_trades", observed)
        assert verdict.verdict == task_verdict.FAILED
        assert verdict.authoritative is True

    def test_before_the_fix_the_same_run_read_as_a_legacy_success(self):
        """Non-vacuity: strip the terminal and the old false-GREEN path returns."""
        legacy = {
            "candidates": 500, "fetched": 500, "pregame_snaps": 0,
            "no_pregame": 0, "api_empty": 500, "trade_pages": 500, "errors": [],
        }
        assert task_verdict.classify_summary(legacy).verdict == task_verdict.UNKNOWN

    def test_a_healthy_run_still_reads_green(self):
        healthy = {
            "candidates": 500, "fetched": 500, "pregame_snaps": 120,
            "api_empty": 380, "errors": [], "terminal": "complete",
        }
        assert task_verdict.verdict_for("kalshi_trades", healthy).verdict == (
            task_verdict.COMPLETE
        )


class TestCandidateQueryIsBoundedToTheRecoverableWindow:
    """The predicate is the fix; pin it at source level like the sibling suites."""

    SRC = inspect.getsource(_backfill_trade_history)

    def test_candidate_sql_bounds_on_the_purge_horizon(self):
        assert "make_interval(days => :purge_days)" in self.SRC
        assert "purge_days" in self.SRC

    def test_the_bound_comes_from_the_measured_constant(self):
        assert "PROVABLY_PURGED_AGE_DAYS" in self.SRC

    def test_null_settlement_is_still_a_candidate(self):
        """Fail-open: a dateless row must not be silently abandoned."""
        assert "IS NULL\n                           OR COALESCE" in self.SRC

    def test_the_run_reports_how_much_is_about_to_expire(self):
        assert '"expiring_soon"' in self.SRC
        assert "is_at_risk" in self.SRC


class TestNoPregameWriteCannotDowngradeAuthority:
    """A capture-side observation must never overwrite a cited settlement."""

    SRC = inspect.getsource(_backfill_trade_history)

    def test_the_update_is_guarded(self):
        assert "OVERWRITABLE_WINNER_SOURCES_SQL" in self.SRC
        guarded = self.SRC.split("SET resolution_source = 'no_pregame_trading'")[1]
        assert "resolution_source IS NULL" in guarded
        assert "OVERWRITABLE_WINNER_SOURCES_SQL" in guarded

    def test_the_guard_is_not_vacuous(self):
        """The allowlist must actually exclude the tiers it claims to protect."""
        assert "api_settlement" not in OVERWRITABLE_WINNER_SOURCES
        assert "box_score" not in OVERWRITABLE_WINNER_SOURCES
        for source in OVERWRITABLE_WINNER_SOURCES:
            assert authority_tier(source) <= authority_tier("no_pregame_trading")


class TestProbeShipsWithTheConstant:
    """The horizon is only honest if anyone can re-measure it."""

    def test_ticker_dates_parse(self):
        from scripts.probe_kalshi_retention import age_from_ticker

        # A purged market 404s, so its age can only come from its own ticker.
        assert age_from_ticker("KXNCAAMBSPREAD-26MAR07CINTCU-CIN7") > 150
        assert age_from_ticker("KXHIGHTBOS-26JUN27-T74") > 30

    def test_unparseable_tickers_return_none_rather_than_guessing(self):
        from scripts.probe_kalshi_retention import age_from_ticker

        assert age_from_ticker("KXNBAWINS-UTA-25-T5") is None
        assert age_from_ticker("KXFOO-26XXX99-BAR") is None
