"""#5355 — a DataGolf opening first read after the tournament started is not a forecast.

THE DEFECT
----------
The accuracy curve prices a DataGolf outcome at
``COALESCE(calibration_probability, opening_probability)``, and Part A1-dg copies
``opening_probability`` into ``calibration_probability`` for every resolved
DataGolf row. Neither asks WHEN the opening was read. The in-play beat
(``_poll_datagolf_live``) creates any outcome it has not seen before with
``opening_probability`` = the IN-PLAY probability, so a player first written on
Friday afternoon carries a mid-tournament reading as his "forecast", and the curve
scored it. A writer-only fix would not reach it: the read path's COALESCE scores
the same opening when ``calibration_probability`` is NULL.

THE EVIDENCE THE RULE READS
---------------------------
DataGolf never stamps ``opening_captured_at``. What exists is the outcome's
``datagolf_model`` snapshots, written in the same pass that creates the outcome,
and the market's ``commence_time`` — 00:00 UTC on DataGolf's start date, written
once at market creation. That timestamp is not the first tee time. It is the
boundary the in-play writer itself refuses to cross (``commence_time > now`` →
skip, #191, 2026-07-14), so a ``datagolf_model`` snapshot captured strictly
before it can only have come from the pre-tournament poll. An opening is proved
pre-start when such a snapshot carries the opening's own value. Anything else is
UNKNOWN timing and is withheld, never assumed to be "now" and never assumed fine.

Only rows whose curve price IS the opening are judged (``price_moved`` false).
A row Part A/A2 moved to a pre-start closing line keeps its price untouched: the
rule does not change ``price_moved`` or any other price rule.

WHY THIS IS A POSTGRES TEST
---------------------------
The contract is which ROWS survive a correlated snapshot predicate inside the
canonical population chain. This executes the REAL ``_calibration_population_ctes``
and the REAL coverage-bridge rung predicates against seeded rows.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and NAMED IN ``ci.yml``: a PG-gated file no
workflow step invokes skips silently while pytest still exits 0.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #5355 contract",
    ),
]

DG_MID = 535501
NO_COMMENCE_MID = 535502
POLY_MID = 535503
ALL_MIDS = (DG_MID, NO_COMMENCE_MID, POLY_MID)

# Fixed once per run: offset FIRST, never branch on the clock (gotcha #44).
NOW = datetime.now(timezone.utc).replace(microsecond=0)
COMMENCE = NOW - timedelta(days=10)
PRE = COMMENCE - timedelta(days=3)
LATE_PRE = COMMENCE - timedelta(hours=1)
POST = COMMENCE + timedelta(days=1)

# (name, opening, calibration_probability, is_winner, snapshots, published?)
# snapshots: (bookmaker, probability, captured_at). Prices are distinct and inside
# 0.005..0.98 so the multi arm's mode/tail heuristics drop nothing; the board is a
# make-the-cut market (not a partition), so one withheld row cannot take its
# neighbours down with it through field completeness.
BOARD = [
    # Healthy pre-tournament forecasts, cp = opening (what A1-dg writes).
    ("Pre A", 0.91, 0.91, True, [("datagolf_model", 0.91, PRE)], True),
    ("Pre B", 0.84, 0.84, True, [("datagolf_model", 0.84, PRE)], True),
    ("Pre C", 0.72, 0.72, True, [("datagolf_model", 0.72, PRE)], True),
    ("Pre D", 0.36, 0.36, False, [("datagolf_model", 0.36, PRE)], True),
    (
        "Pre E then in-play",
        0.24,
        0.24,
        False,
        # Later in-play readings do not taint a pre-start opening.
        [("datagolf_model", 0.24, PRE), ("datagolf_model", 0.05, POST)],
        True,
    ),
    # cp NULL: the read-side COALESCE falls back to a KNOWN-VALID opening.
    ("Pre null cp", 0.66, None, True, [("datagolf_model", 0.66, PRE)], True),
    # Part A/A2 moved the price to a pre-start closing line: out of scope, kept.
    (
        "Moved to closing line",
        0.30,
        0.42,
        False,
        [("datagolf_model", 0.30, PRE), ("datagolf_model", 0.42, LATE_PRE)],
        True,
    ),
    # THE DEFECT: first read by the in-play beat after the start.
    ("Post-start opening", 0.61, 0.61, True, [("datagolf_model", 0.61, POST)], False),
    # Same, before A1-dg ran: only the read path's COALESCE scores it.
    ("Post-start null cp", 0.47, None, False, [("datagolf_model", 0.47, POST)], False),
    # Unknown timing: no snapshot at all.
    ("No snapshot", 0.55, 0.55, False, [], False),
    # Different source: a pre-start snapshot that is not DataGolf's model.
    ("Other bookmaker only", 0.13, 0.13, False, [("kalshi", 0.13, PRE)], False),
    # A pre-start snapshot exists but it is not the opening value.
    (
        "Pre-start reading is not the opening",
        0.58,
        0.58,
        False,
        [("datagolf_model", 0.20, PRE), ("datagolf_model", 0.58, POST)],
        False,
    ),
    # Strictly before: a reading AT the boundary is the in-play writer's.
    ("At the boundary", 0.77, 0.77, True, [("datagolf_model", 0.77, COMMENCE)], False),
]

WITHHELD = {name for name, *_rest, published in BOARD if not published}
PUBLISHED = {name for name, *_rest, published in BOARD if published}

# A DataGolf market with no commence_time: its readings cannot be placed before
# the start, so its whole board is unknown timing.
NO_COMMENCE_BOARD = [
    ("NC A", 0.91, True),
    ("NC B", 0.72, True),
    ("NC C", 0.36, False),
    ("NC D", 0.24, False),
]

# A non-DataGolf golf market whose only readings come after its commence_time:
# the rule is DataGolf's and must not touch another source.
POLY_BOARD = [
    ("Poly A", 0.91, True),
    ("Poly B", 0.72, True),
    ("Poly C", 0.36, False),
    ("Poly D", 0.24, False),
]


async def _seed_market(session, mid, *, source, commence):
    await session.execute(
        text(
            "INSERT INTO futures_markets (id, external_id, name, source, status, "
            "category, mutually_exclusive, market_type, llm_sport_category, volume, "
            "commence_time, resolution_date) VALUES "
            "(:id, :xid, :nm, :src, 'resolved', 'placement', false, "
            "'participation', 'golf', 100, :ct, :rd)"
        ),
        {
            "id": mid,
            "xid": f"{source}:pga:5355{mid}:make_cut",
            "nm": f"Test Open {mid} - Make the Cut",
            "src": source,
            "ct": commence,
            "rd": NOW - timedelta(days=7),
        },
    )


async def _seed_outcome(session, oid, mid, name, opening, cp, winner, snapshots):
    await session.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
            "opening_probability, calibration_probability, is_winner, "
            "resolution_source, volume) VALUES "
            "(:id, :mid, :xid, :nm, :op, :cp, :win, 'leaderboard', 10)"
        ),
        {
            "id": oid,
            "mid": mid,
            "xid": f"dg_{oid}",
            "nm": name,
            "op": opening,
            "cp": cp,
            "win": winner,
        },
    )
    for bookmaker, prob, captured_at in snapshots:
        await session.execute(
            text(
                "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, "
                "probability, reading_count, last_price, yes_bid, yes_ask, "
                "captured_at) VALUES "
                "(:oid, :bk, :p, 1, :p, :p, :p, :at)"
            ),
            {"oid": oid, "bk": bookmaker, "p": prob, "at": captured_at},
        )


async def _clear(session):
    for mid in ALL_MIDS:
        await session.execute(
            text(
                "DELETE FROM futures_odds_snapshots WHERE outcome_id IN "
                "(SELECT id FROM futures_outcomes WHERE market_id = :mid)"
            ),
            {"mid": mid},
        )
        await session.execute(
            text("DELETE FROM futures_outcomes WHERE market_id = :mid"), {"mid": mid}
        )
        await session.execute(text("DELETE FROM futures_markets WHERE id = :mid"), {"mid": mid})


@pytest.fixture
async def session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await _clear(s)
        await _seed_market(s, DG_MID, source="datagolf", commence=COMMENCE)
        for idx, (name, op, cp, win, snaps, _pub) in enumerate(BOARD):
            await _seed_outcome(s, DG_MID * 1000 + idx, DG_MID, name, op, cp, win, snaps)
        await _seed_market(s, NO_COMMENCE_MID, source="datagolf", commence=None)
        for idx, (name, p, win) in enumerate(NO_COMMENCE_BOARD):
            await _seed_outcome(
                s,
                NO_COMMENCE_MID * 1000 + idx,
                NO_COMMENCE_MID,
                name,
                p,
                p,
                win,
                [("datagolf_model", p, PRE)],
            )
        await _seed_market(s, POLY_MID, source="polymarket", commence=COMMENCE)
        for idx, (name, p, win) in enumerate(POLY_BOARD):
            await _seed_outcome(
                s, POLY_MID * 1000 + idx, POLY_MID, name, p, p, win, [("polymarket", p, POST)]
            )
        await s.commit()
        yield s
        await _clear(s)
        await s.commit()
    await engine.dispose()


async def _published(session, mid):
    from app.tasks.precompute_calibration import _calibration_population_ctes

    rows = await session.execute(
        text(
            "WITH "
            + _calibration_population_ctes()
            + " SELECT outcome_name, raw_cp, price_moved FROM deduped WHERE market_id = :mid"
        ),
        {"mid": mid},
    )
    return {r.outcome_name: r for r in rows.all()}


async def test_healthy_pre_start_forecasts_still_publish(session):
    """NON-VACUITY FIRST: an empty published set is also what a broken fixture
    yields, so the withheld assertions mean nothing until the controls publish."""
    rows = await _published(session, DG_MID)
    missing = PUBLISHED - set(rows)
    assert not missing, f"pre-start DataGolf forecasts were withheld: {sorted(missing)}"
    winners = {n for n, *_r, win, _s, pub in BOARD if pub and win}
    losers = {n for n, *_r, win, _s, pub in BOARD if pub and not win}
    assert winners and losers and (winners | losers) <= set(rows)


async def test_the_prices_of_the_survivors_are_unchanged(session):
    """The rule removes rows; it never re-prices one. The cp-NULL row still reads
    its opening through the COALESCE, and the moved row keeps its closing line."""
    rows = await _published(session, DG_MID)
    assert float(rows["Pre null cp"].raw_cp) == pytest.approx(0.66)
    assert rows["Pre null cp"].price_moved is False
    assert float(rows["Moved to closing line"].raw_cp) == pytest.approx(0.42)
    assert rows["Moved to closing line"].price_moved is True
    assert float(rows["Pre E then in-play"].raw_cp) == pytest.approx(0.24)


async def test_an_opening_without_pre_start_evidence_is_not_scored(session):
    rows = await _published(session, DG_MID)
    leaked = WITHHELD & set(rows)
    assert not leaked, (
        "a DataGolf opening with no pre-start datagolf_model reading of its own "
        f"value reached the accuracy curve: {sorted(leaked)}"
    )


async def test_a_market_with_no_start_time_is_unknown_timing(session):
    rows = await _published(session, NO_COMMENCE_MID)
    assert rows == {}, (
        "a DataGolf market with no commence_time cannot place any reading before "
        f"the start, yet these were scored: {sorted(rows)}"
    )


async def test_another_source_is_untouched(session):
    """The rule keys on DataGolf's own writer boundary. A Polymarket golf market
    whose readings all postdate its commence_time is not this rule's business."""
    rows = await _published(session, POLY_MID)
    assert set(rows) == {n for n, *_r in POLY_BOARD}, sorted(rows)


async def test_withheld_rows_are_accounted_on_their_own_rung(session):
    """The coverage bridge's catch-all is where a new ``deduped`` filter lands
    silently. Every withheld row must be claimed by the new rung, using the
    production rung predicates verbatim (first match wins)."""
    from app.tasks.precompute_calibration import (
        _COVERAGE_RUNG_PREDICATES,
        _calibration_population_ctes,
        _coverage_universe_cte,
    )

    branches = " ".join(
        f"WHEN {sql} THEN '{key}'" for key, sql in _COVERAGE_RUNG_PREDICATES if sql
    )
    terminal = _COVERAGE_RUNG_PREDICATES[-1][0]
    rows = await session.execute(
        text(
            "WITH "
            + _calibration_population_ctes()
            + ","
            + _coverage_universe_cte(chunk_scoped=False)
            + f"""
            SELECT fo.name AS outcome_name,
                CASE {branches} ELSE '{terminal}' END AS rung
            FROM coverage_universe cu
            JOIN futures_outcomes fo ON fo.id = cu.outcome_id
            LEFT JOIN market_info mi ON mi.market_id = cu.market_id
            LEFT JOIN normalized n ON n.outcome_id = cu.outcome_id
            LEFT JOIN deduped d ON d.outcome_id = cu.outcome_id
            LEFT JOIN market_result_shape mrs_cov ON mrs_cov.market_id = cu.market_id
            WHERE cu.market_id IN (:a, :b)
            """
        ),
        {"a": DG_MID, "b": NO_COMMENCE_MID},
    )
    rung_by_name = {r.outcome_name: r.rung for r in rows.all()}
    expected = WITHHELD | {n for n, *_r in NO_COMMENCE_BOARD}
    wrong = {
        n: rung_by_name.get(n)
        for n in expected
        if rung_by_name.get(n) != "datagolf_opening_after_start"
    }
    assert not wrong, f"withheld rows claimed by another rung: {wrong}"
    for name in PUBLISHED:
        assert rung_by_name.get(name) == "plotted_on_curve", (name, rung_by_name.get(name))
