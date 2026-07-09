"""Offline replay runner for Discover ranking (#142/RANK-2).

Load a frozen candidate-pool snapshot (``discover_candidate_snapshots``, written
by ``app.utils.discover_candidate_snapshot``) and re-rank it under one or more
configs (InterestingnessWeights + blend weight + per-category base overrides).
For each config it diffs the replayed top-K against:

  (i)   the served ordering captured in the snapshot,
  (ii)  the human-label gold set (RankingJudgment), reusing evaluate_gold_set,
  (iii) classifier metrics (quality-class distribution + family/story diversity).

This is eval infrastructure only. It never mutates ranking behavior — it reads a
snapshot and recomputes offline, mirroring the feed's exact blend formula so a
config diff is apples-to-apples.

Usage:
    # against the latest snapshot in the DB, default two configs:
    python3 scripts/replay_discover_ranking.py

    # a specific snapshot + gold-set split + custom configs:
    python3 scripts/replay_discover_ranking.py --run-id <uuid> --split dev \
        --config-file configs.json --top-k 20 --json

    # fully offline demo (synthetic snapshot, no DB), two configs:
    python3 scripts/replay_discover_ranking.py --demo
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.market_interestingness import (  # noqa: E402
    DEFAULT_WEIGHTS,
    InterestingnessWeights,
    MarketInterestingnessInputs,
    score_market_interestingness,
)
from scripts.evaluate_discover_label_gold_set import evaluate_gold_set  # noqa: E402

_SPLIT_SALT = "bainluck-discover-labels-v1"


def dataset_split(market_id: int | None, event_id: int | None = None) -> str:
    """Deterministic 80/10/10 split — mirror of admin_judgments._dataset_split.

    Kept in sync by hand (same salt/algorithm) to avoid importing the FastAPI
    route module into an offline script.
    """
    item_key = str(market_id or event_id or 0)
    digest = hashlib.md5(f"{_SPLIT_SALT}:{item_key}".encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "dev"
    return "test"


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReplayConfig:
    name: str
    weights: InterestingnessWeights = DEFAULT_WEIGHTS
    blend_weight: float = 0.2
    base_overrides: dict[str, float] = field(default_factory=dict)


def config_from_dict(data: dict[str, Any]) -> ReplayConfig:
    weight_fields = {
        f
        for f in InterestingnessWeights.__dataclass_fields__  # type: ignore[attr-defined]
    }
    raw_weights = data.get("weights") or {}
    weights = InterestingnessWeights(
        **{k: float(v) for k, v in raw_weights.items() if k in weight_fields}
    )
    return ReplayConfig(
        name=str(data.get("name") or "config"),
        weights=weights,
        blend_weight=float(data.get("blend_weight", 0.2)),
        base_overrides={
            str(k).lower(): float(v)
            for k, v in (data.get("base_overrides") or {}).items()
        },
    )


def default_configs() -> list[ReplayConfig]:
    """Three configs that tell the RANK-2 story on any snapshot:

    1. baseline           — current production knobs.
    2. movement_heavy      — a very different interestingness weight vector; if
       its ordering matches baseline that PROVES the +15 blend cap saturates and
       interestingness weights cannot move ordering today (the RANK-3 target).
    3. base_reshuffle      — a per-category base override; demonstrates the harness
       DOES detect a genuine ordering change (base scores is one of the three
       named replay knobs).
    """
    baseline = ReplayConfig(name="baseline", weights=DEFAULT_WEIGHTS, blend_weight=0.2)
    movement_heavy = ReplayConfig(
        name="movement_heavy",
        weights=InterestingnessWeights(
            decisiveness=10.0,
            multi_source=8.0,
            recency=12.0,
            movement=28.0,
            resolution_proximity=12.0,
            category_novelty=8.0,
            volume=12.0,
            llm_quality=10.0,
        ),
        blend_weight=0.35,
    )
    base_reshuffle = ReplayConfig(
        name="base_reshuffle",
        weights=DEFAULT_WEIGHTS,
        blend_weight=0.2,
        base_overrides={"sports": 60.0, "crypto": 12.0},
    )
    return [baseline, movement_heavy, base_reshuffle]


# --------------------------------------------------------------------------- #
# Re-ranking (mirrors feed.py exactly)
# --------------------------------------------------------------------------- #
def blend_rank(pre_blend: float, i_score: float | None, weight: float) -> float:
    """Mirror feed.py's de-saturated ordering blend (#143/RANK-3).

    Both ``pre_blend`` and ``i_score`` are 0-100 (the scorer normalizes to
    0-100). The blend is a direct convex combination weighted by ``weight`` —
    NO ``* 100`` (the #142 double-scale bug) and NO +15 uplift cap on the
    ranking chain, so ``weight`` is the only bound on interestingness'
    influence over ordering. ``weight`` 0 / missing score => unchanged
    (kill switch, mirrors the ``> 0`` guard in feed.py)."""
    if not weight or weight <= 0 or i_score is None:
        return pre_blend
    blended = pre_blend * (1 - weight) + i_score * weight
    return max(0.0, blended)


def replayed_rank_score(row: dict[str, Any], config: ReplayConfig) -> float:
    pre = row.get("pre_blend_rank_score")
    if pre is None:
        pre = row.get("rank_score") or 0.0
    pre = float(pre)

    # First-order base-score override: category_base is additive into the base,
    # so shifting by (new - captured) is exact for the anonymous baseline
    # (multiplier ~1.0). Documented approximation; interestingness/blend are exact.
    if config.base_overrides:
        cat = (row.get("category") or "").lower()
        old_base = row.get("category_base")
        if cat in config.base_overrides and old_base is not None:
            pre = pre + (config.base_overrides[cat] - float(old_base))

    i_score: float | None = None
    features = row.get("features") or {}
    if features:
        inputs = MarketInterestingnessInputs.from_mapping(features)
        i_score = score_market_interestingness(inputs, weights=config.weights).score
    return blend_rank(pre, i_score, config.blend_weight)


def rerank(rows: list[dict[str, Any]], config: ReplayConfig) -> list[dict[str, Any]]:
    scored = []
    for row in rows:
        scored.append({**row, "replay_rank_score": replayed_rank_score(row, config)})
    # Stable tiebreak on the served rank so equal scores keep a deterministic order.
    scored.sort(
        key=lambda r: (-(r["replay_rank_score"]), r.get("served_rank") or 10**9)
    )
    for index, row in enumerate(scored, start=1):
        row["replay_rank"] = index
    return scored


# --------------------------------------------------------------------------- #
# Diffs
# --------------------------------------------------------------------------- #
def diff_vs_served(reranked: list[dict[str, Any]], *, top_k: int) -> dict[str, Any]:
    served_top = {
        r["market_id"]
        for r in sorted(reranked, key=lambda r: r.get("served_rank") or 10**9)[:top_k]
    }
    replay_top = {r["market_id"] for r in reranked[:top_k]}
    deltas = [
        abs((r.get("served_rank") or 0) - r["replay_rank"])
        for r in reranked
        if r.get("served_rank")
    ]
    overlap = len(served_top & replay_top)
    return {
        "top_k": top_k,
        "top_k_overlap": overlap,
        "top_k_overlap_rate": round(overlap / top_k, 4) if top_k else None,
        "moved_into_top_k": sorted(replay_top - served_top),
        "moved_out_of_top_k": sorted(served_top - replay_top),
        "mean_abs_rank_delta": round(sum(deltas) / len(deltas), 3) if deltas else 0.0,
        "max_abs_rank_delta": max(deltas) if deltas else 0,
    }


def gold_set_diff(
    reranked: list[dict[str, Any]],
    labels_by_market: dict[int, dict[str, Any]],
    *,
    top_k: int,
    split: str | None,
) -> dict[str, Any]:
    eval_rows: list[dict[str, Any]] = []
    for row in reranked:
        label = labels_by_market.get(row["market_id"])
        if not label:
            continue
        if split and dataset_split(row["market_id"]) != split:
            continue
        eval_rows.append(
            {
                "id": f"futures:{row['market_id']}",
                "market_id": row["market_id"],
                "name": row.get("name") or label.get("name") or "",
                "category": row.get("category") or label.get("category") or "unknown",
                "label": label.get("label"),
                # rank_seen = the REPLAYED position, so gold-set metrics reflect
                # this config's ordering, not the originally served one.
                "rank_seen": row["replay_rank"],
                "score_at_review": label.get("score_at_review"),
                "tapworthy_score": label.get("tapworthy_score", ""),
                "boring": label.get("boring", ""),
                "clarity": label.get("clarity", ""),
                "explanation_quality": label.get("explanation_quality", ""),
                "image_fit": label.get("image_fit", ""),
                "audience_scope": label.get("audience_scope", ""),
                "duplicate_severity": label.get("duplicate_severity", ""),
                "reason_tags": label.get("reason_tags", ""),
                "fix_type": label.get("fix_type", ""),
                "would_be_interesting_if": label.get("would_be_interesting_if", ""),
            }
        )
    if not eval_rows:
        return {"labeled_candidates": 0, "note": "no labeled candidates in snapshot"}
    metrics = evaluate_gold_set(eval_rows, top_k=min(top_k, len(eval_rows)))
    k = metrics["top_k"]
    return {
        "labeled_candidates": len(eval_rows),
        "split": split or "all",
        "tapworthy_at_k": metrics.get(f"tapworthy_at_{k}"),
        "boring_rate_at_k": metrics.get(f"boring_rate_at_{k}"),
        "duplicate_family_rate_at_k": metrics.get(f"duplicate_family_rate_at_{k}"),
        "tapworthy_recall_at_k": metrics.get(f"tapworthy_recall_at_{k}"),
        "top_k": k,
    }


def classifier_metrics(reranked: list[dict[str, Any]], *, top_k: int) -> dict[str, Any]:
    top = reranked[:top_k]
    quality_counts: dict[str, int] = {}
    for row in top:
        cls = row.get("quality_class") or "unknown"
        quality_counts[cls] = quality_counts.get(cls, 0) + 1
    families = {r.get("family_key") for r in top if r.get("family_key")}
    stories = {r.get("story_key") for r in top if r.get("story_key")}
    interest = [
        r.get("interestingness_score")
        for r in top
        if r.get("interestingness_score") is not None
    ]
    n = len(top)
    return {
        "top_k": n,
        "quality_class_counts": dict(sorted(quality_counts.items())),
        "distinct_families": len(families),
        "distinct_stories": len(stories),
        "duplicate_family_rate": round(1 - len(families) / n, 4) if n else None,
        "distinct_categories": len({r.get("category") for r in top}),
        "mean_interestingness": (
            round(sum(interest) / len(interest), 3) if interest else None
        ),
    }


def compare_configs(
    rows: list[dict[str, Any]],
    configs: list[ReplayConfig],
    labels_by_market: dict[int, dict[str, Any]],
    *,
    top_k: int,
    split: str | None,
) -> dict[str, Any]:
    results = []
    for config in configs:
        reranked = rerank(rows, config)
        results.append(
            {
                "config": config.name,
                "blend_weight": config.blend_weight,
                "vs_served": diff_vs_served(reranked, top_k=top_k),
                "gold_set": gold_set_diff(
                    reranked, labels_by_market, top_k=top_k, split=split
                ),
                "classifier": classifier_metrics(reranked, top_k=top_k),
                "top": [
                    {
                        "rank": r["replay_rank"],
                        "served_rank": r.get("served_rank"),
                        "market_id": r["market_id"],
                        "name": (r.get("name") or "")[:52],
                        "score": round(r["replay_rank_score"], 2),
                    }
                    for r in reranked[:top_k]
                ],
            }
        )
    return {
        "candidate_count": len(rows),
        "top_k": top_k,
        "split": split or "all",
        "configs": results,
    }


def format_table(comparison: dict[str, Any]) -> str:
    lines = []
    lines.append(
        f"Replay comparison — {comparison['candidate_count']} candidates, "
        f"top_k={comparison['top_k']}, split={comparison['split']}"
    )
    lines.append("=" * 78)
    header = (
        f"{'config':<16}{'blend':>6}{'top-k∩':>8}{'meanΔ':>8}"
        f"{'tap@k':>8}{'boring@k':>10}{'dupFam':>8}{'labeled':>9}"
    )
    lines.append(header)
    lines.append("-" * 78)
    for result in comparison["configs"]:
        served = result["vs_served"]
        gold = result["gold_set"]
        clf = result["classifier"]
        lines.append(
            f"{result['config']:<16}"
            f"{result['blend_weight']:>6.2f}"
            f"{served['top_k_overlap']:>8}"
            f"{served['mean_abs_rank_delta']:>8.2f}"
            f"{_fmt(gold.get('tapworthy_at_k')):>8}"
            f"{_fmt(gold.get('boring_rate_at_k')):>10}"
            f"{_fmt(clf.get('duplicate_family_rate')):>8}"
            f"{gold.get('labeled_candidates', 0):>9}"
        )
    lines.append("-" * 78)
    # Show what moved for the non-baseline configs relative to served ordering.
    for result in comparison["configs"]:
        moved_in = result["vs_served"]["moved_into_top_k"]
        if moved_in:
            lines.append(
                f"  [{result['config']}] into top-{comparison['top_k']}: "
                f"markets {moved_in[:10]}"
            )
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.3f}"


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #
def _serialize_snapshot(row: Any) -> dict[str, Any]:
    return {
        "market_id": row.market_id,
        "served_rank": row.served_rank,
        "name": row.name,
        "category": row.category,
        "source": row.source,
        "quality_class": row.quality_class,
        "family_key": row.family_key,
        "story_key": row.story_key,
        "rank_score": row.rank_score,
        "display_score": row.display_score,
        "pre_blend_rank_score": row.pre_blend_rank_score,
        "category_base": row.category_base,
        "interestingness_score": row.interestingness_score,
        "features": row.features or {},
    }


async def load_snapshot_from_db(run_id: str | None) -> tuple[str | None, list[dict[str, Any]]]:
    from sqlalchemy import desc, select

    from app.models.models import DiscoverCandidateSnapshot
    from app.services.database import async_session_maker

    async with async_session_maker() as db:
        if run_id is None:
            latest = await db.execute(
                select(DiscoverCandidateSnapshot.run_id)
                .order_by(desc(DiscoverCandidateSnapshot.captured_at))
                .limit(1)
            )
            run_id = latest.scalars().first()
            if run_id is None:
                return None, []
        result = await db.execute(
            select(DiscoverCandidateSnapshot)
            .where(DiscoverCandidateSnapshot.run_id == run_id)
            .order_by(DiscoverCandidateSnapshot.served_rank)
        )
        rows = [_serialize_snapshot(r) for r in result.scalars().all()]
    return run_id, rows


async def load_labels_from_db(days: int) -> dict[int, dict[str, Any]]:
    from datetime import datetime, timedelta, timezone

    from app.services.database import async_session_maker
    from scripts.export_discover_labeled_dataset import export_rows

    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with async_session_maker() as db:
        rows = await export_rows(
            db, since=since, limit=5000, surface=None, reviewer=None, labels=None
        )
    labels: dict[int, dict[str, Any]] = {}
    for row in rows:
        market_id = row.get("market_id")
        if market_id is None:
            continue
        # Keep the most recent label per market (export is newest-first).
        labels.setdefault(int(market_id), row)
    return labels


def load_rows_from_file(path: str) -> list[dict[str, Any]]:
    text = Path(path).read_text()
    if path.endswith(".jsonl"):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("rows") or data.get("candidates") or []
    return list(data)


def load_labels_from_file(path: str) -> dict[int, dict[str, Any]]:
    rows = load_rows_from_file(path)
    labels: dict[int, dict[str, Any]] = {}
    for row in rows:
        market_id = row.get("market_id")
        if market_id is not None:
            labels.setdefault(int(market_id), row)
    return labels


# --------------------------------------------------------------------------- #
# Demo (no DB): synthetic snapshot scored through the real interestingness path
# --------------------------------------------------------------------------- #
def build_demo_snapshot() -> list[dict[str, Any]]:
    """A synthetic-but-real snapshot: features run through the real scorer.

    Used for offline demos and tests. The ordering diff between configs is
    genuine (produced by the real interestingness scorer), only the input
    features are hand-authored.
    """
    specs = [
        # (mid, cat, pre_blend, cat_base, leader, move, vol, source_count, quality, family)
        (101, "politics", 62.0, 45, 0.58, 0.04, 900000, 3, "compelling", "us_election"),
        (102, "geopolitics", 60.0, 45, 0.71, 0.22, 120000, 2, "compelling", "russia_ukraine"),
        (103, "economics", 58.0, 42, 0.66, 0.01, 40000, 2, "compelling", "fed_rates"),
        (104, "tech", 57.0, 42, 0.80, 0.15, 220000, 2, "compelling", "ai_race"),
        (105, "sports", 56.0, 18.5, 0.90, 0.02, 50000, 3, "commodity", "nba_champ"),
        (106, "entertainment", 55.0, 40, 0.62, 0.09, 15000, 1, "compelling", "box_office"),
        (107, "crypto", 54.0, 28, 0.55, 0.30, 8000, 1, "commodity", "btc_price"),
        (108, "weather", 52.0, 32, 0.75, 0.05, 3000, 1, "commodity", "rain_nyc"),
        (109, "culture", 51.0, 38, 0.60, 0.12, 22000, 2, "compelling", "awards"),
        (110, "health", 50.0, 38, 0.68, 0.03, 12000, 2, "compelling", "outbreak"),
    ]
    rows = []
    for served_rank, (
        mid, cat, pre_blend, cat_base, leader, move, vol, sources, quality, family,
    ) in enumerate(specs, start=1):
        rows.append(
            {
                "market_id": mid,
                "served_rank": served_rank,
                "name": f"Demo {cat} market {mid}",
                "category": cat,
                "source": "demo",
                "quality_class": quality,
                "family_key": family,
                "story_key": family,
                "rank_score": pre_blend,
                "display_score": int(min(98, pre_blend)),
                "pre_blend_rank_score": pre_blend,
                "category_base": cat_base,
                "interestingness_score": None,
                "features": {
                    "leader_probability": leader,
                    "source_count": sources,
                    "movement_24h": move,
                    "resolution_date": "2026-07-20T00:00:00+00:00",
                    "category": cat,
                    "volume_24h": vol,
                    "llm_quality": 0.7,
                    "updated_at": "2026-07-08T18:00:00+00:00",
                },
            }
        )
    return rows


def build_demo_labels() -> dict[int, dict[str, Any]]:
    """Synthetic gold-set labels so the demo exercises the gold-set diff path."""
    specs = {
        101: "love",
        102: "love",
        104: "love",
        105: "bad",
        107: "kill",
        108: "bad",
        109: "fine",
    }
    return {
        mid: {
            "market_id": mid,
            "label": label,
            "score_at_review": {"love": 5, "fine": 3, "bad": 1, "kill": 0}[label],
            "category": "demo",
            "name": f"Demo market {mid}",
        }
        for mid, label in specs.items()
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="Snapshot run_id (default: latest in DB)")
    parser.add_argument("--snapshot-file", help="Load snapshot rows from JSON/JSONL")
    parser.add_argument("--labels-file", help="Load gold-set rows from JSON/JSONL")
    parser.add_argument("--config-file", help="JSON list of config dicts")
    parser.add_argument("--split", choices=("train", "dev", "test"))
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--label-days", type=int, default=120)
    parser.add_argument("--demo", action="store_true", help="Offline synthetic snapshot")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.config_file:
        configs = [config_from_dict(d) for d in json.loads(Path(args.config_file).read_text())]
    else:
        configs = default_configs()

    if args.demo:
        run_id = "demo"
        rows = build_demo_snapshot()
        labels: dict[int, dict[str, Any]] = build_demo_labels()
    elif args.snapshot_file:
        run_id = args.snapshot_file
        rows = load_rows_from_file(args.snapshot_file)
        labels = load_labels_from_file(args.labels_file) if args.labels_file else {}
    else:
        run_id, rows = asyncio.run(load_snapshot_from_db(args.run_id))
        if not rows:
            print("No snapshot rows found. Run the snapshot task or pass --demo.")
            return 1
        labels = (
            load_labels_from_file(args.labels_file)
            if args.labels_file
            else asyncio.run(load_labels_from_db(args.label_days))
        )

    comparison = compare_configs(
        rows, configs, labels, top_k=args.top_k, split=args.split
    )
    comparison["run_id"] = run_id

    if args.json:
        print(json.dumps(comparison, indent=2, sort_keys=True))
    else:
        print(f"run_id: {run_id}")
        print(format_table(comparison))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
