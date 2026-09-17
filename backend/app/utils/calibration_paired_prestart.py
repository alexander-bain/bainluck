"""CAL-P1215 / CAL-P1330 (#6176, #1544, #997) — the paired early/final pre-start cohort.

**The accuracy page currently splits DIFFERENT outcomes into two groups and
compares their aggregate errors. That is not a test of whether a forecast
improved, because no outcome appears on both sides of it.**

Alex, 2026-09-14: *"core question is whether trading brings forecasts closer to
truth before an event ... Current code compares DIFFERENT outcome cohorts by
price_moved and aggregate ECE; it is not an opening-to-close improvement test on
the SAME outcomes."* This module is the cohort that would be.

THE TRACE — what ``price_moved`` actually is
---------------------------------------------
``precompute_calibration``'s grouping dimension, verbatim::

    (fo.calibration_probability IS NOT NULL
     AND fo.calibration_probability IS DISTINCT FROM fo.opening_probability)

It is a **value inequality between two columns**, not a timing comparison. It
reads no clock and no snapshot. Nothing in it can distinguish "the market traded
and did not move" from "we never captured a second price", and those are the two
populations it merges.

``price_moved = false`` is exactly ``cp_absent ∪ cp_eq_open``, the two classes
:mod:`app.utils.calibration_price_provenance` (CAL-P077) already named and
measured:

``cp_absent``
    ``calibration_probability IS NULL``; the read side supplies the opening.
``cp_eq_open``
    The WRITER already fell back. ``backfill_winners`` Part A banks
    ``COALESCE(closing.probability, opening_probability)``, so an outcome with no
    eligible pre-boundary snapshot **stores its opening under the closing line's
    name**. CAL-P077 measured this at **37% to 84% of every cell** — the larger
    half, and invisible to a ``cp IS NULL`` probe.

So the "false" arm is dominated by rows for which *we hold no second price at
all*. It is a statement about our capture, not about the market.

WHY THE LABELS COMPOUND IT
---------------------------
The page renders these two arms as "traded" and "untraded"
(``lib/calibrationMath.ts``, ``describeActivityComparison``). The repo's own
ruling-011 definition of trading evidence is
:mod:`app.utils.calibration_trade_evidence`, and it uses ``volume`` and
open interest — never this predicate. By that definition ``datagolf`` and
``odds_api`` are ``not_applicable``: they have no volume concept, and **datagolf
has ``calibration == opening`` BY CONSTRUCTION** (``backfill_winners`` Part A1-dg
sets ``calibration_probability = fo.opening_probability`` outright, because a
model prediction has no closing line). A whole source can therefore never leave
the "untraded" arm, and is being counted as evidence about trading.

The two arms differ by source mix and capture quality. An aggregate-ECE
comparison between them measures those, and cannot be read as a claim about what
trading does.

WHAT AN HONEST PAIRED COHORT REQUIRES — and what this module enforces
---------------------------------------------------------------------
One outcome contributes BOTH legs, or it contributes nothing:

1. **Same question, same outcome, same resolution.** The pair is keyed on
   ``futures_outcomes.id``, and ``is_winner IS NOT NULL`` — NULL is ungraded
   truth, never a loss (gotcha #21, and the ``is_winner`` annotation in
   ``models.py``). The result must come from a source that is not the price
   itself (:func:`app.utils.resolution_authority.calibration_truth_eligible_sql`);
   a close that crowned its own outcome cannot then be graded against it.
2. **Both legs are real observations**, taken from ``futures_odds_snapshots``.
   Neither leg may be ``opening_probability``: that column is a derived opening
   (see ``opening_source``) and, on the ``cp_eq_open`` population, it is *also*
   what the close fell back to — using it as the early leg would compare a value
   against itself and publish the artifact as a finding.
3. **Both legs are strictly pre-start**, before the SAME boundary
   ``LEAST(commence_time, resolution_date)`` from
   :func:`app.utils.calibration_closing_line.closing_line_boundary_sql`. That
   clamp is what keeps a mis-linked market's post-settlement quote out (Q436 /
   CAL-P117: 1,525 of 1,739 props rows had been re-priced against one).
4. **Both legs pass the SAME eligibility rule** — the shipped closing-line
   predicate, reused rather than restated, so the early leg cannot be selected
   under a laxer filter. An asymmetric filter manufactures improvement.

── WHAT CAL-P1330 (#6176) ADDS, AND WHY EACH ONE BENDS THE NUMBER ────────────

The contract is ``artifacts/other-model-paired-accuracy/REPORT.md`` §2–§4, and
its executable synthetic demonstration is ``paired_accuracy_example.py`` beside
it. Four defects in the first cut of this module would each have moved the
published figure, in a direction nobody chose:

5. **"Earlier" is an INSTANT, not a position in our capture log.** The first cut
   took the FIRST snapshot ever captured as the early leg. That is 30 days of
   lead for one outcome and 7 hours for the next, so the number it produces is a
   statement about when our pollers happened to start, not about the market.
   "Early" here means **the standing eligible price as of** ``S − LEAD``
   (:data:`DEFAULT_LEAD_SECONDS`, 24h). Every paired outcome then carries the
   same lead and the aggregate answers ONE question. Both legs are therefore
   selected ``ORDER BY captured_at DESC`` — the early leg is a closing line too,
   drawn against an earlier boundary. There is no ``ASC`` lateral in this module
   any more, and :func:`paired_legs_sql`'s test asserts that.

   A fixed lead also RETIRES the old ``legs_too_close`` / minimum-separation
   guard: two instants 24h apart cannot be one poll sampled twice.

6. **``captured_at`` is when a VALUE was first seen, not when we last looked.**
   ``tasks/retention.py`` collapses a run of identical readings into its FIRST
   row and moves the last look into ``valid_until``; DataGolf dedups at write
   time. So a price captured a week out and never re-confirmed would otherwise
   pose as "the last price before the start". Freshness is read from
   ``COALESCE(valid_until, captured_at)`` and each leg must clear its own
   staleness bound (:data:`DEFAULT_FINAL_MAX_STALE_SECONDS`,
   :data:`DEFAULT_EARLY_MAX_STALE_SECONDS`).

   The converse matters just as much: **a re-confirmed flat row legitimately
   supplies BOTH legs.** We looked fifty times and it did not move — that is
   evidence of no change, reported as :data:`PAIR_PAIRED_UNCHANGED`. Dropping it
   would bias the cohort toward markets that moved, which is the same class of
   selection defect as the one above, pointed the other way.

7. **A non-NULL ``commence_time`` is not a reported start.** The first cut's
   whole anchoring test was ``commence_time IS NOT NULL``. ``kalshi_ticker`` is
   midnight UTC of a ticker date for a match played that afternoon, and bare
   ``kalshi``/``polymarket`` can be the clock of the poll that minted the row.
   Scoring a "final pre-event" leg against either is scoring against a fiction.
   The repo already owns both questions and this module DELEGATES rather than
   writing a third list: :func:`~app.utils.event_completion.commence_time_is_a_reported_start`
   and :func:`~app.utils.event_rails.commence_time_was_never_a_kickoff`.
   :data:`PAIR_START_CONTRADICTED` adds the case where our own columns disagree
   with the start we hold (gotcha #46, and the wrong-game-in-a-series specimen
   that ``calibration_closing_line`` was built for).

   **Postponements cannot be reconstructed.** No original-start or reschedule
   history exists; ``commence_time`` is overwritten in place. A stale, too-early
   start only makes the final leg EARLIER than it could have been — which biases
   toward showing LESS improvement, so the error is the conservative one. A
   too-late start is what rule 3's clamp and :data:`PAIR_START_CONTRADICTED`
   catch. This is stated rather than inferred around.

8. **One bookmaker supplies both legs, and one EVENT is one piece of evidence.**
   ``futures_odds_snapshots.probability`` is one book's raw, margin-inclusive
   number (see the column's own annotation in ``models.py``), so an early
   DraftKings leg paired with a late FanDuel leg measures a margin difference
   and calls it a forecast improvement (:data:`PAIR_LEGS_FROM_DIFFERENT_BOOKS`).
   And both sides of one game, every leg of a props container, and the same
   question on two venues are ONE observation about the world: the standard
   error clusters on ``event_id`` (:func:`paired_improvement`'s ``cluster_ids``),
   and no margin is published below :data:`MIN_CLUSTERS_FOR_MARGIN` events.

9. **A model forecast is never pooled with market prices.** ``datagolf`` is a
   model output, not a price somebody paid; it gets its own paired set and its
   own sentence, or none. :func:`paired_improvement` REFUSES a mixed cohort
   rather than trusting a caller to remember
   (:data:`MODEL_FORECAST_SOURCES`).

WHAT THIS STILL CANNOT SAY
---------------------------
That trading CAUSED any improvement. Time passing, news arriving and our own
capture all move together, and nothing here separates them. The only sentence
the output supports is "forecasts were more/less accurate closer to the event".
Calibration is reported as its OWN sentence (:func:`leg_calibration`): a
forecaster who says 50% on every coin flip is perfectly calibrated and useless,
and the two words are not interchangeable.

FEASIBILITY IS AN OPEN QUESTION, NOT A FORMALITY
--------------------------------------------------
CAL-P077 measured, on the hindsight rows of its three worst cells, how many had
**even one** snapshot before the boundary: **0 of 8,387** (basketball/quantity),
**0 of 1,259** (hockey/container_member), **32 of 3,737**
(basketball/container_member). A pair needs two, at two fixed instants, from one
book. So "the data supports an early vs final-pre-event comparison" must be
MEASURED before any such label is promised to a reader, which is what
:func:`paired_feasibility_sql` measures and why it classifies the failures
separately instead of returning one count.

**Coverage is UNMEASURED and a thin set is a valid result.** If the walk returns
a handful of outcomes, the honest page says we can answer this for N% of
forecasts — not a thinner version of the claim it makes today.

Pure by construction: no session, no I/O, no clock. Nothing here is wired into
``precompute_calibration``, which stays frozen under ruling 009.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Sequence

from app.utils.calibration_closing_line import (
    closing_line_boundary_sql,
    closing_line_lateral_sql,
    is_eligible_closing_snapshot,
)
from app.utils.calibration_ece import bin_index, calibration_error
from app.utils.event_completion import (
    DERIVED_COMMENCE_SOURCES,
    commence_time_is_a_reported_start,
)
from app.utils.event_rails import (
    POLL_CLOCK_STAMP_TOLERANCE,
    commence_time_was_never_a_kickoff,
)
from app.utils.resolution_authority import calibration_truth_eligible_sql

__all__ = [
    "DEFAULT_EARLY_MAX_STALE_SECONDS",
    "DEFAULT_FINAL_MAX_STALE_SECONDS",
    "DEFAULT_LEAD_SECONDS",
    "MIN_CLUSTERS_FOR_MARGIN",
    "MODEL_FORECAST_SOURCES",
    "PAIR_CLASSES",
    "PAIR_LEGS_FROM_DIFFERENT_BOOKS",
    "PAIR_NO_EARLY_NONE_BEFORE",
    "PAIR_NO_EARLY_STALE",
    "PAIR_NO_FINAL_NONE_BEFORE",
    "PAIR_NO_FINAL_STALE",
    "PAIR_PAIRED",
    "PAIR_PAIRED_UNCHANGED",
    "PAIR_RESULT_NOT_INDEPENDENT",
    "PAIR_START_CONTRADICTED",
    "PAIR_START_NOT_REPORTED",
    "PAIR_START_PROVENANCE_UNKNOWN",
    "PAIR_UNANCHORED_BOUNDARY",
    "PAIRED_CLASSES",
    "START_CONTRADICTION_TOLERANCE_SECONDS",
    "boundary_is_anchored",
    "brier",
    "classify_pair",
    "forecast_kind",
    "leg_calibration",
    "log_loss",
    "paired_feasibility_sql",
    "paired_improvement",
    "paired_legs_sql",
    "result_is_independent",
    "start_is_contradicted_sql",
    "start_is_reported_sql",
    "start_refusal",
]


# ---------------------------------------------------------------------------
# Policy constants. PROVISIONAL, and every one of them must be set from the
# feasibility histogram — never tuned until a cohort looks the way someone
# hoped. They are named here so the walk and the score cannot hold different
# ones, and so a reader of the page can be told exactly what "earlier" meant.
# ---------------------------------------------------------------------------

#: How far before the start the EARLY leg is read. 24 hours.
#:
#: This is the whole of what "earlier" means, and it is a fixed INTERVAL rather
#: than a position in our capture log for the reason given in the header: the
#: first-snapshot-ever rule measures our ingestion.
#:
#: **Decided 2026-09-17 (CAL-P1330, the one open decision in the #6176 report):
#: 24h alone, no second rung.** A 7-day rung is legitimate only as its own
#: paired set — comparing a 7-day improvement against a 24-hour one is a
#: cross-population comparison, which is the exact defect this module exists to
#: remove, unless it is restricted to outcomes holding all three observations.
#: The walk decides whether that set is even populated; until it has run, one
#: rung is the honest number. ``lead_seconds`` stays a parameter so a second set
#: is a call, not a rewrite.
DEFAULT_LEAD_SECONDS = 24 * 3600

#: How stale the FINAL leg may be: how long before the start we may last have
#: CONFIRMED the price, reading ``COALESCE(valid_until, captured_at)``.
#:
#: Six hours, chosen because it is longer than every live polling cadence in
#: ``SPORT_POLLING_TIERS``, so a price that clears it is one we were still
#: watching rather than one we abandoned.
DEFAULT_FINAL_MAX_STALE_SECONDS = 6 * 3600

#: The same bound for the EARLY leg, at its own instant. Wider (12h) because a
#: day out is polled less often than the hour before the start, and a bound
#: tighter than the cadence would empty the cohort for a reason that has nothing
#: to do with the market.
DEFAULT_EARLY_MAX_STALE_SECONDS = 12 * 3600

#: How far ``fm.resolution_date`` may precede ``e.commence_time`` before the two
#: are treated as contradicting each other rather than merely disagreeing about
#: minutes. Six hours: settlement lands after the thing ends, so a settlement
#: that precedes the start by more than a session means the market and the event
#: are not describing the same occasion (the wrong-game-in-a-series specimen in
#: ``calibration_closing_line``). The clamp protects the PRICE; this protects the
#: lead time and the cluster, which the clamp cannot.
START_CONTRADICTION_TOLERANCE_SECONDS = 6 * 3600

#: Below this many EVENTS, no margin of error is displayed at all — not a wide
#: one. A cluster-robust standard error over a handful of clusters is not a
#: conservative estimate, it is an unstable one, and printing it invites a
#: reader to do arithmetic the data cannot support.
MIN_CLUSTERS_FOR_MARGIN = 30

#: Sources whose "price" is a MODEL OUTPUT rather than a number somebody paid.
#:
#: Deliberately NOT :data:`app.utils.calibration_trade_evidence.EXCLUDED_SOURCES`,
#: which reads ``("odds_api", "datagolf")``. That set answers "does this source
#: have a volume concept" — ``odds_api`` is a market with no volume feed, which
#: is a different fact from being a model. Pooling the two questions here would
#: drop every sportsbook price out of the market number.
MODEL_FORECAST_SOURCES = frozenset({"datagolf"})


# ---------------------------------------------------------------------------
# The pair classes. Why an outcome did or did not yield a pair, reported
# separately because "no pair" has nine different causes and only one of them
# is about liquidity.
# ---------------------------------------------------------------------------

#: A pair from two distinct observations of one book.
PAIR_PAIRED = "paired"

#: A pair whose two legs are the SAME collapsed row: we looked repeatedly across
#: both instants and the price never moved. Real evidence of no change, and kept
#: — see header note 6. Counted separately so a reader is never told a cohort
#: "moved" when part of it is this.
PAIR_PAIRED_UNCHANGED = "paired_unchanged"

#: The result is not independent of the price that is being scored: ungraded
#: (``is_winner IS NULL``) or graded by a price-derived source. Python-side only
#: — see :func:`paired_legs_sql`, whose WHERE holds the same rule so the
#: feasibility denominator stays the graded population every other calibration
#: reader uses.
PAIR_RESULT_NOT_INDEPENDENT = "result_not_independent"

#: CAL-P1216b, on codex's 17:11Z finding: *"LEAST of two timestamps alone does
#: not prove real event start"*, and so a leg drawn before it may not be a
#: **pre-event** forecast at all.
#:
#: No linked event at all. The boundary silently becomes ``resolution_date``
#: alone, which is a SETTLEMENT date: at or after the END of the thing. A "final
#: pre-event" leg drawn before it can sit anywhere inside the event, including
#: after the result was effectively known, and would make late forecasts look
#: brilliant for the reason that they were not forecasts.
PAIR_UNANCHORED_BOUNDARY = "unanchored_boundary"

#: A linked event with a start, but ``commence_time_source`` is NULL so nobody
#: can say where that start came from.
#:
#: 🔴 THIS IS DELIBERATELY ITS OWN CLASS AND IS DELIBERATELY EXCLUDED, and the
#: two decisions are separate. ``commence_time_is_a_reported_start(None)``
#: answers TRUE, and its docstring says why in as many words: most of the table
#: predates the column, and freezing ordinary state promotion for nearly every
#: event on the site is the larger error. That reasoning is about a PROMOTION
#: rule and does not transfer to a TRUTH measurement, where an unprovenanced
#: instant is exactly the thing we may not score against. So this module does
#: not widen the house predicate and does not narrow it — it counts the
#: population separately, so the walk reports what the strict choice COSTS
#: instead of burying it in another class.
PAIR_START_PROVENANCE_UNKNOWN = "start_provenance_unknown"

#: The start is a stand-in: a ticker date resolved to midnight UTC, or the clock
#: of the poll that minted the row. Delegated to the two house functions.
PAIR_START_NOT_REPORTED = "start_not_reported"

#: Our own columns contradict the start we hold — ``completed_at`` at or before
#: it (gotcha #46, a cross-event data merge), or a settlement more than
#: :data:`START_CONTRADICTION_TOLERANCE_SECONDS` before it.
PAIR_START_CONTRADICTED = "start_contradicted"

#: No single book holds both legs, but the union of books does. Stitching two
#: books together measures a margin difference, not a forecast change.
PAIR_LEGS_FROM_DIFFERENT_BOOKS = "legs_from_different_books"

#: No eligible observation at all before the start.
PAIR_NO_FINAL_NONE_BEFORE = "no_final_none_before"

#: An observation exists before the start, but we had stopped confirming it long
#: enough before that it cannot stand as the final price.
PAIR_NO_FINAL_STALE = "no_final_stale"

#: A usable final leg, but nothing at all before the early instant — we only
#: started watching inside the lead window.
PAIR_NO_EARLY_NONE_BEFORE = "no_early_none_before"

#: Something before the early instant, but not being confirmed near it.
PAIR_NO_EARLY_STALE = "no_early_stale"

#: The classes that yield two scorable probabilities. Everything else returns
#: ``None`` for both, so a caller cannot score a pair this module refused.
PAIRED_CLASSES: tuple[str, ...] = (PAIR_PAIRED, PAIR_PAIRED_UNCHANGED)

#: Every class, in the order the rule decides them. The order is load-bearing:
#: the first failure NAMES the exclusion, and provenance is settled before a
#: single snapshot is read.
PAIR_CLASSES: tuple[str, ...] = (
    PAIR_RESULT_NOT_INDEPENDENT,
    PAIR_UNANCHORED_BOUNDARY,
    PAIR_START_PROVENANCE_UNKNOWN,
    PAIR_START_NOT_REPORTED,
    PAIR_START_CONTRADICTED,
    PAIR_PAIRED,
    PAIR_PAIRED_UNCHANGED,
    PAIR_LEGS_FROM_DIFFERENT_BOOKS,
    PAIR_NO_FINAL_NONE_BEFORE,
    PAIR_NO_FINAL_STALE,
    PAIR_NO_EARLY_NONE_BEFORE,
    PAIR_NO_EARLY_STALE,
)


def forecast_kind(source: Any) -> str:
    """``"model"`` for a model output, ``"market"`` for a quoted price.

    One word on every row so the two can never be averaged together by accident;
    :func:`paired_improvement` refuses a cohort carrying both.
    """
    return "model" if source in MODEL_FORECAST_SOURCES else "market"


# ---------------------------------------------------------------------------
# The SQL half
# ---------------------------------------------------------------------------

#: The instant both legs are measured against. One expression, used everywhere,
#: so the final leg, the early leg and the freshness tests cannot drift apart.
_BOUNDARY = closing_line_boundary_sql("e.commence_time", "fm.resolution_date")

#: The columns a leg carries. ``last_seen_at`` is the header's note 6 — WHEN WE
#: LAST CONFIRMED THIS PRICE, not when the value was first written — and ``id``
#: is what tells a genuinely flat re-confirmed row (:data:`PAIR_PAIRED_UNCHANGED`)
#: from two distinct looks.
_LEG_COLUMNS = (
    "fos.id, fos.probability, fos.captured_at, "
    "COALESCE(fos.valid_until, fos.captured_at) AS last_seen_at"
)

#: The candidate population: resolved, graded, truth-eligible.
#:
#: ``is_winner IS NOT NULL`` is the graded-truth gate — NULL is ungraded truth,
#: never a loss.
#:
#: Truth-eligibility is rendered by :func:`calibration_truth_eligible_sql`, the
#: only sanctioned way to write it: the allowlist is keyed on
#: ``fo.resolution_source`` (HOW the outcome was graded), NOT on ``fm.source``
#: (which venue quoted it), and the function emits the D112 lone-claim shape term
#: with it as one unit. Interpolating the bare constant is what the drift-scan
#: test forbids, and reading it as a market-source list is the mistake it exists
#: to catch.
#:
#: ``n_outcomes_col`` is omitted deliberately: this module has no market-shape
#: join in scope, so the rendered predicate is the shape-blind allowlist, which
#: keeps the population identical to the other readers rather than silently
#: widening it.
_POPULATION_PREDICATE = f"""
      fm.status = 'resolved'
      AND fo.is_winner IS NOT NULL
      AND {calibration_truth_eligible_sql(source_col="fo.resolution_source")}
"""


def as_of_sql(instant: str, lead_seconds: int) -> str:
    """``instant`` moved back by ``lead_seconds`` — the early leg's own boundary.

    The early leg is not a different KIND of selection from the final one; it is
    the same "last eligible price before X" against an earlier X. Expressed as
    an interval on the shared boundary so the two can never be written by two
    different hands.
    """
    if not isinstance(lead_seconds, int) or lead_seconds <= 0:
        raise ValueError(f"lead_seconds must be a positive int, got {lead_seconds!r}")
    return f"({instant} - INTERVAL '{lead_seconds} seconds')"


def _fresh_sql(leg: str, instant: str, max_stale_seconds: int) -> str:
    """Whether ``leg`` was still being confirmed close enough to ``instant``.

    ``LEAST(last_seen_at, instant)`` caps a ``valid_until`` that runs past the
    instant: a row re-confirmed during the event tells us nothing about how
    fresh it was BEFORE the event, and letting it count would readmit exactly
    the post-start evidence rule 3 excludes.
    """
    if not isinstance(max_stale_seconds, int) or max_stale_seconds < 0:
        raise ValueError(
            f"max_stale_seconds must be a non-negative int, got {max_stale_seconds!r}"
        )
    return (
        f"EXTRACT(EPOCH FROM ({instant} - LEAST({leg}.last_seen_at, {instant})))"
        f" <= {max_stale_seconds}"
    )


def _leg_lateral(*, boundary: str, bookmaker: Optional[str] = None) -> str:
    """One leg: the last eligible quote before ``boundary``, optionally one book.

    Both legs go through :func:`closing_line_lateral_sql` at ``order="DESC"`` —
    there is no ``ASC`` selection in this module, because "the first snapshot we
    ever captured" is the defect CAL-P1330 removed (header note 5).
    """
    extra_and = "" if bookmaker is None else f"AND fos.bookmaker = {bookmaker}"
    return closing_line_lateral_sql(
        outcome_id="fo.id",
        boundary=boundary,
        extra_and=extra_and,
        order="DESC",
        columns=_LEG_COLUMNS,
    )


def start_is_reported_sql(
    commence_time: str = "e.commence_time",
    commence_time_source: str = "e.commence_time_source",
    created_at: str = "e.created_at",
) -> str:
    """The two house start-provenance functions, rendered as SQL.

    DERIVED from their own constants (``DERIVED_COMMENCE_SOURCES``,
    ``_POLL_CLOCK_FALLBACK_SOURCES`` via :func:`commence_time_was_never_a_kickoff`'s
    module, ``POLL_CLOCK_STAMP_TOLERANCE``) rather than re-listed, so a source
    added to either set reaches this predicate without anybody remembering this
    line. ``test_calibration_paired_prestart`` asserts the rendered lists equal
    the Python sets, both directions.

    The emitted expression assumes ``commence_time_source IS NOT NULL`` has
    already been decided by the caller — :data:`PAIR_START_PROVENANCE_UNKNOWN`
    is its own class and its own branch, for the reason that constant gives.

    Two SQL-only details that are not in the Python twin because Python does not
    have them:

    * ``EXTRACT(SECOND FROM ts) = 0`` is Postgres's single test for the Python
      pair ``second == 0 and microsecond == 0`` — ``SECOND`` carries the
      fractional part.
    * ``created_at`` is a bare ``DateTime`` on the model while ``commence_time``
      is ``DateTime(timezone=True)``, so subtracting them directly would be
      resolved at the session's timezone. ``AT TIME ZONE 'UTC'`` is the SQL
      spelling of the ``replace(tzinfo=utc)`` the Python helper already does.
    """
    derived = ", ".join(f"'{s}'" for s in sorted(DERIVED_COMMENCE_SOURCES))
    poll_clock = ", ".join(f"'{s}'" for s in sorted(_poll_clock_fallback_sources()))
    tolerance = int(POLL_CLOCK_STAMP_TOLERANCE.total_seconds())
    return f"""(
          {commence_time_source} NOT IN ({derived})
          AND NOT (
              {commence_time_source} IN ({poll_clock})
              AND EXTRACT(SECOND FROM {commence_time}) <> 0
              AND ABS(EXTRACT(EPOCH FROM (
                      {commence_time} - ({created_at} AT TIME ZONE 'UTC')
                  ))) <= {tolerance}
          )
      )"""


def start_is_contradicted_sql(
    commence_time: str = "e.commence_time",
    completed_at: str = "e.completed_at",
    resolution_date: str = "fm.resolution_date",
) -> str:
    """Our own columns disagreeing with the start we hold. See the class docs."""
    return f"""(
          ({completed_at} IS NOT NULL AND {completed_at} <= {commence_time})
          OR ({resolution_date} IS NOT NULL
              AND {resolution_date} < {commence_time}
                  - INTERVAL '{START_CONTRADICTION_TOLERANCE_SECONDS} seconds')
      )"""


def paired_legs_sql(
    *,
    lead_seconds: int = DEFAULT_LEAD_SECONDS,
    early_max_stale_seconds: int = DEFAULT_EARLY_MAX_STALE_SECONDS,
    final_max_stale_seconds: int = DEFAULT_FINAL_MAX_STALE_SECONDS,
    cursor: str = ":cursor",
    scan: str = ":scan",
) -> str:
    """Per-outcome early and final legs, with the whole pairing rule applied.

    Emits one row per candidate outcome, carrying ``pair_class`` so the callers
    that want the failures (the feasibility fold) and the caller that wants the
    pairs (the score) read the SAME statement rather than two that can disagree.

    THE SHAPE, and why it is three lateral groups rather than two:

    * ``pair_book`` walks this outcome's books in preference order (the market's
      NATIVE book first, then alphabetically) and returns the first that holds a
      fresh leg at BOTH instants. That book's two legs are the pair. Choosing on
      the book rather than on the freshest available leg is deliberate: shopping
      across books for whichever pair happens to look best is a selection effect
      dressed as a measurement.
    * ``union_early`` / ``union_final`` ignore the book. They exist only to tell
      :data:`PAIR_LEGS_FROM_DIFFERENT_BOOKS` (a pair exists, but only by
      stitching) from "there was never a pair", and to name WHICH leg failed and
      why — the four ``no_*`` classes.
    * Freshness is decided in the ``CASE``, not inside the union laterals, so a
      leg that exists but is stale reports ``*_stale`` instead of vanishing into
      ``*_none_before``. Two different findings; summing them would hide which.

    COST: one index seek per book per instant on ``idx_fos_outcome_captured``,
    plus two for the union. Futures rows carry one book for all but the handful
    of ``odds_api`` markets, so this is ~4 seeks per outcome in practice. If the
    admin ``db-query`` rail times out at 25s, halve ``scan`` — the walk is
    cursor-paged precisely so that costs a page, not a rewrite.

    ROW-BOUNDED, NOT ID-WIDTH (``census_reachability``'s measured lesson): outcome
    ids are not uniformly dense, so a fixed id span is a few thousand rows in one
    region and millions in another, while ``LIMIT`` costs about the same wherever
    it lands.

    ``cursor``/``scan`` default to bind-parameter names for a task caller. The
    admin ``db-query`` rail the measurement bus uses does not bind, so
    :func:`paired_feasibility_sql` passes literals instead — same statement,
    substituted in one place rather than paraphrased into a second one.
    """
    as_of_early = as_of_sql(_BOUNDARY, lead_seconds)
    early_fresh = _fresh_sql("early", as_of_early, early_max_stale_seconds)
    final_fresh = _fresh_sql("final", _BOUNDARY, final_max_stale_seconds)
    book_early_fresh = _fresh_sql("ef", as_of_early, early_max_stale_seconds)
    book_final_fresh = _fresh_sql("ff", _BOUNDARY, final_max_stale_seconds)
    return f"""
SELECT fo.id AS outcome_id,
       fm.source AS source,
       CASE WHEN fm.source IN ({", ".join(f"'{s}'" for s in sorted(MODEL_FORECAST_SOURCES))})
            THEN 'model' ELSE 'market' END AS forecast_kind,
       fm.event_id AS cluster_id,
       COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
       fo.is_winner AS is_winner,
       pair_book.bookmaker AS bookmaker,
       pair_book.early_probability AS early_probability,
       pair_book.early_captured_at AS early_captured_at,
       pair_book.final_probability AS final_probability,
       pair_book.final_captured_at AS final_captured_at,
       CASE
           WHEN e.commence_time IS NULL THEN '{PAIR_UNANCHORED_BOUNDARY}'
           WHEN e.commence_time_source IS NULL
               THEN '{PAIR_START_PROVENANCE_UNKNOWN}'
           WHEN NOT {start_is_reported_sql()} THEN '{PAIR_START_NOT_REPORTED}'
           WHEN {start_is_contradicted_sql()} THEN '{PAIR_START_CONTRADICTED}'
           WHEN pair_book.bookmaker IS NOT NULL
                AND pair_book.early_id = pair_book.final_id
               THEN '{PAIR_PAIRED_UNCHANGED}'
           WHEN pair_book.bookmaker IS NOT NULL THEN '{PAIR_PAIRED}'
           WHEN early.id IS NOT NULL AND final.id IS NOT NULL
                AND {early_fresh} AND {final_fresh}
               THEN '{PAIR_LEGS_FROM_DIFFERENT_BOOKS}'
           WHEN final.id IS NULL THEN '{PAIR_NO_FINAL_NONE_BEFORE}'
           WHEN NOT {final_fresh} THEN '{PAIR_NO_FINAL_STALE}'
           WHEN early.id IS NULL THEN '{PAIR_NO_EARLY_NONE_BEFORE}'
           ELSE '{PAIR_NO_EARLY_STALE}'
       END AS pair_class
FROM futures_outcomes fo
JOIN futures_markets fm ON fm.id = fo.market_id
LEFT JOIN events e ON e.id = fm.event_id
LEFT JOIN LATERAL {_leg_lateral(boundary=as_of_early)} early ON true
LEFT JOIN LATERAL {_leg_lateral(boundary=_BOUNDARY)} final ON true
LEFT JOIN LATERAL (
    SELECT b.bookmaker,
           ef.id AS early_id,
           ef.probability AS early_probability,
           ef.captured_at AS early_captured_at,
           ff.id AS final_id,
           ff.probability AS final_probability,
           ff.captured_at AS final_captured_at
    FROM (
        SELECT DISTINCT s.bookmaker
        FROM futures_odds_snapshots s
        WHERE s.outcome_id = fo.id
    ) b
    LEFT JOIN LATERAL {_leg_lateral(boundary=as_of_early, bookmaker="b.bookmaker")} ef ON true
    LEFT JOIN LATERAL {_leg_lateral(boundary=_BOUNDARY, bookmaker="b.bookmaker")} ff ON true
    WHERE ef.id IS NOT NULL AND ff.id IS NOT NULL
      AND {book_early_fresh} AND {book_final_fresh}
    ORDER BY (b.bookmaker <> fm.source), b.bookmaker
    LIMIT 1
) pair_book ON true
WHERE {_POPULATION_PREDICATE}
  AND fo.id > {cursor}
ORDER BY fo.id ASC
LIMIT {scan}
"""


def paired_feasibility_sql(
    *,
    lead_seconds: int = DEFAULT_LEAD_SECONDS,
    early_max_stale_seconds: int = DEFAULT_EARLY_MAX_STALE_SECONDS,
    final_max_stale_seconds: int = DEFAULT_FINAL_MAX_STALE_SECONDS,
    cursor: int = 0,
    scan: int = 200_000,
) -> str:
    """How many outcomes yield a usable pair, and why the rest do not — per source.

    This is the query that decides whether the page can answer Alex's question
    at all, so it reports the failure classes separately: "we never looked
    twice", "we stopped looking", "no single book held both" and "the start is a
    stand-in" are four different findings, and summing them into one "unusable"
    count would hide which one this is.

    ``n_events`` rides along beside ``n`` because the cluster count, not the
    outcome count, is what decides whether a margin may be published at all
    (:data:`MIN_CLUSTERS_FOR_MARGIN`) — measuring one without the other would
    promise a number the uncertainty rule then refuses.

    Literal ``cursor``/``scan`` (ints, not binds) so the statement can be pasted
    straight into the admin ``db-query`` rail, which is what the measurement lane
    actually reaches. Walk the population by feeding the previous window's
    ``MAX(outcome_id)`` back as ``cursor``.
    """
    if not isinstance(cursor, int) or not isinstance(scan, int):
        raise TypeError("cursor and scan are interpolated as literals; pass ints")
    return f"""
SELECT source,
       forecast_kind,
       pair_class,
       COUNT(*) AS n,
       COUNT(DISTINCT cluster_id) AS n_events,
       MIN(EXTRACT(EPOCH FROM (final_captured_at - early_captured_at))) AS min_gap_s,
       AVG(EXTRACT(EPOCH FROM (final_captured_at - early_captured_at))) AS avg_gap_s,
       MAX(EXTRACT(EPOCH FROM (final_captured_at - early_captured_at))) AS max_gap_s,
       MAX(outcome_id) AS max_outcome_id
FROM ({paired_legs_sql(
        lead_seconds=lead_seconds,
        early_max_stale_seconds=early_max_stale_seconds,
        final_max_stale_seconds=final_max_stale_seconds,
        cursor=str(cursor),
        scan=str(scan),
    )}) legs
GROUP BY source, forecast_kind, pair_class
ORDER BY source, forecast_kind, pair_class
"""


# ---------------------------------------------------------------------------
# The Python half — same semantics, so the decisions are testable without a DB
# ---------------------------------------------------------------------------


def _poll_clock_fallback_sources() -> frozenset:
    """The set :func:`commence_time_was_never_a_kickoff` keys its first arm on.

    Read from ``event_rails`` at call time rather than imported once, so this
    module cannot hold a stale copy of a set it does not own. The name is
    private there; reaching for it is deliberate and is the alternative to
    re-listing it here, which is what the header forbids. A rename there fails
    loudly at the first call instead of silently rendering an empty list.
    """
    from app.utils import event_rails

    sources = getattr(event_rails, "_POLL_CLOCK_FALLBACK_SOURCES", None)
    if not sources:
        raise RuntimeError(
            "event_rails._POLL_CLOCK_FALLBACK_SOURCES is missing or empty; "
            "start_is_reported_sql cannot render the poll-clock arm"
        )
    return frozenset(sources)


def start_refusal(event: Any, *, resolution_date: Any = None) -> Optional[str]:
    """``None`` when this event's start may be scored against; else the class.

    Delegates to the two house functions rather than restating either — see
    header note 7 and :data:`PAIR_START_PROVENANCE_UNKNOWN` for the one question
    this module answers differently from the promotion rules, and why.

    Args:
        event: the linked event row (duck-typed on ``commence_time``,
            ``commence_time_source``, ``created_at``, ``completed_at``), or
            ``None`` when the market has no linked event at all.
        resolution_date: ``fm.resolution_date``. Passed in rather than read off
            ``event`` because it lives on the MARKET — the whole
            :data:`PAIR_START_CONTRADICTED` case is the two rows disagreeing, so
            reading both off one object would make the check unable to fire.
    """
    if isinstance(event, datetime):
        # The pre-CAL-P1330 signature took a bare `commence_time`, and a
        # datetime read through getattr would answer "unanchored" for every row
        # — a wrong answer that looks like a finding. Refuse instead.
        raise TypeError(
            "start_refusal takes the event row, not a commence_time; "
            "the provenance columns are the whole point of the check"
        )
    if event is None or getattr(event, "commence_time", None) is None:
        return PAIR_UNANCHORED_BOUNDARY
    source = getattr(event, "commence_time_source", None)
    if source is None:
        return PAIR_START_PROVENANCE_UNKNOWN
    if not commence_time_is_a_reported_start(source):
        return PAIR_START_NOT_REPORTED
    if commence_time_was_never_a_kickoff(event):
        return PAIR_START_NOT_REPORTED
    if _start_is_contradicted(event, resolution_date):
        return PAIR_START_CONTRADICTED
    return None


def _start_is_contradicted(event: Any, resolution_date: Any) -> bool:
    """The Python twin of :func:`start_is_contradicted_sql`."""
    commence = _as_utc(getattr(event, "commence_time", None))
    if commence is None:
        return False
    completed = _as_utc(getattr(event, "completed_at", None))
    if completed is not None and completed <= commence:
        return True
    settled = _as_utc(resolution_date)
    if settled is None:
        return False
    return settled < commence - timedelta(seconds=START_CONTRADICTION_TOLERANCE_SECONDS)


def _as_utc(value: Any) -> Optional[datetime]:
    """Naive timestamps are UTC here, and both sides of every comparison say so.

    ``Event.created_at`` is a bare ``DateTime`` while ``commence_time`` is
    ``DateTime(timezone=True)``; subtracting one from the other raises
    ``TypeError``. That is a crash rather than a wrong answer, which is the good
    direction — but a crash still stops a walk, so normalise instead of assuming
    either side. Anything that is neither ``None`` nor a datetime is a caller
    bug and RAISES: returning ``None`` for it would silently turn a malformed
    row into "no start", which reads as a finding.
    """
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"expected a datetime or None, got {type(value).__name__}")
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def boundary_is_anchored(event: Any, *, resolution_date: Any = None) -> bool:
    """Whether this outcome's boundary is a start we may score a forecast against.

    Kept as a named yes/no beside :func:`start_refusal` because most callers
    only need the answer, and because the SQL branch, the Python mirror and
    every caller must be demonstrably asking one question.
    """
    return start_refusal(event, resolution_date=resolution_date) is None


def result_is_independent(
    is_winner: Any, resolution_source: Any, *, eligible_sources: Iterable[str]
) -> bool:
    """Whether the result was decided by something other than the price.

    ``eligible_sources`` is passed in rather than imported so a caller states
    which allowlist it is holding — the SQL's is
    :func:`calibration_truth_eligible_sql`'s, and a Python caller reading rows
    off that same statement has already had the filter applied.
    """
    if is_winner is None:
        return False
    return resolution_source in set(eligible_sources)


def _standing_leg(
    rows: Sequence[Sequence[Any]],
    instant: datetime,
    max_stale_seconds: int,
) -> tuple[Optional[tuple], str]:
    """The standing eligible price at ``instant``, with proof we were still looking.

    Rows are ``(captured_at, probability, yes_bid, yes_ask, bookmaker,
    valid_until)``. Returns ``(row, "ok" | "none_before" | "stale")``.

    Strictly before ``instant``: a row captured AT the instant is not a forecast
    made before it.
    """
    before = [
        row
        for row in rows
        if _as_utc(row[0]) < instant
        and is_eligible_closing_snapshot(row[1], row[2], row[3])
    ]
    if not before:
        return None, "none_before"
    row = max(before, key=lambda r: _as_utc(r[0]))
    last_seen = _as_utc(row[5]) or _as_utc(row[0])
    last_seen = min(last_seen, instant)
    if (instant - last_seen).total_seconds() > max_stale_seconds:
        return None, "stale"
    return row, "ok"


def classify_pair(
    snapshots: Iterable[Sequence[Any]],
    *,
    event: Any,
    market_source: Any = None,
    resolution_date: Any = None,
    is_winner: Any = None,
    resolution_source: Any = None,
    eligible_sources: Optional[Iterable[str]] = None,
    lead_seconds: int = DEFAULT_LEAD_SECONDS,
    early_max_stale_seconds: int = DEFAULT_EARLY_MAX_STALE_SECONDS,
    final_max_stale_seconds: int = DEFAULT_FINAL_MAX_STALE_SECONDS,
) -> tuple[str, Optional[float], Optional[float]]:
    """The whole rule in Python. Mirrors :func:`paired_legs_sql`'s CASE, in order.

    Args:
        snapshots: rows of ``(captured_at, probability, yes_bid, yes_ask,
            bookmaker, valid_until)``, in any order — sorted here rather than
            trusted, exactly as the SQL's ``ORDER BY`` does.
        event: the linked event row, or ``None``. See :func:`start_refusal`.
        market_source: ``fm.source``, used only to prefer the NATIVE book.
        resolution_date: the market's own settlement date, or ``None``.
        is_winner / resolution_source / eligible_sources: the result-independence
            gate. ``eligible_sources=None`` SKIPS it, which is correct for a
            caller reading rows off :func:`paired_legs_sql` (whose WHERE has
            already applied it) and wrong for anyone else — so it is explicit at
            the call site either way rather than defaulted to a silent answer.
            Supplied, it fails CLOSED: a missing ``is_winner`` is ungraded truth,
            never a loss (gotcha #21).

    Returns:
        ``(pair_class, early_probability, final_probability)``. The two
        probabilities are ``None`` for every class outside :data:`PAIRED_CLASSES`
        — a caller must not be able to score a pair this function refused.
    """
    if eligible_sources is not None and not result_is_independent(
        is_winner, resolution_source, eligible_sources=eligible_sources
    ):
        return PAIR_RESULT_NOT_INDEPENDENT, None, None

    # Provenance first, before any snapshot is looked at — the SQL's first CASE
    # branches. A leg drawn before a stand-in is not a pre-event forecast.
    refusal = start_refusal(event, resolution_date=resolution_date)
    if refusal is not None:
        return refusal, None, None

    start = _as_utc(getattr(event, "commence_time", None))
    resolution_date = _as_utc(resolution_date)
    if resolution_date is not None and resolution_date < start:
        start = resolution_date
    as_of_early = start - timedelta(seconds=lead_seconds)

    rows = list(snapshots)
    by_book: dict[Any, list[Sequence[Any]]] = {}
    for row in rows:
        by_book.setdefault(row[4], []).append(row)

    # The native book first, then alphabetically — one book supplies both legs,
    # and which book is decided BEFORE the legs are looked at so the choice
    # cannot be made by whichever pair scores best.
    for book in sorted(by_book, key=lambda b: (b != market_source, str(b))):
        early, _ = _standing_leg(by_book[book], as_of_early, early_max_stale_seconds)
        final, _ = _standing_leg(by_book[book], start, final_max_stale_seconds)
        if early is not None and final is not None:
            klass = PAIR_PAIRED_UNCHANGED if early is final else PAIR_PAIRED
            return klass, float(early[1]), float(final[1])

    union_early, why_early = _standing_leg(rows, as_of_early, early_max_stale_seconds)
    union_final, why_final = _standing_leg(rows, start, final_max_stale_seconds)
    if union_early is not None and union_final is not None:
        # A pair exists, but only by stitching two books together: that is a
        # margin difference, not a forecast change.
        return PAIR_LEGS_FROM_DIFFERENT_BOOKS, None, None
    if why_final != "ok":
        return (
            (
                PAIR_NO_FINAL_NONE_BEFORE
                if why_final == "none_before"
                else PAIR_NO_FINAL_STALE
            ),
            None,
            None,
        )
    return (
        (
            PAIR_NO_EARLY_NONE_BEFORE
            if why_early == "none_before"
            else PAIR_NO_EARLY_STALE
        ),
        None,
        None,
    )


# NOTE: the pre-CAL-P1330 ``select_paired_legs`` name is GONE, not aliased. It
# took ``(snapshots, *, event_commence, resolution_date, min_separation_seconds)``
# and returned the FIRST-ever snapshot as the early leg — the defect header note
# 5 removes. An alias would have kept the old call sites compiling while
# silently answering a different question, which is the worse of the two
# failures; a NameError names itself. Nothing outside this module's own tests
# imported it (grepped on master at 7eb1f61bf).


# ---------------------------------------------------------------------------
# Proper scores. Defined here because the backend had none — and the two
# published numbers must come from ONE definition, not one per leg.
# ---------------------------------------------------------------------------

#: Log loss is unbounded at p in {0, 1}. Eligibility already rejects those
#: (``0 < p < 1``), so this clamp should never bind; it is here so that a caller
#: passing unfiltered rows gets a large finite penalty rather than ``inf``
#: silently poisoning a mean.
_LOG_EPS = 1e-9

#: Ties are exact-zero deltas in principle, but both legs are floats read off a
#: ``Numeric(7,6)`` column, so "did not change" needs a tolerance rather than an
#: equality. Smaller than the column's own resolution by three orders of
#: magnitude, so it can only absorb float noise, never a real move.
_UNCHANGED_EPS = 1e-12


def brier(probability: float, is_winner: bool) -> float:
    """Squared error of one forecast. Lower is better; range [0, 1]."""
    return (float(probability) - (1.0 if is_winner else 0.0)) ** 2


def log_loss(probability: float, is_winner: bool) -> float:
    """Negative log likelihood of one forecast. Lower is better."""
    p = min(max(float(probability), _LOG_EPS), 1.0 - _LOG_EPS)
    return -math.log(p) if is_winner else -math.log(1.0 - p)


def paired_improvement(
    pairs: Iterable[tuple[float, float, bool]],
    *,
    score: str = "brier",
    cluster_ids: Optional[Sequence[Any]] = None,
    forecast_kinds: Optional[Sequence[str]] = None,
    min_clusters_for_margin: int = MIN_CLUSTERS_FOR_MARGIN,
) -> Optional[dict[str, Any]]:
    """Mean per-outcome score improvement from the early leg to the final leg.

    Args:
        pairs: ``(early_probability, final_probability, is_winner)`` — one tuple
            per OUTCOME. Both probabilities describe the same question and the
            same resolution, which is the entire point of the pairing.
        score: ``"brier"`` or ``"log_loss"``.
        cluster_ids: one ``event_id`` per pair, in the same order. Both sides of
            a game, every leg of a props container and the same question on two
            venues are ONE piece of evidence about the world; without this the
            error bar counts them as two and is too narrow. **Omitting it does
            not produce a publishable margin** — ``displayable_margin`` is
            ``None`` — because a number whose clustering nobody declared cannot
            be defended.
        forecast_kinds: one of ``"market"``/``"model"`` per pair. Supplied, a
            MIXED cohort RAISES: a model output and a quoted price answer
            different questions and averaging them is not a number of anything.
        min_clusters_for_margin: below this many distinct clusters, no margin is
            published at all — not a wide one.

    Returns:
        ``None`` when there is nothing to report — an empty cohort, or a single
        pair, for which a standard error does not exist. **Never ``0.0``**: a
        perfect-looking score standing in for no data is gotcha #53 at the top of
        this product's most-cited number.

        Otherwise a dict whose ``mean_delta = mean(early_score - final_score)``,
        so a **POSITIVE ``mean_delta`` means the final pre-event forecast scored
        BETTER** than the early one. The sign convention is stated here because
        it is the sentence a reader will be shown, and getting it backwards
        inverts the product's claim.

        ``se`` is the naive standard error OF THE PAIRED DIFFERENCE — computed on
        the per-outcome deltas, not from the two means. The legs are strongly
        correlated (same question, a day apart), so an unpaired error bar
        computed from two marginal variances would be far too wide and would
        report "no detectable change" on a real one. It is still NOT the
        publishable margin: ``cluster_se`` is, and only when
        ``displayable_margin`` is not ``None``.

        ``events_improved`` / ``events_worse`` / ``events_unchanged`` count
        CLUSTERS, and a cluster that got worse is reported like any other. A
        result that contradicts the hoped-for improvement is the result.
    """
    if score not in ("brier", "log_loss"):
        raise ValueError(f"unknown score {score!r}")
    fn = brier if score == "brier" else log_loss

    rows = list(pairs)
    if forecast_kinds is not None:
        kinds = list(forecast_kinds)
        if len(kinds) != len(rows):
            raise ValueError("forecast_kinds must have one entry per pair")
        distinct = set(kinds)
        if len(distinct) > 1:
            raise ValueError(
                "market prices and model forecasts must not be pooled: "
                f"cohort carries {sorted(distinct)}. Score them as separate sets."
            )
    clusters = None if cluster_ids is None else list(cluster_ids)
    if clusters is not None and len(clusters) != len(rows):
        raise ValueError("cluster_ids must have one entry per pair")

    deltas: list[float] = []
    early_scores: list[float] = []
    final_scores: list[float] = []
    for early_p, final_p, is_winner in rows:
        e = fn(early_p, is_winner)
        f = fn(final_p, is_winner)
        early_scores.append(e)
        final_scores.append(f)
        deltas.append(e - f)

    n = len(deltas)
    if n < 2:
        return None

    mean_delta = sum(deltas) / n
    variance = sum((d - mean_delta) ** 2 for d in deltas) / (n - 1)
    out: dict[str, Any] = {
        "n": n,
        "mean_delta": mean_delta,
        "se": math.sqrt(variance / n),
        "early_mean": sum(early_scores) / n,
        "final_mean": sum(final_scores) / n,
        # The pre-CAL-P1330 key. Kept so a reader of either name gets the same
        # number rather than a KeyError on one of them.
        "late_mean": sum(final_scores) / n,
        "n_events": None,
        "cluster_se": None,
        "displayable_margin": None,
        "events_improved": None,
        "events_worse": None,
        "events_unchanged": None,
    }
    if clusters is None:
        return out

    by_cluster: dict[Any, list[float]] = {}
    for key, delta in zip(clusters, deltas):
        by_cluster.setdefault(key, []).append(delta)
    g = len(by_cluster)
    out["n_events"] = g
    out["events_improved"] = sum(
        1 for v in by_cluster.values() if sum(v) > _UNCHANGED_EPS
    )
    out["events_worse"] = sum(
        1 for v in by_cluster.values() if sum(v) < -_UNCHANGED_EPS
    )
    out["events_unchanged"] = sum(
        1 for v in by_cluster.values() if abs(sum(v)) <= _UNCHANGED_EPS
    )
    if g > 1:
        # CR1 cluster-robust standard error of the mean: residual SUMS per
        # cluster, with the usual small-G correction. With one outcome per
        # cluster it collapses to the naive SE (up to the correction), which is
        # the sanity check the tests assert.
        meat = sum((sum(v) - len(v) * mean_delta) ** 2 for v in by_cluster.values())
        out["cluster_se"] = math.sqrt(g / (g - 1) * meat) / n
        if g >= min_clusters_for_margin:
            out["displayable_margin"] = out["cluster_se"]
    return out


def leg_calibration(
    pairs: Iterable[tuple[float, float, bool]],
    *,
    min_bin_n: int = 0,
) -> dict[str, Optional[float]]:
    """ECE of each leg, over the SAME paired population. Reported separately.

    Alex asked for the proper-score comparison and the calibration comparison to
    be kept apart, and they answer different questions: a forecast can sharpen
    (better Brier) while drifting off the diagonal (worse ECE). Binning and the
    error itself are :mod:`app.utils.calibration_ece`'s, imported so this cannot
    disagree with the curve about what an ECE is.

    ``min_bin_n`` defaults to 0 here, not to the production floor: the paired
    population is a strict subset of the published one and will be small, so a
    floor borrowed from the full curve would silently empty it. The caller sets
    the floor it can defend and states it.
    """
    early_bins: dict[int, dict[str, float]] = {}
    final_bins: dict[int, dict[str, float]] = {}
    for early_p, final_p, is_winner in pairs:
        won = 1 if is_winner else 0
        for value, bins in ((early_p, early_bins), (final_p, final_bins)):
            b = bins.setdefault(
                bin_index(float(value)), {"n": 0, "winners": 0, "sum_prob": 0.0}
            )
            b["n"] += 1
            b["winners"] += won
            b["sum_prob"] += float(value)
    return {
        "early_ece_pp": calibration_error(early_bins.values(), min_bin_n=min_bin_n),
        "late_ece_pp": calibration_error(final_bins.values(), min_bin_n=min_bin_n),
    }
