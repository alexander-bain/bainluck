"""Protected DNPL reservations on the existing TSP-1 real Redis harness."""

from datetime import timedelta
from types import SimpleNamespace
import pytest
from app.utils import blend_preview as bp
from app.utils.preview_reservations import ReservationPolicy
from tests.test_blend_preview_ledger_tsp1_10090 import (
    BASE10,
    NOW,
    SOURCES,
    Reader,
    _blends,
    redis_kwargs as _redis_fixture,
    rig as _rig_fixture,
)  # noqa: F401

# Imported fixture objects remain available under the harness names.
rig = _rig_fixture
redis_kwargs = _redis_fixture

T1 = "americanfootball_nfl"
T2 = "basketball_wnba"
OTHER = "new_unknown_league"


def context(*, sport=OTHER, status="live", at=0, start=None, ticket=0):
    return SimpleNamespace(
        sport_key=sport,
        status=status,
        commence_time=start,
        completed_at=None,
        preview_context_at=NOW + timedelta(seconds=at),
        preview_read_ticket=ticket,
        espn_win_prob_home=None,
        opening_home_probability=None,
    )


async def deadline(rig):
    _, _, _, now = await rig.k.capacity_ticket(rig.call, "kalshi")
    return now + 1000


async def ops(
    r,
    reg,
    source,
    eid,
    *,
    sport=OTHER,
    status="live",
    at=0,
    start=None,
    value=0.60,
    rev=10,
    basis=1,
):
    ticket, _ = await reg.read_ticket(r.call, source)
    return reg.propose(
        eid,
        source,
        value=value,
        event=context(sport=sport, status=status, at=at, start=start, ticket=ticket),
        row_sources=BASE10,
        row_rev=rev,
        observed_basis={source + "-1": NOW.timestamp() - 30 + basis},
        stamped_at=NOW + timedelta(seconds=basis),
    )


async def prepare(r, reg, source, eid, **kwargs):
    return await reg.prepare(await ops(r, reg, source, eid, **kwargs), r.call, r.stats)


async def classify(r, eid, *, sport=OTHER, status="live", at=1, start=None, rev=10):
    ticket, _ = await r.k.read_ticket(r.call, "kalshi")
    op = r.k.classify(
        eid,
        "kalshi",
        context(sport=sport, status=status, at=at, start=start),
        rev,
        ticket,
    )
    return await r.k.prepare([op], r.call, r.stats)


@pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
async def test_lower_fill_t1_admitted_t2_protected_unique_event_ids(rig):
    for eid in range(1, 49):
        assert _blends(await prepare(rig, rig.k, "kalshi", eid))
    for eid in range(49, 65):
        assert _blends(
            await prepare(
                rig,
                rig.k,
                "kalshi",
                eid,
                status="scheduled",
                start=NOW + timedelta(hours=1),
            )
        )
    assert not _blends(await prepare(rig, rig.p, "polymarket", 65))
    assert await rig.hget("e:65:gen") is None
    [held] = _blends(await prepare(rig, rig.k, "kalshi", 1000, sport=T1))
    [held] = _blends(await rig.run(rig.k, [held]))
    reader = Reader()
    reader.after(held, 1_000_000)
    before = await rig.hget("e:1000:m:kalshi")
    assert _blends(await prepare(rig, rig.p, "polymarket", 1000, sport=T1, value=0.62))
    assert _blends(await prepare(rig, rig.k, "kalshi", 2000, sport=T2))
    for key, value in {
        "r:count:0": "1",
        "r:count:2": "1",
        "r:count:4": "48",
        "r:count:5": "16",
        "nevents": "66",
    }.items():
        assert await rig.hget(key) == value
    assert await rig.hget("e:1000:m:kalshi") == before
    assert reader.held["expires"] == 1_060_000


@pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
async def test_real_t1_overload_keeps_held_preview_and_t2_headroom(rig):
    for eid in range(1, 193):
        assert _blends(await prepare(rig, rig.k, "kalshi", eid, sport=T1))
    before = await rig.hget("e:1:m:kalshi")
    assert not await ops(rig, rig.k, "kalshi", 193, sport=T1)
    assert not _blends(await prepare(rig, rig.p, "polymarket", 194, sport=T1))
    assert await rig.hget("e:194:gen") is None
    assert await rig.hget("e:1:m:kalshi") == before
    assert len(rig.k._events) == 192
    assert _blends(await prepare(rig, rig.p, "polymarket", 195, sport=T2))


@pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
async def test_full_active_transition_retains_charge_transfers_once_and_fences_stale_context(
    rig,
):
    for eid in range(1, 193):
        assert _blends(await prepare(rig, rig.k, "kalshi", eid, sport=T1))
    assert _blends(
        await prepare(
            rig,
            rig.k,
            "kalshi",
            300,
            sport=T1,
            status="scheduled",
            start=NOW + timedelta(hours=1),
        )
    )
    assert _blends(
        await prepare(rig, rig.k, "kalshi", 300, sport=T1, at=1, basis=2, value=0.61)
    )
    assert await rig.hget("e:300:r_bucket") == "1"
    assert await rig.hget("e:300:r_target") == "0"
    assert rig.k._events[300].reservation_bucket == 1
    assert rig.k._events[300].reservation_target == 0
    assert not await ops(
        rig,
        rig.k,
        "kalshi",
        300,
        sport=T1,
        status="scheduled",
        start=NOW + timedelta(hours=1),
    )
    await rig.k.prepare(rig.k.refused(1, "kalshi", "settled"), rig.call, rig.stats)
    ticket, _ = await rig.k.read_ticket(rig.call, "kalshi")
    op = rig.k.retire_policy(1, "kalshi", context(sport=T1, at=2), 10, ticket, await deadline(rig))
    assert await rig.k.prepare([op], rig.call, rig.stats)
    await classify(rig, 300, sport=T1, at=3)
    await classify(rig, 300, sport=T1, at=3)
    assert await rig.hget("e:300:r_bucket") == "0"
    assert await rig.hget("r:count:0") == "192"
    assert await rig.hget("r:count:1") == "0"
    await classify(
        rig, 300, sport=T1, at=0, status="scheduled", start=NOW + timedelta(hours=1)
    )
    assert await rig.hget("e:300:r_bucket") == "0"


def test_local_policy_protects_expiry_evidence_on_all_allocation_paths():
    r = bp.LedgerRegistry(sources=SOURCES, policy=ReservationPolicy((1, 1, 1, 1, 1, 1)))

    def propose(eid, ev):
        return r.propose(
            eid, "kalshi", value=0.61, event=ev, row_sources=BASE10, row_rev=10
        )

    assert propose(1, context())
    state = r._events[1]
    seq = state.pending["kalshi"].seq
    r._local_expired(
        {"event_id": 1, "source": "kalshi", "local_seq": seq, "value": 0.61}
    )
    assert state.expired == {"kalshi": 0.61} and state.expired_through == {
        "kalshi": seq
    }
    assert not propose(2, context()) and 2 not in r._events
    assert propose(3, context(sport=T1))
    before = set(r._events)
    for eid in range(10, 100):
        r.refused(eid, "kalshi", "unobserved")
        r.committed(eid, "kalshi", seq=None, sources=BASE10, rev=10, event=context())
        propose(eid, context(status="finished"))
    assert set(r._events) == before
    assert state.expired_through == {"kalshi": seq}
    assert not propose(4, SimpleNamespace(status="live", preview_read_ticket=0))


@pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
async def test_restart_mismatch_and_legacy_owner_visible(rig):
    before = await rig.client.hgetall(bp.LEDGER_KEY)
    mismatch = bp.LedgerRegistry(
        sources=SOURCES, policy=ReservationPolicy((191, 65, 128, 64, 48, 16))
    )
    with pytest.raises(RuntimeError, match="policy_mismatch"):
        await mismatch.claim(rig.call, "kalshi")
    assert await rig.client.hgetall(bp.LEDGER_KEY) == before
    replacement = rig.registry()
    await replacement.claim(rig.call, "kalshi")
    assert replacement.claims["kalshi"] > rig.k.claims["kalshi"]
    assert _blends(await prepare(rig, replacement, "kalshi", 1, sport=T1))
    # Old scripts require operational exclusion, not merely a fingerprint.
    await rig.client.hset(
        bp.LEDGER_KEY,
        mapping={"owner:polymarket": "900", "read_owner:polymarket": "900"},
    )
    assert not _blends(await prepare(rig, replacement, "kalshi", 2, sport=T1))
    await replacement.capacity_ticket(rig.call, "kalshi")
    assert replacement.capacity_status["compatible"] is False


@pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
async def test_legacy_accounting_outside_window_and_partial_initialization(rig):
    await rig.client.hset(
        bp.LEDGER_KEY,
        mapping={
            "e:99:gen": "44",
            "e:99:seq": "2",
            "e:99:base_rev": "10",
            "e:99:base": "{}",
            "nevents": "1",
        },
    )
    fields = [
        b
        for b in await rig.client.hkeys(bp.LEDGER_KEY)
        if b.startswith(b"r:") or b.startswith(b"policy_owner:")
    ]
    await rig.client.hdel(bp.LEDGER_KEY, "reservation_policy", *fields)
    await rig.k.claim(rig.call, "kalshi")
    await rig.p.claim(rig.call, "polymarket")
    assert await rig.hget("r:unclassified") == "1"
    assert not _blends(await prepare(rig, rig.k, "kalshi", 100, sport=T1))
    await classify(rig, 99, status="scheduled", start=None)
    assert (
        await rig.hget("r:unclassified") == "0" and await rig.hget("r:count:6") == "1"
    )
    assert await rig.hget("e:99:gen") == "44" and await rig.hget("e:99:seq") == "2"
    await rig.k.capacity_ticket(rig.call, "kalshi")
    assert rig.k.capacity_status["debt"] == 1 and not rig.k.capacity_status["ready"]
    assert _blends(await prepare(rig, rig.k, "kalshi", 100, sport=T1))
    await rig.client.hdel(bp.LEDGER_KEY, "r:count:1")
    broken = rig.registry()
    before = await rig.client.hgetall(bp.LEDGER_KEY)
    with pytest.raises(RuntimeError, match="malformed"):
        await broken.claim(rig.call, "polymarket")
    assert await rig.client.hgetall(bp.LEDGER_KEY) == before


@pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
async def test_debt_preserves_deadline_consumes_progress_and_denies_sibling_opens(rig):
    for eid in range(1, 49):
        assert _blends(await prepare(rig, rig.k, "kalshi", eid))
    first = rig.k.pending_seq(1, "kalshi")
    assert _blends(await prepare(rig, rig.k, "kalshi", 1, value=0.62, basis=2))
    # Intermediate migration: compatible valid chains plus one unclassified
    # old resident. This fixture setup is not a production migration operation.
    await rig.client.hset(
        bp.LEDGER_KEY,
        mapping={
            "e:99:gen": "44",
            "e:99:seq": "1",
            "nevents": "49",
            "r:unclassified": "1",
        },
    )
    await classify(rig, 99)
    assert await rig.hget("r:count:4") == "49"
    before = await rig.hget("e:1:m:kalshi")
    await rig.clock(1_020_000)
    commit = rig.k.committed(1, "kalshi", seq=first, sources=BASE10, rev=11)
    await rig.k.prepare(commit, rig.call, rig.stats)
    assert await rig.hget("e:1:m:kalshi") == before
    assert await rig.hget("e:1:base_rev") == "11"
    assert '"_commit_progress"' in await rig.hget("e:1:p:kalshi")
    assert not _blends(await prepare(rig, rig.p, "polymarket", 1, rev=11, value=0.70))
    assert await rig.hget("e:1:m:polymarket") is None
    ticket, _ = await rig.k.read_ticket(rig.call, "kalshi")
    await rig.k.prepare(
        [rig.k.retire_policy(99, "kalshi", context(at=2), 10, ticket, await deadline(rig))],
        rig.call,
        rig.stats,
    )
    assert await rig.hget("r:count:4") == "48"
    await rig.k.prepare(commit, rig.call, rig.stats)
    assert await rig.hget("e:1:m:kalshi") == before
    ticket, _ = await rig.k.read_ticket(rig.call, "kalshi")
    assert not await rig.k.prepare(
        [rig.k.retire_policy(1, "kalshi", context(at=3), 11, ticket, await deadline(rig))],
        rig.call,
        rig.stats,
    )
    assert await rig.hget("e:1:gen") is not None
    await rig.clock(1_060_000)
    rig.k._clock = lambda: 60.0
    await rig.k.prepare(rig.k.expire(), rig.call, rig.stats)
    expired = dict(rig.k._events[1].expired)
    through = dict(rig.k._events[1].expired_through)
    ticket, _ = await rig.k.read_ticket(rig.call, "kalshi")
    await rig.k.prepare(
        [rig.k.retire_policy(1, "kalshi", context(at=4), 11, ticket, await deadline(rig))],
        rig.call,
        rig.stats,
    )
    assert await rig.hget("e:1:gen") is None
    assert not await ops(rig, rig.k, "kalshi", 1, at=5, rev=11, value=0.62, basis=3)
    assert (
        rig.k._events[1].expired == expired
        and rig.k._events[1].expired_through == through
    )


@pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
async def test_maintenance_reclassification_cannot_turn_refused_continue_into_fresh_lease(
    rig,
):
    assert _blends(await prepare(rig, rig.k, "kalshi", 1))
    before = await rig.hget("e:1:m:kalshi")
    chain = rig.k._chains[(1, "kalshi")]
    delayed = await ops(rig, rig.k, "kalshi", 1, at=1, value=0.61, basis=2)
    await classify(rig, 1, sport=T1, at=2)
    assert not await rig.k.prepare(delayed, rig.call, rig.stats)
    assert rig.k._chains[(1, "kalshi")] == chain
    assert rig.k.has_pending(1, "kalshi")
    assert await rig.hget("e:1:m:kalshi") == before
    await rig.clock(1_030_000)
    fresh = await ops(rig, rig.k, "kalshi", 1, sport=T1, at=3, value=0.61, basis=3)
    assert fresh[0]["mode"] == "continue" and fresh[0]["chain"] == chain
    assert _blends(await rig.k.prepare(fresh, rig.call, rig.stats))
    assert (await rig.hget("e:1:m:kalshi")).split()[3] == before.split()[3]


@pytest.mark.parametrize("postpone", [False, True])
@pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
async def test_demotion_or_postponement_cannot_renew_or_replace_borrowed_high_slot(
    rig, postpone
):
    if not postpone:
        for eid in range(10, 58):
            assert _blends(await prepare(rig, rig.k, "kalshi", eid))
    assert _blends(await prepare(rig, rig.k, "kalshi", 1, sport=T1))
    first = rig.k.pending_seq(1, "kalshi")
    before = await rig.hget("e:1:m:kalshi")
    kwargs = (
        {"sport": T1, "status": "scheduled", "start": NOW + timedelta(hours=8)}
        if postpone
        else {"sport": OTHER}
    )
    assert _blends(
        await prepare(rig, rig.k, "kalshi", 1, at=1, value=0.61, basis=2, **kwargs)
    )
    assert await rig.hget("e:1:r_bucket") == "0"
    assert await rig.hget("e:1:r_target") == ("6" if postpone else "4")
    await rig.clock(1_020_000)
    await rig.k.prepare(
        rig.k.committed(1, "kalshi", seq=first, sources=BASE10, rev=11),
        rig.call,
        rig.stats,
    )
    assert (await rig.hget("e:1:m:kalshi")).split()[3] == before.split()[3]
    assert not _blends(
        await prepare(rig, rig.p, "polymarket", 1, at=2, rev=11, **kwargs)
    )
    await rig.k.capacity_ticket(rig.call, "kalshi")
    assert rig.k.capacity_status["debt"] > 0 and not rig.k.capacity_status["ready"]
    await rig.clock(1_060_000)
    rig.k._clock = lambda: 60
    await rig.k.prepare(rig.k.expire(), rig.call, rig.stats)
    ticket, _ = await rig.k.read_ticket(rig.call, "kalshi")
    op = rig.k.retire_policy(1, "kalshi", context(at=3, **kwargs), 11, ticket, await deadline(rig))
    await rig.k.prepare([op], rig.call, rig.stats)
    assert await rig.hget("e:1:gen") is None
    assert await rig.hget("r:count:0") == "0"


@pytest.mark.parametrize("postpone", [False, True])
def test_local_drained_demotion_reclassifies_proof_and_reports_saturation(postpone):
    r = bp.LedgerRegistry(sources=SOURCES, policy=ReservationPolicy((1, 0, 0, 0, 1, 0)))

    def put(eid, ev, value=0.61):
        return r.propose(
            eid, "kalshi", value=value, event=ev, row_sources=BASE10, row_rev=10
        )

    assert put(1, context(sport=T1))
    assert put(2, context())
    kwargs = (
        {"sport": T1, "status": "scheduled", "start": NOW + timedelta(hours=8)}
        if postpone
        else {"sport": OTHER}
    )
    assert put(1, context(at=1, **kwargs), 0.62)
    st = r._events[1]
    assert st.reservation_bucket == 0
    r._local_expired(
        {
            "event_id": 1,
            "source": "kalshi",
            "local_seq": st.pending["kalshi"].seq,
            "value": 0.62,
        }
    )
    assert st.reservation_bucket == (6 if postpone else 4)
    assert st.expired == {"kalshi": 0.62}
    assert not r.local_capacity_status["ready"] and r.local_capacity_status["debt"] > 0
    # Two retained contexts exhaust this deliberately tiny total. Correctness
    # wins: no expired proof is erased to pretend T1 has universal coverage.
    assert not put(3, context(sport=T1, at=2))
    assert set(r._events) == {1, 2}
    assert not put(1, context(at=2, **kwargs), 0.62)


@pytest.mark.parametrize("newer_local_work", [False, True])
@pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
async def test_policy_retirement_ack_preserves_expiry_proof_and_newer_work(
    rig, newer_local_work
):
    for eid in range(1, 49):
        assert _blends(await prepare(rig, rig.k, "kalshi", eid))
    old = rig.k._events[1].pending["kalshi"]
    await rig.clock(1_060_000)
    ticket, _ = await rig.k.read_ticket(rig.call, "kalshi")
    retirement = rig.k.retire_policy(1, "kalshi", context(at=2), 10, ticket, await deadline(rig))
    original_eval = rig.k._eval

    async def delayed_ack(call, operation, *args):
        reply = await original_eval(call, operation, *args)
        if operation == "retire_policy" and newer_local_work:
            assert reply[0] == "ok"
            assert await ops(rig, rig.k, "kalshi", 1, at=3, value=0.62, basis=2)
        return reply

    rig.k._eval = delayed_ack
    await rig.k.prepare([retirement], rig.call, rig.stats)
    state = rig.k._events[1]
    assert await rig.hget("e:1:gen") is None
    if newer_local_work:
        assert state.pending["kalshi"].seq > old.seq
        assert state.pending["kalshi"].value == 0.62
    else:
        assert state.expired == {"kalshi": 0.60}
        assert state.expired_through == {"kalshi": old.seq}
        assert not state.pending
        assert not await ops(rig, rig.k, "kalshi", 1, at=3, value=0.60, basis=3)


def test_local_t1_headroom_reclaims_only_clean_foreign_debt():
    r = bp.LedgerRegistry(sources=SOURCES, policy=ReservationPolicy((1, 0, 0, 0, 1, 0)))

    def put(eid, ev, value=0.61):
        return r.propose(
            eid, "kalshi", value=value, event=ev, row_sources=BASE10, row_rev=10
        )

    assert put(1, context(sport=T1))
    assert put(2, context())
    assert put(1, context(at=1), 0.62)
    st = r._events[1]
    r._local_expired(
        {
            "event_id": 1,
            "source": "kalshi",
            "local_seq": st.pending["kalshi"].seq,
            "value": 0.62,
        }
    )
    assert st.reservation_bucket == 4
    r.committed(1, "kalshi", seq=st.expired_through["kalshi"], sources=BASE10, rev=11)
    assert r._clean_context(st)
    assert put(3, context(sport=T1, at=2))
    assert set(r._events) == {2, 3}
    assert r.has_pending(2, "kalshi")


# Observe the existing maintenance ticket; receipts never issue their own read.
def _reservation_receipts(caplog):
    import json
    prefix = "blend_preview reservation receipt "
    return [json.loads(r.getMessage()[len(prefix):]) for r in caplog.records
            if r.getMessage().startswith(prefix)]


@pytest.mark.parametrize("proof", [False, True])
async def test_maintenance_receipt_ready_provenance_and_retained_proof(rig, caplog, proof):
    import os
    from datetime import datetime
    if proof:
        assert await prepare(rig, rig.k, "kalshi", 1, sport=T1)
        st = rig.k._events[1]
        rig.k._local_expired({"event_id": 1, "source": "kalshi",
                             "local_seq": st.pending["kalshi"].seq, "value": .60})
    caplog.set_level("INFO", logger=bp.__name__)
    calls = []
    async def call(*args):
        calls.append(args[0])
        return await rig.call(*args)
    await rig.k.capacity_ticket(call, "kalshi")
    assert not _reservation_receipts(caplog)  # Generic one-off reads do not opt in.
    before = await rig.client.hgetall(bp.LEDGER_KEY)
    result = await rig.k.capacity_ticket(call, "kalshi", maintenance_receipt=True)
    [r] = _reservation_receipts(caplog)
    assert calls == ["EVAL", "EVAL"] and await rig.client.hgetall(bp.LEDGER_KEY) == before
    assert r["status"] == "ready" and r["ready"] is True
    assert r["origin"] == "capacity_maintenance" and r["version"] == 1
    assert r["pid"] == os.getpid() and r["source"] == "kalshi"
    assert r["claim"] == rig.k.claim_of("kalshi")
    assert r["registry_id"] == rig.k._capacity_registry_id != rig.p._capacity_registry_id
    assert r["policy_fingerprint"] == rig.k.policy.fingerprint
    assert r["sample_seq"] == 2 and r["redis_time_ms"] == result[3]
    assert datetime.fromisoformat(r["sample_started_at"]) <= datetime.fromisoformat(r["sample_finished_at"])
    assert 0 <= r["sample_duration_ms"] <= 1000 and r["shared"]["shared_ready"] is True
    assert r["local"] == rig.k.local_capacity_status and r["local"]["proofs"] == int(proof)


async def test_maintenance_receipt_shared_ready_local_debt(rig, caplog):
    assert await prepare(rig, rig.k, "kalshi", 1, sport=T1)
    st = rig.k._events[1]
    st.reservation_target = 6  # Local retained proof moves outside the eligible window.
    rig.k._local_expired({"event_id": 1, "source": "kalshi",
                         "local_seq": st.pending["kalshi"].seq, "value": .60})
    caplog.set_level("INFO", logger=bp.__name__)
    await rig.k.capacity_ticket(rig.call, "kalshi", maintenance_receipt=True)
    [r] = _reservation_receipts(caplog)
    assert r["shared"]["shared_ready"] is True
    assert r["local"]["proofs"] == 1 and r["local"]["debt"] == 1 and r["local"]["ready"] is False
    assert r["status"] == "not_ready" and r["ready"] is False and st.expired == {"kalshi": .60}


@pytest.mark.parametrize("fault,error", [
    ("absent", KeyError), ("malformed", ValueError), ("ready_number", None),
    ("counts_array", None), ("negative_count", None), ("inconsistent_ready", None),
    ("missing_time", ValueError), ("refused", None),
])
async def test_maintenance_receipt_bad_sample_never_reuses_cached_green(rig, caplog, fault, error):
    import json
    await rig.k.capacity_ticket(rig.call, "kalshi")
    assert rig.k.capacity_status["ready"] is True
    caplog.set_level("INFO", logger=bp.__name__)
    async def call(*args):
        reply = await rig.call(*args)
        status = json.loads(reply[4])
        if fault == "absent": reply[4] = "{}"
        elif fault == "malformed": reply[4] = "not json"
        elif fault == "missing_time": reply[5] = ""
        elif fault == "refused": return ["policy_required"]
        else:
            if fault == "ready_number": status["ready"] = 1
            elif fault == "counts_array": status["counts"] = []
            elif fault == "negative_count": status["counts"]["0"] = -1
            elif fault == "inconsistent_ready": status["debt"] = 1
            reply[4] = json.dumps(status)
        return reply
    if error:
        with pytest.raises(error):
            await rig.k.capacity_ticket(call, "kalshi", maintenance_receipt=True)
    else:
        await rig.k.capacity_ticket(call, "kalshi", maintenance_receipt=True)
    [r] = _reservation_receipts(caplog)
    assert r["status"] == "invalid_sample" and r["ready"] is False
    assert r["shared"] is None and r["local"] is None and r["sample_seq"] == 2


async def test_maintenance_receipt_bounded_emission_fresh_sequence(rig, caplog):
    caplog.set_level("INFO", logger=bp.__name__)
    for _ in range(3):
        await rig.k.capacity_ticket(rig.call, "kalshi", maintenance_receipt=True)
    [first] = _reservation_receipts(caplog)
    assert first["sample_seq"] == 1 and rig.k._capacity_receipt_after["kalshi"] > bp.time.monotonic()
    rig.k._capacity_receipt_after["kalshi"] = bp.time.monotonic() - 1
    await rig.k.capacity_ticket(rig.call, "kalshi", maintenance_receipt=True)
    first, second = _reservation_receipts(caplog)
    assert second["sample_seq"] == 4 and second["registry_id"] == first["registry_id"]
    assert second["redis_time_ms"] >= first["redis_time_ms"]


@pytest.mark.parametrize("fault", ["stale", "forked_registry", "unclaimed"])
async def test_maintenance_receipt_stale_or_wrong_process_refuses_green(rig, caplog, fault):
    await rig.k.capacity_ticket(rig.call, "kalshi")
    caplog.set_level("INFO", logger=bp.__name__)
    if fault == "unclaimed":
        rig.k.claims.clear()
        await rig.k.capacity_ticket(rig.call, "kalshi", maintenance_receipt=True)
    else:
        if fault == "forked_registry": rig.k._capacity_pid = -1
        rig.k._capacity_receipt("kalshi", bp.time.monotonic() - (2 if fault == "stale" else 0),
                               NOW.isoformat(), 2, rig.k.capacity_status, 1_000_000)
    [r] = _reservation_receipts(caplog)
    assert r["status"] == "invalid_sample" and r["ready"] is False


async def test_maintenance_ticket_gateway_emits_without_extra_eval(rig, monkeypatch, caplog):
    from app.tasks.live_blend_refresh import LiveBlendRefresher
    refresher = LiveBlendRefresher("kalshi")
    monkeypatch.setattr(bp, "registry", lambda: rig.k)
    monkeypatch.setattr(refresher, "_client", lambda: rig.client)
    caplog.set_level("INFO", logger=bp.__name__)
    calls = []
    original = refresher._preview_call
    def tracked(connection):
        execute = original(connection)
        async def call(*args):
            calls.append(args[0])
            return await execute(*args)
        return call
    monkeypatch.setattr(refresher, "_preview_call", tracked)
    await refresher._preview_ticket(include_candidates=True)
    [r] = _reservation_receipts(caplog)
    assert r["status"] == "ready" and r["registry_id"] == rig.k._capacity_registry_id
    assert calls == ["EVAL"]


@pytest.mark.parametrize("malformed", [False, True])
async def test_maintenance_receipt_sink_failure_preserves_ticket_outcome(rig, monkeypatch, malformed):
    import json
    attempts = []

    def broken_sink(*args, **kwargs):
        attempts.append(args)
        raise RuntimeError("receipt sink failed")

    monkeypatch.setattr(bp.logger, "info", broken_sink)

    async def call(*args):
        reply = await rig.call(*args)
        if malformed:
            reply[4] = "not json"
        return reply

    if malformed:
        with pytest.raises(json.JSONDecodeError):
            await rig.k.capacity_ticket(call, "kalshi", maintenance_receipt=True)
    else:
        ticket, candidates, idle, redis_ms = await rig.k.capacity_ticket(
            call, "kalshi", maintenance_receipt=True)
        assert ticket == 0 and candidates == [] and idle == set() and redis_ms > 0
        assert rig.k.capacity_status["ready"] is True
    assert len(attempts) == 1
