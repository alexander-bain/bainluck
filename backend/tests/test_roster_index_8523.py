"""#8523: the dropdown's roster index — one load per TTL, plain data, a failed
load that raises and is not retried on the next keystroke.

`/typeahead` runs on every keystroke. The index exists so that `patrick m`,
`patrick ma`, ... (each a two-word miss) cost a dict lookup rather than the
~120 ms roster query. What the real rows match is proven on Postgres in
`tests/integration/test_search_recall_contract.py`; this file pins the CACHE.
"""

import asyncio

import pytest

from app.routes import events as ev


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows=None, fail=False):
        self.rows = rows or []
        self.fail = fail
        self.executes = 0

    async def execute(self, _stmt):
        self.executes += 1
        if self.fail:
            raise RuntimeError("boom")
        return _Result(self.rows)


@pytest.fixture(autouse=True)
def _fresh_index(monkeypatch):
    monkeypatch.setattr(ev, "_roster_index", {})
    monkeypatch.setattr(ev, "_roster_index_expires_at", 0.0)
    yield


def _run(coro):
    return asyncio.run(coro)


def test_a_hit_answers_the_club_ids():
    db = _FakeDB([(560, "patrick mahomes"), (560, "travis kelce"), (31, "josh allen"),
                  (44, "josh allen")])
    assert _run(ev._roster_player_team_ids(db, "patrick mahomes")) == (560,)
    assert _run(ev._roster_player_team_ids(db, "josh allen")) == (31, 44)


def test_every_keystroke_after_the_first_costs_no_query():
    db = _FakeDB([(560, "patrick mahomes")])
    for key in ("patrick m", "patrick ma", "patrick mah", "patrick mahomes"):
        _run(ev._roster_player_team_ids(db, key))
    assert db.executes == 1


def test_the_index_reloads_after_its_ttl(monkeypatch):
    db = _FakeDB([(560, "patrick mahomes")])
    clock = [1000.0]
    monkeypatch.setattr(ev.time, "monotonic", lambda: clock[0])
    _run(ev._roster_player_team_ids(db, "x y"))
    clock[0] += ev._ROSTER_INDEX_TTL_S - 1
    _run(ev._roster_player_team_ids(db, "x y"))
    assert db.executes == 1
    clock[0] += 2
    _run(ev._roster_player_team_ids(db, "x y"))
    assert db.executes == 2


def test_a_failed_load_raises_then_waits_out_the_retry_window(monkeypatch):
    db = _FakeDB(fail=True)
    clock = [1000.0]
    monkeypatch.setattr(ev.time, "monotonic", lambda: clock[0])
    with pytest.raises(RuntimeError):
        _run(ev._roster_player_team_ids(db, "patrick mahomes"))
    # The next keystroke must not re-run a query that just failed.
    assert _run(ev._roster_player_team_ids(db, "patrick mahomes")) == ()
    assert db.executes == 1
    clock[0] += ev._ROSTER_INDEX_RETRY_S + 1
    with pytest.raises(RuntimeError):
        _run(ev._roster_player_team_ids(db, "patrick mahomes"))
    assert db.executes == 2


def test_whitespace_in_a_stored_name_is_collapsed():
    db = _FakeDB([(560, "patrick  mahomes ")])
    assert _run(ev._roster_player_team_ids(db, "patrick mahomes")) == (560,)


def test_the_index_holds_plain_data_only():
    """Gotcha #6 / #2107: a module-global cache must never hold ORM rows."""
    _run(ev._roster_player_team_ids(_FakeDB([(560, "patrick mahomes")]), "a b"))
    assert all(
        isinstance(k, str) and isinstance(v, tuple) and all(isinstance(i, int) for i in v)
        for k, v in ev._roster_index.items()
    )
