"""The cursor that lets one command sweep a window bigger than one page. #2693.

`DEFAULT_LIMIT` is a router-timeout bound (100) and the window held 685 rows the
day it was measured, so every unpaged call sees a minority of the population and
the rail was only ever runnable by hand, one `--sport` slice at a time. Paging is
what retires that.

Three things paging can get wrong, and one that would be worse than not paging
at all:

* **Skipping a row inside a tie.** `commence_time` is not unique — an NFL Sunday
  puts a dozen fixtures on one kickoff — so a cursor carrying only the clock, or
  an ORDER BY without a tiebreaker, steps over rows silently. Nothing reports
  it: the sweep prints a clean census of the rows it happened to see.
* **Losing a row to the moving floor.** The window starts at `now - lookback`
  and `now` advances during the sweep, so an OFFSET would shift under the sweep
  (gotcha #41). A keyset names a position, not a count.
* **Calling the end of a cursor an empty population.** `no_work` on the last page
  of a sweep reads as an all-clear for the whole window.
* And the preservation obligation: an UNPAGED call must return exactly what it
  returned before this file existed. `truncated` and `eligible` mean what
  lane1/067 made them mean.

The DB tests run the SHIPPED `_load_rows` against a real SQLite database rather
than asserting on a compiled string, so the ORDER BY and the keyset predicate are
exercised by a planner instead of by a regex. `Event` carries JSONB columns that
SQLite cannot render, so the type is shimmed to JSON for DDL only — no test here
reads a JSONB column.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.tasks import reconcile_anchor_schedule as rail
from app.utils.anchor_schedule import AnchoredRow
from app.utils.authority_id_collisions import AuthorityRecord

UTC = timezone.utc

#: A tie, deliberately. Twelve NFL fixtures share one Sunday kickoff, and that
#: is the shape every cursor bug in this file hides inside.
TIE = datetime(2026, 9, 13, 17, 0, tzinfo=UTC)


@compiles(JSONB, "sqlite")
def _jsonb_as_json_for_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL only
    return "JSON"


class _AsyncSessionOverSync:
    """Give a synchronous Session the one `await`able method the rail uses.

    The rail is async and there is no aiosqlite in this sandbox. Wrapping is
    honest where re-implementing would not be: the statement executed is the one
    `_load_rows` built, against a real engine, and the rows come back through
    the real result API.
    """

    def __init__(self, session: Session):
        self._session = session

    async def execute(self, statement):
        return self._session.execute(statement)


@pytest.fixture
def db():
    from app.models.models import Base, Event, Sport

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Event.__table__, Sport.__table__])
    with Session(engine) as session:
        session.add(Sport(id=1, key="americanfootball_nfl", name="NFL"))
        session.commit()
        yield session, _AsyncSessionOverSync(session)


def _insert(session, event_id: int, commence_time: datetime, espn_id: str) -> None:
    from app.models.models import Event

    session.add(
        Event(
            id=event_id,
            sport_id=1,
            espn_id=espn_id,
            home_team_name="Home",
            away_team_name="Away",
            commence_time=commence_time,
            status="scheduled",
        )
    )
    session.commit()


async def _page_through(async_session, *, limit: int) -> list[int]:
    """Walk the whole window with the shipped loader, returning ids in order."""
    seen: list[int] = []
    cursor = None
    while True:
        rows = await rail._load_rows(
            async_session,
            sport=None,
            limit=limit,
            lookback=rail.DEFAULT_LOOKBACK,
            horizon=rail.DEFAULT_HORIZON,
            now=TIE,
            cursor=cursor,
        )
        if not rows:
            return seen
        seen.extend(row.event_id for row in rows)
        last = rows[-1]
        cursor = rail.encode_cursor(last.commence_time, last.event_id)


class TestTheCursorCodec:
    def test_round_trips_both_sort_keys(self):
        cursor = rail.encode_cursor(TIE, 14780147)
        assert rail.decode_cursor(cursor) == (TIE, 14780147)

    def test_a_naive_kickoff_comes_back_as_utc(self):
        """A cursor that lost its tzinfo must not compare against an aware column."""
        naive = rail.encode_cursor(TIE.replace(tzinfo=None), 7)
        moment, event_id = rail.decode_cursor(naive)
        assert (moment, event_id) == (TIE, 7)

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "no-separator-at-all",
            f"not-a-date{rail.CURSOR_SEPARATOR}7",
            f"{TIE.isoformat()}{rail.CURSOR_SEPARATOR}not-an-int",
            f"{rail.CURSOR_SEPARATOR}7",
        ],
    )
    def test_a_malformed_cursor_raises_rather_than_restarting(self, bad):
        """Refused, never ignored.

        Ignoring a bad cursor restarts the sweep at the oldest row, and a driver
        looping until `next_cursor` is None would then loop over page one
        forever while every page reported a healthy census.
        """
        with pytest.raises(ValueError):
            rail.decode_cursor(bad)

    def test_an_id_bearing_separator_survives_because_the_split_is_from_the_right(self):
        """ISO-8601 has no `|`, but the codec must not assume the *kickoff* has none."""
        weird = f"a{rail.CURSOR_SEPARATOR}b"
        with pytest.raises(ValueError):
            rail.decode_cursor(weird)


class TestTheOrderingHasATiebreaker:
    """The tiebreaker cannot be proved behaviourally here, so it is proved directly.

    This started as a behavioural test — five rows on one kickoff, two-row pages,
    assert every row is visited once — and **the mutant survived it**. Deleting
    `Event.id` from the ORDER BY left all 18 tests green, because in SQLite `id`
    IS the rowid: with or without the tiebreaker the engine hands ties back in
    ascending id, so the two orderings are indistinguishable on this database.
    Postgres has no such guarantee — a tie's order there is whatever the plan
    produces, and it can change as rows are updated.

    A green behavioural test would therefore have been worse than no test: it
    would have claimed to guard the tiebreaker while being incapable of seeing
    it go. So the guard reads the ORDER BY the shipped query actually carries.
    It is narrower than a behavioural proof and it says so — but it fails on the
    mutant, which is the whole job.
    """

    def _order_by_of(self, statement) -> list[str]:
        return [str(clause) for clause in statement._order_by_clauses]

    async def test_the_query_orders_by_both_cursor_components(self, db):
        """Both sort keys, in the order the cursor encodes them.

        `encode_cursor` writes `(commence_time, event_id)`. If the query orders
        by anything else, the cursor names a position in an ordering that does
        not exist, and a page boundary inside a tie either repeats rows or steps
        over them — silently, since the census only ever counts what it saw.
        """
        captured = []

        class _Capturing:
            async def execute(self, statement):
                captured.append(statement)

                class _Empty:
                    def all(self):
                        return []

                return _Empty()

        await rail._load_rows(
            _Capturing(),
            sport=None,
            limit=10,
            lookback=rail.DEFAULT_LOOKBACK,
            horizon=rail.DEFAULT_HORIZON,
            now=TIE,
            cursor=None,
        )

        assert self._order_by_of(captured[0]) == ["events.commence_time", "events.id"]

    async def test_the_keyset_predicate_covers_the_tie(self, db):
        """`a > t OR (a = t AND b > i)` — the second half is what walks a tie.

        Without it the predicate is `commence_time > t`, which skips every row
        sharing the cursor's kickoff: an NFL Sunday would lose eleven fixtures
        at one page boundary.
        """
        predicate = rail._after_cursor(rail.encode_cursor(TIE, 14780147))

        rendered = str(predicate[0]).replace("\n", " ")
        assert "events.commence_time >" in rendered
        assert "events.commence_time =" in rendered
        assert "events.id >" in rendered


class TestNoRowIsSkippedOrRepeated:
    async def test_every_row_in_a_tie_is_visited_exactly_once(self, db):
        """Five rows on one kickoff, two per page — two boundaries inside the tie.

        This does NOT prove the ORDER BY tiebreaker (see the class above); on
        SQLite it passes either way. What it does prove is the other half: the
        keyset predicate walks *through* a tie rather than jumping over it, and
        the page boundaries neither repeat nor drop a row.
        """
        session, async_session = db
        ids = [14780147, 14780148, 14780149, 14780150, 14781140]
        for offset, event_id in enumerate(ids):
            _insert(session, event_id, TIE, f"4018730{offset:02d}")

        seen = await _page_through(async_session, limit=2)

        assert seen == sorted(ids), "a page boundary inside a tie lost or repeated rows"
        assert len(seen) == len(set(seen))

    async def test_paging_and_one_big_page_see_the_same_population(self, db):
        """Paging may change how many calls it takes, never what is examined."""
        session, async_session = db
        ids = list(range(14780140, 14780152))
        for offset, event_id in enumerate(ids):
            # Half on a shared kickoff, half spread out: a mix is the only
            # arrangement that exercises both branches of the keyset predicate.
            when = TIE if offset % 2 else TIE + timedelta(days=offset)
            _insert(session, event_id, when, f"4018731{offset:02d}")

        paged = await _page_through(async_session, limit=3)
        single = await _page_through(async_session, limit=1000)

        assert paged == single
        assert len(paged) == len(ids)

    async def test_the_cursor_is_exclusive(self, db):
        """The row the cursor names is behind us; seeing it again is a repeat."""
        session, async_session = db
        _insert(session, 14780147, TIE, "401873001")
        _insert(session, 14780148, TIE, "401873002")

        rows = await rail._load_rows(
            async_session,
            sport=None,
            limit=10,
            lookback=rail.DEFAULT_LOOKBACK,
            horizon=rail.DEFAULT_HORIZON,
            now=TIE,
            cursor=rail.encode_cursor(TIE, 14780147),
        )

        assert [row.event_id for row in rows] == [14780148]


class TestAPagedRunNeverSaysNoWork:
    """`no_work` is an all-clear. Only a call that saw the whole window earns it."""

    def _wire(self, monkeypatch, rows, *, eligible, remaining):
        async def _load_rows(session, **kwargs):
            return list(rows)

        async def _count_eligible(session, **kwargs):
            return remaining if kwargs.get("cursor") else eligible

        async def _fetch_record(service, sport_keys, authority_id):
            return AuthorityRecord(
                authority_id=authority_id,
                home_names=frozenset({"home"}),
                away_names=frozenset({"away"}),
                starts_at=TIE,
                label="Away v Home",
            )

        monkeypatch.setattr(rail, "_load_rows", _load_rows)
        monkeypatch.setattr(rail, "_count_eligible", _count_eligible)
        monkeypatch.setattr(
            "app.tasks.repair_authority_id_collisions._fetch_record", _fetch_record
        )
        monkeypatch.setattr("app.services.espn_api.get_espn_service", lambda: object())

    def _row(self, event_id=14780147):
        return AnchoredRow(
            event_id=event_id,
            sport_key="americanfootball_nfl",
            home_team_name="Home",
            away_team_name="Away",
            espn_id="401873001",
            commence_time=TIE,
            status="scheduled",
            completed_at=None,
            commence_time_source="espn",
        )

    async def test_a_cursor_past_the_end_is_partial_not_no_work(self, monkeypatch):
        """Reaching the end of a cursor is not discovering an empty population."""
        self._wire(monkeypatch, [], eligible=685, remaining=0)

        result = await rail.reconcile(
            object(), cursor=rail.encode_cursor(TIE, 14780147)
        )

        assert result["terminal"] == "partial"
        assert result["terminal"] != "no_work"
        assert result["next_cursor"] is None
        assert result["has_more"] is False

    async def test_an_empty_window_with_no_cursor_still_says_no_work(self, monkeypatch):
        """The control. The old reading survives for the case it was true of."""
        self._wire(monkeypatch, [], eligible=0, remaining=0)

        result = await rail.reconcile(object())

        assert result["terminal"] == "no_work"

    async def test_a_last_page_that_agrees_is_still_partial(self, monkeypatch):
        """Everything on this page agreed — but this page is not the window."""
        self._wire(monkeypatch, [self._row()], eligible=685, remaining=1)

        result = await rail.reconcile(
            object(), cursor=rail.encode_cursor(TIE - timedelta(days=1), 1)
        )

        assert result["by_verdict"]["agrees"] == 1
        assert result["has_more"] is False, "nothing follows this page"
        assert result["truncated"] is True, "yet it saw 1 of 685"
        assert result["terminal"] == "partial"


class TestTheUnpagedReadingIsUnchanged:
    """lane1/067 gave `eligible` and `truncated` their meaning. Paging kept it."""

    def _wire(self, monkeypatch, rows, eligible):
        async def _load_rows(session, **kwargs):
            return list(rows)

        async def _count_eligible(session, **kwargs):
            return eligible

        async def _fetch_record(service, sport_keys, authority_id):
            return None

        monkeypatch.setattr(rail, "_load_rows", _load_rows)
        monkeypatch.setattr(rail, "_count_eligible", _count_eligible)
        monkeypatch.setattr(
            "app.tasks.repair_authority_id_collisions._fetch_record", _fetch_record
        )
        monkeypatch.setattr("app.services.espn_api.get_espn_service", lambda: object())

    def _row(self, event_id):
        return AnchoredRow(
            event_id=event_id,
            sport_key="americanfootball_nfl",
            home_team_name="Home",
            away_team_name="Away",
            espn_id=f"4018730{event_id % 100:02d}",
            commence_time=TIE,
            status="scheduled",
            completed_at=None,
            commence_time_source="espn",
        )

    async def test_page_one_reports_remaining_equal_to_eligible(self, monkeypatch):
        """The preservation proof.

        `truncated` is `eligible > examined` and `remaining == eligible` on an
        uncursored call, so a caller who never pages cannot observe that paging
        was added.
        """
        self._wire(monkeypatch, [self._row(1), self._row(2)], eligible=685)

        result = await rail.reconcile(object())

        assert result["remaining"] == result["eligible"] == 685
        assert result["truncated"] is True
        assert result["has_more"] is True

    async def test_a_complete_unpaged_pass_offers_no_cursor(self, monkeypatch):
        self._wire(monkeypatch, [self._row(1), self._row(2)], eligible=2)

        result = await rail.reconcile(object())

        assert result["truncated"] is False
        assert result["has_more"] is False
        assert result["next_cursor"] is None


class TestTheOperatorLineNamesTheRightRemedy:
    def test_mid_sweep_it_hands_over_the_cursor(self):
        line = rail.summarize_for_operator(
            {
                "measured": True,
                "terminal": "partial",
                "examined": 100,
                "eligible": 685,
                "remaining": 685,
                "has_more": True,
                "next_cursor": "CURSOR-HERE",
                "by_verdict": {},
            }
        )

        assert "CURSOR-HERE" in line
        assert "585 after this page" in line

    def test_on_the_last_page_it_does_not_tell_you_to_raise_the_limit(self):
        """There is nothing left to see; advising a bigger page wastes a command."""
        line = rail.summarize_for_operator(
            {
                "measured": True,
                "terminal": "partial",
                "examined": 85,
                "eligible": 685,
                "remaining": 85,
                "truncated": True,
                "has_more": False,
                "next_cursor": None,
                "by_verdict": {},
            }
        )

        assert "TAIL" in line
        assert "raise limit" not in line
