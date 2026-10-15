"""#10090: a held Clippers page follows the Clippers book, not ``1 - Denver``.

Kalshi stores the Clippers side as ``Los Angeles C`` and ESPN stores the home
team as ``LA Clippers``. The resolvers' side test could not join the two, so
the Clippers outcome named no side. ``Denver`` named the away side, and the home
probability was read as ``1 - Denver``. Measured 2026-10-15 04:06:38Z, Nuggets
at Clippers (event 15326747, market 64805004): the home book was 0.54/0.55 and
Denver's was 0.46/0.47. The Kalshi leg held 0.535 for 8.4 s while the home
outcome stood at 0.545.

Fixtures are production rows (db-query 2026-10-15 ~04:20Z). Prices for the
specimen come from the retained venue replay at 04:06:38.896989Z
(artifacts/live-iteration-goal-20261011/post-11053-aftercheck/review/).
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from app.utils import live_blend as lb
from app.utils import prediction_market_matching as pmm
from app.utils.prediction_market_matching import (
    _city_initials_names_team,
    _fuzzy_team_match,
    _outcome_names_team,
    find_moneyline_outcome,
)

NOW = datetime(2026, 10, 15, 4, 6, 38, tzinfo=timezone.utc)


def _outcome(oid: int, name: str, p: str, rank: int) -> NS:
    return NS(
        id=oid, name=name, current_probability=Decimal(p), rank=rank,
        last_updated=NOW, is_winner=None,
    )


def _entry(market_id: int, name: str, ticker: str, outcomes: list) -> lb.MarketOutcomes:
    market = NS(
        id=market_id, source="kalshi", name=name, external_id=ticker,
        status="open", market_type="duel", market_metadata={},
    )
    return lb.MarketOutcomes(
        market=market, outcomes=outcomes,
        event_commence_time=datetime(2026, 10, 15, 2, 30, tzinfo=timezone.utc),
        event_has_result=False,
    )


def _den_lac(order: str = "home_first", lac: str = "0.545", den: str = "0.465"):
    outs = [
        _outcome(243704122, "Los Angeles C", lac, 1),
        _outcome(243704123, "Denver", den, 2),
    ]
    if order == "away_first":
        outs.reverse()
    return _entry(64805004, "Denver vs Los Angeles C", "KXNBAGAME-26OCT14DENLAC", outs)


def _old_side_test(outcome_name: str, event_team: str) -> bool:
    """The side test as deployed at 4cb8198f2c, before this arm."""
    return _fuzzy_team_match(outcome_name, event_team) or pmm._doubles_pair_match(
        outcome_name, event_team
    )


# ── the specimen, end to end through the blend writer's reader ─────────────


@pytest.mark.parametrize("order", ["home_first", "away_first"])
def test_specimen_15326747_reads_the_home_book(order):
    reading = lb.compute_source_home_probability(
        [_den_lac(order)], "LA Clippers", "Denver Nuggets",
    )
    assert reading is not None
    assert reading.home_probability == pytest.approx(0.545)
    assert reading.outcome.id == 243704122


def test_specimen_follows_a_home_only_move():
    """The defect's visible shape: the home book moves and Denver's does not."""
    before = lb.compute_source_home_probability(
        [_den_lac(lac="0.535")], "LA Clippers", "Denver Nuggets",
    )
    after = lb.compute_source_home_probability(
        [_den_lac(lac="0.545")], "LA Clippers", "Denver Nuggets",
    )
    assert (before.home_probability, after.home_probability) == pytest.approx(
        (0.535, 0.545)
    )


def test_strawman_the_deployed_side_test_reads_one_minus_denver(monkeypatch):
    """Proves the specimen exercises the new arm. Without it the reader picks
    Denver and prints 0.535 against a 0.545 home book."""
    monkeypatch.setattr(pmm, "_outcome_names_team", _old_side_test)
    reading = lb.compute_source_home_probability(
        [_den_lac()], "LA Clippers", "Denver Nuggets",
    )
    assert reading.outcome.id == 243704123
    assert reading.home_probability == pytest.approx(0.535)


def test_control_a_clippers_row_already_stored_in_full_is_unchanged():
    """Event 15324790 stores ``Los Angeles Clippers``, which the old rule reached."""
    outs = [
        _outcome(247725379, "Los Angeles C", "0.59", 1),
        _outcome(247725380, "Sacramento", "0.415", 2),
    ]
    entry = _entry(65904594, "Sacramento vs Los Angeles C", "KXNBAGAME-26OCT21SACLAC", outs)
    assert _old_side_test("Los Angeles C", "Los Angeles Clippers")
    reading = lb.compute_source_home_probability(
        [entry], "Los Angeles Clippers", "Sacramento Kings",
    )
    assert reading.outcome.id == 247725379
    assert reading.home_probability == pytest.approx(0.59)


def test_every_resolver_caller_gets_the_same_side():
    """The poll writer and the chart backfill call `find_moneyline_outcome`
    directly. They must pick the row the live reader picks, or two writers
    alternate between 0.545 and 0.535 on one leg."""
    entry = _den_lac("away_first")
    matchup = lb._matchup_for_entry(entry)
    outcome, yes_is_home = find_moneyline_outcome(
        list(entry.outcomes), matchup, "LA Clippers", "Denver Nuggets",
    )
    assert (outcome.id, yes_is_home) == (243704122, True)


# ── same city, derivatives and draws ───────────────────────────────────────


def _lal_lac(lal: str, lac: str) -> lb.MarketOutcomes:
    outs = [_outcome(1, "Los Angeles L", lal, 1), _outcome(2, "Los Angeles C", lac, 2)]
    return _entry(1, "Los Angeles L vs Los Angeles C", "KXNBAGAME-26OCT30LALLAC", outs)


# (Lakers price, Clippers price, home, away, expected home probability)
_SAME_CITY = [
    ("0.62", "0.39", "Los Angeles Lakers", "LA Clippers", 0.62),
    ("0.62", "0.39", "LA Clippers", "Los Angeles Lakers", 0.38),
    ("0.39", "0.62", "Los Angeles Lakers", "LA Clippers", 0.39),
    ("0.39", "0.62", "LA Clippers", "Los Angeles Lakers", 0.61),
]


@pytest.mark.parametrize("lal, lac, home, away, expected", _SAME_CITY)
def test_same_city_lakers_and_clippers_stay_apart(lal, lac, home, away, expected):
    """``Los Angeles C`` names ``LA Clippers`` by its letter. It also reaches
    ``Los Angeles Lakers`` through the linker's containment rule, because
    ``normalize_name`` deletes the trailing ``c``. A name that reaches both
    sides is refused (#4629). The Lakers row alone orients the market, and the
    reading is the right team whichever club is favoured."""
    reading = lb.compute_source_home_probability([_lal_lac(lal, lac)], home, away)
    assert reading.outcome.name == "Los Angeles L"
    assert reading.home_probability == pytest.approx(expected)
    assert not _outcome_names_team("Los Angeles L", "LA Clippers")
    assert not _city_initials_names_team("Los Angeles C", "Los Angeles Lakers")


@pytest.mark.parametrize(
    "home, away, wrong",
    [("Los Angeles Lakers", "LA Clippers", 0.62), ("LA Clippers", "Los Angeles Lakers", 0.38)],
)
def test_strawman_the_deployed_side_test_prices_the_wrong_la_club(monkeypatch, home, away, wrong):
    """With the Clippers favoured, the old rule read ``Los Angeles C`` as the
    Lakers. It printed the Clippers' price for a Lakers home game, and the
    inverse for a Clippers home game."""
    monkeypatch.setattr(pmm, "_outcome_names_team", _old_side_test)
    reading = lb.compute_source_home_probability([_lal_lac("0.39", "0.62")], home, away)
    assert reading.outcome.name == "Los Angeles C"
    assert reading.home_probability == pytest.approx(wrong)


def test_first_half_market_on_the_specimen_event_still_never_speaks():
    outs = [
        _outcome(246380934, "Denver", "0.01", 2),
        _outcome(246380935, "Los Angeles C", "0.99", 1),
        _outcome(246380936, "Tie", "0.01", 2),
    ]
    entry = _entry(
        65551442, "Denver vs Los Angeles C: 1st Half Winner",
        "KXNBA1H-26OCT14DENLAC", outs,
    )
    assert lb._reading_for_entry(entry, "LA Clippers", "Denver Nuggets") is None


def test_galaxy_three_way_reads_its_partition_and_tie_names_no_side():
    """Market 65551448. Before this arm ``Los Angeles G`` named no side,
    ``Portland`` named the away side, and the away-leg complement of a
    three-way board was refused, so the event carried no Kalshi leg."""
    outs = [
        _outcome(246380960, "Los Angeles G", "0.975", 1),
        _outcome(246380961, "Portland", "0.01", 3),
        _outcome(246380962, "Tie", "0.025", 2),
    ]
    entry = _entry(65551448, "Los Angeles G vs Portland", "KXMLSGAME-26OCT14LAGPOR", outs)
    reading = lb._reading_for_entry(entry, "LA Galaxy", "Portland Timbers")
    assert reading is not None
    _matchup, home, outcome, _yes, away, draw = reading
    assert (outcome.id, home, away, draw) == (246380960, 0.975, 0.01, 0.025)
    assert not _outcome_names_team("Tie", "LA Galaxy")
    assert not _outcome_names_team("Tie", "Portland Timbers")


# ── the predicate ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "outcome, team, expected",
    [
        ("Los Angeles C", "LA Clippers", True),
        ("Los Angeles G", "LA Galaxy", True),
        ("Chicago WS", "Chicago White Sox", True),
        ("New York R", "New York Rangers", True),
        ("Los Angeles C", "Los Angeles Lakers", False),  # same city, other letter
        ("Los Angeles A", "LA Clippers", False),
        ("San Diego C", "LA Clippers", False),  # other city, same letter
        ("Los Angeles c", "LA Clippers", False),  # the capital is the evidence
        ("Los Angeles LAC", "LA Clippers", False),  # three capitals: not initials
        ("C", "LA Clippers", False),  # no city
        ("Denver", "Denver Nuggets", False),  # not truncated: the old rule's case
        ("Tie", "LA Clippers", False),
        ("Chicago C wins 6th inning", "Chicago Cubs", False),
        ("Los Angeles C", "Clippers", False),  # a bare nickname has no city
    ],
)
def test_city_initials_names_team(outcome, team, expected):
    assert _city_initials_names_team(outcome, team) is expected


def test_the_linker_rule_is_not_widened():
    """The arm lives in the resolvers' side test only (#8722's reason)."""
    assert not _fuzzy_team_match("Los Angeles C", "LA Clippers")
    assert not _fuzzy_team_match("Los Angeles G", "LA Galaxy")
