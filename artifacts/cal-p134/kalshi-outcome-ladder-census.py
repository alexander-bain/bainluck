"""Offline census: the Kalshi OUTCOME-site cumulative ladder, which --by mono cannot see.

CAL-P133 built ``app/utils/ladder_monotonicity`` with two rung sites. The NAME
site (one market per rung, price = the YES leg) is what ``--by mono`` folds. The
OUTCOME site exists in the module but is wired to exactly one grammar: a bare
``2400+`` leg, every leg of the market, or the market is refused.

Kalshi does not write that grammar. Kalshi writes ``Above 410M``, ``above
$68.25`` and — most of all — ``7,175 or above``. So a ``--by mono`` fold of
``kalshi/economics`` reads 46 families and one condemned pair on a cell that is
wall-to-wall cumulative ladders: the instrument reports its own blindness as an
all-clear (gotcha #53, lesson 16).

This script measures, offline and on the raw cell, three things a rule design
needs before it is worth wiring:

  1. how much of the cell is an all-cumulative-legs market at all;
  2. whether those legs are BROADLY monotone — the falsification test for the
     premise. If ``above X`` legs were mutually exclusive brackets rather than
     cumulative thresholds, their prices would not be ordered, and the coherent
     share would sit near chance instead of near one;
  3. the violating markets, by name, so a cert can argue about a specific pair.

⚠️ Its counts are RAW-CELL counts. Lesson 19: the published population is a
different and much smaller thing, and only the exact rail can measure it.
"""
import gzip, json, os, re, subprocess, sys, collections

API = os.environ["BAINLUCK_API"]; TOK = os.environ["ADMIN_TOKEN"]
CAP = 1000


def q(sql, limit=CAP):
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{API}/api/admin/db-query",
         "-H", f"Authorization: Bearer {TOK}", "-H", "Content-Type: application/json",
         "-d", json.dumps({"sql": sql, "limit": limit})],
        capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        raise RuntimeError(r.stdout[:400])


ROWS_SQL = """
SELECT fm.id, fm.name, fm.market_type, fo.name,
       COALESCE(fo.calibration_probability, fo.opening_probability),
       fo.is_winner, fo.resolution_source
FROM futures_markets fm JOIN futures_outcomes fo ON fo.market_id = fm.id
WHERE fm.source = '{src}'
  AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{cat}'
  AND fm.id >= {lo} AND fm.id < {hi}
"""


def pull(src, cat, lo, hi, depth=0):
    d = q(ROWS_SQL.format(src=src, cat=cat, lo=lo, hi=hi))
    if "rows" in d and d["row_count"] < CAP:
        return d["rows"]
    if hi - lo <= 1 or depth > 30:
        raise RuntimeError(f"irreducible {lo}-{hi}")
    mid = lo + (hi - lo) // 2
    return pull(src, cat, lo, mid, depth + 1) + pull(src, cat, mid, hi, depth + 1)


# --- the grammar under test -------------------------------------------------
SCALE = {"k": 1e3, "m": 1e6, "b": 1e9, "bn": 1e9, "t": 1e12}
# "Above 410M", "above $68.25", "over 3.5%"
PRE_RE = re.compile(r"^\s*(?:above|over|at least)\s+\$?\s*"
                    r"(?P<val>\d[\d,]*(?:\.\d+)?)\s?(?P<unit>bn|[kmbt])?\s*%?\s*$", re.I)
# "7,175 or above", "$25,600 or higher", "3.0% or more"
POST_RE = re.compile(r"^\s*\$?\s*(?P<val>\d[\d,]*(?:\.\d+)?)\s?(?P<unit>bn|[kmbt])?\s*%?\s*"
                     r"or\s+(?:above|higher|more|greater)\s*$", re.I)
# the bare form the shipped module already knows
PLUS_RE = re.compile(r"^\s*\$?\s*(?P<val>\d[\d,]*(?:\.\d+)?)\s?(?P<unit>bn|[kmbt])?\s*\+\s*$", re.I)


def cumulative_rung(leg):
    for rx in (PRE_RE, POST_RE, PLUS_RE):
        m = rx.match(leg or "")
        if m:
            v = float(m.group("val").replace(",", ""))
            if m.group("unit"):
                v *= SCALE[m.group("unit").lower()]
            return v
    return None


def load_rows(src, cat):
    """The pull, cached on disk. Ten minutes of production load per cell, and
    every re-analysis after the first is free — which is the only reason the
    is_winner law below got measured at all."""
    cache = f"artifacts/cal-p134/rows-{src}-{cat}.json.gz"
    if os.path.exists(cache):
        print(f"  cache {cache}", file=sys.stderr)
        with gzip.open(cache, "rt") as fh:
            return json.load(fh)
    rng = q(f"SELECT MIN(id), MAX(id) FROM futures_markets WHERE source = '{src}'", 5)
    lo, hi = rng["rows"][0]
    rows = []
    e, width = lo, 1_000_000
    while e <= hi:
        nxt = min(e + width, hi + 1)
        rows += pull(src, cat, e, nxt)
        print(f"  chunk {e}-{nxt}: {len(rows)} rows", file=sys.stderr, flush=True)
        e = nxt
    with gzip.open(cache, "wt") as fh:
        json.dump(rows, fh)
    return rows


def main():
    src, cat = sys.argv[1], sys.argv[2]
    rows = load_rows(src, cat)

    mkts = collections.defaultdict(lambda: {"name": None, "type": None, "legs": []})
    for mid, mname, mtype, oname, price, win, rsrc in rows:
        m = mkts[mid]
        m["name"], m["type"] = mname, mtype
        m["legs"].append((oname, price, win, rsrc))

    census = collections.Counter()
    coherent, violating, flat_only = [], [], []
    for mid, m in mkts.items():
        census["markets"] += 1
        census["legs"] += len(m["legs"])
        parsed = [(cumulative_rung(o), p) for o, p, _, _ in m["legs"]]
        n_cum = sum(1 for v, _ in parsed if v is not None)
        if n_cum == 0:
            census["markets_no_cumulative_leg"] += 1
            continue
        if n_cum < len(parsed):
            census["markets_mixed_legs"] += 1
            continue
        census["markets_all_cumulative"] += 1
        vals = [v for v, _ in parsed]
        if len(set(vals)) != len(vals):
            census["markets_duplicate_rung"] += 1
            continue
        rungs = {v: float(p) for v, p in parsed if p is not None}
        if len(rungs) < 2:
            census["markets_untestable_one_priced_rung"] += 1
            continue
        census["markets_testable"] += 1
        census["testable_legs"] += len(m["legs"])
        order = sorted(rungs)
        vio = [(a, rungs[a], b, rungs[b]) for a, b in zip(order, order[1:])
               if rungs[b] > rungs[a]]
        flat = [(a, b) for a, b in zip(order, order[1:]) if rungs[b] == rungs[a]]
        census["pairs"] += len(order) - 1
        census["violating_pairs"] += len(vio)
        census["flat_pairs"] += len(flat)
        if vio:
            census["markets_violating"] += 1
            census["violating_legs"] += len(m["legs"])
            violating.append((mid, m["name"], m["type"], len(m["legs"]), vio))
        else:
            census["markets_coherent"] += 1
            coherent.append(mid)
            if flat:
                flat_only.append(mid)

    print(f"\n=== {src}/{cat} — OUTCOME-site cumulative ladder census (RAW CELL) ===")
    for k in ("markets", "legs", "markets_no_cumulative_leg", "markets_mixed_legs",
              "markets_all_cumulative", "markets_duplicate_rung",
              "markets_untestable_one_priced_rung", "markets_testable",
              "testable_legs", "markets_coherent", "markets_violating",
              "violating_legs", "pairs", "violating_pairs", "flat_pairs"):
        print(f"  {k:38s} {census[k]}")
    t = census["markets_testable"]
    if t:
        print(f"\n  COHERENT SHARE {census['markets_coherent'] / t * 100:.1f}% "
              f"of testable markets  <- the falsification test: brackets would "
              f"not be ordered")
    print(f"\n  worst violators:")
    violating.sort(key=lambda r: -max(hp - lp for _, lp, _, hp in r[4]))
    for mid, nm, mt, nlegs, vio in violating[:12]:
        a, ap, b, bp = max(vio, key=lambda v: v[3] - v[1])
        print(f"    {mid} [{mt}] {str(nm)[:62]!r}")
        print(f"        P(>= {a:g}) = {ap:.3f}  <  P(>= {b:g}) = {bp:.3f}   "
              f"({len(vio)} bad pairs, {nlegs} legs)")
    out = {"cell": f"{src}/{cat}", "census": dict(census),
           "violating_market_ids": [v[0] for v in violating],
           "coherent_market_ids": coherent}
    p = f"artifacts/cal-p134/outcome-ladder-{src}-{cat}.json"
    json.dump(out, open(p, "w"), indent=1)
    print(f"\n  wrote {p}")


if __name__ == "__main__":
    main()
