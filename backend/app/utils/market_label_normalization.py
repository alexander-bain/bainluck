"""
Market label normalization for Related Futures.

Translates verbose/machine-readable market names (primarily from Kalshi)
into clean, human-readable labels, and assigns structured categories for
grouping and filtering.

Categories:
    playoff_path  — Playoff berth, conference champion, league champion
    conference     — Conference finals matchup, conference MVP
    award          — MVP, DPOY, 6MOY, MIP, All-Teams, trophies, draft picks
    season_stat    — PPG/RPG/APG leader, best/worst record, win totals, divisions
    game_prop      — Player stat props for a specific game
    trade          — "Player's Next Team" trade speculation
    novelty        — 2K cover, records, will-they-stay, tournament point totals
    ncaa           — NCAA tournament bracket rounds (Men's Round of X)
    other          — Uncategorized
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ── Label cleaning patterns ──────────────────────────────────────────────

# Kalshi uses "Pro Basketball" instead of "NBA", etc.
_PRO_SPORT_REWRITES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bPro Basketball\b", re.I), "NBA"),
    (re.compile(r"\bPro Football\b", re.I), "NFL"),
    (re.compile(r"\bPro Hockey\b", re.I), "NHL"),
    (re.compile(r"\bPro Baseball\b", re.I), "MLB"),
    (re.compile(r"\bAll-Pro\b", re.I), "All-NBA"),
]

# Strip "MLB: 2026 ..." or "NHL: ..." league-year prefixes
_LEAGUE_PREFIX_RE = re.compile(
    r"^(?:MLB|NHL|NFL|NBA|NCAAM|NCAAW):\s+(?:2\d{3}\s+)?", re.I
)

# Strip standalone year or year-range prefix: "2026 ...", "2025-2026 ..."
_YEAR_PREFIX_RE = re.compile(r"^2\d{3}[-\u2013]?(?:\d{2,4}\s+|\s+)")

# Verbose suffixes Kalshi adds
_VERBOSE_SUFFIXES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\s+Winner\??\s*$", re.I), ""),
    (re.compile(r"\s+Selections?\s*$", re.I), ""),
    (re.compile(r"\s+Qualifiers?\s*$", re.I), ""),
]

# Specific label rewrites (pattern → clean label). First match wins.
_LABEL_REWRITES: list[tuple[re.Pattern, str]] = [

    # ── NBA ──────────────────────────────────────────────────────────────

    # Championship
    (re.compile(r"^(?:2\d{3}\s+)?NBA\s+Champ(?:ion(?:ship)?)?\s*(?:Winner)?\s*$", re.I),
     "NBA Champion"),

    # Conference champions
    (re.compile(r"^(?:NBA\s+)?(Eastern|Western)\s+Conference\s+Champion\s*$", re.I),
     r"\1 Conference Champion"),

    # Conference finals matchup
    (re.compile(r"^(?:NBA\s+)?(Eastern|Western)\s+Conference\s+Finals\s+Matchup\s*$", re.I),
     r"\1 Conference Finals Matchup"),
    (re.compile(r"^NBA\s+Finals\s+Matchup\s*$", re.I), "NBA Finals Matchup"),

    # Conference finals MVP
    (re.compile(r"^(Eastern|Western)\s+Conference\s+Finals\s+MVP\s*(?:Winner)?\s*$", re.I),
     r"\1 Conf Finals MVP"),

    # Playoffs
    (re.compile(r"^Which teams will make the NBA Playoffs\??\s*$", re.I),
     "Make NBA Playoffs"),
    (re.compile(r"^NBA\s+Playoff\s*(?:Qualifiers?)?\s*$", re.I), "NBA Playoff Qualifiers"),

    # Play-in
    (re.compile(r"^Teams to Make the (Eastern|Western) Conference Play-In.*$", re.I),
     r"\1 Conference Play-In"),

    # Win totals (generic — handles NBA, MLB, NHL, NFL after pro sport rewrite)
    (re.compile(r"^(?:NBA|MLB|NHL|NFL)\s+Win\s+Totals?.*$", re.I), "Win Total"),
    (re.compile(r"^(?:NBA|MLB|NHL|NFL)\s+Wins\s*$", re.I), "Win Total"),
    (re.compile(r"^(.+?)\s+(?:NBA|MLB|NHL|NFL)\s+wins\s+this\s+season\??\s*$", re.I),
     r"\1 Win Total"),
    (re.compile(r"^Regular\s+Season\s+Win\s+Totals?\s*$", re.I), "Win Total"),
    # Binary win total per team: "Boston Celtics 2025-26 Season Win Total Over 48.5"
    (re.compile(
        r"^(.+?)\s+\d{4}[-\u2013]\d{2,4}\s+(?:Season\s+)?Win\s+Total\s+(?:Over|Under)\s+[\d.]+\s*$",
        re.I,
    ), r"\1 Win Total"),

    # Win streak
    (re.compile(r"^How many games will (.+?) win in a row.*$", re.I),
     r"\1 Win Streak"),

    # Best/worst record (generic)
    (re.compile(r"^(?:NBA|MLB|NHL|NFL)\s+Best\s+(?:Regular\s+Season\s+)?Record\s*$", re.I),
     "Best Record"),
    (re.compile(r"^(?:NBA|MLB|NHL|NFL)\s+Worst\s+(?:Regular\s+Season\s+)?Record\s*$", re.I),
     "Worst Record"),

    # Seed
    (re.compile(r"^(?:NBA\s+)?(Eastern|Western)\s+Conference\s+#1\s+Seed\s*$", re.I),
     r"\1 Conference #1 Seed"),

    # Division winner (generic — handles NBA, NHL after prefix strip)
    (re.compile(r"^(?:(?:NBA|NHL|NFL)[\s:]+)?(\w+)\s+Division\s+(?:Winner)?\s*$", re.I),
     r"\1 Division Winner"),

    # Stats leaders
    (re.compile(r"^NBA\s+Points?\s+Per\s+Game\s+Leader\s*$", re.I), "PPG Leader"),
    (re.compile(r"^NBA\s+Rebounds?\s+Per\s+Game\s+Leader\s*$", re.I), "RPG Leader"),
    (re.compile(r"^NBA\s+Assists?\s+Per\s+Game\s+Leader\s*$", re.I), "APG Leader"),
    (re.compile(r"^NBA\s+Steals?\s+Per\s+Game\s+Leader\s*$", re.I), "SPG Leader"),
    (re.compile(r"^NBA\s+Blocks?\s+Per\s+Game\s+Leader\s*$", re.I), "BPG Leader"),
    (re.compile(r"^NBA\s+Three\s+Pointers?\s+(?:Made\s+)?Per\s+Game\s+Leader\s*$", re.I),
     "3PM Leader"),

    # NBA Awards
    (re.compile(r"^(?:NBA\s+)?MVP\s*(?:Winner)?\s*$", re.I), "MVP"),
    (re.compile(r"^(?:NBA\s+)?Defensive\s+Player\s+of\s+the\s+Year\s*(?:Winner)?\s*$", re.I),
     "DPOY"),
    (re.compile(r"^(?:NBA\s+)?Sixth\s+Man\s+of\s+the\s+Year\s*(?:Winner)?\s*$", re.I),
     "6MOY"),
    (re.compile(r"^(?:NBA\s+)?Most\s+Improved\s+Player\s*(?:Winner)?\s*$", re.I), "MIP"),
    (re.compile(r"^(?:NBA\s+)?Clutch\s+Player\s+of\s+the\s+Year\s*(?:Winner)?\s*$", re.I),
     "Clutch Player"),
    (re.compile(r"^Rookie\s+of\s+the\s+Year\s*(?:Winner)?\s*$", re.I), "ROY"),
    (re.compile(r"^Finals\s+MVP\s*(?:Winner)?\s*$", re.I), "Finals MVP"),

    # All-teams
    (re.compile(r"^All-NBA\s+(1st|2nd|3rd)\s+Team\s*(?:Selections?)?\s*$", re.I),
     r"All-NBA \1 Team"),
    (re.compile(r"^NBA\s+All-Defensive\s+(1st|2nd|3rd)\s+Team\s*(?:Selections?)?\s*$", re.I),
     r"All-Defensive \1 Team"),

    # NBA Draft
    (re.compile(r"^NBA\s+Draft:\s+(1st|2nd|3rd)\s+Overall\s+[Pp]ick\s*$", re.I),
     r"NBA Draft \1 Pick"),
    (re.compile(r"^NBA\s+#(\d+)\s+Overall\s+Pick\s*$", re.I),
     r"NBA Draft #\1 Pick"),
    (re.compile(r"^NBA\s+Players\s+Drafted\s+Top\s+(\d+)\s*$", re.I),
     r"NBA Draft Top \1"),

    # ── NHL ──────────────────────────────────────────────────────────────

    # Stanley Cup
    (re.compile(r"^(?:2\d{3}\s+)?(?:NHL\s+)?Stanley\s+Cup[®]?\s*(?:Champion)?\??\s*$", re.I),
     "Stanley Cup Champion"),
    (re.compile(r"^NHL\s+Champ(?:ion(?:ship)?)?\s*(?:Winner)?\s*$", re.I),
     "Stanley Cup Champion"),

    # NHL Playoffs
    (re.compile(r"^Stanley\s+Cup[®]?\s+Playoff\s*(?:Qualifiers?)?\s*$", re.I),
     "Make NHL Playoffs"),
    (re.compile(r"^Which teams will make the NHL Playoffs\??\s*$", re.I),
     "Make NHL Playoffs"),
    (re.compile(r"^NHL\s+Playoff\s*(?:Qualifiers?)?\s*$", re.I),
     "Make NHL Playoffs"),

    # NHL Trophies
    (re.compile(r"^NHL\s+Hart\s+Memorial\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Hart Trophy"),
    (re.compile(r"^NHL\s+James\s+Norris\s+Memorial\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Norris Trophy"),
    (re.compile(r"^NHL\s+Vezina\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Vezina Trophy"),
    (re.compile(r"^NHL\s+Calder\s+Memorial\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Calder Trophy"),
    (re.compile(r"^NHL\s+Art\s+Ross\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Art Ross Trophy"),
    (re.compile(r"^NHL\s+Selke\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Selke Trophy"),
    (re.compile(r"^NHL\s+Conn\s+Smythe\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Conn Smythe Trophy"),
    # Maurice "Rocket" Richard (various quote styles)
    (re.compile(
        r"^NHL\s+Maurice\s+['\u2018\u2019\u201C\u201D\"]+Rocket['\u2018\u2019\u201C\u201D\"]+\s+"
        r"Richard\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Rocket Richard Trophy"),
    # Presidents' Trophy (various apostrophe placements)
    (re.compile(r"^NHL\s+President['\u2019]?s?['\u2019]?\s+Trophy\s*(?:Winner)?\s*$", re.I),
     "Presidents' Trophy"),

    # ── MLB ──────────────────────────────────────────────────────────────

    # World Series
    (re.compile(r"^(?:MLB\s+)?World\s+Series\s+(?:Champion|Winner)\s*(?:\d{4})?\s*$", re.I),
     "World Series Champion"),
    (re.compile(r"^MLB\s+Champ(?:ion(?:ship)?)?\s*(?:Winner)?\s*$", re.I),
     "World Series Champion"),

    # League champions
    (re.compile(r"^American\s+League\s+Champion\s*$", re.I), "AL Champion"),
    (re.compile(r"^National\s+League\s+Champion\s*$", re.I), "NL Champion"),

    # MLB divisions (AL/NL + direction + Division/Champion)
    (re.compile(r"^(AL|NL)\s+(East|West|Central)\s+(?:Division\s+)?(?:Champion|Winner)\s*$", re.I),
     r"\1 \2 Winner"),

    # MLB Playoffs
    (re.compile(r"^MLB\s+Playoff\s*(?:Qualifiers?)?\s*$", re.I), "Make MLB Playoffs"),

    # World Series Matchup
    (re.compile(r"^MLB\s+Championship\s+Series\s+Matchup\s*$", re.I),
     "World Series Matchup"),

    # Streaks
    (re.compile(r"^Longest\s+(?:regular\s+season\s+)?(winning|losing)\s+streak\s*$", re.I),
     r"Longest \1 Streak"),

    # ── NCAA ─────────────────────────────────────────────────────────────

    # NCAA Championship
    (re.compile(r"^NCAAB\s+Champ(?:ion(?:ship)?)?\s*(?:Winner)?\s*$", re.I), "NCAAB Champion"),
    (re.compile(r"^NCAA\s+Tournament\s+Winner\s*$", re.I), "NCAA Champion"),

    # NCAA Tournament advancement (Polymarket style)
    (re.compile(r"^NCAA\s+Tournament:\s+Team\s+to\s+make\s+Semifinals?\s*$", re.I),
     "Make Final Four"),
    (re.compile(r"^NCAA\s+Tournament:\s+Team\s+to\s+make\s+National\s+Championship\s*$", re.I),
     "Make Championship Game"),
    (re.compile(r"^NCAA\s+Tournament:\s+Team\s+to\s+make\s+Sweet\s+Sixteen\s*$", re.I),
     "Make Sweet Sixteen"),

    # NCAA Tournament awards
    (re.compile(r"^(?:NCAA\s+Tournament:\s+)?Most\s+Outstanding\s+Player\s*$", re.I),
     "Most Outstanding Player"),
    (re.compile(
        r"^(?:Men's\s+)?College\s+Basketball\s+(?:Tournament\s+)?Most\s+Outstanding\s+Player\s*$",
        re.I),
     "Most Outstanding Player"),

    # Naismith awards
    (re.compile(
        r"^(?:College\s+Basketball\s+)?Naismith\s+(?:College\s+)?Player\s+of\s+the\s+Year\s*$",
        re.I),
     "Naismith Player of the Year"),
    (re.compile(
        r"^(?:NCAAM:\s+)?Naismith\s+Defensive\s+Player\s+of\s+the\s+Year\s*$", re.I),
     "Naismith DPOY"),

    # NCAA seeding
    (re.compile(r"^Men's\s+(\d+)\s+Seed\s*$", re.I), r"#\1 Seed"),

    # NCAA bracket rounds (Kalshi "Men's X Qualifiers" style) — keep as "Men's X"
    (re.compile(
        r"^(Men's|Women's)\s+(Round\s+of\s+\d+|Semifinals|Championship\s+Game)"
        r"\s*(?:Qualifiers?)?\s*$", re.I),
     r"\1 \2"),

    # "Team to Score the Most Points in ..." (tournament novelty prop)
    (re.compile(r"^Team\s+to\s+Score\s+the\s+Most\s+Points\s+in\s+the\s+(.+?)\s*$", re.I),
     r"Most Points in \1"),

    # ── Generic (all sports) ─────────────────────────────────────────────

    # Trade rumors (handle trailing "?")
    (re.compile(r"^(.+?)['\u2019]s?\s+[Nn]ext\s+[Tt]eam\??\s*$", re.I),
     r"\1 Trade Destination"),

    # Novelty
    (re.compile(r"^Who will be on the cover of NBA 2K\d+\??\s*$", re.I), "NBA 2K Cover"),
    (re.compile(r"^(.+?) play together on (.+?) again\??\s*$", re.I),
     r"\1 Stay in \2?"),

    # "When will X make/break/reach his Nth..." → "X: Milestone Description"
    (re.compile(
        r"^When will (.+?) (?:make|hit|reach|break|score|get) "
        r"(?:his|her|their)\s+(\d+)(?:st|nd|rd|th)\s+(.+?)(?:\s+\(.*\))?\??\s*$",
        re.I),
     r"\1: \2th \3"),

    # "Will X break/set the record for..." → "X: Record Name"
    (re.compile(
        r"^Will (.+?) (?:break|set|beat) (?:the )?"
        r"(?:record|all-time record) (?:for )?(.+?)\??\s*$",
        re.I),
     r"\1: \2 Record"),
]

# Game prop detection: "Team at/vs Team: Stat" or "Team vs. Team" (bare moneyline)
_GAME_STAT_PROP_RE = re.compile(
    r".+\s+(?:at|vs\.?)\s+.+:\s*(?:1H\s+)?(?:O/U\s+\d|"
    r"Points|Rebounds|Assists|Steals|Blocks|Three\s*Pointers?|"
    r"Turnovers|Double\s*Doubles?|Triple\s*Doubles?|First\s+Half\s+Winner|"
    r"Spread|Total\s*Points?|Team\s*Totals?|Moneyline|"
    # Polymarket player prop format: "Player: Stat O/U X"
    r"[A-Z][a-z]+\s+[A-Z])",
    re.IGNORECASE,
)

# Bare "Team vs. Team" markets (Polymarket moneyline, no stat qualifier)
_BARE_MATCHUP_RE = re.compile(
    r"^[A-Z][\w\s.]+\s+vs\.?\s+[A-Z][\w\s.]+$",
    re.IGNORECASE,
)

# NCAA bracket round detection
_NCAA_ROUND_RE = re.compile(
    r"(?:Men's|Women's)\s+(?:Round\s+of\s+\d+|Semifinals|Championship\s+Game|"
    r"College\s+Basketball\s+Champion)",
    re.IGNORECASE,
)


# ── Category assignment ──────────────────────────────────────────────────

_CATEGORY_RULES: list[tuple[re.Pattern, str]] = [
    # Game props (highest priority — check before championship/conference patterns)
    (_GAME_STAT_PROP_RE, "game_prop"),
    (_BARE_MATCHUP_RE, "game_prop"),

    # NCAA bracket rounds
    (_NCAA_ROUND_RE, "ncaa"),

    # Trade destinations
    (re.compile(r"Trade Destination$|Next Team$|next team\??$", re.I), "trade"),

    # Novelty
    (re.compile(
        r"2K\s*Cover|play together|record.*three\s*pointer|breaking.*record|"
        r"Most Points in|Stay in .+\?|^\w.+:\s+\d+th\s+",
        re.I,
    ), "novelty"),

    # Playoff path (check specific before general)
    (re.compile(r"Champion$", re.I), "playoff_path"),
    (re.compile(r"Conference Champion$", re.I), "playoff_path"),
    (re.compile(r"^Make\s+", re.I), "playoff_path"),
    (re.compile(r"Playoff\s+(Qualifiers|Teams)", re.I), "playoff_path"),
    (re.compile(r"Play-In", re.I), "playoff_path"),
    (re.compile(r"#\d+\s+Seed", re.I), "playoff_path"),

    # Conference (must be before awards — "Conf Finals MVP" is conference, not award)
    (re.compile(r"Conf(?:erence)? Finals\b", re.I), "conference"),
    (re.compile(r"(?:NBA|World Series|Championship Series)\s+(?:Finals\s+)?Matchup", re.I),
     "conference"),

    # Awards — NHL trophies, NBA awards, NCAA awards, draft picks
    (re.compile(
        r"\bMVP\b|\bDPOY\b|\b6MOY\b|\bMIP\b|\bROY\b|Clutch Player|"
        r"All-NBA|All-Defensive|"
        r"Hart Trophy|Norris Trophy|Vezina Trophy|Calder Trophy|"
        r"Art Ross Trophy|Rocket Richard|Selke Trophy|Conn Smythe|"
        r"Most Outstanding Player|Naismith|"
        r"NBA Draft",
        re.I,
    ), "award"),

    # Season stats
    (re.compile(
        r"PPG|RPG|APG|SPG|BPG|3PM|Per Game Leader|"
        r"Best Record|Worst Record|Win Total|Win Streak|Division Winner|"
        r"Presidents['\u2019]?\s+Trophy|"
        r"Longest .+ Streak|"
        r"(AL|NL)\s+(East|West|Central)\s+Winner",
        re.I,
    ), "season_stat"),
]


# ── Merge group assignment ───────────────────────────────────────────────

_MERGE_RULES: list[tuple[re.Pattern, str]] = [
    # NBA
    (re.compile(r"NBA Champion", re.I), "nba_champion"),
    (re.compile(r"(Eastern|Western) Conference Champion", re.I), r"\1_conf_champion"),
    (re.compile(r"Make NBA Playoffs|NBA Playoff Qualifiers", re.I), "make_playoffs"),
    (re.compile(r"(Eastern|Western) Conference #1 Seed", re.I), r"\1_conf_1_seed"),
    (re.compile(r"(Eastern|Western) Conference Play-In", re.I), r"\1_conf_playin"),
    (re.compile(r"^MVP$", re.I), "mvp"),
    (re.compile(r"^Finals MVP$", re.I), "finals_mvp"),
    (re.compile(r"^DPOY$", re.I), "dpoy"),
    (re.compile(r"^6MOY$", re.I), "6moy"),
    (re.compile(r"^MIP$", re.I), "mip"),
    (re.compile(r"^ROY$", re.I), "roy"),
    (re.compile(r"^Clutch Player$", re.I), "clutch_player"),
    (re.compile(r"^PPG Leader$", re.I), "ppg_leader"),
    (re.compile(r"^RPG Leader$", re.I), "rpg_leader"),
    (re.compile(r"^APG Leader$", re.I), "apg_leader"),
    (re.compile(r"^SPG Leader$", re.I), "spg_leader"),
    (re.compile(r"^BPG Leader$", re.I), "bpg_leader"),
    (re.compile(r"^3PM Leader$", re.I), "3pm_leader"),
    (re.compile(r"^Best Record$", re.I), "best_record"),
    (re.compile(r"^Worst Record$", re.I), "worst_record"),
    (re.compile(r"Win Total$", re.I), "win_total"),
    (re.compile(r"(\w+) Division Winner", re.I), r"\1_division"),
    (re.compile(r"(Eastern|Western) Conference Finals Matchup", re.I),
     r"\1_conf_finals_matchup"),
    (re.compile(r"NBA Finals Matchup", re.I), "nba_finals_matchup"),
    (re.compile(r"(Eastern|Western) Conf Finals MVP", re.I), r"\1_conf_finals_mvp"),
    (re.compile(r"All-NBA (\d)", re.I), r"all_nba_\1"),
    (re.compile(r"All-Defensive (\d)", re.I), r"all_def_\1"),
    (re.compile(r"NBA Draft #?(\d+)\w*\s+Pick", re.I), r"nba_draft_\1"),

    # Trade destinations (per-player merge group)
    (re.compile(r"^(.+?)\s+Trade Destination$", re.I), r"\1_trade"),

    # NFL
    (re.compile(r"Super Bowl Champion", re.I), "nfl_champion"),
    (re.compile(r"(AFC|NFC) Champion", re.I), r"\1_champion"),
    (re.compile(r"Super Bowl Matchup", re.I), "super_bowl_matchup"),
    (re.compile(r"Make NFL Playoffs", re.I), "make_nfl_playoffs"),
    (re.compile(r"^NFL MVP$", re.I), "nfl_mvp"),

    # NHL
    (re.compile(r"Stanley Cup Champion", re.I), "stanley_cup_champion"),
    (re.compile(r"Stanley Cup Matchup", re.I), "stanley_cup_matchup"),
    (re.compile(r"Make NHL Playoffs", re.I), "make_nhl_playoffs"),
    (re.compile(r"^Hart Trophy$", re.I), "hart_trophy"),
    (re.compile(r"^Norris Trophy$", re.I), "norris_trophy"),
    (re.compile(r"^Vezina Trophy$", re.I), "vezina_trophy"),
    (re.compile(r"^Calder Trophy$", re.I), "calder_trophy"),
    (re.compile(r"^Art Ross Trophy$", re.I), "art_ross_trophy"),
    (re.compile(r"^Rocket Richard Trophy$", re.I), "rocket_richard_trophy"),
    (re.compile(r"^Selke Trophy$", re.I), "selke_trophy"),
    (re.compile(r"^Conn Smythe Trophy$", re.I), "conn_smythe_trophy"),
    (re.compile(r"^Presidents['\u2019]?\s+Trophy$", re.I), "presidents_trophy"),

    # MLB
    (re.compile(r"World Series Champion", re.I), "world_series_champion"),
    (re.compile(r"^AL Champion$", re.I), "al_champion"),
    (re.compile(r"^NL Champion$", re.I), "nl_champion"),
    (re.compile(r"Make MLB Playoffs", re.I), "make_mlb_playoffs"),
    (re.compile(r"World Series Matchup", re.I), "world_series_matchup"),
    (re.compile(r"^(AL|NL)\s+(East|West|Central)\s+Winner$", re.I), r"\1_\2"),

    # NCAA
    (re.compile(r"NCAA(?:B)? Champion", re.I), "ncaa_champion"),
    (re.compile(r"Make Final Four", re.I), "make_final_four"),
    (re.compile(r"Make Championship Game", re.I), "make_championship_game"),
    (re.compile(r"Make Sweet Sixteen", re.I), "make_sweet_sixteen"),
    (re.compile(r"^Most Outstanding Player$", re.I), "most_outstanding_player"),
    (re.compile(r"^Naismith Player of the Year$", re.I), "naismith_poty"),
    (re.compile(r"^Naismith DPOY$", re.I), "naismith_dpoy"),
]


def normalize_market_label(raw_name: str) -> str:
    """Clean a raw market name into a human-readable label."""
    label = raw_name.strip()

    # Step 1: Rewrite "Pro Basketball/Football/etc." → league name
    for pat, repl in _PRO_SPORT_REWRITES:
        label = pat.sub(repl, label)

    # Step 2: Strip league:year prefix ("MLB: 2026 ...", "NHL: ...")
    label = _LEAGUE_PREFIX_RE.sub("", label)

    # Step 3: Strip standalone year prefix ("2026 ...", "2025-2026 ...")
    label = _YEAR_PREFIX_RE.sub("", label)

    label = label.strip()

    # Step 4: Apply specific label rewrites (these handle suffixes internally)
    for pat, repl in _LABEL_REWRITES:
        m = pat.match(label)
        if m:
            label = m.expand(repl)
            return label.strip()

    # Step 5: Don't strip suffixes from game props (e.g., "Team vs Team: First Half Winner")
    if _GAME_STAT_PROP_RE.search(label):
        return label.strip()

    # Step 6: Only strip verbose suffixes if no specific rewrite matched
    for pat, repl in _VERBOSE_SUFFIXES:
        label = pat.sub(repl, label)

    label = label.strip()

    # Step 7: Truncate very long labels (novelty/misc) at a word boundary
    if len(label) > 60:
        truncated = label[:57]
        # Cut at last space to avoid breaking mid-word
        last_space = truncated.rfind(" ")
        if last_space > 30:
            truncated = truncated[:last_space]
        label = truncated.rstrip(".,;: ") + "…"

    return label


def classify_market_category(
    clean_label: str,
    raw_name: str = "",
    market_category: str = "",
) -> str:
    """Assign a structured category to a market based on its clean label."""
    # Check clean label first
    for pat, cat in _CATEGORY_RULES:
        if pat.search(clean_label):
            return cat

    # Check raw name as fallback
    if raw_name and raw_name != clean_label:
        for pat, cat in _CATEGORY_RULES:
            if pat.search(raw_name):
                return cat

    # Use existing category from DB if available
    if market_category in ("game_prop", "championship", "award"):
        return market_category

    logger.debug("Unclassified market (category=other): clean=%r raw=%r", clean_label, raw_name)
    return "other"


def get_merge_group(clean_label: str) -> Optional[str]:
    """Get the merge group key for a clean label.

    Markets with the same merge group represent the same thing across
    different sources and should be aggregated into a single display item.
    """
    for pat, repl in _MERGE_RULES:
        m = pat.search(clean_label)
        if m:
            result = m.expand(repl)
            return result.lower().replace(" ", "_")
    return None


def is_wrong_sport_leak(
    raw_name: str,
    outcome_name: str,
    event_sport_key: str,
) -> bool:
    """Detect if a market leaked in from a different sport."""
    if not event_sport_key:
        return False

    sport_prefix = event_sport_key.split("_")[0]

    # ── NCAA bracket rounds in non-NCAA games ────────────────────────────
    if sport_prefix != "basketball" or "_ncaa" not in event_sport_key:
        if _NCAA_ROUND_RE.search(raw_name):
            return True
        if re.search(r"College Basketball Champion", raw_name, re.I):
            return True
        if re.search(r"NCAAB Championship", raw_name, re.I):
            return True
        if re.search(r"NCAA Tournament", raw_name, re.I):
            return True
        if re.search(r"Naismith", raw_name, re.I):
            return True

    # ── NHL teams leaking into NBA/NCAA via conference markets ───────────
    if sport_prefix == "basketball":
        _NHL_TEAMS = {
            "bruins", "rangers", "maple leafs", "canadiens", "penguins",
            "capitals", "flyers", "devils", "islanders", "hurricanes",
            "panthers", "lightning", "red wings", "senators", "sabres",
            "blue jackets", "blackhawks", "blues", "predators", "stars",
            "wild", "avalanche", "jets", "flames", "oilers", "canucks",
            "kraken", "coyotes", "sharks", "golden knights", "ducks",
            "utah hockey club",
        }
        outcome_lower = outcome_name.lower()
        for team in _NHL_TEAMS:
            if team in outcome_lower:
                return True

    # ── AHL / College Hockey leaking into NHL games ──────────────────────
    if "icehockey" in event_sport_key and "_nhl" in event_sport_key:
        if re.search(r"\bAHL\b|College Hockey", raw_name, re.I):
            return True

    # ── College Baseball leaking into MLB games ──────────────────────────
    if "baseball" in event_sport_key and "_mlb" in event_sport_key:
        if re.search(r"College Baseball", raw_name, re.I):
            return True

    # ── NBA conference markets leaking into NCAA games ───────────────────
    if "_ncaa" in event_sport_key:
        if re.search(r"(Eastern|Western) Conference Finals Winner", raw_name, re.I):
            return True

    return False


# ── Playoff stage classification ─────────────────────────────────────────
# Single source of truth for playoff stage names and ordering.
# Frontends should use these pre-computed values instead of re-deriving.
# Priority order matters: conference MUST be checked before championship
# to prevent "Eastern Conference Champion" matching "champion" first.

_PLAYOFF_STAGE_RULES: list[tuple[re.Pattern, str, int]] = [
    # Priority 1: Conference (checked FIRST — "Eastern Conference Champion" is conference, not championship)
    # Includes "\bAL\b" and "\bNL\b" for MLB pennant (American/National League Champion)
    (re.compile(r"conference|eastern|western|afc|nfc|american\s+league|national\s+league|\bAL\b\s+champ|\bNL\b\s+champ", re.I),
     "conference", 4),
    # Priority 2: Championship
    (re.compile(r"championship|champion|title|finals|world\s+series|super\s+bowl|stanley\s+cup", re.I),
     "championship", 5),
    # Priority 3: Division
    (re.compile(r"division", re.I), "division", 3),
    # Priority 4: Play-In
    (re.compile(r"play[- ]?in", re.I), "play_in", 2),
    # Priority 5: Make Playoffs
    (re.compile(r"make\s+playoffs|playoff\s+berth|playoff\s+qualifiers|playoffs$", re.I),
     "playoffs", 1),
    # Priority 6: #1 Seed / Best Record
    (re.compile(r"#1\s+seed|top\s+seed|first\s+seed|best\s+record", re.I),
     "top_seed", 6),
]

# Extract specific conference/division name for display
_CONF_NAME_RE = re.compile(r"(eastern|western|afc|nfc|american|national|\bAL\b|\bNL\b)", re.I)
_DIV_NAME_RE = re.compile(r"([\w]+)\s+division", re.I)


def compute_playoff_stage(
    clean_label: str,
    raw_name: str = "",
) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """Compute playoff stage classification for a market.

    Returns (stage_type, stage_display_name, stage_order) or (None, None, None)
    if not a playoff-path market.

    stage_type: machine-readable key ("conference", "championship", "division", etc.)
    stage_display_name: human-readable label ("Eastern Champ", "Championship", "Atlantic Div")
    stage_order: sort order (1=Playoffs, 2=Play-In, 3=Division, 4=Conference, 5=Championship, 6=#1 Seed)
    """
    text = (clean_label or raw_name or "").lower()
    if not text:
        return None, None, None

    for pattern, stage_type, order in _PLAYOFF_STAGE_RULES:
        if pattern.search(text):
            # Compute display name based on stage type
            if stage_type == "conference":
                m = _CONF_NAME_RE.search(text)
                if m:
                    raw = m.group(1)
                    # Keep abbreviations uppercase (AL, NL, AFC, NFC)
                    if raw.upper() in ("AL", "NL", "AFC", "NFC"):
                        display = raw.upper() + " Champ"
                    else:
                        display = raw[0].upper() + raw[1:] + " Champ"
                else:
                    display = "Conference"
            elif stage_type == "championship":
                display = "Championship"
            elif stage_type == "division":
                m = _DIV_NAME_RE.search(text)
                if m and m.group(1).lower() not in ("the", "a", "win"):
                    display = m.group(1)[0].upper() + m.group(1)[1:] + " Div"
                else:
                    display = "Division"
            elif stage_type == "play_in":
                display = "Play-In"
            elif stage_type == "playoffs":
                display = "Playoffs"
            elif stage_type == "top_seed":
                display = "#1 Seed"
            else:
                display = clean_label or raw_name

            return stage_type, display, order

    return None, None, None


# ── Relevance filtering ──────────────────────────────────────────────────

CATEGORY_RELEVANCE_ORDER = [
    "playoff_path",
    "conference",
    "award",
    "season_stat",
    "game_prop",
    "trade",
    "novelty",
    "ncaa",
    "other",
]

CATEGORY_LIMITS = {
    "playoff_path": 8,
    "conference": 4,
    "award": 6,
    "season_stat": 4,
    "game_prop": 6,
    "trade": 3,
    "novelty": 2,
    "ncaa": 0,
    "other": 2,
}


# ── Market tier assignment ───────────────────────────────────────────────
# Moved from team_linking.py to co-locate all market classification logic.
# Tier = display priority/importance (1-5), orthogonal to category.

# Tier 1: Championship / title winner
_TIER_1_PATTERNS = [
    re.compile(r"\b(championship|champion|super.bowl|world.series|stanley.cup|nba.finals|title)\b", re.I),
    re.compile(r"\bwinner\b", re.I),  # Catch-all for "X Winner" markets
]

# Tier 2: Conference winner
_TIER_2_PATTERNS = [
    re.compile(r"\b(conference|eastern|western|afc|nfc|american.league|national.league)\b", re.I),
]

# Tier 3: Awards / MVP / individual honors
_TIER_3_PATTERNS = [
    re.compile(r"\b(mvp|rookie|defensive.player|sixth.man|most.improved|cy.young|heisman)\b", re.I),
    re.compile(r"\b(hart.trophy|vezina|calder|norris.trophy|selke|conn.smythe|ballon.d.or)\b", re.I),
    re.compile(r"\b(award|trophy|player.of.the.year|golden.boot|golden.glove)\b", re.I),
]

# Tier 4: Division winner
_TIER_4_PATTERNS = [
    re.compile(r"\b(division|atlantic|pacific|central|southeast|northwest|southwest)\b", re.I),
    re.compile(r"\b(al.east|al.west|al.central|nl.east|nl.west|nl.central)\b", re.I),
    re.compile(r"\b(afc.east|afc.west|afc.north|afc.south|nfc.east|nfc.west|nfc.north|nfc.south)\b", re.I),
    re.compile(r"\b(metropolitan|atlantic.division|pacific.division|central.division)\b", re.I),
    # Playoff qualification — progression step before championship
    re.compile(r"\bplayoff.qualif", re.I),
    re.compile(r"\bmake.(?:the.)?(?:playoffs|postseason)", re.I),
    re.compile(r"\b(?:playoff|postseason).berth", re.I),
]

_NON_SPORT_CATEGORIES = {
    "politics", "crypto", "economics", "entertainment", "tech",
    "weather", "geopolitics", "culture",
}


def compute_market_tier(market_name: str, category: Optional[str] = None,
                        sport_category: Optional[str] = None) -> int:
    """
    Assign a tier (1-5) to a futures market based on its name and category.

    Tiers:
        1 = Championship / title winner (highest relevance)
        2 = Conference winner / non-sports top-level
        3 = Awards / MVP / individual honors
        4 = Division winner
        5 = Props / other (lowest relevance)

    Non-sports markets (politics, crypto, entertainment, etc.) default to
    tier 2 since they have no championship/conference hierarchy — they're
    all top-level questions that should rank alongside major sports futures.

    Returns:
        Integer 1-5
    """
    name_lower = (market_name or "").lower()
    cat_lower = (category or "").lower()

    # Game props are always tier 5
    if cat_lower == "game_prop":
        return 5

    # Check category field first for quick classification
    if cat_lower == "mvp":
        return 3

    # Division check before championship — "Division Winner" contains "winner"
    # but should be tier 4, not tier 1
    for pattern in _TIER_4_PATTERNS:
        if pattern.search(name_lower):
            return 4

    # Conference check before championship — "Conference Winner" also contains "winner"
    for pattern in _TIER_2_PATTERNS:
        if pattern.search(name_lower):
            return 2

    # Awards check before championship — "MVP Award" also might match "winner"
    for pattern in _TIER_3_PATTERNS:
        if pattern.search(name_lower):
            return 3

    # Championship / title
    if cat_lower == "championship":
        return 1
    for pattern in _TIER_1_PATTERNS:
        if pattern.search(name_lower):
            return 1

    # Non-sports markets default to tier 2 (no hierarchy — all top-level)
    effective_category = (sport_category or category or "").lower()
    if effective_category in _NON_SPORT_CATEGORIES:
        return 2

    logger.debug("Unclassified market (tier=5): name=%r category=%r", market_name, category)
    return 5
