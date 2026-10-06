"""Persisted observation corruption and unknown-age contracts."""

import pytest
from dataclasses import replace
from app.services.activitykit_observation import (
    decode_snapshot,
    encode_snapshot,
    ActivityKitObservationAdapter,
)
from app.utils.event_fk_inventory import EVENT_CHILD_DISPOSITIONS
from tests.test_activitykit_delivery_state import snapshot


def test_codec_preserves_known_and_unknown_independent_clocks():
    original = replace(snapshot(), probability_observed_at=None)
    assert decode_snapshot(encode_snapshot(original)) == original
    assert decode_snapshot(encode_snapshot(original)).probability_observed_at is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: {**value, "schema": 2},
        lambda value: {"schema": 1},
        lambda value: {**value, "snapshot": {**value["snapshot"], "event_id": False}},
        lambda value: {
            **value,
            "snapshot": {**value["snapshot"], "score_observed_at": "2026-10-05"},
        },
    ],
)
def test_corrupt_persisted_snapshot_fails_closed(mutate):
    with pytest.raises(ValueError):
        decode_snapshot(mutate(encode_snapshot(snapshot())))


@pytest.mark.parametrize("timeout", [0, 30001, True])
def test_serializer_wait_is_bounded(timeout):
    with pytest.raises(ValueError):
        ActivityKitObservationAdapter(None, lock_timeout_ms=timeout)


def test_retained_event_observation_is_substance():
    assert EVENT_CHILD_DISPOSITIONS["activitykit_observations"] == "SUBSTANCE"
