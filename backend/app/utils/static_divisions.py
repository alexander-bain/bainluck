"""Static conference/division map for MLB and NFL — the grid's division truth
when live standings are absent.

Queue #242 Item 1c (L2-162's filed gap): the championship-grid division race did
not render for MLB or NFL because ``Team.standings_data`` is ``NULL`` for every
team in those leagues (StatPal populates NBA/NHL standings with a nested
conference/division structure, but not MLB/NFL, and the NFL is dark all
offseason). Division/conference membership in these two leagues is stable and
does not depend on the schedule, so a static map is the reliable source — the
grid falls back to it whenever ``standings_data`` has no division label.

Pure data + a lookup; imports nothing (circular-import safe, like sport_keys).
Keyed by team NICKNAME (unambiguous within a single league) matched as a suffix
of the team's full name, so "New York Yankees" and "Chicago White Sox" both
resolve. Cross-league nickname clashes (Cardinals, Giants, Rangers) are resolved
by scoping the lookup to the requested league.
"""

from __future__ import annotations

# nickname -> (conference, division). Nicknames are lowercase and matched as a
# suffix of the normalized team name.
_MLB: dict[str, tuple[str, str]] = {
    # American League
    "orioles": ("American League", "AL East"),
    "red sox": ("American League", "AL East"),
    "yankees": ("American League", "AL East"),
    "rays": ("American League", "AL East"),
    "blue jays": ("American League", "AL East"),
    "white sox": ("American League", "AL Central"),
    "guardians": ("American League", "AL Central"),
    "tigers": ("American League", "AL Central"),
    "royals": ("American League", "AL Central"),
    "twins": ("American League", "AL Central"),
    "astros": ("American League", "AL West"),
    "angels": ("American League", "AL West"),
    "athletics": ("American League", "AL West"),
    "mariners": ("American League", "AL West"),
    "rangers": ("American League", "AL West"),
    # National League
    "braves": ("National League", "NL East"),
    "marlins": ("National League", "NL East"),
    "mets": ("National League", "NL East"),
    "phillies": ("National League", "NL East"),
    "nationals": ("National League", "NL East"),
    "cubs": ("National League", "NL Central"),
    "reds": ("National League", "NL Central"),
    "brewers": ("National League", "NL Central"),
    "pirates": ("National League", "NL Central"),
    "cardinals": ("National League", "NL Central"),
    "diamondbacks": ("National League", "NL West"),
    "rockies": ("National League", "NL West"),
    "dodgers": ("National League", "NL West"),
    "padres": ("National League", "NL West"),
    "giants": ("National League", "NL West"),
}

_NFL: dict[str, tuple[str, str]] = {
    # AFC
    "bills": ("AFC", "AFC East"),
    "dolphins": ("AFC", "AFC East"),
    "patriots": ("AFC", "AFC East"),
    "jets": ("AFC", "AFC East"),
    "ravens": ("AFC", "AFC North"),
    "bengals": ("AFC", "AFC North"),
    "browns": ("AFC", "AFC North"),
    "steelers": ("AFC", "AFC North"),
    "texans": ("AFC", "AFC South"),
    "colts": ("AFC", "AFC South"),
    "jaguars": ("AFC", "AFC South"),
    "titans": ("AFC", "AFC South"),
    "broncos": ("AFC", "AFC West"),
    "chiefs": ("AFC", "AFC West"),
    "raiders": ("AFC", "AFC West"),
    "chargers": ("AFC", "AFC West"),
    # NFC
    "cowboys": ("NFC", "NFC East"),
    "giants": ("NFC", "NFC East"),
    "eagles": ("NFC", "NFC East"),
    "commanders": ("NFC", "NFC East"),
    "bears": ("NFC", "NFC North"),
    "lions": ("NFC", "NFC North"),
    "packers": ("NFC", "NFC North"),
    "vikings": ("NFC", "NFC North"),
    "falcons": ("NFC", "NFC South"),
    "panthers": ("NFC", "NFC South"),
    "saints": ("NFC", "NFC South"),
    "buccaneers": ("NFC", "NFC South"),
    "cardinals": ("NFC", "NFC West"),
    "rams": ("NFC", "NFC West"),
    "49ers": ("NFC", "NFC West"),
    "seahawks": ("NFC", "NFC West"),
}

# league slug / sport_key fragment -> nickname map. Accepts both the grid slug
# ("mlb", "nfl") and the Odds-API sport_key ("baseball_mlb", "americanfootball_nfl").
_LEAGUE_MAPS: dict[str, dict[str, tuple[str, str]]] = {
    "mlb": _MLB,
    "baseball_mlb": _MLB,
    "nfl": _NFL,
    "americanfootball_nfl": _NFL,
}


def _norm(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def lookup_division(league: str, team_name: str) -> tuple[str | None, str | None]:
    """Return (conference, division) for a team in MLB or NFL, or (None, None).

    ``league`` may be a grid slug ("mlb") or a sport_key ("baseball_mlb").
    Matches the team's nickname as a suffix of its (normalized) full name;
    longer nicknames ("white sox") are tried before shorter ones so a "sox"
    suffix never mis-resolves.
    """
    table = _LEAGUE_MAPS.get((league or "").strip().lower())
    if not table:
        return (None, None)
    norm = _norm(team_name)
    if not norm:
        return (None, None)
    for nickname in sorted(table, key=len, reverse=True):
        if norm == nickname or norm.endswith(" " + nickname):
            return table[nickname]
    return (None, None)
