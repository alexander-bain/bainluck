"""Restart fidelity and finite lease recovery; not PostgreSQL concurrency proof."""

from dataclasses import replace
from datetime import timedelta
import json
import pytest
from app.services.activitykit_worker import (
    decode_state,
    encode_state,
    reserve_state,
    rebind_token,
)
from app.utils.activitykit_delivery_state import RetryPolicy
from app.utils.activitykit_push_record import activity_ref, push_record
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


def test_unavailable_token_replacement_resumes_latest_snapshot_and_original_clocks():
    reserved, attempt = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    halted = reserved.complete(attempt.attempt_id, now=NOW, failure="unavailable")
    replaced = rebind_token(persisted(halted), token_changed=True)
    assert replaced.halted is None and replaced.pending == "update"
    assert replaced.snapshot == halted.snapshot
    assert replaced.score_fence == halted.score_fence
    _, new = replaced.dispatch(now=NOW + timedelta(seconds=1))
    assert new.count == 1


def test_accepted_unchanged_reading_is_requeued_only_for_new_token():
    reserved, attempt = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    done = reserved.complete(attempt.attempt_id, now=NOW)
    assert rebind_token(done, token_changed=False) == done
    replacement = rebind_token(done, token_changed=True)
    assert replacement.snapshot == done.snapshot and replacement.pending == "update"
    assert replacement.last_timestamp == done.last_timestamp


@pytest.mark.parametrize("flag", ["stopped", "ended"])
def test_token_replacement_does_not_resurrect_stop_or_end(flag):
    done = replace(
        state().observe(snapshot(), revision=1),
        **{flag: True},
        halted="unavailable",
        pending=None
    )
    assert rebind_token(done, token_changed=True) == done


def test_terminal_replacement_requeues_only_authoritative_end():
    terminal = state().observe(
        snapshot(
            lifecycle="final", home_rendered_percent=None, probability_observed_at=None
        ),
        revision=1,
    )
    replaced = rebind_token(
        replace(terminal, halted="unavailable", pending=None), token_changed=True
    )
    _, attempt = replaced.dispatch(now=NOW)
    assert attempt.kind == "terminal"
    assert (
        "homeRenderedPercent"
        not in json.loads(attempt.push.body)["aps"]["content-state"]["snapshot"]
    )


def test_true_token_replacement_resets_exhaustion_but_not_configuration_halt():
    exhausted = replace(
        state().observe(snapshot(), revision=1), halted="retry_exhausted"
    )
    assert rebind_token(exhausted, token_changed=False) == exhausted
    assert rebind_token(exhausted, token_changed=True).halted is None
    configuration = replace(exhausted, halted="permanent")
    assert rebind_token(configuration, token_changed=True) == configuration


# #10542 step 1: the per-push age record.


def _fields(line):
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def test_push_record_says_how_old_the_numbers_were_when_the_push_left():
    reading = snapshot(
        home_score=77,
        away_score=75,
        home_rendered_percent=65,
        score_observed_at=NOW - timedelta(seconds=20),
        probability_observed_at=NOW - timedelta(seconds=45),
    )
    _, attempt = state().observe(reading, revision=1).dispatch(now=NOW)
    sent = NOW + timedelta(seconds=2)
    line = push_record(
        attempt,
        activity_id="registered-activity",
        sent_at=sent,
        answered_at=sent + timedelta(milliseconds=84),
        outcome="accepted",
        reason="apns_accepted",
    )
    fields = _fields(line)
    assert line.startswith("activitykit push: ")
    assert "screen=[live 75-77 65%]" in line  # away-home, as Apple Sports prints it
    assert fields["event"] == "42"
    assert fields["kind"] == "update"
    assert fields["priority"] == "10"  # first send: the screen is new
    assert fields["score_age"] == "22.0"
    assert fields["chance_age"] == "47.0"
    assert fields["outcome"] == "accepted"
    assert fields["reason"] == "apns_accepted"
    assert fields["apple_ms"] == "84"
    assert fields["attempt"] == "1"
    assert fields["activity"] == activity_ref("registered-activity")
    assert "registered-activity" not in line


def test_push_record_marks_a_refresh_of_the_same_screen_at_priority_5():
    first = state().observe(snapshot(), revision=1)
    sent, attempt = first.dispatch(now=NOW)
    done = sent.complete(attempt.attempt_id, now=NOW)
    later = NOW + timedelta(seconds=30)
    _, refresh = done.observe(
        snapshot(score_observed_at=later, probability_observed_at=later), revision=2
    ).dispatch(now=later)
    line = push_record(
        refresh,
        activity_id="registered-activity",
        sent_at=later,
        answered_at=later,
        outcome="accepted",
        reason="apns_accepted",
    )
    assert _fields(line)["priority"] == "5"
    assert _fields(line)["score_age"] == "0.0"


def test_push_record_prints_a_dash_for_a_clock_the_push_does_not_carry():
    reading = snapshot(
        lifecycle="suspended", home_rendered_percent=None, probability_observed_at=None
    )
    _, attempt = state().observe(reading, revision=1).dispatch(now=NOW)
    line = push_record(
        attempt,
        activity_id="registered-activity",
        sent_at=NOW,
        answered_at=NOW - timedelta(seconds=1),  # a clock step never goes negative
        outcome="retry",
        reason="transport_unavailable",
    )
    assert _fields(line)["chance_age"] == "-"
    assert "screen=[suspended 2-1 -]" in line
    assert _fields(line)["apple_ms"] == "0"


def test_push_record_never_raises_on_an_odd_body():
    _, attempt = state().observe(snapshot(), revision=1).dispatch(now=NOW)
    odd = replace(
        attempt,
        command=replace(attempt.command, push=replace(attempt.push, body=b"not json")),
    )
    line = push_record(
        odd,
        activity_id="x",
        sent_at=NOW,
        answered_at=NOW,
        outcome="rejected",
        reason="invalid_command",
    )
    assert _fields(line)["score_age"] == "-"
    assert _fields(line)["event"] == "-"
