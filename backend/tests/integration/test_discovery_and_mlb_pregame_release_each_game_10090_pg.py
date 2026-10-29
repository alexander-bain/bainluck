"""#10090: discovery and the MLB pre-game poll release each game before the next.

WHAT PRODUCTION RECORDED
------------------------
Speed's lock watch, 2026-10-29 04:08Z: one backend from the background worker
was a holder, ``xact_start`` 04:08:47.25, still in the same transaction at
04:08:49 and 04:08:52. Its statements were ``odds_snapshots`` dedup writes and
``SELECT teams.name, teams.id FROM teams WHERE sport_id AND name IN (…)``. That
team lookup exists in ``app/`` only inside ``_discover_events``.

``_discover_events`` committed once per SPORT. Inside a sport,
``_ingest_event_odds`` stamps ``betting`` on game N's ``events`` row (its last
write), and the same transaction then ran games N+1…'s registry lookups and
snapshot bookkeeping, then the team block (team creates, the team lookup, the
team-id links on up to 200 ``events`` rows) and the audit read. Game N's row
lock was held for all of it, and its betting frame was not published until the
whole pass ended. ``_poll_mlb_pregame`` had the same shape over its slate,
without the team block. ``_poll_all_odds`` already commits per game (the
sibling ``test_a_poll_releases_each_game_before_the_next_games_snapshots_10090_pg``).

WHAT THIS FILE DRIVES
---------------------
The real tasks over real Postgres rows: one sport, two live games A then B,
four books each. A second connection holds one row ``FOR UPDATE`` so the pass
blocks on a real lock at a known point, and the file waits until
``pg_blocking_pids`` says so. No sleep stands in for the cause. While the pass
is blocked, a third connection tries the venue stamp's own lock on the games'
``events`` rows under the stamp's 500 ms ``lock_timeout``.

* ``test_the_probe_can_see_a_held_row``: control. The probe reads ``locked`` on
  a row a foreign transaction really holds.
* ``test_discovery_releases_a_game_before_the_next_games_bookkeeping``: the
  pass is blocked in game B's snapshot bookkeeping. Game A's row is free and A's
  betting frame is already published.
* ``test_discovery_releases_every_game_before_the_team_block``: the pass is
  blocked in the team block, linking an unlinked row. Both games' rows are free
  and both frames are published.
* ``test_the_snapshot_cache_survives_the_per_game_commit``: the payload lists
  game A twice, so the second listing reads the first listing's snapshots out
  of ``snapshot_cache`` AFTER A's commit. With the task session's
  ``expire_on_commit=False`` the second reading lands; the control arm runs the
  same pass on a session that expires on commit and the second reading is lost,
  so the cache really is read across the commit.
* ``test_a_failed_game_rolls_back_alone_and_publishes_nothing``: B fails after
  all of its writes. B's writes roll back and its frame is never sent; A's
  committed writes stand and A is published exactly once. This is the one
  behaviour that moves on purpose: on the parent, B's error also rolled back A.
* ``test_mlb_pregame_releases_a_game_before_the_next_games_bookkeeping``: the
  pre-game poll, blocked in game B's bookkeeping, has released game A. Its
  games are scheduled, so it publishes no frames; the lock is the whole ship.

Every arm checks snapshot counts and ``betting_book_count`` so a "free" row can
never come from a pass that simply wrote less.
"""

import asyncio
import contextlib
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #10090 discovery / "
            "MLB pre-game per-game commit gate (CI job `search-recall` provides one)"
        ),
    ),
]

#: The stamp's own bound (PR #8490).
STAMP_LOCK_TIMEOUT = "500ms"

NFL = "americanfootball_nfl"
MLB = "baseball_mlb"
SPORT_IDS = {NFL: 995701, MLB: 995702}
GAMES = {
    NFL: (
        {"event_id": 995711, "home": "Atlanta Falcons D10090", "away": "Baltimore Ravens D10090",
         "team_ids": (995721, 995722)},
        {"event_id": 995712, "home": "Denver Broncos D10090", "away": "Los Angeles Chargers D10090",
         "team_ids": (995723, 995724)},
    ),
    MLB: (
        {"event_id": 995714, "home": "Atlanta Braves P10090", "away": "Boston Red Sox P10090",
         "team_ids": (995725, 995726)},
        {"event_id": 995715, "home": "Detroit Tigers P10090", "away": "Seattle Mariners P10090",
         "team_ids": (995727, 995728)},
    ),
}
#: An NFL row the team block links: names it knows, team ids it lacks.
UNLINKED = 995713
EVENT_IDS = [g["event_id"] for gs in GAMES.values() for g in gs] + [UNLINKED]
TEAM_IDS = [t for gs in GAMES.values() for g in gs for t in g["team_ids"]]
BOOKS = ("draftkings", "fanduel", "betmgm", "caesars")


def _external_id(event_id: int) -> str:
    return f"odds-10090-disc-{event_id}"


def _ids(sport_key):
    a, b = (g["event_id"] for g in GAMES[sport_key])
    return a, b


@pytest.fixture
async def pg_engine():
    """Real schema with ``checkfirst``; only this file's id block is removed."""
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    tables = [
        Base.metadata.tables[name]
        for name in (
            "sports", "teams", "venues", "events", "odds_snapshots",
            "event_provider_anchors", "team_identity_mapping",
            "futures_markets", "futures_outcomes", "win_prob_snapshots",
            "owed_chart_points", "score_snapshots",
        )
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)
        await _clear(conn)
    yield engine
    async with engine.begin() as conn:
        await _clear(conn)
    await engine.dispose()


async def _clear(conn):
    for table in ("owed_chart_points", "win_prob_snapshots", "odds_snapshots",
                  "event_provider_anchors"):
        await conn.execute(
            text(f"DELETE FROM {table} WHERE event_id = ANY(:ids)"), {"ids": EVENT_IDS}
        )
    await conn.execute(text("DELETE FROM events WHERE id = ANY(:ids)"), {"ids": EVENT_IDS})
    await conn.execute(
        text("DELETE FROM team_identity_mapping WHERE team_id = ANY(:ids)"), {"ids": TEAM_IDS}
    )
    await conn.execute(text("DELETE FROM teams WHERE id = ANY(:ids)"), {"ids": TEAM_IDS})
    await conn.execute(
        text("DELETE FROM sports WHERE id = ANY(:ids)"), {"ids": list(SPORT_IDS.values())}
    )


def _commence(sport_key, anchor):
    # NFL: live, started 30 minutes ago. MLB: inside the pre-game T-48h..T-2h
    # window and outside the main loop's ±6h, so the pre-game task runs.
    return anchor - timedelta(minutes=30) if sport_key == NFL else anchor + timedelta(hours=10)


async def _seed(conn, anchor, sport_key, *, unlinked=False):
    """Two games of ``sport_key``; optionally the unlinked NFL row.

    ``sports`` is reused by key when the shared CI database already has it (the
    #837 gate explains why the serial must not fire there).
    """
    sport_id = (
        await conn.execute(text("SELECT id FROM sports WHERE key = :k"), {"k": sport_key})
    ).scalar_one_or_none()
    if sport_id is None:
        sport_id = SPORT_IDS[sport_key]
        await conn.execute(
            text("INSERT INTO sports (id, key, name, active) VALUES (:i, :k, :k, true)"),
            {"i": sport_id, "k": sport_key},
        )
    else:
        await conn.execute(text("UPDATE sports SET active = true WHERE id = :i"), {"i": sport_id})
    status = "live" if sport_key == NFL else "scheduled"
    for game in GAMES[sport_key]:
        home_id, away_id = game["team_ids"]
        for team_id, name in ((home_id, game["home"]), (away_id, game["away"])):
            await conn.execute(
                text("INSERT INTO teams (id, sport_id, name) VALUES (:i, :s, :n)"),
                {"i": team_id, "s": sport_id, "n": name},
            )
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, external_id, home_team_id, "
                "away_team_id, home_team_name, away_team_name, commence_time, "
                "status) VALUES (:i, :s, :x, :ht, :at, :h, :a, :c, :st)"
            ),
            {
                "i": game["event_id"], "s": sport_id, "x": _external_id(game["event_id"]),
                "ht": home_id, "at": away_id, "h": game["home"], "a": game["away"],
                "c": _commence(sport_key, anchor), "st": status,
            },
        )
    if unlinked:
        a, b = GAMES[NFL]
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, external_id, home_team_name, "
                "away_team_name, commence_time, status) "
                "VALUES (:i, :s, :x, :h, :a, :c, 'scheduled')"
            ),
            {"i": UNLINKED, "s": sport_id, "x": _external_id(UNLINKED),
             "h": a["home"], "a": b["away"], "c": anchor + timedelta(days=2)},
        )


def _odds_payload(sport_key, anchor, *, order=None):
    """One odds response; four books agreeing at -150/+130 on every game.

    Four agreeing books clear BETTING_BOOK_FLOOR and are no split market, so
    each game really receives the ``betting`` write whose lock is the subject.
    """
    games = {g["event_id"]: g for g in GAMES[sport_key]}
    return [
        {
            "id": _external_id(event_id),
            "sport_key": sport_key,
            "commence_time": _commence(sport_key, anchor).isoformat().replace("+00:00", "Z"),
            "home_team": games[event_id]["home"],
            "away_team": games[event_id]["away"],
            "bookmakers": [
                {
                    "key": book,
                    "title": book,
                    "markets": [{
                        "key": "h2h",
                        "outcomes": [
                            {"name": games[event_id]["home"], "price": -150},
                            {"name": games[event_id]["away"], "price": 130},
                        ],
                    }],
                }
                for book in BOOKS
            ],
        }
        for event_id in (order or list(games))
    ]


class _OddsService:
    """Answers one sport with the fixed payload; every other sport is empty."""

    def __init__(self, sport_key, payload):
        self._sport_key = sport_key
        self._payload = payload
        self.last_requests_used = 0
        self.last_requests_remaining = None  # skips record_odds_api_quota → Redis

    async def get_odds(self, sport_key, **kwargs):
        return self._payload if sport_key == self._sport_key else []

    async def close(self):
        return None


class _NoESPN:
    async def get_scoreboard(self, *args, **kwargs):
        return []

    async def close(self):
        return None


def _session_factory(engine, *, expire_on_commit=False):
    """`get_task_session`'s shape: commit, then publish what the commit confirmed."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.utils.nonvenue_live_push import publish_committed_nonvenue_frames

    maker = async_sessionmaker(engine, expire_on_commit=expire_on_commit)

    @contextlib.asynccontextmanager
    async def _session(**_kwargs):
        async with maker() as session:
            try:
                yield session
                await session.commit()
                await publish_committed_nonvenue_frames(session)
            except Exception:
                await session.rollback()
                raise

    return _session


def _wire(monkeypatch, engine, *, expire_on_commit=False):
    """Both tasks, minus network, Redis and the quota guard. Returns published frames."""
    from app.services import espn_api
    from app.tasks import odds_polling, redis_state, sports
    from app.utils import nonvenue_live_push

    def _no_redis():
        raise RuntimeError("no redis in this gate")

    published: list[dict] = []

    async def _publish_frame(_redis, frame):
        published.append(frame)
        return True

    class _Redis:
        async def aclose(self):
            return None

    factory = _session_factory(engine, expire_on_commit=expire_on_commit)
    for module in (sports, odds_polling):
        monkeypatch.setattr(module, "get_task_session", factory)
        monkeypatch.setattr(module, "check_quota_guard", lambda *a, **k: (True, "ok_test"))
        monkeypatch.setattr(module, "get_redis_client", _no_redis)
    monkeypatch.setattr(espn_api, "ESPNAPIService", _NoESPN)
    monkeypatch.setattr(nonvenue_live_push, "publish_frame", _publish_frame)
    monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: _Redis())
    return published


async def _discover(monkeypatch, service):
    from app.tasks import sports

    monkeypatch.setattr(sports, "OddsAPIService", lambda: service)
    return await sports._discover_events()


async def _pregame(monkeypatch, service):
    from app.tasks import odds_polling

    monkeypatch.setattr(odds_polling, "OddsAPIService", lambda: service)
    return await odds_polling._poll_mlb_pregame()


async def _snapshots(engine, event_id):
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT bookmaker, reading_count FROM odds_snapshots "
                    "WHERE event_id = :i ORDER BY bookmaker"
                ),
                {"i": event_id},
            )
        ).all()


async def _readings(engine, event_id):
    return [r.reading_count for r in await _snapshots(engine, event_id)]


async def _sources(engine, event_id) -> dict:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text("SELECT win_probability_sources FROM events WHERE id = :i"),
                {"i": event_id},
            )
        ).scalar_one() or {}


async def _probe(engine, event_id):
    """Try the stamp's lock on one row under the stamp's timeout; never write."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text(f"SET LOCAL lock_timeout = '{STAMP_LOCK_TIMEOUT}'"))
            await conn.execute(
                text(
                    "UPDATE events SET win_probability_sources = win_probability_sources "
                    "WHERE id = :i"
                ),
                {"i": event_id},
            )
            return "free"
        except DBAPIError as exc:
            orig = getattr(exc, "orig", None)
            code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
            if code == "55P03" or "LockNotAvailable" in repr(orig) or "lock timeout" in str(exc):
                return "locked"
            raise
        finally:
            await trans.rollback()


@contextlib.asynccontextmanager
async def _hold(engine, sql, params):
    """A second transaction holding the selected row ``FOR UPDATE``. Yields its pid."""
    async with engine.connect() as holder:
        trans = await holder.begin()
        pid = (await holder.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        assert (await holder.execute(text(sql + " FOR UPDATE"), params)).first() is not None
        try:
            yield pid
        finally:
            await trans.commit()


async def _wait_until_blocked_by(engine, holder_pid, task, *, timeout_s=30.0):
    """Return the waiting statement once a backend is blocked by ``holder_pid``."""
    deadline = time.monotonic() + timeout_s
    async with engine.connect() as conn:
        while time.monotonic() < deadline:
            if task.done():
                await task  # surface the pass's own error
                pytest.fail("the pass finished without ever blocking on the held row")
            row = (
                await conn.execute(
                    text(
                        "SELECT query FROM pg_stat_activity "
                        "WHERE :h = ANY(pg_blocking_pids(pid))"
                    ),
                    {"h": holder_pid},
                )
            ).first()
            await conn.rollback()
            if row is not None:
                return row.query
            await asyncio.sleep(0.02)
    pytest.fail(f"no backend blocked on the held row within {timeout_s}s")


async def _warm(engine, monkeypatch, sport_key, run):
    """Seed, then one unobstructed pass: every book has its snapshot row."""
    anchor = datetime.now(timezone.utc)
    async with engine.begin() as conn:
        await _seed(conn, anchor, sport_key)
    service = _OddsService(sport_key, _odds_payload(sport_key, anchor))
    published = _wire(monkeypatch, engine)
    first = await run(monkeypatch, service)
    assert first["snapshots"] == 2 * len(BOOKS), first
    for event_id in _ids(sport_key):
        assert await _readings(engine, event_id) == [1] * len(BOOKS)
    published.clear()
    return service, published


SNAPSHOT_ROW = (
    "SELECT id FROM odds_snapshots WHERE event_id = :e AND bookmaker = :b"
)


async def _blocked_in_game_b(engine, monkeypatch, sport_key, run):
    """Warm, then a second pass blocked in game B's first book. Probes game A."""
    game_a, game_b = _ids(sport_key)
    service, published = await _warm(engine, monkeypatch, sport_key, run)
    async with _hold(engine, SNAPSHOT_ROW, {"e": game_b, "b": BOOKS[0]}) as holder_pid:
        task = asyncio.create_task(run(monkeypatch, service))
        waiting = await _wait_until_blocked_by(engine, holder_pid, task)
        verdict = await _probe(engine, game_a)
        published_while_blocked = [(f["event_id"], f["source"]) for f in published]
    result = await asyncio.wait_for(task, 60)
    return waiting, verdict, published_while_blocked, result, published


async def _assert_both_games_written(engine, sport_key, result, readings):
    assert result["snapshots"] == 2 * len(BOOKS), result
    for event_id in _ids(sport_key):
        rows = await _snapshots(engine, event_id)
        assert [r.bookmaker for r in rows] == sorted(BOOKS)
        assert [r.reading_count for r in rows] == [readings] * len(BOOKS), (event_id, rows)
        sources = await _sources(engine, event_id)
        assert sources.get("betting_book_count") == len(BOOKS), sources
        assert sources["betting"]["value"] == pytest.approx(0.58, abs=0.01), sources


async def test_the_probe_can_see_a_held_row(pg_engine):
    anchor = datetime.now(timezone.utc)
    async with pg_engine.begin() as conn:
        await _seed(conn, anchor, NFL)
    game_a, _ = _ids(NFL)
    async with _hold(pg_engine, "SELECT id FROM events WHERE id = :i", {"i": game_a}):
        assert await _probe(pg_engine, game_a) == "locked"
    assert await _probe(pg_engine, game_a) == "free"


async def test_discovery_releases_a_game_before_the_next_games_bookkeeping(
    pg_engine, monkeypatch
):
    game_a, _ = _ids(NFL)
    waiting, verdict, published_mid, result, published = await _blocked_in_game_b(
        pg_engine, monkeypatch, NFL, _discover
    )
    # The pass is inside game B's snapshot bookkeeping.
    assert waiting.lstrip().upper().startswith("UPDATE ODDS_SNAPSHOTS"), waiting
    assert verdict == "free", (
        "game A's row was still locked while discovery was blocked in game B's "
        "snapshot bookkeeping. Discovery holds A's `betting` write until the end of "
        "the sport, so the venue stamp gives up at 500 ms and re-queues (#10090)."
    )
    assert published_mid == [(game_a, "betting")], (
        f"game A's betting frame was not published while game B was blocked "
        f"({published_mid}): discovery publishes only at the end of the pass."
    )
    await _assert_both_games_written(pg_engine, NFL, result, readings=2)
    # Each committed game's frame is published exactly once.
    assert sorted(f["event_id"] for f in published) == sorted(_ids(NFL)), published


async def test_discovery_releases_every_game_before_the_team_block(pg_engine, monkeypatch):
    anchor = datetime.now(timezone.utc)
    async with pg_engine.begin() as conn:
        await _seed(conn, anchor, NFL, unlinked=True)
    published = _wire(monkeypatch, pg_engine)
    service = _OddsService(NFL, _odds_payload(NFL, anchor))
    games = _ids(NFL)

    async with _hold(pg_engine, "SELECT id FROM events WHERE id = :i", {"i": UNLINKED}) as pid:
        task = asyncio.create_task(_discover(monkeypatch, service))
        waiting = await _wait_until_blocked_by(pg_engine, pid, task)
        verdicts = {event_id: await _probe(pg_engine, event_id) for event_id in games}
        published_mid = sorted(f["event_id"] for f in published)
    result = await asyncio.wait_for(task, 60)

    # The pass is in the team block, linking the unlinked row.
    assert waiting.lstrip().upper().startswith("UPDATE EVENTS"), waiting
    assert "home_team_id" in waiting, waiting
    assert verdicts == {event_id: "free" for event_id in games}, (
        f"while discovery's team block waited on the unlinked row, the games' rows "
        f"read {verdicts}. The team block ran inside the games' transaction, so "
        "every game's `betting` write stayed locked behind it (#10090)."
    )
    assert published_mid == sorted(games), published_mid
    await _assert_both_games_written(pg_engine, NFL, result, readings=1)
    # The team block still did its job once it got the row.
    async with pg_engine.connect() as conn:
        linked = (await conn.execute(
            text("SELECT home_team_id, away_team_id FROM events WHERE id = :i"),
            {"i": UNLINKED},
        )).one()
    a, b = GAMES[NFL]
    assert tuple(linked) == (a["team_ids"][0], b["team_ids"][1]), linked


@pytest.mark.parametrize("expire_on_commit", [False, True])
async def test_the_snapshot_cache_survives_the_per_game_commit(
    pg_engine, monkeypatch, caplog, expire_on_commit
):
    """The payload lists game A twice; its second listing reads the cache after A's commit."""
    anchor = datetime.now(timezone.utc)
    async with pg_engine.begin() as conn:
        await _seed(conn, anchor, NFL)
    game_a, _ = _ids(NFL)
    _wire(monkeypatch, pg_engine, expire_on_commit=expire_on_commit)
    service = _OddsService(NFL, _odds_payload(NFL, anchor, order=[game_a, game_a]))

    with caplog.at_level(logging.WARNING, logger="app.tasks.sports"):
        await _discover(monkeypatch, service)
    failures = [r.getMessage() for r in caplog.records if "Error discovering" in r.getMessage()]

    if not expire_on_commit:
        # The task session's setting: the first listing created four rows and
        # committed; the second read them from the cache and counted a reading.
        assert failures == [], failures
        assert await _readings(pg_engine, game_a) == [2] * len(BOOKS)
    else:
        # Control: on a session that expires on commit, the cached rows are
        # expired and reading them is IO the async session cannot do. The
        # second listing fails, so this arm proves the head arm really read the
        # cache across the commit.
        assert len(failures) == 1 and "greenlet" in failures[0].lower(), failures
        assert await _readings(pg_engine, game_a) == [1] * len(BOOKS)


async def test_a_failed_game_rolls_back_alone_and_publishes_nothing(pg_engine, monkeypatch):
    """Game B fails after ALL of its own writes; only those writes are undone."""
    from app.tasks import odds_polling

    game_a, game_b = _ids(NFL)
    service, published = await _warm(pg_engine, monkeypatch, NFL, _discover)
    before_b = await _sources(pg_engine, game_b)

    real = odds_polling._ingest_event_odds
    published_before_b: list[list[int]] = []

    async def _ingest(session, event, *args, **kwargs):
        if event.id == game_b:
            published_before_b.append([f["event_id"] for f in published])
        processed = await real(session, event, *args, **kwargs)
        if event.id == game_b:
            await session.execute(text("SELECT 1/0"))  # a real error, aborting the txn
        return processed

    monkeypatch.setattr(odds_polling, "_ingest_event_odds", _ingest)
    await _discover(monkeypatch, service)  # must not raise

    assert published_before_b == [[game_a]], published_before_b
    assert await _readings(pg_engine, game_b) == [1] * len(BOOKS)
    assert await _sources(pg_engine, game_b) == before_b
    assert await _readings(pg_engine, game_a) == [2] * len(BOOKS)
    assert [f["event_id"] for f in published] == [game_a], published


async def test_mlb_pregame_releases_a_game_before_the_next_games_bookkeeping(
    pg_engine, monkeypatch
):
    game_a, _ = _ids(MLB)
    waiting, verdict, published_mid, result, published = await _blocked_in_game_b(
        pg_engine, monkeypatch, MLB, _pregame
    )
    assert waiting.lstrip().upper().startswith("UPDATE ODDS_SNAPSHOTS"), waiting
    assert verdict == "free", (
        "game A's row was still locked while the MLB pre-game poll was blocked in "
        "game B's snapshot bookkeeping: the slate is one transaction (#10090)."
    )
    # Pre-game rows are `scheduled`, and a nonvenue frame is built only for a
    # live game, so this pass publishes nothing; the row lock is its whole ship.
    assert published_mid == [] and published == [], published
    await _assert_both_games_written(pg_engine, MLB, result, readings=2)


async def test_the_team_block_reads_team_ids_from_the_table_not_the_identity_map(
    pg_engine, monkeypatch
):
    """A row linked by another writer after its game's commit keeps that link.

    The unlinked row is itself a listed game, so the registry loads it into the
    session with both team ids empty. After its per-game commit (and before the
    team block), another writer links its home side. The team block must read
    that from the table: the row the session cached still says "unlinked".
    """
    from app.utils import nonvenue_live_push

    anchor = datetime.now(timezone.utc)
    async with pg_engine.begin() as conn:
        await _seed(conn, anchor, NFL, unlinked=True)
    _wire(monkeypatch, pg_engine)
    a, b = GAMES[NFL]
    other_writer_home = b["team_ids"][0]  # not the id the team block would choose
    listing = _odds_payload(NFL, anchor)[0] | {
        "id": _external_id(UNLINKED),
        "commence_time": (anchor + timedelta(days=2)).isoformat().replace("+00:00", "Z"),
        "home_team": a["home"],
        "away_team": b["away"],
    }
    listing["bookmakers"] = [
        {**bk, "markets": [{"key": "h2h", "outcomes": [
            {"name": a["home"], "price": -150}, {"name": b["away"], "price": 130},
        ]}]}
        for bk in listing["bookmakers"]
    ]
    service = _OddsService(NFL, [listing])

    real_publish = nonvenue_live_push.publish_committed_nonvenue_frames
    linked_by_other: list[int] = []

    async def _publish_then_other_writer(session):
        await real_publish(session)
        if linked_by_other:
            return
        # Bounded: if the pass still holds the row, this writer would wait on
        # it from the pass's own event loop forever. It records the hold instead.
        try:
            async with pg_engine.begin() as conn:
                await conn.execute(text(f"SET LOCAL lock_timeout = '{STAMP_LOCK_TIMEOUT}'"))
                await conn.execute(
                    text("UPDATE events SET home_team_id = :t WHERE id = :i"),
                    {"t": other_writer_home, "i": UNLINKED},
                )
            linked_by_other.append(UNLINKED)
        except DBAPIError:
            linked_by_other.append("row still held by the pass")

    monkeypatch.setattr(
        nonvenue_live_push, "publish_committed_nonvenue_frames", _publish_then_other_writer
    )
    result = await _discover(monkeypatch, service)

    assert linked_by_other == [UNLINKED], (
        f"the other writer could not link the row after its game's commit "
        f"({linked_by_other}): the pass had not released it before the team block."
    )
    assert result["snapshots"] == len(BOOKS), result
    async with pg_engine.connect() as conn:
        linked = (await conn.execute(
            text("SELECT home_team_id, away_team_id FROM events WHERE id = :i"),
            {"i": UNLINKED},
        )).one()
    assert tuple(linked) == (other_writer_home, b["team_ids"][1]), (
        f"the team block overwrote another writer's home link ({linked}): it read the "
        "row the session cached before the game's commit, not the table (#10090)."
    )
