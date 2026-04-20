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
    # Regex patterns to EXCLUDE markets even if they match league_name_patterns.
    # Used to separate MLB from college baseball (both match "World Series").
    league_exclude_patterns: list[str] = field(default_factory=list)
    # Kalshi ticker prefixes that belong to this league. Markets whose
    # external_id starts with any of these prefixes pass the league filter
    # even if their name doesn't match league_name_patterns.
    external_id_prefixes: list[str] = field(default_factory=list)
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
                r"Make\s+(?:the\s+)?(?:Playoffs|Postseason)",
                r"(?:Playoff|Postseason)\s+(?:Berth|Qualif)",
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
                r"Make\s+(?:the\s+)?(?:Playoffs|Postseason)",
                r"(?:Playoff|Postseason)\s+(?:Berth|Qualif)",
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
        r"\bMen.s\s+College\s+Basketball\b",
    ],
    # Kalshi ticker prefixes that belong to this league — used when market names
    # don't contain league keywords (e.g., "Men's Semifinals Qualifiers").
    external_id_prefixes=["KXMARMADROUND"],
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
                r"College\s+Basketball\s+Champion\b",  # Kalshi: "Men's College Basketball Champion"
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
                r"Quarter.?Finals?",
                r"Round\s+of\s+8\s+Qualif",   # Kalshi: "Men's Round of 8 Qualifiers"
            ],
        ),
        MarketMatchingRule(
            column="sweet_16",
            name_patterns=[
                r"Sweet\s+(?:16|Sixteen)",
                r"Make.*Sweet",
                r"Round\s+of\s+16\s+Qualif",  # Kalshi: "Men's Round of 16 Qualifiers"
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
    region_split=False,  # Flat list — easier to compare across regions
    trend_hours=72,  # Tournament is ~3 weeks, show recent window
    max_teams=68,
    season_pattern="2026",
)

WNCAA_BASKETBALL_CONFIG = LeagueConfig(
    slug="ncaa-women-basketball",
    name="Women's NCAA Tournament 2026",
    sport_category="basketball",
    sport_keys=["basketball_wncaab"],
    stage_key="ncaa_women_basketball",
    league_name_patterns=[
        r"\bWomen.s\s+College\s+Basketball\b",
        r"\bWomen.s\s+NCAA\b",
        r"\bWomen.s\s+March\s+Madness\b",
        r"\bWNCAA\b",
        r"\bWomen.s\s+(?:Championship|Semifinals|Round\s+of\s+8)\b",
    ],
    external_id_prefixes=["KXWMARMAD"],
    columns=[
        GridColumn(key="elite_eight", label="Elite 8", order=1),
        GridColumn(key="final_four", label="Final Four", order=2),
        GridColumn(key="title_game", label="Title Game", order=3),
        GridColumn(key="championship", label="Champion", order=4),
    ],
    matching_rules=[
        MarketMatchingRule(
            column="championship",
            tier=1,
            name_patterns=[
                r"Women.s\s+College\s+Basketball\s+Champion\b",
                r"Women.s\s+NCAA\s+(?:Tournament\s+)?(?:Winner|Champion)",
                r"Women.s\s+March\s+Madness.*(?:Winner|Champion)",
                r"WNCAAB\s+Championship",
            ],
            canonical_prefix="basketball_wncaab_championship",
        ),
        MarketMatchingRule(
            column="title_game",
            name_patterns=[
                r"Women.s\s+Championship\s+Game",
                r"Women.s\s+(?:National\s+)?Championship\s+Game\s+Qualif",
            ],
        ),
        MarketMatchingRule(
            column="final_four",
            name_patterns=[
                r"Women.s\s+(?:Final\s+Four|Semifinals)",
                r"Women.s\s+Semifinals\s+Qualif",
            ],
        ),
        MarketMatchingRule(
            column="elite_eight",
            name_patterns=[
                r"Women.s\s+(?:Elite\s+(?:Eight|8)|Quarter.?Finals?)",
                r"Women.s\s+Round\s+of\s+8\s+Qualif",
            ],
        ),
    ],
    team_sort="championship_desc",
    conference_split=False,
    region_split=False,
    trend_hours=72,
    max_teams=68,
    season_pattern="2026",
)

NFL_CONFIG = LeagueConfig(
    slug="nfl",
    name="NFL Playoffs 2025-26",
    sport_category="football",
    sport_keys=["americanfootball_nfl"],
    stage_key="football",
    league_name_patterns=[
        r"\bNFL\b",
        r"\bSuper\s+Bowl\b",
        r"\bPro\s+Football\b",
    ],
    columns=[
        GridColumn(key="make_playoffs", label="Make Playoffs", order=1),
        GridColumn(key="division", label="Division", order=2),
        GridColumn(key="conference", label="Conference", order=3),
        GridColumn(key="championship", label="Super Bowl", order=4),
    ],
    matching_rules=[
        MarketMatchingRule(
            column="championship",
            tier=1,
            name_patterns=[
                r"Super\s+Bowl",
                r"NFL\s+Championship",
                r"NFL\s+Champion",
            ],
            canonical_prefix="americanfootball_nfl_championship",
        ),
        MarketMatchingRule(
            column="conference",
            tier=2,
            name_patterns=[
                r"(?:AFC|NFC)\s+Champion",
                r"(?:AFC|NFC)\s+Winner",
                r"NFL.*Conference",
            ],
        ),
        MarketMatchingRule(
            column="division",
            tier=4,
            name_patterns=[
                r"\bDivision\b",
                r"(?:AFC|NFC)\s+(?:East|West|North|South)\b",
            ],
        ),
        MarketMatchingRule(
            column="make_playoffs",
            name_patterns=[
                r"Make\s+(?:the\s+)?(?:Playoffs|Postseason)",
                r"(?:Playoff|Postseason)\s+(?:Berth|Qualif)",
            ],
        ),
    ],
    team_sort="championship_desc",
    conference_split=True,
    conference_field="conference",
    trend_hours=168,
    max_teams=32,
)

MLB_CONFIG = LeagueConfig(
    slug="mlb",
    name="MLB Playoffs 2026",
    sport_category="baseball",
    sport_keys=["baseball_mlb"],
    stage_key="baseball",
    league_name_patterns=[
        r"\bMLB\b",
        r"\bWorld\s+Series\b",
        r"\bPro\s+Baseball\b",
        r"\bMajor\s+League\s+Baseball\b",
        r"\bAmerican\s+League\b",
        r"\bNational\s+League\b",
        r"\bAL\s+(?:East|West|Central)\b",
        r"\bNL\s+(?:East|West|Central)\b",
    ],
    # Exclude college baseball markets that match "World Series" etc.
    league_exclude_patterns=[
        r"\bCollege\b",
        r"\bNCAA\b",
        r"\bCWS\b",
    ],
    columns=[
        GridColumn(key="make_playoffs", label="Make Playoffs", order=1),
        GridColumn(key="division", label="Division", order=2),
        GridColumn(key="pennant", label="AL / NL Champ", order=3),
        GridColumn(key="championship", label="World Series", order=4),
    ],
    matching_rules=[
        MarketMatchingRule(
            column="championship",
            tier=1,
            name_patterns=[
                r"World\s+Series",
                r"MLB\s+Championship",
                r"MLB\s+Champion",
                r"Pro\s+Baseball\s+Champion",
            ],
            canonical_prefix="baseball_mlb_championship",
        ),
        MarketMatchingRule(
            column="pennant",
            tier=2,
            name_patterns=[
                r"(?:American|National)\s+League\s+(?:Pennant|Champion|Winner)",
                r"(?:AL|NL)\s+(?:Pennant|Champion|Winner)",
                r"MLB.*(?:AL|NL)\b",
            ],
        ),
        MarketMatchingRule(
            column="division",
            tier=4,
            name_patterns=[
                r"\bDivision\b",
                r"(?:AL|NL)\s+(?:East|West|Central)\b",
            ],
        ),
        MarketMatchingRule(
            column="make_playoffs",
            name_patterns=[
                r"Make\s+(?:the\s+)?(?:Playoffs|Postseason)",
                r"(?:Playoff|Postseason)\s+(?:Berth|Qualif)",
            ],
        ),
    ],
    team_sort="championship_desc",
    conference_split=True,
    conference_field="conference",  # AL vs NL stored as "conference" in standings
    trend_hours=168,
    max_teams=30,
    season_pattern="2026",
)

WNBA_CONFIG = LeagueConfig(
    slug="wnba",
    name="WNBA Playoffs 2026",
    sport_category="basketball",
    sport_keys=["basketball_wnba"],
    stage_key="basketball",
    league_name_patterns=[
        r"\bWNBA\b",
        r"\bWomen.?s\s+(?:NBA|Basketball)\b",
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
                r"WNBA\s+Championship",
                r"WNBA\s+Champion",
                r"WNBA\s+Finals",
            ],
            canonical_prefix="basketball_wnba_championship",
        ),
        MarketMatchingRule(
            column="conference",
            tier=2,
            name_patterns=[
                r"WNBA.*Conference",
                r"(?:Eastern|Western)\s+Conference.*WNBA",
            ],
        ),
        MarketMatchingRule(
            column="make_playoffs",
            name_patterns=[
                r"Make\s+(?:the\s+)?(?:Playoffs|Postseason)",
                r"(?:Playoff|Postseason)\s+(?:Berth|Qualif)",
            ],
        ),
    ],
    team_sort="championship_desc",
    conference_split=True,
    conference_field="conference",
    trend_hours=168,
    max_teams=13,
    season_pattern="2026",
)

MLS_CONFIG = LeagueConfig(
    slug="mls",
    name="MLS Cup 2026",
    sport_category="soccer",
    sport_keys=["soccer_usa_mls"],
    stage_key="soccer",
    league_name_patterns=[
        r"\bMLS\b",
        r"\bMajor\s+League\s+Soccer\b",
    ],
    columns=[
        GridColumn(key="make_playoffs", label="Make Playoffs", order=1),
        GridColumn(key="conference", label="Conference", order=2),
        GridColumn(key="championship", label="MLS Cup", order=3),
    ],
    matching_rules=[
        MarketMatchingRule(
            column="championship",
            tier=1,
            name_patterns=[
                r"MLS\s+Cup",
                r"MLS\s+Championship",
                r"MLS\s+Champion",
            ],
            canonical_prefix="soccer_usa_mls_championship",
        ),
        MarketMatchingRule(
            column="conference",
            tier=2,
            name_patterns=[
                r"(?:Eastern|Western)\s+Conference",
                r"MLS.*Conference",
            ],
        ),
        MarketMatchingRule(
            column="make_playoffs",
            name_patterns=[
                r"Make\s+(?:the\s+)?(?:Playoffs|Postseason)",
                r"(?:Playoff|Postseason)\s+(?:Berth|Qualif)",
            ],
        ),
    ],
    team_sort="championship_desc",
    conference_split=True,
    conference_field="conference",
    trend_hours=168,
    max_teams=29,
    season_pattern="2026",
)

NCAA_FOOTBALL_CONFIG = LeagueConfig(
    slug="ncaa-football",
    name="College Football Playoff 2026-27",
    sport_category="football",
    sport_keys=["americanfootball_ncaaf"],
    stage_key="football",
    league_name_patterns=[
        r"\bCFP\b",
        r"\bCollege\s+Football\s+Playoff\b",
        r"\bNCAAF\b",
        r"\bCollege\s+Football\b",
        r"\bFBS\b",
    ],
    columns=[
        GridColumn(key="make_playoffs", label="Make Playoff", order=1),
        GridColumn(key="semifinal", label="Semifinal", order=2),
        GridColumn(key="championship", label="Champion", order=3),
    ],
    matching_rules=[
        MarketMatchingRule(
            column="championship",
            tier=1,
            name_patterns=[
                r"College\s+Football\s+Playoff.*(?:Winner|Champion)",
                r"NCAAF\s+Championship",
                r"NCAAF\s+Champion",
                r"CFP\s+(?:Winner|Champion)",
                r"National\s+Champion(?!\s*ship\s+Game).*(?:College|NCAAF|CFP)",
            ],
            canonical_prefix="americanfootball_ncaaf_championship",
        ),
        MarketMatchingRule(
            column="semifinal",
            name_patterns=[
                r"Semifinal",
                r"(?:Rose|Sugar|Orange|Cotton)\s+Bowl",
                r"Make.*Semifinal",
                r"Final\s+Four",  # CFP uses "Final Four" terminology too
            ],
        ),
        MarketMatchingRule(
            column="make_playoffs",
            name_patterns=[
                r"Make\s+(?:the\s+)?(?:College\s+Football\s+)?Playoff",
                r"CFP\s+(?:Berth|Qualif|Field)",
                r"Playoff\s+(?:Berth|Qualif)",
            ],
        ),
    ],
    team_sort="championship_desc",
    conference_split=True,
    conference_field="conference",
    trend_hours=168,
    max_teams=40,
    season_pattern="2026-27",
)

EPL_CONFIG = LeagueConfig(
    slug="epl",
    name="Premier League 2025-26",
    sport_category="soccer",
    sport_keys=["soccer_epl"],
    stage_key="soccer",
    league_name_patterns=[
        r"\bPremier\s+League\b",
        r"\bEPL\b",
        r"\bEnglish\s+Premier\b",
    ],
    columns=[
        GridColumn(key="relegation", label="Relegated", order=1, sequential=False),
        GridColumn(key="top_4", label="Top 4", order=2, sequential=False),
        GridColumn(key="championship", label="Champion", order=3, sequential=False),
    ],
    matching_rules=[
        MarketMatchingRule(
            column="championship",
            tier=1,
            name_patterns=[
                r"Premier\s+League.*(?:Winner|Champion)",
                r"EPL.*(?:Winner|Champion)",
                r"Win\s+(?:the\s+)?Premier\s+League",
            ],
            canonical_prefix="soccer_epl_championship",
        ),
        MarketMatchingRule(
            column="top_4",
            name_patterns=[
                r"Top\s*4",
                r"Champions\s+League\s+(?:Qualif|Spot|Place)",
                r"Finish\s+(?:in\s+)?Top\s*4",
            ],
        ),
        MarketMatchingRule(
            column="relegation",
            name_patterns=[
                r"Relegat",
                r"Bottom\s*3",
                r"Go\s+Down",
            ],
        ),
    ],
    team_sort="championship_desc",
    conference_split=False,
    trend_hours=168,
    max_teams=20,
)

LA_LIGA_CONFIG = LeagueConfig(
    slug="la-liga",
    name="La Liga 2025-26",
    sport_category="soccer",
    sport_keys=["soccer_spain_la_liga"],
    stage_key="soccer",
    league_name_patterns=[
        r"\bLa\s+Liga\b",
        r"\bSpanish\s+(?:League|Football)\b",
        r"\bLiga\s+(?:BBVA|Santander)\b",
    ],
    columns=[
        GridColumn(key="relegation", label="Relegated", order=1, sequential=False),
        GridColumn(key="top_4", label="Top 4", order=2, sequential=False),
        GridColumn(key="championship", label="Champion", order=3, sequential=False),
    ],
    matching_rules=[
        MarketMatchingRule(
            column="championship",
            tier=1,
            name_patterns=[
                r"La\s+Liga.*(?:Winner|Champion)",
                r"Win\s+(?:the\s+)?La\s+Liga",
                r"Spanish\s+League.*(?:Winner|Champion)",
            ],
            canonical_prefix="soccer_spain_la_liga_championship",
        ),
        MarketMatchingRule(
            column="top_4",
            name_patterns=[
                r"Top\s*4",
                r"Champions\s+League\s+(?:Qualif|Spot|Place)",
            ],
        ),
        MarketMatchingRule(
            column="relegation",
            name_patterns=[
                r"Relegat",
                r"Bottom\s*3",
            ],
        ),
    ],
    team_sort="championship_desc",
    conference_split=False,
    trend_hours=168,
    max_teams=20,
)

CHAMPIONS_LEAGUE_CONFIG = LeagueConfig(
    slug="champions-league",
    name="Champions League 2025-26",
    sport_category="soccer",
    sport_keys=["soccer_uefa_champs_league"],
    stage_key="soccer",
    league_name_patterns=[
        r"\bChampions\s+League\b",
        r"\bUCL\b",
        r"\bUEFA\s+Champions\b",
    ],
    columns=[
        GridColumn(key="quarterfinal", label="QF", order=1),
        GridColumn(key="semifinal", label="SF", order=2),
        GridColumn(key="final", label="Final", order=3),
        GridColumn(key="championship", label="Champion", order=4),
    ],
    matching_rules=[
        MarketMatchingRule(
            column="championship",
            tier=1,
            name_patterns=[
                r"Champions\s+League.*(?:Winner|Champion)",
                r"UCL.*(?:Winner|Champion)",
                r"Win\s+(?:the\s+)?Champions\s+League",
            ],
            canonical_prefix="soccer_uefa_champs_league_championship",
        ),
        MarketMatchingRule(
            column="final",
            name_patterns=[
                r"(?:Make|Reach)\s+(?:the\s+)?Final",
                r"Finalist",
            ],
        ),
        MarketMatchingRule(
            column="semifinal",
            name_patterns=[
                r"(?:Make|Reach)\s+(?:the\s+)?Semi",
                r"Semifinal",
                r"Last\s*4",
            ],
        ),
        MarketMatchingRule(
            column="quarterfinal",
            name_patterns=[
                r"(?:Make|Reach)\s+(?:the\s+)?Quarter",
                r"Quarterfinal",
                r"Last\s*8",
            ],
        ),
    ],
    team_sort="championship_desc",
    conference_split=False,
    trend_hours=168,
    max_teams=36,
)

BUNDESLIGA_CONFIG = LeagueConfig(
    slug="bundesliga",
    name="Bundesliga 2025-26",
    sport_category="soccer",
    sport_keys=["soccer_germany_bundesliga"],
    stage_key="soccer",
    league_name_patterns=[
        r"\bBundesliga\b",
        r"\bGerman\s+(?:League|Football)\b",
    ],
    columns=[
        GridColumn(key="relegation", label="Relegated", order=1, sequential=False),
        GridColumn(key="top_4", label="Top 4", order=2, sequential=False),
        GridColumn(key="championship", label="Champion", order=3, sequential=False),
    ],
    matching_rules=[
        MarketMatchingRule(
            column="championship",
            tier=1,
            name_patterns=[
                r"Bundesliga.*(?:Winner|Champion)",
                r"Win\s+(?:the\s+)?Bundesliga",
                r"German\s+League.*(?:Winner|Champion)",
            ],
            canonical_prefix="soccer_germany_bundesliga_championship",
        ),
        MarketMatchingRule(
            column="top_4",
            name_patterns=[
                r"Top\s*4",
                r"Champions\s+League\s+(?:Qualif|Spot|Place)",
            ],
        ),
        MarketMatchingRule(
            column="relegation",
            name_patterns=[
                r"Relegat",
                r"Bottom\s*(?:2|3)",
            ],
        ),
    ],
    team_sort="championship_desc",
    conference_split=False,
    trend_hours=168,
    max_teams=18,
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
    max_teams=156,  # Full PGA field (DataGolf defines the canonical field)
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
        NFL_CONFIG,
        MLB_CONFIG,
        WNBA_CONFIG,
        MLS_CONFIG,
        NCAA_BASKETBALL_CONFIG,
        WNCAA_BASKETBALL_CONFIG,
        NCAA_FOOTBALL_CONFIG,
        EPL_CONFIG,
        LA_LIGA_CONFIG,
        CHAMPIONS_LEAGUE_CONFIG,
        BUNDESLIGA_CONFIG,
        GOLF_CONFIG,
    ]
}


def get_league_config(slug: str) -> LeagueConfig | None:
    """Look up a league config by URL slug."""
    return LEAGUE_CONFIGS.get(slug)


def get_all_league_slugs() -> list[str]:
    """Return all configured league slugs (for index page / navigation)."""
    return list(LEAGUE_CONFIGS.keys())


# ---------------------------------------------------------------------------
# Sport groups — sport_category → league slugs
# ---------------------------------------------------------------------------

SPORT_GROUPS: dict[str, list[str]] = {
    "basketball": ["nba", "wnba", "ncaa-basketball", "ncaa-women-basketball"],
    "football": ["nfl", "ncaa-football"],
    "baseball": ["mlb"],
    "hockey": ["nhl"],
    "soccer": ["epl", "la-liga", "champions-league", "bundesliga", "mls"],
    "golf": ["golf"],
}

# Reverse: league_slug → sport_group
LEAGUE_TO_SPORT: dict[str, str] = {
    league: sport
    for sport, leagues in SPORT_GROUPS.items()
    for league in leagues
}

# Odds API sport_key → league_slug (for resolving events to their league)
_SPORT_KEY_TO_LEAGUE: dict[str, str] = {}
for _cfg in LEAGUE_CONFIGS.values():
    for _sk in _cfg.sport_keys:
        _SPORT_KEY_TO_LEAGUE[_sk] = _cfg.slug


def get_league_for_sport_key(sport_key: str) -> LeagueConfig | None:
    """Resolve an Odds API sport key (e.g., 'basketball_nba') to its LeagueConfig."""
    slug = _SPORT_KEY_TO_LEAGUE.get(sport_key)
    if slug:
        return LEAGUE_CONFIGS.get(slug)
    return None
