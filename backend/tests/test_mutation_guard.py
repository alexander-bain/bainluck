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


def test_a_drifted_or_newly_ambiguous_needle_FAILS_the_scan():
    """The scan used to find drift, print it, and then exit 0 saying CLEAN.

    🔴 TWO STATEMENTS ABOUT ONE TREE, ONE OF THEM FALSE, AND THE REASSURING ONE
    LAST (CERT-563). Pass A printed `N needle(s) no longer present` and four
    lines later `✅ every needle present in its own target`, then returned 0. In
    the session that found this, the green line was read and believed, and the
    drift it contradicted was discovered thirty-two minutes later by the battery
    that could not apply the mutant.

    Both states mean the same thing — the mutant DOES NOT RUN, so the
    denominator says N and the power is N-1 — and neither may pass. Ambiguity is
    ratcheted rather than simply fatal: see `ambiguous_needle_baseline.json`.

    Exercised through the real scanner on a synthetic harness, so it tests the
    shipped exit code and not a re-implementation of it.
    """
    scanner = EVALS / "scan_mutation_residue.py"
    # `harvest()` is replaced so the scanner's REAL Pass A and its REAL exit code
    # run over one synthetic pair. Re-implementing the check here would only
    # prove that this file's copy of it works.
    probe = textwrap.dedent(
        f"""
        import sys, pathlib
        sys.path.insert(0, {str(EVALS)!r})
        import scan_mutation_residue as s
        target = pathlib.Path({str(EVALS / "scan_mutation_residue.py")!r})
        pair = s.Pair("synthetic_probe_mutations", "M-PROBE", NEEDLE,
                      "ZZZ-NOT-PRESENT-ANYWHERE-ZZZ", target)
        s.harvest = lambda: ([pair], [])
        sys.argv = ["scan", "--all-tracked"]
        sys.exit(s.main())
        """
    )
    for label, needle, expect in (
        # Absent from the target: the mutant can never be applied.
        ("drifted", "THIS TEXT IS NOT IN THE TARGET ANYWHERE AT ALL", "drifted"),
        # Present many times, and NOT in the baseline: the harness would refuse
        # it as HARNESS-FAIL, so it can never be applied either.
        ("newly ambiguous", "import ", "newly ambiguous"),
    ):
        result = subprocess.run(
            [sys.executable, "-c", probe.replace("NEEDLE", repr(needle))],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(EVALS.parents[1]),
        )
        assert result.returncode == 1, (
            f"a {label} needle did not fail the scan (exit {result.returncode}). "
            "This is the false green CERT-563 was written about.\n"
            f"{result.stdout}\n{result.stderr}"
        )
        assert "NOT CLEAN" in result.stdout, result.stdout
        assert expect in result.stdout, result.stdout

    # And the real tree, with its real baseline, must be clean — this is the
    # control that keeps the two assertions above from passing vacuously.
    clean = subprocess.run(
        [sys.executable, str(scanner)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(EVALS.parents[1]),
    )
    assert clean.returncode == 0, f"{clean.stdout}\n{clean.stderr}"
    assert "🔴 NOT CLEAN" not in clean.stdout


def test_the_ambiguity_baseline_matches_the_tree_it_describes():
    """A ratchet whose baseline has rotted is a ratchet nobody is holding.

    Every entry must still be genuinely ambiguous — a stale line silently
    licenses a real regression under the same name — and the scan prints a nudge
    (not a failure) when one becomes unique, because failing a lane for REPAIRING
    a guard would be perverse. This asserts the file is well-formed and that the
    scan agrees with it, which is the part a nudge cannot enforce.
    """
    baseline = json.loads((EVALS / "ambiguous_needle_baseline.json").read_text())
    known = baseline["known_ambiguous"]
    assert known, "an empty baseline should be DELETED, not kept as an empty list"
    assert len(known) == len(set(known)), "duplicate entries in the baseline"
    assert baseline["_issue"].startswith("#"), "the debt must name its issue"
    for entry in known:
        assert ":" in entry, f"{entry!r} is not a `harness:mutant-id` pair"

    result = subprocess.run(
        [sys.executable, str(EVALS / "scan_mutation_residue.py")],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(EVALS.parents[1]),
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert f"{len(known)} baselined ambiguous needle(s) remain" in result.stdout, (
        "the scan and the baseline disagree about how many ambiguous needles "
        f"exist. Baseline says {len(known)}.\n{result.stdout}"
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


# ---------------------------------------------------------------------------
# CERT-579: two runs of ONE harness in ONE checkout
# ---------------------------------------------------------------------------
#
# CERT-563 closed the two-WORKTREE collision by namespacing the manifest and the
# backups on the repo root. CERT-579 showed the same collision survives inside a
# single checkout, because the names were still derived from the LABEL and a
# label belongs to the harness, not to the run. The cert's two-process probe had
# both runs exit 0 with the target still mutated and the shared manifest already
# unlinked — residue that nothing names, which is the one state `--check` and the
# residue scanner cannot see.
#
# These pin both halves of the repair, and they pin them the way the cert found
# it: by actually running two processes, not by asserting on path strings. A
# string assertion would have passed against the broken code the moment somebody
# added a token anywhere in the name.


def _concurrency_probe(tmp_path, hold_a="3.0", hold_b="0.2"):
    """Two guarded runs of the same label, overlapping, in this checkout.

    Returns `(rc_a, rc_b, target_is_pristine, text)`.
    """
    import hashlib
    import subprocess
    import sys
    import textwrap
    import time

    backend = Path(__file__).resolve().parents[1]
    target = tmp_path / "victim.py"
    pristine = "ORIGINAL PRISTINE CONTENT\n"
    target.write_text(pristine)

    worker = tmp_path / "worker.py"
    worker.write_text(
        textwrap.dedent(
            f'''
            import sys, time, pathlib
            sys.path.insert(0, {str(backend)!r})
            from scripts.evals._mutation_guard import guarded_targets
            target = pathlib.Path(sys.argv[1]); hold = float(sys.argv[2]); tag = sys.argv[3]
            with guarded_targets((target,), {str(tmp_path / "backups")!r}, "cert579_probe"):
                target.write_text("MUTATED BY " + tag + "\\n")
                time.sleep(hold)
            '''
        )
    )

    def _spawn(hold, tag):
        return subprocess.Popen(
            [sys.executable, str(worker), str(target), hold, tag],
            cwd=str(backend), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

    a = _spawn(hold_a, "A")
    time.sleep(1.0)  # A is inside its guard and has already mutated the target
    b = _spawn(hold_b, "B")
    a.communicate(); b.communicate()

    text = target.read_text()
    pristine_now = (
        hashlib.sha256(text.encode()).hexdigest()
        == hashlib.sha256(pristine.encode()).hexdigest()
    )
    return a.returncode, b.returncode, pristine_now, text


def test_two_concurrent_runs_in_one_checkout_do_not_corrupt_the_target(tmp_path):
    """CERT-579's exact probe. The target must come back pristine.

    Before the fix this ended with both processes exiting 0 and the file reading
    `MUTATED BY A` — run B copied A's already-mutated target over the shared
    backup, so A's restore had nothing pristine to restore FROM.
    """
    rc_a, rc_b, pristine, text = _concurrency_probe(tmp_path)
    assert pristine, (
        "two concurrent runs of one harness in one checkout left the target "
        f"mutated: {text!r} (A exit {rc_a}, B exit {rc_b}). Each run must own its "
        "own backup — see `_run_scoped` and `_RUN`."
    )


def test_each_run_owns_its_backup_and_its_manifest(tmp_path):
    """The mechanism, so a future edit cannot keep the probe green by accident.

    Two guards built in one process for one label must not name the same backup
    or the same manifest. This is the property the probe above depends on; if it
    is ever true only because of timing, this fails first and says why.
    """
    import importlib

    mg = importlib.import_module("scripts.evals._mutation_guard")

    target = tmp_path / "t.py"
    target.write_text("x = 1\n")
    monkey_dir = tmp_path / "manifests"
    original_dir = mg.MANIFEST_DIR
    mg.MANIFEST_DIR = monkey_dir
    try:
        # 🔴 SEQUENTIALLY, NOT CONCURRENTLY. Since CERT-588 the guard holds an
        # exclusive lock on the target set for its whole context, so starting a
        # second guard on the same target while the first is live is precisely
        # what is now forbidden — doing it here would block until the timeout.
        # The property under test is that two RUNS get different paths, which is
        # about naming and does not need them to overlap.
        first = mg._Guard((target,), tmp_path / "b", "same_label").start()
        first_backup, first_run = first.backups[target], first._run
        first.restore_all()
        first.finish()

        saved = mg._RUN
        mg._RUN = f"{saved}-second"
        try:
            second = mg._Guard((target,), tmp_path / "b", "same_label").start()
            second_backup, second_run = second.backups[target], second._run
            second.restore_all()
            second.finish()
        finally:
            mg._RUN = saved

        assert first_backup != second_backup, (
            "two runs of one label share a backup path — the second run's "
            "`copy2` overwrites the first run's pristine bytes (CERT-579)"
        )
        assert mg._manifest_path("same_label", first_run) != mg._manifest_path(
            "same_label", second_run
        ), "two runs of one label share a manifest path (CERT-579)"
    finally:
        mg.MANIFEST_DIR = original_dir


def test_a_failed_restore_is_raised_not_swallowed(tmp_path):
    """The second half of CERT-579: the verdict must reach the caller.

    `restore_all` always detected the mismatch and returned False. `guarded_targets`
    threw that away, so the harness scored its mutants against a dirty tree and
    exited 0. Deleting the backup from underneath the guard is the cheapest way to
    force a restore failure without a second process.
    """
    from scripts.evals._mutation_guard import guarded_targets

    target = tmp_path / "victim.py"
    target.write_text("pristine\n")

    with pytest.raises(RuntimeError, match="could NOT restore"):
        with guarded_targets((target,), tmp_path / "backups", "cert579_restore_fails") as guard:
            target.write_text("mutated\n")
            # The backup vanishes — a stand-in for the concurrent overwrite.
            guard.backups[target].unlink()


# ---------------------------------------------------------------------------
# CERT-588: oracle ISOLATION, not just a pristine tree afterwards
# ---------------------------------------------------------------------------
#
# CERT-579's repair gave every run its own backup, so the file always ends up
# pristine. CERT-588 showed that is the wrong property to assert. `start()`
# SKIPPED a live manifest rather than waiting on it, so the second run could
# copy the first run's already-mutated target into its own backup and then
# mutate the same file: A wrote `A`, B wrote `B`, **A's oracle read `B`**, both
# exited 0, and the final file was pristine. A run scored ANOTHER run's mutant
# as its own and banked a KILLED or SURVIVED that describes neither.
#
# No assertion about final bytes can see that, which is why the probe below
# checks what each process OBSERVES while it holds the file — the thing an
# oracle actually depends on.


def test_each_run_observes_only_its_own_mutant(tmp_path):
    """The isolation property: each process must read back what IT wrote.

    🔴 SYNCHRONIZED WITH HANDSHAKE FILES, NOT WITH SLEEPS, and that is the whole
    difference between a test that reproduces CERT-588 and one that does not. A
    first version of this used `sleep(1.0)` to stagger the two runs and it PASSED
    against the pre-lock guard — B happened to finish and restore A's mutant back
    before A got round to reading, so A saw its own bytes by luck. The defect is a
    WINDOW, so the probe has to hold the window open on purpose:

        A: mutate -> announce `a_ready` -> wait for `b_wrote` -> READ
        B: wait for `a_ready` -> mutate -> announce `b_wrote` -> READ

    Pre-lock, B mutates while A is parked, so A's read returns B's bytes. With the
    lock, B is still waiting to start, `b_wrote` never appears, A's bounded wait
    lapses and A reads its own — then releases, and B runs cleanly afterwards.
    """
    import subprocess
    import sys
    import textwrap

    backend = Path(__file__).resolve().parents[1]
    target = tmp_path / "victim.py"
    target.write_text("ORIGINAL\n")
    a_ready, b_wrote = tmp_path / "a_ready", tmp_path / "b_wrote"

    worker = tmp_path / "worker.py"
    worker.write_text(
        textwrap.dedent(
            f'''
            import sys, time, pathlib
            sys.path.insert(0, {str(backend)!r})
            from scripts.evals._mutation_guard import guarded_targets
            target = pathlib.Path({str(target)!r})
            a_ready = pathlib.Path({str(a_ready)!r})
            b_wrote = pathlib.Path({str(b_wrote)!r})
            tag = sys.argv[1]

            def wait_for(path, limit):
                end = time.monotonic() + limit
                while time.monotonic() < end:
                    if path.exists():
                        return True
                    time.sleep(0.05)
                return False

            if tag == "B":
                wait_for(a_ready, 15)
            with guarded_targets((target,), {str(tmp_path / "backups")!r}, "cert588_probe"):
                target.write_text("MUTATED BY " + tag + "\\n")
                if tag == "A":
                    a_ready.write_text("x")
                    wait_for(b_wrote, 6)
                else:
                    b_wrote.write_text("x")
                    time.sleep(0.3)
                observed = target.read_text().strip()
            print("OBSERVED:" + observed)
            '''
        )
    )

    def _spawn(tag):
        return subprocess.Popen(
            [sys.executable, str(worker), tag],
            cwd=str(backend), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

    a, b = _spawn("A"), _spawn("B")
    out_a, out_b = a.communicate()[0], b.communicate()[0]

    def _observed(out, tag):
        line = [ln for ln in out.splitlines() if ln.startswith("OBSERVED:")]
        assert line, f"run {tag} never reported what it observed:\n{out}"
        return line[0].split(":", 1)[1]

    seen_a, seen_b = _observed(out_a, "A"), _observed(out_b, "B")
    assert seen_a == "MUTATED BY A", (
        f"run A's oracle observed {seen_a!r} — another run mutated the target while A "
        "was reading it, so A's verdict describes somebody else's mutant (CERT-588)"
    )
    assert seen_b == "MUTATED BY B", (
        f"run B's oracle observed {seen_b!r} — the same defect from the other side"
    )
    assert target.read_text() == "ORIGINAL\n", "the target must still end up pristine"


def test_the_target_lock_is_scoped_to_the_targets_not_the_label(tmp_path):
    """Serialization is the cost of sharing a FILE; nothing else should pay it."""
    import importlib

    mg = importlib.import_module("scripts.evals._mutation_guard")

    one, two = tmp_path / "one.py", tmp_path / "two.py"
    one.write_text("a = 1\n")
    two.write_text("b = 2\n")

    original_dir = mg.MANIFEST_DIR
    mg.MANIFEST_DIR = tmp_path / "manifests"
    mg.MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    try:
        g_one = mg._Guard((one,), tmp_path / "b1", "same_label")
        g_two = mg._Guard((two,), tmp_path / "b2", "same_label")
        assert g_one._lock_path() != g_two._lock_path(), (
            "two guards over DIFFERENT targets share a lock — unrelated harnesses "
            "would serialize for no reason"
        )
        g_same = mg._Guard((one,), tmp_path / "b3", "a_totally_different_label")
        assert g_one._lock_path() == g_same._lock_path(), (
            "two guards over the SAME target take different locks — the label must "
            "not be part of the key or the mutual exclusion does not hold"
        )
    finally:
        mg.MANIFEST_DIR = original_dir


def test_the_lock_fails_closed_rather_than_hanging(tmp_path, monkeypatch):
    """A wedged holder must produce a loud refusal, not a silent hang.

    The bounded wait is what makes serialization safe to adopt: ordinary overlap
    queues, and a run that never releases turns into a message naming the lock
    file instead of a CI job that sits there until the runner kills it.
    """
    import importlib

    mg = importlib.import_module("scripts.evals._mutation_guard")

    target = tmp_path / "victim.py"
    target.write_text("x = 1\n")
    original_dir = mg.MANIFEST_DIR
    mg.MANIFEST_DIR = tmp_path / "manifests"
    mg.MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MUTATION_GUARD_LOCK_TIMEOUT_S", "1")
    try:
        holder = mg._Guard((target,), tmp_path / "b", "holder").start()
        try:
            with pytest.raises(RuntimeError, match="could not take the target lock"):
                mg._Guard((target,), tmp_path / "b2", "second").start()
        finally:
            holder.restore_all()
            holder.finish()
        # And once the holder is gone the lock is free again — a released lock
        # that stays held would be the same hang wearing a different hat.
        second = mg._Guard((target,), tmp_path / "b3", "second").start()
        second.restore_all()
        second.finish()
    finally:
        mg.MANIFEST_DIR = original_dir
