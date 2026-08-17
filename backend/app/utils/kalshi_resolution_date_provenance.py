"""Split the #1868 population by WHICH defect it has, from venue evidence. Pure.

CAL-P061. 3,928 Kalshi markets carry an all-loser grade at ``api_settlement``
authority — the top rung, which nothing may later overwrite — while their stored
``resolution_date`` is still in the future. #1868 posed two readings and said they
need different fixes. Measured live on 2026-08-14 (n=311, stratified category x
band, all 78 strata sampled, 100% population coverage), **both are real** and the
split is lopsided:

    PREMATURE GRADE   venue still 'active', result ''     ~3,554   90.5%
    WRONG DATE        venue settled, stored date later      ~373    9.5%
    unaddressable                                              1    0.0%

WHY THE DATE IS WRONG, NAMED BY MEASUREMENT, NOT BY CODE READING. The poller
writes ``resolution_date = max(expiration_time)`` over the event's sub-markets
(``app/tasks/kalshi.py:801,820`` <- ``app/services/kalshi_api.py:1173``). Our
stored value reproduces the venue's ``max(expiration_time)`` **310/310 = 100.0%**
exactly. But for a market that ``can_close_early`` — 99.7% of the sample —
``expiration_time`` equals ``latest_expiration_time``: it is the LATEST POSSIBLE
expiry, a backstop, not a schedule. Taking ``max()`` across sub-markets then makes
it a max of backstops. Against real settlement the stored date is late in 68/68
cases: median 57.8 days, p90 363.8, max 1,287.

``settlement_ts`` — the truth — is on the SAME payload and is read by zero lines of
our code. So is ``expected_expiration_time``. Neither exists on ``KalshiMarket``.

THE TWO ARMS MUST NEVER FIRE TOGETHER. #1868's closing note is the design
constraint: *"a wrong date on a graded row is a two-variable problem and moving one
silently is how #1852 happened."* A premature grade and a stale date are different
defects with different evidence and different blast radii, so this module refuses
to emit a verdict that changes both. :func:`classify_provenance` returns exactly
one disposition per market, and the date arm is defined only where the grade is
already correct.

Pure module: no DB, no network, no clock injected implicitly. ``now`` is always a
parameter, so a test can never be made green or red by the wall clock (gotcha #44).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.utils.kalshi_market_status import gradeable_winner, is_terminal
from app.utils.kalshi_retention import (
    AT_RISK_AGE_DAYS,
    PROVABLY_PURGED_AGE_DAYS,
)

# --------------------------------------------------------------------------
# Verdicts. Each names WHAT IS WRONG, never a bare severity, so the disposition
# is readable from the verdict alone.
# --------------------------------------------------------------------------

#: Venue has not settled this market at all — no terminal sub-market, no result.
#: We nonetheless wrote every leg a loser at ``api_settlement``. The GRADE is the
#: defect; the future-dated ``resolution_date`` is arguably correct, because the
#: market genuinely has not resolved. Repair = RETRACT the grade. Never touch the
#: date on this arm.
VERDICT_PREMATURE_GRADE = "PREMATURE_GRADE"

#: Venue settled, and did so BEFORE the date we store. The GRADE's timing is
#: defensible; the DATE is the defect. Repair = correct ``resolution_date`` to the
#: venue's ``settlement_ts``. Never touch ``is_winner`` on this arm.
VERDICT_STALE_RESOLUTION_DATE = "STALE_RESOLUTION_DATE"

#: Venue settled AND names a real winner, while we hold all-losers. This is the
#: #1852 fabricated-loss class, not a date question. Measured at 25/68 = 36.8% of
#: the settled subset. Repair is NOT ours: hand off to the kalshi-fabricated-loss
#: rail, which already compare-and-sets per leg. Emitting a date fix here would be
#: the two-variable move the issue forbids.
VERDICT_FABRICATED_LOSS_REFERRAL = "FABRICATED_LOSS_REFERRAL"

#: 200 with an empty market list. NOT "never settled" — it is the retention cliff
#: wearing the same response shape (gotcha #53). No verdict is derivable; the row
#: is left exactly as it is and counted separately so a zero-yield run cannot be
#: read as a clean one.
VERDICT_UNADDRESSABLE = "UNADDRESSABLE"

#: Venue evidence agrees with what we hold. No write.
VERDICT_CONSISTENT = "CONSISTENT"

#: Verdicts whose repair this module owns. The referral and the two no-ops are
#: deliberately excluded: a rail that "handles" a referral is a rail that writes
#: outside its evidence.
REPAIRABLE_VERDICTS = frozenset(
    {VERDICT_PREMATURE_GRADE, VERDICT_STALE_RESOLUTION_DATE}
)


@dataclass(frozen=True)
class VenueLeg:
    """One sub-market's ``(status, result)`` AS A PAIR.

    Kept paired on purpose. An earlier draft of this module carried parallel
    ``statuses`` and ``results`` tuples and asked whether any status crossed with
    any result graded a winner — a cross-product, which invents leg states that do
    not exist: an event holding ``('active', 'finalized')`` and ``('', 'yes')``
    would be asked about the pair ``('active', 'yes')`` that no sub-market has.
    ``gradeable_winner`` is only meaningful on a real pair, so only real pairs are
    stored.
    """

    status: str = ""
    result: str = ""


@dataclass(frozen=True)
class VenueEvidence:
    """What one ``GET /events/{ticker}`` says, reduced to what the split needs.

    ``settlement_ts`` is the max across the event's terminal sub-markets, mirroring
    the writer's own ``max()`` so the comparison is like-for-like.
    """

    ticker: str
    answered: bool
    legs: tuple[VenueLeg, ...] = ()
    settlement_ts: datetime | None = None
    max_expiration_time: datetime | None = None
    any_can_close_early: bool = False

    @property
    def statuses(self) -> tuple[str, ...]:
        return tuple(sorted({leg.status for leg in self.legs}))

    @property
    def has_terminal(self) -> bool:
        return any(is_terminal(leg.status) for leg in self.legs)

    @property
    def names_a_winner(self) -> bool:
        """True when the venue grades at least one sub-market a winner.

        Uses the shipping mapper, so ``""`` and ``"scalar"`` can never be read as
        a winner here any more than they can in the grader (CAL-P053).
        """
        return any(
            gradeable_winner(leg.status, leg.result) is True for leg in self.legs
        )


@dataclass(frozen=True)
class ProvenanceVerdict:
    ticker: str
    verdict: str
    reason: str
    #: Only ever set on :data:`VERDICT_STALE_RESOLUTION_DATE`.
    corrected_resolution_date: datetime | None = None
    #: Days our stored date sits after real settlement. Positive means late.
    error_days: float | None = None
    #: Retention band recomputed on the CORRECTED date, not the stored one.
    true_retention_band: str | None = None

    @property
    def is_repairable(self) -> bool:
        return self.verdict in REPAIRABLE_VERDICTS


def retention_band(age_days: float) -> str:
    """Band a settlement age against the MEASURED Kalshi bounds.

    Uses ``app/utils/kalshi_retention.py`` rather than a hand-rolled day count —
    gotcha #35 exists because three rails each re-derived this in prose and each
    ground purged rows anyway.
    """
    if age_days < AT_RISK_AGE_DAYS:
        return "reachable"
    if age_days < PROVABLY_PURGED_AGE_DAYS:
        return "at_risk"
    return "provably_purged"


def classify_provenance(
    *,
    evidence: VenueEvidence,
    stored_resolution_date: datetime | None,
    now: datetime,
) -> ProvenanceVerdict:
    """Return exactly ONE disposition for one market.

    The ordering below is the whole design. ``UNADDRESSABLE`` is tested before
    anything that could infer a fact from silence; the fabricated-loss referral is
    tested before the date arm, so a market that needs a regrade can never also be
    handed a date correction.
    """
    if not evidence.answered:
        return ProvenanceVerdict(
            ticker=evidence.ticker,
            verdict=VERDICT_UNADDRESSABLE,
            reason=(
                "venue answered 200 with no markets; purged and never-settled are "
                "the same response shape, so no verdict is derivable (gotcha #53)"
            ),
        )

    # No terminal sub-market and no settlement stamp => the venue has not settled
    # this market. Our all-loser api_settlement grade asserts something the venue
    # does not.
    if not evidence.has_terminal and evidence.settlement_ts is None:
        return ProvenanceVerdict(
            ticker=evidence.ticker,
            verdict=VERDICT_PREMATURE_GRADE,
            reason=(
                f"venue statuses {list(evidence.statuses)} are all non-terminal and "
                "no settlement_ts exists, yet every leg is graded a loser at "
                "api_settlement authority"
            ),
        )

    if evidence.settlement_ts is None:
        # Terminal but unstamped. Real (a closed market awaiting settlement), and
        # not a date defect. Do not invent a date from a status.
        return ProvenanceVerdict(
            ticker=evidence.ticker,
            verdict=VERDICT_CONSISTENT,
            reason="terminal at the venue but carrying no settlement_ts; nothing to correct",
        )

    if evidence.names_a_winner:
        return ProvenanceVerdict(
            ticker=evidence.ticker,
            verdict=VERDICT_FABRICATED_LOSS_REFERRAL,
            reason=(
                "venue settled and names a winner while we hold all-losers; this is "
                "the #1852 regrade class and is referred, not repaired here"
            ),
        )

    if stored_resolution_date is None:
        return ProvenanceVerdict(
            ticker=evidence.ticker,
            verdict=VERDICT_CONSISTENT,
            reason="no stored resolution_date to compare",
        )

    error = (stored_resolution_date - evidence.settlement_ts).total_seconds() / 86400.0
    if error <= 0:
        return ProvenanceVerdict(
            ticker=evidence.ticker,
            verdict=VERDICT_CONSISTENT,
            reason="stored resolution_date is at or before real settlement",
            error_days=error,
        )

    age = (now - evidence.settlement_ts).total_seconds() / 86400.0
    return ProvenanceVerdict(
        ticker=evidence.ticker,
        verdict=VERDICT_STALE_RESOLUTION_DATE,
        reason=(
            f"venue settled {evidence.settlement_ts.isoformat()} but we store "
            f"{stored_resolution_date.isoformat()} — {error:.2f} days late; the "
            "stored value is max(expiration_time), an early-close backstop"
        ),
        corrected_resolution_date=evidence.settlement_ts,
        error_days=error,
        true_retention_band=retention_band(age),
    )


def banding_shift(
    verdicts: list[ProvenanceVerdict],
) -> dict[str, int]:
    """How the retention picture changes once dates are corrected.

    Every row in the #1868 population is banded ``future_date`` today, which every
    recovery rail reads as *not due yet, skip*. Correcting the date re-bands it
    against real age. This function is what turns "the dates are wrong" into an
    operational number: how many rows are actually actionable now, and how many are
    already past saving.
    """
    out = {"reachable": 0, "at_risk": 0, "provably_purged": 0, "no_band": 0}
    for v in verdicts:
        if v.true_retention_band is None:
            out["no_band"] += 1
        else:
            out[v.true_retention_band] += 1
    return out


def days_until_at_risk(
    verdict: ProvenanceVerdict, now: datetime
) -> float | None:
    """Days before a corrected row crosses the LOWER (warning) retention bound.

    Deliberately the lower bound: the warning must precede the loss, which is the
    same reasoning ``kalshi_retention`` uses to pick which bound goes where.
    """
    if verdict.corrected_resolution_date is None:
        return None
    deadline = verdict.corrected_resolution_date + timedelta(days=AT_RISK_AGE_DAYS)
    return (deadline - now).total_seconds() / 86400.0
