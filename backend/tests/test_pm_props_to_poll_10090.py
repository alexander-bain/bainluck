"""#10090 `PM_WS_PROPS_TO_POLL` — venue-labelled props leave both Polymarket socket
arms and the 30-second poll prices them (Alex 2026-11-01 ~9:05 AM PT, CPU item 5).

At 17:10Z 5,267 of the game window's 5,538 Polymarket markets (10,090 of ~11,200
subscribed tokens) carried a venue label other than ``moneyline``: props the
blend never reads, on a venue process at 0.96 of a core. On by default since
the settings freeze (production since 2026-11-01, docs/live-settings.md);
``PM_WS_PROPS_TO_POLL=0`` is off, and off every arm is exactly what it was. On:

* the game arm's real loader drops every market ``pm_non_speaking_metadata``
  refutes (no token, no top-up, no event link) and keeps the rest unchanged;
* the open arm's slate seed excludes the same markets by the same rule in SQL
  (a held event's markets still come back through the held-event seed);
* the poll's population gains them: the socket window's events, the refusal;
* a held game's event can bring the open arm's refresh forward.
"""

import pytest
from sqlalchemy.dialects import postgresql

import app.tasks.polymarket_open_contracts as poc
import app.tasks.venue_poll_30s as v
from app.utils.content_understanding import (
    CONTENT_UNDERSTANDING_KEY, CONTENT_UNDERSTANDING_VERSION,
)
from app.services.polymarket_api import GAMMA_FULL_CONTEST_WINNER_TYPES
from tests.test_pm_slate_metadata_projection_10663 import STORED, real_loader


@pytest.mark.parametrize("raw, on", [(None, True), ("", True), ("0", False), (" 0 ", False),
                                     ("1", True), (" 1 ", True), ("yes", True)])
def test_the_switch_is_on_unless_exactly_zero(monkeypatch, raw, on):
    if raw is None:
        monkeypatch.delenv("PM_WS_PROPS_TO_POLL", raising=False)
    else:
        monkeypatch.setenv("PM_WS_PROPS_TO_POLL", raw)
    assert poc.props_to_poll_enabled() is on


@pytest.mark.asyncio
@pytest.mark.parametrize("stored_live_only", [False, True])
async def test_the_game_arm_drops_exactly_the_refuted_markets(monkeypatch, stored_live_only):
    off, _, off_calls = real_loader(STORED)
    on, _, on_calls = real_loader(STORED)
    monkeypatch.setenv("PM_WS_PROPS_TO_POLL", "0")
    want = await off(stored_live_only=stored_live_only)
    monkeypatch.setenv("PM_WS_PROPS_TO_POLL", "1")
    got = await on(stored_live_only=stored_live_only)

    refuted = {8, 15}  # tennis_completed_match, total
    assert want["non_blend_market_ids"] == refuted
    assert got["non_blend_market_ids"] == set()
    assert got["market_ids"] == want["market_ids"] - refuted
    assert not refuted & set(got["event_id_by_market"])
    assert not refuted & set(got["asset_to_market"].values())
    assert {a for a, m in want["asset_to_market"].items() if m not in refuted} == set(
        got["asset_to_market"])
    for (_kind, *rest_off), (_k, *rest_on) in zip(off_calls, on_calls):
        if _kind == "market":
            assert {m for m, _c in rest_on[0]} == {m for m, _c in rest_off[0]} - refuted


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(),
                            compile_kwargs={"literal_binds": True}))


def test_the_open_arms_slate_seed_excludes_them_only_when_on(monkeypatch):
    monkeypatch.setenv("PM_WS_PROPS_TO_POLL", "0")
    off = _sql(poc.open_contract_scope_markets_stmt())
    assert "venue_type" not in off
    monkeypatch.setenv("PM_WS_PROPS_TO_POLL", "1")
    on = _sql(poc.open_contract_scope_markets_stmt())
    assert on.startswith(off.split(" WHERE ")[0]) and "venue_type" in on and "NOT" in on
    # Unset is on.
    monkeypatch.delenv("PM_WS_PROPS_TO_POLL", raising=False)
    assert _sql(poc.open_contract_scope_markets_stmt()) == on


def test_the_poll_population_is_unchanged_off_and_gains_the_props_arm_on(monkeypatch):
    monkeypatch.setenv("PM_WS_PROPS_TO_POLL", "0")
    off = v.polymarket_population_sql(False)
    assert "props AS" not in off and "FROM props" not in off
    monkeypatch.setenv("PM_WS_PROPS_TO_POLL", "1")
    on = v.polymarket_population_sql(False)
    assert "props AS MATERIALIZED" in on and "SELECT id FROM props" in on
    assert v.PM_VENUE_LABEL_REFUSAL_SQL in on
    # the props arm is the socket's own window, rendered, not a restatement
    from app.tasks.polymarket_ws import _slate_event_window
    assert f"COALESCE({v._render(_slate_event_window())}, FALSE)" in on
    # and with it off again, byte-identical
    monkeypatch.setenv("PM_WS_PROPS_TO_POLL", "0")
    assert v.polymarket_population_sql(False) == off
    # unset is on
    monkeypatch.delenv("PM_WS_PROPS_TO_POLL", raising=False)
    assert v.polymarket_population_sql(False) == on


def test_the_written_out_refusal_names_the_rules_constants():
    """The poll's SQL is written with `->`; pin it to the constants the Python
    rule and the Core clause read, so a change to either fails here."""
    sql = v.PM_VENUE_LABEL_REFUSAL_SQL
    assert GAMMA_FULL_CONTEST_WINNER_TYPES == frozenset({"moneyline"})
    assert f"'{CONTENT_UNDERSTANDING_KEY}'" in sql
    assert f"->>'v') = '{CONTENT_UNDERSTANDING_VERSION}'" in sql
    assert "<> 'moneyline'" in sql and sql.startswith("COALESCE(")
