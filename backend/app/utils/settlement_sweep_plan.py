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
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.utils.kalshi_retention import CAPTURE_PLANNING_AGE_DAYS, _age_days

#: Bucket edges in DAYS REMAINING against the capture-planning horizon, ordered by
#: deadline. ``(label, lower_inclusive, upper_inclusive)``.
BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("0-7", 0, 7),
    ("8-14", 8, 14),
    ("15-30", 15, 30),
    ("31-60", 31, 60),
    ("61-74", 61, 74),
)

#: The bucket whose contents expire before the next weekly sweep. It is taken to
#: exhaustion before anything else, and it is the only bucket with that privilege.
TERMINAL_BUCKET = "0-7"

#: Minimum share of a sweep's budget reserved for NON-terminal buckets, so a large
#: terminal bucket (or a stuck one) cannot consume a whole week's capacity and leave
#: the 10,420-row bucket untouched. Starvation in the other direction is still
#: starvation.
NON_TERMINAL_RESERVE = 0.5


@dataclass(frozen=True)
class Candidate:
    """A market nominated for probing. A nomination is never evidence."""

    market_id: int
    source: str
    external_id: str
    resolution_date: datetime | None
    candidate_reason: str

    def days_remaining(self, now: datetime | None = None) -> float | None:
        age = _age_days(self.resolution_date, now)
        return None if age is None else CAPTURE_PLANNING_AGE_DAYS - age


def bucket_for(days_remaining: float | None) -> str:
    """Name the bucket a candidate falls in.

    ``expired`` and ``future`` are named rather than dropped: a sweep that silently
    filters them reports a clean run over a population it never defined, and the
    difference between "nothing to do" and "we excluded it" is exactly the
    distinction gotcha #53 is about.
    """
    if days_remaining is None:
        return "unknown"
    if days_remaining < 0:
        return "expired"
    for label, low, high in BUCKETS:
        if low <= days_remaining <= high:
            return label
    return "future"


def order_candidates(
    candidates: list[Candidate], now: datetime | None = None
) -> list[Candidate]:
    """Deadline order, terminal bucket first, oldest-within-bucket first.

    Deterministic to the row: ties break on ``market_id``. A non-deterministic order
    under a budget cap means the rehearsal and the run can select different rows
    while both report the same count — the identity-vs-cardinality confusion that
    returned BLOCK on the delete rail.
    """
    now = now or datetime.now(timezone.utc)
    bucket_rank = {label: i for i, (label, _, _) in enumerate(BUCKETS)}

    def key(c: Candidate) -> tuple[int, float, int]:
        remaining = c.days_remaining(now)
        label = bucket_for(remaining)
        # `expired` and `unknown` sort last: they cannot be saved (expired) or
        # cannot be scheduled (unknown), so they must never displace a row that can.
        rank = bucket_rank.get(label, len(BUCKETS) + (0 if label == "future" else 1))
        return (rank, remaining if remaining is not None else 1e9, c.market_id)

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

    terminal = [c for c in ordered if bucket_for(c.days_remaining(now)) == TERMINAL_BUCKET]
    rest = [c for c in ordered if bucket_for(c.days_remaining(now)) != TERMINAL_BUCKET]

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


def burn_down(candidates: list[Candidate], now: datetime | None = None) -> dict[str, int]:
    """Population by bucket — the report that proves a deadline was or was not met."""
    now = now or datetime.now(timezone.utc)
    counts: dict[str, int] = {}
    for c in candidates:
        label = bucket_for(c.days_remaining(now))
        counts[label] = counts.get(label, 0) + 1
    return counts
