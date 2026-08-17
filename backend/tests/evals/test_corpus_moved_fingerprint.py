"""RULING 073 — a disposition change with no code change is a CORPUS event.

THE SPECIMEN THIS FILE EXISTS FOR (LAT-P059, 2026-08-17). The armed null
control was re-run against production with NO code change: same producer blob
`61de6598`, 46/46 specimens, fidelity `exact`. Three dispositions moved, all
upward — 39/44 -> 41/44, MRR 0.8913043478260869 -> 0.9347826086956522, zero
regressions. From the output alone that is "+2 passes, zero regressions": a
clean win to bank and then misattribute to whatever shipped most recently.

It was none of that. All three old top-ranked entities had LEFT THE ELIGIBLE
POOL. "FedEx St. Jude Championship Winner" resolved and stopped out-ranking the
Fed Chair market. "Stanley Cup ... Carolina Hurricanes" resolved and stopped
out-ranking the hurricane market. `event:15191951` closed BETWEEN THE TWO READS.
The ranking did not improve; the distractors resolved.

Occurrence FOUR of "specimens pinned to live markets expire", and the FIRST in
the flattering direction — which is why the guard is mechanical and not a note.
A number that looks worse gets investigated. A number that looks better gets
banked. The asymmetry lives in the reader, so the fingerprint lives in the
instrument.
"""

from __future__ import annotations

from scripts.evals.search_gold_eval import (
    _pool_fingerprint,
    _score_probe,
    classify_disposition_changes,
)


def _row(key, disposition, pool_ids, *, top=None, eligible=True):
    """A graded detail row, shaped as `_score_probe` emits one."""
    return {
        "probe_key": key,
        "disposition": disposition,
        "pool_fingerprint": _pool_fingerprint([{"entity_id": i} for i in pool_ids]),
        "pool_size": len(pool_ids),
        "pool_entity_ids": sorted(pool_ids),
        "expected_entity_eligible": eligible,
        "actual_top": {"entity_id": top} if top else None,
    }


# ---------------------------------------------------------------------------
# The hinge: SET, not sequence.
# ---------------------------------------------------------------------------


def test_a_reordered_pool_has_the_SAME_fingerprint() -> None:
    """This is the whole hinge, and getting it wrong inverts the guard.

    A pool whose members merely REORDERED is a ranking event and must still be
    graded. Hashing the ordered candidate list would classify every genuine
    ranking improvement as CORPUS-MOVED and quarantine precisely the thing the
    gold set exists to detect — a guard that suppresses real findings is worse
    than no guard.
    """
    a = [{"entity_id": "x"}, {"entity_id": "y"}, {"entity_id": "z"}]
    b = [{"entity_id": "z"}, {"entity_id": "x"}, {"entity_id": "y"}]
    assert _pool_fingerprint(a) == _pool_fingerprint(b)


def test_a_changed_MEMBERSHIP_has_a_different_fingerprint() -> None:
    a = [{"entity_id": "x"}, {"entity_id": "y"}]
    b = [{"entity_id": "x"}]
    assert _pool_fingerprint(a) != _pool_fingerprint(b)


def test_duplicate_entities_do_not_change_the_pool() -> None:
    """Eligibility is a set question: "could this have been ranked?"."""
    a = [{"entity_id": "x"}, {"entity_id": "y"}]
    b = [{"entity_id": "x"}, {"entity_id": "x"}, {"entity_id": "y"}]
    assert _pool_fingerprint(a) == _pool_fingerprint(b)


# ---------------------------------------------------------------------------
# Attribution.
# ---------------------------------------------------------------------------


def test_the_lat_p059_specimen_is_quarantined_and_the_expired_one_is_NAMED() -> None:
    """Replay the real case: a distractor resolves, a fail becomes a pass.

    Naming the departed specimen is not a nicety. Ruling 073 lets the baseline
    move only by an explicit re-baseline that NAMES the expired specimens, which
    is unsatisfiable if the tooling reports only a count.
    """
    before = [_row("fed_chair", "fail",
                   ["market:fedex_st_jude", "market:fed_chair"],
                   top="market:fedex_st_jude")]
    after = [_row("fed_chair", "pass",
                  ["market:fed_chair"],
                  top="market:fed_chair")]

    delta = classify_disposition_changes(before, after, code_changed=False)

    assert delta["corpus_moved"] == 1
    assert delta["real"] == 0
    assert delta["baseline_may_move"] is False, (
        "a quarantined delta must not move the banked baseline"
    )
    change = delta["changes"][0]
    assert change["verdict"] == "CORPUS-MOVED"
    assert change["before"] == "fail" and change["after"] == "pass"
    assert change["left_pool"] == ["market:fedex_st_jude"], (
        "the expired specimen must be named, not merely counted"
    )
    assert change["pool_size_before"] == 2 and change["pool_size_after"] == 1


def test_an_improvement_over_an_UNCHANGED_pool_is_REAL_and_still_grades() -> None:
    """The guard must not swallow genuine wins.

    Same members, different winner: the ranking function did this, and the
    baseline is allowed to move.
    """
    pool = ["market:a", "market:b"]
    before = [_row("k", "fail", pool, top="market:b")]
    after = [_row("k", "pass", pool, top="market:a")]

    delta = classify_disposition_changes(before, after, code_changed=False)

    assert delta["real"] == 1
    assert delta["corpus_moved"] == 0
    assert delta["baseline_may_move"] is True
    assert delta["changes"][0]["verdict"] == "REAL"


def test_a_code_change_over_a_moved_pool_is_CONFOUNDED_not_a_win() -> None:
    """Ship Tuesday, read Thursday: attributable to neither, and it says so.

    The tempting reading is "we changed the ranking and it got better". With the
    pool moved underneath, that inference is unavailable — and CONFOUNDED is the
    verdict that refuses to supply it.
    """
    before = [_row("k", "fail", ["a", "b"], top="b")]
    after = [_row("k", "pass", ["a"], top="a")]

    delta = classify_disposition_changes(before, after, code_changed=True)

    assert delta["confounded"] == 1
    assert delta["real"] == 0
    assert delta["changes"][0]["verdict"] == "CONFOUNDED"


def test_a_code_change_over_a_STABLE_pool_is_REAL() -> None:
    pool = ["a", "b"]
    delta = classify_disposition_changes(
        [_row("k", "fail", pool, top="b")],
        [_row("k", "pass", pool, top="a")],
        code_changed=True,
    )
    assert delta["real"] == 1
    assert delta["baseline_may_move"] is True


def test_an_unchanged_disposition_is_not_reported_even_if_the_pool_moved() -> None:
    """Only CHANGES are attributed; a stable verdict needs no explanation."""
    delta = classify_disposition_changes(
        [_row("k", "pass", ["a", "b"], top="a")],
        [_row("k", "pass", ["a"], top="a")],
        code_changed=False,
    )
    assert delta["changed"] == 0
    assert delta["baseline_may_move"] is True


# ---------------------------------------------------------------------------
# The absent-fingerprint case — the one that would quietly restore the bug.
# ---------------------------------------------------------------------------


def test_a_pre_ruling_artifact_is_UNATTRIBUTABLE_not_REAL() -> None:
    """Two absent fingerprints must not compare EQUAL and read as "pool stable".

    Every graded artifact banked before ruling 073 lacks the field. Defaulting a
    missing fingerprint to "unchanged" would attribute every historical
    comparison to the ranking — reinstating the exact misreading the ruling
    exists to prevent, on the entire back catalogue, silently. Gotcha #53: an
    absent value and a known-equal value are not the same answer.
    """
    before = [{"probe_key": "k", "disposition": "fail"}]  # no fingerprint
    after = [_row("k", "pass", ["a"], top="a")]

    delta = classify_disposition_changes(before, after, code_changed=False)

    assert delta["unattributable"] == 1
    assert delta["real"] == 0
    assert delta["corpus_moved"] == 0
    assert delta["changes"][0]["verdict"] == "UNATTRIBUTABLE-NO-FINGERPRINT"


def test_a_new_probe_is_its_own_verdict() -> None:
    delta = classify_disposition_changes([], [_row("k", "pass", ["a"])], code_changed=False)
    assert delta["new_probes"] == 1
    assert delta["changes"][0]["verdict"] == "NEW-PROBE"


# ---------------------------------------------------------------------------
# The scorer emits what the comparison needs.
# ---------------------------------------------------------------------------


def _probe(key="k"):
    return {
        "identity": {"probe_key": key, "probe_version": 1, "task_type": "search_entity"},
        "oracle": {
            "answer": {
                "expected_entity_id": "market:target",
                "allowed_entity_ids": [],
                "expected_surfaces": ["any"],
                "expected_item_type": "futures",
                "query_class": "unit",
            }
        },
        "lifecycle": {"known_failure_status": "none"},
    }


def _probe_with_query_class():
    p = _probe()
    p["oracle"]["query_class"] = "unit"
    return p


def test_score_probe_emits_the_fingerprint_size_and_eligibility() -> None:
    record = {
        "fetch_ok": True,
        "candidates": [
            {"entity_id": "market:distractor", "surface": "futures", "item_type": "futures"},
            {"entity_id": "market:target", "surface": "futures", "item_type": "futures"},
        ],
    }
    detail = _score_probe(_probe_with_query_class(), record)

    assert detail["pool_size"] == 2
    assert detail["pool_entity_ids"] == ["market:distractor", "market:target"]
    assert detail["pool_fingerprint"] == _pool_fingerprint(record["candidates"])
    assert detail["expected_entity_eligible"] is True
    assert detail["disposition"] == "fail", "the distractor is on top"


def test_a_probe_whose_expected_entity_left_the_pool_is_marked_ineligible() -> None:
    """"We got worse at ranking it" and "it stopped existing" are the same row
    today. This is the field that separates them."""
    record = {
        "fetch_ok": True,
        "candidates": [
            {"entity_id": "market:someone_else", "surface": "futures", "item_type": "futures"},
        ],
    }
    detail = _score_probe(_probe_with_query_class(), record)

    assert detail["expected_entity_eligible"] is False
    assert detail["pool_size"] == 1


def test_an_unmeasured_probe_reports_eligibility_as_UNKNOWN_not_False() -> None:
    """A fetch that never happened says nothing about eligibility.

    `False` here would read as "the entity left the pool" — a claim about the
    corpus produced by a broken run, which is the same class of invention this
    whole ruling is about.
    """
    detail = _score_probe(_probe_with_query_class(), None)

    assert detail["disposition"] == "unmeasured"
    assert detail["expected_entity_eligible"] is None
    assert detail["pool_size"] == 0
