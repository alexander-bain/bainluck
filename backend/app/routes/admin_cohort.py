"""Admin cohort-market-type ECE table — league×source×market_type×band × week, sorted descending by ECE."""
import json
import time
from fastapi import APIRouter, Query, Request, BackgroundTasks
from fastapi import Depends
from fastapi.responses import JSONResponse, HTMLResponse
from app.routes.admin_utils import _check_admin_secret
from app.services import get_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

_CACHE_KEY = "bainluck:cohort_market_type"
_CACHE_TTL = 86400

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
    secret: str = Query(""),
):
    _check_admin_secret(secret, request=request)
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
    secret: str = Query(""),
):
    """Lightweight approximation: source×market_type×league ECE without full dedup.
    Runs in <10s on web, so it can be served synchronously. Useful to test
    your hypothesis immediately while the canonical build completes."""
    _check_admin_secret(secret, request=request)
    from sqlalchemy import text
    # Direct scan of resolved outcomes with usable prob, no virtual-market/field logic
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
        LIMIT 200000
    """))).all()
    # Compute ECE per cohort in Python (10 bins, n-weighted)
    from collections import defaultdict
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r.source, r.league, r.market_type)].append((float(r.prob), int(r.is_winner)))
    out=[]
    for (src,league,mt), lst in grouped.items():
        n=len(lst)
        if n<30:
            continue
        # 10 bins
        bins=[[] for _ in range(10)]
        for p,a in lst:
            bins[min(int(p*10),9)].append((p,a))
        total_ece=0.0
        for b in bins:
            if not b: continue
            avg_p=sum(p for p,_ in b)/len(b)
            avg_a=sum(a for _,a in b)/len(b)
            total_ece+= len(b)/n * abs(avg_p-avg_a)
        ece= round(total_ece*100,2)
        avg_p=sum(p for p,_ in lst)/n
        avg_a=sum(a for _,a in lst)/n
        out.append({"source":src,"league_category":league,"market_type":mt,"n":n,"ece":ece,"pred":round(avg_p,3),"actual":round(avg_a,3),"gap_pp":round((avg_p-avg_a)*100,2)})
    out=sorted(out, key=lambda x: x["ece"], reverse=True)
    return {"rows_scanned": len(rows), "cohorts": len(grouped), "sufficient": len(out), "by_ece": out[:100], "note": "light approximation without dedup/field-normalization; canonical heavy build is more accurate"}

@router.get("/admin/cohort-market-type/debug")
async def cohort_market_type_debug(
    request: Request,
    secret: str = Query(""),
):
    _check_admin_secret(secret, request=request)
    return {"cached": _load_cached() is not None, "debug": _load_debug()}

@router.post("/admin/cohort-market-type/build")
async def cohort_market_type_build(
    request: Request,
    background_tasks: BackgroundTasks,
    secret: str = Query(""),
):
    _check_admin_secret(secret, request=request)
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
    secret: str = Query(""),
):
    _check_admin_secret(secret, request=request)
    cached = _load_cached()
    if cached:
        return cached
    return JSONResponse(status_code=202, content={"status": "no cached table yet"})


@router.get("/admin/cohort-market-type/weekly")
async def cohort_market_type_weekly(
    request: Request,
    secret: str = Query(""),
):
    _check_admin_secret(secret, request=request)
    cached = _load_cached()
    if cached and "weekly_by_cohort" in cached:
        return {"weekly_by_cohort": cached["weekly_by_cohort"], "weekly": cached.get("weekly", []), "generated_at": cached.get("generated_at")}
    return JSONResponse(status_code=202, content={"status": "no cached weekly yet, POST /build first"})


@router.get("/admin/cohort-views", response_class=HTMLResponse)
async def cohort_views_html(request: Request, secret: str = Query("")):
    _check_admin_secret(secret, request=request)
    html = """<!doctype html>
<html><head><meta charset="utf-8"><title>Cohort Views — ECE by source×league×type×band × week</title>
<meta http-equiv="refresh" content="60">
<style>
body{{font-family:system-ui,sans-serif;margin:24px;background:#0a0a0a;color:#e5e5e5}}
a{{color:#60a5fa}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border:1px solid #333;padding:6px 8px;text-align:left;white-space:nowrap}}
th{{background:#1a1a1a;position:sticky;top:0}}
tr:nth-child(even){{background:#111}}
.badge{{padding:2px 6px;border-radius:4px;font-size:11px}}
.green{{background:#065f46;color:#a7f3d0}}
.red{{background:#7f1d1d;color:#fecaca}}
.notprov{{background:#422006;color:#fde68a}}
.muted{{color:#9ca3af}}
</style></head><body>
<h1>Cohort Views — league × source × market_type × band <span class="muted" style="font-weight:normal">sorted desc by ECE</span></h1>
<p class="muted">Auto-refreshes every 60s when authorized. Heavy table built in worker (Celery heavy queue, ~90s). Graded share &lt;50% ⇒ <code>NOT-PROVABLE-selection-biased</code> per today's ruling. Band = 0-10%..90-100% (4th axis). Weekly trend for Monday scoreboard below.</p>
<p class="muted">Auth: paste <code>ADMIN_TOKEN</code> below — it is held in memory only, sent as <code>Authorization: Bearer</code>, never in the URL or browser storage. Prefer the Next.js page at <a href="/admin/cohort-views">/admin/cohort-views</a> for normal viewing.</p>
<div id="auth" class="muted" style="margin:8px 0">Admin token (Bearer, in-memory only): <input id="secretInput" type="password" placeholder="paste ADMIN_TOKEN, not stored" style="background:#1a1a1a;color:#e5e5e5;border:1px solid #333;padding:4px 8px;width:360px"> <button id="saveSecret" style="padding:4px 8px">Load</button> <span id="authStatus" class="muted"></span></div>
<div id="meta" class="muted">Not loaded — enter token and click Load.</div>
<h2>Top by ECE (heavy, with band + graded_share)</h2>
<table id="tbl"><thead><tr><th>rank</th><th>source</th><th>league</th><th>type</th><th>band</th><th>n</th><th>q</th><th>graded_share</th><th>ECE</th><th>gap pp</th><th>verdict</th></tr></thead><tbody></tbody></table>
<h2>Weekly — last 6 weeks per cohort (is it improving?)</h2>
<div id="weekly" class="muted">Loading weekly…</div>
<script>
let _inMemoryToken = "";
async function fetchJSON(url) {
  const secret = _inMemoryToken;
  const headers = {};
  if (secret) headers["Authorization"] = "Bearer " + secret;
  const r = await fetch(url, {headers});
  if (!r.ok) throw new Error(r.status + " " + await r.text());
  return r.json();
}}
async function load() {{
  const meta = document.getElementById("meta");
  const tbody = document.querySelector("#tbl tbody");
  const weeklyDiv = document.getElementById("weekly");
  if (!_inMemoryToken) { meta.textContent = "Enter ADMIN_TOKEN above and click Load (token stays in memory only)."; return; }
  try {{
    const data = await fetchJSON("/api/admin/cohort-market-type");
    if (data.status) {{ meta.textContent = data.message + " (debug: " + JSON.stringify(data.debug||"") + ")"; return; }}
    const byBand = data.by_band_worst || data.by_band || [];
    const rows = (byBand.length ? byBand : data.by_ece || []).slice(0,100);
    meta.textContent = `Rows ${{data.rows}} cohorts ${{data.cohorts}} sufficient ${{data.sufficient}} — generated ${{new Date((data.generated_at||0)*1000).toLocaleString()}}`;
    tbody.innerHTML = "";
    rows.forEach((c,i) => {{
      const tr = document.createElement("tr");
      const v = c.verdict || "";
      const vc = v.startsWith("GREEN") ? "green" : v.startsWith("RED") ? "red" : "notprov";
      tr.innerHTML = `<td>${{i+1}}</td><td>${{c.source}}</td><td>${{c.league_category}}</td><td>${{c.market_type}}</td><td>${{c.probability_band||c.band_idx||""}}</td><td>${{c.n}}</td><td>${{c.independent_questions}}</td><td>${{c.graded_share!=null ? (c.graded_share*100).toFixed(1)+"%" : "—"}}</td><td>${{ (c.ece*100).toFixed? (c.ece*100).toFixed(2) : c.ece }}</td><td>${{(c.signed_error*100).toFixed(2)}}</td><td><span class="badge ${{vc}}">${{v}}</span></td>`;
      tbody.appendChild(tr);
    }});
    // Weekly
    if (data.weekly_by_cohort) {{
      let html = '<table><thead><tr><th>cohort</th><th>weekly ECE (last 6)</th></tr></thead><tbody>';
      let n=0;
      for (const [k, series] of Object.entries(data.weekly_by_cohort)) {{
        if (n++>20) break;
        const eces = series.map(s=> `${{s.week}}:${{(s.ece*100).toFixed(1)}}`).join(" → ");
        html += `<tr><td>${{k}}</td><td>${{eces}}</td></tr>`;
      }}
      html += '</tbody></table>';
      weeklyDiv.innerHTML = html;
    }} else {{
      weeklyDiv.textContent = "No weekly data yet (heavy build pending)";
    }}
  }} catch(e) {{
    meta.textContent = "Error: " + e.message;
    weeklyDiv.textContent = "";
  }}
}}
const input = document.getElementById("secretInput");
const saveBtn = document.getElementById("saveSecret");
const authStatus = document.getElementById("authStatus");
if (saveBtn) saveBtn.onclick = () => { _inMemoryToken = (input.value || "").trim(); input.value = ""; authStatus.textContent = _inMemoryToken ? "Loaded (in-memory, will clear on reload)" : "Cleared"; load(); };
// No auto-load: user must click Load. No URL param, no browser storage.
setInterval(load, 60000);
</script>
</body></html>"""
    return HTMLResponse(content=html)
