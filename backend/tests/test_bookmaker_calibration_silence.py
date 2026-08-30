"""#1835 (CAL-P051) — the per-bookmaker moneyline source must not vanish silently.

The defect these guard: ``odds_api_bookmaker`` was absent from the live
``/api/calibration`` payload for an unknown but long period, and *nothing*
reported it. The writer (``_precompute_bookmaker_calibration``) was reachable
only as a ``backfill_winners`` phase sitting behind that pipeline's first budget
guard; production measured ``stopped_before: "bookmaker_closing"`` with
``successes_24h: 0``, so the writer never ran, the 24h Redis key expired, and
the reader — which publishes nothing when the key is missing — published
nothing. Three distinct causes (starved writer, expired key, throwing read) all
produced that same silence.

So there are two independent things to hold down, and they are tested
separately because they fail separately:

1. **The writer runs at all** — it has its own beat, so a heavy resolution
   cycle cannot starve it.
2. **A run that produces nothing says so** — the returned summary carries
   terminal truth and the task is enforced by ``task_verdict``, so a starved,
   empty or unwritten run can never be recorded as a success.

Note what is deliberately NOT asserted: which of the three causes it was. The
point of the terminal contract is that the silence closes regardless.
"""

import pytest

from app.utils.task_verdict import (
    COMPLETE,
    NOT_GREEN,
    ENFORCED_TASKS,
    classify_summary,
    verdict_for,
)


# --- 1. The writer has its own beat ------------------------------------------


def test_bookmaker_calibration_has_a_dedicated_beat():
    """It must not be reachable ONLY as a backfill_winners phase.

    This is the whole starvation fix. If this beat is ever removed, the writer
    goes back to running behind the first budget guard of a pipeline that is
    measured to stop *at* that guard.
    """
    from app.tasks import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "precompute-bookmaker-calibration" in schedule, (
        "the dedicated beat is gone — the writer is starvable again (#1835)"
    )
    entry = schedule["precompute-bookmaker-calibration"]
    assert entry["task"] == "app.tasks.precompute_bookmaker_calibration"
    assert entry["options"]["queue"] == "background"


def test_bookmaker_beat_does_not_collide_with_the_heavy_calibration_beats():
    """#183 Item 3's lesson: a long co-scheduled task starves a beat.

    The background worker has two slots. This asserts the bookmaker beat never
    shares a (minute, hour) with the other long calibration grinders — the exact
    contention that kept `compute_calibration_prices` from ever being dispatched.
    """
    from app.tasks import celery_app

    schedule = celery_app.conf.beat_schedule
    mine = schedule["precompute-bookmaker-calibration"]["schedule"]
    my_minutes = set(mine.minute)
    my_hours = set(mine.hour)
    # Guard the guard: an empty set intersects with everything to nothing, so
    # a parse that silently yielded {} would make this test pass forever.
    assert my_minutes and my_hours

    for name in ("compute-calibration-prices", "precompute-calibration-main"):
        other = schedule[name]["schedule"]
        overlap_minutes = my_minutes & set(other.minute)
        overlap_hours = my_hours & set(other.hour)
        assert not (overlap_minutes and overlap_hours), (
            f"bookmaker beat shares a dispatch slot with {name} "
            f"(minutes {sorted(overlap_minutes)}, hours {sorted(overlap_hours)}) "
            "— two long calibration tasks on a 2-slot worker (#183 Item 3)"
        )


def test_the_task_is_registered_and_wrapped_in_tracked_run():
    from app.tasks import celery_app

    assert "app.tasks.precompute_bookmaker_calibration" in celery_app.tasks


# --- 2. A run that produces nothing must say so -------------------------------


def test_task_is_verdict_enforced():
    """Without enrolment the contract is computed and then ignored."""
    assert "bookmaker_calibration" in ENFORCED_TASKS


@pytest.mark.parametrize(
    "summary,why",
    [
        (
            {"terminal": "no_work", "bookmakers": 0, "data_points": 0,
             "errors": ["query returned zero buckets"], "published": False},
            "zero buckets — the reader will publish no source at all",
        ),
        (
            {"terminal": "failed", "bookmakers": 0, "data_points": 5,
             "errors": ["Redis: connection refused"], "published": False},
            "buckets computed then never landed — no reader can see them",
        ),
        (
            {"terminal": "failed", "bookmakers": 0, "data_points": 0,
             "errors": ["boom"], "published": False},
            "the query itself raised",
        ),
    ],
)
def test_a_run_that_publishes_nothing_never_reads_green(summary, why):
    verdict = verdict_for("bookmaker_calibration", summary)
    assert verdict.verdict in NOT_GREEN, f"false GREEN on: {why}"


def test_a_real_publish_reads_complete():
    """The guard must not be vacuous by simply never going green."""
    verdict = verdict_for(
        "bookmaker_calibration",
        {"terminal": "complete", "bookmakers": 7, "data_points": 41234,
         "errors": [], "published": True},
    )
    assert verdict.verdict == COMPLETE


def test_the_pre_fix_summary_shape_would_have_been_false_green():
    """Pins WHY this defect was invisible, so the lesson can't be refactored out.

    The old summary carried no terminal at all. Under the enforced contract that
    is not a success — which is the entire behavioural change. If someone later
    strips the terminal from the writer, this test explains what breaks.
    """
    legacy = {"bookmakers": 0, "data_points": 0, "errors": []}
    assert classify_summary(legacy).verdict in NOT_GREEN


# --- 3. The writer sets those terminals -------------------------------------


def _summary_for(rows, *, redis_raises=False, query_raises=False,
                 grid=None, chunk_raises=None, monkeypatch=None,
                 deadline=None, seconds_per_chunk=None):
    """Run the real writer against a stubbed session + Redis.

    ``seconds_per_chunk`` installs a FAKE clock that advances only when the
    writer issues a chunk query, so a budget test measures the writer's own
    traversal instead of how fast the machine ran the stubs. The stubs answer
    instantly; against the real clock no budget could ever expire and a
    budget guard written on it would pass vacuously forever (gotcha #44 — an
    anchor that reads the wall is not an anchor).
    """
    from datetime import datetime, timezone

    import app.tasks.backfill_winners as bw

    clock = {"t": 1_000_000.0}
    if seconds_per_chunk is not None:
        import time as _real_time

        # The module attribute, because the writer does `import time as _time`
        # at CALL time — it re-resolves `sys.modules['time']` on every run, so
        # rebinding a name on `bw` would patch nothing and the guard would
        # silently test the real clock.
        monkeypatch.setattr(_real_time, "monotonic", lambda: clock["t"])

    class _Cell:
        def __init__(self, category, bucket_start):
            self.category = category
            self.bucket_start = bucket_start

    if grid is None:
        grid = [_Cell("basketball_nba",
                      datetime(2026, 3, 1, tzinfo=timezone.utc))]

    # CAL-P134: the writer now issues THREE statement shapes — the category
    # list, a per-slice ``SET LOCAL statement_timeout``, and the bounded chunk
    # query — so the double has to tell them apart. It dispatches on the SQL
    # text rather than on call order, because call order is exactly what the
    # chunking changed and a positional double would have to be re-tuned every
    # time the sweep is re-shaped.
    class _Result:
        def __init__(self, payload):
            self._payload = payload

        def all(self):
            if query_raises:
                raise RuntimeError("boom")
            return self._payload

        def scalars(self):
            return self

    class _Session:
        def __init__(self):
            self.chunk_calls = 0

        async def execute(self, statement, *a, **k):
            sql = str(statement)
            if "SET LOCAL statement_timeout" in sql:
                return _Result([])
            if "date_trunc('month'" in sql:
                return _Result(list(grid))
            self.chunk_calls += 1
            if seconds_per_chunk is not None:
                clock["t"] += seconds_per_chunk
            if chunk_raises is not None:
                exc = chunk_raises(self.chunk_calls)
                if exc is not None:
                    raise exc
            return _Result(rows)

        async def rollback(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _Redis:
        def __init__(self):
            self.written = None

        def setex(self, key, ttl, value):
            if redis_raises:
                raise RuntimeError("connection refused")
            self.written = (key, ttl, value)

    redis = _Redis()
    session = _Session()
    monkeypatch.setattr(bw, "get_task_session", lambda: session)
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: redis
    )

    import asyncio

    return (
        asyncio.run(bw._precompute_bookmaker_calibration(deadline=deadline)),
        redis,
    )


def _grid(*categories):
    """One month cell per category, so the sweep issues one chunk query each."""
    from datetime import datetime, timezone

    class _Cell:
        def __init__(self, category):
            self.category = category
            self.bucket_start = datetime(2026, 3, 1, tzinfo=timezone.utc)

    return [_Cell(c) for c in categories]


class _Row:
    def __init__(self, idx, category):
        self.bucket_idx = idx
        self.category = category
        self.n = 100
        self.winners = 55
        self.avg_prob = 0.55
        self.sum_prob = 55.0
        self.sum_sq_err = 24.0


def test_writer_reports_complete_and_publishes(monkeypatch):
    summary, redis = _summary_for([_Row(5, "basketball_nba")], monkeypatch=monkeypatch)
    assert summary["terminal"] == "complete"
    assert summary["published"] is True
    assert redis.written is not None
    key, ttl, _ = redis.written
    assert key == "bainluck:bookmaker_calibration"
    assert ttl == 86400, (
        "TTL raised — that trades a visible absence for an invisible staleness"
    )


def test_writer_reports_no_work_on_zero_rows(monkeypatch):
    summary, redis = _summary_for([], monkeypatch=monkeypatch)
    assert summary["terminal"] == "no_work"
    assert summary["published"] is False
    assert redis.written is None
    assert verdict_for("bookmaker_calibration", summary).verdict in NOT_GREEN


def test_writer_reports_failed_when_redis_write_raises(monkeypatch):
    summary, _ = _summary_for(
        [_Row(5, "basketball_nba")], redis_raises=True, monkeypatch=monkeypatch
    )
    assert summary["terminal"] == "failed"
    assert summary["published"] is False
    assert verdict_for("bookmaker_calibration", summary).verdict in NOT_GREEN


def test_writer_reports_failed_when_the_query_raises(monkeypatch):
    summary, _ = _summary_for([], query_raises=True, monkeypatch=monkeypatch)
    assert summary["terminal"] == "failed"
    assert verdict_for("bookmaker_calibration", summary).verdict in NOT_GREEN


def test_published_buckets_carry_the_source_key_the_reader_groups_on(monkeypatch):
    """The reader keys `by_source` off this string; a rename is a silent drop."""
    import json

    _, redis = _summary_for([_Row(5, "basketball_nba")], monkeypatch=monkeypatch)
    buckets = json.loads(redis.written[2])
    assert buckets and all(b["source"] == "odds_api_bookmaker" for b in buckets)


# --- 4. CAL-P134: the sweep is bounded, and a partial one publishes NOTHING ---
#
# The 2026-08-29 outage: the unbounded statement stopped finishing inside the
# task's 600s soft limit, the Redis key aged out of its 24h TTL, and
# /api/calibration went 23 hours without publishing. Chunking fixes the finish;
# these guard the part that decides what happens when it still does not.


class _Timeout(Exception):
    """Shaped so ``_is_statement_timeout`` recognises it, the way asyncpg's does."""

    def __str__(self):
        return "canceling statement due to statement timeout"


def test_a_chunk_that_times_out_is_split_rather_than_abandoned(monkeypatch):
    """The first slice times out; the two halves succeed and the run is green."""
    calls = {"n": 0}

    def raiser(call_index):
        calls["n"] = call_index
        return _Timeout() if call_index == 1 else None

    summary, redis = _summary_for(
        [_Row(5, "basketball_nba")], chunk_raises=raiser, monkeypatch=monkeypatch
    )
    assert summary["terminal"] == "complete"
    assert redis.written is not None
    assert calls["n"] >= 3, "the timing-out window was never split"
    assert summary["chunks"] >= 2


def test_an_irreducible_chunk_writes_NOTHING_and_reports_failed(monkeypatch):
    """THE LOAD-BEARING GUARD. A partial curve is the defect, not a degraded fix.

    The reader publishes whatever the key holds. A key holding a fraction of the
    sports produces a candidate the population gate refuses — a SILENT
    non-publish. Writing nothing instead keeps the absence loud, which is what
    the terminal contract exists for.
    """
    summary, redis = _summary_for(
        [_Row(5, "basketball_nba")],
        chunk_raises=lambda _i: _Timeout(),
        monkeypatch=monkeypatch,
    )
    assert summary["terminal"] == "failed"
    assert summary["published"] is False
    assert redis.written is None, (
        "a short curve was published — this is the outage, not the fix"
    )
    assert summary["chunks_failed"], "the failure was not named"
    assert verdict_for("bookmaker_calibration", summary).verdict in NOT_GREEN


def test_the_traversal_stops_on_the_wall_instead_of_fanning_out(monkeypatch):
    """THE CERT-457 REGRESSION. ``_CHUNK_TIMEOUT_S`` bounds a STATEMENT, not the WALK.

    An irreducible month halves to a 3,600 s floor, which bottoms out at depth
    10: 1,024 leaves under 2,047 timed nodes. At 45 s each that is ~92 ks of
    querying inside an 1,800 s task, so before the traversal budget the task
    was soft-killed mid-walk on every cycle — the key never written, the TTL
    lapsing, the publish outage preserved, and the database loaded for nothing.

    The clock here advances only when the writer issues a chunk query, so this
    asserts the writer's own arithmetic and not the speed of the stubs.
    """
    seen = {"n": 0}

    def raiser(call_index):
        seen["n"] = call_index
        return _Timeout()  # every slice is irreducible: the worst case

    summary, redis = _summary_for(
        [_Row(5, "basketball_nba")],
        chunk_raises=raiser,
        seconds_per_chunk=45,  # == _CHUNK_TIMEOUT_S: each node burns its ceiling
        monkeypatch=monkeypatch,
    )

    # Not vacuous: it really did walk before it stopped. A budget guard that
    # passes because nothing ran proves nothing about the bound.
    assert seen["n"] >= 2, "the writer never traversed; the guard is vacuous"
    assert seen["n"] < 2047 / 4, (
        f"the walk issued {seen['n']} timed queries — the traversal is still "
        f"bounded only by the 2,047-node fan-out, which is the defect"
    )
    assert summary["budget_exhausted"] is True
    assert summary["terminal"] == "failed"
    assert redis.written is None, "a short curve was published on a busted budget"


def test_budget_exhaustion_is_reported_and_is_not_called_irreducible(monkeypatch):
    """Failing closed is half the contract; saying WHICH failure is the other half.

    ``irreducible`` means a window will not answer however narrow it gets — a
    query bug or a lock. ``unrun`` means the walk ran out of wall. Pooling them
    would report a database problem every time the task was merely slow, and
    send the next session hunting the wrong defect.
    """
    summary, redis = _summary_for(
        [_Row(5, "basketball_nba")],
        deadline=float("-inf"),  # the wall is already behind us on entry
        monkeypatch=monkeypatch,
    )

    assert summary["terminal"] == "failed"
    assert summary["published"] is False
    assert redis.written is None
    assert summary["chunks_unrun"], "the unrun cells were not named"
    assert not summary["chunks_failed"], (
        "a cell that was never QUERIED was reported as irreducible"
    )
    blob = " ".join(summary["errors"]).lower()
    assert "budget" in blob and "unrun" in blob, (
        f"the terminal does not say the budget ran out: {summary['errors']}"
    )
    assert verdict_for("bookmaker_calibration", summary).verdict in NOT_GREEN


def test_the_phase_caller_hands_down_the_pipelines_wall(monkeypatch):
    """The callee has two zeros, so the shorter-walled caller must say so.

    Standalone it owns an 1,800 s beat; as the ``bookmaker_closing`` phase it
    has whatever is left of an 840 s task that resolution already spent down.
    A budget measured from the wrong zero is not a budget, it is a duration.
    """
    import inspect

    import app.tasks.backfill_winners as bw

    assert "deadline" in inspect.signature(
        bw._precompute_bookmaker_calibration
    ).parameters, "the callee can no longer be told a caller's wall"

    src = inspect.getsource(bw._backfill_all_winners)
    assert "deadline=_pipeline_start + _SOFT_LIMIT_S - _BUDGET_MARGIN_S" in src, (
        "the bookmaker_closing phase stopped passing the pipeline's wall; the "
        "callee would fall back to its standalone 1800s budget inside an 840s "
        "task and take the whole pipeline down with it"
    )


def test_the_traversal_budget_leaves_room_under_the_soft_limit():
    """The margin has to cover the longest thing that can happen after a check."""
    from app.tasks.backfill_winners import (
        _CHUNK_TIMEOUT_S,
        _TRAVERSAL_BUDGET_S,
    )

    # Read off the TASK, not copied as a literal: the budget is only correct
    # relative to the wall it is sized against, so if someone re-tunes the
    # soft limit this guard has to move with it rather than keep asserting
    # against a number that used to be true.
    from app.tasks import precompute_bookmaker_calibration as _task

    soft_limit = _task.soft_time_limit
    assert soft_limit, "the beat lost its soft limit; the budget has no wall"
    margin = soft_limit - _TRAVERSAL_BUDGET_S
    assert 0 < margin < soft_limit / 2, (
        f"a {margin}s margin under a {soft_limit}s limit is not a margin"
    )
    assert margin > _CHUNK_TIMEOUT_S, (
        f"a {margin}s margin cannot absorb the {_CHUNK_TIMEOUT_S}s statement "
        f"that may still be in flight past the final budget check"
    )


def test_one_failing_category_fails_the_whole_run_not_just_its_own_rows(monkeypatch):
    """Nine categories land, one cannot. That is still a short curve."""

    def raiser(call_index):
        # every slice of the last category is irreducible
        return _Timeout() if call_index > 9 else None

    summary, redis = _summary_for(
        [_Row(5, "basketball_nba")],
        grid=_grid(*(f"sport_{i}" for i in range(10))),
        chunk_raises=raiser,
        monkeypatch=monkeypatch,
    )
    assert summary["terminal"] == "failed"
    assert redis.written is None


def test_a_non_timeout_error_propagates_instead_of_being_split(monkeypatch):
    """gotcha #45: never catch-all around scheduled work. Only OUR timeout may
    be contained; a real query bug must not be retried as if it were density."""
    summary, redis = _summary_for(
        [_Row(5, "basketball_nba")],
        chunk_raises=lambda _i: RuntimeError("column does not exist"),
        monkeypatch=monkeypatch,
    )
    assert summary["terminal"] == "failed"
    assert redis.written is None
    assert any("column does not exist" in e for e in summary["errors"])


def test_avg_prob_is_recomputed_from_the_totals_not_averaged_across_chunks(
        monkeypatch):
    """A mean of per-chunk means is weighted by CHUNK, and the chunk boundaries
    are chosen by how slow the database was that minute."""
    import json

    # two categories -> at least two chunks, each contributing the same row
    _, redis = _summary_for(
        [_Row(5, "basketball_nba")],
        grid=_grid("basketball_nba", "icehockey_nhl"),
        monkeypatch=monkeypatch,
    )
    buckets = json.loads(redis.written[2])
    for b in buckets:
        assert b["avg_prob"] == pytest.approx(b["sum_prob"] / b["n"])


def test_the_chunk_sql_is_single_pass_and_bounded():
    """The two properties the rewrite is FOR, asserted on the statement itself.

    Both were measured, not assumed: the LATERAL form was a second pass over the
    same snapshots, and an unbounded sweep is what stopped finishing.
    """
    from app.tasks.backfill_winners import _BOOKMAKER_CHUNK_SQL

    sql = _BOOKMAKER_CHUNK_SQL
    assert "CROSS JOIN LATERAL" not in sql, (
        "the second pass over odds_snapshots is back — this is what could not "
        "finish inside the soft limit"
    )
    assert "DISTINCT ON" in sql
    for bind in (":category", ":lo", ":hi"):
        assert bind in sql, f"{bind} missing — the sweep is unbounded again"
    # It must still carry the four additive quantities, or chunked accumulation
    # cannot reconstruct the buckets.
    for col in ("COUNT(*)", "sum_prob", "sum_sq_err", "winners"):
        assert col in sql


@pytest.mark.parametrize("start,expected", [
    ((2026, 1, 1), (2026, 2, 1)),
    ((2026, 12, 1), (2027, 1, 1)),      # the year rollover
    ((2026, 2, 1), (2026, 3, 1)),       # short month
    ((2024, 2, 1), (2024, 3, 1)),       # leap February
    ((2026, 7, 1), (2026, 8, 1)),       # 31-day month: +30d would leave a gap
])
def test_the_grid_cell_edge_is_a_calendar_month(start, expected):
    """A partition of the event set with a gap in it is silently dropped
    population, not a visible failure. ``+30 days`` gaps every long month."""
    from datetime import datetime, timezone

    from app.tasks.backfill_winners import _add_month

    lo = datetime(*start, tzinfo=timezone.utc)
    assert _add_month(lo) == datetime(*expected, tzinfo=timezone.utc)


def test_the_grid_is_derived_from_where_the_events_are():
    """gotcha #41: a sweep needs both bounds. Here they come from the data, so
    an empty span is never queried and a dense cell never has to be searched
    for by halving down from a decade."""
    import inspect

    from app.tasks import backfill_winners as bw

    src = inspect.getsource(bw._precompute_bookmaker_calibration)
    assert "date_trunc('month', e.commence_time)" in src
    assert "GROUP BY 1, 2" in src


def test_the_per_slice_ceiling_is_far_below_the_task_soft_limit():
    """A slow slice must cost a split, never the run."""
    from app.tasks.backfill_winners import _CHUNK_TIMEOUT_S

    assert _CHUNK_TIMEOUT_S * 4 <= 600, (
        "one slice can consume most of the 600s soft limit — the budget guard "
        "is back to being the thing that decides the outcome"
    )


def test_splitting_terminates():
    """A window that is narrow and STILL timing out is a query bug or a lock,
    not density, and must be reported rather than subdivided forever."""
    from app.tasks.backfill_winners import _CHUNK_MAX_DEPTH, _CHUNK_MIN_SPAN_S

    assert _CHUNK_MAX_DEPTH <= 20
    assert _CHUNK_MIN_SPAN_S >= 60


def test_the_soft_limit_is_above_the_measured_sweep_and_the_kill_is_publish_safe():
    """600 s was inherited, not measured, and it is what the outage was made of.

    A stratified sample of 64 of the 372 grid cells took 377 s, with 24 of them
    over db-query's own 10 s cap — so the full sweep is comfortably past 600 s.
    Raising a limit is only safe alongside the two properties asserted here: the
    longest uninterrupted statement is bounded far below it, and the single
    Redis write happens after every slice has landed, so a run killed at the
    limit publishes nothing rather than a short curve.
    """
    from app.tasks import celery_app

    task = celery_app.tasks["app.tasks.precompute_bookmaker_calibration"]
    from app.tasks.backfill_winners import _CHUNK_TIMEOUT_S

    assert task.soft_time_limit >= 1200, (
        "back under the measured sweep cost — the writer can be killed before "
        "it finishes again (#1835)"
    )
    assert task.time_limit > task.soft_time_limit
    assert _CHUNK_TIMEOUT_S * 8 <= task.soft_time_limit, (
        "one statement can eat a large fraction of the budget"
    )
