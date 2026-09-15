"""#6211 — isolate the predicate that censors the published DataGolf population.

Seeds DataGolf tournaments — the five markets ``app/tasks/datagolf.py`` actually
writes — into a real Postgres and runs the REAL ``_calibration_population_ctes()``
over them, reporting the survivor count and win rate at every stage plus the
first ``deduped`` reason each dropped row trips.

It runs a LADDER of variants, each adding one production-ism measured off
production on 2026-09-15, so the variant where the population collapses NAMES the
mechanism rather than asserting it:

    v0_clean        every player graded ``leaderboard``, no market_type
    v1_market_type  + market_type: win='field'/mex, the rest 'participation'
    v2_dnp          + the 40% of rows production grades ``did_not_play``
    v3_cal_prob     + the calibration_probability shape (NULL / moved)

Production shape this mirrors (``/api/admin/db-query``, 2026-09-15):

    kind      mtype          mex    markets  outcomes  cal_null  moved  elig    w
    make_cut  participation  False       68     11450      2142   4107  6522  4263
    top_20    participation  False       68     11391      1237   4618  6476  1481
    top_10    participation  False       68     11376      1522   4572  6476   755
    top_5     participation  False       68     11371      1778   4532  6476   398
    win       field          True        68     11365      2168   4283  6476    68

Run:
    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://bain@localhost:5432/bl_6211_datagolf \
        python3 artifacts-calibration-1310/repro_datagolf_population.py
"""

from __future__ import annotations

import asyncio
import os
import random
import sys

from sqlalchemy import text

DB_URL = os.environ["SEARCH_TEST_DATABASE_URL"]

BASE_MID = 962000
FIELD_N = 167  # production: ~11,400 outcomes over 68 markets
N_TOURNAMENTS = 3
CUT_LINE = 75
DNP_RATE = 0.40  # production: 16,269 did_not_play of 40,051
CAL_NULL_RATE = 0.15
CAL_MOVED_RATE = 0.38

KINDS = ("win", "top_5", "top_10", "top_20", "make_cut")


def _probs(kind: str) -> list[float]:
    if kind == "make_cut":
        return [round(0.93 - (0.81 * i / (FIELD_N - 1)), 4) for i in range(FIELD_N)]
    scale = {"win": 0.080, "top_5": 0.30, "top_10": 0.45, "top_20": 0.62}[kind]
    return [round(max(scale * (0.955**i), 0.0005), 4) for i in range(FIELD_N)]


def _won(kind: str, i: int) -> bool:
    return {
        "win": i == 0,
        "top_5": i < 5,
        "top_10": i < 10,
        "top_20": i < 20,
        "make_cut": i < CUT_LINE,
    }[kind]


async def _seed(session, variant: str):
    rng = random.Random(6211)
    await session.execute(text("DELETE FROM futures_odds_snapshots"))
    await session.execute(text("DELETE FROM futures_outcomes"))
    await session.execute(text("DELETE FROM futures_markets"))

    for t in range(N_TOURNAMENTS):
        # Which players withdrew — the same set across a tournament's five
        # markets, as a real withdrawal is.
        dnp = set()
        if variant in ("v2_dnp", "v3_cal_prob"):
            dnp = {
                i
                for i in range(FIELD_N)
                # never the champion: a player who did not play cannot win
                if i != 0 and rng.random() < DNP_RATE
            }
        for k, kind in enumerate(KINDS):
            mid = BASE_MID + t * 10 + k
            if variant == "v0_clean":
                mtype, mex = None, (kind == "win")
            else:
                mtype = "field" if kind == "win" else "participation"
                mex = kind == "win"
            await session.execute(
                text(
                    "INSERT INTO futures_markets (id, external_id, name, source, "
                    "status, category, mutually_exclusive, market_type, "
                    "llm_sport_category, volume, resolution_date) VALUES "
                    "(:id, :xid, :nm, 'datagolf', 'resolved', :cat, :mex, :mt, "
                    "'golf', 100, NOW() - INTERVAL '7 days')"
                ),
                {
                    "id": mid,
                    "xid": f"datagolf:pga:{6211 + t}:{kind}",
                    "nm": f"Test Open {t} - {kind}",
                    "cat": "championship" if kind == "win" else "placement",
                    "mex": mex,
                    "mt": mtype,
                },
            )
            probs = _probs(kind)
            for i in range(FIELD_N):
                oid = mid * 1000 + i
                is_dnp = i in dnp
                win = (not is_dnp) and _won(kind, i)
                rs = "did_not_play" if is_dnp else "leaderboard"
                p = probs[i]
                if variant == "v3_cal_prob":
                    r = rng.random()
                    if r < CAL_NULL_RATE:
                        cal = None
                    elif r < CAL_NULL_RATE + CAL_MOVED_RATE:
                        cal = round(min(max(p * rng.uniform(0.7, 1.4), 0.001), 0.999), 4)
                    else:
                        cal = p
                else:
                    cal = p
                await session.execute(
                    text(
                        "INSERT INTO futures_outcomes (id, market_id, external_id, "
                        "name, opening_probability, calibration_probability, "
                        "is_winner, resolution_source, volume) VALUES "
                        "(:id, :mid, :xid, :nm, :p, :cal, :win, :rs, 10)"
                    ),
                    {
                        "id": oid,
                        "mid": mid,
                        "xid": f"dg_{mid}_{i}",
                        "nm": f"Player {i:03d}",
                        "p": p,
                        "cal": cal,
                        "win": win,
                        "rs": rs,
                    },
                )
                await session.execute(
                    text(
                        "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, "
                        "probability, reading_count, last_price, yes_bid, yes_ask) "
                        "VALUES (:oid, 'datagolf_model', :p, 1, :p, :p, :p)"
                    ),
                    {"oid": oid, "p": p},
                )
    await session.commit()


REASON_SQL = """
    CASE
      WHEN NOT is_liquid THEN 'illiquid'
      WHEN is_poly_placeholder THEN 'poly_placeholder'
      WHEN is_below_writer_bar THEN 'below_writer_bar'
      WHEN is_malformed_binary THEN 'malformed_binary'
      WHEN is_esports_bundle THEN 'esports_bundle'
      WHEN is_player_props_placeholder THEN 'player_props_placeholder'
      WHEN is_golf_placeholder THEN 'golf_placeholder'
      WHEN is_kalshi_prop_threshold THEN 'kalshi_prop_threshold'
      WHEN is_weather_wide_spread THEN 'weather_wide_spread'
      WHEN is_no_winner_market THEN 'no_winner_market'
      WHEN is_draw_authority_missing THEN 'draw_authority_missing'
      WHEN is_orphan_partition THEN 'orphan_partition'
      WHEN is_identity_disputed THEN 'identity_disputed'
      WHEN is_field_incomplete THEN 'field_incomplete'
      WHEN is_mex_normalized THEN 'PUBLISHED(mex_normalized)'
      WHEN is_threshold_ladder AND rn <> 1 THEN 'ladder_non_representative'
      WHEN is_threshold_ladder THEN 'PUBLISHED(ladder rn=1)'
      WHEN is_multi AND adj_opening_probability <= 0.005 THEN 'multi_tail<=0.005'
      WHEN is_multi AND adj_opening_probability >= 0.98 THEN 'multi_head>=0.98'
      WHEN is_multi AND mp_hit THEN 'multi_modal_price'
      WHEN is_multi THEN 'PUBLISHED(multi)'
      WHEN rn <> 1 THEN 'non_representative_rn'
      ELSE 'PUBLISHED(rn=1)'
    END"""


def _kind(mid: int) -> str:
    return KINDS[(mid - BASE_MID) % 10]


async def _report(session, ctes, variant):
    print("\n" + "=" * 78)
    print(f"VARIANT {variant}")
    print("=" * 78)

    stage = {}
    for cte in ("ranked_outcomes", "normalized", "deduped"):
        r = (
            await session.execute(
                text(
                    "WITH "
                    + ctes
                    + f" SELECT COUNT(*) n, SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) w"
                    f" FROM {cte}"
                )
            )
        ).one()
        stage[cte] = (r.n, r.w or 0)
    raw = (
        await session.execute(
            text(
                "SELECT COUNT(*) n, COUNT(*) FILTER (WHERE is_winner) w "
                "FROM futures_outcomes"
            )
        )
    ).one()
    stage["seeded (raw)"] = (raw.n, raw.w)
    for name in ("seeded (raw)", "ranked_outcomes", "normalized", "deduped"):
        n, w = stage[name]
        pct = f"{100.0*w/n:5.1f}%" if n else "    -"
        print(f"   {name:18s} n={n:6d} winners={w:6d}  {pct}")

    rows = (
        await session.execute(
            text(
                "WITH "
                + ctes
                + """, mp_flagged AS (
                    SELECT ro.*, (mp.vm_id IS NOT NULL) AS mp_hit
                    FROM normalized ro
                    LEFT JOIN mode_prices mp
                      ON mp.vm_id = ro.vm_id AND mp.source = ro.source
                     AND mp.mode_price = ro.adj_opening_probability
                )
                SELECT market_id, """
                + REASON_SQL
                + """ AS reason, COUNT(*) n,
                    SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) w
                FROM mp_flagged GROUP BY 1, 2 ORDER BY 1, 3 DESC"""
            )
        )
    ).all()
    agg: dict[tuple[str, str], list[int]] = {}
    for r in rows:
        key = (_kind(r.market_id), r.reason)
        cur = agg.setdefault(key, [0, 0])
        cur[0] += r.n
        cur[1] += r.w
    print("   -- first deduped reason, summed over tournaments --")
    for (kind, reason), (n, w) in sorted(agg.items(), key=lambda kv: (kv[0][0], -kv[1][0])):
        mark = "  <== PUBLISHED" if reason.startswith("PUBLISHED") else ""
        print(f"      {kind:10s} {reason:26s} n={n:5d} winners={w:5d}{mark}")

    pub = (
        await session.execute(
            text(
                "WITH "
                + ctes
                + " SELECT COUNT(*) n, SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) w,"
                " MIN(adj_opening_probability) lo, MAX(adj_opening_probability) hi"
                " FROM deduped"
            )
        )
    ).one()
    if pub.n:
        print(
            f"   PUBLISHED: n={pub.n} winners={pub.w} "
            f"({100.0*pub.w/pub.n:.1f}%) price {float(pub.lo):.3f}..{float(pub.hi):.3f}"
        )


async def main():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base
    from app.tasks.precompute_calibration import _calibration_population_ctes

    engine = create_async_engine(DB_URL)
    # Local Postgres is 14; a whole-metadata create_all dies on a PG15-only
    # ``NULLS NOT DISTINCT`` index in an unrelated table.
    wanted = [
        t for t in Base.metadata.sorted_tables if t.name != "container_provider_anchors"
    ]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=wanted)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    ctes = _calibration_population_ctes()

    async with Session() as session:
        for variant in ("v0_clean", "v1_market_type", "v2_dnp", "v3_cal_prob"):
            await _seed(session, variant)
            await _report(session, ctes, variant)

    await engine.dispose()


asyncio.run(main())
