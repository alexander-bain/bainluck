"""#6537 — Discover asks who wins the U.S. House ONCE, not twice.

THE SPECIMEN, found mystery-shopping Discover on production release v4619
`9b0a8a15`, 2026-09-16 10:59–11:00Z. One page load at 390px; two cards ~1,100 px
apart with two cards between them, served at ranks 30 and 33 of
`GET /api/feed?limit=200`, both standalone:

    108621  kalshi      Which party will win the U.S. House?      resolves Feb 1, 2027
              Democratic Party 86%  ·  Republican Party 14%
    112903  polymarket  Which party will win the House in 2026?   resolves Nov 3, 2026
              Democratic Party 88%  ·  Republican Party 14%

One question — control of the U.S. House at the 2026 midterms — read from the
rows rather than inferred from the titles: the priced outcome sets are identical
(`{Democratic Party, Republican Party}`) and the Feb 2027 / Nov 2026 split is each
venue's own end-date stamp, election night against the seating of the new
Congress. Same shape as #6400's Brazil pair (Oct 3 / Oct 25).

## What refused it, and why only half of that was safe to touch

    tokens A  {which, party, win, u, s, house}   numeric {}
    tokens B  {which, party, win, house, 2026}   numeric {2026}
    jaccard 0.571 (bound 0.72)   containment 0.800 (bound 0.85)

Two independent refusals. `_conservative_near_match_score` returns None at
`left_num != right_num` before the bounds are even read, and the bounds fail too
— depressed by `U.S.` shattering into the two meaningless tokens `u` and `s`.

The numeric guard is LOAD-BEARING and is not relaxed by this ship: it is what
keeps "Fed rate hike in 2026?" apart from "Fed rate hike in 2027?" and every
`Above 40` rung apart from `Above 50`. Instead the year is set aside as a
QUALIFIER before the predicate ever runs, in `_comparison_title` — the pairwise
rewriter that already exists for exactly this, at the one caller that can see the
rows — on four gates, each of which independently kills a hazard (see that
docstring). With the year gone from one side and `U.S.` rejoined into `us` on the
other, the pair reads jaccard 0.800 / containment 1.000 and BOTH numeric sets are
empty, so the guard is satisfied rather than widened.

## The four neighbours that must stay refused

Measured at reader scale on the 114 standalone futures cards served at 11:11Z
(6,441 pairs): exactly five pairs are refused while containment >= 0.80, the only
shape in which a missed duplicate can hide. One is this bug. The other four are
the predicate doing its job, and three are refused by the very numeric guard a
careless fix loosens. They are the controls below, reproduced here as titles so
they are bound by CI rather than by a capture that ages. (The sweep that produced
them runs against a saved feed payload and lives with the lane's evidence, not in
the repo; its before/after over 6,786 pairs is quoted in the PR: one card folds —
the specimen — and the four stay refused.)
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.cross_source_matching import (
    _near_match_tokens,
    is_same_question,
)
from app.utils.discover_bundles import (
    _SAME_CYCLE_MAX_DAYS,
    _comparison_title,
    fold_same_question_cards,
)

HOUSE_KALSHI = "Which party will win the U.S. House?"
HOUSE_POLY = "Which party will win the House in 2026?"
SENATE_KALSHI = "Which party will win the U.S. Senate?"

PARTIES = ("Democratic Party", "Republican Party")


def _card(
    market_id: int,
    name: str,
    *,
    source: str,
    score: float,
    resolution_date: str | None,
    priced: tuple[str, ...] = PARTIES,
    unpriced: tuple[str, ...] = (),
) -> dict:
    """A scored futures card in the shape the fold is handed by the route.

    `top_outcomes` is what the served payload carries — priced legs with a
    `probability`, and (Polymarket) placeholder legs whose probability is NULL.
    """
    outcomes = [
        {"id": 1000 + i, "name": n, "probability": 0.5, "rank": i + 1}
        for i, n in enumerate(priced)
    ] + [
        {"id": 2000 + i, "name": n, "probability": None, "rank": len(priced) + i + 1}
        for i, n in enumerate(unpriced)
    ]
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "reason": "reason",
        "headline": name,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": "politics",
            "source": source,
            "resolution_date": resolution_date,
            "top_outcomes": outcomes,
        },
        "_sort_time": 1000 + market_id,
    }


def _house_pair() -> list[dict]:
    """The two cards, with production's own ids, dates and legs.

    112903's seven unpriced placeholder legs are real and deliberate: a naive
    "same outcomes" gate reads them as a different question, and the reader never
    sees one of them.
    """
    return [
        _card(108621, HOUSE_KALSHI, source="kalshi", score=71,
              resolution_date="2027-02-01T15:00:00+00:00"),
        _card(112903, HOUSE_POLY, source="polymarket", score=69,
              resolution_date="2026-11-03T00:00:00+00:00",
              unpriced=("Other", "Party A", "Party B", "Party C",
                        "Party D", "Party E", "Party F")),
    ]


def _names(items: list[dict]) -> list[str]:
    return [i["data"]["name"] if i.get("type") == "futures" else i["type"] for i in items]


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_discover_asks_who_wins_the_house_once():
    kept = fold_same_question_cards(_house_pair())

    assert _names(kept) == [HOUSE_KALSHI], (
        "the better-ranked card survives; the second phrasing of the same "
        "question is dropped"
    )


def test_the_survivor_is_the_better_ranked_card_whichever_venue_leads():
    assert _names(fold_same_question_cards(list(reversed(_house_pair())))) == [HOUSE_POLY]


def test_the_raw_titles_are_still_refused_so_the_rewrite_is_what_did_it():
    """Non-vacuity: nothing here loosened the predicate itself.

    If this ever starts passing, `is_same_question` has been widened and the
    hazards its numeric guard holds back need re-measuring — the fold's four
    controls below would no longer be protected by it.
    """
    assert not is_same_question(HOUSE_KALSHI, HOUSE_POLY)


def test_the_rewritten_titles_clear_the_bounds_with_room():
    left = _comparison_title(_house_pair()[0]["data"], _house_pair()[1]["data"])
    right = _comparison_title(_house_pair()[1]["data"], _house_pair()[0]["data"])

    assert left == HOUSE_KALSHI, "the undated side is never rewritten"
    assert "2026" not in right
    assert is_same_question(left, right)

    a, b = _near_match_tokens(left), _near_match_tokens(right)
    overlap = len(a & b)
    assert overlap / len(a | b) == pytest.approx(0.80, abs=0.005)
    assert overlap / min(len(a), len(b)) == pytest.approx(1.00, abs=0.005)


# ---------------------------------------------------------------------------
# The four gates, one control each — a fold is only as good as what it declines
# ---------------------------------------------------------------------------


def test_gate_1_two_stated_years_are_two_questions():
    """The numeric guard's whole job, and this ship does not touch it."""
    cards = [
        _card(1, "Fed rate hike in 2026?", source="kalshi", score=80,
              resolution_date="2026-12-31T00:00:00+00:00",
              priced=("Yes", "No")),
        _card(2, "Fed rate hike in 2027?", source="polymarket", score=79,
              resolution_date="2027-01-15T00:00:00+00:00",
              priced=("Yes", "No")),
    ]

    assert len(fold_same_question_cards(cards)) == 2
    assert _comparison_title(cards[0]["data"], cards[1]["data"]) == "Fed rate hike in 2026?"


def test_gate_2_the_venue_s_date_must_agree_with_the_venue_s_own_title():
    """A title saying 2026 on a row that settles in 2029 is not describing its
    own edition, so its year is not a qualifier we may drop."""
    data = _card(1, "Which party will win the House in 2026?", source="polymarket",
                 score=80, resolution_date="2029-11-03T00:00:00+00:00")["data"]
    other = _card(2, HOUSE_KALSHI, source="kalshi", score=79,
                  resolution_date="2029-12-01T00:00:00+00:00")["data"]

    assert _comparison_title(data, other) == "Which party will win the House in 2026?"
    assert len(fold_same_question_cards([_card(2, HOUSE_KALSHI, source="kalshi", score=80,
                                               resolution_date="2029-12-01T00:00:00+00:00"),
                                         _card(1, "Which party will win the House in 2026?",
                                               source="polymarket", score=79,
                                               resolution_date="2029-11-03T00:00:00+00:00")])) == 2


def test_gate_3_next_year_s_edition_does_not_fold_onto_this_year_s():
    """The hazard removal 2's date check exists for, reachable again the moment a
    year may be dropped from mid-sentence. Same title, same field, ONE YEAR APART."""
    cards = [
        _card(1, "2026 Masters Winner", source="polymarket", score=80,
              resolution_date="2026-04-12T22:00:00+00:00",
              priced=("Scottie Scheffler", "Rory McIlroy")),
        _card(2, "Masters Winner", source="kalshi", score=79,
              resolution_date="2027-04-11T22:00:00+00:00",
              priced=("Scottie Scheffler", "Rory McIlroy")),
    ]

    assert _names(fold_same_question_cards(cards)) == ["2026 Masters Winner", "Masters Winner"]
    assert _comparison_title(cards[0]["data"], cards[1]["data"]) == "2026 Masters Winner"


def test_gate_3_boundary_is_the_annual_repeat_it_separates():
    """`_SAME_CYCLE_MAX_DAYS` is derived from the yearly repeat, so pin BOTH
    sides of it — a constant only tested on the side that passes is a constant
    nobody would notice being widened to 364.

    The sweep below reads the constant, so it alone would MOVE WITH a widening
    and prove nothing (measured: widening it to 364 left every test green). The
    derivation is therefore asserted directly: two rows more than half a year
    apart are nearer to the next annual edition than to each other, so twice this
    must not reach the yearly repeat.
    """
    assert _SAME_CYCLE_MAX_DAYS == 182
    assert _SAME_CYCLE_MAX_DAYS * 2 < 365, (
        "a window this wide admits two consecutive annual editions of one title, "
        "which is the hazard the window exists to exclude"
    )

    base = datetime(2026, 11, 3, tzinfo=timezone.utc)
    for offset, folds in ((_SAME_CYCLE_MAX_DAYS - 1, True), (_SAME_CYCLE_MAX_DAYS, False)):
        cards = [
            _card(1, HOUSE_KALSHI, source="kalshi", score=80,
                  resolution_date=(base + timedelta(days=offset)).isoformat()),
            _card(2, HOUSE_POLY, source="polymarket", score=79,
                  resolution_date=base.isoformat()),
        ]
        assert (len(fold_same_question_cards(cards)) == 1) is folds, (
            f"{offset} days apart should {'fold' if folds else 'not fold'}"
        )


def test_gate_4_the_rows_must_price_the_same_outcomes():
    """The independent, row-level second signal: a title match is a candidate
    until something that is not the title agrees."""
    cards = _house_pair()
    cards[1]["data"]["top_outcomes"][1]["name"] = "Reform Party"

    assert len(fold_same_question_cards(cards)) == 2


def test_gate_4_unpriced_placeholder_legs_do_not_defeat_it():
    """PRICED, not all: the specimen only folds because the seven NULL legs the
    reader never sees are excluded. Deleting the word `priced` from that helper
    reverts the ship, and this is the test that says so."""
    cards = _house_pair()
    assert len(cards[1]["data"]["top_outcomes"]) == 9
    assert len(fold_same_question_cards(cards)) == 1


@pytest.mark.parametrize("resolution_date", [None, "", "not a date", "2026"])
def test_a_row_that_does_not_state_a_parseable_date_is_not_folded(resolution_date):
    """An absent date is not evidence — all four gates need the rows to speak."""
    cards = _house_pair()
    cards[1]["data"]["resolution_date"] = resolution_date

    assert len(fold_same_question_cards(cards)) == 2


def test_two_years_in_one_title_are_not_a_single_qualifier():
    """Both years are chosen so that EITHER of them would clear every other gate
    if the count check were relaxed to `>= 1` — otherwise this test passes or
    fails on set iteration order, which is a coin flip, not a guard."""
    two_years = "Which party will win the House in 2026 or 2027?"
    cards = [
        _card(1, two_years, source="polymarket", score=80,
              resolution_date="2027-01-15T00:00:00+00:00"),
        _card(2, HOUSE_KALSHI, source="kalshi", score=79,
              resolution_date="2027-02-01T15:00:00+00:00"),
    ]

    assert _comparison_title(cards[0]["data"], cards[1]["data"]) == two_years
    assert len(fold_same_question_cards(cards)) == 2


# ---------------------------------------------------------------------------
# The other four near-misses on the same page — measured, not imagined
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "left,right,left_date,right_date",
    [
        # Two rungs of one ladder. Refused by the numeric guard: both carry one.
        ("#1 Paid App in the US Apple App Store on September 18",
         "#2 Paid App in the US Apple App Store on September 18",
         "2026-09-19T04:00:00+00:00", "2026-09-19T04:00:00+00:00"),
        # Two chambers. No year on either side, so no rewrite can reach it; it
        # reads 0.667 / 0.800 after the acronym rejoin, FURTHER from the bound
        # than the 0.714 / 0.833 it read before.
        (HOUSE_KALSHI, SENATE_KALSHI,
         "2027-02-01T15:00:00+00:00", "2027-02-01T15:00:00+00:00"),
        # Two cities.
        ("Highest temperature in Ankara on September 18",
         "Highest temperature in Dallas on September 18",
         "2026-09-19T04:00:00+00:00", "2026-09-19T04:00:00+00:00"),
        # Two tournaments three years and one gender apart.
        ("2027 FIFA Women's World Cup Champion", "2030 FIFA World Cup Champion",
         "2027-07-25T00:00:00+00:00", "2030-07-21T00:00:00+00:00"),
    ],
)
def test_the_page_s_other_near_misses_stay_refused(left, right, left_date, right_date):
    cards = [
        _card(1, left, source="kalshi", score=80, resolution_date=left_date),
        _card(2, right, source="polymarket", score=79, resolution_date=right_date),
    ]

    assert _names(fold_same_question_cards(cards)) == [left, right]


# ---------------------------------------------------------------------------
# The tokenizer half — rejoined, never dropped
# ---------------------------------------------------------------------------


def test_a_dotted_acronym_is_one_token_not_two_single_characters():
    assert _near_match_tokens("Which party will win the U.S. House?") == {
        "which", "party", "win", "us", "house"
    }
    assert _near_match_tokens("U.S. House") == _near_match_tokens("US House")


def test_two_countries_do_not_collapse_into_one_question():
    """Why the acronym is REJOINED rather than dropped: deleting single-character
    tokens would make these two titles identical."""
    assert _near_match_tokens("Who wins the U.K. general election?") != _near_match_tokens(
        "Who wins the U.S. general election?"
    )
    assert not is_same_question(
        "Who wins the U.K. general election?", "Who wins the U.S. general election?"
    )


def test_a_possessive_keeps_its_s():
    """NOT "tokenize the normalized string", which fuses `men's` into `mens` and
    drops the measured 2027 Women's World Cup duplicate (jaccard 0.75, one token
    of room) under the bound. Tried; it reddened that control; narrowed to this.
    """
    assert "s" in _near_match_tokens("US Open Men's Singles Winner")
    assert is_same_question(
        "2027 FIFA Women's World Cup Champion", "FIFA Women's World Cup 2027 Winner"
    )
