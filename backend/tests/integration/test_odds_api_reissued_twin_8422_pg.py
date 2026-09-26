"""#8422 — the re-issued-id sweep's READ, WRITE and LIFT, against real Postgres.

The judgement is covered in `tests/test_odds_api_reissued_twin_8422.py`. What a
recording session cannot run is the SQL: the per-event `array_agg` over
`event_provider_anchors`, `make_interval(days => :n)` under asyncpg, the jsonb
`||` / `@>` append, the `- tag` lift, and the bank table's `to_regclass` probe.
So this drives `run_odds_api_reissued_twin_sweep` end to end in a private
schema (Postgres 14 on the lane VM as well as CI), with only the provider
replaced, and reads each outcome back from the rows.

The seed is production's Fleetwood block plus one filler population so the
floor holds; the #8755 tests add production's WNBA block and its `odds_snapshots`
lines (the `DISTINCT` / `CAST(numeric AS text)` read) and drive the one-off
repair script's by-id read on a ghost already `live`. Times are offsets from the real clock taken ONCE (the SQL reads
`now()`), never branched on (gotcha #44).
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8422 "
            "re-issued-id sweep gate (CI job: search-recall)"
        ),
    ),
]

_SCHEMA = "odds_api_reissued_twin_8422"
UTC = timezone.utc
EFL, EPL = 1295, 1296
GHOST, CANON = 15313977, 15314731
OLD, NEW = "95b553f793547e502d7124f78511f2cf", "29d04f0dddd5b30cd51de9acb7925795"
# #8755 — production's WNBA block: the ghost holds the NEWER id and one FanDuel
# line that Sunday's row also holds.
WNBA = 1297
FRIDAY, SUNDAY = 15318133, 15318132
F_ID, S_ID = "430c3ce5bf9f4327248452640a68bdae", "4a5f7b77830bdea66bedfe80560e7082"


class FakeService:
    def __init__(self, listed):
        self.listed = listed

    async def get_events(self, sport):
        return [{"id": i} for i in self.listed.get(sport, ())]


@pytest.fixture
async def pg(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.tasks.base as base
    import app.tasks.odds_api_reissued_twin_sweep as mod
    from app.models.models import (
        Base, Event, EventProviderAnchor, OddsSnapshot, Sport, Team, Venue,
    )

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
                tables=[
                    Sport.__table__, Team.__table__, Venue.__table__,
                    Event.__table__, EventProviderAnchor.__table__,
                    OddsSnapshot.__table__,
                ],
            )
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def session_in_schema():
        async with maker() as s:
            yield s

    monkeypatch.setattr(base, "get_task_session", session_in_schema)
    monkeypatch.delenv(mod.REISSUED_TWIN_SWEEP_DISABLED_ENV, raising=False)

    now = datetime.now(UTC)
    async with maker() as s:
        for sid, key in ((EFL, "soccer_england_efl_cup"), (EPL, "soccer_epl"), (WNBA, "basketball_wnba")):
            await s.execute(
                text("INSERT INTO sports (id, key, name, active) VALUES (:i, :k, :k, true)"),
                {"i": sid, "k": key},
            )
        seed = [
            (GHOST, EFL, "Fleetwood Town", "Arsenal", now + timedelta(days=33, hours=19), OLD, now - timedelta(days=8)),
            (CANON, EFL, "Fleetwood Town", "Arsenal", now + timedelta(days=33), NEW, now - timedelta(days=7)),
        ] + [
            (900000 + i, EPL, f"Home {i}", f"Away {i}", now + timedelta(days=3, minutes=i),
             f"filler{i}", now - timedelta(days=1))
            for i in range(mod.MIN_ROWS_FLOOR)
        ]
        for eid, sport, home, away, at, oid, seen in seed:
            await s.execute(
                text(
                    "INSERT INTO events (id, sport_id, external_id, home_team_name, "
                    "away_team_name, commence_time, status, event_tags) VALUES "
                    "(:id, :sp, :ext, :h, :a, :t, 'scheduled', CAST(:tags AS jsonb))"
                ),
                {"id": eid, "sp": sport, "ext": oid, "h": home, "a": away, "t": at,
                 "tags": '["audience:casual"]' if eid == GHOST else None},
            )
            await s.execute(
                text(
                    "INSERT INTO event_provider_anchors (event_id, source, source_id, "
                    "id_kind, first_seen_at) VALUES (:e, 'odds_api', :o, 'game', :f)"
                ),
                {"e": eid, "o": oid, "f": seen},
            )
        await s.commit()
        yield mod, s
        await s.rollback()
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
    await engine.dispose()


async def _tags(s, eid):
    await s.commit()
    return (await s.execute(text("SELECT event_tags FROM events WHERE id = :i"), {"i": eid})).scalar()


async def test_the_ghost_is_tagged_banked_idempotent_and_lifted_when_relisted(pg):
    mod, s = pg

    first = await mod.run_odds_api_reissued_twin_sweep(service=FakeService({"soccer_england_efl_cup": {NEW}}))
    assert first["terminal"] == "complete", first
    assert first["rows_read"] == mod.MIN_ROWS_FLOOR + 2 and first["tagged"] == 1
    tags = await _tags(s, GHOST)
    assert f"provenance:duplicate-of:{CANON}" in tags and "audience:casual" in tags
    assert await _tags(s, CANON) is None

    banked = (await s.execute(text(f"SELECT canonical_id, ghost_odds_api_ids, old_tags FROM {mod.BAK_TABLE}"))).one()
    assert banked.canonical_id == CANON and banked.ghost_odds_api_ids == OLD
    assert "duplicate-of" not in banked.old_tags

    # Idempotent in the database: a second pass plans nothing and appends nothing.
    second = await mod.run_odds_api_reissued_twin_sweep(service=FakeService({"soccer_england_efl_cup": {NEW}}))
    assert second["terminal"] == "complete" and second["tagged"] == 0 and second["labels_held"] == 1
    assert (await _tags(s, GHOST)).count(f"provenance:duplicate-of:{CANON}") == 1

    # The provider lists the old id again: the label's one fact is gone.
    third = await mod.run_odds_api_reissued_twin_sweep(
        service=FakeService({"soccer_england_efl_cup": {OLD, NEW}})
    )
    assert third["lifted"] == 1, third
    assert await _tags(s, GHOST) == ["audience:casual"]


async def test_both_ids_listed_writes_nothing(pg):
    mod, s = pg
    out = await mod.run_odds_api_reissued_twin_sweep(
        service=FakeService({"soccer_england_efl_cup": {OLD, NEW}})
    )
    assert out["terminal"] == "complete" and out["tagged"] == 0
    assert out["refusal_samples"][0]["reason"] == "all_listed"
    assert await _tags(s, GHOST) == ["audience:casual"]


async def test_the_restore_script_removes_only_its_element(pg, capsys):
    mod, s = pg
    from scripts.restore_8422_odds_api_reissued_tags import run as restore

    await mod.run_odds_api_reissued_twin_sweep(service=FakeService({"soccer_england_efl_cup": {NEW}}))
    assert await restore(apply=True, only=[999]) == 2  # an unbanked id aborts
    assert await restore(apply=True, only=None) == 0
    assert await _tags(s, GHOST) == ["audience:casual"]


async def _seed_wnba(s, *, friday_at, friday_status, friday_spread):
    """Sunday (older id, listed) and Friday (newer id) with their book lines."""
    now = datetime.now(UTC)
    for eid, oid, at, status, seen in (
        (SUNDAY, S_ID, now + timedelta(days=2), "scheduled", now - timedelta(days=2, minutes=2)),
        (FRIDAY, F_ID, friday_at, friday_status, now - timedelta(days=2)),
    ):
        await s.execute(
            text(
                "INSERT INTO events (id, sport_id, external_id, home_team_name, away_team_name, "
                "commence_time, status) VALUES (:id, :sp, :ext, 'Minnesota Lynx', "
                "'New York Liberty', :t, :st)"
            ),
            {"id": eid, "sp": WNBA, "ext": oid, "t": at, "st": status},
        )
        await s.execute(
            text(
                "INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind, "
                "first_seen_at) VALUES (:e, 'odds_api', :o, 'game', :f)"
            ),
            {"e": eid, "o": oid, "f": seen},
        )
    snaps = [
        (SUNDAY, "draftkings", -270, 220, -6.5, 173.5),
        (SUNDAY, "fanduel", -300, 235, -7.5, 173.5),
        (SUNDAY, "fanduel", -300, 235, -7.5, 173.5),  # repeats collapse under DISTINCT
        (SUNDAY, "fanduel", -300, 235, None, None),
        (FRIDAY, "fanduel", -300, 235, friday_spread, 173.5),
        (FRIDAY, "fanduel", -300, 235, None, None),  # a partial capture is ignored
    ]
    for i, (eid, book, hml, aml, spread, total) in enumerate(snaps):
        await s.execute(
            text(
                "INSERT INTO odds_snapshots (event_id, captured_at, bookmaker, home_moneyline, "
                "away_moneyline, home_spread, over_under, reading_count) "
                "VALUES (:e, :c, :b, :h, :a, :sp, :t, 1)"
            ),
            {"e": eid, "c": now - timedelta(days=2, minutes=i), "b": book, "h": hml, "a": aml,
             "sp": spread, "t": total},
        )
    await s.commit()


async def test_a_newer_id_ghost_whose_line_moved_is_tagged_by_the_sweep_8755(pg):
    mod, s = pg
    await _seed_wnba(s, friday_at=datetime.now(UTC) + timedelta(days=1),
                     friday_status="scheduled", friday_spread=-7.5)

    lines = await mod.load_book_lines(s, [SUNDAY, FRIDAY])
    assert lines[FRIDAY] == frozenset({("fanduel", -300, 235, "-7.5", "173.5")})
    assert lines[SUNDAY] == frozenset({
        ("fanduel", -300, 235, "-7.5", "173.5"), ("draftkings", -270, 220, "-6.5", "173.5"),
    })

    out = await mod.run_odds_api_reissued_twin_sweep(
        service=FakeService({"soccer_england_efl_cup": {NEW}, "basketball_wnba": {S_ID}})
    )
    assert out["terminal"] == "complete" and out["tagged"] == 2, out
    assert f"provenance:duplicate-of:{SUNDAY}" in await _tags(s, FRIDAY)
    assert not await _tags(s, SUNDAY)


async def test_a_newer_id_ghost_whose_line_differs_is_refused_8755(pg):
    mod, s = pg
    await _seed_wnba(s, friday_at=datetime.now(UTC) + timedelta(days=1),
                     friday_status="scheduled", friday_spread=-8.5)
    out = await mod.run_odds_api_reissued_twin_sweep(
        service=FakeService({"soccer_england_efl_cup": {NEW}, "basketball_wnba": {S_ID}})
    )
    assert out["tagged"] == 1  # Fleetwood only
    assert {"event_ids": [SUNDAY, FRIDAY], "sport_key": "basketball_wnba",
            "reason": f"ghost_{FRIDAY}_is_the_newer_id"} in out["refusal_samples"]
    assert not await _tags(s, FRIDAY)


async def test_the_repair_labels_a_live_ghost_the_sweep_cannot_see_and_restore_undoes_it(pg):
    mod, s = pg
    from scripts.repair_8755_newer_id_twin import run as repair
    from scripts.restore_8422_odds_api_reissued_tags import run as restore

    await _seed_wnba(s, friday_at=datetime.now(UTC) - timedelta(minutes=85),
                     friday_status="live", friday_spread=-7.5)
    listed = FakeService({"basketball_wnba": {S_ID}})

    # The sweep's window cannot see a live row past its start.
    rows, _ = await mod.load_rows(s, lookahead=mod.DEFAULT_LOOKAHEAD_DAYS)
    assert FRIDAY not in {r.event_id for r in rows}

    assert await repair(ghost=FRIDAY, canonical=SUNDAY, apply=False, service=listed) == 0
    assert not await _tags(s, FRIDAY)  # the dry run wrote nothing
    assert await repair(ghost=FRIDAY, canonical=SUNDAY, apply=True, service=listed) == 0
    assert await _tags(s, FRIDAY) == [f"provenance:duplicate-of:{SUNDAY}"]
    banked = (await s.execute(
        text(f"SELECT canonical_id, ghost_odds_api_ids FROM {mod.BAK_TABLE} WHERE event_id = :e"),
        {"e": FRIDAY},
    )).one()
    assert (banked.canonical_id, banked.ghost_odds_api_ids) == (SUNDAY, F_ID)
    assert await repair(ghost=FRIDAY, canonical=SUNDAY, apply=True, service=listed) == 0  # no-op

    assert await restore(apply=True, only=[FRIDAY]) == 0
    assert await _tags(s, FRIDAY) == []
