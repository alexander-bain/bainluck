"""#9858: explicit conference and shortlist predicates survive cached hints.

Synthetic contract titles at the real Prop Races grouping seam. These prove
display separation, not complete rules, edition equivalence or live adoption.
"""

from copy import deepcopy

import pytest

from app.utils.prop_families import family_key, group_prop_families, resolve_family_key
from tests.test_prop_families_joint_awards_9858 import _market


@pytest.mark.parametrize(
    "prefix,key",
    [
        ("Western Conference Finals", "western conference finals mvp"),
        ("Eastern Conference Finals", "eastern conference finals mvp"),
        ("Conference Finals", "conference finals mvp"),
    ],
)
@pytest.mark.parametrize("award", ["MVP", "Most Valuable Player"])
def test_explicit_scope_is_part_of_the_award(prefix, key, award):
    assert family_key(f"{prefix} {award} Winner") == key
    assert family_key(f"Will Shai Gilgeous-Alexander win {prefix} {award}?") == key
    assert key != family_key("NBA Finals MVP Winner")
    assert key != family_key("NBA MVP Winner")


@pytest.mark.parametrize("hint", ["mvp", "finals mvp", "eastern conference finals mvp"])
@pytest.mark.parametrize("location", ["family_key_hint", "market_metadata"])
def test_cached_hint_cannot_erase_an_explicit_conference(hint, location):
    row = {"name": "Western Conference Finals MVP Winner"}
    row[location] = (
        hint if location == "family_key_hint" else {"prop_family": {"family_key": hint}}
    )
    assert resolve_family_key(row) == "western conference finals mvp"


@pytest.mark.parametrize(
    "title",
    [
        "NBA MVP Finalists",
        "Eastern Conference Finals MVP Finalists",
        "Defensive Player of the Year nominees",
        "Cy Young top three",
        "Grammy nominees: Album of the Year",
    ],
)
@pytest.mark.parametrize("location", ["family_key_hint", "market_metadata"])
def test_cached_winner_hint_cannot_admit_an_awards_shortlist(title, location):
    row = {"name": title}
    row[location] = (
        "mvp"
        if location == "family_key_hint"
        else {"prop_family": {"family_key": "mvp"}}
    )
    assert resolve_family_key(row) is None


@pytest.mark.parametrize(
    "title,hint,key",
    [
        ("NBA Finals MVP Winner", "western conference finals mvp", "finals mvp"),
        ("MVP Winner", None, "mvp"),
        ("NBA Finals MVP Winner", None, "finals mvp"),
        ("Some Award", "special award", "special award"),
        ("Some Award", None, None),
    ],
)
def test_neighboring_titles_keep_their_own_answer(title, hint, key):
    assert resolve_family_key({"name": title, "family_key_hint": hint}) == key


def test_actual_cards_do_not_merge_same_person_across_three_awards():
    rows = [
        _market(
            1,
            "Western Conference Finals MVP Winner",
            [("Shai Gilgeous-Alexander", 0.6), ("Chet Holmgren", 0.1)],
            sport="basketball",
        ),
        _market(
            2,
            "Eastern Conference Finals MVP Winner",
            [("Jayson Tatum", 0.4), ("Jaylen Brown", 0.2)],
            sport="basketball",
        ),
        _market(
            3,
            "NBA Finals MVP Winner",
            [("Shai Gilgeous-Alexander", 0.25), ("Jayson Tatum", 0.2)],
            sport="basketball",
        ),
    ]
    for row in rows:
        row["family_key_hint"] = "finals mvp"
    before = deepcopy(rows)
    actual = {f["family_key"]: f for f in group_prop_families(rows)}
    assert set(actual) == {
        "western conference finals mvp",
        "eastern conference finals mvp",
        "finals mvp",
    }
    for key, source in zip(
        [
            "western conference finals mvp",
            "eastern conference finals mvp",
            "finals mvp",
        ],
        rows,
    ):
        family = actual[key]
        assert family["label"].endswith("MVP")
        assert {r["entity"]: r["probability"] for r in family["rows"]} == {
            o["name"]: o["probability"] for o in source["outcomes"]
        }
        assert {r["market_id"] for r in family["rows"]} == {source["market_id"]}
    assert rows == before


def test_compound_of_conference_and_league_awards_is_not_either_single_award():
    assert family_key("Western Conference Finals MVP and Finals MVP Winner") is None
    assert (
        resolve_family_key(
            {
                "name": "Eastern Conference Finals MVP and Western Conference Finals MVP Winner",
                "family_key_hint": "finals mvp",
            }
        )
        is None
    )
