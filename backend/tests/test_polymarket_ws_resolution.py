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

from app.tasks.polymarket_ws import (
    WS_RESOLUTION_UNCONFIRMED,
    WS_RESOLUTION_VOID,
    WS_RESOLUTION_WINNER,
    _apply_ws_resolution,
    ws_resolution_verdict,
)

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
        verdict=(WS_RESOLUTION_WINNER, 1),
    )
    assert written == 2
    texts = _stmts_text(captured)
    # THE contract: no statement writes calibration_probability.
    assert all("calibration_probability" not in t for t in texts), texts
    # Status is set to resolved, and is_winner IS written (winner/status update).
    assert any("futures_markets" in t and "status" in t for t in texts)
    assert any("SET is_winner" in t or "is_winner=" in t for t in texts)


@pytest.mark.asyncio
async def test_winner_write_stamps_authoritative_source_atomically():
    """Queue #284 Item 1: every applied winner write sets ``resolution_source`` in
    the SAME UPDATE statement as ``is_winner`` (a registered tier-3 source,
    ``clob_authoritative``) — so a failed/partial write can never leave a graded
    outcome with a NULL source (tier -1, silently overwritable by a later guess),
    and the WS-settled winner is calibration-truth eligible."""
    from app.utils.resolution_authority import (
        is_authoritative,
        is_calibration_truth_eligible,
    )

    session, captured = _make_session([_Row(1, None), _Row(2, None)])
    written = await _apply_ws_resolution(
        session, market_id=10,
        outcomes=[(1, "0xabc_yes"), (2, "0xabc_no")],
        verdict=(WS_RESOLUTION_WINNER, 1),
    )
    assert written == 2

    # Every outcome UPDATE that writes is_winner also writes resolution_source,
    # and every such statement carries the SAME registered source value.
    winner_updates = [
        s for s in captured
        if "futures_outcomes" in str(s) and "is_winner" in str(s)
    ]
    assert winner_updates, [str(s) for s in captured]
    for stmt in winner_updates:
        text = str(stmt)
        assert "resolution_source" in text, text
        params = stmt.compile().params
        assert params.get("resolution_source") == "clob_authoritative"

    # The stamped source is authoritative (tier 3) and eligible to grade the
    # published calibration curve.
    assert is_authoritative("clob_authoritative")
    assert is_calibration_truth_eligible("clob_authoritative")


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
        verdict=(WS_RESOLUTION_WINNER, 2),
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
        verdict=(WS_RESOLUTION_WINNER, 1),
    )
    # settlement_sync is authoritative → skipped.
    assert written == 0
    assert all("calibration_probability" not in str(s) for s in captured)


# ── #9418: the winner is the CLOB-confirmed TOKEN, never the push's label ─────
#
# Production 2026-09-30/10-01: 2,471 of 2,618 markets this socket settled in a
# day were stored with EVERY leg `is_winner=False` under `clob_authoritative`,
# because the venue's `winning_outcome` is a display word ("Over", "Stefan
# Kozlov") and the old writer graded only a literal yes/no on a `_yes`/`_no`
# leg. The payloads below are the venue's own, captured from the public CLOB
# socket and `/markets/{condition}` on 2026-10-01.

_OVER = "1099789015" + "0" * 66   # BOS@NYY "O/U 3.5" Over token (shape only)
_UNDER = "2688334074" + "0" * 66
_COND = "0x" + "ab" * 32


def _push(winning_asset_id=_OVER, label="Over"):
    return {
        "event_type": "market_resolved",
        "market": _COND,
        "assets_ids": [_OVER, _UNDER],
        "winning_asset_id": winning_asset_id,
        "winning_outcome": label,
    }


def _clob(over_winner, under_winner, over_price, under_price, closed=True):
    return {
        "closed": closed,
        "tokens": [
            {"token_id": _OVER, "outcome": "Over", "winner": over_winner, "price": over_price},
            {"token_id": _UNDER, "outcome": "Under", "winner": under_winner, "price": under_price},
        ],
    }


_ASSETS = {_OVER: 101, _UNDER: 102}
_LEGS = [101, 102]


def _verdict(push, clob, legs=_LEGS, assets=_ASSETS):
    return ws_resolution_verdict(push.get("winning_asset_id"), clob, legs, assets)


def test_specimen_over_label_grades_the_over_leg():
    """BOS@NYY O/U 3.5 (market 63530124): venue paid Over 1/0, label "Over".
    The old writer stored both legs lost; the token names leg 101."""
    assert _verdict(_push(), _clob(True, False, 1, 0)) == (WS_RESOLUTION_WINNER, 101)


def test_second_token_names_the_second_leg_whatever_its_name():
    """A named side (`{condition}_side1`, "Aidan Kim") is graded by its token —
    the label and the leg's suffix are never consulted."""
    v = _verdict(_push(_UNDER, "Aidan Kim"), _clob(False, True, 0, 1))
    assert v == (WS_RESOLUTION_WINNER, 102)


def test_label_is_never_read():
    """A label contradicting the token changes nothing: the token decides."""
    assert _verdict(_push(_OVER, "No"), _clob(True, False, 1, 0)) == (
        WS_RESOLUTION_WINNER,
        101,
    )


def test_specimen_void_is_a_void_not_two_losers():
    """Kozlov v Kim (15320860, market 62715379): closed, both tokens
    `winner: false` at 0.5. Stored before as two `clob_authoritative` losers."""
    assert _verdict(_push(None, ""), _clob(False, False, 0.5, 0.5)) == (
        WS_RESOLUTION_VOID,
        None,
    )


@pytest.mark.parametrize(
    "clob",
    [
        None,                                        # CLOB unreachable / 404
        {"closed": True},                            # no tokens
        _clob(False, False, 1, 0),                   # closed, winner not flipped yet
        _clob(False, False, 0.5, 0.5, closed=False),  # not closed: no void yet
        _clob(False, False, 0.5, 0.49),              # not the void payout
        _clob(True, True, 1, 1),                     # two winners
    ],
)
def test_anything_short_of_a_confirmed_result_is_unconfirmed(clob):
    assert _verdict(_push(), clob) == (WS_RESOLUTION_UNCONFIRMED, None)


def test_push_token_disagreeing_with_clob_is_unconfirmed():
    assert _verdict(_push(_UNDER), _clob(True, False, 1, 0)) == (
        WS_RESOLUTION_UNCONFIRMED,
        None,
    )


def test_push_without_a_token_takes_the_clob_winner():
    """`winning_asset_id` is optional in the venue schema; the CLOB still names it."""
    assert _verdict(_push(None), _clob(True, False, 1, 0)) == (WS_RESOLUTION_WINNER, 101)


def test_winning_token_that_is_not_a_leg_of_this_market_is_unconfirmed():
    """A token mapped to another market's leg (a mirror) never grades this one."""
    assert _verdict(_push(), _clob(True, False, 1, 0), legs=[102, 103]) == (
        WS_RESOLUTION_UNCONFIRMED,
        None,
    )
    assert _verdict(_push(), _clob(True, False, 1, 0), assets={_UNDER: 102}) == (
        WS_RESOLUTION_UNCONFIRMED,
        None,
    )


def _outcome_writes(captured):
    return [
        s for s in captured
        if "futures_outcomes" in str(s) and "is_winner" in str(s)
        and not str(s).strip().upper().startswith("SELECT")
    ]


@pytest.mark.asyncio
async def test_specimen_end_to_end_over_leg_is_the_winner():
    """Push + CLOB → verdict → write: the Over leg is True, Under False."""
    session, captured = _make_session([_Row(101, None), _Row(102, None)])
    verdict = _verdict(_push(), _clob(True, False, 1, 0))
    written = await _apply_ws_resolution(
        session, market_id=63530124,
        outcomes=[(101, _COND + "_yes"), (102, _COND + "_no")],
        verdict=verdict,
    )
    assert written == 2
    graded = {}
    for stmt in _outcome_writes(captured):
        params = stmt.compile().params
        graded[params["id_1"]] = params["is_winner"]
        assert params["resolution_source"] == "clob_authoritative"
    assert graded == {101: True, 102: False}


@pytest.mark.asyncio
async def test_void_writes_the_venue_void_and_grades_nothing():
    from app.tasks.kalshi_resolution_sweep import VOID_UPDATE_SQL

    session, captured = _make_session([_Row(101, None), _Row(102, None)])
    written = await _apply_ws_resolution(
        session, market_id=62715379,
        outcomes=[(101, _COND + "_yes"), (102, _COND + "_no")],
        verdict=(WS_RESOLUTION_VOID, None),
    )
    assert written == 0
    assert _outcome_writes(captured) == []
    texts = [str(s) for s in captured]
    assert any(t == VOID_UPDATE_SQL for t in texts), texts
    assert any("futures_markets" in t and "status" in t for t in texts)
    assert all("calibration_probability" not in t for t in texts)


@pytest.mark.asyncio
async def test_unconfirmed_resolves_the_market_and_grades_nothing():
    session, captured = _make_session([_Row(101, None), _Row(102, None)])
    written = await _apply_ws_resolution(
        session, market_id=10,
        outcomes=[(101, _COND + "_yes"), (102, _COND + "_no")],
        verdict=(WS_RESOLUTION_UNCONFIRMED, None),
    )
    assert written == 0
    assert _outcome_writes(captured) == []
    assert any("futures_markets" in str(s) and "status" in str(s) for s in captured)
