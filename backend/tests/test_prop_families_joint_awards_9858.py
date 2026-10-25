"""#9858: a Cy Young-and-MVP contract is not a single-award race.

The reported Dodgers title is retained; IDs and prices below are synthetic.
These exercise the actual grouping consumer, including both cached-hint paths.
Separate destination reachability still needs release/reader acceptance.
"""

from copy import deepcopy

import pytest

from app.utils.prop_families import family_key, group_prop_families, resolve_family_key


@pytest.mark.parametrize(
    "title",
    [
        "Shohei Ohtani: Cy Young and MVP Winner",
        "Will Shohei Ohtani win Cy Young and MVP?",
        "Shohei Ohtani to win MVP and Cy Young",
        "Cy Young Award and the Most Valuable Player Award",
        "Cy Young & MVP",
        "Cy Young+MVP",
        "Cy Young or MVP Winner",
        "Defensive Player of the Year and MVP",
        "MVP and Finals MVP",
        "Cy Young\nAND\tMVP Winner",
    ],
)
def test_explicit_compound_does_not_borrow_either_single_award_family(title):
    assert family_key(title) is None


@pytest.mark.parametrize(
    "title,key",
    [
        ("Cy Young Winner", "cy young"),
        ("MVP Winner", "mvp"),
        ("Finals MVP", "finals mvp"),
        ("Defensive Player of the Year", "defensive player of the year"),
        ("World Series MVP", "championship game mvp"),
        ("All-Star Game MVP", "all-star game mvp"),
        ("Most Valuable Player (MVP)", "mvp"),
        ("Most Valuable Player and MVP", "mvp"),
        ("Will reigning MVP Shohei Ohtani win Cy Young?", "cy young"),
        ("Will Cy Young winner Shohei Ohtani win MVP?", "cy young"),
        ("Roy Smith to win Cy Young", "cy young"),
        ("Cy Young and mvplayer", "cy young"),
    ],
)
def test_single_awards_overlapping_aliases_and_incidental_mentions_keep_behavior(
    title, key
):
    # Incidental-mention controls preserve existing classification, not a claim
    # that this patch solves the broader predicate/edition inference contract.
    assert family_key(title) == key


def _market(market_id, title, candidates, **extra):
    return {
        "market_id": market_id,
        "name": title,
        "source": "polymarket",
        "group_id": f"polymarket:{market_id}",
        "url": f"https://polymarket.com/event/synthetic-{market_id}",
        "status": "open",
        "sport": "baseball",
        "resolution_date": None,
        "outcomes": [
            {
                "outcome_id": market_id * 10 + index,
                "name": name,
                "probability": price,
                "is_winner": None,
            }
            for index, (name, price) in enumerate(candidates)
        ],
        **extra,
    }


@pytest.mark.parametrize("name_field", ["name", "market_name"])
@pytest.mark.parametrize(
    "hint",
    [
        {},
        {"family_key_hint": "cy young"},
        {"family_key_hint": "mvp"},
        {"market_metadata": {"prop_family": {"family_key": "cy young"}}},
        {"market_metadata": {"prop_family": {"family_key": "mvp"}}},
    ],
)
def test_dodgers_races_exclude_joint_market_even_with_cached_hint(name_field, hint):
    joint = _market(
        9858, "Shohei Ohtani: Cy Young and MVP Winner", [("Yes", 0.01)], **hint
    )
    if name_field != "name":
        joint[name_field] = joint.pop("name")
    singles = [
        _market(
            1, "Cy Young Winner", [("Yoshinobu Yamamoto", 0.4), ("Shohei Ohtani", 0.2)]
        ),
        _market(2, "MVP Winner", [("Shohei Ohtani", 0.5), ("Freddie Freeman", 0.1)]),
    ]
    before = deepcopy(singles + [joint])
    assert resolve_family_key(joint) is None
    actual = group_prop_families(singles + [joint])
    assert actual == group_prop_families(singles)
    assert {family["family_key"] for family in actual} == {"cy young", "mvp"}
    assert singles + [joint] == before  # The standalone market, ID and URL survive.


def test_noncompound_hint_remains_available_for_unrecognized_title():
    assert resolve_family_key({"name": "Some Award", "family_key_hint": "mvp"}) == "mvp"
