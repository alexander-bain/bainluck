"""Guards for LAT-P029 Item 3 — the gate must not report a broken run as a miss.

The gold gate (queue 313) grades Search. These tests grade the GATE, on the one
axis that decides whether its number means anything: can it tell "we could not
measure" apart from "Search found nothing"? Gotcha #53 is the general form —
*an empty 200 is not an absence, it is a response shape* — and the scorer was
committing exactly that error against its own producer, which records
`error`/`fetch_ok` and cites #53 by name for doing so.

Item 4's requirement is that a changed grading path must be able to FAIL, so each
test below drives the scorer with a deliberately broken searcher (one that returns
nothing, one that returns everything, one that never ran) and asserts the scorer
says so.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evals.probe_registry import filter_probes, load_registry
from scripts.evals.search_bucket_producer import BUCKET_MAP, map_response, map_row
from scripts.evals.search_gold_eval import (
    evaluate_bucket_recall,
    evaluate_entity_probes,
    load_result_records,
)

REGISTRY_PATH = Path(__file__).parents[2] / "scripts" / "evals" / "search_gold_probes.json"


def _probes() -> list[dict]:
    return filter_probes(load_registry(REGISTRY_PATH), task_type="search_entity", split="test")


def _detail(report: dict, key: str) -> dict:
    return next(row for row in report["details"] if row["probe_key"] == key)


def _passing_candidate(probe: dict) -> dict:
    answer = probe["oracle"]["answer"]
    return {
        "entity_id": answer["expected_entity_id"],
        "surface": answer["expected_surfaces"][0],
        "item_type": answer["expected_item_type"],
    }


def _all_passing(probes: list[dict]) -> dict[str, dict]:
    return {
        probe["identity"]["probe_key"]: {
            "candidates": [_passing_candidate(probe)],
            "fetch_ok": True,
        }
        for probe in probes
    }


# --------------------------------------------------------------------------
# 3a — a failed fetch is not a recall miss
# --------------------------------------------------------------------------

def test_a_failed_fetch_is_unmeasured_not_a_miss() -> None:
    probes = _probes()
    results = _all_passing(probes)
    victim = probes[0]["identity"]["probe_key"]
    results[victim] = {"candidates": [], "fetch_ok": False, "error": "HTTPError 429: Too Many Requests"}

    report = evaluate_entity_probes(probes, results)
    detail = _detail(report, victim)
    assert detail["code"] == "FETCH_FAILED"
    assert detail["disposition"] == "unmeasured"
    assert "429" in detail["fetch_error"]
    # The whole point: it must not be counted against Search.
    assert report["lifecycle_counts"]["fail"] == 0
    assert report["unmeasured"] == 1
    assert report["coverage"] == pytest.approx((len(probes) - 1) / len(probes))


def test_a_probe_missing_from_the_results_file_is_unmeasured_not_a_miss() -> None:
    """The fourth hole: `results.get(key, [])` turned "never ran" into "found nothing"."""

    probes = _probes()
    results = _all_passing(probes)
    victim = probes[0]["identity"]["probe_key"]
    del results[victim]

    detail = _detail(evaluate_entity_probes(probes, results), victim)
    assert detail["code"] == "NOT_PRODUCED"
    assert detail["disposition"] == "unmeasured"


def test_a_genuine_empty_answer_is_still_a_miss() -> None:
    """The other direction — the fix must not launder real zero-recall away.

    A searcher that returns NOTHING while the fetch succeeded is exactly the
    failure the gate exists to catch, and it must still score NO_RESULTS.
    """

    probes = _probes()
    results = _all_passing(probes)
    victim = probes[0]["identity"]["probe_key"]
    results[victim] = {"candidates": [], "fetch_ok": True}

    detail = _detail(evaluate_entity_probes(probes, results), victim)
    assert detail["code"] == "NO_RESULTS"
    assert detail["disposition"] != "unmeasured"


def test_partial_fetch_failure_cannot_quietly_move_the_headline_rate() -> None:
    """Total failure was already loud; PARTIAL failure was the hazard.

    Six flaky fetches used to subtract six from the numerator and nothing from the
    denominator, so the rate dropped and read as a code regression. Now they leave
    the rate alone and show up as coverage < 1.
    """

    probes = _probes()
    clean = evaluate_entity_probes(probes, _all_passing(probes))

    flaky = _all_passing(probes)
    for probe in probes[:6]:
        flaky[probe["identity"]["probe_key"]] = {
            "candidates": [], "fetch_ok": False, "error": "TimeoutError: timed out",
        }
    degraded = evaluate_entity_probes(probes, flaky)

    assert clean["entity_top_1_rate"] == degraded["entity_top_1_rate"]
    assert degraded["unmeasured"] == 6
    assert degraded["coverage"] < 1.0
    assert len(degraded["unmeasured_probes"]) == 6


def test_the_loader_preserves_fetch_status_from_a_producer_file(tmp_path: Path) -> None:
    """End to end: the producer writes the fields, the loader must not drop them."""

    path = tmp_path / "results.json"
    path.write_text(
        json.dumps(
            {
                "results": [
                    {"probe_key": "ok", "candidates": [{"entity_id": "team:x"}], "fetch_ok": True},
                    {"probe_key": "bad", "candidates": [], "fetch_ok": False, "error": "HTTPError 422: Unprocessable Entity"},
                ]
            }
        ),
        encoding="utf-8",
    )
    records = load_result_records(path)
    assert records["ok"]["fetch_ok"] is True
    assert records["bad"]["fetch_ok"] is False
    assert "422" in records["bad"]["error"]


def test_a_legacy_row_without_fetch_ok_still_counts_as_measured(tmp_path: Path) -> None:
    """Defaulting the other way would move legacy rows out of the denominator."""

    path = tmp_path / "results.json"
    path.write_text(json.dumps({"results": [{"probe_key": "a", "candidates": []}]}), encoding="utf-8")
    assert load_result_records(path)["a"]["fetch_ok"] is True


# --------------------------------------------------------------------------
# 3c — per-bucket recall against /search
# --------------------------------------------------------------------------

def _bucket_record(bucket: str, entity_id: str) -> dict:
    return {"candidates": [{"entity_id": entity_id, "bucket": bucket, "rank_in_bucket": 1}], "fetch_ok": True}


def _market_probe(probes: list[dict]) -> dict:
    return next(
        probe for probe in probes
        if probe["oracle"]["answer"]["expected_entity_id"].startswith("market:")
    )


def test_bucket_recall_passes_when_the_expected_bucket_holds_the_answer() -> None:
    probes = _probes()
    target = _market_probe(probes)
    key = target["identity"]["probe_key"]
    results = {key: _bucket_record("futures", target["oracle"]["answer"]["expected_entity_id"])}

    detail = _detail(evaluate_bucket_recall([target], results), key)
    assert detail["code"] == "PASS"
    assert detail["expected_bucket"] == "futures"


def test_bucket_recall_names_an_empty_bucket_as_such() -> None:
    """`BUCKET_EMPTY` is the f98d8104 revert's exact signature and must be visible.

    That revert shipped a statement timeout, and /search answered 200 with the
    futures bucket EMPTY. A gate that lumped this in with "wrong result" would have
    described the outage as a relevance regression — which is precisely the wrong
    diagnosis the Integrator recorded at the time.
    """

    probes = _probes()
    target = _market_probe(probes)
    key = target["identity"]["probe_key"]
    results = {key: {"candidates": [], "fetch_ok": True}}

    report = evaluate_bucket_recall([target], results)
    assert _detail(report, key)["code"] == "BUCKET_EMPTY"
    assert report["empty_buckets"] == 1
    assert report["bucket_recall_rate"] == 0.0


def test_bucket_recall_distinguishes_wrong_bucket_from_absent() -> None:
    probes = _probes()
    target = _market_probe(probes)
    key = target["identity"]["probe_key"]
    expected = target["oracle"]["answer"]["expected_entity_id"]

    wrong = evaluate_bucket_recall([target], {key: _bucket_record("teams", expected)})
    assert _detail(wrong, key)["code"] == "WRONG_BUCKET"

    absent = evaluate_bucket_recall([target], {key: _bucket_record("futures", "market:999999999")})
    assert _detail(absent, key)["code"] == "NOT_IN_BUCKET"


def test_bucket_recall_declares_hub_probes_unsupported_rather_than_failed() -> None:
    """/search has no hub bucket. Scoring that as a miss would invent a defect."""

    probes = _probes()
    hubs = [p for p in probes if p["oracle"]["answer"]["expected_entity_id"].startswith("hub:")]
    assert hubs, "the gold set is expected to contain at least one hub probe"
    key = hubs[0]["identity"]["probe_key"]

    report = evaluate_bucket_recall([hubs[0]], {key: {"candidates": [], "fetch_ok": True}})
    detail = _detail(report, key)
    assert detail["code"] == "BUCKET_UNSUPPORTED"
    assert detail["disposition"] == "unmeasured"
    assert report["measured"] == 0


def test_bucket_recall_also_refuses_to_score_an_unfetched_probe() -> None:
    probes = _probes()
    target = _market_probe(probes)
    key = target["identity"]["probe_key"]

    failed = evaluate_bucket_recall([target], {key: {"candidates": [], "fetch_ok": False, "error": "boom"}})
    assert _detail(failed, key)["code"] == "FETCH_FAILED"
    assert evaluate_bucket_recall([target], {})["details"][0]["code"] == "NOT_PRODUCED"


def _firehose(key: str, ids: list[str]) -> dict:
    return {
        key: {
            "candidates": [
                {"entity_id": entity_id, "bucket": "futures", "rank_in_bucket": rank}
                for rank, entity_id in enumerate(ids, 1)
            ],
            "fetch_ok": True,
        }
    }


def test_a_searcher_that_returns_everything_wrong_still_fails() -> None:
    """Item 4's second broken searcher: a flood of the WRONG ids is still a miss."""

    probes = _probes()
    target = _market_probe(probes)
    key = target["identity"]["probe_key"]
    noise = [f"market:9{index:06d}" for index in range(500)]
    assert target["oracle"]["answer"]["expected_entity_id"] not in noise

    detail = _detail(evaluate_bucket_recall([target], _firehose(key, noise)), key)
    assert detail["code"] == "NOT_IN_BUCKET"
    assert detail["bucket_size"] == 500


def test_recall_grading_is_gameable_by_a_firehose_and_says_so_via_bucket_size() -> None:
    """A LIMIT of this mode, pinned rather than hidden.

    Bucket recall is rank-blind by construction — that is the whole reason it can
    grade /search without inventing a cross-bucket merge order. The cost of being
    rank-blind is that a searcher returning the entire corpus scores a PASS. This
    is not a hole to plug in the recall scorer; plugging it would mean inventing
    the very ranking the mode exists to avoid asserting.

    The two real defences are kept honest instead: `bucket_size` is published on
    every detail so a flood is VISIBLE, and the rank-sensitive `entity_top_1` mode
    against /typeahead is retained alongside rather than replaced.
    """

    probes = _probes()
    target = _market_probe(probes)
    key = target["identity"]["probe_key"]
    flood = [f"market:9{index:06d}" for index in range(499)]
    flood.append(target["oracle"]["answer"]["expected_entity_id"])

    detail = _detail(evaluate_bucket_recall([target], _firehose(key, flood)), key)
    assert detail["code"] == "PASS"
    assert detail["bucket_size"] == 500, "a 500-row bucket must be visible in the report"


# --------------------------------------------------------------------------
# the /search adapter
# --------------------------------------------------------------------------

def test_adapter_maps_each_search_bucket_to_its_own_identifier() -> None:
    payload = {
        "teams": [{"slug": "boston-red-sox-mlb", "name": "Boston Red Sox"}],
        "results": [{"id": 15189221, "home_team": "Red Sox"}],
        "event_concepts": [{"key": "event:golf:the-open-championship", "name": "The Open"}],
        "futures": [{"id": 113466, "name": "2027 Champion"}],
    }
    rows = {row["bucket"]: row for row in map_response(payload)}
    assert rows["teams"]["entity_id"] == "team:boston-red-sox-mlb"
    assert rows["results"]["entity_id"] == "event:15189221"
    assert rows["event_concepts"]["entity_id"] == "concept:event:golf:the-open-championship"
    assert rows["futures"]["entity_id"] == "market:113466"


def test_adapter_never_mints_identity_from_display_text() -> None:
    row = map_row("teams", {"name": "Boston Celtics"}, 1)
    assert row["entity_id"] == "unresolved:teams:missing_slug"
    assert "celtics" not in row["entity_id"].casefold()


def test_adapter_ignores_futures_families_to_avoid_double_counting() -> None:
    """Families are a presentation grouping over markets already in flat `futures`.

    Verified live 2026-08-10: every family member id was a subset of the flat list.
    Mapping both would give one market two identities and a doubled bucket size.
    """

    assert "futures_families" not in BUCKET_MAP
    payload = {"futures": [{"id": 1, "name": "m"}], "futures_families": [{"members": [{"id": 1}]}]}
    assert len(map_response(payload)) == 1
