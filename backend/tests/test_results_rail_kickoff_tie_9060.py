"""THE LATEST FINAL OF A SHARED KICKOFF STAYS ON THE LEAGUE PAGE — #9060.

═══ WHAT A READER SAW ═══

`/sport/football/ncaaf`, "Showing the 8 most recent", on the night of
2026-09-26: Oregon @ USC (kickoff 23:30Z, final 03:19Z) was missing, while LSU
(final 03:06Z) and NC State (02:59Z) — the same 23:30Z kickoff, both finished
EARLIER — were on the page. `recent_results_query` sorted on
`commence_time DESC` only, so when the eight-row cut fell inside a kickoff tie
the database picked which tied games made it, and "most recent" was a coin toss.

═══ THE FIX ═══

The outer select breaks a kickoff tie on `completed_at DESC NULLS LAST`, then
`id DESC`. The game that ended last wins the tie; a closed row with no stamp
goes behind the stamped ones (Postgres puts NULL FIRST on a bare DESC, which is
why `NULLS LAST` is spelled out); `id` makes the rest deterministic. Nothing
moves inside the `OFFSET 0` fence — `test_league_rails_query_plan` still owns
that, and its regex on the leading key is unchanged.

═══ RED-FIRST ═══

`TestTheOldSortCouldNotDecide` does not depend on how SQLite happens to order
equal keys (it promises nothing). It shows the pre-fix key is EQUAL across the
eighth and ninth rows of this slate — the cut sits inside a tie, so the old sort
had no answer to give — and that the new keys are strictly ordered there. The
slate's ids are laid out so the behavioural tests are red on the plain revert
as well (measured: 9 of 14 fail), not only on a dropped key.
"""

import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

# SQLite cannot render Postgres-native column types. DDL shims for the sqlite
# dialect ONLY — production is Postgres and never reaches them.


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.routes.league_futures import RESULTS_LIMIT, recent_results_query  # noqa: E402

#: A fixed anchor. Offsets from it, never a branch on the clock (gotcha #44).
NOW = datetime(2026, 9, 27, 6, 0, tzinfo=timezone.utc)
LEAGUE = "americanfootball_ncaaf"
S_NCAAF = 1

TIE_KICKOFF = datetime(2026, 9, 26, 23, 30, tzinfo=timezone.utc)

#: Six later kickoffs, each its own instant — they fill slots 1-6 whatever the
#: tie-break is, so the cut at 8 (and the +1 "more" row at 9) lands in the tie.
LATER = [
    (
        301 + i,
        datetime(2026, 9, 27, 2, 30, tzinfo=timezone.utc) - timedelta(minutes=15 * i),
    )
    for i in range(6)
]

LSU = 101  # final 03:06Z
NC_STATE = 102  # final 02:59Z
OREGON_USC = 103  # final 03:19Z — the one that fell off
EARLY_A = 104  # final 02:55Z
EARLY_B = 105  # final 02:50Z
UNSTAMPED = 106  # closed with a score, no completed_at

#: Oregon @ USC holds the MIDDLE id of the five stamped tie games, so neither
#: `id ASC` (SQLite's rowid order for equal keys, the order the pre-fix query
#: happens to return here) nor `id DESC` puts it in the two slots the tie gets.
#: Only the finish time can.
TIE = [
    (LSU, datetime(2026, 9, 27, 3, 6, tzinfo=timezone.utc)),
    (NC_STATE, datetime(2026, 9, 27, 2, 59, tzinfo=timezone.utc)),
    (OREGON_USC, datetime(2026, 9, 27, 3, 19, tzinfo=timezone.utc)),
    (EARLY_A, datetime(2026, 9, 27, 2, 55, tzinfo=timezone.utc)),
    (EARLY_B, datetime(2026, 9, 27, 2, 50, tzinfo=timezone.utc)),
    (UNSTAMPED, None),
]
TIE_IDS = {eid for eid, _ in TIE}

OLDER = 401  # an afternoon game — behind the whole tie


def _row(eid, commence_time, completed_at, status="completed"):
    return Event(
        id=eid,
        sport_id=S_NCAAF,
        external_id=f"ext-{eid}",
        home_team_name=f"Home {eid}",
        away_team_name=f"Away {eid}",
        commence_time=commence_time,
        completed_at=completed_at,
        status=status,
        home_score=21,
        away_score=17,
    )


def _slate(reverse):
    rows = [_row(eid, ct, ct + timedelta(hours=3, minutes=20)) for eid, ct in LATER]
    rows += [
        _row(eid, TIE_KICKOFF, done, "completed" if done else "closed")
        for eid, done in TIE
    ]
    older = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)
    rows.append(_row(OLDER, older, older + timedelta(hours=3)))
    return list(reversed(rows)) if reverse else rows


def _session(reverse):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    s = Session(eng)
    s.add(Sport(id=S_NCAAF, key=LEAGUE, name="NCAAF"))
    # Insertion order is the one thing an undecided tie tends to follow, so
    # every behavioural claim below is checked under BOTH orders.
    for r in _slate(reverse):
        s.add(r)
        s.flush()
    s.commit()
    return s


@pytest.fixture(params=[False, True], ids=["inserted-forward", "inserted-reversed"])
def session(request):
    s = _session(request.param)
    yield s
    s.close()


def _served(session, query=None):
    rows = session.execute(
        query if query is not None else recent_results_query(LEAGUE, NOW)
    )
    return list(rows.scalars().all())


class TestTheOldSortCouldNotDecide:
    """🔴 RED-FIRST: on `commence_time` alone the cut falls inside a tie."""

    def test_the_eighth_and_ninth_rows_share_the_old_key(self, session):
        rows = _served(session)
        assert len(rows) == RESULTS_LIMIT + 1
        eighth, ninth = rows[RESULTS_LIMIT - 1], rows[RESULTS_LIMIT]
        # The pre-fix sort key. Equal here ⇒ the old query had no reason to put
        # one of them on the page and the other behind "more".
        assert eighth.commence_time == ninth.commence_time
        assert {eighth.id, ninth.id} <= TIE_IDS

    def test_the_new_keys_are_strictly_ordered_across_the_cut(self, session):
        rows = _served(session)
        eighth, ninth = rows[RESULTS_LIMIT - 1], rows[RESULTS_LIMIT]
        assert eighth.completed_at > ninth.completed_at


class TestTheLatestFinalMakesThePage:
    def test_oregon_usc_is_among_the_eight_shown(self, session):
        shown = [e.id for e in _served(session)[:RESULTS_LIMIT]]
        assert OREGON_USC in shown

    def test_the_tie_gives_its_two_slots_to_the_two_latest_finishes(self, session):
        rows = _served(session)
        assert [e.id for e in rows[6:RESULTS_LIMIT]] == [OREGON_USC, LSU]
        assert rows[RESULTS_LIMIT].id == NC_STATE  # the "more" row, not lost

    def test_a_tie_reads_latest_finish_first(self, session):
        ids = [
            e.id
            for e in _served(session, recent_results_query(LEAGUE, NOW).limit(None))
        ]
        tie_order = [i for i in ids if i in TIE_IDS]
        assert tie_order == [OREGON_USC, LSU, NC_STATE, EARLY_A, EARLY_B, UNSTAMPED]

    def test_later_kickoffs_still_lead(self, session):
        """Control: the leading key is still the kickoff — a tie-break, not a re-sort."""
        ids = [
            e.id
            for e in _served(session, recent_results_query(LEAGUE, NOW).limit(None))
        ]
        assert ids[:6] == [eid for eid, _ in LATER]
        assert ids[-1] == OLDER


class TestTheStatementPostgresRuns:
    """SQLite sorts NULL last on DESC by itself; Postgres does not. Pin the words."""

    def _sql(self):
        return str(
            recent_results_query(LEAGUE, NOW).compile(dialect=postgresql.dialect())
        )

    def test_outer_order_by_carries_both_tie_breakers_in_order(self):
        outside = self._sql().rsplit(") AS anon_", 1)[1]
        assert re.search(
            r"ORDER BY anon_\d+\.commence_time DESC, "
            r"anon_\d+\.completed_at DESC NULLS LAST, anon_\d+\.id DESC",
            outside,
        ), outside

    def test_nothing_was_added_inside_the_fence(self):
        inside = self._sql().rsplit(") AS anon_", 1)[0]
        assert "ORDER BY" not in inside.upper()
        assert "completed_at DESC" not in inside
