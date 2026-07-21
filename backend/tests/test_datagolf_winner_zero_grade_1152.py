"""Regression guards for #1152: DataGolf Winner/Top-N markets grading the
CHAMPION as a loser (0 winners) for ~4 tournaments since 2026-07-05.

Root cause: the authoritative leaderboard resolver (_backfill_datagolf_winners)
sat in the budget-starved Phase-0g tail of _backfill_all_winners and stopped
running ~2026-07-05, while the earlier heuristic all_losers pass (inside
_backfill_from_current_probability) graded the ENTIRE winner field — including
the champion — as losers, because the champion's stored current_probability is
a stale pre-win model prediction (e.g. 0.45%) that never converged above the
0.10 all_losers ceiling. The concept/event page then showed the champion as a
loser.

Fix: (1) run _backfill_datagolf_winners() in the un-budget-guarded core section
BEFORE the current-probability heuristic, and (2) exclude source='datagolf' from
the all_losers pass so the heuristic can never touch golf winner/top-N markets
(they have their own authoritative leaderboard resolver).
"""

import importlib
import inspect

import pytest

# NB: `from app.tasks import backfill_winners` yields the registered Celery TASK
# object (which shadows the module name), not the module. Load the module
# explicitly so monkeypatch/inspect see the real functions.
bw = importlib.import_module("app.tasks.backfill_winners")


# ---------------------------------------------------------------------------
# Mock async session harness (mirrors tests/test_golf_commence_fix.py).
# ---------------------------------------------------------------------------
class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _MockSession:
    """Serves canned SELECT results in order; records UPDATE params."""

    def __init__(self, select_results):
        self._selects = list(select_results)
        self.updates = []  # list of param dicts for UPDATE statements
        self.committed = False

    async def execute(self, stmt, params=None):
        s = str(stmt)
        if "UPDATE" in s:
            self.updates.append(params)
            return _Result([])
        return self._selects.pop(0)

    async def commit(self):
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _full_field_leaderboard(champion_dg_id=11889):
    """A realistic full (>=100) final leaderboard with a single position '1'."""
    lb = [{"dg_id": champion_dg_id, "name": "Champion", "position": "1"}]
    # positions 2..156 (mix of ties + numerics) so the field is a full field.
    for i in range(2, 157):
        lb.append({"dg_id": 20000 + i, "name": f"Player {i}", "position": str(i)})
    return lb


@pytest.mark.asyncio
async def test_winner_market_champion_graded_true_not_loser(monkeypatch):
    """The dg_id at leaderboard position '1' must resolve is_winner=TRUE and be
    the ONLY winner in a DataGolf 'win' market — never all-losers."""
    champion = 11889
    leaderboard = _full_field_leaderboard(champion)

    market = _Row(
        id=1,
        external_id="datagolf:pga:100:win",
        market_metadata={"leaderboard": leaderboard},
    )
    outcomes = [
        _Row(id=101, external_id=f"dg_{champion}"),   # champion, pos "1"
        _Row(id=102, external_id="dg_20009"),         # runner-ish, pos "9"
        _Row(id=103, external_id="dg_99999"),         # absent → did_not_play
    ]

    sess = _MockSession([_Result([market]), _Result(outcomes)])
    monkeypatch.setattr(bw, "get_task_session", lambda: sess)

    stats = await bw._backfill_datagolf_winners()

    by_oid = {u["oid"]: u for u in sess.updates}
    # Champion is a winner via the authoritative leaderboard source.
    assert by_oid[101]["won"] is True
    assert by_oid[101]["src"] == "leaderboard"
    # Non-winning field members are losers, absent player did_not_play.
    assert by_oid[102]["won"] is False
    assert by_oid[103]["won"] is False
    assert by_oid[103]["src"] == "did_not_play"
    # Exactly ONE winner — the defect was ZERO winners.
    assert sum(1 for u in sess.updates if u["won"] is True) == 1
    assert stats["winners_set"] == 1


@pytest.mark.asyncio
async def test_top5_market_grades_top_finishers_true(monkeypatch):
    """A DataGolf top_5 market must grade positions 1-5 as winners (not zero)."""
    leaderboard = [
        {"dg_id": 1, "position": "1"},
        {"dg_id": 2, "position": "T2"},
        {"dg_id": 3, "position": "T2"},
        {"dg_id": 4, "position": "4"},
        {"dg_id": 5, "position": "5"},
        {"dg_id": 6, "position": "6"},
    ]
    # pad to a full field so absent-inference is unambiguous
    for i in range(7, 157):
        leaderboard.append({"dg_id": i, "position": str(i)})

    market = _Row(
        id=2,
        external_id="datagolf:pga:100:top_5",
        market_metadata={"leaderboard": leaderboard},
    )
    outcomes = [
        _Row(id=201, external_id="dg_1"),
        _Row(id=205, external_id="dg_5"),
        _Row(id=206, external_id="dg_6"),
    ]
    sess = _MockSession([_Result([market]), _Result(outcomes)])
    monkeypatch.setattr(bw, "get_task_session", lambda: sess)

    await bw._backfill_datagolf_winners()

    by_oid = {u["oid"]: u for u in sess.updates}
    assert by_oid[201]["won"] is True   # 1st
    assert by_oid[205]["won"] is True   # 5th (== threshold)
    assert by_oid[206]["won"] is False  # 6th
    assert sum(1 for u in sess.updates if u["won"] is True) == 2


def test_all_losers_pass_excludes_datagolf():
    """The all_losers heuristic must never touch DataGolf markets — they have
    an authoritative leaderboard resolver. Without this exclusion the champion
    (stale sub-1% current_probability) is graded a loser (#1152)."""
    src = inspect.getsource(bw._backfill_from_current_probability)
    assert "resolution_source = 'all_losers'" in src
    # The all_losers CTE (all_loser_markets) must filter out datagolf.
    cte = src[src.index("all_loser_markets"): src.index("resolution_source = 'all_losers'")]
    assert "fm.source != 'datagolf'" in cte, (
        "all_losers pass must exclude source='datagolf'"
    )


def test_datagolf_winner_resolution_runs_before_current_probability():
    """The authoritative leaderboard resolver must be invoked BEFORE the
    current-probability heuristic in the main pipeline, so the champion is set
    is_winner=TRUE before all_losers can run. Guards against the budget-starved
    Phase-0g tail placement that let the resolver silently stop running."""
    src = inspect.getsource(bw._backfill_all_winners)
    dg_call = src.index("await _backfill_datagolf_winners()")
    prob_call = src.index("await _backfill_from_current_probability()")
    assert dg_call < prob_call, (
        "_backfill_datagolf_winners() must run before "
        "_backfill_from_current_probability() (#1152)"
    )
