"""#8127 — a 30d card that claims a leader also says what the leader is at.

Production 2026-09-23, 390px, `https://bainluck.com/`, card 19:

    POLITICS · Resolves Oct 4, 2026
    Brazil Presidential Election
    Flávio Bolsonaro leads          <- the caption a reader meets
    1 Flávio Bolsonaro 59% · 2 Luiz Inácio Lula da Silva 41% · 3 Renan Santos 1%

The caption asserts a lead and never states it, while the same card's `reason`
slot already said "leads at 59%" and `Presidents Cup - Winner` one slot above
said "Jackson Koivun leads at 6%; resolves within a week".

`generate_futures_context_summary`'s 30d rung was gated on
`headline == RESOLVING_WITHIN_MONTH_HEADLINE`, which is that rung's NO-LEADER
fallback. With a leader present `generate_futures_headline` returns its own
leader form, the gate missed, and the summary fell through to echoing the
headline — the one string in the module that carries the verb without a percent.

** WHY THE OLD GUARD WAS GREEN, AND WHAT THIS FILE DOES DIFFERENTLY. **
`test_feed_reasons.py::test_futures_context_summary_expands_generic_resolving_copy`
hands `generate_futures_context_summary` the bare constant as its `headline` and
asserts the expansion. The routes never do that: they pass whatever
`generate_futures_headline` returned for the same card. The fixture was an input
the pipeline cannot produce for a card that has a leader, so the assertion could
not fail however broken the gate was.

So every case below composes the summary the way the route composes it — from
the REAL headline generator's output — via `_compose`, and
`test_the_specimens_headline_is_not_the_generic_constant` pins the thing that
made the old guard vacuous: if the specimen's headline ever becomes the bare
constant again, this file's other assertions stop proving anything and that test
says so out loud rather than going quietly green.
"""

import pytest

from app.utils.feed_reasons import (
    RESOLVING_WITHIN_MONTH_HEADLINE,
    generate_futures_context_summary,
    generate_futures_headline,
)

# The served specimen, from `/api/feed?limit=60` on 2026-09-23.
SPECIMEN = dict(
    highlight_reasons=["resolving_soon_30d"],
    leader_name="Flávio Bolsonaro",
    leader_probability=0.59,
    rendered_leader_percent=59,
    rendered_runner_up_percent=41,
    market_name="Brazil Presidential Election",
)


def _compose(**card):
    """Headline then summary, exactly as the feed routes chain them.

    The whole point of the file: the summary is never handed a headline that
    was not produced for this same card.
    """
    headline = generate_futures_headline(**card)
    summary = generate_futures_context_summary(headline=headline, **card)
    return headline, summary


def test_the_specimens_headline_is_not_the_generic_constant():
    """The anti-vacuity pin — see the module docstring.

    The old guard passed because its fixture headline was the bare constant.
    If that ever becomes what the real generator returns for a card WITH a
    leader, the rest of this file would be testing the path that was never
    broken, so the regression is asserted here directly.
    """
    headline, _ = _compose(**SPECIMEN)

    assert headline != RESOLVING_WITHIN_MONTH_HEADLINE
    assert headline == "Flávio Bolsonaro leads; resolves within a month"


def test_a_monthly_card_with_a_visible_lead_states_the_percent():
    _, summary = _compose(**SPECIMEN)

    assert summary == "Flávio Bolsonaro leads at 59%; resolves within a month"


@pytest.mark.parametrize(
    "leader_name, probability, leader_pct, runner_up_pct",
    [
        # The two cards actually serving the defect on 2026-09-23.
        ("Flávio Bolsonaro", 0.59, 59, 41),
        ("1.9 to 2.1%", 0.44, 44, 31),
        # A comfortable lead and a one-point lead: the percent is owed whatever
        # the margin, so long as the board can show it (#6187).
        ("Runaway Favourite", 0.91, 91, 4),
        ("Narrow Leader", 0.35, 35, 34),
    ],
)
def test_every_visible_lead_on_a_monthly_card_carries_its_percent(
    leader_name, probability, leader_pct, runner_up_pct
):
    """Severing the fix for one specimen must not leave the others passing.

    Four leaders rather than one because the repaired branch reconstructs the
    headline from `leader_name` and the agreement verb: a specimen set that
    varied only the percentage would still pass an implementation that got the
    subject wrong.
    """
    _, summary = _compose(
        highlight_reasons=["resolving_soon_30d"],
        leader_name=leader_name,
        leader_probability=probability,
        rendered_leader_percent=leader_pct,
        rendered_runner_up_percent=runner_up_pct,
        market_name="Some Monthly Market",
    )

    assert summary == f"{leader_name} leads at {leader_pct}%; resolves within a month"


def test_a_tie_on_a_monthly_card_is_byte_identical(  # #6187
):
    """The tie form already stated the percent and must not move.

    It is deliberately NOT routed through the repaired branch — it reaches the
    reader by falling through to the headline — so this pins that the fix did
    not quietly take over a case it was not measured on.
    """
    headline, summary = _compose(
        highlight_reasons=["resolving_soon_30d"],
        leader_name="Tied Team",
        leader_probability=0.22,
        rendered_leader_percent=22,
        rendered_runner_up_percent=22,
        market_name="Some Cup",
    )

    assert headline == "Tied Team at 22%; resolves within a month"
    assert summary == "Tied Team at 22%; resolves within a month"


def test_a_monthly_card_with_no_leader_is_byte_identical():
    headline, summary = _compose(highlight_reasons=["resolving_soon_30d"])

    assert headline == RESOLVING_WITHIN_MONTH_HEADLINE
    assert summary == "Resolves within a month"


def test_the_weekly_sibling_is_byte_identical():
    """The 7d rung was already correct — it is the card that made the defect
    legible, one slot above the specimen in the same edition."""
    _, summary = _compose(
        highlight_reasons=["resolving_soon_7d"],
        leader_name="Jackson Koivun",
        leader_probability=0.06,
        rendered_leader_percent=6,
        rendered_runner_up_percent=4,
        market_name="Presidents Cup - Winner",
    )

    assert summary == "Jackson Koivun leads at 6%; resolves within a week"


def test_a_stronger_rung_is_not_hijacked_by_the_monthly_clause():
    """`resolving_soon_30d` can sit in `reasons` while the headline picks a
    louder rung. The repaired gate matches the headline the 30d branch itself
    builds, so a movement headline still reaches the reader as the news."""
    card = dict(
        highlight_reasons=["resolving_soon_30d", "major_movement_24h"],
        leader_name="Flávio Bolsonaro",
        leader_probability=0.59,
        rendered_leader_percent=59,
        rendered_runner_up_percent=41,
        market_name="Brazil Presidential Election",
    )
    headline = generate_futures_headline(top_mover_name="Lula", top_mover_change=0.08, **card)
    summary = generate_futures_context_summary(
        headline=headline, top_mover_change=0.08, **card
    )

    assert headline == "Lula up 8 points today"
    assert summary.startswith("Lula up 8 points today")
    assert "resolves within a month" not in summary


def test_no_monthly_leader_caption_names_a_leader_without_a_percent():
    """The class, not the specimen: sweep the shapes a 30d card can take and
    assert none of them reaches a reader naming a leader with no number."""
    cards = [
        dict(leader_name="Flávio Bolsonaro", leader_probability=0.59,
             rendered_leader_percent=59, rendered_runner_up_percent=41),
        dict(leader_name="Tied Team", leader_probability=0.22,
             rendered_leader_percent=22, rendered_runner_up_percent=22),
        dict(leader_name="Layne Riggs", leader_probability=0.29,
             rendered_leader_percent=29, rendered_runner_up_percent=12),
        dict(leader_name="Above 68", leader_probability=0.51,
             rendered_leader_percent=51, rendered_runner_up_percent=50),
    ]
    offenders = []
    for card in cards:
        _, summary = _compose(
            highlight_reasons=["resolving_soon_30d"],
            market_name="Some Monthly Market",
            **card,
        )
        if card["leader_name"] in summary and "%" not in summary:
            offenders.append(summary)

    assert offenders == []
