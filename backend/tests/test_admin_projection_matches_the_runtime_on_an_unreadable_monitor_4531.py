"""The admin failover projection must not contradict the runtime it discloses. #4531.

Named as a non-blocking follow-up by CERT-2413 when it granted #4493's token
(`4493-ADMIN-PROJECTION-MATCHES-UNREADABLE-MONITOR`), filed by `authority/090`,
measured on master, and real.

THE DEFECT
----------
`GET /api/admin/statpal/authority-agreement` answers *"if ESPN went dark for
this sport right now, would anything happen?"*, and its own comment says why it
is built the way it is::

    Answered by running the REAL decision function against the most favourable
    hypothetical … so it cannot disagree with what would actually happen. A
    second reading of the same rules, written here, is a disclosure that drifts.

It honoured that for `flip_permitted` and broke it one line earlier, building
the gate's ARGUMENT itself::

    days, ledger_why = await read_ledger_days(sport_key)
    gate = (False, ledger_why) if days is None else flip_permitted(sport_key, days)

When the monitor's snapshot store is unreadable (`days is None`) the D104 bypass
inside `flip_permitted` was never reached, so the row reported
`would_fire_if_espn_went_dark: false` for a RULED sport — while the runtime,
since #4443, fails over anyway. The disclosure contradicting the behaviour it
discloses, in the one place a human is meant to check before ruling on a flip.

It needs ESPN dark AND the snapshot store degraded at the same time. Those are
not independent events — one broad incident produces both — so the wrong answer
appears exactly in the hour D104 exists for.

THE SHAPE, WHICH IS THE REUSABLE PART
-------------------------------------
"A ruling that retires a requirement leaves its scaffolding refusing." D104
retired the streak's authority for ruled sports; this call site still gated on
the ledger being *readable at all*. The fix is not a second `if ruled:` in the
route — that is the very drift `flip_permitted` exists to prevent. **The gate is
BOTH lines**: `flip_permitted` plus how its argument is built when the ledger
will not read. So the second half moved into
`utils.authority_failover.gate_on_unreadable_ledger`, beside
`would_fail_over_now` where the discloser already looks, and both the runtime
and the disclosure ask it.

WHY THE STRUCTURAL GUARD BELOW IS `ast` AND NOT A GREP
------------------------------------------------------
Two independent reasons, and the first is the one that would have bitten:

* the route now carries a COMMENT quoting the retired `(False, ledger_why)`
  line, so a source scan for that text matches the fix's own prose and reports
  the defect present forever after it is gone — a guard blinded by its target's
  own documentation;
* "the disclosure is DERIVED from the shared gate" is a claim about an
  assignment, and a value comparison cannot grade a derivation. Two functions
  agreeing on today's inputs does not make one call the other.

WHY THE VERDICT ALONE CANNOT BE THE ASSERTION
---------------------------------------------
For an unruled sport the wrong answer and the right answer are BOTH `false`.
Only the ruled sport separates them on the verdict, and only the `why` separates
a refusal that consulted the gate from one that short-circuited. So every test
here asserts the reason as well.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

import app.config.authority_by_sport as switch
from app.utils.authority_agreement import SHADOW_STAMPERS

# Reused rather than re-cut, so the endpoint's shim cannot drift between files.
# Re-exported by assignment rather than imported by name: `call` is a fixture
# AND a parameter of every test below, and an import binding shadowed by a
# parameter reads to the linter as a redefinition.
from tests import test_authority_agreement_endpoint as _endpoint

FakeSession = _endpoint.FakeSession
call = _endpoint.call

#: D104-ruled: the failover may fire with no streak, so an unreadable MONITOR
#: must not refuse it.
RULED = "americanfootball_nfl"

#: NOT ruled, so its refusal must survive unchanged — and must still carry the
#: ledger's own failed-read reason rather than a streak verdict never computed.
#: Kept in step with `UNRULED` in
#: `test_ruled_failover_survives_monitor_read_failure_4443`; when the NHL ships
#: as the third ruled release this specimen moves, and #4531's own note about
#: the shrinking pool of unruled controls applies here too.
UNRULED = "icehockey_nhl"

#: `None` for the days — NOT `[]`. That distinction is the whole defect: `[]` is
#: "measured, nothing there"; `None` is "we could not look".
UNREADABLE = None
UNREADABLE_WHY = "could not read authority-agreement-ledger: redis timeout"


def _ledger_unreadable(monkeypatch):
    """Make the durable ledger read FAIL, the way a degraded store fails."""
    import app.services.authority_ledger as ledger

    async def _read(sport_key):
        return UNREADABLE, UNREADABLE_WHY

    monkeypatch.setattr(ledger, "read_ledger_days", _read)


def _ledger_readable(monkeypatch, days=()):
    """A monitor that answers. `[]` is a real, successful, empty measurement."""
    import app.services.authority_ledger as ledger

    async def _read(sport_key):
        return list(days), "read ok"

    monkeypatch.setattr(ledger, "read_ledger_days", _read)


async def _failover_rows(call):
    """`{sport_key: failover-block}` from a live call to the real endpoint."""
    out = await call(metrics={}, session=FakeSession())
    return {s["sport_key"]: s["authority"]["failover"] for s in out["sports"]}


# ── The ship ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_ruled_sport_is_projected_to_fail_over_when_the_monitor_is_dark(
    monkeypatch, call
):
    """THE ASSERTION THAT WAS RED ON MASTER.

    Football is ruled, the runtime fails it over on an unreadable monitor
    (#4443), and the admin projection said it would not.
    """
    _ledger_unreadable(monkeypatch)

    row = (await _failover_rows(call))[RULED]

    assert row["would_fire_if_espn_went_dark"] is True, (
        "the admin projection says a D104-RULED sport would not fail over while "
        "the monitor is unreadable, but the runtime fails it over — the "
        "disclosure is contradicting the behaviour it discloses. "
        f"code={row['code']!r} why={row['why']!r}"
    )


@pytest.mark.asyncio
async def test_the_projection_still_reports_the_failed_read_it_ignored(
    monkeypatch, call
):
    """Ignoring the monitor as an AUTHORITY is the ruling; hiding it is not.

    Dropping the failed read from the receipt would make a degraded store
    indistinguishable from a healthy one on the surface an operator reads.
    """
    _ledger_unreadable(monkeypatch)

    row = (await _failover_rows(call))[RULED]

    assert UNREADABLE_WHY in row["why"], (
        "the projection permitted the ruled sport but dropped the monitor's own "
        f"failed-read reason from the receipt: {row['why']!r}"
    )


# ── The control, which is the half that keeps this from being a weakening ───


@pytest.mark.asyncio
async def test_an_unreadable_monitor_does_not_open_the_projection_for_an_unruled_sport(
    monkeypatch, call
):
    """A degraded snapshot store must not become a way to project anything."""
    _ledger_unreadable(monkeypatch)

    row = (await _failover_rows(call))[UNRULED]

    assert row["would_fire_if_espn_went_dark"] is False, (
        f"{UNRULED} has no D104 ruling, so an unreadable monitor must not "
        "project a failover for it"
    )
    assert UNREADABLE_WHY in row["why"], (
        "the unruled refusal must carry the LEDGER's own failed-read reason "
        "rather than a streak verdict that was never computed — both the right "
        f"and the wrong answer are `false` here, so the reason is the test: {row['why']!r}"
    )


@pytest.mark.asyncio
async def test_only_ruled_sports_are_projected_to_fire_on_an_unreadable_monitor(
    monkeypatch, call
):
    """The safety property over every sport the endpoint publishes, not two keys.

    Adding an eighth measured sport re-checks the assumption instead of
    inheriting it.
    """
    _ledger_unreadable(monkeypatch)

    rows = await _failover_rows(call)
    fired = {k for k, v in rows.items() if v["would_fire_if_espn_went_dark"]}

    assert fired <= set(switch.FLIP_RULED_WITHOUT_STREAK), (
        "a sport outside FLIP_RULED_WITHOUT_STREAK is projected to fail over on "
        f"an unreadable monitor: {sorted(fired - set(switch.FLIP_RULED_WITHOUT_STREAK))}"
    )
    assert fired, (
        "no sport at all is projected to fire, so this file cannot be measuring "
        "the fix — check FLIP_RULED_WITHOUT_STREAK is populated and reached"
    )


# ── The readable path, which must not have moved ────────────────────────────


@pytest.mark.asyncio
async def test_the_projection_is_unchanged_for_every_sport_when_the_monitor_reads(
    monkeypatch, call
):
    """Acceptance bullet 4: the seven-row projection is untouched on the happy path.

    A readable-but-empty ledger is the sharpest version — it is the input the
    unreadable branch now *simulates*, so if the two branches had been collapsed
    into one this would still pass while the control above failed. Pinned
    against the gate's own answer for each sport.
    """
    _ledger_readable(monkeypatch, days=[])

    rows = await _failover_rows(call)

    for key in sorted(SHADOW_STAMPERS):
        expected_permitted, _ = switch.flip_permitted(key, [])
        assert rows[key]["would_fire_if_espn_went_dark"] == expected_permitted, (
            f"{key}'s projection on a READABLE ledger no longer matches "
            "`flip_permitted`'s own answer, so the fix to the unreadable branch "
            "changed the branch that was already right"
        )
        assert UNREADABLE_WHY not in rows[key]["why"], (
            f"{key} carries an unreadable-monitor note on a ledger that read fine"
        )


# ── The argument the soundness proof is about ───────────────────────────────


def test_the_shared_gate_asks_flip_permitted_with_an_EMPTY_ledger():
    """Found by a surviving mutant: `flip_permitted(key, [None])` passed everything.

    The helper is only sound because of a property proven about ONE argument —
    `test_only_a_ruled_sport_can_pass_the_gate_on_an_empty_ledger` (#4443) pins
    that `flip_permitted(key, [])` can permit a ruled sport and nothing else.
    Every other route to `True` runs through `compute_streak`, which refuses on
    an empty ledger.

    Nothing pinned that the helper actually passes `[]`. Swapping it for a
    non-empty list left all fourteen tests green — the call site inheriting a
    soundness proof it no longer satisfies, which is the "mutate the wiring, not
    the logic" gap. So the argument itself is asserted here, by spying on the
    real call rather than by reading the source.
    """
    from app.utils import authority_failover

    seen = []

    def _spy(sport_key, ledger_days):
        seen.append((sport_key, list(ledger_days)))
        return False, "spied"

    original = authority_failover.flip_permitted
    authority_failover.flip_permitted = _spy
    try:
        authority_failover.gate_on_unreadable_ledger(RULED, UNREADABLE_WHY)
    finally:
        authority_failover.flip_permitted = original

    assert seen == [(RULED, [])], (
        "the unreadable-ledger gate did not ask `flip_permitted` with an EMPTY "
        "ledger. Only `[]` carries the proof that this cannot open the gate for "
        f"an unruled sport, so any other argument is unproven: {seen!r}"
    )


# ── The structural guard: the short-circuit may not come back ───────────────


def _gate_assignment_source(func) -> ast.Assign:
    """The `gate = …` assignment inside `func`, parsed — never grepped."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    assigns = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "gate" for t in node.targets
        )
    ]
    assert assigns, f"no `gate = …` assignment found in {func.__qualname__}"
    return assigns


def _called_names(node: ast.AST) -> set[str]:
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


def test_the_route_builds_its_gate_by_CALLING_the_shared_helper():
    """The derivation, asserted on the parsed assignment.

    A value comparison cannot grade "the disclosure uses the runtime's gate" —
    two functions can agree on today's inputs without one calling the other. And
    a source scan cannot do it either: the route's own comment quotes the
    retired `(False, ledger_why)` line, so a grep for the defect matches the fix.
    """
    from app.routes import admin_providers

    assigns = _gate_assignment_source(admin_providers.statpal_authority_agreement)
    called = set().union(*(_called_names(a.value) for a in assigns))

    assert "gate_on_unreadable_ledger" in called, (
        "the admin projection no longer builds its gate by calling "
        "`gate_on_unreadable_ledger`, so it has gone back to answering the "
        "unreadable-monitor case with a second copy of the rules. "
        f"calls found: {sorted(called)}"
    )
    assert "flip_permitted" in called, (
        "the readable branch must still ask `flip_permitted` directly; "
        f"calls found: {sorted(called)}"
    )


def test_no_gate_assignment_short_circuits_on_a_bare_constant():
    """The specific regression: `(False, ledger_why)` written at the call site.

    Catches the short-circuit returning in either caller, in whatever variable
    name it wears, by looking for a literal `False` used as the first element of
    a gate tuple rather than for the retired text.
    """
    from app.routes import admin_providers
    import app.tasks.espn_sync as espn_sync

    for func in (
        admin_providers.statpal_authority_agreement,
        espn_sync._decide_failovers,
    ):
        for assign in _gate_assignment_source(func):
            for tup in ast.walk(assign.value):
                if not isinstance(tup, ast.Tuple) or not tup.elts:
                    continue
                first = tup.elts[0]
                assert not (
                    isinstance(first, ast.Constant) and first.value is False
                ), (
                    f"{func.__qualname__} assigns `gate` from a hardcoded "
                    "`(False, …)` tuple — that is the D104-retired short-circuit, "
                    "and it must come from `gate_on_unreadable_ledger` so the "
                    "runtime and the disclosure cannot drift apart"
                )


def test_there_is_exactly_one_copy_of_the_unreadable_gate():
    """Both callers reach the same object, so neither can be fixed alone."""
    from app.routes import admin_providers  # noqa: F401 — import side effect only
    from app.tasks import espn_sync  # noqa: F401
    from app.utils import authority_failover

    assert hasattr(authority_failover, "gate_on_unreadable_ledger"), (
        "the shared gate has moved or been renamed; both callers must follow it"
    )
    assert not hasattr(espn_sync, "_gate_on_unreadable_ledger"), (
        "`espn_sync` has grown its own private copy of the unreadable-ledger "
        "gate again — that is the drift #4531 was filed for"
    )
