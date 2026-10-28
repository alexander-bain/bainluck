"""#11681 diagnostic-only pytest observer. DIAGNOSTIC ONLY, DO NOT MERGE.

Lives only on branch diag/10090-11681-hosted-timing. It changes no assertion,
budget, wait, retry, fixture or production code path; it only reads clocks and
counters. Built from lane1's l1probe/l1observe (GC callbacks, per-window
CPU/run-queue) and speed's authority_gate_diagnostic (pool/driver stages,
20 ms event-loop overshoot, statement KIND only, never SQL text or parameters).

Records, for the whole pytest process:
  gc       every CPython collection: start, duration, generation, collected, test
  tests    per test: setup/call/teardown/end times and gc.get_count() at setup
  windows  every AuthorityStore call that owns an asyncio.timeout budget
           (7 methods): wall, thread CPU, run-queue wait, involuntary switches,
           GC inside, task.cancelling(), outcome
  events   stages inside a window: pool checkout (+ server pid) / checkin /
           reset / invalidate / connect, and the asyncpg awaits BEGIN, COMMIT,
           ROLLBACK, prepare, fetch, reload_schema_state, each with wall, CPU,
           run-queue, GC inside and outcome
  lags     event-loop overshoots >= 20 ms on any loop that ran a window
           during that test (matched to windows by time in the analysis)

Bounded: preallocated array.array columns (not GC-tracked containers). The
only per-event Python allocations are one transient coroutine/frame per
wrapped await and one TimerHandle per 20 ms tick, which can move when a
collection fires (observer effect, disclosed). Overflow is counted, not grown.
"""

import array
import asyncio
import contextvars
import gc
import json
import math
import os
import resource
import sys
import time
import weakref

import pytest

OUT = os.environ.get("L1OBS_OUT", "l1observe.json")
CAP_GC, CAP_WIN, CAP_EV, CAP_LAG, CAP_TEST = 80_000, 30_000, 300_000, 50_000, 4_000
TICK_S, LAG_S = 0.020, 0.020
NAN = float("nan")
_perf = time.perf_counter
_cpu = time.thread_time
_SCHED = "/proc/thread-self/schedstat"
_HAS_SCHED = os.path.exists(_SCHED)
_RUSAGE = getattr(resource, "RUSAGE_THREAD", None)


def _rq_ns():
    if not _HAS_SCHED:
        return NAN
    fd = os.open(_SCHED, os.O_RDONLY)
    try:
        return float(os.read(fd, 128).split()[1])
    finally:
        os.close(fd)


def _nivcsw():
    return NAN if _RUSAGE is None else float(resource.getrusage(_RUSAGE).ru_nivcsw)


def _buf(code, n):
    return array.array(code, bytes(array.array(code).itemsize * n))


class _Table:
    def __init__(self, cap, doubles, smalls=(), ints=()):
        self.cap, self.n, self.over = cap, 0, 0
        self.cols = {f: _buf("d", cap) for f in doubles}
        self.cols.update({f: _buf("b", cap) for f in smalls})
        self.cols.update({f: _buf("i", cap) for f in ints})

    def claim(self):
        n = self.n
        if n >= self.cap:
            self.over += 1
            return -1
        self.n = n + 1
        return n

    def dump(self):
        n = self.n
        return {
            f: [None if isinstance(v, float) and math.isnan(v) else v for v in b[:n]]
            for f, b in self.cols.items()
        }

    def nbytes(self):
        return sum(b.buffer_info()[1] * b.itemsize for b in self.cols.values())


GC = _Table(CAP_GC, ("p0", "dur"), ("gen",), ("collected", "test"))
TESTS_T = _Table(
    CAP_TEST, ("setup_p", "call_p", "teardown_p", "end_p"), (), ("g0", "g1", "g2")
)
WIN = _Table(
    CAP_WIN,
    ("epoch0", "p0", "p1", "c0", "c1", "rq0", "rq1", "iv0", "iv1", "gc_s", "gc2_s"),
    ("method", "outcome", "cancelling"),
    ("test",),
)
EV = _Table(
    CAP_EV,
    ("epoch0", "p0", "p1", "c0", "c1", "rq0", "rq1", "gc_s"),
    ("kind", "outcome", "sqlk"),
    ("win", "pid"),
)
LAG = _Table(CAP_LAG, ("p", "lag"), (), ("test",))

METHODS = (
    "read", "read_for_producer", "read_retirement", "activation_step",
    "take_activation_step", "complete_retirement", "_compare_exchange",
)
KINDS = (
    "pool.checkout", "pool.checkin", "pool.reset", "pool.invalidate", "pool.connect",
    "BEGIN", "COMMIT", "ROLLBACK", "prepare", "fetch", "reload_schema_state",
)
K = {name: i for i, name in enumerate(KINDS)}
SQL_KINDS = (
    "OTHER", "SELECT", "INSERT", "UPDATE", "DELETE", "BEGIN", "COMMIT", "ROLLBACK",
    "SAVEPOINT", "RELEASE", "SET_LOCK_TIMEOUT", "SET_STATEMENT_TIMEOUT", "SET", "WITH",
)
OUTCOMES = ["ok"]
TESTS = []
_test_ix = {}
_state = {"test": -1, "gc_start": NAN, "row": -1}
_WINV = contextvars.ContextVar("l1obs_window", default=-1)
_loops = weakref.WeakKeyDictionary()
ANCHORS = []


def _anchor(label):
    ANCHORS.append((label, _perf(), time.time(), time.monotonic()))


def _sql_kind(query):
    if not isinstance(query, str):
        return 0
    head = query[:48].lstrip().upper()
    if head.startswith("SET LOCAL LOCK_TIMEOUT"):
        return 10
    if head.startswith("SET LOCAL STATEMENT_TIMEOUT"):
        return 11
    word = head.split(None, 1)[0].rstrip(";") if head else ""
    return SQL_KINDS.index(word) if word in SQL_KINDS[1:10] + ("SET", "WITH") else 0


def _outcome(exc):
    label = type(exc).__name__
    if label not in OUTCOMES:
        OUTCOMES.append(label)
    return OUTCOMES.index(label)


def _gc_cb(phase, info):
    if phase == "start":
        _state["gc_start"] = _perf()
        return
    n = GC.claim()
    if n < 0:
        return
    t0 = _state["gc_start"]
    c = GC.cols
    c["p0"][n] = t0
    c["dur"][n] = _perf() - t0
    c["gen"][n] = info.get("generation", -1)
    c["collected"][n] = info.get("collected", -1)
    c["test"][n] = _state["test"]


def _gc_since(first, t_from):
    total = gen2 = 0.0
    c = GC.cols
    for i in range(first, GC.n):
        if c["p0"][i] >= t_from:
            total += c["dur"][i]
            if c["gen"][i] == 2:
                gen2 += c["dur"][i]
    return total, gen2


def _tick(loop, due):
    now = loop.time()
    lag = now - due
    if lag >= LAG_S:
        n = LAG.claim()
        if n >= 0:
            LAG.cols["p"][n] = _perf()
            LAG.cols["lag"][n] = lag
            LAG.cols["test"][n] = _state["test"]
    nxt = now + TICK_S
    _loops[loop] = loop.call_at(nxt, _tick, loop, nxt, context=contextvars.Context())


def _ensure_sampler():
    loop = asyncio.get_running_loop()
    if loop not in _loops:
        due = loop.time() + TICK_S
        # A fresh empty context: the tick must not inherit the window that started it.
        _loops[loop] = loop.call_at(due, _tick, loop, due, context=contextvars.Context())


def _instant(kind, pid=-1):
    w = _WINV.get()
    if w < 0:
        return
    n = EV.claim()
    if n < 0:
        return
    c = EV.cols
    p = _perf()
    c["win"][n], c["kind"][n], c["pid"][n] = w, K[kind], pid
    c["p0"][n] = c["p1"][n] = p
    c["epoch0"][n] = time.time()
    for f in ("c0", "c1", "rq0", "rq1"):
        c[f][n] = NAN
    c["gc_s"][n] = 0.0
    c["outcome"][n] = c["sqlk"][n] = 0


def _stage(cls, name, kind, sql_arg=None):
    original = getattr(cls, name)

    async def observed(self, *args, **kwargs):
        w = _WINV.get()
        if w < 0:
            return await original(self, *args, **kwargs)
        n = EV.claim()
        if n < 0:
            return await original(self, *args, **kwargs)
        c = EV.cols
        c["win"][n], c["kind"][n], c["pid"][n] = w, K[kind], -1
        if sql_arg == "arg0":
            c["sqlk"][n] = _sql_kind(args[0] if args else kwargs.get("query"))
        elif sql_arg == "self":
            c["sqlk"][n] = _sql_kind(getattr(self, "_query", None))
        else:
            c["sqlk"][n] = 0
        gc_first = GC.n
        c["epoch0"][n] = time.time()
        c["rq0"][n] = _rq_ns()
        c["c0"][n] = _cpu()
        c["p0"][n] = p0 = _perf()
        outcome = 0
        try:
            return await original(self, *args, **kwargs)
        except BaseException as exc:
            outcome = _outcome(exc)
            raise
        finally:
            c["p1"][n] = _perf()
            c["c1"][n] = _cpu()
            c["rq1"][n] = _rq_ns()
            c["outcome"][n] = outcome
            c["gc_s"][n] = _gc_since(gc_first, p0)[0]

    observed.__name__ = name
    setattr(cls, name, observed)


def _window(store, code, name):
    original = getattr(store, name)

    async def observed(self, *args, **kwargs):
        n = WIN.claim()
        if n < 0:
            return await original(self, *args, **kwargs)
        _ensure_sampler()
        c = WIN.cols
        task = asyncio.current_task()
        c["method"][n], c["test"][n] = code, _state["test"]
        c["cancelling"][n] = task.cancelling() if task is not None else -1
        gc_first = GC.n
        c["epoch0"][n] = time.time()
        c["rq0"][n] = _rq_ns()
        c["iv0"][n] = _nivcsw()
        c["c0"][n] = _cpu()
        c["p0"][n] = p0 = _perf()
        token = _WINV.set(n)
        outcome = 0
        try:
            return await original(self, *args, **kwargs)
        except BaseException as exc:
            outcome = _outcome(exc)
            raise
        finally:
            c["p1"][n] = _perf()
            c["c1"][n] = _cpu()
            c["rq1"][n] = _rq_ns()
            c["iv1"][n] = _nivcsw()
            _WINV.reset(token)
            c["outcome"][n] = outcome
            c["gc_s"][n], c["gc2_s"][n] = _gc_since(gc_first, p0)

    observed.__name__ = name
    setattr(store, name, observed)


def _server_pid(dbapi_conn):
    try:
        return int(dbapi_conn._connection.get_server_pid())
    except Exception:
        return -1


def _install():
    import asyncpg.connection as apg_conn
    import asyncpg.prepared_stmt as apg_ps
    import asyncpg.transaction as apg_tx
    from sqlalchemy import event
    from sqlalchemy.pool import Pool
    from app.services import dnpl_authority

    for code, name in enumerate(METHODS):
        _window(dnpl_authority.AuthorityStore, code, name)
    _stage(apg_tx.Transaction, "start", "BEGIN")
    _stage(apg_tx.Transaction, "commit", "COMMIT")
    _stage(apg_tx.Transaction, "rollback", "ROLLBACK")
    _stage(apg_conn.Connection, "prepare", "prepare", sql_arg="arg0")
    _stage(apg_conn.Connection, "reload_schema_state", "reload_schema_state")
    _stage(apg_ps.PreparedStatement, "fetch", "fetch", sql_arg="self")

    event.listen(Pool, "checkout", lambda d, r, p: _instant("pool.checkout", _server_pid(d)))
    event.listen(Pool, "checkin", lambda d, r: _instant("pool.checkin"))
    event.listen(Pool, "reset", lambda d, r, s: _instant("pool.reset"))
    event.listen(Pool, "invalidate", lambda d, r, e: _instant("pool.invalidate"))
    event.listen(Pool, "connect", lambda d, r: _instant("pool.connect", _server_pid(d)))


def pytest_configure(config):
    _anchor("configure")
    gc.callbacks.append(_gc_cb)


def pytest_collection_finish(session):
    # Test modules have already imported the app; patching here keeps import order.
    _install()
    _anchor("collection_finish")


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    ix = _test_ix.get(item.nodeid)
    if ix is None:
        ix = _test_ix[item.nodeid] = len(TESTS)
        TESTS.append(item.nodeid)
    _state["test"] = ix
    n = TESTS_T.claim()
    _state["row"] = n
    if n >= 0:
        c = TESTS_T.cols
        c["setup_p"][n] = _perf()
        c["g0"][n], c["g1"][n], c["g2"][n] = gc.get_count()
        for f in ("call_p", "teardown_p", "end_p"):
            c[f][n] = NAN


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call(item):
    if _state["row"] >= 0:
        TESTS_T.cols["call_p"][_state["row"]] = _perf()


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_teardown(item, nextitem):
    if _state["row"] >= 0:
        TESTS_T.cols["teardown_p"][_state["row"]] = _perf()


def pytest_runtest_logreport(report):
    if report.when != "teardown":
        return
    if _state["row"] >= 0:
        TESTS_T.cols["end_p"][_state["row"]] = _perf()
    for loop, handle in list(_loops.items()):
        handle.cancel()
        del _loops[loop]


def pytest_unconfigure(config):
    _anchor("unconfigure")
    tables = {"gc": GC, "tests_t": TESTS_T, "windows": WIN, "events": EV, "lags": LAG}
    payload = {
        "meta": {
            "python": sys.version,
            "schedstat": _HAS_SCHED,
            "rusage_thread": _RUSAGE is not None,
            "gc_threshold": gc.get_threshold(),
            "gc_count_end": gc.get_count(),
            "gc_stats_end": gc.get_stats(),
            "gc_frozen_end": gc.get_freeze_count(),
            "anchors_label_perf_epoch_monotonic": ANCHORS,
            "retained_buffer_bytes": sum(t.nbytes() for t in tables.values()),
            "caps": {k: t.cap for k, t in tables.items()},
            "overflow": {k: t.over for k, t in tables.items()},
            "methods": METHODS,
            "kinds": KINDS,
            "sql_kinds": SQL_KINDS,
            "outcomes": OUTCOMES,
            "tick_s": TICK_S,
            "lag_threshold_s": LAG_S,
            "boundary": "instrumented CI test process, not production timing",
        },
        "tests": TESTS,
    }
    payload.update({k: t.dump() for k, t in tables.items()})
    text = json.dumps(payload, allow_nan=False)
    # Redaction control: the observer never stores SQL text, parameters or URLs.
    url = os.environ.get("SEARCH_TEST_DATABASE_URL", "")
    secret = url.split("@")[0] if "@" in url else ""
    leaked = bool(secret) and (secret in text or secret.rsplit(":", 1)[-1] + "@" in text)
    payload["meta"]["redaction_ok"] = not leaked
    if leaked:
        payload = {"meta": {"redaction_ok": False, "note": "payload withheld"}}
    with open(OUT, "w") as fh:
        json.dump(payload, fh, allow_nan=False)
