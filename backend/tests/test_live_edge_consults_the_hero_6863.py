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

from app.routes import events
from app.routes.events import get_event_odds_history
from app.utils.aggregation import make_price_read

# The harness is the one the other executed-route chart tests already drive, so
# a change to the route's query shape breaks one place rather than two.
from tests.test_history_end_cap_hides_every_point import _DispatchingSession, _Result
from tests.test_series_fold_3810 import (
    blend_fold_row,
    fold_row,
    is_blend_fold,
    is_series_fold,
)

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


class _FoldedHistorySession(_DispatchingSession):
    def __init__(self, event, twin, rows):
        super().__init__(event, rows)
        self.events = [event, twin] if twin is not None else [event]
        self.blend_reads = 0

    async def execute(self, statement, *args, **kwargs):
        sql = str(statement)
        if is_blend_fold(sql):
            self.blend_reads += 1
            return _Result(
                [
                    (*blend_fold_row(row), revision, row is not self.event)
                    for row, revision in zip(self.events, (5, 8))
                ]
            )
        if is_series_fold(sql):
            return _Result([fold_row(row) for row in self.events])
        return await super().execute(statement, *args, **kwargs)


def _opening_snapshot(now):
    return _snapshot(now - timedelta(hours=3), 0.495)


def _fresh_opening_chance(now):
    observed_at = now - timedelta(seconds=70)
    reading = _snapshot(observed_at, 0.495)
    return reading, {"polymarket": {
        "value": 0.495,
        "updated_at": observed_at.isoformat(),
        "price_read": make_price_read(0.495, observed_at),
    }}


async def _serve_opening_history(now, rows, *, sources=None, folded=True, chart_range="all"):
    event = _live_event({} if folded else sources or {})
    event.commence_time = now - timedelta(minutes=15)
    event.opening_home_probability = 0.495
    twin = SimpleNamespace(
        id=event.id + 1,
        home_team_name=event.home_team_name,
        away_team_name=event.away_team_name,
        win_probability_sources=sources or {},
    )
    for snapshot in rows:
        snapshot.event_id = twin.id if folded else event.id
    session = _FoldedHistorySession(event, twin if folded else None, rows)
    payload = await get_event_odds_history(
        event_id=event.id,
        hours=48,
        chart_range=chart_range,
        response=MagicMock(headers={}),
        db=session,
    )
    return payload, session.blend_reads


async def test_a_folded_live_game_never_promotes_its_only_stored_pregame_quote():
    now = datetime.now(UTC)
    opening = _opening_snapshot(now)
    payload, reads = await _serve_opening_history(now, [opening])
    assert payload["status"] == "live"
    assert not payload["blend_edge_pinned"]
    assert not any(p.get("live_edge") for p in _points(payload)), _points(payload)
    # The source may be omitted as undrawable with one point. If it draws,
    # its only permissible timestamp is the original historical quote.
    assert all(p["timestamp"] == opening.captured_at.isoformat() for p in _points(payload))
    assert reads == 1


async def test_silent_fold_keeps_both_real_pregame_points_on_all():
    now = datetime.now(UTC)
    rows = [_opening_snapshot(now), _snapshot(now - timedelta(hours=2), 0.51)]
    payload, _ = await _serve_opening_history(now, rows)
    assert [(p["timestamp"], p["home_probability"]) for p in _points(payload)] == [
        (row.captured_at.isoformat(), row.home_win_probability) for row in rows
    ]


@pytest.mark.parametrize("new_chart_row", [False, True])
async def test_a_fresh_folded_twin_can_keep_the_same_numeric_chance_at_the_live_edge(new_chart_row):
    now = datetime.now(UTC)
    current, sources = _fresh_opening_chance(now)
    rows = [_opening_snapshot(now)]
    if new_chart_row:
        rows.append(current)
    payload, reads = await _serve_opening_history(now, rows, sources=sources)
    points = _points(payload)
    stored = [p for p in points if not p.get("live_edge")]
    assert [p["timestamp"] for p in stored] == [r.captured_at.isoformat() for r in rows]
    assert [p["home_probability"] for p in stored] == [0.495] * len(rows)
    edges = [p for p in points if p.get("live_edge")]
    assert len(edges) == 1
    assert edges[0]["home_probability"] == 0.495
    assert edges[0]["evidence"] == {"kind": "live_edge"}
    assert abs(datetime.fromisoformat(edges[0]["timestamp"]) - now) < timedelta(seconds=5)
    assert reads == (0 if new_chart_row else 1)


@pytest.mark.parametrize("old_or_missing_read", [False, True], ids=["undated", "pregame-only"])
async def test_a_recent_write_cannot_promote_a_pregame_tail_without_a_live_price_read(old_or_missing_read):
    now = datetime.now(UTC)
    opening = _opening_snapshot(now)
    _, sources = _fresh_opening_chance(now)
    sources["polymarket"]["price_read"] = (
        make_price_read(0.495, opening.captured_at) if old_or_missing_read else None
    )
    payload, reads = await _serve_opening_history(now, [opening], sources=sources)
    assert not any(point.get("live_edge") for point in _points(payload))
    assert reads == 1


@pytest.mark.parametrize("cached_hero", [False, True])
async def test_folded_venue_admission_and_the_blend_pin_share_one_fold_read(monkeypatch, cached_hero):
    now = datetime.now(UTC)
    current, sources = _fresh_opening_chance(now)
    observed_at = current.captured_at.isoformat()
    cached = {
        "hero_probability_source": "blend",
        "hero_probability": 0.495,
        "hero_probability_observed_at": observed_at,
        "blend_fold_revision": {str(_SPECIMEN_ID): 3, str(_SPECIMEN_ID + 1): 4},
    }
    monkeypatch.setattr(events, "_cached_detail_payload", lambda *_: cached if cached_hero else None)
    rows = [
        _opening_snapshot(now),
        _snapshot(now - timedelta(hours=3), 0.56, source="kalshi"),
        _snapshot(now - timedelta(hours=2), 0.59, source="kalshi"),
        current,
    ]
    payload, reads = await _serve_opening_history(now, rows, sources=sources)

    assert reads == 1
    assert payload["blend_edge_pinned"]
    assert payload["blend_edge_observed_at"] == observed_at
    assert payload["blend_edge_fold_revision"] == (
        cached["blend_fold_revision"] if cached_hero else {str(_SPECIMEN_ID): 5, str(_SPECIMEN_ID + 1): 8}
    )
    assert _points(payload, "polymarket")[-1]["live_edge"]
    assert not any(p.get("live_edge") for p in _points(payload, "kalshi"))


@pytest.mark.parametrize("folded, include_snapshots", [(False, True), (True, False)])
async def test_no_new_fold_read_without_a_live_folded_source_series(folded, include_snapshots):
    now = datetime.now(UTC)
    rows = [_opening_snapshot(now), _snapshot(now - timedelta(hours=2), 0.51)] if include_snapshots else []
    payload, reads = await _serve_opening_history(now, rows, folded=folded)
    assert reads == 0
    assert [p["timestamp"] for p in _points(payload)] == [r.captured_at.isoformat() for r in rows]
