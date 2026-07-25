"""Queue #253 — Calibration Robustness Audit census (read-heavy, off the request path).

Produces the two deferred deliverables that #251 could not run on the web path
(db-query statement timeout): the literal per-event history-density census
(Item 1) and the full raw-row sub-cohort calibration sweep (Item 2, via the
landed ``cohort_sweep`` helper).

Runs as a Heroku one-off (``heroku run:detached -a bainluck "python3
scripts/evals/cal_robustness_census.py"`` — scripts live at /app per
PROJECT_PATH=backend, so NO ``cd backend``). Because a detached dyno's stdout is
unreadable in the sandbox (gotcha #48), every result section is persisted as a
``cal_robustness_253:<section>`` marker row on ``entities`` (kind='seed_diag',
never collides with real entities) so it can be read back via
``POST /api/admin/db-query`` with ``entity_metadata->>'payload'`` (a TEXT read,
sidestepping the JSONB-repr gotcha #40). The ``:meta`` row is written LAST, so
its presence signals the run finished; an ``:error`` row carries a traceback if
the run dies (the dyno's stdout/logs are unreadable, so this is the only way to
see a failure).

Connection discipline (this is why the first two runs crashed): the app's DB
connections carry Heroku Postgres's default statement_timeout, and it is
CONNECTION-local. A pooled session that commits between statements can be handed
a fresh connection that still has the default timeout, so the slow per-event
GROUP BY hit it and killed the dyno. Fix: hold ONE dedicated ``engine.connect()``
connection for the whole run, ``SET statement_timeout = 0`` on it once, and do
every heavy read on it (no pool churn). Marker writes go through their own
short-lived sessions on separate connections, so their commits never disturb the
read connection.

This is a MEASUREMENT script only — it writes diagnostic marker rows, no
calibration/backfill/data fixes (per the queue's PREREQ NOTE).

Density interpretation (from the retention recon): snapshots older than the
collapse cutoff (24h turbo for odds/futures, 48h for winprob) are run-length
collapsed — a flat stretch becomes ONE row with ``reading_count`` = the true
poll count and ``valid_until`` = when the value changed. So raw COUNT(*)
UNDER-counts sampling density for historical data; ``SUM(reading_count)`` is the
true poll count. A series is genuinely sparse only when effective points are low
relative to its span, not merely when raw rows are few.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

START = "2026-03-01"
REF_PREFIX = "cal_robustness_253"


async def _write_marker(section: str, payload) -> None:
    """Persist one result section as a seed_diag marker row on ``entities``.

    Self-contained: opens its OWN short-lived session (separate connection) so
    its commit never disturbs the run's dedicated read connection. Stores the
    JSON as a text blob under entity_metadata.payload (no size cap — our own
    writer), Core JSONB ``||`` merge (gotcha #4). ``get_task_session`` commits on
    exit."""
    from sqlalchemy import cast, func, literal, select, update
    from sqlalchemy.dialects.postgresql import JSONB

    from app.models.models import Entity
    from app.tasks.base import get_task_session

    ref = f"{REF_PREFIX}:{section}"
    md = {"payload": json.dumps(payload, default=str)}
    async with get_task_session() as s:
        existing = (
            await s.execute(select(Entity.id).where(Entity.external_ref == ref))
        ).scalar_one_or_none()
        if existing:
            await s.execute(
                update(Entity)
                .where(Entity.id == existing)
                .values(
                    entity_metadata=func.coalesce(
                        Entity.entity_metadata, cast(literal("{}"), JSONB)
                    ).op("||")(cast(literal(json.dumps(md)), JSONB))
                )
            )
        else:
            s.add(
                Entity(
                    kind="seed_diag",
                    canonical_name=ref.split(":", 1)[-1],
                    external_ref=ref,
                    entity_metadata=md,
                )
            )


def _rows(result):
    return [dict(r._mapping) for r in result.all()]


async def _run(conn) -> None:
    """The census body — all heavy reads run on the single dedicated ``conn``."""
    from sqlalchemy import text

    await _write_marker("progress", {"stage": "start"})

    # ======================================================================
    # ITEM 1 — history-density census (games + futures), March -> today
    # ======================================================================

    # --- Games: monthly volume (raw rows vs effective poll count) ----------
    games_monthly = _rows(await conn.execute(text(f"""
        SELECT date_trunc('month', captured_at)::date AS month,
               count(*)                         AS rows,
               coalesce(sum(reading_count),0)   AS effective,
               count(DISTINCT event_id)         AS events
        FROM win_prob_snapshots
        WHERE captured_at >= '{START}'
        GROUP BY 1 ORDER BY 1
    """)))
    await _write_marker("progress", {"stage": "games_monthly"})

    # --- Games: per-event density, joined to league/status ----------------
    # One heavy GROUP BY read into Python. Effective points = sum(reading_count)
    # (true poll count post-collapse); span = last coverage instant - first.
    # START is inlined as a SQL literal (not a bind param): asyncpg types a
    # str bind as VARCHAR, and `timestamptz >= varchar` has no operator
    # (crashed the first three runs). A literal gets the implicit date cast, and
    # `:start::timestamptz` would trip the asyncpg text()-drops-bind gotcha.
    game_ev = _rows(await conn.execute(text(f"""
        SELECT d.event_id, d.rows, d.eff, d.n_sources,
               e.llm_league AS league, e.status,
               e.commence_time::date AS game_date,
               EXTRACT(EPOCH FROM (d.last_at - d.first_at))/3600.0 AS span_h
        FROM (
            SELECT s.event_id,
                   count(*)                                    AS rows,
                   coalesce(sum(s.reading_count),0)            AS eff,
                   count(DISTINCT s.source)                    AS n_sources,
                   min(s.captured_at)                          AS first_at,
                   max(coalesce(s.valid_until, s.captured_at)) AS last_at
            FROM win_prob_snapshots s
            WHERE s.captured_at >= '{START}'
            GROUP BY s.event_id
        ) d
        JOIN events e ON e.id = d.event_id
        WHERE e.commence_time >= '{START}'
    """)))
    await _write_marker("progress", {"stage": "game_ev_loaded", "n": len(game_ev)})

    settled = [g for g in game_ev if g["status"] in ("completed", "closed")]

    # By-league rollup (settled events — those that had a full window).
    by_league: dict = {}
    for g in settled:
        by_league.setdefault(g["league"] or "(none)", []).append(g)
    games_by_league = sorted(
        [
            {
                "league": lg, "events": len(gs),
                "avg_eff": round(sum(g["eff"] for g in gs) / len(gs), 1),
                "avg_rows": round(sum(g["rows"] for g in gs) / len(gs), 1),
                "avg_sources": round(sum(g["n_sources"] for g in gs) / len(gs), 2),
                "sparse_events": sum(1 for g in gs if g["eff"] < 6),
                "pct_sparse": round(100.0 * sum(1 for g in gs if g["eff"] < 6) / len(gs), 1),
            }
            for lg, gs in by_league.items() if len(gs) >= 5
        ],
        key=lambda x: x["events"], reverse=True,
    )

    # Worst-100 settled games by effective density (span >= 0.5h to exclude
    # slivers). These are genuine capture gaps — game win-prob is NOT
    # historically backfillable, so they are upstream coverage limits.
    games_worst = sorted(
        [g for g in settled if (g["span_h"] or 0) >= 0.5],
        key=lambda g: (g["eff"], -(g["span_h"] or 0)),
    )[:100]
    games_worst = [
        {
            "event_id": g["event_id"], "league": g["league"] or "(none)",
            "status": g["status"], "eff": g["eff"], "rows": g["rows"],
            "n_sources": g["n_sources"], "span_h": round(g["span_h"] or 0, 2),
            "game_date": g["game_date"],
        }
        for g in games_worst
    ]
    await _write_marker("games", {
        "monthly": games_monthly,
        "settled_events": len(settled),
        "by_league": games_by_league,
        "worst_100": games_worst,
        "note": "eff = SUM(reading_count) (true poll count post-collapse); "
                "rows = raw snapshot rows; sparse = eff<6 over a game window. "
                "Game win-prob (espn/betting/mlb live) is NOT historically "
                "backfillable — worst games are upstream coverage limits.",
    })
    await _write_marker("progress", {"stage": "games_done"})

    # --- Futures: dedup magnitude (raw vs effective) ----------------------
    dedup = _rows(await conn.execute(text(f"""
        SELECT 'win_prob_snapshots' AS tbl,
               round(avg(reading_count)::numeric,3) AS avg_rc,
               max(reading_count) AS max_rc,
               round(100.0*sum(CASE WHEN reading_count>1 THEN 1 ELSE 0 END)/count(*),2) AS pct_deduped,
               count(*) AS rows, coalesce(sum(reading_count),0) AS effective
        FROM win_prob_snapshots WHERE captured_at >= '{START}'
        UNION ALL
        SELECT 'futures_odds_snapshots',
               round(avg(reading_count)::numeric,3), max(reading_count),
               round(100.0*sum(CASE WHEN reading_count>1 THEN 1 ELSE 0 END)/count(*),2),
               count(*), coalesce(sum(reading_count),0)
        FROM futures_odds_snapshots WHERE captured_at >= '{START}'
    """)))
    await _write_marker("progress", {"stage": "dedup"})

    # --- Futures: per-outcome density, joined to source/league ------------
    fut_ev = _rows(await conn.execute(text(f"""
        SELECT d.outcome_id, d.rows, d.eff, d.n_books,
               m.source,
               coalesce(m.llm_league, m.llm_sport_category, m.category, '(none)') AS league,
               coalesce(m.market_type, 'unshaped') AS market_type,
               EXTRACT(EPOCH FROM (d.last_at - d.first_at))/86400.0 AS span_d
        FROM (
            SELECT s.outcome_id,
                   count(*)                                    AS rows,
                   coalesce(sum(s.reading_count),0)            AS eff,
                   count(DISTINCT s.bookmaker)                 AS n_books,
                   min(s.captured_at)                          AS first_at,
                   max(coalesce(s.valid_until, s.captured_at)) AS last_at
            FROM futures_odds_snapshots s
            WHERE s.captured_at >= '{START}'
            GROUP BY s.outcome_id
        ) d
        JOIN futures_outcomes o ON o.id = d.outcome_id
        JOIN futures_markets m  ON m.id = o.market_id
    """)))
    await _write_marker("progress", {"stage": "fut_ev_loaded", "n": len(fut_ev)})

    # By-source rollup.
    by_src: dict = {}
    for f in fut_ev:
        by_src.setdefault(f["source"] or "(none)", []).append(f)
    fut_by_source = sorted(
        [
            {
                "source": src, "outcomes": len(fs),
                "avg_eff": round(sum(f["eff"] for f in fs) / len(fs), 1),
                "avg_rows": round(sum(f["rows"] for f in fs) / len(fs), 1),
                "avg_span_d": round(sum((f["span_d"] or 0) for f in fs) / len(fs), 2),
                "single_row": sum(1 for f in fs if f["rows"] == 1),
                "pct_single_row": round(100.0 * sum(1 for f in fs if f["rows"] == 1) / len(fs), 1),
            }
            for src, fs in by_src.items()
        ],
        key=lambda x: x["outcomes"], reverse=True,
    )
    # By source x shape rollup.
    by_ss: dict = {}
    for f in fut_ev:
        by_ss.setdefault((f["source"] or "(none)", f["market_type"]), []).append(f)
    fut_by_shape = sorted(
        [
            {
                "source": k[0], "market_type": k[1], "outcomes": len(fs),
                "avg_eff": round(sum(f["eff"] for f in fs) / len(fs), 1),
                "avg_span_d": round(sum((f["span_d"] or 0) for f in fs) / len(fs), 2),
            }
            for k, fs in by_ss.items() if len(fs) >= 50
        ],
        key=lambda x: x["outcomes"], reverse=True,
    )[:40]

    # Worst-100 genuinely-sparse futures: long open span (>=3d), few effective
    # pts (< 1 pt/day). Recoverability: polymarket -> CLOB backfill; kalshi ->
    # only within ~2-3mo of settlement (gotcha #35).
    def _recov(src):
        return {
            "polymarket": "recoverable_clob",
            "kalshi": "kalshi_time_gated_2-3mo",
            "datagolf": "model_limited",
        }.get(src, "limited")

    sparse_fut = [f for f in fut_ev if (f["span_d"] or 0) >= 3 and f["eff"] < (f["span_d"] or 0)]
    sparse_fut.sort(key=lambda f: (f["eff"] / max(f["span_d"] or 0.01, 0.01), -(f["span_d"] or 0)))
    fut_worst = [
        {
            "outcome_id": f["outcome_id"], "source": f["source"] or "(none)",
            "league": f["league"], "market_type": f["market_type"],
            "eff": f["eff"], "rows": f["rows"], "n_books": f["n_books"],
            "span_d": round(f["span_d"] or 0, 2),
            "eff_per_day": round(f["eff"] / max(f["span_d"] or 0.01, 0.01), 2),
            "recoverability": _recov(f["source"]),
        }
        for f in sparse_fut[:100]
    ]
    await _write_marker("futures", {
        "dedup_magnitude": dedup,
        "total_outcomes": len(fut_ev),
        "sparse_outcomes": len(sparse_fut),
        "by_source": fut_by_source,
        "by_source_shape": fut_by_shape,
        "worst_100": fut_worst,
        "note": "eff = SUM(reading_count); genuinely sparse = span>=3d AND "
                "eff<span_d (below 1pt/day). Flat-but-dense (high reading_count) "
                "is legit-captured, exempt. futures_odds dedups ONLY via the "
                "24h turbo-collapse job (no write-time dedup).",
    })
    await _write_marker("progress", {"stage": "futures_done"})

    # ======================================================================
    # ITEM 2 — full raw-row sub-cohort calibration sweep
    # ======================================================================
    from sqlalchemy.ext.asyncio import AsyncSession

    from scripts.evals.cohort_sweep import (
        expected_calibration_error,
        load_from_session,
        normalize_rows,
        sweep,
    )

    # load_from_session needs a Session; bind one to the dedicated connection so
    # the big 1.28M-row select runs on the same no-timeout connection.
    read_sess = AsyncSession(bind=conn)
    try:
        raw = await load_from_session(read_sess)
    finally:
        await read_sess.close()
    await _write_marker("progress", {"stage": "loaded_rows", "n": len(raw)})

    report = sweep(raw, worst_n=25)

    # Compact drill-down: drop the per-cohort 10-example lists (huge), keep the
    # calibration stats.
    drill = [
        {k: c[k] for k in (
            "source", "league_category", "market_type", "n", "sufficient",
            "predicted_rate", "actual_rate", "signed_error", "direction",
            "ece", "calibration_slope", "severity",
        )} | {"anti_flag": c["anti_calibration"]["flag"]}
        for c in report["drill_down"]
    ]

    # Shape-level and source-level rollups (assume-our-bug: shape is the axis).
    norm = normalize_rows(raw)

    def rollup(key_fn):
        groups: dict = {}
        for r in norm:
            groups.setdefault(key_fn(r), []).append(r)
        out = []
        for key, rs in sorted(groups.items()):
            n = len(rs)
            pred = sum(r["probability"] for r in rs) / n
            act = sum(r["actual"] for r in rs) / n
            out.append({
                "key": key, "n": n,
                "predicted": round(pred, 4), "actual": round(act, 4),
                "signed_error": round(pred - act, 4),
                "ece": round(expected_calibration_error(rs), 4),
            })
        return sorted(out, key=lambda x: x["n"], reverse=True)

    by_shape = rollup(lambda r: r["market_type"])
    by_source = rollup(lambda r: r["source"])
    by_source_shape = [
        x for x in rollup(lambda r: f"{r['source']}|{r['market_type']}")
        if x["n"] >= 100
    ]

    # The honest baseline: duel (binary) reliability curve, deciles.
    duel = [r for r in norm if r["market_type"] == "duel"]
    curve = []
    for i in range(10):
        lo, hi = i / 10.0, (i + 1) / 10.0
        bucket = [r for r in duel if (lo <= r["probability"] < hi) or (i == 9 and r["probability"] == 1.0)]
        if bucket:
            curve.append({
                "decile": f"{lo:.1f}-{hi:.1f}", "n": len(bucket),
                "predicted": round(sum(r["probability"] for r in bucket) / len(bucket), 3),
                "actual": round(sum(r["actual"] for r in bucket) / len(bucket), 3),
            })
    duel_ece = round(expected_calibration_error(duel), 4) if duel else None

    # #254 Item 2: source-collapsed sport×shape cells (compact — drop examples),
    # plus a golf-only breakout (Alex's catch: golf's duel/quantity outcomes
    # deserve their own curve, not to be averaged into the winner-field).
    sport_shape = [
        {k: c[k] for k in (
            "league_category", "market_type", "n", "sufficient",
            "predicted_rate", "actual_rate", "signed_error", "ece",
            "calibration_slope", "severity",
        )} | {"anti_flag": c["anti_calibration"]["flag"]}
        for c in report["by_sport_shape"]
    ]
    golf_by_shape = [
        c for c in sport_shape
        if c["league_category"] in ("golf", "PGA", "LPGA", "DPWorld")
        or "golf" in c["league_category"].lower()
    ]

    await _write_marker("sweep", {
        "population": report["rows"],
        "cohorts": report["cohorts"],
        "worst_25": report["worst_20"],  # worst_n=25 requested above
        "by_shape": by_shape,
        "by_source": by_source,
        "by_source_shape": by_source_shape,
        "by_sport_shape": sport_shape,
        "golf_by_shape": golf_by_shape,
        "duel_curve": curve,
        "duel_ece": duel_ece,
    })
    await _write_marker("sweep_drill", {"drill_down": drill})
    await _write_marker("progress", {"stage": "sweep_done"})

    # Final meta marker (written LAST — presence == run complete).
    await _write_marker("meta", {
        "queue": "253",
        "start": START,
        "calibratable_rows": report["rows"],
        "cohorts": report["cohorts"],
        "duel_ece": duel_ece,
        "sections": ["games", "futures", "sweep", "sweep_drill", "meta"],
        "done": True,
    })


async def run() -> None:
    from sqlalchemy import text

    from app.tasks.base import _get_task_engine

    engine = _get_task_engine()
    try:
        async with engine.connect() as conn:
            # One dedicated connection, timeout disabled ONCE (session-level,
            # survives across reads; no pool churn since we hold this connection
            # for the whole run).
            await conn.execute(text("SET statement_timeout = 0"))
            await _run(conn)
    except Exception:
        # The dyno's stdout/logs are unreadable in the sandbox — persist the
        # traceback so the failure is visible via db-query.
        import traceback

        try:
            await _write_marker("error", {"traceback": traceback.format_exc()[-6000:]})
        except Exception:
            pass
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
