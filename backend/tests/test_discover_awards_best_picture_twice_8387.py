"""#8387 — Discover's Awards Season card asks who wins Best Picture ONCE.

THE SPECIMEN, found mystery-shopping Discover at 390px on production,
2026-09-24 13:51Z. The "Awards Season — Who wins awards season?" bundle
(`theme:story:major_entertainment_events`, six members) listed:

    row 1  6173044   kalshi      Oscar Winner: Best Picture         resolves 2027-12-31
             The Odyssey 37.7% · The Black Ball 20.6% · Dune: Part Three 7.4%
    row 5  57313556  polymarket  Oscars 2027: Best Picture Winner   resolves 2027-07-01
             The Odyssey 49% · La Bola Negra 31.5% · Dune: Part Three 11.5%

"The Odyssey leads at 38%" and "The Odyssey leads at 49%" in one card: one
question, two numbers. The #4446 in-bundle fold refused it three ways, each
measured in the issue: `Oscars`/`Oscar` (jaccard 0.60 after the year is set
aside), the rows settling 183 days apart (one over `_SAME_CYCLE_MAX_DAYS`), and
the served top-three outcome sets differing only by a translated film title.

Sweep over the 3,328 cross-venue pairs of `GET /api/feed?limit=250` at 13:55Z:
0 fold on master, 1 folds with this change — the specimen.
"""

from datetime import datetime

from app.utils.cross_source_matching import is_same_question
from app.utils.discover_bundles import (
    _SAME_CYCLE_MAX_DAYS,
    _comparison_title,
    _dedupe_same_question_members,
    _same_priced_outcomes,
    fold_same_question_cards,
)

KALSHI_DATE = "2027-12-31T15:00:00+00:00"
POLY_DATE = "2027-07-01T03:59:00+00:00"


def _member(market_id, name, source, resolution_date, outcomes, score=90.0):
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "reason": "reason",
        "headline": name,
        "data": {
            "id": market_id,
            "name": name,
            "source": source,
            "llm_sport_category": "entertainment",
            "resolution_date": resolution_date,
            "top_outcomes": [
                {"id": market_id * 10 + i, "name": n, "probability": p, "rank": i + 1}
                for i, (n, p) in enumerate(outcomes)
            ],
        },
        "_sort_time": 1000 + market_id,
    }


def _bundle_members():
    """The six served members, in served order, with production's ids and legs."""
    return [
        _member(
            6173044,
            "Oscar Winner: Best Picture",
            "kalshi",
            KALSHI_DATE,
            [
                ("The Odyssey", 0.3774),
                ("The Black Ball", 0.2062),
                ("Dune: Part Three", 0.0739),
            ],
        ),
        _member(
            58495122,
            "Oscars 2027: Best Adapted Screenplay Winner",
            "polymarket",
            POLY_DATE,
            [("The Invite", 0.25), ("The Black Ball", 0.2), ("The Odyssey", 0.15)],
        ),
        _member(
            58492243,
            "Grammys 2027: Song of the Year Winner",
            "polymarket",
            POLY_DATE,
            [
                ("Choosin' Texas - Ella Langley", 0.34),
                ("the cure - Olivia Rodrigo", 0.2),
                ("Man I Need - Olivia Dean", 0.1),
            ],
        ),
        _member(
            58495124,
            "Oscars 2027: Best Cinematography Winner",
            "polymarket",
            POLY_DATE,
            [
                ("The Odyssey", 0.58),
                ("Dune: Part Three", 0.2),
                ("Project Hail Mary", 0.1),
            ],
        ),
        _member(
            57313556,
            "Oscars 2027: Best Picture Winner",
            "polymarket",
            POLY_DATE,
            [
                ("The Odyssey", 0.49),
                ("La Bola Negra", 0.315),
                ("Dune: Part Three", 0.115),
            ],
        ),
        _member(
            57368169,
            "Oscars 2027: Best Actor Winner",
            "polymarket",
            POLY_DATE,
            [("John Malkovich", 0.2), ("Matt Damon", 0.15), ("Andrew Scott", 0.1)],
        ),
    ]


def _ids(items):
    return [i["data"]["id"] for i in items]


def _data(members, market_id):
    return next(m["data"] for m in members if m["data"]["id"] == market_id)


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_the_awards_card_lists_best_picture_once():
    kept, folded = _dedupe_same_question_members(_bundle_members())

    assert _ids(folded) == [57313556]
    # The better-ranked Kalshi row survives, and every other award stays —
    # including the two Oscars categories this film ALSO leads.
    assert _ids(kept) == [6173044, 58495122, 58492243, 58495124, 57368169]


def test_the_standalone_fold_agrees():
    members = _bundle_members()
    pair = [members[0], members[4]]
    assert _ids(fold_same_question_cards(pair)) == [6173044]


def test_the_raw_titles_are_still_refused_so_the_rewrite_is_what_did_it():
    assert not is_same_question(
        "Oscar Winner: Best Picture", "Oscars 2027: Best Picture Winner"
    )


def test_the_rows_settle_outside_the_cycle_window_so_the_stated_year_arm_is_needed():
    """183 days, one over the window — `_resolve_within_one_cycle` alone refuses
    the specimen, so deleting the stated-year arm reverts the ship."""
    gap = datetime.fromisoformat(KALSHI_DATE) - datetime.fromisoformat(POLY_DATE)
    assert gap.days > _SAME_CYCLE_MAX_DAYS


def test_the_field_outcome_arm_is_needed():
    """Strict set equality over the served top three fails on the translated
    runner-up; deleting the field arm reverts the ship."""
    members = _bundle_members()
    kalshi, poly = _data(members, 6173044), _data(members, 57313556)
    names = lambda d: {o["name"] for o in d["top_outcomes"]}  # noqa: E731
    assert names(kalshi) != names(poly)
    assert _same_priced_outcomes(poly, kalshi)


# ---------------------------------------------------------------------------
# The field arm's refusals
# ---------------------------------------------------------------------------


def test_a_field_with_a_different_leader_is_not_the_same_question():
    members = _bundle_members()
    poly = _data(members, 57313556)
    poly["top_outcomes"][0]["probability"] = 0.1  # La Bola Negra now leads
    assert not _same_priced_outcomes(poly, _data(members, 6173044))
    kept, folded = _dedupe_same_question_members(members)
    assert folded == []


def test_a_field_sharing_only_its_leader_is_not_the_same_question():
    members = _bundle_members()
    poly = _data(members, 57313556)
    poly["top_outcomes"][2]["name"] = "Project Hail Mary"
    assert not _same_priced_outcomes(poly, _data(members, 6173044))


def test_a_two_way_race_still_needs_the_identical_set():
    """The field arm starts at three priced names; the House's two parties stay
    on #6537's equality gate."""
    left = {
        "top_outcomes": [
            {"name": "Democratic Party", "probability": 0.86},
            {"name": "Republican Party", "probability": 0.14},
        ]
    }
    right = {
        "top_outcomes": [
            {"name": "Democratic Party", "probability": 0.88},
            {"name": "Reform Party", "probability": 0.12},
        ]
    }
    assert not _same_priced_outcomes(left, right)


def test_unpriced_legs_do_not_count_toward_the_field():
    left = {
        "top_outcomes": [
            {"name": "A", "probability": 0.5},
            {"name": "B", "probability": 0.3},
            {"name": "C", "probability": None},
        ]
    }
    right = {
        "top_outcomes": [
            {"name": "A", "probability": 0.6},
            {"name": "B", "probability": 0.2},
            {"name": "D", "probability": None},
        ]
    }
    assert _same_priced_outcomes(left, right)  # equal priced sets {a, b}
    right["top_outcomes"][1]["name"] = "E"
    assert not _same_priced_outcomes(left, right)  # two priced each: equality only


# ---------------------------------------------------------------------------
# The ceremony fold
# ---------------------------------------------------------------------------


def test_a_ceremony_plural_folds_to_its_singular():
    empty: dict = {}
    assert (
        _comparison_title({"name": "Grammys: Album of the Year"}, empty)
        == "Grammy: Album of the Year"
    )
    assert (
        _comparison_title({"name": "Golden Globes Best Drama"}, empty)
        == "Golden Globe Best Drama"
    )


def test_the_fold_is_a_closed_vocabulary_not_a_plural_rule():
    """A generic trailing-s strip reads "World Series" as "World Serie" — and then
    "Serie A Champion 2026" beside "World Series Champion 2026" clears the near
    arm at jaccard 0.75. Neither title is touched."""
    empty: dict = {}
    for title in (
        "World Series Champion 2026",
        "Serie A Champion 2026",
        "Tony's Pizza Bowl",
        "Oscar Piastri wins the title",
    ):
        assert _comparison_title({"name": title}, empty) == title
    assert not is_same_question(
        _comparison_title({"name": "Serie A Champion 2026"}, empty),
        _comparison_title({"name": "World Series Champion 2026"}, empty),
    )
