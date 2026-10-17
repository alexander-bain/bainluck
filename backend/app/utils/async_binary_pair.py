"""#11157 — which raw observations of a Yes/No pair answer for one another's scale.

PILLARS: TRUTH / FORMATTING. SHIP: a market chart shows its genuine probability
move without inventing observation times or freshness.

WHY A RULE BEYOND THE EXACT INSTANT. Polymarket's CLOB `prices-history` stamps
each token at its own second: market 65678073 at fidelity=1 has Yes 461 points
and No 459 with ZERO shared instants (Live, #11157 comment 6229278103). PR
#11160 paired exact instants only, so on the venue's real shape it pairs
nothing and `/history` refuses every point.

WHERE THE RULE RUNS. ONCE, in the fill, on each leg's RAW series (after
layering and the last-good merge, before compaction), and the decision is
written into the bank as an annotation on both points (`VenuePoint.pair_at` /
`peer_at`). The reader never re-pairs: it VERIFIES the annotation (lane1's I2).
That is the point of running it here — ambiguity is a property of the raw
series, and a reader looking at compacted rows can see a sample as unique
because compaction dropped its neighbour.

WHAT A PAIR IS (lane1's invariants I4–I6, 2026-10-17 early review):
  * same tier label — one call, one fidelity; never across tiers (I5);
  * |skew| ≤ S, where S = min(`PAIR_SKEW_MAX_SECONDS`, half the declared grain,
    half of each sample's own local spacing in its leg). An undeclared grain
    gives S = 0, so it pairs only at an exact shared instant (I4);
  * one-to-one: a sample with two candidates within S pairs with neither, and a
    pair stands only when each is the other's ONLY candidate (I4/I6).

WHAT A PAIR IS NOT. It is not a claim of simultaneity, and it moves no clock:
each half keeps its own raw instant everywhere (I1). `pair_at` — the later of
the two raw instants — is KNOWLEDGE time, the first instant both values
existed, and is never written into an observation field.

S IS PROVISIONAL. Lane1 sets S from the measured per-tier skew distribution
(evidence E1, Live's). Until E1 lands, the 30 s ceiling is lane1's stated upper
bound; one specimen's quoted minute (Yes :23, No :20) is a 3 s skew.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta
from typing import Sequence

from app.utils.futures_chart_series import declared_resolution_seconds

#: Lane1's I4 ceiling on the skew between two halves of one pair. Not the grain:
#: a grain is how often the venue was asked, not how far apart two tokens' quotes
#: may sit and still describe one moment.
PAIR_SKEW_MAX_SECONDS = 30.0

#: Lane1's I7 refusal guard: an admitted pair whose two raw values disagree with
#: a complementary book by more than this is withheld and counted. It catches a
#: mixed pair across a move; it is never evidence of identity or of a clock.
PAIR_COHERENCE_EPSILON = 0.01

#: `(observed_at, tier_label)` — what the fill holds per point.
Observation = tuple[datetime, str]


def pair_skew_bound_seconds(tier_label: str | None) -> float:
    """S's tier half: min(ceiling, grain/2), or 0.0 when the tier declares nothing."""
    grain = declared_resolution_seconds(tier_label)
    if grain is None:
        return 0.0
    return min(PAIR_SKEW_MAX_SECONDS, grain / 2.0)


def _local_spacing(leg: Sequence[Observation]) -> list[float]:
    """Each sample's distance to its nearest neighbour in its OWN leg (inf if alone)."""
    out: list[float] = []
    for k, (ts, _tier) in enumerate(leg):
        gaps = []
        if k > 0:
            gaps.append((ts - leg[k - 1][0]).total_seconds())
        if k + 1 < len(leg):
            gaps.append((leg[k + 1][0] - ts).total_seconds())
        out.append(min(gaps) if gaps else float("inf"))
    return out


def pair_observations(
    leg_a: Sequence[Observation], leg_b: Sequence[Observation]
) -> list[tuple[int, int]]:
    """`(index_in_a, index_in_b)` for every pair the rule admits. Each leg must be
    strictly ascending (the bank's own invariant, `parse_points`)."""
    spacing_a, spacing_b = _local_spacing(leg_a), _local_spacing(leg_b)

    def bound(i: int, j: int) -> float:
        return min(
            pair_skew_bound_seconds(leg_a[i][1]),
            spacing_a[i] / 2.0,
            spacing_b[j] / 2.0,
        )

    times_b = [ts for ts, _tier in leg_b]
    reach = timedelta(seconds=PAIR_SKEW_MAX_SECONDS)
    candidates_a: dict[int, list[int]] = {}
    candidates_b: dict[int, list[int]] = {}
    for i, (ts_a, tier_a) in enumerate(leg_a):
        # S never exceeds the ceiling, so only that window can hold a candidate.
        for j in range(bisect_left(times_b, ts_a - reach), bisect_right(times_b, ts_a + reach)):
            if leg_b[j][1] != tier_a:
                continue
            if abs((ts_a - times_b[j]).total_seconds()) <= bound(i, j):
                candidates_a.setdefault(i, []).append(j)
                candidates_b.setdefault(j, []).append(i)
    return sorted(
        (i, js[0])
        for i, js in candidates_a.items()
        if len(js) == 1 and candidates_b.get(js[0]) == [i]
    )
