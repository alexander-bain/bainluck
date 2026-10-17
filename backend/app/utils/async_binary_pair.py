"""#11157 — which observations of a Yes/No pair answer for one another's scale.

PILLARS: TRUTH / FORMATTING. SHIP: a market chart shows its genuine probability
move without inventing observation times or freshness.

ONE RULE, TWO CALLERS. The fill keeps both halves of a pair through compaction
(`tasks/generic_market_history_fill._compact_entries`) and `/history` admits a
venue point only when its partner is present (`routes/futures`). If the two
asked different questions, compaction would keep halves the reader cannot pair,
or the reader would pair halves compaction never promised to keep — so both
import this function and neither re-derives it.

WHY A RULE BEYOND THE EXACT INSTANT. Polymarket's CLOB `prices-history` stamps
each token at its own second: market 65678073 at fidelity=1 has Yes 461 points
and No 459 with ZERO shared instants but 456 shared minutes (Live, #11157
comment 6229278103). PR #11160 paired exact instants only, so on the venue's
real shape it pairs nothing and the reader refuses every point.

WHAT A PAIR IS, AND IS NOT.
  * Exact shared instants pair first, whatever their tier — #11160's rule,
    unchanged.
  * Otherwise two samples pair only when BOTH declare the venue's fine grain
    (`ASYNC_PAIR_GRAIN_SECONDS`) and they fall in the SAME declared cell, and that
    cell holds exactly one sample of each leg. The cell is the venue's own unit:
    `fidelity=1` asks for one sample per minute, so two samples in one minute are
    the venue's two statements about that minute, and a sample a second across
    the boundary is a statement about a different one.
  * Never across a cell boundary, never one sample for two partners, never a
    coarse or undeclared grain — a sixty-minute or twelve-hour cell is not a
    moment, and an unlabelled point declares nothing to pair within.
  * A pair says NOTHING about simultaneity and moves NO clock. Each half keeps
    its own instant everywhere it is stored or served; the pair is only the
    evidence the reader's scale question is asked of. Its knowledge time (the
    later of the two instants) is a separate fact, never a quote time.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Sequence

from app.utils.futures_chart_series import (
    CLOB_FINE_FIDELITY,
    declared_resolution_seconds,
)

#: The only declared grain at which two samples a few seconds apart may pair:
#: the CLOB fine tier, one sample per minute. Named from the fidelity the fill
#: asks for, so moving that constant moves this one with it.
ASYNC_PAIR_GRAIN_SECONDS = float(CLOB_FINE_FIDELITY * 60)

#: `(observed_at, tier_label)` — what each caller already holds per point.
Observation = tuple[datetime, str]


def _cell(observed_at: datetime) -> int:
    return int(observed_at.timestamp() // ASYNC_PAIR_GRAIN_SECONDS)


def pair_observations(
    leg_a: Sequence[Observation], leg_b: Sequence[Observation]
) -> list[tuple[int, int]]:
    """`(index_in_a, index_in_b)` for every admissible pair, one-to-one, ascending in `a`."""
    pairs: list[tuple[int, int]] = []
    b_at = {ts: j for j, (ts, _tier) in enumerate(leg_b)}
    exact_a: set[int] = set()
    exact_b: set[int] = set()
    for i, (ts, _tier) in enumerate(leg_a):
        j = b_at.get(ts)
        if j is not None:
            pairs.append((i, j))
            exact_a.add(i)
            exact_b.add(j)

    # Every sample counts toward its cell's population, whatever its tier and
    # whether or not it already paired exactly: a second sample in a cell makes
    # the cell ambiguous, and ambiguity pairs nothing.
    cells_a: dict[int, list[int]] = defaultdict(list)
    cells_b: dict[int, list[int]] = defaultdict(list)
    for i, (ts, _tier) in enumerate(leg_a):
        cells_a[_cell(ts)].append(i)
    for j, (ts, _tier) in enumerate(leg_b):
        cells_b[_cell(ts)].append(j)

    for key in cells_a.keys() & cells_b.keys():
        in_a, in_b = cells_a[key], cells_b[key]
        if len(in_a) != 1 or len(in_b) != 1:
            continue
        i, j = in_a[0], in_b[0]
        if i in exact_a or j in exact_b:
            continue
        if (
            declared_resolution_seconds(leg_a[i][1]) != ASYNC_PAIR_GRAIN_SECONDS
            or declared_resolution_seconds(leg_b[j][1]) != ASYNC_PAIR_GRAIN_SECONDS
        ):
            continue
        pairs.append((i, j))

    pairs.sort()
    return pairs
