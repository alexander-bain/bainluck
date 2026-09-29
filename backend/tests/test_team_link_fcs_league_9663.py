"""#9663 — Kalshi's FCS title board is the FCS league, not FBS.

WHAT A READER SAW. The South Carolina Gamecocks' and San Diego State's football
pages carried a 0.5-1% "Championship" step and the Washington Huskies' hero read
0.6%, all from Kalshi's FCS national title board (KXNCAAFFCS-27). None of those
schools play FCS.

WHY. The ticker maps are prefix maps, so ``KXNCAAFFCS`` resolves through
``kxncaaf`` to ``americanfootball_ncaaf``. The league check (#5119) compared FBS
with FBS and refused nothing, while every FCS row was refused as the other
league. Measured 2026-09-29: 68 of the board's 128 legs linked, all 68 on FBS
rows, and none of the 60 unlinked could ever bind. Read as FCS, 49 of the 68
moved and 19 cleared: the league matcher could not read "Montana St." as
"Montana State Bobcats" or "William & Mary" as "William and Mary Tribe"
(CERT-3806). With the spelling fallback the league matcher answers 125 of the
128 legs, and the backfill lands 123: VMI and LIU are under the Phase 2
selector's 4-character floor (#9687). Brown, Princeton and Mercyhurst have no
FCS row and stay NULL.

The team rows are production's own shapes (``teams`` read 2026-09-29).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team
from app.tasks import team_linking
from app.utils.market_team_sport import link_crosses_league, market_league_sport_key

from tests.test_team_link_drain_advances_7307 import (
    _AsyncShim,
    _FakeCursorStore,
    _make_engine,
)


SPORTS = [(2, "americanfootball_ncaaf"), (6, "americanfootball_ncaaf_fcs")]

# id, sport_id, name, alternate_names
GAMECOCKS = (15295, 2, "South Carolina Gamecocks", ["Gamecocks", "South Carolina"])
HUSKIES = (15301, 2, "Washington Huskies", ["Huskies", "Washington"])
AZTECS = (19767, 2, "San Diego State Aztecs", ["Aztecs", "San Diego St"])
VILLANOVA = (18622, 6, "Villanova Wildcats", ["Wildcats", "Villanova"])
EAGLES = (18623, 6, "Eastern Washington Eagles", ["Eagles", "E Washington"])
TOREROS = (18984, 6, "San Diego Toreros", ["Toreros", "San Diego"])
SC_STATE = (19781, 6, "South Carolina State Bulldogs", None)
# An FCS school's FBS-keyed row, with no FCS row at all.
MERCYHURST_FBS = (19800, 2, "Mercyhurst Lakers", None)

TEAMS = [GAMECOCKS, HUSKIES, AZTECS, VILLANOVA, EAGLES, TOREROS, SC_STATE, MERCYHURST_FBS]

# id, external_id, name
MARKETS = [
    (500001, "KXNCAAFFCS-27", "College Football FCS Championship"),
    (500002, "KXNCAAF-27", "College Football Championship"),
]

# id, market_id, name, stored team_id
OUTCOMES = [
    (1, 500001, "San Diego", AZTECS[0]),              # -> Toreros
    (2, 500001, "Eastern Washington", HUSKIES[0]),    # -> Eagles
    (3, 500001, "South Carolina St.", GAMECOCKS[0]),  # -> South Carolina State
    (7, 500001, "Mercyhurst", MERCYHURST_FBS[0]),     # no FCS row -> NULL
    (4, 500001, "Villanova", None),                   # -> Villanova (was refused as FCS)
    (5, 500002, "Washington", HUSKIES[0]),            # FBS board: untouched
    (6, 500002, "San Diego St.", AZTECS[0]),          # FBS board: untouched
]

EXPECTED = {
    1: TOREROS[0],
    2: EAGLES[0],
    3: SC_STATE[0],
    4: VILLANOVA[0],
    5: HUSKIES[0],
    6: AZTECS[0],
    7: None,
}


def _seed(session: Session, outcomes=OUTCOMES) -> None:
    session.add_all([Sport(id=i, key=k, name=k, active=True) for i, k in SPORTS])
    for i, s, n, a in TEAMS:
        session.add(Team(id=i, sport_id=s, name=n, alternate_names=a))
    for mid, ext, name in MARKETS:
        session.add(FuturesMarket(
            id=mid, source="kalshi", external_id=ext, name=name,
            category="championship", llm_sport_category="football",
            status="open", market_tier=1,
        ))
    session.flush()
    for oid, mid, name, team_id in outcomes:
        session.add(FuturesOutcome(
            id=oid, market_id=mid, external_id=f"o{oid}", name=name, team_id=team_id,
        ))
    session.commit()


def _drain(session: Session, limit: int = 100) -> dict:
    @asynccontextmanager
    async def _fake_task_session():
        yield _AsyncShim(session)

    async def _run():
        import unittest.mock as mock

        with mock.patch.object(team_linking, "get_task_session", _fake_task_session), \
                mock.patch.object(team_linking, "_cursor_store", _FakeCursorStore):
            return await team_linking._backfill_team_links(limit=limit, use_llm=False)

    return asyncio.run(_run())


def _links(session: Session) -> dict:
    session.flush()
    return dict(session.execute(select(FuturesOutcome.id, FuturesOutcome.team_id)).all())


def test_the_fcs_board_names_the_fcs_league_and_only_that_series_does():
    assert market_league_sport_key("kalshi", "KXNCAAFFCS-27") == "americanfootball_ncaaf_fcs"
    # Series that merely share the stem stay FBS.
    assert market_league_sport_key("kalshi", "KXNCAAF-27") == "americanfootball_ncaaf"
    assert market_league_sport_key("kalshi", "KXNCAAFFINALIST-27") == "americanfootball_ncaaf"
    assert market_league_sport_key("kalshi", "KXNCAAFFIRSTTDTEAM-26NOV01") == (
        "americanfootball_ncaaf"
    )
    # The team page's own refusal (routes/teams.py) reads the same answer.
    assert link_crosses_league("kalshi", "KXNCAAFFCS-27", "americanfootball_ncaaf")
    assert not link_crosses_league("kalshi", "KXNCAAFFCS-27", "americanfootball_ncaaf_fcs")
    assert not link_crosses_league("kalshi", "KXNCAAF-27", "americanfootball_ncaaf")


def test_fcs_legs_on_fbs_schools_move_to_their_fcs_school_or_clear():
    with Session(_make_engine()) as session:
        _seed(session)
        stats = _drain(session)
        links = _links(session)

    assert stats["errors"] == []
    assert links == EXPECTED
    assert stats["links_outside_market_league"] == 4  # outcomes 1, 2, 3, 7
    assert stats["outcomes_relinked_into_market_league"] == 3
    assert stats["outcomes_unlinked_outside_market_league"] == 1


def test_step_0_binds_an_unlinked_fcs_leg_inside_fcs_not_fbs():
    # Read off the bare ticker map the board is FBS, where "San Diego" is San
    # Diego State by city (its name minus "State Aztecs"). Phase 3 would then
    # clear that link on the next run, and Step 0 would write it again.
    outcomes = [(1, 500001, "San Diego", None)]
    with Session(_make_engine()) as session:
        _seed(session, outcomes)
        stats = _drain(session)
        links = _links(session)

    assert stats["errors"] == []
    assert links == {1: TOREROS[0]}
    assert stats["outcomes_linked_by_league"] == 1
    assert stats["links_outside_market_league"] == 0


# --- The league matcher's spelling fallback (CERT-3806's repair) ---------------

def _team(tid, name, aliases=None):
    return {"id": tid, "name": name, "alternate_names": aliases or []}


FCS_ROWS = [
    _team(1, "Montana Grizzlies", ["Grizzlies", "Montana"]),
    _team(2, "Montana State Bobcats", ["Bobcats", "Montana St"]),
    _team(3, "Idaho Vandals"),
    _team(4, "Idaho State Bengals"),
    _team(5, "South Carolina State Bulldogs"),
    _team(6, "Youngstown St Penguins", ["Youngstown State Penguins", "Penguins"]),
    _team(7, "William and Mary Tribe"),
    _team(8, "Arkansas Pine Bluff Golden Lions"),
    _team(9, "UT Martin Skyhawks", ["Skyhawks", "UT Martin"]),
    _team(10, "Houston Baptist Huskies"),
    _team(11, "Albany"),
    _team(12, "Central Connecticut Blue Devils"),
    _team(13, "Tennessee State Tigers"),
    _team(14, "East Tennessee State Buccaneers", ["ETSU", "Buccaneers"]),
]


def test_the_fallback_reads_a_college_feed_spelling_as_the_school_it_names():
    from app.utils.team_linking import match_outcome_to_league_team as match

    expected = {
        "Montana St.": 2,               # "St." is "State"
        "Montana": 1,                   # "Montana State" does not shadow "Montana"
        "Idaho": 3,                     # "Idaho State Bengals" is not a city "Idaho"
        "South Carolina St.": 5,
        "Youngstown St.": 6,            # the row writes "St" too
        "William & Mary": 7,
        "Arkansas-Pine Bluff": 8,
        "Tennessee-Martin": 9,          # the venue's own names for a school
        "Houston Christian": 10,
        "University at Albany": 11,
        "Central Connecticut St.": 12,
        "Tennessee St.": 13,            # "East Tennessee State" merely contains it
        "East Tennessee St.": 14,
        "Brown": None,                  # no row
    }
    assert {name: match(name, FCS_ROWS) for name in expected} == expected


def test_the_fallback_keeps_the_one_team_rule():
    from app.utils.team_linking import match_outcome_to_league_team as match

    # Any other continuation still shadows: "Miami" is either school.
    miami = [_team(1, "Miami Hurricanes", ["Miami"]), _team(2, "Miami (OH) RedHawks", ["Miami OH"])]
    assert match("Miami", miami) is None
    # A bare city names either club (the strict arm's own case, unchanged).
    la = [
        _team(1, "Los Angeles Lakers", ["Lakers", "Los Angeles"]),
        _team(2, "Los Angeles Clippers", ["Clippers"]),
    ]
    assert match("Los Angeles", la) is None
    # A substring of a word is no rival: "Duke" is inside "Dukes".
    duke = [_team(1, "Duke Blue Devils", ["Duke"]), _team(2, "Duquesne Dukes")]
    assert match("Duke", duke) == 1
    # Two rows answering the same spelling is no answer.
    twins = [_team(1, "Idaho State Bengals", ["Idaho St"]), _team(2, "Idaho St Bengals")]
    assert match("Idaho St.", twins) is None
    # Two rows that spell the same with nothing after it: no shadow applies, so
    # only the one-team rule refuses.
    assert match("Idaho St.", [_team(1, "Idaho State"), _team(2, "Idaho St")]) is None


def test_the_fallback_never_replaces_an_answer_the_strict_arms_give():
    from app.utils.team_linking import match_outcome_to_league_team as match

    # The strict city arm reads "Idaho" as the league's only Idaho row; the
    # fallback alone would refuse it (a city form never drops "State"). The
    # strict answer stands, so no link the matcher makes today moves.
    assert match("Idaho", [_team(4, "Idaho State Bengals")]) == 4


# --- The whole board (CERT-3806: every leg reaches its FCS school) ------------

def test_the_whole_board_leaves_every_fbs_page_and_lands_on_its_fcs_school():
    import json
    from pathlib import Path

    fx = json.loads(
        (Path(__file__).parent / "fixtures" / "kalshi_fcs_board_9663.json").read_text()
    )
    fbs_ids = {tid for tid, _, _ in fx["fbs_teams"]}
    fcs_by_name = {name: tid for tid, name, _ in fx["fcs_teams"]}
    assert len(fx["legs"]) == 128
    assert sum(1 for _, _, tid in fx["legs"] if tid in fbs_ids) == 68  # the BEFORE

    with Session(_make_engine()) as session:
        session.add_all([Sport(id=i, key=k, name=k, active=True) for i, k in SPORTS])
        for sport_id, rows in ((2, fx["fbs_teams"]), (6, fx["fcs_teams"])):
            for tid, name, aliases in rows:
                session.add(Team(id=tid, sport_id=sport_id, name=name, alternate_names=aliases))
        session.add(FuturesMarket(
            id=1, source="kalshi", external_id="KXNCAAFFCS-27",
            name="FCS Championship 2027", category="championship",
            llm_sport_category="football", status="open", market_tier=1,
        ))
        session.flush()
        for oid, name, team_id in fx["legs"]:
            session.add(FuturesOutcome(
                id=oid, market_id=1, external_id=f"o{oid}", name=name, team_id=team_id,
            ))
        session.commit()
        name_of = {oid: name for oid, name, _ in fx["legs"]}

        # The scheduled run's limit: one run selects the whole board. (Each
        # `_drain` starts a fresh cursor store, so pages of 100 would re-read the
        # head and never reach the last legs.)
        assert _drain(session, limit=2000)["errors"] == []
        links = _links(session)

    # Wrong page: no leg is left on an FBS school.
    assert [name_of[o] for o, t in links.items() if t in fbs_ids] == []
    # Right page: each leg is on the FCS school read for it by hand, except the
    # two the Phase 2 selector never reads (names under 4 characters, #9687).
    held = {"LIU", "VMI"}
    expected = {
        name_of[o]: None if name_of[o] in held else fcs_by_name.get(fx["expected"][name_of[o]])
        for o in links
    }
    assert {name_of[o]: t for o, t in links.items()} == expected
    assert sum(1 for t in links.values() if t is not None) == 123
    assert sorted(n for o, n in name_of.items() if links[o] is None) == [
        "Brown", "LIU", "Mercyhurst", "Princeton", "VMI",
    ]
    # No FCS row exists for three; the matcher already answers the two held legs.
    assert [n for n, school in fx["expected"].items() if school is None] == [
        "Brown", "Mercyhurst", "Princeton",
    ]
    from app.utils.team_linking import match_outcome_to_league_team

    fcs_rows = [_team(tid, name, aliases) for tid, name, aliases in fx["fcs_teams"]]
    assert {n: match_outcome_to_league_team(n, fcs_rows) for n in sorted(held)} == {
        "LIU": fcs_by_name["LIU Sharks"], "VMI": fcs_by_name["VMI Keydets"],
    }
