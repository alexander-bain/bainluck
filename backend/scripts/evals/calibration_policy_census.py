"""Read-only calibration policy counterfactual census (C24).

Production callers pass an approved SQLAlchemy AsyncSession to
``run_from_session``. The current curve always comes from the canonical
``deduped`` CTE; broader evidence universes are named explicitly and never
misrepresented as published rows.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

KNOWN_RELATIONS = {
    "complements", "competitors", "cumulative_thresholds", "exclusive_ranges",
    "independent_participation", "conditional", "unknown",
}


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in result.all()]


async def load_from_session(session: Any) -> dict[str, list[dict[str, Any]]]:
    """Load canonical rows and four explicitly broader evidence universes."""
    from sqlalchemy import text
    from app.tasks.precompute_calibration import _calibration_population_ctes
    from app.utils.resolution_authority import CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL

    canonical_body = _calibration_population_ctes()
    canonical_sql = text(
        "WITH " + canonical_body + """
        SELECT d.outcome_id, d.market_id, d.vm_id AS question_id, d.source,
               d.category, d.market_type, d.adj_opening_probability AS probability,
               d.is_winner, d.is_multi, d.is_mex_normalized,
               fo.volume, fo.resolution_source,
               COALESCE(ev.has_bid, false) AS has_bid,
               COALESCE(ev.has_trade, false) AS has_trade
        FROM deduped d
        JOIN futures_outcomes fo ON fo.id = d.outcome_id
        LEFT JOIN LATERAL (
            SELECT bool_or(fos.yes_bid > 0) AS has_bid,
                   bool_or(fos.last_price > 0) AS has_trade
            FROM futures_odds_snapshots fos WHERE fos.outcome_id = d.outcome_id
        ) ev ON true
        ORDER BY d.outcome_id
        """
    )

    # Broader than canonical by design: resolved + opening-valid + independent
    # truth. canonical_included distinguishes final published membership; rows
    # outside may have one OR MORE exclusion reasons, so this is never called a
    # volume-only counterfactual.
    volume_sql = text(
        "WITH " + canonical_body + f"""
        , canonical_ids AS (SELECT outcome_id, vm_id FROM deduped)
        SELECT fo.id AS outcome_id, fo.market_id, fm.source,
               COALESCE(ci.vm_id, 'm:' || fm.id::text) AS question_id,
               fo.volume, (ci.outcome_id IS NOT NULL) AS canonical_included,
               fo.resolution_source,
               COALESCE(ev.has_bid, false) AS has_bid,
               COALESCE(ev.has_trade, false) AS has_trade,
               (ev.seen_snapshot IS NOT NULL) AS snapshot_evidence_available
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        LEFT JOIN canonical_ids ci ON ci.outcome_id = fo.id
        LEFT JOIN LATERAL (
            SELECT true AS seen_snapshot,
                   bool_or(fos.yes_bid > 0) AS has_bid,
                   bool_or(fos.last_price > 0) AS has_trade
            FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id
            HAVING COUNT(*) > 0
        ) ev ON true
        WHERE fm.status = 'resolved'
          AND fo.opening_probability > 0 AND fo.opening_probability < 1
          AND fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
        ORDER BY fo.id
        """
    )

    # ``normalized`` is the canonical pre-final-filter population. This captures
    # exactly the non-normalized multi tails the production rule removes without
    # reproducing any eligibility predicate.
    tails_sql = text(
        "WITH " + canonical_body + """
        , canonical_ids AS (SELECT outcome_id FROM deduped)
        SELECT n.outcome_id, n.market_id, n.vm_id AS question_id, n.source,
               n.category, n.market_type, n.adj_opening_probability AS probability,
               n.is_winner, n.is_multi, n.is_mex_normalized,
               fo.resolution_source, fo.volume,
               (ci.outcome_id IS NOT NULL) AS canonical_included,
               COALESCE(ev.has_bid, false) AS has_bid,
               COALESCE(ev.has_trade, false) AS has_trade
        FROM normalized n
        JOIN futures_outcomes fo ON fo.id = n.outcome_id
        LEFT JOIN canonical_ids ci ON ci.outcome_id = n.outcome_id
        LEFT JOIN LATERAL (
            SELECT bool_or(fos.yes_bid > 0) AS has_bid,
                   bool_or(fos.last_price > 0) AS has_trade
            FROM futures_odds_snapshots fos WHERE fos.outcome_id = n.outcome_id
        ) ev ON true
        WHERE n.is_multi AND NOT n.is_mex_normalized
          AND (n.adj_opening_probability <= 0.005
               OR n.adj_opening_probability >= 0.98)
        ORDER BY n.outcome_id
        """
    )

    sports_sql = text("""
        SELECT e.id::text || ':moneyline' AS question_id, 'moneyline' AS kind, 'home' AS leg,
               true AS positive_leg,
               COALESCE(e.closing_home_probability, e.opening_home_probability) AS probability,
               (e.home_score > e.away_score) AS is_winner
        FROM events e WHERE e.status IN ('completed','closed')
          AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
          AND e.home_score != e.away_score
          AND COALESCE(e.closing_home_probability, e.opening_home_probability) > 0
          AND COALESCE(e.closing_home_probability, e.opening_home_probability) < 1
        UNION ALL
        SELECT e.id::text || ':moneyline', 'moneyline', 'away', false,
               COALESCE(e.closing_away_probability, e.opening_away_probability),
               (e.away_score > e.home_score)
        FROM events e WHERE e.status IN ('completed','closed')
          AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
          AND e.home_score != e.away_score
          AND COALESCE(e.closing_away_probability, e.opening_away_probability) > 0
          AND COALESCE(e.closing_away_probability, e.opening_away_probability) < 1
        UNION ALL
        SELECT e.id::text || ':spread', 'spread', 'home', true,
               CASE WHEN e.closing_home_spread_odds < 0
                    THEN abs(e.closing_home_spread_odds)::numeric/(abs(e.closing_home_spread_odds)+100.0)
                    ELSE 100.0/(e.closing_home_spread_odds+100.0) END /
               (CASE WHEN e.closing_home_spread_odds < 0
                     THEN abs(e.closing_home_spread_odds)::numeric/(abs(e.closing_home_spread_odds)+100.0)
                     ELSE 100.0/(e.closing_home_spread_odds+100.0) END +
                CASE WHEN e.closing_away_spread_odds < 0
                     THEN abs(e.closing_away_spread_odds)::numeric/(abs(e.closing_away_spread_odds)+100.0)
                     ELSE 100.0/(e.closing_away_spread_odds+100.0) END),
               ((e.home_score-e.away_score)+e.closing_home_spread > 0)
        FROM events e WHERE e.status IN ('completed','closed')
          AND e.closing_home_spread IS NOT NULL
          AND e.closing_home_spread_odds IS NOT NULL AND e.closing_away_spread_odds IS NOT NULL
          AND (e.home_score-e.away_score)+e.closing_home_spread != 0
        UNION ALL
        SELECT e.id::text || ':total', 'total', 'over', true,
               CASE WHEN e.closing_over_odds < 0
                    THEN abs(e.closing_over_odds)::numeric/(abs(e.closing_over_odds)+100.0)
                    ELSE 100.0/(e.closing_over_odds+100.0) END /
               (CASE WHEN e.closing_over_odds < 0
                     THEN abs(e.closing_over_odds)::numeric/(abs(e.closing_over_odds)+100.0)
                     ELSE 100.0/(e.closing_over_odds+100.0) END +
                CASE WHEN e.closing_under_odds < 0
                     THEN abs(e.closing_under_odds)::numeric/(abs(e.closing_under_odds)+100.0)
                     ELSE 100.0/(e.closing_under_odds+100.0) END),
               (e.home_score+e.away_score > e.closing_over_under)
        FROM events e WHERE e.status IN ('completed','closed')
          AND e.closing_over_under IS NOT NULL
          AND e.closing_over_odds IS NOT NULL AND e.closing_under_odds IS NOT NULL
          AND e.home_score+e.away_score != e.closing_over_under
        ORDER BY question_id, kind, leg
    """)

    size_two_sql = text("""
        WITH group_two AS (
            SELECT source, group_id AS family_id, array_agg(id ORDER BY id) AS market_ids
            FROM futures_markets WHERE status='resolved' AND group_id IS NOT NULL
            GROUP BY source, group_id HAVING COUNT(*)=2
        ), event_two AS (
            SELECT source, event_id AS family_id, array_agg(id ORDER BY id) AS market_ids
            FROM futures_markets WHERE status='resolved' AND event_id IS NOT NULL
            GROUP BY source, event_id HAVING COUNT(*)=2
        ), families AS (
            SELECT g.source, 'group:' || g.family_id AS family_key, unnest(g.market_ids) AS market_id
            FROM group_two g
            UNION ALL
            SELECT e.source, 'event:' || e.family_id::text AS family_key, unnest(e.market_ids) AS market_id
            FROM event_two e
        )
        SELECT f.family_key, f.source, fm.id AS market_id, fm.name AS market_name,
               fm.market_type, fm.mutually_exclusive,
               fm.market_metadata->'shape'->>'outcome_relation' AS outcome_relation,
               (fm.market_metadata->'shape'->>'exhaustive')::boolean AS exhaustive,
               (fm.market_metadata->'shape'->>'expected_winners')::int AS expected_winners,
               fo.id AS outcome_id, fo.name AS outcome_name, fo.is_winner
        FROM families f JOIN futures_markets fm ON fm.id=f.market_id
        JOIN futures_outcomes fo ON fo.market_id=fm.id
        ORDER BY f.family_key, fm.id, fo.id
    """)

    results = []
    for statement in (canonical_sql, volume_sql, tails_sql, sports_sql, size_two_sql):
        results.append(_rows(await session.execute(statement)))
    return dict(zip(("canonical", "volume_universe", "tail_candidates", "sports", "size_two"), results))


def _normal(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        try:
            p = float(row["probability"])
        except (KeyError, TypeError, ValueError):
            continue
        if not 0 <= p <= 1 or row.get("is_winner") is None:
            continue
        out.append({**row, "probability": p, "actual": int(bool(row["is_winner"])),
                    "question_id": str(row.get("question_id") or row.get("outcome_id"))})
    return out


def metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    data = _normal(rows)
    if not data:
        return {"outcomes": 0, "questions": 0, "ece": None, "brier": None}
    bins: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in data:
        bins[min(int(row["probability"] * 10), 9)].append(row)
    ece = sum(
        len(group) / len(data) * abs(
            sum(r["probability"] for r in group) / len(group)
            - sum(r["actual"] for r in group) / len(group)
        ) for group in bins.values()
    )
    brier = sum((r["probability"] - r["actual"]) ** 2 for r in data) / len(data)
    return {"outcomes": len(data), "questions": len({r["question_id"] for r in data}),
            "ece": round(ece, 6), "brier": round(brier, 6)}


def bucket_deltas(before: Iterable[dict[str, Any]], after: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    def bucket(rows):
        out = Counter()
        for row in _normal(rows):
            out[min(int(row["probability"] * 10), 9)] += 1
        return out
    a, b = bucket(before), bucket(after)
    return [{"bucket": i, "before": a[i], "after": b[i], "delta": b[i] - a[i]}
            for i in sorted(set(a) | set(b))]


def volume_census(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    cells: dict[tuple[str, str, str, bool], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        volume = row.get("volume")
        vstate = "null" if volume is None else "zero" if float(volume) == 0 else "positive"
        if not row.get("snapshot_evidence_available", True):
            evidence = "unknown"
        elif row.get("has_bid") and row.get("has_trade"):
            evidence = "bid_and_trade"
        elif row.get("has_bid"):
            evidence = "bid_only"
        elif row.get("has_trade"):
            evidence = "trade_only"
        else:
            evidence = "none"
        cells[(str(row.get("source") or "unknown"), vstate, evidence,
               bool(row.get("canonical_included")))].append(row)
    output = []
    contradictions = 0
    for key, group in sorted(cells.items()):
        source, vstate, evidence, included = key
        if vstate == "zero" and evidence in {"bid_only", "bid_and_trade"}:
            contradictions += len(group)
        output.append({"source": source, "volume_state": vstate,
                       "snapshot_evidence": evidence, "canonical_included": included,
                       "outcomes": len(group),
                       "questions": len({str(r.get('question_id')) for r in group})})
    return {"universe": "resolved_opening_valid_independent_truth; exclusions may overlap",
            "cells": output, "bid_with_zero_volume_outcomes": contradictions}


def sports_counterfactual(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    data = list(rows)
    current = metrics(data)
    one_per_question = [r for r in data if bool(r.get("positive_leg"))]
    by_kind = {kind: metrics(r for r in data if r.get("kind") == kind)
               for kind in sorted({str(r.get("kind")) for r in data})}
    return {"estimands": {"current": "outcome-weighted; moneyline has two legs",
                           "question": "one declared positive leg per binary question"},
            "current": current, "question_weighted": metrics(one_per_question),
            "by_kind": by_kind}


def datagolf_counterfactual(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    data = list(rows)
    dg = [r for r in data if r.get("source") == "datagolf"]
    without = [r for r in data if r.get("source") != "datagolf"]
    return {"label": "DataGolf model forecast; no source-bias interpretation",
            "combined_current": metrics(data), "datagolf_only": metrics(dg),
            "combined_without_datagolf": metrics(without),
            "bucket_deltas_without_datagolf": bucket_deltas(data, without)}


def tail_census(canonical: Iterable[dict[str, Any]], tails: Iterable[dict[str, Any]]) -> dict[str, Any]:
    current, candidates = list(canonical), list(tails)
    added = current + [r for r in candidates if not r.get("canonical_included")]
    cells: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        evidence = "traded" if row.get("has_trade") else "bid_only" if row.get("has_bid") else "none"
        cells[(str(row.get("source") or "unknown"), str(row.get("market_type") or "unknown"),
               evidence, str(row.get("resolution_source") or "missing"))].append(row)
    return {"rule": "non-normalized multi probability <=0.005 or >=0.98",
            "cells": [{"source": k[0], "market_type": k[1], "trading_evidence": k[2],
                       "resolution_source": k[3], "outcomes": len(v),
                       "questions": len({str(r.get('question_id')) for r in v})}
                      for k, v in sorted(cells.items())],
            "current": metrics(current), "include_candidates": metrics(added),
            "bucket_deltas": bucket_deltas(current, added)}


def classify_size_two(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        families[str(row.get("family_key"))].append(row)
    output, counts = [], Counter()
    for key, group in sorted(families.items()):
        relations = {r.get("outcome_relation") or "unknown" for r in group}
        unknown_rel = relations - KNOWN_RELATIONS
        member_ids = {r.get("market_id") for r in group}
        positives = [r for r in group if str(r.get("outcome_name") or "").strip().lower() not in {"no", "under"}]
        negatives = [r for r in group if str(r.get("outcome_name") or "").strip().lower() in {"no", "under"}]
        projected_winners = sum(r.get("is_winner") is True for r in positives)
        contracts = {(r.get("exhaustive"), r.get("expected_winners")) for r in group}
        if unknown_rel:
            verdict, reason = "unknown", "unrecognized_relation"
        elif relations & {"conditional", "cumulative_thresholds", "independent_participation"}:
            verdict, reason = "unsafe", "non_competitor_relation"
        elif relations == {"competitors"} and contracts == {(True, 1)} and len(member_ids) == 2:
            if len(positives) == 2 and projected_winners == 1:
                verdict, reason = "structurally_safe_candidate", "explicit_positive_projection"
            else:
                verdict, reason = "unknown", "positive_leg_projection_unproven"
        else:
            verdict, reason = "unknown", "contract_incomplete_or_mixed"
        counts[verdict] += 1
        output.append({"family_key": key, "verdict": verdict, "reason": reason,
                       "markets": len(member_ids), "raw_outcomes": len(group),
                       "positive_legs": len(positives), "negative_legs": len(negatives),
                       "projected_winners": projected_winners,
                       "relations": sorted(str(v) for v in relations),
                       "examples": sorted({str(r.get('market_name') or '') for r in group})[:3]})
    return {"counts": dict(sorted(counts.items())), "families": output,
            "warning": "raw four-leg Yes/No families are never treated as two outcomes without explicit projection"}


def build_report(payload: dict[str, Any]) -> dict[str, Any]:
    canonical = payload.get("canonical") or payload.get("rows") or []
    from app.utils.resolution_authority import calibration_truth_class
    unknown_resolution_sources = sorted({
        str(row.get("resolution_source")) for row in canonical
        if row.get("resolution_source")
        and calibration_truth_class(str(row.get("resolution_source"))) == "unknown"
    })
    return {
        "contract": {"current_population": "canonical deduped row identity",
                     "counterfactuals": "descriptive; no product winner or source-bias claim",
                     "unknown_resolution_sources": unknown_resolution_sources,
                     "contract_ok": not unknown_resolution_sources},
        "current": metrics(canonical),
        "volume": volume_census(payload.get("volume_universe") or []),
        "sports_weighting": sports_counterfactual(payload.get("sports") or []),
        "datagolf": datagolf_counterfactual(canonical),
        "extreme_tails": tail_census(canonical, payload.get("tail_candidates") or []),
        "size_two_families": classify_size_two(payload.get("size_two") or []),
    }


async def run_from_session(session: Any) -> dict[str, Any]:
    return build_report(await load_from_session(session))


async def _main(path: str) -> None:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    print(json.dumps(build_report(payload), indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Offline JSON export; production uses run_from_session")
    args = parser.parse_args()
    asyncio.run(_main(args.input))
