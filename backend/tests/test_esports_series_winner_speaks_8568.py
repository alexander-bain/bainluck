"""#8568 — an esports match winner titled "(BO3) - <tournament>" may speak.

THE DEFECT. Polymarket titles every esports match winner
`<Game>: A vs B (BOn) - <Tournament>`. The " - " after the series format read
as a trailing qualifier, so `classify_game_market_class` answered "other",
`admissible_as_blend_speaker` refused the market, and the match page said
"No price yet" while Polymarket priced it (specimen /events/15317527, Eternal
Fire vs WBT, market 62124243 at 79 / 21.5).

MEASURED over every Polymarket name carrying a "(BOn)" tag in the ten days to
2026-09-25 (1,741 rows): 1,717 move "other" → "moneyline" at the call site, 24
stay refused, and nothing moves the other way (the branch cannot fire on a name
without "(BOn) - "). The 24 are team names the recognizer's character class has
never read ("Pipsqueak+4", "KaBuM!", a U+2060 word-joiner before "Movistar"),
all unlinked — a separate question, left exactly as it was. Of the 54 LINKED
rows, exactly 27 become admissible — one match winner per event, 27 events,
each with the two team names as outcomes — and every linked container stays
refused.

What must stay refused, and is pinned below both directions:
  * the venue's map books, which do NOT wear the series format
    ("Counter-Strike: Eternal Fire vs WBT - Map 1 Winner");
  * a "(BOn) - " tail that names a derivative instead of a tournament;
  * the container sharing the winner's exact title, whose outcomes are book
    labels ("Map 1 Winner", "Match Winner", "Map Handicap …").
"""

import pytest

from app.utils import game_market_class
from app.utils.game_market_class import (
    classify_game_market_class,
    competition_prefix_tail,
    outcomes_refute_game_winner,
)
from app.utils.live_blend import (
    MarketOutcomes,
    admissible_as_blend_speaker,
    compute_source_home_probability,
)
from app.utils.prediction_market_matching import (
    _strip_category_prefix,
    extract_matchup_with_ticker_fallback,
)


class _Outcome:
    def __init__(self, name, prob=0.5, rank=None):
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = None
        self.current_yes_ask = None
        self.rank = rank


class _Market:
    def __init__(self, id, name, external_id=None):
        self.id = id
        self.source = "polymarket"
        self.external_id = external_id or f"0x{id:06x}"
        self.name = name
        self.market_metadata = None


def _at_call_site(name):
    """Classify the way `_class_says_game_winner` does (#5660's lesson)."""
    return classify_game_market_class(_strip_category_prefix(name), None)


SPECIMEN = (
    "Counter-Strike: Eternal Fire vs WBT (BO3) - "
    "Stake Ranked Episode 5: Closed Qualifier Playoffs"
)

# Real production titles, one per game family and tournament shape.
SERIES_WINNERS = [
    SPECIMEN,  # a colon INSIDE the tournament
    "Counter-Strike: BIG Academy vs Noir Verse (BO3) - CCT Europe Closed Qualifier: Series #10 Group D",
    "Rainbow Six Siege: Daystar vs Fury (BO1) - Asia Pacific League Asia - Stage 2 Group Stage",  # a dash inside it
    "LoL: FENNEL vs Cupid Esports (BO1) - World Star Challengers Invitational Group C",
    "Dota 2: Aurora Young Blood vs d06eg (BO3) - PGL Wallachia Group Stage",
    "Valorant: Team A vs Team B (BO3) - VCT Game Changers Pacific Playoffs",  # "Game" in the tournament
    "Mobile Legends Bang Bang: Geek Fam ID vs Dewa United Esports (BO3) - MPL Indonesia Regular Season",
    "Rocket League: Karmine Corp vs Falcons (BO7) - RLCS World Championship Playoffs",
    "Counter-Strike: Movistar KOI Fénix vs T1 Academy (BO1) - Swiss Round 3",  # a numbered ROUND is a whole match
]


class TestTheMatchWinnerNowSpeaks:
    @pytest.mark.parametrize("name", SERIES_WINNERS)
    def test_classifies_moneyline_at_the_call_site(self, name):
        assert _at_call_site(name) == "moneyline"

    def test_the_specimen_is_admitted_with_its_team_outcomes(self):
        market = _Market(62124243, SPECIMEN)
        outcomes = [_Outcome("Eternal Fire", 0.79, 0), _Outcome("WBT", 0.215, 1)]
        assert admissible_as_blend_speaker(market, is_primary=True, outcomes=outcomes)

    def test_the_writer_parses_the_same_title_it_admitted(self):
        """CERT-2751: admission the writer cannot act on is not a ship."""
        tail = competition_prefix_tail(SPECIMEN)
        assert tail == "Eternal Fire vs WBT (BO3)"
        matchup = extract_matchup_with_ticker_fallback(tail, external_id=None)
        assert (matchup.team_a, matchup.team_b) == ("Eternal Fire", "WBT")

    def test_the_group_publishes_the_venue_price_past_its_container(self):
        """The user-visible half: the page's number, from the real market.

        The container is the LOWER id (61976150 < 62124243 on production), so
        it is asked first and must be passed over, not published.
        """
        group = [
            MarketOutcomes(
                market=_Market(61976150, SPECIMEN),
                outcomes=[
                    _Outcome(n, 0.5, i)
                    for i, n in enumerate([
                        "Map 1 Winner",
                        "O/U 2.5 Games",
                        "Map Handicap: EF (-1.5) vs WBT (+1.5)",
                        "Match Winner",
                        "Map 2 Winner",
                    ])
                ],
            ),
            MarketOutcomes(
                market=_Market(62124243, SPECIMEN),
                outcomes=[_Outcome("Eternal Fire", 0.79, 0), _Outcome("WBT", 0.215, 1)],
            ),
        ]
        reading = compute_source_home_probability(group, "Eternal Fire", "WBT")
        assert reading is not None
        assert reading.market.id == 62124243
        assert reading.home_probability == pytest.approx(0.79, abs=0.02)

    def test_non_vacuity_the_series_branch_is_what_admits(self, monkeypatch):
        """Sever the new branch and the specimen goes back to "other"."""
        monkeypatch.setattr(game_market_class, "_without_series_tournament", lambda s: s)
        assert _at_call_site(SPECIMEN) == "other"


class TestDerivativesStayRefused:
    @pytest.mark.parametrize(
        "name",
        [
            # The venue's real map books: no series format before the dash.
            "Counter-Strike: Eternal Fire vs WBT - Map 1 Winner",
            "Counter-Strike: Eternal Fire vs WBT - Map 2 Winner",
            # A "(BOn) - " tail that names a derivative, not a tournament.
            "Counter-Strike: Eternal Fire vs WBT (BO3) - Map 1 Winner",
            "Counter-Strike: Eternal Fire vs WBT (BO3) - Map Handicap",
            "Counter-Strike: Eternal Fire vs WBT (BO3) - Total Maps Over 2.5",
            "Counter-Strike: Eternal Fire vs WBT (BO3) - 1st Half Winner",
        ],
    )
    def test_is_not_a_moneyline(self, name):
        assert _at_call_site(name) != "moneyline"

    @pytest.mark.parametrize(
        "tail",
        ["Map 1 Winner", "Map Handicap", "Total Maps Over 2.5", "1st Half Winner", "Match Winner"],
    )
    def test_the_tournament_test_itself_refuses_a_derivative_tail(self, tail):
        """Asked of the tail function directly, because the classifier's earlier
        branches (winner word, spread, total) refuse every name above before the
        new branch is reached — through `classify` alone this check is vacuous.
        The writer calls `competition_prefix_tail` unconditionally, so this is
        the door that decides what it parses."""
        assert competition_prefix_tail(f"Counter-Strike: Eternal Fire vs WBT (BO3) - {tail}") is None

    def test_dash_without_a_colon_is_left_as_it_was(self):
        """#5660's rule: a " - " with no prefix colon has no evidence behind it."""
        assert _at_call_site("Eternal Fire vs WBT (BO3) - PGL Wallachia Playoffs") == "other"

    @pytest.mark.parametrize(
        "outcomes",
        [
            ["Match Winner"],  # 62250327, a linked container with one book loaded
            ["Map 2 Winner", "Match Winner", "Map 1 Winner"],  # 62215103
            ["Map 1 Winner", "Match Winner", "Map 2 Winner"],  # 61975868
        ],
    )
    def test_a_container_wearing_the_winners_title_is_refuted(self, outcomes):
        """These three production rows were refuted by nothing before this ship;
        they were only silent because the title classed "other"."""
        assert outcomes_refute_game_winner(outcomes)
        market = _Market(1, SPECIMEN)
        assert not admissible_as_blend_speaker(
            market, is_primary=True, outcomes=[_Outcome(n) for n in outcomes]
        )

    @pytest.mark.parametrize(
        "outcomes",
        [["Eternal Fire", "WBT"], ["Map Makers", "Matchbox"], ["Team 1", "Team 2"]],
    )
    def test_team_names_are_never_refuted_by_the_new_labels(self, outcomes):
        assert not outcomes_refute_game_winner(outcomes)
