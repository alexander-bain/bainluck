"""Exact candidate residue checks, using scratch Git and one synthetic pair.

The real scanner parser, Pass A/Pass B, baseline policy and exit codes execute.
Only harvesting is replaced: no real mutation harness or native source runs.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCANNER = Path(__file__).resolve().parents[1] / "scripts/evals/scan_mutation_residue.py"
NEEDLE = "the original native statement remains exactly once"
MUTANT = "a copied native replacement that is not the original"


@pytest.fixture
def rig(tmp_path, monkeypatch):
    def git(*args):
        result = subprocess.run(
            ["git", "-C", str(tmp_path), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    git("init", "-q", "-b", "master")
    git("config", "user.name", "scratch")
    git("config", "user.email", "scratch@example.invalid")
    git("config", "core.hooksPath", str(tmp_path / "no-hooks"))

    def commit(files=None, remove=()):
        for name, content in (files or {}).items():
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content if isinstance(content, bytes) else content.encode())
            git("add", "--", name)
        for name in remove:
            git("rm", "--", name)
        git("commit", "-qm", "scratch", "--allow-empty")
        return git("rev-parse", "HEAD")

    base = commit({"ios/Declared.swift": NEEDLE})
    git("update-ref", "refs/remotes/origin/master", base)
    copied = tmp_path / "backend/scripts/evals/scan_mutation_residue.py"
    copied.parent.mkdir(parents=True)
    copied.write_text(SCANNER.read_text(), encoding="utf-8")
    copied.with_name("ambiguous_needle_baseline.json").write_text(
        '{"known_ambiguous": []}'
    )
    spec = importlib.util.spec_from_file_location("scratch_scan_10708", copied)
    scan = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scan)
    pair = scan.Pair("synthetic", "M1", NEEDLE, MUTANT, tmp_path / "ios/Declared.swift")
    monkeypatch.setattr(scan, "harvest", lambda: ([pair], []))
    monkeypatch.setattr(scan, "DISK_FREE", frozenset())
    return SimpleNamespace(path=tmp_path, git=git, commit=commit, base=base, scan=scan)


def run(rig, monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, "argv", ["scan", *args])
    try:
        code = rig.scan.main()
    except SystemExit as exc:
        code = exc.code
    output = capsys.readouterr()
    return code, output.out, output.err


def test_whole_range_finds_earlier_swift_copy_when_origin_master_is_head(
    rig, monkeypatch, capsys
):
    rig.commit({"ios/Copied.swift": MUTANT})
    head = rig.commit({"ios/Later.swift": "a later clean native tip"})
    rig.git("update-ref", "refs/remotes/origin/master", head)
    code, out, _ = run(rig, monkeypatch, capsys)
    assert (
        code == 0 and "x 0 files" in out
    )  # retained default is not exact-range evidence
    code, out, err = run(rig, monkeypatch, capsys, "--base", rig.base, "--head", head)
    assert code == 1 and "ios/Copied.swift" in out and "RESIDUE" in out, err
    assert f"{rig.base}..{head}" in out and "2 existing candidate file(s)" in out


@pytest.mark.parametrize("copied_residue", [False, True])
def test_source_blobs_are_independent_of_merge_checkout_and_dirty_bytes(
    rig, monkeypatch, capsys, copied_residue
):
    rig.git("switch", "-c", "native")
    head = rig.commit(
        {"ios/Candidate.swift": MUTANT if copied_residue else "clean source"}
    )
    rig.git("switch", "-c", "carrier", rig.base)
    rig.commit({"ios/MergeOnly.swift": MUTANT})
    rig.git("merge", "--no-ff", "native", "-m", "scratch merge")
    checkout = rig.git("rev-parse", "HEAD")
    # Neither this dirty file nor the unrelated carrier mutant is the source head.
    (rig.path / "ios/Candidate.swift").write_text(
        "dirty checkout, no copied replacement"
    )
    code, out, err = run(rig, monkeypatch, capsys, "--base", rig.base, "--head", head)
    assert code == int(copied_residue), err
    assert f"checkout={checkout}" in out and f"{rig.base}..{head}" in out
    assert "1 existing candidate file(s)" in out and "ios/MergeOnly.swift" not in out


def test_two_endpoints_are_not_their_merge_base(rig, monkeypatch, capsys):
    common = rig.commit({"ios/Copied.swift": MUTANT})
    base = rig.commit(remove=("ios/Copied.swift",))
    rig.git("switch", "-c", "other", common)
    head = rig.commit({"ios/Later.swift": "clean"})
    code, out, err = run(rig, monkeypatch, capsys, "--base", base, "--head", head)
    assert code == 1 and "ios/Copied.swift" in out, err
    assert "2 existing candidate file(s)" in out  # three-dot would include only Later


def test_base_precedent_uses_committed_base_not_checkout(rig, monkeypatch, capsys):
    base = rig.commit({"ios/Preexisting.swift": MUTANT})
    head = rig.commit({"ios/Preexisting.swift": MUTANT + "\nnew comment"})
    (rig.path / "ios/Preexisting.swift").write_text("dirty clean bytes")
    code, out, err = run(rig, monkeypatch, capsys, "--base", base, "--head", head)
    assert code == 0 and "ALREADY in that file" in out and "CLEAN" in out, err


def test_deletion_is_reported_without_inventing_a_head_blob(rig, monkeypatch, capsys):
    base = rig.commit({"ios/Removed.swift": "clean"})
    head = rig.commit(remove=("ios/Removed.swift",))
    code, out, err = run(rig, monkeypatch, capsys, "--base", base, "--head", head)
    assert code == 0, err
    assert "0 existing candidate file(s), 1 deletion(s)" in out
    assert "DELETED at candidate head" in out and "ios/Removed.swift" in out


def test_rename_is_a_deletion_and_new_blob_not_a_hidden_source(
    rig, monkeypatch, capsys
):
    base = rig.commit({"ios/Old.swift": MUTANT})
    head = rig.commit({"ios/New.swift": MUTANT}, remove=("ios/Old.swift",))
    code, out, err = run(rig, monkeypatch, capsys, "--base", base, "--head", head)
    assert code == 1 and "ios/New.swift" in out, err
    assert "1 existing candidate file(s), 1 deletion(s)" in out


def test_nul_records_preserve_whitespace_and_glob_filename(rig, monkeypatch, capsys):
    name = "ios/line\nwith\t[glob] space.swift"
    head = rig.commit({name: MUTANT})
    code, out, err = run(rig, monkeypatch, capsys, "--base", rig.base, "--head", head)
    assert code == 1 and name in out, err


@pytest.mark.parametrize("option", ["--base", "--head"])
def test_unresolvable_endpoint_refuses_not_a_finding(rig, monkeypatch, capsys, option):
    args = {"--base": rig.base, "--head": rig.base}
    args[option] = "missing-ref"
    code, out, err = run(
        rig, monkeypatch, capsys, "--base", args["--base"], "--head", args["--head"]
    )
    assert code == 2 and "CANNOT MEASURE" in err and "CLEAN" not in out


@pytest.mark.parametrize(
    "args", [("--head", "HEAD"), ("--base", "HEAD", "--head", "HEAD", "--all-tracked")]
)
def test_exact_mode_requires_both_endpoints_and_no_all_tracked(
    rig, monkeypatch, capsys, args
):
    code, out, err = run(rig, monkeypatch, capsys, *args)
    assert code == 2 and "--head requires" in err and "CLEAN" not in out


@pytest.mark.parametrize("where", ["head", "base"])
def test_non_utf8_needed_blob_refuses(rig, monkeypatch, capsys, where):
    if where == "head":
        base = rig.base
        head = rig.commit({"ios/Bad.swift": b"\xff"})
    else:
        base = rig.commit({"ios/Bad.swift": b"\xff" + MUTANT.encode()})
        head = rig.commit({"ios/Bad.swift": MUTANT})
    code, out, err = run(rig, monkeypatch, capsys, "--base", base, "--head", head)
    assert code == 2 and "not UTF-8" in err and "CLEAN" not in out


@pytest.mark.parametrize("command", ["diff", "cat-file"])
def test_git_read_failure_is_refusal(rig, monkeypatch, capsys, command):
    head = rig.commit({"ios/Candidate.swift": MUTANT})
    real_run = subprocess.run

    def failed(args, **kwargs):
        if args[:3] == ["git", "-C", str(rig.path)] and args[3] == command:
            return subprocess.CompletedProcess(args, 128, b"", b"injected read failure")
        return real_run(args, **kwargs)

    monkeypatch.setattr(rig.scan.subprocess, "run", failed)
    code, out, err = run(rig, monkeypatch, capsys, "--base", rig.base, "--head", head)
    assert code == 2 and "injected read failure" in err and "CLEAN" not in out


@pytest.mark.parametrize("failure", ["spawn", "timeout"])
def test_git_spawn_or_timeout_refuses(rig, monkeypatch, capsys, failure):
    head = rig.commit({"ios/Candidate.swift": "clean"})
    real_run = subprocess.run

    def failed(args, **kwargs):
        if args[:4] == ["git", "-C", str(rig.path), "diff"]:
            if failure == "spawn":
                raise OSError("injected spawn error")
            raise subprocess.TimeoutExpired(args, 30)
        return real_run(args, **kwargs)

    monkeypatch.setattr(rig.scan.subprocess, "run", failed)
    code, out, err = run(rig, monkeypatch, capsys, "--base", rig.base, "--head", head)
    assert code == 2 and "CANNOT MEASURE" in err and "CLEAN" not in out


def test_unknown_harvest_still_refuses_before_range_success(rig, monkeypatch, capsys):
    monkeypatch.setattr(rig.scan, "harvest", lambda: ([], ["unknown_harness"]))
    code, out, _ = run(rig, monkeypatch, capsys, "--base", rig.base, "--head", rig.base)
    assert code == 2 and "unknown_harness" in out and "CLEAN" not in out


def test_symlink_candidate_cannot_be_mistaken_for_source_bytes(
    rig, monkeypatch, capsys
):
    (rig.path / "ios/Link.swift").symlink_to("Declared.swift")
    rig.git("add", "--", "ios/Link.swift")
    head = rig.commit()
    code, out, err = run(rig, monkeypatch, capsys, "--base", rig.base, "--head", head)
    assert code == 2 and "unsupported candidate file mode" in err and "CLEAN" not in out


def test_clean_empty_exact_range_is_named_and_default_all_tracked_is_retained(
    rig, monkeypatch, capsys
):
    code, out, err = run(
        rig, monkeypatch, capsys, "--base", rig.base, "--head", rig.base
    )
    assert code == 0 and "0 existing candidate file(s), 0 deletion(s)" in out, err
    rig.commit({"ios/Copied.swift": MUTANT})
    rig.git("update-ref", "refs/remotes/origin/master", "HEAD")
    code, out, err = run(rig, monkeypatch, capsys, "--all-tracked")
    assert code == 0 and "ALREADY in that file" in out and "all tracked" in out, err


def test_pass_a_still_grades_checkout_even_with_an_exact_clean_head(
    rig, monkeypatch, capsys
):
    (rig.path / "ios/Declared.swift").write_text(MUTANT)
    code, out, err = run(
        rig, monkeypatch, capsys, "--base", rig.base, "--head", rig.base
    )
    assert code == 1 and "target(s) hold the MUTANT" in out, err
