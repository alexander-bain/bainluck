"""A D104-ruled sport's failover survives the MONITOR being unreadable. #4443.

Named as a non-blocking follow-up by CERT-2393 on the D104 football ship
(#4417), measured on master, and real.

THE DEFECT
----------
`espn_sync._decide_failovers` read the durable ledger and forced the gate shut
whenever the read failed, *before* `flip_permitted` was ever consulted::

    days, ledger_why = await read_ledger_days(sport_key)
    gate = (False, ledger_why) if days is None else flip_permitted(sport_key, days)

The in-line comment called this deliberate — "an outage in the snapshot store
can never open this gate" — and **that reasoning was correct before D104 and is
not correct after it.** Before D104 the ledger WAS the evidence, so no ledger
honestly meant no permission. After D104 the ledger is a MONITOR for a ruled
sport: Alex retired the proof days and kept the daily fold running as an
observation. Refusing football because the monitor's store is degraded refuses
on the monitor rather than on evidence.

WHY IT IS WORTH FIXING RATHER THAN NOTING
-----------------------------------------
It needs two things at once — ESPN dark for football AND the snapshot store
unavailable. Those are not independent events: one broad infrastructure
incident produces both. That is precisely the hour D104 exists for, and the
hour in which football would otherwise go blank.

THE PROPERTY THAT MAKES THE FIX NARROW, AND THE ONE THIS FILE MOST WANTS PINNED
-------------------------------------------------------------------------------
`flip_permitted(key, [])` can return `True` for a **ruled sport and nothing
else**. Every other route to `True` in that function runs through
`compute_streak`, and an empty ledger yields `streak is None`, which refuses.
So "ask the gate with an empty ledger" is not a weakening of the gate — it is
the gate, asked about a sport whose permission no longer depends on days.

That is why the fix is *not* `if ruled: gate = (True, ...)`. A second copy of
"which sports are exempt" in the caller is exactly the drift `flip_permitted`
exists to prevent. The caller asks; the gate still answers.

`test_an_unreadable_ledger_cannot_open_the_gate_for_an_unruled_sport` is the
control that stops this ship becoming "an unreadable ledger opens the gate",
and `test_only_a_ruled_sport_can_pass_the_gate_on_an_empty_ledger` pins the
property directly against every sport we measure, so the day a fifth sport is
added the assumption is re-checked rather than assumed.
"""

from datetime import datetime, timedelta, timezone

import pytest

import app.config.authority_by_sport as switch
from app.utils.authority_agreement import SHADOW_STAMPERS

# Reused rather than re-cut: one rail for this path, so a change to the
# sqlite/session shim cannot leave two test files describing different worlds.
from tests.test_authority_failover_3473 import (  # noqa: F401 — `dispatches` is a fixture
    NFL,
    _Fx,
    _live,
    _wire_sqlite,
    dispatches,
)

#: A sport D104 has NOT ruled, so its refusal must still carry the ledger's own
#: failed-read reason. Moved from `basketball_nba` to `icehockey_nhl` when the
#: NBA shipped as the second ruled release (#4493) — the specimen moves, the
#: test stays, exactly as `STILL_GATED` in `test_authority_failover_3473` has
#: now done twice.
UNRULED = "icehockey_nhl"

#: What `read_ledger_days` hands back when the snapshot store cannot be read.
#: `None` for the days — NOT `[]`. The distinction is the whole defect: `[]` is
#: "measured, nothing there", `None` is "we could not look".
UNREADABLE = None
UNREADABLE_WHY = "could not read authority-agreement-ledger: redis timeout"


def _ledger_unreadable(monkeypatch):
    """Make the durable ledger read FAIL, the way a degraded store fails."""
    import app.services.authority_ledger as ledger

    async def _read(sport_key):
        return UNREADABLE, UNREADABLE_WHY

    monkeypatch.setattr(ledger, "read_ledger_days", _read)


# ── The property the fix rests on ──────────────────────────────────────────


def test_only_a_ruled_sport_can_pass_the_gate_on_an_empty_ledger():
    """The safety property, asserted over every sport we measure.

    The fix asks `flip_permitted(key, [])` when the ledger cannot be read. That
    is only sound if an empty ledger cannot permit an UNRULED sport — otherwise
    a degraded snapshot store would become a way to flip anything. Pinned here
    against the real sport list rather than the two keys the tests below use,
    so adding a fifth measured sport re-checks the assumption.
    """
    permitted_on_empty = {
        key for key in sorted(SHADOW_STAMPERS) if switch.flip_permitted(key, [])[0]
    }

    assert permitted_on_empty <= set(switch.FLIP_RULED_WITHOUT_STREAK), (
        "a sport outside FLIP_RULED_WITHOUT_STREAK was permitted on an EMPTY "
        "ledger, so asking the gate with `[]` when the monitor is unreadable "
        f"would open it for a sport with no ruling: {sorted(permitted_on_empty)}"
    )
    assert permitted_on_empty, (
        "no sport at all passes the gate on an empty ledger, so the fix below "
        "cannot be doing anything — check FLIP_RULED_WITHOUT_STREAK is populated"
    )


# ── The fix, at the gate ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_ruled_sport_still_fails_over_when_the_monitor_cannot_be_read(
    monkeypatch,
):
    """THE SHIP. ESPN dark for football + the snapshot store down ⇒ still serves.

    This is the assertion that was red on master: the gate was forced shut by
    the failed read and football was reported as ungated, identically to a
    sport with no ruling at all.
    """
    import app.tasks.espn_sync as espn_sync
    from app.utils import authority_failover as failover

    _ledger_unreadable(monkeypatch)

    async def _standby(sport_key):
        return failover.FIXTURES, failover.FIXTURES

    monkeypatch.setattr(espn_sync, "_statpal_standby_reading", _standby)

    decisions = await espn_sync._decide_failovers({}, {NFL}, {"errors": []})

    assert decisions[NFL].code == failover.FAILOVER_ESPN_DARK, (
        "football did not fail over with an unreadable monitor — got "
        f"{decisions[NFL].code}: {decisions[NFL].why}"
    )


@pytest.mark.asyncio
async def test_the_reported_reason_names_both_the_ruling_and_the_failed_read(
    monkeypatch,
):
    """The degraded read stays VISIBLE — it is ignored as authority, not hidden.

    A gate that opened while silently discarding `ledger_why` would make a
    monitor outage indistinguishable from a healthy monitor in every receipt we
    keep. The point of D104 is that the read no longer DECIDES, not that it no
    longer happened.
    """
    import app.tasks.espn_sync as espn_sync
    from app.utils import authority_failover as failover

    _ledger_unreadable(monkeypatch)

    async def _standby(sport_key):
        return failover.FIXTURES, failover.FIXTURES

    monkeypatch.setattr(espn_sync, "_statpal_standby_reading", _standby)

    why = (await espn_sync._decide_failovers({}, {NFL}, {"errors": []}))[NFL].why

    assert "D104" in why, f"the ruling is not named in the receipt: {why}"
    assert UNREADABLE_WHY in why, (
        "the failed monitor read was dropped from the receipt, so a snapshot "
        f"outage is invisible in the record: {why}"
    )


@pytest.mark.asyncio
async def test_an_unreadable_ledger_cannot_open_the_gate_for_an_unruled_sport(
    monkeypatch,
):
    """THE CONTROL. Without this the ship is "an outage opens the gate".

    An unruled sport keeps today's behaviour byte for byte: refused, carrying
    the ledger's own reason rather than a streak verdict it never computed.
    """
    import app.tasks.espn_sync as espn_sync
    from app.utils import authority_failover as failover

    _ledger_unreadable(monkeypatch)

    decisions = await espn_sync._decide_failovers({}, {UNRULED}, {"errors": []})

    assert decisions[UNRULED].code != failover.FAILOVER_ESPN_DARK, (
        "an unruled sport failed over on an unreadable ledger — the fix has "
        "become 'a degraded snapshot store opens the gate'"
    )
    assert UNREADABLE_WHY in decisions[UNRULED].why, (
        "an unruled sport's refusal stopped carrying the ledger's own reason, "
        f"which is a change to today's wording: {decisions[UNRULED].why}"
    )


@pytest.mark.asyncio
async def test_a_readable_ledger_is_still_the_thing_the_gate_reads(monkeypatch):
    """The unchanged path, so the fix is a NEW branch and not a replacement.

    A healthy monitor must still reach `flip_permitted` with its real days —
    mutation bait otherwise: hard-wiring the empty-ledger call for every read
    would pass every other test in this file.
    """
    import app.services.authority_ledger as ledger
    import app.tasks.espn_sync as espn_sync
    from app.utils import authority_failover as failover
    from tests.test_authority_failover_3473 import SEVEN_MEETS_DAYS

    seen: list[object] = []

    async def _read(sport_key):
        return SEVEN_MEETS_DAYS, "seven"

    monkeypatch.setattr(ledger, "read_ledger_days", _read)

    real_gate = espn_sync.__dict__.get("flip_permitted")
    assert real_gate is None, (
        "`flip_permitted` is now a module global; this spy must be re-pointed"
    )

    original = switch.flip_permitted

    def _spy(sport_key, days):
        seen.append(list(days))
        return original(sport_key, days)

    monkeypatch.setattr(switch, "flip_permitted", _spy)

    async def _standby(sport_key):
        return failover.FIXTURES, failover.FIXTURES

    monkeypatch.setattr(espn_sync, "_statpal_standby_reading", _standby)

    await espn_sync._decide_failovers({}, {NFL}, {"errors": []})

    assert seen == [SEVEN_MEETS_DAYS], (
        "the gate was not handed the ledger's real days on a healthy read — "
        f"got {seen}"
    )


# ── CERT-2393's second half: the ACTOR, not the verdict ────────────────────


@pytest.mark.asyncio
async def test_the_failover_actually_writes_when_the_monitor_is_unreadable(
    monkeypatch, dispatches  # noqa: F811 — the imported fixture, bound by pytest
):
    """End to end: a `serving` verdict is not a write, so assert the WRITE.

    authority/085 caught exactly this shape in the standing-switch route
    (#4434) — `decide` returning `serving=statpal` while nothing wrote. CERT-2393
    asked for this guard by name. So this asserts both StatPal writers REACHED
    the service, not merely that their counters moved: mutation on the sibling
    file showed that stubbing `_sync_statpal_schedules` out entirely still left
    `failover_schedule_writes == 1` and every counter assertion green.
    """
    import app.services.statpal_api as statpal_api

    import app.tasks.espn_sync as espn_sync

    _wire_sqlite(monkeypatch)
    _ledger_unreadable(monkeypatch)
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    now = datetime.now(timezone.utc)
    live_row = _live(now - timedelta(hours=1))
    live_row.fixture_id = "sp-1"

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
    await espn_sync._act_on_failovers(
        await espn_sync._decide_failovers({}, {NFL}, stats), stats
    )

    assert stats["failover_serving"] == 1
    assert stats["errors"] == []

    # The writers REACHED StatPal — the counters alone do not prove this.
    assert "writer:schedules" in reached, (
        "`_sync_statpal_schedules` never called the service, so the schedule "
        f"half did not run with an unreadable monitor. Reached: {reached}"
    )
    assert "writer:livescores" in reached, (
        f"`_sync_statpal_livescores` never called the service. Reached: {reached}"
    )

    # And still nothing goes to a queue (the CERT-2050 refusal stands).
    assert dispatches.calls == []
    assert dispatches.live.calls == []
