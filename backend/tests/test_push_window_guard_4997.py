"""#4997, #6044 — the push wrapper, pinned on what survived the window's retirement.

The bug this script replaces was not "someone forgot notice 29". authority/114
checked the window **three times**, got "inside" every time, and pushed 29 minutes
early — because it was computing the time by adding its own ``sleep`` durations to
the session's opening stamp instead of reading a clock. That arithmetic only ever
drifts ahead, so it can never report "outside".

**The window itself is retired** (#6044; coordinator 2026-09-13 16:55 PT). Beat
moved to ``bainluck-heavy``, so a main-app release can no longer cycle the :15
rebuild the band protected, and a band that refuses 41 minutes of every hour now
costs a desk that merges hourly and buys nothing. The clock discipline outlives
it: the stamps this prints get quoted into ledgers and merge messages.

So the tests that matter are:

* the retirement is **structural, not switchable** — at every one of the 60
  minutes a releasing push is dispatched, and the band symbols are gone;
* nothing it prints **advises a wait**. That is the #6044 defect class itself:
  the desk spent two consecutive notes telling lanes to ignore a stale line
  their own merge tool printed;
* the CLI **cannot be handed a time** (a ``--now`` flag would rebuild the hole);
* it labels **toward assuming a release** on every uncertain answer, so a
  production check is never silently dropped;
* ``exec`` dispatches through ``execvp``, so the clock read and the push stay one
  command whatever the caller intends.

Every case drives a **fixed** ``now`` through :func:`run`'s keyword seam — gotcha
#44: a test anchor that reads the clock is a test that branches on the clock. The
one test that reads the real clock asserts exit 0 at whatever minute it runs,
which IS the retirement and is true at every minute of the day.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "push_window_guard.py"

# 1 is the code the clock can no longer produce — kept named so the assertions
# that forbid it read as a forbidden value rather than a bare literal.
PASS, REFUSE, USAGE = 0, 1, 2


def _module():
    """Import the script by path — it is not on any package path."""
    spec = importlib.util.spec_from_file_location("push_window_guard", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    # Registered BEFORE exec. This mattered when the module defined a dataclass
    # (`from __future__ import annotations` stringifies its fields, and
    # `@dataclass` resolves them through `sys.modules[cls.__module__]`, which
    # raises if the module is not there yet). The dataclass went with the band;
    # the registration stays so re-adding any annotated class cannot resurrect a
    # failure whose cause lives in this file rather than in the script.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


guard = _module()


def _at(minute: int, second: int = 0) -> datetime:
    """A fixed UTC instant at ``minute`` past a fixed hour. Never the clock."""
    return datetime(2026, 9, 10, 23, minute, second, tzinfo=timezone.utc)


# ── the retirement: structural, not switchable ────────────────────────────


def test_a_releasing_push_is_dispatched_at_every_minute_of_the_hour(no_exec):
    """The sweep that replaces the band sweep, and the one that matters now.

    The retired band refused :51 through :31 — 41 of 60 minutes, every hour, on a
    desk that merges hourly. Samples would let an edge survive, so this walks all
    60 and requires a dispatch at each. ``--before/--after`` is deliberately
    omitted so every iteration takes the *assume a release* branch: that is the
    branch the band used to gate, and a no-release range would pass this test
    even with the window fully restored.
    """
    for minute in range(60):
        no_exec.clear()
        with pytest.raises(Execed):
            guard.run(
                ["exec", "--repo", str(REPO), "--", "git", "push", "origin", "master"],
                now=_at(minute),
            )
        assert no_exec == [("git", ["git", "push", "origin", "master"])], (
            f"a releasing push was not dispatched at :{minute:02d} — the window is back"
        )


def test_nothing_it_prints_advises_a_wait(capsys):
    """#6044's defect class, keyed on what a reader sees rather than on source.

    The merge gate's crime was not refusing — it was *printing* "OUTSIDE at
    02:10Z — next window :32-:50" while the desk merged hourly, so int345 spent
    two consecutive notes telling lanes to ignore their own tool. Advice with no
    teeth still costs a wait, so the assertion is over the program's OUTPUT at
    the minutes the band used to reject, not over its source: a source scan would
    have to exempt this file's own history section and would go stale the moment
    someone reworded the refusal.
    """
    for minute in (0, 31, 51, 59):
        guard.run(["check", "--repo", str(REPO)], now=_at(minute))
        out = capsys.readouterr().out
        lowered = out.lower()
        for advice in ("refuse", "outside", "opens in", "next window", "wait"):
            assert advice not in lowered, f"at :{minute:02d} it printed {advice!r}:\n{out}"
        # ... and it is not silent about why it did not stop you.
        assert "RETIRED" in out, out


def test_the_band_symbols_are_gone_rather_than_left_for_a_flag_to_restore():
    """A band behind a switch is a band an old notice talks someone into flipping.

    Named one by one: a survivor would be the thing a later reader rebuilds the
    refusal from, and ``hasattr`` over a list is the only form that names which.
    """
    for symbol in (
        "window_bounds",
        "window_verdict",
        "Verdict",
        "REBUILD_START_MIN",
        "REBUILD_DURATION_MIN",
        "MIN_DEPLOY_LAG_MIN",
        "MAX_DEPLOY_LAG_MIN",
        "CLOSE_MARGIN_MIN",
    ):
        assert not hasattr(guard, symbol), f"{symbol} survived the retirement"


def test_the_retirement_note_says_when_and_why_and_names_the_replacement_app():
    """Dated and mechanised, so the next reader can check it instead of trusting it.

    A bare "retired" leaves nothing to verify against; the date lets a reader find
    the coordinator's note, and ``bainluck-heavy`` names the fact that must be
    re-measured (a dyno census) before anyone restores the band.
    """
    note = guard.WINDOW_RETIRED_NOTE
    assert "2026-09-13" in note
    assert "6044" in note
    assert "bainluck-heavy" in note
    assert "beat" in note.lower()


# ── the release question: every uncertain answer must refuse ───────────────────


@pytest.fixture
def docs_only_repo(tmp_path):
    """A real git repo with a real docs-only range, and the REAL deploy script.

    Not a mock: the whole value of the bypass is that it is the deploy path's own
    answer, so a stub here would let the two drift apart and this suite would
    still be green. Returns ``(repo_path, before, after)``.
    """
    script = tmp_path / ".github" / "scripts"
    script.mkdir(parents=True)
    (script / "heroku-release-required.sh").write_text(
        (REPO / ".github" / "scripts" / "heroku-release-required.sh").read_text()
    )

    def git(*a):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *a], capture_output=True, text=True, check=True
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.email", "t@t"), git("config", "user.name", "t")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("one\n")
    git("add", "-A"), git("commit", "-qm", "one")
    before = git("rev-parse", "HEAD")
    (tmp_path / "docs" / "a.md").write_text("two\n")
    git("add", "-A"), git("commit", "-qm", "two")
    return tmp_path, before, git("rev-parse", "HEAD")


def test_a_range_that_releases_nothing_is_not_a_release(docs_only_repo):
    repo, before, after = docs_only_repo
    required, why = guard.release_required(before, after, repo=str(repo))
    assert required is False, why


def test_a_ref_name_is_reported_whole_and_a_sha_is_abbreviated(docs_only_repo):
    """`origin/ma..origin/ma` — a truncation that reads as a guard bug, found live."""
    repo, before, after = docs_only_repo
    _, why = guard.release_required(before, after, repo=str(repo))
    assert f"{before[:9]}..{after[:9]}" in why
    assert guard._short("origin/master~1") == "origin/master~1"
    assert guard._short("HEAD") == "HEAD"
    assert guard._short("a" * 40) == "a" * 9


def test_an_empty_range_still_assumes_a_release(docs_only_repo):
    """`heroku-release-required.sh` cannot prove frontend-only from an empty diff.

    Worth pinning because it is the tempting shortcut: `--before HEAD --after HEAD`
    reads like "changes nothing" and would be a total bypass if it answered false.
    """
    repo, _, after = docs_only_repo
    required, why = guard.release_required(after, after, repo=str(repo))
    assert required is True, why


def test_missing_deploy_script_assumes_a_release(tmp_path):
    required, why = guard.release_required("a" * 40, "b" * 40, repo=str(tmp_path))
    assert required is True
    assert "not found" in why


def test_no_range_assumes_a_release():
    for before, after in [(None, None), ("abc1234", None), (None, "abc1234")]:
        required, why = guard.release_required(before, after, repo=str(REPO))
        assert required is True, (before, after)
        assert "no --before/--after" in why


def test_an_unresolvable_sha_assumes_a_release():
    """`heroku-release-required.sh` itself fails toward releasing; so must we."""
    required, why = guard.release_required(
        "0" * 40, "1" * 40, repo=str(REPO)
    )
    assert required is True, why


def test_a_garbled_answer_assumes_a_release(tmp_path, monkeypatch):
    """Anything that is not the literal string `false` is not a no."""
    script = tmp_path / ".github" / "scripts"
    script.mkdir(parents=True)
    (script / "heroku-release-required.sh").write_text("echo maybe\n")
    required, why = guard.release_required("a" * 7, "b" * 7, repo=str(tmp_path))
    assert required is True
    assert "maybe" in why


def test_a_nonzero_exit_assumes_a_release(tmp_path):
    script = tmp_path / ".github" / "scripts"
    script.mkdir(parents=True)
    (script / "heroku-release-required.sh").write_text("echo false\nexit 9\n")
    required, why = guard.release_required("a" * 7, "b" * 7, repo=str(tmp_path))
    assert required is True, why
    assert "exited 9" in why


# ── the decision, end to end through the CLI entry point ───────────────────────


class Execed(Exception):
    """Stands in for `execvp` not returning. Control really does not come back."""


@pytest.fixture
def no_exec(monkeypatch):
    """Capture what would have been exec'd. Nothing in this file ever really execs.

    The fake RAISES rather than returning, because a fake that returns would put
    the guard on a line production can never reach and make its own guard-rail
    (`unreachable: execvp does not return`) look like a bug.
    """
    calls = []

    def fake(file, args):
        calls.append((file, args))
        raise Execed()

    monkeypatch.setattr(guard.os, "execvp", fake)
    return calls


def test_the_push_is_dispatched_verbatim_at_the_minute_the_band_used_to_refuse(no_exec):
    """:03 was the deepest part of the old refusal; the command still goes through whole.

    "Verbatim" is the assertion: ``execvp`` receives the exact argv it was handed,
    so the wrapper cannot quietly add, drop or reorder a git flag.
    """
    with pytest.raises(Execed):
        guard.run(
            ["exec", "--repo", str(REPO), "--", "git", "-c", "push.default=simple",
             "push", "origin", "master"],
            now=_at(3),
        )
    assert no_exec == [
        ("git", ["git", "-c", "push.default=simple", "push", "origin", "master"])
    ]


def test_a_push_that_releases_nothing_is_dispatched_too(no_exec, docs_only_repo):
    """The no-release branch still reaches the dispatch, by its own route.

    Kept from the pre-retirement suite because it exercises the *other* label
    path: with a real docs-only range the deploy script answers "false", so this
    would still pass if that branch were broken into a refusal.
    """
    repo, before, after = docs_only_repo
    with pytest.raises(Execed):
        guard.run(
            ["exec", "--repo", str(repo), "--before", before, "--after", after,
             "--", "git", "push", "origin", "master"],
            now=_at(3),
        )
    assert no_exec == [("git", ["git", "push", "origin", "master"])]


def test_check_mode_reports_at_every_minute_without_ever_dispatching(no_exec, capsys):
    """`check` is the mode a desk runs to decide whether to wait, so it must never say wait.

    Swept rather than sampled for the same reason as the dispatch sweep, and it
    pins the second half of the mode's contract at the same time: reporting is
    all it does — no minute of the hour turns `check` into a push.
    """
    codes = {guard.run(["check", "--repo", str(REPO)], now=_at(m)) for m in range(60)}
    capsys.readouterr()
    assert codes == {PASS}, f"check returned {codes - {PASS}} — REFUSE is {REFUSE}"
    assert no_exec == []


def test_exec_without_a_command_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        guard.run(["exec", "--repo", str(REPO)], now=_at(40))
    assert exc.value.code == USAGE


# ── the hole that must stay closed ─────────────────────────────────────────────


def test_the_cli_offers_no_way_to_supply_a_time():
    """A `--now` flag would rebuild exactly the bug this guard replaces.

    The seam the tests above drive is a keyword argument on ``run``. If it ever
    becomes reachable from ``argv``, a lane under time pressure can hand the
    guard the same computed time that fooled authority/114 three times running,
    and the guard will agree with it.
    """
    for flag in ["--now", "--minute", "--utc", "--time"]:
        with pytest.raises(SystemExit) as exc:
            guard.run([ "check", flag, "23:40", "--repo", str(REPO)], now=_at(3))
        assert exc.value.code == USAGE, flag


def test_the_script_reads_its_own_clock_and_passes_at_whatever_minute_that_is():
    """The retirement, proved against the real clock rather than the seam.

    Run for real, as a desk runs it, with no time supplied anywhere. Before
    #6044 the expected exit code depended on the minute this happened to execute;
    now it is 0 at all 60, so this asserts the property directly. The stamp is
    still parsed and reported, so a failure says WHICH minute refused instead of
    just "exit 1".

    The FIRST line only. A greedy ``split("/")[-1]`` over the whole output finds
    the slash in "--before/--after" on the next line instead — which is how the
    first draft of this test failed, and it would have read as a script bug.
    """
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "check", "--repo", str(REPO)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert "clock read now:" in proc.stdout, proc.stdout + proc.stderr
    first = proc.stdout.splitlines()[0]
    stamp = first.split("  /  ")[-1].strip()
    minute = int(stamp.split(":")[1])
    assert proc.returncode == PASS, (
        f"printed {stamp} (minute :{minute:02d}) and exited {proc.returncode} — "
        f"the retired window is refusing again\n{proc.stdout}"
    )


def test_both_stamps_come_from_one_measurement(capsys):
    """Notice 24: PT and UTC, side by side, never converted by rule."""
    guard.run(["check", "--repo", str(REPO)], now=_at(40))
    out = capsys.readouterr().out
    assert "PT" in out and "23:40:00Z" in out
    assert "04:40:00pm PT" in out, out
