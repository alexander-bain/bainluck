"""#6863 — the chart's live edge is withheld where the hero serves no price.

THE SPECIMEN, photographed on production at 390px (`artifacts-live-528/
LOOK-15316643-live-390.png`, read 2026-09-23 07:28Z against `9b6542ef4f`):

    /events/15316643 — Gibson v Anisimova, tennis, status `live`.

    hero   ● LIVE        "No price"        (win_probability_sources {} -> null)
    chart  a flat Polymarket line to the right edge, readout
           "Gibson 49% - Anisimova 51%" stamped 12:27 AM,
           over a caption that reads
           "Polymarket last reading 9:26 PM - none in the 3h 1m since".

The last STORED snapshot was 04:26:04Z. The last SERVED point was 07:28:25Z —
the wall-clock instant of the request, confirmed twice a minute apart. The
route's own `_extend_win_prob_history_to_live_edge` (#920) was planting a
synthetic "now" point carrying a three-hour-stale 0.495, and the chart drew to
it. One screen, two answers, and only the channel that DECLINED carried a
marker.

WHY THESE ARE ROUTE-LEVEL AND NOT UNIT TESTS. The unit guards in
`test_event_history_live_edge.py` pin the predicate, and they pass just as
happily when the CALL SITE hands it `None` — which fails open by design for
folded events and would serve the defect unchanged on every event. A gate is
only wired if the served payload changes, so these drive the real
`get_event_odds_history` and assert on what a reader is sent. Measured: with
the predicate correct and the call site passing `None`, arm one below fails and
every unit guard stays green.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.routes.events import get_event_odds_history

# The harness is the one the other executed-route chart tests already drive, so
# a change to the route's query shape breaks one place rather than two.
from tests.test_history_end_cap_hides_every_point import _DispatchingSession

UTC = timezone.utc

#: Offsets, never absolute instants — the anchor must not branch on the clock
#: (gotcha #44). `NOW` is read inside each test so a slow suite cannot drift.
_STALE_BY = timedelta(hours=3)
_SERIES_SPAN = timedelta(hours=2)

_SPECIMEN_ID = 15316643


def _snapshot(when, home_prob, source="polymarket"):
    return SimpleNamespace(
        event_id=_SPECIMEN_ID,
        captured_at=when,
        source=source,
        home_win_probability=home_prob,
        away_win_probability=round(1.0 - home_prob, 4),
        draw_probability=None,
        game_state=None,
    )


def _live_event(sources):
    """The specimen: in progress, and `sources` is what the hero rests on."""
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=_SPECIMEN_ID,
        status="live",
        commence_time=now - timedelta(hours=5, minutes=28),
        completed_at=None,
        home_team_name="Gibson",
        away_team_name="Anisimova",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key="tennis_wta"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources=sources,
    )


def _stale_series(now):
    """Real observations that stop three hours before now, as the specimen's did."""
    last = now - _STALE_BY
    first = last - _SERIES_SPAN
    return [
        _snapshot(first, 0.495),
        _snapshot(first + _SERIES_SPAN / 2, 0.495),
        _snapshot(last, 0.495),
    ]


async def _serve(event, rows):
    session = _DispatchingSession(event, rows)
    return await get_event_odds_history(
        event_id=event.id, hours=720, response=MagicMock(headers={}), db=session
    )


def _points(payload, source="polymarket"):
    return (payload.get("win_prob_history") or {}).get(source) or []


# ---------------------------------------------------------------------------
# The defect
# ---------------------------------------------------------------------------


async def test_a_page_that_serves_no_price_serves_no_now_point():
    """THE SHIP. Hero has nothing, so the chart asserts nothing at `now`."""
    now = datetime.now(UTC)
    event = _live_event({})  # the specimen's bag, empty

    payload = await _serve(event, _stale_series(now))
    points = _points(payload)

    assert points, "the real observations must still be served"
    assert not any(p.get("live_edge") for p in points), (
        "a page serving `No price` planted a now-point anyway"
    )
    # The right edge is the last REAL reading, which is what the page's own
    # caption already told the reader.
    last_ts = datetime.fromisoformat(points[-1]["timestamp"])
    assert (now - last_ts) >= _STALE_BY - timedelta(minutes=1)


async def test_the_real_observations_are_kept_not_deleted():
    """This withholds an assertion; it must not delete traded history (#5898)."""
    now = datetime.now(UTC)
    payload = await _serve(_live_event({}), _stale_series(now))

    served = [p["home_probability"] for p in _points(payload)]
    assert served == [0.495, 0.495, 0.495]


async def test_a_bag_holding_no_tier_one_reading_counts_as_no_price():
    """`{"betting_book_count": 1}` is a NON-EMPTY bag with nothing in it.

    Measured on production: of the live/suspended events carrying a non-empty
    bag, several hold only `betting_book_count`, which is not in
    `SOURCE_WEIGHTS`. A gate keyed on "is the bag empty?" rather than on the
    hero's own reading set would extend the line on every one of them.
    """
    now = datetime.now(UTC)
    payload = await _serve(_live_event({"betting_book_count": 1}), _stale_series(now))

    assert not any(p.get("live_edge") for p in _points(payload))


async def test_a_reading_the_eligibility_gate_refused_gets_no_edge():
    """CU-4 (#5311), which is the whole reason this asks the HERO's function.

    `_tier1_readings` is, in its own docstring, "the ONE place that decides
    which stored readings reach the hero, the chart edge, the divergence gate
    and the Discover card, so a refusal applied here cannot be applied
    inconsistently across surfaces". A positively-refused Polymarket reading is
    in the bag and is NOT in that set — so a gate keyed on the bag's raw keys
    would carry the line forward on exactly the readings a rule already said no
    to. Measured: with the call site reading `win_probability_sources.keys()`
    instead of `effective_source_weights`, this test and the next one fail and
    the other 19 stay green.
    """
    now = datetime.now(UTC)
    event = _live_event(
        {
            "polymarket": {
                "value": 0.495,
                "updated_at": (now - _STALE_BY).isoformat(),
                "eligibility": {"v": 1, "status": "ineligible"},
            }
        }
    )

    payload = await _serve(event, _stale_series(now))

    assert not any(p.get("live_edge") for p in _points(payload))


async def test_a_bag_entry_carrying_no_usable_value_gets_no_edge():
    """Present in the bag, absent from the hero — the column holds both shapes."""
    now = datetime.now(UTC)
    event = _live_event(
        {"polymarket": {"updated_at": (now - _STALE_BY).isoformat()}}  # no `value`
    )

    payload = await _serve(event, _stale_series(now))

    assert not any(p.get("live_edge") for p in _points(payload))


# ---------------------------------------------------------------------------
# The controls — #920 must still work, or this ship is a regression
# ---------------------------------------------------------------------------


async def test_a_priced_live_game_still_tracks_the_clock():
    """#920's own case, and the proof this gate is not simply switched off.

    Measured on the live population 2026-09-23 07:33Z: 59 live events with
    snapshots, 55 of them carry the chart's source in the hero's bag and are
    served exactly as before.
    """
    now = datetime.now(UTC)
    event = _live_event(
        {"polymarket": {"value": 0.495, "updated_at": (now - _STALE_BY).isoformat()}}
    )

    payload = await _serve(event, _stale_series(now))
    points = _points(payload)

    edges = [p for p in points if p.get("live_edge")]
    assert len(edges) == 1, "a source the hero counts must still reach the live clock"
    assert edges[0]["home_probability"] == 0.495


async def test_only_the_unspoken_source_loses_its_edge():
    """The discriminating payload: one source counted, one not, same request."""
    now = datetime.now(UTC)
    event = _live_event(
        {"kalshi": {"value": 0.61, "updated_at": (now - _STALE_BY).isoformat()}}
    )
    rows = _stale_series(now) + [
        _snapshot(now - _STALE_BY, 0.61, source="kalshi"),
    ]

    payload = await _serve(event, rows)

    assert any(p.get("live_edge") for p in _points(payload, "kalshi"))
    assert not any(p.get("live_edge") for p in _points(payload, "polymarket"))


async def test_a_finished_event_is_untouched_by_this_gate():
    """Settled means settled — the completed journey is not this gate's business."""
    now = datetime.now(UTC)
    event = _live_event({})
    event.status = "completed"
    event.completed_at = now - timedelta(minutes=30)

    payload = await _serve(event, _stale_series(now))

    assert not any(p.get("live_edge") for p in _points(payload))
    assert len(_points(payload)) == 3


@pytest.mark.parametrize("sources", [{}, {"betting_book_count": 1}])
async def test_the_withholding_does_not_empty_the_chart(sources):
    """A reader still gets the line — this is one point fewer, not a blank card."""
    now = datetime.now(UTC)
    payload = await _serve(_live_event(sources), _stale_series(now))

    assert len(_points(payload)) == 3
