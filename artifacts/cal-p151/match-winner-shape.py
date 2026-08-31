#!/usr/bin/env python3
"""CAL-P151 — why `match_winner` carries the whole polymarket/cricket miss.

WHAT THE FOLD FOUND FIRST. `cricket-population-fold.py` reproduced the published
cell on the deployed chain (3,260 rows against the payload's 3,258, gap +4.48 vs
+4.51) and then localised the miss: of the seven name-families, three of the four
big ones are essentially perfect —

    toss match double   -0.05 pp     team top batter  +0.32 pp
    most sixes          +0.41 pp

— and ONE family carries the cell:

    match_winner        +12.27 pp on 1,124 of 3,260 published rows

with an arithmetic tell that cannot be a pricing story. `toss match double`
publishes **0.99 winners per market**, exactly what a single-winner question
resolves to. `match_winner` publishes **1.96 winners per market** on the deployed
chain and **1.32** after the lift. A duel cannot have more than one winner.

WHAT THIS FILE MEASURES. Three readings, each one turning that ratio into a
distribution so it can be believed or killed:

  1. RAW — the winner-count distribution over every resolved Polymarket cricket
     market whose name carries no ' - ' (the match-winner family), by
     `n_outcomes`, `win_count` and `mutually_exclusive`. This says how big the
     class is and, crucially, **how much of it the malformed-binary rung can
     see**: that rung fires only on `n_outcomes = 2 AND mutually_exclusive`, so
     everything else is invisible to it.

  2. SAMPLES — the actual outcome rows of a few offending markets, read from the
     book rather than inferred from a count. CAL-P134's lesson and CAL-P150's:
     a class is not believed until its members are looked at.

  3. PUBLISHED — the same distribution restricted to rows that reach `deduped`,
     on both chains. This is the one that matters: a defect that never publishes
     is not the cell's miss. Run on `base` (the deployed predicate, i.e. the
     cell as served) and on `head` (the branch, i.e. after the lift).

🔴 WHAT THE SAMPLES SHOW, AND WHY IT IS AN INGESTION BUG NOT A GRADING ONE.
A market named `T20 World Cup: Australia vs Oman (Game 1)` has three outcomes,
and they are not `Australia` / `Oman` / `Draw`. They are:

    'T20 World Cup: Australia vs Oman (Game 1)'
    'T20 World Cup: Australia vs Oman (Game 1) - Completed match'
    'T20 World Cup: Australia vs Oman (Game 1) - Who wins the toss'

Those are the names of three SIBLING MARKETS. The event's sub-markets have been
collapsed into one market's outcome list instead of being decomposed — gotcha
#18 ("Polymarket game events are nested sub-markets — decompose by
`condition_id`"), unapplied here. Each sibling resolved YES on its own question,
so the market carries two or three `is_winner = true` rows, and the published
realized rate is inflated far above the price.

This is squarely D14's premise: the venue priced the coin flip at 0.4997 and the
well-formed families land within half a point. The broken component is ours.

EXIT CODES (gotcha #124):
  0  all three readings completed
  5  a query failed or the environment is missing
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "backend"))

#: The fold module owns the population collection, the component chunking and
#: the scope argument. Imported rather than re-implemented so the two files
#: cannot drift about which markets "cricket" means.
_spec = importlib.util.spec_from_file_location(
    "cal_p151_fold", os.path.join(HERE, "cricket-population-fold.py")
)
fold = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fold)

#: The match-winner family: a Polymarket cricket market whose name carries no
#: ' - ' suffix. Same classifier the fold uses, so the two agree family-for-family.
MATCH_WINNER_PREDICATE = "position(' - ' in fm.name) = 0"

RAW_SQL = """
SELECT t.n_outcomes, t.win_count, t.mex, COUNT(*) AS markets
FROM (
  SELECT fm.id, fm.mutually_exclusive AS mex,
         COUNT(*) AS n_outcomes,
         COUNT(*) FILTER (WHERE fo.is_winner = true) AS win_count
  FROM futures_markets fm
  JOIN futures_outcomes fo ON fo.market_id = fm.id
  WHERE fm.id IN ({ids}) AND {pred}
  GROUP BY 1, 2
) t
GROUP BY 1, 2, 3
"""

PUBLISHED_TAIL = f"""
, pub AS (
  SELECT d.market_id, d.outcome_id, d.is_winner
  FROM deduped d
  JOIN futures_markets fm ON fm.id = d.market_id
  WHERE d.source = 'polymarket' AND d.category = 'cricket'
    AND {MATCH_WINNER_PREDICATE}
)
SELECT legs, wins, COUNT(*) AS markets FROM (
  SELECT market_id, COUNT(*) AS legs, COUNT(*) FILTER (WHERE is_winner) AS wins
  FROM pub GROUP BY 1
) t
GROUP BY 1, 2
ORDER BY 1, 2
"""

ID_BATCH = 1500


def main() -> int:
    if not fold.API or not fold.TOKEN:
        print("🔴 source ~/.claude/.env first (BAINLUCK_API / ADMIN_TOKEN)")
        return 5

    print("=" * 88)
    print("CAL-P151 — the shape of polymarket/cricket `match_winner`")
    print("=" * 88)

    try:
        markets = fold.collect_cricket_markets()
    except (urllib.error.HTTPError, RuntimeError) as exc:
        print(f"🔴 collection failed: {exc}")
        return 5
    poly = [int(m["id"]) for m in markets if m["source"] == "polymarket"]
    print(f"\nresolved Polymarket cricket markets: {len(poly):,}")

    # ---- 1. RAW ---------------------------------------------------------
    print("\n[1/3] RAW winner-count distribution over the match-winner family")
    agg: dict[tuple, int] = {}
    for i in range(0, len(poly), ID_BATCH):
        sql = RAW_SQL.format(
            ids=",".join(str(x) for x in poly[i : i + ID_BATCH]),
            pred=MATCH_WINNER_PREDICATE,
        )
        try:
            res = fold.query(sql)
        except urllib.error.HTTPError as exc:
            print(f"🔴 raw batch failed: {exc} {exc.read()[:200]!r}")
            return 5
        for r in res["rows"]:
            agg[(r[0], r[1], r[2])] = agg.get((r[0], r[1], r[2]), 0) + int(r[3])

    print(f"\n  {'n_outcomes':>10} {'win_count':>10} {'mutually_excl':>14} {'markets':>9}")
    for k in sorted(agg):
        print(f"  {k[0]:>10} {k[1]:>10} {str(k[2]):>14} {agg[k]:>9,}")
    total = sum(agg.values())
    bad = sum(v for k, v in agg.items() if k[1] != 1)
    # The malformed-binary rung: `mi.mutually_exclusive = true AND
    # mrs.n_outcomes = 2 AND mrs.win_count <> 1`. Anything outside that shape is
    # a market the rung cannot reach, however wrong its winner count is.
    caught = sum(v for k, v in agg.items() if k[1] != 1 and k[0] == 2 and k[2])
    print(f"\n  markets total: {total:,}")
    print(f"  win_count != 1: {bad:,} ({100.0 * bad / total:.1f}%)")
    print(f"    caught by the malformed-binary rung (n_outcomes=2 AND mex): {caught:,}")
    print(f"    🔴 INVISIBLE to it: {bad - caught:,}")

    # ---- 2. SAMPLES -----------------------------------------------------
    print("\n[2/3] SAMPLES — read from the book, not inferred from the count")
    samples: list[tuple] = []
    for i in range(0, len(poly), ID_BATCH):
        if len(samples) >= 4:
            break
        sql = (
            "SELECT fm.id, fm.name, COUNT(*) AS n_out, "
            "COUNT(*) FILTER (WHERE fo.is_winner) AS wins "
            "FROM futures_markets fm JOIN futures_outcomes fo ON fo.market_id=fm.id "
            f"WHERE fm.id IN ({','.join(str(x) for x in poly[i:i + ID_BATCH])}) "
            f"AND {MATCH_WINNER_PREDICATE} "
            "GROUP BY 1,2 HAVING COUNT(*)=3 "
            "AND COUNT(*) FILTER (WHERE fo.is_winner) IN (2,3)"
        )
        try:
            res = fold.query(sql)
        except urllib.error.HTTPError:
            continue
        for r in res["rows"]:
            if len(samples) < 4:
                samples.append((r[0], r[1]))
    for mid, name in samples:
        print(f"\n  market {mid}: {name!r}")
        res = fold.query(
            "SELECT fo.name, fo.is_winner, fo.opening_probability, "
            f"fo.calibration_probability FROM futures_outcomes fo "
            f"WHERE fo.market_id={mid} ORDER BY fo.id"
        )
        for r in res["rows"]:
            print(
                f"     is_winner={str(r[1]):<5} open={str(r[2]):<6} cal={str(r[3]):<6} "
                f"outcome={r[0]!r}"
            )
    print(
        "\n  🔴 the outcomes are the names of SIBLING MARKETS, not the legs of a duel."
    )

    # ---- 3. PUBLISHED ---------------------------------------------------
    print("\n[3/3] PUBLISHED — the same distribution among rows that reach `deduped`")
    comps = fold.components(markets)
    chunks = fold.pack(comps, fold.FOLD_CHUNK_MARKETS)
    from app.utils.sql_comment_strip import strip_sql_comments

    published: dict[str, dict] = {}
    for chain in ("base", "head"):
        build = fold.load_population_builder(chain)
        pagg: dict[tuple, int] = {}
        work = list(chunks)
        while work:
            ch = work.pop(0)
            flat = [i for c in ch for i in c]
            sql = strip_sql_comments(
                "WITH "
                + build(market_info_extra="AND fm.id IN (" + ",".join(map(str, flat)) + ")")
                + PUBLISHED_TAIL
            )
            try:
                res = fold.query(sql)
            except urllib.error.HTTPError as exc:
                if len(ch) < 2:
                    print(f"🔴 an unsplittable chunk failed: {exc}")
                    return 5
                mid = len(ch) // 2
                work.insert(0, ch[mid:])
                work.insert(0, ch[:mid])
                continue
            for r in res["rows"]:
                pagg[(r[0], r[1])] = pagg.get((r[0], r[1]), 0) + int(r[2])
        tot = sum(pagg.values())
        badp = sum(v for k, v in pagg.items() if k[1] != 1)
        label = "DEPLOYED — the cell as served" if chain == "base" else "AFTER THE LIFT"
        print(f"\n  === {chain}: {label} ===")
        print(f"  {'legs_pub':>9} {'winners_pub':>12} {'markets':>9}")
        for k in sorted(pagg):
            print(f"  {k[0]:>9} {k[1]:>12} {pagg[k]:>9,}")
        print(
            f"  published match_winner markets: {tot:,};  "
            f"win_count != 1: {badp:,} ({100.0 * badp / tot:.1f}%)"
        )
        published[chain] = {
            "distribution": {f"{k[0]}legs_{k[1]}wins": v for k, v in sorted(pagg.items())},
            "markets": tot,
            "win_count_not_1": badp,
        }

    out = os.path.join(HERE, "match-winner-shape.json")
    with open(out, "w") as fh:
        json.dump(
            {
                "raw": {
                    "distribution": {
                        f"{k[0]}out_{k[1]}win_mex{k[2]}": v for k, v in sorted(agg.items())
                    },
                    "markets": total,
                    "win_count_not_1": bad,
                    "caught_by_malformed_binary_rung": caught,
                    "invisible_to_it": bad - caught,
                },
                "samples": [{"market_id": m, "name": n} for m, n in samples],
                "published": published,
            },
            fh,
            indent=1,
            default=str,
        )
    print(f"\nbanked -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
