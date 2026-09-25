"""#837, the three gaps the per-sport commit left: rollback, the (id, key) loop, scores.

`test_a_poll_releases_its_event_rows_per_sport_837_pg.py` proves both odds passes
commit at the end of each sport. This file proves what that commit alone does NOT:

1. A FAILED SPORT NO LONGER TAKES THE SPORTS AFTER IT DOWN. Production: at
   03:05:27Z `poll_all_odds[be29398d]` lost a 40P01 to discovery's transaction;
   the per-sport `except` logged and `continue`d with the transaction still
   aborted, so every later sport hit PendingRollbackError and the pass died.
   Both passes now roll back in the per-sport `except`. The failure injected
   here is a real Postgres error (`division_by_zero`), not a mock, because what
   matters is what the ABORTED TRANSACTION does to the next statement.
2. THE DISCOVER LOOP READS PLAIN (id, key) PAIRS. The rollback expires every
   ORM row in the session (gotcha #6); reading `sport.key` off an expired
   `Sport` next iteration lazy-loads outside a greenlet (MissingGreenlet) and
   kills the whole pass. The discover rollback arm fails on that mutant.
3. THE SCORES LOOP RELEASES EACH SPORT before the next sport's `get_scores`
   call, as the odds loop does.

Measured by latency's rig on 16872be6c1 (the per-sport commit alone): all three
arms fail; with the fix, all pass.

The probe: the fake odds client, at every network call, tries `SELECT ... FOR
UPDATE` under a 300 ms `lock_timeout` from a SECOND connection on every game an
earlier call already answered. `test_the_probe_can_see_a_held_row` is its
positive control.

WHAT IS NOT HERE: the registry (`find_or_create_event` is a lookup of the seeded
row — matching is not the subject), and the stale sweep and live GEI update
(unscoped: they sweep every `live` row on a CI database shared across the
`search-recall` job). Sport keys are invented (`test837_*`) so no sibling step's
rows join either pass and the ESPN schedule branch never makes a network call.
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

SPORTS = {993801: "test837_alpha", 993802: "test837_beta"}

# One upcoming game per sport (the odds loops) and one finished, unanchored game
# per sport (the scores loop). Ids are this file's own block.
ODDS_GAMES = {993811: 993801, 993812: 993802}
SCORE_GAMES = {993821: 993801, 993822: 993802}
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
# The probe's positive control
# ─────────────────────────────────────────────────────────────────────────────


async def test_the_probe_can_see_a_held_row(pg_engine):
    """A row another transaction holds reads ``held``; released, it reads ``free``.

    Without this, every "free" below could be a probe that cannot see a lock.
    """
    event_id = next(iter(SCORE_GAMES))
    async with pg_engine.connect() as holder:
        trans = await holder.begin()
        await holder.execute(
            text("UPDATE events SET status = status WHERE id = :i"), {"i": event_id}
        )
        assert await _probe(pg_engine, [event_id]) == {event_id: "held"}
        await trans.rollback()
    assert await _probe(pg_engine, [event_id]) == {event_id: "free"}


# ─────────────────────────────────────────────────────────────────────────────
# The scores loop, at its next network call
# ─────────────────────────────────────────────────────────────────────────────


async def test_the_scores_loop_releases_a_sport_before_the_next_sports_fetch(
    pg_engine, monkeypatch
):
    """Scores for ONE sport's finished game; the probe runs at the other's fetch."""
    from app.tasks import odds_polling

    async with pg_engine.connect() as conn:
        commence = (
            await conn.execute(
                text("SELECT commence_time FROM events WHERE id = 993821")
            )
        ).scalar_one()

    # Both sports answer (so either order reaches a probe); only the first one
    # asked is written, because each finished game gets its own payload.
    service = _ProbingOddsAPI(
        pg_engine,
        scores_for={
            993821: _score_payload(993821, commence),
            993822: _score_payload(993822, commence),
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
