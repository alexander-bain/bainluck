"""What the OUTCOME-EVIDENCE probe class can and cannot tell apart (ruling 056, #1861).

WHY THIS FILE EXISTS
--------------------
`-44` (#1843) deployed ALONE as v3807, carried a real ranking change, and moved
**zero** of the 46 gold probes — byte-identical per-probe dispositions against
v3806. Ruling 056 forbids writing that down as "the change did nothing": a null
read indicts the INSTRUMENT until the probe set is shown to discriminate that
class of change.

So this file is the demonstration. It does not test Search; it tests **the probe
class**, which is the thing #1861 says nobody had ever checked. The registry was
assembled for COVERAGE of Alex's query set and has never once been asked which
tiers it can separate.

THE MEASURED RESULT, STATED UP FRONT
------------------------------------
#1843 widened ranking evidence from the three DISPLAY outcomes to every owned
outcome. Whether that moves `entity_top_1` depends entirely on **whether the
lift is uniform across the rival set**, and the rival set decides that, not the
change:

* **Uniform (4 of 5 specimens).** Every candidate owns the queried outcome below
  its display cut, so all of them go MC5 -> MC4 together. Relative order is
  untouched and top-1 cannot move. *This is why 46 probes read identical on
  v3807.*
* **Non-uniform (`club kid`).** A rival carries the outcome INSIDE its own top 3,
  so it already scored MC4 before the change and did not move while the others
  did. Top-1 moves. Found by building this test, not by predicting it.
* **The substring accident (`fjord`).** The pre-change winner does not own the
  outcome at all — it merely contains the letters. This is #1843's own stated
  specimen: *"a market that owns the answer was losing to unrelated substring
  accidents."* Both sides here are REAL production rows.

All three are asserted below, because a class whose limits are undocumented gets
over-read the first time it returns green.

The evidence is a frozen production capture
(`scripts/evals/outcome_evidence_discrimination_fixtures.json`, v3808,
2026-08-14, 155 outcomes across 7 markets), so the proof is deterministic and
survives the 2027 Oscars settling.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.utils.search_match_class import (
    MC3_PARTIAL_TOKENS,
    MC4_OUTCOME_ONLY,
    MC5_FRAGMENT,
    Evidence,
    match_class,
    rank,
)

_EVALS = Path(__file__).resolve().parents[1] / "scripts" / "evals"
_FIXTURE = _EVALS / "outcome_evidence_discrimination_fixtures.json"
_REGISTRY = _EVALS / "search_gold_probes.json"

#: The market every outcome-evidence probe expects at rank 1.
TARGET_MARKET = "6173044"

#: The display cut #1843 was about: `_build_search_top_outcomes` shows three.
DISPLAY_CUT = 3

#: (query, the outcome rank that answers it inside TARGET_MARKET).
#: Re-derived from the fixture by the first test rather than trusted.
SPECIMENS = [
    ("werwulf", 17),
    ("elsinore", 35),
    ("behemoth", 9),
    ("minotaur", 31),
    ("club kid", 37),
]

#: The four whose lift is uniform across the production rival set. `club kid` is
#: excluded and gets its own test, because a rival displays it in ITS top three.
UNIFORM_SPECIMENS = [row for row in SPECIMENS if row[0] != "club kid"]

#: Ranking tiers that mean "the NAME matched". MC5 is the floor, not a match —
#: `match_class` never returns None for non-derived evidence, so "no name match"
#: has to be spelled as "did not reach a name tier".
NAME_TIERS = range(0, MC3_PARTIAL_TOKENS + 1)


@pytest.fixture(scope="module")
def markets() -> dict[str, dict]:
    return json.loads(_FIXTURE.read_text())["markets"]


def _evidence(market: dict, *, truncate: bool) -> Evidence:
    """The Evidence the scorer sees, under one of the two regimes.

    `truncate=True` reproduces PRE-#1843: the pool item carried only the three
    display outcomes, so the scorer's view of what the market owned stopped at
    the display cut. `truncate=False` is the deployed behaviour.
    """

    outcomes = market["outcomes"][:DISPLAY_CUT] if truncate else market["outcomes"]
    return Evidence(
        name=market["name"],
        aliases=(),
        outcomes=tuple(outcomes),
        kind="futures",
        derived=False,
        sport_key="entertainment",
    )


def _ranked(query: str, markets: dict[str, dict], *, truncate: bool) -> list[str]:
    candidates = [
        (_evidence(market, truncate=truncate), market_id)
        for market_id, market in markets.items()
    ]
    return rank(query, candidates)


# ---------------------------------------------------------------------------
# 1. The specimens are what the registry says they are.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query,expected_rank", SPECIMENS)
def test_specimen_answers_sit_outside_the_display_cut(query, expected_rank, markets):
    """The whole class rests on this: the answer is NOT in the displayed three.

    If a specimen ever drifts inside the cut, the probe silently stops testing
    what it was built to test and starts passing for the wrong reason — the
    exact failure ruling 049 is about.
    """

    names = [name.lower() for name in markets[TARGET_MARKET]["outcomes"]]
    positions = [i for i, name in enumerate(names, start=1) if query in name]

    assert positions == [expected_rank], (
        f"{query!r} was specimened at outcome rank {expected_rank}; the fixture "
        f"puts it at {positions}"
    )
    assert expected_rank > DISPLAY_CUT, (
        f"{query!r} sits at rank {expected_rank}, INSIDE the top-{DISPLAY_CUT} "
        "display cut — it cannot test outcome evidence"
    )


@pytest.mark.parametrize("query,_rank", SPECIMENS)
def test_specimen_reaches_no_name_tier(query, _rank, markets):
    """The market's NAME must be silent, or the probe grades MC1, not MC4."""

    name_only = Evidence(
        name=markets[TARGET_MARKET]["name"],
        aliases=(),
        outcomes=(),
        kind="futures",
        derived=False,
        sport_key="entertainment",
    )
    assert match_class(query, name_only) not in NAME_TIERS, (
        f"{query!r} matches 'Oscar winner: Best Picture' on its NAME; this probe "
        "would grade name matching, not outcome evidence"
    )


# ---------------------------------------------------------------------------
# 2. What the class DOES grade.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query,_rank", SPECIMENS)
def test_full_outcomes_score_mc4_and_truncation_drops_them_to_mc5(query, _rank, markets):
    """#1843, stated as a property: the class lift is real and re-cappable.

    This is the regression guard the class buys — at the SCORER seam. Cap the
    scorer's view of owned outcomes and this fails.

    It does NOT guard the route seam, and the distinction was found by planning
    the mutation list rather than by running it (gotcha #131): this file builds
    `Evidence` directly, so re-capping `_search_owned_outcome_names` itself is
    invisible here. That call site is owned by
    `tests/test_typeahead_evidence_boundary.py`, which asserts the unbounded walk
    at its source. Both are in this class's oracle set
    (`scripts/evals/outcome_evidence_class_mutations.py`) precisely because
    neither covers the other.

    The re-cap shape matters because it has now shipped three times — #1836's
    team pool, #1839's dedup guard, and #1843 itself.
    """

    target = markets[TARGET_MARKET]

    assert match_class(query, _evidence(target, truncate=False)) == MC4_OUTCOME_ONLY
    assert match_class(query, _evidence(target, truncate=True)) == MC5_FRAGMENT


def test_the_owner_beats_a_real_substring_accident(markets):
    """#1843's own stated specimen, with BOTH sides taken from production.

    Query `fjord`. The film "Fjord" is a Best Picture nominee at outcome rank 7,
    outside the display cut. "FH Hafnarfjordur vs. Vikingur Reykjavik" (market
    58773117, live on v3808) merely CONTAINS the letters — `hafnarfjordur` does
    not start with `fjord`, so it cannot reach MC2 and lands on the MC5 floor.

    Pre-#1843 both were MC5 and the accident won on input order alone.
    Post-#1843 the owner is MC4 and the accident cannot beat it. That is the
    only shape in which outcome evidence changes an answer.

    `fjord` is deliberately NOT a gold probe: production ALSO carries
    "Chicoutimi—Le Fjord By-Election Winner", which matches on its own name and
    legitimately outranks both, making the referent a genuine ambiguity. It is
    unfit as a gold answer and perfect as a ranking specimen.
    """

    query = "fjord"
    accident = Evidence(
        name="FH Hafnarfjordur vs. Vikingur Reykjavik",
        aliases=(),
        outcomes=("FH Hafnarfjordur", "Vikingur Reykjavik"),
        kind="futures",
        derived=False,
        sport_key="soccer",
    )
    assert match_class(query, accident) == MC5_FRAGMENT

    owner_full = _evidence(markets[TARGET_MARKET], truncate=False)
    owner_capped = _evidence(markets[TARGET_MARKET], truncate=True)
    assert match_class(query, owner_full) == MC4_OUTCOME_ONLY
    assert match_class(query, owner_capped) == MC5_FRAGMENT

    # Input order deliberately puts the accident FIRST, so a stable sort keeps it
    # there on a tie. Only a real class difference can overturn that.
    post = rank(query, [(accident, "accident"), (owner_full, "owner")])
    pre = rank(query, [(accident, "accident"), (owner_capped, "owner")])

    assert post[0] == "owner", "post-#1843 the outcome owner must beat the accident"
    assert pre[0] == "accident", (
        "pre-#1843 the accident won on input order — if this no longer holds, the "
        "property this class grades has changed and the class needs re-deriving"
    )


def test_mc4_requires_every_query_token_not_merely_one():
    """MC4's conjunction, asserted — and it was NOT, until a mutation said so.

    `OUTCOME_EVIDENCE_ROWS` justifies keeping the multi-token `club kid` specimen
    on the grounds that "a single-token-only class would leave that conjunction
    untested". Planning the mutation gate showed that claim was false: flipping
    `all(...)` to `any(...)` in `match_class` survived the whole oracle set,
    including `club kid`, because every candidate that owns "kid" happens to own
    "club" as well. The specimen exercises the multi-token PATH; it never
    exercised the CONJUNCTION.

    A partial owner must not reach MC4. Under `any(...)` it does, and a market
    ranks on half a query. (gotcha #131 — the mutation plan finding the missing
    instrument.)
    """

    partial_owner = Evidence(
        name="Oscar winner: Best Picture",
        aliases=(),
        outcomes=("Club Soda", "The Odyssey"),  # owns "club", never owns "kid"
        kind="futures",
        derived=False,
        sport_key="entertainment",
    )
    assert match_class("club kid", partial_owner) != MC4_OUTCOME_ONLY, (
        "a market owning only SOME query tokens reached MC4 — the conjunction is "
        "gone and outcome evidence now ranks on partial matches"
    )

    full_owner = Evidence(
        name="Oscar winner: Best Picture",
        aliases=(),
        outcomes=("Club Kid", "The Odyssey"),
        kind="futures",
        derived=False,
        sport_key="entertainment",
    )
    assert match_class("club kid", full_owner) == MC4_OUTCOME_ONLY


def test_club_kid_is_the_non_uniform_specimen_and_top_1_moves(markets):
    """The one specimen where the lift is NOT uniform, and top-1 therefore moves.

    "Club Kid" sits at outcome rank 37/38 in the Best Picture winner market, but
    at rank **3 of 17** in "Oscars 2027: Best Original Screenplay Winner"
    (58492236) — INSIDE its display cut. So that rival already scored MC4 before
    #1843 and did not move, while every other candidate went MC5 -> MC4.

    An unequal lift changes relative order, and relative order is all
    `entity_top_1` reads. This specimen is why the class is worth keeping rather
    than merely worth documenting: it is the existence proof that an
    outcome-evidence change CAN be graded top-1.

    Found by building this test. It was not predicted, and the four-uniform /
    one-non-uniform split is the actual answer to #1861.
    """

    query = "club kid"
    holders = {
        market_id: [
            i for i, name in enumerate(market["outcomes"], start=1)
            if query in name.lower()
        ][0]
        for market_id, market in markets.items()
        if any(query in name.lower() for name in market["outcomes"])
    }
    assert holders["58492236"] <= DISPLAY_CUT, (
        "the non-uniformity depends on 58492236 displaying 'Club Kid' in its top "
        f"{DISPLAY_CUT}; the fixture now puts it at rank {holders['58492236']}"
    )
    assert holders[TARGET_MARKET] > DISPLAY_CUT

    post = _ranked(query, markets, truncate=False)
    pre = _ranked(query, markets, truncate=True)

    assert pre[0] == "58492236", (
        "pre-#1843 the only market still scoring MC4 was the one displaying the "
        f"outcome; got {pre[0]}"
    )
    assert post[0] != pre[0], "an unequal lift must move top-1"


# ---------------------------------------------------------------------------
# 3. What the class does NOT grade. Asserted, so nobody over-reads it.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query,_rank", UNIFORM_SPECIMENS)
def test_a_uniform_lift_does_not_move_top_1(query, _rank, markets):
    """THE #1861 FINDING, pinned as an assertion.

    Against the real production rival set — seven Oscar markets that all own the
    same nominees below their display cuts — #1843 moves every candidate from
    MC5 to MC4 simultaneously. Relative order is untouched, so `entity_top_1`
    reads identical before and after. This is why 46 probes returned
    byte-identical dispositions on v3807, and why "no movement" was a fact about
    the instrument rather than about the change.

    If this ever fails it is not automatically a bug: it would mean the rival set
    diverged and the class became sensitive to a uniform lift. Re-read the §5
    ledger's `-44` row before changing anything here.
    """

    post = _ranked(query, markets, truncate=False)
    pre = _ranked(query, markets, truncate=True)

    assert post[0] == pre[0], (
        "top-1 moved under a uniform lift — the documented limit of this class no "
        "longer holds and docs/search-scoring-spec.md §5 needs restating"
    )
    # And the class genuinely DID change underneath that stable answer, which is
    # the whole point: invisible to top-1 is not the same as absent.
    target = markets[TARGET_MARKET]
    assert match_class(query, _evidence(target, truncate=False)) != match_class(
        query, _evidence(target, truncate=True)
    )


def test_the_canary_split_never_grows_the_ledger_cohort():
    """`test` is 46 probes. The §5 ledger is written against that number.

    Adding discrimination probes to `test` would silently move the denominator
    and make every prior read incomparable — a measurement defect committed while
    fixing one. This asserts the separation the registry promises.
    """

    registry = json.loads(_REGISTRY.read_text())
    probes = registry["probes"]
    metadata = registry["metadata"]

    # Added because planning M2 showed nothing asserted it: folding the new class
    # into `migrated` would restate 46 as 51 and overclaim coverage of Alex's
    # gold draft, with every other test still green (gotcha #131).
    assert metadata["migrated"] == 46, (
        "`migrated` counts probes taken FROM Alex's gold draft; the "
        "outcome-evidence class is not from it and must not inflate this number"
    )
    assert metadata["outcome_evidence_probes"] == len(SPECIMENS)
    # LAT-P058/#1881 added a SECOND canary class (diacritic folding). `canary` is
    # the place new probe classes go — that is what ruling 060 is for — so this
    # asserts what actually matters and did not weaken to accommodate it:
    #   * `test` is still exactly 46;
    #   * the outcome-evidence class is still exactly its own size;
    #   * `canary` is the SUM of the declared classes, so a class cannot be added
    #     without also being declared in metadata.
    diacritic_n = metadata.get("diacritic_probes", 0)
    assert metadata["split_counts"] == {
        "test": 46,
        "canary": len(SPECIMENS) + diacritic_n,
    }

    test_split = [p for p in probes if p["isolation"]["split"] == "test"]
    canary = [p for p in probes if p["isolation"]["split"] == "canary"]

    assert len(test_split) == 46, (
        f"the ledger cohort is 46 probes and this registry has {len(test_split)} — "
        "every entity_top_1 number in docs/search-scoring-spec.md §5 just became "
        "incomparable"
    )
    assert sum(
        1 for p in test_split if p["lifecycle"]["known_failure_status"] == "pass"
    ) == 44, "the 44-wide graded cohort changed size"

    families = {p["identity"]["gold_family"] for p in canary}
    assert families <= {"outcome_evidence", "diacritic_folding"}, (
        f"an undeclared probe class appeared in `canary`: {families}"
    )
    outcome_canary = [
        p for p in canary if p["identity"]["gold_family"] == "outcome_evidence"
    ]
    assert len(outcome_canary) == len(SPECIMENS)
    assert len(canary) == len(SPECIMENS) + diacritic_n
    assert all(p["lifecycle"]["difficulty"] == "discrimination" for p in canary)
    # No canary probe may leak into the `test` cohort's families either.
    assert not (families & {p["identity"]["gold_family"] for p in test_split})
