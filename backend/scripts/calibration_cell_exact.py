#!/usr/bin/env python3
"""CAL-P114 — fold ONE published cell through the PRODUCER'S OWN CTE chain.

This is the third and last instrument in the CAL-P112 family, and it exists
because the first two could not measure the cell this queue was pointed at.

===========================  ==========================================  =========
instrument                   how it derives the population               reproduces
===========================  ==========================================  =========
``calibration_cell_shape_fold``   re-implements the predicate down to    NO on
                                  ``ranked_outcomes``; no dedup, no      several
                                  per-outcome exclusions. Scales.        cells
``calibration_cell_replica``      re-implements the chain through        yes, to
                                  ``deduped`` in Python. Caps at         ~2% on n
                                  ~6,000 candidate rows.
**this file**                     ``_calibration_population_ctes()``     BY
                                  IMPORTED FROM THE PRODUCER, verbatim.  CONSTRUCTION
===========================  ==========================================  =========

The first two are re-implementations, so every published-curve rule they bench
inherits an unmeasured drift between the bench and the curve. On
``kalshi/economics`` that drift is not small and not subtle: the shape census
reads **69,653 / 4.65 / +4.27** (55,425 / 3.41 / +2.19 with the truth-eligibility
gate) against the payload's **28,581 / 5.29 / −0.47** — 1.9x the rows and the
WRONG SIGN on the gap. A rule designed on that rail is designed on a different
population, and CAL-P112 said exactly this about ``polymarket/tech`` before
declaring it UNMEASURED.

WHY THIS ONE CANNOT DRIFT
---------------------------
It does not re-implement anything. It calls
``precompute_calibration._calibration_population_ctes()`` — the same function
the producer calls to build the curve — and appends only a ``GROUP BY`` over
``deduped``, which is the final published population. Its self-check is
therefore not "do two implementations agree" but "does the producer's own
predicate, run now, reproduce the payload it produced".

**It does not import the frozen file to CHANGE it.** Ruling 009 freezes commits
to ``precompute_calibration.py``; reading it is what every test in
``backend/tests`` already does. ``git diff origin/master`` for that path is
empty on this branch.

THE THREE THINGS THAT MADE IT WORK, ALL OF THEM NON-OBVIOUS
-------------------------------------------------------------
1. ``market_info_extra`` is a documented parameter of the chain (the horizon
   surface at ``precompute_calibration.py:5583`` uses it the same way). It
   injects into ``market_info``'s WHERE, and every downstream CTE joins
   ``market_info`` — so scoping it to one cell scopes the whole chain.
2. **``POST /api/admin/db-query`` refuses the chain verbatim** with
   ``"Multi-statement queries not allowed"``. The producer's SQL is full of
   prose comments and some contain a semicolon; the guard counts those. The
   comments are stripped quote-safely before sending (``_strip_sql_comments``).
3. The whole-cell chain exceeds the row path's hard 10 s budget, so it is
   chunked on ``fm.id`` through the SAME ``market_info_extra`` hook, and a
   chunk that still times out is SPLIT rather than retried (gotcha #53 — a
   silently short answer reads as "the class is small").

THE ONE APPROXIMATION, MEASURED RATHER THAN ASSERTED
------------------------------------------------------
Chunking on ``fm.id`` can split a ``group_id`` / ``event_id`` cluster across a
chunk boundary, and ``virtual_market``'s ">= 3 markets in the same source"
grouping test is then evaluated on a partial cluster — so a market that is
grouped in production can read ungrouped in a chunk and take the ``rn = 1``
branch instead of the multi branch. This is the same class of approximation
``calibration_cell_replica`` documents, and here it is CHECKED rather than
described: ``--edge-check`` re-runs the whole sweep at a different chunk width
and prints both totals. If the two disagree, the chunking is doing something
and the run says so instead of averaging it away.

Usage::

    python3 backend/scripts/calibration_cell_exact.py \\
        --source kalshi --category economics --by age --edge-check \\
        --out artifacts/cal-p114/exact-kalshi-economics.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks.precompute_calibration import (  # noqa: E402
    _calibration_population_ctes,
)
from app.utils.ladder_coherence import (  # noqa: E402
    ambiguous_families,
    incoherent_families,
    ladder_family_key,
    parse_ou_line,
    read_ladders,
)
# Imported under its module name, NOT flat. ``ladder_monotonicity`` exports its
# own ``ambiguous_families`` with a different key type, and a flat import would
# silently rebind the O/U one above — two predicates, one name, and whichever
# import line came last decides which rule the ``ladder`` dimension enforces.
from app.utils import ladder_monotonicity  # noqa: E402

ladder_report = ladder_monotonicity.ladder_report
from app.utils.pair_opening_coherence import PAIR_SUM_TOLERANCE  # noqa: E402

#: The db-query row path's silent truncation point.
ROW_CAP = 1000

#: Default id width per chunk. 1M ids measured ~1.7 s against production.
DEFAULT_WIDTH = 1_000_000


class QueryTimeout(RuntimeError):
    """The server cancelled the statement — the one failure this script can
    FIX, by scanning a narrower id range, and the one that must never be
    retried forever at the same size."""


def _strip_sql_comments(sql: str) -> str:
    """Drop ``--`` line comments, respecting single-quoted literals.

    The db-query guard rejects the producer's SQL outright because some of its
    prose comments contain a semicolon and the guard reads that as a second
    statement. Stripping comments is semantics-preserving; stripping them with
    a naive ``split('--')`` is not, because outcome names and regexes in this
    chain legitimately contain ``--`` inside quotes.
    """
    out = []
    for line in sql.split("\n"):
        i, in_quote, cut = 0, False, None
        while i < len(line):
            ch = line[i]
            if ch == "'":
                in_quote = not in_quote
            elif not in_quote and ch == "-" and line[i + 1:i + 2] == "-":
                cut = i
                break
            i += 1
        out.append(line if cut is None else line[:cut].rstrip())
    return "\n".join(ln for ln in out if ln.strip())


def db_query(sql: str, limit: int = ROW_CAP, retries: int = 3) -> dict:
    base = os.environ["BAINLUCK_API"].rstrip("/")
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(
            f"{base}/api/admin/db-query", data=body,
            headers={"Authorization": "Bearer " + os.environ["ADMIN_TOKEN"],
                     "Content-Type": "application/json"})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=180).read().decode())
        except urllib.error.HTTPError as e:
            last = e.read().decode()[:400]
            if "statement_timeout" in last:
                raise QueryTimeout(last) from e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"db-query failed after {retries} attempts: {last}")


# ---------------------------------------------------------------------------
# Attribution dimensions. Each is a SQL expression over ``deduped d`` plus the
# joins it needs. ``none`` is the plain cell fold and is what the self-check
# compares against the payload.
# ---------------------------------------------------------------------------
#: How stale the last snapshot before the market's own close is. Part A2 of
#: ``backfill_winners`` sets ``calibration_probability`` to exactly this
#: snapshot for every non-event market with a ``commence_time``, which is 100%
#: of ``kalshi/economics``, so this dimension asks: how old is the price the
#: curve calls a closing line?
AGE_JOIN = """
LEFT JOIN futures_markets fm2 ON fm2.id = d.market_id
LEFT JOIN LATERAL (
    SELECT fos.captured_at
    FROM futures_odds_snapshots fos
    WHERE fos.outcome_id = d.outcome_id
      AND fos.captured_at < fm2.commence_time
      AND fos.probability > 0 AND fos.probability < 1
    ORDER BY fos.captured_at DESC LIMIT 1
) ls ON true
"""
AGE_EXPR = """
CASE WHEN fm2.commence_time IS NULL THEN 'z_no_commence'
     WHEN ls.captured_at IS NULL THEN 'z_no_snapshot'
     WHEN fm2.commence_time - ls.captured_at < INTERVAL '15 minutes' THEN 'a_lt15m'
     WHEN fm2.commence_time - ls.captured_at < INTERVAL '1 hour'     THEN 'b_15m_1h'
     WHEN fm2.commence_time - ls.captured_at < INTERVAL '4 hours'    THEN 'c_1h_4h'
     WHEN fm2.commence_time - ls.captured_at < INTERVAL '1 day'      THEN 'd_4h_1d'
     WHEN fm2.commence_time - ls.captured_at < INTERVAL '7 days'     THEN 'e_1d_7d'
     ELSE 'f_gt7d' END
"""

#: The Kalshi SERIES ticker — everything before the first '-' of the event
#: ticker. This is the market FAMILY (KXWTIH, KXNASDAQ100U, KXFED...), which is
#: the unit a rule can actually name.
SERIES_JOIN = "LEFT JOIN futures_markets fm2 ON fm2.id = d.market_id"
SERIES_EXPR = "SPLIT_PART(fm2.external_id, '-', 1)"

#: CAL-P127 — the ROUND-SCOPE x QUESTION-FAMILY cross, for `kalshi/golf` (rank 9).
#:
#: ``series`` folds this cell into 65 arms, which is past ``rule_search``'s
#: ``MAX_CLASSES`` — so the searcher refuses it, and the only thing left is to
#: read the table and pick the bad-looking rows by hand. That is an exhaustive
#: search for an overfit performed by a human instead of a loop, and lesson 7
#: exists because a hand-picked subset cannot support "no rule exists".
#:
#: So the 65 arms are collapsed on the two properties the Kalshi ticker actually
#: encodes, and on nothing else:
#:
#:   scope    does the ticker name a ROUND (``R<n>``)? ``KXPGAR1TOP10`` does,
#:            ``KXPGATOP10`` does not. This is the difference between "top 10
#:            after 18 holes" and "top 10 at the end of the tournament".
#:   family   what is being asked — a TOP-N cut (``...TOP<n>``), the round or
#:            tournament LEAD (``...LEAD``), or anything else.
#:
#: WHY THE ROUND TEST IS ``R[0-9]`` AND NOT ``R``. Three of this cell's series
#: carry an R that is not a round: ``KXPGAROUNDSCORE``, ``KXPGAROUNDLOW`` and
#: ``KXOWGRRANK``. Requiring a DIGIT after the R separates them, and the guard
#: suite pins all three by name — an enumeration written by reading one source's
#: titles is complete for that source and silently partial for every other
#: (gotcha #129), so the test is structural and the counterexamples are frozen.
#:
#: WHY THE FAMILY TEST IS ANCHORED. ``TOP[0-9]+$`` and ``LEAD$`` are anchored to
#: the END of the series token so that a future ``KXPGATOP10MARGIN`` — a margin
#: prop that merely mentions a cut — does not silently join the TOP-N arm and
#: dilute whatever verdict this partition supports.
#:
#: This is a PARTITION, not a rule. Every row lands in exactly one of six arms
#: and no arm is privileged; which arms (if any) a rule should drop is decided
#: by ``calibration_rule_search`` over the whole 2^6 lattice, scored on a
#: holdout, not by this expression.
GOLFROUND_JOIN = SERIES_JOIN
GOLFROUND_EXPR = """
CASE WHEN SPLIT_PART(fm2.external_id, '-', 1) ~ 'R[0-9]'
     THEN 'round' ELSE 'tourney' END
|| '|' ||
CASE WHEN SPLIT_PART(fm2.external_id, '-', 1) ~ 'TOP[0-9]+$' THEN 'topn'
     WHEN SPLIT_PART(fm2.external_id, '-', 1) ~ 'LEAD$'      THEN 'lead'
     ELSE 'other' END
"""

#: Terminal market shape, on the same basis ``market_result_shape`` uses.
#:
#: The ``market_id IN (SELECT market_id FROM market_info)`` conjunct is NOT
#: redundant with the ``ON`` clause and must not be "tidied" away. Without it
#: the planner has no predicate on ``futures_outcomes`` and prices a full
#: 3.3M-row seq scan + aggregate BEFORE the join — measured here as a chunk
#: that never returns and recursively splits to the depth limit. It is the same
#: defect CAL-P039 found in ``vm_stats`` (19.1x on the query), arriving through
#: a different door: a planner hint spelled as a predicate. ``market_info`` is
#: already scoped to this chunk's cell, so the conjunct is implied by the join
#: and changes no row.
SHAPE_JOIN = """
LEFT JOIN (
    SELECT fo3.market_id,
           COUNT(*) AS mn,
           COUNT(*) FILTER (WHERE fo3.is_winner) AS mw
    FROM futures_outcomes fo3
    WHERE fo3.market_id IN (SELECT market_id FROM market_info)
    GROUP BY fo3.market_id
) sh ON sh.market_id = d.market_id
"""
SHAPE_EXPR = """
CASE WHEN sh.mw = 0 THEN 'void_0win'
     WHEN sh.mn >= 3 AND sh.mw >= 2 THEN 'bundle_multiwin'
     WHEN sh.mn >= 3 AND sh.mw = 1 THEN 'field_1win'
     WHEN sh.mn = 2 AND sh.mw = 1 THEN 'binary_1win'
     WHEN sh.mn = 2 THEN 'binary_other'
     ELSE 'single' END
"""

#: SHAPE x PUBLISHED-PRICE-SUM, the cross CAL-P112's RULE E turns on.
#:
#: RULE E replaces the bundle test's realized ``win_count >= 2`` with a
#: STRUCTURAL one — a market whose published prices sum to more than 1.15 is
#: not a partition, whatever it happened to realize. The two tests disagree on
#: exactly the rows that decide whether a cell is a calibration failure or a
#: population defect: a ladder that realized ONE winner passes the realization
#: test and fails the structural one. Folding the cross is the only way to see
#: whether a cell's ``field_1win`` remainder is a clean control (sums to ~1) or
#: the same ladders on a quiet day (sums to N x p).
#:
#: The sum is over ``deduped`` — the PUBLISHED rows — because that is the sum a
#: reader of the curve is implicitly told is a probability distribution.
SUMBAND_PRE = """,
msums AS (
    SELECT market_id, SUM(adj_opening_probability) AS msum
    FROM deduped GROUP BY market_id
)"""
SUMBAND_JOIN = SHAPE_JOIN + "\nLEFT JOIN msums ms ON ms.market_id = d.market_id"

#: The price-sum band on its own, so the ``pairsum`` cross below composes it
#: rather than restating it. Two dimensions that band the same quantity must
#: band it identically or their tables cannot be read against each other.
SUMBAND_ONLY_EXPR = """
CASE WHEN ms.msum IS NULL THEN 'na'
     WHEN ms.msum <= 1.15 THEN 'a_sum_le_1.15'
     WHEN ms.msum <= 2    THEN 'b_sum_1.15_2'
     WHEN ms.msum <= 5    THEN 'c_sum_2_5'
     WHEN ms.msum <= 15   THEN 'd_sum_5_15'
     ELSE 'e_sum_gt_15' END
"""
SUMBAND_EXPR = """
CASE WHEN sh.mw = 0 THEN 'void'
     WHEN sh.mn >= 3 AND sh.mw >= 2 THEN 'bundle'
     WHEN sh.mn >= 3 AND sh.mw = 1 THEN 'field1'
     WHEN sh.mn = 2 THEN 'binary'
     ELSE 'single' END
|| '|' ||
""" + SUMBAND_ONLY_EXPR

#: CAL-P130 — the SLOT-NORMALIZED price sum, for `polymarket/golf` (rank 12).
#:
#: WHY ``sumband`` CANNOT ANSWER THIS CELL. ``sumband`` bands the raw published
#: sum against constants (1.15, 2, 5, 15) that encode one assumption: a market
#: is a PARTITION, so a coherent sum is ~1. CAL-P127 recorded that this premise
#: is backwards in golf — "will player X finish top 10" is an INDEPENDENT
#: BINARY, and a hundred of them priced against ten slots legitimately sum to
#: ten (gotcha #23). Every subset that clears the bar over ``sumband``,
#: ``pairsum``, ``policy`` and ``shape`` on this cell clears it by deleting the
#: ``sum > 15`` band — 60-82% of the cell, and structurally the wrong rows.
#:
#: THE QUANTITY THAT IS ACTUALLY COHERENT OR NOT. A golf field market DECLARES
#: its own slot count in its own name: "... Winner" offers one slot, "... Top 5"
#: five, "... Top 20" twenty. So the coherent sum is not 1, it is N, and the
#: scale-free statement of the defect is the RATIO ``msum / N``. CAL-P129 found
#: the same defect on ``kalshi/entertainment`` in the special case N = 1 (a
#: one-winner field whose prices sum past 1.15); this is that finding's general
#: form, and the N = 1 arm below is exactly CAL-P129's ``field1|*``.
#:
#: 🔴 THE SLOT COUNT IS READ FROM THE NAME, NEVER FROM THE REALIZATION. The
#: rail's ``shape``/``sumband`` dimensions classify on ``mw`` — how many
#: outcomes actually WON — which is legitimate for diagnosis and is LEAKAGE for
#: a shipping exclusion rule: it would decide which resolved markets count by
#: what they resolved to. Every input here (``fm2.name``, published prices) is
#: known at publish time, so a rule keyed on this dimension can be evaluated
#: before a winner exists.
#:
#: THE BANDS ARE SYMMETRIC IN LOG SPACE AROUND 1 AND WERE FIXED BEFORE THE FOLD
#: RAN — 1/4, 3/4, 4/3, 4. Lesson 13: a correction expected to run one way runs
#: both ways, so the banding must be able to SEE both ways.
#:
#: ⚠️ AND ON THIS CELL IT DOES NOT, WHICH IS ITSELF THE MEASUREMENT. Raw markets
#: DO under-sum badly — "Puerto Rico Open Top 10" publishes a sum of 0.50 against
#: ten declared slots, a ratio of 0.05 — but in the PUBLISHED population
#: ``a_ratio_lt_0.25`` holds ZERO rows and ``b_ratio_0.25_0.75`` holds 60 (0.9%).
#: The low tail is almost entirely filtered out before the curve sees it. So on
#: ``polymarket/golf`` the defect really is one-directional, and that is a fact
#: about the published cell rather than an assumption baked into the bands —
#: which is the only reason it is safe to say (lesson 6: a population a rule is
#: designed on is not the population it will run on, and the two are checked
#: here rather than conflated).
#:
#: ``z_cut`` is separated rather than banded: "To Make the Cut" declares no
#: number, the cut size is a property of the weekend, and guessing it would be
#: this dimension inventing the quantity it claims to measure. A row a rule
#: cannot see must not be scored as if it could.
SLOTS_EXPR = """
CASE WHEN fm2.name ~* 'top[[:space:]]+[0-9]+[[:space:]]*$'
          THEN (SUBSTRING(fm2.name FROM 'op[[:space:]]+([0-9]+)[[:space:]]*$'))::numeric
     WHEN fm2.name ~* 'winner[[:space:]]*$' THEN 1
     ELSE NULL END
"""
SLOTRATIO_JOIN = SERIES_JOIN + "\nLEFT JOIN msums ms ON ms.market_id = d.market_id"
SLOTRATIO_EXPR = f"""
CASE WHEN ({SLOTS_EXPR}) IS NULL AND fm2.name ~* 'make[[:space:]]+the[[:space:]]+cut'
          THEN 'z_cut_no_declared_n'
     WHEN ({SLOTS_EXPR}) IS NULL THEN 'z_no_declared_n'
     WHEN ms.msum IS NULL THEN 'z_no_sum'
     WHEN ms.msum / ({SLOTS_EXPR}) < 0.25  THEN 'a_ratio_lt_0.25'
     WHEN ms.msum / ({SLOTS_EXPR}) < 0.75  THEN 'b_ratio_0.25_0.75'
     WHEN ms.msum / ({SLOTS_EXPR}) <= 1.3333 THEN 'c_ratio_coherent'
     WHEN ms.msum / ({SLOTS_EXPR}) <= 4    THEN 'd_ratio_1.33_4'
     ELSE 'e_ratio_gt_4' END
"""

#: CAL-P131 — the DECLARED-PARTITION price sum, for `polymarket/economics`
#: (rank 15). The third instrument in the ``sumband`` succession, and the second
#: one on the rail that a shipping exclusion rule is allowed to read.
#:
#: WHY ``sumband`` CANNOT ANSWER THIS CELL EITHER, AND FOR A NEW REASON.
#: ``sumband`` bands the published sum against 1 and splits the cell with
#: ``sh.mw`` — how many outcomes actually WON. Both halves of that are wrong
#: here:
#:
#:   * ``polymarket/economics`` is dominated by NESTED THRESHOLD LADDERS —
#:     *"Will Apple (AAPL) close above $255 / $260 / $265 ... on August 5?"*.
#:     The rungs are not mutually exclusive, so their prices are NOT a
#:     distribution: a coherent thirteen-rung ladder sums to the EXPECTED
#:     NUMBER OF RUNGS THAT HIT, anywhere in ``[0, 13]``. ``sumband`` reads that
#:     as ``d_sum_5_15`` and condemns 53% of the cell for being arithmetically
#:     correct. This is gotcha #23 arriving through a different door than golf's
#:     (CAL-P130): golf's independent binaries share ONE slot count declared in
#:     the market name; a ladder's rungs are NESTED and declare no slot count at
#:     all.
#:   * ``sh.mw`` is the realized win count, so every rule ``sumband`` admits is
#:     leakage — it selects resolved markets by their resolution. CAL-P130 made
#:     this the standing test and it disqualifies ``field1``/``bundle`` outright.
#:
#: THE QUANTITY THAT IS ACTUALLY COHERENT OR NOT, AND WHERE IT IS DECLARED.
#: Golf declares its coherent sum in the MARKET name ("Top 10" → 10). Economics
#: declares its coherent sum in the OUTCOME names, through their GRAMMAR: a
#: market whose legs read ``<$6,400`` / ``$6,400-$6,500`` / ... / ``>$7,300`` has
#: said, in its own text, that it is a partition of the real line — mutually
#: exclusive and exhaustive — so its prices must sum to 1 and a sum of 1.96 is a
#: defect of the market, not a forecast that turned out wrong. A market whose
#: legs read ``$255``, ``$260``, ``$265`` has said no such thing.
#:
#: So the test is: DOES THE MARKET DECLARE A PARTITION, and if so, does it sum
#: like one. Both readings come from the leg names and the published prices.
#:
#: 🔴 EXHAUSTIVENESS IS REQUIRED, NOT ASSUMED. A run of interior bands with no
#: open-ended tail (``<x`` low and ``>y`` high) is mutually exclusive but NOT
#: exhaustive, and its coherent sum is some unknown number below 1. Those
#: markets are separated into ``z_not_exhaustive`` rather than banded, for the
#: same reason CAL-P130 separated ``z_cut``: a dimension must not invent the
#: quantity it claims to measure.
#:
#: 🔴 EVERY INPUT IS KNOWN AT PUBLISH TIME. Leg names and published prices, and
#: nothing else — no ``mw``, no ``is_winner``, no resolution column.
#: ``test_the_expression_never_reads_a_realized_winner`` pins it, and it is the
#: guard to keep if the others are ever trimmed.
#:
#: THE BANDS ARE THE SAME FOUR ``slotratio`` USES — 1/4, 3/4, 4/3, 4, symmetric
#: in log space around 1 — deliberately, so the two tables can be read against
#: each other, and fixed before the fold ran (lesson 13).
#:
#: ``|full`` vs ``|part`` IS A CROSS, NOT A GATE. A partition whose legs did not
#: all reach the curve publishes a sum that is mechanically short of 1 through
#: no fault of the market's pricing, and folding those rows into the ratio bands
#: unlabelled would let a liquidity artifact read as an incoherence. Making it a
#: SUFFIX rather than an early ``CASE`` arm keeps both readings visible: the
#: partial partitions are still banded, and any rule over the partition can be
#: scored with them in or out.
BANDLEG_INTERIOR = (
    r"'^[$]?[0-9][0-9,.]*[[:space:]]*[-–][[:space:]]*[$]?[0-9]'"
)
BANDLEG_TAIL = r"'^[<>]'"
BANDRATIO_PRE = SUMBAND_PRE + """,
bandlegs AS (
    SELECT fo9.market_id,
           COUNT(*) AS bl_legs,
           COUNT(*) FILTER (WHERE btrim(fo9.name) ~ """ + BANDLEG_TAIL + """
                               OR btrim(fo9.name) ~ """ + BANDLEG_INTERIOR + """
                           ) AS bl_bands,
           COUNT(*) FILTER (WHERE btrim(fo9.name) ~ '^<') AS bl_low,
           COUNT(*) FILTER (WHERE btrim(fo9.name) ~ '^>') AS bl_high
    FROM futures_outcomes fo9
    WHERE fo9.market_id IN (SELECT market_id FROM market_info)
    GROUP BY fo9.market_id
),
publegs AS (
    SELECT market_id, COUNT(*) AS pub_legs FROM deduped GROUP BY market_id
)"""
BANDRATIO_JOIN = """
LEFT JOIN msums ms ON ms.market_id = d.market_id
LEFT JOIN bandlegs bl ON bl.market_id = d.market_id
LEFT JOIN publegs pl ON pl.market_id = d.market_id
"""
BANDRATIO_EXPR = """
CASE WHEN bl.bl_legs IS NULL OR bl.bl_legs < 3 THEN 'z_not_a_partition'
     WHEN bl.bl_bands < bl.bl_legs THEN 'z_not_a_partition'
     WHEN bl.bl_low = 0 OR bl.bl_high = 0 THEN 'z_not_exhaustive'
     WHEN ms.msum IS NULL THEN 'z_no_sum'
     ELSE (CASE WHEN ms.msum < 0.25    THEN 'a_sum_lt_0.25'
                WHEN ms.msum < 0.75    THEN 'b_sum_0.25_0.75'
                WHEN ms.msum <= 1.3333 THEN 'c_sum_coherent'
                WHEN ms.msum <= 4      THEN 'd_sum_1.33_4'
                ELSE 'e_sum_gt_4' END)
          || (CASE WHEN pl.pub_legs IS NULL OR pl.pub_legs < bl.bl_legs
                        THEN '|part' ELSE '|full' END)
     END
"""

#: CAL-P132 — the TWO-GRAIN TWIN dimension, for `polymarket/tech` (rank 19).
#:
#: WHAT IT ASKS. Does this row's ``group_id`` publish the SAME question at TWO
#: grains at once — a ``field`` market listing every candidate answer, AND a
#: shelf of ``container_member`` binaries asking about those answers one at a
#: time — and if so, which grain is this row?
#:
#: WHY THE CELL NEEDS IT. ``polymarket/tech`` is not a tech cell in the sense the
#: board's other [C] cells are. 29.2% of its 2,973 raw markets are PODCAST AND
#: KEYNOTE WORD BINGO — *"What will Jensen Huang say during the NVIDIA GTC
#: Keynote?"*, *"What will be said on the next All-In Podcast?"* — and Polymarket
#: publishes each of those events twice. Group ``polymarket:555948`` carries a
#: 22-leg field, *"What will Tim Cook say at Apple WWDC 2026 on June 8th?"*, and
#: fourteen separate binaries, *"Will Tim Cook say 'Siri' during the Apple WWDC
#: 2026 event on June 8th?"* — the same phrase list, asked twice, both ingested,
#: both scored by the curve.
#:
#: WHY NO DIMENSION ALREADY ON THE RAIL CAN SEE IT. ``market_type`` separates
#: ``field`` from ``container_member`` but is blind to whether they are the same
#: question: a lone field and a twinned field land in one arm. ``series`` keys on
#: the group and therefore splits the cell into one arm per event — 289 of them
#: here, past ``rule_search``'s ``MAX_CLASSES``, so it cannot be searched at all.
#: This dimension is ``series`` collapsed onto the one property of a group that
#: is a claim about the PRODUCT rather than about one event.
#:
#: THE SUFFIX IS A CROSS, NOT A GATE — CAL-P131's ``|full`` / ``|part`` rule
#: applied to a second dimension. The whole question is whether ONE of the two
#: grains is the broken one, and a dimension that labelled the group without
#: labelling the row's own grain could not answer it: the field rows and the
#: member rows of a twinned group would pool, and a defect in one grain would be
#: diluted by the other. ``a_twinned|f`` and ``a_twinned|m`` are the two arms the
#: whole build exists to compare, and ``b_field_only|f`` is their control — the
#: same market shape, same category, same price scale, published ONCE.
#:
#: THE GROUP CENSUS IS DELIBERATELY NOT CHUNK-SCOPED. ``grpcomp`` filters to the
#: groups this chunk touches and then counts EVERY market in each of those
#: groups, straight off ``futures_markets``. Counting only the chunk's own rows
#: would make twin-ness a property of where the chunk boundary fell — gotcha #53
#: in its usual costume, a market reading ``b_field_only`` because its siblings
#: were 1,000,000 ids away and the fold reporting that as a clean table. It is
#: also why the census does NOT filter on ``status`` or category: a twin is a
#: fact about what was published, not about what happened to resolve.
#:
#: LEAKAGE. ``market_type`` is assigned by ``app.utils.market_shape`` from
#: outcome structure, leg names and group membership, and ``group_id`` is
#: ingestion metadata. Neither reads a resolution, so unlike ``shape`` and
#: ``sumband`` — which branch on ``sh.mw``, the realized win count — a rule keyed
#: on this dimension is evaluable before any outcome exists.
TWIN_PRE = """,
grpcomp AS (
    SELECT fm12.group_id,
           COUNT(*) FILTER (WHERE fm12.market_type = 'field') AS g_fields,
           COUNT(*) FILTER (WHERE fm12.market_type = 'container_member')
               AS g_members
    FROM futures_markets fm12
    WHERE fm12.group_id IN (
        SELECT group_id FROM market_info WHERE group_id IS NOT NULL
    )
    GROUP BY fm12.group_id
)"""
TWIN_JOIN = """
LEFT JOIN futures_markets fm11 ON fm11.id = d.market_id
LEFT JOIN grpcomp gc ON gc.group_id = fm11.group_id
"""
TWIN_EXPR = """
CASE WHEN fm11.group_id IS NULL THEN 'z_ungrouped'
     WHEN gc.g_fields >= 1 AND gc.g_members >= 1 THEN 'a_twinned'
     WHEN gc.g_fields >= 1 THEN 'b_field_only'
     WHEN gc.g_members >= 1 THEN 'c_members_only'
     ELSE 'd_no_grain' END
|| '|' ||
CASE WHEN d.market_type = 'field' THEN 'f'
     WHEN d.market_type = 'container_member' THEN 'm'
     ELSE 'o' END
"""

#: CAL-P117 — the Over/Under PAIR dimension, for `polymarket/baseball`.
#:
#: Rank 1 of the board is not a bundle cell: it is two-leg Over/Under quantity
#: markets, and the two mechanisms named for it on ``program/calibration-99``
#: (CAL-P094's 0.5000 placeholder, CAL-P100's published-pair incoherence) are
#: both properties of the PAIR, not of a row. Neither has ever been measured
#: against the published cell — CAL-P100 shipped its arm with the words *"NO
#: ECE CLAIM ... this ships with its delta unmeasured"* — so this dimension
#: exists to supply exactly that number on the producer's own chain.
#:
#: The aggregates are over ALL outcomes of the market, which is the basis
#: ``market_result_shape`` uses; the branch's own predicates are reproduced
#: verbatim rather than paraphrased:
#:
#:   * shape       — ``hs_n_outcomes = 2 AND hs_named_over = 1 AND
#:                   hs_named_under = 1`` (``two_leg_over_under_shape_clauses``)
#:   * half-spike  — ``hs_half_legs = 2``, where a half leg is
#:                   ``ROUND(opening_probability, 4) = 0.5000``
#:   * CAL-P100    — both sums over a COMPLETE pair, coherent at opening and
#:                   incoherent as published, against ``PAIR_SUM_TOLERANCE``
#:
#: The CASE is ORDERED, so the classes it prints are marginal-with-precedence
#: rather than the two rules' raw marginals: a pair that opens 0.5000/0.5000
#: opens coherent by construction, so it can also satisfy CAL-P100's arm if its
#: published sum drifts. Half-spike is tested first and the overlap is therefore
#: reported inside ``a_half_spike``. That is a reporting choice and it is stated
#: because the two arms are OR'd in the real predicate, where the overlap is
#: removed once either way.
#: IMPORTED, never restated. ``pair_opening_coherence``'s own comment gives the
#: reason and it applies here verbatim: a tolerance that drifted between the
#: writer gate and the instrument that benches a read-side rule would let one of
#: them disagree with the measurement that justified the other. A test asserts
#: this name *is* the imported one, not a copy that happens to be equal
#: (CAL-P115's rule — an equal copy drifts on the next edit).
PAIR_TOLERANCE = PAIR_SUM_TOLERANCE
PAIR_JOIN = """
LEFT JOIN (
    SELECT fo5.market_id,
           COUNT(*) AS pr_n,
           COUNT(*) FILTER (WHERE lower(btrim(fo5.name)) = 'over') AS pr_over,
           COUNT(*) FILTER (WHERE lower(btrim(fo5.name)) = 'under') AS pr_under,
           COUNT(*) FILTER (WHERE ROUND(fo5.opening_probability, 4) = 0.5000)
               AS pr_half,
           SUM(fo5.opening_probability) AS pr_open_sum,
           COUNT(*) FILTER (WHERE fo5.opening_probability IS NOT NULL)
               AS pr_open_legs,
           SUM(COALESCE(fo5.calibration_probability, fo5.opening_probability))
               AS pr_pub_sum,
           COUNT(*) FILTER (WHERE COALESCE(fo5.calibration_probability,
                                           fo5.opening_probability) IS NOT NULL)
               AS pr_pub_legs
    FROM futures_outcomes fo5
    WHERE fo5.market_id IN (SELECT market_id FROM market_info)
    GROUP BY fo5.market_id
) pr ON pr.market_id = d.market_id
"""
PAIR_EXPR = f"""
CASE WHEN pr.pr_n = 2 AND pr.pr_over = 1 AND pr.pr_under = 1 THEN
       CASE WHEN pr.pr_half = 2 THEN 'a_half_spike'
            WHEN pr.pr_open_legs = 2 AND pr.pr_pub_legs = 2
                 AND ABS(pr.pr_open_sum - 1) <= {PAIR_TOLERANCE}
                 AND ABS(pr.pr_pub_sum - 1) > {PAIR_TOLERANCE}
                 THEN 'b_pub_incoherent'
            WHEN pr.pr_open_legs = 2
                 AND ABS(pr.pr_open_sum - 1) > {PAIR_TOLERANCE}
                 THEN 'c_open_incoherent'
            WHEN pr.pr_open_legs = 2 AND pr.pr_pub_legs = 2
                 THEN 'd_pair_coherent'
            ELSE 'e_pair_partial' END
     ELSE 'z_not_ou_pair' END
"""

#: The same classes crossed with ``market_type``. CAL-P100 scoped its rule to
#: ``polymarket/baseball/quantity``; whether that scope is the right one is a
#: measurement, not a preference, and this is the fold that answers it.
PAIRTYPE_EXPR = PAIR_EXPR.rstrip() + "\n|| '|' || COALESCE(d.market_type, 'null')\n"

#: pair class x published price sum band, in ONE fold.
#:
#: Needed because the two candidate rule families for this cell live in
#: different dimensions and a policy that combines them cannot be arithmetic'd
#: out of two separate sweeps: the pair rules act on two-leg markets (which sit
#: in the ``a_sum_le_1.15`` band by construction) and the sum rule acts on the
#: many-legged tail. They LOOK disjoint, and "looks disjoint" is how a
#: double-counted exclusion gets published (CERT-403B). One fold, one
#: partition, no inference.
PAIRSUM_JOIN = PAIR_JOIN + "\nLEFT JOIN msums ms ON ms.market_id = d.market_id"
PAIRSUM_EXPR = PAIR_EXPR.rstrip() + "\n|| '|' ||\n" + SUMBAND_ONLY_EXPR

#: THE POLICY FOLD — every candidate exclusion for `polymarket/baseball` as one
#: ORDERED partition, crossed with the price-sum band so the survivors can be
#: read as well as counted.
#:
#: A policy that is assembled by subtracting three separate sweeps from each
#: other is a policy whose overlaps were assumed. This dimension assigns each
#: published row to at most ONE arm, in a fixed precedence, so "what does
#: shipping all three do" is a pooling of classes rather than an inference:
#:
#:   r1  CAL-P094's 0.5000 placeholder pair (both legs open at exactly 0.5000)
#:   r2  CAL-P100's published-pair incoherence (coherent open, incoherent
#:       published) — r1 first, so a pair that is both is charged to r1
#:   r3  CAL-P117's player-prop bundle: a Polymarket market whose NAME ends in
#:       "Player Props", which packs 36-38 independent player binaries into one
#:       market at a published price sum of 15-19
#:   keep  everything the three arms do not touch
#:
#: The name test is the market's own title, not a shape heuristic, because the
#: shape it produces (many legs, few winners, sum >> 1) is shared with the
#: honest 28-leg game bundles that publish at 1.0000 per leg and grade every
#: leg a winner — those contribute exactly zero error and excluding them would
#: be deleting rows to move a denominator.
POLICY_JOIN = PAIR_JOIN + """
LEFT JOIN futures_markets fm4 ON fm4.id = d.market_id
LEFT JOIN msums ms ON ms.market_id = d.market_id
"""
POLICY_EXPR = f"""
CASE WHEN pr.pr_n = 2 AND pr.pr_over = 1 AND pr.pr_under = 1
          AND pr.pr_half = 2 THEN 'r1_half_spike'
     WHEN pr.pr_n = 2 AND pr.pr_over = 1 AND pr.pr_under = 1
          AND pr.pr_open_legs = 2 AND pr.pr_pub_legs = 2
          AND ABS(pr.pr_open_sum - 1) <= {PAIR_TOLERANCE}
          AND ABS(pr.pr_pub_sum - 1) > {PAIR_TOLERANCE} THEN 'r2_pub_incoherent'
     WHEN fm4.name ILIKE '%player props%' THEN 'r3_player_props'
     ELSE 'keep' END
|| '|' ||
""" + SUMBAND_ONLY_EXPR

#: CAL-P117 — how far the PUBLISHED price was moved from the OPENING quote, and
#: whether it was moved TO a coin flip.
#:
#: This is CAL-P094's 0.5000 spike asked as a row-level question instead of a
#: two-leg-pair one. That predicate tests ``ROUND(opening_probability, 4) =
#: 0.5000`` on a market with exactly two legs named Over and Under, so it is
#: blind to the same phantom arriving through the other column on a market with
#: 37 legs — which is what a Polymarket "Player Props" container is.
#:
#: ``c_moved_elsewhere`` is the CONTROL and the reason this dimension is a
#: ladder rather than a flag: a published price that moved a long way from its
#: open is ordinary line movement, and a rule that cannot tell that apart from
#: a placeholder overwrite is a rule that deletes real forecasts. The claim the
#: ladder has to support is not "moved" but "moved TO 0.50".
DRIFT_JOIN = "LEFT JOIN futures_outcomes fo6 ON fo6.id = d.outcome_id"
DRIFT_EXPR = """
CASE WHEN fo6.calibration_probability IS NULL THEN 'z_no_cp_fallback'
     WHEN fo6.opening_probability IS NULL THEN 'y_no_opening'
     WHEN fo6.calibration_probability BETWEEN 0.45 AND 0.55
          AND ABS(fo6.calibration_probability - fo6.opening_probability) > 0.25
          THEN 'a_forced_to_half'
     WHEN fo6.calibration_probability BETWEEN 0.45 AND 0.55
          AND ABS(fo6.calibration_probability - fo6.opening_probability) > 0.10
          THEN 'b_pulled_to_half'
     WHEN ABS(fo6.calibration_probability - fo6.opening_probability) > 0.25
          THEN 'c_moved_elsewhere'
     ELSE 'd_normal' END
"""

#: THE SUCCESSION FOLD — can a COLUMN-level predicate retire the name match?
#:
#: ``policy``'s third arm is ``name ILIKE '%player props%'``, and a rule keyed
#: on a provider's market title is a rule that breaks the day the provider
#: renames the container. ``cpdrift`` says a column-level predicate for the
#: same rows exists (``a_forced_to_half``: 1,915 rows, ECE 44.36, gap +44.36).
#: Whether it can REPLACE the name arm cannot be answered by putting the two
#: sweeps side by side — they overlap, and by how much is the whole question.
#:
#: So: one ordered partition over five arms, crossed with a single flag that
#: says whether the row is in the name arm's population. Every combination of
#: {R1, R2, M1, M2, R3} is then a pooling of these ten classes.
#:
#:   r1 / r2  as in ``policy``
#:   m1       published price forced INTO [0.45, 0.55] from an open >0.25 away
#:   m2       the same, pulled >0.10 — the softer rung, so the ladder is visible
#:   keep     everything else
#:   |p       the row is in a "Player Props" market whose published prices sum
#:            to more than 1.15 (RULE E's own constant, not a new threshold)
#:
#: m1 is tested BEFORE the flag is read, so "drop m1" removes a props row that
#: m1 catches and R3's residual is the props rows m1 does NOT catch. That is the
#: succession question stated as an arithmetic one.
POLICY2_JOIN = POLICY_JOIN + "\nLEFT JOIN futures_outcomes fo7 ON fo7.id = d.outcome_id"
POLICY2_EXPR = f"""
CASE WHEN pr.pr_n = 2 AND pr.pr_over = 1 AND pr.pr_under = 1
          AND pr.pr_half = 2 THEN 'r1_half_spike'
     WHEN pr.pr_n = 2 AND pr.pr_over = 1 AND pr.pr_under = 1
          AND pr.pr_open_legs = 2 AND pr.pr_pub_legs = 2
          AND ABS(pr.pr_open_sum - 1) <= {PAIR_TOLERANCE}
          AND ABS(pr.pr_pub_sum - 1) > {PAIR_TOLERANCE} THEN 'r2_pub_incoherent'
     WHEN fo7.calibration_probability BETWEEN 0.45 AND 0.55
          AND ABS(fo7.calibration_probability - fo7.opening_probability) > 0.25
          THEN 'm1_forced_to_half'
     WHEN fo7.calibration_probability BETWEEN 0.45 AND 0.55
          AND ABS(fo7.calibration_probability - fo7.opening_probability) > 0.10
          THEN 'm2_pulled_to_half'
     ELSE 'keep' END
|| '|' ||
CASE WHEN fm4.name ILIKE '%player props%' AND ms.msum > 1.15 THEN 'p'
     ELSE 'n' END
"""

#: CAL-P118 — the LADDER dimension, for `polymarket/soccer` (rank 4).
#:
#: The board carries this cell as "✅ O/U ladder coherence (CAL-P106/107)". That
#: claim has never been evaluated against the published cell: CAL-P106 measured
#: 5,708 legs of ``soccer/quantity`` — 5.3% of the published cell's 106,803 —
#: and §7 of the scorecard turned that into a −0.28 pp prediction by ARITHMETIC.
#: CAL-P117 found exactly this pattern on rank 1 and the arithmetic was wrong by
#: a factor. So this dimension exists to replace the prediction with a fold.
#:
#: THE PREDICATE IS IMPORTED, NOT RESTATED. ``incoherent_families`` and its
#: helpers come from ``app.utils.ladder_coherence`` — the module a shipping
#: caller would use — and the fold never re-derives a family key or a violation.
#: The module's own docstring says the SQL rendering it also carries is UNPROVEN
#: against the Python and that measurement must be driven from the Python side
#: until a whole-population differential exists; that instruction is obeyed here
#: rather than argued with, which is why the verdict is computed in Python and
#: only the ANSWER (a set of market ids) is pushed back into SQL.
#:
#: WHY A PRE-PASS AND NOT A WINDOW. A ladder family is a set of markets sharing
#: a name modulo the rung, and market ids inside one family are NOT guaranteed
#: contiguous. A window computed inside a chunked fold would evaluate some
#: families on a partial rung set and silently under-condemn — the same class of
#: error ``--edge-check`` exists to catch, but arriving through the dimension
#: instead of through ``virtual_market``. The pre-pass sweeps the whole cell
#: once, at its own chunk width, so the verdict for a family never depends on
#: where a boundary fell. Each fold chunk then receives only the ids inside its
#: own range, which is why the arrays stay small.
LADDER_ROWS_SQL = """
SELECT fm.id AS market_id,
       MAX(fm.name) AS name,
       MAX(CASE WHEN lower(btrim(fo.name)) = 'over'
                THEN COALESCE(fo.calibration_probability, fo.opening_probability)
           END) AS over_price
FROM futures_markets fm
JOIN futures_outcomes fo ON fo.market_id = fm.id
WHERE fm.source = '{source}'
  AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}'
  AND fm.name ~ 'O/U[[:space:]]+[0-9]'
  AND fm.id >= {lo} AND fm.id < {hi}
GROUP BY fm.id
"""

#: A chunk whose id array would make the statement longer than this is SPLIT
#: rather than sent. The row path has no documented body limit, so the failure
#: it would produce is an unclassified 4xx — and an unclassified 4xx in a
#: chunked sweep reads as "this range is empty" (gotcha #53).
MAX_SQL_CHARS = 60_000

#: Filled by :func:`ladder_context` before the sweep starts. Three disjoint id
#: sets plus the census that produced them.
_LADDER: dict | None = None


def _pull_ladder_rows(source: str, category: str, lo: int, hi: int,
                      depth: int = 0) -> list:
    """Every O/U-bearing market in an id range, or a split."""
    sql = LADDER_ROWS_SQL.format(source=source, category=category, lo=lo, hi=hi)
    try:
        r = db_query(sql, limit=ROW_CAP)
    except QueryTimeout:
        r = None
    if r is not None and r["row_count"] < ROW_CAP:
        return r["rows"]
    if depth > 18 or hi - lo <= 1:
        raise RuntimeError(f"ladder pre-pass chunk {lo}-{hi} irreducible at depth {depth}")
    mid = lo + (hi - lo) // 2
    return (_pull_ladder_rows(source, category, lo, mid, depth + 1)
            + _pull_ladder_rows(source, category, mid, hi, depth + 1))


def ladder_partition(recs: list) -> dict:
    """Split ``{market_id, name, over_price}`` records into the rule's three classes.

    Pure, so the arm a market lands in is testable without production. The
    verdict itself is not computed here — ``incoherent_families`` and
    ``ambiguous_families`` are the shipped functions and this only reads which
    bucket each market's family fell into.

    A market with no Over price or no rung token takes no part at all: the
    predicate cannot place it in a ladder, and a row a rule cannot see must not
    be reported as a row the rule kept (gotcha #53).
    """
    usable = [r for r in recs
              if ladder_family_key(r["name"]) is not None
              and parse_ou_line(r["name"]) is not None
              and r["over_price"] is not None]

    ladders = read_ladders(usable)
    ambiguous = ambiguous_families(ladders)
    condemned = incoherent_families(usable)

    drop, amb_ids, coherent = set(), set(), set()
    for r in usable:
        key = ladder_family_key(r["name"])
        if key in condemned:
            drop.add(r["market_id"])
        elif key in ambiguous:
            amb_ids.add(r["market_id"])
        else:
            coherent.add(r["market_id"])

    singletons = sum(1 for v in ladders.values() if len(v["rungs"]) < 2)
    return {
        "drop": drop, "ambiguous": amb_ids, "coherent": coherent,
        "census": {
            "ou_markets_scanned": len(recs),
            "ou_markets_usable": len(usable),
            "no_over_price": len(recs) - len(usable),
            "families": len(ladders),
            "families_singleton": singletons,
            "families_ambiguous": len(ambiguous),
            "families_condemned": len(condemned),
            "markets_drop": len(drop),
            "markets_ambiguous": len(amb_ids),
            "markets_coherent": len(coherent),
        },
    }


def ladder_context(source: str, category: str, width: int) -> dict:
    """Sweep the cell once and hand the shipped predicate its whole population.

    Returns the three id sets the dimension partitions on, and a census that is
    printed rather than summarised — ``ambiguous`` in particular is the rule's
    own fail-toward-keeping guard and a run where it swallowed the cell would
    otherwise look like a rule that found nothing.
    """
    rng = db_query(
        f"SELECT MIN(id) AS lo, MAX(id) AS hi FROM futures_markets "
        f"WHERE source = '{source}'", limit=5)
    lo, hi = rng["rows"][0]

    rows: list = []
    e = lo
    n_chunks = 0
    while e <= hi:
        nxt = min(e + width, hi + 1)
        n_chunks += 1
        print(f"    ladder pre-pass [{n_chunks}] ids {e}-{nxt}",
              file=sys.stderr, flush=True)
        rows.extend(_pull_ladder_rows(source, category, e, nxt))
        e = nxt

    # The predicate's own input shape: name + Over price, one row per rung.
    return ladder_partition(
        [{"market_id": r[0], "name": r[1], "over_price": r[2]} for r in rows])


def _id_array(ids: set, lo: int, hi: int) -> str:
    inside = sorted(i for i in ids if lo <= i < hi)
    if not inside:
        return "ARRAY[]::bigint[]"
    return "ARRAY[" + ",".join(str(i) for i in inside) + "]::bigint[]"


def ladder_dim(lo: int, hi: int) -> tuple[str, str, str]:
    """The dimension expression for ONE chunk, from the pre-pass verdict.

    Four arms, and the last two are the controls the rule has to survive:
    ``c_ladder_coherent`` is the population the rule KEEPS and its error is what
    the cell looks like after the rule ships; ``z_not_a_ladder`` is the part of
    the cell the mechanism cannot touch at all, and doctrine 18 says a
    row-dropping fix is graded on exactly that.
    """
    if _LADDER is None:  # pragma: no cover - main() fills it first
        raise RuntimeError("ladder_context() must run before the sweep")
    return (f"""
CASE WHEN d.market_id = ANY({_id_array(_LADDER['drop'], lo, hi)})
          THEN 'a_drop_incoherent'
     WHEN d.market_id = ANY({_id_array(_LADDER['ambiguous'], lo, hi)})
          THEN 'b_ambiguous_kept'
     WHEN d.market_id = ANY({_id_array(_LADDER['coherent'], lo, hi)})
          THEN 'c_ladder_coherent'
     ELSE 'z_not_a_ladder' END
""", "", "")


#: The MONOTONICITY pre-pass. Same pre-pass argument as the ladder one above —
#: a nested family's market ids are not contiguous, so the verdict must not
#: depend on where a chunk boundary fell — with one deliberate difference.
#:
#: THERE IS NO NAME FILTER IN THIS SQL, and that is the point. ``LADDER_ROWS_SQL``
#: carries a Postgres name prefilter (the rung pattern, quoted once in this file
#: and guarded by ``TestThePrefilterCannotHideARung``) which is a second
#: rendering of a predicate whose authority is the Python; ``ladder_coherence``
#: calls that pair UNPROVEN and books a whole-population differential as a cert
#: obligation.
#: Rather than open a second such obligation, this pre-pass pulls EVERY market in
#: the cell that has a YES leg and lets the Python grammar be the only definition
#: of what a rung is. It costs more rows and buys back the only thing that could
#: make the fold disagree with the shipped predicate.
MONO_ROWS_SQL = """
SELECT fm.id AS market_id,
       MAX(fm.name) AS name,
       MAX(CASE WHEN lower(btrim(fo.name)) = 'yes'
                THEN COALESCE(fo.calibration_probability, fo.opening_probability)
           END) AS yes_price
FROM futures_markets fm
JOIN futures_outcomes fo ON fo.market_id = fm.id
WHERE fm.source = '{source}'
  AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}'
  AND fm.id >= {lo} AND fm.id < {hi}
GROUP BY fm.id
"""

#: Filled by :func:`mono_context` before the sweep starts.
_MONO: dict | None = None


def _pull_mono_rows(source: str, category: str, lo: int, hi: int,
                    depth: int = 0) -> list:
    """Every market with a YES leg in an id range, or a split."""
    sql = MONO_ROWS_SQL.format(source=source, category=category, lo=lo, hi=hi)
    try:
        r = db_query(sql, limit=ROW_CAP)
    except QueryTimeout:
        r = None
    if r is not None and r["row_count"] < ROW_CAP:
        return r["rows"]
    if depth > 24 or hi - lo <= 1:
        raise RuntimeError(f"mono pre-pass chunk {lo}-{hi} irreducible at depth {depth}")
    mid = lo + (hi - lo) // 2
    return (_pull_mono_rows(source, category, lo, mid, depth + 1)
            + _pull_mono_rows(source, category, mid, hi, depth + 1))


def mono_context(source: str, category: str, width: int) -> dict:
    """Sweep the cell once and hand the shipped predicate its whole population.

    The verdict is computed by ``app.utils.ladder_monotonicity.ladder_report`` —
    the module a shipping caller would use — and this function never re-derives
    a family key, a direction or a violation.
    """
    rng = db_query(
        f"SELECT MIN(id) AS lo, MAX(id) AS hi FROM futures_markets "
        f"WHERE source = '{source}'", limit=5)
    lo, hi = rng["rows"][0]

    rows: list = []
    e = lo
    n_chunks = 0
    while e <= hi:
        nxt = min(e + width, hi + 1)
        n_chunks += 1
        print(f"    mono pre-pass [{n_chunks}] ids {e}-{nxt}",
              file=sys.stderr, flush=True)
        rows.extend(_pull_mono_rows(source, category, e, nxt))
        e = nxt

    return ladder_report(
        [{"market_id": r[0], "name": r[1], "yes_price": r[2]} for r in rows])


def mono_dim(lo: int, hi: int) -> tuple[str, str, str]:
    """The dimension expression for ONE chunk, from the pre-pass verdict.

    Four arms, and as with ``ladder`` the last two are the controls the rule has
    to survive: ``c_mono_coherent`` is the population a rule would KEEP and its
    error is what the cell looks like afterwards, and ``z_not_in_a_ladder`` is
    the part of the cell the mechanism cannot touch at all, which doctrine 18
    says is how a row-dropping fix is graded.
    """
    if _MONO is None:  # pragma: no cover - main() fills it first
        raise RuntimeError("mono_context() must run before the sweep")
    return (f"""
CASE WHEN d.market_id = ANY({_id_array(_MONO['drop'], lo, hi)})
          THEN 'a_drop_reversed'
     WHEN d.market_id = ANY({_id_array(_MONO['ambiguous'], lo, hi)})
          THEN 'b_ambiguous_kept'
     WHEN d.market_id = ANY({_id_array(_MONO['coherent'], lo, hi)})
          THEN 'c_mono_coherent'
     ELSE 'z_not_in_a_ladder' END
""", "", "")


#: Dimensions whose expression depends on the chunk, and therefore cannot live
#: in the static table below.
PER_CHUNK_DIMENSIONS = {"ladder": ladder_dim, "mono": mono_dim}

#: The pre-pass each per-chunk dimension needs before the sweep can start.
#: Keyed the same way, so adding a dimension to one table without the other is a
#: KeyError at start-up rather than an empty partition at the end (gotcha #53).
PER_CHUNK_CONTEXT = {"ladder": ladder_context, "mono": mono_context}

#: name -> (key expression, extra JOINs, extra CTEs appended to the chain)
DIMENSIONS = {
    "none": ("'all'", "", ""),
    "age": (AGE_EXPR, AGE_JOIN, ""),
    "series": (SERIES_EXPR, SERIES_JOIN, ""),
    "golfround": (GOLFROUND_EXPR, GOLFROUND_JOIN, ""),
    "shape": (SHAPE_EXPR, SHAPE_JOIN, ""),
    "sumband": (SUMBAND_EXPR, SUMBAND_JOIN, SUMBAND_PRE),
    "slotratio": (SLOTRATIO_EXPR, SLOTRATIO_JOIN, SUMBAND_PRE),
    "bandratio": (BANDRATIO_EXPR, BANDRATIO_JOIN, BANDRATIO_PRE),
    "twin": (TWIN_EXPR, TWIN_JOIN, TWIN_PRE),
    "pair": (PAIR_EXPR, PAIR_JOIN, ""),
    "pairtype": (PAIRTYPE_EXPR, PAIR_JOIN, ""),
    "pairsum": (PAIRSUM_EXPR, PAIRSUM_JOIN, SUMBAND_PRE),
    "policy": (POLICY_EXPR, POLICY_JOIN, SUMBAND_PRE),
    "cpdrift": (DRIFT_EXPR, DRIFT_JOIN, ""),
    "policy2": (POLICY2_EXPR, POLICY2_JOIN, SUMBAND_PRE),
    "price_moved": ("CASE WHEN d.price_moved THEN 'moved' ELSE 'unmoved' END", "", ""),
    "market_type": ("COALESCE(d.market_type, 'null')", "", ""),
}


def cell_sql(source: str, category: str, lo: int, hi: int, dim: str) -> str:
    if dim in PER_CHUNK_DIMENSIONS:
        expr, join, pre = PER_CHUNK_DIMENSIONS[dim](lo, hi)
    else:
        expr, join, pre = DIMENSIONS[dim]
    pop = _calibration_population_ctes(
        market_info_extra=(
            f"AND fm.source = '{source}' "
            f"AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}' "
            f"AND fm.id >= {lo} AND fm.id < {hi}"
        )
    )
    return _strip_sql_comments(
        "WITH " + pop + pre + f"""
SELECT {expr} AS k,
       LEAST(FLOOR(d.adj_opening_probability * 10)::int, 9) AS b,
       COUNT(*) AS n,
       SUM(CASE WHEN d.is_winner THEN 1 ELSE 0 END) AS w,
       ROUND(SUM(d.adj_opening_probability)::numeric, 6) AS sp
FROM deduped d
{join}
GROUP BY 1, 2"""
    )


def collect(source: str, category: str, lo: int, hi: int, dim: str,
            depth: int = 0) -> list:
    """Fold one id range, splitting on BOTH failure modes of the row path.

    Truncation and statement-timeout are the same bug wearing two faces: the
    range is too big. Only one of them is loud. A per-chunk dimension adds a
    third face — a statement too long to send — and it is the quietest of all,
    so it is checked BEFORE the request rather than diagnosed from its reply.
    """
    sql = cell_sql(source, category, lo, hi, dim)
    if len(sql) > MAX_SQL_CHARS:
        return _split(source, category, lo, hi, dim, depth, "over the SQL length cap")
    try:
        r = db_query(sql, limit=ROW_CAP)
    except QueryTimeout:
        return _split(source, category, lo, hi, dim, depth, "timing out")
    if r["row_count"] >= ROW_CAP:
        return _split(source, category, lo, hi, dim, depth, "truncated")
    return r["rows"]


def _split(source: str, category: str, lo: int, hi: int, dim: str,
           depth: int, why: str) -> list:
    if depth > 18 or hi - lo <= 1:
        raise RuntimeError(f"chunk {lo}-{hi} still {why} at depth {depth}")
    mid = lo + (hi - lo) // 2
    return (collect(source, category, lo, mid, dim, depth + 1)
            + collect(source, category, mid, hi, dim, depth + 1))


def sweep(source: str, category: str, dim: str, width: int,
          holdout_at: int | None = None) -> tuple[dict, dict]:
    rng = db_query(
        f"SELECT MIN(id) AS lo, MAX(id) AS hi FROM futures_markets "
        f"WHERE source = '{source}'", limit=5)
    lo, hi = rng["rows"][0]

    edges, e = [], lo
    while e <= hi:
        edges.append(e)
        e = min(e + width, hi + 1)
    edges.append(hi + 1)
    if holdout_at and lo < holdout_at <= hi:
        edges = sorted(set(edges) | {holdout_at})

    def _new():
        return defaultdict(lambda: defaultdict(lambda: {"n": 0, "w": 0, "sp": 0.0}))

    by_key = _new()
    halves = {"OLD": _new(), "NEW": _new()}
    t_sweep = time.time()
    for i in range(len(edges) - 1):
        rlo, rhi = edges[i], edges[i + 1]
        half = None if not holdout_at else ("OLD" if rlo < holdout_at else "NEW")
        # Progress on stderr, not stdout: a sweep with no output for ten
        # minutes is indistinguishable from a hung one, and the whole point of
        # the split-on-timeout recursion is that SOME chunks cost far more than
        # the median. Say which one.
        print(f"    [{i + 1}/{len(edges) - 1}] ids {rlo}-{rhi} "
              f"({time.time() - t_sweep:.0f}s elapsed)", file=sys.stderr, flush=True)
        for k, b, n, w, sp in collect(source, category, rlo, rhi, dim):
            targets = [by_key] + ([halves[half]] if half else [])
            for t in targets:
                v = t[k][b]
                v["n"] += n
                v["w"] += w
                v["sp"] += float(sp)
    return by_key, halves


def fold(bins: dict) -> tuple[int, float | None, float | None]:
    n = sum(v["n"] for v in bins.values())
    if not n:
        return 0, None, None
    ece = sum(abs(v["w"] / v["n"] - v["sp"] / v["n"]) * v["n"]
              for v in bins.values()) / n * 100
    gap = sum(v["sp"] - v["w"] for v in bins.values()) / n * 100
    return n, round(ece, 2), round(gap, 2)


def pool(by_key: dict) -> dict:
    out: dict[int, dict] = defaultdict(lambda: {"n": 0, "w": 0, "sp": 0.0})
    for bb in by_key.values():
        for b, v in bb.items():
            out[b]["n"] += v["n"]
            out[b]["w"] += v["w"]
            out[b]["sp"] += v["sp"]
    return out


#: How many times :func:`fetch_payload` re-asks after a 429, and how long it
#: waits between tries. The public rate limit is 60 requests/minute and a whole-
#: cell sweep spends most of that budget on ``db-query`` chunks, so the payload
#: fetch — which happens AFTER the sweep — routinely arrives as the 61st request
#: in the window. Sixty-five seconds is one full window plus slack.
#:
#: WHY A RETRY AND NOT A CACHE. The self-check's whole warrant is that the
#: payload it compares against is the one the site is serving now; a cached
#: payload would let a stale curve silently certify a fold of a newer one.
#: WHY BOUNDED AND LOUD. A throttle that is swallowed reads as "the cell is
#: empty" (gotcha #53); a throttle that is retried forever reads as a hang. On
#: exhaustion this re-raises the 429 unchanged, so the failure is still a
#: harness story told in the harness's own words (gotcha #124).
PAYLOAD_RETRIES = 3
PAYLOAD_BACKOFF_S = 65


def fetch_payload() -> dict:
    """``GET /api/calibration``, re-asking a bounded number of times on 429."""
    base = os.environ["BAINLUCK_API"].rstrip("/")
    for attempt in range(PAYLOAD_RETRIES):
        try:
            with urllib.request.urlopen(f"{base}/api/calibration", timeout=120) as fh:
                return json.loads(fh.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == PAYLOAD_RETRIES - 1:
                raise
            print(f"    payload fetch throttled (429), retry "
                  f"{attempt + 1}/{PAYLOAD_RETRIES - 1} in {PAYLOAD_BACKOFF_S}s",
                  flush=True)
            time.sleep(PAYLOAD_BACKOFF_S)
    raise AssertionError("unreachable")  # pragma: no cover


def payload_cell(source: str, category: str) -> tuple[int, float | None, float | None, dict]:
    """The published cell, folded from the served payload's own buckets.

    This is the number every line this script prints must be read against —
    a rail that is not shown to reproduce is a parallel rail wearing the
    published curve's name.
    """
    d = fetch_payload()
    bins: dict[int, dict] = defaultdict(lambda: {"n": 0, "w": 0, "sp": 0.0})
    for r in d["buckets"]:
        if r["source"] == source and r["category"] == category:
            v = bins[r["bucket_idx"]]
            v["n"] += r["n"]
            v["w"] += r["winners"]
            v["sp"] += r["sum_prob"]
    n, ece, gap = fold(bins)
    return n, ece, gap, {"generated_at": d.get("generated_at"),
                         "population_version": d.get("population_version")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--by", default="none",
                    choices=sorted(set(DIMENSIONS) | set(PER_CHUNK_DIMENSIONS)))
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH,
                    help="id width per chunk (a chunk that times out is split)")
    ap.add_argument("--edge-check", action="store_true",
                    help="re-run the plain fold at half the chunk width and "
                         "print both totals, so chunk-boundary effects on "
                         "virtual_market grouping are measured, not assumed")
    ap.add_argument("--holdout-at", type=int, default=None,
                    help="a market_id; fold OLD (< id) and NEW (>= id) "
                         "separately. market_id is monotone with creation, so "
                         "NEW is genuinely later data. The id becomes a chunk "
                         "EDGE, so neither half is contaminated.")
    ap.add_argument("--out")
    args = ap.parse_args()

    global _LADDER, _MONO
    ladder_census = None
    if args.by in PER_CHUNK_DIMENSIONS:
        context = PER_CHUNK_CONTEXT[args.by](
            args.source, args.category, args.width)
        if args.by == "ladder":
            _LADDER = context
        else:
            _MONO = context
        ladder_census = context["census"]
        print(f"  {args.by.upper()} PRE-PASS — the shipped predicate, "
              f"whole cell, one sweep")
        for k, v in ladder_census.items():
            print(f"    {k:<38} {v}")
        print()

    t0 = time.time()
    by_key, halves = sweep(args.source, args.category, args.by,
                           args.width, args.holdout_at)
    took = time.time() - t0

    pooled = pool(by_key)
    n, ece, gap = fold(pooled)
    pn, pece, pgap, meta = payload_cell(args.source, args.category)

    print(f"{args.source}/{args.category}   (--by {args.by}, "
          f"width {args.width}, {took:.0f}s)")
    print(f"  curve generated {meta['generated_at']}  "
          f"population {meta['population_version']}")
    print()
    print("  SELF-CHECK — the producer's own chain against the payload it produced")
    print(f"    {'exact replica':<16} n={n:>7}  ECE={ece:>6}  gap={gap:>+7}")
    print(f"    {'payload':<16} n={pn:>7}  ECE={pece:>6}  gap={pgap:>+7}")
    if pn:
        dn = (n - pn) / pn * 100
        print(f"    {'delta':<16} n={n - pn:>+7} ({dn:+.2f}%)  "
              f"ECE={ece - pece:+.2f}  gap={gap - pgap:+.2f}")
    print()

    if args.by != "none":
        print(f"  {'class':<18} {'n':>7} {'share':>7} {'ECE':>7} {'gap':>8}")
        for k in sorted(by_key, key=lambda k: -sum(v["n"] for v in by_key[k].values())):
            kn, kece, kgap = fold(by_key[k])
            print(f"  {str(k):<18} {kn:>7} {kn / n * 100:>6.1f}% "
                  f"{kece:>7} {kgap:>+8}")
        print()

    if args.holdout_at:
        print(f"  HOLDOUT on market_id {args.holdout_at}")
        for half in ("OLD", "NEW"):
            print(f"    {half}")
            for k in sorted(halves[half],
                            key=lambda k: -sum(v["n"] for v in halves[half][k].values())):
                kn, kece, kgap = fold(halves[half][k])
                print(f"      {str(k):<18} {kn:>7} {kece:>7} {kgap:>+8}")
        print()

    edge = None
    if args.edge_check:
        w2 = max(1, args.width // 2)
        bk2, _ = sweep(args.source, args.category, "none", w2)
        n2, ece2, gap2 = fold(pool(bk2))
        edge = {"width": w2, "n": n2, "ece": ece2, "gap": gap2}
        print(f"  EDGE CHECK — same fold at chunk width {w2}")
        print(f"    n={n2} ECE={ece2} gap={gap2:+}   "
              f"(vs n={n} ECE={ece} gap={gap:+} at width {args.width})")
        if (n2, ece2, gap2) == (n, ece, gap):
            print("    IDENTICAL — chunk boundaries do not move this cell.")
        else:
            print("    ⚠️  DIFFERENT — chunking is affecting virtual_market "
                  "grouping; treat every class number as approximate.")
        print()

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump({
                "source": args.source, "category": args.category,
                "by": args.by, "width": args.width, "seconds": round(took, 1),
                "payload": {"n": pn, "ece": pece, "gap": pgap, **meta},
                "exact": {"n": n, "ece": ece, "gap": gap},
                "ladder_census": ladder_census,
                "edge_check": edge,
                "by_key": {str(k): {str(b): v for b, v in bb.items()}
                           for k, bb in by_key.items()},
                "halves": {h: {str(k): {str(b): v for b, v in bb.items()}
                               for k, bb in hv.items()}
                           for h, hv in halves.items()} if args.holdout_at else None,
            }, fh)
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
