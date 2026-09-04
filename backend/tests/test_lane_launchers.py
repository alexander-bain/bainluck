"""Guard tests for the lane launcher scripts (integrator/106, 2026-09-03).

WHAT REGRESSED, AND WHY THESE TESTS EXIST
-----------------------------------------
`start-lanes.sh` and `lanes-supervisor.sh` each carried their own hand-written
copy of the lane list. They drifted: start-lanes opened SIX windows, the
supervisor knew SEVEN lanes, and NINE lanes actually existed. `lane1b`,
`authority` and `native` were in neither or only one, so a machine that rebooted
came back missing lanes and nothing said so. That class of bug is invisible to
every other test in this repo because it lives entirely in shell.

The fix is one list (`lanes.conf`) sourced by both scripts. The tests here drive
each script against a SYNTHETIC lanes.conf and assert it opens/relaunches exactly
what that conf describes — so a launcher that ignores a lane fails no matter what
the real conf happens to say, and the tests run identically on Alex's laptop and
in CI, where no lane is running and no worktree exists.

Second thing guarded: `lane-runner.sh` self-restock. A lane whose inbox empties
now writes its own next directive instead of waiting for a human (measured 9/3:
`live` idle 3h, `latency` idle 1.5h). BOTH arms are asserted — that it does
restock an empty lane, and that each of the guards (queued work, .running, an
already-pending RESTOCK, no program file, the minimum interval) actually blocks
it. A restock test that only covered the happy path would let the runner race a
live session into a duplicate directive.

Every script is driven through its own `--dry-run`, so nothing here opens a
Terminal window, kills a process, or writes into the live handoff tree.
"""

import os
import re
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CONF = REPO / "lanes.conf"
START = REPO / "start-lanes.sh"
SUPERVISOR = REPO / "lanes-supervisor.sh"
RUNNER = REPO / "lane-runner.sh"
LANE4 = REPO / "lane4-runner.sh"

# The lane roster is a property of Alex's machine, not of the repo (worktrees and
# `.claude/` are untracked). Tests that assert against the REAL conf are skipped
# where those do not exist; the mechanism tests below are synthetic and always run.
#
# HOME_REPO, not REPO: this file is also checked out into throwaway worktrees, and
# the handoff tree + lane worktrees only ever live under ~/bainluck. Anchoring the
# machine-scoped assertions on `REPO` made them fail in any worktree — a false red
# that says nothing about the launchers.
HOME_REPO = Path.home() / "bainluck"
ON_LANE_MACHINE = (Path.home() / "bainluck-dev").is_dir() and (HOME_REPO / ".claude").is_dir()
needs_machine = pytest.mark.skipif(
    not ON_LANE_MACHINE, reason="lane worktrees only exist on the lane machine"
)


def run(script, *args, env=None):
    """Run a launcher, returning (rc, stdout+stderr).

    Never pipes the script into anything (gotcha #54): the exit code is captured
    and returned so callers assert on its VALUE, not merely on output text.
    """
    full = dict(os.environ)
    full.update(env or {})
    p = subprocess.run(
        ["bash", str(script), *args],
        capture_output=True, text=True, env=full, cwd=str(REPO), timeout=120,
    )
    return p.returncode, p.stdout + p.stderr


def source_conf(expr, conf=CONF):
    p = subprocess.run(
        ["bash", "-c", f'. "{conf}"; {expr}'], capture_output=True, text=True, timeout=30
    )
    assert p.returncode == 0, f"{conf} is not sourceable: {p.stderr}"
    return p.stdout


def real_lanes():
    out = source_conf('for L in $LANES_ALL; do echo "$L $(lane_dir "$L")"; done')
    return [tuple(line.split(None, 1)) for line in out.strip().splitlines()]


def write_conf(tmp_path, lanes, graders=2, runner=None, lane4=None):
    """A synthetic lanes.conf. `lanes` maps lane name -> worktree dir."""
    conf = tmp_path / "lanes.conf"
    arms = "".join(f'    {n}) echo "{d}" ;;\n' for n, d in lanes.items())
    conf.write_text(
        f'LANES_ALL="{" ".join(lanes)}"\n'
        f"lane_dir () {{\n  case \"$1\" in\n{arms}    *) echo /nonexistent ;;\n  esac\n}}\n"
        f'LANE_RUNNER="{runner or RUNNER}"\n'
        f"LANE4_GRADERS={graders}\n"
        f'LANE4_RUNNER="{lane4 or LANE4}"\n'
    )
    return conf


# ---------------------------------------------------------------- syntax ----


@pytest.mark.parametrize("script", [CONF, START, SUPERVISOR, RUNNER, LANE4])
def test_launcher_scripts_parse(script):
    """A launcher with a syntax error fails at reboot, when nobody is watching."""
    p = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert p.returncode == 0, f"{script.name} does not parse:\n{p.stderr}"


# ------------------------------------------------------- one shared list ----


@pytest.mark.parametrize("script", [START, SUPERVISOR])
def test_launchers_hardcode_no_lane_list(script):
    """Neither launcher may carry its own copy — that is exactly how they drifted.

    The specific fossil this catches is `launch "$R $HOME/bainluck integrator lane1"`,
    which paired two lanes in one runner long after lane1 got its own worktree,
    and which the supervisor never reproduced.
    """
    text = script.read_text()
    # Whole-line comments are stripped first: these scripts deliberately QUOTE the
    # removed `$HOME/bainluck integrator lane1` line in a comment explaining why it
    # went, and a scan that cannot tell prose from code would force that history
    # to be deleted to stay green.
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    assert "lanes.conf" in code, f"{script.name} does not source lanes.conf"
    assert "bainluck-dev/" not in code, (
        f"{script.name} hardcodes a worktree path; the mapping belongs in lanes.conf"
    )
    assert "integrator lane1" not in code, (
        f"{script.name} still pairs integrator+lane1 in one runner — stale since "
        "lane1 got its own worktree (Alex, 2026-09-03)"
    )


def test_lanes_conf_names_the_nine_lanes_and_two_graders():
    """The roster Alex asked for on 9/3, and the grader count the bus is written for."""
    names = [lane for lane, _ in real_lanes()]
    for expected in (
        "integrator", "lane1", "lane1b", "ux", "latency",
        "calibration", "live", "authority", "native",
    ):
        assert expected in names, f"lanes.conf is missing lane '{expected}'"
    assert int(source_conf('printf %s "$LANE4_GRADERS"')) >= 2, (
        "the cert bus runs two graders (D44); one is a half-rate bus that looks healthy"
    )


@needs_machine
def test_every_real_lane_has_a_worktree_and_an_inbox():
    """A lane the launchers will start must actually be startable on this machine."""
    for lane, wt in real_lanes():
        assert Path(wt).is_dir(), f"lane '{lane}': no worktree at {wt}"
        inbox = HOME_REPO / ".claude" / "handoff" / "runner-inbox" / lane
        assert inbox.is_dir(), f"lane '{lane}': no inbox at {inbox}"


# --------------------------------------------------------- start-lanes.sh ----


def test_start_lanes_opens_one_window_per_lane_plus_every_grader(tmp_path):
    """The regression itself: exactly one window per lane in the conf, plus N graders."""
    lanes = {n: str(tmp_path) for n in ("integrator", "lane1", "lane1b", "extra")}
    conf = write_conf(tmp_path, lanes, graders=2)
    rc, out = run(START, "--dry-run", env={"LANES_CONF": str(conf)})
    assert rc == 0, out

    launched = re.findall(r"would open Terminal window: (.+)$", out, re.M)
    expected = [f"{RUNNER} {tmp_path} {n}" for n in lanes] + [str(LANE4)] * 2
    assert launched == expected, (
        "start-lanes.sh does not open exactly the windows lanes.conf describes.\n"
        "expected:\n  " + "\n  ".join(expected) + "\ngot:\n  " + "\n  ".join(launched)
    )
    assert "SKIPPED lane" not in out


def test_start_lanes_gives_each_lane_its_own_runner(tmp_path):
    """One lane per window. The old line served two inboxes from one runner, so
    lane1 waited on the integrator's sessions for no reason."""
    conf = write_conf(tmp_path, {"a": str(tmp_path), "b": str(tmp_path)}, graders=0)
    rc, out = run(START, "--dry-run", env={"LANES_CONF": str(conf)})
    assert rc == 0, out
    for line in re.findall(r"would open Terminal window: (.+)$", out, re.M):
        assert len(line.split()) == 3, f"window serves more than one lane: {line}"


@needs_machine
def test_start_lanes_covers_the_real_roster_with_no_skips():
    """On the lane machine, every real lane opens: no worktree is missing."""
    rc, out = run(START, "--dry-run", env={"LANES_CONF": str(CONF)})
    assert rc == 0, out
    launched = re.findall(r"would open Terminal window: (.+)$", out, re.M)
    # The runner and grader paths come from the CONF the script actually sources,
    # not from this checkout — in a worktree those differ, and comparing against
    # the checkout's own paths is a false red about nothing.
    runner = source_conf('printf %s "$LANE_RUNNER"')
    lane4 = source_conf('printf %s "$LANE4_RUNNER"')
    expected = [f"{runner} {wt} {lane}" for lane, wt in real_lanes()]
    expected += [lane4] * int(source_conf('printf %s "$LANE4_GRADERS"'))
    assert launched == expected
    assert "SKIPPED lane" not in out, out


def test_start_lanes_dry_run_does_not_reap():
    """--dry-run must never kill a process; the orphan reap is the destructive step."""
    rc, out = run(START, "--dry-run", env={"LANES_CONF": str(CONF)})
    assert rc == 0, out
    assert "skipping orphan reap" in out
    assert "Reaping orphaned" not in out


@pytest.mark.parametrize("script", [START, SUPERVISOR])
def test_launchers_find_their_conf_next_to_themselves(script, tmp_path):
    """A checkout must be self-contained: no LANES_CONF, no ~/bainluck.

    Caught by CI, which checks out to /home/runner/work/bainluck and has no home
    directory copy — the launchers looked only under $HOME and died with
    "missing /home/runner/bainluck/lanes.conf". The same hole would hit any
    throwaway worktree. lanes.conf is a tracked sibling; find it there first.
    """
    rc, out = run(script, "--dry-run", env={"HOME": str(tmp_path), "LANES_CONF": ""})
    assert rc == 0, out
    assert "missing" not in out, out


def test_start_lanes_is_loud_about_a_missing_worktree(tmp_path):
    """A lane with no worktree is reported, never silently dropped.

    An unopened window looks exactly like a lane with no work — which is how a
    lane goes missing for hours without anyone noticing.
    """
    conf = write_conf(tmp_path, {"ghostlane": str(tmp_path / "nope")}, graders=0)
    rc, out = run(START, "--dry-run", env={"LANES_CONF": str(conf)})
    assert rc == 0, out
    assert "SKIPPED lane 'ghostlane'" in out
    assert "would open Terminal window" not in out, "a skipped lane was launched anyway"


# ----------------------------------------------------- lanes-supervisor.sh ----


def test_supervisor_checks_every_lane_in_the_conf(tmp_path):
    """The regression: it knew seven of nine.

    Every lane is given a directory but no runner, so each must be reported
    missing. A lane the supervisor does not iterate simply never appears.
    """
    names = [lane for lane, _ in real_lanes()] + ["a-brand-new-lane"]
    conf = write_conf(tmp_path, {n: str(tmp_path) for n in names}, graders=0)
    rc, out = run(SUPERVISOR, "--dry-run", env={"LANES_CONF": str(conf)})
    assert rc == 0, out
    unchecked = [n for n in names if f"lane '{n}' has no runner" not in out]
    assert not unchecked, f"listed in lanes.conf but never checked: {unchecked}"


def test_supervisor_leaves_a_live_lane_alone(tmp_path):
    """Control arm — and the one that catches a blind matcher.

    A real process is started with exactly the argv the supervisor launches, and
    the supervisor must NOT relaunch it. Without this arm, a supervisor that
    relaunched every lane on every pass would sail through the test above.

    It also pins the pgrep bug: `pgrep -f` EXCLUDES ITS OWN ANCESTORS, so a
    supervisor started from a lane's Terminal window could not see that lane's
    runner and opened a duplicate window every five minutes, forever. Observed
    9/3 the first time --dry-run was run from the integrator window.
    """
    fake = tmp_path / "fake-runner.sh"
    fake.write_text("#!/bin/bash\nsleep 30\n")
    fake.chmod(0o755)
    conf = write_conf(tmp_path, {"demo": str(tmp_path)}, graders=0, runner=fake)

    proc = subprocess.Popen(["/bin/bash", str(fake), str(tmp_path), "demo"])
    try:
        time.sleep(0.5)
        rc, out = run(SUPERVISOR, "--dry-run", env={"LANES_CONF": str(conf)})
    finally:
        proc.kill()
        proc.wait()
    assert rc == 0, out
    assert "would relaunch" not in out, f"supervisor cannot see a live runner:\n{out}"


def test_supervisor_relaunches_a_dead_lane_and_the_grader_deficit(tmp_path):
    """Treatment arm: a lane with no runner, and a grader shortfall, are both caught —
    and the shortfall relaunches the DEFICIT, not a fixed number."""
    missing = tmp_path / "no-such-grader.sh"
    conf = write_conf(tmp_path, {"ghostlane": str(tmp_path)}, graders=3, lane4=missing)
    rc, out = run(SUPERVISOR, "--dry-run", env={"LANES_CONF": str(conf)})
    assert rc == 0, out
    assert "lane 'ghostlane' has no runner" in out
    assert f"would relaunch: {RUNNER} {tmp_path} ghostlane" in out
    assert "lane4 graders: 0 of 3" in out
    assert out.count(f"would relaunch: {missing}") == 3


def test_supervisor_counts_graders_and_not_mere_mentions(tmp_path):
    """A WHOLE-LINE match, not a substring one.

    Any process whose argv merely MENTIONS the grader path — an editor, another
    agent's shell, a heredoc — used to be counted as a live grader. Counting too
    HIGH is the unsafe direction: a dead grader is then never relaunched and the
    cert bus quietly runs at half rate. Measured while building this: a substring
    count read "3 of 5" while exactly two graders were running.

    Both arms, against the same decoy-free tree:
      - a process that merely names the path  -> still counted MISSING
      - a process actually running it         -> counted ALIVE
    """
    grader = tmp_path / "grader.sh"
    grader.write_text("#!/bin/bash\nsleep 30\n")
    grader.chmod(0o755)
    conf = write_conf(tmp_path, {}, graders=1, lane4=grader)

    decoy = subprocess.Popen(["sleep", "30", str(grader)])   # mentions it, is not it
    try:
        time.sleep(0.5)
        rc, out = run(SUPERVISOR, "--dry-run", env={"LANES_CONF": str(conf)})
    finally:
        decoy.kill()
        decoy.wait()
    assert rc == 0, out
    assert "lane4 graders: 0 of 1" in out, f"a mere mention was counted as a grader:\n{out}"

    real = subprocess.Popen(["/bin/bash", str(grader)])
    try:
        time.sleep(0.5)
        rc, out = run(SUPERVISOR, "--dry-run", env={"LANES_CONF": str(conf)})
    finally:
        real.kill()
        real.wait()
    assert rc == 0, out
    assert "lane4 graders:" not in out, f"a live grader was not counted:\n{out}"


# --------------------------------------------- lane-runner.sh self-restock ----


def _handoff(tmp_path, lane="demo", program="PROGRAM-DEMO.md"):
    """A scratch handoff tree with one lane and (optionally) a program file."""
    handoff = tmp_path / "handoff"
    (handoff / "runner-inbox" / lane).mkdir(parents=True)
    if program:
        (handoff / program).write_text("# demo program file\n")
        (handoff / "lane-program-map.txt").write_text(f"{lane} {program}\n")
    return handoff


def _restock(handoff, lane="demo", **env):
    e = {"LANE_HANDOFF": str(handoff)}
    e.update(env)
    return run(RUNNER, "--dry-run", str(REPO), lane, env=e)


def test_restock_fires_on_an_empty_inbox(tmp_path):
    """The ship: an empty lane stages its own next directive instead of idling."""
    rc, out = _restock(_handoff(tmp_path))
    assert rc == 0, out
    assert "WOULD WRITE" in out, out
    assert "Your inbox is empty." in out
    assert "PROGRAM-DEMO.md" in out
    assert "STANDING-NOTICES.md" in out
    assert "Do not end with a question." in out


def test_restock_dry_run_writes_nothing(tmp_path):
    """The dry-run the directive asked for: it prints, it does not stage."""
    handoff = _handoff(tmp_path)
    rc, out = _restock(handoff)
    assert rc == 0, out
    staged = list((handoff / "runner-inbox" / "demo").iterdir())
    assert staged == [], f"dry-run wrote {staged}"


def test_restock_blocked_by_queued_work(tmp_path):
    """Guard 1a: a lane with a directive waiting is not idle."""
    handoff = _handoff(tmp_path)
    (handoff / "runner-inbox" / "demo" / "001-real-work.md").write_text("do a thing\n")
    rc, out = _restock(handoff)
    assert rc == 0, out
    assert "inbox has queued work" in out
    assert "WOULD WRITE" not in out


def test_restock_blocked_by_a_running_directive(tmp_path):
    """Guard 1b, the one that matters most: never race a live session.

    A duplicate runner window holding a session open would otherwise get a
    restock stacked on top of the work it is mid-way through.
    """
    handoff = _handoff(tmp_path)
    (handoff / "runner-inbox" / "demo" / "001-in-flight.md.running").write_text("busy\n")
    rc, out = _restock(handoff)
    assert rc == 0, out
    assert ".running" in out and "no restock" in out
    assert "WOULD WRITE" not in out


def test_restock_never_stacks_two(tmp_path):
    """Guard 2: at most one RESTOCK pending per lane."""
    handoff = _handoff(tmp_path)
    (handoff / "runner-inbox" / "demo" / "RESTOCK-20260903-000000.md").write_text("x\n")
    rc, out = _restock(handoff)
    assert rc == 0, out
    assert "WOULD WRITE" not in out


def test_restock_refuses_a_lane_with_no_program_file(tmp_path):
    """Guard 3: never hand a lane a directive citing a file that is not there.

    The lane is left idle ON PURPOSE, and the log names the one-line fix rather
    than leaving a silent gap.
    """
    rc, out = _restock(_handoff(tmp_path, program=None))
    assert rc == 0, out
    assert "NO PROGRAM FILE" in out
    assert "lane-program-map.txt" in out
    assert "WOULD WRITE" not in out


def test_restock_map_entry_pointing_at_a_missing_file_fails_closed(tmp_path):
    """A stale map line must not produce a directive citing a ghost file."""
    handoff = _handoff(tmp_path, program=None)
    (handoff / "lane-program-map.txt").write_text("demo PROGRAM-GONE.md\n")
    rc, out = _restock(handoff)
    assert rc == 0, out
    assert "NO PROGRAM FILE" in out
    assert "WOULD WRITE" not in out


def test_restock_default_program_name_is_used_when_unmapped(tmp_path):
    """With no map line, a lane falls back to PROGRAM-<LANE>.md if it exists."""
    handoff = tmp_path / "handoff"
    (handoff / "runner-inbox" / "demo").mkdir(parents=True)
    (handoff / "PROGRAM-DEMO.md").write_text("# fallback\n")
    rc, out = _restock(handoff)
    assert rc == 0, out
    assert "WOULD WRITE" in out
    assert "PROGRAM-DEMO.md" in out


def test_restock_interval_floor_blocks_a_spin(tmp_path):
    """Guard 4: a directive that fails on contact must not spin the lane.

    Without the floor: restock -> session fails 3x -> quarantined -> inbox empty
    -> restock, at session speed, forever.
    """
    handoff = _handoff(tmp_path)
    (handoff / "runner-inbox" / "demo" / ".last-restock").write_text(str(int(time.time())))
    rc, out = _restock(handoff)
    assert rc == 0, out
    assert "floor" in out and "holding" in out
    assert "WOULD WRITE" not in out

    # Control: the same tree with the floor at 0 DOES restock, so the block above
    # is the floor doing its job and not some other guard tripping first.
    rc, out = _restock(handoff, LANE_RESTOCK_MIN_INTERVAL="0")
    assert rc == 0, out
    assert "WOULD WRITE" in out


def test_restock_actually_writes_the_directive(tmp_path):
    """The WRITE path, not the rehearsal.

    --dry-run only ever proves the branch that writes nothing. This runs the real
    one: the file must land in the inbox under a name the take-loop's glob will
    pick up (`RESTOCK-<stamp>.md`), and the interval stamp must be recorded — if
    it were not, the floor could never bite and a failing directive could spin
    the lane at session speed.
    """
    handoff = _handoff(tmp_path)
    inbox = handoff / "runner-inbox" / "demo"
    rc, out = run(RUNNER, "--restock-once", str(REPO), "demo",
                  env={"LANE_HANDOFF": str(handoff)})
    assert rc == 0, out

    written = sorted(p.name for p in inbox.glob("RESTOCK-*.md"))
    assert len(written) == 1, f"expected one RESTOCK, got {written}"
    body = (inbox / written[0]).read_text()
    assert "Your inbox is empty." in body
    assert "PROGRAM-DEMO.md" in body
    assert "Do not end with a question." in body
    assert (inbox / ".last-restock").exists(), "no interval stamp — the floor can never bite"

    # And it does not write a second one on the next pass. Both the "one pending"
    # guard and the interval floor should hold here; either is enough.
    rc, out = run(RUNNER, "--restock-once", str(REPO), "demo",
                  env={"LANE_HANDOFF": str(handoff)})
    assert rc == 1, f"a second restock was written:\n{out}"
    assert len(list(inbox.glob("RESTOCK-*.md"))) == 1


def test_restock_dry_run_does_not_requeue_running_directives(tmp_path):
    """A rehearsal must not touch a live lane's in-flight work.

    Crash recovery renames `*.md.running` back to `*.md` at startup. Under
    --dry-run that would re-queue a directive a real runner is mid-session on.
    """
    handoff = _handoff(tmp_path)
    running = handoff / "runner-inbox" / "demo" / "001-in-flight.md.running"
    running.write_text("busy\n")
    rc, out = _restock(handoff)
    assert rc == 0, out
    assert running.exists(), "dry-run re-queued an in-flight directive"
    assert not (handoff / "runner-inbox" / "demo" / "001-in-flight.md").exists()
