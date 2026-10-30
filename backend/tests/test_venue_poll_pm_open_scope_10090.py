"""#10090 — the poll's Polymarket open-arm rendering follows
``POLYMARKET_WS_OPEN_SCOPE``. The real-Postgres population contract is
``tests/integration/test_venue_poll_pm_open_scope_pg_10090.py``; this file
pins the rendering and the wiring that every CI run can see."""

import pytest

from app.tasks import venue_poll_30s as v
from app.utils import reader_presence
from app.utils.reader_presence import PresenceUnreadable, ReaderPresence


def _window():
    from app.tasks.polymarket_ws import _slate_event_window

    return v._render(_slate_event_window())


def test_all_claims_every_tokened_market_as_before():
    sql = v.polymarket_population_sql(True, "all")
    assert sql == v.polymarket_population_sql(True)
    assert "EXISTS (SELECT 1 FROM events e" not in sql


def test_slate_claims_a_tokened_market_only_inside_the_game_sockets_window():
    sql = v.polymarket_population_sql(True, "slate")
    claim = (
        "EXISTS (SELECT 1 FROM events e WHERE e.id = fm.event_id AND "
        f"{v._socket_game_sql(_window())})"
    )
    assert claim in sql
    assert "AND NOT ((COALESCE(fm.market_metadata->>'clob_token_ids'" in sql


def test_open_arm_off_claims_nothing_whatever_the_scope():
    assert v.polymarket_population_sql(False, "slate") == v.polymarket_population_sql(
        False, "all"
    )
    assert "clob_token_ids" not in v.polymarket_population_sql(False, "slate")


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["all", "slate"])
async def test_the_population_read_renders_the_flag_it_reads(monkeypatch, scope):
    seen = []

    class _Rows:
        def fetchall(self):
            return []

    class _Session:
        async def execute(self, stmt, params=None):
            seen.append(str(stmt))
            return _Rows()

    monkeypatch.setenv("POLYMARKET_WS_OPEN_SCOPE", scope)
    monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setattr(v, "shown_market_ids", lambda: [])
    monkeypatch.setattr(v, "held_presence", lambda: ReaderPresence())
    v._POPULATION.clear()
    try:
        await v.load_population(_Session(), "polymarket", now_mono=0.0)
    finally:
        v._POPULATION.clear()
    assert seen == [v.polymarket_population_sql(True, scope)]


# ── #10090 fixture 12 wiring: held markets join *shown* (the real-PG contract
# is the integration file's fixture 12) ─────────────────────────────────────


@pytest.mark.parametrize("venue", ["polymarket", "kalshi"])
def test_both_venues_pool_a_held_arm_minus_the_game_socket(venue):
    sql = v._pool_sql(venue, _window())
    assert "held AS MATERIALIZED" in sql
    assert "SELECT unnest(CAST(:held_market_ids AS integer[]))" in sql
    assert "h.event_id = ANY(CAST(:held_event_ids AS integer[]))" in sql
    held_arm = sql[sql.index("held AS MATERIALIZED"):sql.index("pool AS")]
    assert f"AND NOT {v._socket_game_sql(_window())}" in held_arm
    assert "SELECT id FROM held" in sql[sql.index("pool AS"):]


def test_the_binds_carry_the_held_set_and_default_to_nobody():
    binds = v.population_binds([1], ReaderPresence(frozenset({7, 5}), frozenset({9})))
    assert (binds["held_market_ids"], binds["held_event_ids"]) == ([5, 7], [9])
    empty = v.population_binds([])
    assert (empty["held_market_ids"], empty["held_event_ids"]) == ([], [])


@pytest.mark.asyncio
async def test_the_population_read_binds_the_held_set(monkeypatch):
    seen = []

    class _Rows:
        def fetchall(self):
            return []

    class _Session:
        async def execute(self, stmt, params=None):
            seen.append(params)
            return _Rows()

    held = ReaderPresence(frozenset({17}), frozenset({900}))
    monkeypatch.setattr(v, "shown_market_ids", lambda: [])
    monkeypatch.setattr(v, "held_presence", lambda: held)
    v._POPULATION.clear()
    try:
        await v.load_population(_Session(), "polymarket", now_mono=0.0)
    finally:
        v._POPULATION.clear()
    assert (seen[0]["held_market_ids"], seen[0]["held_event_ids"]) == ([17], [900])


def test_an_unreadable_held_set_reuses_the_last_one_read(monkeypatch):
    answers = [ReaderPresence(frozenset({17})), PresenceUnreadable("down")]

    def read():
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(v, "_LAST_PRESENCE", None)
    monkeypatch.setattr(reader_presence, "read_reader_presence", read)
    assert v.held_presence() == ReaderPresence(frozenset({17}))
    assert v.held_presence() == ReaderPresence(frozenset({17}))


def test_an_unreadable_held_set_with_none_read_holds_nobody(monkeypatch):
    def read():
        raise PresenceUnreadable("down")

    monkeypatch.setattr(v, "_LAST_PRESENCE", None)
    monkeypatch.setattr(reader_presence, "read_reader_presence", read)
    assert v.held_presence() == ReaderPresence()


def test_shown_is_the_one_served_definition(monkeypatch):
    monkeypatch.setattr(reader_presence, "served_market_ids", lambda: [3, 4])
    assert v.shown_market_ids() == [3, 4]
