"""Queue #261 Item 2 — Polymarket websocket resolution leakage contract.

The websocket ``market_resolved`` path must set status/winner but MUST NOT copy
the last buffered trade into ``calibration_probability`` — a terminal price
cannot both define the winner and grade the earlier/current forecast
(self-grading leakage, C20/C21). It also routes the winner write through the
resolution-authority contract: an outcome an authoritative settlement already
owns is left untouched.
"""

from collections import namedtuple

import pytest

from app.tasks.polymarket_ws import _apply_ws_resolution

_Row = namedtuple("_Row", ["id", "resolution_source"])


def _make_session(existing_rows):
    """A minimal async session double: the SELECT returns ``existing_rows``,
    every UPDATE is captured for inspection."""
    captured = []

    class _Session:
        async def execute(self, stmt, *args, **kwargs):
            captured.append(stmt)
            if str(stmt).strip().upper().startswith("SELECT"):
                class _Res:
                    def all(self_inner):
                        return existing_rows
                return _Res()
            return None

    return _Session(), captured


def _stmts_text(captured):
    return [str(s) for s in captured]


@pytest.mark.asyncio
async def test_resolution_never_writes_calibration_probability():
    # Fresh resolution: no prior source, so both outcomes are graded.
    session, captured = _make_session(
        [_Row(1, None), _Row(2, None)]
    )
    written = await _apply_ws_resolution(
        session, market_id=10,
        outcomes=[(1, "0xabc_yes"), (2, "0xabc_no")],
        winning_outcome="yes",
    )
    assert written == 2
    texts = _stmts_text(captured)
    # THE contract: no statement writes calibration_probability.
    assert all("calibration_probability" not in t for t in texts), texts
    # Status is set to resolved, and is_winner IS written (winner/status update).
    assert any("futures_markets" in t and "status" in t for t in texts)
    assert any("SET is_winner" in t or "is_winner=" in t for t in texts)


@pytest.mark.asyncio
async def test_authoritative_existing_resolution_is_not_rewritten():
    # Outcome 1 already settled authoritatively (api_settlement) → skipped;
    # outcome 2 unresolved → graded. A bare websocket push must not downgrade
    # the authoritative winner.
    session, captured = _make_session(
        [_Row(1, "api_settlement"), _Row(2, None)]
    )
    written = await _apply_ws_resolution(
        session, market_id=10,
        outcomes=[(1, "0xabc_yes"), (2, "0xabc_no")],
        winning_outcome="no",
    )
    assert written == 1  # only the unresolved outcome
    texts = _stmts_text(captured)
    assert all("calibration_probability" not in t for t in texts), texts


@pytest.mark.asyncio
async def test_price_derived_existing_is_regradable_but_still_no_scalar():
    # settlement_sync is price-derived (tier 3 authority) — it IS authoritative,
    # so the websocket leaves it alone; the point is that NO run of this path
    # ever writes a calibration scalar regardless of the prior source.
    session, captured = _make_session([_Row(1, "settlement_sync")])
    written = await _apply_ws_resolution(
        session, market_id=10,
        outcomes=[(1, "0xabc_yes")],
        winning_outcome="yes",
    )
    # settlement_sync is authoritative → skipped.
    assert written == 0
    assert all("calibration_probability" not in str(s) for s in captured)
