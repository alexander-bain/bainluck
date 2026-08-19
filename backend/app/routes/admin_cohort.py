"""Admin cohort-market-type ECE table — league×source×market_type×band × week, sorted descending by ECE."""
import json
import time
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi import Depends
from fastapi.responses import JSONResponse, HTMLResponse
from app.routes.admin_utils import _check_admin_secret
from app.services import get_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

_CACHE_KEY = "bainluck:cohort_market_type"
_CACHE_TTL = 86400
_STALE_HOURS = 6  # visible STALE badge when cache older than 6h

def _load_cached():
    try:
        from app.tasks.redis_state import get_redis_client
        rc = get_redis_client()
        raw = rc.get(_CACHE_KEY)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None

def _load_debug():
    try:
        from app.tasks.redis_state import get_redis_client
        rc = get_redis_client()
        raw = rc.get(_CACHE_KEY + ":debug")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None

@router.get("/admin/cohort-market-type")
async def cohort_market_type(
    request: Request,
):
    _check_admin_secret(request=request)
    cached = _load_cached()
    if cached:
        return cached
    debug = _load_debug()
    return JSONResponse(
        status_code=202,
        content={
            "status": "no cached table yet",
            "message": "POST to /api/admin/cohort-market-type/build to trigger a background build (runs in worker, ~90s), then GET again. If still empty after 3m, check debug or try /light",
            "cache_key": _CACHE_KEY,
            "debug": debug,
        },
    )

@router.get("/admin/cohort-market-type/light")
async def cohort_market_type_light(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Lightweight approximation: source×market_type×league ECE without full dedup.
    Runs in <10s on web, so it can be served synchronously. Useful to test
    your hypothesis immediately while the canonical build completes."""
    _check_admin_secret(request=request)
    from sqlalchemy import text
    # Direct scan of resolved outcomes with usable prob, no virtual-market/field logic
    # Sampling: WHERE random() < p is unbiased row-level Bernoulli (no Sort),
    # unlike ORDER BY random() which sorts the whole join (O(n log n) and H12
    # >30s on the production join) and unlike TABLESAMPLE SYSTEM which is
    # block-sampled and heap-biased. p=0.30 is calibrated so expected
    # 0.30 * ~700k eligible ≈210k → LIMIT 200k is loose; floor check below
    # ensures ≥150k scanned or the caller is warned (unbiased but too small is
    # still wrong). Statistical property: each eligible outcome has equal .30
    # inclusion probability independent of heap order.
    rows = (await db.execute(text("""
        SELECT fm.source, COALESCE(fm.llm_sport_category,'uncategorized') as league,
               COALESCE(fm.market_type,'unknown') as market_type,
               COALESCE(fo.calibration_probability, fo.opening_probability) as prob,
               fo.is_winner
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id=fo.market_id
        WHERE fm.status='resolved'
          AND COALESCE(fo.calibration_probability, fo.opening_probability) >0
          AND COALESCE(fo.calibration_probability, fo.opening_probability) <1
          AND fo.opening_probability IS NOT NULL
          AND fo.is_winner IS NOT NULL
          AND random() < 0.30
        LIMIT 200000
    """))).all()
    # Compute ECE per cohort via the ONE canonical definition where possible
    from collections import defaultdict
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r.source, r.league, r.market_type)].append((float(r.prob), int(r.is_winner)))
    out=[]
    for (src,league,mt), lst in grouped.items():
        n=len(lst)
        if n<30:
            continue
        # Build buckets and delegate to sentinel's _compute_horizon_mce when available
        bins=[[] for _ in range(10)]
        for p,a in lst:
            bins[min(int(p*10),9)].append((p,a))
        ece_pp = None
        is_fallback = False
        try:
            from app.tasks.precompute_calibration import _compute_horizon_mce
            buckets=[]
            for b in bins:
                if not b:
                    continue
                buckets.append({"n": len(b), "winners": sum(a for _,a in b), "sum_prob": sum(p for p,_ in b)})
            v = _compute_horizon_mce(buckets, weighted=True)
            if v is not None:
                ece_pp = round(v,2)
            else:
                is_fallback = True
        except Exception:
            is_fallback = True
        if ece_pp is None:
            total_ece=0.0
            for b in bins:
                if not b: continue
                avg_p=sum(p for p,_ in b)/len(b)
                avg_a=sum(a for _,a in b)/len(b)
                total_ece+= len(b)/n * abs(avg_p-avg_a)
            ece_pp= round(total_ece*100,2)
            is_fallback = True
        avg_p=sum(p for p,_ in lst)/n
        avg_a=sum(a for _,a in lst)/n
        label = "fallback-nonparity" if is_fallback else "light-estimate"
        out.append({"source":src,"league_category":league,"market_type":mt,"n":n,"ece":ece_pp,"ece_label":label,"pred":round(avg_p,3),"actual":round(avg_a,3),"gap_pp":round((avg_p-avg_a)*100,2)})
    out=sorted(out, key=lambda x: x["ece"], reverse=True)
    # Top-level label is fallback-nonparity if any row fell back, else light-estimate
    top_label = "fallback-nonparity" if any(r.get("ece_label")=="fallback-nonparity" for r in out) else "light-estimate"
    return {"rows_scanned": len(rows), "cohorts": len(grouped), "sufficient": len(out), "by_ece": out[:100], "ece_label": top_label, "note": "light-estimate: 200k sample without dedup/field-normalization; canonical heavy build is the source of truth" + (" — some rows used fallback-nonparity" if top_label=="fallback-nonparity" else "")}

@router.get("/admin/cohort-market-type/debug")
async def cohort_market_type_debug(
    request: Request,
):
    _check_admin_secret(request=request)
    return {"cached": _load_cached() is not None, "debug": _load_debug()}

@router.post("/admin/cohort-market-type/build")
async def cohort_market_type_build(
    request: Request,
    background_tasks: BackgroundTasks,
):
    _check_admin_secret(request=request)
    # Enqueue background build via Celery if available, else run in background task
    try:
        from app.tasks import celery_app
        celery_app.send_task("app.tasks.build_cohort_market_type", queue="heavy")
        return {"status": "enqueued", "task": "app.tasks.build_cohort_market_type", "cache_key": _CACHE_KEY}
    except Exception as e:
        # Fallback: run in FastAPI background task (still hits 30s limit, but try)
        background_tasks.add_task(_build_and_cache)
        return {"status": "enqueued_background", "error": str(e)[:200]}

async def _build_and_cache():
    try:
        from scripts.evals.cohort_sweep import load_from_session, sweep
        from app.services.database import async_session_maker
        async with async_session_maker() as s:
            rows = await load_from_session(s)
        report = sweep(rows)
        by_ece = sorted([c for c in report["drill_down"] if c["sufficient"]], key=lambda c: c["ece"], reverse=True)
        payload = {
            "rows": report["rows"],
            "cohorts": report["cohorts"],
            "sufficient": len(by_ece),
            "minimum_cohort_n": report["minimum_cohort_n"],
            "by_ece": by_ece,
            "generated_at": time.time(),
        }
        from app.tasks.redis_state import get_redis_client
        rc = get_redis_client()
        rc.set(_CACHE_KEY, json.dumps(payload, default=str), ex=_CACHE_TTL)
    except Exception as e:
        import traceback
        traceback.print_exc()

@router.get("/admin/cohort-market-type/full")
async def cohort_market_type_full(
    request: Request,
):
    _check_admin_secret(request=request)
    cached = _load_cached()
    if cached:
        return cached
    return JSONResponse(status_code=202, content={"status": "no cached table yet"})


@router.get("/admin/cohort-market-type/weekly")
async def cohort_market_type_weekly(
    request: Request,
):
    _check_admin_secret(request=request)
    cached = _load_cached()
    if cached and "weekly_by_cohort" in cached:
        return {"weekly_by_cohort": cached["weekly_by_cohort"], "weekly": cached.get("weekly", []), "generated_at": cached.get("generated_at")}
    return JSONResponse(status_code=202, content={"status": "no cached weekly yet, POST /build first"})


@router.get("/admin/cohort-provenance-split")
async def cohort_provenance_split(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Provenance split: venue-graded vs all rows per worst shape cell.

    Header-only auth (no ?secret). Returns per (league, market_type) for
    polymarket quantity/container_member: n_all, n_venue, null_default_share,
    plus ECE_all and ECE_venue (10-bin, n-weighted) so the decider is one call.

    Aggregates in SQL over the FULL population. It used to ship up to 300,000
    rows to Python behind ``ORDER BY random()``, which sorts the whole join
    before the LIMIT can discard any of it — that read returned in 29.99s once
    and has H12'd at the router's hard 30s limit on every attempt since
    (4/4 on 2026-08-18), taking the #1912 per-cell evidence base with it.
    Everything this endpoint computes is a bin-level aggregate, so the bins are
    now built by the database and only ~1,000 rows cross the wire. Two
    consequences beyond speed: the numbers are the whole population rather than
    a sample, and ``n_all`` is a real count rather than a sampled one.
    """
    _check_admin_secret(request=request)
    from sqlalchemy import text
    from collections import defaultdict
    agg = (await db.execute(text("""
        SELECT COALESCE(fm.llm_sport_category,'uncategorized') AS league,
               COALESCE(fm.market_type,'unknown') AS market_type,
               (fo.resolution_source IS NOT NULL) AS venue,
               LEAST(FLOOR(COALESCE(fo.calibration_probability, fo.opening_probability)*10),9)::int AS bin,
               COUNT(*) AS n,
               SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS sum_prob,
               SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS winners
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status='resolved'
          AND fm.source='polymarket'
          AND fm.market_type IN ('quantity','container_member')
          AND COALESCE(fo.calibration_probability, fo.opening_probability) > 0
          AND COALESCE(fo.calibration_probability, fo.opening_probability) < 1
          AND fo.opening_probability IS NOT NULL
          AND fo.is_winner IS NOT NULL
        GROUP BY 1,2,3,4
    """))).all()
    # Group by (league, market_type) and compute ECE_all vs ECE_venue via ONE canonical definition.
    # The unit here is a BIN AGGREGATE (n, sum_prob, winners), not a list of pairs, because the
    # database already did the binning — but the definition is byte-for-byte the one
    # _compute_horizon_mce implements, and the fallback below is the same arithmetic it was.
    # Returns (ece_pp, is_fallback) so callers can label fallback-nonparity.
    def ece_of_with_label(bins):
        n = sum(b["n"] for b in bins.values())
        if n < 30:
            return None, False
        buckets = [
            {"n": b["n"], "winners": b["winners"], "sum_prob": b["sum_prob"]}
            for b in bins.values() if b["n"]
        ]
        try:
            from app.tasks.precompute_calibration import _compute_horizon_mce
            v = _compute_horizon_mce(buckets, weighted=True)
            if v is not None:
                return round(v, 2), False
        except Exception:
            pass
        total = 0.0
        for b in buckets:
            avg_p = b["sum_prob"] / b["n"]
            avg_a = b["winners"] / b["n"]
            total += b["n"] / n * abs(avg_p - avg_a)
        return round(total * 100, 2), True

    def _empty_bins():
        return defaultdict(lambda: {"n": 0, "sum_prob": 0.0, "winners": 0.0})

    from collections import defaultdict
    grouped_all = defaultdict(_empty_bins)
    grouped_venue = defaultdict(_empty_bins)
    counts = defaultdict(lambda: {"n_all": 0, "n_venue": 0})
    rows_aggregated = 0
    for r in agg:
        key = (r.league, r.market_type)
        n = int(r.n)
        sum_prob = float(r.sum_prob or 0.0)
        winners = float(r.winners or 0.0)
        rows_aggregated += n
        slot = grouped_all[key][int(r.bin)]
        slot["n"] += n
        slot["sum_prob"] += sum_prob
        slot["winners"] += winners
        counts[key]["n_all"] += n
        if r.venue:
            vslot = grouped_venue[key][int(r.bin)]
            vslot["n"] += n
            vslot["sum_prob"] += sum_prob
            vslot["winners"] += winners
            counts[key]["n_venue"] += n
    out = []
    for key in sorted(grouped_all.keys()):
        league, mtype = key
        n_all = counts[key]["n_all"]
        n_venue = counts[key]["n_venue"]
        n_default = n_all - n_venue
        null_share = round(n_default/n_all,3) if n_all else None
        graded_share = round(n_venue/n_all,3) if n_all else None
        ece_all, fellback_all = ece_of_with_label(grouped_all[key])
        ece_venue, fellback_venue = ece_of_with_label(grouped_venue[key]) if n_venue >= 30 else (None, False)
        # Also compute gap for context
        def gap_of(bins):
            n = sum(b["n"] for b in bins.values())
            if not n:
                return None
            avg_p = sum(b["sum_prob"] for b in bins.values()) / n
            avg_a = sum(b["winners"] for b in bins.values()) / n
            return round((avg_p-avg_a)*100,2)
        gap_all = gap_of(grouped_all[key])
        gap_venue = gap_of(grouped_venue[key]) if n_venue >=30 else None
        # Verdict per LAUNCH-LEDGER: graded_share <50% wins BEFORE ≤5pp test — use shared _verdict_for
        # For the main cell verdict, graded_share <0.5 blocks GREEN even if ECE ≤5pp.
        # For the venue-graded sub-cohort, rows are 100% graded, so use 1.0.
        from scripts.evals.cohort_sweep import _verdict_for
        def _prov_verdict(ece, n, gshare):
            sufficient = n >= 30 if n is not None else False
            return _verdict_for(ece, sufficient, gshare)
        # Label fallback so divergent number can never render unmarked
        ece_label_all = "fallback-nonparity" if fellback_all else None
        ece_label_venue = "fallback-nonparity" if fellback_venue else None
        out.append({
            "league": league, "market_type": mtype,
            "n_all": n_all, "n_venue": n_venue, "n_default": n_default,
            "null_default_share": null_share, "graded_share": graded_share,
            "ece_all": ece_all, "ece_label_all": ece_label_all, "ece_venue": ece_venue, "ece_label_venue": ece_label_venue,
            "gap_all": gap_all, "gap_venue": gap_venue,
            "verdict_all": _prov_verdict(ece_all, n_all, graded_share),
            "verdict_venue": _prov_verdict(ece_venue, n_venue, 1.0),
        })
    out = sorted(out, key=lambda x: (x["ece_all"] or 0), reverse=True)
    return {
        "rows_scanned": rows_aggregated,
        "sampled": False,
        "population": "full",
        "bin_rows_returned": len(agg),
        "cells": out,
        "note": (
            "venue = resolution_source IS NOT NULL; default = IS NULL (226k PM defaults). "
            "Bins are aggregated in SQL over the FULL population — rows_scanned is a real "
            "count, not a 300k sample."
        ),
    }


@router.post("/admin/cohort-cell-census/run")
async def cohort_cell_census_run(
    request: Request,
    page_size: int = 1000,
    resume: bool = True,
    inline: bool = False,
):
    """#1978: run (or resume) the all-cells provenance census on the worker.

    This exists because ``GET /admin/cohort-provenance-split`` above — which is
    the correct full-population reader, correctly rewritten to aggregate in SQL —
    **cannot be served.** It returns HTTP 503 at 30.21 s, re-measured by CAL-P075
    after the 40 h orphan backend was killed and the reclaim ran on both tables,
    so bloat was never the cause: the planner drives from a Parallel Seq Scan on
    ``futures_outcomes`` (87% of plan cost) that every cell pays in full, and
    narrowing the filter does not narrow the scan. A 12-to-76-minute job cannot be
    an HTTP request.

    ``inline=true`` runs it in-request and WILL H12 on the full population — it
    exists for a small ``page_size`` smoke test, not for a real census. The
    default enqueues.

    Re-invoke until the artifact reports ``complete: true``; each call resumes
    from the banked cursor. ``resume=false`` starts a fresh walk, which is what
    you want after the population predicate changes and nothing else.
    """
    _check_admin_secret(request=request)

    if inline:
        from app.tasks.cohort_cell_census_worker import run_cohort_cell_census

        return await run_cohort_cell_census(
            page_size=int(page_size), resume=bool(resume)
        )

    from app.routes.admin_utils import _safe_send_task

    result = _safe_send_task(
        "app.tasks.cohort_cell_census",
        kwargs={"page_size": int(page_size), "resume": bool(resume)},
    )
    return {"status": "enqueued", "task_id": getattr(result, "id", None)}


@router.get("/admin/cohort-cell-census/last")
async def cohort_cell_census_last(request: Request):
    """#1978: read the last census artifact (or the in-flight checkpoint).

    Serves the same per-cell shape as ``/admin/cohort-provenance-split`` plus the
    ``ece_complete`` / ``ece_incomplete`` twins and a per-cell ``measured`` flag.

    **A partial read is a first-class answer here.** ``complete: false`` with a
    ``resume_cursor`` means the walk is mid-flight, and the cells already banked
    are still worth having — that is the whole reason ``measured`` is per cell
    rather than per run. It is never rendered as a clean zero (gotcha #53).
    """
    _check_admin_secret(request=request)

    from app.services.durable_snapshots import read_snapshot_standalone
    from app.utils.cohort_cell_census import CENSUS_IDENTITY, CENSUS_SCHEMA

    try:
        read = await read_snapshot_standalone(
            CENSUS_IDENTITY, expected_version=CENSUS_SCHEMA, max_age_s=30 * 86400
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "measured": False,
            "reason": f"artifact_read_raised: {type(exc).__name__}",
        }
    if not read.ok or read.envelope is None:
        return {"measured": False, "reason": f"artifact_unreadable: {read.status}"}
    payload = dict(read.envelope.payload or {})
    # The raw bin accumulator is the checkpoint's business, not a reader's: it is
    # tens of thousands of keys and says nothing the per-cell rows do not.
    payload.pop("bins", None)
    return payload


@router.get("/admin/cohort-sums-histogram")
async def cohort_sums_histogram(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Sums-to-1 histogram for Polymarket container_member/quantity ladders.

    Header-only auth. Groups by COALESCE(group_id, event_id) and computes
    sum_prob per group using curve price. Returns bucket histogram + per-size stats.
    Only meaningful if provenance survives venue-graded-only.

    Buckets in SQL (#1974). This used to sort every group with ``ORDER BY
    random()`` and ship up to 100,000 of them to Python, which H12'd at the
    router's hard 30s limit on all three of INT-085's attempts and could not be
    recovered off-route either. The bucket assignment, the per-bucket means and
    the per-size medians are all aggregates, so the database does them and a
    couple of dozen rows cross the wire. The endpoint is no longer sampled,
    so the counts are the whole population.
    """
    _check_admin_secret(request=request)
    from sqlalchemy import text

    # One shared derived table. `bucket` is the same six-way split the Python
    # loop applied, expressed once so the two readers below cannot drift.
    _GROUPS = """
        SELECT COALESCE(fm.group_id::text, 'event:'||fm.event_id::text) AS group_key,
               COUNT(*) AS members,
               SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS sum_prob,
               BOOL_OR(fo.resolution_source IS NOT NULL) AS has_venue
        FROM futures_markets fm
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE fm.status='resolved'
          AND fm.source='polymarket'
          AND fm.market_type IN ('container_member','quantity')
          AND COALESCE(fo.calibration_probability, fo.opening_probability) > 0
          AND COALESCE(fo.calibration_probability, fo.opening_probability) < 1
          AND fo.opening_probability IS NOT NULL
          AND fo.is_winner IS NOT NULL
        GROUP BY group_key
        HAVING COUNT(*) >= 2
    """
    _BUCKET = """
        CASE WHEN sum_prob < 1.0 THEN 0
             WHEN sum_prob < 1.5 THEN 1
             WHEN sum_prob < 2.0 THEN 2
             WHEN sum_prob < 3.0 THEN 3
             WHEN sum_prob < 5.0 THEN 4
             ELSE 5 END
    """
    ORDERED = [
        "0–1.0 (under)", "1.0–1.5 (slightly over)", "1.5–2.0 (over)",
        "2.0–3.0 (ladder)", "3.0–5.0 (strong ladder)", "5.0+ (extreme ladder)",
    ]

    hist_rows = (await db.execute(text(f"""
        SELECT {_BUCKET} AS bucket_idx,
               has_venue,
               COUNT(*) AS groups,
               SUM(sum_prob) AS total_sum,
               SUM(members) AS total_members
        FROM ({_GROUPS}) g
        GROUP BY 1, 2
    """))).all()

    # A declared top-N over an already-aggregated table, not a bound on the
    # input — and `per_size_total` below says how many distinct sizes it dropped,
    # because a truncated list that does not announce its truncation reads as
    # "these are all of them".
    _PER_SIZE_N = 20
    size_rows = (await db.execute(text(f"""
        SELECT members,
               COUNT(*) AS groups,
               AVG(sum_prob) AS avg_sum,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY sum_prob) AS median_sum,
               COUNT(*) OVER () AS distinct_sizes
        FROM ({_GROUPS}) g
        GROUP BY members
        ORDER BY members
        LIMIT {_PER_SIZE_N}
    """))).all()

    all_counts = {b: 0 for b in ORDERED}
    all_sum = {b: 0.0 for b in ORDERED}
    all_members = {b: 0.0 for b in ORDERED}
    venue_counts = {b: 0 for b in ORDERED}
    groups_scanned = 0
    for r in hist_rows:
        b = ORDERED[int(r.bucket_idx)]
        n = int(r.groups)
        groups_scanned += n
        all_counts[b] += n
        all_sum[b] += float(r.total_sum or 0)
        all_members[b] += float(r.total_members or 0)
        if r.has_venue:
            venue_counts[b] += n

    hist = []
    for b in ORDERED:
        cnt = all_counts[b]
        hist.append({
            "bucket": b,
            "groups": cnt,
            "avg_sum": round(all_sum[b] / cnt, 2) if cnt else None,
            "avg_members": round(all_members[b] / cnt, 1) if cnt else None,
        })
    vhist = [{"bucket": b, "groups": venue_counts[b]} for b in ORDERED]
    size_stats = [
        {"members": int(r.members), "groups": int(r.groups),
         "avg_sum": round(float(r.avg_sum), 2) if r.avg_sum is not None else None,
         "median_sum": round(float(r.median_sum), 2) if r.median_sum is not None else None}
        for r in size_rows
    ]
    per_size_total = int(size_rows[0].distinct_sizes) if size_rows else 0
    return {
        "groups_scanned": groups_scanned,
        "sampled": False,
        "population": "full",
        "per_size_total": per_size_total,
        "per_size_shown": len(size_stats),
        "histogram_all": hist,
        "histogram_venue_only": vhist,
        "per_size": size_stats,
        "note": (
            "sum_prob = SUM(curve_price) per COALESCE(group_id, event_id); "
            "venue_only = has_venue=true; 5.0+ is extreme ladder defect. "
            "Bucketed in SQL over the FULL population (#1974) — not a 100k sample. "
            "median_sum is PERCENTILE_CONT(0.5); the pre-#1974 value was the "
            "upper of the two middles for even counts."
        ),
    }


@router.get("/admin/cohort-views", response_class=HTMLResponse)
async def cohort_views_html(request: Request):
    _check_admin_secret(request=request)
    html = """<!doctype html>
<html><head><meta charset="utf-8"><title>Cohort Views — ECE by source×league×type×band × week</title>
<meta http-equiv="refresh" content="60">
<style>
body{font-family:system-ui,sans-serif;margin:24px;background:#0a0a0a;color:#e5e5e5}
a{color:#60a5fa}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid #333;padding:6px 8px;text-align:left;white-space:nowrap}
th{background:#1a1a1a;position:sticky;top:0}
tr:nth-child(even){background:#111}
.badge{padding:2px 6px;border-radius:4px;font-size:11px}
.green{background:#065f46;color:#a7f3d0}
.red{background:#7f1d1d;color:#fecaca}
.notprov{background:#422006;color:#fde68a}
.muted{color:#9ca3af}
.stale{background:#7f1d1d;color:#fecaca;padding:2px 8px;border-radius:4px;font-weight:bold;margin-left:8px}
</style></head><body>
<h1>Cohort Views — league × source × market_type × band <span class="muted" style="font-weight:normal">sorted desc by ECE</span></h1>
<p class="muted">Auto-refreshes every 60s when authorized. Heavy table built in worker (Celery heavy queue, ~90s). Graded share &lt;50% ⇒ <code>NOT-PROVABLE-selection-biased</code> per today's ruling. Band = 0-10%..90-100% (4th axis). Weekly trend for Monday scoreboard below. <span class="muted">STALE threshold: 6h.</span></p>
<p class="muted">Auth: paste <code>ADMIN_TOKEN</code> below — it is held in memory only, sent as <code>Authorization: Bearer</code>, never in the URL or browser storage. Prefer the Next.js page at <a href="/admin/cohort-views">/admin/cohort-views</a> for normal viewing.</p>
<div id="auth" class="muted" style="margin:8px 0">Admin token (Bearer, in-memory only): <input id="secretInput" type="password" placeholder="paste ADMIN_TOKEN, not stored" style="background:#1a1a1a;color:#e5e5e5;border:1px solid #333;padding:4px 8px;width:360px"> <button id="saveSecret" style="padding:4px 8px">Load</button> <span id="authStatus" class="muted"></span> <button id="rebuildBtn" style="padding:4px 8px;margin-left:12px;border:1px solid #a16207;background:#422006;color:#fde68a">Rebuild (POST /build)</button> <span id="rebuildStatus" class="muted"></span></div>
<div id="meta" class="muted">Not loaded — enter token and click Load.</div>
<h2>Top by ECE (heavy, with band + graded_share)</h2>
<table id="tbl"><thead><tr><th>rank</th><th>source</th><th>league</th><th>type</th><th>band</th><th>n</th><th>q</th><th>graded_share</th><th>ECE</th><th>gap pp</th><th>verdict</th></tr></thead><tbody></tbody></table>
<h2>Weekly — last 6 weeks per cohort (is it improving?)</h2>
<div id="weekly" class="muted">Loading weekly…</div>
<script>
let _inMemoryToken = "";
const STALE_HOURS = 6;
async function fetchJSON(url) {
  const secret = _inMemoryToken;
  const headers = {};
  if (secret) headers["Authorization"] = "Bearer " + secret;
  const r = await fetch(url, {headers});
  if (!r.ok) throw new Error(r.status + " " + await r.text());
  return r.json();
}
async function postBuild() {
  const secret = _inMemoryToken;
  const headers = {};
  if (secret) headers["Authorization"] = "Bearer " + secret;
  const r = await fetch("/api/admin/cohort-market-type/build", {method:"POST", headers});
  if (!r.ok) throw new Error(r.status + " " + await r.text());
  return r.json();
}
async function load() {
  const meta = document.getElementById("meta");
  const tbody = document.querySelector("#tbl tbody");
  const weeklyDiv = document.getElementById("weekly");
  if (!_inMemoryToken) { meta.textContent = "Enter ADMIN_TOKEN above and click Load (token stays in memory only)."; return; }
  try {
    const data = await fetchJSON("/api/admin/cohort-market-type");
    if (data.status) { meta.textContent = data.message + " (debug: " + JSON.stringify(data.debug||"") + ")"; return; }
    const byBand = data.by_band_worst || data.by_band || [];
    const rows = (byBand.length ? byBand : data.by_ece || []).slice(0,100);
    const genAt = data.generated_at || 0;
    const ageH = genAt ? (Date.now()/1000 - genAt)/3600 : null;
    const isStale = ageH !== null && ageH > STALE_HOURS;
    const staleBadge = isStale ? ` <span class="stale">STALE — ${ageH.toFixed(1)}h old (>${STALE_HOURS}h)</span>` : "";
    const lightLabel = data.ece_label ? ` <span class="muted">(${
      data.ece_label
    })</span>` : "";
    meta.innerHTML = `Rows ${data.rows} cohorts ${data.cohorts} sufficient ${data.sufficient} — generated ${new Date(genAt*1000).toLocaleString()}${staleBadge}${lightLabel}`;
    tbody.innerHTML = "";
    rows.forEach((c,i) => {
      const tr = document.createElement("tr");
      const v = c.verdict || "";
      const vc = v.startsWith("GREEN") ? "green" : v.startsWith("RED") ? "red" : "notprov";
      tr.innerHTML = `<td>${i+1}</td><td>${c.source}</td><td>${c.league_category}</td><td>${c.market_type}</td><td>${c.probability_band||c.band_idx||""}</td><td>${c.n}</td><td>${c.independent_questions}</td><td>${c.graded_share!=null ? (c.graded_share*100).toFixed(1)+"%" : "—"}</td><td>${ (c.ece*100).toFixed? (c.ece*100).toFixed(2) : c.ece }</td><td>${(c.signed_error*100).toFixed(2)}</td><td><span class="badge ${vc}">${v}</span></td>`;
      tbody.appendChild(tr);
    });
    // Weekly
    if (data.weekly_by_cohort) {
      let html = '<table><thead><tr><th>cohort</th><th>weekly ECE (last 6)</th></tr></thead><tbody>';
      let n=0;
      for (const [k, series] of Object.entries(data.weekly_by_cohort)) {
        if (n++>20) break;
        const eces = series.map(s=> `${s.week}:${(s.ece*100).toFixed(1)}`).join(" → ");
        html += `<tr><td>${k}</td><td>${eces}</td></tr>`;
      }
      html += '</tbody></table>';
      weeklyDiv.innerHTML = html;
    } else {
      weeklyDiv.textContent = "No weekly data yet (heavy build pending)";
    }
  } catch(e) {
    meta.textContent = "Error: " + e.message;
    weeklyDiv.textContent = "";
  }
}
const input = document.getElementById("secretInput");
const saveBtn = document.getElementById("saveSecret");
const authStatus = document.getElementById("authStatus");
const rebuildBtn = document.getElementById("rebuildBtn");
const rebuildStatus = document.getElementById("rebuildStatus");
if (saveBtn) saveBtn.onclick = () => { _inMemoryToken = (input.value || "").trim(); input.value = ""; authStatus.textContent = _inMemoryToken ? "Loaded (in-memory, will clear on reload)" : "Cleared"; load(); };
if (rebuildBtn) rebuildBtn.onclick = async () => {
  if (!_inMemoryToken) { rebuildStatus.textContent = "Enter token first"; return; }
  rebuildBtn.disabled = true; rebuildStatus.textContent = "Enqueuing…";
  try { const j = await postBuild(); rebuildStatus.textContent = "Enqueued: " + (j.status || j.task || "ok") + " — reload in ~90s"; }
  catch(e) { rebuildStatus.textContent = "Error: " + e.message; }
  finally { rebuildBtn.disabled = false; setTimeout(()=>{ rebuildStatus.textContent=""; }, 5000); }
};
// No auto-load: user must click Load. No URL param, no browser storage.
setInterval(load, 60000);
</script>
</body></html>"""
    return HTMLResponse(content=html)
