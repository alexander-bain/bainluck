"""#10230 r2 — `judge` reaches the Aaron Judge market through the SQL window, not around it.

r1 (`ed6ad55095`) taught `_rerank_search_futures` to lift a traded contender above
thin name matches, and went live in v5428 (2026-10-02 23:20Z) changing nothing:
both routes fetch a 20-row window ordered name match first, then market tier, and
production's `judge` window is 11 name matches plus 9 tier 1-3 outcome rows. "MLB
The Show 27: Cover Athlete" is tier 5, so the window was full before it, and the
reranker never saw it. r1's route test put the market INSIDE the window, which is
the one thing production never does.

So these windows are production's shape — full, the contender absent — and the
session answers the headline-contender statement the way SQL would: with its tier-1
clause in the WHERE it returns nothing (the only tier-1 Judge outcome is the Hank
Aaron Award at 0.3%), without it the Show cover. Red on r1's code: the lane still
asks with the tier clause, and the Show cover never reaches either response.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

_asyncio = pytest.mark.asyncio

SHOW_COVER_ID = 24014885
WINDOW = 20  # `_SEARCH_FUTURES_WINDOW` == `_TYPEAHEAD_FUTURES_POOL`


def _outcome(name, prob, oid):
    return SimpleNamespace(
        id=oid, name=name, probability=prob, current_probability=prob,
        opening_probability=prob, is_winner=None, price=prob,
        probability_change_24h=None, american_odds=None,
        current_american_odds=None, rank=oid % 10, sort_order=oid,
        current_yes_bid=None, current_yes_ask=None, external_id=f"OUT-{oid}",
        resolution_source=None,
    )


def _market(mid, name, outcomes, *, volume, tier, category):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=mid, name=name, external_id=f"KX-{mid}",
        llm_sport_category=category, category=category,
        market_tier=tier, market_type="winner", sport=None, sport_id=None,
        source="kalshi", volume=volume, status="open",
        resolution_date=(now + timedelta(days=40)).date(), updated_at=now,
        canonical_market_key=None, image_url=None, hook_description=None,
        group_id=None, event_id=None, outcomes=outcomes,
    )


COUNTIES = ["Harris", "Williamson", "El Paso", "Tarrant", "Fort Bend", "Denton",
            "Collin", "Bexar", "Travis", "Hidalgo"]


def _county(i, county, volume):
    mid = 63_135_100 + i
    return _market(
        mid, f"{county} County Judge winner?",
        [_outcome(f"Candidate {county} A", 0.7, mid * 10 + 1),
         _outcome(f"Candidate {county} B", 0.3, mid * 10 + 2)],
        volume=volume, tier=1, category="politics",
    )


def _name_matches(volume=None):
    """Production's 11: ten county races (NULL to $4k) and the $8k impeachment question."""
    rows = [_county(i, c, volume if volume is not None else (4005.0 if i == 0 else None))
            for i, c in enumerate(COUNTIES)]
    rows.append(_market(
        112810, "Will the House impeach a federal judge this year?",
        [_outcome("Yes", 0.0905, 1128101), _outcome("No", 0.9095, 1128102)],
        volume=volume if volume is not None else 8056.0, tier=5, category="legal",
    ))
    return rows


def _outcome_only():
    """Nine tier 1-3 rows that name Aaron Judge (or a near word) and do NOT qualify."""
    def judge_board(mid, name, prob, volume, tier):
        return _market(mid, name, [_outcome("Cal Raleigh", 0.6, mid * 10 + 1),
                                   _outcome("Aaron Judge", prob, mid * 10 + 2)],
                       volume=volume, tier=tier, category="baseball")
    return [
        judge_board(206625, "MLB: 2026 AL Hank Aaron Winner", 0.003, 421512.0, 1),
        judge_board(58728333, "American League MVP Finalists", 0.03, 18968.0, 2),
        _market(59164635, "Which ballot measures will pass in Georgia?",
                [_outcome("Nonpartisan Elections for Probate Judges Amendment", 0.70,
                          591646351)],
                volume=12403.0, tier=2, category="politics"),
        _market(59699781, "Daytime Emmy Awards: Outstanding Legal / Courtroom Series",
                [_outcome("Justice For The People with Judge Milian", 0.17, 596997811)],
                volume=1172.0, tier=2, category="entertainment"),
        judge_board(216, "AL MVP Winner?", 0.01, 5055009.0, 3),
        judge_board(132768, "MLB: 2026 AL MVP ", 0.0005, 1047535.0, 3),
        judge_board(218, "AL Hank Aaron Award Winner?", 0.01, 33857.0, 3),
        judge_board(63309006, "MLB Postseason: World Series MVP", 0.045, 499.0, 3),
        judge_board(62952891, "ALCS MVP Winner", 0.0635, None, 3),
    ]


def _show_cover():
    return _market(
        SHOW_COVER_ID, "MLB The Show 27: Cover Athlete",
        [_outcome("Cal Raleigh", 0.40, 240148851), _outcome("Aaron Judge", 0.085, 240148852)],
        volume=21820.0, tier=5, category="baseball",
    )


def _empty_result():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.unique.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = None
    result.fetchall.return_value = []
    result.all.return_value = []
    result.first.return_value = None
    result.mappings.return_value.all.return_value = []
    return result


def _lane_where_has_tier_clause(sql: str) -> bool:
    return "futures_markets.market_tier =" in sql.split("ORDER BY")[0]


def _session(window, contenders, lane_sql: list):
    """The window for the window's statement; the contender lane answered like SQL.

    `~*` discriminates the headline-contender statement (the only `~*` builder in
    the route, #2579's harness). With the tier-1 clause in its WHERE, SQL returns
    only tier-1 rows; every contender here is below tier 1.
    """
    session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        result = _empty_result()
        try:
            sql = str(stmt)
        except Exception:  # noqa: BLE001
            return result
        if "futures_markets" not in sql or "SELECT" not in sql.upper():
            return result
        if "~*" in sql:
            lane_sql.append(sql)
            rows = ([m for m in contenders if m.market_tier == 1]
                    if _lane_where_has_tier_clause(sql) else contenders)
        else:
            rows = window
        result.scalars.return_value.unique.return_value.all.return_value = list(rows)
        result.scalars.return_value.all.return_value = list(rows)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


async def _get(url, window, contenders, monkeypatch, lane_sql):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    session = _session(window, contenders, lane_sql)

    async def _db():
        yield session

    async def _no_user():
        return None

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_rw] = _db
    app.dependency_overrides[get_optional_user] = _no_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app),
                                   base_url="http://test") as ac:
                resp = await ac.get(url)
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    return resp.json()


def _full_window():
    rows = _name_matches() + _outcome_only()
    assert len(rows) == WINDOW
    return rows


def _typeahead_ids(body):
    return [str(s.get("market_id")) for s in body["suggestions"] if s.get("type") == "futures"]


def _search_ids(body):
    return [str(m.get("id")) for m in body.get("futures") or []]


@_asyncio
async def test_typeahead_judge_reaches_the_show_cover_through_a_full_window(monkeypatch):
    lane_sql: list = []
    body = await _get("/api/events/typeahead?q=judge", _full_window(), [_show_cover()],
                      monkeypatch, lane_sql)
    ids = _typeahead_ids(body)
    assert str(SHOW_COVER_ID) in ids, ids
    assert len(ids) == 5, ids
    assert lane_sql and not _lane_where_has_tier_clause(lane_sql[-1])


@_asyncio
async def test_search_judge_leads_with_the_show_cover_through_a_full_window(monkeypatch):
    lane_sql: list = []
    body = await _get("/api/events/search?q=judge&debug_timing=true", _full_window(),
                      [_show_cover()], monkeypatch, lane_sql)
    ids = _search_ids(body)
    # Every name match trades under $10k, so r1's rule puts the contender first.
    assert ids[:1] == [str(SHOW_COVER_ID)], ids
    assert lane_sql and not _lane_where_has_tier_clause(lane_sql[-1])


@_asyncio
async def test_control_a_window_with_room_keeps_the_tier_clause(monkeypatch):
    """Not full: the cut dropped nothing, so the lane asks exactly what it always asked."""
    lane_sql: list = []
    window = _name_matches() + _outcome_only()[:4]
    body = await _get("/api/events/search?q=judge&debug_timing=true", window,
                      [_show_cover()], monkeypatch, lane_sql)
    assert str(SHOW_COVER_ID) not in _search_ids(body)
    assert all(_lane_where_has_tier_clause(s) for s in lane_sql), lane_sql


@_asyncio
async def test_control_traded_name_matches_keep_the_tier_clause(monkeypatch):
    """`hawks`' shape: every name match trades >= $10k, so nothing is thin to beat."""
    lane_sql: list = []
    window = _name_matches(volume=50_000.0) + _outcome_only()
    for path in ("/api/events/search?q=judge&debug_timing=true",
                 "/api/events/typeahead?q=judge"):
        body = await _get(path, window, [_show_cover()], monkeypatch, lane_sql)
        ids = _search_ids(body) if "search?" in path else _typeahead_ids(body)
        assert str(SHOW_COVER_ID) not in ids, (path, ids)
    assert all(_lane_where_has_tier_clause(s) for s in lane_sql), lane_sql


def test_statement_any_tier_drops_the_clause_and_orders_tier_one_first():
    from app.routes.events import _headline_contender_statement

    plain = str(_headline_contender_statement([r"\mjudge\M"], [], limit=5))
    wide = str(_headline_contender_statement([r"\mjudge\M"], [], limit=5, any_tier=True))
    assert _lane_where_has_tier_clause(plain)
    assert "market_tier" not in plain.split("ORDER BY")[1]
    assert not _lane_where_has_tier_clause(wide)
    assert "futures_markets.market_tier =" in wide.split("ORDER BY")[1]
