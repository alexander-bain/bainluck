"""A1 (#173/#1024) — entity-registry duplicate census.

The A1 identity graph creates one ``entities`` row per real-world participant, but
the person dedup anchor is ``person:<sport_key>:<norm>`` (``entity_registry._person_ref``)
and the seeds feed it TWO different sport_key sources — ``Sport.key`` from events
and ``llm_sport_category`` from futures fields. Tennis, whose events span a distinct
sport key per tournament edition, therefore multiplies: one entity row per
sport_key for the SAME player (e.g. "Alexandra Eala" ×15 across 15 sport_keys).
Teams inherit their own dups from the legacy ``teams`` table (the registry keys on
``teams.id``, so two team rows for one club → two team entities). There is no DB
uniqueness on ``entities`` and no committed census — so the dup count was unmeasured.

This is the missing MEASUREMENT tool. It quantifies the dup population and, for the
fix-design decision, splits it into:

  * SAFE-to-merge — all copies of a ``(kind, canonical_name)`` sit in ONE sport
    family (same first sport_key segment, e.g. all ``tennis*``). Merging these into
    one entity with sport_key-scoped aliases collapses no distinct real person.
  * RISKY-to-merge — copies span MORE than one sport family, i.e. a possible
    cross-sport homonym ("John Smith" the golfer vs. the footballer). The
    ``person:<sport_key>:<norm>`` key exists precisely to keep those apart, so a
    blind ``(kind, norm)`` merge would fuse two distinct people. These need a
    per-family or category-gated merge rule, not a global collapse.

The engine is SHADOW-MODE today (nothing live reads ``entities``), so the dups are
cosmetic — but a canonicalization pass is a prerequisite before any per-link-type
cutover, and this census is what makes that fix measurable (before/after).

Read-only: uses the admin ``/api/admin/db-query`` endpoint (needs ``ADMIN_TOKEN`` +
``BAINLUCK_API``; ``source ~/.claude/.env``). Writes nothing.

Usage:
    source ~/.claude/.env && python3 scripts/audit_entity_dups.py
    python3 scripts/audit_entity_dups.py --top 25 --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")
TOKEN = os.environ.get("ADMIN_TOKEN", "")


def db_query(sql: str, limit: int = 1000) -> list[dict]:
    """Run a read-only SQL query via the admin endpoint; return list-of-dicts."""
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    req = Request(
        f"{API}/api/admin/db-query",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as resp:
            payload = json.load(resp)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"db-query {exc.code}: {detail}\nSQL: {sql[:200]}") from None
    cols = payload["columns"]
    return [dict(zip(cols, row)) for row in payload["rows"]]


# The dedup anchor is bucketed by sport_key; the "family" is the first
# underscore-delimited segment of the sport_key (tennis_atp, tennis_wta,
# tennis_wimbledon → "tennis"). Copies that all share a family are same-sport
# edition dups (safe to merge); copies spanning families are homonym-risk.
def _family_expr(col: str) -> str:
    return f"split_part(lower(coalesce({col}, '')), '_', 1)"


def census() -> dict:
    out: dict = {}

    out["by_kind"] = db_query(
        "SELECT kind, count(*) AS rows, count(DISTINCT canonical_name) AS names, "
        "count(*) - count(DISTINCT canonical_name) AS surplus_rows "
        "FROM entities GROUP BY 1 ORDER BY 2 DESC",
        limit=50,
    )

    out["multiplicity"] = db_query(
        "SELECT n_copies, count(*) AS names FROM ("
        "  SELECT kind, canonical_name, count(*) AS n_copies FROM entities "
        "  WHERE kind IN ('person','team') GROUP BY 1,2"
        ") t WHERE n_copies > 1 GROUP BY 1 ORDER BY 1 DESC",
        limit=100,
    )

    # SAFE vs RISKY split: a (kind, canonical_name) group is safe to merge when
    # every copy is in the same sport family.
    fam = _family_expr("sport_key")
    out["merge_safety"] = db_query(
        "SELECT kind, "
        "  count(*) FILTER (WHERE families = 1) AS safe_names, "
        "  sum(copies) FILTER (WHERE families = 1) - count(*) FILTER (WHERE families = 1) AS safe_surplus_rows, "
        "  count(*) FILTER (WHERE families > 1) AS risky_names, "
        "  sum(copies) FILTER (WHERE families > 1) - count(*) FILTER (WHERE families > 1) AS risky_surplus_rows "
        "FROM ("
        f"  SELECT kind, canonical_name, count(*) AS copies, count(DISTINCT {fam}) AS families "
        "  FROM entities WHERE kind IN ('person','team') GROUP BY 1,2 HAVING count(*) > 1"
        ") g GROUP BY kind ORDER BY kind",
        limit=50,
    )

    # cross-kind collision: the same normalized name existing as BOTH person and
    # team (tennis players seeded as teams AND persons).
    out["person_and_team"] = db_query(
        "SELECT count(*) AS names_both FROM ("
        "  SELECT canonical_name FROM entities WHERE kind IN ('person','team') "
        "  GROUP BY canonical_name HAVING count(DISTINCT kind) > 1"
        ") x",
        limit=5,
    )

    return out


def top_offenders(kind: str, top: int) -> list[dict]:
    fam = _family_expr("sport_key")
    return db_query(
        f"SELECT canonical_name, count(*) AS copies, count(DISTINCT sport_key) AS sport_keys, "
        f"count(DISTINCT {fam}) AS families "
        f"FROM entities WHERE kind = '{kind}' GROUP BY 1 HAVING count(*) > 1 "
        f"ORDER BY 2 DESC, 1 LIMIT {int(top)}",
        limit=int(top),
    )


def _fmt_rows(rows: list[dict]) -> str:
    if not rows:
        return "  (none)"
    cols = list(rows[0].keys())
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    head = "  " + "  ".join(c.ljust(widths[c]) for c in cols)
    body = "\n".join(
        "  " + "  ".join(str(r[c]).ljust(widths[c]) for c in cols) for r in rows
    )
    return head + "\n" + body


def main() -> int:
    parser = argparse.ArgumentParser(description="A1 entity duplicate census (#173)")
    parser.add_argument("--top", type=int, default=15, help="top offenders per kind")
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    args = parser.parse_args()

    if not TOKEN:
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    data = census()
    data["top_persons"] = top_offenders("person", args.top)
    data["top_teams"] = top_offenders("team", args.top)

    if args.json:
        print(json.dumps(data, indent=2, default=str))
        return 0

    print("=== A1 entity duplicate census (#173/#1024) ===\n")
    print("Rows by kind (surplus_rows = rows - distinct names = dup inflation):")
    print(_fmt_rows(data["by_kind"]))
    print("\nDup multiplicity (person+team, names sharing N copies):")
    print(_fmt_rows(data["multiplicity"]))
    print("\nMerge safety split (same-family copies are safe; cross-family are homonym-risk):")
    print(_fmt_rows(data["merge_safety"]))
    both = data["person_and_team"][0]["names_both"] if data["person_and_team"] else 0
    print(f"\nCross-kind collisions (name exists as BOTH person and team): {both}")
    print(f"\nTop {args.top} duplicated persons:")
    print(_fmt_rows(data["top_persons"]))
    print(f"\nTop {args.top} duplicated teams:")
    print(_fmt_rows(data["top_teams"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
