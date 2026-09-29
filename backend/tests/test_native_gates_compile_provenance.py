"""Guard tests for `tools/native-gates.sh` compile provenance (#9659).

WHAT THIS GUARDS
----------------
Build 32 (63455d0dfa, 2026-09-29) passed its full suite, 4356 tests / 0 failures
in 37.3 minutes, and the gate still failed: 15 changed test files were "NOT SEEN"
in the test log, because the run was incremental and Xcode had compiled them in
an earlier run. The only remedy the gate offered was another 37 minutes. Native
closed the gap by hand with a targeted compile of those 15 files plus their 210
tests, in 19 seconds.

#9659 makes that the gate's own behaviour, without weakening it:

* cached compile evidence is accepted only with an established identity (this
  run finished green; its own log names the test target's output-file map; the
  map is Debug-iphonesimulator/BainLuckTests; it lists the file's exact path in
  this tree; the object exists and is not older than the source; and a ledger row
  says a gate run saw this same content compile into that same object);
* anything short of that goes to ONE bounded fallback that recompiles only those
  files and runs only their XCTestCase classes, never an automatic full rerun;
* every full run writes a manifest, and `--check-manifest` says whether its
  evidence can stand for an identical, clean iOS tree.

HOW THESE TESTS AVOID BEING VACUOUS
-----------------------------------
The script's `--selftest-provenance` drives the REAL functions against a real
git tree, a DerivedData laid out like a live one, and a fake xcodebuild that
records its argv, so the fallback's plan, proof and ledger write are executed,
not described. Its cases were mutation-checked when #9659 was built (nine
mutants, each killed). This file asserts that mode passes, that it actually ran
the cases that matter, and separately drives `--check-manifest` through the
command line against synthetic repositories.

Runs on Linux CI with no Xcode, no simulator and no network. Gotcha #54: the
script is never piped; its exit code is asserted as a VALUE.
"""

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GATES = REPO / "tools" / "native-gates.sh"

pytestmark = pytest.mark.skipif(
    not GATES.is_file(), reason="native-gates.sh is not in this checkout"
)


def run_gates(*args, cwd=None, env_extra=None, timeout=300):
    import os

    env = dict(os.environ)
    env.update(env_extra or {})
    p = subprocess.run(
        ["bash", str(GATES), *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return p.returncode, p.stdout + p.stderr


def git(repo, *args):
    p = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60
    )
    assert p.returncode == 0, f"git {' '.join(args)} failed: {p.stderr}"
    return p.stdout.strip()


def make_repo(path):
    """A git root shaped like this repo, with a stub Xcode project under ios/."""
    ios = path / "ios" / "Bain Luck"
    (ios / "Bain Luck.xcodeproj").mkdir(parents=True)
    (ios / "Bain Luck.xcodeproj" / "project.pbxproj").write_text("// stub\n")
    (ios / "BainLuckTests").mkdir()
    (ios / "BainLuckTests" / "FooTests.swift").write_text(
        "import XCTest\nfinal class FooTests: XCTestCase {}\n"
    )
    git(path, "init", "-q", "-b", "master", ".")
    git(path, "config", "user.email", "gate@test")
    git(path, "config", "user.name", "gate")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "base")
    return path


def good_manifest(repo, **over):
    tree = git(repo, "rev-parse", "HEAD:ios")
    m = {
        "schema": "native-gates-manifest/1",
        "gated_tree": str(repo),
        "gated_sha": git(repo, "rev-parse", "HEAD"),
        "gated_branch": "master",
        "ios_tree_start": tree,
        "ios_tree_end": tree,
        "ios_dirty_start": False,
        "ios_dirty_end": False,
        "macos_build_exit": 0,
        "test_exit": 0,
        "verdict": "PASS_LINE",
        "notice10_line": "Executed 4356 tests, with 0 failures (0 unexpected) in 242.355 (243.650) seconds",
        "changed_files_error": None,
        "tests_unproven": 0,
        "evidence": [
            {
                "path": "ios/Bain Luck/BainLuckTests/FooTests.swift",
                "blob": "x",
                "evidence": "cache",
                "detail": "identity",
            }
        ],
        "gate_exit": 0,
    }
    m.update(over)
    return m


def write(path, obj):
    path.write_text(json.dumps(obj))
    return path


# ── the self-test drives the real provenance functions ───────────────────────


def test_provenance_selftest_passes_and_ran_its_cases():
    rc, out = run_gates("--selftest-provenance")
    assert rc == 0, out
    assert "  FAIL" not in out, out
    # Not vacuous: the cases that ARE the ship must have run and passed by name.
    for needle in (
        "rule 6: changed content behind a preserved mtime -> insufficient",
        "current object, but no gate run ever saw it compiled -> insufficient",
        "A: NOT the cached file's (no full rerun, no re-test of what is proven)",
        "A: the ledger learned from the fallback",
        "C: ...and called a REAL failure, not a proof gap",
        "0 tests executed is a vacuous pass -> refused",
        "...and is NEVER a notice-10 line",
        "reuse: an untracked Swift file here -> NOT reusable",
        "section 3a hands the unseen files to provenance_for_unseen",
    ):
        assert f"  ok    {needle}" in out, f"case did not run/pass: {needle}\n{out}"
    assert out.count("  ok    ") >= 60, out


# ── --check-manifest, through the command line ───────────────────────────────


def _no_build_env(tmp_path):
    """A fake xcodebuild that leaves a marker, so 'nothing was built' is checked."""
    marker = tmp_path / "xcodebuild-ran"
    fake = tmp_path / "fake-xcodebuild"
    fake.write_text(f"#!/usr/bin/env bash\ntouch '{marker}'\nexit 0\n")
    fake.chmod(0o755)
    return {"NATIVE_GATES_XCODEBUILD": str(fake)}, marker


def test_same_clean_ios_tree_is_reusable_and_nothing_is_built(tmp_path):
    repo = make_repo(tmp_path / "repo")
    man = write(tmp_path / "m.json", good_manifest(repo))
    env, marker = _no_build_env(tmp_path)
    rc, out = run_gates("--check-manifest", str(man), cwd=repo, env_extra=env)
    assert rc == 0, out
    assert "REUSABLE" in out and "NOT REUSABLE" not in out, out
    assert "Executed 4356 tests, with 0 failures" in out, out
    assert not marker.exists(), "--check-manifest must never start xcodebuild"


def test_a_backend_only_commit_keeps_the_ios_evidence(tmp_path):
    """Identity is the iOS TREE, not the sha: a commit outside ios/ reuses it."""
    repo = make_repo(tmp_path / "repo")
    man = write(tmp_path / "m.json", good_manifest(repo))
    (repo / "backend.txt").write_text("server change\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "backend only")
    rc, out = run_gates("--check-manifest", str(man), cwd=repo)
    assert rc == 0, out


def test_a_changed_ios_tree_is_not_reusable(tmp_path):
    repo = make_repo(tmp_path / "repo")
    man = write(tmp_path / "m.json", good_manifest(repo))
    f = repo / "ios" / "Bain Luck" / "BainLuckTests" / "FooTests.swift"
    f.write_text(f.read_text() + "// changed\n")
    git(repo, "commit", "-qam", "ios change")
    rc, out = run_gates("--check-manifest", str(man), cwd=repo)
    assert rc == 1, out
    assert "the iOS tree differs" in out, out


@pytest.mark.parametrize(
    "over, needle",
    [
        ({"verdict": "PARTIAL", "notice10_line": "", "test_exit": 137}, "not a complete pass"),
        ({"tests_unproven": 1}, "had no compile evidence"),
        (
            {
                "evidence": [
                    {"path": "ios/Bain Luck/BainLuckTests/BarTests.swift", "blob": "y",
                     "evidence": "none", "detail": "fallback failed"}
                ]
            },
            "BarTests.swift",
        ),
        ({"ios_dirty_start": True}, "uncommitted iOS changes"),
        ({"ios_tree_end": "0" * 40}, "changed while that gate was running"),
        ({"macos_build_exit": 65}, "macOS build did not pass"),
        ({"gate_exit": 1}, "the gate itself exited 1"),
        ({"schema": "something-else"}, "unknown manifest schema"),
    ],
)
def test_incomplete_or_failed_evidence_is_not_reusable(tmp_path, over, needle):
    repo = make_repo(tmp_path / "repo")
    man = write(tmp_path / "m.json", good_manifest(repo, **over))
    rc, out = run_gates("--check-manifest", str(man), cwd=repo)
    assert rc == 1, out
    assert needle in out, out


def test_uncommitted_or_untracked_ios_files_here_block_reuse(tmp_path):
    """File-system-synchronized groups compile an untracked Swift file, so it
    changes what would be tested even though HEAD:ios does not move."""
    repo = make_repo(tmp_path / "repo")
    man = write(tmp_path / "m.json", good_manifest(repo))
    extra = repo / "ios" / "Bain Luck" / "BainLuckTests" / "New.swift"
    extra.write_text("// untracked\n")
    rc, out = run_gates("--check-manifest", str(man), cwd=repo)
    assert rc == 1, out
    assert "this tree has uncommitted iOS changes" in out, out
    extra.unlink()
    rc, out = run_gates("--check-manifest", str(man), cwd=repo)
    assert rc == 0, out


def test_an_unreadable_manifest_is_refused_by_name(tmp_path):
    repo = make_repo(tmp_path / "repo")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    rc, out = run_gates("--check-manifest", str(bad), cwd=repo)
    assert rc == 1, out
    assert "cannot read the manifest" in out, out


def test_help_documents_the_new_flags():
    rc, out = run_gates("--help")
    assert rc == 0, out
    for flag in ("--check-manifest", "--no-fallback", "--selftest-provenance"):
        assert flag in out, f"{flag} missing from --help"
