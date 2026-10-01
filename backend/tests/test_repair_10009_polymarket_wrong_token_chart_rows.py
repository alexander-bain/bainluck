"""#10009 — the repair that takes the other side's price off Polymarket chart lines.

The repair is a D51(b) production write. Its policy is the pure row verdict
(``classify_row``) plus the group plan that feeds it the venue's two tokens, and
both are pinned here on the specimen's real shape: Phillies at Braves (event
15322407), the Braves ``_no`` leg whose stored YES price is the Phillies token.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    """Import a `scripts/` module by path (same seam as the #9066 test)."""
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


repair = _load("repair_10009_polymarket_wrong_token_chart_rows")
restore = _load("restore_10009_polymarket_wrong_token_chart_rows")

_CONDITION = "0x56843c39ee842fae25c33d55a160628192506e5a4d3df922ebd7f1faee8114dc"
_PHILLIES, _BRAVES = "PHILLIES_TOKEN_0", "BRAVES_TOKEN_1"

#: 2026-09-30 05:20Z: the venue's Phillies token read 0.445, so Braves 0.555.
#: The stored row (Braves leg) held 0.445.
_T = int(datetime(2026, 9, 30, 5, 20, 7, tzinfo=timezone.utc).timestamp())
_T2 = _T + 600


# ---------------------------------------------------------------------------
# The row verdict
# ---------------------------------------------------------------------------


def test_the_specimen_row_holds_the_wrong_tokens_price_and_flips():
    assert repair.classify_row(0.445, right_price=0.555, wrong_price=0.445) == repair.FLIP


def test_a_row_on_the_right_token_is_left():
    assert repair.classify_row(0.555, right_price=0.555, wrong_price=0.445) == repair.RIGHT


def test_a_row_at_even_money_is_ambiguous_and_left():
    """Both tokens read 0.50 — a flip would change nothing and proves nothing."""
    assert repair.classify_row(0.5, right_price=0.5, wrong_price=0.5) == repair.AMBIGUOUS


def test_a_row_with_no_venue_minute_is_left():
    assert repair.classify_row(0.445, right_price=None, wrong_price=0.445) == repair.UNMATCHED
    assert repair.classify_row(None, right_price=0.555, wrong_price=0.445) == repair.UNMATCHED


def test_tokens_that_are_not_complements_never_flip():
    """`1 - p` is the right token's price ONLY when the two books sum to 1."""
    assert (
        repair.classify_row(0.445, right_price=0.60, wrong_price=0.445)
        == repair.NOT_COMPLEMENT
    )


def test_a_row_matching_neither_token_is_left():
    assert repair.classify_row(0.30, right_price=0.555, wrong_price=0.445) == repair.NEITHER


def test_the_right_token_is_the_sockets_suffix_rule():
    assert repair.right_token_index(f"{_CONDITION}_no") == 1
    assert repair.right_token_index(f"{_CONDITION}_side1") == 1
    assert repair.right_token_index(f"{_CONDITION}_yes") == 0
    assert repair.right_token_index(_CONDITION) == 0
    assert repair.right_token_index("legacy_leg_b") is None


def test_venue_minutes_key_points_on_the_rails_minute():
    minutes = repair.venue_minutes([{"t": _T, "p": 0.445}, {"t": "bad", "p": 1}])
    assert minutes == {datetime(2026, 9, 30, 5, 20, tzinfo=timezone.utc): 0.445}


# ---------------------------------------------------------------------------
# The group plan, end to end on the specimen's shape
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows, self._scalar = rows or [], scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)

    def scalar(self):
        return self._scalar

    def mappings(self):
        return self._rows


class _Session:
    """Answers the plan's three reads by what each one selects."""

    def __init__(self, *, leg_ext, stored_tokens, snaps):
        self.leg_ext, self.stored_tokens, self.snaps = leg_ext, stored_tokens, snaps

    async def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM futures_outcomes" in sql:
            return _Result(rows=[self.leg_ext])
        if "clob_token_ids" in sql:
            return _Result(scalar=self.stored_tokens)
        if "FROM win_prob_snapshots" in sql:
            return _Result(rows=self.snaps)
        raise AssertionError(f"unexpected SQL: {sql[:80]}")


def _service(clob_tokens=(_PHILLIES, _BRAVES)):
    history = {
        _PHILLIES: [{"t": _T, "p": 0.445}, {"t": _T2, "p": 0.5}],
        _BRAVES: [{"t": _T, "p": 0.555}, {"t": _T2, "p": 0.5}],
    }
    return SimpleNamespace(
        get_clob_market_by_condition=AsyncMock(
            return_value={"tokens": [{"token_id": t} for t in clob_tokens]}
        ),
        get_prices_history=AsyncMock(
            side_effect=lambda token_id, **_: history[token_id]
        ),
    )


def _snap(row_id, ts, yes, stamped=False):
    return {
        "id": row_id,
        "captured_at": datetime.fromtimestamp(ts, tz=timezone.utc),
        "yes": yes,
        "stamped": stamped,
    }


_GROUP = {"event_id": 15322407, "market_id": 63069860, "leg": "Atlanta Braves"}


async def test_the_braves_rows_holding_the_phillies_price_are_planned_for_a_flip():
    session = _Session(
        leg_ext=f"{_CONDITION}_no",
        stored_tokens=[_PHILLIES, _BRAVES],
        snaps=[_snap(1, _T, 0.445), _snap(2, _T2, 0.5)],
    )
    service = _service()

    why, rows = await repair._plan_group(session, service, _GROUP)

    assert why is None
    assert rows == [
        {"id": 1, "verdict": repair.FLIP},
        {"id": 2, "verdict": repair.AMBIGUOUS},
    ]
    service.get_clob_market_by_condition.assert_awaited_once_with(_CONDITION)


async def test_a_second_run_never_flips_a_row_back():
    """Already repaired (stamped, and now equal to the right token): left."""
    session = _Session(
        leg_ext=f"{_CONDITION}_no",
        stored_tokens=[_PHILLIES, _BRAVES],
        snaps=[_snap(1, _T, 0.555, stamped=True)],
    )
    why, rows = await repair._plan_group(session, _service(), _GROUP)
    assert why is None
    assert rows == [{"id": 1, "verdict": repair.RIGHT}]


async def test_a_stamped_row_that_reads_wrong_is_never_flipped_twice():
    session = _Session(
        leg_ext=f"{_CONDITION}_no",
        stored_tokens=[_PHILLIES, _BRAVES],
        snaps=[_snap(1, _T, 0.445, stamped=True)],
    )
    _why, rows = await repair._plan_group(session, _service(), _GROUP)
    assert rows == [{"id": 1, "verdict": repair.NEITHER}]


async def test_a_token_order_disagreement_skips_the_group():
    session = _Session(
        leg_ext=f"{_CONDITION}_no",
        stored_tokens=[_BRAVES, _PHILLIES],
        snaps=[_snap(1, _T, 0.445)],
    )
    why, rows = await repair._plan_group(session, _service(), _GROUP)
    assert why and "order" in why
    assert rows == []


async def test_a_leg_whose_suffix_names_no_token_is_skipped():
    session = _Session(leg_ext="legacy_leg_b", stored_tokens=None, snaps=[])
    why, rows = await repair._plan_group(session, _service(), _GROUP)
    assert why and "names no token" in why
    assert rows == []


async def test_a_condition_without_two_clob_tokens_is_skipped():
    session = _Session(leg_ext=f"{_CONDITION}_no", stored_tokens=None, snaps=[])
    why, _rows = await repair._plan_group(session, _service(clob_tokens=(_PHILLIES,)), _GROUP)
    assert why and "not 2" in why


# ---------------------------------------------------------------------------
# The write, the undo and the app refusal
# ---------------------------------------------------------------------------


def test_the_flip_refuses_rows_already_stamped_and_rows_it_does_not_own():
    sql = " ".join(repair.FLIP_SQL.split())
    assert "NOT (game_state ? 'token_repair')" in sql
    assert "source = 'polymarket'" in sql
    assert "game_state->>'poll_type' = 'history_backfill'" in sql
    assert "home_win_probability = 1 - home_win_probability" in sql
    assert "away_win_probability = 1 - away_win_probability" in sql


def test_the_undo_restores_only_rows_still_carrying_the_stamp():
    sql = " ".join(restore.RESTORE_SQL.split())
    assert repair.BACKUP_TABLE in sql
    assert "s.game_state->>'token_repair' = :stamp" in sql
    assert restore.REPAIR_STAMP == repair.REPAIR_STAMP


@pytest.mark.parametrize("app", [None, "bainluck", "bainluck-staging"])
def test_only_heavy_may_apply(monkeypatch, app):
    if app is None:
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    else:
        monkeypatch.setenv("HEROKU_APP_NAME", app)
    assert repair.wrong_app_refusal() is not None


def test_heavy_may_apply(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert repair.wrong_app_refusal() is None


async def test_apply_off_heavy_refuses_before_touching_anything(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    assert await repair.run(True, 14, 14) == 2
    assert await restore.run(True) == 2
