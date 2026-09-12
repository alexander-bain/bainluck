"""#4056 — a Discover card never answers with its own title or its own number.

THE SHIP. Three rungs of the futures fallback ladder said nothing, and one of them said
something false. Measured on production `6f24a670`, 2026-09-09 03:0x PT, `GET /api/feed?limit=60`,
walking top-level cards AND bundle member rows (a bundle renders each nested `data.items[]`
card as a row, so those sentences are fully reader-visible):

    72 cards eligible (carry a market name)
    36 failing (card, field) pairs across 16 distinct cards
       NUMBER_ECHO  28   `42% chance` in headline + context_summary, 14 cards
       TITLE_ECHO    6   the title back, in all three slots, 2 cards
       MID_NUMBER    2   `...Before the 2030-3...: 42% chance`

The three defects, and why each is one:

1. NUMBER_ECHO — `compose_binary_card_copy`'s terminal returned `composed(answer, answer)`,
   putting `42% chance` directly beneath a hero already printing 42% in 48pt. Standing
   notice 34: a reader sees the number and at most one short caption, and "if a number
   cannot be shown honestly, leave the space empty". A bare `42% chance` above a 42% hero
   IS the empty case, wearing text.

2. TITLE_ECHO — `generate_futures_headline` returned the chopped title with nothing
   appended, and `generate_futures_reason` returned the title verbatim, twice. On the Alito
   card that made all three sentence slots the same string.

3. MID_NUMBER — `_short_market_name` cut at a character count, so the chop could land
   inside a number and the card stated a value the market does not (`2030-3` for
   *Before the 2030-31 Season*). A mid-word chop is ugly; a mid-number chop is a different
   number, which is a truth defect, not a formatting one.

🔴 THE THREE MUST MOVE TOGETHER. Both clients build the caption from a four-deep chain and
`hook_description` is the floor of both (web `utils.ts:452`:
`context_summary || headline || reason || hook_description || ""`; iOS `DiscoverView.swift:749`
+ `DiscoverFuturesCard.swift:73`: `contextSummary ?? reason ?? headline ?? hookDescription`).
Blanking one slot moves the defect one rung down and the reader sees no change. That is why
these tests assert on the WHOLE `BinaryCardCopy` triple, not on `headline` alone.

Empty is a supported state on both clients today and needs no client change: web's three
render sites are `{contextSnippet && (…)}`, iOS's row is `if let contextText { … }` inside a
VStack, which emits no spacing for an absent child.
"""

from __future__ import annotations

import re

import pytest

import app.utils.feed_reasons as fr

NOW = None

#: The production specimens, verbatim from the census above.
STANLEY_2030 = "Canadian Team to Win the Stanley Cup® Before the 2030-31 Season"
UTAH = "Will Utah Mammoth advance to the Second Round of the 2027 Stanley Cup Playoffs?"
ALITO = "Will Samuel Alito announce his retirement by...?"
TAIWAN = "Will China invade Taiwan by end of 2026?"

#: A chop that landed inside a number, as the CENSUS spots it from outside. Anchored
#: ANYWHERE in the string, not at the end: #4056's suggested guard shape was "no served
#: string ENDS `<digit>...`", and that anchor reads ZERO on the very production pull that
#: contained two of them, because `compose_binary_card_copy` appends `: 42% chance` after
#: the chopped title. A control that fails toward PASS is how a broken ship gets certified.
#:
#: 🔴 THIS PATTERN IS A SMELL TEST, NOT THE INVARIANT, and it over-refuses. It cannot tell
#: a truncated number from a COMPLETE one followed by an ellipsis: `September 7...` (from
#: "September 7 - September 13") is honest — `7` is a whole token — and this regex flags it
#: anyway. It is kept for the two production specimens where a digit genuinely WAS split,
#: and for the census, which has no access to the original title. The property the code
#: actually guarantees is `assert_whole_word_prefix` below, which is both stricter and
#: exact, and that is what the parametrized guard asserts.
MID_NUMBER_CHOP = re.compile(r"\d\.\.\.")

BARE_NUMBER_SENTENCE = re.compile(r"^\d{1,3}% chance$")


def assert_whole_word_prefix(short: str, title: str) -> None:
    """THE INVARIANT: a shortened title is the original cut at a word boundary.

    Stronger than "no digit before the ellipsis" and exactly the property that makes
    the card honest — if the retained text is a whole-word prefix of the title, then no
    token was split, so no number was turned into a different number and no word into a
    different word. `2030-3` fails this (the title's token is `2030-31`); `September 7`
    passes it (the title's token is `7`).
    """
    body = short[:-3] if short.endswith("...") else short
    body = body.rstrip()
    if not body:
        return
    stripped_title = re.sub(r"\s*\?\s*$", "", title.strip())
    title_words = stripped_title.split()
    body_words = body.split()
    assert (
        body_words == title_words[: len(body_words)]
    ), f"the chop split a token: {short!r} is not a whole-word prefix of {title!r}"


# ── 1. MID_NUMBER: the chop never lands inside a token ───────────────────────────


@pytest.mark.parametrize(
    "title",
    [
        STANLEY_2030,
        UTAH,
        "Will New Jersey Devils advance to the Second Round of the 2027 Stanley Cup Playoffs?",
        "Will WTI Crude Oil (WTI) hit (HIGH) $100 in September 2027 or later?",
        "How many 5.5 or above earthquakes worldwide September 7 - September 13?",
    ],
)
def test_the_title_chop_never_splits_a_token(title):
    assert_whole_word_prefix(fr._short_market_name(title), title)


@pytest.mark.parametrize("title", [STANLEY_2030, UTAH])
def test_the_two_production_specimens_no_longer_show_a_split_number(title):
    """The two strings the census actually found on production, by the census's own test.

    Kept separate from the invariant above because this is the shape a reader SEES and
    the shape the census greps for — and because these two are exactly the rows where
    `MID_NUMBER_CHOP` is diagnostic rather than over-broad.
    """
    short = fr._short_market_name(title)
    assert not MID_NUMBER_CHOP.search(
        short
    ), f"chop landed inside a number: {short!r} (from {title!r})"


def test_the_chop_lands_on_a_word_boundary_not_a_character_count():
    """The specific production string, asserted as the whole value.

    Not `assert "2030-3" not in short` — that passes on a chop that merely moved the
    lie one character (`2030-` is also a number the market does not name).
    """
    assert (
        fr._short_market_name(STANLEY_2030)
        == "Canadian Team to Win the Stanley Cup® Before the..."
    )


def test_a_title_that_fits_is_returned_whole():
    """The chop must not fire on the 56 of 72 cards that never needed it."""
    assert fr._short_market_name("Fed rate hike in 2026?") == "Fed rate hike in 2026"
    assert fr._short_market_name("MLB World Series Winner") == "MLB World Series Winner"


def test_a_single_token_wider_than_the_window_still_terminates():
    """No word boundary to back up to. It must cut, and still not end mid-number."""
    short = fr._short_market_name("X" * 70 + "2027")
    assert short.endswith("...")
    assert not MID_NUMBER_CHOP.search(short)


# ── 2. NUMBER_ECHO: a card with no story does not restate its own hero ───────────


@pytest.mark.parametrize("probability", [0.03, 0.42, 0.71, 0.97])
def test_a_binary_with_no_signal_says_nothing_in_all_three_slots(probability):
    copy = fr.compose_binary_card_copy(
        market_name=TAIWAN,
        highlight_reasons=[],
        affirmative_probability=probability,
    )
    assert copy == ("", "", ""), (
        "the whole triple must be empty — blanking one slot moves the defect one "
        f"rung down the client fallback chain: {copy!r}"
    )


def test_multi_source_is_not_a_story_either():
    """`multi_source` is a count of our own inventory (#4160/D91), not a why-now."""
    copy = fr.compose_binary_card_copy(
        market_name=TAIWAN,
        highlight_reasons=["multi_source"],
        affirmative_probability=0.04,
    )
    assert copy == ("", "", "")


def test_no_generator_serves_a_bare_percent_sentence():
    """The three public entry points, at the route's own call shape."""
    kwargs = dict(
        market_name="Will a member of Congress resign or be expelled in Sep 2026?",
        highlight_reasons=[],
        leader_name="Yes",
        leader_probability=0.13,
        affirmative_probability=0.13,
        source_count=2,
    )
    headline = fr.generate_futures_headline(**kwargs)
    reason = fr.generate_futures_reason(**kwargs)
    summary = fr.generate_futures_context_summary(headline=headline, **kwargs)

    for slot, served in (
        ("headline", headline),
        ("reason", reason),
        ("context_summary", summary),
    ):
        assert not BARE_NUMBER_SENTENCE.match(
            served.strip()
        ), f"{slot} restated the hero number as prose: {served!r}"


# ── 3. TITLE_ECHO: the question is not its own answer ────────────────────────────


def test_a_weak_leader_label_does_not_promote_the_title_into_the_headline():
    headline = fr.generate_futures_headline(
        highlight_reasons=[],
        leader_name="June 30, 2027",  # a bare date — `_weak_outcome_label` is true
        leader_probability=0.40,
        market_name=ALITO,
    )
    assert headline == ""


def test_the_reason_slot_does_not_echo_the_title_verbatim():
    """Both rungs: the weak-leader one and the terminal one."""
    weak = fr.generate_futures_reason(
        market_name=ALITO,
        highlight_reasons=[],
        leader_name="June 30, 2027",
        leader_probability=0.40,
    )
    terminal = fr.generate_futures_reason(market_name=ALITO, highlight_reasons=[])
    assert weak == ""
    assert terminal == ""


def test_all_three_slots_are_empty_for_the_alito_card_together():
    """The served defect, as one assertion: the card printed the same phrase twice."""
    kwargs = dict(
        market_name=ALITO,
        highlight_reasons=[],
        leader_name="June 30, 2027",
        leader_probability=0.40,
    )
    headline = fr.generate_futures_headline(**kwargs)
    reason = fr.generate_futures_reason(**kwargs)
    summary = fr.generate_futures_context_summary(headline=headline, **kwargs)
    assert (headline, reason, summary) == ("", "", "")


# ── 4. CONTROLS — the survivals. A suite that only proves things went AWAY is ────
#      green while the feed goes silent, which is the bigger regression.


def test_a_field_market_still_names_its_leader():
    headline = fr.generate_futures_headline(
        highlight_reasons=[],
        leader_name="Los Angeles Dodgers",
        leader_probability=0.305,
        market_name="MLB World Series Winner",
    )
    assert headline == "Los Angeles Dodgers leads at 31%"


def test_a_moving_binary_still_gets_its_sentence():
    copy = fr.compose_binary_card_copy(
        market_name=TAIWAN,
        highlight_reasons=["major_movement_24h"],
        affirmative_probability=0.04,
        top_mover_change=0.06,
    )
    assert copy.headline == "Up 6 points today"
    assert "4% chance" in copy.context_summary, (
        "the number may still appear as part of a real sentence — what is banned is "
        "the number ALONE"
    )
    assert copy.reason.startswith("Will China invade Taiwan by end of 2026:")


def test_a_resolving_binary_still_gets_its_sentence():
    copy = fr.compose_binary_card_copy(
        market_name=TAIWAN,
        highlight_reasons=["resolving_soon_7d"],
        affirmative_probability=0.04,
    )
    # #4805: the words are the predicate. `resolving_soon_7d` fires on a duration,
    # not on a calendar week, so a card resolving on Monday could say "this week"
    # on a Sunday. Flipped with the ship, not exempted from it.
    assert copy.headline == "Resolving within a week"
    assert copy.context_summary == "4% chance, resolving within a week"


def test_the_title_is_still_used_as_a_SUBJECT_when_a_clause_follows_it():
    """The chop is not banned — echoing the title with nothing appended is.

    Every other `_short_market_name` call composes "<title> <fact>". Those must
    survive, or this ship has emptied the feed instead of cleaning it.
    """
    headline = fr.generate_futures_headline(
        market_name=UTAH,
        highlight_reasons=["major_movement_24h"],
        top_mover_name="June 30, 2027",  # weak label -> the title becomes the subject
        top_mover_change=0.08,
    )
    assert headline == (
        "Will Utah Mammoth advance to the Second Round of the... odds up 8 points"
    ), headline
    # The subject is a chop, and the chop still obeys the invariant.
    assert_whole_word_prefix(headline.split(" odds up")[0], UTAH)

    # The reason slot's equivalent rung keeps the title too, uncut, with the fact
    # in front of it. Also a real sentence, also must survive.
    reason = fr.generate_futures_reason(
        market_name=UTAH,
        highlight_reasons=["major_movement_24h"],
        top_mover_name="June 30, 2027",
        top_mover_change=0.08,
    )
    assert reason and reason != UTAH
    assert reason.startswith("Big odds movement in "), reason


def test_a_settled_card_is_unchanged():
    """`stale_past_resolution` already returned the empty triple; it still does."""
    assert fr.compose_binary_card_copy(
        market_name=TAIWAN,
        highlight_reasons=["stale_past_resolution"],
        affirmative_probability=0.04,
    ) == ("", "", "")
