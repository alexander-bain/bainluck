"""The venue sockets say which markets moved, and only once the move is stored. #9484.

WHAT THIS SHIPS. An open standalone future, a prop, or a Discover market card
has no event blend, so the event stream never told a client its price moved;
the client waited for its next poll. Codex's `market_quote_push` (#9511) gives
each market a channel (`live:market:{id}`). This file pins the PRODUCER half,
which lives here: each socket stages one invalidation per row its price
UPDATE actually RETURNED, and publishes it only after the outer commit landed.

WHY A REAL SESSION. The whole contract is transactional — "only a committed
write publishes", "a rolled-back write never does", "a refused row signals
nothing" — so a fake session would be asserting its own answers. The slate
SELECTs are replayed (they are the socket's subscription, not what this file
is about), but every UPDATE the consumer emits runs on a REAL SQLAlchemy
Session over a file-backed SQLite database: its RETURNING, the #5411 settled
guard, and the after-commit / after-rollback events that `market_quote_push`
listens to are the engine's own. A second connection reads the row at publish
time, so "published after commit" is observed, not assumed.

THE CASES (Kalshi, the real `_run_kalshi_ws_consumer`):

    the_price_that_landed ........ THE SHIP. One tick on an open row → exactly
                                   one frame on its market channel, carrying
                                   the stored `last_updated` of that row, and
                                   the row was already committed when it went.
    the_tick_that_changed_nothing  Same price, same book → the row is written
                                   (liveness) but no frame (ux, #9526). The
                                   book-only arm needs Postgres: see
                                   integration/test_ws_quote_moved_9484_pg.py.
    the_settled_row .............. #5411 refuses the write (0 rows returned) →
                                   no frame. A buffered id is not evidence.
    the_commit_that_failed ....... The first commit fails → no frame; the retry
                                   commits → exactly ONE frame, so the rolled-
                                   back staging did not ride along.
    the_standalone_market ........ Slate row with no event → still one frame.
                                   Market publication never waits on a blend.
    the_settlement ............... A lifecycle `settled` push → one terminal
                                   frame carrying the stored `settled_at`.

And the Polymarket twin, through its real consumer: the flush's ship case, the
same price again (written, no frame — price arm only, this socket writes no
book), and its `market_resolved` push → one terminal frame carrying the `settled_at` that
transaction stored (read back inside it, so the read runs for real too).
"""

import asyncio
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import (
    Column, DateTime, Integer, MetaData, String, Table, create_engine, insert, select, text,
)
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.selectable import Select

import app.services.kalshi_ws as kalshi_svc
import app.services.polymarket_api as polymarket_api
import app.tasks.kalshi_ws as kalshi_task
import app.tasks.live_blend_refresh as blend_mod
from app.models.models import FuturesOutcome
from app.utils.market_quote_push import market_channel, parse_market_frame

pytestmark = pytest.mark.asyncio

MARKET_ID = 7
EVENT_ID = 900
TICKER = "KXTEST-Y"
MARKET_EXT = "KXTEST"
OUTCOME_ID = 81

TICK = json.dumps({
    "type": "ticker",
    "msg": {
        "market_ticker": TICKER,
        "yes_bid_dollars": "0.40",
        "yes_ask_dollars": "0.44",
    },
})

SETTLE = json.dumps({
    "type": "market_lifecycle_v2",
    "msg": {"market_ticker": TICKER, "status": "settled", "result": "yes"},
})


# ------------------------------------------------------------- the rig ----


def _database(tmp_path, resolution_source=None, current_probability=0.30,
              book=(None, None), price_changed_at=None):
    """A file-backed SQLite DB holding the one market and its one outcome."""
    url = f"sqlite:///{tmp_path / 'ws.db'}"
    engine = create_engine(url)
    # `futures_markets` carries JSONB columns SQLite cannot create; the socket's
    # settlement UPDATE only names these, so a same-named table holding them is
    # the table that statement runs against.
    markets = Table(
        "futures_markets", MetaData(),
        Column("id", Integer, primary_key=True),
        Column("source", String), Column("external_id", String),
        Column("name", String), Column("status", String),
        Column("settled_at", DateTime(timezone=True)),
        Column("updated_at", DateTime(timezone=True)),  # the model's onupdate
    )
    markets.create(engine)
    FuturesOutcome.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(insert(markets).values(
            id=MARKET_ID, source="kalshi", external_id=MARKET_EXT,
            name="A standalone question", status="open",
        ))
        conn.execute(insert(FuturesOutcome.__table__).values(
            id=OUTCOME_ID, market_id=MARKET_ID, external_id=TICKER,
            name="Yes", current_probability=current_probability,
            current_yes_bid=book[0], current_yes_ask=book[1],
            price_changed_at=price_changed_at,
            resolution_source=resolution_source,
        ))
    return engine


def _routes_to_the_database(stmt) -> bool:
    """The price UPDATE and the settlement's market UPDATE run for real.

    The #6598 re-rank and the settlement's `is_winner` writes are other
    features' statements (and the re-rank is Postgres SQL); they get the
    replayed result, exactly as in the #5411 file.
    """
    if isinstance(stmt, Select):
        # The Polymarket resolution reads back the `settled_at` its own UPDATE
        # stored. Only that read; the slate SELECTs stay replayed.
        return [c.key for c in stmt.selected_columns] == ["settled_at"]
    if not isinstance(stmt, Update):
        return False
    if stmt.table.name == "futures_markets":
        return True
    return stmt.table.name == "futures_outcomes" and any(
        getattr(col, "key", col) == "current_probability"
        for col in stmt._values
    )


class _Replayed:
    def __init__(self, rows, rowcount=1):
        self._rows = rows
        self.rowcount = rowcount

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _HybridSession:
    """An AsyncSession-shaped wrapper over a REAL sync Session."""

    def __init__(self, real, batches):
        self.sync_session = real
        self._batches = batches
        self.wrote_a_price = False

    @property
    def info(self):
        return self.sync_session.info

    async def execute(self, stmt, *_a, **_kw):
        if _routes_to_the_database(stmt):
            self.wrote_a_price |= (
                isinstance(stmt, Update) and stmt.table.name == "futures_outcomes"
            )
            return self.sync_session.execute(stmt)
        if isinstance(stmt, Update):
            return _Replayed([], rowcount=0)
        return _Replayed(self._batches.pop(0) if self._batches else [])


class _FakeRedis:
    """Records each PUBLISH with what a second connection saw at that moment."""

    def __init__(self, engine):
        self._engine = engine
        self.published = []

    async def publish(self, channel, payload):
        with self._engine.connect() as conn:
            stored = conn.execute(
                select(FuturesOutcome.__table__.c.current_probability)
                .where(FuturesOutcome.__table__.c.id == OUTCOME_ID)
            ).scalar_one()
        self.published.append((channel, json.loads(payload), float(stored)))
        return 0


def _frames(messages):
    class _Frames:
        def __init__(self):
            self._frames = list(messages)

        async def send(self, _payload):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._frames:
                return self._frames.pop(0)
            await asyncio.sleep(3600)  # the recycle cancellation lands here
            raise StopAsyncIteration  # pragma: no cover

    return _Frames()


#: The Polymarket consumer's three-query slate (the Q489/Q491 shape), with the
#: seeded row as its YES leg.
POLY_YES_TOKEN = "111"
POLY_NO_TOKEN = "222"
POLY_CONDITION = "0xabc"
POLY_TICK = json.dumps({
    "event_type": "best_bid_ask", "asset_id": POLY_YES_TOKEN,
    "best_bid": "0.40", "best_ask": "0.44",
})
POLY_SLATE = [
    [
        (OUTCOME_ID, MARKET_ID, f"{POLY_CONDITION}_yes", POLY_CONDITION, EVENT_ID),
        (82, MARKET_ID, f"{POLY_CONDITION}_no", POLY_CONDITION, EVENT_ID),
    ],
    [(MARKET_ID, POLY_CONDITION, {"clob_token_ids": [POLY_YES_TOKEN, POLY_NO_TOKEN]})],
    [
        (OUTCOME_ID, MARKET_ID, f"{POLY_CONDITION}_yes"),
        (82, MARKET_ID, f"{POLY_CONDITION}_no"),
    ],
]


class _UndecidedPolymarketVenue:
    """CLOB and Gamma both answer at once, neither has settled the market."""

    async def get_clob_market_by_condition(self, _condition_id):
        return None

    async def get_closed_gamma_market_raw(self, _condition_id):
        return None

    async def close(self):
        return None


async def _drive_kalshi(monkeypatch, engine, messages, event_id=EVENT_ID,
                        fail_commits=0, venue="kalshi"):
    import websockets

    import app.tasks.base as task_base
    import app.tasks.polymarket_ws as poly_task
    import app.tasks.redis_state as redis_state

    redis = _FakeRedis(engine)
    if venue == "kalshi":
        batches = [
            [(MARKET_EXT, MARKET_ID, event_id)],
            [(TICKER, MARKET_ID, OUTCOME_ID)],
        ]
    else:
        batches = [list(b) for b in POLY_SLATE]
    budget = {"fail_commits": fail_commits}

    class _Refresher(blend_mod.LiveBlendRefresher):
        """The real market publisher; the event blend is Q460's and elsewhere."""

        async def refresh(self, _event_ids):
            return None

        async def refresh_pending(self):
            return None

    class _SessionCtx:
        async def __aenter__(self):
            self.real = Session(engine)
            self.session = _HybridSession(self.real, batches)
            return self.session

        async def __aexit__(self, exc_type, *_exc):
            try:
                if (
                    exc_type is None
                    and self.session.wrote_a_price
                    and budget["fail_commits"] > 0
                ):
                    budget["fail_commits"] -= 1
                    self.real.rollback()
                    raise RuntimeError("commit failed")
                if exc_type is None:
                    self.real.commit()
                else:
                    self.real.rollback()
            finally:
                self.real.close()
            return False

    def _connect(*_a, **_kw):
        class _Ctx:
            async def __aenter__(self_inner):
                return _frames(messages)

            async def __aexit__(self_inner, *_exc):
                return False

        return _Ctx()

    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-secret")
    monkeypatch.setattr(kalshi_svc, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(kalshi_svc, "_sign_ws_request", lambda _k, _i: {})
    for task in (kalshi_task, poly_task):
        monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 0.5)
        monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", 0.02)
    monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _Refresher)
    monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: redis)
    monkeypatch.setattr(websockets, "connect", _connect)
    monkeypatch.setattr(
        task_base, "get_task_session", lambda *a, **kw: _SessionCtx()
    )
    # A `market_resolved` push asks the venue (CLOB, then Gamma, #9418) before
    # it writes. Unstubbed, those were REAL network reads: fast refusals on a
    # sandboxed laptop, slow answers on a CI runner — slow enough that the
    # 0.5 s recycle above cancelled the settle before it wrote (PR #10019 CI).
    # The venue here has not decided: the first answer is `unconfirmed`.
    monkeypatch.setattr(
        polymarket_api, "PolymarketAPIService", _UndecidedPolymarketVenue
    )

    if venue == "kalshi":
        stats = await kalshi_task._run_kalshi_ws_consumer()
    else:
        stats = await poly_task._run_polymarket_ws_consumer()
    return redis.published, stats


def _stored(engine, table, column, row_id):
    with engine.connect() as conn:
        return conn.execute(
            text(f"SELECT {column} FROM {table} WHERE id = :id"), {"id": row_id}
        ).scalar_one()


def _as_utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


# ------------------------------------------------------------ the cases ----


class TestTheKalshiSocketSaysWhichMarketMoved:
    async def test_the_price_that_landed(self, monkeypatch, tmp_path):
        engine = _database(tmp_path)
        published, stats = await _drive_kalshi(monkeypatch, engine, [TICK])

        # (No `price_updates` assertion: SQLite reports rowcount 0 under
        # RETURNING, so that counter is a Postgres fact. The frame and the
        # second connection's read below are the evidence.)
        assert stats["errors"] == 0
        assert len(published) == 1, published
        channel, frame, stored_at_publish = published[0]
        assert channel == market_channel(MARKET_ID)
        parsed = parse_market_frame(json.dumps(frame))
        assert parsed is not None, frame
        assert parsed["source"] == "kalshi" and parsed["terminal"] is False
        assert parsed["outcome_ids"] == [OUTCOME_ID]
        # The stamp is the row's STORED clock, not a send time.
        stored = _as_utc(_stored(engine, "futures_outcomes", "last_updated", OUTCOME_ID))
        assert _as_utc(parsed["outcome_observed_at"][str(OUTCOME_ID)]) == stored
        # Published only once the write was committed: a second connection
        # already read the streamed price.
        assert stored_at_publish == pytest.approx(0.42)

    async def test_the_settled_row(self, monkeypatch, tmp_path):
        engine = _database(tmp_path, resolution_source="api_settlement")
        published, stats = await _drive_kalshi(monkeypatch, engine, [TICK])

        assert stats["errors"] == 0
        assert published == []
        # The guard really refused it: the settled price is untouched.
        assert _stored(engine, "futures_outcomes", "current_probability",
                       OUTCOME_ID) == pytest.approx(0.30)

    async def test_the_commit_that_failed(self, monkeypatch, tmp_path):
        engine = _database(tmp_path)
        published, stats = await _drive_kalshi(
            monkeypatch, engine, [TICK], fail_commits=1
        )

        assert stats["errors"] >= 1 and stats["requeued"] >= 1
        # The retry landed and said so ONCE: the rolled-back staging from the
        # failed attempt was discarded, not carried into the next commit.
        assert len(published) == 1, published
        assert published[0][2] == pytest.approx(0.42)

    async def test_the_tick_that_changed_nothing(self, monkeypatch, tmp_path):
        """ux's #9526 finding: the same quote again is written, never signalled.

        The row already holds the tick's price (0.42, the 0.40/0.44 midpoint)
        and its book. The write still lands — `last_updated` is liveness — but
        no frame goes, so no held page re-reads an unchanged row.
        """
        moved_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        # The midpoint exactly as the socket computes it: SQLite ignores
        # NUMERIC(7, 6), so it compares the raw float, not the stored rounding
        # (the Postgres file covers that).
        engine = _database(
            tmp_path, current_probability=(0.40 + 0.44) / 2, book=(0.40, 0.44),
            price_changed_at=moved_at,
        )
        published, stats = await _drive_kalshi(monkeypatch, engine, [TICK])

        assert stats["errors"] == 0
        assert published == []
        assert stats["quotes_unchanged"] == 1
        # Written, not skipped: the liveness stamp moved, the change stamp did not.
        assert _as_utc(
            _stored(engine, "futures_outcomes", "last_updated", OUTCOME_ID)
        ) > moved_at
        assert _as_utc(
            _stored(engine, "futures_outcomes", "price_changed_at", OUTCOME_ID)
        ) == moved_at

    async def test_the_standalone_market(self, monkeypatch, tmp_path):
        engine = _database(tmp_path)
        published, _stats = await _drive_kalshi(
            monkeypatch, engine, [TICK], event_id=None
        )

        assert [p[0] for p in published] == [market_channel(MARKET_ID)]

    async def test_the_settlement(self, monkeypatch, tmp_path):
        engine = _database(tmp_path)
        published, stats = await _drive_kalshi(monkeypatch, engine, [SETTLE])

        assert stats["settlements"] == 1
        assert len(published) == 1, published
        parsed = parse_market_frame(json.dumps(published[0][1]))
        assert parsed["terminal"] is True and parsed["outcome_ids"] == []
        settled_at = _as_utc(_stored(engine, "futures_markets", "settled_at", MARKET_ID))
        assert _as_utc(parsed["updated_at"]) == settled_at


class TestThePolymarketSocketSaysWhichMarketMoved:
    async def test_the_price_that_landed(self, monkeypatch, tmp_path):
        """Twin of the Kalshi ship case, through the real Polymarket consumer."""
        engine = _database(tmp_path)
        published, stats = await _drive_kalshi(
            monkeypatch, engine, [POLY_TICK], venue="polymarket"
        )

        assert stats["errors"] == 0
        assert len(published) == 1, published
        channel, frame, stored_at_publish = published[0]
        parsed = parse_market_frame(json.dumps(frame))
        assert channel == market_channel(MARKET_ID)
        assert parsed["source"] == "polymarket" and parsed["terminal"] is False
        # Only the row that exists was RETURNED. The NO leg (82) is on the
        # slate and was priced too, but has no row here — a buffered id whose
        # row is gone signals nothing.
        assert parsed["outcome_ids"] == [OUTCOME_ID]
        stored = _as_utc(
            _stored(engine, "futures_outcomes", "last_updated", OUTCOME_ID)
        )
        assert _as_utc(parsed["outcome_observed_at"][str(OUTCOME_ID)]) == stored
        assert stored_at_publish == pytest.approx(0.42)

    async def test_the_tick_that_changed_nothing(self, monkeypatch, tmp_path):
        """Twin of the Kalshi case: the same price again is written, never
        signalled. The row holds the tick's midpoint exactly as the socket
        computes it (SQLite compares the raw float; the Postgres file covers
        the stored rounding)."""
        moved_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        engine = _database(
            tmp_path, current_probability=(0.40 + 0.44) / 2,
            price_changed_at=moved_at,
        )
        published, stats = await _drive_kalshi(
            monkeypatch, engine, [POLY_TICK], venue="polymarket"
        )

        assert stats["errors"] == 0
        assert published == []
        assert stats["quotes_unchanged"] == 1
        assert _as_utc(
            _stored(engine, "futures_outcomes", "last_updated", OUTCOME_ID)
        ) > moved_at
        assert _as_utc(
            _stored(engine, "futures_outcomes", "price_changed_at", OUTCOME_ID)
        ) == moved_at

    async def test_the_resolution(self, monkeypatch, tmp_path):
        """Twin of the Kalshi settlement: a `market_resolved` push → one terminal
        frame carrying the stored `settled_at`, published after the commit."""
        engine = _database(tmp_path)
        resolved = json.dumps({
            "event_type": "market_resolved", "market": POLY_CONDITION,
            "winning_outcome": "Yes",
        })
        published, stats = await _drive_kalshi(
            monkeypatch, engine, [resolved], venue="polymarket"
        )

        assert stats["resolutions"] == 1 and stats["errors"] == 0
        assert len(published) == 1, published
        channel, frame, _stored_at_publish = published[0]
        assert channel == market_channel(MARKET_ID)
        parsed = parse_market_frame(json.dumps(frame))
        assert parsed["source"] == "polymarket"
        assert parsed["terminal"] is True and parsed["outcome_ids"] == []
        assert _stored(engine, "futures_markets", "status", MARKET_ID) == "resolved"
        settled_at = _as_utc(_stored(engine, "futures_markets", "settled_at", MARKET_ID))
        assert _as_utc(parsed["updated_at"]) == settled_at
