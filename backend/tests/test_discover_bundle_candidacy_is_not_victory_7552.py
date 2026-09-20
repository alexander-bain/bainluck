"""#7552 — an authored "who wins" sentence may not head a row about running.

THE DEFECT, read off production 2026-09-20 16:47Z, Discover page one at 390px,
slot 5. The card is headed "2028 ELECTION" and captioned "Who wins in 2028?".
Its third row:

    Who will announce Presidential run before 2028?   90%
      J.D. Vance leads at 90%, Rahm Emanuel up 61 points since Aug 4

Announcing a run is not winning one. A reader who takes the heading at its word
reads that 90% as a 90% chance of WINNING the presidency.

THE MECHANISM. Two independent things are keyed on one string. `_story_key`
(`feed_market_quality.py`) decides MEMBERSHIP from topic words alone — "2028"
plus any of four election nouns — and `AUTHORED_STORY_QUESTIONS` authors the
QUESTION for the whole key. Nothing checks that a member answers the sentence.
#4147 added the first such check along one axis (season); this is the second.

🔴 THIS IS A CLASS AND THE TEST IS WRITTEN AS ONE. #6890 ("Who wins on the next
card?" over three UFC futures), #4147, #6353 ("Who wins Be evicted?"), #4785
("How warm does it get in these cities?" — true of 0 of 4) are all closed, all
the same shape, and all were fixed one story at a time. So the claim is read off
the authored sentence rather than listed per key, and the parametrised case
below asserts that property directly: every victory sentence in the map is
guarded, no non-victory sentence is.

🔴 THE NEGATIVE CASES ARE THE POINT, because the expensive error here is
eviction, not retention. Measured over all 42,325 open markets (2026-09-20
16:5xZ, `futures_markets` where `status='open'`), the guard moves 85 of the
6,079 members under authored keys — 83 of `story:us_2028_election` and 2 of
`story:regional_us_elections`. It moves ZERO members of `story:ufc_events`,
`story:fifa_world_cup`, `story:grand_slam_tennis`,
`story:major_entertainment_events` and `story:music_charts`, whose "Will X
become champion…" phrasing is the obvious false positive and is not one:
becoming the champion IS winning. And it moves zero members of
`story:middle_east_conflict`, whose three withdrawal markets DO answer "Where is
the Middle East conflict heading?" — the verb only disqualifies once the
sentence above it promises a winner.
"""

import pytest

from app.utils.discover_bundles import (
    AUTHORED_STORY_QUESTIONS,
    _member_answers_story_question,
    _story_question_promises_a_winner,
    assemble_story_theme_bundles,
)


def _member(
    market_id: int,
    name: str,
    score: float = 72.0,
    llm_sport_category: str = "politics",
) -> dict:
    """A feed item in the shape the bundler consumes.

    `llm_sport_category` is a real input to `_theme_story_key` and not
    decoration — see #4147's fixture, whose tennis pair silently keyed as
    `story:minor_soccer_leagues` until it was threaded through.
    """
    return {
        "type": "futures",
        "score": score,
        "reason": "reason",
        "headline": name,
        "_sort_time": 0.0,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": llm_sport_category,
            "canonical_market_key": None,
            "discover_card": {},
        },
    }


# The row production served under "Who wins in 2028?", and two that honestly
# answer it — all three names verbatim from `futures_markets`.
ANNOUNCE_ROW = _member(
    58336022, "Who will announce Presidential run before 2028?", 90.0
)
WINNER_ROWS = [
    _member(108326, "2028 U.S. Presidential Election winner?", 88.0),
    _member(108327, "2028 Republican presidential nominee", 86.0),
]


# ── The defect ───────────────────────────────────────────────────────────────


def test_the_announce_row_may_not_sit_under_who_wins():
    assert (
        _member_answers_story_question("story:us_2028_election", ANNOUNCE_ROW) is False
    )


def test_the_bundle_keeps_the_rows_that_answer_it():
    out = assemble_story_theme_bundles([*WINNER_ROWS, ANNOUNCE_ROW])

    bundles = [item for item in out if item.get("type") == "bundle"]
    assert len(bundles) == 1
    assert bundles[0]["data"]["shared_question"] == "Who wins in 2028?"
    assert bundles[0]["data"]["member_ids"] == [108326, 108327]


def test_the_false_pairing_is_gone_from_the_served_payload():
    """The absence assertion, named rather than inferred.

    A future change that keeps the announce row in the group and merely
    re-words the header still fails this.
    """
    out = assemble_story_theme_bundles([*WINNER_ROWS, ANNOUNCE_ROW])
    bundles = [item for item in out if item.get("type") == "bundle"]

    for bundle in bundles:
        served = repr(bundle)
        assert "announce Presidential run" not in served
        assert 58336022 not in bundle["data"]["member_ids"]


# ── EVICT means ungroup, not delete ──────────────────────────────────────────
#
# The whole change hangs on where an evicted member goes. If it were dropped,
# this "fix" would delete a real market from page one instead of ungrouping it —
# strictly worse than the false header it removes. Asserted at the assembly
# level, because that is what a reader experiences.


def test_an_evicted_member_comes_back_as_its_own_card():
    out = assemble_story_theme_bundles([*WINNER_ROWS, ANNOUNCE_ROW])

    standalone = [item for item in out if item.get("type") == "futures"]
    assert [item["data"]["id"] for item in standalone] == [58336022]


def test_a_family_with_too_few_answering_members_does_not_fold_at_all():
    """One honest row plus two announce rows is not a story, and loses nobody."""
    out = assemble_story_theme_bundles(
        [
            WINNER_ROWS[0],
            ANNOUNCE_ROW,
            _member(
                58336023,
                "Will LeBron James announce a Presidential run before 2028?",
                70.0,
            ),
        ]
    )

    assert not any(item.get("type") == "bundle" for item in out)
    assert {item["data"]["id"] for item in out} == {108326, 58336022, 58336023}


# ── The negative controls: what must keep folding ────────────────────────────


def test_becoming_the_champion_is_winning():
    """`story:ufc_events`' real members — the obvious false positive."""
    members = [
        _member(1, "Will Ciryl Gane become UFC champion in 2026?", 80.0, "mma"),
        _member(
            2, "Who will be UFC Heavyweight champion at the end of 2026?", 79.0, "mma"
        ),
    ]
    for item in members:
        assert _member_answers_story_question("story:ufc_events", item) is True


def test_a_withdrawal_still_answers_a_non_victory_question():
    """Measured: 3 `story:middle_east_conflict` members carry the verb.

    "Where is the Middle East conflict heading?" is honestly answered by a
    withdrawal, so the verb is not disqualifying here. Without the victory gate
    this fix would have dissolved a good bundle to repair a bad one.
    """
    withdrawal = _member(
        3, "Will Iran withdraw from the NPT before 2027?", 85.0, "world"
    )
    assert (
        _member_answers_story_question("story:middle_east_conflict", withdrawal) is True
    )

    out = assemble_story_theme_bundles(
        [
            withdrawal,
            _member(4, "Israel x Hamas ceasefire by December 31?", 84.0, "world"),
        ]
    )
    bundles = [item for item in out if item.get("type") == "bundle"]
    assert len(bundles) == 1
    assert (
        bundles[0]["data"]["shared_question"]
        == "Where is the Middle East conflict heading?"
    )


def test_an_unauthored_family_is_never_guarded():
    """Fail-open, #4147's "an unknown season never splits".

    The derived tier phrases itself "Who wins {shared}?" and the golf/UFC
    prefixes override the sentence to "What happens at X?" AFTER this runs, so
    only what `AUTHORED_STORY_QUESTIONS` states is checked.
    """
    row = _member(5, "Will anyone run for the club presidency?", 70.0, "golf")
    assert _story_question_promises_a_winner("story:golf_tournament:the_open") is False
    assert _member_answers_story_question("story:golf_tournament:the_open", row) is True
    assert _member_answers_story_question("story:no_such_key_at_all", row) is True


# ── The claim is read off the sentence, not listed per key ───────────────────


@pytest.mark.parametrize("story_key", sorted(AUTHORED_STORY_QUESTIONS))
def test_every_victory_sentence_is_guarded_and_no_other_is(story_key):
    """The property that makes the fifth instance not need a fifth patch.

    Pinned against the map itself, so a newly authored "Who wins …?" inherits
    the guard and a newly authored "What happens …?" does not — neither needing
    an edit here.
    """
    question = AUTHORED_STORY_QUESTIONS[story_key].lower()
    promises = _story_question_promises_a_winner(story_key)
    announce = _member(9, "Will Jane Doe announce a Presidential run before 2028?")

    # Independent reading of the sentence, so this is a real second opinion on
    # the classifier rather than the classifier asserted against itself.
    words = set(question.replace("?", "").replace(",", "").split())
    reads_as_victory = bool(
        words & {"wins", "win", "winner", "tops", "beats", "reaches"}
        or "comes out on top" in question
        or "ends up with" in question
    )
    assert promises is reads_as_victory

    # The guard fires if and only if the sentence promised a winner.
    assert _member_answers_story_question(story_key, announce) is (not promises)
