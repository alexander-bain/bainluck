"""Guard tests for `tools/native-shoot.sh` binary resolution (#5480, native/126).

THE SAME INVARIANT AS test_native_gates_tree_resolution.py, ONE LAYER OVER
-------------------------------------------------------------------------
A native rig must name what it acted on, and must never spell "I could not tell"
the way it spells "nothing to report". The gates script broke that rule about the
TREE it built; this script broke it about the BINARY it photographed.

`APP` was a hardcoded DerivedData path carrying Xcode's per-machine hash:

    APP="/Users/bain/Library/.../Bain_Luck-bkmrwhmxuqqsseeuqlyqvcavesmz/.../Bain Luck.app"

Two failures, and the dangerous one is silent:

  1. On a machine whose hash differs, `install` fails — loud, survivable.
  2. On the machine it was written for it ALWAYS resolves, so a shoot taken
     before a build finished — or after one that failed — photographs the
     PREVIOUS binary and prints `shot <label>.png` exactly as a good run does.

Standing notice 4 (the LOOK RULE) makes a screenshot the evidence that a change
is done. A PNG of the previous build is wrong evidence that looks identical to
right evidence, which is the whole reason this class of bug is worth a test.

MEASURED 2026-09-12: 28 `Bain_Luck-*` DerivedData directories existed on this
machine. Resolution is now "newest wins" over a glob, the count is printed, and
a binary older than the newest Swift source is REFUSED rather than shot.

NOT VACUOUS
-----------
These drive the script through `--resolve-only` — real resolution, real mtime
comparison, stopping before simctl — against synthetic DerivedData trees. No
simulator, no Xcode, no network. Gotcha #54: never piped, the exit code is
asserted as a VALUE.
"""

import os
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SHOOT = REPO / "tools" / "native-shoot.sh"

pytestmark = [
    pytest.mark.skipif(not SHOOT.is_file(), reason="native-shoot.sh is not in this checkout"),
    # `stat -f %m` and `date -r` are BSD spellings. The script is a macOS-only rig
    # (simctl, Xcode); on Linux CI these assertions would grade the coreutils
    # flavour, not the script, so they are skipped rather than made to lie.
    pytest.mark.skipif(os.uname().sysname != "Darwin", reason="macOS-only rig (BSD stat/date)"),
]


def make_app(root, name, mtime):
    """A synthetic built .app — the bundle name contains a space on purpose."""
    app = root / name / "Build" / "Products" / "Debug-iphonesimulator" / "Bain Luck.app"
    app.mkdir(parents=True)
    binary = app / "Bain Luck"
    binary.write_text("// pretend mach-o\n")
    os.utime(binary, (mtime, mtime))
    os.utime(app, (mtime, mtime))
    return app


def shoot(derived, *args, src_root, env_extra=None):
    """Drive the script's resolve-and-stop mode against a synthetic DerivedData.

    `src_root` is never optional. The staleness check measures the Swift sources
    under the SCRIPT's own git toplevel, so running the repo's real copy would
    grade this lane's working tree — every test would flip green or red on
    whether someone had touched a .swift file recently. Every test therefore
    drives a COPY of the script placed in a tree it fully controls.
    """
    env = dict(os.environ)
    env["NATIVE_SHOOT_DERIVED"] = str(derived)
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(
        ["bash", str(src_root / "tools" / "native-shoot.sh"), "probe", "", "--resolve-only", *args],
        capture_output=True, text=True, timeout=120, env=env,
    )
    return p.returncode, p.stdout + p.stderr


def _tree_with_script(tmp_path, src_mtime):
    """A git tree holding a copy of the script and one Swift source.

    SRC_ROOT is resolved from the SCRIPT's own toplevel, so the script has to
    live in the synthetic tree for the staleness check to measure it.
    """
    root = tmp_path / "tree"
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "native-shoot.sh").write_text(SHOOT.read_text())
    ios = root / "ios" / "Bain Luck"
    ios.mkdir(parents=True)
    src = ios / "Thing.swift"
    src.write_text("// source\n")
    os.utime(src, (src_mtime, src_mtime))
    subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "master", "."],
                   capture_output=True, timeout=60, check=True)
    return root


@pytest.fixture
def old_source_tree(tmp_path):
    """A tree whose Swift source predates any app the resolution tests build,
    so staleness never fires and those tests grade resolution alone."""
    return _tree_with_script(tmp_path, time.time() - 1_000_000)


# ── RESOLUTION ───────────────────────────────────────────────────────────────


def test_resolves_a_bundle_whose_name_contains_a_space(tmp_path, old_source_tree):
    """The regression that made the first draft of this fix report "not built".

    `for x in $(ls -td .../Bain\\ Luck.app)` word-splits the bundle in half, finds
    nothing, and reads exactly like "you have not built yet".
    """
    now = time.time()
    make_app(tmp_path, "Bain_Luck-aaa", now - 100)
    rc, out = shoot(tmp_path, src_root=old_source_tree)
    assert rc == 0, out
    assert "Bain Luck.app" in out, f"failed to resolve a bundle with a space:\n{out}"
    assert "NO BUILT APP FOUND" not in out


def test_picks_the_newest_of_many_derived_data_copies(tmp_path, old_source_tree):
    """28 existed on the real machine; a hardcoded hash picks one arbitrarily."""
    now = time.time()
    make_app(tmp_path, "Bain_Luck-old", now - 10_000)
    newest = make_app(tmp_path, "Bain_Luck-new", now - 10)
    make_app(tmp_path, "Bain_Luck-middle", now - 5_000)

    rc, out = shoot(tmp_path, src_root=old_source_tree)
    assert rc == 0, out
    assert str(newest) in out, f"did not pick the newest build:\n{out}"
    assert "Bain_Luck-old" not in out
    assert "newest of 3 built copies" in out, "did not disclose that it chose among several"


def test_a_single_copy_does_not_claim_to_have_chosen(tmp_path, old_source_tree):
    now = time.time()
    make_app(tmp_path, "Bain_Luck-only", now - 10)
    rc, out = shoot(tmp_path, src_root=old_source_tree)
    assert rc == 0, out
    assert "newest of" not in out, "cried wolf about choosing with one candidate"


def test_no_build_refuses_and_names_where_it_looked(tmp_path, old_source_tree):
    rc, out = shoot(tmp_path, src_root=old_source_tree)
    assert rc == 1, out
    assert "NO BUILT APP FOUND" in out
    assert str(tmp_path) in out, "did not say where it looked"
    assert "NATIVE_SHOOT_APP" in out, "did not name the override"


def test_the_explicit_override_wins(tmp_path, old_source_tree):
    now = time.time()
    make_app(tmp_path, "Bain_Luck-auto", now - 10)
    other = make_app(tmp_path / "elsewhere", "Bain_Luck-chosen", now - 9_999)
    rc, out = shoot(tmp_path, src_root=old_source_tree, env_extra={"NATIVE_SHOOT_APP": str(other)})
    assert rc == 0, out
    assert str(other) in out
    assert "Bain_Luck-auto" not in out


def test_it_always_prints_which_binary_and_when_it_was_built(tmp_path, old_source_tree):
    """A LOOK is evidence; evidence names its provenance."""
    now = time.time()
    app = make_app(tmp_path, "Bain_Luck-aaa", now - 100)
    rc, out = shoot(tmp_path, src_root=old_source_tree)
    assert rc == 0, out
    assert f"app: {app}" in out
    assert "built:" in out
    assert "UNKNOWN" not in out


# ── STALENESS: THE SILENT FAILURE ────────────────────────────────────────────


def test_a_binary_older_than_the_source_is_refused(tmp_path):
    """The shot that looks right and is not. This is the point of the whole file."""
    now = time.time()
    derived = tmp_path / "dd"
    derived.mkdir()
    make_app(derived, "Bain_Luck-aaa", now - 5_000)      # built earlier
    root = _tree_with_script(tmp_path, now - 10)          # edited later

    rc, out = shoot(derived, src_root=root)
    assert rc == 1, f"a stale binary was accepted:\n{out}"
    assert "STALE BINARY" in out, out
    assert "Thing.swift" in out, "did not name the source that is newer"
    assert "--allow-stale" in out, "did not name the override"


def test_allow_stale_proceeds_but_says_so(tmp_path):
    """An override that is silent is just the bug with an extra flag."""
    now = time.time()
    derived = tmp_path / "dd"
    derived.mkdir()
    make_app(derived, "Bain_Luck-aaa", now - 5_000)
    root = _tree_with_script(tmp_path, now - 10)

    rc, out = shoot(derived, "--allow-stale", src_root=root)
    assert rc == 0, out
    assert "shooting it anyway" in out
    assert "SAY SO" in out, "the override did not tell the operator to disclose it"


def test_a_fresh_binary_is_not_called_stale(tmp_path):
    """The refusal must not fire on the ordinary build-then-shoot sequence."""
    now = time.time()
    derived = tmp_path / "dd"
    derived.mkdir()
    make_app(derived, "Bain_Luck-aaa", now - 10)          # built after
    root = _tree_with_script(tmp_path, now - 5_000)       # edited before

    rc, out = shoot(derived, src_root=root)
    assert rc == 0, out
    assert "STALE" not in out, f"cried wolf on a fresh build:\n{out}"


def test_resolve_only_installs_nothing(tmp_path, old_source_tree):
    now = time.time()
    make_app(tmp_path, "Bain_Luck-aaa", now - 10)
    rc, out = shoot(tmp_path, src_root=old_source_tree)
    assert rc == 0, out
    assert "nothing installed, nothing shot" in out
    assert "shot " not in out


def test_the_script_parses():
    p = subprocess.run(["bash", "-n", str(SHOOT)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
