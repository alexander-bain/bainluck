"""Q458 (#2335) — a school with an ampersand in its name reaches its own game.

`_BARE_MATCHUP_RE` and `_DASH_MATCHUP_RE` are the only two matchup patterns in
`prediction_market_matching` that spell their team names as an explicit
character class; every other pattern reads a bare ``.+?``. So they were the only
two that could REFUSE a character, and the character they refused was ``&`` —
the one real team names use. "Alabama A&M vs Howard" therefore parsed to nothing
at all, and every A&M, A&T, "William & Mary", "Brighton & Hove Albion" and
"Hayes & Yeading United" market in the corpus was invisible to the matcher.

Admitting ``&`` is one character. The other three changes guarded here are what
makes admitting it SAFE, and each was found by measuring the first:

* **Strong-separator split.** Admitting ``&`` let more names through the bare
  pattern, which exposed that the pattern splits at the FIRST separator — and
  "at" is a preposition that lives inside real names. "University at Albany vs
  Buffalo" read as ("University", "Albany vs Buffalo"). Splitting at the strong
  separator (``vs``/``v``/``@``, which no team name contains) reads the game.
* **The three-way refusal.** Once a side may contain ``&``, "Bitcoin vs. Gold
  vs. S&P 500 in 2026" parses as a two-team game. A side that is ITSELF a
  matchup means the name was never a game.
* **The sub-market descriptor never names an event.** Admitting ``&`` lets
  "Cambridge City FC vs. Maldon & Tiptree FC - Exact Score" parse for the first
  time, and AUTO-CREATE stamps whatever team_b holds — live proof, events
  15293085 and 15291704, whose away teams are "Portishead Town FC - Exact
  Score" and "HFX Wanderers FC - Exact Score" while sibling 15293077 came out
  clean. This branch first answered that by STRIPPING the five big Polymarket
  labels in `_MORE_MARKETS_RE`. Master answered it the other way and landed
  first: #2871 REFUSES such a row as evidence of a game and deliberately leaves
  the suffix on the parsed name, because `_MATCHUP_NON_GAME_KEYWORDS` reads
  "winner" out of it to keep a period market out of a full-game blend. Both
  close the hole; only one of them keeps that rule working, and stripping
  regressed golden pair 59683704. So the strip was dropped and what is asserted
  below is that admitting ``&`` does not open a route around #2871.
* **The institutional-suffix mascot rule.** The candidate query is
  ``LIMIT 20 ORDER BY commence_time``, and `_expand_team_search_terms` was
  emitting "State" as the "mascot" of "Missouri State". ``%State%`` filled all
  twenty slots with unrelated state schools, so the market's own event
  (14793413, five days out) never made the list.

Measured on production 2026-08-30 over the complete affected population — every
unlinked open market whose name carries ``&`` or two separators, 348 rows:
**+6 markets link, 0 lost**, and the auto-create disposition goes from 4 event
identities to 12, all 8 new ones real fixtures with clean names.
"""

import pytest

from app.tasks.prediction_market_matching import _expand_team_search_terms
from app.utils.prediction_market_matching import (
    extract_matchup,
    is_derivative_market_name,
    is_game_level_market,
)


def _teams(name):
    """(team_a, team_b) or None — the parse under test, in one call."""
    m = extract_matchup(name)
    return None if m is None else (m.team_a, m.team_b)


# ---------------------------------------------------------------------------
# The ship: ampersand names parse, and reach game-level
# ---------------------------------------------------------------------------

# Every one of these is a real unlinked production row read 2026-08-30.
AMPERSAND_MATCHUPS = [
    ("Alabama A&M vs Howard", "Alabama A&M", "Howard"),
    ("Miles Golden Bears vs Alcorn St.", "Miles Golden Bears", "Alcorn St."),
    ("North Carolina A&T vs Georgia St.", "North Carolina A&T", "Georgia St."),
    ("William & Mary vs Villanova", "William & Mary", "Villanova"),
    ("Missouri St. vs Texas A&M", "Missouri St.", "Texas A&M"),
    ("East Texas A&M vs Mercer", "East Texas A&M", "Mercer"),
    ("Prairie View A&M vs Tarleton St.", "Prairie View A&M", "Tarleton St."),
    ("Delaware St. vs William & Mary", "Delaware St.", "William & Mary"),
    ("Bosnia & Herzegovina vs Lithuania", "Bosnia & Herzegovina", "Lithuania"),
    (
        "Brighton & Hove Albion FC vs. Leeds United FC",
        "Brighton & Hove Albion FC",
        "Leeds United FC",
    ),
    (
        "Hayes & Yeading United FC vs. Camberley Town FC",
        "Hayes & Yeading United FC",
        "Camberley Town FC",
    ),
    (
        "Chippenham Town FC vs. Havant & Waterlooville FC",
        "Chippenham Town FC",
        "Havant & Waterlooville FC",
    ),
    (
        "Wingate & Finchley FC vs. Felixstowe & Walton United FC",
        "Wingate & Finchley FC",
        "Felixstowe & Walton United FC",
    ),
    ("Elon Phoenix vs William & Mary Tribe", "Elon Phoenix", "William & Mary Tribe"),
]


@pytest.mark.parametrize("name,team_a,team_b", AMPERSAND_MATCHUPS)
def test_ampersand_name_parses_to_both_teams(name, team_a, team_b):
    assert _teams(name) == (team_a, team_b)


@pytest.mark.parametrize("name,team_a,team_b", AMPERSAND_MATCHUPS)
def test_ampersand_name_is_game_level(name, team_a, team_b):
    assert is_game_level_market(name, None, external_id=None) is True


def test_the_ampersand_is_read_as_part_of_a_name_never_as_a_separator():
    """`&` joins; it never splits. Both sides keep theirs."""
    assert _teams("Wingate & Finchley FC vs Maldon & Tiptree FC") == (
        "Wingate & Finchley FC",
        "Maldon & Tiptree FC",
    )


def test_dash_matchup_also_admits_the_ampersand():
    """The European dash form carried the same character class, and the same gap."""
    assert _teams("Brighton & Hove Albion - Leeds United") == (
        "Brighton & Hove Albion",
        "Leeds United",
    )


# ---------------------------------------------------------------------------
# Substrate 1 — split at the strong separator, because "at" lives inside names
# ---------------------------------------------------------------------------

def test_a_team_name_containing_at_is_not_split_on_it():
    """"University at Albany" is one team. Splitting at the first separator made
    it two, and buried the opponent in the second capture."""
    assert _teams("University at Albany vs Buffalo") == (
        "University at Albany",
        "Buffalo",
    )
    assert _teams("University at Albany vs LIU") == ("University at Albany", "LIU")
    assert _teams("University At Albany Great Danes vs Colgate Raiders") == (
        "University At Albany Great Danes",
        "Colgate Raiders",
    )


def test_the_same_team_on_the_other_side_still_parses():
    """It already worked here — team_b absorbing " at " was harmless. Pinned so
    the strong-separator preference cannot break the case it was not aimed at."""
    assert _teams("New Hampshire vs University at Albany") == (
        "New Hampshire",
        "University at Albany",
    )


def test_at_is_still_a_separator_when_it_is_the_only_one():
    """The strong separator is a PREFERENCE, not a requirement."""
    assert _teams("Kansas City at Las Vegas") == ("Kansas City", "Las Vegas")
    assert _teams("Toledo at Michigan St.") == ("Toledo", "Michigan St.")


# ---------------------------------------------------------------------------
# Substrate 2 — a side that is itself a matchup means it was never a game
# ---------------------------------------------------------------------------

THREE_WAY_NAMES = [
    "Bitcoin vs. Gold vs. S&P 500 in 2026",
    "Bitcoin vs Gold vs Silver",
    "Alice vs Bob vs Carol",
]


@pytest.mark.parametrize("name", THREE_WAY_NAMES)
def test_a_three_way_comparison_is_not_a_game(name):
    assert _teams(name) is None
    assert is_game_level_market(name, None, external_id=None) is False


def test_the_three_way_refusal_does_not_reach_a_two_team_game():
    """The refusal keys on a SECOND separator, not on the name being long."""
    assert _teams("Bitcoin vs. Gold") == ("Bitcoin", "Gold")


def test_doubles_tennis_slashes_are_not_separators():
    """`/` partners a pair; it must not be read as a second matchup."""
    assert _teams("Schnaitter/Wallner vs Glinka/Sakellaridis") == (
        "Schnaitter/Wallner",
        "Glinka/Sakellaridis",
    )


# ---------------------------------------------------------------------------
# Substrate 3 — the Polymarket sub-market descriptor never names an event
# ---------------------------------------------------------------------------

# The game's own container. These ARE stripped: the container market is the
# fixture itself, so it may create it (#1021, gotcha #18).
CONTAINER_LABELS = ["More Markets", "Player Props"]

# A prop or period of the game. Under #2871 these are refused as evidence that
# the game exists, and the suffix stays ON the parsed name on purpose.
DERIVATIVE_LABELS = [
    "Exact Score",
    "First Team to Score",
    "Second Half Result",
    "Halftime Result",
    "Total Corners",
]


@pytest.mark.parametrize("label", CONTAINER_LABELS)
def test_container_label_is_stripped_off_the_second_team(label):
    name = f"Cambridge City FC vs. Maldon & Tiptree FC - {label}"
    assert _teams(name) == ("Cambridge City FC", "Maldon & Tiptree FC")


@pytest.mark.parametrize("label", DERIVATIVE_LABELS)
def test_a_derivative_of_an_ampersand_game_is_refused_as_evidence_of_it(label):
    """
    The interaction this ship has to survive. Before ``&`` was admitted these
    names did not parse at all, so #2871 was never asked about them; now they
    do, and it must still answer no. Asserted as the refusal itself, not as the
    parse, because the parse is exactly what #2871 wants left dirty.
    """
    name = f"Cambridge City FC vs. Maldon & Tiptree FC - {label}"
    assert _teams(name) is not None, "the ampersand ship must make this parse"
    assert is_derivative_market_name(name), (
        f"'- {label}' must still read as a derivative once & is admitted — "
        "otherwise auto-create mints a game named after a prop"
    )


def test_every_derivative_of_one_fixture_is_refused_so_one_game_stays_one_event():
    """Five rows, one game: none of the five may mint an event, and the
    container may. That is what keeps one fixture from becoming six rows in
    /search — the failure the strip was reaching for, reached the other way."""
    fixture = "Chippenham Town FC vs. Havant & Waterlooville FC"
    assert all(
        is_derivative_market_name(f"{fixture} - {label}")
        for label in DERIVATIVE_LABELS
    )
    assert not is_derivative_market_name(fixture)
    for label in CONTAINER_LABELS:
        assert not is_derivative_market_name(f"{fixture} - {label}")
        assert _teams(f"{fixture} - {label}") == (
            "Chippenham Town FC", "Havant & Waterlooville FC"
        )


TOURNAMENT_CONTEXT_SUFFIXES = [
    "BLAST Open Porto Group A",
    "FISSURE PLAYGROUND Group B",
    "EPL Masters Group A",
    "KPL Growth League Group Stage",
]


@pytest.mark.parametrize("suffix", TOURNAMENT_CONTEXT_SUFFIXES)
def test_tournament_context_is_not_stripped_as_if_it_were_a_label(suffix):
    """The strip list is CLOSED on purpose. These suffixes are the only thing
    telling two real markets apart; erasing them would merge distinct games."""
    name = f"Team Liquid vs. G2 Esports - {suffix}"
    team_a, team_b = _teams(name)
    assert team_a == "Team Liquid"
    assert team_b.endswith(suffix), (
        f"tournament context {suffix!r} was stripped off team_b ({team_b!r}); "
        "only the named sub-market labels may be removed"
    )


# "- LPL Playoffs", "- Map 1 Winner" and "- Game 2 Winner" are refused too, but
# for a DIFFERENT and pre-existing reason — "playoffs", "winner" and "season"
# are futures keywords, so `_has_futures_matchup_keyword` rejects the whole name
# before any of this. Verified identical on `origin/master`. Pinned so a future
# edit to the strip list cannot quietly become the thing holding them out.
FUTURES_KEYWORD_SUFFIXES = [
    "LPL Playoffs",
    "Map 1 Winner",
    "Game 2 Winner",
    "ESEA Advanced Europe Regular Season",
    "Hitpoint Masters Regular Season",
]


@pytest.mark.parametrize("suffix", FUTURES_KEYWORD_SUFFIXES)
def test_futures_keyword_suffixes_stay_refused_by_the_futures_guard(suffix):
    assert _teams(f"Team Liquid vs. G2 Esports - {suffix}") is None


# ---------------------------------------------------------------------------
# Substrate 4 — "%State%" is a census, not a search
# ---------------------------------------------------------------------------

INSTITUTIONAL_LAST_WORDS = [
    ("Missouri State", "State"),
    ("Georgia State", "State"),
    ("Leeds United", "United"),
    ("Cambridge City", "City"),
    ("Chippenham Town", "Town"),
    ("Boston College", "College"),
]


@pytest.mark.parametrize("team,suffix", INSTITUTIONAL_LAST_WORDS)
def test_institutional_suffix_is_not_emitted_as_a_search_term(team, suffix):
    """It would ILIKE '%State%' against every state school in the country and
    blow the candidate query's 20-row limit before the real event is reached."""
    assert suffix not in _expand_team_search_terms(team)


@pytest.mark.parametrize("team,suffix", INSTITUTIONAL_LAST_WORDS)
def test_the_full_name_is_still_searched(team, suffix):
    """Narrowing the expansion must not remove the term that actually works."""
    assert team in _expand_team_search_terms(team)


# Mascots of five characters or more — the pre-existing floor in the rule this
# narrows. ("Owls", "Jets", "Suns" were never expanded and still are not.)
REAL_MASCOTS = [
    ("WSH Capitals", "Capitals"),
    ("Georgia Southern Eagles", "Eagles"),
    ("Alabama A&M Bulldogs", "Bulldogs"),
    ("Prairie View A&M Panthers", "Panthers"),
    ("William & Mary Tribe", "Tribe"),
]


@pytest.mark.parametrize("team,mascot", REAL_MASCOTS)
def test_a_real_mascot_is_still_expanded(team, mascot):
    """Both directions: the suffix list must not swallow the rule it narrows."""
    assert mascot in _expand_team_search_terms(team)


# ---------------------------------------------------------------------------
# Substrate 5 — a category-fallback sport key cannot prove a game is uncovered
# ---------------------------------------------------------------------------

def test_american_football_is_the_only_comprehensively_covered_family():
    """American football's category fallback is refused; soccer's is not.

    Soccer must stay out: MLS is one league out of hundreds, and refusing every
    soccer auto-create on its account would strand the non-league fixtures
    Polymarket lists and nobody else does.

    RE-POINTED by the integrator/224 D52 rescue (2026-09-06). This branch was cut
    2026-08-30 and asserted the refusal by scanning
    `_create_event_from_prediction_market` for its own
    `_COMPREHENSIVELY_COVERED_FAMILIES` frozenset. Master reached the same refusal
    first, under Q453: `auto_create_sport_key_from_category` returns None for the
    `football` category, so the sport key is never built and the caller's "no sport
    key determinable" branch refuses the auto-create. The branch's own guard was
    dropped as superseded by content, so the source scan could only assert the
    absence of code that no longer needs to exist. The intent is unchanged and now
    pinned as BEHAVIOUR on the surviving mechanism, which a later refactor of that
    helper cannot silently defeat the way a substring scan can.
    """
    from app.utils.prediction_market_matching import (
        auto_create_sport_key_from_category,
    )

    # American football: refused, so no event is auto-created beside the real
    # americanfootball_ncaaf_fcs row ("Missouri State vs. Texas A&M").
    assert auto_create_sport_key_from_category("football") is None

    # Soccer: still allowed to create, and it must stay that way.
    assert auto_create_sport_key_from_category("soccer") == "soccer_other"
