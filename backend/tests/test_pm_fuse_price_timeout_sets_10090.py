"""#10090 — a DNPL game chunk arms and restores its two budgets in one statement each.

The bound price transaction sent SET lock_timeout, then the statement-timeout
arm; after the UPDATE, the statement-timeout restore, then SET lock_timeout.
Fused, each pair is one statement — same transaction, order and values — and
every other chunk is unchanged. The `PM_FUSE_PRICE_TIMEOUT_SETS` off switch was
removed in the settings freeze (docs/live-settings.md): fused is the only path.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace as NS

import pytest

from app.tasks import polymarket_ws as pm
from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL, SET_STATEMENT_TIMEOUT_SQL
from tests.test_pm_quote_lock_bound_10090 import writer_rig
from tests.test_ws_flush_cadence_10090 import _FakeTime

NAMES = {
    id(SET_LOCK_TIMEOUT_SQL): "set_lock",
    id(SET_STATEMENT_TIMEOUT_SQL): "set_statement",
    id(pm.ARM_DNPL_PRICE_STATEMENT_TIMEOUT_SQL): "arm",
    id(pm.ARM_LOCK_AND_DNPL_PRICE_STATEMENT_TIMEOUT_SQL): "arm_lock_and_statement",
    id(pm.RESTORE_DNPL_PRICE_TIMEOUTS_SQL): "restore_statement_and_lock",
}


def recording_writer(monkeypatch, *, scope):
    r, state = writer_rig(_FakeTime(monkeypatch, t=1000), books={})
    state.held = False
    r.ns["blend_refresher"].preview = scope != "off"
    r.ns["blend_refresher"].preview_events = {90} if scope != "off" else set()
    if scope == "prop":
        r.ns["non_blend_outcome_ids"].add(1)
    sent = []
    factory = r.ns["get_task_session"]

    class Session:
        def __init__(self, original):
            self.original, self.info = original, original.info

        async def execute(self, stmt, params=None):
            name = NAMES.get(id(stmt))
            if name is None:
                sent.append((stmt[0], None))
                return await self.original.execute(stmt, params)
            sent.append((name, params))
            # The rig's session tracks the lock budget each statement runs under.
            lock_ms = params.get("lock_ms") if name != "set_lock" else params["ms"]
            if lock_ms is not None:
                await self.original.execute(SET_LOCK_TIMEOUT_SQL, {"ms": lock_ms})
            if name in ("arm", "arm_lock_and_statement"):
                return NS(scalar_one=lambda: "2s")
            return NS()

    @asynccontextmanager
    async def sessions():
        async with factory() as original:
            yield Session(original)

    r.ns["get_task_session"] = sessions
    return r, state, sent


FUSED = [
    ("arm_lock_and_statement", {"lock_ms": "50ms", "ms": "250ms"}),
    ("price", None),
    ("restore_statement_and_lock", {"ms": "2s", "lock_ms": "500ms"}),
    ("rank", None),
]


async def test_a_bound_game_chunk_sends_each_pair_as_one_statement(monkeypatch):
    r, state, sent = recording_writer(monkeypatch, scope="game")
    assert (await r.ns["write_chunk"]({1: .6, 2: .4})).written_ids == (1, 2)
    assert sent == FUSED
    assert state.commits == [1, 2]
    # The UPDATE waits 50 ms for a lock, the rerank 500 ms.
    assert state.statement_budgets == [("price", 0.05), ("rank", 0.5)]
    assert len(sent) == 4


@pytest.mark.parametrize("scope,final", [("off", False), ("prop", False), ("game", True)],
                         ids=["preview-off", "prop-chunk", "final-drain"])
async def test_an_unbound_chunk_arms_no_statement_budget(monkeypatch, scope, final):
    r, state, sent = recording_writer(monkeypatch, scope=scope)
    assert (await r.ns["write_chunk"]({1: .6, 2: .4}, final=final)).written_ids == (1, 2)
    assert not any(name.startswith(("arm", "restore")) for name, _ in sent)


def test_the_fused_arm_keeps_the_existing_cap_rule_verbatim():
    # Drift guard: the tighter-prior rule must be the separate arm's own text.
    separate = " ".join(pm.ARM_DNPL_PRICE_STATEMENT_TIMEOUT_SQL.text.split())
    fused = " ".join(pm.ARM_LOCK_AND_DNPL_PRICE_STATEMENT_TIMEOUT_SQL.text.split())
    rule = separate[separate.index("CASE"):separate.index("END") + len("END")]
    assert rule in fused
    assert "MATERIALIZED" in fused
    # Same order as the separate statements: lock first on arm, last on restore.
    assert fused.index("'lock_timeout'") < fused.index("'statement_timeout', CASE")
    restore = pm.RESTORE_DNPL_PRICE_TIMEOUTS_SQL.text
    assert restore.index("'statement_timeout'") < restore.index("'lock_timeout'")


def test_the_off_switch_is_gone():
    assert not hasattr(pm, "PM_FUSE_PRICE_TIMEOUT_SETS")
    assert not hasattr(pm, "_fuse_price_timeout_sets_env")
