"""#4974 reader slice 1: ``GET /api/events/{event_id}/publications`` route contract.

The route is mounted on a small app with a fake session, so no database is
needed; the resolver and fold helpers are replaced at the names this route
imports. The one SQL read is checked by compiling it for Postgres. The last
class binds the path to the production route table without making a request.

Named mutants (boundary section A, ``4974-UX-READER-SLICE-1-BOUNDARY.md``):
skip the fold check; drop the cap; read past three columns; order by
``recorded_at``; add a body key; read the requested id instead of the served one.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.models.models import ProbabilityPublication
from app.routes import event_publications as route
from app.services.database import get_db

T0 = datetime(2026, 10, 4, 23, 0, 0, tzinfo=timezone.utc)
PATH = "/api/events/{event_id}/publications"


class _Result:
    def __init__(self, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return list(self._rows)


class _FakeSession:
    """Answers the event load by primary key and the publications read."""

    def __init__(self, events, rows_by_event):
        self.events = events
        self.rows_by_event = rows_by_event
        self.publication_reads = []

    async def execute(self, statement):
        froms = {getattr(f, "name", None) for f in statement.get_final_froms()}
        if "probability_publications" in froms:
            self.publication_reads.append(statement)
            event_id = statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            ).string.split("probability_publications.event_id = ")[1].split()[0]
            return _Result(rows=self.rows_by_event.get(int(event_id), []))
        assert froms == {"events"}, froms
        event_id = statement.whereclause.right.value
        return _Result(scalar=self.events.get(event_id))


def _event(event_id):
    return SimpleNamespace(id=event_id, event_tags=None, sport=None)


@pytest.fixture
def rig(monkeypatch):
    state = SimpleNamespace(
        events={1: _event(1), 2: _event(2)},
        rows_by_event={},
        resolve_to={},
        fold_ids={},
        fold_calls=[],
    )

    async def resolve_served_event(db, event, *, requested_id):
        target = state.resolve_to.get(requested_id, requested_id)
        return SimpleNamespace(event=state.events[target], event_id=target)

    async def serve_fold_absorbed_rows(db, event):
        return []

    async def folded_series_event_ids(db, event_id, absorbed=()):
        state.fold_calls.append(event_id)
        return state.fold_ids.get(event_id, [event_id])

    monkeypatch.setattr(route, "resolve_served_event", resolve_served_event)
    monkeypatch.setattr(route, "serve_fold_absorbed_rows", serve_fold_absorbed_rows)
    monkeypatch.setattr(route, "folded_series_event_ids", folded_series_event_ids)

    app = FastAPI()
    app.include_router(route.router, prefix="/api/events")
    state.session = _FakeSession(state.events, state.rows_by_event)

    async def _db():
        yield state.session

    app.dependency_overrides[get_db] = _db
    state.client = TestClient(app)
    return state


def _rows(n):
    return [(i + 1, T0 + timedelta(seconds=i), 0.5) for i in range(n)]


class TestTheServedBody:
    def test_empty_table_serves_no_vertices(self, rig):
        resp = rig.client.get("/api/events/1/publications")
        assert resp.status_code == 200
        assert resp.json() == {
            "event_id": 1,
            "schema_version": 1,
            "time_basis": "recorded_at_insert_before_commit",
            "truncated": False,
            "vertices": [],
        }

    def test_stored_rows_are_served_as_vertices_by_rev_with_nulls_omitted(self, rig):
        rig.rows_by_event[1] = [
            (4, T0 + timedelta(seconds=40), 0.55),
            (5, T0 + timedelta(seconds=20), None),
            (6, T0 + timedelta(seconds=10), 0.61),
        ]
        body = rig.client.get("/api/events/1/publications").json()
        assert body["vertices"] == [
            {"rev": 4, "t": "2026-10-04T23:00:40+00:00", "p": 0.55},
            {"rev": 6, "t": "2026-10-04T23:00:10+00:00", "p": 0.61},
        ]

    def test_body_keys_are_exactly_the_contract(self, rig):
        rig.rows_by_event[1] = _rows(2)
        body = rig.client.get("/api/events/1/publications").json()
        assert set(body) == {"event_id", "schema_version", "time_basis", "truncated", "vertices"}
        assert all(set(v) == {"rev", "t", "p"} for v in body["vertices"])

    def test_cache_control_is_public_sixty_seconds(self, rig):
        resp = rig.client.get("/api/events/1/publications")
        assert resp.headers["cache-control"] == "public, max-age=60"

    def test_missing_event_is_404(self, rig):
        assert rig.client.get("/api/events/999/publications").status_code == 404
        assert rig.session.publication_reads == []

    def test_more_than_5000_rows_serves_nothing_truncated(self, rig):
        rig.rows_by_event[1] = _rows(5001)
        body = rig.client.get("/api/events/1/publications").json()
        assert body["truncated"] is True
        assert body["vertices"] == []


class TestTheServedRow:
    def test_a_duplicate_reads_the_row_it_was_resolved_to(self, rig):
        # Mutant: read the requested id ⇒ the ghost's (empty) rows are served.
        rig.resolve_to[2] = 1
        rig.rows_by_event[1] = _rows(2)
        body = rig.client.get("/api/events/2/publications").json()
        assert body["event_id"] == 1
        assert [v["rev"] for v in body["vertices"]] == [1, 2]
        assert rig.fold_calls == [1]

    def test_fold_contributor_present_serves_nothing_and_reads_nothing(self, rig):
        # Mutant: skip the fold check ⇒ the canonical's own checkpoints are served.
        rig.rows_by_event[1] = _rows(3)
        rig.fold_ids[1] = [1, 2]
        body = rig.client.get("/api/events/1/publications").json()
        assert body["vertices"] == []
        assert body["truncated"] is False
        assert rig.session.publication_reads == []

    def test_an_unfolded_row_reads_once(self, rig):
        rig.rows_by_event[1] = _rows(1)
        rig.client.get("/api/events/1/publications")
        assert len(rig.session.publication_reads) == 1


class TestTheOneRead:
    @staticmethod
    def _sql(event_id=1):
        return route.publications_statement(event_id).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        ).string

    def test_selects_exactly_rev_recorded_at_blend_probability(self):
        statement = route.publications_statement(1)
        assert [c.key for c in statement.selected_columns] == [
            "rev",
            "recorded_at",
            "blend_probability",
        ]

    def test_never_names_the_columns_slice_1_must_not_read(self):
        sql = self._sql()
        for column in ProbabilityPublication.__table__.columns.keys():
            if column in {"event_id", "rev", "recorded_at", "blend_probability"}:
                continue
            assert f"probability_publications.{column}" not in sql, column

    def test_one_event_ordered_by_rev_limited_one_past_the_cap(self):
        sql = " ".join(self._sql(15300001).split())
        assert "WHERE probability_publications.event_id = 15300001" in sql
        assert sql.endswith("ORDER BY probability_publications.rev LIMIT 5001")


class TestTheProductionRouteTable:
    def test_the_path_reaches_this_handler_first(self):
        # Mounted after `events.router` on the same prefix; nothing earlier in
        # the table may claim the path.
        from app.main import app

        for candidate in app.routes:
            if not isinstance(candidate, APIRoute) or "GET" not in candidate.methods:
                continue
            if candidate.path_regex.match("/api/events/123/publications"):
                assert candidate.endpoint is route.get_event_publications
                assert candidate.path == PATH
                break
        else:
            pytest.fail(f"{PATH} is not mounted")

    def test_get_only(self):
        from app.main import app

        methods = set()
        for candidate in app.routes:
            if isinstance(candidate, APIRoute) and candidate.path == PATH:
                methods |= candidate.methods
        assert methods == {"GET"}
