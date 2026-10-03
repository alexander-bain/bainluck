"""#9587 — `cubs` leads Futures & Markets with the World Series, like `yankees` does.

THE DEFECT, read on production v5274 (`9aad33b0`) 2026-09-29 09:2xZ, the first
day of MLB's postseason: `/search?q=cubs` served `MLB World Series Champion
2026` at row 7 of 10, behind six Cubs–Padres game props; `padres` row 6. For
`yankees`, `phillies`, `brewers`, `tigers`, `mariners` it was row 0.

THE MECHANISM. `/search`'s headline-contender lane fired only when every page
row was a name match — i.e. only when the contender could NOT be on the page.
When the World Series market reached the page by itself (an outcome-only row),
the gate was false and the market kept the reranker's slot under the props.
Absent meant promoted to row 0; present meant buried.

THE SEED reproduces that shape: eight Cubs game props match `cubs` by NAME, so
the window is not saturated, the outcome arm runs and brings the World Series
market in by its "Chicago Cubs" outcome, and the reranker places it after every
name match. THE FIX runs the same contender statement restricted to the page's
tier-1 outcome-only ids and hoists the page's own row.

STRAWMAN: the hoist arm disarmed -> the World Series is back below the props.
CONTROLS: (1) the page's SET of rows is identical with and without the hoist —
it reorders, never adds or drops; (2) a tier-1 board where the typed club is a
2% longshot is on the page and is NOT hoisted — the lane's own probability
floor still decides, not the new arm.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.market_display_name import rewrite_question_colon_display

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres on-page "
            "contender hoist gate (CI job `search-recall` provides one)"
        ),
    ),
]

WORLD_SERIES = "MLB World Series Champion 2026"
CUBS_PROPS = [
    "Will there be a run scored in the first inning?: Chicago Cubs vs. San Diego Padres",
    "Spread: Chicago Cubs (-1.5)",
    "Spread: Chicago Cubs (-2.5)",
    "Will the game go to extra innings?: Chicago Cubs vs. San Diego Padres",
    "Chicago Cubs Team Total: O/U 2.5",
    "1st 5 Innings Spread: Chicago Cubs (-1.5)",
    "Chicago Cubs vs. San Diego Padres: O/U 7.5",
    "Chicago Cubs vs. San Diego Padres: 1st 5 Innings O/U 5.5",
]
# What the search card PRINTS for those seeded names: #10240's one
# question-colon rule turns "…inning?: A vs. B" into "…inning? — A vs. B" on the
# card. The seed stores the venue's text; the ordering assertions read the card.
CUBS_PROPS_SERVED = [rewrite_question_colon_display(n) for n in CUBS_PROPS]
ROYALS_PROPS = [
    "Spread: Kansas City Royals (-1.5)",
    "Kansas City Royals Team Total: O/U 3.5",
    "Kansas City Royals vs. Detroit Tigers: O/U 8.5",
]
# A tier-1, high-volume board where the Royals are a listed longshot (0.02, no
# team anchor): the lane's clause 3 refuses it, so it must stay where it ranks.
LONGSHOT_BOARD = "AL Pennant Winner 2026"


@pytest.fixture
async def maker():
    """A clean schema per test — the `search-recall` database is shared."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    now = datetime.now(timezone.utc)
    yes_no = [("Yes", 0.45), ("No", 0.55)]
    rows = (
        [(n, 5, "game_prop", 20_000.0, yes_no) for n in CUBS_PROPS + ROYALS_PROPS]
        + [(
            WORLD_SERIES, 1, "championship", 40_000_000.0,
            [
                ("Los Angeles Dodgers", 0.30),
                ("Milwaukee Brewers", 0.16),
                ("New York Yankees", 0.10),
                ("Chicago Cubs", 0.08),
                ("San Diego Padres", 0.06),
            ],
        )]
        + [(
            LONGSHOT_BOARD, 1, "championship", 9_000_000.0,
            [
                ("New York Yankees", 0.35),
                ("Detroit Tigers", 0.25),
                ("Kansas City Royals", 0.02),
            ],
        )]
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        for i, (name, tier, category, volume, outcomes) in enumerate(rows):
            market = FuturesMarket(
                source="polymarket", external_id=f"hoist-9587-{i}", name=name,
                status="open", resolution_date=now + timedelta(days=20),
                llm_sport_category="baseball", category=category,
                market_tier=tier, volume=volume,
            )
            session.add(market)
            await session.flush()
            for outcome, p in outcomes:
                session.add(FuturesOutcome(
                    market_id=market.id, name=outcome, current_probability=p,
                    external_id=f"{market.external_id}:{outcome}",
                ))
        await session.commit()

    try:
        yield session_maker
    finally:
        # Leave nothing behind: the `search-recall` database is shared with the next suite.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def http(maker):
    """The real app against the real database, no Redis."""
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override
    app.dependency_overrides[get_optional_user] = lambda: None

    with patch(
        "app.tasks.redis_state.get_redis_client",
        side_effect=RuntimeError("no redis in the recall gate"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def search(http):
    """`GET /api/events/search` futures card names, in served order."""

    async def _get(q: str) -> list[str]:
        resp = await http.get("/api/events/search", params={"q": q})
        assert resp.status_code == 200, f"{q!r} -> {resp.status_code}"
        payload = resp.json()
        assert "futures" in payload, sorted(payload)
        return [f["name"] for f in payload["futures"] or []]

    return _get


def _disarm_hoist(monkeypatch):
    from app.routes import events as events_module

    monkeypatch.setattr(
        events_module, "on_page_contender_candidates", lambda page, is_match: []
    )


@pytest.mark.parametrize("q", ["cubs", "Cubs", "chicago cubs"])
async def test_the_world_series_leads_when_it_is_already_on_the_page(search, q):
    futures = await search(q)
    assert futures and futures[0] == WORLD_SERIES, f"{q!r} served {futures[:4]}"
    assert set(futures[1:]) <= set(CUBS_PROPS_SERVED), futures


async def test_strawman_without_the_hoist_arm_it_sits_below_the_props(
    search, monkeypatch
):
    """The seed reproduces production: disarm the arm and the props lead."""
    _disarm_hoist(monkeypatch)
    futures = await search("cubs")
    assert WORLD_SERIES in futures, f"seed no longer puts it on the page: {futures}"
    assert futures.index(WORLD_SERIES) > 0 and futures[0] in CUBS_PROPS_SERVED, futures


async def test_control_the_hoist_reorders_and_never_changes_which_rows_ship(
    search, monkeypatch
):
    hoisted = await search("cubs")
    _disarm_hoist(monkeypatch)
    unhoisted = await search("cubs")
    assert sorted(hoisted) == sorted(unhoisted) and len(hoisted) == len(unhoisted)
    rest = [n for n in unhoisted if n != WORLD_SERIES]
    assert hoisted == [WORLD_SERIES] + rest, (hoisted, unhoisted)


async def test_control_a_longshot_board_on_the_page_is_not_hoisted(search):
    futures = await search("royals")
    assert LONGSHOT_BOARD in futures, f"control seed lost its board: {futures}"
    assert futures[0] in ROYALS_PROPS and futures.index(LONGSHOT_BOARD) > 0, futures


# ---------------------------------------------------------------------------
# #10240 residual: the phone search DROPDOWN prints the card's title.
#
# Production v5433 (`7f1bbb105f`), 2026-10-03 04:08Z, ux at 390px: the /search
# card and the market page read "…extra innings? — Yankees vs. Rays", while the
# overlay's typeahead rows for `extra innings` still read "…extra innings?: …".
# The typeahead served `rewrite_venue_league_vocabulary(name)` and never the
# question-colon rule. It now applies that one rule AFTER its rank, so the
# scorer still reads the text it read before (the id-order control below).
# ---------------------------------------------------------------------------


async def _typeahead_futures(http, q: str) -> list[tuple[int, str]]:
    resp = await http.get("/api/events/typeahead", params={"q": q})
    assert resp.status_code == 200, f"{q!r} -> {resp.status_code}"
    return [
        (r["market_id"], r["text"])
        for r in resp.json()["suggestions"]
        if r.get("type") == "futures"
    ]


async def _search_cards(http, q: str) -> dict[int, str]:
    resp = await http.get("/api/events/search", params={"q": q})
    assert resp.status_code == 200, f"{q!r} -> {resp.status_code}"
    return {f["id"]: f["name"] for f in resp.json()["futures"] or []}


def _disarm_typeahead_colon_rule(monkeypatch):
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "rewrite_question_colon_display", lambda n: n)


EXTRA_INNINGS = CUBS_PROPS[3]


async def test_10240_the_dropdown_row_reads_like_the_card_it_opens(http):
    rows = await _typeahead_futures(http, "extra innings")
    texts = [t for _, t in rows]
    assert rewrite_question_colon_display(EXTRA_INNINGS) in texts, rows
    assert not [t for t in texts if "?:" in t], rows
    cards = await _search_cards(http, "extra innings")
    for market_id, text in rows:
        if market_id in cards:
            assert text == cards[market_id], (market_id, text, cards[market_id])
    assert set(dict(rows)) & set(cards), (rows, cards)


async def test_10240_control_rows_without_the_shape_are_byte_identical(http):
    rows = await _typeahead_futures(http, "cubs")
    plain = {n for n in CUBS_PROPS + [WORLD_SERIES] if "?:" not in n}
    served = {n: rewrite_question_colon_display(n) for n in CUBS_PROPS if "?:" in n}
    texts = [t for _, t in rows]
    assert plain & set(texts), f"control seed served no plain row: {rows}"
    for text in texts:
        assert text in plain or text in served.values(), text


async def test_10240_strawman_and_control_disarmed_prints_the_colon_same_order(
    http, monkeypatch
):
    armed = await _typeahead_futures(http, "extra innings")
    _disarm_typeahead_colon_rule(monkeypatch)
    disarmed = await _typeahead_futures(http, "extra innings")
    # Strawman: without the rule the dropdown prints the venue's "?:" again.
    assert EXTRA_INNINGS in [t for _, t in disarmed], disarmed
    # Control: the rule is display-only — the same rows in the same order.
    assert [m for m, _ in armed] == [m for m, _ in disarmed], (armed, disarmed)
