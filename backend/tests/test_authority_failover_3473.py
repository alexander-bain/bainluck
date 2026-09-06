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
from pathlib import Path

import pytest

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
    NOT_GATED,
    NOT_READ,
    NOTHING_TO_SERVE,
    STANDBY_DARK,
    STANDBY_NOT_READ,
    STANDING_STATPAL,
    decide,
    espn_reading,
    reading_from_fixtures,
    would_fail_over_now,
)

NFL = "americanfootball_nfl"

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
    assert decide(NFL, espn=DARK, statpal=DARK, gate=_open_gate()).code == STANDBY_DARK


# ── The nine outcomes ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "espn,statpal,expected,serving,failed_over",
    [
        # ESPN answering ends everything, and is the only deactivation there is.
        (FIXTURES, NOT_READ, ESPN_ANSWERED, ESPN, False),
        # The two that fire.
        (DARK, FIXTURES, FAILOVER_ESPN_DARK, STATPAL, True),
        (EMPTY, FIXTURES, FAILOVER_ESPN_SILENT, STATPAL, True),
        # Both answered, neither has a game: a quiet slate, never an outage.
        (EMPTY, EMPTY, BOTH_QUIET, ESPN, False),
        # A real unexplained silence with nothing to serve in its place.
        (DARK, EMPTY, NOTHING_TO_SERVE, ESPN, False),
        # Trading a known silence for an unknown one.
        (DARK, DARK, STANDBY_DARK, ESPN, False),
        (EMPTY, DARK, STANDBY_DARK, ESPN, False),
        # A caller bug, reported rather than raised.
        (DARK, NOT_READ, STANDBY_NOT_READ, ESPN, False),
    ],
)
def test_every_outcome_under_an_open_gate(espn, statpal, expected, serving, failed_over):
    """The states production will reach after 2026-09-11, proven now.

    Under the REAL gate opened by seven real days — so this is the behaviour the
    mechanism will actually have, not the behaviour of a stub.
    """
    decision = decide(NFL, espn=espn, statpal=statpal, gate=_open_gate())
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
            NFL, espn=DARK, statpal=FIXTURES, gate=gate
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
    during = decide(NFL, espn=DARK, statpal=FIXTURES, gate=gate)
    assert during.failed_over is True

    after = decide(NFL, espn=FIXTURES, statpal=FIXTURES, gate=gate)
    assert after.code == ESPN_ANSWERED
    assert after.serving == ESPN
    assert after.failed_over is False

    # And the case a latch gets wrong: ESPN back with an empty slate that
    # StatPal agrees with is a quiet day, not a continuing outage.
    quiet = decide(NFL, espn=EMPTY, statpal=EMPTY, gate=gate)
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
    assert params == {"espn", "statpal", "gate", "standing"}, (
        "a new input to `decide` — if it carries game STATE rather than a "
        "reading, step 7's 'never for state disagreements' stops being "
        f"structural. Got {sorted(params)}"
    )


def test_decide_is_total_and_never_raises():
    """A `KeyError` out of this path would be an outage in the sport we were
    trying to protect, so every input has an answer — including nonsense."""
    for espn in (DARK, EMPTY, FIXTURES, "who knows", ""):
        for statpal in (DARK, EMPTY, FIXTURES, NOT_READ, "who knows"):
            decision = decide(NFL, espn=espn, statpal=statpal, gate=_open_gate())
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


# ── The consumer: what the ESPN sync actually does with a decision ──────────


class _Dispatches:
    """Stands in for `sync_statpal_schedules`, recording what was dispatched."""

    def __init__(self, explode: bool = False):
        self.calls: list[str] = []
        self.explode = explode

    def delay(self, sport_key):
        if self.explode:
            raise RuntimeError("broker unreachable")
        self.calls.append(sport_key)


@pytest.fixture
def dispatches(monkeypatch):
    import app.tasks as tasks

    stub = _Dispatches()
    monkeypatch.setattr(tasks, "sync_statpal_schedules", stub, raising=False)
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
    assert stats.get("failover_activated", 0) == 0
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
        return FIXTURES

    monkeypatch.setattr(espn_sync, "_statpal_standby_reading", _standby)

    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers({}, {"americanfootball_nfl"}, stats), stats
    )

    assert dispatches.calls == [NFL]
    assert stats["failover_activated"] == 1
    assert stats["failover_dispatched"] == 1
    assert stats["failover"][0]["code"] == FAILOVER_ESPN_DARK
    assert stats["failover"][0]["serving"] == STATPAL


@pytest.mark.asyncio
async def test_a_failed_dispatch_is_not_counted_as_a_failover_that_served(
    monkeypatch, dispatches
):
    """Two counters, because a decision and a dispatch can come apart.

    A broker that refused the job is a failover that did not happen, and
    reporting `activated == dispatched` by assumption would make an outage the
    site did NOT ride out look like one it did.
    """
    import app.tasks as tasks
    import app.tasks.espn_sync as espn_sync

    from app.tasks.espn_sync import _act_on_failovers, _decide_failovers

    monkeypatch.setattr(tasks, "sync_statpal_schedules", _Dispatches(explode=True))
    _no_ledger(monkeypatch, days=SEVEN_MEETS_DAYS, why="seven")

    async def _standby(sport_key):
        return FIXTURES

    monkeypatch.setattr(espn_sync, "_statpal_standby_reading", _standby)

    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers({}, {"americanfootball_nfl"}, stats), stats
    )

    assert stats["failover_activated"] == 1
    assert stats.get("failover_dispatched", 0) == 0
    assert any("failover_dispatch_" in e for e in stats["errors"])
    # The receipt still says a failover was decided — the decision is a fact
    # about the providers, and the broker's mood does not change it.
    assert stats["failover"][0]["code"] == FAILOVER_ESPN_DARK


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
        return DARK

    monkeypatch.setattr(espn_sync, "_statpal_standby_reading", _standby)

    stats = {"errors": []}
    await _act_on_failovers(
        await _decide_failovers({}, {"americanfootball_nfl"}, stats), stats
    )

    assert dispatches.calls == []
    assert stats["failover"][0]["code"] == STANDBY_DARK


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
            return ["a fixture"]

        async def get_fixtures(self, *a, **k):  # pragma: no cover - must not run
            raise AssertionError(
                "the standby was read through `get_fixtures`, which cannot "
                "distinguish an outage from an empty slate"
            )

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    assert await _statpal_standby_reading(NFL) == FIXTURES
    assert calls == ["schedule:nfl"]


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

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    assert await _statpal_standby_reading(NFL) == DARK


@pytest.mark.asyncio
async def test_an_unmapped_or_keyless_standby_is_dark_not_empty(monkeypatch):
    """We did not ask, so StatPal has said nothing — and our own silence must
    never be published as theirs."""
    import app.services.statpal_api as statpal_api
    from app.tasks.espn_sync import _statpal_standby_reading

    monkeypatch.setattr(statpal_api, "is_available", lambda: False)
    assert await _statpal_standby_reading(NFL) == DARK

    monkeypatch.setattr(statpal_api, "is_available", lambda: True)
    assert await _statpal_standby_reading("quidditch_premier") == DARK


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
