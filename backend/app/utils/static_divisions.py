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

#6246 — ONE VOCABULARY. A fallback is only a fallback if its labels are
interchangeable with the thing it stands in for. This map's were not: it said
"AFC" where live standings say "American Football Conference", and "AL Central"
where they say "Central". ``grouped_teams`` keys on the raw string, so a MIXED
population — some rows standings-backed, some map-backed, which is exactly the
offseason/preseason/regular-season transition this map exists for — rendered
four conference blocks for two conferences, with the Chargers and Steelers in a
two-team "AFC" table above the real one.

So the labels below are now the live-standings vocabulary, and
``canonical_conference`` / ``canonical_division`` fold the abbreviations back
into it for rows that arrive carrying them from anywhere else. Both halves
matter: fixing the table alone would leave the page one bad upstream row away
from splitting again.
"""

from __future__ import annotations

# nickname -> (conference, division). Nicknames are lowercase and matched as a
# suffix of the normalized team name.
_MLB: dict[str, tuple[str, str]] = {
    # American League
    "orioles": ("American League", "East"),
    "red sox": ("American League", "East"),
    "yankees": ("American League", "East"),
    "rays": ("American League", "East"),
    "blue jays": ("American League", "East"),
    "white sox": ("American League", "Central"),
    "guardians": ("American League", "Central"),
    "tigers": ("American League", "Central"),
    "royals": ("American League", "Central"),
    "twins": ("American League", "Central"),
    "astros": ("American League", "West"),
    "angels": ("American League", "West"),
    "athletics": ("American League", "West"),
    "mariners": ("American League", "West"),
    "rangers": ("American League", "West"),
    # National League
    "braves": ("National League", "East"),
    "marlins": ("National League", "East"),
    "mets": ("National League", "East"),
    "phillies": ("National League", "East"),
    "nationals": ("National League", "East"),
    "cubs": ("National League", "Central"),
    "reds": ("National League", "Central"),
    "brewers": ("National League", "Central"),
    "pirates": ("National League", "Central"),
    "cardinals": ("National League", "Central"),
    "diamondbacks": ("National League", "West"),
    "rockies": ("National League", "West"),
    "dodgers": ("National League", "West"),
    "padres": ("National League", "West"),
    "giants": ("National League", "West"),
}

_NFL: dict[str, tuple[str, str]] = {
    # AFC
    "bills": ("American Football Conference", "AFC East"),
    "dolphins": ("American Football Conference", "AFC East"),
    "patriots": ("American Football Conference", "AFC East"),
    "jets": ("American Football Conference", "AFC East"),
    "ravens": ("American Football Conference", "AFC North"),
    "bengals": ("American Football Conference", "AFC North"),
    "browns": ("American Football Conference", "AFC North"),
    "steelers": ("American Football Conference", "AFC North"),
    "texans": ("American Football Conference", "AFC South"),
    "colts": ("American Football Conference", "AFC South"),
    "jaguars": ("American Football Conference", "AFC South"),
    "titans": ("American Football Conference", "AFC South"),
    "broncos": ("American Football Conference", "AFC West"),
    "chiefs": ("American Football Conference", "AFC West"),
    "raiders": ("American Football Conference", "AFC West"),
    "chargers": ("American Football Conference", "AFC West"),
    # NFC
    "cowboys": ("National Football Conference", "NFC East"),
    "giants": ("National Football Conference", "NFC East"),
    "eagles": ("National Football Conference", "NFC East"),
    "commanders": ("National Football Conference", "NFC East"),
    "bears": ("National Football Conference", "NFC North"),
    "lions": ("National Football Conference", "NFC North"),
    "packers": ("National Football Conference", "NFC North"),
    "vikings": ("National Football Conference", "NFC North"),
    "falcons": ("National Football Conference", "NFC South"),
    "panthers": ("National Football Conference", "NFC South"),
    "saints": ("National Football Conference", "NFC South"),
    "buccaneers": ("National Football Conference", "NFC South"),
    "cardinals": ("National Football Conference", "NFC West"),
    "rams": ("National Football Conference", "NFC West"),
    "49ers": ("National Football Conference", "NFC West"),
    "seahawks": ("National Football Conference", "NFC West"),
}

# league slug / sport_key fragment -> nickname map. Accepts both the grid slug
# ("mlb", "nfl") and the Odds-API sport_key ("baseball_mlb", "americanfootball_nfl").
_LEAGUE_MAPS: dict[str, dict[str, tuple[str, str]]] = {
    "mlb": _MLB,
    "baseball_mlb": _MLB,
    "nfl": _NFL,
    "americanfootball_nfl": _NFL,
}


# ── #6246: the one vocabulary, and the aliases that fold into it ─────────────
#
# Keyed by the same league slugs / sport_keys as ``_LEAGUE_MAPS``, then by the
# lowercased incoming label. Deliberately an explicit alias table and not a
# prefix strip: "AL Central" -> "Central" by rule would also rewrite a league
# whose divisions are genuinely named that way, and a widening matched by
# grammar reaches populations this fix never reasoned about.
_CONFERENCE_ALIASES: dict[str, dict[str, str]] = {
    "nfl": {
        "afc": "American Football Conference",
        "nfc": "National Football Conference",
    },
    "mlb": {
        "al": "American League",
        "nl": "National League",
        "american": "American League",
        "national": "National League",
    },
}

_DIVISION_ALIASES: dict[str, dict[str, str]] = {
    "mlb": {
        "al east": "East",
        "al central": "Central",
        "al west": "West",
        "nl east": "East",
        "nl central": "Central",
        "nl west": "West",
    },
}

# The generic rule that lived inline in ``playoffs.py``, kept verbatim so
# leagues with no alias table (NBA, NHL, the college grids) are unchanged:
# only directional and league names earn a "Conference" suffix — never a named
# conference like "SEC", "Big Ten" or "ACC".
_CONFERENCE_SUFFIX_NAMES = frozenset({"eastern", "western", "american", "national"})

# Slug/sport_key -> the alias-table key, so both spellings reach the same rules.
_ALIAS_LEAGUE_KEYS: dict[str, str] = {
    "mlb": "mlb",
    "baseball_mlb": "mlb",
    "nfl": "nfl",
    "americanfootball_nfl": "nfl",
}


def _norm(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def _alias_key(league: str | None) -> str | None:
    return _ALIAS_LEAGUE_KEYS.get((league or "").strip().lower())


def canonical_conference(league: str | None, value: str | None) -> str | None:
    """Fold a conference ABBREVIATION into the vocabulary live standings use.

    This is the half that is safe everywhere: it only rewrites labels listed in
    a league's alias table, so it cannot touch a league this fix never measured.
    Unknown labels pass through untouched — it normalizes spelling, it never
    invents membership.

    The directional "Eastern" -> "Eastern Conference" suffix is deliberately NOT
    here. That rule has only ever run where `grouped_teams` is built, so the grid
    said "Eastern Conference" while the event page's Championship Path said
    "Eastern" off the same metadata. Widening it to both surfaces would be a
    reader-visible change on two leagues with no defect filed against them, so it
    stays in `grid_conference_key` where it already lived.
    """
    if not value or not value.strip():
        return value
    label = " ".join(value.strip().split())
    key = _alias_key(league)
    if key:
        aliased = _CONFERENCE_ALIASES.get(key, {}).get(label.lower())
        if aliased:
            return aliased
    return label


def grid_conference_key(league: str | None, value: str | None) -> str | None:
    """The string `grouped_teams` keys on — one block per conference (#6246).

    The alias fold, then the directional/league suffix rule exactly as it was
    written inline in ``playoffs.py``: only "Eastern"/"Western"/"American"/
    "National" earn a "Conference" suffix, never a named conference like "SEC",
    "Big Ten" or "ACC".
    """
    label = canonical_conference(league, value)
    if not label or not label.strip():
        return label
    lowered = label.lower()
    if (
        not lowered.endswith("conference")
        and not lowered.endswith("league")
        and lowered in _CONFERENCE_SUFFIX_NAMES
    ):
        return f"{label} Conference"
    return label


def canonical_division(league: str | None, value: str | None) -> str | None:
    """Fold a division label into the vocabulary live standings use.

    Scoped to the leagues that have an alias table. NHL's "Atlantic Division"
    and NBA's "Atlantic" are each internally consistent within their own league
    and are left exactly as they are.
    """
    if not value or not value.strip():
        return value
    label = " ".join(value.strip().split())
    key = _alias_key(league)
    if not key:
        return label
    return _DIVISION_ALIASES.get(key, {}).get(label.lower(), label)


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
