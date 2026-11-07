"""No module dedupes an alert through GitHub's /search API (#12272, #11988, r252).

Production's token gets ``422 Unprocessable Entity`` from search (#11988, logged
Nov 4), and the index is eventually consistent even when it answers (r252). Code
that reads a failed or empty search as "no open issue" files a duplicate every
run: the Horizon sentinel re-filed its open conditions night after night
(#2491, #12075, #12136 and #12260 all declare one fingerprint). The rail
(``sentinel_filing.reconcile_issue``) and the watchdog read the REST list.

A ratchet: the modules below still call search and are listed so the list can
only shrink. A new caller fails the first test; a fixed one must leave the list
(the second test).
"""

from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
SEARCH_ENDPOINT = "api.github.com/search/issues"

STILL_SEARCHING = {
    "routes/admin_file_issue.py",
    "tasks/calibration_sentinel.py",
    "tasks/settled_concept_sentinel.py",
}


def _callers() -> set[str]:
    return {
        path.relative_to(APP).as_posix()
        for path in APP.rglob("*.py")
        if SEARCH_ENDPOINT in path.read_text(encoding="utf-8")
    }


def test_no_new_module_calls_the_search_api():
    assert _callers() <= STILL_SEARCHING


def test_a_module_moved_to_the_rail_leaves_the_list():
    assert STILL_SEARCHING <= _callers()


def test_the_horizon_sentinel_is_off_search():
    assert "tasks/horizon_sentinel.py" not in _callers()
