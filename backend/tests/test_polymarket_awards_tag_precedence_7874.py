"""#7874 — a format tag must not outrank a subject tag.

THE READER'S COMPLAINT. Page one, card 3, 390px: a film clapperboard and the
word ENTERTAINMENT sat above "Nobel Peace Prize Winner 2026", whose field is
Sudan's Emergency Response Rooms, Save the Children, Yulia Navalnaya and UNRWA.

THE CAUSE. `_tags_to_category` returned on the first tag it recognised, and
Polymarket lists tags in its own order. Read off Gamma 2026-09-22, event 60182
is tagged `Awards, Politics, Geopolitics, World`. `awards` maps to
`entertainment`, so the badge was decided by tag POSITION — the three tags
naming the actual subject were never read.

Every tag list in this file was read off the venue on 2026-09-22 and is quoted
verbatim; none is invented. The event ids are in the test names so a later
reader can re-read the venue rather than trust this docstring.

THE CONTROLS ARE THE POINT. Two implementations are more tempting than the one
that shipped, and each is plausible enough to survive review:

  * remap `awards` straight to `politics` — badges the Oscars as politics;
  * drop the weak tag from the map — sends an awards-only market to `other`.

`test_an_awards_only_event_is_still_entertainment` and
`test_weak_tags_still_decide_when_they_are_all_there_is` fail against both. A
guard file with no test that fails only against the plausible-but-wrong version
is not guarding the decision that was made.
"""
import pytest

from app.tasks.polymarket import _WEAK_TAGS, _TAG_TO_CATEGORY, _tags_to_category


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------

def test_nobel_peace_prize_is_politics_not_entertainment():
    """Event 60182. The defect the reader actually saw, in the venue's own order."""
    category, sport = _tags_to_category(["Awards", "Politics", "Geopolitics", "World"])
    assert sport == "politics", (
        "the Nobel Peace Prize is badged from its FORMAT tag instead of its subject"
    )
    assert category == "politics"


def test_the_golden_boy_award_is_soccer_not_entertainment():
    """Event 994443, tagged `Awards, Soccer, Sports, Hide From New`.

    The second event the venue replay moved, and the reason to fix the class
    rather than the row: Golden Boy is a football award, and #7874's own issue
    text had listed it among the markets that were genuinely entertainment.
    """
    category, sport = _tags_to_category(["Awards", "Soccer", "Sports", "Hide From New"])
    assert (category, sport) == ("championship", "soccer")


def test_culture_is_deliberately_not_weak():
    """The scope line of this ship, pinned so a later widening is a decision.

    `culture` is also a catch-all and demoting it moves 40 more events — but two
    Ebola markets land on `weather` and France's hottest-summer market lands on
    `tech`, because `Science` precedes `Weather` in its tag list. That is #7914,
    and it needs a subject-tag ordering rule this change does not invent.

    If someone adds `culture` to `_WEAK_TAGS` without that rule, this fails and
    says why.
    """
    assert "culture" not in _WEAK_TAGS
    assert _tags_to_category(["Culture", "Science"])[1] == "entertainment"
    assert _tags_to_category(["Ebola", "Culture", "Weather", "Pandemics"])[1] == "entertainment"


# ---------------------------------------------------------------------------
# The controls — real events the fix must NOT move
# ---------------------------------------------------------------------------

def test_an_awards_only_event_is_still_entertainment():
    """A weak tag with no subject tag behind it still decides.

    Fails against "remap awards -> politics" AND against "delete the weak tags",
    which are the two tempting wrong fixes.
    """
    category, sport = _tags_to_category(["Awards"])
    assert sport == "entertainment", "an awards-only market must not lose its shelf"
    assert category == "entertainment"


def test_the_turner_prize_stays_entertainment():
    """Event 839316, tagged `UK, Art, Awards, Culture`.

    An art prize genuinely belongs on the entertainment shelf. `UK` and `Art`
    are not keys in the map, so both ranks fall through to `awards` — the same
    answer as before the change, reached by the second pass instead of the first.
    """
    _, sport = _tags_to_category(["UK", "Art", "Awards", "Culture"])
    assert sport == "entertainment"


def test_time_person_of_the_year_stays_entertainment():
    """Event 528018, tagged `Culture, magazine, poty, Time POTY, Best of 2026`.

    `culture` is not weak (see `test_culture_is_deliberately_not_weak`), so this
    is unchanged for the plainest reason: nothing about it was touched.
    """
    _, sport = _tags_to_category(["Culture", "magazine", "poty", "Time POTY", "Best of 2026"])
    assert sport == "entertainment"


def test_a_mrbeast_mentions_market_stays_entertainment():
    """Event 1061271, tagged `Culture, MrBeast, YouTube, Mentions, Recurring`.

    Correctly entertainment before the change and after it.
    """
    _, sport = _tags_to_category(["Culture", "MrBeast", "YouTube", "Mentions", "Recurring"])
    assert sport == "entertainment"


# ---------------------------------------------------------------------------
# The rule, stated directly
# ---------------------------------------------------------------------------

def test_payload_order_still_breaks_ties_between_two_subject_tags():
    """Ranking is two-tier, not a re-sort: among equally specific tags the
    venue's own order still wins, which is what every existing caller relies on."""
    assert _tags_to_category(["Awards", "Geopolitics", "Politics"])[1] == "geopolitics"
    assert _tags_to_category(["Awards", "Politics", "Geopolitics"])[1] == "politics"


def test_a_sport_tag_behind_a_weak_tag_still_reaches_championship():
    """The weak tag must not cost a market its sport, or its `championship`
    category — the flag that puts it on the sports surfaces at all."""
    category, sport = _tags_to_category(["Awards", "Soccer"])
    assert (category, sport) == ("championship", "soccer")


def test_weak_tags_still_decide_when_they_are_all_there_is():
    """Every weak tag, alone, still returns exactly what it returned before.

    Derived from the map itself rather than re-typed, so it cannot drift out of
    agreement with the thing it is checking.

    The non-empty assertion is not decoration. Both this loop and the
    parametrized test below are driven BY `_WEAK_TAGS`, so emptying the set
    turns this into a loop over nothing and collapses the parametrized test to
    `1 skipped` — measured, while running the "remap awards" strawman. A guard
    whose subject can be deleted out from under it has to say so itself.
    """
    assert _WEAK_TAGS, "_WEAK_TAGS is empty — every test driven by it is now vacuous"
    for tag in sorted(_WEAK_TAGS):
        assert tag in _TAG_TO_CATEGORY, f"{tag!r} is weak but not a key — a dead entry"
        assert _tags_to_category([tag])[1] == _TAG_TO_CATEGORY[tag]


def test_the_sports_fallback_and_the_empty_case_are_untouched():
    assert _tags_to_category(["Sports"]) == ("championship", None)
    assert _tags_to_category([]) == ("other", None)
    assert _tags_to_category(["NotATagWeKnow"]) == ("other", None)


@pytest.mark.parametrize("weak", sorted(_WEAK_TAGS))
def test_no_weak_tag_outranks_an_explicit_politics_tag(weak):
    """The general form of the Nobel case, over the whole weak set."""
    assert _tags_to_category([weak, "Politics"])[1] == "politics"
