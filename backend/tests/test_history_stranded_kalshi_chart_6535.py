"""#6535 — the chart kept drawing the settled grade that #6522 withdrew from the hero.

WHAT A READER SAW
-----------------
`/events/15313166` at 390px, **after** #6522 went live: hero "No price yet",
header "Starts in 23m", and a Win Probability curve flat at ~52% all day then
spiking vertically to a labelled **99%** with the endpoint dot. The page
withdrew the number in its loudest position and kept it in the chart — and, as
#6535 notes, that is arguably *harder* to notice than before, because the hero
no longer corroborates it.

#6522 reasoned that "the hero and the chart do not read `futures_outcomes`.
They read `Event.win_probability_sources`." True of the hero. The chart reads
`win_prob_snapshots`, a separate persisted series, and withdrawing a live key
does not retract rows already written there.

THE POPULATION IS LIVE AND THE LEGS WERE READ AT THE VENUE, NOT INFERRED
------------------------------------------------------------------------
Production, 2026-09-16 16:24Z. Eight events were pre-kick-off with a Kalshi
market and no Kalshi leg carrying a price; **four of those still served a Kalshi
chart series** while none of the eight still carried the hero — so #6522's half
is working and this is precisely the half it did not reach:

    event      commence   served kalshi series          venue (api.elections.kalshi.com)
    15313382   16:30Z     198 pts, 0.60 -> 0.995        BAN finalized 'yes' / HRU 'no'
    15313613   17:00Z      30 pts, 0.045 -> 0.01        QUE finalized 'yes' / TIK 'no'
    15313385   16:40Z      99 pts                       REYSAN finalized 'yes' / DESRAQ 'no'
    15313397   19:00Z       3 pts, 0.71 -> 0.50         both legs finalized, result 'scalar'

Every one of those eight legs carried `expected_expiration_time` EQUAL to our
stored `commence_time` — which is the #5905/#6568 clock defect underneath all of
this, and the reason the repair here is deliberately reversible rather than a
deletion. See `test_a_settled_grade_is_not_always_a_ghost` below.

`result='scalar'` on 15313397 is worth keeping: it is a venue vocabulary word
not in any status allowlist we wrote, and `venue_answered`'s truthiness test
caught it anyway. A rule written against the results known on the day would not
have.

WHY THE PREDICATE IS THE EXPENSIVE ONE
---------------------------------------
`NOT jsonb_exists(win_probability_sources, 'kalshi')` needs no join and is true
of exactly the rows the hero sweep has drained, so it looks like a free way to
ask this question. Measured over the 345 pre-kick-off events carrying a Kalshi
chart series on 2026-09-16: the cheap form and #6522's book test agree on 4, and
the cheap form fires on **13 more whose Kalshi book is live**. It would hide a
legitimate curve on thirteen pages to repair four. That measurement is why
`KALSHI_BOOK_SILENT_SQL` exists as one shared object and is asked with a join.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.tasks.prediction_market_matching import (
    _KALSHI_STRANDED_PRE_KICKOFF_HERO_SQL,
)
from app.utils.futures_liveness import (
    KALSHI_BOOK_SILENT_FOR_EVENT_SQL,
    KALSHI_BOOK_SILENT_SQL,
)

from tests.test_history_window_stale_open_event import _history  # noqa: E402

UTC = timezone.utc

#: The headline production specimen: 198 points ending at the venue's own grade.
_SPECIMEN_ID = 15313382


def _snapshot(when, home_prob, *, source="kalshi"):
    return SimpleNamespace(
        event_id=_SPECIMEN_ID,
        captured_at=when,
        source=source,
        home_win_probability=home_prob,
        away_win_probability=round(1.0 - home_prob, 4),
        draw_probability=None,
        game_state={"market_name": "Bandecchi vs Hruncakova"},
    )


def _stranded_curve(now, *, source="kalshi"):
    """Pre-match drift that ends in a settlement — the shape the reader sees.

    The last point is the grade. The ones before it are honest pre-match prices,
    which is why the repair cannot simply truncate a tail: nothing on the row
    tells a 0.99 settlement apart from a 0.99 lopsided quote. Read at the venue
    on 2026-09-16, `KXWTACHALLENGERMATCH-26SEP16LAZMIN-LAZ` was `active` with
    `result ''` and a live book at exactly 0.99.
    """
    start = now - timedelta(hours=6)
    rows = [
        _snapshot(start + timedelta(minutes=10 * step), round(0.55 + step * 0.01, 4),
                  source=source)
        for step in range(20)
    ]
    rows.append(_snapshot(now - timedelta(minutes=8), 0.995, source=source))
    return rows


def _pre_kickoff_event(now, *, minutes_to_start=25, status="scheduled"):
    """Our own row still says this contest has not started."""
    return SimpleNamespace(
        id=_SPECIMEN_ID,
        status=status,
        commence_time=now + timedelta(minutes=minutes_to_start),
        completed_at=None,
        home_team_name="Bandecchi",
        away_team_name="Hruncakova",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key="tennis_wta"),
        sport_id=1,
        box_score_data=None,
        # #6522 has already drained the hero on this population — all four
        # production specimens read `hero_still_present: 0`. The chart must be
        # repaired without leaning on that, because the sweep that drains it
        # self-drains and the strict-only arm measured 1 event where the hero
        # was still there and the book was already silent.
        win_probability_sources={},
    )


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


async def test_the_chart_stops_drawing_the_grade_the_hero_already_withdrew():
    now = datetime.now(UTC)
    event = _pre_kickoff_event(now)

    payload, session = await _history(
        event, _stranded_curve(now), hours=24, kalshi_book_silent=True
    )

    assert "kalshi" not in payload["win_prob_history"], (
        "the settled 99% is still plotted on a page that says the match has not started"
    )
    assert session.kalshi_silence_asked == 1, (
        "the book question must be asked exactly once per request, not per point"
    )


async def test_the_legend_loses_the_curve_with_it():
    """A legend naming a line nobody draws is #3810's confusion in reverse."""
    now = datetime.now(UTC)
    payload, _ = await _history(
        _pre_kickoff_event(now), _stranded_curve(now), hours=24,
        kalshi_book_silent=True,
    )

    assert "kalshi" not in payload["win_prob_sources"]


async def test_the_surface_is_still_a_surface():
    """The withholding must not empty the chart — every sibling survives whole.

    An empty chart passes every refusal assertion above while being a worse page
    than the one this repair exists to fix, so the positive half is asserted on
    the same request: Polymarket's series arrives byte-for-byte identical with
    and without the Kalshi withdrawal.
    """
    now = datetime.now(UTC)
    rows = _stranded_curve(now) + _stranded_curve(now, source="polymarket")

    kept, _ = await _history(
        _pre_kickoff_event(now), rows, hours=24, kalshi_book_silent=False
    )
    withdrawn, _ = await _history(
        _pre_kickoff_event(now), rows, hours=24, kalshi_book_silent=True
    )

    assert "kalshi" in kept["win_prob_history"]
    assert "kalshi" not in withdrawn["win_prob_history"]
    assert (
        withdrawn["win_prob_history"]["polymarket"]
        == kept["win_prob_history"]["polymarket"]
    ), "the sibling series changed while a different source was withdrawn"
    assert withdrawn["win_prob_sources"]["polymarket"] == (
        kept["win_prob_sources"]["polymarket"]
    )


def _flat(now, value, source):
    """A second source that DISAGREES with the grade, so the aggregate can move.

    Three identical curves make every aggregate assertion vacuous — removing one
    of three equal sources changes no average. That is exactly the shape my first
    probe of this had, and it reported A == B == C, which reads as "the
    withdrawal is clean" and is really "nothing here could have differed".
    """
    start = now - timedelta(hours=6)
    return [
        _snapshot(start + timedelta(minutes=10 * step), value, source=source)
        for step in range(21)
    ]


async def test_the_withdrawn_grade_leaves_the_AGGREGATE_line_too():
    """🔴 The bigger half, and it is not the Kalshi curve.

    `aggregate_line` is built from `win_prob_history` further down this same
    route, so before this repair the withdrawn settlement was also driving the
    chart's **Bain Luck aggregate** — the line a reader takes as our answer.
    Measured through the real route: with Polymarket and ESPN both flat at 0.50
    and the stranded Kalshi series ending at its 0.995 grade, the aggregate's
    last point reads **0.995** unrepaired and **0.50** repaired.

    The assertion is byte-identity against a payload that NEVER HELD the Kalshi
    rows, not merely "the number moved": a partial withdrawal that left one
    bucket behind would still move it.

    This also keeps the repair consistent with #6522 rather than merely adjacent
    to it — the blend dropped Kalshi from `win_probability_sources` at the same
    moment, and the chart's own aggregate was the one place still averaging it in.
    """
    now = datetime.now(UTC)
    stranded = _stranded_curve(now)
    others = _flat(now, 0.50, "polymarket") + _flat(now, 0.50, "espn")

    withdrawn, _ = await _history(
        _pre_kickoff_event(now), stranded + others, hours=24, kalshi_book_silent=True
    )
    never_had_it, _ = await _history(
        _pre_kickoff_event(now), others, hours=24, kalshi_book_silent=True
    )
    unrepaired, _ = await _history(
        _pre_kickoff_event(now), stranded + others, hours=24, kalshi_book_silent=False
    )

    assert withdrawn["aggregate_line"] == never_had_it["aggregate_line"], (
        "the withdrawn grade left residue in the aggregate line"
    )
    assert withdrawn["aggregate_line"][-1]["home_probability"] == 0.50

    # The rig can see a difference at all — without this the assertion above
    # would pass against a route that never computed an aggregate.
    assert unrepaired["aggregate_line"][-1]["home_probability"] == 0.995
    assert unrepaired["aggregate_line"] != withdrawn["aggregate_line"]


# ---------------------------------------------------------------------------
# The controls. Each fails EXACTLY ONE clause, so each isolates one of them.
# ---------------------------------------------------------------------------


async def test_a_live_kalshi_book_keeps_its_curve_before_kick_off():
    """Fails the BOOK clause only — still pre-kick-off.

    The production control is `15307676` (Omonia Nicosia v Celta Vigo): pre-kick-off
    at 19:45Z with 189 Kalshi points and a live book, measured `silent: false` in
    the same read that convicted the four specimens. Thirteen such events would
    lose a legitimate curve under the cheap predicate this test pins us away from.
    """
    now = datetime.now(UTC)
    payload, session = await _history(
        _pre_kickoff_event(now), _stranded_curve(now), hours=24,
        kalshi_book_silent=False,
    )

    assert payload["win_prob_history"]["kalshi"], (
        "a pre-kick-off event whose Kalshi book is still quoting lost its chart"
    )
    assert session.kalshi_silence_asked == 1


async def test_a_started_contest_keeps_its_curve_even_with_a_silent_book():
    """Fails the CLOCK clause only — the book is silent.

    "Settled means settled": once our own row agrees the contest has started,
    the grade is the honest last point and the chart is where a reader goes to
    see the journey to it. This is also what makes the repair reversible — the
    series returns by itself when `commence_time` passes, with nothing deleted.
    """
    now = datetime.now(UTC)
    event = _pre_kickoff_event(now, minutes_to_start=-90, status="live")

    payload, session = await _history(
        event, _stranded_curve(now), hours=24, kalshi_book_silent=True
    )

    assert payload["win_prob_history"]["kalshi"], (
        "a contest our row says is under way lost its Kalshi curve"
    )
    assert session.kalshi_silence_asked == 0, (
        "the book was queried on a page that can never withdraw — wasted round trip"
    )


async def test_a_page_with_no_kalshi_series_never_asks_the_question():
    """The query is gated on there being something to withdraw."""
    now = datetime.now(UTC)
    payload, session = await _history(
        _pre_kickoff_event(now), _stranded_curve(now, source="polymarket"),
        hours=24, kalshi_book_silent=True,
    )

    assert session.kalshi_silence_asked == 0
    assert payload["win_prob_history"]["polymarket"]


async def test_a_settled_grade_is_not_always_a_ghost():
    """🔴 Why this is a serve-time refusal and NOT a row deletion.

    On production `15307696` (Port FC v Kobe) the venue's book closed ~58 minutes
    BEFORE our stored kick-off, because that stored hour is Kalshi's
    `expected_expiration_time` rather than a kick-off (#5905 / #6568). The match
    really happened and the grade is the honest number; our clock is the defect.
    Every one of the four specimens above shares that shape — stored
    `commence_time` equal to the venue's `expected_expiration_time` to the minute.

    A repair that deleted `win_prob_snapshots` rows would destroy a true final
    point on that class. This one cannot: the same rows are served again the
    moment the row's own clock passes, which this test asserts on ONE unchanged
    set of snapshot rows.
    """
    now = datetime.now(UTC)
    rows = _stranded_curve(now)

    before, _ = await _history(
        _pre_kickoff_event(now, minutes_to_start=25), rows, hours=24,
        kalshi_book_silent=True,
    )
    after, _ = await _history(
        _pre_kickoff_event(now, minutes_to_start=-5), rows, hours=24,
        kalshi_book_silent=True,
    )

    assert "kalshi" not in before["win_prob_history"]
    assert len(after["win_prob_history"]["kalshi"]) == len(rows), (
        "the withheld points did not come back once our own clock agreed — "
        "this repair is meant to be reversible, and something deleted them"
    )
    assert after["win_prob_history"]["kalshi"][-1]["home_probability"] == 0.995


# ---------------------------------------------------------------------------
# The shared object. #6535's scope note asks for this explicitly.
# ---------------------------------------------------------------------------


def test_the_chart_and_the_hero_sweep_ask_ONE_question():
    """Not "the two agree today" — the same characters, from one constant.

    #6535: "A third opinion about the same key in `win_prob_snapshots` is the
    same hazard." Two statements that merely happen to match are exactly what
    drifts; this asserts they are built from one object, so they cannot.
    """
    clause = KALSHI_BOOK_SILENT_SQL.strip()

    assert clause in str(_KALSHI_STRANDED_PRE_KICKOFF_HERO_SQL)
    assert clause in KALSHI_BOOK_SILENT_FOR_EVENT_SQL


def test_the_hero_sweep_still_carries_its_own_two_clauses():
    """The interpolation must not have eaten the clock or the hero test.

    An f-string that dropped a neighbouring line would still contain the shared
    clause and pass the test above, while selecting every event in the table.
    """
    sql = str(_KALSHI_STRANDED_PRE_KICKOFF_HERO_SQL)

    assert "e.status = 'scheduled'" in sql
    assert "e.commence_time > NOW()" in sql
    assert "jsonb_exists(e.win_probability_sources, 'kalshi')" in sql
    assert "LIMIT :limit" in sql


def test_the_single_event_form_is_bound_not_interpolated():
    """One parameter, named, so no caller can concatenate an id into it."""
    assert ":event_id" in KALSHI_BOOK_SILENT_FOR_EVENT_SQL
    assert "AS silent" in KALSHI_BOOK_SILENT_FOR_EVENT_SQL
