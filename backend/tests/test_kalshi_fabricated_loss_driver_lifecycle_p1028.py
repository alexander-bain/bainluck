"""The drain driver must not overwrite its own backups, and must not understate its sweep.

CAL-P1028, discharging the two FOLLOW-UPs named by CERT-2015:
``CAL-P1026-OUTPUT-COLLISION-GUARD`` and the reporting half of
``CAL-P1026-RESTORE-CHECK-FAIL-CLOSED`` (the rate denominator).

Both defects are real and both were found by reading the artifacts of the
completed CAL-P1026 sweep, not by inspection:

1. **The driver could overwrite its own undo.** ``batch-NNN-dryrun.json`` IS the
   backup and ``batch-NNN-apply.json`` IS the one-command undo. The driver wrote
   both unconditionally, so a resume launched with a ``--start-batch`` that had
   already been used renumbered from there and walked over the previous run's
   slots. Losing those files does not lose a log — it removes the only way to
   reverse an apply that already happened against production.

2. **``summary.json`` reads as a sweep total and is not one.** ``totals`` is
   zeroed at every launch and ``summary.json`` is written on clean exit, so a
   resume reports only from ``--start-batch``. The real CAL-P1026 sweep ran 720
   batches; its ``summary.json`` describes 420. Anyone quoting it reports **12**
   unexplained absences where the sweep found **804** — a 67× understatement of
   the residue, in the direction that makes the data look healthier.

These tests are offline by construction: the driver checks its environment, then
its output directory, and only then makes its first network call, so every path
exercised here stops before the first ``_curl``.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / \
    "drive_kalshi_fabricated_loss_drain.py"
_SPEC = importlib.util.spec_from_file_location("drive_kalshi_fabricated_loss_drain", _SCRIPT)
driver = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(driver)


def _run(monkeypatch, argv, *, with_env=True):
    """Invoke the driver's main() with argv, and make a network call a test failure."""
    monkeypatch.setattr(driver.sys, "argv", ["drive"] + argv)
    if with_env:
        monkeypatch.setenv("BAINLUCK_API", "https://example.invalid")
        monkeypatch.setenv("ADMIN_TOKEN", "not-a-real-token")

    def _no_network(*a, **k):
        # Halt is the driver's own clean-stop signal, so a run that gets this far
        # exits 1 having written summary.json. rc==1 therefore means "passed the
        # preflight and started work", and rc==2 means "refused before any work" —
        # which is exactly the distinction these tests need, without a live call.
        raise driver.Halt("network stubbed by the test")

    monkeypatch.setattr(driver, "_curl", _no_network)
    return driver.main()


# ---------------------------------------------------------------------------
# 1. The collision guard
# ---------------------------------------------------------------------------

def test_refuses_to_start_when_a_banked_artifact_would_be_overwritten(tmp_path, monkeypatch):
    """The exact shape of the accident: resuming onto batch numbers already banked."""
    (tmp_path / "batch-007-dryrun.json").write_text('{"backup": true}')
    (tmp_path / "batch-007-apply.json").write_text('{"undo": true}')

    rc = _run(monkeypatch, ["--out", str(tmp_path), "--start-batch", "5"])

    assert rc == 2, "a collision must refuse to start, not run and overwrite"
    # The incumbents are untouched — the whole point of refusing.
    assert json.loads((tmp_path / "batch-007-dryrun.json").read_text()) == {"backup": True}
    assert json.loads((tmp_path / "batch-007-apply.json").read_text()) == {"undo": True}
    assert not (tmp_path / "summary.json").exists()


def test_refusal_names_the_start_batch_that_would_have_worked(tmp_path, monkeypatch, capsys):
    """A guard that only says 'no' makes the operator guess, and guessing is the bug."""
    for n in (7, 8, 12):
        (tmp_path / f"batch-{n:03d}-dryrun.json").write_text("{}")

    _run(monkeypatch, ["--out", str(tmp_path), "--start-batch", "5"])

    out = capsys.readouterr().out
    assert "REFUSING TO START" in out
    assert "correct --start-batch for this directory is 13" in out, \
        "must name the next free batch (highest banked + 1), not just refuse"


def test_start_batch_above_the_banked_range_is_allowed(tmp_path, monkeypatch):
    """A correct resume must not be blocked — the guard is about collision, not about resuming."""
    (tmp_path / "batch-007-dryrun.json").write_text("{}")

    rc = _run(monkeypatch, ["--out", str(tmp_path), "--start-batch", "8"])

    assert rc == 1, "should proceed to work and halt on the stubbed network, not refuse"


def test_overwrite_artifacts_is_the_documented_escape_hatch(tmp_path, monkeypatch):
    (tmp_path / "batch-007-dryrun.json").write_text("{}")

    rc = _run(monkeypatch, ["--out", str(tmp_path), "--start-batch", "5",
                            "--overwrite-artifacts"])

    assert rc == 1, "explicit override must proceed past the preflight"


def test_fresh_directory_is_never_blocked(tmp_path, monkeypatch):
    rc = _run(monkeypatch, ["--out", str(tmp_path / "fresh"), "--start-batch", "1"])
    assert rc == 1


def test_unrelated_files_do_not_trip_the_guard(tmp_path, monkeypatch):
    """progress.jsonl, summary.json and the second-source log always exist on a resume."""
    (tmp_path / "progress.jsonl").write_text('{"batch": 1}\n')
    (tmp_path / "summary.json").write_text("{}")
    (tmp_path / "restore-second-source.jsonl").write_text("{}\n")

    assert _run(monkeypatch, ["--out", str(tmp_path), "--start-batch", "2"]) == 1


# ---------------------------------------------------------------------------
# 2. _bank() — the backstop must never destroy what it is protecting
# ---------------------------------------------------------------------------

def test_bank_parks_the_new_payload_rather_than_losing_it(tmp_path):
    """By the time _bank refuses an apply artifact, the apply may already have run.

    Raising and dropping the payload would destroy the undo for a mutation that
    already happened — strictly worse than the overwrite. So the incumbent is kept
    AND the new copy is parked.
    """
    target = tmp_path / "batch-007-apply.json"
    target.write_text('{"incumbent": true}')

    with pytest.raises(driver.ArtifactCollision) as e:
        driver._bank(target, {"fresh": True}, overwrite=False)

    assert json.loads(target.read_text()) == {"incumbent": True}
    parked = [p for p in tmp_path.glob("batch-007-apply.CONFLICT-*.json")]
    assert len(parked) == 1, "the refused payload must survive somewhere"
    assert json.loads(parked[0].read_text()) == {"fresh": True}
    assert parked[0].name in str(e.value), "the operator must be told where it went"


def test_bank_writes_normally_when_there_is_no_collision(tmp_path):
    target = tmp_path / "batch-001-dryrun.json"
    driver._bank(target, {"ok": 1}, overwrite=False)
    assert json.loads(target.read_text()) == {"ok": 1}


def test_bank_overwrites_only_when_told_to(tmp_path):
    target = tmp_path / "batch-001-dryrun.json"
    target.write_text('{"old": true}')
    driver._bank(target, {"new": True}, overwrite=True)
    assert json.loads(target.read_text()) == {"new": True}


# ---------------------------------------------------------------------------
# 3. The sweep total must span resumes
# ---------------------------------------------------------------------------

def _progress(tmp_path, rows):
    p = tmp_path / "progress.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def test_sweep_totals_span_every_resume_not_just_the_last(tmp_path):
    """The CAL-P1026 shape in miniature: a big first leg, a small second leg.

    The per-invocation totals would report the second leg only. That is what
    turned 804 unexplained absences into a reported 12.
    """
    rows = [{"batch": i, "examined": 10, "answered": 0, "unexplained_absence": 10,
             "leg_verdicts": {}} for i in range(1, 61)]
    rows += [{"batch": i, "examined": 10, "answered": 10, "unexplained_absence": 0,
              "leg_verdicts": {"confirmed_loss": 3}} for i in range(61, 71)]

    t = driver._sweep_totals(_progress(tmp_path, rows))

    assert t["batches"] == 70
    assert t["examined"] == 700
    assert t["unexplained_absence"] == 600, "the early legs must not vanish from the total"
    assert t["batch_range"] == {"first": 1, "last": 70}
    assert t["leg_verdicts"] == {"confirmed_loss": 30}


def test_sweep_totals_tolerate_a_truncated_final_line(tmp_path):
    """A killed run leaves a half-written line; it must not take the whole total with it."""
    p = tmp_path / "progress.jsonl"
    p.write_text('{"batch": 1, "examined": 10, "answered": 10}\n{"batch": 2, "exam')

    t = driver._sweep_totals(p)

    assert t["batches"] == 1 and t["examined"] == 10


def test_sweep_totals_on_a_missing_log_says_so_rather_than_reporting_zero_work(tmp_path):
    t = driver._sweep_totals(tmp_path / "nope.jsonl")
    assert t["batches"] == 0 and "note" in t


def test_summary_names_the_batches_it_covers(tmp_path, monkeypatch):
    """The disclosure that stops summary.json being read as the sweep.

    A resume that does no work still has to say which slice it speaks for, so a
    reader can tell the difference between 'the sweep found 12' and 'this leg
    found 12'.
    """
    _progress(tmp_path, [{"batch": i, "examined": 10, "answered": 10,
                          "unexplained_absence": 0} for i in range(1, 31)])
    (tmp_path / "batch-001-dryrun.json").write_text("{}")

    _run(monkeypatch, ["--out", str(tmp_path), "--start-batch", "31"])

    s = json.loads((tmp_path / "summary.json").read_text())
    assert s["covers_batches"]["first"] == 31, "must disclose that it starts at 31, not 1"
    assert s["sweep_totals"]["batches"] == 30, "and must carry the whole sweep beside it"
    assert s["sweep_totals"]["examined"] == 300
    assert s["totals"]["examined"] == 0, "its own leg genuinely did no work"
