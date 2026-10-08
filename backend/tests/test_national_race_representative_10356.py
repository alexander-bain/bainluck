"""#10356 slice 1 — a national race is represented by its national question.

THE SPECIMEN, production 2026-10-04 10:18Z (r4 warm-rail capture e93246d2, the
retained 20-card page): slot 5 was "Brazil Presidential Election First Round:
1st Place in Tocantins" — one state's first-round result standing for Brazil's
whole race. The #9877 cap seats one card per national race and seated the
highest-ranked member. The rest of the race sat in that card's overflow:

    59114100  ...First Round: 1st Place in Tocantins        rank 106  (seated)
    59934255  Brazil Presidential Election First Round Winner  rank 104
    112996    Brazil Presidential Election                     rank  91
    112998    Will any presidential candidate win outright...  rank  73
    129272    Brazil Presidential Election First Round: 3rd Place  rank 44

Alex's rule (October 7): the positively identified overall-winner question
represents the race, else the first-round-winner question, else today's choice
exactly. Scores, probabilities and every other story are untouched.
"""

import pytest

from app.routes.feed import _merge_broadened_futures
from app.utils import feed_market_quality as fmq
from app.utils.feed_market_quality import (
    NATIONAL_RACE_FIRST_ROUND_WINNER,
    NATIONAL_RACE_OVERALL_WINNER,
    classify_market_quality,
    diversify_quality_families,
    national_presidential_election_story_key,
    national_race_representative_kind,
)

BRAZIL = "story:brazil_presidential_election"

# (market id, name, rank score) — the production rows, names and ranks verbatim.
TOCANTINS = (
    59114100,
    "Brazil Presidential Election First Round: 1st Place in Tocantins",
    106.0,
)
FIRST_ROUND = (59934255, "Brazil Presidential Election First Round Winner", 104.0)
OVERALL = (112996, "Brazil Presidential Election", 91.0)
OUTRIGHT = (
    112998,
    "Will any presidential candidate win outright in the first round of the Brazil election?",
    73.0,
)
THIRD = (129272, "Brazil Presidential Election First Round: 3rd Place", 44.0)
# Kalshi's overall-winner row (#9877's specimen), strict-INELIGIBLE on production.
OVERALL_KALSHI = (109952, "Brazil Presidential election winner?", 98.0)
FRANCE = (113364, "Next French Presidential Election", 103.0)


def _item(row, *, persisted=None) -> dict:
    market_id, name, rank = row
    quality = classify_market_quality(name, "politics", persisted_story_key=persisted)
    return {
        "type": "futures",
        "score": min(rank, 95),
        "_rank_score": rank,
        "_sort_time": 0,
        "_quality_class": quality.quality_class,
        "_quality_family_key": quality.family_key,
        "_quality_story_key": quality.story_key,
        "data": {"id": market_id, "name": name},
    }


def _ids(items) -> list[int]:
    return [i["data"]["id"] for i in items]


def _overflow_ids(items, story=BRAZIL) -> list[int]:
    carriers = [i for i in items if i.get("_quality_story_key") == story]
    assert carriers, f"{story} has no card"
    return _ids(carriers[0].get("_story_overflow_members") or [])


def _brazil_ids(items) -> list[int]:
    return [i["data"]["id"] for i in items if i.get("_quality_story_key") == BRAZIL]


def _without_representatives(monkeypatch):
    """Today's selector: no race gets a representative entry."""
    monkeypatch.setattr(fmq, "_national_race_representatives", lambda *a, **k: {})


def test_every_specimen_row_is_one_national_race():
    for row in (TOCANTINS, FIRST_ROUND, OVERALL, OUTRIGHT, THIRD, OVERALL_KALSHI):
        assert _item(row)["_quality_story_key"] == BRAZIL, row[1]


# --- the selector -----------------------------------------------------------


def test_overall_winner_represents_the_race_over_first_round_and_state_despite_rank():
    pool = [_item(r) for r in (TOCANTINS, FIRST_ROUND, OVERALL, OUTRIGHT, THIRD)]
    kept = diversify_quality_families(pool, exact_family_cap=1, story_family_cap=5)
    assert _brazil_ids(kept) == [OVERALL[0]]
    # Nothing is deleted: the displaced members ride the overflow, in rank order.
    assert _overflow_ids(kept) == [TOCANTINS[0], FIRST_ROUND[0], OUTRIGHT[0], THIRD[0]]


def test_first_round_winner_represents_the_race_when_no_overall_question():
    pool = [_item(r) for r in (TOCANTINS, FIRST_ROUND, OUTRIGHT, THIRD)]
    kept = diversify_quality_families(pool, exact_family_cap=1, story_family_cap=5)
    assert _brazil_ids(kept) == [FIRST_ROUND[0]]
    assert _overflow_ids(kept) == [TOCANTINS[0], OUTRIGHT[0], THIRD[0]]


def test_first_round_winner_beats_a_state_that_outranks_it_by_a_wide_margin():
    tocantins = (TOCANTINS[0], TOCANTINS[1], 160.0)
    pool = [_item(r) for r in (tocantins, FIRST_ROUND)]
    kept = diversify_quality_families(pool)
    assert _brazil_ids(kept) == [FIRST_ROUND[0]]


def test_the_representative_keeps_its_own_score_and_payload():
    overall = _item(OVERALL)
    snapshot = {k: v for k, v in overall.items()}
    kept = diversify_quality_families([_item(TOCANTINS), _item(FIRST_ROUND), overall])
    (seated,) = [i for i in kept if i["data"]["id"] == OVERALL[0]]
    assert {
        k: v for k, v in seated.items() if k != "_story_overflow_members"
    } == snapshot
    assert seated["score"] == 91.0 and seated["_rank_score"] == 91.0


def test_the_returned_list_stays_in_rank_order():
    pool = [_item(r) for r in (FRANCE, TOCANTINS, FIRST_ROUND, OVERALL)]
    kept = diversify_quality_families(pool)
    ranks = [i["_rank_score"] for i in kept]
    assert ranks == sorted(ranks, reverse=True)
    assert _ids(kept) == [FRANCE[0], OVERALL[0]]


# --- neither preferred kind: today's behaviour exactly ----------------------


def test_neither_kind_present_selects_exactly_as_today(monkeypatch):
    pool = [_item(r) for r in (TOCANTINS, OUTRIGHT, THIRD)]
    assert (
        fmq._national_race_representatives(
            sorted(pool, key=lambda x: x["_rank_score"], reverse=True),
            exact_counts={},
        )
        == {}
    )
    after = diversify_quality_families([dict(i) for i in pool])
    _without_representatives(monkeypatch)
    before = diversify_quality_families([dict(i) for i in pool])
    assert after == before
    assert _brazil_ids(after) == [TOCANTINS[0]]
    assert _overflow_ids(after) == [OUTRIGHT[0], THIRD[0]]


def test_states_only_race_keeps_its_top_ranked_state():
    acre = (900001, "Brazil Presidential Election First Round: 1st Place in Acre", 80.0)
    kept = diversify_quality_families([_item(acre), _item(TOCANTINS)])
    assert _brazil_ids(kept) == [TOCANTINS[0]]


def test_unrelated_stories_and_unkeyed_items_are_byte_identical(monkeypatch):
    rows = [
        (1, "MLB World Series Winner", 186.5, None),
        (2, "Will Israel strike Iran by October 31?", 120.0, None),
        (3, "Will Iran close the Strait of Hormuz in 2026?", 110.0, None),
        (4, "Will Hezbollah attack Israel in October?", 100.0, None),
        (5, "Will Hamas release hostages by November?", 99.0, None),
        (6, "Will Israel annex the West Bank in 2026?", 98.0, None),
        (7, "Amapá Governor Election Winner", 97.0, None),
        (8, "Ceará Governor Election Winner", 96.0, None),
        (9, "Biltmore Championship Asheville Winner", 95.0, None),
        (10, "Biltmore Championship Asheville: Top 10", 94.0, None),
        (11, "Next French Presidential Election", 103.0, None),
        (12, "2027 French Presidential Election winner", 70.0, None),
    ]
    pool = [_item((i, n, r), persisted=p) for i, n, r, p in rows]
    pool += [_item(r) for r in (TOCANTINS, OUTRIGHT, THIRD)]
    after = diversify_quality_families([dict(i) for i in pool])
    _without_representatives(monkeypatch)
    before = diversify_quality_families([dict(i) for i in pool])
    assert after == before


def test_only_the_race_with_a_preferred_member_changes(monkeypatch):
    france_round = (
        900002,
        "Next French Presidential Election: 1st Place in Paris",
        140.0,
    )
    pool = [_item(r) for r in (TOCANTINS, FIRST_ROUND, OVERALL, france_round)]
    after = diversify_quality_families([dict(i) for i in pool])
    _without_representatives(monkeypatch)
    before = diversify_quality_families([dict(i) for i in pool])
    assert _ids(before) == [france_round[0], TOCANTINS[0]]
    assert _ids(after) == [france_round[0], OVERALL[0]]


# --- strict eligibility: a later pool never replaces a seated card ----------


def test_relaxed_only_overall_never_replaces_a_strict_survivor():
    # The strict pool held only a state row, so today's choice seated it.
    strict = diversify_quality_families([_item(TOCANTINS)])
    assert _ids(strict) == [TOCANTINS[0]]
    # The relaxed pool also holds the strict-ineligible overall-winner rows.
    relaxed = diversify_quality_families(
        [_item(OVERALL_KALSHI), _item(OVERALL), _item(TOCANTINS)]
    )
    assert _brazil_ids(relaxed) == [OVERALL_KALSHI[0]]
    merged, added = _merge_broadened_futures(strict, relaxed)
    assert _brazil_ids(merged) == [TOCANTINS[0]]
    assert added == []


def test_already_kept_race_gets_no_representative_entry():
    placed = _item(TOCANTINS)
    added = diversify_quality_families(
        [_item(OVERALL), _item(FIRST_ROUND)],
        already_kept=[placed],
    )
    assert added == []


def test_strict_pool_seats_its_strict_first_round_over_a_relaxed_overall():
    # Overall is relaxed-only: the strict pool never sees it, so the strict
    # first-round question is the card, and the merge keeps it.
    strict = diversify_quality_families([_item(TOCANTINS), _item(FIRST_ROUND)])
    assert _ids(strict) == [FIRST_ROUND[0]]
    relaxed = diversify_quality_families(
        [_item(TOCANTINS), _item(FIRST_ROUND), _item(OVERALL)]
    )
    merged, _ = _merge_broadened_futures(strict, relaxed)
    assert _brazil_ids(merged) == [FIRST_ROUND[0]]


def test_a_race_whose_preferred_member_the_family_cap_would_refuse_keeps_a_card():
    # An earlier card already holds the overall question's exact wording under a
    # different (persisted) story, so the family cap refuses the overall row.
    # Holding the race for it would leave Brazil with no card at all.
    twin = _item((900003, "Brazil Presidential Election", 150.0))
    twin["_quality_story_key"] = "story:some_persisted_slug"
    pool = [twin, _item(TOCANTINS), _item(OVERALL)]
    kept = diversify_quality_families(pool)
    assert _brazil_ids(kept) == [TOCANTINS[0]]


def test_story_cap_disabled_is_untouched(monkeypatch):
    pool = [_item(r) for r in (TOCANTINS, FIRST_ROUND, OVERALL)]
    after = diversify_quality_families([dict(i) for i in pool], story_family_cap=0)
    _without_representatives(monkeypatch)
    before = diversify_quality_families([dict(i) for i in pool], story_family_cap=0)
    assert after == before
    assert _ids(after) == [TOCANTINS[0], FIRST_ROUND[0], OVERALL[0]]


# --- positive identification ------------------------------------------------


@pytest.mark.parametrize(
    "name, kind",
    [
        ("Brazil Presidential Election", NATIONAL_RACE_OVERALL_WINNER),
        ("Brazil Presidential election winner?", NATIONAL_RACE_OVERALL_WINNER),
        ("Next French Presidential Election", NATIONAL_RACE_OVERALL_WINNER),
        ("Bulgarian presidential election", NATIONAL_RACE_OVERALL_WINNER),
        ("2027 French Presidential Election winner", NATIONAL_RACE_OVERALL_WINNER),
        (
            "Brazil Presidential Election First Round Winner",
            NATIONAL_RACE_FIRST_ROUND_WINNER,
        ),
        (
            "Brazil Presidential Election: First Round Winner",
            NATIONAL_RACE_FIRST_ROUND_WINNER,
        ),
        # A state or region is never the national question.
        ("Brazil Presidential Election First Round: 1st Place in Tocantins", None),
        ("Brazil Presidential Election First Round: 1st Place in Acre", None),
        ("Brazil Presidential Election Winner in Tocantins", None),
        # No state name is not proof of national: other propositions stay others.
        ("Brazil Presidential Election First Round: 3rd Place", None),
        ("Brazil Presidential Election First Round: 1st Place", None),
        (
            "Will any presidential candidate win outright in the first round of the Brazil election?",
            None,
        ),
        ("Brazil Presidential Election Runoff Winner", None),
        ("Brazil Presidential Election Second Round Winner", None),
        ("Who will win the Brazil presidential election?", None),
        # Not a foreign national race at all.
        ("US Presidential Election", None),
        ("Republican Presidential Election", None),
    ],
)
def test_kind_is_positive_identification_of_the_whole_title(name, kind):
    assert (
        national_race_representative_kind(
            name, national_presidential_election_story_key(name)
        )
        == kind
    )


@pytest.mark.parametrize(
    "name, story",
    [
        # Another country's overall question never represents this race.
        ("Next French Presidential Election", BRAZIL),
        # Another edition is another race.
        ("2026 Brazil Presidential Election", BRAZIL),
        ("Brazil Presidential Election", "story:2026_brazil_presidential_election"),
        # A non-national story is never a national race, whatever the title says.
        ("Brazil Presidential Election", "story:foreign_local_elections"),
        ("Brazil Presidential Election", None),
        # The malformed broad canonical key identifies nothing.
        ("Brazil Presidential Election", "politics:US:championship:2026"),
    ],
)
def test_kind_requires_the_title_to_name_this_exact_race(name, story):
    assert national_race_representative_kind(name, story) is None


def test_distinct_editions_are_distinct_races():
    dated = (900004, "2026 Brazil Presidential Election", 60.0)
    pool = [_item(r) for r in (TOCANTINS, dated)]
    assert pool[1]["_quality_story_key"] == "story:2026_brazil_presidential_election"
    kept = diversify_quality_families(pool)
    # Each edition seats its own card; the dated overall does not stand in for
    # the undated race, so Brazil's undated race keeps its state row.
    assert _ids(kept) == [TOCANTINS[0], dated[0]]
