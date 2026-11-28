"""Wiring and behavior guards for #13102 priority lane + loud 1:25 AM PT watchdog.

Pins the two mechanisms that stop the 1:00 AM PT Nightly Fun Scout from
silently slipping hours behind overnight ``background`` work:

1. ``discover_fun_scout`` rides its dedicated ``scout_nightly`` priority queue
   consumed after ``discover_base`` and ahead of ``background`` on
   ``worker-background``.
2. ``discover_fun_scout_watchdog`` runs daily at ``09:25 UTC`` (``1:25 AM PST``)
   on ``heavy`` (immune to ``worker-background`` contention) and posts loudly
   to ``#13580`` by ``1:30 AM PT`` whenever ``#13102`` has no report for today,
   without touching ``DISCOVER_FUN_SCOUT_ENABLED`` on ``bainluck-heavy``.
"""

from __future__ import annotations

import importlib
import logging
import pathlib
import re
from datetime import datetime, timezone

import pytest

from app.tasks import (
    DISCOVER_BASE_QUEUE,
    HEAVY_TASKS,
    SCOUT_NIGHTLY_QUEUE,
    celery_app,
)

scout_task = importlib.import_module("app.tasks.discover_fun_scout")

PROCFILE = pathlib.Path(__file__).resolve().parents[1] / "Procfile"
FROZEN_WATCHDOG_NOW = datetime(2026, 11, 29, 9, 25, 0, tzinfo=timezone.utc)


def _proc_queues(proc: str) -> list[str]:
    line = next(ln for ln in PROCFILE.read_text().splitlines() if ln.startswith(f"{proc}:"))
    match = re.search(r"--queues=(\S+)", line)
    return match.group(1).split(",") if match else []


class _MemoryRedis:
    def __init__(self, initial: dict[str, str] | None = None, lengths: dict[str, int] | None = None):
        self.store: dict[str, str] = dict(initial or {})
        self.lengths: dict[str, int] = dict(lengths or {})

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def delete(self, key: str):
        self.store.pop(key, None)
        return 1

    def llen(self, key: str) -> int:
        return self.lengths.get(key, 0)


class _Resp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_scout_nightly_priority_lane_and_heavy_watchdog_wiring():
    conf = celery_app.conf
    assert SCOUT_NIGHTLY_QUEUE == "scout_nightly"
    assert SCOUT_NIGHTLY_QUEUE in {q.name for q in conf.task_queues}

    assert _proc_queues("worker-background") == [
        DISCOVER_BASE_QUEUE,
        SCOUT_NIGHTLY_QUEUE,
        "background",
    ]
    for other_proc in ("worker-realtime", "worker-heavy"):
        assert SCOUT_NIGHTLY_QUEUE not in _proc_queues(other_proc), other_proc

    # Only discover_fun_scout rides scout_nightly.
    assert conf.task_routes["app.tasks.discover_fun_scout"] == {
        "queue": SCOUT_NIGHTLY_QUEUE
    }
    routed_scout = sorted(
        t for t, r in conf.task_routes.items() if r.get("queue") == SCOUT_NIGHTLY_QUEUE
    )
    assert routed_scout == ["app.tasks.discover_fun_scout"]

    nightly = conf.beat_schedule["discover-fun-scout-nightly"]
    assert nightly["task"] == "app.tasks.discover_fun_scout"
    assert nightly["options"]["queue"] == SCOUT_NIGHTLY_QUEUE
    assert nightly["schedule"].hour == {9}
    assert nightly["schedule"].minute == {0}

    # Watchdog runs on heavy at 09:25 UTC (1:25 AM PST) with unique heavy slot.
    assert "app.tasks.discover_fun_scout_watchdog" in celery_app.tasks
    assert "app.tasks.discover_fun_scout_watchdog" in HEAVY_TASKS
    assert conf.task_routes["app.tasks.discover_fun_scout_watchdog"] == {"queue": "heavy"}

    wd = conf.beat_schedule["discover-fun-scout-watchdog-daily"]
    assert wd["task"] == "app.tasks.discover_fun_scout_watchdog"
    assert wd["options"]["queue"] == "heavy"
    assert wd["schedule"].hour == {9}
    assert wd["schedule"].minute == {25}


def test_watchdog_celery_task_wrapper_calls_tracked_run(monkeypatch):
    import app.tasks as tasks_pkg

    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(scout_task, "_run_discover_fun_scout_watchdog", lambda: "sentinel-coro")
    monkeypatch.setattr(
        tasks_pkg,
        "_tracked_run",
        lambda name, coro: calls.append((name, coro)) or {"status": "ok"},
    )
    out = tasks_pkg.discover_fun_scout_watchdog.run()
    assert out == {"status": "ok"}
    assert calls == [("discover_fun_scout_watchdog", "sentinel-coro")]


@pytest.mark.asyncio
async def test_watchdog_is_quiet_when_report_is_present_on_13102(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token-value")
    posts: list[dict] = []

    def fake_get(url, *, headers=None, params=None, timeout=None):
        assert "/issues/13102/comments" in url
        assert params["since"] == "2026-11-29T00:00:00Z"
        return _Resp(
            200,
            [
                {
                    "body": "## Nightly Fun Scout Report — `2026-11-29`\n\nAll good.",
                    "html_url": "https://github.com/alexander-bain/bainluck/issues/13102#issuecomment-777",
                }
            ],
        )

    monkeypatch.setattr(scout_task.httpx, "get", fake_get)
    monkeypatch.setattr(scout_task.httpx, "post", lambda *a, **kw: posts.append(kw) or _Resp(201, {}))

    out = await scout_task._run_discover_fun_scout_watchdog(now=FROZEN_WATCHDOG_NOW)
    assert out == {
        "status": "ok",
        "run_date": "2026-11-29",
        "report_url": "https://github.com/alexander-bain/bainluck/issues/13102#issuecomment-777",
    }
    assert posts == []


@pytest.mark.asyncio
async def test_watchdog_respects_redis_disabled_marker_even_when_heavy_env_disabled(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token-value")
    monkeypatch.delenv("DISCOVER_FUN_SCOUT_ENABLED", raising=False)
    redis_client = _MemoryRedis()
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: redis_client)

    disabled_out = await scout_task._run_discover_fun_scout(
        force=False, now=datetime(2026, 11, 29, 9, 0, 2, tzinfo=timezone.utc)
    )
    assert disabled_out == {"status": "disabled"}
    assert redis_client.get("bainluck:fun_scout:disabled:2026-11-29") == "1"

    posts: list[dict] = []
    monkeypatch.setattr(scout_task.httpx, "get", lambda *a, **kw: _Resp(200, []))
    monkeypatch.setattr(scout_task.httpx, "post", lambda *a, **kw: posts.append(kw) or _Resp(201, {}))

    wd_out = await scout_task._run_discover_fun_scout_watchdog(now=FROZEN_WATCHDOG_NOW)
    assert wd_out == {"status": "skipped_disabled", "run_date": "2026-11-29"}
    assert posts == []


@pytest.mark.asyncio
async def test_watchdog_alerts_13580_loudly_when_missing_and_dedupes(monkeypatch, caplog):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token-value")
    # Even when heavy env does NOT enable scout, missing disabled marker MUST alert.
    monkeypatch.delenv("DISCOVER_FUN_SCOUT_ENABLED", raising=False)
    redis_client = _MemoryRedis(
        initial={"bainluck:fun_scout:latest": '{"run_date": "2026-11-28"}'},
        lengths={"scout_nightly": 1, "background": 14},
    )
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: redis_client)

    issue_13580_comments: list[dict] = []

    def fake_get(url, *, headers=None, params=None, timeout=None):
        if "/issues/13102/comments" in url:
            return _Resp(200, [])
        if "/issues/13580/comments" in url:
            return _Resp(200, list(issue_13580_comments))
        raise AssertionError(f"unexpected GET {url}")

    def fake_post(url, *, headers=None, json=None, timeout=None):
        assert "/issues/13580/comments" in url
        body = json["body"]
        assert "test-token-value" not in body
        comment_url = f"https://github.com/alexander-bain/bainluck/issues/13580#issuecomment-{len(issue_13580_comments) + 1}"
        issue_13580_comments.append({"body": body, "html_url": comment_url})
        return _Resp(201, {"html_url": comment_url})

    monkeypatch.setattr(scout_task.httpx, "get", fake_get)
    monkeypatch.setattr(scout_task.httpx, "post", fake_post)

    with caplog.at_level(logging.ERROR):
        first = await scout_task._run_discover_fun_scout_watchdog(now=FROZEN_WATCHDOG_NOW)

    assert first["status"] == "alerted"
    assert first["run_date"] == "2026-11-29"
    assert first["runtime_state"]["scout_nightly_queue_depth"] == 1
    assert first["runtime_state"]["background_queue_depth"] == 14
    assert first["runtime_state"]["latest_run_date"] == "2026-11-28"
    assert len(issue_13580_comments) == 1
    posted_body = issue_13580_comments[0]["body"]
    assert "#13102" in posted_body
    assert "2026-11-29" in posted_body
    assert "<!-- fun-scout-missing:2026-11-29 -->" in posted_body
    assert any("missing report for 2026-11-29" in rec.message for rec in caplog.records)

    # Clear Redis claim key to also prove GitHub marker dedupes across Redis restarts.
    redis_client.delete("bainluck:fun_scout:missing_alert_claimed:2026-11-29")
    second = await scout_task._run_discover_fun_scout_watchdog(now=FROZEN_WATCHDOG_NOW)
    assert second == {
        "status": "already_alerted",
        "run_date": "2026-11-29",
        "alert_url": "https://github.com/alexander-bain/bainluck/issues/13580#issuecomment-1",
    }
    assert len(issue_13580_comments) == 1


@pytest.mark.asyncio
async def test_watchdog_never_blind_posts_when_github_read_fails(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token-value")
    posts: list[dict] = []
    monkeypatch.setattr(scout_task.httpx, "post", lambda *a, **kw: posts.append(kw) or _Resp(201, {}))

    monkeypatch.setattr(scout_task.httpx, "get", lambda *a, **kw: _Resp(502, {"message": "bad gateway"}))
    out_13102_err = await scout_task._run_discover_fun_scout_watchdog(now=FROZEN_WATCHDOG_NOW)
    assert out_13102_err == {
        "status": "github_read_failed",
        "run_date": "2026-11-29",
        "error": "GitHub API HTTP 502",
    }

    def fake_get_13580_err(url, *, headers=None, params=None, timeout=None):
        if "/issues/13102/comments" in url:
            return _Resp(200, [])
        return _Resp(503, {"message": "unavailable"})

    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: _MemoryRedis())
    monkeypatch.setattr(scout_task.httpx, "get", fake_get_13580_err)
    out_13580_err = await scout_task._run_discover_fun_scout_watchdog(now=FROZEN_WATCHDOG_NOW)
    assert out_13580_err == {
        "status": "alert_dedupe_read_failed",
        "run_date": "2026-11-29",
        "error": "GitHub API HTTP 503",
    }
    assert posts == []


@pytest.mark.asyncio
async def test_watchdog_releases_claim_if_alert_post_fails(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token-value")
    redis_client = _MemoryRedis()
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: redis_client)
    monkeypatch.setattr(scout_task.httpx, "get", lambda *a, **kw: _Resp(200, []))
    monkeypatch.setattr(scout_task.httpx, "post", lambda *a, **kw: _Resp(500, {}))

    out = await scout_task._run_discover_fun_scout_watchdog(now=FROZEN_WATCHDOG_NOW)
    assert out == {
        "status": "alert_post_failed",
        "run_date": "2026-11-29",
        "error": "GitHub API HTTP 500",
    }
    assert redis_client.get("bainluck:fun_scout:missing_alert_claimed:2026-11-29") is None
