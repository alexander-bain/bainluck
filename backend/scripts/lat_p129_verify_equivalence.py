#!/usr/bin/env python3
"""LAT-P129 — prove the source-scoped candidate filter selects the SAME markets.

For every league config this builds two predicates:

* **OLD** — a faithful transcription of ``get_playoff_grid``'s candidate filter
  as it stands on master (flat ``OR`` of bare ``external_id`` prefixes).
* **NEW** — whatever ``_build_grid_market_filters`` emits today.

and asks production for the SYMMETRIC DIFFERENCE:
``WHERE (OLD) IS DISTINCT FROM (NEW)``. Zero rows on both filters, for every
league, is the equivalence proof — not a count match, which two different sets
of the same size would also pass.

The count is read from ``EXPLAIN (ANALYZE)``'s actual rows rather than the row
path, because the OLD predicate is a ~20 s sequential scan over 911,217 rows and
db-query's row path has a hard 10 s timeout.

Run from ``backend/``:  ``python3 scripts/lat_p129_verify_equivalence.py``
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import and_, or_  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402

from app.config.league_configs import (  # noqa: E402
    get_all_league_slugs,
    get_league_config,
)
from app.models import FuturesMarket  # noqa: E402
from app.routes.playoffs import (  # noqa: E402
    _build_grid_market_filters,
    _league_pattern_to_ilike,
)

API = os.environ["BAINLUCK_API"]
TOKEN = os.environ["ADMIN_TOKEN"]


def old_filters(config):
    """Master's candidate filter, transcribed verbatim (pre-LAT-P129)."""
    sport_conditions = []
    for sk in config.sport_keys:
        sport_conditions.append(FuturesMarket.external_id.ilike(f"{sk}%"))
    if config.external_id_prefixes:
        for pfx in config.external_id_prefixes:
            sport_conditions.append(FuturesMarket.external_id.ilike(f"{pfx}%"))

    category_conditions = []
    if config.league_name_patterns:
        for pattern_str in config.league_name_patterns:
            sql_pattern = _league_pattern_to_ilike(pattern_str)
            if sql_pattern:
                category_conditions.append(
                    and_(
                        FuturesMarket.llm_sport_category == config.sport_category,
                        FuturesMarket.name.ilike(f"%{sql_pattern}%"),
                    )
                )
    if not category_conditions:
        category_conditions.append(
            FuturesMarket.llm_sport_category == config.sport_category
        )

    ticker_filter = or_(*sport_conditions) if sport_conditions else None
    category_filter = or_(*category_conditions) if category_conditions else None
    status_conditions = []
    if ticker_filter is not None:
        status_conditions.append(
            and_(ticker_filter, FuturesMarket.status.in_(("open", "closed", "resolved")))
        )
    if category_filter is not None:
        status_conditions.append(
            and_(category_filter, FuturesMarket.status.in_(("open", "closed")))
        )
    with_status = (
        or_(*status_conditions)
        if status_conditions
        else FuturesMarket.status.in_(("open", "closed"))
    )
    bare = (
        or_(*sport_conditions, *category_conditions)
        if sport_conditions or category_conditions
        else None
    )
    return with_status, bare


def sql_of(clause) -> str:
    return str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def explain_rows(sql: str):
    """Return (actual_rows, exec_ms) for a SELECT, via EXPLAIN ANALYZE."""
    body = json.dumps(
        {"sql": sql, "explain": True, "analyze": True, "timeout_ms": 25000}
    )
    out = subprocess.run(
        [
            "curl", "-s", "-X", "POST",
            "-H", f"Authorization: Bearer {TOKEN}",
            "-H", "Content-Type: application/json",
            "-d", body,
            f"{API}/api/admin/db-query",
        ],
        capture_output=True, text=True,
    ).stdout
    try:
        payload = json.loads(out)
    except ValueError:
        return None, f"unparseable: {out[:160]}"
    if "plan" not in payload:
        return None, str(payload.get("detail", payload))[:160]
    plan = payload["plan"][0]
    return plan["Plan"]["Actual Rows"], plan.get("Execution Time")


def difference_predicate(config) -> str:
    """SQL for exactly the rows OLD selects and NEW does not.

    ``NEW`` only ever ADDS a ``source =`` conjunct to ``OLD``'s external-id
    branches — the category branch, the status split and the ILIKE bodies are
    byte-identical — so ``NEW`` implies ``OLD`` and the symmetric difference
    collapses to ``OLD AND NOT NEW``: rows whose ``external_id`` matches one of
    this league's prefixes while carrying some OTHER source.

    Computing that set directly instead of ``OLD IS DISTINCT FROM NEW`` matters
    for a boring reason: the XOR form evaluates both predicates for all 911,217
    rows and blows db-query's 25 s ceiling on the eight biggest leagues. A
    timeout is a story about the harness, not a difference, and must never be
    read as one.
    """
    return " OR ".join(difference_terms(config)) or "false"


def difference_terms(config) -> list:
    """One ``OLD AND NOT NEW`` term per configured prefix.

    Kept separable so a league with enough prefixes to blow the 25 s ceiling
    (golf has five sport keys) can be proven one term at a time instead of
    being reported as an unknown.
    """
    terms = []
    for sport_key in config.sport_keys:
        terms.append(f"(external_id ILIKE '{sport_key}%' AND source <> 'odds_api')")
    for prefix in config.external_id_prefixes or []:
        terms.append(f"(external_id ILIKE '{prefix}%' AND source <> 'kalshi')")
    return terms


def main() -> int:
    failures, harness = [], []
    print(f"{'league':<24}{'OLD-minus-NEW rows':>20}{'exec_ms':>10}   verdict")
    print("-" * 72)
    for slug in sorted(get_all_league_slugs()):
        config = get_league_config(slug)

        # Structural check first: NEW must differ from OLD only by source terms.
        old_ws, _ = old_filters(config)
        new_ws, _ = _build_grid_market_filters(config)
        stripped = sql_of(new_ws)
        for source in ("odds_api", "kalshi"):
            stripped = stripped.replace(
                f"futures_markets.source = '{source}' AND ", ""
            )
        if " ".join(stripped.split()) != " ".join(sql_of(old_ws).split()):
            failures.append((slug, "structural: NEW differs from OLD beyond source"))
            print(f"{slug:<24}{'-':>20}{'-':>10}   STRUCTURAL DIFFERENCE")
            continue

        sql = (
            "SELECT id FROM futures_markets WHERE "
            f"({difference_predicate(config)})"
        )
        rows, info = explain_rows(sql)
        if rows is None:
            # Too many prefixes for one 25 s scan — prove them one at a time.
            chunk_rows, chunk_ms, chunk_fail = 0, 0.0, None
            for term in difference_terms(config):
                r, i = explain_rows(
                    f"SELECT id FROM futures_markets WHERE {term}"
                )
                if r is None:
                    chunk_fail = i
                    break
                chunk_rows += r
                chunk_ms += i
            if chunk_fail is not None:
                harness.append((slug, chunk_fail))
                print(f"{slug:<24}{'-':>20}{'-':>10}   HARNESS: {str(chunk_fail)[:30]}")
                continue
            rows, info = chunk_rows, chunk_ms
            print(f"{slug:<24}{rows:>20}{info:>10.0f}   "
                  f"{'IDENTICAL (chunked)' if rows == 0 else 'ROWS LOST'}")
            if rows != 0:
                failures.append((slug, f"{rows} rows lost"))
            continue
        ok = rows == 0
        if not ok:
            failures.append((slug, f"{rows} rows lost"))
        print(
            f"{slug:<24}{rows:>20}{info:>10.0f}   "
            f"{'IDENTICAL' if ok else 'ROWS LOST'}"
        )

    print("-" * 72)
    if harness:
        print(f"HARNESS FAILURES (not results): {[h[0] for h in harness]}")
    if failures:
        print(f"FAIL — {len(failures)} league(s): {failures}")
        return 1
    if harness:
        return 2
    print(
        f"PASS — all {len(get_all_league_slugs())} leagues: NEW differs from OLD "
        f"only by source scoping, and that scoping loses ZERO rows"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
