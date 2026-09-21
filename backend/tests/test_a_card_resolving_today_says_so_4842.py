"""#4842 — the card resolving tomorrow was the one card that could not say so.

Pillar DISCOVER, on TRUTH. Ship D1 (#4066): page one says why each card is here
this morning — and a resolution inside two days is the most time-urgent why-now
a card can have.

THE DEFECT. `compute_futures_highlight` suppresses micro-bets (daily temperature,
oil close, stock close) with `result.score -= 20`. That suppression is a RANKING
decision and it is right. But it is the `if` arm of the same `if/elif` that owns
the resolution DISPLAY codes:

    if days_until <= 1:
        result.score -= 20
        result.reasons.append("micro_bet")
    elif 0 < days_until <= 30:
        ... append("resolving_soon_7d" | "resolving_soon_30d")

so days 0-1 were the only window inside thirty days that could emit no
resolution copy at all. Same shape as #4695 one rung down this ladder: a reason
code deleted with the score term it happened to sit beside.

MEASURED on production `39b50b84`, `GET /api/feed?limit=250`, 2026-09-21 09:45Z
(payload banked at `artifacts-discover/d381/BEFORE-4842-feed250-39b50b84.json`):
3 of 129 served cards resolve inside one day and not one says when it resolves.
The issue's own filed specimen — `Will "Nvidia" be said during the next episode
of the All-In Podcast?`, `resolution_date 2026-09-11T23:59Z`, ~30 hours out —
served `headline: None`, `reason: ""`, `context_summary: ""`.

WHY TWO RUNGS. `timedelta.days` truncates toward zero, so `days_until <= 1` spans
0h to 47h59m. "within a day" is false across most of the second half of that
window, and #4805 settled that the copy is classified off the UNFLOORED horizon.
One rung would have missed this issue's own specimen, which sits at 1.25 days.

WHY NO HEADLINE. `routes/feed.py` feeds the composed headline to
`apply_explanation_quality_score` and `explanation_score_rank` (7837 / 10828 /
12311), both called with `reason=None`, so `has_specific_explanation` reduces to
`headline not in _GENERIC_HEADLINES` and the headline decides a 93/80/60 cap. A
new headline would therefore move a card's ORDER as well as its words — and the
two directions do not cancel: a silent card's `None`/`""` is a member, while a
card already carrying a dated move is not. So this ship writes CAPTIONS: the day
rungs live in `generate_futures_reason`, `generate_futures_context_summary`, and
last-before-the-terminal in `compose_binary_card_copy` where the headline it
composes is `""` — byte-identical to the terminal it precedes.

That is the claim the neutrality tests below pin, and it was measured old-vs-new
over 52 shapes (horizon x field/binary x moved/still) before it was written:
headline moved 0, score moved 0, explanation class moved 0, captions gained 48.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils import feed_reasons as fr
from app.utils.feed_market_quality import _GENERIC_HEADLINES, has_specific_explanation
from app.utils.futures_highlights import (
    PRIMARY_REASON_LABELS,
    compute_futures_highlight,
)

#: 02:45 Pacific on the Monday the re-measure was taken. A fixed literal with
#: every horizon OFFSET from it (gotcha #44): the whole subject is what the copy
#: says relative to a resolution instant, so an anchor that moves tests nothing.
NOW = datetime(2026, 9, 21, 9, 45, tzinfo=timezone.utc)

#: The issue's own specimen, verbatim from the served payload it was filed from.
ALL_IN = "Will \"Nvidia\" be said during the next episode of the All-In Podcast?"
#: A daily-close market — the class `micro_bet` exists to suppress, and the class
#: for which "resolves today" is the single most useful thing a card can say.
WTI = "WTI Crude Oil (WTI) closes above ___ on September 21?"


def _field(change: float = 0.0) -> list[dict]:
    return [
        {"name": "Above 62", "current_probability": 0.61,
         "probability_change_24h": change},
        {"name": "Above 64", "current_probability": 0.20,
         "probability_change_24h": 0.0},
    ]


def _highlight(hours: float | None, *, name: str = WTI, change: float = 0.0):
    return compute_futures_highlight(
        market_name=name,
        outcomes=_field(change),
        resolution_date=None if hours is None else NOW + timedelta(hours=hours),
        now=NOW,
        sport_category="economics",
        market_tier=2,
        source_count=1,
    )


def _copy(reasons: list[str], *, name: str = WTI, change: float | None = None):
    """The three strings `routes/feed.py` composes, for one reason set."""
    kwargs = dict(
        market_name=name,
        leader_name="Above 62",
        leader_probability=0.61,
        top_mover_change=change,
        now=NOW,
    )
    headline = fr.generate_futures_headline(highlight_reasons=reasons, **kwargs)
    return {
        "headline": headline,
        "reason": fr.generate_futures_reason(highlight_reasons=reasons, **kwargs),
        "context": fr.generate_futures_context_summary(
            headline=headline, highlight_reasons=reasons, **kwargs
        ),
    }


# ── The window, rung by rung ────────────────────────────────────────────────
#
# Hours from `NOW`, and the resolution code the card must carry. The three rows
# inside 48h are the ship; the rows around them are the controls that prove it
# did not widen into a window that already worked.

WINDOW = [
    pytest.param(0.0, "resolving_soon_1d", id="resolves-this-instant"),
    pytest.param(6.0, "resolving_soon_1d", id="six-hours"),
    pytest.param(23.0, "resolving_soon_1d", id="tonight"),
    pytest.param(24.0, "resolving_soon_1d", id="exactly-one-day"),
    pytest.param(24.5, "resolving_soon_2d", id="just-over-one-day"),
    pytest.param(30.0, "resolving_soon_2d", id="the-all-in-specimen-30h"),
    pytest.param(47.9, "resolving_soon_2d", id="just-under-two-days"),
    pytest.param(49.0, "resolving_soon_7d", id="two-days-is-the-week-rung"),
    pytest.param(24 * 6, "resolving_soon_7d", id="six-days"),
    pytest.param(24 * 20, "resolving_soon_30d", id="twenty-days"),
]


@pytest.mark.parametrize("hours,code", WINDOW)
def test_every_horizon_inside_a_month_carries_exactly_one_resolution_code(
    hours, code
):
    reasons = _highlight(hours).reasons
    carried = [r for r in reasons if r.startswith("resolving_soon")]
    assert carried == [code], f"{hours}h carried {carried}"


@pytest.mark.parametrize("hours", [0.0, 6.0, 23.0, 24.0, 24.5, 30.0, 47.9])
def test_the_suppression_the_caption_used_to_ride_on_is_untouched(hours):
    """`micro_bet` still fires, and it still costs exactly 20 points.

    The whole argument of this ship is that the ranking decision and the copy
    decision were never the same decision. If a later change buys the caption by
    letting the suppression go, this fails.
    """
    suppressed = _highlight(hours)
    # The same market a day and a half further out: past the micro-bet window,
    # nothing else about it differs, so the gap between them IS the suppression.
    unsuppressed = _highlight(hours + 48.0)
    assert "micro_bet" in suppressed.reasons
    assert "micro_bet" not in unsuppressed.reasons
    assert unsuppressed.score - suppressed.score == 20


def test_a_market_that_has_already_resolved_is_never_told_it_resolves_today():
    """`.days` truncates a past instant to 0 or negative, into the micro-bet arm.

    The feed's eligibility gate excludes those rows, so this is unreachable from
    the served page today — and it is the one sentence this ship must never
    emit, so it is pinned here rather than left to that gate.
    """
    for hours in (-0.5, -6.0, -24 * 9):
        reasons = _highlight(hours).reasons
        assert "micro_bet" in reasons
        assert not [r for r in reasons if r.startswith("resolving_soon")]


def test_an_unknown_resolution_date_still_says_nothing_about_resolving():
    reasons = _highlight(None).reasons
    assert not [r for r in reasons if r.startswith("resolving_soon")]


# ── What the reader actually reads ──────────────────────────────────────────


@pytest.mark.parametrize(
    "code,phrase",
    [("resolving_soon_1d", "within a day"), ("resolving_soon_2d", "within two days")],
)
def test_the_caption_states_the_deadline_in_both_generators(code, phrase):
    copy = _copy([code, "micro_bet"])
    assert phrase in copy["context"]
    assert phrase in copy["reason"]


@pytest.mark.parametrize(
    "code,phrase",
    [("resolving_soon_1d", "within a day"), ("resolving_soon_2d", "within two days")],
)
def test_a_binary_card_with_nothing_else_to_say_says_the_deadline(code, phrase):
    """The filed specimen's own shape: a yes/no card with no move and no hook.

    Before this ship it served `reason: ""` / `context_summary: ""` — the #4056
    terminal, which is correct when nothing about the world is true of the
    market and wrong when the market resolves tomorrow.
    """
    copy = fr.compose_binary_card_copy(
        market_name=ALL_IN,
        highlight_reasons=[code, "micro_bet"],
        affirmative_probability=0.62,
        now=NOW,
    )
    assert phrase in copy.context_summary
    assert "62% chance" in copy.context_summary
    assert copy.reason


def test_the_pre_fix_reason_set_is_still_silent():
    """The vacuity control for the two tests above.

    `micro_bet` alone is exactly what this arm emitted before #4842. If the
    assertions above can pass without the new codes, they are not testing this
    ship.
    """
    copy = fr.compose_binary_card_copy(
        market_name=ALL_IN,
        highlight_reasons=["micro_bet"],
        affirmative_probability=0.62,
        now=NOW,
    )
    assert copy == fr.BinaryCardCopy("", "", "")
    field = _copy(["micro_bet"])
    assert "within a day" not in field["context"]
    assert "within two days" not in field["context"]
    assert "within a day" not in field["reason"]
    assert "within two days" not in field["reason"]


def test_the_two_rungs_never_disagree_with_the_clock_they_were_classified_on():
    """End to end: the horizon decides the code, and the code decides the words.

    A producer and a consumer that agree on a vocabulary with nothing testing
    the join is how #4695 happened; #4805 added that assertion for the week and
    month rungs and this is the same assertion for the two day rungs.
    """
    assert "resolves within a day" in _copy(_highlight(10.0).reasons)["context"]
    assert "resolves within two days" in _copy(_highlight(30.0).reasons)["context"]
    # …and the false sentence is absent from the far side of each boundary.
    assert "within a day" not in _copy(_highlight(30.0).reasons)["context"]
    assert "within two days" not in _copy(_highlight(10.0).reasons)["context"]


# ── Ranking neutrality: the headline never moves ────────────────────────────
#
# This ship is copy. Every assertion below fails if it becomes a ranking change.

#: Reason sets a card in the micro-bet window can plausibly arrive with. Each is
#: paired with the day code to prove the code adds nothing to the headline.
CARRIER_REASONS = [
    pytest.param([], id="no-other-signal"),
    pytest.param(["micro_bet"], id="micro-bet-only"),
    pytest.param(["micro_bet", "major_movement_24h"], id="moved-today"),
    pytest.param(["micro_bet", "moderate_movement_24h"], id="moved-a-little"),
    pytest.param(["micro_bet", "leader_change"], id="new-favorite"),
    pytest.param(["micro_bet", "multi_source", "high_volume"], id="scoring-only"),
]


@pytest.mark.parametrize("reasons", CARRIER_REASONS)
@pytest.mark.parametrize("code", ["resolving_soon_1d", "resolving_soon_2d"])
def test_adding_the_day_code_leaves_the_headline_byte_identical(reasons, code):
    before = _copy(list(reasons), change=0.09)["headline"]
    after = _copy([*reasons, code], change=0.09)["headline"]
    assert after == before


@pytest.mark.parametrize("reasons", CARRIER_REASONS)
@pytest.mark.parametrize("code", ["resolving_soon_1d", "resolving_soon_2d"])
def test_adding_the_day_code_leaves_the_explanation_class_unchanged(reasons, code):
    """`has_specific_explanation` is the 93/80/60 cap's whole input on this path.

    Called the way the RANKING path calls it — `reason=None` — because that is
    the call whose answer decides the card's order.
    """
    def explained(rs):
        return has_specific_explanation(
            hook_description=None, headline=_copy(rs, change=0.09)["headline"]
        )

    assert explained([*reasons, code]) == explained(list(reasons))


@pytest.mark.parametrize("code", ["resolving_soon_1d", "resolving_soon_2d"])
def test_the_binary_composer_emits_the_terminals_own_empty_headline(code):
    copy = fr.compose_binary_card_copy(
        market_name=ALL_IN,
        highlight_reasons=[code, "micro_bet"],
        affirmative_probability=0.62,
        now=NOW,
    )
    assert copy.headline == ""
    assert copy.headline in _GENERIC_HEADLINES


@pytest.mark.parametrize("code", ["resolving_soon_1d", "resolving_soon_2d"])
def test_neither_day_code_has_a_primary_reason_label(code):
    """`routes/feed.py` serves `generate_futures_headline(...) or primary_reason`.

    A rung here would reach the headline through the `or` — the second door
    #4066's own note records being caught by — and undo the neutrality above.
    """
    assert code not in dict(PRIMARY_REASON_LABELS)


@pytest.mark.parametrize("code", ["resolving_soon_1d", "resolving_soon_2d"])
def test_a_card_that_already_leads_with_a_move_keeps_leading_with_it(code):
    """The editorial cost of the last-rung placement, stated as a test.

    A binary card with a dated lifetime move AND a deadline inside two days
    leads with the move. That is deliberate — reordering the two is a ranking
    decision — and it is pinned so nobody "fixes" it by accident.
    """
    moved = fr.compose_binary_card_copy(
        market_name=ALL_IN,
        highlight_reasons=[code, "micro_bet"],
        affirmative_probability=0.62,
        top_surprise_change=0.21,
        top_surprise_opened_at=NOW - timedelta(days=3),
        now=NOW,
    )
    assert "21 points" in moved.headline
    assert "within a day" not in moved.context_summary
    assert "within two days" not in moved.context_summary


def test_the_score_is_the_same_number_it_was_before_the_captions_arrived():
    """A pin, not a derivation: the micro-bet arm's score for a fixed specimen.

    `_highlight(30.0)` is this issue's specimen horizon. The number below was
    read off the arm BEFORE the caption was added to it; any later change that
    buys copy with score has to edit this line, which is the point of it.
    """
    assert _highlight(30.0).score == 40.0
    assert _highlight(10.0).score == 40.0
