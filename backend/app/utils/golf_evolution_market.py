"""Which winner market tells a tournament's story — the evolution-chart pick.

A completed major carries several markets that all classify as "winner": a
long-lived odds_api futures market, a real-money Kalshi market, a DataGolf model
line, and a handful of winner-shaped PROPS ("Winner Nationality", "Country of
Winner") that hold no golfers at all. Exactly one of them becomes the
path-to-resolution chart. Choosing it is a POLICY — three filters and a ranking
with two different tie-breaks — and it had been living inline in a route, tangled
with the queries that fetch its inputs.

Extracted per **ruling 005 (extract-on-touch)** alongside the LAT-P020/#1107 fix
that collapsed those queries. The ruling's bar is that the extracted unit be a
*pure module* — no ORM session, no request context — because that is the property
that makes the next fix in this area cheap. Everything here takes plain dicts and
lists, so the policy is testable without a database, a fixture, or an event loop.

The split is deliberate: the CALLER fetches the three facts (outcome counts,
snapshot counts, the graded winner's last price) in whatever query shape is
fastest, and this module decides what they mean. That is what let the caller go
from three queries per candidate market to three queries total without any risk
to the decision itself.

Tie-breaks are load-bearing and asymmetric, so they are stated rather than left
to be re-derived from the comparison operators:

  * snapshot-richness keeps the FIRST market at the maximum (strict `>`)
  * the settled-resolve preference keeps the LAST market at the maximum (`>=`)

Both reproduce the behaviour of the inline loop this replaced.
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping, Optional, Sequence

# #225 Item 3: minimum resolved-winner snapshot probability for a settled winner
# market to be preferred as the evolution (path-to-resolution) chart source. A
# real-money market converges to ~1.0 for the champion; a stale futures market
# that stopped before the finish never crosses this, so it stays a fallback.
SETTLED_RESOLVE_MIN = 0.5

# Below this, a "winner" market is not a golfer field: "League of Winner" has 3
# outcomes, Yes/No binaries have 2.
MIN_CONTENDER_OUTCOMES = 5

# Chart-specific exclusion for the contenders Win chart (#955): drop winner-PROP
# markets (nationality / country-of-winner / tour-of-winner / winning margin)
# that classify as type "winner" but hold no golfers. Unlike _NON_WINNER_MARKET_RE,
# this must NOT match a real field like "PGA Tour: U.S. Open Winner", so it uses
# the "X of (the) winner" prop phrasing and explicit prop nouns rather than a
# broad "tour .* winner".
NON_CONTENDER_WINNER_RE = re.compile(
    r"\bnationality\b"
    r"|\bcontinent\b"
    r"|\b(?:country|tour|region|state)\s+of\s+(?:the\s+)?winner\b"
    r"|\bwinning\s+(?:country|nationality|tour|score|margin)\b"
    r"|\bwinner'?s?\s+(?:tour|nationality|country)\b"
    r"|\bmargin\s+of\s+victory\b",
    re.I,
)


def contender_candidates(
    market_ids: Sequence[int],
    id_to_name: Mapping[int, str],
) -> list[int]:
    """Winner markets that could plausibly hold a golfer field, in input order.

    Name-only, so it costs nothing and runs BEFORE any per-market fact is
    fetched — a nationality prop should never reach the snapshot count.
    """
    return [
        mid
        for mid in market_ids
        if not NON_CONTENDER_WINNER_RE.search(id_to_name.get(mid, "") or "")
    ]


def eligible_candidates(
    candidate_ids: Iterable[int],
    outcome_counts: Mapping[int, int],
    min_outcomes: int = MIN_CONTENDER_OUTCOMES,
) -> list[int]:
    """Candidates that carry a real field, in input order.

    A market absent from `outcome_counts` has no outcomes and is dropped, which
    matches the inline version's `scalar() or 0`.
    """
    return [
        mid for mid in candidate_ids if outcome_counts.get(mid, 0) >= min_outcomes
    ]


def select_by_settled_resolution(
    eligible_ids: Sequence[int],
    winner_last: Mapping[int, object],
    settled_resolve_min: float = SETTLED_RESOLVE_MIN,
) -> Optional[int]:
    """The market whose graded winner ENDED high and STAYED there, or None.

    `winner_last` is the graded winner's LATEST price. A real-money Kalshi market
    closes at ~0.999; the odds_api futures market fizzles at ~18% because it
    stopped updating before the finish; the DataGolf model RESETS to ~0.5%
    post-event, so its momentary in-play 1.0 would win a max()-based rank while
    leaving an ugly end-drop on the chart. Ranking on the FINAL value is what
    picks the market that actually stays at the top.

    Returns None for a live or upcoming tournament: nothing is graded yet, so
    `winner_last` is empty and the caller falls back to snapshot richness.

    Ties keep the LAST market at the maximum (`>=`).
    """
    resolved_best_id: Optional[int] = None
    resolved_best_val = settled_resolve_min

    for mid in eligible_ids:
        winner_resolve = winner_last.get(mid)
        if winner_resolve is not None and float(winner_resolve) >= resolved_best_val:
            resolved_best_val = float(winner_resolve)
            resolved_best_id = mid

    return resolved_best_id


def select_by_snapshot_richness(
    eligible_ids: Sequence[int],
    snap_counts: Mapping[int, int],
) -> Optional[int]:
    """The market with the most price history — the fullest line to draw.

    The right answer for a live or upcoming tournament, where nothing has
    resolved yet and there is no better signal than coverage.

    Ties keep the FIRST market at the maximum (strict `>`).

    THIS IS THE EXPENSIVE ONE. Its input is a count over every snapshot of every
    outcome of the market, and a long-lived golf winner market holds the entire
    field: 193,981 snapshot rows for one market, measured in production
    2026-08-09, ~4.7s cold for that market ALONE. Callers must treat building
    `snap_counts` as the fallback it is — see the ordering note on
    `select_evolution_market`.
    """
    best_id: Optional[int] = None
    best_count = -1

    for mid in eligible_ids:
        total = snap_counts.get(mid, 0)
        if total > best_count:
            best_count = total
            best_id = mid

    return best_id


def select_evolution_market(
    eligible_ids: Sequence[int],
    snap_counts: Mapping[int, int],
    winner_last: Mapping[int, object],
    settled_resolve_min: float = SETTLED_RESOLVE_MIN,
) -> Optional[int]:
    """The market whose journey the chart should draw, or None.

    The settled pick wins outright over the richness pick; richness is only
    consulted when nothing is graded.

    **The order is a performance contract, not just a preference.** Resolution is
    decided by one price per market (the graded winner's last snapshot) and cost
    613 ms for ELEVEN markets in production; richness has to count every snapshot
    of every outcome and cost ~4,700 ms for ONE market. Since resolution WINS
    whenever it produces an answer, a caller that builds `snap_counts` eagerly
    pays the expensive input to compute a value it then discards — which is
    exactly what `get_golf_tournament` was doing on every completed major
    (LAT-P020, #1107). Callers should therefore try
    `select_by_settled_resolution` first and only fetch `snap_counts` if it
    returns None.

    This combined form is kept because it is the honest statement of the policy
    and the thing equivalence tests can pin against the pre-LAT-P020 loop.
    """
    return select_by_settled_resolution(
        eligible_ids, winner_last, settled_resolve_min
    ) or select_by_snapshot_richness(eligible_ids, snap_counts)
