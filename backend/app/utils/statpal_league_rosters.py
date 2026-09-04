"""Do StatPal's NBA/NHL/MLB names and ours name the same franchise? #2867 / D50.

Program step 3's answer to the question `app/utils/nfl_team_matching` answered for
the NFL, extended by step 5 to MLB. Same conclusion — **equality after
normalization, nothing looser** — and it is measured for each league rather than
inherited from the last one.

## What was measured, 2026-09-04 ~5:10am PT

Live `GET /v1/{nba,nhl}/season-schedule` against production `events`:

    league   StatPal distinct names   our forward-window names   exact agreement
    NBA      30                       30                         30 / 30
    NHL      32                       32                         32 / 32

"Forward-window" is `commence_time >= 2026-09-01`: 41 NBA rows and 32 NHL rows,
the whole of our inventory inside the season StatPal is serving. Every one of
them joined to a StatPal fixture on the normalised `(away, home)` pair, in the
same orientation, with no swap and no near-match needed.

## Our table holds a SECOND vocabulary, and it is dead

This is the one way NBA/NHL differ from the NFL, and it is worth stating before
someone rediscovers it as a wall of unmatched rows. Production also holds
city-only team names — `Toronto`, `Los Angeles C`, `New York I`, `Golden State` —
242 rows of them (126 NBA, 116 NHL). Measured bounds:

    games covered   2026-03-05 → 2026-05-20   (last season)
    last written    2026-03-24 / 2026-03-25   (`events.created_at`)

Nothing has written a city-only name in over five months, and no such row exists
anywhere in the 2026/27 season window. So this module does **not** bridge them:
a rule that maps `Los Angeles C` to a franchise is a rule that has to guess
between the Clippers and the Lakers from one letter, and the reward for guessing
right is a link nobody asked for on a game that finished in May. They are named
here so that a city-only row appearing in a future window is reported as
`UNKNOWN_TEAM_NAME` — loudly, by name — instead of vanishing into a miss count.

## Normalization is shared with the NFL module on purpose

:func:`app.utils.nfl_team_matching.normalize_team` and ``pair_matches`` are not
NFL logic. They are case-folding, accent-stripping, punctuation-stripping and
same-orientation pair equality, and they carry two things these leagues need:
`Montréal Canadiens` (which production spells both ways) folds onto
`Montreal Canadiens`, and `St Louis Blues` onto `St. Louis Blues` — both real
pairs in our own table today. Re-implementing that here would be a second copy
to keep in step, and renaming the NFL module to say so would edit a file that is
in front of the bus. Imported, and the misleading name is called out here.
"""

from __future__ import annotations

from typing import Optional

from app.utils.nfl_team_matching import normalize_team

#: The 30 franchises as BOTH sides spell them, measured 2026-09-04 against live
#: `GET /v1/nba/season-schedule` (1206 games) and production `events`. Identical
#: sets. Reporting only — see :func:`is_known_league_team`.
NBA_TEAM_NAMES: frozenset[str] = frozenset(
    normalize_team(n)
    for n in (
        "Atlanta Hawks",
        "Boston Celtics",
        "Brooklyn Nets",
        "Charlotte Hornets",
        "Chicago Bulls",
        "Cleveland Cavaliers",
        "Dallas Mavericks",
        "Denver Nuggets",
        "Detroit Pistons",
        "Golden State Warriors",
        "Houston Rockets",
        "Indiana Pacers",
        "Los Angeles Clippers",
        "Los Angeles Lakers",
        "Memphis Grizzlies",
        "Miami Heat",
        "Milwaukee Bucks",
        "Minnesota Timberwolves",
        "New Orleans Pelicans",
        "New York Knicks",
        "Oklahoma City Thunder",
        "Orlando Magic",
        "Philadelphia 76ers",
        "Phoenix Suns",
        "Portland Trail Blazers",
        "Sacramento Kings",
        "San Antonio Spurs",
        "Toronto Raptors",
        "Utah Jazz",
        "Washington Wizards",
    )
)

#: The 32 franchises as BOTH sides spell them, measured 2026-09-04 against live
#: `GET /v1/nhl/season-schedule` (1404 games) and production `events`.
#:
#: `Utah Mammoth` is here because that is what both sides serve today; the
#: franchise was renamed and this roster is a measurement of the current answer,
#: not a history of the league.
NHL_TEAM_NAMES: frozenset[str] = frozenset(
    normalize_team(n)
    for n in (
        "Anaheim Ducks",
        "Boston Bruins",
        "Buffalo Sabres",
        "Calgary Flames",
        "Carolina Hurricanes",
        "Chicago Blackhawks",
        "Colorado Avalanche",
        "Columbus Blue Jackets",
        "Dallas Stars",
        "Detroit Red Wings",
        "Edmonton Oilers",
        "Florida Panthers",
        "Los Angeles Kings",
        "Minnesota Wild",
        "Montreal Canadiens",
        "Nashville Predators",
        "New Jersey Devils",
        "New York Islanders",
        "New York Rangers",
        "Ottawa Senators",
        "Philadelphia Flyers",
        "Pittsburgh Penguins",
        "San Jose Sharks",
        "Seattle Kraken",
        "St. Louis Blues",
        "Tampa Bay Lightning",
        "Toronto Maple Leafs",
        "Utah Mammoth",
        "Vancouver Canucks",
        "Vegas Golden Knights",
        "Washington Capitals",
        "Winnipeg Jets",
    )
)

#: The 30 franchises, measured 2026-09-04 against the full MLB census — live
#: `GET /v1/mlb/season-schedule` (227 games) and `GET /v1/mlb/livescores` (16) —
#: and against production `events` over the same window (252 rows).
#:
#: **Both sides serve 31 distinct STRINGS for these 30 clubs, and it is the same
#: extra string on both: `St.Louis Cardinals` beside `St. Louis Cardinals`.** Our
#: table holds the split too (12 rows against 7 on 2026-09-04), so this is not a
#: provider quirk to absorb at the boundary — it is one club spelled two ways in
#: two vocabularies, and :func:`normalize_team` is what makes the comparison
#: exact rather than lucky. It strips the period and collapses the space, so both
#: reduce to `st louis cardinals`. Nothing here special-cases the club, and
#: nothing should: the day a second club gains a period, the same rule covers it.
#:
#: `Athletics` is city-less because that is what both sides serve today, the same
#: reasoning as NHL's `Utah Mammoth` above — this is a measurement of the current
#: answer, not a history of the league.
MLB_TEAM_NAMES: frozenset[str] = frozenset(
    normalize_team(n)
    for n in (
        "Arizona Diamondbacks",
        "Athletics",
        "Atlanta Braves",
        "Baltimore Orioles",
        "Boston Red Sox",
        "Chicago Cubs",
        "Chicago White Sox",
        "Cincinnati Reds",
        "Cleveland Guardians",
        "Colorado Rockies",
        "Detroit Tigers",
        "Houston Astros",
        "Kansas City Royals",
        "Los Angeles Angels",
        "Los Angeles Dodgers",
        "Miami Marlins",
        "Milwaukee Brewers",
        "Minnesota Twins",
        "New York Mets",
        "New York Yankees",
        "Philadelphia Phillies",
        "Pittsburgh Pirates",
        "San Diego Padres",
        "San Francisco Giants",
        "Seattle Mariners",
        "St. Louis Cardinals",
        "Tampa Bay Rays",
        "Texas Rangers",
        "Toronto Blue Jays",
        "Washington Nationals",
    )
)

#: Our `sports.key` -> the roster both sides were measured to share.
LEAGUE_TEAM_NAMES: dict[str, frozenset[str]] = {
    "basketball_nba": NBA_TEAM_NAMES,
    "icehockey_nhl": NHL_TEAM_NAMES,
    "baseball_mlb": MLB_TEAM_NAMES,
}

#: The dead city-only vocabulary, verbatim, so an appearance is recognisable
#: rather than merely unknown. Deliberately NOT matchable: see the module
#: docstring. Two of these — `Los Angeles` and `New York` — are also the reason
#: the others exist, since a bare city names two franchises in both leagues and
#: the disambiguating single letter is not something to match a game on.
DEAD_CITY_ONLY_NAMES: frozenset[str] = frozenset(
    normalize_team(n)
    for n in (
        "Atlanta", "Boston", "Brooklyn", "Charlotte", "Chicago", "Cleveland",
        "Dallas", "Denver", "Detroit", "Golden State", "Houston", "Indiana",
        "Los Angeles C", "Los Angeles L", "Memphis", "Miami", "Milwaukee",
        "Minnesota", "New Orleans", "New York", "Oklahoma City", "Orlando",
        "Philadelphia", "Phoenix", "Portland", "Sacramento", "San Antonio",
        "Toronto", "Utah", "Washington",
        "Anaheim", "Buffalo", "Calgary", "Carolina", "Colorado", "Columbus",
        "Edmonton", "Florida", "Los Angeles", "Montreal", "Nashville",
        "New Jersey", "New York I", "New York R", "Ottawa", "Pittsburgh",
        "San Jose", "Seattle", "St. Louis", "Tampa Bay", "Vancouver", "Vegas",
        "Winnipeg",
    )
)


def is_known_league_team(sport_key: Optional[str], name: Optional[str]) -> bool:
    """Is this one of the names both sides were measured to use for this league?

    Reports; never gates. The same reasoning as the NFL module: if both sides
    rename a franchise on the same day, matching keeps working and this roster
    goes stale loudly on the next read; if only one side renames, the mismatch
    surfaces as a named team instead of a silent zero. A sport with no roster
    here answers ``False`` for everything, which is the honest answer to "is this
    one of the names I measured" when nothing was measured.
    """
    roster = LEAGUE_TEAM_NAMES.get(str(sport_key or ""))
    if not roster:
        return False
    return normalize_team(name) in roster


def is_dead_city_only_name(name: Optional[str]) -> bool:
    """Is this the retired city-only spelling, e.g. `"Los Angeles C"`?

    A row carrying one of these inside a live window would mean the vocabulary
    came back, which is a finding about our ingestion and not about StatPal.
    """
    return normalize_team(name) in DEAD_CITY_ONLY_NAMES
