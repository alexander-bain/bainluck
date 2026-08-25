"""CAL-P061 (#1868) — the resolution-date provenance split.

These tests encode the four live measurements from 2026-08-14 (n=311, stratified
category x age band, all 78 strata sampled, 100% population coverage) as
specimens, so a regression has to disagree with the venue rather than merely with
an opinion.

The load-bearing assertions are the ones about what a verdict does NOT do. The
issue's own closing note is the design constraint — *"a wrong date on a graded row
is a two-variable problem and moving one silently is how #1852 happened"* — so
every arm is tested for the write it must refuse as well as the write it makes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.kalshi_retention import AT_RISK_AGE_DAYS, PROVABLY_PURGED_AGE_DAYS
from app.utils.kalshi_resolution_date_provenance import (
    REPAIRABLE_VERDICTS,
    VERDICT_CONSISTENT,
    VERDICT_FABRICATED_LOSS_REFERRAL,
    VERDICT_PREMATURE_GRADE,
    VERDICT_STALE_RESOLUTION_DATE,
    VERDICT_UNADDRESSABLE,
    VenueEvidence,
    VenueLeg,
    banding_shift,
    classify_provenance,
    days_until_at_risk,
    retention_band,
)

# A fixed clock. Never derived from the wall clock, and no branch anywhere picks
# it — gotcha #44's rule, and the reason this file cannot go red in the evening.
NOW = datetime(2026, 8, 14, 18, 0, tzinfo=timezone.utc)


def _ev(**kw) -> VenueEvidence:
    kw.setdefault("ticker", "KXTEST-26")
    kw.setdefault("answered", True)
    return VenueEvidence(**kw)


# ---------------------------------------------------------------------------
# The dominant arm: 90.5% of the population
# ---------------------------------------------------------------------------


def test_active_unsettled_market_is_a_premature_grade_not_a_date_bug():
    """242/311 sampled markets: venue 'active', result ''. We graded all-losers."""
    v = classify_provenance(
        evidence=_ev(legs=(VenueLeg("active", ""), VenueLeg("active", ""))),
        stored_resolution_date=NOW + timedelta(days=900),
        now=NOW,
    )
    assert v.verdict == VERDICT_PREMATURE_GRADE
    # THE POINT: the date is not touched on this arm. The market genuinely has
    # not resolved, so a future-dated resolution_date is defensible; the grade is
    # the defect. Emitting a date correction here would be the two-variable move.
    assert v.corrected_resolution_date is None
    assert v.true_retention_band is None


def test_premature_grade_survives_a_wildly_wrong_stored_date():
    """Even an absurd stored date must not convert this into the date arm."""
    for ahead in (1, 400, 3842):
        v = classify_provenance(
            evidence=_ev(legs=(VenueLeg("active", ""),)),
            stored_resolution_date=NOW + timedelta(days=ahead),
            now=NOW,
        )
        assert v.verdict == VERDICT_PREMATURE_GRADE
        assert v.corrected_resolution_date is None


# ---------------------------------------------------------------------------
# The date arm: 9.5% of the population
# ---------------------------------------------------------------------------


def test_settled_market_with_a_later_stored_date_is_the_date_arm():
    settled = NOW - timedelta(days=13, hours=7)
    v = classify_provenance(
        evidence=_ev(
            legs=(VenueLeg("finalized", "no"), VenueLeg("finalized", "no")),
            settlement_ts=settled,
        ),
        stored_resolution_date=NOW + timedelta(days=44),
        now=NOW,
    )
    assert v.verdict == VERDICT_STALE_RESOLUTION_DATE
    assert v.corrected_resolution_date == settled
    assert v.error_days == pytest.approx(57.29, abs=0.05)
    # Corrected age is ~13.3d -> reachable, which is the operational finding:
    # the row is actionable TODAY and the wrong date is what hides it.
    assert v.true_retention_band == "reachable"


def test_date_arm_never_reaches_a_market_the_venue_says_someone_won():
    """36.8% of the settled subset names a winner. That is #1852's rail, not ours."""
    v = classify_provenance(
        evidence=_ev(
            legs=(VenueLeg("finalized", "yes"), VenueLeg("finalized", "no")),
            settlement_ts=NOW - timedelta(days=10),
        ),
        stored_resolution_date=NOW + timedelta(days=200),
        now=NOW,
    )
    assert v.verdict == VERDICT_FABRICATED_LOSS_REFERRAL
    # A referral must not carry a repair of its own, or the attended apply would
    # move the date on a row whose grade is about to change underneath it.
    assert v.corrected_resolution_date is None
    assert v.verdict not in REPAIRABLE_VERDICTS


@pytest.mark.parametrize("bad_result", ["", "scalar", "SCALAR", None, "  "])
def test_unmappable_results_are_not_read_as_a_winner(bad_result):
    """CAL-P053's three-state rule, enforced here too: '' and 'scalar' != loser."""
    v = classify_provenance(
        evidence=_ev(
            legs=(VenueLeg("finalized", bad_result or ""),),
            settlement_ts=NOW - timedelta(days=5),
        ),
        stored_resolution_date=NOW + timedelta(days=30),
        now=NOW,
    )
    assert v.verdict == VERDICT_STALE_RESOLUTION_DATE


def test_stored_date_at_or_before_settlement_is_consistent():
    settled = NOW - timedelta(days=5)
    for stored in (settled, settled - timedelta(days=1)):
        v = classify_provenance(
            evidence=_ev(legs=(VenueLeg("finalized", "no"),), settlement_ts=settled),
            stored_resolution_date=stored,
            now=NOW,
        )
        assert v.verdict == VERDICT_CONSISTENT
        assert v.corrected_resolution_date is None


# ---------------------------------------------------------------------------
# The absence rules (gotcha #53)
# ---------------------------------------------------------------------------


def test_empty_venue_answer_is_unaddressable_never_never_settled():
    v = classify_provenance(
        evidence=_ev(answered=False),
        stored_resolution_date=NOW + timedelta(days=100),
        now=NOW,
    )
    assert v.verdict == VERDICT_UNADDRESSABLE
    assert v.verdict not in REPAIRABLE_VERDICTS
    assert v.corrected_resolution_date is None
    # An unaddressable row must NOT be reported as a premature grade: purged and
    # never-settled share a response shape, and only one of them is our defect.
    assert v.verdict != VERDICT_PREMATURE_GRADE


def test_terminal_but_unstamped_invents_no_date():
    """A closed-awaiting-settlement market is real. Do not derive a date from a status."""
    v = classify_provenance(
        evidence=_ev(legs=(VenueLeg("closed", ""),), settlement_ts=None),
        stored_resolution_date=NOW + timedelta(days=60),
        now=NOW,
    )
    assert v.verdict == VERDICT_CONSISTENT
    assert v.corrected_resolution_date is None


# ---------------------------------------------------------------------------
# The cross-product bug this module was refactored to make unrepresentable
# ---------------------------------------------------------------------------


def test_winner_detection_uses_real_legs_not_a_status_result_cross_product():
    """('active','') + ('finalized','no') must NOT synthesise ('finalized','yes')."""
    ev = _ev(legs=(VenueLeg("active", ""), VenueLeg("finalized", "no")))
    assert ev.names_a_winner is False
    ev2 = _ev(legs=(VenueLeg("active", "yes"), VenueLeg("finalized", "no")))
    # 'active' carries no declared result, so this is still not a winner.
    assert ev2.names_a_winner is False
    ev3 = _ev(legs=(VenueLeg("finalized", "yes"),))
    assert ev3.names_a_winner is True


# ---------------------------------------------------------------------------
# Retention banding (item 4)
# ---------------------------------------------------------------------------


def test_retention_band_uses_the_measured_constants():
    """The boundary is the CONSTANT, and the constant is the measurement.

    2026-08-24 (C-KALSHI-RETENTION-1, BLOCK): this test used to pin the lower edge at
    a literal 74 — ``OBSERVED_PRESENT_MAX_AGE_DAYS``, which the re-measurement proved
    is a *survivor observation* and not a floor. Confirmed purges start at **47** days,
    so a 73.9-day row is already ``at_risk`` and every assertion below the old edge was
    asserting the opposite of the truth.

    Two halves on purpose. Reading the boundary from the constant is what stops the
    test rotting the next time the probe re-measures; pinning the constant to the
    measured literal is what stops it going vacuous, which a constants-only test
    would (it would pass for any value at all, including the 74 that was wrong).
    """
    # Half 1 — the constants ARE the measurement. Change these only with a probe run.
    assert AT_RISK_AGE_DAYS == 47, "youngest CONFIRMED purge, C-KALSHI-RETENTION-1"
    assert PROVABLY_PURGED_AGE_DAYS == 86, "upper skip-work bound; not refuted"

    # Half 2 — the banding logic reads the constants and gets both edges right.
    assert retention_band(0) == "reachable"
    assert retention_band(AT_RISK_AGE_DAYS - 0.1) == "reachable"
    assert retention_band(AT_RISK_AGE_DAYS) == "at_risk"
    assert retention_band(PROVABLY_PURGED_AGE_DAYS - 0.1) == "at_risk"
    assert retention_band(PROVABLY_PURGED_AGE_DAYS) == "provably_purged"
    assert retention_band(1287) == "provably_purged"

    # The specimen that broke the old shape: 68d got the purge response from
    # KXITFMATCH-26JUN14FONSZA while a 74d sibling was still fully present.
    # Non-monotonic retention means this row must NOT read as reachable.
    assert retention_band(68) == "at_risk"


def test_banding_shift_counts_the_operational_picture():
    settled_recent = classify_provenance(
        evidence=_ev(legs=(VenueLeg("finalized", "no"),), settlement_ts=NOW - timedelta(days=13)),
        stored_resolution_date=NOW + timedelta(days=44),
        now=NOW,
    )
    premature = classify_provenance(
        evidence=_ev(legs=(VenueLeg("active", ""),)),
        stored_resolution_date=NOW + timedelta(days=900),
        now=NOW,
    )
    shift = banding_shift([settled_recent, premature])
    assert shift["reachable"] == 1
    # The premature arm has no true band, and must not be silently counted as
    # reachable — that would overstate how much work the repair unlocks.
    assert shift["no_band"] == 1
    assert shift["provably_purged"] == 0


def test_days_until_at_risk_warns_before_the_loss():
    """The warning line moved 74 -> 47, and this specimen moved with it.

    2026-08-24: the old assertion read ``remaining == approx(8.1)`` and
    ``0 < remaining < 74`` on the sample's oldest row (65.9d), i.e. it claimed eight
    days of headroom. Against the measured 47-day confirmed-purge line that row is
    **18.9 days PAST** the warning, and the old test would have kept certifying
    headroom that does not exist — the exact failure mode the re-measurement was run
    to find. Both directions are asserted now, because "warns before the loss" is a
    claim about the pre-warning case and the old test only ever exercised one row.
    """
    # The sample's oldest row: already past the line, and the sign says so.
    late = classify_provenance(
        evidence=_ev(legs=(VenueLeg("finalized", "no"),), settlement_ts=NOW - timedelta(days=65.9)),
        stored_resolution_date=NOW + timedelta(days=10),
        now=NOW,
    )
    remaining_late = days_until_at_risk(late, NOW)
    assert remaining_late == pytest.approx(AT_RISK_AGE_DAYS - 65.9, abs=0.05)
    assert remaining_late < 0, "a row past the warning line must report negative headroom"

    # A genuinely pre-warning row: the warning still precedes the loss, which is the
    # property this test is named for and the old specimen no longer demonstrated.
    early = classify_provenance(
        evidence=_ev(legs=(VenueLeg("finalized", "no"),), settlement_ts=NOW - timedelta(days=40)),
        stored_resolution_date=NOW + timedelta(days=10),
        now=NOW,
    )
    remaining_early = days_until_at_risk(early, NOW)
    assert remaining_early == pytest.approx(AT_RISK_AGE_DAYS - 40, abs=0.05)
    assert 0 < remaining_early < PROVABLY_PURGED_AGE_DAYS


def test_days_until_at_risk_is_none_without_a_correction():
    v = classify_provenance(
        evidence=_ev(legs=(VenueLeg("active", ""),)),
        stored_resolution_date=NOW + timedelta(days=5),
        now=NOW,
    )
    assert days_until_at_risk(v, NOW) is None
