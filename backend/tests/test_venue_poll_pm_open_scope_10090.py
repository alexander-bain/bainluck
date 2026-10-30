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
    monkeypatch.delenv(v.HELD_ENV, raising=False)
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
    sql = v._pool_sql(venue, _window(), held=True)
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
    monkeypatch.setenv(v.HELD_ENV, "1")
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


# ── #10090 latency R1 on a792d96b: the held arm has its own flag, so A off
# changes nothing ─────────────────────────────────────────────────────────────


def _g2_pool_sql(venue, window_sql, held=False):
    """``_pool_sql`` as G2 2ac3c58f rendered it, verbatim: the baseline the
    unset flag must reproduce byte for byte."""
    from app.tasks.futures_price_refresh import HIGH_VALUE_SQL

    valued = f"({HIGH_VALUE_SQL} OR fm.id = ANY(CAST(:shown_ids AS integer[])))"
    return f"""
        unlinked AS MATERIALIZED (
            SELECT fm.id
              FROM futures_markets fm
             WHERE fm.status = 'open'
               AND fm.event_id IS NULL
               AND fm.source = '{venue}'
               AND {valued}
        ),
        linked AS MATERIALIZED (
            SELECT fm.id
              FROM events e
              JOIN futures_markets fm ON fm.event_id = e.id
             WHERE e.status = 'scheduled'
               AND e.commence_time > NOW()
               AND fm.status = 'open'
               AND fm.source = '{venue}'
               AND e.commence_time <= NOW() + make_interval(hours => :game_horizon_hours)
               AND NOT {v._socket_game_sql(window_sql)}
        ),
        pool AS (
            SELECT id FROM unlinked
            UNION
            SELECT id FROM linked
        )
    """


@pytest.mark.parametrize("raw", [None, "", "0", "off", "false", "no", "maybe"])
def test_the_held_flag_is_off_unless_set(raw):
    environ = {} if raw is None else {v.HELD_ENV: raw}
    assert v.held_arm_enabled(environ) is False


@pytest.mark.parametrize("raw", ["1", "on", "true", "YES", " 1 "])
def test_the_held_flag_turns_on(raw):
    assert v.held_arm_enabled({v.HELD_ENV: raw}) is True


def _population_renders(open_arm, scope):
    return (
        v.kalshi_population_sql(open_arm),
        v.polymarket_population_sql(open_arm, scope),
    )


@pytest.mark.parametrize("open_arm", [True, False])
@pytest.mark.parametrize("scope", ["all", "slate"])
def test_unset_both_venues_render_the_g2_population_byte_for_byte(
    monkeypatch, open_arm, scope
):
    actual = _population_renders(open_arm, scope)
    for sql in actual:
        assert "held" not in sql
    monkeypatch.setattr(v, "_pool_sql", _g2_pool_sql)
    assert actual == _population_renders(open_arm, scope)


@pytest.mark.parametrize("venue", ["polymarket", "kalshi"])
def test_on_is_the_unset_render_plus_the_held_arm_and_its_union_only(venue):
    off = v._pool_sql(venue, _window())
    on = v._pool_sql(venue, _window(), held=True)
    arm = on[on.index("\n        held AS MATERIALIZED"):on.index("\n        pool AS")]
    union = "\n            UNION\n            SELECT id FROM held"
    assert on.replace(arm, "", 1).replace(union, "", 1) == off


@pytest.mark.asyncio
@pytest.mark.parametrize("venue", ["polymarket", "kalshi"])
async def test_unset_the_population_read_never_reads_the_held_set(monkeypatch, venue):
    seen = []

    class _Rows:
        def fetchall(self):
            return []

    class _Session:
        async def execute(self, stmt, params=None):
            seen.append(str(stmt))
            return _Rows()

    def refuse():
        raise AssertionError("read_reader_presence called with the held arm off")

    monkeypatch.delenv(v.HELD_ENV, raising=False)
    monkeypatch.delenv("POLYMARKET_WS_OPEN_SCOPE", raising=False)
    monkeypatch.setattr(reader_presence, "read_reader_presence", refuse)
    monkeypatch.setattr(v, "_LAST_PRESENCE", None)
    monkeypatch.setattr(v, "shown_market_ids", lambda: [])
    v._POPULATION.clear()
    try:
        await v.load_population(_Session(), venue, now_mono=0.0)
    finally:
        v._POPULATION.clear()
    monkeypatch.setattr(v, "_pool_sql", _g2_pool_sql)
    if venue == "kalshi":
        expected = v.kalshi_population_sql(v._kalshi_open_arm())
    else:
        expected = v.polymarket_population_sql(v._polymarket_open_arm(), "all")
    assert seen == [expected]


@pytest.mark.asyncio
async def test_on_the_population_read_reads_both_signals_off_the_loop(monkeypatch):
    import threading

    loop_thread = threading.get_ident()
    threads = {}

    class _Rows:
        def fetchall(self):
            return []

    class _Session:
        async def execute(self, stmt, params=None):
            return _Rows()

    def shown():
        threads["shown"] = threading.get_ident()
        return []

    def held():
        threads["held"] = threading.get_ident()
        return ReaderPresence()

    monkeypatch.setenv(v.HELD_ENV, "1")
    monkeypatch.setattr(v, "shown_market_ids", shown)
    monkeypatch.setattr(v, "held_presence", held)
    v._POPULATION.clear()
    try:
        await v.load_population(_Session(), "polymarket", now_mono=0.0)
    finally:
        v._POPULATION.clear()
    assert set(threads) == {"shown", "held"}
    assert loop_thread not in threads.values()
