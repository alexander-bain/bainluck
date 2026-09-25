"""#8403 — a named two-sided game's CLOB tokens land on their own team's leg.

Production specimen: market 62084794 "Lukko Rauma vs. Tappara Tampere". Gamma
serves ``outcomes ["Lukko Rauma", "Tappara Tampere"]`` with ``clobTokenIds
[7382…, 5952…]``. Our legs are ``{condition}`` = Lukko (id 234499671) and
``{condition}_side1`` = Tappara (id 234499670): the ``_side1`` leg is OLDER. Q489
zipped the tokens onto the legs in id order, so Lukko's book streamed onto
Tappara's row and Tappara's onto Lukko's, and the page's headline flipped
between the two teams' prices (59% → 39% → 55% → 39% held open at 390 px).
21 of 67 live-or-upcoming two-sided markets had this shape on 2026-09-24.

Drives the REAL consumer with only the socket and the slate faked, the harness
``test_poly_ws_asset_outcome_map_q489.py`` established.
"""

import asyncio
import json

import pytest
import websockets
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update

import app.tasks.live_blend_refresh as blend_mod
import app.tasks.polymarket_ws as poly_task
from app.tasks.polymarket_ws import legs_in_token_order

CONDITION = "0x7cc1ae744afa"
LUKKO_TOKEN = "7382"  # Gamma token 0 → outcomes[0] "Lukko Rauma"
TAPPARA_TOKEN = "5952"  # Gamma token 1 → outcomes[1] "Tappara Tampere"
LUKKO_LEG = 234499671  # bare condition id — the NEWER row
TAPPARA_LEG = 234499670  # `_side1` — the OLDER row
MARKET_ID = 62084794
EVENT_ID = 15317914


def _slate(legs):
    """Three queries in the consumer's order; `legs` is ORDER BY outcome_id."""
    return [
        [(oid, MARKET_ID, ext, CONDITION, EVENT_ID) for oid, ext in legs],
        [(MARKET_ID, CONDITION, {"clob_token_ids": [LUKKO_TOKEN, TAPPARA_TOKEN]})],
        [(oid, MARKET_ID, ext) for oid, ext in legs],
    ]


SPECIMEN_LEGS = [(TAPPARA_LEG, f"{CONDITION}_side1"), (LUKKO_LEG, CONDITION)]


class _Socket:
    def __init__(self, frames):
        self._frames = list(frames)

    async def send(self, _payload):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._frames:
            return self._frames.pop(0)
        await asyncio.sleep(3600)
        raise StopAsyncIteration  # pragma: no cover


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)
        self.rowcount = len(self._rows)

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, batches, writes):
        self._batches = batches
        self._writes = writes

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            params = stmt.compile(dialect=postgresql.dialect()).params
            if (
                stmt.table.name == "futures_outcomes"
                and "current_probability" in params
            ):
                self._writes.append((params["id_1"], params["current_probability"]))
            return _Result([])
        return _Result(self._batches.pop(0) if self._batches else [])


class _NoopRefresher:
    def __init__(self, *_a, **_kw):
        pass

    async def refresh(self, event_ids):
        return None

    async def refresh_pending(self):
        # #837 tail: the quiet-flush path; a fake never defers a stamp.
        return None


async def _run(monkeypatch, legs, frames):
    import app.tasks.base as task_base

    writes = []
    batches = _slate(legs)

    def _connect(*_a, **_kw):
        class _Ctx:
            async def __aenter__(self_inner):
                return _Socket(frames)

            async def __aexit__(self_inner, *_exc):
                return False

        return _Ctx()

    class _SessCtx:
        async def __aenter__(self):
            return _Session(batches, writes)

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(websockets, "connect", _connect)
    monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _SessCtx())
    monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.05)
    monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _NoopRefresher)
    stats = await poly_task._run_polymarket_ws_consumer()
    return writes, stats


def _book(token, bid, ask):
    return json.dumps(
        {
            "event_type": "best_bid_ask",
            "asset_id": token,
            "best_bid": bid,
            "best_ask": ask,
        }
    )


def _trade(token, price):
    return json.dumps(
        {"event_type": "last_trade_price", "asset_id": token, "price": price}
    )


# ── the specimen, through the real consumer ─────────────────────────────────


class TestTheOlderSide1LegGetsItsOwnToken:
    async def test_each_teams_book_lands_on_its_own_leg(self, monkeypatch):
        """THE REGRESSION. Pre-fix: Lukko's 0.46 book wrote Tappara's leg and
        Tappara's 0.54 wrote Lukko's — the flip on the page."""
        writes, stats = await _run(
            monkeypatch,
            SPECIMEN_LEGS,
            [_book(LUKKO_TOKEN, "0.42", "0.50"), _book(TAPPARA_TOKEN, "0.50", "0.58")],
        )
        assert dict(writes) == {
            LUKKO_LEG: pytest.approx(0.46),
            TAPPARA_LEG: pytest.approx(0.54),
        }, writes
        assert stats["assets_mapped"] == 2, stats

    async def test_a_trade_follows_the_same_pairing(self, monkeypatch):
        writes, _ = await _run(
            monkeypatch, SPECIMEN_LEGS, [_trade(TAPPARA_TOKEN, "0.55")]
        )
        assert writes == [(TAPPARA_LEG, pytest.approx(0.55))], writes

    async def test_the_usual_order_is_unchanged(self, monkeypatch):
        """Control: bare leg OLDER (46 of the 67). Same answer as before."""
        legs = [(TAPPARA_LEG - 10, CONDITION), (TAPPARA_LEG, f"{CONDITION}_side1")]
        writes, _ = await _run(
            monkeypatch,
            legs,
            [_book(LUKKO_TOKEN, "0.42", "0.50"), _book(TAPPARA_TOKEN, "0.50", "0.58")],
        )
        assert dict(writes) == {
            TAPPARA_LEG - 10: pytest.approx(0.46),
            TAPPARA_LEG: pytest.approx(0.54),
        }, writes


# ── the helper ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "pairs, expected",
    [
        # side1 older → reordered bare-first
        ([(2, "0xa_side1"), (3, "0xa")], [(3, "0xa"), (2, "0xa_side1")]),
        # already bare-first → unchanged
        ([(2, "0xa"), (3, "0xa_side1")], [(2, "0xa"), (3, "0xa_side1")]),
        # Yes/No binary with No older → Yes first
        ([(5, "0xb_no"), (6, "0xb_yes")], [(6, "0xb_yes"), (5, "0xb_no")]),
        ([(5, "0xb_yes"), (6, "0xb_no")], [(5, "0xb_yes"), (6, "0xb_no")]),
    ],
)
def test_legs_are_ordered_by_the_token_their_suffix_names(pairs, expected):
    assert legs_in_token_order(pairs) == expected


@pytest.mark.parametrize(
    "pairs",
    [
        [(2, "0xa_over"), (3, "0xa_under")],  # suffix not named → untouched
        [(2, "0xa_side1"), (3, "0xa_no")],  # two second-token legs → untouched
        [(2, "0xa"), (3, "0xb")],  # two first-token legs → untouched
        [(4, "0xa_side1"), (3, "0xa"), (5, "0xa_yes")],  # three legs → untouched
        [(2, "0xa_side1")],
        [(2, "0xa_side1"), (3, "")],  # a blank id is not a bare condition id
        [],
    ],
)
def test_any_other_shape_keeps_the_callers_order(pairs):
    assert legs_in_token_order(pairs) == pairs
