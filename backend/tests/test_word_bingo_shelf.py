"""D19 — word-bingo markets get their own shelf and leave `tech`.

Alex ruling, 2026-08-30: "keynote/podcast mention markets get their own category
label; they leave the tech shelf."

## the defect

A word-bingo market resolves on WHAT SOMEONE SAYS, not on the subject of the
word. "Will Dell say 'Nvidia' during earnings call?" is not a market about
Nvidia, and "Will Dell say 'Agentic' during earnings call?" is not a technology
market — it is a bet on a word. Seventeen of these, all from one earnings call,
were the entire word-bingo population of the Tech & Science shelf on production
2026-08-30, crowding a shelf that is supposed to be about technology.

## the trap this guards

The pre-existing `_WORD_BINGO_RE` is a REFUSAL guard: it stops `misfiled_subject`
moving "Will Trump say 'Flu' this week?" onto the health shelf. It is loose on
purpose, because when the question is *may I move this*, over-matching is safe.

Assigning a shelf asks the opposite question, and the same looseness is now
unsafe: a bare `say` would claim "Will the Fed say rates will fall?". So the
positive rule requires a verb AND an occasion-or-quoted-token, and the loose
refusal still stands for everything the positive rule declines to claim. Both
directions are asserted below — a future simplification that collapses the two
regexes into one breaks one side or the other.
"""

import pytest

from app.utils.futures_categorization import (
    WORD_BINGO_CATEGORY,
    is_word_bingo_market,
    misfiled_subject,
)

# Verbatim from production 2026-08-30 — every open specimen on the two shelves
# `misfiled_subject` is allowed to correct (17 `tech`, 4 `other`), deduplicated
# down to the distinct title shapes.
PRODUCTION_WORD_BINGO = [
    'Will Dell say "Agentic" during earnings call?',
    'Will Dell say "AI" or "Artificial Intelligence" 20+ times during earnings call?',
    'Will Dell say "Data Center" 10+ times during earnings call?',
    'Will Dell say "Nvidia" during earnings call?',
    'Will Dell say "Trump" during earnings call?',
    "What will Dell say during their next earnings call?",
    "What will Bernie say during March on Washington?",
    "What will Abigail Spanberger say during March on Washington?",
    "What will RFK say during Saturday in America?",
    "What will the reporters say during ABC World News Tonight?",
]

# Markets that contain a say/mention verb and are NOT word bingo. These are the
# reason the positive rule needs more than the verb.
NOT_WORD_BINGO = [
    "Will the Fed say rates will fall?",
    "Will Trump say Flu this week?",
    "Who said it first?",
    "Will the report mention a recession?",
]


@pytest.mark.parametrize("name", PRODUCTION_WORD_BINGO)
def test_production_specimens_are_recognised(name):
    assert is_word_bingo_market(name) is True


@pytest.mark.parametrize("name", NOT_WORD_BINGO)
def test_a_bare_verb_is_not_enough(name):
    assert is_word_bingo_market(name) is False


@pytest.mark.parametrize("name", PRODUCTION_WORD_BINGO)
def test_word_bingo_leaves_the_tech_shelf(name):
    """The ruling's own sentence, asserted."""
    assert misfiled_subject(name, "tech") == WORD_BINGO_CATEGORY


@pytest.mark.parametrize("name", PRODUCTION_WORD_BINGO)
def test_word_bingo_also_leaves_other(name):
    assert misfiled_subject(name, "other") == WORD_BINGO_CATEGORY


def test_the_new_shelf_is_not_tech():
    assert WORD_BINGO_CATEGORY != "tech"


@pytest.mark.parametrize("name", NOT_WORD_BINGO)
def test_the_loose_refusal_still_stands(name):
    """A verb-only match is still refused, exactly as before D19.

    This is the property the original guard was added for: "Will Trump say
    'Flu' this week?" must not become a health market. D19 must not have
    weakened it.
    """
    assert misfiled_subject(name, "tech") is None


def test_word_bingo_beats_the_subject_shelves():
    """A word-bingo title that also names a disease or a storm is still word bingo.

    This is the exact case that motivated the original refusal — the subject
    regexes would otherwise claim it — and it is now routed rather than merely
    declined.
    """
    assert misfiled_subject('Will Trump say "Measles" during the press briefing?', "tech") == (
        WORD_BINGO_CATEGORY
    )
    assert misfiled_subject('Will Bernie say "Hurricane" during his speech?', "tech") == (
        WORD_BINGO_CATEGORY
    )


def test_shelves_outside_the_sanctioned_sources_are_untouched():
    """D19 authorises leaving `tech`. It does not authorise re-shelving politics.

    169 open word-bingo markets sit on `politics`, 115 on `entertainment` and 92
    on `economics` (production, 2026-08-30). Moving those is a separate decision
    and this rule must not take it as a side effect.
    """
    for shelf in ("politics", "entertainment", "economics", "health", "weather"):
        assert misfiled_subject(PRODUCTION_WORD_BINGO[0], shelf) is None


def test_the_subject_overrides_still_work():
    """The health/weather routing D19 rides on top of is unchanged."""
    assert misfiled_subject("Measles cases in U.S. by February 28?", "tech") == "health"
    assert misfiled_subject(
        "How many acres will Palisades wildfire burn by Friday?", "tech"
    ) == "weather"


def test_empty_and_none_are_safe():
    assert is_word_bingo_market("") is False
    assert misfiled_subject("", "tech") is None


def test_the_shelf_is_registered_everywhere_it_must_be():
    """A shelf missing from any of these is a shelf that silently misbehaves.

    Each omission has a distinct, quiet failure: no feed tag means the category
    page is unreachable; no base score means it inherits the SPORTS floor and
    ranks as if it were a game; a missing non-sport marker lets the tier
    default and the championship flip treat it as a sports market.
    """
    from app.services.llm import SPORT_CATEGORIES
    from app.tasks.polymarket import NON_SPORT_CATEGORIES
    from app.utils.event_taxonomy import ALLOWED_TAGS
    from app.utils.futures_highlights import CATEGORY_BASE_SCORES, SPORTS_CATEGORY_BASE
    from app.utils.market_label_normalization import _NON_SPORT_CATEGORIES

    assert WORD_BINGO_CATEGORY in SPORT_CATEGORIES, "classifier vocabulary"
    assert WORD_BINGO_CATEGORY in ALLOWED_TAGS["sport"], "feed tag would never be emitted"
    assert WORD_BINGO_CATEGORY in NON_SPORT_CATEGORIES, "could be flipped to championship"
    assert WORD_BINGO_CATEGORY in _NON_SPORT_CATEGORIES, "market tier default"
    assert WORD_BINGO_CATEGORY in CATEGORY_BASE_SCORES, "would inherit the sports floor"
    assert CATEGORY_BASE_SCORES[WORD_BINGO_CATEGORY] < SPORTS_CATEGORY_BASE + 10, (
        "a wall of near-identical 'will X say Y' cards must not out-base ordinary "
        "sports markets on page one"
    )


def test_tags_are_actually_emitted_for_the_new_shelf():
    """End-to-end on the tag path, not just the allowlist membership."""
    from app.utils.event_taxonomy import compute_market_tags

    tags = compute_market_tags(llm_sport_category=WORD_BINGO_CATEGORY, market_tier=2)
    assert f"sport:{WORD_BINGO_CATEGORY}" in tags
