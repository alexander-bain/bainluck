"""The offline falsifier mirror, proven before a time-gated window consumes it.

## Why this file exists

`scripts/falsifier_offline_mirror.py` exists for one reason: the #2071
censoring-mirror fix is SERVER-side and unmerged, so the live
`/api/admin/heavy-move/falsifier` cannot answer the question Fable's 2026-08-22
directive asked ("re-grade with the censoring mirror fix in place"). The grade is
a pure function of the observations, so the mirror re-runs THIS branch's
`grade_move` over the SAME production task-metrics.

That makes the mirror a load-bearing instrument inside a time-gated read, which
is exactly the situation `test_grade_ruling_110_harness.py` was written for: a
tool first exercised inside the window is not prep.

## The two traps this is written against

1. **A partial payload rendering as a grade.** If one task-metrics fetch fails,
   the absent beat would grade `unreadable` and the run would still produce a
   verdict — a network fact laundered into a statement about the routing
   (gotcha #53). The mirror must refuse the WHOLE payload at exit 3.
2. **Silent drift from the route it mirrors.** If `admin_celery`'s payload gains
   or renames a field the grader reads, the mirror keeps producing a
   confident-looking answer of the wrong shape. So the contract asserted here is
   the one that matters: **`grade_ruling_110.py` must not be able to tell the
   difference**, and the mirror must be honestly self-labelled so no reader
   mistakes it for a second measurement.
"""

from __future__ import annotations

import json

import pytest

from scripts.falsifier_offline_mirror import EXIT_OK, EXIT_UNREADABLE, main
from scripts.grade_ruling_110 import build_report

from app.utils.heavy_routing_falsifier import READ_SET


def _obs(p50_ms: float, n: int = 50, successes: int = 20, failures: int = 0):
    return {
        "successes_24h": successes,
        "failures_24h": failures,
        "recent_durations_ms": [p50_ms] * n,
        "recent_durations_at": [1_787_000_000 + i * 3600 for i in range(n)],
    }


@pytest.fixture()
def fake_fetch(monkeypatch):
    """Serve every READ_SET name from a dict, so no network is touched."""
    served: dict = {name: _obs(120_000.0) for name in READ_SET}

    def _fetch(name):
        val = served[name]
        if isinstance(val, Exception):
            raise val
        return val

    monkeypatch.setattr("scripts.falsifier_offline_mirror._fetch", _fetch)
    monkeypatch.setenv("BAINLUCK_API", "https://example.invalid")
    monkeypatch.setenv("ADMIN_TOKEN", "test-token")
    return served


def test_it_writes_a_payload_grade_ruling_110_can_consume(fake_fetch, tmp_path):
    out = tmp_path / "mirror.json"
    assert main(["--out", str(out)]) == EXIT_OK
    payload = json.loads(out.read_text())

    # The real contract: the grader consumes it without special-casing.
    report = build_report(payload)
    assert {g["prediction"] for g in report["grades"]} == {"P3", "P4", "P5"}
    assert report["falsifier_verdict"] == payload["verdict"]


def test_every_field_grade_ruling_110_reads_is_present(fake_fetch, tmp_path):
    out = tmp_path / "mirror.json"
    assert main(["--out", str(out)]) == EXIT_OK
    payload = json.loads(out.read_text())

    for key in ("verdict", "reason", "horizon", "movers", "beats"):
        assert key in payload, f"grade_ruling_110 reads {key!r}"
    for key in ("age_since_move_h", "counters_clear_the_move"):
        assert key in payload["horizon"]
    for beat in payload["beats"]:
        # `verdict` drives coverage counting; `censored_side` and
        # `observed_clip_rate` are #2071's reporting half and must survive.
        for key in ("task", "verdict", "ratio", "censored_side", "observed_clip_rate"):
            assert key in beat, f"beat row is missing {key!r}"


def test_one_failed_fetch_refuses_the_WHOLE_payload_rather_than_grading_partially(
    fake_fetch, tmp_path
):
    """A network fact must never be laundered into a fact about the routing."""
    victim = READ_SET[0]
    fake_fetch[victim] = OSError("connection reset")

    out = tmp_path / "mirror.json"
    assert main(["--out", str(out)]) == EXIT_UNREADABLE
    assert not out.exists(), "a refused read must not leave a partial payload behind"


def test_it_refuses_without_credentials_rather_than_fetching_nothing(monkeypatch, tmp_path):
    monkeypatch.delenv("BAINLUCK_API", raising=False)
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    assert main(["--out", str(tmp_path / "x.json")]) == EXIT_UNREADABLE


def test_the_payload_labels_itself_as_a_regrade_not_a_second_measurement(
    fake_fetch, tmp_path
):
    """Doctrine clause 14's trap, inverted.

    The mirror re-runs the GRADING over production's own observations. Reporting
    it as an independent confirmation would be manufacturing a second
    measurement out of one, so the payload has to say what it is in-band — a
    caveat that lives only in a report is a caveat the next reader does not get.
    """
    out = tmp_path / "mirror.json"
    assert main(["--out", str(out)]) == EXIT_OK
    mirror = json.loads(out.read_text())["_mirror"]

    assert mirror["not_a_second_measurement"] is True
    assert "task-metrics" in mirror["measurement_source"]
    assert mirror["expires_when"], "it must name the condition that retires it"


def test_it_reads_every_name_in_READ_SET_not_just_the_baseline_names(fake_fetch, tmp_path):
    """The movers were once absent from the dict the panel interrogated, so
    `samples` was 0 by construction (#2071). READ_SET exists to stop that, and a
    mirror that fetched only the baseline names would reintroduce it."""
    seen: list[str] = []
    original = fake_fetch.copy()

    def _fetch(name):
        seen.append(name)
        return original[name]

    import scripts.falsifier_offline_mirror as mod

    mod._fetch = _fetch
    try:
        assert main(["--out", str(tmp_path / "m.json")]) == EXIT_OK
    finally:
        pass
    assert sorted(seen) == sorted(READ_SET)
