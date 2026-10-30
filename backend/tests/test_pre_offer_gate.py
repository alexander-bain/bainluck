"""Exercise refusal boundaries and real subprocesses for the early local gate."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pre_offer_gate", ROOT / "tools/pre_offer_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Preflight test")
    git(tmp_path, "config", "user.email", "preflight@example.invalid")
    (tmp_path / "source").write_text("base")
    git(tmp_path, "add", "source")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def test_exact_checkout_and_dirty_source(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "source").write_text("candidate")
    git(repo, "commit", "-qam", "candidate")
    assert gate.checkout(repo, base, "HEAD")[2] == {"source"}
    with pytest.raises(gate.Refusal, match="not this checkout"):
        gate.checkout(repo, base, base)
    (repo / "untracked").write_text("unreviewed")
    with pytest.raises(gate.Refusal, match="uncommitted/untracked"):
        gate.checkout(repo, base, "HEAD")


def test_missing_and_nonancestor_base(repo):
    with pytest.raises(gate.Refusal, match="exited"):
        gate.checkout(repo, "missing", "HEAD")
    original = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "--orphan", "other")
    git(repo, "commit", "-qm", "unrelated")
    with pytest.raises(gate.Refusal, match="exited 1"):
        gate.checkout(repo, original, "HEAD")


def test_real_child_failure_missing_executable_and_timeout(tmp_path):
    with pytest.raises(gate.Refusal, match="exit 7"):
        gate.execute([sys.executable, "-c", "raise SystemExit(7)"], tmp_path)
    with pytest.raises(gate.Refusal, match="cannot execute"):
        gate.execute([str(tmp_path / "missing")], tmp_path)
    with pytest.raises(gate.Refusal, match="timed out"):
        gate.execute([sys.executable, "-c", "import time; time.sleep(10)"], tmp_path, .05)


def test_actual_workflow_pin_and_unsupported_selector():
    workflow = yaml.safe_load((ROOT / gate.WORKFLOW).read_text())
    assert gate.release_wake_pin(workflow) > 0
    step = next(s for s in workflow["jobs"]["database-integration"]["steps"]
                if gate.COUNT_FILE in s.get("run", ""))
    step["run"] = step["run"].replace("-v -rs", "-k narrow -v -rs")
    with pytest.raises(gate.Refusal, match="selection changed"):
        gate.release_wake_pin(workflow)


@pytest.mark.parametrize("pin", [1, 2])
def test_real_collection_without_test_execution(tmp_path, pin):
    backend = tmp_path / "backend"
    test = backend / gate.COUNT_FILE
    test.parent.mkdir(parents=True)
    test.write_text("def test_one():\n    raise AssertionError('must only collect')\n")
    workflow = tmp_path / gate.WORKFLOW
    workflow.parent.mkdir(parents=True)
    run = (f"if python -m pytest {gate.COUNT_FILE} -v -rs > {gate.COUNT_LOG} 2>&1; then\n"
           f'grep -qE "[^0-9]{pin} passed[,[:space:]]" {gate.COUNT_LOG}\n')
    workflow.write_text(yaml.safe_dump({"jobs": {"database-integration": {"steps": [{"run": run}]}}}))
    if pin == 1:
        gate.check_release_wake(tmp_path, {gate.WORKFLOW})
    else:
        with pytest.raises(gate.Refusal, match="actual collection selects 1"):
            gate.check_release_wake(tmp_path, {gate.WORKFLOW})


def test_main_refuses_midrun_mutation_and_runs_both_children(repo, monkeypatch):
    monkeypatch.setattr(gate, "ROOT", repo)
    commands = []
    def child(command, cwd):
        commands.append((command, cwd))
        if command[0] == "npm":
            (repo / "source").write_text("changed during gate")
        return ""
    monkeypatch.setattr(gate, "execute", child)
    assert gate.main(["HEAD"]) == 1
    assert commands[0][0][3:3 + len(gate.GUARDS)] == list(gate.GUARDS)
    assert commands[1][0][1:] == ["scripts/evals/scan_mutation_residue.py", "--base",
                                 git(repo, "rev-parse", "HEAD"), "--head", git(repo, "rev-parse", "HEAD")]
    assert commands[2][0] == ["npm", "run", "contract"]


def test_first_child_failure_never_emits_pass(repo, monkeypatch, capsys):
    monkeypatch.setattr(gate, "ROOT", repo)
    def fail(*args):
        raise gate.Refusal("guard failed")
    monkeypatch.setattr(gate, "execute", fail)
    assert gate.main(["HEAD"]) == 1
    assert '"early_preflight": "PASS"' not in capsys.readouterr().out


def test_authoritative_manifest_guard_rejects_added_unassigned_ci_step():
    # Reproduce the #994 failure class against the real guard and real inputs.
    guard_spec = importlib.util.spec_from_file_location("postgres_guard", ROOT / "backend/tests/test_ci_postgres_groups.py")
    guard = importlib.util.module_from_spec(guard_spec)
    guard_spec.loader.exec_module(guard)
    jobs, manifest = guard._inputs()
    worker = jobs["database-integration"]
    guard._validate_assignments(worker, manifest)
    worker["steps"].append({"name": "new product DB acceptance", "run": "python -m pytest tests/new.py",
                            "if": "matrix.group == 'shared-tail'"})
    with pytest.raises(AssertionError, match="missing or extra execution unit"):
        guard._validate_assignments(worker, manifest)


def test_configured_selection_is_preserved_and_triggers_binding(tmp_path):
    backend = tmp_path / "backend"
    test = backend / gate.COUNT_FILE
    test.parent.mkdir(parents=True)
    test.write_text("def test_one(): pass\ndef test_two(): pass\n")
    (backend / "pytest.ini").write_text("[pytest]\naddopts = -v -k test_one\n")
    workflow = tmp_path / gate.WORKFLOW
    workflow.parent.mkdir(parents=True)
    run = (f"if python -m pytest {gate.COUNT_FILE} -v -rs > {gate.COUNT_LOG} 2>&1; then\n"
           f'grep -qE "[^0-9]2 passed[,[:space:]]" {gate.COUNT_LOG}\n')
    workflow.write_text(yaml.safe_dump({"jobs": {"database-integration": {"steps": [{"run": run}]}}}))
    with pytest.raises(gate.Refusal, match="actual collection selects 1"):
        gate.check_release_wake(tmp_path, {"backend/pytest.ini"})


def test_malformed_selected_node_receipt_refuses(monkeypatch):
    monkeypatch.setattr(gate, "execute", lambda *args: "PREFLIGHT_NODE_IDS={broken\n")
    with pytest.raises(gate.Refusal, match="invalid collection receipt"):
        gate.check_release_wake(ROOT, {gate.WORKFLOW})


def test_extra_whole_files_are_counted_and_any_other_selector_refuses(tmp_path):
    # #10090 PR #11797: the step names the PM skip-locked file after COUNT_FILE;
    # its pin is the cases of BOTH files, so collection must select both.
    backend = tmp_path / "backend"
    extra = "tests/integration/test_extra_10090_pg.py"
    for name, body in ((gate.COUNT_FILE, "def test_one(): pass\n"),
                       (extra, "def test_two(): pass\ndef test_three(): pass\n")):
        (backend / name).parent.mkdir(parents=True, exist_ok=True)
        (backend / name).write_text(body)
    workflow = tmp_path / gate.WORKFLOW
    workflow.parent.mkdir(parents=True)

    def write(selection, pin):
        run = (f"if python -m pytest {gate.COUNT_FILE} \\\n  {selection} \\\n"
               f"  -v -rs > {gate.COUNT_LOG} 2>&1; then\n"
               f'grep -qE "[^0-9]{pin} passed[,[:space:]]" {gate.COUNT_LOG}\n')
        workflow.write_text(yaml.safe_dump({"jobs": {"database-integration": {"steps": [{"run": run}]}}}))

    write(extra, 3)
    gate.check_release_wake(tmp_path, {"backend/" + extra})
    write(extra, 1)
    with pytest.raises(gate.Refusal, match="actual collection selects 3"):
        gate.check_release_wake(tmp_path, {"backend/" + extra})
    for narrowing in (extra + "::test_two", f"{extra} -k two", gate.COUNT_FILE):
        write(narrowing, 3)
        with pytest.raises(gate.Refusal, match="selection changed"):
            gate.check_release_wake(tmp_path, {gate.WORKFLOW})
