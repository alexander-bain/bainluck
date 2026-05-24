#!/usr/bin/env python3
"""Analyze ranking judgments to diagnose scorer calibration.

Usage:
    python3 scripts/analyze_ranking_judgments.py [--since YYYY-MM-DD] [--export path.csv]

Reads from the ranking_judgments table and produces:
1. Score-by-label report (are love items scoring highest?)
2. Reason tag frequency (what's the most common complaint?)
3. Pairwise violations (love items ranked below bad items)
4. Category quality map (which categories are mis-ranked?)
"""

import argparse
import asyncio
import csv
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def main():
    parser = argparse.ArgumentParser(description="Analyze ranking judgments")
    parser.add_argument("--since", type=str, help="Only include judgments since this date")
    parser.add_argument("--export", type=str, help="Export to CSV path")
    args = parser.parse_args()

    from sqlalchemy import select, func
    from app.models.models import RankingJudgment
    from app.services.database import async_session_factory
    from app.utils.discover_reason_tags import canonical_reason_tags

    async with async_session_factory() as db:
        q = select(RankingJudgment).order_by(RankingJudgment.created_at)
        if args.since:
            q = q.where(RankingJudgment.date >= date.fromisoformat(args.since))

        rows = (await db.execute(q)).scalars().all()

    if not rows:
        print("No judgments found.")
        return

    print(f"\n{'='*60}")
    print(f"  RANKING JUDGMENTS ANALYSIS — {len(rows)} judgments")
    print(f"{'='*60}\n")

    # 1. Score by label
    label_scores: dict[str, list[float]] = {}
    for r in rows:
        if r.score_at_review is not None:
            label_scores.setdefault(r.label, []).append(r.score_at_review)

    print("1. SCORE BY LABEL")
    print(f"{'Label':<8} {'Count':>6} {'Mean':>8} {'Min':>8} {'Max':>8}")
    print("-" * 42)
    for label in ["love", "fine", "bad", "kill"]:
        scores = label_scores.get(label, [])
        if scores:
            mean = sum(scores) / len(scores)
            print(f"{label:<8} {len(scores):>6} {mean:>8.1f} {min(scores):>8.1f} {max(scores):>8.1f}")
        else:
            print(f"{label:<8} {0:>6} {'—':>8} {'—':>8} {'—':>8}")

    # Check if scorer is calibrated (love should score highest)
    love_avg = sum(label_scores.get("love", [0])) / max(len(label_scores.get("love", [1])), 1)
    bad_avg = sum(label_scores.get("bad", [0])) / max(len(label_scores.get("bad", [1])), 1)
    if love_avg < bad_avg:
        print("\n  ⚠️  MISCALIBRATED: 'love' items avg lower than 'bad' items!")
    elif love_avg > 0:
        print(f"\n  ✓ Calibrated: love ({love_avg:.1f}) > bad ({bad_avg:.1f})")

    # 2. Reason tag frequency
    tag_counts: dict[str, int] = {}
    tag_labels: dict[str, dict[str, int]] = {}
    for r in rows:
        for tag in canonical_reason_tags(r.reason_tags):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            tag_labels.setdefault(tag, {})
            tag_labels[tag][r.label] = tag_labels[tag].get(r.label, 0) + 1

    print(f"\n2. REASON TAGS ({len(tag_counts)} unique)")
    print(f"{'Tag':<16} {'Count':>6} {'Top Label':<10}")
    print("-" * 36)
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        top_label = max(tag_labels[tag].items(), key=lambda x: x[1])[0]
        print(f"{tag:<16} {count:>6} {top_label:<10}")

    # 3. Pairwise violations
    pairwise = [r for r in rows if r.better_than or r.worse_than]
    print(f"\n3. PAIRWISE COMPARISONS: {len(pairwise)} recorded")
    for r in pairwise[:10]:
        if r.better_than:
            print(f"  '{r.market_name}' should beat '{r.better_than}'")
        if r.worse_than:
            print(f"  '{r.market_name}' should lose to '{r.worse_than}'")

    # 4. Category quality map
    cat_labels: dict[str, dict[str, int]] = {}
    for r in rows:
        cat = r.category_at_review or "unknown"
        cat_labels.setdefault(cat, {})
        cat_labels[cat][r.label] = cat_labels[cat].get(r.label, 0) + 1

    print(f"\n4. CATEGORY QUALITY MAP")
    print(f"{'Category':<16} {'Love':>6} {'Fine':>6} {'Bad':>6} {'Kill':>6}")
    print("-" * 46)
    for cat, labels in sorted(cat_labels.items(), key=lambda x: -sum(x[1].values())):
        print(f"{cat:<16} {labels.get('love', 0):>6} {labels.get('fine', 0):>6} {labels.get('bad', 0):>6} {labels.get('kill', 0):>6}")

    # Export
    if args.export:
        with open(args.export, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "date", "surface", "rank_seen", "item_type", "market_id",
                "market_name", "label", "reason_tags", "better_than", "worse_than",
                "notes", "score_at_review", "category_at_review", "reviewer",
            ])
            for r in rows:
                writer.writerow([
                    r.date, r.surface, r.rank_seen, r.item_type, r.market_id,
                    r.market_name, r.label, ",".join(canonical_reason_tags(r.reason_tags)),
                    r.better_than, r.worse_than, r.notes, r.score_at_review,
                    r.category_at_review, r.reviewer,
                ])
        print(f"\nExported {len(rows)} judgments to {args.export}")


if __name__ == "__main__":
    asyncio.run(main())
