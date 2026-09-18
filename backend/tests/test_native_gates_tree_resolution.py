"""Guard tests for `tools/native-gates.sh` tree resolution (#5480, native/126).

WHAT REGRESSED, AND WHY THESE TESTS EXIST
-----------------------------------------
`native-gates.sh` derived the Xcode project from `${BASH_SOURCE[0]}`, so

    cd ~/bainluck-dev/native && bash ~/bainluck/tools/native-gates.sh

built and tested **~/bainluck** — the shared master checkout — and printed a
perfectly well-formed `Executed N tests, with 0 failures` line for MASTER.

Standing notice 10's iOS clause makes that one line the entire iOS gate, because
CI compiles no Swift. It is the one gate in the fleet with no independent check,
and it could green a tree that did not contain the change. native/123 banked
`Executed 2027` — exactly the *previous* ship's count — for a branch whose real
count was 2034. A stale-but-plausible number is the hardest kind to catch by eye.

The second defect was worse, because it was silent in the direction that matters.
The recompile proof ran `git diff --name-only "$BASE"...HEAD 2>/dev/null`.
Three-dot needs a merge base; under a shallow clone (#5428) `git merge-base`
exits non-zero, the redirect ate the error, the list came back empty, and the
script printed "no changed Swift files — nothing to prove". **A vacuous pass,
worded identically to the legitimate no-op.** The check that exists specifically
to catch "you did not build what you think you built" is the one that went quiet.

AMENDED 2026-09-18 (native/231): SHALLOW IS NOT THE SAME AS BASELESS.
The paragraph above is right about what #5428 saw and wrong about what causes it.
A depth-1 clone whose base ref IS its own HEAD — every lane worktree on this
machine, and the fixture this file used — resolves a merge base instantly. Both
the script and this suite refused on shallowness itself, so the recompile proof
ran nowhere and the gate exited 1 on runs whose build and tests passed. The
blind case is a MISSING MERGE BASE; shallowness only explains one. The two tests
below now separate them, and #5428's own case (shallow *and* stranded) is still
guarded, remedy and all.

HOW THESE TESTS AVOID BEING VACUOUS THEMSELVES
----------------------------------------------
They do not grep the script for `rev-parse --show-toplevel`; a source-scan would
pass against a script that computed the right path and then ignored it. Every
test below DRIVES the script through `--explain` — a mode that performs the real
resolution and the real diff and then stops before xcodebuild — against
synthetic git repositories built in tmp_path, and asserts on what it resolved.

That makes the suite runnable in CI, on Linux, with no Xcode, no simulator and
no network: `--explain` touches nothing but git. Gotcha #54: the script is never
piped, its exit code is captured and asserted as a VALUE.

The load-bearing assertion is `test_gates_the_cwd_tree_not_the_script_tree`.
Everything else guards a way the fix could rot.
"""

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GATES = REPO / "tools" / "native-gates.sh"

pytestmark = pytest.mark.skipif(
    not GATES.is_file(), reason="native-gates.sh is not in this checkout"
)


def git(repo, *args, check=True):
    """Run git in `repo`. Always -C: a bare git call would read the CWD, which is
    the entire class of bug this file guards."""
    p = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60
    )
    if check and p.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed ({p.returncode}): {p.stderr}")
    return p.stdout.strip()


def explain(cwd, *args):
    """Drive the gate script's resolve-and-stop mode. Returns (rc, stdout+stderr).

    Never piped (gotcha #54) — the caller asserts on the exit code's VALUE.
    """
    p = subprocess.run(
        ["bash", str(GATES), "--explain", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return p.returncode, p.stdout + p.stderr


def make_repo(path, swift_name="A.swift", with_project=True):
    """A minimal tree shaped like this repo: a git root with ios/Bain Luck in it."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "master", ".")
    git(path, "config", "user.email", "gate@test")
    git(path, "config", "user.name", "gate")
    ios = path / "ios" / "Bain Luck"
    ios.mkdir(parents=True, exist_ok=True)
    if with_project:
        (ios / "Bain Luck.xcodeproj").mkdir(exist_ok=True)
        (ios / "Bain Luck.xcodeproj" / "project.pbxproj").write_text("// stub\n")
    (ios / swift_name).write_text("// base\n")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "base")
    return path


# ── THE HEADLINE REGRESSION ──────────────────────────────────────────────────


def test_gates_the_cwd_tree_not_the_script_tree(tmp_path):
    """Invoked from tree B, it must gate B — even though the script lives in A.

    This is #5480 itself. Before the fix the script resolved its project from
    BASH_SOURCE and gated A, printing a clean green for a tree with none of B's
    changes in it.
    """
    a = make_repo(tmp_path / "script_tree")
    b = make_repo(tmp_path / "work_tree")

    # The script is invoked BY ITS PATH IN A, with the CWD in B.
    (a / "tools").mkdir()
    (a / "tools" / "native-gates.sh").write_text(GATES.read_text())

    # B has a real change; A does not.
    (b / "ios" / "Bain Luck" / "Changed.swift").write_text("// only in B\n")

    p = subprocess.run(
        ["bash", str(a / "tools" / "native-gates.sh"), "--explain", "--base", "master"],
        cwd=str(b),
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = p.stdout + p.stderr
    assert p.returncode == 0, out

    assert f"gating {b}" in out, f"gated the wrong tree:\n{out}"
    assert str(a) not in out.split("THIS SCRIPT LIVES IN A DIFFERENT TREE")[0], (
        "resolved the script's tree as the subject"
    )
    # and it must have found B's change, not A's emptiness
    assert "Changed.swift" in out, f"did not see the CWD tree's change:\n{out}"


def test_a_divergent_script_tree_is_announced_not_silent(tmp_path):
    """The old failure was silent. When the two trees differ, say so."""
    a = make_repo(tmp_path / "script_tree")
    b = make_repo(tmp_path / "work_tree")
    (a / "tools").mkdir()
    (a / "tools" / "native-gates.sh").write_text(GATES.read_text())

    p = subprocess.run(
        ["bash", str(a / "tools" / "native-gates.sh"), "--explain", "--base", "master"],
        cwd=str(b),
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = p.stdout + p.stderr
    assert "THIS SCRIPT LIVES IN A DIFFERENT TREE" in out, out
    assert str(a) in out, "the divergent tree is not named"


def test_same_tree_prints_no_divergence_banner(tmp_path):
    """The banner must not cry wolf on the ordinary invocation."""
    b = make_repo(tmp_path / "work_tree")
    (b / "tools").mkdir()
    (b / "tools" / "native-gates.sh").write_text(GATES.read_text())
    p = subprocess.run(
        ["bash", str(b / "tools" / "native-gates.sh"), "--explain", "--base", "master"],
        cwd=str(b),
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = p.stdout + p.stderr
    assert p.returncode == 0, out
    assert "DIFFERENT TREE" not in out, out


# ── "I COULD NOT TELL" IS NOT SPELLED LIKE "NOTHING TO REPORT" ───────────────
#
# These three run together on purpose: the point is not merely that the two
# failures are caught, it is that all three outcomes are DISTINGUISHABLE.


def test_a_real_no_op_reports_a_comparison_that_happened(tmp_path):
    b = make_repo(tmp_path / "clean")
    rc, out = explain(b, "--base", "master")
    assert rc == 0, out
    assert "none" in out
    assert "CANNOT DETERMINE" not in out


def shallow_clone_of(origin, dest):
    """A depth-1 clone, asserted to really be shallow before anything reads it."""
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", f"file://{origin}", str(dest)],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    assert git(dest, "rev-parse", "--is-shallow-repository") == "true"
    git(dest, "config", "user.email", "gate@test")
    git(dest, "config", "user.name", "gate")
    return dest


def strand(repo, swift_name="Stranded.swift"):
    """Put the repo on a branch that shares no history with anything — the only
    way a merge base actually goes missing."""
    git(repo, "checkout", "-q", "--orphan", "stranded")
    git(repo, "rm", "-rqf", ".")
    ios = repo / "ios" / "Bain Luck"
    ios.mkdir(parents=True, exist_ok=True)
    (ios / "Bain Luck.xcodeproj").mkdir(exist_ok=True)
    (ios / "Bain Luck.xcodeproj" / "project.pbxproj").write_text("// stub\n")
    (ios / swift_name).write_text("// stranded\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "stranded")
    return repo


def test_a_shallow_repo_with_a_resolvable_base_is_not_blind(tmp_path):
    """SHALLOWNESS IS NOT BLINDNESS, and this file used to assert that it was.

    The original test cloned `--depth 1` and required exit 1 with the SHALLOW
    remedy — but that clone's `master` IS its own HEAD, so `git merge-base` answers
    instantly. The script agreed with the test by refusing a priori on
    `rev-parse --is-shallow-repository`, and between them they turned the
    recompile proof off for every lane worktree on this machine (all shallow) and
    made the gate exit 1 on runs whose build and tests both passed.

    Measured on b57235c0e in ~/bainluck-dev/native, 2026-09-18: the script said
    CANNOT DETERMINE while `git merge-base origin/master HEAD` returned
    9c8787a234 and the three-dot diff named both changed files.

    #5428's real observation is the case below this one, and it is still guarded.
    """
    origin = make_repo(tmp_path / "origin")
    shallow = shallow_clone_of(origin, tmp_path / "shallow")
    (shallow / "ios" / "Bain Luck" / "Changed.swift").write_text("// in the clone\n")

    rc, out = explain(shallow, "--base", "master")
    assert rc == 0, f"a resolvable comparison was refused as blind:\n{out}"
    assert "CANNOT DETERMINE" not in out, out
    assert "Changed.swift" in out, f"the proof ran but saw nothing:\n{out}"


def test_a_shallow_repo_that_really_has_no_base_still_says_shallow(tmp_path):
    """#5428's own case, kept: shallow AND baseless must name the unshallow remedy.

    Without this, the fix above would read as deleting the protection rather than
    aiming it.
    """
    origin = make_repo(tmp_path / "origin")
    shallow = strand(shallow_clone_of(origin, tmp_path / "shallow"))

    rc, out = explain(shallow, "--base", "origin/master")
    assert rc == 1, f"a blind proof must not exit 0:\n{out}"
    assert "SHALLOW" in out, out
    assert "fetch --unshallow" in out, "no remedy named"
    # THE POINT: it must not be worded like the legitimate no-op.
    assert "nothing to prove" not in out, out


def test_an_unresolvable_base_fails_and_is_worded_differently(tmp_path):
    """No merge base is a different fault from a shallow clone, and from a no-op."""
    b = make_repo(tmp_path / "work")
    # An orphan branch shares no history with master.
    git(b, "checkout", "-q", "--orphan", "unrelated")
    git(b, "rm", "-rqf", ".")
    (b / "other.txt").write_text("x\n")
    git(b, "add", "-A")
    git(b, "commit", "-qm", "unrelated")
    git(b, "checkout", "-q", "master")

    rc, out = explain(b, "--base", "unrelated")
    assert rc == 1, f"could-not-tell must not exit 0:\n{out}"
    assert "no merge base" in out.lower(), out
    assert "nothing to prove" not in out, out
    assert "SHALLOW" not in out, "misdiagnosed as the shallow case"


def test_one_unambiguous_marker_separates_blind_from_no_op(tmp_path):
    """Belt on the two above, and the sharpest form of #5480's second defect.

    There must be ONE marker that means "I could not tell", it must appear in
    every blind case, and it must appear in no honest one. Asserting the three
    sentences are merely *different* is too weak — a wording that unified the
    blind cases with the no-op still differs between them by the base's name,
    and would slip through while restoring exactly the bug.

    A future edit that re-unified the wording fails here even if it keeps both
    exit codes and both cause names intact.
    """
    MARKER = "CANNOT DETERMINE"

    clean = make_repo(tmp_path / "clean")
    clean_rc, clean_out = explain(clean, "--base", "master")

    origin = make_repo(tmp_path / "origin")
    # Shallow AND stranded: the blind case. A depth-1 clone on its own branch is
    # NOT blind (see above), and using one here would assert the marker on a run
    # that could see perfectly well.
    shallow = strand(shallow_clone_of(origin, tmp_path / "shallow"))
    shallow_rc, shallow_out = explain(shallow, "--base", "origin/master")

    unrelated = make_repo(tmp_path / "unrelated")
    git(unrelated, "checkout", "-q", "--orphan", "other")
    git(unrelated, "rm", "-rqf", ".")
    (unrelated / "x.txt").write_text("x\n")
    git(unrelated, "add", "-A")
    git(unrelated, "commit", "-qm", "orphan")
    git(unrelated, "checkout", "-q", "master")
    unrel_rc, unrel_out = explain(unrelated, "--base", "other")

    # The honest no-op: exit 0, and the marker absent.
    assert clean_rc == 0, clean_out
    assert MARKER not in clean_out, "an honest comparison claimed it was blind"

    # Both blind cases: exit non-zero, marker present, own cause named.
    for name, rc, out, cause in (
        ("shallow", shallow_rc, shallow_out, "SHALLOW"),
        ("unrelated base", unrel_rc, unrel_out, "no merge base"),
    ):
        assert rc == 1, f"{name} exited {rc}, so a blind proof read as a pass:\n{out}"
        assert MARKER in out, f"{name} did not carry the blind marker:\n{out}"
        assert cause.lower() in out.lower(), f"{name} did not name its cause:\n{out}"


# ── RESOLUTION EDGE CASES ────────────────────────────────────────────────────


def test_project_root_overrides_both(tmp_path):
    a = make_repo(tmp_path / "script_tree")
    b = make_repo(tmp_path / "target")
    rc, out = explain(a, "--project-root", str(b), "--base", "master")
    assert rc == 0, out
    assert f"gating {b}" in out, out


def test_a_tree_with_no_xcode_project_refuses_by_name(tmp_path):
    """Exit 2, naming the path it looked for — not a confusing xcodebuild error."""
    b = make_repo(tmp_path / "no_project", with_project=False)
    rc, out = explain(b, "--base", "master")
    assert rc == 2, out
    assert "NO XCODE PROJECT" in out, out
    assert "Bain Luck.xcodeproj" in out, "did not name the path it looked for"


def test_a_non_git_cwd_falls_back_to_the_script_tree_and_says_so(tmp_path):
    """Falling back is fine. Falling back silently is not."""
    a = make_repo(tmp_path / "script_tree")
    (a / "tools").mkdir()
    (a / "tools" / "native-gates.sh").write_text(GATES.read_text())
    outside = tmp_path / "not_a_repo"
    outside.mkdir()

    p = subprocess.run(
        ["bash", str(a / "tools" / "native-gates.sh"), "--explain", "--base", "master"],
        cwd=str(outside),
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = p.stdout + p.stderr
    assert p.returncode == 0, out
    assert f"gating {a}" in out, out
    assert "CWD is not a git tree" in out, "fell back without saying so"


def test_explain_builds_nothing(tmp_path):
    """--explain is the testable seam only because it stops before xcodebuild."""
    b = make_repo(tmp_path / "work")
    rc, out = explain(b, "--base", "master")
    assert rc == 0, out
    assert "nothing was built" in out
    assert "BUILD SUCCEEDED" not in out
    assert "BainLuckTests" not in out


# ── THE SELF-DESCRIBING SUMMARY ──────────────────────────────────────────────


def test_the_resolution_block_names_tree_sha_and_branch(tmp_path):
    """A number pasted into a PR body has to carry its provenance (#5480).

    `Executed 2027` was indistinguishable from `Executed 2034` precisely because
    neither said which tree produced it.
    """
    b = make_repo(tmp_path / "work")
    sha = git(b, "rev-parse", "HEAD")
    rc, out = explain(b, "--base", "master")
    assert rc == 0, out
    assert str(b) in out
    assert sha in out, "the gated sha is not printed"
    assert "master" in out, "the gated branch is not printed"


def test_swift_files_outside_ios_are_not_claimed_as_changed(tmp_path):
    """The proof asks "did THIS BUILD compile it", so it may only count ios/.

    MEASURED on the shared checkout 2026-09-12: `~/bainluck` carries untracked
    scratch copies of the whole iOS tree (`cert-scratch-593/`), and the unscoped
    `*.swift` pathspec claimed 226 of them as changed files awaiting proof. Every
    one would have reported NOT SEEN IN THE BUILD LOG — truthfully, since they
    are not in the project — burying any real miss in noise.
    """
    b = make_repo(tmp_path / "work")
    scratch = b / "cert-scratch-999" / "ios" / "Bain Luck"
    scratch.mkdir(parents=True)
    (scratch / "Copy.swift").write_text("// not in the project\n")
    (b / "ios" / "Bain Luck" / "Real.swift").write_text("// in the project\n")

    rc, out = explain(b, "--base", "master")
    assert rc == 0, out
    assert "Real.swift" in out, "missed a Swift file the build does compile"
    assert "Copy.swift" not in out, (
        f"claimed a Swift file outside ios/ as changed:\n{out}"
    )


def test_the_script_parses(tmp_path):
    p = subprocess.run(["bash", "-n", str(GATES)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
