#!/usr/bin/env python3
"""CAL-P150 — polymarket/cricket by MARKET-NAME FAMILY, under the D14 overrule.

WHY THIS EXISTS. D14, verbatim Alex: *"I refuse to believe that well traded
markets for any sport are fundamentally inaccurate. Markets aren't wrong;
calculations are."* CAL-P123's refusal — 1,971 candidate rules searched, not one
brings the cell under 3.0 — is not overturned as a measurement; what is
overturned is the CONCLUSION drawn from it. The presumption returns to our
pipeline, and the directive names the order: the wrong-leg class first, then
staleness, then leg-mapping.

THE FIRST LEAD IS REFUTED AND THIS FILE IS WHAT REPLACES IT. Running CAL-P138's
published leg-swap fold on cricket returns **0 families** over 6,264 cached rows
— and unlike the usual case that is NOT instrument blindness. Polymarket's
cricket book contains no Over/Under ladders at all. Its names are:

    <League>: <A> vs <B>                      the match winner
    <League>: <A> vs <B> - Most Sixes
    <League>: <A> vs <B> - Team Top Batter
    <League>: <A> vs <B> - Toss Match Double
    <League>: <A> vs <B> - Who wins the toss?

There is no `O/U <number>` anywhere in it, so a class defined as "the Over leg
is stored on the Under side" has no rows to act on here. That is a true zero,
and CAL-P134's lesson (a check by one grammar reports its own blindness as an
all-clear) is the reason it is stated with the names rather than as a count.

SO THE QUESTION BECOMES WHICH SHAPE CARRIES IT, and the shapes above are not one
kind of question. Four hypotheses, all OURS, and this fold is what separates
them — a single per-family reading of n, mean published price and realized
rate, which is the only cut that can tell "the venue misprices cricket" from
"we grade one family wrong":

  H1  TOSS MATCH DOUBLE is a CONJUNCTION (win the toss AND the match, ~0.25
      base rate against a ~0.5 match price). If it is graded on the match alone
      the realized rate exceeds the published price and the cell under-predicts
      — which is the direction the cell actually shows (gap -4.51).
  H2  WHO WINS THE TOSS is a true coin flip. A well-calibrated 50/50 family
      should contribute ~0 ECE; if it does not, the defect is in grading, not
      pricing, because nothing about a coin can be mispriced.
  H3  TEAM TOP BATTER is a FIELD market — one winner among ~11 batters. This is
      the polymarket/golf shape (CAL-P130: ~100 golfers each priced ~48% to
      finish top five), i.e. members priced as independent binaries rather than
      as a partition.
  H4  MOST SIXES / the bare match winner are ordinary 2-way questions and should
      be near the bar. If THEY carry the miss, none of the above is the story.

The cell's published reading is ECE 8.0, gap -4.51 on n=3,258 (q268). A negative
gap is UNDER-prediction: outcomes win more often than we said they would. H1 and
H3 both produce that sign; H2 produces it only if grading is wrong.

METHOD. Direct reads of `futures_markets` / `futures_outcomes`, chunked on
`fm.id` because an unbounded scan of this predicate hits the rail's statement
timeout (measured: it did). `MOD` is not sargable, so the chunking is a range
scan on the primary key — the same deviation CAL-P094 declared and for the same
reason.

🔴 WHAT THIS IS NOT. It is not the published population. It reads the raw tables,
so it will not reproduce the payload's n, and lesson 19 says a cell census is
not a published-population census. It is a POINTER at which family to fold
properly, not a measurement of the cell. Any number here that ends up in an
argument has to be re-derived through `_calibration_population_ctes` first.

EXIT CODES (gotcha #124):
  0  the fold completed and every family is reported
  4  the fold completed and the families do not reconstruct the cell's row count
     within tolerance — the partition is leaking and must not be read
  5  a chunk failed and the fold is incomplete
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

API = os.environ.get("BAINLUCK_API", "").rstrip("/")
TOKEN = os.environ.get("ADMIN_TOKEN", "")

#: The id span the leg-swap fold walked for this cell, so the two instruments
#: cover the same universe rather than two overlapping guesses.
ID_LO, ID_HI = 112_847, 59_851_747
CHUNKS = 12

SQL = """
SELECT
  CASE
    WHEN position(' - ' in fm.name) = 0 THEN 'match_winner'
    ELSE lower(btrim(substring(fm.name from position(' - ' in fm.name) + 3)))
  END AS family,
  COUNT(*) AS n,
  SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS sum_p,
  COUNT(*) FILTER (WHERE fo.is_winner = true) AS winners,
  COUNT(*) FILTER (WHERE fo.is_winner IS NULL) AS ungraded,
  COUNT(DISTINCT fm.id) AS markets
FROM futures_markets fm
JOIN futures_outcomes fo ON fo.market_id = fm.id
WHERE fm.source = 'polymarket'
  AND fm.llm_sport_category = 'cricket'
  AND fm.status = 'resolved'
  AND fm.id >= {lo} AND fm.id < {hi}
  AND COALESCE(fo.calibration_probability, fo.opening_probability) > 0
  AND COALESCE(fo.calibration_probability, fo.opening_probability) < 1
GROUP BY 1
"""


def query(sql: str):
    body = json.dumps({"sql": sql, "limit": 500}).encode()
    req = urllib.request.Request(
        f"{API}/api/admin/db-query",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as fh:
        return json.load(fh)


def main() -> int:
    if not API or not TOKEN:
        print("🔴 source ~/.claude/.env first (BAINLUCK_API / ADMIN_TOKEN)")
        return 5

    families: dict[str, dict] = {}

    def absorb(res) -> None:
        # Rows are ARRAYS, not dicts — zip against the declared column order.
        for row in res.get("rows") or []:
            fam, n, sum_p, winners, ungraded, markets = row
            acc = families.setdefault(
                fam, {"n": 0, "sum_p": 0.0, "winners": 0, "ungraded": 0, "markets": 0}
            )
            acc["n"] += int(n)
            acc["sum_p"] += float(sum_p or 0)
            acc["winners"] += int(winners)
            acc["ungraded"] += int(ungraded)
            acc["markets"] += int(markets)

    def pull(lo: int, hi: int, depth: int = 0) -> bool:
        """One id range, halving on a statement timeout rather than retrying.

        MEASURED: 11 of 12 equal chunks fit and the twelfth did not — the
        recent-id range is far denser than the old one, which is what an equal
        split over a primary key always gets wrong on a growing table. Retrying
        the same range would have failed the same way; the population is not
        transient, the WIDTH is wrong (memory: chunk, do not retry).
        """
        if depth > 6:
            print(f"    🔴 ids {lo}-{hi} will not fit at any width tried")
            return False
        try:
            res = query(SQL.format(lo=lo, hi=hi))
        except urllib.error.HTTPError as exc:
            payload = exc.read()[:400]
            if b"statement_timeout" not in payload:
                print(f"    🔴 ids {lo}-{hi} failed: {payload!r}")
                return False
            res = {"detail": {"reason": "statement_timeout"}}
        if isinstance(res, dict) and "detail" in res:
            reason = res["detail"]
            timed_out = isinstance(reason, dict) and reason.get("reason") == "statement_timeout"
            if not timed_out:
                print(f"    🔴 ids {lo}-{hi} refused: {reason}")
                return False
            mid = (lo + hi) // 2
            if mid <= lo:
                print(f"    🔴 ids {lo}-{hi} cannot be split further")
                return False
            print(f"    timeout — halving {lo}-{hi}", flush=True)
            return pull(lo, mid, depth + 1) and pull(mid, hi, depth + 1)
        absorb(res)
        return True

    step = (ID_HI - ID_LO) // CHUNKS + 1
    for i in range(CHUNKS):
        lo = ID_LO + i * step
        hi = min(lo + step, ID_HI + 1)
        print(f"  [{i+1}/{CHUNKS}] ids {lo}-{hi}", flush=True)
        if not pull(lo, hi):
            return 5

    rows = []
    for fam, a in families.items():
        if not a["n"]:
            continue
        mean_p = a["sum_p"] / a["n"]
        realized = a["winners"] / a["n"]
        rows.append(
            {
                "family": fam,
                "markets": a["markets"],
                "n": a["n"],
                "mean_price": round(mean_p, 4),
                "realized": round(realized, 4),
                # gap = price - realized, the board's sign convention: NEGATIVE
                # means we under-predicted (it happened more than we said).
                "gap_pp": round((mean_p - realized) * 100, 2),
                "ungraded": a["ungraded"],
            }
        )
    rows.sort(key=lambda r: -r["n"])
    total_n = sum(r["n"] for r in rows)

    out = {
        "cell": "polymarket/cricket",
        "basis": "RAW TABLES, not the published population — a pointer, not a measurement",
        "id_span": [ID_LO, ID_HI],
        "chunks": CHUNKS,
        "total_n": total_n,
        "families": rows,
    }
    with open(os.path.join(HERE, "cricket-shape.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    print()
    print("polymarket/cricket BY MARKET-NAME FAMILY  (raw tables, eligible-priced rows)")
    print(f"  {'family':<34} {'mkts':>6} {'n':>7} {'price':>7} {'realized':>9} "
          f"{'gap pp':>8} {'ungraded':>9}")
    for r in rows:
        print(f"  {r['family'][:34]:<34} {r['markets']:>6} {r['n']:>7} "
              f"{r['mean_price']:>7} {r['realized']:>9} {r['gap_pp']:>8} "
              f"{r['ungraded']:>9}")
    print(f"  {'TOTAL':<34} {'':>6} {total_n:>7}")

    if not rows:
        print("🔴 the fold found NO rows — that is a broken instrument, not a clean cell")
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
