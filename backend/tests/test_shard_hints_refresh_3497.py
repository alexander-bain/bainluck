"""#3497's refresh half — the machinery that moves the shard hints' NUMERATOR.

#5220 stopped the staleness guard reddening master as the suite grows: it counts
unmeasured files instead of a ratio against a growing denominator, and it warns
at 150 long before it fails at 600. That bought runway; it did not stop the
decay. Measured across 19 hours on 2026-09-11/12, `measured` did not move at all
— 1,654 — while the suite went 1,655 -> 1,722 files, because the numerator only
ever moved when a human remembered to run `--record`.

`.github/workflows/shard-hints-refresh.yml` moves it automatically. These are the
properties that make that safe to run unattended, which is a higher bar than
making it work: an unattended refresh COMMITS its result, so every way the
result can be quietly wrong has to be a refusal rather than a warning.

The three that would actually have shipped broken:

  1. the archive holds every shard log TWICE, so the obvious selection doubles
     every duration and reports success;
  2. a partial set of shard logs does not degrade the file, it DELETES a
     quarter of the suite's measurements and writes the rest as a fresh census;
  3. without pytest's collection census the weights come from printed durations
     alone, and pytest hides everything under 0.005s — so files of fast tests
     record at ~0s and get packed as free.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

BACKEND = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND / "scripts" / "ci_shard.py"
WORKFLOW = BACKEND.parent / ".github" / "workflows" / "shard-hints-refresh.yml"


def _load():
    spec = importlib.util.spec_from_file_location("ci_shard_refresh_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ci_shard = _load()


# A duration line exactly as a shard prints it, with the Actions timestamp that
# every downloaded log carries.
def _dur(path: str, secs: str = "1.5") -> str:
    return f"2026-09-12T11:49:57.5647990Z {secs}s call {path}::TestX::test_y"


def _archive(tmp_path: Path, shards: int = 4, *, flat_copies: bool = True) -> Path:
    """An unpacked Actions log archive, laid out the way GitHub really lays it out.

    Measured against run 34709301550: a per-job DIRECTORY of step logs, plus a
    flat top-level copy of each whole job beside it. Both match `*backend-tests*`.
    """
    root = tmp_path / "logs"
    root.mkdir()
    for i in range(1, shards + 1):
        job = root / f"backend-tests ({i})"
        job.mkdir()
        (job / "1_Set up job.txt").write_text("2026-09-12T11:00:00.0Z setting up\n")
        (job / f"4_Run tests (shard {i}-{shards}).txt").write_text(
            _dur(f"tests/test_shard{i}.py") + "\n"
        )
        if flat_copies:
            # The duplicate. Same content, top level, no directory.
            (root / f"{i}_backend-tests ({i}).txt").write_text(
                _dur(f"tests/test_shard{i}.py") + "\n"
            )
    # A neighbouring job that must never be swept in.
    other = root / "frontend-build"
    other.mkdir()
    (other / "3_Build.txt").write_text("2026-09-12T11:00:00.0Z built\n")
    return root


# --------------------------------------------------------------------------
# 1. The duplicate in the archive
# --------------------------------------------------------------------------

def test_each_shard_log_is_selected_exactly_once(tmp_path):
    """The regression: both archive layouts match, and doubling reports success.

    Asserted on the DURATION LINES the selection yields, not on the file count —
    the harm is a 2x in what `--record` sums, so that is the quantity to pin. A
    test on "how many paths came back" would pass just as happily against a
    selection that returned the flat copies INSTEAD of the directories.
    """
    root = _archive(tmp_path, shards=4)
    step_logs, job_dirs = ci_shard.shard_log_files(root)
    assert job_dirs == 4

    pat = re.compile(r"\d+\.\d+s call (tests/\S+\.py)::")
    seen: list[str] = []
    for p in step_logs:
        seen += pat.findall(p.read_text())

    assert sorted(seen) == [f"tests/test_shard{i}.py" for i in range(1, 5)], (
        f"each shard's durations must appear exactly once; got {sorted(seen)}"
    )
    # And nothing from a neighbouring job, which would add a second measurement
    # for any file it shares and inflate that file's weight.
    assert all("frontend-build" not in str(p) for p in step_logs)


def test_the_archive_really_does_carry_the_duplicate(tmp_path):
    """The fixture is only worth what it reproduces.

    Without this, `_archive` could stop emitting flat copies — through an edit or
    a refactor — and the test above would keep passing while guarding nothing.
    It is the strawman check for the fixture, not an assertion about the code.
    """
    root = _archive(tmp_path, shards=4)
    flat = [p for p in root.iterdir() if p.is_file() and "backend-tests" in p.name]
    assert len(flat) == 4, "the fixture must reproduce GitHub's duplicate top-level copies"

    naive = sorted(p for p in root.rglob("*.txt") if "backend-tests" in str(p))
    selected, _ = ci_shard.shard_log_files(root)
    assert len(naive) == 2 * len(selected) - 4 or len(naive) > len(selected), (
        "the naive glob must pick up strictly more than the real selection"
    )


# --------------------------------------------------------------------------
# 2. A partial set of shard logs
# --------------------------------------------------------------------------

@pytest.mark.parametrize("present,expected", [(3, 4), (1, 4), (5, 4)])
def test_a_shard_count_mismatch_refuses(tmp_path, present, expected, capsys):
    """`--record` REPLACES the file, so a missing shard is a deletion.

    Three of four logs does not produce a slightly worse hint file; it produces
    one with a quarter of the suite's measurements gone, written as though it
    were a complete census. The next `--verify` then reports those files as
    unmeasured, which reads as ordinary decay rather than as a bad write.
    """
    root = _archive(tmp_path, shards=present)
    args = argparse.Namespace(shard_logs=str(root), expect=expected)
    rc = ci_shard.cmd_shard_logs(args)
    assert rc == 1
    assert "expected" in capsys.readouterr().out


def test_an_archive_with_no_shard_jobs_refuses(tmp_path, capsys):
    """A frontend-scoped run skips the shards. Zero logs is a loud stop, not an empty success."""
    root = tmp_path / "logs"
    (root / "frontend-build").mkdir(parents=True)
    (root / "frontend-build" / "3_Build.txt").write_text("built\n")
    rc = ci_shard.cmd_shard_logs(argparse.Namespace(shard_logs=str(root), expect=None))
    assert rc == 1
    assert "no `backend-tests*` job directories" in capsys.readouterr().out


def test_the_matching_case_succeeds_and_prints_the_paths(tmp_path, capsys):
    """The positive control: without it every refusal above is satisfied by a
    function that refuses unconditionally."""
    root = _archive(tmp_path, shards=4)
    rc = ci_shard.cmd_shard_logs(argparse.Namespace(shard_logs=str(root), expect=4))
    out = capsys.readouterr().out
    assert rc == 0
    assert len([ln for ln in out.splitlines() if ln.strip()]) == 8  # 2 step logs x 4 shards


# --------------------------------------------------------------------------
# 3. The census, and the unattended write
# --------------------------------------------------------------------------

def _record_with_census(
    monkeypatch, tmp_path, census_stdout: str, *, require: bool, returncode: int = 0
):
    """Run `--record` with the pytest collection census stubbed to `census_stdout`."""
    durations = tmp_path / "durations.json"
    sentinel = '{"files": {"tests/test_pre_existing.py": 9.0}}'
    durations.write_text(sentinel)
    monkeypatch.setattr(ci_shard, "DURATIONS_FILE", durations)
    monkeypatch.setattr(
        ci_shard.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            stdout=census_stdout, stderr="import error in tests/test_x.py", returncode=returncode
        ),
    )
    log = tmp_path / "shards.log"
    log.write_text(_dur("tests/test_alpha.py") + "\n")
    rc = ci_shard.cmd_record(
        argparse.Namespace(record=str(log), require_census=require)
    )
    return rc, durations, sentinel


def test_require_census_refuses_to_write_when_the_census_is_empty(monkeypatch, tmp_path, capsys):
    """Gotcha #53: a warning is only a warning if somebody is reading.

    Without the census, weights are printed durations alone — and pytest hides
    everything under 0.005s, so a file of 500 fast unit tests records at ~0s and
    is packed as free. A human running `--record` sees that scroll past and can
    judge it. The workflow commits it.

    The assertion is that the FILE IS UNTOUCHED, not merely that the exit code is
    1: a non-zero exit after the write has already happened would leave the bad
    hints on disk for the next reader, and the workflow's own diff check would
    then propose them.
    """
    rc, durations, sentinel = _record_with_census(
        monkeypatch, tmp_path, census_stdout="", require=True
    )
    assert rc == 1
    assert durations.read_text() == sentinel, "the degraded write must not have happened"
    assert "census empty" in capsys.readouterr().out


def test_without_the_flag_the_lenient_behaviour_is_unchanged(monkeypatch, tmp_path, capsys):
    """The strictness is opt-in by the caller that needs it.

    Interactive `--record` keeps warning and writing; only the unattended caller
    asks to be refused. Pinning this stops a later tightening from silently
    breaking the hand-run path the failing guard's own message tells people to use.
    """
    rc, durations, sentinel = _record_with_census(
        monkeypatch, tmp_path, census_stdout="", require=False
    )
    assert rc == 0
    assert durations.read_text() != sentinel, "the lenient path must still write"
    assert "::warning::collection census empty" in capsys.readouterr().out


def test_a_census_that_errored_is_refused_even_though_it_collected_files(monkeypatch, tmp_path, capsys):
    """CERT-2752's named follow-up: partial is more dangerous than empty.

    `--collect-only` exits non-zero when some file fails to import while the rest
    collect fine. `n_tests` is then populated and the emptiness check passes — but
    every file that failed to collect is missing, so it records from printed
    durations alone with no sub-threshold estimate and is packed lighter than it
    is. The bad write arrives through the door marked "census present", which is
    why a non-empty census is not on its own sufficient.
    """
    census = "tests/test_alpha.py::test_one\ntests/test_alpha.py::test_two\n"
    rc, durations, sentinel = _record_with_census(
        monkeypatch, tmp_path, census_stdout=census, require=True, returncode=2
    )
    assert rc == 1
    assert durations.read_text() == sentinel, "a partial census must not be written"
    out = capsys.readouterr().out
    assert "PARTIAL" in out
    assert "exited 2" in out


def test_a_partial_census_still_writes_for_the_interactive_caller(monkeypatch, tmp_path, capsys):
    """The strictness stays opt-in, and the warning still names what happened."""
    census = "tests/test_alpha.py::test_one\n"
    rc, durations, sentinel = _record_with_census(
        monkeypatch, tmp_path, census_stdout=census, require=False, returncode=2
    )
    assert rc == 0
    assert durations.read_text() != sentinel
    assert "census exited 2" in capsys.readouterr().out


def test_a_healthy_census_writes_under_require_census(monkeypatch, tmp_path):
    """Positive control: `--require-census` must not be a blanket refusal."""
    census = "tests/test_alpha.py::test_one\ntests/test_alpha.py::test_two\n"
    rc, durations, sentinel = _record_with_census(
        monkeypatch, tmp_path, census_stdout=census, require=True
    )
    assert rc == 0
    written = json.loads(durations.read_text())["files"]
    assert "tests/test_alpha.py" in written


# --------------------------------------------------------------------------
# 4. `--staleness`, and the #3497 property it must not reintroduce
# --------------------------------------------------------------------------

def _staleness(monkeypatch, capsys, n_files: int, n_unmeasured: int) -> dict:
    files = [f"tests/test_{i}.py" for i in range(n_files)]
    weights = {f: 1.0 for f in files[: n_files - n_unmeasured]}
    monkeypatch.setattr(ci_shard, "discover_test_files", lambda: files)
    monkeypatch.setattr(ci_shard, "load_durations", lambda: weights)
    assert ci_shard.cmd_staleness(argparse.Namespace()) == 0
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("n_files", [200, 2_000, 200_000])
def test_the_staleness_verdict_does_not_depend_on_the_suite_size(monkeypatch, capsys, n_files):
    """#3497 itself, now for the command the automation reads.

    Identical ABSOLUTE staleness at suite sizes three orders of magnitude apart
    must give an identical verdict. Under the old ratio it did not: 10 unmeasured
    files passed in a 10,000-file suite and failed in a 30-file one, which is how
    a push that broke nothing took master red for every lane at once.

    This is the property that would be lost if `--staleness` ever recomputed its
    own verdict from the constants instead of calling the shared pair.
    """
    got = _staleness(monkeypatch, capsys, n_files, n_unmeasured=200)
    assert got["unmeasured"] == 200
    assert got["needs_refresh"] is True   # 200 > warn 150
    assert got["stale"] is False          # 200 < fail 600


@pytest.mark.parametrize(
    "unmeasured",
    [
        0,
        ci_shard.STALE_HINTS_WARN_UNMEASURED,
        ci_shard.STALE_HINTS_WARN_UNMEASURED + 1,
        ci_shard.STALE_HINTS_MAX_UNMEASURED,
        ci_shard.STALE_HINTS_MAX_UNMEASURED + 1,
    ],
)
def test_staleness_agrees_with_the_shared_verdict_pair(monkeypatch, capsys, unmeasured):
    """The two callers cannot drift apart — including exactly ON each threshold.

    Both thresholds are strict `>`, so the boundary value is NOT over the line.
    That is the one place an independently-written comparison would differ from
    the shared pair while agreeing everywhere else.
    """
    got = _staleness(monkeypatch, capsys, n_files=1_000, n_unmeasured=unmeasured)
    assert got["needs_refresh"] is ci_shard.hints_need_refresh(unmeasured)
    assert got["stale"] is ci_shard.hints_are_stale(unmeasured)
    assert got["warn_at"] == ci_shard.STALE_HINTS_WARN_UNMEASURED
    assert got["fail_at"] == ci_shard.STALE_HINTS_MAX_UNMEASURED


# --------------------------------------------------------------------------
# 5. The workflow's own wiring
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def workflow() -> dict:
    assert WORKFLOW.exists(), f"{WORKFLOW} is missing"
    # PyYAML parses the `on:` key as the boolean True (YAML 1.1). Read it back
    # under whichever key survived rather than asserting on a key that is not
    # there — the trap that makes workflow tests quietly assert nothing.
    doc = yaml.safe_load(WORKFLOW.read_text())
    doc["_on"] = doc.get("on", doc.get(True))
    assert doc["_on"] is not None, "could not find the workflow's trigger block"
    return doc


def test_the_refresh_is_not_on_a_cron(workflow):
    """MEASURED, not preferred: this repo's scheduler is ~4h late.

    #5662 measured all 100 `event=schedule` runs over 2026-09-02..09-12 — 0 of 98
    fired within five minutes of their slot, delay min/median/max 19m / 239m /
    359m, with `created_at == run_started_at` so the lateness is the scheduler
    itself. A cron here would fire hours after some unrelated master sha.

    It is also the wrong SHAPE: the input this job needs is a specific CI run's
    logs, and `workflow_run` hands it the run id. A schedule would have to go
    hunting for a run and choose one.
    """
    triggers = workflow["_on"]
    assert "schedule" not in triggers, (
        "a cron cannot serve this job: the repo's scheduler runs a measured 239-minute "
        "median behind its slot, and the trigger is also the data source"
    )
    assert "workflow_run" in triggers
    assert triggers["workflow_run"]["workflows"] == ["CI"]


def test_only_a_green_master_push_is_a_valid_source(workflow):
    """CI runs on `pull_request` and on every branch.

    A PR's logs describe that branch's suite, and the refresh would be committed
    against master. The gate has to name all three of conclusion, event and
    branch; any one of them missing admits a source that does not match.
    """
    guard = workflow["jobs"]["refresh"]["if"]
    for needed in (
        "workflow_run.conclusion == 'success'",
        "workflow_run.event == 'push'",
        "workflow_run.head_branch == 'master'",
    ):
        assert needed in guard, f"the job guard must require {needed}"


def test_the_cheap_gate_runs_before_anything_expensive(workflow):
    """The cost argument is an ORDERING, so assert the ordering.

    This fires on every green master push — ~31 a day — and does real work
    roughly weekly. That is only affordable because the staleness read is stdlib
    and comes first. A cheap gate placed after `pip install -r requirements.txt`
    is not a cheap gate, and nothing about the job's output would say so.
    """
    steps = workflow["jobs"]["refresh"]["steps"]
    names = [s.get("name", s.get("uses", "")) for s in steps]
    gate = next(i for i, s in enumerate(steps) if s.get("id") == "staleness")
    install = next(i for i, n in enumerate(names) if "Install dependencies" in str(n))
    assert gate < install, f"staleness gate must precede the install; got {names}"


def test_every_step_after_the_gate_is_held_by_it(workflow):
    """Otherwise the HOLD path stops being a hold.

    A step added below the gate without the `if:` runs on all ~31 pushes a day,
    and if it is one of the writing steps it runs when there is nothing to
    propose. The summary step is exempt: it is `if: always()` on purpose, so a
    failed run still says what it was doing.
    """
    steps = workflow["jobs"]["refresh"]["steps"]
    gate = next(i for i, s in enumerate(steps) if s.get("id") == "staleness")
    for step in steps[gate + 1:]:
        cond = str(step.get("if", ""))
        assert "steps.staleness.outputs.due" in cond or cond == "always()", (
            f"step {step.get('name')!r} is not gated on the staleness verdict (if: {cond!r})"
        )


def test_the_refresh_records_with_the_census_required(workflow):
    """The unattended write must be the strict one.

    `--record` without `--require-census` warns and writes. This job commits what
    it writes, so the flag is the difference between a refusal and a hint file of
    ~0s weights that looks like a measurement.
    """
    steps = workflow["jobs"]["refresh"]["steps"]
    record = next(s for s in steps if s.get("name") == "Record")
    assert "--require-census" in record["run"]


def test_the_branch_is_pushed_before_the_pr_is_attempted(workflow):
    """The branch is the deliverable; the PR is a convenience that may be refused.

    This repo reads `can_approve_pull_request_reviews: false`, the same switch as
    "Allow GitHub Actions to create and approve pull requests", so `gh pr create`
    under `GITHUB_TOKEN` may simply be forbidden. If the PR attempt came first and
    the step stopped there, every firing would throw away the expensive half —
    the log download, the census and the record — and the next run would redo it.

    Pushing first makes a refused PR cost a click instead of a rerun. Asserted as
    an ordering because that is exactly what the property is.
    """
    steps = workflow["jobs"]["refresh"]["steps"]
    run = next(s for s in steps if str(s.get("name", "")).startswith("Open (or update)"))["run"]
    assert "git push --force origin" in run
    assert "gh pr create" in run
    assert run.index("git push --force origin") < run.index("gh pr create"), (
        "the refreshed branch must be pushed before the PR is attempted"
    )


# --------------------------------------------------------------------------
# 6. The refusal path, EXECUTED (CERT-2752's required repair + test)
# --------------------------------------------------------------------------
#
# The structural tests above read the YAML. These run the step's actual shell
# against stubbed `git` and `gh`, because the property under test is a runtime
# ordering and an exit code, and neither is visible in the document.
#
# The defect this closes: the first version caught `gh pr create`'s refusal and
# exited 0. The refreshed hints then sat on a branch nobody was told about while
# master kept decaying toward the hard stop — a GREEN run that silently needed a
# human, which is the same shape as #5662's "stay green and sync nothing".

_GIT_STUB = r"""#!/usr/bin/env bash
echo "git $*" >> "$STUB_LOG"
case "$1 $2" in
  # There ARE changes to propose, so the step does not take its early exit.
  "diff --quiet") exit 1 ;;
esac
exit 0
"""

_GH_STUB = r"""#!/usr/bin/env bash
echo "gh $*" >> "$STUB_LOG"
case "$1 $2" in
  "pr view")   exit "${STUB_PR_VIEW_RC:-1}" ;;
  "pr create") echo "$STUB_PR_CREATE_MSG"; exit "${STUB_PR_CREATE_RC:-1}" ;;
  "pr edit")   exit "${STUB_PR_EDIT_RC:-0}" ;;
esac
exit 0
"""


def _run_pr_step(tmp_path, **env):
    """Execute the 'Open (or update) the refresh PR' step with git/gh stubbed."""
    doc = yaml.safe_load(WORKFLOW.read_text())
    step = next(
        s for s in doc["jobs"]["refresh"]["steps"]
        if str(s.get("name", "")).startswith("Open (or update)")
    )
    # GitHub expression interpolation is the runner's job, not bash's.
    script = re.sub(r"\$\{\{[^}]*\}\}", "175", step["run"])

    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in (("git", _GIT_STUB), ("gh", _GH_STUB)):
        f = bindir / name
        f.write_text(body)
        f.chmod(0o755)

    runner_temp = tmp_path / "rt"
    runner_temp.mkdir()
    (runner_temp / "staleness-after.json").write_text('{"unmeasured": 0}')
    summary = tmp_path / "summary.md"
    summary.touch()
    log = tmp_path / "stub.log"
    log.touch()

    script_file = tmp_path / "step.sh"
    script_file.write_text(script)

    import os
    import subprocess

    proc = subprocess.run(
        ["bash", str(script_file)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "RUNNER_TEMP": str(runner_temp),
            "GITHUB_STEP_SUMMARY": str(summary),
            "STUB_LOG": str(log),
            "RUN_ID": "34709301550",
            "REPO": "alexander-bain/bainluck",
            "SOURCE_SHA": "deadbeef",
            "STUB_PR_CREATE_MSG": "GitHub Actions is not permitted to create or approve pull requests",
            **env,
        },
    )
    return proc, log.read_text(), summary.read_text()


def test_a_refused_pr_creation_fails_loudly_after_the_branch_is_preserved(tmp_path):
    """CERT-2752's required test. Four properties, all on one real execution.

    A green run whose work needs a human is worse than a red one, because only
    the red is ever looked at. But failing BEFORE the branch is pushed would
    throw away the download, the census and the record — so the order matters as
    much as the exit code, and both are asserted here rather than inferred.
    """
    proc, log, summary = _run_pr_step(
        tmp_path, STUB_PR_VIEW_RC="1", STUB_PR_CREATE_RC="1"
    )

    # 1. It fails. This is the repair.
    assert proc.returncode != 0, (
        f"a refused PR must not exit 0.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )

    # 2. The branch was pushed, and pushed BEFORE the PR was attempted — so the
    #    expensive half is banked and a retry is a click, not a rerun.
    assert "git push --force origin ci/shard-hints-refresh" in log, log
    assert log.index("git push --force") < log.index("gh pr create"), (
        f"the branch must be pushed before the PR is attempted:\n{log}"
    )

    # 3. The work is recoverable by hand, and the summary says exactly how.
    assert "ci/shard-hints-refresh" in summary
    assert "gh pr create --base master --head ci/shard-hints-refresh" in summary
    assert "nothing needs redoing" in summary

    # 4. The failure explains itself where a reader will be looking — the log —
    #    rather than only in a summary tab.
    assert "::error::" in proc.stdout
    assert "REFUSED" in proc.stdout


def test_the_step_succeeds_when_the_pr_can_be_created(tmp_path):
    """Positive control.

    Without it, the repair above is satisfied by a step that always fails — and
    a workflow that is permanently red is one nobody reads either.
    """
    proc, log, summary = _run_pr_step(
        tmp_path, STUB_PR_VIEW_RC="1", STUB_PR_CREATE_RC="0"
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "git push --force origin ci/shard-hints-refresh" in log
    assert "::error::" not in proc.stdout


def test_updating_an_already_open_pr_succeeds(tmp_path):
    """The rolling-proposal path: the branch already has a PR, so update its body.

    This is the common case after the first firing, and it must not be swept into
    the failure branch by the repair above.
    """
    proc, log, _ = _run_pr_step(
        tmp_path, STUB_PR_VIEW_RC="0", STUB_PR_EDIT_RC="0"
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "gh pr edit" in log
    assert "gh pr create" not in log


def test_a_failed_update_of_an_open_pr_is_also_loud(tmp_path):
    """The other way the PR half can fail silently.

    `gh pr edit` failing leaves an OPEN PR carrying a stale body — describing a
    different run, a different sha and a different unmeasured count — which is
    more misleading than no PR at all.
    """
    proc, _, _ = _run_pr_step(
        tmp_path, STUB_PR_VIEW_RC="0", STUB_PR_EDIT_RC="1"
    )
    assert proc.returncode != 0, f"stdout:\n{proc.stdout}"


def test_the_step_holds_when_there_is_nothing_to_propose(tmp_path):
    """If the hints are already current on this sha, exit 0 and touch nothing.

    Proven by the absence of a push, not by the exit code alone — exit 0 is also
    what a successful run returns.
    """
    git_noop = _GIT_STUB.replace('"diff --quiet") exit 1 ;;', '"diff --quiet") exit 0 ;;')
    doc = yaml.safe_load(WORKFLOW.read_text())
    step = next(
        s for s in doc["jobs"]["refresh"]["steps"]
        if str(s.get("name", "")).startswith("Open (or update)")
    )
    import os
    import subprocess

    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "git").write_text(git_noop)
    (bindir / "git").chmod(0o755)
    (bindir / "gh").write_text(_GH_STUB)
    (bindir / "gh").chmod(0o755)
    rt = tmp_path / "rt"
    rt.mkdir()
    log = tmp_path / "stub.log"
    log.touch()
    sf = tmp_path / "step.sh"
    sf.write_text(re.sub(r"\$\{\{[^}]*\}\}", "175", step["run"]))
    proc = subprocess.run(
        ["bash", str(sf)], capture_output=True, text=True, cwd=tmp_path,
        env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}",
             "RUNNER_TEMP": str(rt), "GITHUB_STEP_SUMMARY": str(tmp_path / "s.md"),
             "STUB_LOG": str(log), "RUN_ID": "1", "REPO": "o/r", "SOURCE_SHA": "abc"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "git push" not in log.read_text(), "nothing should be pushed when there is no change"


def test_the_checkout_pins_the_sha_whose_logs_are_read(workflow):
    """The census comes from the CHECKED-OUT tree; the durations come from the LOGS.

    If those are two different shas, files added in between are collected by the
    census, get a weight of `n_tests x 0.0025s` with no measurement behind it, and
    are then counted as `measured` — so they are packed as very nearly free AND
    they stop the staleness signal from reporting them. Measured on a real
    archive: 1,016 of 1,751 files had no printed duration line at all, so this is
    the majority path, not an edge case.
    """
    steps = workflow["jobs"]["refresh"]["steps"]
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout"))
    assert "workflow_run.head_sha" in str(checkout["with"]["ref"])
