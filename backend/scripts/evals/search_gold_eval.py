"""Offline search gold-set evaluator using a local serialized candidate corpus.

The gold markdown is parsed from both the coverage and real-history halves. A
corpus JSON contains surfaces with ``name``, ``surface`` and optional ``volume``.
Production concept detectors and futures reranking are imported when available.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

REAL_CLASSES = {
    "Golf": "category_as_query", "MLB": "category_as_query", "tush push": "concept_rule",
    "Taylor Swift Madison": "qualified_entity", "Where will Taylor Swift and Travis Kelce's Wedding occur?": "full_question",
    "us open": "ambiguity", "fable": "self_reference",
}


def parse_gold_markdown(path: str | Path) -> list[dict[str, str]]:
    text = Path(path).read_text(encoding="utf-8").replace("\xa0", " ")
    rows: list[dict[str, str]] = []
    before_real, _, real = text.partition("## THE REAL HALF")
    family = "coverage"
    for line in before_real.splitlines():
        match = re.match(r"^([^:#]+):\s*(.+)$", line)
        if not match or line.startswith(("Source", "STATUS")):
            continue
        heading, body = match.groups()
        surface_match = re.search(r"\(([^)]+)\)\s*$", body)
        expected = surface_match.group(1).split("/")[0] if surface_match else "any"
        body = re.sub(r"\s*\([^)]+\)\s*$", "", body)
        family = heading.strip().lower().replace(" ", "_")
        rows.extend({"query": q.strip(" \"") , "class": family, "expected_surface": expected} for q in body.split(" · ") if q.strip())
    for heading in ("Native Recents", "Desktop Recents"):
        match = re.search(rf"^{heading}:\s*(.+)$", real, re.MULTILINE)
        if match:
            for query in match.group(1).split(" · "):
                query = query.strip(" \"")
                rows.append({"query": query, "class": REAL_CLASSES.get(query, "real_history"), "expected_surface": "any"})
    return rows


def load_corpus(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("items", data.get("rows", []))


def rank_local(query: str, corpus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.routes.events import _apply_search_synonyms, _rerank_search_futures, _strip_search_scaffolding

    terms = _strip_search_scaffolding(re.findall(r"[a-z0-9]+", query.lower()))
    expanded = _apply_search_synonyms([(term, None) for term in terms])
    tokens = {token for term, synonym in expanded for token in f"{term} {synonym or ''}".split()}
    candidates = []
    for item in corpus:
        haystack = " ".join(str(item.get(key, "")) for key in ("name", "aliases", "outcomes")).lower()
        overlap = len(tokens & set(re.findall(r"[a-z0-9]+", haystack)))
        phrase = query.lower().strip(" ?\"") in haystack
        if overlap:
            candidate = dict(item)
            candidate["_rank"] = (int(phrase), overlap / max(len(tokens), 1), float(item.get("volume") or 0))
            candidates.append(candidate)
    candidates.sort(key=lambda item: item["_rank"], reverse=True)
    futures = [item for item in candidates if item.get("surface") == "market"]
    if futures:
        objects = [SimpleNamespace(**item, llm_sport_category=item.get("category"), volume=item.get("volume", 0)) for item in futures]
        ordered = _rerank_search_futures(objects, expanded)
        order = {obj.name: index for index, obj in enumerate(ordered)}
        candidates.sort(key=lambda item: (item.get("surface") == "market", -order.get(item.get("name"), 999), item["_rank"]), reverse=True)
    return candidates


def evaluate(gold: list[dict[str, str]], corpus: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[bool]] = defaultdict(list)
    misses = []
    for row in gold:
        ranked = rank_local(row["query"], corpus)
        top = ranked[0] if ranked else None
        expected = row["expected_surface"]
        ok = top is not None and (expected == "any" or expected in str(top.get("surface", "")))
        buckets[row["class"]].append(ok)
        if not ok:
            misses.append({"query": row["query"], "expected_surface": expected, "actual_top_3": [{"name": x.get("name"), "surface": x.get("surface")} for x in ranked[:3]]})
    return {"total": len(gold), "top_1_rate": sum(map(sum, buckets.values())) / len(gold) if gold else 0, "per_class": {key: {"correct": sum(values), "total": len(values), "rate": sum(values) / len(values)} for key, values in sorted(buckets.items())}, "worst_misses": misses[:20]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = evaluate(parse_gold_markdown(args.gold), load_corpus(args.corpus))
    print(json.dumps(report, indent=2))
    return 1 if report["top_1_rate"] < 1 else 0


if __name__ == "__main__":
    raise SystemExit(main())
