"""#9051 — detail, history and the frame each serve the revision vector of the read they report.

The ship: a removed source stops influencing the held headline and chart, and
valid survivor quotes and re-admissions still land. ux's 0558Z contract makes
the client compare ``{row_id: rev}`` vectors instead of clocks; these are the
producer-side guarantees it relies on, without a server:

* detail's ``blend_fold_revision`` names every row the fold read, and is cached
  in the same entry as the hero;
* history's ``blend_edge_fold_revision`` comes from the SAME read as the pinned
  value: the cached hero's vector when the cache serves the edge, the fresh
  fold's vector when the route computes it, and never one with the other;
* a legacy cache entry or a row with no revision makes no claim (``None``),
  never "revision zero".

The trigger, commit order and the migration are graded on real Postgres in
``tests/integration/test_fold_revision_9051_pg.py``.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.utils.live_push import build_frame
from app.utils.wps_revision import (
    CREATE_TRIGGER_SQL,
    fold_revision_vector,
)
from tests.test_blend_fold_chart_pin_parity_3911 import (
    CANON_ID,
    GHOST_ID,
    _Result,
    _RouteSession,
    _now,
    both_routes as _shared_both_routes,
)
from tests.test_series_fold_3810 import is_blend_fold


@pytest.fixture
def both_routes(monkeypatch):
    return _shared_both_routes.__wrapped__(monkeypatch)


@pytest.fixture(autouse=True)
def _clean_cache(both_routes):
    both_routes.cache.clear()
    yield
    both_routes.cache.clear()


class _RevisionedSession(_RouteSession):
    """The shared route rig, answering the fold with production's five columns."""

    def __init__(self, now, *, canon_rev, twin_rev, canon=None, twin=None):
        super().__init__(now, canon=canon, twin=twin)
        self.event.status = "live"
        self.event.commence_time = now - timedelta(hours=1)
        self.event.win_probability_sources_rev = canon_rev
        self.twin_rev = twin_rev

    async def execute(self, statement, *a, **kw):
        sql = " ".join(str(statement).split())
        if is_blend_fold(sql):
            assert "events.win_probability_sources_rev" in sql, sql
            self.blend_fold_lookups += 1
            # Production's one-snapshot answer: the canonical AND its twin.
            return _Result(
                [
                    (
                        CANON_ID,
                        self.event.home_team_name,
                        self.event.away_team_name,
                        self.event.win_probability_sources,
                        self.event.win_probability_sources_rev,
                        False,
                    ),
                    (
                        GHOST_ID,
                        "Shelton",
                        "Tsitsipas",
                        {
                            "kalshi": {
                                "value": self.twin,
                                "updated_at": self.now.isoformat(),
                            }
                        },
                        self.twin_rev,
                        True,
                    ),
                ]
            )
        return await super().execute(statement, *a, **kw)


def _vector(canon_rev, twin_rev):
    return {str(CANON_ID): canon_rev, str(GHOST_ID): twin_rev}


class TestDetail:
    def test_the_hero_is_served_with_every_folded_rows_revision(self, both_routes):
        now = _now()
        detail = both_routes.detail(
            _RevisionedSession(now, canon_rev=4, twin_rev=9, canon=0.6, twin=0.4)
        )
        assert detail["hero_probability"] == pytest.approx(0.5)
        assert detail["blend_fold_revision"] == _vector(4, 9)
        _cached_at, _status, payload = both_routes.cache[CANON_ID]
        assert payload["blend_fold_revision"] == _vector(4, 9)
        assert payload["hero_probability"] == detail["hero_probability"]

    def test_a_row_with_no_revision_makes_no_claim(self, both_routes):
        now = _now()
        detail = both_routes.detail(
            _RevisionedSession(now, canon_rev=None, twin_rev=9)
        )
        assert detail["blend_fold_revision"] is None


class TestHistory:
    def test_a_cached_edge_carries_the_cached_heros_vector(self, both_routes):
        now = _now()
        detail = both_routes.detail(
            _RevisionedSession(now, canon_rev=4, twin_rev=9, canon=0.6, twin=0.4)
        )
        # The row has moved on since the detail read; the edge still shows the
        # cached hero, so its vector must be the cached one.
        session = _RevisionedSession(
            now, canon_rev=5, twin_rev=10, canon=0.2, twin=0.1
        )
        history = both_routes.history(session)
        assert history["blend_edge_pinned"] is True
        assert history["aggregate_line"][-1]["home_probability"] == pytest.approx(
            detail["hero_probability"]
        )
        assert history["blend_edge_fold_revision"] == _vector(4, 9)
        assert session.blend_fold_lookups == 0

    def test_a_fresh_edge_carries_the_fresh_folds_vector(self, both_routes):
        now = _now()
        both_routes.detail(
            _RevisionedSession(now, canon_rev=4, twin_rev=9, canon=0.6, twin=0.4)
        )
        cached_at, status, payload = both_routes.cache[CANON_ID]
        both_routes.cache[CANON_ID] = (cached_at - 60, status, payload)
        session = _RevisionedSession(
            now, canon_rev=5, twin_rev=10, canon=0.2, twin=0.1
        )
        history = both_routes.history(session)
        assert history["aggregate_line"][-1]["home_probability"] == pytest.approx(
            0.15
        )
        assert history["blend_edge_fold_revision"] == _vector(5, 10)
        assert session.blend_fold_lookups == 1

    def test_a_legacy_cache_entry_cannot_borrow_the_fresh_rows_vector(
        self, both_routes
    ):
        now = _now()
        detail = both_routes.detail(
            _RevisionedSession(now, canon_rev=4, twin_rev=9, canon=0.6, twin=0.4)
        )
        detail.pop("blend_fold_revision")
        history = both_routes.history(
            _RevisionedSession(now, canon_rev=5, twin_rev=10)
        )
        assert history["blend_edge_pinned"] is True
        assert history["aggregate_line"][-1]["home_probability"] == pytest.approx(
            0.5
        )
        assert history["blend_edge_fold_revision"] is None

    def test_no_pin_serves_no_vector(self, both_routes):
        now = _now()
        session = _RevisionedSession(now, canon_rev=4, twin_rev=9)
        session.event.status = "completed"
        session.event.completed_at = now - timedelta(minutes=1)
        session.event.home_score, session.event.away_score = 2, 0
        history = both_routes.history(session)
        assert history["blend_edge_pinned"] is False
        assert history["blend_edge_fold_revision"] is None


class TestTheVectorAndTheFrame:
    def test_all_or_nothing(self):
        assert fold_revision_vector(1, 3, [(2, 0)]) == {"1": 3, "2": 0}
        assert fold_revision_vector(1, 3, []) == {"1": 3}
        assert fold_revision_vector(1, 3, [(2, None)]) is None
        assert fold_revision_vector(1, None, [(2, 5)]) is None
        # bool is an int subclass; a True must not read as revision 1.
        assert fold_revision_vector(1, True, []) is None
        assert fold_revision_vector(None, 3, []) is None

    def test_the_frame_names_its_own_row(self):
        frame = build_frame(
            event_id=15, probability=0.5, source="kalshi", source_value=0.5,
            updated_at="2026-09-27T06:00:00+00:00", status="live", rev=12,
        )
        assert frame["rev"] == {"15": 12}
        for rev in (None, True, "12"):
            unclaimed = build_frame(
                event_id=15, probability=0.5, source="kalshi", source_value=0.5,
                updated_at="2026-09-27T06:00:00+00:00", status="live", rev=rev,
            )
            assert unclaimed["rev"] is None

    def test_the_trigger_fires_on_any_update_that_changes_the_bag(self):
        # `UPDATE OF win_probability_sources` would fire only when the column is
        # named in the SET list; the WHEN clause is what decides.
        flat = " ".join(CREATE_TRIGGER_SQL.split())
        assert "BEFORE UPDATE ON events FOR EACH ROW" in flat
        assert " OF " not in flat
        assert (
            "WHEN (OLD.win_probability_sources IS DISTINCT FROM "
            "NEW.win_probability_sources)" in flat
        )
