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


#: entity-id prefix -> the response bucket that answer must arrive in. Derived
#: from ``BUCKET_MAP`` so the two cannot drift.
PREFIX_TO_BUCKET: dict[str, str] = {
    prefix: bucket for bucket, (_, prefix, _, _) in BUCKET_MAP.items()
}


def expected_bucket(entity_id: str | None) -> str | None:
    """Which bucket the probe's answer has to come back in, or None if unknown."""

    if not isinstance(entity_id, str) or ":" not in entity_id:
        return None
    return PREFIX_TO_BUCKET.get(entity_id.split(":", 1)[0])


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
    # LAT-P118: an eval pass is not a person. Without this header every probe
    # writes a `search_query_logs` row and votes in the 40-slot warm head the
    # `typeahead_warmer` elects — measured putting a probe term in slot 40 of 40.
    request = urllib.request.Request(url, headers={"X-Bainluck-Origin": "harness"})
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed host
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
    items: list[tuple[str, str]] | list[tuple[str, str, str | None]],
    *,
    api: str,
    sleep: float,
    timeout: float,
    retries: int = 2,
    repeat: int = 1,
) -> dict[str, Any]:
    """Run each ``(probe_key, query[, expected_bucket])`` against /search and map every bucket.

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

    LAT-P037: SO IS AN EMPTY EXPECTED BUCKET, and the omission is worth naming.
    This module's own docstring opens with "the gate exists to prevent the
    ``f98d8104`` revert, and that revert was /search's futures bucket emptying" —
    and then it recorded ``bucket_sizes`` and never looked at them. Nothing here
    could tell an empty bucket from a bad ranking; both arrive as one absent id,
    and one of them is an outage. LAT-P035 was reverted for emptying that same arm
    at two characters, so the instrument has now missed the specific failure it
    was built for twice.

    ``empty_expected_bucket`` is that check: the probe's answer is a market, the
    ``futures`` bucket came back with zero rows, and the fetch SUCCEEDED. That is
    not a miss, it is HTTP 200 with the primary results missing — the exact
    ``f98d8104`` signature — and it is reported separately from a miss rather than
    averaged into one recall number (gotcha #53: an empty answer and no answer
    must never read the same).
    """

    rows: list[dict[str, Any]] = []
    normalised: list[tuple[str, str, str | None, str | None]] = [
        (
            item[0],
            item[1],
            item[2] if len(item) > 2 else None,
            item[3] if len(item) > 3 else None,
        )
        for item in items
    ]
    pending = len(normalised) * max(1, repeat)
    for probe_key, query, want_bucket, failure_status in normalised:
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
            if want_bucket:
                row["expected_bucket"] = want_bucket
                empty = row["bucket_sizes"].get(want_bucket) == 0
                row["empty_expected_bucket"] = empty
                # A probe DECLARED xfail is known-broken and unambiguous, and for
                # some of them the empty bucket IS the declared breakage — the
                # wedding query is 57 characters, /typeahead's max_length is 50, so
                # /search answers with an empty 200 by design of the bug. Measured
                # on production 2026-08-11 (v3777) it is the ONLY empty expected
                # bucket in the 46-probe set, so failing the run on it would leave
                # the check permanently red, and a permanently red check is one
                # nobody reads. It is still reported, under its own key.
                if empty and failure_status == "xfail":
                    row["empty_expected_bucket"] = False
                    row["empty_expected_bucket_declared"] = True
            # LAT-P038/#1769: the SIBLING verdict — a bucket that is not empty
            # and is still wrong, because rows were merged away rather than
            # never found.
            #
            # `president` returned ONE market while 461 open ones matched, and
            # `search-gold-president-001` PASSED throughout, because 112897 was
            # the row that survived. Recall asks "is the answer present" and
            # cannot ask "and nothing else was deleted" — so collapse is a
            # separate verdict, not a term in the recall score (gotcha #53).
            #
            # Read from the server, never inferred from bucket size. A one-row
            # bucket is legitimate for a narrow query (`tush push` returns one
            # market and is CORRECT), and from out here the two are identical
            # responses; the candidate count that tells them apart exists only
            # inside the request. /search reports `futures_collapse` when its
            # candidate window was saturated and the page still came up short.
            collapse = payload.get("futures_collapse")
            row["bucket_collapse"] = bool(collapse)
            if collapse:
                row["bucket_collapse_detail"] = collapse

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
    emptied = [row["probe_key"] for row in rows if row.get("empty_expected_bucket")]
    declared_empty = [
        row["probe_key"] for row in rows if row.get("empty_expected_bucket_declared")
    ]
    collapsed = [row["probe_key"] for row in rows if row.get("bucket_collapse")]
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
            "empty_expected_bucket": len(emptied),
            "empty_expected_bucket_probes": emptied,
            "empty_expected_bucket_declared_probes": declared_empty,
            "bucket_collapse": len(collapsed),
            "bucket_collapse_probes": collapsed,
        },
        "results": rows,
    }


def _registry_items(registry: str, split: str) -> list[tuple[str, str, str | None]]:
    probes = filter_probes(load_registry(registry), task_type="search_entity", split=split)
    items: list[tuple[str, str, str | None]] = []
    for probe in probes:
        query = (probe.get("presentation") or {}).get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                f"SEARCH_PROBE_QUERY_MISSING: {probe['identity']['probe_key']} has no presentation.query"
            )
        want = expected_bucket(
            ((probe.get("oracle") or {}).get("answer") or {}).get("expected_entity_id")
        )
        status = (probe.get("lifecycle") or {}).get("known_failure_status")
        items.append((probe["identity"]["probe_key"], query, want, status))
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
        # Exploration mode has no registry and therefore no expected answer, so
        # there is no bucket to call empty. It gets None rather than a guess.
        items = [(f"explore-{index:03d}", query, None) for index, query in enumerate(queries, 1)]

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
    # Always printed, never only inside a mode flag. An empty expected bucket is
    # the f98d8104 signature (HTTP 200, primary results missing) and the number a
    # skimmer reads must carry it.
    print(f"SEARCH BUCKET EMPTY-EXPECTED: {meta['empty_expected_bucket']}")
    for probe_key in meta["empty_expected_bucket_probes"]:
        print(f"  EMPTY EXPECTED BUCKET: {probe_key}")
    for probe_key in meta["empty_expected_bucket_declared_probes"]:
        print(f"  empty expected bucket (declared xfail, not counted): {probe_key}")
    # Printed on its own line for the same reason as the one above, and FAILS the
    # run for the same reason: this module has twice recorded a signal and never
    # read it. The exit policy is measured, not assumed — over the real compiled
    # predicate against production 2026-08-11, with the #1769 dedup fix applied,
    # collapse fires on 0 of the 46 gold queries, so a non-zero count is a
    # regression rather than a standing red.
    print(f"SEARCH BUCKET COLLAPSE: {meta['bucket_collapse']}")
    for probe_key in meta["bucket_collapse_probes"]:
        print(f"  BUCKET COLLAPSED: {probe_key}")
    return 1 if (
        meta["fetch_failed"]
        or meta["flapping"]
        or meta["empty_expected_bucket"]
        or meta["bucket_collapse"]
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
