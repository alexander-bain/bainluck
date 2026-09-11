"""#4997 — the push-window guard, pinned on the property that makes it worth having.

The bug this guard replaces was not "someone forgot notice 29". authority/114
checked the window **three times**, got "inside" every time, and pushed 29 minutes
early — because it was computing the time by adding its own ``sleep`` durations to
the session's opening stamp instead of reading a clock. That arithmetic only ever
drifts ahead, so it can never report "outside".

So the tests that matter are not "does :40 pass". They are:

* the CLI **cannot be handed a time** (a ``--now`` flag would rebuild the hole);
* it **refuses toward safety** on every uncertain release answer;
* it **does not refuse a push that cannot collide**, because a guard that
  over-refuses the 13 frontend-only pushes a day is a guard lanes route around;
* the ``exec`` dispatch is gated on the verdict, not merely reported beside it.

Every case drives a **fixed** ``now`` through :func:`run`'s keyword seam — gotcha
#44: a test anchor that reads the clock is a test that branches on the clock. The
one test that does read the real clock asserts only self-consistency, which is
true at every minute of the day.
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

PASS, REFUSE, USAGE = 0, 1, 2


def _module():
    """Import the script by path — it is not on any package path."""
    spec = importlib.util.spec_from_file_location("push_window_guard", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    # Registered BEFORE exec: the guard's `from __future__ import annotations` makes
    # its dataclass fields strings, and `@dataclass` resolves them through
    # `sys.modules[cls.__module__]`. An unregistered module raises at import.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


guard = _module()


def _at(minute: int, second: int = 0) -> datetime:
    """A fixed UTC instant at ``minute`` past a fixed hour. Never the clock."""
    return datetime(2026, 9, 10, 23, minute, second, tzinfo=timezone.utc)


# ── the band, and where its numbers come from ──────────────────────────────────


def test_the_band_is_derived_from_the_notice_29_constants_not_typed_in():
    """:32–:50 must fall OUT of the arithmetic, so a lag change moves it.

    Pinning the literals alone would let someone edit a constant and leave the
    band stale; pinning only the derivation would let both drift together away
    from the number two other documents quote. Both, together, is the check.
    """
    opens, closes = guard.window_bounds()
    assert (opens, closes) == (32, 50)
    assert opens == (
        guard.REBUILD_START_MIN + guard.MIN_DEPLOY_LAG_MIN + guard.REBUILD_DURATION_MIN
    )
    assert closes == (
        guard.REBUILD_START_MIN + 60 - guard.MAX_DEPLOY_LAG_MIN - guard.CLOSE_MARGIN_MIN
    )


def test_moving_a_measured_constant_moves_the_band(monkeypatch):
    """The equality above is satisfied by a hardcoded 32 — this is not.

    Notice 29 tells the next lane to *re-derive when the lag changes*. That
    instruction is only true if the constants are load-bearing, so the check is
    that a changed lag actually moves the edge, in the direction it should.
    """
    monkeypatch.setattr(guard, "MIN_DEPLOY_LAG_MIN", guard.MIN_DEPLOY_LAG_MIN + 4)
    assert guard.window_bounds()[0] == 36
    monkeypatch.setattr(guard, "MAX_DEPLOY_LAG_MIN", guard.MAX_DEPLOY_LAG_MIN + 6)
    assert guard.window_bounds()[1] == 44
    monkeypatch.setattr(guard, "REBUILD_DURATION_MIN", 0)
    assert guard.window_bounds()[0] == 29


def test_every_minute_of_the_hour_is_classified_and_only_nineteen_are_inside():
    """A sweep, not samples: an off-by-one at either edge shows up as a count."""
    inside = [m for m in range(60) if guard.window_verdict(_at(m)).inside]
    assert inside == list(range(32, 51))
    assert len(inside) == 19


@pytest.mark.parametrize(
    "minute,expected",
    [(31, False), (32, True), (50, True), (51, False)],
)
def test_both_edges_are_inclusive(minute, expected):
    assert guard.window_verdict(_at(minute)).inside is expected


def test_the_wait_wraps_the_hour_rather_than_going_negative():
    """:51 must be told to wait 41 minutes, not -19."""
    assert guard.window_verdict(_at(51)).minutes_to_open == 41
    assert guard.window_verdict(_at(0)).minutes_to_open == 32
    assert guard.window_verdict(_at(31)).minutes_to_open == 1
    assert all(guard.window_verdict(_at(m)).minutes_to_open >= 0 for m in range(60))


def test_seconds_never_move_a_minute_across_an_edge():
    """:50:59 is still inside; the band is minutes past the hour, as notice 29 writes it."""
    assert guard.window_verdict(_at(50, 59)).inside is True
    assert guard.window_verdict(_at(31, 59)).inside is False


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


def test_outside_the_window_a_releasing_push_is_refused_and_nothing_is_dispatched(no_exec):
    code = guard.run(
        ["exec", "--repo", str(REPO), "--", "git", "push", "origin", "master"],
        now=_at(3),
    )
    assert code == REFUSE
    assert no_exec == [], "a refused push must not dispatch anything"


def test_inside_the_window_the_push_is_dispatched_verbatim(no_exec):
    with pytest.raises(Execed):
        guard.run(
            ["exec", "--repo", str(REPO), "--", "git", "push", "origin", "master"],
            now=_at(40),
        )
    assert no_exec == [("git", ["git", "push", "origin", "master"])]


def test_a_push_that_releases_nothing_passes_at_the_worst_minute_of_the_hour(
    no_exec, docs_only_repo
):
    """The over-refusal failure mode: 13 frontend-only pushes a day must not wait."""
    repo, before, after = docs_only_repo
    with pytest.raises(Execed):
        guard.run(
            ["exec", "--repo", str(repo), "--before", before, "--after", after,
             "--", "git", "push", "origin", "master"],
            now=_at(3),
        )
    assert no_exec == [("git", ["git", "push", "origin", "master"])]


def test_check_mode_reports_without_dispatching(no_exec):
    assert guard.run(["check", "--repo", str(REPO)], now=_at(40)) == PASS
    assert guard.run(["check", "--repo", str(REPO)], now=_at(3)) == REFUSE
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


def test_the_script_reads_its_own_clock_when_none_is_given():
    """Self-consistency, so this arm is true at every minute of the day.

    Run for real as a lane runs it, and require the verdict it prints to agree
    with the band evaluated at the timestamp it printed. This is the only test
    here that touches the real clock, and it asserts no particular time.
    """
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "check", "--repo", str(REPO)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert "clock read now:" in proc.stdout, proc.stdout + proc.stderr
    # The FIRST line only. A greedy `split("/")[-1]` over the whole output finds
    # the slash in "--before/--after" on the next line instead — which is how the
    # first draft of this test failed, and it would have read as a guard bug.
    first = proc.stdout.splitlines()[0]
    stamp = first.split("  /  ")[-1].strip()
    minute = int(stamp.split(":")[1])
    expected = PASS if guard.window_verdict(_at(minute)).inside else REFUSE
    assert proc.returncode == expected, (
        f"printed {stamp} (minute {minute}) but exited {proc.returncode}\n{proc.stdout}"
    )


def test_the_refusal_says_not_to_add_a_sleep_to_the_reading(capsys):
    """The refusal has to name the bug, because the bug is what a lane does next."""
    guard.run(["check", "--repo", str(REPO)], now=_at(3))
    out = capsys.readouterr().out
    assert "REFUSE" in out
    assert "opens in 29 min" in out
    # The instruction, not just the word: a refusal that merely says "outside the
    # window" leaves the lane's next move — add 29 minutes to this reading — intact.
    assert "Do NOT compute" in out
    assert "run this command again" in out


def test_both_stamps_come_from_one_measurement(capsys):
    """Notice 24: PT and UTC, side by side, never converted by rule."""
    guard.run(["check", "--repo", str(REPO)], now=_at(40))
    out = capsys.readouterr().out
    assert "PT" in out and "23:40:00Z" in out
    assert "04:40:00pm PT" in out, out
