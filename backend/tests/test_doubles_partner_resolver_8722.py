"""#8722: a doubles moneyline resolves its sides when the venue writes full names.

Kalshi names every doubles side in full (``Casper Ruud / Alexander Zverev``) and
our event rows carry surnames (``Ruud / Zverev``). ``_fuzzy_team_match`` refused
every such pair, so 0 of 75 doubles events carried a Kalshi reading and live match
15319106 held Polymarket's 57% while Kalshi traded at 0.535.

The fixtures below are production rows (db-query 2026-09-26 20:04Z / 20:15Z).
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from app.utils import live_blend as lb
from app.utils.prediction_market_matching import (
    MatchupInfo,
    _doubles_pair_match,
    _fuzzy_team_match,
    _outcome_names_team,
    find_moneyline_outcome,
    find_three_way_partition,
)

NOW = datetime(2026, 9, 26, 20, 4, 33, tzinfo=timezone.utc)
HOME, AWAY = "Ruud / Zverev", "Bublik / Nakashima"


def _outcome(name: str, p: str, rank: int) -> NS:
    return NS(
        name=name, current_probability=Decimal(p), current_yes_bid=None,
        current_yes_ask=None, last_updated=NOW, rank=rank, id=rank,
        is_winner=None, result=None, status="active", market_status="active",
    )


def _specimen_entry(outcomes: list) -> lb.MarketOutcomes:
    market = NS(
        id=62418248, source="kalshi", name=f"{HOME} vs {AWAY}",
        external_id="KXLAVERCUPDOUBLESMATCH-26SEP26RUUZVEBUBNAK", status="open",
        market_type="game", market_metadata={}, llm_sport_category="tennis",
    )
    return lb.MarketOutcomes(
        market=market, outcomes=outcomes,
        event_commence_time=datetime(2026, 9, 26, 19, 30, tzinfo=timezone.utc),
        event_has_result=False,
    )


# ── the specimen, end to end through the blend writer's reader ─────────────


@pytest.mark.parametrize("order", ["home_first", "away_first"])
def test_specimen_15319106_reads_kalshis_home_price(order):
    outs = [
        _outcome("Casper Ruud / Alexander Zverev", "0.535", 1),
        _outcome("Alexander Bublik / Brandon Nakashima", "0.465", 2),
    ]
    if order == "away_first":
        outs.reverse()
    reading = lb.compute_source_home_probability([_specimen_entry(outs)], HOME, AWAY)
    assert reading is not None
    assert reading.home_probability == pytest.approx(0.535)
    assert reading.outcome.name == "Casper Ruud / Alexander Zverev"


def test_specimen_resolver_names_the_home_pair():
    outs = [
        _outcome("Alexander Bublik / Brandon Nakashima", "0.465", 2),
        _outcome("Casper Ruud / Alexander Zverev", "0.535", 1),
    ]
    matchup = MatchupInfo(HOME, AWAY, HOME, "bare_matchup")
    outcome, yes_is_home = find_moneyline_outcome(outs, matchup, HOME, AWAY)
    assert outcome.name == "Casper Ruud / Alexander Zverev"
    assert yes_is_home is True


def test_short_names_control_still_reads_the_same_price():
    outs = [_outcome(HOME, "0.535", 1), _outcome(AWAY, "0.465", 2)]
    reading = lb.compute_source_home_probability([_specimen_entry(outs)], HOME, AWAY)
    assert reading.home_probability == pytest.approx(0.535)


# ── name shapes our rows actually carry ────────────────────────────────────


@pytest.mark.parametrize(
    "market_side, event_side",
    [
        # WTA surname-first with hyphenated initials.
        ("Hao-Ching Chan / Fang-Hsien Wu", "Chan H-C / Wu F-H"),
        # Trailing single initials (15317818).
        ("Federico Agustin Gomez / Luis David Martinez", "Gomez F / Martinez L"),
        # Two-word surname, and an initial on only one partner (15317748, 15317749).
        ("Hans Hach Verdugo / Mitchell Krueger", "Hach Verdugo / Krueger"),
        ("Mac Kiger / John-Patrick Smith", "Kiger / Smith J-P"),
        # Four-word surname (15317707) and a venue disambiguator (15317742).
        ("Boris Arias / Arklon Huertas Del Pino Cordova", "Arias / Huertas Del Pino Cordova"),
        ("Miyu (1994) Kato / Ellen Perez", "Kato / Perez"),
        # Partners listed in the other order.
        ("Alexander Zverev / Casper Ruud", "Ruud / Zverev"),
        # Either side may be the short one.
        ("Ruud / Zverev", "Casper Ruud / Alexander Zverev"),
        # Accents fold.
        ("Sebastián Báez / Tomás Etcheverry", "Baez / Etcheverry"),
    ],
)
def test_pairs_that_name_the_same_two_players_match(market_side, event_side):
    assert _doubles_pair_match(market_side, event_side)
    assert _outcome_names_team(market_side, event_side)


# ── fail closed ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "market_side, event_side",
    [
        # Twins: one surname lands in BOTH venue partners (15318078).
        ("Ivan Sabanov / Matej Sabanov", "Sabanov / Sabanov"),
        ("Latisha Chan / Hao-Ching Chan", "Chan H-C / Chan Y-J"),
        # A surname found in both venue partners is ambiguous, even when the
        # other partner could only be one of them.
        ("Latisha Chan / Hao-Ching Chan Wu", "Chan / Wu"),
        # Both of our partners land on the SAME venue partner (not one-to-one).
        ("Casper Ruud / Alexander Zverev", "Ruud / Casper"),
        # Only one partner in common.
        ("Casper Ruud / Alexander Bublik", "Ruud / Zverev"),
        # The whole matchup is not a pair.
        ("Casper Ruud / Alexander Zverev vs Alexander Bublik / Brandon Nakashima", "Ruud / Zverev"),
        # A partner made only of initials identifies nobody.
        ("Casper Ruud / Alexander Zverev", "Ruud / A"),
        # Singles against a pair.
        ("Casper Ruud", "Ruud / Zverev"),
        # A surname must be a whole word, not a substring.
        ("Casper Ruudi / Alexander Zverevski", "Ruud / Zverev"),
    ],
)
def test_ambiguous_or_partial_pairs_are_refused(market_side, event_side):
    assert not _doubles_pair_match(market_side, event_side)


def test_shared_surname_across_teams_resolves_only_the_true_side():
    home, away = "Bryan / Smith", "Bryan / Jones"
    outs = [_outcome("Bob Bryan / Mike Jones", "0.40", 1), _outcome("Mike Bryan / Tom Smith", "0.60", 2)]
    assert _outcome_names_team("Bob Bryan / Mike Jones", away)
    assert not _outcome_names_team("Bob Bryan / Mike Jones", home)
    matchup = MatchupInfo(home, away, home, "bare_matchup")
    outcome, yes_is_home = find_moneyline_outcome(outs, matchup, home, away)
    assert (outcome.name, yes_is_home) == ("Mike Bryan / Tom Smith", True)


def test_an_outcome_that_names_both_pairs_still_names_neither():
    # #4629's guard runs on the widened side test: a name reaching both
    # sides is skipped, never given to the home side first.
    home, away = "Ruud / Zverev", "Zverev / Ruud"
    outs = [_outcome("Casper Ruud / Alexander Zverev", "0.535", 1)]
    matchup = MatchupInfo(home, away, home, "bare_matchup")
    assert find_moneyline_outcome(outs, matchup, home, away) is None


# ── scope: resolvers only, singles unchanged ───────────────────────────────


def test_the_linker_rule_itself_is_unchanged():
    # lane1 owns the linker; #8722 must not widen `_fuzzy_team_match`.
    assert not _fuzzy_team_match("Casper Ruud / Alexander Zverev", "Ruud / Zverev")


@pytest.mark.parametrize(
    "market_side, event_side",
    [
        ("Flavio Cobolli", "Cobolli"),
        ("Learner Tien", "Cobolli"),
        ("Boston Celtics", "Celtics"),
        ("LA", "Los Angeles Lakers"),
        ("Ohio St.", "Ohio Bobcats"),
        ("Draw (Spain vs. Portugal U20)", "Spain"),
        ("Arthur Gea", "Gea"),
    ],
)
def test_singles_and_team_names_answer_exactly_as_before(market_side, event_side):
    assert _outcome_names_team(market_side, event_side) == _fuzzy_team_match(
        market_side, event_side
    )


def test_three_way_partition_uses_the_same_side_test():
    home_o = _outcome("Casper Ruud / Alexander Zverev", "0.50", 1)
    away_o = _outcome("Alexander Bublik / Brandon Nakashima", "0.40", 2)
    tie_o = _outcome("Tie", "0.10", 3)
    result = find_three_way_partition([home_o, away_o, tie_o], home_o, HOME, AWAY)
    assert result == (away_o, tie_o)
