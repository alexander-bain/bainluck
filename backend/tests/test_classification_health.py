"""Fixture-first tests for the pure classification-health contract (UX-P001).

These pin the product contract:
* pure backfill debt (empty stored tags, inline classifies fine) is NEVER a
  defect and NEVER alarms — a 48%-stored-coverage population with zero eligible
  defects is GREEN (healthy-with-debt);
* one proved eligible defect is RED with a concrete reason + count;
* an incomplete census with zero defects is YELLOW (incomplete evidence);
* a failed census is UNKNOWN (fail-closed).
"""

import pytest

from app.utils.classification_health import (
    AUTHORITY_DISAGREE,
    GREEN,
    INVALID,
    MISSING,
    RED,
    UNKNOWN,
    VERSION,
    YELLOW,
    KindCensus,
    RecordInput,
    classify_record,
    evaluate,
    unknown_envelope,
)


# ── classify_record: the per-record defect contract ────────────────────

def test_clean_record_with_full_inline_authority_has_no_defect():
    rec = RecordInput(
        kind="futures",
        id=1,
        inline_tags=["sport:basketball", "league:nba", "category:championship"],
        stored_tags=["sport:basketball", "league:nba", "category:championship"],
    )
    assert classify_record(rec) == frozenset()


def test_empty_stored_tags_but_inline_ok_is_debt_not_defect():
    # The whole point: persisted tags empty, inline authority classifies fine.
    rec = RecordInput(
        kind="event",
        id=2,
        inline_tags=["sport:basketball", "league:nba"],
        stored_tags=[],
    )
    assert classify_record(rec) == frozenset()


def test_missing_when_inline_yields_no_sport():
    rec = RecordInput(
        kind="futures",
        id=3,
        inline_tags=[],  # inline authority cannot establish a sport identity
        stored_tags=[],
    )
    assert classify_record(rec) == frozenset({MISSING})


def test_invalid_when_stored_tag_is_out_of_vocabulary():
    rec = RecordInput(
        kind="futures",
        id=4,
        inline_tags=["sport:basketball"],
        stored_tags=["sport:basketball", "sport:quidditch"],  # not in vocab
    )
    assert classify_record(rec) == frozenset({INVALID})


def test_authority_disagree_when_stored_identity_contradicts_inline():
    rec = RecordInput(
        kind="event",
        id=5,
        inline_tags=["sport:football", "league:nfl"],
        stored_tags=["sport:basketball", "league:nba"],
    )
    assert classify_record(rec) == frozenset({AUTHORITY_DISAGREE})


def test_authority_disagree_not_fired_when_inline_lacks_the_namespace():
    # Conservative: only proved contradictions count. Inline has no league, so a
    # stored league is not flagged (could be legitimately richer).
    rec = RecordInput(
        kind="futures",
        id=6,
        inline_tags=["sport:basketball"],
        stored_tags=["sport:basketball", "league:nba"],
    )
    assert classify_record(rec) == frozenset()


def test_multiple_defects_collected():
    rec = RecordInput(
        kind="futures",
        id=7,
        inline_tags=[],  # no sport → MISSING
        stored_tags=["sport:quidditch"],  # out of vocab → INVALID
    )
    assert classify_record(rec) == frozenset({MISSING, INVALID})


def test_classify_record_never_raises_on_garbage():
    rec = RecordInput(
        kind="futures",
        id=8,
        inline_tags=["nocolon", 123, None],  # type: ignore[list-item]
        stored_tags=[None, "sport:basketball"],  # type: ignore[list-item]
    )
    # nocolon/None skipped; inline has no valid sport → MISSING, no crash.
    assert classify_record(rec) == frozenset({MISSING})


# ── evaluate: the verdict contract ─────────────────────────────────────

def _events(records, eligible_total=None, verified=None, complete=True):
    n = len(records)
    return KindCensus(
        eligible_total=eligible_total if eligible_total is not None else n,
        verified=verified if verified is not None else n,
        census_complete=complete,
        records=records,
    )


def test_green_healthy_with_debt_48pct_coverage_zero_defects():
    # 100 eligible; 52 have empty stored tags (48% stored coverage) but all
    # inline-classify. Complete census, zero defects → GREEN, not "attention".
    records = []
    for i in range(100):
        stored = [] if i < 52 else ["sport:basketball", "league:nba"]
        records.append(
            RecordInput(
                kind="futures",
                id=i,
                inline_tags=["sport:basketball", "league:nba"],
                stored_tags=stored,
            )
        )
    env = evaluate(
        events=_events([], eligible_total=0, verified=0, complete=True),
        futures=_events(records, eligible_total=100, verified=100, complete=True),
        generated_at="2026-08-04T00:00:00+00:00",
    )
    assert env["verdict"] == GREEN
    assert env["version"] == VERSION
    assert env["census_complete"] is True
    assert env["actionable"]["count"] == 0
    assert env["eligible"] == {
        "numerator": 100,
        "denominator": 100,
        "events": 0,
        "futures": 100,
    }


def test_red_one_proved_eligible_defect_with_reason_and_count():
    good = RecordInput(
        kind="futures", id=1,
        inline_tags=["sport:basketball"], stored_tags=[],
    )
    bad = RecordInput(
        kind="futures", id=2,
        inline_tags=[], stored_tags=[],  # MISSING
    )
    env = evaluate(
        events=_events([], eligible_total=0, verified=0, complete=True),
        futures=_events([good, bad], eligible_total=2, verified=2, complete=True),
        generated_at="2026-08-04T00:00:00+00:00",
    )
    assert env["verdict"] == RED
    assert env["actionable"]["count"] == 1
    assert env["actionable"]["reasons"] == {MISSING: 1}
    assert env["actionable"]["representative_ids"] == [
        {"kind": "futures", "id": 2, "reasons": [MISSING]}
    ]


def test_red_even_when_census_incomplete():
    # A proved defect reads RED regardless of completeness.
    bad = RecordInput(kind="event", id=9, inline_tags=[], stored_tags=[])
    env = evaluate(
        events=_events([bad], eligible_total=1000, verified=1, complete=False),
        futures=_events([], eligible_total=0, verified=0, complete=True),
        generated_at="2026-08-04T00:00:00+00:00",
    )
    assert env["verdict"] == RED
    assert env["census_complete"] is False


def test_yellow_incomplete_census_zero_defects():
    good = RecordInput(kind="futures", id=1, inline_tags=["sport:golf"], stored_tags=[])
    env = evaluate(
        events=_events([], eligible_total=0, verified=0, complete=True),
        futures=_events([good], eligible_total=5000, verified=1, complete=False),
        generated_at="2026-08-04T00:00:00+00:00",
    )
    assert env["verdict"] == YELLOW
    assert env["reason"] == "census_incomplete"
    assert env["eligible"]["numerator"] == 1
    assert env["eligible"]["denominator"] == 5000


def test_representative_ids_bounded_to_ten():
    records = [
        RecordInput(kind="futures", id=i, inline_tags=[], stored_tags=[])
        for i in range(25)
    ]
    env = evaluate(
        events=_events([], eligible_total=0, verified=0, complete=True),
        futures=_events(records, eligible_total=25, verified=25, complete=True),
        generated_at="2026-08-04T00:00:00+00:00",
    )
    assert env["verdict"] == RED
    assert env["actionable"]["count"] == 25
    assert len(env["actionable"]["representative_ids"]) == 10


def test_unknown_envelope_is_fail_closed():
    env = unknown_envelope("db_error", "2026-08-04T00:00:00+00:00")
    assert env["verdict"] == UNKNOWN
    assert env["census_complete"] is False
    assert env["version"] == VERSION
    assert env["actionable"]["count"] == 0
