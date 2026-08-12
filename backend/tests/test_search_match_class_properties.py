"""Property suite for the tier-lexicographic search scorer (ruling 041, Q325).

**This is a RECONSTRUCTION.** The ratified spec carried twelve property
invariants and their enumeration was lost with the document (delivered
untracked, never committed — which is why `docs/search-scoring-spec.md` now
exists and is committed with the code it governs). These twelve are rebuilt from
the tier semantics, and five of them are named verbatim in the reconstruction
brief: tier order is inviolable, owned-evidence exclusion holds for every
concept, MC0 is exactly-equal-unfolded, kind-order breaks ties deterministically,
and adding evidence never demotes. The other seven are derived from the same
semantics and are marked as such. They are not claimed to BE the original twelve.

Properties are exhaustive over a small deliberate space rather than randomised:
a scorer's invariants are about ordering between a handful of shapes, and an
enumerated space cannot flake, cannot depend on a seed, and cannot depend on the
clock (gotcha #44).
"""

import itertools

import pytest

from app.utils import search_match_class as smc
from app.utils.search_match_class import (
    MC0_EXACT,
    MC1_ALL_TOKENS,
    MC2_LAST_TOKEN_PREFIX,
    MC3_PARTIAL_TOKENS,
    MC4_OUTCOME_ONLY,
    MC5_FRAGMENT,
    UNRANKABLE,
    Evidence,
    match_class,
    rank,
    rank_key,
)

ALL_CLASSES = [
    MC0_EXACT,
    MC1_ALL_TOKENS,
    MC2_LAST_TOKEN_PREFIX,
    MC3_PARTIAL_TOKENS,
    MC4_OUTCOME_ONLY,
    MC5_FRAGMENT,
]

QUERY = "super bowl"

#: One specimen per class, all against the SAME query, so any pair can be
#: compared directly. Verified by `test_p0_the_specimen_table_is_honest`.
SPECIMENS: dict[int, Evidence] = {
    MC0_EXACT: Evidence(name="Super Bowl", kind="market"),
    MC1_ALL_TOKENS: Evidence(name="Super Bowl LXI Winner", kind="market"),
    MC2_LAST_TOKEN_PREFIX: Evidence(name="Super Bowling Night", kind="market"),
    MC3_PARTIAL_TOKENS: Evidence(name="Bowl Game Champion", kind="market"),
    MC4_OUTCOME_ONLY: Evidence(
        name="Big Game Winner", outcomes=("Super Bowl",), kind="market"
    ),
    MC5_FRAGMENT: Evidence(name="Supermarket Bowlers Guild", kind="market"),
}


def test_p0_the_specimen_table_is_honest():
    """Guard on the guard: every specimen really is in the class it claims.

    Without this, a specimen that silently drifted into a different class would
    make the ordering properties below pass while comparing the wrong things.
    """
    for expected, ev in SPECIMENS.items():
        assert match_class(QUERY, ev) == expected, (
            f"specimen for class {expected} actually scores "
            f"{match_class(QUERY, ev)}: {ev.name!r}"
        )


# --- P1 (named): tier order is inviolable ----------------------------------


def test_p1_tier_order_is_inviolable_across_every_pair():
    for better, worse in itertools.combinations(ALL_CLASSES, 2):
        kb = rank_key(QUERY, SPECIMENS[better])
        kw = rank_key(QUERY, SPECIMENS[worse])
        assert kb < kw, f"class {better} must sort before {worse}"


def test_p1b_no_within_tier_signal_can_cross_a_tier():
    """The strongest possible lower-class candidate still loses to the weakest
    possible higher-class one. This is the property the knobs are constrained
    BY — it is what makes tuning them safe."""
    strongest_low = Evidence(
        name="Supermarket Bowlers Guild",
        kind="market",                       # best kind
        sport_key="basketball_nba",          # best prominence
        within_tier=(-(10**9),),             # absurdly good within-tier signal
    )
    weakest_high = Evidence(
        name="Bowl Game Champion",           # only MC3
        kind="team",                         # worst kind
        sport_key="obscure_league",          # worst prominence
        within_tier=(10**9,),
    )
    assert match_class(QUERY, strongest_low) == MC5_FRAGMENT
    assert match_class(QUERY, weakest_high) == MC3_PARTIAL_TOKENS
    assert rank_key(QUERY, weakest_high) < rank_key(QUERY, strongest_low)


@pytest.mark.parametrize(
    "knob,value",
    [
        ("TRIGRAM_FLOOR", 0.0),
        ("TRIGRAM_FLOOR", 1.0),
        ("MIN_FRAGMENT_LEN", 1),
        ("PREFIX_MIN_LEN", 1),
        ("PARTIAL_MIN_COVERAGE", 0.0),
        ("PARTIAL_MIN_COVERAGE", 1.0),
    ],
)
def test_p1c_tier_order_survives_every_knob_extreme(monkeypatch, knob, value):
    """A knob at either extreme may change WHICH class a candidate lands in; it
    may never change the order BETWEEN classes."""
    monkeypatch.setattr(smc, knob, value)
    keys = []
    for cls in ALL_CLASSES:
        k = rank_key(QUERY, SPECIMENS[cls])
        if k is not None:
            keys.append((match_class(QUERY, SPECIMENS[cls]), k))
    for (ca, ka), (cb, kb) in itertools.combinations(keys, 2):
        if ca != cb:
            assert (ka < kb) == (ca < cb)


# --- P2 (named): owned-evidence exclusion ----------------------------------


def test_p2_derived_evidence_is_unrankable_not_merely_demoted():
    derived = Evidence(name="Super Bowl", kind="event_concept", derived=True)
    assert match_class(QUERY, derived) is UNRANKABLE
    assert rank_key(QUERY, derived) is None


def test_p2b_the_emmys_black_hole_cannot_recur():
    """The measured failure, verbatim: four gold queries answered with an Emmys
    concept that had matched none of them. A concept derived from a member
    market owns no evidence about the query and must not appear at all."""
    emmys = Evidence(name="Emmys", kind="event_concept", derived=True)
    for q in ("super bowl", "world series", "wwe", "stranger things"):
        assert match_class(q, emmys) is UNRANKABLE
        assert rank(q, [(emmys, "emmys")]) == []


def test_p2c_a_concept_that_owns_the_match_still_ranks():
    """Owned-evidence-only is not "concepts rank last" — a concept whose own
    name matches is a first-class answer. `british open` must still be able to
    reach the golf concept."""
    concept = Evidence(name="The Open Championship", aliases=("British Open",),
                       kind="event_concept")
    assert match_class("british open", concept) == MC0_EXACT
    team_brito = Evidence(name="Brito", kind="team")
    assert match_class("british open", team_brito) == MC5_FRAGMENT
    assert rank("british open", [(team_brito, "brito"), (concept, "open")]) == [
        "open", "brito",
    ]


def test_p2d_exclusion_holds_for_every_concept_shape():
    for name, aliases in [
        ("Emmys", ()), ("Oscars", ("Academy Awards",)), ("", ()),
        ("Super Bowl", ("The Big Game",)),
    ]:
        ev = Evidence(name=name, aliases=aliases, kind="event_concept", derived=True)
        assert match_class(QUERY, ev) is UNRANKABLE


# --- P3 (named): MC0 is exactly-equal-unfolded -----------------------------


def test_p3_mc0_is_exact_and_unfolded():
    assert match_class("celtics", Evidence(name="Celtics")) == MC0_EXACT
    assert match_class("Celtics", Evidence(name="celtics")) == MC0_EXACT
    # Accents and punctuation do NOT meet at MC0 — they meet at MC1.
    assert match_class("sao paulo", Evidence(name="São Paulo")) != MC0_EXACT
    assert match_class("sao paulo", Evidence(name="São Paulo")) == MC1_ALL_TOKENS
    assert match_class("celtic", Evidence(name="Celtics")) != MC0_EXACT


def test_p3b_mc0_matches_an_alias_as_readily_as_the_name():
    ev = Evidence(name="The Open Championship", aliases=("British Open", "The Open"))
    assert match_class("british open", ev) == MC0_EXACT
    assert match_class("the open", ev) == MC0_EXACT


# --- P4 (named): kind order breaks ties deterministically ------------------


def test_p4_kind_order_is_market_event_team():
    same = "Super Bowl LXI Winner"
    keys = {
        kind: rank_key(QUERY, Evidence(name=same, kind=kind))
        for kind in ("market", "event", "team")
    }
    assert keys["market"] < keys["event"] < keys["team"]


def test_p4b_kind_order_is_total_and_repeatable():
    # Aggregates (concept, hub) above their members, then the ratified
    # market > event > team. The aggregate placement is a reconstruction
    # judgment and was MEASURED into this order — the opposite placement cost
    # seven gold probes. See KIND_ORDER's comment.
    kinds = ["event_concept", "hub", "market", "event", "team"]
    same = "Super Bowl LXI Winner"
    order = sorted(kinds, key=lambda k: rank_key(QUERY, Evidence(name=same, kind=k)))
    assert order == kinds
    assert order == sorted(
        kinds, key=lambda k: rank_key(QUERY, Evidence(name=same, kind=k))
    )


# --- P5 (named): adding evidence never demotes -----------------------------


@pytest.mark.parametrize("q", ["super bowl", "bowl", "super", "sup", "wwe"])
def test_p5_adding_an_alias_never_demotes(q):
    base = Evidence(name="Big Game Winner", kind="market")
    for extra in ("Super Bowl", "wwe", "Something Else Entirely"):
        richer = Evidence(name="Big Game Winner", aliases=(extra,), kind="market")
        b, r = match_class(q, base), match_class(q, richer)
        if b is UNRANKABLE:
            continue
        assert r is not UNRANKABLE, "adding evidence made a ranked entity vanish"
        assert r <= b, f"adding alias {extra!r} demoted {q!r}: {b} -> {r}"


@pytest.mark.parametrize("q", ["super bowl", "bowl", "wwe"])
def test_p5b_adding_an_outcome_never_demotes(q):
    base = Evidence(name="Big Game Winner", kind="market")
    richer = Evidence(name="Big Game Winner", outcomes=("Super Bowl", "wwe"),
                      kind="market")
    b, r = match_class(q, base), match_class(q, richer)
    if b is not UNRANKABLE:
        assert r is not UNRANKABLE and r <= b


# --- P6..P12 (derived from the tier semantics) -----------------------------


def test_p6_a_fragment_never_outranks_a_token_match():
    """The second measured failure family, verbatim. Each pair is a real
    production result from 2026-08-12 21:48Z."""
    cases = [
        ("ai", Evidence(name="1. FC Kaiserslautern", kind="team"),
         Evidence(name="Which AI model is best?", kind="market")),
        ("ipo", Evidence(name="Asteras Tripolis", kind="team"),
         Evidence(name="Which company will IPO in 2026?", kind="market")),
        ("british open", Evidence(name="Brito", kind="team"),
         Evidence(name="British Open Winner", kind="market")),
    ]
    for q, fragment, real in cases:
        assert match_class(q, real) < match_class(q, fragment), q
        assert rank(q, [(fragment, "bad"), (real, "good")])[0] == "good", q


def test_p6b_hurricane_is_a_kind_order_case_not_a_fragment_case():
    """The ruling's own example, and it is worth separating from P6.

    `Carolina Hurricanes` is an HONEST MC1 match for `hurricane` — "Hurricanes"
    folds to "hurricane". No tier can separate these two, and none should: what
    the ruling settles is that when a market and a team match equally well, the
    market is the answer. This is the case kind order exists for.
    """
    team = Evidence(name="Carolina Hurricanes", kind="team")
    market = Evidence(name="Hurricane landfall in 2026?", kind="market")
    assert match_class("hurricane", team) == match_class("hurricane", market) == MC1_ALL_TOKENS
    assert rank("hurricane", [(team, "team"), (market, "market")]) == ["market", "team"]


def test_p7_full_ties_preserve_input_order():
    a = Evidence(name="Super Bowl LXI Winner", kind="market")
    b = Evidence(name="Super Bowl LX Winner", kind="market")
    assert rank_key(QUERY, a) == rank_key(QUERY, b)
    assert rank(QUERY, [(a, "a"), (b, "b")]) == ["a", "b"]
    assert rank(QUERY, [(b, "b"), (a, "a")]) == ["b", "a"]


@pytest.mark.parametrize("q", ["", "   ", "\t", "!!!", "—"])
def test_p8_a_contentless_query_ranks_nothing(q):
    assert match_class(q, Evidence(name="Super Bowl")) is UNRANKABLE
    assert rank(q, [(Evidence(name="Super Bowl"), "x")]) == []


def test_p9_outcome_evidence_never_beats_a_name_match():
    name_match = Evidence(name="Super Bowl Winner", kind="team")
    outcome_match = Evidence(name="Unrelated Market",
                             outcomes=("Super Bowl",), kind="market")
    assert match_class(QUERY, name_match) < match_class(QUERY, outcome_match)
    assert rank(QUERY, [(outcome_match, "outcome"), (name_match, "name")]) == [
        "name", "outcome",
    ]


def test_p10_prominence_breaks_same_class_same_kind_ties_only():
    big = Evidence(name="Boston Bruins", kind="team", sport_key="icehockey_nhl")
    small = Evidence(name="Belmont Bruins", kind="team", sport_key="ncaab_other")
    assert match_class("bruins", big) == match_class("bruins", small)
    assert rank("bruins", [(small, "belmont"), (big, "boston")]) == [
        "boston", "belmont",
    ]
    # ...but prominence cannot rescue a worse class.
    prominent_fragment = Evidence(name="Brutus Bruinsdottir Fan Club", kind="team",
                                  sport_key="icehockey_nhl")
    plain_exact = Evidence(name="Bruins", kind="team", sport_key=None)
    assert rank("bruins", [(prominent_fragment, "frag"), (plain_exact, "exact")])[0] == "exact"


def test_p10b_mc2_is_a_PREFIX_match_not_a_containment_match():
    """Found by a surviving mutation: swapping `startswith` for `in` changed
    nothing any test could see.

    MC2 exists for the typeahead case — the user is mid-way through the last
    word — so it must anchor at the START of a name token. Containment would
    quietly promote interior fragments into a class above MC3, which is the
    fragment family this ruling exists to demote.
    """
    ev = Evidence(name="Super Bowling Night", kind="market")
    # "bowl" IS a prefix of "bowling": MC2.
    assert match_class("super bowl", ev) == MC2_LAST_TOKEN_PREFIX
    # "owl" is INSIDE "bowling" but does not start it: MC2 must not apply.
    assert match_class("super owl", ev) == MC3_PARTIAL_TOKENS


def test_p11_folding_is_confined_to_mc1_and_below():
    plural = Evidence(name="Patriot")
    assert match_class("patriots", plural) == MC1_ALL_TOKENS
    assert match_class("patriots", plural) != MC0_EXACT
    assert match_class("patriot", Evidence(name="Patriot")) == MC0_EXACT


def test_p12_rank_drops_derived_evidence_and_nothing_else():
    """The scorer REORDERS; it does not filter.

    Only derived-only evidence is UNRANKABLE. A weak-but-owned candidate sinks
    to MC5 and stays in the answer, because recall was decided by the SQL that
    built the candidate set — a scorer that also filters can empty a result set
    while reporting that it ordered one.
    """
    cands = [
        (Evidence(name="Super Bowl", kind="market"), "keep-mc0"),
        (Evidence(name="Emmys", kind="event_concept", derived=True), "drop-derived"),
        (Evidence(name="Totally Unrelated", kind="team"), "keep-mc5"),
        (Evidence(name="Super Bowl LXI", kind="market"), "keep-mc1"),
    ]
    out = rank(QUERY, cands)
    assert out == ["keep-mc0", "keep-mc1", "keep-mc5"]
    for ev, label in cands:
        assert (rank_key(QUERY, ev) is None) == label.startswith("drop")


def test_p12b_a_better_fragment_orders_ahead_inside_mc5():
    # Measured credits against "super bowl": 0.500 vs 0.000. `Superb Owl
    # Sanctuary` is deliberately NOT used here — it scores 0.280, just under
    # TRIGRAM_FLOOR, so it earns no credit. That is the knob doing its job, and
    # the specimen was swapped rather than the floor lowered to fit it: a knob
    # move is only accepted against the measured gold set, never against a test
    # someone wrote five minutes earlier.
    near = Evidence(name="Souper Bowle", kind="team")
    far = Evidence(name="Totally Unrelated", kind="team")
    assert match_class(QUERY, near) == match_class(QUERY, far) == MC5_FRAGMENT
    assert rank(QUERY, [(far, "far"), (near, "near")]) == ["near", "far"]
