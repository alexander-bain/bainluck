"""#10090 (11/01 17:41Z): a CLOB window priced ~3,500 legs and the pass spent the
rest of its budget committing ~500 markets one after another. Markets are
independent (one commit each), so `_write_jobs` runs them on `WRITERS` sessions."""

import asyncio
from contextlib import asynccontextmanager

import pytest

from app.tasks import base
from app.tasks import venue_poll_30s as v


class _S:
    def __init__(self, name):
        self.name, self.rollbacks = name, 0

    async def rollback(self):
        self.rollbacks += 1


def _factory(opened, fail=False):
    @asynccontextmanager
    async def get_task_session(**_kw):
        if fail:
            raise ConnectionError("pool exhausted")
        s = _S(f"extra{len(opened)}")
        opened.append(s)
        yield s
    return get_task_session


async def test_every_job_is_written_once_across_the_writer_sessions(monkeypatch):
    opened = []
    monkeypatch.setattr(base, "get_task_session", _factory(opened))
    monkeypatch.setattr(v, "WRITERS", 3)
    done, used = [], set()

    async def write(session, job):
        await asyncio.sleep(0.001)
        done.append(job)
        used.add(session.name)

    stats = {}
    await v._write_jobs(_S("caller"), list(range(10)), write, stats)
    assert sorted(done) == list(range(10))
    assert len(opened) == 2 and stats["writers"] == 3
    assert used == {"caller", "extra0", "extra1"}


@pytest.mark.parametrize("writers, jobs", [(1, 5), (4, 1)])
async def test_one_writer_or_one_job_stays_on_the_callers_session(monkeypatch, writers, jobs):
    opened = []
    monkeypatch.setattr(base, "get_task_session", _factory(opened))
    monkeypatch.setattr(v, "WRITERS", writers)
    seen = []

    async def write(session, job):
        seen.append((session.name, job))

    await v._write_jobs(_S("caller"), list(range(jobs)), write, {})
    assert opened == [] and [n for n, _j in seen] == ["caller"] * jobs


async def test_a_writer_that_cannot_open_leaves_its_share_to_the_others(monkeypatch):
    monkeypatch.setattr(base, "get_task_session", _factory([], fail=True))
    monkeypatch.setattr(v, "WRITERS", 4)
    done = []

    async def write(session, job):
        done.append(job)

    stats = {}
    await v._write_jobs(_S("caller"), list(range(6)), write, stats)
    assert sorted(done) == list(range(6)) and stats["writer_open_errors"] == 1
