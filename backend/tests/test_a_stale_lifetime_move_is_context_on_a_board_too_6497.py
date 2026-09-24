"""#6497 — a multi-outcome Discover card stops leading its caption with a
February price move.

#6482 shipped this rule for the BINARY card and scoped itself there on purpose,
naming these rows as the follow-up. It could leave the binary headline
byte-identical because a binary card's reader-visible slot is `context_summary`.
On a multi-outcome board the HEADLINE is the slot the reader reads —
`generate_futures_context_summary` returns it verbatim once the leader's name
already appears in it — so the same clause has to land in a different generator,
and that generator's output is a ranking input.

Measured on production v4612 (`154be569`), `/api/feed?limit=60`, 2026-09-16 06:4xZ:

    idx 29  Which party will win the U.S. Senate?            (108620)
            headline == context_summary == 'Democratic Party up 15 points since Feb 19'
            board standing beneath it: 55 / 45

    idx 53  How many Republican senators will lose reelection in 2026?  (109593)
            headline == context_summary == '5 or more up 40 points since Feb 19'
            board standing beneath it: 52 / 26

Feb 19 is the bulk `opening_captured_at` date covering 57,122 outcomes — when we
first saw the row, not a day anything happened to it.

Every test fixes `now` explicitly. Nothing here branches on the wall clock
(gotcha #44): the anchors are absolute datetimes and the horizon is crossed by
moving `now`, never by what day the suite happens to run.
"""

from datetime import datetime, timezone

import pytest

from app.utils.feed_market_quality import _GENERIC_HEADLINES
from app.utils.feed_reasons import (
    generate_futures_context_summary,
    generate_futures_headline,
)

# Read off the production feed the morning this was filed.
FEB_19 = datetime(2026, 2, 19, 12, tzinfo=timezone.utc)  # midday: same day in every US zone (#8350)
NOW = datetime(2026, 9, 16, 6, 45, tzinfo=timezone.utc)

#: `now` set so FEB_19 is three days old — inside the seven-day news horizon.
#: This is how the suite reads the BEFORE string without a second code path:
#: same inputs, same branch, the horizon simply has not been crossed.
WITHIN_HORIZON_NOW = datetime(2026, 2, 22, 12, tzinfo=timezone.utc)

SENATE = dict(
    market_name="Which party will win the U.S. Senate?",
    leader_name="Democratic Party",
    leader_probability=0.545,
    rendered_leader_percent=55,
    rendered_runner_up_percent=45,
    top_surprise_name="Democratic Party",
    top_surprise_change=0.15000000000000002,
    top_surprise_is_printed=True,
)

R_SENATORS = dict(
    market_name="How many Republican senators will lose reelection in 2026?",
    leader_name="5 or more",
    leader_probability=0.5227,
    rendered_leader_percent=52,
    rendered_runner_up_percent=26,
    top_surprise_name="5 or more",
    top_surprise_change=0.3999999999999999,
    top_surprise_is_printed=True,
)


def headline(specimen, *, reason="major_surprise", opened_at=FEB_19, now=NOW, **over):
    kwargs = {**specimen, **over}
    return generate_futures_headline(
        highlight_reasons=[reason],
        source_count=2,
        top_surprise_opened_at=opened_at,
        now=now,
        **kwargs,
    )


# ── the ship ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "specimen,expected",
    [
        (SENATE, "Democratic Party leads at 55%, up 15 points since Feb 19"),
        (R_SENATORS, "5 or more leads at 52%, up 40 points since Feb 19"),
    ],
)
def test_the_two_production_cards_state_their_standing_before_the_stale_move(
    specimen, expected
):
    assert headline(specimen) == expected


@pytest.mark.parametrize(
    "specimen,before",
    [
        (SENATE, "Democratic Party up 15 points since Feb 19"),
        (R_SENATORS, "5 or more up 40 points since Feb 19"),
    ],
)
def test_inside_the_horizon_the_move_still_leads_byte_for_byte(specimen, before):
    """A move measured this week IS the news and is not demoted.

    Byte-identity against the string production actually served is what makes
    this a reorder rather than a rewrite.
    """
    assert headline(specimen, now=WITHIN_HORIZON_NOW) == before


@pytest.mark.parametrize("specimen", [SENATE, R_SENATORS])
def test_the_move_is_never_dropped_and_never_loses_its_date(specimen):
    """D1 clause (a) demotes the move to context; it does not delete it."""
    out = headline(specimen)
    assert "since Feb 19" in out
    assert "points" in out
    # and the standing is genuinely in FRONT of it, not appended after
    assert out.index("%") < out.index("since Feb 19")


@pytest.mark.parametrize("specimen", [SENATE, R_SENATORS])
def test_the_subject_is_not_said_twice_when_the_mover_is_the_leader(specimen):
    """"Democratic Party leads at 55%, Democratic Party up 15 points" is the
    shape the elision exists to prevent. Both live specimens take this arm."""
    out = headline(specimen)
    assert out.count(specimen["leader_name"]) == 1


def test_a_mover_that_is_not_the_leader_keeps_its_own_subject():
    """No live specimen — every dated-baseline board on the page that morning
    moved on its own leader — so the arm is manufactured rather than sampled.
    Without the name the sentence would attribute the Republican move to the
    Democrats."""
    out = headline(SENATE, top_surprise_name="Republican Party")
    assert out == (
        "Democratic Party leads at 55%, Republican Party up 15 points since Feb 19"
    )


def test_the_horizon_boundary_is_the_same_seven_days_the_binary_card_uses():
    """Seven days old is still news; eight is not. Pinned on both sides so a
    silent widening of `_LIFETIME_MOVE_NEWS_HORIZON_DAYS` reddens here."""
    seven = FEB_19.replace(day=26)
    eight = FEB_19.replace(day=27)
    assert headline(SENATE, now=seven) == "Democratic Party up 15 points since Feb 19"
    assert headline(SENATE, now=eight) == (
        "Democratic Party leads at 55%, up 15 points since Feb 19"
    )


# ── the refusals it inherits, rather than restates ───────────────────────────


def test_a_tied_board_states_the_level_and_never_claims_a_lead():
    """#6187: the comparative is dropped, but the standing is still said — the
    reorder must not become a reason to print "leads" where the board shows a
    tie."""
    out = headline(SENATE, rendered_runner_up_percent=55)
    assert out == "Democratic Party at 55%, up 15 points since Feb 19"
    assert "leads" not in out


def test_a_cumulative_ladder_rung_keeps_todays_string_rather_than_a_false_favorite():
    """#4640: a ladder rung has no favorite to be. The refusal is to stay
    silent about standing, NOT to blank the card — the move is the only
    sentence it has."""
    out = headline(R_SENATORS, leader_is_ladder_rung=True)
    assert out == "5 or more up 40 points since Feb 19"


@pytest.mark.parametrize(
    "over",
    [
        {"leader_name": None},
        {"leader_probability": None},
        {"leader_name": "", "leader_probability": None},
    ],
)
def test_no_leader_means_todays_string_not_an_empty_card(over):
    """The gate fails CLOSED onto the existing sentence. Returning "" here
    would hand the caption chain down to `reason`/`hook_description` and, on a
    card with neither, reproduce the #4056 empty terminal this module has been
    closing for three ships."""
    out = headline(SENATE, **over)
    assert out == "Democratic Party up 15 points since Feb 19"


@pytest.mark.parametrize("weak", [">5000", "120", "Mar 4"])
def test_a_weak_outcome_label_still_borrows_the_market_title_unchanged(weak):
    """The arm above the reorder is untouched: a label that cannot be a subject
    still produces the market-level paraphrase, with no standing bolted on.

    The labels are the ones `_weak_outcome_label` actually refuses — a bare
    threshold, a bare number, a bare date. Note that "Above 120" is NOT one of
    them despite that function's docstring example: its regex is anchored on a
    numeric token, so a prose-prefixed threshold reads as nameable and takes the
    normal subject arm. Pinned here because the first draft of this test assumed
    otherwise and the suite caught it.
    """
    out = headline(SENATE, top_surprise_name=weak)
    # `_short_market_name` drops the trailing question mark.
    assert out == "Which party will win the U.S. Senate shifted since Feb 19"


def test_an_undatable_baseline_says_nothing_here_as_before():
    """No `opening_captured_at` means the branch never speaks — the module
    refuses "from opening" without a date, and the reorder does not create a
    new way in."""
    out = headline(SENATE, opened_at=None)
    assert "since" not in out


def test_the_down_direction_reads_correctly():
    out = headline(SENATE, top_surprise_change=-0.225)
    assert out == "Democratic Party leads at 55%, down 22.5 points since Feb 19"


def test_the_percent_stated_is_the_one_the_board_prints_not_one_re_derived():
    """#4146: the sentence states the card's OWN rendered percent.

    The operands have to DISAGREE or this asserts nothing — with the served
    0.5227 the two routes both give 52 and the guard is vacuous (the first
    draft was, and the mutation run caught it). So the divergence here is the
    real one this market showed on 2026-09-16: `/api/admin/discover-quality/
    trace/109593` carried `leader_probability: 0.57` while the card's own row
    printed 52, because the board is normalized at serve time. Re-deriving from
    the probability would print "at 57%" three millimetres above a row reading
    52% — #6181's defect, which is why `_display_pct` takes the printed value.
    """
    out = headline(R_SENATORS, leader_probability=0.57)
    assert out == "5 or more leads at 52%, up 40 points since Feb 19"
    assert "57%" not in out


# ── the slot the reader actually reads ───────────────────────────────────────


@pytest.mark.parametrize("specimen", [SENATE, R_SENATORS])
def test_the_context_summary_follows_the_headline_without_appending_the_leader(
    specimen,
):
    """This is why the headline had to move. The context summary returns the
    headline verbatim (its `; {leader}` append is skipped because the leader's
    name is already in the string), so on these cards the headline IS the
    caption — and a fix confined to `context_summary`, as #6482's was, could
    not have reached them."""
    head = headline(specimen)
    ctx = generate_futures_context_summary(
        headline=head,
        highlight_reasons=["major_surprise"],
        market_name=specimen["market_name"],
        leader_name=specimen["leader_name"],
        leader_probability=specimen["leader_probability"],
        rendered_leader_percent=specimen["rendered_leader_percent"],
        rendered_runner_up_percent=specimen["rendered_runner_up_percent"],
        source_count=2,
        top_surprise_change=specimen["top_surprise_change"],
        top_surprise_opened_at=FEB_19,
        now=NOW,
    )
    assert ctx == head


# ── the ranking input this ship deliberately touches ─────────────────────────


@pytest.mark.parametrize("specimen", [SENATE, R_SENATORS])
def test_neither_side_of_the_horizon_is_a_generic_headline(specimen):
    """The ranking claim, asserted rather than argued.

    On the ranking path `has_specific_explanation` reduces to `headline not in
    _GENERIC_HEADLINES` (`reason` is not passed there), so the 93/80/60 cap in
    `explanation_score_rank` turns on membership of that set alone. Both the
    before and the after string carry a dated move, so neither can be a member
    and the cap branch is unreachable on both sides — the card's words change
    and its order does not.
    """
    assert headline(specimen, now=WITHIN_HORIZON_NOW) not in _GENERIC_HEADLINES
    assert headline(specimen) not in _GENERIC_HEADLINES
