"""Unified feed API endpoint.

Merges scored events and scored futures into a single ranked list,
providing a "what's interesting right now" view across all content types.

Supports optional authentication: logged-in users get personalized scoring
based on their favorite teams, sport affinities, and pinned items.
Anonymous users see the generic interestingness feed.
"""

import asyncio
import hashlib
import json as _json_module
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, and_, or_, func, case, cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import JSONB

from app.dependencies.auth import get_optional_user
from app.models import Event, Sport, FuturesMarket, FuturesOutcome
from app.models.models import User, UserFavorite, UserPreference, UserPin, Team
from app.services import get_db
from app.utils.aggregation import SOURCE_WEIGHTS, compute_aggregate_probability as _compute_aggregate_probability
from app.utils.event_taxonomy import compute_event_tags, compute_market_tags
from app.utils import (
    compute_highlight,
    get_highlight_label,
    should_highlight,
    get_league_tier,
    get_season_multiplier,
)
from app.utils.highlights import parse_game_progress
from app.utils.futures_highlights import compute_futures_highlight, should_highlight_futures
from app.utils.feed_market_quality import (
    apply_explanation_quality_score,
    apply_quality_score,
    cap_low_quality_families,
    classify_market_quality,
    diversify_discover_first_page,
    diversify_quality_families,
)
from app.utils.feed_reasons import generate_event_reason, generate_futures_headline, generate_futures_reason
from app.utils.feed_quality_debug import build_feed_quality_debug, load_default_ground_truth_items
from app.utils.feed_quality_debug import summarize_missing_ground_truth_db_trace
from app.utils.name_normalization import names_match as _team_name_matches
from app.utils.personalization import (
    PersonalizationContext,
    compute_event_multiplier,
    compute_futures_multiplier,
)
from app.routes.events import _build_team_lookup, _format_team_data

logger = logging.getLogger(__name__)

router = APIRouter()


def _record_feed_timing(
    timings: list[dict[str, float | str]],
    started_at: float,
    previous_at: float,
    stage: str,
) -> float:
    """Record a stage timing relative to request start for admin diagnostics."""
    current_at = time.perf_counter()
    timings.append({
        "stage": stage,
        "ms": round((current_at - previous_at) * 1000, 2),
        "elapsed_ms": round((current_at - started_at) * 1000, 2),
    })
    return current_at


def _set_feed_timing_header(response: Response, started_at: float) -> None:
    response.headers["X-Feed-Elapsed-Ms"] = str(round((time.perf_counter() - started_at) * 1000, 2))


def _check_admin_secret(secret: str | None) -> bool:
    expected = os.getenv("ADMIN_TOKEN") or os.getenv("ADMIN_SECRET")
    return bool(expected and secret == expected)


_TRACE_STOPWORDS = {
    "will", "what", "when", "which", "with", "from", "that", "this",
    "before", "after", "market", "winner", "yes", "no", "the", "and",
    "win", "wins", "won",
}
_DEDUP_NAME_STOPWORDS = _TRACE_STOPWORDS | {
    "who", "does", "have", "than", "then", "into", "onto", "over", "under",
    "above", "below", "between", "next", "last", "end", "start", "season",
    "year", "month", "week", "day", "date", "2024", "2025", "2026", "2027",
    "2028", "2029", "2030",
}

DISCOVER_SPORTS_CATEGORIES = (
    "basketball", "football", "baseball", "hockey", "soccer",
    "golf", "mma", "boxing", "tennis", "cricket", "motorsports",
    "esports", "rugby", "lacrosse",
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


def _dedupe_futures_by_canonical(futures_items: list[dict]) -> list[dict]:
    """Deduplicate futures by canonical key using the feed's existing rules."""
    seen_canonical: dict[str, dict] = {}
    deduped: list[dict] = []
    for fitem in futures_items:
        key = fitem["data"].get("canonical_market_key")
        if key is None:
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
    limit: int = Query(200, description="Number of feed items to return", ge=1, le=5000),
    offset: int = Query(0, description="Offset for pagination", ge=0),
    sport: Optional[str] = Query(None, description="Filter by sport category (e.g., basketball, football)"),
    include_events: bool = Query(True, description="Include game events in feed"),
    include_futures: bool = Query(True, description="Include futures markets in feed"),
    my_teams_only: bool = Query(False, description="Filter to only the user's followed teams"),
    tags: Optional[str] = Query(None, description="Filter by taxonomy tags (JSON array, e.g., [\"sport:basketball\"])"),
    event_pct: Optional[float] = Query(None, description="Override event percentage floor (0.0-1.0). Discover uses 0.15."),
    debug: bool = Query(False, description="Include admin-only feed quality diagnostics"),
    secret: Optional[str] = Query(None, description="Admin secret for debug diagnostics"),
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

    if debug and not _check_admin_secret(secret):
        _set_feed_timing_header(response, _started_at)
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # --- Redis response cache (anon 15s, auth 5s) ---
    _cache_key = None
    _cache_ttl = 15 if user is None else 5
    _async_redis = None
    if not my_teams_only and not debug:
        try:
            from app.tasks.redis_state import get_async_redis_client
            _async_redis = get_async_redis_client()
            _user_part = f"u:{user.id}" if user else "anon"
            _parts = f"feed:{_user_part}:{sport or 'all'}:{limit}:{offset}:{include_events}:{include_futures}:{tags or ''}:{event_pct or ''}"
            _cache_key = f"feed_cache:{hashlib.md5(_parts.encode()).hexdigest()}"
            cached = await _async_redis.get(_cache_key)
            if cached:
                await _async_redis.aclose()
                _previous_at = _record_feed_timing(_timings, _started_at, _previous_at, "cache_hit")
                _set_feed_timing_header(response, _started_at)
                return _json_module.loads(cached)
        except Exception:
            _cache_key = None

    now = datetime.now(timezone.utc)

    # Parse tag filter — split into static (SQL-pushable) and dynamic (inline)
    import json as _json
    tag_filter: Optional[list[str]] = None
    static_tag_filter: list[str] = []  # Tags that don't change: sport, league, tier, class, level, gender, category, source
    dynamic_tag_filter: list[str] = []  # Tags that change frequently: status, signal, timing, ei, importance
    STATIC_NAMESPACES = {"sport", "league", "tier", "class", "level", "gender", "category", "source"}
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
    if my_teams_only and not user:
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
    ctx = await _load_personalization_context(db, user)
    _previous_at = _record_feed_timing(_timings, _started_at, _previous_at, "personalization")

    # Build team name set once (used by both scoring functions + response).
    # Only uses Team.name (full ESPN display name like "Brown Bears"), NOT
    # alternate_names (short forms like "Bears", "Brown") which cause false
    # positives: "bears" matching "chicago bears", "brown" matching "browns".
    my_team_names: list[str] = []
    if my_teams_only and user and ctx.team_relations:
        team_ids = list(ctx.team_relations.keys())
        team_name_result = await db.execute(
            select(Team.name).where(Team.id.in_(team_ids))
        )
        my_team_names = [name for (name,) in team_name_result.all() if name]

    feed_items = []

    # === SCORE EVENTS ===
    if include_events:
        try:
            event_items = await _score_events(db, now, sport, ctx, my_teams_only=my_teams_only, my_team_names=my_team_names, tag_filter=dynamic_tag_filter or None, static_tag_filter=static_tag_filter or None)
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
    _previous_at = _record_feed_timing(_timings, _started_at, _previous_at, "team_enrichment")

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
    if include_futures:
        try:
            futures_items = await _score_futures(
                db,
                now,
                sport,
                ctx,
                my_teams_only=my_teams_only,
                my_team_names=my_team_names,
                tag_filter=dynamic_tag_filter or None,
                static_tag_filter=static_tag_filter or None,
                timing_records=_timings,
                timing_started_at=_started_at,
            )

            feed_items.extend(_dedupe_futures_by_canonical(futures_items))
        except Exception as e:
            logger.error("Feed: futures scoring failed, returning partial feed: %s", e)
    _previous_at = _record_feed_timing(_timings, _started_at, _previous_at, "futures")

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
    # events (EI 85+, live elimination/buzzer-beater) keep their score.
    if event_pct is not None and event_pct < 0.3:
        for item in feed_items:
            if item["type"] != "event":
                continue
            data = item.get("data", {})
            ei = data.get("ei") or data.get("pulse")
            ei_score = ei.get("score", 0) if ei else 0
            headline = (item.get("headline") or "").lower()
            is_exceptional = (
                ei_score >= 70
                or any(kw in headline for kw in [
                    "elimination", "buzzer", "walk-off", "historic",
                    "upset", "comeback", "playoff", "championship",
                ])
                or item.get("score", 0) >= 90
            )
            if not is_exceptional:
                item["score"] = min(item["score"], 35)
        # Re-sort after demotion so demoted events fall below high-scoring futures
        feed_items.sort(key=lambda x: (x["score"], x.get("_sort_time", 0)), reverse=True)

    if not my_teams_only:
        if event_pct is not None and event_pct < 0.2:
            pass  # Discover mode: let scores decide, no artificial event promotion
        else:
            _epct = 0.6 if not ctx.is_authenticated else 0.4
            feed_items = _ensure_feed_diversity(feed_items, limit, event_pct=_epct)

    if not my_teams_only and ((event_pct is not None and event_pct < 0.3) or not include_events):
        feed_items = diversify_discover_first_page(feed_items, first_page_size=min(20, limit))
    _previous_at = _record_feed_timing(_timings, _started_at, _previous_at, "ranking")

    total = len(feed_items)
    paginated = feed_items[offset:offset + limit]

    debug_payload = None
    if debug:
        ground_truth_items = load_default_ground_truth_items()
        debug_payload = build_feed_quality_debug(
            paginated,
            ground_truth_items=ground_truth_items,
            top_n=min(20, len(paginated)),
        )
        await _attach_missing_ground_truth_traces(db, debug_payload["missing_ground_truth"], now)
    _previous_at = _record_feed_timing(_timings, _started_at, _previous_at, "debug")

    # Remove internal sort/debug keys
    for item in paginated:
        item.pop("_sort_time", None)
        item.pop("_quality_class", None)
        item.pop("_quality_family_key", None)
        item.pop("_quality_story_key", None)

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
            "pinned_events": len(ctx.pinned_event_ids),
            "pinned_futures": len(ctx.pinned_futures_ids),
        }

    if debug_payload is not None:
        payload["debug_summary"] = debug_payload["summary"]
        payload["debug_items"] = debug_payload["items"]
        payload["missing_ground_truth"] = debug_payload["missing_ground_truth"]
        payload["missing_ground_truth_summary"] = debug_payload["missing_ground_truth_summary"]
        payload["debug_timing"] = {
            "total_ms": round((time.perf_counter() - _started_at) * 1000, 2),
            "stages": _timings,
        }

    # --- Write to cache ---
    if _cache_key and _async_redis:
        try:
            await _async_redis.setex(_cache_key, _cache_ttl, _json_module.dumps(payload, default=str))
            await _async_redis.aclose()
        except Exception:
            pass

    _set_feed_timing_header(response, _started_at)
    return payload


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
            item["db_trace"] = summarize_missing_ground_truth_db_trace(item, [], now=now)
            continue

        tokens = _trace_search_tokens(item.get("name") or "")
        clauses = []
        if item.get("name"):
            clauses.append(FuturesMarket.name.ilike(f"%{item['name'][:120]}%"))
        if tokens:
            clauses.append(and_(*[FuturesMarket.name.ilike(f"%{token}%") for token in tokens[:3]]))
        if not clauses:
            item["db_trace"] = summarize_missing_ground_truth_db_trace(item, [], now=now)
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
                "volume_24h": float(row.volume_24h) if row.volume_24h is not None else None,
                "resolution_date": row.resolution_date.isoformat() if row.resolution_date else None,
                "hook_description": row.hook_description,
                "image_url": row.image_url,
            }
            for row in result.all()
        ]
        item["db_trace"] = summarize_missing_ground_truth_db_trace(item, matches, now=now)


def _utc(dt: datetime | None) -> datetime | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _market_base_trace(market: FuturesMarket, now: datetime) -> dict:
    blockers: list[str] = []
    if market.status != "open":
        blockers.append("not_open")
    if market.event_id is not None:
        blockers.append("event_linked_game_market")
    resolution_date = _utc(market.resolution_date)
    if resolution_date and resolution_date < now:
        blockers.append("past_resolution")
    if re.search(r"\bvs\.?\b", market.name or "", re.IGNORECASE):
        blockers.append("game_name_filtered")

    return {
        "eligible": not blockers,
        "blockers": blockers,
        "checks": {
            "status": market.status,
            "event_id": market.event_id,
            "resolution_date": resolution_date.isoformat() if resolution_date else None,
            "game_name_filtered": bool(re.search(r"\bvs\.?\b", market.name or "", re.IGNORECASE)),
        },
    }


def _top_outcomes_for_trace(market: FuturesMarket) -> tuple[list[dict], str | None, float | None]:
    sorted_outcomes = sorted(
        market.outcomes,
        key=lambda o: float(o.current_probability) if o.current_probability is not None else 0,
        reverse=True,
    )
    outcomes_data = []
    for outcome in sorted_outcomes[:10]:
        outcomes_data.append({
            "name": outcome.name,
            "probability": float(outcome.current_probability) if outcome.current_probability is not None else None,
            "probability_change_24h": (
                float(outcome.probability_change_24h)
                if outcome.probability_change_24h is not None else None
            ),
            "rank": outcome.rank,
            "rank_change_24h": outcome.rank_change_24h,
            "opening_probability": (
                float(outcome.opening_probability)
                if outcome.opening_probability is not None else None
            ),
        })

    leader_name = None
    leader_prob = None
    if sorted_outcomes:
        leader = sorted_outcomes[0]
        leader_name = leader.name
        leader_prob = float(leader.current_probability) if leader.current_probability is not None else None
    return outcomes_data, leader_name, leader_prob


def _market_runtime_filter_trace(
    market: FuturesMarket,
    outcomes_data: list[dict],
    leader_name: str | None,
    leader_prob: float | None,
    now: datetime,
) -> dict:
    blockers: list[str] = []
    probs_available = [o["probability"] for o in outcomes_data if o["probability"] is not None]
    all_settled = (
        len(probs_available) >= 2
        and all(p < 0.05 or p > 0.95 for p in probs_available)
    )
    if all_settled:
        blockers.append("all_outcomes_settled")

    leader_opening = None
    if leader_name:
        for outcome in outcomes_data:
            if outcome["name"] == leader_name:
                leader_opening = outcome.get("opening_probability")
                break
    is_effectively_resolved = leader_prob is not None and leader_prob >= 0.97
    if is_effectively_resolved and (leader_opening is None or leader_opening >= 0.85):
        blockers.append("effectively_resolved")

    has_any_movement = any(
        outcome["probability_change_24h"] is not None
        and abs(outcome["probability_change_24h"]) > 0.001
        for outcome in outcomes_data
    )

    days_stale = None
    updated_at = _utc(market.updated_at)
    if updated_at:
        days_stale = (now - updated_at).total_seconds() / 86400
        if days_stale > 7 and not has_any_movement:
            blockers.append("stale_no_movement")

    commence_time = _utc(market.commence_time)

    return {
        "eligible": not blockers,
        "blockers": blockers,
        "checks": {
            "all_outcomes_settled": all_settled,
            "leader_probability": leader_prob,
            "leader_opening_probability": leader_opening,
            "has_any_movement": has_any_movement,
            "days_stale": round(days_stale, 2) if days_stale is not None else None,
            "commence_time": commence_time.isoformat() if commence_time else None,
            "commence_time_staleness_applied": False,
        },
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
        ~FuturesMarket.name.ilike('% vs %'),
        ~FuturesMarket.name.ilike('% vs. %'),
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
    for name, extra_filter, ordering, limit in pool_specs:
        result = await db.execute(
            select(FuturesMarket.id)
            .where(*base_filters, extra_filter)
            .order_by(*ordering)
            .limit(limit)
        )
        ids = list(result.scalars().all())
        candidate_ids.extend(ids)
        pools.append({
            "name": name,
            "limit": limit,
            "candidate_count": len(ids),
            "included": market_id in ids,
            "position": ids.index(market_id) + 1 if market_id in ids else None,
        })

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
        "candidate_position": deduped.index(market_id) + 1 if market_id in seen else None,
        "pools": pools,
    }


def _score_market_trace(
    market: FuturesMarket,
    now: datetime,
    source_count: int,
) -> dict:
    outcomes_data, leader_name, leader_prob = _top_outcomes_for_trace(market)
    runtime_filters = _market_runtime_filter_trace(
        market,
        outcomes_data,
        leader_name,
        leader_prob,
        now,
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
    )

    top_mover_name = highlight_result.top_mover_name
    top_mover_change = None
    if top_mover_name:
        for outcome in outcomes_data:
            if outcome["name"] == top_mover_name and outcome.get("probability_change_24h"):
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
        if top_surprise_change is None or abs(surprise_change) > abs(top_surprise_change):
            top_surprise_name = outcome.get("name")
            top_surprise_change = surprise_change

    headline = generate_futures_headline(
        highlight_reasons=highlight_result.reasons,
        top_mover_name=top_mover_name,
        top_mover_change=top_mover_change,
        top_surprise_name=top_surprise_name,
        top_surprise_change=top_surprise_change,
        leader_name=leader_name,
        leader_probability=leader_prob,
        source_count=source_count,
    ) or highlight_result.primary_reason

    quality = classify_market_quality(
        market_name=market.name,
        sport_category=market.llm_sport_category,
        outcome_names=[outcome.name for outcome in market.outcomes if outcome.name],
    )
    quality_score = apply_quality_score(highlight_result.score, quality)
    explanation_score = apply_explanation_quality_score(
        quality_score,
        hook_description=market.hook_description,
        headline=headline,
        quality=quality,
    )
    p_result = compute_futures_multiplier(
        ctx=PersonalizationContext(),
        sport_category=market.llm_sport_category,
        outcome_team_ids=[o.team_id for o in market.outcomes if o.team_id is not None],
        futures_market_id=market.id,
        sport_key=market.sport.key if market.sport else None,
        outcome_names=[o.name for o in market.outcomes if o.name],
    )
    final_score = min(100, int(explanation_score * p_result.multiplier))

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
    if "stale_no_movement" in blockers or "effectively_resolved" in blockers:
        return "No ranking fix unless stale/resolved markets need a special recap surface."
    rank_phases = trace.get("rank_phases") or {}
    if rank_phases.get("dropped_by_canonical_dedupe"):
        return "Inspect canonical dedupe; this market is being collapsed behind a sibling."
    returned_rank = rank_phases.get("returned_rank")
    if returned_rank and returned_rank <= 50:
        return "No immediate fix; the market is eligible and present in the returned diagnostic feed."
    if not trace["final_ranking"]["survived_final_caps"]:
        return "Inspect quality family caps, story deduping, and first-page diversity for this story."
    if rank_phases.get("post_diversity_rank") and rank_phases["post_diversity_rank"] > 50:
        return "Inspect Discover diversity repair and category/story caps before tuning score."
    if trace["final_ranking"]["final_futures_rank"] and trace["final_ranking"]["final_futures_rank"] > 50:
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
    dropped_by_canonical_dedupe = raw_futures_rank is not None and post_dedupe_rank is None
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
                    item for item in deduped_futures
                    if (item.get("data") or {}).get("canonical_market_key") == target_key
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
        for item in feed_items:
            if item["type"] != "event":
                continue
            data = item.get("data", {})
            ei = data.get("ei") or data.get("pulse")
            ei_score = ei.get("score", 0) if ei else 0
            headline = (item.get("headline") or "").lower()
            is_exceptional = (
                ei_score >= 70
                or any(kw in headline for kw in [
                    "elimination", "buzzer", "walk-off", "historic",
                    "upset", "comeback", "playoff", "championship",
                ])
                or item.get("score", 0) >= 90
            )
            if not is_exceptional:
                item["score"] = min(item["score"], 35)
        feed_items.sort(key=lambda x: (x["score"], x.get("_sort_time", 0)), reverse=True)
        post_event_demote_rank = _rank_futures_market(feed_items, market_id)

    post_event_mix_rank = post_event_demote_rank
    if event_pct is not None and event_pct >= 0.2:
        feed_items = _ensure_feed_diversity(feed_items, limit, event_pct=0.6)
        post_event_mix_rank = _rank_futures_market(feed_items, market_id)

    post_diversity_rank = post_event_mix_rank
    if (event_pct is not None and event_pct < 0.3) or not include_events:
        feed_items = diversify_discover_first_page(feed_items, first_page_size=min(20, limit))
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
        .options(selectinload(FuturesMarket.outcomes), selectinload(FuturesMarket.sport))
        .where(FuturesMarket.id == market_id)
    )
    market = result.scalars().first()
    if not market:
        return None

    canonical_counts = await _get_canonical_source_counts(db)
    source_count = (
        canonical_counts.get(market.canonical_market_key, 1)
        if market.canonical_market_key else 1
    )
    base_eligibility = _market_base_trace(market, now)
    candidate_pools = await _discover_candidate_pool_trace(db, now, market_id)
    score_trace = _score_market_trace(market, now, source_count)

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
            "volume_24h": float(market.volume_24h) if market.volume_24h is not None else None,
            "resolution_date": _utc(market.resolution_date).isoformat() if _utc(market.resolution_date) else None,
            "updated_at": _utc(market.updated_at).isoformat() if _utc(market.updated_at) else None,
        },
        "base_eligibility": base_eligibility,
        "candidate_pools": candidate_pools,
        "score_trace": score_trace,
        "rank_phases": rank_phases,
        "final_ranking": {
            "survived_final_caps": rank_phases["returned"],
            "final_futures_rank": rank_phases["raw_futures_rank"],
            "final_score": score_trace["scores"]["final"] if rank_phases["raw_futures_rank"] else None,
            "scored_futures_count": rank_phases["raw_futures_count"],
        },
    }
    trace["suggested_fix"] = _suggest_trace_fix(trace)
    return trace


async def _load_personalization_context(
    db: AsyncSession,
    user: Optional[User],
) -> PersonalizationContext:
    """Load all user personalization data into a context object.

    Single query pattern: load favorites, preferences, and pins in parallel-ish
    SQLAlchemy queries, then assemble into the context.
    """
    if not user:
        return PersonalizationContext()

    # Load user favorites, preferences, and pins in parallel
    favorites_result, prefs_result, pins_result = await asyncio.gather(
        db.execute(select(UserFavorite).where(UserFavorite.user_id == user.id)),
        db.execute(select(UserPreference).where(UserPreference.user_id == user.id)),
        db.execute(select(UserPin).where(UserPin.user_id == user.id)),
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
    sport_affinities = prefs.sport_affinities if prefs and prefs.sport_affinities else {}

    pins = pins_result.scalars().all()
    pinned_event_ids = {p.target_id for p in pins if p.pin_type == "event"}
    pinned_futures_ids = {p.target_id for p in pins if p.pin_type == "future"}

    # Load roster player names from followed teams for player-futures matching
    roster_player_names: set[str] = set()
    followed_team_ids = [
        tid for tid, rels in team_relations.items()
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
        is_authenticated=True,
    )


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
        user_team_ids_list = list(set(ctx.team_relations.keys())) if ctx.team_relations else []
        if user_team_ids_list:
            team_conditions.append(Event.home_team_id.in_(user_team_ids_list))
            team_conditions.append(Event.away_team_id.in_(user_team_ids_list))
        if my_team_names:
            for tn in my_team_names:
                escaped = tn.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                team_conditions.append(Event.home_team_name.ilike(f"%{escaped}%"))
                team_conditions.append(Event.away_team_name.ilike(f"%{escaped}%"))
        if team_conditions:
            query = query.where(or_(*team_conditions))
        else:
            # No teams → nothing to show
            return []
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
                for team_name in (my_team_names or []):
                    if _team_name_matches(team_name, home_name):
                        matched_by_name = True
                        break
                    if _team_name_matches(team_name, away_name):
                        matched_by_name = True
                        break

            if not matched_by_id and not matched_by_name:
                continue

        opening_home_prob = float(event.opening_home_probability) if event.opening_home_probability else None
        opening_away_prob = float(event.opening_away_probability) if event.opening_away_probability else None

        # Always compute aggregate from all available sources (ESPN, stat model,
        # Kalshi, Polymarket, sportsbook consensus). Falls back through tiers.
        current_home_prob = _compute_aggregate_probability(event)
        if current_home_prob is None and event.id in snapshot_fallbacks:
            current_home_prob = snapshot_fallbacks[event.id]
        current_away_prob = round(1.0 - current_home_prob, 6) if current_home_prob is not None else None

        # Skip events without any probability data:
        # - Scheduled: StatPal-created events not yet matched to Odds API
        # - Completed/closed with no scores: no odds movement, no final score
        #   = terrible UX (empty chart, no data). These are typically niche
        #   sports where only StatPal has schedules but no odds coverage.
        if current_home_prob is None and event.status == "scheduled":
            continue
        if (current_home_prob is None
                and event.status in ("completed", "closed")
                and not event.home_score and not event.away_score):
            continue

        # Track whether we have sportsbook-specific data or only aggregate
        has_sportsbook_odds = opening_home_prob is not None
        prob_source = None if has_sportsbook_odds else ("aggregate" if current_home_prob is not None else None)

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
            current_home_spread=float(event.opening_home_spread) if event.opening_home_spread else None,
            current_over_under=float(event.opening_over_under) if event.opening_over_under else None,
            opening_home_prob=opening_home_prob,
            opening_away_prob=opening_away_prob,
            opening_home_spread=float(event.opening_home_spread) if event.opening_home_spread else None,
            opening_over_under=float(event.opening_over_under) if event.opening_over_under else None,
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

        _source_count = len(event.win_probability_sources) if event.win_probability_sources else 0
        _game_progress, _ = parse_game_progress(event.period, sport_key)

        base_score, extra_reasons = compute_base_score(
            highlight_score=highlight_result.score,
            highlight_reasons=highlight_result.reasons,
            home_champ_prob=champ_probs.get(event.home_team_id, 0) if event.home_team_id else 0,
            away_champ_prob=champ_probs.get(event.away_team_id, 0) if event.away_team_id else 0,
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
        )
        personalized_score = min(100, int(base_score * p_result.multiplier))

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

        ended_at = get_statpal_end_time(event) if event.status in ("completed", "closed") else None
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

        # Include personalization debug info when score was boosted/suppressed
        if p_result.is_personalized:
            item["personalized"] = True
            item["base_score"] = base_score
            item["multiplier"] = round(p_result.multiplier, 2)
            item["personalization_reasons"] = p_result.reasons

        scored_items.append(item)

    return scored_items


async def _score_futures(
    db: AsyncSession,
    now: datetime,
    sport_filter: Optional[str],
    ctx: PersonalizationContext,
    my_teams_only: bool = False,
    my_team_names: Optional[list] = None,
    tag_filter: Optional[list[str]] = None,
    static_tag_filter: Optional[list[str]] = None,
    timing_records: Optional[list[dict[str, float | str]]] = None,
    timing_started_at: float | None = None,
) -> list[dict]:
    """Score and format futures markets for the feed.

    Uses per-category queries to guarantee diversity. A single big query
    sorted by resolution_date is dominated by crypto's 8,955 five-minute
    markets, so we query each category separately.
    """
    timing_previous_at = time.perf_counter()

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
        ~FuturesMarket.name.ilike('% vs %'),
        ~FuturesMarket.name.ilike('% vs. %'),
        # NOTE: '% at %' filter deliberately removed — it killed non-sports
        # markets like "S&P at 4pm", "temperature at NYC". The event_id IS NULL
        # filter already excludes game matchups.
    ]

    base_options = [
        selectinload(FuturesMarket.outcomes),
        selectinload(FuturesMarket.sport),
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
            FuturesMarket.market_tags.op("@>")(cast(_json_mod.dumps(static_tag_filter), JSONB))
        )

    # Pool 1: sports futures (capped — tier-ordered so best surface first)
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
        .limit(50)
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
        .limit(180)
    )

    movement_expr = (
        select(func.max(func.abs(FuturesOutcome.probability_change_24h)))
        .where(FuturesOutcome.market_id == FuturesMarket.id)
        .correlate(FuturesMarket)
        .scalar_subquery()
    )

    # Pool 2b: non-sports by actual movement. This surfaces stories that are
    # changing quickly even if their absolute volume is lower.
    nonsports_movement_query = (
        select(FuturesMarket.id)
        .where(
            *id_filters,
            non_sports_filter,
        )
        .order_by(
            movement_expr.desc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        )
        .limit(160)
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
        .limit(160)
    )

    # Pool 2d: soon-resolving markets. Timeliness matters, but this pool is
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
        .limit(120)
    )

    candidate_queries_started_at = timing_previous_at
    sports_result = await db.execute(sports_query)
    mark_timing("pool_sports")
    nonsports_result = await db.execute(nonsports_query)
    mark_timing("pool_nonsports_volume")
    nonsports_movement_result = await db.execute(nonsports_movement_query)
    mark_timing("pool_nonsports_movement")
    nonsports_enriched_result = await db.execute(nonsports_enriched_query)
    mark_timing("pool_nonsports_enriched")
    nonsports_timely_result = await db.execute(nonsports_timely_query)
    mark_timing("pool_nonsports_timely")
    mark_timing("candidate_queries", since_at=candidate_queries_started_at, update_previous=False)

    candidate_market_ids = (
        list(sports_result.scalars().all())
        + list(nonsports_result.scalars().all())
        + list(nonsports_movement_result.scalars().all())
        + list(nonsports_enriched_result.scalars().all())
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
    canonical_source_counts = await _get_canonical_source_counts(db)
    mark_timing("canonical_counts")

    scored_items = []
    for market in markets:
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
            change = float(o.probability_change_24h) if o.probability_change_24h else None
            outcomes_data.append({
                "name": o.name,
                "probability": prob,
                "probability_change_24h": change,
                "rank": o.rank,
                "rank_change_24h": o.rank_change_24h,
                "opening_probability": float(o.opening_probability) if o.opening_probability else None,
            })

        if sorted_outcomes:
            leader = sorted_outcomes[0]
            leader_name = leader.name
            leader_prob = float(leader.current_probability) if leader.current_probability else None

        # --- Staleness filters ---
        # 1) All outcomes settled: every outcome is <5% or >95%
        probs_available = [o["probability"] for o in outcomes_data if o["probability"] is not None]
        all_settled = (
            len(probs_available) >= 2
            and all(p < 0.05 or p > 0.95 for p in probs_available)
        )
        if all_settled:
            continue

        # 2) Leader at ≥97% with no interesting journey
        is_effectively_resolved = leader_prob is not None and leader_prob >= 0.97
        if is_effectively_resolved:
            leader_opening = None
            for o in outcomes_data:
                if o["name"] == leader_name:
                    leader_opening = o.get("opening_probability")
                    break
            if leader_opening is None or leader_opening >= 0.85:
                continue

        # 3) Stale market: no price updates for 7+ days and zero movement
        has_any_movement = any(
            o["probability_change_24h"] is not None and abs(o["probability_change_24h"]) > 0.001
            for o in outcomes_data
        )
        if market.updated_at:
            days_stale = (now - market.updated_at.replace(tzinfo=timezone.utc if market.updated_at.tzinfo is None else market.updated_at.tzinfo)).total_seconds() / 86400
            if days_stale > 7 and not has_any_movement:
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
            if top_surprise_change is None or abs(surprise_change) > abs(top_surprise_change):
                top_surprise_name = o.get("name")
                top_surprise_change = surprise_change

        headline = generate_futures_headline(
            highlight_reasons=highlight_result.reasons,
            top_mover_name=top_mover_name,
            top_mover_change=top_mover_change,
            top_surprise_name=top_surprise_name,
            top_surprise_change=top_surprise_change,
            leader_name=leader_name,
            leader_probability=leader_prob,
            source_count=source_count,
        ) or highlight_result.primary_reason

        quality = classify_market_quality(
            market_name=market.name,
            sport_category=market.llm_sport_category,
            outcome_names=[o.name for o in market.outcomes if o.name],
        )
        if quality.quality_class == "suppress":
            continue

        base_score = apply_quality_score(highlight_result.score, quality)
        base_score = apply_explanation_quality_score(
            base_score,
            hook_description=market.hook_description,
            headline=headline,
            quality=quality,
        )
        if quality.reasons:
            highlight_result.reasons.extend(f"quality:{r}" for r in quality.reasons)

        # Apply personalization multiplier
        outcome_team_ids = [o.team_id for o in market.outcomes if o.team_id is not None]

        # my_teams_only: skip futures that don't involve the user's teams
        if my_teams_only:
            matched_by_id = bool(set(outcome_team_ids) & user_team_ids)

            # Fall back to outcome name matching when team_ids aren't linked
            matched_by_name = False
            if not matched_by_id and my_team_names:
                for o in market.outcomes:
                    if o.name:
                        for team_name in (my_team_names or []):
                            if _team_name_matches(team_name, o.name):
                                matched_by_name = True
                                break
                    if matched_by_name:
                        break

            if not matched_by_id and not matched_by_name:
                continue

        # Collect matched outcome details for "why is this here?" context
        matched_outcomes_list = []
        if my_teams_only and user_team_ids:
            for o in market.outcomes:
                is_match = False
                if o.team_id and o.team_id in user_team_ids:
                    is_match = True
                elif my_team_names and o.name:
                    for team_name in (my_team_names or []):
                        if _team_name_matches(team_name, o.name):
                            is_match = True
                            break
                if is_match:
                    matched_outcomes_list.append({
                        "name": o.name,
                        "probability": float(o.current_probability) if o.current_probability else None,
                        "rank": o.rank,
                        "movement": float(o.probability_change_24h) if o.probability_change_24h else None,
                    })

        outcome_names = [o.name for o in market.outcomes if o.name]
        p_result = compute_futures_multiplier(
            ctx=ctx,
            sport_category=market.llm_sport_category,
            outcome_team_ids=outcome_team_ids,
            futures_market_id=market.id,
            sport_key=market.sport.key if market.sport else None,
            outcome_names=outcome_names,
        )
        personalized_score = min(100, int(base_score * p_result.multiplier))

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
            top_mover_name=top_mover_name,
            top_mover_change=top_mover_change,
            top_surprise_name=top_surprise_name,
            top_surprise_change=top_surprise_change,
            leader_name=leader_name,
            leader_probability=leader_prob,
            source_count=source_count,
        )

        # Build compact futures data for the feed
        top_outcomes_data = [
            {
                "id": o.id,
                "name": o.name,
                "probability": float(o.current_probability) if o.current_probability else None,
                "rank": o.rank,
                "movement": float(o.probability_change_24h) if o.probability_change_24h else None,
            }
            for o in sorted_outcomes[:3]  # Show top 3 in feed card
        ]

        futures_data = {
            "id": market.id,
            "name": market.name,
            "sport": market.sport.key if market.sport else None,
            "sport_name": market.sport.name if market.sport else None,
            "llm_sport_category": market.llm_sport_category,
            "source": market.source,
            "source_count": source_count,
            "market_tier": market.market_tier,
            "status": market.status,
            "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
            "top_outcomes": top_outcomes_data,
            "outcome_count": len(market.outcomes),
            "canonical_market_key": market.canonical_market_key,
            "image_url": market.image_url,
            "hook_description": market.hook_description,
        }

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
    mark_timing("scoring_loop")

    scored_items = cap_low_quality_families(scored_items, cap=1)
    scored_items = diversify_quality_families(
        scored_items,
        exact_family_cap=1,
        story_family_cap=5,
    )
    mark_timing("caps")
    for item in scored_items:
        item.pop("_quality_class", None)
        item.pop("_quality_family_key", None)
        item.pop("_quality_story_key", None)

    return scored_items


_canonical_source_counts_cache: Optional[dict[str, int]] = None
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
    if _champ_prob_cache is not None and (now_ts - _champ_prob_cache_ts) < _CHAMP_PROB_CACHE_TTL:
        return _champ_prob_cache

    from sqlalchemy import text
    result = await db.execute(
        text("""
            SELECT fo.team_id, MAX(fo.current_probability) AS max_prob
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fo.market_id = fm.id
            WHERE fm.market_tier = 1
              AND fm.status = 'open'
              AND fo.team_id IS NOT NULL
              AND fo.current_probability IS NOT NULL
              AND fo.current_probability > 0
            GROUP BY fo.team_id
        """)
    )
    cache = {row.team_id: float(row.max_prob) for row in result.all()}
    _champ_prob_cache = cache
    _champ_prob_cache_ts = now_ts
    return cache


async def _get_canonical_source_counts(db: AsyncSession) -> dict[str, int]:
    """Get source count for each canonical market key (cached 5 min)."""
    import time

    global _canonical_source_counts_cache, _canonical_source_counts_ts
    now = time.time()
    if _canonical_source_counts_cache is not None and (now - _canonical_source_counts_ts) < _CANONICAL_CACHE_TTL:
        return _canonical_source_counts_cache

    result = await db.execute(
        select(
            FuturesMarket.canonical_market_key,
            func.count(func.distinct(FuturesMarket.source)).label("source_count"),
        )
        .where(FuturesMarket.canonical_market_key.isnot(None))
        .group_by(FuturesMarket.canonical_market_key)
    )
    cache = {row.canonical_market_key: row.source_count for row in result.all()}
    _canonical_source_counts_cache = cache
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
    non_events = sorted(futures + other, key=lambda x: (x["score"], x.get("_sort_time", 0)), reverse=True)
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
_GOLF_CACHE_TTL = 120  # 2 minutes


_DEFAULT_FEED_TOURS = frozenset({"pga", "major", "dp_world", "lpga", "liv"})

# Map tournament tour values to user affinity keys
_TOUR_AFFINITY_KEYS: dict[str, str] = {
    "pga": "golf_pga",
    "major": "golf_pga",       # Majors bundled with PGA Tour
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
                "winner" in n.lower() or "outright" in n.lower()
                for n in market_names
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
        reason = f"{t.get('tour_label', 'Golf')}: {leader['name']} leads at {leader_pct}%"
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

        feed_items.append({
            "type": "tournament",
            "score": score,
            "reason": reason,
            "headline": headline,
            "data": data,
            "_sort_time": (
                datetime.fromisoformat(t["commence_time"]).timestamp()
                if t.get("commence_time") else 0
            ),
        })

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
