"""Pure logic for championship grid building.

Extracted from routes/playoffs.py `get_playoff_grid` (862 lines)
to make grid logic independently testable.
"""

import logging
import re

logger = logging.getLogger(__name__)

EXPECTED_COLUMN_SUMS = {
    "championship": 1.0,
    "conference": 2.0,
    "pennant": 2.0,
}


def normalize_column_sums(
    teams: list[dict],
    columns: list,
    league_slug: str,
) -> None:
    """Normalize championship/conference column probabilities to expected sums.

    When raw probabilities undershoot by >15% (common with prediction market
    data where long-tail teams floor at 0.1%), scales all values proportionally.

    Modifies teams in-place.
    """
    for col in columns:
        col_key = col.key if hasattr(col, "key") else col.get("key", "")
        expected = EXPECTED_COLUMN_SUMS.get(col_key)
        if not expected:
            continue
        col_sum = sum(
            t["cells"].get(col_key, {}).get("merged_probability", 0)
            for t in teams
        )
        if col_sum > expected * 2.5:
            logger.warning(
                "Column %s sum=%.1f%% exceeds 2.5x expected %.0f%% for %s",
                col_key, col_sum * 100, expected * 100, league_slug,
            )
        elif 0 < col_sum < expected * 0.85:
            scale = expected / col_sum
            logger.info(
                "Normalizing %s column from %.1f%% to %.0f%% (x%.2f) for %s",
                col_key, col_sum * 100, expected * 100, scale, league_slug,
            )
            for t in teams:
                cell = t["cells"].get(col_key)
                if cell and cell.get("merged_probability") is not None:
                    cell["merged_probability"] = round(cell["merged_probability"] * scale, 4)
                    for src in cell.get("sources", []):
                        src["probability"] = round(src["probability"] * scale, 4)


def compute_movers(
    teams: list[dict],
    championship_col: str,
    limit: int = 10,
) -> list[dict]:
    """Compute biggest 24h movers in the championship column.

    Returns list of mover dicts sorted by absolute change, descending.
    """
    movers = []
    for team_row in teams:
        champ_cell = team_row["cells"].get(championship_col)
        if champ_cell and champ_cell.get("trend_24h") is not None:
            movers.append({
                "name": team_row["name"],
                "short_name": team_row["short_name"],
                "team_id": team_row["team_id"],
                "column": championship_col,
                "change_24h": champ_cell["trend_24h"],
                "direction": "up" if champ_cell["trend_24h"] > 0 else "down",
                "logo_url": team_row.get("logo_url"),
                "primary_color": team_row.get("primary_color"),
            })

    movers.sort(key=lambda m: abs(m["change_24h"]), reverse=True)
    return movers[:limit]


def sort_teams_by_championship(
    teams: list[dict],
    championship_col: str,
    max_teams: int,
) -> list[dict]:
    """Sort teams by championship probability (descending) and cap to max."""
    teams.sort(
        key=lambda t: -(t["cells"].get(championship_col, {}).get("merged_probability", 0))
    )
    return teams[:max_teams]


# Regex for outcomes that are NOT team names (thresholds, dates, generic text)
_NON_TEAM_OUTCOME_RE = re.compile(
    r"""
    ^\d                |   # Starts with digit: "#1 seed", "1+ wins"
    \bover\b           |   # Over/Under
    \bunder\b          |
    \byes\b            |
    \bno\b             |
    \btotal\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_valid_grid_outcome(
    outcome_name: str,
    probability: float,
    source: str,
    has_real_bid: bool,
    sport_category: str | None = None,
    country_names: set[str] | None = None,
) -> bool:
    """Check if an outcome should be included in the grid.

    Filters out: non-team names, generic yes/no, matchup pairs,
    country names in club competitions, and prediction market noise.
    """
    name = outcome_name.strip()

    if not name:
        return False
    if probability <= 0 or probability >= 1.0:
        return False
    if name.lower() in ("yes", "no", "over", "under"):
        return False
    if re.match(r"^#?\d+", name):
        return False

    # Matchup pairs like "Tampa Bay and Colorado"
    if re.search(r"\band\b", name, re.IGNORECASE):
        if not re.search(r"\bTrail\s+Blazers\b", name, re.IGNORECASE):
            if re.match(r"^[\w\s.]+ and [\w\s.]+$", name):
                return False

    # Country names in club competitions
    if sport_category == "soccer" and country_names and name in country_names:
        return False

    # Prediction market noise (near-50% with no real bid activity)
    if source in ("kalshi", "polymarket") and abs(probability - 0.5) < 0.02:
        if not has_real_bid:
            return False

    return True
