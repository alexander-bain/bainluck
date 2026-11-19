"""The red-master alarm (Fable, Nov 16 item 3): the line it posts, from real logs.

The two specimens are the shapes of the Nov 15-16 red masters: run 43797011147
(the shard-hints limit) and run 43878166099 (the CPU sampler), as their job logs
print them — Actions timestamps and pytest's colour escapes included.
"""

import json
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
    assert "HOLD ends at the first of: the re-run passing; the next server \"live\" line" in line
    assert "`/api/health` serves" in line and "Fable or Alex" in line
    assert "Ruling 241: A — This alarm re-ran the failed jobs once automatically" in line
    assert "when the re-run passes, the HOLD ends immediately" in line
    assert "Builder E moves it within the hour to `flaky-canary`" in line
    assert "7 days to repair or delete it" in line
    assert first.endswith("[run 43797011147](https://github.com/o/r/actions/runs/43797011147)")
    assert "`0e3c5e4aa5`" in line and "#12687" in line
    assert line.rstrip().endswith(alarm.marker(43797011147, 1))


def test_a_red_job_outside_deploys_needs_reports_without_holding_the_server():
    """The bot's point on #12788: when the run's own `deploy` job succeeded, the server
    got the change, so the line reports the failure and must not freeze server merges."""
    line = _line(failed_jobs=["flaky-canary"], deployed=True)
    first = line.splitlines()[0]
    assert first.startswith("stuck: master red, `tests/test_ci_shard.py::")
    assert "HOLD" not in line
    assert "Ruling 241: A" not in line
    assert "`deploy` job still succeeded, so the server slot is not held" in line
    held = _line(deployed=False)
    assert "HOLD (server)" in held.splitlines()[0]
    assert "`deploy` job did not succeed" in held


def test_main_reads_deploy_from_the_runs_own_jobs(monkeypatch, capsys):
    monkeypatch.setenv("REPO", "o/r")
    monkeypatch.setenv("NOW_LINES_ISSUE", "12779")
    monkeypatch.setenv("RUN_ID", "1")
    """`deployed` comes from the run's jobs list: a failed shard with deploy skipped holds,
    a failed canary with deploy green does not. Dry-run never triggers a re-run."""
    calls = []

    def fake_gh(jobs):
        def _gh(path, *rest, body=None):
            calls.append((path, rest, body))
            if path.endswith("/jobs?filter=latest&per_page=100"):
                return json.dumps({"jobs": jobs})
            if "/logs" in path:
                return ""
            return json.dumps({
                "id": 1, "run_attempt": 1, "event": "push", "head_branch": "master",
                "conclusion": "failure", "head_sha": "a" * 40, "display_title": "t",
                "html_url": "https://github.com/o/r/actions/runs/1",
            })
        return _gh

    monkeypatch.setattr(alarm, "_gh", fake_gh([
        {"id": 7, "name": "backend-tests (6)", "conclusion": "failure"},
        {"id": 8, "name": "deploy", "conclusion": "skipped"},
    ]))
    assert alarm.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "HOLD (server)" in out and "dry-run: not triggered" in out
    assert not any("rerun-failed-jobs" in p for p, _, _ in calls)

    monkeypatch.setattr(alarm, "_gh", fake_gh([
        {"id": 7, "name": "flaky-canary", "conclusion": "failure"},
        {"id": 8, "name": "deploy", "conclusion": "success"},
    ]))
    assert alarm.main(["--dry-run"]) == 0
    assert "HOLD" not in capsys.readouterr().out


def test_main_reruns_failed_jobs_once_on_attempt_1_and_never_on_attempt_2(monkeypatch):
    """Ruling 241: A: attempt 1 triggers rerun-failed-jobs once and says so in the stuck line;
    attempt 2 never re-runs again, and a duplicate alarm never double-triggers."""
    monkeypatch.setenv("REPO", "o/r")
    monkeypatch.setenv("NOW_LINES_ISSUE", "12779")
    monkeypatch.setenv("RUN_ID", "99")

    def run_once(attempt, *, comments=(), rerun_error=None, deployed=False):
        posted = []
        reruns = []

        def fake_gh(path, *rest, body=None):
            if path.endswith("/jobs?filter=latest&per_page=100"):
                return json.dumps({"jobs": [
                    {"id": 7, "name": "backend-tests (2)", "conclusion": "failure"},
                    {"id": 8, "name": "deploy", "conclusion": "success" if deployed else "skipped"},
                ]})
            if "/logs" in path:
                return "FAILED tests/test_x.py::test_t - AssertionError\n"
            if "/issues/12779/comments?per_page=100" in path:
                return "\n".join(json.dumps(c) for c in comments)
            if path.endswith("/rerun-failed-jobs"):
                reruns.append((path, rest))
                if rerun_error:
                    raise RuntimeError(rerun_error)
                return ""
            if path.endswith("/issues/12779/comments"):
                posted.append(body["body"])
                return "{}"
            return json.dumps({
                "id": 99, "run_attempt": attempt, "event": "push", "head_branch": "master",
                "conclusion": "failure", "head_sha": "b" * 40, "display_title": "fix (#1)",
                "html_url": "https://github.com/o/r/actions/runs/99",
            })

        monkeypatch.setattr(alarm, "_gh", fake_gh)
        assert alarm.main([]) == 0
        return reruns, posted

    reruns, posted = run_once(1)
    assert reruns == [("repos/o/r/actions/runs/99/rerun-failed-jobs", ("--method", "POST"))]
    assert len(posted) == 1
    assert "re-ran the failed jobs once automatically" in posted[0]

    # Already posted for attempt 1: neither re-runs nor posts again.
    reruns2, posted2 = run_once(1, comments=[posted[0]])
    assert reruns2 == [] and posted2 == []

    # Attempt 2 failed too: posts, never triggers a second automatic re-run.
    reruns3, posted3 = run_once(2, comments=[posted[0]])
    assert reruns3 == [] and len(posted3) == 1
    assert "no further auto-rerun" in posted3[0] and "(attempt 2)" in posted3[0]

    # Deploy succeeded (non-blocking job red): no HOLD and no re-run.
    reruns4, posted4 = run_once(1, deployed=True)
    assert reruns4 == [] and len(posted4) == 1 and "HOLD" not in posted4[0]

    # Rerun API failure still posts the stuck line so nobody is blind.
    reruns5, posted5 = run_once(1, rerun_error="gh api exited 403")
    assert len(reruns5) == 1 and len(posted5) == 1
    assert "Automatic re-run failed" in posted5[0]


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
    assert wf["permissions"] == {"actions": "write", "contents": "read", "issues": "write"}
    assert alarm.RED_CONCLUSIONS == ("failure", "timed_out")
