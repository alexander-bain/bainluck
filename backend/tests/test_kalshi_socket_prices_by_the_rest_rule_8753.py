"""#8753 — the Kalshi live socket prices a leg by the REST writer's rule.

WHAT A READER SAW. ``/events/15315945`` (Northwestern @ Indiana, live, 2026-09-26
00:40Z) drew *First Team to Score a TD* as

    Indiana scores first TD        96%    stored 0.960, book 0.59 / 0.95
    Northwestern scores first TD   42%    stored 0.420, book 0.04 / 0.46
    No team scores a TD             1%    stored 0.010, book 0.00 / 0.01

— three exclusive outcomes summing to 139%, Indiana printed ABOVE its own ask.

WHY. ``handle_ticker`` stored the last trade whenever there was one. The REST
writer (``app.tasks.kalshi._kalshi_yes_probability``) prefers a tight book's
midpoint and takes a trade only when the live book does not refute it (#5121);
on that book it stores 0.77. The socket ticks faster than the poll, so the
socket's number was the one on the page. The fix calls the REST rule rather than
re-spelling it, and writes the tick's book beside the price, so the stored row is
one instant's quote instead of a socket price beside a two-minute-old REST book.

HOW. The real consumer is driven over one real tick (the harness of
``test_a_settled_leg_takes_no_live_price_5411``), the price UPDATE it emits is
captured, and that statement is EXECUTED against a real SQLite row — so the
stored value is read back from an engine, not inferred from a parameter dict.
"""

import json

import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.sql.dml import Update

import app.services.kalshi_ws as kalshi_svc
import app.tasks.kalshi_ws as kalshi_task
import app.tasks.live_blend_refresh as blend_mod
from app.models.models import FuturesOutcome
from app.tasks.kalshi import _kalshi_yes_probability
from app.utils.kalshi_empty_book import book_refutes_price
from tests.test_a_settled_leg_takes_no_live_price_5411 import (
    _CapturingSession,
    _Frames,
    _NoopRefresher,
)

MARKET_ID = 61817501
EVENT_ID = 15315945
MARKET_EXT = "KXNCAAFFIRSTTDTEAM-26SEP25NWIND"
TICKER = f"{MARKET_EXT}-IND"
OUTCOME_ID = 8753

#: What the row held before the tick — the poll's last write. Distinct from
#: every value a tick below carries, so "the book was written" and "the book was
#: left alone" read differently off the engine.
SEEDED_PRICE = 0.5
SEEDED_BID = 0.30
SEEDED_ASK = 0.70

SLATE = [
    [(MARKET_EXT, MARKET_ID, EVENT_ID)],
    [(TICKER, MARKET_ID, OUTCOME_ID)],
]


def _tick(**fields) -> str:
    return json.dumps({
        "type": "ticker",
        "msg": {"market_ticker": TICKER, **fields},
    })


async def _price_updates(monkeypatch, frame) -> list[Update]:
    """Run the REAL consumer over one tick; return the price UPDATEs it emitted."""
    import websockets

    import app.tasks.base as task_base

    captured: list[Update] = []
    batches = [list(b) for b in SLATE]

    def _connect(*_a, **_kw):
        class _Ctx:
            async def __aenter__(self_inner):
                return _Frames([frame])

            async def __aexit__(self_inner, *_exc):
                return False

        return _Ctx()

    class _SessionCtx:
        async def __aenter__(self):
            return _CapturingSession(batches, captured, 1)

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-secret")
    monkeypatch.setattr(kalshi_svc, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(kalshi_svc, "_sign_ws_request", lambda _k, _i: {})
    monkeypatch.setattr(kalshi_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.5)
    monkeypatch.setattr(kalshi_task, "PRICE_FLUSH_SECONDS", 0.02)
    monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _NoopRefresher)
    monkeypatch.setattr(websockets, "connect", _connect)
    monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _SessionCtx())

    await kalshi_task._run_kalshi_ws_consumer()
    return captured


def _stored_after(stmt) -> tuple[float, float, float]:
    """Execute the captured UPDATE on one seeded SQLite row; read the row back."""
    engine = create_engine("sqlite://")
    table = FuturesOutcome.__table__
    table.create(engine)
    with engine.begin() as conn:
        conn.execute(insert(table).values(
            id=OUTCOME_ID,
            market_id=MARKET_ID,
            external_id=TICKER,
            name="Indiana scores first TD",
            current_probability=SEEDED_PRICE,
            current_yes_bid=SEEDED_BID,
            current_yes_ask=SEEDED_ASK,
        ))
        assert conn.execute(stmt).rowcount == 1
        row = conn.execute(
            select(
                table.c.current_probability,
                table.c.current_yes_bid,
                table.c.current_yes_ask,
            ).where(table.c.id == OUTCOME_ID)
        ).one()
    return tuple(float(v) for v in row)


async def _stored_for(monkeypatch, frame) -> tuple[float, float, float]:
    updates = await _price_updates(monkeypatch, frame)
    assert len(updates) == 1, (
        f"expected exactly one price UPDATE, captured {len(updates)} — the harness "
        "is not driving the flush this file is about"
    )
    return _stored_after(updates[0])


# ------------------------------------------------------------- the ship ----


@pytest.mark.asyncio
async def test_the_specimen_tick_stores_the_midpoint_not_the_trade_above_its_ask(
    monkeypatch,
):
    price, bid, ask = await _stored_for(
        monkeypatch,
        _tick(price_dollars="0.9600", yes_bid_dollars="0.5900",
              yes_ask_dollars="0.9500"),
    )

    assert price != pytest.approx(0.96), (
        "the socket stored Indiana's 0.96 trade above its own 0.95 ask again — "
        "the card prints 'Indiana scores first TD 96%' (#8753)"
    )
    assert price == pytest.approx(0.77), (
        "a 0.59/0.95 book is tight (< 0.50 wide), so the REST rule stores its "
        f"midpoint; the socket stored {price}"
    )
    assert not book_refutes_price(bid, ask, price), (
        "the stored row's own book prices out its own stored price — the exact "
        "shape #6532's read-side arm withholds"
    )


@pytest.mark.asyncio
async def test_the_tick_writes_its_own_book_beside_the_price(monkeypatch):
    _price, bid, ask = await _stored_for(
        monkeypatch,
        _tick(price_dollars="0.9600", yes_bid_dollars="0.5900",
              yes_ask_dollars="0.9500"),
    )

    assert (bid, ask) == (pytest.approx(0.59), pytest.approx(0.95)), (
        "the price came from the tick's book but the row still carries the poll's "
        f"book ({bid}/{ask}); every read-side book rule then compares one instant's "
        "price with another instant's quote"
    )


# ------------------------------------------------ the rule, not a new one ----


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bid, ask, last",
    [
        # Wide book, a trade INSIDE it: trade evidence beats a wide book (rule 2).
        ("0.1000", "0.7000", "0.4000"),
        # Tight book, no trade: midpoint (rule 1).
        ("0.4000", "0.4400", None),
        # Wide one-sided longshot, trade ABOVE the ask: refuted, ask cap (rule 3).
        ("0.0000", "0.0900", "0.5200"),
    ],
)
async def test_the_socket_stores_exactly_what_the_rest_writer_would(
    monkeypatch, bid, ask, last
):
    fields = {"yes_bid_dollars": bid, "yes_ask_dollars": ask}
    if last is not None:
        fields["price_dollars"] = last
    price, _bid, _ask = await _stored_for(monkeypatch, _tick(**fields))

    expected = _kalshi_yes_probability(
        float(bid), float(ask), float(last) if last is not None else None
    )
    assert price == pytest.approx(expected), (
        f"book {bid}/{ask} last {last}: REST stores {expected}, the socket stored "
        f"{price} — two price policies for one venue"
    )


@pytest.mark.asyncio
async def test_a_wide_book_with_a_refuted_trade_writes_nothing(monkeypatch):
    # 0.02/0.80 is wide, the 0.96 trade sits above the ask, and the ask is not a
    # longshot: the REST rule returns None — no price exists, so none is written
    # (the old socket wrote 0.96).
    assert _kalshi_yes_probability(0.02, 0.80, 0.96) is None
    updates = await _price_updates(
        monkeypatch,
        _tick(price_dollars="0.9600", yes_bid_dollars="0.0200",
              yes_ask_dollars="0.8000"),
    )
    assert updates == [], "a book with no price in it was written as one"


@pytest.mark.asyncio
async def test_a_tick_without_a_book_keeps_the_trade_and_leaves_the_book_alone(
    monkeypatch,
):
    # Control for the book write: a trade-only tick has no quote to store, so the
    # poll's book must survive untouched rather than be nulled.
    price, bid, ask = await _stored_for(monkeypatch, _tick(price_dollars="0.3300"))

    assert price == pytest.approx(0.33)
    assert (bid, ask) == (pytest.approx(SEEDED_BID), pytest.approx(SEEDED_ASK)), (
        f"a tick that carried no book overwrote the stored one: {bid}/{ask}"
    )
