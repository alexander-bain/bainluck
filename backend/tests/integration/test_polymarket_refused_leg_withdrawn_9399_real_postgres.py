"""#9399 through the REAL hourly-poll writer, against real Postgres.

The unit file (`tests/test_polymarket_refused_leg_withdrawn_9399.py`) answers the
withdrawal's SELECT from a fake. This one runs the SQL: two passes of
``_process_event_batch`` over the Hurricane Nolo field (Gamma event 1075583).

    pass 1 (10:50Z-shaped)  Category 5 quotes a tight book around 0.92 -> stored 0.92
    pass 2 (16:0xZ, verbatim) Category 5 outcomePrices 0.205 on 0.09/0.32, last 0.92
                              -> both prices refused; before #9399 the row kept 0.92

After pass 2 the 0.92 must be gone, Category 4 must carry this pass's 0.72, and a
leg whose stored price its current book does NOT refute must keep it.
"""

from __future__ import annotations

import os

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #9399 poll writer against real "
            "Postgres (CI job `search-recall` provides one)"
        ),
    ),
]

EVENT_ID = "1075583"
CAT3, CAT4, CAT5 = "0xnolo_cat3", "0xnolo_cat4", "0xnolo_cat5"


@pytest.fixture
async def engine(monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    import app.tasks.base as task_base
    from app.services.database import Base

    eng = create_async_engine(DB_URL)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(task_base, "DATABASE_URL", DB_URL)
    yield eng
    await eng.dispose()


def _leg(cid, n, *, prices, bid, ask, last):
    from app.services.polymarket_api import PolymarketMarket

    return PolymarketMarket(
        condition_id=cid,
        question=f"Will Hurricane Nolo reach Category {n}?",
        group_item_title=f"Category {n}",
        outcomes=["Yes", "No"],
        outcome_prices=prices,
        best_bid=bid,
        best_ask=ask,
        last_trade_price=last,
        volume_24h=5_000.0,
    )


def _nolo(cat5, cat3=None):
    from app.services.polymarket_api import PolymarketEvent

    return PolymarketEvent(
        id=EVENT_ID,
        title="How strong will Nolo be?",
        neg_risk=True,
        markets=[
            _leg(CAT4, 4, prices=[0.785, 0.215], bid=0.65, ask=0.92, last=0.72),
            cat5,
            cat3 or _leg(CAT3, 3, prices=[0.025, 0.975], bid=0.02, ask=0.03, last=0.025),
        ],
    )


async def _poll(event):
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.tasks.polymarket import _process_event_batch
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american

    class _Counting(dict):
        def __missing__(self, key):
            return 0

    stats = _Counting(errors=[], by_category={})
    await _process_event_batch(
        [event], stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
        pg_insert, probability_to_american, compute_market_tier,
    )
    assert not stats["errors"], stats["errors"]
    return stats


async def _stored(engine) -> dict:
    from sqlalchemy import text

    async with engine.connect() as conn:
        rows = (
            await conn.execute(text(
                "SELECT o.external_id, o.current_probability::float, "
                "       o.current_american_odds "
                "  FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id "
                " WHERE m.source = 'polymarket' AND m.external_id = :eid"
            ), {"eid": EVENT_ID})
        ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


async def test_the_refuted_092_is_withdrawn_and_the_field_names_the_venues_favorite(engine):
    tight_092 = _leg(CAT5, 5, prices=[0.92, 0.08], bid=0.91, ask=0.93, last=0.92)
    await _poll(_nolo(tight_092))
    before = await _stored(engine)
    assert before[CAT5][0] == pytest.approx(0.92), "pass 1 must store the specimen's 0.92"

    refused = _leg(CAT5, 5, prices=[0.205, 0.795], bid=0.09, ask=0.32, last=0.92)
    stats = await _poll(_nolo(refused))
    after = await _stored(engine)

    assert stats["legs_withdrawn_book_refuted"] == 1
    assert after[CAT5] == (None, None)
    assert after[CAT4][0] == pytest.approx(0.72)
    priced = {k: v[0] for k, v in after.items() if v[0] is not None}
    assert max(priced, key=priced.get) == CAT4


async def test_a_refused_leg_whose_stored_price_the_book_supports_keeps_it(engine):
    """Control: same refusal shape, but the stored 0.20 sits inside 0.09/0.32."""
    inside = _leg(CAT5, 5, prices=[0.20, 0.80], bid=0.19, ask=0.21, last=0.20)
    await _poll(_nolo(inside))
    refused = _leg(CAT5, 5, prices=[0.205, 0.795], bid=0.09, ask=0.32, last=0.92)
    stats = await _poll(_nolo(refused))

    assert stats["legs_withdrawn_book_refuted"] == 0
    assert (await _stored(engine))[CAT5][0] == pytest.approx(0.20)


async def test_a_graded_leg_is_never_withdrawn(engine):
    from sqlalchemy import text

    tight_092 = _leg(CAT5, 5, prices=[0.92, 0.08], bid=0.91, ask=0.93, last=0.92)
    await _poll(_nolo(tight_092))
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE futures_outcomes SET resolution_source = 'api_settlement' "
            " WHERE external_id = :cid"
        ), {"cid": CAT5})
    refused = _leg(CAT5, 5, prices=[0.205, 0.795], bid=0.09, ask=0.32, last=0.92)
    stats = await _poll(_nolo(refused))

    assert stats["legs_withdrawn_book_refuted"] == 0
    assert (await _stored(engine))[CAT5][0] == pytest.approx(0.92)


# ---------------------------------------------------------------------------
# #10298 — the same writer, reached through the non-negRisk GAME branch (C1 + C2)
# ---------------------------------------------------------------------------
#
# Lions–Packers (Polymarket game market 61040985) printed "Packers 53%" over a
# 0.15/0.52 book. Two passes of the real poll over a game event: pass 1 stores a
# moneyline, pass 2 serves the specimen book. Production writer of 0.53: UNKNOWN —
# this is the admitted failure shape, not a claim about which writer stored it.

GAME_ID = "61040985"
ML, SPREAD = "0xlp_ml", "0xlp_spread"


def _game_leg(cid, question, *, prices, bid, ask, last, title=None):
    from app.services.polymarket_api import PolymarketMarket

    return PolymarketMarket(
        condition_id=cid,
        question=question,
        group_item_title=title,
        outcomes=["Packers", "Lions"] if title is None else ["Yes", "No"],
        outcome_prices=prices,
        best_bid=bid,
        best_ask=ask,
        last_trade_price=last,
        volume_24h=5_000.0,
    )


def _game(moneyline=None, *, spread_price=0.29):
    from app.services.polymarket_api import PolymarketEvent

    spread = _game_leg(
        SPREAD, "Spread: Packers (-5.5)", title="Spread -5.5",
        prices=[spread_price, 1 - spread_price],
        bid=spread_price - 0.01, ask=spread_price + 0.01, last=spread_price,
    )
    markets = [spread] if moneyline is None else [moneyline, spread]
    return PolymarketEvent(
        id=GAME_ID, title="Lions vs. Packers", neg_risk=False, markets=markets,
    )


def _ml(raw, bid, ask, last=None):
    return _game_leg(ML, "Lions vs. Packers", prices=[raw, round(1 - raw, 4)],
                     bid=bid, ask=ask, last=last)


async def _wrapper_rows(engine) -> dict:
    """Every leg of the WRAPPER market (external_id = the Gamma event id)."""
    from sqlalchemy import text

    async with engine.connect() as conn:
        rows = (
            await conn.execute(text(
                "SELECT o.external_id, o.current_probability::float, "
                "       o.current_american_odds, o.opening_probability::float, "
                "       o.price_changed_at, o.last_updated "
                "  FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id "
                " WHERE m.source = 'polymarket' AND m.external_id = :eid"
            ), {"eid": GAME_ID})
        ).fetchall()
    return {
        r[0]: {"p": r[1], "odds": r[2], "opening": r[3], "changed": r[4], "touched": r[5]}
        for r in rows
    }


async def _other_rows(engine) -> dict:
    """Every outcome NOT under the wrapper — the decomposed per-sub-market rows."""
    from sqlalchemy import text

    async with engine.connect() as conn:
        rows = (
            await conn.execute(text(
                "SELECT m.external_id, o.external_id, o.current_probability::float "
                "  FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id "
                " WHERE m.external_id <> :eid"
            ), {"eid": GAME_ID})
        ).fetchall()
    return {(r[0], r[1]): r[2] for r in rows}


async def test_10298_a_moneyline_its_own_book_refutes_is_withdrawn(engine):
    """(d)/(f1): stored 0.53, fresh 0.15/0.52 book, raw 0.53 → NULL on the wrapper."""
    await _poll(_game(_ml(0.53, 0.52, 0.54, last=0.53)))
    before = await _wrapper_rows(engine)
    assert before[ML]["p"] == pytest.approx(0.53), "pass 1 must store the 0.53"
    others_before = await _other_rows(engine)

    stats = await _poll(_game(_ml(0.53, 0.15, 0.52, last=0.53), spread_price=0.30))
    after = await _wrapper_rows(engine)

    assert stats["legs_withdrawn_book_refuted"] == 1
    assert (after[ML]["p"], after[ML]["odds"]) == (None, None)
    assert after[ML]["changed"] is not None
    assert after[ML]["changed"] != before[ML]["changed"]
    assert after[ML]["opening"] == before[ML]["opening"]
    assert after[ML]["touched"] == before[ML]["touched"]
    assert after[SPREAD]["p"] == pytest.approx(0.30), "the side leg keeps this pass's write"
    # identity: only the wrapper's own leg — no decomposed row was withdrawn
    others_after = await _other_rows(engine)
    assert {k for k, v in others_after.items() if v is None} <= {
        k for k, v in others_before.items() if v is None
    }


async def test_10298_a_refuted_raw_with_a_surviving_trade_is_still_withdrawn(engine):
    """(f2): last 0.40 sits inside 0.15/0.52 — it is NOT substituted."""
    await _poll(_game(_ml(0.53, 0.52, 0.54, last=0.53)))
    stats = await _poll(_game(_ml(0.53, 0.15, 0.52, last=0.40)))
    after = await _wrapper_rows(engine)
    assert stats["legs_withdrawn_book_refuted"] == 1
    assert after[ML]["p"] is None


async def test_10298_a_raw_price_inside_its_book_is_written_unchanged(engine):
    """(f3) control: 0.40 on 0.38/0.42 → written, nothing withdrawn."""
    await _poll(_game(_ml(0.41, 0.40, 0.42, last=0.41)))
    stats = await _poll(_game(_ml(0.40, 0.38, 0.42, last=0.40)))
    assert stats["legs_withdrawn_book_refuted"] == 0
    assert (await _wrapper_rows(engine))[ML]["p"] == pytest.approx(0.40)


async def test_10298_a_refused_moneyline_whose_stored_price_the_book_supports_keeps_it(engine):
    """Stored 0.40 sits inside 0.15/0.52: the raw 0.53 is refused, the 0.40 retained."""
    await _poll(_game(_ml(0.40, 0.39, 0.41, last=0.40)))
    stats = await _poll(_game(_ml(0.53, 0.15, 0.52, last=0.53)))
    assert stats["legs_withdrawn_book_refuted"] == 0
    assert (await _wrapper_rows(engine))[ML]["p"] == pytest.approx(0.40)


@pytest.mark.parametrize("column, value", [
    ("resolution_source", "'api_settlement'"),
    ("is_winner", "TRUE"),
])
async def test_10298_graded_and_crowned_moneylines_are_never_withdrawn(engine, column, value):
    from sqlalchemy import text

    await _poll(_game(_ml(0.53, 0.52, 0.54, last=0.53)))
    async with engine.begin() as conn:
        await conn.execute(text(
            f"UPDATE futures_outcomes SET {column} = {value} WHERE external_id = :cid"
        ), {"cid": ML})
    stats = await _poll(_game(_ml(0.53, 0.15, 0.52, last=0.53)))
    assert stats["legs_withdrawn_book_refuted"] == 0
    assert (await _wrapper_rows(engine))[ML]["p"] == pytest.approx(0.53)


async def test_10298_a_truncated_payload_withdraws_nothing(engine):
    """Pass 2 omits the moneyline entirely: nothing is inferred from its absence."""
    await _poll(_game(_ml(0.53, 0.52, 0.54, last=0.53)))
    stats = await _poll(_game(None))
    assert stats["legs_withdrawn_book_refuted"] == 0
    assert (await _wrapper_rows(engine))[ML]["p"] == pytest.approx(0.53)


async def test_10298_a_price_changed_underfoot_is_not_withdrawn(engine):
    """CAS: another writer stores 0.20 between the withdrawal's read and its write."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.tasks.polymarket import _refused_leg_books, _withdraw_book_refuted_legs

    await _poll(_game(_ml(0.53, 0.52, 0.54, last=0.53)))
    async with engine.connect() as conn:
        market_id = (await conn.execute(text(
            "SELECT id FROM futures_markets WHERE source='polymarket' AND external_id=:e"
        ), {"e": GAME_ID})).scalar_one()

    books = _refused_leg_books(_game(_ml(0.53, 0.15, 0.52, last=0.53)))
    assert books == {ML: (0.15, 0.52)}

    class _Underfoot:
        """Commits a competing write right after the withdrawal's SELECT."""

        def __init__(self, session):
            self.session, self.fired = session, False

        async def execute(self, statement, *a, **kw):
            result = await self.session.execute(statement, *a, **kw)
            if not self.fired:
                self.fired = True
                async with engine.begin() as other:
                    await other.execute(text(
                        "UPDATE futures_outcomes SET current_probability = 0.20 "
                        " WHERE market_id = :m AND external_id = :c"
                    ), {"m": market_id, "c": ML})
            return result

    async with AsyncSession(engine) as session:
        n = await _withdraw_book_refuted_legs(_Underfoot(session), market_id, books)
        await session.commit()
    assert n == 0
    assert (await _wrapper_rows(engine))[ML]["p"] == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# #10298 — the HOURLY REFRESH composition (fetch → write → withdraw → twins)
# ---------------------------------------------------------------------------
#
# The independent review's finding: the poll above skips the refuted 0.53, but
# `futures_price_refresh` prices the same leg through the unchanged resolver
# (0.53 over 0.15/0.52 — the wide-spread last trade), wrote it onto the parent's
# bare row and snapshotted it, and only THEN withdrew it. A supported 0.40 came
# out NULL and a 0.53 chart point survived. These run the real task: only the
# venue is faked, so the selector, the write/withdraw order, the twin pass and the
# transaction all belong to `_refresh_stale_futures_prices`.

_SPREAD_BOOK = dict(spread_price=0.30)


async def _refresh(engine, monkeypatch, event, *, registered):
    """One real refresh pass over `event`, selecting exactly `registered`."""
    import contextlib

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.tasks import futures_price_refresh as fpr
    from app.utils.category_served_markets import CategoryServed
    from app.utils.feed_served_markets import SERVED_UNAVAILABLE, ServedSignal

    async with engine.begin() as conn:  # age every snapshot out of the window
        await conn.execute(text(
            "UPDATE futures_odds_snapshots SET captured_at = captured_at - interval '2 days'"
        ))

    @contextlib.asynccontextmanager
    async def _session(**_kw):
        async with AsyncSession(engine, expire_on_commit=False) as s:
            yield s

    class _Gamma:
        async def get_events_by_ids(self, ids):
            return [event] if str(event.id) in ids else []

        def _parse_event(self, raw):
            return raw

        async def close(self):
            return None

    async def _none(*_a, **_k):
        return []

    monkeypatch.delenv("KALSHI_API_KEY", raising=False)
    monkeypatch.setattr("app.tasks.base.get_task_session", _session)
    monkeypatch.setattr(
        "app.utils.tournament_register.registered_market_ids", lambda: set(registered)
    )
    monkeypatch.setattr(
        "app.utils.feed_served_markets.served_signal",
        lambda: ServedSignal(state=SERVED_UNAVAILABLE, ids=[]),
    )
    monkeypatch.setattr(
        "app.utils.feed_served_markets.note_served_signal_healthy", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "app.utils.category_served_markets.category_served_market_ids",
        lambda *a, **k: CategoryServed(ids=[]),
    )
    for scan in ("_scan_candidates", "_scan_in_play_candidates",
                 "_scan_series_card_candidates", "_scan_threshold_label_candidates"):
        monkeypatch.setattr(fpr, scan, _none)
    monkeypatch.setattr(fpr, "_load_attempt_skips", lambda ids: set())
    monkeypatch.setattr(fpr, "_mark_attempted", lambda ids, ttl_seconds: None)
    monkeypatch.setattr(fpr, "_load_label_attempt_skips", lambda ids: set())
    monkeypatch.setattr(fpr, "_mark_label_attempted", lambda ids: None)
    monkeypatch.setattr("app.services.polymarket_api.PolymarketAPIService", _Gamma)
    stats = await fpr._refresh_stale_futures_prices()
    assert not stats["errors"], stats["errors"]
    assert stats["registered_attempted"] == len(registered), stats
    return stats


async def _legs(engine) -> dict:
    """``(market external_id, outcome external_id)`` → the columns a write moves."""
    from sqlalchemy import text

    async with engine.connect() as conn:
        rows = (
            await conn.execute(text(
                "SELECT m.id, m.external_id, o.external_id, "
                "       o.current_probability::float, o.current_yes_bid::float, "
                "       o.current_yes_ask::float, o.last_updated, o.price_changed_at, "
                "       o.opening_probability::float, "
                "       (SELECT COUNT(*) FROM futures_odds_snapshots s "
                "         WHERE s.outcome_id = o.id "
                "           AND s.captured_at > NOW() - interval '1 hour') "
                "  FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id"
            ))
        ).fetchall()
    return {
        (r[1], r[2]): {
            "market_id": r[0], "p": r[3], "bid": r[4], "ask": r[5], "touched": r[6],
            "changed": r[7], "opening": r[8], "fresh_snapshots": r[9],
        }
        for r in rows
    }


def _mid(legs, market_ext):
    return next(v["market_id"] for (m, _o), v in legs.items() if m == market_ext)


_PARENT_ML = (GAME_ID, ML)
_CHILD_ML_YES = (ML, f"{ML}_yes")
_PARENT_SPREAD = (GAME_ID, SPREAD)


async def test_10298_refresh_keeps_a_supported_040_and_writes_no_053(engine, monkeypatch):
    """Selected parent. Stored 0.40 is inside 0.15/0.52: it stays, untouched."""
    await _poll(_game(_ml(0.40, 0.39, 0.41, last=0.40)))
    before = await _legs(engine)
    stats = await _refresh(
        engine, monkeypatch, _game(_ml(0.53, 0.15, 0.52, last=0.53), **_SPREAD_BOOK),
        registered=[_mid(before, GAME_ID)],
    )
    after = await _legs(engine)

    p_before, p_after = before[_PARENT_ML], after[_PARENT_ML]
    assert p_after["p"] == pytest.approx(0.40)
    assert p_after["fresh_snapshots"] == 0, "no 0.53 chart point on the parent"
    for col in ("bid", "ask", "touched", "changed", "opening"):
        assert p_after[col] == p_before[col], col
    assert stats.get("legs_declined_parent_refused", 0) == 1
    assert stats["legs_withdrawn_book_refuted"] == 0
    # the healthy sibling on the same parent still refreshes
    assert after[_PARENT_SPREAD]["p"] == pytest.approx(0.30)
    assert after[_PARENT_SPREAD]["fresh_snapshots"] == 1
    # the decomposed child keeps its unchanged resolver contract (via the twin pass)
    from app.tasks.polymarket import _resolve_market_probability

    resolved = _resolve_market_probability(_ml(0.53, 0.15, 0.52, last=0.53))
    assert after[_CHILD_ML_YES]["p"] == pytest.approx(resolved)
    assert after[_CHILD_ML_YES]["fresh_snapshots"] == 1


async def test_10298_refresh_withdraws_a_stored_053_without_a_new_snapshot(engine, monkeypatch):
    """Selected parent. Stored 0.53 is priced out by 0.52: NULL, and no 0.53 point."""
    await _poll(_game(_ml(0.53, 0.52, 0.54, last=0.53)))
    before = await _legs(engine)
    stats = await _refresh(
        engine, monkeypatch, _game(_ml(0.53, 0.15, 0.52, last=0.53), **_SPREAD_BOOK),
        registered=[_mid(before, GAME_ID)],
    )
    after = await _legs(engine)

    assert after[_PARENT_ML]["p"] is None
    assert after[_PARENT_ML]["fresh_snapshots"] == 0
    assert after[_PARENT_ML]["touched"] == before[_PARENT_ML]["touched"]
    assert after[_PARENT_ML]["opening"] == before[_PARENT_ML]["opening"]
    assert stats.get("legs_declined_parent_refused", 0) == 1
    assert stats["legs_withdrawn_book_refuted"] == 1


@pytest.mark.parametrize("stored, withdrawn", [
    ((0.40, 0.39, 0.41), 0),   # supported by 0.15/0.52: survives untouched
    ((0.53, 0.52, 0.54), 1),   # priced out by the 0.52 ask: NULL, no new point
])
async def test_10298_a_twin_only_parent_is_withheld_like_a_selected_one(
    engine, monkeypatch, stored, withdrawn
):
    """Only the decomposed child is selected, so the twin pass alone reaches the
    parent. The bare row takes no write and no snapshot, and the same guarded
    withdrawal judges what it already stores."""
    await _poll(_game(_ml(stored[0], stored[1], stored[2], last=stored[0])))
    before = await _legs(engine)
    stats = await _refresh(
        engine, monkeypatch, _game(_ml(0.53, 0.15, 0.52, last=0.53), **_SPREAD_BOOK),
        registered=[_mid(before, ML)],
    )
    after = await _legs(engine)

    p_before, p_after = before[_PARENT_ML], after[_PARENT_ML]
    if withdrawn:
        assert p_after["p"] is None
        assert p_after["changed"] != p_before["changed"]
    else:
        assert p_after["p"] == pytest.approx(stored[0])
        assert p_after["changed"] == p_before["changed"]
    assert p_after["fresh_snapshots"] == 0
    for col in ("bid", "ask", "touched", "opening"):
        assert p_after[col] == p_before[col], col
    assert after[_CHILD_ML_YES]["fresh_snapshots"] == 1, "the selected child still prices"
    assert after[_PARENT_SPREAD]["p"] == pytest.approx(0.30)
    assert after[_PARENT_SPREAD]["fresh_snapshots"] == 1, "the healthy parent sibling refreshes"
    assert stats["legs_withdrawn_book_refuted"] == withdrawn
    assert stats.get("legs_declined_parent_refused", 0) >= 1


@pytest.mark.parametrize("column, value", [
    # An inferred grade passes the twin lookup's fence, so ONLY the guarded
    # withdrawal's `resolution_source IS NULL` exemption can save it — the arm
    # that proves the new twin wiring kept the helper's exemptions.
    ("resolution_source", "'pass2_guess'"),
    # These two the twin lookup itself fences (CONDITION_TWIN_MARKETS_SQL).
    ("resolution_source", "'api_settlement'"),
    ("is_winner", "TRUE"),
])
async def test_10298_twin_path_keeps_the_graded_and_crowned_exemptions(
    engine, monkeypatch, column, value
):
    """Graded and crowned twin parents keep their number."""
    from sqlalchemy import text

    await _poll(_game(_ml(0.53, 0.52, 0.54, last=0.53)))
    async with engine.begin() as conn:
        await conn.execute(text(
            f"UPDATE futures_outcomes SET {column} = {value} WHERE external_id = :cid"
        ), {"cid": ML})
    before = await _legs(engine)
    stats = await _refresh(
        engine, monkeypatch, _game(_ml(0.53, 0.15, 0.52, last=0.53), **_SPREAD_BOOK),
        registered=[_mid(before, ML)],
    )
    after = await _legs(engine)
    assert after[_PARENT_ML]["p"] == pytest.approx(0.53)
    assert after[_PARENT_ML]["fresh_snapshots"] == 0
    assert stats["legs_withdrawn_book_refuted"] == 0


async def test_10298_twin_path_respects_the_compare_and_set(engine, monkeypatch):
    """A writer that changes the twin parent's price between the withdrawal's
    read and its write wins: the stale read withdraws nothing."""
    from sqlalchemy import text

    from app.tasks import polymarket as pm

    await _poll(_game(_ml(0.53, 0.52, 0.54, last=0.53)))
    before = await _legs(engine)
    parent_id = _mid(before, GAME_ID)
    real = pm._withdraw_book_refuted_legs

    async def _underfoot(session, market_id, books):
        if market_id == parent_id and books:
            real_execute = session.execute
            fired = []

            async def _execute(statement, *a, **kw):
                result = await real_execute(statement, *a, **kw)
                if not fired:
                    fired.append(1)
                    async with engine.begin() as other:
                        await other.execute(text(
                            "UPDATE futures_outcomes SET current_probability = 0.20 "
                            " WHERE market_id = :m AND external_id = :c"
                        ), {"m": market_id, "c": ML})
                return result

            session.execute = _execute
            try:
                return await real(session, market_id, books)
            finally:
                del session.execute
        return await real(session, market_id, books)

    monkeypatch.setattr(pm, "_withdraw_book_refuted_legs", _underfoot)
    stats = await _refresh(
        engine, monkeypatch, _game(_ml(0.53, 0.15, 0.52, last=0.53), **_SPREAD_BOOK),
        registered=[_mid(before, ML)],
    )
    after = await _legs(engine)
    assert stats["legs_withdrawn_book_refuted"] == 0
    assert after[_PARENT_ML]["p"] == pytest.approx(0.20)


async def test_10298_strawman_without_the_tag_reproduces_the_finding(engine, monkeypatch):
    """The reviewer's recording, as a control: strip the fetch's tag and the
    supported 0.40 comes out NULL with a 0.53 snapshot left behind. Without this
    the two tests above would also pass on a rig that never reached the write."""
    from app.tasks import futures_price_refresh as fpr

    real = fpr._fetch_polymarket_prices

    async def _untagged(*a, **k):
        out, unpriced = await real(*a, **k)
        for items in out.values():
            if isinstance(items, list):
                for item in items:
                    item.pop("parent_book_refused", None)
        return out, unpriced

    await _poll(_game(_ml(0.40, 0.39, 0.41, last=0.40)))
    before = await _legs(engine)
    monkeypatch.setattr(fpr, "_fetch_polymarket_prices", _untagged)
    await _refresh(
        engine, monkeypatch, _game(_ml(0.53, 0.15, 0.52, last=0.53), **_SPREAD_BOOK),
        registered=[_mid(before, GAME_ID)],
    )
    after = await _legs(engine)
    assert after[_PARENT_ML]["p"] is None
    assert after[_PARENT_ML]["fresh_snapshots"] == 1


@pytest.mark.parametrize("raw, bid, ask, declined", [
    (0.525, 0.15, 0.52, 0),    # half a cent over the ask: inside epsilon, kept
    (0.5251, 0.15, 0.52, 1),   # past it: refused
    (0.145, 0.15, 0.52, 0),    # bid mirror, kept
    (0.1449, 0.15, 0.52, 1),   # bid mirror, refused
    (0.53, None, None, 0),     # no book: outside this change
])
async def test_10298_refresh_boundaries_and_no_book(engine, monkeypatch, raw, bid, ask, declined):
    await _poll(_game(_ml(0.40, 0.39, 0.41, last=0.40)))
    before = await _legs(engine)
    stats = await _refresh(
        engine, monkeypatch, _game(_ml(raw, bid, ask, last=raw), **_SPREAD_BOOK),
        registered=[_mid(before, GAME_ID)],
    )
    after = await _legs(engine)
    # a kept leg is written by the unchanged resolver; a refused one is not
    assert after[_PARENT_ML]["fresh_snapshots"] == 1 - declined
    if declined:
        assert after[_PARENT_ML]["touched"] == before[_PARENT_ML]["touched"]
    assert stats.get("legs_declined_parent_refused", 0) == declined


async def test_10298_refresh_a_truncated_payload_tags_nothing(engine, monkeypatch):
    await _poll(_game(_ml(0.53, 0.52, 0.54, last=0.53)))
    before = await _legs(engine)
    stats = await _refresh(
        engine, monkeypatch, _game(None, **_SPREAD_BOOK),
        registered=[_mid(before, GAME_ID)],
    )
    after = await _legs(engine)
    assert stats.get("legs_declined_parent_refused", 0) == 0
    assert stats["legs_withdrawn_book_refuted"] == 0
    assert after[_PARENT_ML]["p"] == pytest.approx(0.53)
    assert after[_PARENT_SPREAD]["fresh_snapshots"] == 1


async def test_10298_refresh_negrisk_field_is_untouched_by_the_tag(engine, monkeypatch):
    """negRisk control: the Nolo field refreshes exactly as before — nothing tagged."""
    await _poll(_nolo(_leg(CAT5, 5, prices=[0.20, 0.80], bid=0.19, ask=0.21, last=0.20)))
    before = await _legs(engine)
    stats = await _refresh(
        engine, monkeypatch,
        _nolo(_leg(CAT5, 5, prices=[0.22, 0.78], bid=0.21, ask=0.23, last=0.22)),
        registered=[_mid(before, EVENT_ID)],
    )
    after = await _legs(engine)
    assert stats.get("legs_declined_parent_refused", 0) == 0
    assert after[(EVENT_ID, CAT5)]["fresh_snapshots"] == 1
    assert after[(EVENT_ID, CAT4)]["fresh_snapshots"] == 1


async def test_10298_refresh_singleton_game_is_untouched_by_the_tag(engine, monkeypatch):
    """Single-market control: one market, raw 0.53 over 0.15/0.52, nothing tagged."""
    from app.services.polymarket_api import PolymarketEvent

    def _solo(m):
        return PolymarketEvent(id=GAME_ID, title="Lions vs. Packers", neg_risk=False, markets=[m])

    await _poll(_solo(_ml(0.40, 0.39, 0.41, last=0.40)))
    before = await _legs(engine)
    stats = await _refresh(
        engine, monkeypatch, _solo(_ml(0.53, 0.15, 0.52, last=0.53)),
        registered=[_mid(before, GAME_ID)],
    )
    assert (await _legs(engine))[_PARENT_ML]["fresh_snapshots"] == 1, "written as before"
    assert stats.get("legs_declined_parent_refused", 0) == 0
