"""#7147 / CERT-3147 — the behavioural half: drive the WRITER, read the ROW.

CERT-3147 granted the #7147 writer repair and named one follow-up:

    add a behavioral DB/writer/history test because the named test currently
    proves the predicate and separate AST/string checks prove wiring

That is an exact description of what
``test_completed_espn_final_is_not_repoisoned_7147.py`` does and does not do.
It proves ``clockless_write_repoisons_a_settled_final`` returns the right
boolean, and it proves — structurally, by parsing ``odds_polling``'s own source
— that the loop calls it, joins it to ``_skip_score_write``, and counts it.
Between "the predicate is right" and "the row survives the pass" there is no
test at all, and that gap is the whole of the defect #7147 is about: production
event ``15313146`` was repaired to ESPN's ``7-3`` at 22:37Z and was serving
``7-2`` again by 23:15:07Z. Nobody doubted the arithmetic; the row moved.

So this file asserts nothing about the predicate and nothing about the source
text. It builds a database, puts a settled ESPN-anchored final in it, hands the
real ``_poll_all_odds`` a real Odds API payload that disagrees, and then looks
at what the ``events`` row and the ``score_snapshots`` table actually hold.

🔴 TWO WAYS THIS FILE COULD HAVE BEEN A STRAWMAN, BOTH MEASURED, BOTH GUARDED

1. **The identity map answers with the score the row used to hold.** The writer
   is Core SQL (``Event.__table__.update()``), which the ORM's identity map
   never sees. Reading the specimen back through the session that seeded it
   returns ``7-3`` *whether or not the guard held* — measured here on the
   permitted-write control, where the session said ``7-3`` and the database
   said ``7-2``. Every assertion below therefore reads through
   :func:`_stored`, which opens a NEW session. A test that reads the seeding
   session is not testing the writer, it is testing its own cache.

2. **A pass that never fetches scores refuses everything by accident.** If the
   sport is ESPN-covered, or its score cadence is not due, ``get_scores`` is
   never called — and then "the row is unchanged, no snapshot was added" is
   true for a reason that has nothing to do with the guard.
   :class:`TestTheRailCanActuallyWrite` is the positive control (a permitted
   write lands, and lands a snapshot), and every refusal test additionally
   asserts the refusal COUNTER moved, which only the guard itself can do.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import DateTime, create_engine, event as sa_event, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.sqlite.base import DATETIME as _SqliteDATETIME
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


class _UTCAwareDateTime(_SqliteDATETIME):
    """sqlite hands back naive datetimes; production's column is ``tz=True``.

    Without this the rail does not fail loudly — it fails *interestingly*. The
    task compares ``event_obj.commence_time`` against an aware ``now`` inside
    ``external_id_currency``, and a ``TypeError`` there lands in the per-record
    ``except`` that wraps every score record, so the pass would skip the
    specimen and report a clean, empty, meaningless success.
    """

    def result_processor(self, dialect, coltype):  # pragma: no cover - rail
        inner = super().result_processor(dialect, coltype)

        def process(value):
            parsed = inner(value)
            if parsed is not None and parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed

        return process


class _BoolOr:  # pragma: no cover - test rail
    """``func.bool_or`` is Postgres; the sport-data query at the top of the
    pass is unreachable on sqlite without it."""

    def __init__(self):
        self.value = 0

    def step(self, value):
        if value:
            self.value = 1

    def finalize(self):
        return self.value


#: The Odds API scores endpoint is only consulted once per sport per
#: ``SCORE_FETCH_INTERVAL``; the rail's Redis reports "never fetched" so the
#: specimen's sport is always due.
class _FakeRedis:  # pragma: no cover - test rail
    def __init__(self, last_poll_ts):
        self.last_poll_ts = last_poll_ts

    def get(self, key):
        if key.startswith("bainluck:last_poll:"):
            return str(self.last_poll_ts).encode()
        return None

    def hget(self, *_a, **_k):
        return None

    def hgetall(self, *_a, **_k):
        return {}

    def set(self, *_a, **_k):
        return True

    def incr(self, *_a, **_k):
        return 1

    def expire(self, *_a, **_k):
        return True


class _AsyncShim:  # pragma: no cover - test rail
    """The async surface of ``get_task_session`` over a sync sqlite session."""

    def __init__(self, session):
        self._s = session

    async def execute(self, statement, params=None):
        if params is None:
            return self._s.execute(statement)
        return self._s.execute(statement, params)

    def add(self, obj):
        self._s.add(obj)

    async def commit(self):
        self._s.commit()

    async def flush(self):
        self._s.flush()

    async def rollback(self):
        self._s.rollback()


SPORT_KEY = "baseball_mlb"


def _engine():
    engine = create_engine("sqlite://")
    engine.dialect.colspecs = {**engine.dialect.colspecs, DateTime: _UTCAwareDateTime}

    @sa_event.listens_for(engine, "connect")
    def _register(dbapi_conn, _record):  # pragma: no cover - test rail
        dbapi_conn.create_aggregate("bool_or", 1, _BoolOr)

    return engine


def _score_record(*, external_id, commence, home_team, away_team, home, away,
                  completed=True):
    """One record in the shape ``service.get_scores`` returns.

    ``home``/``away`` of ``None`` is spelled as the empty string on purpose:
    that is what the provider sends for a side it has no number for, and the
    task's own parser turns it into ``None``. Passing ``None`` through here
    instead would be the test writing the parser's answer for it.
    """
    return {
        "id": external_id,
        "completed": completed,
        "commence_time": commence.isoformat().replace("+00:00", "Z"),
        "home_team": home_team,
        "away_team": away_team,
        "scores": [
            {"name": home_team, "score": "" if home is None else str(home)},
            {"name": away_team, "score": "" if away is None else str(away)},
        ],
    }


async def _run_pass(*, specimen, payload):
    """Seed a database, run the REAL ``_poll_all_odds``, hand back the engine.

    ``specimen`` is the row under test as a kwargs dict for ``Event``. A second
    row is always seeded beside it and it is load-bearing: the ESPN-coverage
    probe skips the score fetch entirely for an ESPN-mapped sport whose recent
    scheduled/live events ALL carry an ``espn_id``, so without one unmatched
    row this pass would never call ``get_scores`` and every refusal assertion
    below would pass for the wrong reason.
    """
    from app.models.models import (
        Base,
        Event,
        ScoreSnapshot,
        Sport,
        Team,
        WinProbSnapshot,
    )
    import app.tasks.odds_polling as odds_polling

    engine = _engine()
    Base.metadata.create_all(
        engine,
        tables=[
            Sport.__table__,
            Team.__table__,
            Event.__table__,
            ScoreSnapshot.__table__,
            WinProbSnapshot.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)

    sport = Sport(key=SPORT_KEY, name="MLB", active=True)
    session.add(sport)
    session.flush()

    row = Event(sport_id=sport.id, **specimen)
    # The unmatched row the coverage probe needs. `scheduled` with a commence
    # already past is the ordinary state of a row our schedule holds and ESPN
    # has not claimed yet — the population #7147 lives among.
    unmatched = Event(
        sport_id=sport.id,
        external_id="odds-api-unmatched",
        home_team_name="Cubs",
        away_team_name="Cardinals",
        commence_time=now - timedelta(minutes=20),
        status="scheduled",
    )
    session.add_all([row, unmatched])
    session.commit()
    specimen_id = row.id

    service = MagicMock()
    service.get_odds = AsyncMock(return_value=[])
    service.get_scores = AsyncMock(return_value=payload)
    service.close = AsyncMock()
    # Real `None`s: a MagicMock here is `is not None` and would reach the real
    # quota recorder.
    service.last_requests_remaining = None
    service.last_requests_used = None

    class _Ctx:
        async def __aenter__(self_inner):
            return _AsyncShim(session)

        async def __aexit__(self_inner, *_exc):
            session.commit()
            return False

    with patch.object(odds_polling, "check_quota_guard", return_value=(True, "ok")), \
            patch.object(odds_polling, "OddsAPIService", return_value=service), \
            patch.object(
                odds_polling,
                "get_redis_client",
                return_value=_FakeRedis(now.timestamp() - 100_000),
            ), \
            patch.object(odds_polling, "get_task_session", return_value=_Ctx()), \
            patch.object(
                odds_polling,
                "detect_and_close_stale_events",
                AsyncMock(return_value={"closed": 0, "suspended": 0}),
            ), \
            patch.object(odds_polling, "update_poll_state", MagicMock()), \
            patch(
                "app.tasks.excitement_index.update_live_ei",
                AsyncMock(return_value=0),
            ):
        result = await odds_polling._poll_all_odds()

    session.close()
    return result, engine, specimen_id, service


def _stored(engine, event_id):
    """The row as the DATABASE holds it — never as a session remembers it.

    🔴 The whole file turns on this. The writer is
    ``Event.__table__.update()``, a Core statement the identity map cannot see,
    so the seeding session answers with the seeded score no matter what the
    pass did. Measured on the permitted-write control in this file: the session
    said ``7-3``; the database said ``7-2``.
    """
    from app.models.models import Event

    with Session(engine) as fresh:
        row = fresh.execute(select(Event).where(Event.id == event_id)).scalar_one()
        return {
            "home_score": row.home_score,
            "away_score": row.away_score,
            "status": row.status,
        }


def _snapshots(engine, event_id):
    from app.models.models import ScoreSnapshot

    with Session(engine) as fresh:
        return fresh.execute(
            select(ScoreSnapshot.home_score, ScoreSnapshot.away_score)
            .where(ScoreSnapshot.event_id == event_id)
            .order_by(ScoreSnapshot.id)
        ).all()


def _settled_specimen(**overrides):
    """#7147's shape: a completed, ESPN-anchored row holding a real final."""
    now = datetime.now(timezone.utc)
    base = dict(
        external_id="odds-api-specimen",
        espn_id="401-espn-specimen",
        home_team_name="Red Sox",
        away_team_name="Yankees",
        commence_time=now - timedelta(hours=3),
        completed_at=now - timedelta(hours=1),
        status="completed",
        home_score=7,
        away_score=3,
    )
    base.update(overrides)
    return base


def _payload_for(specimen, *, home, away, completed=True):
    return [
        _score_record(
            external_id=specimen["external_id"],
            commence=specimen["commence_time"],
            home_team=specimen["home_team_name"],
            away_team=specimen["away_team_name"],
            home=home,
            away=away,
            completed=completed,
        )
    ]


class TestTheSpecimenTheWriterUsedToRepoison:
    """Production 2026-09-19: repaired to ``7-3``, serving ``7-2`` within 40
    minutes, with a fresh ``score_history`` row to match."""

    @pytest.fixture(scope="class")
    def outcome(self):
        specimen = _settled_specimen()
        return asyncio.run(
            _run_pass(
                specimen=specimen,
                payload=_payload_for(specimen, home=7, away=2),
            )
        )

    def test_the_pass_really_asked_the_provider_for_scores(self, outcome):
        """The rail's own precondition. A pass that skipped the score fetch
        would satisfy every other assertion in this class while proving
        nothing."""
        _, _, _, service = outcome
        service.get_scores.assert_awaited_once_with(SPORT_KEY, days_from=3)

    def test_the_row_still_holds_the_authoritys_final(self, outcome):
        _, engine, event_id, _ = outcome
        stored = _stored(engine, event_id)
        assert (stored["home_score"], stored["away_score"]) == (7, 3), (
            "the clockless feed overwrote a settled ESPN-anchored final; the "
            "#7147 cleanup is sweeping residue this writer re-creates"
        )

    def test_no_score_snapshot_records_the_refused_pair(self, outcome):
        """The history half, and the reason ``_skip_score_write`` exists: a
        snapshot of a score the pass declined to store puts a number in the
        Score Differential chart the event row never held — in the very table
        #7147 is cleaning."""
        _, engine, event_id, _ = outcome
        assert _snapshots(engine, event_id) == []

    def test_the_refusal_is_counted(self, outcome):
        result, _, _, _ = outcome
        assert result["scores_refused_settled_repoison"] == 1

    def test_the_status_is_not_touched(self, outcome):
        """The repair declines the SCORE. A guard that also reverted the status
        would be a second, unreviewed behaviour riding the first."""
        _, engine, event_id, _ = outcome
        assert _stored(engine, event_id)["status"] == "completed"


class TestTheRailCanActuallyWrite:
    """🔴 THE STRAWMAN GUARD. Every assertion above is satisfied by a rail that
    writes nothing at all — a broken engine, an unreached loop, a payload the
    parser dropped. This is the same pass with the same plumbing on a row the
    guard has no opinion about, and it must move."""

    @pytest.fixture(scope="class")
    def outcome(self):
        specimen = _settled_specimen(
            status="live", espn_id=None, completed_at=None
        )
        return asyncio.run(
            _run_pass(
                specimen=specimen,
                payload=_payload_for(specimen, home=7, away=2, completed=False),
            )
        )

    def test_the_permitted_write_reaches_the_row(self, outcome):
        _, engine, event_id, _ = outcome
        stored = _stored(engine, event_id)
        assert (stored["home_score"], stored["away_score"]) == (7, 2), (
            "this rail cannot write at all, so no refusal it reports is "
            "evidence of anything"
        )

    def test_the_permitted_write_leaves_its_snapshot(self, outcome):
        _, engine, event_id, _ = outcome
        assert _snapshots(engine, event_id) == [(7, 2)]

    def test_nothing_was_refused(self, outcome):
        result, _, _, _ = outcome
        assert result["scores_refused_settled_repoison"] == 0


class TestTheCarveOutTheSiblingGuardWasProtecting:
    """``clockless_write_defers_to_authority``'s docstring, verbatim: *the write
    that lands a FINAL score must never be withheld*. Landing one on a row that
    holds none is the write that sentence is about, and it still lands."""

    @pytest.fixture(scope="class")
    def outcome(self):
        specimen = _settled_specimen(home_score=None, away_score=None)
        return asyncio.run(
            _run_pass(
                specimen=specimen,
                payload=_payload_for(specimen, home=7, away=3),
            )
        )

    def test_a_settled_row_holding_no_score_takes_the_final(self, outcome):
        _, engine, event_id, _ = outcome
        stored = _stored(engine, event_id)
        assert (stored["home_score"], stored["away_score"]) == (7, 3), (
            "the guard swallowed the write that LANDS a final, which is the "
            "one case the sibling deferral was written to protect"
        )

    def test_it_is_not_counted_as_a_refusal(self, outcome):
        result, _, _, _ = outcome
        assert result["scores_refused_settled_repoison"] == 0


class TestItJudgesThePairTheRowWillHold:
    """CERT-2963's correction, measured end to end for the first time.

    ``odds_polling`` writes the two halves in independent statements, so a
    payload carrying ONLY the away side lands on the stored home side: stored
    ``7-3`` plus an incoming ``away=2`` stores ``7-2``. A guard that judged the
    PAYLOAD would see ``(None, 2)`` — not a complete pair, nothing to protect —
    and wave it through. This is the exact shape the production specimen
    arrived in.
    """

    @pytest.fixture(scope="class")
    def outcome(self):
        specimen = _settled_specimen()
        return asyncio.run(
            _run_pass(
                specimen=specimen,
                payload=_payload_for(specimen, home=None, away=2),
            )
        )

    def test_the_one_sided_write_never_reaches_the_row(self, outcome):
        _, engine, event_id, _ = outcome
        stored = _stored(engine, event_id)
        assert (stored["home_score"], stored["away_score"]) == (7, 3), (
            "a one-sided payload re-poisoned the pair; the guard is reading "
            "the payload instead of the pair the row would hold"
        )

    def test_it_is_counted(self, outcome):
        result, _, _, _ = outcome
        assert result["scores_refused_settled_repoison"] == 1


class TestItDoesNotRefuseAnAgreeingWrite:
    """A guard that refused every settled row would pass all four classes
    above. The provider agreeing with the authority is the overwhelmingly
    common case (measured 98.6% on the MLB+NFL sample in #7147) and it is not a
    refusal."""

    @pytest.fixture(scope="class")
    def outcome(self):
        specimen = _settled_specimen()
        return asyncio.run(
            _run_pass(
                specimen=specimen,
                payload=_payload_for(specimen, home=7, away=3),
            )
        )

    def test_the_agreeing_pair_is_not_counted_as_a_refusal(self, outcome):
        result, _, _, _ = outcome
        assert result["scores_refused_settled_repoison"] == 0

    def test_the_row_is_unchanged_and_no_snapshot_is_added(self, outcome):
        """Not refused, and also not churned: the snapshot is conditioned on
        the pair actually changing."""
        _, engine, event_id, _ = outcome
        stored = _stored(engine, event_id)
        assert (stored["home_score"], stored["away_score"]) == (7, 3)
        assert _snapshots(engine, event_id) == []
