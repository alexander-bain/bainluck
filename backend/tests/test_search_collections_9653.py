"""#9653 — a /search page offers the published hub its own games belong to.

SHIP: a reader who searches a club and sees this week's NFL game (or a
postseason MLB game) can open the same NFL-week / MLB-postseason hub Discover
and Browse open. Pillar: DISCOVER / MATCHING.

What is pinned here, against ``app.utils.search_collections`` and the two exits
of ``GET /api/events/search``:

* **off means byte-identical** — either switch off: no statement, and the
  route returns the very body it would have returned before #9653;
* **relevance, not a slot** — the only evidence is this page's
  ``results[].id``, and a page with no games reads nothing;
* **the producer's card, verbatim, at most two** — the native Search consumer
  decodes the #9653 handoff card, so this surface must not reshape it;
* **live authority** — the cache never holds a card, and a hub withdrawn after
  the body was cached is gone from the next serve;
* **bounded and fail-open** — a failed or overrun read serves the ordinary
  answer and restores the session.

The producer's SQL is graded on real Postgres in
``tests/integration/test_container_discovery_real_postgres.py``; this file
grades the consumer.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.utils import search_collections as sc

FIXTURE = (
    Path(__file__).parent / "fixtures" / "container_discovery_9653" / "search_by_games.json"
)
WINDOW_START = datetime(2026, 10, 1, 17, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 10, 8, 17, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _Session:
    """Answers the producer's schema probe and aggregate read, nothing else."""

    def __init__(self, rows=(), *, fail=False, delay=0.0):
        self.rows = list(rows)
        self.fail = fail
        self.delay = delay
        self.statements: list[str] = []
        self.params: list = []
        self.rollbacks = 0

    async def execute(self, sql, params=None):
        text_ = str(sql)
        self.statements.append(text_)
        self.params.append(params)
        if "to_regclass('public.container_corrections')" in text_:
            return _Result([(True, True)])
        if text_.startswith("WITH hub AS"):
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.fail:
                raise RuntimeError("statement failed")
            return _Result(self.rows)
        raise AssertionError(f"unexpected statement: {text_[:120]}")

    async def rollback(self):
        self.rollbacks += 1


def _row(slug="nfl-2026-week-5", *, id=70, name="NFL 2026 · Week 5", matched=(501, 502)):
    """One row of the producer's aggregate read, in ``_COLUMNS`` order."""
    return (
        id, name, slug, "live", WINDOW_START, WINDOW_END,
        None, "published", 4, 4, 1, list(matched),
    )


def _payload(ids=(501, 502, 503)):
    return {
        "query": "chiefs",
        "teams": [{"name": "Kansas City Chiefs"}],
        "event_concepts": [],
        "results": [{"id": i, "home_team": "A", "away_team": "B"} for i in ids],
        "futures": [{"id": 9, "name": "Super Bowl"}],
        "futures_families": [],
        "pagination": {"page": 1, "per_page": 25, "total_results": len(ids)},
        "sports": [],
        "filters": {"sport": None, "days_back": 30, "include_upcoming": True},
    }


@pytest.fixture
def switches_on(monkeypatch):
    monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")


# ---------------------------------------------------------------------------
# Off means byte-identical
# ---------------------------------------------------------------------------


class TestOffMeansUnchanged:
    @pytest.mark.parametrize(
        "discovery_on, hub_on", [("false", "true"), ("true", "false"), ("false", "false")]
    )
    async def test_either_switch_off_reads_nothing_and_returns_the_same_body(
        self, monkeypatch, discovery_on, hub_on
    ):
        monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", discovery_on)
        monkeypatch.setenv("CONTAINERS_READ_ENABLED", hub_on)
        session = _Session([_row()])
        body = _payload()
        before = copy.deepcopy(body)

        out = await sc.attach_search_collections(session, body)

        assert out is body and out == before
        assert "collections" not in out
        assert session.statements == []

    async def test_default_environment_is_off(self, monkeypatch):
        monkeypatch.delenv("CONTAINER_DISCOVERY_ENABLED", raising=False)
        monkeypatch.delenv("CONTAINERS_READ_ENABLED", raising=False)
        assert sc.search_collections_enabled() is False


# ---------------------------------------------------------------------------
# Relevance, not a slot
# ---------------------------------------------------------------------------


class TestRelevance:
    async def test_the_page_s_own_games_are_the_only_evidence(self, switches_on):
        session = _Session([_row()])
        await sc.attach_search_collections(session, _payload(ids=(503, 501, 502)))
        read_params = session.params[-1]
        assert read_params["event_ids"] == [501, 502, 503]
        assert read_params["limit"] == sc.SEARCH_COLLECTIONS_CAP

    async def test_a_page_with_no_games_reads_nothing(self, switches_on):
        session = _Session([_row()])
        body = _payload(ids=())
        out = await sc.attach_search_collections(session, body)
        assert out is body and "collections" not in out
        assert session.statements == []

    async def test_malformed_result_rows_are_skipped_not_fatal(self, switches_on):
        session = _Session([_row()])
        body = _payload(ids=(501,))
        body["results"] += [{"home_team": "no id"}, "not a dict", {"id": None}, {"id": "x"}]
        await sc.attach_search_collections(session, body)
        assert session.params[-1]["event_ids"] == [501]

    async def test_no_eligible_hub_leaves_the_body_untouched(self, switches_on):
        session = _Session([])
        body = _payload()
        out = await sc.attach_search_collections(session, body)
        assert out is body and "collections" not in out


# ---------------------------------------------------------------------------
# The producer's card, verbatim, at most two
# ---------------------------------------------------------------------------


class TestProducerCard:
    async def test_the_card_is_the_handoff_fixture_byte_for_byte(self, switches_on):
        """The native Search consumer builds against ``search_by_games.json``."""
        banked = json.loads(FIXTURE.read_text())["response"]["collections"]
        out = await sc.attach_search_collections(_Session([_row()]), _payload())
        assert json.loads(json.dumps(out["collections"])) == banked

    async def test_nothing_else_in_the_payload_moves(self, switches_on):
        body = _payload()
        before = copy.deepcopy(body)
        out = await sc.attach_search_collections(_Session([_row()]), body)
        assert {k: v for k, v in out.items() if k != "collections"} == before
        assert body == before, "the caller's (possibly already-cached) body was mutated"

    async def test_at_most_two_cards_most_matched_first(self, switches_on):
        rows = [
            _row("nfl-2026-week-5", id=70, matched=(501, 502, 503)),
            _row("nfl-2026-week-4", id=69, name="NFL 2026 · Week 4", matched=(501, 502)),
            _row("mlb-2026-postseason", id=71, name="MLB 2026 Postseason", matched=(501,)),
        ]
        out = await sc.attach_search_collections(_Session(rows), _payload())
        assert [c["slug"] for c in out["collections"]] == ["nfl-2026-week-5", "nfl-2026-week-4"]

    async def test_an_ineligible_row_is_refused_by_the_producer_not_reshaped_here(
        self, switches_on
    ):
        withdrawn = list(_row())
        withdrawn[7] = "withdrawn"
        out = await sc.attach_search_collections(_Session([tuple(withdrawn)]), _payload())
        assert "collections" not in out


# ---------------------------------------------------------------------------
# Bounded and fail-open
# ---------------------------------------------------------------------------


class TestFailOpen:
    async def test_a_failed_read_serves_the_ordinary_answer_and_restores_the_session(
        self, switches_on
    ):
        session = _Session([_row()], fail=True)
        body = _payload()
        out = await sc.attach_search_collections(session, body)
        assert out is body and "collections" not in out
        assert session.rollbacks == 1

    async def test_an_overrun_read_is_cut_at_the_budget(self, switches_on):
        session = _Session([_row()], delay=5.0)
        body = _payload()
        loop = asyncio.get_running_loop()
        started = loop.time()
        out = await sc.attach_search_collections(session, body, budget_seconds=0.05)
        assert loop.time() - started < 1.0
        assert out is body and session.rollbacks == 1

    async def test_the_budget_can_only_shrink_never_grow(self, switches_on):
        session = _Session([_row()], delay=5.0)
        loop = asyncio.get_running_loop()
        started = loop.time()
        await sc.attach_search_collections(session, _payload(), budget_seconds=60)
        assert loop.time() - started < sc.SEARCH_COLLECTION_READ_BUDGET_SECONDS + 1.0


# ---------------------------------------------------------------------------
# The route: live authority across the response cache
# ---------------------------------------------------------------------------


class _FakeRedis:
    def __init__(self):
        self.strings: dict[str, str] = {}

    def get(self, key):
        v = self.strings.get(key)
        return v.encode() if isinstance(v, str) else v

    def setex(self, key, ttl, value):
        self.strings[key] = value
        return True


@pytest.fixture
def rc(monkeypatch):
    client = _FakeRedis()
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: client)
    monkeypatch.setattr("app.routes.events._record_search_query", lambda *a, **k: None)
    return client


def _warm(rc, body, q="chiefs"):
    from app.utils.search_cache import search_response_cache_key

    key = search_response_cache_key(
        q=q, sport=None, tags=None, page=1, per_page=25, days_back=30, include_upcoming=True
    )
    rc.strings[key] = json.dumps(body)
    return key


async def _search(db, q="chiefs"):
    """Every parameter explicit: FastAPI's ``Query(...)`` defaults are truthy here."""
    from fastapi import Response
    from starlette.requests import Request

    from app.routes.events import search_events

    request = Request(
        {"type": "http", "method": "GET", "path": "/api/events/search",
         "headers": [], "query_string": b""}
    )
    return await search_events(
        request=request, response=Response(), q=q, sport=None, tags=None, page=1,
        per_page=25, days_back=30, include_upcoming=True, debug_timing=False,
        db=db, current_user=None,
    )


class TestRouteCacheHitExit:
    async def test_flags_off_serves_the_cached_body_exactly(self, rc, monkeypatch):
        monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "false")
        body = _payload()
        _warm(rc, body)
        # `db=None`: any statement at all would raise.
        assert await _search(None) == body

    async def test_flags_on_adds_the_hub_and_the_cache_never_holds_it(
        self, rc, switches_on
    ):
        body = _payload()
        key = _warm(rc, body)
        out = await _search(_Session([_row()]))
        assert [c["slug"] for c in out["collections"]] == ["nfl-2026-week-5"]
        assert "collections" not in json.loads(rc.strings[key])

    async def test_a_hub_withdrawn_after_caching_is_gone_from_the_next_serve(
        self, rc, switches_on
    ):
        body = _payload()
        _warm(rc, body)
        first = await _search(_Session([_row()]))
        assert first["collections"]
        withdrawn = list(_row())
        withdrawn[7] = "withdrawn"
        second = await _search(_Session([tuple(withdrawn)]))
        assert second == body


class TestRouteBuildExit:
    """The build exit is ~3,600 lines of SQL stages, so its ORDER is pinned on
    source: the attach must follow the cache write (else the cache would hold a
    card and a withdrawal would survive the TTL), and the warmer must skip it."""

    def _source(self):
        from app.routes.events import search_events

        return inspect.getsource(search_events)

    def test_both_exits_attach(self):
        src = self._source()
        assert src.count("attach_search_collections(db, _hit)") == 1
        assert src.count("attach_search_collections(db, _payload)") == 1

    def test_the_build_exit_attaches_after_the_cache_write(self):
        src = self._source()
        write = src.index("_get_rc().setex(")
        attach = src.index("attach_search_collections(db, _payload)")
        assert write < attach

    def test_the_warmer_rebuild_skips_the_read(self):
        src = self._source()
        attach = src.index("attach_search_collections(db, _payload)")
        guard = src.rindex("if _force_search_cache_rebuild.get():", 0, attach)
        assert src[guard:attach].count("return _payload") == 1
