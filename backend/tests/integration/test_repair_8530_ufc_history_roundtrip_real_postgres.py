"""#8530 step 3's apply/restore round trip, executed against a REAL PostgreSQL.

`scripts/repair_8530_ufc_flipped_history.py` swaps home/away on the UFC Fight
Night 2026-09-26 chart history under D51(b), which permits it only because it
backs up first and ships a one-command restore. What that grant rests on is
decided by the server, not by the Python around it:

1. **`IS NOT DISTINCT FROM` over a row tuple with genuine NULLs.** Most sportsbook
   rows have no spread, so `(home_spread, …)` carries NULLs; with `=` the swap
   would silently match nothing. It is also the whole idempotency claim: a
   re-run must write zero rows.
2. **`UPDATE … FROM` reading the BACKUP row, not the half-written live row.** A
   swap written as `SET home = away, away = home` over the live row is the
   classic self-referencing trap; the script reads both sides from `b`.
3. **`= ANY(:ids)` binding a Python list under asyncpg** with no explicit cast.
4. **The restore sparing a row written after the repair.**

The corpus, each row with the wrong answer it catches:

* 15314293 (home favoured): a pre-flip row (outside the window, must not move),
  two inverted rows inside it (one carrying a spread, so NULL and non-NULL
  tuples both pass through the swap), and the post-fix row (must not move).
* 15314294 (away favoured): one inverted row, the opposite side.
* 15314291 Kalshi: OK, FLIP, NO_EVIDENCE and UNEXPLAINED rows. The alternating
  right/wrong shape is the reason Kalshi is judged per row, not by window.
* 15314294 Kalshi: a FLIP whose outcome names the AWAY fighter (the `1 - yes` arm).
* A control event outside the six, with an inverted-looking row in the window.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8530 history "
            "round trip (CI job `search-recall` provides one)"
        ),
    ),
]

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "scripts"
    / "repair_8530_ufc_flipped_history.py"
)


def _load_repair():
    spec = importlib.util.spec_from_file_location("repair_8530", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load_repair()

_UTC = timezone.utc
_PRE = datetime(2026, 9, 20, 5, 0, tzinfo=_UTC)        # before the feed flipped
_IN_1 = datetime(2026, 9, 21, 8, 36, 7, tzinfo=_UTC)   # the flip pass
_IN_2 = datetime(2026, 9, 24, 20, 6, 12, tzinfo=_UTC)
_POST = datetime(2026, 9, 25, 5, 37, 14, tzinfo=_UTC)  # #8534's first pass
CONTROL_EVENT = 85309999

#: odds row key -> (event, captured_at, home_ml, away_ml, home_p, away_p, spread,
#: home_spread_odds, away_spread_odds, proj_home, proj_away, over_under)
_ODDS = {
    "vie_pre":    (15314293, _PRE,  -110, -110, 0.5000, 0.5000, None, None, None, None, None, None),
    "vie_in":     (15314293, _IN_2,  136, -162, 0.4066, 0.5934, None, None, None, None, None, None),
    "vie_spread": (15314293, _IN_1,  110, -130, 0.4545, 0.5455, 1.5, -150, 120, 1.2, 1.8, 2.5),
    "vie_post":   (15314293, _POST, -162,  136, 0.5934, 0.4066, None, None, None, None, None, None),
    "dem_in":     (15314294, _IN_2, -950,  625, 0.8677, 0.1323, None, None, None, None, None, None),
    "control":    (CONTROL_EVENT, _IN_2, 136, -162, 0.4066, 0.5934, None, None, None, None, None, None),
}
#: What each odds row must read after --apply, from a literal (never re-derived).
_ODDS_AFTER = {
    "vie_pre":    (-110, -110, 0.5000, 0.5000, None, None, None, None, None),
    "vie_in":     (-162,  136, 0.5934, 0.4066, None, None, None, None, None),
    "vie_spread": (-130,  110, 0.5455, 0.4545, -1.5, 120, -150, 1.8, 1.2),
    "vie_post":   (-162,  136, 0.5934, 0.4066, None, None, None, None, None),
    "dem_in":     ( 625, -950, 0.1323, 0.8677, None, None, None, None, None),
    "control":    ( 136, -162, 0.4066, 0.5934, None, None, None, None, None),
}

_JACKSON = "Montel Jackson"
#: kalshi row key -> (event, captured_at, stored home, game_state)
_KALSHI = {
    "jac_ok":    (15314291, _IN_1, 0.6550, {"outcome_name": _JACKSON, "yes_probability": 0.655}),
    "jac_flip":  (15314291, _IN_2, 0.3450, {"outcome_name": _JACKSON, "yes_probability": 0.655}),
    "jac_noev":  (15314291, _IN_2, 0.3450, {"market_id": 61620872}),
    "jac_odd":   (15314291, _IN_2, 0.5000, {"outcome_name": _JACKSON, "yes_probability": 0.655}),
    "jau_away":  (15314294, _IN_2, 0.8750, {"outcome_name": "Yazmin Jauregui", "yes_probability": 0.875}),
}
_KALSHI_AFTER = {"jac_ok": 0.6550, "jac_flip": 0.6550, "jac_noev": 0.3450,
                 "jac_odd": 0.5000, "jau_away": 0.1250}

_NAMES = {
    15314291: ("Montel Jackson", "Ricky Simon"),
    15314293: ("Rodolfo Vieira", "Robert Bryczek"),
    15314294: ("Vanessa Demopoulos", "Yazmin Jauregui"),
    CONTROL_EVENT: ("Control Home", "Control Away"),
}

_ODDS_COLS = ("home_moneyline, away_moneyline, home_win_probability, away_win_probability, "
              "home_spread, home_spread_odds, away_spread_odds, projected_home_score, "
              "projected_away_score")


@pytest.fixture
async def pg_engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        for bak in (repair.BAK_ODDS, repair.BAK_WP):
            await conn.execute(text(f"DROP TABLE IF EXISTS {bak}"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        for bak in (repair.BAK_ODDS, repair.BAK_WP):
            await conn.execute(text(f"DROP TABLE IF EXISTS {bak}"))
    await engine.dispose()


async def _seed(s, odds: dict, kalshi: dict) -> dict:
    from app.models.models import Event, OddsSnapshot, Sport, WinProbSnapshot

    sport = Sport(key="mma_mixed_martial_arts", name="MMA")
    s.add(sport)
    await s.flush()
    for eid, (home, away) in _NAMES.items():
        s.add(Event(id=eid, sport_id=sport.id, home_team_name=home, away_team_name=away,
                    commence_time=datetime(2026, 9, 26, 23, 15, tzinfo=_UTC)))
    await s.flush()
    ids = {}
    for key, (eid, at, hml, aml, hp, ap, sp, hso, aso, ph, pa, ou) in odds.items():
        row = OddsSnapshot(event_id=eid, captured_at=at, bookmaker="draftkings",
                           home_moneyline=hml, away_moneyline=aml,
                           home_win_probability=hp, away_win_probability=ap,
                           home_spread=sp, home_spread_odds=hso, away_spread_odds=aso,
                           projected_home_score=ph, projected_away_score=pa,
                           over_under=ou, reading_count=1)
        s.add(row)
        await s.flush()
        ids[key] = row.id
    for key, (eid, at, home, gs) in kalshi.items():
        row = WinProbSnapshot(event_id=eid, source="kalshi", captured_at=at,
                              home_win_probability=home, away_win_probability=round(1 - home, 4),
                              game_state=gs, reading_count=1)
        s.add(row)
        await s.flush()
        ids[key] = row.id
    await s.commit()
    return ids


@pytest.fixture
async def session(pg_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with maker() as s:
        s.info["ids"] = await _seed(s, _ODDS, _KALSHI)
        yield s


def _num(v):
    return None if v is None else (float(v) if not isinstance(v, int) else v)


async def _odds(s, ids: dict) -> dict:
    out = {}
    for key in _ODDS:
        row = (await s.execute(text(f"SELECT {_ODDS_COLS} FROM odds_snapshots WHERE id = :i"),
                               {"i": ids[key]})).one()
        out[key] = tuple(_num(v) for v in row)
    return out


async def _kalshi(s, ids: dict) -> dict:
    out = {}
    for key in _KALSHI:
        v = (await s.execute(text("SELECT home_win_probability FROM win_prob_snapshots WHERE id = :i"),
                             {"i": ids[key]})).scalar_one()
        out[key] = float(v)
    return out


async def _exists(s, table: str) -> bool:
    return bool((await s.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": table})).scalar())


# ── the corpus can tell the wrong answers apart ─────────────────────────────


async def test_the_seeded_corpus_can_distinguish_the_wrong_answers(session):
    before = await _odds(session, session.info["ids"])
    changed = {k for k in _ODDS if before[k] != _ODDS_AFTER[k]}
    unchanged = set(_ODDS) - changed
    assert changed == {"vie_in", "vie_spread", "dem_in"}
    assert unchanged == {"vie_pre", "vie_post", "control"}
    assert before["vie_spread"][4] is not None and before["vie_in"][4] is None


async def test_plan_reads_the_window_and_each_kalshi_rows_own_evidence(session):
    plan = await repair.build_plan(session)
    ids = session.info["ids"]
    assert sorted(plan["odds_ids"]) == sorted([ids["vie_in"], ids["vie_spread"], ids["dem_in"]])
    assert sorted(plan["kalshi_ids"]) == sorted([ids["jac_flip"], ids["jau_away"]])
    assert {r["id"] for r in plan["kalshi"]["OK"]} == {ids["jac_ok"]}
    assert {r["id"] for r in plan["kalshi"]["NO_EVIDENCE"]} == {ids["jac_noev"]}
    assert {r["id"] for r in plan["kalshi"]["UNEXPLAINED"]} == {ids["jac_odd"]}
    assert repair.apply_refusal(plan) is None


async def test_plan_only_writes_nothing(session):
    ids = session.info["ids"]
    before = await _odds(session, ids), await _kalshi(session, ids)
    assert await repair.repair(session, apply=False) == 0
    assert (await _odds(session, ids), await _kalshi(session, ids)) == before
    assert not await _exists(session, repair.BAK_ODDS)


async def test_apply_swaps_exactly_the_planned_rows_and_backs_them_up(session):
    ids = session.info["ids"]
    original = await _odds(session, ids)
    assert await repair.repair(session, apply=True) == 0

    assert await _odds(session, ids) == _ODDS_AFTER
    assert await _kalshi(session, ids) == _KALSHI_AFTER

    bak = (await session.execute(text(
        f"SELECT id, home_moneyline FROM {repair.BAK_ODDS} ORDER BY id"))).all()
    assert {i for i, _ in bak} == {ids["vie_in"], ids["vie_spread"], ids["dem_in"]}
    assert {i: ml for i, ml in bak}[ids["dem_in"]] == original["dem_in"][0] == -950
    wp_bak = (await session.execute(text(f"SELECT id FROM {repair.BAK_WP}"))).scalars().all()
    assert set(wp_bak) == {ids["jac_flip"], ids["jau_away"]}


async def test_a_second_apply_writes_nothing(session):
    ids = session.info["ids"]
    assert await repair.repair(session, apply=True) == 0
    plan = await repair.build_plan(session)
    assert {r["id"] for r in plan["odds"]["ALREADY"]} == {ids["vie_in"], ids["vie_spread"], ids["dem_in"]}
    assert plan["odds_ids"] == [] and plan["kalshi_ids"] == []
    assert await repair.repair(session, apply=True) == 0
    assert await _odds(session, ids) == _ODDS_AFTER
    assert await _kalshi(session, ids) == _KALSHI_AFTER


async def test_restore_puts_back_every_row_except_one_written_since(session):
    ids = session.info["ids"]
    original_odds, original_k = await _odds(session, ids), await _kalshi(session, ids)
    assert await repair.repair(session, apply=True) == 0

    # A later writer touches one repaired row. The restore must spare it.
    await session.execute(text(
        "UPDATE win_prob_snapshots SET home_win_probability = 0.7000, "
        "away_win_probability = 0.3000 WHERE id = :i"), {"i": ids["jau_away"]})
    await session.commit()

    assert await repair.restore(session) == 0
    assert await _odds(session, ids) == original_odds
    after_k = await _kalshi(session, ids)
    assert after_k["jau_away"] == 0.7000
    assert {k: v for k, v in after_k.items() if k != "jau_away"} == \
        {k: v for k, v in original_k.items() if k != "jau_away"}


async def test_a_window_row_already_on_the_favourites_side_refuses_the_whole_apply(pg_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    contradicting = dict(_ODDS)
    contradicting["vie_right"] = (15314293, _IN_2, -162, 136, 0.5934, 0.4066,
                                  None, None, None, None, None, None)
    maker = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with maker() as s:
        ids = await _seed(s, contradicting, _KALSHI)
        plan = await repair.build_plan(s)
        assert {r["id"] for r in plan["odds"]["UNEXPLAINED"]} == {ids["vie_right"]}
        assert await repair.repair(s, apply=True) == 2
        assert not await _exists(s, repair.BAK_ODDS)
        row = (await s.execute(text("SELECT home_moneyline FROM odds_snapshots WHERE id = :i"),
                               {"i": ids["dem_in"]})).scalar_one()
        assert row == -950
