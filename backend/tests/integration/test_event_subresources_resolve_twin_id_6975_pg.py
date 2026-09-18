"""#6975 — the original game link opens the WHOLE game, not a hero over emptiness.

WHAT A READER SAW
=================

`bainluck://events/15310639` (Liverpool 0–0 Fulham, completed Sep 12) drew a
page whose hero was RIGHT and whose whole body was EMPTY: "No win probability
readings for this game", "No prediction markets for this game", and two
Championship Path cards both titled `FC`. The canonical id `15297677` drew the
populated page. Measured on production 2026-09-18 (issue #6975):

    GET /api/events/15310639                  -> id 15297677 (resolved)
    GET /api/events/15310639/game-markets     -> event_id 15310639, 0 markets
    GET /api/events/15310639/team-progression -> "Liverpool FC" / short_name "FC"

The detail route canonicalised the id; its three sub-resources did not. The app
rendered every payload faithfully — each empty state was the honest rendering
of an empty payload — which is exactly why the page read as truthful and was
not.

WHY THIS NEEDS A DATABASE
=========================

The fix is one identity decision (`resolve_served_event`, the detail route's
own two arms lifted out) applied to three more routes, and the thing that
proves it is that the ROW the query filters, the fold, the cache keys and the
returned identity all follow. A mocked session hands every query the same
stub row, so a route that resolved the id and then read the wrong table would
still "pass"; only a server can answer "which row's markets came back". So
this gate seeds a known twin and its canonical with DISTINCT values — different
club spellings, markets only on the canonical, series points only on the
canonical — and asks the real route handlers over a real session. The wrong
row cannot pass by accident.

THE CONTROLS
============

* Direct canonical requests are unchanged: their bodies are byte-equal to what
  the twin id now serves (minus the cache envelope's timestamps), which is also
  the proof that market folding and history calculation are the SAME
  computation — the twin id runs the canonical's build, it does not run a new
  one.
* A clean, untagged event serves itself, with its own distinct values.
* Absent id → 404 on all three; a tag naming a vanished row, a self-naming tag,
  a malformed tag and a two-node cycle each serve the row asked for (one hop,
  never chased) — the detail route's existing refusals, pinned so the
  extraction cannot have loosened them.
* Retirement: a `merged` row that names its successor serves the successor on
  every surface; a `voided` row that names nothing keeps today's behaviour —
  the detail route's 410, and the sub-resources' own content.

THE CACHE
=========

`/game-markets` is a two-tier cache (L1 dict, L2 Redis primary + mirror) keyed
by the id the caller asked for; `/team-progression` is a five-minute Redis slot
keyed the same way. Both are exercised cold AND warm with a fake Redis:

* a slot written under the twin id BEFORE this shipped holds the twin's empty
  book. For game-markets it carries the release that built it and `gmc.read`
  refuses a slot from another build (#6355) — the test sets the running build
  and stamps the stale slot with a different one, which is what production
  looks like on the deploy that carries this. For team-progression there is no
  build stamp, so the namespace is versioned and the old key is simply never
  read.
* after one build, a second reader of the twin id (a different process — L1
  cleared) is served from Redis with the CANONICAL content and no rebuild; a
  reader of the canonical id is served from the slot the twin's build filled.

RUN
===

    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://... python -m pytest \\
        tests/integration/test_event_subresources_resolve_twin_id_6975_pg.py -v

CI's `search-recall` job names this file; without the URL every test skips,
and a skipped gate reads exactly like a passing one — so it is named there.
"""

from __future__ import annotations

import datetime as dt
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6975 twin-id "
        "sub-resource gate (CI's search-recall job provides it)"
    ),
)

UTC = dt.timezone.utc

#: Production ids, kept so a failure names the rows a reader would have seen.
CANONICAL = 15297677  # Liverpool v Fulham, the real row: 0-0, completed
GHOST = 15310639  # the twin the B11 link carries: tagged duplicate-of
CLEAN = 15297724  # an unrelated, untagged fixture (the matrix's own row)
ABSENT = 15399999  # no such row
DANGLING = 15310640  # tagged as duplicate of a row that does not exist
SELF_TAGGED = 15310641  # tagged as duplicate of ITSELF
MALFORMED = 15310642  # carries a tag whose tail is not an id
CYCLE_A = 15310643  # tagged -> CYCLE_B
CYCLE_B = 15310644  # tagged -> CYCLE_A
MERGED = 15310645  # status 'merged', tagged -> CANONICAL
VOIDED = 15310646  # status 'voided', no tag
DRAIN_GHOST = 15310647  # Q050 arm: market-born, its only market moved to CANONICAL

ALL_EVENT_IDS = [
    CANONICAL,
    GHOST,
    CLEAN,
    DANGLING,
    SELF_TAGGED,
    MALFORMED,
    CYCLE_A,
    CYCLE_B,
    MERGED,
    VOIDED,
    DRAIN_GHOST,
]

#: Reserved `sports.id`; explicit so this gate never draws from the shared
#: database's sequence (see the #6221 sibling for the CI failure that costs).
S_EPL = 90_006_975
SPORT_KEY = "soccer_epl"

#: Markets, all on the CANONICAL. Ids reserved the same way.
M_SCORE = 90_006_975_1
M_FIRST = 90_006_975_2
M_CLEAN = 90_006_975_3  # the clean event's own market, distinct name
M_DRAINED = 90_006_975_4  # the market whose anchor still names DRAIN_GHOST
ALL_MARKET_IDS = [M_SCORE, M_FIRST, M_CLEAN, M_DRAINED]

KICKOFF = dt.datetime(2026, 9, 12, 14, 0, tzinfo=UTC)
FINAL_WHISTLE = dt.datetime(2026, 9, 12, 15, 54, 11, tzinfo=UTC)
DRAINED_TICKER = "KXEPLGAME-26SEP12LIVFUL"


# ─────────────────────────────────────────────────────────────────────────────
# Harness
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
async def pg_engine():
    """Function-scoped: `pytest.ini` leaves the fixture loop scope unset.

    Creates the whole metadata rather than a hand-picked table set — the
    history route reads eight tables and a missing one would fail this gate
    for a reason that has nothing to do with #6975. CI's service container is
    Postgres 15, which `create_all` needs for the one `NULLS NOT DISTINCT`
    clause in the metadata.
    """
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(sync, checkfirst=True)
        )
    yield engine
    await engine.dispose()


class _FakeRedis:
    """In-memory Redis: the get / set / setex / delete surface the two tiers use.

    Anything else raises `AttributeError`, which every Redis touch on these
    routes wraps in a broad `except` — so an unexpected call degrades to a
    cache miss rather than to a fake that quietly answers.
    """

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.ttls[k] = int(ttl)
        self.store[k] = v.encode() if isinstance(v, str) else v

    def set(self, k, v, nx=False, ex=None, **_):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        if ex is not None:
            self.ttls[k] = int(ex)
        return True

    def delete(self, *keys):
        n = 0
        for k in keys:
            self.ttls.pop(k, None)
            n += int(self.store.pop(k, None) is not None)
        return n

    def exists(self, k):
        return int(k in self.store)


@pytest.fixture
def fake_redis(monkeypatch):
    """One fake behind BOTH tiers, and the in-process L1s emptied.

    `get_game_markets` reaches Redis through `game_markets_cache.get_client`;
    `get_team_progression` through `app.tasks.redis_state.get_redis_client`
    (imported inside the handler, so the module attribute is what it reads).
    """
    from app.routes import events as events_route
    from app.tasks import redis_state
    from app.utils import game_markets_cache as gmc

    rc = _FakeRedis()
    monkeypatch.setattr(gmc, "get_client", lambda: rc)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: rc)
    events_route._game_markets_cache.clear()
    events_route._event_detail_cache.clear()
    yield rc
    events_route._game_markets_cache.clear()
    events_route._event_detail_cache.clear()


@pytest.fixture
def league_context(monkeypatch):
    """A minimal league context so `/team-progression` composes its cards.

    The grid behind `enrich_event_with_context` is its own Redis-backed
    service and is not what this gate is about; what IS under test is which
    row's names the cards carry. The stub echoes the row it is handed, so a
    card titled `FC` can only come from the ghost row having been served.
    """
    from app.services import league_context as lc

    calls: list[int] = []

    async def _ctx(event, db):
        calls.append(int(event.id))
        cells = {"make_playoffs": 0.5}
        return {
            "columns": [{"key": "make_playoffs", "label": "Top 4"}],
            "home_team": {
                "cells": cells,
                "changes_24h": {},
                "sources_available": ["kalshi"],
            },
            "away_team": {
                "cells": cells,
                "changes_24h": {},
                "sources_available": ["kalshi"],
            },
        }

    monkeypatch.setattr(lc, "enrich_event_with_context", _ctx)
    return calls


@pytest.fixture
async def client(pg_engine, monkeypatch):
    """httpx client over the REAL FastAPI app, with `get_db` handing out real
    sessions on the disposable database — the integration `client` fixture's
    shape, minus the mock."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    async def _real_get_db():
        async with AsyncSession(pg_engine, expire_on_commit=False) as session:
            yield session

    async def _no_user():
        return None

    app.dependency_overrides[get_db] = _real_get_db
    app.dependency_overrides[get_db_rw] = _real_get_db
    app.dependency_overrides[get_optional_user] = _no_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                yield ac
    finally:
        app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Seed
# ─────────────────────────────────────────────────────────────────────────────


async def _sport_id(session, key, name, reserved_id):
    await session.execute(
        text(
            "INSERT INTO sports (id, key, name, active) "
            "VALUES (:i, :k, :n, true) ON CONFLICT DO NOTHING"
        ),
        {"i": reserved_id, "k": key, "n": name},
    )
    sport_id = (
        await session.execute(text("SELECT id FROM sports WHERE key = :k"), {"k": key})
    ).scalar()
    assert sport_id is not None, f"sport {key!r} neither present nor insertable"
    return sport_id


async def _seed(pg_engine):
    """The Liverpool–Fulham pair as production holds it, plus every control.

    Distinct values are the whole design: the ghost spells the clubs with the
    club-type suffix production stores (`Liverpool FC`), so `short_name` — the
    last word of the served name — reads `FC` off the ghost and `Liverpool` off
    the canonical; markets and series points exist ONLY on the canonical; the
    clean event has its own market with its own name.
    """
    from app.models.models import (
        Event,
        EventProviderAnchor,
        FuturesMarket,
        FuturesOutcome,
        WinProbSnapshot,
    )
    from app.services.anchor_channel import duplicate_tag
    from app.utils.provider_anchor_keys import ANCHOR_KIND_MARKET, SOURCE_KALSHI

    async with AsyncSession(pg_engine, expire_on_commit=False) as s:
        await s.execute(
            delete(EventProviderAnchor).where(
                EventProviderAnchor.event_id.in_(ALL_EVENT_IDS)
            )
        )
        await s.execute(
            delete(WinProbSnapshot).where(WinProbSnapshot.event_id.in_(ALL_EVENT_IDS))
        )
        await s.execute(
            delete(FuturesOutcome).where(FuturesOutcome.market_id.in_(ALL_MARKET_IDS))
        )
        await s.execute(
            delete(FuturesMarket).where(FuturesMarket.id.in_(ALL_MARKET_IDS))
        )
        await s.execute(delete(Event).where(Event.id.in_(ALL_EVENT_IDS)))
        sport_id = await _sport_id(s, SPORT_KEY, "Premier League", S_EPL)

        def _event(eid, home, away, **over):
            base = {
                "id": eid,
                "sport_id": sport_id,
                "home_team_name": home,
                "away_team_name": away,
                "commence_time": KICKOFF,
                "status": "completed",
                "home_score": 0,
                "away_score": 0,
                "completed_at": FINAL_WHISTLE,
                "commence_time_source": "statpal",
                "win_probability_sources": {"kalshi": {"value": 0.42}},
            }
            base.update(over)
            return Event(**base)

        s.add_all(
            [
                # The real row.
                _event(CANONICAL, "Liverpool", "Fulham"),
                # The twin the link carries: proven duplicate (ruling 048 arm B).
                _event(
                    GHOST,
                    "Liverpool FC",
                    "Fulham FC",
                    status="scheduled",
                    home_score=None,
                    away_score=None,
                    completed_at=None,
                    win_probability_sources=None,
                    event_tags=[duplicate_tag(CANONICAL)],
                ),
                # Untagged, unrelated, with its own distinct content.
                _event(CLEAN, "Arsenal", "Chelsea", home_score=2, away_score=1),
                # Refusals the extraction must not have loosened.
                _event(
                    DANGLING,
                    "Dangling FC",
                    "Target Gone FC",
                    event_tags=[duplicate_tag(ABSENT)],
                ),
                _event(
                    SELF_TAGGED,
                    "Self FC",
                    "Naming FC",
                    event_tags=[duplicate_tag(SELF_TAGGED)],
                ),
                _event(
                    MALFORMED,
                    "Malformed FC",
                    "Tag FC",
                    event_tags=["provenance:duplicate-of:not-an-id"],
                ),
                _event(
                    CYCLE_A,
                    "Cycle A Home",
                    "Cycle A Away",
                    event_tags=[duplicate_tag(CYCLE_B)],
                ),
                _event(
                    CYCLE_B,
                    "Cycle B Home",
                    "Cycle B Away",
                    event_tags=[duplicate_tag(CYCLE_A)],
                ),
                # Retirement, both shapes.
                _event(
                    MERGED,
                    "Merged FC",
                    "Away FC",
                    status="merged",
                    event_tags=[duplicate_tag(CANONICAL)],
                ),
                _event(
                    VOIDED,
                    "Voided FC",
                    "Never Played FC",
                    status="voided",
                    home_score=None,
                    away_score=None,
                    completed_at=None,
                ),
                # Q050: a market-born row whose only market now sits on the
                # canonical — the id-keyed contradiction the drain reads.
                _event(
                    DRAIN_GHOST,
                    "Liverpool FC",
                    "Fulham FC",
                    status="scheduled",
                    home_score=None,
                    away_score=None,
                    completed_at=None,
                    win_probability_sources=None,
                    commence_time_source="kalshi",
                ),
            ]
        )
        await s.flush()

        def _market(mid, eid, name, ticker):
            return FuturesMarket(
                id=mid,
                source="kalshi",
                external_id=ticker,
                sport_id=sport_id,
                event_id=eid,
                name=name,
                category="game_prop",
                llm_sport_category="soccer",
                status="resolved",
                mutually_exclusive=True,
                commence_time=KICKOFF,
                settled_at=FINAL_WHISTLE,
            )

        s.add_all(
            [
                _market(
                    M_SCORE,
                    CANONICAL,
                    "Liverpool vs Fulham: Correct Score",
                    "KXEPLSCORE-26SEP12LIVFUL",
                ),
                _market(
                    M_FIRST,
                    CANONICAL,
                    "Liverpool vs Fulham: First Team to Score",
                    "KXEPLFTS-26SEP12LIVFUL",
                ),
                _market(
                    M_CLEAN,
                    CLEAN,
                    "Arsenal vs Chelsea: Correct Score",
                    "KXEPLSCORE-26SEP12ARSCHE",
                ),
                _market(
                    M_DRAINED, CANONICAL, "Liverpool vs Fulham: Winner", DRAINED_TICKER
                ),
            ]
        )
        await s.flush()

        # Graded legs: `resolution_source` set, as a settled book the page may
        # print carries it (#6025 withholds a settled market graded nothing).
        def _leg(mid, ext, name, prob, won):
            return FuturesOutcome(
                market_id=mid,
                external_id=ext,
                name=name,
                current_probability=prob,
                is_winner=won,
                resolution_source="api_settlement",
                last_updated=FINAL_WHISTLE,
            )

        s.add_all(
            [
                _leg(M_SCORE, "draw-0-0", "Draw 0-0", 1.0, True),
                _leg(M_SCORE, "liv-1-0", "Liverpool 1-0", 0.0, False),
                _leg(M_FIRST, "no-goal", "No Goal", 1.0, True),
                _leg(M_CLEAN, "ars-2-1", "Arsenal 2-1", 1.0, True),
                _leg(M_DRAINED, "liv", "Liverpool", 0.0, False),
                _leg(M_DRAINED, "draw", "Draw", 1.0, True),
            ]
        )
        # The anchor the registry wrote when the market MINTED the drain ghost;
        # the market itself has since been moved onto the canonical.
        s.add(
            EventProviderAnchor(
                event_id=DRAIN_GHOST,
                source=SOURCE_KALSHI,
                source_id=DRAINED_TICKER,
                id_kind=ANCHOR_KIND_MARKET,
            )
        )
        # The curve: one point before kick-off, two after — ONLY on the
        # canonical, so `range=since_start` has something to omit and the ghost
        # has nothing of its own to draw.
        for eid in (CANONICAL, CLEAN):
            for minutes, prob in ((-60, 0.80), (10, 0.60), (70, 0.42)):
                s.add(
                    WinProbSnapshot(
                        event_id=eid,
                        source="kalshi",
                        captured_at=KICKOFF + dt.timedelta(minutes=minutes),
                        home_win_probability=prob,
                        away_win_probability=round(1 - prob, 2),
                    )
                )
        await s.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

MARKET_BUCKETS = (
    "totals",
    "player_props",
    "team_totals",
    "spreads",
    "period_markets",
    "matchups",
    "other",
)


def _book(body: dict) -> dict:
    """The game-markets body minus its cache envelope — the bytes a reader
    compares, with the two timestamps the envelope stamps per build left out."""
    from app.utils.event_concept_cache import ENVELOPE_FIELD

    return {k: v for k, v in body.items() if k != ENVELOPE_FIELD}


def _market_count(body: dict) -> int:
    return sum(len(body.get(b) or []) for b in MARKET_BUCKETS)


def _curve_points(body: dict) -> int:
    return sum(len(v or []) for v in (body.get("win_prob_history") or {}).values())


async def _get(client, path):
    r = await client.get(path)
    assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:300]}"
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# The ship — RED on the parent for the twin id, GREEN for the canonical
# ─────────────────────────────────────────────────────────────────────────────


@needs_postgres
@pytest.mark.asyncio
async def test_game_markets_on_the_original_id_serve_the_canonical_book(
    pg_engine, client, fake_redis
):
    """RED ON THE PARENT: `event_id 15310639, home_team null, 0 markets`."""
    await _seed(pg_engine)
    canonical = await _get(client, f"/api/events/{CANONICAL}/game-markets")
    ghost = await _get(client, f"/api/events/{GHOST}/game-markets")

    assert (
        _market_count(canonical) >= 3
    ), "the canonical seed did not build a book — gate is vacuous"
    assert ghost["event_id"] == CANONICAL
    assert ghost["home_team"] == "Liverpool" and ghost["away_team"] == "Fulham"
    assert _book(ghost) == _book(canonical), (
        "the twin id's book is not the canonical's — a different computation, "
        "or a different row, reached the reader"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_history_on_the_original_id_draws_the_canonical_curve(
    pg_engine, client, fake_redis
):
    """RED ON THE PARENT: `win_prob_history` empty for the twin id.

    Query parameters survive the resolution: `range=since_start` omits the
    pre-kick-off point for BOTH ids, `all` keeps it for both.
    """
    await _seed(pg_engine)
    for rng, expected in (("since_start", 2), ("all", 3)):
        canonical = await _get(
            client, f"/api/events/{CANONICAL}/history?hours=48&range={rng}"
        )
        ghost = await _get(client, f"/api/events/{GHOST}/history?hours=48&range={rng}")

        assert _curve_points(canonical) == expected, (
            rng,
            canonical.get("win_prob_history"),
        )
        assert ghost["event_id"] == CANONICAL
        assert ghost["home_team"] == "Liverpool"
        assert _curve_points(ghost) == expected, (
            f"range={rng}: the twin id drew {_curve_points(ghost)} points, the "
            f"canonical {expected}"
        )
        assert ghost["win_prob_history"] == canonical["win_prob_history"]
        assert ghost["time_domain"] == canonical["time_domain"]
        assert ghost["completed_at"] == canonical["completed_at"]


@needs_postgres
@pytest.mark.asyncio
async def test_team_progression_on_the_original_id_names_the_clubs(
    pg_engine, client, fake_redis, league_context
):
    """RED ON THE PARENT: home `"Liverpool FC"` / short_name `"FC"`."""
    await _seed(pg_engine)
    canonical = await _get(client, f"/api/events/{CANONICAL}/team-progression")
    ghost = await _get(client, f"/api/events/{GHOST}/team-progression")

    assert canonical["home_team"]["short_name"] == "Liverpool"
    assert ghost["event_id"] == CANONICAL
    assert ghost["home_team"]["name"] == "Liverpool"
    assert ghost["home_team"]["short_name"] == "Liverpool"
    assert ghost["away_team"]["short_name"] == "Fulham"
    assert ghost == canonical
    assert league_context == [CANONICAL], (
        "the progression was composed off a row other than the canonical, or "
        f"more than once: {league_context}"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_the_detail_route_and_its_three_sub_resources_agree_about_the_row(
    pg_engine, client, fake_redis, league_context
):
    """The page-level invariant #6975 states: one id, one row, on all four."""
    await _seed(pg_engine)
    detail = await _get(client, f"/api/events/{GHOST}")
    ids = {
        "detail": detail["id"],
        "game-markets": (await _get(client, f"/api/events/{GHOST}/game-markets"))[
            "event_id"
        ],
        "history": (await _get(client, f"/api/events/{GHOST}/history?hours=48"))[
            "event_id"
        ],
        "team-progression": (
            await _get(client, f"/api/events/{GHOST}/team-progression")
        )["event_id"],
    }
    assert ids == {k: CANONICAL for k in ids}, ids


@needs_postgres
@pytest.mark.asyncio
async def test_the_Q050_market_born_arm_resolves_on_every_surface(
    pg_engine, client, fake_redis, league_context
):
    """The second identity mechanism, unchanged: a market-born row whose only
    market moved to the canonical reads as the canonical — on the detail route
    (today) and on all three sub-resources (this ship)."""
    await _seed(pg_engine)
    from app.services.anchor_channel import resolve_market_born_duplicate

    async with AsyncSession(pg_engine) as s:
        assert (
            await resolve_market_born_duplicate(s, DRAIN_GHOST) == CANONICAL
        ), "the drain verdict does not fire on the seed — this test would be vacuous"

    detail = await _get(client, f"/api/events/{DRAIN_GHOST}")
    markets = await _get(client, f"/api/events/{DRAIN_GHOST}/game-markets")
    history = await _get(client, f"/api/events/{DRAIN_GHOST}/history?hours=48")
    progression = await _get(client, f"/api/events/{DRAIN_GHOST}/team-progression")

    assert detail["id"] == CANONICAL
    assert markets["event_id"] == CANONICAL and _market_count(markets) >= 3
    assert history["event_id"] == CANONICAL and _curve_points(history) == 3
    assert progression["home_team"]["short_name"] == "Liverpool"


# ─────────────────────────────────────────────────────────────────────────────
# Controls — green on the parent AND on the ship
# ─────────────────────────────────────────────────────────────────────────────


@needs_postgres
@pytest.mark.asyncio
async def test_CONTROL_direct_canonical_requests_are_unchanged(
    pg_engine, client, fake_redis, league_context
):
    await _seed(pg_engine)
    markets = await _get(client, f"/api/events/{CANONICAL}/game-markets")
    history = await _get(
        client, f"/api/events/{CANONICAL}/history?hours=48&range=since_start"
    )
    progression = await _get(client, f"/api/events/{CANONICAL}/team-progression")

    assert markets["event_id"] == CANONICAL and markets["home_team"] == "Liverpool"
    names = {
        o["outcome_name"] if "outcome_name" in o else o.get("name")
        for b in MARKET_BUCKETS
        for o in (markets.get(b) or [])
    }
    assert names & {
        "Draw 0-0",
        "No Goal",
    }, f"the seeded outcomes did not reach the book: {names}"
    assert history["event_id"] == CANONICAL and _curve_points(history) == 2
    assert progression["event_id"] == CANONICAL
    assert progression["home_team"]["short_name"] == "Liverpool"


@needs_postgres
@pytest.mark.asyncio
async def test_CONTROL_a_clean_event_serves_itself(
    pg_engine, client, fake_redis, league_context
):
    await _seed(pg_engine)
    markets = await _get(client, f"/api/events/{CLEAN}/game-markets")
    history = await _get(client, f"/api/events/{CLEAN}/history?hours=48")
    progression = await _get(client, f"/api/events/{CLEAN}/team-progression")

    assert markets["event_id"] == CLEAN and markets["home_team"] == "Arsenal"
    assert _market_count(markets) == 1
    assert history["event_id"] == CLEAN and history["home_team"] == "Arsenal"
    assert _curve_points(history) >= 3, "the clean event's own curve did not draw"
    assert progression["event_id"] == CLEAN
    assert progression["home_team"]["short_name"] == "Arsenal"


@needs_postgres
@pytest.mark.asyncio
async def test_CONTROL_an_absent_id_is_a_404_on_every_surface(
    pg_engine, client, fake_redis
):
    await _seed(pg_engine)
    for path in ("", "/game-markets", "/history?hours=48", "/team-progression"):
        r = await client.get(f"/api/events/{ABSENT}{path}")
        assert r.status_code == 404, (path, r.status_code)


@needs_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_id, home",
    [
        (DANGLING, "Dangling FC"),  # tag names a row that does not exist
        (SELF_TAGGED, "Self FC"),  # tag names itself
        (MALFORMED, "Malformed FC"),  # tag tail is not an id
    ],
)
async def test_CONTROL_a_proof_that_cannot_be_followed_serves_the_row_asked_for(
    pg_engine, client, fake_redis, league_context, event_id, home
):
    """The detail route's refusals, now every surface's: a missing target, a
    self-reference and a malformed tail each leave the row in hand."""
    await _seed(pg_engine)
    detail = await _get(client, f"/api/events/{event_id}")
    markets = await _get(client, f"/api/events/{event_id}/game-markets")
    history = await _get(client, f"/api/events/{event_id}/history?hours=48")
    progression = await _get(client, f"/api/events/{event_id}/team-progression")

    assert detail["id"] == event_id and detail["home_team"] == home
    # A row with no markets answers the tier's empty literal, which carries
    # the id and no team names — today's shape, kept.
    assert markets["event_id"] == event_id
    assert history["event_id"] == event_id and history["home_team"] == home
    assert progression["event_id"] == event_id
    assert progression["home_team"]["name"] == home


@needs_postgres
@pytest.mark.asyncio
async def test_CONTROL_a_cycle_is_one_hop_and_never_chased(
    pg_engine, client, fake_redis, league_context
):
    """A tagged -> B and B tagged -> A: each serves the OTHER, once. No walk,
    no hang, no redesign of the graph — `canonical_id_from_tags` is one hop."""
    from app.routes import events as events_route

    await _seed(pg_engine)
    for asked, served, home in (
        (CYCLE_A, CYCLE_B, "Cycle B Home"),
        (CYCLE_B, CYCLE_A, "Cycle A Home"),
    ):
        # Each hop from a cold cache. The detail and game-markets tiers key a
        # payload under BOTH ids (Q050), so on a two-node cycle the second
        # request would otherwise be served the first's payload — a
        # pre-existing property of dual keying on a shape production holds
        # zero of, not the one-hop rule under test here.
        events_route._event_detail_cache.clear()
        events_route._game_markets_cache.clear()
        fake_redis.store.clear()
        assert (await _get(client, f"/api/events/{asked}"))["id"] == served
        markets = await _get(client, f"/api/events/{asked}/game-markets")
        history = await _get(client, f"/api/events/{asked}/history?hours=48")
        progression = await _get(client, f"/api/events/{asked}/team-progression")
        assert markets["event_id"] == served
        assert history["event_id"] == served and history["home_team"] == home
        assert progression["home_team"]["name"] == home


@needs_postgres
@pytest.mark.asyncio
async def test_CONTROL_retirement_semantics_are_unchanged(
    pg_engine, client, fake_redis, league_context
):
    """A `merged` row that names its successor serves the successor everywhere
    (better than telling a reader there is no game). A `voided` row that names
    nothing keeps today's behaviour on each surface: the detail route's 410,
    and the sub-resources' own content — this ship changes identity, not
    retirement."""
    await _seed(pg_engine)
    assert (await _get(client, f"/api/events/{MERGED}"))["id"] == CANONICAL
    assert (await _get(client, f"/api/events/{MERGED}/game-markets"))[
        "event_id"
    ] == CANONICAL
    assert (await _get(client, f"/api/events/{MERGED}/history?hours=48"))[
        "event_id"
    ] == CANONICAL
    assert (await _get(client, f"/api/events/{MERGED}/team-progression"))["home_team"][
        "short_name"
    ] == "Liverpool"

    assert (await client.get(f"/api/events/{VOIDED}")).status_code == 410
    assert (await _get(client, f"/api/events/{VOIDED}/game-markets"))[
        "event_id"
    ] == VOIDED
    assert (await _get(client, f"/api/events/{VOIDED}/history?hours=48"))[
        "home_team"
    ] == "Voided FC"
    assert (await _get(client, f"/api/events/{VOIDED}/team-progression"))["home_team"][
        "name"
    ] == "Voided FC"


# ─────────────────────────────────────────────────────────────────────────────
# Cache — cold and warm, stale alias slots included
# ─────────────────────────────────────────────────────────────────────────────


def _empty_ghost_book() -> dict:
    """Byte-for-byte what the parent published under the twin id."""
    return {
        "event_id": GHOST,
        "totals": [],
        "player_props": [],
        "spreads": [],
        "matchups": [],
        "other": [],
        "pace": None,
        "props_script": [],
    }


@needs_postgres
@pytest.mark.asyncio
async def test_game_markets_a_stale_alias_slot_from_the_previous_release_is_refused(
    pg_engine, client, fake_redis, monkeypatch
):
    """What the deploy carrying this looks like: Redis still holds the twin
    id's EMPTY book, stamped with the release that built it. `gmc.read` refuses
    a slot from another build (#6355), the route rebuilds, resolves, and serves
    the canonical — cold path over a poisoned slot."""
    from app.utils import game_markets_cache as gmc

    await _seed(pg_engine)
    monkeypatch.setenv("HEROKU_RELEASE_VERSION", "v-before-6975")
    stale = gmc.stamp(_empty_ghost_book(), source_status="scheduled")
    # The write is the SEEDING of this test, not one of its claims, so it lives
    # outside the assert: `python -O` strips assert statements, and an assert
    # that both seeds and checks would leave the slot unwritten while every
    # assertion below still passed — a green test of nothing (`py/side-effect-in-assert`).
    wrote_stale_slot = gmc.write(GHOST, stale, fake_redis)
    assert wrote_stale_slot, "the fake did not take the slot"
    assert (
        gmc.read(GHOST, fake_redis)[1] == "live"
    ), "precondition: the slot serves on its own build"

    monkeypatch.setenv("HEROKU_RELEASE_VERSION", "v-with-6975")
    assert gmc.read(GHOST, fake_redis)[1] == "stale_build"

    ghost = await _get(client, f"/api/events/{GHOST}/game-markets")
    assert ghost["event_id"] == CANONICAL and _market_count(ghost) >= 3


@needs_postgres
@pytest.mark.asyncio
async def test_game_markets_warm_paths_serve_the_canonical_book_without_a_rebuild(
    pg_engine, client, fake_redis, monkeypatch
):
    """After one build for the twin id: (1) a reader of the twin id on a
    DIFFERENT process is served from Redis, canonical content, no build; (2) a
    reader of the CANONICAL id is served from the slot that build filled."""
    from app.routes import events as events_route
    from app.utils import game_markets_cache as gmc

    await _seed(pg_engine)
    builds: list[int] = []
    real_build = events_route._build_game_markets

    async def _counting_build(event_id, db):
        builds.append(int(event_id))
        return await real_build(event_id, db)

    monkeypatch.setattr(events_route, "_build_game_markets", _counting_build)

    first = await _get(client, f"/api/events/{GHOST}/game-markets")
    assert builds == [GHOST] and first["event_id"] == CANONICAL
    assert gmc.read(GHOST, fake_redis)[1] == "live"
    assert (
        gmc.read(CANONICAL, fake_redis)[1] == "live"
    ), "the canonical's slot was not filled"

    events_route._game_markets_cache.clear()  # another worker: same Redis, empty L1
    second = await _get(client, f"/api/events/{GHOST}/game-markets")
    assert builds == [GHOST], "the second reader of the twin id rebuilt"
    assert second["event_id"] == CANONICAL and _book(second) == _book(first)

    third = await _get(client, f"/api/events/{CANONICAL}/game-markets")
    assert builds == [
        GHOST
    ], "a canonical reader rebuilt what the twin's build already published"
    assert _book(third) == _book(first)


@needs_postgres
@pytest.mark.asyncio
async def test_game_markets_a_direct_canonical_build_is_not_published_under_any_other_id(
    pg_engine, client, fake_redis
):
    """The reverse direction is deliberately NOT a fold: a canonical build knows
    nothing about which twins name it, so it fills exactly its own slot."""
    from app.utils import game_markets_cache as gmc

    await _seed(pg_engine)
    await _get(client, f"/api/events/{CANONICAL}/game-markets")
    assert gmc.read(CANONICAL, fake_redis)[1] == "live"
    assert gmc.read(GHOST, fake_redis)[1] == "miss"


@needs_postgres
@pytest.mark.asyncio
async def test_team_progression_a_stale_alias_slot_is_never_read_and_the_warm_slots_serve(
    pg_engine, client, fake_redis, league_context
):
    """The pre-#6975 slot has no build stamp, so it is made unreachable BY KEY:
    the twin id's old entry (`"Liverpool FC"` / `"FC"`) sits under the old
    namespace and the route serves the canonical anyway (cold). Then both ids'
    NEW slots are warm, and a reader of either is served without composing
    again (warm)."""
    import json

    from app.routes import events as events_route

    await _seed(pg_engine)
    old_key = f"bainluck:team_progression:{GHOST}"
    fake_redis.setex(
        old_key,
        300,
        json.dumps(
            {
                "event_id": GHOST,
                "league": "epl",
                "league_name": "Premier League",
                "grid_url": "/playoffs/epl",
                "home_team": {"name": "Liverpool FC", "short_name": "FC"},
                "away_team": {"name": "Fulham FC", "short_name": "FC"},
            }
        ),
    )

    ghost = await _get(client, f"/api/events/{GHOST}/team-progression")
    assert ghost["home_team"]["short_name"] == "Liverpool", ghost
    assert league_context == [CANONICAL]
    assert (
        old_key in fake_redis.store
    ), "the old slot was touched — it should simply never be read"
    new_keys = {events_route._team_progression_cache_key(i) for i in (GHOST, CANONICAL)}
    assert new_keys <= set(
        fake_redis.store
    ), f"both ids' slots should be warm: {sorted(fake_redis.store)}"

    # Warm: neither id composes again.
    again = await _get(client, f"/api/events/{GHOST}/team-progression")
    canonical = await _get(client, f"/api/events/{CANONICAL}/team-progression")
    assert again == ghost == canonical
    assert league_context == [CANONICAL], "a warm reader composed the progression again"


@needs_postgres
@pytest.mark.asyncio
async def test_team_progression_a_warm_canonical_slot_serves_a_cold_twin_id(
    pg_engine, client, fake_redis, league_context
):
    """Canonical cache reuse: the canonical was read first, then the twin id
    arrives cold — it is filled from the canonical's slot, not composed."""
    await _seed(pg_engine)
    canonical = await _get(client, f"/api/events/{CANONICAL}/team-progression")
    assert league_context == [CANONICAL]
    ghost = await _get(client, f"/api/events/{GHOST}/team-progression")
    assert ghost == canonical
    assert league_context == [
        CANONICAL
    ], "the twin id composed again despite a warm canonical slot"
