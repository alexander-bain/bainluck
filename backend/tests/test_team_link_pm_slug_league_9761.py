"""#9761, Polymarket half — a ``pro-football-`` event slug names the NFL, so a pro leg leaves the college.

WHAT A READER SAW. The LSU Tigers' page listed "Mansoor Delane — Pro Football:
2026-27 AP Defensive Rookie 5%"; Notre Dame's listed Jeremiyah Love's four NFL
props, Jadarian Price's and DeVonta Smith's (2026-09-30). Those are NFL questions
about players who left for the NFL.

WHY. A Polymarket market's id is a bare number (``741436``), so
``market_league_sport_key`` answered None and the league checks (#5119 Phase 3,
#9617 Step 0, the bind-site refusal, the team page's own refusal) never saw the
NFL. The venue does say so, in its own structure: the Gamma event slug
``pro-football-2026-27-ap-defensive-rookie-of-the-year-winner`` (notice 40).
Measured on production 2026-09-30: 522 open legs sit on ``pro-football-`` slugs,
515 on NFL clubs and exactly these 7 on college teams. The draft board
(``2027-pro-football-draft-1st-overall-pick``) is about college players and is
not claimed by the prefix.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team
from app.routes import teams as teams_route
from app.utils.market_team_sport import (
    link_crosses_league,
    market_event_slug,
    market_league_sport_key,
)

from tests.test_team_link_drain_advances_7307 import _make_engine
from tests.test_team_link_fcs_league_9663 import _drain, _links
from tests.test_team_path_cross_league_2593 import _ids, _outcome, _path


DROY_SLUG = "pro-football-2026-27-ap-defensive-rookie-of-the-year-winner"
OROY_SLUG = "pro-football-2026-27-ap-offensive-rookie-of-the-year-winner"
DRAFT_SLUG = "2027-pro-football-draft-1st-overall-pick"
NCAAF_SLUG = "ncaa-football-2026-national-champion"


def test_a_pro_football_slug_names_the_nfl():
    assert market_league_sport_key("polymarket", "741436", DROY_SLUG) == "americanfootball_nfl"
    # The team page's own refusal reads the same answer.
    assert link_crosses_league("polymarket", "741436", "americanfootball_ncaaf", DROY_SLUG)
    assert not link_crosses_league("polymarket", "741436", "americanfootball_nfl", DROY_SLUG)


def test_no_slug_a_draft_slug_or_a_college_slug_is_no_claim():
    for slug in (None, "", DRAFT_SLUG, NCAAF_SLUG, "new-pro-football-cba-agreed-before-the-2027"):
        assert market_league_sport_key("polymarket", "448882", slug) is None, slug
        assert not link_crosses_league("polymarket", "448882", "americanfootball_ncaaf", slug)


def test_the_slug_speaks_only_for_polymarket():
    """A Kalshi ticker keeps its own read; a slug handed with it changes nothing."""
    assert market_league_sport_key("kalshi", "KXNCAAF-27", DROY_SLUG) == "americanfootball_ncaaf"
    assert market_league_sport_key("odds_api", "x", DROY_SLUG) is None


def test_the_slug_is_read_off_the_metadata_or_not_at_all():
    assert market_event_slug({"polymarket_event_slug": DROY_SLUG}) == DROY_SLUG
    for meta in (None, {}, [], "pro-football-x", {"polymarket_event_slug": 7}):
        assert market_event_slug(meta) is None, meta


# ── The drain: Phase 3 moves the stored links, Phase 2 cannot put them back ───
SPORTS = [(1, "americanfootball_nfl"), (2, "americanfootball_ncaaf")]

# id, sport_id, name, alternate_names, roster (last season's college rosters)
LSU = (9, 2, "LSU Tigers", ["LSU", "Tigers"], [{"name": "Mansoor Delane"}])
NOTRE_DAME = (835, 2, "Notre Dame Fighting Irish", ["Notre Dame", "Fighting Irish"],
              [{"name": "Jeremiyah Love"}, {"name": "CJ Carr"}])
BULLS = (400, 2, "Buffalo Bulls", ["Bulls", "Buffalo"], None)
BILLS = (401, 1, "Buffalo Bills", ["Bills", "Buffalo"], None)
CHIEFS = (402, 1, "Kansas City Chiefs", ["Chiefs", "Kansas City"], None)

# id, external_id, name, slug
MARKETS = [
    (1, "741436", "Pro Football: 2026-27 AP Defensive Rookie of the Year Winner", DROY_SLUG),
    (2, "741437", "Pro Football: 2026-27 AP Offensive Rookie of the Year Winner", OROY_SLUG),
    (3, "448882", "2027 Pro Football Draft: 1st Overall Pick", DRAFT_SLUG),
    (4, "357914", "NCAA Football: 2027 National Champion", NCAAF_SLUG),
    (5, "700001", "Pro Football: 2026-27 Highest Scoring Team", "pro-football-2026-27-highest-scoring-team"),
    (6, "700002", "Pro Football: 2026-27 Top Rookie", "pro-football-2026-27-top-rookie"),
]

# id, market_id, name, stored team_id
OUTCOMES = [
    (211383725, 1, "Mansoor Delane", LSU[0]),         # production's link -> NULL
    (211453881, 2, "Jeremiyah Love", NOTRE_DAME[0]),  # production's link -> NULL
    (95106402, 3, "CJ Carr", NOTRE_DAME[0]),          # draft board: stands
    (55309451, 4, "LSU Tigers", LSU[0]),              # college title: stands
    (5, 5, "Buffalo", BULLS[0]),                      # -> the Bills
    (6, 6, "Mansoor Delane", None),                   # unlinked: LSU's roster must not take it
    (7, 5, "Kansas City", None),                      # unlinked: Step 0 binds the Chiefs
]


def _seed(session: Session) -> None:
    session.add_all([Sport(id=i, key=k, name=k, active=True) for i, k in SPORTS])
    for tid, sid, name, aliases, roster in (LSU, NOTRE_DAME, BULLS, BILLS, CHIEFS):
        session.add(Team(id=tid, sport_id=sid, name=name, alternate_names=aliases,
                         roster_players=roster))
    for mid, ext, name, slug in MARKETS:
        session.add(FuturesMarket(
            id=mid, source="polymarket", external_id=ext, name=name,
            category="championship", llm_sport_category="football",
            status="open", market_tier=5,
            market_metadata={"polymarket_event_slug": slug, "polymarket_event_id": ext},
        ))
    session.flush()
    for oid, mid, name, team_id in OUTCOMES:
        session.add(FuturesOutcome(
            id=oid, market_id=mid, external_id=f"o{oid}", name=name, team_id=team_id,
        ))
    session.commit()


EXPECTED = {
    211383725: None,
    211453881: None,
    95106402: NOTRE_DAME[0],
    55309451: LSU[0],
    5: BILLS[0],
    6: None,
    7: CHIEFS[0],
}


def test_the_nfl_props_leave_lsu_and_notre_dame_and_stay_gone():
    with Session(_make_engine()) as session:
        _seed(session)
        first = _drain(session)
        after_first = _links(session)
        # The NULLs re-enter Phase 2 on the next run, where the college rosters
        # still list both players; the league check must refuse them.
        second = _drain(session)
        after_second = _links(session)

    assert first["errors"] == [] and second["errors"] == []
    assert after_first == EXPECTED
    assert after_second == EXPECTED
    assert first["links_outside_market_league"] == 3  # Delane, Love, "Buffalo"
    assert first["outcomes_relinked_into_market_league"] == 1
    assert first["outcomes_unlinked_outside_market_league"] == 2
    assert first["outcomes_linked_by_league"] == 1  # "Kansas City" -> Chiefs
    assert second["links_outside_market_league"] == 0


def test_without_the_slug_the_drain_leaves_every_college_link_standing():
    """STRAWMAN: the fixture carries the defect — with the slug naming no league,
    Phase 3 moves no Polymarket link and the roster re-takes the unlinked Delane leg."""
    with patch(
        "app.utils.market_team_sport._polymarket_slug_league", lambda _slug: None
    ), Session(_make_engine()) as session:
        _seed(session)
        stats = _drain(session)
        links = _links(session)
    assert stats["errors"] == []
    assert links[211383725] == LSU[0]
    assert links[211453881] == NOTRE_DAME[0]
    assert links[5] == BULLS[0]
    assert links[6] == LSU[0]


# ── The team page's own refusal ───────────────────────────────────────────────
def _pm_market(mid, name, slug, *, tier):
    return SimpleNamespace(
        id=mid, name=name, source="polymarket", external_id=str(mid),
        llm_sport_category="football", market_tier=tier,
        group_id=f"polymarket:{mid}", canonical_market_key=None,
        market_metadata={"polymarket_event_slug": slug},
    )


PRO_TITLE = _pm_market(700003, "Pro Football Champion", "pro-football-champion", tier=1)
COLLEGE_TITLE = _pm_market(700004, "NCAA Football Champion", "ncaa-football-champion", tier=1)
LSU_ROWS = [(_outcome(1, 0.02, LSU[0]), PRO_TITLE), (_outcome(2, 0.02, LSU[0]), COLLEGE_TITLE)]


async def test_a_college_page_refuses_a_pro_football_title_leg():
    path = await _path(LSU[0], "americanfootball_ncaaf", LSU_ROWS)
    assert _ids(path) == [(1, COLLEGE_TITLE.id)], path


async def test_without_the_slug_the_college_page_carries_the_pro_leg():
    """STRAWMAN: the page reads the slug off the row; unread, the NFL leg is a candidate."""
    with patch.object(teams_route, "market_event_slug", lambda _meta: None):
        path = await _path(LSU[0], "americanfootball_ncaaf", LSU_ROWS)
    assert path != [] and _ids(path) != [(1, COLLEGE_TITLE.id)], path
