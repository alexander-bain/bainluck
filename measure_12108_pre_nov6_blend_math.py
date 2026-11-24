"""Pre-Nov-6 historical blend-vs-sources math measurement for #12108 (Items 1 & 2).

Compares every forecast source alone (`kalshi`, `polymarket`, `pm_avg`, `betting`,
`espn`, `stat_model`, `mlb`) against the Bain Luck blend replayed under today's
pre-game rule (`compute_aggregate_probability_tiered`) on the exact same pre-Nov-6
completed games, across 4 pre-game cutoffs (`start`, `t_minus_1h`, `t_minus_6h`,
`t_minus_24h`), overall and by sport, reporting log loss (first) and typical miss
(10-band ECE in points, second) with 95% cluster-bootstrap intervals (`seed=12108`,
`replicates=1000`, clustered by `series_doubleheader`).

Strict hard bounds:
- NEVER connects to production unless ALL THREE are true:
  1) `--production --alex-approved --fable-sql-read-go`
  2) Current local PT time >= 2026-11-23T20:45:00-08:00
- Every SQL statement carries `e.commence_time < TIMESTAMPTZ '2026-11-06T00:00:00Z'`,
  `(e.completed_at IS NULL OR e.completed_at < TIMESTAMPTZ '2026-11-06T00:00:00Z')`,
  `(e.score_observed_at IS NULL OR e.score_observed_at < TIMESTAMPTZ '2026-11-06T00:00:00Z')`,
  and `captured_at < TIMESTAMPTZ '2026-11-06T00:00:00Z'`.
- ZERO queries to `probability_publications` (zero held-out games read).
- Read-only Postgres session (`default_transaction_read_only = on`,
  `SET LOCAL transaction_read_only = on`, `SET LOCAL statement_timeout = '120s'`
  on events/win-prob and `'30s'` on odds), `1.0s` pause between batches,
  `30-minute` max read wall clock, two-phase stratified seeded-random order,
  partial-read scoring on stop/timeout, and ZERO retries on any statement timeout.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import subprocess
import sys
import time
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

BACKEND_DIR = Path("/Users/bain/.bainluck/speed/wt/blend-replay-12133/backend")
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.models import Base  # noqa: E402
from app.tasks.calibration_main_build import is_statement_timeout  # noqa: E402
from app.utils.aggregation import (  # noqa: E402
    compute_aggregate_probability_tiered,
)
from app.utils.publication_reader import HORIZONS  # noqa: E402
from scripts.evals.blend_replay_export import rebuild_betting  # noqa: E402

_PT = ZoneInfo("America/Los_Angeles")
_EARLIEST_PROD_PT = datetime(2026, 11, 23, 20, 45, 0, tzinfo=_PT)
_PRE_NOV6_ISO = "2026-11-06T00:00:00Z"
_EVENTS_STMT_TIMEOUT_S = 120
_WP_STMT_TIMEOUT_S = 120
_ODDS_STMT_TIMEOUT_S = 30
_INTER_BATCH_PAUSE_S = 1.0
_MAX_READ_DURATION_S = 1800.0
_NON_PM_ODDS_SAMPLE_LIMIT = 4000
_BATCH_SIZE = 200
_SERIES_MAX_GAP = timedelta(days=4)
_LOG_LOSS_CLIP = 1e-15
_BOOTSTRAP_SEED = 12108
_BOOTSTRAP_REPLICATES = 1000
_DB_ROLE_NOTE = "primary postgresql-globular-51563 (Heroku Standard 3 — no follower attached)"

REPLAY_LIMITS: tuple[str, ...] = (
    "1. **Unrecorded historical blends:** `probability_publications` was off before `v6185` (`2026-11-06T05:52:44Z`), so we replay today's `compute_aggregate_probability_tiered(..., \"scheduled\")` on stored snapshots rather than reading served blends.",
    "2. **Write-time deduplication (`captured_at` vs `valid_until`):** `win_prob_snapshots` and `odds_snapshots` bump `valid_until` in place on repeated values and leave `valid_until = NULL` when a final value changed once; quiet dark periods cannot always be separated from unchanged quotes.",
    "3. **Per-bookmaker lookback vs simultaneous poll board:** reconstruction takes each bookmaker's latest `odds_snapshots` row with `captured_at <= cutoff`, pooling books over a trailing window if individual books went quiet earlier.",
    "4. **Tier-2 mutable fallback omitted:** `Event.espn_win_prob_home` is overwritten post-game and cannot supply historical pre-game cutoffs whenever `win_prob_snapshots(source='espn')` is absent.",
    "5. **Pre-existing proportional de-vig & binary home-win target:** stored `odds_snapshots.home_win_probability` is already proportionally de-vigged at poll time, and `outcome = (home_score > away_score)` scores 3-way draws as `0`.",
)

HORIZON_DISPLAY_ORDER: tuple[str, ...] = (
    "start",
    "t_minus_1h",
    "t_minus_6h",
    "t_minus_24h",
)
HORIZON_LABELS: dict[str, str] = {
    "start": "Start (T-0)",
    "t_minus_1h": "1h Before",
    "t_minus_6h": "6h Before",
    "t_minus_24h": "24h Before",
}
COMPARATORS: tuple[str, ...] = (
    "kalshi",
    "polymarket",
    "pm_avg",
    "betting",
    "espn",
    "stat_model",
    "mlb",
)
COMPARATOR_LABELS: dict[str, str] = {
    "blend": "Bain Luck Blend",
    "kalshi": "Kalshi",
    "polymarket": "Polymarket",
    "pm_avg": "PM Avg (Kalshi+Polymarket)/2",
    "betting": "Sportsbooks",
    "espn": "ESPN",
    "stat_model": "Bain Luck Model",
    "mlb": "MLB Model",
}
COMMON_OVERLAP_SETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("All 4 core sources (Books + ESPN + Kalshi + Polymarket)", ("betting", "espn", "kalshi", "polymarket")),
    ("Books + Kalshi + Polymarket", ("betting", "kalshi", "polymarket")),
    ("Both Prediction Markets (Kalshi + Polymarket + PM Avg)", ("kalshi", "polymarket", "pm_avg")),
    ("Books + ESPN", ("betting", "espn")),
    ("Books + ESPN + Bain Luck Model", ("betting", "espn", "stat_model")),
    ("Baseball All 4 (Books + ESPN + Bain Luck Model + MLB Model)", ("betting", "espn", "stat_model", "mlb")),
)
CUTOFF_PAIRS: tuple[tuple[str, str], ...] = (
    ("start", "t_minus_1h"),
    ("start", "t_minus_6h"),
    ("start", "t_minus_24h"),
    ("t_minus_1h", "t_minus_6h"),
    ("t_minus_6h", "t_minus_24h"),
)

EVENTS_SQL = f"""
SELECT e.id AS event_id,
       e.commence_time AS start,
       e.completed_at AS completed_at,
       e.score_observed_at AS score_observed_at,
       e.home_team_name AS home_team_name,
       e.away_team_name AS away_team_name,
       e.home_score AS home_score,
       e.away_score AS away_score,
       s.key AS league,
       s."group" AS sport_group
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE e.status = 'completed'
   AND e.home_score IS NOT NULL
   AND e.away_score IS NOT NULL
   AND e.commence_time < TIMESTAMPTZ '{_PRE_NOV6_ISO}'
   AND (e.completed_at IS NULL OR e.completed_at < TIMESTAMPTZ '{_PRE_NOV6_ISO}')
   AND (e.score_observed_at IS NULL OR e.score_observed_at < TIMESTAMPTZ '{_PRE_NOV6_ISO}')
 ORDER BY e.id
""".strip()

WIN_PROB_BATCH_SQL = f"""
SELECT b.event_id AS event_id,
       b.horizon AS horizon,
       src.source AS source,
       snap.id AS snap_id,
       snap.captured_at AS captured_at,
       snap.valid_until AS valid_until,
       snap.home_win_probability AS home_win_probability
  FROM unnest(
      CAST(:event_ids AS bigint[]),
      CAST(:cutoffs AS timestamptz[]),
      CAST(:horizons AS text[])
  ) AS b(event_id, cutoff, horizon)
  CROSS JOIN (
      VALUES ('espn'), ('kalshi'), ('polymarket'), ('stat_model'), ('mlb'), ('fangraphs')
  ) AS src(source)
  CROSS JOIN LATERAL (
      SELECT w.id, w.captured_at, w.valid_until, w.home_win_probability
        FROM win_prob_snapshots w
       WHERE w.event_id = b.event_id
         AND w.source = src.source
         AND w.captured_at <= b.cutoff
         AND w.captured_at < TIMESTAMPTZ '{_PRE_NOV6_ISO}'
         AND w.home_win_probability IS NOT NULL
         AND w.home_win_probability >= 0
         AND w.home_win_probability <= 1
       ORDER BY w.captured_at DESC, w.id DESC
       LIMIT 1
  ) AS snap
""".strip()

ODDS_BATCH_SQL = f"""
SELECT o.event_id AS event_id,
       o.id AS snap_id,
       o.bookmaker AS bookmaker,
       o.captured_at AS captured_at,
       o.valid_until AS valid_until,
       o.home_win_probability AS home_win_probability
  FROM odds_snapshots o
  JOIN events e ON e.id = o.event_id
 WHERE o.event_id = ANY(CAST(:event_ids AS bigint[]))
   AND e.commence_time < TIMESTAMPTZ '{_PRE_NOV6_ISO}'
   AND (e.completed_at IS NULL OR e.completed_at < TIMESTAMPTZ '{_PRE_NOV6_ISO}')
   AND (e.score_observed_at IS NULL OR e.score_observed_at < TIMESTAMPTZ '{_PRE_NOV6_ISO}')
   AND o.captured_at <= e.commence_time
   AND o.captured_at < TIMESTAMPTZ '{_PRE_NOV6_ISO}'
   AND o.home_win_probability IS NOT NULL
   AND o.home_win_probability > 0
   AND o.home_win_probability < 1
 ORDER BY o.event_id, o.bookmaker, o.captured_at, o.id
""".strip()


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _valid_prob(raw: Any) -> float | None:
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        p = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(p) or not (0.0 <= p <= 1.0):
        return None
    return p


def _async_db_url(raw_url: str) -> str:
    url = raw_url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("PostgreSQL DATABASE_URL required")
    return url


def assign_series_clusters(events: list[dict[str, Any]]) -> dict[int, str]:
    """Group consecutive matchups between the same teams within 4 days into one cluster_id."""
    grouped: dict[tuple[str, tuple[str, str]], list[dict[str, Any]]] = defaultdict(list)
    for ev in events:
        t1 = str(ev["home_team_name"]).strip().lower()
        t2 = str(ev["away_team_name"]).strip().lower()
        pair = tuple(sorted((t1, t2)))
        grouped[(str(ev["league"]), pair)].append(ev)

    cluster_by_eid: dict[int, str] = {}
    for (league, pair), games in grouped.items():
        games_sorted = sorted(games, key=lambda g: (_as_utc(g["start"]), int(g["event_id"])))
        series_start = _as_utc(games_sorted[0]["start"])
        prev_start = series_start
        for g in games_sorted:
            st = _as_utc(g["start"])
            if st - prev_start > _SERIES_MAX_GAP:
                series_start = st
            cluster_by_eid[int(g["event_id"])] = (
                f"{league}:{pair[0]}_vs_{pair[1]}:{series_start.date().isoformat()}"
            )
            prev_start = st
    return cluster_by_eid


def _effective_stamp(captured: datetime, valid_until: datetime | None, cutoff: datetime) -> datetime:
    cap = _as_utc(captured)
    if valid_until is not None:
        vu = _as_utc(valid_until)
        if vu >= cap:
            return min(_as_utc(cutoff), vu)
    return cap


def _bin_stats_and_ll(rows: list[tuple[str, float, int]]) -> tuple[float, float, np.ndarray]:
    """Compute point log_loss, point ECE (pp), and `(C, 22)` sufficient-stat matrix ordered by cluster."""
    by_cluster: dict[str, np.ndarray] = {}
    for cid, p, y in rows:
        vec = by_cluster.get(cid)
        if vec is None:
            vec = np.zeros(22, dtype=np.float64)
            by_cluster[cid] = vec
        vec[0] += 1.0
        clipped = min(1.0 - _LOG_LOSS_CLIP, max(_LOG_LOSS_CLIP, p))
        ll = -(y * math.log(clipped) + (1 - y) * math.log1p(-clipped))
        vec[1] += ll
        b = min(9, math.floor(p * 10.0))
        vec[2 + b] += y
        vec[12 + b] += p
    mat = np.vstack([by_cluster[k] for k in sorted(by_cluster)])
    tot = mat.sum(axis=0)
    n = float(tot[0])
    ll_pt = float(tot[1] / n)
    ece_pt = float(np.sum(np.abs(tot[2:12] - tot[12:22])) / n * 100.0)
    return ll_pt, ece_pt, mat


def _bootstrap_from_counts(
    rng: np.random.Generator, mat: np.ndarray, replicates: int = _BOOTSTRAP_REPLICATES
) -> tuple[np.ndarray, np.ndarray]:
    """Vectorized cluster-bootstrap replicates returning `(ll_reps, ece_reps)`."""
    c_count = mat.shape[0]
    ll_reps = np.empty(replicates, dtype=np.float64)
    ece_reps = np.empty(replicates, dtype=np.float64)
    probs = np.full(c_count, 1.0 / c_count, dtype=np.float64)
    # Draw cluster weight matrix in bounded chunks to keep peak memory tiny.
    chunk = 100
    for start in range(0, replicates, chunk):
        end = min(replicates, start + chunk)
        w = rng.multinomial(c_count, probs, size=end - start).astype(np.float64)
        s = w @ mat
        n = s[:, 0]
        ll_reps[start:end] = s[:, 1] / n
        ece_reps[start:end] = np.sum(np.abs(s[:, 2:12] - s[:, 12:22]), axis=1) / n * 100.0
    return ll_reps, ece_reps


def _ci95(reps: np.ndarray, *, digits: int) -> list[float]:
    return [
        round(float(np.percentile(reps, 2.5)), digits),
        round(float(np.percentile(reps, 97.5)), digits),
    ]


def score_single_arm(rows: list[tuple[str, float, int]]) -> dict[str, Any]:
    """Score one probability arm ``[(cluster_id, p, y), ...]`` with 95% cluster bootstrap."""
    if not rows:
        return {
            "n_games": 0,
            "n_clusters": 0,
            "log_loss": None,
            "log_loss_ci95": None,
            "ece_pp": None,
            "ece_ci95": None,
        }
    ll_pt, ece_pt, mat = _bin_stats_and_ll(rows)
    n_clusters = int(mat.shape[0])
    if n_clusters < 2:
        return {
            "n_games": len(rows),
            "n_clusters": n_clusters,
            "log_loss": round(ll_pt, 5),
            "log_loss_ci95": None,
            "ece_pp": round(ece_pt, 3),
            "ece_ci95": None,
        }
    rng = np.random.default_rng(_BOOTSTRAP_SEED)
    ll_reps, ece_reps = _bootstrap_from_counts(rng, mat)
    return {
        "n_games": len(rows),
        "n_clusters": n_clusters,
        "log_loss": round(ll_pt, 5),
        "log_loss_ci95": _ci95(ll_reps, digits=5),
        "ece_pp": round(ece_pt, 3),
        "ece_ci95": _ci95(ece_reps, digits=3),
    }


def score_paired_comparison(
    pairs: list[tuple[str, float, float, int]],
) -> dict[str, Any]:
    """Paired cluster-bootstrap comparison: ``arm_a`` vs ``arm_b`` on exact same rows.

    Returns metrics for ``arm_a`` (`comp`), ``arm_b`` (`blend` or `other`), and
    paired delta ``arm_b - arm_a`` (negative means `arm_b` improves over `arm_a`).
    """
    if not pairs:
        return {
            "n_games": 0,
            "n_clusters": 0,
            "a": score_single_arm([]),
            "b": score_single_arm([]),
            "delta_b_minus_a": {
                "log_loss": None,
                "log_loss_ci95": None,
                "ll_outside_zero": None,
                "ece_pp": None,
                "ece_ci95": None,
                "ece_outside_zero": None,
            },
        }

    ll_a, ece_a, mat_a = _bin_stats_and_ll([(c, pa, y) for c, pa, _, y in pairs])
    ll_b, ece_b, mat_b = _bin_stats_and_ll([(c, pb, y) for c, _, pb, y in pairs])
    n_clusters = int(mat_a.shape[0])
    delta_ll = ll_b - ll_a
    delta_ece = ece_b - ece_a

    if n_clusters < 2:
        return {
            "n_games": len(pairs),
            "n_clusters": n_clusters,
            "a": {
                "n_games": len(pairs),
                "n_clusters": n_clusters,
                "log_loss": round(ll_a, 5),
                "log_loss_ci95": None,
                "ece_pp": round(ece_a, 3),
                "ece_ci95": None,
            },
            "b": {
                "n_games": len(pairs),
                "n_clusters": n_clusters,
                "log_loss": round(ll_b, 5),
                "log_loss_ci95": None,
                "ece_pp": round(ece_b, 3),
                "ece_ci95": None,
            },
            "delta_b_minus_a": {
                "log_loss": round(delta_ll, 5),
                "log_loss_ci95": None,
                "ll_outside_zero": None,
                "ece_pp": round(delta_ece, 3),
                "ece_ci95": None,
                "ece_outside_zero": None,
            },
        }

    # Joint paired cluster weights guarantee identical cluster draws for arm_a & arm_b.
    rng = np.random.default_rng(_BOOTSTRAP_SEED)
    probs = np.full(n_clusters, 1.0 / n_clusters, dtype=np.float64)
    ll_a_reps = np.empty(_BOOTSTRAP_REPLICATES, dtype=np.float64)
    ll_b_reps = np.empty(_BOOTSTRAP_REPLICATES, dtype=np.float64)
    ece_a_reps = np.empty(_BOOTSTRAP_REPLICATES, dtype=np.float64)
    ece_b_reps = np.empty(_BOOTSTRAP_REPLICATES, dtype=np.float64)
    chunk = 100
    for start in range(0, _BOOTSTRAP_REPLICATES, chunk):
        end = min(_BOOTSTRAP_REPLICATES, start + chunk)
        w = rng.multinomial(n_clusters, probs, size=end - start).astype(np.float64)
        sa = w @ mat_a
        sb = w @ mat_b
        na = sa[:, 0]
        nb = sb[:, 0]
        ll_a_reps[start:end] = sa[:, 1] / na
        ll_b_reps[start:end] = sb[:, 1] / nb
        ece_a_reps[start:end] = np.sum(np.abs(sa[:, 2:12] - sa[:, 12:22]), axis=1) / na * 100.0
        ece_b_reps[start:end] = np.sum(np.abs(sb[:, 2:12] - sb[:, 12:22]), axis=1) / nb * 100.0

    d_ll_reps = ll_b_reps - ll_a_reps
    d_ece_reps = ece_b_reps - ece_a_reps
    ll_ci = _ci95(d_ll_reps, digits=5)
    ece_ci = _ci95(d_ece_reps, digits=3)
    return {
        "n_games": len(pairs),
        "n_clusters": n_clusters,
        "a": {
            "n_games": len(pairs),
            "n_clusters": n_clusters,
            "log_loss": round(ll_a, 5),
            "log_loss_ci95": _ci95(ll_a_reps, digits=5),
            "ece_pp": round(ece_a, 3),
            "ece_ci95": _ci95(ece_a_reps, digits=3),
        },
        "b": {
            "n_games": len(pairs),
            "n_clusters": n_clusters,
            "log_loss": round(ll_b, 5),
            "log_loss_ci95": _ci95(ll_b_reps, digits=5),
            "ece_pp": round(ece_b, 3),
            "ece_ci95": _ci95(ece_b_reps, digits=3),
        },
        "delta_b_minus_a": {
            "log_loss": round(delta_ll, 5),
            "log_loss_ci95": ll_ci,
            "ll_outside_zero": (ll_ci[1] < 0.0) or (ll_ci[0] > 0.0),
            "ece_pp": round(delta_ece, 3),
            "ece_ci95": ece_ci,
            "ece_outside_zero": (ece_ci[1] < 0.0) or (ece_ci[0] > 0.0),
        },
    }


def _stratified_seed_order(
    events: list[dict[str, Any]], *, seed: int = _BOOTSTRAP_SEED
) -> list[dict[str, Any]]:
    """Order events in a seeded random order evenly spread across sport groups."""
    if not events:
        return []
    rng = random.Random(seed)
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in events:
        by_group[str(ev["sport_group"])].append(ev)

    ranked: list[tuple[float, int, int, dict[str, Any]]] = []
    for g_idx, sg in enumerate(sorted(by_group)):
        grp = list(by_group[sg])
        rng.shuffle(grp)
        n_g = len(grp)
        for i, ev in enumerate(grp):
            ranked.append(((i + 0.5) / n_g, g_idx, int(ev["event_id"]), ev))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in ranked]


def _interleave_odds_targets(
    pm_events: list[dict[str, Any]],
    non_pm_sample: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Interleave PM-covered events and non-PM cutoff sample proportionally."""
    n_pm = len(pm_events)
    n_non = len(non_pm_sample)
    if n_pm == 0:
        return list(non_pm_sample)
    if n_non == 0:
        return list(pm_events)
    tagged: list[tuple[float, int, dict[str, Any]]] = []
    for i, ev in enumerate(pm_events):
        tagged.append(((i + 0.5) / n_pm, 0, ev))
    for i, ev in enumerate(non_pm_sample):
        tagged.append(((i + 0.5) / n_non, 1, ev))
    tagged.sort(key=lambda item: (item[0], item[1], int(item[2]["event_id"])))
    return [item[2] for item in tagged]


async def read_pre_nov6_observations(
    db_url: str,
    *,
    batch_pause_s: float = _INTER_BATCH_PAUSE_S,
    odds_stmt_timeout_s: int = _ODDS_STMT_TIMEOUT_S,
    wp_stmt_timeout_s: int = _WP_STMT_TIMEOUT_S,
    max_read_duration_s: float = _MAX_READ_DURATION_S,
    non_pm_sample_limit: int = _NON_PM_ODDS_SAMPLE_LIMIT,
    db_role_note: str = _DB_ROLE_NOTE,
    force_stop_after_odds_batches: int | None = None,
) -> dict[str, Any]:
    """Two-phase read of pre-Nov-6 observations with load bounds and partial-read survival.

    Phase 1: win_prob_snapshots across all pre-Nov-6 completed games (stratified seeded-random).
    Phase 2: odds_snapshots ONLY for games with >=1 Kalshi/Polymarket reading at any cutoff,
             plus a seeded-random stratified sample of up to 4,000 remaining Phase-1 games.
    Stops cleanly on any statement timeout (zero retries) or after `max_read_duration_s`
    and keeps every batch read so far for scoring.
    """
    started = time.monotonic()
    deadline = started + max_read_duration_s
    engine = create_async_engine(
        _async_db_url(db_url),
        connect_args={
            "server_settings": {
                "default_transaction_read_only": "on",
            }
        },
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    stopped_early = False
    stop_reason: str | None = None
    stop_stage: str | None = None

    def _assemble_horizon_records(
        wp_events: list[dict[str, Any]],
        wp_by_eh: dict[tuple[int, str], dict[str, dict[str, Any]]],
        odds_fetched_eids: set[int],
        books_by_eb: dict[int, dict[str, tuple[list[datetime], list[dict[str, Any]]]]],
        cutoffs_by_eid: dict[int, list[tuple[str, datetime]]],
        cluster_by_eid: dict[int, str],
    ) -> dict[str, dict[int, dict[str, Any]]]:
        records_by_horizon: dict[str, dict[int, dict[str, Any]]] = {
            h: {} for h in HORIZON_DISPLAY_ORDER
        }
        for ev in wp_events:
            eid = int(ev["event_id"])
            y = 1 if int(ev["home_score"]) > int(ev["away_score"]) else 0
            sport_group = str(ev["sport_group"])
            league = str(ev["league"])
            cid = cluster_by_eid[eid]
            has_odds = eid in odds_fetched_eids
            ev_books = books_by_eb.get(eid, {}) if has_odds else {}

            for h_name, cutoff in cutoffs_by_eid[eid]:
                sources_payload: dict[str, dict[str, Any]] = {}
                raw_probs: dict[str, float] = {}

                for src, info in wp_by_eh.get((eid, h_name), {}).items():
                    raw_probs[src] = info["prob"]
                    stamp = _effective_stamp(info["captured_at"], info["valid_until"], cutoff)
                    sources_payload[src] = {
                        "value": info["prob"],
                        "updated_at": stamp.isoformat(),
                    }

                if has_odds:
                    active_books: list[dict[str, Any]] = []
                    active_stamps: list[datetime] = []
                    for _bm, (caps, rows_list) in ev_books.items():
                        idx_pos = bisect_right(caps, cutoff) - 1
                        if idx_pos >= 0:
                            row_sel = rows_list[idx_pos]
                            active_books.append(row_sel)
                            active_stamps.append(
                                _effective_stamp(
                                    row_sel["captured_at"], row_sel["valid_until"], cutoff
                                )
                            )
                    betting = rebuild_betting(active_books)
                    if betting["value"] is not None and active_stamps:
                        raw_probs["betting"] = float(betting["value"])
                        sources_payload["betting"] = {
                            "value": float(betting["value"]),
                            "updated_at": max(active_stamps).isoformat(),
                        }

                if not raw_probs:
                    continue

                if "kalshi" in raw_probs and "polymarket" in raw_probs:
                    raw_probs["pm_avg"] = 0.5 * (raw_probs["kalshi"] + raw_probs["polymarket"])

                blend_prob: float | None = None
                if has_odds and sources_payload:
                    computed, _ = compute_aggregate_probability_tiered(
                        SimpleNamespace(
                            win_probability_sources=sources_payload,
                            status="scheduled",
                            espn_win_prob_home=None,
                            opening_home_probability=None,
                        ),
                        "scheduled",
                    )
                    if computed is not None:
                        blend_prob = float(computed)

                records_by_horizon[h_name][eid] = {
                    "event_id": eid,
                    "cluster_id": cid,
                    "sport_group": sport_group,
                    "league": league,
                    "outcome": y,
                    "odds_read": has_odds,
                    "n_sources_blended": len(sources_payload) if blend_prob is not None else 0,
                    "sources": raw_probs,
                    "blend": blend_prob,
                }
        return records_by_horizon

    try:
        async with Session() as s:
            await s.execute(text("SET LOCAL transaction_read_only = on"))
            await s.execute(text(f"SET LOCAL statement_timeout = '{_EVENTS_STMT_TIMEOUT_S}s'"))
            try:
                res = await s.execute(text(EVENTS_SQL))
                raw_event_rows = [dict(r) for r in res.mappings()]
                await s.rollback()
            except Exception as exc:  # noqa: BLE001
                await s.rollback()
                return {
                    "timed_out": is_statement_timeout(exc),
                    "stage": "events_scan",
                    "statement_timeout_s": _EVENTS_STMT_TIMEOUT_S,
                    "elapsed_s": round(time.monotonic() - started, 2),
                    "database": db_role_note,
                    "error": str(exc),
                }

        cluster_by_eid = assign_series_clusters(raw_event_rows)
        ordered_events = _stratified_seed_order(raw_event_rows, seed=_BOOTSTRAP_SEED)

        cutoffs_by_eid: dict[int, list[tuple[str, datetime]]] = {}
        for ev in ordered_events:
            eid = int(ev["event_id"])
            st = _as_utc(ev["start"])
            cutoffs_by_eid[eid] = [(h_name, st - offset) for h_name, offset in HORIZONS]

        statements_executed = 1
        wp_batches_total = math.ceil(len(ordered_events) / _BATCH_SIZE) if ordered_events else 0
        wp_batches_done = 0
        wp_events_read: list[dict[str, Any]] = []
        wp_by_eh: dict[tuple[int, str], dict[str, dict[str, Any]]] = defaultdict(dict)
        pm_eids: set[int] = set()

        odds_fetched_eids: set[int] = set()
        books_by_eb: dict[int, dict[str, tuple[list[datetime], list[dict[str, Any]]]]] = defaultdict(dict)
        odds_target_pm = 0
        odds_target_non_pm_pool = 0
        odds_target_non_pm_sample = 0
        odds_batches_total = 0
        odds_batches_done = 0

        async with Session() as s:
            wp_stmt = text(WIN_PROB_BATCH_SQL)
            odds_stmt = text(ODDS_BATCH_SQL)

            # ── Phase 1: win_prob_snapshots across ALL pre-Nov-6 games ──
            for b_idx in range(wp_batches_total):
                if time.monotonic() >= deadline:
                    stopped_early = True
                    stop_reason = f"max_read_duration_{int(max_read_duration_s)}s"
                    stop_stage = "win_prob_batch"
                    break

                if b_idx > 0 and batch_pause_s > 0:
                    await asyncio.sleep(batch_pause_s)
                    if time.monotonic() >= deadline:
                        stopped_early = True
                        stop_reason = f"max_read_duration_{int(max_read_duration_s)}s"
                        stop_stage = "win_prob_batch"
                        break

                batch = ordered_events[b_idx * _BATCH_SIZE : (b_idx + 1) * _BATCH_SIZE]
                u_eids: list[int] = []
                u_cutoffs: list[datetime] = []
                u_horizons: list[str] = []
                for ev in batch:
                    eid = int(ev["event_id"])
                    for h_name, cutoff in cutoffs_by_eid[eid]:
                        u_eids.append(eid)
                        u_cutoffs.append(cutoff)
                        u_horizons.append(h_name)

                await s.rollback()
                await s.execute(text("SET LOCAL transaction_read_only = on"))
                await s.execute(text(f"SET LOCAL statement_timeout = '{wp_stmt_timeout_s}s'"))
                try:
                    wp_res = await s.execute(
                        wp_stmt,
                        {"event_ids": u_eids, "cutoffs": u_cutoffs, "horizons": u_horizons},
                    )
                    wp_rows = wp_res.mappings().all()
                    statements_executed += 1
                    await s.rollback()
                except Exception as exc:  # noqa: BLE001
                    await s.rollback()
                    stopped_early = True
                    stop_reason = (
                        f"statement_timeout_{wp_stmt_timeout_s}s"
                        if is_statement_timeout(exc)
                        else f"error:{type(exc).__name__}"
                    )
                    stop_stage = "win_prob_batch"
                    break

                wp_batches_done += 1
                wp_events_read.extend(batch)
                for r in wp_rows:
                    eid = int(r["event_id"])
                    h_name = str(r["horizon"])
                    src = str(r["source"])
                    prob = _valid_prob(r["home_win_probability"])
                    if prob is None:
                        continue
                    key_src = "mlb" if src == "fangraphs" else src
                    if src == "fangraphs" and "mlb" in wp_by_eh[(eid, h_name)]:
                        continue
                    if key_src in ("kalshi", "polymarket"):
                        pm_eids.add(eid)
                    wp_by_eh[(eid, h_name)][key_src] = {
                        "prob": prob,
                        "captured_at": _as_utc(r["captured_at"]),
                        "valid_until": _as_utc(r["valid_until"]) if r["valid_until"] else None,
                    }

            # ── Phase 2: odds_snapshots ONLY for PM-covered games + seeded-random 4,000 non-PM games ──
            if not stopped_early and wp_events_read:
                pm_events = [ev for ev in wp_events_read if int(ev["event_id"]) in pm_eids]
                non_pm_pool = [ev for ev in wp_events_read if int(ev["event_id"]) not in pm_eids]
                non_pm_strat = _stratified_seed_order(non_pm_pool, seed=_BOOTSTRAP_SEED + 1)
                non_pm_sample = non_pm_strat[: min(non_pm_sample_limit, len(non_pm_strat))]
                pm_strat = _stratified_seed_order(pm_events, seed=_BOOTSTRAP_SEED + 2)
                odds_targets = _interleave_odds_targets(pm_strat, non_pm_sample)

                odds_target_pm = len(pm_strat)
                odds_target_non_pm_pool = len(non_pm_pool)
                odds_target_non_pm_sample = len(non_pm_sample)
                odds_batches_total = math.ceil(len(odds_targets) / _BATCH_SIZE) if odds_targets else 0

                for b_idx in range(odds_batches_total):
                    if force_stop_after_odds_batches is not None and b_idx >= force_stop_after_odds_batches:
                        stopped_early = True
                        stop_reason = f"simulated_stop_after_{force_stop_after_odds_batches}_odds_batches"
                        stop_stage = "odds_batch"
                        break
                    if time.monotonic() >= deadline:
                        stopped_early = True
                        stop_reason = f"max_read_duration_{int(max_read_duration_s)}s"
                        stop_stage = "odds_batch"
                        break

                    if batch_pause_s > 0:
                        await asyncio.sleep(batch_pause_s)
                        if time.monotonic() >= deadline:
                            stopped_early = True
                            stop_reason = f"max_read_duration_{int(max_read_duration_s)}s"
                            stop_stage = "odds_batch"
                            break

                    batch = odds_targets[b_idx * _BATCH_SIZE : (b_idx + 1) * _BATCH_SIZE]
                    eids_param = [int(ev["event_id"]) for ev in batch]
                    await s.rollback()
                    await s.execute(text("SET LOCAL transaction_read_only = on"))
                    await s.execute(text(f"SET LOCAL statement_timeout = '{odds_stmt_timeout_s}s'"))
                    try:
                        odds_res = await s.execute(odds_stmt, {"event_ids": eids_param})
                        odds_rows = odds_res.mappings().all()
                        statements_executed += 1
                        await s.rollback()
                    except Exception as exc:  # noqa: BLE001
                        await s.rollback()
                        stopped_early = True
                        stop_reason = (
                            f"statement_timeout_{odds_stmt_timeout_s}s"
                            if is_statement_timeout(exc)
                            else f"error:{type(exc).__name__}"
                        )
                        stop_stage = "odds_batch"
                        break

                    odds_batches_done += 1
                    odds_fetched_eids.update(eids_param)
                    for r in odds_rows:
                        eid = int(r["event_id"])
                        bm = str(r["bookmaker"])
                        cap = _as_utc(r["captured_at"])
                        entry = books_by_eb[eid].get(bm)
                        if entry is None:
                            entry = ([], [])
                            books_by_eb[eid][bm] = entry
                        entry[0].append(cap)
                        entry[1].append(
                            {
                                "home_win_probability": float(r["home_win_probability"]),
                                "captured_at": cap,
                                "valid_until": _as_utc(r["valid_until"]) if r["valid_until"] else None,
                            }
                        )

        records_by_horizon = _assemble_horizon_records(
            wp_events_read,
            wp_by_eh,
            odds_fetched_eids,
            books_by_eb,
            cutoffs_by_eid,
            cluster_by_eid,
        )
        return {
            "timed_out": stopped_early and (stop_reason or "").startswith("statement_timeout"),
            "stopped_early": stopped_early,
            "stop_reason": stop_reason,
            "stop_stage": stop_stage,
            "database": db_role_note,
            "ceiling": _PRE_NOV6_ISO,
            "wp_statement_timeout_s": wp_stmt_timeout_s,
            "odds_statement_timeout_s": odds_stmt_timeout_s,
            "batch_pause_s": batch_pause_s,
            "max_read_duration_s": max_read_duration_s,
            "events_total": len(ordered_events),
            "wp_events_read": len(wp_events_read),
            "wp_batches_done": wp_batches_done,
            "wp_batches_total": wp_batches_total,
            "odds_target_pm": odds_target_pm,
            "odds_target_non_pm_pool": odds_target_non_pm_pool,
            "odds_target_non_pm_sample": odds_target_non_pm_sample,
            "odds_events_read": len(odds_fetched_eids),
            "odds_batches_done": odds_batches_done,
            "odds_batches_total": odds_batches_total,
            "events_read": len(wp_events_read),
            "clusters_read": len({cluster_by_eid[int(ev["event_id"])] for ev in wp_events_read}),
            "batches_total": wp_batches_total + odds_batches_total,
            "statements_executed": statements_executed,
            "elapsed_s": round(time.monotonic() - started, 2),
            "records_by_horizon": records_by_horizon,
        }
    finally:
        await engine.dispose()


def _build_pairwise_and_common(
    records: list[dict[str, Any]], *, multi_only: bool
) -> dict[str, Any]:
    pool = [
        r
        for r in records
        if r["blend"] is not None and (not multi_only or r["n_sources_blended"] >= 2)
    ]
    pairwise: dict[str, dict[str, Any]] = {}
    for comp in COMPARATORS:
        pairs = [
            (r["cluster_id"], r["sources"][comp], r["blend"], r["outcome"])
            for r in pool
            if comp in r["sources"]
        ]
        pairwise[comp] = score_paired_comparison(pairs)

    common_sets: list[dict[str, Any]] = []
    for title, req_keys in COMMON_OVERLAP_SETS:
        matched = [r for r in pool if all(k in r["sources"] for k in req_keys)]
        if not matched:
            continue
        arms: dict[str, Any] = {
            "blend": score_single_arm([(r["cluster_id"], r["blend"], r["outcome"]) for r in matched])
        }
        deltas_vs_blend: dict[str, Any] = {}
        for k in req_keys:
            comp_res = score_paired_comparison(
                [(r["cluster_id"], r["sources"][k], r["blend"], r["outcome"]) for r in matched]
            )
            arms[k] = comp_res["a"]
            deltas_vs_blend[k] = comp_res["delta_b_minus_a"]
        common_sets.append(
            {
                "title": title,
                "keys": list(req_keys),
                "n_games": len(matched),
                "n_clusters": len({r["cluster_id"] for r in matched}),
                "arms": arms,
                "delta_blend_minus_comp": deltas_vs_blend,
            }
        )
    return {"pairwise": pairwise, "common_sets": common_sets}


def compute_analysis_report(obs: dict[str, Any]) -> dict[str, Any]:
    """Compute Item 1 & Item 2 tables (overall + by sport, across all 4 cutoffs + cutoff gaps)."""
    records_by_h: dict[str, dict[int, dict[str, Any]]] = obs["records_by_horizon"]

    # Collect all sport groups seen in start horizon (or union across horizons).
    sport_groups = sorted(
        {
            r["sport_group"]
            for h_map in records_by_h.values()
            for r in h_map.values()
        }
    )

    horizons_report: dict[str, Any] = {}
    for h_name in HORIZON_DISPLAY_ORDER:
        all_recs = list(records_by_h[h_name].values())
        by_sport: dict[str, Any] = {}
        for sg in sport_groups:
            sg_recs = [r for r in all_recs if r["sport_group"] == sg]
            if not sg_recs:
                continue
            by_sport[sg] = {
                "n_events": len(sg_recs),
                "multi_source": _build_pairwise_and_common(sg_recs, multi_only=True),
                "all_matched": _build_pairwise_and_common(sg_recs, multi_only=False),
            }
        horizons_report[h_name] = {
            "label": HORIZON_LABELS[h_name],
            "n_events": len(all_recs),
            "overall": {
                "multi_source": _build_pairwise_and_common(all_recs, multi_only=True),
                "all_matched": _build_pairwise_and_common(all_recs, multi_only=False),
            },
            "by_sport": by_sport,
        }

    # Item 2: Cutoff-to-cutoff paired differences on exact same games present at both cutoffs.
    cutoff_gaps: dict[str, Any] = {"overall": {}, "by_sport": {}}
    all_arms = ("blend",) + COMPARATORS

    def _pair_cutoffs(sg_filter: str | None) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for h_near, h_far in CUTOFF_PAIRS:
            pair_key = f"{h_near} - {h_far}"
            near_map = records_by_h[h_near]
            far_map = records_by_h[h_far]
            shared_eids = sorted(set(near_map) & set(far_map))
            if sg_filter is not None:
                shared_eids = [eid for eid in shared_eids if near_map[eid]["sport_group"] == sg_filter]
            arm_gaps: dict[str, Any] = {}
            for arm in all_arms:
                rows_paired: list[tuple[str, float, float, int]] = []
                for eid in shared_eids:
                    rn, rf = near_map[eid], far_map[eid]
                    pn = rn["blend"] if arm == "blend" else rn["sources"].get(arm)
                    pf = rf["blend"] if arm == "blend" else rf["sources"].get(arm)
                    if pn is None or pf is None:
                        continue
                    # a = far (earlier), b = near (closer to start) -> delta = near - far
                    rows_paired.append((rn["cluster_id"], pf, pn, rn["outcome"]))
                if rows_paired:
                    arm_gaps[arm] = score_paired_comparison(rows_paired)
            out[pair_key] = arm_gaps

        # Also score exact 4-cutoff common set for `blend` and core sources
        four_eids = sorted(
            set(records_by_h["start"])
            & set(records_by_h["t_minus_1h"])
            & set(records_by_h["t_minus_6h"])
            & set(records_by_h["t_minus_24h"])
        )
        if sg_filter is not None:
            four_eids = [
                eid for eid in four_eids if records_by_h["start"][eid]["sport_group"] == sg_filter
            ]
        four_common: dict[str, Any] = {}
        for arm in all_arms:
            valid_eids = []
            for eid in four_eids:
                vals = [
                    records_by_h[h][eid]["blend"]
                    if arm == "blend"
                    else records_by_h[h][eid]["sources"].get(arm)
                    for h in HORIZON_DISPLAY_ORDER
                ]
                if all(v is not None for v in vals):
                    valid_eids.append((eid, vals))
            if not valid_eids:
                continue
            per_h = {
                h: score_single_arm(
                    [
                        (
                            records_by_h[h][eid]["cluster_id"],
                            vals[idx],
                            records_by_h[h][eid]["outcome"],
                        )
                        for eid, vals in valid_eids
                    ]
                )
                for idx, h in enumerate(HORIZON_DISPLAY_ORDER)
            }
            four_common[arm] = {
                "n_games": len(valid_eids),
                "by_horizon": per_h,
                "start_minus_24h": score_paired_comparison(
                    [
                        (
                            records_by_h["start"][eid]["cluster_id"],
                            vals[3],
                            vals[0],
                            records_by_h["start"][eid]["outcome"],
                        )
                        for eid, vals in valid_eids
                    ]
                )["delta_b_minus_a"],
            }
        out["four_cutoff_common_set"] = four_common
        return out

    cutoff_gaps["overall"] = _pair_cutoffs(None)
    for sg in sport_groups:
        cutoff_gaps["by_sport"][sg] = _pair_cutoffs(sg)

    return {
        "meta": {
            "database": obs["database"],
            "stopped_early": obs["stopped_early"],
            "stop_reason": obs["stop_reason"],
            "stop_stage": obs["stop_stage"],
            "ceiling": obs["ceiling"],
            "wp_statement_timeout_s": obs["wp_statement_timeout_s"],
            "odds_statement_timeout_s": obs["odds_statement_timeout_s"],
            "batch_pause_s": obs["batch_pause_s"],
            "max_read_duration_s": obs["max_read_duration_s"],
            "events_total": obs["events_total"],
            "wp_events_read": obs["wp_events_read"],
            "wp_batches_done": obs["wp_batches_done"],
            "wp_batches_total": obs["wp_batches_total"],
            "odds_target_pm": obs["odds_target_pm"],
            "odds_target_non_pm_pool": obs["odds_target_non_pm_pool"],
            "odds_target_non_pm_sample": obs["odds_target_non_pm_sample"],
            "odds_events_read": obs["odds_events_read"],
            "odds_batches_done": obs["odds_batches_done"],
            "odds_batches_total": obs["odds_batches_total"],
            "events_read": obs["events_read"],
            "clusters_read": obs["clusters_read"],
            "batches_total": obs["batches_total"],
            "statements_executed": obs["statements_executed"],
            "elapsed_s": obs["elapsed_s"],
            "bootstrap_seed": _BOOTSTRAP_SEED,
            "bootstrap_replicates": _BOOTSTRAP_REPLICATES,
            "log_loss_clip": _LOG_LOSS_CLIP,
            "target": "home_win (1 if home_score > away_score else 0; draws = 0)",
        },
        "horizons": horizons_report,
        "cutoff_gaps": cutoff_gaps,
    }


def _fmt_val_ci(val: float | None, ci: list[float] | None, *, fmt: str, unit: str = "") -> str:
    if val is None:
        return "—"
    v_s = f"{val:{fmt}}{unit}"
    if ci is None:
        return v_s
    return f"{v_s} [{ci[0]:{fmt}}, {ci[1]:{fmt}}]"


def format_markdown_summary(report: dict[str, Any]) -> str:
    """Render concise Markdown tables for Items 1 & 2 with DB, counts, stop state, and replay limits."""
    m = report["meta"]
    stop_line = (
        f"PARTIAL STOP (`{m['stop_stage']}` / `{m['stop_reason']}`): scored `{m['wp_events_read']}/{m['events_total']}` win-prob games and `{m['odds_events_read']}` odds+blend games"
        if m["stopped_early"]
        else f"COMPLETE: `{m['wp_events_read']}/{m['events_total']}` win-prob games and `{m['odds_events_read']}` odds+blend games"
    )
    lines = [
        f"**Database Read:** `{m['database']}`",
        f"**Run Coverage & Bounds:** {stop_line} · `odds_target_pm={m['odds_target_pm']}` + `odds_target_non_pm_sample={m['odds_target_non_pm_sample']}` (from `{m['odds_target_non_pm_pool']}` non-PM games) · `wp_batches={m['wp_batches_done']}/{m['wp_batches_total']}` · `odds_batches={m['odds_batches_done']}/{m['odds_batches_total']}` · `pause={m['batch_pause_s']}s` · `timeouts=120s wp / {m['odds_statement_timeout_s']}s odds` · `cap={int(m['max_read_duration_s'])}s` · `elapsed={m['elapsed_s']}s` · `ceiling < {m['ceiling']}`",
        "",
        "### Replay Limits (Section 3 — kept at top)",
        *REPLAY_LIMITS,
        "",
        "### Item 1 & Item 2 — Paired Log Loss (first) & Typical Miss / ECE (second), Multi-Source Blended Games (`>= 2` sources, `odds_read` games)",
    ]

    for h_name in HORIZON_DISPLAY_ORDER:
        h_data = report["horizons"][h_name]
        lines.append(f"\n#### {h_data['label']} (events with replay = {h_data['n_events']})")
        lines.append(
            "| Comparator | Games | Clusters | Comp Log Loss (95% CI) | Blend Log Loss (95% CI) | Δ Log Loss Blend−Comp (95% CI) | Comp Miss (95% CI) | Blend Miss (95% CI) | Δ Miss Blend−Comp (95% CI) |"
        )
        lines.append("|---|---:|---:|---|---|---|---|---|---|")
        pw = h_data["overall"]["multi_source"]["pairwise"]
        for comp in COMPARATORS:
            row = pw[comp]
            if row["n_games"] == 0:
                continue
            a, b, d = row["a"], row["b"], row["delta_b_minus_a"]
            ll_flag = " **(OUTSIDE 0)**" if d["ll_outside_zero"] else ""
            ec_flag = " **(OUTSIDE 0)**" if d["ece_outside_zero"] else ""
            lines.append(
                f"| {COMPARATOR_LABELS[comp]} | {row['n_games']} | {row['n_clusters']} | "
                f"{_fmt_val_ci(a['log_loss'], a['log_loss_ci95'], fmt='.4f')} | "
                f"{_fmt_val_ci(b['log_loss'], b['log_loss_ci95'], fmt='.4f')} | "
                f"{_fmt_val_ci(d['log_loss'], d['log_loss_ci95'], fmt='+.4f')}{ll_flag} | "
                f"{_fmt_val_ci(a['ece_pp'], a['ece_ci95'], fmt='.2f', unit='pt')} | "
                f"{_fmt_val_ci(b['ece_pp'], b['ece_ci95'], fmt='.2f', unit='pt')} | "
                f"{_fmt_val_ci(d['ece_pp'], d['ece_ci95'], fmt='+.2f', unit='pt')}{ec_flag} |"
            )

    lines.append("\n### Item 2 — Cutoff-to-Cutoff Paired Gaps (Closer to Start minus Further from Start)")
    lines.append(
        "| Arm | Cutoff Pair | Same Games | Clusters | Δ Log Loss (95% CI) | Δ Typical Miss (95% CI) | Outside 95% CI? |"
    )
    lines.append("|---|---|---:|---:|---|---|---|")
    ov_gaps = report["cutoff_gaps"]["overall"]
    for h_near, h_far in CUTOFF_PAIRS:
        pkey = f"{h_near} - {h_far}"
        for arm in ("blend",) + COMPARATORS:
            row = ov_gaps.get(pkey, {}).get(arm)
            if not row or row["n_games"] == 0:
                continue
            d = row["delta_b_minus_a"]
            flag = []
            if d["ll_outside_zero"]:
                flag.append("LogLoss")
            if d["ece_outside_zero"]:
                flag.append("Miss")
            lines.append(
                f"| {COMPARATOR_LABELS[arm]} | `{pkey}` | {row['n_games']} | {row['n_clusters']} | "
                f"{_fmt_val_ci(d['log_loss'], d['log_loss_ci95'], fmt='+.4f')} | "
                f"{_fmt_val_ci(d['ece_pp'], d['ece_ci95'], fmt='+.2f', unit='pt')} | "
                f"{', '.join(flag) if flag else 'no'} |"
            )

    lines.append("\n### By Sport Breakdown (Start T-0, Multi-Source Blended Games)")
    start_sports = report["horizons"]["start"]["by_sport"]
    for sg in sorted(start_sports):
        sg_pw = start_sports[sg]["multi_source"]["pairwise"]
        active = [(c, sg_pw[c]) for c in COMPARATORS if sg_pw[c]["n_games"] > 0]
        if not active:
            continue
        lines.append(f"\n**{sg}** (`Start` events = {start_sports[sg]['n_events']})")
        lines.append(
            "| Comparator | Games | Clusters | Comp Log Loss | Blend Log Loss | Δ Log Loss (95% CI) | Comp Miss | Blend Miss | Δ Miss (95% CI) |"
        )
        lines.append("|---|---:|---:|---:|---:|---|---:|---:|---|")
        for c, row in active:
            a, b, d = row["a"], row["b"], row["delta_b_minus_a"]
            lines.append(
                f"| {COMPARATOR_LABELS[c]} | {row['n_games']} | {row['n_clusters']} | "
                f"{a['log_loss']:.4f} | {b['log_loss']:.4f} | "
                f"{_fmt_val_ci(d['log_loss'], d['log_loss_ci95'], fmt='+.4f')} | "
                f"{a['ece_pp']:.2f}pt | {b['ece_pp']:.2f}pt | "
                f"{_fmt_val_ci(d['ece_pp'], d['ece_ci95'], fmt='+.2f', unit='pt')} |"
            )
    return "\n".join(lines)


async def _run_self_test() -> None:
    db_name = "bl_12108_math_selftest_tmp"
    subprocess.run(["dropdb", "-h", "/tmp", "--if-exists", db_name], check=True)
    subprocess.run(["createdb", "-h", "/tmp", db_name], check=True)
    db_url = f"postgresql+asyncpg://bain@localhost:5432/{db_name}"
    pg14_safe_tables = [
        t for t in Base.metadata.sorted_tables if t.name != "container_provider_anchors"
    ]

    async def _seed() -> None:
        engine = create_async_engine(db_url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=pg14_safe_tables))
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with Session() as s:
                await s.execute(
                    text(
                        'INSERT INTO sports (id, key, name, "group", active) VALUES '
                        "(1, 'basketball_nba', 'NBA', 'Basketball', true), "
                        "(2, 'baseball_mlb', 'MLB', 'Baseball', true), "
                        "(3, 'soccer_epl', 'EPL', 'Soccer', true)"
                    )
                )
                # Seed 6 PM games (3 NBA + 2 MLB + 1 EPL) + 3 non-PM pre-Nov-6 games + 3 Nov-6 excluded controls
                events_spec = [
                    (71001, 1, "st-1", "Team Alpha", "Team Beta",
                     datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc),
                     datetime(2026, 10, 20, 22, 30, tzinfo=timezone.utc), 110, 104),
                    (71002, 1, "st-2", "Team Beta", "Team Alpha",
                     datetime(2026, 10, 22, 20, 0, tzinfo=timezone.utc),
                     datetime(2026, 10, 22, 22, 30, tzinfo=timezone.utc), 98, 106),
                    (71003, 1, "st-3", "Team Gamma", "Team Delta",
                     datetime(2026, 10, 28, 20, 0, tzinfo=timezone.utc),
                     datetime(2026, 10, 28, 22, 30, tzinfo=timezone.utc), 115, 102),
                    (71004, 2, "st-4", "Clubs North", "Clubs South",
                     datetime(2026, 10, 10, 19, 0, tzinfo=timezone.utc),
                     datetime(2026, 10, 10, 22, 15, tzinfo=timezone.utc), 5, 2),
                    (71005, 2, "st-5", "Clubs South", "Clubs North",
                     datetime(2026, 10, 11, 19, 0, tzinfo=timezone.utc),
                     datetime(2026, 10, 11, 22, 15, tzinfo=timezone.utc), 1, 4),
                    (71006, 3, "st-6", "City FC", "United FC",
                     datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc),
                     datetime(2026, 10, 18, 17, 0, tzinfo=timezone.utc), 2, 0),
                    # 3 non-PM pre-Nov-6 games (tests non_pm sampling cap!)
                    (71007, 1, "nonpm-1", "NonPM A", "NonPM B",
                     datetime(2026, 10, 15, 20, 0, tzinfo=timezone.utc),
                     datetime(2026, 10, 15, 22, 30, tzinfo=timezone.utc), 108, 101),
                    (71008, 2, "nonpm-2", "NonPM C", "NonPM D",
                     datetime(2026, 10, 16, 19, 0, tzinfo=timezone.utc),
                     datetime(2026, 10, 16, 22, 0, tzinfo=timezone.utc), 6, 3),
                    (71009, 3, "nonpm-3", "NonPM E", "NonPM F",
                     datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc),
                     datetime(2026, 10, 17, 17, 0, tzinfo=timezone.utc), 3, 1),
                    (71901, 1, "ex-start", "Holdout A", "Holdout B",
                     datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc),
                     datetime(2026, 11, 6, 2, 30, tzinfo=timezone.utc), 100, 99),
                    (71902, 1, "ex-comp", "Holdout C", "Holdout D",
                     datetime(2026, 11, 5, 22, 0, tzinfo=timezone.utc),
                     datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc), 105, 97),
                    (71903, 1, "ex-obs", "Holdout E", "Holdout F",
                     datetime(2026, 11, 5, 19, 0, tzinfo=timezone.utc),
                     datetime(2026, 11, 5, 21, 30, tzinfo=timezone.utc), 101, 103),
                ]
                for eid, sid, ext, hm, aw, ct, comp_at, hs, as_ in events_spec:
                    obs_at = (
                        datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
                        if eid == 71903
                        else comp_at
                    )
                    await s.execute(
                        text(
                            "INSERT INTO events (id, sport_id, external_id, home_team_name, away_team_name, "
                            "commence_time, completed_at, score_observed_at, status, home_score, away_score) "
                            "VALUES (:eid, :sid, :ext, :hm, :aw, :ct, :comp, :obs, 'completed', :hs, :as)"
                        ),
                        {
                            "eid": eid, "sid": sid, "ext": ext, "hm": hm, "aw": aw,
                            "ct": ct, "comp": comp_at, "obs": obs_at, "hs": hs, "as": as_,
                        },
                    )
                oid = 1
                wid = 1
                for eid, sid, ext, hm, aw, ct, comp_at, hs, as_ in events_spec:
                    home_won = hs > as_
                    for h_off_idx, hrs in enumerate([25, 7, 2, 0]):
                        ts = ct - timedelta(hours=hrs, minutes=15)
                        vu = ct + timedelta(minutes=1)
                        shift = h_off_idx * 0.02 * (1 if home_won else -1)
                        base = 0.62 if home_won else 0.36
                        for bm, adj in [("book1", -0.01), ("book2", 0.0), ("book3", 0.01)]:
                            oid += 1
                            await s.execute(
                                text(
                                    "INSERT INTO odds_snapshots (id, event_id, bookmaker, captured_at, valid_until, reading_count, home_win_probability) "
                                    "VALUES (:id, :eid, :bm, :cap, :vu, 1, :p)"
                                ),
                                {
                                    "id": oid, "eid": eid, "bm": bm, "cap": ts, "vu": vu,
                                    "p": round(base + shift + adj, 4),
                                },
                            )
                        srcs = [
                            ("espn", round(base - 0.04 + shift, 4)),
                            ("stat_model", round(base - 0.01 + shift, 4)),
                        ]
                        if eid not in (71007, 71008, 71009):
                            srcs.extend([
                                ("kalshi", round(base + 0.02 + shift, 4)),
                                ("polymarket", round(base - 0.02 + shift, 4)),
                            ])
                        if sid == 2:
                            srcs.append(("mlb", round(base + 0.01 + shift, 4)))
                        for src_name, p_val in srcs:
                            wid += 1
                            await s.execute(
                                text(
                                    "INSERT INTO win_prob_snapshots (id, event_id, source, captured_at, valid_until, reading_count, home_win_probability) "
                                    "VALUES (:id, :eid, :src, :cap, :vu, 1, :p)"
                                ),
                                {"id": wid, "eid": eid, "src": src_name, "cap": ts, "vu": vu, "p": p_val},
                            )
                await s.commit()
        finally:
            await engine.dispose()

    try:
        await _seed()
        # Verify full two-phase run with non_pm_sample_limit=2 (out of 3 non-PM games -> 6 + 2 = 8 odds games!)
        obs = await read_pre_nov6_observations(
            db_url,
            batch_pause_s=0.0,
            non_pm_sample_limit=2,
        )
        assert obs["stopped_early"] is False, obs
        assert obs["events_read"] == 9, obs
        assert obs["odds_target_pm"] == 6 and obs["odds_target_non_pm_sample"] == 2 and obs["odds_events_read"] == 8, obs
        # One game without odds read must have blend=None (never a fake no-books blend)
        no_odds = [r for r in obs["records_by_horizon"]["start"].values() if not r["odds_read"]]
        assert len(no_odds) == 1 and no_odds[0]["blend"] is None, no_odds
        report = compute_analysis_report(obs)
        start_pw = report["horizons"]["start"]["overall"]["multi_source"]["pairwise"]
        assert start_pw["kalshi"]["n_games"] == 6
        assert start_pw["espn"]["n_games"] == 8
        md = format_markdown_summary(report)
        assert "postgresql-globular-51563" in md and "Replay Limits" in md

        # Verify early stop keeps batches already read and scores cleanly
        obs_part = await read_pre_nov6_observations(
            db_url,
            batch_pause_s=0.0,
            non_pm_sample_limit=2,
            force_stop_after_odds_batches=0,
        )
        assert obs_part["stopped_early"] is True and obs_part["wp_events_read"] == 9
        rep_part = compute_analysis_report(obs_part)
        assert "PARTIAL STOP" in format_markdown_summary(rep_part)
        print(
            json.dumps(
                {
                    "self_test": "PASSED",
                    "events_read": obs["events_read"],
                    "nov6_controls_excluded": 3,
                    "odds_target_pm": obs["odds_target_pm"],
                    "odds_target_non_pm_pool": obs["odds_target_non_pm_pool"],
                    "odds_target_non_pm_sample": obs["odds_target_non_pm_sample"],
                    "odds_events_read": obs["odds_events_read"],
                    "partial_stop_verified": True,
                },
                indent=2,
            )
        )
    finally:
        subprocess.run(["dropdb", "-h", "/tmp", "--if-exists", db_name], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--print-sql", action="store_true")
    mode.add_argument("--production", action="store_true")
    parser.add_argument("--alex-approved", action="store_true")
    parser.add_argument("--fable-sql-read-go", action="store_true")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args()

    if args.print_sql:
        print("=== 1. EVENTS_SQL (completed pre-Nov-6 games, zero held-out events) ===")
        print(EVENTS_SQL)
        print("\n=== 2. WIN_PROB_BATCH_SQL (200-event indexed LATERAL across all win_prob_snapshots sources) ===")
        print(WIN_PROB_BATCH_SQL)
        print("\n=== 3. ODDS_BATCH_SQL (200-event pre-cutoff bookmaker rows for producer median/floor replay) ===")
        print(ODDS_BATCH_SQL)
        return 0

    if args.self_test:
        asyncio.run(_run_self_test())
        return 0

    if not args.alex_approved or not args.fable_sql_read_go:
        parser.error(
            "--production requires BOTH --alex-approved AND --fable-sql-read-go "
            "(after Fable posts 'SQL read, go' on #12108)"
        )
    now_pt = datetime.now(_PT)
    if now_pt < _EARLIEST_PROD_PT:
        parser.error(
            f"Condition 4 forbids production run before 8:45 PM PT tonight "
            f"(current PT: {now_pt.isoformat()}, earliest: {_EARLIEST_PROD_PT.isoformat()})"
        )

    url = os.environ["DATABASE_URL"]
    obs = asyncio.run(read_pre_nov6_observations(url))
    if "records_by_horizon" not in obs or obs.get("wp_events_read", 0) == 0:
        out = {k: v for k, v in obs.items() if k != "records_by_horizon"}
        print(json.dumps(out, indent=2, default=str))
        return 1

    report = compute_analysis_report(obs)
    md = format_markdown_summary(report)
    if args.output_json:
        args.output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.output_md:
        args.output_md.write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
