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
    #: The column whose probability BOUNDS this one, when that is not simply the
    #: column before it. Monotonicity (`utils/playoff_grid.monotonic_pairs`)
    #: otherwise reads "the previous sequential column" as the prerequisite,
    #: which is false wherever a stage sits beside the ladder rather than on it:
    #: in all four leagues with a `division` column a wild card reaches — and
    #: wins — the conference final without winning its division (#7076). Must
    #: name an EARLIER sequential column of the same league; the guard test
    #: `test_playoff_grid_division_is_not_a_prerequisite_7076` asserts that for
    #: every config, because a typo here falls back to the previous column and
    #: would restore the bug silently.
    depends_on: str | None = None


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
    name: str  # Display name, e.g. "NBA Playoffs <season>" — SERVED to readers
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
    # Kalshi ticker prefixes for a *different* competition that would otherwise
    # be over-captured by external_id_prefixes (prefix collision) or by
    # league_name_patterns. Markets whose external_id starts with any of these
    # are excluded from the grid on EVERY match path. Example: KXNBACUP (the
    # in-season Cup) collides with the NBA's KXNBA prefix but is a separate
    # competition and must not surface in the NBA Championship grid.
    external_id_exclude_prefixes: list[str] = field(default_factory=list)
    # Kalshi series tickers carrying this league's per-team SEASON WIN TOTAL
    # ladder (T2-1 / #5058). One market per team, named
    # "<competition>: <subject> Total Wins", rungs named "10+ wins".
    #
    # 🔴 EMPTY MEANS "we have not checked this league", not "the venue has no
    # such market". The subject on those markets is a bare place name
    # ("New England", "Los Angeles C") resolved against THIS league's closed
    # team set, and that resolution is only as safe as the set is small — thirty
    # pro clubs, yes; several hundred college programmes sharing place names
    # with each other and with the pros, not yet. Adding a series here is
    # therefore a claim that the resolution has been measured for that league,
    # which is why it is a list and not a pattern.
    wins_series: list[str] = field(default_factory=list)
    team_sort: str = "championship_desc"  # "championship_desc" | "name_asc" | "seed_asc"
    conference_split: bool = False  # Show teams grouped by conference?
    conference_field: str = "conference"  # Field on standings_data for grouping
    region_split: bool = False  # Show teams grouped by region (March Madness)?
    trend_hours: int = 168  # Default trend chart window (7 days)
    max_teams: int = 40  # Cap on teams shown in grid
    # NOT only a filter (#4441). This string is also SERVED to readers as
    # `season` on `GET /api/playoffs/{slug}`, and it sets the `max_year` bound
    # in `_extract_season_max_year`, so a stale value captions a hub with a
    # season that has ended AND drops that season's own futures markets. Seven
    # leagues sat on this default a full season past its end because nothing
    # ever failed when it went stale; `tests/test_league_hub_season_is_not_
    # last_season_4441.py` now fails when the two-calendar-year leagues stop
    # agreeing with each other, which is the tell that one was forgotten.
    season_pattern: str = "2026-27"  # For filtering to current season markets


# ---------------------------------------------------------------------------
# League definitions
# ---------------------------------------------------------------------------

NBA_CONFIG = LeagueConfig(
    slug="nba",
    name="NBA Playoffs 2026-27",
    sport_category="basketball",
    sport_keys=["basketball_nba"],
    stage_key="basketball",
    league_name_patterns=[
        r"\bNBA\b",
        r"\bPro\s+Basketball\b",
    ],
    external_id_prefixes=["KXNBA"],
    # The in-season Cup (Emirates NBA Cup) is a *different* competition than the
    # NBA Championship this grid represents. Its Kalshi series KXNBACUP collides
    # with the KXNBA prefix above, and its market names ("... Pro Basketball Cup
    # Champion") match the \bPro Basketball\b name pattern. Both would otherwise
    # inject Cup probabilities into the Championship grid (grid sentinel #196
    # extreme-watch: teams shown at Cup odds in the NBA champion column).
    external_id_exclude_prefixes=["KXNBACUP"],
    league_exclude_patterns=[
        r"\bPro\s+Basketball\s+Cup\b",
        r"\bNBA\s+Cup\b",
        # #8893: three markets that do not ask who wins a conference were drawn
        # on the Conference stage chart — "Conference Finals Qualifiers" (who
        # REACHES the conference final), "Conference to Win Pro Basketball
        # Finals" and "LeBron James' Next Conference" (outcomes are conferences:
        # lines named "Any team in the Eastern Conference 99%").
        r"\bConference\s+Finals\s+Qualif",
        r"\bConference\s+to\s+Win\b",
        r"\bNext\s+Conference\b",
    ],
    columns=[
        GridColumn(key="make_playoffs", label="Make Playoffs", order=1),
        GridColumn(key="division", label="Division", order=2),
        # #7076: bounded by making the playoffs, NOT by winning the division —
        # a wild card wins the conference without ever leading its division.
        GridColumn(key="conference", label="Conference", order=3, depends_on="make_playoffs"),
        GridColumn(key="championship", label="Champion", order=4),
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
            column="division",
            tier=4,
            name_patterns=[
                r"Division\s+Winner",
                r"Win\s+(?:the\s+)?Division",
                r"Division\s+Champion",
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
    # Measured 2026-09-11: 30 open `KXNBAWINS-27*` markets; "Los Angeles C" and
    # "Los Angeles L" each prefix exactly one of this grid's 30 team names.
    wins_series=["KXNBAWINS"],
    team_sort="championship_desc",
    conference_split=True,
    conference_field="conference",
    trend_hours=168,
    max_teams=30,
)

NHL_CONFIG = LeagueConfig(
    slug="nhl",
    name="NHL Playoffs 2026-27",
    sport_category="hockey",
    sport_keys=["icehockey_nhl"],
    stage_key="hockey",
    external_id_prefixes=["KXNHL"],
    league_name_patterns=[
        r"\bNHL\b",
        r"\bStanley\s+Cup\b",
        r"\bPro\s+Hockey\b",
    ],
    columns=[
        GridColumn(key="make_playoffs", label="Make Playoffs", order=1),
        GridColumn(key="division", label="Division", order=2),
        # #7076: see the NBA block — the division is beside the ladder, not on it.
        GridColumn(key="conference", label="Conference", order=3, depends_on="make_playoffs"),
        GridColumn(key="championship", label="Stanley Cup", order=4),
    ],
    matching_rules=[
        MarketMatchingRule(
            column="make_playoffs",
            name_patterns=[
                r"Make\s+(?:the\s+)?(?:Playoffs|Postseason)",
                r"(?:Playoff|Postseason)\s+(?:Berth|Qualif)",
                r"Playoff\s+Qualif",
            ],
        ),
        MarketMatchingRule(
            column="championship",
            tier=1,
            name_patterns=[
                r"Stanley\s+Cup(?!\s*®?\s*Playoff\s*Qualif)",
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
    ],
    team_sort="championship_desc",
    conference_split=True,
    conference_field="conference",
    trend_hours=168,
    max_teams=32,
)

NCAA_BASKETBALL_CONFIG = LeagueConfig(
    slug="ncaa-basketball",
    name="NCAA Tournament 2027",
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
    #
    # #8166. `KXMARMAD-2` is the CHAMPION series. Only the round markets were
    # listed here, so Kalshi's `KXMARMAD-27` ("Men's 2027 College Basketball
    # Champion", 73/73 priced) never reached the candidate set and the Champion
    # column was served by odds_api alone — while the other five columns were
    # already Kalshi 2027. The championship rule below has carried
    # `College\s+Basketball\s+Champion\b` commented "Kalshi: Men's College
    # Basketball Champion" the whole time: the pattern was unreachable at THIS
    # gate, not missing.
    #
    # ═══ WHY NOT THE BARE `KXMARMAD` (measured, not argued) ═══
    #
    # Over the real candidate population (44 rows, census 2026-09-23) a bare
    # `KXMARMAD` admits 33 further markets and FOUR reach a column:
    # `KXMARMADSEEDROUND-26S1F4` / `-26S2F4` and `KXMARMADSEED-26F4` land in
    # `final_four`, `KXMARMADSEED-26R32` in `round_of_32` — seed-COUNT props, not
    # teams. Those four happen to contribute nothing today (all 33 of their
    # outcomes are either past the 7-day stale cutoff or caught by the numeric-
    # outcome filter), so they are not the reason for the narrowing. The reason is
    # their OPEN 2027 siblings: `KXMARMADSEED-27T2/T3/T4/T5` and `KXMARMAD1SEED-27`
    # carry 293 fresh, team-NAMED, fully-priced outcomes ("Michigan St.", "FDU")
    # that neither the stale cutoff nor the numeric filter touches. They reach no
    # column today only because `_match_market_to_column` finds no pattern for
    # "Top 2 Seeds" — a single name-shaped defence. Narrowing here keeps them out
    # of the candidate set entirely, which is a second and structural one.
    #
    # The trailing `2` is a decade bound, not a season pin: it covers
    # `KXMARMAD-26` through `-29` and excludes every `KXMARMADSEED*` /
    # `KXMARMAD1SEED*` / `KXMARMADUPSET*` / `KXMARMADPTS*` sibling, which insert
    # LETTERS where the champion series puts its season. It is also what keeps
    # this arm index-served: `external_id_prefix_range` refuses a prefix ending in
    # punctuation (`-` is ignorable at the primary level under en_US.UTF-8), so a
    # bare `KXMARMAD-` yields NO range and drops this league back to the 266K-row
    # Kalshi scan LAT-P132 measured at 24,465 ms. `KXMARMAD-2` ranges to
    # `['KXMARMAD-', 'KXMARMAD-3')`. The same decade bound is already assumed by
    # `_YEAR_RE` in `routes/playoffs.py`.
    external_id_prefixes=["KXMARMADROUND", "KXMARMAD-2"],
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
    # #8166. The 2026 men's tournament finished in April 2026. Every market this
    # grid actually serves is the 2027 one: the five round columns are fed by
    # `KXMARMADROUND-27*`, and their 2026 twins are `resolved` with outcomes last
    # written in March/April 2026 — beyond the grid's 7-day stale cutoff, so they
    # contribute nothing. The grid was therefore already forecasting March 2027
    # while `name` said 2026 and the two NCAA basketball grids contradicted each
    # other about what season it is.
    #
    # The pattern is load-bearing as well as a label, which is the second half of
    # the same defect: at "2026", `_is_future_season_market` dropped the one
    # market whose name carries its year — Kalshi's "Men's 2027 College Basketball
    # Champion". Same mechanism, same repair, as the women's config below.
    #
    # BOTH gates were necessary and neither was sufficient: with only this pattern
    # moved the champion market is still excluded by the ticker prefix above, and
    # with only the prefix widened it is still dropped here.
    season_pattern="2027",
)

WNCAA_BASKETBALL_CONFIG = LeagueConfig(
    slug="ncaa-women-basketball",
    name="Women's NCAA Tournament 2027",
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
    # The 2026 women's tournament finished in April 2026; the only WNCAAB market
    # carrying live prices is Kalshi's KXWMARMAD-27 ("Women's 2027 College
    # Basketball Champion", 35 priced outcomes). Because that name carries its
    # year, a season_pattern of "2026" made _is_future_season_market drop the one
    # market with data, and the grid served columns=[] teams=0 behind the
    # "No championship odds available yet" empty state — a false claim.
    # The 2026 markets this now treats as past season are all resolved and five
    # months stale, so the outcome-level staleness cutoff already excluded them.
    season_pattern="2027",
)

NFL_CONFIG = LeagueConfig(
    slug="nfl",
    name="NFL Playoffs 2026-27",
    sport_category="football",
    sport_keys=["americanfootball_nfl"],
    external_id_prefixes=["KXNFL"],
    # "Who will host the 2031 Pro Football Championship?" is a stadium-award
    # market, not a title market — it matches \bPro\s+Football\b and would land
    # cities in the Champion column.
    external_id_exclude_prefixes=["KXSBHOST"],
    # #8893: Kalshi KXNFLROUNDQUAL-27CONF asks who REACHES the conference title
    # game; on the Conference stage chart its prices ("Cincinnati 25.5%") drew
    # above the conference-winner lines. Reaching is not winning (#8885).
    league_exclude_patterns=[
        r"\bConference\s+Championship\s+(?:Game\s+)?Qualif",
    ],
    stage_key="football",
    league_name_patterns=[
        r"\bNFL\b",
        r"\bSuper\s+Bowl\b",
        r"\bPro\s+Football\b",
    ],
    columns=[
        GridColumn(key="make_playoffs", label="Make Playoffs", order=1),
        GridColumn(key="division", label="Division", order=2),
        # #7076: a wild card plays — and has won — the Super Bowl, so the
        # division title cannot bound the conference cell.
        GridColumn(key="conference", label="Conference", order=3, depends_on="make_playoffs"),
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
    # Measured 2026-09-11: 32 open `KXNFLWINS-27*` markets, and all 32 subjects
    # ("New England", "New York G", "Los Angeles C", ...) resolve to exactly one
    # of this grid's 32 team names.
    wins_series=["KXNFLWINS"],
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
    external_id_prefixes=["KXMLB"],
    # "Pro Baseball Championship Series Matchup" asks which two teams REACH the
    # World Series, not who wins it — it matches \bPro\s+Baseball\b and would
    # put matchup pairs in the Champion column.
    external_id_exclude_prefixes=["KXTEAMSINWS"],
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
        # #8893: "Pro Baseball NLCS Qualifiers" asks who REACHES the LCS; the
        # pennant rule's \b(?:ALCS|NLCS)\b admitted it, and the AL / NL Champ
        # chart drew "Los Angeles D 67.5%" above the real pennant line (41.5%).
        r"\b(?:AL|NL)(?:CS|DS)\s+Qualif",
    ],
    columns=[
        GridColumn(key="make_playoffs", label="Make Playoffs", order=1),
        GridColumn(key="division", label="Division", order=2),
        # #7076 — the reported specimen. Boston's real pennant rows (0.115 /
        # 0.122) sat far above their division rows (0.010 / 0.003) because a
        # wild card wins the pennant; the old previous-column bound rewrote
        # pennant AND World Series to the division blend, 0.0065, for 10 of 30
        # teams including the Yankees.
        GridColumn(key="pennant", label="AL / NL Champ", order=3, depends_on="make_playoffs"),
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
            column="division",
            tier=4,
            name_patterns=[
                r"\bDivision\b",
                r"(?:AL|NL)\s+(?:East|West|Central)\b",
            ],
        ),
        MarketMatchingRule(
            column="pennant",
            tier=2,
            name_patterns=[
                r"(?:American|National)\s+League\s+(?:Pennant|Champion|Winner)",
                r"(?:AL|NL)\s+(?:Pennant|Champion|Winner)",
                r"\b(?:ALCS|NLCS)\b",
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
    external_id_prefixes=["KXWNBA"],
    # #8893: KXWNBA3PTROUND ("3-Point Contest Championship Round Qualifiers")
    # rides the KXWNBA prefix; its players led the Champion chart at 99%.
    league_exclude_patterns=[
        r"\b(?:3|Three)-?\s*Point\s+Contest\b",
    ],
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
    # This grid has make_playoffs / semifinal / championship columns and no
    # conference column, so a conference title has nowhere honest to go — the
    # stage fallback drops it in `championship`, next to national-title odds.
    # FCS is a different division entirely.
    league_exclude_patterns=[
        r"\b(?:AAC|ACC|Big\s*12|Big\s*Ten|MAC|Mountain\s+West|Pac-?12|SEC|Sun\s+Belt|C-?USA|Conference\s+USA)\s+Championship\b",
        r"\bFCS\b",
        # "Will <team> Make the 2027 CFP National Championship" is odds to REACH
        # the final, not to win it. There is no `final` column here, and the
        # stage fallback files it under `championship`, where it would overstate
        # every team's title odds.
        r"\bMake\b.*\bNational\s+Championship\b",
        # #8885: Kalshi names the same question "College Football National
        # Championship Qualifiers" (KXNCAAFFINALIST). Filed under
        # `championship`, its ~30% finalist prices merged with the Winner
        # market's ~12% by team name and drew the Champion chart as a sawtooth.
        r"\bNational\s+Championship\s+(?:Game\s+)?Qualifiers?\b",
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
    name="Premier League 2026-27",
    sport_category="soccer",
    sport_keys=["soccer_epl"],
    stage_key="soccer",
    league_name_patterns=[
        r"\bPremier\s+League\b",
        r"\bEPL\b",
        r"\bEnglish\s+Premier\b",
    ],
    league_exclude_patterns=[
        r"\bEgyptian\b",
        r"\bEgypt\b",
        r"\bSaudi\b",
        r"\bScottish\b",
        r"\bRussian\b",
        r"\bUkrainian\b",
        # Until the ILIKE prefilter was repaired these three could never reach
        # the Python matcher, so "<somewhere else>'s Premier League" was
        # excluded only in principle. They are real open markets today.
        r"\bCaribbean\b",
        r"\bKazakhstan\b",
        r"\bLanka\b",
        r"\bEFL\b",
        r"\bChampionship\b(?!.*League)",
        r"\bLeague One\b",
        r"\bLeague Two\b",
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
    name="La Liga 2026-27",
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
    name="Champions League 2026-27",
    sport_category="soccer",
    sport_keys=["soccer_uefa_champs_league"],
    stage_key="soccer",
    league_name_patterns=[
        r"\bChampions\s+League\b",
        r"\bUCL\b",
        r"\bUEFA\s+Champions\b",
    ],
    # #6250: Kalshi's KXUCLLEAGUE-27 "Champions League: League of Champion"
    # asks which DOMESTIC LEAGUE the winner comes from — its 16 outcomes are
    # "Ligue 1" 0.99, "Bundesliga" 0.99, "English Premier League" 0.52 — and it
    # satisfies the Champion column's `Champions\s+League.*(?:Winner|Champion)`
    # rule on the word "Champion" alone. Four leagues therefore rendered as
    # grid rows under a column headed "Team", and team_count counted them.
    # Excluded on the SERIES TICKER rather than the title because the title is
    # what admitted it: a name regex narrow enough to refuse "League of
    # Champion" is one typo away from refusing the real "Champions League
    # Winner" (KXUCL-27), while the ticker families are disjoint by
    # construction and survive the season roll to KXUCLLEAGUE-28.
    # The market is not deleted or hidden: /futures/59164808 stays reachable.
    external_id_exclude_prefixes=["KXUCLLEAGUE"],
    # #6905: the ASIAN confederation's competition, in the UEFA grid. Polymarket
    # 60607650 "AFC Champions League Elite 2026-27 Winner" satisfies this
    # config's `\bChampions\s+League\b` league gate, and then the Champion
    # column's `Champions\s+League.*(?:Winner|Champion)` NAME rule — it is tier
    # 2, so the tier path never fired and raising the tier bar would not have
    # stopped it. Admitted, it merged its clubs into this table: read from
    # production 2026-09-18,
    # FIFTEEN of the 36 rows were AFC — Shanghai Port ranked SIXTH to win the
    # UEFA Champions League, above Manchester City, with Pakhtakor, Al-Hilal,
    # Kashima Antlers and eleven more beside them. The grid caps at 36, so
    # fifteen genuine UEFA clubs were pushed off the table to make room.
    #
    # Excluded on the CONFEDERATION QUALIFIER, which is the token that makes it a
    # different competition. This is a name gate and #6250 argued against those
    # — but #6250's objection was to a name gate narrow enough to refuse the real
    # market by one typo ("League of Champion" vs "Champions League Winner").
    # That risk is absent here: "AFC" is a prefix no UEFA market carries, the two
    # strings are disjoint rather than one-character apart, and the season roll
    # to 2027-28 does not touch it. The Kalshi ticker mechanism is unavailable —
    # this row is Polymarket and its external_id is the numeric event id 994393,
    # which changes next season, so a prefix rule would silently lapse.
    #
    # `AFC` is also the NFL's American Football Conference. It cannot collide:
    # the pattern requires "Champions League" immediately after, and this
    # exclusion is scoped to this config, which the NFL grid never reads.
    # The market is not deleted or hidden: /futures/60607650 stays reachable.
    league_exclude_patterns=[
        r"\bAFC\s+Champions\s+League\b",
        # #8893: "League Phase Winner" asks who tops the league table, not who
        # lifts the trophy; blended into the Champion cells it lifted Barcelona
        # to 21% (winner market 17.7%). No league-phase market is a QF/SF/
        # Champion question.
        r"\bLeague\s+Phase\b",
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
    name="Bundesliga 2026-27",
    sport_category="soccer",
    sport_keys=["soccer_germany_bundesliga"],
    stage_key="soccer",
    league_name_patterns=[
        r"\bBundesliga\b",
        r"\bGerman\s+(?:League|Football)\b",
    ],
    # #6905 (Alex, p1). "Bundesliga" is not one competition's name — it is the
    # German word for "federal league", and at least two OTHER competitions
    # carry it. `\bBundesliga\b` admitted both, and because the child's title
    # CONTAINS the parent's string no positive gate can separate them; the
    # discriminator has to be the qualifier that names the other competition.
    #
    #   1. polymarket 58867088 "2. Bundesliga: 2026-27 Winner" — the division
    #      BELOW this one. Read from production 2026-09-18: seven of the top ten
    #      rows of the Champion column were 2. Bundesliga clubs, Eintracht
    #      Braunschweig ranked SECOND to win the Bundesliga, above Dortmund.
    #      They carry no crest and no Relegated or Top 4 value because they are
    #      not in this competition. The grid caps at 18, so the seven intruders
    #      pushed Augsburg and M'gladbach off the table — and M'gladbach's 84%
    #      Relegated is the highest in the division, so the single most
    #      significant number on the page was the one not served.
    #
    #   2. polymarket 59516500 "Austrian Bundesliga: Teams relegated (2026-27)"
    #      — a DIFFERENT COUNTRY's top flight, reaching the Relegated column.
    #      Not named in #6905; found by enumerating this grid's admitted set
    #      rather than the one market the issue reported.
    #
    # Both are Polymarket with numeric event ids (836242, 904914) that change on
    # the season roll, so #6250's ticker-prefix mechanism cannot express this.
    # These patterns are anchored on the qualifier, not on the season, so they
    # survive the roll and also cover the sibling rows the same two competitions
    # publish (Runner-Up, 3rd Place, promotion, clean sheets — twenty-one rows
    # measured today), none of which should ever enter this grid either.
    # Nothing is deleted or hidden: /futures/58867088 and /futures/59516500 stay
    # reachable, and the German second division is a real competition we serve.
    league_exclude_patterns=[
        r"\b2\.\s*Bundesliga\b",
        r"\bAustrian\s+Bundesliga\b",
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
    # "U.S. Open: First Time Winner?" is a yes/no prop about the field, not a
    # golfer's odds to win — it matches the `win` column's \bWinner\b rule.
    league_exclude_patterns=[
        r"\bFirst\s+Time\s+Winner\b",
    ],
    columns=[
        GridColumn(key="make_cut", label="Make Cut", order=1, sequential=True),
        GridColumn(key="top_20", label="Top 20", order=2, sequential=True),
        GridColumn(key="top_10", label="Top 10", order=3, sequential=True),
        GridColumn(key="top_5", label="Top 5", order=4, sequential=True),
        GridColumn(key="win", label="Win", order=5, sequential=True),
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


_SLUG_ALIASES: dict[str, str] = {
    "ucl": "champions-league",
    "ncaab": "ncaa-basketball",
    "ncaaf": "ncaa-football",
    "wncaab": "ncaa-women-basketball",
    "ncaa": "ncaa-basketball",
}


def resolve_league_slug(slug: str) -> str:
    """Map a URL slug onto the ONE slug the rest of the system is keyed on.

    ``get_league_config`` has always resolved aliases, so every caller that only
    needed the config was already alias-safe. A caller that does anything else
    with the slug — a cache key, a task name, a ``league_slug`` column
    comparison, an ``== "ncaa-basketball"`` branch — was not, and that gap is
    #7766: ``/api/playoffs/ncaab`` and ``/api/playoffs/ncaa-basketball`` built
    and cached two payloads for one league, and the page requests the alias.

    An unknown slug is returned unchanged. This resolves, it does not validate:
    the caller's existing "do we have a config for this?" check is still the
    guard (and in ``routes/playoffs.py`` it is also the taint guard — see
    ``_schedule_grid_refresh``).
    """
    return _SLUG_ALIASES.get(slug, slug)


def get_league_config(slug: str) -> LeagueConfig | None:
    """Look up a league config by URL slug."""
    return LEAGUE_CONFIGS.get(resolve_league_slug(slug))


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
