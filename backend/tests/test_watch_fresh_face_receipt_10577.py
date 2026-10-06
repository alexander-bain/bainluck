"""A green summary cannot omit the real fresh-face activation regression."""
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
MARKERS = (
    "WATCH_UI_STRESS_TYPE=accessibility5", "WATCH_UI_STANDARD_TYPE=large",
    "WATCH_UI_ROUNDING_PAIR=45", "WATCH_UI_ROUNDING_DRAW=46",
    "WATCH_UI_LAUNCHER_COLD=PASS", "WATCH_UI_COMPLICATION_CONTENT=PASS",
    "WATCH_UI_ACTUAL_WIDGET_WARM=PASS", "WATCH_UI_ACTUAL_WIDGET_COLD=PASS",
    "WATCH_UI_ACTUAL_WIDGET_EMPTY=PASS", "WATCH_UI_FRESH_FACE_ACTIVATION=PASS",
    "WATCH_RECTANGULAR_INSTALLED_DETAIL=Saved · 64% · Live",
    "WATCH_UI_CLEAR_SELECTION=PASS", "WATCH_UI_PICKER_RETURN=PASS",
    "WATCH_UI_DISCOVERIES_SAVED=PASS", "WATCH_UI_DISCOVERIES_LARGE=PASS",
    "WATCH_UI_DISCOVERIES_UNSELECTED=PASS", "WATCH_UI_DISCOVERIES_CONTINUATION=PASS",
    "WATCH_UI_DISCOVERIES_RETURN_STANDARD=PASS", "WATCH_UI_DISCOVERIES_RETURN_LARGE=PASS",
    "WATCH_UI_DISCOVERIES_HEADING_STANDARD=PASS", "WATCH_UI_DISCOVERIES_HEADING_LARGE=PASS",
    "WATCH_UI_CIRCULAR_CONTENT=PASS", "WATCH_UI_CIRCULAR_FALLBACK=PASS", "WATCH_UI_ACTUAL_CIRCULAR_SAVED=PASS",
)
CASE = ("Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests "
        "testFreshConfiguredFaceIsActiveBeforeActualLauncherTap]' passed (90.123 seconds).")
SUMMARY = ("Test Suite 'All tests' passed at 2026-10-06 00:00:00.000.\n"
           "\t Executed 17 tests, with 0 failures (0 unexpected) in 1200 seconds\n"
           "** TEST EXECUTE SUCCEEDED **\n")


def gate(log, tmp_path):
    path = tmp_path / "tests.log"
    path.write_text(log)
    harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
    code = harness.split("<<'PYVERIFY'\n", 1)[1].split("\nPYVERIFY", 1)[0]
    return subprocess.run([sys.executable, "-c", code, str(path)],
                          capture_output=True, text=True)


def accepted_log():
    return "\n".join((*MARKERS, CASE, SUMMARY))


def test_seventeen_test_summary_and_real_activation_case_are_accepted(tmp_path):
    log = accepted_log()
    result = gate(log, tmp_path)
    assert result.returncode == 0, result.stderr
    receipt = subprocess.run(
        [sys.executable, str(ROOT / "tools/watch_iphone_receipt.py"),
         "--log", str(tmp_path / "tests.log"), "--exit-code", "0",
         "--sha", "fixture", "--output", str(tmp_path / "receipt.json")],
        capture_output=True, text=True)
    assert receipt.returncode == 0, receipt.stderr
    assert '"tests": 17' in (tmp_path / "receipt.json").read_text()


@pytest.mark.parametrize("marker", [
    "WATCH_UI_FRESH_FACE_ACTIVATION=PASS",
    "WATCH_UI_DISCOVERIES_RETURN_STANDARD=PASS",
    "WATCH_UI_DISCOVERIES_RETURN_LARGE=PASS",
    "WATCH_UI_DISCOVERIES_HEADING_STANDARD=PASS",
    "WATCH_UI_DISCOVERIES_HEADING_LARGE=PASS",
    "WATCH_UI_CIRCULAR_CONTENT=PASS",
    "WATCH_UI_CIRCULAR_FALLBACK=PASS", "WATCH_UI_ACTUAL_CIRCULAR_SAVED=PASS",
])
def test_new_marker_cannot_silently_disappear(tmp_path, marker):
    result = gate(accepted_log().replace(marker, ""), tmp_path)
    assert result.returncode == 1
    assert marker in result.stderr


def test_marker_and_green_summary_cannot_replace_executed_case(tmp_path):
    result = gate(accepted_log().replace(CASE, ""), tmp_path)
    assert result.returncode == 1
    assert "activation regression did not pass" in result.stderr


def test_failed_activation_case_cannot_be_overruled_by_marker(tmp_path):
    result = gate(accepted_log().replace("passed (90.123 seconds)", "failed (90.123 seconds)"), tmp_path)
    assert result.returncode == 1
    assert "activation regression did not pass" in result.stderr
