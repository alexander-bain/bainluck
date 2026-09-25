"""#837: a multi-sport odds pass releases a game's rows before its next network call.

WHAT WAS MEASURED (production, 2026-09-25, live/583's capture, no new capture)
------------------------------------------------------------------------------
From 03:05:40 to 03:06:35Z the live blend refresher re-queued Padres @ Dodgers
(15317977) every ~2 s — "row locked >500ms" on its `events` tuple, both arms,
30 lines. Postgres named the holder: pid 2355090, transaction 22490318, opened
03:05:00 by `discover_events` on worker-background. The transaction ended at
03:06:35.8 (a waiter "acquired ShareLock on transaction 22490318 after
44746.833 ms"), which is that pass's single `session.commit()`: one transaction
across 33 sports' Odds API fetches, and every `events` row `_ingest_event_odds`
touched (`UPDATE events SET win_probability_sources`) stayed locked until it.
`poll_all_odds[ecad4b0e]` queued 17.8 s and 44.7 s behind the same holder (56.4 s
against its usual 8–11 s), and `poll_all_odds[be29398d]` lost a 40P01 to it and
died on PendingRollbackError — every sport after the deadlock inherited the
aborted transaction.

`_poll_all_odds` has the same shape on a 30 s beat. Its passes are short, so the
holds are short, but live/583's re-queues for this game cluster at :23–:24 and
:53 — the seconds just before that pass commits.

WHAT THIS FILE PROVES
---------------------
The fake odds client PROBES THE DATABASE FROM A SECOND CONNECTION at the moment
the pass makes its next network call: `SELECT ... FOR UPDATE` under a 300 ms
`lock_timeout` on every game a previous call already answered. Before #837 that
probe is refused (the pass is idle in transaction holding the row). After, it
acquires. That is the reproducer, and it runs on both passes and on the scores
loop.

The second property is the rollback: a sport whose statement fails must not
take the sports after it down with it. The failure is a real Postgres error
(`division_by_zero`), not a mock, because what matters is what the ABORTED
TRANSACTION does to the next statement.

WHAT IS NOT HERE
----------------
The registry. `find_or_create_event` is replaced by a lookup of the seeded row:
matching is not the subject, and the real registry would pull a dozen tables
into a file about transaction boundaries. The stale sweep and the live GEI
update are neutralised because they are UNSCOPED (they sweep every `live` row),
and the CI database is shared with the other steps of the `search-recall` job.

The sport keys are invented (`test837_*`) so no other step's rows can join
either pass, and so the ESPN schedule branch in `_discover_events`
(`SPORT_LEAGUE_MAP` sports only) never makes a network call.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #837 lock-release "
        "gate (CI job `search-recall` provides one)"
    ),
)

SPORTS = {993701: "test837_alpha", 993702: "test837_beta"}

# One upcoming game per sport (the odds loops) and one finished, unanchored game
# per sport (the scores loop). Ids are this file's own block.
ODDS_GAMES = {993711: 993701, 993712: 993702}
SCORE_GAMES = {993721: 993701, 993722: 993702}
ALL_GAMES = {**ODDS_GAMES, **SCORE_GAMES}

HOME, AWAY = "Alpha Home", "Beta Away"
BOOKS = ("book_one", "book_two", "book_three")  # BETTING_BOOK_FLOOR is 3


def _ext(event_id: int) -> str:
    return f"odds-837-pg-{event_id}"


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


@pytest.fixture
async def pg_engine():
    """Real Postgres, only this file's tables, only this file's rows (7147's rig)."""
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models import Event, ScoreSnapshot
    from app.services.database import Base

    tables = [
        Base.metadata.tables[name]
        for name in ("sports", "teams", "venues", "odds_snapshots")
    ] + [Event.__table__, ScoreSnapshot.__table__]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)
        await _clear(conn)
        await _seed(conn)
    yield engine
    async with engine.begin() as conn:
        await _clear(conn)
    await engine.dispose()


async def _clear(conn):
    ids = list(ALL_GAMES)
    for table in ("odds_snapshots", "score_snapshots"):
        await conn.execute(
            text(f"DELETE FROM {table} WHERE event_id = ANY(:ids)"), {"ids": ids}
        )
    await conn.execute(text("DELETE FROM events WHERE id = ANY(:ids)"), {"ids": ids})
    await conn.execute(
        text("DELETE FROM teams WHERE sport_id = ANY(:s)"), {"s": list(SPORTS)}
    )
    await conn.execute(
        text("DELETE FROM sports WHERE id = ANY(:s)"), {"s": list(SPORTS)}
    )


async def _seed(conn):
    """Two sports, their teams (so discovery creates none), and four games.

    🔴 Every time is an offset from one `now` (gotcha #44), and the odds games
    start in +1 h so `_poll_all_odds`' 6-hour lookahead selects both sports.
    """
    now = datetime.now(timezone.utc)
    for sport_id, key in SPORTS.items():
        await conn.execute(
            text("INSERT INTO sports (id, key, name, active) VALUES (:i, :k, :k, true)"),
            {"i": sport_id, "k": key},
        )
        for name in (HOME, AWAY):
            await conn.execute(
                text("INSERT INTO teams (sport_id, name) VALUES (:s, :n)"),
                {"s": sport_id, "n": name},
            )
    for event_id, sport_id in ODDS_GAMES.items():
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, external_id, home_team_name, "
                "away_team_name, commence_time, status) "
                "VALUES (:i, :s, :x, :h, :a, :c, 'scheduled')"
            ),
            {"i": event_id, "s": sport_id, "x": _ext(event_id), "h": HOME,
             "a": AWAY, "c": now + timedelta(hours=1)},
        )
    for event_id, sport_id in SCORE_GAMES.items():
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, external_id, home_team_name, "
                "away_team_name, commence_time, status) "
                "VALUES (:i, :s, :x, :h, :a, :c, 'completed')"
            ),
            {"i": event_id, "s": sport_id, "x": _ext(event_id), "h": HOME,
             "a": AWAY, "c": now - timedelta(hours=4)},
        )


def _odds_payload(event_id: int) -> list[dict]:
    """One Odds API event with three books quoting the same moneyline."""
    return [{
        "id": _ext(event_id),
        "commence_time": _iso(datetime.now(timezone.utc) + timedelta(hours=1)),
        "home_team": HOME,
        "away_team": AWAY,
        "bookmakers": [
            {"key": book, "title": book, "markets": [{
                "key": "h2h",
                "outcomes": [{"name": HOME, "price": -150},
                             {"name": AWAY, "price": 130}],
            }]}
            for book in BOOKS
        ],
    }]


def _score_payload(event_id: int, commence: datetime) -> list[dict]:
    return [{
        "id": _ext(event_id),
        "commence_time": _iso(commence),
        "completed": True,
        "home_team": HOME,
        "away_team": AWAY,
        "scores": [{"name": HOME, "score": "5"}, {"name": AWAY, "score": "2"}],
    }]


async def _probe(engine, event_ids) -> dict[int, str]:
    """From a SECOND connection: is each game's `events` row free right now?"""
    out = {}
    for event_id in event_ids:
        async with engine.connect() as conn:
            try:
                async with conn.begin():
                    await conn.execute(text("SET LOCAL lock_timeout = '300ms'"))
                    await conn.execute(
                        text("SELECT id FROM events WHERE id = :i FOR UPDATE"),
                        {"i": event_id},
                    )
                out[event_id] = "free"
            except DBAPIError as exc:
                if "lock" not in str(exc).lower():
                    raise
                out[event_id] = "held"
    return out


class _ProbingOddsAPI:
    """Answers this file's two sports, and probes at every network call.

    The ORDER in which a pass visits sports is a heap order (`GROUP BY` / a
    bare `select(Sport)`), so nothing here assumes which sport is first: each
    call probes every game an EARLIER call answered.
    """

    def __init__(self, engine, *, scores_for=None):
        self._engine = engine
        self._scores_for = scores_for or {}
        self.last_requests_used = 0
        self.last_requests_remaining = None  # skips record_odds_api_quota
        self.answered_odds: list[int] = []
        self.answered_scores: list[int] = []
        self.odds_probes: list[dict[int, str]] = []
        self.score_probes: list[dict[int, str]] = []

    async def get_odds(self, sport_key, **kwargs):
        if self.answered_odds:
            self.odds_probes.append(await _probe(self._engine, self.answered_odds))
        for event_id, sport_id in ODDS_GAMES.items():
            if SPORTS[sport_id] == sport_key:
                self.answered_odds.append(event_id)
                return _odds_payload(event_id)
        return []

    async def get_scores(self, sport_key, **kwargs):
        if self.answered_scores:
            self.score_probes.append(await _probe(self._engine, self.answered_scores))
        for event_id, payload in self._scores_for.items():
            if SPORTS[SCORE_GAMES[event_id]] == sport_key:
                self.answered_scores.append(event_id)
                return payload
        return []

    async def close(self):
        return None


def _wire(monkeypatch, engine, module, service):
    """Point one pass's module at this engine, this client, no Redis, no quota."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models import Event
    from app.services import event_registry

    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _session():
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _seeded_event(session, identity):
        event_id = int(identity.claim.source_id.rsplit("-", 1)[1])
        return await session.get(Event, event_id), False

    def _no_redis():
        raise RuntimeError("no redis in this gate")

    monkeypatch.setattr(module, "get_task_session", _session)
    monkeypatch.setattr(module, "OddsAPIService", lambda: service)
    monkeypatch.setattr(module, "check_quota_guard", lambda *a, **k: (True, "ok_test"))
    monkeypatch.setattr(module, "get_redis_client", _no_redis)
    monkeypatch.setattr(event_registry, "find_or_create_event", _seeded_event)


def _neutralise_unscoped_sweeps(monkeypatch):
    from app.tasks import excitement_index, odds_polling

    async def _no_stale_sweep(_session):
        return {"closed": 0, "suspended": 0}

    async def _no_live_gei(_session):
        return 0

    monkeypatch.setattr(odds_polling, "detect_and_close_stale_events", _no_stale_sweep)
    monkeypatch.setattr(excitement_index, "update_live_ei", _no_live_gei)


async def _betting(engine, event_id):
    async with engine.connect() as conn:
        sources = (
            await conn.execute(
                text("SELECT win_probability_sources FROM events WHERE id = :i"),
                {"i": event_id},
            )
        ).scalar_one()
        snaps = (
            await conn.execute(
                text("SELECT count(*) FROM odds_snapshots WHERE event_id = :i"),
                {"i": event_id},
            )
        ).scalar_one()
    return (sources or {}).get("betting"), snaps


# ─────────────────────────────────────────────────────────────────────────────
# The reproducer — each pass, at its next network call
# ─────────────────────────────────────────────────────────────────────────────


async def test_poll_all_odds_releases_a_game_before_the_next_sports_fetch(
    pg_engine, monkeypatch
):
    from app.tasks import odds_polling

    service = _ProbingOddsAPI(pg_engine)
    _wire(monkeypatch, pg_engine, odds_polling, service)
    _neutralise_unscoped_sweeps(monkeypatch)

    await odds_polling._poll_all_odds()

    # CONTROL: the probe ran with a game in hand, and that game WAS written —
    # a pass that never updated the row would read "free" for the wrong reason.
    assert service.odds_probes, "the second sport was never fetched — probe never ran"
    first = service.answered_odds[0]
    betting, snaps = await _betting(pg_engine, first)
    assert betting is not None and snaps == len(BOOKS), (first, betting, snaps)

    assert all(v == "free" for p in service.odds_probes for v in p.values()), (
        f"poll_all_odds held a finished game's events row across the next "
        f"sport's fetch: {service.odds_probes!r} (#837)"
    )


async def test_discover_events_releases_a_game_before_the_next_sports_fetch(
    pg_engine, monkeypatch
):
    """The measured holder. Same probe, the other pass."""
    from app.tasks import sports

    service = _ProbingOddsAPI(pg_engine)
    _wire(monkeypatch, pg_engine, sports, service)

    await sports._discover_events()

    assert service.odds_probes, "the second sport was never fetched — probe never ran"
    first = service.answered_odds[0]
    betting, snaps = await _betting(pg_engine, first)
    assert betting is not None and snaps == len(BOOKS), (first, betting, snaps)

    assert all(v == "free" for p in service.odds_probes for v in p.values()), (
        f"discover_events held a finished game's events row across the next "
        f"sport's fetch: {service.odds_probes!r} — this is the 03:05:27–03:06:35Z "
        "holder (#837)"
    )


async def test_the_scores_loop_releases_a_sport_before_the_next_sports_fetch(
    pg_engine, monkeypatch
):
    """Scores for ONE sport's finished game; the probe runs at the other's fetch."""
    from app.tasks import odds_polling

    async with pg_engine.connect() as conn:
        commence = (
            await conn.execute(
                text("SELECT commence_time FROM events WHERE id = 993721")
            )
        ).scalar_one()

    # Both sports answer (so either order reaches a probe); only the first one
    # asked is written, because each finished game gets its own payload.
    service = _ProbingOddsAPI(
        pg_engine,
        scores_for={
            993721: _score_payload(993721, commence),
            993722: _score_payload(993722, commence),
        },
    )
    _wire(monkeypatch, pg_engine, odds_polling, service)
    _neutralise_unscoped_sweeps(monkeypatch)

    await odds_polling._poll_all_odds()

    assert service.score_probes, "the second sport's scores were never fetched"
    first = service.answered_scores[0]
    async with pg_engine.connect() as conn:
        written = (
            await conn.execute(
                text("SELECT home_score, away_score FROM events WHERE id = :i"),
                {"i": first},
            )
        ).one()
    assert tuple(written) == (5, 2), f"control: game {first} was not scored: {written}"

    assert all(v == "free" for p in service.score_probes for v in p.values()), (
        f"the scores loop held a scored game's row across the next sport's "
        f"fetch: {service.score_probes!r} (#837)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# One sport's failed statement no longer takes the sports after it down
# ─────────────────────────────────────────────────────────────────────────────


def _fail_the_first_sport(monkeypatch, module_with_ingest):
    """Wrap `_ingest_event_odds` so the FIRST game ingested raises a real error.

    Stateful rather than keyed on a sport, for the heap-order reason above.
    """
    from app.tasks import odds_polling

    real = odds_polling._ingest_event_odds
    failed: list[int] = []

    async def _ingest(session, event, *args, **kwargs):
        if not failed:
            failed.append(event.id)
            await session.execute(text("SELECT 1/0"))
        return await real(session, event, *args, **kwargs)

    monkeypatch.setattr(module_with_ingest, "_ingest_event_odds", _ingest)
    return failed


async def test_poll_all_odds_keeps_polling_after_one_sports_database_error(
    pg_engine, monkeypatch
):
    from app.tasks import odds_polling

    service = _ProbingOddsAPI(pg_engine)
    _wire(monkeypatch, pg_engine, odds_polling, service)
    _neutralise_unscoped_sweeps(monkeypatch)
    failed = _fail_the_first_sport(monkeypatch, odds_polling)

    await odds_polling._poll_all_odds()  # must not raise

    assert failed and len(service.answered_odds) == 2, (failed, service.answered_odds)
    (survivor,) = [e for e in service.answered_odds if e != failed[0]]
    betting, snaps = await _betting(pg_engine, survivor)
    assert betting is not None and snaps == len(BOOKS), (
        f"game {survivor} (the sport AFTER the failure) was not written: "
        f"betting={betting!r}, snapshots={snaps} — the aborted transaction "
        "reached it (#837)"
    )


async def test_discover_events_keeps_polling_after_one_sports_database_error(
    pg_engine, monkeypatch
):
    """Also proves the gotcha-#6 half: the loop reads plain (id, key) pairs, so
    the rollback's expiry cannot reach the next iteration's sport."""
    from app.tasks import odds_polling, sports

    service = _ProbingOddsAPI(pg_engine)
    _wire(monkeypatch, pg_engine, sports, service)
    failed = _fail_the_first_sport(monkeypatch, odds_polling)

    await sports._discover_events()  # must not raise

    assert failed and len(service.answered_odds) == 2, (failed, service.answered_odds)
    (survivor,) = [e for e in service.answered_odds if e != failed[0]]
    betting, snaps = await _betting(pg_engine, survivor)
    assert betting is not None and snaps == len(BOOKS), (
        f"game {survivor} (the sport AFTER the failure) was not written: "
        f"betting={betting!r}, snapshots={snaps} (#837)"
    )
