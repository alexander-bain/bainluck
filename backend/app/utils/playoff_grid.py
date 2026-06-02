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


def enforce_monotonicity(teams: list[dict], columns: list) -> int:
    """Enforce monotonicity across sequential grid columns for every team.

    For sequential columns ordered earliest-to-latest (e.g., Make Playoffs ->
    Division -> Conference -> Championship), later stages must have probability
    <= earlier stages.  If Conference > Division, cap Conference at Division.

    This function is idempotent and should be called:
      1. During initial cell building (per-team, before normalization)
      2. After normalize_column_sums (which can inflate columns and break
         monotonicity that was previously enforced)

    Returns the number of violations corrected.
    """
    seq_cols = [c for c in columns if (c.sequential if hasattr(c, "sequential") else True)]
    seq_keys = [c.key if hasattr(c, "key") else c for c in sorted(
        seq_cols, key=lambda c: c.order if hasattr(c, "order") else 0
    )]

    if len(seq_keys) < 2:
        return 0

    violations_fixed = 0
    for team in teams:
        cells = team.get("cells", {})
        for i in range(1, len(seq_keys)):
            prev_key = seq_keys[i - 1]
            curr_key = seq_keys[i]
            prev_cell = cells.get(prev_key)
            curr_cell = cells.get(curr_key)
            if prev_cell and curr_cell:
                prev_p = prev_cell["merged_probability"]
                curr_p = curr_cell["merged_probability"]
                if curr_p > prev_p:
                    curr_cell["merged_probability"] = prev_p
                    # Also cap individual source probabilities
                    for src in curr_cell.get("sources", []):
                        if src["probability"] > prev_p:
                            src["probability"] = round(prev_p, 4)
                    violations_fixed += 1
                    logger.debug(
                        "Monotonicity fix: %s %s %.4f > %s %.4f -> capped to %.4f",
                        team.get("name", "?"), curr_key, curr_p,
                        prev_key, prev_p, prev_p,
                    )
    return violations_fixed


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
                "Column %s sum=%.1f%% exceeds 2.5x expected %.0f%% for %s — likely a matching bug",
                col_key, col_sum * 100, expected * 100, league_slug,
            )
        elif col_sum > expected * 1.05:
            # Moderate overshoot (5-150%) — typically from prediction market
            # minimum tick sizes (0.5-1% floor on long-shot teams). Safe to
            # normalize down proportionally.
            scale = expected / col_sum
            logger.info(
                "Normalizing %s column from %.1f%% to %.0f%% (x%.2f) for %s (overshoot)",
                col_key, col_sum * 100, expected * 100, scale, league_slug,
            )
            for t in teams:
                cell = t["cells"].get(col_key)
                if cell and cell.get("merged_probability") is not None:
                    cell["merged_probability"] = round(cell["merged_probability"] * scale, 4)
                    for src in cell.get("sources", []):
                        src["probability"] = round(src["probability"] * scale, 4)
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

        # After any normalization, cap individual cells at 100%.
        # Column-sum normalization can push a dominant team above 1.0 when
        # scaling up from an undershoot (e.g., OKC at 69% conference win
        # scaled by 1.5x → 103%). Cap merged_probability and source
        # probabilities to prevent impossible >100% display values.
        for t in teams:
            cell = t["cells"].get(col_key)
            if cell and cell.get("merged_probability") is not None:
                if cell["merged_probability"] > 1.0:
                    cell["merged_probability"] = 1.0
                for src in cell.get("sources", []):
                    if src["probability"] > 1.0:
                        src["probability"] = 1.0


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
