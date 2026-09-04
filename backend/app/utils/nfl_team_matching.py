"""Does this StatPal NFL team name and ours name the same franchise? #2867 / D50.

## Why this is a different problem from tennis, and gets a different answer

`app/utils/tennis_name_matching` is 240 lines because tennis names genuinely
disagree: StatPal writes `Y. Bu` where we write `Bu Yunchaokete`, and reading one
into the other needs an initial-and-surname grammar.

**NFL does not have that problem, and it is worth saying so with a measurement
rather than an assumption.** Measured 2026-09-03/04 against the banked
`season-schedule` body and against production:

    StatPal's distinct NFL team names   32
    our distinct NFL team names         32
    exact string agreement              32 / 32

So the rule here is *equality after normalization*, and the normalization exists
to absorb rendering noise (case, punctuation, doubled spaces, a non-breaking
space in a copied string), **not** to bridge a real naming difference. There is
nothing to bridge.

## The rule is deliberately unforgiving, because the alternative is a wrong game

The temptation with a 32-name closed vocabulary is a nickname or city fallback:
match on the last token, or on `los angeles`. Both are wrong here for reasons
already in this codebase's data:

  * **`Los Angeles` names two franchises.** Production holds two Week-1 rows for
    one Chargers fixture — `Los Angeles Rams v Arizona Cardinals` and
    `Los Angeles Chargers v Arizona Cardinals` at the same 2026-09-13 20:25 —
    where StatPal has only the Chargers game. A city-token fallback would link
    the phantom as confidently as the real one.
  * **`New York` and the two `New York` teams** have the same shape, as do the
    two `Los Angeles` teams in the 2026-09-11 pair (`Rams v 49ers` and
    `Chargers v 49ers`, one of which is a phantom).

A rule that cannot express "I do not recognise this" will express something
else. So: full-name equality after normalization, and an unrecognised name is
reported by name rather than approximated.

## `is_known_nfl_team` reports; it never gates

The 32-name roster below is used to *label a miss* — `UNKNOWN_TEAM_NAME` reads
very differently from `NO_CANDIDATE` when a person is triaging receipts — and it
is deliberately NOT consulted by :func:`teams_match`. If both sides rename a
franchise on the same day, matching should keep working and the roster should go
stale loudly on the next read; if only one side renames, the mismatch surfaces as
a named team rather than as a silent zero. Gating the match on the roster would
invert both of those.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

#: Everything that is not a letter, a digit or a space. The `49ers` keep their
#: digits; `St. Louis`-style punctuation and any stray hyphen are dropped.
_NOISE_RE = re.compile(r"[^a-z0-9 ]+")
_SPACES_RE = re.compile(r"\s+")


def normalize_team(name: Optional[str]) -> str:
    """`" San  Francisco 49ers "` -> `"san francisco 49ers"`. `""` for nothing.

    An empty string out is the honest answer for an empty string in, and
    :func:`teams_match` refuses it — a normalizer that returned `None` would push
    the same check onto every caller.
    """
    if not name:
        return ""
    # NFKC first so a non-breaking space becomes a space before the space
    # collapse runs, rather than surviving into the noise strip as a letter.
    folded = unicodedata.normalize("NFKC", str(name))
    folded = unicodedata.normalize("NFKD", folded)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = _NOISE_RE.sub(" ", folded.lower())
    return _SPACES_RE.sub(" ", folded).strip()


def team_matches(statpal_name: Optional[str], our_name: Optional[str]) -> bool:
    """Same franchise? Equality after normalization, and nothing looser.

    Empty on either side is `False`, never a match: absence has never been
    evidence, and a blank team name matching a blank one would pair two broken
    rows and call it a link.
    """
    a = normalize_team(statpal_name)
    b = normalize_team(our_name)
    if not a or not b:
        return False
    return a == b


def pair_matches(
    statpal_pair: tuple[Optional[str], Optional[str]],
    our_pair: tuple[Optional[str], Optional[str]],
) -> bool:
    """Both sides of the fixture, in the SAME orientation.

    Home matches home and away matches away. The orientation is not a detail we
    can be relaxed about: measured over the 16 Week-1 games in the banked
    `season-schedule` body against production, StatPal's `home`/`away` and ours
    agree on every one, so accepting the swapped orientation would buy nothing
    and would silently pair a game with its own reverse fixture later in the
    season — the two meetings of a division rival are a real pair of rows.
    """
    return team_matches(statpal_pair[0], our_pair[0]) and team_matches(
        statpal_pair[1], our_pair[1]
    )


#: The 32 franchises as BOTH sides spell them, measured 2026-09-03/04 (StatPal
#: `season-schedule`) and 2026-09-04 (production `events`). Identical sets.
#:
#: Reporting only — see the module docstring. A name absent from here is still
#: matched normally; it is just labelled so a rename is a finding rather than a
#: zero.
NFL_TEAM_NAMES: frozenset[str] = frozenset(
    normalize_team(n)
    for n in (
        "Arizona Cardinals",
        "Atlanta Falcons",
        "Baltimore Ravens",
        "Buffalo Bills",
        "Carolina Panthers",
        "Chicago Bears",
        "Cincinnati Bengals",
        "Cleveland Browns",
        "Dallas Cowboys",
        "Denver Broncos",
        "Detroit Lions",
        "Green Bay Packers",
        "Houston Texans",
        "Indianapolis Colts",
        "Jacksonville Jaguars",
        "Kansas City Chiefs",
        "Las Vegas Raiders",
        "Los Angeles Chargers",
        "Los Angeles Rams",
        "Miami Dolphins",
        "Minnesota Vikings",
        "New England Patriots",
        "New Orleans Saints",
        "New York Giants",
        "New York Jets",
        "Philadelphia Eagles",
        "Pittsburgh Steelers",
        "San Francisco 49ers",
        "Seattle Seahawks",
        "Tampa Bay Buccaneers",
        "Tennessee Titans",
        "Washington Commanders",
    )
)


def is_known_nfl_team(name: Optional[str]) -> bool:
    """Is this one of the 32 names both sides were measured to use?"""
    return normalize_team(name) in NFL_TEAM_NAMES
