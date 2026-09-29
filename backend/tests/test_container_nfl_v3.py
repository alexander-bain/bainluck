"""One NFL week assembles from the authority's week identity, by id. #9649 (v3).

The positive corpus is REAL: `tests/fixtures/statpal_nfl_season_schedule_20260903.json`
is StatPal's `/v1/nfl/season-schedule` captured 2026-09-03 (Hall of Fame Weekend
+ Week 1, 17 games), and `statpal_nfl_post_season_placeholders_20260909.json` is
the 2026-09-09 Post Season stage (53 raw rows, 7 bracket placeholders). Both are
parsed through the shipped `StatPalAPIService._parse_nfl_season_schedule`.

Where a control needs a shape the captures do not hold — a Week 2 game, a
contest filed under two weeks, last season's preseason game — it is DERIVED from
one real parsed fixture with `dataclasses.replace`, and the test says which
field it moved. Our event and market rows are test doubles keyed on the real
contest ids; no production row is read.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

from app.services.statpal_api import StatPalAPIService, StatPalUpstreamError
from app.tasks.container_assembly import SOURCE_CONFIDENCE, UNDO_LINE
from app.tasks.container_nfl_assembly import (
    EVENTS_FOR_CONTESTS_SQL,
    MARKETS_FOR_EVENTS_SQL,
    UNIDENTIFIED_IN_SPAN_SQL,
    assemble_nfl_week,
    gather_nfl_week_candidates,
    run_nfl_week_assembly,
)
from app.utils.container_nfl import (
    EXCLUDED_CONFLICTING_IDENTITY,
    EXCLUDED_DUPLICATE_EVENT_ROWS,
    EXCLUDED_MARKET_ON_DUPLICATE,
    EXCLUDED_NO_WEEK_IDENTITY,
    EXCLUDED_OTHER_WEEK,
    EXCLUDED_PLACEHOLDER,
    EXCLUDED_WRONG_SEASON,
    INCOMPLETE_CONFLICTING_IDENTITY,
    INCOMPLETE_DUPLICATE_ROWS,
    INCOMPLETE_MARKETS_TRUNCATED,
    INCOMPLETE_NO_EVENT_ROW,
    STAGE_PRESEASON,
    UNAVAILABLE_NO_EVENT_ROW,
    UNAVAILABLE_SEASON_MISMATCH,
    UNAVAILABLE_SEASON_UNKNOWN,
    UNAVAILABLE_WEEK_NOT_SCHEDULED,
    EventRow,
    MarketRow,
    NflWeek,
    nfl_season_for_kickoff,
    parse_round_identity,
    resolve_week_members,
    schedule_season,
    select_week_contests,
)

FIXTURES = Path(__file__).parent / "fixtures"
REAL_SCHEDULE = FIXTURES / "statpal_nfl_season_schedule_20260903.json"
PLACEHOLDERS = FIXTURES / "statpal_nfl_post_season_placeholders_20260909.json"

WEEK_1 = NflWeek(season=2026, week=1)

#: The 16 Week-1 contest ids in the capture, read off the payload by hand and
#: pinned so a trimmed fixture is a failure rather than a quieter pass.
WEEK_1_CONTESTS = {str(i) for i in range(280445, 280461)}
HALL_OF_FAME_CONTEST = "280493"

#: Chargers v Cardinals, 2026-09-13 20:25Z — the kickoff production also held a
#: Rams v Cardinals phantom at (`stamp_nfl_statpal_fixtures` module note).
CHARGERS_CARDINALS = "280456"
#: Chiefs v Broncos, the Monday game; used as "the authority has it, we do not".
CHIEFS_BRONCOS = "280460"


def _parse(path: Path) -> list:
    return StatPalAPIService()._parse_nfl_season_schedule(json.loads(path.read_text()))


@pytest.fixture(scope="module")
def real():
    return _parse(REAL_SCHEDULE)


@pytest.fixture(scope="module")
def placeholders():
    return _parse(PLACEHOLDERS)


def _by_id(fixtures, contest_id):
    return next(f for f in fixtures if f.fixture_id == contest_id)


def _at(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


# --- the corpus, checked before anything leans on it --------------------------


def test_the_capture_still_holds_week_1_and_the_hall_of_fame_game(real):
    ids = {f.fixture_id for f in real}
    assert WEEK_1_CONTESTS <= ids
    assert HALL_OF_FAME_CONTEST in ids
    assert len(real) == 17


# --- week identity -------------------------------------------------------------


@pytest.mark.parametrize(
    "round_info, expected",
    [
        ("Regular Season / Week 1", ("Regular Season", 1)),
        ("Regular Season / Week 18", ("Regular Season", 18)),
        ("Pre Season / Week 2", ("Pre Season", 2)),
        ("Pre Season / Hall of Fame Weekend", None),
        ("Post Season / Wild Card", None),
        ("Regular Season / Week One", None),
        ("Regular Season", None),
        ("Week 1", None),
        ("Preseason / Week 1", None),
        (None, None),
    ],
)
def test_round_identity_is_exact_never_nearest(round_info, expected):
    assert parse_round_identity(round_info) == expected


def test_playoff_kickoffs_in_january_belong_to_the_season_before():
    assert nfl_season_for_kickoff(_at(2026, 9, 10)) == 2026
    assert nfl_season_for_kickoff(_at(2027, 1, 16)) == 2026
    assert nfl_season_for_kickoff(_at(2027, 2, 14)) == 2026


def test_the_week_slug_names_season_stage_and_week():
    assert WEEK_1.slug == "nfl-2026-week-1"
    assert NflWeek(2026, 2, STAGE_PRESEASON).slug == "nfl-2026-preseason-week-2"
    with pytest.raises(ValueError):
        NflWeek(2026, 1, "Preseason")
    with pytest.raises(ValueError):
        NflWeek(2026, 0)


def test_the_schedule_names_its_own_season(real, placeholders):
    assert schedule_season(real) == 2026
    # Placeholder kickoffs sit on StatPal's default slot; they never vote.
    assert schedule_season(real + placeholders) == 2026
    assert schedule_season(placeholders) is None


# --- selection: which authority contests are the week --------------------------


def test_week_1_is_exactly_the_sixteen_real_week_1_contests(real, placeholders):
    selection = select_week_contests(real + placeholders, WEEK_1)
    assert selection.unavailable is None
    assert {c.contest_id for c in selection.contests} == WEEK_1_CONTESTS
    # The neighbouring stage's real game is refused for having no numbered week,
    # never absorbed because it is the closest date.
    assert [r["statpal_id"] for r in selection.excluded[EXCLUDED_NO_WEEK_IDENTITY]] == [
        HALL_OF_FAME_CONTEST
    ]
    # 53 raw placeholder rows are 7 contests, and every one is refused as a
    # bracket slot before its five conflicting round labels are even read.
    assert len(selection.excluded[EXCLUDED_PLACEHOLDER]) == 7
    assert EXCLUDED_CONFLICTING_IDENTITY not in selection.excluded


def test_the_adjacent_week_does_not_absorb_week_1(real):
    selection = select_week_contests(real, NflWeek(2026, 2))
    assert selection.contests == []
    assert selection.unavailable == UNAVAILABLE_WEEK_NOT_SCHEDULED
    assert len(selection.excluded[EXCLUDED_OTHER_WEEK]) == 16


def test_a_week_2_game_stays_out_of_week_1_and_is_week_2s(real):
    # DERIVED: one real Week-1 game, relabelled Week 2, new id, a week later.
    week_2 = replace(
        _by_id(real, "280445"),
        fixture_id="990001",
        round_info="Regular Season / Week 2",
        start_time=_by_id(real, "280445").start_time + timedelta(days=7),
    )
    week_1 = select_week_contests(real + [week_2], WEEK_1)
    assert "990001" not in {c.contest_id for c in week_1.contests}
    assert [r["statpal_id"] for r in week_1.excluded[EXCLUDED_OTHER_WEEK]] == ["990001"]

    week_2_sel = select_week_contests(real + [week_2], NflWeek(2026, 2))
    assert [c.contest_id for c in week_2_sel.contests] == ["990001"]


def test_another_season_is_unavailable_not_a_rematch(real):
    selection = select_week_contests(real, NflWeek(2025, 1))
    assert selection.unavailable == UNAVAILABLE_SEASON_MISMATCH
    assert selection.contests == []


def test_a_schedule_mixing_seasons_is_unavailable(real):
    # DERIVED: a real Week-1 game moved to the same slot in 2025.
    stale = replace(
        _by_id(real, "280447"),
        fixture_id="880447",
        start_time=_by_id(real, "280447").start_time.replace(year=2025),
    )
    selection = select_week_contests(real + [stale], WEEK_1)
    assert selection.unavailable == UNAVAILABLE_SEASON_UNKNOWN
    assert selection.contests == []


def test_a_preseason_game_from_last_season_is_refused_by_season(real):
    # DERIVED: the real Hall of Fame game, relabelled a numbered preseason week
    # (a) as dated, and (b) moved back a year.
    hof = _by_id(real, HALL_OF_FAME_CONTEST)
    this_year = replace(hof, round_info="Pre Season / Week 1")
    last_year = replace(
        hof,
        fixture_id="880493",
        round_info="Pre Season / Week 1",
        start_time=hof.start_time.replace(year=2025),
    )
    fixtures = [f for f in real if f.fixture_id != HALL_OF_FAME_CONTEST] + [this_year, last_year]
    selection = select_week_contests(fixtures, NflWeek(2026, 1, STAGE_PRESEASON))
    assert [c.contest_id for c in selection.contests] == [HALL_OF_FAME_CONTEST]
    assert [r["statpal_id"] for r in selection.excluded[EXCLUDED_WRONG_SEASON]] == ["880493"]


def test_a_contest_filed_under_two_weeks_has_no_week(real):
    # DERIVED: the same contest id served again under Week 2.
    twice = replace(_by_id(real, "280449"), round_info="Regular Season / Week 2")
    selection = select_week_contests(real + [twice], WEEK_1)
    assert "280449" not in {c.contest_id for c in selection.contests}
    assert [r["statpal_id"] for r in selection.excluded[EXCLUDED_CONFLICTING_IDENTITY]] == ["280449"]


def test_a_repeated_identical_contest_is_one_contest(real):
    selection = select_week_contests(real + [_by_id(real, "280450")], WEEK_1)
    assert len(selection.contests) == 16


def test_status_and_unknown_kickoff_are_carried_not_filtered(real):
    # DERIVED: four real Week-1 games given the four lifecycle states, and one
    # with no kickoff at all and one whose kickoff is a placeholder.
    moved = {
        "280448": dict(status="finished"),
        "280451": dict(status="live"),
        "280452": dict(status="postponed"),
        "280453": dict(start_time=None),
        "280454": dict(start_is_placeholder=True),
    }
    fixtures = [replace(f, **moved.get(f.fixture_id, {})) for f in real]
    selection = select_week_contests(fixtures, WEEK_1)
    contests = {c.contest_id: c for c in selection.contests}
    assert set(contests) == WEEK_1_CONTESTS
    assert contests["280448"].status == "finished"
    assert contests["280451"].status == "live"
    assert contests["280452"].status == "postponed"
    assert contests["280453"].start_known is False
    assert contests["280453"].receipt()["kickoff"] is None
    assert contests["280454"].start_known is False
    assert contests["280454"].receipt()["kickoff"] is None
    assert contests["280445"].receipt()["kickoff"] == "2026-09-10T00:20:00+00:00"


# --- members: our rows, joined by contest id ------------------------------------


def _week_rows(real):
    """One of our rows per Week-1 contest, keyed on the real contest id, except:
    two rows hold Chargers v Cardinals, and Chiefs v Broncos has none."""
    rows = []
    for n, f in enumerate(sorted(real, key=lambda f: f.fixture_id)):
        if f.fixture_id not in WEEK_1_CONTESTS or f.fixture_id == CHIEFS_BRONCOS:
            continue
        rows.append(
            EventRow(
                id=1000 + n,
                statpal_fixture_id=f.fixture_id,
                status="scheduled",
                commence_time=f.start_time,
                home=f.home_team,
                away=f.away_team,
            )
        )
    duplicate = _by_id(real, CHARGERS_CARDINALS)
    rows.append(
        EventRow(
            id=2000,
            statpal_fixture_id=CHARGERS_CARDINALS,
            status="scheduled",
            commence_time=duplicate.start_time,
            home=duplicate.home_team,
            away=duplicate.away_team,
        )
    )
    return rows


def _event_id(rows, contest_id):
    return min(r.id for r in rows if r.statpal_fixture_id == contest_id)


def test_members_are_one_row_per_contest_and_gaps_stay_visible(real):
    selection = select_week_contests(real, WEEK_1)
    rows = _week_rows(real)
    members = resolve_week_members(selection, rows, [])

    events = [c for c in members.candidates if c.child_type == "event"]
    assert len(events) == 14
    assert {c.external_id for c in events} == WEEK_1_CONTESTS - {CHARGERS_CARDINALS, CHIEFS_BRONCOS}
    assert all(c.source == "authority_tournament_id" for c in events)

    [dup] = members.excluded[EXCLUDED_DUPLICATE_EVENT_ROWS]
    assert dup["statpal_id"] == CHARGERS_CARDINALS
    assert sorted(dup["event_ids"]) == sorted(
        r.id for r in rows if r.statpal_fixture_id == CHARGERS_CARDINALS
    )

    [gap] = members.unavailable
    assert gap["statpal_id"] == CHIEFS_BRONCOS
    assert gap["reason"] == UNAVAILABLE_NO_EVENT_ROW


def test_markets_follow_their_event_and_both_venues_stay(real):
    selection = select_week_contests(real, WEEK_1)
    rows = _week_rows(real)
    seahawks = _event_id(rows, "280445")
    dup_event = _event_id(rows, CHARGERS_CARDINALS)
    markets = [
        MarketRow(1, seahawks, "Patriots at Seahawks", "KXNFLGAME-26SEP09NESEA", "kalshi", "binary", "open"),
        MarketRow(2, seahawks, "Patriots vs. Seahawks", "0xabc", "polymarket", "binary", "open"),
        MarketRow(2, seahawks, "Patriots vs. Seahawks", "0xabc", "polymarket", "binary", "open"),
        MarketRow(3, seahawks, "Seahawks total points", "KXNFLTOTAL-26SEP09NESEA", "kalshi", "threshold", "resolved"),
        MarketRow(4, dup_event, "Cardinals at Chargers", "KXNFLGAME-26SEP13ARILAC", "kalshi", "binary", "open"),
        MarketRow(5, 999999, "Some other game", "X", "kalshi", "binary", "open"),
    ]
    members = resolve_week_members(selection, rows, markets)
    market_ids = [c.child_id for c in members.candidates if c.child_type == "market"]
    assert market_ids == [1, 2, 3]
    assert {c.market_source for c in members.candidates if c.child_id in (1, 2)} == {"kalshi", "polymarket"}
    assert members.excluded[EXCLUDED_MARKET_ON_DUPLICATE] == [
        {"market_id": 4, "event_id": dup_event, "source": "kalshi"}
    ]


def test_an_unavailable_week_has_no_members_even_with_rows(real):
    selection = select_week_contests(real, NflWeek(2026, 2))
    members = resolve_week_members(selection, _week_rows(real), [])
    assert members.candidates == []


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
    probe from in-memory rows, and records every write statement it is handed.
    Anything else is a query this test did not expect, and fails it."""

    def __init__(self, events, markets, unidentified, live_markets=None):
        self.events = events
        self.markets = markets
        self.unidentified = unidentified
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
        if sql == EVENTS_FOR_CONTESTS_SQL:
            ids = set(params["contest_ids"])
            return _Result([self._event(r) for r in self.events if r.statpal_fixture_id in ids])
        if sql == MARKETS_FOR_EVENTS_SQL:
            ids = set(params["event_ids"])
            return _Result(
                [
                    (m.id, m.event_id, m.name, m.external_id, m.source, m.market_type, m.status)
                    for m in self.markets
                    if m.event_id in ids
                ][: params["limit"]]
            )
        if sql == UNIDENTIFIED_IN_SPAN_SQL:
            return _Result([self._event(r) for r in self.unidentified])
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
        return (r.id, r.statpal_fixture_id, r.status, r.commence_time, r.home, r.away)


class _Container:
    def __init__(self, slug=WEEK_1.slug, id=77):
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
                    for k in ("parent_type", "parent_id", "child_type", "child_id", "kind", "class", "source", "confidence")
                }
            )
            n += 1
            if not suffix:
                break
    return edges


def _session_for(real):
    rows = _week_rows(real)
    seahawks = _event_id(rows, "280445")
    markets = [
        MarketRow(1, seahawks, "Patriots at Seahawks", "KXNFLGAME-26SEP09NESEA", "kalshi", "binary", "open"),
        MarketRow(2, seahawks, "Patriots vs. Seahawks", "0xabc", "polymarket", "binary", "open"),
        MarketRow(4, _event_id(rows, CHARGERS_CARDINALS), "Cardinals at Chargers", "KX-DUP", "kalshi", "binary", "open"),
    ]
    chargers = _by_id(real, CHARGERS_CARDINALS)
    phantom = EventRow(
        id=3000,
        statpal_fixture_id=None,
        status="scheduled",
        commence_time=chargers.start_time,
        home="Arizona Cardinals",
        away="Los Angeles Rams",
    )
    return _Session(rows, markets, [phantom]), rows


@pytest.mark.asyncio
async def test_the_adapter_feeds_assemble_container_the_week_and_nothing_else(real):
    session, rows = _session_for(real)
    report = await run_nfl_week_assembly(session, _Container(), real, WEEK_1, apply=True)

    # A missing game and two rows for another: the 14 supported games are kept,
    # but the week is not claimed whole.
    assert report["terminal"] == "partial"
    assert report["reason"] == INCOMPLETE_NO_EVENT_ROW
    assert report["incomplete"] == [INCOMPLETE_NO_EVENT_ROW, INCOMPLETE_DUPLICATE_ROWS]
    edges = _edge_rows(session)
    event_edges = [e for e in edges if e["child_type"] == "event"]
    market_edges = [e for e in edges if e["child_type"] == "market"]

    expected_events = {
        r.id for r in rows if r.statpal_fixture_id not in (CHARGERS_CARDINALS,)
    }
    assert {e["child_id"] for e in event_edges} == expected_events
    assert len(event_edges) == 14
    assert {e["child_id"] for e in market_edges} == {1, 2}
    assert all(e["parent_type"] == "container" and e["parent_id"] == 77 for e in edges)
    assert all(e["kind"] == "contains" for e in edges)
    assert {e["class"] for e in event_edges} == {"match_winner"}
    assert {e["source"] for e in event_edges} == {"authority_tournament_id"}
    assert {float(e["confidence"]) for e in event_edges} == {SOURCE_CONFIDENCE["authority_tournament_id"]}
    assert {e["source"] for e in market_edges} == {"matcher"}

    # The phantom and both duplicate rows are named, and none became a member.
    assert [u["event_id"] for u in report["unidentified_in_span"]] == [3000]
    dup_ids = set(report["excluded"][EXCLUDED_DUPLICATE_EVENT_ROWS][0]["event_ids"])
    assert not dup_ids & {e["child_id"] for e in edges}
    assert 3000 not in {e["child_id"] for e in edges}
    assert [g["statpal_id"] for g in report["contests_without_event_row"]] == [CHIEFS_BRONCOS]

    assert report["assembly"]["edges_written"] == 16
    assert report["assembly"]["by_class"]["match_winner"] >= 14
    assert report["undo"]["edges"] == UNDO_LINE
    assert session.committed is False


@pytest.mark.asyncio
async def test_a_dry_run_writes_nothing_and_still_reports_the_week(real):
    session, _ = _session_for(real)
    report = await run_nfl_week_assembly(session, _Container(), real, WEEK_1, apply=False)
    assert session.writes == []
    assert "assembly" not in report
    assert report["harvest"]["candidates"] == {"event": 14, "market": 2}
    assert report["harvest"]["excluded"][EXCLUDED_DUPLICATE_EVENT_ROWS] == 1
    assert report["harvest"]["excluded"][EXCLUDED_MARKET_ON_DUPLICATE] == 1


@pytest.mark.asyncio
async def test_a_week_is_never_written_into_another_weeks_container(real):
    session, _ = _session_for(real)
    report = await run_nfl_week_assembly(
        session, _Container(slug="nfl-2026-week-2"), real, WEEK_1, apply=True
    )
    assert report["terminal"] == "refused"
    assert session.reads == [] and session.writes == []


@pytest.mark.asyncio
async def test_an_unscheduled_week_is_unavailable_and_reads_nothing(real):
    session, _ = _session_for(real)
    week_2 = NflWeek(2026, 2)
    report = await run_nfl_week_assembly(session, _Container(slug=week_2.slug), real, week_2, apply=True)
    assert report["terminal"] == "unavailable"
    assert report["reason"] == UNAVAILABLE_WEEK_NOT_SCHEDULED
    assert session.reads == [] and session.writes == []


@pytest.mark.asyncio
async def test_a_week_with_no_row_of_ours_is_partial_never_complete(real):
    session = _Session([], [], [])
    report = await run_nfl_week_assembly(session, _Container(), real, WEEK_1, apply=True)
    assert report["terminal"] == "partial"
    assert report["reason"] == "no_member_found"
    assert len(report["contests_without_event_row"]) == 16
    assert session.writes == []


@pytest.mark.asyncio
async def test_a_ghost_market_is_unresolved_not_written(real):
    session, _ = _session_for(real)
    session.live_markets = {1}
    report = await run_nfl_week_assembly(session, _Container(), real, WEEK_1, apply=True)
    assert {e["child_id"] for e in _edge_rows(session) if e["child_type"] == "market"} == {1}
    assert [u["child_id"] for u in report["assembly"]["unresolved"]] == [2]


@pytest.mark.asyncio
async def test_an_unreadable_schedule_is_unavailable_not_an_empty_week():
    class _Down:
        async def get_schedule_fixtures(self, sport):
            assert sport == "nfl"
            raise StatPalUpstreamError("503")

    session = _Session([], [], [])
    report = await assemble_nfl_week(session, _Container(), WEEK_1, apply=True, service=_Down())
    assert report["terminal"] == "unavailable"
    assert report["reason"] == "schedule_unreadable"
    assert session.reads == [] and session.writes == []


@pytest.mark.asyncio
async def test_the_dispatch_entry_reads_the_schedule_and_runs_the_week(real):
    class _Up:
        async def get_schedule_fixtures(self, sport):
            return list(real)

    session, _ = _session_for(real)
    report = await assemble_nfl_week(session, _Container(), WEEK_1, apply=False, service=_Up())
    assert report["terminal"] == "partial"
    assert report["harvest"]["contests"] == 16
    assert report["harvest"]["incomplete"] == [INCOMPLETE_NO_EVENT_ROW, INCOMPLETE_DUPLICATE_ROWS]


@pytest.mark.asyncio
async def test_gather_reads_only_by_id_for_membership(real):
    session, _ = _session_for(real)
    await gather_nfl_week_candidates(session, real, WEEK_1)
    sqls = [s for s, _ in session.reads]
    assert sqls == [EVENTS_FOR_CONTESTS_SQL, MARKETS_FOR_EVENTS_SQL, UNIDENTIFIED_IN_SPAN_SQL]
    # The membership reads carry no name and no time.
    for sql in (EVENTS_FOR_CONTESTS_SQL, MARKETS_FOR_EVENTS_SQL):
        assert "team_name =" not in sql and "commence_time >=" not in sql


# --- complete means the whole week, not "found something" -----------------------


def _whole_week_rows(real):
    """Exactly one of our rows per real Week-1 contest — the only shape that is
    a whole week."""
    return [
        EventRow(
            id=5000 + n,
            statpal_fixture_id=f.fixture_id,
            status="scheduled",
            commence_time=f.start_time,
            home=f.home_team,
            away=f.away_team,
        )
        for n, f in enumerate(sorted(real, key=lambda f: f.fixture_id))
        if f.fixture_id in WEEK_1_CONTESTS
    ]


def _whole_week_markets(rows):
    return [
        MarketRow(10 + i, r.id, f"{r.away} at {r.home}", f"KX-{r.statpal_fixture_id}", "kalshi", "binary", "open")
        for i, r in enumerate(rows)
    ]


@pytest.mark.asyncio
async def test_a_genuinely_whole_week_is_complete(real):
    # CONTROL: every clause below must be able to flip this to partial.
    rows = _whole_week_rows(real)
    session = _Session(rows, _whole_week_markets(rows), [])
    report = await run_nfl_week_assembly(session, _Container(), real, WEEK_1, apply=True)
    assert report["terminal"] == "complete"
    assert report["reason"] is None
    assert report["incomplete"] == []
    assert report["assembly"]["edges_written"] == 32
    assert report["contests_without_event_row"] == []


@pytest.mark.asyncio
async def test_a_week_missing_one_game_is_partial_and_keeps_the_rest(real):
    rows = [r for r in _whole_week_rows(real) if r.statpal_fixture_id != CHIEFS_BRONCOS]
    session = _Session(rows, _whole_week_markets(rows), [])
    report = await run_nfl_week_assembly(session, _Container(), real, WEEK_1, apply=True)
    assert report["terminal"] == "partial"
    assert report["reason"] == INCOMPLETE_NO_EVENT_ROW
    assert report["incomplete"] == [INCOMPLETE_NO_EVENT_ROW]
    assert [g["statpal_id"] for g in report["contests_without_event_row"]] == [CHIEFS_BRONCOS]
    # The 15 supported games and their questions are still assembled.
    assert {e["child_id"] for e in _edge_rows(session) if e["child_type"] == "event"} == {r.id for r in rows}


@pytest.mark.asyncio
async def test_two_rows_for_one_game_make_the_week_partial(real):
    # Every contest has a row; one also has a second row, so that game is
    # refused and the week is short it.
    rows = _whole_week_rows(real)
    twin = replace(next(r for r in rows if r.statpal_fixture_id == CHARGERS_CARDINALS), id=9000)
    rows = rows + [twin]
    session = _Session(rows, _whole_week_markets(rows), [])
    report = await run_nfl_week_assembly(session, _Container(), real, WEEK_1, apply=True)
    assert report["terminal"] == "partial"
    assert report["reason"] == INCOMPLETE_DUPLICATE_ROWS
    assert report["incomplete"] == [INCOMPLETE_DUPLICATE_ROWS]
    event_ids = {e["child_id"] for e in _edge_rows(session) if e["child_type"] == "event"}
    assert len(event_ids) == 15 and 9000 not in event_ids


@pytest.mark.asyncio
async def test_a_capped_market_read_is_partial_even_with_every_game(real):
    rows = _whole_week_rows(real)
    session = _Session(rows, _whole_week_markets(rows), [])
    report = await run_nfl_week_assembly(session, _Container(), real, WEEK_1, apply=True, limit=5)
    assert report["harvest"]["markets_truncated"] is True
    assert report["terminal"] == "partial"
    assert report["reason"] == INCOMPLETE_MARKETS_TRUNCATED
    assert report["incomplete"] == [INCOMPLETE_MARKETS_TRUNCATED]
    # At the cap exactly, nothing was cut: whole.
    session = _Session(rows, _whole_week_markets(rows), [])
    report = await run_nfl_week_assembly(session, _Container(), real, WEEK_1, apply=False, limit=16)
    assert report["terminal"] == "complete"


@pytest.mark.asyncio
async def test_a_week_game_also_filed_under_another_week_makes_it_partial(real):
    # DERIVED: a real Week-1 contest served again under Week 2.
    twice = replace(_by_id(real, "280449"), round_info="Regular Season / Week 2")
    rows = _whole_week_rows(real)
    session = _Session(rows, _whole_week_markets(rows), [])
    report = await run_nfl_week_assembly(session, _Container(), real + [twice], WEEK_1, apply=False)
    assert report["terminal"] == "partial"
    assert report["incomplete"] == [INCOMPLETE_CONFLICTING_IDENTITY]


@pytest.mark.asyncio
async def test_a_conflict_between_two_other_weeks_does_not_touch_this_one(real):
    # DERIVED: a new contest id served under Week 2 and Week 3 — not Week 1's.
    base = _by_id(real, "280449")
    w2 = replace(base, fixture_id="880449", round_info="Regular Season / Week 2")
    w3 = replace(base, fixture_id="880449", round_info="Regular Season / Week 3")
    rows = _whole_week_rows(real)
    session = _Session(rows, _whole_week_markets(rows), [])
    report = await run_nfl_week_assembly(session, _Container(), real + [w2, w3], WEEK_1, apply=False)
    assert report["excluded"][EXCLUDED_CONFLICTING_IDENTITY][0]["statpal_id"] == "880449"
    assert report["terminal"] == "complete"
