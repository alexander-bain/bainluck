"""#10090 — optional reads end at their deadline by cancellation.

The normal ACK settlement, the durable normal recovery page read and the
preview capacity reads are optional: past their deadline the caller gets a
TimeoutError and the read is cancelled. Abandoning such a read instead (left
to finish on its own task) was trialled as `LIVE_BLEND_ABANDON_OPTIONAL_DB` /
`abandon_optional_db`, lost, and was removed in the settings freeze
(docs/live-settings.md). These are the plain-path tests kept from the removed
`tests/test_optional_db_abandon_10090.py`: `_optional_db` is exactly
``asyncio.timeout(budget_s)`` around its body, `_optional_db_in_pass` is
exactly ``await body(None)`` under the pass's own deadline, and the optional
share check never reads busy while the share exists.
"""

import asyncio
from contextlib import asynccontextmanager

import pytest

from app.tasks.live_blend_refresh import FRESH_STAMP_WORKERS, LiveBlendRefresher
from tests.test_live_blend_refresh import _Result

pytestmark = pytest.mark.asyncio


def refresher():
    r = LiveBlendRefresher("polymarket")
    opened = []

    class Session:
        async def execute(self, statement, params=None):
            return _Result()

    @asynccontextmanager
    async def factory():
        opened.append(True)
        yield Session()

    r._session_factory = factory
    return r, opened


class Body:
    """A read that finishes when told to, recording how it ended."""

    def __init__(self, value="graph"):
        self.value = value
        self.release = asyncio.Event()
        self.started = asyncio.Event()
        self.ended = None

    async def __call__(self):
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.ended = "cancelled"
            raise
        self.ended = "finished"
        return self.value


@pytest.mark.parametrize("key", [None, 2, 3])
async def test_the_deadline_releases_the_caller_and_cancels_the_read(key):
    r, _ = refresher()
    body = Body()
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_read", .02, body, key)
    assert loop.time() - started < .5
    assert body.ended == "cancelled"
    assert not r._optional_db_busy()


async def test_a_read_that_finishes_in_time_returns_and_its_error_propagates():
    r, _ = refresher()
    body = Body("rows")
    body.release.set()
    assert await r._optional_db("normal_read", .5, body) == "rows"

    async def broken():
        raise ValueError("query failed")

    with pytest.raises(ValueError):
        await r._optional_db("normal_read", .5, broken)


async def test_busy_checks_are_inert():
    """Nothing is ever held past its deadline, so every busy check reads False."""
    r, _ = refresher()
    assert r._session_slots._value == FRESH_STAMP_WORKERS
    assert not r._optional_db_busy()
    # #11700's detached observation reads never count against the optional share.
    r._detached_reads = {asyncio.get_running_loop().create_future()}
    assert not r._optional_db_busy()


# ── preview capacity maintenance: the pass deadline cancels its read ─────────


class _Row:
    def __init__(self, **values):
        self._mapping = values

    def __getattr__(self, name):
        try:
            return self.__dict__["_mapping"][name]
        except KeyError:
            raise AttributeError(name) from None


class _HangingRead:
    """A capacity session whose first statement runs until released."""

    def __init__(self, row):
        self.row = row
        self.release = asyncio.Event()
        self.started = asyncio.Event()
        self.ended = None
        self.closed = 0

    @asynccontextmanager
    async def factory(self):
        outer = self

        class Session:
            async def execute(self, statement, params=None):
                outer.started.set()
                try:
                    await outer.release.wait()
                except asyncio.CancelledError:
                    outer.ended = "cancelled"
                    raise
                outer.ended = "finished"

                class Result:
                    def first(self):
                        return outer.row

                    def all(self):
                        return [outer.row]

                return Result()

        try:
            yield Session()
        finally:
            self.closed += 1


@pytest.fixture
def capacity(monkeypatch):
    """A refresher whose policy retirement reads through `_HangingRead`."""
    from app.utils import blend_preview

    calls = {"retire_policy": [], "published": []}

    class Registry:
        def retire_policy(self, *args):
            calls["retire_policy"].append(args)
            return None

    monkeypatch.setattr(blend_preview, "registry", lambda: Registry())
    r = LiveBlendRefresher("kalshi")
    read = _HangingRead(_Row(id=1, preview_rev=3))
    r._session_factory = read.factory
    r._reservation_context_query = lambda ids: ids

    async def publish(frames, **_):
        calls["published"].append(frames)

    r._publish_previews = publish
    return r, read, calls


async def _retire_under_pass(r, budget_s=.05):
    """One policy retirement inside a pass budget, as `_maintain_preview_capacity` runs it."""
    async with asyncio.timeout(budget_s) as budget:
        await r._retire_policy_preview_event(1, 7, 0, budget.when())


async def test_capacity_the_pass_deadline_cancels_the_read(capacity):
    r, read, calls = capacity
    with pytest.raises(TimeoutError):
        await _retire_under_pass(r)
    assert read.ended == "cancelled" and read.closed == 1
    assert not r._session_slots.locked() and r._session_slots._value == FRESH_STAMP_WORKERS
    assert calls == {"retire_policy": [], "published": []}


async def test_capacity_a_completed_read_proceeds(capacity):
    r, read, calls = capacity
    read.release.set()
    await _retire_under_pass(r, 1)
    assert len(calls["retire_policy"]) == 1 and calls["published"] == [[]]
