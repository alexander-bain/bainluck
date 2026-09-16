"""#6604 — a soccer hero stops printing the DRAW's price as the home team's chance.

THE PAGE THIS EXISTS FOR. `/events/15312327`, Spain v Portugal U20, in play,
2026-09-16 ~12:05 PT at 390px:

    Spain  < 1 %          Live · Bain Luck blend

Polymarket, read at the venue in the same minute (notice 26 method, `GET
gamma-api.polymarket.com/events?id=1019809`), priced **Spain at 0.9995**:

    Will Spain win on 2026-09-16?                  0.9995
    Will Spain vs. Portugal U20 end in a draw?     0.0005   <- we stored this
    Will Portugal U20 win on 2026-09-16?           0.0005

The hero was inverted by 99.9 points against the only source it had. On 44
fixtures the draw leg was the hero's ONLY input, so nothing diluted it.

──────────────────────────────────────────────────────────────────────────────
THE CAUSE: "IS THE MATCHUP" AND "CONTAINS ONE" ARE DIFFERENT QUESTIONS
──────────────────────────────────────────────────────────────────────────────
`find_moneyline_outcome`'s last-resort fallback was written for Polymarket's
UFC shape, where the outcome name IS the matchup — `"Tai Tuivasa vs. Robelis
Despaigne"`. It tested for that with containment:

    if a_lower in name_lower and b_lower in name_lower and ":" not in name:

Polymarket names a soccer draw leg **`Draw (Spain vs. Portugal U20)`**. That
contains both team names and carries no `":"`, so it satisfied the test exactly,
and the fallback returned it as the home team's YES leg.

🔴 EVERY GUARD ON THE PATH BEHAVED AS DESIGNED, which is why nothing caught it:

1. `_is_prop_or_spread_outcome` does not claim it — a draw is not a prop.
2. #4629's `matches_home and matches_away ⇒ continue` **correctly** refuses to
   give a both-teams name to either side, leaving both lists empty.
3. That empty state is exactly the condition that hands control to the fallback.

So the defect is the fallback predicate's alone, and it is fixed there.

──────────────────────────────────────────────────────────────────────────────
THE FIX IS A RESIDUE, NOT A VOCABULARY — AND THAT IS THE LOAD-BEARING CHOICE
──────────────────────────────────────────────────────────────────────────────
`outcome_name_is_the_whole_matchup` accounts for both team names, reduces what
is left to words, and discards the joins (`vs`/`v`/`versus`/`at`). Anything
remaining means the name asks a different question from "who won".

**It never looks at the word "Draw".** `Empate (...)`, `Unentschieden (...)`,
an exact score `2 - 2`, a `(Regulation)` qualifier — all refused by the same
rule, for the same reason, in any language. A draw word list would be the
instrument this file has already ruled against in `find_three_way_partition`'s
own words — *"Coherence is evidence; a spelling is a guess that reads as
evidence"* — and three disagreeing draw vocabularies already exist here.

**It is a STRICT NARROWING.** It begins by requiring exactly the containment the
old predicate required and then adds a condition, so it can only ever decline —
never re-point a resolved outcome at a different one. Declining is the
function's documented contract ("Returns None — never a guess").

──────────────────────────────────────────────────────────────────────────────
MEASURED ON PRODUCTION BEFORE AND AFTER, BY RUNNING THE REAL FUNCTION
──────────────────────────────────────────────────────────────────────────────
500 Polymarket markets on events in the last 4 days, every one of them holding
at least one outcome that satisfies the OLD predicate, replayed through
`extract_matchup_with_ticker_fallback` → `find_moneyline_outcome`:

    returned a reading BEFORE                200
    returned a reading AFTER                 172
    changed                                   28
      withdrawn (had a reading, now none)     28
      re-pointed to a different outcome        0
      newly gained a reading                   0

**All 28 withdrawals are `Draw (...)` legs.** Zero re-pointings, so no event's
number moves to a different market; zero legitimate matchup readings lost. That
every withdrawal spells "Draw" is the FINDING, not the rule — the predicate
never reads that word.

🪤 A first pass at sizing this counted every outcome whose name contains both
team names (8,372 rows) and called them all "newly refused". That measures the
wrong population: the fallback only runs when NO outcome matched a team, so the
overwhelming majority of those rows are draw legs sitting beside working `A` and
`B` legs where the fallback is never reached. Only replaying the real function
answers the question.

WHAT EACH TEST HERE DEFENDS:

* the ship — the live specimen's hero gets Spain's price, not the draw's
  (`test_the_spain_hero_stops_printing_the_draws_price`);
* that the specimen was ever defective — the OLD predicate is reconstructed and
  shown to accept the draw leg, so the fix is not green against a healthy
  fixture (`test_the_old_containment_predicate_really_did_accept_the_draw_leg`);
* the thing the fallback exists for must still work
  (`test_the_ufc_matchup_shape_still_resolves`);
* that the rule is structural, not lexical — other languages, scorelines and
  qualifiers are refused by the same rule
  (`test_a_draw_in_any_language_is_refused_without_a_word_for_draw`);
* the narrowing direction — it can only decline, never re-point
  (`test_the_predicate_is_a_strict_narrowing_of_the_one_it_replaces`);
* the upstream guards are unchanged and still do their jobs
  (`test_a_real_team_leg_still_wins_before_the_fallback_is_reached`).

Refs #6604, #4629, #2693.
"""

import re

import pytest

from app.utils.prediction_market_matching import (
    MatchupInfo,
    find_moneyline_outcome,
    outcome_name_is_the_whole_matchup,
)


class _Outcome:
    """The three attributes `find_moneyline_outcome` reads, and no more."""

    def __init__(self, name, probability, rank=0):
        self.name = name
        self.current_probability = probability
        self.rank = rank
        self.external_id = None

    def __repr__(self):  # pragma: no cover - failure output only
        return f"<{self.name!r} @ {self.current_probability}>"


SPAIN = "Spain"
PORTUGAL = "Portugal U20"


def _spain_portugal_outcomes():
    """The venue's three legs, at the prices it published for the live match."""
    return [
        _Outcome("Draw (Spain vs. Portugal U20)", 0.0005, rank=0),
        _Outcome("Spain", 0.9995, rank=1),
        _Outcome("Portugal U20", 0.0005, rank=2),
    ]


def _matchup(team_a=SPAIN, team_b=PORTUGAL):
    """`yes_team` is team_a and the format is the bare matchup, which is the
    shape `extract_matchup_with_ticker_fallback` returns for Polymarket's
    `"Spain vs. Portugal U20"` market names — the rows this ship is about.
    """
    return MatchupInfo(
        team_a=team_a, team_b=team_b, yes_team=team_a, format_type="bare_matchup"
    )


def _old_containment_predicate(name, team_a, team_b):
    """The predicate this ship replaces, reconstructed verbatim from the diff.

    Here so the BEFORE is asserted rather than asserted-about. A fix test that
    only checks the new behaviour is green on a fixture that never carried the
    defect; this one proves the fixture does.
    """
    a_lower, b_lower = team_a.lower(), team_b.lower()
    name_lower = name.lower()
    return a_lower in name_lower and b_lower in name_lower and ":" not in name


# =============================================================================
# The specimen was defective
# =============================================================================


def test_the_old_containment_predicate_really_did_accept_the_draw_leg():
    """The BEFORE. Without this the ship test below could pass on any fixture."""
    assert _old_containment_predicate(
        "Draw (Spain vs. Portugal U20)", SPAIN, PORTUGAL
    ), "the reconstructed old predicate no longer reproduces #6604's cause"


def test_the_draw_leg_reaches_the_fallback_because_the_guards_above_work():
    """#4629's rule is what empties both lists and hands control to the fallback.

    Asserted so a later reader does not "fix" the draw upstream: the draw leg
    matching both teams is CORRECT, and giving it to either side would be the
    older bug this file's #4629 note describes.
    """
    from app.utils.prediction_market_matching import _fuzzy_team_match

    draw = "Draw (Spain vs. Portugal U20)"
    assert _fuzzy_team_match(draw, SPAIN)
    assert _fuzzy_team_match(draw, PORTUGAL)


# =============================================================================
# The ship
# =============================================================================


def test_the_spain_hero_stops_printing_the_draws_price():
    """`/events/15312327`. The reader's number becomes Spain's, not the draw's."""
    result = find_moneyline_outcome(
        _spain_portugal_outcomes(), _matchup(), SPAIN, PORTUGAL
    )

    assert result is not None, "the page lost its only Polymarket reading"
    outcome, yes_is_home = result
    assert outcome.name == SPAIN
    assert outcome.current_probability == pytest.approx(0.9995)
    assert yes_is_home is True


def test_the_hero_is_not_merely_different_but_the_venues_own_number():
    """0.9995, not 0.0005 and not 0.5 — the two wrong answers this class produces.

    0.5 is called out by name because it is the arithmetic signature of the
    inverted-pair bug the #4629 note in this module records, and a fix that
    produced it would look plausible on a card.
    """
    outcome, _ = find_moneyline_outcome(
        _spain_portugal_outcomes(), _matchup(), SPAIN, PORTUGAL
    )

    assert outcome.current_probability != pytest.approx(0.0005)
    assert outcome.current_probability != pytest.approx(0.5)


def test_the_huddersfield_scheduled_specimen_too():
    """`/events/15311769` printed 25%, which was the draw."""
    home, away = "Huddersfield Town AFC", "Luton Town FC"
    outcomes = [
        _Outcome(f"Draw ({home} vs. {away})", 0.25, rank=0),
        _Outcome(home, 0.475, rank=1),
        _Outcome(away, 0.275, rank=2),
    ]

    outcome, _ = find_moneyline_outcome(outcomes, _matchup(home, away), home, away)

    assert outcome.current_probability == pytest.approx(0.475)


def test_a_fixture_whose_only_leg_is_the_draw_gets_no_reading_at_all():
    """The 44-fixture cohort: Polymarket is the hero's only source.

    Returning nothing is the right answer and the function's documented contract.
    A number derived from the draw would be a confident lie with no second
    source to dilute it, which is exactly what the reader saw.
    """
    outcomes = [_Outcome("Draw (Spain vs. Portugal U20)", 0.0005)]

    assert find_moneyline_outcome(outcomes, _matchup(), SPAIN, PORTUGAL) is None


# =============================================================================
# What the fallback exists for must still work
# =============================================================================


def test_the_ufc_matchup_shape_still_resolves():
    """The shape the fallback was written for, from its own docstring.

    If this breaks, the fix has thrown away the feature instead of narrowing it.
    """
    a, b = "Tai Tuivasa", "Robelis Despaigne"
    outcomes = [_Outcome(f"{a} vs. {b}", 0.62)]

    result = find_moneyline_outcome(outcomes, _matchup(a, b), a, b)

    assert result is not None
    assert result[0].current_probability == pytest.approx(0.62)


@pytest.mark.parametrize(
    "name",
    [
        "Pistons vs. Bulls",
        "Pistons vs Bulls",
        "Pistons versus Bulls",
        "Bulls at Pistons",
        "Bulls @ Pistons",
        "Pistons - Bulls",
    ],
)
def test_every_join_a_venue_writes_still_reads_as_the_matchup(name):
    """The joins are the allow-list, so each one has to be honoured."""
    assert outcome_name_is_the_whole_matchup(name, "Pistons", "Bulls")


# =============================================================================
# The rule is structural, not lexical
# =============================================================================


@pytest.mark.parametrize(
    "name,why",
    [
        ("Draw (Spain vs. Portugal U20)", "English"),
        ("Empate (Spain vs. Portugal U20)", "Spanish"),
        ("Unentschieden (Spain vs. Portugal U20)", "German"),
        ("Nul (Spain vs. Portugal U20)", "Dutch"),
        ("Match nul (Spain vs. Portugal U20)", "French, two words"),
        ("引き分け (Spain vs. Portugal U20)", "not Latin script at all"),
    ],
)
def test_a_draw_in_any_language_is_refused_without_a_word_for_draw(name, why):
    """No vocabulary is consulted, so no language is privileged.

    This is the property that makes the fix causal rather than a patch: the
    venue can invent a seventh spelling tomorrow and it is still refused,
    because the rule is "something is left over", not "this word appeared".
    """
    assert not outcome_name_is_the_whole_matchup(name, SPAIN, PORTUGAL), why

    source = __import__(
        "inspect"
    ).getsource(outcome_name_is_the_whole_matchup)
    body = source.split('"""')[-1]
    for word in ("draw", "empate", "unentschieden", "nul"):
        assert word not in body.lower(), (
            f"{word!r} appeared in the predicate's code — the rule has become a "
            "vocabulary, which is the instrument this file already ruled against"
        )


@pytest.mark.parametrize(
    "name",
    [
        "SBV Excelsior 2 - 2 FC Utrecht",
        "SBV Excelsior vs. FC Utrecht (Regulation)",
        "First half: SBV Excelsior vs. FC Utrecht",
        "SBV Excelsior vs. FC Utrecht - Exact Score",
    ],
)
def test_a_name_that_asks_a_different_question_is_refused(name):
    """Exact scores, periods and qualifiers are the same class as the draw.

    The exact-score shape is not hypothetical: market 59843664 on production
    carries `SBV Excelsior 2 - 2 FC Utrecht` at 0.0005, and the old predicate
    accepted it as a moneyline for the same reason it accepted the draw.
    """
    assert not outcome_name_is_the_whole_matchup(name, "SBV Excelsior", "FC Utrecht")


def test_one_team_name_inside_the_other_is_handled():
    """`Portugal` and `Portugal U20`. Removing the short name first strands a
    bare `u20` in the residue and refuses the name for an artefact of removal
    order rather than a fact about it — so the longer name goes first.
    """
    assert outcome_name_is_the_whole_matchup(
        "Portugal vs. Portugal U20", "Portugal", "Portugal U20"
    )
    assert not outcome_name_is_the_whole_matchup(
        "Draw (Portugal vs. Portugal U20)", "Portugal", "Portugal U20"
    )


def test_the_longer_team_name_is_removed_first_even_when_it_appears_second():
    """The case that actually pins the removal ORDER, which the test above does
    not: a mutation setting `reverse=False` survives `"Portugal vs. Portugal
    U20"` because there the short name's first occurrence is its own, so both
    orders happen to work.

    Put the longer name FIRST in the string and the orders diverge. Shortest
    first removes `"portugal"` out of the middle of `"portugal u20"`, leaving
    `" u20 vs. portugal"` — and `"portugal u20"` is no longer present to remove,
    so a perfectly ordinary matchup is refused.
    """
    assert outcome_name_is_the_whole_matchup(
        "Portugal U20 vs. Portugal", "Portugal", "Portugal U20"
    ), "removal order is no longer longest-first"


def test_a_team_named_twice_is_a_name_saying_something_extra():
    """Each team name is removed ONCE, not everywhere it appears.

    A name that mentions a side twice is not the bare matchup — it is the
    matchup plus a qualifier that happens to be a team name. Removing every
    occurrence erases the qualifier along with the participant and the residue
    comes back empty, so the name reads as the matchup and the fallback prices
    the wrong question. One occurrence each is what keeps the extra visible.
    """
    assert not outcome_name_is_the_whole_matchup(
        "Spain vs. Portugal U20 (Spain)", SPAIN, PORTUGAL
    )


def test_the_order_the_teams_appear_in_does_not_matter():
    assert outcome_name_is_the_whole_matchup(
        "Spain vs. Portugal U20", PORTUGAL, SPAIN
    )


@pytest.mark.parametrize(
    "name,team_a,team_b",
    [
        (None, SPAIN, PORTUGAL),
        ("", SPAIN, PORTUGAL),
        ("Spain vs. Portugal U20", None, PORTUGAL),
        ("Spain vs. Portugal U20", SPAIN, None),
        ("Spain vs. Portugal U20", "", PORTUGAL),
    ],
)
def test_a_missing_name_or_team_is_refused_rather_than_matching_everything(
    name, team_a, team_b
):
    """An empty team name is a substring of every string. Left unguarded it would
    turn this predicate into "contains the other team", which is most of the bug
    back again.
    """
    assert not outcome_name_is_the_whole_matchup(name, team_a, team_b)


# =============================================================================
# Direction, and the guards above
# =============================================================================


@pytest.mark.parametrize(
    "name",
    [
        "Draw (Spain vs. Portugal U20)",
        "Spain vs. Portugal U20",
        "Spain",
        "Portugal U20",
        "Spain vs. Portugal U20 - Exact Score",
        "Total goals over 2.5",
        "",
    ],
)
def test_the_predicate_is_a_strict_narrowing_of_the_one_it_replaces(name):
    """It may refuse where the old test accepted; it may NEVER accept where the
    old test refused. That is what makes it impossible for this change to
    re-point a resolved outcome at a different market — the production replay
    found 0 re-pointings, and this is the reason it must stay 0.
    """
    if outcome_name_is_the_whole_matchup(name, SPAIN, PORTUGAL):
        assert _old_containment_predicate(name, SPAIN, PORTUGAL), (
            f"{name!r} is accepted by the new predicate but was refused by the "
            "old one — the change is no longer a narrowing and can move a "
            "reading rather than withdraw it"
        )


def test_a_real_team_leg_still_wins_before_the_fallback_is_reached():
    """The fallback is a LAST resort and must stay one: when a leg names a team,
    that leg is the answer and this predicate is never consulted.
    """
    outcomes = [
        _Outcome("Spain vs. Portugal U20", 0.40, rank=0),  # matchup-shaped
        _Outcome("Spain", 0.9995, rank=1),  # a real team leg
    ]

    outcome, yes_is_home = find_moneyline_outcome(
        outcomes, _matchup(), SPAIN, PORTUGAL
    )

    assert outcome.name == SPAIN
    assert yes_is_home is True


def test_the_join_allowlist_is_an_allowlist_and_not_a_rejection_list():
    """Read as source: the mechanism must stay "discard known joins, refuse any
    other leftover". A rejection list is wrong here for the reason the module
    docstring gives, and it is an easy thing to drift into.
    """
    from app.utils.prediction_market_matching import _MATCHUP_JOIN_TOKENS

    assert _MATCHUP_JOIN_TOKENS == frozenset({"vs", "v", "versus", "at"})
    # Every member must be a bare word: a token carrying punctuation would never
    # survive the non-alphanumeric split and would silently never match.
    for token in _MATCHUP_JOIN_TOKENS:
        assert re.fullmatch(r"[a-z0-9]+", token), token
