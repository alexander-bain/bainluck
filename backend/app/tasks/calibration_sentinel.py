"""Calibration Sentinel — self-serve detection → diagnosis → issue filing (#1054).

Alex-directed 2026-07-09 (plan of record: .claude/handoff/design_calibration_sentinel.md).
Goal: remove the human from the DETECTION loop. New market formats (Olympics,
Oscars, playoff structures) WILL break calibration again; this task catches the
break, builds the standard evidence census the humans kept doing by hand, and
files ONE deduped GitHub issue per cohort fingerprint. Alex's eyeball stays the
SHIP gate (D5), never the smoke detector.

Four pillars (design doc §1-§4):
  1. Cohort mining across MULTIPLE dimensions (category × source × series-family ×
     structure × TABLE PROVENANCE — the r127 wrong-table lesson as a hard field),
     n-weighted MCE per cohort, on the RAW (un-excluded) population so a break is
     visible even where a read-side exclusion currently hides it from the curve.
  2. New-format early-warning tier: series first-seen <30d get a lower floor and a
     wider threshold, so a broken new format is caught at n=500 not n=50,000.
  3. Auto evidence pack: per-bucket cp-vs-winrate (both sides), sample rows, table
     provenance, and OVERLAP vs the season's known classes (placeholder / both-false
     / sign-flip / draw-mass / normalization / esports-bundle / void / heuristic).
  4. Filing + routing: one deduped issue per cohort fingerprint (alert-intake +
     area:calibration + needs-agent + severity). The sentinel NEVER writes market
     data (gotcha #21) — it files work.

Design intent — TWO modes:
  * Live run (file_issues=True, suppress_known=True): mine, SUPPRESS cohorts whose
    miscalibration is already explained by a SHIPPED exclusion (so it doesn't
    re-file known work), file the rest (accepted residuals + genuinely new).
  * Backtest run (file_issues=False, suppress_known=False): report EVERY flagged
    cohort tagged with which known class it maps to — the honest test that the
    detector can rediscover the season's known cohorts unaided.

Marker-vs-DB note (r134 lesson): the sentinel reads live DB rows for both the
cohort MCE and the evidence census — it never trusts a cached curve marker to
decide whether a cohort is broken; the published-curve exclusion counters are
used only to *explain/suppress*, never to *detect*.
"""

import hashlib
import logging
import time as _time
from typing import Any

from sqlalchemy import text

from app.tasks.base import get_task_session
from app.tasks.precompute_calibration import (
    _compute_horizon_mce,
    binary_is_malformed,
    market_is_esports_multi_bundle,
    market_needs_mex_normalization,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunable thresholds (mirrors precompute_calibration's Redis-tunable pattern —
# override at runtime via the Redis keys below, no deploy).
# ---------------------------------------------------------------------------
SENTINEL_N_FLOOR = 1000            # calibration:sentinel_n_floor
SENTINEL_MCE_THRESHOLD = 5.0       # calibration:sentinel_mce_threshold (pp)
# New-format early-warning tier: looser so a broken new format is caught early.
SENTINEL_NEW_N_FLOOR = 300         # calibration:sentinel_new_n_floor
SENTINEL_NEW_MCE_THRESHOLD = 3.0   # calibration:sentinel_new_mce_threshold (pp)
SENTINEL_NEW_FORMAT_DAYS = 30
# A cohort whose flagged outcomes are >= this fraction explained by a shipped
# exclusion is "already covered" and is suppressed in a live run.
SENTINEL_COVERAGE_THRESHOLD = 0.40  # calibration:sentinel_coverage_threshold
# Bound the number of flagged cohorts we build a (snapshot-touching) evidence
# census for, so a pathological run can't grind the snapshot table.
SENTINEL_MAX_EVIDENCE_COHORTS = 40
# A live run files AT MOST this many issues (highest-severity first, after
# cross-view dedup) so one run can't spam the board with 100+ near-duplicate
# cards. The rest are visible in the cached findings for the next run.
SENTINEL_MAX_ISSUES_PER_RUN = 6  # calibration:sentinel_max_issues_per_run

# Guess/terminal/void resolution sources folded into the "heuristic" overlap
# signal — mirrors the inline NOT IN (...) list the main calibration scan uses.
_HEURISTIC_SOURCES = (
    "pass2_guess",
    "pass2_loser",
    "all_losers",
    "pass3_threshold",
    "binary_higher_wins",
    "multi_max_prob",
    "no_pregame_trading",
)
_VOID_SOURCES = ("did_not_play", "withdrew")


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------
def series_family(external_id: str | None) -> str:
    """Coarse series/ticker-prefix family key.

    Kalshi tickers are ``SERIES-EVENTSUFFIX`` (e.g. ``KXPGATOUR-THOC26``); the
    prefix before the first ``-`` is the series family. Polymarket external_ids
    are less structured — fall back to the leading alpha run. Used as one cohort
    dimension so a single broken series (a new Olympics/Oscars format) surfaces
    without being diluted into its whole category.
    """
    if not external_id:
        return "unknown"
    head = external_id.split("-", 1)[0]
    # Strip a trailing digit run so e.g. "KXNBA2026" and "KXNBA2025" fold together.
    i = len(head)
    while i > 0 and head[i - 1].isdigit():
        i -= 1
    return (head[:i] or head)[:60]


def structure_class(n_outcomes: int, mutually_exclusive: bool) -> str:
    """Market-structure dimension: binary / mex_multi / multi_nonmex / single."""
    if n_outcomes == 2:
        return "binary"
    if n_outcomes >= 3:
        return "mex_multi" if mutually_exclusive else "multi_nonmex"
    return "single"


def dedup_overlapping(cohorts: list[dict]) -> list[dict]:
    """Collapse cohorts that describe the SAME underlying break at different
    granularities.

    The cohort views intentionally re-slice the same rows (a poly-hockey break
    surfaces as `category=hockey`, `source=poly·category=hockey`,
    `category=hockey·structure=...` all at once). For FILING we want one issue per
    break, so — walking a severity-sorted list — drop any cohort whose dimension
    VALUE set is a subset/superset of one already kept (the same break family, a
    coarser/finer cut). The first (highest-severity) survivor wins. Cohorts with
    disjoint value sets are independent breaks and both survive.
    """
    kept: list[dict] = []
    kept_valuesets: list[frozenset] = []
    for c in cohorts:
        vals = frozenset(c["dims"].values())
        if any(vals <= ks or ks <= vals for ks in kept_valuesets):
            continue
        kept.append(c)
        kept_valuesets.append(vals)
    return kept


def cohort_fingerprint(cohort_key: tuple[tuple[str, str], ...]) -> str:
    """Stable 12-char fingerprint of a cohort's (dim, value) pairs.

    Two runs of the same cohort produce the same fingerprint, so a re-run
    accretes on / dedupes against the existing issue instead of filing a
    duplicate (design §4).
    """
    raw = "|".join(f"{d}={v}" for d, v in sorted(cohort_key))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def passes_flag(total_n: int, mce: float | None, is_new_format: bool) -> bool:
    """Flag rule (design §1/§2): n >= floor AND mce >= threshold, with a looser
    early-warning tier for new formats."""
    if mce is None:
        return False
    if is_new_format:
        return total_n >= SENTINEL_NEW_N_FLOOR and mce >= SENTINEL_NEW_MCE_THRESHOLD
    return total_n >= SENTINEL_N_FLOOR and mce >= SENTINEL_MCE_THRESHOLD


def severity_for(mce: float, is_new_format: bool) -> str:
    """P1 for a big established break, P2 for a moderate one, P3 for early-warning."""
    if is_new_format:
        return "P3"
    if mce >= 10.0:
        return "P1"
    return "P2"


def hook_signature(buckets: list[dict]) -> bool:
    """True if the cohort shows the high-cp-low-winrate 'hook' (the sign-flip /
    placeholder signature): the top confidence bands (cp >= 0.7) resolve well
    below their predicted rate. This is the shape both the poly-Under sign class
    and the placeholder class leave behind."""
    top_n = 0
    top_win = 0
    top_cp = 0.0
    for b in buckets:
        if b["n"] == 0:
            continue
        avg_cp = b["sum_prob"] / b["n"]
        if avg_cp >= 0.7:
            top_n += b["n"]
            top_win += b["winners"]
            top_cp += b["sum_prob"]
    if top_n < 50:
        return False
    winrate = top_win / top_n
    pred = top_cp / top_n
    return (pred - winrate) >= 0.15


def classify_coverage(
    overlap_fractions: dict[str, float],
    category: str | None,
    provenance: str,
) -> tuple[str | None, float]:
    """Decide whether a flagged cohort's miscalibration is already explained by a
    SHIPPED exclusion. Returns (explained_by, coverage_fraction).

    ``overlap_fractions`` maps a known-class key to the fraction of the cohort's
    outcomes it covers (esports_multi_bundle / malformed_binary / mex_normalization
    / void / heuristic / poly_placeholder). The soccer 2-way draw class is
    structural (an events-table soccer moneyline), so it's keyed off category +
    provenance rather than a per-outcome flag.
    """
    # Structural known class: events-table soccer moneyline == the draw-omission
    # (soccer_2way) exclusion. Events are grouped by sport family (soccer_epl ->
    # "soccer") so all leagues aggregate past the n-floor; match either form.
    if provenance == "events" and (category or "").startswith("soccer"):
        return "soccer_2way", 1.0

    best_key = None
    best_frac = 0.0
    for key, frac in overlap_fractions.items():
        if frac > best_frac:
            best_frac = frac
            best_key = key
    if best_frac >= SENTINEL_COVERAGE_THRESHOLD:
        return best_key, best_frac
    return None, best_frac


# The cohort "views" — each maps a fine-grained scan row to a cohort key, or None
# to skip. Mining folds the fine rows into every view so a break is caught at
# whatever granularity it lives (a whole source, a single series, a structure ×
# category combo). Provenance is carried in every key (the r127 hard field).
def _cohort_views(row: dict) -> list[tuple[tuple[str, str], ...]]:
    src = row["source"]
    cat = row["category"]
    fam = row["series_family"]
    struct = row["structure_class"]
    prov = row["provenance"]
    return [
        (("provenance", prov), ("source", src)),
        (("provenance", prov), ("category", cat)),
        (("provenance", prov), ("source", src), ("category", cat)),
        (("provenance", prov), ("source", src), ("structure", struct)),
        (("provenance", prov), ("category", cat), ("structure", struct)),
        (("provenance", prov), ("source", src), ("series", fam)),
    ]


# ---------------------------------------------------------------------------
# SQL — the cheap mining scan (no snapshot join). Two populations, unioned by
# provenance so the r127 wrong-table split is a first-class dimension.
# ---------------------------------------------------------------------------
_FUTURES_MINING_SQL = """
WITH base AS (
    SELECT
        fm.source AS source,
        COALESCE(fm.llm_sport_category, 'unknown') AS category,
        -- Series-family is only meaningful for tickered sources (Kalshi/DataGolf
        -- tickers are SERIES-EVENT); Polymarket external_ids are unique slugs, so
        -- collapse those to the category to keep this dimension bounded.
        CASE WHEN fm.source IN ('kalshi', 'datagolf')
             THEN split_part(fm.external_id, '-', 1)
             ELSE COALESCE(fm.llm_sport_category, 'unknown')
        END AS ext_prefix,
        fm.mutually_exclusive AS mutually_exclusive,
        fm.created_at AS created_at,
        fo.is_winner AS is_winner,
        fo.resolution_source AS resolution_source,
        COALESCE(fo.calibration_probability, fo.opening_probability) AS cp,
        COUNT(*) OVER (PARTITION BY fo.market_id) AS n_outcomes,
        SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) OVER (PARTITION BY fo.market_id) AS n_winners,
        SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) OVER (PARTITION BY fo.market_id) AS cp_sum
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fm.status = 'resolved'
      AND COALESCE(fo.calibration_probability, fo.opening_probability) IS NOT NULL
)
SELECT
    'futures' AS provenance,
    source,
    category,
    ext_prefix AS series_family,
    CASE WHEN n_outcomes = 2 THEN 'binary'
         WHEN mutually_exclusive AND n_outcomes >= 3 THEN 'mex_multi'
         WHEN n_outcomes >= 3 THEN 'multi_nonmex'
         ELSE 'single' END AS structure_class,
    LEAST(FLOOR(cp * 10)::int, 9) AS bucket,
    COUNT(*) AS n,
    SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS winners,
    SUM(cp) AS sum_prob,
    SUM(CASE WHEN n_outcomes = 2 AND n_winners <> 1 THEN 1 ELSE 0 END) AS malformed_binary_n,
    SUM(CASE WHEN category = 'esports' AND n_outcomes >= 3 AND n_winners >= 2 THEN 1 ELSE 0 END) AS esports_bundle_n,
    SUM(CASE WHEN mutually_exclusive AND n_outcomes >= 3 AND n_winners = 1 AND cp_sum > 1.15 THEN 1 ELSE 0 END) AS mex_norm_n,
    SUM(CASE WHEN resolution_source IN {void_in} THEN 1 ELSE 0 END) AS void_n,
    SUM(CASE WHEN resolution_source IN {heuristic_in} THEN 1 ELSE 0 END) AS heuristic_n,
    MIN(created_at) AS min_created_at
FROM base
GROUP BY 1, 2, 3, 4, 5, 6
"""

# Events population: moneyline home/away split (2-way). Draws are intentionally
# LEFT IN as losses for both sides — that's exactly what surfaces the soccer
# draw-omission (soccer_2way) miscalibration. Events has no created_at column
# (schema drift), so new-format detection does not apply here.
_EVENTS_MINING_SQL = """
WITH sides AS (
    SELECT split_part(s.key, '_', 1) AS category,
           CASE WHEN e.home_score > e.away_score THEN 1 ELSE 0 END AS win,
           COALESCE(e.closing_home_probability, e.opening_home_probability) AS cp
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    WHERE e.status IN ('completed', 'closed')
      AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
      AND COALESCE(e.closing_home_probability, e.opening_home_probability) IS NOT NULL
    UNION ALL
    SELECT split_part(s.key, '_', 1) AS category,
           CASE WHEN e.away_score > e.home_score THEN 1 ELSE 0 END AS win,
           COALESCE(e.closing_away_probability, e.opening_away_probability) AS cp
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    WHERE e.status IN ('completed', 'closed')
      AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
      AND COALESCE(e.closing_away_probability, e.opening_away_probability) IS NOT NULL
)
SELECT
    'events' AS provenance,
    'odds_api' AS source,
    category AS category,
    'events_moneyline' AS series_family,
    'binary' AS structure_class,
    LEAST(FLOOR(cp * 10)::int, 9) AS bucket,
    COUNT(*) AS n,
    SUM(win) AS winners,
    SUM(cp) AS sum_prob,
    0 AS malformed_binary_n,
    0 AS esports_bundle_n,
    0 AS mex_norm_n,
    0 AS void_n,
    0 AS heuristic_n,
    NULL::timestamptz AS min_created_at
FROM sides
GROUP BY category, bucket
"""


def _in_list(items: tuple[str, ...]) -> str:
    """SQL IN-list literal from trusted module constants (no user input)."""
    return "(" + ", ".join("'" + x.replace("'", "''") + "'" for x in items) + ")"


# Bake the trusted resolution-source lists into the futures scan (inline literals,
# matching the main calibration scan's NOT IN (...) style — avoids asyncpg
# array-param type ambiguity).
_FUTURES_MINING_SQL = _FUTURES_MINING_SQL.format(
    void_in=_in_list(_VOID_SOURCES),
    heuristic_in=_in_list(_HEURISTIC_SOURCES),
)


def _empty_buckets() -> list[dict]:
    return [{"bucket": i, "n": 0, "winners": 0, "sum_prob": 0.0} for i in range(10)]


def _fold_row_into_cohort(cohort: dict, row: dict) -> None:
    """Accumulate one fine-grained scan row into a cohort aggregate."""
    b = cohort["buckets"][row["bucket"]]
    b["n"] += row["n"]
    b["winners"] += row["winners"]
    b["sum_prob"] += float(row["sum_prob"] or 0.0)
    cohort["total_n"] += row["n"]
    cohort["overlap_counts"]["malformed_binary"] += row["malformed_binary_n"]
    cohort["overlap_counts"]["esports_multi_bundle"] += row["esports_bundle_n"]
    cohort["overlap_counts"]["mex_normalization"] += row["mex_norm_n"]
    cohort["overlap_counts"]["void"] += row["void_n"]
    cohort["overlap_counts"]["heuristic"] += row["heuristic_n"]
    mca = row.get("min_created_at")
    if mca is not None:
        cur = cohort["min_created_at"]
        cohort["min_created_at"] = mca if cur is None else min(cur, mca)


def _new_cohort(cohort_key: tuple[tuple[str, str], ...], sample_row: dict) -> dict:
    d = dict(cohort_key)
    return {
        "cohort_key": cohort_key,
        "fingerprint": cohort_fingerprint(cohort_key),
        "dims": d,
        "provenance": d.get("provenance", "?"),
        "category": d.get("category"),
        "buckets": _empty_buckets(),
        "total_n": 0,
        "overlap_counts": {
            "malformed_binary": 0,
            "esports_multi_bundle": 0,
            "mex_normalization": 0,
            "void": 0,
            "heuristic": 0,
        },
        "min_created_at": None,
    }


def _finalize_cohort(cohort: dict, now_ts: float) -> dict:
    buckets = cohort["buckets"]
    cohort["mce"] = _compute_horizon_mce(buckets, weighted=True)
    mca = cohort["min_created_at"]
    is_new = False
    if mca is not None:
        try:
            age_days = (now_ts - mca.timestamp()) / 86400.0
            is_new = age_days <= SENTINEL_NEW_FORMAT_DAYS
        except Exception:
            is_new = False
    cohort["is_new_format"] = is_new
    cohort["hook_signature"] = hook_signature(buckets)
    # Overlap fractions vs total_n (poly_placeholder is added later by the census).
    fracs = {}
    for k, cnt in cohort["overlap_counts"].items():
        fracs[k] = round(cnt / cohort["total_n"], 4) if cohort["total_n"] else 0.0
    cohort["overlap_fractions"] = fracs
    return cohort


# ---------------------------------------------------------------------------
# Evidence census (per flagged cohort) — the snapshot-touching part, bounded to
# the flagged cohorts only.
# ---------------------------------------------------------------------------
def _cohort_where(dims: dict) -> tuple[str, dict]:
    """Build a WHERE clause + params restricting the futures scan to a cohort.

    Only futures cohorts get the snapshot census (events have no snapshot bid
    evidence and no placeholder class). Series/structure dims are honored where
    present.
    """
    clauses = ["fm.status = 'resolved'"]
    params: dict[str, Any] = {}
    if "source" in dims:
        clauses.append("fm.source = :src")
        params["src"] = dims["source"]
    if "category" in dims:
        clauses.append("COALESCE(fm.llm_sport_category, 'unknown') = :cat")
        params["cat"] = dims["category"]
    return " AND ".join(clauses), params


async def _placeholder_fraction(session, dims: dict) -> float | None:
    """Fraction of a poly cohort's outcomes that are no-bid ~0.50 placeholders.

    Uses SNAPSHOT bid provenance (the #151 discriminator) — the one known class
    the cheap mining scan can't see. Only meaningful for polymarket cohorts.
    """
    if dims.get("source") != "polymarket":
        return None
    where, params = _cohort_where(dims)
    params["cap"] = 3000
    # Bounded SAMPLE: the per-outcome NOT EXISTS over snapshots is the one op that
    # can run away over a whole category, so cap the candidate set first (a 3000-row
    # sample gives a fine fraction estimate) — the budget-guard "bound the inner op"
    # lesson (gotcha #38/#966).
    sql = text(f"""
        WITH sample AS (
            SELECT fo.id AS oid,
                   COALESCE(fo.calibration_probability, fo.opening_probability) AS cp
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE {where}
              AND COALESCE(fo.calibration_probability, fo.opening_probability) IS NOT NULL
            LIMIT :cap
        )
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN cp BETWEEN 0.45 AND 0.55
                      AND NOT EXISTS (
                          SELECT 1 FROM futures_odds_snapshots fos
                          WHERE fos.outcome_id = sample.oid
                            AND (fos.yes_bid > 0 OR fos.last_price > 0))
                     THEN 1 ELSE 0 END) AS placeholder
        FROM sample
    """)
    res = (await session.execute(sql, params)).first()
    if not res or not res.total:
        return None
    return round(res.placeholder / res.total, 4)


async def _sample_rows(session, dims: dict, limit: int = 12) -> list[dict]:
    """Pull a few concrete rows from a flagged FUTURES cohort's high-cp band for
    the evidence pack (the row-trace protocol's starting point)."""
    if dims.get("provenance") != "futures":
        return []
    where, params = _cohort_where(dims)
    params["lim"] = limit
    params["cap"] = 5000
    # Bound the candidate set before the top-N sort so a huge cohort can't force a
    # full-category sort (same inner-op-bounding discipline as the placeholder census).
    sql = text(f"""
        WITH sample AS (
            SELECT fm.source AS source, fm.external_id AS external_id, fo.name AS outcome,
                   COALESCE(fo.calibration_probability, fo.opening_probability) AS cp,
                   fo.is_winner AS is_winner, fo.resolution_source AS resolution_source
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE {where}
              AND COALESCE(fo.calibration_probability, fo.opening_probability) >= 0.6
            LIMIT :cap
        )
        SELECT source, external_id, outcome, cp, is_winner, resolution_source
        FROM sample
        ORDER BY cp DESC
        LIMIT :lim
    """)
    rows = (await session.execute(sql, params)).all()
    return [
        {
            "source": r.source,
            "market": r.external_id,
            "outcome": r.outcome,
            "cp": round(float(r.cp), 3),
            "is_winner": bool(r.is_winner),
            "resolution_source": r.resolution_source,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Evidence-pack rendering (the GitHub issue body)
# ---------------------------------------------------------------------------
_PLAYBOOK_BRANCHES = {
    "poly_placeholder": "curve-exclusion (no-bid ~0.50 placeholder; #151) — read-side, no regrade",
    "malformed_binary": "curve-exclusion (winner-count != 1; L2-79) — read-side, no regrade",
    "esports_multi_bundle": "curve-exclusion (cumulative ladder, >=2 winners; #159) — read-side, no regrade",
    "mex_normalization": "normalize per-market cp sum (mex >=3, 1 winner; #157) — read-side, no regrade",
    "void": "denominator fix (did_not_play/withdrew; #762) — read-side, no regrade",
    "heuristic": "curve-exclude then authoritative re-resolve (guess-family poison; #754/gotcha #21)",
    "soccer_2way": "3-way capture (draw column; #1011) — historical rows excluded, no regrade",
}


def _bucket_table(buckets: list[dict]) -> str:
    lines = [
        "| cp band | n | pred | actual | gap (pp) |",
        "|--------:|--:|-----:|-------:|---------:|",
    ]
    for i, b in enumerate(buckets):
        if b["n"] == 0:
            continue
        pred = b["sum_prob"] / b["n"]
        actual = b["winners"] / b["n"]
        gap = (actual - pred) * 100
        lines.append(
            f"| {i*10}-{i*10+10}% | {b['n']} | {pred*100:.1f}% | {actual*100:.1f}% | {gap:+.1f} |"
        )
    return "\n".join(lines)


def build_issue_title(cohort: dict) -> str:
    dims = cohort["dims"]
    label = " · ".join(f"{d}={dims[d]}" for d in dims if d != "provenance")
    tag = "new-format" if cohort["is_new_format"] else "calibration"
    title = f"[Calibration Sentinel] {tag} break: {label} (MCE {cohort['mce']:.1f}pp, n={cohort['total_n']})"
    return title[:256]


def build_issue_body(cohort: dict, explained_by: str | None, coverage: float) -> str:
    dims = cohort["dims"]
    fp = cohort["fingerprint"]
    parts = [
        "## Calibration Sentinel finding",
        "",
        f"`sentinel-fingerprint:{fp}`  (dedupe key — do not remove)",
        "",
        "**Cohort dimensions:**",
    ]
    for d, v in sorted(cohort["cohort_key"]):
        parts.append(f"- `{d}` = `{v}`")
    parts += [
        "",
        f"**n-weighted MCE:** {cohort['mce']:.2f}pp  ",
        f"**Sample size:** {cohort['total_n']} resolved outcomes  ",
        f"**Population/table provenance:** `{cohort['provenance']}` "
        f"({'events ground-truth (scores)' if cohort['provenance']=='events' else 'futures_outcomes'})  ",
        f"**Tier:** {'NEW-FORMAT early-warning (series first seen <30d)' if cohort['is_new_format'] else 'established'}  ",
        f"**Hook / sign-flip signature (high-cp band under-resolving):** {'YES' if cohort['hook_signature'] else 'no'}",
        "",
        "### Per-bucket census (cp vs actual)",
        _bucket_table(cohort["buckets"]),
        "",
        "### Overlap vs known classes",
    ]
    fracs = cohort["overlap_fractions"]
    for k in ("poly_placeholder", "esports_multi_bundle", "malformed_binary",
              "mex_normalization", "void", "heuristic"):
        if k in fracs:
            parts.append(f"- {k}: {fracs[k]*100:.1f}% of outcomes")
    if cohort["provenance"] == "events" and (cohort["category"] or "").startswith("soccer_"):
        parts.append("- soccer_2way (draw omission): structural — events soccer moneyline")
    parts.append("")

    if explained_by:
        branch = _PLAYBOOK_BRANCHES.get(explained_by, "see docs/calibration-diagnosis-playbooks.md")
        parts += [
            f"### Diagnosis: likely the **{explained_by}** class ({coverage*100:.0f}% coverage)",
            f"Playbook branch: {branch}.",
            "",
            "This overlaps a class with a shipped read-side exclusion — verify the "
            "exclusion still covers this cohort (it may be a new series/source the "
            "existing guard misses). If already covered, close with the exclusion "
            "reference.",
        ]
    else:
        parts += [
            "### Diagnosis: UNEXPLAINED by any shipped exclusion",
            "No known class covers this break above threshold — this is a candidate "
            "NEW break. Follow the row-trace protocol in "
            "`docs/calibration-diagnosis-playbooks.md` (Step 2) before any fix, and "
            "assume-our-bug + verify-before-regrade (gotcha #21).",
        ]

    samples = cohort.get("sample_rows") or []
    if samples:
        parts += ["", "### Sample high-cp rows"]
        parts.append("| source | market | outcome | cp | winner | resolution_source |")
        parts.append("|--------|--------|---------|---:|:------:|-------------------|")
        for s in samples:
            parts.append(
                f"| {s['source']} | `{s['market']}` | {s['outcome'][:40]} | "
                f"{s['cp']} | {'✓' if s['is_winner'] else '✗'} | {s['resolution_source'] or '—'} |"
            )

    parts += [
        "",
        "---",
        "*Auto-filed by the Calibration Sentinel (#1054). Read-only detection — the "
        "sentinel never writes market data (gotcha #21). "
        "[Calibration](https://bainluck.com/calibration)*",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Filing + dedup (reuses the bug_report_github httpx client)
# ---------------------------------------------------------------------------
def _find_open_issue_by_fingerprint(fingerprint: str) -> int | None:
    """Search open issues for an existing finding with this fingerprint."""
    import httpx
    from app.tasks.bug_report_github import GITHUB_TOKEN, REPO

    if not GITHUB_TOKEN:
        return None
    q = f'repo:{REPO} in:body "sentinel-fingerprint:{fingerprint}" state:open'
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
        logger.warning("Sentinel dedup search failed for %s: %s", fingerprint, exc)
        return None


def file_cohort_issue(cohort: dict, explained_by: str | None, coverage: float) -> dict:
    """File OR update one issue for a cohort fingerprint. Returns an action dict."""
    from app.tasks.bug_report_github import (
        GITHUB_TOKEN,
        add_to_project_board,
        comment_on_issue,
        create_github_issue,
    )

    fp = cohort["fingerprint"]
    if not GITHUB_TOKEN:
        return {"fingerprint": fp, "action": "skipped_no_token"}

    existing = _find_open_issue_by_fingerprint(fp)
    if existing:
        try:
            comment_on_issue(
                existing,
                f"Sentinel re-observed this cohort: MCE {cohort['mce']:.2f}pp, "
                f"n={cohort['total_n']} (fingerprint `{fp}`). Still open.",
            )
        except Exception as exc:
            logger.warning("Sentinel comment failed on #%d: %s", existing, exc)
        return {"fingerprint": fp, "action": "commented", "issue": existing}

    severity = severity_for(cohort["mce"], cohort["is_new_format"])
    labels = [
        "alert-intake",
        "area:calibration",
        "needs-agent",
        f"priority:{severity.lower()}",
    ]
    title = build_issue_title(cohort)
    body = build_issue_body(cohort, explained_by, coverage)
    try:
        number, node_id = create_github_issue(title, body, labels)
    except Exception as exc:
        logger.error("Sentinel issue creation failed (%s): %s", fp, exc)
        return {"fingerprint": fp, "action": "error", "error": str(exc)[:200]}
    try:
        add_to_project_board(node_id)
    except Exception:
        logger.warning("Sentinel: add issue #%d to board failed (non-fatal)", number, exc_info=True)
    return {"fingerprint": fp, "action": "filed", "issue": number, "severity": severity}


# ---------------------------------------------------------------------------
# Runtime threshold overrides (Redis, no-deploy tuning)
# ---------------------------------------------------------------------------
def _load_overrides() -> None:
    global SENTINEL_N_FLOOR, SENTINEL_MCE_THRESHOLD, SENTINEL_NEW_N_FLOOR
    global SENTINEL_NEW_MCE_THRESHOLD, SENTINEL_COVERAGE_THRESHOLD, SENTINEL_MAX_ISSUES_PER_RUN
    try:
        from app.tasks.redis_state import get_redis_client

        r = get_redis_client()
        for key, name, cast in (
            ("calibration:sentinel_n_floor", "SENTINEL_N_FLOOR", int),
            ("calibration:sentinel_mce_threshold", "SENTINEL_MCE_THRESHOLD", float),
            ("calibration:sentinel_new_n_floor", "SENTINEL_NEW_N_FLOOR", int),
            ("calibration:sentinel_new_mce_threshold", "SENTINEL_NEW_MCE_THRESHOLD", float),
            ("calibration:sentinel_coverage_threshold", "SENTINEL_COVERAGE_THRESHOLD", float),
            ("calibration:sentinel_max_issues_per_run", "SENTINEL_MAX_ISSUES_PER_RUN", int),
        ):
            v = r.get(key)
            if v is not None:
                globals()[name] = cast(v)
    except Exception as exc:
        logger.info("Sentinel threshold overrides not loaded (using defaults): %s", exc)


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
async def _run_calibration_sentinel(
    file_issues: bool = True,
    suppress_known: bool = True,
    deadline_seconds: float = 600.0,
) -> dict[str, Any]:
    """Mine cohorts, build evidence packs, and (in a live run) file deduped issues.

    * Live run (defaults): suppress cohorts already covered by a shipped exclusion,
      file the rest.
    * Backtest run (file_issues=False, suppress_known=False): return every flagged
      cohort tagged with the known class it maps to — the honest rediscovery test.
    """
    _load_overrides()
    start = _time.monotonic()
    now_ts = _time.time()

    stats: dict[str, Any] = {
        "mode": "live" if (file_issues and suppress_known) else "backtest",
        "thresholds": {
            "n_floor": SENTINEL_N_FLOOR,
            "mce_threshold": SENTINEL_MCE_THRESHOLD,
            "new_n_floor": SENTINEL_NEW_N_FLOOR,
            "new_mce_threshold": SENTINEL_NEW_MCE_THRESHOLD,
            "coverage_threshold": SENTINEL_COVERAGE_THRESHOLD,
        },
        "fine_rows": 0,
        "cohorts_evaluated": 0,
        "flagged": 0,
        "explained": 0,
        "unexplained": 0,
        "filed": [],
        "findings": [],
        "errors": [],
    }

    cohorts: dict[tuple, dict] = {}

    async with get_task_session() as session:
        # --- Mining scan: fold both populations into every cohort view ---
        for label, sql in (("futures", _FUTURES_MINING_SQL), ("events", _EVENTS_MINING_SQL)):
            try:
                result = await session.execute(text(sql))
                for r in result.mappings():
                    row = dict(r)
                    # series_family / structure_class are computed in SQL (bounded
                    # cardinality); fold the season-digit suffix here so e.g.
                    # KXNBA2026 and KXNBA2025 collapse to one series.
                    row["series_family"] = series_family(row["series_family"])
                    stats["fine_rows"] += 1
                    for ck in _cohort_views(row):
                        c = cohorts.get(ck)
                        if c is None:
                            c = _new_cohort(ck, row)
                            cohorts[ck] = c
                        _fold_row_into_cohort(c, row)
            except Exception as exc:
                logger.error("Sentinel %s mining scan failed: %s", label, exc)
                stats["errors"].append({"scan": label, "error": str(exc)[:200]})
                try:
                    await session.rollback()
                except Exception:
                    pass

        # --- Finalize + flag ---
        flagged: list[dict] = []
        for c in cohorts.values():
            _finalize_cohort(c, now_ts)
            stats["cohorts_evaluated"] += 1
            if passes_flag(c["total_n"], c["mce"], c["is_new_format"]):
                flagged.append(c)
        flagged.sort(key=lambda c: (c["mce"] or 0) * (1 if not c["is_new_format"] else 1.5), reverse=True)
        stats["flagged"] = len(flagged)

        # --- Evidence census + classification (bounded) ---
        for i, c in enumerate(flagged):
            if _time.monotonic() - start > deadline_seconds:
                stats["errors"].append({"deadline": f"stopped after {i} of {len(flagged)} flagged cohorts"})
                break
            try:
                if i < SENTINEL_MAX_EVIDENCE_COHORTS:
                    ph = await _placeholder_fraction(session, c["dims"])
                    if ph is not None:
                        c["overlap_fractions"]["poly_placeholder"] = ph
                    c["sample_rows"] = await _sample_rows(session, c["dims"])
            except Exception as exc:
                logger.warning("Sentinel evidence census failed (%s): %s", c["fingerprint"], exc)
                try:
                    await session.rollback()
                except Exception:
                    pass

            explained_by, coverage = classify_coverage(
                c["overlap_fractions"], c["category"], c["provenance"]
            )
            c["explained_by"] = explained_by
            c["coverage"] = coverage
            if explained_by:
                stats["explained"] += 1
            else:
                stats["unexplained"] += 1

            finding = {
                "fingerprint": c["fingerprint"],
                "dims": c["dims"],
                "mce": round(c["mce"], 2),
                "n": c["total_n"],
                "provenance": c["provenance"],
                "is_new_format": c["is_new_format"],
                "hook_signature": c["hook_signature"],
                "explained_by": explained_by,
                "coverage": round(coverage, 3),
                "overlap_fractions": c["overlap_fractions"],
            }
            stats["findings"].append(finding)

    # --- Filing (outside the session; httpx calls) ---
    # Suppress cohorts explained by a shipped exclusion in a live run so the
    # sentinel doesn't re-file known work; still surface them in the findings.
    candidates = [c for c in flagged if not (suppress_known and c.get("explained_by"))]
    candidates.sort(
        key=lambda c: (0 if c.get("explained_by") else 1, c["mce"] or 0), reverse=True
    )
    candidates = dedup_overlapping(candidates)
    stats["file_candidates_deduped"] = len(candidates)
    stats["filing_capped"] = len(candidates) > SENTINEL_MAX_ISSUES_PER_RUN
    if file_issues:
        for c in candidates[:SENTINEL_MAX_ISSUES_PER_RUN]:
            action = file_cohort_issue(c, c.get("explained_by"), c.get("coverage", 0.0))
            stats["filed"].append(action)

    stats["duration_seconds"] = round(_time.monotonic() - start, 1)
    # #1202: stamp a run-level wall clock so /calibration-sentinel/last and the
    # cockpit can render age ("ran 6h ago") + apply the stale-RED silence check —
    # the same generated_at the flow/grid/settled sentinels already persist (#232).
    from datetime import datetime as _dt, timezone as _tz
    stats["generated_at"] = _dt.now(_tz.utc).isoformat()

    # Cache the full run so it's inspectable without re-scanning (the backtest /
    # ops read path) — findings can be large, so keep 14 days, not forever.
    # Queue 298 (#1512): durable row first, Redis as the accelerator. The
    # backtest run keeps its own separate identity, exactly as it keeps its own
    # Redis key — the two must never overwrite each other.
    from app.services.durable_snapshots import publish_sentinel_evidence
    from app.utils.durable_state import evaluate_publication

    _backtest = stats["mode"] == "backtest"
    stages = await publish_sentinel_evidence(
        identity="sentinel:calibration:backtest" if _backtest else "sentinel:calibration",
        redis_key=(
            "bainluck:calibration_sentinel:last_backtest"
            if _backtest
            else "bainluck:calibration_sentinel:last"
        ),
        stats=stats,
        source="calibration_sentinel",
    )
    stats["persistence"] = stages
    evaluate_publication(
        compute_complete=True,
        durable_write="ok" if stages["durable"] in ("ok", "superseded") else "error",
        volatile_write=stages.get("volatile", "not_attempted"),
        stages=stages,
    ).raise_if_failed("calibration sentinel evidence")

    logger.info(
        "Calibration sentinel (%s): %d cohorts, %d flagged (%d unexplained, %d explained), %d filed",
        stats["mode"],
        stats["cohorts_evaluated"],
        stats["flagged"],
        stats["unexplained"],
        stats["explained"],
        len(stats["filed"]),
    )
    return stats
