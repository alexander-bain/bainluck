"""
LLM-based auditing of matching quality across the system.

Three audit functions that sample records, ask GPT-4o-mini to verify
correctness, and store structured findings for admin review.

Audit 1: Canonical key dedup (false positive/negative detection)
Audit 2: Prediction market → event linking (false/missing links)
Audit 3: Related futures coverage (missing team associations)
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

from app.models import (
    Event,
    FuturesMarket,
    FuturesOutcome,
    LineMovementAnalysis,
)
from app.services import llm
from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)


# =========================================================================
# Audit 1: Canonical Key Dedup
# =========================================================================

async def _audit_canonical_keys_impl(limit: int = 50) -> dict:
    """Sample canonical key groups and verify with LLM."""
    if not llm.is_available():
        return {"status": "skipped", "reason": "LLM not available"}

    findings = []
    sampled = 0

    async with get_task_session() as session:
        # Phase 1: Verify existing groups (false positive detection)
        # Find canonical keys with multiple markets grouped together
        group_query = (
            select(
                FuturesMarket.canonical_market_key,
                func.count(FuturesMarket.id).label("cnt"),
            )
            .where(
                FuturesMarket.canonical_market_key.isnot(None),
                FuturesMarket.status != "resolved",
            )
            .group_by(FuturesMarket.canonical_market_key)
            .having(func.count(FuturesMarket.id) > 1)
            .order_by(func.random())
            .limit(limit)
        )
        group_result = await session.execute(group_query)
        groups = group_result.all()

        for row in groups:
            canonical_key = row.canonical_market_key
            sampled += 1

            # Get markets in this group
            markets_result = await session.execute(
                select(FuturesMarket)
                .options(selectinload(FuturesMarket.outcomes))
                .where(FuturesMarket.canonical_market_key == canonical_key)
                .limit(10)
            )
            markets = markets_result.scalars().all()

            if len(markets) < 2:
                continue

            # Build prompt for LLM
            market_descriptions = []
            market_ids = []
            market_names = []
            for m in markets:
                top_outcomes = sorted(
                    m.outcomes,
                    key=lambda o: float(o.current_probability or 0),
                    reverse=True,
                )[:5]
                outcome_names = [o.name for o in top_outcomes]
                market_descriptions.append(
                    f"  - ID {m.id}: \"{m.name}\" (source: {m.source}, "
                    f"category: {m.llm_sport_category or m.category}, "
                    f"tier: {m.market_tier})\n"
                    f"    Top outcomes: {', '.join(outcome_names) if outcome_names else 'none'}"
                )
                market_ids.append(m.id)
                market_names.append(m.name)

            prompt = (
                "You are auditing a prediction market aggregator's deduplication system.\n"
                f"These markets share the canonical key \"{canonical_key}\":\n\n"
                + "\n".join(market_descriptions) + "\n\n"
                "Are these genuinely the same market (same sport, league, category, season)?\n"
                "Answer JSON: {\"same_market\": true/false, \"confidence\": 0.0-1.0, "
                "\"reason\": \"...\", \"pattern_category\": \"short_id_for_recurring_issue_or_null\", "
                "\"suggested_rule\": \"deterministic rule to prevent this, or null\"}"
            )

            result = llm.audit_match(prompt)
            if not result:
                continue

            if not result.get("same_market", True):
                findings.append({
                    "type": "false_positive",
                    "pattern_category": result.get("pattern_category"),
                    "canonical_key": canonical_key,
                    "market_ids": market_ids,
                    "market_names": market_names,
                    "confidence": result.get("confidence", 0),
                    "reason": result.get("reason", ""),
                    "suggested_rule": result.get("suggested_rule"),
                    "suggested_action": f"review_canonical_key_{canonical_key}",
                })

        # Phase 2: Find missing keys (false negative detection)
        # Sample markets without canonical keys that might need one
        unkeyed_result = await session.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.canonical_market_key.is_(None),
                FuturesMarket.status != "resolved",
                FuturesMarket.llm_sport_category.isnot(None),
                FuturesMarket.llm_sport_category != "other",
            )
            .order_by(func.random())
            .limit(limit)
        )
        unkeyed_markets = unkeyed_result.scalars().all()

        # Get existing canonical keys for comparison
        existing_keys_result = await session.execute(
            select(
                FuturesMarket.canonical_market_key,
                FuturesMarket.name,
            )
            .where(FuturesMarket.canonical_market_key.isnot(None))
            .distinct(FuturesMarket.canonical_market_key)
            .limit(200)
        )
        existing_keys = {
            row.canonical_market_key: row.name
            for row in existing_keys_result.all()
        }

        for market in unkeyed_markets:
            sampled += 1
            category = market.llm_sport_category or market.category

            # Find relevant existing keys for this category
            relevant_keys = {
                k: v for k, v in existing_keys.items()
                if category in k
            }

            if not relevant_keys:
                continue

            top_outcomes = sorted(
                market.outcomes,
                key=lambda o: float(o.current_probability or 0),
                reverse=True,
            )[:5]
            outcome_names = [o.name for o in top_outcomes]

            key_list = "\n".join(
                f"  - \"{k}\" (sample: \"{v}\")"
                for k, v in list(relevant_keys.items())[:20]
            )

            prompt = (
                "This market has no canonical key:\n"
                f"  Name: \"{market.name}\", Source: {market.source}, "
                f"Category: {category}\n"
                f"  Top outcomes: {', '.join(outcome_names) if outcome_names else 'none'}\n\n"
                f"Here are existing canonical keys for category \"{category}\":\n"
                f"{key_list}\n\n"
                "Does this market match any existing key, or should it get a new one?\n"
                "Answer JSON: {\"matches_key\": \"existing_key_or_null\", "
                "\"suggested_key\": \"new_key_if_no_match\", \"confidence\": 0.0-1.0, "
                "\"reason\": \"...\", \"pattern_category\": \"short_id_or_null\", "
                "\"suggested_rule\": \"rule_or_null\"}"
            )

            result = llm.audit_match(prompt)
            if not result:
                continue

            matched_key = result.get("matches_key")
            if matched_key and matched_key != "null" and result.get("confidence", 0) >= 0.7:
                findings.append({
                    "type": "false_negative",
                    "pattern_category": result.get("pattern_category"),
                    "market_id": market.id,
                    "market_name": market.name,
                    "suggested_key": matched_key,
                    "confidence": result.get("confidence", 0),
                    "reason": result.get("reason", ""),
                    "suggested_rule": result.get("suggested_rule"),
                    "suggested_action": f"set_canonical_key_{market.id}",
                })

        # Store results
        audit_row = LineMovementAnalysis(
            event_id=None,
            analysis_type="audit_canonical",
            movement_data={
                "audit_type": "canonical_key",
                "run_at": datetime.now(timezone.utc).isoformat(),
                "sampled": sampled,
                "issues_found": len(findings),
                "findings": findings,
            },
            explanation=f"Canonical key audit: {sampled} sampled, {len(findings)} issues found",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        session.add(audit_row)

    return {
        "status": "success",
        "sampled": sampled,
        "issues_found": len(findings),
        "findings": findings[:20],  # Limit response size
    }


# =========================================================================
# Audit 2: Prediction Market → Event Matching
# =========================================================================

async def _audit_prediction_market_links_impl(limit: int = 50) -> dict:
    """Sample linked prediction markets and verify with LLM."""
    if not llm.is_available():
        return {"status": "skipped", "reason": "LLM not available"}

    findings = []
    sampled = 0

    async with get_task_session() as session:
        # Phase 1: Verify existing links (false link detection)
        linked_result = await session.execute(
            select(FuturesMarket, Event)
            .join(Event, FuturesMarket.event_id == Event.id)
            .where(FuturesMarket.event_id.isnot(None))
            .order_by(func.random())
            .limit(limit)
        )
        linked_rows = linked_result.all()

        for fm, event in linked_rows:
            sampled += 1

            prompt = (
                "A prediction market has been linked to a sports event. Verify the link.\n\n"
                f"Market: \"{fm.name}\" (source: {fm.source}, ticker: {fm.external_id[:60]})\n"
                f"Linked event: {event.away_team_name} at {event.home_team_name}, "
                f"{event.commence_time.isoformat() if event.commence_time else 'unknown'}, "
                f"sport: {event.sport_id}\n\n"
                "Is this market about this specific game?\n"
                "Answer JSON: {\"correct_link\": true/false, \"confidence\": 0.0-1.0, "
                "\"reason\": \"...\", \"pattern_category\": \"short_id_or_null\", "
                "\"suggested_rule\": \"rule_or_null\"}"
            )

            result = llm.audit_match(prompt)
            if not result:
                continue

            if not result.get("correct_link", True):
                findings.append({
                    "type": "false_link",
                    "pattern_category": result.get("pattern_category"),
                    "market_id": fm.id,
                    "market_name": fm.name,
                    "market_source": fm.source,
                    "event_id": event.id,
                    "event_teams": f"{event.away_team_name} at {event.home_team_name}",
                    "confidence": result.get("confidence", 0),
                    "reason": result.get("reason", ""),
                    "suggested_rule": result.get("suggested_rule"),
                    "suggested_action": f"unlink_market_{fm.id}",
                })

        # Phase 2: Find unlinked game-level markets (missing link detection)
        unlinked_result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.event_id.is_(None),
                FuturesMarket.status != "resolved",
                (
                    FuturesMarket.name.ilike("%vs%")
                    | FuturesMarket.name.ilike("%at %")
                    | FuturesMarket.external_id.like("KX%GAME%")
                    | FuturesMarket.external_id.like("KX%FIGHT%")
                ),
            )
            .order_by(func.random())
            .limit(limit)
        )
        unlinked_markets = unlinked_result.scalars().all()

        for fm in unlinked_markets:
            sampled += 1

            prompt = (
                "This prediction market is NOT linked to any event:\n"
                f"  Name: \"{fm.name}\", Source: {fm.source}, "
                f"Ticker: {fm.external_id[:60]}\n\n"
                "Is this a game-level market (about a specific matchup, "
                "not a season-long future)?\n"
                "If yes, which two teams are playing?\n"
                "Answer JSON: {\"is_game_level\": true/false, "
                "\"team_a\": \"name_or_null\", \"team_b\": \"name_or_null\", "
                "\"confidence\": 0.0-1.0, \"pattern_category\": \"short_id_or_null\", "
                "\"suggested_rule\": \"rule_or_null\"}"
            )

            result = llm.audit_match(prompt)
            if not result:
                continue

            if result.get("is_game_level") and result.get("confidence", 0) >= 0.7:
                findings.append({
                    "type": "missing_link",
                    "pattern_category": result.get("pattern_category"),
                    "market_id": fm.id,
                    "market_name": fm.name,
                    "market_source": fm.source,
                    "suggested_team_a": result.get("team_a"),
                    "suggested_team_b": result.get("team_b"),
                    "confidence": result.get("confidence", 0),
                    "reason": result.get("reason", ""),
                    "suggested_rule": result.get("suggested_rule"),
                    "suggested_action": f"link_market_{fm.id}",
                })

        # Store results
        audit_row = LineMovementAnalysis(
            event_id=None,
            analysis_type="audit_pred_market",
            movement_data={
                "audit_type": "prediction_market_link",
                "run_at": datetime.now(timezone.utc).isoformat(),
                "sampled": sampled,
                "issues_found": len(findings),
                "findings": findings,
            },
            explanation=f"Prediction market link audit: {sampled} sampled, {len(findings)} issues found",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        session.add(audit_row)

    return {
        "status": "success",
        "sampled": sampled,
        "issues_found": len(findings),
        "findings": findings[:20],
    }


# =========================================================================
# Audit 3: Related Futures (Event → Futures)
# =========================================================================

# Tier 1 sports that should have championship futures
_MAJOR_SPORT_PREFIXES = {
    "basketball_nba", "americanfootball_nfl", "baseball_mlb",
    "icehockey_nhl", "soccer_epl", "soccer_spain_la_liga",
    "soccer_uefa_champs_league",
}


async def _audit_related_futures_impl(limit: int = 30) -> dict:
    """Sample events and verify their related futures coverage."""
    if not llm.is_available():
        return {"status": "skipped", "reason": "LLM not available"}

    findings = []
    sampled = 0

    async with get_task_session() as session:
        # Phase 1: Coverage check — do major-sport events have championship futures?
        from app.models import Sport

        events_result = await session.execute(
            select(Event)
            .join(Sport, Event.sport_id == Sport.id)
            .where(
                Event.status.in_(["scheduled", "live"]),
                Event.commence_time > datetime.now(timezone.utc) - timedelta(days=1),
            )
            .order_by(func.random())
            .limit(limit)
        )
        events = events_result.scalars().all()

        for event in events:
            sampled += 1

            # Look up sport key
            sport_result = await session.execute(
                select(Sport.key).where(Sport.id == event.sport_id)
            )
            sport_key = sport_result.scalar_one_or_none() or ""

            # Check if this is a major sport
            is_major = any(sport_key.startswith(p) for p in _MAJOR_SPORT_PREFIXES)
            if not is_major:
                continue

            # Count championship futures for each team
            home_count = 0
            away_count = 0

            for team_name, label in [
                (event.home_team_name, "home"),
                (event.away_team_name, "away"),
            ]:
                if not team_name:
                    continue
                # Simple ILIKE search for team name in championship outcomes
                count_result = await session.execute(
                    select(func.count(FuturesOutcome.id))
                    .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
                    .where(
                        FuturesMarket.market_tier == 1,
                        FuturesMarket.status != "resolved",
                        FuturesOutcome.name.ilike(f"%{team_name}%"),
                    )
                )
                count = count_result.scalar() or 0
                if label == "home":
                    home_count = count
                else:
                    away_count = count

            # Flag if a major-sport team has zero championship futures
            if home_count == 0 or away_count == 0:
                prompt = (
                    f"A {sport_key} game between {event.home_team_name} and "
                    f"{event.away_team_name} has been checked for related "
                    f"championship futures.\n\n"
                    f"{event.home_team_name}: {home_count} championship futures found\n"
                    f"{event.away_team_name}: {away_count} championship futures found\n\n"
                    f"For a {sport_key} team, is it expected to have championship futures?\n"
                    f"If a team has 0, is this likely a data gap or expected "
                    f"(e.g., minor league, exhibition team)?\n"
                    "Answer JSON: {\"home_coverage_ok\": true/false, "
                    "\"away_coverage_ok\": true/false, \"reason\": \"...\", "
                    "\"pattern_category\": \"short_id_or_null\", "
                    "\"suggested_rule\": \"rule_or_null\"}"
                )

                result = llm.audit_match(prompt)
                if not result:
                    continue

                if not result.get("home_coverage_ok", True) or not result.get("away_coverage_ok", True):
                    findings.append({
                        "type": "missing_championship_futures",
                        "pattern_category": result.get("pattern_category"),
                        "event_id": event.id,
                        "home_team": event.home_team_name,
                        "away_team": event.away_team_name,
                        "sport_key": sport_key,
                        "home_championship_count": home_count,
                        "away_championship_count": away_count,
                        "confidence": 1.0,  # This is a data check, not subjective
                        "reason": result.get("reason", ""),
                        "suggested_rule": result.get("suggested_rule"),
                        "suggested_action": "run_backfill_team_links",
                    })

        # Phase 2: team_id coverage on high-probability outcomes
        unlinked_result = await session.execute(
            select(FuturesOutcome, FuturesMarket.name.label("market_name"),
                   FuturesMarket.llm_sport_category)
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .where(
                FuturesOutcome.team_id.is_(None),
                FuturesOutcome.current_probability > 0.01,
                FuturesMarket.llm_sport_category.in_(
                    ["basketball", "football", "baseball", "hockey", "soccer"]
                ),
                FuturesMarket.market_tier.in_([1, 2]),
                FuturesMarket.status != "resolved",
            )
            .order_by(FuturesOutcome.current_probability.desc())
            .limit(limit)
        )
        unlinked_outcomes = unlinked_result.all()

        for outcome, market_name, sport_cat in unlinked_outcomes:
            sampled += 1

            prompt = (
                f"This futures outcome has no team_id link:\n"
                f"  Outcome: \"{outcome.name}\"\n"
                f"  Market: \"{market_name}\"\n"
                f"  Sport category: {sport_cat}\n\n"
                "What team is this outcome for? Is this a recognizable team name?\n"
                "Answer JSON: {\"team_name\": \"full_team_name_or_null\", "
                "\"confidence\": 0.0-1.0, \"reason\": \"...\", "
                "\"pattern_category\": \"short_id_or_null\", "
                "\"suggested_rule\": \"rule_or_null\"}"
            )

            result = llm.audit_match(prompt)
            if not result:
                continue

            team_name = result.get("team_name")
            if team_name and team_name != "null" and result.get("confidence", 0) >= 0.8:
                findings.append({
                    "type": "missing_team_id",
                    "pattern_category": result.get("pattern_category"),
                    "outcome_id": outcome.id,
                    "outcome_name": outcome.name,
                    "market_name": market_name,
                    "suggested_team_name": team_name,
                    "confidence": result.get("confidence", 0),
                    "reason": result.get("reason", ""),
                    "suggested_rule": result.get("suggested_rule"),
                    "suggested_action": f"link_team_{outcome.id}",
                })

        # Store results
        audit_row = LineMovementAnalysis(
            event_id=None,
            analysis_type="audit_related_fut",
            movement_data={
                "audit_type": "related_futures",
                "run_at": datetime.now(timezone.utc).isoformat(),
                "sampled": sampled,
                "issues_found": len(findings),
                "findings": findings,
            },
            explanation=f"Related futures audit: {sampled} sampled, {len(findings)} issues found",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        session.add(audit_row)

    return {
        "status": "success",
        "sampled": sampled,
        "issues_found": len(findings),
        "findings": findings[:20],
    }


# =========================================================================
# Pattern aggregation — recurring issues across audit runs
# =========================================================================

async def _get_audit_patterns_impl(days: int = 30) -> dict:
    """Aggregate pattern_category across recent audit findings."""
    async with get_task_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = await session.execute(
            select(LineMovementAnalysis)
            .where(
                LineMovementAnalysis.analysis_type.in_([
                    "audit_canonical", "audit_pred_market", "audit_related_fut",
                ]),
                LineMovementAnalysis.created_at >= cutoff,
            )
            .order_by(LineMovementAnalysis.created_at.desc())
        )
        audit_rows = result.scalars().all()

        # Aggregate patterns
        pattern_counts: dict[str, dict] = {}
        for row in audit_rows:
            data = row.movement_data or {}
            for finding in data.get("findings", []):
                cat = finding.get("pattern_category")
                if not cat or cat == "null":
                    continue
                if cat not in pattern_counts:
                    pattern_counts[cat] = {
                        "category": cat,
                        "count": 0,
                        "latest_suggestion": None,
                        "audit_types": set(),
                        "finding_types": set(),
                    }
                pattern_counts[cat]["count"] += 1
                rule = finding.get("suggested_rule")
                if rule and rule != "null":
                    pattern_counts[cat]["latest_suggestion"] = rule
                pattern_counts[cat]["audit_types"].add(data.get("audit_type", ""))
                pattern_counts[cat]["finding_types"].add(finding.get("type", ""))

        # Convert sets to lists for JSON serialization and sort by count
        patterns = sorted(pattern_counts.values(), key=lambda p: p["count"], reverse=True)
        for p in patterns:
            p["audit_types"] = sorted(p["audit_types"])
            p["finding_types"] = sorted(p["finding_types"])

        return {
            "days": days,
            "total_audit_runs": len(audit_rows),
            "unique_patterns": len(patterns),
            "patterns": patterns[:50],
        }


# =========================================================================
# Matching Eval Metrics (Coverage + Accuracy tracked over time)
# =========================================================================

MATCHING_METRICS_PREFIX = "bainluck:matching_metrics"

# Major sports that should ALWAYS have good coverage
_MAJOR_SPORTS = {
    "americanfootball_nfl", "basketball_nba", "baseball_mlb", "icehockey_nhl",
    "basketball_ncaab", "soccer_epl", "soccer_usa_mls",
}


async def _compute_matching_metrics_impl() -> dict:
    """Compute coverage and accuracy metrics for prediction market matching.

    Metrics:
    - coverage_pct: % of active events with at least one prediction market match
    - major_coverage_pct: coverage for major sports only (should be near 100%)
    - kalshi_coverage: % with Kalshi match
    - polymarket_coverage: % with Polymarket match
    - by_sport: per-sport coverage breakdown
    - total_events: total active events
    - matched_events: events with prediction market match
    """
    from sqlalchemy import text

    async with get_task_session() as session:
        # All active events with prediction market coverage via futures_markets join
        result = await session.execute(text("""
            SELECT
                s.key AS sport_key,
                COUNT(DISTINCT e.id) AS total,
                COUNT(DISTINCT CASE WHEN fm.id IS NOT NULL THEN e.id END) AS matched,
                COUNT(DISTINCT CASE WHEN fm.source = 'kalshi' THEN e.id END) AS kalshi_matched,
                COUNT(DISTINCT CASE WHEN fm.source = 'polymarket' THEN e.id END) AS poly_matched
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            LEFT JOIN futures_markets fm ON fm.event_id = e.id
                AND fm.source IN ('kalshi', 'polymarket')
            WHERE e.status IN ('scheduled', 'live')
              AND e.commence_time >= NOW() - INTERVAL '6 hours'
            GROUP BY s.key
            ORDER BY COUNT(DISTINCT e.id) DESC
        """))
        rows = result.fetchall()

        total = sum(r.total for r in rows)
        matched = sum(r.matched for r in rows)
        kalshi = sum(r.kalshi_matched for r in rows)
        poly = sum(r.poly_matched for r in rows)

        # Major sports breakdown — only count sports where PM markets exist
        # (sports with 0 matches have no PM coverage, making 100% impossible)
        major_total = sum(r.total for r in rows if r.sport_key in _MAJOR_SPORTS)
        major_matched = sum(r.matched for r in rows if r.sport_key in _MAJOR_SPORTS)
        major_matchable = sum(
            r.total for r in rows
            if r.sport_key in _MAJOR_SPORTS and (r.kalshi_matched > 0 or r.poly_matched > 0)
        )

        by_sport = []
        for r in rows:
            has_pm_coverage = r.kalshi_matched > 0 or r.poly_matched > 0
            by_sport.append({
                "sport": r.sport_key,
                "total": r.total,
                "matched": r.matched,
                "coverage_pct": round(r.matched / max(r.total, 1) * 100, 1),
                "kalshi": r.kalshi_matched,
                "polymarket": r.poly_matched,
                "is_major": r.sport_key in _MAJOR_SPORTS,
                "has_pm_coverage": has_pm_coverage,
            })

        # Unmatched major sport events (the ones we should NEVER miss)
        unmatched_major = await session.execute(text("""
            SELECT e.id, s.key AS sport_key, e.home_team_name, e.away_team_name,
                   e.commence_time, e.status
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            LEFT JOIN futures_markets fm ON fm.event_id = e.id
                AND fm.source IN ('kalshi', 'polymarket')
            WHERE e.status IN ('scheduled', 'live')
              AND e.commence_time >= NOW() - INTERVAL '6 hours'
              AND e.commence_time <= NOW() + INTERVAL '24 hours'
              AND fm.id IS NULL
              AND s.key = ANY(:sports)
            GROUP BY e.id, s.key, e.home_team_name, e.away_team_name, e.commence_time, e.status
            ORDER BY e.commence_time
            LIMIT 20
        """), {"sports": list(_MAJOR_SPORTS)})
        gaps = [
            {
                "id": r.id,
                "sport": r.sport_key,
                "matchup": f"{r.away_team_name} @ {r.home_team_name}",
                "time": r.commence_time.isoformat() if r.commence_time else None,
                "status": r.status,
            }
            for r in unmatched_major.fetchall()
        ]

        metrics = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "coverage_pct": round(matched / max(total, 1) * 100, 1),
            "major_coverage_pct": round(major_matched / max(major_total, 1) * 100, 1),
            "kalshi_coverage_pct": round(kalshi / max(total, 1) * 100, 1),
            "polymarket_coverage_pct": round(poly / max(total, 1) * 100, 1),
            "total_events": total,
            "matched_events": matched,
            "major_total": major_total,
            "major_matched": major_matched,
            "by_sport": by_sport,
            "unmatched_major_gaps": gaps,
        }

        # Store in Redis for trending
        _store_matching_metrics(metrics)

        return metrics


def _store_matching_metrics(metrics: dict):
    """Store daily matching metrics snapshot in Redis."""
    from app.tasks.redis_state import get_redis_client

    r = get_redis_client()
    if not r:
        return
    try:
        day_key = metrics["timestamp"][:10]
        redis_key = f"{MATCHING_METRICS_PREFIX}:{day_key}"
        r.set(redis_key, json.dumps({
            "date": day_key,
            "coverage_pct": metrics["coverage_pct"],
            "major_coverage_pct": metrics["major_coverage_pct"],
            "kalshi_coverage_pct": metrics["kalshi_coverage_pct"],
            "polymarket_coverage_pct": metrics["polymarket_coverage_pct"],
            "total_events": metrics["total_events"],
            "matched_events": metrics["matched_events"],
            "major_total": metrics["major_total"],
            "major_matched": metrics["major_matched"],
        }), ex=86400 * 90)
    except Exception:
        pass


def get_matching_metrics_history(days: int = 90) -> list:
    """Get daily matching metrics for trending."""
    from app.tasks.redis_state import get_redis_client

    r = get_redis_client()
    if not r:
        return []
    try:
        results = []
        now = datetime.now(timezone.utc)
        for i in range(days):
            day = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            key = f"{MATCHING_METRICS_PREFIX}:{day}"
            val = r.get(key)
            if val:
                results.append(json.loads(val))
        return results
    except Exception:
        return []
