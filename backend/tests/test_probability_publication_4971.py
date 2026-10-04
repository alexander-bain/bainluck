"""#4971: the pure half of the publication record. The transactional half
(final committed bag, rollback, savepoint, revision trigger, concurrency) is in
``tests/integration/test_probability_publication_pg_4971.py``."""

from decimal import Decimal

import pytest

from app.utils.probability_publication import (
    COVERAGE_COMPLETE,
    COVERAGE_UNCOVERED,
    RECORDING_FLAG,
    build_publication,
    recording_enabled,
)

STAMP = "2026-10-04T20:00:00+00:00"


def _obs(source, value, returned, *, rev=1, evidence=None):
    return {
        "source": source,
        "value": value,
        "removed": value is None,
        "rev": rev,
        "stamped_at": STAMP,
        "returned_sources": returned,
        "evidence": evidence,
    }


def _build(bag, observations, **overrides):
    kwargs = dict(
        event_id=7,
        sources=bag,
        rev=3,
        status="live",
        espn_win_prob_home=None,
        opening_home_probability=None,
        observations=observations,
        stream_frame_eligible=True,
    )
    kwargs.update(overrides)
    return build_publication(**kwargs)


@pytest.mark.parametrize("raw", [None, "", "1", "yes", "TRUE ", "on"])
def test_recording_is_off_unless_exactly_true(monkeypatch, raw):
    if raw is None:
        monkeypatch.delenv(RECORDING_FLAG, raising=False)
    else:
        monkeypatch.setenv(RECORDING_FLAG, raw)
    assert recording_enabled() is (raw == "TRUE ")


def test_complete_publication_keeps_bag_clocks_and_evidence_verbatim():
    bag = {
        "mlb": {"value": 0.612345678, "updated_at": STAMP},
        "kalshi": 0.7,
        "betting_book_count": 4,
    }
    pub = _build(bag, [_obs("mlb", 0.612345678, bag, evidence={"n": 1})])
    assert pub["sources"] is bag
    assert pub["coverage"] == COVERAGE_COMPLETE and pub["uncovered_keys"] == []
    # Only real sources carry a clock; a bare legacy float has none.
    assert pub["source_clocks"] == {"mlb": STAMP, "kalshi": None}
    assert pub["observations"][0]["evidence"] == {"n": 1}
    assert "returned_sources" not in pub["observations"][0]
    assert pub["blend_tier"] == "sources"


def test_a_key_the_last_nonvenue_writer_did_not_return_is_uncovered():
    returned = {"mlb": {"value": 0.6, "updated_at": STAMP}}
    bag = {**returned, "kalshi": 0.8}
    pub = _build(bag, [_obs("mlb", 0.6, returned)])
    assert pub["coverage"] == COVERAGE_UNCOVERED
    assert pub["uncovered_keys"] == ["kalshi"]


def test_removed_lists_only_sources_still_absent_at_commit():
    readded = {"betting": {"value": 0.5, "updated_at": STAMP}}
    pub = _build(
        readded,
        [
            _obs("betting", None, {}, rev=1),
            _obs("stat_model", None, {}, rev=1),
            _obs("betting", 0.5, readded, rev=2),
        ],
    )
    assert pub["removed_sources"] == ["stat_model"]


def test_non_bag_inputs_reach_the_blend_and_the_hash():
    a = _build({}, [_obs("betting", None, {})], opening_home_probability=Decimal("0.55"))
    assert (a["blend_probability"], a["blend_tier"]) == (0.55, "opening")
    assert a["blend_inputs"]["opening_home_probability"] == 0.55
    b = _build({}, [_obs("betting", None, {})], opening_home_probability=Decimal("0.56"))
    c = _build({}, [_obs("betting", None, {})], opening_home_probability=Decimal("0.55"))
    assert a["payload_sha256"] != b["payload_sha256"]
    assert a["payload_sha256"] == c["payload_sha256"]


def test_status_is_part_of_the_identity_payload():
    bag = {"kalshi": 0.8, "betting": 0.4}
    live = _build(bag, [_obs("stat_model", None, bag)])
    done = _build(bag, [_obs("stat_model", None, bag)], status="completed")
    assert (live["event_status"], done["event_status"]) == ("live", "completed")
    assert live["payload_sha256"] != done["payload_sha256"]


def test_evidence_does_not_change_the_payload_identity():
    bag = {"mlb": {"value": 0.6, "updated_at": STAMP}}
    one = _build(bag, [_obs("mlb", 0.6, bag, evidence={"x": 1})])
    two = _build(bag, [_obs("mlb", 0.6, bag, evidence={"x": 2})])
    assert one["payload_sha256"] == two["payload_sha256"]


def test_a_publication_needs_a_write():
    with pytest.raises(ValueError):
        _build({}, [])
