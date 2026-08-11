"""LAT-P035 Item 2 — the bucket producer must report a FLAPPING probe, not average it.

LAT-P034 measured bucket recall 39/44 -> 41/44 and then found the 41st point was
not a fix at all: `search-gold-red-sox-001` had flipped because the teams bucket
returned `team:boston-red-sox` on one run and `team:boston-red-sox-mlb` on the
next — the two duplicate rows of #1754, alternating, bucket size 2 both times.

That is a measurement-integrity failure rather than a Search defect: a single run
cannot tell "Search improved" from "Search is unstable and I sampled the good
side", and every number the lane reports rides on that distinction. These tests
pin the verdict logic, including the case that must NOT be called stable.
"""

from __future__ import annotations

import pytest

from scripts.evals import search_bucket_producer as producer


def _payload(team_slugs: list[str], futures_ids: list[int] | None = None) -> dict:
    return {
        "teams": [{"slug": slug, "name": slug} for slug in team_slugs],
        "futures": [{"id": mid, "name": f"m{mid}"} for mid in (futures_ids or [])],
        "results": [],
        "event_concepts": [],
        "_elapsed_ms": 5,
    }


def _run(responses, *, repeat):
    """Drive `produce` against a scripted sequence of fetch outcomes."""

    calls = iter(responses)

    def fake_fetch(query, *, api, timeout):
        outcome = next(calls)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    original = producer.fetch_search
    producer.fetch_search = fake_fetch
    try:
        return producer.produce(
            [("probe-1", "red sox")], api="http://x", sleep=0, timeout=1,
            retries=0, repeat=repeat,
        )
    finally:
        producer.fetch_search = original


def test_identical_runs_are_reported_stable():
    out = _run([_payload(["a", "b"]), _payload(["a", "b"])], repeat=2)
    assert out["results"][0]["stability"]["verdict"] == "STABLE"
    assert out["metadata"]["flapping"] == 0


def test_the_red_sox_flap_is_caught():
    """The exact shape LAT-P034 hit: same bucket SIZE, different member."""
    out = _run(
        [_payload(["boston-red-sox-mlb", "worcester-red-sox"]),
         _payload(["boston-red-sox", "worcester-red-sox"])],
        repeat=2,
    )
    row = out["results"][0]
    assert row["stability"]["verdict"] == "FLAPPING", (
        "a bucket that swapped one member for another was called stable — this is "
        "the +/-1 that made 41/44 unquotable"
    )
    assert len(row["stability"]["observed_variants"]) == 2
    assert out["metadata"]["flapping_probes"] == ["probe-1"]


def test_rank_order_within_a_bucket_is_not_a_flap():
    """The scorer grades MEMBERSHIP, so reordering is not a change to the measured
    thing. Flagging it would cry wolf on every run and the mode would get switched
    off — which is the failure that matters."""
    out = _run([_payload(["a", "b"]), _payload(["b", "a"])], repeat=2)
    assert out["results"][0]["stability"]["verdict"] == "STABLE"


def test_a_failed_run_is_unverified_rather_than_stable():
    """Absence of evidence is not evidence of stability (gotcha #53). One good run
    and one failure must not read the same as two agreeing runs."""
    out = _run([_payload(["a"]), ValueError("boom")], repeat=2)
    assert out["results"][0]["stability"]["verdict"] == "UNVERIFIED"
    assert out["metadata"]["unverified_stability_probes"] == ["probe-1"]
    assert out["metadata"]["flapping"] == 0


def test_the_graded_answer_is_always_the_first_run():
    """Repetition adds a verdict; it must never change the number. A repeated file
    and a single-run file have to agree on what the scorer reads, or the stability
    mode would itself become a source of drift."""
    out = _run([_payload(["first"]), _payload(["second"])], repeat=2)
    ids = [c["entity_id"] for c in out["results"][0]["candidates"]]
    assert ids == ["team:first"]


def test_single_run_output_carries_no_stability_claim():
    """`--repeat 1` cannot support a verdict, so it must not emit one."""
    out = _run([_payload(["a"])], repeat=1)
    assert "stability" not in out["results"][0]
    assert out["metadata"]["flapping"] == 0
