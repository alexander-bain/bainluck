"""lane1-Q478 census — how many `quantity` markets does the detail page ladder?

TOP-PRODUCT-DEFECTS item 10. Before this queue the ONLY route to `QuantityGroup`
on `app/futures/[id]/page.tsx` was the backend's `threshold_groups`, built by
`detect_threshold_groups()` -> `extract_threshold()`, which is numeric-only. Any
`quantity` market whose rungs carry no parseable numeral produced `{}` and fell
through to the generic ranked table (rank badges + initial avatars).

This replays the REAL production population through the REAL predicate, so the
before/after is measured rather than argued.

    python3 scripts/census_quantity_ladder_q478.py

Reads production via the admin db-query endpoint; needs BAINLUCK_API + ADMIN_TOKEN.
"""

import ast
import json
import os
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.market_grouping import detect_threshold_groups  # noqa: E402

API = os.environ["BAINLUCK_API"]
TOKEN = os.environ["ADMIN_TOKEN"]
CHUNKS = 24


def query(sql: str, limit: int = 1000) -> list[dict]:
    body = json.dumps({"sql": sql, "limit": limit})
    out = subprocess.run(
        [
            "curl", "-s", "-X", "POST",
            "-H", f"Authorization: Bearer {TOKEN}",
            "-H", "Content-Type: application/json",
            "-d", body, f"{API}/api/admin/db-query",
        ],
        capture_output=True, text=True,
    ).stdout
    payload = json.loads(out)
    if "rows" not in payload:
        raise SystemExit(f"db-query refused: {out[:400]}")
    if payload.get("truncated"):
        print("  !! TRUNCATED chunk — raise CHUNKS", file=sys.stderr)
    rows = [dict(zip(payload["columns"], row)) for row in payload["rows"]]
    for row in rows:
        row["outcome_names"] = _decode_array(row.get("outcome_names"))
    return rows


def _decode_array(value):
    """`array_agg` comes back as a PYTHON-REPR STRING, not a JSON list.

    Measured: `{"rows": [[109349, "['Before 2027', 'Before October', ...]"]]}`.
    Iterating it yields CHARACTERS, and a first cut of this census did exactly
    that: `extract_threshold` parsed 0 of 36,262 "outcomes" because every one of
    them was a 1-character fragment, which reads as a dramatic finding and is an
    artifact. Same class as the JSONB-as-repr gotcha on this endpoint.
    """
    if value is None or isinstance(value, list):
        return value or []
    parsed = ast.literal_eval(value)
    return [x for x in parsed if x is not None]


def main() -> None:
    markets: list[dict] = []
    for i in range(CHUNKS):
        markets.extend(query(
            "SELECT m.id, m.group_id, m.name, m.mutually_exclusive, "
            "       array_agg(o.name ORDER BY o.id) AS outcome_names "
            "FROM futures_markets m JOIN futures_outcomes o ON o.market_id = m.id "
            "WHERE m.market_type = 'quantity' AND m.status = 'open' "
            f"  AND (abs(hashtext(m.id::text)) % {CHUNKS}) = {i} "
            "GROUP BY m.id, m.group_id, m.name, m.mutually_exclusive"
        ))
        print(f"  chunk {i + 1}/{CHUNKS}: {len(markets)} so far", file=sys.stderr)

    # FIDELITY: the page fetches `/api/futures/groups/{group_id}` and the route
    # runs detect_threshold_groups over EVERY market in that group, not just this
    # one. Replaying per-market would understate the "before" for any market with
    # siblings, so group first and replay the group exactly as the route does.
    # A null group_id means the page never fetches at all -> no ladder, ever.
    by_group: dict[str, list[dict]] = {}
    ungrouped: list[dict] = []
    for m in markets:
        if m["group_id"]:
            by_group.setdefault(m["group_id"], []).append(m)
        else:
            ungrouped.append(m)

    # Groups can also contain non-quantity siblings; pull their outcomes too.
    sibling_names: dict[str, list[dict]] = {}
    gids = list(by_group)
    for i in range(0, len(gids), 200):
        batch = gids[i:i + 200]
        literal = ",".join("'" + g.replace("'", "''") + "'" for g in batch)
        for row in query(
            "SELECT m.group_id, m.id, m.name, "
            "       array_agg(o.name ORDER BY o.id) AS outcome_names "
            "FROM futures_markets m JOIN futures_outcomes o ON o.market_id = m.id "
            f"WHERE m.group_id IN ({literal}) "
            "GROUP BY m.group_id, m.id, m.name"
        ):
            sibling_names.setdefault(row["group_id"], []).append(row)
        print(f"  siblings {min(i + 200, len(gids))}/{len(gids)}", file=sys.stderr)

    def group_ladders(rows: list[dict]) -> bool:
        """Exactly the route's computation, then the page's `>= 2` filter."""
        all_outcomes = []
        for r in rows:
            for j, n in enumerate(r["outcome_names"] or []):
                all_outcomes.append({
                    "id": j, "name": n, "market_id": r["id"],
                    "group_id": r["group_id"], "market_name": r["name"],
                })
        groups = detect_threshold_groups(all_outcomes)
        return any(len(v) >= 2 for v in groups.values())

    grouped_draws = {g: group_ladders(sibling_names.get(g, [])) for g in by_group}

    laddered_before = 0
    laddered_after = 0
    too_few = 0
    order = Counter()

    for m in markets:
        gid = m["group_id"]
        before = bool(gid) and grouped_draws.get(gid, False)
        if before:
            laddered_before += 1
            laddered_after += 1
            continue
        if len(m["outcome_names"] or []) >= 2:
            laddered_after += 1
            order["cumulative" if m["mutually_exclusive"] is False else "served"] += 1
        else:
            too_few += 1

    total = len(markets)
    print()
    print(f"open `quantity` markets with outcomes : {total}")
    print(f"  laddered BEFORE (threshold_groups)  : {laddered_before}"
          f"  ({laddered_before / total:.1%})")
    print(f"  laddered AFTER  (+ own outcomes)    : {laddered_after}"
          f"  ({laddered_after / total:.1%})")
    print(f"  newly laddered by this queue        : {laddered_after - laddered_before}")
    print(f"  still not laddered (<2 outcomes)    : {too_few}")
    print(f"  new ladders by ordering rule        : {dict(order)}")


if __name__ == "__main__":
    main()
