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


# ── #9418 after-check: CLOB lags the push by minutes; Gamma does not ──────────
#
# Production 2026-10-01 05:3x–06:0xZ, after #9995 went live: 16 of 16 socket
# resolutions read `unconfirmed` (0 CLOB read failures). Gamma had closed each
# market and recorded `umaResolutionStatus: "resolved"` with 0/1 prices ~50 s
# BEFORE the push (e.g. 0x3d779007… Chan-Yeong Oh v Kai-i Wang: closed
# 05:56:04Z, Gamma updated 05:56:13Z, push 05:57:03Z), while CLOB `/markets`
# still read `closed: false`, no winner, five minutes later. Gamma's
# `outcomes`/`outcomePrices`/`clobTokenIds` are index-aligned with CLOB's
# token order (read on the same specimen).

from app.tasks.polymarket_ws import (  # noqa: E402
    gamma_resolution_verdict,
    settle_with_rechecks,
)


def _gamma(prices, *, closed=True, uma="resolved", tokens=(_OVER, _UNDER)):
    import json as _json

    return {
        "conditionId": _COND,
        "closed": closed,
        "umaResolutionStatus": uma,
        "outcomes": '["Over", "Under"]',
        "outcomePrices": _json.dumps([str(p) for p in prices]),
        "clobTokenIds": _json.dumps(list(tokens)),
    }


def _gverdict(push, gamma, legs=_LEGS, assets=_ASSETS):
    return gamma_resolution_verdict(push.get("winning_asset_id"), gamma, legs, assets)


def test_gamma_resolved_record_grades_the_winning_token():
    assert _gverdict(_push(), _gamma([1, 0])) == (WS_RESOLUTION_WINNER, 101)
    assert _gverdict(_push(_UNDER, "Under"), _gamma([0, 1])) == (WS_RESOLUTION_WINNER, 102)


def test_gamma_accepts_list_fields_as_well_as_json_strings():
    g = _gamma([1, 0])
    g["outcomePrices"], g["clobTokenIds"] = ["1", "0"], [_OVER, _UNDER]
    assert _gverdict(_push(), g) == (WS_RESOLUTION_WINNER, 101)


def test_gamma_void_is_a_void():
    assert _gverdict(_push(None, ""), _gamma([0.5, 0.5])) == (WS_RESOLUTION_VOID, None)


def test_gamma_label_is_never_read():
    assert _gverdict(_push(_OVER, "Under"), _gamma([1, 0])) == (WS_RESOLUTION_WINNER, 101)


@pytest.mark.parametrize(
    "gamma",
    [
        None,
        _gamma([1, 0], closed=False),             # still trading
        _gamma([1, 0], uma="proposed"),           # UMA not final
        _gamma([1, 0], uma=None),
        _gamma([0.9995, 0.0005]),                 # a price, not a payout
        _gamma([1, 1]),                           # two winners
        _gamma([1, 0.5]),                         # winner beside a non-zero
        _gamma([0, 0]),                           # no leg paid
        _gamma([0.7, 0]),                         # a top price is not a payout
        _gamma([0.5, 0.49]),                      # not the void payout
        _gamma([1, 0], tokens=(_OVER,)),          # misaligned lists
        _gamma([1], tokens=(_OVER,)),             # one-legged
    ],
)
def test_gamma_anything_short_of_a_settled_payout_is_unconfirmed(gamma):
    assert _gverdict(_push(), gamma) == (WS_RESOLUTION_UNCONFIRMED, None)


def test_gamma_winner_disagreeing_with_the_push_token_is_unconfirmed():
    assert _gverdict(_push(_UNDER), _gamma([1, 0])) == (WS_RESOLUTION_UNCONFIRMED, None)


def test_gamma_winner_that_is_not_a_leg_of_this_market_is_unconfirmed():
    assert _gverdict(_push(), _gamma([1, 0]), legs=[102]) == (WS_RESOLUTION_UNCONFIRMED, None)
    assert _gverdict(_push(), _gamma([1, 0]), assets={_UNDER: 102}) == (
        WS_RESOLUTION_UNCONFIRMED,
        None,
    )


def test_gamma_index_is_the_token_not_our_row_order():
    """Prices [0, 1] name the SECOND token; that token's leg wins whatever id it has."""
    assert _gverdict(_push(None), _gamma([0, 1]), assets={_OVER: 202, _UNDER: 201},
                     legs=[201, 202]) == (WS_RESOLUTION_WINNER, 201)


_UNC = (WS_RESOLUTION_UNCONFIRMED, None)
_WIN = (WS_RESOLUTION_WINNER, 101)


async def _settle(answers, delays=(10.0, 30.0)):
    answers = list(answers)
    asked, written, slept = [], [], []

    async def ask():
        asked.append(1)
        return answers.pop(0)

    async def write(v):
        written.append(v)

    async def sleep(d):
        slept.append(d)

    result = await settle_with_rechecks(ask, write, delays=delays, sleep=sleep)
    return result, written, slept, len(asked)


async def test_a_decided_first_answer_is_written_once_and_never_re_asked():
    result, written, slept, asked = await _settle([_WIN])
    assert result == (_WIN, False)
    assert written == [_WIN] and slept == [] and asked == 1


async def test_an_unconfirmed_first_answer_is_written_then_graded_on_a_re_ask():
    """The market reads settled at once; the grade follows when the venue confirms."""
    result, written, slept, asked = await _settle([_UNC, _UNC, _WIN])
    assert result == (_WIN, True)
    assert written == [_UNC, _WIN]
    assert slept == [10.0, 30.0] and asked == 3


async def test_a_venue_that_never_confirms_stays_unconfirmed_after_the_last_re_ask():
    result, written, slept, asked = await _settle([_UNC, _UNC, _UNC])
    assert result == (_UNC, False)
    assert written == [_UNC]
    assert asked == 3


async def test_a_late_void_is_written_as_a_void():
    void = (WS_RESOLUTION_VOID, None)
    result, written, _slept, _asked = await _settle([_UNC, void])
    assert result == (void, True) and written == [_UNC, void]


def test_the_re_asks_finish_inside_one_socket_run():
    """A recycle cancels outstanding settles; the waits must fit a run."""
    from app.tasks.kalshi_ws import SUBSCRIPTION_REFRESH_SECONDS
    from app.tasks.polymarket_ws import RESOLUTION_RECHECK_DELAYS_S

    assert sum(RESOLUTION_RECHECK_DELAYS_S) < SUBSCRIPTION_REFRESH_SECONDS / 2


async def test_the_gamma_read_asks_for_closed_markets_by_condition():
    """`/markets/{id}` 422s on a condition id and the list form's default filter
    is closed=false — both would read a settled market as absent."""
    import httpx

    from app.services.polymarket_api import PolymarketAPIService

    seen = {}

    def handler(request):
        seen["path"], seen["params"] = request.url.path, dict(request.url.params)
        return httpx.Response(200, json=[{"conditionId": "0xother"}, {"conditionId": _COND, "closed": True}])

    svc = PolymarketAPIService()
    await svc.gamma_client.aclose()
    svc.gamma_client = httpx.AsyncClient(
        base_url=svc.GAMMA_BASE_URL, transport=httpx.MockTransport(handler)
    )
    try:
        row = await svc.get_closed_gamma_market_raw(_COND)
    finally:
        await svc.close()
    assert seen == {"path": "/markets", "params": {"condition_ids": _COND, "closed": "true"}}
    assert row == {"conditionId": _COND, "closed": True}


def test_gamma_prices_and_tokens_of_different_lengths_are_unconfirmed():
    """Index alignment is the whole proof of WHICH token won; a list that does
    not line up proves nothing, even when a position happens to read 1."""
    assert _gverdict(_push(None), _gamma([0, 1, 0])) == (WS_RESOLUTION_UNCONFIRMED, None)
