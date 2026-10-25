"""Explicit stream reconciliation rereads advance a primed cached fold.

The ordinary routes still share cached hero/value/revision. A fresh pair must
read canonical and twin revisions together and honor source removal.
"""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import events as events_route
from app.routes.events import get_event, get_event_odds_history
from app.services.database import get_db
from tests.test_blend_fold_chart_pin_parity_3911 import CANON_ID, GHOST_ID, _Result, _now
from tests.test_fold_revision_9051 import _RevisionedSession, _vector, both_routes as _revision_routes
from tests.test_series_fold_3810 import is_blend_fold


@pytest.fixture
def routes(monkeypatch):
    rig = _revision_routes.__wrapped__(monkeypatch)
    rig.cache.clear()
    yield rig
    rig.cache.clear()


def _frozen_clock(at):
    """`events.datetime` with `now()` pinned, so two serves read the same instant.

    The metaclass derives from `type(datetime)` so it composes with
    `scripts/clock_sweep.py`, which installs a `datetime` of its own metaclass.
    """

    class _AcceptsRealDatetimes(type(datetime)):
        def __instancecheck__(cls, obj):
            return isinstance(obj, datetime)

    class _Frozen(datetime, metaclass=_AcceptsRealDatetimes):
        @classmethod
        def now(cls, tz=None):
            return at if tz is None else at.astimezone(tz)

    return _Frozen


def detail(session, *, fresh=False):
    return asyncio.run(get_event(CANON_ID, db=session, fresh=fresh))


def history(session, *, fresh=False):
    return asyncio.run(get_event_odds_history(
        CANON_ID, hours=720, response=MagicMock(headers={}), db=session, fresh=fresh,
    ))


def prime(now):
    old = detail(_RevisionedSession(now, canon_rev=4, twin_rev=9, canon=0.6, twin=0.4))
    assert old["hero_probability"] == pytest.approx(0.5)
    assert old["blend_fold_revision"] == _vector(4, 9)
    return old


def test_fresh_detail_advances_and_populates_the_ordinary_cache(routes):
    now = _now()
    old = prime(now)
    current = _RevisionedSession(now, canon_rev=5, twin_rev=10, canon=0.2, twin=0.1)
    assert detail(current) is old
    assert current.blend_fold_lookups == 0
    updated = detail(current, fresh=True)
    assert current.blend_fold_lookups == 1
    assert updated["hero_probability"] == pytest.approx(0.15)
    assert updated["blend_fold_revision"] == _vector(5, 10)
    assert detail(current) is updated
    assert current.blend_fold_lookups == 1


def test_fresh_history_bypasses_another_workers_cached_hero_without_rewriting_it(routes, monkeypatch):
    now = _now()
    # #11570: ONE route clock for both reads. The live edge carries each series
    # to the minute the route reads, so two reads either side of a minute
    # boundary differ by a carried bucket and the prefix equality below fails
    # for a reason that is not this test's (CI 40046287955, shard 5).
    # Mid-minute, where a real read stands, not on either edge of it.
    monkeypatch.setattr(events_route, "datetime", _frozen_clock(now + timedelta(seconds=30)))
    old = prime(now)
    current = _RevisionedSession(now, canon_rev=5, twin_rev=10, canon=0.2, twin=0.1)
    ordinary = history(current)
    assert ordinary["blend_edge_pinned"] is True
    assert ordinary["aggregate_line"][-1]["home_probability"] == pytest.approx(0.5)
    assert ordinary["blend_edge_fold_revision"] == _vector(4, 9)
    assert current.blend_fold_lookups == 0
    fresh = history(current, fresh=True)
    assert fresh["aggregate_line"][-1]["home_probability"] == pytest.approx(0.15)
    assert fresh["blend_edge_fold_revision"] == _vector(5, 10)
    # #10090: the coverage prefix (read before any history) and the pin's own
    # read (beside its value) are two statements; neither borrows the other.
    assert current.blend_fold_lookups == 2
    # Called outside the cached route there are no build marks, so nobody
    # could have recorded a swallowed read: completeness unknown, no claim.
    assert fresh["history_fold_revision"] is None
    assert routes.cache[CANON_ID][2] is old
    assert fresh["aggregate_line"][:-1] == ordinary["aggregate_line"][:-1]


def test_a_minute_boundary_between_the_two_reads_is_what_grew_the_fresh_line(routes, monkeypatch):
    """#11570's control: the clock alone, not the bypass, made the prefixes differ.

    This is the interleaving CI hit, forced; the test above now pins one clock.
    Everything it grades holds; the fresh line has exactly one more point, the
    series carried to the later minute.
    """
    now = _now()
    monkeypatch.setattr(events_route, "datetime", _frozen_clock(now + timedelta(seconds=59.9)))
    old = prime(now)
    current = _RevisionedSession(now, canon_rev=5, twin_rev=10, canon=0.2, twin=0.1)
    ordinary = history(current)
    monkeypatch.setattr(events_route, "datetime", _frozen_clock(now + timedelta(seconds=60.1)))
    fresh = history(current, fresh=True)
    assert ordinary["aggregate_line"][-1]["home_probability"] == pytest.approx(0.5)
    assert ordinary["blend_edge_fold_revision"] == _vector(4, 9)
    assert fresh["aggregate_line"][-1]["home_probability"] == pytest.approx(0.15)
    assert fresh["blend_edge_fold_revision"] == _vector(5, 10)
    assert current.blend_fold_lookups == 2
    assert routes.cache[CANON_ID][2] is old
    *shared, carried = fresh["aggregate_line"][:-1]
    assert shared == ordinary["aggregate_line"][:-1]
    assert carried == {
        **ordinary["aggregate_line"][-2],
        "timestamp": (now + timedelta(minutes=1)).isoformat(),
    }


class RemovedSourceSession(_RevisionedSession):
    async def execute(self, statement, *args, **kwargs):
        result = await super().execute(statement, *args, **kwargs)
        if is_blend_fold(" ".join(str(statement).split())):
            return _Result([
                (*row[:3], {}, *row[4:]) if row[0] == GHOST_ID else row
                for row in result.all()
            ])
        return result


def test_source_removal_and_readmission_advance_the_pair_before_cache_expiry(routes):
    now = _now()
    old = prime(now)
    removed = RemovedSourceSession(now, canon_rev=4, twin_rev=10, canon=0.6, twin=0.4)
    fresh_history = history(removed, fresh=True)
    assert routes.cache[CANON_ID][2] is old
    fresh_detail = detail(removed, fresh=True)
    assert fresh_detail["hero_probability"] == pytest.approx(0.6)
    assert fresh_history["aggregate_line"][-1]["home_probability"] == pytest.approx(0.6)
    assert fresh_detail["blend_fold_revision"] == _vector(4, 10)
    assert fresh_history["blend_edge_fold_revision"] == _vector(4, 10)
    admitted = _RevisionedSession(now, canon_rev=4, twin_rev=11, canon=0.6, twin=0.2)
    returned = detail(admitted, fresh=True)
    assert returned["hero_probability"] == pytest.approx(0.4)
    assert returned["blend_fold_revision"] == _vector(4, 11)


@pytest.mark.parametrize("path,is_history", [
    (f"/events/{CANON_ID}", False),
    (f"/events/{CANON_ID}/history?hours=720", True),
])
def test_http_fresh_query_is_explicit_and_false_preserves_cache(routes, path, is_history):
    now = _now()
    prime(now)
    current = _RevisionedSession(now, canon_rev=5, twin_rev=10, canon=0.2, twin=0.1)
    app = FastAPI()
    app.get("/events/{event_id}")(get_event)
    app.get("/events/{event_id}/history")(get_event_odds_history)
    app.dependency_overrides[get_db] = lambda: current
    sep = "&" if "?" in path else "?"
    with TestClient(app) as client:
        cached = client.get(path + sep + "fresh=false")
        assert cached.status_code == 200
        assert current.blend_fold_lookups == 0
        advanced = client.get(path + sep + "fresh=true")
    assert advanced.status_code == 200
    # History's fresh build also reads the #10090 coverage prefix.
    assert current.blend_fold_lookups == (2 if is_history else 1)
    payload = advanced.json()
    key = "blend_edge_fold_revision" if is_history else "blend_fold_revision"
    assert payload[key] == _vector(5, 10)
    value = payload["aggregate_line"][-1]["home_probability"] if is_history else payload["hero_probability"]
    assert value == pytest.approx(0.15)
