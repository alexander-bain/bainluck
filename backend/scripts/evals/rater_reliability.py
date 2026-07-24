"""Compute rater agreement and score synthetic or registered known-answer probes."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from .calibrate_interestingness import load_rows, verdict_label
except ImportError:  # Direct ``python scripts/evals/rater_reliability.py`` execution.
    from calibrate_interestingness import load_rows, verdict_label


def agreement_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_item: dict[str, list[tuple[str, int]]] = defaultdict(list)
    probe_scores: dict[str, list[bool]] = defaultdict(list)
    for index, row in enumerate(rows):
        label = verdict_label(row)
        if label is None:
            continue
        rater = str(row.get("reviewer") or row.get("rater") or "unknown")
        item = str(row.get("item_id") or row.get("market_id") or row.get("id") or index)
        by_item[item].append((rater, label))
        answer = row.get("known_answer")
        if answer not in (None, ""):
            expected = verdict_label({"label": answer})
            if expected is not None:
                probe_scores[rater].append(label == expected)
    rater_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"judgments": 0, "agreements": 0, "shared": 0})
    pair_counts: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for judgments in by_item.values():
        majority = Counter(label for _, label in judgments).most_common(1)[0][0]
        for rater, label in judgments:
            rater_stats[rater]["judgments"] += 1
            if len(judgments) > 1:
                rater_stats[rater]["shared"] += 1
                rater_stats[rater]["agreements"] += label == majority
        for i, (left, left_label) in enumerate(judgments):
            for right, right_label in judgments[i + 1:]:
                pair_counts[tuple(sorted((left, right)))].append(left_label == right_label)
    for rater, stats in rater_stats.items():
        stats["majority_agreement"] = stats["agreements"] / stats["shared"] if stats["shared"] else None
        probes = probe_scores.get(rater, [])
        stats["probe_accuracy"] = sum(probes) / len(probes) if probes else None
        stats["probe_count"] = len(probes)
    return {"raters": dict(rater_stats), "pairwise": {" vs ".join(pair): {"shared": len(values), "agreement": sum(values) / len(values)} for pair, values in sorted(pair_counts.items())}}


def inject_probes(rows: list[dict[str, Any]], registry: list[dict[str, Any]], every: int) -> list[dict[str, Any]]:
    if every <= 0 or not registry:
        return rows
    output, probe_index = [], 0
    for index, row in enumerate(rows, 1):
        output.append(row)
        if index % every == 0:
            probe = dict(registry[probe_index % len(registry)])
            probe["is_probe"] = True
            probe["probe_id"] = probe.get("probe_id") or probe.get("id")
            output.append(probe)
            probe_index += 1
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--probe-registry")
    parser.add_argument("--inject-every", type=int, default=0)
    parser.add_argument("--write-injected")
    args = parser.parse_args()
    rows = load_rows(args.input)
    if args.probe_registry:
        rows = inject_probes(rows, load_rows(args.probe_registry), args.inject_every)
    if args.write_injected:
        Path(args.write_injected).write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(agreement_report(rows), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
