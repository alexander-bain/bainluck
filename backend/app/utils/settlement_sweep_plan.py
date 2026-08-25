"""Which markets the weekly capture sweep takes, and in what order.

Queue 389 Item 1 (#2077). Pure planning logic: no DB, no HTTP, so the ordering
policy — the part that decides what survives — is testable without either.

THE SCHEDULE, AND WHY IT IS DATES AND NOT A BACKLOG
---------------------------------------------------

C-CLIFF-CENSUS-1 (2026-08-21) turned the hole into a burn-down with deadlines, and
C-PM-RETENTION-1 then cut it down to Kalshi alone (Polymarket Gamma has no cliff:
0 of 70 records gone across 30 days to 3.66 years, so its 250,526 are a bulk
re-poll with no clock). What is left is small and dated:

    bucket        deadline        kalshi missing      note
    -----------------------------------------------------------------------
    0-7           2026-08-28      1,202               dies first
    8-14          2026-09-04      1,064
    15-30         2026-09-20      2,511
    31-60         2026-10-20      7,959
    61-74         2026-11-03      10,420              largest
                                  ------
                                  23,156 total, ~310/day burn

**A bucket's deadline is an acceptance date, not an aspiration.** A sweep that runs
after it does not partially succeed; the rows are gone, permanently, and no later
effort recovers them at any price. That asymmetry is the whole reason this module
exists as an explicit ordering policy rather than an ``ORDER BY resolution_date``.

THE HONEST DENOMINATOR — three ways a settlement is unreachable, and only one is a clock
------------------------------------------------------------------------------------------

The sweep's coverage number is meaningless unless the population it divides by excludes
what no sweep can ever reach. Three classes are permanently out, for three different
reasons, and collapsing them would make the burn-down report a debt it can never pay:

* **``PURGED`` — retention.** Kalshi drops a settled market's record. A clock, and the
  only one of the three the weekly sweep races.
* **``PRICE_UNDETERMINABLE`` — form.** Polymarket's ``no_resolved`` class
  (C-DEGRADED-FORM-1, ~8k, all 365+ days): the source still holds the record and the
  record never carried a price. Nothing was lost; nothing will arrive.
* **``no_eid`` — INGESTION.** ~153k Polymarket rows for which we never stored
  ``polymarket_event_id``. C-EID-RECOVERY-1's verdict: **unverifiable by source
  design** — there is no public ``conditionId`` → event route, so the key cannot be
  recovered from outside. The capture sweep cannot save these at any speed.

**The third one is the lesson of this whole program repeated one layer up, and it is
worth saying plainly: the mapping EXISTED at ingest and is unrecoverable afterwards.**
Retention gave us ~66 days to capture what Kalshi holds; ingestion gave us one instant,
and we did not take it. The fix-forward is therefore not a sweep but a WRITE at mint
time — store the id when it is in front of us — and it is a near-term item pending
C-INGEST-EID-AUDIT-1's answer to whether ingestion still mints eventless rows today.
A sweep can chase a closing window. It cannot chase a closed one.

So the determinable population is **~404.8k**, and the committed scope is
**Kalshi-weekly (dated) + Polymarket-on-demand (undated)**.

THE ORDERING, WHICH IS NOT SIMPLY "OLDEST FIRST"
------------------------------------------------

Two true things pull in opposite directions:

* The **0-7 bucket dies first** — on 2026-08-28, the first sweep's own date.
* The **61-74 bucket is the largest** (10,420 of 23,156) and is where the hole
  actually is.

"Oldest first" alone starves the big bucket; "biggest first" alone lets the
terminal bucket expire *during the sweep that was supposed to save it*. Gotcha #41
is this exact family in both directions: ordering newest-first never reaches the
old tail, and oldest-first without a floor grinds the already-dead first. **Ordering
is never the whole answer — ask what the ordering starts on.**

So the policy is: **terminal bucket to exhaustion, then the rest by deadline.** The
terminal bucket is tiny (1,202) and unrepeatable; everything else gets another
sweep next week. A reserved share guarantees the big bucket still makes progress in
week one rather than waiting for the small buckets to be perfect.

AND THEN A THIRD TRUE THING, WHICH BROKE THE OTHER TWO (#2175, 2026-08-24)
--------------------------------------------------------------------------

Ordering by deadline alone assumes every row in a bucket is equally likely to
answer. They are not. The 2026-08-24 run measured the terminal bucket owing 568
rows: **0** never probed, 227 stuck on ``rate_limited`` (a channel failure — see
#2174), and **341 carrying ``ambiguous_empty``** — a 200 whose body could not
distinguish absence from emptiness, correctly recorded as not-a-fact and therefore
correctly non-terminal.

Non-terminal means re-probed. Oldest-first means re-probed FIRST. And those 341
are the oldest rows in the bucket. So every pass spent its budget re-asking the
markets least likely to answer, ahead of the ones a retry would have fixed:
614 -> 594 -> 577 -> 568 owed, freeing 20, then 17, then 9. **Decelerating.**

The fix is not to make ``ambiguous_empty`` terminal — that promotes "we could not
tell" into "we have our answer", which is the conversion this program exists to
refuse. The fix is that the planner now knows what has already been ASKED of a
candidate, and tiers on it inside the bucket. See :func:`order_candidates`.

**The general clause, which outlives this case:** an ordering over a population
that gets re-offered every cycle must be a function of the answers already
received, not only of the deadline. Otherwise the rows that cannot answer are
exactly the rows that get asked the most. That is gotcha #41's family again — "ask
what the ordering starts on" — one turn further round: ask what it starts on *the
second time*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from app.utils.kalshi_retention import CAPTURE_PLANNING_AGE_DAYS, _age_days
from app.utils.settlement_truth import is_stable_nonanswer

#: Bucket edges in DAYS REMAINING against the capture-planning horizon, ordered by
#: deadline. ``(label, lower_inclusive, upper_inclusive)``.
BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("0-7", 0, 7),
    ("8-14", 8, 14),
    ("15-30", 15, 30),
    ("31-60", 31, 60),
    ("61-74", 61, 74),
)

#: Rows already PAST the capture-planning horizon. Not "gone" — see
#: :func:`bucket_for` — and deliberately ranked ahead of every dated bucket.
OVERDUE_BUCKET = "overdue"

#: The bucket whose contents expire before the next weekly sweep. It is taken to
#: exhaustion before anything else, and it is the only bucket with that privilege.
TERMINAL_BUCKET = "0-7"

#: Buckets that get the exhaustion privilege. ``overdue`` joined ``0-7`` on
#: 2026-08-24: "the bucket that stops existing" describes a row 20 days past the
#: horizon at least as well as one with 5 days left, and under non-monotonic
#: retention the overdue row is the likelier of the two to vanish next. Giving 0-7
#: priority over it would spend the budget in deadline order on a population whose
#: deadlines have been shown not to be ordered.
TERMINAL_BUCKETS: frozenset[str] = frozenset({OVERDUE_BUCKET, TERMINAL_BUCKET})

#: Minimum share of a sweep's budget reserved for NON-terminal buckets, so a large
#: terminal bucket (or a stuck one) cannot consume a whole week's capacity and leave
#: the 10,420-row bucket untouched. Starvation in the other direction is still
#: starvation.
NON_TERMINAL_RESERVE = 0.5

#: Attempt tiers, INSIDE a deadline bucket. See :func:`attempt_tier`.
TIER_NEVER_PROBED = 0
TIER_TRANSIENT_ONLY = 1
TIER_STABLE_NONANSWER = 2


@dataclass(frozen=True)
class Candidate:
    """A market nominated for probing. A nomination is never evidence."""

    market_id: int
    source: str
    external_id: str
    resolution_date: datetime | None
    candidate_reason: str

    #: How many times ANY sweep has already probed this market. Zero means the
    #: capture table has never held a row for it.
    attempts: int = 0
    #: Of those attempts, how many produced a non-answer the source would simply
    #: repeat (``ambiguous_empty`` and friends). See :func:`attempt_tier` for why
    #: this is counted EVER rather than read off the latest row.
    stable_nonanswers: int = 0

    def days_remaining(self, now: datetime | None = None) -> float | None:
        age = _age_days(self.resolution_date, now)
        return None if age is None else CAPTURE_PLANNING_AGE_DAYS - age

    def attempt_tier(self) -> int:
        """How much another call to this market is worth. Lower is worth more."""
        if self.attempts <= 0:
            return TIER_NEVER_PROBED
        if self.stable_nonanswers <= 0:
            return TIER_TRANSIENT_ONLY
        return TIER_STABLE_NONANSWER


def attempt_tier_from_dispositions(dispositions) -> int:
    """Tier a market from its capture history — the mapping used to build candidates.

    **Ever, not last.** A market that answered ``ambiguous_empty`` on Monday and
    ``rate_limited`` on Tuesday is tier 2, not tier 1: the source has already told
    us what it will say, and a later 429 does not un-tell it. Reading only the
    most recent row would let one transient failure promote a known-unanswerable
    market back to the head of the queue, which is the livelock wearing a hat.
    """
    attempts = 0
    stable = 0
    for disposition in dispositions:
        attempts += 1
        if is_stable_nonanswer(disposition):
            stable += 1
    if attempts <= 0:
        return TIER_NEVER_PROBED
    return TIER_TRANSIENT_ONLY if stable <= 0 else TIER_STABLE_NONANSWER


def bucket_for(days_remaining: float | None) -> str:
    """Name the bucket a candidate falls in.

    ``overdue`` and ``future`` are named rather than dropped: a sweep that silently
    filters them reports a clean run over a population it never defined, and the
    difference between "nothing to do" and "we excluded it" is exactly the
    distinction gotcha #53 is about.

    ``overdue`` WAS CALLED ``expired``, AND THE RENAME IS THE POINT (2026-08-24).
    "Expired" asserts the row is gone. C-KALSHI-RETENTION-1 falsified exactly that
    claim: retention is non-monotonic, so being past the planning horizon is not
    evidence of loss — 68-day markets are still present with 100 trades while
    54-day siblings in the same series are purged. The only constant permitted to
    say a row is unreachable is ``PROVABLY_PURGED_AGE_DAYS`` (86d), and rows past
    it never reach this function: they are excluded upstream by
    ``recovery_window_start``. So EVERY candidate this names is still possibly
    recoverable, and a past-horizon row is the most urgent thing in the queue
    rather than the least. See :func:`order_candidates` for the ordering half.

    THE EDGES ARE FLOORED, AND THAT IS NOT A ROUNDING PREFERENCE. ``days_remaining``
    is a float over a continuous clock, but :data:`BUCKETS` is written in whole days
    with INCLUSIVE ends — so ``0-7`` then ``8-14`` leaves the open interval
    ``(7, 8)`` in no bucket at all. Before this floor, a row with 7.4 days of life
    fell through every branch and was named ``future``: sorted BEHIND the 61-74
    bucket by :func:`order_candidates`, and reported to a human as not-yet-at-risk
    while it was eight days from being unrecoverable. Measured against production
    2026-08-24, the four such gaps — ``(7,8) (14,15) (30,31) (60,61)`` — held 1,201
    of the 20,499 in-window rows, 149 of them in the gap adjacent to the terminal
    bucket.

    Flooring closes all four and rounds toward URGENCY: 7.9 days remaining is
    treated as 7, landing in the terminal bucket that is taken to exhaustion.
    Over-including into the more urgent bucket costs a probe; under-including costs
    the row.
    """
    if days_remaining is None:
        return "unknown"
    if days_remaining < 0:
        return OVERDUE_BUCKET
    whole = math.floor(days_remaining)
    for label, low, high in BUCKETS:
        if low <= whole <= high:
            return label
    return "future"


def order_candidates(
    candidates: list[Candidate], now: datetime | None = None
) -> list[Candidate]:
    """Deadline bucket first, then what a call is WORTH, then oldest, then id.

    THE SECOND KEY IS THE #2175 FIX, AND ITS POSITION IS THE WHOLE POINT
    --------------------------------------------------------------------

    Until 2026-08-24 the key was ``(bucket, days_remaining, market_id)``. Both of
    those are right and together they livelocked the terminal bucket, because the
    rows carrying ``ambiguous_empty`` ARE the oldest rows in it. Oldest-first
    handed the head of every pass to 341 markets the source had already declined
    to answer, ahead of 227 whose only problem was a 429. Three paced passes
    freed 20, then 17, then 9 rows. Decelerating: the sweep was paying full price
    to re-learn the same nothing.

    So the tier goes INSIDE the bucket and AHEAD of the age:

        (bucket_rank, attempt_tier, attempts, days_remaining, market_id)

    * ``bucket_rank`` stays outermost. A dying 0-7 row still outranks a fresh
      61-74 row no matter how many times it has been asked — the terminal bucket
      is the one that stops existing, and ``NON_TERMINAL_RESERVE`` is what
      protects the big bucket from it. Demoting a bucket for its history would
      trade a permanent loss for a temporary one. Since 2026-08-24 ``overdue``
      is rank 0, ahead of every dated bucket, for the reason given inline in the
      body: past-the-horizon is not evidence of loss, so it is the most urgent
      rank rather than the last one.
    * ``attempt_tier`` then prefers never-probed over channel-failed over
      already-answered-nothing.
    * ``attempts`` spreads the re-asks within a tier, so a row asked five times
      yields to one asked once instead of monopolising the retry budget.
    * ``days_remaining`` and ``market_id`` are unchanged and still break every
      remaining tie.

    Nothing is dropped and nothing becomes terminal: tier-2 rows are still probed
    with whatever budget survives the rows that can actually move. The fix is an
    ORDER, not an exclusion, and :func:`plan_sweep`'s ``skipped_by_bucket`` still
    reports anything the budget left behind.

    Deterministic to the row: ties break on ``market_id``. A non-deterministic order
    under a budget cap means the rehearsal and the run can select different rows
    while both report the same count — the identity-vs-cardinality confusion that
    returned BLOCK on the delete rail.
    """
    now = now or datetime.now(timezone.utc)
    # `overdue` is rank 0 and the dated buckets follow it. Until 2026-08-24 it was
    # LAST, on the reasoning that an expired row "cannot be saved" — which
    # C-KALSHI-RETENTION-1 disproved: purges begin at 47d and are non-monotonic, so
    # past-the-horizon means "we are late", never "it is gone". Everything that
    # provably cannot be saved is already excluded by the 86-day skip-work bound
    # before it becomes a candidate, so nothing reaching here is unsalvageable and
    # the most overdue row is the most urgent one. Sorting it last meant the fix for
    # the 47-day finding — lowering the horizon — would have DEMOTED every row it
    # newly caught, making the sweep worse the more accurate its constants got.
    bucket_rank = {OVERDUE_BUCKET: 0}
    bucket_rank.update({label: i + 1 for i, (label, _, _) in enumerate(BUCKETS)})
    # `future` then `unknown` still sort last: one genuinely has time, the other
    # cannot be scheduled at all. Neither may displace a row that is running out.
    _FUTURE_RANK = len(BUCKETS) + 1
    _UNKNOWN_RANK = len(BUCKETS) + 2

    def key(c: Candidate) -> tuple[int, int, int, float, int]:
        remaining = c.days_remaining(now)
        label = bucket_for(remaining)
        rank = bucket_rank.get(
            label, _FUTURE_RANK if label == "future" else _UNKNOWN_RANK
        )
        return (
            rank,
            c.attempt_tier(),
            c.attempts,
            remaining if remaining is not None else 1e9,
            c.market_id,
        )

    return sorted(candidates, key=key)


def plan_sweep(
    candidates: list[Candidate], budget: int, now: datetime | None = None
) -> tuple[list[Candidate], dict[str, int]]:
    """Choose this run's work list, and report what was left behind.

    Returns ``(selected, skipped_by_bucket)``. **The second element is not
    bookkeeping** — a sweep that caps coverage without saying what it dropped reads
    as "covered everything" when it did not, and the burn-down is the one place
    that lie is unrecoverable.
    """
    now = now or datetime.now(timezone.utc)
    ordered = order_candidates(candidates, now)

    terminal = [c for c in ordered if bucket_for(c.days_remaining(now)) in TERMINAL_BUCKETS]
    rest = [c for c in ordered if bucket_for(c.days_remaining(now)) not in TERMINAL_BUCKETS]

    # The terminal bucket is taken to exhaustion, but never past the point where
    # the reserve for everything else would be consumed.
    max_terminal = budget if not rest else int(budget * (1.0 - NON_TERMINAL_RESERVE))
    if len(terminal) <= max_terminal or not rest:
        selected = terminal[:budget]
    else:
        selected = terminal[:max_terminal]

    remaining_budget = budget - len(selected)
    selected = selected + rest[:remaining_budget]

    chosen = {c.market_id for c in selected}
    skipped: dict[str, int] = {}
    for c in ordered:
        if c.market_id in chosen:
            continue
        label = bucket_for(c.days_remaining(now))
        skipped[label] = skipped.get(label, 0) + 1

    return selected, skipped


#: Human-readable names for the tiers, used by the sweep report.
TIER_NAMES: dict[int, str] = {
    TIER_NEVER_PROBED: "never_probed",
    TIER_TRANSIENT_ONLY: "transient_only",
    TIER_STABLE_NONANSWER: "stable_nonanswer",
}


def tier_counts(candidates: list[Candidate]) -> dict[str, int]:
    """Selection by probe-history tier — the livelock's vital sign.

    Reported rather than merely computed. A pass that selects mostly
    ``stable_nonanswer`` rows is re-asking markets the source has already declined,
    and before #2175 that fact was invisible: the run looked identical to a healthy
    one right up until the dispositions came back the same as last time. A number
    that only appears in the postmortem is a number that arrives too late.
    """
    counts: dict[str, int] = {}
    for c in candidates:
        label = TIER_NAMES.get(c.attempt_tier(), "unknown")
        counts[label] = counts.get(label, 0) + 1
    return counts


def burn_down(candidates: list[Candidate], now: datetime | None = None) -> dict[str, int]:
    """Population by bucket — the report that proves a deadline was or was not met."""
    now = now or datetime.now(timezone.utc)
    counts: dict[str, int] = {}
    for c in candidates:
        label = bucket_for(c.days_remaining(now))
        counts[label] = counts.get(label, 0) + 1
    return counts
