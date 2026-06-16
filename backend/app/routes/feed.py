"""Unified feed API endpoint.

Merges scored events and scored futures into a single ranked list,
providing a "what's interesting right now" view across all content types.

Supports optional authentication: logged-in users get personalized scoring
based on their favorite teams, sport affinities, and pinned items.
Anonymous users see the generic interestingness feed.
"""

import asyncio
import hashlib
import inspect
import json as _json_module
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, or_, func, case, cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload
from sqlalchemy.dialects.postgresql import JSONB

from app.dependencies.auth import get_optional_user
from app.models import Event, Sport, FuturesMarket, FuturesOutcome
from app.models.models import (
    DiscoverInteraction,
    DiscoverReviewDecision,
    ExternalCuratorGroundTruthItem,
    User,
    UserFavorite,
    UserPreference,
    UserPin,
    Team,
)
from app.services import get_db, get_db_rw
from app.utils.aggregation import (
    SOURCE_WEIGHTS,
    compute_aggregate_probability as _compute_aggregate_probability,
)
from app.utils.event_taxonomy import compute_event_tags, compute_market_tags
from app.utils.discover_card_archetypes import classify_discover_card_archetype
from app.utils.discover_bundles import (
    assemble_awards_theme_bundles,
    assemble_discover_comparison_bundles,
    assemble_geopolitics_theme_bundles,
)
from app.utils import (
    compute_highlight,
    get_highlight_label,
    should_highlight,
    get_league_tier,
    get_season_multiplier,
)
from app.utils.highlights import parse_game_progress
from app.utils.futures_highlights import (
    compute_futures_highlight,
    should_highlight_futures,
)
from app.utils.feed_market_quality import (
    _story_key as compute_story_key,
    apply_explanation_quality_score,
    apply_quality_score,
    backfill_discover_editorial_tail,
    balance_discover_event_category_mix,
    cap_low_quality_families,
    classify_market_quality,
    diversify_discover_first_page,
    diversify_quality_families,
    editorial_archetype,
)
from app.utils.feed_reasons import (
    generate_event_reason,
    generate_futures_context_summary,
    generate_futures_headline,
    generate_futures_reason,
    humanize_binary_outcome_name,
    humanize_outcome_names_for_feed,
)
from app.utils.external_curator_ground_truth import (
    load_external_curator_ground_truth_report_from_env,
)
from app.utils.persisted_external_curator_ground_truth import (
    load_persisted_external_curator_ground_truth_report,
    merge_external_curator_ground_truth_reports,
)
from app.utils.feed_quality_debug import (
    apply_db_trace_missing_ground_truth_triage,
    build_feed_quality_debug,
    find_missing_ground_truth_items,
    load_default_ground_truth_items,
    summarize_missing_ground_truth_db_trace,
)
from app.utils.feed_cache import (
    FEED_RESPONSE_STALE_TTL_SECONDS,
    build_feed_cache_metadata,
)
from app.utils.polymarket_email_ground_truth import (
    load_polymarket_email_ground_truth_report_from_env,
    summarize_polymarket_email_ground_truth,
)
from app.tasks.enrich_markets import (
    _discover_llm_feature_tokens,
    _discover_llm_score_adjustment,
    _get_discover_llm_metadata,
)
from app.utils.hook_staleness import is_hook_stale
from app.utils.labeling_queue import (
    filter_reviewed_feed_items as _filter_reviewed_feed_items,
    load_reviewed_ranking_keys as _load_reviewed_ranking_keys,
    review_key_for_feed_item as _review_key_for_feed_item,
)
from app.utils.name_normalization import names_match as _team_name_matches
from app.utils.personalization import (
    PersonalizationContext,
    compute_event_multiplier,
    compute_futures_multiplier,
)
from app.routes.admin_utils import _check_admin_auth, _resolve_admin_email
from app.routes.events import _build_team_lookup, _format_team_data

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Card recycling for exhausted feeds (heavy users hit a hard "all caught up"
# wall once they've impressioned the fresh candidate pool; user_seen_markets is
# empty in prod, so the wall is the DiscoverInteraction impression suppression at
# seen_suppression_hours). Recycling re-shows a previously-seen card ONLY if it
# went stale enough to read as new again (FEED_RECYCLE_AFTER_HOURS) AND is still
# worth it (live/contested or moved materially in 24h). Recycled cards carry a
# score penalty so fresh un-seen cards always outrank them — recycling therefore
# only surfaces when the fresh pool can't fill the page (an implicit serving
# floor). Fresh users (no impressions) are unaffected. All tunable via env. ---
FEED_RECYCLE_ENABLED = os.getenv("FEED_RECYCLE_ENABLED", "true").lower() == "true"
FEED_RECYCLE_AFTER_HOURS = float(os.getenv("FEED_RECYCLE_AFTER_HOURS", "12"))
FEED_RECYCLE_MATERIALITY = float(os.getenv("FEED_RECYCLE_MATERIALITY", "0.08"))
FEED_RECYCLE_PENALTY = float(os.getenv("FEED_RECYCLE_PENALTY", "25"))
# An outcome probability in this band counts the market as still "live"/contested.
_FEED_RECYCLE_LIVE_LO = 0.12
_FEED_RECYCLE_LIVE_HI = 0.88


def _futures_recycle_eligible(market, ctx, now) -> bool:
    """Whether a previously-seen futures market may be recycled into an exhausted
    feed.

    True only if it was last seen at least FEED_RECYCLE_AFTER_HOURS ago (so it
    reads as new again — a soft recycle, not infinite repetition) AND is still
    worth re-showing: a contested/live outcome OR a material 24h move. Returns
    False when recycling is disabled. Missing last-seen timestamps (e.g. from the
    user_seen_markets supplement) skip only the age guard.
    """
    if not FEED_RECYCLE_ENABLED:
        return False
    last_seen = ctx.recent_seen_futures_at.get(market.id)
    if last_seen is not None:
        age_hours = (now - last_seen).total_seconds() / 3600.0
        if age_hours < FEED_RECYCLE_AFTER_HOURS:
            return False
    moved = False
    competitive = False
    for o in market.outcomes:
        ch = o.probability_change_24h
        if ch is not None and abs(float(ch)) >= FEED_RECYCLE_MATERIALITY:
            moved = True
        p = o.current_probability
        if p is not None and _FEED_RECYCLE_LIVE_LO <= float(p) <= _FEED_RECYCLE_LIVE_HI:
            competitive = True
        if moved and competitive:
            break
    return moved or competitive


_DISCOVER_ACTIONS = {
    "impression",
    "detail_click",
    "open",
    "dismiss",
    "like",
    "unlike",
    "share",
    "group_expand",
    "challenge_start",
    "challenge_complete",
    "context_expand",
    "context_collapse",
}
_DISCOVER_ITEM_TYPES = {"event", "futures", "grid", "tournament"}
_DISCOVER_SURFACES = {"web", "native", "unknown"}


class DiscoverInteractionIn(BaseModel):
    action: str = Field(..., max_length=30)
    item_type: str = Field(..., max_length=20)
    item_id: str = Field(..., max_length=100)
    category: str | None = Field(None, max_length=80)
    item_name: str | None = Field(None, max_length=300)
    score: int | None = None
    rank: int | None = None
    surface: str = Field("unknown", max_length=20)
    source: str | None = Field(None, max_length=50)


class DiscoverInteractionBatch(BaseModel):
    interactions: list[DiscoverInteractionIn] = Field(..., min_length=1, max_length=50)


def _normalize_discover_value(
    value: str | None, allowed: set[str], fallback: str
) -> str:
    normalized = (value or fallback).strip().lower()
    return normalized if normalized in allowed else fallback


def _session_id_from_request(request: Request) -> str | None:
    return request.cookies.get("session_id") or request.headers.get("x-session-id")


def _record_feed_timing(
    timings: list[dict[str, float | str]],
    started_at: float,
    previous_at: float,
    stage: str,
) -> float:
    """Record a stage timing relative to request start for admin diagnostics."""
    current_at = time.perf_counter()
    timings.append(
        {
            "stage": stage,
            "ms": round((current_at - previous_at) * 1000, 2),
            "elapsed_ms": round((current_at - started_at) * 1000, 2),
        }
    )
    return current_at


def _set_feed_timing_header(response: Response, started_at: float) -> None:
    response.headers["X-Feed-Elapsed-Ms"] = str(
        round((time.perf_counter() - started_at) * 1000, 2)
    )


def _set_feed_cache_status(response: Response, status: str) -> None:
    response.headers["X-Feed-Cache"] = status


from app.routes.admin_utils import _check_admin_secret  # noqa

def _discover_runtime_config_defaults() -> dict[str, float | bool]:
    return {
        "interaction_suppression_enabled": os.getenv(
            "DISCOVER_INTERACTION_SUPPRESSION", "true"
        ).lower()
        != "false",
        "seen_suppression_hours": float(
            os.getenv("DISCOVER_SEEN_SUPPRESSION_HOURS", "48")
        ),
        "dismiss_suppression_days": float(
            os.getenv("DISCOVER_DISMISS_SUPPRESSION_DAYS", "14")
        ),
        "stale_no_movement_days": float(
            os.getenv("DISCOVER_STALE_NO_MOVEMENT_DAYS", "2")
        ),
        "no_resolution_stale_days": float(
            os.getenv("DISCOVER_NO_RESOLUTION_STALE_DAYS", "5")
        ),
    }


async def _load_discover_runtime_config() -> dict[str, float | bool]:
    config = _discover_runtime_config_defaults()
    try:
        from app.tasks.redis_state import get_async_redis_client

        redis = get_async_redis_client()
        raw = await redis.hgetall("bainluck:discover_runtime_config")
        decoded = {
            (k.decode() if isinstance(k, bytes) else k): (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in raw.items()
        }
        if "interaction_suppression_enabled" in decoded:
            config["interaction_suppression_enabled"] = (
                decoded["interaction_suppression_enabled"].lower() == "true"
            )
        for key in (
            "seen_suppression_hours",
            "dismiss_suppression_days",
            "stale_no_movement_days",
            "no_resolution_stale_days",
        ):
            if key in decoded:
                config[key] = float(decoded[key])
    except Exception:
        pass
    return config


@router.post("/interactions")
async def record_discover_interactions(
    request: Request,
    body: DiscoverInteractionBatch,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db_rw),
):
    """Record web/native Discover engagement events for ranking diagnostics."""
    user_id = user.id if user else None
    session_id = _session_id_from_request(request)
    discover_config = await _load_discover_runtime_config()

    rows = []
    for event in body.interactions:
        action = _normalize_discover_value(
            event.action, _DISCOVER_ACTIONS, "impression"
        )
        item_type = _normalize_discover_value(
            event.item_type, _DISCOVER_ITEM_TYPES, "futures"
        )
        surface = _normalize_discover_value(
            event.surface, _DISCOVER_SURFACES, "unknown"
        )
        category = (event.category or "other").strip().lower()[:80] or "other"
        rows.append(
            DiscoverInteraction(
                user_id=user_id,
                session_id=session_id,
                surface=surface,
                action=action,
                item_type=item_type,
                item_id=str(event.item_id)[:100],
                category=category,
                item_name=event.item_name[:300] if event.item_name else None,
                score=event.score,
                rank=event.rank,
                source=event.source[:50] if event.source else None,
            )
        )

    maybe_add = db.add_all(rows)
    if inspect.isawaitable(maybe_add):
        await maybe_add
    await db.commit()
    return {"status": "ok", "recorded": len(rows)}


_TRACE_STOPWORDS = {
    "will",
    "what",
    "when",
    "which",
    "with",
    "from",
    "that",
    "this",
    "before",
    "after",
    "market",
    "winner",
    "yes",
    "no",
    "the",
    "and",
    "win",
    "wins",
    "won",
}
_DEDUP_NAME_STOPWORDS = _TRACE_STOPWORDS | {
    "who",
    "does",
    "have",
    "than",
    "then",
    "into",
    "onto",
    "over",
    "under",
    "above",
    "below",
    "between",
    "next",
    "last",
    "end",
    "start",
    "season",
    "year",
    "month",
    "week",
    "day",
    "date",
    "2024",
    "2025",
    "2026",
    "2027",
    "2028",
    "2029",
    "2030",
}

DISCOVER_SPORTS_CATEGORIES = (
    "basketball",
    "football",
    "baseball",
    "hockey",
    "soccer",
    "golf",
    "mma",
    "boxing",
    "tennis",
    "cricket",
    "motorsports",
    "esports",
    "rugby",
    "lacrosse",
)

# Editorial recall patterns — canonical list lives in
# app.utils.editorial_patterns. Polling tasks precompute
# `is_editorial_recall` at ingest time; feed queries the column.

_DISCOVER_SPORTS_EDITORIAL_RECALL_PATTERNS = (
    "%fifa world cup%",
    "%world cup%",
    "%champions league%",
    "%super bowl%",
    "%nba finals%",
    "%stanley cup%",
    "%world series%",
    # Grand Slam tennis
    "%wimbledon%",
    "%french open%",
    "%us open%",
    "%australian open%",
    "%roland garros%",
    "%grand slam%",
    # UFC/MMA major events
    "%ufc%",
    "%title fight%",
    "%title bout%",
)


def _discover_editorial_recall_filter():
    """SQL filter for high-texture Discover candidates that can be low volume.

    Uses the precomputed `is_editorial_recall` column set at polling time,
    replacing the old 44-ILIKE scan.
    """
    return FuturesMarket.is_editorial_recall.is_(True)


async def _get_editorial_recall_ids(db) -> list[int]:
    """Get editorial recall market IDs using precomputed column.

    Polling tasks set `is_editorial_recall=True` at ingest time so this
    is a simple indexed boolean filter instead of the old 44-ILIKE scan.
    """
    result = await db.execute(
        select(FuturesMarket.id).where(
            FuturesMarket.status.in_(["open", "active"]),
            FuturesMarket.is_editorial_recall.is_(True),
        )
    )
    return [r[0] for r in result.all()]


def _discover_sports_editorial_recall_filter():
    """SQL filter for sports futures that are broad enough for Discover."""
    return or_(
        *(
            FuturesMarket.name.ilike(pattern)
            for pattern in _DISCOVER_SPORTS_EDITORIAL_RECALL_PATTERNS
        )
    )


async def _external_curator_recall_market_ids(
    db: AsyncSession,
    base_filters: list,
    *,
    row_limit: int = 80,
    market_limit: int = 80,
) -> list[int]:
    """Find feed-eligible markets matching accepted external-curator rows.

    This is intentionally only a candidate-pool recall lane. Matched markets
    still pass through normal scoring, quality caps, personalization, and final
    diversity; social rows do not directly boost rank.
    """
    curator_result = await db.execute(
        select(ExternalCuratorGroundTruthItem.name)
        .where(
            ExternalCuratorGroundTruthItem.review_status.in_(
                ("accepted", "approved", "reviewed")
            )
        )
        .order_by(ExternalCuratorGroundTruthItem.imported_at.desc())
        .limit(row_limit)
    )
    names = [str(name or "").strip() for name in curator_result.scalars().all()]
    clauses = []
    for name in names:
        if not name:
            continue
        tokens = _trace_search_tokens(name)
        clauses.append(FuturesMarket.name.ilike(f"%{name[:120]}%"))
        if tokens:
            clauses.append(
                and_(*[FuturesMarket.name.ilike(f"%{token}%") for token in tokens[:3]])
            )
    if not clauses:
        return []

    market_result = await db.execute(
        select(FuturesMarket.id)
        .where(*base_filters, or_(*clauses))
        .order_by(
            FuturesMarket.market_tier.asc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
            FuturesMarket.updated_at.desc().nulls_last(),
        )
        .limit(market_limit)
    )
    return list(market_result.scalars().all())


# Sport keys allowed in My Stuff feed (Tier 1 + Tier 2 from SPORT_POLLING_TIERS).
# Excludes Tier 3 sports (NCAA hockey, esports, minor soccer leagues, etc.) that
# cause false positives — e.g., a Red Sox follower seeing "Boston College" hockey
# or "Boston Breach" esports. Bug reports BR42/BR43.
MY_STUFF_ALLOWED_SPORT_KEYS = {
    # Tier 1 — core US sports
    "basketball_nba",
    "basketball_ncaab",
    "icehockey_nhl",
    "baseball_mlb",
    "americanfootball_nfl",
    # Tier 2 — secondary
    "basketball_wnba",
    "americanfootball_ncaaf",
    "soccer_epl",
    "soccer_usa_mls",
    "soccer_uefa_champs_league",
    "mma_mixed_martial_arts",
}

# LLM sport categories corresponding to MY_STUFF_ALLOWED_SPORT_KEYS.
# Used for futures filtering where sport_key isn't directly available.
MY_STUFF_ALLOWED_CATEGORIES = {
    "basketball",
    "football",
    "baseball",
    "hockey",
    "soccer",
    "mma",
}

_SPORTS_POSTSEASON_SQL_FILTER = and_(
    FuturesMarket.llm_sport_category.in_(
        ("basketball", "football", "baseball", "hockey")
    ),
    or_(
        FuturesMarket.name.like("%NBA Finals%"),
        FuturesMarket.name.like("%WNBA Finals%"),
        FuturesMarket.name.like("%Stanley Cup%"),
        FuturesMarket.name.like("%World Series%"),
        FuturesMarket.name.like("%Super Bowl%"),
    ),
    or_(
        FuturesMarket.name.ilike("%advance%"),
        FuturesMarket.name.ilike("%reach%"),
        FuturesMarket.name.ilike("%make%"),
        FuturesMarket.name.ilike("%win%"),
        FuturesMarket.name.ilike("%winner%"),
    ),
)


def _trace_search_tokens(name: str) -> list[str]:
    tokens = [
        t.lower()
        for t in re.findall(r"[A-Za-z][A-Za-z0-9']{2,}", name)
        if t.lower() not in _TRACE_STOPWORDS
    ]
    deduped: list[str] = []
    for token in tokens:
        if token not in deduped:
            deduped.append(token)
    return deduped[:4]


def _futures_market_id(item: dict) -> int | None:
    if item.get("type") != "futures":
        return None
    data = item.get("data") or {}
    return data.get("id")


def _rank_futures_market(items: list[dict], market_id: int) -> int | None:
    for idx, item in enumerate(items, start=1):
        if _futures_market_id(item) == market_id:
            return idx
    return None


_DISCOVER_EVENT_EXCEPTION_KEYWORDS = (
    "elimination",
    "buzzer",
    "walk-off",
    "historic",
    "upset",
    "comeback",
    "playoff",
    "championship",
)


def _discover_event_ei_score(item: dict) -> float:
    data = item.get("data") or {}
    ei = data.get("ei") or data.get("pulse")
    if isinstance(ei, dict):
        raw_score = ei.get("score", 0)
    else:
        raw_score = ei or 0
    try:
        return float(raw_score)
    except (TypeError, ValueError):
        return 0.0


def _discover_event_has_major_league_context(item: dict) -> bool:
    data = item.get("data") or {}
    sport_key = data.get("sport") or data.get("sport_key")
    if sport_key and get_league_tier(sport_key) <= 2:
        return True
    event_tags = data.get("event_tags") or []
    return "tier:1" in event_tags or "tier:2" in event_tags


def _is_discover_event_demotion_exception(item: dict) -> bool:
    """Return whether a Discover-mode event should keep its original score.

    A live sports event earns a Discover slot only if:
    1. The game is genuinely wild (EI ≥ 85)
    2. It's a major league AND the game is exciting (EI ≥ 80)
    3. It's a playoff/championship/elimination game in a major league
    4. The headline signals something extraordinary (walk-off, buzzer beater)

    Routine live games — even in major leagues — belong on Sports, not Discover.
    A generic NBA regular season game at EI 70 should not outrank "Who will be
    the next James Bond?" for a general audience.
    """
    if item.get("type") != "event":
        return False

    ei_score = _discover_event_ei_score(item)
    has_major_league_context = _discover_event_has_major_league_context(item)

    if ei_score >= 85:
        return True
    if ei_score >= 80 and has_major_league_context:
        return True

    headline = (item.get("headline") or "").lower()
    has_high_drama_keyword = any(
        kw in headline for kw in ("elimination", "buzzer", "walk-off", "historic")
    )
    if has_high_drama_keyword and has_major_league_context:
        return True

    has_postseason_keyword = any(
        kw in headline for kw in ("playoff", "championship", "finals")
    )
    if has_postseason_keyword and has_major_league_context and ei_score >= 60:
        return True

    return False


def _demote_non_exceptional_discover_events(feed_items: list[dict]) -> None:
    for item in feed_items:
        if item.get("type") != "event":
            continue
        if not _is_discover_event_demotion_exception(item):
            item["score"] = min(item["score"], 35)


def _filter_discover_event_noise(feed_items: list[dict]) -> list[dict]:
    """Remove routine game cards from Discover mode after demotion.

    Discover is not the sports scoreboard. Completed games, obscure no-logo
    live games, and ordinary low-score events should stay on Sports/My Stuff,
    not take slots from prediction-market stories.
    """
    filtered: list[dict] = []
    for item in feed_items:
        if item.get("type") != "event":
            filtered.append(item)
            continue

        data = item.get("data") or {}
        status = (data.get("status") or "").lower()
        if status in {"completed", "closed"}:
            continue

        if item.get("score", 0) < 45 and not _is_discover_event_demotion_exception(
            item
        ):
            continue

        has_team_media = bool(data.get("home_team_data") or data.get("away_team_data"))
        if not has_team_media and not _is_discover_event_demotion_exception(item):
            continue

        filtered.append(item)
    return filtered


def _should_skip_futures_for_recent_dismissal(
    *,
    market,
    quality=None,
    ctx: PersonalizationContext,
    my_teams_only: bool,
) -> bool:
    """Propagate recent negative feedback across grouped/story-related futures."""
    if my_teams_only:
        return False

    if (
        ctx.recent_dismissed_group_ids
        and getattr(market, "group_id", None)
        and str(market.group_id) in ctx.recent_dismissed_group_ids
    ):
        return True

    return bool(
        quality
        and ctx.recent_dismissed_story_keys
        and quality.story_key
        and quality.story_key in ctx.recent_dismissed_story_keys
    )


def _dedupe_futures_by_group_id(futures_items: list[dict]) -> list[dict]:
    """Deduplicate futures by group_id, keeping the highest-scoring per group.

    Polymarket sub-markets sharing a group_id (e.g., 10 nominee markets for
    "Who wins Best Picture?") should appear as one card, not 10.  Markets
    without a group_id pass through unchanged.
    """
    sorted_items = sorted(
        futures_items,
        key=lambda x: (x.get("score", 0), x.get("_sort_time", 0)),
        reverse=True,
    )
    survivor_by_group: dict[str, dict] = {}
    kept: list[dict] = []
    for item in sorted_items:
        data = item.get("data") or {}
        group_id = data.get("group_id")
        if group_id is not None:
            gid_str = str(group_id)
            survivor = survivor_by_group.get(gid_str)
            if survivor is not None:
                # Preserve the dropped same-group sibling on the surviving card
                # under a private key so the Discover-mode awards theme bundler
                # (assemble_awards_theme_bundles) can reconstruct the full race.
                # Stripped from the default-feed response in the serving path.
                survivor.setdefault("_grouped_members", []).append(item)
                continue
            survivor_by_group[gid_str] = item
        kept.append(item)
    return kept


def _dedupe_futures_by_canonical(futures_items: list[dict]) -> list[dict]:
    """Deduplicate futures by canonical key using the feed's existing rules."""
    seen_canonical: dict[str, dict] = {}
    deduped: list[dict] = []
    for fitem in futures_items:
        key = fitem["data"].get("canonical_market_key")
        if key is None or not _canonical_key_safe_for_dedupe(key):
            deduped.append(fitem)
            continue
        if key not in seen_canonical:
            seen_canonical[key] = fitem
        elif fitem["score"] > seen_canonical[key]["score"]:
            if _outcomes_overlap(seen_canonical[key], fitem):
                seen_canonical[key] = fitem
            else:
                deduped.append(fitem)
        else:
            if not _outcomes_overlap(seen_canonical[key], fitem):
                deduped.append(fitem)
    deduped.extend(seen_canonical.values())
    return deduped


def _canonical_key_safe_for_dedupe(key: str | None) -> bool:
    """Reject broad generated keys that are too weak for feed dedupe."""
    if not key:
        return False
    parts = key.split(":")
    if len(parts) < 4:
        return True
    sport, league, category, _season = parts[:4]
    sports_like_categories = {
        "baseball",
        "basketball",
        "football",
        "golf",
        "hockey",
        "mma",
        "olympics",
        "soccer",
        "tennis",
    }
    generic_market_categories = {"championship", "prediction", "other", "general"}
    return bool(
        league
        or sport in sports_like_categories
        or category not in generic_market_categories
    )


_EXTERNAL_CURATOR_RECALL_SCORE_BONUS = 25


def _apply_external_curator_recall_score(
    score: float,
    reasons: list[str],
    *,
    is_external_curator_recall: bool,
) -> float:
    """Give reviewed external-curator matches a bounded recall lift."""
    if not is_external_curator_recall:
        return score
    boosted = min(98, score + _EXTERNAL_CURATOR_RECALL_SCORE_BONUS)
    if boosted != score:
        delta = boosted - score
        delta_label: int | float = int(delta) if float(delta).is_integer() else delta
        reasons.append(f"external_curator_recall:+{delta_label}")
    return boosted


def _name_tokens_for_dedupe(name: str | None) -> set[str]:
    if not name:
        return set()
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9']{2,}", name)
        if token.lower() not in _DEDUP_NAME_STOPWORDS
    }


def _binary_names_compatible_for_dedupe(item_a: dict, item_b: dict) -> bool:
    """Prevent generic Yes/No outcomes from collapsing unrelated stories."""
    data_a = item_a.get("data", {})
    data_b = item_b.get("data", {})
    story_a = item_a.get("_quality_story_key")
    story_b = item_b.get("_quality_story_key")
    if story_a and story_b:
        return story_a == story_b

    tokens_a = _name_tokens_for_dedupe(data_a.get("name"))
    tokens_b = _name_tokens_for_dedupe(data_b.get("name"))
    if not tokens_a or not tokens_b:
        return True
    overlap = tokens_a & tokens_b
    smaller = min(len(tokens_a), len(tokens_b))
    return len(overlap) >= 2 or (smaller > 0 and len(overlap) / smaller >= 0.5)


def _ei_label(score: int) -> str:
    """Short EI label for feed display."""
    if score >= 90:
        return "Incredible"
    if score >= 81:
        return "Must-Watch"
    if score >= 71:
        return "Exciting"
    if score >= 61:
        return "Engaging"
    if score >= 51:
        return "Competitive"
    return "Steady"


# Backward-compatible alias
_pulse_label = _ei_label


@router.get("")
async def get_feed(
    response: Response,
    request: Request,
    limit: int = Query(
        200, description="Number of feed items to return", ge=1, le=5000
    ),
    offset: int = Query(0, description="Offset for pagination", ge=0),
    sport: Optional[str] = Query(
        None, description="Filter by sport category (e.g., basketball, football)"
    ),
    include_events: bool = Query(True, description="Include game events in feed"),
    include_futures: bool = Query(True, description="Include futures markets in feed"),
    my_teams_only: bool = Query(
        False, description="Filter to only the user's followed teams"
    ),
    mode: Optional[str] = Query(
        None,
        description=(
            "Feed mode: 'discover' (default) runs full editorial scoring; "
            "'sports' skips expensive Discover pools and returns events + "
            "top sports futures sorted by tier/volume, 10x faster."
        ),
    ),
    tags: Optional[str] = Query(
        None,
        description='Filter by taxonomy tags (JSON array, e.g., ["sport:basketball"])',
    ),
    event_pct: Optional[float] = Query(
        None,
        description="Override event percentage floor (0.0-1.0). Discover uses 0.15.",
    ),
    debug: bool = Query(
        False, description="Include admin-only feed quality diagnostics"
    ),
    debug_ground_truth: bool = Query(
        True,
        description=(
            "When debug=true, include slower ground-truth recall diagnostics. "
            "Disable for fast admin labeling/debug-card loads."
        ),
    ),
    debug_personalization: bool = Query(
        False,
        description=(
            "When debug=true, keep authenticated personalization/seen state. "
            "Default debug mode is global for admin labeling."
        ),
    ),
    exclude_reviewed: bool = Query(
        False,
        description=(
            "Admin/debug labeling helper: exclude cards already present in "
            "ranking_judgments for the reviewer/surface."
        ),
    ),
    reviewer: Optional[str] = Query(
        None,
        description="Reviewer key used when exclude_reviewed=true.",
    ),
    reviewed_surface: Optional[str] = Query(
        None,
        description="Optional ranking_judgments surface filter for reviewed exclusion.",
    ),
    secret: Optional[str] = Query(
        None, description="Admin secret for debug diagnostics"
    ),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """
    Get a unified ranked feed of interesting events and futures.

    When authenticated, scores are personalized based on:
    - Favorite teams (follow, local, alma_mater, rival relationships)
    - Sport affinities (boost/suppress by sport preference)
    - Pinned items (boosted in feed)
    - Rival schadenfreude (rival losing = extra boost)

    Returns a single list where each item has:
    - type: "event" or "futures"
    - score: 0-100 interestingness (personalized if authenticated)
    - reason: human-readable explanation
    - headline: short label for badges
    - data: full event or futures payload
    - personalized: whether score was personalized (only present if true)
    """
    _started_at = time.perf_counter()
    _previous_at = _started_at
    _timings: list[dict[str, float | str]] = []

    if (debug or exclude_reviewed) and not await _check_admin_auth(secret, request, db):
        _set_feed_timing_header(response, _started_at)
        raise HTTPException(status_code=403, detail="Admin access required")

    session_id = _session_id_from_request(request)
    debug_global = debug and not debug_personalization and not my_teams_only
    feed_user = None if debug_global else user
    feed_session_id = None if debug_global else session_id
    discover_config = await _load_discover_runtime_config()
    if debug:
        discover_config = {
            **discover_config,
            "interaction_suppression_enabled": False,
        }

    # --- Redis response cache (anon 15s, auth 5s, my_teams 30s) ---
    _cache_key = None
    # Session/user feeds change as impressions are recorded. Keep anonymous
    # no-session cache warmer, but make per-session Discover refreshes respond
    # quickly to "already seen" suppression.
    _cache_ttl = 30 if my_teams_only else (5 if (feed_user or feed_session_id) else 60)
    _async_redis = None
    _cache_status = "disabled"
    if not debug and not exclude_reviewed:
        _cache_status = "miss"
        try:
            from app.tasks.redis_state import get_async_redis_client

            _async_redis = get_async_redis_client()
            _user_part = (
                f"u:{feed_user.id}"
                if feed_user
                else f"s:{feed_session_id}" if feed_session_id else "anon"
            )
            _parts = f"feed:{_user_part}:{sport or 'all'}:{limit}:{offset}:{include_events}:{include_futures}:{tags or ''}:{event_pct or ''}:{my_teams_only}:{mode or 'discover'}"
            _cache_key = f"feed_cache:{hashlib.md5(_parts.encode()).hexdigest()}"
            cached = await _async_redis.get(_cache_key)
            if cached:
                await _async_redis.aclose()
                payload = _json_module.loads(cached)
                if isinstance(payload, dict):
                    payload["cache"] = build_feed_cache_metadata(
                        "hit",
                        ttl_seconds=_cache_ttl,
                    )
                _previous_at = _record_feed_timing(
                    _timings, _started_at, _previous_at, "cache_hit"
                )
                _set_feed_cache_status(response, "hit")
                _set_feed_timing_header(response, _started_at)
                return payload
            # Stale fallback: serve old data if primary cache expired
            _stale_key = f"{_cache_key}:stale"
            stale = await _async_redis.get(_stale_key)
            if stale:
                await _async_redis.aclose()
                payload = _json_module.loads(stale)
                if isinstance(payload, dict):
                    payload["cache"] = build_feed_cache_metadata(
                        "stale_hit",
                        ttl_seconds=_cache_ttl,
                    )
                _previous_at = _record_feed_timing(
                    _timings, _started_at, _previous_at, "cache_stale_hit"
                )
                _set_feed_cache_status(response, "stale_hit")
                _set_feed_timing_header(response, _started_at)
                return payload
        except Exception:
            _cache_key = None
            _cache_status = "error"
    elif debug:
        _cache_status = "disabled_debug"
    elif exclude_reviewed:
        _cache_status = "disabled_reviewed_filter"

    now = datetime.now(timezone.utc)

    # Parse tag filter — split into static (SQL-pushable) and dynamic (inline)
    import json as _json

    tag_filter: Optional[list[str]] = None
    static_tag_filter: list[str] = (
        []
    )  # Tags that don't change: sport, league, tier, class, level, gender, category, source
    dynamic_tag_filter: list[str] = (
        []
    )  # Tags that change frequently: status, signal, timing, ei, importance
    STATIC_NAMESPACES = {
        "sport",
        "league",
        "tier",
        "class",
        "level",
        "gender",
        "category",
        "source",
    }
    if tags:
        try:
            tag_filter = _json.loads(tags)
            if not isinstance(tag_filter, list):
                tag_filter = None
            else:
                for t in tag_filter:
                    ns = t.split(":")[0] if ":" in t else ""
                    if ns in STATIC_NAMESPACES:
                        static_tag_filter.append(t)
                    else:
                        dynamic_tag_filter.append(t)
        except (ValueError, TypeError):
            tag_filter = None

    # my_teams_only requires authentication
    if my_teams_only and not feed_user:
        _set_feed_timing_header(response, _started_at)
        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "has_more": False,
            "my_teams_only": True,
            "requires_auth": True,
        }

    # Load personalization context (one DB query for all user data)
    try:
        ctx = await _load_personalization_context(
            db,
            feed_user,
            session_id=feed_session_id,
            config=discover_config,
        )
    except Exception:
        logger.exception("Personalization context failed — falling back to anonymous")
        ctx = PersonalizationContext()
    _previous_at = _record_feed_timing(
        _timings, _started_at, _previous_at, "personalization"
    )

    # Build team name set once (used by both scoring functions + response).
    # Only uses Team.name (full ESPN display name like "Brown Bears"), NOT
    # alternate_names (short forms like "Bears", "Brown") which cause false
    # positives: "bears" matching "chicago bears", "brown" matching "browns".
    my_team_names: list[str] = []
    # Map team name -> set of sport categories the user follows that team in.
    # Used by futures matching (BR53) to prevent cross-sport false positives
    # like "Aliya Boston" (WNBA) matching "Boston Bruins" (NHL).
    my_team_sport_categories: dict[str, set[str]] = {}
    if my_teams_only and feed_user and ctx.team_relations:
        team_ids = list(ctx.team_relations.keys())
        team_name_result = await db.execute(
            select(Team.name, Sport.key)
            .where(Team.id.in_(team_ids))
            .join(Sport, Team.sport_id == Sport.id)
        )
        for name, sport_key in team_name_result.all():
            if name:
                my_team_names.append(name)
                cat = _personalization_category_from_sport_key(sport_key)
                if cat:
                    my_team_sport_categories.setdefault(name, set()).add(cat)

    feed_items = []

    # === SCORE EVENTS ===
    if include_events:
        try:
            event_items = await _score_events(
                db,
                now,
                sport,
                ctx,
                my_teams_only=my_teams_only,
                my_team_names=my_team_names,
                tag_filter=dynamic_tag_filter or None,
                static_tag_filter=static_tag_filter or None,
            )
            feed_items.extend(event_items)
        except Exception as e:
            logger.error("Feed: event scoring failed, returning partial feed: %s", e)
    _previous_at = _record_feed_timing(_timings, _started_at, _previous_at, "events")

    # === ENRICH EVENTS WITH TEAM DATA ===
    # _build_team_lookup is cached in-memory (5-min TTL, ~500 teams) — essentially free.
    if feed_items:
        all_team_names = []
        for item in feed_items:
            if item["type"] == "event":
                d = item["data"]
                all_team_names.append(d["home_team"])
                all_team_names.append(d["away_team"])
        if all_team_names:
            team_lookup = await _build_team_lookup(db, all_team_names)
            for item in feed_items:
                if item["type"] == "event":
                    d = item["data"]
                    home_team = team_lookup.get(d["home_team"])
                    away_team = team_lookup.get(d["away_team"])
                    if home_team:
                        d["home_team_data"] = _format_team_data(home_team)
                    if away_team:
                        d["away_team_data"] = _format_team_data(away_team)
    _previous_at = _record_feed_timing(
        _timings, _started_at, _previous_at, "team_enrichment"
    )

    # === SCORE GOLF TOURNAMENTS ===
    # Skip golf tournaments if a non-golf sport tag is active
    _skip_golf = not include_events
    if static_tag_filter:
        sport_tags = [t for t in static_tag_filter if t.startswith("sport:")]
        if sport_tags and "sport:golf" not in sport_tags:
            _skip_golf = True
    if not _skip_golf:
        try:
            tournament_items = await _score_golf_tournaments(db, now, sport, ctx)
            if tournament_items:
                feed_items.extend(tournament_items)
        except Exception as e:
            logger.error("Feed: golf scoring failed, returning partial feed: %s", e)
    _previous_at = _record_feed_timing(_timings, _started_at, _previous_at, "golf")

    # === SCORE FUTURES ===
    _is_sports_mode = (mode or "").lower() == "sports"
    if include_futures:
        try:
            if _is_sports_mode:
                # Sports mode: skip the expensive Discover scoring pipeline
                # (10 candidate pool queries + editorial recall + interestingness
                # cache). Instead, run a single fast query for top sports futures.
                futures_items = await _score_sports_mode_futures(
                    db,
                    now,
                    sport,
                    ctx,
                    my_teams_only=my_teams_only,
                    my_team_names=my_team_names,
                    my_team_sport_categories=my_team_sport_categories,
                )
            else:
                futures_items = await _score_futures(
                    db,
                    now,
                    sport,
                    ctx,
                    my_teams_only=my_teams_only,
                    my_team_names=my_team_names,
                    my_team_sport_categories=my_team_sport_categories,
                    tag_filter=dynamic_tag_filter or None,
                    static_tag_filter=static_tag_filter or None,
                    timing_records=_timings,
                    timing_started_at=_started_at,
                    config=discover_config,
                )

            feed_items.extend(_dedupe_futures_by_canonical(futures_items))
        except Exception as e:
            logger.error(
                "Feed: futures scoring failed, returning partial feed: %s",
                e,
                exc_info=True,
            )
            import sentry_sdk

            sentry_sdk.capture_exception(e)
    _previous_at = _record_feed_timing(_timings, _started_at, _previous_at, "futures")

    await _apply_manual_review_decisions(db, feed_items)
    _previous_at = _record_feed_timing(
        _timings, _started_at, _previous_at, "review_decisions"
    )

    # === RANK AND PAGINATE ===
    # Sort by score descending, then by recency as tiebreaker
    feed_items.sort(key=lambda x: (x["score"], x.get("_sort_time", 0)), reverse=True)

    # === DIVERSITY GUARANTEE ===
    # Ensure the feed has a mix of events and futures.
    # Without this, futures can dominate (they get "resolving soon" + "multi source"
    # bonuses that events don't have).
    # For anonymous users, enforce a stronger event bias (events are the core product).
    # Skip diversity enforcement for my_teams_only — show everything matching.
    # When event_pct is low (Discover mode), demote ordinary events so
    # interesting futures can compete. A routine playoff game scores 100
    # from live+close+tier but isn't more interesting than "Will China
    # invade Taiwan?" for a Discover audience. Only truly exceptional
    # events (strong EI or top-tier exception keywords) keep their score.
    if event_pct is not None and event_pct < 0.3:
        _demote_non_exceptional_discover_events(feed_items)
        feed_items = _filter_discover_event_noise(feed_items)
        # Re-sort after demotion so demoted events fall below high-scoring futures
        feed_items.sort(
            key=lambda x: (x["score"], x.get("_sort_time", 0)), reverse=True
        )
        feed_items = balance_discover_event_category_mix(feed_items)

    if not my_teams_only:
        if event_pct is not None and event_pct < 0.2:
            pass  # Discover mode: let scores decide, no artificial event promotion
        else:
            _epct = 0.6 if not ctx.is_authenticated else 0.4
            feed_items = _ensure_feed_diversity(feed_items, limit, event_pct=_epct)

    if not my_teams_only and (
        (event_pct is not None and event_pct < 0.3) or not include_events
    ):
        _is_cold_start = not ctx.discover_category_affinities
        feed_items = diversify_discover_first_page(
            feed_items, first_page_size=min(20, limit),
            cold_start=_is_cold_start,
        )
        feed_items = backfill_discover_editorial_tail(
            feed_items,
            window_size=min(50, len(feed_items)),
            preserve_top=min(20, len(feed_items)),
        )
    _previous_at = _record_feed_timing(_timings, _started_at, _previous_at, "ranking")

    reviewed_filter = None
    if exclude_reviewed:
        # Resolve reviewer: when "native" and authenticated via Bearer token,
        # use the admin's email for per-user reviewed state.
        effective_reviewer = reviewer
        if reviewer == "native":
            admin_email = await _resolve_admin_email(request, db)
            if admin_email:
                effective_reviewer = admin_email

        reviewed_keys = await _load_reviewed_ranking_keys(
            db,
            reviewer=effective_reviewer,
            surface=reviewed_surface,
        )
        feed_items, reviewed_filtered_count = _filter_reviewed_feed_items(
            feed_items,
            reviewed_keys,
        )
        reviewed_filter = {
            "enabled": True,
            "reviewer": effective_reviewer,
            "surface": reviewed_surface,
            "reviewed_key_count": len(reviewed_keys),
            "filtered_count": reviewed_filtered_count,
        }
    _previous_at = _record_feed_timing(
        _timings, _started_at, _previous_at, "reviewed_filter"
    )

    if not my_teams_only and (
        (event_pct is not None and event_pct < 0.3) or not include_events
    ):
        feed_items = assemble_discover_comparison_bundles(feed_items)
        feed_items = assemble_geopolitics_theme_bundles(feed_items)
        feed_items = assemble_awards_theme_bundles(feed_items)
    _previous_at = _record_feed_timing(_timings, _started_at, _previous_at, "bundles")

    total = len(feed_items)
    paginated = feed_items[offset : offset + limit]

    debug_payload = None
    if debug:
        email_ground_truth_items: list[dict] = []
        external_curator_items: list[dict] = []
        ground_truth_items = load_default_ground_truth_items()
        if debug_ground_truth:
            email_ground_truth_report = await asyncio.to_thread(
                load_polymarket_email_ground_truth_report_from_env,
                now=now,
            )
            external_curator_report = await asyncio.to_thread(
                load_external_curator_ground_truth_report_from_env,
                now=now,
            )
            persisted_external_curator_report = (
                await load_persisted_external_curator_ground_truth_report(db, now=now)
            )
            external_curator_report = merge_external_curator_ground_truth_reports(
                [external_curator_report, persisted_external_curator_report],
                now=now,
            )
            email_ground_truth_items = email_ground_truth_report["items"]
            external_curator_items = external_curator_report["items"]
            ground_truth_items = (
                ground_truth_items + email_ground_truth_items + external_curator_items
            )
        debug_payload = build_feed_quality_debug(
            paginated,
            ground_truth_items=ground_truth_items,
            top_n=min(20, len(paginated)),
        )
        if debug_ground_truth:
            await _attach_missing_ground_truth_traces(
                db, debug_payload["missing_ground_truth"], now
            )
            debug_payload["missing_ground_truth_summary"] = (
                apply_db_trace_missing_ground_truth_triage(
                    debug_payload["missing_ground_truth"]
                )
            )
            email_missing_ground_truth = find_missing_ground_truth_items(
                debug_payload["items"],
                email_ground_truth_items,
                limit=80,
            )
            await _attach_missing_ground_truth_traces(
                db, email_missing_ground_truth, now
            )
            email_missing_ground_truth_summary = (
                apply_db_trace_missing_ground_truth_triage(email_missing_ground_truth)
            )
            email_metadata = email_ground_truth_report["metadata"]
            email_summary = summarize_polymarket_email_ground_truth(
                debug_payload["items"],
                email_ground_truth_items,
            )
            debug_payload["email_ground_truth"] = {
                **email_metadata,
                "total": email_summary["total"],
                "top20_hits": email_summary["top20_hits"],
                "top50_hits": email_summary["top50_hits"],
                "missing": email_summary["missing"],
                "hit_rate_50": email_summary["hit_rate_50"],
                "hits": email_summary["hits"][:20],
                "missing_items": email_summary["missing_items"][:50],
                "db_trace_bucket_counts": email_missing_ground_truth_summary[
                    "bucket_counts"
                ],
            }
            debug_payload["email_ground_truth_misses"] = email_missing_ground_truth
            external_curator_missing = find_missing_ground_truth_items(
                debug_payload["items"],
                external_curator_items,
                limit=80,
            )
            await _attach_missing_ground_truth_traces(db, external_curator_missing, now)
            external_curator_missing_summary = (
                apply_db_trace_missing_ground_truth_triage(external_curator_missing)
            )
            external_summary = summarize_polymarket_email_ground_truth(
                debug_payload["items"],
                external_curator_items,
            )
            debug_payload["external_curator_ground_truth"] = {
                **external_curator_report["metadata"],
                "total": external_summary["total"],
                "top20_hits": external_summary["top20_hits"],
                "top50_hits": external_summary["top50_hits"],
                "missing": external_summary["missing"],
                "hit_rate_50": external_summary["hit_rate_50"],
                "hits": external_summary["hits"][:20],
                "missing_items": external_summary["missing_items"][:50],
                "db_trace_bucket_counts": external_curator_missing_summary[
                    "bucket_counts"
                ],
            }
            debug_payload["external_curator_ground_truth_misses"] = (
                external_curator_missing
            )
        else:
            empty_ground_truth = {
                "total": 0,
                "top20_hits": 0,
                "top50_hits": 0,
                "missing": 0,
                "hit_rate_50": 0,
                "hits": [],
                "missing_items": [],
                "db_trace_bucket_counts": {},
                "skipped": True,
            }
            debug_payload["email_ground_truth"] = empty_ground_truth
            debug_payload["email_ground_truth_misses"] = []
            debug_payload["external_curator_ground_truth"] = empty_ground_truth
            debug_payload["external_curator_ground_truth_misses"] = []
    _previous_at = _record_feed_timing(_timings, _started_at, _previous_at, "debug")

    # Remove internal sort/debug keys
    for item in paginated:
        item.pop("_sort_time", None)
        item.pop("_quality_class", None)
        item.pop("_quality_family_key", None)
        item.pop("_quality_story_key", None)
        item.pop("_review_decision", None)
        item.pop("_review_decision_scope", None)
        item.pop("_review_decision_scope_key", None)
        item.pop("_review_decision_penalty", None)
        item.pop("_grouped_members", None)

    payload = {
        "items": paginated,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }

    if my_teams_only:
        payload["my_teams_only"] = True
        if my_team_names:
            payload["matched_teams"] = my_team_names

    # Include personalization metadata if authenticated
    if ctx.is_authenticated:
        payload["personalized"] = True
        payload["personalization"] = {
            "team_count": len(ctx.team_relations),
            "sport_affinities_count": len(ctx.sport_affinities),
            "discover_category_affinities_count": len(ctx.discover_category_affinities),
            "pinned_events": len(ctx.pinned_event_ids),
            "pinned_futures": len(ctx.pinned_futures_ids),
        }

    if debug_payload is not None:
        payload["debug_global"] = debug_global
        if reviewed_filter is not None:
            payload["reviewed_filter"] = reviewed_filter
        payload["debug_summary"] = debug_payload["summary"]
        payload["debug_items"] = debug_payload["items"]
        payload["missing_ground_truth"] = debug_payload["missing_ground_truth"]
        payload["missing_ground_truth_summary"] = debug_payload[
            "missing_ground_truth_summary"
        ]
        payload["email_ground_truth"] = debug_payload["email_ground_truth"]
        payload["email_ground_truth_misses"] = debug_payload[
            "email_ground_truth_misses"
        ]
        payload["external_curator_ground_truth"] = debug_payload[
            "external_curator_ground_truth"
        ]
        payload["external_curator_ground_truth_misses"] = debug_payload[
            "external_curator_ground_truth_misses"
        ]
        payload["debug_timing"] = {
            "total_ms": round((time.perf_counter() - _started_at) * 1000, 2),
            "stages": _timings,
        }

    payload["cache"] = build_feed_cache_metadata(
        _cache_status,
        ttl_seconds=_cache_ttl if _cache_key else None,
        stale_ttl_seconds=(
            FEED_RESPONSE_STALE_TTL_SECONDS
            if _cache_key or _cache_status == "miss"
            else None
        ),
    )

    # --- Write to cache ---
    if _cache_key and _async_redis:
        try:
            _payload_json = _json_module.dumps(payload, default=str)
            await _async_redis.setex(_cache_key, _cache_ttl, _payload_json)
            await _async_redis.setex(
                f"{_cache_key}:stale",
                FEED_RESPONSE_STALE_TTL_SECONDS,
                _payload_json,
            )
            await _async_redis.aclose()
        except Exception:
            pass

    _set_feed_cache_status(response, _cache_status)
    _set_feed_timing_header(response, _started_at)
    return payload


def _apply_manual_review_decision_map(
    feed_items: list[dict],
    decisions: dict[tuple[str, str], str],
    scoped_decisions: dict[tuple[str, str], str] | None = None,
) -> None:
    """Apply bounded human review nudges recorded from the Discover admin page."""
    scoped_decisions = scoped_decisions or {}
    kept_items: list[dict] = []
    for item in feed_items:
        data = item.get("data") or {}
        item_id = data.get("id")
        if item_id is None:
            kept_items.append(item)
            continue

        item_type = str(item.get("type"))
        decision = decisions.get((item_type, str(item_id)))
        scope = "exact"
        scope_key = str(item_id)
        if decision is None:
            for candidate_scope in _review_decision_scope_keys(item):
                scoped = scoped_decisions.get((item_type, candidate_scope))
                if scoped:
                    decision = scoped
                    scope = "family"
                    scope_key = candidate_scope
                    break

        if decision in {"needs_design_fix", "needs_data_fix"}:
            item["_review_decision"] = decision
            item["_review_decision_scope"] = scope
            item["_review_decision_scope_key"] = scope_key
            continue
        if decision == "accepted_promote":
            if scope == "exact":
                item["score"] = min(98, float(item.get("score") or 0) + 8)
                item["_review_decision"] = decision
                item["_review_decision_scope"] = scope
                item["_review_decision_scope_key"] = scope_key
        elif decision == "accepted_downrank":
            penalty = 18 if scope == "exact" else 12
            item["score"] = max(0, float(item.get("score") or 0) - penalty)
            item["_review_decision"] = decision
            item["_review_decision_scope"] = scope
            item["_review_decision_scope_key"] = scope_key
            item["_review_decision_penalty"] = -penalty
        kept_items.append(item)
    feed_items[:] = kept_items


def _review_decision_scope_keys(item: dict) -> list[str]:
    """Return explicit non-exact review scopes for a feed item."""
    data = item.get("data") or {}
    keys: list[str] = []
    for key in (
        item.get("_quality_story_key"),
        item.get("_quality_family_key"),
    ):
        if key:
            keys.append(str(key))
    group_id = data.get("group_id")
    if group_id:
        keys.extend([str(group_id), f"group:{group_id}"])
    category = (
        data.get("llm_sport_category") or data.get("sport_name") or data.get("sport")
    )
    if category:
        keys.append(f"category:{str(category).lower()}")

    deduped: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


async def _apply_manual_review_decisions(
    db: AsyncSession,
    feed_items: list[dict],
) -> None:
    if not feed_items:
        return

    result = await db.execute(
        select(
            DiscoverReviewDecision.item_type,
            DiscoverReviewDecision.item_id,
            DiscoverReviewDecision.decision,
            DiscoverReviewDecision.family_key,
        )
        .where(
            DiscoverReviewDecision.decision.in_(
                [
                    "accepted_promote",
                    "accepted_downrank",
                    "needs_design_fix",
                    "needs_data_fix",
                ]
            )
        )
        .order_by(DiscoverReviewDecision.created_at.desc())
        .limit(1000)
    )
    decisions: dict[tuple[str, str], str] = {}
    scoped_decisions: dict[tuple[str, str], str] = {}
    for row in result.all():
        key = (str(row.item_type), str(row.item_id))
        if key not in decisions:
            decisions[key] = row.decision
        if row.family_key and row.decision != "accepted_promote":
            scope_key = (str(row.item_type), str(row.family_key))
            if scope_key not in scoped_decisions:
                scoped_decisions[scope_key] = row.decision
    _apply_manual_review_decision_map(feed_items, decisions, scoped_decisions)


async def _attach_missing_ground_truth_traces(
    db: AsyncSession,
    missing_items: list[dict],
    now: datetime,
) -> None:
    """Attach lightweight DB root-cause traces to missing ground-truth rows."""
    for item in missing_items:
        if item.get("triage_bucket") not in {
            "candidate_recall_gap",
            "ranking_too_low",
            "quality_filter_too_harsh",
        }:
            item["db_trace"] = summarize_missing_ground_truth_db_trace(
                item, [], now=now
            )
            continue

        tokens = _trace_search_tokens(item.get("name") or "")
        clauses = []
        if item.get("name"):
            clauses.append(FuturesMarket.name.ilike(f"%{item['name'][:120]}%"))
        if tokens:
            clauses.append(
                and_(*[FuturesMarket.name.ilike(f"%{token}%") for token in tokens[:3]])
            )
        if not clauses:
            item["db_trace"] = summarize_missing_ground_truth_db_trace(
                item, [], now=now
            )
            continue

        result = await db.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesMarket.source,
                FuturesMarket.status,
                FuturesMarket.event_id,
                FuturesMarket.llm_sport_category,
                FuturesMarket.market_tier,
                FuturesMarket.volume_24h,
                FuturesMarket.resolution_date,
                FuturesMarket.hook_description,
                FuturesMarket.image_url,
            )
            .where(or_(*clauses))
            .order_by(
                FuturesMarket.status.asc(),
                FuturesMarket.volume_24h.desc().nullslast(),
                FuturesMarket.updated_at.desc().nullslast(),
            )
            .limit(5)
        )
        matches = [
            {
                "id": row.id,
                "name": row.name,
                "source": row.source,
                "status": row.status,
                "event_id": row.event_id,
                "llm_sport_category": row.llm_sport_category,
                "market_tier": row.market_tier,
                "volume_24h": (
                    float(row.volume_24h) if row.volume_24h is not None else None
                ),
                "resolution_date": (
                    row.resolution_date.isoformat() if row.resolution_date else None
                ),
                "hook_description": row.hook_description,
                "image_url": row.image_url,
            }
            for row in result.all()
        ]
        item["db_trace"] = summarize_missing_ground_truth_db_trace(
            item, matches, now=now
        )


def _utc(dt: datetime | None) -> datetime | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


_SPORT_LABEL_MAP: dict[str, str] = {
    "americanfootball_nfl": "NFL",
    "americanfootball_ncaaf": "NCAAF",
    "basketball_nba": "NBA",
    "basketball_wnba": "WNBA",
    "basketball_ncaab": "NCAAB",
    "baseball_mlb": "MLB",
    "icehockey_nhl": "NHL",
    "soccer_epl": "EPL",
    "soccer_usa_mls": "MLS",
    "soccer_uefa_champs_league": "UCL",
    "golf_pga": "PGA",
    "tennis_atp": "ATP",
    "tennis_wta": "WTA",
    "mma_mixed_martial_arts": "MMA",
}


def _get_sport_label(sport_key: str | None) -> str | None:
    if not sport_key:
        return None
    if sport_key in _SPORT_LABEL_MAP:
        return _SPORT_LABEL_MAP[sport_key]
    parts = sport_key.split("_")
    if len(parts) >= 2:
        return parts[-1].upper()
    return sport_key.upper()


def _compute_temporal_badge(
    *,
    status: str | None = None,
    resolution_date: datetime | None = None,
    created_at: datetime | None = None,
    now: datetime,
) -> str | None:
    """Compute a temporal badge for a feed card.

    Returns one of "Live", "Closing Soon", "New", or None.
    - Live events/markets get "Live"
    - Resolution within 48 hours → "Closing Soon"
    - Market created within last 24 hours → "New"
    - Resolution > 30 days away → None (and frontend should hide the date)
    """
    normalized_status = (status or "").lower()
    if normalized_status in ("live", "in_progress"):
        return "Live"

    res_dt = _utc(resolution_date)
    if res_dt:
        hours_until = (res_dt - now).total_seconds() / 3600
        if 0 < hours_until <= 48:
            return "Closing Soon"

    created_dt = _utc(created_at)
    if created_dt:
        hours_since_created = (now - created_dt).total_seconds() / 3600
        if hours_since_created <= 24:
            return "New"

    return None


def _is_sports_market_category(sport_category: str | None) -> bool:
    category = (sport_category or "").lower()
    return category in DISCOVER_SPORTS_CATEGORIES or category in {
        "sports",
        "racing",
    }


def _effective_resolution_thresholds(sport_category: str | None) -> tuple[float, float]:
    """Return leader/current and opening thresholds for stale-feed suppression."""
    if _is_sports_market_category(sport_category):
        return 0.90, 0.70
    return 0.95, 0.85



from app.utils.market_staleness import (
    infer_market_real_world_end as _infer_market_real_world_end,
    is_title_implied_stale as _market_title_implied_stale_blocker,
)


def _market_base_trace(market: FuturesMarket, now: datetime) -> dict:
    blockers: list[str] = []
    if market.status != "open":
        blockers.append("not_open")
    if market.event_id is not None:
        blockers.append("event_linked_game_market")
    resolution_date = _utc(market.resolution_date)
    if resolution_date and resolution_date < now:
        blockers.append("past_resolution")
    title_stale_blocker = _market_title_implied_stale_blocker(
        market.name,
        getattr(market, "llm_sport_category", None),
        now,
    )
    if title_stale_blocker:
        blockers.append(title_stale_blocker)
    if re.search(r"\bvs\.?\b", market.name or "", re.IGNORECASE):
        blockers.append("game_name_filtered")

    return {
        "eligible": not blockers,
        "blockers": blockers,
        "checks": {
            "status": market.status,
            "event_id": market.event_id,
            "resolution_date": resolution_date.isoformat() if resolution_date else None,
            "would_be_title_implied_stale": bool(title_stale_blocker),
            "title_implied_stale_reason": title_stale_blocker,
            "game_name_filtered": bool(
                re.search(r"\bvs\.?\b", market.name or "", re.IGNORECASE)
            ),
        },
    }


def _normalize_feed_probabilities(
    top_outcomes: list[dict],
    all_sorted_outcomes: list,
) -> list[dict]:
    """Normalize feed-card probabilities for independent binary markets.

    Uses the sum across ALL outcomes (not just the displayed top N) to decide
    whether normalization is appropriate:

    - all_sum <= threshold  -> no normalization needed (already sane)
    - threshold < all_sum <= 2.0 -> independent binary markets (gotcha #58):
      divide each displayed outcome by all_sum so the slice shows correct
      *relative* standing without inflating to 100%.
    - all_sum > 2.0 -> threshold/cumulative outcomes (e.g. "rank 3+", "rank
      4+") that are NOT mutually exclusive.  Normalizing these flattens an
      81% leader to ~33%.  Skip entirely.
    """
    probs_top = [o for o in top_outcomes if o.get("probability")]
    if not probs_top:
        return top_outcomes

    # Two-outcome markets: stricter threshold (true binary)
    total_displayed = len(probs_top)
    norm_threshold = 1.01 if total_displayed == 2 else 1.05

    # Sum across ALL outcomes to gauge whether these are mutually exclusive
    all_sum = sum(
        float(o.current_probability)
        for o in all_sorted_outcomes
        if o.current_probability
    )

    if all_sum <= norm_threshold:
        # Probabilities already sum to ~100% — no normalization needed
        return top_outcomes

    if all_sum > 2.0:
        # Threshold / cumulative outcomes — do NOT normalize.
        # Raw probabilities are individually meaningful.
        return top_outcomes

    # Independent binary markets summing to 100-200%: normalize the displayed
    # outcomes using the all-outcome sum as divisor.
    for o in top_outcomes:
        if o.get("probability"):
            o["probability"] = round(o["probability"] / all_sum, 4)

    return top_outcomes


def _top_outcomes_for_trace(
    market: FuturesMarket,
) -> tuple[list[dict], str | None, float | None]:
    sorted_outcomes = sorted(
        market.outcomes,
        key=lambda o: (
            float(o.current_probability) if o.current_probability is not None else 0
        ),
        reverse=True,
    )
    outcomes_data = []
    for outcome in sorted_outcomes[:10]:
        outcomes_data.append(
            {
                "name": outcome.name,
                "probability": (
                    float(outcome.current_probability)
                    if outcome.current_probability is not None
                    else None
                ),
                "probability_change_24h": (
                    float(outcome.probability_change_24h)
                    if outcome.probability_change_24h is not None
                    else None
                ),
                "rank": outcome.rank,
                "rank_change_24h": outcome.rank_change_24h,
                "opening_probability": (
                    float(outcome.opening_probability)
                    if outcome.opening_probability is not None
                    else None
                ),
            }
        )

    leader_name = None
    leader_prob = None
    if sorted_outcomes:
        leader = sorted_outcomes[0]
        leader_name = leader.name
        leader_prob = (
            float(leader.current_probability)
            if leader.current_probability is not None
            else None
        )
    return outcomes_data, leader_name, leader_prob


def _market_runtime_filter_trace(
    market: FuturesMarket,
    outcomes_data: list[dict],
    leader_name: str | None,
    leader_prob: float | None,
    now: datetime,
    sport_category: str | None = None,
    *,
    stale_no_movement_days: float = 2,
    no_resolution_stale_days: float = 5,
) -> dict:
    blockers: list[str] = []

    # Past resolution date — market should have resolved already
    resolution_date = _utc(getattr(market, "resolution_date", None))
    if resolution_date and resolution_date < now:
        blockers.append("past_resolution_date")
    title_stale_blocker = _market_title_implied_stale_blocker(
        getattr(market, "name", None),
        sport_category,
        now,
    )
    if title_stale_blocker:
        blockers.append(title_stale_blocker)

    probs_available = [
        o["probability"] for o in outcomes_data if o["probability"] is not None
    ]
    all_settled = len(probs_available) >= 2 and all(
        p < 0.05 or p > 0.95 for p in probs_available
    )
    if all_settled:
        blockers.append("all_outcomes_settled")
    if leader_prob is not None and leader_prob >= 0.97:
        blockers.append("locked_market")
    if leader_prob is not None and leader_prob <= 0.03 and len(probs_available) <= 2:
        blockers.append("near_zero_binary")
    # Dead market: all outcomes at zero probability
    if probs_available and all(p < 0.001 for p in probs_available):
        blockers.append("all_outcomes_zero")

    leader_opening = None
    if leader_name:
        for outcome in outcomes_data:
            if outcome["name"] == leader_name:
                leader_opening = outcome.get("opening_probability")
                break

    has_any_movement = any(
        outcome["probability_change_24h"] is not None
        and abs(outcome["probability_change_24h"]) > 0.001
        for outcome in outcomes_data
    )
    max_recent_movement = max(
        (
            abs(o["probability_change_24h"])
            for o in outcomes_data
            if o["probability_change_24h"] is not None
        ),
        default=0.0,
    )

    days_stale = None
    movement_evidence_status = "missing" if not has_any_movement else "unknown"
    updated_at = _utc(market.updated_at)
    if updated_at:
        days_stale = (now - updated_at).total_seconds() / 86400
        if has_any_movement:
            if days_stale > stale_no_movement_days:
                movement_evidence_status = "stale"
                blockers.append("stale_movement_evidence")
            else:
                movement_evidence_status = "fresh"
        if days_stale > stale_no_movement_days and not has_any_movement:
            blockers.append("stale_no_movement")
        if resolution_date is None and days_stale > no_resolution_stale_days:
            if has_any_movement:
                blockers.append("stale_no_resolution_stale_movement")
            else:
                blockers.append("stale_no_resolution_no_movement")

    resolved_threshold, opening_threshold = _effective_resolution_thresholds(
        sport_category
    )
    is_effectively_resolved = (
        leader_prob is not None and leader_prob >= resolved_threshold
    )
    is_sports_category = _is_sports_market_category(sport_category)
    sports_effectively_settled = (
        is_sports_category
        and is_effectively_resolved
        and leader_opening is not None
        and leader_opening < opening_threshold
        and any(o["probability_change_24h"] is not None for o in outcomes_data)
        and max_recent_movement < 0.01
    )
    if sports_effectively_settled:
        blockers.append("sports_effectively_settled")
    elif is_effectively_resolved and (
        leader_opening is None or leader_opening >= opening_threshold
    ):
        blockers.append("effectively_resolved")

    # Soft-settled binary market: leader >=60% with negligible movement.
    # Catches elimination/advancement markets stuck below the 90% threshold.
    # Only applied to sports categories where elimination makes a market
    # de facto resolved even when the exchange hasn't formally settled it.
    soft_settled = False
    if (
        is_sports_category
        and not sports_effectively_settled
        and leader_prob is not None
        and leader_prob >= 0.60
        and len(probs_available) == 2
    ):
        if max_recent_movement < 0.02:
            if leader_opening is None or leader_opening >= 0.50:
                soft_settled = True
                blockers.append("soft_settled_binary")

    commence_time = _utc(market.commence_time)
    golf_started_too_long_ago = (
        (sport_category or "").lower() == "golf"
        and commence_time is not None
        and commence_time < now - timedelta(days=6)
    )
    if golf_started_too_long_ago:
        blockers.append("stale_golf_tournament")

    return {
        "eligible": not blockers,
        "blockers": blockers,
        "checks": {
            "all_outcomes_settled": all_settled,
            "leader_probability": leader_prob,
            "leader_opening_probability": leader_opening,
            "effective_resolution_threshold": resolved_threshold,
            "effective_resolution_opening_threshold": opening_threshold,
            "sports_effectively_settled": sports_effectively_settled,
            "has_any_movement": has_any_movement,
            "movement_evidence_status": movement_evidence_status,
            "movement_evidence_updated_at": (
                updated_at.isoformat() if updated_at else None
            ),
            "max_recent_movement": round(max_recent_movement, 4),
            "soft_settled_binary": soft_settled,
            "locked_market": bool(leader_prob is not None and leader_prob >= 0.97),
            "near_zero_binary": bool(
                leader_prob is not None
                and leader_prob <= 0.03
                and len(probs_available) <= 2
            ),
            "all_outcomes_zero": bool(
                probs_available and all(p < 0.001 for p in probs_available)
            ),
            "would_be_title_implied_stale": bool(title_stale_blocker),
            "title_implied_stale_reason": title_stale_blocker,
            "days_stale": round(days_stale, 2) if days_stale is not None else None,
            "commence_time": commence_time.isoformat() if commence_time else None,
            "commence_time_staleness_applied": golf_started_too_long_ago,
        },
    }


def build_effective_settlement_followup_item(
    market: FuturesMarket,
    now: datetime,
) -> dict | None:
    """Return admin follow-up data for sports futures hidden as effectively settled."""
    outcomes_data, leader_name, leader_prob = _top_outcomes_for_trace(market)
    runtime_filters = _market_runtime_filter_trace(
        market,
        outcomes_data,
        leader_name,
        leader_prob,
        now,
        sport_category=market.llm_sport_category,
    )
    if "sports_effectively_settled" not in runtime_filters["blockers"]:
        return None

    checks = runtime_filters.get("checks") or {}
    leader_opening = checks.get("leader_opening_probability")
    updated_at = _utc(market.updated_at)
    resolution_date = _utc(market.resolution_date)
    commence_time = _utc(market.commence_time)
    days_since_update = (
        round((now - updated_at).total_seconds() / 86400, 2) if updated_at else None
    )
    if days_since_update is None:
        age_bucket = "unknown"
    elif days_since_update <= 2:
        age_bucket = "recent_source_update"
    elif days_since_update <= 14:
        age_bucket = "aging_source_update"
    else:
        age_bucket = "old_source_update"

    source = (market.source or "").lower()
    if source == "kalshi":
        suggested_action = (
            "Run or inspect Kalshi settlement/API winner backfill for this market."
        )
    elif source == "polymarket":
        suggested_action = (
            "Run or inspect Polymarket settlement lookup/backfill for this market."
        )
    else:
        suggested_action = (
            "Inspect source settlement state and polling freshness for this market."
        )

    return {
        "market_id": market.id,
        "source": market.source,
        "name": market.name,
        "status": market.status,
        "category": market.category,
        "llm_sport_category": market.llm_sport_category,
        "event_id": market.event_id,
        "group_id": market.group_id,
        "canonical_market_key": market.canonical_market_key,
        "external_id": market.external_id,
        "leader_name": leader_name,
        "leader_probability": leader_prob,
        "leader_opening_probability": leader_opening,
        "max_recent_movement": checks.get("max_recent_movement"),
        "updated_at": updated_at.isoformat() if updated_at else None,
        "days_since_update": days_since_update,
        "age_bucket": age_bucket,
        "resolution_date": resolution_date.isoformat() if resolution_date else None,
        "commence_time": commence_time.isoformat() if commence_time else None,
        "blockers": runtime_filters["blockers"],
        "checks": checks,
        "top_outcomes": outcomes_data[:5],
        "suggested_action": suggested_action,
    }


async def _discover_candidate_pool_trace(
    db: AsyncSession,
    now: datetime,
    market_id: int,
) -> dict:
    base_filters = [
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= now,
        ),
        ~FuturesMarket.name.like("% vs %"),
        ~FuturesMarket.name.like("% vs. %"),
    ]
    non_sports_filter = or_(
        ~FuturesMarket.llm_sport_category.in_(DISCOVER_SPORTS_CATEGORIES),
        FuturesMarket.llm_sport_category.is_(None),
    )
    movement_expr = (
        select(func.max(func.abs(FuturesOutcome.probability_change_24h)))
        .where(FuturesOutcome.market_id == FuturesMarket.id)
        .correlate(FuturesMarket)
        .scalar_subquery()
    )
    pool_specs = [
        (
            "sports_tier",
            FuturesMarket.llm_sport_category.in_(DISCOVER_SPORTS_CATEGORIES),
            [
                FuturesMarket.market_tier.asc().nulls_last(),
                FuturesMarket.resolution_date.asc().nulls_last(),
            ],
            50,
        ),
        (
            "sports_postseason",
            _SPORTS_POSTSEASON_SQL_FILTER,
            [
                FuturesMarket.resolution_date.asc().nulls_last(),
                FuturesMarket.updated_at.desc().nulls_last(),
            ],
            80,
        ),
        (
            "sports_editorial_recall",
            and_(
                FuturesMarket.llm_sport_category.in_(DISCOVER_SPORTS_CATEGORIES),
                _discover_sports_editorial_recall_filter(),
            ),
            [
                FuturesMarket.market_tier.asc().nulls_last(),
                FuturesMarket.volume_24h.desc().nulls_last(),
                FuturesMarket.updated_at.desc().nulls_last(),
            ],
            80,
        ),
        (
            "nonsports_volume",
            non_sports_filter,
            [
                FuturesMarket.volume_24h.desc().nulls_last(),
                FuturesMarket.market_tier.asc().nulls_last(),
            ],
            180,
        ),
        (
            "nonsports_movement",
            non_sports_filter,
            [
                movement_expr.desc().nulls_last(),
                FuturesMarket.volume_24h.desc().nulls_last(),
            ],
            160,
        ),
        (
            "nonsports_enriched",
            and_(
                non_sports_filter,
                or_(
                    FuturesMarket.hook_description.isnot(None),
                    FuturesMarket.image_url.isnot(None),
                ),
            ),
            [
                FuturesMarket.hook_generated_at.desc().nulls_last(),
                FuturesMarket.updated_at.desc().nulls_last(),
            ],
            160,
        ),
        (
            "nonsports_editorial_recall",
            and_(non_sports_filter, _discover_editorial_recall_filter()),
            [
                FuturesMarket.market_tier.asc().nulls_last(),
                FuturesMarket.volume_24h.desc().nulls_last(),
                FuturesMarket.updated_at.desc().nulls_last(),
            ],
            120,
        ),
        (
            "nonsports_timely",
            and_(non_sports_filter, FuturesMarket.resolution_date.isnot(None)),
            [
                FuturesMarket.resolution_date.asc().nulls_last(),
                FuturesMarket.volume_24h.desc().nulls_last(),
            ],
            120,
        ),
    ]

    pools = []
    candidate_ids: list[int] = []
    external_curator_ids = await _external_curator_recall_market_ids(
        db,
        base_filters,
        row_limit=80,
        market_limit=80,
    )
    candidate_ids.extend(external_curator_ids)
    pools.append(
        {
            "name": "external_curator_recall",
            "limit": 80,
            "candidate_count": len(external_curator_ids),
            "included": market_id in external_curator_ids,
            "position": (
                external_curator_ids.index(market_id) + 1
                if market_id in external_curator_ids
                else None
            ),
        }
    )
    for name, extra_filter, ordering, limit in pool_specs:
        result = await db.execute(
            select(FuturesMarket.id)
            .where(*base_filters, extra_filter)
            .order_by(*ordering)
            .limit(limit)
        )
        ids = list(result.scalars().all())
        candidate_ids.extend(ids)
        pools.append(
            {
                "name": name,
                "limit": limit,
                "candidate_count": len(ids),
                "included": market_id in ids,
                "position": ids.index(market_id) + 1 if market_id in ids else None,
            }
        )

    deduped: list[int] = []
    seen: set[int] = set()
    for candidate_id in candidate_ids:
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        deduped.append(candidate_id)

    return {
        "included": market_id in seen,
        "deduped_candidate_count": len(deduped),
        "candidate_position": (
            deduped.index(market_id) + 1 if market_id in seen else None
        ),
        "pools": pools,
    }


def _get_cached_interestingness(market_id: int) -> dict | None:
    """Read a single interestingness score from Redis for admin trace output."""
    try:
        from app.tasks.redis_state import get_redis_client

        r = get_redis_client()
        raw = r.get(f"interestingness:{market_id}")
        if raw is not None:
            return _json_module.loads(raw.decode() if isinstance(raw, bytes) else raw)
    except Exception:
        pass
    return None


def _score_market_trace(
    market: FuturesMarket,
    now: datetime,
    source_count: int,
    *,
    is_external_curator_recall: bool = False,
) -> dict:
    outcomes_data, leader_name, leader_prob = _top_outcomes_for_trace(market)
    runtime_filters = _market_runtime_filter_trace(
        market,
        outcomes_data,
        leader_name,
        leader_prob,
        now,
        sport_category=market.llm_sport_category,
    )

    highlight_result = compute_futures_highlight(
        market_tier=market.market_tier,
        sport_category=market.llm_sport_category,
        resolution_date=market.resolution_date,
        outcomes=outcomes_data,
        source_count=source_count,
        now=now,
        market_name=market.name,
        volume_24h=market.volume_24h,
        curation_score_adj=market.__dict__.get("curation_score_adj", 0) or 0,
    )

    top_mover_name = highlight_result.top_mover_name
    top_mover_change = None
    if top_mover_name:
        for outcome in outcomes_data:
            if outcome["name"] == top_mover_name and outcome.get(
                "probability_change_24h"
            ):
                top_mover_change = outcome["probability_change_24h"]
                break

    top_surprise_name = None
    top_surprise_change = None
    for outcome in outcomes_data:
        opening = outcome.get("opening_probability")
        current = outcome.get("probability")
        if opening is None or current is None:
            continue
        surprise_change = current - opening
        if top_surprise_change is None or abs(surprise_change) > abs(
            top_surprise_change
        ):
            top_surprise_name = outcome.get("name")
            top_surprise_change = surprise_change

    headline = (
        generate_futures_headline(
            highlight_reasons=highlight_result.reasons,
            top_mover_name=top_mover_name,
            top_mover_change=top_mover_change,
            top_surprise_name=top_surprise_name,
            top_surprise_change=top_surprise_change,
            leader_name=leader_name,
            leader_probability=leader_prob,
            source_count=source_count,
            market_name=market.name,
        )
        or highlight_result.primary_reason
    )
    context_summary = generate_futures_context_summary(
        headline=headline,
        highlight_reasons=highlight_result.reasons,
        market_name=market.name,
        leader_name=leader_name,
        leader_probability=leader_prob,
        source_count=source_count,
    )

    # Snippet v2: prefer cached angle-based snippet when flag is on
    _snippet_v2 = (market.market_metadata or {}).get("snippet_v2") if market.__dict__.get("market_metadata") else None
    if _snippet_v2 and isinstance(_snippet_v2, dict) and _snippet_v2.get("snippet_text"):
        from app.tasks.redis_state import get_redis_client as _rc
        try:
            _flag = _rc().get("snippet_v2:enabled")
            if _flag and _flag.decode().lower() in ("true", "1", "yes"):
                context_summary = _snippet_v2["snippet_text"]
        except Exception:
            pass

    quality = classify_market_quality(
        market_name=market.name,
        sport_category=market.llm_sport_category,
        outcome_names=[outcome.name for outcome in market.outcomes if outcome.name],
        external_id=market.external_id,
        persisted_story_key=market.__dict__.get("story_key"),
        status=market.__dict__.get("status"),  # R6: resolved sports never surface
    )
    quality_score = apply_quality_score(highlight_result.score, quality)
    explanation_score = apply_explanation_quality_score(
        quality_score,
        hook_description=market.hook_description,
        headline=headline,
        quality=quality,
    )
    explanation_score = _apply_external_curator_recall_score(
        explanation_score,
        highlight_result.reasons,
        is_external_curator_recall=is_external_curator_recall,
    )
    p_result = compute_futures_multiplier(
        ctx=PersonalizationContext(),
        sport_category=market.llm_sport_category,
        outcome_team_ids=[o.team_id for o in market.outcomes if o.team_id is not None],
        futures_market_id=market.id,
        sport_key=market.sport.key if market.sport else None,
        outcome_names=[o.name for o in market.outcomes if o.name],
    )
    final_score = min(98, int(explanation_score * p_result.multiplier))

    blockers = list(runtime_filters["blockers"])
    if quality.quality_class == "suppress":
        blockers.append("quality_suppressed")
    if final_score < 15:
        blockers.append("below_score_floor")

    return {
        "eligible_before_caps": not blockers,
        "blockers": blockers,
        "runtime_filters": runtime_filters,
        "scores": {
            "highlight": highlight_result.score,
            "after_quality": quality_score,
            "after_explanation": explanation_score,
            "personalization_multiplier": p_result.multiplier,
            "final": final_score,
        },
        "highlight": {
            "headline": headline,
            "context_summary": context_summary,
            "reason": generate_futures_reason(
                market_name=market.name,
                highlight_reasons=highlight_result.reasons,
                top_mover_name=top_mover_name,
                top_mover_change=top_mover_change,
                top_surprise_name=top_surprise_name,
                top_surprise_change=top_surprise_change,
                leader_name=leader_name,
                leader_probability=leader_prob,
                source_count=source_count,
            ),
            "primary_reason": highlight_result.primary_reason,
            "reasons": highlight_result.reasons,
            "leader_name": leader_name,
            "leader_probability": leader_prob,
            "top_mover_name": top_mover_name,
            "top_mover_change": top_mover_change,
            "top_surprise_name": top_surprise_name,
            "top_surprise_change": top_surprise_change,
        },
        "quality": {
            "class": quality.quality_class,
            "family_key": quality.family_key,
            "story_key": quality.story_key,
            "reasons": quality.reasons,
        },
        "explanation": {
            "has_hook": bool(market.hook_description),
            "has_image": bool(market.image_url),
            "headline_ok": bool(headline),
        },
        "interestingness": _get_cached_interestingness(market.id),
        "top_outcomes": outcomes_data[:5],
    }


def _suggest_trace_fix(trace: dict) -> str:
    if not trace["base_eligibility"]["eligible"]:
        blockers = trace["base_eligibility"]["blockers"]
        if "event_linked_game_market" in blockers:
            return "Leave out of Discover; route this to event detail or a game-market module."
        if "not_open" in blockers or "past_resolution" in blockers:
            return "No ranking fix; this market is closed or stale by source state."
        return "Fix base eligibility only if this class should intentionally appear in Discover."
    if not trace["candidate_pools"]["included"]:
        return "Add or retune a targeted candidate pool for this market class."
    blockers = trace["score_trace"]["blockers"]
    if "quality_suppressed" in blockers:
        return "Tune the quality classifier if this is genuinely editorial."
    if (
        "stale_no_movement" in blockers
        or "effectively_resolved" in blockers
        or "sports_effectively_settled" in blockers
    ):
        return "No ranking fix; inspect settlement/backfill diagnostics for the stale source state."
    rank_phases = trace.get("rank_phases") or {}
    if rank_phases.get("dropped_by_canonical_dedupe"):
        return (
            "Inspect canonical dedupe; this market is being collapsed behind a sibling."
        )
    returned_rank = rank_phases.get("returned_rank")
    if returned_rank and returned_rank <= 50:
        return "No immediate fix; the market is eligible and present in the returned diagnostic feed."
    if not trace["final_ranking"]["survived_final_caps"]:
        return "Inspect quality family caps, story deduping, and first-page diversity for this story."
    if (
        rank_phases.get("post_diversity_rank")
        and rank_phases["post_diversity_rank"] > 50
    ):
        return "Inspect Discover diversity repair and category/story caps before tuning score."
    if (
        trace["final_ranking"]["final_futures_rank"]
        and trace["final_ranking"]["final_futures_rank"] > 50
    ):
        return "Tune scoring inputs only if this should beat stronger same-category stories."
    return "No immediate fix; the market is eligible and present in the scored feed."


async def _discover_rank_phase_trace(
    db: AsyncSession,
    now: datetime,
    market_id: int,
    *,
    include_events: bool,
    event_pct: float | None,
    limit: int,
) -> dict:
    """Trace a futures market through the same assembly phases as GET /feed."""
    ctx = PersonalizationContext()
    event_items: list[dict] = []
    tournament_items: list[dict] = []
    if include_events:
        event_items = await _score_events(db, now, None, ctx)
        tournament_items = await _score_golf_tournaments(db, now, None, ctx)

    raw_futures = await _score_futures(
        db,
        now,
        sport_filter=None,
        ctx=ctx,
        my_teams_only=False,
    )
    raw_futures_rank = _rank_futures_market(raw_futures, market_id)

    deduped_futures = _dedupe_futures_by_canonical(raw_futures)
    post_dedupe_rank = _rank_futures_market(deduped_futures, market_id)
    dropped_by_canonical_dedupe = (
        raw_futures_rank is not None and post_dedupe_rank is None
    )
    canonical_replacement = None
    if dropped_by_canonical_dedupe:
        target = next(
            (item for item in raw_futures if _futures_market_id(item) == market_id),
            None,
        )
        target_key = (target or {}).get("data", {}).get("canonical_market_key")
        if target_key:
            replacement = next(
                (
                    item
                    for item in deduped_futures
                    if (item.get("data") or {}).get("canonical_market_key")
                    == target_key
                ),
                None,
            )
            if replacement:
                canonical_replacement = {
                    "id": _futures_market_id(replacement),
                    "name": (replacement.get("data") or {}).get("name"),
                    "score": replacement.get("score"),
                }

    feed_items = event_items + tournament_items + deduped_futures
    feed_items.sort(key=lambda x: (x["score"], x.get("_sort_time", 0)), reverse=True)
    post_initial_sort_rank = _rank_futures_market(feed_items, market_id)

    post_event_demote_rank = post_initial_sort_rank
    if event_pct is not None and event_pct < 0.3:
        _demote_non_exceptional_discover_events(feed_items)
        feed_items.sort(
            key=lambda x: (x["score"], x.get("_sort_time", 0)), reverse=True
        )
        post_event_demote_rank = _rank_futures_market(feed_items, market_id)

    post_event_mix_rank = post_event_demote_rank
    if event_pct is not None and event_pct >= 0.2:
        feed_items = _ensure_feed_diversity(feed_items, limit, event_pct=0.6)
        post_event_mix_rank = _rank_futures_market(feed_items, market_id)

    post_diversity_rank = post_event_mix_rank
    if (event_pct is not None and event_pct < 0.3) or not include_events:
        feed_items = diversify_discover_first_page(
            feed_items, first_page_size=min(20, limit),
            cold_start=not ctx.discover_category_affinities,
        )
        feed_items = backfill_discover_editorial_tail(
            feed_items,
            window_size=min(50, len(feed_items)),
            preserve_top=min(20, len(feed_items)),
        )
        post_diversity_rank = _rank_futures_market(feed_items, market_id)

    returned = feed_items[:limit]
    returned_rank = _rank_futures_market(returned, market_id)

    return {
        "mode": {
            "include_events": include_events,
            "event_pct": event_pct,
            "limit": limit,
        },
        "raw_futures_rank": raw_futures_rank,
        "post_canonical_dedupe_rank": post_dedupe_rank,
        "post_initial_sort_rank": post_initial_sort_rank,
        "post_event_demote_rank": post_event_demote_rank,
        "post_event_mix_rank": post_event_mix_rank,
        "post_diversity_rank": post_diversity_rank,
        "returned_rank": returned_rank,
        "returned": returned_rank is not None,
        "raw_futures_count": len(raw_futures),
        "post_dedupe_futures_count": len(deduped_futures),
        "assembled_count": len(feed_items),
        "dropped_by_canonical_dedupe": dropped_by_canonical_dedupe,
        "canonical_replacement": canonical_replacement,
    }


async def build_discover_market_trace(
    db: AsyncSession,
    market_id: int,
    now: datetime | None = None,
    *,
    include_events: bool = False,
    event_pct: float | None = 0.15,
    limit: int = 50,
) -> dict | None:
    """Build an admin-only pipeline trace for a single Discover market."""
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
        select(FuturesMarket)
        .options(
            selectinload(FuturesMarket.outcomes), selectinload(FuturesMarket.sport)
        )
        .where(FuturesMarket.id == market_id)
    )
    market = result.scalars().first()
    if not market:
        return None

    canonical_counts = await _get_canonical_source_counts(db)
    source_count = (
        canonical_counts.get(market.canonical_market_key, 1)
        if market.canonical_market_key
        else 1
    )
    base_eligibility = _market_base_trace(market, now)
    candidate_pools = await _discover_candidate_pool_trace(db, now, market_id)
    score_trace = _score_market_trace(
        market,
        now,
        source_count,
        is_external_curator_recall=any(
            pool.get("name") == "external_curator_recall" and pool.get("included")
            for pool in candidate_pools.get("pools", [])
        ),
    )

    rank_phases = await _discover_rank_phase_trace(
        db,
        now,
        market_id,
        include_events=include_events,
        event_pct=event_pct,
        limit=limit,
    )

    trace = {
        "market": {
            "id": market.id,
            "name": market.name,
            "source": market.source,
            "status": market.status,
            "category": market.category,
            "llm_sport_category": market.llm_sport_category,
            "market_tier": market.market_tier,
            "market_type": market.market_type,
            "external_id": market.external_id,
            "canonical_market_key": market.canonical_market_key,
            "source_count": source_count,
            "volume_24h": (
                float(market.volume_24h) if market.volume_24h is not None else None
            ),
            "resolution_date": (
                _utc(market.resolution_date).isoformat()
                if _utc(market.resolution_date)
                else None
            ),
            "updated_at": (
                _utc(market.updated_at).isoformat() if _utc(market.updated_at) else None
            ),
        },
        "base_eligibility": base_eligibility,
        "candidate_pools": candidate_pools,
        "score_trace": score_trace,
        "rank_phases": rank_phases,
        "final_ranking": {
            "survived_final_caps": rank_phases["returned"],
            "final_futures_rank": rank_phases["raw_futures_rank"],
            "final_score": (
                score_trace["scores"]["final"]
                if rank_phases["raw_futures_rank"]
                else None
            ),
            "scored_futures_count": rank_phases["raw_futures_count"],
        },
    }
    trace["suggested_fix"] = _suggest_trace_fix(trace)
    return trace


async def _load_personalization_context(
    db: AsyncSession,
    user: Optional[User],
    *,
    session_id: str | None = None,
    config: dict[str, float | bool] | None = None,
) -> PersonalizationContext:
    """Load all user personalization data into a context object.

    Single query pattern: load favorites, preferences, and pins in parallel-ish
    SQLAlchemy queries, then assemble into the context.
    """
    if not user and not session_id:
        return PersonalizationContext()

    interaction_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    config = config or _discover_runtime_config_defaults()
    interaction_suppression_enabled = bool(
        config.get("interaction_suppression_enabled", True)
    )
    seen_cutoff = datetime.now(timezone.utc) - timedelta(
        hours=float(config.get("seen_suppression_hours", 48))
    )
    dismiss_cutoff = datetime.now(timezone.utc) - timedelta(
        days=float(config.get("dismiss_suppression_days", 14))
    )

    interaction_identity_filters = []
    if user:
        interaction_identity_filters.append(DiscoverInteraction.user_id == user.id)
    if session_id:
        interaction_identity_filters.append(
            DiscoverInteraction.session_id == session_id
        )
    interaction_identity_clause = or_(*interaction_identity_filters)

    # Load user favorites, preferences, pins, and recent Discover behavior in parallel
    if user:
        favorites_query = select(UserFavorite).where(UserFavorite.user_id == user.id)
        prefs_query = select(UserPreference).where(UserPreference.user_id == user.id)
        pins_query = select(UserPin).where(UserPin.user_id == user.id)
    else:
        favorites_query = select(UserFavorite).where(False)
        prefs_query = select(UserPreference).where(False)
        pins_query = select(UserPin).where(False)

    favorites_result = await db.execute(favorites_query)
    prefs_result = await db.execute(prefs_query)
    pins_result = await db.execute(pins_query)
    interactions_result = await db.execute(
        select(
            DiscoverInteraction.category,
            DiscoverInteraction.action,
            func.count(DiscoverInteraction.id).label("count"),
        )
        .where(
            interaction_identity_clause,
            DiscoverInteraction.created_at >= interaction_cutoff,
            DiscoverInteraction.category.isnot(None),
        )
        .group_by(DiscoverInteraction.category, DiscoverInteraction.action)
    )
    feature_interactions_result = await db.execute(
        select(
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_name,
            DiscoverInteraction.category,
            DiscoverInteraction.action,
            func.count(DiscoverInteraction.id).label("count"),
        )
        .where(
            interaction_identity_clause,
            DiscoverInteraction.created_at >= interaction_cutoff,
            DiscoverInteraction.item_name.isnot(None),
            DiscoverInteraction.category.isnot(None),
            DiscoverInteraction.action.in_(
                (
                    "detail_click",
                    "open",
                    "share",
                    "like",
                    "unlike",
                    "dismiss",
                    "group_expand",
                    "context_expand",
                )
            ),
        )
        .group_by(
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_name,
            DiscoverInteraction.category,
            DiscoverInteraction.action,
        )
    )
    recent_items_result = await db.execute(
        select(
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
            DiscoverInteraction.action,
            func.max(DiscoverInteraction.created_at).label("last_seen"),
            func.max(DiscoverInteraction.item_name).label("item_name"),
            func.max(DiscoverInteraction.category).label("category"),
        )
        .where(
            interaction_identity_clause,
            DiscoverInteraction.item_type.in_(("event", "futures")),
            DiscoverInteraction.action.in_(("impression", "dismiss", "unlike")),
            DiscoverInteraction.created_at >= dismiss_cutoff,
        )
        .group_by(
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
            DiscoverInteraction.action,
        )
        .order_by(func.max(DiscoverInteraction.created_at).desc())
    )

    favorites = favorites_result.scalars().all()

    team_relations: dict[int, set[str]] = {}
    team_weights: dict[int, float] = {}
    for fav in favorites:
        if fav.team_id not in team_relations:
            team_relations[fav.team_id] = set()
        team_relations[fav.team_id].add(fav.relation_type)
        team_weights[fav.team_id] = float(fav.weight) if fav.weight else 1.0

    prefs = prefs_result.scalar_one_or_none()
    sport_affinities = (
        prefs.sport_affinities if prefs and prefs.sport_affinities else {}
    )

    pins = pins_result.scalars().all()
    pinned_event_ids = {p.target_id for p in pins if p.pin_type == "event"}
    pinned_futures_ids = {p.target_id for p in pins if p.pin_type == "future"}

    category_affinities = _build_discover_category_affinities(interactions_result.all())
    feature_affinities = _build_discover_feature_affinities(
        feature_interactions_result.all()
    )
    recent_seen_event_ids: set[int] = set()
    recent_seen_futures_ids: set[int] = set()
    recent_seen_event_at: dict[int, datetime] = {}
    recent_seen_futures_at: dict[int, datetime] = {}
    recent_dismissed_event_ids: set[int] = set()
    recent_dismissed_futures_ids: set[int] = set()
    recent_dismissed_story_keys: set[str] = set()
    recent_dismissed_group_ids: set[str] = set()
    recent_dismissed_feature_token_sets: list[set[str]] = []
    if interaction_suppression_enabled:
        for (
            item_type,
            item_id_raw,
            action,
            last_seen,
            item_name,
            category,
        ) in recent_items_result.all():
            try:
                item_id = int(item_id_raw)
            except (TypeError, ValueError):
                continue
            last_seen_dt = _utc(last_seen)
            if action in ("dismiss", "unlike"):
                if item_type == "event":
                    recent_dismissed_event_ids.add(item_id)
                elif item_type == "futures":
                    recent_dismissed_futures_ids.add(item_id)
                if item_name:
                    sk = compute_story_key(item_name, category or "")
                    if sk:
                        recent_dismissed_story_keys.add(sk)
                    if len(recent_dismissed_feature_token_sets) < 50:
                        recent_dismissed_feature_token_sets.append(
                            _discover_semantic_tokens(
                                item_name=item_name,
                                category=category,
                                item_type=item_type,
                            )
                        )
            elif (
                action == "impression" and last_seen_dt and last_seen_dt >= seen_cutoff
            ):
                if item_type == "event":
                    recent_seen_event_ids.add(item_id)
                    recent_seen_event_at[item_id] = last_seen_dt
                elif item_type == "futures":
                    recent_seen_futures_ids.add(item_id)
                    recent_seen_futures_at[item_id] = last_seen_dt

    # Supplement seen IDs from user_seen_markets table (written by the
    # predictions/Higher-Lower flow). This table tracks markets the user
    # has already been shown as guess cards, so re-showing them in
    # Discover is redundant.
    if interaction_suppression_enabled:
        from app.models.models import UserSeenMarket

        usm_identity_filters = []
        if user:
            usm_identity_filters.append(UserSeenMarket.user_id == user.id)
        if session_id:
            usm_identity_filters.append(UserSeenMarket.session_id == session_id)
        if usm_identity_filters:
            usm_result = await db.execute(
                select(UserSeenMarket.item_type, UserSeenMarket.item_id).where(
                    or_(*usm_identity_filters),
                    UserSeenMarket.seen_at >= seen_cutoff,
                )
            )
            for item_type_usm, item_id_usm in usm_result.all():
                if item_type_usm == "event":
                    recent_seen_event_ids.add(item_id_usm)
                elif item_type_usm == "futures":
                    recent_seen_futures_ids.add(item_id_usm)

    if recent_dismissed_futures_ids:
        gid_result = await db.execute(
            select(FuturesMarket.group_id).where(
                FuturesMarket.id.in_(recent_dismissed_futures_ids),
                FuturesMarket.group_id.isnot(None),
            )
        )
        for (gid,) in gid_result.all():
            recent_dismissed_group_ids.add(str(gid))

    # Load roster player names from followed teams for player-futures matching
    roster_player_names: set[str] = set()
    followed_team_ids = [
        tid
        for tid, rels in team_relations.items()
        if "follow" in rels or "local" in rels or "alma_mater" in rels
    ]
    if followed_team_ids:
        teams_result = await db.execute(
            select(Team.roster_players).where(
                Team.id.in_(followed_team_ids),
                Team.roster_players.isnot(None),
            )
        )
        for (roster,) in teams_result.all():
            if isinstance(roster, list):
                for item in roster:
                    if isinstance(item, dict):
                        name = item.get("name")
                    elif isinstance(item, str):
                        name = item
                    else:
                        continue
                    if name:
                        roster_player_names.add(name.lower())

    return PersonalizationContext(
        team_relations=team_relations,
        team_weights=team_weights,
        sport_affinities=sport_affinities,
        pinned_event_ids=pinned_event_ids,
        pinned_futures_ids=pinned_futures_ids,
        roster_player_names=roster_player_names,
        discover_category_affinities=category_affinities,
        discover_feature_affinities=feature_affinities,
        recent_seen_event_ids=recent_seen_event_ids,
        recent_seen_futures_ids=recent_seen_futures_ids,
        recent_seen_event_at=recent_seen_event_at,
        recent_seen_futures_at=recent_seen_futures_at,
        recent_dismissed_event_ids=recent_dismissed_event_ids,
        recent_dismissed_futures_ids=recent_dismissed_futures_ids,
        recent_dismissed_story_keys=recent_dismissed_story_keys,
        recent_dismissed_group_ids=recent_dismissed_group_ids,
        recent_dismissed_feature_token_sets=recent_dismissed_feature_token_sets,
        is_authenticated=bool(user),
    )


def _build_discover_category_affinities(rows) -> dict[str, float]:
    """Convert recent Discover interaction counts into bounded category deltas.

    Cold-start fast-lane: when session has < 20 total interactions, all weights
    are doubled so early swipes bend the feed faster (#850). This means 2
    same-category dismisses reach the -0.40 floor that previously took 3+.
    """
    raw_scores: dict[str, float] = {}
    action_counts: dict[str, int] = {}
    negative_counts: dict[str, int] = {}
    base_weights = {
        "detail_click": 1.5,
        "open": 1.5,
        "share": 3.0,
        "like": 2.0,
        "group_expand": 0.75,
        "challenge_start": 0.5,
        "challenge_complete": 1.0,
        "context_expand": 0.35,
        "context_collapse": 0.0,
        "unlike": -1.0,
        "dismiss": -2.0,
    }
    all_rows = list(rows)
    total_interactions = sum(int(count or 0) for _, _, count in all_rows)
    _cold_start = total_interactions < 20
    cold_start_boost = 2.0 if _cold_start else 1.0
    weights = {k: v * cold_start_boost for k, v in base_weights.items()}
    for category, action, count in all_rows:
        if not category or action not in weights:
            continue
        key = str(category).lower()
        n = int(count or 0)
        raw_scores[key] = raw_scores.get(key, 0.0) + weights[action] * n
        action_counts[key] = action_counts.get(key, 0) + n
        if action in ("dismiss", "unlike"):
            negative_counts[key] = negative_counts.get(key, 0) + n

    affinities: dict[str, float] = {}
    for category, score in raw_scores.items():
        if action_counts.get(category, 0) < 2:
            continue
        # Escalate penalty when negative swipes dominate: 3+ dismiss/unlike
        # actions with a strongly negative raw score unlock a deeper floor.
        n_negative = negative_counts.get(category, 0)
        # Cold-start: halve thresholds so early dismisses reach deeper floors
        _t8, _t5, _t3 = (4, 3, 2) if _cold_start else (8, 5, 3)
        _s12, _s8, _s4 = (-6.0, -4.0, -2.0) if _cold_start else (-12.0, -8.0, -4.0)
        if n_negative >= _t8 and score < _s12:
            floor = -0.80
        elif n_negative >= _t5 and score < _s8:
            floor = -0.60
        elif n_negative >= _t3 and score < _s4:
            floor = -0.40
        else:
            floor = -0.15
        affinities[category] = max(floor, min(0.18, score / 20.0))
    return affinities


_REGIONAL_FEATURE_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "boston",
        ("region:boston", "region:massachusetts", "region:new_england"),
    ),
    (
        "massachusetts",
        ("region:massachusetts", "region:new_england"),
    ),
    (
        "red sox",
        (
            "region:boston",
            "region:massachusetts",
            "region:new_england",
            "team:boston_red_sox",
        ),
    ),
    (
        "celtics",
        (
            "region:boston",
            "region:massachusetts",
            "region:new_england",
            "team:boston_celtics",
        ),
    ),
    (
        "bruins",
        (
            "region:boston",
            "region:massachusetts",
            "region:new_england",
            "team:boston_bruins",
        ),
    ),
    (
        "patriots",
        ("region:massachusetts", "region:new_england", "team:new_england_patriots"),
    ),
    (
        "new england",
        ("region:new_england",),
    ),
    (
        "connecticut",
        ("region:connecticut", "region:new_england"),
    ),
    (
        "rhode island",
        ("region:rhode_island", "region:new_england"),
    ),
    (
        "new hampshire",
        ("region:new_hampshire", "region:new_england"),
    ),
    (
        "vermont",
        ("region:vermont", "region:new_england"),
    ),
    (
        "maine",
        ("region:maine", "region:new_england"),
    ),
)


def _discover_feature_tokens(
    *,
    item_name: str | None,
    category: str | None,
    item_type: str | None = None,
) -> set[str]:
    """Derive cheap story/entity tokens used for fast swipe personalization."""
    name = item_name or ""
    normalized_category = (category or "other").strip().lower() or "other"
    tokens = {f"category:{normalized_category}"}
    if item_type:
        tokens.add(f"type:{str(item_type).lower()}")

    archetype = editorial_archetype(name, normalized_category)
    tokens.add(f"archetype:{archetype}")

    lower = name.lower()
    if " vs " in lower or " v. " in lower:
        tokens.add("format:matchup")
    if any(
        term in lower
        for term in (
            "spotify",
            "billboard",
            "album",
            "song",
            "box office",
            "oscar",
            "grammy",
        )
    ):
        tokens.add("topic:entertainment_charts")
    if any(
        term in lower
        for term in ("fed", "rate cut", "inflation", "cpi", "recession", "jobs report")
    ):
        tokens.add("topic:macro")
    if any(
        term in lower
        for term in ("openai", "anthropic", "gpt", "ai", "nvidia", "spacex", "tesla")
    ):
        tokens.add("topic:ai_tech")
    if any(
        term in lower
        for term in ("president", "election", "senate", "house", "primary")
    ):
        tokens.add("topic:elections")
    for alias, region_tokens in _REGIONAL_FEATURE_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            tokens.update(region_tokens)

    # Entity-ish tokens: proper-name bigrams catch artists, teams, politicians,
    # companies, and places without a separate entity extraction service.
    proper_tokens = re.findall(r"\b[A-Z][A-Za-z'&.-]{2,}\b", name)
    stop = {
        "Will",
        "What",
        "When",
        "Which",
        "Market",
        "Yes",
        "No",
        "The",
        "This",
        "Next",
        "Week",
        "Month",
        "Year",
        "Today",
        "Tomorrow",
        "Over",
        "Under",
    }
    filtered = [t for t in proper_tokens if t not in stop]
    for first, second in zip(filtered, filtered[1:]):
        entity = re.sub(r"[^a-z0-9]+", "_", f"{first}_{second}".lower()).strip("_")
        if entity and len(entity) <= 60:
            tokens.add(f"entity:{entity}")
    for token in filtered[:4]:
        entity = re.sub(r"[^a-z0-9]+", "_", token.lower()).strip("_")
        if entity and len(entity) >= 3:
            tokens.add(f"entity:{entity}")

    return tokens


_DISCOVER_SEMANTIC_STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "before",
    "between",
    "from",
    "into",
    "market",
    "month",
    "next",
    "over",
    "than",
    "that",
    "the",
    "their",
    "this",
    "today",
    "tomorrow",
    "under",
    "week",
    "when",
    "what",
    "which",
    "will",
    "with",
    "year",
    "yes",
    "no",
    "who",
    "wins",
    "win",
    "winner",
    "winning",
    "champion",
    "champions",
    "championship",
}


def _discover_semantic_tokens(
    *,
    item_name: str | None,
    category: str | None,
    item_type: str | None = None,
) -> set[str]:
    """Derive compact semantic tokens for soft dismiss propagation."""
    tokens = {
        token
        for token in _discover_feature_tokens(
            item_name=item_name,
            category=category,
            item_type=item_type,
        )
        if token.startswith(("topic:", "region:", "team:"))
    }
    lower = (item_name or "").lower()
    if re.search(
        r"\b(champion|champions|championship|winner|winning|wins|win)\b",
        lower,
    ):
        tokens.add("term:win")
    if "primera division" in lower:
        tokens.add("term:league")

    for word in re.findall(r"\b[a-z][a-z0-9]{3,}\b", lower):
        if word in _DISCOVER_SEMANTIC_STOPWORDS:
            continue
        if word in {"champions", "champion", "championship", "winner", "winning"}:
            tokens.add("term:win")
            continue
        if word in {"league", "division"}:
            tokens.add("term:league")
            continue
        tokens.add(f"term:{word}")
        if len(tokens) >= 16:
            break
    return tokens


def _build_discover_feature_affinities(rows) -> dict[str, float]:
    """Convert recent item interactions into bounded story/entity deltas."""
    weights = {
        "detail_click": 1.0,
        "open": 1.0,
        "share": 2.5,
        "like": 2.0,
        "group_expand": 0.6,
        "context_expand": 0.3,
        "unlike": -1.0,
        # Older clients may still send dismiss; treat it as a stronger soft
        # downrank for related features, while exact suppression is separate.
        "dismiss": -1.5,
    }
    raw_scores: dict[str, float] = {}
    for item_type, item_name, category, action, count in rows:
        if action not in weights:
            continue
        tokens = _discover_feature_tokens(
            item_name=item_name,
            category=category,
            item_type=item_type,
        )
        weighted = weights[action] * int(count or 0)
        for token in tokens:
            raw_scores[token] = raw_scores.get(token, 0.0) + weighted

    affinities: dict[str, float] = {}
    for token, score in raw_scores.items():
        value = score / 18.0
        if abs(value) < 0.03:
            continue
        affinities[token] = max(-0.12, min(0.12, value))
    return affinities


def _personalization_category_from_sport_key(sport_key: str | None) -> str | None:
    if not sport_key:
        return None
    root = sport_key.split("_")[0].lower()
    if root == "americanfootball":
        return "football"
    if root == "icehockey":
        return "hockey"
    return root


def _build_personalization_trace(
    *,
    ctx: PersonalizationContext,
    item_type: str,
    category: str | None,
    base_score: int | float,
    final_score: int | float,
    p_result,
) -> dict | None:
    """Return compact per-card personalization diagnostics for authenticated feeds."""
    if not ctx.is_authenticated:
        return None

    normalized_category = (category or "other").lower()
    category_delta = ctx.discover_category_affinities.get(normalized_category, 0.0)
    multiplier = float(p_result.multiplier)
    base = int(round(base_score))
    final = int(round(final_score))
    return {
        "item_type": item_type,
        "category": normalized_category,
        "base_score": base,
        "final_score": final,
        "score_delta": final - base,
        "multiplier": round(multiplier, 3),
        "is_personalized": bool(p_result.is_personalized),
        "reasons": list(p_result.reasons),
        "category_affinity_delta": round(float(category_delta), 3),
        "feature_affinity_reasons": [
            r for r in p_result.reasons if r.startswith("discover_feature_")
        ],
        "bounded": 0.3 <= multiplier <= 3.0,
    }


async def _score_events(
    db: AsyncSession,
    now: datetime,
    sport_filter: Optional[str],
    ctx: PersonalizationContext,
    my_teams_only: bool = False,
    my_team_names: Optional[list] = None,
    tag_filter: Optional[list[str]] = None,
    static_tag_filter: Optional[list[str]] = None,
) -> list[dict]:
    """Score and format events for the feed.

    PERFORMANCE: Uses opening odds (already on Event model) for scoring
    instead of re-aggregating from odds_snapshots. This avoids the expensive
    window-function query that was taking 25+ seconds with 130+ live events.
    Opening odds are accurate enough for ranking — the full aggregated odds
    are shown when the user clicks through to the event detail page.

    Tag filtering uses a two-tier approach:
    - Static tags (sport, league, tier, etc.) are pushed to SQL via GIN index
    - Dynamic tags (status, signal, timing, etc.) are filtered inline for freshness
    """
    # Wider time windows for my_teams_only — users want to see all their
    # team's upcoming games and recent results.
    # 72h completed window ensures yesterday's and weekend games are visible
    # when checking on Monday morning (24h was too tight — games disappeared).
    if my_teams_only:
        recent_cutoff = now - timedelta(hours=72)
        upcoming_cutoff = now + timedelta(days=7)
    else:
        # Tighter time windows than the full events list to keep query fast
        recent_cutoff = now - timedelta(hours=24)
        upcoming_cutoff = now + timedelta(hours=12)
    # Guard against events incorrectly stuck in "live" status with future
    # commence_times (e.g., from Scores API returning upcoming events as
    # completed=False). Only include "live" events that have actually started.
    live_start_cutoff = now + timedelta(hours=1)  # Small buffer for clock drift

    query = (
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .options(selectinload(Event.sport))
        .where(
            or_(
                and_(
                    Event.status == "live",
                    Event.commence_time <= live_start_cutoff,
                ),
                and_(
                    Event.status == "scheduled",
                    Event.commence_time >= now,
                    Event.commence_time <= upcoming_cutoff,
                ),
                and_(
                    Event.status.in_(["completed", "closed"]),
                    Event.commence_time >= recent_cutoff,
                ),
            )
        )
    )

    if sport_filter:
        query = query.where(Sport.key.ilike(f"%{sport_filter}%"))

    # Push static tags to SQL via GIN containment index (@>)
    # Only for tags that don't change after event creation (sport, league, tier, etc.)
    if static_tag_filter:
        import json as _json_mod

        query = query.where(
            Event.event_tags.op("@>")(cast(_json_mod.dumps(static_tag_filter), JSONB))
        )

    # For my_teams_only, push team filtering to SQL so we don't miss events
    # beyond the safety cap (the 7-day window can have 1000+ events across
    # all sports, but only ~20-40 involve the user's teams).
    if my_teams_only:
        team_conditions = []
        user_team_ids_list = (
            list(set(ctx.team_relations.keys())) if ctx.team_relations else []
        )
        if user_team_ids_list:
            team_conditions.append(Event.home_team_id.in_(user_team_ids_list))
            team_conditions.append(Event.away_team_id.in_(user_team_ids_list))
        if my_team_names:
            for tn in my_team_names:
                escaped = (
                    tn.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                team_conditions.append(Event.home_team_name.ilike(f"%{escaped}%"))
                team_conditions.append(Event.away_team_name.ilike(f"%{escaped}%"))
        if team_conditions:
            query = query.where(or_(*team_conditions))
        else:
            # No teams → nothing to show
            return []
        # Restrict to Tier 1+2 sports — prevents false positives from name
        # collisions with Tier 3 sports (e.g., "Boston" matching Boston College
        # hockey, Boston Breach esports, Boston River soccer). BR42/BR43.
        query = query.where(Sport.key.in_(MY_STUFF_ALLOWED_SPORT_KEYS))
        query = query.limit(200)  # Safety cap (user's teams only)
    else:
        # Prioritize live > recently completed > scheduled so the 500-row
        # cap doesn't crowd out live events when thousands of scheduled
        # events exist across all sports.
        query = query.order_by(
            case(
                (Event.status == "live", 0),
                (Event.status.in_(["completed", "closed"]), 1),
                else_=2,
            ),
            Event.commence_time.desc(),
        )
        query = query.limit(500)  # Safety cap (all events)

    result = await db.execute(query)
    events = result.scalars().all()

    if not events:
        return []

    # Batch fallback: for events where _compute_aggregate_probability() returns
    # None, query the latest win_prob_snapshot per event. This catches
    # Kalshi/Polymarket pregame data that's only in snapshots (not on Event model).
    snapshot_fallbacks: dict[int, float] = {}
    events_needing_fallback = [
        e for e in events if _compute_aggregate_probability(e) is None
    ]
    if events_needing_fallback:
        fallback_ids = [e.id for e in events_needing_fallback]
        from sqlalchemy import text

        fb_result = await db.execute(
            text("""
                SELECT DISTINCT ON (event_id) event_id, home_win_probability
                FROM win_prob_snapshots
                WHERE event_id = ANY(:ids)
                  AND home_win_probability IS NOT NULL
                ORDER BY event_id, captured_at DESC
            """),
            {"ids": fallback_ids},
        )
        for row in fb_result.all():
            snapshot_fallbacks[row.event_id] = round(float(row.home_win_probability), 6)

    # Score each event using aggregate probabilities from all available sources
    scored_items = []
    user_team_ids = set(ctx.team_relations.keys()) if my_teams_only else set()

    champ_probs = await _get_championship_probabilities(db)

    from app.utils.feed_scoring import compute_base_score, format_event_data
    from app.tasks.odds_polling import get_statpal_end_time

    for event in events:
        if not my_teams_only:
            if event.id in ctx.recent_dismissed_event_ids:
                continue
            if event.id in ctx.recent_seen_event_ids and event.status != "live":
                continue
            if (
                event.status == "live"
                and event.commence_time
                and event.commence_time < now - timedelta(hours=8)
            ):
                continue

        # my_teams_only: skip events that don't involve the user's teams
        if my_teams_only:
            # Try team_id matching first (fast, when IDs are linked)
            event_team_ids = {event.home_team_id, event.away_team_id} - {None}
            matched_by_id = bool(event_team_ids & user_team_ids)

            # Fall back to name matching (handles events without team_id links)
            matched_by_name = False
            if not matched_by_id and my_team_names:
                home_name = event.home_team_name or ""
                away_name = event.away_team_name or ""
                for team_name in my_team_names or []:
                    if _team_name_matches(team_name, home_name):
                        matched_by_name = True
                        break
                    if _team_name_matches(team_name, away_name):
                        matched_by_name = True
                        break

            if not matched_by_id and not matched_by_name:
                continue

        opening_home_prob = (
            float(event.opening_home_probability)
            if event.opening_home_probability
            else None
        )
        opening_away_prob = (
            float(event.opening_away_probability)
            if event.opening_away_probability
            else None
        )

        # Always compute aggregate from all available sources (ESPN, stat model,
        # Kalshi, Polymarket, sportsbook consensus). Falls back through tiers.
        current_home_prob = _compute_aggregate_probability(event)
        if current_home_prob is None and event.id in snapshot_fallbacks:
            current_home_prob = snapshot_fallbacks[event.id]
        current_away_prob = (
            round(1.0 - current_home_prob, 6) if current_home_prob is not None else None
        )

        # Skip events without any probability data:
        # - Scheduled: StatPal-created events not yet matched to Odds API
        # - Completed/closed with no scores: no odds movement, no final score
        #   = terrible UX (empty chart, no data). These are typically niche
        #   sports where only StatPal has schedules but no odds coverage.
        if current_home_prob is None and event.status == "scheduled":
            continue
        if (
            current_home_prob is None
            and event.status in ("completed", "closed")
            and not event.home_score
            and not event.away_score
        ):
            continue

        # Track whether we have sportsbook-specific data or only aggregate
        has_sportsbook_odds = opening_home_prob is not None
        prob_source = (
            None
            if has_sportsbook_odds
            else ("aggregate" if current_home_prob is not None else None)
        )

        # Auto-detect preseason as exhibition from sport key when
        # llm_importance isn't set (ESPN doesn't sync preseason sport keys)
        importance = event.llm_importance
        if not importance or importance == "unknown":
            sport_key_str = event.sport.key if event.sport else ""
            if "preseason" in sport_key_str:
                importance = "exhibition"

        highlight_result = compute_highlight(
            status=event.status,
            commence_time=event.commence_time,
            sport_key=event.sport.key if event.sport else None,
            current_home_prob=current_home_prob,
            current_away_prob=current_away_prob,
            current_home_spread=(
                float(event.opening_home_spread) if event.opening_home_spread else None
            ),
            current_over_under=(
                float(event.opening_over_under) if event.opening_over_under else None
            ),
            opening_home_prob=opening_home_prob,
            opening_away_prob=opening_away_prob,
            opening_home_spread=(
                float(event.opening_home_spread) if event.opening_home_spread else None
            ),
            opening_over_under=(
                float(event.opening_over_under) if event.opening_over_under else None
            ),
            opening_favorite=event.opening_favorite,
            now=now,
            home_team_name=event.home_team_name,
            away_team_name=event.away_team_name,
            importance=importance,
            end_time=event.statpal_end_time,
            period=event.period,
        )

        sport_key = event.sport.key if event.sport else None
        _event_tags = event.event_tags or []

        _source_count = (
            len(event.win_probability_sources) if event.win_probability_sources else 0
        )
        _game_progress, _ = parse_game_progress(event.period, sport_key)

        base_score, extra_reasons = compute_base_score(
            highlight_score=highlight_result.score,
            highlight_reasons=highlight_result.reasons,
            home_champ_prob=(
                champ_probs.get(event.home_team_id, 0) if event.home_team_id else 0
            ),
            away_champ_prob=(
                champ_probs.get(event.away_team_id, 0) if event.away_team_id else 0
            ),
            sport_key=sport_key,
            now=now,
            event_tags=_event_tags,
            event_status=event.status,
            raw_ei=float(event.raw_ei) if event.raw_ei else None,
            get_season_multiplier_fn=get_season_multiplier,
            get_league_tier_fn=get_league_tier,
            home_score=event.home_score,
            away_score=event.away_score,
            source_count=_source_count,
            game_progress=_game_progress,
            ei_metadata=event.ei_metadata,
        )
        highlight_result.reasons = extra_reasons

        # Apply personalization multiplier
        p_result = compute_event_multiplier(
            ctx=ctx,
            home_team_id=event.home_team_id,
            away_team_id=event.away_team_id,
            sport_key=event.sport.key if event.sport else None,
            event_id=event.id,
            home_score=event.home_score,
            away_score=event.away_score,
            feature_tokens=list(
                _discover_feature_tokens(
                    item_name=f"{event.away_team_name} vs {event.home_team_name}",
                    category=_personalization_category_from_sport_key(sport_key),
                    item_type="event",
                )
            )
            + list(
                _discover_semantic_tokens(
                    item_name=f"{event.away_team_name} vs {event.home_team_name}",
                    category=_personalization_category_from_sport_key(sport_key),
                    item_type="event",
                )
            ),
        )
        personalized_score = min(98, int(base_score * p_result.multiplier))

        # --- "Nah" sport hard filter ---
        # If the user explicitly said "Nah" to this sport, don't show it
        # UNLESS it's a championship or playoff game.  A user who said "Nah"
        # to soccer shouldn't see Champions League regular matches, but a
        # World Cup Final is a genuine cultural event worth surfacing.
        is_nah = any("sport_nah" in r for r in p_result.reasons)
        if is_nah and not my_teams_only:
            if importance not in ("championship", "playoff"):
                continue
            # Championship/playoff in a "Nah" sport: override but explain
            personalized_score = max(personalized_score, 35)

        # --- "If it's wild" sport — higher bar ---
        # The user said "If it's wild" (affinity 0.1) — only show if something
        # genuinely unusual is happening (upset, lead change, big swing, playoff).
        # A live close game alone isn't enough.
        is_low_affinity = any("sport_suppress" in r for r in p_result.reasons)
        if is_low_affinity and not my_teams_only:
            # Require a genuinely notable game — live+close+tier1 = 75 * 0.7 = 52
            # isn't enough. Need upset(+20), lead change(+8), big swing(+15),
            # or playoff(+15) to clear the bar.
            min_score = 55
        elif my_teams_only:
            min_score = 0
        elif p_result.is_personalized and p_result.multiplier >= 1.0:
            min_score = 10
        else:
            min_score = 30
        if personalized_score < min_score:
            continue

        # Generate reason text
        reason = generate_event_reason(
            home_team=event.home_team_name,
            away_team=event.away_team_name,
            status=event.status,
            highlight_reasons=highlight_result.reasons,
            home_probability=current_home_prob,
            away_probability=current_away_prob,
            opening_home_prob=opening_home_prob,
            home_score=event.home_score,
            away_score=event.away_score,
            event_tags=_event_tags,
        )

        # Compute event_tags on-the-fly (fresh, not stale persisted)
        inline_tags = compute_event_tags(
            sport_key=event.sport.key if event.sport else "",
            status=event.status,
            commence_time=event.commence_time,
            llm_importance=importance,
            llm_gender=getattr(event, "llm_gender", None),
            llm_level=getattr(event, "llm_level", None),
            llm_league=getattr(event, "llm_league", None),
            raw_ei=float(event.raw_ei) if event.raw_ei else None,
            broadcast_info=getattr(event, "broadcast_info", None),
            highlight_result=highlight_result,
        )

        if tag_filter:
            if not all(t in inline_tags for t in tag_filter):
                continue

        ended_at = (
            get_statpal_end_time(event)
            if event.status in ("completed", "closed")
            else None
        )
        event_data = format_event_data(
            event_id=event.id,
            external_id=event.external_id,
            sport_key=sport_key,
            sport_name=event.sport.name if event.sport else None,
            home_team=event.home_team_name,
            away_team=event.away_team_name,
            commence_time=event.commence_time,
            status=event.status,
            home_score=event.home_score,
            away_score=event.away_score,
            current_home_prob=current_home_prob,
            current_away_prob=current_away_prob,
            opening_home_prob=opening_home_prob,
            opening_away_prob=opening_away_prob,
            opening_favorite=event.opening_favorite,
            win_probability_sources=event.win_probability_sources,
            prob_source=prob_source,
            game_clock=getattr(event, "game_clock", None),
            period=event.period,
            broadcast_info=getattr(event, "broadcast_info", None),
            highlight_label=get_highlight_label(highlight_result),
            raw_ei=float(event.raw_ei) if event.raw_ei else None,
            inline_tags=inline_tags,
            ended_at=ended_at,
        )
        event_data["temporal_badge"] = _compute_temporal_badge(
            status=event.status,
            now=now,
        )
        event_data["sport_label"] = _get_sport_label(sport_key)

        sort_time = event.commence_time.timestamp()
        if event.status == "live":
            sort_time = now.timestamp() + 86400

        item = {
            "type": "event",
            "score": personalized_score,
            "reason": reason,
            "headline": get_highlight_label(highlight_result),
            "data": event_data,
            "_sort_time": sort_time,
        }
        personalization_trace = _build_personalization_trace(
            ctx=ctx,
            item_type="event",
            category=_personalization_category_from_sport_key(sport_key),
            base_score=base_score,
            final_score=personalized_score,
            p_result=p_result,
        )
        if personalization_trace:
            item["personalization_trace"] = personalization_trace

        # Include personalization debug info when score was boosted/suppressed
        if p_result.is_personalized:
            item["personalized"] = True
            item["base_score"] = base_score
            item["multiplier"] = round(p_result.multiplier, 2)
            item["personalization_reasons"] = p_result.reasons

        scored_items.append(item)

    return scored_items


async def _score_sports_mode_futures(
    db: AsyncSession,
    now: datetime,
    sport_filter: Optional[str],
    ctx: PersonalizationContext,
    my_teams_only: bool = False,
    my_team_names: Optional[list] = None,
    my_team_sport_categories: Optional[dict[str, set[str]]] = None,
) -> list[dict]:
    """Fast sports-mode futures: single query, no editorial pools.

    Returns the same data shape as ``_score_futures`` but skips the 10+
    candidate-pool queries, external-curator recall, interestingness Redis
    cache, and quality/editorial pipelines that make Discover scoring take
    ~5 seconds cold.  Instead runs ONE query for sports futures ordered by
    tier then volume, scores them with the standard highlight/quality
    pipeline, and returns.  Typically finishes in <200 ms.
    """
    base_filters = [
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= now,
        ),
        ~FuturesMarket.name.like("% vs %"),
        ~FuturesMarket.name.like("% vs. %"),
    ]

    sports_filter = FuturesMarket.llm_sport_category.in_(DISCOVER_SPORTS_CATEGORIES)

    if sport_filter:
        sports_filter = and_(
            sports_filter,
            or_(
                FuturesMarket.llm_sport_category.ilike(f"%{sport_filter}%"),
                FuturesMarket.external_id.ilike(f"%{sport_filter}%"),
            ),
        )

    # Single query: top 120 sports futures by tier then volume
    id_result = await db.execute(
        select(FuturesMarket.id)
        .where(*base_filters, sports_filter)
        .order_by(
            FuturesMarket.market_tier.asc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        )
        .limit(120)
    )
    market_ids = list(id_result.scalars().all())
    if not market_ids:
        return []

    base_options = [
        load_only(
            FuturesMarket.id,
            FuturesMarket.name,
            FuturesMarket.source,
            FuturesMarket.external_id,
            FuturesMarket.sport_id,
            FuturesMarket.category,
            FuturesMarket.llm_sport_category,
            FuturesMarket.market_tier,
            FuturesMarket.canonical_market_key,
            FuturesMarket.group_id,
            FuturesMarket.group_type,
            FuturesMarket.image_url,
            FuturesMarket.hook_description,
            FuturesMarket.hook_generated_at,
            FuturesMarket.hook_leader_at_generation,
            FuturesMarket.market_metadata,
            FuturesMarket.curation_score_adj,
            FuturesMarket.volume_24h,
            FuturesMarket.updated_at,
            FuturesMarket.commence_time,
            FuturesMarket.resolution_date,
            FuturesMarket.status,
            FuturesMarket.created_at,
            FuturesMarket.llm_league,
            FuturesMarket.llm_gender,
            FuturesMarket.llm_level,
        ),
        selectinload(FuturesMarket.outcomes).load_only(
            FuturesOutcome.id,
            FuturesOutcome.name,
            FuturesOutcome.team_id,
            FuturesOutcome.current_probability,
            FuturesOutcome.probability_change_24h,
            FuturesOutcome.rank,
            FuturesOutcome.rank_change_24h,
            FuturesOutcome.opening_probability,
        ),
        selectinload(FuturesMarket.sport).load_only(Sport.key, Sport.name),
    ]

    markets_result = await db.execute(
        select(FuturesMarket)
        .options(*base_options)
        .where(FuturesMarket.id.in_(market_ids))
    )
    markets_by_id = {
        market.id: market for market in markets_result.scalars().unique().all()
    }
    markets = [markets_by_id[mid] for mid in market_ids if mid in markets_by_id]

    if not markets:
        return []

    # Build canonical source counts for the candidate set
    candidate_canonical_keys = {
        m.canonical_market_key for m in markets if m.canonical_market_key
    }
    canonical_source_counts = await _get_canonical_source_counts(
        db, keys=candidate_canonical_keys
    )

    user_team_ids = set(ctx.team_relations.keys()) if ctx.team_relations else set()

    scored_items: list[dict] = []
    for market in markets:
        # --- Staleness/settlement filters (same as _score_futures) ---
        if market.resolution_date:
            res_dt = _utc(market.resolution_date)
            if res_dt and res_dt < now:
                continue

        sorted_outcomes = sorted(
            market.outcomes,
            key=lambda o: float(o.current_probability) if o.current_probability else 0,
            reverse=True,
        )
        outcomes_data = []
        leader_name = None
        leader_prob = None

        for o in sorted_outcomes[:10]:
            prob = float(o.current_probability) if o.current_probability else None
            change = (
                float(o.probability_change_24h) if o.probability_change_24h else None
            )
            outcomes_data.append(
                {
                    "name": o.name,
                    "probability": prob,
                    "probability_change_24h": change,
                    "rank": o.rank,
                    "rank_change_24h": o.rank_change_24h,
                    "opening_probability": (
                        float(o.opening_probability) if o.opening_probability else None
                    ),
                }
            )

        if sorted_outcomes:
            leader = sorted_outcomes[0]
            leader_name = leader.name
            leader_prob = (
                float(leader.current_probability)
                if leader.current_probability
                else None
            )

        probs_available = [
            o["probability"] for o in outcomes_data if o["probability"] is not None
        ]

        # Filter settled/dead markets
        all_settled = len(probs_available) >= 2 and all(
            p < 0.05 or p > 0.95 for p in probs_available
        )
        if all_settled:
            continue
        if leader_prob is not None and leader_prob >= 0.97:
            continue
        if (
            leader_prob is not None
            and leader_prob <= 0.03
            and len(probs_available) <= 2
        ):
            continue
        if probs_available and all(p < 0.001 for p in probs_available):
            continue
        if not probs_available and market.outcomes:
            continue

        has_any_movement = any(
            o["probability_change_24h"] is not None
            and abs(o["probability_change_24h"]) > 0.001
            for o in outcomes_data
        )
        if market.updated_at:
            days_stale = (
                now
                - market.updated_at.replace(
                    tzinfo=(
                        timezone.utc
                        if market.updated_at.tzinfo is None
                        else market.updated_at.tzinfo
                    )
                )
            ).total_seconds() / 86400
            if days_stale > 2 and not has_any_movement:
                continue

        max_recent_movement = max(
            (
                abs(o["probability_change_24h"])
                for o in outcomes_data
                if o["probability_change_24h"] is not None
            ),
            default=0.0,
        )
        resolved_threshold, opening_threshold = _effective_resolution_thresholds(
            market.llm_sport_category
        )
        is_effectively_resolved = (
            leader_prob is not None and leader_prob >= resolved_threshold
        )
        if is_effectively_resolved:
            leader_opening = None
            for o in outcomes_data:
                if o["name"] == leader_name:
                    leader_opening = o.get("opening_probability")
                    break
            sports_effectively_settled = (
                leader_opening is not None
                and leader_opening < opening_threshold
                and any(o["probability_change_24h"] is not None for o in outcomes_data)
                and max_recent_movement < 0.01
            )
            if sports_effectively_settled or (
                leader_opening is None or leader_opening >= opening_threshold
            ):
                continue

        # Soft-settled binary
        if (
            leader_prob is not None
            and leader_prob >= 0.60
            and len(probs_available) == 2
        ):
            if max_recent_movement < 0.02:
                leader_opening_prob = None
                for o in outcomes_data:
                    if o["name"] == leader_name:
                        leader_opening_prob = o.get("opening_probability")
                        break
                if leader_opening_prob is None or leader_opening_prob >= 0.50:
                    continue

        if (market.llm_sport_category or "").lower() == "golf" and market.commence_time:
            commence_time = _utc(market.commence_time)
            if commence_time and commence_time < now - timedelta(days=6):
                continue

        # --- my_teams_only filtering ---
        if my_teams_only:
            market_sport_key = market.sport.key if market.sport else None
            if market_sport_key and market_sport_key not in MY_STUFF_ALLOWED_SPORT_KEYS:
                continue
            if not market_sport_key and market.llm_sport_category:
                if market.llm_sport_category not in MY_STUFF_ALLOWED_CATEGORIES:
                    continue

            outcome_team_ids = [
                o.team_id for o in market.outcomes if o.team_id is not None
            ]
            matched_by_id = bool(set(outcome_team_ids) & user_team_ids)
            matched_by_name = False
            if not matched_by_id and my_team_names:
                market_cat = market.llm_sport_category
                if not market_cat and market_sport_key:
                    market_cat = _personalization_category_from_sport_key(
                        market_sport_key
                    )
                for o in market.outcomes:
                    if o.name:
                        for team_name in my_team_names or []:
                            if _team_name_matches(team_name, o.name):
                                if my_team_sport_categories and market_cat:
                                    team_cats = my_team_sport_categories.get(team_name)
                                    if team_cats and market_cat not in team_cats:
                                        continue
                                matched_by_name = True
                                break
                    if matched_by_name:
                        break
            if not matched_by_id and not matched_by_name:
                continue

        # --- Scoring (lightweight — no editorial/quality caps) ---
        source_count = 1
        if market.canonical_market_key:
            source_count = canonical_source_counts.get(market.canonical_market_key, 1)

        highlight_result = compute_futures_highlight(
            market_tier=market.market_tier,
            sport_category=market.llm_sport_category,
            resolution_date=market.resolution_date,
            outcomes=outcomes_data,
            source_count=source_count,
            now=now,
            market_name=market.name,
            volume_24h=market.volume_24h,
            curation_score_adj=market.__dict__.get("curation_score_adj", 0) or 0,
        )

        top_mover_name = highlight_result.top_mover_name
        top_mover_change = None
        if top_mover_name:
            for o in outcomes_data:
                if o["name"] == top_mover_name and o.get("probability_change_24h"):
                    top_mover_change = o["probability_change_24h"]
                    break

        top_surprise_name = None
        top_surprise_change = None
        for o in outcomes_data:
            opening = o.get("opening_probability")
            current = o.get("probability")
            if opening is None or current is None:
                continue
            surprise_change = current - opening
            if top_surprise_change is None or abs(surprise_change) > abs(
                top_surprise_change
            ):
                top_surprise_name = o.get("name")
                top_surprise_change = surprise_change

        _h_leader = (
            humanize_binary_outcome_name(leader_name, market.name)
            if leader_name
            else leader_name
        )
        _h_mover = (
            humanize_binary_outcome_name(top_mover_name, market.name)
            if top_mover_name
            else top_mover_name
        )
        _h_surprise = (
            humanize_binary_outcome_name(top_surprise_name, market.name)
            if top_surprise_name
            else top_surprise_name
        )

        headline = (
            generate_futures_headline(
                highlight_reasons=highlight_result.reasons,
                top_mover_name=_h_mover,
                top_mover_change=top_mover_change,
                top_surprise_name=_h_surprise,
                top_surprise_change=top_surprise_change,
                leader_name=_h_leader,
                leader_probability=leader_prob,
                source_count=source_count,
                market_name=market.name,
            )
            or highlight_result.primary_reason
        )
        context_summary = generate_futures_context_summary(
            headline=headline,
            highlight_reasons=highlight_result.reasons,
            market_name=market.name,
            leader_name=_h_leader,
            leader_probability=leader_prob,
            source_count=source_count,
        )

        quality = classify_market_quality(
            market_name=market.name,
            sport_category=market.llm_sport_category,
            outcome_names=[o.name for o in market.outcomes if o.name],
            external_id=market.external_id,
            status=market.status,  # R6: resolved sports never surface
        )
        if quality.quality_class == "suppress":
            continue

        effective_hook = market.hook_description
        if effective_hook and is_hook_stale(
            hook_description=effective_hook,
            hook_generated_at=market.hook_generated_at,
            hook_leader_at_generation=market.hook_leader_at_generation,
            current_leader_name=leader_name,
            current_leader_probability=leader_prob,
            market_metadata=market.market_metadata,
            now=now,
        ):
            effective_hook = None

        base_score = apply_quality_score(highlight_result.score, quality)
        base_score = apply_explanation_quality_score(
            base_score,
            hook_description=effective_hook,
            headline=headline,
            quality=quality,
        )

        # Apply personalization
        outcome_team_ids_for_p = [
            o.team_id for o in market.outcomes if o.team_id is not None
        ]
        outcome_names = [o.name for o in market.outcomes if o.name]
        p_result = compute_futures_multiplier(
            ctx=ctx,
            sport_category=market.llm_sport_category,
            outcome_team_ids=outcome_team_ids_for_p,
            futures_market_id=market.id,
            sport_key=market.sport.key if market.sport else None,
            outcome_names=outcome_names,
        )
        personalized_score = min(98, int(base_score * p_result.multiplier))
        if not my_teams_only and personalized_score < 15:
            continue

        reason = generate_futures_reason(
            market_name=market.name,
            highlight_reasons=highlight_result.reasons,
            top_mover_name=_h_mover,
            top_mover_change=top_mover_change,
            top_surprise_name=_h_surprise,
            top_surprise_change=top_surprise_change,
            leader_name=_h_leader,
            leader_probability=leader_prob,
            source_count=source_count,
        )

        # Build compact feed data (same shape as _score_futures)
        top_outcomes_data = [
            {
                "id": o.id,
                "name": o.name,
                "probability": (
                    float(o.current_probability) if o.current_probability else None
                ),
                "rank": o.rank,
                "movement": (
                    float(o.probability_change_24h)
                    if o.probability_change_24h
                    else None
                ),
            }
            for o in sorted_outcomes[:3]
        ]
        top_outcomes_data = humanize_outcome_names_for_feed(
            top_outcomes_data, market.name
        )
        top_outcomes_data = _normalize_feed_probabilities(
            top_outcomes_data, sorted_outcomes
        )

        source_names = (
            (_canonical_source_names_cache or {}).get(
                market.canonical_market_key, [market.source]
            )
            if market.canonical_market_key
            else [market.source]
        )
        all_outcomes_for_card = [
            {
                "name": o.name,
                "probability": (
                    float(o.current_probability)
                    if o.current_probability is not None
                    else None
                ),
                "movement": (
                    float(o.probability_change_24h)
                    if o.probability_change_24h is not None
                    else None
                ),
            }
            for o in sorted_outcomes
        ]
        discover_card = classify_discover_card_archetype(
            name=market.name,
            category=market.llm_sport_category,
            outcomes=all_outcomes_for_card,
            outcome_count=len(market.outcomes),
            source_count=source_count,
            sources=source_names,
            group_id=market.group_id,
            group_type=market.group_type,
            canonical_market_key=market.canonical_market_key,
            status=market.status,
        )

        futures_data = {
            "id": market.id,
            "name": market.name,
            "sport": market.sport.key if market.sport else None,
            "sport_name": market.sport.name if market.sport else None,
            "llm_sport_category": market.llm_sport_category,
            "source": market.source,
            "source_count": source_count,
            "sources": source_names,
            "market_tier": market.market_tier,
            "status": market.status,
            "resolution_date": (
                market.resolution_date.isoformat() if market.resolution_date else None
            ),
            "top_outcomes": top_outcomes_data,
            "outcome_count": len(market.outcomes),
            "canonical_market_key": market.canonical_market_key,
            "group_id": market.group_id,
            "group_type": market.group_type,
            "discover_card": discover_card,
            "image_url": market.image_url,
            "hook_description": effective_hook,
            "temporal_badge": _compute_temporal_badge(
                status=market.status,
                resolution_date=market.resolution_date,
                created_at=market.created_at,
                now=now,
            ),
        }

        inline_market_tags = compute_market_tags(
            llm_sport_category=market.llm_sport_category,
            llm_league=getattr(market, "llm_league", None),
            llm_gender=getattr(market, "llm_gender", None),
            llm_level=getattr(market, "llm_level", None),
            market_tier=market.market_tier,
            category=market.category,
            status=market.status,
            source=market.source,
        )
        futures_data["market_tags"] = inline_market_tags

        sort_time = now.timestamp()
        if market.resolution_date:
            days_until = (market.resolution_date - now).total_seconds()
            sort_time = now.timestamp() + max(0, 86400 * 30 - days_until)

        item: dict = {
            "type": "futures",
            "score": personalized_score,
            "reason": reason,
            "headline": headline,
            "context_summary": context_summary,
            "data": futures_data,
            "_sort_time": sort_time,
            "_quality_class": quality.quality_class,
            "_quality_family_key": quality.family_key,
            "_quality_story_key": quality.story_key,
        }
        if p_result.is_personalized:
            item["personalized"] = True
            item["base_score"] = base_score
            item["multiplier"] = round(p_result.multiplier, 2)
            item["personalization_reasons"] = p_result.reasons

        scored_items.append(item)

    # Apply same dedup + caps as full pipeline
    scored_items = _dedupe_futures_by_group_id(scored_items)
    scored_items = cap_low_quality_families(scored_items, cap=1)
    scored_items = diversify_quality_families(
        scored_items,
        exact_family_cap=1,
        story_family_cap=5,
    )

    return scored_items


async def _score_futures(
    db: AsyncSession,
    now: datetime,
    sport_filter: Optional[str],
    ctx: PersonalizationContext,
    my_teams_only: bool = False,
    my_team_names: Optional[list] = None,
    my_team_sport_categories: Optional[dict[str, set[str]]] = None,
    tag_filter: Optional[list[str]] = None,
    static_tag_filter: Optional[list[str]] = None,
    timing_records: Optional[list[dict[str, float | str]]] = None,
    timing_started_at: float | None = None,
    config: dict[str, float | bool] | None = None,
) -> list[dict]:
    """Score and format futures markets for the feed.

    Uses per-category queries to guarantee diversity. A single big query
    sorted by resolution_date is dominated by crypto's 8,955 five-minute
    markets, so we query each category separately.
    """
    timing_previous_at = time.perf_counter()
    config = config or _discover_runtime_config_defaults()
    stale_no_movement_days = float(config.get("stale_no_movement_days", 2))
    no_resolution_stale_days = float(config.get("no_resolution_stale_days", 5))

    # --- Precomputed interestingness cache ---
    # Load all interestingness scores from Redis in one batch after candidate
    # IDs are known (deferred below). The blend weight is controllable via a
    # Redis key so it can be tuned or killed without redeployment.
    _interestingness_cache: dict[int, dict] | None = None
    _interestingness_blend_weight: float = 0.0

    def mark_timing(
        stage: str,
        *,
        since_at: float | None = None,
        update_previous: bool = True,
    ) -> None:
        nonlocal timing_previous_at
        if timing_records is None or timing_started_at is None:
            return
        recorded_at = _record_feed_timing(
            timing_records,
            timing_started_at,
            since_at if since_at is not None else timing_previous_at,
            f"futures.{stage}",
        )
        if update_previous:
            timing_previous_at = recorded_at

    # === BASE FILTERS ===
    base_filters = [
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= now,
        ),
        ~FuturesMarket.name.like("% vs %"),
        ~FuturesMarket.name.like("% vs. %"),
        # NOTE: '% at %' filter deliberately removed — it killed non-sports
        # markets like "S&P at 4pm", "temperature at NYC". The event_id IS NULL
        # filter already excludes game matchups.
    ]

    base_options = [
        load_only(
            FuturesMarket.id,
            FuturesMarket.name,
            FuturesMarket.source,
            FuturesMarket.external_id,
            FuturesMarket.sport_id,
            FuturesMarket.category,
            FuturesMarket.llm_sport_category,
            FuturesMarket.market_tier,
            FuturesMarket.canonical_market_key,
            FuturesMarket.group_id,
            FuturesMarket.group_type,
            FuturesMarket.image_url,
            FuturesMarket.hook_description,
            FuturesMarket.hook_generated_at,
            FuturesMarket.hook_leader_at_generation,
            FuturesMarket.market_metadata,
            FuturesMarket.curation_score_adj,
            FuturesMarket.volume_24h,
            FuturesMarket.updated_at,
            FuturesMarket.commence_time,
            FuturesMarket.resolution_date,
            FuturesMarket.status,
            FuturesMarket.created_at,
            FuturesMarket.llm_league,
            FuturesMarket.llm_gender,
            FuturesMarket.llm_level,
        ),
        selectinload(FuturesMarket.outcomes).load_only(
            FuturesOutcome.id,
            FuturesOutcome.name,
            FuturesOutcome.team_id,
            FuturesOutcome.current_probability,
            FuturesOutcome.probability_change_24h,
            FuturesOutcome.rank,
            FuturesOutcome.rank_change_24h,
            FuturesOutcome.opening_probability,
        ),
        selectinload(FuturesMarket.sport).load_only(Sport.key, Sport.name),
    ]

    # For my_teams_only: use full Team.name (not alternate_names) to avoid false positives.
    user_team_ids = set(ctx.team_relations.keys()) if ctx.team_relations else set()

    # === TWO-POOL QUERY — ensure non-sports markets compete fairly ===
    # Sports outnumber non-sports ~10:1 in the DB, so a single query
    # returns ~90% sports. Pull sports and non-sports separately with
    # generous limits, then score everything together.
    id_filters = list(base_filters)
    if sport_filter:
        id_filters.append(
            or_(
                FuturesMarket.llm_sport_category.ilike(f"%{sport_filter}%"),
                FuturesMarket.external_id.ilike(f"%{sport_filter}%"),
            )
        )

    if static_tag_filter:
        import json as _json_mod

        id_filters.append(
            FuturesMarket.market_tags.op("@>")(
                cast(_json_mod.dumps(static_tag_filter), JSONB)
            )
        )

    # Pool 1: sports futures (capped — tier-ordered so best surface first).
    # Limit was 50 but that starved Tier 2 sports (MMA, tennis, soccer)
    # because Tier 1 sports filled the pool first. Raised to 80 to ensure
    # UFC, Grand Slam tennis, and World Cup markets enter the candidate set.
    sports_query = (
        select(FuturesMarket.id)
        .where(
            *id_filters,
            FuturesMarket.llm_sport_category.in_(DISCOVER_SPORTS_CATEGORIES),
        )
        .order_by(
            FuturesMarket.market_tier.asc().nulls_last(),
            FuturesMarket.resolution_date.asc().nulls_last(),
        )
        .limit(80)
    )

    sports_postseason_query = (
        select(FuturesMarket.id)
        .where(
            *id_filters,
            _SPORTS_POSTSEASON_SQL_FILTER,
        )
        .order_by(
            FuturesMarket.resolution_date.asc().nulls_last(),
            FuturesMarket.updated_at.desc().nulls_last(),
        )
        .limit(80)
    )

    # Pool 1c: broad sports futures with mainstream Discover value. This keeps
    # World Cup / Super Bowl / Finals style markets from being crowded out by
    # generic tier ordering while still passing through normal story caps.
    sports_editorial_recall_query = (
        select(FuturesMarket.id)
        .where(
            *id_filters,
            FuturesMarket.llm_sport_category.in_(DISCOVER_SPORTS_CATEGORIES),
            _discover_sports_editorial_recall_filter(),
        )
        .order_by(
            FuturesMarket.market_tier.asc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
            FuturesMarket.updated_at.desc().nulls_last(),
        )
        .limit(80)
    )

    non_sports_filter = or_(
        ~FuturesMarket.llm_sport_category.in_(DISCOVER_SPORTS_CATEGORIES),
        FuturesMarket.llm_sport_category.is_(None),
    )

    # Pool 2a: non-sports futures by liquidity. Good for markets people are
    # actively trading, but too narrow on its own because commodities/weather
    # ladders dominate volume.
    nonsports_query = (
        select(FuturesMarket.id)
        .where(
            *id_filters,
            non_sports_filter,
        )
        .order_by(
            FuturesMarket.volume_24h.desc().nulls_last(),
            FuturesMarket.market_tier.asc().nulls_last(),
        )
        .limit(120)
    )

    # Pool 2b: non-sports by actual movement. Uses denormalized
    # max_movement_24h column (updated by Celery task) instead of a
    # GROUP BY subquery on futures_outcomes. Cuts this pool from ~9s to <100ms.
    nonsports_movement_query = (
        select(FuturesMarket.id)
        .where(
            *id_filters,
            non_sports_filter,
            FuturesMarket.max_movement_24h.isnot(None),
            FuturesMarket.max_movement_24h > 0,
        )
        .order_by(
            FuturesMarket.max_movement_24h.desc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        )
        .limit(100)
    )

    # Pool 2c: enriched markets. Hook/image enrichment is a useful prior that a
    # market is feed-shaped, and it helps lower-volume good stories enter the
    # scoring stage.
    nonsports_enriched_query = (
        select(FuturesMarket.id)
        .where(
            *id_filters,
            non_sports_filter,
            or_(
                FuturesMarket.hook_description.isnot(None),
                FuturesMarket.image_url.isnot(None),
            ),
        )
        .order_by(
            FuturesMarket.hook_generated_at.desc().nulls_last(),
            FuturesMarket.updated_at.desc().nulls_last(),
        )
        .limit(100)
    )

    # Pool 2d: high-texture editorial recall. Uses a 5-minute cached ID list
    # instead of running 44 ILIKE patterns (~580-1870ms) on every request.
    _editorial_ids = await _get_editorial_recall_ids(db)
    nonsports_editorial_recall_query = (
        select(FuturesMarket.id)
        .where(
            *id_filters,
            non_sports_filter,
            (
                FuturesMarket.id.in_(_editorial_ids)
                if _editorial_ids
                else FuturesMarket.id == -1
            ),
        )
        .order_by(
            FuturesMarket.market_tier.asc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
            FuturesMarket.updated_at.desc().nulls_last(),
        )
        .limit(80)
    )

    # Pool 2e: soon-resolving markets. Timeliness matters, but this pool is
    # still scored and quality-capped later, so routine ladders do not get a
    # free pass.
    nonsports_timely_query = (
        select(FuturesMarket.id)
        .where(
            *id_filters,
            non_sports_filter,
            FuturesMarket.resolution_date.isnot(None),
        )
        .order_by(
            FuturesMarket.resolution_date.asc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        )
        .limit(80)
    )

    candidate_queries_started_at = timing_previous_at
    external_curator_recall_ids = await _external_curator_recall_market_ids(
        db,
        id_filters,
        row_limit=80,
        market_limit=80,
    )
    mark_timing("pool_external_curator_recall")
    sports_result = await db.execute(sports_query)
    mark_timing("pool_sports")
    sports_postseason_result = await db.execute(sports_postseason_query)
    mark_timing("pool_sports_postseason")
    sports_editorial_recall_result = await db.execute(sports_editorial_recall_query)
    mark_timing("pool_sports_editorial_recall")
    nonsports_result = await db.execute(nonsports_query)
    mark_timing("pool_nonsports_volume")
    nonsports_movement_result = await db.execute(nonsports_movement_query)
    mark_timing("pool_nonsports_movement")
    nonsports_enriched_result = await db.execute(nonsports_enriched_query)
    mark_timing("pool_nonsports_enriched")
    nonsports_editorial_recall_result = await db.execute(
        nonsports_editorial_recall_query
    )
    mark_timing("pool_nonsports_editorial_recall")
    nonsports_timely_result = await db.execute(nonsports_timely_query)
    mark_timing("pool_nonsports_timely")
    mark_timing(
        "candidate_queries",
        since_at=candidate_queries_started_at,
        update_previous=False,
    )

    candidate_market_ids = (
        list(external_curator_recall_ids)
        + list(sports_result.scalars().all())
        + list(sports_postseason_result.scalars().all())
        + list(sports_editorial_recall_result.scalars().all())
        + list(nonsports_result.scalars().all())
        + list(nonsports_movement_result.scalars().all())
        + list(nonsports_enriched_result.scalars().all())
        + list(nonsports_editorial_recall_result.scalars().all())
        + list(nonsports_timely_result.scalars().all())
    )
    seen_market_ids: set[int] = set()
    market_ids: list[int] = []
    for market_id in candidate_market_ids:
        if market_id in seen_market_ids:
            continue
        seen_market_ids.add(market_id)
        market_ids.append(market_id)

    if not market_ids:
        mark_timing("candidate_dedupe")
        return []
    mark_timing("candidate_dedupe")

    markets_result = await db.execute(
        select(FuturesMarket)
        .options(*base_options)
        .where(FuturesMarket.id.in_(market_ids))
    )
    markets_by_id = {
        market.id: market for market in markets_result.scalars().unique().all()
    }
    markets = [markets_by_id[mid] for mid in market_ids if mid in markets_by_id]
    mark_timing("market_load")

    if not markets:
        return []

    # Build canonical key → source count map for cross-source scoring
    candidate_canonical_keys = {
        market.canonical_market_key for market in markets if market.canonical_market_key
    }
    canonical_source_counts = await _get_canonical_source_counts(
        db, keys=candidate_canonical_keys
    )
    mark_timing("canonical_counts")

    # --- Load precomputed interestingness scores from Redis ---
    try:
        from app.tasks.redis_state import get_async_redis_client

        _int_redis = get_async_redis_client()
        # Read blend weight (default 0.2; set to 0 to disable)
        raw_weight = await _int_redis.get("interestingness:blend_weight")
        if raw_weight is not None:
            try:
                _interestingness_blend_weight = float(
                    raw_weight.decode()
                    if isinstance(raw_weight, bytes)
                    else str(raw_weight)
                )
            except (ValueError, TypeError):
                _interestingness_blend_weight = 0.2
        else:
            _interestingness_blend_weight = 0.2  # default

        if _interestingness_blend_weight > 0:
            _int_keys = [f"interestingness:{mid}" for mid in market_ids]
            if _int_keys:
                _int_values = await _int_redis.mget(_int_keys)
                _interestingness_cache = {}
                for mid, raw_val in zip(market_ids, _int_values):
                    if raw_val is not None:
                        try:
                            parsed = _json_module.loads(
                                raw_val.decode()
                                if isinstance(raw_val, bytes)
                                else raw_val
                            )
                            _interestingness_cache[mid] = parsed
                        except (ValueError, TypeError):
                            pass
        await _int_redis.aclose()
    except Exception:
        logger.debug(
            "Interestingness cache load failed — skipping blend", exc_info=True
        )
        _interestingness_cache = None
        _interestingness_blend_weight = 0.0
    mark_timing("interestingness_cache")

    scored_items = []
    for market in markets:
        is_recycled = False
        if not my_teams_only:
            if market.id in ctx.recent_dismissed_futures_ids:
                continue
            if market.id in ctx.recent_seen_futures_ids:
                # Exhausted-feed recycling: re-show a stale-but-still-relevant
                # seen card (penalized below fresh) instead of walling. Otherwise
                # keep the hard skip that fresh users rely on.
                if _futures_recycle_eligible(market, ctx, now):
                    is_recycled = True
                else:
                    continue
            if _should_skip_futures_for_recent_dismissal(
                market=market,
                ctx=ctx,
                my_teams_only=my_teams_only,
            ):
                continue

        # Skip markets past their resolution date (belt-and-suspenders;
        # base_filters should exclude these at the SQL level, but naive
        # datetime timezone mismatches can let them through — issue #486).
        if market.resolution_date:
            res_dt = _utc(market.resolution_date)
            if res_dt and res_dt < now:
                continue

        # Prepare outcome data for scoring
        outcomes_data = []
        leader_name = None
        leader_prob = None

        sorted_outcomes = sorted(
            market.outcomes,
            key=lambda o: float(o.current_probability) if o.current_probability else 0,
            reverse=True,
        )

        for o in sorted_outcomes[:10]:  # Score based on top 10 outcomes
            prob = float(o.current_probability) if o.current_probability else None
            change = (
                float(o.probability_change_24h) if o.probability_change_24h else None
            )
            outcomes_data.append(
                {
                    "name": o.name,
                    "probability": prob,
                    "probability_change_24h": change,
                    "rank": o.rank,
                    "rank_change_24h": o.rank_change_24h,
                    "opening_probability": (
                        float(o.opening_probability) if o.opening_probability else None
                    ),
                }
            )

        if sorted_outcomes:
            leader = sorted_outcomes[0]
            leader_name = leader.name
            leader_prob = (
                float(leader.current_probability)
                if leader.current_probability
                else None
            )

        # --- Staleness filters ---
        # Keep serving-time exclusions on the same helper used by admin trace
        # output so stale/debug decisions cannot drift.
        runtime_filters = _market_runtime_filter_trace(
            market,
            outcomes_data,
            leader_name,
            leader_prob,
            now,
            sport_category=market.llm_sport_category,
            stale_no_movement_days=stale_no_movement_days,
            no_resolution_stale_days=no_resolution_stale_days,
        )
        if not runtime_filters["eligible"]:
            continue

        probs_available = [
            o["probability"] for o in outcomes_data if o["probability"] is not None
        ]
        if not probs_available and market.outcomes:
            # Market has outcomes but none have probability data — dead
            continue

        # Get source count from canonical key
        source_count = 1
        if market.canonical_market_key:
            source_count = canonical_source_counts.get(market.canonical_market_key, 1)

        highlight_result = compute_futures_highlight(
            market_tier=market.market_tier,
            sport_category=market.llm_sport_category,
            resolution_date=market.resolution_date,
            outcomes=outcomes_data,
            source_count=source_count,
            now=now,
            market_name=market.name,
            volume_24h=market.volume_24h,
            curation_score_adj=market.__dict__.get("curation_score_adj", 0) or 0,
        )

        top_mover_name = highlight_result.top_mover_name
        top_mover_change = None
        if top_mover_name:
            for o in outcomes_data:
                if o["name"] == top_mover_name and o.get("probability_change_24h"):
                    top_mover_change = o["probability_change_24h"]
                    break

        top_surprise_name = None
        top_surprise_change = None
        for o in outcomes_data:
            opening = o.get("opening_probability")
            current = o.get("probability")
            if opening is None or current is None:
                continue
            surprise_change = current - opening
            if top_surprise_change is None or abs(surprise_change) > abs(
                top_surprise_change
            ):
                top_surprise_name = o.get("name")
                top_surprise_change = surprise_change

        # Humanize Yes/No outcome names for display (BR49).
        # Scoring/filtering above uses the raw names; display-facing
        # generators below use humanized versions so headlines read
        # "Anthropic leads at 69%" instead of "Yes leads at 69%".
        _h_leader = (
            humanize_binary_outcome_name(leader_name, market.name)
            if leader_name
            else leader_name
        )
        _h_mover = (
            humanize_binary_outcome_name(top_mover_name, market.name)
            if top_mover_name
            else top_mover_name
        )
        _h_surprise = (
            humanize_binary_outcome_name(top_surprise_name, market.name)
            if top_surprise_name
            else top_surprise_name
        )

        headline = (
            generate_futures_headline(
                highlight_reasons=highlight_result.reasons,
                top_mover_name=_h_mover,
                top_mover_change=top_mover_change,
                top_surprise_name=_h_surprise,
                top_surprise_change=top_surprise_change,
                leader_name=_h_leader,
                leader_probability=leader_prob,
                source_count=source_count,
                market_name=market.name,
            )
            or highlight_result.primary_reason
        )
        context_summary = generate_futures_context_summary(
            headline=headline,
            highlight_reasons=highlight_result.reasons,
            market_name=market.name,
            leader_name=_h_leader,
            leader_probability=leader_prob,
            source_count=source_count,
        )

        quality = classify_market_quality(
            market_name=market.name,
            sport_category=market.llm_sport_category,
            outcome_names=[o.name for o in market.outcomes if o.name],
            external_id=market.external_id,
            status=market.status,  # R6: resolved sports never surface
        )
        if quality.quality_class == "suppress":
            continue
        if _should_skip_futures_for_recent_dismissal(
            market=market,
            quality=quality,
            ctx=ctx,
            my_teams_only=my_teams_only,
        ):
            continue

        # Detect stale hooks early so explanation scoring uses the
        # effective (possibly suppressed) hook, not the raw DB value.
        effective_hook = market.hook_description
        if effective_hook and is_hook_stale(
            hook_description=effective_hook,
            hook_generated_at=market.hook_generated_at,
            hook_leader_at_generation=market.hook_leader_at_generation,
            current_leader_name=leader_name,
            current_leader_probability=leader_prob,
            market_metadata=market.market_metadata,
            now=now,
        ):
            effective_hook = None

        base_score = apply_quality_score(highlight_result.score, quality)
        base_score = apply_explanation_quality_score(
            base_score,
            hook_description=effective_hook,
            headline=headline,
            quality=quality,
        )
        base_score = _apply_external_curator_recall_score(
            base_score,
            highlight_result.reasons,
            is_external_curator_recall=market.id in external_curator_recall_ids,
        )
        discover_llm_metadata = _get_discover_llm_metadata(market.market_metadata)
        llm_score_adjustment = _discover_llm_score_adjustment(discover_llm_metadata)
        if llm_score_adjustment:
            base_score = max(0, min(98, base_score + llm_score_adjustment))
            highlight_result.reasons.append(
                f"discover_llm_score:{llm_score_adjustment:+d}"
            )

        # === INTERESTINGNESS BLEND ===
        # Read precomputed interestingness from Redis and blend with base_score.
        # Weight is controllable via Redis key (default 0.2, kill switch at 0).
        if _interestingness_cache is not None:
            cached_entry = _interestingness_cache.get(market.id)
            if cached_entry is not None and _interestingness_blend_weight > 0:
                i_score = cached_entry.get("score", 0)
                pre_blend = base_score
                blended = (
                    base_score * (1 - _interestingness_blend_weight)
                    + (i_score * 100) * _interestingness_blend_weight
                )
                # Cap: interestingness can add at most 15 points over base
                base_score = min(blended, pre_blend + 15)
                base_score = max(0, min(98, base_score))
                i_reasons = cached_entry.get("reasons") or []
                if abs(base_score - pre_blend) >= 0.5:
                    delta = base_score - pre_blend
                    delta_label: int | float = (
                        int(delta) if float(delta).is_integer() else round(delta, 1)
                    )
                    highlight_result.reasons.append(f"interestingness:{delta_label:+g}")

        if quality.reasons:
            highlight_result.reasons.extend(f"quality:{r}" for r in quality.reasons)

        # Apply personalization multiplier
        outcome_team_ids = [o.team_id for o in market.outcomes if o.team_id is not None]

        # my_teams_only: skip futures that don't involve the user's teams
        if my_teams_only:
            # Skip Tier 3 sports — same filter as events to avoid false
            # positives from name collisions. BR42/BR43.
            market_sport_key = market.sport.key if market.sport else None
            if market_sport_key and market_sport_key not in MY_STUFF_ALLOWED_SPORT_KEYS:
                continue
            # Also filter by llm_sport_category for markets without a sport FK
            if not market_sport_key and market.llm_sport_category:
                if market.llm_sport_category not in MY_STUFF_ALLOWED_CATEGORIES:
                    continue

            matched_by_id = bool(set(outcome_team_ids) & user_team_ids)

            # Fall back to outcome name matching when team_ids aren't linked.
            # BR53: require sport-category match to prevent cross-sport false
            # positives (e.g., "Aliya Boston" matching "Boston Bruins" via
            # token overlap, or "Believers: Boston Red Sox" Sports Emmy
            # matching a baseball team).
            matched_by_name = False
            if not matched_by_id and my_team_names:
                market_cat = market.llm_sport_category
                if not market_cat and market_sport_key:
                    market_cat = _personalization_category_from_sport_key(
                        market_sport_key
                    )
                for o in market.outcomes:
                    if o.name:
                        for team_name in my_team_names or []:
                            if _team_name_matches(team_name, o.name):
                                # Verify sport compatibility (BR53)
                                if my_team_sport_categories and market_cat:
                                    team_cats = my_team_sport_categories.get(team_name)
                                    if team_cats and market_cat not in team_cats:
                                        continue  # sport mismatch — skip
                                matched_by_name = True
                                break
                    if matched_by_name:
                        break

            if not matched_by_id and not matched_by_name:
                continue

        # Collect matched outcome details for "why is this here?" context
        matched_outcomes_list = []
        if my_teams_only and user_team_ids:
            market_cat_for_match = market.llm_sport_category
            if not market_cat_for_match and (market.sport and market.sport.key):
                market_cat_for_match = _personalization_category_from_sport_key(
                    market.sport.key
                )
            for o in market.outcomes:
                is_match = False
                if o.team_id and o.team_id in user_team_ids:
                    is_match = True
                elif my_team_names and o.name:
                    for team_name in my_team_names or []:
                        if _team_name_matches(team_name, o.name):
                            # BR53: sport-category check for name-matched outcomes
                            if my_team_sport_categories and market_cat_for_match:
                                team_cats = my_team_sport_categories.get(team_name)
                                if team_cats and market_cat_for_match not in team_cats:
                                    continue
                            is_match = True
                            break
                if is_match:
                    matched_outcomes_list.append(
                        {
                            "name": o.name,
                            "probability": (
                                float(o.current_probability)
                                if o.current_probability
                                else None
                            ),
                            "rank": o.rank,
                            "movement": (
                                float(o.probability_change_24h)
                                if o.probability_change_24h
                                else None
                            ),
                        }
                    )

        outcome_names = [o.name for o in market.outcomes if o.name]
        p_result = compute_futures_multiplier(
            ctx=ctx,
            sport_category=market.llm_sport_category,
            outcome_team_ids=outcome_team_ids,
            futures_market_id=market.id,
            sport_key=market.sport.key if market.sport else None,
            outcome_names=outcome_names,
            feature_tokens=list(
                _discover_feature_tokens(
                    item_name=market.name,
                    category=market.llm_sport_category,
                    item_type="futures",
                )
            )
            + list(
                _discover_semantic_tokens(
                    item_name=market.name,
                    category=market.llm_sport_category,
                    item_type="futures",
                )
            )
            + _discover_llm_feature_tokens(discover_llm_metadata),
        )
        personalized_score = min(98, int(base_score * p_result.multiplier))

        # Recycled (previously-seen) cards rank below fresh ones, so they only
        # surface when the fresh pool can't fill the page (implicit serving floor).
        if is_recycled:
            personalized_score = max(1, int(personalized_score - FEED_RECYCLE_PENALTY))

        # --- "Nah" category hard filter for futures ---
        is_nah = any("sport_nah" in r for r in p_result.reasons)
        if is_nah and not my_teams_only:
            continue  # No override for futures — no "championship" equivalent

        # "If it's wild" — higher bar for low-affinity futures too
        is_low_affinity = any("sport_suppress" in r for r in p_result.reasons)
        if is_low_affinity and not my_teams_only and personalized_score < 55:
            continue

        # Filter low-signal futures (my_teams_only shows everything)
        if not my_teams_only and personalized_score < 15:
            continue

        reason = generate_futures_reason(
            market_name=market.name,
            highlight_reasons=highlight_result.reasons,
            top_mover_name=_h_mover,
            top_mover_change=top_mover_change,
            top_surprise_name=_h_surprise,
            top_surprise_change=top_surprise_change,
            leader_name=_h_leader,
            leader_probability=leader_prob,
            source_count=source_count,
        )

        # Build compact futures data for the feed
        top_outcomes_data = [
            {
                "id": o.id,
                "name": o.name,
                "probability": (
                    float(o.current_probability) if o.current_probability else None
                ),
                "rank": o.rank,
                "movement": (
                    float(o.probability_change_24h)
                    if o.probability_change_24h
                    else None
                ),
            }
            for o in sorted_outcomes[:3]  # Show top 3 in feed card
        ]

        # Humanize Yes/No outcome names for feed card display (BR49)
        top_outcomes_data = humanize_outcome_names_for_feed(
            top_outcomes_data, market.name
        )

        # Normalize probabilities for independent binary markets (gotcha #58).
        # Use the ALL-outcomes sum to distinguish mutually-exclusive markets
        # (sum ~100-150%) from threshold/cumulative markets (sum >>200%).
        # Threshold markets (e.g. "rank 3+", "rank 4+") have non-exclusive
        # outcomes whose raw probabilities are meaningful — normalizing them
        # flattens an 81% leader to 33% when the top 3 are all high.
        top_outcomes_data = _normalize_feed_probabilities(
            top_outcomes_data, sorted_outcomes
        )

        source_names = (
            (_canonical_source_names_cache or {}).get(
                market.canonical_market_key, [market.source]
            )
            if market.canonical_market_key
            else [market.source]
        )
        all_outcomes_for_card = [
            {
                "name": o.name,
                "probability": (
                    float(o.current_probability)
                    if o.current_probability is not None
                    else None
                ),
                "movement": (
                    float(o.probability_change_24h)
                    if o.probability_change_24h is not None
                    else None
                ),
            }
            for o in sorted_outcomes
        ]
        is_effectively_resolved = market.status == "resolved"
        discover_card = classify_discover_card_archetype(
            name=market.name,
            category=market.llm_sport_category,
            outcomes=all_outcomes_for_card,
            outcome_count=len(market.outcomes),
            source_count=source_count,
            sources=source_names,
            group_id=market.group_id,
            group_type=market.group_type,
            canonical_market_key=market.canonical_market_key,
            discover_llm=discover_llm_metadata,
            resolved=is_effectively_resolved,
            status=market.status,
        )

        futures_data = {
            "id": market.id,
            "name": market.name,
            "sport": market.sport.key if market.sport else None,
            "sport_name": market.sport.name if market.sport else None,
            "llm_sport_category": market.llm_sport_category,
            "source": market.source,
            "source_count": source_count,
            "sources": source_names,
            "market_tier": market.market_tier,
            "status": market.status,
            "resolution_date": (
                market.resolution_date.isoformat() if market.resolution_date else None
            ),
            "top_outcomes": top_outcomes_data,
            "outcome_count": len(market.outcomes),
            "canonical_market_key": market.canonical_market_key,
            "group_id": market.group_id,
            "group_type": market.group_type,
            "discover_card": discover_card,
            "image_url": market.image_url,
            "hook_description": effective_hook,
            "temporal_badge": _compute_temporal_badge(
                status=market.status,
                resolution_date=market.resolution_date,
                created_at=market.created_at,
                now=now,
            ),
        }
        if discover_llm_metadata:
            futures_data["discover_llm"] = {
                "topic": discover_llm_metadata.get("topic"),
                "subtopic": discover_llm_metadata.get("subtopic"),
                "archetype": discover_llm_metadata.get("archetype"),
                "audience_scope": discover_llm_metadata.get("audience_scope"),
                "salience_score": discover_llm_metadata.get("salience_score"),
                "junk_flags": discover_llm_metadata.get("junk_flags") or [],
                "comparison_axes": discover_llm_metadata.get("comparison_axes") or [],
            }
        # Attach interestingness metadata to feed item data
        if _interestingness_cache is not None:
            cached_entry = _interestingness_cache.get(market.id)
            if cached_entry is not None:
                futures_data["interestingness_score"] = cached_entry.get("score")
                futures_data["interestingness_reasons"] = cached_entry.get("reasons")

        # Compute market_tags on-the-fly
        inline_market_tags = compute_market_tags(
            llm_sport_category=market.llm_sport_category,
            llm_league=getattr(market, "llm_league", None),
            llm_gender=getattr(market, "llm_gender", None),
            llm_level=getattr(market, "llm_level", None),
            market_tier=market.market_tier,
            category=market.category,
            status=market.status,
            source=market.source,
        )
        futures_data["market_tags"] = inline_market_tags

        # Tag filter: skip futures that don't match requested tags
        if tag_filter:
            if not all(t in inline_market_tags for t in tag_filter):
                continue

        if matched_outcomes_list:
            futures_data["matched_outcomes"] = matched_outcomes_list

        # Add resolved metadata for markets that have effectively settled
        if is_effectively_resolved:
            futures_data["resolved"] = True
            futures_data["winner"] = leader_name
            futures_data["winner_opening_probability"] = leader_opening

        # Sort time: higher-tier markets and markets resolving soon get priority
        sort_time = now.timestamp()
        if market.resolution_date:
            # Closer resolution = more timely
            days_until = (market.resolution_date - now).total_seconds()
            sort_time = now.timestamp() + max(0, 86400 * 30 - days_until)

        item = {
            "type": "futures",
            "score": personalized_score,
            "reason": reason,
            "headline": headline,
            "context_summary": context_summary,
            "data": futures_data,
            "_sort_time": sort_time,
            "_quality_class": quality.quality_class,
            "_quality_family_key": quality.family_key,
            "_quality_story_key": quality.story_key,
        }
        personalization_trace = _build_personalization_trace(
            ctx=ctx,
            item_type="futures",
            category=market.llm_sport_category,
            base_score=base_score,
            final_score=personalized_score,
            p_result=p_result,
        )
        if personalization_trace:
            item["personalization_trace"] = personalization_trace

        if p_result.is_personalized:
            item["personalized"] = True
            item["base_score"] = base_score
            item["multiplier"] = round(p_result.multiplier, 2)
            item["personalization_reasons"] = p_result.reasons

        if is_recycled:
            item["recycled"] = True

        scored_items.append(item)
    mark_timing("scoring_loop")

    # Dedup by group_id: keep only the highest-scoring market per group.
    # Polymarket sub-markets sharing a group_id represent the same real-world
    # question (e.g., "Who wins Best Picture?" x 10 nominee markets).
    scored_items = _dedupe_futures_by_group_id(scored_items)

    scored_items = cap_low_quality_families(scored_items, cap=1)
    scored_items = diversify_quality_families(
        scored_items,
        exact_family_cap=1,
        story_family_cap=5,
    )
    mark_timing("caps")

    return scored_items


_canonical_source_counts_cache: Optional[dict[str, int]] = None
_canonical_source_names_cache: Optional[dict[str, list[str]]] = None
_canonical_source_counts_ts: float = 0.0
_CANONICAL_CACHE_TTL = 300  # 5 minutes

# Championship probability cache (for stakes weighting)
_champ_prob_cache: Optional[dict[int, float]] = None
_champ_prob_cache_ts: float = 0.0
_CHAMP_PROB_CACHE_TTL = 300  # 5 minutes


async def _get_championship_probabilities(db: AsyncSession) -> dict[int, float]:
    """Return {team_id: max_championship_probability} for all teams with championship futures.

    Queries market_tier=1 (championship) futures outcomes with a linked team_id.
    Cached for 5 minutes since championship odds change slowly.
    """
    import time

    global _champ_prob_cache, _champ_prob_cache_ts
    now_ts = time.time()
    if (
        _champ_prob_cache is not None
        and (now_ts - _champ_prob_cache_ts) < _CHAMP_PROB_CACHE_TTL
    ):
        return _champ_prob_cache

    from sqlalchemy import text

    result = await db.execute(text("""
            SELECT fo.team_id, MAX(fo.current_probability) AS max_prob
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fo.market_id = fm.id
            WHERE fm.market_tier = 1
              AND fm.status = 'open'
              AND fo.team_id IS NOT NULL
              AND fo.current_probability IS NOT NULL
              AND fo.current_probability > 0
            GROUP BY fo.team_id
        """))
    cache = {row.team_id: float(row.max_prob) for row in result.all()}
    _champ_prob_cache = cache
    _champ_prob_cache_ts = now_ts
    return cache


async def _get_canonical_source_counts(
    db: AsyncSession,
    keys: Optional[set[str]] = None,
) -> dict[str, int]:
    """Get source counts for canonical market keys.

    The full map is cached for trace/debug callers. Feed scoring passes the
    candidate keys so it does not group the entire futures market table on a
    cold worker.
    """
    import time

    global _canonical_source_counts_cache, _canonical_source_names_cache, _canonical_source_counts_ts
    now = time.time()
    if (
        _canonical_source_counts_cache is not None
        and (now - _canonical_source_counts_ts) < _CANONICAL_CACHE_TTL
    ):
        if keys is None:
            return _canonical_source_counts_cache
        return {
            key: count
            for key, count in _canonical_source_counts_cache.items()
            if key in keys
        }

    if keys is not None and not keys:
        return {}

    query = select(
        FuturesMarket.canonical_market_key,
        func.count(func.distinct(FuturesMarket.source)).label("source_count"),
        func.array_agg(func.distinct(FuturesMarket.source)).label("sources"),
    ).where(FuturesMarket.canonical_market_key.isnot(None))
    if keys is not None:
        query = query.where(FuturesMarket.canonical_market_key.in_(keys))
    query = query.group_by(FuturesMarket.canonical_market_key)

    result = await db.execute(query)
    rows = result.all()
    cache = {row.canonical_market_key: row.source_count for row in rows}
    names_cache = {
        row.canonical_market_key: sorted(row.sources) if row.sources else []
        for row in rows
    }
    if keys is not None:
        _canonical_source_names_cache = {
            **((_canonical_source_names_cache or {})),
            **names_cache,
        }
        return cache

    _canonical_source_counts_cache = cache
    _canonical_source_names_cache = names_cache
    _canonical_source_counts_ts = now
    return cache


def _ensure_feed_diversity(
    items: list[dict],
    target_size: int,
    event_pct: float = 0.4,
) -> list[dict]:
    """
    Ensure the feed has a healthy mix of events and futures.

    The feed should lead with real games when available. Without this,
    futures can dominate because they get "resolving soon" + "multi source"
    bonuses that events don't have.

    Strategy:
    - Reserve at least event_pct of slots for events (if available).
    - Among the top N items, interleave so events aren't all pushed down.
    - Preserves score ordering within each type.
    """
    if not items:
        return items

    events = [i for i in items if i["type"] == "event"]
    futures = [i for i in items if i["type"] == "futures"]
    other = [i for i in items if i["type"] not in ("event", "futures")]

    # If one type is empty, nothing to balance
    if not events or not futures:
        return items

    # Determine minimum event slots (event_pct of target, at least 3)
    min_event_slots = max(3, int(target_size * event_pct))
    min_event_slots = min(min_event_slots, len(events))

    # Check if the natural ordering already has enough events in the top N
    top_n = items[:target_size]
    events_in_top = sum(1 for i in top_n if i["type"] == "event")

    if events_in_top >= min_event_slots:
        # Natural ordering is fine
        return items

    # Need to promote events. Take top events that aren't already in top N,
    # and interleave them with the existing top items.
    # Merge futures + other (tournaments, etc.) into one pool sorted by score.
    non_events = sorted(
        futures + other,
        key=lambda x: (x["score"], x.get("_sort_time", 0)),
        reverse=True,
    )
    result = []
    event_idx = 0
    non_event_idx = 0
    events_placed = 0

    for slot in range(min(target_size, len(items))):
        need_event = events_placed < min_event_slots and event_idx < len(events)

        # Every 2-3 items, prefer an event if we need more
        if need_event and (slot % 3 != 2 or non_event_idx >= len(non_events)):
            result.append(events[event_idx])
            event_idx += 1
            events_placed += 1
        elif non_event_idx < len(non_events):
            result.append(non_events[non_event_idx])
            non_event_idx += 1
        elif event_idx < len(events):
            result.append(events[event_idx])
            event_idx += 1
            events_placed += 1

    # Append remaining items (beyond target_size) in original order
    placed_ids = set()
    for item in result:
        data = item.get("data", {})
        key = (item["type"], data.get("id") or data.get("key"))
        placed_ids.add(key)

    for item in items:
        data = item.get("data", {})
        key = (item["type"], data.get("id") or data.get("key"))
        if key not in placed_ids:
            result.append(item)

    return result


def _outcomes_overlap(item_a: dict, item_b: dict) -> bool:
    """Check if two feed futures items have overlapping top outcome names.

    Used as a safety check before deduplicating by canonical_market_key.
    Returns True if at least 1 outcome name appears in both items' top
    outcomes (case-insensitive).  Returns True if either item has no
    outcomes (benefit of the doubt — can't disprove overlap).
    """
    outcomes_a = item_a.get("data", {}).get("top_outcomes", [])
    outcomes_b = item_b.get("data", {}).get("top_outcomes", [])
    if not outcomes_a or not outcomes_b:
        return True  # Can't check — assume overlap
    names_a = {o.get("name", "").lower().strip() for o in outcomes_a if o.get("name")}
    names_b = {o.get("name", "").lower().strip() for o in outcomes_b if o.get("name")}
    if not names_a or not names_b:
        return True
    binary_names = {"yes", "no"}
    if names_a <= binary_names and names_b <= binary_names:
        return _binary_names_compatible_for_dedupe(item_a, item_b)
    return bool(names_a & names_b)


# ============================================================================
# Golf Tournament Feed Items
# ============================================================================

# In-memory cache for golf tournament data (avoids re-querying every feed call)
_golf_cache: dict[str, tuple[float, list[dict]]] = {}
_GOLF_CACHE_TTL = 300  # 5 minutes


_DEFAULT_FEED_TOURS = frozenset({"pga", "major", "dp_world", "lpga", "liv"})

# Map tournament tour values to user affinity keys
_TOUR_AFFINITY_KEYS: dict[str, str] = {
    "pga": "golf_pga",
    "major": "golf_pga",  # Majors bundled with PGA Tour
    "dp_world": "golf_dp_world",
    "lpga": "golf_lpga",
    "liv": "golf_liv",
}


def _compute_user_feed_tours(ctx) -> set[str]:
    """Compute which golf tours a user wants to see based on sport affinities."""
    if not ctx or not ctx.is_authenticated or not ctx.sport_affinities:
        return set(_DEFAULT_FEED_TOURS)

    has_any_golf = any(k.startswith("golf") for k in ctx.sport_affinities)
    if not has_any_golf:
        return set()  # User went through onboarding, no golf interest

    # Check for new-style tour-level keys
    has_tour_keys = any(
        k in ctx.sport_affinities
        for k in ("golf_pga", "golf_dp_world", "golf_lpga", "golf_liv")
    )
    if not has_tour_keys:
        # Legacy user — has golf_masters_tournament_winner etc. but no tour keys
        # Show all tours (preserves old behavior)
        return set(_DEFAULT_FEED_TOURS)

    # New-style user — filter by tour preference
    tours: set[str] = set()
    for tour, affinity_key in _TOUR_AFFINITY_KEYS.items():
        if ctx.sport_affinities.get(affinity_key, 0.0) > 0.05:
            tours.add(tour)
    return tours


async def _score_golf_tournaments(
    db: AsyncSession,
    now: datetime,
    sport_filter: Optional[str],
    ctx=None,
) -> list[dict]:
    """Score golf tournaments for the unified feed.

    Calls the golf landing page endpoint internally to get tournament data,
    caches the result, and scores each tournament for feed ranking.
    Returns feed items with type="tournament".
    """
    # If sport filter is set and doesn't match golf, skip
    if sport_filter and sport_filter not in ("golf", "all"):
        return []

    import time as _time

    # Cache raw tournament data (shared across users), filter per-user below
    cache_key = "golf_tournaments_raw"
    tournaments = None
    if cache_key in _golf_cache:
        cached_at, cached_data = _golf_cache[cache_key]
        if _time.time() - cached_at < _GOLF_CACHE_TTL:
            tournaments = cached_data

    if tournaments is None:
        try:
            from app.routes.golf import get_golf

            golf_data = await get_golf(db=db)
        except Exception as e:
            logger.warning("Feed: failed to load golf tournaments: %s", e)
            return []

        tournaments = golf_data.get("tournaments", [])
        _golf_cache[cache_key] = (_time.time(), tournaments)

    if not tournaments:
        return []

    feed_items: list[dict] = []

    # Per-user tour filtering based on sport affinities
    feed_tours = _compute_user_feed_tours(ctx)
    if not feed_tours:
        return []  # User has no golf interest

    for t in tournaments:
        # Only include tournaments with golfer data
        golfers = t.get("golfers", [])
        if not golfers:
            continue

        # Only include tours the user follows
        if t.get("tour") not in feed_tours:
            continue

        # Only include winner/outright markets (skip top-20, make-cut, etc.)
        is_winner_market = t.get("is_tour_event", False) or t.get("is_major", False)
        # For non-tour events, check market names for winner pattern
        if not is_winner_market:
            market_names = t.get("market_names", [])
            is_winner_market = any(
                "winner" in n.lower() or "outright" in n.lower() for n in market_names
            )
        if not is_winner_market:
            continue

        # Score the tournament
        score = _score_tournament(t, now)
        if score <= 0:
            continue

        # Build the reason text
        leader = golfers[0]
        leader_pct = round(leader["probability"] * 100, 1)
        reason = (
            f"{t.get('tour_label', 'Golf')}: {leader['name']} leads at {leader_pct}%"
        )
        if leader.get("movement_24h") and abs(leader["movement_24h"]) >= 0.01:
            mv = leader["movement_24h"]
            direction = "up" if mv > 0 else "down"
            reason += f" ({direction} {abs(round(mv * 100, 1))}% today)"

        # Build headline
        headline = None
        is_live = _tournament_is_live(t, now)
        if is_live:
            headline = "Live"
        elif t.get("start_date"):
            start = datetime.fromisoformat(t["start_date"])
            days_until = (start.date() - now.date()).days
            if days_until <= 0:
                headline = "Today"
            elif days_until == 1:
                headline = "Tomorrow"
            elif days_until <= 7:
                headline = "This week"

        # Build tournament feed item data
        data = {
            "key": t.get("key"),
            "name": t.get("name"),
            "slug": t.get("slug"),
            "tour": t.get("tour"),
            "tour_label": t.get("tour_label"),
            "is_major": t.get("is_major", False),
            "venue": t.get("venue"),
            "location": t.get("location"),
            "start_date": t.get("start_date"),
            "end_date": t.get("end_date"),
            "schedule_status": t.get("schedule_status"),
            "commence_time": t.get("commence_time"),
            "resolution_date": t.get("resolution_date"),
            "golfers": [
                {
                    "name": g["name"],
                    "probability": g["probability"],
                    "rank": g["rank"],
                    "movement_24h": g.get("movement_24h"),
                }
                for g in golfers[:10]  # Top 10 for feed
            ],
            "market_ids": t.get("market_ids", []),
            "source_count": len(set(t.get("market_sources", []))),
        }

        feed_items.append(
            {
                "type": "tournament",
                "score": score,
                "reason": reason,
                "headline": headline,
                "data": data,
                "_sort_time": (
                    datetime.fromisoformat(t["commence_time"]).timestamp()
                    if t.get("commence_time")
                    else 0
                ),
            }
        )

    return feed_items


def _tournament_is_live(t: dict, now: datetime) -> bool:
    """Check if a tournament is currently live."""
    if t.get("schedule_status") == "in-progress":
        return True
    if t.get("start_date") and t.get("end_date"):
        try:
            start = datetime.fromisoformat(t["start_date"]).replace(tzinfo=timezone.utc)
            end = datetime.fromisoformat(t["end_date"]).replace(tzinfo=timezone.utc)
            if start <= now <= end + timedelta(hours=12):
                return True
        except (ValueError, TypeError):
            pass
    # Fallback: significant movement = in progress
    golfers = t.get("golfers", [])
    if any(g.get("movement_24h") and abs(g["movement_24h"]) >= 0.01 for g in golfers):
        return True
    return False


def _score_tournament(t: dict, now: datetime) -> int:
    """Score a golf tournament for feed ranking (0-100)."""
    score = 30  # Base score

    # Live tournaments score high
    if _tournament_is_live(t, now):
        score += 35

    # Majors get a boost
    if t.get("is_major"):
        score += 15

    # Tournaments starting soon get a boost; stale ones get penalized
    if t.get("start_date"):
        try:
            start = datetime.fromisoformat(t["start_date"])
            days_until = (start.date() - now.date()).days
            if days_until <= 0 and days_until >= -4:
                # Currently in progress or just started (4-day tournament window)
                score += 20
            elif days_until < -4:
                # Stale — started more than 4 days ago, probably over
                return 0
            elif days_until <= 3:
                score += 15
            elif days_until <= 7:
                score += 10
        except (ValueError, TypeError):
            pass

    # Movement in leader odds = more interesting
    golfers = t.get("golfers", [])
    if golfers and golfers[0].get("movement_24h"):
        mv = abs(golfers[0]["movement_24h"])
        if mv >= 0.05:
            score += 10
        elif mv >= 0.02:
            score += 5

    # Multi-source data = more reliable = more interesting
    sources = set(t.get("market_sources", []))
    if len(sources) >= 3:
        score += 5
    elif len(sources) >= 2:
        score += 3

    return min(score, 100)


@router.get("/tag-counts")
async def get_tag_counts(
    db: AsyncSession = Depends(get_db),
):
    """Return item counts grouped by sport for the category index page.

    Counts active events (live, scheduled within 12h, completed within 24h)
    and open futures markets per sport category.
    """
    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(hours=24)
    upcoming_cutoff = now + timedelta(hours=12)

    from sqlalchemy import text

    # Count events by sport key prefix (first segment before '_')
    event_counts_result = await db.execute(
        text("""
            SELECT
                CASE
                    WHEN s.key LIKE 'americanfootball_%' THEN 'football'
                    WHEN s.key LIKE 'basketball_%' THEN 'basketball'
                    WHEN s.key LIKE 'baseball_%' THEN 'baseball'
                    WHEN s.key LIKE 'icehockey_%' THEN 'hockey'
                    WHEN s.key LIKE 'soccer_%' THEN 'soccer'
                    WHEN s.key LIKE 'mma_%' THEN 'mma'
                    WHEN s.key LIKE 'boxing_%' THEN 'boxing'
                    WHEN s.key LIKE 'golf_%' THEN 'golf'
                    WHEN s.key LIKE 'tennis_%' THEN 'tennis'
                    WHEN s.key LIKE 'cricket_%' THEN 'cricket'
                    WHEN s.key LIKE 'rugbyleague_%' OR s.key LIKE 'rugbyunion_%' THEN 'rugby'
                    WHEN s.key LIKE 'aussierules_%' THEN 'aussierules'
                    WHEN s.key LIKE 'esports_%' THEN 'esports'
                    WHEN s.key LIKE 'lacrosse_%' THEN 'lacrosse'
                    WHEN s.key LIKE 'motorsport_%' OR s.key LIKE 'racing_%' THEN 'motorsport'
                    ELSE 'other'
                END AS category,
                COUNT(*) AS cnt
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            WHERE (
                (e.status = 'live')
                OR (e.status = 'scheduled' AND e.commence_time <= :upcoming AND e.commence_time >= :now)
                OR (e.status IN ('completed', 'closed') AND e.commence_time >= :recent)
            )
            GROUP BY category
        """),
        {"now": now, "upcoming": upcoming_cutoff, "recent": recent_cutoff},
    )
    event_counts: dict[str, int] = {}
    for row in event_counts_result.all():
        event_counts[row.category] = row.cnt

    # Count futures by llm_sport_category
    futures_counts_result = await db.execute(
        text("""
            SELECT
                COALESCE(llm_sport_category, 'other') AS category,
                COUNT(*) AS cnt
            FROM futures_markets
            WHERE status = 'open'
              AND event_id IS NULL
              AND (resolution_date IS NULL OR resolution_date >= :now)
            GROUP BY category
        """),
        {"now": now},
    )
    futures_counts: dict[str, int] = {}
    for row in futures_counts_result.all():
        futures_counts[row.category] = row.cnt

    # Merge into response
    all_categories = set(event_counts.keys()) | set(futures_counts.keys())
    counts = {}
    for cat in sorted(all_categories):
        counts[cat] = {
            "events": event_counts.get(cat, 0),
            "futures": futures_counts.get(cat, 0),
        }

    return {"counts": counts}
