#!/usr/bin/env python3
"""LAT-P130 — prove the source-scoped golf candidate filter loses no rows.

Scoping ``external_id ILIKE 'golf_pga%'`` to ``source = 'odds_api'`` is not a
logical identity. It is an identity **on the population that exists**, and the
difference between those two claims is the whole risk of this change. So this
script measures rather than argues, in two independent ways:

**STRUCTURAL** — take the filter the route actually builds, strip the
``source = 'odds_api'`` conjuncts back out, and compare the compiled SQL
byte-for-byte to the legacy predicate. If they differ, the change did something
other than add a source scope, and no population check can cover that.

**POPULATION** — ask production for the rows the old filter matched and the new
one does not. That set is exactly ``source <> 'odds_api' AND (external_id
matches a golf sport key)``, plus any row with a NULL source. It must be empty.

The population half is run **per source**, not as one whole-table query. The
unchunked form is a seq scan that lands within a second or two of db-query's 25 s
ceiling, and a query that times out returns ``reason: statement_timeout`` — which
is a story about the harness, not a difference. This script therefore separates
CANNOT MEASURE from ROWS LOST and exits 2, not 1, when it could not measure. The
first draft of the LAT-P129 equivalent reported eight false differences by
scoring timeouts as diffs.

Usage:  source ~/.claude/.env && python3 scripts/lat_p130_verify_golf_equivalence.py
Exit:   0 = equivalent · 1 = rows would be lost · 2 = could not measure
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import or_, select  # noqa: E402
from sqlalchemy.sql import operators  # noqa: E402
from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList, Grouping  # noqa: E402

from app.config.league_configs import get_league_config  # noqa: E402
from app.models import FuturesMarket  # noqa: E402
from app.routes.playoffs import (  # noqa: E402
    _GOLF_SPORT_KEY_ID_SPACE_SOURCE,
    _build_golf_candidate_filters,
)

GOLF = get_league_config("golf")


# ---------------------------------------------------------------------------
# STRUCTURAL
# ---------------------------------------------------------------------------

def _strip_source_scope(clause):
    """Rebuild ``clause`` with every ``source = <id space>`` conjunct removed."""
    if isinstance(clause, Grouping):
        return _strip_source_scope(clause.element)
    if isinstance(clause, BooleanClauseList):
        kept = []
        for child in clause.clauses:
            if (
                isinstance(child, BinaryExpression)
                and child.operator is operators.eq
                and getattr(child.left, "key", None) == "source"
                and child.right.value == _GOLF_SPORT_KEY_ID_SPACE_SOURCE
            ):
                continue
            kept.append(_strip_source_scope(child))
        if len(kept) == 1:
            return kept[0]
        if clause.operator is operators.and_:
            from sqlalchemy import and_ as _and

            return _and(*kept)
        return or_(*kept)
    return clause


def _sql(clauses) -> str:
    stmt = select(FuturesMarket.id).where(*clauses)
    return " ".join(str(stmt.compile(compile_kwargs={"literal_binds": True})).split())


def _legacy_clauses(config):
    return [
        or_(
            *[FuturesMarket.external_id.ilike(f"{sk}%") for sk in config.sport_keys],
            FuturesMarket.llm_sport_category == "golf",
        ),
        FuturesMarket.status != "resolved",
        FuturesMarket.source != "datagolf",
    ]


def structural_check() -> bool:
    new = _build_golf_candidate_filters(GOLF)
    stripped = [_strip_source_scope(c) for c in new]
    got, want = _sql(stripped), _sql(_legacy_clauses(GOLF))
    print("STRUCTURAL")
    if got == want:
        print("  OK   the new filter is the legacy filter plus a source scope")
        return True
    print("  DIFF the new filter is not the legacy filter with a source scope added")
    print(f"    legacy:  {want}")
    print(f"    stripped:{got}")
    return False


# ---------------------------------------------------------------------------
# POPULATION
# ---------------------------------------------------------------------------

class CannotMeasure(Exception):
    pass


def _post(body: dict) -> dict:
    api, token = os.environ.get("BAINLUCK_API"), os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        raise CannotMeasure("BAINLUCK_API / ADMIN_TOKEN not set (source ~/.claude/.env)")
    proc = subprocess.run(
        [
            "curl", "-s", "-X", "POST",
            "-H", f"Authorization: Bearer {token}",
            "-H", "Content-Type: application/json",
            "-d", json.dumps(body),
            f"{api}/api/admin/db-query",
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise CannotMeasure(f"curl exit {proc.returncode}: {proc.stderr.strip()[:200]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise CannotMeasure(f"non-JSON response: {proc.stdout[:200]!r}")


def db_query(sql: str) -> list:
    payload = _post({"sql": sql, "limit": 500})
    if "rows" not in payload:
        detail = payload.get("detail", payload)
        reason = detail.get("reason") if isinstance(detail, dict) else str(detail)
        # statement_timeout, rate limits, 5xx — none of these are "no diff".
        raise CannotMeasure(f"query did not return rows: {reason}")
    if payload.get("truncated"):
        raise CannotMeasure("result truncated at the row cap — cannot claim a count")
    return payload["rows"]


def _leaf_scans(plan: dict) -> list:
    """Every scan node on ``futures_markets`` in an EXPLAIN ANALYZE plan."""
    found = []
    if "Relation Name" in plan or "Index Name" in plan:
        if not plan.get("Plans"):
            found.append(plan)
    for child in plan.get("Plans", []):
        found.extend(_leaf_scans(child))
    return found


def scan_counts(sql: str) -> tuple[int, int]:
    """Run ``sql`` through EXPLAIN ANALYZE; return (matched, examined).

    The row path has a hard 10 s ceiling and the polymarket probe measures 9.4 s
    — close enough that it times out on a busy database, and a timeout is not a
    zero. The explain path allows 25 s, so the counts are read off the plan
    instead. ``examined`` exists so the caller can reconcile against the table's
    real row count: a scan that stopped early would otherwise report "0 matches"
    exactly like a scan that finished and found none.
    """
    payload = _post({"sql": sql, "explain": True, "analyze": True, "timeout_ms": 25000})
    if not payload.get("plan"):
        detail = payload.get("detail", payload)
        reason = detail.get("reason") if isinstance(detail, dict) else str(detail)
        raise CannotMeasure(f"no plan returned: {reason}")
    scans = _leaf_scans(payload["plan"][0]["Plan"])
    if not scans:
        raise CannotMeasure("plan contained no scan node to read counts from")
    matched = examined = 0
    for node in scans:
        rows, loops = node.get("Actual Rows"), node.get("Actual Loops")
        if rows is None or loops is None:
            raise CannotMeasure("plan node carried no actual-row counts")
        removed = node.get("Rows Removed by Filter") or 0
        matched += rows * loops
        examined += (rows + removed) * loops
    return matched, examined


def _sport_key_predicate() -> str:
    return " OR ".join(
        f"external_id ILIKE '{sk}%'" for sk in GOLF.sport_keys
    )


# The sweep is per source, not whole-table: the whole-table probe measures
# ~21.6 s against db-query's 25 s ceiling, and a source RANGE (`source >= 'k'`)
# does not get an index range scan, so it times out too. `source = '...'` drives
# uq_futures_source_external and lands at 5–10 s.
#
# That needs a list of sources, and the census that produces one is itself
# marginal (4.7–9.9 s on a 10 s row path). So the list is discovered when it can
# be and falls back to the known set when it cannot — and the fallback is safe
# only because of the examined-row reconciliation below, which is what would
# catch a source missing from the list. Coverage is proven, not listed.
_KNOWN_SOURCES = ["datagolf", "kalshi", "odds_api", "polymarket"]


def _discover_sources() -> tuple[list[str], str]:
    try:
        rows = db_query(
            "SELECT source, count(*) AS n FROM futures_markets GROUP BY source"
        )
        return [r[0] for r in rows], "census"
    except CannotMeasure as exc:
        print(f"  census unavailable ({exc}); falling back to the known source set")
        return list(_KNOWN_SOURCES), "fallback"


def population_check() -> bool:
    print("POPULATION")
    keys = _sport_key_predicate()

    est_rows = db_query(
        "SELECT CAST(reltuples AS bigint) AS est FROM pg_class "
        "WHERE relname = 'futures_markets'"
    )
    estimate = est_rows[0][0]
    print(f"  futures_markets ~{estimate} rows (pg_class estimate)")

    n_null = db_query(
        "SELECT count(*) AS n FROM futures_markets WHERE source IS NULL"
    )[0][0]
    print(f"  NULL source rows: {n_null}")
    if n_null:
        print("  LOST a NULL source can never satisfy source = 'odds_api'")
        return False

    sources, how = _discover_sources()
    print(f"  sources ({how}): {', '.join(sources)}")

    lost_total = 0
    examined_total = 0
    for source in sources:
        lost, examined = scan_counts(
            "SELECT count(*) AS n FROM futures_markets "
            f"WHERE source = '{source}' AND ({keys})"
        )
        examined_total += examined
        if source == _GOLF_SPORT_KEY_ID_SPACE_SOURCE:
            # This IS the scoped id space — matches here are kept, not lost. It is
            # still swept so it counts toward coverage.
            print(f"  keep  {source}: {lost} matched, {examined} examined")
            continue
        lost_total += lost
        verdict = "OK  " if lost == 0 else "LOST"
        print(f"  {verdict}  {source}: {lost} matched, {examined} examined")

    # "It returned" is not "it worked". A scan that covered a fraction of the
    # table reports zero matches exactly like one that covered all of it, so the
    # coverage is reconciled rather than assumed.
    print(f"  examined {examined_total} of ~{estimate}")
    if examined_total < estimate * 0.95:
        raise CannotMeasure(
            f"the partitions examined {examined_total} rows against an estimate of "
            f"{estimate} — the sweep did not cover the population"
        )

    if lost_total:
        print(f"  LOST {lost_total} rows the legacy filter matched and the new one drops")
        return False
    print("  OK   no non-odds_api row carries a golf sport-key prefix")
    return True


def main() -> int:
    ok_struct = structural_check()
    print()
    try:
        ok_pop = population_check()
    except CannotMeasure as exc:
        print(f"  CANNOT MEASURE: {exc}")
        print("\nVERDICT  UNMEASURED — this is not a pass")
        return 2

    print()
    if ok_struct and ok_pop:
        print("VERDICT  EQUIVALENT on the current population")
        return 0
    print("VERDICT  NOT EQUIVALENT")
    return 1


if __name__ == "__main__":
    sys.exit(main())
