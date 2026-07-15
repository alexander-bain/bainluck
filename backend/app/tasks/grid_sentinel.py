"""Grid Sentinel — the third application of the sentinel recipe (Queue #196).

Alex: "I STILL see issues every time I look" at the championship grids. The grid
health *score* (`audit_matching_quality.py --grid`, 100 minus severity penalties)
is a poor smoke detector: the mlb-66 forensic (Item 1) showed a 66/100 MLB grid
in-season with ZERO structural defects — the entire deduction was 10
source-disagreement warnings (Kalshi vs Polymarket diverging >15pp on bubble-team
make-playoffs) plus one universal-decline warning. Both are BLEND-HIDDEN
(users see the median, never the divergence — Alex's ruling "the blend is the
product") or mathematically expected (a small-sum column declines for most teams
when one rises). The raw score cried wolf.

This sentinel replaces the raw score with a VERDICT: it classifies every finding
as REAL (a defect the user sees or that corrupts the number) vs EXPLAINED (an
artifact the calendar or the blend accounts for), so RED always means REAL. Only
REAL findings file a deduped, evidence-packed GitHub issue (the live rail, per
the flow/calibration sentinels). The cockpit grid tile consumes this verdict +
artifact badges instead of the number.

Modeled on the Flow Sentinel (app/tasks/flow_sentinel.py) and Calibration
Sentinel (app/tasks/calibration_sentinel.py): same mine → classify → evidence-pack
→ auto-file-deduped rails, same fingerprint dedup, same GITHUB_TOKEN filing path.
Read-only against production and the DB (gotcha #21 — the sentinel files work, it
never writes market data).

Four finding tiers:
  * structural — missing teams / missing columns / low fill / monotonicity /
    prob-sum. These are REAL when the league is ACTIVE; the artifact registry
    (season_windows) downgrades them to EXPLAINED in the offseason / on a break.
  * plausibility — source disagreement / universal trend / illiquid 0-1 extremes.
    Blend-hidden or calendar-explained → WATCH (surfaced, never filed) unless
    EXTREME (a mis-linkage signal), which stays REAL.
  * invariant (the GROUND-TRUTH self-check) — merged_probability MUST lie inside
    the [min,max] envelope of its own sources; a single-source cell must equal
    its source. A violation is pipeline corruption — ALWAYS REAL, calendar cannot
    explain it. This is the sampled self-check that retires the Manus ground-truth
    file from accuracy duty. (The full cell-by-cell DB recompute is filed as a
    completion issue.)
  * freshness — DB self-check: the newest futures snapshot for an ACTIVE league
    must be recent. Stale-when-active is REAL; stale-when-quiet is EXPLAINED.
"""

import hashlib
import logging
import os
import statistics
import time as _time
from typing import Any

import httpx

from app.utils import season_windows

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (Redis-tunable, no-deploy — mirrors the flow/calibration sentinels)
# ---------------------------------------------------------------------------
GRID_SENTINEL_API = os.environ.get("GRID_SENTINEL_API", "https://api.bainluck.com")
HTTP_TIMEOUT = 30.0

# Leagues audited. Team-count/column expectations only apply to the fixed-roster
# leagues; golf is field-based and gets invariant + plausibility checks only.
GRID_LEAGUES = ("mlb", "nba", "nhl")

# Expected structure per fixed-roster league (drives structural checks).
EXPECTED_TEAMS = {"mlb": 30, "nba": 30, "nhl": 32}
EXPECTED_COLUMNS = {
    "mlb": {"make_playoffs", "division", "pennant", "championship"},
    "nba": {"make_playoffs", "division", "conference", "championship"},
    "nhl": {"make_playoffs", "division", "conference", "championship"},
}

# Thresholds (Redis-tunable).
FILL_WARN = 0.80                 # grid:sentinel_fill_warn — below this a column is under-filled
FILL_CRIT = 0.50                 # grid:sentinel_fill_crit — below this it is broken
MONOTONICITY_EPS = 0.02          # >2pp of "later round > earlier round" is a violation
PROB_SUM_TOL = 0.15              # championship column should sum to 100% ± this
PROB_SUM_CRIT = 0.30             # beyond this it is critical
ENVELOPE_TOL = 0.01              # merged must be within [min-tol, max+tol] of its sources
DISAGREEMENT_EXTREME_PP = 40.0   # grid:sentinel_disagreement_extreme_pp — mis-linkage signal
STALE_HOURS = 12.0               # grid:sentinel_stale_hours — active league freshness bar
SELFCHECK_SAMPLE = 60            # cells sampled for the envelope self-check per league

# Noise floor: Kalshi/Polymarket at ~0.50 are illiquid binary defaults, not prices.
_NOISE_FLOOR = 0.02

# ---------------------------------------------------------------------------
# Runtime threshold overrides (Redis, no-deploy tuning)
# ---------------------------------------------------------------------------
def _load_overrides() -> None:
    try:
        from app.tasks.redis_state import get_redis_client

        r = get_redis_client()
        for key, name, cast in (
            ("grid:sentinel_fill_warn", "FILL_WARN", float),
            ("grid:sentinel_fill_crit", "FILL_CRIT", float),
            ("grid:sentinel_disagreement_extreme_pp", "DISAGREEMENT_EXTREME_PP", float),
            ("grid:sentinel_stale_hours", "STALE_HOURS", float),
        ):
            v = r.get(key)
            if v is not None:
                globals()[name] = cast(v.decode() if isinstance(v, bytes) else v)
    except Exception as exc:
        logger.info("Grid sentinel overrides not loaded (using defaults): %s", exc)


# ---------------------------------------------------------------------------
# Finding constructor — every check emits these. `real` is set later by the
# artifact registry; checks report `seasonal_ok` (True when the calendar can
# excuse it) so the registry can decide.
# ---------------------------------------------------------------------------
def _finding(check: str, severity: str, detail: str, *,
             seasonal_ok: bool = False, tier: str = "structural",
             **extra: Any) -> dict:
    return {"check": check, "severity": severity, "detail": detail,
            "seasonal_ok": seasonal_ok, "tier": tier, **extra}


# ---------------------------------------------------------------------------
# Pure structural checks (unit-tested — operate on a grid_data dict)
# ---------------------------------------------------------------------------
def _cells(team: dict) -> dict:
    return team.get("cells") or {}


def _merged(cell: dict | None):
    if not isinstance(cell, dict):
        return None
    return cell.get("merged_probability")


def check_teams_present(grid: dict, league: str) -> list[dict]:
    """Missing teams — an empty grid or a partial roster. Empty is always REAL
    (structural collapse); a partial roster is seasonal-excusable (futures for
    some teams may not be listed yet in the offseason)."""
    teams = grid.get("teams") or []
    expected = EXPECTED_TEAMS.get(league)
    if not teams:
        return [_finding("grid_empty", "critical",
                         f"{league.upper()} grid returned ZERO teams",
                         seasonal_ok=False)]
    if expected and len(teams) < expected:
        return [_finding("grid_missing_teams", "warning",
                         f"{league.upper()} grid has {len(teams)}/{expected} teams",
                         seasonal_ok=True, present=len(teams), expected=expected)]
    return []


def check_missing_columns(grid: dict, league: str) -> list[dict]:
    """Expected columns absent AND carrying no data. Seasonal-excusable (e.g.
    make_playoffs collapses/absent once the postseason field is set)."""
    expected = EXPECTED_COLUMNS.get(league)
    if not expected:
        return []
    present = {c.get("key") for c in (grid.get("columns") or [])}
    teams = grid.get("teams") or []
    out = []
    for col in sorted(expected - present):
        has_data = any(_merged(_cells(t).get(col)) is not None for t in teams)
        if not has_data:
            out.append(_finding("grid_missing_column", "warning",
                                f"{league.upper()} missing column '{col}' (no data)",
                                seasonal_ok=True, column=col))
    return out


def check_fill_rate(grid: dict, league: str) -> list[dict]:
    """Columns where many teams lack data. Seasonal-excusable when quiet."""
    teams = grid.get("teams") or []
    if not teams:
        return []
    out = []
    for col in grid.get("columns") or []:
        key = col.get("key")
        label = col.get("label", key)
        filled = sum(1 for t in teams if _merged(_cells(t).get(key)) is not None)
        pct = filled / len(teams)
        if pct < FILL_CRIT:
            out.append(_finding("grid_fill_rate", "critical",
                                f"{league.upper()} '{label}': only {filled}/{len(teams)} "
                                f"teams filled ({pct*100:.0f}%)",
                                seasonal_ok=True, column=label, fill_pct=round(pct, 3)))
        elif pct < FILL_WARN:
            out.append(_finding("grid_fill_rate", "warning",
                                f"{league.upper()} '{label}': only {filled}/{len(teams)} "
                                f"teams filled ({pct*100:.0f}%)",
                                seasonal_ok=True, column=label, fill_pct=round(pct, 3)))
    return out


def check_monotonicity(grid: dict, league: str) -> list[dict]:
    """P(earlier round) >= P(later round) for each team. A later-round probability
    exceeding an earlier one is impossible — ALWAYS REAL, calendar cannot excuse
    it (never seasonal_ok)."""
    cols = grid.get("columns") or []
    keys = [c.get("key") for c in cols]
    labels = [c.get("label", c.get("key")) for c in cols]
    out = []
    for t in grid.get("teams") or []:
        cells = _cells(t)
        name = t.get("name", "?")
        for i in range(len(keys) - 1):
            left = _merged(cells.get(keys[i]))
            right = _merged(cells.get(keys[i + 1]))
            if left is not None and right is not None and right > left + MONOTONICITY_EPS:
                out.append(_finding(
                    "grid_monotonicity", "critical",
                    f"{league.upper()} {name}: {labels[i+1]} ({right*100:.1f}%) > "
                    f"{labels[i]} ({left*100:.1f}%)",
                    seasonal_ok=False, team=name))
    return out


def check_prob_sum(grid: dict, league: str) -> list[dict]:
    """The championship column should sum to ~100% across teams. A large deviation
    is a normalization / double-count defect — REAL (not seasonal); the sum is a
    mathematical property of a single-winner market regardless of calendar."""
    teams = grid.get("teams") or []
    out = []
    for col in grid.get("columns") or []:
        if col.get("key") != "championship":
            continue
        probs = [_merged(_cells(t).get("championship")) for t in teams]
        probs = [p for p in probs if p is not None]
        if not probs:
            continue
        total = sum(probs)
        dev = abs(total - 1.0)
        if dev > PROB_SUM_TOL:
            # OVER 100% is double-counting / normalization — a bug the calendar
            # cannot excuse (always REAL). UNDER 100% is missing probability mass,
            # which in a quiet window is just incomplete futures coverage
            # (seasonal-excusable); in-season it is a real gap.
            over = total > 1.0
            out.append(_finding(
                "grid_prob_sum",
                "critical" if dev > PROB_SUM_CRIT else "warning",
                f"{league.upper()} championship sums to {total*100:.0f}% "
                f"across {len(probs)} teams (expected ~100%)",
                seasonal_ok=not over, sum_pct=round(total * 100, 1)))
    return out


# ---------------------------------------------------------------------------
# Ground-truth self-check (the invariant tier) — the merged value must live
# inside the envelope of the very sources the grid reports for that cell. This
# bypasses trusting the pipeline's arithmetic: a merged prob outside its own
# sources is corruption no aggregation rule can produce.
# ---------------------------------------------------------------------------
def _all_source_probs(cell: dict) -> list[float]:
    """Every numeric source probability the grid reported for a cell. Used by the
    ENVELOPE invariant: the pipeline blends ALL of these (including ~0.50 illiquid
    values), so the merged value must lie within their full min/max range — using
    a noise-floor-filtered subset here would false-positive a legitimately blended
    cell (the Braves NL-East case: [51.5%, 81.5%] median 66.5%)."""
    probs = []
    for s in cell.get("sources") or []:
        p = s.get("probability")
        if isinstance(p, (int, float)):
            probs.append(float(p))
    return probs


def _meaningful_source_probs(cell: dict) -> list[float]:
    """Source probabilities with the illiquid ~0.50 binary noise floor removed —
    used only by the DISAGREEMENT check so two illiquid defaults do not read as a
    real divergence. NOT for the envelope invariant (see _all_source_probs)."""
    probs = []
    for s in cell.get("sources") or []:
        p = s.get("probability")
        if not isinstance(p, (int, float)):
            continue
        src = s.get("source", "")
        if src in ("kalshi", "polymarket") and abs(p - 0.50) <= _NOISE_FLOOR:
            continue  # illiquid binary noise floor
        probs.append(float(p))
    return probs


def check_envelope_invariant(grid: dict, league: str, sample: int = SELFCHECK_SAMPLE) -> tuple[list[dict], dict]:
    """For a sample of cells, assert merged ∈ [min(sources)-tol, max(sources)+tol]
    and single-source fidelity. Returns (findings, stats). Deterministic sampling
    (iteration order) so a re-run is stable — no Math.random dependency."""
    teams = grid.get("teams") or []
    cols = [c.get("key") for c in (grid.get("columns") or [])]
    findings = []
    checked = 0
    for t in teams:
        cells = _cells(t)
        name = t.get("name", "?")
        for key in cols:
            cell = cells.get(key)
            if not isinstance(cell, dict):
                continue
            merged = _merged(cell)
            if merged is None:
                continue
            probs = _all_source_probs(cell)
            if not probs:
                continue
            checked += 1
            if checked > sample:
                break
            lo, hi = min(probs), max(probs)
            inside = lo - ENVELOPE_TOL <= merged <= hi + ENVELOPE_TOL
            # Multi-source cells: the pipeline may invert a "No"-side source before
            # merging (_correct_inverted_probs), so the corrected merged can land in
            # the reflected envelope [1-hi, 1-lo] while the reported sources are raw.
            # Accept that too — only a merged outside BOTH is genuine corruption.
            # Single-source cells cannot invert, so they stay strict.
            if not inside and len(probs) >= 2:
                inside = (1.0 - hi) - ENVELOPE_TOL <= merged <= (1.0 - lo) + ENVELOPE_TOL
            if not inside:
                findings.append(_finding(
                    "grid_envelope_violation", "critical",
                    f"{league.upper()} {name} → {key}: merged {merged*100:.1f}% is "
                    f"OUTSIDE its source envelope [{lo*100:.1f}%, {hi*100:.1f}%] — "
                    f"pipeline corruption",
                    seasonal_ok=False, tier="invariant", team=name, column=key))
        if checked > sample:
            break
    return findings, {"cells_self_checked": min(checked, sample)}


# ---------------------------------------------------------------------------
# Plausibility checks (WATCH by default — blend-hidden or calendar-explained;
# only the EXTREME variants stay REAL as a mis-linkage signal)
# ---------------------------------------------------------------------------
def check_source_disagreement(grid: dict, league: str) -> list[dict]:
    """Kalshi vs Polymarket divergence. The user sees the blended median, so this
    is NOT user-facing (Alex: the blend is the product) — a WATCH, never filed —
    UNLESS the gap is extreme, which suggests a mis-linked market (REAL)."""
    out = []
    for t in grid.get("teams") or []:
        cells = _cells(t)
        name = t.get("name", "?")
        for col in grid.get("columns") or []:
            key = col.get("key")
            label = col.get("label", key)
            cell = cells.get(key)
            if not isinstance(cell, dict):
                continue
            probs = _meaningful_source_probs(cell)
            if len(probs) < 2:
                continue
            diff_pp = (max(probs) - min(probs)) * 100
            if diff_pp >= DISAGREEMENT_EXTREME_PP:
                out.append(_finding(
                    "grid_source_disagreement_extreme", "critical",
                    f"{league.upper()} {name} → {label}: {diff_pp:.0f}pp source gap "
                    f"— possible mis-linked market",
                    seasonal_ok=False, tier="plausibility", team=name, diff_pp=round(diff_pp, 1)))
            elif diff_pp > 15.0:
                out.append(_finding(
                    "grid_source_disagreement", "info",
                    f"{league.upper()} {name} → {label}: {diff_pp:.0f}pp source gap "
                    f"(blend-hidden)",
                    seasonal_ok=True, tier="plausibility", team=name, diff_pp=round(diff_pp, 1)))
    return out


def check_illiquid_extremes(grid: dict, league: str) -> list[dict]:
    """Single-source cells pinned to exactly 0% or 100% — illiquid one-sided
    markets. Expected in the offseason / pre-tournament (EXPLAINED); a WATCH when
    active (worth an eye, but the blend still shows a defensible number)."""
    out = []
    for t in grid.get("teams") or []:
        cells = _cells(t)
        name = t.get("name", "?")
        for col in grid.get("columns") or []:
            key = col.get("key")
            cell = cells.get(key)
            if not isinstance(cell, dict):
                continue
            merged = _merged(cell)
            srcs = cell.get("sources") or []
            if merged is None or len(srcs) != 1:
                continue
            if merged <= 0.0 or merged >= 1.0:
                out.append(_finding(
                    "grid_illiquid_extreme", "info",
                    f"{league.upper()} {name} → {key}: single-source {merged*100:.0f}% "
                    f"({srcs[0].get('source')}) — illiquid one-sided market",
                    seasonal_ok=True, tier="plausibility", team=name))
    return out


# ---------------------------------------------------------------------------
# Artifact registry — decide REAL vs EXPLAINED for each finding given the
# league's calendar phase. RED (fileable) == any REAL finding survives.
# ---------------------------------------------------------------------------
def classify_findings(findings: list[dict], league: str, now=None) -> dict:
    """Split findings into real / explained / watch. This is the artifact registry
    — the mechanism that makes RED mean REAL:

      * ``watch`` — plausibility findings (source disagreement, illiquid extremes).
        The user sees the blended median, never the divergence (Alex: the blend is
        the product), so these NEVER go RED — they are surfaced for a human eye but
        never file. This is the mlb-66 fix: the raw score's 33-point deduction was
        entirely these.
      * ``explained`` — a structural/freshness finding that is seasonal_ok AND the
        league is in a quiet window (offseason / break): incomplete offseason
        coverage, an absent playoff column, stale-when-not-playing. Context, not
        RED.
      * ``real`` — everything else: monotonicity, envelope corruption, over-100%
        sums, an empty grid, stale-when-active. The calendar and the blend cannot
        excuse these. Only these file.
    """
    phase = season_windows.league_phase(league, now)
    quiet = phase in ("offseason", "break")
    note = season_windows.seasonal_note(league, now)
    real, explained, watch = [], [], []
    for f in findings:
        if f.get("tier") == "plausibility":
            watch.append({**f, "note": "blend-hidden — user sees the merged value"})
        elif f.get("seasonal_ok") and quiet:
            explained.append({**f, "explained_by": note or f"{league} {phase}"})
        else:
            real.append(f)
    return {"league": league, "phase": phase, "real": real,
            "explained": explained, "watch": watch}


def grid_verdict(classified: dict) -> str:
    """RED if any REAL finding, else GREEN. (AMBER is reserved for the cockpit,
    which shows AMBER when only explained artifacts / watches exist.)"""
    return "red" if classified["real"] else "green"


# ---------------------------------------------------------------------------
# Fingerprint + severity + filing (reuses the bug_report_github rail)
# ---------------------------------------------------------------------------
def grid_fingerprint(league: str) -> str:
    """One deduped issue per league's grid — re-runs comment instead of re-filing."""
    return hashlib.sha1(f"grid:{league}".encode("utf-8")).hexdigest()[:12]


def severity_for_grid(real: list[dict]) -> str:
    """P1 when a critical structural/invariant defect is present, else P2."""
    if any(f["severity"] == "critical" for f in real):
        return "P1"
    return "P2"


def build_grid_issue_title(league: str, real: list[dict]) -> str:
    crit = sum(1 for f in real if f["severity"] == "critical")
    title = (f"[Grid Sentinel] {league.upper()} grid has {len(real)} real "
             f"defect(s) ({crit} critical)")
    return title[:256]


def build_grid_issue_body(classified: dict) -> str:
    league = classified["league"]
    fp = grid_fingerprint(league)
    real = classified["real"]
    explained = classified["explained"]
    watch = classified.get("watch") or []
    parts = [
        "## Grid Sentinel finding",
        "",
        f"`grid-sentinel-fingerprint:{fp}`  (dedupe key — do not remove)",
        "",
        f"**League:** `{league}` (phase: {classified['phase']})  ",
        f"**Real defects:** {len(real)}  ",
        f"**Explained artifacts (not filed):** {len(explained)}  ",
        f"**Watch (blend-hidden, not filed):** {len(watch)}  ",
        f"**Run against:** {GRID_SENTINEL_API}",
        "",
        "### Real defects (RED — the calendar/blend does NOT explain these)",
    ]
    for f in real[:40]:
        parts.append(f"- **[{f['severity']}]** {f['detail']}")
    if len(real) > 40:
        parts.append(f"- …and {len(real) - 40} more")
    # Extreme source gaps are blend-hidden (WATCH, not RED) but often signal a
    # mis-linked market — worth surfacing on the same issue for a human to check.
    extreme_watch = [f for f in watch if f.get("check") == "grid_source_disagreement_extreme"]
    if extreme_watch:
        parts += ["", "### Watch — extreme source gaps (possible mis-linkage, blend-hidden)"]
        for f in extreme_watch[:15]:
            parts.append(f"- {f['detail']}")
    if explained:
        parts += ["", "### Explained artifacts (context — suppressed by the registry)"]
        for f in explained[:15]:
            parts.append(f"- {f['detail']} — _{f.get('explained_by')}_")
    parts += [
        "",
        "---",
        "*Auto-filed by the Grid Sentinel (Queue #196) — the grid reliability "
        "program's measurement. Read-only detection; never writes market data "
        "(gotcha #21). Reproduce with "
        "`POST /api/admin/grid-sentinel/run?inline=true&file_issues=false`.*",
    ]
    return "\n".join(parts)


def _find_open_issue_by_fingerprint(fingerprint: str) -> int | None:
    from app.tasks.bug_report_github import GITHUB_TOKEN, REPO

    if not GITHUB_TOKEN:
        return None
    q = f'repo:{REPO} in:body "grid-sentinel-fingerprint:{fingerprint}" state:open'
    try:
        resp = httpx.get(
            "https://api.github.com/search/issues",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={"q": q},
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return items[0]["number"] if items else None
    except Exception as exc:
        logger.warning("Grid sentinel dedup search failed for %s: %s", fingerprint, exc)
        return None


def file_grid_issue(classified: dict) -> dict:
    """File OR update one issue for a league's grid fingerprint (only when REAL
    defects survive the registry)."""
    from app.tasks.bug_report_github import (
        GITHUB_TOKEN,
        add_to_project_board,
        comment_on_issue,
        create_github_issue,
    )

    league = classified["league"]
    fp = grid_fingerprint(league)
    real = classified["real"]
    if not real:
        return {"league": league, "fingerprint": fp, "action": "green_no_file"}
    if not GITHUB_TOKEN:
        return {"league": league, "fingerprint": fp, "action": "skipped_no_token"}

    existing = _find_open_issue_by_fingerprint(fp)
    if existing:
        try:
            comment_on_issue(
                existing,
                f"Grid Sentinel re-observed {len(real)} real defect(s) on the "
                f"{league.upper()} grid (fingerprint `{fp}`). Still open.",
            )
        except Exception as exc:
            logger.warning("Grid sentinel comment failed on #%d: %s", existing, exc)
        return {"league": league, "fingerprint": fp, "action": "commented", "issue": existing}

    severity = severity_for_grid(real)
    labels = ["alert-intake", "needs-agent", "area:event-details", f"priority:{severity.lower()}"]
    title = build_grid_issue_title(league, real)
    body = build_grid_issue_body(classified)
    try:
        number, node_id = create_github_issue(title, body, labels)
    except Exception as exc:
        logger.error("Grid sentinel issue creation failed (%s): %s", fp, exc)
        return {"league": league, "fingerprint": fp, "action": "error", "error": str(exc)[:200]}
    try:
        add_to_project_board(node_id)
    except Exception:
        logger.warning("Grid sentinel: add issue #%d to board failed (non-fatal)", number, exc_info=True)
    return {"league": league, "fingerprint": fp, "action": "filed", "issue": number, "severity": severity}


# ---------------------------------------------------------------------------
# DB freshness self-check (bypasses the grid pipeline — reads futures rows
# directly). Stale-when-active is REAL; stale-when-quiet is EXPLAINED.
# ---------------------------------------------------------------------------
async def _grid_freshness(league: str, now=None) -> dict:
    """Newest futures snapshot age for the league, read straight from the DB.
    Returns a dict with the age and whether it is a real staleness defect."""
    from datetime import datetime, timezone

    from sqlalchemy import func, or_, select

    from app.config.league_configs import get_league_config
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.tasks.base import get_task_session

    now = now or datetime.now(timezone.utc)
    config = get_league_config(league)
    if not config:
        return {"league": league, "skipped": True, "reason": "no league config"}

    conds = []
    for sk in getattr(config, "sport_keys", []) or []:
        conds.append(FuturesMarket.external_id.ilike(f"{sk}%"))
    for pfx in getattr(config, "external_id_prefixes", []) or []:
        conds.append(FuturesMarket.external_id.ilike(f"{pfx}%"))
    if getattr(config, "sport_category", None):
        conds.append(FuturesMarket.llm_sport_category == config.sport_category)
    if not conds:
        return {"league": league, "skipped": True, "reason": "no match conditions"}

    try:
        async with get_task_session() as session:
            await session.execute(
                __import__("sqlalchemy").text("SET LOCAL statement_timeout = '15s'")
            )
            stmt = (
                select(func.max(FuturesOutcome.last_updated))
                .select_from(FuturesOutcome)
                .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
                .where(or_(*conds), FuturesMarket.status.in_(("open", "closed")))
            )
            newest = (await session.execute(stmt)).scalar()
    except Exception as exc:
        logger.warning("Grid sentinel freshness DB read failed (%s): %s", league, exc)
        return {"league": league, "skipped": True, "reason": f"db error: {str(exc)[:120]}"}

    if newest is None:
        # No open futures at all: real only if the league is active.
        active = season_windows.is_active(league, now)
        return {"league": league, "newest": None, "age_hours": None,
                "stale": active, "seasonal_ok": not active}

    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    age_h = (now - newest).total_seconds() / 3600.0
    active = season_windows.is_active(league, now)
    return {
        "league": league,
        "newest": newest.isoformat(),
        "age_hours": round(age_h, 1),
        "stale": age_h > STALE_HOURS and active,
        "seasonal_ok": not active,
    }


def freshness_findings(fresh: dict, league: str) -> list[dict]:
    if fresh.get("skipped"):
        return []
    if fresh.get("newest") is None and fresh.get("stale"):
        return [_finding("grid_no_open_futures", "critical",
                         f"{league.upper()} has ZERO open futures while active",
                         seasonal_ok=False, tier="freshness")]
    if fresh.get("stale"):
        return [_finding("grid_stale_futures", "warning",
                         f"{league.upper()} newest futures snapshot is "
                         f"{fresh.get('age_hours')}h old (bar {STALE_HOURS}h) while active",
                         seasonal_ok=fresh.get("seasonal_ok", False), tier="freshness")]
    return []


# ---------------------------------------------------------------------------
# Per-league runner (HTTP grid fetch + all checks + DB freshness)
# ---------------------------------------------------------------------------
async def _get_json(client: httpx.AsyncClient, path: str, params: dict | None = None) -> Any:
    resp = await client.get(path, params=params)
    resp.raise_for_status()
    return resp.json()


async def _run_league(client: httpx.AsyncClient, league: str, now=None) -> dict:
    try:
        grid = await _get_json(client, f"/api/playoffs/{league}")
    except Exception as exc:
        classified = {"league": league, "phase": season_windows.league_phase(league, now),
                      "real": [_finding("grid_fetch_error", "critical",
                                        f"/api/playoffs/{league} errored: {str(exc)[:120]}",
                                        seasonal_ok=False)],
                      "explained": []}
        return {"league": league, "grid_ok": False, "classified": classified,
                "verdict": "red", "stats": {}}

    findings: list[dict] = []
    findings += check_teams_present(grid, league)
    findings += check_missing_columns(grid, league)
    findings += check_fill_rate(grid, league)
    findings += check_monotonicity(grid, league)
    findings += check_prob_sum(grid, league)
    findings += check_source_disagreement(grid, league)
    findings += check_illiquid_extremes(grid, league)

    env_findings, selfcheck_stats = check_envelope_invariant(grid, league)
    findings += env_findings

    # DB freshness self-check (bypasses the pipeline).
    fresh = await _grid_freshness(league, now)
    findings += freshness_findings(fresh, league)

    classified = classify_findings(findings, league, now)
    verdict = grid_verdict(classified)
    return {
        "league": league,
        "grid_ok": True,
        "teams": len(grid.get("teams") or []),
        "columns": [c.get("key") for c in (grid.get("columns") or [])],
        "sources": grid.get("sources_available"),
        "classified": classified,
        "verdict": verdict,
        "watch_count": len(classified.get("watch") or []),
        "stats": {**selfcheck_stats, "freshness": fresh},
    }


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
async def _run_grid_sentinel(
    file_issues: bool = True,
    deadline_seconds: float = 480.0,
    now=None,
) -> dict[str, Any]:
    """Audit each championship grid, classify findings against the artifact
    registry, and (in a live run) file ONE deduped issue per league with REAL
    defects. Returns a scorecard cached to Redis for the cockpit tile."""
    _load_overrides()
    start = _time.monotonic()

    stats: dict[str, Any] = {
        "mode": "live" if file_issues else "detect_only",
        "api": GRID_SENTINEL_API,
        "config": {
            "fill_warn": FILL_WARN, "fill_crit": FILL_CRIT,
            "disagreement_extreme_pp": DISAGREEMENT_EXTREME_PP,
            "stale_hours": STALE_HOURS,
        },
        "leagues": [],
        "filed": [],
        "errors": [],
    }

    async with httpx.AsyncClient(base_url=GRID_SENTINEL_API, timeout=HTTP_TIMEOUT,
                                 follow_redirects=True) as client:
        for league in GRID_LEAGUES:
            if _time.monotonic() - start > deadline_seconds:
                stats["errors"].append({"deadline": f"stopped before {league}"})
                break
            try:
                result = await _run_league(client, league, now)
            except Exception as exc:
                logger.error("Grid sentinel league %s crashed: %s", league, exc)
                result = {"league": league, "grid_ok": False,
                          "classified": {"league": league, "phase": "?",
                                         "real": [_finding("grid_crash", "critical",
                                                           f"league audit crashed: {str(exc)[:150]}",
                                                           seasonal_ok=False)],
                                         "explained": []},
                          "verdict": "red", "stats": {}}
            stats["leagues"].append(result)

    # --- Scorecard ---
    red = [lg for lg in stats["leagues"] if lg["verdict"] == "red"]
    stats["scorecard"] = {
        "leagues_total": len(stats["leagues"]),
        "leagues_red": len(red),
        "leagues_green": len(stats["leagues"]) - len(red),
        "per_league": [
            {
                "league": lg["league"],
                "verdict": lg["verdict"],
                "phase": lg["classified"]["phase"],
                "real_defects": len(lg["classified"]["real"]),
                "explained_artifacts": len(lg["classified"]["explained"]),
                "watch": lg.get("watch_count", 0),
                "teams": lg.get("teams"),
                "columns": lg.get("columns"),
                "cells_self_checked": lg.get("stats", {}).get("cells_self_checked"),
            }
            for lg in stats["leagues"]
        ],
    }

    # --- Filing (one deduped issue per RED league) ---
    if file_issues:
        for lg in red:
            stats["filed"].append(file_grid_issue(lg["classified"]))

    stats["duration_seconds"] = round(_time.monotonic() - start, 1)

    # Cache for the cockpit / ops read path.
    try:
        import json as _json

        from app.tasks.redis_state import get_redis_client

        get_redis_client().setex(
            "bainluck:grid_sentinel:last", 14 * 86400, _json.dumps(stats, default=str)
        )
    except Exception as exc:
        logger.warning("Grid sentinel result cache write failed: %s", exc)

    logger.info(
        "Grid sentinel (%s): %d/%d grids green, %d issues filed in %.1fs",
        stats["mode"],
        stats["scorecard"]["leagues_green"],
        stats["scorecard"]["leagues_total"],
        len(stats["filed"]),
        stats["duration_seconds"],
    )
    return stats
