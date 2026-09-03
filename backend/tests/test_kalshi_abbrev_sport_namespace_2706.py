"""#2706 — a Kalshi ticker never borrows another sport's team abbreviations.

WHAT WENT WRONG. ``_KALSHI_TEAM_ABBREVS`` is namespaced by sport suffix (``_nhl``,
``_mlb``, ``_mls``, ``_soc``, ``_wnba``) — but the NBA block holds the UNSUFFIXED
keys and the NFL block was written unsuffixed too, so it only ever won the
abbreviations the NBA does not claim. For all twelve NBA/NFL shared cities the
lookup's ``or`` fallback walked straight into the NBA namespace::

    get("atl_nfl") -> None -> get("atl") -> "Hawks"

So ``KXNFLGAME-26SEP13ATLPIT`` — a market Kalshi titles *"ATL Falcons vs PIT
Steelers"* — was searched for as **Hawks**, matched nothing, and was filed under
``name_mismatch``. Same for ``PHI`` -> 76ers, ``MIA`` -> Heat, ``CLE`` ->
Cavaliers, ``DET`` -> Pistons, and for MLS ``NSH`` -> Predators (NHL) and ``NE``
-> Patriots (NFL).

THE TICKERS BELOW ARE NOT INVENTED. Every one in ``BLOCKED_BY_THE_COLLISION`` was
read off ``market_match_receipts`` on production on 2026-09-03, where it sat
rejected with ``reject_reason='name_mismatch'``. 73 of the 155 open
``name_mismatch`` receipts (47%) were this one shape
(``ARTIFACT-LANE1B-006-name-mismatch-shapes-2026-09-02.md``).

WHY THERE ARE THREE ARMS. A test that only asserts the NFL answers would pass if
someone deleted the NBA block entirely, so ``UNCHANGED_BY_THE_FIX`` pins the
sports that were already right — including the NFL tickers that never collided.
And a fixed data table goes stale the moment a bare key is added, so
``test_every_bare_abbreviation_declares_which_sport_owns_it`` fails CI if the map
and the ownership table ever drift apart. That is the guard on the *class*; the
ticker lists are the guard on the *cases*.
"""

from __future__ import annotations

import pytest

from app.utils.prediction_market_matching import (
    _KALSHI_TEAM_ABBREVS,
    _SPORT_ABBREV_SUFFIX,
    extract_team_codes_from_ticker,
    extract_teams_from_ticker,
)

# _BARE_ABBREV_OWNER and _resolve_team_abbrev are imported lazily inside the
# ownership tests. A module-level import of a symbol the fix introduces turns
# the whole file into a COLLECTION ERROR before the fix, which would make the
# case arms below vacuous rather than red — the red has to be an assertion.

# ---------------------------------------------------------------------------
# The cases: tickers that production filed as name_mismatch, and the answer
# Kalshi's own market title already contained.
# ---------------------------------------------------------------------------

#: (ticker, expected_team_a, expected_team_b, what production resolved instead)
BLOCKED_BY_THE_COLLISION = [
    # ---- NFL tickers that resolved to the NBA team sharing the city code ----
    ("KXNFLGAME-26SEP13ATLPIT", "Falcons", "Steelers", "Hawks"),
    ("KXNFLGAME-26SEP13BALIND", "Ravens", "Colts", "Pacers"),
    ("KXNFLGAME-26SEP13BUFHOU", "Bills", "Texans", "Rockets"),
    ("KXNFLGAME-26SEP13DALNYG", "Cowboys", "Giants", "Mavericks"),
    ("KXNFLGAME-26SEP13GBMIN", "Packers", "Vikings", "Timberwolves"),
    ("KXNFLGAME-26SEP13MIALV", "Dolphins", "Raiders", "Heat"),
    ("KXNFLGAME-26SEP13NODET", "Saints", "Lions", "Pistons"),
    ("KXNFLGAME-26SEP14DENKC", "Broncos", "Chiefs", "Nuggets"),
    ("KXNFLGAME-26SEP17DETBUF", "Lions", "Bills", "Pistons"),
    ("KXNFLGAME-26SEP20CINHOU", "Bengals", "Texans", "Rockets"),
    ("KXNFLGAME-26SEP20CLETB", "Browns", "Buccaneers", "Cavaliers"),
    ("KXNFLGAME-26SEP20INDKC", "Colts", "Chiefs", "Pacers"),
    ("KXNFLGAME-26SEP20MIASF", "Dolphins", "49ers", "Heat"),
    ("KXNFLGAME-26SEP20PHITEN", "Eagles", "Titans", "76ers"),
    # Half/quarter props ride the same parse.
    ("KXNFL1HSPREAD-26SEP13ATLPIT", "Falcons", "Steelers", "Hawks"),
    ("KXNFL2HTOTAL-26SEP13NODET", "Saints", "Lions", "Pistons"),
    # Per-team outcome markets append "-TEAM"; the suffix strip must survive too.
    ("KXNFLGAME-26SEP13BALIND-BAL", "Ravens", "Colts", "Pacers"),
    # ---- MLS tickers that resolved to the NHL / NFL team ----
    ("KXMLSGAME-26AUG15NSHMIA", "Nashville SC", "Inter Miami", "Predators"),
    ("KXMLSGAME-26SEP04NYCNSH", "New York City FC", "Nashville SC", "Predators"),
    ("KXMLSGAME-26SEP09TORNSH", "Toronto FC", "Nashville SC", "Predators"),
    ("KXMLSGAME-26AUG29CLBNE", "Columbus Crew", "New England Revolution", "Patriots"),
    ("KXMLSGAME-26SEP09NYCNE", "New York City FC", "New England Revolution", "Patriots"),
]

#: The other arm. These resolved correctly BEFORE the fix and must not move —
#: without them, deleting the NBA/NHL/MLB blocks would still pass the arm above.
UNCHANGED_BY_THE_FIX = [
    # NBA keeps the unsuffixed namespace it has always owned.
    ("KXNBAGAME-26FEB21DETCHI", "Pistons", "Bulls"),
    ("KXNBAGAME-26APR28BOSPHI", "Celtics", "76ers"),
    ("KXNBAGAME-26MAR03MIAATL", "Heat", "Hawks"),
    ("KXNBAGAME-26JAN14DENMIN", "Nuggets", "Timberwolves"),
    # NFL codes the NBA never claimed were already right.
    ("KXNFL2HSPREAD-26AUG27SFLV", "49ers", "Raiders"),
    ("KXNFLGAME-26AUG28WASBAL-BAL", "Commanders", "Ravens"),
    # MLB / NHL / MLS namespaces are untouched.
    ("KXMLBGAME-26AUG171910SDNYM", "Padres", "Mets"),
    ("KXMLBGAME-26JUL191420MINCHC", "Twins", "Cubs"),
    ("KXNHLGAME-26JAN02NSHCOL", "Predators", "Avalanche"),
    ("KXMLSGAME-26SEP05SEACHI", "Seattle Sounders", "Chicago Fire"),
]


@pytest.mark.parametrize(
    "ticker,team_a,team_b,was", BLOCKED_BY_THE_COLLISION, ids=lambda v: str(v)[:34]
)
def test_a_ticker_resolves_inside_its_own_sport(ticker, team_a, team_b, was):
    """RED before the fix: every one of these returned ``was`` for one side."""
    got = extract_teams_from_ticker(ticker)
    assert got == (team_a, team_b), (
        f"{ticker} resolved to {got}, expected {(team_a, team_b)}. "
        f"Production filed this market as name_mismatch because one side came "
        f"back as {was!r} — a team from another sport."
    )


@pytest.mark.parametrize(
    "ticker,team_a,team_b", UNCHANGED_BY_THE_FIX, ids=lambda v: str(v)[:34]
)
def test_the_sports_that_were_already_right_do_not_move(ticker, team_a, team_b):
    assert extract_teams_from_ticker(ticker) == (team_a, team_b)


def test_the_codes_half_still_travels_with_the_names():
    """``extract_team_codes_from_ticker`` is the disambiguator display callers
    need (gotcha #16, #2060 item 3). The fix must not drop the code half."""
    pair = extract_team_codes_from_ticker("KXNFLGAME-26SEP20PHITEN")
    assert pair == (("phi", "Eagles"), ("ten", "Titans"))


# ---------------------------------------------------------------------------
# The class guard: ownership, not a fixed list of cases.
# ---------------------------------------------------------------------------


def _bare_abbrev_owner():
    from app.utils.prediction_market_matching import _BARE_ABBREV_OWNER

    return _BARE_ABBREV_OWNER


def test_every_bare_abbreviation_declares_which_sport_owns_it():
    """The bug was an undeclared owner: ``atl`` belonged to the NBA, nothing said
    so, and the NFL borrowed it. A bare key with no owner can be borrowed again,
    so adding one without declaring it reddens CI here."""
    bare = {k for k in _KALSHI_TEAM_ABBREVS if "_" not in k}
    undeclared = sorted(bare - set(_bare_abbrev_owner()))
    assert not undeclared, (
        f"{len(undeclared)} unsuffixed abbreviation(s) do not say which sport owns "
        f"them, so another sport's ticker can fall back onto them: {undeclared}. "
        f"Add each to _BARE_ABBREV_OWNER."
    )


def test_ownership_is_not_claimed_for_abbreviations_that_do_not_exist():
    """The inverse drift: an owner entry for a deleted key would silently block a
    fallback that no longer needs blocking."""
    orphans = sorted(set(_bare_abbrev_owner()) - set(_KALSHI_TEAM_ABBREVS))
    assert not orphans, f"_BARE_ABBREV_OWNER names abbreviations that are gone: {orphans}"


def test_no_sport_can_resolve_a_team_owned_by_another_sport():
    """THE CLASS. For every sport with its own namespace, every bare abbreviation
    owned by a DIFFERENT sport must either resolve inside the asking sport or not
    resolve at all — it may never return the owner's team."""
    from app.utils.prediction_market_matching import _resolve_team_abbrev

    leaks = []
    for suffix in sorted({s for s in _SPORT_ABBREV_SUFFIX.values() if s}):
        for abbrev, owner in _bare_abbrev_owner().items():
            if owner == suffix:
                continue
            got = _resolve_team_abbrev(abbrev, suffix)
            if got is not None and got == _KALSHI_TEAM_ABBREVS[abbrev]:
                # Allowed only if this sport genuinely has the same team name.
                if _KALSHI_TEAM_ABBREVS.get(abbrev + suffix) != got:
                    leaks.append(f"{abbrev!r} ({owner}) leaked into {suffix} as {got!r}")
    assert not leaks, "cross-sport abbreviation leak:\n  " + "\n  ".join(leaks)


def test_an_unknown_abbreviation_refuses_rather_than_guessing():
    """A sport-scoped miss must be a miss. Returning the wrong team is worse than
    returning nothing: nothing falls through to the title parse, which for these
    markets carries the right answer ('PHI Eagles vs TEN Titans')."""
    assert extract_teams_from_ticker("KXNFLGAME-26SEP13ZZZQQQ") is None


def test_the_nfl_namespace_covers_every_team_in_the_league():
    """The collision only bit the twelve shared cities, but a partial namespace is
    how it happened. All 32 must be present or the next shared code reopens it."""
    nfl = {v for k, v in _KALSHI_TEAM_ABBREVS.items() if k.endswith("_nfl")}
    assert len(nfl) == 32, f"expected 32 NFL teams in the _nfl namespace, found {len(nfl)}: {sorted(nfl)}"
