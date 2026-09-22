"""What the gold set can now tell apart about MC3 and MC2 (#1867).

WHY THIS FILE EXISTS
--------------------
`docs/search-scoring-spec.md` §7 recorded two blind spots: MC3 (partial tokens)
had NO probe isolating it, and MC2 (last-token prefix) was graded only
incidentally. Under ruling 056 a null read on either class is a statement about
the INSTRUMENT, not the change — so `PARTIAL_MIN_COVERAGE` could be retuned in
either direction and every number in §5 would be unchanged, and nobody could
learn anything from moving it.

#1867 closed both with six `canary` probes. This file is the test that says
what they grade, in the shape #1861's class established: capability AND limit,
both asserted, so no future reader has to rediscover which probe is which.

HOW THE EVIDENCE GETS HERE
--------------------------
`scripts/evals/mc3_mc2_discrimination_fixtures.json` holds production's own
served order plus, per candidate, the evidence the ENDPOINT ranked it on —
echoed through `evidence_to_wire` and rebuilt here through `evidence_from_wire`.
Nothing in this file constructs an `Evidence` by hand. That is not fastidiousness:
LAT-P050 measured that a harness which invents evidence from display text
demotes five correct answers and publishes a projection that misses its band by
seven. A test that hand-builds its specimen asserts the fixture.

TWO INSTRUMENT FACTS THIS FILE PINS, BOTH MEASURED WHILE BUILDING IT
--------------------------------------------------------------------
1. **The route scores `parse_intent(q).subject`, not the query.** Replaying the
   raw query is a DIFFERENT computation from production's, and it manufactures
   discriminators that do not exist — `who wins the us open` looks like a
   two-sided MC3 specimen raw and is inert on its subject. Every probe here is
   replayed on the subject, and `test_every_probe_replays_productions_own_rank_1`
   refuses the whole class if that replay ever stops reproducing production.
2. **`new ya` is MC2, not MC1B.** The MC1B boundary is real but narrower than it
   reads: `_query_prefixes_an_owned_name` folds the whole string, and `newya` is
   not a prefix of `newyorkyankees`. It is still the wrong MC2 probe, for an
   unrelated reason — muting MC2 does not move its top-1. Asserted below so the
   distinction is not re-litigated from prose.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.utils.search_intent import parse_intent
from app.utils.search_match_class import (
    MC1B_OWN_NAME_PREFIX,
    MC2_LAST_TOKEN_PREFIX,
    MC3_PARTIAL_TOKENS,
    PARTIAL_MIN_COVERAGE,
    PREFIX_MIN_LEN,
    Evidence,
    evidence_from_wire,
    match_class,
    rank,
)
import app.utils.search_match_class as scorer

_EVALS = Path(__file__).resolve().parents[1] / "scripts" / "evals"
_FIXTURE = _EVALS / "mc3_mc2_discrimination_fixtures.json"
_REGISTRY = _EVALS / "search_gold_probes.json"

#: The MC3 knob sweep. Twenty steps across the whole open interval, the same
#: sweep the specimens were found with — a two-point check would have missed the
#: Masters probe's lower edge at 0.333 entirely.
SWEEP = [round(0.05 * step, 2) for step in range(1, 21)]

#: (query, expected rank-1 entity, the edges where top-1 CHANGES).
#: An empty edge tuple is a LIMIT row and is load-bearing — see the class
#: comment in `scripts/evals/build_search_gold_registry.py`.
MC3_SPECIMENS = [
    ("2027 the masters champion odds", "market:61056094", ((0.30, 0.35), (0.65, 0.70))),
    ("2027 champions league winner odds", "market:392", ((0.75, 0.80),)),
    ("masters winner", "market:4", ()),
]

#: (query, expected rank-1 entity, what rank 1 BECOMES when MC2 cannot fire).
#: `None` is the LIMIT row: MC2 is present in the set and decides nothing.
MC2_SPECIMENS = [
    ("masters champ", "market:61056094", "concept:event:golf:the-masters"),
    ("oscar pictu", "market:6173044", "concept:event:awards:oscars"),
    ("manchester unite", "market:59164813", None),
]

#: The `test`-split probes whose real-world subject sits nearest these canary
#: rows. They are the reason the canary group keys are allowed to be distinct
#: (GROUP_SPLIT_LEAKAGE), and the claim is measured, not asserted.
CONTROLS = ["masters", "oscars", "best picture", "red sox", "us open"]


@pytest.fixture(scope="module")
def captured() -> dict[str, dict]:
    return json.loads(_FIXTURE.read_text())["queries"]


def _candidates(captured: dict, query: str) -> list[tuple[Evidence, str]]:
    """Production's served candidates for `query`, in production's own order."""
    row = captured[query]
    return [
        (evidence_from_wire(c["evidence"]), c["entity_id"])
        for c in row["candidates"]
    ]


def _top1(query: str, cands: list[tuple[Evidence, str]], *,
          coverage: float | None = None, prefix_min: int | None = None) -> str | None:
    """Rank 1 under the real scorer, optionally with one knob moved.

    Both knobs are restored in a `finally`: a module global left moved by a
    failing assertion would silently retune every test that runs after it.
    """
    old_cov, old_pre = scorer.PARTIAL_MIN_COVERAGE, scorer.PREFIX_MIN_LEN
    try:
        if coverage is not None:
            scorer.PARTIAL_MIN_COVERAGE = coverage
        if prefix_min is not None:
            scorer.PREFIX_MIN_LEN = prefix_min
        ordered = rank(query, list(cands))
    finally:
        scorer.PARTIAL_MIN_COVERAGE, scorer.PREFIX_MIN_LEN = old_cov, old_pre
    return ordered[0] if ordered else None


def _subject(captured: dict, query: str) -> str:
    """The string the route scores, re-derived rather than read off the fixture.

    Deliberately NOT `captured[query]["subject"]`: the fixture records what the
    subject was at capture time, and this recomputes it, so a change to
    `parse_intent` that moves a probe's subject fails HERE — loudly, next to the
    reason it matters — instead of quietly turning every specimen into a
    measurement of a different query.
    """
    stored = captured[query]["subject"]
    intent = parse_intent(query)
    derived = intent.subject if intent else query
    assert derived == stored, (
        f"`parse_intent` now maps {query!r} to {derived!r}, not the {stored!r} these "
        "specimens were captured and verified against. Every MC3/MC2 edge below was "
        "measured on the old subject; re-capture the fixture before trusting them."
    )
    return derived


# ---------------------------------------------------------------------------
# 0. Fidelity. Nothing below means anything if the replay is not production's.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query", [q for q, _, _ in MC3_SPECIMENS] + [q for q, _, _ in MC2_SPECIMENS]
)
def test_every_probe_replays_productions_own_rank_1(query, captured):
    """The offline replay reproduces production's served rank 1, at the shipped
    knobs, for every probe in both classes.

    This is the gate that rejected the first candidate set. A specimen whose
    replay disagrees with production is not a hard probe — it is a probe of a
    computation we do not ship, and its edges describe nothing.
    """

    cands = _candidates(captured, query)
    served_first = cands[0][1]
    assert _top1(_subject(captured, query), cands) == served_first, (
        f"the scorer replayed on {_subject(captured, query)!r} does not reproduce "
        f"production's served rank 1 ({served_first}) for {query!r}"
    )


@pytest.mark.parametrize("query, expected, _edges", MC3_SPECIMENS)
def test_mc3_probe_expects_what_production_serves(query, expected, _edges, captured):
    assert _candidates(captured, query)[0][1] == expected


@pytest.mark.parametrize("query, expected, _muted", MC2_SPECIMENS)
def test_mc2_probe_expects_what_production_serves(query, expected, _muted, captured):
    assert _candidates(captured, query)[0][1] == expected


# ---------------------------------------------------------------------------
# 1. MC3 — the knob is gradeable now, in both directions, by two mechanisms.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query, expected, edges", MC3_SPECIMENS)
def test_mc3_edges_are_exactly_where_the_class_claims(query, expected, edges, captured):
    """Sweep `PARTIAL_MIN_COVERAGE` across 0.05..1.00 and assert the answer
    changes at the recorded edges and NOWHERE else.

    Asserting the full sweep rather than the two edge points is the whole
    difference between "the knob can move this" and "the knob moves this HERE":
    a change that shifted an edge by a step, or opened a third one, would pass a
    two-point check and is a different scorer.
    """

    subject = _subject(captured, query)
    cands = _candidates(captured, query)
    observed = {cov: _top1(subject, cands, coverage=cov) for cov in SWEEP}

    changes = [
        (lo, hi)
        for lo, hi in zip(SWEEP, SWEEP[1:])
        if observed[lo] != observed[hi]
    ]
    assert tuple(changes) == edges, (
        f"{query!r}: top-1 changes at {changes}, not the recorded {list(edges)}. "
        "Either the scorer moved or the corpus did — check the fixture's capture "
        "date before editing this expectation."
    )
    assert observed[PARTIAL_MIN_COVERAGE] == expected, (
        "at the SHIPPED knob the probe must expect what production serves"
    )


def test_the_shipped_mc3_knob_is_pinned_at_the_value_the_ledger_was_read_at():
    """The one retune this class cannot see on its own, closed with an assertion.

    Added because the mutation gate caught it: moving `PARTIAL_MIN_COVERAGE`
    from 0.5 to 0.4 passes every other test in this file, and honestly so —
    0.4 sits above the Masters probe's lower edge (0.333), so no served answer
    changes and `entity_top_1` is right to read null.

    But a knob move that grades null is exactly the thing §5's ledger must not
    absorb silently: every published number was read at 0.5. So the shipped
    value is pinned HERE rather than inferred, and a deliberate retune has to
    come through this test — which puts it next to the edges it will invalidate
    and the spec section it must update. This is a bookkeeping assertion, not a
    claim that 0.5 is correct.
    """

    assert PARTIAL_MIN_COVERAGE == 0.5, (
        "PARTIAL_MIN_COVERAGE moved. Every edge in MC3_SPECIMENS was measured "
        "against 0.5, and §5's ledger was read at it. Re-sweep the specimens, "
        "update §7's table, then change this number."
    )


def test_mc3_limit_is_a_real_limit_not_a_missing_probe(captured):
    """`masters winner` cannot be moved by the knob at ANY value, and that is
    the point of keeping it.

    The issue's third non-negotiable: a probe set must encode what it cannot
    separate. An MC1 candidate owns every token of this query and class order is
    inviolable, so no MC3 admission can reach it. A null read on this probe after
    an MC3 retune is correct behaviour — the distinction ruling 056 exists to let
    a reader draw — and without this row the class would offer no way to tell
    "the change did nothing" from "the instrument is blind again".
    """

    query = "masters winner"
    subject = _subject(captured, query)
    cands = _candidates(captured, query)

    assert match_class(subject, cands[0][0]) < MC3_PARTIAL_TOKENS, (
        "this row is a limit only because a BETTER-than-MC3 class owns the query; "
        "if that stops being true the probe is no longer a limit and must be re-graded"
    )
    assert len({_top1(subject, cands, coverage=cov) for cov in SWEEP}) == 1


def test_the_two_mc3_specimens_move_by_different_mechanisms(captured):
    """One probe would have been a coincidence; these two are a class.

    The Masters probe turns on a KIND INVERSION — the concept sits at lower
    coverage and a better `KIND_ORDER` rank, so admitting it changes who leads.
    The Champions League probe has no inversion at all (every candidate is
    `futures`): its cohort crosses the threshold TOGETHER and the answer still
    moves, because inside MC3 the tie breaks on `within_tier` and inside MC5 it
    breaks on `fragment_credit`. A set holding only the first would read that
    second mechanism as a null forever.
    """

    masters = _candidates(captured, "2027 the masters champion odds")
    champions = _candidates(captured, "2027 champions league winner odds")

    def kinds(cands):
        return {scorer.kind_rank(ev.kind) for ev, _ in cands}

    assert len(kinds(masters)) > 1, "the Masters specimen needs mixed kinds to invert"
    assert len(kinds(champions)) == 1, (
        "the Champions League specimen's whole value is that kind CANNOT be the "
        "explanation; if its candidate set gained a second kind, re-specimen it"
    )


# ---------------------------------------------------------------------------
# 2. MC2 — the class decides the answer, and where it merely appears.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query, expected, muted_top1", MC2_SPECIMENS)
def test_mc2_mute_moves_the_answer_where_the_class_claims(
    query, expected, muted_top1, captured
):
    """MC2 has no knob, so the discrimination test is the class itself: raise
    `PREFIX_MIN_LEN` above the last token and MC2 cannot fire, which is what a
    regression in that branch looks like from the outside.

    `muted_top1 is None` marks the LIMIT row — MC2 present, MC2 deciding
    nothing — which is #1867's Gap 2 stated as a probe instead of an argument.
    """

    subject = _subject(captured, query)
    cands = _candidates(captured, query)

    assert _top1(subject, cands) == expected
    muted = _top1(subject, cands, prefix_min=99)

    if muted_top1 is None:
        assert muted == expected, (
            f"{query!r} is recorded as the MC2 LIMIT, but muting MC2 moved its answer "
            f"to {muted} — it is now a discriminating probe and the class comment is wrong"
        )
    else:
        assert muted == muted_top1, (
            f"{query!r}: muting MC2 gives {muted}, not the recorded {muted_top1}"
        )
        assert muted != expected


def test_the_mc2_limit_row_is_full_of_mc2_and_grades_none_of_it(captured):
    """Why 'MC2 appears in the candidate set' is not coverage.

    FOUR of `manchester unite`'s seven candidates score MC2. A coverage table
    counting probes whose sets contain an MC2 row would score this query as
    solid MC2 coverage — and muting MC2 entirely leaves rank 1 untouched,
    because MC1B is checked first and owns the top three. This is the measured
    content of "graded only by accident", and the reason the two probes above
    had to be found rather than counted.
    """

    subject = _subject(captured, "manchester unite")
    cands = _candidates(captured, "manchester unite")
    classes = [match_class(subject, ev) for ev, _ in cands]

    assert classes.count(MC2_LAST_TOKEN_PREFIX) >= 4
    assert classes[0] == MC1B_OWN_NAME_PREFIX
    assert _top1(subject, cands) == _top1(subject, cands, prefix_min=99)


def test_new_ya_is_mc2_and_is_still_the_wrong_probe():
    """The `new ya` / `boston so` question, settled against the scorer.

    An earlier write-up of this class called `new ya` MC1B and chose `boston so`
    over it on that basis. The conclusion was right and the reason was not:
    `new ya` IS MC2, because `_query_prefixes_an_owned_name` folds the WHOLE
    string and `newya` is not a prefix of `newyorkyankees`. What disqualifies it
    is that its candidate set collapses uniformly when MC2 is muted, so it
    grades nothing — the same uniform-lift trap #1861 documented for MC4.

    Pinned here because a wrong reason for a right answer is the thing that gets
    copied into the next class.
    """

    yankees = Evidence(
        name="New York Yankees", aliases=("Yankees",), outcomes=(),
        kind="team", derived=False,
    )
    assert match_class("new ya", yankees) == MC2_LAST_TOKEN_PREFIX
    # The genuine MC1B shape, for contrast: one unfinished token that IS a live
    # prefix of a whole owned name (#4519).
    assert match_class("yank", yankees) == MC1B_OWN_NAME_PREFIX
    # ...and `boston so` is MC2 for the reason the class comment gives: `boston`
    # is complete, `so` prefixes `sox`, and `bostonso` prefixes no owned name.
    red_sox = Evidence(
        name="Boston Red Sox", aliases=("Boston", "Red Sox", "BOS"), outcomes=(),
        kind="team", derived=False,
    )
    assert match_class("boston so", red_sox) == MC2_LAST_TOKEN_PREFIX


def test_prefix_min_len_is_what_the_mute_actually_disables():
    """The mute above must disable MC2 and nothing else, or every MC2 assertion
    in this file is measuring a side effect."""

    assert PREFIX_MIN_LEN <= 4, "the specimens' last tokens must clear the floor"
    red_sox = Evidence(
        name="Boston Red Sox", aliases=("Boston", "Red Sox", "BOS"), outcomes=(),
        kind="team", derived=False,
    )
    old = scorer.PREFIX_MIN_LEN
    try:
        scorer.PREFIX_MIN_LEN = 99
        assert match_class("boston so", red_sox) == MC3_PARTIAL_TOKENS, (
            "muting MC2 must drop the specimen to MC3, not to MC5 or UNRANKABLE — "
            "otherwise the mute is testing admission, not the prefix class"
        )
    finally:
        scorer.PREFIX_MIN_LEN = old


# ---------------------------------------------------------------------------
# 3. The group-key judgment, measured rather than asserted.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", CONTROLS)
def test_the_neighbouring_test_probes_cannot_be_moved_by_this_knob(query, captured):
    """Why these canary rows may hold group keys distinct from `test`'s.

    `validate_registry` refuses a real-world group that spans splits, and it was
    right to: a subject measured in both cohorts is a contaminated read. The
    Masters and Oscars rows keep separate keys because their referents differ
    (the winner MARKETS, not the tournament CONCEPT) — and because the
    contamination is absent in fact: every `test` probe in the neighbourhood is
    MC0/MC1/MC1B on a fully-owned or single-token query, so class order puts it
    out of the MC3 knob's reach at every value.

    If this ever fails, the keys must merge and the specimens must move. That is
    the check — not a re-reading of the paragraph in the registry builder.
    """

    subject = _subject(captured, query)
    cands = _candidates(captured, query)
    assert len({_top1(subject, cands, coverage=cov) for cov in SWEEP}) == 1, (
        f"the `test` probe {query!r} IS reachable by PARTIAL_MIN_COVERAGE; the canary "
        "MC3 class now shares a real-world subject with the ledger cohort and its "
        "group keys are no longer honest"
    )


# ---------------------------------------------------------------------------
# 4. The registry rows exist, are declared, and did not touch the ledger cohort.
# ---------------------------------------------------------------------------


def test_the_mc3_and_mc2_classes_are_in_canary_and_declared():
    """#1867's first non-negotiable and its acceptance line, in one assertion.

    NOTE for whoever adds the NEXT class: this deliberately does not assert that
    `canary` holds only today's families. An earlier draft did, as a way of
    keeping the issue open in code — it passed while coverage was missing and
    failed the moment any valid new class landed, which is a test that defends
    the defect. What must hold is that every canary family is DECLARED in
    metadata and that `test` never moves.
    """

    registry = json.loads(_REGISTRY.read_text())
    probes, metadata = registry["probes"], registry["metadata"]

    canary = [p for p in probes if p["isolation"]["split"] == "canary"]
    mc3 = [p for p in canary if p["identity"]["gold_family"] == "mc3_partial"]
    mc2 = [p for p in canary if p["identity"]["gold_family"] == "mc2_prefix"]

    assert len(mc3) == len(MC3_SPECIMENS) == metadata["mc3_probes"]
    assert len(mc2) == len(MC2_SPECIMENS) == metadata["mc2_probes"]
    assert {p["presentation"]["query"] for p in mc3} == {q for q, _, _ in MC3_SPECIMENS}
    assert {p["presentation"]["query"] for p in mc2} == {q for q, _, _ in MC2_SPECIMENS}
    assert all(p["lifecycle"]["difficulty"] == "discrimination" for p in mc3 + mc2)
    assert all(p["lifecycle"]["issue_gotcha"] == "#1867" for p in mc3 + mc2)

    # Every canary family is declared in metadata, and canary is their SUM — so a
    # class cannot be added without also being counted.
    declared = (
        metadata["outcome_evidence_probes"] + metadata["diacritic_probes"]
        + metadata["mc3_probes"] + metadata["mc2_probes"]
    )
    assert metadata["split_counts"]["canary"] == declared == len(canary)

    # ...and the §5 ledger cohort did not move. This is the acceptance line.
    assert metadata["split_counts"]["test"] == 46
    assert metadata["migrated"] == 46
    test_split = [p for p in probes if p["isolation"]["split"] == "test"]
    assert len(test_split) == 46
    assert sum(
        1 for p in test_split if p["lifecycle"]["known_failure_status"] == "pass"
    ) == 44


def test_the_new_classes_spread_across_real_world_groups():
    """Six probes, four groups — so one market resolving cannot take the class.

    The outcome-evidence class lost three specimens to expiry before anyone
    wrote its shelf-life note down; this asserts the diversification instead of
    describing it.
    """

    registry = json.loads(_REGISTRY.read_text())
    mine = [
        p for p in registry["probes"]
        if p["identity"]["gold_family"] in {"mc3_partial", "mc2_prefix"}
    ]
    groups = {p["isolation"]["real_world_group_key"] for p in mine}
    assert len(mine) == 6
    assert len(groups) >= 4, f"the class collapsed onto {groups}"

    test_groups = {
        p["isolation"]["real_world_group_key"]
        for p in registry["probes"] if p["isolation"]["split"] == "test"
    }
    assert not (groups & test_groups), (
        "a canary group key leaked into the ledger cohort; validate_registry "
        "refuses this, and the measured justification lives in "
        "test_the_neighbouring_test_probes_cannot_be_moved_by_this_knob"
    )
