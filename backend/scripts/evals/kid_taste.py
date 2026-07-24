"""Extract kid taste signals from Play interactions and Higher/Lower guesses.

Consumes a JSON export or an SQLAlchemy AsyncSession. JSON may contain
``discover_interactions``, ``user_predictions``, and optional
``interestingness``/``candidate_snapshots`` arrays. Database loading is
read-only and restricted to ``kid:%`` sessions plus Play-sourced interactions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

POSITIVE_ACTIONS = {"like"}
NEGATIVE_ACTIONS = {"unlike", "dismiss"}


def load_json(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"discover_interactions": data, "user_predictions": [], "interestingness": []}
    if not isinstance(data, dict):
        raise ValueError("JSON export must be an object or interaction array")
    return {
        "discover_interactions": _list_value(data, "discover_interactions", "interactions"),
        "user_predictions": _list_value(data, "user_predictions", "predictions"),
        "interestingness": _list_value(data, "interestingness", "candidate_snapshots"),
    }


def _list_value(data: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        if isinstance(data.get(key), list):
            return data[key]
    return []


async def load_from_session(session: Any) -> dict[str, list[dict[str, Any]]]:
    """Load kid rows and the latest available market scorer snapshots."""
    from sqlalchemy import and_, func, select
    from app.models.models import (
        DiscoverCandidateSnapshot,
        DiscoverInteraction,
        FuturesMarket,
        UserPrediction,
    )

    kid_session = "kid:%"
    interaction_result = await session.execute(
        select(
            DiscoverInteraction.session_id,
            DiscoverInteraction.action,
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
            DiscoverInteraction.category,
            DiscoverInteraction.item_name,
            DiscoverInteraction.score,
            DiscoverInteraction.source,
            DiscoverInteraction.created_at,
        ).where(
            DiscoverInteraction.session_id.like(kid_session),
            DiscoverInteraction.source == "play",
        )
    )
    prediction_result = await session.execute(
        select(
            UserPrediction.session_id,
            UserPrediction.market_id,
            UserPrediction.guess,
            UserPrediction.threshold,
            UserPrediction.actual_probability,
            UserPrediction.correct,
            UserPrediction.created_at,
            FuturesMarket.id.label("resolved_market_id"),
            FuturesMarket.name.label("item_name"),
            FuturesMarket.llm_sport_category.label("category"),
        )
        .outerjoin(FuturesMarket, FuturesMarket.id == UserPrediction.market_id)
        .where(UserPrediction.session_id.like(kid_session))
    )
    latest = (
        select(
            DiscoverCandidateSnapshot.market_id,
            func.max(DiscoverCandidateSnapshot.captured_at).label("captured_at"),
        )
        .group_by(DiscoverCandidateSnapshot.market_id)
        .subquery()
    )
    snapshot_result = await session.execute(
        select(
            DiscoverCandidateSnapshot.market_id.label("item_id"),
            DiscoverCandidateSnapshot.interestingness_score,
            DiscoverCandidateSnapshot.name.label("item_name"),
            DiscoverCandidateSnapshot.category,
        ).join(
            latest,
            and_(
                latest.c.market_id == DiscoverCandidateSnapshot.market_id,
                latest.c.captured_at == DiscoverCandidateSnapshot.captured_at,
            ),
        )
    )
    return {
        "discover_interactions": [dict(row._mapping) for row in interaction_result.all()],
        "user_predictions": [dict(row._mapping) for row in prediction_result.all()],
        "interestingness": [dict(row._mapping) for row in snapshot_result.all()],
    }


async def load_rows(source: str | Path | Any) -> dict[str, list[dict[str, Any]]]:
    if isinstance(source, (str, Path)):
        return load_json(source)
    if hasattr(source, "execute"):
        return await load_from_session(source)
    raise TypeError("source must be a JSON path or SQLAlchemy session")


def analyze(export: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    interactions = _normalize_interactions(export.get("discover_interactions", []))
    predictions = _normalize_predictions(export.get("user_predictions", []))
    score_index = _score_index(export.get("interestingness", []))
    kid_ids = sorted({row["kid"] for row in interactions + predictions})
    profiles = [
        _profile(
            kid,
            [row for row in interactions if row["kid"] == kid],
            [row for row in predictions if row["kid"] == kid],
            score_index,
        )
        for kid in kid_ids
    ]
    return {
        "kids": len(kid_ids),
        "interaction_rows": len(interactions),
        "prediction_rows": len(predictions),
        "profiles": profiles,
        "inter_kid_agreement": _inter_kid_agreement(interactions),
        "namespace_caveat": {
            "definite_missing_market": sum(
                profile["predictions"]["namespace_flags"]["definite_missing_market"]
                for profile in profiles
            ),
            "unverifiable_legacy": sum(
                profile["predictions"]["namespace_flags"]["unverifiable_legacy"]
                for profile in profiles
            ),
            "note": (
                "Legacy user_predictions has no subject type. Existing market IDs may still "
                "be event-ID collisions and cannot be proven valid after capture."
            ),
        },
    }


def _normalize_interactions(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        session_id = str(row.get("session_id") or "")
        action = str(row.get("action") or "").lower()
        if not session_id.startswith("kid:") or row.get("source") != "play":
            continue
        if action not in POSITIVE_ACTIONS | NEGATIVE_ACTIONS:
            continue
        item_id = str(row.get("item_id") or "")
        if not item_id:
            continue
        normalized.append(
            {
                **row,
                "kid": session_id,
                "action": action,
                "preference": 1 if action in POSITIVE_ACTIONS else -1,
                "item_id": item_id,
                "item_type": str(row.get("item_type") or "unknown"),
                "category": str(row.get("category") or "unknown").lower(),
                "item_name": str(row.get("item_name") or item_id),
            }
        )
    return normalized


def _normalize_predictions(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        session_id = str(row.get("session_id") or "")
        if not session_id.startswith("kid:"):
            continue
        market_id = row.get("market_id")
        if market_id is None:
            continue
        market_exists = row.get("market_exists")
        if market_exists is None and "resolved_market_id" in row:
            market_exists = row.get("resolved_market_id") is not None
        subject_type = row.get("subject_type")
        if subject_type == "event" or market_exists is False:
            namespace_status = "definite_missing_market"
        elif subject_type == "futures":
            namespace_status = "verified_futures"
        else:
            namespace_status = "unverifiable_legacy"
        normalized.append(
            {
                **row,
                "kid": session_id,
                "market_id": str(market_id),
                "correct": bool(row.get("correct")),
                "namespace_status": namespace_status,
                "created_at": str(row.get("created_at") or ""),
            }
        )
    return normalized


def _score_index(rows: Iterable[dict[str, Any]]) -> dict[str, float]:
    result = {}
    for row in rows:
        item_id = row.get("item_id", row.get("market_id"))
        value = row.get("interestingness_score", row.get("score"))
        try:
            score = float(value)
        except (TypeError, ValueError):
            continue
        if item_id is not None and math.isfinite(score):
            result[str(item_id)] = score
    return result


def _profile(
    kid: str,
    interactions: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    score_index: dict[str, float],
) -> dict[str, Any]:
    category = _taste_rollup(interactions, "category")
    entities = _taste_rollup(interactions, "item_name")
    scored = []
    for row in interactions:
        score = score_index.get(row["item_id"])
        if score is None:
            try:
                score = float(row["score"])
            except (KeyError, TypeError, ValueError):
                continue
        scored.append({**row, "interestingness_score": score})
    preferences = [row["preference"] for row in scored]
    scores = [row["interestingness_score"] for row in scored]
    divergence = sorted(
        scored,
        key=lambda row: row["preference"] * (50.0 - row["interestingness_score"]),
        reverse=True,
    )[:10]
    prediction_correct = [row["correct"] for row in sorted(predictions, key=lambda row: row["created_at"])]
    current_streak, best_streak = _streaks(prediction_correct)
    return {
        "kid": kid,
        "interactions": len(interactions),
        "likes": sum(row["preference"] > 0 for row in interactions),
        "dislikes": sum(row["preference"] < 0 for row in interactions),
        "like_rate": _round(sum(row["preference"] > 0 for row in interactions) / len(interactions))
        if interactions
        else None,
        "categories": category,
        "entities": entities,
        "scorer_agreement": {
            "n": len(scored),
            "pearson": _round(_pearson(preferences, scores)),
            "mean_liked_score": _round(_mean(row["interestingness_score"] for row in scored if row["preference"] > 0)),
            "mean_disliked_score": _round(_mean(row["interestingness_score"] for row in scored if row["preference"] < 0)),
            "hardest_divergences": [
                {
                    "item_id": row["item_id"],
                    "item_name": row["item_name"],
                    "action": row["action"],
                    "interestingness_score": row["interestingness_score"],
                }
                for row in divergence
            ],
        },
        "predictions": {
            "n": len(predictions),
            "correct": sum(prediction_correct),
            "accuracy": _round(sum(prediction_correct) / len(prediction_correct)) if predictions else None,
            "current_streak": current_streak,
            "best_streak": best_streak,
            "namespace_flags": {
                status: sum(row["namespace_status"] == status for row in predictions)
                for status in ("definite_missing_market", "unverifiable_legacy", "verified_futures")
            },
        },
    }


def _taste_rollup(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row["preference"])
    return sorted(
        (
            {
                key: name,
                "ratings": len(values),
                "likes": sum(value > 0 for value in values),
                "dislikes": sum(value < 0 for value in values),
                "like_rate": _round(sum(value > 0 for value in values) / len(values)),
            }
            for name, values in groups.items()
        ),
        key=lambda row: (-row["ratings"], -row["like_rate"], row[key]),
    )


def _inter_kid_agreement(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_kid: dict[str, dict[tuple[str, str], int]] = defaultdict(dict)
    for row in rows:
        by_kid[row["kid"]][(row["item_type"], row["item_id"])] = row["preference"]
    pairs = []
    for left, right in combinations(sorted(by_kid), 2):
        shared = sorted(set(by_kid[left]) & set(by_kid[right]))
        agreements = sum(by_kid[left][item] == by_kid[right][item] for item in shared)
        pairs.append(
            {
                "left": left,
                "right": right,
                "shared_items": len(shared),
                "agreements": agreements,
                "agreement_rate": _round(agreements / len(shared)) if shared else None,
            }
        )
    comparable = [row for row in pairs if row["shared_items"]]
    shared_total = sum(row["shared_items"] for row in comparable)
    return {
        "pairs": pairs,
        "micro_agreement_rate": _round(
            sum(row["agreements"] for row in comparable) / shared_total
        )
        if shared_total
        else None,
    }


def _streaks(correct: list[bool]) -> tuple[int, int]:
    current = 0
    for value in reversed(correct):
        if not value:
            break
        current += 1
    best = run = 0
    for value in correct:
        run = run + 1 if value else 0
        best = max(best, run)
    return current, best


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    xbar, ybar = _mean(xs), _mean(ys)
    numerator = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys))
    xden = sum((x - xbar) ** 2 for x in xs)
    yden = sum((y - ybar) ** 2 for y in ys)
    return numerator / math.sqrt(xden * yden) if xden and yden else None


def _mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def format_table(report: dict[str, Any]) -> str:
    lines = [
        f"Kid taste: {report['kids']} kids, {report['interaction_rows']} ratings, "
        f"{report['prediction_rows']} guesses",
        f"{'kid':<22} {'ratings':>7} {'like%':>7} {'guesses':>7} {'accuracy':>9} {'best':>5} {'r':>8}",
    ]
    for profile in report["profiles"]:
        like_rate = profile["like_rate"]
        accuracy = profile["predictions"]["accuracy"]
        correlation = profile["scorer_agreement"]["pearson"]
        lines.append(
            f"{profile['kid']:<22.22} {profile['interactions']:>7} "
            f"{_pct(like_rate):>7} {profile['predictions']['n']:>7} "
            f"{_pct(accuracy):>9} {profile['predictions']['best_streak']:>5} "
            f"{_display(correlation):>8}"
        )
    caveat = report["namespace_caveat"]
    lines.append(
        f"Prediction namespace: {caveat['definite_missing_market']} definite bad IDs; "
        f"{caveat['unverifiable_legacy']} legacy/unverifiable"
    )
    return "\n".join(lines)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _display(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON export containing Play rows")
    parser.add_argument("--json", action="store_true", help="Emit full JSON report")
    parser.add_argument("--output", help="Write full JSON report to this path")
    args = parser.parse_args()
    report = analyze(asyncio.run(load_rows(args.input)))
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2) if args.json else format_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
