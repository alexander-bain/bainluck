"""#4160 / #4133 (D1, #4066) — our own machinery never reaches a reader.

Three strings were on production page one the morning this shipped, and none of
them is a thing that happened in the world:

    "Tracked by 2 sources"                                <- the HEADLINE, 4 of 20
    "Luiz Inácio Lula da Silva (52%) leads Brazil Presidential Election
     across 2 sources"                                    <- the reason line
    "Multiple ranking changes; Hike 25bps leads at 55%"   <- the day before

The first two are counts of our own inventory (D91: attribution is BY NAME in the
source mark, never an anonymous integer in the body). The third described the
ordering of our leaderboard, and — worse — `WHY_NOW_MARKERS` listed it, so the
metric that is supposed to prove D1 shipped scored it as a card that had
explained itself.

🔴 THE GUARD IS RUNTIME, NOT A SOURCE SCAN. It drives every branch of the three
generators over the full cross-product of highlight reasons and asserts on the
OUTPUT, so a new branch that spells the same idea a new way still fails — and so
that moving a template behind a helper cannot blind it.
"""

import itertools

import pytest

from app.utils.feed_quality_debug import WHY_NOW_MARKERS
from app.utils.feed_reasons import (
    DIAGNOSTIC_PHRASES,
    contains_diagnostic_phrase,
    generate_futures_context_summary,
    generate_futures_headline,
    generate_futures_reason,
)
from app.utils.futures_highlights import FUTURES_WEIGHTS

# Every signal the scorer can attach to a card, plus the two lifetime-move
# reasons that only `feed_reasons` knows about. Driving the cross-product means
# the guard covers branches this file's author never read.
ALL_HIGHLIGHT_REASONS = sorted(
    set(FUTURES_WEIGHTS) | {"major_surprise", "moderate_surprise"}
)

MARKET_NAME = "Brazil Presidential Election"


#: `generate_futures_context_summary` takes the changes but not the mover names.
_CONTEXT_SUMMARY_KWARGS = {
    "leader_name",
    "leader_probability",
    "source_count",
    "affirmative_probability",
    "top_mover_change",
    "top_surprise_change",
    "top_surprise_opened_at",
    "now",
}


def _every_generator_output(reasons: list[str], **kwargs) -> list[tuple[str, str]]:
    """(what produced it, what it said) for the three served strings."""
    reason = generate_futures_reason(MARKET_NAME, reasons, **kwargs)
    headline = generate_futures_headline(reasons, market_name=MARKET_NAME, **kwargs)
    context = generate_futures_context_summary(
        headline=headline,
        highlight_reasons=reasons,
        market_name=MARKET_NAME,
        **{k: v for k, v in kwargs.items() if k in _CONTEXT_SUMMARY_KWARGS},
    )
    return [
        ("reason", reason),
        ("headline", headline),
        ("context_summary", context),
    ]


@pytest.mark.parametrize("source_count", [1, 2, 3, 7])
@pytest.mark.parametrize("with_leader", [True, False])
def test_no_single_signal_serves_a_diagnostic_phrase(source_count, with_leader):
    """Each signal alone, at every source count, with and without a leader."""
    kwargs = {
        "source_count": source_count,
        "leader_name": "Luiz Inácio Lula da Silva" if with_leader else None,
        "leader_probability": 0.52 if with_leader else None,
    }
    offenders = []
    for signal in ALL_HIGHLIGHT_REASONS:
        for producer, served in _every_generator_output([signal], **kwargs):
            if contains_diagnostic_phrase(served):
                offenders.append(f"{signal} -> {producer}: {served!r}")
    assert not offenders, "served copy talks about our pipeline:\n" + "\n".join(
        offenders
    )


def test_no_pair_of_signals_serves_a_diagnostic_phrase():
    """Pairs, because the ladder's order is what put the count on the screen.

    The production defect needed `multi_source` to survive every branch above
    it; a single-signal test would have missed a template that only appears when
    two signals are present.
    """
    offenders = []
    for left, right in itertools.combinations(ALL_HIGHLIGHT_REASONS, 2):
        for producer, served in _every_generator_output(
            [left, right],
            source_count=2,
            leader_name="Luiz Inácio Lula da Silva",
            leader_probability=0.52,
            top_mover_name="Jair Bolsonaro",
            top_mover_change=0.061,
        ):
            if contains_diagnostic_phrase(served):
                offenders.append(f"{left}+{right} -> {producer}: {served!r}")
    assert not offenders, "served copy talks about our pipeline:\n" + "\n".join(
        offenders
    )


def test_the_three_strings_that_were_on_page_one_are_not_producible():
    """Named, so a reader of this file knows exactly what was fixed."""
    multi_source = _every_generator_output(
        ["multi_source"],
        source_count=2,
        leader_name="Luiz Inácio Lula da Silva",
        leader_probability=0.52,
    )
    served = dict(multi_source)
    assert served["headline"] != "Tracked by 2 sources"
    assert "across 2 sources" not in served["reason"]
    # It still says the useful half: who leads, and at what.
    assert "Luiz Inácio Lula da Silva" in served["reason"]
    assert "52%" in served["reason"]

    shakeup = dict(
        _every_generator_output(
            ["rank_shakeup"],
            source_count=1,
            leader_name="Hike 25bps",
            leader_probability=0.55,
        )
    )
    assert "ranking change" not in shakeup["reason"].lower()
    assert "ranking change" not in shakeup["headline"].lower()

    divergence = dict(
        _every_generator_output(
            ["source_divergence"],
            source_count=2,
            leader_name="Hike 25bps",
            leader_probability=0.55,
        )
    )
    assert "disagree" not in divergence["reason"].lower()
    assert "disagree" not in divergence["headline"].lower()


def test_why_now_markers_are_disjoint_from_the_ban_list():
    """The credit list may never contain a phrase the ban list forbids.

    This is the assertion that would have failed the day "multiple ranking
    changes" was added to `WHY_NOW_MARKERS`: a metric cannot award a card for
    saying something the card is not allowed to say.
    """
    credited_but_banned = [
        marker
        for marker in WHY_NOW_MARKERS
        if any(phrase in marker.lower() for phrase in DIAGNOSTIC_PHRASES)
    ]
    assert not credited_but_banned, (
        "WHY_NOW_MARKERS credits banned pipeline vocabulary: " f"{credited_but_banned}"
    )


def test_the_ban_list_itself_still_catches_what_it_is_for():
    """A ban list that matches nothing is a ban on nothing (a guard that lies).

    Pins the detector against the exact strings production served, so a later
    edit that empties DIAGNOSTIC_PHRASES fails here rather than passing the four
    tests above vacuously.
    """
    assert contains_diagnostic_phrase("Tracked by 2 sources")
    assert contains_diagnostic_phrase(
        "Los Angeles Dodgers (30%) leads MLB World Series Winner across 2 sources"
    )
    assert contains_diagnostic_phrase("Multiple ranking changes in Fed decision")
    assert contains_diagnostic_phrase("Sources disagree (2)")
    assert contains_diagnostic_phrase("3 sources disagree, but Lula leads at 52%")
    assert contains_diagnostic_phrase(
        "Brazil Presidential Election tracked by 2 sources"
    )
    # And does not fire on the honest sentences that replaced them.
    assert not contains_diagnostic_phrase(
        "Luiz Inácio Lula da Silva (52%) leads Brazil Presidential Election"
    )
    assert not contains_diagnostic_phrase("New favorite: Hike 25bps (55%)")
    assert not contains_diagnostic_phrase("Jair Bolsonaro moved up 6.1 points today")
