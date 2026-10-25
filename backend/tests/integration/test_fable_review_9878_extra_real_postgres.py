"""Extra real-PostgreSQL regression scenarios for #9878 / #11040 (adapted from Fable review).

F2b  The SAME 8h-old prices as F2, but the family is refused (Dec 31 rule
     incompatible), so Oct 31 is served as today's ordinary standalone card.
LIVE The D2 family as served, then a newer Dec 31 price written to the row and
     the REAL `/api/feed/price-cards` builder (`feed_prices._market_cards`) run
     over the members, plus authoritative settlement propagation on `/api/feed/price-cards`
     when a market row still has lagging `status='open'` (B2 + B6).
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from tests.integration.test_fable_review_9878_real_postgres import (  # noqa: F401
    DB_URL, OUT_DIR, _event, _feed, _leg, _poll, _retained, engine,
)
from tests.integration.test_fable_review_9878_scenarios_real_postgres import (
    BASIS_AT, RETAINED_NOW, _base, _iso, _record, _retained_prices, _set_meta, _set_outcome,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not DB_URL, reason="set SEARCH_TEST_DATABASE_URL"),
]


async def test_F2b_same_stale_prices_family_refused_existing_card(engine):
    r, ids = await _base(engine)
    bad = r["rule"].replace("between market creation and the specified date", "between November 1 and the specified date")
    st = await _poll(_event([_leg(r, "oct"), _leg(r, "dec", description=bad)]))
    assert not st["errors"]
    obs = _iso(RETAINED_NOW - timedelta(hours=8))
    await _retained_prices(engine, r, ids, oct_obs=obs, dec_obs=obs)
    s = _record("F2b_prices_8h_old_family_refused", await _feed(engine, RETAINED_NOW))
    assert not any(x["type"] == "bundle" for x in s["displayed"])


async def test_LIVE_newer_price_and_settlement_through_real_price_cards_route(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.routes import feed_prices

    r, ids = await _base(engine)
    o, d = await _retained_prices(engine, r, ids)
    await _set_outcome(engine, d["Yes"], probability_change_24h=-0.065)
    await _set_outcome(engine, d["No"], probability_change_24h=0.065)
    await _set_outcome(engine, o["Yes"], probability_change_24h=-0.011)
    await _set_meta(engine, o["market_id"], {"dated_movement_basis": {str(o["Yes"]): [0.084, BASIS_AT]}})
    await _set_meta(engine, d["market_id"], {"dated_movement_basis": {str(d["Yes"]): [0.31, BASIS_AT]}})
    _record("LIVE_served", await _feed(engine, RETAINED_NOW))

    # SYNTHETIC later tick: Dec 31 Yes 0.245 -> 0.32 two minutes after the serve.
    later = RETAINED_NOW + timedelta(minutes=2)
    await _set_outcome(engine, d["Yes"], current_probability=0.32, last_updated=later, probability_change_24h=0.01)
    await _set_outcome(engine, d["No"], current_probability=0.68, last_updated=later, probability_change_24h=-0.01)
    # SYNTHETIC later tick for Oct 31 too (0.073 -> 0.15), used by the standalone-card control.
    await _set_outcome(engine, o["Yes"], current_probability=0.15, last_updated=later, probability_change_24h=0.066)
    await _set_outcome(engine, o["No"], current_probability=0.85, last_updated=later, probability_change_24h=-0.066)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        items, dispositions = await feed_prices._market_cards(db, [o["market_id"], d["market_id"]], later + timedelta(minutes=1))
    body = {"items": feed_prices._public(items), "dispositions": dispositions,
            "built_at": (later + timedelta(minutes=1)).timestamp()}
    out = OUT_DIR / "scenarios"
    out.mkdir(parents=True, exist_ok=True)
    (out / "LIVE_price_cards.json").write_text(json.dumps(json.loads(json.dumps(body, default=str)), indent=1))
    dec = next(i for i in body["items"] if i["data"]["id"] == d["market_id"])
    yes_rows = [t for t in dec["data"].get("top_outcomes") or [] if t.get("id") == d["Yes"]]
    assert yes_rows and abs(yes_rows[0]["probability"] - 0.32) < 1e-9, dec["data"].get("top_outcomes")
    assert (dec["data"].get("deadline_member") or {}).get("yes_probability") == pytest.approx(0.32)

    # B2 on price-cards path: authoritative outcome settlement on a lagging `status='open'` row
    # must survive the `FuturesMarketSnapshot` carrier inside `feed_prices._market_cards`.
    await _set_outcome(engine, o["No"], is_winner=True, resolution_source="api_settlement")
    await _set_outcome(engine, o["Yes"], is_winner=False, resolution_source="api_settlement")
    async with maker() as db:
        settled_items, _ = await feed_prices._market_cards(db, [o["market_id"], d["market_id"]], later + timedelta(minutes=2))
    settled_public = feed_prices._public(settled_items)
    oct_card = next(i for i in settled_public if i["data"]["id"] == o["market_id"])
    oct_member = oct_card["data"].get("deadline_member") or {}
    assert (oct_member.get("settlement") or {}).get("state") == "resolved", oct_member
    assert (oct_member.get("settlement") or {}).get("result") == "No", oct_member
    assert (oct_member.get("settlement") or {}).get("lagging_local_status") is True, oct_member
