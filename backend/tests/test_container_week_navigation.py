"""Source fixtures for the fresh optional route; no served/production acceptance."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routes import containers
from app.services import get_db
from app.services.container_discovery import _COLUMNS
from app.utils.container_week_navigation import MAX_EDITIONS, select_navigation


def row(slug, **changes):
    data = dict(
        id=1,
        name="Fixture",
        slug=slug,
        status="scheduled",
        window_start=None,
        window_end=None,
        parent_container_id=None,
        publication_state="published",
        revision=4,
        game_count=1,
        question_count=0,
        matched_event_ids=[],
    )
    return {**data, **changes}


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0]


class Session:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def execute(self, sql, params=None):
        self.calls.append((str(sql), params))
        if "to_regclass" in str(sql):
            return Result([(True, True)])
        return Result([tuple(r[k] for k in _COLUMNS) for r in self.rows])


def route_client(monkeypatch, session):
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    app = FastAPI()
    app.include_router(containers.router, prefix="/api/containers")
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app)


def test_route_fresh_complete_range_and_publication_changes(monkeypatch):
    current = "nfl-2026-week-4"
    session = Session([row(current), row("nfl-2026-week-6")])
    with route_client(monkeypatch, session) as client:

        def read():
            return client.get(f"/api/containers/{current}/week-navigation")

        first = read()
        assert first.headers["cache-control"] == "no-store"
        assert (
            first.json()["next"]["destination"]["web"] == "/collections/nfl-2026-week-6"
        )
        assert "Week 6" in first.json()["next"]["label"]  # gap explicit, never Week5
        session.rows.append(row("nfl-2026-week-5"))
        assert read().json()["next"]["slug"] == "nfl-2026-week-5"
        session.rows[-1]["publication_state"] = "withdrawn"
        assert read().json()["next"]["slug"] == "nfl-2026-week-6"
        session.rows[0]["publication_state"] = "withdrawn"
        assert read().json()["state"] == "unavailable"
    query, params = session.calls[1]
    assert len(params["slugs"]) == MAX_EDITIONS == 297
    assert params["limit"] == MAX_EDITIONS + 1
    assert "c.slug = ANY(:slugs)" in query
    assert "parent_container_id IS NULL" in query
    assert "COUNT(DISTINCT ev.id) + COUNT(DISTINCT fm.id) > 0" in query
    assert len(session.calls) == 8  # schema + one aggregate per fresh read


def test_stage_order_season_isolation_and_unseen_week():
    current = "nfl-2026-week-1"
    rows = [
        row(current),
        row("nfl-2026-preseason-week-4"),
        row("nfl-2026-postseason-week-1"),
        row("nfl-2027-week-1"),
    ]
    answer = select_navigation(current, rows)
    assert answer["previous"]["slug"] == "nfl-2026-preseason-week-4"
    assert answer["next"]["slug"] == "nfl-2026-postseason-week-1"
    rows.append(row("nfl-2026-week-2"))
    assert select_navigation(current, rows)["next"]["slug"] == "nfl-2026-week-2"


@pytest.mark.parametrize(
    "bad",
    [
        row("nfl-2026-week-5", publication_state="unpublished"),
        row("nfl-2026-week-5", publication_state="withdrawn"),
        row("nfl-2026-week-5", parent_container_id=20),
        row("nfl-2026-week-5", game_count=0),
        row("nfl-2026-week-05"),
        row("nfl-2026-week-0"),
        row("nfl-2026-week-100"),
        row("mlb-2026-postseason"),
        row("nfl-2025-week-5"),
    ],
)
def test_ineligible_destination_never_linked(bad):
    current = "nfl-2026-week-4"
    answer = select_navigation(current, [row(current), bad])
    assert answer == {
        "slug": current,
        "state": "available",
        "previous": None,
        "next": None,
    }


def test_ambiguous_and_truncated_refuse_not_false_absence():
    current = "nfl-2026-week-4"
    for rows in (
        [row(current), row(current, id=2)],
        [row(current)] * (MAX_EDITIONS + 1),
        [],
    ):
        assert select_navigation(current, rows)["state"] == "unavailable"


def test_route_failure_does_not_become_known_empty(monkeypatch):
    class Failed(Session):
        async def execute(self, *args):
            raise RuntimeError("fixture read failure")

    with route_client(monkeypatch, Failed([])) as client:
        assert (
            client.get("/api/containers/nfl-2026-week-4/week-navigation").json()[
                "state"
            ]
            == "unavailable"
        )
        assert (
            client.get("/api/containers/ai/week-navigation").json()["state"]
            == "not_applicable"
        )
        monkeypatch.setenv("CONTAINERS_READ_ENABLED", "false")
        assert (
            client.get("/api/containers/nfl-2026-week-4/week-navigation").status_code
            == 404
        )


def test_navigation_route_has_bounded_timeout(monkeypatch):
    import asyncio
    from app.utils import container_week_navigation

    async def stalled(*args):
        await asyncio.sleep(30)

    monkeypatch.setattr(container_week_navigation, "read_week_navigation", stalled)
    with route_client(monkeypatch, Session([])) as client:
        assert (
            client.get("/api/containers/nfl-2026-week-4/week-navigation").json()[
                "state"
            ]
            == "unavailable"
        )
