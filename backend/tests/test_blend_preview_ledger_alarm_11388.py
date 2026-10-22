"""#11388 — a rejected two-source ledger update is never silent.

SHIP: broader live delivery can stop safely when an update is rejected. The
admission review (artifacts/latency-11388-redis-cost-gate-85be05f092/
ADMISSION-REVIEW.md, item 4) requires a bounded, fixed-shape warning for every
ledger authority failure — fenced, lost, malformed, exhausted — in the
mutation and publication paths, plus the admission refusals full and no_base,
so the operator can stop on the first. Supersession (stale, terminal) and
expiry are normal and must stay quiet.

The real-Redis cases reuse the TSP-1 rig (same private server rules); the
batching and throttle cases drive `LedgerRegistry` with a scripted ``call``.
"""

from __future__ import annotations

import logging
import re

import pytest

from app.utils import blend_preview
from tests import test_blend_preview_ledger_tsp1_10090 as tsp1
from tests.test_blend_preview_ledger_tsp1_10090 import EV, SOURCES, _blends, _propose

#: The TSP-1 rig's fixtures, shared: one private Redis, two venue registries.
redis_kwargs, rig = tsp1.redis_kwargs, tsp1.rig

LOGGER = "app.utils.blend_preview"
#: What the operator's immediate-stop matcher is handed. Searched, not anchored:
#: production prefixes every line.
OPERATOR_PATTERN = re.compile(
    r"blend_preview ledger ALARM status=(fenced|lost|malformed|exhausted|full|no_base|lost_admission)"
    r" phase=(claim|read_ticket|propose|settle|terminal|retire|publish) source=(kalshi|polymarket)"
    r" count=([1-9][0-9]*) event_id=([0-9]+|-)$"
)


def _alarms(caplog):
    lines = [r.getMessage() for r in caplog.records
             if r.name == LOGGER and r.levelno == logging.WARNING and "ALARM" in r.getMessage()]
    for line in lines:
        assert OPERATOR_PATTERN.search(line), line
    return [OPERATOR_PATTERN.search(line).groups() for line in lines]


@pytest.fixture(autouse=True)
def _warnings(caplog):
    caplog.set_level(logging.WARNING, logger=LOGGER)


def test_the_format_and_status_set_are_the_ones_handed_to_the_operator():
    assert blend_preview.LEDGER_ALARM_FORMAT == (
        "blend_preview ledger ALARM status=%s phase=%s source=%s count=%d event_id=%s")
    assert blend_preview.LEDGER_ALARM_STATUSES == frozenset(
        {"fenced", "lost", "malformed", "exhausted", "full", "no_base", "lost_admission"})
    assert blend_preview.LEDGER_ALARM_INTERVAL_S == 10.0


# ------------------------------------------------------------ real Redis


class TestMutation:
    async def test_a_superseded_owner_is_fenced_and_says_so(self, rig, caplog):
        await rig.registry().claim(rig.call, "kalshi")  # a replacement worker
        assert await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6)) == []
        assert rig.stats["fenced"] == 1
        assert _alarms(caplog) == [("fenced", "propose", "kalshi", "1", str(EV))]

    async def test_a_lost_ledger_alarms_on_the_write_and_on_the_reclaim(self, rig, caplog):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        await rig.client.delete(blend_preview.LEDGER_KEY)
        assert await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2)) == []
        with pytest.raises(RuntimeError, match="lost"):
            await rig.registry().claim(rig.call, "kalshi")
        assert _alarms(caplog) == [("lost", "propose", "polymarket", "1", str(EV)),
                                   ("lost", "claim", "kalshi", "1", "-")]

    async def test_a_malformed_event_field_alarms(self, rig, caplog):
        await rig.client.hset(blend_preview.LEDGER_KEY, f"e:{EV}:seq", "01")
        assert await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6)) == []
        assert rig.stats["ledger_refused"] == 1
        assert _alarms(caplog) == [("malformed", "propose", "kalshi", "1", str(EV))]

    async def test_an_exhausted_claim_alarms(self, rig, caplog):
        await rig.client.hset(blend_preview.LEDGER_KEY, "epoch", "9007199254740991")
        with pytest.raises(RuntimeError, match="exhausted"):
            await rig.registry().claim(rig.call, "kalshi")
        assert _alarms(caplog) == [("exhausted", "claim", "kalshi", "1", "-")]

    async def test_a_full_ledger_refuses_the_new_event_and_says_so(self, rig, caplog, monkeypatch):
        monkeypatch.setattr(blend_preview, "LEDGER_MAX_EVENTS", 1)
        assert _blends(await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6)))
        assert await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6, event_id=EV + 1)) == []
        assert _alarms(caplog) == [("full", "propose", "kalshi", "1", str(EV + 1))]

    async def test_no_committed_base_refuses_and_says_so(self, rig, caplog):
        ops = _propose(rig.k, "kalshi", 0.6)
        [op] = [o for o in ops if o.get("ledger_op") == "propose"]
        op["base_rev"], op["base"] = None, None
        assert await rig.run(rig.k, ops) == []
        assert _alarms(caplog) == [("no_base", "propose", "kalshi", "1", str(EV))]


class TestPublication:
    async def test_an_owner_superseded_between_read_and_send_is_fenced_at_publish(self, rig, caplog):
        frames = await rig.k.prepare(_propose(rig.k, "kalshi", 0.6), rig.call, rig.stats)
        assert _blends(frames)
        await rig.registry().claim(rig.call, "kalshi")
        await rig.k.execute(frames, rig.call, rig.channel, rig.stats)
        assert _blends(await rig.drain()) == []
        assert _alarms(caplog) == [("fenced", "publish", "kalshi", "1", str(EV))]


class TestAdmissionAuthority:
    """F3: a ledger that still has owners but no readable retirement barrier.

    Every operation refuses `lost_admission`, so without a line the window
    would keep running with no previews at all.
    """

    async def test_a_lost_barrier_alarms_on_the_reclaim(self, rig, caplog):
        # (An unreadable one is `malformed` at a claim, already an alarm.)
        await _lose_barrier(rig)
        with pytest.raises(RuntimeError, match="lost_admission"):
            await rig.registry().claim(rig.call, "kalshi")
        assert _alarms(caplog) == [("lost_admission", "claim", "kalshi", "1", "-")]

    async def test_a_lost_barrier_alarms_on_the_ticket_read_with_no_chain_in_flight(self, rig, caplog):
        await _lose_barrier(rig)
        assert await rig.k.read_ticket(rig.call, "kalshi") == (None, [])
        # Without a ticket nothing else reaches the ledger: the read is the only line.
        assert await _tsp1_fresh_ops(rig, rig.k) == []
        assert _alarms(caplog) == [("lost_admission", "read_ticket", "kalshi", "1", "-")]

    @pytest.mark.parametrize("barrier", [None, "01"])
    async def test_a_lost_or_unreadable_barrier_alarms_on_the_write(self, rig, caplog, barrier):
        await _lose_barrier(rig, barrier)
        assert await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6)) == []
        assert rig.stats["ledger_refused"] == 1
        assert _alarms(caplog) == [("lost_admission", "propose", "kalshi", "1", str(EV))]

    async def test_a_barrier_lost_between_read_and_send_alarms_at_publish(self, rig, caplog):
        frames = await rig.k.prepare(_propose(rig.k, "kalshi", 0.6), rig.call, rig.stats)
        assert _blends(frames)
        await _lose_barrier(rig)
        await rig.k.execute(frames, rig.call, rig.channel, rig.stats)
        assert _blends(await rig.drain()) == []
        assert _alarms(caplog) == [("lost_admission", "publish", "kalshi", "1", str(EV))]

    async def test_a_barrier_lost_after_the_ticket_alarms_at_retire(self, rig, caplog):
        await rig.run(rig.k, await _tsp1_fresh_ops(rig, rig.k))
        ticket, _ = await rig.k.read_ticket(rig.call, "kalshi")
        await _lose_barrier(rig)
        assert await rig.run(rig.k, [rig.k.retire_read(EV, "kalshi", 11, ticket, committed_rev=12)]) == []
        assert await rig.hget(f"e:{EV}:gen") is not None
        assert _alarms(caplog) == [("lost_admission", "retire", "kalshi", "1", str(EV))]


class TestAdmissionQuietWhenNormal:
    """The two other F3 refusals are ordinary transitions, counted but quiet."""

    async def test_an_open_read_before_another_venues_retirement_is_read_required(
            self, rig, caplog, monkeypatch):
        seen = _statuses(rig.k, monkeypatch)
        delayed = await _tsp1_fresh_ops(rig, rig.k)
        ticket, _ = await rig.p.read_ticket(rig.call, "polymarket")
        await rig.run(rig.p, [rig.p.retire_read(EV, "polymarket", 11, ticket, committed_rev=12)])
        assert await rig.run(rig.k, delayed) == []
        assert seen == ["read_required"]
        assert rig.stats["ledger_refused"] >= 1
        assert _alarms(caplog) == []

    async def test_a_retirement_on_a_superseded_ticket_is_read_required(self, rig, caplog, monkeypatch):
        await rig.run(rig.p, await _tsp1_fresh_ops(rig, rig.p))
        ticket, _ = await rig.p.read_ticket(rig.call, "polymarket")
        await rig.run(rig.k, [rig.k.retire_read(999, "kalshi", 20, ticket, committed_rev=21)])
        seen = _statuses(rig.p, monkeypatch)
        assert await rig.run(rig.p, [rig.p.retire_read(EV, "polymarket", 11, ticket, committed_rev=12)]) == []
        assert seen == ["read_required"]
        assert await rig.hget(f"e:{EV}:gen") is not None
        assert _alarms(caplog) == []

    async def test_a_venue_without_read_before_admit_makes_retirement_wait_quietly(
            self, rig, caplog, monkeypatch):
        await rig.run(rig.k, await _tsp1_fresh_ops(rig, rig.k))
        await rig.client.hdel(blend_preview.LEDGER_KEY, "read_owner:polymarket")
        ticket, _ = await rig.k.read_ticket(rig.call, "kalshi")
        assert ticket is not None
        seen = _statuses(rig.k, monkeypatch)
        assert await rig.run(rig.k, [rig.k.retire_read(EV, "kalshi", 11, ticket, committed_rev=12)]) == []
        assert seen == ["legacy_owner"]
        assert await rig.hget(f"e:{EV}:gen") is not None
        assert _alarms(caplog) == []


async def _lose_barrier(rig, value=None):
    if value is None:
        await rig.client.hdel(blend_preview.LEDGER_KEY, "retired")
    else:
        await rig.client.hset(blend_preview.LEDGER_KEY, "retired", value)


async def _tsp1_fresh_ops(rig, reg, source=None):
    source = source or ("kalshi" if reg is rig.k else "polymarket")
    return await tsp1._fresh_ops(rig, reg, source)


def _statuses(reg, monkeypatch):
    """Every refusal status the registry passed to its alarm filter."""
    seen, original = [], reg._alarm

    def spy(status, *args):
        seen.append(status)
        original(status, *args)

    monkeypatch.setattr(reg, "_alarm", spy)
    return seen


class TestQuietWhenNormal:
    async def test_a_superseded_read_set_is_not_an_alarm(self, rig, caplog):
        frames = await rig.k.prepare(_propose(rig.k, "kalshi", 0.6), rig.call, rig.stats)
        await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, basis_s=2))
        await rig.k.execute(frames, rig.call, rig.channel, rig.stats)
        assert rig.stats["ledger_superseded"] == 1
        assert _alarms(caplog) == []

    async def test_proposals_behind_a_tombstone_are_not_an_alarm(self, rig, caplog):
        await rig.run(rig.k, _propose(rig.k, "kalshi", 0.6))
        await rig.run(rig.p, _propose(rig.p, "polymarket", 0.7, rev=12, status="final", basis_s=2))
        assert await rig.run(rig.k, _propose(rig.k, "kalshi", 0.61, rev=11, basis_s=3)) == []
        assert rig.stats["ledger_refused"] >= 1  # still counted
        assert _alarms(caplog) == []


# ------------------------------------------------------ batching / bound


class Scripted:
    """A ``call`` answering each EVAL with the next scripted status."""

    def __init__(self, *statuses, fail_after=None):
        self.statuses = list(statuses)
        self.fail_after = fail_after
        self.calls = 0

    async def __call__(self, *args):
        if self.fail_after is not None and self.calls >= self.fail_after:
            raise TimeoutError("cut")
        self.calls += 1
        return [self.statuses.pop(0).encode()]


def _registry(clock):
    reg = blend_preview.LedgerRegistry(sources=SOURCES, max_uncommitted_s=60.0,
                                       clock=lambda: clock[0])
    reg.claims = {"kalshi": 50, "polymarket": 51}
    return reg


def _settle(event_id, source="kalshi"):
    return {"ledger_op": "settle", "mode": "sync", "event_id": event_id, "source": source,
            "through": None, "reason": "expired", "base_rev": None, "base": None}


class TestBound:
    async def test_one_line_per_key_per_batch_with_the_count(self, caplog):
        reg, stats = _registry([0.0]), {}
        call = Scripted("fenced", "fenced", "lost", "fenced")
        await reg.execute([_settle(3), _settle(4), _settle(5), _settle(6, "polymarket")],
                          call, str, stats)
        assert sorted(_alarms(caplog)) == [
            ("fenced", "settle", "kalshi", "2", "3"),
            ("fenced", "settle", "polymarket", "1", "6"),
            ("lost", "settle", "kalshi", "1", "5"),
        ]
        assert stats == {"fenced": 3, "ledger_refused": 1}

    async def test_a_persisting_refusal_repeats_at_most_once_per_interval_and_keeps_count(self, caplog):
        clock = [100.0]
        reg = _registry(clock)
        await reg.prepare([_settle(3)], Scripted("fenced"), {})
        clock[0] = 109.9
        await reg.prepare([_settle(4), _settle(5)], Scripted("fenced", "fenced"), {})
        assert _alarms(caplog) == [("fenced", "settle", "kalshi", "1", "3")]
        clock[0] = 110.0
        await reg.prepare([_settle(6)], Scripted("fenced"), {})
        assert _alarms(caplog) == [("fenced", "settle", "kalshi", "1", "3"),
                                   ("fenced", "settle", "kalshi", "3", "4")]

    async def test_a_batch_cut_by_a_timeout_still_logs_what_it_saw(self, caplog):
        reg = _registry([0.0])
        with pytest.raises(TimeoutError):
            await reg.prepare([_settle(3), _settle(4)], Scripted("malformed", fail_after=1), {})
        assert _alarms(caplog) == [("malformed", "settle", "kalshi", "1", "3")]

    @pytest.mark.parametrize("status", ["stale", "terminal", "missing_chain",
                                        "old_local", "chain_exists", "contributor",
                                        "stale_terminal", "unchanged", "none",
                                        "read_required", "legacy_owner"])
    async def test_normal_refusals_are_quiet(self, caplog, status):
        reg = _registry([0.0])
        await reg.prepare([_settle(3)], Scripted(status), {})
        assert _alarms(caplog) == []


class TestTicketRead:
    async def test_a_refused_ticket_read_alarms_once_per_interval(self, caplog):
        clock = [0.0]
        reg = _registry(clock)
        assert await reg.read_ticket(Scripted("lost_admission"), "kalshi") == (None, [])
        assert await reg.read_ticket(Scripted("lost_admission"), "kalshi") == (None, [])
        clock[0] = 10.0
        assert await reg.read_ticket(Scripted("lost_admission"), "kalshi") == (None, [])
        assert _alarms(caplog) == [("lost_admission", "read_ticket", "kalshi", "1", "-"),
                                   ("lost_admission", "read_ticket", "kalshi", "2", "-")]

    async def test_an_unclaimed_source_reads_no_ticket_and_says_nothing(self, caplog):
        reg = _registry([0.0])
        reg.claims = {}
        call = Scripted()
        assert await reg.read_ticket(call, "kalshi") == (None, [])
        assert call.calls == 0
        assert _alarms(caplog) == []
