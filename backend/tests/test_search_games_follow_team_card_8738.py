"""#8738 — the games list follows the TEAMS card's leader.

`lakers` on production 2026-09-25: the TEAMS card led with Los Angeles Lakers
(the marquee tie-break) and the GAMES list opened with Växjö Lakers v HV71 and
Western Kentucky v Mercyhurst Lakers, because every Lakers club ties on
`search_rank` and the games tie broke by kickoff.

The behaviour is proven on a real Postgres in
`tests/integration/test_search_recall_contract.py` (the leader's game leads, the
strawman without the key reproduces the defect, a namesake's game is sunk and
not dropped). This file pins the helper's contract and the wiring.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from app.routes import events as ev
from app.routes.events import (
    _SEARCH_TEAM_WINDOW,
    _team_card_lead_order_key,
    _team_card_lead_sport_keys,
)


def _row(name, sport_key, rank=0.1):
    return SimpleNamespace(name=name, sport_key=sport_key, team_rank=rank)


# Production's eight Lakers rows, 2026-09-25 (equal rank on "lakers").
LAKERS = [
    _row("Los Angeles Lakers", "basketball_nba"),
    _row("Mercyhurst Lakers", "basketball_ncaab"),
    _row("Växjö Lakers", "icehockey_sweden_hockey_league"),
    _row("Mercyhurst Lakers", "lacrosse_ncaa"),
    _row("ROOSEVELT Lakers", "baseball_ncaa"),
    _row("Mercyhurst Lakers", "baseball_ncaa"),
    _row("Los Angeles Lakers", "basketball_nba_summer_league"),
    _row("Mercyhurst Lakers", "americanfootball_ncaaf"),
]


def _sql(expr) -> str:
    return str(
        expr.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


class TestTheLeader:
    def test_lakers_leads_with_every_la_lakers_competition(self):
        assert _team_card_lead_sport_keys(LAKERS, _SEARCH_TEAM_WINDOW) == frozenset(
            {"basketball_nba", "basketball_nba_summer_league"}
        )

    def test_a_stronger_text_match_leads_over_the_marquee_club(self):
        """`mercyhurst lakers`: the college outranks LA on rank — rank first."""
        rows = [
            _row("Los Angeles Lakers", "basketball_nba", 0.1),
            _row("Mercyhurst Lakers", "americanfootball_ncaaf", 0.2),
            _row("Mercyhurst Lakers", "basketball_ncaab", 0.2),
        ]
        assert _team_card_lead_sport_keys(rows, _SEARCH_TEAM_WINDOW) == frozenset(
            {"americanfootball_ncaaf", "basketball_ncaab"}
        )

    def test_two_marquee_clubs_share_the_lead(self):
        """`giants`: NFL and MLB both lead; the NPB namesake does not."""
        rows = [
            _row("New York Giants", "americanfootball_nfl"),
            _row("San Francisco Giants", "baseball_mlb"),
            _row("Yomiuri Giants", "baseball_npb"),
        ]
        assert _team_card_lead_sport_keys(rows, _SEARCH_TEAM_WINDOW) == frozenset(
            {"americanfootball_nfl", "baseball_mlb"}
        )

    def test_a_clubs_cup_competition_leads_with_its_league(self):
        """Man City's FA Cup row is non-marquee but the SAME club: it leads."""
        rows = [
            _row("Manchester City", "soccer_epl"),
            _row("Manchester City", "soccer_fa_cup"),
            _row("Manchester City FC Women", "soccer_fa_wsl", 0.05),
        ]
        assert _team_card_lead_sport_keys(rows, _SEARCH_TEAM_WINDOW) == frozenset(
            {"soccer_epl", "soccer_fa_cup"}
        )


class TestDisarmed:
    def test_no_rows(self):
        assert _team_card_lead_sport_keys([], _SEARCH_TEAM_WINDOW) is None
        assert _team_card_lead_sport_keys(None, _SEARCH_TEAM_WINDOW) is None

    def test_a_full_window(self):
        rows = [_row(f"Club {i}", "soccer_epl" if i == 0 else "soccer_spl") for i in range(5)]
        assert _team_card_lead_sport_keys(rows, 5) is None
        assert _team_card_lead_sport_keys(rows, 6) == frozenset({"soccer_epl"})

    def test_one_club_has_nothing_to_decide(self):
        assert _team_card_lead_sport_keys(
            [_row("Los Angeles Dodgers", "baseball_mlb")], _SEARCH_TEAM_WINDOW
        ) is None

    def test_an_outright_tie_has_nothing_to_decide(self):
        """`barcelona`: two non-marquee clubs, equal rank — no leader to follow."""
        rows = [
            _row("Barcelona", "soccer_spain_la_liga"),
            _row("Barcelona SC", "soccer_ecuador_liga_pro"),
        ]
        assert _team_card_lead_sport_keys(rows, _SEARCH_TEAM_WINDOW) is None

    def test_individual_sport_rows_are_not_the_card(self):
        """The card drops tennis/MMA 'teams'; so does its leader."""
        rows = [
            _row("Lakers", "tennis_atp_us_open", 0.9),
            _row("Växjö Lakers", "icehockey_sweden_hockey_league"),
        ]
        assert _team_card_lead_sport_keys(rows, _SEARCH_TEAM_WINDOW) is None


class TestTheKey:
    def test_disarmed_adds_no_key(self):
        assert _team_card_lead_order_key(None) is None
        assert _team_card_lead_order_key(frozenset()) is None

    def test_it_is_a_key_not_a_filter(self):
        sql = _sql(_team_card_lead_order_key(frozenset({"basketball_nba"})))
        assert sql == "CASE WHEN (sports.key IN ('basketball_nba')) THEN 0 ELSE 1 END"


class TestTheHandlerWiring:
    SRC = inspect.getsource(ev.search_events)

    def test_the_leader_reads_the_early_team_rows(self):
        read = self.SRC.index("_early_team_rows = (await db.execute(_search_team_rows_q([]))).all()")
        key = self.SRC.index("_team_card_lead_sport_keys(_early_team_rows, _SEARCH_TEAM_WINDOW)")
        order = self.SRC.index("*( (_team_card_lead_key,) if _team_card_lead_key is not None else () ),")
        assert read < key < order

    def test_the_key_sits_under_status_and_over_the_tag_tier(self):
        start = self.SRC.index("_day_boost = _intent_day_order_key(_intent, now)")
        block = self.SRC[start:start + 1400]
        status = block.index("status_order,")
        key = block.index("(_team_card_lead_key,)")
        tag = block.index("tag_boost,")
        assert status < key < tag
