"""#8052 — an Angels page stops printing the DODGERS' numbers as the Angels'.

WHAT A READER SAW, production 2026-09-22 17:1xZ, `https://bainluck.com/events/15316874`
(Athletics vs Los Angeles Angels). The "Bigger Picture" card headed
**Angels · 60–96 · #5 West** read, top to bottom:

    World Series Champion    31%     <- the DODGERS' number
    NL Champion              41%     <- the DODGERS' number, on an AL club
    World Series Champion     0%     <- the Angels' own
    AL Champion              <1%
    Make MLB Playoffs         0%

and on the Dodgers' own page the same hour (`/events/15316961`,
`/api/events/15316961/related-futures`) the mirror image: `home_team_futures`
carried the ANGELS' `al_west`, `al_champion`, `world_series_champion`,
`make_mlb_playoffs` and fifteen `Los Angeles A vs …` World Series legs, and the
Dodgers card showed **no "Make Playoffs" line at all** while the Padres card
beside it read 98%.

WHY. `_team_name_patterns("Los Angeles Dodgers")` emits a bare `Los Angeles`,
because Kalshi labels teams by city (`Texas`, `Houston`, `Seattle`). In a
two-club city that pattern cannot tell the clubs apart, so Kalshi's truncated
`Los Angeles A` — the Angels — occupies whole tokens of the Dodgers' patterns
and the name fallback admits it. Symmetric by construction, and not MLB-only:
`Chicago C` matches the White Sox's patterns, `New York M` the Yankees'.

AND WHY IT DELETES A ROW RATHER THAN ADDING ONE. `dedup_by_merge_group` keys the
per-team groups (`make_mlb_playoffs`, division winners) on `merge_group` ALONE,
so both admitted rows of one group collapse to one and the tie-break —
freshness, then liquidity — knows nothing about which club the page is for. In
market 266 (`Pro Baseball Playoff Qualifiers`) the Angels' row is `0.000` and the
Dodgers' is `1.000`; the Angels' won.

═══ THE FIXTURE IS PRODUCTION'S OWN ═══

Team ids, abbreviations and `alternate_names` are the production `teams` rows
read 2026-09-22 (`10707` Dodgers / `LAD` / `['Dodgers', 'Los Angeles']`, `10712`
Angels / `LAA` / `['Los Angeles', 'Angels']`, `10715` Astros, `10716` Marlins,
`10745` Padres). Market 266 and its two outcome tickers
`KXMLBPLAYOFFS-26-LAD` / `KXMLBPLAYOFFS-26-LAA` with `1.000` / `0.000` are the
production rows. The `events`, `futures_markets` and `futures_outcomes` objects
are SYNTHETIC (the MagicMock harness `test_route_related_futures.py` provides,
reused by #7851); outcome ids are invented.

═══ ONE MUTATION SURVIVES, AND IT IS UNREACHABLE RATHER THAN UNGUARDED ═══

`artifacts-lane1-599/convict_8052_guards.py` runs six mutations of the fix and
convicts five. The survivor is "arm the veto even when neither team resolved"
(dropping the `all_team_ids` clause). It survives because the roster read is
ITSELF gated on `all_team_ids`, so with no resolved team there is no index, no
claimed team and nothing for the clause to decide — it is belt-and-braces for a
future caller that loads the index earlier, not live logic. Recorded here rather
than chased with a test that would have to fake a state the route cannot reach.

═══ WHAT THE CONTROLS ARE FOR ═══

The failure this guard can cause is worse than the defect: a veto aimed one
token too wide empties the section. So four of the seven arms below are
refusals-to-refuse — a single-club city, a silent ticker, a matchup ticker that
names this event's club alongside another, and an event whose teams do not
resolve to `teams` rows at all (there the veto must never arm, because there is
nothing to compare against).
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

# A fresh event id per route call: the route memoises bodies per event id
# (`_related_futures_cache`), so a reused id would hand one test another test's
# body. Same reason #7851 does it.
_EVENT_IDS = itertools.count(8052001)

DODGERS, ANGELS, ASTROS, MARLINS, PADRES = 10707, 10712, 10715, 10716, 10745

# The production `teams` rows for this sport, as the roster read returns them.
_ROSTER = [
    (DODGERS, "Los Angeles Dodgers", "LAD", "Los Angeles", ["Dodgers", "Los Angeles"]),
    (ANGELS, "Los Angeles Angels", "LAA", "Los Angeles", ["Los Angeles", "Angels"]),
    (ASTROS, "Houston Astros", "HOU", "Houston", ["Houston", "Astros"]),
    (MARLINS, "Miami Marlins", "MIA", "Miami", ["Marlins", "Miami"]),
    (PADRES, "San Diego Padres", "SD", "San Diego", ["San Diego", "Padres"]),
]


def _fresh_event_id() -> int:
    return next(_EVENT_IDS)


def _mlb_event(home: str, away: str):
    ev = _make_event(
        id=_fresh_event_id(),
        home_team=home,
        away_team=away,
        status="scheduled",
        sport_key="baseball_mlb",
    )
    ev.sport.name = "Baseball"
    ev.sport_id = 53232
    return ev


def _outcome(id, market, name, probability, *, ticker=None, team_id=None):
    o = _make_outcome(
        id=id,
        market=market,
        name=name,
        probability=probability,
        probability_change_24h=0.0,
    )
    o.external_id = ticker
    o.team_id = team_id
    return o


def _roster_rows():
    return [
        SimpleNamespace(
            id=tid,
            # #7867 widened the roster read to the sport family and selects
            # `sport_id` to partition it; every row here is the event's own
            # league, so the partition is the identity and the seven arms below
            # are unchanged.
            sport_id=53232,
            name=name,
            abbreviation=abbrev,
            location=location,
            alternate_names=list(alts),
            logo_url_small=None,
            logo_url=None,
        )
        for tid, name, abbrev, location, alts in _ROSTER
    ]


def _team_row(team_id):
    return SimpleNamespace(id=team_id, alternate_names=[], roster_players=[])


def _session(event, outcomes, *, home_team_id, away_team_id, roster=True):
    """Mock DB session: the route's own queries, answered by statement text.

    `roster=False` is the "neither team resolves" arm — the route finds no
    `teams` row for either side, exactly as #7851's session does, and the veto
    must stay disarmed.
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    market_ids = sorted({o.market.id for o in outcomes})
    # The route asks for the home team first, then the away team.
    per_team = iter(
        [_team_row(home_team_id), _team_row(away_team_id)] if roster else [None, None]
    )

    async def mock_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower()
        if "from events" in stmt_str:
            return _MockResult(scalar=event)
        if "select sports.id" in stmt_str:
            return _MockResult(rows=[SimpleNamespace(id=53232)])
        if "from teams" in stmt_str:
            # The sport-wide roster read (it alone selects the logo columns).
            if "teams.logo_url" in stmt_str:
                return _MockResult(rows=_roster_rows() if roster else [])
            # The two per-team lookups select `teams.id`; the award-headshot
            # supplement selects only `teams.roster_players`.
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


def _served(body):
    return body["home_team_futures"] + body["away_team_futures"]


def _names(body):
    return [r["outcome_name"] for r in _served(body)]


# ── the production markets ───────────────────────────────────────────────────

PLAYOFFS_ID = 266
AL_WEST_ID = 271
WS_ID = 60000271


def _playoff_market():
    return _make_market(
        id=PLAYOFFS_ID, name="Pro Baseball Playoff Qualifiers", source="kalshi"
    )


def _al_west_market():
    return _make_market(id=AL_WEST_ID, name="AL West Division Winner", source="kalshi")


def _ws_market():
    return _make_market(id=WS_ID, name="World Series Matchup", source="kalshi")


# ── the defect ───────────────────────────────────────────────────────────────


async def test_the_angels_al_west_row_does_not_join_the_dodgers(monkeypatch):
    """`Los Angeles A` is the Angels and belongs on no Dodgers page."""
    event = _mlb_event("Los Angeles Dodgers", "San Diego Padres")
    outcomes = [
        _outcome(80520001, _al_west_market(), "Los Angeles A", 0.001,
                 ticker="KXMLBALWEST-26-LAA", team_id=ANGELS),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, home_team_id=DODGERS, away_team_id=PADRES),
        event.id,
    )
    assert "Los Angeles A" not in _names(body)
    assert _served(body) == []


async def test_the_dodgers_own_playoff_row_is_the_one_served(monkeypatch):
    """The displacement, which is what the reader actually loses.

    Both rows of market 266 reach the candidate net; they share one merge group
    and `dedup_by_merge_group` keeps exactly one. Before the veto the Angels'
    0.000 won and a club that had clinched showed nothing.
    """
    market = _playoff_market()
    event = _mlb_event("Los Angeles Dodgers", "San Diego Padres")
    outcomes = [
        # Angels first, which is the order that produced the defect.
        _outcome(80520002, market, "Los Angeles A", 0.0,
                 ticker="KXMLBPLAYOFFS-26-LAA", team_id=ANGELS),
        _outcome(80520003, market, "Los Angeles D", 1.0,
                 ticker="KXMLBPLAYOFFS-26-LAD", team_id=DODGERS),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, home_team_id=DODGERS, away_team_id=PADRES),
        event.id,
    )
    served = _served(body)
    assert [r["outcome_name"] for r in served] == ["Los Angeles D"]
    assert served[0]["probability"] == 1.0


async def test_the_dodgers_rows_do_not_join_the_angels_page(monkeypatch):
    """The symmetric half — the one a reader saw on 2026-09-22."""
    event = _mlb_event("Athletics", "Los Angeles Angels")
    outcomes = [
        _outcome(80520004, _al_west_market(), "Los Angeles D", 0.41,
                 ticker="KXMLBNLWEST-26-LAD", team_id=DODGERS),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, home_team_id=11494, away_team_id=ANGELS),
        event.id,
    )
    assert "Los Angeles D" not in _names(body)


# ── the controls: four ways this veto must refuse to fire ────────────────────


async def test_a_crosswise_stored_team_id_does_not_rescue_the_sibling(monkeypatch):
    """The ticker outranks `futures_outcomes.team_id`, and it has to.

    #2010 measured that column wrong on 11.6% of ticker-derivable Kalshi
    outcomes and wrong toward the CITY SIBLING every time — `Los Angeles D`
    stored as the Angels, `New York M` stored as the Yankees. An implementation
    that trusted the stored id here would admit the sibling row and veto the
    right club: the precise inversion. So this row carries the Dodgers' id on
    the Angels' ticker, which is production's shape, and it must still be
    refused on the Dodgers' page.
    """
    event = _mlb_event("Los Angeles Dodgers", "San Diego Padres")
    outcomes = [
        _outcome(80520013, _al_west_market(), "Los Angeles A", 0.001,
                 ticker="KXMLBALWEST-26-LAA", team_id=DODGERS),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, home_team_id=DODGERS, away_team_id=PADRES),
        event.id,
    )
    assert _served(body) == []


async def test_the_polymarket_row_that_printed_31_percent_is_refused(monkeypatch):
    """THE SPECIMEN A READER SAW, and the reason a ticker rule alone is not enough.

    The two lines at the top of the Angels' card came from POLYMARKET rows
    labelled `Los Angeles Dodgers` and keyed by a hex condition id. No ticker
    rule can reach them; the exact alias can.
    """
    event = _mlb_event("Athletics", "Los Angeles Angels")
    poly_ws = _make_market(id=199100, name="MLB: 2026 World Series Champion",
                           source="polymarket")
    poly_nl = _make_market(id=199101, name="MLB: 2026 NL Champion", source="polymarket")
    outcomes = [
        _outcome(80520010, poly_ws, "Los Angeles Dodgers", 0.30525,
                 ticker="0x749d8eccbc0a99447e71fc5e40a0096842774b"),
        _outcome(80520011, poly_nl, "Los Angeles Dodgers", 0.41,
                 ticker="0x07d6d1ac69e705071cfaa10ab950f8231dc3de"),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, home_team_id=11494, away_team_id=ANGELS),
        event.id,
    )
    assert _served(body) == []


async def test_an_alias_two_clubs_share_still_falls_through(monkeypatch):
    """`Los Angeles` is an `alternate_names` entry on BOTH LA clubs.

    The index drops such an alias rather than ranking it, so it resolves to
    nothing and the row keeps exactly the name-matching behaviour it has today.
    That coin flip is a different defect (#7230) and this guard does not claim
    it — asserted so a later reader knows the silence is deliberate.
    """
    event = _mlb_event("Los Angeles Dodgers", "San Diego Padres")
    outcomes = [
        _outcome(80520012, _al_west_market(), "Los Angeles", 0.5, ticker=None),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, home_team_id=DODGERS, away_team_id=PADRES),
        event.id,
    )
    assert _names(body) == ["Los Angeles"]


async def test_a_single_club_city_is_untouched(monkeypatch):
    """Houston is exactly the label the bare-city pattern exists for."""
    event = _mlb_event("Houston Astros", "Miami Marlins")
    outcomes = [
        _outcome(80520005, _al_west_market(), "Houston", 0.405,
                 ticker="KXMLBALWEST-26-HOU", team_id=ASTROS),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, home_team_id=ASTROS, away_team_id=MARLINS),
        event.id,
    )
    assert _names(body) == ["Houston"]


async def test_a_ticker_that_names_no_team_keeps_the_name_fallback(monkeypatch):
    """Polymarket's hex condition ids, player props, threshold ladders.

    Silence is "this ticker does not name a team", never "no team" — so the row
    is classified exactly as it was before this guard existed.
    """
    event = _mlb_event("Los Angeles Dodgers", "San Diego Padres")
    poly = _make_market(id=199065, name="MLB: 2026 AL West Champion", source="polymarket")
    outcomes = [
        _outcome(80520006, poly, "Los Angeles Dodgers", 0.3,
                 ticker="0xc78136b44e5f7e90751db373d4ef6aac4320a94e"),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, home_team_id=DODGERS, away_team_id=PADRES),
        event.id,
    )
    assert _names(body) == ["Los Angeles Dodgers"]


async def test_a_matchup_ticker_naming_this_club_and_another_is_admitted(monkeypatch):
    """`resolve_row_team_id` refuses a two-team ticker; membership must not.

    "Angels vs Dodgers" is a Dodgers row on a Dodgers page. Only a matchup
    naming NEITHER of this event's clubs is refused — the fifteen
    `Los Angeles A vs …` legs that were on the Dodgers' page are that shape.
    """
    event = _mlb_event("Los Angeles Dodgers", "San Diego Padres")
    ws = _ws_market()
    outcomes = [
        _outcome(80520007, ws, "Los Angeles A vs Los Angeles D", 0.002,
                 ticker="KXMLBWS-26-LAA-LAD"),
        _outcome(80520008, ws, "Los Angeles A vs Miami", 0.002,
                 ticker="KXMLBWS-26-LAA-MIA"),
    ]
    body = await _get(
        monkeypatch,
        _session(event, outcomes, home_team_id=DODGERS, away_team_id=PADRES),
        event.id,
    )
    assert _names(body) == ["Los Angeles A vs Los Angeles D"]


async def test_an_event_whose_teams_do_not_resolve_keeps_todays_payload(monkeypatch):
    """No `teams` row for either side ⇒ nothing to compare against ⇒ no veto.

    This is the arm that makes the change additive. An event whose names do not
    match a roster row keeps the name fallback it has today, wrong-city rows and
    all — fixing those is not this guard's business and silently emptying the
    section would be far worse than the defect.
    """
    event = _mlb_event("Los Angeles Dodgers", "San Diego Padres")
    outcomes = [
        _outcome(80520009, _al_west_market(), "Los Angeles A", 0.001,
                 ticker="KXMLBALWEST-26-LAA"),
    ]
    body = await _get(
        monkeypatch,
        _session(
            event, outcomes, home_team_id=DODGERS, away_team_id=PADRES, roster=False
        ),
        event.id,
    )
    assert _names(body) == ["Los Angeles A"]
