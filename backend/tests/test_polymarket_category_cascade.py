"""Q446 — the Polymarket category cascade, and the order of its four arms.

`resolve_event_category` was extracted from the middle of `_process_polymarket_events`
so that its ORDER could be tested. Order is the whole substance of this cascade —
each arm exists precisely to beat the one after it — and until the extraction it was
only reachable by running a 200-line async loop against a live database, so nothing
drove it. Four arms had accumulated inline with no test between them.

    1. TABLE TENNIS at the group level (#1230)
    2. no usable tag -> pattern match, then league inference
    3. a non-sport tag but a sport title -> promote
    4. a non-sport tag on the WRONG non-sport shelf -> `misfiled_subject` (Q446)

Arms 1-3 are unchanged by Q446. They are pinned here because an extraction that is
not pinned is a rewrite nobody checked.
"""

import pytest

from app.tasks.polymarket import (
    NON_SPORT_CATEGORIES,
    _tags_to_category,
    resolve_event_category,
)


def _resolve(tags, title, group_names=None):
    """Drive the cascade the way the poller does: tags first, then the rest."""
    category, sport = _tags_to_category(tags)
    cat, sport, _arm = resolve_event_category(
        category, sport, title, group_names or [title]
    )
    return cat, sport


def _arm_for(tags, title, group_names=None):
    category, sport = _tags_to_category(tags)
    return resolve_event_category(category, sport, title, group_names or [title])[2]


# --------------------------------------------------------------------------
# Arm 4 — the Q446 fix, and the fact that it runs LAST
# --------------------------------------------------------------------------


def test_a_flu_market_tagged_tech_lands_on_health():
    """CAL-P132's biggest bucket — 71 markets of this shape.

    Polymarket's only tag for this market is `tech`.
    """
    category, sport = _resolve(["Tech"], "Flu Hospitalization Rate Week 32, 2026?")
    assert sport == "health"
    assert category == "health"


def test_a_wildfire_market_tagged_tech_lands_on_weather():
    category, sport = _resolve(["Tech"], "Palisades wildfire burns 10,000 acres by Friday?")
    assert sport == "weather"
    assert category == "weather"


def test_an_earthquake_market_stays_where_it_is():
    """26 markets. No right shelf exists, so none is invented."""
    _, sport = _resolve(["Earthquakes", "Tech"], "10.0 or above earthquake before 2027?")
    assert sport == "tech"


def test_arm_3_beats_arm_4_a_sport_title_is_never_lost_to_a_subject():
    """THE ORDERING THAT MATTERS. A market whose title names a sport must be that
    sport, even when the title also carries a health or weather word.

    `Hurricanes` is an NHL team; `Miami Heat` is an NBA team and "heat wave" is a
    weather trigger. If arm 4 ever ran before arm 3, both would land on `weather`.
    """
    _, sport = _resolve(["Tech"], "Will the Carolina Hurricanes win the Stanley Cup?")
    assert sport not in ("weather", "health"), f"a sport market went to {sport}"


def test_arm_4_does_not_fire_on_an_ordinary_tech_market():
    _, sport = _resolve(["Tech", "AI"], "Will OpenAI release GPT-6 before 2027?")
    assert sport == "tech"


# --------------------------------------------------------------------------
# Arms 1-3 — unchanged, pinned because the extraction moved them
# --------------------------------------------------------------------------


def test_arm_1_table_tennis_beats_the_seasonal_baseball_guess():
    """#1230. The parent title is bare; the child props carry the tell."""
    category, sport = _resolve(
        [],
        "Melisek Marian vs. Moulis Pavel",
        [
            "Melisek Marian vs. Moulis Pavel",
            "Melisek Marian vs. Moulis Pavel: Total Games O/U 3.5",
        ],
    )
    assert sport == "table_tennis"
    assert category == "championship"


def test_arm_2_pattern_match_when_the_tags_say_nothing():
    category, sport = _resolve([], "Who will win the 2027 NBA Championship?")
    assert sport == "basketball"
    assert category == "championship"


def test_arm_3_promotes_a_sport_title_off_a_non_sport_tag():
    """"Pro Baseball: 2026 AL Cy Young Winner", tagged `awards` -> entertainment."""
    category, sport = _resolve(["Awards"], "Pro Baseball: 2026 AL Cy Young Winner")
    assert sport == "baseball"
    assert category == "championship"


def test_a_usable_sport_tag_is_left_alone():
    category, sport = _resolve(["Sports", "NBA"], "Who wins the title?")
    assert sport == "basketball"
    assert category == "championship"


# --------------------------------------------------------------------------
# Invariants
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tags,title",
    [
        (["Tech"], "Flu Hospitalization Rate Week 32, 2026?"),
        (["Tech"], "Palisades wildfire burns 10,000 acres?"),
        (["Awards"], "Pro Baseball: 2026 AL Cy Young Winner"),
        ([], "Who will win the 2027 NBA Championship?"),
        (["Politics"], "Will the government shut down in 2026?"),
        ([], ""),
    ],
)
def test_a_non_sport_category_never_carries_championship(tags, title):
    category, sport = _resolve(tags, title)
    if sport in NON_SPORT_CATEGORIES:
        assert category != "championship", (
            f"{sport!r} is not a sport but the market was filed as a championship"
        )


def test_the_non_sport_set_is_named_once():
    """It used to be re-declared inside the poller's function body.

    Two copies of one rule is how the golf module's `_is_placeholder_price` comment
    starts, and this file would rather not earn its own version of that story.
    """
    import app.tasks.polymarket as poly

    src = open(poly.__file__).read()
    assert src.count("NON_SPORT_CATEGORIES = ") == 1
    assert "health" in NON_SPORT_CATEGORIES and "weather" in NON_SPORT_CATEGORIES


def test_an_empty_title_does_not_crash_the_cascade():
    assert resolve_event_category("other", None, None, [""]) == ("other", None, "fallback")
    assert resolve_event_category("other", None, "", [""]) == ("other", None, "fallback")


# --------------------------------------------------------------------------
# The reported arm — `stats["by_category"]` counts the FALLBACK arm only
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tags,title,group_names,expected_arm",
    [
        ([], "Who will win the 2027 NBA Championship?", None, "fallback"),
        (["Sports", "NBA"], "Who wins the title?", None, "tag"),
        (["Awards"], "Pro Baseball: 2026 AL Cy Young Winner", None, "promoted"),
        (["Tech"], "Flu Hospitalization Rate Week 32, 2026?", None, "subject"),
        (
            [],
            "Melisek Marian vs. Moulis Pavel",
            [
                "Melisek Marian vs. Moulis Pavel",
                "Melisek Marian vs. Moulis Pavel: Total Games O/U 3.5",
            ],
            "table_tennis",
        ),
    ],
)
def test_the_deciding_arm_is_reported(tags, title, group_names, expected_arm):
    """The poller counts `by_category` on the FALLBACK arm only.

    That has been the counter's meaning since before the extraction — it lived
    inside the tagless branch. Returning the arm is what lets the caller keep that
    meaning without re-deriving the condition and calling `detect_table_tennis_group`
    a second time. Widening an ops metric silently is how a dashboard starts lying.
    """
    assert _arm_for(tags, title, group_names) == expected_arm
