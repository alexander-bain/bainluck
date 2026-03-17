"""League configurations for championship progression grids.

Each league defines grid columns, sport keys for market discovery,
team sorting strategy, conference/region grouping, and market matching
rules with source tiers.

Stage definitions (patterns for matching market names to columns) live
in `app/utils/tournament_stages.py` and are referenced by column key.
This file adds the grid-level configuration on top.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GridColumn:
    """A single column in the playoff grid."""

    key: str  # matches stage key in tournament_stages.py
    label: str
    order: int
    sequential: bool = True  # True = must survive prior round to reach this one


@dataclass(frozen=True)
class MarketMatchingRule:
    """Maps a grid column to market search patterns and source tier."""

    column: str  # GridColumn.key
    tier: int | None = None  # market_tier value (1=championship, 2=conference, etc.)
    name_patterns: list[str] = field(default_factory=list)  # regex patterns on market name
    canonical_prefix: str | None = None  # canonical_market_key prefix


@dataclass(frozen=True)
class LeagueConfig:
    """Full configuration for a league's playoff grid page."""

    slug: str  # URL slug: "nba", "nhl", "ncaa-basketball", "golf"
    name: str  # Display name: "NBA Playoffs 2025-26"
    sport_category: str  # llm_sport_category value: "basketball", "hockey", etc.
    sport_keys: list[str]  # Odds API sport key prefixes for market discovery
    stage_key: str  # Key into SPORT_STAGES in tournament_stages.py
    columns: list[GridColumn]
    matching_rules: list[MarketMatchingRule] = field(default_factory=list)
    # Regex patterns to identify this league's markets from non-sport-key sources
    # (Kalshi/Polymarket). At least one pattern must match the market name for
    # inclusion. Needed to separate NBA from NCAAB (both llm_sport_category="basketball").
    league_name_patterns: list[str] = field(default_factory=list)
    team_sort: str = "championship_desc"  # "championship_desc" | "name_asc" | "seed_asc"
    conference_split: bool = False  # Show teams grouped by conference?
    conference_field: str = "conference"  # Field on standings_data for grouping
    region_split: bool = False  # Show teams grouped by region (March Madness)?
    trend_hours: int = 168  # Default trend chart window (7 days)
    max_teams: int = 40  # Cap on teams shown in grid
    season_pattern: str = "2025-26"  # For filtering to current season markets


# ---------------------------------------------------------------------------
# League definitions
# ---------------------------------------------------------------------------

NBA_CONFIG = LeagueConfig(
    slug="nba",
    name="NBA Playoffs 2025-26",
    sport_category="basketball",
    sport_keys=["basketball_nba"],
    stage_key="basketball",
    league_name_patterns=[
        r"\bNBA\b",
        r"\bPro\s+Basketball\b",
    ],
    columns=[
        GridColumn(key="make_playoffs", label="Make Playoffs", order=1),
        GridColumn(key="conference", label="Conference", order=2),
        GridColumn(key="championship", label="Champion", order=3),
    ],
    matching_rules=[
        MarketMatchingRule(
            column="championship",
            tier=1,
            name_patterns=[
                r"NBA\s+Championship",
                r"NBA\s+Finals\s+Winner",
                r"NBA\s+Champion",
            ],
            canonical_prefix="basketball_nba_championship",
        ),
        MarketMatchingRule(
            column="conference",
            tier=2,
            name_patterns=[
                r"Eastern\s+Conference",
                r"Western\s+Conference",
                r"NBA.*Conference",
            ],
        ),
        MarketMatchingRule(
            column="make_playoffs",
            tier=4,
            name_patterns=[
                r"Make\s+Playoffs",
                r"Playoff\s+(?:Berth|Qualif)",
            ],
        ),
    ],
    team_sort="championship_desc",
    conference_split=True,
    conference_field="conference",
    trend_hours=168,
    max_teams=30,
)

NHL_CONFIG = LeagueConfig(
    slug="nhl",
    name="NHL Playoffs 2025-26",
    sport_category="hockey",
    sport_keys=["icehockey_nhl"],
    stage_key="hockey",
    league_name_patterns=[
        r"\bNHL\b",
        r"\bStanley\s+Cup\b",
        r"\bPro\s+Hockey\b",
    ],
    columns=[
        GridColumn(key="make_playoffs", label="Make Playoffs", order=1),
        GridColumn(key="division", label="Division", order=2),
        GridColumn(key="conference", label="Conference", order=3),
        GridColumn(key="championship", label="Stanley Cup", order=4),
    ],
    matching_rules=[
        MarketMatchingRule(
            column="championship",
            tier=1,
            name_patterns=[
                r"Stanley\s+Cup",
                r"NHL\s+Championship",
                r"NHL\s+Champion",
            ],
            canonical_prefix="icehockey_nhl_championship",
        ),
        MarketMatchingRule(
            column="conference",
            tier=2,
            name_patterns=[
                r"(?:Eastern|Western)\s+Conference",
                r"NHL.*Conference",
            ],
        ),
        MarketMatchingRule(
            column="division",
            tier=4,
            name_patterns=[
                r"\bDivision\b",
                r"(?:Atlantic|Metropolitan|Central|Pacific)\b",
            ],
        ),
        MarketMatchingRule(
            column="make_playoffs",
            name_patterns=[
                r"Make\s+Playoffs",
                r"Playoff\s+(?:Berth|Qualif)",
            ],
        ),
    ],
    team_sort="championship_desc",
    conference_split=True,
    conference_field="conference",
    trend_hours=168,
    max_teams=32,
)

NCAA_BASKETBALL_CONFIG = LeagueConfig(
    slug="ncaa-basketball",
    name="NCAA Tournament 2026",
    sport_category="basketball",
    sport_keys=["basketball_ncaab"],
    stage_key="ncaa_basketball",
    league_name_patterns=[
        r"\bNCAA\b",
        r"\bMarch\s+Madness\b",
        r"\bCollege\s+Basketball\b",
        r"\bNCAAB\b",
    ],
    columns=[
        GridColumn(key="round_of_32", label="R32", order=1),
        GridColumn(key="sweet_16", label="Sweet 16", order=2),
        GridColumn(key="elite_eight", label="Elite 8", order=3),
        GridColumn(key="final_four", label="Final Four", order=4),
        GridColumn(key="title_game", label="Title Game", order=5),
        GridColumn(key="championship", label="Champion", order=6),
    ],
    matching_rules=[
        MarketMatchingRule(
            column="championship",
            tier=1,
            name_patterns=[
                r"NCAAB\s+Championship\s+Winner",
                r"NCAAB\s+Championship(?!\s+Game)",  # "NCAAB Championship" but NOT "Championship Game"
                r"NCAA\s+Tournament\s+Winner",
                r"NCAA\s+Champion(?!\s*ship\s+Game)",  # "NCAA Champion" but NOT "Championship Game"
                r"March\s+Madness.*Winner",
                r"Win\s+(?:the\s+)?NCAA\s+Tournament",
            ],
            canonical_prefix="basketball_ncaab_championship",
        ),
        MarketMatchingRule(
            column="title_game",
            name_patterns=[
                r"National\s+Championship\s+Game",
                r"Championship\s+Game",
                r"Make.*Championship\s+Game",
                r"Make.*Championship(?!\s+Winner)",  # "Make Championship" but NOT "Make Championship Winner"
                r"Title\s+Game",
            ],
        ),
        MarketMatchingRule(
            column="final_four",
            name_patterns=[
                r"Final\s+Four",
                r"Make.*Final\s+Four",
                r"Semifinals",
            ],
        ),
        MarketMatchingRule(
            column="elite_eight",
            name_patterns=[
                r"Elite\s+Eight",
                r"Elite\s+8",
                r"Make.*Elite",
            ],
        ),
        MarketMatchingRule(
            column="sweet_16",
            name_patterns=[
                r"Sweet\s+(?:16|Sixteen)",
                r"Make.*Sweet",
            ],
        ),
        MarketMatchingRule(
            column="round_of_32",
            name_patterns=[
                r"Round\s+of\s+32",
                r"Second\s+Round",
                r"Win\s+First\s+Round",
            ],
        ),
    ],
    team_sort="championship_desc",
    conference_split=False,
    region_split=True,
    trend_hours=72,  # Tournament is ~3 weeks, show recent window
    max_teams=68,
    season_pattern="2026",
)

GOLF_CONFIG = LeagueConfig(
    slug="golf",
    name="PGA Tour",
    sport_category="golf",
    sport_keys=["golf_pga", "golf_masters", "golf_us_open", "golf_open", "golf_pga_championship"],
    stage_key="golf",
    league_name_patterns=[
        r"\bPGA\b",
        r"\bMasters\b",
        r"\bU\.?S\.?\s+Open\b",
        r"\bOpen\s+Championship\b",
        r"\bGolf\b",
    ],
    columns=[
        GridColumn(key="make_cut", label="Make Cut", order=1, sequential=False),
        GridColumn(key="top_20", label="Top 20", order=2, sequential=False),
        GridColumn(key="top_10", label="Top 10", order=3, sequential=False),
        GridColumn(key="top_5", label="Top 5", order=4, sequential=False),
        GridColumn(key="win", label="Win", order=5, sequential=False),
    ],
    matching_rules=[
        MarketMatchingRule(
            column="win",
            tier=1,
            name_patterns=[r"\bWinner\b", r"\bChampionship\b", r"\bWin\b"],
        ),
        MarketMatchingRule(
            column="top_5",
            name_patterns=[r"Top\s*5"],
        ),
        MarketMatchingRule(
            column="top_10",
            name_patterns=[r"Top\s*10"],
        ),
        MarketMatchingRule(
            column="top_20",
            name_patterns=[r"Top\s*20"],
        ),
        MarketMatchingRule(
            column="make_cut",
            name_patterns=[r"Make.*Cut", r"Cut"],
        ),
    ],
    team_sort="championship_desc",  # Sort golfers by win probability
    conference_split=False,
    trend_hours=168,
    max_teams=50,  # Top 50 golfers per tournament
    season_pattern="2026",
)


# ---------------------------------------------------------------------------
# Registry — slug → config lookup
# ---------------------------------------------------------------------------

LEAGUE_CONFIGS: dict[str, LeagueConfig] = {
    cfg.slug: cfg
    for cfg in [
        NBA_CONFIG,
        NHL_CONFIG,
        NCAA_BASKETBALL_CONFIG,
        GOLF_CONFIG,
    ]
}


def get_league_config(slug: str) -> LeagueConfig | None:
    """Look up a league config by URL slug."""
    return LEAGUE_CONFIGS.get(slug)


def get_all_league_slugs() -> list[str]:
    """Return all configured league slugs (for index page / navigation)."""
    return list(LEAGUE_CONFIGS.keys())
