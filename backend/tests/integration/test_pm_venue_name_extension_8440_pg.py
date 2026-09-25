"""#8440 — a Polymarket game market reaches the sportsbook row whose names its own extend.

Polymarket calls a Liiga club by its name plus its city ("Lukko Rauma vs. Tappara
Tampere"); the sportsbook row we already hold says "Lukko" v "Tappara". The
windowed ILIKE looks for ``%Lukko Rauma%`` / ``%Rauma%`` and neither is inside
"Lukko", so the market minted a second row for the game and search printed two
cards with contradictory results (production 2026-09-24: 15317756 "No result
reported", 15317914 "Lukko Rauma wins").

Everything that decides the answer here is SQL — ``strpos`` on a folded,
space-terminated string, ``translate`` for the accents, a window on the venue
stamp — and a recording session cannot run any of it. So: real PostgreSQL, the
real ``sports`` / ``teams`` / ``venues`` / ``events`` tables created in a private
schema (runs on the lane VM's Postgres 14 as well as in CI), and the real
``_find_matching_event``.
"""

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8440 "
            "venue-name-extension gate (CI job: search-recall)"
        ),
    ),
]

_SCHEMA = "pm_venue_name_extension_8440"
UTC = timezone.utc
GAME = datetime(2026, 9, 24, 15, 30, tzinfo=UTC)  # Lukko v Tappara, venue stamp
LISTED = datetime(2026, 9, 23, 14, 48, tzinfo=UTC)  # Gamma listing stamp
NOW = datetime(2026, 9, 23, 15, 15, tzinfo=UTC)  # the pass that minted 15317914

LIIGA, LALIGA = 22, 1310


@pytest.fixture
async def pg():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base, Event, Sport, Team, Venue

    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": _SCHEMA}}
    )
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {_SCHEMA}"))
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c,
                tables=[Sport.__table__, Team.__table__, Venue.__table__, Event.__table__],
            )
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        for sid, key in ((LIIGA, "icehockey_liiga"), (LALIGA, "soccer_spain_la_liga")):
            await s.execute(
                text("INSERT INTO sports (id, key, name, active) VALUES (:i, :k, :k, true)"),
                {"i": sid, "k": key},
            )
        await s.commit()
        yield s
        await s.rollback()
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
    await engine.dispose()


async def _event(s, eid, home, away, *, sport=LIIGA, at=GAME, ext="odds", status="scheduled"):
    await s.execute(
        text(
            "INSERT INTO events (id, sport_id, external_id, home_team_name, away_team_name, "
            "commence_time, status) VALUES (:id, :sp, :ext, :h, :a, :t, :st)"
        ),
        {
            "id": eid, "sp": sport, "h": home, "a": away, "t": at, "st": status,
            "ext": None if ext is None else f"{ext}-{eid}",
        },
    )
    await s.commit()


def _market(name, *, venue_start=GAME, source="polymarket", category="hockey"):
    meta = {"polymarket_event_id": "1069485"}
    if venue_start is not None:
        meta["venue_game_start"] = venue_start.isoformat()
    return SimpleNamespace(
        id=62084794, source=source, external_id="1069485", name=name,
        commence_time=LISTED, llm_sport_category=category, market_metadata=meta,
    )


async def _find(s, market):
    from app.tasks.prediction_market_matching import _find_matching_event
    from app.utils.prediction_market_matching import extract_matchup_with_ticker_fallback

    matchup = extract_matchup_with_ticker_fallback(market.name, external_id=market.external_id)
    assert matchup is not None and matchup.team_b, "specimen must parse as a matchup"
    return await _find_matching_event(s, matchup, market, NOW)


async def _extension_ids(s, market):
    from app.tasks.prediction_market_matching import (
        MAX_PAST_GAME_DELTA, _venue_name_extension_candidates,
    )
    from app.utils.prediction_market_matching import extract_matchup_with_ticker_fallback

    matchup = extract_matchup_with_ticker_fallback(market.name, external_id=market.external_id)
    rows = await _venue_name_extension_candidates(s, matchup, market, NOW - MAX_PAST_GAME_DELTA)
    return sorted(r.id for r in rows)


class TestTheSpecimenLinks:
    async def test_lukko_rauma_market_is_offered_the_sportsbook_row(self, pg):
        await _event(pg, 15317756, "Lukko", "Tappara")
        picked = await _find(pg, _market("Lukko Rauma vs. Tappara Tampere"))
        assert picked is not None, (
            "the market found no row, so it mints a second card for the game — #8440"
        )
        assert picked["event_id"] == 15317756
        assert picked["yes_is_home"] is True

    async def test_the_new_pass_is_what_links_it(self, pg, monkeypatch):
        # Control: with the extension pass silenced the same market finds
        # nothing — so the link above is the new pass, not the old ILIKE.
        import app.tasks.prediction_market_matching as pmm

        await _event(pg, 15317756, "Lukko", "Tappara")

        async def _nothing(*a, **k):
            return []

        monkeypatch.setattr(pmm, "_venue_name_extension_candidates", _nothing)
        assert await _find(pg, _market("Lukko Rauma vs. Tappara Tampere")) is None

    async def test_accented_stored_name_and_la_liga_suffix(self, pg):
        await _event(pg, 15317988, "Ässät", "SaiPa")
        await _event(pg, 15312070, "Getafe", "Málaga", sport=LALIGA)
        got = await _find(pg, _market("Assat Pori vs. SaiPa Lappeenranta"))
        assert got is not None and got["event_id"] == 15317988
        got = await _find(pg, _market("Getafe CF vs. Málaga CF", category="soccer"))
        assert got is not None and got["event_id"] == 15312070

    async def test_swapped_orientation_is_reached_and_reported(self, pg):
        await _event(pg, 15317759, "Tappara", "Lukko")
        picked = await _find(pg, _market("Lukko Rauma vs. Tappara Tampere"))
        assert picked is not None and picked["event_id"] == 15317759
        assert picked["yes_is_home"] is False


class TestTheRetrievalStaysNarrow:
    async def test_whole_word_prefix_only(self, pg):
        await _event(pg, 1, "Lukko", "Tappara")          # prefix both sides ✅
        await _event(pg, 2, "Rauma", "Tampere")          # the CITY words, not a prefix
        await _event(pg, 3, "Luk", "Tap")                # partial words
        await _event(pg, 4, "Lukko", "Kärpät")           # one side only
        await _event(pg, 5, "Lukko Rauma", "Tappara Tampere")  # identical names ✅
        ids = await _extension_ids(pg, _market("Lukko Rauma vs. Tappara Tampere"))
        assert ids == [1, 5]

    async def test_a_two_letter_stored_name_is_an_initial_not_a_club(self, pg):
        # "HC" IS a whole-word prefix of "HC Davos" — only the length floor
        # keeps every "HC …" / "EV …" row in the league out of the list.
        await _event(pg, 6, "HC", "EV")
        await _event(pg, 8, "HC Davos", "EV Zug")
        assert await _extension_ids(pg, _market("HC Davos vs. EV Zug")) == [8]

    async def test_only_near_the_venue_instant(self, pg):
        await _event(pg, 1, "Lukko", "Tappara", at=GAME + timedelta(hours=2, minutes=59))
        await _event(pg, 2, "Lukko", "Tappara", at=GAME + timedelta(hours=3, minutes=1))
        await _event(pg, 3, "Lukko", "Tappara", at=GAME - timedelta(days=4))
        ids = await _extension_ids(pg, _market("Lukko Rauma vs. Tappara Tampere"))
        assert ids == [1]

    async def test_needs_polymarket_and_the_venue_stamp(self, pg):
        await _event(pg, 1, "Lukko", "Tappara")
        assert await _extension_ids(pg, _market("Lukko Rauma vs. Tappara Tampere", venue_start=None)) == []
        assert await _extension_ids(pg, _market("Lukko Rauma vs. Tappara Tampere", source="kalshi")) == []

    async def test_the_scoring_gate_still_refuses_the_wrong_sport(self, pg):
        # Retrieval widened, acceptance did not: a SOCCER row that happens to
        # carry the prefix names is looked at and refused by the sport check
        # (the market is hockey).
        await _event(pg, 7, "Lukko", "Tappara", sport=LALIGA)
        assert await _extension_ids(pg, _market("Lukko Rauma vs. Tappara Tampere")) == [7]
        assert await _find(pg, _market("Lukko Rauma vs. Tappara Tampere")) is None
