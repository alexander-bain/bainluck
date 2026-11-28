#!/usr/bin/env python3
"""Draw and verify the sealed (300) and development (200) CU eval sets (#13898).

Authorization notice: every draw or refresh reads production tables and requires
Alex's explicit yes. Decision 453 authorized the initial Nov 27 draw only, and
decision 457 authorized the narrow rank + league key re-freeze over the same
500 markets. Do NOT run any draw against production without an explicit yes in
the active window; pass ``DATABASE_URL`` explicitly (never auto-fetched).

Usage:
  # Verify existing committed JSON files against their manifest SHA-256 hashes:
  python3 scripts/draw_cu_eval_sets.py --verify

  # Execute a newly authorized draw with saved slate weights and explicit DATABASE_URL:
  DATABASE_URL=... python3 scripts/draw_cu_eval_sets.py --slates-weights /path/to/slate_weights.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "backend" / "data" / "evals"
SEALED_PATH = DATA_DIR / "cu_sealed_300_v1.json"
DEV_PATH = DATA_DIR / "cu_dev_200_v1.json"
MANIFEST_PATH = DATA_DIR / "cu_datasets_manifest.json"
PILOT_PATH = REPO_ROOT / "handoffs" / "cu-coverage-20261127-rev10-regrade50.json"

DRAW_SEED = "cu-sealed-v1-2026-11-27"
QUARTERLY_REFRESH_RULE = (
    "Each quarter, retire the third of the sealed set (100 markets) that has been "
    "settled longest (by settled_at, then resolution_date) and draw replacements "
    "from non-pilot, non-sealed open markets using a newly posted seed."
)
RULES_TEXT_NOTE = (
    "rules_text is null on all 500 markets because Bain Luck does not store contract "
    "rules text on futures_markets rows and the CU writer does not read it."
)
DRAW_ORDER_NOTE = (
    "The development set was drawn after the sealed set from the remaining open markets, "
    "so it holds fewer of the most-seen markets (10 of 100 reader-weighted development "
    "rows appeared on all 14 slate days vs 69 of 200 in the sealed set). This does not "
    "bias the sealed set."
)

SQL_OPEN_ROSTER = """
SELECT
    fm.id,
    fm.source,
    COALESCE(fm.market_type, 'unclassified') AS market_type,
    COALESCE(fm.market_metadata->'shape'->>'outcome_relation', 'unknown') AS outcome_relation,
    CASE
        WHEN fm.volume_24h IS NULL THEN 'null'
        WHEN fm.volume_24h <= 0 THEN 'zero'
        WHEN fm.volume_24h < 1000 THEN 'low'
        WHEN fm.volume_24h < 50000 THEN 'mid'
        ELSE 'high'
    END AS volume_tier
FROM futures_markets fm
WHERE fm.status = 'open'
ORDER BY fm.id;
""".strip()

SQL_FREEZE_MARKETS = """
SELECT
    fm.id AS market_id,
    fm.source,
    fm.external_id,
    fm.event_id,
    fm.name,
    fm.description,
    fm.category,
    fm.llm_sport_category,
    fm.market_type,
    COALESCE(fm.market_metadata->'shape'->>'outcome_relation', 'unknown') AS outcome_relation,
    fm.volume_24h,
    fm.resolution_date,
    fm.status,
    fm.settled_at,
    fm.market_metadata->>'rules_primary' AS rules_primary,
    fm.market_metadata->>'rules_secondary' AS rules_secondary,
    fm.market_metadata->>'description' AS metadata_description,
    fm.market_metadata->>'rules' AS metadata_rules,
    e.commence_time AS linked_start,
    e.commence_time_source AS start_source,
    e.status AS linked_event_status,
    league.key AS linked_league,
    home_league.key AS home_team_league,
    away_league.key AS away_team_league
FROM futures_markets fm
LEFT JOIN events e ON e.id = fm.event_id
LEFT JOIN sports league ON league.id = e.sport_id
LEFT JOIN teams home_team ON home_team.id = e.home_team_id
LEFT JOIN teams away_team ON away_team.id = e.away_team_id
LEFT JOIN sports home_league ON home_league.id = home_team.sport_id
LEFT JOIN sports away_league ON away_league.id = away_team.sport_id
WHERE fm.id = ANY(%s)
ORDER BY fm.id;
""".strip()

SQL_FREEZE_OUTCOMES = """
SELECT
    fo.market_id,
    fo.id AS outcome_id,
    fo.name,
    fo.rank,
    fo.current_probability,
    fo.probability_change_24h
FROM futures_outcomes fo
WHERE fo.market_id = ANY(%s)
ORDER BY fo.market_id, fo.rank ASC NULLS LAST, fo.id ASC;
""".strip()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n").encode("utf-8")


def weighted_sample_without_replacement(
    rng: random.Random, candidates: list[tuple[int, int]], k: int
) -> list[int]:
    """Weighted Efraimidis-Spirakis sampling without replacement (deterministic)."""
    if k <= 0 or not candidates:
        return []
    keyed: list[tuple[float, int]] = []
    for mid, weight in sorted(candidates):
        w = max(1, int(weight))
        u = max(rng.random(), 1e-18)
        score = math.log(u) / w
        keyed.append((score, mid))
    keyed.sort(key=lambda item: (-item[0], item[1]))
    return [mid for _, mid in keyed[: min(k, len(keyed))]]


def spread_roster_sample(
    rng: random.Random,
    roster_rows: list[tuple[int, str, str, str, str]],
    exclude_ids: set[int],
    k: int,
) -> tuple[list[int], dict[int, tuple[str, str, str, str]]]:
    """Deal evenly round-robin across (source, market_type, outcome_relation, volume_tier)."""
    by_stratum: dict[tuple[str, str, str, str], list[int]] = defaultdict(list)
    stratum_by_id: dict[int, tuple[str, str, str, str]] = {}
    for mid, source, mtype, rel, vol_tier in roster_rows:
        if mid in exclude_ids:
            continue
        stratum = (source, mtype, rel, vol_tier)
        by_stratum[stratum].append(mid)
        stratum_by_id[mid] = stratum

    strata_order = sorted(by_stratum.keys())
    rng.shuffle(strata_order)
    for stratum in strata_order:
        rng.shuffle(by_stratum[stratum])

    picked: list[int] = []
    while len(picked) < k:
        progressed = False
        for stratum in strata_order:
            bucket = by_stratum[stratum]
            if bucket:
                picked.append(bucket.pop(0))
                progressed = True
                if len(picked) >= k:
                    break
        if not progressed:
            break
    return picked, stratum_by_id


def _clean_rules_text(row: dict[str, Any]) -> str | None:
    parts: list[str] = []
    seen: set[str] = set()
    for key in ("rules_primary", "rules_secondary", "metadata_rules", "metadata_description", "description"):
        val = row.get(key)
        if isinstance(val, str):
            text = val.strip()
            if text and text not in seen:
                seen.add(text)
                parts.append(text)
    return "\n\n".join(parts) if parts else None


def _resolve_db_url() -> str:
    env_url = (os.environ.get("DATABASE_URL") or "").strip()
    if env_url:
        return env_url
    raise RuntimeError(
        "DATABASE_URL must be passed explicitly; running draw_cu_eval_sets.py reads "
        "production and requires Alex's explicit yes (decision 453 covered Nov 27 only)."
    )


def enrich_frozen_payload(
    payload: dict[str, Any],
    *,
    ranks_by_outcome_id: dict[int, int | None],
    leagues_by_event_id: dict[int, dict[str, str | None]],
) -> tuple[dict[str, Any], dict[str, int]]:
    """Enrich an already-drawn dataset with outcome ranks and linked-game league keys.

    Keeps the exact drawn market IDs, seed, buckets, prices, and titles unchanged.
    """
    total_outcomes = 0
    matched_outcomes = 0
    linked_markets_enriched = 0
    enriched_markets: list[dict[str, Any]] = []

    for market in payload.get("markets") or []:
        event_id = market.get("event_id")
        league_info = (
            leagues_by_event_id.get(int(event_id), {})
            if event_id is not None
            else {}
        )
        if event_id is not None and int(event_id) in leagues_by_event_id:
            linked_markets_enriched += 1

        new_outcomes: list[dict[str, Any]] = []
        for out in market.get("outcomes") or []:
            oid = int(out["outcome_id"])
            total_outcomes += 1
            if oid in ranks_by_outcome_id:
                matched_outcomes += 1
            rank_val = ranks_by_outcome_id.get(oid, out.get("rank"))
            new_outcomes.append(
                {
                    "outcome_id": oid,
                    "name": out["name"],
                    "rank": int(rank_val) if rank_val is not None else None,
                    "prob": out.get("prob"),
                    "move": out.get("move"),
                }
            )
        new_outcomes.sort(
            key=lambda o: (o["rank"] is None, o["rank"] if o["rank"] is not None else 0, o["outcome_id"])
        )

        # Preserve original key ordering with league keys right after linked_event_status.
        updated: dict[str, Any] = {}
        inserted_leagues = False
        for key, val in market.items():
            if key in {"linked_league", "home_team_league", "away_team_league", "outcomes", "outcome_names"}:
                continue
            updated[key] = val
            if key == "linked_event_status":
                updated["linked_league"] = league_info.get("linked_league")
                updated["home_team_league"] = league_info.get("home_team_league")
                updated["away_team_league"] = league_info.get("away_team_league")
                inserted_leagues = True
        if not inserted_leagues:
            updated["linked_league"] = league_info.get("linked_league")
            updated["home_team_league"] = league_info.get("home_team_league")
            updated["away_team_league"] = league_info.get("away_team_league")
        updated["outcomes"] = new_outcomes
        updated["outcome_names"] = [o["name"] for o in new_outcomes]
        enriched_markets.append(updated)

    new_payload: dict[str, Any] = {}
    inserted_notes = False
    for key, val in payload.items():
        if key in {"rules_text_note", "draw_order_note", "markets"}:
            continue
        new_payload[key] = val
        if key == "quarterly_refresh_rule":
            new_payload["rules_text_note"] = RULES_TEXT_NOTE
            new_payload["draw_order_note"] = DRAW_ORDER_NOTE
            inserted_notes = True
    if not inserted_notes:
        new_payload["rules_text_note"] = RULES_TEXT_NOTE
        new_payload["draw_order_note"] = DRAW_ORDER_NOTE
    new_payload["markets"] = enriched_markets

    stats = {
        "total_outcomes": total_outcomes,
        "matched_outcomes": matched_outcomes,
        "linked_markets_enriched": linked_markets_enriched,
    }
    return new_payload, stats


def execute_draw(slates_weights_path: Path, pilot_path: Path) -> dict[str, Any]:
    import psycopg2
    import psycopg2.extras

    slates_info = json.loads(slates_weights_path.read_text(encoding="utf-8"))
    slate_weights: dict[int, int] = {int(k): int(v) for k, v in slates_info["weights"].items()}
    pilot_data = json.loads(pilot_path.read_text(encoding="utf-8"))
    pilot_ids: list[int] = [int(p["market_id"]) for p in pilot_data["profiles"]]
    pilot_id_set = set(pilot_ids)

    rng = random.Random(DRAW_SEED)
    db_url = _resolve_db_url()
    conn = psycopg2.connect(db_url)
    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute(SQL_OPEN_ROSTER)
            roster_rows = cur.fetchall()
            open_row_count = len(roster_rows)
            open_by_id = {int(r[0]): r for r in roster_rows}

            slate_open_candidates = [
                (mid, weight)
                for mid, weight in sorted(slate_weights.items())
                if mid in open_by_id and mid not in pilot_id_set
            ]
            sealed_reader_ids = weighted_sample_without_replacement(rng, slate_open_candidates, 200)
            sealed_reader_set = set(sealed_reader_ids)

            sealed_roster_ids, stratum_by_id = spread_roster_sample(
                rng, roster_rows, pilot_id_set | sealed_reader_set, 100
            )
            sealed_id_set = sealed_reader_set | set(sealed_roster_ids)

            remaining_slate = [
                (mid, weight)
                for mid, weight in slate_open_candidates
                if mid not in sealed_id_set
            ]
            dev_reader_ids = weighted_sample_without_replacement(rng, remaining_slate, 100)
            dev_roster_ids, _ = spread_roster_sample(
                rng, roster_rows, pilot_id_set | sealed_id_set | set(dev_reader_ids), 50
            )

            all_drawn_ids = sorted(sealed_id_set | set(dev_reader_ids) | set(dev_roster_ids) | pilot_id_set)

            dict_cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            dict_cur.execute(SQL_FREEZE_MARKETS, (all_drawn_ids,))
            market_rows = dict_cur.fetchall()

            dict_cur.execute(SQL_FREEZE_OUTCOMES, (all_drawn_ids,))
            outcome_rows = dict_cur.fetchall()
            dict_cur.close()
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()

    outcomes_by_market: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in outcome_rows:
        outcomes_by_market[int(row["market_id"])].append(
            {
                "outcome_id": int(row["outcome_id"]),
                "name": row["name"],
                "rank": int(row["rank"]) if row.get("rank") is not None else None,
                "prob": float(row["current_probability"]) if row["current_probability"] is not None else None,
                "move": float(row["probability_change_24h"]) if row["probability_change_24h"] is not None else None,
            }
        )

    market_by_id = {int(r["market_id"]): dict(r) for r in market_rows}
    distinct_strata = sorted({(r[1], r[2], r[3], r[4]) for r in roster_rows})

    def build_entry(mid: int, draw_bucket: str) -> dict[str, Any]:
        row = market_by_id[mid]
        outs = sorted(
            outcomes_by_market.get(mid, []),
            key=lambda o: (o["rank"] is None, o["rank"] if o["rank"] is not None else 0, o["outcome_id"]),
        )
        stratum = stratum_by_id.get(mid)
        if stratum is None and mid in open_by_id:
            _, src, mtype, rel, vtier = open_by_id[mid]
            stratum = (src, mtype, rel, vtier)
        return {
            "market_id": mid,
            "draw_bucket": draw_bucket,
            "slate_days_appeared": slate_weights.get(mid, 0),
            "stratum": {
                "venue": stratum[0] if stratum else row["source"],
                "shape": stratum[1] if stratum else (row["market_type"] or "unclassified"),
                "outcome_relation": stratum[2] if stratum else (row["outcome_relation"] or "unknown"),
                "volume_tier": stratum[3] if stratum else "unknown",
            },
            "title": row["name"],
            "source": row["source"],
            "external_id": row["external_id"],
            "category": row["category"],
            "llm_sport_category": row["llm_sport_category"],
            "market_type": row["market_type"],
            "outcome_relation": row["outcome_relation"],
            "volume_24h": int(row["volume_24h"]) if row["volume_24h"] is not None else None,
            "resolution_date": row["resolution_date"].isoformat() if row["resolution_date"] else None,
            "status": row["status"],
            "settled_at": row["settled_at"].isoformat() if row["settled_at"] else None,
            "rules_text": _clean_rules_text(row),
            "event_id": row["event_id"],
            "linked_start": row["linked_start"].isoformat() if row["linked_start"] else None,
            "start_source": row["start_source"],
            "linked_event_status": row["linked_event_status"],
            "linked_league": row.get("linked_league"),
            "home_team_league": row.get("home_team_league"),
            "away_team_league": row.get("away_team_league"),
            "outcomes": outs,
            "outcome_names": [o["name"] for o in outs],
        }

    sealed_entries = [build_entry(mid, "reader_weighted") for mid in sealed_reader_ids] + [
        build_entry(mid, "roster_spread") for mid in sealed_roster_ids
    ]
    dev_entries = (
        [build_entry(mid, "reader_weighted") for mid in dev_reader_ids]
        + [build_entry(mid, "roster_spread") for mid in dev_roster_ids]
        + [build_entry(mid, "pilot_50") for mid in pilot_ids]
    )

    drawn_at = datetime.now(timezone.utc).isoformat()
    common_header = {
        "schema_version": 1,
        "seed": DRAW_SEED,
        "drawn_at_utc": drawn_at,
        "reader_exposure_measure": {
            "source": "GET /api/admin/ranking/slates?surface=discover&limit=14",
            "definition": "Discover first 120 served items per daily slate, expanding bundles to member futures IDs, weighted by distinct days appeared (1..14).",
            "date_range": slates_info["date_range"],
            "slate_count": slates_info["slate_count"],
            "search_note": (
                "Search half omitted in v1 because search_query_logs does not store returned "
                "futures market IDs and reader search text stays unread (#13898). Next quarterly "
                "refresh adds search weights once search logs returned market IDs."
            ),
        },
        "quarterly_refresh_rule": QUARTERLY_REFRESH_RULE,
        "rules_text_note": RULES_TEXT_NOTE,
        "draw_order_note": DRAW_ORDER_NOTE,
    }

    sealed_payload = {
        **common_header,
        "dataset": "sealed",
        "counts": {
            "total": len(sealed_entries),
            "reader_weighted": len(sealed_reader_ids),
            "roster_spread": len(sealed_roster_ids),
        },
        "markets": sealed_entries,
    }
    dev_payload = {
        **common_header,
        "dataset": "development",
        "counts": {
            "total": len(dev_entries),
            "reader_weighted": len(dev_reader_ids),
            "roster_spread": len(dev_roster_ids),
            "pilot_50": len(pilot_ids),
        },
        "markets": dev_entries,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sealed_bytes = canonical_json_bytes(sealed_payload)
    dev_bytes = canonical_json_bytes(dev_payload)
    SEALED_PATH.write_bytes(sealed_bytes)
    DEV_PATH.write_bytes(dev_bytes)

    manifest = {
        "schema_version": 1,
        "seed": DRAW_SEED,
        "drawn_at_utc": drawn_at,
        "quarterly_refresh_rule": QUARTERLY_REFRESH_RULE,
        "reader_exposure_date_range": slates_info["date_range"],
        "db_query_row_counts": {
            "open_futures_markets_scanned": open_row_count,
            "distinct_roster_combinations_open": len(distinct_strata),
            "distinct_slate_markets_eligible_open": len(slate_open_candidates),
            "frozen_markets_fetched": len(market_rows),
            "frozen_outcomes_fetched": len(outcome_rows),
            "sealed_total": len(sealed_entries),
            "sealed_strata_covered": len({tuple(e["stratum"].values()) for e in sealed_entries if e["draw_bucket"] == "roster_spread"}),
            "dev_total": len(dev_entries),
        },
        "files": {
            "cu_sealed_300_v1.json": {
                "path": "backend/data/evals/cu_sealed_300_v1.json",
                "sha256": sha256_bytes(sealed_bytes),
                "count": len(sealed_entries),
            },
            "cu_dev_200_v1.json": {
                "path": "backend/data/evals/cu_dev_200_v1.json",
                "sha256": sha256_bytes(dev_bytes),
                "count": len(dev_entries),
            },
        },
    }
    MANIFEST_PATH.write_bytes(canonical_json_bytes(manifest))
    return manifest


def verify_committed_sets() -> list[str]:
    errors: list[str] = []
    if not MANIFEST_PATH.exists():
        return [f"Missing manifest: {MANIFEST_PATH}"]
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for fname, meta in manifest["files"].items():
        target = REPO_ROOT / meta["path"]
        if not target.exists():
            errors.append(f"Missing frozen file: {target}")
            continue
        actual_hash = sha256_bytes(target.read_bytes())
        if actual_hash != meta["sha256"]:
            errors.append(f"Hash mismatch for {fname}: expected {meta['sha256']}, got {actual_hash}")

    sealed = json.loads(SEALED_PATH.read_text(encoding="utf-8"))
    dev = json.loads(DEV_PATH.read_text(encoding="utf-8"))
    sealed_ids = {m["market_id"] for m in sealed["markets"]}
    dev_ids = {m["market_id"] for m in dev["markets"]}
    if len(sealed["markets"]) != 300 or len(sealed_ids) != 300:
        errors.append(f"Sealed set must have 300 unique markets, got {len(sealed['markets'])}/{len(sealed_ids)}")
    if len(dev["markets"]) != 200 or len(dev_ids) != 200:
        errors.append(f"Dev set must have 200 unique markets, got {len(dev['markets'])}/{len(dev_ids)}")
    overlap = sealed_ids & dev_ids
    if overlap:
        errors.append(f"Sealed and dev sets overlap on {sorted(overlap)[:5]}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draw or verify CU sealed & dev datasets (#13898).")
    parser.add_argument("--verify", action="store_true", help="Verify hashes & invariants only")
    parser.add_argument("--slates-weights", type=Path, help="Precomputed reader-seen weights JSON")
    parser.add_argument("--pilot", type=Path, default=PILOT_PATH, help="Pilot 50 JSON path")
    args = parser.parse_args(argv)

    if args.verify:
        errors = verify_committed_sets()
        if errors:
            for err in errors:
                print(f"ERROR: {err}", file=sys.stderr)
            return 1
        print("OK: sealed 300 and dev 200 hashes and invariants match manifest.")
        return 0

    if not args.slates_weights:
        parser.error("--slates-weights is required when drawing")
    manifest = execute_draw(args.slates_weights, args.pilot)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
