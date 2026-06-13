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
from sqlalchemy import select, update, func

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
DISCOVER_LLM_METADATA_KEY = "discover_llm"
DISCOVER_LLM_SCHEMA_VERSION = 1
DISCOVER_LLM_MODEL = os.getenv("DISCOVER_LLM_MODEL", "gpt-4o-mini")

# CU v2 writer revision. Bump this (NOT schema_version) to force a re-tag of
# existing schema_version=2 profiles when the writer logic changes but the
# schema shape does not. Consumers still gate on schema_version; re-tag
# freshness gates on writer_rev so a logic fix re-runs over already-tagged rows.
CU_WRITER_REV = 4


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

                # Persist story_key alongside LLM metadata
                from app.utils.feed_market_quality import _story_key
                computed_story_key = _story_key(
                    market.name or "",
                    market.llm_sport_category or market.category or "other",
                )

                await session.execute(
                    update(FuturesMarket)
                    .where(FuturesMarket.id == market.id)
                    .values(
                        market_metadata=next_metadata,
                        story_key=computed_story_key,
                    )
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


_CU_V2_PROMPT = """You are classifying a prediction-market card for a casual audience's Discover feed. Return ONLY valid JSON matching the schema below — no extra keys, no prose.

Market: {name}
Category: {category}
Source: {source}
Resolution date: {resolution_date}
Outcomes:
{outcomes}

CLASSIFICATION RULES (apply exactly — these are corrected from graded errors):
1. temporal: recurring institutional decisions and scheduled measurements are "periodic" (Fed decisions, daily high-temperature markets, weekly tweet counts). Any "by [date]?" phrasing is "deadline" even when an event underlies it (ceasefires, IPOs). Reserve "event_tied" for a singular real-world event with its own date (a match, an election, a tournament). Do NOT over-use event_tied.
2. topic boundaries: armed-conflict / international-relations markets are "geopolitics" regardless of the countries involved (Russia–Ukraine included). "esports" means VIDEO-GAME competitions ONLY (Counter-Strike/CS2, Dota, League of Legends, Valorant, Overwatch, Rocket League, Call of Duty, StarCraft, etc.) — matches AND tournament winners (e.g. IEM Cologne) are "esports". A "X vs Y" matchup is NOT automatically esports: traditional/physical sports played by humans (tennis, table tennis, badminton, snooker, darts, cricket, soccer, basketball, etc.) are "sports" even when phrased as "Tournament: Player A vs Player B" (e.g. an ATP tennis match is "sports", never "esports"). Celebrity-business stunts (e.g. Musk/OnlyFans) are "entertainment", not economics.
3. stakes = magnitude of the real-world consequence, NOT market volume: ceasefires/peace deals 4–5, pandemics 3+, an esports match 1, a celebrity tweet count 1.
4. breadth = how many ORDINARY people know/care about THIS market's specific subject — not the topic's global fame: an esports match is 1 (regardless of how popular the game is), an esports tournament winner 2, the World Cup 5.
5. oddity baseline is 1. Ordinary markets — including dramatic ones — are 1. Reserve 3+ for genuine weirdness (clavicular pregnancy 5, Musk-buys-OnlyFans 5); a 2 must be justified.
6. event_date sanity: the event_date must be plausible relative to the resolution date above. It should NOT be in the distant past for a market that has not yet resolved (e.g. a 2023 date on a 2026 market is wrong), and for an in-progress series/season an event_tied date more than 13 months in the future is almost certainly wrong. If your derived date falls outside roughly [a few weeks before the resolution date, ~13 months after today], re-derive it or return null rather than guessing a wild year.

CALIBRATED EXAMPLES (market -> topic / temporal / stakes,breadth,oddity):
- "CS: NaVi vs Legacy (BO3)" -> esports / event_tied / S1 B1 O1
- "Stuttgart Open: Kyrgios vs Moutet" -> sports (tennis) / event_tied / S1 B1 O1   (a human-played match is NOT esports)
- "Israel–Hezbollah ceasefire by…?" -> geopolitics / deadline / S4 B4 O1
- "Fed Decision in June?" -> economics / periodic / S3 B4 O1
- "Love Island USA: Winning Couple" -> entertainment / event_tied / S5 B3 O2
- "Clavicular pregnancy in 2026?" -> health / deadline / S1 B1 O5
- "Highest temp in Seoul, June 12" -> weather / periodic / S1 B3 O1

JSON schema:
{{
  "topic": "sports|esports|politics|geopolitics|economics|tech|entertainment|culture|health|weather|crypto",
  "subtopic": "<lowercase open vocab, e.g. basketball, elections, fed, ai, awards>",
  "entities": [{{"name": "<lowercase>", "type": "team|person|org|place|work|event"}}],
  "geography": "us|global|local|country:<XX>",
  "story_key": "story:<slug>",
  "series_key": "series:<slug>|null",
  "temporal": "event_tied|deadline|evergreen|periodic",
  "event_date": "<YYYY-MM-DD or null — the real-world moment, NOT resolution_date>",
  "recurrence": "one_off|annual|weekly|daily|null",
  "stakes": <1-5, real-world consequence magnitude per rule 3>,
  "breadth": <1-5, reach of THIS market's subject per rule 4>,
  "oddity": <1-5, baseline 1 per rule 5>,
  "arc": "race|comeback|collapse|milestone|upset_watch|none",
  "hook_facts": [{{"type": "stat|context|comparison", "text": "<one falsifiable claim>"}}],
  "junk_flags": ["<ladder|dated_bucket|social_count|duplicate_phrasing — empty array if none>"],
  "confidence": <0.0-1.0, your confidence in this classification>
}}"""


def _compute_liveness(outcome_probs: list[float] | None, status: str | None) -> str:
    """Computed liveness signal — is anything in this market still in play?

    Derived from the MOST COMPETITIVE outcome (closest to a coin flip), not the
    rank-1 outcome. On bundled markets (esports, prop-heavy events) the rank-1
    outcome is frequently a settled side-prop pinned at 0%/100% — e.g. "First
    Blood in Game 2?" at 100% for an open match — which falsely read as "dead".
    The most-competitive outcome reflects whether the market's real question is
    still undecided.
    """
    if status and status != "open":
        return "resolved"
    probs = [p for p in (outcome_probs or []) if p is not None]
    if not probs:
        return "unknown"
    best = min(probs, key=lambda p: abs(p - 0.5))
    if best <= 0.02 or best >= 0.98:
        return "dead"
    if best <= 0.05 or best >= 0.95:
        return "extreme"
    return "active"


async def enrich_cu_v2_profiles(limit: int = 125):
    """Generate Content Understanding v2 profiles for feed-shaped markets.

    Writes to market_metadata['discover_llm'] with schema_version=2.
    v1 profiles are preserved — v2 overwrites the same key but consumers
    check schema_version before reading.
    """
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.llm import _get_client
    from sqlalchemy import or_

    client = _get_client()
    if not client:
        return {"skipped": True, "reason": "no_openai_key"}

    now = datetime.now(timezone.utc)
    stats = {
        "processed": 0, "generated": 0, "skipped_fresh": 0,
        "errors": 0, "input_tokens": 0, "output_tokens": 0,
        "estimated_cost_usd": 0.0,
    }
    COST_CAP_USD = 30.0

    # Phase 1: ONE upfront read — materialize everything as plain dicts.
    # Zero ORM objects survive into the write loop (gotcha #6).
    work_items: list[dict] = []
    async with get_task_session() as read_session:
        feed_categories = [
            "politics", "geopolitics", "economics", "tech", "health",
            "entertainment", "weather", "basketball", "baseball",
            "football", "hockey", "soccer", "golf", "culture", "mma",
        ]
        from sqlalchemy import text as _text
        rows = await read_session.execute(_text("""
            SELECT fm.id, fm.name, fm.source, fm.status,
                   COALESCE(fm.llm_sport_category, fm.category, 'other') AS category,
                   fm.resolution_date, fm.market_metadata,
                   (SELECT json_agg(json_build_object(
                       'name', fo.name,
                       'prob', fo.current_probability,
                       'move', fo.probability_change_24h
                   ) ORDER BY fo.rank ASC NULLS LAST)
                    FROM futures_outcomes fo
                    WHERE fo.market_id = fm.id
                    LIMIT 8
                   ) AS outcomes
            FROM futures_markets fm
            WHERE fm.status = 'open'
              AND fm.llm_sport_category != 'crypto'
              AND (fm.llm_sport_category = ANY(:cats) OR fm.volume_24h >= 5000 OR fm.market_tier <= 3)
            ORDER BY fm.volume_24h DESC NULLS LAST, fm.updated_at DESC NULLS LAST
            LIMIT :lim
        """), {"cats": feed_categories, "lim": limit * 4})

        for r in rows.mappings().all():
            meta = r["market_metadata"] or {}
            if isinstance(meta, str):
                meta = json.loads(meta)
            existing = meta.get(DISCOVER_LLM_METADATA_KEY)
            if (
                existing
                and isinstance(existing, dict)
                and existing.get("schema_version") == 2
                and existing.get("writer_rev") == CU_WRITER_REV
            ):
                # Only honor the freshness skip when the profile was produced by
                # the current writer revision. A writer_rev bump forces a re-tag
                # of older rev profiles even if they are <24h old.
                ts = existing.get("generated_at", "")
                if ts:
                    try:
                        age = (now - datetime.fromisoformat(ts)).total_seconds()
                        if age < 86400:
                            stats["skipped_fresh"] += 1
                            continue
                    except (ValueError, TypeError):
                        pass

            outcomes_raw = r["outcomes"] or []
            if isinstance(outcomes_raw, str):
                outcomes_raw = json.loads(outcomes_raw)
            outcome_lines = []
            leader_prob = None
            all_probs: list[float] = []
            for i, o in enumerate(outcomes_raw[:8]):
                prob = float(o.get("prob") or 0)
                if i == 0:
                    leader_prob = prob
                move = float(o.get("move") or 0)
                move_text = f", 24h {move * 100:+.1f}pp" if abs(move) >= 0.01 else ""
                outcome_lines.append(f"- {o.get('name', '?')}: {int(prob * 100)}%{move_text}")
            # Liveness is computed from the full outcome set (not just the 8 shown
            # to the LLM) so bundled prop markets are classified correctly.
            for o in outcomes_raw:
                if o.get("prob") is not None:
                    all_probs.append(float(o.get("prob")))

            work_items.append({
                "id": r["id"],
                "name": r["name"],
                "source": r["source"],
                "status": r["status"],
                "category": r["category"],
                "resolution_date": r["resolution_date"].isoformat() if r["resolution_date"] else "unknown",
                "metadata": dict(meta),
                "outcome_lines": outcome_lines,
                "leader_prob": leader_prob,
                "outcome_probs": all_probs,
            })
            if len(work_items) >= limit:
                break

    logger.info("CU v2: %d candidates materialized, %d skipped fresh", len(work_items), stats["skipped_fresh"])

    # Phase 2: LLM calls + Core UPDATEs only — no session reads.
    async with get_task_session() as write_session:
        for item in work_items:
            if stats["estimated_cost_usd"] >= COST_CAP_USD:
                logger.warning("CU v2: cost cap reached ($%.2f), stopping", stats["estimated_cost_usd"])
                break

            prompt = _CU_V2_PROMPT.format(
                name=item["name"] or "",
                category=item["category"],
                source=item["source"] or "",
                resolution_date=item["resolution_date"],
                outcomes="\n".join(item["outcome_lines"]) if item["outcome_lines"] else "- unknown",
            )

            try:
                response = client.chat.completions.create(
                    model=DISCOVER_LLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500,
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or "{}"
                raw = _json_from_llm_response(content)

                usage = getattr(response, "usage", None)
                if usage:
                    inp = int(getattr(usage, "prompt_tokens", 0) or 0)
                    out = int(getattr(usage, "completion_tokens", 0) or 0)
                    stats["input_tokens"] += inp
                    stats["output_tokens"] += out
                    stats["estimated_cost_usd"] += (inp * 0.15 + out * 0.60) / 1_000_000

                liveness = _compute_liveness(item["outcome_probs"], item["status"])
                profile = {
                    "schema_version": 2,
                    "writer_rev": CU_WRITER_REV,
                    "model": DISCOVER_LLM_MODEL,
                    "generated_at": now.isoformat(),
                    "topic": raw.get("topic"),
                    "subtopic": raw.get("subtopic"),
                    "entities": raw.get("entities", []),
                    "geography": raw.get("geography"),
                    "story_key": raw.get("story_key"),
                    "series_key": raw.get("series_key"),
                    "temporal_class": raw.get("temporal"),
                    "event_date": raw.get("event_date"),
                    "recurrence": raw.get("recurrence"),
                    "stakes": raw.get("stakes"),
                    "breadth": raw.get("breadth"),
                    "oddity": raw.get("oddity"),
                    "arc": raw.get("arc"),
                    "hook_facts": raw.get("hook_facts", []),
                    "junk_flags": raw.get("junk_flags", []),
                    "confidence": raw.get("confidence"),
                    "liveness": liveness,
                }

                next_metadata = dict(item["metadata"])
                next_metadata[DISCOVER_LLM_METADATA_KEY] = profile

                await write_session.execute(
                    update(FuturesMarket)
                    .where(FuturesMarket.id == item["id"])
                    .values(market_metadata=next_metadata)
                )

                story_key = raw.get("story_key")
                if story_key:
                    from sqlalchemy import text as _text
                    await write_session.execute(
                        _text("UPDATE futures_markets SET story_key = :sk WHERE id = :mid"),
                        {"sk": story_key, "mid": item["id"]},
                    )
                stats["generated"] += 1
            except Exception as exc:
                logger.warning("CU v2 failed for market %s: %s", item["id"], exc)
                stats["errors"] += 1
                try:
                    await write_session.rollback()
                except Exception:
                    pass

            stats["processed"] += 1
            await asyncio.sleep(0.15)

        await write_session.commit()

    logger.info("CU v2 enrichment: %s", stats)
    return stats


def _get_cu_v2_profile(market_metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the discover_llm profile only when it is a CU v2 (schema_version=2)
    profile. The judge consumes v2 fields (temporal_class, liveness); the v1
    reader (_get_discover_llm_metadata) intentionally rejects v2, so this is a
    separate accessor (#596)."""
    if not isinstance(market_metadata, dict):
        return None
    metadata = market_metadata.get(DISCOVER_LLM_METADATA_KEY)
    if not isinstance(metadata, dict):
        return None
    if metadata.get("schema_version") != 2:
        return None
    return metadata


def _compact_feed_item_for_llm(
    item: dict[str, Any], profile: dict[str, Any] | None = None
) -> dict[str, Any]:
    data = item.get("data") or {}
    top = data.get("top_outcomes") or []
    leader_prob = top[0].get("probability") if top else None

    is_extreme = False
    if leader_prob is not None:
        is_extreme = leader_prob < 0.02 or leader_prob > 0.98

    compact = {
        "id": data.get("id"),
        "name": data.get("name"),
        "category": data.get("llm_sport_category"),
        "score": item.get("score"),
        "headline": item.get("headline"),
        "context_summary": item.get("context_summary"),
        "top_outcomes": top,
        "status": data.get("status"),
        "leader_probability": round(leader_prob, 3) if leader_prob is not None else None,
        "probability_extreme": is_extreme,
        "resolution_date": data.get("resolution_date"),
    }
    # CU v2 profile context (temporal_class + liveness) as first-class judge
    # signals (#596). Degrade gracefully when a card has no v2 profile.
    if profile:
        compact["temporal_class"] = profile.get("temporal_class")
        compact["liveness"] = profile.get("liveness")
        compact["cu_profile"] = True
    else:
        compact["cu_profile"] = False
    return compact


# Fallback few-shots when no human verdicts exist yet in discover_review_decisions.
_JUDGE_FALLBACK_FEW_SHOTS = (
    "- 'NHL Stanley Cup Champion' during Finals week -> keep (live major sport)\n"
    "- 'Will Nathalie Arthaud run for French president?' at 78% -> downrank (obscure foreign election)\n"
    "- 'Emmy nominations: Outstanding Television Movie' -> keep (broad entertainment)\n"
    "- 'Tudor Black Bay watch price Up or Down: June' -> downrank (narrow commodity ladder)\n"
    "- 'US-Iran nuclear deal by June 30?' -> promote (major geopolitical)\n"
    "- Market at 99.2% -> downrank (dead probability, resolved in practice)"
)


def _format_live_sports_context(league_rows: list[tuple]) -> str:
    """Render a 'what is live/imminent this week' block from REAL event counts.

    league_rows: iterable of (sport_key, game_count) for scheduled/live games in
    the next ~7 days. Pure/testable. Fixes the judge's live-sports blindness —
    it downranked hockey/basketball/mma/soccer DURING their Finals/Cup because
    the old static block didn't tell it what was actually playing (#596).
    """
    rows = [(k, c) for k, c in (league_rows or []) if k and c]
    if not rows:
        return (
            "LIVE/IMMINENT SPORTS THIS WEEK: none detected. Treat sports futures "
            "with no active season as low-value."
        )
    parts = ", ".join(f"{k} ({c})" for k, c in rows)
    return (
        "LIVE/IMMINENT SPORTS THIS WEEK (real game counts, next 7 days): "
        f"{parts}. Markets about these leagues' current games/series are HIGH-VALUE "
        "— do NOT downrank them as 'no active season'. Leagues NOT in this list have "
        "no games this week; their futures are lower-value."
    )


def _format_judge_few_shots(human_decisions: list[dict[str, Any]]) -> str:
    """Build corrective few-shots from the human reviewer's own verdicts (#596).

    rejected_* verdicts are the precision-improving signal (the judge's past
    mistakes); accepted_* confirm correct calls. Pure/testable. Falls back to a
    static set when no human verdicts exist yet.
    """
    lines: list[str] = []
    for d in human_decisions or []:
        name = (d.get("name") or "").strip()
        if not name:
            continue
        dec = d.get("decision")
        if dec == "rejected_promote":
            lines.append(f"- '{name}' -> do NOT promote (keep/downrank); reviewer rejected a promote here")
        elif dec == "rejected_downrank":
            lines.append(f"- '{name}' -> do NOT downrank (keep); reviewer rejected a downrank here")
        elif dec == "accepted_promote":
            lines.append(f"- '{name}' -> promote (reviewer confirmed)")
        elif dec == "accepted_downrank":
            lines.append(f"- '{name}' -> downrank (reviewer confirmed)")
        if len(lines) >= 6:
            break
    return "\n".join(lines) if lines else _JUDGE_FALLBACK_FEW_SHOTS


def _assemble_judge_prompt(
    date_str: str,
    sports_context: str,
    few_shots: str,
    compact: list[dict[str, Any]],
    email_misses: list[dict[str, Any]],
) -> str:
    """Assemble the Discover judge prompt. Pure/testable (#596)."""
    return (
        f"Today is {date_str}. You are reviewing the top Discover prediction-market "
        "cards for a casual audience's feed quality.\n\n"
        f"{sports_context}\n\n"
        "EACH CARD MAY INCLUDE A CONTENT-UNDERSTANDING PROFILE:\n"
        "- temporal_class: deadline | event_tied | periodic | evergreen (how it resolves in time).\n"
        "- liveness: active | extreme | dead | resolved | unknown (derived from the MOST "
        "COMPETITIVE outcome). 'dead'/'resolved' = the real question is already decided; "
        "'extreme' = nearly decided. Cards with cu_profile=false must be judged on "
        "probability/status alone.\n\n"
        "RULES:\n"
        "- HARD RULE: never 'promote' a card whose liveness is 'dead'/'resolved'/'extreme', "
        "or probability_extreme=true, or leader <2% / >98%. A decided market has zero "
        "discovery value — at most 'keep', usually 'downrank'.\n"
        "- status='resolved' or past resolution_date is stale -> downrank.\n"
        "- Use temporal_class: a 'deadline'/'event_tied' market whose event already passed is "
        "stale; an upcoming dated event is timely.\n"
        "- LIVE major-sport games/series for the leagues listed above are high-value -> keep or promote.\n"
        "- Downrank: minor local elections, narrow commodity/index/KPI ladders, repetitive "
        "threshold buckets, low-tier sports with NO active season this week.\n"
        "- Promote: broad public interest, surprising/odd questions, timely cultural moments, "
        "geopolitical developments, cross-category oddities — but only when liveness is 'active'.\n\n"
        "FEW-SHOT EXAMPLES (from the human reviewer's own verdicts — match this judgment):\n"
        f"{few_shots}\n\n"
        "Return JSON only: "
        "{\"reviews\":[{\"id\":123,\"grade\":1-5,\"action\":\"keep|promote|downrank|investigate\","
        "\"reason\":\"short reason\"}]}\n\n"
        f"Top cards:\n{json.dumps(compact, separators=(',', ':'))}\n\n"
        f"Polymarket email highlights missing from top feed:\n"
        f"{json.dumps(email_misses[:10], separators=(',', ':'))}"
    )


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

        # CU v2 profiles (temporal_class + liveness) for the graded markets,
        # fetched in one query and merged into the compact cards (#596).
        from app.models.models import FuturesMarket, Event, Sport
        market_ids = [
            int((it.get("data") or {}).get("id"))
            for it in items
            if (it.get("data") or {}).get("id") is not None
        ]
        profiles_by_id: dict[int, dict] = {}
        if market_ids:
            prof_rows = await session.execute(
                select(FuturesMarket.id, FuturesMarket.market_metadata)
                .where(FuturesMarket.id.in_(market_ids))
            )
            for mid, meta in prof_rows.all():
                prof = _get_cu_v2_profile(meta)
                if prof:
                    profiles_by_id[mid] = prof
        cu_hits = len(profiles_by_id)
        if market_ids and cu_hits < len(market_ids):
            logger.info(
                "Judge CU v2 coverage: %d/%d profiles present (%d missing — judged on prob/status)",
                cu_hits, len(market_ids), len(market_ids) - cu_hits,
            )

        compact = []
        for it in items:
            mid = (it.get("data") or {}).get("id")
            prof = profiles_by_id.get(int(mid)) if mid is not None else None
            compact.append(_compact_feed_item_for_llm(it, prof))

        # Dynamic "what's live this week" sports context from real event counts.
        week_ahead = now + timedelta(days=7)
        sport_rows = await session.execute(
            select(Sport.key, func.count(Event.id))
            .join(Event)
            .where(
                Event.status.in_(["scheduled", "live"]),
                Event.commence_time >= now - timedelta(hours=6),
                Event.commence_time <= week_ahead,
            )
            .group_by(Sport.key)
            .order_by(func.count(Event.id).desc())
        )
        sports_context = _format_live_sports_context(sport_rows.all())

        # Corrective few-shots from the human reviewer's own verdicts; rejections
        # (the judge's past mistakes) ranked first, then accepted confirmations.
        fs_rows = await session.execute(
            select(DiscoverReviewDecision.item_name, DiscoverReviewDecision.decision)
            .where(DiscoverReviewDecision.decision.in_([
                "rejected_promote", "rejected_downrank",
                "accepted_promote", "accepted_downrank",
            ]))
            .order_by(DiscoverReviewDecision.created_at.desc())
            .limit(60)
        )
        _human = [{"name": n, "decision": d} for n, d in fs_rows.all() if n]
        _human.sort(key=lambda r: 0 if str(r["decision"]).startswith("rejected_") else 1)
        few_shots = _format_judge_few_shots(_human)

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

        date_str = now.strftime("%B %d, %Y")
        prompt = _assemble_judge_prompt(
            date_str, sports_context, few_shots, compact, email_misses
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


_SNIPPET_REPHRASE_PROMPT = """Rewrite this market context line in wire-service voice.
Rules: one sentence, under 80 chars, no emoji, no probability numbers,
no quotation marks, factual not hype. Keep the core signal (direction, magnitude, source).

Market: {market_name}
Raw: {raw_snippet}
Rewrite:"""


async def _llm_rephrase_snippet(
    market_name: str, raw_snippet: str, angle_type: str
) -> str | None:
    """Call GPT-4o-mini to rephrase a deterministic snippet template.

    Returns the rephrased text, or None if the call fails or no API key.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        import openai

        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": _SNIPPET_REPHRASE_PROMPT.format(
                        market_name=market_name, raw_snippet=raw_snippet
                    ),
                }
            ],
            max_tokens=60,
            temperature=0.4,
        )
        text = response.choices[0].message.content.strip().strip('"').strip("'")
        if len(text) > 120:
            text = text[:117] + "..."
        return text if text else None
    except Exception as exc:
        logger.debug("Snippet rephrase failed for %s: %s", market_name[:40], exc)
        return None


async def enrich_snippet_angles(limit: int = 125):
    """Compute snippet angles for feed-shaped markets and cache in market_metadata.

    Runs as a batched background task (same cadence as enrich_discover_llm_metadata).
    Stores (angle_type, snippet_text) in market_metadata['snippet_v2'].
    """
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.utils.snippet_angles import MarketContext, select_angle
    from sqlalchemy import case, or_

    now = datetime.now(timezone.utc)
    stats = {"processed": 0, "angles_found": 0, "skipped_fresh": 0, "errors": 0}

    async with get_task_session() as session:
        feed_categories = [
            "politics", "geopolitics", "economics", "tech", "health",
            "entertainment", "weather", "basketball", "baseball",
            "football", "hockey", "soccer", "golf",
        ]
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
                FuturesMarket.volume_24h.desc().nullslast(),
                FuturesMarket.updated_at.desc().nullslast(),
            )
            .limit(limit * 3)
        )
        candidates = result.scalars().all()

        for market in candidates:
            if stats["processed"] >= limit:
                break

            # Skip if snippet_v2 was computed recently (< 2h)
            existing = (market.market_metadata or {}).get("snippet_v2")
            if existing and isinstance(existing, dict):
                computed_at = existing.get("computed_at", "")
                if computed_at:
                    try:
                        age = (now - datetime.fromisoformat(computed_at)).total_seconds()
                        if age < 7200:
                            stats["skipped_fresh"] += 1
                            continue
                    except (ValueError, TypeError):
                        pass

            stats["processed"] += 1

            # Load leader outcome
            outcome_result = await session.execute(
                select(FuturesOutcome)
                .where(FuturesOutcome.market_id == market.id)
                .order_by(FuturesOutcome.rank.asc().nullslast())
                .limit(1)
            )
            leader = outcome_result.scalar_one_or_none()

            ctx = MarketContext(
                name=market.name or "",
                probability=leader.current_probability if leader else None,
                opening_probability=leader.opening_probability if leader else None,
                movement_24h=leader.probability_change_24h if leader else None,
                outcome_name=leader.name if leader else None,
                resolution_date=market.resolution_date,
                volume_24h=market.volume_24h,
                now=now,
            )

            angle = select_angle(ctx)

            phrased_text = None
            if angle:
                phrased_text = await _llm_rephrase_snippet(
                    market.name or "", angle.template, angle.angle_type
                )

            snippet_v2 = {
                "angle_type": angle.angle_type if angle else None,
                "snippet_raw": angle.template if angle else None,
                "snippet_text": phrased_text or (angle.template if angle else None),
                "computed_at": now.isoformat(),
            }

            try:
                next_metadata = dict(market.market_metadata or {})
                next_metadata["snippet_v2"] = snippet_v2
                await session.execute(
                    update(FuturesMarket)
                    .where(FuturesMarket.id == market.id)
                    .values(market_metadata=next_metadata)
                )
                if angle:
                    stats["angles_found"] += 1
            except Exception as exc:
                logger.warning("Snippet angle failed for market %s: %s", market.id, exc)
                stats["errors"] += 1
                try:
                    await session.rollback()
                except Exception:
                    pass

        await session.commit()

    logger.info("Snippet angles: %s", stats)
    return stats
