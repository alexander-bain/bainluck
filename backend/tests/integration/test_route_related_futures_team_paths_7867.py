"""#7867 — a team's Championship Path holds its own markets, not another club's.

WHAT A READER SAW (production, ids on the issue and its comments):

  * `/events/15311565` Duke Blue Devils — `Arizona State Sun Devils`, `Middle
    Tennessee Blue Raiders`, `Delaware Blue Hens` on Duke's NCAAF title market,
    and `Duke Tobin` (an NFL executive) as the highest-relevance row.
  * `/events/15308925` Miami Hurricanes — fourteen `Miami (OH)` rows, still
    served at `d4d69292` (read 2026-09-23 through the public API).
  * `/events/15315984` Coastal Carolina — 22 rows for South / North / East
    Carolina and NC State, while Liberty beside it served 0 foreign rows.
  * `/events/15316298` Giants v Twins — `Japan NPB Champion || Yomiuri Giants`
    at rel 44.7, the highest row on the Giants' card; `Korea KBO Champion ||
    LG Twins` the highest on the Twins'.
  * `/events/15316211` Islanders — `Bridgeport Islanders` (AHL), `New York
    Rangers`, and the Rangers' `New York R and …` Stanley Cup legs.
  * `/events/15298683` Lynx / Liberty — `Minnesota Timberwolves`, `New York
    Knicks`.

THROUGH THE REAL HANDLER. Every test below issues `GET /api/events/{id}/
related-futures` against `app.main.app` with the route's own queries answered
by statement text — the harness `test_route_related_futures.py` provides and
#7851 / #8052 reuse. The only thing faked is the database; classification,
merge, dedup and ordering are the shipped code.

THE ROSTER IS THE FAMILY. #7867 widened the one roster read to every `teams`
row in the sport family (see `_load_team_roster`). The session below answers
that read with rows across leagues, carrying `sport_id`, exactly as the
widened query returns them. Production ids are used where the public API gave
them (2026-09-23); constructed ids are in the 9xxxxx range and say so.

WHAT THE CONTROLS ARE FOR. The failure this can cause is worse than the
defect — a refusal aimed one token too wide empties a card — so more than half
the arms are refusals-to-refuse: `Miami (FL)` (the row the rejected rule
lost), abbreviated D/ST props, bare venue labels, a bare label that only a
sibling league lists, a twin row in our own league, an event whose teams do
not resolve, a same-name school in the sibling league, a real 0% and an
unpriced leg. Every assertion names literal outcome ids, so a mutant that
hides every row, or merely reorders the wrong ones, fails on the controls.
"""

import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

from tests.integration.test_route_related_futures import (
    _make_event,
    _make_market,
    _make_outcome,
    _MockResult,
)

_EVENT_IDS = itertools.count(7867001)

# ── sport ids (constructed; the family is what matters) ─────────────────────
NCAAF, NFL, FCS = 700100, 700101, 700102
MLB, NPB, KBO = 700200, 700201, 700202
NHL, AHL = 700300, 700301
WNBA, NBA = 700400, 700401
BASKETBALL_OTHER = 700402

# ── the family rosters: (id, sport_id, name, abbreviation, location, alts) ──
# production ids: Duke 15311, Miami (OH) RedHawks 15332, South Carolina 15295,
# Ball State 15299, Dolphins 565, Patriots 11, Steelers 540, Lions 567.
FOOTBALL = [
    (15311, NCAAF, "Duke Blue Devils", "DUKE", "Duke", ["Duke", "Blue Devils"]),
    (900001, NCAAF, "Stanford Cardinal", "STAN", "Stanford", ["Stanford"]),
    (900002, NCAAF, "Miami Hurricanes", "MIA", "Miami (FL)", ["Miami (FL)", "Hurricanes"]),
    (900020, NCAAF, "Wake Forest Demon Deacons", "WAKE", "Wake Forest", ["Wake Forest"]),
    (15332, NCAAF, "Miami (OH) RedHawks", "M-OH", "Miami (OH)", ["Miami (OH)"]),
    (900003, NCAAF, "Arizona State Sun Devils", "ASU", "Arizona State", ["Sun Devils"]),
    (900004, NCAAF, "Middle Tennessee Blue Raiders", "MTSU", "Middle Tennessee", []),
    (900005, NCAAF, "Delaware Blue Hens", "DEL", "Delaware", []),
    (900006, NCAAF, "Coastal Carolina Chanticleers", "CCU", "Coastal Carolina", ["Coastal Carolina"]),
    (900021, NCAAF, "Liberty Flames", "LIB", "Liberty", ["Liberty"]),
    (15295, NCAAF, "South Carolina Gamecocks", "SC", "South Carolina", ["South Carolina"]),
    (900007, NCAAF, "North Carolina Tar Heels", "UNC", "North Carolina", ["North Carolina"]),
    (900008, NCAAF, "North Carolina State Wolfpack", "NCSU", "North Carolina St.", ["North Carolina St."]),
    (900009, NCAAF, "East Carolina Pirates", "ECU", "East Carolina", ["East Carolina"]),
    (900010, NCAAF, "Penn State Nittany Lions", "PSU", "Penn State", ["Penn State"]),
    (15299, NCAAF, "Ball State Cardinals", "BALL", "Ball St.", ["Ball St."]),
    (900011, FCS, "Columbia Lions", "COLU", "Columbia", ["Columbia"]),
    (900022, FCS, "Lafayette Leopards", "LAF", "Lafayette", ["Lafayette"]),
    (565, NFL, "Miami Dolphins", "MIA", "Miami", ["Miami", "Dolphins"]),
    (11, NFL, "New England Patriots", "NE", "New England", ["New England", "Patriots"]),
    (540, NFL, "Pittsburgh Steelers", "PIT", "Pittsburgh", ["Pittsburgh", "Steelers"]),
    (567, NFL, "Detroit Lions", "DET", "Detroit", ["Detroit", "Lions"]),
]

# production ids: Giants 6609, Twins 10739, Tigers 10747, Yomiuri 12494,
# Hanshin 12483, Lotte 12796, LG Twins 12794.
BASEBALL = [
    (6609, MLB, "San Francisco Giants", "SF", "San Francisco", ["Giants", "San Francisco"]),
    (10739, MLB, "Minnesota Twins", "MIN", "Minnesota", ["Twins", "Minnesota"]),
    (10747, MLB, "Detroit Tigers", "DET", "Detroit", ["Tigers", "Detroit"]),
    (900030, MLB, "Washington Nationals", "WSH", "Washington", ["Nationals", "Washington"]),
    (12494, NPB, "Yomiuri Giants", None, None, None),
    (12483, NPB, "Hanshin Tigers", None, None, None),
    (12796, KBO, "Lotte Giants", None, None, None),
    (12794, KBO, "LG Twins", None, None, None),
]

# production ids: Islanders 54 / twins 6181, 12716; Rangers 57 / twin 8293;
# Bridgeport 1347.
HOCKEY = [
    (54, NHL, "New York Islanders", "NYI", "New York", ["Islanders", "New York"]),
    (6181, NHL, "New York I", "NYI", None, None),
    (12716, NHL, "New Jersey", "NYI", None, None),
    (57, NHL, "New York Rangers", "NYR", "New York", ["Rangers", "New York"]),
    (8293, NHL, "New York R", "NYR", None, None),
    (900040, NHL, "New Jersey Devils", "NJ", "New Jersey", ["Devils"]),
    (900041, NHL, "Colorado Avalanche", "COL", "Colorado", ["Avalanche", "Colorado"]),
    (1347, AHL, "Bridgeport Islanders", None, None, None),
]

# production ids: Lynx 13923, Liberty 13414, Timberwolves 106, Knicks 108.
BASKETBALL = [
    (13923, WNBA, "Minnesota Lynx", "MIN", "Minnesota", ["Lynx", "Minnesota"]),
    (13414, WNBA, "New York Liberty", "NY", "New York", ["Liberty", "New York"]),
    (106, NBA, "Minnesota Timberwolves", "MIN", "Minnesota", ["Timberwolves", "Minnesota"]),
    (108, NBA, "New York Knicks", "NY", "New York", ["Knicks", "New York"]),
]


def _fresh_event_id() -> int:
    return next(_EVENT_IDS)


def _event(home, away, *, sport_key, sport_id, status="scheduled"):
    ev = _make_event(
        id=_fresh_event_id(), home_team=home, away_team=away,
        status=status, sport_key=sport_key,
    )
    ev.sport_id = sport_id
    ev.sport.name = sport_key
    return ev


def _outcome(id, market, name, probability, *, ticker=None, team_id=None):
    # The shared harness derives `opening_probability` from the price, so an
    # UNPRICED leg is built at 0.0 and then un-priced — the route reads
    # `current_probability` and must serve the row with `probability: null`.
    o = _make_outcome(
        id=id, market=market, name=name,
        probability=0.0 if probability is None else probability,
        probability_change_24h=0.0,
    )
    if probability is None:
        o.current_probability = None
        o.opening_probability = None
    o.external_id = ticker
    o.team_id = team_id
    return o


def _roster_rows(table):
    return [
        SimpleNamespace(
            id=i, sport_id=s, name=n, abbreviation=a, location=loc,
            alternate_names=list(alts) if alts else alts,
            logo_url_small=None, logo_url=None,
        )
        for i, s, n, a, loc, alts in table
    ]


def _team_row(team_id):
    return SimpleNamespace(id=team_id, alternate_names=[], roster_players=[])


def _session(event, outcomes, *, roster, home_team_id, away_team_id, sport_ids):
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    market_ids = sorted({o.market.id for o in outcomes})
    per_team = iter([
        _team_row(home_team_id) if home_team_id else None,
        _team_row(away_team_id) if away_team_id else None,
    ])
    roster_reads = {"n": 0}

    async def mock_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower()
        if "from events" in stmt_str:
            return _MockResult(scalar=event)
        if "select sports.id" in stmt_str:
            return _MockResult(rows=[SimpleNamespace(id=s) for s in sport_ids])
        if "from teams" in stmt_str:
            if "teams.logo_url" in stmt_str:
                roster_reads["n"] += 1
                # Faithful to the statement's own scope: the family read joins
                # `sports` and takes every row; the pre-#7867 read is
                # `teams.sport_id = :x` and must see ONLY the event's league —
                # otherwise a base run is handed identity it never queried.
                rows = _roster_rows(roster)
                if "join sports" not in stmt_str:
                    rows = [r for r in rows if r.sport_id == event.sport_id]
                return _MockResult(rows=rows)
            if "teams.id" in stmt_str:
                return _MockResult(first=next(per_team, None))
            return _MockResult(rows=[])
        if "from futures_outcomes" in stmt_str:
            return _MockResult(scalar_rows=list(outcomes))
        if "from futures_odds_snapshots" in stmt_str:
            return _MockResult(rows=[])
        if "from line_movement_analyses" in stmt_str:
            return _MockResult(scalar=None)
        if "select futures_markets.id" in stmt_str:
            if "order by futures_markets.market_tier" in stmt_str:
                return _MockResult(
                    rows=[SimpleNamespace(id=m, market_tier=1) for m in market_ids]
                )
            return _MockResult(rows=[])
        return _MockResult()

    session.execute = AsyncMock(side_effect=mock_execute)
    session.roster_reads = roster_reads
    return session


async def _get(monkeypatch, session, event_id):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch(
                "app.services.league_context.enrich_event_with_context",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get(f"/api/events/{event_id}/related-futures")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ids(body, side=None):
    sides = [side] if side else ["home_team_futures", "away_team_futures"]
    return {r["outcome_id"] for s in sides for r in body[s]}


def _by_id(body, outcome_id):
    for s in ("home_team_futures", "away_team_futures"):
        for r in body[s]:
            if r["outcome_id"] == outcome_id:
                return r
    return None


# ═══ Duke Blue Devils — the issue's own page ════════════════════════════════

NCAAF_TITLE = 6601311          # production market: NCAAF Championship Winner
ACC_MATCHUP = 59172714         # production market: ACC Conference Championship Matchup


async def test_duke_keeps_its_own_rows_and_loses_the_other_schools(monkeypatch):
    event = _event("Duke Blue Devils", "Stanford Cardinal", sport_key="americanfootball_ncaaf", sport_id=NCAAF)
    title = _make_market(id=NCAAF_TITLE, name="NCAAF Championship Winner", source="odds_api")
    acc = _make_market(id=ACC_MATCHUP, name="ACC Conference Championship Matchup", source="kalshi")
    exec_award = _make_market(id=900100, name="Executive of the Year Winner?", source="kalshi")
    outcomes = [
        _outcome(34312774, title, "Duke Blue Devils", 0.001012),            # production row — KEEP
        _outcome(34312827, title, "Stanford Cardinal", 0.000565),           # production row — KEEP (away)
        _outcome(78670001, title, "Arizona State Sun Devils", 0.02),        # `Devils`   — REFUSE
        _outcome(78670002, title, "Middle Tennessee Blue Raiders", 0.001),  # `Blue`     — REFUSE
        _outcome(78670003, title, "Delaware Blue Hens", 0.0005),            # `Blue`     — REFUSE
        _outcome(222348725, acc, "Duke vs Miami (FL)", 0.17),               # production — KEEP
        _outcome(222348782, acc, "Duke vs Stanford", 0.15),                 # production — KEEP
        _outcome(78670004, exec_award, "Duke Tobin", 0.19),                 # a person   — LIMITATION, stays
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=FOOTBALL, home_team_id=15311, away_team_id=900001,
                 sport_ids=[NCAAF]),
        event.id,
    )
    home = _ids(body, "home_team_futures")
    assert {34312774, 222348725, 222348782} <= home
    assert 34312827 in _ids(body, "away_team_futures")
    assert not {78670001, 78670002, 78670003} & _ids(body)
    # The named limitation, asserted so a later reader knows it is deliberate:
    # a person is not in `teams`, so this row is not refused here.
    assert 78670004 in home


# ═══ Miami Hurricanes — Miami (FL) is kept, Miami (OH) is refused ═══════════

MAC_MATCHUP = 59172719         # production market
ACC_QUALIFIERS = 52756023      # production market
CFP_OH = 58420090              # production market: Will Miami (OH) Make the 2027 CFP …?
CFB_FL = 61373595              # production market: Will Miami (FL) Make the 2026-27 CFB Playoffs?


async def test_the_hurricanes_keep_miami_fl_and_lose_miami_oh(monkeypatch):
    event = _event("Wake Forest Demon Deacons", "Miami Hurricanes", sport_key="americanfootball_ncaaf", sport_id=NCAAF)
    mac = _make_market(id=MAC_MATCHUP, name="MAC Conference Championship Matchup", source="kalshi")
    acc = _make_market(id=ACC_MATCHUP, name="ACC Conference Championship Matchup", source="kalshi")
    qual = _make_market(id=ACC_QUALIFIERS, name="College Football ACC Championship Game Qualifiers", source="kalshi")
    title = _make_market(id=NCAAF_TITLE, name="NCAAF Championship Winner", source="odds_api")
    cfp_oh = _make_market(id=CFP_OH, name="Will Miami (OH) Make the 2027 College Football Playoff National Championship Game?", source="polymarket")
    cfb_fl = _make_market(id=CFB_FL, name="Will Miami (FL) Make the 2026-27 CFB Playoffs?", source="polymarket")
    outcomes = [
        # production rows the reader wants — KEEP
        _outcome(198635142, qual, "Miami (FL)", 0.9, ticker="KXNCAAFACCQUAL-26-MIAFL"),
        _outcome(34312736, title, "Miami Hurricanes", 0.085776),
        _outcome(222348730, acc, "Miami (FL) vs Virginia Tech", 0.19),
        _outcome(231038325, cfb_fl, "Yes", 0.87),                       # reached by MARKET name
        _outcome(206775933, qual, "Wake Forest", 0.06),                 # home control
        # production rows that are another school — REFUSE
        _outcome(225996032, mac, "Ball St. vs Miami (OH)", 0.1, ticker="KXNCAAFCONFMATCHUP-26MAC-BALLMOH"),
        _outcome(225996002, mac, "Miami (OH) vs Toledo", 0.18, ticker="KXNCAAFCONFMATCHUP-26MAC-MOHTOL"),
        _outcome(216717539, cfp_oh, "Yes", 0.0265),                     # reached by MARKET name
        _outcome(216717540, cfp_oh, "No", 0.9735),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=FOOTBALL, home_team_id=900020, away_team_id=900002,
                 sport_ids=[NCAAF]),
        event.id,
    )
    away = _ids(body, "away_team_futures")
    assert {198635142, 34312736, 222348730, 231038325} <= away
    assert 206775933 in _ids(body, "home_team_futures")
    assert not {225996032, 225996002, 216717539, 216717540} & _ids(body)


async def test_a_bare_miami_that_only_the_dolphins_list_is_still_the_hurricanes(monkeypatch):
    """The NFL row lists `Miami`; the Hurricanes' row lists `Miami (FL)`. An
    equal-span refusal would take the venue's own bare label away from the
    college page. Strictly-longer only."""
    event = _event("Wake Forest Demon Deacons", "Miami Hurricanes", sport_key="americanfootball_ncaaf", sport_id=NCAAF)
    qual = _make_market(id=ACC_QUALIFIERS, name="College Football ACC Championship Game Qualifiers", source="kalshi")
    outcomes = [_outcome(78670010, qual, "Miami", 0.9)]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=FOOTBALL, home_team_id=900020, away_team_id=900002,
                 sport_ids=[NCAAF]),
        event.id,
    )
    assert 78670010 in _ids(body, "away_team_futures")


# ═══ Coastal Carolina — the geographic token, with Liberty as the control ═══

STEEL_BRIDGE = 61461617        # production market: 2027 Steel Bridge National Champion
CUSA_MATCHUP = 900101


async def test_coastal_carolina_loses_the_other_carolinas_and_liberty_is_untouched(monkeypatch):
    event = _event("Coastal Carolina Chanticleers", "Liberty Flames", sport_key="americanfootball_ncaaf", sport_id=NCAAF)
    steel = _make_market(id=STEEL_BRIDGE, name="2027 Steel Bridge National Champion", source="kalshi")
    sec = _make_market(id=900102, name="SEC Conference Championship Matchup", source="kalshi")
    acc = _make_market(id=ACC_MATCHUP, name="ACC Conference Championship Matchup", source="kalshi")
    aac = _make_market(id=900103, name="AAC Conference Championship Matchup", source="kalshi")
    sunbelt = _make_market(id=900104, name="Sun Belt Conference Championship Matchup", source="kalshi")
    cusa = _make_market(id=CUSA_MATCHUP, name="Conference USA Championship Matchup", source="kalshi")
    outcomes = [
        # KEEP
        _outcome(78670020, steel, "Coastal Carolina", 0.05),
        _outcome(78670021, sunbelt, "Coastal Carolina vs Troy", 0.12),
        _outcome(78670022, steel, "Liberty", 0.05),                     # the control side
        _outcome(78670023, cusa, "Liberty vs Western Kentucky", 0.2),
        # REFUSE — the 5% a reader saw printed under the Chanticleers' crest
        _outcome(78670024, steel, "South Carolina", 0.05),
        _outcome(78670025, sec, "Alabama vs South Carolina", 0.03),
        _outcome(78670026, acc, "North Carolina St. vs Pittsburgh", 0.15),
        _outcome(78670027, acc, "Boston College vs North Carolina", 0.15),
        _outcome(78670028, aac, "East Carolina vs Navy", 0.1),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=FOOTBALL, home_team_id=900006, away_team_id=900021,
                 sport_ids=[NCAAF]),
        event.id,
    )
    assert {78670020, 78670021} <= _ids(body, "home_team_futures")
    assert {78670022, 78670023} <= _ids(body, "away_team_futures")
    assert not {78670024, 78670025, 78670026, 78670027, 78670028} & _ids(body)
    # Liberty's card is byte-for-byte the control: exactly its two rows.
    assert _ids(body, "away_team_futures") == {78670022, 78670023}


# ═══ MLB — a foreign league's club is refused; a real 0% and an unpriced leg stay ═══

NPB_TITLE = 11371619           # production market: Japan NPB Champion
KBO_TITLE = 11371643           # production market: Korea KBO Champion
WS_POLY = 114584               # production market: MLB World Series Champion 2026


async def test_the_giants_and_twins_lose_yomiuri_lotte_and_lg(monkeypatch):
    event = _event("San Francisco Giants", "Minnesota Twins", sport_key="baseball_mlb", sport_id=MLB, status="live")
    npb = _make_market(id=NPB_TITLE, name="Japan NPB Champion", source="kalshi")
    kbo = _make_market(id=KBO_TITLE, name="Korea KBO Champion", source="kalshi")
    ws = _make_market(id=WS_POLY, name="MLB World Series Champion 2026", source="polymarket")
    al = _make_market(id=900200, name="MLB: 2026 American League Champion", source="polymarket")
    csm = _make_market(id=2417016, name="Pro Baseball Championship Series Matchup", source="kalshi")
    outcomes = [
        # production rows — REFUSE (rel 44.7 / 41.0, the highest on each card)
        _outcome(64406477, npb, "Yomiuri Giants", 0.08),
        _outcome(78670030, kbo, "Lotte Giants", 0.01),
        _outcome(64406819, kbo, "LG Twins", 0.155),
        # KEEP: a real zero, the exact full-name row, a bare state, a matchup leg
        _outcome(1634483, ws, "San Francisco Giants", 0.0),
        _outcome(78670031, al, "Minnesota Twins", 0.0),
        _outcome(2327, csm, "Minnesota", 0.001),
        _outcome(13986802, csm, "Minnesota vs San Francisco", 0.005),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=BASEBALL, home_team_id=6609, away_team_id=10739,
                 sport_ids=[MLB, NPB, KBO]),
        event.id,
    )
    assert not {64406477, 78670030, 64406819} & _ids(body)
    assert 1634483 in _ids(body, "home_team_futures")
    assert _by_id(body, 1634483)["probability"] in (0.0, None)   # a real zero, not a dropped row
    assert {78670031, 2327} <= _ids(body, "away_team_futures")
    assert 13986802 in _ids(body)


async def test_the_tigers_unpriced_world_series_row_stays_and_hanshin_goes(monkeypatch):
    event = _event("Detroit Tigers", "Washington Nationals", sport_key="baseball_mlb", sport_id=MLB)
    npb = _make_market(id=NPB_TITLE, name="Japan NPB Champion", source="kalshi")
    ws = _make_market(id=WS_POLY, name="MLB World Series Champion 2026", source="polymarket")
    outcomes = [
        _outcome(78670040, npb, "Hanshin Tigers", 0.125),               # REFUSE
        _outcome(78670041, ws, "Detroit Tigers", None),                  # KEEP — unpriced leg
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=BASEBALL, home_team_id=10747, away_team_id=900030,
                 sport_ids=[MLB, NPB, KBO]),
        event.id,
    )
    assert 78670040 not in _ids(body)
    row = _by_id(body, 78670041)
    assert row is not None and row["probability"] is None


# ═══ NHL — the AHL affiliate and the city sibling go; the twin row is ours ═══

NHL_CHAMP = 900300
AHL_WIN = 900301
SCF_MATCHUP = 900302


async def test_the_islanders_lose_bridgeport_and_the_rangers(monkeypatch):
    event = _event("New Jersey Devils", "New York Islanders", sport_key="icehockey_nhl", sport_id=NHL)
    champ = _make_market(id=NHL_CHAMP, name="NHL: 2027 Champion", source="polymarket")
    ahl = _make_market(id=AHL_WIN, name="American Hockey League: Winner", source="polymarket")
    scf = _make_market(id=SCF_MATCHUP, name="Stanley Cup Final Matchup", source="kalshi")
    outcomes = [
        _outcome(78670050, ahl, "Bridgeport Islanders", 0.06),              # REFUSE
        _outcome(78670051, champ, "New York Rangers", 0.03),                # REFUSE
        _outcome(78670052, scf, "New York R and Colorado", 0.004),          # REFUSE (Rangers' twin row)
        _outcome(78670053, champ, "New York Islanders", 0.02),              # KEEP
        _outcome(78670054, scf, "New York I and Colorado", 0.003),          # KEEP (Islanders' twin row)
        _outcome(78670055, champ, "New Jersey Devils", 0.05),               # KEEP (home)
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=HOCKEY, home_team_id=900040, away_team_id=54,
                 sport_ids=[NHL, AHL]),
        event.id,
    )
    assert not {78670050, 78670051, 78670052} & _ids(body)
    assert {78670053, 78670054} <= _ids(body, "away_team_futures")
    assert 78670055 in _ids(body, "home_team_futures")


async def test_on_the_rangers_own_page_their_twin_rows_are_theirs(monkeypatch):
    """`New York R` (8293) shares `NYR` with the Rangers (57) in the same
    league, so it is ours and the Stanley Cup legs stay on the Rangers' page.
    The Islanders' leg beside it names no club of this page and goes."""
    event = _event("New York Rangers", "New Jersey Devils", sport_key="icehockey_nhl", sport_id=NHL)
    scf = _make_market(id=SCF_MATCHUP, name="Stanley Cup Final Matchup", source="kalshi")
    outcomes = [
        _outcome(78670060, scf, "New York R and Colorado", 0.004),          # KEEP
        _outcome(78670061, scf, "New York I and Colorado", 0.003),          # REFUSE — the Islanders'
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=HOCKEY, home_team_id=57, away_team_id=900040,
                 sport_ids=[NHL, AHL]),
        event.id,
    )
    assert 78670060 in _ids(body, "home_team_futures")
    assert 78670061 not in _ids(body)


async def test_a_leg_naming_the_opponent_beside_a_foreign_club_lands_on_the_opponent(monkeypatch):
    """Per-side: on a Rangers v Avalanche page, `New York I and Colorado` is
    the Islanders' AND Colorado's. It is served — on Colorado's side, not
    through the Islanders' token onto the Rangers'."""
    event = _event("New York Rangers", "Colorado Avalanche", sport_key="icehockey_nhl", sport_id=NHL)
    scf = _make_market(id=SCF_MATCHUP, name="Stanley Cup Final Matchup", source="kalshi")
    outcomes = [_outcome(78670062, scf, "New York I and Colorado", 0.003)]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=HOCKEY, home_team_id=57, away_team_id=900041,
                 sport_ids=[NHL, AHL]),
        event.id,
    )
    assert 78670062 in _ids(body, "away_team_futures")
    assert 78670062 not in _ids(body, "home_team_futures")


# ═══ WNBA — the NBA counterpart goes; the bare state label stays ════════════

async def test_the_lynx_and_liberty_lose_their_nba_counterparts(monkeypatch):
    event = _event("Minnesota Lynx", "New York Liberty", sport_key="basketball_wnba", sport_id=WNBA)
    nba = _make_market(id=900400, name="NBA Championship Winner", source="odds_api")
    wnba = _make_market(id=900401, name="WNBA: 2026 Champion", source="polymarket")
    comm = _make_market(id=900402, name="WNBA Commissioner's Cup Winner", source="kalshi")
    outcomes = [
        _outcome(78670070, nba, "Minnesota Timberwolves", 0.04),           # REFUSE
        _outcome(78670071, nba, "New York Knicks", 0.09),                  # REFUSE
        _outcome(78670072, wnba, "Minnesota Lynx", 0.3),                   # KEEP
        _outcome(78670073, wnba, "New York Liberty", 0.25),                # KEEP
        _outcome(78670074, comm, "Minnesota", 0.2),                        # KEEP — bare label
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=BASKETBALL, home_team_id=13923, away_team_id=13414,
                 sport_ids=[WNBA]),   # the women's branch narrows the pool; the roster read does not
        event.id,
    )
    assert not {78670070, 78670071} & _ids(body)
    assert {78670072, 78670074} <= _ids(body, "home_team_futures")
    assert 78670073 in _ids(body, "away_team_futures")


# ═══ NFL — abbreviated D/ST props and short labels are untouched ════════════

async def test_abbreviated_defensive_props_and_bare_labels_are_kept(monkeypatch):
    event = _event("New England Patriots", "Pittsburgh Steelers", sport_key="americanfootball_nfl", sport_id=NFL, status="live")
    dst = _make_market(id=900500, name="Pro Football Defensive Sacks Leaders", source="kalshi")
    afc = _make_market(id=900501, name="Pro Football: 2027 AFC Champion", source="kalshi")
    title = _make_market(id=NCAAF_TITLE, name="NCAAF Championship Winner", source="odds_api")
    outcomes = [
        _outcome(78670080, dst, "NE Patriots D/ST: 1+", 0.6),              # KEEP
        _outcome(78670081, dst, "PIT Steelers D/ST: 1+", 0.55),            # KEEP
        _outcome(78670082, afc, "New England", 0.05),                      # KEEP
        _outcome(78670083, afc, "Pittsburgh", 0.07),                       # KEEP
        _outcome(78670084, title, "Penn State Nittany Lions", 0.03),       # REFUSE (a college, via nothing of ours — control that it is simply not matched)
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=FOOTBALL, home_team_id=11, away_team_id=540,
                 sport_ids=[NFL]),
        event.id,
    )
    assert {78670080, 78670082} <= _ids(body, "home_team_futures")
    assert {78670081, 78670083} <= _ids(body, "away_team_futures")
    assert 78670084 not in _ids(body)


# ═══ Columbia Lions — same mascot, two other leagues ════════════════════════

async def test_columbia_loses_detroit_and_penn_state(monkeypatch):
    event = _event("Columbia Lions", "Lafayette Leopards", sport_key="americanfootball_ncaaf", sport_id=FCS)
    sb = _make_market(id=900600, name="NFL Super Bowl Winner", source="odds_api")
    title = _make_market(id=NCAAF_TITLE, name="NCAAF Championship Winner", source="odds_api")
    ivy = _make_market(id=900601, name="Ivy League Champion", source="kalshi")
    outcomes = [
        _outcome(78670090, sb, "Detroit Lions", 0.06),                     # REFUSE
        _outcome(78670091, title, "Penn State Nittany Lions", 0.03),       # REFUSE
        _outcome(78670092, ivy, "Columbia", 0.1),                          # KEEP
        _outcome(78670093, ivy, "Lafayette", 0.05),                        # away — not Ivy, but the label is theirs
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=FOOTBALL, home_team_id=900011, away_team_id=900022,
                 sport_ids=[FCS, NCAAF, NFL]),
        event.id,
    )
    assert not {78670090, 78670091} & _ids(body)
    assert 78670092 in _ids(body, "home_team_futures")
    assert 78670093 in _ids(body, "away_team_futures")


# ═══ Same-name school across leagues; unknown league metadata ═══════════════

async def test_the_same_school_in_the_sibling_league_is_ours(monkeypatch):
    """CONSTRUCTED. The women's row has the lower id; the event resolved the
    men's. Both are ours by name, so `UConn vs Duke` stays."""
    roster = [
        (900700, WNBA, "Connecticut Huskies", "CONN", "Connecticut", ["UConn"]),
        (900701, NBA, "Connecticut Huskies", "CONN", "Connecticut", ["UConn"]),
        (900702, WNBA, "Central Connecticut St.", "CCSU", "Central Connecticut", []),
        (15311, NBA, "Duke Blue Devils", "DUKE", "Duke", ["Duke"]),
    ]
    event = _event("Connecticut Huskies", "Duke Blue Devils", sport_key="basketball_ncaab", sport_id=NBA)
    conf = _make_market(id=900703, name="Big East Tournament Matchup", source="kalshi")
    nec = _make_market(id=900704, name="NEC Men's Conference Tournament Champion", source="kalshi")
    outcomes = [
        _outcome(78670100, conf, "UConn vs Duke", 0.2),                    # KEEP
        _outcome(78670101, nec, "Central Connecticut St.", 0.13),          # REFUSE
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, roster=roster, home_team_id=900701, away_team_id=15311,
                 sport_ids=[NBA]),
        event.id,
    )
    assert 78670100 in _ids(body)
    assert 78670101 not in _ids(body)


async def test_an_event_whose_teams_do_not_resolve_keeps_todays_payload(monkeypatch):
    """Unknown league metadata (`basketball_other`, no `teams` row for either
    side): nothing is ours, so nothing can be foreign, and the payload is
    exactly what it is today — foreign rows included. Asserted so the
    limitation is deliberate. (The merge step's own roster read, gated on any
    merge group, is pre-existing and may still run; it arms nothing here.)"""
    event = _event("Minnesota Lynx", "New York Liberty", sport_key="basketball_other", sport_id=BASKETBALL_OTHER)
    nba = _make_market(id=900400, name="NBA Championship Winner", source="odds_api")
    outcomes = [_outcome(78670110, nba, "Minnesota Timberwolves", 0.04)]
    session = _session(event, outcomes, roster=BASKETBALL, home_team_id=None, away_team_id=None,
                       sport_ids=[WNBA, NBA, BASKETBALL_OTHER])
    body = await _get(monkeypatch, session, event.id)
    assert 78670110 in _ids(body)
    assert session.roster_reads["n"] <= 1


# ═══ The roster read is still one read ══════════════════════════════════════

async def test_the_family_roster_is_read_at_most_once_per_request(monkeypatch):
    event = _event("San Francisco Giants", "Minnesota Twins", sport_key="baseball_mlb", sport_id=MLB)
    npb = _make_market(id=NPB_TITLE, name="Japan NPB Champion", source="kalshi")
    ws = _make_market(id=WS_POLY, name="MLB World Series Champion 2026", source="polymarket")
    outcomes = [
        _outcome(64406477, npb, "Yomiuri Giants", 0.08),
        _outcome(1634483, ws, "San Francisco Giants", 0.001),
    ]
    session = _session(event, outcomes, roster=BASEBALL, home_team_id=6609, away_team_id=10739,
                       sport_ids=[MLB, NPB, KBO])
    await _get(monkeypatch, session, event.id)
    assert session.roster_reads["n"] == 1
