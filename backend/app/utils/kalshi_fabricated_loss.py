"""What to do with a loss the venue never declared — the BACKWARD half of CAL-P053.

CAL-P056 (#1852). CAL-P053 shipped ``kalshi_market_status.gradeable_winner``, whose
three-state return stops the producer: a Kalshi ``result`` of ``""`` or ``"scalar"``
now means *do not write* instead of *this outcome lost*. That fix is live
(``d59c9374``, deployed 2026-08-14 16:59:38 UTC) and this module does nothing about
it. This module is about the grades **already written** before it landed.

THE TWO MECHANISMS, and only the first was fixed going forward:

1. **Unmappable result → loss.** ``result`` values of ``"scalar"`` and ``""`` were
   written as ``is_winner = false`` with ``resolution_source = 'api_settlement'`` —
   the TOP authority rung, which :func:`resolution_authority.is_downgrade` then
   protects from any later correction. It is a fabricated claim wearing the
   strongest badge we issue.
2. **Ticker mismatch.** The venue's winning leg exists but our outcome
   ``external_id`` does not match it, so only the losing legs update. DIAGNOSED,
   NOT FIXED — this module COUNTS and SAMPLES those legs and never writes them,
   because a leg we cannot identify is a leg we cannot grade.

MEASURED, live, 2026-08-14 (public Kalshi API, no auth) on a market this codebase
had recorded as all-losers::

    GET /markets?event_ticker=KXPGAR1LEAD-COPC26  ->  152 markets
        status: finalized x152
        result: no x150,  scalar x2,  yes x0

So 150 of those losses are CORRECT — the venue really did say no — and 2 are
fabricated. A blanket "all-loser markets are wrong" repair would have corrupted
150 true rows to fix 2. The unit of repair is therefore the LEG, judged against
the venue's own per-leg declaration, never the market's shape.

WHY THIS IS ALLOWED TO WRITE AT ALL (gotcha #21: never bulk-reset ``is_winner``
without a confirmed alternative source). It is not a bulk reset and it is not a
guess. Every write in :func:`classify_leg` is licensed by the venue's own answer
for that exact ticker, fetched in the same call. A leg the venue does not answer
for is left exactly as it is.

THE ONE DELIBERATE AUTHORITY-LADDER EXCEPTION. Retracting a fabricated loss writes
:data:`RETRACTION_SOURCE` (tier 1) over ``api_settlement`` (tier 3), which
``is_downgrade`` calls a downgrade — and normally forbids. It is permitted here,
and ONLY here, because the tier-3 write was never authorised by the venue in the
first place: the badge is what is being corrected. The retraction is reversible by
real evidence — ``ungradeable_result`` is not in ``AUTHORITATIVE_SOURCES``, so the
ordinary Kalshi graders will overwrite it the moment the venue declares a side.

WHAT A RETRACTION CHANGES DOWNSTREAM. ``resolution_source`` is the published
curve's eligibility predicate (``fo.resolution_source IN
CALIBRATION_TRUTH_ELIGIBLE_SOURCES``), so moving a row from ``api_settlement`` to
``ungradeable_result`` REMOVES it from the curve rather than re-grading it. That is
the honest outcome: we do not know what happened, and ruling 054 says an unknown is
declared and counted, never absorbed. Expect the published curve to MOVE on the
first recompute after an apply pass — that is a CORRECTION, and its cause and count
are reported by the rail that caused it.

Pure module: no DB, no network. Safe to import from tasks and tests alike.
"""

from __future__ import annotations

from typing import Any

from app.utils import kalshi_market_status as kms
from app.utils.kalshi_retention import AT_RISK_AGE_DAYS, PROVABLY_PURGED_AGE_DAYS
from app.utils.resolution_authority import AUTHORITATIVE_SOURCES

#: The source a retracted fabricated loss carries. Classified TERMINAL (tier 1) in
#: ``resolution_authority``: structurally no-winner, calibration-truth INELIGIBLE,
#: and overwritable by any real result. The name matches the counter the live
#: graders already increment (``stats["ungradeable_result"]``), so the forward
#: skip and the backward retraction are spelled the same thing.
RETRACTION_SOURCE = "ungradeable_result"

#: The only existing source this repair will touch. A leg carrying a DIFFERENT
#: tier-3 source belongs to another rail's cohort (clob_field_repair,
#: clob_never_graded, datagolf_settlement, …) and is left alone — reverting
#: someone else's cohort in this predicate would make both irreversible.
REPAIRABLE_SOURCE = "api_settlement"

#: Legs whose disposition writes something. Everything else is observation.
WRITING_VERDICTS = frozenset({"restore_winner", "retract_fabricated"})

#: Market-level verdicts that mean "we asked the venue and it told us nothing".
#: Split deliberately — gotcha #53: an empty 200 is a response SHAPE, and the two
#: readings of it are a fact about retention and a fact about the market.
SILENT_VERDICTS = frozenset({"purged_declared_exclusion", "unexplained_absence"})


def classify_leg(
    our_is_winner: bool,
    our_source: str | None,
    venue_status: str | None,
    venue_result: str | None,
    *,
    present_at_venue: bool = True,
) -> str:
    """Decide what the venue's answer means for one stored leg. Pure.

    Returns exactly one verdict:

    ``not_at_venue``
        Our ``external_id`` is absent from the venue's market list for this event
        — mechanism 2. Counted and sampled, NEVER written: a leg we cannot
        identify is a leg we cannot grade, and guessing which venue leg it "must"
        be is precisely the guess-family behaviour the authority ladder exists to
        forbid.
    ``foreign_authority``
        The leg carries a tier-3 source other than ``api_settlement``. Another
        rail owns this row.
    ``not_repairable``
        The leg carries no ``api_settlement`` badge at all, so there is no
        fabricated tier-3 claim here to correct.
    ``restore_winner``
        The venue declared YES for this exact ticker and we hold a loss. Write.
    ``confirmed_loss``
        The venue declared NO and we hold a loss. The stored grade is CORRECT.
        This is the majority verdict on real data (150 of 152 in the specimen
        above) and the reason this repair is per-leg rather than per-market.
    ``already_winner``
        We already hold the winner the venue declared. No write.
    ``unsupported_winner``
        We hold a WIN the venue never declared — the mirror of the defect this
        rail repairs. Out of population here (zero-winner markets only), and
        reported rather than silently treated as correct.
    ``retract_fabricated``
        The venue declared nothing this codebase can map to a side — ``scalar``,
        the empty string, or a status that does not carry a result at all — yet
        we hold ``api_settlement`` + loser. The claim is unsupported. Retract.
    """
    if not present_at_venue:
        return "not_at_venue"
    if our_source != REPAIRABLE_SOURCE:
        if our_source in AUTHORITATIVE_SOURCES:
            return "foreign_authority"
        return "not_repairable"

    declared = kms.gradeable_winner(venue_status, venue_result)
    if declared is None:
        # The whole point of CAL-P053's third state, read backwards: an absence
        # of declaration cannot license the grade we recorded — in EITHER
        # direction. `unsupported_winner` cannot occur in this rail's population
        # (it selects zero-winner markets) and is returned rather than folded
        # into `already_winner` because a win the venue never declared is the
        # same defect as a loss it never declared, and a mapper that reported it
        # as fine would be the thing this module exists to stop.
        return "retract_fabricated" if not our_is_winner else "unsupported_winner"
    if declared:
        return "already_winner" if our_is_winner else "restore_winner"
    return "confirmed_loss"


def classify_market(
    venue_markets: list[dict] | None,
    age_days: float | None,
    *,
    mutually_exclusive: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Decide whether the venue answered usefully for a whole event. Pure.

    ``venue_markets is None`` means the lookup failed or 404'd — gotcha #36: a
    swallowed transport error and a genuine absence are indistinguishable at that
    boundary, so it is ``unknown``, never "gone".

    An EMPTY list is the gotcha-#53 case and is split by the MEASURED retention
    bound rather than by prose: past :data:`kalshi_retention.PROVABLY_PURGED_AGE_DAYS`
    the emptiness is explained by retention and becomes a DECLARED, counted
    exclusion (ruling 054); inside the bound it is an ``unexplained_absence`` and
    stays visible as its own number, because collapsing it into the purged bucket
    would hide a real upstream defect behind a known one.
    """
    if venue_markets is None:
        return "unknown", {"reason": "venue lookup returned None (404 or error)"}

    if not venue_markets:
        if age_days is not None and age_days >= PROVABLY_PURGED_AGE_DAYS:
            return "purged_declared_exclusion", {
                "reason": "empty market list past the measured retention bound",
                "age_days": age_days,
                "purge_bound_days": PROVABLY_PURGED_AGE_DAYS,
            }
        return "unexplained_absence", {
            "reason": "empty market list INSIDE the retention window",
            "age_days": age_days,
            "purge_bound_days": PROVABLY_PURGED_AGE_DAYS,
        }

    yes_legs = [
        m.get("ticker")
        for m in venue_markets
        if kms.gradeable_winner(m.get("status"), m.get("result")) is True
    ]
    if mutually_exclusive and len(yes_legs) > 1:
        # Contradictory upstream for a field that can only have one winner. Fail
        # closed on the WHOLE market rather than pick one — the winner-field
        # repair's discipline (CAL-P007).
        return "contradictory_venue", {
            "reason": "more than one YES leg on a mutually-exclusive market",
            "yes_legs": yes_legs[:5],
            "yes_count": len(yes_legs),
        }

    return "answered", {
        "venue_markets": len(venue_markets),
        "venue_yes_legs": len(yes_legs),
    }


#: The standing population, as SQL, in ONE place so the census, the work
#: selection and the after-check cannot drift from each other.
#:
#: Read it as: a Kalshi market, every one of whose outcomes we graded, that has NO
#: winner at all and at least one ``api_settlement`` loss. ``COUNT(*) >= 2`` is
#: deliberate — a ONE-leg Kalshi binary that settled NO is an ordinary, correct
#: loser, and 4,372 of them sit in this shape; including them would bury the
#: defect in legitimate rows and spend the venue budget on nothing.
POPULATION_HAVING_SQL = """
        COUNT(*) >= 2
    AND COUNT(*) FILTER (WHERE fo.is_winner) = 0
    AND COUNT(*) = COUNT(*) FILTER (WHERE fo.resolution_source = 'api_settlement')
"""

#: Retention banding for the census, expressed against the MEASURED bounds rather
#: than a hand-rolled day count (gotcha #35). ``future_date`` is its own band and
#: not folded into ``in_retention``: a market graded all-losers whose scheduled
#: resolution has not yet ARRIVED is a second anomaly, and it is 47% of the
#: Kalshi population measured on 2026-08-14.
#: ``at_risk`` (the 74–86 day uncertainty band) is REPORTED separately but is
#: still WORK: ``kalshi_retention``'s rule is that skipping uses the UPPER bound,
#: so a row in the band is attempted, fail-open. It is banded only so the count
#: that is about to become unrecoverable is visible while it still can be saved.
RETENTION_BAND_SQL = f"""
        CASE
          WHEN fm.resolution_date IS NULL THEN 'unknown_date'
          WHEN fm.resolution_date > NOW() THEN 'future_date'
          WHEN NOW() - fm.resolution_date
               >= INTERVAL '{PROVABLY_PURGED_AGE_DAYS} days'
            THEN 'provably_purged'
          WHEN NOW() - fm.resolution_date
               >= INTERVAL '{AT_RISK_AGE_DAYS} days'
            THEN 'at_risk'
          ELSE 'reachable'
        END
"""
