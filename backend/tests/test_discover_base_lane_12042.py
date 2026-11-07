"""#12042 L-1 (worker audit 2026-11-06 §7.1 step 1; Alex 52-A): the Discover base
rebuild runs on its own lane, which `worker-background` serves first.

Pinned here, each one a way the lane silently stops being first:

* the queue is declared, and the task route and the beat entry both name it
  (beat options override task_routes at dispatch, so both must agree);
* `worker-background` consumes `discover_base` BEFORE `background`, and no
  other worker consumes it;
* the broker reads a worker's queues in that order (`priority`), not rotating
  (kombu's default `round_robin` would put the lane behind `background` right
  after it delivered).
"""

from __future__ import annotations

import pathlib
import re

from app.tasks import DISCOVER_BASE_QUEUE, celery_app

PROCFILE = pathlib.Path(__file__).resolve().parents[1] / "Procfile"


def _queues(proc: str) -> list[str]:
    line = next(ln for ln in PROCFILE.read_text().splitlines() if ln.startswith(f"{proc}:"))
    found = re.search(r"--queues=(\S+)", line)
    return found.group(1).split(",") if found else []


def test_the_lane_is_declared_and_both_dispatch_paths_name_it():
    conf = celery_app.conf
    assert DISCOVER_BASE_QUEUE == "discover_base"
    assert DISCOVER_BASE_QUEUE in {q.name for q in conf.task_queues}
    assert conf.task_routes["app.tasks.precompute_discover_candidate_base"] == {
        "queue": DISCOVER_BASE_QUEUE
    }
    beat = conf.beat_schedule["precompute-discover-candidate-base"]
    assert beat["task"] == "app.tasks.precompute_discover_candidate_base"
    assert beat["options"]["queue"] == DISCOVER_BASE_QUEUE


def test_worker_background_serves_the_lane_first_and_alone():
    assert _queues("worker-background") == [DISCOVER_BASE_QUEUE, "background"]
    for proc in ("worker-realtime", "worker-heavy"):
        assert DISCOVER_BASE_QUEUE not in _queues(proc), proc


def test_the_broker_reads_queues_in_order_not_round_robin():
    opts = celery_app.conf.broker_transport_options
    assert opts["queue_order_strategy"] == "priority"
    # The keepalive settings beside it are untouched.
    assert opts["health_check_interval"] == 25 and opts["retry_on_timeout"] is True


def test_nothing_else_rides_the_lane():
    conf = celery_app.conf
    on_lane = sorted(
        name
        for name, entry in conf.beat_schedule.items()
        if (entry.get("options") or {}).get("queue") == DISCOVER_BASE_QUEUE
    )
    assert on_lane == ["precompute-discover-candidate-base"]
    routed = sorted(t for t, r in conf.task_routes.items() if r.get("queue") == DISCOVER_BASE_QUEUE)
    assert routed == ["app.tasks.precompute_discover_candidate_base"]
