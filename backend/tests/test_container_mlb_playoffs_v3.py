"""One MLB postseason assembles from ESPN's postseason stamp, by ESPN id. #9650 (v3).

The positive corpus is REAL: `PHI_ATL_G2` is ESPN's
`baseball/mlb/scoreboard?dates=20260930` entry for event 401907972 (Phillies at
Braves, NLWC Game 2), read 2026-09-28 05:3xZ and banked in
`test_certain_postseason_games_9216.py`; it is parsed here through the shipped
`ESPNAPIService._parse_event`. Our event ids and market ids/tickers are the
production ones in `fixtures/sports_series_game_order_9602.json` (the
2026-09-29 11:12Z `/api/feed` capture): PHI@ATL Game 1 = event 15320289
(Kalshi 62924885, Polymarket 63026432), Game 2 = 15320701 (Kalshi 62924881),
CWS@HOU Game 2 = 15320702 (Kalshi 62924880).

Where a control needs a shape the capture does not hold — Game 1, the "If
Necessary" Game 3, the AL series, last October, a September regular-season game
— it is DERIVED from the one real entry by changing the fields the test names,
and the ESPN id is the real one where #9216 recorded it (401907965 Game 1,
401907897 CWS@HOU Game 2). Our event and market rows are test doubles keyed on
those real ids; no production row is read.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.services.espn_api import ESPNAPIService
from app.tasks.container_assembly import SOURCE_CONFIDENCE, UNDO_LINE
from app.tasks.container_mlb_playoffs_assembly import (
    EVENTS_FOR_ESPN_IDS_SQL,
    MARKETS_FOR_EVENTS_SQL,
    MAX_BOARD_DAYS,
    UNIDENTIFIED_IN_SPAN_SQL,
    assemble_mlb_postseason,
    board_days,
    gather_mlb_postseason_candidates,
    run_mlb_postseason_assembly,
)
from app.utils.container_mlb_playoffs import (
    EXCLUDED_CONFLICTING_IDENTITY,
    EXCLUDED_DUPLICATE_EVENT_ROWS,
    EXCLUDED_GAME_WINNER_MARKET,
    EXCLUDED_MARKET_ON_DUPLICATE,
    EXCLUDED_NO_ESPN_ID,
    EXCLUDED_NO_SEASON_TYPE,
    EXCLUDED_NOT_POSTSEASON,
    EXCLUDED_OTHER_SEASON,
    EXCLUDED_PLACEHOLDER,
    INCOMPLETE_BOARD_DAY_DARK,
    INCOMPLETE_CONFLICTING_IDENTITY,
    INCOMPLETE_DUPLICATE_ROWS,
    INCOMPLETE_MARKETS_TRUNCATED,
    INCOMPLETE_NO_EVENT_ROW,
    INCOMPLETE_STRANDED_QUESTIONS,
    NOT_YET_CERTAIN,
    UNAVAILABLE_BOARDS_DARK,
    UNAVAILABLE_NO_BOARD_DAYS,
    UNAVAILABLE_NO_EVENT_ROW,
    UNAVAILABLE_NO_POSTSEASON_GAMES,
    EventRow,
    MarketRow,
    MlbPostseason,
    mlb_season_for_date,
    resolve_postseason_members,
    select_postseason_games,
)
from tests.test_certain_postseason_games_9216 import PHI_ATL_G2

POST_2026 = MlbPostseason(2026)

G1_ESPN, G2_ESPN, G3_ESPN = "401907965", "401907972", "401907973"
CWS_HOU_G2_ESPN = "401907897"
REGULAR_ESPN = "401800924"  # DERIVED id
LAST_YEAR_ESPN = "401700001"  # DERIVED id

G1_EVENT, G2_EVENT, CWS_HOU_G2_EVENT = 15320289, 15320701, 15320702


def _derive(espn_id, date_iso, headline, *, season=None, series=None, teams=None):
    """A board entry DERIVED from the real PHI@ATL Game 2 entry."""
    p = copy.deepcopy(PHI_ATL_G2)
    p["id"] = espn_id
    p["date"] = date_iso
    comp = p["competitions"][0]
    comp["notes"][0]["headline"] = headline
    if season is not None:
        p["season"] = season
    if series == "none":
        del comp["series"]
        comp["notes"] = []
    elif series:
        comp["series"].update(series)
    if teams:
        away, home = teams
        for c in comp["competitors"]:
            name = home if c["homeAway"] == "home" else away
            c["team"] = {**c["team"], "displayName": name, "name": name.split()[-1]}
    return p


def _parse(payload):
    ee = ESPNAPIService()._parse_event(payload)
    assert ee is not None
    return ee


@pytest.fixture(scope="module")
def g2():
    return _parse(PHI_ATL_G2)


@pytest.fixture(scope="module")
def corpus(g2):
    """Board entries by name: the real Game 2 and its derived siblings."""
    return {
        "g1": _parse(_derive(G1_ESPN, "2026-09-29T18:00Z", "NLWC - Game 1")),
        "g2": g2,
        "g3": _parse(_derive(G3_ESPN, "2026-10-01T18:00Z", "NLWC - Game 3 If Necessary")),
        "cws_hou_g2": _parse(
            _derive(
                CWS_HOU_G2_ESPN,
                "2026-09-30T21:00Z",
                "ALWC - Game 2",
                teams=("Chicago White Sox", "Houston Astros"),
            )
        ),
        # DERIVED: the same clubs in September, which ESPN files as type 2.
        "regular": _parse(
            _derive(
                REGULAR_ESPN,
                "2026-09-24T23:15Z",
                "",
                season={"year": 2026, "type": 2, "slug": "regular-season"},
                series="none",
            )
        ),
        # DERIVED: last October's playoff game between the same clubs.
        "last_year": _parse(
            _derive(
                LAST_YEAR_ESPN,
                "2025-10-01T18:00Z",
                "NLWC - Game 1",
                season={"year": 2025, "type": 3, "slug": "post-season"},
                series={"completed": True, "competitors": [{"wins": 2}, {"wins": 0}]},
            )
        ),
    }


def _boards(corpus, names_by_day=None):
    names_by_day = names_by_day or {
        "20260929": ["g1"],
        "20260930": ["g2", "cws_hou_g2"],
        "20261001": ["g3"],
    }
    return [(day, [corpus[n] for n in names]) for day, names in names_by_day.items()]


# --- the corpus, checked before anything leans on it --------------------------


def test_the_real_entry_is_a_postseason_game_two(g2):
    assert g2.espn_id == G2_ESPN
    assert g2.season_type == 3
    assert g2.playoff_series.game_number == 2
    assert g2.date == datetime(2026, 9, 30, 18, 0, tzinfo=timezone.utc)
    assert g2.home_team.display_name == "Atlanta Braves"


def test_the_derived_siblings_carry_the_fields_they_claim(corpus):
    assert corpus["regular"].season_type == 2 and corpus["regular"].playoff_series is None
    assert corpus["last_year"].season_type == 3 and corpus["last_year"].date.year == 2025
    assert corpus["g3"].playoff_series.game_number == 3
    assert corpus["cws_hou_g2"].home_team.display_name == "Houston Astros"


def test_a_season_is_its_calendar_year_and_the_slug_names_it():
    assert mlb_season_for_date(datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc)) == 2026
    assert mlb_season_for_date(datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc)) == 2026
    assert POST_2026.slug == "mlb-2026-postseason"
    assert POST_2026.display_name == "MLB 2026 Postseason"
    with pytest.raises(ValueError):
        MlbPostseason(26)


# --- selection: ESPN's postseason stamp, this season only ----------------------


def test_the_postseason_is_exactly_espns_type_3_games_of_the_season(corpus):
    boards = _boards(
        corpus,
        {
            "20260924": ["regular"],
            "20260929": ["g1", "last_year"],
            "20260930": ["g2", "cws_hou_g2"],
            "20261001": ["g3"],
        },
    )
    selection = select_postseason_games(boards, POST_2026)
    assert selection.unavailable is None
    assert {g.espn_id for g in selection.games} == {G1_ESPN, G2_ESPN, G3_ESPN, CWS_HOU_G2_ESPN}
    assert [r["espn_id"] for r in selection.excluded[EXCLUDED_NOT_POSTSEASON]] == [REGULAR_ESPN]
    assert [r["espn_id"] for r in selection.excluded[EXCLUDED_OTHER_SEASON]] == [LAST_YEAR_ESPN]
    certain = {g.espn_id: (g.certain, g.certainty_reason) for g in selection.games}
    assert certain[G1_ESPN] == (True, "within_wins_needed")
    assert certain[G3_ESPN] == (False, "if_necessary")
    # Every id the boards named is accounted for, regular season included.
    assert selection.listed_ids >= {REGULAR_ESPN, LAST_YEAR_ESPN, G1_ESPN}


def test_last_octobers_game_belongs_to_last_octobers_postseason(corpus):
    selection = select_postseason_games(
        [("20251001", [corpus["last_year"]]), ("20260930", [corpus["g2"]])], MlbPostseason(2025)
    )
    assert [g.espn_id for g in selection.games] == [LAST_YEAR_ESPN]
    assert [r["espn_id"] for r in selection.excluded[EXCLUDED_OTHER_SEASON]] == [G2_ESPN]


def test_a_played_game_is_owed_whatever_the_series_says(corpus):
    played = replace(corpus["g3"], status="post")
    [game] = select_postseason_games([("20261001", [played])], POST_2026).games
    assert (game.certain, game.certainty_reason) == (True, "played")


def test_entries_without_identity_are_refused_and_named(corpus):
    no_id = replace(corpus["g1"], espn_id="")
    no_type = replace(corpus["g1"], espn_id="401900001", season_type=None)
    no_date = replace(corpus["g1"], espn_id="401900002", date=None)
    tbd = replace(
        corpus["g1"], espn_id="401900003", home_team=replace(corpus["g1"].home_team, display_name="TBD", name="TBD")
    )
    selection = select_postseason_games(
        [("20260929", [no_id, no_type, no_date, tbd, corpus["g2"]])], POST_2026
    )
    assert [g.espn_id for g in selection.games] == [G2_ESPN]
    assert len(selection.excluded[EXCLUDED_NO_ESPN_ID]) == 1
    assert [r["espn_id"] for r in selection.excluded[EXCLUDED_NO_SEASON_TYPE]] == ["401900001"]
    assert [r["espn_id"] for r in selection.excluded["no_season_evidence"]] == ["401900002"]
    assert [r["espn_id"] for r in selection.excluded[EXCLUDED_PLACEHOLDER]] == ["401900003"]


def test_one_id_listed_as_two_identities_has_none(corpus):
    # DERIVED: Game 2's id served again stamped regular season.
    relabelled = replace(corpus["g2"], season_type=2)
    selection = select_postseason_games(
        [("20260929", [corpus["g1"]]), ("20260930", [corpus["g2"], relabelled])], POST_2026
    )
    assert G2_ESPN not in {g.espn_id for g in selection.games}
    assert selection.withheld == [G2_ESPN]
    assert [r["espn_id"] for r in selection.excluded[EXCLUDED_CONFLICTING_IDENTITY]] == [G2_ESPN]


def test_a_repeated_identical_entry_is_one_game(corpus):
    selection = select_postseason_games(
        [("20260930", [corpus["g2"]]), ("20261001", [corpus["g2"]])], POST_2026
    )
    assert [g.espn_id for g in selection.games] == [G2_ESPN]


@pytest.mark.parametrize(
    ("boards", "reason"),
    [
        ([], UNAVAILABLE_NO_BOARD_DAYS),
        ([("20260929", None), ("20260930", None)], UNAVAILABLE_BOARDS_DARK),
        ([("20260929", []), ("20260930", [])], UNAVAILABLE_NO_POSTSEASON_GAMES),
    ],
)
def test_we_could_not_tell_is_never_an_empty_postseason(boards, reason):
    assert select_postseason_games(boards, POST_2026).unavailable == reason


def test_a_regular_season_slate_is_not_a_postseason(corpus):
    selection = select_postseason_games([("20260924", [corpus["regular"]])], POST_2026)
    assert selection.unavailable == UNAVAILABLE_NO_POSTSEASON_GAMES


# --- members: our rows, joined by ESPN id ---------------------------------------


def _rows(*, include=(G1_EVENT, G2_EVENT, CWS_HOU_G2_EVENT)):
    catalogue = {
        G1_EVENT: EventRow(G1_EVENT, G1_ESPN, "scheduled", datetime(2026, 9, 29, 18, 0, tzinfo=timezone.utc), "Atlanta Braves", "Philadelphia Phillies"),
        G2_EVENT: EventRow(G2_EVENT, G2_ESPN, "scheduled", datetime(2026, 9, 30, 18, 0, tzinfo=timezone.utc), "Atlanta Braves", "Philadelphia Phillies"),
        CWS_HOU_G2_EVENT: EventRow(CWS_HOU_G2_EVENT, CWS_HOU_G2_ESPN, "scheduled", datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc), "Houston Astros", "Chicago White Sox"),
    }
    return [catalogue[i] for i in include]


def _markets():
    # "binary" is a test double, not a `market_shape` value, so these rows run
    # the plumbing as questions. The game-winner rule (`container_game_winner`)
    # is graded on the REAL stored shapes in `_game_one_board()` below.
    return [
        MarketRow(62924880, CWS_HOU_G2_EVENT, "White Sox at Astros", "KXMLBGAME-26SEP301700CWSHOU", "kalshi", "binary", "open"),
        MarketRow(62924881, G2_EVENT, "Phillies at Braves", "KXMLBGAME-26SEP301400PHIATL", "kalshi", "binary", "open"),
        MarketRow(62924885, G1_EVENT, "Phillies at Braves", "KXMLBGAME-26SEP291400PHIATL", "kalshi", "binary", "open"),
        MarketRow(63026432, G1_EVENT, "Phillies vs. Braves", "0x4b89caf655c9602405a1c0366a1de9cc976f88d3b85ff69a808754ed2e81f36b", "polymarket", "binary", "open"),
    ]


def test_members_are_espns_games_we_hold_and_their_questions(corpus):
    selection = select_postseason_games(_boards(corpus), POST_2026)
    members = resolve_postseason_members(selection, _rows(), _markets() + [MarketRow(1, 999, "x", "X", "kalshi", "binary", "open")])
    events = [c for c in members.candidates if c.child_type == "event"]
    markets = [c for c in members.candidates if c.child_type == "market"]
    assert {c.child_id for c in events} == {G1_EVENT, G2_EVENT, CWS_HOU_G2_EVENT}
    assert {c.external_id for c in events} == {G1_ESPN, G2_ESPN, CWS_HOU_G2_ESPN}
    assert [c.child_id for c in markets] == [62924880, 62924881, 62924885, 63026432]
    assert {c.market_source for c in markets if c.child_id in (62924885, 63026432)} == {"kalshi", "polymarket"}
    # Game 3 is listed "If Necessary" and we hold no row: not owed yet.
    assert members.unavailable == []
    assert [(g["espn_id"], g["reason"]) for g in members.not_yet_certain] == [(G3_ESPN, NOT_YET_CERTAIN)]


def test_a_certain_game_with_no_row_is_a_gap_never_fabricated(corpus):
    selection = select_postseason_games(_boards(corpus), POST_2026)
    members = resolve_postseason_members(selection, _rows(include=(G1_EVENT, G2_EVENT)), _markets())
    [gap] = members.unavailable
    assert (gap["espn_id"], gap["reason"]) == (CWS_HOU_G2_ESPN, UNAVAILABLE_NO_EVENT_ROW)
    assert CWS_HOU_G2_EVENT not in {c.child_id for c in members.candidates}
    assert 62924880 not in {c.child_id for c in members.candidates}


def test_two_rows_holding_one_espn_id_admit_neither(corpus):
    # Defensive: `uq_events_espn_id` forbids this on production.
    selection = select_postseason_games(_boards(corpus), POST_2026)
    twin = EventRow(9000, G2_ESPN, "scheduled", None, "Atlanta Braves", "Philadelphia Phillies")
    markets = _markets() + [MarketRow(7, 9000, "x", "X", "kalshi", "binary", "open")]
    members = resolve_postseason_members(selection, _rows() + [twin], markets)
    ids = {c.child_id for c in members.candidates}
    assert G2_EVENT not in ids and 9000 not in ids and 62924881 not in ids
    [dup] = members.excluded[EXCLUDED_DUPLICATE_EVENT_ROWS]
    assert sorted(dup["event_ids"]) == [9000, G2_EVENT]
    assert {m["market_id"] for m in members.excluded[EXCLUDED_MARKET_ON_DUPLICATE]} == {7, 62924881}


# --- the adapter feeding the shared pipeline ------------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Session:
    """Answers the adapter's three reads and `assemble_container`'s existence
    probes from in-memory rows, and records every write. Anything else is a
    query this test did not expect, and fails it."""

    def __init__(self, events, markets, unidentified=(), live_markets=None):
        self.events = list(events)
        self.markets = list(markets)
        self.unidentified = list(unidentified)
        self.live_markets = live_markets
        self.writes = []
        self.reads = []
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = getattr(stmt, "text", None)
        if sql is None:
            self.writes.append(stmt)
            return _Result([])
        self.reads.append((sql, params))
        # Composition with #9651 / #9217 (authority): assemble_container asks
        # whether the correction ledger is migrated (answered: not here, the
        # old pass) and which markets' receipts another phase owns (none).
        if sql.startswith("SELECT to_regclass('public.container_corrections')"):
            self.reads.pop()
            return _Result([(False, False)])
        if sql.startswith("SELECT market_id FROM market_match_receipts"):
            self.reads.pop()
            return _Result([])
        if sql == EVENTS_FOR_ESPN_IDS_SQL:
            ids = set(params["espn_ids"])
            return _Result([self._event(r) for r in self.events if r.espn_id in ids])
        if sql == MARKETS_FOR_EVENTS_SQL:
            ids = set(params["event_ids"])
            return _Result(
                [
                    (m.id, m.event_id, m.name, m.external_id, m.source, m.market_type, m.status)
                    for m in sorted(self.markets, key=lambda m: m.id)
                    if m.event_id in ids
                ][: params["limit"]]
            )
        if sql == UNIDENTIFIED_IN_SPAN_SQL:
            listed = set(params["listed_ids"])
            return _Result(
                [
                    self._event(r) + (sum(1 for m in self.markets if m.event_id == r.id),)
                    for r in self.unidentified
                    if r.espn_id is None or r.espn_id not in listed
                ]
            )
        if sql.startswith("SELECT id FROM events WHERE id = ANY"):
            known = {r.id for r in self.events}
            return _Result([(i,) for i in params["ids"] if i in known])
        if sql.startswith("SELECT id FROM futures_markets WHERE id = ANY"):
            live = self.live_markets if self.live_markets is not None else {m.id for m in self.markets}
            return _Result([(i,) for i in params["ids"] if i in live])
        raise AssertionError(f"unexpected query: {sql}")

    async def commit(self):  # pragma: no cover — the adapter must never reach it
        self.committed = True

    @staticmethod
    def _event(r):
        return (r.id, r.espn_id, r.status, r.commence_time, r.home, r.away)


class _Container:
    def __init__(self, slug=POST_2026.slug, id=91):
        self.id = id
        self.slug = slug


def _edge_rows(session):
    """The `event_edges` rows the shared upsert was handed, compiled as Postgres
    would receive them."""
    edges = []
    for stmt in session.writes:
        if getattr(stmt.table, "name", None) != "event_edges":
            continue
        params = stmt.compile(dialect=postgresql.dialect()).params
        n = 0
        while f"child_id_m{n}" in params or (n == 0 and "child_id" in params):
            suffix = f"_m{n}" if f"child_id_m{n}" in params else ""
            edges.append(
                {
                    k: params[f"{k}{suffix}"]
                    for k in ("parent_type", "parent_id", "child_type", "child_id", "kind", "source", "confidence")
                }
            )
            n += 1
            if not suffix:
                break
    return edges


#: DERIVED: the Odds API twin of Game 2 — same game, its own row, no ESPN id.
ODDS_TWIN = EventRow(15320777, None, "scheduled", datetime(2026, 9, 30, 18, 0, tzinfo=timezone.utc), "Atlanta Braves", "Philadelphia Phillies")


@pytest.mark.asyncio
async def test_a_whole_postseason_read_is_complete(corpus):
    # CONTROL: every clause below must be able to flip this to partial.
    session = _Session(_rows(), _markets())
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, apply=True)
    assert report["terminal"] == "complete"
    assert report["reason"] is None and report["incomplete"] == []
    edges = _edge_rows(session)
    assert {e["child_id"] for e in edges if e["child_type"] == "event"} == {G1_EVENT, G2_EVENT, CWS_HOU_G2_EVENT}
    assert {e["child_id"] for e in edges if e["child_type"] == "market"} == {62924880, 62924881, 62924885, 63026432}
    assert all(e["parent_type"] == "container" and e["parent_id"] == 91 and e["kind"] == "contains" for e in edges)
    assert {e["source"] for e in edges if e["child_type"] == "event"} == {"authority_tournament_id"}
    assert {float(e["confidence"]) for e in edges if e["child_type"] == "event"} == {SOURCE_CONFIDENCE["authority_tournament_id"]}
    assert report["assembly"]["edges_written"] == 7
    assert [g["espn_id"] for g in report["not_yet_certain"]] == [G3_ESPN]
    assert report["undo"]["edges"] == UNDO_LINE
    assert session.committed is False


@pytest.mark.asyncio
async def test_a_dry_run_writes_nothing_and_still_reports(corpus):
    session = _Session(_rows(), _markets())
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026)
    assert session.writes == [] and "assembly" not in report
    assert report["harvest"]["candidates"] == {"event": 3, "market": 4}
    assert report["terminal"] == "complete"


@pytest.mark.asyncio
async def test_a_certain_game_missing_its_row_is_partial_and_keeps_the_rest(corpus):
    session = _Session(_rows(include=(G1_EVENT, G2_EVENT)), _markets())
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, apply=True)
    assert report["terminal"] == "partial"
    assert report["incomplete"] == [INCOMPLETE_NO_EVENT_ROW]
    assert [g["espn_id"] for g in report["games_without_event_row"]] == [CWS_HOU_G2_ESPN]
    assert {e["child_id"] for e in _edge_rows(session) if e["child_type"] == "event"} == {G1_EVENT, G2_EVENT}


@pytest.mark.asyncio
async def test_a_twin_holding_questions_makes_the_postseason_partial(corpus):
    twin_market = MarketRow(62999999, ODDS_TWIN.id, "Phillies vs Braves", "odds:x", "polymarket", "binary", "open")
    session = _Session(_rows(), _markets() + [twin_market], unidentified=[ODDS_TWIN])
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, apply=True)
    assert report["terminal"] == "partial"
    assert report["incomplete"] == [INCOMPLETE_STRANDED_QUESTIONS]
    assert report["unidentified_in_span"] == [
        {
            "event_id": ODDS_TWIN.id,
            "teams": ["Philadelphia Phillies", "Atlanta Braves"],
            "commence_time": "2026-09-30T18:00:00+00:00",
            "status": "scheduled",
            "espn_id": None,
            "markets": 1,
        }
    ]
    # Named, never admitted — by name and minute it IS Game 2, and that is
    # exactly the evidence membership may not use.
    ids = {e["child_id"] for e in _edge_rows(session)}
    assert ODDS_TWIN.id not in ids and 62999999 not in ids


@pytest.mark.asyncio
async def test_a_twin_holding_no_questions_is_named_but_costs_nothing(corpus):
    session = _Session(_rows(), _markets(), unidentified=[ODDS_TWIN])
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026)
    assert [u["event_id"] for u in report["unidentified_in_span"]] == [ODDS_TWIN.id]
    assert report["terminal"] == "complete"


@pytest.mark.asyncio
async def test_a_row_espn_listed_as_regular_season_is_not_unidentified(corpus):
    # A September row whose id the boards listed as type 2 is accounted for.
    september = EventRow(15300001, REGULAR_ESPN, "final", datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc), "Atlanta Braves", "Philadelphia Phillies")
    boards = _boards(corpus) + [("20260928", [corpus["regular"]])]
    session = _Session(_rows(), _markets() + [MarketRow(5, september.id, "x", "X", "kalshi", "binary", "resolved")], unidentified=[september])
    report = await run_mlb_postseason_assembly(session, _Container(), boards, POST_2026)
    assert report["unidentified_in_span"] == []
    assert report["terminal"] == "complete"


@pytest.mark.asyncio
async def test_an_unread_board_day_is_partial_not_an_empty_day(corpus):
    boards = _boards(corpus) + [("20261002", None)]
    session = _Session(_rows(), _markets())
    report = await run_mlb_postseason_assembly(session, _Container(), boards, POST_2026)
    assert report["terminal"] == "partial"
    assert report["incomplete"] == [INCOMPLETE_BOARD_DAY_DARK]
    assert report["harvest"]["days_unread"] == ["20261002"]


@pytest.mark.asyncio
async def test_a_capped_market_read_is_partial(corpus):
    session = _Session(_rows(), _markets())
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, limit=3)
    assert report["harvest"]["markets_truncated"] is True
    assert report["incomplete"] == [INCOMPLETE_MARKETS_TRUNCATED]
    session = _Session(_rows(), _markets())
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, limit=4)
    assert report["terminal"] == "complete"


@pytest.mark.asyncio
async def test_duplicate_rows_and_contradicted_ids_are_partial(corpus):
    twin = EventRow(9000, G2_ESPN, "scheduled", None, "Atlanta Braves", "Philadelphia Phillies")
    session = _Session(_rows() + [twin], _markets())
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026)
    assert report["incomplete"] == [INCOMPLETE_DUPLICATE_ROWS]

    relabelled = replace(corpus["cws_hou_g2"], season_type=2)
    boards = _boards(corpus) + [("20261002", [relabelled])]
    session = _Session(_rows(), _markets())
    report = await run_mlb_postseason_assembly(session, _Container(), boards, POST_2026)
    assert report["terminal"] == "partial"
    assert report["incomplete"] == [INCOMPLETE_CONFLICTING_IDENTITY]


@pytest.mark.asyncio
async def test_no_row_of_ours_is_partial_never_complete(corpus):
    session = _Session([], [])
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, apply=True)
    assert report["terminal"] == "partial" and report["reason"] == "no_member_found"
    assert len(report["games_without_event_row"]) == 3
    assert session.writes == []


@pytest.mark.asyncio
async def test_a_season_is_never_written_into_another_seasons_container(corpus):
    session = _Session(_rows(), _markets())
    report = await run_mlb_postseason_assembly(
        session, _Container(slug="mlb-2025-postseason"), _boards(corpus), POST_2026, apply=True
    )
    assert report["terminal"] == "refused"
    assert session.reads == [] and session.writes == []


@pytest.mark.asyncio
async def test_an_unavailable_postseason_reads_nothing(corpus):
    session = _Session(_rows(), _markets())
    report = await run_mlb_postseason_assembly(
        session, _Container(), [("20260924", [corpus["regular"]])], POST_2026, apply=True
    )
    assert report["terminal"] == "unavailable"
    assert report["reason"] == UNAVAILABLE_NO_POSTSEASON_GAMES
    assert session.reads == [] and session.writes == []


@pytest.mark.asyncio
async def test_a_ghost_market_is_unresolved_not_written(corpus):
    session = _Session(_rows(), _markets(), live_markets={62924880, 62924881, 62924885})
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, apply=True)
    assert 63026432 not in {e["child_id"] for e in _edge_rows(session)}
    assert [u["child_id"] for u in report["assembly"]["unresolved"]] == [63026432]


@pytest.mark.asyncio
async def test_membership_reads_are_by_id_only(corpus):
    session = _Session(_rows(), _markets())
    await gather_mlb_postseason_candidates(session, _boards(corpus), POST_2026)
    assert [s for s, _ in session.reads] == [EVENTS_FOR_ESPN_IDS_SQL, MARKETS_FOR_EVENTS_SQL, UNIDENTIFIED_IN_SPAN_SQL]
    for sql in (EVENTS_FOR_ESPN_IDS_SQL, MARKETS_FOR_EVENTS_SQL):
        assert "team_name =" not in sql and "commence_time >=" not in sql and "llm_importance" not in sql


# --- the dispatch entry ---------------------------------------------------------


class _Espn:
    def __init__(self, by_day, fail=()):
        self.by_day = by_day
        self.fail = set(fail)
        self.asked = []
        self.closed = False

    async def get_scoreboard(self, sport_key, date=None, groups=None):
        assert sport_key == "baseball_mlb" and groups is None
        self.asked.append(date)
        if date in self.fail:
            raise RuntimeError("boom")
        return self.by_day.get(date, [])

    async def close(self):
        self.closed = True


def test_board_days_are_inclusive():
    assert board_days(date(2026, 9, 29), date(2026, 10, 1)) == ["20260929", "20260930", "20261001"]
    assert board_days(date(2026, 10, 1), date(2026, 9, 29)) == []


@pytest.mark.asyncio
async def test_the_dispatch_entry_reads_each_day_and_runs_the_postseason(corpus):
    espn = _Espn({day: entries for day, entries in _boards(corpus)}, fail={"20261002"})
    session = _Session(_rows(), _markets())
    report = await assemble_mlb_postseason(
        session, _Container(), POST_2026, date(2026, 9, 29), date(2026, 10, 2), espn=espn
    )
    assert espn.asked == ["20260929", "20260930", "20261001", "20261002"]
    assert espn.closed is False  # an injected client is the caller's to close
    assert report["terminal"] == "partial"
    assert report["incomplete"] == [INCOMPLETE_BOARD_DAY_DARK]


@pytest.mark.asyncio
async def test_an_out_of_bounds_window_is_refused_before_any_read(corpus):
    espn = _Espn({})
    session = _Session(_rows(), _markets())
    start = date(2026, 9, 1)
    report = await assemble_mlb_postseason(
        session, _Container(), POST_2026, start, date.fromordinal(start.toordinal() + MAX_BOARD_DAYS), espn=espn
    )
    assert report["terminal"] == "refused" and report["reason"] == "board_window_out_of_bounds"
    assert espn.asked == [] and session.reads == []


@pytest.mark.asyncio
async def test_a_contradiction_outside_this_postseason_does_not_touch_it(corpus):
    # DERIVED: last October's id served again stamped regular season — a
    # contradiction between two identities, neither of them 2026's postseason.
    relabelled = replace(corpus["last_year"], season_type=2)
    boards = _boards(corpus) + [("20251001", [corpus["last_year"], relabelled])]
    session = _Session(_rows(), _markets())
    report = await run_mlb_postseason_assembly(session, _Container(), boards, POST_2026)
    assert [r["espn_id"] for r in report["excluded"][EXCLUDED_CONFLICTING_IDENTITY]] == [LAST_YEAR_ESPN]
    assert report["terminal"] == "complete"


# --- one card per game: the game's own winner market is the game card ------------


def _game_one_board():
    """REAL rows: PHI@ATL Game 1 (event 15320289) as stored on 2026-09-30 —
    `futures_markets` id, name, external_id, source, `market_type` and status
    read through `/api/admin/db-query`. Only `event_id` is the test double's."""
    return [
        MarketRow(62924885, G1_EVENT, "Game 1: Philadelphia vs Atlanta", "KXMLBGAME-26SEP291400PHIATL", "kalshi", "duel", "resolved"),
        MarketRow(62932002, G1_EVENT, "Philadelphia vs Atlanta: Spread", "KXMLBSPREAD-26SEP291400PHIATL", "kalshi", "field", "resolved"),
        MarketRow(63026431, G1_EVENT, "Philadelphia Phillies vs. Atlanta Braves", "1097824", "polymarket", "field", "resolved"),
        MarketRow(63026432, G1_EVENT, "Philadelphia Phillies vs. Atlanta Braves", "0x4b89caf655c9602405a1c0366a1de9cc976f88d3b85ff69a808754ed2e81f36b", "polymarket", "duel", "resolved"),
        MarketRow(63026433, G1_EVENT, "Spread: Atlanta Braves (-1.5)", "0x5c0c5cd1a9b9c329fa03076140", "polymarket", "duel", "resolved"),
        MarketRow(63153623, G1_EVENT, "Philadelphia vs Atlanta: 9th Inning Winner", "KXMLBINNINGWIN-26SEP291400PH", "kalshi", "field", "resolved"),
    ]


GAME_ONE_WINNERS = {62924885, 63026432}
GAME_ONE_QUESTIONS = {62932002, 63026431, 63026433, 63153623}


def test_game_ones_winner_markets_are_the_game_card_not_two_more_questions(corpus):
    selection = select_postseason_games(_boards(corpus), POST_2026)
    members = resolve_postseason_members(selection, _rows(), _game_one_board())
    markets = {c.child_id for c in members.candidates if c.child_type == "market"}
    assert markets == GAME_ONE_QUESTIONS
    assert G1_EVENT in {c.child_id for c in members.candidates if c.child_type == "event"}
    assert members.excluded[EXCLUDED_GAME_WINNER_MARKET] == [
        {"market_id": 62924885, "event_id": G1_EVENT, "source": "kalshi"},
        {"market_id": 63026432, "event_id": G1_EVENT, "source": "polymarket"},
    ]


@pytest.mark.asyncio
async def test_no_winner_edge_is_written_and_the_postseason_stays_complete(corpus):
    # Through the shipped SQL row mapping: `market_type` is column 5 of
    # MARKETS_FOR_EVENTS_SQL; a mis-mapped column would make the rule inert.
    session = _Session(_rows(), _game_one_board())
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, apply=True)
    edges = {e["child_id"] for e in _edge_rows(session) if e["child_type"] == "market"}
    assert edges == GAME_ONE_QUESTIONS and not edges & GAME_ONE_WINNERS
    assert {r["market_id"] for r in report["excluded"][EXCLUDED_GAME_WINNER_MARKET]} == GAME_ONE_WINNERS
    # Deliberate, not a gap: it never makes the read partial.
    assert report["terminal"] == "complete" and report["incomplete"] == []
