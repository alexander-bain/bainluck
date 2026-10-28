"""#10090: an odds pass commits and publishes a live game before the NEXT game's bookkeeping.

WHAT PRODUCTION RECORDED, AND WHAT IT DOES NOT PROVE
----------------------------------------------------
Alex's screenshot on 2026-10-12: BAL @ ATL (event 14780557), Q4, 23–23, a held
page whose last receipt was 21 s old. The goal owner's bounded lock capture
(``artifacts/live-iteration-goal-20261011/user-21s-14780557/blocking-window.jsonl``)
caught a venue-source ``UPDATE events SET win_probability_sources`` (pid
2661383) waiting on ``transactionid`` behind pid 2662097 at 03:38:29.906863Z.
2662097 was ``idle in transaction`` 1.386 s in, and its last statement was
``UPDATE odds_snapshots SET reading_count=…, valid_until=…``. Separately,
worker-ws logged ``PM event 14780557 row locked >500ms, re-queued`` at
03:38:30.160.

The captured statement carried its event id as a bound parameter (``$8``), so
the capture does NOT show that pid 2661383 was writing event 14780557. The two
records are concurrent and relevant. They are not joined, and nothing here
claims the 1.386 s was that game's delay.

What the source shows: that snapshot-writer shape is ``_poll_all_odds``. #837
made it commit once per SPORT. Inside a sport, ``_ingest_event_odds`` stamps
``betting`` on game N's ``events`` row, and then the same transaction goes on
to games N+1…: registry lookups, snapshot SELECTs, and the autoflushed
``reading_count``/``valid_until`` updates of every book that did not move.
Game N's row lock is held for all of it. Game N's betting frame waited too,
because it was published only after the sport's commit.

WHAT THIS FILE DRIVES
---------------------
The real ``_poll_all_odds`` over real Postgres rows: one sport, two live games A
then B, four books each. A first pass creates every snapshot (production's
steady state). The second pass re-reads the same prices, so each book is the
"values unchanged" bookkeeping branch production was in. Before that pass, a
second connection takes ``FOR UPDATE`` on game B's first snapshot row: a
concurrent snapshot writer (``poll_all_odds`` waited 44.7 s on discovery's
snapshot rows in #837's capture). The pass then blocks on a real lock inside
game B's bookkeeping, and the file waits until ``pg_blocking_pids`` says so.
No sleep stands in for the cause.

While the pass is held there, the REAL ``LiveBlendRefresher`` (Polymarket arm,
production's 500 ms stamp bound) refreshes game A.

* ``test_a_venue_stamp_is_not_held_by_the_next_games_snapshots``: the ship.
  While B's bookkeeping is still blocked, A's committed betting frame has
  already been published, and A's venue stamp lands. Both are read BEFORE the
  blocker is released. On 604c032cc0 (per-game commit, per-sport publish), the
  stamp lands but no betting frame has been published yet. On the per-sport
  commit parent, the stamp also reads ``lock_skipped`` and A is re-queued.
* ``test_the_refresher_bound_binds_in_this_rig``: control. The same refresher
  against a row a foreign transaction really holds reports ``lock_skipped``. A
  rig where the bound never binds would make the ship case vacuous.
* ``test_a_failed_game_rolls_back_alone_and_publishes_nothing``: failure and
  rollback control. Game B raises a real Postgres error AFTER its snapshot
  updates and ``betting`` stamp. Every one of those writes rolls back, and B's
  frame is never published. A's committed writes stand, and A's frame was
  already published before B's ingest began. A is published exactly once. The
  pass finishes. This is the one behaviour the fix moves on purpose: on the
  parent the SPORT was the transaction unit, so B's error also rolled back A's
  already-finished writes. The game is now the transaction unit. The error
  unit is unchanged: a failed game still ends its sport (the ``except`` after
  the game loop), and later sports still run, as #837 established.

Every arm checks snapshot counts and ``betting_book_count`` so that a "free"
row can never come from a pass that simply wrote less.
"""

import asyncio
import contextlib
import os
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #10090 per-game "
            "commit gate (CI job `search-recall` provides one)"
        ),
    ),
]

SPORT_KEY = "americanfootball_nfl"
SPORT_ID = 994701
#: A first, then B: the payload order is the order the pass ingests them.
GAMES = (
    {"event_id": 994711, "home": "Atlanta Falcons 10090", "away": "Baltimore Ravens 10090",
     "team_ids": (994721, 994722)},
    {"event_id": 994712, "home": "Denver Broncos 10090", "away": "Los Angeles Chargers 10090",
     "team_ids": (994723, 994724)},
)
GAME_A, GAME_B = (g["event_id"] for g in GAMES)
EVENT_IDS = [GAME_A, GAME_B]
TEAM_IDS = [t for g in GAMES for t in g["team_ids"]]
MARKET_ID = 994731
BOOKS = ("draftkings", "fanduel", "betmgm", "caesars")


def _external_id(event_id: int) -> str:
    return f"odds-10090-pg-{event_id}"


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
            # #10090 attempt151: a stamp commits its publication intent here.
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
    await conn.execute(text("DELETE FROM score_snapshots WHERE event_id = ANY(:ids)"), {"ids": EVENT_IDS})
    await conn.execute(
        text("DELETE FROM owed_chart_points WHERE event_id = ANY(:ids)"), {"ids": EVENT_IDS}
    )
    # attempt151: another file's leftover publication intents in this shared
    # database are a dead owner's, and recovery discovery is per source, not per
    # event: the arm would republish their controls into the frames pinned here.
    await conn.execute(text(
        "DELETE FROM owed_chart_points "
        "WHERE source IN ('polymarket_price_publish', 'kalshi_price_publish')"
    ))
    await conn.execute(text("DELETE FROM futures_markets WHERE id = :i"), {"i": MARKET_ID})
    await conn.execute(
        text("DELETE FROM win_prob_snapshots WHERE event_id = ANY(:ids)"), {"ids": EVENT_IDS}
    )
    await conn.execute(
        text("DELETE FROM odds_snapshots WHERE event_id = ANY(:ids)"), {"ids": EVENT_IDS}
    )
    await conn.execute(
        text("DELETE FROM event_provider_anchors WHERE event_id = ANY(:ids)"),
        {"ids": EVENT_IDS},
    )
    await conn.execute(text("DELETE FROM events WHERE id = ANY(:ids)"), {"ids": EVENT_IDS})
    await conn.execute(text("DELETE FROM teams WHERE id = ANY(:ids)"), {"ids": TEAM_IDS})
    await conn.execute(text("DELETE FROM sports WHERE id = :i"), {"i": SPORT_ID})


async def _seed(conn, anchor):
    """Two live NFL games started 30 minutes ago, and one Polymarket market on A.

    ``sports`` is reused by key when a sibling step already created it (the
    #837 gate explains why the serial must not fire on the shared CI database).
    """
    sport_id = (
        await conn.execute(text("SELECT id FROM sports WHERE key = :k"), {"k": SPORT_KEY})
    ).scalar_one_or_none()
    if sport_id is None:
        await conn.execute(
            text("INSERT INTO sports (id, key, name, active) VALUES (:i, :k, :k, true)"),
            {"i": SPORT_ID, "k": SPORT_KEY},
        )
        sport_id = SPORT_ID
    else:
        await conn.execute(text("UPDATE sports SET active = true WHERE id = :i"), {"i": sport_id})
    for game in GAMES:
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
                "status) VALUES (:i, :s, :x, :ht, :at, :h, :a, :c, 'live')"
            ),
            {
                "i": game["event_id"], "s": sport_id, "x": _external_id(game["event_id"]),
                "ht": home_id, "at": away_id, "h": game["home"], "a": game["away"],
                "c": anchor - timedelta(minutes=30),
            },
        )
    await conn.execute(
        text(
            "INSERT INTO futures_markets (id, sport_id, event_id, source, external_id, "
            "name, category, mutually_exclusive, status) "
            "VALUES (:i, :s, :e, 'polymarket', :x, :n, 'game', true, 'open')"
        ),
        {"i": MARKET_ID, "s": sport_id, "e": GAME_A, "x": f"pm-10090-{GAME_A}",
         "n": f"game {GAME_A}"},
    )


def _odds_payload(anchor):
    """One NFL odds response: A then B, four books agreeing at -150/+130.

    Four agreeing books clear BETTING_BOOK_FLOOR and are no split market, so
    each game really receives the ``UPDATE events SET win_probability_sources``
    whose lock is the subject.
    """
    return [
        {
            "id": _external_id(game["event_id"]),
            "sport_key": SPORT_KEY,
            "commence_time": (anchor - timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
            "home_team": game["home"],
            "away_team": game["away"],
            "bookmakers": [
                {
                    "key": book,
                    "title": book,
                    "markets": [{
                        "key": "h2h",
                        "outcomes": [
                            {"name": game["home"], "price": -150},
                            {"name": game["away"], "price": 130},
                        ],
                    }],
                }
                for book in BOOKS
            ],
        }
        for game in GAMES
    ]


class _OddsService:
    """Answers our sport with the fixed payload; every other sport is empty."""

    def __init__(self, anchor):
        self._payload = _odds_payload(anchor)
        self.last_requests_used = 0
        self.last_requests_remaining = None  # skips record_odds_api_quota → Redis

    async def get_odds(self, sport_key, **kwargs):
        return self._payload if sport_key == SPORT_KEY else []

    async def get_scores(self, sport_key, **kwargs):
        return []

    async def close(self):
        return None


def _session_factory(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(engine, expire_on_commit=False)

    @contextlib.asynccontextmanager
    async def _session(**_kwargs):
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _session


def _wire(monkeypatch, engine):
    """Production `_poll_all_odds`, minus its network, Redis and unscoped sweeps.

    Returns the list that collects every nonvenue frame the pass publishes.
    """
    from app.tasks import excitement_index, odds_polling, redis_state
    from app.utils import nonvenue_live_push

    async def _zero(*_a, **_k):
        return 0

    async def _no_stale_sweep(_session):
        return {"closed": 0, "suspended": 0}

    def _no_redis():
        raise RuntimeError("no redis in this gate")

    published: list[dict] = []

    async def _publish_frame(_redis, frame):
        published.append(frame)
        return True

    class _Redis:
        async def aclose(self):
            return None

    monkeypatch.setattr(odds_polling, "get_task_session", _session_factory(engine))
    monkeypatch.setattr(odds_polling, "check_quota_guard", lambda *a, **k: (True, "ok_test"))
    monkeypatch.setattr(odds_polling, "get_redis_client", _no_redis)
    monkeypatch.setattr(odds_polling, "detect_and_close_stale_events", _no_stale_sweep)
    monkeypatch.setattr(odds_polling, "update_poll_state", lambda *a, **k: None)
    monkeypatch.setattr(excitement_index, "update_live_ei", _zero)
    monkeypatch.setattr(nonvenue_live_push, "publish_frame", _publish_frame)
    monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: _Redis())
    return published


async def _pass(monkeypatch, service):
    from app.tasks import odds_polling

    monkeypatch.setattr(odds_polling, "OddsAPIService", lambda: service)
    return await odds_polling._poll_all_odds()


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


async def _sources(engine, event_id) -> dict:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text("SELECT win_probability_sources FROM events WHERE id = :i"),
                {"i": event_id},
            )
        ).scalar_one() or {}


async def _warm(engine, monkeypatch):
    """Seed, then one unobstructed pass: every book has its snapshot row."""
    anchor = datetime.now(timezone.utc)
    async with engine.begin() as conn:
        await _seed(conn, anchor)
    service = _OddsService(anchor)
    published = _wire(monkeypatch, engine)
    first = await _pass(monkeypatch, service)
    assert first["snapshots"] == 2 * len(BOOKS), first
    for event_id in EVENT_IDS:
        assert [r.reading_count for r in await _snapshots(engine, event_id)] == [1] * len(BOOKS)
    published.clear()
    return service, published


@contextlib.asynccontextmanager
async def _hold_snapshot_row(engine, event_id, bookmaker):
    """A second transaction holding one snapshot row ``FOR UPDATE``. Yields its pid."""
    async with engine.connect() as holder:
        trans = await holder.begin()
        pid = (await holder.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        await holder.execute(
            text(
                "SELECT id FROM odds_snapshots WHERE event_id = :e AND bookmaker = :b "
                "FOR UPDATE"
            ),
            {"e": event_id, "b": bookmaker},
        )
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
    pytest.fail(f"no backend blocked on the held snapshot row within {timeout_s}s")


def _refresher(monkeypatch, engine):
    """The real Polymarket `LiveBlendRefresher` at production's stamp bound."""
    from app.tasks import live_blend_refresh as lbr
    from app.utils import live_blend

    monkeypatch.setattr(
        live_blend, "compute_source_home_probability",
        lambda group, home, away: SimpleNamespace(home_probability=0.565, eligibility=None),
    )

    @contextlib.asynccontextmanager
    async def _session(**_kwargs):
        from sqlalchemy.ext.asyncio import async_sessionmaker

        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
            await session.commit()

    monkeypatch.setattr("app.tasks.base.get_task_session", _session)

    arm = lbr.LiveBlendRefresher(
        "polymarket", stamp_lock_timeout_ms=lbr.DEFAULT_STAMP_LOCK_TIMEOUT_MS
    )
    frames: list[dict] = []

    async def _oriented(session, event_id, home_prob, *, reading=None, before_fallback=None):
        return home_prob

    async def _publish(batch):
        frames.extend(batch)
        # Acknowledged as Redis does (attempt151): delivered, nothing owed.
        return {(f["event_id"], f["rev"][str(f["event_id"])]) for f in batch}

    arm._oriented = _oriented
    arm._publish = _publish
    arm._last_snapshot_at = {GAME_A: float("inf")}  # no chart point: the stamp is the subject
    return arm, frames


async def test_a_venue_stamp_is_not_held_by_the_next_games_snapshots(pg_engine, monkeypatch):
    service, published = await _warm(pg_engine, monkeypatch)
    arm, frames = _refresher(monkeypatch, pg_engine)

    async with _hold_snapshot_row(pg_engine, GAME_B, BOOKS[0]) as holder_pid:
        task = asyncio.create_task(_pass(monkeypatch, service))
        waiting = await _wait_until_blocked_by(pg_engine, holder_pid, task)
        # The pass is inside game B's bookkeeping, as production's pid was.
        assert waiting.lstrip().upper().startswith("UPDATE ODDS_SNAPSHOTS"), waiting
        sources_mid = await _sources(pg_engine, GAME_A)
        # Read while B is still blocked, before the holder releases its row.
        published_while_b_blocked = list(published)

        started = time.monotonic()
        stats = dict(await asyncio.wait_for(arm.refresh([GAME_A]), 30))
        elapsed = time.monotonic() - started

    result = await asyncio.wait_for(task, 60)

    assert [(f["event_id"], f["source"]) for f in published_while_b_blocked] == [
        (GAME_A, "betting")
    ], (
        f"game A was committed, but its betting frame was not published while game "
        f"B's snapshot bookkeeping was blocked ({published_while_b_blocked}). The "
        "pass publishes only after the whole sport, so a committed probability "
        "waits on later games' bookkeeping (#10090)."
    )
    assert stats["stamped"] == 1 and stats["lock_skipped"] == 0 and stats["errors"] == 0, (
        f"game A's venue stamp could not take its row while the pass was blocked "
        f"in game B's snapshot bookkeeping ({stats}, {elapsed:.2f}s). The pass still "
        "holds A's row from its `betting` write until the end of the sport, so the "
        "stamp gives up at 500 ms and re-queues — production's 03:38:29Z line (#10090)."
    )
    assert [f["event_id"] for f in frames] == [GAME_A]
    assert arm._lock_retry == set()

    # Nothing the pass owes was dropped: both games, every book, one reading more.
    assert result["snapshots"] == 2 * len(BOOKS), result
    for event_id in EVENT_IDS:
        rows = await _snapshots(pg_engine, event_id)
        assert [r.bookmaker for r in rows] == sorted(BOOKS)
        assert [r.reading_count for r in rows] == [2] * len(BOOKS), (event_id, rows)
        sources = await _sources(pg_engine, event_id)
        assert sources.get("betting_book_count") == len(BOOKS), sources
        assert sources["betting"]["value"] == pytest.approx(0.58, abs=0.01), sources
    # A's betting stamp was COMMITTED before B blocked, and the venue stamp
    # survived the pass's later commits beside it.
    assert sources_mid["betting"]["updated_at"] is not None
    final_a = await _sources(pg_engine, GAME_A)
    assert final_a["polymarket"]["value"] == pytest.approx(0.565), final_a
    assert final_a["betting"] == sources_mid["betting"], (sources_mid, final_a)
    # Publication follows commit: one betting frame per committed game, each
    # exactly once (A's early publish is not repeated by the sport-end publish).
    assert sorted(f["event_id"] for f in published) == EVENT_IDS, published
    assert {f["source"] for f in published} == {"betting"}


async def test_the_refresher_bound_binds_in_this_rig(pg_engine, monkeypatch):
    """Control: the same refresher reports ``lock_skipped`` on a row really held."""
    await _warm(pg_engine, monkeypatch)
    arm, frames = _refresher(monkeypatch, pg_engine)

    async with pg_engine.connect() as holder:
        trans = await holder.begin()
        await holder.execute(
            text("SELECT id FROM events WHERE id = :i FOR UPDATE"), {"i": GAME_A}
        )
        stats = dict(await asyncio.wait_for(arm.refresh([GAME_A]), 30))
        await trans.rollback()

    assert stats["lock_skipped"] == 1 and stats["stamped"] == 0, stats
    assert frames == [] and arm._lock_retry == {GAME_A}


async def test_a_failed_game_rolls_back_alone_and_publishes_nothing(pg_engine, monkeypatch):
    """Game B fails after ALL of its own writes; only those writes are undone."""
    from app.tasks import odds_polling

    service, published = await _warm(pg_engine, monkeypatch)
    before_b = await _sources(pg_engine, GAME_B)

    real = odds_polling._ingest_event_odds
    failed: list[int] = []
    published_before_b: list[list[int]] = []

    async def _ingest(session, event, *args, **kwargs):
        if event.id == GAME_B:
            published_before_b.append([f["event_id"] for f in published])
        processed = await real(session, event, *args, **kwargs)
        if event.id == GAME_B:
            failed.append(event.id)
            await session.execute(text("SELECT 1/0"))  # a real error, aborting the txn
        return processed

    monkeypatch.setattr(odds_polling, "_ingest_event_odds", _ingest)
    await _pass(monkeypatch, service)  # must not raise

    assert failed == [GAME_B]
    # A's frame was out before B's ingest began, so B's failure cannot hold it.
    assert published_before_b == [[GAME_A]], published_before_b
    # B: its snapshot bookkeeping and its betting stamp roll back together.
    assert [r.reading_count for r in await _snapshots(pg_engine, GAME_B)] == [1] * len(BOOKS)
    assert await _sources(pg_engine, GAME_B) == before_b
    # A: committed before B started, so it stands.
    assert [r.reading_count for r in await _snapshots(pg_engine, GAME_A)] == [2] * len(BOOKS)
    # Only the committed game's frame is ever published, exactly once. B's frame
    # was dropped with its rollback. A later publish in the pass would have sent
    # it if it were still queued.
    assert [f["event_id"] for f in published] == [GAME_A], published


@pytest.mark.parametrize("fail_second", [False, True])
async def test_model_is_published_before_the_next_score_write(pg_engine, monkeypatch, fail_second):
    """Real model/score/snapshot writes; the next game cannot retain game A."""
    from app.utils import nonvenue_live_push

    anchor = datetime.now(timezone.utc)
    async with pg_engine.begin() as conn:
        await _seed(conn, anchor)
        await conn.execute(text(
            "UPDATE events SET opening_home_probability=0.6, period='3', "
            "game_clock='10:00' WHERE id = ANY(:ids)"
        ), {"ids": EVENT_IDS})

    class Scores(_OddsService):
        async def get_odds(self, sport_key, **kwargs):
            return []

        async def get_scores(self, sport_key, **kwargs):
            if sport_key != SPORT_KEY:
                return []
            return [dict(
                id=_external_id(g["event_id"]), completed=False,
                commence_time=(anchor - timedelta(minutes=30)).isoformat(),
                home_team=g["home"], away_team=g["away"],
                scores=[{"name": g["home"], "score": "21"},
                        {"name": g["away"], "score": "14"}],
            ) for g in GAMES]

    published = _wire(monkeypatch, pg_engine)
    original = nonvenue_live_push.write_nonvenue_probability
    before_second = []

    async def write(session, event, source, value, **kwargs):
        if event.id == GAME_B:
            before_second.append((
                await _sources(pg_engine, GAME_A),
                [f["event_id"] for f in published],
            ))
        result = await original(session, event, source, value, **kwargs)
        if event.id == GAME_B and fail_second:
            await session.execute(text("SELECT 1/0"))
        return result

    monkeypatch.setattr(nonvenue_live_push, "write_nonvenue_probability", write)
    await _pass(monkeypatch, Scores(anchor))
    assert len(before_second) == 1, before_second
    sources, visible = before_second[0]
    assert "stat_model" in sources and visible == [GAME_A], before_second
    assert [f["event_id"] for f in published] == ([GAME_A] if fail_second else EVENT_IDS)
    assert all(f["source"] == "stat_model" for f in published)
    async with pg_engine.connect() as conn:
        snapshots = (await conn.execute(text(
            "SELECT event_id, home_win_probability FROM win_prob_snapshots "
            "WHERE event_id = ANY(:ids) AND source='stat_model' ORDER BY event_id"
        ), {"ids": EVENT_IDS})).all()
        scores = (await conn.execute(text(
            "SELECT id, home_score, away_score FROM events WHERE id = ANY(:ids) ORDER BY id"
        ), {"ids": EVENT_IDS})).all()
    expected = [GAME_A] if fail_second else EVENT_IDS
    assert [s.event_id for s in snapshots] == expected
    for snapshot, frame in zip(snapshots, published):
        assert float(snapshot.home_win_probability) == pytest.approx(frame["source_value"])
    assert scores[0][1:] == (21, 14)
    assert scores[1][1:] == ((None, None) if fail_second else (21, 14))
