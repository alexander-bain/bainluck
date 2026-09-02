"""Q048 — a match-winner market that RESOLVED is still evidence of a wrong link.

THE SPECIMEN, measured on production 2026-09-02 (US Open, Monfils v Vallejo):

    KXATPSETWINNER/GTOTAL/GSPREAD/EXACTMATCH-26AUG30VALMON
                                 -> 15293804  (odds_api, 2026-09-01 23:04Z,
                                               completed 1-3 — the real row)
    KXATPMATCH-26AUG30VALMON     -> 15300759  (kalshi_ticker, 2026-08-30 00:00Z
                                               midnight stand-in, "scheduled")

ESPN had the match final at 2026-09-01 23:05Z. `/api/events/15300759` read
`scheduled`, and a user searching "Monfils" got that GHOST first, above the real
settled row.

Q435 built the reconciliation that should have collapsed this the moment both
rows were visible. It could not, because it read `FuturesMarket.status ==
"open"` — and a tennis match-winner market resolves at exactly the moment the
ghost becomes user-visible. If the schedule-derived twin had not appeared while
the winner was still open, `_choose_segment_event` saw one candidate, returned
`single`, moved nothing, and the market then resolved out of sight for good.

Measured across the 2,933 Kalshi tennis markets created since the US Open began:
**25 markets sat on the wrong event of their own segment and all 25 were
`resolved`** — a 100% blind spot, every one a `KX*MATCH-*`.

These tests pin BOTH ARMS everywhere, because a guard that only pins the new
behaviour passes equally well on a reconciler that has simply stopped filtering
anything at all.
"""

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update
from sqlalchemy.dialects import sqlite as sqlite_dialect

from app.models.models import FuturesMarket
from app.tasks.prediction_market_matching import (
    KALSHI_SEGMENT_WINDOW_DAYS,
    MAX_KALSHI_SEGMENT_ROWS,
    _reconcile_kalshi_match_segments,
)

# The real production specimen, ticker for ticker.
VALMON_PROPS = (
    "KXATPSETWINNER-26AUG30VALMON-1",
    "KXATPSETWINNER-26AUG30VALMON-2",
    "KXATPSETWINNER-26AUG30VALMON-3",
    "KXATPGTOTAL-26AUG30VALMON",
    "KXATPGSPREAD-26AUG30VALMON",
    "KXATPEXACTMATCH-26AUG30VALMON",
)
VALMON_WINNER = "KXATPMATCH-26AUG30VALMON"
REAL_EVENT = 15293804      # odds_api, completed, the row ESPN agrees with
GHOST_EVENT = 15300759     # kalshi_ticker, midnight stand-in, "scheduled"


# =============================================================================
# Part 1 — the POPULATION. The real WHERE clause, executed.
#
# The fake session below cannot test the filter: it returns whatever rows it was
# handed, whatever the statement says. So the population is proved by taking the
# statement the reconciler actually issues, compiling it, and RUNNING it over
# planted rows in stdlib sqlite3. If the predicate stops selecting a resolved
# link, these go red; if it starts selecting everything, they also go red.
# =============================================================================


class _CapturingSession:
    """Records the statements issued and returns nothing."""

    def __init__(self):
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)

        class _Empty:
            def all(self_inner):
                return []

        return _Empty()

    async def commit(self):  # pragma: no cover — nothing moves on an empty read
        pass

    async def rollback(self):  # pragma: no cover
        pass


def _candidate_select():
    """The SELECT the reconciler really issues, as literal SQL."""
    session = _CapturingSession()
    asyncio.run(_reconcile_kalshi_match_segments(session))
    assert session.statements, "the reconciler issued no query at all"
    return session.statements[0].compile(
        dialect=sqlite_dialect.dialect(),
        compile_kwargs={"literal_binds": True},
    ).string


#: (id, external_id, status, event_id, age_in_days, should_be_selected, why)
POPULATION = [
    # ── the arm that already worked, and must keep working ──────────────
    (1, VALMON_WINNER, "open", GHOST_EVENT, 0, True,
     "open+linked — today's population"),
    (2, "KXATPGTOTAL-26AUG30VALMON", "open", None, 0, True,
     "open+unlinked — today's population, the ADOPT candidate"),
    (3, "KXWTAMATCH-26JUN01AAABBB", "open", 900, 400, True,
     "open stays in scope at ANY age — the window is additive, not a filter"),

    # ── the arm Q048 adds: the whole defect ─────────────────────────────
    (4, VALMON_WINNER + "-X", "resolved", GHOST_EVENT, 1, True,
     "RESOLVED but LINKED and in window — the 25-row blind spot"),
    (5, "KXWTAMATCH-26AUG30STASEI", "settled", GHOST_EVENT, 13, True,
     "any non-open status counts; 'open' is not the only word Kalshi writes"),

    # ── the narrowing, which is load-bearing ────────────────────────────
    (6, "KXATPEXACTMATCH-26AUG23COMYIB", "resolved", None, 1, False,
     "resolved+UNLINKED is an ADOPT candidate, deliberately out of scope"),
    (7, "KXATPMATCH-26MAY01AAABBB", "resolved", 901, 60, False,
     "resolved+linked but OUTSIDE the window — the window is real"),

    # ── the bounds that were already there ──────────────────────────────
    (8, "KXNBAGAME-26FEB20BOSGSW", "resolved", 902, 1, False,
     "not a tennis prefix"),
    (9, "KXATPMATCH-26AUG30AAABBB", "resolved", 903, 1, False,
     "not a kalshi source", "polymarket"),
]


def _run_population_query():
    """Execute the production predicate over the planted rows."""
    sql = _candidate_select()
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE futures_markets ("
        " id INTEGER, external_id TEXT, status TEXT, event_id INTEGER,"
        " source TEXT, created_at TEXT)"
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for row in POPULATION:
        mid, ext, status, event_id, age, _expected, _why = row[:7]
        source = row[7] if len(row) > 7 else "kalshi"
        created = now - timedelta(days=age)
        conn.execute(
            "INSERT INTO futures_markets VALUES (?,?,?,?,?,?)",
            (mid, ext, status, event_id, source, created.isoformat(sep=" ")),
        )
    conn.commit()
    return {r[0] for r in conn.execute(sql).fetchall()}


class TestCandidatePopulation:
    def test_the_predicate_selects_exactly_the_intended_rows(self):
        selected = _run_population_query()
        expected = {row[0] for row in POPULATION if row[5]}
        missing = expected - selected
        extra = selected - expected
        assert not missing, "\n".join(
            f"NOT SELECTED but should be: id={r[0]} {r[1]} ({r[6]})"
            for r in POPULATION if r[0] in missing
        )
        assert not extra, "\n".join(
            f"SELECTED but should not be: id={r[0]} {r[1]} ({r[6]})"
            for r in POPULATION if r[0] in extra
        )

    def test_a_resolved_link_is_in_scope(self):
        """RED BEFORE THE FIX — this is the whole defect, one row."""
        assert 4 in _run_population_query()

    def test_a_resolved_orphan_is_not(self):
        """The narrowing. Admitting these attaches 176 historical props in one
        pass (measured 2026-09-02) — a different ship, not this one."""
        assert 6 not in _run_population_query()

    def test_an_open_market_is_never_aged_out(self):
        """CONTROL — green under both arms. An open market 400 days old still
        reconciles, so the window can only ever ADD rows."""
        assert 3 in _run_population_query()

    def test_the_window_is_not_infinite(self):
        """Without this, 'in window' is untestable and the constant decorative."""
        assert 7 not in _run_population_query()

    def test_the_window_constant_is_actually_the_one_in_the_query(self):
        """A constant nothing reads is a comment. Move it, and the rendered
        floor must move with it."""
        sql = _candidate_select()
        floor = datetime.now(timezone.utc) - timedelta(
            days=KALSHI_SEGMENT_WINDOW_DAYS
        )
        assert floor.strftime("%Y-%m-%d") in sql, sql


# =============================================================================
# Part 2 — the DECISION, on the specimen. Both arms.
# =============================================================================


class _Row:
    def __init__(self, mid, external_id, event_id):
        self.id = mid
        self.external_id = external_id
        self.event_id = event_id


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Returns a fixed row set — it models what the query FOUND, not the query."""

    def __init__(self, markets, provenance, sport_ids=None):
        self._markets = markets
        self._provenance = provenance
        self._sport_ids = sport_ids or {}
        self.updates = []
        self.commits = 0

    async def execute(self, stmt):
        if isinstance(stmt, type(update(FuturesMarket))):
            self.updates.append(stmt)
            return _Result([])
        text = str(stmt)
        if "futures_markets" in text:
            return _Result(self._markets)
        if "events" in text:
            return _Result([
                (eid, src, self._sport_ids.get(eid))
                for eid, src in self._provenance.items()
            ])
        raise AssertionError(f"unexpected statement: {text[:120]}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):  # pragma: no cover
        pass


def _applied(session):
    moves = {}
    for stmt in session.updates:
        values = dict(stmt._values)
        target = values[FuturesMarket.__table__.c.event_id].value
        ids = set(stmt.whereclause.right.value)
        moves.setdefault(target, set()).update(ids)
    return moves


def _valmon_session(include_winner):
    """The production specimen. `include_winner` models the open-only read,
    which could not see the resolved match-winner market at all."""
    markets = [
        _Row(100 + i, ticker, REAL_EVENT)
        for i, ticker in enumerate(VALMON_PROPS)
    ]
    if include_winner:
        markets.append(_Row(59693708, VALMON_WINNER, GHOST_EVENT))
    return _FakeSession(
        markets=markets,
        provenance={REAL_EVENT: "odds_api", GHOST_EVENT: "kalshi_ticker"},
    )


@pytest.mark.asyncio
class TestTheSpecimen:
    async def test_the_winner_market_converges_onto_the_real_event(self):
        session = _valmon_session(include_winner=True)
        stats = await _reconcile_kalshi_match_segments(session)

        assert _applied(session) == {REAL_EVENT: {59693708}}
        assert stats["converged"] == 1
        assert stats["adopted"] == 0
        assert stats["ambiguous"] == 0

    async def test_without_the_winner_row_nothing_moves(self):
        """THE OTHER ARM, and the reason the old filter was fatal rather than
        merely incomplete: with the resolved winner invisible, the segment is a
        clean `single` on the REAL event and the pass reports success while the
        ghost keeps the market. A green run is not a converged one."""
        session = _valmon_session(include_winner=False)
        stats = await _reconcile_kalshi_match_segments(session)

        assert session.updates == []
        assert session.commits == 0
        assert stats["converged"] == 0

    async def test_the_ghost_never_wins_the_segment(self):
        """Direction matters. The ticker-derived row is the duplicate, always —
        a reconciliation that moved the props onto the ghost would also report
        `converged: 6` and would be a strictly worse bug."""
        session = _valmon_session(include_winner=True)
        await _reconcile_kalshi_match_segments(session)

        assert GHOST_EVENT not in _applied(session)

    async def test_settlements_are_untouched_on_a_resolved_market(self):
        """gotcha #21 — this pass now moves markets that ALREADY CARRY a
        settlement, which is exactly when writing one would be unrecoverable.
        Only the link may move."""
        session = _valmon_session(include_winner=True)
        await _reconcile_kalshi_match_segments(session)

        assert session.updates, "nothing moved — this guard would be vacuous"
        for stmt in session.updates:
            touched = {c.name for c in dict(stmt._values)}
            assert touched <= {"event_id", "sport_id"}, touched

    async def test_status_is_never_rewritten_to_reopen_a_resolved_market(self):
        session = _valmon_session(include_winner=True)
        await _reconcile_kalshi_match_segments(session)

        for stmt in session.updates:
            assert "status" not in {c.name for c in dict(stmt._values)}


# =============================================================================
# Part 3 — a truncated read must REFUSE, not reconcile half a picture.
# =============================================================================


@pytest.mark.asyncio
class TestTruncationRefuses:
    async def test_a_capped_read_moves_nothing_and_says_so(self):
        """The cap slices by `id`, which cuts ACROSS segments. A segment whose
        schedule-derived member fell off the end reads as all-ticker-derived,
        and an unlinked sibling would then be ADOPTED onto the ghost — an
        actively wrong move, not a missed one."""
        markets = [
            _Row(i, f"KXATPMATCH-26AUG30P{i:05d}", GHOST_EVENT)
            for i in range(MAX_KALSHI_SEGMENT_ROWS)
        ]
        markets.append(_Row(999999, VALMON_WINNER, None))
        session = _FakeSession(
            markets=markets,
            provenance={GHOST_EVENT: "kalshi_ticker", REAL_EVENT: "odds_api"},
        )
        stats = await _reconcile_kalshi_match_segments(session)

        assert stats["truncated"] is True
        assert session.updates == []
        assert session.commits == 0

    async def test_an_uncapped_read_is_not_flagged_truncated(self):
        """CONTROL — otherwise a reconciler that always refused would pass."""
        session = _valmon_session(include_winner=True)
        stats = await _reconcile_kalshi_match_segments(session)

        assert stats["truncated"] is False
        assert session.updates, "the control must actually do the work"

    async def test_the_refusal_is_loud(self, caplog):
        """A silent cap reads exactly like 'covered everything'."""
        import logging

        markets = [
            _Row(i, f"KXATPMATCH-26AUG30P{i:05d}", GHOST_EVENT)
            for i in range(MAX_KALSHI_SEGMENT_ROWS)
        ]
        session = _FakeSession(
            markets=markets, provenance={GHOST_EVENT: "kalshi_ticker"},
        )
        with caplog.at_level(logging.ERROR):
            await _reconcile_kalshi_match_segments(session)

        assert any(
            rec.levelno >= logging.ERROR and "REFUSED" in rec.getMessage()
            for rec in caplog.records
        ), [r.getMessage() for r in caplog.records]


# =============================================================================
# Part 4 — the constants are honest about the population they were sized for.
# =============================================================================


class TestBounds:
    def test_the_cap_is_a_backstop_not_a_routine_bound(self):
        """Measured 2026-09-02, at the US Open peak: 589 open ATP/WTA rows of
        any age plus 3,782 resolved rows inside the window. A cap that the
        normal population can reach would make the refusal above fire in
        ordinary operation and silently disable reconciliation."""
        measured_peak = 589 + 3782
        assert MAX_KALSHI_SEGMENT_ROWS > 4 * measured_peak

    def test_the_window_covers_a_grand_slam(self):
        """A slam runs a fortnight. A window shorter than the tournament would
        strand the first week's ghosts while the second week was still being
        played — the exact rows this queue exists to collapse."""
        assert KALSHI_SEGMENT_WINDOW_DAYS >= 14


# =============================================================================
# Part 5 — the SEARCH half. A stand-in start is not evidence of separateness.
#
# Converging the market off the ghost does NOT remove the ghost from search:
# `15300753` (Sonmez v Gauff) holds ZERO markets on production and still ranks
# FIRST for "Gauff". #2623's dedup already exists to collapse exactly this
# twin — it just cannot reach these, because its 36h window reads the gap as
# evidence the two are different fixtures. Measured over the 22 ghost/real
# pairs the Kalshi segment key identifies across the US Open: gaps run 15.0h to
# 71.1h, median 66.7h, and 19 of the 22 are outside 36h.
# =============================================================================

from app.utils.search_fixture_dedup import (  # noqa: E402
    DERIVED_START_WINDOW_HOURS,
    FIXTURE_TIME_WINDOW_HOURS,
    duplicate_fixture_event_ids,
)


class _Sport:
    def __init__(self, key):
        self.key = key


class _Event:
    """Duck-typed exactly as the helper reads it."""

    def __init__(self, eid, home, away, hours_from_anchor, sport, source,
                 score=None):
        self.id = eid
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = datetime(2026, 9, 1, 23, 4, tzinfo=timezone.utc) \
            + timedelta(hours=hours_from_anchor)
        self.home_score, self.away_score = score if score else (None, None)
        self.commence_time_source = source
        self.sport = _Sport(sport)


def _real_monfils(**kw):
    return _Event(REAL_EVENT, "Adolfo Daniel Vallejo", "Gael Monfils", 0,
                  "tennis_atp_us_open", "odds_api", score=(1, 3), **kw)


def _ghost_monfils(hours=-71.1, source="kalshi_ticker"):
    return _Event(GHOST_EVENT, "Vallejo", "Monfils", hours, "tennis_atp", source)


class TestSearchDropsTheGhost:
    def test_the_ghost_71_hours_out_is_collapsed(self):
        """THE SHIP. RED BEFORE THE FIX — 71.1h is outside the 36h window, so
        `/api/events/search?q=Monfils` renders the ghost FIRST, above the row
        that already carries the right date and the right score."""
        dropped = duplicate_fixture_event_ids([_real_monfils(), _ghost_monfils()])
        assert dropped == {GHOST_EVENT}

    def test_the_real_row_is_never_the_one_dropped(self):
        """Direction. Dropping 15293804 would delete the only correct row."""
        dropped = duplicate_fixture_event_ids([_real_monfils(), _ghost_monfils()])
        assert REAL_EVENT not in dropped

    def test_two_reported_starts_71_hours_apart_still_do_not_pair(self):
        """CONTROL, and the load-bearing one: the 36h window is untouched for
        rows whose times somebody actually reported. Without this, the change
        reads as 'widen the window', which would re-open #2623's MLB finding."""
        real = _real_monfils()
        other = _Event(777, "Vallejo", "Monfils", -71.1, "tennis_atp", "kalshi")
        assert duplicate_fixture_event_ids([real, other]) == set()

    def test_two_stand_ins_do_not_pair_with_each_other(self):
        """Both derived ⇒ the NARROW window still applies. Nothing in the gap
        between two stand-ins was reported by anybody."""
        a = _Event(801, "Vallejo", "Monfils", -71.1, "tennis_atp", "kalshi_ticker")
        b = _Event(802, "Adolfo Daniel Vallejo", "Gael Monfils", 0,
                   "tennis_atp", "kalshi_ticker", score=(1, 3))
        assert duplicate_fixture_event_ids([a, b]) == set()

    def test_the_wider_window_is_still_a_window(self):
        """96h is bounded on purpose. Unbounded, any PAST meeting of the same
        two players would dominate a future ghost."""
        dropped = duplicate_fixture_event_ids(
            [_real_monfils(), _ghost_monfils(hours=-200)]
        )
        assert dropped == set()

    def test_a_null_provenance_is_a_reported_start(self):
        """Most of the table predates the column. If `None` read as derived,
        this would silently widen the window for nearly every row on the site
        — the exact narrowness q076 spelled out and this must not undo."""
        dropped = duplicate_fixture_event_ids(
            [_real_monfils(), _ghost_monfils(source=None)]
        )
        assert dropped == set()

    def test_a_team_sport_is_untouched(self):
        """#2623 measured this the hard way: three real Angels-Yankees games on
        consecutive days. A team sport plays the same opponent back to back."""
        a = _Event(901, "Los Angeles Angels", "New York Yankees", 0,
                   "baseball_mlb", "odds_api", score=(4, 1))
        b = _Event(902, "Angels", "Yankees", -71.1, "baseball_mlb",
                   "kalshi_ticker")
        assert duplicate_fixture_event_ids([a, b]) == set()

    def test_the_two_windows_are_distinct_and_ordered(self):
        """If they were equal the whole change would be inert while every test
        above still passed on the narrow one."""
        assert DERIVED_START_WINDOW_HOURS > FIXTURE_TIME_WINDOW_HOURS

    def test_the_measured_worst_case_fits_with_headroom(self):
        """Worst observed pair 71.1h (15300759 -> 15293804), measured
        2026-09-02 across 22 pairs. A window sized exactly to the worst case
        strands the next one."""
        assert DERIVED_START_WINDOW_HOURS >= 72
