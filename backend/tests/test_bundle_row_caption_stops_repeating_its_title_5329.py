"""#5329 — a bundle row's caption stops repeating the heading directly above it.

Photographed on production `36509e8e` at 390px, 2026-09-11 19:44Z, page one of
`/discover`, first row of the Russia–Ukraine bundle:

    Russia x Ukraine ceasefire agreement by...?                          23%
    December 31 · Russia x Ukraine ceasefire agreement by... shifted since May 14

`_copy_repeats_market_name` is a guard whose entire job is to stop that. It FIRED
on this row. Its three escapes then all missed — the reasons are `major_surprise`
so neither `resolving_soon` rung applies, and `leader_clause()` is empty because
the leader is `December 31`, itself a weak label — and control fell out of the
`if` to `return headline`, handing back the string the guard had just objected to.

Nothing pinned that fall-through, which is why it shipped. These guards pin it
from both sides: the rung fires where it should, and it does not outrank the
three escapes that were already there or reach a headline that says something new.

The fixture strings are the production row verbatim.
"""

from datetime import datetime, timezone

from app.utils.feed_reasons import (
    generate_futures_context_summary,
    generate_futures_headline,
)

NOW = datetime(2026, 9, 11, 19, 0, tzinfo=timezone.utc)
OPENED = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)

# The production row, verbatim.
MARKET = "Russia x Ukraine ceasefire agreement by...?"
WEAK_LEADER = "December 31"
SERVED_ECHO = "Russia x Ukraine ceasefire agreement by... shifted since May 14"


def _context(**overrides) -> str:
    """The production row's arguments, with named overrides."""
    kwargs = dict(
        headline=SERVED_ECHO,
        highlight_reasons=["major_surprise"],
        market_name=MARKET,
        leader_name=WEAK_LEADER,
        leader_probability=0.23,
        top_surprise_change=-0.09,
        top_surprise_opened_at=OPENED,
        now=NOW,
    )
    kwargs.update(overrides)
    return generate_futures_context_summary(**kwargs)


def test_the_headline_really_is_the_echo_this_test_file_is_about():
    """Anchor: the input is the string production served, not one I invented.

    If `generate_futures_headline` ever stops emitting the market name here,
    every guard below is testing a row that no longer exists and should be
    re-derived rather than deleted.
    """
    headline = generate_futures_headline(
        highlight_reasons=["major_surprise"],
        top_surprise_name=WEAK_LEADER,
        top_surprise_change=-0.09,
        market_name=MARKET,
        leader_name=WEAK_LEADER,
        leader_probability=0.23,
        top_surprise_opened_at=OPENED,
        now=NOW,
    )
    assert headline == SERVED_ECHO


def test_the_caption_no_longer_repeats_the_market_name():
    caption = _context()

    assert caption == "Shifted since May 14"
    # The point of the ship, stated as the reader's complaint rather than as a
    # string equality: the title is not in the line underneath the title.
    assert "Russia x Ukraine" not in caption
    assert "ceasefire agreement" not in caption


def test_the_caption_is_not_empty_because_empty_promotes_the_echo():
    """An empty context summary does not suppress the echo, it promotes it.

    Both clients read `firstMeaningful([context_summary, headline, reason,
    hook_description])` (#4265), so `""` here just hands the same restated
    question back through the next link in the chain. This is the reason the
    rung composes a sentence instead of bailing out.
    """
    caption = _context()

    assert caption != ""
    assert caption.strip() == caption


def test_the_dated_half_survives_because_it_is_the_informative_half():
    """#4758 put that date on the row; this ship must not take it back off."""
    assert "May 14" in _context()


# --- the three escapes that were already there still outrank the new rung ---


def test_resolving_within_a_week_still_wins_over_the_new_rung():
    assert (
        _context(highlight_reasons=["major_surprise", "resolving_soon_7d"])
        == "Resolves within a week"
    )


def test_resolving_within_a_month_still_wins_over_the_new_rung():
    assert (
        _context(highlight_reasons=["major_surprise", "resolving_soon_30d"])
        == "Resolves within a month"
    )


def test_a_real_leader_still_wins_over_the_new_rung():
    """With a nameable leader there is a better sentence than a bare date."""
    caption = _context(leader_name="Vladimir Putin", leader_probability=0.23)

    assert caption == "Vladimir Putin leads at 23%"
    assert "Shifted since" not in caption


# --- and the rung does not reach rows it has no business on ---


def test_a_headline_that_says_something_new_is_left_alone():
    """The Fed row from the same page one, which was already correct.

    `Up 61 points since Apr 29` does not restate its market name, so the guard
    never fires and the new rung is unreachable.
    """
    caption = generate_futures_context_summary(
        headline="Up 61 points since Apr 29",
        highlight_reasons=["major_surprise"],
        market_name="Fed Rate Hike by September 2026 Meeting?",
        leader_name=None,
        leader_probability=None,
        top_surprise_change=0.61,
        top_surprise_opened_at=datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc),
        now=NOW,
    )

    assert caption == "Up 61 points since Apr 29"


def test_an_undated_opening_does_not_invent_a_date():
    """No `top_surprise_opened_at` means no honest "since" to report.

    The old behaviour stands rather than a fabricated one: better the echo than
    a date we do not have.
    """
    caption = _context(top_surprise_opened_at=None)

    assert "Shifted since" not in caption
    assert caption == SERVED_ECHO


def test_a_row_with_no_surprise_reason_does_not_claim_one():
    """`Shifted since` is a claim that a move was detected. No move, no claim."""
    caption = _context(highlight_reasons=["some_other_reason"])

    assert "Shifted since" not in caption


def test_a_missing_change_does_not_claim_a_move():
    caption = _context(top_surprise_change=None)

    assert "Shifted since" not in caption


def test_a_moderate_surprise_is_carried_too():
    """The headline branch that produces the echo accepts both surprise tiers,
    so the rung that repairs it has to cover both or it fixes half the rows."""
    assert _context(highlight_reasons=["moderate_surprise"]) == "Shifted since May 14"
