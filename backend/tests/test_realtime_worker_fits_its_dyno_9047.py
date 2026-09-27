"""#9047: worker-realtime's children must be able to fit inside its dyno.

worker-realtime runs live scores, live prices and the ESPN live sync. It is a
Standard-2X (1024 MB quota, `heroku ps:type -a bainluck`) running a prefork pool
of 4 children, and billiard recycles a child only AFTER a task, once the child's
peak RSS passes `--max-memory-per-child` (KiB). At 350000 the four children alone
were allowed 4 x 342 MB = 1367 MB before counting the parent, so the ceiling sat
above the quota by construction. Heroku's metrics API showed the result for the
week of 2026-09-20: mean memory over quota for 5-24 hours a day, swap up to
1072 MB, and peaks of 2041-2072 MB against the 2048 MB R15 kill line. A swapping
worker runs every live task slower.

The busy-hour numbers say the children's copy-on-write sharing with the parent
is mostly gone (1.3-1.6 GB at 4 children under a 342 MB cap), so the worst case
`parent + concurrency x cap` is the realistic one, not a pessimistic bound.
The twin pool is the oracle for the new value: worker-background runs the same
code under `--max-memory-per-child=200000` and averaged 393 MB over the same
week.

What would have to happen for this to go red: someone raises the cap or the
concurrency back past the quota, or buys the fit by quietly dropping live slots.
"""

from __future__ import annotations

from tests.fixtures.sentry_formation import parse_procfile

#: `heroku ps:type -a bainluck` on 2026-09-27: worker-realtime is Standard-2X.
REALTIME_DYNO_QUOTA_MB = 1024
#: The parent process: 103 MB peak RSS after importing app.tasks and its default
#: modules (measured locally, 214 tasks registered), rounded up for the Linux
#: runtime and the Sentry/Celery boot that a bare import does not do.
PARENT_RESERVE_MB = 150
#: Live slots the fix must not give away to make the arithmetic work.
REALTIME_LIVE_SLOTS = 4


def _realtime() -> dict:
    return parse_procfile()["worker-realtime"]


def test_the_children_and_parent_fit_the_quota():
    spec = _realtime()
    assert spec["max_memory_kb"], "worker-realtime lost --max-memory-per-child"
    ceiling_mb = PARENT_RESERVE_MB + spec["concurrency"] * spec["max_memory_kb"] / 1024
    assert ceiling_mb <= REALTIME_DYNO_QUOTA_MB, (
        f"worker-realtime can hold {ceiling_mb:.0f} MB between tasks "
        f"({spec['concurrency']} x {spec['max_memory_kb']} KiB + {PARENT_RESERVE_MB} MB "
        f"parent) on a {REALTIME_DYNO_QUOTA_MB} MB dyno: it will swap (R14) under a "
        f"live slate, as it did every day of the week of 2026-09-20 (#9047)."
    )


def test_the_fit_is_not_bought_by_dropping_live_slots():
    assert _realtime()["concurrency"] >= REALTIME_LIVE_SLOTS, (
        "worker-realtime lost live slots; the memory fit (#9047) was made at "
        f"{REALTIME_LIVE_SLOTS} children and a smaller pool slows every live task."
    )


def test_the_realtime_pool_still_consumes_only_the_realtime_queue():
    assert "--queues=realtime" in _realtime()["command"]
