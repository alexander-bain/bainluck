"""Guards for the Polymarket trading-evidence contract (#1870, CAL-P060).

Every test here is written to FAIL ON REVERT of a specific line, not to
describe the module. The defect being guarded is subtle and reads as correct:
"the venue returned no trades, so record zero trading" is a sentence nobody
challenges in review, and it is exactly wrong for a market the venue has
purged. That sentence shipped once on the Kalshi trade backfill and was
recorded as a SUCCESS every 6h for ten weeks (gotcha #53). These tests exist so
it cannot ship a second time on the Polymarket path.
"""

from datetime import date, datetime, timezone

import pytest

from app.utils.polymarket_evidence import (
    GAMMA_MARKETS_MAX_OFFSET,
    PM_ADDRESSABLE_FROM,
    PM_BOUNDARY_MEASURED_ON,
    PM_SWEEP_FLOOR,
    PM_UNADDRESSABLE_THROUGH,
    PMEvidence,
    build_evidence_receipt,
    classify_pm_evidence,
    volume_to_write,
)


class TestEmpty200IsNotAbsence:
    """The core of gotcha #53: same response body, two different facts."""

    def test_purged_and_untraded_send_byte_identical_trade_bodies(self):
        """Measured 2026-08-14: both return HTTP 200 with ``[]``.

        This is the whole reason existence must be consulted. If this test ever
        starts failing because the two inputs produce the same verdict, the
        classifier has stopped distinguishing them.
        """
        purged = classify_pm_evidence(clob_status=404, trades=[])
        untraded = classify_pm_evidence(clob_status=200, trades=[])

        # Identical activity signal...
        assert purged is PMEvidence.UNADDRESSABLE
        assert untraded is PMEvidence.CONFIRMED_ZERO
        # ...opposite verdicts. Collapsing these is the defect.
        assert purged is not untraded

    def test_unaddressable_never_writes_a_zero(self):
        """FAILS ON REVERT of the ``clob_status == 404`` early return.

        Writing 0 here would state, in the database, that Polymarket confirmed
        nobody traded a market Polymarket will not even acknowledge exists.
        """
        assert volume_to_write(PMEvidence.UNADDRESSABLE) is None

    def test_confirmed_zero_writes_a_real_zero_not_a_null(self):
        """FAILS ON REVERT of the CONFIRMED_ZERO branch.

        The 0 is the entire fix. Polymarket had 0.00% of these; Kalshi had
        5.08%. If this returns None the column goes back to meaning two things.
        """
        assert volume_to_write(PMEvidence.CONFIRMED_ZERO) == 0


class TestExistenceIsCheckedBeforeActivity:
    def test_ordering_is_load_bearing(self):
        """A 404 wins even when the activity signal is fully populated.

        Guards against a refactor that checks ``trades`` first for speed. If
        existence stopped being consulted first, a purged market that happens
        to have stale indexed trades would be classified from the wrong signal.
        """
        assert (
            classify_pm_evidence(clob_status=404, trades=[{"size": 1}] * 5)
            is PMEvidence.UNADDRESSABLE
        )

    @pytest.mark.parametrize("status", [429, 500, 502, 503, None])
    def test_rate_limits_and_errors_are_never_facts(self, status):
        """Gotcha #36: a 429 must never be indistinguishable from 'not found'.

        The Kalshi backfill "decelerated" for weeks because a catch-all turned
        rate limits into absences. Same failure, different venue.
        """
        assert (
            classify_pm_evidence(clob_status=status, trades=[])
            is PMEvidence.INDETERMINATE
        )
        assert volume_to_write(PMEvidence.INDETERMINATE) is None

    def test_incomplete_trade_call_on_a_live_market_is_indeterminate(self):
        """Addressable, but the activity call never completed.

        ``trades=None`` is not ``trades=[]``. Treating them alike would invent
        a confirmed zero out of a timeout.
        """
        assert (
            classify_pm_evidence(clob_status=200, trades=None)
            is PMEvidence.INDETERMINATE
        )


class TestTradedDetection:
    def test_trades_present_means_traded(self):
        assert (
            classify_pm_evidence(clob_status=200, trades=[{"size": 1}])
            is PMEvidence.TRADED
        )

    def test_authoritative_volume_settles_it_without_trades(self):
        """gamma/events/{id} volume outranks an empty trade page.

        Measured: event 10446's sub-markets carry volumes of 405 and 546 while
        the paged backfill left them NULL. A positive authoritative figure is a
        fact; an empty trade page under it would be a pagination artifact.
        """
        assert (
            classify_pm_evidence(clob_status=200, trades=[], gamma_volume=405.0)
            is PMEvidence.TRADED
        )

    def test_zero_authoritative_volume_does_not_override_existence(self):
        assert (
            classify_pm_evidence(clob_status=404, trades=[], gamma_volume=0.0)
            is PMEvidence.UNADDRESSABLE
        )

    def test_traded_volume_is_clamped_to_the_integer_column(self):
        assert volume_to_write(PMEvidence.TRADED, 9_999_999_999.0) == 2_000_000_000
        assert volume_to_write(PMEvidence.TRADED, 405.9) == 405


class TestReceiptDisambiguatesNull:
    """NULL means 'never asked' ONLY because the receipt carries the rest."""

    def test_receipt_stamps_when_we_asked(self):
        ts = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
        r = build_evidence_receipt(PMEvidence.CONFIRMED_ZERO, n_trades=0, fetched_at=ts)
        assert r["verdict"] == "confirmed_zero"
        assert r["fetched_at"] == ts.isoformat()
        assert r["n_trades"] == 0

    def test_unaddressable_receipt_says_why_the_null_is_permanent(self):
        """FAILS ON REVERT of the ``reason`` branch.

        A successor reading a NULL must be able to tell "pending" from
        "impossible" without re-probing the venue. That is the difference
        between a queue item and a closed finding.
        """
        r = build_evidence_receipt(PMEvidence.UNADDRESSABLE)
        assert r["verdict"] == "unaddressable"
        assert "not zero" in r["reason"].lower()

    def test_every_verdict_produces_a_receipt_with_a_timestamp(self):
        for ev in PMEvidence:
            r = build_evidence_receipt(ev)
            assert r["verdict"] == ev.value
            assert r["fetched_at"]
            assert r["boundary_measured_on"] == PM_BOUNDARY_MEASURED_ON.isoformat()


class TestMeasuredConstantsAreCoherent:
    """Gotcha #35: a predicate cannot consume a range written in prose.

    These do not re-probe the venue (that is
    ``scripts/probe_polymarket_retention.py``). They assert the constants stay
    internally consistent, so a careless edit to one cannot silently invert the
    sweep's floor.
    """

    def test_the_boundary_is_an_interval_not_a_guessed_day(self):
        assert PM_UNADDRESSABLE_THROUGH < PM_ADDRESSABLE_FROM

    def test_the_sweep_floor_excludes_the_measured_dead_cohort(self):
        assert PM_SWEEP_FLOOR == PM_UNADDRESSABLE_THROUGH
        assert PM_SWEEP_FLOOR < PM_ADDRESSABLE_FROM

    def test_the_boundary_carries_its_measurement_date(self):
        """An undated retention bound is the thing gotcha #35 forbids."""
        assert isinstance(PM_BOUNDARY_MEASURED_ON, date)
        assert PM_BOUNDARY_MEASURED_ON >= date(2026, 8, 14)

    def test_the_offset_cap_is_recorded(self):
        """offset=2000 -> 200, offset=2050 -> 422, measured 2026-08-14.

        This constant is why the recovery rail addresses events by id instead
        of paging /markets. If someone raises it without re-probing, the paging
        rail silently 422s again.
        """
        assert GAMMA_MARKETS_MAX_OFFSET == 2000
