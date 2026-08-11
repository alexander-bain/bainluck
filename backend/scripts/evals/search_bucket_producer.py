"""Produce PER-BUCKET ``GET /api/events/search`` results for ``search_gold_eval.py``.

This is the second producer. ``search_results_producer.py`` fetches
``/api/events/typeahead`` and is graded on TOP-1; this one fetches
``/api/events/search`` and is graded on per-bucket RECALL
(``search_gold_eval.evaluate_bucket_recall``). Both are needed, for a reason that
is worth stating plainly rather than leaving to be rediscovered:

**The gate exists to prevent the ``f98d8104`` revert, and that revert was
/search's futures bucket emptying.** LAT-P002 shipped a 4s statement timeout;
post-deploy, three of eight sampled queries returned HTTP 200 with ZERO futures
and ``degraded=['futures']``. A gate that only ever calls /typeahead cannot see
that failure, however well it grades.

WHY THIS DOES NOT INVENT A MERGE ORDER
--------------------------------------
``search_results_producer`` refused to grade /search precisely because /search
answers with parallel buckets (``teams``, ``event_concepts``, ``results``,
``futures``, ``futures_families``) and asserts no order across them — so any
top-1 would be the ADAPTER's opinion, not Search's. That refusal was correct and
is preserved here: this producer emits no cross-bucket rank at all. Every row
carries the ``bucket`` it came from, and the scorer asks only whether the bucket
that should hold the answer contained it. Rank WITHIN a bucket is recorded
because Search does assert it, but nothing grades on it today.

``futures_families`` is deliberately not mapped: it is a presentation grouping
over markets that are already in the flat ``futures`` list (verified live
2026-08-10 — every family member id was a subset of flat ``futures``), so mapping
it would double-count the same market under two identities.

Identity is taken from the id field the API already returns for that bucket,
never minted from display text — the same rule ``search_results_producer``
follows, and for the same reason: a coerced id can collide with a real expected
id and score a false pass.

Usage
-----
    python scripts/evals/search_bucket_producer.py \
        --registry scripts/evals/search_gold_probes.json --split test \
        --out /tmp/search_buckets.json
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from .probe_registry import filter_probes, load_registry
except ImportError:  # Direct ``python scripts/evals/search_bucket_producer.py`` use.
    from probe_registry import filter_probes, load_registry

DEFAULT_API = "https://api.bainluck.com"
ADAPTER_VERSION = "search-bucket-adapter/v1"

# response bucket -> (id field, entity_id prefix, surface, item_type).
# The prefixes match ``search_results_producer.TYPE_MAP`` so one registry of
# expected ids grades against BOTH surfaces without translation.
BUCKET_MAP: dict[str, tuple[str, str, str, str]] = {
    "teams": ("slug", "team", "team", "team"),
    "results": ("id", "event", "event", "event"),
    "event_concepts": ("key", "concept", "concept", "concept"),
    "futures": ("id", "market", "market", "futures"),
}


def map_row(bucket: str, row: dict[str, Any], rank: int) -> dict[str, Any]:
    """Map one /search bucket row onto the scorer's row shape."""

    id_field, prefix, surface, item_type = BUCKET_MAP[bucket]
    raw_id = row.get(id_field)
    entity_id = (
        f"{prefix}:{raw_id}"
        if raw_id not in (None, "")
        else f"unresolved:{bucket}:missing_{id_field}"
    )
    return {
        "entity_id": entity_id,
        "bucket": bucket,
        "surface": surface,
        "item_type": item_type,
        "rank_in_bucket": rank,
        "display_name": row.get("name") or row.get("home_team"),
    }


def map_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten every mapped bucket into one candidate list, order not significant."""

    candidates: list[dict[str, Any]] = []
    for bucket in BUCKET_MAP:
        rows = payload.get(bucket)
        if not isinstance(rows, list):
            continue
        candidates.extend(
            map_row(bucket, row, rank)
            for rank, row in enumerate(rows, 1)
            if isinstance(row, dict)
        )
    return candidates


def fetch_search(query: str, *, api: str, timeout: float) -> dict[str, Any]:
    url = f"{api.rstrip('/')}/api/events/search?q={urllib.parse.quote(query)}"
    started = time.monotonic()
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - fixed host
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(f"SEARCH_SOURCE_INVALID: non-object response for {query!r}")
    payload["_elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return payload


def _bucket_id_signature(candidates: list[dict[str, Any]]) -> list[list[str]]:
    """The identity of a result, for stability comparison: bucket -> sorted ids.

    Deliberately ignores rank WITHIN a bucket. The scorer grades membership, so a
    reordering inside a bucket is not a change to the thing being measured, and
    flagging it would cry wolf on every run.
    """

    by_bucket: dict[str, set[str]] = {}
    for row in candidates:
        by_bucket.setdefault(str(row.get("bucket")), set()).add(str(row.get("entity_id")))
    return [[bucket, *sorted(ids)] for bucket, ids in sorted(by_bucket.items())]


def _fetch_once(
    query: str, *, api: str, timeout: float, sleep: float, retries: int
) -> tuple[dict[str, Any], str | None]:
    """One fetch with retries. Returns ``(payload, error)`` — never raises."""

    error: str | None = None
    for attempt in range(retries + 1):
        try:
            return fetch_search(query, api=api, timeout=timeout), None
        except urllib.error.HTTPError as exc:
            # Status is kept in the message: a 422 (the query the surface
            # refuses) and a 429 (rate limit) must stay tellable apart when
            # someone reads the unmeasured list.
            error = f"HTTPError {exc.code}: {exc.reason}"
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(sleep * (attempt + 2))
    return {}, error


def produce(
    items: list[tuple[str, str]],
    *,
    api: str,
    sleep: float,
    timeout: float,
    retries: int = 2,
    repeat: int = 1,
) -> dict[str, Any]:
    """Run each ``(probe_key, query)`` against /search and map every bucket.

    A fetch that fails after ``retries`` is recorded with ``error`` set, ``fetch_ok``
    False and NO candidates — never as an empty result (gotcha #53). The scorer
    reads both fields and reports the probe as unmeasured rather than as a miss.

    ``repeat`` > 1 re-runs every probe and reports whether the answer was STABLE
    (LAT-P035, Item 2). This exists because a score can be wrong in a way no
    single run can show:

    LAT-P034 measured bucket recall 39/44 -> 41/44 and found the 41st was not a
    fix. ``search-gold-red-sox-001`` had flipped because the teams bucket returned
    ``team:boston-red-sox`` on one run and ``team:boston-red-sox-mlb`` on the next
    — the two duplicate rows of #1754, alternating, with bucket size 2 both times.
    A +/-1 swing that no change to Search caused, reported as if it were one.

    The fix has two halves and this is the general one. The registry adjudicates
    THAT probe (both ids denote one club, so it is an ambiguity, not a coin flip);
    this reports ANY probe whose answer moves between runs, including ones nobody
    has noticed yet. A single run cannot distinguish "Search improved" from
    "Search is unstable and I sampled the good side", and the difference decides
    whether a queue's headline number means anything.

    Instability is a first-class failure: ``main`` exits non-zero on it, exactly as
    it does for a fetch failure, so a flapping gate can never read as a clean pass.
    """

    rows: list[dict[str, Any]] = []
    pending = len(items) * max(1, repeat)
    for probe_key, query in items:
        observations: list[dict[str, Any]] = []
        for _ in range(max(1, repeat)):
            payload, error = _fetch_once(
                query, api=api, timeout=timeout, sleep=sleep, retries=retries
            )
            observations.append({"payload": payload, "error": error})
            pending -= 1
            if pending > 0:
                time.sleep(sleep)

        # The FIRST observation is the graded one, so a single-run file and the
        # first run of a repeated file are byte-identical in the fields the
        # scorer reads. Repetition adds a verdict; it never changes the answer.
        first = observations[0]
        error = first["error"]
        payload = first["payload"]
        row: dict[str, Any] = {
            "probe_key": probe_key,
            "query": query,
            "candidates": [] if error is not None else map_response(payload),
        }
        if error is not None:
            row["error"] = error
            row["fetch_ok"] = False
        else:
            row["fetch_ok"] = True
            row["elapsed_ms"] = payload.get("_elapsed_ms")
            # `degraded` is how /search says a stage was shed. It is the direct
            # signal the LAT-P002 revert produced, so it is carried through to
            # the results file instead of being inferred from an empty bucket.
            row["degraded"] = payload.get("degraded") or []
            row["bucket_sizes"] = {
                bucket: len(payload.get(bucket) or []) for bucket in BUCKET_MAP
            }

        if repeat > 1:
            # A run that FAILED to fetch is not evidence of instability — it is
            # absence of evidence. Only successful observations are compared, and
            # a probe with fewer than two of them is reported as unverified
            # rather than as stable (gotcha #53: an empty answer and no answer
            # must never read the same).
            good = [o for o in observations if o["error"] is None]
            variants = [_bucket_id_signature(map_response(o["payload"])) for o in good]
            unique = [v for i, v in enumerate(variants) if v not in variants[:i]]
            row["stability"] = {
                "runs": len(observations),
                "compared": len(good),
                "verdict": (
                    "UNVERIFIED" if len(good) < 2
                    else "STABLE" if len(unique) == 1
                    else "FLAPPING"
                ),
            }
            if len(unique) > 1:
                row["stability"]["observed_variants"] = unique

        rows.append(row)
    fetched = sum(1 for row in rows if row.get("fetch_ok"))
    flapping = [
        row["probe_key"] for row in rows
        if (row.get("stability") or {}).get("verdict") == "FLAPPING"
    ]
    unverified = [
        row["probe_key"] for row in rows
        if (row.get("stability") or {}).get("verdict") == "UNVERIFIED"
    ]
    return {
        "metadata": {
            "adapter_version": ADAPTER_VERSION,
            "source": f"{api.rstrip('/')}/api/events/search",
            "probes": len(rows),
            "fetch_ok": fetched,
            "fetch_failed": len(rows) - fetched,
            "repeat": repeat,
            "flapping": len(flapping),
            "flapping_probes": flapping,
            "unverified_stability_probes": unverified,
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
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.6,
        help="seconds between calls; the public API is 60/min and a throttled "
             "response parses as a phantom zero-recall result",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="run every probe N times and report STABLE/FLAPPING per probe; "
             "exits non-zero on any flap (LAT-P035 — see produce.__doc__)",
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
        items, api=args.api, sleep=args.sleep, timeout=args.timeout, repeat=args.repeat
    )
    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    meta = payload["metadata"]
    print(json.dumps(meta, indent=2))
    if args.repeat > 1:
        # Printed as its own line, not buried in the JSON: the whole point is that
        # a reader who only skims cannot come away with a number that a flap made up.
        print(f"SEARCH BUCKET STABILITY: {meta['flapping']} flapping over {args.repeat} runs")
        for probe_key in meta["flapping_probes"]:
            print(f"  FLAPPING: {probe_key}")
    return 1 if (meta["fetch_failed"] or meta["flapping"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
