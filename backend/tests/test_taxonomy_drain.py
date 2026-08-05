"""Tests for the old-tail taxonomy drain (UX-P001, gotcha #109/#47/#42).

Guards the properties that make a tail actually drain:
* oldest-first keyset ordering (``id > cursor ORDER BY id ASC``) — a newest-first
  backfill can never reach the tail (#109);
* commit-before-cursor-advance (#47) — a crash re-does an idempotent slice, it
  never skips untagged rows;
* wrap-to-start on a completed pass, so new/poison tail rows are re-scanned;
* per-row poison isolation (#42).
"""

from types import SimpleNamespace

import pytest

from app.tasks.taxonomy import (
    _MARKET_DRAIN_CURSOR_KEY,
    _drain_missing_market_tags,
    _read_cursor,
)


class _FakeRedis:
    def __init__(self, initial=None, log=None):
        self.store = dict(initial or {})
        self.log = log if log is not None else []

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.log.append(("setex", key))
        self.store[key] = str(value).encode()

    def delete(self, key):
        self.log.append(("delete", key))
        self.store.pop(key, None)


class _FakeResult:
    def __init__(self, rows=None, scalar_val=None):
        self._rows = rows or []
        self._scalar = scalar_val

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _FakeSession:
    def __init__(self, results, log):
        self._results = list(results)
        self.statements = []
        self.log = log

    async def execute(self, stmt):
        self.statements.append(str(stmt))
        return self._results.pop(0)

    async def commit(self):
        self.log.append(("commit", None))


def _market(mid, **over):
    base = dict(
        id=mid,
        llm_sport_category="basketball",
        llm_league="NBA",
        llm_gender=None,
        llm_level=None,
        market_tier=1,
        category="championship",
        status="open",
        resolution_date=None,
        source="kalshi",
        market_tags=[],
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_read_cursor_parses_bytes_and_defaults_to_zero():
    assert _read_cursor(_FakeRedis({"k": b"42"}), "k") == 42
    assert _read_cursor(_FakeRedis({}), "k") == 0
    assert _read_cursor(_FakeRedis({"k": b"junk"}), "k") == 0


async def test_market_drain_tags_slice_oldest_first_commit_before_cursor():
    log = []
    m1, m2 = _market(101), _market(202)
    session = _FakeSession(
        results=[_FakeResult(rows=[m1, m2]), _FakeResult(scalar_val=45000)],
        log=log,
    )
    rc = _FakeRedis(log=log)

    result = await _drain_missing_market_tags(session, rc, slice_limit=500)

    assert result["checked"] == 2
    assert result["tagged"] == 2
    assert result["remaining"] == 45000
    # Cursor advances to the LAST (highest) id in the oldest-first slice.
    assert result["cursor"] == 202

    # Oldest-first keyset: the select must filter id > cursor and ORDER BY id ASC.
    select_sql = session.statements[0]
    assert "futures_markets.id >" in select_sql
    assert "ORDER BY futures_markets.id ASC" in select_sql

    # Commit strictly precedes the cursor setex (#47).
    assert ("commit", None) in log
    assert ("setex", _MARKET_DRAIN_CURSOR_KEY) in log
    assert log.index(("commit", None)) < log.index(("setex", _MARKET_DRAIN_CURSOR_KEY))

    # Tags were actually computed onto the rows.
    assert "sport:basketball" in m1.market_tags


async def test_market_drain_wraps_cursor_when_pass_complete():
    log = []
    session = _FakeSession(
        results=[_FakeResult(rows=[]), _FakeResult(scalar_val=0)],
        log=log,
    )
    rc = _FakeRedis(initial={_MARKET_DRAIN_CURSOR_KEY: b"999"}, log=log)

    result = await _drain_missing_market_tags(session, rc, slice_limit=500)

    assert result["checked"] == 0
    assert result["wrapped"] is True
    assert result["remaining"] == 0
    # Wrapping deletes the cursor so the next run re-scans from id 0.
    assert _MARKET_DRAIN_CURSOR_KEY not in rc.store
    assert ("delete", _MARKET_DRAIN_CURSOR_KEY) in log


async def test_market_drain_isolates_a_poison_row():
    log = []
    good = _market(1)
    # Force a hard failure on the poison row: a non-str llm_league breaks the
    # ``.lower()`` inside compute_market_tags.
    poison = _market(2, llm_league=123)
    session = _FakeSession(
        results=[_FakeResult(rows=[good, poison]), _FakeResult(scalar_val=1)],
        log=log,
    )
    rc = _FakeRedis(log=log)

    result = await _drain_missing_market_tags(session, rc, slice_limit=500)

    # The healthy sibling still got tagged; the pass was not wiped (#42).
    assert result["checked"] == 2
    assert result["tagged"] == 1
    assert "sport:basketball" in good.market_tags
    # Cursor still advances past the poison row so the slice makes progress.
    assert result["cursor"] == 2
