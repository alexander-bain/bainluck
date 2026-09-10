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
from datetime import datetime, timezone

import pytest

from app.utils.feed_quality_debug import WHY_NOW_MARKERS
from app.utils.feed_reasons import (
    DIAGNOSTIC_PHRASES,
    claims_undated_baseline,
    contains_diagnostic_phrase,
    generate_futures_context_summary,
    generate_futures_headline,
    generate_futures_reason,
)
from app.utils.futures_highlights import (
    FUTURES_WEIGHTS,
    PRIMARY_REASON_LABELS as FUTURES_PRIMARY_REASON_LABELS,
    compute_futures_highlight,
)

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


# ── The producer the first draft of this guard could not see ─────────────────
#
# CI found it and three local bands did not. `routes/feed.py` composes the served
# headline as `generate_futures_headline(...) or highlight_result.primary_reason`,
# and `primary_reason` came off a SECOND label table in `futures_highlights.py`
# carrying "Sources disagree", "Rankings shakeup" and "Multi-source". Deleting the
# branches in `feed_reasons` alone would have made a headline empty MORE often and
# handed those exact three strings to the fallback — the fix making its own defect
# more visible. A ban that covers one producer is a ban on one producer.


def test_the_headline_fallback_label_is_never_a_diagnostic():
    """Every scoring signal's last-resort display label, one at a time."""
    offenders = []
    for signal in ALL_HIGHLIGHT_REASONS:
        label = dict(FUTURES_PRIMARY_REASON_LABELS).get(signal)
        if contains_diagnostic_phrase(label):
            offenders.append(f"{signal} -> primary_reason: {label!r}")
    assert (
        not offenders
    ), "the headline fallback talks about our pipeline:\n" + "\n".join(offenders)


def test_the_served_headline_is_clean_however_it_is_composed():
    """The real expression from `routes/feed.py`, not either half alone.

    A divergent, multi-source, reshuffled card with no mover data is the exact
    shape that empties the headline and reaches the fallback.
    """
    reasons = ["source_divergence", "multi_source", "rank_shakeup"]
    highlight = compute_futures_highlight(
        market_tier=1,
        sport_category="basketball",
        source_count=3,
        max_source_divergence=0.09,
        outcomes=[
            {
                "name": "Thunder",
                "probability": 0.31,
                "probability_change_24h": 0.06,
                "rank": 1,
                "rank_change_24h": 0,
                "opening_probability": 0.25,
            }
        ],
    )
    served = (
        generate_futures_headline(
            highlight.reasons,
            leader_name="Thunder",
            leader_probability=0.31,
            source_count=3,
        )
        or highlight.primary_reason
        or ""
    )
    assert not contains_diagnostic_phrase(served), f"served headline: {served!r}"
    assert not contains_diagnostic_phrase(highlight.primary_reason)
    # And the signals themselves are untouched — this is a COPY fix, not a
    # scoring change. The card still ranks on the divergence it no longer names.
    assert highlight.flags.has_source_divergence is True
    assert "source_divergence" in highlight.reasons

    for signal in reasons:
        one_signal_headline = (
            generate_futures_headline(
                [signal], leader_name=None, leader_probability=None, source_count=3
            )
            or dict(FUTURES_PRIMARY_REASON_LABELS).get(signal)
            or ""
        )
        assert not contains_diagnostic_phrase(
            one_signal_headline
        ), f"{signal} composed to {one_signal_headline!r}"


# ── The same reach, the predicate it was missing (discover/030, D1 clause a) ──
#
# Everything above asks ONE question of the served string: does it talk about our
# pipeline? "Well off its opening price" does not — it talks about the market —
# so it passed every test in this file while being served as the only prose on 6
# of 7 cards carrying it (production, 2026-09-09, `GET /api/feed` limit=100: 11
# occurrences over 100 cards, incl. 2 bundle-member rows).
#
# Clause a bans a second thing: measuring against a baseline without dating it.
# That ban is conditional — the same sentence with "since Mar 4" in it is the
# copy we WANT — so it cannot be spelled as more entries in DIAGNOSTIC_PHRASES.
# The tests below reuse this file's reach (every signal, every composition) with
# `claims_undated_baseline` as the question.


def test_no_signal_serves_an_undated_baseline_claim():
    """Each scoring signal's last-resort label, and each generator's output."""
    offenders = []
    for signal in ALL_HIGHLIGHT_REASONS:
        label = dict(FUTURES_PRIMARY_REASON_LABELS).get(signal)
        if claims_undated_baseline(label):
            offenders.append(f"{signal} -> primary_reason: {label!r}")
        for producer, served in _every_generator_output(
            [signal],
            source_count=1,
            leader_name="Luiz Inácio Lula da Silva",
            leader_probability=0.52,
        ):
            if claims_undated_baseline(served):
                offenders.append(f"{signal} -> {producer}: {served!r}")
    assert (
        not offenders
    ), "served copy cites a baseline it will not date:\n" + "\n".join(offenders)


def test_the_surprise_card_composes_to_nothing_rather_than_to_the_undated_claim():
    """The production shape: a lifetime move whose opening has no date.

    `_biggest_move_from_opening` returns `opened_at=None` for every market today
    (`opening_captured_at` is not in the outcome projection — CERT-622), so the
    dated sentence cannot fire. The card must then say NOTHING, not fall through
    to a label that makes the claim anyway.
    """
    highlight = compute_futures_highlight(
        market_tier=1,
        sport_category="hockey",
        market_name="Canadian Team to Win the Stanley Cup Before the 2030-31 Season",
        outcomes=[
            {
                "name": "Yes",
                "probability": 0.415,
                "probability_change_24h": None,
                "rank": 1,
                "rank_change_24h": 0,
                "opening_probability": 0.70,
            }
        ],
    )
    # The SIGNAL is untouched — this is a copy fix, not a ranking change.
    assert "major_surprise" in highlight.reasons
    assert highlight.primary_reason is None

    served = (
        generate_futures_headline(
            highlight.reasons,
            top_surprise_name="Yes",
            top_surprise_change=-0.285,
            top_surprise_opened_at=None,  # the state of every market today
            now=datetime(2026, 9, 9, 21, 0, tzinfo=timezone.utc),
        )
        or highlight.primary_reason
        or ""
    )
    assert served == "", f"the card still says {served!r} over an undated opening"

    # And WITH a date the sentence is restored in full, so this is a gate on the
    # missing baseline, not a deletion of the signal's voice.
    dated = generate_futures_headline(
        highlight.reasons,
        top_surprise_name="Yes",
        top_surprise_change=-0.285,
        top_surprise_opened_at=datetime(2026, 3, 4, tzinfo=timezone.utc),
        now=datetime(2026, 9, 9, 21, 0, tzinfo=timezone.utc),
    )
    assert "since Mar 4" in dated
    assert not claims_undated_baseline(dated)


def test_the_undated_baseline_detector_catches_what_it_is_for():
    """A predicate that matches nothing bans nothing (a guard that lies).

    Pinned against the exact strings production served on 2026-09-09 and against
    the dated sentences that must keep passing.
    """
    assert claims_undated_baseline("Well off its opening price")
    assert claims_undated_baseline("Off its opening price")
    assert claims_undated_baseline("0 (0 bps) · Well off its opening price")
    assert claims_undated_baseline(
        "China x Philippines military clash moved up 37.5 points from opening"
    )
    # The dated forms — the copy this clause exists to produce.
    assert not claims_undated_baseline("OpenAI release up 27.0 points since Mar 4")
    assert not claims_undated_baseline(
        "Down 28.5 points since Mar 4, 2025 — now 42% chance"
    )
    assert not claims_undated_baseline(
        "Brazil Presidential Election has shifted since Sep 1"
    )
    # And it does not fire on copy that names no baseline at all.
    assert not claims_undated_baseline("New favorite")
    assert not claims_undated_baseline("Renan Santos down 28.5 points today")
    assert not claims_undated_baseline(None)
