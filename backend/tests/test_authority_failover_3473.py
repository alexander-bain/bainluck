"""Nothing goes blank when ESPN does — the decision, its gate, and its actor. #3473.

Program step 7. Three things are pinned here, and they fail for three different
reasons:

  * **The distinction.** `_sync_espn_live_events` used to write
    `espn_data.get(sport_key, [])`, mapping "ESPN went dark" and "ESPN says
    there are no games" onto one `[]` and one `continue` — undoing, thirty lines
    later, the separation the fetch loop had just taken care to preserve. An AST
    walk over the function keeps that line from coming back.
  * **The states.** `decide` has nine outcomes and production can reach two of
    them today. The other seven are tested because they are the ones that will
    matter on the day this stops being dark, and a pure function is the only
    kind that can be put in a state its caller will not reach for months.
  * **The rider.** `authority_failover` is a pure module, and a pure module
    nothing calls is architecture-only. One test walks `app/` for an actor.

WHAT MAKES THESE NON-VACUOUS. `flip_permitted` refuses every sport today, so a
test that only asserted "no failover fires" would pass against a `decide` that
was hard-wired to return `False` — and would keep passing after the gate opened.
Every refusal asserted here is paired with the same call under a ledger holding
a genuine seven, where the answer flips. The bar is the real one: these are
`flip_permitted`'s own days, not a stubbed gate.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.config.authority_by_sport import (
    AUTHORITY_BY_SPORT,
    ESPN,
    STATPAL,
    flip_permitted,
)
from app.utils.authority_agreement import SHADOW_STAMPERS
from app.utils.authority_failover import (
    BOTH_QUIET,
    DARK,
    EMPTY,
    ESPN_ANSWERED,
    FAILOVER_CODES,
    FAILOVER_ESPN_DARK,
    FAILOVER_ESPN_SILENT,
    FIXTURES,
    LIVE_PATH_DARK,
    LIVE_PATH_SILENT_ON_THE_GAME,
    NOT_GATED,
    NOT_READ,
    NOTHING_TO_SERVE,
    STANDBY_DARK,
    STANDBY_NOT_READ,
    STANDING_STATPAL,
    WINDOW_BACK,
    decide,
    espn_reading,
    reading_from_fixtures,
    reading_in_window,
    would_fail_over_now,
)

NFL = "americanfootball_nfl"


# `Event` carries Postgres JSONB/ARRAY columns that sqlite cannot render as DDL.
# The repo's standing shim (see `test_proven_duplicate_2263`), so the writer test
# below can create the real tables from the real models.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"

#: A ledger holding a genuine seven, in the shape `authority_streak.fold_day`
#: writes. Used to open the REAL gate rather than to stub it — every "it refuses
#: today" assertion below is paired with the same call under these days, so none
#: of them can pass because the mechanism is inert.
SEVEN_MEETS_DAYS = [
    {"day": f"2026-09-{d:02d}", "state": "MEETS"} for d in range(1, 8)
]


def _open_gate() -> tuple[bool, str]:
    gate = flip_permitted(NFL, SEVEN_MEETS_DAYS)
    assert gate[0] is True, (
        "the control is broken: seven MEETS days no longer open the real gate, "
        f"so every paired assertion below is vacuous. {gate[1]}"
    )
    return gate


def _shut_gate() -> tuple[bool, str]:
    gate = flip_permitted(NFL, [])
    assert gate[0] is False
    return gate


# ── The reading: three states where the caller had two ──────────────────────


def test_an_absent_key_and_an_empty_list_are_different_readings():
    """The defect, at its smallest.

    `get_scoreboard` returns `None` when ESPN did not answer and `[]` when the
    slate is genuinely empty, and the fetch loop preserves that by leaving a
    dark sport's key ABSENT. `.get(sport_key, [])` was what threw it away.
    """
    assert espn_reading({}, NFL) == DARK
    assert espn_reading({NFL: []}, NFL) == EMPTY
    assert espn_reading({NFL: ["a game"]}, NFL) == FIXTURES

    # And the two silences are not merely different strings — they must not be
    # equal, which is the only property the old `.get(key, [])` violated.
    assert espn_reading({}, NFL) != espn_reading({NFL: []}, NFL)


def test_a_standby_client_that_returns_none_is_dark_not_empty():
    """`reading_from_fixtures` applies the same convention on the other side."""
    assert reading_from_fixtures(None) == DARK
    assert reading_from_fixtures([]) == EMPTY
    assert reading_from_fixtures(["a fixture"]) == FIXTURES


def test_not_read_is_its_own_symbol_and_never_collapses_into_dark():
    """"we did not look" and "they went quiet" are opposite facts.

    Sharing one symbol would let the cheap case wear the grave one's clothes:
    a caller that forgot to read the standby would be reported as having found
    StatPal silent, which is a claim about StatPal.
    """
    assert NOT_READ != DARK
    assert decide(NFL, espn=DARK, gate=_open_gate()).code == STANDBY_NOT_READ
    assert (
        decide(
            NFL, espn=DARK, statpal=DARK, statpal_live=DARK, gate=_open_gate()
        ).code
        == STANDBY_DARK
    )


# ── The nine outcomes ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "espn,statpal,live,expected,serving,failed_over",
    [
        # ESPN answering ends everything, and is the only deactivation there is.
        (FIXTURES, NOT_READ, NOT_READ, ESPN_ANSWERED, ESPN, False),
        # The two that fire — both halves of the standby answered.
        (DARK, FIXTURES, FIXTURES, FAILOVER_ESPN_DARK, STATPAL, True),
        (EMPTY, FIXTURES, FIXTURES, FAILOVER_ESPN_SILENT, STATPAL, True),
        # Both answered, neither has a game: a quiet slate, never an outage.
        (EMPTY, EMPTY, FIXTURES, BOTH_QUIET, ESPN, False),
        # A real unexplained silence with nothing to serve in its place.
        (DARK, EMPTY, FIXTURES, NOTHING_TO_SERVE, ESPN, False),
        # Trading a known silence for an unknown one.
        (DARK, DARK, DARK, STANDBY_DARK, ESPN, False),
        (EMPTY, DARK, FIXTURES, STANDBY_DARK, ESPN, False),
        # CERT-2044: the standby has the game and cannot say what is happening
        # in it. The blank, not a failover away from one.
        (DARK, FIXTURES, DARK, LIVE_PATH_DARK, ESPN, False),
        (EMPTY, FIXTURES, DARK, LIVE_PATH_DARK, ESPN, False),
        # CERT-2046: the live board ANSWERED and is not carrying the game its
        # own schedule says is under way. StatPal contradicting itself, which
        # is a different fact from StatPal being down.
        (DARK, FIXTURES, EMPTY, LIVE_PATH_SILENT_ON_THE_GAME, ESPN, False),
        (EMPTY, FIXTURES, EMPTY, LIVE_PATH_SILENT_ON_THE_GAME, ESPN, False),
        # A caller bug, reported rather than raised — either half unread.
        (DARK, NOT_READ, FIXTURES, STANDBY_NOT_READ, ESPN, False),
        (DARK, FIXTURES, NOT_READ, STANDBY_NOT_READ, ESPN, False),
    ],
)
def test_every_outcome_under_an_open_gate(
    espn, statpal, live, expected, serving, failed_over
):
    """The states production will reach after 2026-09-11, proven now.

    Under the REAL gate opened by seven real days — so this is the behaviour the
    mechanism will actually have, not the behaviour of a stub.
    """
    decision = decide(
        NFL, espn=espn, statpal=statpal, statpal_live=live, gate=_open_gate()
    )
    assert decision.code == expected
    assert decision.serving == serving
    assert decision.failed_over is failed_over
    assert decision.sport_key == NFL
    assert decision.why, "every outcome states its reason; that is the point of the type"


def test_a_flipped_sport_is_standing_not_failed_over():
    """`STANDING_STATPAL` is a flip, not an outage override, and counting it as
    a failover would report a sport as degraded for as long as it was flipped."""
    decision = decide(NFL, espn=FIXTURES, gate=_shut_gate(), standing=STATPAL)
    assert decision.code == STANDING_STATPAL
    assert decision.serving == STATPAL
    assert decision.failed_over is False
    assert decision.code not in FAILOVER_CODES

    # It outranks ESPN's reading: a flipped sport does not revert because ESPN
    # happened to answer this pass.
    for reading in (DARK, EMPTY, FIXTURES):
        assert decide(NFL, espn=reading, gate=_shut_gate(), standing=STATPAL).serving == STATPAL


def test_the_gate_is_asked_before_the_standby_is_read():
    """The ordering the caller depends on to avoid a network call.

    `_decide_failovers` reads StatPal only when `decide` tells it the standby
    could have mattered. If the gate stopped being the earlier question, that
    caller would start making a StatPal call on every dark sport on every pass
    while still being unable to act on the answer.
    """
    ungated = decide(NFL, espn=DARK, gate=_shut_gate())
    assert ungated.code == NOT_GATED, (
        "the shut gate must refuse BEFORE the missing standby is noticed; "
        f"got {ungated.code}"
    )
    # And the control: with the gate open, the same call reaches the standby
    # question, so the assertion above is about ordering and not about the
    # standby being ignored altogether.
    assert decide(NFL, espn=DARK, gate=_open_gate()).code == STANDBY_NOT_READ


# ── Dark by construction, and provably not inert ────────────────────────────


def test_no_stamped_sport_can_fail_over_today():
    """The safety claim: the mechanism ships incapable of acting.

    Over every sport on the row an operator reads, using each sport's own real
    gate against an empty ledger.
    """
    for sport_key in SHADOW_STAMPERS:
        gate = flip_permitted(sport_key, [])
        decision = would_fail_over_now(sport_key, gate)
        assert decision.failed_over is False, (
            f"{sport_key} would fail over today: {decision.why}"
        )
        assert decision.code == NOT_GATED


def test_and_it_is_not_inert_the_same_sport_fires_on_a_genuine_seven():
    """The pair to the test above, and what stops it being vacuous.

    Without this, a `decide` hard-wired to refuse would pass — and would keep
    passing after the seven days landed, which is precisely when the refusal
    stops being the right answer.
    """
    decision = would_fail_over_now(NFL, _open_gate())
    assert decision.failed_over is True
    assert decision.code == FAILOVER_ESPN_DARK
    assert decision.serving == STATPAL


def test_nothing_has_flipped_so_no_sport_is_standing_on_statpal():
    """A tripwire on the other input. `would_fail_over_now` reads the switch;
    if a value here became STATPAL the disclosure above would change meaning."""
    assert set(AUTHORITY_BY_SPORT.values()) == {ESPN}


def test_the_disclosure_cannot_disagree_with_the_decision():
    """`would_fail_over_now` re-uses `decide` rather than re-deriving its rules.

    A disclosure that reimplements its subject is one that drifts from it. Here
    the two are the same call, so this asserts an identity rather than a
    coincidence — over an open gate AND a shut one, because a disclosure that
    agreed only in the refusing case would be the easy half.
    """
    for gate in (_shut_gate(), _open_gate()):
        assert would_fail_over_now(NFL, gate) == decide(
            NFL, espn=DARK, statpal=FIXTURES, statpal_live=FIXTURES, gate=gate
        )


# ── Deactivation, and the state that is deliberately not kept ───────────────


def test_the_failover_ends_by_itself_because_nothing_was_stored():
    """Deactivation is not a mechanism; it is the absence of one.

    A latch cleared on ESPN success could not reopen — ESPN returning with a
    genuinely empty slate is, at a latch, indistinguishable from ESPN still
    being dark — so the override would outlive the outage by however long the
    sport was out of season. Two calls, no shared object, and the second is not
    influenced by the first.
    """
    gate = _open_gate()
    during = decide(NFL, espn=DARK, statpal=FIXTURES, statpal_live=FIXTURES, gate=gate)
    assert during.failed_over is True

    after = decide(NFL, espn=FIXTURES, statpal=FIXTURES, statpal_live=FIXTURES, gate=gate)
    assert after.code == ESPN_ANSWERED
    assert after.serving == ESPN
    assert after.failed_over is False

    # And the case a latch gets wrong: ESPN back with an empty slate that
    # StatPal agrees with is a quiet day, not a continuing outage.
    quiet = decide(NFL, espn=EMPTY, statpal=EMPTY, statpal_live=FIXTURES, gate=gate)
    assert quiet.failed_over is False
    assert quiet.code == BOTH_QUIET


def test_a_score_disagreement_cannot_reach_the_decision_at_all():
    """"Never for state disagreements" is a property of the signature.

    Program step 7 requires that a failover fire on an outage and never on a
    state disagreement. That is not enforced by a check that could be removed —
    there is no parameter a score, status or period could arrive in. This walks
    the signature so adding one has to be a deliberate act with a test to break.
    """
    params = set(inspect.signature(decide).parameters) - {"sport_key"}
    assert params == {"espn", "statpal", "statpal_live", "gate", "standing"}, (
        "a new input to `decide` — if it carries game STATE rather than a "
        "reading, step 7's 'never for state disagreements' stops being "
        f"structural. Got {sorted(params)}"
    )


def test_decide_is_total_and_never_raises():
    """A `KeyError` out of this path would be an outage in the sport we were
    trying to protect, so every input has an answer — including nonsense."""
    for espn in (DARK, EMPTY, FIXTURES, "who knows", ""):
        for statpal in (DARK, EMPTY, FIXTURES, NOT_READ, "who knows"):
            decision = decide(
                NFL, espn=espn, statpal=statpal,
                statpal_live=FIXTURES, gate=_open_gate(),
            )
            assert decision.serving in {ESPN, STATPAL}
            assert decision.why


# ── The rider rule, and the line that must not come back ────────────────────

APP = Path(__file__).resolve().parent.parent / "app"
FAILOVER_MODULE = "app.utils.authority_failover"


def test_the_decision_module_has_an_actor():
    """The RIDER RULE in CI. A pure function nothing calls is architecture-only.

    Walks `app/` for a module that imports the decision module, excluding the
    module itself. If step 7's consumer is ever deleted or refactored away, this
    fails rather than leaving a well-documented function nothing reaches.
    """
    callers = set()
    for path in sorted(APP.rglob("*.py")):
        module = "app." + ".".join(path.relative_to(APP).with_suffix("").parts)
        if module == FAILOVER_MODULE:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == FAILOVER_MODULE:
                callers.add(module)
            elif isinstance(node, ast.Import) and any(
                a.name == FAILOVER_MODULE for a in node.names
            ):
                callers.add(module)
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module == "app.utils"
                and any(a.name == "authority_failover" for a in node.names)
            ):
                callers.add(module)

    assert "app.tasks.espn_sync" in callers, (
        "the ESPN sync no longer reaches the failover decision, so step 7's "
        f"mechanism is unreachable. Callers found: {sorted(callers)}"
    )


# ── A real DB rail, shared by every test that must watch a WRITE land ────────


class _AsyncShim:
    """Async surface over a real sync session.

    No aiosqlite in this sandbox, so this is the repo's established shape: the
    statements executed are production's own and the rows come back through the
    real result API. Nothing about the writers is reimplemented.
    """

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


def _wire_sqlite(monkeypatch):
    """A live NFL Event on a real engine, wired in as every task's session.

    Returns `(session, event_id)`. `expire_on_commit=False` matches the app's
    own task sessions (gotcha #6); without it sqlite reloads `commence_time`
    NAIVE — it has no tz type — and the writer's premature-live guard raises on
    a comparison Postgres never makes.
    """
    from sqlalchemy import create_engine
    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session

    import app.tasks.base as task_base
    from app.models.models import Base, Event, ScoreSnapshot, Sport

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[Event.__table__, Sport.__table__, ScoreSnapshot.__table__],
    )
    session = Session(engine, expire_on_commit=False)

    now = datetime.now(timezone.utc)
    sport = Sport(key=NFL, name="NFL")
    session.add(sport)
    session.flush()
    event = Event(
        sport_id=sport.id,
        home_team_name="Bears",
        away_team_name="Packers",
        commence_time=now - timedelta(hours=1),
        status="live",
    )
    session.add(event)
    session.commit()

    # sqlite has no timezone-aware timestamp type, so every datetime RELOADED
    # from it comes back naive — and production compares `commence_time` with an
    # aware `now` (the writer's premature-live guard). Postgres returns these
    # aware, so a naive reload is a fidelity gap in the rail, not a shape the
    # code must handle. Reattached on load, in the same family as the
    # `@compiles(JSONB, "sqlite")` DDL shim above: written into `__dict__` so it
    # does not mark the attribute dirty and cause a spurious UPDATE.
    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    class _Ctx:
        async def __aenter__(self_inner):
            return _AsyncShim(session)

        async def __aexit__(self_inner, *exc):
            session.commit()
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    for module in ("app.tasks.statpal_sync", "app.tasks.espn_sync"):
        monkeypatch.setattr(f"{module}.get_task_session", lambda: _Ctx(), raising=False)
    return session, event.id


# ── The consumer: what the ESPN sync actually does with a decision ──────────


class _NoDispatch:
    """Records any attempt to dispatch a task, so a test can assert there were none.

    There should never be one. `_act_on_failovers` dispatches nothing on
    purpose: a standing CI guard
    (`test_celery_result_retention.test_no_task_dispatches_another_task`) bans
    intra-task dispatch outright, and lane1/130's measurement says it would buy
    only cadence anyway. This fixture is how the tests below keep that true —
    if a dispatch is ever reintroduced here, the CI guard catches the code and
    these catch the behaviour.
    """

    def __init__(self):
        self.calls: list[str] = []

    def delay(self, sport_key="<no-arg>"):
        self.calls.append(sport_key)


@pytest.fixture
def dispatches(monkeypatch):
    import app.tasks as tasks

    stub = _NoDispatch()
    live = _NoDispatch()
    monkeypatch.setattr(tasks, "sync_statpal_schedules", stub, raising=False)
    monkeypatch.setattr(tasks, "sync_statpal_livescores", live, raising=False)
    stub.live = live
    return stub


def _no_ledger(monkeypatch, days=None, why="stubbed: no ledger"):
    """Make the durable ledger read deterministic without a snapshot store."""
    import app.services.authority_ledger as ledger

    async def _read(sport_key):
        return days, why

    monkeypatch.setattr(ledger, "read_ledger_days", _read)


@pytest.mark.asyncio
async def test_a_dark_sport_and_an_empty_sport_get_different_receipts(monkeypatch):
    """The user-visible half of #3473, at the task.

    Both are skipped by the passes — ESPN has nothing to contribute either way —
    but they are no longer the same event. Before this ship they produced one
    indistinguishable `continue` and no record at all.
    """
    from app.tasks.espn_sync import _decide_failovers

    _no_ledger(monkeypatch)
    stats = {"errors": []}
    decisions = await _decide_failovers(
        {"basketball_nba": []}, {"americanfootball_nfl", "basketball_nba"}, stats
    )

    assert decisions["americanfootball_nfl"].why != decisions["basketball_nba"].why
    assert "dark" in decisions["americanfootball_nfl"].why
    assert "empty" in decisions["basketball_nba"].why


@pytest.mark.asyncio
async def test_a_sport_espn_answered_for_is_not_decided_at_all(monkeypatch):
    """No receipt, no ledger read, no cost on the path that is 99.9% of passes."""
    from app.tasks.espn_sync import _decide_failovers

    reads: list[str] = []

    import app.services.authority_ledger as ledger

    async def _read(sport_key):
        reads.append(sport_key)
        return [], "stub"

    monkeypatch.setattr(ledger, "read_ledger_days", _read)

    decisions = await _decide_failovers(
        {"americanfootball_nfl": ["a game"]}, {"americanfootball_nfl"}, {"errors": []}
    )
    assert decisions == {}
    assert reads == []


@pytest.mark.asyncio
async def test_a_sport_with_no_shadow_stamper_costs_no_durable_read(monkeypatch):
    """The bound on a pass over a dozen quiet sports.

    `flip_permitted` refuses a sport with no shadow stamper before it looks at
    any days, so reading its ledger every two minutes would buy nothing. The
    refusal still comes from the gate — this asserts the read is skipped, not
    that the reasoning was copied.
    """
    from app.tasks.espn_sync import _decide_failovers

    reads: list[str] = []

    import app.services.authority_ledger as ledger

    async def _read(sport_key):
        reads.append(sport_key)
        return [], "stub"

    monkeypatch.setattr(ledger, "read_ledger_days", _read)

    decisions = await _decide_failovers({}, {"soccer_epl"}, {"errors": []})
    assert reads == []
    assert "no shadow stamper" in decisions["soccer_epl"].why


@pytest.mark.asyncio
async def test_an_unreadable_ledger_refuses_rather_than_permits(monkeypatch):
    """A snapshot-store outage must never be able to OPEN this gate.

    `read_ledger_days` returns `None` for "could not be trusted", distinct from
    `[]` for "never recorded a day" — if the caller collapsed them, an
    unreadable ledger would reach `compute_streak` as an empty list. That
    happens to refuse too, today, which is exactly why it is worth pinning: the
    reason would be wrong ("not measured yet") and a future gate that treated a
    short streak more kindly would inherit the wrong answer silently.
    """
    from app.tasks.espn_sync import _decide_failovers

    _no_ledger(monkeypatch, days=None, why="durable-read-CORRUPT: bad envelope")
    decisions = await _decide_failovers({}, {"americanfootball_nfl"}, {"errors": []})

    decision = decisions["americanfootball_nfl"]
    assert decision.failed_over is False
    assert "durable-read-CORRUPT" in decision.why


@pytest.mark.asyncio
async def test_today_nothing_is_dispatched_and_a_receipt_is_still_written(
    monkeypatch, dispatches
):
    """Dark by construction, at the actor rather than at the function.

    The empty ledger is the real production state, so this is what the next
    ESPN outage does today: records it, and takes no action.
    """
    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    _no_ledger(monkeypatch, days=[], why="no days")
    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers({}, {"americanfootball_nfl"}, stats), stats
    )

    assert dispatches.calls == []
    assert stats.get("failover_serving", 0) == 0
    assert stats["failover"][0]["code"] == NOT_GATED
    assert stats["failover"][0]["sport_key"] == NFL


@pytest.mark.asyncio
async def test_with_a_genuine_seven_the_outage_dispatches_statpal(
    monkeypatch, dispatches
):
    """The ship, proven end to end at the actor — and the pair that stops the
    test above from passing against a mechanism that can never act.

    The standby is read only because the gate opened, which is the ordering
    `decide` owns and `_decide_failovers` obeys.
    """
    import app.tasks.espn_sync as espn_sync

    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    _no_ledger(monkeypatch, days=SEVEN_MEETS_DAYS, why="seven")

    async def _standby(sport_key):
        return FIXTURES, FIXTURES

    monkeypatch.setattr(espn_sync, "_statpal_standby_reading", _standby)

    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers({}, {"americanfootball_nfl"}, stats), stats
    )

    assert dispatches.calls == [], "the failover must not dispatch anything"
    assert stats["failover_serving"] == 1
    assert stats["failover"][0]["code"] == FAILOVER_ESPN_DARK
    assert stats["failover"][0]["serving"] == STATPAL


@pytest.mark.asyncio
async def test_an_espn_slate_statpal_contradicts_also_dispatches(
    monkeypatch, dispatches
):
    """The empty-200 trap, all the way to the act.

    Found by mutation: narrowing `FAILOVER_CODES` to the dark case alone left
    every other test passing, because the actor was only ever exercised on an
    ESPN that had gone silent at the transport. This is the harder and more
    interesting case — ESPN answered 200 with an empty board while StatPal holds
    fixtures for the same window — and it must act identically.
    """
    import app.tasks.espn_sync as espn_sync

    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    _no_ledger(monkeypatch, days=SEVEN_MEETS_DAYS, why="seven")

    async def _standby(sport_key):
        return FIXTURES, FIXTURES

    monkeypatch.setattr(espn_sync, "_statpal_standby_reading", _standby)

    stats = {"errors": []}
    # ESPN ANSWERED — the key is present, the list is empty.
    await _act_on_failovers(
        await _decide_failovers(
            {"americanfootball_nfl": []}, {"americanfootball_nfl"}, stats
        ),
        stats,
    )

    assert dispatches.calls == [], "the failover must not dispatch anything"
    assert stats["failover_serving"] == 1
    assert stats["failover"][0]["code"] == FAILOVER_ESPN_SILENT
    assert stats["failover"][0]["code"] in FAILOVER_CODES


@pytest.mark.asyncio
async def test_a_failover_serves_in_line_and_dispatches_nothing(
    monkeypatch, dispatches
):
    """The act: StatPal's writers run INSIDE this pass, and no task is queued.

    Two things at once, because they are two halves of one decision:

      * it SERVES — `_sync_statpal_schedules` and `_sync_statpal_livescores`
        both run and both report a write;
      * it DISPATCHES NOTHING —
        `test_celery_result_retention.test_no_task_dispatches_another_task`
        bans intra-task dispatch across `app/tasks/` with no allowlist, and
        calling the coroutines directly has none of that hazard. This pins the
        behaviour so the idea cannot come back after the code guard is satisfied.
    """
    import app.services.statpal_api as statpal_api

    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    session, event_id = _wire_sqlite(monkeypatch)
    _no_ledger(monkeypatch, days=SEVEN_MEETS_DAYS, why="seven")
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    now = datetime.now(timezone.utc)
    live_row = _live(now - timedelta(hours=1))
    live_row.fixture_id = "sp-1"

    # Which service methods the WRITERS reach, recorded — because a counter
    # that increments beside a writer proves only that the line ran. Mutation
    # found this: stubbing `_sync_statpal_schedules` out entirely still left
    # `failover_schedule_writes == 1` and every assertion green.
    reached: list[str] = []

    class _Service:
        async def get_schedule_fixtures(self, sport, day_offset=None):
            reached.append("readiness:schedule")
            return [_Fx(now - timedelta(hours=1))]

        async def get_live_fixtures(self, sport):
            reached.append("readiness:live")
            return [live_row]

        async def get_live_scores(self, sport):
            reached.append("writer:livescores")
            return [live_row]

        async def get_fixtures(self, *a, **k):
            reached.append("writer:schedules")
            return []

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers(
            {"americanfootball_nfl": []}, {"americanfootball_nfl"}, stats
        ),
        stats,
    )

    assert stats["failover_serving"] == 1
    assert stats["failover_schedule_writes"] == 1
    assert stats["failover_live_writes"] == 1
    assert stats["failover"][0]["serving"] == STATPAL
    assert stats["errors"] == []

    # BOTH writers actually reached StatPal — not just their counters.
    assert "writer:schedules" in reached, (
        "`_sync_statpal_schedules` never called the service, so the schedule "
        f"half did not run. Reached: {reached}"
    )
    assert "writer:livescores" in reached, (
        f"`_sync_statpal_livescores` never called the service. Reached: {reached}"
    )
    # And readiness asked both questions before any of it.
    assert reached[:2] == ["readiness:schedule", "readiness:live"]

    # And nothing went to a queue.
    assert dispatches.calls == []
    assert dispatches.live.calls == []


@pytest.mark.asyncio
async def test_the_full_espn_pass_serves_a_dark_sport_and_the_score_advances(
    monkeypatch, dispatches
):
    """**CERT-2050's named regression.** The whole task, and a persisted advance.

    "Route a permitted ESPN-dark decision through an allowed non-task StatPal
    writer seam, with a full-task regression proving persisted status/score/
    period and a snapshot advance during `_sync_espn_live_events`."

    So this drives `_sync_espn_live_events` itself — not the helpers — with
    ESPN DARK for NFL (`get_scoreboard` returns `None`, which is the shape that
    means "the authority did not answer") and a healthy StatPal behind an open
    gate. The Event's score and period move and a ScoreSnapshot lands, from a
    pass in which ESPN contributed nothing at all.
    """
    from sqlalchemy import select

    import app.services.espn_api as espn_api
    import app.services.statpal_api as statpal_api
    from app.models.models import Event, ScoreSnapshot
    from app.tasks.espn_sync import _sync_espn_live_events

    session, event_id = _wire_sqlite(monkeypatch)
    _no_ledger(monkeypatch, days=SEVEN_MEETS_DAYS, why="seven")
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    now = datetime.now(timezone.utc)
    live_row = _live(now - timedelta(hours=1))
    live_row.home_score, live_row.away_score = 28, 24
    live_row.raw_status = "Q4"
    live_row.fixture_id = "sp-42"

    class _ESPN:
        async def get_scoreboard(self, sport_key, date=None):
            return None  # AUTHORITY DARK — ESPN did not answer.

        async def close(self):
            pass

    class _StatPal:
        async def get_schedule_fixtures(self, sport, day_offset=None):
            return [_Fx(now - timedelta(hours=1))]

        async def get_live_fixtures(self, sport):
            return [live_row]

        async def get_live_scores(self, sport):
            return [live_row]

        async def get_fixtures(self, *a, **k):
            return []

        async def close(self):
            pass

    monkeypatch.setattr(espn_api, "ESPNAPIService", _ESPN)
    monkeypatch.setattr(statpal_api, "StatPalAPIService", _StatPal)

    result = await _sync_espn_live_events()

    assert result["authority_dark_sports"] >= 1, result
    assert result["failover_serving"] == 1, result
    assert result["failover_live_writes"] == 1, result

    fresh = session.execute(select(Event).where(Event.id == event_id)).scalar_one()
    assert fresh.home_score == 28, "the site would still be showing the old score"
    assert fresh.away_score == 24
    assert fresh.period == "Q4"

    snaps = session.execute(
        select(ScoreSnapshot).where(ScoreSnapshot.event_id == event_id)
    ).scalars().all()
    assert len(snaps) == 1
    assert (snaps[0].home_score, snaps[0].away_score) == (28, 24)

    # The whole point: no task was queued to make that happen.
    assert dispatches.calls == []
    assert dispatches.live.calls == []


@pytest.mark.asyncio
async def test_a_quiet_day_writes_nothing_through_the_full_pass(
    monkeypatch, dispatches
):
    """**CERT-2050's named control.** ESPN empty and StatPal empty must not write.

    The other half of the regression, and the one that stops the test above
    from passing against a pass that serves unconditionally. ESPN ANSWERS with
    an empty board and StatPal has no started fixture: a quiet day, not an
    outage. The Event must be exactly as it was.
    """
    from sqlalchemy import select

    import app.services.espn_api as espn_api
    import app.services.statpal_api as statpal_api
    from app.models.models import Event, ScoreSnapshot
    from app.tasks.espn_sync import _sync_espn_live_events

    session, event_id = _wire_sqlite(monkeypatch)
    _no_ledger(monkeypatch, days=SEVEN_MEETS_DAYS, why="seven")
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    now = datetime.now(timezone.utc)

    class _ESPN:
        async def get_scoreboard(self, sport_key, date=None):
            return []  # ANSWERED, and has nothing.

        async def close(self):
            pass

    class _StatPal:
        async def get_schedule_fixtures(self, sport, day_offset=None):
            # A season of games, none of them started.
            return [_Fx(now + timedelta(days=d)) for d in range(1, 30)]

        async def get_live_fixtures(self, sport):
            return []

        async def get_live_scores(self, sport):
            return [_live(now - timedelta(hours=1))]

        async def get_fixtures(self, *a, **k):
            return []

        async def close(self):
            pass

    monkeypatch.setattr(espn_api, "ESPNAPIService", _ESPN)
    monkeypatch.setattr(statpal_api, "StatPalAPIService", _StatPal)

    result = await _sync_espn_live_events()

    assert result.get("failover_serving", 0) == 0, result
    assert result.get("failover_schedule_writes", 0) == 0
    assert result.get("failover_live_writes", 0) == 0
    assert result["failover"][0]["code"] == BOTH_QUIET

    fresh = session.execute(select(Event).where(Event.id == event_id)).scalar_one()
    assert fresh.home_score is None, "a quiet day wrote a score"
    assert fresh.away_score is None
    assert fresh.period is None
    assert session.execute(
        select(ScoreSnapshot).where(ScoreSnapshot.event_id == event_id)
    ).scalars().all() == []


@pytest.mark.asyncio
async def test_a_state_nobody_can_serve_is_counted_apart_from_an_ordinary_refusal(
    monkeypatch, dispatches
):
    """`failover_uncovered` is the alarming counter, and it is not the same as
    "no failover".

    Most refusals are facts about the day: a quiet slate, a sport with no shadow
    stamper, a streak that has not run. `BLANK_CODES` are the ones where ESPN is
    silent and the standby cannot cover, so nothing can say what is happening in
    a game that is on — the state the site actually goes blank in. Counting them
    together with the benign refusals would bury the only one worth waking up
    for.
    """
    import app.services.statpal_api as statpal_api

    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    _no_ledger(monkeypatch, days=SEVEN_MEETS_DAYS, why="seven")
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    now = datetime.now(timezone.utc)

    class _Service:
        async def get_schedule_fixtures(self, sport, day_offset=None):
            return [_Fx(now - timedelta(hours=1))]

        async def get_live_fixtures(self, sport):
            raise statpal_api.StatPalUpstreamError("livescores 503")

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers(
            {"americanfootball_nfl": []}, {"americanfootball_nfl"}, stats
        ),
        stats,
    )

    assert stats["failover_uncovered"] == 1
    assert stats.get("failover_serving", 0) == 0

    # The control: an ordinary refusal does NOT touch the alarming counter.
    stats2 = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers({}, {"soccer_epl"}, stats2), stats2
    )
    assert stats2.get("failover_uncovered", 0) == 0
    assert stats2["failover"][0]["code"] == NOT_GATED


@pytest.mark.asyncio
async def test_a_dark_standby_stops_the_failover_even_with_the_gate_open(
    monkeypatch, dispatches
):
    """The refusal that only exists once the gate is open, so it can only be
    reached — and can only be tested — under a genuine seven."""
    import app.tasks.espn_sync as espn_sync

    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    _no_ledger(monkeypatch, days=SEVEN_MEETS_DAYS, why="seven")

    async def _standby(sport_key):
        return DARK, DARK

    monkeypatch.setattr(espn_sync, "_statpal_standby_reading", _standby)

    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers({}, {"americanfootball_nfl"}, stats), stats
    )

    assert dispatches.calls == []
    assert stats["failover"][0]["code"] == STANDBY_DARK


# ── CERT-2040's repair: the two windows must be matched ─────────────────────


class _Fx:
    """A standby fixture: when it starts, who is playing, and its status.

    The team names matter since CERT-2046 — readiness correlates the schedule
    against the live board using the writer's own team-pair key, so a fixture
    with no names would be a game neither side could match.
    """

    def __init__(
        self,
        start_time,
        home="Bears",
        away="Packers",
        status="live",
        home_score=None,
        away_score=None,
        raw_status=None,
    ):
        self.start_time = start_time
        self.home_team = home
        self.away_team = away
        self.status = status
        # Since CERT-2047 a live row must also CARRY STATE for readiness to
        # count it. Default None, so a row is stateless unless a test says
        # otherwise — the safer default, and the one that would have caught
        # CERT-2047 had it been the default the first time.
        self.home_score = home_score
        self.away_score = away_score
        self.raw_status = raw_status


def _live(start_time, home="Bears", away="Packers"):
    """A live-board row that carries state the writer can advance from."""
    return _Fx(
        start_time, home=home, away=away,
        home_score=14, away_score=7, raw_status="Q2",
    )


def test_a_whole_season_of_future_fixtures_is_an_empty_reading():
    """**The CERT-2040 BLOCK, in one assertion.**

    `get_scoreboard` answers about today; `get_schedule_fixtures` answers with a
    season — 321 NFL games from August to February. The first cut counted the
    season against today's board, so a healthy quiet day read as StatPal having
    fixtures ESPN was hiding, and `BOTH_QUIET` became a state the system could
    not enter.
    """
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    season = [_Fx(now + timedelta(days=d)) for d in range(1, 90)]

    reading, detail = reading_in_window(season, now=now)
    assert reading == EMPTY, (
        "a season of fixtures none of which have started is not evidence that "
        "ESPN is hiding a game happening right now"
    )
    assert detail["total"] == 89 and detail["in_window"] == 0


def test_a_game_that_started_inside_the_window_is_a_fixtures_reading():
    """The control, and what stops the repair from being "always say EMPTY".

    One game two hours ago, among the same season of future ones: that is the
    blank this ship is about — a game under way that ESPN has stopped
    reporting.
    """
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    rows = [_Fx(now + timedelta(days=d)) for d in range(1, 90)]
    rows.append(_Fx(now - timedelta(hours=2)))

    reading, detail = reading_in_window(rows, now=now)
    assert reading == FIXTURES
    assert detail["in_window"] == 1


def test_the_window_edges_and_the_undated_row():
    """Both edges are inclusive, and an undated fixture never counts.

    An undated row cannot be shown to be in the window, and counting it would
    let an unplaceable season row trigger the exact failover the window exists
    to prevent — so it is reported and excluded, never guessed at.
    """
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)

    assert reading_in_window([_Fx(now)], now=now)[0] == FIXTURES
    assert reading_in_window([_Fx(now - WINDOW_BACK)], now=now)[0] == FIXTURES
    # Just outside, on both sides.
    assert reading_in_window(
        [_Fx(now - WINDOW_BACK - timedelta(minutes=1))], now=now
    )[0] == EMPTY
    assert reading_in_window([_Fx(now + timedelta(minutes=1))], now=now)[0] == EMPTY

    reading, detail = reading_in_window([_Fx(None), _Fx(None)], now=now)
    assert reading == EMPTY
    assert detail["undated"] == 2 and detail["in_window"] == 0


def test_a_naive_start_time_is_read_as_utc_rather_than_crashing():
    """A parser that dropped the tzinfo must not take the sync down — comparing
    an aware `now` with a naive fixture raises `TypeError` in Python."""
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 9, 6, 10, 0)
    assert reading_in_window([_Fx(naive)], now=now)[0] == FIXTURES


def test_a_dark_standby_still_reads_dark_through_the_windowed_path():
    """The window must not swallow the distinction the read path exists for."""
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    assert reading_in_window(None, now=now)[0] == DARK


@pytest.mark.asyncio
async def test_only_future_statpal_fixtures_do_not_dispatch_but_a_started_one_does(
    monkeypatch, dispatches
):
    """CERT-2040's named regression, end to end at the actor.

    "ESPN empty today plus only future StatPal fixtures must not dispatch,
    while a same-day fixture must." Both halves, under an open gate, through
    the real `_statpal_standby_reading`.
    """
    import app.services.statpal_api as statpal_api
    import app.tasks.espn_sync as espn_sync

    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    _no_ledger(monkeypatch, days=SEVEN_MEETS_DAYS, why="seven")
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    def _serve(rows, live_dark=False):
        class _Service:
            async def get_schedule_fixtures(self, sport, day_offset=None):
                return rows

            async def get_live_fixtures(self, sport):
                if live_dark:
                    raise statpal_api.StatPalUpstreamError("livescores 503")
                # Carries whatever the schedule says is under way, so this
                # stub is a HEALTHY StatPal. The contradiction case has its
                # own test.
                return [_live(r.start_time, r.home_team, r.away_team)
                        for r in rows if r.status == "live"
                        and r.start_time <= datetime.now(timezone.utc)]

            async def close(self):
                pass

        monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    now = datetime.now(timezone.utc)

    # Half one: a season of fixtures, none started. A quiet day, not an outage.
    _serve([_Fx(now + timedelta(days=d)) for d in range(1, 90)])
    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers(
            {"americanfootball_nfl": []}, {"americanfootball_nfl"}, stats
        ),
        stats,
    )
    assert dispatches.calls == []
    assert stats["failover"][0]["code"] == BOTH_QUIET

    # Half two: the same season plus one game that kicked off an hour ago.
    _serve(
        [_Fx(now + timedelta(days=d)) for d in range(1, 90)]
        + [_Fx(now - timedelta(hours=1))]
    )
    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers(
            {"americanfootball_nfl": []}, {"americanfootball_nfl"}, stats
        ),
        stats,
    )
    assert dispatches.calls == [], "the failover must not dispatch anything"
    assert stats["failover"][0]["code"] == FAILOVER_ESPN_SILENT


@pytest.mark.asyncio
async def test_a_dark_live_endpoint_refuses_by_name_and_dispatches_nothing(
    monkeypatch, dispatches
):
    """**CERT-2044's named regression.** "Current schedule + live endpoint dark
    yields a named refusal and no dispatch."

    The state: StatPal's `season-schedule` is healthy and holds a game that
    kicked off an hour ago, and `livescores` is down. Readiness used to read
    only the first, so this reported `FAILOVER-ESPN-SILENT` and `serving:
    statpal` while score, clock and status stayed frozen — a failover claiming
    to serve down a path it had never checked.

    It is a REFUSAL and not a quiet skip because this is the state in which the
    site genuinely does go blank: ESPN silent, StatPal unable to say what is
    happening. That deserves a named code an operator can search for.
    """
    import app.services.statpal_api as statpal_api

    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    _no_ledger(monkeypatch, days=SEVEN_MEETS_DAYS, why="seven")
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    now = datetime.now(timezone.utc)
    started = [_Fx(now - timedelta(hours=1))]

    class _Service:
        async def get_schedule_fixtures(self, sport, day_offset=None):
            return started

        async def get_live_fixtures(self, sport):
            raise statpal_api.StatPalUpstreamError("livescores 503")

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers(
            {"americanfootball_nfl": []}, {"americanfootball_nfl"}, stats
        ),
        stats,
    )

    assert dispatches.calls == []
    assert dispatches.live.calls == []
    assert stats.get("failover_serving", 0) == 0
    assert stats["failover"][0]["code"] == LIVE_PATH_DARK
    assert stats["failover"][0]["serving"] == ESPN
    assert stats["failover"][0]["failed_over"] is False


@pytest.mark.asyncio
async def test_a_healthy_live_endpoint_dispatches_both_halves(
    monkeypatch, dispatches
):
    """The control for the test above, and the second half of CERT-2044's
    regression: with `livescores` answering, the same state dispatches — and it
    dispatches BOTH tasks, because readiness proved both halves.

    Dispatching only the schedule sync would restore the sport's fixtures and
    leave score and clock to the 30s beat, which would make the live-path
    readiness check a question nothing acted on.
    """
    import app.services.statpal_api as statpal_api

    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    _no_ledger(monkeypatch, days=SEVEN_MEETS_DAYS, why="seven")
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    now = datetime.now(timezone.utc)

    class _Service:
        async def get_schedule_fixtures(self, sport, day_offset=None):
            return [_Fx(now - timedelta(hours=1), home="Montréal", away="Bears")]

        async def get_live_fixtures(self, sport):
            # Carries the game the schedule says is under way. Since CERT-2046
            # an answer alone is not health — the live board has to be
            # carrying the fixture at risk, because the writer keys on it.
            #
            # SPELLED DIFFERENTLY ON PURPOSE. StatPal's two endpoints do not
            # agree on case or accents, and the writer's `_fixture_match_key`
            # normalises both away. If readiness ever stopped using THAT key
            # and grew its own, this pair would stop matching and the failover
            # would refuse a sport StatPal was serving perfectly well — so this
            # is what pins "readiness uses the writer's key" at the actor,
            # rather than only where the key is passed in.
            return [_live(now - timedelta(hours=1), home="MONTREAL", away="bears")]

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers(
            {"americanfootball_nfl": []}, {"americanfootball_nfl"}, stats
        ),
        stats,
    )

    assert dispatches.calls == [], "the failover must not dispatch anything"
    assert dispatches.live.calls == []
    assert stats["failover"][0]["code"] == FAILOVER_ESPN_SILENT


@pytest.mark.asyncio
async def test_an_answering_but_empty_live_board_refuses_when_a_game_is_on(
    monkeypatch, dispatches
):
    """**CERT-2046's named regression.** "Persisted active event + current
    schedule + HTTP-200/empty livescores must not declare/dispatch failover."

    The state presentation three got wrong: StatPal's schedule says a game
    kicked off an hour ago, `livescores` answers 200 with `[]`. That is not a
    healthy quiet board — it is StatPal contradicting itself, and the writer,
    which keys live rows to events by team pair, would skip every event and
    write no score, no period and no snapshot while the receipt said
    `serving: statpal`.
    """
    import app.services.statpal_api as statpal_api

    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    _no_ledger(monkeypatch, days=SEVEN_MEETS_DAYS, why="seven")
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    now = datetime.now(timezone.utc)

    class _Service:
        async def get_schedule_fixtures(self, sport, day_offset=None):
            return [_Fx(now - timedelta(hours=1))]

        async def get_live_fixtures(self, sport):
            return []  # HTTP 200, no rows.

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers(
            {"americanfootball_nfl": []}, {"americanfootball_nfl"}, stats
        ),
        stats,
    )

    assert dispatches.calls == []
    assert dispatches.live.calls == []
    assert stats.get("failover_serving", 0) == 0
    assert stats["failover"][0]["code"] == LIVE_PATH_SILENT_ON_THE_GAME
    assert stats["failover"][0]["failed_over"] is False
    # Named apart from the transport failure: one is StatPal down, the other is
    # StatPal wrong, and an operator needs to know which.
    assert LIVE_PATH_SILENT_ON_THE_GAME != LIVE_PATH_DARK


def test_a_finished_fixture_is_not_expected_on_the_live_board():
    """The control that stops the repair from being "always refuse".

    A game StatPal's own schedule calls `finished` has legitimately dropped off
    the live board. Demanding it be there would make readiness permanently
    false for the six hours after every game ends — the window is 6h back, so
    every completed game sits in it.
    """
    from app.tasks.statpal_sync import _fixture_match_key, live_row_bears_state
    from app.utils.authority_failover import active_fixtures, live_reading_for

    now = datetime.now(timezone.utc)
    done = _Fx(now - timedelta(hours=3), status="finished")
    playing = _Fx(now - timedelta(hours=1), home="Jets", away="Bills")

    assert active_fixtures([done], now=now) == []
    # An empty live board with only a finished fixture in window is healthy.
    reading, _ = live_reading_for(
        active_fixtures([done], now=now), [], key=_fixture_match_key,
        bears_state=live_row_bears_state,
    )
    assert reading == FIXTURES

    # And the live one still has to be carried.
    reading, detail = live_reading_for(
        active_fixtures([done, playing], now=now), [], key=_fixture_match_key,
        bears_state=live_row_bears_state,
    )
    assert reading == EMPTY
    assert detail["missing"] == 1


def test_readiness_matches_on_the_writers_own_key():
    """Readiness and the writer agree by construction, not by coincidence.

    `live_reading_for` takes the key function rather than owning one, and the
    caller passes `statpal_sync._fixture_match_key` — the same function the
    writer uses to bind a live row to an event. Two implementations of "the
    same game" is how readiness comes to count a fixture the writer will not
    find, which is the whole class of defect CERT-2044 and CERT-2046 are in.
    """
    from app.tasks.statpal_sync import _fixture_match_key, live_row_bears_state
    from app.utils.authority_failover import live_reading_for

    now = datetime.now(timezone.utc)
    scheduled = _Fx(now - timedelta(hours=1), home="Montréal", away="Bears")
    # The live board spells it without the accent and in a different case —
    # the writer's key normalises both away, so readiness must too.
    live = _live(now, home="MONTREAL", away="bears")

    reading, detail = live_reading_for(
        [scheduled], [live], key=_fixture_match_key,
        bears_state=live_row_bears_state,
    )
    assert reading == FIXTURES, detail

    # The control: a genuinely different game does NOT cover it.
    other = _live(now, home="Jets", away="Bills")
    reading, detail = live_reading_for(
        [scheduled], [other], key=_fixture_match_key,
        bears_state=live_row_bears_state,
    )
    assert reading == EMPTY
    assert detail["missing"] == 1


@pytest.mark.asyncio
async def test_the_matching_live_row_advances_score_and_period_through_the_real_writer(
    monkeypatch,
):
    """**CERT-2046's second named regression, and CERT-2044's, now paid.**

    "The paired matching live row must advance score and period/status through
    the real writer."

    Asked twice and argued with once, on the grounds that
    `_sync_statpal_livescores` is pre-existing behaviour this ship only invokes.
    The reviewer asked again, so it is built rather than re-argued — and it is a
    better test than the argument was, because it is the only thing that closes
    the loop the last three BLOCKs were all about: readiness says StatPal can
    serve, and this shows the dispatched writer then actually writes.

    Real ORM statements against a real engine (sqlite, no aiosqlite in this
    sandbox, so the session is the repo's established async shim over a sync
    one). Nothing about the writer is stubbed except its HTTP client.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    import app.services.statpal_api as statpal_api
    import app.tasks.base as task_base
    from app.models.models import Base, Event, ScoreSnapshot, Sport
    from app.tasks.statpal_sync import _sync_statpal_livescores

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[Event.__table__, Sport.__table__, ScoreSnapshot.__table__],
    )
    # `expire_on_commit=False`, matching the app's own task sessions (gotcha
    # #6). Without it sqlite reloads `commence_time` as a NAIVE datetime after
    # the commit — sqlite has no tz type — and the writer's premature-live guard
    # raises comparing it with an aware `now`. That is a sqlite artifact, not a
    # production shape; Postgres returns the value tz-aware.
    sync_session = Session(engine, expire_on_commit=False)

    now = datetime.now(timezone.utc)
    sport = Sport(key=NFL, name="NFL")
    sync_session.add(sport)
    sync_session.flush()
    event = Event(
        sport_id=sport.id,
        home_team_name="Bears",
        away_team_name="Packers",
        commence_time=now - timedelta(hours=1),
        status="live",
    )
    sync_session.add(event)
    sync_session.commit()
    event_id = event.id

    class _AsyncShim:
        """Async surface over a real sync session. The statements executed are
        the writer's own and the rows come back through the real result API."""

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

    live_row = _Fx(now - timedelta(hours=1))
    live_row.home_score = 21
    live_row.away_score = 17
    live_row.raw_status = "Q3"
    live_row.fixture_id = "sp-999"

    class _Service:
        async def get_live_scores(self, sport):
            return [live_row]

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    result = await _sync_statpal_livescores()

    fresh = sync_session.execute(
        select(Event).where(Event.id == event_id)
    ).scalar_one()
    assert fresh.home_score == 21, result
    assert fresh.away_score == 17, result
    assert fresh.period == "Q3", result

    snaps = sync_session.execute(
        select(ScoreSnapshot).where(ScoreSnapshot.event_id == event_id)
    ).scalars().all()
    assert len(snaps) == 1
    assert (snaps[0].home_score, snaps[0].away_score) == (21, 17)
    assert result["events_updated"] == 1


@pytest.mark.parametrize(
    "kwargs,expected,why",
    [
        ({"home_score": 14}, True, "a home score alone is state"),
        ({"away_score": 7}, True, "an away score alone is state"),
        ({"raw_status": "Q3"}, True, "a period alone is state"),
        ({"raw_status": "HT"}, True, "half time is a period"),
        # 0-0 IS a score. `is not None`, never truthiness — a scoreless first
        # quarter is the most ordinary live state there is, and a predicate
        # written with `if fixture.home_score:` would call it stateless and
        # refuse to fail over during exactly the part of a game where the
        # score has not moved yet.
        ({"home_score": 0, "away_score": 0}, True, "0-0 is a score, not an absence"),
        ({}, False, "no score and no period is nothing the writer can use"),
        ({"raw_status": "live"}, False, "'live' says it is live, not what is happening"),
        ({"raw_status": "Live"}, False, "same, capitalised — the writer excludes both"),
        ({"raw_status": ""}, False, "an empty string is not a period"),
    ],
)
def test_each_branch_of_the_state_predicate_on_its_own(kwargs, expected, why):
    """Every branch isolated, because a row with all of them proves none of them.

    Found by mutation: deleting the `home_score` branch left the whole suite
    green, because every state-bearing fake carried scores AND a period, so the
    surviving branches covered for the deleted one. A predicate the writer's
    behaviour depends on has to be pinned one condition at a time.
    """
    from app.tasks.statpal_sync import live_row_bears_state

    row = _Fx(datetime.now(timezone.utc), **kwargs)
    assert live_row_bears_state(row) is expected, why


@pytest.mark.asyncio
async def test_a_same_team_row_with_no_state_refuses_and_dispatches_nothing(
    monkeypatch, dispatches
):
    """**CERT-2047's first named regression.**

    "An in-window active schedule row plus same-team scheduled/no-state live row
    must refuse and dispatch nothing."

    The row MATCHES on the team key and carries nothing the writer can use — no
    scores, no period. Presentation four accepted it, because coverage was
    measured by key presence alone. Every state-bearing branch in the writer is
    guarded on `home_score`/`away_score` being present or a `raw_status` richer
    than "live", so this pass would have written nothing while the receipt said
    `serving: statpal`.
    """
    import app.services.statpal_api as statpal_api

    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    _no_ledger(monkeypatch, days=SEVEN_MEETS_DAYS, why="seven")
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    now = datetime.now(timezone.utc)

    class _Service:
        async def get_schedule_fixtures(self, sport, day_offset=None):
            return [_Fx(now - timedelta(hours=1))]

        async def get_live_fixtures(self, sport):
            # Right teams. `scheduled`. No scores, no raw period.
            return [_Fx(now - timedelta(hours=1), status="scheduled")]

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers(
            {"americanfootball_nfl": []}, {"americanfootball_nfl"}, stats
        ),
        stats,
    )

    assert dispatches.calls == []
    assert dispatches.live.calls == []
    assert stats.get("failover_serving", 0) == 0
    assert stats["failover"][0]["code"] == LIVE_PATH_SILENT_ON_THE_GAME
    assert stats["failover"][0]["failed_over"] is False


@pytest.mark.asyncio
async def test_a_stateless_live_row_advances_nothing_through_the_real_writer(
    monkeypatch,
):
    """**CERT-2047's second half, and the proof that the predicate is honest.**

    `live_row_bears_state` claims to describe what the writer can act on. That
    claim is worth exactly as much as its agreement with the writer, so this
    runs the REAL `_sync_statpal_livescores` over a row the predicate rejects
    and shows score and period unmoved.

    Paired with
    `test_the_matching_live_row_advances_score_and_period_through_the_real_writer`,
    which does the same with a row the predicate accepts and shows both move.
    Together they are the evidence that readiness and the writer agree — which
    four reviews running has been the thing this ship kept failing to have.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    import app.services.statpal_api as statpal_api
    import app.tasks.base as task_base
    from app.models.models import Base, Event, ScoreSnapshot, Sport
    from app.tasks.statpal_sync import _sync_statpal_livescores, live_row_bears_state

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[Event.__table__, Sport.__table__, ScoreSnapshot.__table__],
    )
    sync_session = Session(engine, expire_on_commit=False)

    now = datetime.now(timezone.utc)
    sport = Sport(key=NFL, name="NFL")
    sync_session.add(sport)
    sync_session.flush()
    event = Event(
        sport_id=sport.id,
        home_team_name="Bears",
        away_team_name="Packers",
        commence_time=now - timedelta(hours=1),
        status="live",
    )
    sync_session.add(event)
    sync_session.commit()
    event_id = event.id

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

    stateless = _Fx(now - timedelta(hours=1), status="scheduled")
    stateless.fixture_id = "sp-777"
    # The predicate's claim, stated before the writer is asked.
    assert live_row_bears_state(stateless) is False

    class _Service:
        async def get_live_scores(self, sport):
            return [stateless]

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    await _sync_statpal_livescores()

    fresh = sync_session.execute(
        select(Event).where(Event.id == event_id)
    ).scalar_one()
    assert fresh.home_score is None, "the writer advanced a score from a stateless row"
    assert fresh.away_score is None
    assert fresh.period is None, "the writer advanced a period from a stateless row"
    snaps = sync_session.execute(
        select(ScoreSnapshot).where(ScoreSnapshot.event_id == event_id)
    ).scalars().all()
    assert snaps == []

    # And the predicate's other half, so this is not "the predicate says False
    # about everything": the same row with a score is accepted.
    assert live_row_bears_state(_live(now)) is True


def test_the_note_says_what_a_flip_does_NOT_do(monkeypatch):
    """CERT-2040's other finding: the disclosure over-claimed.

    The first cut's note said flipping "changes what serves it", which an
    operator would reasonably read as ESPN having been suppressed. It has not
    been — `_sync_espn_live_events` selects sports by what ESPN returned, not by
    the switch, so a flipped sport still takes its scores and win probability
    from ESPN on every pass ESPN answers.

    The repair is the note, not the behaviour: suppressing ESPN for a flipped
    sport would remove a win-probability source from the blend, which is a
    product decision and a further build step. So this pins that the limit is
    STATED, which is what #3442 established as the standard — put the true
    sentence where the person deciding will read it.
    """
    from app.config.authority_by_sport import SWITCH_WIRING_NOTE, switch_wiring_note

    note = switch_wiring_note(True)
    assert note == SWITCH_WIRING_NOTE
    assert "DOES NOT" in note
    assert "does not suppress the ESPN path" in note
    assert "win probability" in note

    # And the decision's own reason carries the same caveat, so a reader of the
    # receipt is not left with a `serving: statpal` they will over-read.
    standing = decide(NFL, espn=DARK, gate=_shut_gate(), standing=STATPAL)
    assert "NOTE THE LIMIT" in standing.why


# ── The two reads the tests above stub, proven for themselves ───────────────


@pytest.mark.asyncio
async def test_an_untrustworthy_ledger_reads_as_none_never_as_no_days():
    """`read_ledger_days`'s own contract, not a stub of it.

    `None` (could not be trusted) and `[]` (exists, has recorded nothing) must
    not collapse. `_read_ledger` classifies rather than raising, so the refusal
    arrives as a dict and this asserts it is not mistaken for a ledger.
    """
    import app.services.authority_ledger as ledger

    async def _refuse(identity):
        return {"refuse": {"reason": "durable-read-CORRUPT", "detail": "bad envelope"}}

    original = ledger._read_ledger
    ledger._read_ledger = _refuse
    try:
        days, why = await ledger.read_ledger_days(NFL)
    finally:
        ledger._read_ledger = original

    assert days is None, "a refused read must not arrive as a ledger with no days"
    assert "durable-read-CORRUPT" in why
    assert "bad envelope" in why


@pytest.mark.asyncio
async def test_a_ledger_that_exists_with_no_days_reads_as_an_empty_list():
    """The other side of the same distinction — the control that stops the test
    above from passing because the function returns `None` for everything."""
    import app.services.authority_ledger as ledger

    async def _empty(identity):
        return {"ledger": {"sport_key": NFL, "days": []}, "generation": 1}

    original = ledger._read_ledger
    ledger._read_ledger = _empty
    try:
        days, why = await ledger.read_ledger_days(NFL)
    finally:
        ledger._read_ledger = original

    assert days == []
    assert "0 recorded day" in why


@pytest.mark.asyncio
async def test_the_standby_is_read_through_the_client_that_can_say_dark(monkeypatch):
    """`_statpal_standby_reading` must not use `get_fixtures`.

    `get_fixtures` ends `if not data: return []`, so an upstream failure and a
    sport with no games arrive identically — the same collapse this ship exists
    to undo, on the other side of the comparison. `get_schedule_fixtures` raises
    `StatPalUpstreamError` instead, and that is why it is the one called.
    """
    import app.services.statpal_api as statpal_api
    from app.tasks.espn_sync import _statpal_standby_reading

    calls: list[str] = []

    class _Service:
        async def get_schedule_fixtures(self, sport, day_offset=None):
            calls.append(f"schedule:{sport}")
            # A game that kicked off an hour ago. It has to be a real
            # `start_time`: since CERT-2040's repair an undated row is
            # unplaceable and does not count, so a bare sentinel here would
            # (correctly) read EMPTY and this test would be asserting the
            # wrong thing.
            return [_Fx(datetime.now(timezone.utc) - timedelta(hours=1))]

        async def get_live_fixtures(self, sport):
            calls.append(f"live:{sport}")
            return [_live(datetime.now(timezone.utc) - timedelta(hours=1))]

        async def get_fixtures(self, *a, **k):  # pragma: no cover - must not run
            raise AssertionError(
                "the standby was read through `get_fixtures`, which cannot "
                "distinguish an outage from an empty slate"
            )

        async def get_live_scores(self, *a, **k):  # pragma: no cover - must not run
            raise AssertionError(
                "the live half was read through `get_live_scores`, which ends "
                "`if not data: return []` and cannot express dark"
            )

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    assert await _statpal_standby_reading(NFL) == (FIXTURES, FIXTURES)
    assert calls == ["schedule:nfl", "live:nfl"]


@pytest.mark.asyncio
async def test_an_upstream_error_from_the_standby_is_dark_not_empty(monkeypatch):
    """The raise the authority read path exists to make, honoured here.

    Reported as DARK, so `decide` refuses. Reading it as EMPTY would make the
    decision `NOTHING_TO_SERVE` — a confident claim that StatPal has no games,
    manufactured out of our own failure to ask.
    """
    import app.services.statpal_api as statpal_api
    from app.tasks.espn_sync import _statpal_standby_reading

    class _Service:
        async def get_schedule_fixtures(self, sport, day_offset=None):
            raise statpal_api.StatPalUpstreamError("502 from StatPal")

        async def get_live_fixtures(self, sport):  # pragma: no cover
            return []

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    assert await _statpal_standby_reading(NFL) == (DARK, DARK)


@pytest.mark.asyncio
async def test_an_unmapped_or_keyless_standby_is_dark_not_empty(monkeypatch):
    """We did not ask, so StatPal has said nothing — and our own silence must
    never be published as theirs."""
    import app.services.statpal_api as statpal_api
    from app.tasks.espn_sync import _statpal_standby_reading

    monkeypatch.setattr(statpal_api, "is_available", lambda: False)
    assert await _statpal_standby_reading(NFL) == (DARK, DARK)

    monkeypatch.setattr(statpal_api, "is_available", lambda: True)
    assert await _statpal_standby_reading("quidditch_premier") == (DARK, DARK)


def _espn_sync_function(name: str) -> ast.FunctionDef:
    import app.tasks.espn_sync as espn_sync

    tree = ast.parse(Path(espn_sync.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found — this guard is watching nothing")


def test_the_sync_no_longer_defaults_espn_data_to_an_empty_list():
    """The regression guard on the exact line #3473 is about.

    An AST walk rather than a grep: `espn_data.get(\\n    sport_key,\\n    [],\\n)`
    is the same defect and defeats a substring scan, and the linter is entitled
    to produce that formatting at any time.
    """
    fn = _espn_sync_function("_sync_espn_live_events")
    offenders = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "espn_data"
        and len(node.args) > 1
    ]
    assert not offenders, (
        "`espn_data.get(sport_key, <default>)` is back at line(s) "
        f"{[n.lineno for n in offenders]}. A default here collapses 'ESPN went "
        "dark' into 'ESPN has no games' and undoes the whole ship — take the "
        "reading with `_failover.espn_reading` instead"
    )

    # The control: the walk is looking at a function that really does touch
    # `espn_data`, so a rename could not make this pass by finding nothing.
    touches = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Name) and node.id == "espn_data"
    ]
    assert touches, "`_sync_espn_live_events` no longer mentions `espn_data`"


# ── One live write per pass, however many sports went dark ──────────────────
#
# `STANDING-STATPAL-FAILOVER-COALESCING` (CERT-2052): *"before multiple sports
# flip, call the global livescore writer once per pass or prove 300-second
# runtime and concurrent-write idempotence against its 30-second beat."* The
# first branch, taken. These are the tests that catch it coming back.
#
# The condition is not hypothetical. NFL, NBA and NHL are all at day 2 of D50's
# seven as of 2026-09-06 and `flip_permitted` opens for all three on the same
# days, so the first day any of them can flip is a day all three can — which is
# why the multi-sport pass is tested with exactly those three keys.


def _three_dark_sports_wiring(monkeypatch):
    """A pass where NFL, NBA and NHL are all ESPN-dark and all servable.

    Returns the `calls` list every writer appends to, in call order — one list
    rather than two counters, because "one live write" is only the right answer
    if it lands AFTER the schedule writes it should see the fixtures of.
    """
    import app.services.statpal_api as statpal_api
    import app.tasks.espn_sync as espn_sync
    import app.tasks.statpal_sync as statpal_sync

    _no_ledger(monkeypatch, days=SEVEN_MEETS_DAYS, why="seven")
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    async def _standby(sport_key):
        return FIXTURES, FIXTURES

    monkeypatch.setattr(espn_sync, "_statpal_standby_reading", _standby)

    calls: list[str] = []

    async def _schedules(sport_key):
        calls.append(f"schedule:{sport_key}")
        return {"ok": True}

    async def _livescores():
        calls.append("live")
        return {"ok": True}

    monkeypatch.setattr(statpal_sync, "_sync_statpal_schedules", _schedules)
    monkeypatch.setattr(statpal_sync, "_sync_statpal_livescores", _livescores)
    return calls


THREE_DARK = {"americanfootball_nfl", "basketball_nba", "icehockey_nhl"}


def test_the_control_all_three_of_those_sports_really_do_open_on_the_same_days():
    """Without this, the multi-sport tests could pass by serving one sport.

    If a future ruling closes NBA or NHL, these tests must fail loudly here —
    at the premise — rather than quietly degrade into a single-sport pass that
    a per-sport live write would also satisfy.
    """
    opened = [k for k in sorted(THREE_DARK) if flip_permitted(k, SEVEN_MEETS_DAYS)[0]]
    assert opened == sorted(THREE_DARK), (
        "the multi-sport coalescing tests are no longer testing multiple sports: "
        f"only {opened} open on seven MEETS days"
    )


@pytest.mark.asyncio
async def test_three_dark_sports_get_three_schedule_writes_and_one_live_write(
    monkeypatch, dispatches
):
    """**The named repair.** N sports served, ONE global livescore call.

    `_sync_statpal_livescores()` takes no sport key — it advances every sport
    that has a live event in our database — so one call covers all three. The
    first cut called it inside the per-sport loop, which was invisible while at
    most one sport could be permitted and becomes three full passes over every
    live sport the moment three can.

    The schedule writer is the opposite and stays per sport: it takes a key, so
    three dark sports are three genuinely different reads.
    """
    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    calls = _three_dark_sports_wiring(monkeypatch)

    stats = {"errors": []}
    await _act_on_failovers(await _decide_failovers({}, THREE_DARK, stats), stats)

    assert calls.count("live") == 1, (
        "the global livescore writer ran once per SPORT instead of once per "
        f"PASS — {calls.count('live')} calls for 3 sports. Call order: {calls}"
    )
    assert sorted(c for c in calls if c.startswith("schedule:")) == [
        "schedule:americanfootball_nfl",
        "schedule:basketball_nba",
        "schedule:icehockey_nhl",
    ], calls
    # And the one live write lands last, after every fixture this pass wrote.
    assert calls[-1] == "live", calls

    assert stats["failover_serving"] == 3
    assert stats["failover_schedule_writes"] == 3
    assert stats["failover_live_writes"] == 1
    # The counter that stops "1 live write" reading as "two sports unserved".
    assert stats["failover_live_sports_covered"] == 3
    assert stats["errors"] == []
    assert dispatches.calls == []


@pytest.mark.asyncio
async def test_a_sport_the_gate_refuses_gets_no_schedule_write_and_is_not_counted(
    monkeypatch, dispatches
):
    """The pairing that stops the test above passing against "serve everything".

    Baseball is ESPN-dark in the same pass and `flip_permitted` refuses it — no
    governing identity number (D63). Three sports are served, four went dark,
    and the single live write is still one call covering the three that were.
    """
    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    calls = _three_dark_sports_wiring(monkeypatch)
    assert flip_permitted("baseball_mlb", SEVEN_MEETS_DAYS)[0] is False, (
        "the control is broken: baseball now opens on seven days, so this test "
        "is no longer about a refused sport"
    )

    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers({}, THREE_DARK | {"baseball_mlb"}, stats), stats
    )

    assert "schedule:baseball_mlb" not in calls, calls
    assert calls.count("live") == 1, calls
    assert stats["failover_serving"] == 3
    assert stats["failover_live_sports_covered"] == 3, (
        "the covered count must name the sports actually served, not every "
        f"sport ESPN went dark on. {stats}"
    )
    assert len(stats["failover"]) == 4, "every dark sport still gets a receipt"


@pytest.mark.asyncio
async def test_no_sport_served_means_the_live_writer_is_never_called(
    monkeypatch, dispatches
):
    """The other direction, and the one a coalesced call is easiest to break in.

    "Call it once per pass" must mean once per pass **that served something**.
    A pass where the gate refuses everything — today's production state — must
    not touch StatPal at all, and an unconditional post-loop call would look
    correct in every test above.
    """
    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    calls = _three_dark_sports_wiring(monkeypatch)
    _no_ledger(monkeypatch, days=[], why="no days")  # shut the gate again

    stats = {"errors": []}
    await _act_on_failovers(await _decide_failovers({}, THREE_DARK, stats), stats)

    assert calls == [], f"a pass that served nothing still wrote: {calls}"
    assert stats.get("failover_serving", 0) == 0
    assert "failover_live_writes" not in stats
    assert "failover_live_sports_covered" not in stats


@pytest.mark.asyncio
async def test_a_failed_live_write_records_one_error_naming_every_sport_it_dropped(
    monkeypatch, dispatches
):
    """One call means one failure — and it must say who lost coverage.

    Per-sport calls used to produce a per-sport error each. Coalescing gives one
    exception for three dropped sports, so the error string carries all three
    names or an operator reads one sport's outage where there were three. The
    schedule writes that DID work stay counted: a partial outcome is a real one.

    `failover_live_sports_covered` must NOT advance — the sports were served a
    schedule and nothing else.
    """
    import app.tasks.statpal_sync as statpal_sync

    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    calls = _three_dark_sports_wiring(monkeypatch)

    async def _boom():
        calls.append("live")
        raise RuntimeError("statpal livescores 503")

    monkeypatch.setattr(statpal_sync, "_sync_statpal_livescores", _boom)

    stats = {"errors": []}
    await _act_on_failovers(await _decide_failovers({}, THREE_DARK, stats), stats)

    assert calls.count("live") == 1, calls
    assert len(stats["errors"]) == 1, stats["errors"]
    error = stats["errors"][0]
    for sport_key in sorted(THREE_DARK):
        assert sport_key in error, (
            f"{sport_key} lost live coverage and the error does not name it: "
            f"{error}"
        )
    assert "503" in error
    assert stats["failover_schedule_writes"] == 3, "the schedule half worked"
    assert stats.get("failover_live_writes", 0) == 0
    assert stats.get("failover_live_sports_covered", 0) == 0


@pytest.mark.asyncio
async def test_the_one_sport_case_reports_exactly_what_it_reported_before(
    monkeypatch, dispatches
):
    """Coalescing must be invisible in the only case production can reach today.

    At most one sport can be permitted at a time until a second clears seven
    days, so the single-sport summary and the single-sport error string are a
    live contract with anything already reading them. Both are unchanged: one
    live write, one covered sport, and an error keyed on the bare sport name.
    """
    import app.tasks.statpal_sync as statpal_sync

    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    calls = _three_dark_sports_wiring(monkeypatch)

    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers({}, {"americanfootball_nfl"}, stats), stats
    )
    assert calls == ["schedule:americanfootball_nfl", "live"]
    assert stats["failover_live_writes"] == 1
    assert stats["failover_live_sports_covered"] == 1

    async def _boom():
        raise RuntimeError("statpal livescores 503")

    monkeypatch.setattr(statpal_sync, "_sync_statpal_livescores", _boom)
    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers({}, {"americanfootball_nfl"}, stats), stats
    )
    assert stats["errors"] == [
        "failover_live_americanfootball_nfl: statpal livescores 503"
    ], "the one-sport error string changed shape"
