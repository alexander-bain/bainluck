#!/usr/bin/env python3
"""#13036 (Ruling 269: A) — repair upcoming ``(W)`` women's college basketball rows.

WHAT A READER SEES TODAY
------------------------
Before #13037 shipped, auto-created Polymarket/Kalshi women's college basketball
event rows stored the AWAY team in ``home_team_name`` with a trailing ``(W)``
marker and frequently landed under ``basketball_other`` instead of
``basketball_wncaab``. Every probability stored on those rows is home-oriented,
so a standalone row has both its sides and its stored home chance reversed, and
a row that duplicates an existing clean ``basketball_wncaab`` schedule row splits
its prediction markets away from the canonical game card.

RULING 269: A SCOPE (upcoming ``scheduled`` rows only)
------------------------------------------------------
Only currently upcoming (``status = 'scheduled'``) ``(W)``-tagged rows in
``basketball_other`` or ``basketball_wncaab`` with no ``espn_id``, no score, and
no ``completed_at`` are touched. Past-tipoff ``suspended`` rows and prior-season
``closed`` rows stay untouched.

Each upcoming row lands in one of two buckets:

1. **Has a clean ``basketball_wncaab`` twin** (``action = "move_to_twin"``):
   - Move linked ``futures_markets.event_id`` onto the clean twin (compare-and-set
     per market; outcome counts verified unchanged).
   - Move linked ``event_provider_anchors.event_id`` onto the clean twin so
     future polls resolve directly to the canonical row.
   - Retire the ``(W)`` row reversibly: ``status = 'voided'`` and append
     ``provenance:duplicate-of:<twin_id>`` to ``event_tags``. Nothing is deleted.

2. **Stands alone** (``action = "repair_standalone"``):
   - Strip trailing ``(W)`` from team names and normalized names.
   - Move ``sport_id`` to ``basketball_wncaab``.
   - Swap ``home_team_name`` / ``away_team_name``, normalized names, alt names,
     and team IDs.
   - Transpose home-perspective opening fields (if present), flip every numeric
     source probability in ``win_probability_sources`` (``1 - p``), and swap
     ``win_prob_snapshots.home_win_probability`` / ``away_win_probability``.
   - After commit, run the settle stage (adapted from #7739) against the live
     writer's own ``compute_source_home_probability`` so any in-flight refresh
     that overwrote a row back to ``1 - expected`` is re-stamped and verified.

SAFETY, DRIFT GUARD, AND ONE-COMMAND ROLLBACK (D51(b) / Ruling 47(c) / 269: A)
------------------------------------------------------------------------------
- Dry run is the DEFAULT and runs inside ``SET TRANSACTION READ ONLY`` — nothing
  can be written.
- Dry run prints the exact split, 10 before/after examples of each bucket, a
  deterministic ``plan_sha256``, the four backup tables where pre-write values
  are saved, and the exact single-command rollback.
- ``--apply`` requires ``--backup``, ``--expect-plan-sha256 <hash>``, and
  ``HEROKU_APP_NAME == 'bainluck'``. If ANY candidate row, twin target, market
  link, anchor link, or refusal differs from the dry run, ``--apply`` prints the
  diff and stops with exit code 2 without writing a byte.
- All backup inserts and updates execute inside ONE atomic database transaction.
  Any compare-and-set rowcount mismatch aborts and rolls back the entire run.
- One-command rollback:

      heroku run:detached -a bainluck -- \\
          python3 scripts/repair_wbb_upcoming_orientation_13036.py --rollback <run_id>
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.services.anchor_channel import (  # noqa: E402
    DUPLICATE_TAG_PREFIX,
    duplicate_tag,
)
from app.tasks.prediction_market_matching import (  # noqa: E402
    matchup_names_one_competitor,
    strip_womens_suffix,
)
from app.utils.agent_origin import curl_args  # noqa: E402

PRODUCER_APP = "bainluck"
TARGET_SPORT_KEY = "basketball_wncaab"
SOURCE_SPORT_KEYS = ("basketball_other", "basketball_wncaab")
TWIN_WINDOW_HOURS = 36
ESPN_WINDOW_HOURS = 12
ESPN_WBB_PATH = "basketball/womens-college-basketball"
SETTLE_EPSILON = 5e-4

BACKUP_EVENTS_TABLE = "bak_13036_wbb_events"
BACKUP_MARKETS_TABLE = "bak_13036_wbb_markets"
BACKUP_ANCHORS_TABLE = "bak_13036_wbb_anchors"
BACKUP_SNAPSHOTS_TABLE = "bak_13036_wbb_snapshots"

CANDIDATE_SQL = """
SELECT e.id,
       e.sport_id,
       s.key AS sport_key,
       e.home_team_name,
       e.away_team_name,
       e.home_team_normalized,
       e.away_team_normalized,
       e.home_team_alt_names,
       e.away_team_alt_names,
       e.home_team_id,
       e.away_team_id,
       e.commence_time,
       e.status,
       e.espn_id,
       e.external_id,
       e.home_score,
       e.away_score,
       e.completed_at,
       e.opening_home_probability,
       e.opening_away_probability,
       e.opening_home_spread,
       e.opening_favorite,
       e.closing_home_probability,
       e.closing_away_probability,
       e.closing_home_spread,
       e.espn_win_prob_home,
       e.win_probability_sources,
       e.event_tags
FROM events e
JOIN sports s ON s.id = e.sport_id
WHERE s.key = ANY(:sport_keys)
  AND e.status = 'scheduled'
  AND (e.home_team_name ~ '\\(W\\)\\s*$' OR e.away_team_name ~ '\\(W\\)\\s*$')
ORDER BY e.commence_time ASC, e.id ASC
"""

CLEAN_TWINS_SQL = """
SELECT e.id,
       e.home_team_name,
       e.away_team_name,
       e.commence_time,
       e.status,
       e.espn_id,
       e.external_id,
       e.event_tags
FROM events e
JOIN sports s ON s.id = e.sport_id
WHERE s.key = :target_sport_key
  AND e.status IN ('scheduled', 'live')
  AND e.home_team_name !~ '\\(W\\)\\s*$'
  AND e.away_team_name !~ '\\(W\\)\\s*$'
  AND e.commence_time >= :window_start
  AND e.commence_time <= :window_end
ORDER BY e.commence_time ASC, e.id ASC
"""

MARKETS_FOR_EVENTS_SQL = """
SELECT fm.id AS market_id,
       fm.event_id,
       fm.source,
       fm.external_id,
       fm.name,
       (SELECT count(*) FROM futures_outcomes fo WHERE fo.market_id = fm.id) AS outcome_count
FROM futures_markets fm
WHERE fm.event_id = ANY(:ids)
ORDER BY fm.event_id ASC, fm.id ASC
"""

ANCHORS_FOR_EVENTS_SQL = """
SELECT id AS anchor_id, event_id, source, source_id, id_kind
FROM event_provider_anchors
WHERE event_id = ANY(:ids)
ORDER BY event_id ASC, id ASC
"""

CHILD_COUNTS_SQL = """
SELECT e.id,
       (SELECT count(*) FROM odds_snapshots o WHERE o.event_id = e.id) AS odds_snapshots,
       (SELECT count(*) FROM espn_snapshots es WHERE es.event_id = e.id) AS espn_snapshots,
       (SELECT count(*) FROM score_snapshots sc WHERE sc.event_id = e.id) AS score_snapshots,
       (SELECT count(*) FROM win_prob_snapshots wp WHERE wp.event_id = e.id) AS win_prob_snapshots
FROM events e
WHERE e.id = ANY(:ids)
"""

REMAINING_UPCOMING_W_SQL = """
SELECT count(*) AS cnt
FROM events e
JOIN sports s ON s.id = e.sport_id
WHERE s.key = ANY(:sport_keys)
  AND e.status = 'scheduled'
  AND (e.home_team_name ~ '\\(W\\)\\s*$' OR e.away_team_name ~ '\\(W\\)\\s*$')
"""

VERIFY_REPAIRED_SQL = """
SELECT e.id,
       s.key AS sport_key,
       e.home_team_name,
       e.away_team_name,
       e.commence_time,
       e.status,
       e.win_probability_sources
FROM events e
JOIN sports s ON s.id = e.sport_id
WHERE e.id = ANY(:ids)
ORDER BY e.commence_time ASC, e.id ASC
"""

STORED_POLY_SQL = """
SELECT id, (win_probability_sources -> 'polymarket' ->> 'value')::float AS value
FROM events
WHERE id = ANY(:ids)
"""

RESTAMP_POLY_SQL = """
UPDATE events
SET win_probability_sources = jsonb_set(
    win_probability_sources,
    '{polymarket,value}',
    to_jsonb(round(cast(:value AS numeric), 4))
)
WHERE id = :event_id
  AND win_probability_sources -> 'polymarket' ? 'value'
"""

RESTAMP_SNAPSHOTS_SQL = """
UPDATE win_prob_snapshots
SET home_win_probability = away_win_probability,
    away_win_probability = home_win_probability
WHERE event_id = :event_id
  AND captured_at >= :since
  AND home_win_probability IS NOT NULL
  AND away_win_probability IS NOT NULL
  AND abs(home_win_probability - (1 - cast(:expected AS numeric))) <= cast(:eps AS numeric)
"""


@dataclass(frozen=True)
class TwinMoveItem:
    event_id: int
    commence_time: datetime
    old_sport_key: str
    old_home: str
    old_away: str
    old_status: str
    twin_id: int
    twin_home: str
    twin_away: str
    twin_espn_id: Optional[str]
    twin_orientation: str  # "swapped" | "same"
    market_ids: tuple[int, ...]
    market_outcome_counts: tuple[tuple[int, int], ...]
    anchor_ids: tuple[int, ...]


@dataclass(frozen=True)
class StandaloneRepairItem:
    event_id: int
    commence_time: datetime
    old_sport_key: str
    old_home: str
    old_away: str
    new_home: str
    new_away: str
    old_home_norm: Optional[str]
    old_away_norm: Optional[str]
    new_home_norm: Optional[str]
    new_away_norm: Optional[str]
    old_status: str
    old_wps: Optional[dict[str, Any]]
    new_wps: Optional[dict[str, Any]]
    win_prob_snapshot_count: int
    has_opening_fields: bool
    espn_check: str = "unchecked"
    espn_id: Optional[str] = None
    espn_home: Optional[str] = None
    espn_away: Optional[str] = None


@dataclass
class RepairPlan:
    twin_moves: list[TwinMoveItem] = field(default_factory=list)
    standalone_repairs: list[StandaloneRepairItem] = field(default_factory=list)
    refusals: list[dict[str, Any]] = field(default_factory=list)
    internal_w_duplicate_pairs: list[tuple[int, int]] = field(default_factory=list)

    @property
    def total_candidates(self) -> int:
        return len(self.twin_moves) + len(self.standalone_repairs) + len(self.refusals)


def _has_duplicate_tag(tags: Any) -> bool:
    if not isinstance(tags, list):
        return False
    return any(isinstance(t, str) and t.startswith(DUPLICATE_TAG_PREFIX) for t in tags)


def _strip_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned, _ = strip_womens_suffix(value)
    return cleaned


def _to_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    return None


def flip_probability(value: float) -> float:
    flipped = round(1.0 - float(value), 4)
    if flipped < 0.0:
        return 0.0
    if flipped > 1.0:
        return 1.0
    return flipped


def flip_win_probability_sources(raw: Any) -> Any:
    """Invert every numeric home-perspective probability in ``win_probability_sources``.

    Handles both shapes stored in production (dict entries carrying numeric
    ``value``, and legacy bare floats) while preserving timestamps, eligibility
    metadata, and non-numeric keys verbatim.
    """
    if not isinstance(raw, dict):
        return raw
    out: dict[str, Any] = {}
    for key, entry in raw.items():
        if isinstance(entry, dict):
            copied = dict(entry)
            val = _to_float(copied.get("value"))
            if val is not None:
                copied["value"] = flip_probability(val)
            out[key] = copied
        else:
            val = _to_float(entry)
            out[key] = flip_probability(val) if val is not None else entry
    return out


def flip_opening_favorite(fav: Optional[str]) -> Optional[str]:
    if fav == "home":
        return "away"
    if fav == "away":
        return "home"
    return fav


def append_duplicate_tag(existing_tags: Any, canonical_id: int) -> list[str]:
    tags = [t for t in existing_tags if isinstance(t, str)] if isinstance(existing_tags, list) else []
    tag = duplicate_tag(canonical_id)
    if tag not in tags:
        tags.append(tag)
    return tags


def unhandled_standalone_reasons(row: dict[str, Any], counts: dict[str, int]) -> list[str]:
    reasons: list[str] = []
    if row.get("espn_id") is not None:
        reasons.append("espn_id")
    if row.get("home_score") is not None or row.get("away_score") is not None:
        reasons.append("score")
    if row.get("completed_at") is not None:
        reasons.append("completed_at")
    if (
        row.get("closing_home_probability") is not None
        or row.get("closing_away_probability") is not None
        or row.get("closing_home_spread") is not None
    ):
        reasons.append("closing-line")
    if row.get("espn_win_prob_home") is not None:
        reasons.append("espn-win-prob")
    if counts.get("odds_snapshots", 0) > 0:
        reasons.append(f"{counts['odds_snapshots']} odds_snapshots")
    if counts.get("espn_snapshots", 0) > 0:
        reasons.append(f"{counts['espn_snapshots']} espn_snapshots")
    if counts.get("score_snapshots", 0) > 0:
        reasons.append(f"{counts['score_snapshots']} score_snapshots")
    return reasons


def has_opening_fields(row: dict[str, Any]) -> bool:
    return any(
        row.get(col) is not None
        for col in (
            "opening_home_probability",
            "opening_away_probability",
            "opening_home_spread",
            "opening_favorite",
        )
    )


def find_clean_twin(
    candidate: dict[str, Any],
    clean_twins: list[dict[str, Any]],
    *,
    window_hours: int = TWIN_WINDOW_HOURS,
) -> tuple[Optional[dict[str, Any]], Optional[str], Optional[str]]:
    """Return ``(twin_row, orientation, refusal_reason)``.

    Matches stripped candidate team names against clean ``basketball_wncaab``
    rows within ``±window_hours``. Prefers ESPN-anchored clean rows when
    multiple clean rows exist; refuses as ``AMBIGUOUS_TWIN`` if tied.
    """
    cand_home, _ = strip_womens_suffix(candidate["home_team_name"])
    cand_away, _ = strip_womens_suffix(candidate["away_team_name"])
    cand_time: datetime = candidate["commence_time"]
    window = timedelta(hours=window_hours)

    matches: list[tuple[dict[str, Any], str]] = []
    for twin in clean_twins:
        if twin["id"] == candidate["id"]:
            continue
        if _has_duplicate_tag(twin.get("event_tags")):
            continue
        if abs(twin["commence_time"] - cand_time) > window:
            continue
        same_order = matchup_names_one_competitor(
            cand_home, twin["home_team_name"]
        ) and matchup_names_one_competitor(cand_away, twin["away_team_name"])
        swapped_order = matchup_names_one_competitor(
            cand_home, twin["away_team_name"]
        ) and matchup_names_one_competitor(cand_away, twin["home_team_name"])
        if swapped_order and not same_order:
            matches.append((twin, "swapped"))
        elif same_order and not swapped_order:
            matches.append((twin, "same"))
        elif same_order and swapped_order:
            matches.append((twin, "swapped"))

    if not matches:
        return None, None, None
    if len(matches) == 1:
        return matches[0][0], matches[0][1], None

    espn_matches = [m for m in matches if m[0].get("espn_id")]
    if len(espn_matches) == 1:
        return espn_matches[0][0], espn_matches[0][1], None

    ext_matches = [m for m in matches if m[0].get("external_id")]
    if len(ext_matches) == 1:
        return ext_matches[0][0], ext_matches[0][1], None

    ids = [m[0]["id"] for m in matches]
    return None, None, f"AMBIGUOUS_TWIN ({ids})"


def match_espn_fixture(
    home_before: str,
    away_before: str,
    commence_time: datetime,
    fixtures: list[dict[str, Any]],
    *,
    window_hours: int = ESPN_WINDOW_HOURS,
) -> tuple[str, Optional[dict[str, Any]]]:
    """Compare a pre-repair ``(W)`` row's sides against ESPN's WBB scoreboard."""
    clean_home, _ = strip_womens_suffix(home_before)
    clean_away, _ = strip_womens_suffix(away_before)
    window = timedelta(hours=window_hours)

    hits: list[dict[str, Any]] = []
    for fx in fixtures:
        if abs(fx["kickoff"] - commence_time) > window:
            continue
        straight = matchup_names_one_competitor(
            clean_home, fx["home"]
        ) and matchup_names_one_competitor(clean_away, fx["away"])
        flipped = matchup_names_one_competitor(
            clean_home, fx["away"]
        ) and matchup_names_one_competitor(clean_away, fx["home"])
        if straight or flipped:
            hits.append(fx)

    if not hits:
        return "no_espn_fixture", None
    if len(hits) > 1:
        return "espn_ambiguous", None
    hit = hits[0]
    if hit.get("neutral"):
        return "espn_neutral", hit
    is_reversed = matchup_names_one_competitor(
        clean_home, hit["away"]
    ) and matchup_names_one_competitor(clean_away, hit["home"])
    if is_reversed:
        return "confirmed_reversed", hit
    return "espn_already_aligned", hit


def build_plan(
    candidates: list[dict[str, Any]],
    clean_twins: list[dict[str, Any]],
    markets_by_event: dict[int, list[dict[str, Any]]],
    anchors_by_event: dict[int, list[dict[str, Any]]],
    child_counts_by_event: dict[int, dict[str, int]],
    espn_fixtures: Optional[list[dict[str, Any]]] = None,
) -> RepairPlan:
    """Deterministically partition upcoming ``(W)`` rows into twin moves, standalone repairs, and refusals."""
    plan = RepairPlan()

    for row in candidates:
        eid = int(row["id"])
        counts = child_counts_by_event.get(eid, {})
        if row.get("espn_id") is not None or row.get("home_score") is not None or row.get("away_score") is not None or row.get("completed_at") is not None:
            plan.refusals.append({
                "event_id": eid,
                "reason": "has_espn_or_score_or_completed",
                "home": row["home_team_name"],
                "away": row["away_team_name"],
            })
            continue
        if _has_duplicate_tag(row.get("event_tags")):
            plan.refusals.append({
                "event_id": eid,
                "reason": "already_tagged_duplicate",
                "home": row["home_team_name"],
                "away": row["away_team_name"],
            })
            continue

        twin, orientation, twin_err = find_clean_twin(row, clean_twins)
        if twin_err is not None:
            plan.refusals.append({
                "event_id": eid,
                "reason": twin_err,
                "home": row["home_team_name"],
                "away": row["away_team_name"],
            })
            continue

        if twin is not None and orientation is not None:
            mkts = sorted(markets_by_event.get(eid, []), key=lambda m: int(m["market_id"]))
            ancs = sorted(anchors_by_event.get(eid, []), key=lambda a: int(a["anchor_id"]))
            plan.twin_moves.append(
                TwinMoveItem(
                    event_id=eid,
                    commence_time=row["commence_time"],
                    old_sport_key=row["sport_key"],
                    old_home=row["home_team_name"],
                    old_away=row["away_team_name"],
                    old_status=row["status"],
                    twin_id=int(twin["id"]),
                    twin_home=twin["home_team_name"],
                    twin_away=twin["away_team_name"],
                    twin_espn_id=twin.get("espn_id"),
                    twin_orientation=orientation,
                    market_ids=tuple(int(m["market_id"]) for m in mkts),
                    market_outcome_counts=tuple(
                        (int(m["market_id"]), int(m["outcome_count"])) for m in mkts
                    ),
                    anchor_ids=tuple(int(a["anchor_id"]) for a in ancs),
                )
            )
            continue

        reasons = unhandled_standalone_reasons(row, counts)
        if reasons:
            plan.refusals.append({
                "event_id": eid,
                "reason": "unhandled_standalone_fields: " + ", ".join(reasons),
                "home": row["home_team_name"],
                "away": row["away_team_name"],
            })
            continue

        espn_status = "unchecked"
        espn_id = None
        espn_home = None
        espn_away = None
        if espn_fixtures is not None:
            espn_status, hit = match_espn_fixture(
                row["home_team_name"],
                row["away_team_name"],
                row["commence_time"],
                espn_fixtures,
            )
            if hit is not None:
                espn_id = hit.get("espn_id")
                espn_home = hit.get("home")
                espn_away = hit.get("away")
            if espn_status == "espn_already_aligned":
                plan.refusals.append({
                    "event_id": eid,
                    "reason": (
                        f"espn_already_aligned (espn {espn_id}: "
                        f"home={espn_home}, away={espn_away})"
                    ),
                    "home": row["home_team_name"],
                    "away": row["away_team_name"],
                })
                continue

        new_home, _ = strip_womens_suffix(row["away_team_name"])
        new_away, _ = strip_womens_suffix(row["home_team_name"])
        new_home_norm = _strip_optional(row.get("away_team_normalized"))
        new_away_norm = _strip_optional(row.get("home_team_normalized"))
        old_wps = row.get("win_probability_sources")
        new_wps = flip_win_probability_sources(old_wps)

        plan.standalone_repairs.append(
            StandaloneRepairItem(
                event_id=eid,
                commence_time=row["commence_time"],
                old_sport_key=row["sport_key"],
                old_home=row["home_team_name"],
                old_away=row["away_team_name"],
                new_home=new_home,
                new_away=new_away,
                old_home_norm=row.get("home_team_normalized"),
                old_away_norm=row.get("away_team_normalized"),
                new_home_norm=new_home_norm,
                new_away_norm=new_away_norm,
                old_status=row["status"],
                old_wps=old_wps,
                new_wps=new_wps,
                win_prob_snapshot_count=int(counts.get("win_prob_snapshots", 0)),
                has_opening_fields=has_opening_fields(row),
                espn_check=espn_status,
                espn_id=espn_id,
                espn_home=espn_home,
                espn_away=espn_away,
            )
        )

    # Detect any standalone (W) rows that would collide with another standalone (W) row
    window = timedelta(hours=TWIN_WINDOW_HOURS)
    standalone = plan.standalone_repairs
    for i in range(len(standalone)):
        a = standalone[i]
        for j in range(i + 1, len(standalone)):
            b = standalone[j]
            if abs(a.commence_time - b.commence_time) > window:
                continue
            same_pair = (
                matchup_names_one_competitor(a.new_home, b.new_home)
                and matchup_names_one_competitor(a.new_away, b.new_away)
            ) or (
                matchup_names_one_competitor(a.new_home, b.new_away)
                and matchup_names_one_competitor(a.new_away, b.new_home)
            )
            if same_pair:
                plan.internal_w_duplicate_pairs.append((a.event_id, b.event_id))

    return plan


def plan_fingerprint_payload(plan: RepairPlan) -> dict[str, Any]:
    """Canonical structure hashed into ``plan_sha256``.

    Deliberately excludes volatile live float quotes (which tick between dry run
    and apply while the live values are banked and flipped atomically inside the
    apply transaction), while pinning every event ID, action, twin target,
    market ID, anchor ID, sport, team name, status, and refusal.
    """
    return {
        "twin_moves": [
            {
                "event_id": item.event_id,
                "old_sport_key": item.old_sport_key,
                "old_home": item.old_home,
                "old_away": item.old_away,
                "old_status": item.old_status,
                "twin_id": item.twin_id,
                "twin_home": item.twin_home,
                "twin_away": item.twin_away,
                "twin_orientation": item.twin_orientation,
                "market_ids": list(item.market_ids),
                "anchor_ids": list(item.anchor_ids),
            }
            for item in sorted(plan.twin_moves, key=lambda x: x.event_id)
        ],
        "standalone_repairs": [
            {
                "event_id": item.event_id,
                "old_sport_key": item.old_sport_key,
                "old_home": item.old_home,
                "old_away": item.old_away,
                "new_home": item.new_home,
                "new_away": item.new_away,
                "old_status": item.old_status,
            }
            for item in sorted(plan.standalone_repairs, key=lambda x: x.event_id)
        ],
        "refusals": sorted(plan.refusals, key=lambda r: int(r["event_id"])),
        "internal_w_duplicate_pairs": sorted(
            [list(p) for p in plan.internal_w_duplicate_pairs]
        ),
    }


def compute_plan_sha256(plan: RepairPlan) -> str:
    encoded = json.dumps(
        plan_fingerprint_payload(plan), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def summarize_wps(wps: Any) -> str:
    if not isinstance(wps, dict) or not wps:
        return "none"
    parts = []
    for src in sorted(wps.keys()):
        entry = wps[src]
        if isinstance(entry, dict):
            val = _to_float(entry.get("value"))
            parts.append(f"{src}={val:.4f}" if val is not None else f"{src}=?")
        else:
            val = _to_float(entry)
            parts.append(f"{src}={val:.4f}" if val is not None else f"{src}=?")
    return ", ".join(parts)


def espn_wbb_slate(yyyymmdd: str) -> list[dict[str, Any]]:
    """Fetch one ESPN women's college basketball D1 scoreboard day."""
    url = (
        f"https://site.api.espn.com/apis/site/v2/sports/{ESPN_WBB_PATH}"
        f"/scoreboard?dates={yyyymmdd}&limit=500&groups=50"
    )
    out = subprocess.run(
        ["curl", *curl_args(url), "-s", "--max-time", "30", "-w", "\n%{http_code}", url],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"curl exit {out.returncode}")
    body, _, code = out.stdout.rpartition("\n")
    if code.strip() != "200":
        raise RuntimeError(f"HTTP {code.strip()}")
    fixtures: list[dict[str, Any]] = []
    for ev in json.loads(body).get("events", []):
        comp = ev["competitions"][0]
        sides = {
            c["homeAway"]: c["team"].get("displayName")
            for c in comp.get("competitors", [])
        }
        if not sides.get("home") or not sides.get("away"):
            continue
        fixtures.append({
            "espn_id": ev["id"],
            "kickoff": datetime.fromisoformat(ev["date"].replace("Z", "+00:00")),
            "home": sides["home"],
            "away": sides["away"],
            "neutral": bool(comp.get("neutralSite")),
        })
    return fixtures


def load_espn_fixtures_for_dates(dates: set[str]) -> list[dict[str, Any]]:
    seen_ids: set[str] = set()
    fixtures: list[dict[str, Any]] = []
    for day in sorted(dates):
        try:
            day_fixtures = espn_wbb_slate(day)
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN: ESPN WBB {day} fetch failed: {exc}", file=sys.stderr)
            continue
        for fx in day_fixtures:
            if fx["espn_id"] not in seen_ids:
                seen_ids.add(fx["espn_id"])
                fixtures.append(fx)
    return fixtures


def dates_for_events(commence_times: list[datetime]) -> set[str]:
    days: set[str] = set()
    for ct in commence_times:
        utc_ct = ct.astimezone(timezone.utc) if ct.tzinfo else ct.replace(tzinfo=timezone.utc)
        for delta in (-1, 0, 1):
            days.add((utc_ct + timedelta(days=delta)).strftime("%Y%m%d"))
    return days


def check_write_gates(args: argparse.Namespace) -> Optional[str]:
    """Return a refusal string for invalid write/rollback invocations, or None."""
    is_write = bool(getattr(args, "apply", False) or getattr(args, "rollback", None))
    if not is_write:
        return None
    if getattr(args, "apply", False) and getattr(args, "rollback", None):
        return "REFUSING: --apply and --rollback are mutually exclusive."
    if getattr(args, "apply", False):
        if not getattr(args, "backup", False):
            return "REFUSING: --apply requires --backup (D51(b))."
        if not getattr(args, "expect_plan_sha256", None):
            return (
                "REFUSING: --apply requires --expect-plan-sha256 <hash> from "
                "the posted dry run (Ruling 269: A Step 3 drift guard)."
            )
        if getattr(args, "settle_rounds", 2) < 2:
            return "REFUSING: --settle-rounds must be at least 2 (last round is verify-only)."
    app = os.environ.get("HEROKU_APP_NAME")
    if app != PRODUCER_APP:
        where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
        return (
            f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. "
            f"Re-run on Heroku with `heroku run:detached -a {PRODUCER_APP}`."
        )
    return None


def format_dry_run_report(plan: RepairPlan, plan_sha256: str, *, examples: int = 10) -> str:
    lines: list[str] = []
    total_markets = sum(len(item.market_ids) for item in plan.twin_moves)
    total_anchors = sum(len(item.anchor_ids) for item in plan.twin_moves)
    total_snaps = sum(item.win_prob_snapshot_count for item in plan.standalone_repairs)
    sport_counts = Counter(
        [item.old_sport_key for item in plan.twin_moves]
        + [item.old_sport_key for item in plan.standalone_repairs]
    )
    espn_counts = Counter(item.espn_check for item in plan.standalone_repairs)
    opening_count = sum(1 for item in plan.standalone_repairs if item.has_opening_fields)

    lines.append("=== #13036 (Ruling 269: A) DRY RUN — NOTHING WRITTEN ===")
    lines.append(f"plan_sha256: {plan_sha256}")
    lines.append(f"total upcoming scheduled (W) candidates: {plan.total_candidates}")
    lines.append(f"  by source sport: {dict(sport_counts)}")
    lines.append(
        f"  bucket A (has clean basketball_wncaab twin -> move markets + retire (W) row): "
        f"{len(plan.twin_moves)} rows ({total_markets} markets, {total_anchors} anchors)"
    )
    lines.append(
        f"  bucket B (stands alone -> strip (W), move to basketball_wncaab, swap sides, flip chances): "
        f"{len(plan.standalone_repairs)} rows ({total_snaps} win_prob_snapshots, "
        f"{opening_count} with opening fields)"
    )
    lines.append(f"  standalone ESPN cross-check: {dict(espn_counts)}")
    lines.append(f"  refusals: {len(plan.refusals)}")
    lines.append(f"  internal (W)-to-(W) duplicate pairs: {len(plan.internal_w_duplicate_pairs)}")

    if plan.refusals:
        lines.append("\nREFUSALS (must be resolved before --apply):")
        for ref in plan.refusals[:20]:
            lines.append(
                f"  - event {ref['event_id']} ({ref['away']} @ {ref['home']}): {ref['reason']}"
            )
    if plan.internal_w_duplicate_pairs:
        lines.append("\nINTERNAL (W)-TO-(W) DUPLICATE PAIRS:")
        for a_id, b_id in plan.internal_w_duplicate_pairs[:20]:
            lines.append(f"  - ({a_id}, {b_id})")

    lines.append(f"\n--- BUCKET A EXAMPLES (up to {examples} of {len(plan.twin_moves)} twin moves) ---")
    for item in plan.twin_moves[:examples]:
        ts = item.commence_time.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
        lines.append(
            f"  event {item.event_id} [{item.old_sport_key}, {ts}] | "
            f"BEFORE: home='{item.old_home}', away='{item.old_away}', status={item.old_status}, "
            f"{len(item.market_ids)} market(s) {list(item.market_ids)} -> "
            f"AFTER: markets+anchors moved to clean twin {item.twin_id} "
            f"(home='{item.twin_home}', away='{item.twin_away}', espn_id={item.twin_espn_id}, "
            f"pair={item.twin_orientation}); event {item.event_id} status='voided', "
            f"tag='provenance:duplicate-of:{item.twin_id}'"
        )

    lines.append(
        f"\n--- BUCKET B EXAMPLES (up to {examples} of {len(plan.standalone_repairs)} standalone repairs) ---"
    )
    for item in plan.standalone_repairs[:examples]:
        ts = item.commence_time.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
        espn_note = (
            f", espn={item.espn_check} (espn_id={item.espn_id}: home='{item.espn_home}', away='{item.espn_away}')"
            if item.espn_id
            else f", espn={item.espn_check}"
        )
        lines.append(
            f"  event {item.event_id} [{ts}] | "
            f"BEFORE: sport={item.old_sport_key}, home='{item.old_home}', away='{item.old_away}', "
            f"wps=[{summarize_wps(item.old_wps)}], snaps={item.win_prob_snapshot_count} -> "
            f"AFTER: sport={TARGET_SPORT_KEY}, home='{item.new_home}', away='{item.new_away}', "
            f"wps=[{summarize_wps(item.new_wps)}]{espn_note}"
        )

    lines.append("\n--- BACKUP & ONE-COMMAND ROLLBACK ---")
    lines.append(
        "Before any UPDATE commits, pre-write values are saved (keyed by run_id) into "
        "four PostgreSQL backup tables on app `bainluck` inside the same atomic transaction: "
        f"`{BACKUP_EVENTS_TABLE}`, `{BACKUP_MARKETS_TABLE}`, "
        f"`{BACKUP_ANCHORS_TABLE}`, `{BACKUP_SNAPSHOTS_TABLE}`."
    )
    lines.append(
        "One-command rollback (restores all four tables atomically for the printed `<run_id>`):"
    )
    lines.append(
        "  heroku run:detached -a bainluck -- "
        "python3 scripts/repair_wbb_upcoming_orientation_13036.py --rollback <run_id>"
    )
    lines.append("\nAttended apply command (after Alex's go in this window):")
    lines.append(
        "  heroku run:detached -a bainluck -- "
        "python3 scripts/repair_wbb_upcoming_orientation_13036.py "
        f"--backup --apply --expect-plan-sha256 {plan_sha256}"
    )
    return "\n".join(lines)


async def ensure_backup_tables(session) -> None:
    """Create the four D51(b) backup tables idempotently (Ruling 47(c) attended runtime DDL)."""
    await session.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {BACKUP_EVENTS_TABLE} (
                run_id text NOT NULL,
                event_id bigint NOT NULL,
                action text NOT NULL,
                twin_id bigint,
                sport_id bigint NOT NULL,
                status text NOT NULL,
                home_team_name text NOT NULL,
                away_team_name text NOT NULL,
                home_team_normalized text,
                away_team_normalized text,
                home_team_alt_names jsonb,
                away_team_alt_names jsonb,
                home_team_id bigint,
                away_team_id bigint,
                opening_home_probability numeric,
                opening_away_probability numeric,
                opening_home_spread numeric,
                opening_favorite text,
                win_probability_sources jsonb,
                event_tags jsonb,
                backed_up_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (run_id, event_id)
            )
            """
        )
    )
    await session.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {BACKUP_MARKETS_TABLE} (
                run_id text NOT NULL,
                market_id bigint NOT NULL,
                old_event_id bigint NOT NULL,
                new_event_id bigint NOT NULL,
                outcome_count integer NOT NULL,
                backed_up_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (run_id, market_id)
            )
            """
        )
    )
    await session.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {BACKUP_ANCHORS_TABLE} (
                run_id text NOT NULL,
                anchor_id bigint NOT NULL,
                old_event_id bigint NOT NULL,
                new_event_id bigint NOT NULL,
                backed_up_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (run_id, anchor_id)
            )
            """
        )
    )
    await session.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {BACKUP_SNAPSHOTS_TABLE} (
                run_id text NOT NULL,
                snapshot_id bigint NOT NULL,
                event_id bigint NOT NULL,
                old_home_win_probability numeric,
                old_away_win_probability numeric,
                backed_up_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (run_id, snapshot_id)
            )
            """
        )
    )


async def load_plan_from_db(session, *, check_espn: bool) -> tuple[RepairPlan, int]:
    """Read upcoming (W) rows, clean twins, markets, anchors, and counts."""
    wncaab_id = (
        await session.execute(
            text("SELECT id FROM sports WHERE key = :k"), {"k": TARGET_SPORT_KEY}
        )
    ).scalar_one()

    candidates = [
        dict(r)
        for r in (
            await session.execute(
                text(CANDIDATE_SQL), {"sport_keys": list(SOURCE_SPORT_KEYS)}
            )
        ).mappings().all()
    ]
    if not candidates:
        return RepairPlan(), int(wncaab_id)

    min_ct = min(r["commence_time"] for r in candidates) - timedelta(hours=TWIN_WINDOW_HOURS)
    max_ct = max(r["commence_time"] for r in candidates) + timedelta(hours=TWIN_WINDOW_HOURS)
    clean_twins = [
        dict(r)
        for r in (
            await session.execute(
                text(CLEAN_TWINS_SQL),
                {
                    "target_sport_key": TARGET_SPORT_KEY,
                    "window_start": min_ct,
                    "window_end": max_ct,
                },
            )
        ).mappings().all()
    ]

    ids = [int(r["id"]) for r in candidates]
    markets_by_event: dict[int, list[dict[str, Any]]] = {}
    for m in (
        await session.execute(text(MARKETS_FOR_EVENTS_SQL), {"ids": ids})
    ).mappings().all():
        markets_by_event.setdefault(int(m["event_id"]), []).append(dict(m))

    anchors_by_event: dict[int, list[dict[str, Any]]] = {}
    for a in (
        await session.execute(text(ANCHORS_FOR_EVENTS_SQL), {"ids": ids})
    ).mappings().all():
        anchors_by_event.setdefault(int(a["event_id"]), []).append(dict(a))

    child_counts_by_event: dict[int, dict[str, int]] = {}
    for c in (
        await session.execute(text(CHILD_COUNTS_SQL), {"ids": ids})
    ).mappings().all():
        child_counts_by_event[int(c["id"])] = {
            "odds_snapshots": int(c["odds_snapshots"]),
            "espn_snapshots": int(c["espn_snapshots"]),
            "score_snapshots": int(c["score_snapshots"]),
            "win_prob_snapshots": int(c["win_prob_snapshots"]),
        }

    espn_fixtures = None
    if check_espn:
        days = dates_for_events([r["commence_time"] for r in candidates])
        espn_fixtures = load_espn_fixtures_for_dates(days)

    plan = build_plan(
        candidates=candidates,
        clean_twins=clean_twins,
        markets_by_event=markets_by_event,
        anchors_by_event=anchors_by_event,
        child_counts_by_event=child_counts_by_event,
        espn_fixtures=espn_fixtures,
    )
    return plan, int(wncaab_id)


async def apply_plan_atomic(session, plan: RepairPlan, wncaab_sport_id: int, run_id: str) -> dict[str, int]:
    """Bank every touched row and apply twin moves + standalone repairs inside ONE transaction."""
    stats = {
        "events_backed_up": 0,
        "markets_moved": 0,
        "anchors_moved": 0,
        "twins_retired": 0,
        "standalone_repaired": 0,
        "snapshots_swapped": 0,
    }

    # 1. Twin moves: bank event + markets + anchors, move markets/anchors, retire (W) row
    for item in plan.twin_moves:
        live_ev = (
            await session.execute(
                text(
                    """
                    SELECT id, sport_id, status, home_team_name, away_team_name,
                           home_team_normalized, away_team_normalized,
                           home_team_alt_names, away_team_alt_names,
                           home_team_id, away_team_id,
                           opening_home_probability, opening_away_probability,
                           opening_home_spread, opening_favorite,
                           win_probability_sources, event_tags
                    FROM events
                    WHERE id = :eid
                    FOR UPDATE
                    """
                ),
                {"eid": item.event_id},
            )
        ).mappings().one_or_none()
        if live_ev is None or live_ev["status"] != "scheduled":
            raise RuntimeError(
                f"compare-and-set failed for twin event {item.event_id}: "
                f"status={None if live_ev is None else live_ev['status']}"
            )
        twin_alive = (
            await session.execute(
                text(
                    "SELECT id FROM events WHERE id = :tid AND status IN ('scheduled', 'live')"
                ),
                {"tid": item.twin_id},
            )
        ).scalar_one_or_none()
        if twin_alive is None:
            raise RuntimeError(
                f"clean twin {item.twin_id} for event {item.event_id} is no longer active"
            )

        await session.execute(
            text(
                f"""
                INSERT INTO {BACKUP_EVENTS_TABLE} (
                    run_id, event_id, action, twin_id, sport_id, status,
                    home_team_name, away_team_name, home_team_normalized, away_team_normalized,
                    home_team_alt_names, away_team_alt_names, home_team_id, away_team_id,
                    opening_home_probability, opening_away_probability,
                    opening_home_spread, opening_favorite,
                    win_probability_sources, event_tags
                )
                SELECT :run_id, id, 'move_to_twin', :twin_id, sport_id, status,
                       home_team_name, away_team_name, home_team_normalized, away_team_normalized,
                       home_team_alt_names, away_team_alt_names, home_team_id, away_team_id,
                       opening_home_probability, opening_away_probability,
                       opening_home_spread, opening_favorite,
                       win_probability_sources, event_tags
                FROM events
                WHERE id = :eid
                """
            ),
            {"run_id": run_id, "twin_id": item.twin_id, "eid": item.event_id},
        )
        stats["events_backed_up"] += 1

        for market_id, expected_outcomes in item.market_outcome_counts:
            live_outcomes = (
                await session.execute(
                    text("SELECT count(*) FROM futures_outcomes WHERE market_id = :mid"),
                    {"mid": market_id},
                )
            ).scalar_one()
            if int(live_outcomes) != expected_outcomes:
                raise RuntimeError(
                    f"market {market_id} outcome count drifted: {live_outcomes} != {expected_outcomes}"
                )
            await session.execute(
                text(
                    f"""
                    INSERT INTO {BACKUP_MARKETS_TABLE}
                        (run_id, market_id, old_event_id, new_event_id, outcome_count)
                    VALUES (:run_id, :mid, :old_eid, :new_eid, :oc)
                    """
                ),
                {
                    "run_id": run_id,
                    "mid": market_id,
                    "old_eid": item.event_id,
                    "new_eid": item.twin_id,
                    "oc": expected_outcomes,
                },
            )
            res = await session.execute(
                text(
                    """
                    UPDATE futures_markets
                    SET event_id = :new_eid
                    WHERE id = :mid AND event_id = :old_eid
                    """
                ),
                {"mid": market_id, "old_eid": item.event_id, "new_eid": item.twin_id},
            )
            if res.rowcount != 1:
                raise RuntimeError(
                    f"compare-and-set failed moving market {market_id} from {item.event_id}"
                )
            stats["markets_moved"] += 1

        for anchor_id in item.anchor_ids:
            await session.execute(
                text(
                    f"""
                    INSERT INTO {BACKUP_ANCHORS_TABLE}
                        (run_id, anchor_id, old_event_id, new_event_id)
                    VALUES (:run_id, :aid, :old_eid, :new_eid)
                    """
                ),
                {
                    "run_id": run_id,
                    "aid": anchor_id,
                    "old_eid": item.event_id,
                    "new_eid": item.twin_id,
                },
            )
            res = await session.execute(
                text(
                    """
                    UPDATE event_provider_anchors
                    SET event_id = :new_eid
                    WHERE id = :aid AND event_id = :old_eid
                    """
                ),
                {"aid": anchor_id, "old_eid": item.event_id, "new_eid": item.twin_id},
            )
            if res.rowcount != 1:
                raise RuntimeError(
                    f"compare-and-set failed moving anchor {anchor_id} from {item.event_id}"
                )
            stats["anchors_moved"] += 1

        new_tags = append_duplicate_tag(live_ev["event_tags"], item.twin_id)
        res = await session.execute(
            text(
                """
                UPDATE events
                SET status = 'voided',
                    event_tags = cast(:tags_json AS jsonb)
                WHERE id = :eid AND status = 'scheduled'
                """
            ),
            {"eid": item.event_id, "tags_json": json.dumps(new_tags)},
        )
        if res.rowcount != 1:
            raise RuntimeError(f"compare-and-set failed retiring twin event {item.event_id}")
        stats["twins_retired"] += 1

    # 2. Standalone repairs: bank live row + snapshots, strip (W), move sport, swap sides, flip chances
    for item in plan.standalone_repairs:
        live_ev = (
            await session.execute(
                text(
                    """
                    SELECT id, sport_id, status, home_team_name, away_team_name,
                           home_team_normalized, away_team_normalized,
                           home_team_alt_names, away_team_alt_names,
                           home_team_id, away_team_id,
                           opening_home_probability, opening_away_probability,
                           opening_home_spread, opening_favorite,
                           win_probability_sources, event_tags
                    FROM events
                    WHERE id = :eid
                    FOR UPDATE
                    """
                ),
                {"eid": item.event_id},
            )
        ).mappings().one_or_none()
        if (
            live_ev is None
            or live_ev["status"] != "scheduled"
            or live_ev["home_team_name"] != item.old_home
            or live_ev["away_team_name"] != item.old_away
        ):
            raise RuntimeError(
                f"compare-and-set failed for standalone event {item.event_id}: row changed"
            )

        await session.execute(
            text(
                f"""
                INSERT INTO {BACKUP_EVENTS_TABLE} (
                    run_id, event_id, action, twin_id, sport_id, status,
                    home_team_name, away_team_name, home_team_normalized, away_team_normalized,
                    home_team_alt_names, away_team_alt_names, home_team_id, away_team_id,
                    opening_home_probability, opening_away_probability,
                    opening_home_spread, opening_favorite,
                    win_probability_sources, event_tags
                )
                SELECT :run_id, id, 'repair_standalone', NULL, sport_id, status,
                       home_team_name, away_team_name, home_team_normalized, away_team_normalized,
                       home_team_alt_names, away_team_alt_names, home_team_id, away_team_id,
                       opening_home_probability, opening_away_probability,
                       opening_home_spread, opening_favorite,
                       win_probability_sources, event_tags
                FROM events
                WHERE id = :eid
                """
            ),
            {"run_id": run_id, "eid": item.event_id},
        )
        stats["events_backed_up"] += 1

        # Bank exact live win_prob_snapshots by snapshot_id before swapping
        await session.execute(
            text(
                f"""
                INSERT INTO {BACKUP_SNAPSHOTS_TABLE} (
                    run_id, snapshot_id, event_id,
                    old_home_win_probability, old_away_win_probability
                )
                SELECT :run_id, id, event_id, home_win_probability, away_win_probability
                FROM win_prob_snapshots
                WHERE event_id = :eid
                """
            ),
            {"run_id": run_id, "eid": item.event_id},
        )
        snap_res = await session.execute(
            text(
                f"""
                UPDATE win_prob_snapshots
                SET home_win_probability = away_win_probability,
                    away_win_probability = home_win_probability
                WHERE event_id = :eid
                  AND id IN (
                      SELECT snapshot_id FROM {BACKUP_SNAPSHOTS_TABLE}
                      WHERE run_id = :run_id AND event_id = :eid
                  )
                """
            ),
            {"run_id": run_id, "eid": item.event_id},
        )
        stats["snapshots_swapped"] += snap_res.rowcount

        flipped_live_wps = flip_win_probability_sources(live_ev["win_probability_sources"])
        new_opening_spread = (
            -live_ev["opening_home_spread"]
            if live_ev["opening_home_spread"] is not None
            else None
        )
        new_opening_fav = flip_opening_favorite(live_ev["opening_favorite"])

        res = await session.execute(
            text(
                """
                UPDATE events
                SET sport_id = :wncaab_sport_id,
                    home_team_name = :new_home,
                    away_team_name = :new_away,
                    home_team_normalized = :new_home_norm,
                    away_team_normalized = :new_away_norm,
                    home_team_alt_names = away_team_alt_names,
                    away_team_alt_names = home_team_alt_names,
                    home_team_id = away_team_id,
                    away_team_id = home_team_id,
                    opening_home_probability = opening_away_probability,
                    opening_away_probability = opening_home_probability,
                    opening_home_spread = :new_opening_spread,
                    opening_favorite = :new_opening_fav,
                    win_probability_sources = cast(:wps_json AS jsonb)
                WHERE id = :eid
                  AND status = 'scheduled'
                  AND home_team_name = :old_home
                  AND away_team_name = :old_away
                """
            ),
            {
                "wncaab_sport_id": wncaab_sport_id,
                "new_home": item.new_home,
                "new_away": item.new_away,
                "new_home_norm": item.new_home_norm,
                "new_away_norm": item.new_away_norm,
                "new_opening_spread": new_opening_spread,
                "new_opening_fav": new_opening_fav,
                "wps_json": None if flipped_live_wps is None else json.dumps(flipped_live_wps),
                "eid": item.event_id,
                "old_home": item.old_home,
                "old_away": item.old_away,
            },
        )
        if res.rowcount != 1:
            raise RuntimeError(
                f"compare-and-set failed repairing standalone event {item.event_id}"
            )
        stats["standalone_repaired"] += 1

    return stats


async def rollback_run_atomic(session, run_id: str) -> dict[str, int]:
    """Restore every event, market, anchor, and snapshot backed up under ``run_id``."""
    ev_count = (
        await session.execute(
            text(f"SELECT count(*) FROM {BACKUP_EVENTS_TABLE} WHERE run_id = :run_id"),
            {"run_id": run_id},
        )
    ).scalar_one()
    if int(ev_count) == 0:
        raise RuntimeError(f"no backup rows found for run_id={run_id}")

    ev_res = await session.execute(
        text(
            f"""
            UPDATE events e
            SET sport_id = b.sport_id,
                status = b.status,
                home_team_name = b.home_team_name,
                away_team_name = b.away_team_name,
                home_team_normalized = b.home_team_normalized,
                away_team_normalized = b.away_team_normalized,
                home_team_alt_names = b.home_team_alt_names,
                away_team_alt_names = b.away_team_alt_names,
                home_team_id = b.home_team_id,
                away_team_id = b.away_team_id,
                opening_home_probability = b.opening_home_probability,
                opening_away_probability = b.opening_away_probability,
                opening_home_spread = b.opening_home_spread,
                opening_favorite = b.opening_favorite,
                win_probability_sources = b.win_probability_sources,
                event_tags = b.event_tags
            FROM {BACKUP_EVENTS_TABLE} b
            WHERE b.run_id = :run_id
              AND e.id = b.event_id
            """
        ),
        {"run_id": run_id},
    )
    mkt_res = await session.execute(
        text(
            f"""
            UPDATE futures_markets fm
            SET event_id = b.old_event_id
            FROM {BACKUP_MARKETS_TABLE} b
            WHERE b.run_id = :run_id
              AND fm.id = b.market_id
            """
        ),
        {"run_id": run_id},
    )
    anc_res = await session.execute(
        text(
            f"""
            UPDATE event_provider_anchors a
            SET event_id = b.old_event_id
            FROM {BACKUP_ANCHORS_TABLE} b
            WHERE b.run_id = :run_id
              AND a.id = b.anchor_id
            """
        ),
        {"run_id": run_id},
    )
    snap_res = await session.execute(
        text(
            f"""
            UPDATE win_prob_snapshots wp
            SET home_win_probability = b.old_home_win_probability,
                away_win_probability = b.old_away_win_probability
            FROM {BACKUP_SNAPSHOTS_TABLE} b
            WHERE b.run_id = :run_id
              AND wp.id = b.snapshot_id
            """
        ),
        {"run_id": run_id},
    )
    return {
        "events_restored": ev_res.rowcount,
        "markets_restored": mkt_res.rowcount,
        "anchors_restored": anc_res.rowcount,
        "snapshots_restored": snap_res.rowcount,
    }


def classify_settlement(stored: Optional[float], expected: Optional[float]) -> str:
    if stored is None and expected is None:
        return "UNPRICED"
    if stored is None:
        return "NOT-YET-WRITTEN"
    if expected is None:
        return "SOURCE-WOULD-RETIRE"
    if abs(stored - expected) < SETTLE_EPSILON:
        return "SETTLED"
    if abs(expected - (1.0 - stored)) < SETTLE_EPSILON:
        return "REVERTED"
    return "UNEXPECTED"


async def writer_expectation(session, ids: list[int]) -> dict[int, Optional[float]]:
    from sqlalchemy import select

    from app.models.models import Event, FuturesMarket, FuturesOutcome
    from app.utils.live_blend import MarketOutcomes, compute_source_home_probability

    if not ids:
        return {}
    market_rows = (
        await session.execute(
            select(FuturesMarket, Event)
            .join(Event, FuturesMarket.event_id == Event.id)
            .where(FuturesMarket.source == "polymarket", FuturesMarket.event_id.in_(ids))
        )
    ).all()

    outcomes_by_market: dict[int, list] = {}
    if market_rows:
        for outcome in (
            await session.execute(
                select(FuturesOutcome).where(
                    FuturesOutcome.market_id.in_([m.id for m, _ in market_rows])
                )
            )
        ).scalars():
            outcomes_by_market.setdefault(outcome.market_id, []).append(outcome)

    grouped: dict[int, tuple] = {}
    for market, event in market_rows:
        entry = grouped.setdefault(event.id, (event, []))
        entry[1].append(
            MarketOutcomes(
                market=market,
                outcomes=outcomes_by_market.get(market.id, []),
                event_has_result=event.completed_at is not None,
            )
        )

    expected: dict[int, Optional[float]] = {eid: None for eid in ids}
    for event_id, (event, group) in grouped.items():
        reading = compute_source_home_probability(
            group, event.home_team_name, event.away_team_name
        )
        expected[event_id] = None if reading is None else round(reading.home_probability, 4)
    return expected


async def settle_standalone(
    session, ids: list[int], swapped_at, rounds: int, wait_s: int
) -> tuple[dict[int, str], Counter]:
    if not ids:
        return {}, Counter()
    verdicts: dict[int, str] = {}
    tally: Counter = Counter()
    for attempt in range(1, rounds + 1):
        final = attempt == rounds
        print(
            f"\n-- settle round {attempt}/{rounds}"
            f"{' (verify only)' if final else ''} — waiting {wait_s}s"
        )
        await asyncio.sleep(wait_s)
        expected = await writer_expectation(session, ids)
        stored = {
            int(r["id"]): r["value"]
            for r in (
                await session.execute(text(STORED_POLY_SQL), {"ids": ids})
            ).mappings().all()
        }
        verdicts = {
            eid: classify_settlement(stored.get(eid), expected.get(eid)) for eid in ids
        }
        tally = Counter(verdicts.values())
        print(f"   settle verdicts: {dict(tally)}")

        reverted = [eid for eid, v in verdicts.items() if v == "REVERTED"]
        if final or not reverted:
            if not reverted and not final:
                continue
            break

        snaps = 0
        for eid in reverted:
            await session.execute(
                text(RESTAMP_POLY_SQL), {"event_id": eid, "value": expected[eid]}
            )
            snaps += (
                await session.execute(
                    text(RESTAMP_SNAPSHOTS_SQL),
                    {
                        "event_id": eid,
                        "since": swapped_at,
                        "expected": expected[eid],
                        "eps": SETTLE_EPSILON,
                    },
                )
            ).rowcount
        await session.commit()
        print(f"   re-stamped {len(reverted)} events and {snaps} racing snapshots")

    return verdicts, tally


async def run_verify_post_apply(session, run_id: Optional[str], limit: int = 10) -> int:
    remaining = (
        await session.execute(
            text(REMAINING_UPCOMING_W_SQL), {"sport_keys": list(SOURCE_SPORT_KEYS)}
        )
    ).scalar_one()
    print(f"remaining upcoming scheduled (W) rows: {remaining}")

    if run_id:
        ids = [
            int(r["event_id"])
            for r in (
                await session.execute(
                    text(
                        f"""
                        SELECT event_id FROM {BACKUP_EVENTS_TABLE}
                        WHERE run_id = :run_id AND action = 'repair_standalone'
                        ORDER BY event_id ASC
                        """
                    ),
                    {"run_id": run_id},
                )
            ).mappings().all()
        ]
    else:
        ids = [
            int(r["id"])
            for r in (
                await session.execute(
                    text(
                        """
                        SELECT e.id FROM events e
                        JOIN sports s ON s.id = e.sport_id
                        WHERE s.key = :k AND e.status = 'scheduled'
                        ORDER BY e.commence_time ASC, e.id ASC
                        LIMIT 200
                        """
                    ),
                    {"k": TARGET_SPORT_KEY},
                )
            ).mappings().all()
        ]

    if not ids:
        print("no repaired standalone rows to compare against ESPN.")
        return 0 if int(remaining) == 0 else 1

    rows = [
        dict(r)
        for r in (
            await session.execute(text(VERIFY_REPAIRED_SQL), {"ids": ids})
        ).mappings().all()
    ]
    fixtures = load_espn_fixtures_for_dates(dates_for_events([r["commence_time"] for r in rows]))

    matched = 0
    mismatched = 0
    print(f"\n--- POST-APPLY ESPN VERIFICATION (first {limit} ESPN-matched games) ---")
    for row in rows:
        # match_espn_fixture expects (home, away) in pre-repair order; here rows are
        # ALREADY repaired, so aligned means stored_home == espn_home!
        window = timedelta(hours=ESPN_WINDOW_HOURS)
        hits = [
            fx
            for fx in fixtures
            if abs(fx["kickoff"] - row["commence_time"]) <= window
            and (
                (
                    matchup_names_one_competitor(row["home_team_name"], fx["home"])
                    and matchup_names_one_competitor(row["away_team_name"], fx["away"])
                )
                or (
                    matchup_names_one_competitor(row["home_team_name"], fx["away"])
                    and matchup_names_one_competitor(row["away_team_name"], fx["home"])
                )
            )
        ]
        if len(hits) != 1 or hits[0].get("neutral"):
            continue
        fx = hits[0]
        aligned = matchup_names_one_competitor(
            row["home_team_name"], fx["home"]
        ) and matchup_names_one_competitor(row["away_team_name"], fx["away"])
        if aligned:
            matched += 1
            if matched <= limit:
                ts = row["commence_time"].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
                print(
                    f"  OK event {row['id']} [{ts}] | "
                    f"Bain Luck: {row['away_team_name']} @ {row['home_team_name']} | "
                    f"ESPN {fx['espn_id']}: {fx['away']} @ {fx['home']}"
                )
        else:
            mismatched += 1
            print(
                f"  MISMATCH event {row['id']} | "
                f"Bain Luck: {row['away_team_name']} @ {row['home_team_name']} | "
                f"ESPN {fx['espn_id']}: {fx['away']} @ {fx['home']}"
            )
    print(f"\nESPN non-neutral matches verified: {matched} aligned, {mismatched} mismatched")
    return 0 if (int(remaining) == 0 and mismatched == 0) else 1


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="execute the repair (default: dry run)")
    ap.add_argument("--backup", action="store_true", help="save before-values in backup tables (required with --apply)")
    ap.add_argument(
        "--expect-plan-sha256",
        type=str,
        default=None,
        help="SHA-256 printed by the dry run; --apply aborts if live plan differs",
    )
    ap.add_argument(
        "--rollback",
        type=str,
        default=None,
        metavar="RUN_ID",
        help="one-command rollback restoring all rows banked under RUN_ID",
    )
    ap.add_argument(
        "--verify-run",
        type=str,
        default=None,
        metavar="RUN_ID",
        help="read-only Step 4 verification: 10 repaired games beside ESPN + remaining (W) count",
    )
    ap.add_argument("--no-espn-check", action="store_true", help="skip ESPN scoreboard cross-check")
    ap.add_argument("--examples", type=int, default=10, help="examples per bucket in dry run (default 10)")
    ap.add_argument("--settle-rounds", type=int, default=2, help="settle rounds after apply (min 2, default 2)")
    ap.add_argument("--settle-wait", type=int, default=45, help="seconds per settle round (default 45)")
    args = ap.parse_args()

    refusal = check_write_gates(args)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2

    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        if args.verify_run:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            return await run_verify_post_apply(session, args.verify_run, limit=args.examples)

        if args.rollback:
            stats = await rollback_run_atomic(session, args.rollback)
            await session.commit()
            print(f"ROLLBACK COMMITTED for run_id={args.rollback}: {json.dumps(stats)}")
            return 0

        if not args.apply:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            plan, _ = await load_plan_from_db(session, check_espn=not args.no_espn_check)
            plan_sha = compute_plan_sha256(plan)
            await session.rollback()
            print(format_dry_run_report(plan, plan_sha, examples=args.examples))
            return 0

        # --apply path: re-derive plan, verify zero drift + zero refusals, bank + apply atomically
        plan, wncaab_sport_id = await load_plan_from_db(session, check_espn=not args.no_espn_check)
        live_sha = compute_plan_sha256(plan)
        if live_sha != args.expect_plan_sha256:
            print(
                f"REFUSING --apply: live plan_sha256 ({live_sha}) != expected "
                f"({args.expect_plan_sha256}). Something changed since the dry run; "
                "stopping with nothing written.",
                file=sys.stderr,
            )
            print(format_dry_run_report(plan, live_sha, examples=args.examples))
            return 2

        if plan.refusals or plan.internal_w_duplicate_pairs:
            print(
                f"REFUSING --apply: {len(plan.refusals)} refusal(s) and "
                f"{len(plan.internal_w_duplicate_pairs)} internal duplicate pair(s) in plan. "
                "Nothing written.",
                file=sys.stderr,
            )
            return 2

        if not plan.twin_moves and not plan.standalone_repairs:
            print("nothing to do — 0 upcoming (W) rows.")
            return 0

        await ensure_backup_tables(session)
        run_id = uuid.uuid4().hex
        stats = await apply_plan_atomic(session, plan, wncaab_sport_id, run_id)
        await session.commit()

        swapped_at = (await session.execute(text("SELECT now()"))).scalar_one()
        remaining = (
            await session.execute(
                text(REMAINING_UPCOMING_W_SQL), {"sport_keys": list(SOURCE_SPORT_KEYS)}
            )
        ).scalar_one()

        print(f"COMMITTED run_id={run_id} at {swapped_at.isoformat()}")
        print(f"stats: {json.dumps(stats)}")
        print(f"remaining upcoming scheduled (W) rows: {remaining}")
        print(
            "ROLLBACK (one command):\n"
            f"  heroku run:detached -a {PRODUCER_APP} -- "
            f"python3 scripts/repair_wbb_upcoming_orientation_13036.py --rollback {run_id}"
        )

        standalone_ids = [item.event_id for item in plan.standalone_repairs]
        verdicts, tally = await settle_standalone(
            session, standalone_ids, swapped_at, args.settle_rounds, args.settle_wait
        )
        unsettled = sorted(
            eid for eid, v in verdicts.items() if v not in ("SETTLED", "UNPRICED")
        )
        print(f"SETTLE VERDICT: {dict(tally)}")

        await run_verify_post_apply(session, run_id, limit=args.examples)

        if unsettled or int(remaining) != 0:
            print(
                f"NOT CLEAN: unsettled={len(unsettled)} ({unsettled[:10]}), "
                f"remaining_w={remaining}",
                file=sys.stderr,
            )
            return 3
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
