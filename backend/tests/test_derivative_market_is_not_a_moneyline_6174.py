"""#6174 — a *Both Teams to Score* row stops printing "<Away team> Win".

`/api/events/{id}/related-futures` served, for market 60973751 on event 15312165
(CD Tenerife vs Cádiz CF, 2026-09-26):

    outcome_name = 'Cádiz CF Win'   market_name = '... : Both Teams to Score'

while the row stored in `futures_outcomes` is plainly named `No`. The label was
fabricated by the server, and it contradicted the market's own heading one line
above it on the page: a reader saw "Cádiz CF Win 50%" under BOTH TEAMS TO SCORE.

The cause is the matchup pattern's terminator. It read

    ^(.+?)\\s+(?:vs\\.?|at|@)\\s+(.+?)(?:\\s*[-:]|$)

so on "<A> vs. <B>: Both Teams to Score" the colon closed team 2 and the
derivative's subject was discarded — the single token proving the market is NOT
a moneyline is what ended the parse. Measured over every Yes/No market attached
to an event kicking off within 7 days: 302 rows took the relabel, and 223 of them
were derivatives (Both Teams to Score 68, Overtime 67, BTTS 50, BTTS First Half
21, …). Only 79 were real moneylines.

The same character class truncated team names: no market in that population uses
" - " as a separator, but "SaiPa Lappeenranta vs. Kiekko-Espoo" is a real
moneyline whose second team contains a hyphen, and it was served as "Kiekko Win".

So the terminator carried both defects, and the fix is one pattern: the name must
be the whole matchup, with no colon on either side.
"""

import pytest

from app.routes.events import resolve_binary_matchup_outcome_name as resolve


# (market_name, expected Yes label, expected No label)
MONEYLINES = [
    ("Celtics vs. 76ers", "Celtics Win", "76ers Win"),
    ("Denver vs Kansas City", "Denver Win", "Kansas City Win"),
    ("Arsenal at Chelsea", "Arsenal Win", "Chelsea Win"),
    ("Team A @ Team B", "Team A Win", "Team B Win"),
    # the hyphen repair — a real moneyline whose team name contains "-"
    (
        "SaiPa Lappeenranta vs. Kiekko-Espoo",
        "SaiPa Lappeenranta Win",
        "Kiekko-Espoo Win",
    ),
    # A COLON IN THE PREFIX IS A CARD, NOT A DERIVATIVE.
    # The first cut of this fix banned colons on both sides and broke this — it is
    # a real fight, and CI caught it (test_dark_polymarket_selector_real_postgres,
    # "the venue's price is on the page"). Position is the whole distinction:
    # "<card>: A vs. B" is a moneyline, "A vs. B: <subject>" is not.
    (
        "UFC 331: Ozzy Diaz vs. Ryan Gandra (Middleweight, Early Prelims)",
        "UFC 331: Ozzy Diaz Win",
        "Ryan Gandra (Middleweight, Early Prelims) Win",
    ),
    ("Premier League: Arsenal vs. Chelsea", "Premier League: Arsenal Win", "Chelsea Win"),
]

# Derivative markets: these share the matchup prefix but are NOT the moneyline.
# Every string here is a real production market name from the measured population.
DERIVATIVES = [
    "CD Tenerife vs. Cádiz CF: Both Teams to Score",
    "ACF Fiorentina vs. SSC Napoli: Both Teams to Score",
    "AFC Bournemouth vs. Liverpool FC: Both Teams to Score",
    "Akron vs Minnesota: Overtime",
    "Al Ahli Saudi vs Pakhtakor: BTTS",
    "Al Ain FC vs. Al Nassr Club: Both Teams to Score in First Half",
    "Denver vs Kansas City: D/ST Touchdown",
    "Denver vs Kansas City: Safety",
]


@pytest.mark.parametrize("market_name,yes_label,no_label", MONEYLINES)
def test_a_moneyline_still_names_the_team(market_name, yes_label, no_label):
    """The relabel this code exists for keeps working — both sides."""
    assert resolve("Yes", market_name) == yes_label
    assert resolve("No", market_name) == no_label


@pytest.mark.parametrize("market_name", DERIVATIVES)
def test_a_derivative_keeps_its_truthful_yes_no(market_name):
    """A derivative is never relabelled as a team winning.

    This is the defect itself: the assertion is that the served string is the
    stored one. "Yes"/"No" reads correctly under the market's own heading.
    """
    assert resolve("Yes", market_name) == "Yes"
    assert resolve("No", market_name) == "No"


@pytest.mark.parametrize("market_name", DERIVATIVES)
def test_no_derivative_is_ever_served_as_a_win(market_name):
    """The reader-facing form of the bug, stated directly.

    Guards the class rather than the strings: whatever the pattern does next, a
    market naming a derivative subject must not produce a "… Win" label.
    """
    for outcome_name in ("Yes", "No"):
        assert not resolve(outcome_name, market_name).endswith(" Win")


def test_the_production_specimen():
    """Event 15312165 / market 60973751 — the row that was caught on the page."""
    name = "CD Tenerife vs. Cádiz CF: Both Teams to Score"
    assert resolve("No", name) == "No", "served 'Cádiz CF Win' before #6174"
    assert resolve("Yes", name) == "Yes", "served 'CD Tenerife Win' before #6174"


def test_a_competition_prefix_whose_tail_is_the_matchup_picks_the_right_side():
    """Two real cricket names where the colon separates series from fixture.

    These are not derivatives — the text after the colon IS the matchup — and the
    old pattern read the sides off the SERIES title instead, so it named the wrong
    team. "T20 India vs Afghanistan: Afghanistan vs India" parsed as
    "T20 India" vs "Afghanistan" and served "Afghanistan Win" for No; the fixture
    says No is India. Allowing a colon in the prefix fixes the side as a
    by-product, which is why these are pinned rather than left to drift.
    """
    assert resolve("No", "T20 India vs Afghanistan: Afghanistan vs India") == "India Win"
    assert (
        resolve(
            "No", "T20 Series Zimbabwe vs South Africa, Women: Zimbabwe vs South Africa"
        )
        == "South Africa Win"
    ), "old pattern said 'South Africa, Women Win' — it took the side from the series"


def test_non_binary_outcomes_are_untouched():
    """Only Yes/No are resolved; a named outcome passes through unchanged."""
    assert resolve("Cádiz CF", "CD Tenerife vs. Cádiz CF") == "Cádiz CF"
    assert resolve("Over 2.5", "CD Tenerife vs. Cádiz CF") == "Over 2.5"


def test_a_market_with_no_matchup_keeps_yes_no():
    """No parseable matchup ⇒ nothing to name the side after."""
    assert resolve("Yes", "Will it rain in Boston?") == "Yes"
    assert resolve("No", "") == "No"
    assert resolve("Yes", "Both Teams to Score") == "Yes"
