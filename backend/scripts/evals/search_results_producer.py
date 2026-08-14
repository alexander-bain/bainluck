"""Produce ranked Search results for ``search_gold_eval.py`` to grade.

``search_gold_eval.py`` is a *scorer*: it grades ``{probe_key: [ranked rows]}``
that someone else fetched. Nothing in the repo fetched them, so no baseline had
ever been produced. This module is that missing half (queue 313, item 3).

THE ADAPTER IS THE HONEST PART
------------------------------
The scorer reads ``entity_id``, ``surface`` and ``item_type`` off each ranked
row. The production Search API emits **none of those names**, so a mapping is
required, and a mapping is a place where a baseline can be quietly invented.
Two decisions therefore get stated here rather than buried:

1. **The source is ``GET /api/events/typeahead``, not ``GET /api/events/search``.**
   ``/search`` answers with *parallel buckets* (``teams``, ``event_concepts``,
   ``results``, ``futures``, ``futures_families``) and no cross-bucket order. To
   score "top-1" against it, this adapter would have to invent a merge order
   across those buckets — and that invented order, not Search, would decide
   every top-1 in the table. ``/typeahead`` already returns ONE ranked
   ``suggestions`` list, so rank 1 is a fact the API asserts, not one we impose.
   It is also the Instant Answers surface itself (the search bar), which is what
   the gold set is a baseline for.

2. **``entity_id`` is built from the identifier the API already returns for that
   suggestion type** (``team_slug``, ``event_id``, ``event_key``, ``market_id``,
   ``competition``) — never from display text, and never minted here. If a
   suggestion type ever arrives without its stable id, the row is emitted with
   an explicit ``unresolved:`` id rather than a guess, so it can never
   accidentally equal an expected id and score a pass.

Usage
-----
    python scripts/evals/search_results_producer.py \
        --registry scripts/evals/search_gold_probes.json --split test \
        --out /tmp/results.json

    # exploration: newline-delimited queries, no registry needed
    python scripts/evals/search_results_producer.py \
        --queries-file /tmp/queries.txt --out /tmp/explore.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from .probe_registry import filter_probes, load_registry
except ImportError:  # Direct ``python scripts/evals/search_results_producer.py`` use.
    from probe_registry import filter_probes, load_registry

DEFAULT_API = "https://api.bainluck.com"
#: v2 preserves the ranking EVIDENCE alongside the identity mapping. v1 captures
#: are still readable by every consumer; they simply carry no evidence, and the
#: reranker labels a run built from one as `legacy` fidelity rather than
#: pretending it reproduces production (LAT-P050).
ADAPTER_VERSION = "typeahead-adapter/v2"

# suggestion ``type`` -> (id field, entity_id prefix, surface, item_type).
# Every entry maps to an identifier the API itself returns. Display text is
# never used as identity.
TYPE_MAP: dict[str, tuple[str, str, str, str]] = {
    "team": ("team_slug", "team", "team", "team"),
    "event": ("event_id", "event", "event", "event"),
    "event_concept": ("event_key", "concept", "concept", "concept"),
    "futures": ("market_id", "market", "market", "futures"),
    "hub": ("competition", "hub", "hub", "hub"),
}


def map_suggestion(
    suggestion: dict[str, Any],
    rank: int,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map one typeahead suggestion onto the scorer's row shape.

    `suggestion` is preserved VERBATIM under ``suggestion`` and, when the
    endpoint was asked for it, the evidence it ranked on under ``evidence``.

    Both are new in v2 and both are the same lesson. The v1 row kept five keys —
    ``entity_id``, ``surface``, ``item_type``, ``rank``, ``display_name`` — which
    is everything the GRADER reads and nothing the SCORER reads. So the offline
    reranker, handed a v1 row, could only invent evidence from display text, and
    a projection built on invented evidence was published as a floor and missed
    its band by 7. A capture that discards the inputs to the thing it is
    projecting is not a cheaper capture; it is a different experiment.
    """

    kind = suggestion.get("type")
    mapping = TYPE_MAP.get(kind)
    if mapping is None:
        # An unmapped type is reported as unresolved rather than coerced: a
        # coerced id could collide with a real expected id and score a pass.
        row = {
            "entity_id": f"unresolved:unmapped_type:{kind}",
            "surface": str(kind),
            "item_type": str(kind),
            "rank": rank,
            "display_name": suggestion.get("text"),
        }
    else:
        id_field, prefix, surface, item_type = mapping
        raw_id = suggestion.get(id_field)
        entity_id = (
            f"{prefix}:{raw_id}"
            if raw_id not in (None, "")
            else f"unresolved:{kind}:missing_{id_field}"
        )
        row = {
            "entity_id": entity_id,
            "surface": surface,
            "item_type": item_type,
            "rank": rank,
            "display_name": suggestion.get("text"),
        }
    row["suggestion"] = suggestion
    if evidence is not None:
        row["evidence"] = evidence
    return row


def fetch_typeahead(
    query: str, *, api: str, timeout: float, debug_evidence: bool = True
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """Fetch one typeahead answer as ``(suggestions, evidence_or_None)``.

    ``evidence`` is None when the endpoint did not return it — an older deploy
    that predates the echo. That is reported as reduced fidelity, never silently
    filled in: an absent echo and an echo of empty evidence must not read the
    same (gotcha #53).
    """
    url = f"{api.rstrip('/')}/api/events/typeahead?q={urllib.parse.quote(query)}"
    if debug_evidence:
        url += "&debug_evidence=1"
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - fixed host
        payload = json.load(response)
    suggestions = payload.get("suggestions")
    if not isinstance(suggestions, list):
        raise ValueError(f"SEARCH_SOURCE_INVALID: no suggestions list for {query!r}")
    return suggestions, aligned_evidence(payload, suggestions)


def aligned_evidence(
    payload: dict[str, Any], suggestions: list[dict[str, Any]]
) -> list[dict[str, Any]] | None:
    """The echo, but only if it is positionally alignable. Otherwise None.

    Positional alignment is the ENTIRE contract of `_evidence`. A length
    mismatch means the pairing is unknowable, so the whole echo is dropped
    rather than zipped into a plausible-looking lie — a misaligned echo is worse
    than no echo, because it would be labelled `exact` and believed.
    """
    evidence = payload.get("_evidence")
    if not isinstance(evidence, list) or len(evidence) != len(suggestions):
        return None
    return evidence


def produce(
    items: list[tuple[str, str]],
    *,
    api: str,
    sleep: float,
    timeout: float,
    retries: int = 2,
    debug_evidence: bool = True,
) -> dict[str, Any]:
    """Run each ``(probe_key, query)`` against Search and map the ranked rows.

    A fetch that fails after ``retries`` is recorded with ``error`` set and NO
    candidates. That is deliberately distinguishable from a real empty result:
    an empty 200 and a failed call must never read the same (gotcha #53).
    """

    rows: list[dict[str, Any]] = []
    evidence_probes = 0
    for index, (probe_key, query) in enumerate(items):
        error: str | None = None
        suggestions: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] | None = None
        for attempt in range(retries + 1):
            try:
                suggestions, evidence = fetch_typeahead(
                    query, api=api, timeout=timeout, debug_evidence=debug_evidence
                )
                error = None
                break
            except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                error = f"{type(exc).__name__}: {exc}"
                if attempt < retries:
                    time.sleep(sleep * (attempt + 2))
        if evidence is not None:
            evidence_probes += 1
        row: dict[str, Any] = {
            "probe_key": probe_key,
            "query": query,
            "has_evidence": evidence is not None,
            "candidates": [
                map_suggestion(
                    item,
                    rank,
                    evidence[rank - 1] if evidence is not None else None,
                )
                for rank, item in enumerate(suggestions, 1)
                if isinstance(item, dict)
            ],
        }
        if error is not None:
            row["error"] = error
            row["fetch_ok"] = False
        else:
            row["fetch_ok"] = True
        rows.append(row)
        if index + 1 < len(items):
            time.sleep(sleep)
    fetched = sum(1 for row in rows if row.get("fetch_ok"))
    if not debug_evidence:
        fidelity = "legacy"
    elif evidence_probes == fetched and fetched:
        fidelity = "exact"
    elif evidence_probes:
        fidelity = "partial"
    else:
        fidelity = "legacy"
    return {
        "metadata": {
            "adapter_version": ADAPTER_VERSION,
            "source": f"{api.rstrip('/')}/api/events/typeahead",
            "probes": len(rows),
            "fetch_ok": fetched,
            "fetch_failed": len(rows) - fetched,
            # How much of what the scorer ranked on this capture actually holds.
            # `exact` = every fetched probe carries the endpoint's own echo, so a
            # rerank reproduces production's evidence. `legacy` = none does, and
            # any projection from it is a different experiment wearing the same
            # filename. Consumers must branch on this, not on presence.
            "evidence_fidelity": fidelity,
            "evidence_probes": evidence_probes,
            "debug_evidence_requested": bool(debug_evidence),
        },
        "results": rows,
    }


def _registry_items(registry: str, split: str) -> list[tuple[str, str]]:
    probes = filter_probes(load_registry(registry), task_type="search_entity", split=split)
    items: list[tuple[str, str]] = []
    for probe in probes:
        query = (probe.get("presentation") or {}).get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                f"SEARCH_PROBE_QUERY_MISSING: {probe['identity']['probe_key']} has no presentation.query"
            )
        items.append((probe["identity"]["probe_key"], query))
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry")
    parser.add_argument("--split", choices=("train", "tune", "test", "canary"), default="test")
    parser.add_argument("--queries-file", help="exploration mode: newline-delimited queries")
    parser.add_argument("--out", required=True)
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--sleep", type=float, default=1.1, help="seconds between calls (public API is 60/min)")
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument(
        "--no-evidence",
        action="store_true",
        help=(
            "Capture without the endpoint's evidence echo (v1 behaviour). "
            "Only for reproducing a legacy capture — the result cannot be "
            "reranked faithfully and is labelled `legacy` fidelity."
        ),
    )
    args = parser.parse_args()

    if bool(args.registry) == bool(args.queries_file):
        parser.error("supply exactly one of --registry or --queries-file")

    if args.registry:
        items = _registry_items(args.registry, args.split)
    else:
        queries = [
            line.strip()
            for line in Path(args.queries_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        items = [(f"explore-{index:03d}", query) for index, query in enumerate(queries, 1)]

    payload = produce(
        items,
        api=args.api,
        sleep=args.sleep,
        timeout=args.timeout,
        debug_evidence=not args.no_evidence,
    )
    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    meta = payload["metadata"]
    print(json.dumps(meta, indent=2))
    return 1 if meta["fetch_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
