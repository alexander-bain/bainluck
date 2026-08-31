#!/usr/bin/env python3
"""CAL-P155 stage 1 — bound the population D13's per-MARKET arm can move.

WHY THIS EXISTS. Alex ruled D13's admission arm PER-MARKET
(`alex-inbox/calibration-919` option A): each independently-graded lone claim
publishes on its own even when two land in the same virtual variant. The number
owed coming out is *how much population that moves* — the measurement parked as
`CAL-P151-P1a` in `PARKED-MEASUREMENTS.md`.

THE SCOPE ARGUMENT — this is a bound by CONSTRUCTION, not a sample. Derive it
from the two arms rather than from the story:

    retired:  market_count = 1 AND total_outcomes = 1 AND graded >= 1
    ruled:    graded_lone_claims >= 1 AND ungraded_lone_claims = 0

A variant changes only where the second fires and the first did not, which needs
``market_count >= 2`` — with ``market_count = 1`` the single market either IS the
graded lone claim (both arms fire) or is not one at all (neither does). And
``market_count >= 2`` needs a ``g:``/``e:`` vm_id, i.e. a group or event key with
>=3 resolved markets in the same source; an ``m:`` variant holds exactly one
market by definition.

So: **every variant the ruling can touch lives under a key with >=3 resolved
markets holding >=1 single-outcome market.** Anything this stage does not return
is excluded by construction.

🔴 **AN EARLIER CUT OF THIS FILE SAID `>=2` SINGLE-OUTCOME MARKETS AND THAT WAS
WRONG BY 3x.** It reasoned from the CASE Alex ruled on — two lone claims sharing
a variant — instead of from the predicate. A variant holding ONE lone claim
beside one MULTI-outcome market also carries ``market_count = 2``, so the retired
arm refused the lone claim there too, and the ruled arm admits it (its
multi-outcome neighbour has ``win_count = 0`` in a no-winner variant and
``no_winner_markets`` drops it). Measured, the difference is not cosmetic:
**890 event keys at ``>=2`` against 6,108 at ``>=1``.** *Scope a change from the
predicate it ships, not from the example that motivated it.*

⚠️ IT IS A SUPERSET AND SAYS SO. Two deliberate loosenings, both in the safe
direction: the ``datagolf_recovery_residual`` exclusion is dropped (it forces a
JSONB detoast per row and the residual is ~0 by design), and a market under a
>=3 GROUP that also sits in a >=3 EVENT is counted on both sides. Stage 2 runs
the producer's own ``virtual_market`` and resolves both exactly.

HOW IT PARTITIONS, AND WHY NOT THE OBVIOUS WAYS. Measured on the read rail this
session (every correlation id banked in the JSON):

  * unscoped chain ``SELECT COUNT(*) FROM market_info``          -> timeout
  * ``SELECT COUNT(*) FROM futures_outcomes``                    -> timeout
  * the group-key aggregate over all of ``status='resolved'``    -> timeout
  * ``mod(fm.event_id, 16) = k`` sharding                        -> timeout

🔴 **The hash-modulus recipe fails here and the reason generalizes:** a modulus
on the grouping key is not sargable, so every shard still scans the whole table.
It assumes the scan is the cheap part. On this database (103% of plan) it is the
only part that costs anything.

What IS sargable is the key's own index — ``ix_futures_markets_event_id`` and
``ix_futures_markets_group_id``. Partitioning on **key RANGES** therefore drives
an index scan AND makes every key whole within exactly one partition, so each
partition emits ONE summary row and nothing has to be reassembled client-side.
An earlier cut of this file grouped by ``fm.id`` windows and had to accumulate
per-key totals in the client; key density blew past the 1,000-row cap on the
first window and it halved nine times without finishing a single range.

🔴 **TEXT RANGES ARE SPLIT BY ASKING THE DATABASE, NEVER BY ARITHMETIC.**
``group_id`` is text under an ``en_US`` collation, so a midpoint computed from
character codes is not the midpoint of the index's ordering. Splits come from
``ORDER BY group_id OFFSET n/2 LIMIT 1``, which is the collation's own answer.

🔴 **COVERAGE IS PROVED BY RECONCILIATION, NOT ASSUMED.** The per-partition
market counts must sum to the global count of resolved markets carrying that
key. If they do not, the tiling has a hole and the run FAILS rather than
reporting a number that is quietly short.

Read-only: SELECTs on the admin read rail. No task is queued, nothing is busted.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _rail import query, rows_as_dicts  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "lone-claim-candidates.json")

#: Stay under the 60 req/min limiter — a throttled response parses as null JSON.
REQ_SPACING_S = 1.05
ROW_CAP = 1000

#: `market_result_shape` counts outcomes over the market AS CAPTURED, so the
#: single-outcome test is over all of `futures_outcomes`, unfiltered. Two
#: semi-joins rather than `GROUP BY market_id HAVING COUNT(*)=1`: both are
#: correct, but the aggregate reads every outcome row of every market in the
#: partition and timed out at 1/8 of the population, while these stop at the
#: second index tuple.
LONE_PREDICATE = """
             EXISTS (SELECT 1 FROM futures_outcomes o WHERE o.market_id = fm.id)
         AND NOT EXISTS (
               SELECT 1 FROM futures_outcomes o WHERE o.market_id = fm.id OFFSET 1)
"""

PARTITION_SQL = """
SELECT COUNT(*) AS keys_,
       COALESCE(SUM(n), 0) AS markets_,
       COUNT(*) FILTER (WHERE n >= 3) AS keys_ge3,
       COUNT(*) FILTER (WHERE n >= 3 AND lone >= 1) AS keys_ge3_lone1,
       COUNT(*) FILTER (WHERE n >= 3 AND lone >= 2) AS keys_ge3_lone2,
       -- THE BOUND. Lone markets under a key that can hold a multi-market
       -- variant: every market the ruling can newly admit is one of these.
       COALESCE(SUM(lone) FILTER (WHERE n >= 3 AND lone >= 1), 0) AS lone_in_ge1,
       -- Kept beside it because it is the sub-case Alex's ruling was ARGUED on
       -- (two graded lone claims in one variant), and reporting only the wider
       -- number would lose the distinction the decision was made about.
       COALESCE(SUM(lone) FILTER (WHERE n >= 3 AND lone >= 2), 0) AS lone_in_ge2
FROM (
  SELECT fm.{col}, fm.source, COUNT(*) AS n,
         COUNT(*) FILTER (WHERE {lone}) AS lone
  FROM futures_markets fm
  WHERE fm.status = 'resolved' AND {bounds}
  GROUP BY 1, 2
) k
"""

LIST_SQL = """
SELECT k.{col} AS key_, k.source, k.n AS n_resolved, k.lone AS n_lone
FROM (
  SELECT fm.{col}, fm.source, COUNT(*) AS n,
         COUNT(*) FILTER (WHERE {lone}) AS lone
  FROM futures_markets fm
  WHERE fm.status = 'resolved' AND {bounds}
  GROUP BY 1, 2
) k
WHERE k.n >= 3 AND k.lone >= 1
ORDER BY k.lone DESC, k.{col}
"""

_last_req = 0.0


def ask(sql: str, limit: int = ROW_CAP) -> list[dict]:
    global _last_req
    gap = REQ_SPACING_S - (time.time() - _last_req)
    if gap > 0:
        time.sleep(gap)
    _last_req = time.time()
    return rows_as_dicts(query(sql, limit=limit))


def _int_bounds(col: str, lo, hi) -> str:
    parts = [f"fm.{col} IS NOT NULL"]
    if lo is not None:
        parts.append(f"fm.{col} >= {lo}")
    if hi is not None:
        parts.append(f"fm.{col} < {hi}")
    return " AND ".join(parts)


def _txt_bounds(col: str, lo, hi) -> str:
    parts = [f"fm.{col} IS NOT NULL"]
    if lo is not None:
        parts.append(f"fm.{col} >= '{lo.replace(chr(39), chr(39) * 2)}'")
    if hi is not None:
        parts.append(f"fm.{col} < '{hi.replace(chr(39), chr(39) * 2)}'")
    return " AND ".join(parts)


def _split_int(lo, hi, col, bounds_fn):
    # Integer seeds are built fully bounded from the measured MIN/MAX so a
    # refused top partition can still be halved. An unbounded one is a bug in
    # the seed list, not a condition to work around.
    if lo is None or hi is None:
        raise RuntimeError(f"cannot split an unbounded {col} partition [{lo},{hi})")
    mid = lo + (hi - lo) // 2
    if mid <= lo or mid >= hi:
        raise RuntimeError(f"{col} partition [{lo},{hi}) is one value and still refused")
    return mid


#: Offsets tried, largest first, when cutting a text partition. A ladder rather
#: than `COUNT(*)/2` on purpose: the count is an aggregate over the whole
#: partition and it TIMED OUT inside the splitter on the first run — the split
#: helper must be cheaper than the query it is rescuing, or it inherits the
#: failure it exists to fix. Each rung is one `ORDER BY ... OFFSET k LIMIT 1`,
#: which walks the index and stops, and the first rung that lands strictly
#: inside the range wins.
_SPLIT_OFFSETS = (100_000, 40_000, 15_000, 5_000, 1_500, 400, 100, 25, 5, 1)


def _split_txt(lo, hi, col, bounds_fn):
    """Ask the DATABASE for the cut point — the collation's ordering, not ASCII's.

    ``group_id`` is text under an ``en_US`` collation, so a midpoint computed
    from character codes is not the midpoint of the index the range scan uses.
    Every candidate comes from the index itself, so lo < cut < hi holds in the
    same ordering the ``>=``/``<`` bounds are evaluated in.
    """
    for k in _SPLIT_OFFSETS:
        try:
            rows = ask(
                f"SELECT fm.{col} AS m FROM futures_markets fm "
                f"WHERE fm.status='resolved' AND {bounds_fn(col, lo, hi)} "
                f"ORDER BY fm.{col} OFFSET {k} LIMIT 1",
                limit=5,
            )
        except urllib.error.HTTPError:
            continue
        if rows and rows[0]["m"] is not None and rows[0]["m"] != lo:
            return rows[0]["m"]
    raise RuntimeError(
        f"no usable cut point inside {col} partition [{lo},{hi}) — every offset "
        f"in {_SPLIT_OFFSETS} either fell outside the range or was refused"
    )


#: Markets per text partition. Sized from measurement, not taste: a
#: `polymarket:1*` range holding 3,666 markets aggregated in 0.9 s against a 10 s
#: wall, so ~8,000 leaves better than 2x headroom on a database whose load other
#: lanes are moving underneath this run.
TEXT_STRIDE = 8_000


def build_text_tiling(col: str) -> list[tuple]:
    """Tile a TEXT key by walking its own index, before aggregating anything.

    🔴 THIS REPLACES GUESSED PREFIX BOUNDS, AND THE COLLATION IS WHY. The first
    cut of this file seeded `[None,'kalshi;')`, `['kalshi;','polymarket;')`,
    `['polymarket;',None)` — obvious in ASCII and WRONG under `en_US`, where
    punctuation is not compared at the primary level, so `'kalshi;'` sorts
    BEFORE `'kalshi:AUCTIONPRICETREY-26'` and the first partition was empty
    while claiming to hold every Kalshi group. It then timed out anyway (an
    unbounded `col < 'x'` estimates most of the table and the planner takes a
    sequential scan), and the splitter could find no cut point inside an empty
    range. Two independent failures from one assumption about ordering.

    Every boundary here comes from `ORDER BY {col} OFFSET n LIMIT 1`, so it is
    the collation's own answer and the partitions tile the space by
    construction. Walking the index in strides also means no partition is ever
    discovered by a 10 s timeout — the cost is paid once, in cheap index scans,
    instead of once per oversized range.
    """
    first = ask(
        f"SELECT fm.{col} AS m FROM futures_markets fm "
        f"WHERE fm.status='resolved' AND fm.{col} IS NOT NULL "
        f"ORDER BY fm.{col} LIMIT 1", limit=5)
    if not first:
        raise RuntimeError(f"no resolved market carries a {col}")
    cuts = [first[0]["m"]]
    while True:
        nxt = None
        # A single key can hold more markets than the stride (one group with
        # 20k legs), which would return the boundary we are already standing on
        # and loop forever. Step out until the cut MOVES.
        for stride in (TEXT_STRIDE, TEXT_STRIDE * 4, TEXT_STRIDE * 16, TEXT_STRIDE * 64):
            rows = ask(
                f"SELECT fm.{col} AS m FROM futures_markets fm "
                f"WHERE fm.status='resolved' AND {_txt_bounds(col, cuts[-1], None)} "
                f"ORDER BY fm.{col} OFFSET {stride} LIMIT 1", limit=5)
            if rows and rows[0]["m"] is not None and rows[0]["m"] != cuts[-1]:
                nxt = rows[0]["m"]
                break
            if not rows:
                break          # past the end: the tail partition closes the tiling
        if nxt is None:
            break
        cuts.append(nxt)
        if len(cuts) % 25 == 0:
            print(f"  {col}: {len(cuts)} cut points so far")
    # The tail is left OPEN so the tiling provably covers everything at or above
    # the first key, and the first key is the measured minimum — so it covers
    # the whole population. Step 4 reconciles that claim against a count taken
    # a different way.
    return list(zip(cuts, cuts[1:])) + [(cuts[-1], None)]


def count_by_id_ranges(extra_pred: str, span: int = 4_000_000) -> int:
    """`COUNT(*)` over the resolved population, walked on the PRIMARY KEY.

    Every window drives `futures_markets_pkey`, so a window that is refused is
    halved rather than retried — the range is the thing that was too big, and
    the same plan at the same size fails the same way (gotcha #124's sibling).
    """
    hi_row = ask("SELECT MAX(fm.id) AS hi FROM futures_markets fm", limit=5)[0]
    top = int(hi_row["hi"]) + 1
    work = [(lo, min(lo + span, top)) for lo in range(0, top, span)]
    total = 0
    while work:
        lo, hi = work.pop(0)
        try:
            row = ask(
                f"SELECT COUNT(*) AS n FROM futures_markets fm "
                f"WHERE fm.status='resolved' AND {extra_pred} "
                f"AND fm.id >= {lo} AND fm.id < {hi}", limit=5)[0]
        except urllib.error.HTTPError:
            if hi - lo <= 1:
                raise RuntimeError(f"id window [{lo},{hi}) is one id and still refused")
            mid = lo + (hi - lo) // 2
            work[:0] = [(lo, mid), (mid, hi)]
            continue
        total += int(row["n"])
    return total


def sweep(col: str, seeds, bounds_fn, split_fn, label: str) -> dict:
    """Walk key-range partitions, halving any that the rail refuses."""
    acc = {
        "keys_": 0, "markets_": 0, "keys_ge3": 0,
        "keys_ge3_lone1": 0, "keys_ge3_lone2": 0,
        "lone_in_ge1": 0, "lone_in_ge2": 0,
    }
    work = list(seeds)
    ranges_done: list[tuple] = []
    refusals = 0
    t0 = time.time()
    while work:
        lo, hi = work.pop(0)
        sql = PARTITION_SQL.format(
            col=col, lone=LONE_PREDICATE, bounds=bounds_fn(col, lo, hi)
        )
        try:
            row = ask(sql, limit=10)[0]
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:160].decode(errors="replace")
            refusals += 1
            # The splitter runs its own queries, so it can be refused too. That
            # is a stop, not a crash: a partition nobody can cut is a HOLE in
            # the tiling, and the reconciliation in step 4 must see it.
            try:
                mid = split_fn(lo, hi, col, bounds_fn)
            except (RuntimeError, urllib.error.HTTPError) as split_exc:
                print(f"🔴 {label} [{lo},{hi}) was refused AND cannot be split: {split_exc}")
                return {"__hole__": (lo, hi)}
            work[:0] = [(lo, mid), (mid, hi)]
            print(f"  {label} [{lo},{hi}) refused -> split at {mid}   ({detail[:60]})")
            continue
        for k in acc:
            acc[k] += int(row[k])
        ranges_done.append((lo, hi))
        if len(ranges_done) % 10 == 0:
            print(f"  {label}: {len(ranges_done)} partitions, {len(work)} queued, "
                  f"{acc['markets_']:,} markets, {time.time() - t0:.0f}s")
    acc["partitions"] = len(ranges_done)
    acc["refusals"] = refusals
    acc["ranges"] = [[lo, hi] for lo, hi in ranges_done]
    acc["elapsed_s"] = round(time.time() - t0, 1)
    return acc


def list_candidates(col: str, ranges, bounds_fn, split_fn, label: str) -> tuple:
    """Re-walk the PROVEN tiling and pull the qualifying keys themselves.

    🔴 THIS STEP IS OPTIONAL AND MUST NOT BE ABLE TO DESTROY THE ANSWER. The
    first run of this file reconciled BOTH tilings exactly — 435,105 event and
    862,408 group markets, the whole measurement done — and then threw the lot
    away because a single partition here was refused and the exception unwound
    before anything was banked. The counts are the deliverable; the key list is
    a convenience for stage 2. So `main` banks BEFORE calling this, a refusal
    splits the partition rather than raising, and a partition that still cannot
    be read is RETURNED BY NAME instead of silently missing.
    """
    out: list[dict] = []
    unlisted: list[dict] = []
    work = [(lo, hi, 0) for lo, hi in ranges]
    while work:
        lo, hi, depth = work.pop(0)
        sql = LIST_SQL.format(col=col, lone=LONE_PREDICATE, bounds=bounds_fn(col, lo, hi))
        try:
            rows = ask(sql, limit=ROW_CAP)
        except urllib.error.HTTPError as exc:
            reason = exc.read()[:120].decode(errors="replace")
            if depth >= 8:
                unlisted.append({"lo": lo, "hi": hi, "why": f"refused at depth {depth}"})
                continue
            try:
                mid = split_fn(lo, hi, col, bounds_fn)
            except (RuntimeError, urllib.error.HTTPError):
                unlisted.append({"lo": lo, "hi": hi, "why": f"unsplittable: {reason}"})
                continue
            work[:0] = [(lo, mid, depth + 1), (mid, hi, depth + 1)]
            continue
        if len(rows) >= ROW_CAP:
            # The rail truncates at 1,000 SILENTLY. Splitting is the only honest
            # response; believing a capped answer is how a short list reads as a
            # complete one.
            if depth >= 8:
                unlisted.append({"lo": lo, "hi": hi, "why": "still at the row cap"})
                continue
            try:
                mid = split_fn(lo, hi, col, bounds_fn)
            except (RuntimeError, urllib.error.HTTPError):
                unlisted.append({"lo": lo, "hi": hi, "why": "capped and unsplittable"})
                continue
            work[:0] = [(lo, mid, depth + 1), (mid, hi, depth + 1)]
            continue
        out.extend(rows)
    return out, unlisted


def main() -> int:
    started = time.time()
    print("=" * 92)
    print("CAL-P155 stage 1 — variants that can hold two lone claims (CAL-P151-P1a)")
    print("=" * 92)

    print("\n[1/4] GLOBAL TOTALS — the reconciliation target")
    # CHUNKED, NOT RETRIED. The bare `COUNT(*) ... WHERE status='resolved'`
    # answered in 5.2 s on the first probe of this session and TIMED OUT on the
    # third, with nothing changed but the load other lanes were putting on a
    # database at 103% of plan. Re-running a plan that just exceeded the wall is
    # the one response guaranteed not to help; the pkey range is the smaller
    # question that always fits.
    tot_g = count_by_id_ranges("fm.group_id IS NOT NULL")
    tot_e = count_by_id_ranges("fm.event_id IS NOT NULL")
    print(f"  resolved markets carrying group_id: {tot_g:,}")
    print(f"  resolved markets carrying event_id: {tot_e:,}")

    print("\n[2/4] EVENT-KEY SWEEP")
    span = ask(
        "SELECT MIN(fm.event_id) AS lo, MAX(fm.event_id) AS hi FROM futures_markets fm "
        "WHERE fm.status='resolved' AND fm.event_id IS NOT NULL", limit=5)[0]
    ev_lo, ev_hi = int(span["lo"]), int(span["hi"]) + 1
    # Fully bounded, and the tiling is closed on both ends so the reconciliation
    # in step 4 is a real check rather than a tautology over an open range.
    cuts = [ev_lo, 2_000_000, 6_000_000, 9_000_000, 12_000_000, 14_000_000, ev_hi]
    cuts = sorted({c for c in cuts if ev_lo <= c <= ev_hi} | {ev_lo, ev_hi})
    ev_seeds = list(zip(cuts, cuts[1:]))
    print(f"  event_id spans [{ev_lo:,}, {ev_hi:,}) in {len(ev_seeds)} seed partitions")
    ev = sweep("event_id", ev_seeds, _int_bounds, _split_int, "event")

    print("\n[3/4] GROUP-KEY SWEEP")
    gr_seeds = build_text_tiling("group_id")
    print(f"  group_id tiled into {len(gr_seeds)} partitions by striding the index")
    gr = sweep("group_id", gr_seeds, _txt_bounds, _split_txt, "group")

    for name, acc in (("event", ev), ("group", gr)):
        if "__hole__" in acc:
            lo, hi = acc["__hole__"]
            print(f"🔴 the {name} tiling has an unreadable hole at [{lo},{hi}). Every "
                  f"count would be short by an unknown amount. Refusing to report.")
            return 4

    print("\n[4/4] RECONCILE, then list the candidates")
    ok_e = ev["markets_"] == tot_e
    ok_g = gr["markets_"] == tot_g
    print(f"  event tiling  {ev['markets_']:,} vs {tot_e:,}  {'OK' if ok_e else '🔴 HOLE'}")
    print(f"  group tiling  {gr['markets_']:,} vs {tot_g:,}  {'OK' if ok_g else '🔴 HOLE'}")
    if not (ok_e and ok_g):
        print("🔴 the partitions do not tile the key space; every count below would be "
              "short by an unknown amount. Refusing to report.")
        return 4

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "totals": {"resolved_with_group_id": tot_g, "resolved_with_event_id": tot_e},
        "event_sweep": {k: v for k, v in ev.items() if k != "ranges"},
        "group_sweep": {k: v for k, v in gr.items() if k != "ranges"},
        "reconciled": True,
        "candidate_listing": "not attempted yet",
        "caveats": [
            "SUPERSET: the datagolf_recovery_residual exclusion is not applied here.",
            "SUPERSET: a market under a >=3 group that also sits in a >=3 event is "
            "counted on BOTH sides; the producer assigns it to g: only.",
            "A candidate key still moves NOTHING unless its whole variant has no "
            "winner at all. Stage 2 answers that on the producer's own chain.",
        ],
    }

    # 🔴 BANK THE RECONCILED COUNTS BEFORE THE OPTIONAL STEP. They are the
    # deliverable and they are already proved; the key list is a convenience.
    # The first run of this file reconciled both tilings and then lost
    # everything to an exception in the listing below.
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"  counts banked -> {OUT} (before listing, so listing cannot lose them)")

    cand_e, unlisted_e = list_candidates(
        "event_id", ev["ranges"], _int_bounds, _split_int, "event")
    cand_g, unlisted_g = list_candidates(
        "group_id", gr["ranges"], _txt_bounds, _split_txt, "group")
    out["elapsed_s"] = round(time.time() - started, 1)
    out["candidate_listing"] = (
        "complete" if not (unlisted_e or unlisted_g) else "PARTIAL — see unlisted_ranges")
    out["candidate_event_keys"] = cand_e
    out["candidate_group_keys"] = cand_g
    out["unlisted_ranges"] = {"event": unlisted_e, "group": unlisted_g}
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=2)
    if unlisted_e or unlisted_g:
        print(f"⚠️  {len(unlisted_e)} event and {len(unlisted_g)} group ranges could NOT "
              f"be listed — the key LIST is short by an unknown amount and says so. "
              f"The COUNTS above are unaffected: they come from the reconciled sweep.")

    print("\n" + "=" * 92)
    print("  THE BOUND — keys with >=3 markets holding >=1 lone claim:")
    print(f"    event  {ev['keys_ge3_lone1']:>7,} keys   {ev['lone_in_ge1']:>7,} lone markets")
    print(f"    group  {gr['keys_ge3_lone1']:>7,} keys   {gr['lone_in_ge1']:>7,} lone markets")
    print(f"    TOTAL  {ev['keys_ge3_lone1'] + gr['keys_ge3_lone1']:>7,} keys   "
          f"{ev['lone_in_ge1'] + gr['lone_in_ge1']:>7,} lone markets  <- upper bound")
    print("  of which the sub-case the ruling was ARGUED on (>=2 lone in one key):")
    print(f"    event  {ev['keys_ge3_lone2']:>7,} keys   {ev['lone_in_ge2']:>7,} lone markets")
    print(f"    group  {gr['keys_ge3_lone2']:>7,} keys   {gr['lone_in_ge2']:>7,} lone markets")
    print(f"  candidate keys listed            : {len(cand_e):,} event + {len(cand_g):,} group")
    print(f"  banked -> {OUT}")
    print("=" * 92)
    print("⚠️  This is the CANDIDATE BOUND, not the delta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
