"""A FABRICATED 0 - 0 IS REPLACED BY THE AUTHORITY'S SCORE OR BY NOTHING — #5841.

═══ WHY THIS SUITE EXISTS ═══

A search for "Yankees" on the launch candidate answers with

    New York Yankees vs Boston Red Sox      0 - 0     MLB  FINAL

and a nine-inning baseball game cannot end 0 - 0. 98 rows across the table make
that claim (18 inside #5841's own 45-day window), and nothing that runs today
can find them again: `backfill_missing_scores`, the pass whose whole job is "a
finished row with no score", selects `home_score IS NULL AND away_score IS NULL`
and these rows carry a `0`.

So the repair is a script, and the danger a script of this shape carries is not
that it misses rows — it is that it writes a plausible wrong number. THE REAL
SPECIMEN PROVES IT: event `14877917` is a 2026-08-29 Yankees–Red Sox card
carrying `espn_id='401815659'`, and that summary is a **2026-06-07** game. A
repair that trusted the stamped anchor would have written `6 - 1` onto an August
card, and every surface would have agreed it looked fixed.

This suite therefore asserts the RULE the script is built on:

    a score is written only when the authority's own answer, for this row's own
    anchor, is a FINISHED game between these two clubs on this row's own date —
    and where it is not, the row is left exactly as it is

═══ WHAT IS DELIBERATELY NOT ASSERTED HERE ═══

Which of two duplicate rows a page SERVES. Two of this cohort's three twin rows
are already invisible because `fold_twin_events` elects the ESPN-anchored
sibling; the third is a serve-time election defect in that helper (lane1's file
under D39, routed with a reproduction). This file asserts only that the repair
REFUSES a row whose fixture another row already holds — writing the result twice
is a worse defect than the 0 - 0 it would replace.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, selectinload

# SQLite cannot render Postgres-native column types. DDL shims for the sqlite
# dialect ONLY — production is Postgres and never reaches them. Without them
# `events` cannot be created and this module degrades to shape-only coverage,
# which for a claim about which ROWS move would be no coverage at all.


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.utils.event_completion import SETTLED_STATUSES  # noqa: E402
from scripts.repair_5841_zero_zero_finals_from_the_authority import (  # noqa: E402
    ANCHOR_MAX_HOURS,
    _BAK_DDL,
    _BANK_SQL,
    DRAW_CAPABLE_PREFIXES,
    MAX_EXPECTED_POPULATION,
    MIN_EXPECTED_POPULATION,
    _CANDIDATES_SQL,
    _SCORED_TWIN_SQL,
    _WRITE_SQL,
    anchor_refusal_reason,
    candidate_refusal_reason,
    horizon_floor,
    population_refusal_reason,
    statement,
    write_statement,
)
from scripts.restore_5841_zero_zero_finals_from_the_authority import (  # noqa: E402
    _PLAN_SQL,
    _RESTORE_SQL,
    restore_params,
    restore_refusal_reason,
)


class _AsyncSession:
    """An `await`-able face on the corpus's synchronous sqlite session.

    The pass is async and the corpus is not. Three methods is the whole surface
    `_run_inner` touches, so this is an adapter rather than a mock: every
    statement it runs is the shipped statement, against a real engine.
    """

    def __init__(self, session):
        self._session = session

    async def execute(self, *args, **kwargs):
        return self._session.execute(*args, **kwargs)

    async def commit(self):
        self._session.commit()

    async def rollback(self):
        self._session.rollback()

NOW = datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc)
FLOOR = horizon_floor(NOW)

S_MLB, S_TENNIS, S_SOCCER = 1, 2, 3

#: The four rows the repair exists to write, verbatim from production
#: 2026-09-16 06:4xZ — id, clubs, the row's own (wrong) clock, the anchor, and
#: what ESPN's summary for that anchor actually says.
SHAPE_A = [
    (15201192, "Baltimore Orioles", "New York Yankees", datetime(2026, 8, 18, 18, 35), "401816574",
     datetime(2026, 8, 18, 22, 35), 1, 3),
    (15201193, "Cleveland Guardians", "San Francisco Giants", datetime(2026, 8, 18, 18, 40), "401816576",
     datetime(2026, 8, 18, 22, 40), 8, 1),
    (15201194, "Tampa Bay Rays", "Toronto Blue Jays", datetime(2026, 8, 18, 18, 40), "401816578",
     datetime(2026, 8, 18, 22, 40), 5, 10),
    (15201195, "Milwaukee Brewers", "Seattle Mariners", datetime(2026, 8, 18, 19, 40), "401816583",
     datetime(2026, 8, 18, 23, 40), 22, 0),
]

#: The row whose stamped anchor is 83 days from its own kick-off.
BORROWED_ID = 14877917
BORROWED_COMMENCE = datetime(2026, 8, 29, 17, 5, tzinfo=timezone.utc)
BORROWED_ANCHOR_DATE = datetime(2026, 6, 7, 17, 35, tzinfo=timezone.utc)


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _event(eid, home, away, commence, *, sport_id=S_MLB, status="closed",
           score=(0, 0), espn_id=None, **kw):
    home_score, away_score = score
    fields = dict(
        id=eid, sport_id=sport_id, external_id=f"ext-{eid}",
        home_team_name=home, away_team_name=away, commence_time=_aware(commence),
        status=status, home_score=home_score, away_score=away_score, espn_id=espn_id,
    )
    fields.update(kw)
    return Event(**fields)


def _anchor(*, date, home, away, home_score, away_score, status="post",
            stopped_without_result=False):
    """An `ESPNEvent`-shaped answer. Shaped, not mocked: `anchor_refusal_reason`
    reads six attributes and a double carrying those six is the whole contract."""
    return NS(
        date=_aware(date), status=status, stopped_without_result=stopped_without_result,
        home_team=NS(display_name=home, name=home.split()[-1]),
        away_team=NS(display_name=away, name=away.split()[-1]),
        home_score=home_score, away_score=away_score,
    )


@pytest.fixture
def corpus():
    """A real engine executing the real plan SQL and the real UPDATE.

    Function-scoped, not module-scoped: the write tests MUTATE it, and a mutated
    module fixture is how a later test starts passing for the wrong reason.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Sport(id=S_MLB, key="baseball_mlb", name="MLB"),
            Sport(id=S_TENNIS, key="tennis_atp_us_open", name="US Open"),
            Sport(id=S_SOCCER, key="soccer_epl", name="EPL"),
        ])
        for eid, home, away, commence, espn_id, _d, _h, _a in SHAPE_A:
            session.add(_event(eid, home, away, commence, espn_id=espn_id))
        # Shape B — the borrowed anchor, and the sibling that holds the result.
        session.add(_event(BORROWED_ID, "New York Yankees", "Boston Red Sox",
                           BORROWED_COMMENCE, espn_id="401815659"))
        session.add(_event(15295242, "New York Yankees", "Boston Red Sox",
                           BORROWED_COMMENCE, status="completed", score=(0, 6),
                           espn_id="401874913"))
        # Shape C — tennis, `completed`, no anchor to ask (#2772's).
        session.add(_event(15293847, "Rafael Jodar", "Thanasi Kokkinakis",
                           datetime(2026, 9, 1, 16, 0), sport_id=S_TENNIS,
                           status="completed"))
        # A real scoreless draw, and a scheduled row, and a scored row.
        session.add(_event(90001, "Everton", "Fulham", datetime(2026, 9, 10, 14, 0),
                           sport_id=S_SOCCER, status="completed", espn_id="700001"))
        session.add(_event(90002, "Chicago Cubs", "St. Louis Cardinals",
                           datetime(2026, 9, 14, 18, 0), status="scheduled",
                           score=(None, None), espn_id="700002"))
        session.add(_event(90003, "Chicago Cubs", "Milwaukee Brewers",
                           datetime(2026, 9, 14, 18, 0), status="completed",
                           score=(4, 2), espn_id="700003"))
        session.commit()
        yield session


def _planned_ids(session, floor=None):
    """Every id the PURE predicate selects, over the real rows.

    `selectinload(Event.sport)` is not convenience: `row_sport_key` reads the
    relationship through the repo's lazy-SAFE helper, which answers `None` for an
    UNLOADED relationship rather than emitting IO. The plan query on production
    selects `s.key` in the same row, so a corpus that leaves `sport` unloaded is
    asking the predicate a question production never asks it — and the draw-
    capable clause would read as "not soccer" for every row.
    """
    rows = session.execute(select(Event).options(selectinload(Event.sport))).scalars().all()
    return {
        row.id
        for row in rows
        if candidate_refusal_reason(row, floor=floor or FLOOR) is None
    }


def _sql_ids(session):
    """Every id the shipped plan SQL selects — the statement the dyno runs."""
    return {
        row.id
        for row in session.execute(
            statement(_CANDIDATES_SQL),
            {"settled": sorted(SETTLED_STATUSES), "floor": FLOOR},
        ).all()
    }


class TestThePopulation:
    """Who is even asked about."""

    def test_the_plan_and_the_shipped_sql_select_the_same_rows(self, corpus):
        # A repair whose plan and whose UPDATE are two independent readings of
        # "which rows" is how a sweep quietly moves a row nobody adjudicated.
        assert _planned_ids(corpus) == _sql_ids(corpus)

    def test_the_four_anchored_rows_and_the_borrowed_one_are_candidates(self, corpus):
        assert _sql_ids(corpus) == {eid for eid, *_ in SHAPE_A} | {BORROWED_ID}

    def test_a_real_scoreless_draw_is_never_a_candidate(self, corpus):
        # The soccer row is `completed`, 0 - 0, anchored and inside the window:
        # it passes every clause EXCEPT the sport one, which is the clause that
        # keeps a genuine nil-nil out.
        assert 90001 not in _sql_ids(corpus)
        row = corpus.execute(
            select(Event).options(selectinload(Event.sport)).where(Event.id == 90001)
        ).scalar_one()
        reason = candidate_refusal_reason(row, floor=FLOOR)
        assert reason and "0 - 0" in reason

    def test_every_draw_capable_prefix_is_excluded_by_the_sql_too(self, corpus):
        # The Python list and the LIKE clauses are generated from one constant;
        # this fails if somebody adds a prefix to one spelling only.
        for prefix in DRAW_CAPABLE_PREFIXES:
            assert f"'{prefix}%'" in _CANDIDATES_SQL

    def test_the_tennis_rows_are_not_candidates_because_nothing_can_be_asked(self, corpus):
        assert 15293847 not in _sql_ids(corpus)
        reason = candidate_refusal_reason(corpus.get(Event, 15293847), floor=FLOOR)
        assert reason and "ESPN anchor" in reason

    def test_an_unsettled_row_is_not_a_candidate(self, corpus):
        assert 90002 not in _sql_ids(corpus)

    def test_a_row_that_already_has_a_result_is_not_a_candidate(self, corpus):
        assert 90003 not in _sql_ids(corpus)

    def test_the_window_excludes_what_it_says_it_excludes(self, corpus):
        old = _event(90004, "Chicago Cubs", "New York Mets",
                     NOW - timedelta(days=200), espn_id="700004")
        corpus.add(old)
        corpus.commit()
        assert 90004 not in _sql_ids(corpus)
        assert _planned_ids(corpus) == _sql_ids(corpus)

    def test_all_time_reaches_the_row_the_default_window_declines(self, corpus):
        corpus.add(_event(90004, "Chicago Cubs", "New York Mets",
                          NOW - timedelta(days=200), espn_id="700004"))
        corpus.commit()
        all_time = horizon_floor(NOW, 0)
        ids = {
            row.id
            for row in corpus.execute(
                statement(_CANDIDATES_SQL),
                {"settled": sorted(SETTLED_STATUSES), "floor": all_time},
            ).all()
        }
        assert 90004 in ids


class TestTheAuthorityDecides:
    """Nothing but ESPN's own answer, for this row's own anchor, writes a score."""

    @pytest.mark.parametrize("eid,home,away,commence,espn_id,anchor_date,hs,a_s", SHAPE_A)
    def test_each_real_specimen_is_cashable_and_writes_its_real_score(
        self, corpus, eid, home, away, commence, espn_id, anchor_date, hs, a_s
    ):
        row = corpus.get(Event, eid)
        anchor = _anchor(date=anchor_date, home=home, away=away,
                         home_score=hs, away_score=a_s)
        assert anchor_refusal_reason(row, anchor) is None
        # The row's clock is four hours out from the authority's — that is a
        # separate defect and it must NOT cost the repair its specimen.
        gap = abs((_aware(anchor_date) - _aware(commence)).total_seconds()) / 3600
        assert 0 < gap <= ANCHOR_MAX_HOURS

    def test_the_borrowed_anchor_is_refused_on_its_date(self, corpus):
        # THE SPECIMEN THIS WHOLE FILE IS ABOUT. The summary is a real, finished
        # Yankees–Red Sox game with a real score — it is simply a DIFFERENT one.
        row = corpus.get(Event, BORROWED_ID)
        reason = anchor_refusal_reason(
            row,
            _anchor(date=BORROWED_ANCHOR_DATE, home="New York Yankees",
                    away="Boston Red Sox", home_score=6, away_score=1),
        )
        assert reason and "anchor_is_a_different_date" in reason

    def test_a_date_check_that_passed_would_have_written_the_june_score(self, corpus):
        # The mutation this test kills, stated as a fact rather than a hope: with
        # the date clause gone, everything else about the borrowed anchor agrees
        # and the repair writes 6 - 1 onto the August card.
        row = corpus.get(Event, BORROWED_ID)
        anchor = _anchor(date=BORROWED_ANCHOR_DATE, home="New York Yankees",
                         away="Boston Red Sox", home_score=6, away_score=1)
        assert anchor_refusal_reason(row, anchor, max_hours=24 * 365) is None

    def test_a_different_fixture_on_the_right_date_is_refused(self, corpus):
        row = corpus.get(Event, 15201192)
        reason = anchor_refusal_reason(
            row,
            _anchor(date=datetime(2026, 8, 18, 22, 35), home="Detroit Tigers",
                    away="New York Yankees", home_score=4, away_score=2),
        )
        assert reason and "anchor_is_a_different_game" in reason

    def test_the_same_two_clubs_the_other_way_round_is_refused(self, corpus):
        # The other half of a home-and-away pair is not this game, and its score
        # read onto our orientation is the scoreline backwards.
        row = corpus.get(Event, 15201192)
        reason = anchor_refusal_reason(
            row,
            _anchor(date=datetime(2026, 8, 18, 22, 35), home="New York Yankees",
                    away="Baltimore Orioles", home_score=3, away_score=1),
        )
        assert reason and "anchor_is_a_different_game" in reason

    def test_a_postponement_carrying_a_score_is_refused(self, corpus):
        row = corpus.get(Event, 15201192)
        reason = anchor_refusal_reason(
            row,
            _anchor(date=datetime(2026, 8, 18, 22, 35), home="Baltimore Orioles",
                    away="New York Yankees", home_score=1, away_score=0,
                    stopped_without_result=True),
        )
        assert reason and "anchor_is_not_final" in reason

    def test_a_game_still_in_progress_is_refused(self, corpus):
        row = corpus.get(Event, 15201192)
        reason = anchor_refusal_reason(
            row,
            _anchor(date=datetime(2026, 8, 18, 22, 35), home="Baltimore Orioles",
                    away="New York Yankees", home_score=1, away_score=0, status="in"),
        )
        assert reason and "anchor_is_not_final" in reason

    def test_an_authority_confirmed_nil_nil_writes_nothing(self, corpus):
        # The only answer that can tell a fabricated 0 - 0 from a real one, and
        # it must not be reported as a failure.
        row = corpus.get(Event, 15201192)
        reason = anchor_refusal_reason(
            row,
            _anchor(date=datetime(2026, 8, 18, 22, 35), home="Baltimore Orioles",
                    away="New York Yankees", home_score=0, away_score=0),
        )
        assert reason and "authority_confirms_0_0" in reason

    def test_silence_is_not_an_answer(self, corpus):
        # gotcha #53 — an empty answer is a response shape, not an absence.
        reason = anchor_refusal_reason(corpus.get(Event, 15201192), None)
        assert reason and "espn_unreachable" in reason


class TestTheTwinIsRefusedNotRepaired:
    """A fixture another row already holds is never published twice."""

    def _twins(self, session, eid):
        row = session.get(Event, eid)
        return session.execute(
            text(_SCORED_TWIN_SQL),
            {
                "eid": row.id, "sport_id": row.sport_id,
                "lo": _aware(row.commence_time) - timedelta(hours=ANCHOR_MAX_HOURS),
                "hi": _aware(row.commence_time) + timedelta(hours=ANCHOR_MAX_HOURS),
                "home": row.home_team_name, "away": row.away_team_name,
            },
        ).all()

    def test_the_same_minute_sibling_is_found(self, corpus):
        found = self._twins(corpus, BORROWED_ID)
        assert [r.id for r in found] == [15295242]

    def test_two_rows_cannot_share_an_anchor_so_that_arm_is_not_written(self, corpus):
        # The borrowed-identity shape (#6215) would be the obvious second arm of
        # the twin query. It is absent because the database refuses the state:
        # `uq_events_espn_id` is UNIQUE over every non-null `espn_id`, and 0
        # espn_ids sit on more than one row in production (measured 2026-09-16).
        # This test is what stops somebody adding an unreachable suppressing arm
        # back — if the index is ever relaxed, this fails and the decision is
        # reopened deliberately.
        corpus.add(_event(90010, "Somebody", "Else", datetime(2026, 5, 1, 12, 0),
                          status="completed", score=(2, 1), espn_id="401816574"))
        with pytest.raises(IntegrityError):
            corpus.commit()
        corpus.rollback()
        assert "espn_id" not in _SCORED_TWIN_SQL

    def test_a_zero_zero_sibling_does_not_count_as_holding_the_result(self, corpus):
        # Otherwise two rows of this very cohort veto each other and the pass
        # refuses the population it exists for.
        corpus.add(_event(90011, "Baltimore Orioles", "New York Yankees",
                          datetime(2026, 8, 18, 18, 35), espn_id="700011"))
        corpus.commit()
        assert self._twins(corpus, 15201192) == []

    def test_the_next_day_game_between_the_same_clubs_is_not_a_twin(self, corpus):
        # A club plays the same opponent on consecutive days as a matter of
        # routine; the real 08-19 Orioles–Yankees game is +28h and must not veto
        # the 08-18 repair.
        corpus.add(_event(15200817, "Baltimore Orioles", "New York Yankees",
                          datetime(2026, 8, 19, 22, 35), status="closed",
                          score=(2, 3), espn_id="700817"))
        corpus.commit()
        assert self._twins(corpus, 15201192) == []


class TestTheAdjudicatorIsWiredToBoth:
    """The verdict a row actually gets — the twin read AND the anchor read.

    The two classes above prove the twin query finds the sibling and the anchor
    rule refuses the borrowed id. Neither proves the PASS consults them, and a
    repair whose guards are unit-tested but unwired is the shape that ships.
    """

    class _Session:
        """Just enough session for `scored_twin`: one `execute(...).first()`."""

        def __init__(self, real, calls):
            self._real, self._calls = real, calls

        async def execute(self, sql, params):
            self._calls.append("twin")
            return self._real.execute(sql, params)

    class _ESPN:
        def __init__(self, anchor, calls):
            self._anchor, self._calls = anchor, calls

        async def get_event(self, sport_key, espn_id):
            self._calls.append(("espn", sport_key, espn_id))
            return self._anchor

    def _verdict(self, corpus, eid, anchor):
        import asyncio

        from scripts.repair_5841_zero_zero_finals_from_the_authority import adjudicate

        calls: list = []
        row = corpus.execute(
            text(
                "SELECT id, status, home_score, away_score, espn_id, home_team_name, "
                "away_team_name, commence_time, sport_id FROM events WHERE id = :eid"
            ),
            {"eid": eid},
        ).one()
        row = NS(**dict(row._mapping), sport_key="baseball_mlb")
        verdict = asyncio.run(
            adjudicate(self._Session(corpus, calls), self._ESPN(anchor, calls), row)
        )
        return verdict, calls

    def test_an_anchored_row_with_no_twin_is_written_from_the_authority(self, corpus):
        verdict, calls = self._verdict(
            corpus, 15201192,
            _anchor(date=datetime(2026, 8, 18, 22, 35), home="Baltimore Orioles",
                    away="New York Yankees", home_score=1, away_score=3),
        )
        assert verdict["verdict"] == "WRITE"
        assert (verdict["home_score"], verdict["away_score"]) == (1, 3)
        assert any(c[0] == "espn" for c in calls if isinstance(c, tuple))

    def test_a_row_whose_sibling_holds_the_result_is_refused_without_asking_espn(self, corpus):
        # 14877917's sibling 15295242 is the same fixture at the same minute,
        # `completed`, 0 - 6. The refusal is reached BEFORE the fetch, which is
        # both the safety claim and the reason the pass is cheap.
        verdict, calls = self._verdict(
            corpus, BORROWED_ID,
            _anchor(date=BORROWED_ANCHOR_DATE, home="New York Yankees",
                    away="Boston Red Sox", home_score=6, away_score=1),
        )
        assert verdict["verdict"] == "REFUSED"
        assert "scored_twin_exists" in verdict["reason"]
        assert not [c for c in calls if isinstance(c, tuple) and c[0] == "espn"]

    def test_a_row_with_no_twin_and_a_borrowed_anchor_is_still_refused(self, corpus):
        # Remove the sibling and the date clause is the only thing left standing
        # between an August card and a June scoreline.
        corpus.execute(text("DELETE FROM events WHERE id = 15295242"))
        corpus.commit()
        verdict, _ = self._verdict(
            corpus, BORROWED_ID,
            _anchor(date=BORROWED_ANCHOR_DATE, home="New York Yankees",
                    away="Boston Red Sox", home_score=6, away_score=1),
        )
        assert verdict["verdict"] == "REFUSED"
        assert "anchor_is_a_different_date" in verdict["reason"]


class TestTheWrite:
    """The UPDATE re-checks the row it adjudicated, not just its id."""

    def _write(self, session, eid, home_score, away_score, **override):
        row = session.get(Event, eid)
        params = {
            "eid": eid, "home_score": home_score, "away_score": away_score,
            "status": row.status, "espn_id": row.espn_id,
        }
        params.update(override)
        result = session.execute(write_statement(), params)
        session.commit()
        return result.rowcount

    def test_it_writes_the_authority_score(self, corpus):
        assert self._write(corpus, 15201192, 1, 3) == 1
        corpus.expire_all()
        row = corpus.get(Event, 15201192)
        assert (row.home_score, row.away_score) == (1, 3)

    def test_a_row_that_gained_a_real_score_since_the_plan_is_untouched(self, corpus):
        # The plan is built once and the sweep then takes minutes on a write-hot
        # table. A live pass landing 5 - 4 in that window must win.
        row = corpus.get(Event, 15201192)
        row.home_score, row.away_score = 5, 4
        corpus.commit()
        assert self._write(corpus, 15201192, 1, 3) == 0
        corpus.expire_all()
        assert (corpus.get(Event, 15201192).home_score,
                corpus.get(Event, 15201192).away_score) == (5, 4)

    def test_a_row_unsettled_since_the_plan_is_untouched(self, corpus):
        # `espn_helpers` writes `status='live', completed_at=NULL` when ESPN
        # reports `in` on a settled row (a replay, or a premature settle).
        row = corpus.get(Event, 15201192)
        row.status = "live"
        corpus.commit()
        assert self._write(corpus, 15201192, 1, 3, status="closed") == 0

    def test_a_row_whose_anchor_was_restamped_since_the_plan_is_untouched(self, corpus):
        row = corpus.get(Event, 15201192)
        row.espn_id = "401999999"
        corpus.commit()
        assert self._write(corpus, 15201192, 1, 3, espn_id="401816574") == 0

    def test_the_write_names_only_the_two_score_columns(self):
        # `status`, `completed_at` and `period` are knowingly left — see the
        # script's docstring. This fails if a later edit widens the SET clause.
        set_clause = _WRITE_SQL.split("SET", 1)[1].split("WHERE", 1)[0]
        assert "home_score" in set_clause and "away_score" in set_clause
        for column in ("status", "completed_at", "period", "espn_id"):
            assert f"{column} =" not in set_clause


class TestTheUndo:
    """CERT-2947. The undo restores what the repair wrote, and NOTHING ELSE.

    The blocked version banked only the pre-image, so it had to infer "is this
    row still repaired?" from "the current score differs from the banked 0 - 0"
    — which is equally true of a row the repair wrote 1 - 3 onto and of a row the
    AUTHORITY later corrected to 2 - 4. The grader changed a repaired row to
    2 - 4, ran the committed statement, and it wrote 0 - 0 back with rowcount 1.

    Both branches are executed here, the second on that exact specimen.
    """

    def _bank(self, session, eid, *, old, new):
        session.execute(text(_BAK_DDL))
        session.execute(text(_BANK_SQL), {
            "eid": eid, "old_home_score": old[0], "old_away_score": old[1],
            "old_status": "closed", "new_home_score": new[0], "new_away_score": new[1],
        })
        session.commit()

    def _repair(self, session, eid, new):
        row = session.get(Event, eid)
        row.home_score, row.away_score = new
        session.commit()

    def _restore(self, session):
        """The shipped plan, the shipped DECISION and the shipped CAS.

        `restore_refusal_reason` is CALLED, never restated: a test that
        re-implements the decision passes on a script whose decision has been
        inverted back to the blocked form, which is exactly what a mutant does.
        """
        restored, skipped = 0, []
        for row in session.execute(text(_PLAN_SQL)).all():
            if restore_refusal_reason(row):
                skipped.append(row.event_id)
                continue
            result = session.execute(text(_RESTORE_SQL), restore_params(row))
            session.commit()
            restored += result.rowcount or 0
        return restored, skipped

    def test_an_untouched_repair_is_put_back(self, corpus):
        self._bank(corpus, 15201192, old=(0, 0), new=(1, 3))
        self._repair(corpus, 15201192, (1, 3))
        assert self._restore(corpus) == (1, [])
        corpus.expire_all()
        row = corpus.get(Event, 15201192)
        assert (row.home_score, row.away_score) == (0, 0)

    def test_a_row_the_authority_corrected_after_the_repair_is_NOT_put_back(self, corpus):
        # The grader's reproduction, verbatim: repaired to 1 - 3, then a newer
        # authoritative 2 - 4 lands. The undo must leave it alone — restoring
        # 0 - 0 here destroys newer truth AND restores the reader defect.
        self._bank(corpus, 15201192, old=(0, 0), new=(1, 3))
        self._repair(corpus, 15201192, (1, 3))
        self._repair(corpus, 15201192, (2, 4))  # the authority, later
        assert self._restore(corpus) == (0, [15201192])
        corpus.expire_all()
        row = corpus.get(Event, 15201192)
        assert (row.home_score, row.away_score) == (2, 4)

    def test_a_half_corrected_row_is_skipped_too(self, corpus):
        self._bank(corpus, 15201192, old=(0, 0), new=(1, 3))
        self._repair(corpus, 15201192, (1, 5))
        assert self._restore(corpus) == (0, [15201192])

    def test_the_cas_binds_the_banked_post_image_and_not_the_current_score(self):
        # The defect was in the BINDING, so this reads the statement itself: the
        # WHERE must compare against `:new_*`, which only the backup row can
        # supply. A `:written_*`-style bind fed from the event row is what made
        # the old WHERE a tautology.
        where = _RESTORE_SQL.split("WHERE", 1)[1]
        assert ":new_home_score" in where and ":new_away_score" in where
        assert "now_" not in where and "written_" not in where

    def test_the_backup_banks_both_images(self):
        for column in ("old_home_score", "old_away_score", "new_home_score", "new_away_score"):
            assert column in _BAK_DDL and column in _BANK_SQL
        # NOT NULL on the post-image: a banked row that cannot say what was
        # written is a restore point that has to guess again.
        assert "new_home_score integer NOT NULL" in _BAK_DDL
        assert "new_away_score integer NOT NULL" in _BAK_DDL

    def test_apply_banks_both_images_BEFORE_it_writes_run_end_to_end(self, corpus):
        # The whole pass, driven over the corpus with a stub authority: plan →
        # bank → write. Asserted by READING the backup table afterwards, because
        # "the banking is unconditional" is a claim about a call happening and
        # only an executed pass can make it.
        import asyncio

        import scripts.repair_5841_zero_zero_finals_from_the_authority as repair

        anchors = {
            espn_id: _anchor(date=anchor_date, home=home, away=away,
                             home_score=hs, away_score=a_s)
            for _eid, home, away, _c, espn_id, anchor_date, hs, a_s in SHAPE_A
        }

        class ESPN:
            async def get_event(self, sport_key, espn_id):
                return anchors.get(espn_id)

        code = asyncio.run(
            repair._run_inner(
                espn=ESPN(), params={"settled": sorted(SETTLED_STATUSES), "floor": FLOOR},
                only_ids=None, apply=True, default_window=False,
                session=_AsyncSession(corpus),
            )
        )
        assert code == 0

        corpus.expire_all()
        for eid, _h, _a, _c, _espn, _d, hs, a_s in SHAPE_A:
            row = corpus.get(Event, eid)
            assert (row.home_score, row.away_score) == (hs, a_s), eid
        banked = {
            r.event_id: (r.old_home_score, r.old_away_score, r.new_home_score, r.new_away_score)
            for r in corpus.execute(text(f"SELECT * FROM {repair.BAK_TABLE}")).all()
        }
        assert set(banked) == {eid for eid, *_ in SHAPE_A}
        for eid, _h, _a, _c, _espn, _d, hs, a_s in SHAPE_A:
            assert banked[eid] == (0, 0, hs, a_s), eid
        # And the twin row is untouched by the same pass.
        assert (corpus.get(Event, BORROWED_ID).home_score,
                corpus.get(Event, BORROWED_ID).away_score) == (0, 0)

    def test_the_repaired_rows_can_then_be_put_back_by_the_shipped_undo(self, corpus):
        # The pair exercised in sequence, which is the only thing that proves the
        # banked post-image and the undo's CAS agree on a spelling.
        self.test_apply_banks_both_images_BEFORE_it_writes_run_end_to_end(corpus)
        restored, skipped = self._restore(corpus)
        assert (restored, skipped) == (4, [])
        corpus.expire_all()
        for eid, *_ in SHAPE_A:
            row = corpus.get(Event, eid)
            assert (row.home_score, row.away_score) == (0, 0), eid


class TestTheBand:
    """A sweep that finds nothing and exits 0 is the failure the band catches."""

    def test_an_empty_population_refuses(self):
        reason = population_refusal_reason(0, default_window=True)
        assert reason and "below the floor" in reason

    def test_a_growing_cohort_refuses(self):
        reason = population_refusal_reason(MAX_EXPECTED_POPULATION + 1, default_window=True)
        assert reason and "FROZEN" in reason

    def test_the_measured_population_passes(self):
        # 18 on production 2026-09-16, of which 5 are candidates (the rest carry
        # no anchor); the band is on the 0 - 0 cohort itself.
        assert population_refusal_reason(18, default_window=True) is None
        assert MIN_EXPECTED_POPULATION <= 18 <= MAX_EXPECTED_POPULATION

    def test_the_band_is_a_claim_about_the_default_window_only(self):
        assert population_refusal_reason(0, default_window=False) is None
