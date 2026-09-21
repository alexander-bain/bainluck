"""#6985 — the spotlight stops blending a Georgia election with an Ohio one.

THE SPECIMEN, read off production `https://bainluck.com/politics` at
2026-09-21 19:55Z, the LEAD card of "Cross-source spotlight — Markets where
sources disagree" (the section sorts by delta descending, so the matcher's worst
mistakes rank top by construction):

    [Both]  [! 63.0pt spread]
    How many House seats will Democrats win in Georgia?
    5
    KALSHI  87.0%          POLYMARKET  24.0%
    Merged: 55.5%                    Disagree by 63.0pp

    market 59693678  kalshi      How many House seats will Democrats win in GEORGIA?
                                 ticker KXHOUSEWINSTATE-GAD-E5 — the state is in the id
    market 58840980  polymarket  How many House seats will the Democrats win in OHIO?

Two different elections in two different states. `Merged: 55.5%` is the mean of a
Georgia probability and an Ohio one, and the 63-point gap the badge calls source
disagreement was manufactured by our own pairing — a truth defect under the
standing ruling that the blend is the product.

## Why the fix is a categorical refusal and not a threshold

    georgia/ohio pair   jaccard 0.750   containment 0.857
    the FIFA duplicate  jaccard 0.750   containment 0.857

IDENTICAL. `test_no_threshold_can_separate_the_specimen_from_the_duplicate`
below pins that equality, because it is the whole argument: the one real
duplicate this predicate exists to catch — Kalshi "2027 FIFA Women's World Cup
Champion" beside Polymarket "FIFA Women's World Cup 2027 Winner" — scores the
same as the defect, so any bound that refuses Georgia/Ohio also refuses the
duplicate, and moving 0.72 / 0.85 would re-break #6537 and #6400 besides. What
separates them is not how much the titles differ but WHAT differs: `champion`
and `win` are one word twice; `georgia` and `ohio` are two elections.

## The scope, stated so a later widening is visible

The refusal is TWO-SIDED: each side must name a place the other does not. The
one-sided case — a place on one side, none on the other — is #6985's ORIGINAL
Spotify specimen ("#2 Artist on Spotify U.S. in 2026?" against the global "#2
Spotify Artist 2026") and it is NOT fixed here, deliberately: the same shape is
#6537's "the U.S. House" beside "the House in 2026", which IS one question.
`test_the_one_sided_residual_is_unchanged` pins the residual as a known miss
rather than a silent one, the way #4446's Fed pair is pinned.

The directive that routed this asked for an ADMITTED control beside the refused
one, because a tighter matcher fails SILENTLY — an under-paired spotlight leaves
nothing on the page for a reader to notice. Every admit below is that control.
"""

from types import SimpleNamespace

import pytest

from app.utils.cross_source_matching import (
    _conservative_near_match_score,
    _near_match_signature,
    find_cross_source_markets,
    is_same_question,
    source,
)

KALSHI_GEORGIA = "How many House seats will Democrats win in Georgia?"
POLY_OHIO = "How many House seats will the Democrats win in Ohio?"

FIFA_KALSHI = "2027 FIFA Women's World Cup Champion"
FIFA_POLY = "FIFA Women's World Cup 2027 Winner"


def _score(left: str, right: str):
    return _conservative_near_match_score(
        _near_match_signature(left), _near_match_signature(right)
    )


# ---------------------------------------------------------------------------
# The specimen
# ---------------------------------------------------------------------------


def test_the_specimen_is_refused():
    """Georgia and Ohio are two elections, so there is no pair to report."""
    assert not is_same_question(KALSHI_GEORGIA, POLY_OHIO)


def test_no_threshold_can_separate_the_specimen_from_the_duplicate():
    """The argument for a categorical guard, pinned as an equality.

    If this ever stops being equal, a threshold COULD separate them and someone
    should re-read whether the guard is still the right shape. Until then, any
    bound that refuses the specimen also refuses the duplicate.
    """
    left, right = _near_match_signature(KALSHI_GEORGIA), _near_match_signature(POLY_OHIO)
    overlap = len(left[0] & right[0])
    specimen = (
        overlap / len(left[0] | right[0]),
        overlap / min(len(left[0]), len(right[0])),
    )

    left, right = _near_match_signature(FIFA_KALSHI), _near_match_signature(FIFA_POLY)
    overlap = len(left[0] & right[0])
    duplicate = (
        overlap / len(left[0] | right[0]),
        overlap / min(len(left[0]), len(right[0])),
    )

    assert specimen == duplicate == (0.75, pytest.approx(6 / 7))
    # ...and the guard, which does not read either number, tells them apart.
    assert _score(KALSHI_GEORGIA, POLY_OHIO) is None
    assert _score(FIFA_KALSHI, FIFA_POLY) == 0.75


@pytest.mark.parametrize(
    "left,right",
    [
        # The specimen's own family — the same Kalshi series, other states.
        (KALSHI_GEORGIA, POLY_OHIO),
        (
            "How many House seats will Democrats win in Louisiana?",
            "How many House seats will the Democrats win in Ohio?",
        ),
        # The directional qualifier IS the place: without `north`/`south` in the
        # vocabulary this pair reads jaccard 0.800 / containment 0.889 and folds.
        (
            "Will North Korea test an intercontinental ballistic missile before July?",
            "Will South Korea test an intercontinental ballistic missile before July?",
        ),
        # Two governor races, same office, same year.
        ("Texas Governor election winner?", "Florida Governor election winner?"),
        # Two countries, the case #6537's tokenizer note is about.
        ("Who wins the U.K. general election?", "Who wins the U.S. general election?"),
        # "Everywhere" against "the U.S." — /entertainment serves BOTH halves of
        # this family as live pairs ("#2 US Netflix Movie this week?" at delta
        # 16.0 and "#2 Global Netflix Movie this week?" at 52.6, each correctly
        # matched to its own twin). The CROSSED pair is refused, but by the
        # thresholds (jaccard 0.571), NOT by the place guard: `global` is not in
        # the place vocabulary. Measured, not assumed — an earlier revision of
        # this ship added it and this control passed with the token removed,
        # which is how the addition was found to be unearned. Pinned here so the
        # refusal is known to be threshold-borne if someone widens those.
        ("#2 US Netflix Movie this week?", "What will be the #2 global Netflix movie this week?"),
    ],
)
def test_two_different_places_are_never_one_question(left, right):
    assert not is_same_question(left, right)


# ---------------------------------------------------------------------------
# The admitted controls — a tighter matcher fails silently, so these are the
# half of the fence that has to be here
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "left,right",
    [
        # The one real duplicate the predicate exists to catch. No place at all.
        (FIFA_KALSHI, FIFA_POLY),
        # A paraphrase that names the SAME place on both sides.
        (
            "Will Donald Trump win the 2028 US presidential election?",
            "Donald Trump to win the 2028 US presidency?",
        ),
        (KALSHI_GEORGIA, "How many House seats will the Democrats win in Georgia?"),
        # Two spellings of one place are one place: without the alias table
        # these read as a two-sided difference and would be refused.
        (
            "Next French Presidential Election Winner",
            "Next France Presidential Election Winner",
        ),
        (
            "Who wins the 2028 USA presidential election?",
            "Who wins the 2028 US presidential election?",
        ),
        # Both halves of the Netflix family, as production serves them today.
        (
            "#2 US Netflix Movie this week?",
            "What will be the #2 US Netflix movie this week?",
        ),
        (
            "#2 Global Netflix Movie this week?",
            "What will be the #2 global Netflix movie this week?",
        ),
    ],
)
def test_a_genuine_paraphrase_still_pairs(left, right):
    assert is_same_question(left, right)


def test_the_one_sided_residual_is_unchanged():
    """#6985's ORIGINAL Spotify specimen, pinned as a known miss.

    A U.S.-scoped Kalshi market beside its GLOBAL Polymarket twin still pairs.
    That is wrong and it stays open on #6985 — but the same one-sided shape is
    #6537's "the U.S. House" beside "the House", which is one question, so it
    cannot be refused by this guard without taking #6537 with it. If someone
    lands the scope-token half, this test fails and tells them so.
    """
    assert is_same_question("#2 Artist on Spotify U.S. in 2026?", "#2 Spotify Artist 2026")
    assert is_same_question("Which party will win the U.S. House?", "Which party will win the House?")


# ---------------------------------------------------------------------------
# End to end — what the reader stops being shown
# ---------------------------------------------------------------------------


def _outcome(name: str, probability: float) -> SimpleNamespace:
    return SimpleNamespace(name=name, current_probability=probability)


def _market(market_id: int, name: str, src: str, outcomes: list) -> SimpleNamespace:
    return SimpleNamespace(id=market_id, name=name, source=src, outcomes=outcomes)


def _row_fn(market):
    """The shape all three category routes' `_market_row` produce."""
    if not market.outcomes:
        return None
    ranked = sorted(
        market.outcomes, key=lambda o: float(o.current_probability or 0), reverse=True
    )
    return {
        "q": market.name,
        "prob": round(float(ranked[0].current_probability or 0) * 100, 1),
        "src": source(market),
        "market_id": market.id,
        "top_outcomes": [
            {"name": o.name, "prob": round(float(o.current_probability or 0) * 100, 1)}
            for o in ranked[:3]
        ],
    }


def test_the_spotlight_serves_no_row_for_the_specimen():
    """The production ladders, verbatim from the issue's measured table.

    Both sides price an outcome named "5", so the pair aligns and the row the
    reader saw was fully built — 87.0 against 24.0, delta 63.0. The refusal has
    to happen at the match, not at alignment.
    """
    markets = [
        _market(
            59693678,
            KALSHI_GEORGIA,
            "kalshi",
            [
                _outcome("Below 5", 0.03),
                _outcome("5", 0.87),
                _outcome("6", 0.07),
                _outcome("7", 0.03),
                _outcome("Above 7", 0.03),
            ],
        ),
        _market(
            58840980,
            POLY_OHIO,
            "polymarket",
            [
                _outcome("4", 0.085),
                _outcome("5", 0.24),
                _outcome("6", 0.415),
                _outcome("7+", 0.26),
            ],
        ),
    ]
    assert find_cross_source_markets(markets, market_row_fn=_row_fn) == []


def test_the_same_state_on_both_sides_still_produces_the_row():
    """The end-to-end admit: nothing about the ladders or the alignment moved,
    so a real Georgia-against-Georgia disagreement is still served."""
    markets = [
        _market(
            59693678,
            KALSHI_GEORGIA,
            "kalshi",
            [_outcome("5", 0.87), _outcome("6", 0.07), _outcome("7", 0.03)],
        ),
        _market(
            58840980,
            "How many House seats will the Democrats win in Georgia?",
            "polymarket",
            [_outcome("5", 0.24), _outcome("6", 0.415), _outcome("7", 0.26)],
        ),
    ]
    rows = find_cross_source_markets(markets, market_row_fn=_row_fn)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "5"
    assert rows[0]["delta"] == 63.0
