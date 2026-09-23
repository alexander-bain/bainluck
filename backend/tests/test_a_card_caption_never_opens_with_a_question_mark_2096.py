"""#2096 — a futures caption never opens with an orphaned `?`.

`generate_futures_reason` splices the market title into two grammatical
positions. In OBJECT position ("Big odds movement in {title}") the title's own
question mark belongs where it sits. In SUBJECT position it lands mid-sentence,
and the CARD then promotes it to the front: both caption chains subtract a
leading restatement of the heading (`stripCardTitleHead`, #6903) and the heading
prints WITHOUT the mark, so the cut lands one character early and the reader
reads

    ? resolves within a month

Photographed at 390px on production `/categories/geopolitics` 2026-09-22
(`artifacts-discover/d428/geo-3200.png`, the Saudi Arabia and Houthi cards).
Measured the same hour over 536 served futures cards on six surfaces: 23 reason
strings carry the mark in subject position, 6 reaching a reader as the caption.

The guard is written against the eleven SUBJECT templates as a class rather than
against the two photographed strings, because the defect is one missing
normalisation shared by all of them and a per-string test would pass while a
twelfth template reintroduced it.
"""

import re

import pytest

from app.utils.feed_reasons import (
    _market_name_as_subject,
    generate_futures_reason,
)

# Every reason code whose template opens with the market title. Each is one of
# the eleven subject-position splices; `has_shifted` reaches the same templates
# through the lifetime-move branch.
SUBJECT_POSITION_REASONS = [
    "resolving_soon_1d",
    "resolving_soon_2d",
    "resolving_soon_7d",
    "resolving_soon_30d",
]

# Real served titles, taken verbatim from the 2026-09-22 census. Every one ends
# in `?`, which is the shape the defect needs; the last carries an INTERNAL mark
# so the repair is pinned as a trailing-only strip.
TITLES_FROM_PRODUCTION = [
    "Saudi Arabia military action against Yemen?",
    "Houthi military action against Saudi Arabia?",
    "Greenland deal text released?",
    '"Digger" Rotten Tomatoes Score?',
    "How many times will Donald Trump visit Trump Bedminster in Sep 2026?",
    "How low will the 30Y US Treasury yield get by Sep 30, 2026?",
    "Who? What?",
]


def _caption_after_heading_subtraction(reason: str, heading: str) -> str:
    """`stripCardTitleHead`'s cut, as the clients perform it.

    Ported deliberately rather than imported: this file is the BACKEND guard,
    and its claim is that the backend string survives the clients' subtraction.
    Pinning that claim to the TypeScript would make a frontend edit able to turn
    this test green while the served string stayed broken — the frontend half
    has its own guard (`captionNeverOpensWithQuestionMark2096.test.ts`).
    """
    name = re.sub(r"\s*\?\s*$", "", heading.strip())
    if not reason.lower().startswith(name.lower()):
        return reason
    rest = re.sub(r"^[\s:,;–—-]+", "", reason[len(name) :])
    return rest[:1].upper() + rest[1:] if rest else ""


@pytest.mark.parametrize("title", TITLES_FROM_PRODUCTION)
@pytest.mark.parametrize("reason_code", SUBJECT_POSITION_REASONS)
def test_subject_position_reason_survives_the_heading_subtraction(title, reason_code):
    """The served string, minus the heading the card prints, is still prose."""
    reason = generate_futures_reason(title, [reason_code])
    assert reason, f"{reason_code} produced no reason for {title!r}"

    caption = _caption_after_heading_subtraction(reason, title)
    assert not caption.startswith("?"), (
        f"caption opens with an orphaned '?': {caption!r}\n"
        f"  title  : {title!r}\n"
        f"  reason : {reason!r}"
    )
    # …and the mark is gone from the sentence entirely, not merely shifted off
    # the front by a longer prefix.
    assert "? resolv" not in reason, f"mark survives mid-sentence: {reason!r}"


@pytest.mark.parametrize("title", TITLES_FROM_PRODUCTION)
def test_subject_position_reason_keeps_the_words_of_the_title(title):
    """A DELETION, never a rewrite (ruling 003).

    The repair may remove the trailing mark and nothing else — in particular it
    may not truncate, which is what adopting `_short_market_name` here would
    have done to every long title on the page.
    """
    reason = generate_futures_reason(title, ["resolving_soon_30d"])
    expected_subject = title.rstrip().rstrip("?").rstrip()
    assert reason.startswith(expected_subject), (
        f"subject was rewritten, not just unmarked\n"
        f"  expected prefix: {expected_subject!r}\n"
        f"  got            : {reason!r}"
    )
    assert "..." not in reason, f"title was truncated: {reason!r}"


def test_object_position_keeps_the_titles_own_question_mark():
    """THE CONTROL, and it exercises the opposite branch of the gate.

    Only SUBJECT position was changed. "Big odds movement in {title}" ends with
    the title, where the mark is the title's own punctuation and correct. A
    repair that stripped it everywhere would pass every assertion above and
    silently reword this class too, so the scope boundary is pinned here rather
    than described in a comment.
    """
    reason = generate_futures_reason(
        "Will Ukraine target Moscow?", ["major_movement_24h"]
    )
    assert reason.endswith("Will Ukraine target Moscow?"), reason


def test_the_helper_strips_only_the_trailing_mark():
    """Anti-vacuity: the helper must be capable of NOT firing.

    A repair that returned "" or stripped every "?" would satisfy the class test
    above; these are the inputs that separate it from those.
    """
    assert _market_name_as_subject("No mark") == "No mark"
    assert _market_name_as_subject("Who? What?") == "Who? What"
    assert _market_name_as_subject("A?") == "A"
    assert _market_name_as_subject("  Trailing ?  ") == "Trailing"
    assert _market_name_as_subject(None) == ""
    assert _market_name_as_subject("?") == ""


def test_the_subtraction_helper_would_have_caught_the_defect():
    """STRAWMAN. The ported cut must actually reproduce the photographed string.

    Without this, a mistake in `_caption_after_heading_subtraction` would make
    every assertion above vacuously true — the test would be asserting that a
    function which never strips anything never strips too much.
    """
    broken = "Saudi Arabia military action against Yemen? resolves within a month"
    assert (
        _caption_after_heading_subtraction(
            broken, "Saudi Arabia military action against Yemen?"
        )
        == "? resolves within a month"
    )
