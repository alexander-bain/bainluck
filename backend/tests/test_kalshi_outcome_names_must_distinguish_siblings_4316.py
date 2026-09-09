"""#4316 — a name that cannot tell two rows apart is not a name.

`_kalshi_outcome_name` decides each leg of a Kalshi event in isolation, so
nothing stopped it handing the SAME string to every leg. On production this
morning `/futures/108342` — "How many Attorneys General will Trump have?", an
open `market_tier=2` market — showed five outcomes at 54.5% / 23% / 3.2% /
3.2% / 1.05%, all five reading `Kxtrumpagcount`. The hero, all three chart
legend entries and the movement caption printed that one string.

Two routes reach the collapse, and the tests below pin both:

* the leg's ``title`` EQUALS the event title, so step 4 never applied and the
  ladder fell through to the series ticker (long-standing — the AG market);
* the leg's ``title`` is a QUESTION, so #4246's guard refuses it and the ladder
  falls to the same series ticker (introduced by #4246, still latent when this
  was written — `KXAKSENATEROUND-26` and friends held their distinct questions
  and would have collapsed on their next poll).

Every payload here is the venue's own, read from
`api.elections.kalshi.com/trade-api/v2/markets?series_ticker=...` on
2026-09-09 (notice 26: measure the venue, not our mirror).
"""

import pytest

from app.tasks.kalshi import (
    _kalshi_outcome_name,
    _parse_kalshi_ticker_name,
    _ticker_leg,
    kalshi_outcome_names,
)


class _Market:
    """The four fields the naming ladder reads off a venue market."""

    def __init__(self, ticker, title, subtitle=None, yes_sub_title=None):
        self.ticker = ticker
        self.title = title
        self.subtitle = subtitle
        self.yes_sub_title = yes_sub_title


# --- the two production specimens, verbatim from the venue --------------------

AG_EVENT = "How many Attorneys General will Trump have?"
AG_MARKETS = [
    # title == event title, yes_sub_title is a bare count
    _Market(f"KXTRUMPAGCOUNT-29-{n}", AG_EVENT, None, str(n))
    for n in (2, 3, 4, 5)
]

AK_EVENT = "How many rounds will the 2026 Alaska Senate election consist of?"
AK_MARKETS = [
    _Market(
        f"KXAKSENATEROUND-26-{n}",
        f"Will the 2026 Alaska Senate election consist of {n} rounds?",
        None,
        str(n),
    )
    for n in (1, 2, 3)
]


def test_the_ag_market_no_longer_prints_one_string_five_times():
    """The exact reader-visible failure that opened #4316."""
    names = kalshi_outcome_names(AG_EVENT, AG_MARKETS)

    assert sorted(names.values()) == ["2", "3", "4", "5"]
    assert "Kxtrumpagcount" not in names.values()


def test_the_question_titled_field_event_does_not_collapse():
    """#4246's guard is right; the last resort underneath it was not.

    Before this fix these three legs each returned `Kxaksenateround`.
    """
    names = kalshi_outcome_names(AK_EVENT, AK_MARKETS)

    assert sorted(names.values()) == ["1", "2", "3"]
    assert "Kxaksenateround" not in names.values()


@pytest.mark.parametrize(
    "event_title,markets",
    [(AG_EVENT, AG_MARKETS), (AK_EVENT, AK_MARKETS)],
    ids=["ag-count", "alaska-rounds"],
)
def test_no_multi_leg_event_shares_one_name(event_title, markets):
    """The invariant, stated once: distinct legs get distinct names."""
    names = kalshi_outcome_names(event_title, markets)

    assert len(set(names.values())) == len(markets)
    assert all(n.strip() for n in names.values())


def test_the_collapse_is_real_without_the_set_level_pass():
    """A red-if-reverted control.

    Without this, the two tests above could pass because the per-leg ladder was
    already fine, and the fix would be untested scaffolding. This pins that the
    per-leg ladder genuinely does collide on both specimens.
    """
    for event_title, markets in ((AG_EVENT, AG_MARKETS), (AK_EVENT, AK_MARKETS)):
        per_leg = {
            m.ticker: _kalshi_outcome_name(event_title, m, len(markets))
            for m in markets
        }
        assert len(set(per_leg.values())) == 1, (
            "specimen no longer reproduces the collapse; if the ladder changed, "
            "re-derive this test's premise rather than deleting it"
        )


# --- #4246 must not regress ---------------------------------------------------


def test_ryder_cup_names_are_untouched():
    """#4246's own ship. Real names never reach the collision ladder."""
    event = "2027 Ryder Cup Winner"
    markets = [
        _Market("KXPGARYDER-RC27-EUR", event, None, "Team Europe"),
        _Market("KXPGARYDER-RC27-USA", event, None, "Team USA"),
        _Market("KXPGARYDER-RC27-TIE", event, None, "Tie"),
    ]

    assert kalshi_outcome_names(event, markets) == {
        "KXPGARYDER-RC27-EUR": "Team Europe",
        "KXPGARYDER-RC27-USA": "Team USA",
        "KXPGARYDER-RC27-TIE": "Tie",
    }


def test_a_question_is_still_refused_when_something_else_distinguishes():
    """The #4246 ban survives: the collision ladder is only reached on a tie.

    Here `yes_sub_title` already tells the legs apart, so no leg is ever
    re-derived and neither question is printed.
    """
    event = "2027 Ryder Cup Winner"
    markets = [
        _Market(
            "KXPGARYDER-RC27-EUR",
            "Will Team Europe win the Ryder Cup?",
            None,
            "Team Europe",
        ),
        _Market(
            "KXPGARYDER-RC27-USA",
            "Will Team USA win the Ryder Cup?",
            None,
            "Team USA",
        ),
    ]

    names = kalshi_outcome_names(event, markets)

    assert sorted(names.values()) == ["Team Europe", "Team USA"]
    assert not any(n.endswith("?") for n in names.values())


# --- the ladder's own rungs ---------------------------------------------------


def test_ticker_leg_keeps_the_numeric_segment_the_old_parser_skipped():
    """`_parse_kalshi_ticker_name` walking past digits is the root cause."""
    assert _ticker_leg("KXTRUMPAGCOUNT-29-5") == "5"
    assert _parse_kalshi_ticker_name("KXTRUMPAGCOUNT-29-5") == "Kxtrumpagcount"


def test_a_single_market_event_is_still_yes():
    """Step 1 is not routed through the collision ladder."""
    event = "Will it rain in Seattle tomorrow?"
    markets = [_Market("KXRAIN-26SEP09-YES", event, None, None)]

    assert kalshi_outcome_names(event, markets) == {"KXRAIN-26SEP09-YES": "Yes"}


def test_an_unresolvable_tie_keeps_the_ladders_answer():
    """No candidate distinguishes, so nothing is invented.

    A duplicate name is bad; a fabricated one is worse. These two legs carry the
    SAME ticker, no sub-title, no subtitle, and titles equal to the event title
    — there is genuinely nothing to tell them apart, and the function must say
    so rather than guess.

    This case is why the distinctness test counts `len(group)` and not the
    length of a ticker-keyed dict: keyed by ticker these two collapse into one
    proposal, which then trivially satisfies "all distinct" and let the tie be
    broken by a value that breaks nothing.
    """
    event = "Some field event"
    markets = [
        _Market("KXFIELD-26", event, None, None),
        _Market("KXFIELD-26", event, None, None),
    ]

    names = kalshi_outcome_names(event, markets)

    assert set(names.values()) == {"Kxfield"}


def test_subtitle_breaks_a_tie_when_yes_sub_title_cannot():
    """Rung 2 of the collision ladder, exercised on its own."""
    event = "Who wins the thing?"
    markets = [
        _Market("KXTHING-26-A", event, "First option", None),
        _Market("KXTHING-26-B", event, "Second option", None),
    ]

    assert sorted(kalshi_outcome_names(event, markets).values()) == [
        "First option",
        "Second option",
    ]


def test_a_distinguishing_question_beats_an_indistinguishable_ticker():
    """Rung 3: when only the questions differ, print the questions.

    This is the deliberate concession to #4246. A question on a card is bad; the
    same string on every row of the card is worse, because the reader cannot
    even tell which row is which.

    The tickers here share their last segment, so the ticker rung underneath
    cannot break the tie either — the question is genuinely the only thing that
    tells these two apart.
    """
    event = "How many states redistrict?"
    markets = [
        _Market("KXREDIST-A-CNT", "Will 3 or more states redistrict?"),
        _Market("KXREDIST-B-CNT", "Will 4 or more states redistrict?"),
    ]

    names = kalshi_outcome_names(event, markets)

    assert names["KXREDIST-A-CNT"] == "Will 3 or more states redistrict?"
    assert names["KXREDIST-B-CNT"] == "Will 4 or more states redistrict?"


def test_a_cryptic_but_distinct_ticker_leg_is_left_alone():
    """The residual #4246 chose, pinned honestly rather than quietly widened.

    When the per-leg ladder already returns distinct values there is no
    collision, so this fix never runs — even though "T3"/"T4" read poorly. That
    is #4246's shipped judgement (ticker over question), and changing it is a
    different ship, not a rider on this one. Pinned so the next session sees the
    trade rather than rediscovering it.
    """
    event = "How many states redistrict?"
    markets = [
        _Market("KXNUMREDISTRICTING-26NOV03-T3", "Will 3 or more states redistrict?"),
        _Market("KXNUMREDISTRICTING-26NOV03-T4", "Will 4 or more states redistrict?"),
    ]

    assert sorted(kalshi_outcome_names(event, markets).values()) == ["T3", "T4"]
