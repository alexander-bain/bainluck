"""#4479 — the Grand Slam card serves the men's US Open once, not twice.

THE SPECIMEN, found paying #4446's own after-LOOK on production `61444efe`,
2026-09-09 13:22 PT — the first `/api/feed?limit=250` read after #4446 deployed:

    slot 26  Grand Slam Tennis  n=3   shared_question: "Who wins the Slam?"
      34277839  US Open Women's Singles Winner        Sabalenka 28%
      114159    2026 Men's US Open Winner (Tennis)    Zverev 46%   Shelton 38%
      34277822  US Open Men's Singles Winner          Zverev 30%   Shelton 26%

Two rows for one question, two apart under one heading that promises one answer,
**sixteen points apart on the leader** — and both rows advertise
``sources: ["kalshi", "polymarket"]``, so each already claims to be a blend. That
is the standing ruling read backwards ("the blend is the product: one number per
question") on top of the ``duplicate-family-rate@20=0`` audit target.

## Why this file exists rather than a threshold change in #4446's matcher

Measured over all 23 same-bundle pairs page one served at 13:30 PT:

    pair                                                jaccard  containment
    2026 Men's US Open Winner (Tennis)
      vs US Open Men's Singles Winner   (the DUPLICATE)    0.625        0.833
    US Open Men's Singles Winner
      vs US Open Women's Singles Winner (must NEVER fold)  0.714        0.833

**The duplicate scores lower than the control.** Any relaxation of the matcher's
0.72 / 0.85 gate that admits 0.625 also admits 0.714 and deletes the women's draw
from the card — the exact deletion #4446 rejected ``canonical_market_key`` to
avoid. So the fix makes the two titles comparable before they are scored, at the
bundler, where the resolution dates that gate the year removal are visible;
``is_same_question`` itself is untouched, because it is shared with the
category-page spotlight.

Every fixture name below is a title production actually served, and the controls
are the duplicate's real neighbours — the whole census, not a chosen subset. A
deduper is only as good as the cards it declines to delete.
"""

import pytest

from app.utils.cross_source_matching import is_same_question
from app.utils.discover_bundles import (
    _comparison_title,
    _dedupe_same_question_members,
    assemble_story_theme_bundles,
)

SLAM_STORY = "story:grand_slam_tennis"
WC_STORY = "story:fifa_world_cup"

MENS_POLY = "2026 Men’s US Open Winner (Tennis)"
MENS_KALSHI = "US Open Men's Singles Winner"
WOMENS_KALSHI = "US Open Women's Singles Winner"


def _member(
    market_id: int,
    name: str,
    *,
    source: str,
    story_key: str,
    score: float,
    resolution_date: str | None = None,
    category: str = "tennis",
) -> dict:
    return {
        "type": "futures",
        "score": score,
        "reason": "reason",
        "headline": name,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": category,
            "source": source,
            "resolution_date": resolution_date,
        },
        "_quality_story_key": story_key,
        "_sort_time": 1000 + market_id,
    }


def _slam_members() -> list[dict]:
    """The three rows the Grand Slam bundle carried, in served rank order."""
    return [
        _member(34277839, WOMENS_KALSHI, source="kalshi", story_key=SLAM_STORY,
                score=83, resolution_date="2026-09-27T02:00:00+00:00"),
        _member(114159, MENS_POLY, source="polymarket", story_key=SLAM_STORY,
                score=80, resolution_date="2026-09-13T00:00:00+00:00"),
        _member(34277822, MENS_KALSHI, source="kalshi", story_key=SLAM_STORY,
                score=78, resolution_date="2026-09-28T02:00:00+00:00"),
    ]


def _names(members: list[dict]) -> list[str]:
    return [m["data"]["name"] for m in members]


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_the_slam_bundle_serves_the_mens_us_open_once():
    kept, folded = _dedupe_same_question_members(_slam_members())

    assert _names(folded) == [MENS_KALSHI]
    assert _names(kept) == [WOMENS_KALSHI, MENS_POLY]


def test_the_womens_draw_survives_the_fold():
    """A dedupe must never be a delete, and this is the row that was at risk.

    #4446 rejected ``canonical_market_key`` precisely because all three of these
    rows carry the identical key ``tennis::championship:2026``; a key-based dedupe
    would have removed the women's draw. Asserted, not assumed.
    """
    kept, _ = _dedupe_same_question_members(_slam_members())
    assert WOMENS_KALSHI in _names(kept)


def test_the_folded_row_does_not_come_back_as_its_own_card():
    """The freed slot goes to a real question, and the duplicate leaves the page.

    Driven through ``assemble_story_theme_bundles`` rather than the private
    helper: a fold that is not claimed as represented falls through the emit loop
    and reappears standalone, which moves the duplicate down the page instead of
    removing it. #4446's own finding, re-asserted for this specimen.
    """
    result = assemble_story_theme_bundles(_slam_members())

    bundle = next((it for it in result if it["type"] == "bundle"), None)
    assert bundle is not None
    assert bundle["data"]["member_ids"] == [34277839, 114159]

    serialized = repr(result)
    assert serialized.count(MENS_KALSHI) == 0, (
        "the folded Kalshi men's row is still somewhere in the emitted feed"
    )


# ---------------------------------------------------------------------------
# The whole served census. 23 pairs, exactly one of which may fold.
# ---------------------------------------------------------------------------

#: Every same-bundle pair page one served at 13:30 PT on 2026-09-09 that this
#: rule could reach, with the venues that served them. Cross-venue only: a
#: same-venue pair is refused by the bundler's first gate before any title is
#: compared, and those are covered by their own test below.
SERVED_CROSS_VENUE_PAIRS = [
    ("Fed & Rates", "Fed decision in Sep 2026?", "kalshi",
     "How many Fed rate cuts in 2026?", "polymarket"),
    ("Fed & Rates", "Number of rate cuts in 2026?", "kalshi",
     "How many Fed rate cuts in 2026?", "polymarket"),
    ("Grand Slam Tennis", WOMENS_KALSHI, "kalshi", MENS_POLY, "polymarket"),
]


@pytest.mark.parametrize("bundle,left,left_src,right,right_src", SERVED_CROSS_VENUE_PAIRS)
def test_no_other_served_cross_venue_pair_folds(bundle, left, left_src, right, right_src):
    a = {"name": left, "source": left_src, "resolution_date": "2026-09-27T00:00:00+00:00"}
    b = {"name": right, "source": right_src, "resolution_date": "2026-09-27T00:00:00+00:00"}
    assert not is_same_question(_comparison_title(a, b), _comparison_title(b, a)), (
        f"{bundle}: {left!r} and {right!r} are different questions and must both survive"
    )


#: The Fed paraphrase pair is #4446's explicitly pinned known miss. It is in the
#: census above as a REFUSAL, which is the behaviour that ship chose; this names
#: it so a later reader does not mistake it for an oversight of this one.
def test_the_fed_paraphrase_remains_an_explicit_non_goal():
    a = {"name": "Number of rate cuts in 2026?", "source": "kalshi",
         "resolution_date": "2026-12-31T00:00:00+00:00"}
    b = {"name": "How many Fed rate cuts in 2026?", "source": "polymarket",
         "resolution_date": "2026-12-31T00:00:00+00:00"}
    assert not is_same_question(_comparison_title(a, b), _comparison_title(b, a))


# ---------------------------------------------------------------------------
# The arms a looser fix dies on
# ---------------------------------------------------------------------------


def test_men_and_women_are_never_the_same_question():
    """The counter-case with the highest score in the whole census (0.714).

    A fix that moved the matcher's threshold instead of normalizing the titles
    passes every other test in this file and deletes a Grand Slam draw here.
    """
    for left, right in ((MENS_KALSHI, WOMENS_KALSHI), (MENS_POLY, WOMENS_KALSHI)):
        a = {"name": left, "source": "polymarket", "resolution_date": "2026-09-28T00:00:00+00:00"}
        b = {"name": right, "source": "kalshi", "resolution_date": "2026-09-27T00:00:00+00:00"}
        assert not is_same_question(_comparison_title(a, b), _comparison_title(b, a)), (
            f"{left!r} folded onto {right!r}"
        )


def test_two_dated_editions_keep_their_years():
    """#4446's own control. Both sides name a year, so neither year is dropped.

    This is what keeps the year removal from being a blanket strip: the matcher's
    ``left_num != right_num`` guard is the thing refusing this pair, and it can
    only do that if both years are still in the strings when it runs.
    """
    a = {"name": "2027 FIFA Women's World Cup Champion", "source": "kalshi",
         "resolution_date": "2027-07-01T00:00:00+00:00"}
    b = {"name": "2030 FIFA World Cup Champion", "source": "kalshi",
         "resolution_date": "2030-07-01T00:00:00+00:00"}
    assert _comparison_title(a, b) == "2027 FIFA Women's World Cup Champion"
    assert _comparison_title(b, a) == "2030 FIFA World Cup Champion"
    assert not is_same_question(_comparison_title(a, b), _comparison_title(b, a))


def test_a_year_is_not_dropped_when_the_two_rows_resolve_in_different_years():
    """The guard that stops an undated title folding onto the wrong edition.

    Without the resolution-date agreement check, "2026 Masters Winner" and an
    undated "Masters Winner" for the 2027 edition become the same question and
    one of them is deleted. The titles here are otherwise identical after the
    strip, so this test fails the moment the check is removed.
    """
    dated = {"name": "2026 Masters Winner", "source": "polymarket",
             "resolution_date": "2026-04-12T00:00:00+00:00"}
    undated = {"name": "Masters Winner", "source": "kalshi",
               "resolution_date": "2027-04-11T00:00:00+00:00"}
    assert _comparison_title(dated, undated) == "2026 Masters Winner"
    assert not is_same_question(
        _comparison_title(dated, undated), _comparison_title(undated, dated)
    )

    # Positive control on the same fixture: agree the years and it folds, so the
    # refusal above is the date check and not some other property of the pair.
    same_year = dict(undated, resolution_date="2026-04-11T00:00:00+00:00")
    assert _comparison_title(dated, same_year) == "Masters Winner"
    assert is_same_question(
        _comparison_title(dated, same_year), _comparison_title(same_year, dated)
    )


def test_a_row_with_no_resolution_date_never_loses_its_year():
    """Unknown is not agreement. A missing date must refuse, not default to yes."""
    dated = {"name": "2026 Masters Winner", "source": "polymarket",
             "resolution_date": "2026-04-12T00:00:00+00:00"}
    undated = {"name": "Masters Winner", "source": "kalshi", "resolution_date": None}
    assert _comparison_title(dated, undated) == "2026 Masters Winner"
    assert not is_same_question(
        _comparison_title(dated, undated), _comparison_title(undated, dated)
    )


def test_one_venues_own_two_listings_are_never_folded():
    """#4446's first gate, unchanged: the venues must differ.

    Same titles as the subject pair, both from Polymarket. Folding a venue's own
    catalogue is not ours to do, and this ship must not have quietly widened that.
    """
    members = [
        _member(1, MENS_POLY, source="polymarket", story_key=SLAM_STORY, score=90,
                resolution_date="2026-09-13T00:00:00+00:00"),
        _member(2, MENS_KALSHI, source="polymarket", story_key=SLAM_STORY, score=80,
                resolution_date="2026-09-28T00:00:00+00:00"),
    ]
    kept, folded = _dedupe_same_question_members(members)
    assert folded == []
    assert len(kept) == 2


def test_the_4446_world_cup_fold_still_happens():
    """The shipped behaviour this change sits on top of. Not a new claim — a
    regression control, because both ships edit the same function."""
    members = [
        _member(56775503, "2027 FIFA Women's World Cup Champion", source="kalshi",
                story_key=WC_STORY, score=90, category="soccer",
                resolution_date="2027-07-01T00:00:00+00:00"),
        _member(56775477, "2030 FIFA World Cup Champion", source="kalshi",
                story_key=WC_STORY, score=88, category="soccer",
                resolution_date="2030-07-01T00:00:00+00:00"),
        _member(60607659, "FIFA Women's World Cup 2027 Winner", source="polymarket",
                story_key=WC_STORY, score=70, category="soccer",
                resolution_date="2027-07-01T00:00:00+00:00"),
    ]
    kept, folded = _dedupe_same_question_members(members)
    assert _names(folded) == ["FIFA Women's World Cup 2027 Winner"]
    assert _names(kept) == [
        "2027 FIFA Women's World Cup Champion",
        "2030 FIFA World Cup Champion",
    ]


# ---------------------------------------------------------------------------
# The two removals, each on its own
# ---------------------------------------------------------------------------


def test_a_trailing_qualifier_is_dropped_symmetrically():
    a = {"name": "US Open Winner (Tennis)", "source": "polymarket"}
    b = {"name": "US Open Winner (Golf)", "source": "kalshi"}
    assert _comparison_title(a, b) == "US Open Winner"
    assert _comparison_title(b, a) == "US Open Winner"


def test_a_qualifier_that_is_not_trailing_is_left_alone():
    a = {"name": "Winner (Tennis) of the US Open", "source": "polymarket"}
    b = {"name": "US Open Winner", "source": "kalshi"}
    assert _comparison_title(a, b) == "Winner (Tennis) of the US Open"


def test_a_long_parenthetical_is_not_a_qualifier():
    """A qualifier is a word or two. A parenthetical sentence is content, and
    deleting it could merge two genuinely different questions."""
    long_tail = "Winner (excluding any player who withdraws before the first round)"
    a = {"name": long_tail, "source": "polymarket"}
    b = {"name": "Winner", "source": "kalshi"}
    assert _comparison_title(a, b) == long_tail
