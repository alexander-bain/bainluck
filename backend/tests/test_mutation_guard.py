"""The mutation-harness restore guard — and the control that justifies it.

An eval harness wrote a mutant into `app/routes/search_typeahead_warmer.py`
and died before restoring it. The mutant rode `bcdcd95f` into the branch as an
edit nobody made, and it looked ordinary because the same window had a real
reason to be touching that same file. The corroborating artifact — a pristine
backup in `/tmp/lat_p056_backups`, dated 3 m 54 s before the commit — is what
turned "unknown change" into a positive identification.

The window recorded **exit 143: SIGTERM**, and that number is why this file
does not simply assert "there is a `try/finally` now". Python's default
SIGTERM disposition terminates the process without raising, so `finally` never
runs. `test_a_bare_try_finally_does_NOT_survive_sigterm` is the control that
pins this: it is the same code shape the directive asked for, and it FAILS to
restore. Every other test here is only meaningful next to it.

Each case runs in a subprocess, because the interesting ones kill the process.
"""

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[1] / "scripts" / "evals"
GUARD = EVALS / "_mutation_guard.py"

ORIGINAL = "the original bytes\n"
MUTANT = "MUTATED\n"


@pytest.fixture
def target(tmp_path: Path) -> Path:
    path = tmp_path / "target.py"
    path.write_text(ORIGINAL)
    return path


def _run(body: str, tmp_path: Path) -> subprocess.CompletedProcess:
    script = tmp_path / "runner.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import os, signal, sys
            sys.path.insert(0, {str(EVALS)!r})
            from pathlib import Path
            from _mutation_guard import guarded_targets, recover, MANIFEST_DIR
            """
        )
        + textwrap.dedent(body)
    )
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )


def test_the_guard_module_exists_where_the_harnesses_import_it_from():
    """A cheap anchor: if this moves, five harnesses stop importing silently."""
    assert GUARD.is_file()


def test_an_exception_mid_mutation_restores(target, tmp_path):
    result = _run(
        f"""
        try:
            with guarded_targets([{str(target)!r}], {str(tmp_path / "bk")!r}, "t-exc"):
                Path({str(target)!r}).write_text("MUTATED\\n")
                raise RuntimeError("oracle blew up")
        except RuntimeError:
            pass
        """,
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert target.read_text() == ORIGINAL


def test_sigterm_mid_mutation_restores_under_the_guard(target, tmp_path):
    """The exact incident: exit 143 between the write and the restore."""
    result = _run(
        f"""
        with guarded_targets([{str(target)!r}], {str(tmp_path / "bk")!r}, "t-term"):
            Path({str(target)!r}).write_text("MUTATED\\n")
            os.kill(os.getpid(), signal.SIGTERM)
            print("UNREACHABLE")
        """,
        tmp_path,
    )
    assert "UNREACHABLE" not in result.stdout
    assert target.read_text() == ORIGINAL, (
        "SIGTERM left the mutant on disk — this is bcdcd95f happening again"
    )


def test_a_bare_try_finally_does_NOT_survive_sigterm(target, tmp_path):
    """THE CONTROL. Without it the test above proves nothing about the guard.

    This is `try/finally` written exactly as asked for, with no signal
    handling. It does not restore, because SIGTERM's default disposition kills
    the interpreter without unwinding. The whole reason `_mutation_guard`
    installs handlers is sitting in this assertion.
    """
    script = tmp_path / "bare.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import os, signal, shutil
            from pathlib import Path
            t = Path({str(target)!r})
            b = Path({str(tmp_path / "bare_backup")!r})
            shutil.copy2(t, b)
            try:
                t.write_text("MUTATED\\n")
                os.kill(os.getpid(), signal.SIGTERM)
            finally:
                shutil.copy2(b, t)
            """
        )
    )
    subprocess.run([sys.executable, str(script)], capture_output=True, timeout=60)
    assert target.read_text() == MUTANT, (
        "a bare try/finally restored across SIGTERM — if this ever passes, the "
        "guard's signal handling is redundant and should be re-argued, not kept"
    )


def test_sigkill_leaves_a_breadcrumb_that_the_next_run_restores_from(target, tmp_path):
    """SIGKILL is uncatchable; the guard makes the residue ANNOUNCE itself.

    It cannot prevent this case and does not claim to. What it converts is a
    mutant that looks like an ordinary uncommitted edit into one that a later
    run names out loud — which is the entire distance between `bcdcd95f` and a
    caught incident.
    """
    manifest_dir = tmp_path / "manifests"
    killer = tmp_path / "killer.py"
    killer.write_text(
        textwrap.dedent(
            f"""
            import os, signal, sys
            sys.path.insert(0, {str(EVALS)!r})
            from pathlib import Path
            import _mutation_guard as g
            g.MANIFEST_DIR = Path({str(manifest_dir)!r})
            with g.guarded_targets([{str(target)!r}], {str(tmp_path / "bk")!r}, "t-kill"):
                Path({str(target)!r}).write_text("MUTATED\\n")
                os.kill(os.getpid(), signal.SIGKILL)
            """
        )
    )
    killed = subprocess.run([sys.executable, str(killer)], capture_output=True, timeout=60)
    assert killed.returncode == -9

    # Uncatchable means uncatchable: the mutant IS on disk.
    assert target.read_text() == MUTANT
    manifests = list(manifest_dir.glob("*.json"))
    assert len(manifests) == 1
    recorded = json.loads(manifests[0].read_text())
    assert recorded["label"] == "t-kill"
    assert str(target) in recorded["targets"]

    # And the next run finds it, restores it, and says so.
    recoverer = tmp_path / "recover.py"
    recoverer.write_text(
        textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {str(EVALS)!r})
            from pathlib import Path
            import _mutation_guard as g
            g.MANIFEST_DIR = Path({str(manifest_dir)!r})
            print("restored", g.recover())
            """
        )
    )
    out = subprocess.run(
        [sys.executable, str(recoverer)], capture_output=True, text=True, timeout=60
    )
    assert "restored 1" in out.stdout
    assert "RESTORED" in out.stdout and "dead run" in out.stdout
    assert target.read_text() == ORIGINAL
    assert not list(manifest_dir.glob("*.json"))


def test_a_clean_run_leaves_no_manifest_behind(target, tmp_path):
    """Otherwise every successful run would look like an abandoned one."""
    manifest_dir = tmp_path / "manifests"
    result = _run(
        f"""
        import _mutation_guard as g
        g.MANIFEST_DIR = Path({str(manifest_dir)!r})
        with g.guarded_targets([{str(target)!r}], {str(tmp_path / "bk")!r}, "t-clean"):
            Path({str(target)!r}).write_text("MUTATED\\n")
        print("exit clean")
        """,
        tmp_path,
    )
    assert "exit clean" in result.stdout, result.stderr
    assert target.read_text() == ORIGINAL
    assert not list(manifest_dir.glob("*.json"))


def test_a_live_run_is_never_recovered_by_a_concurrent_one(target, tmp_path):
    """🔴 CERT-563's blocker, as a test: the false SURVIVED.

    `start()` calls `recover()` unconditionally, and `recover()` used to assume
    every manifest it could see belonged to a corpse. Two batteries in two
    worktrees — a build lane and the cert window, which is the ORDINARY pairing —
    therefore did this:

      1. run A mutates its source file and starts its oracle;
      2. run B starts, recovers A's live manifest, and copies A's backup back
         over A's file *while A's suite is running*;
      3. A's suite passes, because the mutant is no longer on disk;
      4. A reports `SURVIVED`, with `0 harness failures` to give it away.

    A false SURVIVED is the expensive direction — it reads as a missing
    assertion, so the next session writes a guard for a defect that was already
    guarded. It cost CERT-563 a BLOCK on `M18c`, which kills 1/1 when re-run
    alone.

    The control that makes this test mean something is
    `test_sigkill_leaves_a_breadcrumb_that_the_next_run_restores_from` directly
    above: same manifest, same directory, same `recover()` call — and it DOES
    restore, because there the pid is genuinely dead. The distinction being
    asserted is liveness, not visibility.
    """
    manifest_dir = tmp_path / "manifests"
    ready, release = tmp_path / "ready", tmp_path / "release"
    sleeper = tmp_path / "sleeper.py"
    sleeper.write_text(
        textwrap.dedent(
            f"""
            import sys, time
            sys.path.insert(0, {str(EVALS)!r})
            from pathlib import Path
            import _mutation_guard as g
            g.MANIFEST_DIR = Path({str(manifest_dir)!r})
            with g.guarded_targets([{str(target)!r}], {str(tmp_path / "bk")!r}, "t-live"):
                Path({str(target)!r}).write_text("MUTATED\\n")
                Path({str(ready)!r}).write_text("x")
                for _ in range(600):
                    if Path({str(release)!r}).exists():
                        break
                    time.sleep(0.05)
            """
        )
    )
    proc = subprocess.Popen([sys.executable, str(sleeper)])
    try:
        for _ in range(600):
            if ready.exists():
                break
            time.sleep(0.05)
        assert ready.exists(), "the concurrent run never reached its mutation"
        assert target.read_text() == MUTANT
        assert len(list(manifest_dir.glob("*.json"))) == 1

        recoverer = tmp_path / "recover.py"
        recoverer.write_text(
            textwrap.dedent(
                f"""
                import sys
                sys.path.insert(0, {str(EVALS)!r})
                from pathlib import Path
                import _mutation_guard as g
                g.MANIFEST_DIR = Path({str(manifest_dir)!r})
                print("restored", g.recover())
                """
            )
        )
        out = subprocess.run(
            [sys.executable, str(recoverer)], capture_output=True, text=True, timeout=60
        )
        assert "restored 0" in out.stdout, out.stdout
        assert "LIVE pid" in out.stdout
        # The mutant is still on disk, so the run that wrote it is still
        # measuring what it thinks it is measuring.
        assert target.read_text() == MUTANT
        # And its breadcrumb survives: deleting it would strand the residue if
        # the live run went on to be SIGKILLed.
        assert len(list(manifest_dir.glob("*.json"))) == 1
    finally:
        release.write_text("x")
        proc.wait(timeout=60)

    # The live run finished normally and cleaned up after itself.
    assert target.read_text() == ORIGINAL
    assert not list(manifest_dir.glob("*.json"))


def test_a_manifest_written_by_another_checkout_is_left_alone(target, tmp_path):
    """Manifests name ABSOLUTE paths, so another worktree's resolves perfectly
    well — straight into that worktree's working files.

    The refusal keys on who WROTE the manifest, not on where the target lives: a
    harness may legitimately guard a file outside its own tree (every test in
    this module does, via `tmp_path`), so a containment test on the path would
    refuse the honest case along with the foreign one.
    """
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    backup = tmp_path / "bk.py"
    backup.write_text(ORIGINAL)
    target.write_text(MUTANT)
    (manifest_dir / "t-foreign.json").write_text(
        json.dumps(
            {
                "label": "t-foreign",
                "pid": 999999,  # dead, so ONLY the root check can refuse this
                "root": "/some/other/worktree",
                "targets": {str(target): {"backup": str(backup), "sha": "deadbeef"}},
            }
        )
    )
    out = _run(
        f"""
        import _mutation_guard as g
        g.MANIFEST_DIR = Path({str(manifest_dir)!r})
        print("restored", g.recover())
        """,
        tmp_path,
    )
    assert "restored 0" in out.stdout, out.stdout
    assert "another worktree's run" in out.stdout
    assert target.read_text() == MUTANT
    assert list(manifest_dir.glob("*.json")), "the owning tree's breadcrumb was destroyed"


def test_a_manifest_with_no_root_is_still_recovered(target, tmp_path):
    """The compatibility half, asserted rather than assumed.

    `root` is new. Residue written by a run that predates it must still be
    recovered — stranding real residue to close a narrower hole would be the
    worse trade, and the live-pid refusal already covers the dangerous case.
    """
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    backup = tmp_path / "bk.py"
    backup.write_text(ORIGINAL)
    target.write_text(MUTANT)
    (manifest_dir / "t-legacy.json").write_text(
        json.dumps(
            {
                "label": "t-legacy",
                "pid": 999999,
                "targets": {str(target): {"backup": str(backup), "sha": "deadbeef"}},
            }
        )
    )
    out = _run(
        f"""
        import _mutation_guard as g
        g.MANIFEST_DIR = Path({str(manifest_dir)!r})
        print("restored", g.recover())
        """,
        tmp_path,
    )
    assert "restored 1" in out.stdout, out.stdout
    assert target.read_text() == ORIGINAL


def test_the_default_manifest_and_backup_paths_are_worktree_unique():
    """The other half of the same defect: two checkouts sharing one `/tmp` path.

    Backups collided by FILENAME, so a crash in either worktree could restore
    the other's bytes into this tree — a corruption, not just a wrong verdict.
    `_tree_scoped` is asserted IDEMPOTENT because one harness already namespaced
    itself by hand (#2330) and must not end up double-suffixed.
    """
    sys.path.insert(0, str(EVALS))
    import _mutation_guard as g

    assert g.TREE in g.MANIFEST_DIR.name
    assert g.MANIFEST_DIR != g.LEGACY_MANIFEST_DIR

    scoped_dir = g._tree_scoped(Path("/tmp/some_guard_backups"))
    assert scoped_dir.name == f"some_guard_backups_{g.TREE}"
    assert g._tree_scoped(scoped_dir) == scoped_dir

    scoped_file = g._tree_scoped(Path("/tmp/some_backup.py"))
    assert scoped_file.name == f"some_backup_{g.TREE}.py"
    assert g._tree_scoped(scoped_file) == scoped_file


def test_no_mutant_is_sitting_in_a_harness_target_right_now():
    """Detection, standing — the half the guard cannot cover.

    The guard prevents residue from SIGTERM. It cannot prevent SIGKILL, and it
    cannot clean a branch that already has a mutant on it — which is exactly
    the state `bcdcd95f` was in for a full cycle. Pass A of the scanner is
    length-independent: in a clean tree every harness needle is present in its
    own target, so a target holding the MUTANT and not the original is caught
    regardless of how short the replacement is.

    Exit 1 is residue and fails here. Exit 2 is "a harness this scanner does
    not understand", which also fails, and deliberately: a scan that quietly
    covers 8 of 9 harnesses prints the same clean line as one that covers all
    nine (gotcha #53).
    """
    scanner = EVALS / "scan_mutation_residue.py"
    result = subprocess.run(
        [sys.executable, str(scanner)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(EVALS.parents[1]),
    )
    assert result.returncode == 0, (
        f"mutation-residue scan exit {result.returncode}\n{result.stdout}\n{result.stderr}"
    )


def test_an_unresolvable_base_exits_2_not_1():
    """A scan that CANNOT RUN must not borrow the code that means "residue found".

    The scanner's Pass B diffs against a base ref. When that ref does not
    resolve — the ordinary state of a shallow PR checkout, where `origin/master`
    was never fetched — `_files` used `raise SystemExit(str)`, which exits **1**:
    byte-identical to a real finding. Every PR in the repo failed this shard on
    2026-08-24 with a message that read like a mutant sitting in the tree, while
    Pass A had in fact printed its clean line one row above.

    The docstring always promised `2` for "the scan could not be performed"; only
    the code disagreed. This test is the half that CI could not have caught, since
    CI is the environment that produces the bad base in the first place.

    Gotcha #54's amendment, applied to our own tooling: `1` is a result, and every
    other code is a story about the harness.
    """
    scanner = EVALS / "scan_mutation_residue.py"
    result = subprocess.run(
        [sys.executable, str(scanner), "--base", "no-such-ref-deadbeef"],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(EVALS.parents[1]),
    )
    assert result.returncode == 2, (
        "an unresolvable base must exit 2 (CANNOT MEASURE), not 1 (RESIDUE FOUND)\n"
        f"got {result.returncode}\n{result.stdout}\n{result.stderr}"
    )
    assert "CANNOT MEASURE" in result.stderr, (
        "the reason must name itself as an inability to measure, so a reader is "
        f"not left inferring a finding:\n{result.stderr}"
    )


def test_every_on_disk_harness_is_guarded():
    """The class-closing assertion — a NEW harness cannot quietly opt out.

    Two harnesses (`admin_auth_gate`, `duration_sample_window`) mutate a source
    STRING and `exec` it, never touching disk. They are structurally immune and
    are the shape to prefer; they are exempted by measurement — no
    `write_text` / `copy2` — rather than by name.
    """
    offenders = []
    for path in sorted(EVALS.glob("*_mutations.py")):
        src = path.read_text()
        writes_to_disk = ".write_text(" in src or "shutil.copy2(" in src
        if not writes_to_disk:
            continue
        if "guarded_targets" not in src:
            offenders.append(path.name)
    assert not offenders, (
        "these harnesses mutate files on disk without the restore guard, so a "
        f"SIGTERM mid-run leaves a mutant in the tree: {offenders}"
    )
