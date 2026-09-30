"""#9782 — a date-ladder row borrowed its earliest rung's deadline.

Pillar TRUTH. Ship: a Discover row naming a far-off deadline stops saying it
resolves tomorrow.

THE DEFECT. Production Discover page one, 2026-09-30 09:45Z, Ukraine bundle:

    Will Russia capture Dovha Balka?                    ▼4.5 pts  37%
    December 31 · Resolves within a day

`GET /api/feed` item 10846851: `top_outcomes` December 31 0.37 (the row's
number), September 30 0.013; `resolution_date 2026-10-01T03:59Z` — the
September 30 rung's deadline, the EARLIEST rung of the Polymarket date ladder
(`polymarket:375975`); `context_summary "Resolves within a day"`.

`compute_futures_highlight` keys `resolving_soon_1d/2d` on the market's single
`resolution_date`. On a date ladder every rung has its own deadline, the stored
one is the earliest, and nesting makes the LATEST rung the dearest — the one the
card leads with. So the clause describes a 1% rung nobody is shown.

THE FIX drops the two day codes on a cumulative DATE ladder. It is silence, not
a re-keyed window: a bare leg ("December 31") has an inferred year, so the shown
rung's own deadline cannot be computed honestly. The day codes are captions only
(no headline rung, no primary label — #4842), so no card's order moves; the
neutrality tests below pin that on the specimen.

NOT IN THIS SHIP: the 7d/30d codes carry the same borrowed date, but they reach
the headline, which is a ranking input (#4842's docstring), so changing them is
a ranking change and takes a review.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils import feed_reasons as fr
from app.utils import futures_highlights as fh
from app.utils.ladder_monotonicity import cumulative_ladder_is_dated
from app.utils.market_display_name import elided_trailing_preposition

#: The re-measure instant, fixed (gotcha #44); every horizon is an offset.
NOW = datetime(2026, 9, 30, 9, 45, tzinfo=timezone.utc)

#: The specimen, verbatim: raw name, served rows, stored date.
DOVHA_RAW = "Will Russia capture Dovha Balka by...?"
DOVHA_DISPLAY = "Will Russia capture Dovha Balka?"
DOVHA_RESOLVES = datetime(2026, 10, 1, 3, 59, tzinfo=timezone.utc)
DOVHA_ROWS = [
    {"name": "December 31", "current_probability": 0.37,
     "probability_change_24h": -0.045},
    {"name": "September 30", "current_probability": 0.013,
     "probability_change_24h": 0.0},
]

#: A leg that carries its own deadline word (the `date:` namespace).
OWN_WORD_ROWS = [
    {"name": "Before Jan 1, 2027", "current_probability": 0.40,
     "probability_change_24h": 0.0},
    {"name": "Before Oct 1, 2026", "current_probability": 0.02,
     "probability_change_24h": 0.0},
]
OWN_WORD_NAME = "When will the ceasefire be signed?"

#: Controls: magnitude ladders, whose rungs all settle on the one stored date.
MAGNITUDE_ROWS = [
    {"name": "Above 62", "current_probability": 0.61,
     "probability_change_24h": 0.0},
    {"name": "Above 64", "current_probability": 0.20,
     "probability_change_24h": 0.0},
]
MAGNITUDE_NAME = "WTI Crude Oil (WTI) closes above ___ on September 30?"
STRIKE_ROWS = [
    {"name": "$345", "current_probability": 0.9, "probability_change_24h": 0.0},
    {"name": "$350", "current_probability": 0.6, "probability_change_24h": 0.0},
]
STRIKE_NAME = "Google (GOOGL) closes above ___ on September 30?"

DAY_CODES = {"resolving_soon_1d", "resolving_soon_2d"}


def _highlight(rows, name, resolves):
    return fh.compute_futures_highlight(
        market_name=name,
        outcomes=rows,
        resolution_date=resolves,
        now=NOW,
        sport_category="politics",
        market_tier=5,
        source_count=1,
    )


def _dovha_copy(reasons):
    """The headline + context summary `routes/feed.py` composes for the row."""
    kwargs = dict(
        market_name=DOVHA_DISPLAY,
        leader_name="December 31",
        leader_probability=0.37,
        leader_is_ladder_rung=True,
        leader_deadline_preposition=elided_trailing_preposition(DOVHA_RAW),
        now=NOW,
    )
    headline = fr.generate_futures_headline(highlight_reasons=reasons, **kwargs)
    return headline, fr.generate_futures_context_summary(
        headline=headline, highlight_reasons=reasons, **kwargs
    )


@pytest.fixture
def pre_fix(monkeypatch):
    """The scorer as it was: no date ladder is ever recognised."""
    monkeypatch.setattr(fh, "cumulative_ladder_is_dated", lambda *a, **k: False)


# ── The specimen ────────────────────────────────────────────────────────────


def test_the_specimen_carries_no_day_code():
    reasons = _highlight(DOVHA_ROWS, DOVHA_RAW, DOVHA_RESOLVES).reasons
    assert not DAY_CODES & set(reasons), reasons


def test_the_specimen_caption_no_longer_says_it_resolves_within_a_day():
    reasons = _highlight(DOVHA_ROWS, DOVHA_RAW, DOVHA_RESOLVES).reasons
    _, context = _dovha_copy(reasons)
    assert "within a day" not in context.lower()


def test_the_pre_fix_scorer_reproduces_the_served_caption_verbatim(pre_fix):
    """Fixture fidelity + strawman: the old path prints production's string."""
    reasons = _highlight(DOVHA_ROWS, DOVHA_RAW, DOVHA_RESOLVES).reasons
    assert "resolving_soon_1d" in reasons
    assert _dovha_copy(reasons)[1] == "Resolves within a day"


@pytest.mark.parametrize("hours", [6.0, 18.0, 24.0, 30.0, 47.0])
def test_no_day_code_anywhere_in_the_window_on_a_date_ladder(hours):
    for rows, name in ((DOVHA_ROWS, DOVHA_RAW), (OWN_WORD_ROWS, OWN_WORD_NAME)):
        reasons = _highlight(rows, name, NOW + timedelta(hours=hours)).reasons
        assert not DAY_CODES & set(reasons), (name, hours, reasons)


# ── Neutrality: a caption change, never an order change ─────────────────────


def test_score_and_headline_are_what_they_were(monkeypatch):
    new = _highlight(DOVHA_ROWS, DOVHA_RAW, DOVHA_RESOLVES)
    new_headline, _ = _dovha_copy(new.reasons)
    monkeypatch.setattr(fh, "cumulative_ladder_is_dated", lambda *a, **k: False)
    old = _highlight(DOVHA_ROWS, DOVHA_RAW, DOVHA_RESOLVES)
    old_headline, _ = _dovha_copy(old.reasons)
    assert new.score == old.score
    assert new.primary_reason == old.primary_reason
    assert new_headline == old_headline
    # The micro-bet suppression is ranking and is untouched.
    assert "micro_bet" in new.reasons and "micro_bet" in old.reasons
    assert set(old.reasons) - set(new.reasons) == {"resolving_soon_1d"}


# ── Controls: ladders whose rungs share the stored date keep the caption ────


@pytest.mark.parametrize(
    "rows,name",
    [
        pytest.param(MAGNITUDE_ROWS, MAGNITUDE_NAME, id="above-rungs"),
        pytest.param(STRIKE_ROWS, STRIKE_NAME, id="question-strike-rungs"),
    ],
)
@pytest.mark.parametrize(
    "hours,code",
    [(18.0, "resolving_soon_1d"), (30.0, "resolving_soon_2d")],
)
def test_a_magnitude_ladder_still_says_it_resolves_soon(rows, name, hours, code):
    reasons = _highlight(rows, name, NOW + timedelta(hours=hours)).reasons
    assert code in reasons, reasons


def test_a_non_ladder_field_still_says_it_resolves_soon():
    rows = [
        {"name": "Yes", "current_probability": 0.3, "probability_change_24h": 0.0},
        {"name": "No", "current_probability": 0.7, "probability_change_24h": 0.0},
    ]
    reasons = _highlight(rows, "Will it rain in NYC today?",
                         NOW + timedelta(hours=10)).reasons
    assert "resolving_soon_1d" in reasons


# ── The predicate ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rows,name,expected",
    [
        pytest.param(DOVHA_ROWS, DOVHA_RAW, True, id="bare-dates-under-by-question"),
        pytest.param(OWN_WORD_ROWS, OWN_WORD_NAME, True, id="own-word-dates"),
        pytest.param(MAGNITUDE_ROWS, MAGNITUDE_NAME, False, id="above-rungs"),
        pytest.param(STRIKE_ROWS, STRIKE_NAME, False, id="question-strike"),
        pytest.param(DOVHA_ROWS, "Will Russia capture Dovha Balka?", False,
                     id="bare-dates-without-the-blank-are-not-a-ladder"),
        pytest.param(DOVHA_ROWS[:1], DOVHA_RAW, False, id="one-leg"),
        pytest.param(DOVHA_ROWS + [{"name": "Yes"}], DOVHA_RAW, False,
                     id="a-yes-leg-disqualifies"),
    ],
)
def test_cumulative_ladder_is_dated(rows, name, expected):
    assert cumulative_ladder_is_dated(rows, question=name) is expected
