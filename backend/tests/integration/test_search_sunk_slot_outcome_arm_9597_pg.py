"""#9597 — `red sox` on a playoff game day shows the AL pennant, not nine inning props.

THE DEFECT, read on production `462717ea48` 2026-09-29 ~10:40Z, the first day of
MLB's postseason: `/search?q=red sox` served the World Series and then nine props
from tonight's Red Sox @ Yankees game (seven "- Nth Inning Winner"), and no
`MLB: 2026 American League Champion` (199045, tier 2, $4.4M, Boston 11.5%).
`?debug_timing=1`: `futures_outcome_arm: skipped`, `futures_refill_source:
not_fired`. `mariners` (no game tonight) showed the pennant.

THE MECHANISM. The 20-row window is all name matches, so the outcome arm is
skipped (LAT-P111) and the pennant, an OUTCOME match, is never fetched. #8628
r2's fixture cap then sinks every prop past the second, but sunk rows still ship
when nothing else answers, and here nothing else is in hand.

THE SEED reproduces that shape: 22 props of ONE fixture match `red sox` by NAME
(saturating the window), each with the two clubs as its outcomes, and the pennant
and ALDS boards match only on an outcome. THE FIX runs the outcome arm once,
outcome-only by exclusion, when a sunk row would be shipped.

STRAWMAN: the new arm disarmed -> the pennant is missing, props fill the page.
MUTANT the seed is built to bite: drop the tier<=1 exclusion and the arm returns
20 of the same props (they name the club in their outcomes and sort first), so
the pennant is missing again.
CONTROLS: (1) `mariners`: three props, the window is not saturated, the arm is
`not_fired` and the pennant arrives by the old path; (2) the page's head is
unchanged — the World Series, then the fixture's two kept props.

THE WORLD SERIES ROW. Without this arm the page was all name matches, so the
headline lane's absent arm promoted the World Series to row 0. With it, the page
holds outcome-only rows, that gate is false, and the World Series arrives as one
of them — #9587's hoist arm (PR #9592) is what keeps it at row 0, so this file
needs #9592 on its base. `test_the_world_series_still_leads` is that pin.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres sunk-slot "
            "outcome arm gate (CI job `search-recall` provides one)"
        ),
    ),
]

FIXTURE = "Boston Red Sox vs. New York Yankees"
RED_SOX_PROPS = [
    f"{FIXTURE} - {label}"
    for label in (
        [f"{n}{s} Inning Winner" for n, s in (
            (1, "st"), (2, "nd"), (3, "rd"), (4, "th"), (5, "th"),
            (6, "th"), (7, "th"), (8, "th"), (9, "th"),
        )]
        + ["First 5 Innings Winner", "First 3 Innings Winner",
           "First 7 Innings Winner", "Run Line", "Alternate Run Line",
           "Moneyline", "Race to 3 Runs", "Race to 5 Runs",
           "First Team to Score", "Last Team to Score", "Highest Scoring Inning",
           "Extra Innings Winner", "Series Game 1 Winner"]
    )
]
WORLD_SERIES = "MLB World Series Champion 2026"
AL_PENNANT = "MLB: 2026 American League Champion"
ALDS_ADVANCE = "MLB Playoffs: Team to advance to ALDS"
MARINERS_PROPS = [
    "Seattle Mariners vs. Detroit Tigers - 1st Inning Winner",
    "Seattle Mariners vs. Detroit Tigers - Run Line",
    "Seattle Mariners vs. Detroit Tigers - Moneyline",
]


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
    sox_yanks = [("Boston Red Sox", 0.45), ("New York Yankees", 0.55)]
    mariners_tigers = [("Seattle Mariners", 0.52), ("Detroit Tigers", 0.48)]
    rows = (
        [(n, 5, "game_prop", 20_000.0, sox_yanks) for n in RED_SOX_PROPS]
        + [(n, 5, "game_prop", 20_000.0, mariners_tigers) for n in MARINERS_PROPS]
        + [(
            WORLD_SERIES, 1, "championship", 41_786_299.0,
            [("Los Angeles Dodgers", 0.30), ("Milwaukee Brewers", 0.16),
             ("Seattle Mariners", 0.12), ("Philadelphia Phillies", 0.10),
             ("New York Yankees", 0.095), ("Boston Red Sox", 0.08),
             ("Cleveland Guardians", 0.06), ("Chicago Cubs", 0.05)],
        )]
        + [(
            AL_PENNANT, 2, "championship", 4_443_015.0,
            [
                ("New York Yankees", 0.22),
                ("Seattle Mariners", 0.18),
                ("Boston Red Sox", 0.115),
                ("Detroit Tigers", 0.09),
            ],
        )]
        + [(
            ALDS_ADVANCE, 5, "championship", 60_000.0,
            [
                ("New York Yankees", 0.585),
                ("Boston Red Sox", 0.415),
                ("Detroit Tigers", 0.47),
                ("Seattle Mariners", 0.53),
            ],
        )]
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        for i, (name, tier, category, volume, outcomes) in enumerate(rows):
            market = FuturesMarket(
                source="polymarket", external_id=f"sunk-9597-{i}", name=name,
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

    yield session_maker

    await engine.dispose()


@pytest.fixture
async def search(maker):
    """`GET /api/events/search?debug_timing=1` against the real app and database.

    Returns ``(names, debug_timing)``.
    """
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
        ) as http:

            async def _get(q: str) -> tuple[list[str], dict]:
                resp = await http.get(
                    "/api/events/search", params={"q": q, "debug_timing": 1}
                )
                assert resp.status_code == 200, f"{q!r} -> {resp.status_code}"
                payload = resp.json()
                assert "futures" in payload, sorted(payload)
                names = [f["name"] for f in payload["futures"] or []]
                return names, payload.get("debug_timing") or {}

            yield _get

    app.dependency_overrides.clear()


def _disarm(monkeypatch):
    from app.routes import events as events_module

    monkeypatch.setattr(
        events_module, "_needs_sunk_slot_outcome_arm", lambda *a, **k: False
    )


@pytest.mark.parametrize("q", ["red sox", "Red Sox", "boston red sox"])
async def test_the_pennant_takes_a_sunk_props_slot(search, q):
    futures, timing = await search(q)
    assert timing.get("futures_outcome_arm") == "skipped", timing
    assert timing.get("futures_sunk_slot_arm") == "merged", timing
    assert AL_PENNANT in futures, f"{q!r} served {futures}"
    # Above every SUNK prop: the fixture keeps two rows, the rest sit below.
    props_before = [n for n in futures[: futures.index(AL_PENNANT)] if n in RED_SOX_PROPS]
    assert len(props_before) <= 2, futures


async def test_the_alds_board_arrives_too(search):
    futures, _ = await search("red sox")
    assert ALDS_ADVANCE in futures, futures
    assert sum(1 for n in futures if n in RED_SOX_PROPS) < 10, futures


async def test_strawman_without_the_arm_props_fill_the_page(search, monkeypatch):
    """The seed reproduces production: disarm the arm and the pennant is gone."""
    _disarm(monkeypatch)
    futures, timing = await search("red sox")
    assert timing.get("futures_outcome_arm") == "skipped", timing
    assert timing.get("futures_sunk_slot_arm") == "not_fired", timing
    assert AL_PENNANT not in futures and ALDS_ADVANCE not in futures, futures
    assert futures[0] == WORLD_SERIES, futures
    assert all(n in RED_SOX_PROPS for n in futures[1:]), futures


async def test_control_the_name_match_head_is_unchanged(search, monkeypatch):
    armed, _ = await search("red sox")
    _disarm(monkeypatch)
    disarmed, _ = await search("red sox")
    assert armed[:3] == disarmed[:3], (armed, disarmed)
    assert armed[0] == WORLD_SERIES and all(n in RED_SOX_PROPS for n in armed[1:3]), (
        armed,
    )


@pytest.mark.parametrize("q", ["red sox", "yankees"])
async def test_the_world_series_still_leads(search, q):
    futures, timing = await search(q)
    assert timing.get("futures_sunk_slot_arm") == "merged", timing
    assert futures[0] == WORLD_SERIES and AL_PENNANT in futures, futures


async def test_control_an_unsaturated_window_never_fires_the_arm(search):
    futures, timing = await search("mariners")
    assert timing.get("futures_outcome_arm") == "merged", timing
    assert timing.get("futures_sunk_slot_arm") == "not_fired", timing
    assert AL_PENNANT in futures, futures
