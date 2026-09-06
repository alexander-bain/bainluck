"""Pure attach logic: which StatPal fixture's injuries belong to which event.

Kept out of the task so it can be tested without a database, and kept small so
the rule it enforces is readable in one screen:

    an event takes a fixture's injuries only when BOTH sides match, in the
    orientation we hold them, and only when exactly ONE fixture qualifies.

Why both sides. The code this replaces matched one team at a time with
``key.endswith(team_lower.split()[-1])``, which is satisfied by any club whose
last word agrees — "Wanderers", "United", "City". While the injury fetch was
404ing that cost nothing, because the loop never had a row to hang. The change
that makes real rows flow is the change that would have started hanging another
club's injured player on the wrong game, so the two belong in one commit.

Why exactly one. Ambiguity is refused, never guessed: two candidate fixtures
mean we do not know which game we are looking at, and an injury list attributed
to the wrong game is worse on the page than no injury list at all.

Measured against production 2026-09-06 (168 soccer events in the attach window x
146 StatPal fixtures carrying injuries): 45 exact pairs, 18 subset pairs, **0
ambiguous**, 105 with no candidate at all — those are leagues StatPal's injury
product does not cover, which is an absence at the venue and not a matching bug.
Strict orientation cost nothing: 0 events matched only when the sides were
swapped, so a reverse-leg fixture can never be silently accepted.

This module is NOT the event graph (D39/#2693 is lane1's). It joins a vendor
payload to an event that already exists; it never creates, merges or renames one.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Iterable, NamedTuple, Optional

from app.utils.name_normalization import normalize_team_name

#: Tokens that carry no identity in a club name — legal forms and sport words
#: that appear on one side of a naming and not the other ("FC Twente Enschede"
#: vs "Twente", "SV Zulte-Waregem" vs "Waregem"). Deliberately short: every
#: token dropped here is one fewer thing distinguishing two clubs, so it holds
#: only forms that are never the whole name of anything.
_NOISE_TOKENS = frozenset({
    "fc", "cf", "sc", "afc", "ac", "cd", "ud", "sv", "bk", "if", "ff", "fk",
    "sk", "club", "deportivo", "de", "the",
})

_NON_ALNUM = re.compile(r"[^a-z0-9 ]")


def team_tokens(name: Optional[str]) -> frozenset[str]:
    """Identity tokens of a club name, diacritics and legal forms removed.

    Falls back to the un-stripped tokens when stripping would empty the set, so
    a club actually called "FC" (or a one-noise-word name) still compares as
    something rather than matching everything.
    """
    normalized = _NON_ALNUM.sub(" ", normalize_team_name(name or ""))
    raw = [token for token in normalized.split() if token]
    stripped = frozenset(token for token in raw if token not in _NOISE_TOKENS)
    return stripped or frozenset(raw)


def sides_agree(ours: frozenset[str], theirs: frozenset[str]) -> bool:
    """One side of a fixture, matched by containment in either direction.

    "Groningen" vs "FC Groningen", "Rizespor" vs "Caykur Rizespor": one naming
    is a qualified form of the other. Containment accepts those and still
    separates "Manchester United" from "Manchester City", because neither token
    set contains the other. An empty set never matches — it would contain
    everything.
    """
    if not ours or not theirs:
        return False
    return ours == theirs or ours <= theirs or theirs <= ours


class Fixture(NamedTuple):
    """One vendor fixture, reduced to what the attach decision needs."""

    key: str
    home: str
    away: str
    fixture_date: Optional[date]


def choose_fixture(
    home_team: str,
    away_team: str,
    event_date: Optional[date],
    fixtures: Iterable[Fixture],
) -> Optional[str]:
    """The key of the one fixture these two teams are playing, or None.

    `event_date` breaks a tie and nothing more: it is consulted only when two or
    more fixtures already matched on both names, so a fixture whose date failed
    to parse can never be excluded by it. Still ambiguous after the tiebreak =
    no attach.
    """
    ours_home = team_tokens(home_team)
    ours_away = team_tokens(away_team)
    if not ours_home or not ours_away:
        return None

    hits = [
        fixture
        for fixture in fixtures
        if sides_agree(ours_home, team_tokens(fixture.home))
        and sides_agree(ours_away, team_tokens(fixture.away))
    ]
    if len(hits) == 1:
        return hits[0].key
    if not hits:
        return None

    if event_date is not None:
        same_day = [f for f in hits if f.fixture_date == event_date]
        if len(same_day) == 1:
            return same_day[0].key
    return None
