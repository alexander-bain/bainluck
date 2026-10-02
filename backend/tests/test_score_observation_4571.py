"""#4571 — a live score states its own age, and who read it.

The defect class these guard: a stamp that exists but is written on the wrong
condition. Every score write site in this codebase is shaped
`if incoming != current: current = incoming`, so the natural place to put a
stamp is inside that guard — and there it answers "when did the score last
CHANGE", which is null for exactly the row #4571 was filed about (a 0-0 NFL
opener confirmed every 30s and changed never). A test that only asserts "the
stamp is set when the score moves" passes against that bug.

So the assertions below are deliberately weighted to the NO-CHANGE path, plus
an AST guard that the stamp calls are not nested inside the `!=` comparisons —
because a future edit that moves them back in would keep every value-level test
green.
"""

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.utils.score_observation import (
    SCORE_OBSERVATION_SOURCES,
    SCORE_SOURCE_ODDS,
    clear_score_observation,
    score_observation_fields,
    score_observation_values,
    stamp_score_observation,
)

BACKEND = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc)


def _aware(dt):
    """sqlite hands datetimes back naive on a refresh; Postgres (timestamptz)
    never does. Normalise on the TEST side only — the writer is not taught to
    accept a naive clock it can never receive in production."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _event(**kw):
    base = dict(
        id=1,
        status="live",
        home_score=None,
        away_score=None,
        score_source=None,
        score_observed_at=None,
        home_team_name="Home",
        away_team_name="Away",
        commence_time=NOW - timedelta(hours=1),
        completed_at=None,
        game_clock=None,
        period=None,
        broadcast_info=None,
        llm_importance=None,
        espn_id=None,
        commence_time_source=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ───────────────────────── the helper's contract ─────────────────────────


def test_stamp_records_source_and_observation_clock():
    ev = _event()
    assert stamp_score_observation(ev, source="espn", observed_at=NOW) is True
    assert ev.score_source == "espn"
    assert ev.score_observed_at == NOW


def test_stamp_uses_the_callers_clock_not_wall_clock():
    """The clock is the OBSERVATION's, not the row write's.

    A helper that fell back to `now()` would turn a read that lagged ten
    minutes into a fresh-looking stamp — the single failure the column exists
    to make visible.
    """
    stale = NOW - timedelta(minutes=10)
    ev = _event()
    stamp_score_observation(ev, source="statpal", observed_at=stale)
    assert ev.score_observed_at == stale


def test_stamp_without_a_clock_declines_rather_than_inventing_one():
    ev = _event()
    assert stamp_score_observation(ev, source="espn", observed_at=None) is False
    assert ev.score_source is None
    assert ev.score_observed_at is None


@pytest.mark.parametrize("bad", ["ESPN", "odds", "", "statpal_livescores", "mlb"])
def test_unknown_source_raises_rather_than_reaching_the_column(bad):
    """A typo'd source reads as a fourth writer in #4576's attribution query."""
    ev = _event()
    with pytest.raises(ValueError):
        stamp_score_observation(ev, source=bad, observed_at=NOW)
    assert ev.score_source is None


def test_every_permitted_source_fits_the_column():
    from app.models.models import Event

    width = Event.__table__.c.score_source.type.length
    for source in SCORE_OBSERVATION_SOURCES:
        assert len(source) <= width, f"{source!r} overflows score_source"


def test_clear_drops_both_halves():
    ev = _event(score_source="espn", score_observed_at=NOW)
    clear_score_observation(ev)
    assert ev.score_source is None and ev.score_observed_at is None


# ───────────────────────── the payload contract ─────────────────────────


def test_payload_is_present_only_for_an_unread_row():
    assert score_observation_fields(_event()) == {}


def test_payload_serves_both_keys_together():
    ev = _event(score_source="statpal", score_observed_at=NOW)
    assert score_observation_fields(ev) == {
        "score_source": "statpal",
        "score_observed_at": NOW.isoformat(),
    }


@pytest.mark.parametrize(
    "source,observed",
    [("espn", None), (None, NOW)],
)
def test_half_a_stamp_is_served_as_none(source, observed):
    """A source with no clock cannot be aged; a clock with no source cannot be
    attributed. Neither half is served alone."""
    ev = _event(score_source=source, score_observed_at=observed)
    assert score_observation_fields(ev) == {}


def test_payload_is_additive_and_touches_no_existing_key():
    ev = _event(score_source="espn", score_observed_at=NOW)
    assert set(score_observation_fields(ev)) == {
        "score_source",
        "score_observed_at",
    }


# ──────────────── the no-change path, at the real write sites ────────────────
#
# Driven through the REAL ESPN writer against a REAL (sqlite) row, and read back
# from the DATABASE after `expire_all()`. Since #6056 the four live-state columns
# — and, since this recomposition, the stamp beside them — are written by one
# conditional UPDATE; an in-memory object cannot tell a write that matched zero
# rows from one that landed, because SQLAlchemy mirrors the values either way.


def _load_6056_rails():
    """#6056's sqlite rails (StatPal, tennis, interlopers), loaded by PATH.

    Same reason as `_straggler_harness` below: `tests/` is not on `sys.path`
    under every rootdir. Loading it also registers its JSONB/ARRAY-on-sqlite
    compilers, which the ESPN rail here needs too.
    """
    import importlib.util

    path = Path(__file__).with_name("test_live_state_does_not_run_backwards_6056.py")
    spec = importlib.util.spec_from_file_location("_rails_6056", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Board:
    """An ESPN board row shaped as `update_event_fields_from_espn` reads it."""

    def __init__(self, *, home_score, away_score, clock="5:21",
                 status_detail="5:21 - 4th Quarter", status="in"):
        self.clock = clock
        self.status_detail = status_detail
        self.home_score = home_score
        self.away_score = away_score
        self.date = None
        self.period = None
        self.broadcasts = []
        self.season_type = None
        self.state = status
        self.status = status
        self.completed = False
        self.status_type = "STATUS_IN_PROGRESS"


async def _espn_writes(
    *, row_home, row_away, board, observed_at, held_stamp=None,
    period="5:21 - 4th Quarter", game_clock="5:21", interloper=None,
    monkeypatch=None,
):
    """Run the real ESPN writer once; return (row as served, stats, changed)."""
    from sqlalchemy import create_engine, select
    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session

    _load_6056_rails()  # sqlite compilers for JSONB / ARRAY
    import app.utils.espn_helpers as espn_helpers
    from app.models.models import Base, ESPNSnapshot, Event, ScoreSnapshot, Sport

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[
        Event.__table__, Sport.__table__, ScoreSnapshot.__table__,
        ESPNSnapshot.__table__,
    ])
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    sport = Sport(key="americanfootball_nfl", name="NFL")
    session.add(sport)
    session.flush()
    event = Event(
        sport_id=sport.id, home_team_name="Seattle Seahawks",
        away_team_name="New England Patriots",
        commence_time=datetime.now(timezone.utc) - timedelta(hours=1),
        status="live", period=period, game_clock=game_clock,
        home_score=row_home, away_score=row_away, espn_id="401772510",
        commence_time_source="espn", win_probability_sources={},
        score_source="statpal" if held_stamp else None,
        score_observed_at=held_stamp,
    )
    session.add(event)
    session.commit()
    # Not re-read: `expire_on_commit=False` keeps the aware values the writer
    # would get from Postgres, where sqlite would hand them back naive.
    event_id = event.id

    class _Shim:
        def __init__(self, inner):
            self._s = inner

        async def execute(self, statement):
            return self._s.execute(statement)

        def add(self, obj):
            self._s.add(obj)

        async def flush(self):
            self._s.flush()

    if interloper is not None:
        real = espn_helpers.live_write_would_revert
        fired = []

        def _race(*args, **kwargs):
            verdict = real(*args, **kwargs)
            if not verdict and not fired:
                fired.append(True)
                interloper(engine, event_id)
            return verdict

        monkeypatch.setattr(espn_helpers, "live_write_would_revert", _race)

    stats: dict = {}
    changed = await espn_helpers.update_event_fields_from_espn(
        _Shim(session), event, board, set(), stats, observed_at=observed_at,
    )
    session.commit()
    session.expire_all()
    row = session.execute(select(Event).where(Event.id == event_id)).scalar_one()
    return row, stats, changed


@pytest.mark.asyncio
async def test_espn_stamps_a_score_it_did_not_change():
    """#4571's own specimen: 0-0, confirmed, unchanged — and the row is not
    reported as CHANGED for it (a confirmation is not an update)."""
    row, stats, changed = await _espn_writes(
        row_home=0, row_away=0, board=_Board(home_score=0, away_score=0),
        observed_at=NOW,
    )
    assert _aware(row.score_observed_at) == NOW, (
        "a 0-0 game ESPN confirmed but did not change carries no age — "
        "the stamp is gated on change, not on observation (#4571)"
    )
    assert row.score_source == "espn"
    assert (row.home_score, row.away_score) == (0, 0)
    assert changed is False, "a confirmation-only write must not count as a change"
    assert stats.get("live_state_write_lost_race", 0) == 0


@pytest.mark.asyncio
async def test_espn_stamps_a_changed_score_in_the_same_write():
    row, _stats, changed = await _espn_writes(
        row_home=0, row_away=0, board=_Board(home_score=7, away_score=0),
        observed_at=NOW,
    )
    assert (row.home_score, row.away_score) == (7, 0)
    assert (row.score_source, _aware(row.score_observed_at)) == ("espn", NOW)
    assert changed is True


@pytest.mark.asyncio
async def test_espn_without_an_observation_clock_leaves_the_row_unstamped():
    row, _stats, _changed = await _espn_writes(
        row_home=0, row_away=0, board=_Board(home_score=0, away_score=0),
        observed_at=None,
    )
    assert row.score_observed_at is None and row.score_source is None


@pytest.mark.asyncio
async def test_espn_does_not_stamp_a_row_it_read_no_score_for():
    """ESPN stating no score — or half of one — is not an observation of the
    score tuple the row shows."""
    for home, away in ((None, None), (3, None)):
        row, _stats, _changed = await _espn_writes(
            row_home=3, row_away=0, board=_Board(home_score=home, away_score=away),
            observed_at=NOW,
        )
        assert row.score_source is None and row.score_observed_at is None


@pytest.mark.asyncio
async def test_espn_refused_as_a_reversion_stamps_nothing():
    """A reading from EARLIER in the game is refused (#6056). It confirmed
    nothing about the score the row holds, so it must not date it."""
    row, stats, _changed = await _espn_writes(
        row_home=28, row_away=20,
        board=_Board(home_score=28, away_score=14, clock="5:26",
                     status_detail="5:26 - 4th Quarter"),
        observed_at=NOW,
    )
    assert (row.home_score, row.away_score) == (28, 20)
    assert row.score_observed_at is None, (
        "a refused, older ESPN reading stamped the row's score as confirmed"
    )
    assert stats["live_state_reversions_refused"] == 1


@pytest.mark.asyncio
async def test_espn_lost_race_drops_the_stamp_with_the_score(monkeypatch):
    """Another writer commits a newer state between our read and our write: the
    compare-and-write refuses, and the stamp — riding the same statement — is
    refused with it, so our clock never dates the other writer's number."""
    rails = _load_6056_rails()
    row, stats, _changed = await _espn_writes(
        row_home=0, row_away=0, board=_Board(home_score=0, away_score=0),
        observed_at=NOW,
        interloper=rails._commits_a_later_position("5:10 - 4th Quarter", "5:10", (7, 0)),
        monkeypatch=monkeypatch,
    )
    assert (row.home_score, row.away_score) == (7, 0)
    assert row.score_observed_at is None and row.score_source is None
    assert stats["score_confirmation_lost_race"] == 1
    assert stats.get("live_state_write_lost_race", 0) == 0


@pytest.mark.asyncio
async def test_an_earlier_confirmation_never_moves_the_stamp_backwards():
    """Same tuple, older read: a later confirmation already stands, keep it."""
    later = NOW + timedelta(seconds=30)
    row, _stats, _changed = await _espn_writes(
        row_home=0, row_away=0, board=_Board(home_score=0, away_score=0),
        observed_at=NOW, held_stamp=later,
    )
    assert (row.score_source, _aware(row.score_observed_at)) == ("statpal", later)


@pytest.mark.asyncio
async def test_a_changed_score_takes_its_own_clock_even_if_older():
    """A NEW tuple has no older confirmation that could describe it — keeping
    the previous stamp would date ESPN's number with StatPal's read."""
    later = NOW + timedelta(seconds=30)
    row, _stats, _changed = await _espn_writes(
        row_home=0, row_away=0, board=_Board(home_score=7, away_score=0),
        observed_at=NOW, held_stamp=later,
    )
    assert (row.home_score, row.away_score) == (7, 0)
    assert (row.score_source, _aware(row.score_observed_at)) == ("espn", NOW)


# ── the same rules at the StatPal 30-second writer and the tennis authority ──


def _statpal_specimen(rails, scores, *, clock="5:21"):
    now = datetime.now(timezone.utc)
    fixture = rails._Fixture(
        now - timedelta(hours=3), "Seattle Seahawks", "New England Patriots",
        raw_status="4th Quarter", game_clock=clock, scores=scores,
    )
    events = [(
        "Seattle Seahawks", "New England Patriots", "5:21",
        "5:21 - 4th Quarter", (0, 0),
    )]
    return fixture, events


@pytest.mark.asyncio
async def test_statpal_stamps_a_score_it_confirmed_at_its_own_read(monkeypatch):
    rails = _load_6056_rails()
    fixture, events = _statpal_specimen(rails, (0, 0))
    before = datetime.now(timezone.utc)
    rows, snaps, result = await rails._run_livescores(
        monkeypatch, fixtures=[fixture], events=events,
    )
    after = datetime.now(timezone.utc)
    row = rows[0]
    assert row.score_source == "statpal"
    assert before <= _aware(row.score_observed_at) <= after
    assert (row.home_score, row.away_score) == (0, 0)
    assert snaps == [], "a confirmation is not a score change"
    assert result["livescore_confirmation_lost_race"] == 0


@pytest.mark.asyncio
async def test_statpal_refused_as_a_reversion_stamps_nothing(monkeypatch):
    rails = _load_6056_rails()
    fixture, events = _statpal_specimen(rails, (0, 0), clock="9:40")
    rows, _snaps, result = await rails._run_livescores(
        monkeypatch, fixtures=[fixture], events=events,
    )
    assert result["reverting_live_skipped"] == 1
    assert rows[0].score_observed_at is None


@pytest.mark.asyncio
async def test_statpal_lost_race_drops_the_stamp(monkeypatch):
    rails = _load_6056_rails()
    fixture, events = _statpal_specimen(rails, (0, 0))
    rows, _snaps, result = await rails._run_livescores(
        monkeypatch, fixtures=[fixture], events=events,
        interloper=rails._commits_a_later_position("5:10 - 4th Quarter", "5:10", (7, 0)),
    )
    assert (rows[0].home_score, rows[0].away_score) == (7, 0)
    assert rows[0].score_observed_at is None
    assert result["livescore_confirmation_lost_race"] == 1
    assert result["livescore_live_write_lost_race"] == 0


async def _schedule_pass(monkeypatch, rails, *, clock, scores):
    now = datetime.now(timezone.utc)
    return await rails._run_schedules(
        monkeypatch,
        schedule=[rails._ScheduleFixture(
            now - timedelta(hours=3), "New York Giants", "Dallas Cowboys",
            fixture_id="280459",
        )],
        live=[rails._LiveFixture(
            now - timedelta(hours=3), "New York Giants", "Dallas Cowboys",
            raw_status="4th Quarter", game_clock=clock, scores=scores,
        )],
        events=[(
            "New York Giants", "Dallas Cowboys", "5:21", "5:21 - 4th Quarter",
            (28, 20), "280459",
        )],
    )


@pytest.mark.asyncio
async def test_statpal_schedule_pass_stamps_a_confirmed_score(monkeypatch):
    rails = _load_6056_rails()
    before = datetime.now(timezone.utc)
    rows, _result = await _schedule_pass(monkeypatch, rails, clock="5:21", scores=(28, 20))
    assert rows[0].score_source == "statpal"
    assert _aware(rows[0].score_observed_at) >= before


@pytest.mark.asyncio
async def test_statpal_schedule_reversion_stamps_nothing(monkeypatch):
    rails = _load_6056_rails()
    rows, result = await _schedule_pass(monkeypatch, rails, clock="5:26", scores=(28, 14))
    assert result["schedule_reverting_live_skipped"] == 1
    assert rows[0].score_observed_at is None


@pytest.mark.asyncio
async def test_tennis_stamps_an_agreed_set_score(monkeypatch):
    rails = _load_6056_rails()
    before = datetime.now(timezone.utc)
    row, _stats = await rails._drive_tennis(
        monkeypatch, row_home=1, row_away=0, espn_home_sets=1, espn_away_sets=0,
    )
    assert row.score_source == "espn"
    assert row.score_observed_at is not None
    assert _aware(row.score_observed_at) >= before


@pytest.mark.asyncio
async def test_tennis_lost_race_drops_the_stamp(monkeypatch):
    rails = _load_6056_rails()
    row, stats = await rails._drive_tennis(
        monkeypatch, row_home=1, row_away=0, espn_home_sets=1, espn_away_sets=0,
        interloper=rails._commits_a_different_score(2, 0),
    )
    assert (row.home_score, row.away_score) == (2, 0)
    assert row.score_observed_at is None
    assert stats["score_confirmation_lost_race"] == 1
    assert stats["score_write_lost_race"] == 0


# ─────────────────── the wiring, not just the logic ───────────────────


def _calls_in(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name in (
                "stamp_score_observation",
                "clear_score_observation",
                # The Core-UPDATE spelling. `_poll_all_odds` writes scores
                # through `Event.__table__.update()`, so it cannot assign an ORM
                # attribute (gotcha #5) — it merges columns instead. Same rule,
                # different verb, and it must be held to both guards below.
                "score_observation_values",
                # The compare-and-write spelling (#6056): the stamp joined to
                # the score's own UPDATE, never assigned on the ORM row.
                "score_write_stamp_values",
                # The primary-key spelling: a write that does not re-assert its
                # loaded tuple, so the row itself is asked at the write.
                "score_write_stamp_values_at_row",
            ):
                yield node


def _module_tree(relpath):
    return ast.parse((BACKEND / relpath).read_text())


SITES = [
    "app/tasks/statpal_sync.py",
    "app/tasks/espn_sync.py",
    "app/utils/espn_helpers.py",
    # CERT-2460: missed by the first cut of #4571 because the issue's scope line
    # named "MLB Stats API" (which writes no score at all) and not this — an
    # active production writer, every ~5.5 min.
    "app/tasks/odds_polling.py",
]


@pytest.mark.parametrize("relpath", SITES)
def test_every_writer_module_stamps(relpath):
    calls = list(_calls_in(_module_tree(relpath)))
    assert calls, f"{relpath} writes scores but never stamps one (#4571)"


@pytest.mark.parametrize("relpath", SITES)
def test_no_stamp_is_nested_inside_a_score_inequality(relpath):
    """The AST guard that pins WHERE the stamp lives.

    Every value-level test above still passes if a stamp is moved back inside
    `if incoming != current:` — the change path is exercised by both shapes.
    Only reading the tree catches the regression that matters, so this asserts
    no stamp call sits under an `if` whose test compares two score expressions
    with `!=`.
    """
    tree = _module_tree(relpath)
    offenders = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test_src = ast.dump(node.test)
        if "NotEq" not in test_src or "score" not in test_src:
            continue
        for body_node in node.body:
            for call in _calls_in(ast.Module(body=[body_node], type_ignores=[])):
                offenders.append((relpath, getattr(call, "lineno", "?")))

    assert not offenders, (
        "score observation stamp nested inside a score `!=` guard "
        f"at {offenders} — it would answer 'when did the score last change', "
        "which is null for the 0-0 row #4571 was filed about"
    )


_HELPERS = {
    "stamp_score_observation", "clear_score_observation",
    "score_observation_values", "score_write_stamp_values",
    "score_write_stamp_values_at_row",
    "SCORE_SOURCE_ESPN", "SCORE_SOURCE_STATPAL", "SCORE_SOURCE_ODDS",
}


@pytest.mark.parametrize("relpath", SITES + ["app/routes/events.py"])
def test_every_helper_a_writer_uses_is_imported(relpath):
    """A helper called but not imported is a NameError on exactly the path that
    runs rarely — StatPal's live-row CREATION lost its import in this very
    recomposition and no behavioural test reached it. CI runs no pyflakes, so
    the import set is pinned here."""
    tree = _module_tree(relpath)
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "app.utils.score_observation"
        for alias in node.names
    }
    used = {
        node.id for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id in _HELPERS
    } | {"score_observation_fields"} & {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    missing = used - imported
    assert not missing, f"{relpath} uses {sorted(missing)} without importing them"


def test_espn_live_pass_hands_down_its_own_observation_clock():
    """`observed_at` defaults to None, so the feature is inert if the live
    caller stops passing it — and no value-level test would notice."""
    src = (BACKEND / "app/tasks/espn_sync.py").read_text()
    tree = ast.parse(src)

    passed = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "id", None) != "update_fields_fn":
            continue
        assert any(k.arg == "observed_at" for k in node.keywords), (
            "the live ESPN pass calls update_fields_fn without observed_at — "
            "scores would be written with no age (#4571)"
        )
        passed = True

    assert passed, "update_fields_fn call site not found — did it get renamed?"


def test_the_live_pass_stamps_with_each_boards_own_read_clock():
    """Every board is fetched BEFORE any sport is processed, so a clock taken
    inside `_process_live_sport` would date a later sport's scores by when its
    turn came, not by when ESPN was read. The clock is recorded per sport as its
    board returns, and handed down."""
    src = (BACKEND / "app/tasks/espn_sync.py").read_text()
    fetch = src.index("events = await espn.get_scoreboard(key)")
    bound = src.index("espn_read_at[key] = datetime.now(timezone.utc)")
    assert fetch < bound < fetch + 1200

    tree = ast.parse(src)
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", None) == "_process_live_sport"
    ]
    assert calls, "_process_live_sport call site not found"
    for call in calls:
        kw = {k.arg: k.value for k in call.keywords}
        assert "observed_at" in kw, "the live pass drops its board read clock"
        assert "espn_read_at" in ast.dump(kw["observed_at"])


def test_the_statpal_livescore_clock_is_the_boards_read():
    """`_now` is pass entry; each sport's board is read later than that."""
    src = (BACKEND / "app/tasks/statpal_sync.py").read_text()
    fetch = src.index("live_fixtures = await service.get_live_scores(statpal_sport)")
    bound = src.index("_read_at = datetime.now(timezone.utc)")
    assert fetch < bound < fetch + 400
    assert "observed_at=_read_at" in src


def test_the_clears_drop_the_stamp_with_the_score():
    """A stamp outliving its score is a fresh-looking age over a NULL."""
    src = (BACKEND / "app/tasks/espn_sync.py").read_text()
    tree = ast.parse(src)

    clears = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", None) == "clear_score_observation"
    ]
    nulls = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and isinstance(n.value, ast.Constant)
        and n.value.value is None
        and any(
            getattr(t, "attr", None) == "home_score" for t in n.targets
        )
    ]

    assert len(clears) >= len(nulls), (
        f"{len(nulls)} sites null home_score but only {len(clears)} clear the "
        "stamp — a surviving stamp ages a score that is gone (#4571)"
    )


# ────────── the payload wiring, proved on the real formatter's output ──────────
#
# CERT-2444's follow-up on #4582 asked for exactly this distinction: an AST guard
# proving "both operations occur" is weaker than reading the value the formatter
# actually returns. These call `_format_event` and assert on its dict.


def _formattable_event(**kw):
    """The minimum `_format_event` needs. It degrades on missing optional
    attributes (logging a warning), which is why a namespace suffices."""
    base = dict(
        id=1,
        home_team_name="Home",
        away_team_name="Away",
        commence_time=NOW - timedelta(hours=1),
        completed_at=None,
        status="live",
        home_score=3,
        away_score=1,
        score_source=None,
        score_observed_at=None,
        sport=SimpleNamespace(key="baseball_mlb", name="MLB"),
        box_score_data=None,
        win_probability_sources={},
        external_id="x",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_format_event_serves_the_stamp_it_holds():
    from app.routes.events import _format_event

    out = _format_event(
        _formattable_event(score_source="statpal", score_observed_at=NOW)
    )
    assert out["score_source"] == "statpal"
    assert out["score_observed_at"] == NOW.isoformat()


def test_format_event_omits_the_stamp_on_an_unread_row():
    """Present-only on the real formatter, not just in the helper — two null
    keys on every row of a 500-row single-sport list are bytes that can never
    carry an answer."""
    from app.routes.events import _format_event

    out = _format_event(_formattable_event())
    assert "score_source" not in out
    assert "score_observed_at" not in out


def test_format_event_still_serves_the_score_itself():
    """The stamp is ADDITIVE (#4571 scope item 2): no existing key changes
    shape, name or meaning, so no client is forced to cut over."""
    from app.routes.events import _format_event

    without = _format_event(_formattable_event())
    with_stamp = _format_event(
        _formattable_event(score_source="espn", score_observed_at=NOW)
    )

    assert with_stamp["home_score"] == without["home_score"] == 3
    assert with_stamp["away_score"] == without["away_score"] == 1
    assert set(without).issubset(set(with_stamp))
    assert set(with_stamp) - set(without) == {
        "score_source",
        "score_observed_at",
    }


def test_helper_stays_dependency_free():
    """Imported by two task modules and a helper; it must never be the reason
    one of them acquires a cycle (same discipline as sport_keys, gotcha #3).

    Read from the path like the AST guards above rather than re-importing the
    module under a second name: `from … import` at the top of this file plus an
    `import …` here is the same module bound two ways, which CodeQL flags
    (`py/import-and-import-from`, notice level) and which the rest of this file
    has no need of.
    """
    tree = _module_tree("app/utils/score_observation.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("app."), (
                f"score_observation imports {node.module} — keep it "
                "dependency-free"
            )


# ══ CERT-2460 REPAIR — 4571-ODDS-API-SCORE-WRITER-STAMPS-THE-READ ════════════
#
# The first cut of #4571 stamped ESPN and StatPal and MISSED
# `odds_polling._poll_all_odds`, which fetches The Odds API scores and writes
# `events.home_score`/`away_score` through a Core UPDATE every ~5.5 minutes.
#
# An unstamped writer is worse than an unstamped column. The row keeps whichever
# stamp a DIFFERENT source last left, so the payload serves an Odds API score
# under ESPN's name with a fresh-looking age — the precise lie the field exists
# to remove. #4576's attribution query would then name the wrong writer, which
# is the question this ship exists to answer.
#
# The site writes columns, not attributes, so the controls below exercise
# `score_observation_values` — the helper the site actually calls — and the AST
# guards pin that the site calls it, atomically, ungated by change. That is the
# same division this file already uses, and the same one
# `test_live_cadence_lat_p159` uses for this function: "the helper
# `_poll_all_odds` calls, never a local copy of its rule."

ODDS_SITE = "app/tasks/odds_polling.py"


# ── executable: the UNCHANGED 0-0 control ────────────────────────────────────


def test_core_values_stamp_a_score_that_did_not_change():
    """The 0-0 opener a writer confirms every pass and changes never.

    `score_observation_values` takes NO previous score — it cannot be made
    change-sensitive without adding a parameter, which is the strongest form
    this control can take.
    """
    assert score_observation_values(
        source=SCORE_SOURCE_ODDS, observed_at=NOW
    ) == {
        "score_source": "odds_api",
        "score_observed_at": NOW,
    }


@pytest.mark.parametrize("home,away", [(0, 0), (3, 1), (0, 7)])
def test_the_stamp_does_not_depend_on_the_score_at_all(home, away):
    """Whatever the numbers, an observation is an observation."""
    assert score_observation_values(
        source=SCORE_SOURCE_ODDS, observed_at=NOW
    ) == {
        "score_source": "odds_api",
        "score_observed_at": NOW,
    }


# ── executable: the NO-SCORE / no-clock controls ─────────────────────────────


def test_core_values_without_a_clock_stamp_nothing():
    """No clock, no stamp — an absent stamp reads as 'unknown age', which is
    honest. A wrong one is not."""
    assert score_observation_values(
        source=SCORE_SOURCE_ODDS, observed_at=None
    ) == {}


@pytest.mark.parametrize("bad", ["odds", "oddsapi", "OddsAPI", "", "espn2"])
def test_core_values_refuse_a_source_outside_the_registry(bad):
    with pytest.raises(ValueError):
        score_observation_values(source=bad, observed_at=NOW)


def test_odds_api_is_in_the_registry_and_fits_the_column():
    assert "odds_api" in SCORE_OBSERVATION_SOURCES
    assert len("odds_api") <= 20


def test_both_paths_share_one_registry():
    """The ORM stamp and the Core stamp must never disagree about who exists —
    a drift shows up as a silently unstamped writer, i.e. CERT-2460 again."""
    ev = SimpleNamespace(score_source=None, score_observed_at=None)
    for source in sorted(SCORE_OBSERVATION_SOURCES):
        assert stamp_score_observation(ev, source=source, observed_at=NOW) is True
        assert score_observation_values(source=source, observed_at=NOW)

    for bad in ("nope", "mlb"):
        with pytest.raises(ValueError):
            stamp_score_observation(ev, source=bad, observed_at=NOW)
        with pytest.raises(ValueError):
            score_observation_values(source=bad, observed_at=NOW)


# ── the wiring at the odds site ──────────────────────────────────────────────


def _odds_stamp_calls():
    return list(_calls_in(_module_tree(ODDS_SITE)))


def test_the_odds_writer_stamps_at_all():
    """The CERT-2460 defect itself: this returned [] before the repair."""
    assert _odds_stamp_calls(), (
        "odds_polling writes events.home_score but never stamps an observation "
        "(#4571 / CERT-2460)"
    )


def test_the_odds_stamp_is_merged_into_the_same_update_values():
    """ATOMICITY. The stamp must ride the SAME `update_values` dict as the score.

    Two separate writes would leave a window in which the row holds an Odds API
    score under the previous writer's attribution — a narrower version of the
    bug being fixed, and a much harder one to see.
    """
    tree = _module_tree(ODDS_SITE)
    merged = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        # `update_values.update(score_write_stamp_values_at_row(...))`
        if getattr(fn, "attr", None) != "update":
            continue
        if getattr(getattr(fn, "value", None), "id", None) != "update_values":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Call) and getattr(
                arg.func, "id", None
            ) == "score_write_stamp_values_at_row":
                merged = True

    assert merged, (
        "the odds stamp is not merged into `update_values` — it must land in "
        "the same UPDATE as the score it describes"
    )


def test_the_odds_stamp_passes_the_scores_read_clock_not_a_fresh_now():
    """The clock of THIS sport's scores read — never `now()` per row, and never
    the pass-entry `now`, which predates every odds fetch in the pass.

    A per-row clock would stamp a slow pass's last event fresher than its first
    when both came off one provider payload; the pass-entry clock would date a
    read by when the pass began. Both encode our loop, not the provider read.
    """
    for call in _odds_stamp_calls():
        kwargs = {k.arg: k.value for k in call.keywords}
        assert "observed_at" in kwargs, "the site must name its clock"
        observed = kwargs["observed_at"]
        assert isinstance(observed, ast.Name), (
            "observed_at must be the pass clock bound above the loop, not an "
            f"expression like now() — got {ast.dump(observed)}"
        )
        assert observed.id == "_scores_read_at"

    src = (BACKEND / ODDS_SITE).read_text()
    fetch = src.index("scores_data = await service.get_scores(")
    bound = src.index("_scores_read_at = datetime.now(timezone.utc)")
    assert 0 < bound - fetch < 400, (
        "`_scores_read_at` must be taken as the scores fetch returns"
    )


def test_the_odds_stamp_is_handed_the_write_the_reading_and_the_skip():
    """The NO-SCORE / REFUSED-SCORE / HALF-SCORE control, at the site.

    The rule itself lives in `score_write_stamp_values_at_row` and is paid by
    value below and through the real pass in
    `test_odds_stamp_against_a_concurrent_score_4571_e2e.py`; what the site
    owes is the right inputs. The stamp dates the score TUPLE the row will hold,
    so the helper must see the very `update_values` the UPDATE sends, BOTH sides
    of the reading (a one-sided payload lands on the row's other half, which
    this read never confirmed), and `_skip_score_write` as the reason it may not
    confirm. Never gated on change: no `if` with a score `!=` may sit around it.

    And NO loaded pair (Sol a552 review). This UPDATE is by primary key only and
    re-asserts nothing it loaded, so `event_obj`'s scores can be another
    writer's commit out of date by the time it lands; a decision taken against
    them kept a 7-1 stamp on a 3-0 row. The `_at_row` helper asks the row in the
    same statement — handing the site back to the loaded-tuple helper, or giving
    it a `stored` pair, reopens the race.
    """
    calls = _odds_stamp_calls()
    assert len(calls) == 1, f"one stamp site expected, found {len(calls)}"
    assert getattr(calls[0].func, "id", None) == "score_write_stamp_values_at_row", (
        "the odds site's UPDATE is PK-only — its stamp must be decided against "
        "the row at the write, not the tuple it loaded"
    )
    kwargs = {k.arg: k.value for k in calls[0].keywords}

    assert "stored" not in kwargs
    assert ast.unparse(kwargs["writes"]) == "update_values", (
        "the helper must read the same dict the UPDATE sends, or it judges a "
        "write other than the one that lands"
    )
    assert ast.unparse(kwargs["reading"]) == "(home_score, away_score)"
    assert ast.unparse(kwargs["may_confirm"]) == "not _skip_score_write", (
        "a score a guard declined to store must not be confirmed"
    )


def test_a_refused_id_never_reaches_the_stamp():
    """The REFUSED-ID control.

    #1981's guard `continue`s on a STALE/UNVERIFIABLE/UNBOUND external_id before
    any `update_values` is built. A stamp written on that path would date a
    score we deliberately refused to write — attribution for a number that is
    not there.
    """
    src = (BACKEND / ODDS_SITE).read_text().splitlines()

    continue_line = next(
        i for i, line in enumerate(src)
        if line.strip() == "continue"
        and any("IdCurrency.CURRENT" in src[j] for j in range(max(0, i - 30), i))
    )
    stamp_line = min(
        call.lineno for call in _odds_stamp_calls()
    )
    assert continue_line < stamp_line, (
        "the stale-id refusal must short-circuit BEFORE the stamp; a refused "
        "write that still stamps dates a score it did not make"
    )


# ── The straggler settle door (#4652) also signs its reads ───────────────────
#
# #4652 landed on master while this branch waited for a merge slot, adding a
# SECOND writer into the same settle door: `_settle_authority_stragglers` ends
# a match the authority finished on a board day the ordinary pass never asks
# about. It called `update_event_fields_from_espn` without `observed_at`, and
# the stamp helper returns False on a None clock rather than raising — so that
# path wrote scores with no age, silently, on exactly the rows a reader is most
# likely to be looking at (a match that has just been settled).
#
# The AST guard above proves the keyword is TYPED at every call site. This one
# proves a real clock travels through the door and lands on the row.

def _straggler_harness():
    """The captured #4652 fixtures, reused rather than re-invented.

    Loaded by PATH, not by module name: `tests/` is not a package and is not on
    `sys.path` under every pytest rootdir, so a plain import passes here and
    ImportErrors in CI.
    """
    import importlib.util

    path = Path(__file__).with_name("test_authority_straggler_board_day_4652.py")
    spec = importlib.util.spec_from_file_location("_straggler_4652", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stamp_sent(stmt):
    """The stamp one UPDATE carries, as `{score_source, score_observed_at}`.

    Two spellings reach the wire: a changed tuple sends both columns as plain
    values, an unchanged one sends the forward-only `CASE` whose binds are
    `param_N`. Read both; `{}` when the statement carries no stamp.
    """
    compiled = stmt.compile()
    params = dict(compiled.params)
    if "score_observed_at" in params:
        return {k: params[k] for k in ("score_source", "score_observed_at")}
    if "score_observed_at=CASE" not in str(compiled).replace(" ", ""):
        return {}
    return {
        "score_source": next(
            v for v in params.values() if v in SCORE_OBSERVATION_SOURCES
        ),
        "score_observed_at": next(
            v for v in params.values() if isinstance(v, datetime)
        ),
    }


def _stamps_written(session):
    """Every stamp the settle door sent, one per UPDATE statement.

    Since #6056 the door writes live state as a conditional UPDATE, and the
    stamp rides that statement — so the fake session's statements, not the
    in-memory rows, are where a stamp is visible.
    """
    return [stamp for stamp in session.update_params if stamp]


async def _run_straggler(s, rows, **kw):
    session = s._FakeSession(rows)
    session.update_params = []
    real_execute = session.execute

    async def _execute(stmt, *args, **kwargs):
        if not str(stmt).lstrip().upper().startswith("SELECT"):
            session.update_params.append(_stamp_sent(stmt))
        return await real_execute(stmt, *args, **kwargs)

    session.execute = _execute
    espn = s._FakeESPN(s.BOARD_0909, dark=kw.pop("dark", False))
    stats = {"authority_dark_sports": 0, "errors": []}
    await s._settle_authority_stragglers(
        session, espn, kw.pop("now", s.NOW), stats, s.update_event_fields_from_espn
    )
    return session


@pytest.mark.asyncio
async def test_a_straggler_settled_off_a_prior_day_board_carries_a_stamp():
    s = _straggler_harness()
    rows = s._suspended_specimens()

    session = await _run_straggler(s, rows)

    assert [e.status for e in rows] == ["completed", "completed"], (
        "precondition: #4652's pass must still settle these two rows"
    )
    stamps = _stamps_written(session)
    assert len(stamps) == len(rows), (
        f"{len(rows)} rows settled off the prior-day board but {len(stamps)} "
        "carried an observation stamp — the page would print a corrected score "
        "whose age is unknown (#4571 + #4652)"
    )
    for params in stamps:
        assert params["score_source"] == "espn"


@pytest.mark.asyncio
async def test_the_straggler_stamp_is_the_board_read_not_the_pass_clock():
    """Each group is its own fetch, so each carries its own read moment.

    `now` is the pass's entry clock and can be arbitrarily older than the
    board request that actually produced these scores; stamping with it would
    report the score as older than it is.
    """
    s = _straggler_harness()
    rows = s._suspended_specimens()

    session = await _run_straggler(s, rows, now=s.NOW)

    stamps = _stamps_written(session)
    assert stamps
    for params in stamps:
        assert params["score_observed_at"] != s.NOW, (
            "the straggler stamp reused the pass-entry clock instead of the "
            "moment its own board was read"
        )
        assert params["score_observed_at"].tzinfo is not None, "stamp must be aware"


@pytest.mark.asyncio
async def test_an_authority_dark_straggler_board_stamps_nothing():
    """No board, no read, no age. An absence must not be dated (#3473)."""
    s = _straggler_harness()
    rows = s._suspended_specimens()

    session = await _run_straggler(s, rows, dark=True)

    assert _stamps_written(session) == [], (
        "a dark board settled nothing, so it must not have stamped a score"
    )


# ══ SOL 9ec2 FINDINGS — A STAMP DATES THE WHOLE TUPLE THE ROW HOLDS ══════════
#
# Finding 1: each side of a reading lands independently, and only a reading with
# both sides confirmed — so ESPN reading (7, None) against a stored (3, 0) wrote
# home 7 and left StatPal's stamp, taken for (3, 0), dating (7, 0). Same for a
# whole changed score with no clock. A write that moves the tuple without
# confirming it now CLEARS the stamp in the same statement.
#
# Finding 2: the "never backwards" rule was checked against the LOADED row, and
# no compare-and-write predicate reads the stamp — so two confirmations of one
# tuple that load in one order and commit in the other regressed it. An
# unchanged confirmation is now a forward-only CASE the database decides.

from sqlalchemy.sql.elements import ClauseElement  # noqa: E402

from app.utils.score_observation import (  # noqa: E402
    SCORE_STAMP_CLEARED,
    score_write_stamp_values,
    score_write_stamp_values_at_row,
)

T_HELD = NOW - timedelta(seconds=60)


def _decide(stored, writes, reading, *, observed_at=NOW, may_confirm=True):
    return score_write_stamp_values(
        source="espn", observed_at=observed_at, stored=stored,
        writes=writes, reading=reading, may_confirm=may_confirm,
    )


def test_a_half_reading_that_moves_the_score_clears_the_stamp():
    assert _decide((3, 0), {"home_score": 7}, (7, None)) == SCORE_STAMP_CLEARED


def test_a_half_reading_onto_a_blank_row_is_not_a_tuple_anyone_read():
    """The row ends (7, None), which equals the reading — but half a score is
    not a confirmation of anything."""
    assert _decide((None, None), {"home_score": 7}, (7, None)) == SCORE_STAMP_CLEARED


def test_a_changed_score_with_no_clock_clears_the_stamp():
    assert _decide(
        (3, 0), {"home_score": 7}, (7, 0), observed_at=None,
    ) == SCORE_STAMP_CLEARED


def test_a_changed_confirmed_score_takes_this_readings_clock():
    assert _decide((3, 0), {"home_score": 7}, (7, 0)) == {
        "score_source": "espn", "score_observed_at": NOW,
    }


def test_a_half_reading_that_moves_nothing_keeps_the_stamp():
    assert _decide((3, 0), {}, (3, None)) == {}


def test_a_refused_reading_of_the_stored_tuple_confirms_nothing():
    """A reading its writer refused (stale, withheld pre-game, stoppage filler)
    must not date the row even when it happens to equal it."""
    assert _decide((0, 0), {}, (0, 0), may_confirm=False) == {}


def test_a_refused_reading_of_a_different_tuple_confirms_nothing():
    """UX term 1: incoming 4-5 refused, stored 6-5 stays — 6-5 must not look
    freshly confirmed."""
    assert _decide((6, 5), {}, (4, 5), may_confirm=False) == {}


def test_an_unchanged_confirmation_is_decided_by_the_database():
    values = _decide((28, 20), {"home_score": 28, "away_score": 20}, (28, 20))
    assert set(values) == {"score_source", "score_observed_at"}
    assert all(isinstance(v, ClauseElement) for v in values.values()), (
        "an unchanged confirmation sent a plain value: an older read that "
        "commits after a newer one would re-date the score backwards"
    )


def _core_row(*, home, away, source=None, observed_at=None):
    """One real sqlite `events` row, for the Core UPDATE the odds site sends."""
    from sqlalchemy import create_engine

    _load_6056_rails()  # sqlite compilers for JSONB / ARRAY
    from app.models.models import Base, Event, Sport

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Event.__table__, Sport.__table__])
    with engine.begin() as conn:
        sport_id = conn.execute(
            Sport.__table__.insert().values(key="americanfootball_nfl", name="NFL")
        ).inserted_primary_key[0]
        event_id = conn.execute(Event.__table__.insert().values(
            sport_id=sport_id, home_team_name="H", away_team_name="A",
            commence_time=NOW - timedelta(hours=1), status="live",
            home_score=home, away_score=away, win_probability_sources={},
            score_source=source, score_observed_at=observed_at,
        )).inserted_primary_key[0]
    return engine, event_id


def _core_write(engine, event_id, values):
    from sqlalchemy import select

    from app.models.models import Event

    with engine.begin() as conn:
        conn.execute(
            Event.__table__.update().where(Event.id == event_id).values(**values)
        )
        row = conn.execute(
            select(Event.home_score, Event.away_score, Event.score_source,
                   Event.score_observed_at).where(Event.id == event_id)
        ).one()
    return row[0], row[1], row[2], _aware(row[3])


def _odds_values(writes, reading, *, observed_at=NOW, may_confirm=True):
    """What the odds site merges into its PK-only UPDATE — the row-relative
    helper it actually calls, with no loaded pair."""
    values = dict(writes)
    values.update(score_write_stamp_values_at_row(
        source=SCORE_SOURCE_ODDS, observed_at=observed_at,
        writes=values, reading=reading, may_confirm=may_confirm,
    ))
    return values


def test_odds_shaped_one_sided_payload_clears_the_old_stamp_on_a_real_row():
    engine, event_id = _core_row(home=3, away=0, source="statpal", observed_at=T_HELD)
    values = _odds_values({"home_score": 7}, (7, None))
    assert _core_write(engine, event_id, values) == (7, 0, None, None)


@pytest.mark.parametrize(
    "held_source, held_at, expected",
    [
        (None, None, ("odds_api", NOW)),                       # first confirmation
        ("statpal", T_HELD, ("odds_api", NOW)),                # older stamp advances
        ("statpal", NOW + timedelta(seconds=30),               # newer stamp stands
         ("statpal", NOW + timedelta(seconds=30))),
    ],
)
def test_the_forward_only_confirmation_on_a_real_row(held_source, held_at, expected):
    engine, event_id = _core_row(home=0, away=0, source=held_source, observed_at=held_at)
    values = _odds_values({"home_score": 0, "away_score": 0}, (0, 0))
    assert _core_write(engine, event_id, values) == (0, 0, *expected)


# ── Sol a552: the PK-only write is judged against the row AT the write ───────
#
# Each case is (row at the write, Odds writes, Odds reading) → row after. The
# row at the write is what another writer committed after Odds loaded; Odds'
# own loaded pair is deliberately not an input — the helper takes none.

T_OTHER = NOW + timedelta(seconds=30)


@pytest.mark.parametrize(
    "row_at_write, writes, reading, observed_at, expected",
    [
        # Sol arm 1: full 3-0 lands on a concurrent 7-1@T2 → Odds' read dates 3-0.
        ((7, 1), {"home_score": 3, "away_score": 0}, (3, 0), NOW,
         (3, 0, "odds_api", NOW)),
        # Sol arm 2: half (3, None) lands on 7-1 → 3-1, which nobody read whole.
        ((7, 1), {"home_score": 3}, (3, None), NOW, (3, 1, None, None)),
        # Only the AWAY side lands on a moved row → still a fresh tuple, cleared.
        ((7, 1), {"away_score": 0}, (None, 0), NOW, (7, 0, None, None)),
        # Half reading that the moved row happens to agree with → held kept.
        ((3, 1), {"home_score": 3}, (3, None), NOW, (3, 1, "statpal", T_OTHER)),
        # Changed whole score with no clock over a moved row → cleared.
        ((7, 1), {"home_score": 3, "away_score": 0}, (3, 0), None,
         (3, 0, None, None)),
    ],
)
def test_the_pk_only_write_is_judged_against_the_row_at_the_write(
    row_at_write, writes, reading, observed_at, expected,
):
    engine, event_id = _core_row(
        home=row_at_write[0], away=row_at_write[1],
        source="statpal", observed_at=T_OTHER,
    )
    values = _odds_values(writes, reading, observed_at=observed_at)
    assert _core_write(engine, event_id, values) == expected


def test_a_refused_odds_reading_sends_no_stamp_whatever_the_row_holds():
    """`_skip_score_write` strips the score from `update_values`, so nothing
    the statement does can move the tuple — and nothing may date it."""
    assert _odds_values({}, (3, 0), may_confirm=False) == {}
    assert _odds_values({}, (3, None), may_confirm=False) == {}


def test_a_written_side_the_reading_does_not_hold_never_confirms():
    """Defensive: `writes` and `reading` disagreeing is a caller bug, and it
    must read as "not confirmed", never as a stamp for a number not read."""
    engine, event_id = _core_row(home=3, away=0, source="statpal", observed_at=T_HELD)
    values = _odds_values({"home_score": 9, "away_score": 0}, (3, 0))
    assert _core_write(engine, event_id, values) == (9, 0, None, None)


# ── the same rules through the REAL ESPN writer ──────────────────────────────


@pytest.mark.asyncio
async def test_espn_half_reading_that_moves_the_score_clears_an_old_stamp():
    """Sol's specimen: stored (3,0) stamped StatPal@T0; ESPN reads (7, None)."""
    row, _stats, changed = await _espn_writes(
        row_home=3, row_away=0, board=_Board(home_score=7, away_score=None),
        observed_at=NOW, held_stamp=T_HELD,
    )
    assert (row.home_score, row.away_score) == (7, 0)
    assert (row.score_source, row.score_observed_at) == (None, None), (
        "StatPal's stamp for (3, 0) survived onto (7, 0), a tuple nobody "
        "read whole"
    )
    assert changed is True


@pytest.mark.asyncio
async def test_espn_half_reading_that_moves_nothing_keeps_the_stamp():
    row, _stats, _changed = await _espn_writes(
        row_home=3, row_away=0, board=_Board(home_score=3, away_score=None),
        observed_at=NOW, held_stamp=T_HELD,
    )
    assert (row.score_source, _aware(row.score_observed_at)) == ("statpal", T_HELD)


@pytest.mark.asyncio
async def test_espn_changed_score_without_a_clock_clears_an_old_stamp():
    row, _stats, _changed = await _espn_writes(
        row_home=3, row_away=0, board=_Board(home_score=7, away_score=0),
        observed_at=None, held_stamp=T_HELD,
    )
    assert (row.home_score, row.away_score) == (7, 0)
    assert (row.score_source, row.score_observed_at) == (None, None)


@pytest.mark.asyncio
async def test_espn_refused_reversion_leaves_a_held_stamp_exactly_as_it_was():
    """UX term 1, by value: incoming 28-14 refused as earlier in the game; the
    stored 28-20 keeps its stamp — not bumped, not cleared."""
    row, stats, _changed = await _espn_writes(
        row_home=28, row_away=20,
        board=_Board(home_score=28, away_score=14, clock="5:26",
                     status_detail="5:26 - 4th Quarter"),
        observed_at=NOW, held_stamp=T_HELD,
    )
    assert stats["live_state_reversions_refused"] == 1
    assert (row.home_score, row.away_score) == (28, 20)
    assert (row.score_source, _aware(row.score_observed_at)) == ("statpal", T_HELD)


def _confirms_same_tuple_at(at):
    """Another writer, in its own session, confirming the SAME tuple at the
    SAME position with a NEWER read — committed inside our decision window, so
    every compare-and-write predicate still matches when we write."""

    def _run(engine, event_id):
        from sqlalchemy import update
        from sqlalchemy.orm import Session

        from app.models.models import Event

        other = Session(engine)
        try:
            other.execute(
                update(Event).where(Event.id == event_id)
                .values(score_source="statpal", score_observed_at=at)
            )
            other.commit()
        finally:
            other.close()

    return _run


@pytest.mark.asyncio
async def test_an_older_confirmation_committing_after_a_newer_one_keeps_the_newer(
    monkeypatch,
):
    """Finding 2's interleaving: both load an unstamped 0-0; StatPal@T+30
    commits first; ESPN@T commits after. The stamp must stay T+30."""
    later = NOW + timedelta(seconds=30)
    row, stats, changed = await _espn_writes(
        row_home=0, row_away=0, board=_Board(home_score=0, away_score=0),
        observed_at=NOW, interloper=_confirms_same_tuple_at(later),
        monkeypatch=monkeypatch,
    )
    assert (row.score_source, _aware(row.score_observed_at)) == ("statpal", later), (
        "an older same-tuple confirmation re-dated the score backwards"
    )
    assert stats.get("score_confirmation_lost_race", 0) == 0
    assert changed is False


@pytest.mark.asyncio
async def test_the_forward_only_stamp_never_blocks_the_position_it_rides_with(
    monkeypatch,
):
    """Same interleaving, but ESPN's read also moves the clock on: the clock
    must land while the newer stamp stands."""
    later = NOW + timedelta(seconds=30)
    row, stats, changed = await _espn_writes(
        row_home=0, row_away=0,
        board=_Board(home_score=0, away_score=0, clock="5:10",
                     status_detail="5:10 - 4th Quarter"),
        observed_at=NOW, interloper=_confirms_same_tuple_at(later),
        monkeypatch=monkeypatch,
    )
    assert row.game_clock == "5:10" and changed is True
    assert stats.get("live_state_write_lost_race", 0) == 0
    assert (row.score_source, _aware(row.score_observed_at)) == ("statpal", later)


# ── every compare-and-write site hands the helper the write it actually sends ─


def _norm(expr):
    return ast.unparse(ast.parse(expr, mode="eval").body)


_CAS_STAMP_SITES = {
    # site → (stored, writes, reading, may_confirm)
    "app/utils/espn_helpers.py": [(
        "(_observed_home_score, _observed_away_score)", "_live_values",
        "(ee.home_score, ee.away_score)",
        "not _live_state_is_stale and not _withhold_live_state"
        " and not _stoppage_scores_are_filler",
    )],
    "app/tasks/statpal_sync.py": [
        ("(_observed_home_score, _observed_away_score)", "_new_scores",
         "(live_data.home_score, live_data.away_score)", "True"),
        ("(_observed_home_score, _observed_away_score)", "_live_values",
         "(fixture.home_score, fixture.away_score)", "not live_state_is_stale"),
    ],
    "app/tasks/espn_sync.py": [(
        "(_observed_home, _observed_away)", "score['changes']",
        "(score['changes'].get('home_score', _observed_home), "
        "score['changes'].get('away_score', _observed_away))",
        "True",
    )],
}


@pytest.mark.parametrize("relpath", sorted(_CAS_STAMP_SITES))
def test_every_cas_site_hands_the_helper_its_stored_pair_and_its_own_write(relpath):
    """The helper judges the tuple the row will hold from `stored` + `writes`.
    Hand it a different dict than the one the compare-and-write sends, or a
    stored pair other than the one the predicate re-asserts, and it judges a
    write that never happens. `may_confirm` carries the writer's own refusals;
    dropping one there lets a refused reading date the row."""
    found = []
    for node in ast.walk(_module_tree(relpath)):
        if isinstance(node, ast.Call) and getattr(
            node.func, "id", None
        ) == "score_write_stamp_values":
            kw = {k.arg: ast.unparse(k.value) for k in node.keywords}
            found.append(tuple(
                kw[k] for k in ("stored", "writes", "reading", "may_confirm")
            ))
    expected = [tuple(_norm(e) for e in site) for site in _CAS_STAMP_SITES[relpath]]
    assert sorted(found) == sorted(expected)
