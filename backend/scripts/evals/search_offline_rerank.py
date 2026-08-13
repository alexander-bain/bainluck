"""Apply the tier-lexicographic scorer to CAPTURED producer output (ruling 041).

Why this exists, and what it is honestly worth
----------------------------------------------
The gold-set instrument is end-to-end: ``search_results_producer`` fetches
``/api/events/typeahead`` from production, ``search_gold_eval`` grades the
answer. A ranking change therefore cannot be measured until it is DEPLOYED, and
a program lane never pushes. That leaves a real gap between "the scorer is
written" and "the number moved", and the gap is where unfalsifiable claims live.

This closes it partially and says exactly how partially. It re-ranks the
candidate list each probe already returned, using the same
``app.utils.search_match_class`` the endpoint now uses, and emits a
producer-shaped file the unmodified scorer can grade. Same probes, same
instrument, same grader.

**It is a PROJECTION, not a measurement, and it is biased LOW.** Two reasons,
both structural:

1. It can only reorder candidates the OLD assembly already admitted. The old
   assembly sliced every pool before merging (1 hub, 1 team, 2 events, 1
   concept, 2 markets), so a correct answer that the slot rule cut is invisible
   here and will stay a failure in the projection even though the deployed
   scorer would rank it first.
2. The captured rows carry no aliases, no outcomes and no `_derived` flag, so
   MC0-by-alias, MC4 and the owned-evidence exclusion are all UNAVAILABLE. Every
   one of those can only IMPROVE the real result relative to this.

So: a projection number here is a floor. Quote it as a floor, label it a
projection, and replace it with the deployed measurement when the branch lands.

Usage
-----
    python scripts/evals/search_offline_rerank.py \\
        --in /tmp/typeahead_base.json --out /tmp/typeahead_reranked.json
    python scripts/evals/search_gold_eval.py \\
        --registry scripts/evals/search_gold_probes.json --split test \\
        --results /tmp/typeahead_reranked.json --mode entity_top_1
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.utils.search_match_class import Evidence, rank  # noqa: E402

#: Producer `item_type`/`surface` -> the scorer's kind vocabulary.
_KIND = {
    "futures": "futures",
    "market": "futures",
    "concept": "event_concept",
    "event_concept": "event_concept",
    "event": "event",
    "hub": "hub",
    "team": "team",
}


def rerank_probe(probe: dict) -> dict:
    candidates = probe.get("candidates") or []
    if not candidates:
        return probe

    pairs = []
    for c in candidates:
        kind = _KIND.get(
            (c.get("item_type") or c.get("surface") or "").lower(), "futures"
        )
        pairs.append((
            Evidence(name=c.get("display_name") or "", kind=kind),
            c,
        ))

    ordered = rank(probe.get("query") or "", pairs)
    # `rank` drops only derived-only evidence, which the capture cannot express,
    # so nothing should vanish here. Assert it rather than assume it: a silent
    # drop would inflate the projection by removing a wrong answer the deployed
    # code would still have to beat.
    assert len(ordered) == len(candidates), (
        f"{probe.get('probe_key')}: {len(candidates)} in, {len(ordered)} out"
    )

    out = dict(probe)
    out["candidates"] = [
        {**c, "rank": i + 1} for i, c in enumerate(ordered)
    ]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    args = ap.parse_args()

    doc = json.load(open(args.src))
    doc["results"] = [rerank_probe(p) for p in doc.get("results", [])]
    meta = dict(doc.get("metadata") or {})
    meta["reranked_by"] = "app.utils.search_match_class (ruling 041)"
    meta["projection"] = (
        "PROJECTION, biased LOW: reorders only candidates the pre-scorer slot "
        "assembly already admitted, and the capture carries no aliases, "
        "outcomes or derived flags. Not a deployed measurement."
    )
    doc["metadata"] = meta
    json.dump(doc, open(args.dst, "w"), indent=1)

    moved = sum(
        1 for p in doc["results"]
        if (p.get("candidates") or [{}])[0].get("entity_id")
    )
    print(json.dumps({"probes": len(doc["results"]), "with_top": moved}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
