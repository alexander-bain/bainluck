"""Guards for the cross-day boring-rate pooler.

The tool exists because a pooled number is easier to get wrong than a single
one, and every way it goes wrong reads as a cleaner result: a doubled build
looks like more evidence, a UTC midnight looks like one day, a single day
pooled looks like an answer to the multi-day question. Each of those has a test
here, and each is asserted in BOTH directions — the honest case still produces
its number, or the guard is just a way to report nothing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.boring_rate_across_days import (  # noqa: E402
    PoolRefusal,
    _pt_date,
    pool,
    render,
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "boring_rate_across_days.py"


def _sample(at: str, fingerprint: str, boring_names: list[str], window: int = 20, **kw):
    s = {
        "at": at,
        "ok": True,
        "http": 200,
        "window_fingerprint": fingerprint,
        "window_size": window,
        "boring_count": len(boring_names),
        "short_window": window < 20,
        "boring": [
            {"rank": i, "name": n, "quality_class": "low_quality", "reasons": ["x"]}
            for i, n in enumerate(boring_names)
        ],
    }
    s.update(kw)
    return s


def _artifact(tmp_path: Path, name: str, samples: list[dict]) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps({"summary": {}, "samples": samples, "default_reads": []}))
    return p


# --------------------------------------------------------------------------
# The zone. This is the one that would have silently merged cycle 99 into
# cycle 100.
# --------------------------------------------------------------------------


def test_an_evening_pacific_read_carries_the_next_utc_date():
    """The literal cycle-99 timestamp: 04:38Z is the PREVIOUS evening in PT."""
    assert _pt_date("2026-08-19T04:38:19.576055+00:00") == "2026-08-18"
    assert _pt_date("2026-08-19T18:45:00+00:00") == "2026-08-19"


def test_two_artifacts_sharing_a_utc_date_are_still_two_pacific_days(tmp_path):
    """Grouped by UTC these are one day and the tool would refuse. They are two."""
    evening = _artifact(
        tmp_path,
        "evening.json",
        [_sample("2026-08-19T04:38:19+00:00", "aaa", ["Maine State Senate winner?"])],
    )
    midday = _artifact(
        tmp_path,
        "midday.json",
        [_sample("2026-08-19T18:45:00+00:00", "bbb", ["Maine State Senate winner?"])],
    )

    result = pool([evening, midday])

    assert result["grouped_by_timezone"] == "America/Los_Angeles"
    assert result["days"] == 2
    assert sorted(result["per_day"]) == ["2026-08-18", "2026-08-19"]


# --------------------------------------------------------------------------
# The refusal, and its other direction
# --------------------------------------------------------------------------


def test_a_single_pacific_day_is_refused_not_reported(tmp_path):
    one = _artifact(
        tmp_path,
        "one.json",
        [
            _sample("2026-08-19T18:45:00+00:00", "aaa", ["Card A"]),
            _sample("2026-08-19T19:45:00+00:00", "bbb", []),
        ],
    )
    with pytest.raises(PoolRefusal) as exc:
        pool([one])
    assert "ONE Pacific day" in str(exc.value)


def test_two_days_are_reported_rather_than_refused(tmp_path):
    """The other direction: the guard must not simply always refuse."""
    a = _artifact(tmp_path, "a.json", [_sample("2026-08-18T20:00:00+00:00", "aaa", ["Card A"])])
    b = _artifact(tmp_path, "b.json", [_sample("2026-08-19T20:00:00+00:00", "bbb", ["Card A"])])

    result = pool([a, b])

    assert result["pooled"]["rate"] == 0.05  # 2 boring / 40 graded
    assert result["pooled"]["builds"] == 2


def test_zero_countable_builds_is_refused(tmp_path):
    empty = _artifact(
        tmp_path,
        "empty.json",
        [
            {"at": "2026-08-18T20:00:00+00:00", "ok": False, "http": 503},
            _sample("2026-08-19T20:00:00+00:00", "ccc", [], degraded_reason="futures_timeout"),
        ],
    )
    with pytest.raises(PoolRefusal) as exc:
        pool([empty])
    assert "zero countable builds" in str(exc.value)


def test_a_non_census_file_is_refused_by_name(tmp_path):
    p = tmp_path / "notacensus.json"
    p.write_text(json.dumps({"summary": {"boring_rate_at_20": 0.05}}))
    with pytest.raises(PoolRefusal) as exc:
        pool([p])
    assert "not a census artifact" in str(exc.value)


# --------------------------------------------------------------------------
# Denominators and dedupe
# --------------------------------------------------------------------------


def test_the_same_build_on_two_days_counts_once_and_is_named(tmp_path):
    a = _artifact(tmp_path, "a.json", [_sample("2026-08-18T20:00:00+00:00", "same", ["Card A"])])
    b = _artifact(
        tmp_path,
        "b.json",
        [
            _sample("2026-08-19T20:00:00+00:00", "same", ["Card A"]),
            _sample("2026-08-19T21:00:00+00:00", "fresh", []),
        ],
    )

    result = pool([a, b])

    # 2 builds, not 3: the straddling build is one sample.
    assert result["pooled"]["builds"] == 2
    assert result["pooled"]["cards_graded"] == 40
    assert result["per_day"]["2026-08-19"]["builds"] == 1
    repeats = result["deduped"]["cross_day_repeat_builds"]
    assert repeats == [{"fingerprint": "same", "first_day": "2026-08-18", "also_on": "2026-08-19"}]


def test_same_day_repeat_builds_are_counted_and_excluded(tmp_path):
    a = _artifact(
        tmp_path,
        "a.json",
        [
            _sample("2026-08-18T20:00:00+00:00", "dup", ["Card A"]),
            _sample("2026-08-18T20:20:00+00:00", "dup", ["Card A"]),
        ],
    )
    b = _artifact(tmp_path, "b.json", [_sample("2026-08-19T20:00:00+00:00", "other", [])])

    result = pool([a, b])

    assert result["deduped"]["same_day_repeat_builds"] == 1
    assert result["per_day"]["2026-08-18"]["cards_graded"] == 20


def test_failed_degraded_and_short_reads_never_reach_the_denominator(tmp_path):
    a = _artifact(
        tmp_path,
        "a.json",
        [
            _sample("2026-08-18T20:00:00+00:00", "good", ["Card A"]),
            {"at": "2026-08-18T20:10:00+00:00", "ok": False, "http": 503},
            _sample("2026-08-18T20:20:00+00:00", "deg", [], degraded_reason="futures_timeout"),
            _sample("2026-08-18T20:30:00+00:00", "short", ["Card B"], window=3),
        ],
    )
    b = _artifact(tmp_path, "b.json", [_sample("2026-08-19T20:00:00+00:00", "other", [])])

    result = pool([a, b])

    assert result["per_day"]["2026-08-18"]["builds"] == 1
    assert result["per_day"]["2026-08-18"]["cards_graded"] == 20
    assert result["pooled"]["cards_graded"] == 40


def test_the_pooled_rate_is_boring_over_graded_not_a_mean_of_day_rates(tmp_path):
    """Unequal days must not be averaged — that is the classic pooling lie."""
    a = _artifact(
        tmp_path,
        "a.json",
        [
            _sample("2026-08-18T20:00:00+00:00", "a1", ["A"]),
            _sample("2026-08-18T21:00:00+00:00", "a2", ["A"]),
            _sample("2026-08-18T22:00:00+00:00", "a3", ["A"]),
        ],
    )
    b = _artifact(tmp_path, "b.json", [_sample("2026-08-19T20:00:00+00:00", "b1", ["A"] * 5)])

    result = pool([a, b])

    # day1 3/60 = 5%, day2 5/20 = 25%; pooled is 8/80 = 10%, NOT the 15% mean.
    assert result["per_day"]["2026-08-18"]["rate"] == 0.05
    assert result["per_day"]["2026-08-19"]["rate"] == 0.25
    assert result["pooled"]["rate"] == 0.1
    assert result["spread_across_days"] == {"min_rate": 0.05, "max_rate": 0.25}


# --------------------------------------------------------------------------
# Standing defect vs rotation
# --------------------------------------------------------------------------


def test_only_a_card_boring_on_every_day_is_called_standing(tmp_path):
    a = _artifact(
        tmp_path,
        "a.json",
        [_sample("2026-08-18T20:00:00+00:00", "a1", ["Maine State Senate winner?", "One-off"])],
    )
    b = _artifact(
        tmp_path,
        "b.json",
        [_sample("2026-08-19T20:00:00+00:00", "b1", ["Maine State Senate winner?"])],
    )

    result = pool([a, b])

    assert result["boring_on_every_day"] == ["Maine State Senate winner?"]


def test_a_dated_card_rotates_its_name_but_the_reason_class_persists(tmp_path):
    """The real 2026-08-18/19 shape, and the reason per-name persistence is not enough.

    "Will Meta (META) close above $540 on August 19?" is a different NAME every
    morning, so a name-only check reports the whole dated-equity-ladder class as
    rotation. The reasons do not rotate.
    """
    a = _artifact(
        tmp_path,
        "a.json",
        [
            {
                **_sample("2026-08-18T20:00:00+00:00", "a1", []),
                "boring_count": 1,
                "boring": [
                    {
                        "rank": 18,
                        "name": "Will Meta (META) close above $540 on August 18?",
                        "quality_class": "low_quality",
                        "reasons": ["ladder_or_bucket", "daily_equity_direction"],
                    }
                ],
            }
        ],
    )
    b = _artifact(
        tmp_path,
        "b.json",
        [
            {
                **_sample("2026-08-19T20:00:00+00:00", "b1", []),
                "boring_count": 1,
                "boring": [
                    {
                        "rank": 18,
                        "name": "Will Meta (META) close above $540 on August 19?",
                        "quality_class": "low_quality",
                        "reasons": ["ladder_or_bucket", "daily_equity_direction"],
                    }
                ],
            }
        ],
    )

    result = pool([a, b])

    assert result["boring_on_every_day"] == []  # names rotate — correctly
    assert result["boring_reasons_every_day"] == [
        "daily_equity_direction",
        "ladder_or_bucket",
    ]
    assert "daily_equity_direction" in render(result)


def test_a_reason_seen_on_only_one_day_is_not_called_persistent(tmp_path):
    a = _artifact(
        tmp_path,
        "a.json",
        [
            {
                **_sample("2026-08-18T20:00:00+00:00", "a1", []),
                "boring_count": 1,
                "boring": [
                    {"name": "A", "quality_class": "low_quality", "reasons": ["one_off"]}
                ],
            }
        ],
    )
    b = _artifact(
        tmp_path,
        "b.json",
        [
            {
                **_sample("2026-08-19T20:00:00+00:00", "b1", []),
                "boring_count": 1,
                "boring": [
                    {"name": "B", "quality_class": "low_quality", "reasons": ["other"]}
                ],
            }
        ],
    )

    result = pool([a, b])

    assert result["boring_reasons_every_day"] == []


def test_the_served_window_is_pooled_only_when_every_build_carries_it(tmp_path):
    old = _artifact(
        tmp_path, "old.json", [_sample("2026-08-18T20:00:00+00:00", "a1", ["A"])]
    )
    new = _artifact(
        tmp_path,
        "new.json",
        [
            {
                **_sample("2026-08-19T20:00:00+00:00", "b1", ["A"]),
                "served_window_size": 20,
                "served_boring_count": 0,
            }
        ],
    )

    result = pool([old, new])

    assert result["window"] == "futures_only_top20"
    assert result["served_window"]["available"] is False
    assert "1 of 2 countable builds" in result["served_window"]["reason"]
    assert "NOT POOLED" in render(result)


def test_the_served_window_pools_when_every_build_carries_it(tmp_path):
    a = _artifact(
        tmp_path,
        "a.json",
        [
            {
                **_sample("2026-08-18T20:00:00+00:00", "a1", ["A"]),
                "served_window_size": 20,
                "served_boring_count": 0,
            }
        ],
    )
    b = _artifact(
        tmp_path,
        "b.json",
        [
            {
                **_sample("2026-08-19T20:00:00+00:00", "b1", ["A"]),
                "served_window_size": 20,
                "served_boring_count": 1,
            }
        ],
    )

    result = pool([a, b])

    # The futures window says 2/40 = 5%; the served window says 1/40 = 2.5%.
    # Both are reported, and they are not the same number.
    assert result["pooled"]["rate"] == 0.05
    assert result["served_window"] == {
        "available": True,
        "window": "served_top20",
        "slots_graded": 40,
        "boring_cards": 1,
        "rate": 0.025,
    }
    assert "SERVED window (what the visitor scrolls)" in render(result)


def test_render_names_the_zone_it_grouped_by(tmp_path):
    a = _artifact(tmp_path, "a.json", [_sample("2026-08-18T20:00:00+00:00", "a1", ["A"])])
    b = _artifact(tmp_path, "b.json", [_sample("2026-08-19T20:00:00+00:00", "b1", [])])

    text = render(pool([a, b]))

    assert "America/Los_Angeles" in text
    assert "POOLED" in text


# --------------------------------------------------------------------------
# Exit codes — a refusal is 2 (could-not-check), never 0 (gotcha #54)
# --------------------------------------------------------------------------


def test_cli_exits_2_on_a_single_day_and_prints_no_rate(tmp_path):
    one = _artifact(tmp_path, "one.json", [_sample("2026-08-19T18:45:00+00:00", "aaa", ["A"])])
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(one)], capture_output=True, text=True
    )
    assert proc.returncode == 2, proc.stdout
    assert "REFUSED" in proc.stdout
    assert "%" not in proc.stdout


def test_cli_exits_0_and_writes_json_on_a_real_two_day_pool(tmp_path):
    a = _artifact(tmp_path, "a.json", [_sample("2026-08-18T20:00:00+00:00", "a1", ["A"])])
    b = _artifact(tmp_path, "b.json", [_sample("2026-08-19T20:00:00+00:00", "b1", [])])
    out = tmp_path / "pooled.json"

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out), str(a), str(b)],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "POOLED" in proc.stdout
    assert "1/40 = 2.50%" in proc.stdout
    assert json.loads(out.read_text())["days"] == 2


def test_cli_exits_2_when_an_input_is_missing(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "nope.json")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "missing input" in proc.stdout
