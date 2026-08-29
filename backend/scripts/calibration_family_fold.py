#!/usr/bin/env python3
"""CAL-P123 — fold a published cell by its market-NAME FAMILY.

Ruling 134 note: this is a read-only instrument. It writes nothing, it does not
re-implement the producer's population, and ``git diff origin/master --
backend/app/`` is empty on the branch that carries it. Ruling 009 freezes
commits to ``precompute_calibration.py``; this file only imports it, which is
what every test in ``backend/tests`` already does.

WHY THIS FILE EXISTS
--------------------
``calibration_cell_exact.py`` can fold a cell by fourteen dimensions and
**not one of them can name a Polymarket market family.** Its ``series``
dimension is ``SPLIT_PART(fm2.external_id, '-', 1)``, which on Kalshi is the
series ticker — ``KXGOLDH``, ``KXFED`` — the exact unit a rule can name. On
Polymarket the same expression returns the numeric Gamma event id, so
``--by series`` on ``polymarket/cricket`` prints **1,148 classes, 1,086 of them
a single row**, and a dimension that resolves to one row per class is not a
dimension. It is the row list with extra steps.

That gap is why rank 10 of the board sat "diagnosed, no rule built" for twenty
days. Every Polymarket cell is a pile of families — on cricket:
``Team Top Batter``, ``Most Sixes``, ``Toss Match Double``, ``Who wins the
toss?``, ``Completed match?``, ``Match goes to Day #?`` — and on Polymarket the
family is not in a ticker. **It is the text after the last `` - `` of the
market name**, because that is where the Gamma feed puts it:

    T20 Series Hong Kong vs Kuwait: Hong Kong, China vs Kuwait - Most Sixes
    ~~~~~~~~~~~~~ series ~~~~~~~~~~~ ~~~~~~~~ fixture ~~~~~~~~   ~ family ~

A rule that a human can read, a cert can check and a reviewer can refuse has to
name something. On Kalshi it names a ticker. This file is what lets it name a
family.

WHAT IT DOES NOT DO
-------------------
It does not re-implement the chain, the buckets, the self-check or the holdout
split. It registers two dimensions into ``calibration_cell_exact.DIMENSIONS``
and delegates to that module's ``main()``, so every number it prints is folded
by the same code that printed the numbers this board is built from, and the
SELF-CHECK line against the served payload is the same one. **A second rail is
a second population.** There is exactly one rail here; this file adds a column
to it.

THE TWO DIMENSIONS
------------------
``--by family``
    The family alone. Answers "which named product is the error in".

``--by familyclean``
    ``family | clean-or-other``, where **clean** means the row's market is a
    ``field_1win`` whose published prices sum to <= 1.15 — a genuine partition
    that realized exactly one winner. This cross exists because of what the
    ``sumband`` fold found on cricket: the structural bundle test (RULE E,
    CAL-P112) removes 946 of 3,246 rows and leaves the cell at roughly where it
    started, because **the clean 64.6% remainder is itself at 5.75 ECE.** A
    cell whose clean control fails the bar cannot be repaired by removing its
    dirty rows, and the only way to see that before designing a rule is to fold
    the clean rows on their own, by family.

    The ``clean`` predicate is written to match ``SHAPE_EXPR``'s
    ``field_1win`` arm and ``SUMBAND_ONLY_EXPR``'s ``a_sum_le_1.15`` arm term
    for term. If either of those moves, the guard suite fails rather than this
    file silently folding a different subpopulation under the same word.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def _load(name: str):
    """Load a sibling script WITHOUT registering it in ``sys.modules``.

    The registration is the obvious convenience and it is a bug. These modules
    mutate shared state at import time — ``calibration_cluster_sigma`` adds
    ``marketid`` to ``cce.DIMENSIONS``, this file adds four more — so a module
    left in ``sys.modules`` makes those mutations visible to every other test
    in the pytest process. CAL-P121's
    ``test_this_module_adds_exactly_one_dimension_and_no_more`` caught exactly
    that when this file first registered itself, and it was right to: a guard
    that another queue's file can break by being imported is not a guard.
    """
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cce = _load("calibration_cell_exact")


#: The market-name family: the text after the LAST '` - `' separator.
#:
#: Three details that are not decoration:
#:
#: 1. ``'^.* - '`` is GREEDY, so on a name carrying two separators it strips to
#:    the last one. That is the intent — Gamma nests ``series: fixture -
#:    family`` and the family is always the tail.
#: 2. Digits collapse to ``#`` AFTER the split, so ``Match goes to Day 4?`` and
#:    ``Match goes to Day 5?`` are one family rather than two. A family split
#:    by its own rung number is the ``series``-on-Polymarket failure again, one
#:    level down.
#: 3. The no-separator arm is named ``z_no_dash_suffix`` and NOT
#:    ``match_line``. Most of those rows are the plain match-winner market, but
#:    not all of them are — the innings over/under lines land there too — and a
#:    class name that asserts more than the predicate tests is how a fold
#:    starts lying quietly.
FAMILY_EXPR = """
CASE WHEN fm2.name IS NULL THEN 'z_no_name'
     WHEN POSITION(' - ' IN fm2.name) = 0 THEN 'z_no_dash_suffix'
     ELSE REGEXP_REPLACE(REGEXP_REPLACE(fm2.name, '^.* - ', ''),
                         '[0-9]+', '#', 'g')
END
"""

#: ``field_1win`` AND published prices summing to <= 1.15 — the clean control.
#:
#: Written to mirror ``SHAPE_EXPR`` (``sh.mn >= 3 AND sh.mw = 1``) and
#: ``SUMBAND_ONLY_EXPR`` (``ms.msum <= 1.15``). ``ms.msum IS NULL`` is 'other',
#: matching ``SUMBAND_ONLY_EXPR``'s ``'na'`` arm: a row whose market has no
#: price sum has not been shown to be a partition, and the whole point of this
#: arm is that it only contains rows that HAVE been.
CLEAN_EXPR = """
CASE WHEN sh.mn >= 3 AND sh.mw = 1 AND ms.msum IS NOT NULL AND ms.msum <= 1.15
          THEN 'clean'
     ELSE 'other' END
"""

FAMILYCROSS_EXPR = FAMILY_EXPR + " || '|' || " + CLEAN_EXPR

#: Do this market's outcomes CARRY DIFFERENT NAMES?
#:
#: This is the dimension the cricket fold turned out to need, and it is not a
#: variant of any dimension already on the rail. Every existing one asks about
#: PRICES (do they sum to a partition, did they move, how many won). This one
#: asks whether the row's outcome says what it is a forecast OF.
#:
#: Polymarket serves a game event as nested sub-markets keyed by
#: ``condition_id`` (gotcha #18). When they are flattened into one
#: ``futures_market`` without being decomposed, the container's name is copied
#: onto every outcome, so a three-legged cricket market reads:
#:
#:     market   Indian Premier League: Rajasthan Royals vs Sunrisers Hyderabad
#:     outcome  Indian Premier League: Rajasthan Royals vs Sunrisers Hyderab   0.565  lose
#:     outcome  Indian Premier League: Rajasthan Royals vs Sunrisers Hyderab   0.495  WIN
#:     outcome  Indian Premier League: Rajasthan Royals vs Sunrisers Hyderab   0.595  lose
#:
#: Three prices summing to 1.655, three identical labels, and **nothing in the
#: row identifies which side each price is for.** That is not a mispriced
#: market. It is a market with no readable claim, and it is on the calibration
#: curve as three forecasts.
#:
#: The predicate is deliberately ``COUNT(DISTINCT name) = 1`` rather than
#: "outcome name is a prefix of market name". The prefix test is the same
#: measurement wearing a fragile disguise: ``futures_outcomes.name`` is
#: truncated relative to ``futures_markets.name``, so the prefix test depends
#: on a truncation LENGTH, and a length is a thing that changes without telling
#: anyone. Undifferentiation is the property that matters and it is directly
#: observable.
#:
#: The ``market_id IN (SELECT market_id FROM market_info)`` conjunct is the same
#: planner hint ``SHAPE_JOIN`` documents at length and is load-bearing for the
#: same reason: without it the chunk prices a full-table aggregate over
#: ``futures_outcomes`` before the join. It changes no row.
OUTCOME_NAME_JOIN = """
LEFT JOIN (
    SELECT fo4.market_id,
           COUNT(*) AS on_n,
           COUNT(DISTINCT fo4.name) AS on_d
    FROM futures_outcomes fo4
    WHERE fo4.market_id IN (SELECT market_id FROM market_info)
    GROUP BY fo4.market_id
) onm ON onm.market_id = d.market_id
"""
OUTCOME_NAME_EXPR = """
CASE WHEN onm.on_n IS NULL THEN 'z_unknown'
     WHEN onm.on_n = 1 THEN 'd_lone_outcome'
     WHEN onm.on_d = 1 THEN 'a_undifferentiated'
     WHEN onm.on_d < onm.on_n THEN 'b_partly_duplicated'
     ELSE 'c_distinct' END
"""

#: ``outcomenames`` crossed with the family, so the answer to "is this the whole
#: story or only the no-suffix corner of it" is one table rather than two.
FAMILYNAMES_EXPR = FAMILY_EXPR + " || '|' || " + OUTCOME_NAME_EXPR

#: ``setdefault``, never ``DIMENSIONS[k] = v`` — CAL-P121's convention, and its
#: suite enforces the mechanical form too. Rebinding would let this file
#: silently change what an existing ``--by`` means for everyone who imports it.
#:
#: ``setdefault`` has its own quiet failure — a name collision becomes a no-op
#: and the fold runs somebody else's dimension under this file's name — so
#: ``TestItComposesTheRailRatherThanRebuildingIt`` asserts all four names are
#: absent from the rail before registration and present after.
ADDED_DIMENSIONS = {
    "family": (FAMILY_EXPR, cce.SERIES_JOIN, ""),
    "familyclean": (
        FAMILYCROSS_EXPR,
        cce.SERIES_JOIN + cce.SUMBAND_JOIN,
        cce.SUMBAND_PRE,
    ),
    "outcomenames": (OUTCOME_NAME_EXPR, OUTCOME_NAME_JOIN, ""),
    "familynames": (
        FAMILYNAMES_EXPR,
        cce.SERIES_JOIN + OUTCOME_NAME_JOIN,
        "",
    ),
}

#: Recorded BEFORE registration so the collision guard has something to check.
_PRE_EXISTING = frozenset(cce.DIMENSIONS)

for _name, _spec in ADDED_DIMENSIONS.items():
    cce.DIMENSIONS.setdefault(_name, _spec)


def main() -> int:
    if not any(a == "--by" or a.startswith("--by=") for a in sys.argv[1:]):
        sys.argv += ["--by", "family"]
    return cce.main()


if __name__ == "__main__":
    raise SystemExit(main())
