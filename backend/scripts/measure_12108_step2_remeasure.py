"""Decision 448: A — Pre-Nov-6 Calibration Step 2 read-only re-measure (#12108).

Option B scoped re-measurement with all four of Fable's method-check additions:
  1. Frozen E1..E5b exclusion list applied cleanly at read time (zero DB writes).
  2. Pre-registered primary read rule: Bain Luck Blend vs PM Avg
     `(Kalshi + Polymarket) / 2`, Log Loss (Typical Miss / ECE secondary),
     at T-1h on Common Support (Panel B Clean vs Panel C Common-Support Raw);
     95% CI < 0 => helps, > 0 => hurts, includes 0 => cannot tell.
  3. Cross-source start-time fairness check in Table 0 (`score_observed_at`,
     `completed_at`, or non-backfilled in-play `game_state` before stored
     `commence_time`) plus fairness re-run excluding wrong-start games.
  4. Exact reproduction gate against `report_12108_411a.json` across every
     WinProb and Option-B-covered cell (`mismatches != 0` aborts before Panel B).

Strict hard bounds (inherited verbatim from 411: A):
  - Read-only Postgres session (`default_transaction_read_only = on` and per-txn
    `SET LOCAL transaction_read_only = on`), zero retries on statement timeout,
    1.0s inter-batch pause, `max_read_duration_s=3600`, `odds_max_single_batch_s=15`.
  - Strictly pre-Nov-6 ceiling (`commence_time < 2026-11-06T00:00:00Z`,
    `completed_at/score_observed_at/captured_at < 2026-11-06T00:00:00Z`).
  - Zero queries to `probability_publications`.
  - Write-up basis: blend arithmetic applied to stored readings, as 411: A was;
    not served reader history (whose record begins with Decide 44).
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import math
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.tasks.calibration_main_build import is_statement_timeout  # noqa: E402
from app.utils.aggregation import (  # noqa: E402
    compute_aggregate_probability_tiered,
)
from app.utils.publication_reader import HORIZONS  # noqa: E402
from scripts.evals.blend_replay_export import rebuild_betting  # noqa: E402

_PRE_NOV6_ISO = "2026-11-06T00:00:00Z"
_EVENTS_STMT_TIMEOUT_S = 120
_WP_STMT_TIMEOUT_S = 120
_WRONG_START_STMT_TIMEOUT_S = 120
_ESM_DETAIL_STMT_TIMEOUT_S = 120
_ODDS_STMT_TIMEOUT_S = 30
_INTER_BATCH_PAUSE_S = 1.0
_MAX_READ_DURATION_S = 3600.0
_ODDS_MAX_SINGLE_BATCH_S = 15.0
_ODDS_FIRST_N_AVG_COUNT = 0
_ODDS_FIRST_N_AVG_MAX_S = 3.0
_NON_PM_ODDS_SAMPLE_LIMIT = 4000
_BATCH_SIZE = 200
_WRONG_START_BATCH_SIZE = 500
_ODDS_BATCH_SIZE = 40
_SERIES_MAX_GAP = timedelta(days=4)
_LOG_LOSS_CLIP = 1e-15
_BOOTSTRAP_SEED = 12108
_BOOTSTRAP_REPLICATES = 1000
_DB_ROLE_NOTE = "primary postgresql-globular-51563 (Heroku Standard 3 — no follower attached)"

_E1_CUTOFF = datetime(2026, 9, 17, 0, 0, 0, tzinfo=timezone.utc)
_E2_CUTOFF = datetime(2026, 9, 20, 6, 0, 0, tzinfo=timezone.utc)
_E4_CUTOFF = datetime(2026, 9, 25, 16, 0, 0, tzinfo=timezone.utc)

ESM_RAW_SOURCES: tuple[str, ...] = ("espn", "stat_model", "mlb", "fangraphs")
ESM_KEY_SOURCES: tuple[str, ...] = ("espn", "stat_model", "mlb")
EXCLUSION_IDS: tuple[str, ...] = ("E1", "E2", "E3", "E4", "E5a", "E5b")

EXCLUSION_LABELS: dict[str, str] = {
    "E1": "E1 (#2486 ESPN /100 < 2026-09-17Z)",
    "E2": "E2 (#7338 ESPN inverted < 2026-09-20T06Z)",
    "E3": "E3 (#8514 ESPN estimated backfill)",
    "E4": "E4 (#8613 MLB +-1.5 stat_model < 2026-09-25T16Z)",
    "E5a": "E5a (#922/#13850 pre-start terminal clamp overwrite)",
    "E5b": "E5b (#13850 stat_model < commence_time)",
}

WRITING_BASIS_STATEMENT = (
    "This is the blend's arithmetic applied to stored readings, as 411: A was. "
    "It is not the number readers were served (that record begins with Decide 44)."
)

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
    (
        "All 4 core sources (Books + ESPN + Kalshi + Polymarket)",
        ("betting", "espn", "kalshi", "polymarket"),
    ),
    ("Books + Kalshi + Polymarket", ("betting", "kalshi", "polymarket")),
    ("Both Prediction Markets (Kalshi + Polymarket + PM Avg)", ("kalshi", "polymarket", "pm_avg")),
    ("Books + ESPN", ("betting", "espn")),
    ("Books + ESPN + Bain Luck Model", ("betting", "espn", "stat_model")),
    (
        "Baseball All 4 (Books + ESPN + Bain Luck Model + MLB Model)",
        ("betting", "espn", "stat_model", "mlb"),
    ),
)
CUTOFF_PAIRS: tuple[tuple[str, str], ...] = (
    ("start", "t_minus_1h"),
    ("start", "t_minus_6h"),
    ("start", "t_minus_24h"),
    ("t_minus_1h", "t_minus_6h"),
    ("t_minus_6h", "t_minus_24h"),
)
WP_ONLY_ARMS: tuple[str, ...] = ("kalshi", "polymarket", "pm_avg", "espn", "stat_model", "mlb")

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

ESM_DETAIL_SQL = f"""
SELECT w.id AS snap_id,
       w.event_id AS event_id,
       w.source AS source,
       w.captured_at AS captured_at,
       w.valid_until AS valid_until,
       w.home_win_probability AS home_win_probability,
       w.game_state AS game_state
  FROM win_prob_snapshots w
 WHERE w.event_id = ANY(CAST(:event_ids AS bigint[]))
   AND w.source = ANY(CAST(:sources AS text[]))
   AND w.captured_at < TIMESTAMPTZ '{_PRE_NOV6_ISO}'
   AND w.home_win_probability IS NOT NULL
   AND w.home_win_probability >= 0
   AND w.home_win_probability <= 1
 ORDER BY w.event_id, w.source, w.captured_at ASC, w.id ASC
""".strip()

WRONG_START_BATCH_SQL = f"""
SELECT b.event_id AS event_id,
       EXISTS (
           SELECT 1
             FROM win_prob_snapshots w
            WHERE w.event_id = b.event_id
              AND w.captured_at < b.start_at
              AND w.captured_at < TIMESTAMPTZ '{_PRE_NOV6_ISO}'
              AND w.game_state IS NOT NULL
              AND COALESCE(w.game_state->>'backfilled', '') <> 'true'
              AND (
                  LOWER(COALESCE(w.game_state->>'period', '')) NOT IN (
                      '', 'start', 'pre', 'pregame', 'scheduled', '0', 'tbd'
                  )
                  OR (
                      NULLIF(TRIM(COALESCE(w.game_state->>'inning', '')), '') IS NOT NULL
                      AND LOWER(TRIM(COALESCE(w.game_state->>'inning', ''))) <> '0'
                  )
                  OR (
                      (w.game_state->>'home_score') ~ '^[0-9]+$'
                      AND CAST(w.game_state->>'home_score' AS integer) > 0
                  )
                  OR (
                      (w.game_state->>'away_score') ~ '^[0-9]+$'
                      AND CAST(w.game_state->>'away_score' AS integer) > 0
                  )
              )
       ) AS has_prestart_inplay_wp
  FROM unnest(CAST(:event_ids AS bigint[]), CAST(:starts AS timestamptz[])) AS b(event_id, start_at)
""".strip()

ODDS_BATCH_SQL = f"""
WITH RECURSIVE target_events AS (
    SELECT e.id AS event_id,
           e.commence_time AS start_at
      FROM events e
     WHERE e.id = ANY(CAST(:event_ids AS bigint[]))
       AND e.commence_time < TIMESTAMPTZ '{_PRE_NOV6_ISO}'
       AND (e.completed_at IS NULL OR e.completed_at < TIMESTAMPTZ '{_PRE_NOV6_ISO}')
       AND (e.score_observed_at IS NULL OR e.score_observed_at < TIMESTAMPTZ '{_PRE_NOV6_ISO}')
),
event_books AS (
    SELECT te.event_id,
           te.start_at,
           (SELECT o.bookmaker
              FROM odds_snapshots o
             WHERE o.event_id = te.event_id
             ORDER BY o.bookmaker ASC
             LIMIT 1) AS bookmaker
      FROM target_events te
    UNION ALL
    SELECT eb.event_id,
           eb.start_at,
           (SELECT o.bookmaker
              FROM odds_snapshots o
             WHERE o.event_id = eb.event_id
               AND o.bookmaker > eb.bookmaker
             ORDER BY o.bookmaker ASC
             LIMIT 1) AS bookmaker
      FROM event_books eb
     WHERE eb.bookmaker IS NOT NULL
),
distinct_books AS (
    SELECT event_id, start_at, bookmaker
      FROM event_books
     WHERE bookmaker IS NOT NULL
)
SELECT db.event_id AS event_id,
       h.horizon AS horizon,
       snap.id AS snap_id,
       db.bookmaker AS bookmaker,
       snap.captured_at AS captured_at,
       snap.valid_until AS valid_until,
       snap.home_win_probability AS home_win_probability
  FROM distinct_books db
  CROSS JOIN (
      VALUES ('start', INTERVAL '0 seconds'),
             ('t_minus_1h', INTERVAL '1 hour'),
             ('t_minus_6h', INTERVAL '6 hours'),
             ('t_minus_24h', INTERVAL '24 hours')
  ) AS h(horizon, offset_iv)
  CROSS JOIN LATERAL (
      SELECT o.id, o.captured_at, o.valid_until, o.home_win_probability
        FROM odds_snapshots o
       WHERE o.event_id = db.event_id
         AND o.bookmaker = db.bookmaker
         AND o.captured_at <= db.start_at - h.offset_iv
         AND o.captured_at < TIMESTAMPTZ '{_PRE_NOV6_ISO}'
         AND o.home_win_probability IS NOT NULL
         AND o.home_win_probability > 0
         AND o.home_win_probability < 1
       ORDER BY o.captured_at DESC, o.id DESC
       LIMIT 1
  ) AS snap
 ORDER BY db.event_id, h.horizon, db.bookmaker
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


def classify_snapshot_exclusions(
    *,
    raw_source: str,
    league: str,
    captured_at: datetime,
    valid_until: datetime | None,
    prob: float,
    game_state: dict[str, Any] | None,
    commence_time: datetime,
    completed_at: datetime | None,
    max_captured_at_for_source: datetime | None,
) -> dict[str, bool]:
    """Evaluate exact frozen exclusions E1..E5b for one `win_prob_snapshots` row."""
    cap = _as_utc(captured_at)
    start = _as_utc(commence_time)
    vu = _as_utc(valid_until) if valid_until is not None else None
    gs = game_state if isinstance(game_state, dict) else {}

    e1 = raw_source == "espn" and cap < _E1_CUTOFF
    e2 = raw_source == "espn" and cap < _E2_CUTOFF
    e3 = (
        raw_source == "espn"
        and gs.get("backfilled") is True
        and ("seconds_left" in gs)
        and gs.get("time_basis") != "play_wallclock"
    )
    e4 = raw_source == "stat_model" and league == "baseball_mlb" and cap < _E4_CUTOFF

    is_clamped = prob <= 0.0011 or prob >= 0.9989
    held_past_start = vu is not None and vu > start
    is_latest_terminal = (
        completed_at is not None
        and max_captured_at_for_source is not None
        and cap == _as_utc(max_captured_at_for_source)
    )
    e5a = (
        raw_source in ("espn", "stat_model", "mlb")
        and cap <= start
        and is_clamped
        and (held_past_start or is_latest_terminal)
    )
    e5b = raw_source == "stat_model" and cap < start

    return {
        "E1": e1,
        "E2": e2,
        "E3": e3,
        "E4": e4,
        "E5a": e5a,
        "E5b": e5b,
    }


def classify_wrong_start(
    ev: dict[str, Any], *, has_prestart_inplay_wp: bool
) -> dict[str, bool]:
    """Identify whether an event's stored `commence_time` is later than first evidence of play."""
    start = _as_utc(ev["start"])
    score_before = ev.get("score_observed_at") is not None and (
        _as_utc(ev["score_observed_at"]) < start
    )
    completed_before = ev.get("completed_at") is not None and (
        _as_utc(ev["completed_at"]) < start
    )
    return {
        "score_observed_before_start": score_before,
        "completed_before_start": completed_before,
        "inplay_wp_before_start": bool(has_prestart_inplay_wp),
        "any_wrong_start": bool(score_before or completed_before or has_prestart_inplay_wp),
    }


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
    c_count = mat.shape[0]
    ll_reps = np.empty(replicates, dtype=np.float64)
    ece_reps = np.empty(replicates, dtype=np.float64)
    probs = np.full(c_count, 1.0 / c_count, dtype=np.float64)
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


def classify_verdict_from_ci(ci95: list[float] | None) -> str:
    """Pre-registered Addition 2 CI read rule on `Δ Log Loss = Blend − PM Avg`."""
    if not ci95 or len(ci95) != 2:
        return "cannot tell (insufficient clusters for 95% CI)"
    lo, hi = float(ci95[0]), float(ci95[1])
    if hi < 0.0:
        return "helps (adding non-PM sources reduces log loss; 95% CI < 0)"
    if lo > 0.0:
        return "hurts (adding non-PM sources increases log loss; 95% CI > 0)"
    return "cannot tell (95% CI includes 0)"


def _stratified_seed_order(
    events: list[dict[str, Any]], *, seed: int = _BOOTSTRAP_SEED
) -> list[dict[str, Any]]:
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


def _pick_key_source_snapshot(
    rows_by_src: dict[str, list[dict[str, Any]]],
    cutoff: datetime,
    *,
    apply_exclusions: bool,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Select latest raw or clean snapshots per key source (`espn`, `stat_model`, `mlb`)."""
    selected: dict[str, dict[str, Any]] = {}
    audit: dict[str, dict[str, Any]] = {}

    for raw_src in ("espn", "stat_model", "mlb"):
        eligible_raw = [
            r for r in rows_by_src.get(raw_src, []) if _as_utc(r["captured_at"]) <= cutoff
        ]
        raw_latest = eligible_raw[-1] if eligible_raw else None
        clean_candidates = [r for r in eligible_raw if not r["excluded"]]
        clean_latest = clean_candidates[-1] if clean_candidates else None

        if not apply_exclusions:
            if raw_latest is not None:
                selected[raw_src] = raw_latest
        else:
            if clean_latest is not None:
                selected[raw_src] = clean_latest
            if raw_latest is not None:
                raw_flags = raw_latest["flags"]
                audit[raw_src] = {
                    "raw_present": True,
                    "raw_excluded": bool(raw_latest["excluded"]),
                    "flags": dict(raw_flags),
                    "fell_back": bool(raw_latest["excluded"] and clean_latest is not None),
                    "dropped": bool(raw_latest["excluded"] and clean_latest is None),
                    "clean_present": bool(clean_latest is not None),
                }

    # Fangraphs fills `mlb` only when no `mlb` row exists (preserving `411: A` priority).
    fg_eligible = [
        r for r in rows_by_src.get("fangraphs", []) if _as_utc(r["captured_at"]) <= cutoff
    ]
    fg_latest = fg_eligible[-1] if fg_eligible else None
    if "mlb" not in selected and fg_latest is not None:
        if not apply_exclusions or not fg_latest["excluded"]:
            selected["mlb"] = fg_latest

    return selected, audit


async def read_step2_observations(
    db_url: str,
    *,
    batch_pause_s: float = _INTER_BATCH_PAUSE_S,
    wp_stmt_timeout_s: int = _WP_STMT_TIMEOUT_S,
    odds_stmt_timeout_s: int = _ODDS_STMT_TIMEOUT_S,
    max_read_duration_s: float = _MAX_READ_DURATION_S,
    odds_max_single_batch_s: float = _ODDS_MAX_SINGLE_BATCH_S,
    odds_first_n_avg_count: int = _ODDS_FIRST_N_AVG_COUNT,
    odds_first_n_avg_max_s: float = _ODDS_FIRST_N_AVG_MAX_S,
    non_pm_sample_limit: int = _NON_PM_ODDS_SAMPLE_LIMIT,
    db_role_note: str = _DB_ROLE_NOTE,
    force_stop_after_odds_batches: int | None = None,
) -> dict[str, Any]:
    """Read pre-Nov-6 observations under Option B (scoped ODDS_BATCH_SQL on `esm_eids`)."""
    started = time.monotonic()
    deadline = started + max_read_duration_s
    engine = create_async_engine(
        _async_db_url(db_url),
        connect_args={"server_settings": {"default_transaction_read_only": "on"}},
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    stopped_early = False
    stop_reason: str | None = None
    stop_stage: str | None = None

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
        event_by_eid = {int(ev["event_id"]): ev for ev in ordered_events}

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
        esm_eids: set[int] = set()

        # Wrong-start map across all 23,307 events.
        prestart_inplay_eids: set[int] = set()
        wrong_start_batches_done = 0
        wrong_start_batches_total = (
            math.ceil(len(ordered_events) / _WRONG_START_BATCH_SIZE) if ordered_events else 0
        )

        # Annotated ESM rows per event & raw_source, ordered by (captured_at, id) ASC.
        esm_rows_by_eid_src: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        esm_detail_batches_done = 0
        esm_detail_batches_total = 0

        odds_fetched_eids: set[int] = set()
        odds_by_eh: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
        odds_target_pm = 0
        odds_target_non_pm_pool = 0
        odds_target_non_pm_sample = 0
        odds_411a_eids: set[int] = set()
        odds_option_b_targets: list[dict[str, Any]] = []
        odds_batches_total = 0
        odds_batches_done = 0
        odds_batch_durations_s: list[float] = []

        async with Session() as s:
            wp_stmt = text(WIN_PROB_BATCH_SQL)
            wrong_start_stmt = text(WRONG_START_BATCH_SQL)
            esm_stmt = text(ESM_DETAIL_SQL)
            odds_stmt = text(ODDS_BATCH_SQL)

            # ── Phase 1: win_prob_snapshots across ALL pre-Nov-6 games (exact 411: A query) ──
            for b_idx in range(wp_batches_total):
                if time.monotonic() >= deadline:
                    stopped_early = True
                    stop_reason = f"max_read_duration_{int(max_read_duration_s)}s"
                    stop_stage = "win_prob_batch"
                    break
                if b_idx > 0 and batch_pause_s > 0:
                    await asyncio.sleep(batch_pause_s)

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
                    if src in ESM_RAW_SOURCES:
                        esm_eids.add(eid)
                    wp_by_eh[(eid, h_name)][key_src] = {
                        "prob": prob,
                        "captured_at": _as_utc(r["captured_at"]),
                        "valid_until": _as_utc(r["valid_until"]) if r["valid_until"] else None,
                    }

            # ── Phase 1b: Wrong-start evidence scan across ALL pre-Nov-6 games (Addition 3) ──
            if not stopped_early and wp_events_read:
                for b_idx in range(wrong_start_batches_total):
                    if time.monotonic() >= deadline:
                        stopped_early = True
                        stop_reason = f"max_read_duration_{int(max_read_duration_s)}s"
                        stop_stage = "wrong_start_batch"
                        break
                    if batch_pause_s > 0:
                        await asyncio.sleep(batch_pause_s)
                    batch = ordered_events[
                        b_idx * _WRONG_START_BATCH_SIZE : (b_idx + 1) * _WRONG_START_BATCH_SIZE
                    ]
                    ws_eids = [int(ev["event_id"]) for ev in batch]
                    ws_starts = [_as_utc(ev["start"]) for ev in batch]
                    await s.rollback()
                    await s.execute(text("SET LOCAL transaction_read_only = on"))
                    await s.execute(
                        text(f"SET LOCAL statement_timeout = '{_WRONG_START_STMT_TIMEOUT_S}s'")
                    )
                    try:
                        ws_res = await s.execute(
                            wrong_start_stmt, {"event_ids": ws_eids, "starts": ws_starts}
                        )
                        ws_rows = ws_res.mappings().all()
                        statements_executed += 1
                        await s.rollback()
                    except Exception as exc:  # noqa: BLE001
                        await s.rollback()
                        stopped_early = True
                        stop_reason = (
                            f"statement_timeout_{_WRONG_START_STMT_TIMEOUT_S}s"
                            if is_statement_timeout(exc)
                            else f"error:{type(exc).__name__}"
                        )
                        stop_stage = "wrong_start_batch"
                        break
                    wrong_start_batches_done += 1
                    for r in ws_rows:
                        if r["has_prestart_inplay_wp"]:
                            prestart_inplay_eids.add(int(r["event_id"]))

            # ── Phase 1c: Full ESM snapshot series + game_state for E1..E5b & fallback ──
            esm_sorted_eids = sorted(esm_eids)
            esm_detail_batches_total = (
                math.ceil(len(esm_sorted_eids) / _BATCH_SIZE) if esm_sorted_eids else 0
            )
            if not stopped_early and esm_sorted_eids:
                for b_idx in range(esm_detail_batches_total):
                    if time.monotonic() >= deadline:
                        stopped_early = True
                        stop_reason = f"max_read_duration_{int(max_read_duration_s)}s"
                        stop_stage = "esm_detail_batch"
                        break
                    if batch_pause_s > 0:
                        await asyncio.sleep(batch_pause_s)
                    batch_eids = esm_sorted_eids[b_idx * _BATCH_SIZE : (b_idx + 1) * _BATCH_SIZE]
                    await s.rollback()
                    await s.execute(text("SET LOCAL transaction_read_only = on"))
                    await s.execute(
                        text(f"SET LOCAL statement_timeout = '{_ESM_DETAIL_STMT_TIMEOUT_S}s'")
                    )
                    try:
                        det_res = await s.execute(
                            esm_stmt,
                            {"event_ids": batch_eids, "sources": list(ESM_RAW_SOURCES)},
                        )
                        det_rows = det_res.mappings().all()
                        statements_executed += 1
                        await s.rollback()
                    except Exception as exc:  # noqa: BLE001
                        await s.rollback()
                        stopped_early = True
                        stop_reason = (
                            f"statement_timeout_{_ESM_DETAIL_STMT_TIMEOUT_S}s"
                            if is_statement_timeout(exc)
                            else f"error:{type(exc).__name__}"
                        )
                        stop_stage = "esm_detail_batch"
                        break

                    esm_detail_batches_done += 1
                    temp_rows: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
                    for r in det_rows:
                        eid = int(r["event_id"])
                        raw_src = str(r["source"])
                        prob = _valid_prob(r["home_win_probability"])
                        if prob is None:
                            continue
                        temp_rows[(eid, raw_src)].append(
                            {
                                "snap_id": int(r["snap_id"]),
                                "raw_source": raw_src,
                                "captured_at": _as_utc(r["captured_at"]),
                                "valid_until": (
                                    _as_utc(r["valid_until"]) if r["valid_until"] else None
                                ),
                                "prob": prob,
                                "game_state": r["game_state"],
                            }
                        )
                    for (eid, raw_src), rlist in temp_rows.items():
                        rlist.sort(key=lambda x: (x["captured_at"], x["snap_id"]))
                        max_cap = rlist[-1]["captured_at"]
                        ev = event_by_eid[eid]
                        annotated: list[dict[str, Any]] = []
                        for item in rlist:
                            flags = classify_snapshot_exclusions(
                                raw_source=raw_src,
                                league=str(ev["league"]),
                                captured_at=item["captured_at"],
                                valid_until=item["valid_until"],
                                prob=item["prob"],
                                game_state=item["game_state"],
                                commence_time=ev["start"],
                                completed_at=ev.get("completed_at"),
                                max_captured_at_for_source=max_cap,
                            )
                            item_copy = dict(item)
                            item_copy["flags"] = flags
                            item_copy["excluded"] = any(flags.values())
                            annotated.append(item_copy)
                        esm_rows_by_eid_src[eid][raw_src] = annotated

            # ── Phase 2: Option B — ODDS_BATCH_SQL ONLY on `esm_eids` ──
            if not stopped_early and wp_events_read:
                pm_events = [ev for ev in wp_events_read if int(ev["event_id"]) in pm_eids]
                non_pm_pool = [ev for ev in wp_events_read if int(ev["event_id"]) not in pm_eids]
                non_pm_strat = _stratified_seed_order(non_pm_pool, seed=_BOOTSTRAP_SEED + 1)
                non_pm_sample = non_pm_strat[: min(non_pm_sample_limit, len(non_pm_strat))]
                pm_strat = _stratified_seed_order(pm_events, seed=_BOOTSTRAP_SEED + 2)
                odds_targets_411a = _interleave_odds_targets(pm_strat, non_pm_sample)
                odds_target_pm = len(pm_strat)
                odds_target_non_pm_pool = len(non_pm_pool)
                odds_target_non_pm_sample = len(non_pm_sample)
                odds_411a_eids = {int(ev["event_id"]) for ev in odds_targets_411a}

                esm_events = [ev for ev in wp_events_read if int(ev["event_id"]) in esm_eids]
                odds_option_b_targets = _stratified_seed_order(esm_events, seed=_BOOTSTRAP_SEED + 3)
                odds_batches_total = (
                    math.ceil(len(odds_option_b_targets) / _ODDS_BATCH_SIZE)
                    if odds_option_b_targets
                    else 0
                )

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

                    batch = odds_option_b_targets[
                        b_idx * _ODDS_BATCH_SIZE : (b_idx + 1) * _ODDS_BATCH_SIZE
                    ]
                    eids_param = [int(ev["event_id"]) for ev in batch]
                    await s.rollback()
                    await s.execute(text("SET LOCAL transaction_read_only = on"))
                    await s.execute(text(f"SET LOCAL statement_timeout = '{odds_stmt_timeout_s}s'"))
                    b_t0 = time.monotonic()
                    try:
                        odds_res = await s.execute(odds_stmt, {"event_ids": eids_param})
                        odds_rows = odds_res.mappings().all()
                        b_elapsed = time.monotonic() - b_t0
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
                    odds_batch_durations_s.append(round(b_elapsed, 3))
                    odds_fetched_eids.update(eids_param)
                    for r in odds_rows:
                        eid = int(r["event_id"])
                        h_name = str(r["horizon"])
                        odds_by_eh[(eid, h_name)].append(
                            {
                                "home_win_probability": float(r["home_win_probability"]),
                                "captured_at": _as_utc(r["captured_at"]),
                                "valid_until": (
                                    _as_utc(r["valid_until"]) if r["valid_until"] else None
                                ),
                            }
                        )

                    if b_elapsed > odds_max_single_batch_s:
                        stopped_early = True
                        stop_stage = "odds_batch"
                        stop_reason = (
                            f"odds_batch_over_{odds_max_single_batch_s:g}s "
                            f"({b_elapsed:.2f}s on batch {odds_batches_done})"
                        )
                        break

                    if (
                        odds_first_n_avg_count > 0
                        and len(odds_batch_durations_s) == odds_first_n_avg_count
                    ):
                        first_n_avg = sum(odds_batch_durations_s) / odds_first_n_avg_count
                        if first_n_avg > odds_first_n_avg_max_s:
                            stopped_early = True
                            stop_stage = "odds_batch"
                            stop_reason = (
                                f"odds_first_{odds_first_n_avg_count}_avg_over_"
                                f"{odds_first_n_avg_max_s:g}s ({first_n_avg:.2f}s)"
                            )
                            break

        wrong_start_by_eid: dict[int, dict[str, bool]] = {
            int(ev["event_id"]): classify_wrong_start(
                ev, has_prestart_inplay_wp=(int(ev["event_id"]) in prestart_inplay_eids)
            )
            for ev in wp_events_read
        }

        odds_batch_max_s = max(odds_batch_durations_s) if odds_batch_durations_s else None
        odds_batch_median_s = (
            round(float(np.median(odds_batch_durations_s)), 3)
            if odds_batch_durations_s
            else None
        )
        first_n_slice = odds_batch_durations_s[: min(5, len(odds_batch_durations_s))]
        odds_first_5_avg_s = (
            round(sum(first_n_slice) / len(first_n_slice), 3) if first_n_slice else None
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
            "odds_max_single_batch_s": odds_max_single_batch_s,
            "odds_first_n_avg_count": odds_first_n_avg_count,
            "odds_first_n_avg_max_s": odds_first_n_avg_max_s,
            "odds_batch_max_s": odds_batch_max_s,
            "odds_batch_median_s": odds_batch_median_s,
            "odds_first_5_avg_s": odds_first_5_avg_s,
            "events_total": len(ordered_events),
            "wp_events_read": len(wp_events_read),
            "wp_batches_done": wp_batches_done,
            "wp_batches_total": wp_batches_total,
            "wrong_start_batches_done": wrong_start_batches_done,
            "wrong_start_batches_total": wrong_start_batches_total,
            "esm_detail_batches_done": esm_detail_batches_done,
            "esm_detail_batches_total": esm_detail_batches_total,
            "esm_events_count": len(esm_eids),
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
            "wp_events": wp_events_read,
            "cluster_by_eid": cluster_by_eid,
            "cutoffs_by_eid": cutoffs_by_eid,
            "wp_by_eh": wp_by_eh,
            "esm_rows_by_eid_src": esm_rows_by_eid_src,
            "odds_fetched_eids": odds_fetched_eids,
            "odds_411a_eids": odds_411a_eids,
            "odds_by_eh": odds_by_eh,
            "wrong_start_by_eid": wrong_start_by_eid,
        }
    finally:
        await engine.dispose()


def _assemble_mode_records(
    obs: dict[str, Any],
    *,
    apply_exclusions: bool,
    restrict_odds_to_411a: bool,
    exclude_wrong_start: bool = False,
) -> tuple[dict[str, dict[int, dict[str, Any]]], dict[str, Any]]:
    """Build per-horizon records for Panel A (Raw), Panel B (Clean), or fairness subset."""
    wp_events: list[dict[str, Any]] = obs["wp_events"]
    cluster_by_eid: dict[int, str] = obs["cluster_by_eid"]
    cutoffs_by_eid: dict[int, list[tuple[str, datetime]]] = obs["cutoffs_by_eid"]
    wp_by_eh: dict[tuple[int, str], dict[str, dict[str, Any]]] = obs["wp_by_eh"]
    esm_rows_by_eid_src: dict[int, dict[str, list[dict[str, Any]]]] = obs["esm_rows_by_eid_src"]
    odds_fetched_eids: set[int] = obs["odds_fetched_eids"]
    odds_411a_eids: set[int] = obs["odds_411a_eids"]
    odds_by_eh: dict[tuple[int, str], list[dict[str, Any]]] = obs["odds_by_eh"]
    wrong_start_by_eid: dict[int, dict[str, bool]] = obs["wrong_start_by_eid"]

    records_by_horizon: dict[str, dict[int, dict[str, Any]]] = {
        h: {} for h in HORIZON_DISPLAY_ORDER
    }

    # Cutoff-level audit counters ( populated when apply_exclusions=True and exclude_wrong_start=False ).
    cutoff_audit: dict[str, dict[str, dict[str, int]]] = {
        h: {
            src: {
                "raw_games": 0,
                "clean_games": 0,
                "dropped_source": 0,
                "fell_back_to_clean": 0,
                "raw_excluded_total": 0,
                **{f"hit_{eid_k}": 0 for eid_k in EXCLUSION_IDS},
            }
            for src in ESM_KEY_SOURCES
        }
        for h in HORIZON_DISPLAY_ORDER
    }

    for ev in wp_events:
        eid = int(ev["event_id"])
        ws_info = wrong_start_by_eid.get(eid, {})
        is_wrong_start = bool(ws_info.get("any_wrong_start"))
        if exclude_wrong_start and is_wrong_start:
            continue

        y = 1 if int(ev["home_score"]) > int(ev["away_score"]) else 0
        sport_group = str(ev["sport_group"])
        league = str(ev["league"])
        cid = cluster_by_eid[eid]
        has_odds = eid in odds_fetched_eids and (
            not restrict_odds_to_411a or eid in odds_411a_eids
        )
        esm_src_rows = esm_rows_by_eid_src.get(eid)

        for h_name, cutoff in cutoffs_by_eid[eid]:
            sources_payload: dict[str, dict[str, Any]] = {}
            raw_probs: dict[str, float] = {}

            # Market sources (`kalshi`, `polymarket`) always come directly from Phase 1.
            for src, info in wp_by_eh.get((eid, h_name), {}).items():
                if not apply_exclusions or src not in ESM_KEY_SOURCES:
                    raw_probs[src] = info["prob"]
                    stamp = _effective_stamp(info["captured_at"], info["valid_until"], cutoff)
                    sources_payload[src] = {
                        "value": info["prob"],
                        "updated_at": stamp.isoformat(),
                    }

            if apply_exclusions and esm_src_rows is not None:
                clean_esm, audit_esm = _pick_key_source_snapshot(
                    esm_src_rows, cutoff, apply_exclusions=True
                )
                for src, info in clean_esm.items():
                    raw_probs[src] = info["prob"]
                    stamp = _effective_stamp(info["captured_at"], info["valid_until"], cutoff)
                    sources_payload[src] = {
                        "value": info["prob"],
                        "updated_at": stamp.isoformat(),
                    }
                for src, ainfo in audit_esm.items():
                    st_bucket = cutoff_audit[h_name][src]
                    if ainfo["raw_present"]:
                        st_bucket["raw_games"] += 1
                    if ainfo["clean_present"]:
                        st_bucket["clean_games"] += 1
                    if ainfo["raw_excluded"]:
                        st_bucket["raw_excluded_total"] += 1
                        for rule_id, fired in ainfo["flags"].items():
                            if fired:
                                st_bucket[f"hit_{rule_id}"] += 1
                    if ainfo["fell_back"]:
                        st_bucket["fell_back_to_clean"] += 1
                    if ainfo["dropped"]:
                        st_bucket["dropped_source"] += 1

            if has_odds:
                active_books: list[dict[str, Any]] = []
                active_stamps: list[datetime] = []
                for row_sel in odds_by_eh.get((eid, h_name), []):
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
                "wrong_start": is_wrong_start,
                "n_sources_blended": len(sources_payload) if blend_prob is not None else 0,
                "sources": raw_probs,
                "blend": blend_prob,
            }

    return records_by_horizon, cutoff_audit


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


def _compute_panel(records_by_h: dict[str, dict[int, dict[str, Any]]]) -> dict[str, Any]:
    sport_groups = sorted(
        {r["sport_group"] for h_map in records_by_h.values() for r in h_map.values()}
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

    cutoff_gaps: dict[str, Any] = {"overall": {}, "by_sport": {}}
    all_arms = ("blend",) + COMPARATORS

    def _pair_cutoffs(sg_filter: str | None) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for h_near, h_far in CUTOFF_PAIRS:
            pkey = f"{h_near} - {h_far}"
            near_map = records_by_h[h_near]
            far_map = records_by_h[h_far]
            shared_eids = sorted(set(near_map) & set(far_map))
            if sg_filter is not None:
                shared_eids = [
                    eid for eid in shared_eids if near_map[eid]["sport_group"] == sg_filter
                ]
            arm_gaps: dict[str, Any] = {}
            for arm in all_arms:
                rows_paired: list[tuple[str, float, float, int]] = []
                for eid in shared_eids:
                    rn, rf = near_map[eid], far_map[eid]
                    pn = rn["blend"] if arm == "blend" else rn["sources"].get(arm)
                    pf = rf["blend"] if arm == "blend" else rf["sources"].get(arm)
                    if pn is None or pf is None:
                        continue
                    rows_paired.append((rn["cluster_id"], pf, pn, rn["outcome"]))
                if rows_paired:
                    arm_gaps[arm] = score_paired_comparison(rows_paired)
            out[pkey] = arm_gaps

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

    return {"horizons": horizons_report, "cutoff_gaps": cutoff_gaps}


def _compute_common_support_panel_c(
    panel_a_records: dict[str, dict[int, dict[str, Any]]],
    panel_b_records: dict[str, dict[int, dict[str, Any]]],
) -> dict[str, Any]:
    """Restrict Raw Panel A records cleanly to exact `(horizon, event_id, comparator)` survivors of Panel B."""
    # For common-support pairwise/common comparisons: filter Panel A horizon maps to event_ids
    # present in Panel B with `blend is not None` and matching `pm_avg`/source support per comparator.
    horizons_c: dict[str, Any] = {}
    for h_name in HORIZON_DISPLAY_ORDER:
        rec_a = panel_a_records[h_name]
        rec_b = panel_b_records[h_name]

        def _build_restricted(multi_only: bool) -> dict[str, Any]:
            b_pool = {
                eid: r
                for eid, r in rec_b.items()
                if r["blend"] is not None and (not multi_only or r["n_sources_blended"] >= 2)
            }
            a_pool = {
                eid: r
                for eid, r in rec_a.items()
                if r["blend"] is not None and (not multi_only or r["n_sources_blended"] >= 2)
            }
            pairwise: dict[str, dict[str, Any]] = {}
            for comp in COMPARATORS:
                pairs = [
                    (
                        a_pool[eid]["cluster_id"],
                        a_pool[eid]["sources"][comp],
                        a_pool[eid]["blend"],
                        a_pool[eid]["outcome"],
                    )
                    for eid in sorted(set(b_pool) & set(a_pool))
                    if comp in b_pool[eid]["sources"] and comp in a_pool[eid]["sources"]
                ]
                pairwise[comp] = score_paired_comparison(pairs)

            common_sets: list[dict[str, Any]] = []
            for title, req_keys in COMMON_OVERLAP_SETS:
                shared_ids = [
                    eid
                    for eid in sorted(set(b_pool) & set(a_pool))
                    if all(k in b_pool[eid]["sources"] for k in req_keys)
                    and all(k in a_pool[eid]["sources"] for k in req_keys)
                ]
                if not shared_ids:
                    continue
                arms: dict[str, Any] = {
                    "blend": score_single_arm(
                        [
                            (a_pool[eid]["cluster_id"], a_pool[eid]["blend"], a_pool[eid]["outcome"])
                            for eid in shared_ids
                        ]
                    )
                }
                deltas_vs_blend: dict[str, Any] = {}
                for k in req_keys:
                    comp_res = score_paired_comparison(
                        [
                            (
                                a_pool[eid]["cluster_id"],
                                a_pool[eid]["sources"][k],
                                a_pool[eid]["blend"],
                                a_pool[eid]["outcome"],
                            )
                            for eid in shared_ids
                        ]
                    )
                    arms[k] = comp_res["a"]
                    deltas_vs_blend[k] = comp_res["delta_b_minus_a"]
                common_sets.append(
                    {
                        "title": title,
                        "keys": list(req_keys),
                        "n_games": len(shared_ids),
                        "n_clusters": len({a_pool[eid]["cluster_id"] for eid in shared_ids}),
                        "arms": arms,
                        "delta_blend_minus_comp": deltas_vs_blend,
                    }
                )
            return {"pairwise": pairwise, "common_sets": common_sets}

        horizons_c[h_name] = {
            "label": HORIZON_LABELS[h_name],
            "n_events": len(set(rec_a) & set(rec_b)),
            "overall": {
                "multi_source": _build_restricted(multi_only=True),
                "all_matched": _build_restricted(multi_only=False),
            },
        }
    return {"horizons": horizons_c}


def _compute_pm_avg_primary(
    records_raw: dict[str, dict[int, dict[str, Any]]],
    records_clean: dict[str, dict[int, dict[str, Any]]],
) -> dict[str, Any]:
    """Compute pre-registered Blend vs PM Avg comparison on Clean vs Common-Support Raw at every horizon."""
    by_h: dict[str, Any] = {}
    for h_name in HORIZON_DISPLAY_ORDER:
        rmap = records_raw[h_name]
        cmap = records_clean[h_name]
        shared_ids = sorted(
            eid
            for eid in (set(rmap) & set(cmap))
            if rmap[eid]["blend"] is not None
            and cmap[eid]["blend"] is not None
            and rmap[eid]["n_sources_blended"] >= 2
            and cmap[eid]["n_sources_blended"] >= 2
            and "pm_avg" in rmap[eid]["sources"]
            and "pm_avg" in cmap[eid]["sources"]
        )
        clean_res = score_paired_comparison(
            [
                (
                    cmap[eid]["cluster_id"],
                    cmap[eid]["sources"]["pm_avg"],
                    cmap[eid]["blend"],
                    cmap[eid]["outcome"],
                )
                for eid in shared_ids
            ]
        )
        raw_res = score_paired_comparison(
            [
                (
                    rmap[eid]["cluster_id"],
                    rmap[eid]["sources"]["pm_avg"],
                    rmap[eid]["blend"],
                    rmap[eid]["outcome"],
                )
                for eid in shared_ids
            ]
        )
        verdict = classify_verdict_from_ci(clean_res["delta_b_minus_a"]["log_loss_ci95"])
        by_h[h_name] = {
            "n_games": len(shared_ids),
            "n_clusters": clean_res["n_clusters"],
            "panel_b_clean": clean_res,
            "panel_c_common_raw": raw_res,
            "verdict": verdict,
        }
    return by_h


def _compute_table0(obs: dict[str, Any], cutoff_audit: dict[str, Any]) -> dict[str, Any]:
    """Build Table 0: Snapshot-level E1..E5b rejections, cutoff drops/fallbacks, and wrong-start counts."""
    snapshot_counts: dict[str, dict[str, int]] = {
        src: {"total_pre_nov6": 0, "excluded_any": 0, **{k: 0 for k in EXCLUSION_IDS}}
        for src in ESM_RAW_SOURCES
    }
    for eid, src_map in obs["esm_rows_by_eid_src"].items():
        for raw_src, rlist in src_map.items():
            sb = snapshot_counts[raw_src]
            for r in rlist:
                sb["total_pre_nov6"] += 1
                if r["excluded"]:
                    sb["excluded_any"] += 1
                for k in EXCLUSION_IDS:
                    if r["flags"][k]:
                        sb[k] += 1

    # Wrong-start counts across ALL 23,307 events, PM Avg at T-1h, and Option B esm cohort.
    ws_all = {
        "n_events": len(obs["wp_events"]),
        "wrong_start_any": 0,
        "score_observed_before_start": 0,
        "completed_before_start": 0,
        "inplay_wp_before_start": 0,
    }
    ws_esm = {
        "n_events": obs["esm_events_count"],
        "wrong_start_any": 0,
        "score_observed_before_start": 0,
        "completed_before_start": 0,
        "inplay_wp_before_start": 0,
    }
    ws_pm_t1h = {"n_events": 0, "wrong_start_any": 0}
    esm_set = {int(eid) for eid in obs["esm_rows_by_eid_src"]}
    for ev in obs["wp_events"]:
        eid = int(ev["event_id"])
        ws = obs["wrong_start_by_eid"][eid]
        if ws["any_wrong_start"]:
            ws_all["wrong_start_any"] += 1
        if ws["score_observed_before_start"]:
            ws_all["score_observed_before_start"] += 1
        if ws["completed_before_start"]:
            ws_all["completed_before_start"] += 1
        if ws["inplay_wp_before_start"]:
            ws_all["inplay_wp_before_start"] += 1
        if eid in esm_set:
            if ws["any_wrong_start"]:
                ws_esm["wrong_start_any"] += 1
            if ws["score_observed_before_start"]:
                ws_esm["score_observed_before_start"] += 1
            if ws["completed_before_start"]:
                ws_esm["completed_before_start"] += 1
            if ws["inplay_wp_before_start"]:
                ws_esm["inplay_wp_before_start"] += 1
        h_srcs = obs["wp_by_eh"].get((eid, "t_minus_1h"), {})
        if "kalshi" in h_srcs and "polymarket" in h_srcs:
            ws_pm_t1h["n_events"] += 1
            if ws["any_wrong_start"]:
                ws_pm_t1h["wrong_start_any"] += 1

    return {
        "snapshot_counts": snapshot_counts,
        "cutoff_audit": cutoff_audit,
        "wrong_start": {
            "all_pre_nov6": ws_all,
            "esm_cohort": ws_esm,
            "pm_avg_t_minus_1h_all_wp": ws_pm_t1h,
        },
    }


def _compare_values(path: str, got: Any, expected: Any, mismatches: list[dict[str, Any]]) -> None:
    if isinstance(expected, dict):
        if not isinstance(got, dict):
            mismatches.append({"path": path, "expected": type(expected).__name__, "got": repr(got)})
            return
        for k, ev in expected.items():
            _compare_values(f"{path}.{k}", got.get(k), ev, mismatches)
        return
    if isinstance(expected, list):
        if not isinstance(got, list) or len(got) != len(expected):
            mismatches.append({"path": path, "expected": expected, "got": got})
            return
        for idx, (gv, ev) in enumerate(zip(got, expected)):
            _compare_values(f"{path}[{idx}]", gv, ev, mismatches)
        return
    if got != expected:
        mismatches.append({"path": path, "expected": expected, "got": got})


def verify_baseline_411a(
    panel_a_report: dict[str, Any], meta: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, Any]:
    """Addition 4: Reproduce every WinProb and Option-B-covered 411: A metric & CI identically."""
    checked = 0
    mismatches: list[dict[str, Any]] = []

    base_meta = baseline.get("meta", {})
    for mk in (
        "events_total",
        "wp_events_read",
        "odds_target_pm",
        "odds_target_non_pm_pool",
        "odds_target_non_pm_sample",
        "clusters_read",
    ):
        checked += 1
        _compare_values(f"meta.{mk}", meta.get(mk), base_meta.get(mk), mismatches)

    # Check every ESM comparator pairwise cell + ESM-dependent common_sets across overall & by_sport.
    for h_name in HORIZON_DISPLAY_ORDER:
        base_h = baseline["horizons"][h_name]
        got_h = panel_a_report["horizons"][h_name]
        scopes = [("overall", got_h["overall"], base_h["overall"])]
        for sg in sorted(base_h.get("by_sport", {})):
            scopes.append(
                (f"by_sport.{sg}", got_h["by_sport"].get(sg, {}), base_h["by_sport"][sg])
            )
        for s_label, got_scope, base_scope in scopes:
            for pop in ("multi_source", "all_matched"):
                for comp in ESM_KEY_SOURCES:
                    checked += 1
                    _compare_values(
                        f"horizons.{h_name}.{s_label}.{pop}.pairwise.{comp}",
                        got_scope.get(pop, {}).get("pairwise", {}).get(comp),
                        base_scope[pop]["pairwise"][comp],
                        mismatches,
                    )
                base_cs_by_title = {cs["title"]: cs for cs in base_scope[pop].get("common_sets", [])}
                got_cs_by_title = {
                    cs["title"]: cs
                    for cs in got_scope.get(pop, {}).get("common_sets", [])
                }
                for title, bcs in base_cs_by_title.items():
                    if any(k in ESM_KEY_SOURCES for k in bcs.get("keys", [])):
                        checked += 1
                        _compare_values(
                            f"horizons.{h_name}.{s_label}.{pop}.common_sets[{title!r}]",
                            got_cs_by_title.get(title),
                            bcs,
                            mismatches,
                        )

    # Check all WinProb arms in cutoff_gaps (overall & by_sport across all 5 pairs + 4-cutoff set).
    gap_scopes = [
        ("overall", panel_a_report["cutoff_gaps"]["overall"], baseline["cutoff_gaps"]["overall"])
    ]
    for sg in sorted(baseline["cutoff_gaps"].get("by_sport", {})):
        gap_scopes.append(
            (
                f"by_sport.{sg}",
                panel_a_report["cutoff_gaps"]["by_sport"].get(sg, {}),
                baseline["cutoff_gaps"]["by_sport"][sg],
            )
        )
    for g_label, got_g, base_g in gap_scopes:
        for h_near, h_far in CUTOFF_PAIRS:
            pkey = f"{h_near} - {h_far}"
            b_pair = base_g.get(pkey, {})
            g_pair = got_g.get(pkey, {})
            for arm in WP_ONLY_ARMS:
                if arm in b_pair:
                    checked += 1
                    _compare_values(
                        f"cutoff_gaps.{g_label}.{pkey}.{arm}",
                        g_pair.get(arm),
                        b_pair[arm],
                        mismatches,
                    )
        b_four = base_g.get("four_cutoff_common_set", {})
        g_four = got_g.get("four_cutoff_common_set", {})
        for arm in WP_ONLY_ARMS:
            if arm in b_four:
                checked += 1
                _compare_values(
                    f"cutoff_gaps.{g_label}.four_cutoff_common_set.{arm}",
                    g_four.get(arm),
                    b_four[arm],
                    mismatches,
                )

    return {
        "checked_cells": checked,
        "mismatches": len(mismatches),
        "mismatch_details": mismatches[:50],
    }


def compute_step2_report(
    obs: dict[str, Any], *, baseline_411a: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Assemble Panel A (Raw), 411: A gate, Table 0, Panel B (Clean), Panel C, and Fairness re-run."""
    meta = {
        "database": obs["database"],
        "stopped_early": obs["stopped_early"],
        "stop_reason": obs["stop_reason"],
        "stop_stage": obs["stop_stage"],
        "ceiling": obs["ceiling"],
        "wp_statement_timeout_s": obs["wp_statement_timeout_s"],
        "odds_statement_timeout_s": obs["odds_statement_timeout_s"],
        "batch_pause_s": obs["batch_pause_s"],
        "max_read_duration_s": obs["max_read_duration_s"],
        "odds_max_single_batch_s": obs["odds_max_single_batch_s"],
        "odds_batch_max_s": obs["odds_batch_max_s"],
        "odds_batch_median_s": obs["odds_batch_median_s"],
        "odds_first_5_avg_s": obs["odds_first_5_avg_s"],
        "events_total": obs["events_total"],
        "wp_events_read": obs["wp_events_read"],
        "wp_batches_done": obs["wp_batches_done"],
        "wp_batches_total": obs["wp_batches_total"],
        "wrong_start_batches_done": obs["wrong_start_batches_done"],
        "wrong_start_batches_total": obs["wrong_start_batches_total"],
        "esm_detail_batches_done": obs["esm_detail_batches_done"],
        "esm_detail_batches_total": obs["esm_detail_batches_total"],
        "esm_events_count": obs["esm_events_count"],
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
        "scope": "Option B (all 23,307 WP/wrong-start events + ODDS_BATCH_SQL on esm_eids)",
        "target": "home_win (1 if home_score > away_score else 0; draws = 0)",
        "writing_basis": WRITING_BASIS_STATEMENT,
    }

    # Panel A masked to 411: A's ODDS_BATCH_SQL sample for exact baseline reproduction.
    rec_a_411, _ = _assemble_mode_records(
        obs, apply_exclusions=False, restrict_odds_to_411a=True, exclude_wrong_start=False
    )
    panel_a_411 = _compute_panel(rec_a_411)

    baseline_check: dict[str, Any] | None = None
    if baseline_411a is not None:
        baseline_check = verify_baseline_411a(panel_a_411, meta, baseline_411a)
        if baseline_check["mismatches"] != 0:
            return {
                "meta": meta,
                "aborted": True,
                "abort_reason": "411a_baseline_mismatch",
                "baseline_411a_check": baseline_check,
                "panel_a_411": panel_a_411,
            }

    # Full Option-B Raw & Clean across ALL esm_eids (not masked to 411: A's random non-PM cap).
    rec_raw_all, _ = _assemble_mode_records(
        obs, apply_exclusions=False, restrict_odds_to_411a=False, exclude_wrong_start=False
    )
    rec_clean_all, cutoff_audit = _assemble_mode_records(
        obs, apply_exclusions=True, restrict_odds_to_411a=False, exclude_wrong_start=False
    )
    table0 = _compute_table0(obs, cutoff_audit)
    panel_b_clean = _compute_panel(rec_clean_all)
    panel_c_common_raw = _compute_common_support_panel_c(rec_raw_all, rec_clean_all)
    primary_all = _compute_pm_avg_primary(rec_raw_all, rec_clean_all)

    # Fairness re-run excluding wrong-start games across all sources (Addition 3).
    rec_raw_fair, _ = _assemble_mode_records(
        obs, apply_exclusions=False, restrict_odds_to_411a=False, exclude_wrong_start=True
    )
    rec_clean_fair, _ = _assemble_mode_records(
        obs, apply_exclusions=True, restrict_odds_to_411a=False, exclude_wrong_start=True
    )
    panel_b_fair = _compute_panel(rec_clean_fair)
    panel_c_fair = _compute_common_support_panel_c(rec_raw_fair, rec_clean_fair)
    primary_fair = _compute_pm_avg_primary(rec_raw_fair, rec_clean_fair)

    # Standalone PM Avg across all 23,307 WP events with vs without wrong starts (no odds needed).
    pm_standalone: dict[str, Any] = {}
    for h_name in HORIZON_DISPLAY_ORDER:
        all_pm_rows = [
            (r["cluster_id"], r["sources"]["pm_avg"], r["outcome"])
            for r in rec_raw_all[h_name].values()
            if "pm_avg" in r["sources"]
        ]
        fair_pm_rows = [
            (r["cluster_id"], r["sources"]["pm_avg"], r["outcome"])
            for r in rec_raw_all[h_name].values()
            if "pm_avg" in r["sources"] and not r["wrong_start"]
        ]
        pm_standalone[h_name] = {
            "all_wp": score_single_arm(all_pm_rows),
            "excluding_wrong_start": score_single_arm(fair_pm_rows),
        }

    return {
        "meta": meta,
        "aborted": False,
        "baseline_411a_check": baseline_check,
        "table0": table0,
        "pre_registered_primary": {
            "definition": (
                "Bain Luck Blend vs PM Avg ((Kalshi + Polymarket)/2), Log Loss (primary) "
                "and Typical Miss/ECE (secondary), at T-1h on Common Support (Panel B Clean vs "
                "Panel C Raw on identical surviving multi-source esm_eids)"
            ),
            "all_surviving": primary_all,
            "excluding_wrong_start": primary_fair,
        },
        "pm_standalone_all_wp": pm_standalone,
        "panel_a_411": panel_a_411,
        "panel_a_option_b_raw": _compute_panel(rec_raw_all),
        "panel_b_clean": panel_b_clean,
        "panel_c_common_raw": panel_c_common_raw,
        "fairness_excluding_wrong_start": {
            "panel_b_clean": panel_b_fair,
            "panel_c_common_raw": panel_c_fair,
        },
        "_per_game_records": (rec_raw_all, rec_clean_all),
    }


def _fmt_val_ci(val: float | None, ci: list[float] | None, *, fmt: str, unit: str = "") -> str:
    if val is None:
        return "—"
    v_s = f"{val:{fmt}}{unit}"
    if ci is None:
        return v_s
    return f"{v_s} [{ci[0]:{fmt}}, {ci[1]:{fmt}}]"


def format_step2_markdown(report: dict[str, Any]) -> str:
    m = report["meta"]
    lines = [
        f"**Database Read:** `{m['database']}`",
        (
            f"**Coverage & Scope (`Option B`):** events=`{m['wp_events_read']}/{m['events_total']}` · "
            f"`esm_events={m['esm_events_count']}` · `odds_events_read={m['odds_events_read']}` · "
            f"`odds_batches={m['odds_batches_done']}/{m['odds_batches_total']}` · "
            f"`elapsed={m['elapsed_s']}s` · `ceiling < {m['ceiling']}`"
        ),
        f"**Writing Basis:** {m['writing_basis']}",
        "",
    ]

    bcheck = report.get("baseline_411a_check")
    if bcheck is not None:
        lines.append(
            f"### Addition 4 — `411: A` Reproduction Gate: "
            f"`checked_cells={bcheck['checked_cells']}`, `mismatches={bcheck['mismatches']}`"
        )
        if report.get("aborted"):
            lines.append("**ABORTED BEFORE PANEL B due to non-zero `411: A` mismatch:**")
            for mm in bcheck["mismatch_details"][:20]:
                lines.append(
                    f"- `{mm['path']}`: expected `{mm['expected']}` != got `{mm['got']}`"
                )
            return "\n".join(lines)
        lines.append("")

    t0 = report["table0"]
    ws_all = t0["wrong_start"]["all_pre_nov6"]
    ws_esm = t0["wrong_start"]["esm_cohort"]
    ws_pm = t0["wrong_start"]["pm_avg_t_minus_1h_all_wp"]
    lines.extend([
        "### Table 0 — Exclusions (`E1..E5b`) & Start-Time Fairness Counts",
        "",
        "| Raw Source | Pre-Nov-6 Snapshots | Excluded (Any) | E1 | E2 | E3 | E4 | E5a | E5b |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for src in ESM_RAW_SOURCES:
        srow = t0["snapshot_counts"][src]
        lines.append(
            f"| `{src}` | {srow['total_pre_nov6']} | {srow['excluded_any']} | "
            + " | ".join(str(srow[k]) for k in EXCLUSION_IDS)
            + " |"
        )

    lines.extend([
        "",
        "| Cutoff | Source | Raw Games | Excluded | Fell Back Clean | Dropped Source | Clean Games | E1 | E2 | E3 | E4 | E5a | E5b |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for h_name in HORIZON_DISPLAY_ORDER:
        for src in ESM_KEY_SOURCES:
            c = t0["cutoff_audit"][h_name][src]
            if c["raw_games"] == 0:
                continue
            lines.append(
                f"| `{h_name}` | `{src}` | {c['raw_games']} | {c['raw_excluded_total']} | "
                f"{c['fell_back_to_clean']} | {c['dropped_source']} | {c['clean_games']} | "
                + " | ".join(str(c[f"hit_{k}"]) for k in EXCLUSION_IDS)
                + " |"
            )

    lines.extend([
        "",
        "**Wrong Start-Time Fairness Check (`commence_time` later than first evidence of play):**",
        f"- **All pre-Nov-6 events (`n={ws_all['n_events']}`):** `{ws_all['wrong_start_any']}` total "
        f"(`score_observed_at < start`: `{ws_all['score_observed_before_start']}`, "
        f"`completed_at < start`: `{ws_all['completed_before_start']}`, "
        f"non-backfilled in-play `game_state < start`: `{ws_all['inplay_wp_before_start']}`)",
        f"- **Option B ESM cohort (`n={ws_esm['n_events']}`):** `{ws_esm['wrong_start_any']}` total "
        f"(`score`: `{ws_esm['score_observed_before_start']}`, `completed`: `{ws_esm['completed_before_start']}`, `inplay_wp`: `{ws_esm['inplay_wp_before_start']}`)",
        f"- **All-WP PM Avg at T-1h (`n={ws_pm['n_events']}`):** `{ws_pm['wrong_start_any']}` wrong-start games",
        "",
    ])

    prim = report["pre_registered_primary"]
    for label, sub in [
        ("Primary Read — Pre-registered (`T-1h`, Blend vs PM Avg, Common Support, All Surviving Games)", prim["all_surviving"]),
        ("Addition 3 Fairness Re-Run — Same Comparison Excluding Wrong-Start Games", prim["excluding_wrong_start"]),
    ]:
        lines.append(f"### {label}")
        t1 = sub["t_minus_1h"]
        b_row = t1["panel_b_clean"]
        c_row = t1["panel_c_common_raw"]
        bd = b_row["delta_b_minus_a"]
        cd = c_row["delta_b_minus_a"]
        lines.append(
            f"- **`T-1h` Verdict (`n={t1['n_games']}`, clusters=`{t1['n_clusters']}`):** **{t1['verdict']}**"
        )
        lines.append(
            f"  - Panel B (Clean Blend vs PM Avg): PM Avg LL `{_fmt_val_ci(b_row['a']['log_loss'], b_row['a']['log_loss_ci95'], fmt='.4f')}` vs "
            f"Clean Blend LL `{_fmt_val_ci(b_row['b']['log_loss'], b_row['b']['log_loss_ci95'], fmt='.4f')}`, "
            f"Δ LL `{_fmt_val_ci(bd['log_loss'], bd['log_loss_ci95'], fmt='+.4f')}` | "
            f"Δ Miss `{_fmt_val_ci(bd['ece_pp'], bd['ece_ci95'], fmt='+.2f', unit='pt')}`"
        )
        lines.append(
            f"  - Panel C (Common-Support Raw Blend vs PM Avg): Raw Blend LL `{_fmt_val_ci(c_row['b']['log_loss'], c_row['b']['log_loss_ci95'], fmt='.4f')}`, "
            f"Δ LL `{_fmt_val_ci(cd['log_loss'], cd['log_loss_ci95'], fmt='+.4f')}` | "
            f"Δ Miss `{_fmt_val_ci(cd['ece_pp'], cd['ece_ci95'], fmt='+.2f', unit='pt')}`"
        )
        lines.append("")
        lines.append("| Horizon (Secondary except T-1h) | Common N | Clusters | PM Avg LL | Panel C Raw Blend LL (Δ) | Panel B Clean Blend LL (Δ) | Verdict |")
        lines.append("|---|---:|---:|---|---|---|---|")
        for h_name in HORIZON_DISPLAY_ORDER:
            hr = sub[h_name]
            br = hr["panel_b_clean"]
            cr = hr["panel_c_common_raw"]
            lines.append(
                f"| `{h_name}` | {hr['n_games']} | {hr['n_clusters']} | "
                f"{_fmt_val_ci(br['a']['log_loss'], br['a']['log_loss_ci95'], fmt='.4f')} | "
                f"{_fmt_val_ci(cr['b']['log_loss'], cr['b']['log_loss_ci95'], fmt='.4f')} "
                f"(`{_fmt_val_ci(cr['delta_b_minus_a']['log_loss'], cr['delta_b_minus_a']['log_loss_ci95'], fmt='+.4f')}`) | "
                f"{_fmt_val_ci(br['b']['log_loss'], br['b']['log_loss_ci95'], fmt='.4f')} "
                f"(`{_fmt_val_ci(br['delta_b_minus_a']['log_loss'], br['delta_b_minus_a']['log_loss_ci95'], fmt='+.4f')}`) | "
                f"{hr['verdict']} |"
            )
        lines.append("")

    lines.extend([
        "### Option B Comparator Breakdown — Panel C (Common-Support Raw) vs Panel B (Clean E1..E5b), Multi-Source",
        "",
    ])
    for h_name in HORIZON_DISPLAY_ORDER:
        pb = report["panel_b_clean"]["horizons"][h_name]["overall"]["multi_source"]["pairwise"]
        pc = report["panel_c_common_raw"]["horizons"][h_name]["overall"]["multi_source"]["pairwise"]
        lines.append(f"#### {HORIZON_LABELS[h_name]}")
        lines.append(
            "| Comparator | Games | Clusters | Panel C Raw Comp LL -> Panel B Clean Comp LL | Panel C Raw Blend LL -> Panel B Clean Blend LL | Clean Δ Blend−Comp LL (95% CI) | Raw Comp Miss -> Clean Comp Miss |"
        )
        lines.append("|---|---:|---:|---|---|---|---|")
        for comp in COMPARATORS:
            brow = pb[comp]
            crow = pc[comp]
            if brow["n_games"] == 0:
                continue
            ba, bb, bd = brow["a"], brow["b"], brow["delta_b_minus_a"]
            ca, cb = crow["a"], crow["b"]
            lines.append(
                f"| {COMPARATOR_LABELS[comp]} | {brow['n_games']} | {brow['n_clusters']} | "
                f"{_fmt_val_ci(ca['log_loss'], ca['log_loss_ci95'], fmt='.4f')} -> "
                f"{_fmt_val_ci(ba['log_loss'], ba['log_loss_ci95'], fmt='.4f')} | "
                f"{_fmt_val_ci(cb['log_loss'], cb['log_loss_ci95'], fmt='.4f')} -> "
                f"{_fmt_val_ci(bb['log_loss'], bb['log_loss_ci95'], fmt='.4f')} | "
                f"{_fmt_val_ci(bd['log_loss'], bd['log_loss_ci95'], fmt='+.4f')} | "
                f"{_fmt_val_ci(ca['ece_pp'], ca['ece_ci95'], fmt='.2f', unit='pt')} -> "
                f"{_fmt_val_ci(ba['ece_pp'], ba['ece_ci95'], fmt='.2f', unit='pt')} |"
            )
        lines.append("")

    lines.append("### Standalone PM Avg Across All 23,307 WP Events (With vs Without Wrong-Start Games)")
    lines.append("| Horizon | All WP N | All WP PM Avg LL | Excl Wrong Start N | Clean Start PM Avg LL |")
    lines.append("|---|---:|---|---:|---|")
    for h_name in HORIZON_DISPLAY_ORDER:
        pmh = report["pm_standalone_all_wp"][h_name]
        a = pmh["all_wp"]
        f = pmh["excluding_wrong_start"]
        lines.append(
            f"| `{h_name}` | {a['n_games']} | {_fmt_val_ci(a['log_loss'], a['log_loss_ci95'], fmt='.4f')} | "
            f"{f['n_games']} | {_fmt_val_ci(f['log_loss'], f['log_loss_ci95'], fmt='.4f')} |"
        )
    return "\n".join(lines)


def write_per_game_jsonl_gz(
    path: Path,
    raw_records: dict[str, dict[int, dict[str, Any]]],
    clean_records: dict[str, dict[int, dict[str, Any]]],
) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for h_name in HORIZON_DISPLAY_ORDER:
            eids = sorted(set(raw_records[h_name]) | set(clean_records[h_name]))
            for eid in eids:
                r_raw = raw_records[h_name].get(eid)
                r_clean = clean_records[h_name].get(eid)
                ref = r_clean or r_raw
                row = {
                    "horizon": h_name,
                    "event_id": eid,
                    "cluster_id": ref["cluster_id"],
                    "sport_group": ref["sport_group"],
                    "league": ref["league"],
                    "outcome": ref["outcome"],
                    "wrong_start": ref["wrong_start"],
                    "odds_read": ref["odds_read"],
                    "raw_blend": r_raw["blend"] if r_raw else None,
                    "raw_sources": r_raw["sources"] if r_raw else {},
                    "clean_blend": r_clean["blend"] if r_clean else None,
                    "clean_sources": r_clean["sources"] if r_clean else {},
                }
                fh.write(json.dumps(row) + "\n")


async def _run_self_test() -> None:
    print("Self-test mode: run pytest backend/tests/test_measure_12108_step2_remeasure.py -v")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print-sql", action="store_true")
    mode.add_argument("--production", action="store_true")
    mode.add_argument("--self-test", action="store_true")
    parser.add_argument("--alex-approved-448a", action="store_true")
    parser.add_argument("--baseline-411a-json", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    parser.add_argument("--per-game-out", type=Path)
    parser.add_argument("--max-read-duration-s", type=float, default=_MAX_READ_DURATION_S)
    parser.add_argument("--odds-max-single-batch-s", type=float, default=_ODDS_MAX_SINGLE_BATCH_S)
    args = parser.parse_args()

    if args.print_sql:
        print("=== 1. EVENTS_SQL ===")
        print(EVENTS_SQL)
        print("\n=== 2. WIN_PROB_BATCH_SQL ===")
        print(WIN_PROB_BATCH_SQL)
        print("\n=== 3. WRONG_START_BATCH_SQL ===")
        print(WRONG_START_BATCH_SQL)
        print("\n=== 4. ESM_DETAIL_SQL ===")
        print(ESM_DETAIL_SQL)
        print("\n=== 5. ODDS_BATCH_SQL (Option B scoped on esm_eids) ===")
        print(ODDS_BATCH_SQL)
        return 0

    if args.self_test:
        asyncio.run(_run_self_test())
        return 0

    if not args.alex_approved_448a:
        parser.error("--production requires --alex-approved-448a (Decision 448: A)")

    baseline_411a = None
    if args.baseline_411a_json:
        baseline_411a = json.loads(args.baseline_411a_json.read_text(encoding="utf-8"))

    url = os.environ["DATABASE_URL"]
    obs = asyncio.run(
        read_step2_observations(
            url,
            max_read_duration_s=args.max_read_duration_s,
            odds_max_single_batch_s=args.odds_max_single_batch_s,
        )
    )
    if "wp_events" not in obs or obs.get("wp_events_read", 0) == 0:
        out = {
            k: v
            for k, v in obs.items()
            if k not in ("wp_events", "wp_by_eh", "esm_rows_by_eid_src", "odds_by_eh")
        }
        print(json.dumps(out, indent=2, default=str))
        return 1

    report = compute_step2_report(obs, baseline_411a=baseline_411a)
    per_game = report.pop("_per_game_records", None)
    md = format_step2_markdown(report)

    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.md_out:
        args.md_out.write_text(md, encoding="utf-8")
    if args.per_game_out and per_game is not None and not report.get("aborted"):
        raw_rec, clean_rec = per_game
        write_per_game_jsonl_gz(args.per_game_out, raw_rec, clean_rec)

    print(md)
    return 2 if report.get("aborted") else 0


if __name__ == "__main__":
    raise SystemExit(main())
