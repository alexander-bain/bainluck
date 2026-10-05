"""#10516 — the Calibration Sentinel's sample rows must be a usable loser driver.

The weather/single cohort flagged with its 90-100% band resolving at 49.9%, and
the evidence pack printed twelve 0.995 WINNERS (``ORDER BY cp DESC`` over a
tie). The diagnosis then needed "provenance-bound suspect/loser IDs from a
retained row-level artifact" and there was none: the samples carried no ids,
collapsed NULL into a loss, lived only in the filing-day body, and were not in
the durable finding at all.

These tests run ``_sample_rows``' real SQL on SQLite (the category-only cohort
WHERE is portable), and pin the three places the rows must reach.
"""

import asyncio

from sqlalchemy import create_engine, text

from app.tasks.calibration_sentinel import (
    _finalize_cohort,
    _new_cohort,
    _run_calibration_sentinel,
    _sample_rows,
    build_issue_body,
    build_reobservation_comment,
    sample_rows_section,
)


class _SyncBackedSession:
    """An async-session stand-in that runs the statement on a real SQLite engine."""

    def __init__(self, conn):
        self._conn = conn

    async def execute(self, stmt, params=None):
        return self._conn.execute(stmt, params or {})


def _seed(conn):
    conn.execute(text("""
        CREATE TABLE futures_markets (
            id INTEGER PRIMARY KEY, source TEXT, external_id TEXT, status TEXT,
            llm_sport_category TEXT, mutually_exclusive BOOLEAN
        )"""))
    conn.execute(text("""
        CREATE TABLE futures_outcomes (
            id INTEGER PRIMARY KEY, market_id INTEGER, name TEXT,
            calibration_probability REAL, opening_probability REAL,
            is_winner BOOLEAN, resolution_source TEXT
        )"""))
    # Fourteen 0.995 winners (more than the 12-row limit, so a cp-only sort can
    # fill the whole sample with them), then a lost row and an ungraded row at
    # LOWER prices — the exact shape that hid the losers on #10516.
    rows = [(i, f"KXTEMPNYCH-W{i}", 0.995, True, "api_settlement") for i in range(1, 15)]
    rows += [
        (101, "KXTEMPNYCH-LOST", 0.97, False, "api_settlement"),
        (102, "KXTEMPNYCH-NULL", 0.96, None, None),
    ]
    for mid, ext, cp, win, rs in rows:
        conn.execute(
            text("INSERT INTO futures_markets VALUES (:id, 'kalshi', :ext, 'resolved', 'weather', 0)"),
            {"id": mid, "ext": ext},
        )
        conn.execute(
            text("INSERT INTO futures_outcomes VALUES (:oid, :mid, 'Yes', :cp, NULL, :win, :rs)"),
            {"oid": mid * 10, "mid": mid, "cp": cp, "win": win, "rs": rs},
        )
    # A second-structure market (two priced outcomes) that the single filter must drop.
    conn.execute(text("INSERT INTO futures_markets VALUES (200, 'kalshi', 'KXBIN', 'resolved', 'weather', 0)"))
    conn.execute(text("INSERT INTO futures_outcomes VALUES (2000, 200, 'Yes', 0.99, NULL, 0, 'api_settlement')"))
    conn.execute(text("INSERT INTO futures_outcomes VALUES (2001, 200, 'No', 0.01, NULL, 1, 'api_settlement')"))


def _run_sample(limit=12):
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        _seed(conn)
        return asyncio.run(
            _sample_rows(
                _SyncBackedSession(conn),
                {"provenance": "futures", "category": "weather", "structure": "single"},
                limit=limit,
            )
        )


def test_high_cp_non_winners_sort_ahead_of_tied_winners():
    rows = _run_sample()
    assert len(rows) == 12
    # Both non-winners lead, even though every winner is priced higher.
    assert [r["market"] for r in rows[:2]] == ["KXTEMPNYCH-LOST", "KXTEMPNYCH-NULL"]
    assert all(r["is_winner"] is True for r in rows[2:])
    # The binary market never enters a structure=single sample.
    assert all(r["market"] != "KXBIN" for r in rows)


def test_null_grade_stays_null_and_ids_ride_every_row():
    rows = {r["market"]: r for r in _run_sample()}
    assert rows["KXTEMPNYCH-LOST"]["is_winner"] is False
    assert rows["KXTEMPNYCH-NULL"]["is_winner"] is None
    assert rows["KXTEMPNYCH-LOST"]["outcome_id"] == 1010
    assert rows["KXTEMPNYCH-LOST"]["market_id"] == 101
    assert all(isinstance(r["outcome_id"], int) and isinstance(r["market_id"], int) for r in rows.values())


_SAMPLES = [
    {"source": "kalshi", "market": "KXTEMPNYCH-LOST", "outcome": "Yes", "cp": 0.97,
     "is_winner": False, "resolution_source": "api_settlement", "outcome_id": 1010, "market_id": 101},
    {"source": "kalshi", "market": "KXTEMPNYCH-NULL", "outcome": "Yes", "cp": 0.96,
     "is_winner": None, "resolution_source": None, "outcome_id": 1020, "market_id": 102},
    {"source": "kalshi", "market": "KXTEMPNYCH-W1", "outcome": "Yes", "cp": 0.995,
     "is_winner": True, "resolution_source": "api_settlement", "outcome_id": 10, "market_id": 1},
]


def _row_for(lines, market):
    (line,) = [ln for ln in lines if f"`{market}`" in ln]
    return [c.strip() for c in line.strip("|").split("|")]


def test_section_marks_lost_ungraded_and_won_distinctly_with_ids():
    lines = sample_rows_section(_SAMPLES)
    assert _row_for(lines, "KXTEMPNYCH-LOST")[4:] == ["✗", "api_settlement", "1010", "101"]
    assert _row_for(lines, "KXTEMPNYCH-NULL")[4:] == ["—", "—", "1020", "102"]
    assert _row_for(lines, "KXTEMPNYCH-W1")[4:] == ["✓", "api_settlement", "10", "1"]


def test_section_tolerates_rows_cached_before_ids_existed():
    legacy = {k: v for k, v in _SAMPLES[0].items() if k not in ("outcome_id", "market_id")}
    assert _row_for(sample_rows_section([legacy]), "KXTEMPNYCH-LOST")[6:] == ["—", "—"]
    assert sample_rows_section([]) == []


def _cohort(samples):
    return {
        "fingerprint": "9cc54e3c23ba",
        "dims": {"provenance": "futures", "category": "weather", "structure": "single"},
        "mce": 21.77,
        "total_n": 1235,
        "published_mce": 23.17,
        "published_n": 1127,
        "disposition": "real_break",
        "disposition_why": "both over threshold",
        "sample_rows": samples,
    }


def test_reobservation_comment_carries_the_fresh_sample():
    comment = build_reobservation_comment(_cohort(_SAMPLES))
    assert "`KXTEMPNYCH-LOST`" in comment
    assert "| 1010 | 101 |" in comment
    # And stays the bare three-line recurrence when the sweep sampled nothing.
    assert "Sample high-cp rows" not in build_reobservation_comment(_cohort([]))


def test_filed_body_uses_the_same_section():
    dims = {"provenance": "futures", "category": "weather", "structure": "single"}
    c = _new_cohort(tuple(sorted(dims.items())), {})
    c["buckets"][9] = {"bucket": 9, "n": 487, "winners": 243, "sum_prob": 483.6}
    c["total_n"] = 487
    c["min_created_at"] = None
    _finalize_cohort(c, now_ts=1_800_000_000.0)
    c["sample_rows"] = _SAMPLES
    body = build_issue_body(c, explained_by=None, coverage=0.087)
    assert "\n".join(sample_rows_section(_SAMPLES)) in body


def test_durable_finding_retains_the_sample_rows():
    # The finding dict is what publish_sentinel_evidence persists; the sample must
    # be one of its keys, read from the cohort that sampled it.
    import inspect

    src = inspect.getsource(_run_calibration_sentinel)
    finding_block = src[src.index("finding = {"):src.index('stats["findings"].append(finding)')]
    assert '"sample_rows": c.get("sample_rows") or []' in finding_block
