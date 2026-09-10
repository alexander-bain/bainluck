"""TYPING PART OF A TEAM'S NAME LEADS WITH THE TEAM. #4519, ship #4461.

Sibling of `test_typeahead_leads_with_the_entity_4411.py`. That file owns the
case where the query is a COMPLETE word ("shelton", "alcaraz"); this one owns
the keystroke before it — the user is still typing, and MC0 has not arrived yet.

MEASURED ON PRODUCTION, 2026-09-09 23:5xZ, `GET /api/events/typeahead`, plain
(no debug flag — this is what a reader's dropdown was served):

    q=yank      5 inning props, 2 fixture rows, and NO team row in the 7 slots
    q=yankees   MLB World Series Champion, then **New York Yankees**, then …
    q=lak       "Niagara-on-the-Lake, ON Mayoral Election Winner" at rank 0,
                and the Los Angeles Lakers at rank 4

#4461's title is literally "typing 'yank' finds the Yankees".

THE ISSUE FILED IT AS A RECALL BUG. IT IS NOT ONE, AND THAT MATTERS ENOUGH TO
PIN HERE. `%yank%` matches exactly two rows in `teams` and the MLB Yankees is
the first of them, so the candidate WAS built, WAS fetched inside
`_TEAM_POOL_FETCH_LIMIT`, and WAS handed to the scorer. It then placed 8th of 7.
A recall fix would have been inert; measure which half is broken before writing
either one.

THE CAUSE, in one sentence: `yank` is a live prefix of the alias "Yankees" AND a
live prefix of the token "Yankees" buried inside "Colorado Rockies vs. New York
Yankees - 5th Inning Winner", MC2 could not tell those apart, so kind alone
decided and ruling 041's team FLOOR put the entity last. One keystroke later
`yankees` is MC0 on the alias and leads — the whole defect is that MC0 vanishes
a character early with nothing underneath it. `MC1B_OWN_NAME_PREFIX` is that
missing rung.

WHAT THIS FILE MUST NOT BE READ AS: a reversal of the ratified market > event >
team relation (ruling 041 / Q325), or a weakening of MC1. MC1 is checked FIRST,
so MC1B can only fire on a query that is not a complete token of any candidate's
name — the survival controls below fail if either ever changes.
"""

from __future__ import annotations

import pytest

# `smc` for the one test that must MUTATE a knob; the names below for reading.
# One import statement per module — mixing `import x` with `from x import y` is
# a CodeQL notice, and the sibling property suite already uses this exact shape.
from app.utils import search_match_class as smc
from app.utils.search_match_class import (
    MC0_EXACT,
    MC1_ALL_TOKENS,
    MC1B_OWN_NAME_PREFIX,
    MC2_LAST_TOKEN_PREFIX,
    MC3_PARTIAL_TOKENS,
    MC5_FRAGMENT,
    OWN_NAME_PREFIX_MIN_LEN,
    Evidence,
    match_class,
    rank,
)


# --- the shared harness ----------------------------------------------------
#
# Ranks through the REAL `rank`, so a test here cannot pass by re-implementing
# the rule it checks.


def _ranked(q, candidates):
    return rank(q, [(ev, f"{ev.kind}|{ev.name}") for ev in candidates])


#: The measured `yank` candidate set, evidence-for-evidence. Aliases are the
#: real ones (`teams.alternate_names` for id 6610: `['New York', 'Yankees']`)
#: because the alias is what the team wins on — a specimen without them would
#: pass this file while production failed, which is LAT-P050's exact defect.
_YANKEES = Evidence(
    name="New York Yankees",
    aliases=("New York", "Yankees", "NYY"),
    kind="team",
    sport_key="baseball_mlb",
)
_INNING_PROPS = [
    Evidence(
        name=f"Colorado Rockies vs. New York Yankees - {n} Winner",
        kind="futures",
        sport_key="baseball",
    )
    for n in ("First 5 Innings", "9th Inning", "1st Inning", "3rd Inning",
              "5th Inning", "2nd Inning", "6th Inning")
]
_FIXTURES = [
    Evidence(name="Colorado Rockies at New York Yankees", kind="event",
             sport_key="baseball_mlb")
    for _ in range(2)
]


def test_yank_leads_with_the_yankees():
    """The reported screen, in one assertion."""
    out = _ranked("yank", [*_INNING_PROPS, *_FIXTURES, _YANKEES])
    assert out[0] == "team|New York Yankees", out[:3]


def test_every_keystroke_from_yan_to_yankees_leads_with_the_team():
    """Not just the one character that was reported.

    The bug was a HOLE between two working states — `yankees` worked on MC0 and
    the shorter prefixes fell through to MC2 — so a test pinning only `yank`
    would pass with the hole merely moved one character left.
    """
    for q in ("yan", "yank", "yanke", "yankees"):
        out = _ranked(q, [*_INNING_PROPS, *_FIXTURES, _YANKEES])
        assert out[0] == "team|New York Yankees", f"{q!r} -> {out[:3]}"


def test_the_singular_yankee_is_NOT_fixed_by_this_ship_and_that_is_pinned():
    """#4551, and it is asserted rather than omitted ON PURPOSE.

    Writing the sweep above as `yan…yankees` inclusive was the first draft and
    it failed on exactly one keystroke, which is how #4551 was found. Deleting
    that member would have hidden a live production defect inside a green
    guard; pinning the CURRENT behaviour means the day #4551 is fixed, this
    test goes red and names the issue that authorises the change.

    `yankee` never reaches MC1B because it never reaches MC2: `_fold_token`
    strips the plural, so `yankee` is a whole token of "New York Yankees" and
    the team is an honest MC1 — as is every market carrying the same token.
    The class ties and ruling 041's team floor decides. That is the ratified
    relation working as written, not this ship failing.
    """
    assert match_class("yankee", _YANKEES) == MC1_ALL_TOKENS
    assert match_class("yankee", _INNING_PROPS[0]) == MC1_ALL_TOKENS
    out = _ranked("yankee", [*_INNING_PROPS, *_FIXTURES, _YANKEES])
    assert out[0].startswith("futures|"), out[:2]


def test_lak_leads_with_the_lakers_not_a_mayoral_election():
    """The second production specimen, and the one visible above the fold.

    `lak` served "Niagara-on-the-Lake, ON Mayoral Election Winner" at rank 0
    with the Lakers at rank 4 — same class (both merely land mid-name), so kind
    decided and the market took it. The Lakers own the alias "Lakers", which
    `lak` is a live prefix of; the Niagara market owns no name beginning "lak".
    """
    lakers = Evidence(name="Los Angeles Lakers", aliases=("Lakers", "LAL"),
                      kind="team", sport_key="basketball_nba")
    niagara = Evidence(name="Niagara-on-the-Lake, ON Mayoral Election Winner",
                       kind="futures")
    salt_lake = Evidence(name="Real Salt Lake at Houston Dynamo", kind="event")
    out = _ranked("lak", [niagara, salt_lake, lakers])
    assert out[0] == "team|Los Angeles Lakers", out


# --- what the new class is, exactly ----------------------------------------


def test_mc1b_is_the_whole_name_not_a_token_inside_it():
    """The one distinction the class draws. Both of these are MC2 without it."""
    assert match_class("yank", Evidence(name="Yankees")) == MC1B_OWN_NAME_PREFIX
    assert match_class(
        "yank",
        Evidence(name="Colorado Rockies vs. New York Yankees - 5th Inning Winner"),
    ) == MC2_LAST_TOKEN_PREFIX


def test_mc1b_reads_aliases_because_the_alias_is_what_a_team_wins_on():
    """"New York Yankees" does NOT start with `yank`; the alias does.

    So a team whose `alternate_names` are withheld from the scorer cannot reach
    this class at all — the same withheld-evidence failure
    `test_typeahead_evidence_boundary.py` owns, arriving one rung lower.
    """
    assert match_class("yank", Evidence(name="New York Yankees")) == MC2_LAST_TOKEN_PREFIX
    assert match_class(
        "yank", Evidence(name="New York Yankees", aliases=("Yankees",))
    ) == MC1B_OWN_NAME_PREFIX


def test_mc1b_sits_strictly_between_mc1_and_mc2():
    assert MC1_ALL_TOKENS < MC1B_OWN_NAME_PREFIX < MC2_LAST_TOKEN_PREFIX


# --- the survival controls: what must NOT move ------------------------------


def test_a_complete_word_still_beats_an_unfinished_one():
    """MC1 is checked first, and that is the whole safety argument.

    `new` is a complete token of the market's name, so the market is MC1 and
    outranks the team's MC1B — the ratified market > event > team relation
    decides every query whose words are finished, exactly as it does today.
    """
    market = Evidence(name="New York Yankees vs. Boston Red Sox - Winner",
                      kind="futures")
    team = Evidence(name="New York Yankees", aliases=("New York", "Yankees"),
                    kind="team", sport_key="baseball_mlb")
    assert match_class("new", market) == MC1_ALL_TOKENS
    assert match_class("new", team) == MC1_ALL_TOKENS
    assert _ranked("new", [team, market])[0] == "futures|New York Yankees vs. Boston Red Sox - Winner"


def test_two_characters_cannot_carry_the_class():
    """`ai` -> "1. FC Kaiserslautern" is measured failure family #2 in this
    module's own docstring. Without the floor it would come back through a new
    door: `ai` is a live prefix of the whole name "Aizawl FC", which would put a
    team above every market on two keystrokes.
    """
    assert OWN_NAME_PREFIX_MIN_LEN == 3
    assert match_class("ai", Evidence(name="Aizawl FC")) != MC1B_OWN_NAME_PREFIX
    # And three characters, where the class is admitted, is still harmless for
    # the other member of that family — nothing is named "Ipo…".
    assert match_class("ipo", Evidence(name="Asteras Tripolis")) != MC1B_OWN_NAME_PREFIX


@pytest.mark.parametrize(
    "query, name, expected",
    [
        # The protected families, all unchanged (verified against production
        # 2026-09-09: 34 of 38 probes byte-identical, artifacts-lane1-219).
        # MC5, not MC3 — `brito` shares no whole token with the query. P2 in the
        # property suite pins the same specimen at the same class; the first
        # draft of this line guessed MC3 and the suite disagreed.
        ("british open", "Brito", MC5_FRAGMENT),
        ("nba mvp", "NBA MVP", MC0_EXACT),
        ("super bowl", "Super Bowl LXI Winner", MC1_ALL_TOKENS),
        ("super owl", "Night of Super Bowling", MC3_PARTIAL_TOKENS),
        # A prefix that lands in the MIDDLE stays MC2, whatever its length.
        ("bowl", "Night of Super Bowling", MC2_LAST_TOKEN_PREFIX),
    ],
)
def test_the_ratified_families_do_not_move(query, name, expected):
    assert match_class(query, Evidence(name=name)) == expected


def test_the_class_can_only_promote_never_demote():
    """The invariant that makes this safe to put in front of the whole scorer.

    `match_class` returns the FIRST class that holds and MC1B is inserted above
    MC2, so a candidate can only move up. Asserted over the specimen table
    rather than argued: with the class disabled every specimen scores at least
    as badly as with it enabled, and never better.
    """
    specimens = [
        Evidence(name="Yankees"),
        Evidence(name="New York Yankees", aliases=("Yankees",)),
        Evidence(name="Colorado Rockies vs. New York Yankees - 5th Inning Winner"),
        Evidence(name="Night of Super Bowling"),
        Evidence(name="Super Bowl LXI Winner"),
        Evidence(name="Aizawl FC"),
        Evidence(name="Big Game Winner", outcomes=("Super Bowl",)),
    ]
    keep = smc.OWN_NAME_PREFIX_MIN_LEN
    for q in ("yank", "super bowl", "ai", "new", "yankees"):
        with_class = [match_class(q, ev) for ev in specimens]
        smc.OWN_NAME_PREFIX_MIN_LEN = 10**6  # the class can never fire
        try:
            without = [match_class(q, ev) for ev in specimens]
        finally:
            smc.OWN_NAME_PREFIX_MIN_LEN = keep
        for a, b, ev in zip(with_class, without, specimens):
            assert a <= b, f"{q!r} DEMOTED {ev.name!r}: {b} -> {a}"
