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
import time
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


# ── the reader's own guards use the resolver's side test (caller parity) ───
#
# The selector above names sides with `_outcome_names_team`. Two guards
# downstream of it, `_is_unique_named_home_quote` and
# `away_leg_complement_is_not_home`, still named sides with the linker's
# narrower `_fuzzy_team_match` at ee8cd3ae20. So the selector picked
# ``Los Angeles G`` as the away leg of a three-way board, the draw guard could
# not see it was the away leg, and P(home) + P(Tie) was published as home. The
# Clippers row was selected but never proven home, so a stale cached flip could
# still invert it. Counterexamples: Argon's review, reproduced by Root
# (artifacts/live-iteration-goal-20261011/post-11053-aftercheck/
# argon-selection-review/ROOT-COUNTEREXAMPLES.json).


def _guards_on_the_linker_rule(monkeypatch) -> None:
    """The two guards as merged at ee8cd3ae20; the selector keeps the new arm."""
    monkeypatch.setattr(lb, "_pmm", NS(_outcome_names_team=_fuzzy_team_match))


def _priced(oid: int, name: str, p, rank: int) -> NS:
    out = _outcome(oid, name, "0", rank)
    out.current_probability = None if p is None else Decimal(p)
    return out


def _galaxy_at_portland_unpriced_home(order: str) -> lb.MarketOutcomes:
    """Market 65551448 read as Portland's home game, Portland's price absent."""
    outs = [
        _priced(246380960, "Los Angeles G", "0.305", 1),
        _priced(246380961, "Portland", None, 3),
        _priced(246380962, "Tie", "0.230", 2),
    ]
    if order == "reversed":
        outs.reverse()
    return _entry(65551448, "Los Angeles G vs Portland", "KXMLSGAME-26OCT14LAGPOR", outs)


def _el_trafico(order: str) -> lb.MarketOutcomes:
    """Fully priced, and ``Los Angeles FC`` names no side of ``LAFC``."""
    outs = [
        _priced(1, "Los Angeles FC", "0.45", 1),
        _priced(2, "Los Angeles G", "0.30", 2),
        _priced(3, "Tie", "0.25", 3),
    ]
    if order == "reversed":
        outs.reverse()
    return _entry(
        2, "Los Angeles FC vs Los Angeles G", "KXMLSGAME-26OCT18LAFLAG", outs,
    )


# (fixture, home, away, the draw-inflated home the merged guards published)
_DRAW_BOARDS = [
    (_galaxy_at_portland_unpriced_home, "Portland Timbers", "LA Galaxy", 0.695),
    (_el_trafico, "LAFC", "LA Galaxy", 0.70),
]


@pytest.mark.parametrize("order", ["listed", "reversed"])
@pytest.mark.parametrize("board, home, away, _inflated", _DRAW_BOARDS)
def test_a_named_away_leg_of_a_draw_board_is_never_complemented(
    board, home, away, _inflated, order
):
    """Both the live reader and the chart's orientation refuse, as the parent
    did. The selector still names ``Los Angeles G`` as the away leg."""
    from app.tasks.event_chart_backfill import _orient_one_market

    entry = board(order)
    outcome, yes_is_home = find_moneyline_outcome(
        sorted(entry.outcomes, key=lambda o: o.rank), lb._matchup_for_entry(entry),
        home, away,
    )
    assert (outcome.name, yes_is_home) == ("Los Angeles G", False)
    assert lb.compute_source_home_probability([entry], home, away) is None
    assert _orient_one_market(entry, home, away, is_primary=True) is None


@pytest.mark.parametrize("board, home, away, inflated", _DRAW_BOARDS)
def test_strawman_guards_on_the_linker_rule_publish_home_plus_tie(
    monkeypatch, board, home, away, inflated
):
    """The counterexamples reproduce at ee8cd3ae20's guards, so the test above
    is not vacuous: the reader prints P(home) + P(Tie) and the chart orients."""
    from app.tasks.event_chart_backfill import _orient_one_market

    _guards_on_the_linker_rule(monkeypatch)
    entry = board("listed")
    reading = lb.compute_source_home_probability([entry], home, away)
    assert reading.outcome.name == "Los Angeles G"
    assert reading.home_probability == pytest.approx(inflated)
    _market, outcome, is_home = _orient_one_market(entry, home, away, is_primary=True)
    assert (outcome.name, is_home) == ("Los Angeles G", False)


def test_the_galaxy_home_partition_is_still_read_when_fully_priced():
    """Control: a fully valid draw partition still speaks, with its draw."""
    entry = _galaxy_at_portland_unpriced_home("listed")
    entry.outcomes[1].current_probability = Decimal("0.465")
    reading = lb.compute_source_home_probability([entry], "LA Galaxy", "Portland Timbers")
    assert reading.outcome.id == 246380960
    assert (reading.home_probability, reading.away_probability, reading.draw_probability) == (
        pytest.approx(0.305), pytest.approx(0.465), pytest.approx(0.230)
    )


@pytest.mark.parametrize("order", ["home_first", "away_first"])
def test_the_specimens_clippers_row_is_a_proven_home_quote(order):
    reading = lb.compute_source_home_probability(
        [_den_lac(order)], "LA Clippers", "Denver Nuggets",
    )
    assert reading.outcome.id == 243704122
    assert reading.named_home_quote is True
    assert lb.has_proven_home_orientation(reading)


def test_a_home_only_move_is_read_from_the_home_row_both_times():
    """At 0.535/0.465 the home row and ``1 - Denver`` print the same number, so
    the price alone cannot say which row was read."""
    before = lb.compute_source_home_probability(
        [_den_lac(lac="0.535")], "LA Clippers", "Denver Nuggets",
    )
    after = lb.compute_source_home_probability(
        [_den_lac(lac="0.545")], "LA Clippers", "Denver Nuggets",
    )
    assert (before.outcome.id, after.outcome.id) == (243704122, 243704122)
    assert before.named_home_quote and after.named_home_quote


class _NoFallbackSession:
    """Any read the inversion fallback would make fails the test."""

    async def get(self, *args, **kwargs):
        raise AssertionError("fallback Event read")

    async def execute(self, *args, **kwargs):
        raise AssertionError("fallback OddsSnapshot read")


def _forbid_inversion_fallback(monkeypatch) -> None:
    async def forbidden(*args, **kwargs):
        raise AssertionError("_check_and_fix_inversion called")

    monkeypatch.setattr(
        "app.tasks.prediction_market_matching._check_and_fix_inversion", forbidden,
    )


async def test_a_stale_cached_flip_cannot_invert_the_selected_clippers_row(monkeypatch):
    """The live refresher's actual `_oriented`: the named home quote evicts the
    cached flip and never reaches the fallback reads."""
    from app.tasks import prediction_market_matching as poll
    from app.tasks.live_blend_refresh import LiveBlendRefresher

    _forbid_inversion_fallback(monkeypatch)
    reading = lb.compute_source_home_probability(
        [_den_lac()], "LA Clippers", "Denver Nuggets",
    )
    arm = LiveBlendRefresher("kalshi")
    arm._inversion[15326747] = (time.monotonic() + 150, True)

    async def no_fallback():
        raise AssertionError("before_fallback reached")

    oriented = await arm._oriented(
        _NoFallbackSession(), 15326747, reading.home_probability,
        reading=reading, before_fallback=no_fallback,
    )
    assert oriented == pytest.approx(0.545)
    assert 15326747 not in arm._inversion
    assert await poll._orient_blend_reading(
        _NoFallbackSession(), 15326747, reading, "kalshi",
    ) == pytest.approx(0.545)


async def test_strawman_guards_on_the_linker_rule_let_the_cached_flip_invert_it(monkeypatch):
    """At ee8cd3ae20's guards the row is selected but unproven, and the same
    stale flip prints ``1 - 0.545`` as the Clippers' chance."""
    from app.tasks.live_blend_refresh import LiveBlendRefresher

    _guards_on_the_linker_rule(monkeypatch)
    reading = lb.compute_source_home_probability(
        [_den_lac()], "LA Clippers", "Denver Nuggets",
    )
    assert reading.outcome.id == 243704122
    assert reading.named_home_quote is False
    arm = LiveBlendRefresher("kalshi")
    arm._inversion[15326747] = (time.monotonic() + 150, True)
    oriented = await arm._oriented(
        _NoFallbackSession(), 15326747, reading.home_probability, reading=reading,
    )
    assert oriented == pytest.approx(0.455)


@pytest.mark.parametrize("lal, lac, home, away, expected", _SAME_CITY)
def test_same_city_proof_is_given_only_to_the_lakers_row_read_as_home(
    lal, lac, home, away, expected
):
    """``Los Angeles C`` reaches both clubs and is never a proven home quote.
    ``Los Angeles L`` is proven only when it is read as the home side."""
    reading = lb.compute_source_home_probability([_lal_lac(lal, lac)], home, away)
    assert reading.outcome.name == "Los Angeles L"
    assert reading.named_home_quote is (home == "Los Angeles Lakers")
