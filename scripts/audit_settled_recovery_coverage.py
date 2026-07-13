#!/usr/bin/env python3
"""Settled-recovery coverage audit (#174 Item 2).

The durable answer to the "hand-built net has holes" class (golf-class → combat-
class, same bug rediscovered): make settled-recovery coverage MEASURABLE per
category, and flag any category/series that reads ZERO because a hand list omitted
it — not because the source lacks it.

Two sections:
  A. Per-(category, source) recovery cells — from the DB via the admin db-query
     aggregate. total / resolved (settled-recovered, gotcha #33) / linked, with %.
     This is the scoreboard we hill-climb.
  B. Zero-by-omission scan — enumerate the SOURCE's own full listing (Kalshi
     `get_series`, Polymarket `get_tags`) and cross-reference the DB. A source
     series prefix with ZERO DB markets is a hole the recovery net never reached.
     Best-effort: needs the source API creds; degrades to a note if unavailable.

Usage:
    source ~/.claude/.env
    python3 scripts/audit_settled_recovery_coverage.py            # print table
    python3 scripts/audit_settled_recovery_coverage.py --no-source  # section A only
"""

import argparse
import json
import os
import subprocess
import sys


def _api() -> str:
    api = os.getenv("BAINLUCK_API")
    if not api:
        print("ERROR: set BAINLUCK_API (source ~/.claude/.env)", file=sys.stderr)
        sys.exit(2)
    return api.rstrip("/")


def _dbq(sql: str, limit: int = 500):
    """Run a read-only aggregate via the admin db-query endpoint. Returns rows."""
    api = _api()
    token = os.getenv("ADMIN_TOKEN", "")
    body = json.dumps({"sql": sql, "limit": limit})
    cmd = [
        "curl", "-s", "-X", "POST", f"{api}/api/admin/db-query",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Content-Type: application/json",
        "-d", body,
    ]
    try:
        out = subprocess.check_output(cmd, timeout=60)
        d = json.loads(out)
        return d.get("rows") or []
    except Exception as exc:  # noqa: BLE001
        print(f"  db-query failed: {exc}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Section A — per-category recovery cells (DB)
# ---------------------------------------------------------------------------

_CELL_SQL = """
SELECT
  coalesce(llm_sport_category, '(none)') AS category,
  source,
  count(*) AS total,
  count(*) FILTER (WHERE status = 'resolved') AS resolved,
  count(event_id) AS linked
FROM futures_markets
WHERE source IN ('kalshi', 'polymarket')
GROUP BY 1, 2
ORDER BY 1, 2
"""


def section_a() -> list[dict]:
    rows = _dbq(_CELL_SQL, limit=500)
    cells = []
    for r in rows:
        cat, source, total, resolved, linked = r[0], r[1], int(r[2]), int(r[3]), int(r[4])
        cells.append({
            "category": cat, "source": source, "total": total,
            "resolved": resolved, "linked": linked,
            "resolved_pct": round(100.0 * resolved / total, 1) if total else 0.0,
            "linked_pct": round(100.0 * linked / total, 1) if total else 0.0,
        })
    return cells


def print_section_a(cells: list[dict]):
    print("\n=== A. Per-category settled-recovery cells (DB) ===")
    print(f"{'category':<16}{'source':<12}{'total':>8}{'resolved':>10}{'res%':>7}{'linked':>8}{'link%':>7}")
    print("-" * 68)
    zero_resolved = []
    for c in cells:
        print(f"{c['category']:<16}{c['source']:<12}{c['total']:>8}"
              f"{c['resolved']:>10}{c['resolved_pct']:>6}%{c['linked']:>8}{c['linked_pct']:>6}%")
        if c["total"] >= 20 and c["resolved"] == 0:
            zero_resolved.append(c)
    if zero_resolved:
        print("\n  ⚠ categories with markets but ZERO resolved (settled-recovery not reaching them):")
        for c in zero_resolved:
            print(f"    - {c['category']}/{c['source']} ({c['total']} markets, 0 resolved)")


# ---------------------------------------------------------------------------
# Section B — zero-by-omission scan (SOURCE listing vs DB)
# ---------------------------------------------------------------------------

def _db_series_prefixes() -> set[str]:
    rows = _dbq(
        "SELECT DISTINCT regexp_replace(external_id, '-.*', '') "
        "FROM futures_markets WHERE source='kalshi' AND external_id ~ '^KX'",
        limit=5000,
    )
    return {r[0] for r in rows if r and r[0]}


def _db_poly_categories() -> set[str]:
    rows = _dbq(
        "SELECT DISTINCT coalesce(llm_sport_category,'(none)') "
        "FROM futures_markets WHERE source='polymarket'",
        limit=500,
    )
    return {r[0] for r in rows if r and r[0]}


def section_b() -> dict:
    """Best-effort: enumerate the source's own listings and flag holes."""
    import asyncio

    from app.utils.settled_recovery import extract_series_tickers, extract_tag_slugs

    out = {"kalshi_holes": None, "poly_tags": None, "note": None}

    async def _run():
        # Kalshi: source series with ZERO DB markets = never ingested (hole).
        try:
            from app.services.kalshi_api import KalshiAPIService

            svc = KalshiAPIService()
            rows, cursor = [], None
            for _ in range(12):
                page, cursor = await svc.get_series(cursor=cursor)
                rows.extend(page or [])
                if not cursor:
                    break
            source_series = extract_series_tickers(rows)
            db_prefixes = _db_series_prefixes()
            holes = sorted(s for s in source_series if s not in db_prefixes)
            out["kalshi_holes"] = {"source_total": len(source_series), "holes": holes}
        except Exception as exc:  # noqa: BLE001
            out["note"] = f"Kalshi source enumeration unavailable ({exc}); section A still valid."

        # Polymarket: source tags present vs DB categories (informational).
        try:
            from app.services.polymarket_api import PolymarketAPIService

            psvc = PolymarketAPIService()
            tags = extract_tag_slugs(await psvc.get_tags(limit=200))
            out["poly_tags"] = {"source_tags": len(tags)}
        except Exception:  # noqa: BLE001
            pass

    asyncio.run(_run())
    return out


def print_section_b(b: dict):
    print("\n=== B. Zero-by-omission scan (source listing vs DB) ===")
    if b.get("note"):
        print(f"  (degraded) {b['note']}")
    kh = b.get("kalshi_holes")
    if kh is not None:
        holes = kh["holes"]
        print(f"  Kalshi: {kh['source_total']} series at source; "
              f"{len(holes)} with ZERO DB markets (never-ingested holes).")
        if holes:
            print("  Holes (first 40):")
            for h in holes[:40]:
                print(f"    - {h}")
            if len(holes) > 40:
                print(f"    … +{len(holes) - 40} more")
        else:
            print("  ✅ No never-ingested Kalshi series — no zero-by-omission.")
    if b.get("poly_tags"):
        print(f"  Polymarket: {b['poly_tags']['source_tags']} non-crypto tags at source.")


def main():
    p = argparse.ArgumentParser(description="Settled-recovery coverage audit (#174)")
    p.add_argument("--no-source", action="store_true",
                   help="section A only (skip source-listing enumeration)")
    args = p.parse_args()

    cells = section_a()
    print_section_a(cells)
    if not args.no_source:
        # importing app.* requires backend on the path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
        print_section_b(section_b())


if __name__ == "__main__":
    main()
