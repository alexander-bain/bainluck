"""#10523: a Kalshi doubles market titled in full names speaks for its surname-pair row.

**SHIP: a doubles match Polymarket stored as ``Balaji/King`` @ ``Arends/Johnson`` carries
Kalshi's price in its blend, instead of a game page holding one venue where two quote it.**
(Pillar: MATCHING.)

Kalshi titles some doubles with full names, ``N. Sriram Balaji / Evan King vs Sander
Arends / Luke Johnson``, and the row for the match is Polymarket's ``Balaji/King`` @
``Arends/Johnson``. ``match_teams_to_event`` asks ``_fuzzy_team_match`` whether the title's
first pair is one of the row's sides; it is not, so the mapping is None, and
``find_moneyline_outcome`` returned None before it looked at the legs. Each leg names
exactly one of the row's sides by ``_outcome_names_team``, which reads a pair.

Fixtures are production rows (read-only SQL, Nov 8): titles, tickers, leg names, leg ranks
and the rows' team names, verbatim. The four markets have since resolved; they are served
here as open, with fixture prices chosen so the home leg (0.42), the away leg (0.61) and an
inverted reading (1 - 0.61 = 0.39) are three different numbers.

Replayed offline over every market linked to a game in a 4-day window (Nov 8): of 2,075
Kalshi markets, exactly these four go from no reading to a reading; of 52,769 Polymarket
markets with two or three team-named legs, none changes; no existing reading changes.

WHAT EACH TEST DEFENDS:

* the ship: the four specimens speak, end to end through the blend writer's reader, with
  the HOME pair's own price, in either leg order;
* the cause: the title cannot orient these, so the specimens exercise the new arm;
* 🔴 a market sharing ONE pair with the row still says nothing, either side;
* 🔴 a lone leg says nothing (the Polymarket history backfill asks one leg at a time);
* the title path is unchanged when the title maps (Heliovaara / Patten).
"""

from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from app.utils import live_blend as lb
from app.utils.prediction_market_matching import (
    find_moneyline_outcome,
    match_teams_to_event,
)

HOME_PRICE = "0.42"
AWAY_PRICE = "0.61"

#: (market id, ticker, title, row home, row away, home leg, away leg, home leg's rank)
SPECIMENS = [
    (
        69590222, "KXATPDOUBLES-26NOV08BALKINAREJOH",
        "N. Sriram Balaji / Evan King vs Sander Arends / Luke Johnson",
        "Balaji/King", "Arends/Johnson",
        "N. Sriram Balaji / Evan King", "Sander Arends / Luke Johnson", 2,
    ),
    (
        69590243, "KXWTADOUBLES-26NOV08KARWALADKBHO",
        "Naima Karamoko / Simona Waltert vs Vaishnavi Adkar / Rutuja Bhosale",
        "Karamoko/Waltert", "Adkar/Bhosale",
        "Naima Karamoko / Simona Waltert", "Vaishnavi Adkar / Rutuja Bhosale", 1,
    ),
    (
        69590221, "KXATPDOUBLES-26NOV08HALHERHARSKU",
        "Quentin Halys / Pierre-Hugues Herbert vs Christian Harrison / Neal Skupski",
        "Halys/Herbert", "Harrison/Skupski",
        "Quentin Halys / Pierre-Hugues Herbert", "Christian Harrison / Neal Skupski", 1,
    ),
    (
        69405377, "KXWTADOUBLES-26NOV07KARWALHAVUDV",
        "Naima Karamoko / Simona Waltert vs Isabelle Haverlag / Panna Udvardy",
        "Karamoko/Waltert", "Haverlag/Udvardy",
        "Naima Karamoko / Simona Waltert", "Isabelle Haverlag / Panna Udvardy", 1,
    ),
]
IDS = [s[3] + " v " + s[4] for s in SPECIMENS]


def _outcome(name: str, p: str, rank: int) -> NS:
    return NS(
        name=name, current_probability=Decimal(p), current_yes_bid=None,
        current_yes_ask=None, rank=rank, id=rank, is_winner=None, result=None,
        status="active", market_status="active",
    )


def _entry(market_id: int, ticker: str, title: str, outcomes: list) -> lb.MarketOutcomes:
    market = NS(
        id=market_id, source="kalshi", name=title, external_id=ticker,
        status="open", market_type="duel", category="championship",
        market_metadata={}, llm_sport_category="tennis",
    )
    # The kickoff and result clauses judge a LIVE book and are not under test here;
    # None makes them abstain, as for `event_chart_backfill`.
    return lb.MarketOutcomes(
        market=market, outcomes=outcomes, event_commence_time=None, event_has_result=False,
    )


def _specimen(spec, order: str = "stored") -> tuple[lb.MarketOutcomes, str, str, str]:
    market_id, ticker, title, home, away, home_leg, away_leg, home_rank = spec
    outs = [
        _outcome(home_leg, HOME_PRICE, home_rank),
        _outcome(away_leg, AWAY_PRICE, 3 - home_rank),
    ]
    if order == "swapped":
        for o in outs:
            o.rank = 3 - o.rank
            o.id = o.rank
    return _entry(market_id, ticker, title, outs), home, away, home_leg


# ── the ship, end to end through the blend writer's reader ─────────────────


@pytest.mark.parametrize("order", ["stored", "swapped"])
@pytest.mark.parametrize("spec", SPECIMENS, ids=IDS)
def test_specimen_speaks_with_the_home_pairs_own_price(spec, order):
    entry, home, away, home_leg = _specimen(spec, order)
    reading = lb.compute_source_home_probability([entry], home, away)
    assert reading is not None
    assert reading.home_probability == pytest.approx(float(HOME_PRICE))
    assert reading.outcome.name == home_leg


@pytest.mark.parametrize("spec", SPECIMENS, ids=IDS)
def test_specimen_resolves_the_home_leg_as_home(spec):
    entry, home, away, home_leg = _specimen(spec)
    matchup = lb._matchup_for_entry(entry)
    outcome, yes_is_home = find_moneyline_outcome(entry.outcomes, matchup, home, away)
    assert (outcome.name, yes_is_home) == (home_leg, True)


@pytest.mark.parametrize("spec", SPECIMENS, ids=IDS)
def test_the_title_alone_cannot_orient_the_specimens(spec):
    """Proves the specimens reach the legs arm, not the title mapping."""
    entry, home, away, _ = _specimen(spec)
    matchup = lb._matchup_for_entry(entry)
    assert matchup is not None
    assert match_teams_to_event(matchup, home, away) is None


# ── refusals: the legs must name BOTH of the row's sides ───────────────────


@pytest.mark.parametrize(
    "title, legs",
    [
        # Constructed: the row's home pair against a pair that is not on the row.
        (
            "N. Sriram Balaji / Evan King vs Hugo Nys / Edouard Roger-Vasselin",
            ["N. Sriram Balaji / Evan King", "Hugo Nys / Edouard Roger-Vasselin"],
        ),
        # Constructed: the row's away pair against a pair that is not on the row.
        (
            "Sander Arends / Luke Johnson vs Hugo Nys / Edouard Roger-Vasselin",
            ["Sander Arends / Luke Johnson", "Hugo Nys / Edouard Roger-Vasselin"],
        ),
        # Neither pair is on the row.
        (
            "Hugo Nys / Edouard Roger-Vasselin vs Kevin Krawietz / Tim Puetz",
            ["Hugo Nys / Edouard Roger-Vasselin", "Kevin Krawietz / Tim Puetz"],
        ),
    ],
    ids=["home-pair-only", "away-pair-only", "neither"],
)
def test_a_market_sharing_at_most_one_pair_still_says_nothing(title, legs):
    outs = [_outcome(legs[0], HOME_PRICE, 1), _outcome(legs[1], AWAY_PRICE, 2)]
    entry = _entry(1, "KXATPDOUBLES-26NOV08BALKINNYSROG", title, outs)
    matchup = lb._matchup_for_entry(entry)
    assert find_moneyline_outcome(outs, matchup, "Balaji/King", "Arends/Johnson") is None
    assert lb.compute_source_home_probability([entry], "Balaji/King", "Arends/Johnson") is None


@pytest.mark.parametrize("leg", ["home", "away"])
def test_a_lone_leg_does_not_orient_an_unreadable_title(leg):
    """The Polymarket history backfill re-asks the resolver one leg at a time to
    decide whether a side was NAMED; one leg can never show both sides."""
    entry, home, away, _ = _specimen(SPECIMENS[0])
    lone = [o for o in entry.outcomes if (o.name == SPECIMENS[0][5]) == (leg == "home")]
    assert len(lone) == 1
    matchup = lb._matchup_for_entry(entry)
    assert find_moneyline_outcome(lone, matchup, home, away) is None


# ── control: a title that maps reads exactly as before ─────────────────────


def test_control_a_mapped_title_reads_as_before():
    """Production market 69241319 on row 15342921, which held a Kalshi snapshot."""
    outs = [
        _outcome("Harri Heliovaara / Henry Patten", "0.62", 1),
        _outcome("Benjamin Bonzi / Arthur Rinderknech", "0.38", 2),
    ]
    entry = _entry(
        69241319, "KXATPDOUBLES-26NOV06HELPATBONRIN",
        "Heliovaara / Patten vs Bonzi / Rinderknech", outs,
    )
    home, away = "Heliovaara / Patten", "Bonzi / Rinderknech"
    matchup = lb._matchup_for_entry(entry)
    assert match_teams_to_event(matchup, home, away) == {
        "yes_is_home": True, "matched_team": "Heliovaara / Patten",
    }
    reading = lb.compute_source_home_probability([entry], home, away)
    assert reading is not None
    assert reading.home_probability == pytest.approx(0.62)
    assert reading.outcome.name == "Harri Heliovaara / Henry Patten"
