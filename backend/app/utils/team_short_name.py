"""The compact label for a club, on the server side (#7798).

THIS IS THE THIRD IMPLEMENTATION AND IT IS DELIBERATE, NOT AN OVERSIGHT.
`frontend/lib/teamShortName.ts` and `ios/.../Utilities/TeamShortName.swift` are
the other two, and `teamDesignatorParityAcrossClients.test.ts` exists precisely
to stop a third copy drifting. So that guard reads THIS FILE too, out of source,
the same way it reads the Swift — a transcribed copy is the thing it prevents.

It has to exist on the server because the server is where the defect was. The
clients shorten a name they are GIVEN; `playoffs.py` MINTS one into the payload,
and #7798 measured what that mint served: `Leeds United` -> **"United"** and
`Atletico Madrid` -> **"Madrid"**, each handing a club another club's common
name on an iPhone Championship Path card. No client rule can repair a label that
arrived already wrong.

SCOPE IS NARROWER THAN THE CLIENTS' ON PURPOSE. The clients own the person/club
question (`namesAPerson`, #4624), doubles pairs (#3110), particled surnames
(#7163) and the hand-picked table (#4627). None of those reach this call site:
the one caller is the grid's team-metadata lookup, which fires only for rows
that HAVE a `teams` row, and every competitor without one — all 132 golf players
on the grid, measured 2026-09-21 — is served its full name by a different line
and never arrives here. Porting the person rules would be porting dead code, and
dead code is how the two sets drift apart. Only the designator set is shared,
and only the designator set is what the parity guard compares.
"""

import re

from app.config.college_mascots import ESPN_COLLEGE_MASCOTS

#: Trailing words that name a club TYPE rather than a club.
#:
#: Byte-for-byte the web's `CLUB_TYPE_SUFFIXES`, and the parity guard asserts
#: that rather than trusting this comment. Do not add a token here alone — a
#: designator that is not in all three sets is the drift the guard is for.
CLUB_TYPE_SUFFIXES: frozenset[str] = frozenset(
    {
        "united",
        "city",
        "town",
        "state",
        "rovers",
        "wanderers",
        "albion",
        "county",
        "athletic",
        "calcio",
        "club",
        "academy",
        "sporting",
        "afc",
        "wfc",
        "sad",
        "lfc",
        "pfk",
        "nps",
        "cfc",
        "aik",
        "tsv",
        "vfb",
        "vfl",
        "bsc",
        "ssc",
        "psv",
        "gif",
        "bif",
        "fsv",
        "spvgg",
        "rkc",
        "nec",
        "atletico",
        "women",
        "res",
    }
)

_NON_ALPHANUMERIC = re.compile(r"[^A-Za-z0-9]")
_SQUAD_MARKER = re.compile(r"\A[Uu][0-9]{1,2}\Z")
_ROMAN_RESERVE = re.compile(r"\A[Ii]{2,3}\Z")


def is_non_distinctive_trailing_word(token: str | None) -> bool:
    """Is this trailing word incapable of identifying the club on its own?

    The web's clause-for-clause twin. The `<= 2` rule is a LENGTH test rather
    than a list — "FC", "SC", "CF", "HC", "AC" are all caught without naming
    one — and #4250 is the lesson that it stops one letter short of the club
    initials it looks like it covers, which is why the three- and four-letter
    designators are enumerated above.
    """
    bare = _NON_ALPHANUMERIC.sub("", token or "")
    if len(bare) <= 2:
        return True  # includes the empty string
    if bare.lower() in CLUB_TYPE_SUFFIXES:
        return True
    if _SQUAD_MARKER.match(bare):
        return True  # "U21", "U23"
    if bare.isdigit():
        return True  # a bare reserve number
    if _ROMAN_RESERVE.match(bare):
        return True  # "Ludogorets III"; "II" and "IV" fall to the length rule
    return False


#: Ruling 194-A (Alex, Nov 14): a college team's short name is the SCHOOL, never
#: the mascot — "Duke", "Alabama", "Gonzaga", "Ole Miss"; not "Blue Devils",
#: "Crimson Tide", "Bulldogs" ("Bulldogs" could be five schools). Professional
#: teams are unchanged.
#:
#: The mascots below are the fallback for a team whose ESPN `location` we do not
#: hold or cannot trust. Longest first, so "Blue Devils" is tried before "Devils".
COLLEGE_MASCOTS: tuple[str, ...] = tuple(sorted({
    "Blue Devils", "Crimson Tide", "Tar Heels", "Fighting Irish", "Golden Eagles",
    "Red Raiders", "Nittany Lions", "Horned Frogs", "Yellow Jackets", "Sun Devils",
    "Demon Deacons", "Scarlet Knights", "Bulldogs", "Rebels", "Wildcats", "Tigers",
    "Eagles", "Bears", "Cougars", "Huskies", "Spartans", "Wolverines", "Buckeyes",
    "Hoosiers", "Boilermakers", "Illini", "Hawkeyes", "Badgers", "Gators",
    "Volunteers", "Commodores", "Razorbacks", "Aggies", "Longhorns", "Sooners",
    "Jayhawks", "Cyclones", "Mountaineers", "Bruins", "Trojans", "Ducks", "Beavers",
    "Cardinals", "Cardinal", "Cavaliers", "Hokies", "Seminoles", "Hurricanes",
    "Orangemen", "Orange",
} | ESPN_COLLEGE_MASCOTS, key=lambda m: (-len(m), m)))
_COLLEGE_MASCOT_RE = re.compile(
    r"\s+(?:" + "|".join(re.escape(m).replace(r"\ ", r"\s+") for m in COLLEGE_MASCOTS) + r")\Z",
    re.IGNORECASE,
)


def is_college_sport(sport_key: str | None) -> bool:
    """`basketball_ncaab`, `basketball_wncaab`, `americanfootball_ncaaf`, ..."""
    key = (sport_key or "").lower()
    return "ncaa" in key or "college" in key


def school_label(name: str | None, location: str | None = None) -> str | None:
    """A college team's school (194-A), failing safe to the full name.

    ESPN's `location` IS the school ("Duke", "Ole Miss", "Texas A&M"), but it is
    trusted only when the team's own name starts with it: on 2026-11-15 the
    `stanford-cardinal` row served `location: "Arkansas"`, and a school name
    borrowed from another row is worse than the mascot it replaces. Otherwise a
    known mascot is cut off the end; otherwise the full name is served. It never
    emits a word the team is not called.
    """
    if not name:
        return None
    cleaned = " ".join(name.split())
    loc = " ".join((location or "").split())
    if loc and (cleaned.lower() == loc.lower() or cleaned.lower().startswith(loc.lower() + " ")):
        return loc
    stripped = _COLLEGE_MASCOT_RE.sub("", cleaned).strip()
    return stripped or cleaned


def compact_team_label(
    name: str | None,
    abbreviation: str | None = None,
    *,
    sport_key: str | None = None,
    location: str | None = None,
) -> str | None:
    """The label a grid row should carry, or ``None`` when we know neither.

    FAILS SAFE BY CONSTRUCTION, which is the property worth keeping: every
    branch returns the abbreviation, the full name, or the last word of the
    name. It can never emit a string the club is not called, and the only
    direction it moves is "less short, more correct".

    THE ABBREVIATION IS PREFERRED, AND SAYING SO FIXES A PRECEDENCE BUG.
    The line this replaced read ``team.abbreviation or team.name.split()[-1]
    if team.name else None``, which Python parses as
    ``(abbreviation or last_word) if name else None`` — so a row with a good
    abbreviation and no ``name`` served ``short_name: null``, the one case the
    ``abbreviation or`` was written to cover.

    Measured over the whole served grid population — 530 rows across all 14
    configured leagues, 379 of them backed by a `teams` row, 2026-09-21 18:4xZ:
    **4 rows change and 375 are byte-identical**, and every one of the four is
    a correction that a reader can check.

        champions-league  Manchester United  ->  was "United"
        epl               Coventry City      ->  was "City"
        epl               Hull City          ->  was "City"
        mls               Los Angeles FC     ->  was "FC"

    Coventry and Hull were serving the SAME label on one grid while Manchester
    City served "MNC" (#7676 is the missing-`espn_id` half of those two rows;
    this is the label half, and it needs no anchor).

    The 151 grid rows with no `teams` row — 132 golf players among them — do
    not reach this function at all: `playoffs.py`'s row builder falls back to
    the full display name for those, which is already what they serve. They are
    named here because shortening them to a surname is exactly the regression
    this function must never cause, and "it is not reachable" is the reason.
    """
    if abbreviation:
        return abbreviation
    if not name:
        return None
    if is_college_sport(sport_key):
        # 194-A: never the last word for a college team; that word is the mascot.
        return school_label(name, location)
    words = name.split()
    if len(words) < 2:
        return name
    if is_non_distinctive_trailing_word(words[-1]):
        return name
    return words[-1]
