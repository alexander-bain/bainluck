"""#10067 — a club's name reaches its league's title board: soccer legs get a club.

WHAT A READER SAW. Searching ``manchester united`` or ``chelsea`` never put the
Premier League title board (31834301) on the page; ``arsenal`` and ``manchester
city`` did. Search admits a contender priced under 5% only through a team_id
whose team agrees with the query (#6430), and no open soccer leg on a tier-1
board carried one (0 of ~1,800 on 2026-10-01): the Phase 2 selector was scoped
to the four US sports, and Kalshi's ``KXPREMIERLEAGUE`` series named no league.

The bind is league-scoped by construction. Soccer is read by Step 0 alone — the
league the ticker names — never by the category-wide, roster or LLM steps (a
club name is a team row in a dozen soccer sport keys, the #2593 hazard), never
inside ``soccer_other`` (a catch-all, not a league), and only on open, tier-1,
non-event boards.

Team rows are production's shapes (``teams`` read 2026-10-01), duplicates
included: four Brighton rows, "Tottenham" beside "Tottenham Hotspur".
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team
from app.utils.market_team_sport import market_league_sport_key
from app.utils.team_linking import match_outcome_to_league_team, match_outcome_to_one_club

from tests.test_team_link_drain_advances_7307 import _make_engine
from tests.test_team_link_fcs_league_9663 import _drain, _links

SPORTS = [(1, "soccer_epl"), (2, "soccer_fa_cup"), (3, "soccer_other")]
TEAMS = [
    (133, 1, "Arsenal", None),
    (142, 1, "Chelsea", None),
    (145, 1, "Manchester United", ["Man United"]),
    (188, 1, "Manchester City", ["Man City"]),
    (137, 1, "Bournemouth", ["AFC Bournemouth"]),
    (14203, 1, "AFC Bournemouth", ["Bournemouth"]),
    (146, 1, "Tottenham Hotspur", ["Spurs"]),
    (14545, 1, "Tottenham", ["Tottenham Hotspur", "Spurs"]),
    (1876, 1, "Brighton and Hove Albion", ["Brighton", "Seagulls", "Brighton & Hove Albion"]),
    (14419, 1, "Brighton", ["Brighton & Hove Albion"]),
    (14748, 1, "Brighton & Hove Albion", ["Brighton"]),
    (19931, 1, "Brighton & Hove Albion FC", ["Brighton", "Brighton & Hove Albion"]),
    # The same clubs' rows under another soccer key.
    (90133, 2, "Arsenal", None),
    (90142, 2, "Chelsea", None),
    (4770, 3, "Sparta Lichtenberg", None),
]
# id, external_id, tier, event_id, status
MARKETS = [
    (1, "KXPREMIERLEAGUE-27", 1, None, "open"),   # the EPL title board
    (2, "KXFACUP-27", 1, None, "open"),           # a soccer series no map names
    (3, "KXEREDIVISIE-27", 1, None, "open"),      # mapped to soccer_other
    (4, "KXEPLTOP-27", 5, None, "open"),          # a tier-5 board
    (5, "KXPREMIERLEAGUE-26", 1, None, "closed"),  # a resolved board
]

EPL_BOARD = [
    (1, "Arsenal"), (2, "Chelsea"), (3, "Manchester United"), (4, "Manchester City"),
    (5, "Bournemouth"), (6, "Tottenham"), (7, "Brighton"),
]


def _seed(session, outcomes, markets=MARKETS):
    session.add_all([Sport(id=i, key=k, name=k, active=True) for i, k in SPORTS])
    for i, s, n, a in TEAMS:
        session.add(Team(id=i, sport_id=s, name=n, alternate_names=a))
    for mid, ext, tier, event_id, status in markets:
        session.add(FuturesMarket(
            id=mid, source="kalshi", external_id=ext, name=f"market {mid}",
            category="championship", llm_sport_category="soccer",
            status=status, market_tier=tier, event_id=event_id,
        ))
    session.flush()
    for oid, mid, name in outcomes:
        session.add(FuturesOutcome(id=oid, market_id=mid, external_id=f"o{oid}", name=name))
    session.commit()


def _run(outcomes):
    with Session(_make_engine()) as session:
        _seed(session, outcomes)
        stats = _drain(session, limit=2000)
        return stats, _links(session)


def test_the_epl_title_series_names_the_epl():
    assert market_league_sport_key("kalshi", "KXPREMIERLEAGUE-27") == "soccer_epl"


def test_every_club_on_the_epl_title_board_reaches_its_epl_row():
    stats, links = _run([(oid, 1, name) for oid, name in EPL_BOARD])
    assert stats["errors"] == []
    assert links == {
        1: 133, 2: 142, 3: 145, 4: 188,
        # Duplicate rows of one club resolve to the row carrying its games.
        5: 137, 6: 146, 7: 1876,
    }
    assert stats["outcomes_linked_by_league"] == 7


def test_a_soccer_leg_with_no_ticker_league_is_never_bound_by_name():
    # "Chelsea" names exactly one EPL row, and the category-wide matcher would
    # take it; the FA Cup board's ticker names no league, so nothing may decide.
    stats, links = _run([(1, 2, "Chelsea"), (2, 2, "Arsenal")])
    assert stats["errors"] == []
    assert links == {1: None, 2: None}


def test_soccer_other_is_not_a_league_to_bind_inside():
    stats, links = _run([(1, 3, "Sparta")])
    assert stats["errors"] == []
    assert links == {1: None}


def test_only_open_tier_one_non_event_soccer_boards_are_selected():
    from app.tasks.team_linking import unlinked_outcomes_query

    markets = MARKETS + [(6, "KXPREMIERLEAGUE-27X", 1, 777, "open")]  # event-linked
    with Session(_make_engine()) as session:
        _seed(
            session,
            [(1, 1, "Chelsea"), (2, 4, "Chelsea"), (3, 5, "Chelsea"), (4, 6, "Chelsea")],
            markets=markets,
        )
        open_ids = [
            o.id for o in session.execute(
                unlinked_outcomes_query(open_markets=True, cursor=0, batch=100)
            ).scalars().all()
        ]
        resolved_ids = [
            o.id for o in session.execute(
                unlinked_outcomes_query(open_markets=False, cursor=0, batch=100)
            ).scalars().all()
        ]
    assert open_ids == [1]
    assert resolved_ids == []


# ── the one-club read, as a unit ─────────────────────────────────────────────
def _teams(rows):
    return [
        {"id": i, "name": n, "alternate_names": a or [], "sport_key": "x"} for i, n, a in rows
    ]


def test_duplicate_rows_of_one_club_are_ambiguous_to_the_league_matcher():
    # The precondition: without the one-club read these legs bind nothing.
    epl = _teams([(i, n, a) for i, s, n, a in TEAMS if s == 1])
    assert match_outcome_to_league_team("Brighton", epl) is None
    assert match_outcome_to_league_team("Tottenham", epl) is None
    assert match_outcome_to_one_club("Brighton", epl) == 1876
    assert match_outcome_to_one_club("Tottenham", epl) == 146


def test_two_clubs_sharing_a_word_are_not_one_club():
    teams = _teams([
        (1, "New York Knicks", ["New York", "Knicks"]),
        (2, "New York Liberty", ["New York"]),
    ])
    assert match_outcome_to_one_club("New York", teams) is None


def test_a_shortened_row_nobody_claims_is_not_the_same_club():
    # "Manchester" touches two clubs, neither listing the other.
    epl = _teams([(i, n, a) for i, s, n, a in TEAMS if s == 1])
    assert match_outcome_to_one_club("Manchester", epl) is None
    # ...and a name no row answers to binds nothing, however it is shortened.
    assert match_outcome_to_one_club("Hotspur", epl) is None
