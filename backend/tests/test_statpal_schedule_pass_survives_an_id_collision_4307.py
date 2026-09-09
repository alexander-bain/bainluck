"""One ambiguous fixture must not discard a whole sport's pass. #4307.

PILLAR: TRUTH. SHIP: an MLB game stops sitting on an uncorrected kickoff time
and a stuck ``live`` badge because the hourly pass that fixes it died before it
committed anything.

THE DEFECT, as it shipped
═════════════════════════
``_sync_statpal_schedules`` resolved a past fixture's row by StatPal id with::

    event = fid_result.scalar_one_or_none()

``scalar_one_or_none()`` **raises** ``MultipleResultsFound`` when two rows come
back, and on 2026-09-09 seven ``statpal_fixture_id`` values in production were
carried by two rows each (NHL 3, MLB 2, NBA 2) — every one a twin. Today's was
MLB ``364906``: events 15300848 (``suspended``) and 15307210 (``completed``),
San Francisco Giants v St. Louis Cardinals, differing by one space in the club
name.

WHY THE RAISE COST THE WHOLE PASS AND NOT ONE FIXTURE
══════════════════════════════════════════════════════
``get_task_session`` (``app/tasks/base.py:59-66``) commits only on a clean exit
and rolls back on any exception, and ``_sync_statpal_schedules`` has no
intermediate commit. So the exception discarded every ``commence_time``
correction, every ``live`` → ``completed`` transition, every ``statpal_end_time``
fill and every score update the pass had already accumulated — and the
playoff-gap live-create block below it never ran at all.

Measured 2026-09-09 ~11:30Z: ``statpal_schedules`` reported ``starts_24h 39``,
``failures_24h 7`` over a 34,419s window with ``last_failure_type
MultipleResultsFound`` at 11:02:00Z — minute :02 is ``sync-statpal-schedules-mlb``
— i.e. ~7 of MLB's ~9.6 passes in that window. Sentry ``BAINLUCK-16X``: 21
events in the 24h buckets, first seen 2026-09-08T01:03:31Z. The task's own
``health`` field read ``healthy`` throughout.

WHAT THESE GUARDS ARE FOR
═════════════════════════
The behavioural half is the one that matters, and it is built so it can FAIL:
the rail's session context mirrors production's commit/rollback exactly, so a
raise anywhere in the pass loses the sibling's write. Without that fidelity the
test would pass on the shipped code (gotcha: a rig that renders nothing on every
arm reads as a clean diff), so ``TestTheRailCanSeeTheDefect`` re-runs the same
scenario through the verbatim shipped resolution and REQUIRES the raise.

The structural half pins the call site, because the defect was one method name
and a future edit could reintroduce it against a fixture that happens to be
unique.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.tasks.statpal_sync import _statpal_sport_key_filter, row_for_statpal_id


# `Event` carries Postgres JSONB/ARRAY columns that sqlite cannot render as DDL.
# The repo's standing shim (see `test_authority_failover_3473`), so this rail can
# create the real tables from the real models.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"

SOURCE_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "app/tasks/statpal_sync.py"
)

MLB = "baseball_mlb"
#: A key mapping to a DIFFERENT StatPal sport — the #4322 bound's other side.
NHL = "icehockey_nhl"
#: Two of the SEVEN of our league keys that map to StatPal `soccer`. The bound
#: must treat these as one id space, which is why it is not `== sport_id`.
SOCCER_A = "soccer_epl"
SOCCER_B = "soccer_italy_serie_a"

#: The id production carried on two rows on 2026-09-09, and the two event ids.
COLLIDING_FIXTURE_ID = "364906"
#: A second fixture in the same pass, processed AFTER the colliding one. Its
#: write is the thing the raise used to destroy.
SIBLING_FIXTURE_ID = "364999"


# ─────────────────────────────────────────────────────────────────────────────
# The judgement, driven directly
# ─────────────────────────────────────────────────────────────────────────────


class _Row:
    """The only attribute the judgement reads."""

    def __init__(self, sport_id=1, id=None):
        self.sport_id = sport_id
        self.id = id


#: The sport-id set of one StatPal sport with a single league (e.g. `nfl`).
OWN = {1}
#: One StatPal sport carrying several of our league keys — the soccer shape.
SOCCER = {10, 11, 12}


class TestThePredicate:
    """``row_for_statpal_id`` — one game, no game, an ambiguity, or a foreigner."""

    def test_one_row_is_the_game(self):
        row = _Row()
        assert row_for_statpal_id([row], sport_ids=OWN) == (row, False, [])

    def test_no_rows_is_not_a_collision(self):
        """A past fixture we hold no row for is the ordinary case, not a finding."""
        assert row_for_statpal_id([], sport_ids=OWN) == (None, False, [])

    def test_two_rows_is_a_collision_and_yields_no_row(self):
        """Both halves matter: it must FLAG, and it must not pick one."""
        first, second = _Row(), _Row()
        row, collided, foreign = row_for_statpal_id([first, second], sport_ids=OWN)
        assert collided is True
        assert foreign == []
        assert row is None, (
            "Returning either row is the `.first()` behaviour this exists to "
            "refuse — the two rows are a twin and which is the game is exactly "
            "what they disagree about (D55)."
        )

    def test_three_rows_is_also_a_collision(self):
        rows = [_Row(), _Row(), _Row()]
        assert row_for_statpal_id(rows, sport_ids=OWN) == (None, True, [])

    def test_it_accepts_any_sequence(self):
        """SQLAlchemy's `.scalars().all()` is not a list on every version."""
        row = _Row()
        assert row_for_statpal_id(tuple([row]), sport_ids=OWN) == (row, False, [])

    # ── #4322: the sport bound ────────────────────────────────────────────────

    def test_a_foreign_row_is_not_the_game_and_is_not_a_twin(self):
        """CERT-853's shape: one token, two of StatPal's sports.

        The pre-#4322 reader would have enriched this row — another sport's
        event — because it was the only one the unbounded query returned.
        """
        alien = _Row(sport_id=99, id=555)
        row, collided, foreign = row_for_statpal_id([alien], sport_ids=OWN)
        assert row is None, "a foreign row must never be enriched"
        assert collided is False, (
            "cross-sport id reuse is not a twin, and counting it as one would "
            "corrupt the twin population #3093/#3463 read from that number"
        )
        assert foreign == [alien], "and it must be reported, never invisible (D55)"

    def test_a_foreign_row_does_not_make_the_real_one_ambiguous(self):
        """The case where the bound BUYS an enrichment the old reader lost.

        Two rows came back, so the unbounded reader called it a collision and
        skipped. Only one of them is in this StatPal sport, so it is the game.
        """
        mine, alien = _Row(sport_id=1, id=1), _Row(sport_id=99, id=555)
        row, collided, foreign = row_for_statpal_id([mine, alien], sport_ids=OWN)
        assert row is mine
        assert collided is False
        assert foreign == [alien]

    def test_two_own_rows_still_collide_even_beside_a_foreigner(self):
        """The bound narrows the population; it does not soften the refusal."""
        a, b, alien = _Row(1, 1), _Row(1, 2), _Row(99, 555)
        row, collided, foreign = row_for_statpal_id([a, b, alien], sport_ids=OWN)
        assert (row, collided) == (None, True)
        assert foreign == [alien]

    def test_a_sibling_league_of_the_same_statpal_sport_is_NOT_foreign(self):
        """The soccer shape, and the reason the bound is not `== sport_id`.

        Seven of our league keys map to StatPal `soccer`. A fixture pulled during
        one league's iteration legitimately belongs to another's event. Bounding
        on the loop's own sport would refuse every sibling — a false miss on six
        leagues out of seven — so this test fails on the naive fix.
        """
        serie_a = _Row(sport_id=12, id=7)
        row, collided, foreign = row_for_statpal_id([serie_a], sport_ids=SOCCER)
        assert row is serie_a
        assert (collided, foreign) == (False, [])

    def test_a_row_with_no_sport_id_is_treated_as_foreign(self):
        """Unclassifiable is not "mine". Enriching it is the write we refuse."""
        orphan = _Row(sport_id=None, id=3)
        row, collided, foreign = row_for_statpal_id([orphan], sport_ids=OWN)
        assert (row, collided) == (None, False)
        assert foreign == [orphan]

    def test_the_bound_is_mandatory_and_keyword_only(self):
        """A bound that defaults to unbounded is the defect wearing a parameter.

        Asserted on the SIGNATURE rather than by making the two bad calls. Two
        reasons, and the second is the better one:

        1. Written literally, the positional call is a static "too many
           arguments" ERROR to CodeQL (`py/call/wrong-arguments`) — a `failure`
           check-run conclusion, which standing notice 32 refuses outright. A
           splat did not fool it either; the analyser resolves the tuple.
        2. `pytest.raises(TypeError)` is a weaker claim than it looks. It passes
           for a function that raises TypeError for some entirely unrelated
           reason, and it would keep passing if `sport_ids` grew a default of
           `None` and the body raised on it — which is the exact regression this
           guards. The signature is the contract, so assert the contract.
        """
        param = inspect.signature(row_for_statpal_id).parameters["sport_ids"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY, (
            "`sport_ids` must be keyword-only, so a caller cannot pass a bound "
            f"by position and get the argument order wrong. Got {param.kind}."
        )
        assert param.default is inspect.Parameter.empty, (
            "`sport_ids` must have NO default. A bound that defaults to "
            "anything is the unbounded read wearing a parameter, and the next "
            "caller inherits the defect silently (#4322)."
        )


class TestWhichSportsShareTheIdSpace:
    """`_statpal_sport_key_filter` — the bound's OTHER half, and the near miss.

    `row_for_statpal_id` partitions against a set of sport ids. Everything above
    proves it partitions correctly; nothing above proves the SET is right, and
    the first cut of #4322 built it from `STATPAL_SPORT_MAPPING`'s seven soccer
    keys. That is too narrow, and measurably so: the hourly soccer stamper
    writes `statpal_fixture_id` across every `soccer%` sport — 34 of them in
    production on 2026-09-09, one contiguous StatPal id band — so a
    `soccer_efl_champ` row would have been classified FOREIGN and refused, a
    false miss the unbounded reader did not have.
    """

    def _keys_selected(self, session, statpal_sport: str) -> set[str]:
        from sqlalchemy import select

        from app.models.models import Sport

        return set(
            session.execute(
                select(Sport.key).where(_statpal_sport_key_filter(statpal_sport))
            )
            .scalars()
            .all()
        )

    @pytest.fixture()
    def session(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from app.models.models import Sport

        engine = create_engine("sqlite://")
        Sport.__table__.create(engine)
        session = Session(engine, expire_on_commit=False)
        for key in (
            SOCCER_A,            # in the schedule map
            SOCCER_B,            # in the schedule map
            "soccer_efl_champ",  # NOT in the map — stamper-written, 17 prod rows
            "soccer_other",      # NOT in the map
            MLB,
            NHL,
            "tennis_atp_us_open",
        ):
            session.add(Sport(key=key, name=key))
        session.commit()
        try:
            yield session
        finally:
            session.close()

    def test_soccer_covers_the_leagues_the_schedule_map_never_names(self, session):
        """The rail against the narrow bound. Reds on the map-only build."""
        selected = self._keys_selected(session, "soccer")
        assert {"soccer_efl_champ", "soccer_other"} <= selected, (
            "StatPal scopes fixture ids by its own sport, and every `soccer%` "
            "sport draws from that one space. Bounding on the schedule map's "
            "seven keys calls a stamper-written sibling FOREIGN and refuses to "
            "enrich it — worse than the unbounded reader (#4322)."
        )
        assert selected == {
            SOCCER_A, SOCCER_B, "soccer_efl_champ", "soccer_other",
        }

    def test_soccer_does_not_reach_another_statpal_sport(self, session):
        """Wider is not unbounded — the CERT-853 refusal must survive."""
        selected = self._keys_selected(session, "soccer")
        assert not selected & {MLB, NHL, "tennis_atp_us_open"}

    def test_a_one_to_one_sport_falls_back_to_the_map(self, session):
        """No prefix entry ⇒ the map's keys, exactly. NHL must not take MLB."""
        assert self._keys_selected(session, "nhl") == {NHL}
        assert self._keys_selected(session, "mlb") == {MLB}

    def test_tennis_is_knowingly_still_map_bound(self, session):
        """Pins the documented gap so it is a decision, not an oversight.

        `tennis_atp_us_open` carries StatPal tennis ids in production but is not
        in the map, so tennis has soccer's old narrowness. It is unreachable —
        the beat has four entries (nba/nhl/mlb/nfl) — and widening it would move
        the injury attach for no ship. If someone adds `"tennis": "tennis"` to
        `_INJURY_EVENT_SPORT_PREFIX`, this test fails and they must say why.
        """
        assert self._keys_selected(session, "tennis") == set(), (
            "Neither `tennis_atp` nor `tennis_wta` exists in this rail, so the "
            "map-bound filter selects nothing — and `tennis_atp_us_open`, which "
            "does exist and does carry StatPal tennis ids, is not reached."
        )


# ─────────────────────────────────────────────────────────────────────────────
# The rail
# ─────────────────────────────────────────────────────────────────────────────


def _wire(monkeypatch, *, faithful_rollback: bool = True, foreign_fid: str = None):
    """Two MLB rows sharing one StatPal id, plus a clean sibling row.

    ``foreign_fid`` (#4322) additionally creates an **NHL** sport and one event
    under it carrying that fixture id — StatPal's id space is per-sport, so this
    is the CERT-853 shape: one token, two of StatPal's sports. Returned in
    ``ids`` as ``"foreign"``.

    The session context mirrors ``get_task_session``: commit on a clean exit,
    **rollback** on an exception. That fidelity is the whole point — a rail that
    commits regardless cannot tell the fix from the defect.

    Returns ``(session, ids)``.
    """
    from sqlalchemy import create_engine
    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session

    import app.tasks.base as task_base
    from app.models.models import (
        Base, Event, Sport, Team, TeamIdentityMapping,
    )

    engine = create_engine("sqlite://")
    # `team_identity_service.resolve_team` runs inside the loop, so its two
    # tables are part of the rail even though nothing here asserts on them.
    Base.metadata.create_all(
        engine,
        tables=[
            Event.__table__,
            Sport.__table__,
            Team.__table__,
            TeamIdentityMapping.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)

    now = datetime.now(timezone.utc)
    sport = Sport(key=MLB, name="MLB")
    session.add(sport)
    session.flush()

    # The twin: one id, two rows — production's MLB 364906.
    twin_a = Event(
        sport_id=sport.id,
        home_team_name="San Francisco Giants",
        away_team_name="St.Louis Cardinals",
        commence_time=now - timedelta(hours=6),
        status="suspended",
        statpal_fixture_id=COLLIDING_FIXTURE_ID,
    )
    twin_b = Event(
        sport_id=sport.id,
        home_team_name="San Francisco Giants",
        away_team_name="St. Louis Cardinals",
        commence_time=now - timedelta(hours=6),
        status="completed",
        statpal_fixture_id=COLLIDING_FIXTURE_ID,
    )
    # The sibling, processed after the twin, with a kickoff 40 minutes wrong —
    # the correction is what the pass exists to make, and what the raise ate.
    sibling = Event(
        sport_id=sport.id,
        home_team_name="Detroit Tigers",
        away_team_name="Minnesota Twins",
        commence_time=now - timedelta(hours=3),
        status="live",
        statpal_fixture_id=SIBLING_FIXTURE_ID,
    )
    session.add_all([twin_a, twin_b, sibling])
    session.commit()
    ids = {
        "twin_a": twin_a.id,
        "twin_b": twin_b.id,
        "sibling": sibling.id,
        "sport": sport.id,
    }

    if foreign_fid is not None:
        # A DIFFERENT StatPal sport ("nhl"), reusing the same fixture token.
        nhl_sport = Sport(key=NHL, name="NHL")
        session.add(nhl_sport)
        session.flush()
        foreign = Event(
            sport_id=nhl_sport.id,
            home_team_name="Boston Bruins",
            away_team_name="Montreal Canadiens",
            commence_time=now - timedelta(hours=6),
            status="scheduled",
            statpal_fixture_id=foreign_fid,
        )
        session.add(foreign)
        session.commit()
        ids["foreign"] = foreign.id
        ids["foreign_sport"] = nhl_sport.id

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    class _Ctx:
        async def __aenter__(self_inner):
            return _AsyncShim(session)

        async def __aexit__(self_inner, exc_type, *_):
            if exc_type is not None and faithful_rollback:
                session.rollback()
                return False
            session.commit()
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(
        "app.tasks.statpal_sync.get_task_session", lambda: _Ctx(), raising=False
    )
    return session, ids


class _AsyncShim:
    """A sync Session wearing the async Session's two awaited methods."""

    def __init__(self, session):
        self._s = session

    async def execute(self, *a, **kw):
        return self._s.execute(*a, **kw)

    async def flush(self, *a, **kw):
        return self._s.flush(*a, **kw)

    async def commit(self):
        return self._s.commit()

    async def rollback(self):
        return self._s.rollback()

    def add(self, obj):
        return self._s.add(obj)

    def __getattr__(self, name):
        return getattr(self._s, name)


SOCCER_FIXTURE_ID = "9543274"


def _wire_soccer(monkeypatch):
    """Two of our soccer leagues, and one event under the SECOND of them.

    The pass will run for `soccer_epl`; the row belongs to `soccer_italy_serie_a`.
    Both map to StatPal `soccer`, so both are one id space (#4322).
    """
    from sqlalchemy import create_engine
    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session

    import app.tasks.base as task_base
    from app.models.models import Base, Event, Sport, Team, TeamIdentityMapping

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Event.__table__, Sport.__table__,
            Team.__table__, TeamIdentityMapping.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)

    now = datetime.now(timezone.utc)
    epl = Sport(key=SOCCER_A, name="EPL")
    serie_a = Sport(key=SOCCER_B, name="Serie A")
    session.add_all([epl, serie_a])
    session.flush()

    row = Event(
        sport_id=serie_a.id,
        home_team_name="Inter Milan",
        away_team_name="AC Milan",
        # 90 minutes wrong — the correction the pass exists to make.
        commence_time=now - timedelta(hours=2) - timedelta(minutes=90),
        status="completed",
        statpal_fixture_id=SOCCER_FIXTURE_ID,
    )
    session.add(row)
    session.commit()
    ids = {"serie_a": row.id, "epl_sport": epl.id, "serie_a_sport": serie_a.id}

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    class _Ctx:
        async def __aenter__(self):
            return _AsyncShim(session)

        async def __aexit__(self, exc_type, *_):
            if exc_type is not None:
                session.rollback()
                return False
            session.commit()
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(
        "app.tasks.statpal_sync.get_task_session", lambda: _Ctx(), raising=False
    )
    return session, ids


def _stub_soccer_service(monkeypatch, now):
    """StatPal serves the one Serie A fixture under its `soccer` sport."""
    import app.services.statpal_api as statpal_api

    fixture = statpal_api.StatPalFixture(
        fixture_id=SOCCER_FIXTURE_ID,
        home_team="Inter Milan",
        away_team="AC Milan",
        start_time=now - timedelta(hours=2),
        status="finished",
    )

    class _Service:
        async def get_fixtures(self, sport):
            return [fixture]

        async def get_live_scores(self, sport):
            return []

        async def close(self):
            return None

    monkeypatch.setattr(statpal_api, "is_available", lambda: True)
    monkeypatch.setattr(statpal_api, "StatPalAPIService", lambda *a, **kw: _Service())


def _fixtures(now):
    """The two fixtures StatPal serves, colliding one FIRST."""
    # Module alias, not `from ... import`: the file reaches this module both
    # ways otherwise, which is a real CodeQL finding (py/import-and-import-from)
    # and therefore a `failure` conclusion that standing notice 32 refuses.
    import app.services.statpal_api as statpal_api

    StatPalFixture = statpal_api.StatPalFixture
    return [
        StatPalFixture(
            fixture_id=COLLIDING_FIXTURE_ID,
            home_team="San Francisco Giants",
            away_team="St. Louis Cardinals",
            start_time=now - timedelta(hours=6),
            status="finished",
        ),
        StatPalFixture(
            fixture_id=SIBLING_FIXTURE_ID,
            home_team="Detroit Tigers",
            away_team="Minnesota Twins",
            # 40 minutes later than the row holds — a correction, not rounding.
            start_time=now - timedelta(hours=3) + timedelta(minutes=40),
            status="finished",
        ),
    ]


def _stub_service(monkeypatch, now):
    """StatPal serves the two fixtures and no live games."""
    import app.services.statpal_api as statpal_api

    fixtures = _fixtures(now)

    class _Service:
        async def get_fixtures(self, sport):
            return list(fixtures)

        async def get_live_scores(self, sport):
            return []

        async def close(self):
            return None

    monkeypatch.setattr(statpal_api, "is_available", lambda: True)
    monkeypatch.setattr(statpal_api, "StatPalAPIService", lambda *a, **kw: _Service())


# ─────────────────────────────────────────────────────────────────────────────
# The behaviour
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_pass_survives_the_collision_and_the_sibling_is_written(
    monkeypatch,
):
    """The ship: a twin costs its own fixture, and nothing else.

    Three assertions, because the defect could hide behind any one of them:
    it does not raise, it COMMITS (the sibling's correction is on the row after
    the pass returns), and the collision is reported as a count rather than
    absorbed.
    """
    from app.tasks.statpal_sync import _sync_statpal_schedules

    now = datetime.now(timezone.utc)
    session, ids = _wire(monkeypatch)
    _stub_service(monkeypatch, now)

    result = await _sync_statpal_schedules(MLB)

    assert result.get("schedule_fid_collision_skipped") == 1, (
        "The ambiguous fixture must be COUNTED, not silently absorbed — a "
        f"refusal nobody measures is a refusal nobody sees. Got: {result}"
    )

    from app.models.models import Event

    # Expunge, not refresh — see the note in the rollback control below.
    session.expunge_all()
    sibling = session.get(Event, ids["sibling"])
    expected = now - timedelta(hours=3) + timedelta(minutes=40)
    assert abs((sibling.commence_time - expected).total_seconds()) < 5, (
        "The sibling's kickoff correction is the work the raise used to throw "
        "away. It must be on the row AFTER the pass returns — which means the "
        f"pass reached it AND committed. Got {sibling.commence_time}."
    )
    assert sibling.commence_time_source == "statpal"


@pytest.mark.asyncio
async def test_neither_twin_is_enriched(monkeypatch):
    """It skips — it does not pick one. Stamping a twin deepens it (D35)."""
    from app.models.models import Event
    from app.tasks.statpal_sync import _sync_statpal_schedules

    now = datetime.now(timezone.utc)
    session, ids = _wire(monkeypatch)
    _stub_service(monkeypatch, now)

    before = {
        k: session.get(Event, ids[k]).status for k in ("twin_a", "twin_b")
    }

    await _sync_statpal_schedules(MLB)

    session.expunge_all()
    for k in ("twin_a", "twin_b"):
        row = session.get(Event, ids[k])
        assert row.status == before[k], (
            f"{k} changed status. The pass may not guess which of two rows is "
            "the game — that is the twin's own disagreement (D55, #2693)."
        )


@pytest.mark.asyncio
async def test_a_clean_pass_reports_zero_not_nothing(monkeypatch):
    """0 is a reading. An absent key cannot be told from a guard that never ran."""
    from app.tasks.statpal_sync import _sync_statpal_schedules

    now = datetime.now(timezone.utc)
    session, ids = _wire(monkeypatch)
    _stub_service(monkeypatch, now)

    # Break the collision: give one twin its own id.
    from app.models.models import Event

    twin_b = session.get(Event, ids["twin_b"])
    twin_b.statpal_fixture_id = "364906-b"
    session.commit()

    result = await _sync_statpal_schedules(MLB)

    assert "schedule_fid_collision_skipped" in result, (
        "The key must always be present (gotcha #53: an absence and a zero are "
        "different answers)."
    )
    assert result["schedule_fid_collision_skipped"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# #4322 — the sport bound, driven through the whole pass
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_another_sports_row_is_never_enriched_and_is_not_a_twin(monkeypatch):
    """CERT-853's shape, at the call site: one token, two of StatPal's sports.

    Both MLB rows give up the colliding id, so the ONLY row left carrying it
    belongs to NHL. The pre-#4322 reader returned exactly one row and enriched
    it — writing an MLB fixture's kickoff onto a hockey game.
    """
    from app.models.models import Event
    from app.tasks.statpal_sync import _sync_statpal_schedules

    now = datetime.now(timezone.utc)
    session, ids = _wire(monkeypatch, foreign_fid=COLLIDING_FIXTURE_ID)
    _stub_service(monkeypatch, now)

    for key, new_id in (("twin_a", "364906-a"), ("twin_b", "364906-b")):
        session.get(Event, ids[key]).statpal_fixture_id = new_id
    session.commit()
    before = session.get(Event, ids["foreign"]).commence_time

    result = await _sync_statpal_schedules(MLB)

    assert result["schedule_fid_cross_sport_skipped"] == 1, (
        "A token shared across two of StatPal's sports must be counted as what "
        f"it is. Got: {result}"
    )
    assert result["schedule_fid_collision_skipped"] == 0, (
        "and NOT as a twin — that number is the population #3093/#3463 read, "
        "and folding cross-sport reuse into it corrupts the count"
    )

    session.expunge_all()
    after = session.get(Event, ids["foreign"])
    assert after.commence_time == before, (
        "the hockey row must be untouched — enriching it is the silent wrong "
        "write the bound exists to refuse"
    )
    assert after.statpal_fixture_id == COLLIDING_FIXTURE_ID


@pytest.mark.asyncio
async def test_a_foreign_row_no_longer_costs_the_real_row_its_correction(
    monkeypatch,
):
    """The enrichment the bound BUYS BACK.

    Two rows carry `SIBLING_FIXTURE_ID` — ours and a hockey row. Unbounded, that
    is two candidates, so #4307's reader called it a twin and skipped, losing a
    correction it should have made. Only one is in MLB's id space.
    """
    from app.models.models import Event
    from app.tasks.statpal_sync import _sync_statpal_schedules

    now = datetime.now(timezone.utc)
    session, ids = _wire(monkeypatch, foreign_fid=SIBLING_FIXTURE_ID)
    _stub_service(monkeypatch, now)

    result = await _sync_statpal_schedules(MLB)

    assert result["schedule_fid_collision_skipped"] == 1, (
        "the real MLB twin is still refused — the bound narrows the population, "
        "it does not soften the refusal"
    )
    assert result["schedule_fid_cross_sport_skipped"] == 0, (
        "our row WAS found, so nothing was skipped for being cross-sport"
    )

    session.expunge_all()
    sibling = session.get(Event, ids["sibling"])
    expected = now - timedelta(hours=3) + timedelta(minutes=40)
    assert abs((sibling.commence_time - expected).total_seconds()) < 5, (
        "the correction must land: unbounded, this row was collateral damage "
        f"from a hockey row sharing its token. Got {sibling.commence_time}."
    )


@pytest.mark.asyncio
async def test_a_sibling_soccer_league_is_the_same_id_space(monkeypatch):
    """The naive fix's grave: bounding on the loop's own `sport_id`.

    Seven of our league keys map to StatPal `soccer`. This pass runs for
    `soccer_epl` and the row it must correct belongs to `soccer_italy_serie_a`.
    A `== sport_id` bound calls that foreign and refuses the correction — on six
    leagues out of seven, silently, and the counter would even look reassuring.
    """
    from app.models.models import Event
    from app.tasks.statpal_sync import _sync_statpal_schedules

    now = datetime.now(timezone.utc)
    session, ids = _wire_soccer(monkeypatch)
    _stub_soccer_service(monkeypatch, now)

    result = await _sync_statpal_schedules(SOCCER_A)

    assert result["schedule_fid_cross_sport_skipped"] == 0, (
        "a sibling soccer league is the SAME StatPal sport, so it is not "
        f"cross-sport. Got: {result}"
    )
    session.expunge_all()
    row = session.get(Event, ids["serie_a"])
    expected = now - timedelta(hours=2)
    assert abs((row.commence_time - expected).total_seconds()) < 5, (
        "the Serie A row's kickoff correction must land during the EPL pass — "
        f"they share StatPal's `soccer` id space. Got {row.commence_time}."
    )


# ─────────────────────────────────────────────────────────────────────────────
# The control — the rail must be able to SEE the defect
# ─────────────────────────────────────────────────────────────────────────────


class TestTheRailCanSeeTheDefect:
    """Re-run the scenario through the shipped resolution; require the raise.

    Without this, a rail whose session committed regardless of the exception —
    or which never reached the colliding fixture at all — would pass on the
    broken code and prove nothing.
    """

    @pytest.mark.asyncio
    async def test_scalar_one_or_none_raises_on_the_production_pair(
        self, monkeypatch
    ):
        from sqlalchemy import select
        from sqlalchemy.exc import MultipleResultsFound

        from app.models.models import Event

        session, _ids = _wire(monkeypatch)

        result = session.execute(
            select(Event).where(
                Event.statpal_fixture_id == COLLIDING_FIXTURE_ID
            )
        )
        with pytest.raises(MultipleResultsFound):
            result.scalar_one_or_none()

    @pytest.mark.asyncio
    async def test_a_raise_mid_pass_loses_the_siblings_write(self, monkeypatch):
        """The cost claim, demonstrated: rollback discards the earlier write.

        This is why the fix is 'do not raise' rather than 'let the task retry'.
        """
        from app.models.models import Event

        session, ids = _wire(monkeypatch)
        import app.tasks.base as task_base

        sibling = session.get(Event, ids["sibling"])
        original = sibling.commence_time

        with pytest.raises(RuntimeError):
            async with task_base.get_task_session() as s:
                row = s.get(Event, ids["sibling"])
                row.commence_time = original + timedelta(minutes=40)
                await s.flush()
                raise RuntimeError("MultipleResultsFound stands in here")

        # Expunge, not expire: a still-persistent instance is refreshed without
        # firing `loaded_as_persistent`, so sqlite's naive datetime comes back
        # unreattached and the comparison below raises instead of asserting.
        session.expunge_all()
        after = session.get(Event, ids["sibling"])
        assert abs((after.commence_time - original).total_seconds()) < 5, (
            "The rollback must discard the pending correction. If this fails "
            "the rail is not faithful to `get_task_session` and every other "
            "assertion in this file is worth less."
        )


# ─────────────────────────────────────────────────────────────────────────────
# The call site
# ─────────────────────────────────────────────────────────────────────────────


class TestTheCallSite:
    """The resolution may not go back to raising inside the loop."""

    def _anchor_lookup_source(self) -> str:
        """Only the `if fixture.fixture_id:` branch that resolves the anchor.

        Scoped to the BRANCH, not the file and not even the whole function. The
        function legitimately holds a SECOND `scalar_one_or_none()` — the
        live-create existence check, whose query carries `.limit(1)` and so can
        never raise. A function-wide ban would red on that safe call, and a
        reviewer would "fix" it by loosening the guard.
        """
        tree = ast.parse(SOURCE_PATH.read_text())
        for fn in ast.walk(tree):
            if not (
                isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef))
                and fn.name == "_sync_statpal_schedules"
            ):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.If):
                    continue
                branch = ast.unparse(node)
                if "Event.statpal_fixture_id == fixture.fixture_id" in branch:
                    return branch
            raise AssertionError(
                "the anchor-resolution branch is gone — if the lookup moved, "
                "move this guard with it rather than deleting it"
            )
        raise AssertionError("_sync_statpal_schedules not found")

    def test_the_anchor_lookup_does_not_call_scalar_one_or_none(self):
        source = self._anchor_lookup_source()
        assert "scalar_one_or_none" not in source, (
            "`scalar_one_or_none()` raises `MultipleResultsFound` on the seven "
            "ids production carries on two rows, and this function has no "
            "intermediate commit — so the raise costs the whole pass (#4307). "
            "Resolve through `row_for_statpal_id`."
        )

    def test_it_resolves_through_the_named_judgement(self):
        source = self._anchor_lookup_source()
        assert "row_for_statpal_id(" in source, (
            "The ambiguity must be resolved by the named helper, so the "
            "judgement stays testable on its own."
        )

    def test_the_safe_sibling_call_is_left_alone(self):
        """The ban is on the UNBOUNDED lookup, not on the method.

        Pins that the guard above is narrow on purpose: the live-create
        existence check still uses `scalar_one_or_none()` and is still correct,
        because its query is `.limit(1)`. If someone widens the ban to the file,
        this fails and says why.
        """
        tree = ast.parse(SOURCE_PATH.read_text())
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
            and n.name == "_sync_statpal_schedules"
        )
        body = ast.unparse(fn)
        assert "existing.scalar_one_or_none()" in body
        assert ".limit(1)" in body

    def test_the_guard_fires_on_the_code_that_shipped(self):
        """A structural guard is only worth having if it reds on the real code.

        The detector is "does this branch text contain the raising call", so the
        control feeds it the branch exactly as production ran it.
        """
        shipped_branch = (
            "if fixture.fixture_id:\n"
            "    fid_result = await session.execute("
            "select(Event).where(Event.statpal_fixture_id == fixture.fixture_id))\n"
            "    event = fid_result.scalar_one_or_none()"
        )
        assert "scalar_one_or_none" in shipped_branch, (
            "the control's own input no longer contains the defect"
        )
        assert "row_for_statpal_id(" not in shipped_branch
