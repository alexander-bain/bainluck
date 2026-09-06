"""#3089, second surface: a hub/league match card names the side a price is for.

PR #3577 fixed the EVENT PAGE only. Alex's own comment on #3089 anticipated
exactly that gap — "a fix that only knows about `game-markets` would leave this
one standing" — and the hub is the one left standing. Reproduced on
``/api/hub/tennis`` 2026-09-06: 11 of 19 match cards labelled their outcomes with
nothing but Yes/No, and because the payload sorts most-probable-first the order
flips between cards, so a reader who learns the convention is wrong half the time.

The population these guards are drawn from is production, not imagination — every
market name below appeared in ``futures_markets`` on 2026-09-06.
"""

import pytest

from app.routes.league_futures import _serialize_outcomes
from app.utils.matchup_sides import bare_matchup_sides, sided_yes_no_labels


class _Outcome:
    def __init__(self, oid, name, prob):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.opening_probability = None
        self.rank = None
        self.probability_change_24h = None
        self.team_id = None


class _Market:
    def __init__(self, name, sport="tennis"):
        self.name = name
        self.llm_sport_category = sport


def _yes_no():
    return [_Outcome(1, "Yes", 0.795), _Outcome(2, "No", 0.205)]


# ── the ship ────────────────────────────────────────────────────────────────

def test_the_hub_match_card_names_both_sides():
    """The card Alex flagged, verbatim from /api/hub/tennis."""
    rows = _serialize_outcomes(
        _yes_no(), _Market("US Open WTA: Iga Swiatek vs Qinwen Zheng")
    )
    assert [r["name"] for r in rows] == ["Iga Swiatek", "Qinwen Zheng"]
    # The prices are untouched — only the labels moved.
    assert [r["probability"] for r in rows] == [0.795, 0.205]


def test_a_doubles_pairing_is_named_too():
    """"(Doubles)" is a draw type, not a prop — the slash names must survive."""
    rows = _serialize_outcomes(
        _yes_no(), _Market("US Open ATP (Doubles): Lammons/Withrow vs Cabral/Tracy")
    )
    assert [r["name"] for r in rows] == ["Lammons/Withrow", "Cabral/Tracy"]


def test_renaming_is_display_only_and_keeps_the_outcome_id():
    """Anything that resolves, settles or charts this row addresses it by id."""
    rows = _serialize_outcomes(
        _yes_no(), _Market("US Open WTA: Iga Swiatek vs Qinwen Zheng")
    )
    assert [r["id"] for r in rows] == [1, 2]


# ── the refusals: naming these would be WRONG, not merely unhelpful ─────────

@pytest.mark.parametrize(
    "name, why",
    [
        (
            "Set Handicap: Vallejo (-1.5) vs Monfils (+1.5)",
            "Yes means 'Vallejo covers -1.5', not 'Vallejo wins'",
        ),
        (
            "Game Spread: Zverev (-6.5) vs Darderi (+6.5)",
            "Yes means 'Zverev covers -6.5'",
        ),
        (
            "Set 1 Winner: Vallejo vs Monfils",
            "Yes means 'Vallejo wins SET 1', not the match",
        ),
        (
            "Counter-Strike: fnatic vs NIP - Map 1 Winner",
            "the regression 43cc8658 repaired on the event page, one commit ago",
        ),
        (
            "US Open WTA: Completed Match: Kichenok/Kichenok vs Kato/Wu",
            "Yes means 'the match was completed'",
        ),
        (
            "ECS Portugal: Odivelas Titans vs Amadora Royals - Who wins the toss?",
            "Yes means 'Odivelas wins the TOSS'",
        ),
        (
            "US Open WTA: Iga Swiatek vs Qinwen Zheng Total Sets: O/U 2.5",
            "Yes means 'over 2.5 sets'",
        ),
    ],
)
def test_a_prop_about_a_matchup_is_never_given_a_bare_side_name(name, why):
    assert bare_matchup_sides(name) is None, why
    rows = _serialize_outcomes(_yes_no(), _Market(name))
    assert [r["name"] for r in rows] == ["Yes", "No"], why


@pytest.mark.parametrize(
    "name, sole_check",
    [
        ("US Open ATP: Alcaraz vs Sinner - Exhibition", 'the " - " suffix'),
        ("US Open ATP: Alcaraz vs Sinner (BO3)", "a parenthesised side"),
    ],
)
def test_each_structural_refusal_is_load_bearing_on_its_own(name, sole_check):
    """Pins the two checks nothing else covers.

    Every REAL prop name measured on production trips the qualifier vocabulary
    as well as its structural marker, so deleting the structural check would not
    have reddened a single test above. These two names are constructed so that
    `sole_check` is the ONLY reason they are refused — without them, the " - "
    and paren rules could rot away silently and a name like the first would leak
    "Alcaraz" onto a card that is not a plain match.
    """
    from app.utils.matchup_sides import _PROP_QUALIFIER

    assert not _PROP_QUALIFIER.search(name), "no qualifier word — the structural check is alone"
    assert bare_matchup_sides(name) is None, sole_check


def test_the_prop_guard_would_actually_fire_on_a_naive_rule():
    """Proves the refusals above are not vacuous.

    Every refused name really does contain a matchup, so a rule that merely
    looked for " vs " WOULD have named them. Without this, the parametrized test
    could pass for the trivial reason that the strings have no matchup at all.
    """
    naive = "Set Handicap: Vallejo (-1.5) vs Monfils (+1.5)"
    assert " vs " in naive
    assert bare_matchup_sides(naive) is None


# ── the sport gate ──────────────────────────────────────────────────────────

def test_an_unverified_sport_keeps_its_yes_no():
    """Cricket parses as a bare matchup but its side order is UNVERIFIED.

    Its only independent named-side source is a parent whose outcomes are
    truncated child titles, and the Yes/No pair on this very market summed to
    1.235 on production. Unverifiable and junk — so it keeps Yes/No.
    """
    name = "German Super League NRW T10: Dusseldorf Blackcaps vs Cricket Club Koln"
    # It DOES parse — the gate, not the parser, is what refuses it. (Without this
    # line the test would pass even if the parser had simply rejected the name.)
    assert bare_matchup_sides(name) == ("Dusseldorf Blackcaps", "Cricket Club Koln")
    assert sided_yes_no_labels(name, "cricket", ["Yes", "No"]) is None
    rows = _serialize_outcomes(_yes_no(), _Market(name, sport="cricket"))
    assert [r["name"] for r in rows] == ["Yes", "No"]


# ── everything else is untouched ────────────────────────────────────────────

def test_outcomes_that_already_name_themselves_are_left_alone():
    outs = [_Outcome(1, "Carlos Alcaraz", 0.6), _Outcome(2, "Jannik Sinner", 0.4)]
    rows = _serialize_outcomes(outs, _Market("US Open ATP: Alcaraz vs Sinner"))
    assert [r["name"] for r in rows] == ["Carlos Alcaraz", "Jannik Sinner"]


def test_an_over_under_pair_is_not_a_side_pair():
    outs = [_Outcome(1, "Over", 0.5), _Outcome(2, "Under", 0.5)]
    rows = _serialize_outcomes(outs, _Market("US Open ATP: Alcaraz vs Sinner"))
    assert [r["name"] for r in rows] == ["Over", "Under"]


def test_a_three_way_market_is_not_a_side_pair():
    """A matchup with a draw has no two-sided Yes/No to rename."""
    outs = [_Outcome(1, "Yes", 0.5), _Outcome(2, "No", 0.3), _Outcome(3, "Draw", 0.2)]
    rows = _serialize_outcomes(outs, _Market("Some League: A vs B"))
    assert [r["name"] for r in rows] == ["Yes", "No", "Draw"]


def test_a_non_matchup_market_keeps_its_yes():
    """"Will X qualify?" is a real yes/no question — Yes is the RIGHT label."""
    rows = _serialize_outcomes(
        _yes_no(), _Market("Will Carlos Alcaraz Qualify for the Nitto ATP Finals 2026?")
    )
    assert [r["name"] for r in rows] == ["Yes", "No"]


def test_no_market_argument_degrades_to_the_raw_venue_labels():
    rows = _serialize_outcomes(_yes_no())
    assert [r["name"] for r in rows] == ["Yes", "No"]
