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


# ---------------------------------------------------------------------------
# LAT-P037 — an EMPTY expected bucket is an outage, not a miss
# ---------------------------------------------------------------------------
#
# This module's subject opens by saying it exists to prevent the `f98d8104`
# revert, "and that revert was /search's futures bucket emptying" — then recorded
# `bucket_sizes` and never read them. Both times the failure actually happened
# (LAT-P002's 4s timeout, LAT-P035's 2-char word test) the producer would have
# reported it as an ordinary missing id, indistinguishable from a ranking loss.


def _run_items(items, responses):
    calls = iter(responses)

    def fake_fetch(query, *, api, timeout):
        return next(calls)

    original = producer.fetch_search
    producer.fetch_search = fake_fetch
    try:
        return producer.produce(items, api="http://x", sleep=0, timeout=1, retries=0)
    finally:
        producer.fetch_search = original


def test_an_empty_expected_bucket_is_reported_and_fails_the_run():
    """HTTP 200 with the primary bucket empty is the revert signature itself."""
    out = _run_items(
        [("probe-1", "nba champion", "futures", "pass")],
        [_payload(["a"], futures_ids=[])],
    )
    row = out["results"][0]
    assert row["fetch_ok"] is True, "this is a SUCCESSFUL fetch — that is the point"
    assert row["empty_expected_bucket"] is True
    assert out["metadata"]["empty_expected_bucket_probes"] == ["probe-1"]


def test_a_populated_expected_bucket_is_not_flagged():
    """The check must not fire on an ordinary miss, or it becomes noise.

    The market is simply not the one that came back — a ranking/recall question,
    which the recall score already measures.
    """
    out = _run_items(
        [("probe-1", "nba champion", "futures", "pass")],
        [_payload([], futures_ids=[999])],
    )
    assert out["results"][0]["empty_expected_bucket"] is False
    assert out["metadata"]["empty_expected_bucket"] == 0


def test_only_the_bucket_the_answer_lives_in_counts():
    """A market probe says nothing about the teams bucket.

    Flagging every empty bucket would fire on almost every probe — `tush push` has
    no teams and never should — and a check that always fires is switched off.
    """
    out = _run_items(
        [("probe-1", "tush push", "futures", "pass")],
        [_payload([], futures_ids=[113466])],
    )
    assert out["results"][0]["empty_expected_bucket"] is False


def test_a_declared_xfail_empty_bucket_is_reported_but_not_counted():
    """The wedding query's empty 200 IS its declared breakage.

    57 characters against /typeahead's `max_length=50`; measured on production
    2026-08-11 (v3777) it is the only empty expected bucket in the 46-probe set.
    Counting it would make the check permanently red, and a permanently red check
    is one nobody reads — but hiding it entirely is how a declared failure becomes
    a forgotten one, so it keeps its own key.
    """
    out = _run_items(
        [("probe-1", "where will taylor swift...", "futures", "xfail")],
        [_payload([], futures_ids=[])],
    )
    row = out["results"][0]
    assert row["empty_expected_bucket"] is False
    assert row["empty_expected_bucket_declared"] is True
    assert out["metadata"]["empty_expected_bucket"] == 0
    assert out["metadata"]["empty_expected_bucket_declared_probes"] == ["probe-1"]


def test_a_probe_with_no_expected_bucket_makes_no_claim():
    """Exploration mode has no registry and so no expected answer. It must not
    guess one — an invented expectation is worse than no check (gotcha #53)."""
    out = _run_items([("explore-001", "anything")], [_payload([], futures_ids=[])])
    assert "empty_expected_bucket" not in out["results"][0]
    assert out["metadata"]["empty_expected_bucket"] == 0


def test_the_expected_bucket_is_derived_from_the_bucket_map():
    """One mapping, not two. A hand-written prefix table would drift from
    `BUCKET_MAP` the first time a bucket is added."""
    assert producer.expected_bucket("market:350") == "futures"
    assert producer.expected_bucket("team:boston-celtics") == "teams"
    assert producer.expected_bucket("concept:event:golf:the-open") == "event_concepts"
    assert producer.expected_bucket("event:123") == "results"
    assert producer.expected_bucket("hub:golf") is None, (
        "there is no hub BUCKET in /search's response; claiming one would flag "
        "every hub probe as an outage"
    )
    assert producer.expected_bucket(None) is None
    assert producer.expected_bucket("nonsense") is None


# --- LAT-P038/#1769: bucket COLLAPSE, the sibling of an empty bucket ----------
#
# `search-gold-president-001` PASSED on every run while `president` returned ONE
# market out of 461 open matches, because 112897 was the row that survived the
# dedup. Recall asks "is the answer present" and cannot ask "and nothing else was
# deleted", so the collapse needs its own verdict — kept separate from recall and
# from emptiness rather than averaged into either (gotcha #53).


def _collapse_payload(futures_ids, collapse=None):
    payload = _payload([], futures_ids=futures_ids)
    if collapse is not None:
        payload["futures_collapse"] = collapse
    return payload


def test_a_collapsed_bucket_is_reported_and_fails_the_run():
    """The #1769 shape exactly: HTTP 200, bucket NON-empty, and still wrong."""
    out = _run_items(
        [("probe-1", "president", "futures", "pass")],
        [_collapse_payload(
            [112897],
            {"window": 20, "fetched": 20, "returned": 1, "page": 10},
        )],
    )
    row = out["results"][0]
    assert row["fetch_ok"] is True
    assert row["empty_expected_bucket"] is False, (
        "a collapsed bucket is NOT an empty one — one row came back. Folding the "
        "two verdicts together loses the distinction the fix turns on"
    )
    assert row["bucket_collapse"] is True
    assert row["bucket_collapse_detail"]["returned"] == 1
    assert out["metadata"]["bucket_collapse"] == 1
    assert out["metadata"]["bucket_collapse_probes"] == ["probe-1"]


def test_a_small_but_honest_bucket_is_not_a_collapse():
    """`tush push` returns one market and is CORRECT.

    This is the whole reason the verdict is read from the server rather than
    inferred from bucket size: from out here a right one-row answer and a
    collapsed one-row answer are the same response. A size heuristic would fire
    on every narrow query, and a check that always fires gets switched off.
    """
    out = _run_items(
        [("probe-1", "tush push", "futures", "pass")],
        [_collapse_payload([113466])],
    )
    assert out["results"][0]["bucket_collapse"] is False
    assert out["metadata"]["bucket_collapse"] == 0


def test_collapse_is_not_inferred_from_a_full_bucket_either():
    out = _run_items(
        [("probe-1", "fed", "futures", "pass")],
        [_collapse_payload(list(range(1, 11)))],
    )
    assert out["results"][0]["bucket_collapse"] is False


def test_collapse_is_reported_even_with_no_expected_bucket():
    """Exploration mode has no expected answer, but collapse is a claim about the
    RESPONSE, not about the probe's referent — so it is still observable."""
    out = _run_items(
        [("explore-001", "election")],
        [_collapse_payload(
            [112897], {"window": 20, "fetched": 20, "returned": 1, "page": 10}
        )],
    )
    assert out["results"][0]["bucket_collapse"] is True
    assert out["metadata"]["bucket_collapse"] == 1


def test_a_failed_fetch_makes_no_collapse_claim():
    """Absence of evidence, again. A fetch error must not read as a clean bucket."""

    def boom(query, *, api, timeout):
        raise TimeoutError("boom")

    original = producer.fetch_search
    producer.fetch_search = boom
    try:
        out = producer.produce(
            [("probe-1", "president", "futures", "pass")],
            api="http://x", sleep=0, timeout=1, retries=0,
        )
    finally:
        producer.fetch_search = original
    row = out["results"][0]
    assert row["fetch_ok"] is False
    assert "bucket_collapse" not in row
    assert out["metadata"]["bucket_collapse"] == 0


def test_the_collapse_verdict_actually_fails_the_run():
    """Recording a verdict and not acting on it is this module's named failure —
    it carried `bucket_sizes` through two reverts without ever reading them. The
    exit policy is measured, not assumed: over the real compiled predicate
    against production 2026-08-11 with the #1769 fix applied, collapse fires on
    0 of the 46 gold queries, so a non-zero count is a regression."""
    import inspect

    exit_expr = inspect.getsource(producer.main)
    exit_expr = exit_expr[exit_expr.index("return 1 if ("):]
    for signal in (
        "fetch_failed",
        "flapping",
        "empty_expected_bucket",
        "bucket_collapse",
    ):
        assert signal in exit_expr, f"{signal} is reported but cannot fail the run"
