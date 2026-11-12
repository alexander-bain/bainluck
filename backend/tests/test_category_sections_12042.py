"""#12042: the hourly category precompute runs one task per section.

worker-background was killed (R15) with ``precompute_category_pages`` in flight
at 2:28, 5:26 and 7:27 AM PT on Nov 12. Its seven sections ran in one prefork
child, and the worker checks a child against ``--max-memory-per-child`` only when
a task ends, so the child ended near the sum of seven peaks while the other child
ran the every-2-minute Discover base build. Now:

* the hourly task SENDS one ``precompute_category_section`` task per section, in
  the declared order (grids last), so a child can be recycled between sections;
* a section that finds the base build running waits and asks again, up to a cap,
  then runs anyway; the base build never waits;
* each section folds its result into the one report the admin rail reads,
  without overwriting a section that finished at the same moment.
"""

import json

import pytest
from celery.exceptions import Retry

import importlib

import app.tasks as tasks_mod

TASKS = tasks_mod.celery_app.tasks

# `from app.tasks import precompute_category_pages` is the Celery TASK of that
# name, not the module, so import the module by path.
pcp = importlib.import_module("app.tasks.precompute_category_pages")


class _Pipe:
    def __init__(self, store, conflicts):
        self.store, self.conflicts, self.queued = store, conflicts, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def watch(self, key):
        self.key = key

    def get(self, key):
        return self.store.get(key)

    def multi(self):
        pass

    def setex(self, key, ttl, value):
        self.queued.append((key, value))

    def execute(self):
        from redis.exceptions import WatchError

        if self.conflicts:
            # another section wrote first: apply its write, then fail ours
            key, value = self.conflicts.pop(0)
            self.store[key] = value
            raise WatchError()
        for key, value in self.queued:
            self.store[key] = value


class _Redis:
    def __init__(self):
        self.store, self.conflicts = {}, []

    def pipeline(self, transaction=True):
        return _Pipe(self.store, self.conflicts)

    def set(self, key, value, ex=None):
        self.store[key] = value

    def setex(self, key, ttl, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)

    def exists(self, key):
        return int(key in self.store)


@pytest.fixture
def rc(monkeypatch):
    r = _Redis()
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: r)
    return r


def _report(r):
    return json.loads(r.store[pcp.PRECOMPUTE_STATUS_KEY])


def test_the_dispatcher_sends_every_section_in_order(monkeypatch):
    sent = []
    monkeypatch.setattr(
        TASKS["app.tasks.precompute_category_section"],
        "apply_async",
        lambda args=None, queue=None, **k: sent.append((args[0], queue)),
    )
    out = TASKS["app.tasks.precompute_category_pages"].run()
    names = pcp.category_section_names()
    assert [s for s, _ in sent] == names
    assert names[-1] == "grids" and names.index("golf_schedule") < names.index("grids")
    assert {q for _, q in sent} == {"background"}
    assert out == {"status": "dispatched", "sections": names}


def test_the_beat_still_fires_the_dispatcher_once_an_hour():
    beat = tasks_mod.celery_app.conf.beat_schedule
    entries = [e for e in beat.values() if e["task"] == "app.tasks.precompute_category_pages"]
    assert len(entries) == 1
    assert not any(e["task"] == "app.tasks.precompute_category_section" for e in beat.values())


@pytest.mark.asyncio
async def test_one_section_runs_alone_and_merges_into_the_report(monkeypatch, rc):
    ran = []

    async def _fake(name):
        async def _run(*a):
            ran.append(name)
            return {"cached": name}
        return _run

    fakes = {n: await _fake(n) for n in pcp.category_section_names()}
    monkeypatch.setattr(pcp, "_category_sections", lambda: list(fakes.items()))
    # an earlier section's result is already in the report
    rc.store[pcp.PRECOMPUTE_STATUS_KEY] = json.dumps(
        {"sections": {"politics": {"outcome": "ok", "duration_s": 3.0}}, "started_at": "x"}
    )

    await pcp._precompute_all_category_pages(only="weather")

    assert ran == ["weather"]
    rep = _report(rc)
    assert rep["sections"]["weather"]["outcome"] == "ok"
    assert rep["sections"]["politics"] == {"outcome": "ok", "duration_s": 3.0}
    assert rep["sections"]["grids"] == {"outcome": "not_attempted"}
    assert rep["mode"] == "per_section" and rep["generated_at"]
    assert list(rep["sections"]) == pcp.category_section_names()


@pytest.mark.asyncio
async def test_two_sections_finishing_together_both_land(monkeypatch, rc):
    async def _ok(*a):
        return {}

    names = pcp.category_section_names()
    monkeypatch.setattr(pcp, "_category_sections", lambda: [(n, _ok) for n in names])
    # economics commits between our read and our write
    rc.conflicts.append(
        (pcp.PRECOMPUTE_STATUS_KEY, json.dumps({"sections": {"economics": {"outcome": "ok"}}}))
    )
    await pcp._precompute_all_category_pages(only="golf")
    rep = _report(rc)
    assert rep["sections"]["golf"]["outcome"] == "ok"
    assert rep["sections"]["economics"] == {"outcome": "ok"}


@pytest.mark.asyncio
async def test_an_unknown_section_is_refused():
    with pytest.raises(ValueError):
        await pcp._precompute_all_category_pages(only="nope")


def _run_section(monkeypatch, retries, base_running):
    ran = []

    def _fake_tracked(name, coro):
        coro.close()
        ran.append(name)
        return {"ok": True}

    monkeypatch.setattr(tasks_mod, "_tracked_run", _fake_tracked)
    monkeypatch.setattr(pcp, "discover_base_running", lambda: base_running)
    task = TASKS["app.tasks.precompute_category_section"]
    task.push_request(retries=retries)
    try:
        return task.run("politics"), ran
    finally:
        task.pop_request()


def test_a_section_waits_while_the_base_build_runs(monkeypatch):
    with pytest.raises(Retry):
        _run_section(monkeypatch, retries=0, base_running=True)


def test_a_section_runs_when_the_base_is_idle(monkeypatch):
    out, ran = _run_section(monkeypatch, retries=0, base_running=False)
    assert ran == ["category_section_politics"]


def test_a_section_runs_anyway_after_its_last_wait(monkeypatch):
    out, ran = _run_section(
        monkeypatch, retries=tasks_mod.CATEGORY_SECTION_BASE_WAIT_TRIES, base_running=True
    )
    assert ran == ["category_section_politics"]


def test_the_base_flag_is_held_during_a_build_and_cleared_after(rc):
    with pcp.mark_discover_base_running():
        assert pcp.discover_base_running() is True
    assert pcp.discover_base_running() is False


def test_the_base_flag_never_clears_a_newer_builds_flag(rc):
    with pcp.mark_discover_base_running():
        rc.store[pcp.DISCOVER_BASE_RUNNING_KEY] = "a-newer-build"
    assert rc.store[pcp.DISCOVER_BASE_RUNNING_KEY] == "a-newer-build"


def test_redis_down_never_stops_a_build_or_a_section(monkeypatch):
    def _boom(*a, **k):
        raise ConnectionError("redis down")

    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", _boom)
    with pcp.mark_discover_base_running():
        pass
    assert pcp.discover_base_running() is False


def test_the_base_build_holds_the_flag_while_it_runs(monkeypatch, rc):
    seen = []

    def _fake_tracked(name, coro):
        coro.close()
        seen.append(pcp.discover_base_running())
        return {}

    monkeypatch.setattr(tasks_mod, "_tracked_run", _fake_tracked)
    TASKS["app.tasks.precompute_discover_candidate_base"].run()
    assert seen == [True]
    assert pcp.discover_base_running() is False


@pytest.mark.asyncio
async def test_a_section_that_never_lands_reads_not_attempted_next_hour(monkeypatch, rc):
    """Fable's probe (10:38 AM Nov 12): hour 1 all seven land; hour 2 only
    politics lands before the worker dies. Without a fresh report each hour the
    other six kept hour 1's ok under hour 2's generated_at."""
    async def _ok(*a):
        return {}

    names = pcp.category_section_names()
    monkeypatch.setattr(pcp, "_category_sections", lambda: [(n, _ok) for n in names])
    monkeypatch.setattr(TASKS["app.tasks.precompute_category_section"], "apply_async", lambda *a, **k: None)
    dispatch = TASKS["app.tasks.precompute_category_pages"]

    dispatch.run()  # hour 1
    for name in names:
        await pcp._precompute_all_category_pages(only=name)
    hour1 = _report(rc)
    assert all(v["outcome"] == "ok" for v in hour1["sections"].values())

    dispatch.run()  # hour 2
    opened = _report(rc)
    assert all(v == {"outcome": "not_attempted"} for v in opened["sections"].values())
    await pcp._precompute_all_category_pages(only="politics")

    hour2 = _report(rc)
    assert hour2["sections"]["politics"]["outcome"] == "ok"
    assert all(hour2["sections"][n] == {"outcome": "not_attempted"} for n in names if n != "politics")
    assert hour2["started_at"] == opened["started_at"]
    assert hour2["started_at"] >= hour1["started_at"]
