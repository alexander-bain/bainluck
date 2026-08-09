"""Pure logic for related futures processing.

Extracted from routes/events.py `get_related_futures` (783 lines)
to make deduplication and filtering independently testable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# How old a futures quote may be before it stops being a valid answer to
# "what are their chances?" during a live season (#1589).
#
# Season-long markets (make playoffs, win total, division) are polled on cycles
# measured in hours -- Kalshi every 2h, Polymarket hourly -- so a quote a full
# day old is not "slightly behind", it is a market nobody is maintaining.
STALE_AFTER_HOURS = 24


# Merge groups that are per-team (one entry per source, not per outcome)
_PER_TEAM_MERGE_GROUPS = {
    "win_total", "make_playoffs", "make_nfl_playoffs",
    "make_nhl_playoffs", "make_mlb_playoffs",
}
_PER_TEAM_MERGE_SUFFIXES = ("_division", "_conf_champion", "_conf_1_seed", "_conf_playin")


def dedup_by_merge_group(
    futures: list[dict],
    now: datetime | None = None,
    stale_after_hours: int = STALE_AFTER_HOURS,
) -> list[dict]:
    """Deduplicate futures entries by merge group.

    For per-team groups (win_total, make_playoffs, division winners),
    uses merge_group alone as the key. For multi-outcome groups
    (championship, matchups), uses (merge_group, outcome_name).

    Keeps the FRESHEST-ELIGIBLE entry with the highest bookmaker_count, and
    aggregates all sources into an `all_sources` list on the winner.

    #1589 -- why freshness gates this at all. The rule used to be "highest
    bookmaker_count wins", full stop. **Most liquid is not most correct when one
    of them is stale.** A season-long market carried by many bookmakers but no
    longer being updated outranked a fresher quote from fewer, so the page could
    publish a months-old number with total confidence: Alex saw the Red Sox at
    63% to make the playoffs when the real figure was ~90%.

    So stale entries are demoted, not deleted. If every entry in a group is
    stale we still return the best of them rather than dropping the row --
    blanking the "Bigger Picture" section would be a worse regression than a
    stale number, and it is the failure mode a naive filter would introduce
    (gotcha #43).

    `now` is injected so the staleness boundary is deterministically testable
    and never seeded off the wall clock (gotcha #44).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=stale_after_hours)

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
            # Fresh first, then liquidity. `is_stale` is a bool, so sorting on
            # (not stale, bookmaker_count) keeps the old preference intact
            # WITHIN each freshness tier and only ever promotes a fresh entry
            # over a stale one.
            entries.sort(
                key=lambda x: (
                    not _is_stale(x.get("last_updated"), cutoff),
                    x.get("bookmaker_count", 0),
                ),
                reverse=True,
            )
            winner = entries[0]
            winner["all_sources"] = list({e["source"] for e in entries if e.get("source")})
            result.append(winner)
    return result


def _is_stale(last_updated: str | None, cutoff: datetime) -> bool:
    """True when a quote is older than the cutoff, or carries no timestamp.

    A missing timestamp counts as stale: it is an entry that cannot show it is
    current, and the whole point here is to prefer one that can. It is only a
    demotion -- an all-stale group still returns its best entry.
    """
    if not last_updated:
        return True
    try:
        parsed = datetime.fromisoformat(str(last_updated).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed < cutoff


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
