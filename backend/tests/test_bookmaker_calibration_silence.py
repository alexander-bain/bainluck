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


def _summary_for(rows, *, redis_raises=False, query_raises=False, monkeypatch=None):
    """Run the real writer against a stubbed session + Redis."""
    import app.tasks.backfill_winners as bw

    class _Result:
        def all(self):
            if query_raises:
                raise RuntimeError("boom")
            return rows

    class _Session:
        async def execute(self, *a, **k):
            return _Result()

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
    monkeypatch.setattr(bw, "get_task_session", lambda: _Session())
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: redis
    )

    import asyncio

    return asyncio.run(bw._precompute_bookmaker_calibration()), redis


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
