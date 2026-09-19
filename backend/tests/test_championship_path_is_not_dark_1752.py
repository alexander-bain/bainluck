"""#1752 — the team page's championship path was dark on EVERY team.

Two defects, one section:

1. ``_get_championship_path``'s ``graded`` subquery auto-correlated BOTH
   entities away and raised ``InvalidRequestError`` at COMPILE time, on every
   call, for every team. ``routes/teams.py``'s ``except Exception`` swallowed it
   into ``[]``, so a whole reader-facing section was missing and nothing —
   no log-free health check, no coverage count, no row-shaped test — could see
   it. Every row-shaped test of this function passed while it raised 100% of the
   time in production, because "no markets" and "the query never ran" produce
   the same empty list. The only test that can catch this class COMPILES the
   statement, so that is what the first class below does.

2. Un-blinding it alone would have printed confident lies. The step's label is
   the TIER (``Win Division``), and ``market_tier`` is mis-assigned for whole
   families: measured on production 2026-09-19, Boston's tier-4 candidates were
   "Pro Baseball Playoff Qualifiers" 99.5% and "AL East Division Winner" 1%, so
   the repaired section would have rendered "Win Division 50%" for a team 1% to
   win its division. The gates withhold what cannot be labelled truthfully.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import InvalidRequestError

from app.models import FuturesMarket, FuturesOutcome
from app.routes.teams import (
    _TIER_AGREEMENT_BAR,
    _answers_its_tier,
    _championship_path_stmt,
    _get_championship_path,
    _tier_candidates_agree,
)


# ---------------------------------------------------------------------------
# 1. The statement must COMPILE. A row-shaped test cannot see this class.
# ---------------------------------------------------------------------------


def test_championship_path_statement_compiles():
    """The regression itself: this raised InvalidRequestError for every team."""
    stmt = _championship_path_stmt(853)
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "futures_outcomes" in sql


def test_compiled_statement_keeps_the_settled_market_guard():
    """The NOT EXISTS must survive with futures_outcomes in its own FROM.

    `.correlate(FuturesMarket)` is what keeps it there. Correlating nothing (the
    default) strips both entities and the statement stops compiling; correlating
    the wrong entity would silently change which markets count as settled.
    """
    sql = " ".join(
        str(_championship_path_stmt(853).compile(dialect=postgresql.dialect())).split()
    )

    assert "NOT (EXISTS (SELECT futures_outcomes.id FROM futures_outcomes" in sql
    assert "futures_outcomes.market_id = futures_markets.id" in sql
    assert "futures_outcomes.is_winner IS true" in sql


def test_the_uncorrelated_form_is_the_bug_and_still_raises():
    """The control. Without this, the test above cannot fail.

    Every assertion in this file is satisfied by a statement that simply does
    not have the defect, so the defect is rebuilt here and asserted to raise. If
    SQLAlchemy ever stops raising on it, the repair's necessity has changed and
    these tests must be re-read rather than trusted.
    """
    graded = select(FuturesOutcome.id).where(
        FuturesOutcome.market_id == FuturesMarket.id,
        FuturesOutcome.is_winner.is_(True),
    )
    broken = (
        select(FuturesOutcome, FuturesMarket)
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .where(FuturesOutcome.team_id == 853, ~graded.exists())
    )

    with pytest.raises(InvalidRequestError, match="no FROM clauses"):
        broken.compile(dialect=postgresql.dialect())


def test_the_route_still_selects_only_ungraded_open_unlinked_tier_124():
    """The repair must not widen the population it serves."""
    sql = " ".join(
        str(_championship_path_stmt(853).compile(dialect=postgresql.dialect())).split()
    )

    assert "futures_markets.status = " in sql
    assert "futures_markets.event_id IS NULL" in sql
    assert "futures_markets.market_tier IN " in sql
    assert "futures_outcomes.team_id = " in sql


# ---------------------------------------------------------------------------
# 2. A step may not carry a label its market does not answer.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Pro Baseball Playoff Qualifiers",  # tier 4 → would read "Win Division"
        "College Football Playoff Qualifiers",
        "Pro Basketball Playoff Qualifiers",
        "NL Reliever of the Year Winner?",  # tier 1 → would read "Win Championship"
        "AL Reliever of the Year Winner?",
        "Bear Bryant Coach of the Year Winner",
        "Pro Football Championship Halftime Show: Headliner",
    ],
)
def test_a_market_that_does_not_answer_its_tier_is_excluded(name):
    """Every one of these was measured at tier 1/2/4 on production."""
    assert _answers_its_tier(name) is False


@pytest.mark.parametrize(
    "name",
    [
        "MLB World Series Champion 2026",
        "Pro Baseball Champion",
        "American League Champion",
        "AL East Division Winner",
        "NCAAB Championship Winner",
        "NHL Championship Winner",
        "MLS Western Conference Champion",
        "Welterweight Title Holder on Dec 31, 2026?",
        "FIFA World Cup Winner",
        "College Football Big Ten Championship Winner",
    ],
)
def test_a_real_title_market_is_kept(name):
    """The control for the exclusion: it must not eat the section it exists for.

    Without this arm, an exclusion that returned False for everything would pass
    every test above and ship a permanently empty path.
    """
    assert _answers_its_tier(name) is True


def test_the_exclusion_is_case_insensitive_and_survives_a_missing_name():
    assert _answers_its_tier("PRO BASEBALL PLAYOFF QUALIFIERS") is False
    assert _answers_its_tier(None) is True  # nothing to disqualify it on


# ---------------------------------------------------------------------------
# 3. A tier whose sources disagree is withheld, not averaged.
# ---------------------------------------------------------------------------


def test_two_sources_on_one_question_are_blended():
    """Measured: Boston's two championship markets priced 4.55% and 4.95%."""
    assert _tier_candidates_agree([0.0455, 0.0495]) is True


def test_a_qualification_market_beside_a_division_market_is_withheld():
    """Boston tier 4 on production: 99.5% to qualify, 1% to win the AL East.

    Averaging them prints "Win Division 50%", which describes neither.
    """
    assert _tier_candidates_agree([0.995, 0.01]) is False


def test_two_teams_sharing_one_team_id_are_withheld():
    """team_id 6610 carries BOTH "New York Y" and "New York M" on production.

    The path cannot say which team the number is about, so it says nothing. The
    conflation itself is a matching defect and is filed separately.
    """
    assert _tier_candidates_agree([0.995, 0.11, 0.01, 0.01]) is False


def test_a_single_source_always_agrees_with_itself():
    assert _tier_candidates_agree([0.42]) is True


def test_an_empty_tier_does_not_agree():
    """Fail closed: nothing to publish is not the same as a number to publish."""
    assert _tier_candidates_agree([]) is False


def test_the_bar_is_inclusive_at_its_edge():
    """Pins the boundary so a refactor cannot move it silently."""
    assert _tier_candidates_agree([0.10, 0.10 + _TIER_AGREEMENT_BAR]) is True
    assert _tier_candidates_agree([0.10, 0.10 + _TIER_AGREEMENT_BAR + 0.001]) is False


# ---------------------------------------------------------------------------
# 4. The gates must be WIRED. Everything above passes on a tree where both
#    call sites have been deleted, so these drive the real function.
# ---------------------------------------------------------------------------


class _FakeMarket:
    def __init__(self, id, name, tier, group_id=None):
        self.id = id
        self.name = name
        self.market_tier = tier
        self.group_id = group_id
        self.canonical_market_key = None


class _FakeOutcome:
    def __init__(self, name, probability):
        self.name = name
        self.current_probability = probability
        self.rank = None
        self.probability_change_24h = None


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """`_get_championship_path` uses exactly `(await db.execute(stmt)).all()`."""

    def __init__(self, rows):
        self._rows = rows
        self.statements = []

    async def execute(self, stmt):
        # Compiling here is what makes this a test of the REAL statement: a
        # regressed subquery raises from this line, exactly as production does.
        str(stmt.compile(dialect=postgresql.dialect()))
        self.statements.append(stmt)
        return _FakeResult(self._rows)


# Boston Red Sox (team_id 10709) exactly as production served it on 2026-09-19.
_BOSTON_ROWS = [
    (_FakeOutcome("Brayan Bello", 0.01), _FakeMarket(1, "AL Reliever of the Year Winner?", 1)),
    (_FakeOutcome("Boston", 0.0495), _FakeMarket(2, "Pro Baseball Champion", 1)),
    (_FakeOutcome("Aroldis Chapman", 0.03), _FakeMarket(3, "AL Reliever of the Year Winner?", 1)),
    (_FakeOutcome("Boston Red Sox", 0.0455), _FakeMarket(4, "MLB World Series Champion 2026", 1)),
    (_FakeOutcome("Boston", 0.12), _FakeMarket(5, "American League Champion", 2)),
    (_FakeOutcome("Boston", 0.01), _FakeMarket(6, "AL East Division Winner", 4)),
    (_FakeOutcome("Boston", 0.995), _FakeMarket(7, "Pro Baseball Playoff Qualifiers", 4)),
]


@pytest.mark.asyncio
async def test_the_boston_specimen_renders_a_truthful_path():
    """The ship, on the issue's own specimen.

    Before #1752 this returned `[]` for every team. The naive repair would have
    returned "Win Division 50%" — the mean of 99.5% to qualify and 1% to win the
    division.
    """
    path = await _get_championship_path(10709, _FakeDB(_BOSTON_ROWS))
    by_label = {e["label"]: e for e in path}

    assert set(by_label) == {"Championship", "Conference", "Division"}

    # Tier 4: the qualification market is gone, the division market is the step.
    assert by_label["Division"]["probability"] == pytest.approx(0.01)
    assert by_label["Division"]["market_name"] == "AL East Division Winner"

    # Tier 1: the two award legs are gone; the two championship markets are one
    # question priced by two sources, so they blend.
    assert by_label["Championship"]["probability"] == pytest.approx(0.0475)

    assert by_label["Conference"]["probability"] == pytest.approx(0.12)


@pytest.mark.asyncio
async def test_no_step_carries_a_market_that_does_not_answer_its_tier():
    """Kills the mutant that deletes the `_answers_its_tier` call site."""
    path = await _get_championship_path(10709, _FakeDB(_BOSTON_ROWS))

    names = [e["market_name"] for e in path]
    assert not any("Playoff Qualifiers" in n for n in names)
    assert not any("of the Year" in n for n in names)

    # And the number must not be a mean that WAS dragged by them.
    assert all(e["probability"] < 0.5 for e in path)


@pytest.mark.asyncio
async def test_a_tier_whose_sources_disagree_is_withheld_entirely():
    """team_id 6610 carries both "New York Y" and "New York M" on production.

    Kills the mutant that deletes the `_tier_candidates_agree` call site: with
    the qualification markets already excluded, the surviving division markets
    still describe two different teams (11% and 1%), and the step is dropped
    rather than averaged into 6%.
    """
    rows = [
        (_FakeOutcome("New York Y", 0.11), _FakeMarket(1, "AL East Division Winner", 4)),
        (_FakeOutcome("New York M", 0.01), _FakeMarket(2, "NL East Division Winner", 4)),
        (_FakeOutcome("New York Y", 0.08), _FakeMarket(3, "Pro Baseball Champion", 1)),
    ]

    path = await _get_championship_path(6610, _FakeDB(rows))

    assert [e["label"] for e in path] == ["Championship"]  # tier 4 withheld
    assert all(e["tier"] != 4 for e in path)


@pytest.mark.asyncio
async def test_a_team_with_only_untrustworthy_markets_gets_an_empty_path():
    """Honest-empty is a real answer — the card simply does not render."""
    rows = [
        (_FakeOutcome("Boston", 0.995), _FakeMarket(1, "Pro Baseball Playoff Qualifiers", 4)),
        (_FakeOutcome("Mason Miller", 0.945), _FakeMarket(2, "NL Reliever of the Year Winner?", 1)),
    ]

    assert await _get_championship_path(10745, _FakeDB(rows)) == []


@pytest.mark.asyncio
async def test_the_section_is_not_dark_for_a_plain_team():
    """The control for every withholding assertion above.

    Each one is also satisfied by a function that returns `[]` for everything —
    which is precisely the bug. This is the arm that fails if it does.
    """
    rows = [
        (_FakeOutcome("Arsenal", 0.31), _FakeMarket(1, "Premier League Winner", 1)),
    ]

    path = await _get_championship_path(1826, _FakeDB(rows))

    assert len(path) == 1
    assert path[0]["label"] == "Championship"
    assert path[0]["probability"] == pytest.approx(0.31)
