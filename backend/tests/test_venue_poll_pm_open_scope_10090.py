"""#10090 — the poll's Polymarket open-arm rendering follows
``POLYMARKET_WS_OPEN_SCOPE``. The real-Postgres population contract is
``tests/integration/test_venue_poll_pm_open_scope_pg_10090.py``; this file
pins the rendering and the wiring that every CI run can see."""

import pytest

from app.tasks import venue_poll_30s as v


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
    v._POPULATION.clear()
    try:
        await v.load_population(_Session(), "polymarket", now_mono=0.0)
    finally:
        v._POPULATION.clear()
    assert seen == [v.polymarket_population_sql(True, scope)]
