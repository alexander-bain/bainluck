"""Shared cross-surface ranking profiles and scoring helpers (#11937 Stage 2 Step 1).

Connects Discover, Sports (`mode=sports`), and My Stuff (`my_teams_only=True` and
`/api/users/me/team-futures`) to one explicit surface profile and scoring contract
without altering frozen Discover Stage 1 weights (`discover_rank.py`,
`discover_rank_c3.py`) or live Discover behavior.

Invariant (CERT-2190): ``discover``, ``sports``, and ``my_stuff`` are three
distinct surfaces. ``my_teams_only=True`` ALWAYS resolves to ``my_stuff``, even if
the caller also passes ``mode="sports"``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

SurfaceId = Literal["discover", "sports", "my_stuff"]


@dataclass(frozen=True, slots=True)
class RankingSurfaceProfile:
    """Explicit surface-level policy shared across feed surfaces and My Stuff."""

    surface: SurfaceId
    event_weight: float = 1.0
    futures_weight: float = 1.0
    live_game_bonus: float = 0.0
    imminent_kickoff_bonus: float = 0.0
    followed_team_bonus: float = 0.0
    movement_weight: float = 1.0
    coherent_market_bonus: float = 0.0
    # Not read yet — reserved for later Stage 2 steps; the real Sports/Discover
    # diversity and futures caps live in feed.py (`cap_futures_on_games_led_first_page`).
    apply_diversity_caps: bool = True
    apply_discover_demotion: bool = False
    futures_first_page_cap: int | None = None


DISCOVER_SURFACE_PROFILE = RankingSurfaceProfile(
    surface="discover",
    event_weight=1.0,
    futures_weight=1.0,
    live_game_bonus=0.0,
    imminent_kickoff_bonus=0.0,
    followed_team_bonus=0.0,
    movement_weight=1.0,
    coherent_market_bonus=0.0,
    apply_diversity_caps=True,  # not read yet
    apply_discover_demotion=True,  # not read yet
    futures_first_page_cap=None,  # not read yet
)

SPORTS_SURFACE_PROFILE = RankingSurfaceProfile(
    surface="sports",
    event_weight=1.0,
    futures_weight=1.0,
    live_game_bonus=0.0,
    imminent_kickoff_bonus=0.0,
    followed_team_bonus=0.0,
    movement_weight=1.0,
    coherent_market_bonus=0.0,
    apply_diversity_caps=True,  # not read yet
    apply_discover_demotion=False,  # not read yet
    futures_first_page_cap=None,  # not read yet; real cap lives in cap_futures_on_games_led_first_page
)

MY_STUFF_SURFACE_PROFILE = RankingSurfaceProfile(
    surface="my_stuff",
    event_weight=1.0,
    futures_weight=1.0,
    live_game_bonus=0.0,
    imminent_kickoff_bonus=0.0,
    followed_team_bonus=0.0,
    movement_weight=1.0,
    coherent_market_bonus=0.0,
    apply_diversity_caps=False,  # not read yet
    apply_discover_demotion=False,  # not read yet
    futures_first_page_cap=None,  # not read yet
)

_PROFILES_BY_SURFACE: dict[SurfaceId, RankingSurfaceProfile] = {
    "discover": DISCOVER_SURFACE_PROFILE,
    "sports": SPORTS_SURFACE_PROFILE,
    "my_stuff": MY_STUFF_SURFACE_PROFILE,
}


def get_surface_profile(surface: SurfaceId) -> RankingSurfaceProfile:
    """Return the canonical immutable profile for a surface identifier."""
    return _PROFILES_BY_SURFACE[surface]


def resolve_surface_profile(
    *,
    mode: str | None = None,
    sports_mode: bool = False,
    my_teams_only: bool = False,
) -> RankingSurfaceProfile:
    """Resolve the active ranking surface, honoring CERT-2190 My Stuff precedence."""
    if my_teams_only:
        return MY_STUFF_SURFACE_PROFILE
    normalized = (mode or "").strip().lower()
    if sports_mode or normalized == "sports":
        return SPORTS_SURFACE_PROFILE
    return DISCOVER_SURFACE_PROFILE


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    return None


def _base_rank_value(candidate: dict[str, Any]) -> float:
    for key in ("_rank_score", "score", "probability"):
        val = candidate.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    return 0.0


def _candidate_team_ids(candidate: dict[str, Any]) -> set[int]:
    ids: set[int] = set()
    data = candidate.get("data")
    if isinstance(data, dict):
        for team_key in ("home_team_id", "away_team_id", "team_id"):
            tid = data.get(team_key)
            if isinstance(tid, int):
                ids.add(tid)
        matched = data.get("matched_team")
        if isinstance(matched, dict) and isinstance(matched.get("id"), int):
            ids.add(matched["id"])
    matched_top = candidate.get("matched_team")
    if isinstance(matched_top, dict) and isinstance(matched_top.get("id"), int):
        ids.add(matched_top["id"])
    pers = candidate.get("_sports_pers_inputs")
    if isinstance(pers, dict):
        for tid in pers.get("outcome_team_ids") or ():
            if isinstance(tid, int):
                ids.add(tid)
    return ids


def score_candidate_for_surface(
    candidate: dict[str, Any],
    profile: RankingSurfaceProfile,
    *,
    followed_team_ids: set[int] | None = None,
    now: datetime | None = None,
) -> tuple[float, dict[str, Any]]:
    """Compute a deterministic surface score and breakdown without mutating input.

    Under ``DISCOVER_SURFACE_PROFILE``, returns the base score unmodified so frozen
    Discover Stage 1 weights cannot drift.
    """
    base_score = _base_rank_value(candidate)
    if profile.surface == "discover":
        return base_score, {
            "surface": profile.surface,
            "base": base_score,
            "weighted": base_score,
        }

    item_type = str(candidate.get("type") or "").strip().lower()
    data = candidate.get("data") if isinstance(candidate.get("data"), dict) else {}
    weight = profile.event_weight if item_type == "event" else profile.futures_weight

    live_bonus = 0.0
    if (
        item_type == "event"
        and profile.live_game_bonus != 0.0
        and str(data.get("status") or "").lower() == "live"
    ):
        live_bonus = profile.live_game_bonus

    imminent_bonus = 0.0
    if (
        item_type == "event"
        and profile.imminent_kickoff_bonus != 0.0
        and str(data.get("status") or "").lower() != "completed"
        and str(data.get("status") or "").lower() != "closed"
    ):
        anchor = _as_utc(now) if now is not None else None
        kickoff = _as_utc(data.get("commence_time"))
        if anchor is not None and kickoff is not None:
            delta_s = (kickoff - anchor).total_seconds()
            if 0.0 <= delta_s <= 6 * 3600:
                imminent_bonus = profile.imminent_kickoff_bonus

    team_bonus = 0.0
    if profile.followed_team_bonus != 0.0 and followed_team_ids:
        if _candidate_team_ids(candidate) & followed_team_ids:
            team_bonus = profile.followed_team_bonus

    coherent_bonus = 0.0
    if profile.coherent_market_bonus != 0.0 and "_illiquid_binary" in candidate:
        if not candidate.get("_illiquid_binary"):
            coherent_bonus = profile.coherent_market_bonus

    movement_adj = 0.0
    if profile.movement_weight != 1.0:
        move_val = candidate.get("movement_magnitude")
        if isinstance(move_val, (int, float)):
            movement_adj = float(move_val) * (profile.movement_weight - 1.0)

    total = (
        base_score * weight
        + live_bonus
        + imminent_bonus
        + team_bonus
        + coherent_bonus
        + movement_adj
    )
    return float(total), {
        "surface": profile.surface,
        "base": base_score,
        "weight": weight,
        "live_bonus": live_bonus,
        "imminent_bonus": imminent_bonus,
        "team_bonus": team_bonus,
        "coherent_bonus": coherent_bonus,
        "movement_adj": movement_adj,
        "weighted": float(total),
    }


def rank_candidates_for_surface(
    candidates: Iterable[dict[str, Any]],
    profile: RankingSurfaceProfile,
    *,
    followed_team_ids: set[int] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return a newly ordered list of candidates scored for ``profile`` without mutating inputs."""
    items = list(candidates)
    if profile.surface == "discover":
        return sorted(
            items,
            key=lambda item: (
                item.get("_rank_score", item.get("score", 0.0)),
                item.get("_sort_time", 0.0),
            ),
            reverse=True,
        )

    scored: list[tuple[tuple[float, float, int], dict[str, Any]]] = []
    for idx, item in enumerate(items):
        val, _ = score_candidate_for_surface(
            item,
            profile,
            followed_team_ids=followed_team_ids,
            now=now,
        )
        sort_time = item.get("_sort_time")
        tie_time = float(sort_time) if isinstance(sort_time, (int, float)) else 0.0
        scored.append(((val, tie_time, -idx), item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [pair[1] for pair in scored]


def order_my_stuff_team_buckets(
    per_team_items: dict[int, list[dict[str, Any]]],
    *,
    limit: int,
    profile: RankingSurfaceProfile = MY_STUFF_SURFACE_PROFILE,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Order per-team My Stuff futures via shared ``surface_rank`` round-robin fill.

    Uses ``score_candidate_for_surface`` so the team whose leading candidate scores
    highest leads each round while preserving strict round-robin coverage across all
    followed teams (no diversity caps).
    """
    if not per_team_items or limit <= 0:
        return []

    def _team_lead_key(tid: int) -> tuple[float, int]:
        bucket = per_team_items[tid]
        lead_item = bucket[0]
        score_val, _ = score_candidate_for_surface(lead_item, profile, now=now)
        return score_val, -tid

    ordered_team_ids = sorted(per_team_items.keys(), key=_team_lead_key, reverse=True)
    items: list[dict[str, Any]] = []
    depth = 0
    while len(items) < limit:
        progressed = False
        for tid in ordered_team_ids:
            bucket = per_team_items[tid]
            if depth < len(bucket):
                items.append(bucket[depth])
                progressed = True
                if len(items) >= limit:
                    break
        if not progressed:
            break
        depth += 1
    return items
