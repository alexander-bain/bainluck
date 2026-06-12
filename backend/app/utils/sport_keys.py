"""
Canonical sport key translation maps.

Every dict that translates between sport key formats (Odds API keys, ESPN paths,
StatPal identifiers, Kalshi tickers, LLM categories, win-prob model keys) lives
here.  Consumer modules import the dicts (or thin accessor functions) they need.

This module imports nothing from the rest of the codebase, so it cannot create
circular-import problems.
"""

from typing import Optional


# =============================================================================
# 1. SPORT_LEAGUE_MAP — Odds API key → ESPN (sport, league) tuple
# =============================================================================

SPORT_LEAGUE_MAP: dict[str, tuple[str, str]] = {
    # Football
    "americanfootball_nfl": ("football", "nfl"),
    "americanfootball_ncaaf": ("football", "college-football"),
    "americanfootball_cfl": ("football", "cfl"),
    # Basketball
    "basketball_nba": ("basketball", "nba"),
    "basketball_wnba": ("basketball", "wnba"),
    "basketball_ncaab": ("basketball", "mens-college-basketball"),
    "basketball_wncaab": ("basketball", "womens-college-basketball"),
    # Baseball
    "baseball_mlb": ("baseball", "mlb"),
    "baseball_mlb_preseason": ("baseball", "mlb"),
    # Hockey
    "icehockey_nhl": ("hockey", "nhl"),
    # Soccer
    "soccer_epl": ("soccer", "eng.1"),
    "soccer_usa_mls": ("soccer", "usa.1"),
    "soccer_uefa_champs_league": ("soccer", "uefa.champions"),
    "soccer_spain_la_liga": ("soccer", "esp.1"),
    "soccer_germany_bundesliga": ("soccer", "ger.1"),
    "soccer_italy_serie_a": ("soccer", "ita.1"),
    "soccer_france_ligue_one": ("soccer", "fra.1"),
    # Golf
    "golf_pga": ("golf", "pga"),
    "golf_lpga": ("golf", "lpga"),
    # Tennis
    "tennis_atp": ("tennis", "atp"),
    "tennis_wta": ("tennis", "wta"),
    # MMA
    "mma_ufc": ("mma", "ufc"),
    "mma_mixed_martial_arts": ("mma", "ufc"),
    # Lacrosse
    "lacrosse_ncaa": ("lacrosse", "mens-college-lacrosse"),
    "lacrosse_pll": ("lacrosse", "pll"),
    # Aussie Rules
    "aussierules_afl": ("australian-football", "afl"),
    "aussierules_other": ("australian-football", "other"),
    # College Baseball
    "baseball_ncaa": ("baseball", "college-baseball"),
    # UFL
    "americanfootball_ufl": ("football", "ufl"),
}


# =============================================================================
# 1b. EXPECTED_GAME_STATE_INDICATORS — how many distinct period/quarter/inning
#     labels we expect to see for a COMPLETED event in each sport.
#
#     Used by the admin dashboard to grade game-state data completeness.
#     int  → fixed-period sport (NFL = 4 quarters, NBA = 4, etc.)
#     None → variable-round sport (tennis, MMA, boxing, golf)
# =============================================================================

EXPECTED_GAME_STATE_INDICATORS: dict[str, int | None] = {
    # Football — 4 quarters
    "americanfootball_nfl": 4,
    "americanfootball_ncaaf": 4,
    "americanfootball_cfl": 4,
    "americanfootball_ufl": 4,
    # Basketball — 4 quarters (halves for college, but ESPN reports 2 halves)
    "basketball_nba": 4,
    "basketball_wnba": 4,
    "basketball_ncaab": 2,
    "basketball_wncaab": 2,
    # Baseball — 9 innings
    "baseball_mlb": 9,
    "baseball_mlb_preseason": 9,
    "baseball_ncaa": 9,
    # Hockey — 3 periods
    "icehockey_nhl": 3,
    # Soccer — 2 halves
    "soccer_epl": 2,
    "soccer_usa_mls": 2,
    "soccer_uefa_champs_league": 2,
    "soccer_spain_la_liga": 2,
    "soccer_germany_bundesliga": 2,
    "soccer_italy_serie_a": 2,
    "soccer_france_ligue_one": 2,
    # Lacrosse — 4 quarters
    "lacrosse_ncaa": 4,
    "lacrosse_pll": 4,
    # Aussie Rules — 4 quarters
    "aussierules_afl": 4,
    "aussierules_other": 4,
    # Variable-round sports
    "golf_pga": None,
    "golf_lpga": None,
    "tennis_atp": None,
    "tennis_wta": None,
    "mma_ufc": None,
    "mma_mixed_martial_arts": None,
    # confirm after first render
    "boxing_boxing": None,
    "cricket_ipl": None,
    "baseball_kbo": None,
    "baseball_milb": None,
}


# =============================================================================
# 2. ESPN_SPORT_MAPPING — Odds API key → ESPN path string ("sport/league")
# =============================================================================

ESPN_SPORT_MAPPING: dict[str, str] = {
    "basketball_nba": "basketball/nba",
    "basketball_ncaab": "basketball/mens-college-basketball",
    "basketball_wncaab": "basketball/womens-college-basketball",
    "americanfootball_nfl": "football/nfl",
    "americanfootball_ncaaf": "football/college-football",
    "icehockey_nhl": "hockey/nhl",
    "baseball_mlb": "baseball/mlb",
    "baseball_mlb_preseason": "baseball/mlb",
    "soccer_usa_mls": "soccer/usa.1",
    "soccer_epl": "soccer/eng.1",
    # New — match SPORT_LEAGUE_MAP coverage for live sync correction
    "basketball_wnba": "basketball/wnba",
    "americanfootball_cfl": "football/cfl",
    "soccer_uefa_champs_league": "soccer/uefa.champions",
    "golf_pga": "golf/pga",
    "golf_lpga": "golf/lpga",
    # Additional European soccer leagues
    "soccer_spain_la_liga": "soccer/esp.1",
    "soccer_germany_bundesliga": "soccer/ger.1",
    "soccer_italy_serie_a": "soccer/ita.1",
    "soccer_france_ligue_one": "soccer/fra.1",
    # Lacrosse
    "lacrosse_ncaa": "lacrosse/mens-college-lacrosse",
    "lacrosse_pll": "lacrosse/pll",
    # MMA
    "mma_mixed_martial_arts": "mma/ufc",
    # Aussie Rules
    "aussierules_afl": "australian-football/afl",
    "aussierules_other": "australian-football/other",
    # College Baseball
    "baseball_ncaa": "baseball/college-baseball",
    # UFL
    "americanfootball_ufl": "football/ufl",
}


# =============================================================================
# 3. STATPAL_SPORT_MAPPING — Odds API key → StatPal identifier
# =============================================================================

STATPAL_SPORT_MAPPING: dict[str, str] = {
    "americanfootball_nfl": "nfl",
    "basketball_nba": "nba",
    "baseball_mlb": "mlb",
    "icehockey_nhl": "nhl",
    "soccer_epl": "soccer",
    "soccer_usa_mls": "soccer",
    "golf_pga": "pga",
    # Note: StatPal does NOT cover college sports (NCAAB, NCAAF) or WNBA.
    # Their API only supports 13 pro/international sports:
    # NFL, NBA, MLB, NHL, soccer, golf, cricket, esports, F1, handball,
    # horse racing, tennis, volleyball. College sports rely on
    # The Odds API + ESPN for event creation and commence_time correction.
    # More soccer leagues (StatPal uses sport="soccer" for all)
    "soccer_spain_la_liga": "soccer",
    "soccer_germany_bundesliga": "soccer",
    "soccer_italy_serie_a": "soccer",
    "soccer_france_ligue_one": "soccer",
    "soccer_uefa_champs_league": "soccer",
    # Tennis (ATP + WTA both use StatPal sport="tennis")
    "tennis_atp": "tennis",
    "tennis_wta": "tennis",
}

# Sports where StatPal actually provides play-by-play data.
# Other sports return 404 for the PBP endpoint — skip them to save API calls.
STATPAL_PBP_SPORTS: set[str] = {"nfl"}


# =============================================================================
# 4. ODDS_API_TO_WIN_PROB_KEY — Odds API key → win-prob model key
# =============================================================================

ODDS_API_TO_WIN_PROB_KEY: dict[str, str] = {
    "americanfootball_nfl": "football_nfl",
    "americanfootball_ncaaf": "football_ncaaf",
    "icehockey_nhl": "hockey_nhl",
}


# =============================================================================
# 5. SPORT_PREFIX_TO_LLM_CATEGORY — sport key prefix → LLM category
# =============================================================================

SPORT_PREFIX_TO_LLM_CATEGORY: dict[str, str] = {
    "americanfootball": "football",
    "basketball": "basketball",
    "icehockey": "hockey",
    "baseball": "baseball",
    "soccer": "soccer",
    "mma": "mma",
    "golf": "golf",
    "tennis": "tennis",
    "cricket": "cricket",
    "rugby": "rugby",
    "boxing": "boxing",
    "esports": "esports",
    "lacrosse": "lacrosse",
    "aussierules": "aussierules",
    "curling": "curling",
    "fieldhockey": "fieldhockey",
    "motorsport": "motorsports",
}


# =============================================================================
# 6. LLM_CATEGORY_TO_SPORT_PREFIX — LLM category → sport key prefix
# =============================================================================

LLM_CATEGORY_TO_SPORT_PREFIX: dict[str, str] = {
    "basketball": "basketball",
    "football": "americanfootball",
    "soccer": "soccer",
    "hockey": "icehockey",
    "baseball": "baseball",
    "golf": "golf",
    "tennis": "tennis",
    "mma": "mma",
    "boxing": "boxing",
    "cricket": "cricket",
    "rugby": "rugby",
    "motorsports": "motorsport",
    "lacrosse": "lacrosse",
    "esports": "esports",
    "aussierules": "aussierules",
    "olympics": "olympics",
}


# =============================================================================
# 7. KALSHI_TICKER_TO_SPORT_KEY — Kalshi ticker prefix → Odds API sport key
# =============================================================================

KALSHI_TICKER_TO_SPORT_KEY: dict[str, str] = {
    # Major US sports — moneyline
    "kxnbagame": "basketball_nba",
    "kxnflgame": "americanfootball_nfl",
    "kxnhlgame": "icehockey_nhl",
    "kxmlbgame": "baseball_mlb",
    "kxwnbagame": "basketball_wnba",
    "kxmlsgame": "soccer_usa_mls",
    # NBA game-level props (spread, total, halves, quarters, player props)
    "kxnbaspread": "basketball_nba",          # Game spread
    "kxnbatotal": "basketball_nba",           # Game total points
    "kxnbateamtotal": "basketball_nba",       # Team total points
    "kxnba1hwinner": "basketball_nba",        # 1st half winner
    "kxnba1hspread": "basketball_nba",        # 1st half spread
    "kxnba1htotal": "basketball_nba",         # 1st half total
    "kxnba2hwinner": "basketball_nba",        # 2nd half winner
    "kxnba2hspread": "basketball_nba",        # 2nd half spread
    "kxnba2htotal": "basketball_nba",         # 2nd half total
    "kxnba1qwinner": "basketball_nba",        # 1st quarter winner
    "kxnba1qspread": "basketball_nba",        # 1st quarter spread
    "kxnba1qtotal": "basketball_nba",         # 1st quarter total
    "kxnba2qwinner": "basketball_nba",        # 2nd quarter winner
    "kxnba2qspread": "basketball_nba",        # 2nd quarter spread
    "kxnba2qtotal": "basketball_nba",         # 2nd quarter total
    "kxnba3qwinner": "basketball_nba",        # 3rd quarter winner
    "kxnba3qspread": "basketball_nba",        # 3rd quarter spread
    "kxnba3qtotal": "basketball_nba",         # 3rd quarter total
    "kxnba4qwinner": "basketball_nba",        # 4th quarter winner
    "kxnba4qspread": "basketball_nba",        # 4th quarter spread
    "kxnba4qtotal": "basketball_nba",         # 4th quarter total
    "kxnbapts": "basketball_nba",             # Player points props
    "kxnbaast": "basketball_nba",             # Player assists props
    "kxnbareb": "basketball_nba",             # Player rebounds props
    "kxnbablk": "basketball_nba",             # Player blocks props
    "kxnbastl": "basketball_nba",             # Player steals props
    "kxnba3pt": "basketball_nba",             # Player threes props
    "kxnbapa": "basketball_nba",              # Points + Assists combo
    "kxnbapr": "basketball_nba",              # Points + Rebounds combo
    "kxnbapra": "basketball_nba",             # Points + Rebounds + Assists
    "kxnbara": "basketball_nba",              # Rebounds + Assists combo
    "kxnba2d": "basketball_nba",              # Double-double
    "kxnba3d": "basketball_nba",              # Triple-double
    "kxnbafirstbasket": "basketball_nba",     # First basket scorer
    "kxnbamention": "basketball_nba",         # Announcer mention props
    # NFL game-level props (spread, total, halves, quarters, player props)
    "kxnflspread": "americanfootball_nfl",           # Game spread
    "kxnfltotal": "americanfootball_nfl",            # Game total points
    "kxnflteamtotal": "americanfootball_nfl",        # Team total points
    "kxnfl1hwinner": "americanfootball_nfl",         # 1st half winner
    "kxnfl1hspread": "americanfootball_nfl",         # 1st half spread
    "kxnfl1htotal": "americanfootball_nfl",          # 1st half total
    "kxnfl2hwinner": "americanfootball_nfl",         # 2nd half winner
    "kxnfl2hspread": "americanfootball_nfl",         # 2nd half spread
    "kxnfl2htotal": "americanfootball_nfl",          # 2nd half total
    "kxnfl1qwinner": "americanfootball_nfl",         # 1st quarter winner
    "kxnfl1qspread": "americanfootball_nfl",         # 1st quarter spread
    "kxnfl1qtotal": "americanfootball_nfl",          # 1st quarter total
    "kxnfl2qwinner": "americanfootball_nfl",         # 2nd quarter winner
    "kxnfl2qspread": "americanfootball_nfl",         # 2nd quarter spread
    "kxnfl2qtotal": "americanfootball_nfl",          # 2nd quarter total
    "kxnfl3qwinner": "americanfootball_nfl",         # 3rd quarter winner
    "kxnfl3qspread": "americanfootball_nfl",         # 3rd quarter spread
    "kxnfl3qtotal": "americanfootball_nfl",          # 3rd quarter total
    "kxnfl4qwinner": "americanfootball_nfl",         # 4th quarter winner
    "kxnfl4qspread": "americanfootball_nfl",         # 4th quarter spread
    "kxnfl4qtotal": "americanfootball_nfl",          # 4th quarter total
    "kxnflpasstds": "americanfootball_nfl",          # Player passing TDs
    "kxnflpassyds": "americanfootball_nfl",          # Player passing yards
    "kxnflrecyds": "americanfootball_nfl",           # Player receiving yards
    "kxnflrshyds": "americanfootball_nfl",           # Player rushing yards
    "kxnflrec": "americanfootball_nfl",              # Player receptions
    "kxnflanytd": "americanfootball_nfl",            # Anytime TD scorer
    "kxnflfirsttd": "americanfootball_nfl",          # First TD scorer
    "kxnflnexttd": "americanfootball_nfl",           # Next TD scorer
    "kxnflteamfirsttd": "americanfootball_nfl",      # Team first TD
    "kxnfl2td": "americanfootball_nfl",              # Multiple TDs
    "kxnflfirsttdtime": "americanfootball_nfl",      # First TD time
    "kxnflgamefg": "americanfootball_nfl",           # Game field goals
    "kxnflgamesack": "americanfootball_nfl",         # Game sacks
    "kxnflgametd": "americanfootball_nfl",           # Game touchdowns
    "kxnflgameto": "americanfootball_nfl",           # Game turnovers
    "kxnflot": "americanfootball_nfl",               # Overtime
    "kxnflwinmargin": "americanfootball_nfl",        # Win margin
    "kxnfldsttd": "americanfootball_nfl",            # D/ST touchdown
    "kxnflsafety": "americanfootball_nfl",           # Safeties
    "kxnflhighscoreq": "americanfootball_nfl",       # Highest scoring quarter
    "kxnflnoscoreq": "americanfootball_nfl",         # Scoreless quarter
    "kxnfllargelead": "americanfootball_nfl",        # Largest lead
    "kxnfllargestlead": "americanfootball_nfl",      # Largest lead (alt)
    "kxnflleadchange": "americanfootball_nfl",       # Lead changes
    "kxnfllongesttd": "americanfootball_nfl",        # Longest TD
    "kxnflshortesttd": "americanfootball_nfl",       # Shortest TD
    "kxnflmostrecyds": "americanfootball_nfl",       # Most receiving yards
    "kxnflmostrshyds": "americanfootball_nfl",       # Most rushing yards
    "kxnflnonqbpass": "americanfootball_nfl",        # Non-QB passes
    "kxnfl2ptconv": "americanfootball_nfl",          # 2-point conversions
    "kxnfl4dconv": "americanfootball_nfl",           # 4th down conversions
    "kxnfl4downconv": "americanfootball_nfl",        # 4th down conversions (alt)
    "kxnflcombo": "americanfootball_nfl",            # Combo props
    "kxnflprepack": "americanfootball_nfl",          # Pre-pack bundles
    "kxnflmention": "americanfootball_nfl",          # Announcer mention props
    # NHL game-level props
    "kxnhlspread": "icehockey_nhl",                  # Game spread (puck line)
    "kxnhltotal": "icehockey_nhl",                   # Game goal total
    "kxnhl1hwinner": "icehockey_nhl",                # 1st half winner
    "kxnhl1hspread": "icehockey_nhl",                # 1st half spread
    "kxnhl1htotal": "icehockey_nhl",                 # 1st half total
    "kxnhl2hwinner": "icehockey_nhl",                # 2nd half winner
    "kxnhl2hspread": "icehockey_nhl",                # 2nd half spread
    "kxnhl2htotal": "icehockey_nhl",                 # 2nd half total
    "kxnhlanygoal": "icehockey_nhl",                 # Anytime goal scorer
    "kxnhlgoal": "icehockey_nhl",                    # Goal scorer props
    "kxnhlfirstgoal": "icehockey_nhl",               # First goal scorer
    "kxnhlpts": "icehockey_nhl",                     # Player points props
    "kxnhlast": "icehockey_nhl",                     # Player assists props
    "kxnhlsaves": "icehockey_nhl",                   # Goalie saves props
    "kxnhlmention": "icehockey_nhl",                  # Announcer mention props
    # MLB game-level props
    "kxmlbspread": "baseball_mlb",                   # Game spread (run line)
    "kxmlbtotal": "baseball_mlb",                    # Game total runs
    "kxmlbteamtotal": "baseball_mlb",                # Team total runs
    "kxmlb1hwinner": "baseball_mlb",                 # 1st half winner
    "kxmlb1hspread": "baseball_mlb",                 # 1st half spread
    "kxmlb1htotal": "baseball_mlb",                  # 1st half total
    "kxmlb2hwinner": "baseball_mlb",                 # 2nd half winner
    "kxmlb2hspread": "baseball_mlb",                 # 2nd half spread
    "kxmlb2htotal": "baseball_mlb",                  # 2nd half total
    "kxmlbf5": "baseball_mlb",                       # First 5 innings winner
    "kxmlbf5spread": "baseball_mlb",                 # First 5 innings spread
    "kxmlbf5total": "baseball_mlb",                  # First 5 innings total
    "kxmlbhit": "baseball_mlb",                      # Player hits props
    "kxmlbhr": "baseball_mlb",                       # Player home runs props
    "kxmlbks": "baseball_mlb",                       # Player strikeouts props
    "kxmlbtb": "baseball_mlb",                       # Player total bases props
    "kxmlbhrr": "baseball_mlb",                      # Hits + Runs + RBIs combo
    "kxmlbrfi": "baseball_mlb",                      # Run in first inning
    "kxmlbstgame": "baseball_mlb",                   # Spring training game
    "kxmlbmention": "baseball_mlb",                   # Announcer mention props
    # College sports — men's
    "kxncaabgame": "basketball_ncaab",
    "kxncaambgame": "basketball_ncaab",       # Men's college basketball game
    "kxncaamb1hwinner": "basketball_ncaab",   # 1st half winner
    "kxncaamb1hspread": "basketball_ncaab",   # 1st half spread
    "kxncaamb1htotal": "basketball_ncaab",    # 1st half total
    "kxncaamb2hwinner": "basketball_ncaab",   # 2nd half winner
    "kxncaamb2hspread": "basketball_ncaab",   # 2nd half spread
    "kxncaamb2htotal": "basketball_ncaab",    # 2nd half total
    "kxncaambspread": "basketball_ncaab",     # Game spread
    "kxncaambtotal": "basketball_ncaab",      # Game total
    "kxncaamb2ml": "basketball_ncaab",        # 2-game moneyline combo
    "kxncaambfirst10": "basketball_ncaab",    # Race to 10 points
    "kxncaambteammostpts": "basketball_ncaab",  # Team with most points
    # College baseball (NOT basketball — "BB" = baseball in Kalshi tickers)
    "kxncaabbgame": "baseball_ncaa",          # College baseball game
    "kxncaabbspread": "baseball_ncaa",        # College baseball spread
    "kxncaabbtotal": "baseball_ncaa",         # College baseball total runs
    # College football
    "kxncaafgame": "americanfootball_ncaaf",
    "kxncaaf1hwinner": "americanfootball_ncaaf",  # 1st half winner
    "kxncaaf1hspread": "americanfootball_ncaaf",  # 1st half spread
    "kxncaaf1htotal": "americanfootball_ncaaf",   # 1st half total
    "kxncaaf2hwinner": "americanfootball_ncaaf",  # 2nd half winner
    "kxncaaf2hspread": "americanfootball_ncaaf",  # 2nd half spread
    "kxncaaf2htotal": "americanfootball_ncaaf",   # 2nd half total
    "kxncaafspread": "americanfootball_ncaaf",    # Game spread
    "kxncaaftotal": "americanfootball_ncaaf",     # Game total
    "kxncaafteamtotal": "americanfootball_ncaaf", # Team total
    "kxncaafd3game": "americanfootball_ncaaf",    # D3 football game
    "kxncaafcsgame": "americanfootball_ncaaf",    # FCS football game
    "kxncaamlaxgame": "lacrosse_ncaa",
    "kxncaahockeygame": "icehockey_ncaa",
    # College sports — women's
    "kxncaawbgame": "basketball_wncaab",
    "kxncaawbspread": "basketball_wncaab",    # Women's basketball spread
    "kxncaawbtotal": "basketball_wncaab",     # Women's basketball total
    # Hockey leagues
    "kxahlgame": "icehockey_ahl",
    "kxkhlgame": "icehockey_other",
    "kxdelgame": "icehockey_other",           # DEL (German hockey)
    # MLS game-level props
    "kxmlsspread": "soccer_usa_mls",             # MLS spread
    "kxmlstotal": "soccer_usa_mls",              # MLS goal total
    "kxmlsbtts": "soccer_usa_mls",               # Both teams to score
    "kxmlsadvance": "soccer_usa_mls",            # To advance
    # Soccer game-level props
    "kxsoccerspread": "soccer",                  # Soccer spread
    "kxsoccertotal": "soccer",                   # Soccer goal total
    "kxsoccerbtts": "soccer",                    # Both teams to score
    # Soccer short-prefix game tickers (Kalshi uses both kxsoccer* and kxsoc*)
    "kxsocgame": "soccer_epl",                   # EPL game (short prefix)
    "kxsoctotal": "soccer_epl",                  # EPL goal total (short prefix)
    "kxsocbtts": "soccer_epl",                   # EPL both teams to score (short prefix)
    # Tennis
    "kxatpmatch": "tennis_atp",
    "kxatpchallengermatch": "tennis_atp",
    "kxatpsetwinner": "tennis_atp",
    "kxatpanyset": "tennis_atp",                 # Any set winner
    "kxatpexactmatch": "tennis_atp",             # Exact match score
    "kxatpexactsets": "tennis_atp",              # Exact sets
    "kxatpgamespread": "tennis_atp",             # Game spread
    "kxatpgspread": "tennis_atp",                # Game spread (alt ticker)
    "kxatpgametotal": "tennis_atp",              # Total games
    "kxatptotalsets": "tennis_atp",              # Total sets
    "kxatpdoubles": "tennis_atp",                # Doubles match
    "kxatpgame": "tennis_atp",                   # Match winner (by event)
    "kxwtamatch": "tennis_wta",
    "kxwtachallengermatch": "tennis_wta",         # WTA Challenger match
    "kxwtadoubles": "tennis_wta",                # WTA doubles match
    "kxwtagame": "tennis_wta",                   # WTA match winner (by event)
    # Combat sports
    "kxufcfight": "mma_mixed_martial_arts",
    "kxufcdistance": "mma_mixed_martial_arts",   # To go the distance
    "kxufcmof": "mma_mixed_martial_arts",        # Method of finish
    "kxufcmov": "mma_mixed_martial_arts",        # Method of victory
    "kxufcrounds": "mma_mixed_martial_arts",     # Total rounds
    "kxufcvicround": "mma_mixed_martial_arts",   # Round of victory
    "kxboxingfight": "boxing_boxing",
    "kxboxingdistance": "boxing_boxing",          # To go the distance
    "kxboxing1min": "boxing_boxing",              # 1 minute fight
    "kxboxingknockout": "boxing_boxing",          # Knockout
    "kxboxingmov": "boxing_boxing",               # Method of victory
    "kxboxingrounds": "boxing_boxing",            # Total rounds
    "kxboxingvicround": "boxing_boxing",          # Victory in round
    # Esports
    "kxlolgame": "esports",
    "kxlolgames": "esports",                    # LoL games in series
    "kxlolmap": "esports",                      # LoL map winner
    "kxloltotal": "esports",                    # LoL total maps
    "kxloltotalmaps": "esports",                # LoL total maps (alt)
    "kxcs2game": "esports",
    "kxcs2games": "esports",                    # CS2 games in series
    "kxcs2map": "esports",                      # CS2 map winner
    "kxcs2mapwinner": "esports",                # CS2 map winner (alt)
    "kxcs2totalmaps": "esports",                # CS2 total maps
    "kxvalorantgame": "esports",
    "kxvalorantmap": "esports",                 # Valorant map winner
    "kxdimayorgame": "soccer_other",             # Colombian Dimayor (NOT Dota 2)
    # Soccer
    "kxsoccergame": "soccer",
    "kxeculpgame": "soccer_other",            # Ecuadorian league
    "kxvenfutvegame": "soccer_other",         # Venezuelan league
    "kxapfddhgame": "soccer_other",           # Dominican league
    # Asian basketball
    "kxcbagame": "basketball_other",          # Chinese CBA
    "kxjbleaguegame": "basketball_other",     # Japanese B.League
    "kxarglnbgame": "basketball_other",       # Argentine LNB
    # Winter Olympics
    "kxwohockey": "icehockey_olympics",
    "kxwocurling": "curling_olympics",
    # Summer Olympics
    "kxsohockey": "fieldhockey_olympics",
    "kxsobasketball": "basketball_olympics",
    "kxsosoccer": "soccer_olympics",
}


# =============================================================================
# 8. KALSHI_GAME_TICKER_PREFIXES — tuple of Kalshi game ticker prefixes
# =============================================================================

# Leagues we ingest from The Odds API / StatPal / ESPN. Markets for other
# leagues (AHL, KHL, DEL, etc.) can never link because we have no events.
_UNSUPPORTED_LEAGUE_PREFIXES = frozenset({
    "kxahlgame", "kxkhlgame", "kxdelgame",
    "kxshlgame", "kxliigagame",
    "kxeculpgame", "kxvenfutvegame", "kxapfddhgame", "kxdimayorgame",
    "kxcbagame", "kxjbleaguegame", "kxarglnbgame",
})

KALSHI_GAME_TICKER_PREFIXES: tuple[str, ...] = tuple(
    k for k in KALSHI_TICKER_TO_SPORT_KEY.keys()
    if k not in _UNSUPPORTED_LEAGUE_PREFIXES
)

_LINK_RATE_UNSUPPORTED_LEAGUE_PREFIXES = frozenset({
    "kxlolgame", "kxlolgames", "kxlolmap", "kxloltotal", "kxloltotalmaps",
    "kxcs2game", "kxcs2games", "kxcs2map", "kxcs2mapwinner",
    "kxcs2totalmaps", "kxvalorantgame", "kxvalorantmap",
})

# Link-rate denominator prefixes are stricter than "game-shaped" tickers:
# esports markets are game-shaped, but this repo does not ingest esports events.
KALSHI_LINK_RATE_GAME_TICKER_PREFIXES: tuple[str, ...] = tuple(
    k for k in KALSHI_GAME_TICKER_PREFIXES
    if k not in _LINK_RATE_UNSUPPORTED_LEAGUE_PREFIXES
)


# =============================================================================
# 8b. KALSHI_FUTURES_TICKER_TO_SPORT_KEY — season/futures tickers → sport key
#     NOT in KALSHI_GAME_TICKER_PREFIXES (these are NOT game-level markets).
#     Used by get_sport_key_from_ticker() for sport classification of futures.
# =============================================================================

KALSHI_FUTURES_TICKER_TO_SPORT_KEY: dict[str, str] = {
    # NFL futures
    "kxnflmvp": "americanfootball_nfl",              # Regular season MVP
    "kxnfldpoty": "americanfootball_nfl",             # Defensive Player of the Year
    "kxnfldpoy": "americanfootball_nfl",              # DPOY (alt)
    "kxnflopoty": "americanfootball_nfl",             # Offensive Player of the Year
    "kxnflopoy": "americanfootball_nfl",              # OPOY (alt)
    "kxnfldroty": "americanfootball_nfl",             # Defensive Rookie of the Year
    "kxnfldroy": "americanfootball_nfl",              # DROY (alt)
    "kxnfloroty": "americanfootball_nfl",             # Offensive Rookie of the Year
    "kxnfloroy": "americanfootball_nfl",              # OROY (alt)
    "kxnflcpoty": "americanfootball_nfl",             # Comeback Player of the Year
    "kxnflcoach": "americanfootball_nfl",             # Coach of the Year
    "kxnflcoty": "americanfootball_nfl",              # COTY (alt)
    "kxnflasscoach": "americanfootball_nfl",          # Assistant Coach of the Year
    "kxnflcomeback": "americanfootball_nfl",          # Comeback award
    "kxnflsbmvp": "americanfootball_nfl",             # Super Bowl MVP
    "kxnflsbmvpdef": "americanfootball_nfl",          # Defensive SB MVP
    "kxnflsbmvppos": "americanfootball_nfl",          # SB MVP position
    "kxnflsbmvpqb": "americanfootball_nfl",           # Non-QB SB MVP
    "kxnflafcchamp": "americanfootball_nfl",          # AFC Champion
    "kxnflnfcchamp": "americanfootball_nfl",          # NFC Champion
    "kxnflafceast": "americanfootball_nfl",           # AFC East winner
    "kxnflafcnorth": "americanfootball_nfl",          # AFC North winner
    "kxnflafcsouth": "americanfootball_nfl",          # AFC South winner
    "kxnflafcwest": "americanfootball_nfl",           # AFC West winner
    "kxnflnfceast": "americanfootball_nfl",           # NFC East winner
    "kxnflnfcnorth": "americanfootball_nfl",          # NFC North winner
    "kxnflnfcsouth": "americanfootball_nfl",          # NFC South winner
    "kxnflnfcwest": "americanfootball_nfl",           # NFC West winner
    "kxnflplayoff": "americanfootball_nfl",           # Playoff qualifiers
    "kxnflwins": "americanfootball_nfl",              # Team win totals (all 32 teams)
    "kxnflexactwins": "americanfootball_nfl",         # Exact win totals
    "kxnfldraft": "americanfootball_nfl",             # Draft picks (all positions)
    "kxnflfirstpick": "americanfootball_nfl",         # First pick
    "kxnfltrade": "americanfootball_nfl",             # Trades
    "kxnflhirecoach": "americanfootball_nfl",         # Coach hiring
    "kxnflprobowl": "americanfootball_nfl",           # Pro Bowl
    "kxnflprobowlwin": "americanfootball_nfl",        # Pro Bowl game
    "kxnflprimetime": "americanfootball_nfl",         # Primetime games
    "kxnflcombine": "americanfootball_nfl",           # NFL Combine
    "kxnflcombine40": "americanfootball_nfl",         # Combine 40 time
    "kxnflcontractsize": "americanfootball_nfl",      # Contract size
    "kxnflfantasymost": "americanfootball_nfl",       # Most fantasy points
    "kxnflcelebritygame": "americanfootball_nfl",     # Celebrity flag football
    "kxnflreboot": "americanfootball_nfl",            # Reboot rules
    "kxnflredzoneads": "americanfootball_nfl",        # Redzone ads
    "kxnflredzonebrandads": "americanfootball_nfl",   # Redzone brand ads
    "kxnflrecydsrecord": "americanfootball_nfl",      # Receiving yards record
    "kxnflsackrecord": "americanfootball_nfl",        # Sack record
    "kxnflseasonhr": "americanfootball_nfl",          # Season stats
    "kxnfldepthposition": "americanfootball_nfl",     # Depth chart
    "kxnflgpickenscontract": "americanfootball_nfl",  # Pickens contract
    "kxnfl1ydpass": "americanfootball_nfl",           # 1 yard pass novelty
    # NFL cross-cutting tickers (don't start with "kxnfl")
    "kxcoachoutnfl": "americanfootball_nfl",          # Coach fired
    "kxnextcoachoutnfl": "americanfootball_nfl",      # Next coach fired
    "kxnextnflcoach": "americanfootball_nfl",         # Next coach hired
    "kxnextteamnfl": "americanfootball_nfl",          # Player next team
    "kxleadernfl": "americanfootball_nfl",            # Stat leaders (all categories)
    "kxrecordnfl": "americanfootball_nfl",            # Best/worst record
    "kxtradeoffnfl": "americanfootball_nfl",          # Offseason trades
    "kxphilipriversnfl": "americanfootball_nfl",      # Philip Rivers novelty
    # NBA futures
    "kxnba": "basketball_nba",                          # NBA Champion (broad prefix catches all)
    "kxnbamvp": "basketball_nba",                       # Regular season MVP
    "kxnbadpoy": "basketball_nba",                      # Defensive Player of the Year
    "kxnbadpoty": "basketball_nba",                     # DPOY (alt)
    "kxnbaroy": "basketball_nba",                       # Rookie of the Year
    "kxnbaroty": "basketball_nba",                      # ROY (alt)
    "kxnba6moy": "basketball_nba",                      # 6th Man of the Year
    "kxnba6moty": "basketball_nba",                     # 6MOY (alt)
    "kxnbamip": "basketball_nba",                       # Most Improved Player
    "kxnbamipy": "basketball_nba",                      # MIP (alt)
    "kxnbacoty": "basketball_nba",                      # Coach of the Year
    "kxnbacoach": "basketball_nba",                     # Coach of the Year (alt)
    "kxnbaeast": "basketball_nba",                      # Eastern Conference Champion
    "kxnbawest": "basketball_nba",                      # Western Conference Champion
    "kxnbaatlantic": "basketball_nba",                  # Atlantic Division
    "kxnbacentral": "basketball_nba",                   # Central Division
    "kxnbasoutheast": "basketball_nba",                 # Southeast Division
    "kxnbanorthwest": "basketball_nba",                 # Northwest Division
    "kxnbapacific": "basketball_nba",                   # Pacific Division
    "kxnbasouthwest": "basketball_nba",                 # Southwest Division
    "kxnbaplayoff": "basketball_nba",                   # Playoff qualifiers
    "kxnbawins": "basketball_nba",                      # Team win totals (all 30 teams)
    "kxnbaexactwins": "basketball_nba",                 # Exact win totals
    "kxnbaseries": "basketball_nba",                    # Playoff series
    "kxnbafinalmvp": "basketball_nba",                  # Finals MVP
    "kxnbafinalsmvp": "basketball_nba",                 # Finals MVP (alt)
    "kxnbadraft": "basketball_nba",                     # Draft picks
    "kxnbafirstpick": "basketball_nba",                 # First pick
    "kxnbatrade": "basketball_nba",                     # Trades
    "kxnbaallstar": "basketball_nba",                   # All-Star selections
    "kxnbaasg": "basketball_nba",                       # All-Star Game
    "kxnbaallnba": "basketball_nba",                    # All-NBA teams
    "kxnbascoringtitle": "basketball_nba",              # Scoring title
    "kxnbaassisttitle": "basketball_nba",               # Assists leader
    "kxnbareboundtitle": "basketball_nba",              # Rebounds leader
    "kxleadernba": "basketball_nba",                    # Stat leaders (all categories)
    "kxrecordnba": "basketball_nba",                    # Best/worst record
    "kxnextteamnba": "basketball_nba",                  # Player next team
    "kxcoachoutba": "basketball_nba",                   # Coach fired
    # WNBA futures
    "kxwnba": "basketball_wnba",                        # WNBA Champion
    "kxwnbamvp": "basketball_wnba",                     # WNBA MVP
    "kxwnbaroy": "basketball_wnba",                     # WNBA ROY
    "kxwnbaplayoff": "basketball_wnba",                 # WNBA Playoff qualifiers
    "kxwnbawins": "basketball_wnba",                    # WNBA win totals
    "kxwnbadraft": "basketball_wnba",                   # WNBA Draft
    # NHL futures
    "kxnhl": "icehockey_nhl",                         # Stanley Cup (broad prefix catches all)
    # More specific NHL futures for clarity:
    "kxnhlheart": "icehockey_nhl",                    # Hart Trophy (deprecated, use kxnhlhart)
    "kxnhlhart": "icehockey_nhl",                     # Hart Memorial Trophy
    "kxnhlnorris": "icehockey_nhl",                   # Norris Trophy
    "kxnhlvezina": "icehockey_nhl",                   # Vezina Trophy
    "kxnhlcalder": "icehockey_nhl",                   # Calder Trophy
    "kxnhlross": "icehockey_nhl",                     # Art Ross Trophy
    "kxnhlrichard": "icehockey_nhl",                  # Rocket Richard Trophy
    "kxnhladams": "icehockey_nhl",                    # Jack Adams Award
    "kxnhlpres": "icehockey_nhl",                     # President's Trophy
    "kxnhlmvp": "icehockey_nhl",                      # Hart Trophy (alt)
    "kxnhleast": "icehockey_nhl",                     # Eastern Conference
    "kxnhlwest": "icehockey_nhl",                     # Western Conference
    "kxnhlatlantic": "icehockey_nhl",                 # Atlantic Division
    "kxnhlcentral": "icehockey_nhl",                  # Central Division
    "kxnhlmetropolitan": "icehockey_nhl",             # Metropolitan Division
    "kxnhlpacific": "icehockey_nhl",                  # Pacific Division
    "kxnhlplayoff": "icehockey_nhl",                  # Playoff qualifiers
    "kxnhlseries": "icehockey_nhl",                   # Playoff series
    "kxnhlfinalsexact": "icehockey_nhl",              # Finals exact score
    "kxnhlwins": "icehockey_nhl",                     # Team win totals
    "kxnhl1stteam": "icehockey_nhl",                  # All-NHL First Team
    "kxnhl4nations": "icehockey_nhl",                 # 4 Nations Face Off
    # MLB futures
    "kxmlb": "baseball_mlb",                          # World Series (broad prefix)
    "kxmlbal": "baseball_mlb",                        # AL Championship + divisions + awards
    "kxmlbnl": "baseball_mlb",                        # NL Championship + divisions + awards
    "kxmlbplayoffs": "baseball_mlb",                  # Playoff qualifiers
    "kxmlbwins": "baseball_mlb",                      # Team win totals (all 30 teams)
    "kxmlb500": "baseball_mlb",                       # Teams at .500
    "kxmlbbestrecord": "baseball_mlb",                # Best record
    "kxmlbworstrecord": "baseball_mlb",               # Worst record
    "kxmlbdivwinner": "baseball_mlb",                 # Division winners
    "kxmlbasgame": "baseball_mlb",                    # All-Star Game
    "kxmlbhrderby": "baseball_mlb",                   # Home Run Derby
    "kxmlbseasonhr": "baseball_mlb",                  # Season home runs
    "kxmlbss": "baseball_mlb",                        # Silver Slugger
    "kxmlbstat": "baseball_mlb",                      # Season stats
    "kxmlbstatcount": "baseball_mlb",                 # Season stat counts
    "kxmlbseries": "baseball_mlb",                    # Playoff series
    "kxmlbseriesexact": "baseball_mlb",               # Series exact result
    "kxmlbseriesgametotal": "baseball_mlb",           # Series total games
    "kxmlbws": "baseball_mlb",                        # World Series (alt)
    "kxmlbwsmvp": "baseball_mlb",                     # WS MVP
    "kxmlbeoty": "baseball_mlb",                      # Executive of the Year
    "kxmlbtrade": "baseball_mlb",                     # Trades
    "kxmlblstreak": "baseball_mlb",                   # Longest losing streak
    "kxmlbwstreak": "baseball_mlb",                   # Longest winning streak
    "kxmlbworld": "baseball_mlb",                     # World Baseball Classic
    "kxleadermlb": "baseball_mlb",                    # Stat leaders (all categories)
    "kxnextteammlb": "baseball_mlb",                  # Player next team
    "kxcitymlbexpand": "baseball_mlb",                # Expansion city
    # NCAAF futures
    "kxncaaf": "americanfootball_ncaaf",              # Championship (broad prefix)
    "kxncaafacc": "americanfootball_ncaaf",           # ACC Champion
    "kxncaafb10": "americanfootball_ncaaf",           # Big Ten Champion
    "kxncaafb12": "americanfootball_ncaaf",           # Big 12 Champion
    "kxncaafbacc": "americanfootball_ncaaf",          # ACC Champion (alt)
    "kxncaafbb10": "americanfootball_ncaaf",          # Big Ten (alt)
    "kxncaafbb12": "americanfootball_ncaaf",          # Big 12 (alt)
    "kxncaafbsec": "americanfootball_ncaaf",          # SEC Champion
    "kxncaafsec": "americanfootball_ncaaf",           # SEC Champion (alt)
    "kxncaafconf": "americanfootball_ncaaf",          # Championship conference
    "kxncaaffinalist": "americanfootball_ncaaf",      # Finalist
    "kxncaafplayoff": "americanfootball_ncaaf",       # Playoff qualifiers
    "kxncaafaprank": "americanfootball_ncaaf",        # AP rankings
    "kxncaafcoty": "americanfootball_ncaaf",          # Coach of the Year
    "kxncaafcotw": "americanfootball_ncaaf",          # Coach of the Week
    "kxncaafundefeated": "americanfootball_ncaaf",    # Undefeated season
    "kxncaafwins": "americanfootball_ncaaf",          # Win totals
    "kxncaafcs": "americanfootball_ncaaf",            # FCS Champion
    "kxncaafd3": "americanfootball_ncaaf",            # D3 Champion
    "kxncaafaac": "americanfootball_ncaaf",           # AAC Champion
    "kxncaafcusa": "americanfootball_ncaaf",          # Conference USA
    "kxncaafivy": "americanfootball_ncaaf",           # Ivy League
    "kxncaafmac": "americanfootball_ncaaf",           # MAC Champion
    "kxncaafmwc": "americanfootball_ncaaf",           # Mountain West
    "kxncaafpac10": "americanfootball_ncaaf",         # Pac-10 Champion
    "kxncaafpac12": "americanfootball_ncaaf",         # Pac-12 Champion
    "kxncaafsbelt": "americanfootball_ncaaf",         # Sun Belt
    "kxncaafprepack": "americanfootball_ncaaf",       # Pre-pack bundles
    "kxcoachoutncaafb": "americanfootball_ncaaf",     # Coach fired
    # NCAAB futures
    "kxncaabacc": "basketball_ncaab",                 # ACC Tournament
    "kxncaabbig10": "basketball_ncaab",               # Big Ten Tournament
    "kxncaabbig12": "basketball_ncaab",               # Big 12 Tournament
    "kxncaabbigeast": "basketball_ncaab",             # Big East Tournament
    "kxncaabbigten": "basketball_ncaab",              # Big Ten (alt)
    "kxncaabsec": "basketball_ncaab",                 # SEC Tournament
    "kxncaabivy": "basketball_ncaab",                 # Ivy League Tournament
    "kxncaambacc": "basketball_ncaab",                # ACC Tournament (men's)
    "kxncaambbig10": "basketball_ncaab",              # Big 10 Tournament (men's)
    "kxncaambbig12": "basketball_ncaab",              # Big 12 Tournament (men's)
    "kxncaambbigeast": "basketball_ncaab",            # Big East (men's)
    "kxncaambigeast": "basketball_ncaab",             # Big East (alt)
    "kxncaambigten": "basketball_ncaab",              # Big Ten (alt)
    "kxncaambig12": "basketball_ncaab",               # Big 12 (alt)
    "kxncaambsec": "basketball_ncaab",                # SEC (men's)
    "kxncaambivy": "basketball_ncaab",                # Ivy League (men's)
    "kxncaamba10": "basketball_ncaab",                # Atlantic-10
    "kxncaambae": "basketball_ncaab",                 # American East
    "kxncaambamer": "basketball_ncaab",               # American Conference
    "kxncaambasun": "basketball_ncaab",               # Atlantic Sun
    "kxncaambbsky": "basketball_ncaab",               # Big Sky
    "kxncaambbsou": "basketball_ncaab",               # Big South
    "kxncaambbwest": "basketball_ncaab",              # Big West
    "kxncaambcaa": "basketball_ncaab",                # CAA
    "kxncaambhl": "basketball_ncaab",                 # Horizon League
    "kxncaambhor": "basketball_ncaab",                # Horizon League (alt)
    "kxncaambmaa": "basketball_ncaab",                # MAAC
    "kxncaambmamer": "basketball_ncaab",              # Mid-American
    "kxncaambmeac": "basketball_ncaab",               # MEAC
    "kxncaambmval": "basketball_ncaab",               # Missouri Valley
    "kxncaambmw": "basketball_ncaab",                 # Mountain West
    "kxncaambnec": "basketball_ncaab",                # Northeast
    "kxncaambov": "basketball_ncaab",                 # Ohio Valley
    "kxncaambpat": "basketball_ncaab",                # Patriot League
    "kxncaambsbelt": "basketball_ncaab",              # Sun Belt
    "kxncaambslc": "basketball_ncaab",                # Southland
    "kxncaambsocon": "basketball_ncaab",              # Southern
    "kxncaambsum": "basketball_ncaab",                # Summit League
    "kxncaambsun": "basketball_ncaab",                # Atlantic Sun (alt)
    "kxncaambswac": "basketball_ncaab",               # SWAC
    "kxncaambusa": "basketball_ncaab",                # Conference USA
    "kxncaambwac": "basketball_ncaab",                # WAC
    "kxncaambwcc": "basketball_ncaab",                # WCC
    "kxncaambcbc": "basketball_ncaab",                # Crown winner
    "kxncaambcoty": "basketball_ncaab",               # Coach of the Year
    "kxncaambnaismith": "basketball_ncaab",           # Naismith Award
    "kxncaambmop": "basketball_ncaab",                # Most Outstanding Player
    "kxncaambnit": "basketball_ncaab",                # NIT Champion
    "kxncaambnextcoach": "basketball_ncaab",          # Next coach
    "kxncaambaprank": "basketball_ncaab",             # AP Poll
    "kxncaambundefeated": "basketball_ncaab",         # Undefeated season
    # College baseball futures
    "kxncaabaseball": "baseball_ncaa",                # College Baseball Champion
    "kxncaabbgs": "baseball_ncaa",                    # Golden Spikes Award
    "kxncaambachamp": "baseball_ncaa",                # College Baseball Championship
    # WNCAAB futures
    "kxncaawb": "basketball_wncaab",                  # Women's March Madness Champion
    "kxncaawbmop": "basketball_wncaab",               # Most Outstanding Player
    "kxncaawbnit": "basketball_wncaab",               # Women's NIT
    "kxncaawbwbit": "basketball_wncaab",              # WBIT
    # WNBA futures
    "kxwnba": "basketball_wnba",                     # WNBA Championship
    "kxwnbamvp": "basketball_wnba",                  # MVP
    "kxwnbaroty": "basketball_wnba",                 # Rookie of the Year
    "kxwnbaplayoff": "basketball_wnba",              # Playoff qualifiers
    "kxwnbaseries": "basketball_wnba",               # Playoff series
    "kxwnbadraft1": "basketball_wnba",               # Draft 1st pick
    "kxwnbadrafttop3": "basketball_wnba",            # Draft top 3
    "kxwnbaasgame": "basketball_wnba",               # All-Star Game
    "kxwnbagamesplayed": "basketball_wnba",          # Games played
    "kxwnba7figs": "basketball_wnba",                # 7-figure salary
    "kxwnbadelay": "basketball_wnba",                # Season delay
    "kxwnbaportnoy": "basketball_wnba",              # Portnoy ban
    "kxwnbaraise": "basketball_wnba",                # Raise
    # MLS futures
    "kxmlscup": "soccer_usa_mls",                    # MLS Cup
    "kxmlseast": "soccer_usa_mls",                   # Eastern Conference
    "kxmlswest": "soccer_usa_mls",                   # Western Conference
    # Soccer futures
    "kxsoccertransfer": "soccer",                    # Transfer market
    "kxsoccerplaycron": "soccer",                    # Ronaldo World Cup
    "kxsoccerplaymessi": "soccer",                   # Messi World Cup
    "kxeculp": "soccer_other",                       # Ecuadorian league
    "kxapfddh": "soccer_other",                      # Dominican league
    "kxvenfutve": "soccer_other",                    # Venezuelan league
    # Tennis futures
    "kxatp1rank": "tennis_atp",                      # #1 ranked player
    "kxatprank": "tennis_atp",                       # Rankings (alt)
    "kxatpfinals": "tennis_atp",                     # ATP Finals
    "kxatpnextgen": "tennis_atp",                    # Next Gen Finals
    "kxatpgrandslam": "tennis_atp",                  # Grand Slam winner
    "kxatpgrandslamfield": "tennis_atp",             # Grand Slam field winner
    "kxatpamt": "tennis_atp",                        # Mexican Open
    "kxatpit": "tennis_atp",                         # Italian Open
    "kxatpiwo": "tennis_atp",                        # Indian Wells
    "kxatpmad": "tennis_atp",                        # Madrid
    "kxatpmc": "tennis_atp",                         # Monte Carlo
    "kxatpmco": "tennis_atp",                        # Chile Open
    "kxatpmia": "tennis_atp",                        # Miami
    "kxatpwddf": "tennis_atp",                       # Dubai
    "kxwtafinals": "tennis_wta",                     # WTA Finals
    "kxwtagrandslam": "tennis_wta",                  # WTA Grand Slam
    "kxwtait": "tennis_wta",                         # Italian Open
    "kxwtaiwo": "tennis_wta",                        # Indian Wells
    "kxwtamad": "tennis_wta",                        # Madrid
    "kxwtamia": "tennis_wta",                        # Miami
    "kxwtamoa": "tennis_wta",                        # Merida Open
    "kxwtaatx": "tennis_wta",                        # ATX Open
    "kxwtaddf": "tennis_wta",                        # Dubai
    "kxwtaserena": "tennis_wta",                     # Serena Williams
    # Combat futures
    "kxufc": "mma_mixed_martial_arts",               # Weightclass champions
    "kxufctitle": "mma_mixed_martial_arts",           # Title fights
    "kxufcbantamweighttitle": "mma_mixed_martial_arts",
    "kxufcfeatherweighttitle": "mma_mixed_martial_arts",
    "kxufcflyweighttitle": "mma_mixed_martial_arts",
    "kxufcheavyweighttitle": "mma_mixed_martial_arts",
    "kxufclheavyweighttitle": "mma_mixed_martial_arts",
    "kxufclightweighttitle": "mma_mixed_martial_arts",
    "kxufcmiddleweighttitle": "mma_mixed_martial_arts",
    "kxufcwelterweighttitle": "mma_mixed_martial_arts",
    "kxufcmweight": "mma_mixed_martial_arts",        # Middleweight champ
    "kxufcwhitehouse": "mma_mixed_martial_arts",     # White House event
    "kxcardpresenceufcwh": "mma_mixed_martial_arts", # White House card
    "kxboxing": "boxing_boxing",                     # Boxing champion
    # Esports futures
    "kxcs2": "esports",                              # CS2 tournament winner
    "kxcs2iemcologne": "esports",                    # IEM Cologne
    "kxcs2qualifier": "esports",                     # CS2 qualifiers
    "kxcs2qualifiers": "esports",                    # CS2 qualifiers (alt)
    "kxcs2qualify": "esports",                       # CS2 qualifiers (alt2)
    "kxvalorant": "esports",                         # Valorant tournament
    "kxvalorantmastersfinals": "esports",            # Valorant Masters Finals
    "kxvalorantgameteam": "esports",                 # Valorant team matchup
    "kxlol1sttimewin": "esports",                    # LoL first-time winner
    "kxcharcountlolworlds": "esports",               # LoL Worlds
    "kxranklistcs2player": "esports",                # HLTV Player of Year
    "kxranklistcs2team": "esports",                  # HLTV Team of Year
    "kxewccs2": "esports",                           # Esports World Cup CS2
    "kxewcvalorant": "esports",                      # Esports World Cup Valorant
    "kxewcmlbb": "esports",                          # Esports World Cup MLBB (NOT baseball)
    # ── Manus catalog additions (April 21, 2026) ──
    # Baseball divisions + awards + props
    "kxmlbale": "baseball_mlb",
    "kxmlbalc": "baseball_mlb",
    "kxmlbalw": "baseball_mlb",
    "kxmlbnle": "baseball_mlb",
    "kxmlbnlc": "baseball_mlb",
    "kxmlbnlw": "baseball_mlb",
    "kxmlbcyal": "baseball_mlb",
    "kxmlbcynl": "baseball_mlb",
    "kxmlbmvpal": "baseball_mlb",
    "kxmlbmvpnl": "baseball_mlb",
    "kxmlbroya": "baseball_mlb",
    "kxmlbroyn": "baseball_mlb",
    "kxmlbmgral": "baseball_mlb",
    "kxmlbmgrnl": "baseball_mlb",
    "kxmlbplay": "baseball_mlb",
    "kxmlbhits": "baseball_mlb",
    "kxmlbk": "baseball_mlb",
    "kxmlbrbi": "baseball_mlb",
    # Basketball awards + props + college
    "kxnbascore": "basketball_nba",
    "kxnba3pm": "basketball_nba",
    "kxnbadd": "basketball_nba",
    "kxnbahalf": "basketball_nba",
    "kxnbaptsleader": "basketball_nba",
    "kxncaab": "basketball_ncaab",
    "kxncaabff": "basketball_ncaab",
    "kxncaabe8": "basketball_ncaab",
    "kxncaabs16": "basketball_ncaab",
    "kxncaaw": "basketball_wncaab",
    # Football Super Bowl + divisions + awards + props
    "kxnflsb": "americanfootball_nfl",
    "kxnflafc": "americanfootball_nfl",
    "kxnflnfc": "americanfootball_nfl",
    "kxnflafce": "americanfootball_nfl",
    "kxnflafcn": "americanfootball_nfl",
    "kxnflafcs": "americanfootball_nfl",
    "kxnflafcw": "americanfootball_nfl",
    "kxnflnfce": "americanfootball_nfl",
    "kxnflnfcn": "americanfootball_nfl",
    "kxnflnfcs": "americanfootball_nfl",
    "kxnflnfcw": "americanfootball_nfl",
    "kxnflplay": "americanfootball_nfl",
    "kxnflseries": "americanfootball_nfl",
    "kxnflopy": "americanfootball_nfl",
    "kxnfldpy": "americanfootball_nfl",
    "kxnflory": "americanfootball_nfl",
    "kxnfldry": "americanfootball_nfl",
    "kxnflcpy": "americanfootball_nfl",
    "kxnflcoy": "americanfootball_nfl",
    "kxnflhalf": "americanfootball_nfl",
    "kxnflpyds": "americanfootball_nfl",
    "kxnflryds": "americanfootball_nfl",
    "kxnfltds": "americanfootball_nfl",
    "kxheisman": "americanfootball_ncaaf",
    # Hockey conference + awards + series
    "kxnhleast": "icehockey_nhl",
    "kxnhlwest": "icehockey_nhl",
    "kxnhlhart": "icehockey_nhl",
    "kxnhlcalder": "icehockey_nhl",
    "kxnhlnorris": "icehockey_nhl",
    "kxnhlvezina": "icehockey_nhl",
    "kxnhlseries": "icehockey_nhl",
    # Golf tournaments + props
    "kxpgatour": "golf",
    "kxpgamakecut": "golf",
    "kxpgatop5": "golf",
    "kxpgatop10": "golf",
    "kxpgatop20": "golf",
    "kxpgar1lead": "golf",
    "kxpgar2lead": "golf",
    "kxpgar3lead": "golf",
    "kxpgar1top5": "golf",
    "kxpgar1top10": "golf",
    "kxpgar1top20": "golf",
    "kxpgar2top5": "golf",
    "kxpgar2top10": "golf",
    "kxpgar3top5": "golf",
    "kxpgar3top10": "golf",
    "kxpgah2h": "golf",
    "kxpgaholeinone": "golf",
    "kxpgamajorwin": "golf",
    "kxpgawinningscore": "golf",
    "kxpgacutline": "golf",
    "kxpgawinmargin": "golf",
    "kxlpgatour": "golf",
    "kxlivgolf": "golf",
    # Soccer — European leagues + World Cup
    "kxepl": "soccer_epl",
    "kxepltop4": "soccer_epl",
    "kxeplrel": "soccer_epl",
    "kxeplgb": "soccer_epl",
    "kxucl": "soccer_uefa_champions_league",
    "kxlaliga": "soccer_spain_la_liga",
    "kxbundes": "soccer_germany_bundesliga",
    "kxseriea": "soccer_italy_serie_a",
    "kxligue1": "soccer_france_ligue_one",
    "kxmls": "soccer_usa_mls",
    "kxfifawcm": "soccer_fifa_world_cup",
    "kxfifawcw": "soccer_fifa_world_cup_women",
    # Tennis
    "kxatp": "tennis_atp",
    "kxwta": "tennis_wta",
    "kxatpsets": "tennis_atp",
    "kxatptotal": "tennis_atp",
    # Boxing
    "kxwbcheavyweighttitle": "boxing_boxing",
    "kxwbcmiddleweighttitle": "boxing_boxing",
    # Motorsport
    "kxf1wdc": "motorsport",
    "kxf1wcc": "motorsport",
    "kxf1race": "motorsport",
    "kxnascar": "motorsport",
    "kxnascarrace": "motorsport",
    # Esports
    "kxesports": "esports",
    "kxlolworlds": "esports",
    "kxcs2major": "esports",
    "kxval": "esports",
    "kxdota2ti": "esports",
    # Cricket
    "kxcricket": "cricket",
    "kxcricketseries": "cricket",
}


#=============================================================================
# 9. KALSHI_TICKER_TO_DISPLAY_LABEL — Kalshi ticker prefix → display label
# =============================================================================

KALSHI_TICKER_TO_DISPLAY_LABEL: dict[str, str] = {
    "kxnbagame": "NBA",
    "kxnflgame": "NFL",
    "kxnhlgame": "NHL",
    "kxmlbgame": "MLB",
    # NBA game-level props
    "kxnbaspread": "NBA",
    "kxnbatotal": "NBA",
    "kxnbateamtotal": "NBA",
    "kxnba1hwinner": "NBA",
    "kxnba1hspread": "NBA",
    "kxnba1htotal": "NBA",
    "kxnba2hwinner": "NBA",
    "kxnba2hspread": "NBA",
    "kxnba2htotal": "NBA",
    "kxnba1qwinner": "NBA",
    "kxnba1qspread": "NBA",
    "kxnba1qtotal": "NBA",
    "kxnba2qwinner": "NBA",
    "kxnba2qspread": "NBA",
    "kxnba2qtotal": "NBA",
    "kxnba3qwinner": "NBA",
    "kxnba3qspread": "NBA",
    "kxnba3qtotal": "NBA",
    "kxnba4qwinner": "NBA",
    "kxnba4qspread": "NBA",
    "kxnba4qtotal": "NBA",
    "kxnbapts": "NBA",
    "kxnbaast": "NBA",
    "kxnbareb": "NBA",
    "kxnbablk": "NBA",
    "kxnbastl": "NBA",
    "kxnba3pt": "NBA",
    "kxnbapa": "NBA",
    "kxnbapr": "NBA",
    "kxnbapra": "NBA",
    "kxnbara": "NBA",
    "kxnba2d": "NBA",
    "kxnba3d": "NBA",
    "kxnbafirstbasket": "NBA",
    # NFL game-level
    "kxnflspread": "NFL",
    "kxnfltotal": "NFL",
    "kxnflteamtotal": "NFL",
    "kxnfl1hwinner": "NFL",
    "kxnfl1hspread": "NFL",
    "kxnfl1htotal": "NFL",
    "kxnfl2hwinner": "NFL",
    "kxnfl2hspread": "NFL",
    "kxnfl2htotal": "NFL",
    "kxnfl1qwinner": "NFL",
    "kxnfl1qspread": "NFL",
    "kxnfl1qtotal": "NFL",
    "kxnfl2qwinner": "NFL",
    "kxnfl2qspread": "NFL",
    "kxnfl2qtotal": "NFL",
    "kxnfl3qwinner": "NFL",
    "kxnfl3qspread": "NFL",
    "kxnfl3qtotal": "NFL",
    "kxnfl4qwinner": "NFL",
    "kxnfl4qspread": "NFL",
    "kxnfl4qtotal": "NFL",
    "kxnflpasstds": "NFL",
    "kxnflpassyds": "NFL",
    "kxnflrecyds": "NFL",
    "kxnflrshyds": "NFL",
    "kxnflrec": "NFL",
    "kxnflanytd": "NFL",
    "kxnflfirsttd": "NFL",
    "kxnflnexttd": "NFL",
    "kxnflteamfirsttd": "NFL",
    "kxnfl2td": "NFL",
    "kxnflfirsttdtime": "NFL",
    "kxnflgamefg": "NFL",
    "kxnflgamesack": "NFL",
    "kxnflgametd": "NFL",
    "kxnflgameto": "NFL",
    "kxnflot": "NFL",
    "kxnflwinmargin": "NFL",
    "kxnfldsttd": "NFL",
    "kxnflsafety": "NFL",
    "kxnflhighscoreq": "NFL",
    "kxnflnoscoreq": "NFL",
    "kxnfllargelead": "NFL",
    "kxnfllargestlead": "NFL",
    "kxnflleadchange": "NFL",
    "kxnfllongesttd": "NFL",
    "kxnflshortesttd": "NFL",
    "kxnflmostrecyds": "NFL",
    "kxnflmostrshyds": "NFL",
    "kxnflnonqbpass": "NFL",
    "kxnfl2ptconv": "NFL",
    "kxnfl4dconv": "NFL",
    "kxnfl4downconv": "NFL",
    "kxnflcombo": "NFL",
    "kxnflprepack": "NFL",
    # NHL game-level
    "kxnhlspread": "NHL",
    "kxnhltotal": "NHL",
    "kxnhl1hwinner": "NHL",
    "kxnhl1hspread": "NHL",
    "kxnhl1htotal": "NHL",
    "kxnhl2hwinner": "NHL",
    "kxnhl2hspread": "NHL",
    "kxnhl2htotal": "NHL",
    "kxnhlanygoal": "NHL",
    "kxnhlgoal": "NHL",
    "kxnhlfirstgoal": "NHL",
    "kxnhlpts": "NHL",
    "kxnhlast": "NHL",
    "kxnhlsaves": "NHL",
    # MLB game-level
    "kxmlbspread": "MLB",
    "kxmlbtotal": "MLB",
    "kxmlbteamtotal": "MLB",
    "kxmlb1hwinner": "MLB",
    "kxmlb1hspread": "MLB",
    "kxmlb1htotal": "MLB",
    "kxmlb2hwinner": "MLB",
    "kxmlb2hspread": "MLB",
    "kxmlb2htotal": "MLB",
    "kxmlbf5": "MLB",
    "kxmlbf5spread": "MLB",
    "kxmlbf5total": "MLB",
    "kxmlbhit": "MLB",
    "kxmlbhr": "MLB",
    "kxmlbks": "MLB",
    "kxmlbtb": "MLB",
    "kxmlbhrr": "MLB",
    "kxmlbrfi": "MLB",
    "kxmlbstgame": "MLB",
    # College basketball
    "kxncaabgame": "NCAAB",
    "kxncaambgame": "NCAAB",
    "kxncaamb1hwinner": "NCAAB",
    "kxncaamb1hspread": "NCAAB",
    "kxncaamb1htotal": "NCAAB",
    "kxncaamb2hwinner": "NCAAB",
    "kxncaamb2hspread": "NCAAB",
    "kxncaamb2htotal": "NCAAB",
    "kxncaambspread": "NCAAB",
    "kxncaambtotal": "NCAAB",
    "kxncaamb2ml": "NCAAB",
    "kxncaambfirst10": "NCAAB",
    "kxncaambteammostpts": "NCAAB",
    # College baseball
    "kxncaabbgame": "NCAA Baseball",
    "kxncaabbspread": "NCAA Baseball",
    "kxncaabbtotal": "NCAA Baseball",
    # College football
    "kxncaafgame": "NCAAF",
    "kxncaaf1hwinner": "NCAAF",
    "kxncaaf1hspread": "NCAAF",
    "kxncaaf1htotal": "NCAAF",
    "kxncaaf2hwinner": "NCAAF",
    "kxncaaf2hspread": "NCAAF",
    "kxncaaf2htotal": "NCAAF",
    "kxncaafspread": "NCAAF",
    "kxncaaftotal": "NCAAF",
    "kxncaafteamtotal": "NCAAF",
    "kxncaafd3game": "NCAAF",
    "kxncaafcsgame": "NCAAF",
    # Women's college basketball
    "kxncaawbgame": "WNCAAB",
    "kxncaawbspread": "WNCAAB",
    "kxncaawbtotal": "WNCAAB",
    # Other leagues
    "kxncaamlaxgame": "NCAA Lax",
    "kxncaahockeygame": "NCAA Hockey",
    "kxwnbagame": "WNBA",
    # MLS game-level
    "kxmlsgame": "MLS",
    "kxmlsspread": "MLS",
    "kxmlstotal": "MLS",
    "kxmlsbtts": "MLS",
    "kxmlsadvance": "MLS",
    # Soccer game-level
    "kxsoccergame": "Soccer",
    "kxsoccerspread": "Soccer",
    "kxsoccertotal": "Soccer",
    "kxsoccerbtts": "Soccer",
    "kxsocgame": "EPL",
    "kxsoctotal": "EPL",
    "kxsocbtts": "EPL",
    # Minor leagues
    "kxahlgame": "AHL",
    "kxkhlgame": "KHL",
    "kxdelgame": "DEL",
    # Tennis
    "kxatpmatch": "ATP",
    "kxatpchallengermatch": "ATP Challenger",
    "kxatpsetwinner": "ATP",
    "kxatpanyset": "ATP",
    "kxatpexactmatch": "ATP",
    "kxatpexactsets": "ATP",
    "kxatpgamespread": "ATP",
    "kxatpgspread": "ATP",
    "kxatpgametotal": "ATP",
    "kxatptotalsets": "ATP",
    "kxatpdoubles": "ATP",
    "kxatpgame": "ATP",
    "kxwtamatch": "WTA",
    "kxwtachallengermatch": "WTA Challenger",
    "kxwtadoubles": "WTA",
    "kxwtagame": "WTA",
    # Combat
    "kxufcfight": "UFC",
    "kxufcdistance": "UFC",
    "kxufcmof": "UFC",
    "kxufcmov": "UFC",
    "kxufcrounds": "UFC",
    "kxufcvicround": "UFC",
    "kxboxingfight": "Boxing",
    "kxboxingdistance": "Boxing",
    "kxboxing1min": "Boxing",
    "kxboxingknockout": "Boxing",
    "kxboxingmov": "Boxing",
    "kxboxingrounds": "Boxing",
    "kxboxingvicround": "Boxing",
    # Esports
    "kxlolgame": "LoL",
    "kxlolgames": "LoL",
    "kxlolmap": "LoL",
    "kxloltotal": "LoL",
    "kxloltotalmaps": "LoL",
    "kxcs2game": "CS2",
    "kxcs2games": "CS2",
    "kxcs2map": "CS2",
    "kxcs2mapwinner": "CS2",
    "kxcs2totalmaps": "CS2",
    "kxvalorantgame": "Valorant",
    "kxvalorantmap": "Valorant",
    "kxdimayorgame": "Colombian Dimayor",
}


# =============================================================================
# 10. LLM_CATEGORY_TO_SPORT_KEYS — LLM category → list of full sport keys
# =============================================================================

LLM_CATEGORY_TO_SPORT_KEYS: dict[str, list[str]] = {
    "basketball": ["basketball_nba", "basketball_wnba", "basketball_ncaab", "basketball_wncaab"],
    "football": ["americanfootball_nfl", "americanfootball_ncaaf"],
    "baseball": ["baseball_mlb"],
    "hockey": ["icehockey_nhl"],
    "soccer": [
        "soccer_epl", "soccer_usa_mls", "soccer_spain_la_liga",
        "soccer_germany_bundesliga", "soccer_italy_serie_a",
        "soccer_france_ligue_one", "soccer_uefa_champs_league",
    ],
    "golf": ["golf_pga"],
    "tennis": ["tennis_atp", "tennis_wta"],
    "mma": ["mma_mixed_martial_arts"],
    "boxing": ["boxing_boxing"],
    "motorsports": ["motorsport_f1", "motorsport_nascar"],
    "esports": ["esports_lol", "esports_cs2", "esports_valorant"],
}


# =============================================================================
# 11. SPORT_HIERARCHY — Sport → league page architecture
#
# Defines the /sport/{sport} → /sport/{sport}/{league} navigation tree.
# Each sport has leagues (with display metadata) and optional cross-league
# showcase events (majors, cups) that live on the sport hub page.
# =============================================================================

SPORT_HIERARCHY: dict[str, dict] = {
    "golf": {
        "name": "Golf",
        "slug": "golf",
        "leagues": [
            {"slug": "pga", "name": "PGA Tour", "sport_keys": ["golf_pga"]},
            {"slug": "dpworld", "name": "DP World Tour", "sport_keys": []},
            {"slug": "lpga", "name": "LPGA", "sport_keys": ["golf_lpga"]},
            {"slug": "liv", "name": "LIV Golf", "sport_keys": []},
            {"slug": "kft", "name": "Korn Ferry Tour", "sport_keys": []},
        ],
        "showcase_events": [
            # Men's majors
            {"name": "The Masters", "type": "major"},
            {"name": "PGA Championship", "type": "major"},
            {"name": "U.S. Open", "type": "major"},
            {"name": "The Open Championship", "type": "major"},
            # Women's majors
            {"name": "Chevron Championship", "type": "womens_major"},
            {"name": "KPMG Women's PGA Championship", "type": "womens_major"},
            {"name": "U.S. Women's Open", "type": "womens_major"},
            {"name": "AIG Women's Open", "type": "womens_major"},
            {"name": "The Evian Championship", "type": "womens_major"},
            # Cups
            {"name": "Ryder Cup", "type": "cup"},
            {"name": "Presidents Cup", "type": "cup"},
            {"name": "Walker Cup", "type": "cup"},
            {"name": "Solheim Cup", "type": "cup"},
        ],
    },
    "basketball": {
        "name": "Basketball",
        "slug": "basketball",
        "leagues": [
            {"slug": "nba", "name": "NBA", "sport_keys": ["basketball_nba"]},
            {"slug": "wnba", "name": "WNBA", "sport_keys": ["basketball_wnba"]},
            {"slug": "ncaab", "name": "NCAA Men's Basketball", "sport_keys": ["basketball_ncaab"]},
            {"slug": "wncaab", "name": "NCAA Women's Basketball", "sport_keys": ["basketball_wncaab"]},
        ],
        "showcase_events": [
            {"name": "March Madness (Men's)", "type": "tournament"},
            {"name": "March Madness (Women's)", "type": "tournament"},
        ],
    },
    "football": {
        "name": "Football",
        "slug": "football",
        "leagues": [
            {"slug": "nfl", "name": "NFL", "sport_keys": ["americanfootball_nfl"]},
            {"slug": "ncaaf", "name": "NCAA Football", "sport_keys": ["americanfootball_ncaaf"]},
            {"slug": "cfl", "name": "CFL", "sport_keys": ["americanfootball_cfl"]},
            {"slug": "ufl", "name": "UFL", "sport_keys": ["americanfootball_ufl"]},
        ],
        "showcase_events": [
            {"name": "Super Bowl", "type": "championship"},
            {"name": "College Football Playoff", "type": "championship"},
        ],
    },
    "hockey": {
        "name": "Hockey",
        "slug": "hockey",
        "leagues": [
            {"slug": "nhl", "name": "NHL", "sport_keys": ["icehockey_nhl"]},
        ],
        "showcase_events": [
            {"name": "Stanley Cup", "type": "championship"},
        ],
    },
    "baseball": {
        "name": "Baseball",
        "slug": "baseball",
        "leagues": [
            {"slug": "mlb", "name": "MLB", "sport_keys": ["baseball_mlb"]},
            {"slug": "ncaa", "name": "College Baseball", "sport_keys": ["baseball_ncaa"]},
        ],
        "showcase_events": [
            {"name": "World Series", "type": "championship"},
            {"name": "College World Series", "type": "championship"},
        ],
    },
    "soccer": {
        "name": "Soccer",
        "slug": "soccer",
        "leagues": [
            {"slug": "epl", "name": "Premier League", "sport_keys": ["soccer_epl"]},
            {"slug": "mls", "name": "MLS", "sport_keys": ["soccer_usa_mls"]},
            {"slug": "laliga", "name": "La Liga", "sport_keys": ["soccer_spain_la_liga"]},
            {"slug": "bundesliga", "name": "Bundesliga", "sport_keys": ["soccer_germany_bundesliga"]},
            {"slug": "seriea", "name": "Serie A", "sport_keys": ["soccer_italy_serie_a"]},
            {"slug": "ligue1", "name": "Ligue 1", "sport_keys": ["soccer_france_ligue_one"]},
            {"slug": "ucl", "name": "Champions League", "sport_keys": ["soccer_uefa_champs_league"]},
        ],
        "showcase_events": [
            {"name": "Champions League", "type": "championship"},
            {"name": "FIFA World Cup", "type": "championship"},
        ],
    },
    "tennis": {
        "name": "Tennis",
        "slug": "tennis",
        "leagues": [
            {"slug": "atp", "name": "ATP Tour", "sport_keys": ["tennis_atp"]},
            {"slug": "wta", "name": "WTA Tour", "sport_keys": ["tennis_wta"]},
        ],
        "showcase_events": [
            {"name": "Australian Open", "type": "grand_slam"},
            {"name": "French Open", "type": "grand_slam"},
            {"name": "Wimbledon", "type": "grand_slam"},
            {"name": "US Open", "type": "grand_slam"},
        ],
    },
    "mma": {
        "name": "MMA",
        "slug": "mma",
        "leagues": [
            {"slug": "ufc", "name": "UFC", "sport_keys": ["mma_mixed_martial_arts"]},
        ],
        "showcase_events": [],
    },
    "boxing": {
        "name": "Boxing",
        "slug": "boxing",
        "leagues": [
            {"slug": "boxing", "name": "Boxing", "sport_keys": ["boxing_boxing"]},
        ],
        "showcase_events": [],
    },
    "motorsports": {
        "name": "Motorsports",
        "slug": "motorsports",
        "leagues": [
            {"slug": "f1", "name": "Formula 1", "sport_keys": ["motorsport_f1"]},
            {"slug": "nascar", "name": "NASCAR", "sport_keys": ["motorsport_nascar"]},
        ],
        "showcase_events": [
            {"name": "Monaco Grand Prix", "type": "race"},
            {"name": "Daytona 500", "type": "race"},
            {"name": "Indianapolis 500", "type": "race"},
        ],
    },
    "esports": {
        "name": "Esports",
        "slug": "esports",
        "leagues": [
            {"slug": "lol", "name": "League of Legends", "sport_keys": ["esports_lol"]},
            {"slug": "cs2", "name": "Counter-Strike 2", "sport_keys": ["esports_cs2"]},
            {"slug": "valorant", "name": "Valorant", "sport_keys": ["esports_valorant"]},
        ],
        "showcase_events": [
            {"name": "LoL Worlds", "type": "championship"},
            {"name": "CS2 Major", "type": "championship"},
            {"name": "Valorant Champions", "type": "championship"},
        ],
    },
}


_SPORT_SLUG_ALIASES: dict[str, str] = {
    "icehockey": "hockey",
    "americanfootball": "football",
}


def get_sport_hierarchy(sport_slug: str) -> Optional[dict]:
    """Get hierarchy data for a sport by its URL slug (with aliases)."""
    canonical = _SPORT_SLUG_ALIASES.get(sport_slug, sport_slug)
    return SPORT_HIERARCHY.get(canonical)


def get_all_sport_slugs() -> list[str]:
    """Get all sport slugs that have hierarchy data."""
    return list(SPORT_HIERARCHY.keys())


# =============================================================================
# Accessor functions
# =============================================================================

def get_espn_path(sport_key: str) -> Optional[tuple[str, str]]:
    """Look up the ESPN (sport, league) tuple for an Odds API sport key."""
    return SPORT_LEAGUE_MAP.get(sport_key)


def normalize_to_win_prob_key(sport_key: str) -> str:
    """Map an Odds API sport key to the canonical win-prob model key.

    Returns the key unchanged if no alias exists (passthrough).
    """
    return ODDS_API_TO_WIN_PROB_KEY.get(sport_key, sport_key)


def get_sport_prefix_for_category(llm_category: str) -> Optional[str]:
    """Map an LLM sport category to an Odds API sport key prefix."""
    return LLM_CATEGORY_TO_SPORT_PREFIX.get(llm_category)


def get_sport_key_from_ticker(external_id: str) -> Optional[str]:
    """Get the Odds API sport key for a Kalshi ticker (game-level or futures).

    Checks game-level tickers first, then futures tickers.
    Returns a sport key (e.g., ``"basketball_nba"``) or ``None``.
    """
    if not external_id:
        return None
    ext_lower = external_id.lower()
    # Check game-level tickers first (more specific prefixes)
    for prefix, sport in KALSHI_TICKER_TO_SPORT_KEY.items():
        if ext_lower.startswith(prefix):
            return sport
    # Check futures-level tickers
    for prefix, sport in KALSHI_FUTURES_TICKER_TO_SPORT_KEY.items():
        if ext_lower.startswith(prefix):
            return sport
    return None


def is_kalshi_game_ticker(external_id: str) -> bool:
    """Check whether a Kalshi ``external_id`` is a game-level ticker."""
    if not external_id:
        return False
    ext_lower = external_id.lower()
    return any(ext_lower.startswith(prefix) for prefix in KALSHI_GAME_TICKER_PREFIXES)


def get_sport_keys_for_category(category: Optional[str]) -> Optional[list[str]]:
    """Get sport keys to scope team search for a given sport category.

    Returns ``None`` if category is unknown (search all teams).
    """
    if not category:
        return None
    return LLM_CATEGORY_TO_SPORT_KEYS.get(category.lower())


def get_llm_category_for_prefix(sport_prefix: str) -> str:
    """Map a sport key prefix to its LLM category.

    Falls back to the prefix itself if no mapping exists.
    """
    return SPORT_PREFIX_TO_LLM_CATEGORY.get(sport_prefix, sport_prefix)
