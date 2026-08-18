"""Guard tests for the golf-major concept warmer (#1107, LAT-P021).

The warmer is the second half of the fix. The first half (serve-stale-while-
revalidate, `test_event_concept_swr.py`) makes a miss cheap; this keeps the
mirror's CONTENT fresh and makes sure the first build of the day is not paid by
a reader.

Two properties matter more than the warming itself and are pinned here:

  * it is **not load-bearing** — turning it off makes the page slow, never
    broken (asserted in `test_event_concept_swr.py` too, from the route side);
  * it **cannot report success while a major is cold**. A warmer whose whole
    purpose is that all four are warm must read PARTIAL at 3/4, which is what
    `app/utils/task_verdict.py` exists to enforce (gotcha #53: "it returned" is
    not "it worked").
"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

from app.config.event_concept_warm_keys import GOLF_MAJOR_CONCEPT_KEYS, WARM_CONCEPT_KEYS
from app.tasks import event_concept_warmer as warmer
from app.utils import event_concept_cache as cache_mod
from app.utils.task_verdict import NOT_GREEN, classify_summary


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, bytes] = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        return True

    def setex(self, k, ttl, v):
        self.store[k] = v.encode() if isinstance(v, str) else v

    def delete(self, k):
        return int(self.store.pop(k, None) is not None)

    def eval(self, script, numkeys, *args):
        """delete KEYS[1] only if it equals ARGV[1] — the compare-and-delete the
        refresh lock releases through (#1678 finding 1)."""
        key, token = args[0], args[1]
        expected = token.encode() if isinstance(token, str) else token
        if self.store.get(key) == expected:
            self.store.pop(key, None)
            return 1
        return 0


@asynccontextmanager
async def _fake_session():
    yield object()


def _patched(build, rc=None):
    """Patch the three things `_build_one` reaches out to."""
    rc = rc if rc is not None else _FakeRedis()
    return (
        patch("app.tasks.base.get_task_session", _fake_session),
        patch("app.utils.event_concept_cache.build_and_cache", build),
        patch("app.utils.event_concept_cache.get_client", return_value=rc),
    )


async def _run(build, keys=None, rc=None):
    """Drive the warmer over the MAJORS tier only.

    `keys` is passed EXPLICITLY (defaulting to the majors) and that is
    deliberate after #1948. The scheduled path — `_warm_event_concepts(None)` —
    now also resolves the leader tier from the database. Left implicit, every
    test in this file would still pass, because the stubbed session makes the
    leader enumeration fail and return an empty tier: the fixtures would be
    quietly asserting the majors-only contract while the production code did
    something else, which is the third time in this program a fixture has
    agreed with a bug. The scheduled two-tier path has its own suite,
    `test_concept_leader_warm_population.py`.
    """
    a, b, c = _patched(build, rc)
    with a, b, c:
        return await warmer._warm_event_concepts(
            WARM_CONCEPT_KEYS if keys is None else keys
        )


# ---------------------------------------------------------------------------
# The verdict contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_four_warmed_reads_complete():
    async def build(key, db, rc, adapter=None):
        return {"event": {"name": key}}

    summary = await _run(build)

    assert summary["terminal"] == "complete"
    assert summary["completed"] == summary["total"] == len(WARM_CONCEPT_KEYS)
    assert summary["built"] == len(WARM_CONCEPT_KEYS)
    assert classify_summary(summary).verdict not in NOT_GREEN


@pytest.mark.asyncio
async def test_one_cold_major_cannot_read_green():
    """3/4 is not success for this task."""

    async def build(key, db, rc, adapter=None):
        if key == "event:golf:the-open-championship":
            raise RuntimeError("build exploded")
        return {"event": {"name": key}}

    summary = await _run(build)

    assert summary["terminal"] == "partial"
    assert summary["completed"] == 3
    assert summary["total"] == 4
    assert [e["key"] for e in summary["errors"]] == ["event:golf:the-open-championship"]
    assert classify_summary(summary).verdict in NOT_GREEN, (
        "a run that left a major cold reported GREEN — that is the false-GREEN "
        "class #1515 was filed for"
    )


@pytest.mark.asyncio
async def test_an_absent_major_is_accounted_for_not_counted_as_damage():
    """"absent" and "broken" are different facts (gotcha #53).

    An unscheduled major that resolves to nothing is the warmer doing everything
    it can, not a failure. Folding it into the error count would make the task
    permanently amber and train operators to ignore it.
    """

    async def build(key, db, rc, adapter=None):
        if key == "event:golf:u-s-open":
            return None
        return {"event": {"name": key}}

    summary = await _run(build)

    assert summary["terminal"] == "complete"
    assert summary["errors"] == []
    assert summary["absent"] == ["event:golf:u-s-open"]
    assert summary["built"] == 3
    assert summary["completed"] == 4


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_pathological_build_cannot_take_the_other_majors_down():
    """The bound is on ONE build, not on the loop boundary.

    The longest measured single uninterrupted op is The Open at ~35s. Bounding
    only the loop lets one hung build consume the whole budget and reach the
    300s hard SIGKILL, which is recorded as no_data rather than as a failure.
    """
    started = []

    async def build(key, db, rc, adapter=None):
        started.append(key)
        if key == "event:golf:the-open-championship":
            await asyncio.sleep(10)
        return {"event": {"name": key}}

    with patch.object(warmer, "PER_KEY_TIMEOUT_SECONDS", 0.05):
        summary = await _run(build)

    assert started == list(WARM_CONCEPT_KEYS), "the hung build stopped the other three"
    assert summary["errors"] == [
        {"key": "event:golf:the-open-championship", "reason": "timeout"}
    ]
    assert summary["built"] == 3


@pytest.mark.asyncio
async def test_the_per_key_bound_leaves_headroom_under_the_task_budget():
    """Four keys at the per-key bound must still fit inside the soft limit.

    Pinned as arithmetic so raising PER_KEY_TIMEOUT_SECONDS without raising the
    task's soft_time_limit fails here rather than in production as a SIGKILL.
    """
    from app.tasks import celery_app

    task = celery_app.tasks["app.tasks.warm_event_concepts"]
    soft = task.soft_time_limit
    hard = task.time_limit

    assert soft is not None and hard is not None
    assert soft < hard, "a soft limit at or above the hard limit never fires"
    assert hard <= 300, (
        f"time_limit {hard}s is at or above the global 300s hard SIGKILL, which "
        "would be recorded as no_data rather than as a failure"
    )
    # The MAJORS tier's own bound. Since #1948 the binding arithmetic is the sum
    # of the two TIER budgets (asserted in
    # `test_concept_leader_warm_population.py`), because a per-key timeout no
    # longer bounds a tier on its own — the tier budget does. Both still hold.
    assert warmer.PER_KEY_TIMEOUT_SECONDS * len(WARM_CONCEPT_KEYS) <= soft, (
        f"{len(WARM_CONCEPT_KEYS)} keys x {warmer.PER_KEY_TIMEOUT_SECONDS}s exceeds "
        f"the {soft}s soft limit — the run can be killed mid-warm"
    )


# ---------------------------------------------------------------------------
# The single-flight lock the route depends on
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_refresh_lock_is_released_however_the_build_ends():
    """The route holds this lock while it waits. If the worker does not release
    it, the key cannot schedule another revalidation until the lock's own TTL
    expires — so a single failed rebuild would freeze the mirror."""
    key = "event:golf:the-masters"
    keys = cache_mod.cache_keys(key)

    for build in (
        _ok_build,
        _raising_build,
        _absent_build,
    ):
        rc = _FakeRedis()
        # The route acquires and hands the token over with the dispatch (#1678
        # finding 1). Seeding a bare "1" here, as this test used to, encoded the
        # old unconditional release: it passed precisely BECAUSE the worker
        # deleted a lock it could not prove it owned.
        token = cache_mod.acquire_refresh_lock(rc, keys)
        assert token, "precondition: the route should have taken the lock"

        a, b, c = _patched(build, rc)
        with a, b, c:
            await warmer._refresh_event_concept(key, token)
        assert keys.refresh_lock not in rc.store, (
            f"{build.__name__} left the single-flight lock held"
        )


async def _ok_build(key, db, rc, adapter=None):
    return {"event": {"name": key}}


async def _raising_build(key, db, rc, adapter=None):
    raise RuntimeError("boom")


async def _absent_build(key, db, rc, adapter=None):
    return None


@pytest.mark.asyncio
async def test_a_refresh_that_failed_reports_failed():
    key = "event:golf:the-masters"
    a, b, c = _patched(_raising_build)
    with a, b, c:
        summary = await warmer._refresh_event_concept(key)

    assert summary["terminal"] == "failed"
    assert classify_summary(summary).verdict in NOT_GREEN


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_the_named_warm_list_is_the_four_majors_and_nothing_else():
    """The list NAMED in config is still exactly the four majors.

    RETITLED, and the distinction is the whole of #1948. This asserts the
    hand-written tuple, which is the LATENCY tier (#1107) — not "everything the
    warmer warms". The warmer also warms every unsettled concept, enumerated
    from the feed's own population function; that set is dynamic and must never
    be pasted in here, because a hand-copied list is what drifted from the feed
    and deleted the concept tier from Discover.

    Still not "warm every concept": the tier also spans tennis and the awards
    adapters, and an unbounded sweep finds the 300s hard SIGKILL.
    """
    assert len(GOLF_MAJOR_CONCEPT_KEYS) == 4
    assert WARM_CONCEPT_KEYS == GOLF_MAJOR_CONCEPT_KEYS
    assert all(k.startswith("event:golf:") for k in WARM_CONCEPT_KEYS)
    assert len(set(WARM_CONCEPT_KEYS)) == 4


def test_the_slowest_major_is_warmed_first():
    """The Open measured slowest (~35s, the one that 503'd). Building it first
    gives the key most likely to be cut short the whole run's headroom rather
    than what three other builds left behind."""
    assert WARM_CONCEPT_KEYS[0] == "event:golf:the-open-championship"


def test_the_cadence_is_not_sub_ttl_and_that_is_deliberate():
    """LAT-P021 was staged asking for a schedule shorter than the TTL. Item 0
    measured the TTL at 60s and the four builds at ~82s, so a sub-60s cadence
    cannot finish. It does not need to: the route serves the mirror on a miss.

    This asserts the cadence is honest about that rather than quietly reverting
    to a value that cannot work.
    """
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["warm-event-concepts"]
    assert entry["task"] == "app.tasks.warm_event_concepts"
    assert entry["options"]["queue"] == "background"
    # crontab(minute="*/5") — every 5 minutes, comfortably above the ~82s of work
    # and comfortably above the 60s TTL it deliberately does not chase.
    assert "*/5" in str(entry["schedule"])
    assert cache_mod.ENVELOPE_TTL == 60
