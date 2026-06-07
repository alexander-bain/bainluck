"""
Market enrichment tasks: image fetching and LLM hook descriptions.

Runs nightly to enrich FuturesMarket rows with:
1. image_url — relevant photo from Pexels API
2. hook_description — LLM-generated 1-sentence hook explaining why the market is interesting
"""

import os
import logging
import asyncio
import re
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select, update

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
DISCOVER_LLM_METADATA_KEY = "discover_llm"
DISCOVER_LLM_SCHEMA_VERSION = 1
DISCOVER_LLM_MODEL = os.getenv("DISCOVER_LLM_MODEL", "gpt-4o-mini")


def _json_from_llm_response(text: str) -> dict[str, Any]:
    """Parse a JSON object from common LLM response wrappers."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object")
    return data


def _clean_string_list(value: Any, *, max_items: int = 8, max_len: int = 60) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        token = re.sub(r"\s+", " ", item.strip().lower())
        token = re.sub(r"[^a-z0-9 &'/:._-]", "", token)
        if not token or token in seen:
            continue
        seen.add(token)
        cleaned.append(token[:max_len])
        if len(cleaned) >= max_items:
            break
    return cleaned


def _sanitize_discover_llm_metadata(data: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """Keep LLM output small, typed, and safe to consume synchronously."""
    salience = data.get("salience_score", 3)
    try:
        salience_score = int(round(float(salience)))
    except (TypeError, ValueError):
        salience_score = 3
    salience_score = max(1, min(5, salience_score))

    def clean_scalar(key: str, default: str = "other", max_len: int = 50) -> str:
        raw = data.get(key)
        if not isinstance(raw, str):
            return default
        value = re.sub(r"\s+", "_", raw.strip().lower())
        value = re.sub(r"[^a-z0-9_:-]", "", value)
        return (value or default)[:max_len]

    audience_scope = clean_scalar("audience_scope", "broad")
    if audience_scope not in {"broad", "mainstream", "niche", "local", "specialist"}:
        audience_scope = "broad"

    return {
        "schema_version": DISCOVER_LLM_SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "model": DISCOVER_LLM_MODEL,
        "topic": clean_scalar("topic"),
        "subtopic": clean_scalar("subtopic"),
        "archetype": clean_scalar("archetype"),
        "audience_scope": audience_scope,
        "salience_score": salience_score,
        "entities": _clean_string_list(data.get("entities"), max_items=8),
        "junk_flags": _clean_string_list(data.get("junk_flags"), max_items=6),
        "comparison_axes": _clean_string_list(data.get("comparison_axes"), max_items=5),
        "why_interesting": str(data.get("why_interesting") or "").strip()[:240],
    }


def _discover_llm_score_adjustment(metadata: dict[str, Any] | None) -> int:
    """Deterministic score nudge from cached LLM metadata.

    Keep this bounded, but let LLM-derived low-signal labels matter enough to
    move local/niche junk out of the first-page candidate set.
    """
    if not metadata:
        return 0
    try:
        salience = int(metadata.get("salience_score") or 3)
    except (TypeError, ValueError):
        salience = 3
    salience = max(1, min(5, salience))
    adjustment = (salience - 3) * 3
    audience_scope = metadata.get("audience_scope")
    adjustment += {
        "niche": -15,
        "local": -25,
        "specialist": -20,
    }.get(audience_scope, 0)
    junk_flags = metadata.get("junk_flags") or []
    junk_penalties = {
        "local_election": -20,
        "low_tier_sports": -15,
        "minor_soccer": -15,
        "procedural_politics": -15,
        "commodity_ladder": -15,
    }
    for flag in junk_flags:
        normalized = str(flag).strip().lower().replace(" ", "_")
        adjustment += junk_penalties.get(normalized, -6)
    if metadata.get("entities"):
        adjustment += 2
    return max(-30, min(10, adjustment))


def _discover_llm_feature_tokens(metadata: dict[str, Any] | None) -> list[str]:
    """Feature tokens generated offline for swipe personalization."""
    if not metadata:
        return []
    tokens: list[str] = []
    for key in ("topic", "subtopic", "archetype", "audience_scope"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            tokens.append(f"llm_{key}:{value}")
    for entity in metadata.get("entities") or []:
        if isinstance(entity, str) and entity:
            normalized = re.sub(r"[^a-z0-9]+", "_", entity.lower()).strip("_")
            if normalized:
                tokens.append(f"llm_entity:{normalized}")
    for axis in metadata.get("comparison_axes") or []:
        if isinstance(axis, str) and axis:
            normalized = re.sub(r"[^a-z0-9]+", "_", axis.lower()).strip("_")
            if normalized:
                tokens.append(f"llm_axis:{normalized}")
    return tokens[:20]


def _get_discover_llm_metadata(market_metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(market_metadata, dict):
        return None
    metadata = market_metadata.get(DISCOVER_LLM_METADATA_KEY)
    if not isinstance(metadata, dict):
        return None
    if metadata.get("schema_version") != DISCOVER_LLM_SCHEMA_VERSION:
        return None
    return metadata


def _metadata_needs_discover_llm_refresh(
    market_metadata: dict[str, Any] | None,
    *,
    now: datetime,
    max_age_days: int = 30,
) -> bool:
    metadata = _get_discover_llm_metadata(market_metadata)
    if not metadata:
        return True
    generated_at = metadata.get("generated_at")
    if not generated_at:
        return True
    try:
        generated = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    return generated < now - timedelta(days=max_age_days)


def _extract_image_keywords(name: str, category: str | None) -> str:
    name = re.sub(r"\b(Winner|Over/Under|O/U|Spread|Total|Moneyline)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\b(on|at|in|the|a|an|of|for|to|vs\.?|by)\b", " ", name, flags=re.IGNORECASE)
    name = re.sub(r"\d{4}[-/]\d{2,4}", "", name)
    name = re.sub(r"[:\-–—|()#]", " ", name)
    words = [w for w in name.split() if len(w) > 2][:4]
    if not words and category:
        words = [category]
    return " ".join(words)


async def _fetch_pexels_image(query: str) -> str | None:
    """Fetch best image from Pexels. Gets 5 candidates and picks the highest resolution landscape."""
    if not PEXELS_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.pexels.com/v1/search",
                params={
                    "query": query,
                    "per_page": 5,
                    "orientation": "landscape",
                    "size": "medium",
                },
                headers={"Authorization": PEXELS_API_KEY},
            )
            if resp.status_code != 200:
                logger.warning("Pexels API returned %d for query '%s'", resp.status_code, query)
                return None
            data = resp.json()
            photos = data.get("photos", [])
            if not photos:
                return None

            # Score candidates: prefer wider images (better for cards),
            # reject tiny images, prefer photos with alt text (better indexed)
            best = None
            best_score = -1
            for photo in photos:
                w = photo.get("width", 0)
                h = photo.get("height", 0)
                if w < 400 or h < 250:
                    continue
                ratio = w / max(h, 1)
                score = w
                if 1.3 <= ratio <= 2.0:
                    score += 200
                if photo.get("alt"):
                    score += 100
                if score > best_score:
                    best_score = score
                    best = photo

            if not best:
                best = photos[0]

            return best["src"].get("large", best["src"]["medium"])
    except Exception as e:
        logger.error("Pexels fetch error for '%s': %s", query, e)
        return None


async def enrich_market_images(limit: int = 50):
    """Fetch images from Pexels for markets missing image_url."""
    from app.models.models import FuturesMarket

    if not PEXELS_API_KEY:
        logger.info("PEXELS_API_KEY not set — skipping image enrichment")
        return {"skipped": True}

    stats = {"fetched": 0, "found": 0, "errors": 0}

    async with get_task_session() as session:
        result = await session.execute(
            select(FuturesMarket.id, FuturesMarket.name, FuturesMarket.llm_sport_category)
            .where(
                FuturesMarket.image_url.is_(None),
                FuturesMarket.status == "open",
            )
            .order_by(FuturesMarket.volume_24h.desc().nullslast())
            .limit(limit)
        )
        markets = result.all()

        for market_id, name, category in markets:
            query = _extract_image_keywords(name, category)
            if not query.strip():
                continue

            url = await _fetch_pexels_image(query)
            stats["fetched"] += 1

            if url:
                await session.execute(
                    update(FuturesMarket)
                    .where(FuturesMarket.id == market_id)
                    .values(image_url=url)
                )
                stats["found"] += 1
            else:
                stats["errors"] += 1

            await asyncio.sleep(0.5)

        await session.commit()

    logger.info("Image enrichment: %s", stats)
    return stats


def _load_polymarket_blurbs() -> list[dict]:
    """Load curated Polymarket email blurbs for few-shot examples."""
    import json
    from pathlib import Path
    blurb_file = Path(__file__).parent.parent / "data" / "polymarket_blurbs.json"
    if not blurb_file.exists():
        return []
    try:
        return json.loads(blurb_file.read_text())
    except Exception:
        return []


def _needs_regeneration(
    market, current_leader_name: str, current_leader_prob: float | None, now: datetime
) -> bool:
    """Check if an existing hook should be regenerated.

    Re-generates when:
    - No hook yet
    - Leader changed
    - Hook older than 24h
    - Leader probability moved >= 15pp from generation-time snapshot
    """
    from app.utils.hook_staleness import (
        HOOK_PROB_METADATA_KEY,
        STALE_PROBABILITY_DELTA,
    )

    if not market.hook_description:
        return True
    if not market.hook_generated_at:
        return True
    age_hours = (now - market.hook_generated_at).total_seconds() / 3600
    if market.hook_leader_at_generation and market.hook_leader_at_generation != current_leader_name:
        return True
    # Check probability delta against generation-time snapshot
    if current_leader_prob is not None and isinstance(market.market_metadata, dict):
        gen_prob = market.market_metadata.get(HOOK_PROB_METADATA_KEY)
        if gen_prob is not None:
            try:
                if abs(float(current_leader_prob) - float(gen_prob)) >= STALE_PROBABILITY_DELTA:
                    return True
            except (TypeError, ValueError):
                pass
    if age_hours < 24 and market.hook_leader_at_generation == current_leader_name:
        return False
    if age_hours >= 24:
        return True
    return False


async def enrich_market_hooks(limit: int = 50):
    """Generate Polymarket-style context blurbs for markets."""
    import random
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.llm import _get_client
    from sqlalchemy import case, or_

    client = _get_client()
    if not client:
        logger.info("OpenAI not available — skipping hook enrichment")
        return {"skipped": True}

    now = datetime.now(timezone.utc)
    stats = {"processed": 0, "generated": 0, "regenerated": 0, "skipped": 0, "errors": 0}

    blurbs = _load_polymarket_blurbs()

    async with get_task_session() as session:
        feed_categories = [
            "politics",
            "geopolitics",
            "economics",
            "tech",
            "health",
            "entertainment",
            "weather",
        ]
        feed_category_priority = case(
            (
                FuturesMarket.llm_sport_category.in_(feed_categories),
                0,
            ),
            else_=1,
        )
        liquidity_priority = case(
            (FuturesMarket.volume_24h >= 5_000, 0),
            else_=1,
        )

        feed_candidate_scope = or_(
            FuturesMarket.llm_sport_category.in_(feed_categories),
            FuturesMarket.volume_24h >= 5_000,
            FuturesMarket.market_tier <= 3,
        )

        # Only enrich feed-shaped candidates. Do not grind through the entire
        # open-market backlog: there are tens of thousands of open markets, and
        # most should never need LLM hooks unless they become plausible Discover
        # candidates.
        result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.status == "open",
                feed_candidate_scope,
                or_(
                    FuturesMarket.hook_description.is_(None),
                    FuturesMarket.hook_generated_at.is_(None),
                    FuturesMarket.hook_generated_at < now - timedelta(hours=24),
                ),
            )
            .order_by(
                FuturesMarket.hook_description.is_(None).desc(),
                feed_category_priority.asc(),
                liquidity_priority.asc(),
                FuturesMarket.volume_24h.desc().nullslast(),
                FuturesMarket.updated_at.desc().nullslast(),
                FuturesMarket.market_tier.asc().nullslast(),
                FuturesMarket.resolution_date.asc().nullslast(),
            )
            .limit(limit * 3)
        )
        candidates = result.scalars().all()

        processed = 0
        for market in candidates:
            if processed >= limit:
                break

            outcome_result = await session.execute(
                select(
                    FuturesOutcome.name,
                    FuturesOutcome.current_probability,
                    FuturesOutcome.opening_probability,
                    FuturesOutcome.probability_change_24h,
                )
                .where(FuturesOutcome.market_id == market.id)
                .order_by(FuturesOutcome.rank.asc().nullslast())
                .limit(5)
            )
            outcomes = outcome_result.all()
            if not outcomes:
                continue

            leader = outcomes[0]
            leader_name = leader.name
            leader_prob = (
                float(leader.current_probability)
                if leader.current_probability is not None
                else None
            )

            if not _needs_regeneration(market, leader_name, leader_prob, now):
                stats["skipped"] += 1
                continue

            was_regen = market.hook_description is not None

            # Build leaderboard context
            leaderboard_lines = []
            for i, o in enumerate(outcomes):
                prob = int((o.current_probability or 0) * 100)
                opening = int((o.opening_probability or 0) * 100) if o.opening_probability else None
                change = o.probability_change_24h
                parts = [f"#{i+1} {o.name}: {prob}%"]
                if opening and abs(prob - opening) >= 3:
                    parts.append(f"(opened {opening}%)")
                if change and abs(change) >= 0.01:
                    parts.append(f"{'↑' if change > 0 else '↓'}{abs(int(change * 100))}% 24h")
                leaderboard_lines.append(" ".join(parts))

            resolve_str = ""
            if market.resolution_date:
                resolve_str = f"Resolves: {market.resolution_date.strftime('%b %d, %Y')}"

            volume_str = ""
            if market.volume_24h and market.volume_24h > 0:
                vol = market.volume_24h
                if vol >= 1_000_000:
                    volume_str = f"24h volume: ${vol/1_000_000:.1f}M"
                elif vol >= 1_000:
                    volume_str = f"24h volume: ${vol/1_000:.0f}K"

            # Pick 2-3 random Polymarket blurb examples for variety
            examples = random.sample(blurbs, min(3, len(blurbs))) if blurbs else []
            example_str = "\n".join(f'- "{ex["blurb"]}"' for ex in examples) if examples else (
                '- "The son of former Brazilian president Bolsonaro has surged into the lead, buoyed by new polls showing right-wing momentum"\n'
                '- "Cameron Young is running away with the Cadillac Championship after a tournament-record 64 in round one"\n'
                '- "Fed Chair Powell hinted at rate cuts, sending this market surging — three of four economists now expect a cut by September"'
            )

            prompt = (
                f"Write 1-2 sentences (max 250 chars) explaining WHY a reader should care about this topic RIGHT NOW. "
                f"Write like a journalist, not a market description. Focus on what happened, what changed, or why this matters. "
                f"NEVER include specific percentages or probability numbers — those are shown separately and go stale. "
                f"NEVER reference prediction markets, Polymarket, Kalshi, odds, traders, betting, or gambling — write as pure news context.\n\n"
                f"Market: {market.name}\n"
                f"Category: {market.llm_sport_category or 'general'}\n"
                f"Leaderboard:\n" + "\n".join(leaderboard_lines) + "\n"
                f"{resolve_str}\n"
                f"{volume_str}\n\n"
                f"Examples of great hooks:\n{example_str}\n\n"
                f"Your hook:"
            )

            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=150,
                    temperature=0.7,
                )
                hook = response.choices[0].message.content.strip().strip('"').strip("'")
                if "%" in hook:
                    hook = re.sub(r"\d+(\.\d+)?%", "", hook).strip()
                    hook = re.sub(r"\s{2,}", " ", hook)
                if len(hook) > 500:
                    hook = hook[:497] + "..."

                # Store generation-time probability in market_metadata
                # so serve-time staleness check can detect big probability
                # swings without a schema migration.
                from app.utils.hook_staleness import HOOK_PROB_METADATA_KEY

                next_metadata = dict(market.market_metadata or {})
                if leader_prob is not None:
                    next_metadata[HOOK_PROB_METADATA_KEY] = round(leader_prob, 4)
                elif HOOK_PROB_METADATA_KEY in next_metadata:
                    del next_metadata[HOOK_PROB_METADATA_KEY]

                await session.execute(
                    update(FuturesMarket)
                    .where(FuturesMarket.id == market.id)
                    .values(
                        hook_description=hook,
                        hook_generated_at=now,
                        hook_leader_at_generation=leader_name,
                        market_metadata=next_metadata,
                    )
                )
                stats["generated"] += 1
                if was_regen:
                    stats["regenerated"] += 1
            except Exception as e:
                logger.error("Hook generation error for market %d: %s", market.id, e)
                stats["errors"] += 1

            stats["processed"] += 1
            processed += 1
            await asyncio.sleep(0.3)

        await session.commit()

    logger.info("Hook enrichment: %s", stats)
    return stats


async def enrich_discover_llm_metadata(limit: int = 100):
    """Generate cached structured Discover metadata for feed-shaped markets."""
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.llm import _get_client
    from sqlalchemy import case, or_

    client = _get_client()
    if not client:
        logger.info("OpenAI not available - skipping Discover LLM metadata")
        return {"skipped": True}

    now = datetime.now(timezone.utc)
    stats = {
        "processed": 0,
        "generated": 0,
        "skipped_fresh": 0,
        "errors": 0,
        "estimated_input_tokens": 0,
        "estimated_output_tokens": 0,
    }

    async with get_task_session() as session:
        feed_categories = [
            "politics",
            "geopolitics",
            "economics",
            "tech",
            "health",
            "entertainment",
            "weather",
            "basketball",
            "baseball",
            "football",
            "hockey",
            "soccer",
            "golf",
        ]
        feed_category_priority = case(
            (FuturesMarket.llm_sport_category.in_(feed_categories), 0),
            else_=1,
        )
        feed_candidate_scope = or_(
            FuturesMarket.llm_sport_category.in_(feed_categories),
            FuturesMarket.volume_24h >= 5_000,
            FuturesMarket.market_tier <= 3,
        )

        result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.status == "open",
                feed_candidate_scope,
                FuturesMarket.llm_sport_category != "crypto",
            )
            .order_by(
                feed_category_priority.asc(),
                FuturesMarket.volume_24h.desc().nullslast(),
                FuturesMarket.updated_at.desc().nullslast(),
                FuturesMarket.market_tier.asc().nullslast(),
            )
            .limit(limit * 4)
        )
        candidates = result.scalars().all()

        for market in candidates:
            if stats["processed"] >= limit:
                break
            if not _metadata_needs_discover_llm_refresh(market.market_metadata, now=now):
                stats["skipped_fresh"] += 1
                continue

            outcome_result = await session.execute(
                select(
                    FuturesOutcome.name,
                    FuturesOutcome.current_probability,
                    FuturesOutcome.probability_change_24h,
                )
                .where(FuturesOutcome.market_id == market.id)
                .order_by(FuturesOutcome.rank.asc().nullslast())
                .limit(8)
            )
            outcomes = outcome_result.all()
            outcome_lines = []
            for outcome in outcomes:
                probability = int(float(outcome.current_probability or 0) * 100)
                movement = float(outcome.probability_change_24h or 0)
                movement_text = f", 24h move {movement * 100:+.1f}pp" if abs(movement) >= 0.01 else ""
                outcome_lines.append(f"- {outcome.name}: {probability}%{movement_text}")

            prompt = (
                "Classify this prediction-market card for a casual Discover feed. "
                "Return only compact JSON with keys: topic, subtopic, entities, archetype, "
                "audience_scope, salience_score, junk_flags, comparison_axes, why_interesting.\n\n"
                "Definitions:\n"
                "- salience_score: integer 1-5 for whether a normal curious person would care.\n"
                "- audience_scope: one of broad, mainstream, niche, local, specialist.\n"
                "- junk_flags: short strings for low-signal cards such as local_election, low_tier_sports, "
                "minor_soccer, procedural_politics, commodity_ladder, repetitive_bucket, thin_liquidity, "
                "stale_context. Empty if none.\n"
                "- comparison_axes: dimensions useful for game pairings, like sports_vs_music, culture, macro, election, ai_tech.\n\n"
                f"Market: {market.name}\n"
                f"Category: {market.llm_sport_category or market.category or 'other'}\n"
                f"Source: {market.source}\n"
                f"24h volume: {market.volume_24h or 0}\n"
                f"Resolution date: {market.resolution_date.isoformat() if market.resolution_date else 'unknown'}\n"
                "Outcomes:\n"
                + ("\n".join(outcome_lines) if outcome_lines else "- unknown")
            )

            try:
                response = client.chat.completions.create(
                    model=DISCOVER_LLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=350,
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or "{}"
                raw = _json_from_llm_response(content)
                metadata = _sanitize_discover_llm_metadata(raw, now=now)
                next_metadata = dict(market.market_metadata or {})
                next_metadata[DISCOVER_LLM_METADATA_KEY] = metadata
                await session.execute(
                    update(FuturesMarket)
                    .where(FuturesMarket.id == market.id)
                    .values(market_metadata=next_metadata)
                )
                usage = getattr(response, "usage", None)
                if usage:
                    stats["estimated_input_tokens"] += int(getattr(usage, "prompt_tokens", 0) or 0)
                    stats["estimated_output_tokens"] += int(getattr(usage, "completion_tokens", 0) or 0)
                stats["generated"] += 1
            except Exception as exc:
                logger.warning("Discover LLM metadata failed for market %s: %s", market.id, exc)
                stats["errors"] += 1
                try:
                    await session.rollback()
                except Exception:
                    pass

            stats["processed"] += 1
            await asyncio.sleep(0.15)

        await session.commit()

    logger.info("Discover LLM metadata enrichment: %s", stats)
    return stats


def _compact_feed_item_for_llm(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data") or {}
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "category": data.get("llm_sport_category"),
        "score": item.get("score"),
        "headline": item.get("headline"),
        "context_summary": item.get("context_summary"),
        "top_outcomes": data.get("top_outcomes") or [],
    }


async def generate_discover_comparison_candidates(limit: int = 60):
    """Generate cached cross-category comparison-game pair candidates."""
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.llm import _get_client
    from app.tasks.redis_state import get_async_redis_client

    client = _get_client()
    if not client:
        logger.info("OpenAI not available - skipping Discover comparison candidates")
        return {"skipped": True}

    now = datetime.now(timezone.utc)
    async with get_task_session() as session:
        result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.status == "open",
                FuturesMarket.market_metadata.isnot(None),
                FuturesMarket.llm_sport_category != "crypto",
            )
            .order_by(
                FuturesMarket.volume_24h.desc().nullslast(),
                FuturesMarket.updated_at.desc().nullslast(),
            )
            .limit(300)
        )
        markets = []
        for market in result.scalars().all():
            metadata = _get_discover_llm_metadata(market.market_metadata)
            if not metadata:
                continue
            if int(metadata.get("salience_score") or 0) < 4:
                continue
            if metadata.get("junk_flags"):
                continue
            markets.append((market, metadata))
            if len(markets) >= 80:
                break

        cards = []
        for market, metadata in markets:
            outcome_result = await session.execute(
                select(FuturesOutcome.name, FuturesOutcome.current_probability)
                .where(FuturesOutcome.market_id == market.id)
                .order_by(FuturesOutcome.rank.asc().nullslast())
                .limit(1)
            )
            leader = outcome_result.first()
            probability = float(leader.current_probability) if leader and leader.current_probability else None
            cards.append({
                "id": market.id,
                "name": market.name,
                "category": market.llm_sport_category,
                "topic": metadata.get("topic"),
                "archetype": metadata.get("archetype"),
                "comparison_axes": metadata.get("comparison_axes") or [],
                "leader_probability": round(probability * 100) if probability is not None else None,
            })

    if len(cards) < 8:
        return {"generated": 0, "reason": "not_enough_enriched_cards"}

    prompt = (
        "Create fun Discover comparison-game pairs from these prediction cards. "
        "A good pair compares two different categories where the user can guess which probability is higher. "
        "Return JSON: {\"pairs\":[{\"left_id\":1,\"right_id\":2,\"prompt\":\"...\",\"reason\":\"...\"}]}.\n"
        f"Return at most {limit} pairs. Avoid same-category pairs, stale/local/niche items, and pairs where one side is obscure.\n\n"
        f"Cards:\n{json.dumps(cards, separators=(',', ':'))}"
    )

    try:
        response = client.chat.completions.create(
            model=DISCOVER_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1800,
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        raw = _json_from_llm_response(response.choices[0].message.content or "{}")
        pairs = raw.get("pairs") if isinstance(raw.get("pairs"), list) else []
        valid_ids = {card["id"] for card in cards}
        cleaned = []
        for pair in pairs:
            if not isinstance(pair, dict):
                continue
            left_id = pair.get("left_id")
            right_id = pair.get("right_id")
            if left_id not in valid_ids or right_id not in valid_ids or left_id == right_id:
                continue
            cleaned.append({
                "left_id": left_id,
                "right_id": right_id,
                "prompt": str(pair.get("prompt") or "Which is more likely?")[:160],
                "reason": str(pair.get("reason") or "")[:240],
            })
            if len(cleaned) >= limit:
                break
        redis = get_async_redis_client()
        await redis.setex(
            "bainluck:discover_comparison_candidates:v1",
            60 * 60 * 30,
            json.dumps({"generated_at": now.isoformat(), "pairs": cleaned}, default=str),
        )
        await redis.aclose()
        return {"generated": len(cleaned), "candidate_cards": len(cards)}
    except Exception as exc:
        logger.warning("Discover comparison generation failed: %s", exc)
        return {"generated": 0, "errors": 1, "error": str(exc)}


async def evaluate_discover_with_llm(limit: int = 50):
    """Daily LLM review of top Discover futures plus email-highlight misses."""
    from app.models.models import DiscoverReviewDecision
    from app.routes.feed import _score_futures
    from app.utils.personalization import PersonalizationContext
    from app.utils.feed_quality_debug import find_missing_ground_truth_items
    from app.utils.polymarket_email_ground_truth import load_polymarket_email_ground_truth_report_from_env
    from app.services.llm import _get_client

    client = _get_client()
    if not client:
        logger.info("OpenAI not available - skipping Discover LLM eval")
        return {"skipped": True}

    now = datetime.now(timezone.utc)
    stats = {"graded": 0, "proposals": 0, "email_misses": 0, "errors": 0}

    async with get_task_session() as session:
        items = await _score_futures(
            session,
            now,
            sport_filter=None,
            ctx=PersonalizationContext(),
            my_teams_only=False,
        )
        items = sorted(items, key=lambda item: item.get("score") or 0, reverse=True)[:limit]
        compact = [_compact_feed_item_for_llm(item) for item in items]
        diagnosed = [
            {
                "name": card.get("name"),
                "archetype": None,
                "story_key": None,
            }
            for card in compact
        ]
        email_report = await asyncio.to_thread(
            load_polymarket_email_ground_truth_report_from_env,
            now=now,
        )
        email_items = email_report.get("items") or []
        email_misses = find_missing_ground_truth_items(diagnosed, email_items, limit=20)
        stats["email_misses"] = len(email_misses)

        prompt = (
            "You are reviewing the top Discover prediction-market cards. "
            "Grade each card for a casual user's feed quality. Return JSON only: "
            "{\"reviews\":[{\"id\":123,\"grade\":1-5,\"action\":\"keep|promote|downrank|investigate\","
            "\"reason\":\"short reason\"}]}. "
            "Downrank boring low-tier sports, local elections, repetitive buckets, and narrow commodity ladders. "
            "Promote broad, surprising, timely, culturally interesting, or cross-category cards.\n\n"
            f"Top cards:\n{json.dumps(compact, separators=(',', ':'))}\n\n"
            f"Polymarket email highlights missing from top feed:\n{json.dumps(email_misses[:10], separators=(',', ':'))}"
        )

        try:
            response = client.chat.completions.create(
                model=DISCOVER_LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2200,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            raw = _json_from_llm_response(response.choices[0].message.content or "{}")
            reviews = raw.get("reviews") if isinstance(raw.get("reviews"), list) else []
            by_id = {int((item.get("data") or {}).get("id")): item for item in items if (item.get("data") or {}).get("id") is not None}
            for review in reviews:
                if not isinstance(review, dict):
                    continue
                try:
                    market_id = int(review.get("id"))
                except (TypeError, ValueError):
                    continue
                item = by_id.get(market_id)
                if not item:
                    continue
                action = str(review.get("action") or "keep").lower()
                if action not in {"promote", "downrank", "investigate"}:
                    continue
                data = item.get("data") or {}
                decision = f"llm_proposed_{action}"
                existing = await session.execute(
                    select(DiscoverReviewDecision)
                    .where(
                        DiscoverReviewDecision.item_type == "futures",
                        DiscoverReviewDecision.item_id == str(market_id),
                        DiscoverReviewDecision.decision == decision,
                    )
                    .order_by(DiscoverReviewDecision.created_at.desc())
                    .limit(1)
                )
                row = existing.scalars().first()
                notes = (
                    f"LLM daily eval grade={review.get('grade')}; "
                    f"reason={str(review.get('reason') or '')[:400]}"
                )
                if row:
                    row.admin_notes = notes
                    row.created_at = now
                else:
                    session.add(DiscoverReviewDecision(
                        item_type="futures",
                        item_id=str(market_id),
                        item_name=data.get("name"),
                        category=data.get("llm_sport_category"),
                        surface="llm_eval",
                        auth_segment="anonymous",
                        decision=decision,
                        admin_notes=notes,
                    ))
                stats["proposals"] += 1
            stats["graded"] = len(reviews)

            for miss in email_misses[:10]:
                key = re.sub(r"[^a-z0-9]+", "-", str(miss.get("name") or "").lower()).strip("-")[:90]
                if not key:
                    continue
                notes = (
                    "Polymarket email highlight missing from top Discover. "
                    f"triage={miss.get('triage_bucket')}; action={miss.get('recommended_action')}"
                )[:5000]
                existing = await session.execute(
                    select(DiscoverReviewDecision)
                    .where(
                        DiscoverReviewDecision.item_type == "email",
                        DiscoverReviewDecision.item_id == key,
                        DiscoverReviewDecision.decision == "llm_proposed_promote",
                    )
                    .order_by(DiscoverReviewDecision.created_at.desc())
                    .limit(1)
                )
                row = existing.scalars().first()
                if row:
                    row.admin_notes = notes
                    row.created_at = now
                else:
                    session.add(DiscoverReviewDecision(
                        item_type="email",
                        item_id=key,
                        item_name=miss.get("name"),
                        category=miss.get("category"),
                        surface="llm_eval",
                        auth_segment="ground_truth",
                        family_key=miss.get("family_key"),
                        archetype=miss.get("archetype"),
                        decision="llm_proposed_promote",
                        admin_notes=notes,
                    ))
                stats["proposals"] += 1

            await session.commit()
        except Exception as exc:
            logger.warning("Discover LLM eval failed: %s", exc)
            stats["errors"] += 1

    logger.info("Discover LLM eval: %s", stats)
    return stats
