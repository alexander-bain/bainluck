"""Behavioral delivery transitions without a token, network, or implicit clock."""

from datetime import datetime, timedelta, timezone
import json

import pytest

from app.utils.activitykit_delivery_state import DeliveryState, RetryPolicy
from app.utils.activitykit_payload import GameActivitySnapshot

NOW = datetime(2026, 10, 5, tzinfo=timezone.utc)
POLICY = RetryPolicy((timedelta(seconds=1), timedelta(seconds=2)))


def snapshot(**changes):
    return GameActivitySnapshot(
        event_id=42,
        home_team="Home",
        away_team="Away",
        **{
            "lifecycle": "live",
            "home_score": 1,
            "away_score": 2,
            "home_rendered_percent": 60,
            "score_observed_at": NOW,
            "probability_observed_at": NOW,
            **changes,
        }
    )


def state():
    return DeliveryState("registered-activity", 42, POLICY)


def aps(command):
    return json.loads(command.push.body)["aps"]


def test_duplicate_revision_and_duplicate_reading_do_not_send_twice():
    ready = state().observe(snapshot(), revision=1)
    sent, command = ready.dispatch(now=NOW)
    assert sent.dispatch(now=NOW)[1] is None
    done = sent.complete(command.attempt_id, now=NOW)
    assert done.observe(snapshot(home_score=9), revision=1) == done
    duplicate = done.observe(snapshot(), revision=2)
    assert duplicate.pending is None
    assert duplicate.dispatch(now=NOW + timedelta(seconds=1))[1] is None
    assert duplicate.complete(command.attempt_id, now=NOW) == duplicate


def test_latest_pending_reading_coalesces_without_parallel_dispatch():
    sent, first = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    second = sent.observe(snapshot(home_score=3), revision=2)
    third = second.observe(snapshot(home_score=4), revision=3)
    assert third.dispatch(now=NOW + timedelta(seconds=1))[1] is None
    released = third.complete(first.attempt_id, now=NOW)
    assert released.dispatch(now=NOW)[1] is None  # no fabricated ordering timestamp
    _, next_command = released.dispatch(now=NOW + timedelta(seconds=1))
    assert aps(next_command)["content-state"]["snapshot"]["homeScore"] == 4
    assert aps(next_command)["timestamp"] > aps(first)["timestamp"]


@pytest.mark.parametrize("field", ["score_observed_at", "probability_observed_at"])
def test_unknown_clock_never_erases_each_source_high_water_fence(field):
    known = state().observe(snapshot(), revision=1)
    unknown = known.observe(snapshot(**{field: None}), revision=2)
    rejected = unknown.observe(
        snapshot(**{field: NOW - timedelta(seconds=1)}), revision=3
    )
    assert rejected.snapshot == unknown.snapshot
    assert rejected.score_fence == NOW
    assert rejected.probability_fence == NOW
    assert rejected.snapshot.__dict__[field] is None
    assert rejected.seen_revision == 3
    assert rejected.observe(snapshot(home_score=9), revision=2) == rejected


def test_revision_orders_unknown_values_without_becoming_a_clock():
    unknown = state().observe(
        snapshot(score_observed_at=None, probability_observed_at=None), revision=9999
    )
    _, command = unknown.dispatch(now=NOW)
    wire = aps(command)
    assert "scoreObservedAt" not in wire["content-state"]["snapshot"]
    assert wire["stale-date"] == wire["timestamp"]
    assert unknown.observe(snapshot(home_score=9), revision=9998) == unknown


@pytest.mark.parametrize("lifecycle", ["final", "closed"])
def test_terminal_supersedes_update_retry_and_latches_exact_final(lifecycle):
    sent, update = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    waiting = sent.complete(update.attempt_id, now=NOW, failure="transient")
    final = snapshot(
        lifecycle=lifecycle,
        home_rendered_percent=None,
        probability_observed_at=None,
        score_observed_at=NOW - timedelta(seconds=10),
    )
    latched = waiting.observe(final, revision=2)
    assert latched.attempt is None
    assert latched.observe(snapshot(), revision=3) == latched
    delivered, end = latched.dispatch(now=NOW + timedelta(seconds=1))
    assert end.kind == "terminal"
    assert aps(end)["event"] == "end"
    assert "homeRenderedPercent" not in aps(end)["content-state"]["snapshot"]
    assert delivered.snapshot.score_observed_at == final.score_observed_at
    assert delivered.complete(end.attempt_id, now=NOW).ended


def test_stop_waits_for_inflight_update_then_supersedes_final_and_prevents_restart():
    sent, update = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    final = snapshot(
        lifecycle="final", home_rendered_percent=None, probability_observed_at=None
    )
    stopped = sent.observe(final, revision=2).stop()
    assert stopped.observe(snapshot(), revision=3) == stopped
    assert stopped.dispatch(now=NOW)[1] is None
    ready = stopped.complete(update.attempt_id, now=NOW, failure="transient")
    delivered, stop = ready.dispatch(now=NOW + timedelta(seconds=1))
    assert stop.kind == "stop"
    assert aps(stop)["dismissal-date"] < aps(stop)["timestamp"]
    assert delivered.complete(stop.attempt_id, now=NOW).ended


def test_stop_after_inflight_final_still_requests_immediate_dismissal():
    final = snapshot(
        lifecycle="final", home_rendered_percent=None, probability_observed_at=None
    )
    sent, end = state().observe(final, revision=1).dispatch(now=NOW)
    stopped = sent.stop().complete(end.attempt_id, now=NOW)
    assert not stopped.ended
    assert stopped.dispatch(now=NOW + timedelta(seconds=1))[1].kind == "stop"


def test_transient_retries_are_bounded_byte_identical_and_late_ack_is_inert():
    sent, original = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    waiting = sent.complete(original.attempt_id, now=NOW, failure="transient")
    assert waiting.complete(original.attempt_id, now=NOW) == waiting
    assert waiting.dispatch(now=NOW)[1] is None
    for count, clock in [
        (2, NOW + timedelta(seconds=1)),
        (3, NOW + timedelta(seconds=3)),
    ]:
        sent, retry = waiting.dispatch(now=clock)
        assert retry.command_id == original.command_id
        assert retry.push == original.push
        assert retry.attempt_id != original.attempt_id
        for delayed in [None, "permanent", "transient"]:
            assert (
                sent.complete(original.attempt_id, now=clock, failure=delayed) == sent
            )
        assert sent.attempt.count == count
        waiting = sent.complete(retry.attempt_id, now=clock, failure="transient")
    assert waiting.halted == "retry_exhausted"
    assert waiting.dispatch(now=NOW + timedelta(days=1))[1] is None


@pytest.mark.parametrize("failure", ["permanent", "unavailable"])
def test_unavailable_or_permanent_delivery_halts_without_routine_retry(failure):
    sent, command = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    halted = sent.complete(command.attempt_id, now=NOW, failure=failure)
    assert halted.halted == failure
    assert halted.dispatch(now=NOW + timedelta(days=1))[1] is None
    assert halted.stop().dispatch(now=NOW + timedelta(days=1))[1] is None


def test_new_reading_supersedes_waiting_retry_but_inflight_failure_releases_newest():
    sent, command = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    waiting = sent.complete(command.attempt_id, now=NOW, failure="transient")
    newer = waiting.observe(snapshot(home_score=3), revision=2)
    assert newer.attempt is None
    assert newer.dispatch(now=NOW + timedelta(seconds=1))[1] != command
    newest = sent.observe(snapshot(home_score=4), revision=2)
    assert (
        newest.complete(command.attempt_id, now=NOW, failure="transient").attempt
        is None
    )


def test_identity_policy_revision_and_future_clock_reject_invalid_inputs():
    with pytest.raises(ValueError):
        state().observe(GameActivitySnapshot(43, "H", "A", "live"), revision=1)
    with pytest.raises(ValueError):
        state().observe(snapshot(), revision=True)
    with pytest.raises(ValueError):
        RetryPolicy((timedelta(seconds=-1),))
    with pytest.raises(ValueError):
        state().stop()
    with pytest.raises(ValueError):
        state().observe(
            snapshot(score_observed_at=NOW + timedelta(seconds=1)), revision=1
        ).dispatch(now=NOW)


@pytest.mark.parametrize("kind", ["terminal", "stop"])
def test_same_second_end_waits_and_retries_cannot_resurrect_update(kind):
    sent, update = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    ready = sent.complete(update.attempt_id, now=NOW)
    if kind == "terminal":
        ready = ready.observe(
            snapshot(
                lifecycle="final",
                home_rendered_percent=None,
                probability_observed_at=None,
            ),
            revision=2,
        )
    else:
        ready = ready.stop()
    held, command = ready.dispatch(now=NOW + timedelta(microseconds=999999))
    assert command is None
    assert held.pending == kind
    dispatched, end = held.dispatch(now=NOW + timedelta(seconds=1))
    assert end.kind == kind
    assert aps(end)["timestamp"] == aps(update)["timestamp"] + 1
    assert (
        dispatched.complete(update.attempt_id, now=NOW, failure="transient")
        == dispatched
    )
    assert dispatched.observe(snapshot(home_score=99), revision=3) == dispatched
