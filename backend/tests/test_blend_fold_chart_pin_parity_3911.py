"""#3911 repair — `HERO-BLEND-FOLD-CHART-PIN-PARITY-3911`.

Fold A (#3810 acceptance 1) made the hero read the twin rows we decline to
print. `_pin_blend_edge` did not move with it, and that is a two-number
user-visible regression rather than a missing improvement:

    canonical  polymarket 0.60          hero  = weighted median(0.60, 0.40) = 0.40
    twin       kalshi     0.40          edge  = compute_aggregate_probability(raw
                                                canonical) = 0.60

Both are rendered at the same minute on the same screen — the big number says
40% and the curve under it ends at 60%. That is exactly #3898's shape, rebuilt
by the fix for its sibling, and it is why the repair is a parity guard across
BOTH routes rather than another assertion inside `get_event`.

🔴 THE MUTANT THIS FILE EXISTS FOR: pass the raw `event` to `_pin_blend_edge`
instead of the folded view and `test_the_chart_edge_and_the_hero_are_one_number`
fails. The submitted #3911 guards all passed on that mutant (91/91 on the
composed tree), because every one of them read a single route.

CLOCK: every timestamp here is derived from `datetime.now(timezone.utc)` at
import, never from a calendar literal. The pre-match arm of the pin only fires
while the newest bucket is younger than `_PREMATCH_EDGE_MAX_AGE` (2 minutes), so
a frozen anchor would not fail this file — it would make it PASS vacuously the
moment the pin stopped firing, which is #3895 (`EXPIRING-TEST-ANCHORS`) with the
sign flipped. `test_the_fixture_anchor_tracks_the_real_clock` pins that.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.models import Event, Sport
from app.routes.events import get_event, get_event_odds_history
from app.utils.aggregation import compute_aggregate_probability

from tests.test_series_fold_3810 import is_blend_fold, is_series_fold


# The production pair #3810 was filed on.
CANON_ID = 15305016
GHOST_ID = 15304989
S_TENNIS = 77

#: Tracks the real clock — see the module docstring. Truncated to the minute
#: because the pin buckets at 60s and compares parsed datetimes, so a fixture
#: carrying microseconds would sit a hair PAST the bucket it means to be in.
NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)

#: The two readings from the BLOCK, one per row. Equal stamps on purpose: the
#: aggregator's staleness decay is measured against the freshest stamp on the
#: event, so a fixture whose sources are minutes apart would be testing decay
#: rather than the fold.
CANON_PROB = 0.60
TWIN_PROB = 0.40
#: What the two blend to, and therefore what BOTH surfaces must say. Named, not
#: inlined, so the assertions read as "one number" instead of a repeated 0.4.
BLENDED = 0.40


def _sources(**readings):
    return {
        key: {"value": value, "updated_at": NOW.isoformat()}
        for key, value in readings.items()
    }


def _event_row():
    """SCHEDULED, and starting soon.

    Not `completed`: `_EXCLUDE_WHEN_COMPLETED` drops kalshi and polymarket from
    the blend once a game is over, so a settled fixture would agree with itself
    with the repair deleted. Not `live` either — the live arm of the pin APPENDS
    a point, which would hide a wrong value at the end of the line behind a new
    one. Pre-match OVERWRITES the last bucket, which is the sharpest place to
    read the disagreement.
    """
    event = Event(
        id=CANON_ID,
        sport_id=S_TENNIS,
        home_team_name="Ben Shelton",
        away_team_name="Stefanos Tsitsipas",
        commence_time=NOW + timedelta(hours=1),
        status="scheduled",
        win_probability_sources=_sources(polymarket=CANON_PROB),
    )
    event.sport = Sport(id=S_TENNIS, key="tennis_atp_us_open", name="US Open")
    return event


#: The twin as each fold's own projection returns it, oriented in agreement —
#: what production holds for all 12 pairs (measured 2026-09-07).
def _blend_fold_rows():
    return [(GHOST_ID, "Shelton", "Tsitsipas", _sources(kalshi=TWIN_PROB))]


def _series_fold_rows():
    return [
        (CANON_ID, "Ben Shelton", "Stefanos Tsitsipas"),
        (GHOST_ID, "Shelton", "Tsitsipas"),
    ]


def _snap(event_id, source, minutes_ago, home_prob):
    return SimpleNamespace(
        event_id=event_id,
        source=source,
        captured_at=NOW - timedelta(minutes=minutes_ago),
        home_win_probability=home_prob,
        away_win_probability=round(1.0 - home_prob, 4),
        draw_probability=None,
        game_state=None,
    )


def _snapshots():
    """Two sources, because `aggregate_line` is only computed for >1.

    The newest bucket is `NOW` itself, so the pre-match arm of the pin fires on
    the last point rather than declining as a genuinely-past edge.
    """
    return [
        _snap(CANON_ID, "polymarket", 2, CANON_PROB),
        _snap(CANON_ID, "polymarket", 0, CANON_PROB),
        _snap(GHOST_ID, "kalshi", 2, TWIN_PROB),
        _snap(GHOST_ID, "kalshi", 0, TWIN_PROB),
    ]


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _RouteSession:
    """One fake session that answers BOTH routes.

    The two folds' projections are adjacent — `folded_probability_sources`
    selects `id, home_team_name, away_team_name, win_probability_sources`, which
    STARTS WITH `folded_series_event_ids`' projection — so a rig that asked
    `is_series_fold` first handed the blend fold three-tuples and
    `merge_probability_sources` unpacked a row of the wrong width. That was a
    prediction in `test_blend_fold_3810` until this repair drove both folds down
    one route and made it four red tests. `is_series_fold` is now EXCLUSIVE of
    the blend projection, so the two arms below are order-independent; they are
    still written longest-first, because a rig that reads correctly is worth
    more than one that merely runs correctly.
    """

    def __init__(self, event):
        self.event = event
        self.blend_fold_lookups = 0
        self.series_fold_lookups = 0

    async def execute(self, statement, *_a, **_kw):
        sql = " ".join(str(statement).split())

        if "FROM win_prob_snapshots" in sql:
            rows = _snapshots()
            if "min(" in sql:
                return _Result([min(s.captured_at for s in rows)])
            return _Result(sorted(rows, key=lambda s: s.captured_at))
        if "FROM odds_snapshots" in sql:
            return _Result([])
        if is_blend_fold(sql):  # longer projection first — see the docstring
            self.blend_fold_lookups += 1
            return _Result(_blend_fold_rows())
        if is_series_fold(sql):
            self.series_fold_lookups += 1
            return _Result(_series_fold_rows())
        if "FROM events" in sql:
            return _Result([self.event])
        return _Result([])


@pytest.fixture()
def both_routes(monkeypatch):
    """Serve the detail page and its chart off one event, as a reader gets them."""
    from app.routes import events as events_route

    async def _no_percentiles(_db):
        return {}

    async def _no_teams(_db, _names):
        return {}

    async def _no_drain(_db, _event_id):
        return None

    monkeypatch.setattr(events_route, "_load_gei_percentiles", _no_percentiles)
    monkeypatch.setattr(events_route, "_build_team_lookup", _no_teams)
    monkeypatch.setattr(events_route, "resolve_market_born_duplicate", _no_drain)

    def _serve():
        events_route._event_detail_cache.clear()
        detail_session = _RouteSession(_event_row())
        history_session = _RouteSession(_event_row())
        detail = asyncio.run(get_event(CANON_ID, db=detail_session))
        history = asyncio.run(
            get_event_odds_history(
                event_id=CANON_ID,
                hours=720,
                response=MagicMock(headers={}),
                db=history_session,
            )
        )
        return detail, history, history_session

    return _serve


def _edge(history):
    line = history.get("aggregate_line")
    assert line, "no blend line to pin — the fixture, not the ship, is broken"
    return line[-1]["home_probability"]


class TestTheTwoRoutesAgree:
    def test_the_chart_edge_and_the_hero_are_one_number(self, both_routes):
        """🔴 THE REPAIR. Standing ruling #1 across the route PAIR.

        Reverting `_pin_blend_edge`'s second argument to the raw `event` fails
        here and nowhere else in the #3911 suite.
        """
        detail, history, _ = both_routes()

        assert detail["hero_probability"] == pytest.approx(BLENDED)
        assert _edge(history) == pytest.approx(BLENDED)
        assert detail["hero_probability"] == pytest.approx(_edge(history))

    def test_the_unfolded_edge_would_have_been_the_canonicals_own_reading(self):
        """The negative control, computed rather than asserted from memory.

        Without this repair the pin's input is the raw row, whose only reading
        is polymarket — so the edge lands on 0.60 against a 0.40 hero. Pinning
        the number here means a future change to the aggregator that made the
        two coincide could not make the test above pass for the wrong reason.
        """
        raw = compute_aggregate_probability(_event_row(), event_status="scheduled")

        assert raw == pytest.approx(CANON_PROB)
        assert raw != pytest.approx(BLENDED)

    def test_the_history_route_issued_the_blend_fold_lookup(self, both_routes):
        """The wiring, not only its effect.

        The effect above could in principle be produced by a chart that never
        folded but happened to blend to the same number; this cannot.
        """
        _, _, history_session = both_routes()

        assert history_session.blend_fold_lookups == 1
        assert history_session.series_fold_lookups >= 1

    def test_a_chart_with_no_blend_line_pays_no_lookup(self, monkeypatch):
        """The cost side of the repair, stated as a test.

        `_pin_blend_edge` returns on the first line for an empty
        `aggregate_line`, so a single-source chart — the common case — must not
        buy a fold it cannot use.
        """
        from app.routes import events as events_route

        class _OneSourceSession(_RouteSession):
            async def execute(self, statement, *_a, **_kw):
                sql = " ".join(str(statement).split())
                if "FROM win_prob_snapshots" in sql:
                    rows = [s for s in _snapshots() if s.source == "polymarket"]
                    if "min(" in sql:
                        return _Result([min(s.captured_at for s in rows)])
                    return _Result(sorted(rows, key=lambda s: s.captured_at))
                return await super().execute(statement, *_a, **_kw)

        session = _OneSourceSession(_event_row())
        history = asyncio.run(
            get_event_odds_history(
                event_id=CANON_ID,
                hours=720,
                response=MagicMock(headers={}),
                db=session,
            )
        )

        assert history.get("aggregate_line") is None
        assert session.blend_fold_lookups == 0
        assert events_route is not None  # import kept honest


class TestTheFixtureCannotExpire:
    def test_the_fixture_anchor_tracks_the_real_clock(self):
        """#3895 with the sign flipped: a frozen anchor here passes VACUOUSLY.

        The pre-match pin stands down once the newest bucket is older than
        `_PREMATCH_EDGE_MAX_AGE`, so a calendar literal would eventually stop
        the pin firing at all — and a test asserting two numbers agree when
        neither is pinned agrees for the wrong reason, silently, forever.
        """
        from app.routes.events import _PREMATCH_EDGE_MAX_AGE

        age = datetime.now(timezone.utc) - NOW
        assert age < _PREMATCH_EDGE_MAX_AGE, (
            "NOW must be derived from the wall clock at import (gotcha #44); "
            f"it is {age} old, past the {_PREMATCH_EDGE_MAX_AGE} pin window"
        )
