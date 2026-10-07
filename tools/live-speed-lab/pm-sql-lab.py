"""#10664: Polymarket ``write_chunk`` — per-row UPDATEs vs one set-based UPDATE.

Private, disposable PostgreSQL 17 cluster (own socket dir + port, stopped on
exit). The real ``futures_outcomes`` schema from the models plus the indexes the
migrations/psql steps add. Both arms run the EXACT ``write_chunk`` body, lifted
by AST from source: the baseline from master ``BASE``, the candidate from
``BASE`` + ``pm-sql-candidate.patch``. Real ``queue_market_change``, real rerank
SQL, real ``get_task_session`` (lent engine, as the consumer does) and the real
``publish_committed_market_changes`` over a recording Redis stand-in. No
production connection, no provider call, no install, no Redis server.

    python3 tools/live-speed-lab/pm-sql-lab.py            # writes artifacts/10664-pm-sql-lab/results.json
    python3 tools/live-speed-lab/pm-sql-lab.py --dry-run  # no database: sources, patch, both arms compile

Needs an environment where System V IPC works (keyed shmget + shmctl/semctl). A
Claude lane sandbox denies them: initdb fails there and every probe LEAKS a
system-wide IPC id it cannot remove. Do not try to work around it with a shim.
"""

# ruff: noqa: E402
import ast
import asyncio
import functools
import hashlib
import json
import logging
import random
import subprocess
import sys
import tempfile
import time
import types
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import event as sa_event, func, text, update
from sqlalchemy.dialects.postgresql import asyncpg as apg_dialect
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.models import Base, FuturesOutcome
from app.services.database import build_connect_args
from app.tasks.base import get_task_session
from app.utils import market_quote_push
from app.utils.futures_rank import rerank_market_fields_stmt

BASE = "779da46f8b8e20a7a380db77be259dffaa433b77"
PG = Path("/opt/homebrew/opt/postgresql@17/bin")
PORT = 55464
PATCH = Path(__file__).with_name("pm-sql-candidate.patch")
OUT = ROOT / "artifacts" / "10664-pm-sql-lab" / "results.json"
WS = "backend/app/tasks/polymarket_ws.py"
STAMP = "backend/app/utils/price_change_stamp.py"
SIZES = (1, 32, 128, 500)
TIMING_PAIRS = 5
BINARY_MARKETS = 100_000
FIELD_MARKETS = 2_000
FIELD_LEGS = 20
SETTLED_MARKETS = 50

logging.getLogger("pm-sql-lab").addHandler(logging.NullHandler())
logging.getLogger("pm-sql-lab").propagate = False


# ── sources ──────────────────────────────────────────────────────────────────


def git_show(path):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "show", f"{BASE}:{path}"], text=True
    )


def patched_sources():
    with tempfile.TemporaryDirectory(prefix="lane1b-10664-src-") as tmp:
        tmp = Path(tmp)
        for path in (WS, STAMP):
            (tmp / path).parent.mkdir(parents=True, exist_ok=True)
            (tmp / path).write_text(git_show(path))
        # tmp is outside any repository, so `git apply` patches relative to cwd.
        subprocess.run(["git", "apply", str(PATCH)], cwd=tmp, check=True)
        return {path: (tmp / path).read_text() for path in (WS, STAMP)}


def module_from(name, source):
    mod = types.ModuleType(name)
    mod.__file__ = name
    exec(compile(source, name, "exec"), mod.__dict__)
    return mod


def lift(source, name, *, nested_in=None):
    tree = ast.parse(source)
    scope = tree
    if nested_in:
        scope = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nested_in
        )
    fn = next(
        n for n in ast.walk(scope)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    return ast.unparse(fn)


# ── private cluster ──────────────────────────────────────────────────────────


class Cluster:
    def __init__(self, tmp):
        self.dir = Path(tmp)
        self.sock = self.dir / "s"
        self.sock.mkdir()
        self.data = self.dir / "data"

    def url(self, db):
        return f"postgresql+asyncpg://@/{db}?host={self.sock}&port={PORT}"

    def start(self):
        subprocess.run(
            [str(PG / "initdb"), "-D", str(self.data), "-A", "trust", "--no-locale", "-E", "UTF8"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        opts = (
            f"-k {self.sock} -h '' -p {PORT} -c shared_buffers=128MB -c max_connections=20 "
            "-c shared_preload_libraries=pg_stat_statements -c pg_stat_statements.track=all "
            "-c fsync=on -c synchronous_commit=on"
        )
        subprocess.run(
            [str(PG / "pg_ctl"), "-D", str(self.data), "-l", str(self.dir / "pg.log"), "-o", opts, "-w", "start"],
            check=True, stdout=subprocess.DEVNULL,
        )

    def stop(self):
        subprocess.run(
            [str(PG / "pg_ctl"), "-D", str(self.data), "-m", "fast", "-w", "stop"],
            check=True, stdout=subprocess.DEVNULL,
        )

    def version(self):
        return subprocess.check_output([str(PG / "postgres"), "--version"], text=True).strip()


def engine_for(url, **kw):
    kw.setdefault("pool_size", 3)
    kw.setdefault("max_overflow", 2)
    # The consumer's engine shape (`_get_task_engine`): same connect args.
    return create_async_engine(url, pool_pre_ping=True, connect_args=build_connect_args(url), **kw)


EXTRA_INDEXES = [
    # add_futures_tables.py / add_outcome_price_changed_at.py (psql step) /
    # add_discover_feed_indexes.py / add_futures_outcomes_search_index.py
    "CREATE INDEX IF NOT EXISTS ix_futures_outcomes_rank ON futures_outcomes (rank)",
    "CREATE INDEX IF NOT EXISTS ix_futures_outcomes_last_updated ON futures_outcomes (last_updated)",
    "CREATE INDEX IF NOT EXISTS ix_fo_market_movement ON futures_outcomes (market_id, probability_change_24h)",
    "CREATE INDEX IF NOT EXISTS ix_futures_outcomes_name_trgm ON futures_outcomes USING gin (name gin_trgm_ops)",
]


async def build_template(cluster):
    admin = engine_for(cluster.url("postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as c:
        await c.execute(text("CREATE DATABASE lab_tpl"))
    await admin.dispose()
    eng = engine_for(cluster.url("lab_tpl"))
    async with eng.begin() as c:
        await c.execute(text("CREATE EXTENSION pg_trgm"))
        await c.run_sync(Base.metadata.create_all)
        for sql in EXTRA_INDEXES:
            await c.execute(text(sql))
        # Markets: binary game-style markets, then multi-leg fields.
        total = BINARY_MARKETS + FIELD_MARKETS
        await c.execute(text(
            "INSERT INTO futures_markets (id, source, external_id, name, category, mutually_exclusive, status, sport_key)"
            " SELECT g, 'polymarket', 'm' || g, 'Market ' || g, 'game', true, 'open', 'lab'"
            " FROM generate_series(1, :n) g"
        ), {"n": total})
        await c.execute(text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, current_probability,"
            " rank, last_updated, price_changed_at, volume)"
            " SELECT 2*g - 1 + s, g, CASE s WHEN 0 THEN 'c' || g ELSE 'c' || g || '_side1' END,"
            "  'Team ' || (2*g - 1 + s), CASE s WHEN 0 THEN p ELSE 1 - p END, NULL,"
            "  now() - interval '5 minutes', CASE WHEN g % 3 = 0 THEN NULL ELSE now() - interval '1 hour' END, 1000"
            " FROM (SELECT g, round((0.02 + random() * 0.96)::numeric, 6) p FROM generate_series(1, :b) g) m,"
            "  generate_series(0, 1) s"
        ), {"b": BINARY_MARKETS})
        await c.execute(text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, current_probability,"
            " rank, last_updated, price_changed_at, volume)"
            " SELECT 2*:b + (g - :b - 1) * :legs + l, g, 'f' || g || '_' || l, 'Leg ' || g || '/' || l,"
            "  round((random() * 0.3)::numeric, 6), NULL, now() - interval '5 minutes', now() - interval '1 hour', 10"
            " FROM generate_series(:b + 1, :b + :f) g, generate_series(1, :legs) l"
        ), {"b": BINARY_MARKETS, "f": FIELD_MARKETS, "legs": FIELD_LEGS})
        # Settled controls: graded binaries, exactly as a settlement leaves them.
        await c.execute(text(
            "UPDATE futures_outcomes SET current_probability = CASE WHEN id % 2 = 1 THEN 1 ELSE 0 END,"
            " is_winner = (id % 2 = 1), resolution_source = 'api_settlement'"
            " WHERE market_id <= :s"
        ), {"s": SETTLED_MARKETS})
        await c.execute(text("SELECT setval(pg_get_serial_sequence('futures_outcomes','id'), (SELECT max(id) FROM futures_outcomes))"))
        await c.execute(rerank_market_fields_stmt(list(range(1, total + 1))))
    async with eng.connect() as c:
        await c.execute(text("COMMIT"))
        await c.execute(text("VACUUM ANALYZE futures_outcomes"))
        await c.execute(text("VACUUM ANALYZE futures_markets"))
        rows = await c.scalar(text("SELECT count(*) FROM futures_outcomes"))
        idx = [r[0] for r in (await c.execute(text(
            "SELECT indexdef FROM pg_indexes WHERE tablename='futures_outcomes' ORDER BY indexname"
        ))).all()]
        trig = await c.scalar(text(
            "SELECT count(*) FROM pg_trigger WHERE tgrelid='futures_outcomes'::regclass AND NOT tgisinternal"
        ))
    await eng.dispose()
    return {"outcome_rows": rows, "indexes": idx, "user_triggers": trig}


async def fresh_db(cluster, name):
    admin = engine_for(cluster.url("postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as c:
        await c.execute(text(f"DROP DATABASE IF EXISTS {name}"))
        await c.execute(text(f"CREATE DATABASE {name} TEMPLATE lab_tpl"))
    await admin.dispose()
    return cluster.url(name)


# ── the arm: exact write_chunk in its closure ───────────────────────────────


class FakeConn:
    def __init__(self, sink):
        self.sink = sink

    def pack_commands(self, commands):
        return list(commands)

    async def send_packed_command(self, commands):
        for cmd in commands:
            await self.sink(cmd)

    async def read_response(self):
        return 0

    async def disconnect(self):
        pass


class FakePool:
    def __init__(self, sink):
        self.sink = sink

    async def get_connection(self, *a):
        return FakeConn(self.sink)

    async def release(self, conn):
        pass


class Refresher:
    """``blend_refresher`` stand-in: the real market publisher, recorded."""

    def __init__(self, arm):
        self.arm = arm
        self.frames = []
        self.client = types.SimpleNamespace(connection_pool=FakePool(self._sink))

    async def _sink(self, cmd):
        verb, channel, payload = cmd
        frame = json.loads(payload)
        # Post-commit proof: a DIFFERENT session must already read the stamps.
        visible = await self.arm.read_stamps(frame["outcome_ids"])
        frame["visible_elsewhere"] = all(
            visible.get(int(oid)) == datetime.fromisoformat(stamp)
            for oid, stamp in frame["outcome_observed_at"].items()
        )
        frame.pop("published_at")
        self.frames.append([verb, channel, frame])
        self.arm.trace.append(("publish", time.perf_counter()))

    async def publish_market_changes(self, session):
        return await market_quote_push.publish_committed_market_changes(session, self.client)


class Arm:
    def __init__(self, name, url, sources_by_arm):
        sources = sources_by_arm[name]
        self.name = name
        self.url = url
        self.engine = engine_for(url)
        self.observer = engine_for(url, pool_size=4)
        self.trace = []
        self.statements = []
        stamp = module_from(f"stamp_{name}", sources[STAMP])
        sa_event.listen(self.engine.sync_engine, "before_cursor_execute", self._before)
        sa_event.listen(self.engine.sync_engine, "after_cursor_execute", self._after)
        sa_event.listen(self.engine.sync_engine, "commit", self._commit)
        self.ns = dict(
            update=update,
            func=func,
            FuturesOutcome=FuturesOutcome,
            price_changed_at_value=stamp.price_changed_at_value,
            quote_moved_column=stamp.quote_moved_column,
            queue_market_change=market_quote_push.queue_market_change,
            rerank_market_fields_stmt=rerank_market_fields_stmt,
            get_task_session=functools.partial(get_task_session, engine=self.engine),
            logger=logging.getLogger("pm-sql-lab"),
            open_outcome_ids=set(),
        )
        if name == "candidate":
            exec(compile(lift(sources[WS], "chunk_price_update_stmt"), "candidate-helper", "exec"), self.ns)
        exec(compile(lift(sources[WS], "write_chunk", nested_in="_run_polymarket_ws_consumer"), f"write_chunk-{name}", "exec"), self.ns)
        self.write_chunk = self.ns["write_chunk"]

    def _before(self, conn, cursor, statement, parameters, context, executemany):
        kind = "rerank" if "rank(" in statement.lower() else (
            "price" if "current_probability=" in statement.replace(" ", "") else "other")
        self.statements.append([kind, time.perf_counter(), None])

    def _after(self, conn, cursor, statement, parameters, context, executemany):
        self.statements[-1][2] = time.perf_counter()

    def _commit(self, conn):
        self.trace.append(("commit-start", time.perf_counter()))

    def arm_state(self, market_by_outcome, buffer):
        self.stats = dict(
            price_updates=0, quotes_unchanged=0, ranks_rederived=0, errors=0,
            requeued=0, open_contract_prices_written=0,
        )
        self.refresher = Refresher(self)
        self.buffer = buffer
        self.ns.update(
            stats=self.stats,
            market_by_outcome=market_by_outcome,
            blend_refresher=self.refresher,
            buffer_lock=asyncio.Lock(),
            price_buffer=buffer,
        )
        self.trace.clear()
        self.statements.clear()

    async def read_stamps(self, ids):
        async with self.observer.connect() as c:
            rows = (await c.execute(text(
                "SELECT id, last_updated FROM futures_outcomes WHERE id = ANY(:ids)"
            ), {"ids": [int(i) for i in ids]})).all()
        return {r[0]: r[1] for r in rows}

    async def dump(self):
        async with self.observer.connect() as c:
            cols = [c_.name for c_ in FuturesOutcome.__table__.columns]
            rows = (await c.execute(text(
                f"SELECT {', '.join(cols)} FROM futures_outcomes ORDER BY id"
            ))).all()
        return cols, rows

    async def close(self):
        await self.engine.dispose()
        await self.observer.dispose()


# ── normalisation for cross-arm comparison ──────────────────────────────────


def norm_rows(cols, rows, before, txn_times):
    """Rows with each timestamp mapped to: unchanged / the k-th write's clock."""
    clock = {t: f"write-{k}" for k, t in enumerate(txn_times)}
    old = {r[0]: r for r in before}
    out = []
    ts_cols = {"last_updated", "price_changed_at"}
    for r in rows:
        prev = old.get(r[0])
        vals = []
        for name, v, p in zip(cols, r, prev or [None] * len(cols)):
            if name in ts_cols and v is not None:
                v = clock.get(v, "unchanged" if prev is not None and v == p else f"OTHER:{v}")
            elif hasattr(v, "isoformat"):
                v = v.isoformat()
            elif v is not None and not isinstance(v, (int, str, bool, float)):
                v = str(v)
            vals.append(v)
        out.append(vals)
    return out


def norm_frames(frames, txn_times):
    clock = {t.isoformat(): f"write-{k}" for k, t in enumerate(txn_times)}
    out = []
    for verb, channel, f in frames:
        f = dict(f)
        f["outcome_observed_at"] = {k: clock.get(v, v) for k, v in f["outcome_observed_at"].items()}
        f["updated_at"] = clock.get(f["updated_at"], f["updated_at"])
        out.append([verb, channel, f])
    return out


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ── corpus ──────────────────────────────────────────────────────────────────


def market_of(oid):
    if oid <= 2 * BINARY_MARKETS:
        return (oid + 1) // 2
    return BINARY_MARKETS + 1 + (oid - 2 * BINARY_MARKETS - 1) // FIELD_LEGS


MARKET_BY_OUTCOME = None  # built lazily: every outcome id in the template


def all_market_map():
    global MARKET_BY_OUTCOME
    if MARKET_BY_OUTCOME is None:
        top = 2 * BINARY_MARKETS + FIELD_MARKETS * FIELD_LEGS
        MARKET_BY_OUTCOME = {oid: market_of(oid) for oid in range(1, top + 1)}
    return MARKET_BY_OUTCOME


async def stored_prices(arm, ids):
    async with arm.observer.connect() as c:
        rows = (await c.execute(text(
            "SELECT id, current_probability FROM futures_outcomes WHERE id = ANY(:ids)"
        ), {"ids": list(ids)})).all()
    return {r[0]: (None if r[1] is None else float(r[1])) for r in rows}


def corpus_ids(rng, n, *, settled=0, vanished=(), field=0):
    """Chunk ids in BUFFER order (not id order): complement pairs adjacent."""
    ids = []
    if settled:
        mk = rng.randrange(1, SETTLED_MARKETS + 1)
        ids += [2 * mk - 1, 2 * mk][:settled]
    ids += list(vanished)
    if field:
        fm = rng.randrange(BINARY_MARKETS + 1, BINARY_MARKETS + FIELD_MARKETS + 1)
        first = 2 * BINARY_MARKETS + (fm - BINARY_MARKETS - 1) * FIELD_LEGS + 1
        ids += rng.sample(range(first, first + FIELD_LEGS), min(field, FIELD_LEGS))
    while len(ids) < n:
        mk = rng.randrange(SETTLED_MARKETS + 1, BINARY_MARKETS + 1)
        pair = [2 * mk - 1, 2 * mk]
        if pair[0] in ids:
            continue
        rng.shuffle(pair)
        ids += pair[: n - len(ids)]
    ids = ids[:n]
    # Buffer order is oldest-dirty, unrelated to id order: shuffle by pairs.
    rng.shuffle(ids)
    return ids


def corpus_prices(rng, ids, stored):
    """Moved, exactly unchanged, precision-equal and rounding-edge inputs."""
    out = {}
    for i, oid in enumerate(ids):
        s = stored.get(oid)
        kind = i % 20
        if s is None or kind < 11:
            out[oid] = round(rng.uniform(0.01, 0.99), rng.choice((2, 3, 4, 6, 9)))
        elif kind < 15:
            out[oid] = s  # unchanged: liveness touch, no frame
        elif kind < 18:
            out[oid] = s + rng.choice((1, -1)) * rng.uniform(0, 4.9e-7)  # rounds to stored
        else:
            out[oid] = round(s + rng.choice((5e-7, -5e-7, 1.5e-6)), 9)  # half-way edges
        if out[oid] is not None:
            out[oid] = min(max(out[oid], 0.0), 1.0)
    return out


# ── scenarios ───────────────────────────────────────────────────────────────


async def run_writes(arm, chunks):
    """Run successive chunks through the arm; return per-write evidence."""
    writes = []
    for chunk in chunks:
        buffer = dict(chunk)
        arm.arm_state(all_market_map(), buffer)
        ok = await arm.write_chunk(dict(chunk))
        commit_at = next((t for k, t in arm.trace if k == "commit-start"), None)
        first_pub = next((t for k, t in arm.trace if k == "publish"), None)
        writes.append(dict(
            returned=ok,
            stats=dict(arm.stats),
            frames=list(arm.refresher.frames),
            buffer_after=sorted(buffer),
            publish_after_commit=(first_pub is None or (commit_at is not None and first_pub > commit_at)),
            all_frames_visible_elsewhere=all(f[2]["visible_elsewhere"] for f in arm.refresher.frames),
        ))
    return writes


async def txn_times_of(arm, writes):
    stamps = set()
    for w in writes:
        for _, _, f in w["frames"]:
            stamps.update(datetime.fromisoformat(v) for v in f["outcome_observed_at"].values())
    return sorted(stamps)


async def parity_scenario(cluster, sources, label, make_chunks):
    results = {}
    for arm_name in ("baseline", "candidate"):
        url = await fresh_db(cluster, f"p_{label.replace('-', '_')}_{arm_name}")
        arm = Arm(arm_name, url, sources)
        try:
            cols, before = await arm.dump()
            chunks = await make_chunks(arm)
            writes = await run_writes(arm, chunks)
            cols, after = await arm.dump()
            # Every write's clock: read from the rows themselves (touch-stamps).
            clocks = sorted({r[cols.index("last_updated")] for r in after} - {r[cols.index("last_updated")] for r in before})
            results[arm_name] = dict(
                chunks=[[[k, v] for k, v in c.items()] for c in chunks],
                writes=writes,
                rows=norm_rows(cols, after, before, clocks),
                clocks=len(clocks),
                frames=[norm_frames(w["frames"], clocks) for w in writes],
            )
        finally:
            await arm.close()
    b, c = results["baseline"], results["candidate"]
    assert b["chunks"] == c["chunks"], "inputs must be identical"
    checks = dict(
        rows_equal=b["rows"] == c["rows"],
        frames_equal=b["frames"] == c["frames"],
        returned_equal=[w["returned"] for w in b["writes"]] == [w["returned"] for w in c["writes"]],
        stats_equal=[w["stats"] for w in b["writes"]] == [w["stats"] for w in c["writes"]],
        buffer_equal=[w["buffer_after"] for w in b["writes"]] == [w["buffer_after"] for w in c["writes"]],
        publish_after_commit=all(w["publish_after_commit"] for r in (b, c) for w in r["writes"]),
        frames_visible_to_other_session=all(w["all_frames_visible_elsewhere"] for r in (b, c) for w in r["writes"]),
    )
    return dict(
        scenario=label,
        parity=all(checks.values()),
        checks=checks,
        rows_digest={k: digest(v["rows"]) for k, v in results.items()},
        frames_digest={k: digest(v["frames"]) for k, v in results.items()},
        per_write={k: [dict(returned=w["returned"], stats=w["stats"], frames=len(w["frames"]), buffer_after=len(w["buffer_after"])) for w in v["writes"]] for k, v in results.items()},
        sample_frame=(b["frames"][0][:1] if b["frames"] and b["frames"][0] else None),
    )


def corpus_maker(n, seed):
    async def make(arm):
        rng = random.Random(seed)
        vanished = []
        if n >= 32:
            # Two rows that existed when buffered and are gone now.
            vanished = [2 * (BINARY_MARKETS - 7) - 1, 2 * (BINARY_MARKETS - 9)]
            async with arm.observer.begin() as c:
                await c.execute(text("DELETE FROM futures_outcomes WHERE id = ANY(:ids)"), {"ids": vanished})
        ids = corpus_ids(rng, n, settled=2 if n >= 32 else 0, vanished=vanished, field=6 if n >= 32 else 0)
        stored = await stored_prices(arm, ids)
        first = corpus_prices(rng, ids, stored)
        # Second write over the same ids, as the next flush: half move again.
        second = {}
        for i, oid in enumerate(ids):
            second[oid] = first[oid] if i % 2 else round(rng.uniform(0.01, 0.99), 6)
        return [first, second]
    return make


def rollback_maker(n, seed):
    async def make(arm):
        rng = random.Random(seed)
        ids = corpus_ids(rng, n)
        stored = await stored_prices(arm, ids)
        chunk = corpus_prices(rng, ids, stored)
        chunk[ids[n * 2 // 3]] = 12.5  # numeric(7,6) overflow: the write fails mid-chunk
        return [chunk]
    return make


async def probe_locked(observer, ids):
    """Which of ``ids`` are row-locked right now (NOWAIT probe, rolled back)."""
    locked = []
    for oid in ids:
        async with observer.connect() as c:
            tx = await c.begin()
            try:
                await c.execute(text("SET LOCAL lock_timeout = '1ms'"))
                await c.execute(text("SELECT 1 FROM futures_outcomes WHERE id = :i FOR UPDATE NOWAIT"), {"i": oid})
                locked.append(False)
            except Exception:
                locked.append(True)
            finally:
                await tx.rollback()
    return locked


async def wait_for_lock_wait(observer, timeout=5):
    async with observer.connect() as c:
        async with asyncio.timeout(timeout):
            while True:
                n = await c.scalar(text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                    " AND wait_event_type = 'Lock'"
                ))
                if n:
                    return
                await asyncio.sleep(0.005)


async def concurrency_scenario(cluster, sources, label, *, cancel):
    """A row mid-chunk is held by another transaction.

    Lock order is probed while the write waits. ``cancel``: the flush task is
    cancelled while blocked (a recycle). Otherwise: the holder commits its own
    write of the blocked row (the same price the chunk carries, so the chunk's
    write must NOT read as a move), and newer prices arrive in the buffer for
    an already-written row and a not-yet-written row while the write waits.
    """
    results = {}
    for arm_name in ("baseline", "candidate"):
        url = await fresh_db(cluster, f"c_{label.replace('-', '_')}_{arm_name}")
        arm = Arm(arm_name, url, sources)
        try:
            cols, before = await arm.dump()
            rng = random.Random(1066)
            ids = corpus_ids(rng, 8)
            stored = await stored_prices(arm, ids)
            chunk = {oid: round(stored[oid] + 0.05 if stored[oid] < 0.9 else stored[oid] - 0.05, 6) for oid in ids}
            hold = ids[3]
            buffer = dict(chunk)
            arm.arm_state(all_market_map(), buffer)
            holder = await arm.observer.connect()
            htx = await holder.begin()
            await holder.execute(text(
                "UPDATE futures_outcomes SET current_probability = :p,"
                " price_changed_at = timestamptz '2026-01-01 00:00:00+00' WHERE id = :i"
            ), {"p": chunk[hold], "i": hold})
            task = asyncio.create_task(arm.write_chunk(dict(chunk)))
            await wait_for_lock_wait(arm.observer)
            locked = await probe_locked(arm.observer, [i for i in ids if i != hold])
            evidence = dict(held_position=3, chunk_order_locked_while_waiting=locked)
            if cancel:
                task.cancel()
                try:
                    await task
                    evidence["cancel_raised"] = False
                except asyncio.CancelledError:
                    evidence["cancel_raised"] = True
                await htx.rollback()
            else:
                newer = {ids[1]: 0.123457, ids[6]: 0.876543}
                async with arm.ns["buffer_lock"]:
                    buffer.update(newer)
                await htx.commit()
                evidence["returned"] = await asyncio.wait_for(task, 5)
                evidence["buffer_after"] = {str(k): v for k, v in sorted(buffer.items())}
                evidence["buffer_holds_exactly_newer"] = buffer == newer
            await holder.close()
            evidence["locked_after"] = await probe_locked(arm.observer, ids)
            evidence["stats"] = dict(arm.stats)
            cols, after = await arm.dump()
            clocks = sorted({r[cols.index("last_updated")] for r in after} - {r[cols.index("last_updated")] for r in before})
            evidence["frames"] = norm_frames(arm.refresher.frames, clocks)
            evidence["rows"] = norm_rows(cols, after, before, clocks)
            evidence["db_unchanged"] = evidence["rows"] == norm_rows(cols, before, before, [])
            results[arm_name] = evidence
        finally:
            await arm.close()
    b, c = results["baseline"], results["candidate"]
    keys = ["chunk_order_locked_while_waiting", "locked_after", "stats", "frames", "rows"]
    keys += ["cancel_raised"] if cancel else ["returned", "buffer_after"]
    checks = {k + "_equal": b[k] == c[k] for k in keys}
    expected_order = [True, True, True, False, False, False, False]  # positions 0-2 held, 4-7 not yet
    checks["lock_order_is_chunk_order"] = b["chunk_order_locked_while_waiting"] == c["chunk_order_locked_while_waiting"] == expected_order
    checks["no_lock_left"] = not any(b["locked_after"]) and not any(c["locked_after"])
    if cancel:
        checks["cancel_propagated_db_unchanged_no_frames"] = all(
            r["cancel_raised"] and r["db_unchanged"] and not r["frames"] for r in (b, c))
    else:
        checks["newer_input_survives"] = b["buffer_holds_exactly_newer"] and c["buffer_holds_exactly_newer"]
        checks["held_row_not_a_move"] = all(r["stats"]["quotes_unchanged"] == 1 for r in (b, c))
    return dict(
        scenario=label, parity=all(checks.values()), checks=checks,
        baseline={k: v for k, v in b.items() if k not in ("rows",)},
        candidate_rows_digest=digest(c["rows"]), baseline_rows_digest=digest(b["rows"]),
    )


# ── timing ──────────────────────────────────────────────────────────────────


def summarize(arm, ok, wall):
    price = [s for s in arm.statements if s[0] == "price"]
    rerank = [s for s in arm.statements if s[0] == "rerank"]
    commit = next(t for k, t in arm.trace if k == "commit-start")
    end_sql = max(s[2] for s in arm.statements)
    publish = [t for k, t in arm.trace if k == "publish"]
    ms = lambda a, b: round((b - a) * 1000, 3)  # noqa: E731
    return dict(
        ok=ok,
        wall_ms=round(wall * 1000, 3),
        statements=len(arm.statements),
        price_statements=len(price),
        price_sql_ms=round(sum(s[2] - s[1] for s in price) * 1000, 3),
        price_span_ms=ms(price[0][1], price[-1][2]),
        rerank_ms=round(sum(s[2] - s[1] for s in rerank) * 1000, 3),
        commit_start_after_last_sql_ms=ms(end_sql, commit),
        lock_window_ms=ms(price[0][1], publish[0]) if publish else None,
        frames=len(arm.refresher.frames),
    )


async def timing(cluster, sources):
    url = await fresh_db(cluster, "timing")
    arms = {n: Arm(n, url, sources) for n in ("baseline", "candidate")}
    rng = random.Random(10664)
    used = set()

    def chunk_of(n):
        ids = corpus_ids(rng, n)
        while used & set(ids):
            ids = corpus_ids(rng, n)
        used.update(ids)
        return {oid: round(rng.uniform(0.01, 0.99), 6) for oid in ids}

    async def one(arm, n):
        chunk = chunk_of(n)
        arm.arm_state(all_market_map(), dict(chunk))
        t0 = time.perf_counter()
        ok = await arm.write_chunk(chunk)
        return summarize(arm, ok, time.perf_counter() - t0)

    out = {}
    try:
        # Warm both arms' prepared statements on every size (the consumer's
        # engine is long-lived; a cold first statement is not its steady state).
        for n in SIZES:
            for _ in range(2):
                for a in arms.values():
                    await one(a, n)
        async with arms["baseline"].observer.connect() as c:
            await c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_stat_statements"))
            await c.execute(text("SELECT pg_stat_statements_reset()"))
            await c.commit()
        for n in SIZES:
            obs = []
            for pair in range(TIMING_PAIRS):
                order = ("baseline", "candidate") if pair % 2 == 0 else ("candidate", "baseline")
                for name in order:
                    r = await one(arms[name], n)
                    r.update(arm=name, pair=pair)
                    obs.append(r)
            out[str(n)] = obs
        async with arms["baseline"].observer.connect() as c:
            pss = [dict(r._mapping) for r in (await c.execute(text(
                "SELECT left(regexp_replace(query, '\\s+', ' ', 'g'), 90) AS query, calls,"
                " round(total_exec_time::numeric, 3) AS total_exec_ms,"
                " round(mean_exec_time::numeric, 4) AS mean_exec_ms,"
                " round(total_plan_time::numeric, 3) AS total_plan_ms, rows"
                " FROM pg_stat_statements WHERE query ILIKE '%futures_outcomes%'"
                " AND query NOT ILIKE '%pg_stat_statements%' ORDER BY total_exec_time DESC LIMIT 6"
            ))).all()]
        plans = await explain(arms["candidate"], chunk_of(500))
    finally:
        for a in arms.values():
            await a.close()
    return dict(observations=out, pg_stat_statements=pss, candidate_plans=plans)


async def explain(arm, chunk):
    stmt = arm.ns["chunk_price_update_stmt"](chunk)
    compiled = stmt.compile(dialect=apg_dialect.dialect())
    sql = str(compiled)
    params = [compiled.params[k] for k in compiled.positiontup]
    import asyncpg

    raw = await asyncpg.connect(host=str(Path(arm.url.split("host=")[1].split("&")[0])), port=PORT, database=arm.url.split("/")[-1].split("?")[0])
    try:
        tx = raw.transaction()
        await tx.start()
        custom = [r[0] for r in await raw.fetch("EXPLAIN (ANALYZE, BUFFERS, COSTS) " + sql, *params)]
        await tx.rollback()
        generic = [r[0] for r in await raw.fetch("EXPLAIN (GENERIC_PLAN, COSTS) " + sql)]
    finally:
        await raw.close()
    return dict(custom_500_analyze=custom, generic=generic)


# ── main ────────────────────────────────────────────────────────────────────


async def static_controls(sources):
    base_stamp = module_from("stamp_base_ctl", sources["base"][STAMP])
    cand_stamp = module_from("stamp_cand_ctl", sources["candidate"][STAMP])
    d = apg_dialect.dialect()
    t = FuturesOutcome.__table__
    same = all(
        str(base_stamp.price_changed_at_value(t.c.current_probability, t.c.price_changed_at, v).compile(dialect=d))
        == str(cand_stamp.price_changed_at_value(t.c.current_probability, t.c.price_changed_at, v).compile(dialect=d))
        for v in (0.5, None, 0.0512345678)
    )
    return dict(stamp_helper_scalar_sql_identical=same)


async def amain(cluster):
    base = {WS: git_show(WS), STAMP: git_show(STAMP)}
    cand = patched_sources()
    # The candidate's helper imports the stamp module at call time; give it the
    # patched one (scalar SQL proven identical below; baseline uses BASE's).
    sys.modules["app.utils.price_change_stamp"] = module_from("app.utils.price_change_stamp", cand[STAMP])
    sources = {"baseline": base, "candidate": cand}
    report = dict(
        base=BASE,
        postgres=cluster.version(),
        source_sha256={k: hashlib.sha256(v.encode()).hexdigest()[:16] for k, v in base.items()},
        patch_sha256=hashlib.sha256(PATCH.read_bytes()).hexdigest()[:16],
        static=await static_controls({"base": base, "candidate": cand}),
    )
    report["schema"] = await build_template(cluster)

    scen = []
    for n in SIZES:
        scen.append(await parity_scenario(cluster, sources, f"corpus-{n}", corpus_maker(n, 1000 + n)))
    scen.append(await parity_scenario(cluster, sources, "rollback-32", rollback_maker(32, 77)))
    scen.append(await concurrency_scenario(cluster, sources, "held-row-newer-input", cancel=False))
    scen.append(await concurrency_scenario(cluster, sources, "held-row-cancel", cancel=True))
    report["parity"] = scen
    report["all_parity"] = all(s["parity"] for s in scen)
    if report["all_parity"]:
        report["timing"] = await timing(cluster, sources)
    return report


async def dry_run():
    """Everything short of a database: no cluster is started, nothing connects."""
    base = {WS: git_show(WS), STAMP: git_show(STAMP)}
    cand = patched_sources()
    sys.modules["app.utils.price_change_stamp"] = module_from("app.utils.price_change_stamp", cand[STAMP])
    sources = {"baseline": base, "candidate": cand}
    report = dict(
        base=BASE,
        source_sha256={k: hashlib.sha256(v.encode()).hexdigest()[:16] for k, v in base.items()},
        patch_sha256=hashlib.sha256(PATCH.read_bytes()).hexdigest()[:16],
        static=await static_controls({"base": base, "candidate": cand}),
    )
    url = "postgresql+asyncpg://@/none?host=/nonexistent&port=1"  # engines are lazy
    arms = {n: Arm(n, url, sources) for n in ("baseline", "candidate")}
    try:
        b = ast.parse(lift(base[WS], "write_chunk", nested_in="_run_polymarket_ws_consumer"))
        c = ast.parse(lift(cand[WS], "write_chunk", nested_in="_run_polymarket_ws_consumer"))
        # Outside the replaced price block the two bodies must be identical.
        def parts(tree):
            body = tree.body[0].body
            k = next(n for n, node in enumerate(body) if isinstance(node, ast.Try))
            session_with = body[k].body[0]
            return dict(
                outside_try=[ast.dump(n) for n in body[:k] + body[k + 1:]],
                handlers=[ast.dump(h) for h in body[k].handlers],
                after_session=[ast.dump(n) for n in body[k].body[1:]],
                session_items=ast.dump(session_with.items[0]),
                rerank_tail=[ast.dump(n) for n in session_with.body[-2:]],
            )
        pb, pc = parts(b), parts(c)
        report["write_chunk_compiles_both_arms"] = all(callable(a.write_chunk) for a in arms.values())
        report["identical_outside_price_block"] = {key: pb[key] == pc[key] for key in pb}
        report["only_the_price_block_differs"] = all(report["identical_outside_price_block"].values())
        stmt = arms["candidate"].ns["chunk_price_update_stmt"]({11: 0.25, 3: 0.0512345678, 7: None})
        compiled = stmt.compile(dialect=apg_dialect.dialect())
        report["candidate_sql"] = str(compiled)
        report["candidate_params"] = {k: compiled.params[k] for k in compiled.positiontup}
        report["candidate_param_count_independent_of_chunk_size"] = (
            len(arms["candidate"].ns["chunk_price_update_stmt"]({i: 0.5 for i in range(1, 501)}).compile(dialect=apg_dialect.dialect()).positiontup)
            == len(compiled.positiontup) == 3
        )
    finally:
        for a in arms.values():
            await a.close()
    return report


def main():
    if "--dry-run" in sys.argv:
        report = asyncio.run(dry_run())
        print(json.dumps(report, indent=1, default=str))
        ok = report["static"]["stamp_helper_scalar_sql_identical"] and report["write_chunk_compiles_both_arms"] \
            and report["only_the_price_block_differs"] and report["candidate_param_count_independent_of_chunk_size"]
        return 0 if ok else 1
    with tempfile.TemporaryDirectory(prefix="lane1b-10664-pg-") as tmp:
        cluster = Cluster(tmp)
        cluster.start()
        try:
            report = asyncio.run(amain(cluster))
        finally:
            cluster.stop()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1, default=str) + "\n")
    print(json.dumps({k: report[k] for k in ("all_parity", "static", "schema")}, indent=1, default=str))
    for s in report["parity"]:
        print(s["scenario"], s["parity"], {k: v for k, v in s["checks"].items() if not v})
    return 0 if report["all_parity"] else 1


if __name__ == "__main__":
    sys.exit(main())
