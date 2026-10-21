"""Fresh unchanged winner observations may display without an event restamp."""

from datetime import datetime, timedelta, timezone
import asyncio
from types import SimpleNamespace

import pytest

from app.utils import blend_preview
from app.utils.aggregation import stamp_source_reading
from tests.test_blend_preview_display_before_persist_195 import (
    _PreviewSession, _event, _capture_previews, _blends, _revokes,
)
from tests.test_live_blend_refresh import _one_event_refresher


@pytest.fixture(autouse=True)
def preview_enabled(monkeypatch):
    blend_preview.reset_registry_for_tests()
    monkeypatch.setenv(blend_preview.SOURCE_ENV, "polymarket")
    monkeypatch.setenv(blend_preview.EVENT_IDS_ENV, "1")
    yield
    blend_preview.reset_registry_for_tests()


def rig(monkeypatch):
    now = datetime.now(timezone.utc)
    stored = {"polymarket": {"value": .9, "updated_at": (now - timedelta(seconds=5)).isoformat()},
              "kalshi": {"value": .5, "updated_at": (now - timedelta(seconds=10)).isoformat()}}
    event, market = _event()
    event.win_probability_sources = stored
    session = _PreviewSession([(market, event)], None, stored=stored, rev=10)
    refresher, committed = _one_event_refresher(monkeypatch, session)
    refresher._last_written_value[1] = .9
    refresher._last_write_at[1] = 100.
    rows = [SimpleNamespace(id=101, last_updated=now - timedelta(seconds=1)),
            SimpleNamespace(id=102, last_updated=now - timedelta(seconds=1))]
    reading = SimpleNamespace(home_probability=.9, away_probability=None, draw_probability=None,
                              eligibility=None, contributing_outcomes=rows)
    monkeypatch.setattr("app.utils.live_blend.compute_source_home_probability", lambda *a, **kw: reading)
    previews = _capture_previews(monkeypatch, refresher, session)
    return refresher, session, previews, committed, rows, reading, now


async def test_fresh_same_value_previews_without_event_update(monkeypatch):
    r, session, previews, committed, rows, _, _ = rig(monkeypatch)
    await r._refresh_batch([1], 101.)
    [frame] = _blends(previews)
    assert frame["display_observed_at"] == rows[0].last_updated.isoformat()
    assert frame["preview"]["pending"] == {"polymarket": .9}
    assert session.updates == [] and committed == []
    assert r._dispositions[1] == ("preview_only", .9)
    assert not r._lock_retry
    assert r._last_write_at[1] == 100.
    assert blend_preview.registry().has_pending(1, "polymarket")


@pytest.mark.parametrize("kind", ["no-observation", "frozen-winner", "frozen-leg", "unknown-stored",
                                 "fallback", "terminal", "ineligible", "stale-basis"])
async def test_unproved_observation_cannot_take_the_preview_only_path(monkeypatch, kind):
    r, session, previews, committed, rows, reading, now = rig(monkeypatch)
    if kind == "no-observation":
        rows[0].last_updated = None
    elif kind == "frozen-winner":
        for row in rows:
            row.last_updated = now - timedelta(seconds=10)
    elif kind == "frozen-leg":
        rows[0].last_updated = now - timedelta(seconds=10)
    elif kind == "unknown-stored":
        session.stored["polymarket"].pop("updated_at")
    elif kind == "fallback":
        session.stored.pop("polymarket")
    elif kind == "terminal":
        session._market_rows[0][1].status = "completed"
    elif kind == "ineligible":
        from app.utils.probability_eligibility import EligibilityRecord, INELIGIBLE
        reading.eligibility = EligibilityRecord(status=INELIGIBLE)
    elif kind == "stale-basis":
        session.stored["polymarket"].update(
            observed_value=.9, observed_basis={"101": now.timestamp(), "102": now.timestamp()},
        )
    await r._refresh_batch([1], 101.)
    assert not _blends(previews)
    assert not blend_preview.registry().has_pending(1)
    assert not session.updates and not committed and not r._lock_retry


async def test_derivative_tick_cannot_advance_frozen_contributing_winner(monkeypatch):
    r, session, previews, _, rows, _, now = rig(monkeypatch)
    for row in rows:
        row.last_updated = now - timedelta(seconds=10)
    # Fresh derivative rows are present in the DB graph but not the reading.
    session._outcomes = [SimpleNamespace(id=999, market_id=10, last_updated=now)]
    await r._refresh_batch([1], 101.)
    assert r._dispositions[1] == ("unobserved", .9)
    assert not _blends(previews) and not session.updates


async def test_duplicate_basis_and_only_one_fresh_leg_do_not_redate_or_extend(monkeypatch):
    r, session, previews, _, rows, _, _ = rig(monkeypatch)
    clock = [0.]
    blend_preview._REGISTRY = blend_preview.PreviewRegistry(clock=lambda: clock[0], epoch=7)
    await r._refresh_batch([1], 101.)
    first = _blends(previews)[0]
    clock[0] = 2.
    await r._refresh_batch([1], 102.)
    rows[1].last_updated += timedelta(milliseconds=100)
    await r._refresh_batch([1], 103.)
    assert _blends(previews) == [first]
    assert _revokes(previews) == []
    rows[0].last_updated += timedelta(milliseconds=100)
    await r._refresh_batch([1], 104.)
    second = _blends(previews)[1]
    assert second["display_observed_at"] == rows[0].last_updated.isoformat()
    assert second["preview"]["ttl_ms"] == first["preview"]["ttl_ms"] - 2000
    assert not session.updates and not r._lock_retry


async def test_short_ttl_expires_without_reopening_same_value_or_lock_debt(monkeypatch):
    r, session, previews, _, rows, _, _ = rig(monkeypatch)
    clock = [0.]
    blend_preview._REGISTRY = blend_preview.PreviewRegistry(
        max_uncommitted_s=3., clock=lambda: clock[0], epoch=7,
    )
    await r._refresh_batch([1], 101.)
    clock[0] = 3.
    await r._refresh_batch([1], 104.)
    assert [frame["preview"]["reason"] for frame in _revokes(previews)] == ["expired"]
    for row in rows:
        row.last_updated += timedelta(milliseconds=100)
    clock[0] = 5.
    await r._refresh_batch([1], 106.)
    assert len(_blends(previews)) == 1
    assert not blend_preview.registry().has_pending(1)
    assert r._dispositions[1] == ("preview_only", .9)
    assert not session.updates and not r._lock_retry


async def test_regular_restamp_commit_retires_observation_preview(monkeypatch):
    r, session, previews, committed, rows, _, _ = rig(monkeypatch)
    await r._refresh_batch([1], 101.)
    session.locked = False
    session._returned = stamp_source_reading(session.stored, "polymarket", .9)
    session.returned_rev = 11
    await r._refresh_batch([1], 100. + r.unchanged_restamp_interval_s)
    assert len(session.updates) == 1
    assert [frame["rev"] for frame in committed] == [{"1": 11}]
    assert not blend_preview.registry().has_pending(1)
    assert not _revokes(previews)


async def test_off_retains_original_unchanged_storage_throttle(monkeypatch):
    monkeypatch.delenv(blend_preview.SOURCE_ENV)
    r, session, previews, committed, _, _, _ = rig(monkeypatch)
    await r._refresh_batch([1], 101.)
    assert r._dispositions[1] == ("unchanged", .9)
    assert not previews and not committed and not session.updates


def test_preview_only_closes_receipt_without_claiming_a_stamp_or_retry(caplog):
    import logging
    from app.tasks.live_blend_refresh import TailReceipts

    caplog.set_level(logging.INFO, logger="app.tasks.live_blend_refresh")
    receipts = TailReceipts("polymarket")
    for step in (0., 1.):
        mark = receipts.note_input(1, 101, .9, "price_change")
        receipts.observe({1: mark}, mark.recv_wall, set(), mark.recv_mono)
        receipts.resolve({1}, {1: ("preview_only", .9)}, {1: mark}, mark.recv_wall, mark.recv_mono + step)
        assert not receipts._open
    lines = [record.getMessage() for record in caplog.records if "tail-receipt run=" in record.getMessage()]
    assert len(lines) == 1 and receipts.stats["coalesced"] == 1
    assert "result=preview_only" in lines[0] and "value=0.9" in lines[0]
    assert "stamped_at=None" in lines[0] and "lock_retries=0" in lines[0]


def acknowledged_rig(monkeypatch):
    r, session, frames, committed, rows, reading, now = rig(monkeypatch)
    reading.named_home_quote = True
    session._market_rows[0][0].status = "open"
    for index, row in enumerate(rows):
        row.market_id = 10
        row.current_probability = .9 if index == 0 else .1
        row.last_updated = now - timedelta(seconds=3)
        row.resolution_source = None
        row.is_winner = False  # FuturesOutcome Python and server default; unresolved
    session._outcomes = rows
    observations = {1: {row.id: (row.current_probability, (now - timedelta(seconds=1)).timestamp(),
                               SimpleNamespace(probability=row.current_probability)) for row in rows}}

    async def validate(event_ids):
        return set(event_ids)

    async def publish(initial, *, prepare_frames=None):
        frames.extend((len(session.updates), frame) for frame in (
            await prepare_frames() if prepare_frames is not None else initial
        ))

    monkeypatch.setattr(r, "_publish_previews", publish)
    return r, session, frames, committed, rows, reading, observations, validate, now


async def test_accepted_observation_uses_only_ephemeral_clocks_and_no_stamp_state(monkeypatch):
    r, session, frames, committed, rows, _, observations, validate, now = acknowledged_rig(monkeypatch)
    await r.preview_accepted_observations(observations, validate)
    [frame] = _blends(frames)
    assert frame["display_observed_at"] == (now - timedelta(seconds=1)).isoformat()
    assert all(row.last_updated == now - timedelta(seconds=3) for row in rows)
    assert not session.updates and not committed and not r._lock_retry
    assert r._last_write_at[1] == 100. and r._last_written_value[1] == .9
    assert not r._dispositions and not r._history


@pytest.mark.parametrize("refusal", ["unknown-orientation", "missing-partner", "settled-row", "closed-market",
                                    "changed-price", "newer-stored-row", "equal-bound", "db-clock-ahead",
                                    "no-bound", "terminal"])
async def test_ack_preview_requires_current_complete_unresolved_cohort(monkeypatch, refusal):
    r, session, frames, _, rows, reading, observations, validate, now = acknowledged_rig(monkeypatch)
    if refusal == "unknown-orientation":
        reading.named_home_quote = False
    elif refusal == "missing-partner":
        observations[1].pop(rows[1].id)
    elif refusal == "settled-row":
        rows[1].resolution_source = "polymarket"
    elif refusal == "closed-market":
        session._market_rows[0][0].status = "closed"
    elif refusal == "changed-price":
        rows[1].current_probability = .2
    elif refusal == "newer-stored-row":
        rows[1].last_updated = now
    elif refusal == "equal-bound":
        rows[1].last_updated = datetime.fromtimestamp(observations[1][rows[1].id][1], timezone.utc)
    elif refusal == "db-clock-ahead":
        rows[1].last_updated = now + timedelta(seconds=10)
        value, _, mark = observations[1][rows[1].id]
        observations[1][rows[1].id] = (value, (now + timedelta(seconds=5)).timestamp(), mark)
    elif refusal == "no-bound":
        value, _, mark = observations[1][rows[1].id]
        observations[1][rows[1].id] = (value, None, mark)
    elif refusal == "terminal":
        session._market_rows[0][1].status = "completed"
    await r.preview_accepted_observations(observations, validate)
    assert not frames and not session.updates
    assert not blend_preview.registry().has_pending(1)


@pytest.mark.parametrize("cancel", [False, True])
async def test_send_time_validation_after_checkout_rejects_superseded_work_without_proposal(monkeypatch, cancel):
    from app.tasks.live_blend_refresh import LiveBlendRefresher

    r, session, frames, _, _, _, observations, _, _ = acknowledged_rig(monkeypatch)
    monkeypatch.setattr(r, "_publish_previews", LiveBlendRefresher._publish_previews.__get__(r))
    blend_preview.registry().epoch = 7
    entered, release = asyncio.Event(), asyncio.Event()
    commands, released = [], []
    current = [True]

    class Connection:
        async def send_command(self, *args):
            commands.append(args)

        async def read_response(self):
            return 1, 0, 7

        async def disconnect(self):
            pass

    connection = Connection()

    class Pool:
        async def release(self, item):
            released.append(item)

    pool = Pool()

    async def checkout(given):
        assert given is pool
        entered.set()
        await release.wait()
        return connection

    async def validate(ids):
        return set(ids) if current[0] else set()

    monkeypatch.setattr(r, "_client", lambda: SimpleNamespace(connection_pool=pool))
    monkeypatch.setattr("app.utils.market_quote_push._checkout", checkout)
    task = asyncio.create_task(r.preview_accepted_observations(observations, validate))
    await asyncio.wait_for(entered.wait(), 1)
    current[0] = False  # a newer mark/withdrawal became authoritative during checkout
    if cancel:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        release.set()
        await task
        assert released == [connection]
    assert not commands and not session.updates
    assert not blend_preview.registry().has_pending(1)


async def test_future_frozen_bound_never_becomes_a_new_app_clock_observation(monkeypatch):
    r, session, frames, _, _, _, observations, validate, now = acknowledged_rig(monkeypatch)
    for oid, (value, _, mark) in list(observations[1].items()):
        observations[1][oid] = (value, (now + timedelta(seconds=5)).timestamp(), mark)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.wall

    Clock.wall = now
    monkeypatch.setattr('app.tasks.live_blend_refresh.datetime', Clock)
    await r.preview_accepted_observations(observations, validate)
    Clock.wall += timedelta(seconds=2)
    await r.preview_accepted_observations(observations, validate)
    assert not frames and not blend_preview.registry().has_pending(1)
    Clock.wall += timedelta(seconds=4)
    await r.preview_accepted_observations(observations, validate)
    assert _blends(frames)[0]['display_observed_at'] == (now + timedelta(seconds=5)).isoformat()
    before = len(frames)
    Clock.wall += timedelta(seconds=1)
    await r.preview_accepted_observations(observations, validate)
    assert len(frames) == before
    assert not session.updates


@pytest.mark.parametrize('transition', ['terminal', 'closed', 'settled', 'winner', 'missing-bound'])
async def test_authoritative_invalidity_retires_existing_observation_preview(monkeypatch, transition):
    r, session, frames, _, rows, _, observations, validate, _ = acknowledged_rig(monkeypatch)
    await r.preview_accepted_observations(observations, validate)
    assert blend_preview.registry().has_pending(1, 'polymarket')
    frames.clear()
    if transition == 'terminal':
        session._market_rows[0][1].status = 'completed'
    elif transition == 'closed':
        session._market_rows[0][0].status = 'closed'
    elif transition == 'settled':
        rows[1].resolution_source = 'polymarket'
    elif transition == 'winner':
        rows[1].is_winner = True
    else:
        value, _, mark = observations[1][rows[1].id]
        observations[1][rows[1].id] = (value, None, mark)
    await r.preview_accepted_observations(observations, validate)
    if transition == 'missing-bound':
        assert blend_preview.registry().has_pending(1, 'polymarket')
        assert not frames
    else:
        assert not blend_preview.registry().has_pending(1, 'polymarket')
        assert len(_revokes(frames)) == 1
    assert not session.updates


async def test_settled_opposite_leg_retires_pending_singleton_winner_preview(monkeypatch):
    r, session, frames, _, rows, reading, observations, validate, _ = acknowledged_rig(monkeypatch)
    reading.contributing_outcomes = [rows[0]]
    observations[1].pop(rows[1].id)
    await r.preview_accepted_observations(observations, validate)
    assert blend_preview.registry().has_pending(1, 'polymarket')
    frames.clear()
    rows[1].is_winner = True
    await r.preview_accepted_observations(observations, validate)
    assert not blend_preview.registry().has_pending(1, 'polymarket')
    assert len(_revokes(frames)) == 1 and not session.updates


async def test_model_default_false_is_unresolved_and_can_publish_observation(monkeypatch):
    from app.models.models import FuturesOutcome
    from app.utils.settledness import market_assigned_settled

    r, session, frames, _, rows, _, observations, validate, _ = acknowledged_rig(monkeypatch)
    column = FuturesOutcome.__table__.c.is_winner
    assert column.default.arg is False
    assert str(column.server_default.arg) == 'false'
    for row in rows:
        row.is_winner = column.default.arg
    assert not market_assigned_settled(session._market_rows[0][0], rows)
    await r.preview_accepted_observations(observations, validate)
    assert len(_blends(frames)) == 1
    assert blend_preview.registry().has_pending(1, 'polymarket')
    assert not _revokes(frames) and not session.updates


async def test_legacy_null_winner_also_remains_unresolved(monkeypatch):
    r, session, frames, _, rows, _, observations, validate, _ = acknowledged_rig(monkeypatch)
    for row in rows:
        row.is_winner = None
    await r.preview_accepted_observations(observations, validate)
    assert len(_blends(frames)) == 1 and not session.updates
