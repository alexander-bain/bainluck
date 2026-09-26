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
    _team_card_keyed,
    _team_card_lead_order_key,
    _team_card_lead_sport_keys,
)


def _row(name, sport_key, rank=0.1, aliases=()):
    """A team-window row: the columns `_team_card_keyed` builds the card from."""
    return SimpleNamespace(
        id=hash((name, sport_key)) % 10_000, name=name, slug=None,
        abbreviation=None, logo_url_small=None, current_record=None,
        alternate_names=list(aliases), sport_key=sport_key, team_rank=rank,
    )


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
        assert _team_card_lead_sport_keys(LAKERS, "lakers") == frozenset(
            {"basketball_nba", "basketball_nba_summer_league"}
        )

    def test_a_stronger_text_match_leads_over_the_marquee_club(self):
        """`mercyhurst lakers`: the college outranks LA on rank — rank first."""
        rows = [
            _row("Los Angeles Lakers", "basketball_nba", 0.1),
            _row("Mercyhurst Lakers", "americanfootball_ncaaf", 0.2),
            _row("Mercyhurst Lakers", "basketball_ncaab", 0.2),
        ]
        assert _team_card_lead_sport_keys(rows, "mercyhurst lakers") == frozenset(
            {"americanfootball_ncaaf", "basketball_ncaab"}
        )

    def test_two_marquee_clubs_share_the_lead(self):
        """`giants`: NFL and MLB both lead; the NPB namesake does not."""
        rows = [
            _row("New York Giants", "americanfootball_nfl"),
            _row("San Francisco Giants", "baseball_mlb"),
            _row("Yomiuri Giants", "baseball_npb"),
        ]
        assert _team_card_lead_sport_keys(rows, "giants") == frozenset(
            {"americanfootball_nfl", "baseball_mlb"}
        )

    def test_a_clubs_cup_competition_leads_with_its_league(self):
        """Man City's FA Cup row is non-marquee but the SAME club: it leads."""
        rows = [
            _row("Manchester City", "soccer_epl"),
            _row("Manchester City", "soccer_fa_cup"),
            _row("Manchester City FC Women", "soccer_fa_wsl", 0.05),
        ]
        assert _team_card_lead_sport_keys(rows, "manchester city") == frozenset(
            {"soccer_epl", "soccer_fa_cup"}
        )


class TestDisarmed:
    def test_no_rows(self):
        assert _team_card_lead_sport_keys([], "lakers") is None
        assert _team_card_lead_sport_keys(None, "lakers") is None

    def test_one_club_has_nothing_to_decide(self):
        assert _team_card_lead_sport_keys(
            [_row("Los Angeles Dodgers", "baseball_mlb")], "dodgers"
        ) is None

    def test_clubs_the_scorer_cannot_separate_share_the_lead(self):
        """`united`: two non-prominent clubs, same match class — no leader."""
        rows = [
            _row("Leeds United", "soccer_efl_champ"),
            _row("Dundee United", "soccer_spl"),
        ]
        assert _team_card_lead_sport_keys(rows, "united") is None

    def test_individual_sport_rows_are_not_the_card(self):
        """The card drops tennis/MMA 'teams'; so does its leader."""
        rows = [
            _row("Lakers", "tennis_atp_us_open", 0.9),
            _row("Växjö Lakers", "icehockey_sweden_hockey_league"),
        ]
        assert _team_card_lead_sport_keys(rows, "lakers") is None


def _college(i):
    return _row(f"College {i} Eagles", "americanfootball_ncaaf", 4.5, ["Eagles"])


# #8765: production's `eagles` window, 2026-09-26 — FULL (25 rows). Colleges
# repeat "Eagles" across name + aliases and outrank the Philadelphia Eagles on
# text rank; Hanwha (KBO) and Rakuten (NPB) are real clubs called Eagles.
EAGLES_WINDOW = [
    _row("American Eagles", "basketball_ncaab", 4.5,
         ["Eagles", "American", "American University Eagles"]),
    _row("Coppin St Eagles", "basketball_wncaab", 4.5,
         ["Eagles", "Coppin St", "Coppin State Eagles"]),
    _row("Morehead St Eagles", "baseball_ncaa", 4.5,
         ["Morehead State Eagles", "Eagles", "Morehead St"]),
    _row("Philadelphia Eagles", "americanfootball_nfl", 3.0, ["Eagles"]),
    _row("Hanwha Eagles", "baseball_kbo", 3.0, ["Eagles"]),
    _row("Tohoku Rakuten Golden Eagles", "baseball_npb", 3.0, ["Golden Eagles"]),
    *[_college(i) for i in range(19)],
]


class TestTheLeaderIsTheCards:
    """#8765: the games list follows the club the card SHOWS first."""

    def test_eagles_window_is_full(self):
        assert len(EAGLES_WINDOW) == _SEARCH_TEAM_WINDOW

    def test_the_card_leads_with_philadelphia(self):
        assert _team_card_keyed(EAGLES_WINDOW, "eagles")[0][1]["name"] == "Philadelphia Eagles"

    def test_a_full_window_follows_the_cards_leader(self):
        assert _team_card_lead_sport_keys(EAGLES_WINDOW, "eagles") == frozenset(
            {"americanfootball_nfl"}
        )

    def test_the_leader_is_the_card_leader_by_construction(self):
        """Every lead key is a sport of the card's first club, on every specimen."""
        for rows, q in [
            (LAKERS, "lakers"), (EAGLES_WINDOW, "eagles"),
            ([_row("Barcelona", "soccer_spain_la_liga"),
              _row("Barcelona SC", "soccer_ecuador_liga_pro")], "barcelona"),
        ]:
            keys = _team_card_lead_sport_keys(rows, q)
            lead = _team_card_keyed(rows, q)[0][1]["name"].lower()
            if keys is not None:
                assert all(
                    any(r.name.lower() == lead and r.sport_key == k for r in rows)
                    for k in keys
                ), (q, keys, lead)

    def test_strawman_the_rank_then_marquee_leader_is_the_colleges(self):
        """The rule this replaces: (text rank, marquee) leads with a college,
        which is what put Hanwha and NCAAF games over the Philadelphia Eagles."""
        first = ev._sort_matched_team_rows(list(EAGLES_WINDOW))[0]
        assert first.name != "Philadelphia Eagles"
        assert first.team_rank == 4.5


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
        key = self.SRC.index("_team_card_lead_sport_keys(_early_team_rows, _q_identity)")
        order = self.SRC.index("*( (_team_card_lead_key,) if _team_card_lead_key is not None else () ),")
        assert read < key < order

    def test_the_key_sits_under_status_and_over_the_tag_tier(self):
        start = self.SRC.index("_day_boost = _intent_day_order_key(_intent, now)")
        block = self.SRC[start:start + 1400]
        status = block.index("status_order,")
        key = block.index("(_team_card_lead_key,)")
        tag = block.index("tag_boost,")
        assert status < key < tag
