"""Reviewable nickname and spelling cases for the four major US leagues.

These are exact query aliases, never fuzzy identity matches or database writes.
Shared nicknames keep every claimant; the reader can still choose a league.
"""

# canonical team name | nickname | spelling variant
_CASES = {
    "americanfootball_nfl": """
Arizona Cardinals|cardinals|cardnals
Atlanta Falcons|falcons|falocns
Baltimore Ravens|ravens|ravnes
Buffalo Bills|bills|bils
Carolina Panthers|panthers|panters
Chicago Bears|bears|baers
Cincinnati Bengals|bengals|bengles
Cleveland Browns|browns|brownes
Dallas Cowboys|cowboys|cowobys
Denver Broncos|broncos|bronocs
Detroit Lions|lions|lioins
Green Bay Packers|packers|pakcers
Houston Texans|texans|texnas
Indianapolis Colts|colts|coltss
Jacksonville Jaguars|jaguars|jaguers
Kansas City Chiefs|chiefs|cheifs
Las Vegas Raiders|raiders|raders
Los Angeles Chargers|chargers|chagers
Los Angeles Rams|rams|ramss
Miami Dolphins|dolphins|dolpins
Minnesota Vikings|vikings|vikngs
New England Patriots|patriots|patroits
New Orleans Saints|saints|sainst
New York Giants|giants|gaints
New York Jets|jets|jetts
Philadelphia Eagles|eagles|eagels
Pittsburgh Steelers|steelers|stelers
San Francisco 49ers|49ers|49rs
Seattle Seahawks|seahawks|seahwaks
Tampa Bay Buccaneers|buccaneers|buccaners
Tennessee Titans|titans|titnas
Washington Commanders|commanders|comanders
""",
    "basketball_nba": """
Atlanta Hawks|hawks|hawsk
Boston Celtics|celtics|celtcis
Brooklyn Nets|nets|netts
Charlotte Hornets|hornets|hornest
Chicago Bulls|bulls|buls
Cleveland Cavaliers|cavaliers|caveliers
Dallas Mavericks|mavericks|maverecks
Denver Nuggets|nuggets|nugets
Detroit Pistons|pistons|pistions
Golden State Warriors|warriors|warriers
Houston Rockets|rockets|rocktes
Indiana Pacers|pacers|pacres
Los Angeles Clippers|clippers|clipers
Los Angeles Lakers|lakers|lakres
Memphis Grizzlies|grizzlies|grizlies
Miami Heat|heat|heatt
Milwaukee Bucks|bucks|bukcs
Minnesota Timberwolves|timberwolves|timberwolfs
New Orleans Pelicans|pelicans|pelicns
New York Knicks|knicks|nikcs
Oklahoma City Thunder|thunder|thuder
Orlando Magic|magic|magci
Philadelphia 76ers|76ers|76rs
Phoenix Suns|suns|sunss
Portland Trail Blazers|trail blazers|trail blazors
Sacramento Kings|kings|kigns
San Antonio Spurs|spurs|spurrs
Toronto Raptors|raptors|rapters
Utah Jazz|jazz|jazzs
Washington Wizards|wizards|wizrads
""",
    "baseball_mlb": """
Arizona Diamondbacks|diamondbacks|dimondbacks
Athletics|athletics|athlethics
Atlanta Braves|braves|bravse
Baltimore Orioles|orioles|oriols
Boston Red Sox|red sox|redsox
Chicago Cubs|cubs|cubbs
Chicago White Sox|white sox|whitesox
Cincinnati Reds|reds|redss
Cleveland Guardians|guardians|gaurdians
Colorado Rockies|rockies|rockes
Detroit Tigers|tigers|tigrs
Houston Astros|astros|astors
Kansas City Royals|royals|roayls
Los Angeles Angels|angels|anegls
Los Angeles Dodgers|dodgers|dogers
Miami Marlins|marlins|marlns
Milwaukee Brewers|brewers|brewres
Minnesota Twins|twins|twnis
New York Mets|mets|metts
New York Yankees|yankees|yankess
Philadelphia Phillies|phillies|philies
Pittsburgh Pirates|pirates|pirtaes
San Diego Padres|padres|paders
San Francisco Giants|giants|gaints
Seattle Mariners|mariners|marinres
St. Louis Cardinals|cardinals|cardnals
Tampa Bay Rays|rays|rayys
Texas Rangers|rangers|ragners
Toronto Blue Jays|blue jays|bluejays
Washington Nationals|nationals|nationls
""",
    "icehockey_nhl": """
Anaheim Ducks|ducks|dukcs
Boston Bruins|bruins|bruiins
Buffalo Sabres|sabres|sabarres
Calgary Flames|flames|flmaes
Carolina Hurricanes|hurricanes|huricanes
Chicago Blackhawks|blackhawks|blackhaws
Colorado Avalanche|avalanche|avalance
Columbus Blue Jackets|blue jackets|blue jakcets
Dallas Stars|stars|starrs
Detroit Red Wings|red wings|redwings
Edmonton Oilers|oilers|olers
Florida Panthers|panthers|panters
Los Angeles Kings|kings|kigns
Minnesota Wild|wild|wiild
Montreal Canadiens|canadiens|canadeins
Nashville Predators|predators|predetors
New Jersey Devils|devils|devles
New York Islanders|islanders|isladners
New York Rangers|rangers|ragners
Ottawa Senators|senators|senetors
Philadelphia Flyers|flyers|flyres
Pittsburgh Penguins|penguins|penguns
San Jose Sharks|sharks|shakrs
Seattle Kraken|kraken|kracken
St. Louis Blues|blues|bluse
Tampa Bay Lightning|lightning|lightnig
Toronto Maple Leafs|maple leafs|maple leaves
Utah Mammoth|mammoth|mamoth
Vancouver Canucks|canucks|cannucks
Vegas Golden Knights|golden knights|golden knigts
Washington Capitals|capitals|capitlas
Winnipeg Jets|jets|jetts
""",
}

MAJOR_TEAM_SEARCH_CASES = tuple(
    (sport, *line.split("|"))
    for sport, block in _CASES.items()
    for line in block.strip().splitlines()
)

# Only the complete identity query is rewritten. A word inside another name,
# a negation, a game date or a named opponent must never be discarded.
_SPELLINGS = {typo: nickname for _, _, nickname, typo in MAJOR_TEAM_SEARCH_CASES}
MAJOR_TEAM_QUERY_ALIASES = {
    (sport, name): (nickname, spelling)
    for sport, name, nickname, spelling in MAJOR_TEAM_SEARCH_CASES
}


def normalize_major_team_query(query: str) -> str:
    return _SPELLINGS.get(" ".join(query.casefold().split()), query)
