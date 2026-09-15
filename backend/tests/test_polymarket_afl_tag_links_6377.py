"""#6411 (#6377's follow-up) — a real AFL match shows its Polymarket price.

#6377 stopped Aussie Rules fixtures being MINTED as basketball phantoms. It
could not make the market LINK to the real game, and that is the half a reader
sees. Measured on production 2026-09-15, 3 of 3 upcoming AFL/AFLW fixtures::

    15312400 aussierules_aflw  Hawthorn v North Melbourne   0 markets
    15312509 basketball_other  Hawthorn v North Melbourne   1 market
    15310885 aussierules_afl   Hawthorn v Brisbane          0 markets
    15311099 basketball_other  Hawthorn v Brisbane          1 market
    15312406 aussierules_aflw  Essendon v Gold Coast        0 markets
    15312508 basketball_other  Essendon v Gold Coast        1 market

The real game serves nothing; its phantom twin holds the price. That is #5544's
defect one competition over, and it is against the marquee axiom (notice 27).

🔴 THE MECHANISM, and it is not the auto-create. The primary matcher scores
candidate events and **hard-rejects the wrong sport** before anything else can
save the row::

    if sport_prefix and event.sport and event.sport.key:
        if _is_cross_sport_link(sport_prefix, event.sport.key, ...):
            _trace(event, _receipts.REJECT_WRONG_SPORT, score=score)
            continue  # Wrong sport — skip this candidate

``sport_prefix`` comes from ``_market_sport_prefix``, which for a Polymarket
market is ``LLM_CATEGORY_TO_SPORT_PREFIX[llm_sport_category]`` — there is no
ticker. So the nickname guess does not merely mislabel the row: it makes the
real fixture **unreachable as a candidate**, the matcher finds nothing, and the
auto-create it falls through to writes the twin. Honouring Polymarket's own
``afl`` / ``aflw`` tag is what puts the real game back in the candidate set.

Read off Gamma 2026-09-15: ``afl-haw-bri-2026-09-19`` tags ``[sports, games,
afl]``, ``aflw-haw-nmk-2026-09-18`` tags ``[sports, games, aflw]``. Neither tag
was in ``_TAG_TO_CATEGORY``, so ``_tags_to_category`` fell through to the
``sports`` catch-all and the sport was guessed from the club nicknames — Hawks,
Suns, Kangaroos read as basketball. Over 30 days that scattered 17 fixtures
across THREE unrelated catch-alls (``basketball_other`` 11,
``americanfootball_other`` 4, ``motorsport_other`` 3), the Q453 signature.

GUARD DESIGN (Q493's lesson: delete the ambient recovery, so a partial revert
cannot pass). The untagged arm below asserts that the title fallback STILL
answers ``basketball`` for these three titles — so nothing but the tag can
produce the right answer, and dropping either half of the change fails here.
The relation arms assert the map-to-map RELATION rather than restating the
constants, so they cannot agree with the source by construction (#5544/#6406).
"""

import pytest

from app.tasks.polymarket import (
    _SPORT_CATEGORIES,
    _TAG_TO_CATEGORY,
    _tags_to_category,
    resolve_event_category,
)
from app.tasks.prediction_market_matching import _is_cross_sport_link
from app.utils.sport_keys import LLM_CATEGORY_TO_SPORT_PREFIX

# The two real sport keys, both present in `sports` and both active
# (read 2026-09-15), carrying 30 and 18 clubs in `teams` respectively.
REAL_AFL_KEYS = ("aussierules_afl", "aussierules_aflw")

# Verbatim from the three production specimens in the module docstring. These
# are the titles the nickname guess reads as basketball.
AFL_TITLES = (
    "Hawthorn Hawks vs. Brisbane Lions",
    "Essendon Bombers vs. Gold Coast Suns",
    "Hawthorn Hawks vs. North Melbourne Kangaroos",
)

# The three catch-alls the guess actually landed on, measured over 30 days.
MEASURED_WRONG_GUESSES = ("basketball", "motorsports", "football")


def _resolve(tags, title):
    """Drive the cascade the way `_process_polymarket_events` does."""
    category, sport = _tags_to_category(tags)
    return resolve_event_category(category, sport, title, [title])


# --------------------------------------------------------------------------
# The ship — the real fixture stops being hard-rejected as the wrong sport
# --------------------------------------------------------------------------


@pytest.mark.parametrize("real_key", REAL_AFL_KEYS)
@pytest.mark.parametrize("guess", MEASURED_WRONG_GUESSES)
def test_the_nickname_guess_makes_the_real_afl_fixture_an_unreachable_candidate(
    guess, real_key
):
    """The defect, stated at the gate that actually causes it.

    This is the BEFORE half and it must keep passing after the fix: the guesses
    are still wrong sports. What changes is that we stop producing them.
    """
    prefix = LLM_CATEGORY_TO_SPORT_PREFIX.get(guess)
    assert prefix, f"{guess} must be a known category for this test to mean anything"
    assert _is_cross_sport_link(prefix, real_key) is True


@pytest.mark.parametrize("real_key", REAL_AFL_KEYS)
def test_the_venue_tag_puts_the_real_afl_fixture_back_in_the_candidate_set(real_key):
    """THE SHIP. `aussierules` reaches both codes, so the matcher can score them.

    Asserted through the same `_is_cross_sport_link` call the scorer makes, on
    the prefix `_market_sport_prefix` will actually derive — not on a literal.
    """
    prefix = LLM_CATEGORY_TO_SPORT_PREFIX.get(_TAG_TO_CATEGORY["afl"])
    assert _is_cross_sport_link(prefix, real_key) is False


def test_the_fix_does_not_reach_across_into_real_basketball():
    """The other direction, which is the hazard a widening would create.

    Australian NBL fixtures share the continent, the season and several club
    nicknames with the AFL. An `aussierules` market must still be refused on a
    basketball event — this is the notice-40 wrong-sport attachment.
    """
    prefix = LLM_CATEGORY_TO_SPORT_PREFIX[_TAG_TO_CATEGORY["aflw"]]
    for basketball_key in ("basketball_nbl", "basketball_other", "basketball_nba"):
        assert _is_cross_sport_link(prefix, basketball_key) is True


# --------------------------------------------------------------------------
# The tag is read, and it is the only thing that can produce the answer
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tag", ["AFL", "afl", "AFLW", "aflw"])
@pytest.mark.parametrize("title", AFL_TITLES)
def test_an_aussie_rules_tagged_match_is_aussie_rules(tag, title):
    """Both codes, either casing, against the titles that read as basketball."""
    category, sport, arm = _resolve(["Sports", "Games", tag], title)

    assert sport == "aussierules"
    # NOT ("aussierules", "aussierules"). The internal category must stay
    # `championship` — what these rows already carry when the fallback happens
    # to classify them right (production 2026-09-15: 20 on `championship`).
    # This is the assertion that catches dropping `aussierules` from
    # `_SPORT_CATEGORIES`.
    assert category == "championship"
    # And the ops counter stays honest: the TAG decided, not the guess.
    assert arm == "tag"


@pytest.mark.parametrize(
    "tags",
    [
        ["Sports", "Games", "AFL"],
        ["AFL", "Sports", "Games"],
        ["Games", "AFL", "Sports"],
    ],
)
def test_tag_order_does_not_decide(tags):
    """`_tags_to_category` returns on the first mapped tag; `sports` is not one."""
    _, sport, arm = _resolve(tags, AFL_TITLES[0])
    assert (sport, arm) == ("aussierules", "tag")


@pytest.mark.parametrize("title", AFL_TITLES)
def test_without_the_tag_the_fallback_still_answers_basketball(title):
    """Removes the fix's ambient recovery — the strawman guard.

    If this ever goes green on `aussierules`, the tests above stop proving the
    tag did anything and this file needs rewriting rather than trusting.
    """
    _, sport, arm = _resolve(["Sports", "Games"], title)
    assert arm == "fallback"
    assert sport == "basketball"


def test_a_real_australian_basketball_market_is_untouched():
    """The control: the NBL keeps its own tag and its own sport."""
    category, sport, arm = _resolve(
        ["Sports", "Games", "Basketball", "NBL"],
        "Sydney Kings vs. Cairns Taipans",
    )
    assert (category, sport, arm) == ("championship", "basketball", "tag")


# --------------------------------------------------------------------------
# The relation arms — assert the wiring, never restate the constants
# --------------------------------------------------------------------------


def test_both_codes_map_to_one_sport_category():
    """The competition is resolved downstream off `teams`, not here.

    `aussierules_afl` and `aussierules_aflw` are two competitions of one sport,
    and `LLM_CATEGORY_TO_SPORT_PREFIX` has no key that could receive a
    competition. Splitting them here would put a league in a sport field.
    """
    assert _TAG_TO_CATEGORY["afl"] == _TAG_TO_CATEGORY["aflw"]


def test_every_tag_mapping_to_a_sport_yields_the_championship_category():
    """The `_TAG_TO_CATEGORY` -> `_SPORT_CATEGORIES` relation, for the new keys.

    Stated as the relation the two maps must satisfy rather than as a list of
    categories, so it cannot pass by being edited to agree with the source.
    """
    for tag in ("afl", "aflw"):
        mapped = _TAG_TO_CATEGORY[tag]
        assert mapped in _SPORT_CATEGORIES
        assert _tags_to_category(["Sports", tag]) == ("championship", mapped)


def test_the_sport_category_resolves_to_a_prefix_that_reaches_both_real_keys():
    """The end-to-end relation: tag -> category -> prefix -> the real fixtures.

    This is the one arm that fails if ANY link in the chain is broken — the tag
    entry, `LLM_CATEGORY_TO_SPORT_PREFIX`, or the two sport keys themselves.
    """
    prefix = LLM_CATEGORY_TO_SPORT_PREFIX.get(_TAG_TO_CATEGORY["afl"])
    assert prefix is not None
    assert all(key.startswith(prefix) for key in REAL_AFL_KEYS)
    assert not any(_is_cross_sport_link(prefix, key) for key in REAL_AFL_KEYS)
