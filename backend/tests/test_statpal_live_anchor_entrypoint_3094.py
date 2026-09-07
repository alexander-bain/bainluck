"""#3094 — the LIVE anchor rule, proved through the TASK and not through its helper.

`STATPAL-LIVE-ANCHOR-ENTRYPOINT-CONTRACT`, the nonblocking follow-up from
CERT-2137.

`test_statpal_live_anchor_field.py` already proves `_live_anchor_id` — thoroughly,
over every sport and every id shape. What it cannot prove is that
`_sync_statpal_livescores` *calls* it, calls it with the right sport, writes what
it returns, and counts what it refuses. A pure-helper test passes unchanged
against a task that never invokes the helper at all, and the defect this ship
exists for was not a wrong helper: **364 MLB rows carry a wrong-space id because
the writer wrote `fixture.fixture_id`**. That write happens here, in the task, so
this is where the guard belongs.

So every test below drives the REAL task over a REAL session and asserts on the
column and on the returned metrics. Nothing is stubbed but the HTTP client.

## Why the telemetry is asserted from the task's RETURN VALUE

`anchor_skipped_no_field` is a task return value, not a published field. It does
not appear on `/api/admin/statpal/authority-agreement` and never will, so it
cannot be discharged by reading that endpoint — a check that "passed" from the
agreement payload would be reporting on a number that payload does not contain.
The task-metrics path is the only path, and this file is it.

The harness (real ORM statements over sqlite, async shim over a sync session) is
the one established in `test_authority_failover_3473.py`; it is repeated rather
than imported because that file is another lane's subject and a shared fixture
would couple two ships' test files at exactly the point either might rewrite.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.utils.sport_keys import STATPAL_LIVE_ANCHOR_FIELD, STATPAL_SPORT_MAPPING


# `Event` carries Postgres JSONB/ARRAY columns sqlite cannot render as DDL. The
# repo's standing shim (see `test_proven_duplicate_2263`,
# `test_authority_failover_3473`), so these tests create the REAL tables from the
# REAL models rather than a hand-built stand-in that could drift from the schema
# the writer actually writes to.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"

MLB_KEY = "baseball_mlb"
NFL_KEY = "americanfootball_nfl"

#: The id space the anchor must land in — StatPal's `season-schedule` id, which
#: is what `odds_id` carries on the live board. A real value from the measured
#: 6-digit MLB space.
MLB_ODDS_ID = "354453"

#: The id space the anchor must NOT land in: the LIVE endpoint's own `id`, a
#: third space that dereferences to nothing on the schedule. 10 digits, the shape
#: all 364 production defects carry.
MLB_LIVE_ID = "1329190539"

#: NFL declares no anchor field, so its live `fixture_id` IS its anchor and must
#: keep working exactly as before. A real contestid shape.
NFL_FIXTURE_ID = "280445"


class _Fixture:
    """A StatPal live-board row, carrying state so the writer will act on it."""

    def __init__(
        self,
        start_time,
        home,
        away,
        fixture_id=None,
        odds_id=None,
        home_score=3,
        away_score=1,
        raw_status="T5",
    ):
        self.start_time = start_time
        self.home_team = home
        self.away_team = away
        self.status = "live"
        self.fixture_id = fixture_id
        self.odds_id = odds_id
        self.home_score = home_score
        self.away_score = away_score
        self.raw_status = raw_status


async def _run_livescores(monkeypatch, *, sport_key, fixtures, events, preset_anchor=None):
    """Drive the real task over one sport and return `(result, event_rows)`.

    `events` is a list of (home, away) pairs; a fixture only reaches the writer
    if its own names key to the same pair. Rows come back in insertion order.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    import app.services.statpal_api as statpal_api
    import app.tasks.base as task_base
    from app.models.models import Base, Event, ScoreSnapshot, Sport
    from app.tasks.statpal_sync import _sync_statpal_livescores

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Event.__table__, Sport.__table__, ScoreSnapshot.__table__]
    )
    # `expire_on_commit=False` matches the app's own task sessions (gotcha #6).
    # Without it sqlite reloads `commence_time` NAIVE after commit and the
    # writer's premature-live guard raises against an aware `now`. A sqlite
    # artifact, not a production shape.
    sync_session = Session(engine, expire_on_commit=False)

    # sqlite has no tz-aware timestamp type, so every datetime RELOADED from it
    # comes back naive — and the writer's premature-live guard (#1945) compares
    # `commence_time` against an aware `now`, so a naive reload would raise and
    # silently eat every assertion below. Postgres returns these aware, so this
    # is a fidelity gap in the rail, not a shape the code must handle. Written
    # into `__dict__` so it does not mark the attribute dirty.
    @sa_event.listens_for(sync_session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    sport = Sport(key=sport_key, name=sport_key)
    sync_session.add(sport)
    sync_session.flush()
    event_ids = []
    for home, away in events:
        row = Event(
            sport_id=sport.id,
            home_team_name=home,
            away_team_name=away,
            # An hour in the PAST: the premature-live guard (#1945) refuses to
            # write a live score onto a row that has not started, and would
            # silently eat every assertion below.
            commence_time=now - timedelta(hours=1),
            status="live",
        )
        if preset_anchor is not None:
            row.statpal_fixture_id = preset_anchor
        sync_session.add(row)
        sync_session.flush()
        event_ids.append(row.id)
    sync_session.commit()

    class _AsyncShim:
        def __init__(self, session):
            self._s = session

        async def execute(self, statement):
            return self._s.execute(statement)

        def add(self, obj):
            self._s.add(obj)

        async def commit(self):
            self._s.commit()

        async def flush(self):
            self._s.flush()

    class _Ctx:
        async def __aenter__(self_inner):
            return _AsyncShim(sync_session)

        async def __aexit__(self_inner, *exc):
            sync_session.commit()
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(
        "app.tasks.statpal_sync.get_task_session", lambda: _Ctx(), raising=False
    )
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    class _Service:
        async def get_live_scores(self, sport):
            return list(fixtures)

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    result = await _sync_statpal_livescores()
    rows = [
        sync_session.execute(select(Event).where(Event.id == i)).scalar_one()
        for i in event_ids
    ]
    return result, rows


def _mlb_detail(result):
    """The MLB entry of the task's per-sport detail list."""
    return next(d for d in result["sports"] if d["sport"] == "mlb")


# ---------------------------------------------------------------------------
# 1. The write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mlb_anchors_from_oddsid_through_the_real_task(monkeypatch):
    """The ship, end to end: a live MLB row anchors on `odds_id`.

    Control arm: `MLB_LIVE_ID` is present on the same fixture throughout. Without
    it the test would pass against a writer that simply wrote whatever single id
    it was handed, which is the writer that produced the 364 defects.
    """
    now = datetime.now(timezone.utc)
    fixture = _Fixture(
        now - timedelta(hours=1),
        "Red Sox",
        "Yankees",
        fixture_id=MLB_LIVE_ID,
        odds_id=MLB_ODDS_ID,
    )
    result, (event,) = await _run_livescores(
        monkeypatch,
        sport_key=MLB_KEY,
        fixtures=[fixture],
        events=[("Red Sox", "Yankees")],
    )

    assert event.statpal_fixture_id == MLB_ODDS_ID, result
    assert event.statpal_fixture_id != MLB_LIVE_ID, (
        "the writer took the LIVE id — this is the exact defect that put 364 "
        "wrong-space ids in production"
    )
    # The JSONB mirror the column is shadowed by must agree; a reader that
    # consults it would otherwise see the old, wrong answer.
    assert (event.win_probability_sources or {}).get(
        "statpal_fixture_id"
    ) == MLB_ODDS_ID
    assert _mlb_detail(result)["anchor_skipped_no_field"] == 0


# ---------------------------------------------------------------------------
# 2. The refusal, and the count that makes it visible
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("odds_id", [None, "", "   "])
@pytest.mark.asyncio
async def test_a_blank_oddsid_leaves_the_column_null_and_is_counted(
    monkeypatch, odds_id
):
    """3 of 16 live MLB rows carried `oddsid: ""` when it was measured.

    A NULL column is a row the schedule pass can still anchor correctly. A
    wrong-space id is a linkage that reads as authoritative and joins to nothing,
    so refusing is right — but a silent refusal is how 364 rows accumulated, so
    the refusal must also be COUNTED.

    Both halves are asserted. Either alone is satisfiable by a broken writer: the
    NULL alone by one that anchors nothing at all, the count alone by one that
    counts and then writes the wrong id anyway.
    """
    now = datetime.now(timezone.utc)
    fixture = _Fixture(
        now - timedelta(hours=1),
        "Red Sox",
        "Yankees",
        fixture_id=MLB_LIVE_ID,
        odds_id=odds_id,
    )
    result, (event,) = await _run_livescores(
        monkeypatch,
        sport_key=MLB_KEY,
        fixtures=[fixture],
        events=[("Red Sox", "Yankees")],
    )

    assert event.statpal_fixture_id is None, (
        f"odds_id={odds_id!r} produced an anchor anyway: "
        f"{event.statpal_fixture_id!r}"
    )
    assert (event.win_probability_sources or {}).get("statpal_fixture_id") is None
    assert _mlb_detail(result)["anchor_skipped_no_field"] == 1, result

    # Non-vacuity: the refusal is about the ANCHOR, not about the pass. The score
    # still had to be written, or this test would also pass for a writer that
    # skipped the row entirely.
    assert event.home_score == 3, result
    assert event.away_score == 1, result


@pytest.mark.asyncio
async def test_the_skip_count_is_a_count_and_not_a_flag(monkeypatch):
    """Two refused rows report 2.

    A boolean dressed as an integer would satisfy every other test in this file,
    and so would a counter that reset per row.
    """
    now = datetime.now(timezone.utc)
    fixtures = [
        _Fixture(
            now - timedelta(hours=1),
            "Red Sox",
            "Yankees",
            fixture_id=MLB_LIVE_ID,
            odds_id="",
        ),
        _Fixture(
            now - timedelta(hours=1),
            "Cubs",
            "Cardinals",
            fixture_id="1329190540",
            odds_id="",
        ),
    ]
    result, rows = await _run_livescores(
        monkeypatch,
        sport_key=MLB_KEY,
        fixtures=fixtures,
        events=[("Red Sox", "Yankees"), ("Cubs", "Cardinals")],
    )

    assert _mlb_detail(result)["anchor_skipped_no_field"] == 2, result
    assert [r.statpal_fixture_id for r in rows] == [None, None], result


# ---------------------------------------------------------------------------
# 3. The telemetry's SHAPE — presence is itself the signal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_anchor_keys_are_reported_only_for_a_sport_that_declares_one(
    monkeypatch,
):
    """The key's PRESENCE says "this sport has a second id space".

    Emitting `anchor_skipped_no_field: 0` for every sport would turn it into a
    general health metric it is not, and the zero would be read as "nothing went
    wrong here" for sports where the question does not arise.

    Control arm: the MLB half of this assertion lives in the tests above, so this
    one is free to be about NFL's ABSENCE without being vacuous.
    """
    now = datetime.now(timezone.utc)
    fixture = _Fixture(
        now - timedelta(hours=1), "Bears", "Packers", fixture_id=NFL_FIXTURE_ID
    )
    result, _ = await _run_livescores(
        monkeypatch,
        sport_key=NFL_KEY,
        fixtures=[fixture],
        events=[("Bears", "Packers")],
    )

    nfl = next(d for d in result["sports"] if d["sport"] == "nfl")
    assert "anchor_skipped_no_field" not in nfl, (
        "NFL declares no anchor field, so a skip count for it is a number about "
        f"a question that does not arise: {nfl}"
    )
    assert "anchor_field" not in nfl


@pytest.mark.asyncio
async def test_the_reported_anchor_field_is_the_one_the_map_declares(monkeypatch):
    """`anchor_field` must name the real declaration, not a literal.

    Asserted against `STATPAL_LIVE_ANCHOR_FIELD` rather than against the string
    `"odds_id"`, so renaming the field in the map cannot leave the telemetry
    reporting a field name that no longer exists.
    """
    now = datetime.now(timezone.utc)
    fixture = _Fixture(
        now - timedelta(hours=1),
        "Red Sox",
        "Yankees",
        fixture_id=MLB_LIVE_ID,
        odds_id=MLB_ODDS_ID,
    )
    result, _ = await _run_livescores(
        monkeypatch,
        sport_key=MLB_KEY,
        fixtures=[fixture],
        events=[("Red Sox", "Yankees")],
    )

    assert _mlb_detail(result)["anchor_field"] == STATPAL_LIVE_ANCHOR_FIELD["mlb"]


# ---------------------------------------------------------------------------
# 4. Preservation — the declaration is an exception, not a new general rule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nfl_still_anchors_on_its_live_fixture_id(monkeypatch):
    """The sport that declares nothing keeps the parser's answer unchanged.

    This is the regression that matters most in the other direction: #3094
    narrowed the rule for ONE measured sport, and a change that narrowed it for
    everyone would silently stop anchoring every other sport from the live board.
    """
    now = datetime.now(timezone.utc)
    fixture = _Fixture(
        now - timedelta(hours=1), "Bears", "Packers", fixture_id=NFL_FIXTURE_ID
    )
    _, (event,) = await _run_livescores(
        monkeypatch,
        sport_key=NFL_KEY,
        fixtures=[fixture],
        events=[("Bears", "Packers")],
    )

    assert event.statpal_fixture_id == NFL_FIXTURE_ID


@pytest.mark.asyncio
async def test_an_already_anchored_row_is_not_overwritten(monkeypatch):
    """`not _get_statpal_id(event)` guards the write, and it must keep guarding it.

    A row anchored correctly by the SCHEDULE pass — whose `id` for MLB already is
    the anchor — must not be re-pointed by the live pass. Gotcha #15's shape: if
    it is already set, trust it.
    """
    now = datetime.now(timezone.utc)
    fixture = _Fixture(
        now - timedelta(hours=1),
        "Red Sox",
        "Yankees",
        fixture_id=MLB_LIVE_ID,
        odds_id=MLB_ODDS_ID,
    )
    _, (event,) = await _run_livescores(
        monkeypatch,
        sport_key=MLB_KEY,
        fixtures=[fixture],
        events=[("Red Sox", "Yankees")],
        preset_anchor="999999",
    )

    assert event.statpal_fixture_id == "999999"


# ---------------------------------------------------------------------------
# 5. The declaration itself
# ---------------------------------------------------------------------------


def test_mlb_is_the_only_declared_sport_and_it_maps_to_a_real_key():
    """If a second sport joins the map, this file must grow a case for it.

    A declaration nobody drives through the task is a declaration whose writer is
    unproven, which is the exact hole this follow-up exists to close.
    """
    assert set(STATPAL_LIVE_ANCHOR_FIELD) == {"mlb"}
    assert STATPAL_SPORT_MAPPING[MLB_KEY] == "mlb"
    assert STATPAL_SPORT_MAPPING[NFL_KEY] == "nfl"
    assert "nfl" not in STATPAL_LIVE_ANCHOR_FIELD
