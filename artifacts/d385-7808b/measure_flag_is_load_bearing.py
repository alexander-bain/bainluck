"""What does `field_is_mutually_exclusive` actually BUY? Measured, not assumed.

Half two declines on three guards. Guard 1 is the venue's own exclusivity flag,
and its docstring claims it is what keeps a cumulative ladder off the clause.
Two things made me doubt that claim rather than ship it:

  * on every cumulative specimen in the fixture file (SpaceX sum 8.00, NVIDIA
    sum 3.31) flipping the flag ON changes NOTHING — guard 3, the repair test,
    is what declines them, because their remainders cannot land in the band; and
  * the Buffalo ladder the docstring names never reaches a Discover card at all:
    `classify_market_quality` reads its rungs as `numeric_outcome_ladder` and the
    feed suppresses that family (the audit target is `ladder/bucket-rate@20=0`).

So: over the NON-exclusive fields on production, how many would the clause hide
a leg from if the flag were ignored and only guards 2 and 3 stood? Zero means
guard 1 is belt-and-braces and the docstring must stop claiming it is the
defence. Non-zero names the fields it protects, and they go in the guard test.

Reads the same population as `verify_on_production_rows.py` with one predicate
inverted, and calls the SHIPPED function both ways.
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from app.utils.feed_market_quality import classify_fabricated_book  # noqa: E402

IDS = """
SELECT market_id, legs FROM (
  SELECT o2.market_id, COUNT(*) AS legs,
         MAX(o2.current_probability) FILTER (WHERE o2.current_yes_bid > 0.05) AS best_bid_p,
         SUM(o2.current_probability) AS psum
  FROM futures_outcomes o2 JOIN futures_markets m2 ON m2.id=o2.market_id
  WHERE m2.status='open' AND NOT m2.mutually_exclusive
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


def run(sql, limit):
    body = json.dumps({"sql": " ".join(sql.split()), "limit": limit})
    out = subprocess.run(
        [
            "curl", "-s", "-X", "POST",
            "-H", f"Authorization: Bearer {os.environ['ADMIN_TOKEN']}",
            "-H", "Content-Type: application/json", "-d", body,
            f"{os.environ['BAINLUCK_API']}/api/admin/db-query",
        ],
        capture_output=True, text=True,
    ).stdout
    d = json.loads(out)
    if "rows" not in d:
        print(out[:600])
        sys.exit(1)
    if d.get("row_count", 0) >= limit:
        print(f"!! HIT THE CAP at limit={limit}")
        sys.exit(1)
    return [dict(zip(d["columns"], r)) for r in d["rows"]]


def main():
    cand = run(IDS, 900)
    print(f"{len(cand)} NON-exclusive candidate fields (sum>1.25, a bid-backed leg)")

    rows, batch, used = [], [], 0

    def flush():
        nonlocal batch, used
        if batch:
            rows.extend(run(ROWS_FOR % ",".join(str(x) for x in batch), 900))
            batch, used = [], 0

    for r in cand:
        n = int(r["legs"])
        if used + n > 700:
            flush()
        batch.append(r["market_id"])
        used += n
    flush()

    by = {}
    for r in rows:
        by.setdefault(r["market_id"], []).append(r)

    protected = []
    for mid, legs in sorted(by.items()):
        triples = [
            (
                float(x["p"]),
                None if x["b"] is None else float(x["b"]),
                None if x["a"] is None else float(x["a"]),
            )
            for x in legs
        ]
        is_excl = legs[0]["group_type"] == "negrisk"
        assert not legs[0]["me"], f"{mid} is exclusive — wrong population"
        shipped = classify_fabricated_book(
            triples, is_exclusive=is_excl, field_is_mutually_exclusive=False
        )
        no_guard1 = classify_fabricated_book(
            triples, is_exclusive=is_excl, field_is_mutually_exclusive=True
        )
        if shipped == no_guard1:
            continue
        kept_ship = [x["name"] for x, k in zip(legs, shipped[0]) if k]
        kept_none = [x["name"] for x, k in zip(legs, no_guard1[0]) if k]
        protected.append((mid, legs, shipped, no_guard1, kept_ship, kept_none))
        print(
            f"\n{mid} {legs[0]['source']} {str(legs[0]['mname'])[:60]!r}"
            f"  legs={len(legs)} sum={sum(t[0] for t in triples):.2f}"
        )
        print(f"   shipped (guard 1 on) : {sum(shipped[0])} kept, drop_card={shipped[1]}")
        print(f"   guard 1 IGNORED      : {sum(no_guard1[0])} kept, drop_card={no_guard1[1]}")
        print(f"   leader {kept_ship[0] if kept_ship else '(none)'!r}"
              f" -> {kept_none[0] if kept_none else '(none)'!r}")
        for x, a, b in zip(legs, shipped[0], no_guard1[0]):
            if a != b:
                print(f"     guard 1 alone keeps {x['name']!r} p={x['p']} bid={x['b']} ask={x['a']}")

    print(
        f"\n=== {len(by)} non-exclusive fields read, "
        f"{len(protected)} where guard 1 is the ONLY thing declining the clause"
    )


if __name__ == "__main__":
    main()
