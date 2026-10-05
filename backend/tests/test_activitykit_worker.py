"""Restart fidelity and finite lease recovery; not PostgreSQL concurrency proof."""

from dataclasses import replace
from datetime import timedelta
import json
import pytest
from app.services.activitykit_worker import decode_state, encode_state, reserve_state
from app.utils.activitykit_delivery_state import RetryPolicy
from tests.test_activitykit_delivery_state import NOW, snapshot, state


def persisted(value):
    return decode_state(json.loads(json.dumps(encode_state(value))))


def test_restart_keeps_exact_pending_bytes_clocks_and_attempt_identity():
    reserved, attempt = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    restarted = persisted(reserved)
    assert restarted == reserved
    assert restarted.attempt.push.body == attempt.push.body
    assert restarted.attempt.attempt_id == attempt.attempt_id


def test_lease_excludes_second_worker_until_expired():
    reserved, _ = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    same, attempt = reserve_state(
        persisted(reserved),
        now=NOW,
        lease_id="lease",
        lease_expires_at=NOW + timedelta(seconds=60),
        owner_changed=False,
    )
    assert attempt is None
    assert same == reserved


def test_expired_lease_recovers_same_command_with_new_attempt():
    reserved, first = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    recovered, second = reserve_state(
        persisted(reserved),
        now=NOW + timedelta(seconds=60),
        lease_id="lease",
        lease_expires_at=NOW + timedelta(seconds=60),
        owner_changed=False,
    )
    assert second.command == first.command
    assert second.attempt_id != first.attempt_id
    assert second.count == 2
    assert recovered.complete(first.attempt_id, now=NOW) == recovered


def test_recovery_does_not_reset_retry_budget():
    original = replace(state(), retry_policy=RetryPolicy(()))
    reserved, _ = original.observe(snapshot(), revision=1).dispatch(now=NOW)
    recovered, attempt = reserve_state(
        persisted(reserved),
        now=NOW + timedelta(seconds=60),
        lease_id="lease",
        lease_expires_at=NOW,
        owner_changed=False,
    )
    assert attempt is None
    assert recovered.halted == "retry_exhausted"


def test_terminal_supersedes_crashed_update_before_recovery():
    reserved, _ = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    final = reserved.observe(
        snapshot(
            lifecycle="final", home_rendered_percent=None, probability_observed_at=None
        ),
        revision=2,
    )
    _, command = reserve_state(
        persisted(final),
        now=NOW + timedelta(seconds=60),
        lease_id="lease",
        lease_expires_at=NOW,
        owner_changed=False,
    )
    assert command.kind == "terminal"
    assert json.loads(command.push.body)["aps"]["event"] == "end"


def test_replacement_fences_an_unexpired_old_reservation():
    reserved, first = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    _, second = reserve_state(
        reserved,
        now=NOW + timedelta(seconds=1),
        lease_id="old",
        lease_expires_at=NOW + timedelta(seconds=60),
        owner_changed=True,
    )
    assert second.command == first.command
    assert second.count == 2


@pytest.mark.parametrize(
    "corrupt",
    [{}, {"schema": 2, "state": {}}, {"schema": 1, "state": {"token": "SECRET"}}],
)
def test_corrupt_persistence_fails_closed_without_echo(corrupt):
    with pytest.raises(ValueError, match="^Invalid persisted ActivityKit state$"):
        decode_state(corrupt)


def test_stop_and_high_water_fences_survive_restart():
    stopped = state().observe(snapshot(), revision=1).stop()
    assert persisted(stopped) == stopped
    assert persisted(stopped).observe(snapshot(home_score=9), revision=2) == stopped
