"""The red-master alarm (Fable, Nov 16 item 3): the line it posts, from real logs.

The two specimens are the shapes of the Nov 15-16 red masters: run 43797011147
(the shard-hints limit) and run 43878166099 (the CPU sampler), as their job logs
print them — Actions timestamps and pytest's colour escapes included.
"""

import sys
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts"))

import master_red_alarm as alarm  # noqa: E402

WORKFLOW = BACKEND.parent / ".github" / "workflows" / "master-red-alarm.yml"

SAMPLER_LOG = (
    "2026-11-16T14:01:04.8396402Z tests/test_loop_cpu_sampler_10090.py ...F...  [ 60%]\n"
    "2026-11-16T14:03:11.1000000Z =========================== short test summary info ============================\n"
    "2026-11-16T14:03:11.1000001Z \x1b[31mFAILED\x1b[0m tests/test_loop_cpu_sampler_10090.py::"
    "test_samples_are_not_pulled_onto_the_frame_that_makes_syscalls[prof] - AssertionError: (0.72, 0.94)\n"
    "2026-11-16T14:03:11.1000002Z ===== 1 failed, 11860 passed, 527 skipped in 1500.00s =====\n"
)


def test_failing_node_ids_come_from_the_short_summary_with_timestamps_and_colour():
    assert alarm.failed_tests(SAMPLER_LOG) == [
        "tests/test_loop_cpu_sampler_10090.py::"
        "test_samples_are_not_pulled_onto_the_frame_that_makes_syscalls[prof]"
    ]


def test_collection_errors_count_and_repeats_collapse():
    log = (
        "ERROR tests/test_a.py - ImportError: x\n"
        "FAILED tests/test_b.py::t - assert 1\n"
        "FAILED tests/test_b.py::t - assert 1\n"
        "tests/test_c.py FAILED\n"  # a progress line, not the summary
    )
    assert alarm.failed_tests(log) == ["tests/test_a.py", "tests/test_b.py::t"]


def test_verbose_gate_output_without_a_summary_is_read_too():
    """The real-Postgres gates run `-v -rs`: no FAILED summary line, only this."""
    log = (
        "2026-11-11T15:58:01.0Z tests/integration/test_pm_withdrawal_peer_publication_and_startup_10090_pg.py"
        "::test_publish_error_retains_owed_notification ERROR [ 96%]\n"
        "2026-11-11T15:58:01.1Z tests/integration/test_x_pg.py::test_ok PASSED [ 97%]\n"
        "2026-11-11T15:58:02.0Z ===== 26 passed, 1 error in 32.43s =====\n"
    )
    assert alarm.failed_tests(log) == [
        "tests/integration/test_pm_withdrawal_peer_publication_and_startup_10090_pg.py"
        "::test_publish_error_retains_owed_notification"
    ]


def _line(**over):
    args = dict(
        run_id=43797011147,
        attempt=1,
        run_url="https://github.com/o/r/actions/runs/43797011147",
        sha="0e3c5e4aa56803dccbd2f3c0fa693547021dae96",
        title="#219E: the hourly Polymarket poll walks every active event by keyset (#12687)",
        conclusion="failure",
        tests=["tests/test_ci_shard.py::test_the_shipped_hints_are_not_stale_right_now"],
        failed_jobs=["backend-tests (4)"],
    )
    args.update(over)
    return alarm.compose(**args)


def test_the_line_is_the_stuck_shape_fable_asked_for():
    line = _line()
    first = line.splitlines()[0]
    assert first.startswith("stuck: master red, HOLD (server), `tests/test_ci_shard.py::")
    assert "HOLD ends at the next server" in line
    assert first.endswith("[run 43797011147](https://github.com/o/r/actions/runs/43797011147)")
    assert "`0e3c5e4aa5`" in line and "#12687" in line
    assert line.rstrip().endswith(alarm.marker(43797011147, 1))


def test_no_test_line_names_the_failed_jobs_and_long_lists_are_capped():
    assert "failed jobs: `backend-tests (4)`" in _line(tests=[])
    many = [f"tests/test_{i}.py::t" for i in range(8)]
    assert "and 3 more" in _line(tests=many)


def test_one_line_per_run_and_attempt():
    posted = [_line()]
    assert alarm.already_posted(posted, 43797011147, 1)
    assert not alarm.already_posted(posted, 43797011147, 2)
    assert not alarm.already_posted(posted, 43878166099, 1)
    assert "(attempt 2)" in _line(attempt=2)


def test_pr_reference_reads_squash_and_merge_titles():
    assert alarm.pr_reference("fix: x (#12633) (#12773)") == "#12773"
    assert alarm.pr_reference("Merge pull request #12752 from a/b") == "#12752"
    assert alarm.pr_reference("docs: no number") is None


def test_the_workflow_fires_only_on_a_red_push_to_master_and_posts_to_one_issue():
    wf = yaml.safe_load(WORKFLOW.read_text())
    on = wf[True] if True in wf else wf["on"]  # PyYAML reads `on:` as True
    assert on["workflow_run"] == {
        "workflows": ["CI"], "types": ["completed"], "branches": ["master"]
    }
    job = wf["jobs"]["alarm"]
    cond = " ".join(job["if"].split())
    for clause in (
        "github.event.workflow_run.event == 'push'",
        "github.event.workflow_run.head_branch == 'master'",
        "github.event.workflow_run.conclusion == 'failure'",
        "github.event.workflow_run.conclusion == 'timed_out'",
    ):
        assert clause in cond
    assert "cancelled" not in cond
    assert wf["env"]["NOW_LINES_ISSUE"] == "12779"
    assert wf["permissions"] == {"actions": "read", "contents": "read", "issues": "write"}
    assert alarm.RED_CONCLUSIONS == ("failure", "timed_out")
