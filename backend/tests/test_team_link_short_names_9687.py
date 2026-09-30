"""#9687 — "USC", "LSU" and "VMI" on a Kalshi college board reach their school.

WHAT A READER SAW. LSU's, USC's, BYU's, SMU's, TCU's and UCF's team pages
carried none of Kalshi's college title, conference or playoff odds, and VMI and
LIU none of the FCS board's (CERT-3807). Kalshi names these schools by their
three-letter form, and the Phase 2 selector kept ``length(name) >= 4``, so no
step ever saw the leg.

The floor was a filter against generic words, and those still sit behind it:
a short name is now selected only on a Kalshi market, and only Step 0, the
ticker's own league, may bind it. Measured 2026-09-29 over the 62 open short
(series, name) pairs: every Step 0 answer is the school the ticker means ("USC"
is USC in all four college leagues, "A's" the Athletics); "AFC", "NFC", "ACC",
"SEC", "SZA" answer nothing. The category-wide, roster and LLM steps never read
a short name.

Team rows are production's shapes (``teams`` read 2026-09-29).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team

from tests.test_team_link_drain_advances_7307 import _make_engine
from tests.test_team_link_fcs_league_9663 import _drain, _links

SPORTS = [(2, "americanfootball_ncaaf")]
TEAMS = [
    (15331, 2, "USC Trojans", ["Trojans", "USC"]),
    (9, 2, "LSU Tigers", ["LSU", "Tigers"]),
    (15295, 2, "South Carolina Gamecocks", ["Gamecocks", "South Carolina"]),
    (17077, 2, "VMI Keydets", ["VMI", "Keydets"]),
]
# id, source, external_id
MARKETS = [
    (1, "kalshi", "KXNCAAF-27"),      # the FBS title board: league named
    (2, "kalshi", "KXZZZ-27"),        # a football series no map names
    (3, "polymarket", "600001"),      # not Kalshi
]


def _run(outcomes):
    with Session(_make_engine()) as session:
        session.add_all([Sport(id=i, key=k, name=k, active=True) for i, k in SPORTS])
        for i, s, n, a in TEAMS:
            session.add(Team(id=i, sport_id=s, name=n, alternate_names=a))
        for mid, source, ext in MARKETS:
            session.add(FuturesMarket(
                id=mid, source=source, external_id=ext, name=f"market {mid}",
                category="championship", llm_sport_category="football",
                status="open", market_tier=1,
            ))
        session.flush()
        for oid, mid, name in outcomes:
            session.add(FuturesOutcome(id=oid, market_id=mid, external_id=f"o{oid}", name=name))
        session.commit()
        stats = _drain(session, limit=2000)
        return stats, _links(session)


def test_a_kalshi_college_boards_short_names_reach_their_school():
    stats, links = _run([(1, 1, "USC"), (2, 1, "LSU"), (3, 1, "VMI"), (4, 1, "AFC")])
    assert stats["errors"] == []
    assert links == {1: 15331, 2: 9, 3: 17077, 4: None}
    assert stats["outcomes_linked_by_league"] == 3


def test_only_the_tickers_league_reads_a_short_name():
    # No league in the ticker: Step 0 has nothing to read, and the category-wide
    # matcher, which WOULD bind "USC" by alias, is never asked.
    stats, links = _run([(1, 2, "USC"), (2, 2, "USC Trojans")])
    assert stats["errors"] == []
    assert links == {1: None, 2: 15331}  # the long name still binds (control)


def test_a_short_name_off_kalshi_is_still_not_selected():
    # Nothing past Step 0 would bind it anyway; the selector keeps it out so a
    # batch is never spent on rows that cannot bind.
    from app.tasks.team_linking import unlinked_outcomes_query

    with Session(_make_engine()) as session:
        session.add_all([Sport(id=i, key=k, name=k, active=True) for i, k in SPORTS])
        for mid, source, ext in MARKETS:
            session.add(FuturesMarket(
                id=mid, source=source, external_id=ext, name=f"market {mid}",
                category="championship", llm_sport_category="football",
                status="open", market_tier=1,
            ))
        session.flush()
        for oid, mid, name in [(1, 3, "USC"), (2, 3, "USC Trojans"), (3, 1, "USC")]:
            session.add(FuturesOutcome(id=oid, market_id=mid, external_id=f"o{oid}", name=name))
        session.commit()
        query = unlinked_outcomes_query(open_markets=True, cursor=0, batch=100)
        selected = [o.id for o in session.execute(query).scalars().all()]
    assert selected == [2, 3]  # Polymarket's long name and Kalshi's short one
