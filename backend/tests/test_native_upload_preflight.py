"""Guard tests for `tools/native-upload.sh` — the unattended TestFlight path.

WHAT THIS SCRIPT IS AND WHY ITS PREFLIGHT IS THE PART WORTH TESTING
-------------------------------------------------------------------
Build 7 reached TestFlight by a person driving Xcode. `native-upload.sh` is the
path that needs no Xcode UI: archive → export → deliver. Its build and export
steps take minutes and need a Mac with Apple's toolchain, so they are not what
these tests drive. Its PREFLIGHT is, because preflight is where the script can
be silently wrong in both directions:

  * a machine that CANNOT sign an App Store build passing the checks, and
    discovering it five minutes into an archive, or
  * a machine that CAN being told it cannot.

Both read as "the release rig is flaky" rather than as a specific missing thing.

THE THREE FINDINGS EACH TEST CLASS ENCODES
------------------------------------------
1. A DISTRIBUTION PROFILE IS NOT A PROFILE WITH THE RIGHT BUNDLE ID. This machine
   has FOUR profiles naming `com.bainluck.Bain-Luck` and its widget: two "iOS
   Team Provisioning Profile" (development) and two "iOS Team Store Provisioning
   Profile" (App Store). They differ only by the presence of a
   `ProvisionedDevices` array. A check that matched the bundle id alone would
   find the development one first and say PASS on a machine that cannot export.

2. AN EXPORT THAT RENUMBERS THE BUILD BREAKS THE ONLY CLAIM THE RIG MAKES.
   `manageAppVersionAndBuildNumber` defaults to TRUE, and when it is on Xcode
   assigns its own build number during export — so the number in the archive we
   graded is not the number TestFlight receives. The preflight refuses that
   options file rather than producing a build nobody can identify.

3. A MODE THAT CANNOT FINISH MUST FAIL BEFORE IT BUILDS, NOT AFTER. `--upload`
   without an App Store Connect key cannot deliver anything. Archiving for five
   minutes first and then saying so wastes the only scarce thing in a release
   window, and — worse — leaves an .ipa on disk that looks like a finished run.

NOT VACUOUS
-----------
Every test drives the REAL script (`bash tools/native-upload.sh`) with `security`
and `xcodebuild` shimmed onto PATH. The shims are how the tests can assert the
thing that matters most: `--dry-run` and every refusal path leave the xcodebuild
sentinel UNWRITTEN, i.e. no build was started. A test that only read stdout could
not tell a refusal from a refusal-after-a-five-minute-archive.

Gotcha #54: nothing is piped, and the exit code is asserted as a VALUE — 2 (the
rig is unusable, nothing built) is a different verdict from 1 (a step ran and its
artifact is wrong), and the script's contract distinguishes them.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
UPLOAD = REPO / "tools" / "native-upload.sh"

pytestmark = [
    pytest.mark.skipif(not UPLOAD.is_file(), reason="native-upload.sh is not in this checkout"),
    # `date -j -f`, `stat -f` and `security` are macOS spellings. On Linux CI these
    # would grade coreutils, not the script, so they are skipped rather than made
    # to lie. The script is a macOS-only release rig by construction.
    pytest.mark.skipif(os.uname().sysname != "Darwin", reason="macOS-only release rig"),
]

TEAM = "J893F72P4R"
APP_ID = "com.bainluck.Bain-Luck"
WIDGET_ID = "com.bainluck.Bain-Luck.BainLuckWidget"

GOOD_EXPORT_OPTIONS = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>method</key><string>app-store-connect</string>
\t<key>teamID</key><string>%s</string>
\t<key>manageAppVersionAndBuildNumber</key><false/>
</dict>
</plist>
""" % TEAM


def profile_plist(bundle_id, *, store, expires="2027-09-11T00:19:37Z"):
    """One decoded provisioning profile.

    `store` decides the single fact the script keys on: an App Store profile has
    no ProvisionedDevices array, a development profile of the SAME bundle id has
    one. That is the whole distinction and it is the whole point of this fixture.
    """
    devices = "" if store else "\t<key>ProvisionedDevices</key><array><string>abc123</string></array>\n"
    kind = "Store " if store else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n<dict>\n'
        f"\t<key>Name</key><string>iOS Team {kind}Provisioning Profile: {bundle_id}</string>\n"
        f"\t<key>ExpirationDate</key><date>{expires}</date>\n"
        f"{devices}"
        "\t<key>Entitlements</key><dict>\n"
        f"\t\t<key>application-identifier</key><string>{TEAM}.{bundle_id}</string>\n"
        "\t</dict>\n</dict>\n</plist>\n"
    )


@pytest.fixture
def rig(tmp_path):
    """A synthetic machine: a project, profiles, export options and PATH shims.

    Returns a small object whose attributes the individual tests mutate before
    calling `run`, so each test says in one line how its machine differs from a
    healthy one.
    """

    class Rig:
        def __init__(self):
            self.root = tmp_path
            self.project = tmp_path / "ios" / "Bain Luck" / "Bain Luck.xcodeproj"
            self.project.mkdir(parents=True)
            (self.project / "project.pbxproj").write_text(
                "CURRENT_PROJECT_VERSION = 7;\n\t\tCURRENT_PROJECT_VERSION = 1;\n"
            )
            (tmp_path / "tools").mkdir()
            self.script = tmp_path / "tools" / "native-upload.sh"
            self.script.write_text(UPLOAD.read_text())

            self.options = tmp_path / "ExportOptions.plist"
            self.options.write_text(GOOD_EXPORT_OPTIONS)

            self.profiles = tmp_path / "profiles"
            self.profiles.mkdir()
            self.set_profile(APP_ID, store=True)
            self.set_profile(WIDGET_ID, store=True)

            self.identities = "  1) AAAA \"Apple Development: Alex Bain (X)\"\n  2) BBBB \"Apple Distribution: Alex Bain (%s)\"\n" % TEAM
            self.sentinel = tmp_path / "xcodebuild-was-called"
            self.bin = tmp_path / "bin"
            self.bin.mkdir()

        def set_profile(self, bundle_id, *, store, expires="2027-09-11T00:19:37Z", name=None):
            path = self.profiles / f"{name or bundle_id}.mobileprovision"
            path.write_text(profile_plist(bundle_id, store=store, expires=expires))
            return path

        def _write_shims(self):
            # `security` answers the two questions the script asks it, from files
            # this rig controls. `cms -D -i <f>` just prints the file, which is
            # what a decoded profile is.
            (self.bin / "security").write_text(
                "#!/bin/bash\n"
                'if [ "$1" = "find-identity" ]; then\n'
                f"  cat {self.root / 'identities.txt'}\n"
                "  exit 0\n"
                "fi\n"
                'if [ "$1" = "cms" ]; then\n'
                '  for a in "$@"; do last="$a"; done\n'
                '  cat "$last"\n'
                "  exit 0\n"
                "fi\n"
                "exit 1\n"
            )
            # The sentinel is the whole test for "did it build". An xcodebuild
            # that is never called leaves no file; one that is called leaves its
            # arguments, so a test can also assert WHAT it would have built.
            (self.bin / "xcodebuild").write_text(
                "#!/bin/bash\n"
                f'echo "$@" >> {self.sentinel}\n'
                "exit 0\n"
            )
            for f in ("security", "xcodebuild"):
                (self.bin / f).chmod(0o755)
            (self.root / "identities.txt").write_text(self.identities)

        def run(self, *args, env_extra=None):
            self._write_shims()
            env = dict(os.environ)
            env["PATH"] = f"{self.bin}:{env['PATH']}"
            env["NATIVE_EXPORT_OPTIONS"] = str(self.options)
            env["NATIVE_PROFILE_DIR"] = str(self.profiles)
            env["NATIVE_UPLOAD_ARCHIVE"] = str(self.root / "archive.xcarchive")
            env["NATIVE_UPLOAD_EXPORT_DIR"] = str(self.root / "export")
            env["NATIVE_UPLOAD_LOG_DIR"] = str(self.root)
            for v in ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_PATH"):
                env.pop(v, None)
            if env_extra:
                env.update(env_extra)
            p = subprocess.run(
                ["bash", str(self.script), *args],
                capture_output=True, text=True, timeout=120, env=env,
            )
            return p.returncode, p.stdout + p.stderr

        def built(self):
            return self.sentinel.exists()

    return Rig()


# ── the healthy machine ──────────────────────────────────────────────────────


def test_dry_run_passes_on_a_healthy_machine_and_builds_nothing(rig):
    """The baseline. Without it every refusal test below could pass vacuously —
    a script that refused everything would look perfect."""
    rc, out = rig.run("--dry-run")
    assert rc == 0, out
    assert "PREFLIGHT: PASS" in out
    assert "DRY RUN: PASS" in out
    assert not rig.built(), "a dry run started a build:\n" + out


def test_dry_run_prints_the_build_number_it_would_ship(rig):
    """A plan that does not name the build number is not a plan: the number is
    the one thing App Store Connect rejects a delivery over."""
    rc, out = rig.run("--dry-run", "--build", "8")
    assert rc == 0, out
    assert "CURRENT_PROJECT_VERSION=8" in out, out
    assert "build   : 8 (--build)" in out


def test_with_no_build_argument_the_number_is_disclosed_as_a_guess(rig):
    """The fallback reads the highest CURRENT_PROJECT_VERSION in the project
    file, which is a heuristic over two targets. A heuristic printed as a fact is
    how a rig starts lying, so it says so."""
    rc, out = rig.run("--dry-run")
    assert rc == 0, out
    assert "a guess" in out, out


# ── the machine that cannot sign ─────────────────────────────────────────────


def test_a_development_profile_does_not_satisfy_the_store_requirement(rig):
    """FINDING 1. Four profiles on the real machine name these two bundle ids;
    only two of them can export for the App Store, and they differ by the
    presence of ProvisionedDevices alone."""
    for p in rig.profiles.glob("*.mobileprovision"):
        p.unlink()
    rig.set_profile(APP_ID, store=False)
    rig.set_profile(WIDGET_ID, store=False)

    rc, out = rig.run("--dry-run")
    assert rc == 2, out
    assert "no App Store distribution profile installed for com.bainluck.Bain-Luck" in out
    assert not rig.built()


def test_a_missing_widget_profile_fails_even_when_the_app_has_one(rig):
    """The widget is the half that is easy to forget: the app signs, the export
    dies. Both are asserted, so a check that stopped at the app would fail here."""
    (rig.profiles / f"{WIDGET_ID}.mobileprovision").unlink()
    rc, out = rig.run("--dry-run")
    assert rc == 2, out
    assert WIDGET_ID in out
    assert not rig.built()


def test_an_expired_store_profile_is_not_a_valid_one(rig):
    """An expired profile is present, correctly named, and useless. Xcode's own
    message for it talks about signing, which reads like a certificate problem."""
    rig.set_profile(APP_ID, store=True, expires="2020-01-01T00:00:00Z")
    rc, out = rig.run("--dry-run")
    assert rc == 2, out
    assert "EXPIRED" in out
    assert not rig.built()


def test_a_development_identity_alone_is_refused(rig):
    """A machine with only 'Apple Development' cannot sign a store build. A
    count-based check ('1 valid identity found') would pass here."""
    rig.identities = '  1) AAAA "Apple Development: Alex Bain (X)"\n'
    rc, out = rig.run("--dry-run")
    assert rc == 2, out
    assert "Apple Distribution" in out
    assert not rig.built()


# ── the options file that would renumber the build ───────────────────────────


def test_export_options_that_renumber_the_build_are_refused(rig):
    """FINDING 2, and the default Xcode ships: with this on, the build number in
    the archive we graded is not the number TestFlight shows."""
    rig.options.write_text(GOOD_EXPORT_OPTIONS.replace(
        "<key>manageAppVersionAndBuildNumber</key><false/>",
        "<key>manageAppVersionAndBuildNumber</key><true/>",
    ))
    rc, out = rig.run("--dry-run")
    assert rc == 2, out
    assert "renumber" in out
    assert not rig.built()


def test_a_non_app_store_export_method_is_refused(rig):
    """release-testing produces a well-formed .ipa that App Store Connect will
    not take. It fails at the last step of a long path, or not at all."""
    rig.options.write_text(GOOD_EXPORT_OPTIONS.replace(
        "app-store-connect", "release-testing"))
    rc, out = rig.run("--dry-run")
    assert rc == 2, out
    assert "does not produce an App Store build" in out
    assert not rig.built()


def test_a_malformed_options_plist_is_refused_before_the_build(rig):
    rig.options.write_text("this is not a plist\n")
    rc, out = rig.run("--dry-run")
    assert rc == 2, out
    assert "not a valid plist" in out
    assert not rig.built()


# ── the modes that need a credential ─────────────────────────────────────────


def test_upload_without_a_credential_refuses_before_archiving(rig):
    """FINDING 3. The expensive failure is the one that archives first."""
    rc, out = rig.run("--upload", "--build", "8")
    assert rc == 2, out
    assert "ASC_KEY_ID" in out
    assert not rig.built(), "it started a build it could never deliver:\n" + out


def test_upload_refuses_an_inherited_build_number(rig):
    """A guessed build number is free in a dry run and expensive in an upload:
    App Store Connect rejects a duplicate AFTER the delivery."""
    rc, out = rig.run("--upload", env_extra={
        "ASC_KEY_ID": "AAAA1234", "ASC_ISSUER_ID": "u-u-i-d",
        "ASC_KEY_PATH": str(rig.root / "key.p8"),
    })
    assert rc == 2, out
    assert "needs an explicit --build" in out
    assert not rig.built()


def test_a_key_path_naming_no_file_counts_as_absent(rig):
    """Three set variables are not a credential. A path that names nothing is
    the failure mode of a key copied between machines."""
    rc, out = rig.run("--upload", "--build", "8", env_extra={
        "ASC_KEY_ID": "AAAA1234", "ASC_ISSUER_ID": "u-u-i-d",
        "ASC_KEY_PATH": str(rig.root / "does-not-exist.p8"),
    })
    assert rc == 2, out
    assert "names no file" in out
    assert not rig.built()


def test_export_mode_needs_no_credential_at_all(rig):
    """The half that must keep working while the key is Alex's to mint: the .ipa
    is produced offline, so the credential blocks only the last inch."""
    rc, out = rig.run("--dry-run")
    assert rc == 0, out
    assert "asc key : ABSENT" in out
    assert "export still run" in out or "archive and export still run" in out


# ── arguments ────────────────────────────────────────────────────────────────


def test_no_mode_is_an_error_not_a_default(rig):
    """A release script whose no-argument behaviour is 'upload' is a foot-gun;
    one whose no-argument behaviour is silence is worse."""
    rc, out = rig.run()
    assert rc == 2, out
    assert "name a mode" in out
    assert not rig.built()


def test_a_non_numeric_build_is_refused(rig):
    rc, out = rig.run("--dry-run", "--build", "eight")
    assert rc == 2, out
    assert "whole number" in out
    assert not rig.built()


def test_an_unknown_argument_is_refused_rather_than_ignored(rig):
    """`--upload-app` is one plausible typo away from `--upload`, and a script
    that ignored it would print a preflight and exit 2 for 'no mode' — a true
    message about the wrong problem."""
    rc, out = rig.run("--uplaod")
    assert rc == 2, out
    assert "unknown argument" in out
    assert not rig.built()


# ── which tree is in the binary (#5480's class, in the release tool) ─────────
#
# FINDING 4, and the reason this block exists. `REPO_ROOT` is derived from the
# SCRIPT'S OWN LOCATION, so `bash ~/bainluck/tools/native-upload.sh` archives
# ~/bainluck whatever worktree the caller is standing in. That default is right
# for a release — TestFlight should carry master, not a lane branch — and these
# tests do not change it. What was wrong is that the script never said which tree
# it chose and never asked whether that tree was current, which is exactly the
# bug `native-gates.sh` was fixed for in #5480: there it printed a well-formed
# pass line FOR THE WRONG TREE. In a tool that produces the binary the same
# silence ships stale code to a phone with a clean-looking log.
#
# Measured on 2026-09-12 while this was written: the shared checkout was four
# commits behind origin/master with TWO of them touching `ios/`. The old script
# would have archived it and said nothing.
#
# THE DISTINCTION THESE TESTS EXIST TO PIN is between a MEASURED defect and an
# ABSENT measurement. Behind-master and dirty-`ios/` are measured, and they stop
# a build. No git, no network, or a remote sha this tree has never fetched are
# absences — they are printed loudly and they PASS, because a guard that refuses
# offline is a guard someone switches off. `test_a_tree_that_is_not_a_git_repo_
# still_builds` is the anti-over-reach control: the first draft of this change
# refused there, and it broke all seventeen tests above, which is how the
# over-reach was caught rather than shipped.


def _gitify(root, *, behind=False, behind_touches_ios=False, dirty_ios=False, fetch=True):
    """Turn the rig's synthetic machine into a real git checkout with a real origin.

    A fake is not available here: the script asks git itself (`ls-remote`,
    `merge-base --is-ancestor`, `status --porcelain`), so a shim would grade the
    shim. `behind` pushes a commit to origin from a scratch clone and then
    FETCHES it, because the two unhappy states differ by exactly that fetch —
    without it the remote sha is not local and the script must say UNVERIFIED
    rather than BEHIND.
    """
    # Named off root.name, which pytest makes unique per test. `root.parent` is
    # the SESSION directory and is shared, so a fixed "origin.git" there is a
    # cross-test collision that passes alone and fails in a full run — which is
    # exactly how this was found.
    origin = root.parent / f"origin-{root.name}.git"
    scratch = root.parent / f"scratch-{root.name}"

    def git(*args, cwd):
        return subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=60,
            env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"},
        )

    subprocess.run(["git", "init", "--bare", "-b", "master", str(origin)],
                   capture_output=True, text=True, timeout=60)
    git("init", "-b", "master", cwd=root)
    git("config", "user.email", "rig@example.com", cwd=root)
    git("config", "user.name", "rig", cwd=root)
    git("add", "-A", cwd=root)
    git("commit", "-m", "base", cwd=root)
    git("remote", "add", "origin", str(origin), cwd=root)
    git("push", "-u", "origin", "master", cwd=root)

    if behind:
        git("clone", str(origin), str(scratch), cwd=root.parent)
        git("config", "user.email", "rig@example.com", cwd=scratch)
        git("config", "user.name", "rig", cwd=scratch)
        if behind_touches_ios:
            target = scratch / "ios" / "Bain Luck" / "Later.swift"
        else:
            target = scratch / "README.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("landed after this tree was cut\n")
        git("add", "-A", cwd=scratch)
        git("commit", "-m", "later", cwd=scratch)
        git("push", "origin", "master", cwd=scratch)
        # The fetch is the point: it makes the remote commit LOCAL, which is what
        # turns "unmeasured" into "measurably behind". Skipping it models the
        # checkout that has not fetched in hours — the state whose LOCAL
        # `origin/master` ref still points at its own HEAD.
        if fetch:
            git("fetch", "origin", cwd=root)

    if dirty_ios:
        (root / "ios" / "Bain Luck" / "Uncommitted.swift").write_text("// not committed\n")


def _assert_reached_xcodebuild(rc, out, rig):
    """The gate let this build through.

    `rc == 0` is deliberately NOT asserted for build modes. The rig's xcodebuild
    is a shim that records its arguments and creates no archive, so the script
    correctly grades the missing artifact and exits 1 — that is the shim's
    limitation, not the script's behaviour, and asserting 0 would mean shimming
    the artifact grade too, i.e. asserting a fiction. What this change owns is
    the gate, and the gate's observable effect is exactly these two facts:
    no refusal, and xcodebuild reached.
    """
    assert "refusing to build from this tree" not in out, out
    assert rc != 2, "the rig refused before building:\n" + out
    assert rig.built(), "the gate blocked a build it should have allowed:\n" + out


def test_a_stale_local_origin_ref_is_never_read_as_current(rig):
    """THE SURVIVOR THIS WAS ADDED FOR, and the sharpest edge in the change.

    `git rev-parse origin/master` is the obvious way to ask "how far behind am
    I", and it is wrong in precisely the case that matters: a checkout that has
    not fetched has a LOCAL `origin/master` still pointing at its own HEAD, so
    the obvious query answers "level with master, you are current" about a tree
    that is a day stale. That is a reassuring zero, which is worse than no
    answer — it is the failure the whole guard exists to prevent, wearing the
    guard's own uniform.

    So the script asks the REMOTE by `ls-remote`. Here origin has moved and this
    tree has never fetched, so the honest answer is that containment is
    UNMEASURED. The assertion that carries the test is the negative one: the
    script must not print `current`. A mutant swapping `ls-remote` for
    `rev-parse origin/master` passed every other test in this block.
    """
    _gitify(rig.root, behind=True, behind_touches_ios=True, fetch=False)
    rc, out = rig.run("--dry-run")
    assert rc == 0, out
    assert "current" not in out, "a tree that never fetched was called current:\n" + out
    assert "not in this tree yet" in out, out
    assert "UNVERIFIED" in out, out
    assert not rig.built()


def test_a_tree_behind_master_refuses_to_build_and_says_how_far(rig):
    """THE SHIP. A build mode on a stale checkout stops before xcodebuild, and
    the message names the distance rather than saying 'stale' — four commits with
    two touching ios/ is a different decision from four docs commits."""
    _gitify(rig.root, behind=True, behind_touches_ios=True)
    rc, out = rig.run("--archive", "--build", "8")
    assert rc == 2, out
    assert "refusing to build from this tree" in out, out
    assert "BEHIND by 1 commit(s), 1 of them touching ios/" in out, out
    assert not rig.built(), "it refused AFTER starting a build:\n" + out


def test_the_same_stale_tree_is_described_by_a_dry_run_rather_than_refused(rig):
    """A preflight exists to describe a machine, including a bad one. If the
    diagnostic mode refused too, the only way to learn why would be to try to
    build — and the operator would learn it in a release window."""
    _gitify(rig.root, behind=True)
    rc, out = rig.run("--dry-run")
    assert rc == 0, out
    assert "PREFLIGHT: PASS" in out
    assert "BEHIND by 1 commit(s)" in out, out
    assert not rig.built()


def test_a_current_tree_builds(rig):
    """The control that stops every test above from passing vacuously: on a tree
    that contains origin/master the gate is silent and xcodebuild is reached."""
    _gitify(rig.root)
    rc, out = rig.run("--archive", "--build", "8")
    assert "CONTAINS" in out, out
    assert "current" in out, out
    _assert_reached_xcodebuild(rc, out, rig)


def test_uncommitted_ios_changes_refuse_even_on_a_current_tree(rig):
    """Being level with master is not the same as building what master says. An
    uncommitted Swift file is in the binary and in no commit, so nothing could
    later say what shipped."""
    _gitify(rig.root, dirty_ios=True)
    rc, out = rig.run("--archive", "--build", "8")
    assert rc == 2, out
    assert "uncommitted change(s) under ios/" in out, out
    assert not rig.built()


def test_dirt_outside_ios_does_not_block_an_ios_build(rig):
    """Scope. This rig writes shims, logs and a sentinel into the tree on every
    run, and a guard that counted those would fire on every healthy release and
    be disabled within a day."""
    _gitify(rig.root)
    (rig.root / "notes.txt").write_text("scratch\n")
    (rig.root / "backend").mkdir(exist_ok=True)
    (rig.root / "backend" / "whatever.py").write_text("x = 1\n")
    rc, out = rig.run("--archive", "--build", "8")
    _assert_reached_xcodebuild(rc, out, rig)


def test_allow_stale_tree_is_an_override_that_still_prints_the_warning(rig):
    """An escape hatch that hides what it is escaping is how the warning stops
    being read. The facts stay on screen; only the refusal is lifted."""
    _gitify(rig.root, behind=True, behind_touches_ios=True)
    rc, out = rig.run("--archive", "--build", "8", "--allow-stale-tree")
    assert "BEHIND by 1 commit(s), 1 of them touching ios/" in out, out
    _assert_reached_xcodebuild(rc, out, rig)


def test_a_tree_that_is_not_a_git_repo_still_builds_but_says_it_is_unverified(rig):
    """ANTI-OVER-REACH CONTROL. An absent measurement is not a measured defect.
    The first draft refused here and broke the seventeen tests above — which is
    the evidence that refusing on absence is too strong, kept as a test so the
    next person does not re-tighten it."""
    rc, out = rig.run("--archive", "--build", "8")
    assert "NOT a git repo" in out, out
    assert "UNVERIFIED" in out, out
    _assert_reached_xcodebuild(rc, out, rig)


def test_the_tree_is_named_in_every_mode_not_only_when_it_is_wrong(rig):
    """#5480's actual lesson. The old script was not wrong about the tree — it
    was SILENT about it, so a well-formed log described a tree nobody had chosen.
    A reader must be able to see which checkout a good build came from too."""
    _gitify(rig.root)
    rc, out = rig.run("--dry-run")
    assert rc == 0, out
    assert f"tree    : {rig.root}" in out, out
    assert "resolved from the script's own location" in out, out
    assert "master @ " in out, out


def test_repo_overrides_the_scripts_own_location_and_the_preflight_follows_it(rig, tmp_path_factory):
    """`--repo` is the sanctioned way to aim the tool, and the whole preflight —
    not just a banner — must describe the tree it names, or the flag is a lie
    that reads as a feature."""
    other = tmp_path_factory.mktemp("other-checkout")
    proj = other / "ios" / "Bain Luck" / "Bain Luck.xcodeproj"
    proj.mkdir(parents=True)
    (proj / "project.pbxproj").write_text("CURRENT_PROJECT_VERSION = 99;\n")
    rc, out = rig.run("--dry-run", "--repo", str(other))
    assert rc == 0, out
    assert f"tree    : {other}" in out, out
    assert "resolved from --repo" in out, out
    assert "build   : 99" in out, "the project read came from the old tree:\n" + out
    assert not rig.built()


def test_repo_pointing_nowhere_is_refused_before_anything_else(rig):
    """A typo'd path must not silently fall back to the script's own tree — that
    would archive the wrong checkout while the operator believed otherwise."""
    rc, out = rig.run("--dry-run", "--repo", "/no/such/checkout")
    assert rc == 2, out
    assert "--repo needs a directory that exists" in out, out
    assert not rig.built()
