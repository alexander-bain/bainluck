"""#6925: a started game's chart stops shipping the half it does not draw.

`GET /api/events/{id}/history` serves the whole journey — months of pre-season
line drift and then the game — while a started game's chart opens on "Since
Start", not "All" (`OddsChart.tsx:416`: `(isClosed || isLive) && hasPostStartData
? "live" : "all"`). So the event page ships the large majority of its largest
payload in order that the first paint may draw exactly none of it.

Re-measured on production 2026-09-18 from the SERVED payload, after #6924's
split budget landed (which is why these ratios are smaller than the ones in the
issue: the budget split put back the in-window rows the old shared cap was
deleting, so there is more of the game in the payload now and the pre-kickoff
half is a smaller multiple of it — the fix is worth less than it was, and the
honest number is the one here):

    14638896  NFL, completed   2,299,202 B ->   588,254 B   3.9x   89.3% pre-kickoff
    14638444  NFL, completed   1,926,219 B ->   613,793 B   3.1x   85.6% pre-kickoff
    15297681  EPL, completed   1,506,850 B ->   106,770 B  14.1x   93.9% pre-kickoff

🔴 THE COST IS NOT THE WIRE. 2,299,202 B uncompressed is ~84 KB gzipped, so any
framing of this as "saves 2 MB of transfer" aims at a number that does not
exist. Nor is it the database: the uncapped read for 14638896 is 52.2 ms with 0
read blocks. What is left is serialize here and `JSON.parse` there, and both are
paid per emitted point.

🔴 A DEFERRAL, NOT A THINNING, which is what makes it free. The issue proposed
one reading per book per hour before kick-off; that spends fidelity, and "All"
renders every point it is handed, so the reader who taps it pays for the saving.
Omitting a half the caller can ask for again costs no fidelity at all.

🔴 WHAT MAKES THESE NON-VACUOUS — MUTATION, NOT ABSENCE. Run against the
unmodified module this file does not fail, it fails to COLLECT (`ImportError`,
pytest exit 2): the symbols do not exist yet. That is a statement about the
module's surface, not about behaviour, and it would be satisfied by a helper
that trimmed nothing. So each guarantee was instead mutated back individually
on the finished module and this file re-run:

    M1  route never applies the trim            -> 3 red  (the ship's own tests)
    M2  unplaceable point dropped, not kept     -> 1 red  (fail-open)
    M3  hasPostStartData fallback removed       -> 1 red  (the "All" cohort)
    M4  snapshot_count left describing the read -> 1 red  (the rendered count)
    M5  trim applied to EVERY range             -> 4 red  (the controls bite)

M5 is the one that matters: it is the shape in which this ship could delete a
point from a payload served today, and it is caught by the byte-identity
control and the unrecognised-range control. The first draft of the latter
compared against a baseline computed the same way and stayed GREEN under M5 —
a control that trims both sides of its own comparison is not a control — so it
now asserts the pre-kickoff half is present absolutely.

The controls are green before and after by design: a control that goes red
under the fix was testing the fix instead of guarding it.

Clock-swept via the anchors in `test_history_window_budget_6921`, which are
themselves swept 12/12; gotcha #44 is why `_kickoff()` looks the way it does.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime, timedelta, timezone

from app.models.models import Event
from app.routes.events import (
    EVENT_HISTORY_RANGE_SINCE_START,
    _omit_pre_kickoff_points,
    _point_is_at_or_after,
    get_event_odds_history,
)
from tests.test_history_window_budget_6921 import (
    EVENT_ID,
    SPORT_ID,
    _finished_event,
    _kickoff,
    _population,
    _snapshot,
    _sport,
)
from tests.test_price_table_fold_6390 import _HistoryRouteSession

UTC = timezone.utc


def _history(event, rows, **kwargs):
    session = _HistoryRouteSession(event, [], rows)
    return asyncio.run(
        get_event_odds_history(EVENT_ID, hours=48, db=session, **kwargs)
    )


def _since_start(event, rows):
    return _history(event, rows, chart_range=EVENT_HISTORY_RANGE_SINCE_START)


def _book_series(payload, book="draftkings"):
    return payload["bookmaker_history"].get(book, [])


def _stamps(points):
    return [datetime.fromisoformat(p["timestamp"]) for p in points]


def _pre_kickoff_only(kickoff):
    """A population that stops at kickoff — the `hasPostStartData == false` cohort."""
    return [
        _snapshot(kickoff - timedelta(days=30) + timedelta(minutes=i * 10), snap_id=3_000_000 + i)
        for i in range(120)
    ]


def _scheduled_event(kickoff):
    event = Event(
        id=EVENT_ID,
        sport_id=SPORT_ID,
        home_team_name="Buffalo Bills",
        away_team_name="Detroit Lions",
        commence_time=kickoff,
        status="scheduled",
        home_score=None,
        away_score=None,
        completed_at=None,
    )
    event.sport = _sport()
    return event


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_a_started_games_pre_kickoff_half_is_omitted_when_the_caller_asks():
    """The filed defect. 89% of the payload is outside the axis the reader sees."""
    kickoff = _kickoff()
    rows = _population(kickoff)

    full = _history(_finished_event(kickoff), rows)
    trimmed = _since_start(_finished_event(kickoff), rows)

    assert _book_series(full), "the rig must serve a sportsbook series at all"
    assert len(_book_series(trimmed)) < len(_book_series(full)), (
        "the whole ship is that the pre-kickoff half stops being emitted"
    )
    assert all(stamp >= kickoff for stamp in _stamps(_book_series(trimmed))), (
        "a point served under range=since_start is a point inside the axis the "
        "chart's default view draws"
    )


def test_the_game_itself_survives_the_trim_intact():
    """A deferral that deleted the game would be the #6921 defect with a flag on it."""
    kickoff = _kickoff()
    rows = _population(kickoff)

    full_in_game = [s for s in _stamps(_book_series(_history(_finished_event(kickoff), rows))) if s >= kickoff]
    trimmed_in_game = _stamps(_book_series(_since_start(_finished_event(kickoff), rows)))

    assert trimmed_in_game == full_in_game, (
        "every point the default view draws today must still be served; this is "
        "a deferral of what is not drawn, not a thinning of what is"
    )


def test_pre_window_omitted_tells_the_caller_a_second_request_would_say_more():
    kickoff = _kickoff()
    rows = _population(kickoff)

    assert _since_start(_finished_event(kickoff), rows)["pre_window_omitted"] is True
    assert _history(_finished_event(kickoff), rows)["pre_window_omitted"] is False, (
        "false on every payload served today, so the flag can only ever mean "
        "'there is more', never 'there might be'"
    )


def test_the_client_sends_a_parameter_actually_named_range():
    """The contract guard. Calling the function in Python bypasses the alias, so
    every other test here would pass with the alias misspelt and no client could
    reach the feature."""
    parameter = inspect.signature(get_event_odds_history).parameters["chart_range"]
    assert parameter.default.alias == "range"
    assert parameter.default.default == "all", (
        "the default must be the whole journey — a parameter whose job is to "
        "omit data may never omit it by default"
    )


# ---------------------------------------------------------------------------
# The controls: this ship may never subtract from a payload served today
# ---------------------------------------------------------------------------


def test_todays_payload_is_unchanged_byte_for_byte():
    kickoff = _kickoff()
    rows = _population(kickoff)

    default = _history(_finished_event(kickoff), rows)
    explicit_all = _history(_finished_event(kickoff), rows, chart_range="all")

    assert json.dumps(default, default=str) == json.dumps(explicit_all, default=str)
    assert any(stamp < kickoff for stamp in _stamps(_book_series(default))), (
        "the control is only a control while the default still carries the "
        "pre-kickoff half it is asserting about"
    )


def test_an_unrecognised_range_serves_the_whole_journey():
    """Fail-open. A value a future client invents, or a typo, can never delete a point."""
    kickoff = _kickoff()
    rows = _population(kickoff)
    baseline = _book_series(_history(_finished_event(kickoff), rows))

    for value in ("", "since-start", "SINCE_START", "live", "nonsense"):
        served = _book_series(_history(_finished_event(kickoff), rows, chart_range=value))
        assert len(served) == len(baseline), f"{value!r} must serve today's payload"
        # Absolutely, not just relative to a baseline computed the same way: a
        # mutant that trims EVERY range keeps the two sides equal and walks
        # straight through the comparison above.
        assert any(stamp < kickoff for stamp in _stamps(served)), (
            f"{value!r} must still carry the pre-kickoff half"
        )


def test_a_game_with_no_post_kickoff_readings_is_never_trimmed():
    """The cohort whose chart defaults to "All" — the one view that draws the
    half this would remove. It must be safe to send `range=since_start`
    unconditionally, or every client needs this route's own logic to decide."""
    kickoff = (datetime.now(UTC) + timedelta(hours=6)).replace(second=0, microsecond=0)
    rows = _pre_kickoff_only(kickoff)

    trimmed = _since_start(_scheduled_event(kickoff), rows)

    assert len(_book_series(trimmed)) == len(_book_series(_history(_scheduled_event(kickoff), rows)))
    assert trimmed["pre_window_omitted"] is False


# ---------------------------------------------------------------------------
# The helper's own fail-open guarantees
# ---------------------------------------------------------------------------


def _trim(commence_time, **series):
    payload = {
        "history": series.get("history", []),
        "bookmaker_history": series.get("bookmaker_history", {}),
        "win_prob_history": series.get("win_prob_history", {}),
        "win_prob_sources_meta": series.get("win_prob_sources_meta", {}),
        "aggregate_line": series.get("aggregate_line", []),
        "espn_history": series.get("espn_history", []),
    }
    omitted = _omit_pre_kickoff_points(commence_time=commence_time, **payload)
    return omitted, payload


def test_a_point_whose_timestamp_cannot_be_placed_is_kept():
    """Dropping an unknown is exactly how a trim deletes the game it was asked
    to preserve, so an unplaceable point is kept and costs bytes instead."""
    kickoff = _kickoff()
    for bad in ({"timestamp": "not-a-date"}, {"timestamp": None}, {}, {"timestamp": 17}):
        assert _point_is_at_or_after(bad, kickoff) is True


def test_a_source_emptied_by_the_trim_keeps_its_key_and_corrects_its_count():
    """#1828's filter above this one answers the same way — a client must not
    meet a shape this route does not already serve."""
    kickoff = _kickoff()
    stale = [{"timestamp": (kickoff - timedelta(days=3)).isoformat()}]
    live = [{"timestamp": (kickoff + timedelta(minutes=5)).isoformat()}]

    omitted, payload = _trim(
        kickoff,
        history=list(live),
        win_prob_history={"kalshi": list(stale), "espn": list(live)},
        win_prob_sources_meta={"kalshi": {"snapshot_count": 1}, "espn": {"snapshot_count": 1}},
    )

    assert omitted is True
    assert "kalshi" in payload["win_prob_history"], "an emptied series keeps its key"
    assert payload["win_prob_history"]["kalshi"] == []
    assert payload["win_prob_sources_meta"]["kalshi"]["snapshot_count"] == 0, (
        "the advertised count is rendered, so it may not describe rows that "
        "were not served"
    )
    assert payload["win_prob_sources_meta"]["espn"]["snapshot_count"] == 1


def test_a_row_with_no_kickoff_is_never_trimmed():
    stale = [{"timestamp": "2026-05-12T21:20:00+00:00"}]
    omitted, payload = _trim(None, history=list(stale), espn_history=list(stale))
    assert omitted is False
    assert payload["history"] == stale


def test_the_in_game_series_are_left_alone():
    """`espn_history` is in-game by construction (0% pre-kickoff on all three
    specimens) and is read here to decide the fallback."""
    kickoff = _kickoff()
    espn = [{"timestamp": (kickoff + timedelta(minutes=i)).isoformat()} for i in range(3)]
    before = list(espn)

    _trim(
        kickoff,
        history=[{"timestamp": (kickoff - timedelta(days=1)).isoformat()}],
        espn_history=espn,
    )

    assert espn == before
