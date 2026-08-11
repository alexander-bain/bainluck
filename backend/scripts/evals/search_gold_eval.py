"""Offline entity-correct Search evaluator using C47's probe registry.

The legacy markdown parser remains available only to identify rows needing
migration. Scoring requires versioned Search probes with stable entity IDs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from .probe_registry import filter_probes, load_registry
except ImportError:  # Direct ``python scripts/evals/search_gold_eval.py`` use.
    from probe_registry import filter_probes, load_registry

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


class SearchGoldMigrationError(ValueError):
    """Raised when legacy gold lacks stable entity identity."""


# LAT-P029 (3a): the three states a probe can be in, kept SEPARATE.
#
# The producers already distinguish "the fetch failed" from "Search answered with
# nothing" — ``search_results_producer.produce`` sets ``error``/``fetch_ok`` and
# cites gotcha #53 by name for doing so. This loader used to read ``probe_key``
# and ``candidates`` and DISCARD both, so ``_score_probe`` saw an empty list and
# emitted ``NO_RESULTS``: a 422, a timeout, a rate-limit and a real recall miss
# were one indistinguishable number. Total failure is loud (the rate goes to 0.0);
# PARTIAL failure is the hazard — six flaky fetches move the headline and read as
# a code regression that nobody introduced.
#
# A fourth hole lived in ``evaluate_entity_probes``' ``results.get(key, [])``: a
# probe MISSING from the results file entirely also scored ``NO_RESULTS``. Truncate
# a producer run and the gate reported recall failures for probes it never ran.
#
# So: an unmeasured probe is never scored as a miss. It is reported as unmeasured,
# it is excluded from the rate's denominator, and it makes the run exit non-zero.
UNMEASURED_CODES = ("NOT_PRODUCED", "FETCH_FAILED")


def _normalize_record(value: Any) -> dict[str, Any]:
    """Accept either a producer record or a bare candidate list.

    A bare list is what synthetic/in-test callers pass and carries no fetch
    status; it is by definition a successful "these are the results" assertion.
    A producer record carries ``fetch_ok``/``error`` and is trusted over it.
    """

    if isinstance(value, list):
        return {"candidates": value, "fetch_ok": True, "error": None}
    if isinstance(value, dict):
        candidates = value.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("SEARCH_RESULTS_INVALID: candidates must be a list")
        return {
            "candidates": candidates,
            # Absent ``fetch_ok`` means the producer predates the field. Default
            # True rather than False: defaulting to "failed" would silently move
            # every legacy row out of the denominator and inflate the rate.
            "fetch_ok": bool(value.get("fetch_ok", True)),
            "error": value.get("error"),
        }
    raise ValueError("SEARCH_RESULTS_INVALID: expected a record or a candidate list")


def load_result_records(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load producer output, PRESERVING each row's fetch status.

    Replaces ``load_result_rows``, which returned candidates only. The rename is
    deliberate — a second loader that still drops the status is a second way to
    reintroduce the defect (the gotcha-#53 discipline: delete the path, do not
    deprecate it).
    """

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("results", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("SEARCH_RESULTS_INVALID: expected a result-row list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row.get("probe_key") if isinstance(row, dict) else None
        candidates = row.get("candidates") if isinstance(row, dict) else None
        if not isinstance(key, str) or not isinstance(candidates, list):
            raise ValueError("SEARCH_RESULTS_INVALID: probe_key and candidates are required")
        if key in result:
            raise ValueError(f"SEARCH_RESULTS_DUPLICATE: {key}")
        result[key] = _normalize_record(row)
    return result


def require_entity_gold(rows: list[dict[str, Any]]) -> None:
    """Reject legacy surface-only rows instead of recreating the old false green."""

    missing = [row.get("query", "<unknown>") for row in rows if not row.get("expected_entity_id")]
    if missing:
        raise SearchGoldMigrationError(
            "SEARCH_GOLD_MIGRATION_REQUIRED: stable expected_entity_id missing for "
            + ", ".join(sorted(missing))
        )


def _score_probe(probe: dict[str, Any], record: dict[str, Any] | None) -> dict[str, Any]:
    identity = probe["identity"]
    oracle = probe["oracle"]["answer"]
    lifecycle = probe["lifecycle"]
    key = identity["probe_key"]
    expected_ids = {oracle["expected_entity_id"], *oracle.get("allowed_entity_ids", [])}
    expected_surfaces = set(oracle["expected_surfaces"])
    expected_type = oracle["expected_item_type"]

    # LAT-P029 (3a): unmeasured is resolved BEFORE anything reads `candidates`,
    # so no unmeasured probe can fall through into a recall verdict.
    fetch_error: str | None = None
    if record is None:
        candidates: list[dict[str, Any]] = []
        unmeasured = "NOT_PRODUCED"
    elif not record.get("fetch_ok", True):
        candidates = []
        unmeasured = "FETCH_FAILED"
        fetch_error = record.get("error")
    else:
        candidates = record.get("candidates") or []
        unmeasured = ""

    top = candidates[0] if candidates else None
    expected_rank = next(
        (index for index, candidate in enumerate(candidates, 1) if candidate.get("entity_id") in expected_ids),
        None,
    )
    if unmeasured:
        code = unmeasured
    elif top is None:
        code = "NO_RESULTS"
    elif top.get("entity_id") not in expected_ids:
        code = "ENTITY_NOT_TOP"
    elif "any" not in expected_surfaces and top.get("surface") not in expected_surfaces:
        code = "SURFACE_MISMATCH"
    elif top.get("item_type") != expected_type:
        code = "TYPE_MISMATCH"
    else:
        code = "PASS"

    passed = code == "PASS"
    known = lifecycle["known_failure_status"]
    if unmeasured:
        # Never pass, never fail, never xfail. An unmeasured probe says nothing
        # about Search, so it must not be absorbed into a lifecycle verdict —
        # least of all `xfail`, which would let a broken fetch look EXPECTED.
        disposition = "unmeasured"
    elif known == "xfail":
        disposition = "xpass" if passed else "xfail"
    elif known == "fixed" and not passed:
        disposition = "regression"
    else:
        disposition = "pass" if passed else "fail"
    detail = {
        "probe_key": key,
        "probe_version": identity["probe_version"],
        "query_class": oracle["query_class"],
        "code": code,
        "disposition": disposition,
        "expected_rank": expected_rank,
        "reciprocal_rank": 1 / expected_rank if expected_rank else 0.0,
        "actual_top": None if top is None else {
            "entity_id": top.get("entity_id"),
            "surface": top.get("surface"),
            "item_type": top.get("item_type"),
        },
    }
    if unmeasured:
        detail["fetch_error"] = fetch_error
    return detail


def evaluate_entity_probes(
    probes: list[dict[str, Any]],
    results: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Score supplied ranked results against validated Search probes."""

    details = []
    seen_keys = set()
    for probe in sorted(probes, key=lambda row: (row["identity"]["probe_key"], row["identity"]["probe_version"])):
        if probe["identity"]["task_type"] != "search_entity":
            raise ValueError("SEARCH_TASK_TYPE_INVALID")
        key = probe["identity"]["probe_key"]
        if key in seen_keys:
            raise ValueError(f"SEARCH_PROBE_DUPLICATE: {key}")
        seen_keys.add(key)
        # LAT-P029 (3a): `.get(key)` with NO default. A missing key is a distinct
        # state (NOT_PRODUCED); the old `.get(key, [])` turned it into an empty
        # answer, so a truncated producer run reported recall misses for probes
        # that were never run.
        raw = results.get(key)
        details.append(_score_probe(probe, None if raw is None else _normalize_record(raw)))

    counts = {name: sum(row["disposition"] == name for row in details) for name in ("pass", "fail", "xfail", "xpass", "regression")}
    strict_passes = sum(row["code"] == "PASS" for row in details)
    # LAT-P029 (3a): rates are over MEASURED probes only, and `coverage` is what
    # says how much of the set that was. Reporting a rate over the full set would
    # charge Search for fetches that never happened; reporting it over the measured
    # subset WITHOUT coverage would let 4-of-44 measured show a beautiful number.
    # Both are published, and `main()` exits non-zero when coverage is not 1.0.
    measured = [row for row in details if row["code"] not in UNMEASURED_CODES]
    unmeasured = [row for row in details if row["code"] in UNMEASURED_CODES]
    by_class: dict[str, dict[str, int]] = {}
    for row in details:
        bucket = by_class.setdefault(row["query_class"], {"total": 0, "passed": 0})
        bucket["total"] += 1
        bucket["passed"] += row["code"] == "PASS"
    return {
        "total": len(details),
        "measured": len(measured),
        "unmeasured": len(unmeasured),
        "coverage": len(measured) / len(details) if details else 0.0,
        "unmeasured_probes": [
            {"probe_key": row["probe_key"], "code": row["code"], "fetch_error": row.get("fetch_error")}
            for row in unmeasured
        ],
        "entity_top_1_rate": strict_passes / len(measured) if measured else 0.0,
        "mean_reciprocal_rank": sum(row["reciprocal_rank"] for row in measured) / len(measured) if measured else 0.0,
        "lifecycle_counts": counts,
        "per_query_class": {key: by_class[key] for key in sorted(by_class)},
        "details": details,
    }


# ---------------------------------------------------------------------------
# LAT-P029 (3c): per-bucket recall against ``GET /api/events/search``.
#
# The entity scorer above grades TOP-1 against ``/typeahead``, and
# ``search_results_producer`` argues that choice well: /typeahead returns one
# ranked list, so rank 1 is the API's own assertion rather than a merge order the
# adapter invented across /search's parallel buckets. That reasoning is sound and
# is NOT overturned here.
#
# But the regression this gate exists to prevent — the ``f98d8104`` revert of
# LAT-P002 — was /search's FUTURES BUCKET EMPTYING under a new statement timeout.
# A gate that never calls /search structurally cannot see that. So /search is
# graded on the question it can answer honestly:
#
#     did the bucket that should hold the answer contain it AT ALL?
#
# Recall, not rank. No cross-bucket order is invented, because none is needed —
# each expected entity kind has exactly one bucket that can hold it. ``BUCKET_EMPTY``
# is split out from ``NOT_IN_BUCKET`` on purpose: an empty bucket is the revert's
# exact signature and reads very differently from "the bucket answered, wrongly".
BUCKET_FOR_KIND = {
    "team": "teams",
    "event": "results",
    "concept": "event_concepts",
    "market": "futures",
}
BUCKET_UNMEASURED_CODES = ("NOT_PRODUCED", "FETCH_FAILED", "BUCKET_UNSUPPORTED")


def _score_probe_bucket_recall(probe: dict[str, Any], record: dict[str, Any] | None) -> dict[str, Any]:
    identity = probe["identity"]
    oracle = probe["oracle"]["answer"]
    expected_ids = {oracle["expected_entity_id"], *oracle.get("allowed_entity_ids", [])}
    expected_kind = oracle["expected_entity_id"].split(":", 1)[0]
    bucket = BUCKET_FOR_KIND.get(expected_kind)

    fetch_error: str | None = None
    if record is None:
        code, candidates = "NOT_PRODUCED", []
    elif not record.get("fetch_ok", True):
        code, candidates = "FETCH_FAILED", []
        fetch_error = record.get("error")
    elif bucket is None:
        # e.g. ``hub:golf`` — /typeahead emits hub rows, /search has no hub bucket.
        # Declared unsupported rather than failed: /search is not wrong to omit a
        # surface it does not have, and scoring it as a miss would invent a defect.
        code, candidates = "BUCKET_UNSUPPORTED", []
    else:
        candidates = record.get("candidates") or []
        in_bucket = [row for row in candidates if row.get("bucket") == bucket]
        if any(row.get("entity_id") in expected_ids for row in in_bucket):
            code = "PASS"
        elif any(row.get("entity_id") in expected_ids for row in candidates):
            code = "WRONG_BUCKET"
        elif not in_bucket:
            code = "BUCKET_EMPTY"
        else:
            code = "NOT_IN_BUCKET"

    detail = {
        "probe_key": identity["probe_key"],
        "probe_version": identity["probe_version"],
        "query_class": oracle["query_class"],
        "expected_bucket": bucket,
        "code": code,
        "disposition": "unmeasured" if code in BUCKET_UNMEASURED_CODES else ("pass" if code == "PASS" else "fail"),
        "bucket_size": sum(1 for row in candidates if row.get("bucket") == bucket) if bucket else 0,
    }
    if code in BUCKET_UNMEASURED_CODES:
        detail["fetch_error"] = fetch_error
    return detail


def evaluate_bucket_recall(
    probes: list[dict[str, Any]],
    results: dict[str, Any],
) -> dict[str, Any]:
    """Grade per-bucket recall of ``/api/events/search`` (see the note above)."""

    details = []
    seen_keys = set()
    for probe in sorted(probes, key=lambda row: (row["identity"]["probe_key"], row["identity"]["probe_version"])):
        if probe["identity"]["task_type"] != "search_entity":
            raise ValueError("SEARCH_TASK_TYPE_INVALID")
        key = probe["identity"]["probe_key"]
        if key in seen_keys:
            raise ValueError(f"SEARCH_PROBE_DUPLICATE: {key}")
        seen_keys.add(key)
        raw = results.get(key)
        details.append(
            _score_probe_bucket_recall(probe, None if raw is None else _normalize_record(raw))
        )

    measured = [row for row in details if row["code"] not in BUCKET_UNMEASURED_CODES]
    unmeasured = [row for row in details if row["code"] in BUCKET_UNMEASURED_CODES]
    return {
        "total": len(details),
        "measured": len(measured),
        "unmeasured": len(unmeasured),
        "coverage": len(measured) / len(details) if details else 0.0,
        "unmeasured_probes": [
            {"probe_key": row["probe_key"], "code": row["code"], "fetch_error": row.get("fetch_error")}
            for row in unmeasured
        ],
        "bucket_recall_rate": (
            sum(row["code"] == "PASS" for row in measured) / len(measured) if measured else 0.0
        ),
        "empty_buckets": sum(row["code"] == "BUCKET_EMPTY" for row in details),
        "code_counts": {
            code: sum(row["code"] == code for row in details)
            for code in sorted({row["code"] for row in details})
        },
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry")
    parser.add_argument("--split", choices=("train", "tune", "test", "canary"))
    parser.add_argument("--results")
    parser.add_argument("--legacy-gold")
    parser.add_argument(
        "--mode",
        choices=("entity_top_1", "bucket_recall"),
        default="entity_top_1",
        help="entity_top_1 grades /typeahead rank 1; bucket_recall grades /search per bucket",
    )
    args = parser.parse_args()
    if args.legacy_gold:
        require_entity_gold(parse_gold_markdown(args.legacy_gold))
        raise AssertionError("legacy parser unexpectedly produced entity gold")
    if not (args.registry and args.split and args.results):
        parser.error("--registry, --split, and --results are required")
    records = load_registry(args.registry)
    probes = filter_probes(records, task_type="search_entity", split=args.split)
    results = load_result_records(args.results)
    if args.mode == "bucket_recall":
        report = evaluate_bucket_recall(probes, results)
        print(json.dumps(report, indent=2))
        # An unmeasured probe is a broken RUN, not a Search verdict — exit
        # non-zero so it can never be read as a clean pass.
        return 1 if report["unmeasured"] or report["bucket_recall_rate"] < 1.0 else 0
    report = evaluate_entity_probes(probes, results)
    print(json.dumps(report, indent=2))
    counts = report["lifecycle_counts"]
    if report["unmeasured"]:
        return 1
    return 1 if counts["fail"] or counts["regression"] or counts["xpass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
