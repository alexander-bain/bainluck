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

WHAT A RETRACTION CHANGES DOWNSTREAM — MEASURED IN CAL-P057, AND IT IS NOT WHAT
THIS MODULE ORIGINALLY CLAIMED. ``resolution_source`` is the published curve's
eligibility predicate (``fo.resolution_source IN
CALIBRATION_TRUTH_ELIGIBLE_SOURCES``), so moving a row from ``api_settlement`` to
``ungradeable_result`` does remove it from that predicate. The original text
concluded "expect the published curve to MOVE on the first recompute". Measured
against production on 2026-08-14, **that is wrong for retractions**, and the
reason is that this rail's population is the SAME PREDICATE as one of the curve's
own exclusions:

    ``no_winner_markets`` (Queue 299 rung 1) excludes every resolved market with
    ``n_outcomes >= 2`` and ``win_count = 0`` — which is exactly
    :data:`POPULATION_HAVING_SQL`'s first two conjuncts.

Measured over the whole 0–86 day work band, in 15 date shards with none skipped:
**2,887 of 2,887 target markets (100%) are already caught by
``no_winner_markets``**, covering 18,688 legs. Their rows are not on the curve
now, so retracting them cannot move it. The published census already reports the
class: ``no_winner_filter.excluded = 26,627`` outcomes / 1,894 markets.

So the curve moves in the OPPOSITE direction, and only via the other verdict:
a ``restore_winner`` flips ``win_count`` from 0 to 1, the market LEAVES
``no_winner_markets``, and its whole surviving leg set is ADMITTED to the curve.
The movement to declare in advance (ruling 054) is therefore an ADDITION driven
by the restore count — never a subtraction driven by the retraction count.

🔴 **EVERYTHING IN THE FOUR PARAGRAPHS ABOVE IS TRUE OF THE POPULATION THIS RAIL
SELECTED UNTIL CAL-P1124, AND IS NO LONGER TRUE OF THE ONE IT SELECTS NOW.** The
containment that made the retraction arm provably curve-neutral was not a
property of the defect; it was a property of the first two conjuncts of
:data:`POPULATION_HAVING_SQL` happening to BE ``no_winner_markets``. #3617 item C
arm A retires those conjuncts on purpose — they were excluding 96% of the defect
— and the containment goes with them. The rail now selects markets the curve
publishes, so a retraction now REMOVES a published row.

That inverts the sign of the declared movement, and the inversion is the ship
rather than a side effect: "the accuracy page stops counting losses the venue
never declared" is a SUBTRACTION, and a rail that could only ever move the curve
by zero could not have delivered it. Read
:func:`app.tasks.repair_kalshi_fabricated_loss.declared_curve_movement` for the
replacement declaration, its bound, and what now counts as a halt — the old
"any movement on the retraction arm is a HALT" rule would fire on success.

THE PRECONDITION IS ANSWERED, BY MEASUREMENT (Fable ruling 2, 2026-08-14). It was
found by the fingerprint ratchet: adding :data:`RETRACTION_SOURCE` to
``KNOWN_SOURCES`` moves ``CALIBRATION_TRUTH_INELIGIBLE_SOURCES_SQL``, an input
that is ``sql_interpolated: true`` / ``covered_by_value: false`` — the CAL-P031/
P032 hole ruling 024 sequences. The question was whether banked calibration units
invalidate on an apply. Three measurements, not a judgment call:

1. **Does the new source class change any banked unit today?** No, and the proof
   is a count: ``SELECT COUNT(*) ... WHERE resolution_source = 'ungradeable_result'``
   returns **0 rows** in production. A unit recomputed with and without the class
   in the eligible/ineligible sets is identical because the value matches nothing.
2. **Does an apply move the GENERATION fingerprint** —
   ``calibration_staged_futures.generation_fingerprint``, the one mechanism that
   does invalidate banked units? **No.** That digest is computed over
   ``(market_id, source, vm_id, is_grouped)``. Every one of those comes from
   ``market_info`` → ``virtual_market``, whose only filters are
   ``futures_markets.status = 'resolved'`` and the DataGolf residual flag, with
   ``vm_id`` / ``is_grouped`` decided by ``group_sizes`` / ``event_sizes`` —
   which COUNT MARKETS, never outcomes. **Nothing in the roster reads
   ``futures_outcomes`` at all**, so a repair that writes only to
   ``futures_outcomes`` is structurally invisible to it.
3. **Does the MAIN input fingerprint move?** No. It hashes
   ``inspect.getsource`` of four functions plus three named constants. Source
   text is the UNEXPANDED f-string, and a data change moves no source at all.

**Conclusion: nothing invalidates banked units on an apply pass.** That is the
first arm of ruling 2 — the operator declares — and CAL-P058 makes the
declaration EXECUTABLE rather than prose, because C-CERT-1852's fourth finding
is precisely that "someone must answer" supplies no command, no expected value,
no refusal condition and no gate. See
:func:`app.tasks.repair_kalshi_fabricated_loss.invalidate_calibration_generation`:
the apply rail's final step discards the banked state, re-reads to prove it, and
the run returns ``success: false`` if it cannot. The invalidation is WHOLESALE
and that is forced, not lazy — CAL-P034 folds every banked unit into one
accumulator, so a single unit's contribution cannot be subtracted, and the
canonical roster read that would resolve the affected ``vm_id`` exceeded the
10 s statement timeout in production. Both reasons are recorded in that
function's docstring and in its return value.

Pure module: no DB, no network. Safe to import from tasks and tests alike.
"""

from __future__ import annotations

from typing import Any, Iterable

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


def map_venue_by_ticker(venue_markets: list[dict] | None) -> dict[Any, dict]:
    """The venue's markets, keyed by their EXACT ticker. Pure.

    Extracted from the task in CAL-P058 because C-CERT-1852's fifth finding is
    that the committed "live replay" never crossed this line: the fixture test
    classified each venue row directly, so replacing
    ``by_ticker.get(leg.external_id)`` with "the first venue record" — a mapper
    that applies one venue leg to every stored leg — left every specimen
    assertion green. The join is the part most able to be wrong and was the one
    part no test executed.

    It is trivial, and that is the point: the test must enter through THIS
    function, not through a second copy of it written in the test file.
    """
    return {m.get("ticker"): m for m in (venue_markets or [])}


def plan_market_legs(
    stored_legs: Iterable[Any],
    venue_markets: list[dict] | None,
) -> list[dict[str, Any]]:
    """Judge one market's stored legs against the venue. THE production path.

    ``stored_legs`` is any iterable of objects carrying ``id``, ``external_id``,
    ``is_winner`` and ``resolution_source`` — a DB row, or a fixture row shaped
    like one. Returns one record per stored leg::

        {"leg_id", "external_id", "verdict", "prior_is_winner",
         "prior_source", "venue_status", "venue_result", "present_at_venue"}

    The prior state travels WITH the verdict on purpose. It is the compare half
    of the apply's compare-and-set, and re-reading it at write time would be
    asking the same question twice and trusting the second answer — the
    stale-read clobber C-CERT-1852 found in the restore path.

    ``repair()`` calls this and nothing else; there is no second mapping in the
    task. A test that exercises the specimens therefore exercises the shipping
    join, including the ticker identity, rather than a paraphrase of it.
    """
    by_ticker = map_venue_by_ticker(venue_markets)
    planned: list[dict[str, Any]] = []
    for leg in stored_legs:
        vm = by_ticker.get(leg.external_id)
        planned.append(
            {
                "leg_id": leg.id,
                "external_id": leg.external_id,
                "verdict": classify_leg(
                    bool(leg.is_winner),
                    leg.resolution_source,
                    (vm or {}).get("status"),
                    (vm or {}).get("result"),
                    present_at_venue=vm is not None,
                ),
                "prior_is_winner": bool(leg.is_winner),
                "prior_source": leg.resolution_source,
                "venue_status": (vm or {}).get("status"),
                "venue_result": (vm or {}).get("result"),
                "present_at_venue": vm is not None,
            }
        )
    return planned


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
#: 🔴 CAL-P1124 (#3617 item C arm A) SELECTS AT THE LEG, NOT THE MARKET SHAPE, and
#: that is the whole widening. The previous predicate asked three questions about
#: the MARKET::
#:
#:         COUNT(*) >= 2
#:     AND COUNT(*) FILTER (WHERE fo.is_winner) = 0
#:     AND COUNT(*) = COUNT(*) FILTER (WHERE fo.resolution_source = 'api_settlement')
#:
#: and each conjunct excluded a large population that still contains the defect.
#: Measured 2026-09-12 over the reachable floor (``fo.id >= 227000000`` slice, the
#: bound a whole-table count no longer completes inside):
#:
#: ===============================  =======  =============================
#: slice                            markets  ``api_settlement`` losses
#: ===============================  =======  =============================
#: reached before (all 3 conjuncts)     225  1,964
#: crowned, non-exclusive/multi-win   1,315  17,217
#: single-leg                           628  628
#: mixed-source                          22  582
#: ===============================  =======  =============================
#:
#: The three conjuncts are retired for three DIFFERENT reasons, none of them
#: "they looked restrictive":
#:
#: * the source-purity conjunct was never protective — :func:`classify_leg`
#:   already returns ``foreign_authority`` / ``not_repairable`` for a leg carrying
#:   anything other than ``api_settlement`` and writes nothing to it, so excluding
#:   the whole MARKET because one leg belongs to another rail only hid this
#:   rail's own legs;
#: * ``COUNT(*) >= 2`` was protecting the VENUE BUDGET, not correctness — a
#:   one-leg binary that settled NO is judged ``confirmed_loss`` and written to
#:   never. Its function is preserved, and preserved is not the same as kept: the
#:   budget is now protected by :data:`HARM_COHORT_HAVING_SQL`, which drains the
#:   worst-priced cohort first, and the floored slice is 628 markets rather than
#:   the unfloored 4,372 the old comment counted;
#: * ``COUNT(*) FILTER (WHERE fo.is_winner) = 0`` is the one that is NOT simply
#:   dropped. See :data:`IMPLIED_LOSS_EXCLUSION_SQL` — half of what it excluded is
#:   genuinely out of reach and stays out.
#:
#: Read the predicate now as: a Kalshi market holding AT LEAST ONE leg we graded
#: as an ``api_settlement`` loss. The market's shape is no longer consulted; the
#: leg is the unit, which is what the module docstring's 150-of-152 specimen said
#: it had to be from the beginning.
POPULATION_HAVING_SQL = f"""
    COUNT(*) FILTER (
      WHERE fo.resolution_source = '{REPAIRABLE_SOURCE}'
        AND fo.is_winner = false
    ) >= 1
"""

#: 🔴 THE ONE SLICE THE WIDENING DELIBERATELY DOES NOT TAKE, and the reason is
#: gotcha #21's asymmetry rather than caution for its own sake.
#:
#: A MUTUALLY-EXCLUSIVE market in which we recorded EXACTLY ONE winner is a market
#: whose losing legs lost *by exclusion*: the venue declared a winner for that
#: field, and in a field only one member can win. The loss is therefore
#: venue-licensed by entailment even when the venue's per-leg record for the
#: sibling reads ``""``. :func:`classify_leg` cannot see that — it is handed one
#: leg and the venue's answer for that leg alone, and CAL-P1124 is forbidden from
#: changing it (the per-leg license is the thing that makes this rail safe). Fed
#: these legs it would return ``retract_fabricated`` for every one of them.
#:
#: The consequence is not a no-op. Retracting a TRUE loss removes a correct row
#: from the published curve, and it removes it from the LOSING side only — a
#: bucket holding one winner and nine retracted losers publishes as 100%. That is
#: a fabricated accuracy number, which is the defect this rail exists to remove,
#: pointed at the curve from the other side.
#:
#: Measured 2026-09-12 on the same slice: **1,533 markets / 2,105 legs**, the
#: single largest residue slice. They stay excluded, and they stay excluded
#: EXPLICITLY — counted by the census under their own name rather than falling
#: out of a conjunct nobody reads — so the next session inherits a number and a
#: reason instead of a silence. Reaching them needs market-level entailment,
#: which is a separate ship and a separate ruling.
#:
#: A template, not a finished predicate: the two operands live on different
#: aliases at the two call sites (the work selection has ``futures_markets`` in
#: scope as ``s`` and aggregates inline; the census aggregates first and joins
#: ``fm`` afterwards). One definition, two bindings — the alternative is two
#: copies of a safety exclusion, which is how one of them gets edited alone.
IMPLIED_LOSS_EXCLUSION_SQL = "NOT ({mutex} AND {win_count} = 1)"

#: The curve's own price for a leg, character-for-character the expression
#: ``precompute_calibration`` ranks by. It is a COALESCE and NOT an exclusion —
#: gotcha #144 / ruling 103 exist because that fallback was invisible once.
CURVE_PRICE_SQL = "COALESCE(fo.calibration_probability, fo.opening_probability)"

#: 🔴 CAL-P1124 arm B — HARM ORDER AS A COHORT FILTER, AND NOT AS A SORT. The
#: brief asked to drain in harm order rather than id order. Measured against
#: production 2026-09-12, a literal re-sort cannot ship:
#:
#:     ORDER BY MAX(COALESCE(calibration_probability, opening_probability)) DESC
#:     ->  statement_timeout (>10s), LIMIT 40, the reachable floor
#:
#: and the reason is the one CAL-P1013 already paid for. ``_WORK_SQL`` is fast
#: because it drives from ``futures_markets`` IN SORT ORDER and probes outcomes
#: per candidate, so the ``LIMIT`` stops the scan. Sorting on a value that only
#: the per-market probe can produce forces every candidate's aggregate to be
#: computed before the first row is returned — which is precisely the unbounded
#: aggregate over ``futures_outcomes`` that #3195 and #2528 removed. It would have
#: traded a working rail for an ordering.
#:
#: Harm is therefore expressed as a THRESHOLD on the same probe that already runs.
#: The operator drains ``?min_harm=0.9`` first (the cohort we price at 90%+ while
#: calling it a loss — the worst rows on the page and the ones #3617 opened on),
#: then lowers it. The sort, the keyset and the band stay character-for-character
#: what three separate ordering traps made them. Measured in the shipped shape:
#: **1.5s at 0.9, 0.83s unfiltered**, against 7.6s for the form it replaces —
#: narrowing the probe made the rail faster, not slower.
#:
#: ⚠️ THE THRESHOLD IS A PROPERTY OF THE WALK. A walk that reports ``exhausted``
#: at ``min_harm=0.9`` has exhausted the 90%+ cohort and says NOTHING about the
#: rows beneath it. It does not strand them the way CERT-1935's sliding band
#: anchor did — the keyset names a position in an order the threshold does not
#: touch, so a later walk at a lower threshold reaches them from cursor zero —
#: but an operator who reads one ``exhausted`` as "the population is drained" has
#: misread it, so the receipt carries the threshold it ran under.
HARM_COHORT_HAVING_SQL = f"""
    (
      CAST(:min_harm AS double precision) IS NULL
      OR COUNT(*) FILTER (
           WHERE fo.resolution_source = '{REPAIRABLE_SOURCE}'
             AND fo.is_winner = false
             AND {CURVE_PRICE_SQL} >= CAST(:min_harm AS double precision)
         ) >= 1
    )
"""


def market_loss_is_implied(
    mutually_exclusive: bool | None, win_count: int | None
) -> bool:
    """Would this market's remaining losses be TRUE by exclusion? Pure.

    The Python twin of :data:`IMPLIED_LOSS_EXCLUSION_SQL`, and it exists so the
    exclusion is testable without a database. Both call sites interpolate the SQL
    template; the guard suite asserts this function and that template agree on
    the same table of cases, so a future edit to one that does not touch the
    other fails a test rather than quietly widening a safety exclusion.

    ``None`` for either operand is NOT implied — an unknown shape is judged
    per-leg like everything else, because treating unknown as "implied" would
    silently shrink the population by the size of a nullable column.
    """
    return bool(mutually_exclusive) and win_count == 1

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
