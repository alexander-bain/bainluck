"""#10090 — the Polymarket tail rotation: dark, its own task, the socket's
pairing and book rule, D1 (a refused book is counted, never replaced), D2 (the
900 s / 0.03 history bound), the P4 agreement counters, and a rotation that
completes and resumes from its cursor.

The writes themselves (write-on-change, the ``fetched_at`` newer-writer guard,
``FOR NO KEY UPDATE SKIP LOCKED``) are proved against real Postgres in
``tests/integration/test_futures_price_refresh_writes_pg.py`` (``tail_``).
"""

from __future__ import annotations

import inspect
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.tasks import venue_poll_30s as v
from app.tasks import venue_poll_pm_tail as tail
from app.tasks.polymarket_open_contracts import OpenContractLegs

# ── the switch, the task, the beat ────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, "off"),
        ("", "off"),
        ("0", "off"),
        ("off", "off"),
        ("bogus", "off"),
        ("shadow", "shadow"),
        (" Shadow ", "shadow"),
        ("1", "write"),
        ("on", "write"),
        ("true", "write"),
    ],
)
def test_the_switch_is_off_unless_it_says_shadow_or_on(raw, expected):
    env = {} if raw is None else {tail.ENABLED_ENV: raw}
    assert tail.tail_mode(env) == expected


def test_a_dark_tick_body_touches_neither_redis_nor_the_database(monkeypatch):
    from app import tasks

    monkeypatch.delenv(tail.ENABLED_ENV, raising=False)

    def explode(*_a, **_k):
        raise AssertionError("a dark tick must not take a lease, open a session or read Redis")

    monkeypatch.setattr("app.utils.single_flight.single_flight", explode)
    monkeypatch.setattr("app.tasks.base.get_task_session", explode)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", explode)
    monkeypatch.setattr(tail, "poll_tail", explode)
    assert tasks.poll_venue_prices_tail.run() == {"status": "disabled", "terminal": "complete"}


def test_the_beat_entry_is_every_three_minutes_on_heavy_with_its_own_lease():
    from celery.schedules import crontab

    from app.tasks import _crontab_period_seconds, celery_app, poll_venue_prices_tail

    entry = celery_app.conf.beat_schedule["poll-venue-prices-tail"]
    assert entry["task"] == "app.tasks.poll_venue_prices_tail"
    assert isinstance(entry["schedule"], crontab)
    assert _crontab_period_seconds(entry["schedule"]) == tail.CADENCE_S == 180
    assert entry["options"]["queue"] == "heavy"
    # Never the live queue, by route or by beat.
    assert celery_app.conf.task_routes.get("app.tasks.poll_venue_prices_tail") is None
    # The lease outlives the hard limit, and the pass fits inside the beat.
    assert poll_venue_prices_tail.time_limit < tail.LEASE_TTL_S
    assert tail.PASS_BUDGET_S < poll_venue_prices_tail.soft_time_limit <= tail.CADENCE_S
    source = inspect.getsource(poll_venue_prices_tail.run)
    assert '"app.tasks.poll_venue_prices_tail"' in source  # its own single-flight key


def test_the_tail_never_runs_inside_the_30_second_task(monkeypatch):
    from app import tasks
    from app.tasks import venue_poll_pm_clob

    for module in (v, venue_poll_pm_clob):
        assert "venue_poll_pm_tail" not in inspect.getsource(module)
    assert "venue_poll_pm_tail" not in inspect.getsource(tasks.poll_venue_prices_30s.run)

    # And running the 30-second task with the tail switched on never reaches it.
    monkeypatch.setenv(v.ENABLED_ENV, "polymarket")
    monkeypatch.setenv(tail.ENABLED_ENV, "1")

    def explode(*_a, **_k):
        raise AssertionError("the 30-second task called the tail")

    monkeypatch.setattr(tail, "poll_tail", explode)
    monkeypatch.setattr(tail, "rotate_tail", explode)

    class _Lease:
        acquired = True

    class _Flight:
        def __enter__(self):
            return _Lease()

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr("app.utils.single_flight.single_flight", lambda *_a, **_k: _Flight())

    async def stub(venues):
        return {"terminal": "complete", "venues": sorted(venues)}

    monkeypatch.setattr(v, "poll_venue_prices", stub)
    monkeypatch.setattr(tasks, "_tracked_run", lambda _name, coro: _run(coro))
    assert tasks.poll_venue_prices_30s.run() == {"terminal": "complete", "venues": ["polymarket"]}


def _run(coro):
    import asyncio

    return asyncio.new_event_loop().run_until_complete(coro)


# ── which scope, which population ─────────────────────────────────────────────


def test_the_scope_is_the_open_arms_as_this_process_reads_it(monkeypatch):
    from app.tasks import polymarket_open_contracts as poc

    monkeypatch.setattr(poc, "open_contract_prices_enabled", lambda: False)
    assert tail.socket_open_scope() == "off"
    monkeypatch.setattr(poc, "open_contract_prices_enabled", lambda: True)
    monkeypatch.delattr(poc, "open_contract_scope", raising=False)
    assert tail.socket_open_scope() == "all"  # before #11801 the arm is `all`
    monkeypatch.setattr(poc, "open_contract_scope", lambda: "slate", raising=False)
    assert tail.socket_open_scope() == "slate"


async def test_a_write_pass_under_scope_all_reads_nothing(monkeypatch):
    def explode(*_a, **_k):
        raise AssertionError("scope all: the socket carries the tail, nothing to read")

    monkeypatch.setattr(tail, "socket_open_scope", lambda: "all")
    monkeypatch.setattr("app.tasks.base.get_task_session", explode)
    monkeypatch.setattr(tail, "backoff_remaining", explode)
    stats = await tail.poll_tail(tail.MODE_WRITE)
    assert stats["stopped"] == "socket_carries_all" and stats["terminal"] == "complete"
    assert stats["scope"] == "all"


def test_the_candidate_read_renders_the_game_socket_window_and_the_shown_pool():
    from app.tasks.polymarket_ws import _slate_event_window

    window = v._render(_slate_event_window())
    without = tail.candidate_sql(exclude_shown=False)
    assert v._socket_game_sql(window) in without
    assert "pool" not in without and "market_metadata" not in without
    with_pool = tail.candidate_sql(exclude_shown=True)
    assert v._pool_sql("polymarket", window) in with_pool
    assert "fm.id NOT IN (SELECT id FROM pool)" in with_pool


def test_the_shown_pool_is_left_only_while_the_30_second_poll_runs_polymarket(monkeypatch):
    monkeypatch.setenv(v.ENABLED_ENV, "kalshi")
    assert tail.thirty_second_poll_takes_shown() is False
    monkeypatch.setenv(v.ENABLED_ENV, "1")
    assert tail.thirty_second_poll_takes_shown() is True


def test_the_metadata_read_is_the_socket_catalogs_columns_under_the_poll_liveness():
    from sqlalchemy.dialects import postgresql

    from app.utils.futures_liveness import LIVE_MARKET_SQL

    compiled = tail.markets_stmt([1, 2]).compile(dialect=postgresql.dialect())
    sql = str(compiled)
    keys = sorted(v for k, v in compiled.params.items() if k.startswith("market_metadata"))
    assert keys == ["clobTokenIds", "clob_token_ids", "clob_yes_token_by_outcome"]
    assert LIVE_MARKET_SQL.strip()[:40] in sql
    assert "fm.id = ANY (" in sql


# ── tokens: the socket's pairing ──────────────────────────────────────────────


def _legs(rows):
    legs = OpenContractLegs()
    for oid, mid, ext, graded in rows:
        legs.add(oid, mid, ext, graded)
    return legs


def test_tokens_come_from_persisted_metadata_paired_by_the_sockets_rule():
    market_rows = [
        # A binary, stored No-first: paired in token order, token 0 is the Yes book.
        (1, ["tok-a0", "tok-a1"], None, None),
        # A field: per-outcome Yes tokens.
        (2, None, None, {"21": "tok-b", "22": "tok-c", "23": "tok-g"}),
        # Three tokens, two legs, no per-outcome key: unpaired, never guessed.
        (3, ["x", "y", "z"], None, None),
        # A legacy JSON-string token list.
        (4, '["tok-d0", "tok-d1"]', None, None),
    ]
    legs = _legs([
        (12, 1, "0xa_no", False), (11, 1, "0xa_yes", False),
        (21, 2, "0xb", False), (22, 2, "0xc", False), (23, 2, "0xg", True),
        (31, 3, "0xe_yes", False), (32, 3, "0xe_no", False),
        (41, 4, "0xd_yes", False), (42, 4, "0xd_no", False),
    ])
    units, token_of, counts = tail.build_tail(market_rows, legs)
    assert [(u.key, u.legs) for u in units] == [
        ("1", {1: [(12, "0xa_no"), (11, "0xa_yes")]}),
        ("2", {2: [(21, "0xb"), (22, "0xc")]}),
        ("4", {4: [(41, "0xd_yes"), (42, "0xd_no")]}),
    ]
    assert token_of == {"0xa": "tok-a0", "0xb": "tok-b", "0xc": "tok-c", "0xd": "tok-d0"}
    assert counts["markets_unpaired"] == 1 and counts["legs_graded"] == 1


def test_no_gamma_read_ever():
    source = inspect.getsource(tail)
    for gamma in ("get_markets_by_conditions", "resolve_tokens", "_fetch_polymarket_prices"):
        assert gamma not in source


# ── pricing: D1 and the socket's book rule ────────────────────────────────────


def test_a_refused_book_is_counted_and_gives_no_item():
    units = [v.Unit("1", {1: [(11, "0xa"), (12, "0xb"), (13, "0xc"), (14, "0xd"), (15, "0xe")]})]
    token_of = {c: f"t{c}" for c in ("0xa", "0xb", "0xc", "0xd", "0xe")}
    tops = {
        "t0xa": (0.42, 0.50),  # usable
        "t0xb": (None, 0.03),  # no bid
        "t0xc": (0.10, 0.60),  # wide (#1578)
        "t0xd": (0.55, 0.50),  # crossed
        # t0xe: the CLOB did not answer
    }
    stats: dict = {}
    found = tail.price_group(units, token_of, tops, stats)
    assert [i["external_id"] for i in found["1"]] == ["0xa"]
    assert found["1"][0]["probability"] == pytest.approx(0.46)
    assert stats == {
        "tail_book_refused": 3,
        "tail_book_refused_no_book": 1,
        "tail_book_refused_wide": 1,
        "tail_book_refused_crossed": 1,
        "tail_tokens_absent": 1,
    }


def test_the_no_leg_is_token_zeros_complement():
    units = [v.Unit("1", {1: [(11, "0xa_yes"), (12, "0xa_no")]})]
    (item,) = tail.price_group(units, {"0xa": "t0"}, {"t0": (0.60, 0.62)}, {})["1"]
    assert item["probability"] == pytest.approx(0.61)
    assert item["no"]["probability"] == pytest.approx(0.39)
    assert (item["no"]["yes_bid"], item["no"]["yes_ask"]) == (pytest.approx(0.38), pytest.approx(0.40))


# ── P4: the agreement counters ────────────────────────────────────────────────


def test_agreement_is_graded_only_against_a_row_written_within_60_s():
    t = datetime(2026, 10, 30, 20, 0, tzinfo=timezone.utc)
    units = [v.Unit("1", {1: [(11, "0xa_yes"), (12, "0xa_no")]}), v.Unit("2", {2: [(21, "0xb")]}),
             v.Unit("3", {3: [(31, "0xc")]})]
    found = {
        "1": tail.price_group(units[:1], {"0xa": "t"}, {"t": (0.60, 0.62)}, {})["1"],
        "2": tail.price_group(units[1:2], {"0xb": "t"}, {"t": (0.20, 0.22)}, {})["2"],
        "3": tail.price_group(units[2:], {"0xc": "t"}, {"t": (0.50, 0.52)}, {})["3"],
    }
    rows = {
        11: (0.605, 0.60, 0.62, t - timedelta(seconds=59)),  # agree (0.005), fresh
        12: (0.40, 0.38, 0.40, t + timedelta(seconds=5)),    # agree (0.01), newer than the read
        21: (0.25, 0.24, 0.26, t - timedelta(seconds=10)),   # disagree (0.04)
        31: (0.51, 0.50, 0.52, t - timedelta(seconds=61)),   # stale: unreferenced
    }
    stats: dict = {}
    differ = tail.grade_against_rows(units, found, rows, t, stats)
    assert stats == {"tail_agree": 2, "tail_disagree": 1, "tail_unreferenced": 1}
    assert differ == 3  # 31 equals its row exactly; the rest would move


# ── D2: the history bound ─────────────────────────────────────────────────────


def test_the_tail_history_bound_is_900_s_or_a_three_point_move():
    assert (tail.HISTORY_MIN_INTERVAL_S, tail.HISTORY_BIG_MOVE) == (900.0, 0.03)
    now = datetime(2026, 10, 30, 20, 0, tzinfo=timezone.utc)
    poll = v.PollWrite(fetched_at=now, now=now, stored={}, allowed=frozenset(),
                       min_interval_s=tail.HISTORY_MIN_INTERVAL_S, big_move=tail.HISTORY_BIG_MOVE)
    ten_min, sixteen_min = now - timedelta(minutes=10), now - timedelta(minutes=16)
    assert poll.point_due((ten_min, 0.50), 0.52) == "deferred"  # the 30 s poll would write it
    assert poll.point_due((ten_min, 0.50), 0.53) == "big_move"
    assert poll.point_due((sixteen_min, 0.50), 0.51) == "interval"
    assert poll.point_due((sixteen_min, 0.50), 0.50) is None
    # The 30-second poll's own bound is untouched.
    default = v.PollWrite(fetched_at=now, now=now, stored={}, allowed=frozenset())
    assert (default.min_interval_s, default.big_move) == (v.HISTORY_MIN_INTERVAL_S, v.HISTORY_BIG_MOVE)
    assert default.point_due((ten_min, 0.50), 0.52) == "interval"


# ── the rotation ──────────────────────────────────────────────────────────────


class _Service:
    def __init__(self, tops, *, raise_on=None):
        self.tops = tops
        self.raise_on = raise_on or {}
        self.reads: list[list[str]] = []

    async def get_book_tops(self, tokens):
        self.reads.append(list(tokens))
        for token in tokens:
            if token in self.raise_on:
                raise self.raise_on[token]
        return {t: self.tops[t] for t in tokens if t in self.tops}


def _units(n):
    return [v.Unit(str(k), {k: [(k * 10, f"0x{k:02x}")]}) for k in range(1, n + 1)]


def _token_of(n):
    return {f"0x{k:02x}": f"t{k}" for k in range(1, n + 1)}


def _wire(monkeypatch, *, cursor=None):
    state = {"cursor": cursor, "cursors": [], "backoffs": [], "cleared": []}
    monkeypatch.setattr(tail, "read_cursor", lambda name: state["cursor"] if name == tail.CURSOR else None)

    def write_cursor(name, key):
        state["cursors"].append((name, key))
        if key is not None:
            state["cursor"] = key

    monkeypatch.setattr(tail, "write_cursor", write_cursor)
    monkeypatch.setattr(tail, "start_backoff", lambda venue: state["backoffs"].append(venue) or 30)
    monkeypatch.setattr(tail, "clear_backoff", lambda venue: state["cleared"].append(venue))
    writes = []

    async def write_group(_session, venue, group_units, found, fetched_at, stats, *, history=None):
        writes.append((venue, [u.key for u in group_units], found, history))

    async def read_reference(_session, _group_units):
        return {}

    monkeypatch.setattr(tail, "_write_group", write_group)
    monkeypatch.setattr(tail, "read_reference", read_reference)
    return state, writes


async def _rotate(service, units, token_of, *, mode="write", budget_s=20.0):
    stats = {"errors": []}
    await tail.rotate_tail(None, service, units, token_of, mode=mode,
                           deadline=time.monotonic() + budget_s, offset=0.0, stats=stats)
    return stats


async def test_a_rotation_larger_than_a_pass_resumes_from_its_cursor_and_wraps(monkeypatch):
    state, writes = _wire(monkeypatch)
    monkeypatch.setattr(tail, "CLOB_TOKENS_PER_REQUEST", 1)
    monkeypatch.setattr(tail, "REQUESTS_PER_PASS", 2)
    units, token_of = _units(5), _token_of(5)
    service = _Service({t: (0.40, 0.42) for t in token_of.values()})
    keys = []
    for _ in range(3):
        stats = await _rotate(service, units, token_of)
        assert stats["stopped"] == "done"
        keys.append([k for _v, ks, _f, _h in writes for k in ks])
        writes.clear()
    assert keys == [["1", "2"], ["3", "4"], ["5", "1"]]
    assert [c for _n, c in state["cursors"]] == ["2", "4", "1"]


async def test_a_rotation_inside_the_budget_completes_every_unit_in_one_pass(monkeypatch):
    state, writes = _wire(monkeypatch, cursor="3")
    units, token_of = _units(5), _token_of(5)
    service = _Service({t: (0.40, 0.42) for t in token_of.values()})
    stats = await _rotate(service, units, token_of)
    assert stats["stopped"] == "done" and stats["units_done"] == 5
    assert [k for _v, ks, _f, _h in writes for k in ks] == ["4", "5", "1", "2", "3"]
    assert service.reads == [["t4", "t5", "t1", "t2", "t3"]]  # one read, 250 tokens a read
    assert state["cursors"] == [(tail.CURSOR, "3")]


async def test_a_write_pass_passes_the_tail_history_bound(monkeypatch):
    _state, writes = _wire(monkeypatch)
    units, token_of = _units(1), _token_of(1)
    await _rotate(_Service({"t1": (0.40, 0.42)}), units, token_of)
    ((venue, _keys, found, history),) = writes
    assert venue == "polymarket" and history == (900.0, 0.03)
    assert found["1"][0]["external_id"] == "0x01"


async def test_the_30_second_polls_group_write_keeps_its_own_history_bound(monkeypatch):
    """``_write_group`` without ``history`` writes with the 30-second poll's
    bound, never the tail's (latency R1 on #11808)."""
    seen = []

    class _Session:
        async def commit(self):
            return None

    async def load_state(_session, ids):
        return {oid: (0.30, 0.29, 0.31) for oid in ids}

    async def write_market(_session, *, poll, **_k):
        seen.append((poll.min_interval_s, poll.big_move))

    monkeypatch.setattr(v, "load_state", load_state)
    monkeypatch.setattr(v, "write_market", write_market)
    monkeypatch.setattr(v.DeferredPoints, "read", classmethod(lambda cls, ids: cls()))
    monkeypatch.setattr(v.DeferredPoints, "save", lambda self: None)
    units = _units(1)
    found = {"1": [{"external_id": "0x01", "probability": 0.40, "yes_bid": 0.40, "yes_ask": 0.42}]}
    now = datetime.now(timezone.utc)
    stats = {"errors": []}
    await v._write_group(_Session(), "polymarket", units, found, now, stats)
    await v._write_group(_Session(), "polymarket", units, found, now, stats,
                         history=(tail.HISTORY_MIN_INTERVAL_S, tail.HISTORY_BIG_MOVE))
    assert seen == [(v.HISTORY_MIN_INTERVAL_S, v.HISTORY_BIG_MOVE), (900.0, 0.03)]
    assert v.HISTORY_MIN_INTERVAL_S != 900.0


async def test_a_shadow_pass_writes_nothing_and_counts_what_it_would_write(monkeypatch):
    _state, writes = _wire(monkeypatch)
    now = datetime.now(timezone.utc)

    async def read_reference(_session, _group_units):
        return {10: (0.30, 0.29, 0.31, now), 20: (0.41, 0.40, 0.42, now)}

    monkeypatch.setattr(tail, "read_reference", read_reference)
    units, token_of = _units(2), _token_of(2)
    stats = await _rotate(_Service({"t1": (0.40, 0.42), "t2": (0.40, 0.42)}), units, token_of,
                          mode=tail.MODE_SHADOW)
    assert writes == []
    assert stats["tail_would_write"] == 1
    assert stats["tail_agree"] == 1 and stats["tail_disagree"] == 1


def _rate_limited():
    request = httpx.Request("POST", "https://clob.polymarket.com/prices")
    return httpx.HTTPStatusError("429", request=request, response=httpx.Response(429, request=request))


async def test_a_429_backs_off_this_rotation_only_and_keeps_the_cursors_place(monkeypatch):
    state, writes = _wire(monkeypatch, cursor="1")
    units, token_of = _units(3), _token_of(3)
    stats = await _rotate(_Service({}, raise_on={"t2": _rate_limited()}), units, token_of)
    assert stats["stopped"] == "rate_limited"
    assert state["backoffs"] == [tail.BACKOFF_VENUE] != ["polymarket_clob"]
    assert writes == [] and state["cursors"] == [(tail.CURSOR, None)] and state["cursor"] == "1"
    assert state["cleared"] == []


async def test_a_group_that_keeps_failing_is_passed_never_a_wedge(monkeypatch):
    state, writes = _wire(monkeypatch)
    monkeypatch.setattr(tail, "CLOB_TOKENS_PER_REQUEST", 1)
    monkeypatch.setattr(tail, "CONCURRENCY", 1)
    units, token_of = _units(3), _token_of(3)
    service = _Service({"t2": (0.4, 0.42), "t3": (0.4, 0.42)}, raise_on={"t1": RuntimeError("500")})
    stats = await _rotate(service, units, token_of)
    assert stats["stopped"] == "fetch_error" and stats["tail_groups_failed"] == 1
    assert state["cursors"] == [(tail.CURSOR, "1")]  # past the failed group
    stats = await _rotate(service, units, token_of)
    assert [k for _v, ks, _f, _h in writes for k in ks] == ["2", "3"]


async def test_no_read_starts_past_the_pass_budget(monkeypatch):
    state, writes = _wire(monkeypatch)
    units, token_of = _units(1), _token_of(1)
    service = _Service({"t1": (0.4, 0.42)})
    stats = await _rotate(service, units, token_of, budget_s=v._MIN_REQUEST_S - 0.5)
    assert stats["stopped"] == "budget" and service.reads == [] and writes == []
    assert state["cursors"] == [(tail.CURSOR, None)]


@pytest.mark.parametrize("venue", [tail.BACKOFF_VENUE, "polymarket_clob"])
async def test_the_tail_stands_down_while_either_clob_backoff_runs(monkeypatch, venue):
    def explode(*_a, **_k):
        raise AssertionError("a backed-off pass must not open a session")

    monkeypatch.setattr(tail, "socket_open_scope", lambda: "slate")
    monkeypatch.setattr(tail, "backoff_remaining", lambda name: 25.0 if name == venue else 0.0)
    monkeypatch.setattr("app.tasks.base.get_task_session", explode)
    stats = await tail.poll_tail(tail.MODE_WRITE)
    assert stats["stopped"] == "backoff" and stats["backoff_venue"] == venue


async def test_an_empty_tail_is_a_complete_pass_that_says_what_it_read(monkeypatch):
    from contextlib import asynccontextmanager

    reads = []

    class _Session:
        async def commit(self):
            return None

        async def execute(self, _stmt, _binds=None):
            class _R:
                @staticmethod
                def scalar_one():
                    return datetime.now(timezone.utc)

            return _R()

    @asynccontextmanager
    async def session(**_k):
        yield _Session()

    async def load(_session, *, exclude_shown, now_mono):
        reads.append(exclude_shown)
        return [], {}, {"candidate_markets": 0}

    monkeypatch.setattr(tail, "socket_open_scope", lambda: "slate")
    monkeypatch.setattr(tail, "backoff_remaining", lambda _name: 0.0)
    monkeypatch.setattr(tail, "thirty_second_poll_takes_shown", lambda: True)
    monkeypatch.setattr("app.tasks.base.get_task_session", session)
    monkeypatch.setattr(tail, "load_tail_population", load)
    stats = await tail.poll_tail(tail.MODE_SHADOW)
    assert stats["stopped"] == "empty" and stats["terminal"] == "complete"
    assert stats["shown_left_to_30s_poll"] is True and reads == [True]
    assert stats["mode"] == "shadow" and stats["scope"] == "slate"


async def test_a_failed_population_re_read_keeps_the_last_population(monkeypatch):
    class _Session:
        rolled_back = 0

        async def rollback(self):
            self.rolled_back += 1

    calls = []

    async def read(_session, exclude_shown):
        calls.append(exclude_shown)
        if len(calls) > 1:
            raise TimeoutError("canceling statement due to statement timeout")
        return _units(2), _token_of(2), {"candidate_markets": 2}

    monkeypatch.setattr(tail, "_POPULATION", {})
    monkeypatch.setattr(tail, "_read_tail_population", read)
    session = _Session()
    first = await tail.load_tail_population(session, exclude_shown=False, now_mono=0.0)
    assert first[2]["cached"] == 0 and first[2]["read_s"] >= 0
    cached = await tail.load_tail_population(session, exclude_shown=False, now_mono=10.0)
    assert cached[:2] == first[:2] and calls == [False]  # inside the TTL: no read
    assert cached[2]["cached"] == 1 and "read_s" not in cached[2]
    units, token_of, counts = await tail.load_tail_population(
        session, exclude_shown=False, now_mono=tail.POPULATION_TTL_S + 1)
    assert [u.key for u in units] == ["1", "2"] and token_of == _token_of(2)
    assert counts["reread_failed"] == 1 and counts["cached"] == 1 and session.rolled_back == 1
    # A failed re-read is not re-run by the next 3-minute pass, only after a TTL.
    await tail.load_tail_population(
        session, exclude_shown=False, now_mono=tail.POPULATION_TTL_S + 1 + tail.CADENCE_S)
    assert len(calls) == 2
    await tail.load_tail_population(
        session, exclude_shown=False, now_mono=2 * tail.POPULATION_TTL_S + 2)
    assert len(calls) == 3

    monkeypatch.setattr(tail, "_POPULATION", {})
    with pytest.raises(TimeoutError):  # nothing to keep: the pass fails, counted
        await tail.load_tail_population(session, exclude_shown=False, now_mono=0.0)
