"""T2-3 (#5060): explicit question intent in a search query.

WHAT THESE GUARDS ARE FOR. `parse_intent` decides whether a reader asked a
question or merely named a thing, and the cost of the two errors is wildly
asymmetric. A missed intent leaves the reader exactly where they were before the
slice existed. A FALSE intent re-composes the whole page around a question
nobody asked — which is why most of this file is controls rather than cases.

Every test below names the mutation it kills. A guard that passes under a
plausible mutation of the code it guards is vacuous, and a scope restriction is
mutated by DELETING it, never by nudging its constant to a neighbour (which is
usually equivalent and reads as a hole).
"""

import pytest

from app.utils.search_intent import (
    INTENT_DIVISION,
    INTENT_KINDS,
    INTENT_MAKE_CUT,
    INTENT_NEXT_TEAM,
    INTENT_PLAYOFFS,
    INTENT_SEASON_YEAR,
    INTENT_TODAY,
    INTENT_WIN_TOTAL,
    SEASON_MAX,
    SEASON_MIN,
    SearchIntent,
    parse_intent,
)


# ── The seven, as #5060 and the design name them ─────────────────────────────

@pytest.mark.parametrize(
    "query,kind,subject",
    [
        # The three the issue body names by hand.
        ("Patriots playoffs", INTENT_PLAYOFFS, "Patriots"),
        ("Patriots wins", INTENT_WIN_TOTAL, "Patriots"),
        ("Patriots 10 wins", INTENT_WIN_TOTAL, "Patriots"),
        # The rest of the design's list: next team, division, today, a year,
        # make cut.
        ("mahomes next team", INTENT_NEXT_TEAM, "mahomes"),
        ("patriots division", INTENT_DIVISION, "patriots"),
        ("patriots today", INTENT_TODAY, "patriots"),
        ("patriots 2025", INTENT_SEASON_YEAR, "patriots"),
        ("scheffler make cut", INTENT_MAKE_CUT, "scheffler"),
        # Phrasings a reader actually types for the same seven.
        ("patriots make the playoffs", INTENT_PLAYOFFS, "patriots"),
        ("patriots to win the division", INTENT_DIVISION, "patriots"),
        ("scheffler to make the cut", INTENT_MAKE_CUT, "scheffler"),
        ("patriots regular season wins", INTENT_WIN_TOTAL, "patriots"),
    ],
)
def test_the_seven_scaffolds_resolve_to_kind_and_subject(query, kind, subject):
    """Kills: deleting any one scaffold pattern, and any strip that eats the
    subject along with the scaffold."""
    got = parse_intent(query)
    assert got is not None, f"{query!r} produced no intent"
    assert got.kind == kind
    assert got.subject == subject


def test_every_kind_produced_is_in_the_declared_vocabulary():
    """Kills: a kind string invented at a call site and never declared.

    The clients read `kind` as data, so an undeclared value is a silent contract
    break rather than an error.
    """
    queries = [
        "Patriots playoffs", "Patriots wins", "Patriots 10 wins",
        "mahomes next team", "patriots division", "patriots today",
        "patriots 2025", "scheffler make cut",
    ]
    for q in queries:
        got = parse_intent(q)
        assert got is not None and got.kind in INTENT_KINDS


# ── The controls. T2-3's acceptance names these explicitly. ──────────────────

@pytest.mark.parametrize(
    "query",
    [
        # T2-3's named controls — "generic `ai`, `ipo`, weather and award
        # controls unchanged". These must not reach the new path at all.
        "ai", "ipo", "weather", "emmys", "british open", "super bowl",
        # Bare entity names: a name is not a question (ruling 041 proper).
        "patriots", "red sox", "sox", "1. FC Kaiserslautern",
        # Refusal 1: a scaffold with no subject left is not an intent. There is
        # no entity for the question to lead, so these stay generic searches.
        "playoffs", "today", "wins", "next team", "make cut", "division",
        "2026", "2025 wins",
        # Refusal 2: word boundaries, never substrings.
        "divisional round", "todays games",
    ],
)
def test_generic_queries_produce_no_intent(query):
    """Kills: dropping refusal 1 (the empty-subject return), and widening any
    `\\b` anchor to a substring match.

    `divisional round` is the sharpest of these: it contains "division" as a
    prefix. A substring rule would fire, and that is the same failure family
    that had `ai` answering "1. FC K-**ai**-serslautern" before the match-class
    scorer existed.
    """
    assert parse_intent(query) is None


@pytest.mark.parametrize("query", [None, "", "   ", "\t\n"])
def test_empty_input_is_not_an_intent(query):
    """Kills: an unguarded `.strip()` or index on a falsy query."""
    assert parse_intent(query) is None


# ── Ordering inside the taxonomy ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "query",
    [
        "patriots win the division",
        "patriots to win division",
        "patriots wins division",
    ],
)
def test_the_word_wins_does_not_steal_a_division_question(query):
    """Kills: moving `_BARE_WINS_RE` earlier in `_SCAFFOLDS`.

    The division scaffold CONTAINS the word "wins". If the unnumbered win-total
    pattern is tried first, every one of these answers the win-total question
    instead of the division question the reader asked — a wrong answer that
    looks confident. This is the single mutation that makes the scaffold order
    load-bearing, so it is pinned rather than left to comment.
    """
    got = parse_intent(query)
    assert got is not None
    assert got.kind == INTENT_DIVISION, f"{query!r} was claimed by {got.kind}"
    assert got.subject == "patriots"


def test_a_numbered_win_total_beats_a_bare_season_year():
    """Kills: ordering `season_year` ahead of `win_total`.

    "patriots 2025 10 wins" names BOTH. The reader's question is the wins; 2025
    is a qualifier on it, and must survive as one rather than becoming the
    question.
    """
    got = parse_intent("patriots 2025 10 wins")
    assert got is not None
    assert got.kind == INTENT_WIN_TOTAL
    assert got.threshold == 10.0
    assert got.season == 2025
    assert got.subject == "patriots"


# ── Qualifiers are lifted, never dropped ─────────────────────────────────────

@pytest.mark.parametrize(
    "query,threshold",
    [
        ("Patriots 10 wins", 10.0),
        ("patriots 9+ wins", 9.0),
        # The direction-word forms are DELEGATED to
        # `ladder_monotonicity.parse_threshold`. These two kill the deletion of
        # that delegation: the bare-form regex cannot read either one.
        ("patriots over 8.5 wins", 8.5),
        ("patriots at least 10 wins", 10.0),
    ],
)
def test_the_threshold_a_reader_typed_survives(query, threshold):
    """Kills: dropping the threshold capture, and dropping the delegation to
    `parse_threshold` for the direction-word half."""
    got = parse_intent(query)
    assert got is not None and got.kind == INTENT_WIN_TOTAL
    assert got.threshold == threshold


def test_an_unnumbered_win_question_is_still_a_win_question():
    """Kills: refusing a win-total whose rung the reader did not state.

    `threshold is None` is a DESIGNED state here (decision C answers it with the
    supported threshold nearest 50%), not a parse failure. Refusing it sends
    "Patriots wins" back to the bare-name default, where the win question sits
    third — behind the team card and the game — which is the exact ordering the
    reader overrode by typing the word.
    """
    got = parse_intent("Patriots wins")
    assert got is not None
    assert got.kind == INTENT_WIN_TOTAL
    assert got.threshold is None


@pytest.mark.parametrize(
    "query",
    [
        "patriots miss playoffs",
        "patriots will not make the playoffs",
        "patriots won't make the playoffs",
        "scheffler fails to make the cut",
    ],
)
def test_negation_is_captured_and_not_silently_discarded(query):
    """Kills: dropping the negation capture.

    An intent whose negation is lost answers the OPPOSITE question. The subject
    and kind are still right, which is what makes the failure invisible without
    this assertion.
    """
    got = parse_intent(query)
    assert got is not None
    assert got.negated is True


def test_an_unnegated_question_is_not_marked_negated():
    """Kills: hardcoding `negated=True` — the other half of the mutation pair.

    Without this, a mutant that always negates passes every test above.
    """
    got = parse_intent("patriots make the playoffs")
    assert got is not None and got.negated is False


# ── The season bound is a restriction, so it is mutated by REMOVAL ───────────

@pytest.mark.parametrize("year", [SEASON_MIN, 2025, SEASON_MAX])
def test_a_year_inside_the_bound_is_read_as_a_season(year):
    got = parse_intent(f"patriots {year}")
    assert got is not None
    assert got.season == year


@pytest.mark.parametrize("year", [1899, 1066, 3500, 9999])
def test_a_four_digit_run_outside_the_bound_is_not_a_season(year):
    """Kills: DELETING the `SEASON_MIN <= y <= SEASON_MAX` restriction.

    Mutated by removal rather than by nudging a bound to a neighbour: a
    neighbouring constant is equivalent on every realistic query and so reads as
    a hole in the suite. Unbounded, a club's founding year ("Sheffield FC 1857")
    and any four-digit run in a market's own name become season qualifiers.
    """
    assert parse_intent(f"patriots {year}") is None


def test_a_four_digit_year_is_never_read_as_a_win_total():
    """Kills: widening the bare win-total magnitude from `\\d{1,3}`.

    With `\\d{1,4}` the query "patriots 2025 wins" parses as a 2025-WIN total —
    a number no team can reach in any sport we carry — instead of the 2025
    season. Measured on this tree before the guard existed: the `\\b` after a
    3-digit cap is what refuses it.
    """
    got = parse_intent("patriots 2025 wins")
    assert got is not None
    assert got.season == 2025
    assert got.threshold != 2025.0


# ── The subject is an entity, on both code paths ─────────────────────────────

@pytest.mark.parametrize(
    "query", ["will patriots 2025", "the patriots 2025", "patriots 2025"]
)
def test_the_season_path_strips_residual_scaffold_like_the_scaffold_path_does(query):
    """Kills: dropping the residual strip from the season fall-through.

    Two paths reach `SearchIntent`, and both must agree on what a subject is.
    Without the strip the season path returns the subject "will patriots" or
    "the patriots" — a string no entity owns, so identity resolution downstream
    finds nothing and the question is composed about a subject that does not
    exist.

    THE INPUT HERE IS NOT ARBITRARY, and the first version of this guard was
    vacuous. It asserted `parse_intent("2025 wins") is None`, which is true —
    but true for an unrelated reason: `_BARE_WINS_RE` claims that query before
    the season fall-through is ever reached, and refusal 1 kills it there. The
    mutation this test names SURVIVED while the assertion passed. Only a query
    that actually lands on the season path can guard the season path.
    """
    got = parse_intent(query)
    assert got is not None
    assert got.season == 2025
    assert got.subject == "patriots"


def test_the_intent_is_immutable():
    """Kills: unfreezing the dataclass.

    The intent crosses into the composition and both clients read it; a consumer
    that can mutate it in place is a second writer of the reader's question.
    """
    got = parse_intent("Patriots playoffs")
    assert isinstance(got, SearchIntent)
    with pytest.raises(Exception):
        got.kind = INTENT_TODAY  # type: ignore[misc]
