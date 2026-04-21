"""Pure logic for related futures processing.

Extracted from routes/events.py `get_related_futures` (783 lines)
to make deduplication and filtering independently testable.
"""


# Merge groups that are per-team (one entry per source, not per outcome)
_PER_TEAM_MERGE_GROUPS = {
    "win_total", "make_playoffs", "make_nfl_playoffs",
    "make_nhl_playoffs", "make_mlb_playoffs",
}
_PER_TEAM_MERGE_SUFFIXES = ("_division", "_conf_champion", "_conf_1_seed", "_conf_playin")


def dedup_by_merge_group(futures: list[dict]) -> list[dict]:
    """Deduplicate futures entries by merge group.

    For per-team groups (win_total, make_playoffs, division winners),
    uses merge_group alone as the key. For multi-outcome groups
    (championship, matchups), uses (merge_group, outcome_name).

    Keeps the entry with highest bookmaker_count. Aggregates all sources
    into an `all_sources` list on the winner.
    """
    groups: dict[tuple, list[dict]] = {}
    ungrouped: list[dict] = []
    for f in futures:
        mg = f.get("merge_group")
        if mg:
            if mg in _PER_TEAM_MERGE_GROUPS or mg.endswith(_PER_TEAM_MERGE_SUFFIXES):
                key = (mg,)
            else:
                key = (mg, f["outcome_name"].lower())
            groups.setdefault(key, []).append(f)
        else:
            ungrouped.append(f)
    result = list(ungrouped)
    for entries in groups.values():
        if len(entries) == 1:
            result.append(entries[0])
        else:
            entries.sort(key=lambda x: x.get("bookmaker_count", 0), reverse=True)
            winner = entries[0]
            winner["all_sources"] = list({e["source"] for e in entries if e.get("source")})
            result.append(winner)
    return result


def build_futures_entry(
    market,
    outcome,
    relevance_score: float,
    relevance_reason: str,
    clean_label: str,
    display_category: str,
    merge_group: str | None,
    stage_display: str | None,
    stage_type: str | None,
    stage_order: int | None,
    bookmaker_count: int,
    next_update_iso: str,
    player_metadata: dict | None = None,
) -> dict:
    """Build a single futures entry dict for the response.

    Pure function — takes all data as arguments.
    """
    entry = {
        "market_id": market.id,
        "market_name": market.name,
        "clean_label": clean_label,
        "display_category": display_category,
        "merge_group": merge_group,
        "playoff_stage": stage_display,
        "playoff_stage_type": stage_type,
        "stage_order": stage_order,
        "market_tier": market.market_tier,
        "category": market.category,
        "source": market.source,
        "outcome_id": outcome.id,
        "outcome_name": outcome.name,
        "probability": float(outcome.current_probability) if outcome.current_probability else None,
        "american_odds": outcome.current_american_odds,
        "probability_change_24h": float(outcome.probability_change_24h) if outcome.probability_change_24h else None,
        "opening_probability": float(outcome.opening_probability) if outcome.opening_probability else None,
        "rank": outcome.rank,
        "relevance_score": relevance_score,
        "relevance_reason": relevance_reason,
        "last_updated": outcome.last_updated.isoformat() if outcome.last_updated else None,
        "next_update_expected": next_update_iso,
        "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
        "bookmaker_count": bookmaker_count,
    }

    if player_metadata:
        player_lookup = (outcome.name or "").split(":")[0].strip().lower()
        matched = player_metadata.get(player_lookup)
        if matched:
            entry["matched_player"] = matched

    return entry
