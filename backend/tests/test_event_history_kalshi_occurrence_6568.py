"""Guard: the chart and the page agree about kick-off (#6568).

WHAT A READER SAW. On 2026-09-16 at 15:30:30Z, production served ONE event at
two different hours depending on which half of the page asked, both reads inside
the same second:

    GET /api/events/15307696            commence_time  12:15:00Z
    GET /api/events/15307696/history    commence_time  15:15:00Z

Port FC v Kobe, AFC Champions League. The venue had closed and graded the game
book at 14:16:57Z — so the 12:15Z reading is the true kick-off and the stored
15:15Z is the market's EXPECTED EXPIRATION (gotcha #14).

WHY THIS ROUTE, WHEN #5905 ALREADY FIXED THE PAGE. #5905's own docstring gives
the rule and, in the same breath, the reason this surface escaped it: "every
LIST-shaped surface reaches the correction through `fold_twin_events` … the
detail route folds nothing — there is one row and nothing to fold it against —
so it served the raw column". `/history` folds nothing EITHER. It resolves
duplicates through `folded_series_event_ids`, an id lookup that never constructs
the fold, so the correction had never run here. This is the unbuilt half of a
rule the producer had already written down.

WHAT THESE TESTS ARE ACTUALLY DEFENDING. Not "a route subtracts three hours":

* the wiring is dropped and the chart goes back to the stored hour
  (`test_the_history_route_serves_the_kickoff_not_the_expected_expiration`);
* the two halves of one page load drift apart again — the defect itself
  (`test_the_page_and_its_chart_serve_one_kickoff`);
* 🔴 the correction is applied to the SERVED FIELD but not to the consumers
  that reason about state with it
  (`test_the_corrected_clock_reaches_the_window_not_only_the_label`). This is
  the one that matters most and the one a cosmetic fix would fail: four readers
  below the insertion point take `event.commence_time` and decide whether the
  match is finished, stale-open, and how to bound the series. A fix that
  corrected the label alone would leave the page agreeing with itself about the
  hour while still reasoning from the wrong one;
* it fires on a row a schedule provider anchored, moving a REPORTED start;
* it fires outside soccer, where the 180-minute pad is a spread not a constant;
* it double-subtracts and advertises a kick-off six hours early.

🔴 THE REFUSAL TESTS ARE THE ONES THAT CAN GO VACUOUS. `recover_kalshi_
occurrence_starts` opens with `getattr(event, KALSHI_RECOVERY_STAMP, False)`,
and it refuses a row on four independent grounds. A refusal test therefore
passes against a route that never calls the recovery AT ALL — which is precisely
the pre-#6568 route. `test_the_rig_itself_can_see_a_correction` is the strawman
that fails if the rig ever stops being able to observe one, and every refusal
below is paired with the positive case on the same rig.

These tests drive the REAL route function rather than re-implementing its
windowing: a replicated window is a window that can agree with the test and
disagree with production.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.routes.events import (
    _event_started_long_ago_unsettled,
    get_event_odds_history,
)
from app.utils.kalshi_occurrence_start import (
    KALSHI_EXPECTED_EXPIRATION_PAD,
    KALSHI_RECOVERY_STAMP,
)

from tests.test_history_window_stale_open_event import (
    _DispatchingSession,
    _snapshot,
)

UTC = timezone.utc

#: Port FC v Kobe as production held it at 15:30:30Z on 2026-09-16. The stored
#: column is the market's expected expiration, three hours after the whistle.
SPECIMEN_ID = 15307696


def _kalshi_minted_row(now, *, sport_key="soccer_afc_champions_league", **over):
    """The specimen, shaped into a row this recovery should move.

    Four fields carry the whole population and each one is a refusal if it is
    wrong, so all four are set explicitly rather than left to the namespace:

    * `external_id=None`   — no schedule provider reported this start, so the
      hour is ours to correct. A set `external_id` is the anchored case, which
      refuses.
    * `commence_time_source="kalshi"` — in `KALSHI_OCCURRENCE_TIMED_SOURCES`.
      `None` (the bare-namespace default) refuses.
    * `sport.key` a real `str` — `loaded_sport_key` returns `None` for anything
      that is not a string, and `None` refuses.
    * the stamp `False` — set explicitly for the reason #5905's rig sets it:
      a truthy stamp reads as "already recovered" and the recovery returns
      having done nothing, silently.

    `SimpleNamespace` rather than `MagicMock` deliberately. A mock auto-creates
    every attribute truthily, so `external_id` would be set (refuses) and the
    stamp would be truthy (refuses) — a rig on which NOTHING is ever corrected
    and every assertion here is vacuous.
    """
    event = SimpleNamespace(
        id=SPECIMEN_ID,
        status="live",
        commence_time=now - timedelta(minutes=15),  # the stored expiration
        completed_at=None,
        home_team_name="Port FC",
        away_team_name="Kobe",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key=sport_key),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.00525}},
        external_id=None,
        commence_time_source="kalshi",
    )
    setattr(event, KALSHI_RECOVERY_STAMP, False)
    for key, value in over.items():
        setattr(event, key, value)
    return event


async def _history(event, rows=(), hours=48):
    """Drive the real `/api/events/{id}/history` handler over one seeded row."""
    session = _DispatchingSession(event, list(rows))
    payload = await get_event_odds_history(
        event_id=event.id, hours=hours, response=MagicMock(headers={}), db=session
    )
    return payload, session


def _served_commence(payload):
    raw = payload.get("commence_time")
    assert raw, f"the history payload carried no commence_time: {payload!r}"
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))


# ── the rig can see a correction at all (strawman; see the docstring) ────────


async def test_the_rig_itself_can_see_a_correction():
    """If this fails, every refusal test below is meaningless.

    A refusal test passes against a route that never calls the recovery, so the
    suite needs one assertion that is false unless a correction is observable
    through this exact rig.
    """
    now = datetime.now(UTC)
    event = _kalshi_minted_row(now)
    stored = event.commence_time

    payload, _ = await _history(event)

    assert _served_commence(payload) != stored, (
        "the rig observed no correction at all — the refusal tests in this "
        "module are vacuous until this passes"
    )


# ── the ship ────────────────────────────────────────────────────────────────


async def test_the_history_route_serves_the_kickoff_not_the_expected_expiration():
    now = datetime.now(UTC)
    event = _kalshi_minted_row(now)
    expiration = event.commence_time

    payload, _ = await _history(event)

    assert _served_commence(payload) == expiration - KALSHI_EXPECTED_EXPIRATION_PAD, (
        "the chart served the stored expected-expiration hour; this is the "
        "#6568 defect, where /api/events/15307696 said 12:15Z and "
        "/api/events/15307696/history said 15:15Z for the same game"
    )


async def test_the_correction_is_exactly_the_measured_pad_not_a_rounding():
    now = datetime.now(UTC)
    event = _kalshi_minted_row(now)
    expiration = event.commence_time

    payload, _ = await _history(event)

    assert expiration - _served_commence(payload) == KALSHI_EXPECTED_EXPIRATION_PAD


async def test_the_page_and_its_chart_serve_one_kickoff():
    """The acceptance criterion: one `commence_time` per event id per page load.

    The detail route reaches the correction through the same helper, so folding
    a matching row and serving this one must land on the same instant. If these
    diverge the reader is back to a kick-off that changes depending on which
    half of the page they read.
    """
    from app.utils.kalshi_occurrence_start import recover_kalshi_occurrence_starts

    now = datetime.now(UTC)
    as_the_page_sees_it = _kalshi_minted_row(now)
    recover_kalshi_occurrence_starts([as_the_page_sees_it])

    payload, _ = await _history(_kalshi_minted_row(now))

    assert as_the_page_sees_it.commence_time == _served_commence(payload)


# ── 🔴 the state half: it is not the label ──────────────────────────────────


async def test_the_corrected_clock_reaches_the_window_not_only_the_label():
    """The corrected hour must reach the consumers that reason about STATE.

    On the specimen the stored hour is three hours late, so at 15:30Z the route
    read a match that had kicked off at 12:15Z — and been graded by the venue at
    14:16Z — as fifteen minutes old: freshly started, and windowed accordingly.
    The correction moves it to the far side of the requested window, where
    `_event_started_long_ago_unsettled` serves the series whole.

    `hours=2` is chosen so the two clocks fall on OPPOSITE sides of one bound:
    stored = 15 minutes ago (inside), corrected = 3h15m ago (outside). A test
    where both readings landed on the same side would assert nothing about the
    correction reaching this predicate.
    """
    now = datetime.now(UTC)
    event = _kalshi_minted_row(now)
    stored = event.commence_time

    assert _event_started_long_ago_unsettled(
        SimpleNamespace(commence_time=stored), now, hours=2
    ) is False, "the stored clock must read as freshly-started, or this proves nothing"

    payload, _ = await _history(event, hours=2)

    assert _event_started_long_ago_unsettled(event, now, hours=2) is True, (
        "the corrected kick-off never reached the row the windowing consumers "
        "read — the served label was fixed and the state was not"
    )
    assert _served_commence(payload) == stored - KALSHI_EXPECTED_EXPIRATION_PAD


# ── the refusals: rows this route must NOT move ─────────────────────────────


async def test_an_anchored_row_is_never_moved_by_the_history_route():
    """A start a schedule provider reported is not ours to shift."""
    now = datetime.now(UTC)
    event = _kalshi_minted_row(now, external_id="odds-api-abc123")
    stored = event.commence_time

    payload, _ = await _history(event)

    assert _served_commence(payload) == stored


async def test_a_basketball_row_is_never_moved_by_the_history_route():
    """Outside soccer the pad is a spread, not a constant (gotcha #14).

    Measured in the module's own census: MMA returns 255/265/275/285/295/345
    minutes and boxing ~14 days, against soccer's 180 in eleven of eleven rows.
    """
    now = datetime.now(UTC)
    event = _kalshi_minted_row(now, sport_key="basketball_nba")
    stored = event.commence_time

    payload, _ = await _history(event)

    assert _served_commence(payload) == stored


async def test_a_row_whose_time_came_from_a_schedule_is_never_moved():
    now = datetime.now(UTC)
    event = _kalshi_minted_row(now, commence_time_source="odds_api")
    stored = event.commence_time

    payload, _ = await _history(event)

    assert _served_commence(payload) == stored


async def test_a_ticker_midnight_is_never_moved_by_the_history_route():
    """`kalshi_ticker` resolves to midnight UTC — a stand-in, not this instant."""
    now = datetime.now(UTC)
    event = _kalshi_minted_row(now, commence_time_source="kalshi_ticker")
    stored = event.commence_time

    payload, _ = await _history(event)

    assert _served_commence(payload) == stored


# ── idempotence, which is load-bearing rather than tidy ─────────────────────


async def test_two_reads_of_the_same_row_do_not_stack_two_pads():
    """Two requests must not advertise a kick-off SIX hours early.

    authority/179 measured the ladder this guards against on a route that folds
    twice in one request: 21:45 → 18:45 → 15:45 → 12:45. The stamp is what stops
    it, and a caller above this one may start folding the row at any time.
    """
    now = datetime.now(UTC)
    event = _kalshi_minted_row(now)
    stored = event.commence_time

    first, _ = await _history(event)
    second, _ = await _history(event)

    assert _served_commence(first) == _served_commence(second) == (
        stored - KALSHI_EXPECTED_EXPIRATION_PAD
    )


async def test_the_series_still_draws_while_the_clock_is_corrected():
    """A control: correcting the hour must not cost the chart its points.

    The correction sits above the series queries, so a mistake there (an
    exception escaping, a row left unusable) would empty the chart — which
    `suppressWinProbabilityCard` turns into a page with no card at all. The
    #6568 ship is worthless if it buys the right hour and an empty graph.
    """
    now = datetime.now(UTC)
    event = _kalshi_minted_row(now)
    rows = [
        _snapshot(now - timedelta(hours=3) + timedelta(minutes=10 * step), 0.5)
        for step in range(6)
    ]
    for row in rows:
        row.event_id = SPECIMEN_ID

    payload, _ = await _history(event, rows, hours=48)

    assert payload["win_prob_history"].get("kalshi"), (
        "the chart lost its series while the clock was being corrected"
    )
