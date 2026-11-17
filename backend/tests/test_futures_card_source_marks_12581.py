"""Futures cards name only the inputs that priced their displayed rows (#12581)."""

from datetime import timedelta

import pytest

import app.routes.events as events
import app.routes.futures as routes
from tests.test_futures_browse_faceted_withhold_6993 import _BrowseDB, _FacetedDB
from tests.test_futures_verified_title_9387 import (
    KALSHI_ID,
    NOW,
    ODDS_ID,
    PM_ID,
    PM_ROWS,
    _DB,
    _at,
    _route_io,  # noqa: F401 -- existing real-route IO fixture
    kalshi_market,
    odds_market,
    pm_market,
    trio,
)

SURFACES = ("browse", "faceted", "list", "search", "typeahead")


async def card_rows(surface, market, *, withheld=(), verified=None):
    if surface == "browse":
        db = _BrowseDB([market])
        payload = await routes.browse_futures(
            category=None, q=None, limit=50, offset=0, db=db,
        )
        return payload["items"][0]["top_outcomes"]
    if surface == "faceted":
        market.market_tags = []
        payload = await routes.faceted_futures_search(
            tags=None, sport=None, category=None, stakes=None, narrative=None,
            audience=None, q=None, sort=None, page=1, per_page=25,
            db=_FacetedDB([market]),
        )
        return payload["markets"][0]["top_outcomes"]
    if surface == "list":
        return routes._format_market_summary(
            market,
            {market.canonical_market_key: {"count": 3, "sources": [
                "kalshi", "polymarket", "odds_api",
            ]}},
        )["top_outcomes"]
    return events._build_search_top_outcomes(
        market, limit=5, lean=surface == "typeahead",
        withheld=set(withheld), verified=verified,
    )


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize(
    "factory,key,raw",
    [(kalshi_market, "kalshi", 0.13), (pm_market, "polymarket", 0.135),
     (odds_market, "betting", 0.112913)],
)
async def test_source_card_retains_its_own_input_not_other_canonical_members(
    surface, factory, key, raw,
):
    market = factory()
    with _at():
        rows = await card_rows(surface, market)
    row = next(r for r in rows if "Buffalo" in r["name"])
    mark = row["source_mark"]
    assert mark["state"] == "single"
    assert [(s["key"], s["probability"]) for s in mark["sources"]] == [(key, raw)]
    assert mark["sources"][0]["observed_at"] is None
    assert mark["sources"][0]["reason"] == "observation_unknown"
    assert all("source_mark" in r for r in rows)
    if abs(row["probability"] - raw) > 1e-8:
        assert "scaled with the other outcomes to total 100%" in mark["method"]


@pytest.mark.parametrize("surface", SURFACES)
async def test_real_zero_is_a_source_price(surface):
    market = kalshi_market(rows=[(643833, "Buffalo", "KXSB-27-BUF", 0.0)], me=False)
    with _at():
        rows = await card_rows(surface, market)
    assert rows[0]["probability"] == 0.0
    assert rows[0]["source_mark"]["sources"][0]["probability"] == 0.0


@pytest.mark.parametrize("surface", ["browse", "faceted", "search", "typeahead"])
async def test_refused_price_cannot_reappear_in_the_sheet(surface, monkeypatch):
    async def withheld(*args, **kwargs):
        return {643833}

    monkeypatch.setattr(routes, "_withheld_price_outcome_ids", withheld)
    market = kalshi_market(rows=[(643833, "Buffalo", "KXSB-27-BUF", 0.4)], me=False)
    with _at():
        rows = await card_rows(surface, market, withheld={643833})
    assert rows[0]["probability"] is None
    assert rows[0]["source_mark"] == {
        "state": "none", "sources": [], "reason": "no_probability",
    }


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("price,expected", [(0.5, "none"), (0.0, "settled")])
async def test_settled_polymarket_keeps_the_detail_verdict(surface, price, expected):
    market = pm_market(rows=[(1709101, "Buffalo Bills", price)], status="resolved", me=False)
    market.outcomes[0].is_winner = False
    market.outcomes[0].resolution_source = "clob_authoritative"
    with _at():
        rows = await card_rows(surface, market)
    mark = rows[0]["source_mark"]
    assert mark["state"] == expected
    if expected == "settled":
        assert mark["settled"] == {"source": "clob_authoritative", "result": "Lost", "at": None}
    else:
        assert mark["reason"] == "result_unknown"


@pytest.mark.parametrize("lean", [False, True])
@pytest.mark.parametrize("mid", [ODDS_ID, KALSHI_ID, PM_ID])
async def test_search_blend_names_exact_inputs_and_adds_no_reads(mid, lean):
    markets = trio()
    market = next(m for m in markets if m.id == mid)
    db = _DB(markets)
    with _at():
        verdict = await routes._compose_verified_title(db, market)
        reads = list(db.statements)
        rows = await card_rows("typeahead" if lean else "search", market, verified=verdict)
    row = next(r for r in rows if r["name"] == "Buffalo Bills")
    assert row["source_mark"]["state"] == "blend"
    assert [(s["key"], s["probability"]) for s in row["source_mark"]["sources"]] == [
        ("kalshi", 0.13), ("polymarket", 0.135), ("betting", 0.112913),
    ]
    assert "scaled with the other outcomes" in row["source_mark"]["method"]
    assert db.statements == reads
    assert ("id" in row) is not lean


async def test_divergence_mark_names_only_the_admitted_source():
    pm_rows = [r if r[1] != "Buffalo Bills" else (r[0], r[1], 0.60) for r in PM_ROWS]
    markets = trio(odds=odds_market(anchor=None), pm=pm_market(rows=pm_rows))
    with _at():
        verdict = await routes._compose_verified_title(_DB(markets), markets[1])
        rows = await card_rows("search", markets[1], verified=verdict)
    row = next(r for r in rows if r["id"] == 643833)
    overlay = verdict.overlay[643833]
    assert overlay.aggregation_rule == "divergence_gate"
    assert row["source_mark"]["state"] == "single"
    assert [s["key"] for s in row["source_mark"]["sources"]] == overlay.contributing_sources


async def test_cached_card_carries_the_original_composition_inputs(monkeypatch):
    markets = trio()
    monkeypatch.setenv("VERIFIED_TITLE_CACHE_SECONDS", "60")
    monkeypatch.setattr(routes, "_VERIFIED_TITLE_CACHE", {})
    db = _DB(markets)
    with _at():
        first = await routes._resolve_verified_title(db, markets[0])
        a = await card_rows("search", markets[0], verified=first)
        reads = list(db.statements)
        markets[1].outcomes[0].current_probability = 0.9
        markets[1].outcomes[0].last_updated = NOW + timedelta(minutes=10)
        second = await routes._resolve_verified_title(db, markets[1])
        b = await card_rows("typeahead", markets[1], verified=second)
    assert db.statements == reads
    a_row, b_row = (next(r for r in rows if r["name"] == "Buffalo Bills") for rows in (a, b))
    assert a_row["source_mark"] == b_row["source_mark"]
    assert a_row["probability"] == b_row["probability"]
