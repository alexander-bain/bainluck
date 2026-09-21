"""Run the REAL classify_fabricated_book over real production rows, before vs after.

Not a re-implementation: it imports the shipped function and calls it with the same
(probability, yes_bid, yes_ask) triples routes/feed.py builds.
"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from app.utils.feed_market_quality import classify_fabricated_book  # noqa: E402

SQL = """
SELECT o.market_id, m.name AS mname, m.source, m.group_type, m.mutually_exclusive AS me,
       o.name, o.current_probability AS p, o.current_yes_bid AS b, o.current_yes_ask AS a
FROM futures_outcomes o JOIN futures_markets m ON m.id=o.market_id
WHERE m.status='open' AND o.last_updated > NOW() - INTERVAL '2 days'
  AND o.current_probability IS NOT NULL
  AND o.market_id IN (
    SELECT market_id FROM (
      SELECT o2.market_id,
             MAX(o2.current_probability) FILTER (WHERE o2.current_yes_bid > 0.05) AS best_bid_p,
             SUM(o2.current_probability) AS psum
      FROM futures_outcomes o2 JOIN futures_markets m2 ON m2.id=o2.market_id
      WHERE m2.status='open' AND m2.mutually_exclusive
            AND o2.last_updated > NOW() - INTERVAL '2 days'
            AND o2.current_probability IS NOT NULL
      GROUP BY o2.market_id
    ) q WHERE psum > 1.25 AND best_bid_p IS NOT NULL
  )
ORDER BY o.market_id, o.current_probability DESC NULLS LAST
"""
CONTROLS = """
SELECT o.market_id, m.name AS mname, m.source, m.group_type, m.mutually_exclusive AS me,
       o.name, o.current_probability AS p, o.current_yes_bid AS b, o.current_yes_ask AS a
FROM futures_outcomes o JOIN futures_markets m ON m.id=o.market_id
WHERE o.market_id IN (12230832, 12230830, 61756198, 61791815, 60473187, 56775560, 60473053, 61696689)
  AND o.current_probability IS NOT NULL
ORDER BY o.market_id, o.current_probability DESC NULLS LAST
"""

def run(sql, limit):
    body = json.dumps({"sql": " ".join(sql.split()), "limit": limit})
    out = subprocess.run(
        ["curl", "-s", "-X", "POST", "-H", f"Authorization: Bearer {os.environ['ADMIN_TOKEN']}",
         "-H", "Content-Type: application/json", "-d", body,
         f"{os.environ['BAINLUCK_API']}/api/admin/db-query"], capture_output=True, text=True).stdout
    d = json.loads(out)
    if "rows" not in d:
        print(out[:600]); sys.exit(1)
    # `truncated` is True whenever row_count == limit, which is not the same as
    # "rows were dropped" — the cap is only real if the batch filled it exactly.
    if d.get("row_count") >= limit:
        print(f"!! HIT THE CAP at limit={limit} — batch is too big"); sys.exit(1)
    return [dict(zip(d["columns"], r)) for r in d["rows"]]


def group(rows):
    by = {}
    for r in rows:
        by.setdefault(r["market_id"], []).append(r)
    return by


def judge(legs):
    triples = [
        (float(x["p"]), None if x["b"] is None else float(x["b"]),
         None if x["a"] is None else float(x["a"])) for x in legs
    ]
    is_excl = legs[0]["group_type"] == "negrisk"
    me = bool(legs[0]["me"])
    before = classify_fabricated_book(triples, is_exclusive=is_excl)
    after = classify_fabricated_book(
        triples, is_exclusive=is_excl, field_is_mutually_exclusive=me)
    return before, after


def leader(legs, keep):
    kept = [x for x, k in zip(legs, keep) if k]
    return kept[0]["name"] if kept else "(none)"


def report(by, label):
    changed = dropped = 0
    lines = []
    for mid, legs in sorted(by.items()):
        (kb, db), (ka, da) = judge(legs)
        if kb == ka and db == da:
            continue
        lb, la = leader(legs, kb), leader(legs, ka)
        if da and not db:
            dropped += 1
        if lb != la:
            changed += 1
        lines.append(
            f"{mid:>9} {legs[0]['source'][:10]:11}{str(legs[0]['mname'])[:40]:42}"
            f" hid {sum(kb)-sum(ka):>2} more | {str(lb)[:24]:25}-> {str(la)[:24]:25}"
            f" | card dropped: {db}->{da}")
    print(f"=== {label}: {len(by)} fields read, {len(lines)} changed, "
          f"{changed} leader changes, {dropped} cards newly dropped")
    for line in lines:
        print(line)
    return lines


IDS = """
SELECT market_id, legs FROM (
  SELECT o2.market_id, COUNT(*) AS legs,
         MAX(o2.current_probability) FILTER (WHERE o2.current_yes_bid > 0.05) AS best_bid_p,
         SUM(o2.current_probability) AS psum
  FROM futures_outcomes o2 JOIN futures_markets m2 ON m2.id=o2.market_id
  WHERE m2.status='open' AND m2.mutually_exclusive
        AND o2.last_updated > NOW() - INTERVAL '2 days'
        AND o2.current_probability IS NOT NULL
  GROUP BY o2.market_id
) q WHERE psum > 1.25 AND best_bid_p IS NOT NULL ORDER BY market_id
"""

ROWS_FOR = """
SELECT o.market_id, m.name AS mname, m.source, m.group_type, m.mutually_exclusive AS me,
       o.name, o.current_probability AS p, o.current_yes_bid AS b, o.current_yes_ask AS a
FROM futures_outcomes o JOIN futures_markets m ON m.id=o.market_id
WHERE o.market_id IN (%s) AND o.current_probability IS NOT NULL
ORDER BY o.market_id, o.current_probability DESC NULLS LAST
"""

if __name__ == "__main__":
    cand = run(IDS, 400)
    print(f"{len(cand)} candidate fields")
    rows = []
    batch, used = [], 0
    def flush():
        global batch, used
        if batch:
            rows.extend(run(ROWS_FOR % ",".join(str(x) for x in batch), 500))
            batch, used = [], 0
    for r in cand:
        n = int(r["legs"])
        if used + n > 400:
            flush()
        batch.append(r["market_id"]); used += n
    flush()
    report(group(rows), "candidate fields (exclusive, sum>1.25, a bid-backed leg)")
    print()
    report(group(run(CONTROLS, 500)), "controls (ladders, O/U pairs, coherent fields)")
