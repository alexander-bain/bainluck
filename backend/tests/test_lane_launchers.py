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
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CONF = REPO / "lanes.conf"
START = REPO / "start-lanes.sh"
SUPERVISOR = REPO / "lanes-supervisor.sh"
RUNNER = REPO / "lane-runner.sh"
LANE4 = REPO / "lane4-runner.sh"
BUS = REPO / "bus-runner.sh"

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


def write_conf(
    tmp_path, lanes, graders=2, runner=None, lane4=None, bus=None, supervisor=None
):
    """A synthetic lanes.conf. `lanes` maps lane name -> worktree dir.

    `bus` and `supervisor` default to None = the variable unset, which is the
    older-checkout case: the launchers must still bring up every lane and grader
    without either.
    """
    conf = tmp_path / "lanes.conf"
    arms = "".join(f'    {n}) echo "{d}" ;;\n' for n, d in lanes.items())
    conf.write_text(
        f'LANES_ALL="{" ".join(lanes)}"\n'
        f"lane_dir () {{\n  case \"$1\" in\n{arms}    *) echo /nonexistent ;;\n  esac\n}}\n"
        f'LANE_RUNNER="{runner or RUNNER}"\n'
        f"LANE4_GRADERS={graders}\n"
        f'LANE4_RUNNER="{lane4 or LANE4}"\n'
        + (f'BUS_RUNNER="{bus}"\n' if bus else "")
        + (f'SUPERVISOR="{supervisor}"\n' if supervisor else "")
    )
    return conf


def stub_pgrep(tmp_path, found):
    """A directory to prepend to PATH whose `pgrep` reports found / not-found.

    The supervisor branch in `start-lanes.sh` asks `pgrep` whether one is
    already running, and on a lane machine the honest answer is always "yes" —
    so the arm that actually LAUNCHES could never be exercised on the machine
    that runs it. Shadowing `pgrep` on PATH drives the real branch either way
    without a test hook in the script, and without killing the live supervisor.

    Only `pgrep` is shadowed; every other command still resolves normally.
    `--dry-run` skips the reap block, so this is the script's only `pgrep` call.
    """
    d = tmp_path / ("pathstub-found" if found else "pathstub-missing")
    d.mkdir()
    p = d / "pgrep"
    p.write_text("#!/bin/bash\n" + ("echo 424242\nexit 0\n" if found else "exit 1\n"))
    p.chmod(0o755)
    return d


# ---------------------------------------------------------------- syntax ----


@pytest.mark.parametrize("script", [CONF, START, SUPERVISOR, RUNNER, LANE4, BUS])
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
    bus = source_conf('printf %s "${BUS_RUNNER:-}"')
    if bus:
        expected.append(bus)
    assert launched == expected
    assert "SKIPPED lane" not in out, out
    assert "SKIPPED the measurement bus" not in out, out


# ------------------------------------------------- the measurement bus ----
#
# integrator/135, 2026-09-04. The cert graders have been headless since
# lane4-runner.sh; the MEASUREMENT bus never was — it ran only when Alex pasted a
# prompt, and the recurring M-R set duly banked buckets 04, 13 and 17 on 9/4 with
# nothing in between. `bus-runner.sh` is its runner. These tests pin the two
# things that make it safe to leave running over a weekend: it opens exactly ONE
# window, and a checkout without it still starts everything else.


def test_start_lanes_opens_the_measurement_bus_when_the_conf_names_it(tmp_path):
    conf = write_conf(tmp_path, {"a": str(tmp_path)}, graders=0, bus=BUS)
    rc, out = run(START, "--dry-run", env={"LANES_CONF": str(conf)})
    assert rc == 0, out
    launched = re.findall(r"would open Terminal window: (.+)$", out, re.M)
    assert launched.count(str(BUS)) == 1, (
        "the measurement bus must open exactly one window — two would race on the "
        "same bucket's artifacts, and unlike the two cert graders (D44) there is no "
        f"tie-break rule for that.\ngot: {launched}"
    )


def test_start_lanes_survives_a_checkout_with_no_bus_runner(tmp_path):
    """An older checkout must still bring up every lane and grader.

    The bus is additive; a missing script is a skipped window with a reason, never
    a launcher that dies before it reaches the lanes.
    """
    conf = write_conf(tmp_path, {"a": str(tmp_path), "b": str(tmp_path)}, graders=2,
                      bus=tmp_path / "nope.sh")
    rc, out = run(START, "--dry-run", env={"LANES_CONF": str(conf)})
    assert rc == 0, out
    launched = re.findall(r"would open Terminal window: (.+)$", out, re.M)
    assert len(launched) == 4, f"lanes/graders did not all launch: {launched}"
    assert "SKIPPED the measurement bus" in out, (
        "a missing bus script must say so — a silently absent bus is exactly the "
        "failure the M-R record already had"
    )


def test_supervisor_relaunches_a_dead_measurement_bus(tmp_path):
    """It matters more over a weekend than on a weekday: nobody is watching.

    A bus that dies on Saturday and is not relaunched is a hole in the record
    until Monday, which is the whole thing integrator/135 was written to close.
    """
    conf = write_conf(tmp_path, {}, graders=0, bus=BUS)
    rc, out = run(SUPERVISOR, "--dry-run", env={"LANES_CONF": str(conf)})
    assert rc == 0, out
    assert str(BUS) in re.findall(r"would relaunch: (.+)$", out, re.M), (
        f"the supervisor does not keep the measurement bus alive:\n{out}"
    )


def test_supervisor_survives_a_checkout_with_no_bus_runner(tmp_path):
    conf = write_conf(tmp_path, {}, graders=0, bus=tmp_path / "nope.sh")
    rc, out = run(SUPERVISOR, "--dry-run", env={"LANES_CONF": str(conf)})
    assert rc == 0, out
    assert "nope.sh" not in out, "supervisor tries to relaunch a bus that does not exist"


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


def test_dry_run_leaves_the_handoff_tree_byte_identical(tmp_path):
    """A rehearsal must not write ANYWHERE in the handoff tree.

    CERT-874 follow-up: --dry-run claimed a process-group ownership record under
    `runner-pids/` and ran that directory's garbage collector. Both are real
    writes, and the GC DELETES — so a rehearsal could disown a live runner's
    sessions and hand them to the orphan reaper. It also created the log dir and
    any missing inbox. A rehearsal is only safe to point at production state if
    it leaves that state untouched.
    """
    handoff = _handoff(tmp_path)

    def snapshot():
        return {
            str(p.relative_to(handoff)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(handoff.rglob("*")) if p.is_file()
        }

    before = snapshot()
    rc, out = _restock(handoff)
    assert rc == 0, out
    assert snapshot() == before, "dry-run modified the handoff tree"
    assert not (handoff / "runner-pids").exists(), "dry-run claimed a pgid ownership record"
    assert not (handoff / "runner-logs").exists(), "dry-run created a log directory"


def test_rescue_runs_its_tests_in_the_rebased_worktree(monkeypatch, tmp_path):
    """The pytest a rescue runs must execute in the REBASED tree, not the checkout.

    CERT-874 BLOCK: `do_rescue` rebased into a throwaway worktree and then ran
    pytest with `cwd=REPO/backend`. That is the worst shape a gate can take — it
    tests a tree the rescue did not produce, sees green, moves the branch, and
    reports an UNTESTED rebase as verified. The shared checkout also carries other
    lanes' uncommitted work, so its result is not even reproducible.

    Driven with the real subprocess boundary mocked, so nothing is rebased here.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("stranded_sweep", REPO / "tools" / "stranded-sweep.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    calls = []

    def fake_git(*args, check=True):
        calls.append(("git", args))
        return 0, "", ""

    def fake_run(cmd, **kw):
        calls.append((tuple(cmd), kw.get("cwd")))

        class R:
            returncode = 0
            stdout = "0" * 40
            stderr = ""
        return R()

    monkeypatch.setattr(mod, "git", fake_git)
    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    rec = {"branch": "lane1/q999-demo", "ref": "origin/lane1/q999-demo", "pr": 1,
           "sha": "0" * 8, "sha_full": "0" * 40,
           "files": ["backend/app/routes/feed.py"]}
    mod.do_rescue(rec, dry=False)

    pytest_calls = [(c, cwd) for c, cwd in
                    [(c, w) for c, w in calls if isinstance(c, tuple) and c and c[0] != "git"]
                    if "pytest" in c]
    assert len(pytest_calls) == 1, f"expected one pytest invocation, got {pytest_calls}"
    cwd = pytest_calls[0][1]
    assert cwd is not None, "pytest ran with no explicit cwd — it would inherit the caller's"
    assert "stranded-sweep-" in cwd, (
        f"rescue ran its tests in {cwd}, which is not the rebased worktree — "
        "it would greenlight an untested rebase"
    )
    assert not cwd.startswith(str(REPO / "backend")), (
        f"rescue ran its tests in the shared checkout ({cwd}); that tree is not "
        "what the rebase produced and holds other lanes' uncommitted work"
    )


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


# ---------------------------------------------------------------------------
# A rescue that cannot be fetched has not rescued anything (integrator/134)
# ---------------------------------------------------------------------------
# CERT-874 -> 876 fixed WHICH TREE the rescue tests. This is the next defect in
# the same function: what it does with the tree once it is green.
#
# `do_rescue` rebased, tested, moved the LOCAL branch, and printed a
# `stage-cert.sh` line naming the new sha. It never pushed. Measured on the
# 2026-09-03 sweep: PRs #420, #2091 and #2168 all reported "rescued -> <sha>,
# focused tests green", and all three remote branches were still sitting on
# their OLD heads. The advertised shas existed in exactly one laptop's object
# store — unfetchable by CI, by the cert bus, and by any grader. That is the
# same "no readable ref" dead end this script already reports as UNRESOLVED for
# PRs whose branch was deleted, except self-inflicted and announced as success.


def _load_sweep():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "stranded_sweep", REPO / "tools" / "stranded-sweep.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _drive_rescue(monkeypatch, push_rc=0):
    """Run do_rescue with the subprocess boundary faked; return (calls, printed)."""
    mod = _load_sweep()
    calls, printed = [], []

    def fake_git(*args, check=True):
        calls.append(("git",) + args)
        return 0, "", ""

    def fake_run(cmd, **kw):
        calls.append(tuple(cmd))

        class R:
            returncode = push_rc if "push" in cmd else 0
            stdout = "a" * 40
            stderr = "! [rejected] stale info"
        return R()

    monkeypatch.setattr(mod, "git", fake_git)
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr("builtins.print", lambda *a, **k: printed.append(" ".join(map(str, a))))

    rec = {"branch": "lane1/q999-demo", "ref": "origin/lane1/q999-demo", "pr": 1,
           "sha": "0" * 8, "sha_full": "0" * 40,
           "files": ["backend/app/routes/feed.py"]}
    ok = mod.do_rescue(rec, dry=False)
    return ok, calls, printed


def test_rescue_pushes_the_branch_it_rebased(monkeypatch):
    """A green rebase must reach the remote, or the sha it advertises is a dead ref."""
    ok, calls, printed = _drive_rescue(monkeypatch)
    pushes = [c for c in calls if "push" in c]
    assert pushes, (
        "do_rescue reported a rescue without ever pushing. The new sha then lives "
        "only in the local object store: the PR head never moves and no grader, "
        "machine or CI run can fetch what the re-stage line names."
    )
    cmd = pushes[0]
    assert any(a.startswith("--force-with-lease=") for a in cmd), (
        f"rescue force-pushed without a lease: {cmd}. A branch someone else moved "
        "mid-run would be silently overwritten."
    )
    lease = next(a for a in cmd if a.startswith("--force-with-lease="))
    assert len(lease.split(":")[-1]) == 40, (
        f"lease {lease!r} does not name a full 40-char oid — git does not honour an "
        "abbreviated lease, and a lease that degrades to a plain force is worse "
        "than no lease at all"
    )
    assert ok is True


def test_rescue_reports_failure_when_the_push_is_rejected(monkeypatch):
    """The regression arm: a rejected push must NOT be announced as a rescue."""
    ok, calls, printed = _drive_rescue(monkeypatch, push_rc=1)
    assert ok is False, "a rejected push still counted as a successful rescue"
    blob = "\n".join(printed)
    assert "PUSH FAILED" in blob, f"push failure was not reported to the operator: {blob!r}"
    assert "re-stage:" not in blob, (
        "rescue printed a re-stage line for a sha that never reached the remote — "
        "the grader it points at cannot fetch it"
    )


def test_resolve_ref_falls_back_to_the_pull_head_when_the_branch_is_gone(monkeypatch):
    """A deleted branch must not be a permanent UNRESOLVED.

    Measured on #998 (`fix/887-mrbdgf0e`, branch deleted, 58d stale): the sweep
    said "run `git fetch origin` and re-run", which can never work for a branch
    that no longer exists on the remote. GitHub still serves the head under
    refs/pull/N/head, so the PR is judgeable.
    """
    mod = _load_sweep()
    seen = []

    def fake_git(*args, check=True):
        seen.append(args)
        if args[0] == "cat-file" and "refs/stranded-sweep/pr998" in args[-1]:
            return 0, "", ""
        if args[0] == "cat-file":
            return 1, "", "not a valid object name"
        if args[0] == "fetch":
            return 0, "", ""
        return 1, "", ""

    monkeypatch.setattr(mod, "git", fake_git)

    assert mod.resolve_ref("fix/887-mrbdgf0e", "4b1a5ba9" + "0" * 32, pr=998) == \
        "refs/stranded-sweep/pr998"
    assert any(a[0] == "fetch" and any("refs/pull/998/head" in x for x in a) for a in seen), (
        f"resolve_ref never tried refs/pull/998/head: {seen}"
    )


def test_resolve_ref_without_a_pr_number_still_gives_up(monkeypatch):
    """Control arm: the fallback is the LAST resort, not a way to never return None."""
    mod = _load_sweep()
    monkeypatch.setattr(mod, "git", lambda *a, check=True: (1, "", "nope"))
    assert mod.resolve_ref("gone/branch", "b" * 40) is None


# ----------------------------------------- the cross-root write grant ----
#
# integrator/135 item 2, 2026-09-04. A lane can only write handoff files in
# ~/bainluck if its worktree carries `.claude/settings.json` naming ~/bainluck in
# permissions.additionalDirectories. `--add-dir` grants READ but not WRITE, and
# settings are read at LAUNCH only — so lane-runner.sh seeds the file before it
# starts a session.
#
# THE BUG THIS GUARDS: `native` was stood up 9/3 without the file. It could not
# file anything for its whole existence — every note went to a private
# handoff-outbox/ that only a human copying by hand could deliver, and 8 had piled
# up by 9/4 including three meant for Alex. Nothing announced it: the session just
# gets EPERM and works around it. Worse, no other lane can repair it — the
# writable set is own-worktree + ~/bainluck, so even the Integrator gets EPERM on
# ~/bainluck-dev. The runner is the one process positioned to fix it.
#
# The seeding runs on the real session path only, so these drive the actual loop
# with a short timeout rather than --dry-run (which must write nothing anywhere).


def run_runner_briefly(workdir, handoff, seconds=6):
    """Start lane-runner.sh for real, let it seed, then stop it. Returns output.

    `start_new_session` is load-bearing, not tidiness: lane-runner.sh traps
    INT/TERM/HUP with `kill 0` to take its session subtree down with it, and
    `kill 0` signals the CALLER's process group. Without its own session, a
    runner started here could signal pytest itself.

    The runner never terminates on its own — seeding happens before the serve
    loop, so the only way to observe it is to start the real thing and stop it.
    --dry-run cannot stand in: it is specified to write nothing anywhere, which
    is precisely the branch that does not seed.
    """
    full = dict(os.environ)
    full["LANE_HANDOFF"] = str(handoff)
    try:
        p = subprocess.run(
            ["bash", str(RUNNER), str(workdir), "testlane"],
            capture_output=True, text=True, env=full, cwd=str(REPO),
            timeout=seconds, start_new_session=True,
        )
        return p.stdout + p.stderr
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"") + (exc.stderr or b"")
        return out.decode() if isinstance(out, bytes) else str(out)


def read_grant(workdir):
    import json
    f = Path(workdir) / ".claude" / "settings.json"
    if not f.exists():
        return None
    return json.loads(f.read_text())


def test_runner_creates_the_grant_for_a_worktree_that_has_none(tmp_path):
    """Native's exact situation: no settings file at all."""
    wt = tmp_path / "wt"; wt.mkdir()
    handoff = tmp_path / "handoff"; (handoff / "runner-inbox" / "testlane").mkdir(parents=True)
    run_runner_briefly(wt, handoff)
    data = read_grant(wt)
    assert data is not None, "lane-runner.sh did not create the grant file"
    assert str(Path.home() / "bainluck") in data["permissions"]["additionalDirectories"]


def test_runner_does_not_rewrite_a_grant_that_is_already_there(tmp_path):
    """Byte-identical, mtime untouched — a lane's settings file is not the runner's
    to reformat, and a needless rewrite invites a mid-session settings change that
    (settings being read at launch) would do nothing but look like it did."""
    wt = tmp_path / "wt"; (wt / ".claude").mkdir(parents=True)
    f = wt / ".claude" / "settings.json"
    original = '{ "permissions": { "additionalDirectories": ["%s"] } }' % (Path.home() / "bainluck")
    f.write_text(original)
    before = (f.read_text(), f.stat().st_mtime_ns)
    handoff = tmp_path / "handoff"; (handoff / "runner-inbox" / "testlane").mkdir(parents=True)
    time.sleep(1)
    run_runner_briefly(wt, handoff)
    assert (f.read_text(), f.stat().st_mtime_ns) == before, "the runner rewrote a correct grant"


def test_runner_merges_rather_than_clobbering_other_settings(tmp_path):
    """A lane may carry real settings; the grant is added beside them, never over."""
    import json
    wt = tmp_path / "wt"; (wt / ".claude").mkdir(parents=True)
    f = wt / ".claude" / "settings.json"
    f.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "model": "opus"}))
    handoff = tmp_path / "handoff"; (handoff / "runner-inbox" / "testlane").mkdir(parents=True)
    run_runner_briefly(wt, handoff)
    data = read_grant(wt)
    assert data["model"] == "opus", "clobbered an unrelated key"
    assert data["permissions"]["allow"] == ["Bash(ls)"], "clobbered an existing permission"
    assert str(Path.home() / "bainluck") in data["permissions"]["additionalDirectories"]


def test_runner_leaves_an_unparseable_settings_file_alone(tmp_path):
    """Never overwrite what we failed to read: it may be a lane's real settings
    with one bad comma. Say so and let a human fix the JSON."""
    wt = tmp_path / "wt"; (wt / ".claude").mkdir(parents=True)
    f = wt / ".claude" / "settings.json"
    f.write_text("{ this is not json")
    handoff = tmp_path / "handoff"; (handoff / "runner-inbox" / "testlane").mkdir(parents=True)
    out = run_runner_briefly(wt, handoff)
    assert f.read_text() == "{ this is not json", "clobbered a file it could not parse"
    assert "leaving it alone" in out, f"failed silently instead of saying so:\n{out}"


@needs_machine
def test_runner_does_not_write_settings_into_the_master_tree(tmp_path):
    """The integrator's workdir IS ~/bainluck. It needs the REVERSE grant, which
    lives in its own settings.local.json — seeding a settings.json there would be
    noise at best, and must never disturb what is already there."""
    handoff = tmp_path / "handoff"; (handoff / "runner-inbox" / "testlane").mkdir(parents=True)
    target = HOME_REPO / ".claude" / "settings.json"
    existed = target.exists()
    before = target.read_text() if existed else None
    run_runner_briefly(HOME_REPO, handoff)
    assert target.exists() == existed, "the runner created/removed settings.json in the master tree"
    if existed:
        assert target.read_text() == before, "the runner edited the master tree's settings.json"


@needs_machine
def test_every_lane_worktree_can_write_the_handoff_tree():
    """The end state, asserted directly against the machine: every lane the
    launchers will start carries the grant. This is the check whose absence let
    `native` run for a day unable to file a single note."""
    import json
    grant = str(HOME_REPO)
    missing = []
    for lane, wt in real_lanes():
        if Path(wt).resolve() == HOME_REPO.resolve():
            continue  # the integrator; see the test above
        f = Path(wt) / ".claude" / "settings.json"
        try:
            dirs = json.loads(f.read_text())["permissions"]["additionalDirectories"]
        except Exception:
            missing.append(lane)
            continue
        if grant not in dirs:
            missing.append(lane)
    assert not missing, (
        f"lanes that cannot write {grant}/.claude/handoff/: {missing}. Their notes will "
        "land in a private handoff-outbox/ that only a human copying by hand can deliver. "
        "lane-runner.sh seeds this at launch, so a lane listed here has not been "
        "restarted since the grant landed."
    )


# ---------------------------------------------------------------------------
# A .running marker older than a session can be is an orphan (integrator/205)
# ---------------------------------------------------------------------------
# THE WEDGE. The runner takes `Q` -> `Q.running` and expects to move `$RUN`
# itself when the session ends. But a session may rename its OWN marker — a
# self-restock session marks the RESTOCK file `…superseded-by-047` and writes
# `047-….md.running` in its place. If that session then hits the 2h cap (rc 124)
# or simply ends, `mv "$RUN" …` finds nothing, the orphan stays, `inbox_running`
# reads 1, guard 1 refuses every restock, and no queued `.md` exists to take.
# The lane is idle forever and the window says nothing.
#
# Measured 2026-09-05: integrator idle ~4:00-4:10am on a marker orphaned the
# previous Thursday, native idle 8:59-10:10am, lane1b idle 7:33-10:10am.
#
# The startup crash-recovery pass cannot catch this — it runs once, at runner
# start, so a marker orphaned under a long-lived runner is never looked at
# again. These tests drive the real write path, because a reaper proven only
# under --dry-run is a reaper proven not to run.


def _reap(handoff, lane="demo", **env):
    """One REAL pass: reap, then restock. Starts no session."""
    e = {"LANE_HANDOFF": str(handoff)}
    e.update(env)
    return run(RUNNER, "--restock-once", str(REPO), lane, env=e)


# The runner ages markers by ctime, which is the right clock (`mv` updates it,
# so it dates the TAKE; mtime would date the directive's authoring and call a
# freshly-taken week-old directive stale). ctime cannot be backdated portably —
# `os.utime` moves atime/mtime and bumps ctime to now — so these tests shrink
# the threshold to 1s and then genuinely wait past it. That keeps the age
# comparison real rather than trivially true: a cap of 0 would fire even if the
# age test were deleted. The bound itself is proved by
# `test_reaper_leaves_a_live_sessions_marker_alone`, which runs the same fixture
# under the real 7200s cap and asserts nothing is touched.
STALE_NOW = {"LANE_SESSION_TIMEOUT": "1", "LANE_STALE_RUNNING_GRACE": "0"}
STALE_WAIT = 1.2   # > the 1s cap above, so the marker is genuinely past it


def test_reaper_unwedges_a_lane_orphaned_by_its_own_session(tmp_path):
    """The ship: the orphan is retired and the lane restocks itself again.

    Both halves are asserted. Retiring the marker without the restock firing
    would leave the lane just as idle as before.
    """
    handoff = _handoff(tmp_path)
    inbox = handoff / "runner-inbox" / "demo"
    (inbox / "047-orphan.md.running").write_text("orphaned by a capped session\n")
    time.sleep(STALE_WAIT)

    rc, out = _reap(handoff, **STALE_NOW)
    assert rc == 0, out
    assert "retired orphaned marker 047-orphan.md.running" in out, out

    # The reported age must be a real elapsed time, not an epoch subtracted from
    # something that was never a clock. `stat -f %c` is not an error on GNU
    # coreutils — there `-f` selects FILESYSTEM status and `%c` is the total
    # inode count, so it exits 0 and yields a large number that is not a time.
    # Probing BSD-first read every marker as decades stale on Linux and retired
    # live sessions' markers; the symptom surfaced in the negative arm, but this
    # is the assertion that names the cause. Deliberately platform-independent:
    # it fails on whichever OS gets the probe order wrong.
    age = int(re.search(r"\((\d+)s old,", out).group(1))
    assert age < 3600, (
        f"the reaper aged this marker at {age}s ({age / 86400:.0f} days) — it is "
        "seconds old, so file_ctime is not reading a timestamp on this platform"
    )

    assert not (inbox / "047-orphan.md.running").exists(), "the orphan still wedges the lane"
    names = sorted(p.name for p in inbox.iterdir())
    assert any(n.startswith("047-orphan.md.stale-") for n in names), names
    assert any(n.startswith("RESTOCK-") and n.endswith(".md") for n in names), (
        f"the lane was unwedged but never restocked: {names}"
    )


def test_reaper_never_requeues_the_orphan_as_work(tmp_path):
    """A retired marker must be invisible to the queue glob.

    Crash recovery re-queues because a dead runner left work genuinely
    unstarted. Here the session RAN — usually merged, pushed and reported — and
    only the bookkeeping was lost. Renaming back to `.md` would re-run finished
    work, so the marker is parked under a name `ls *.md` cannot see.
    """
    handoff = _handoff(tmp_path)
    inbox = handoff / "runner-inbox" / "demo"
    (inbox / "047-orphan.md.running").write_text("already merged and pushed\n")
    time.sleep(STALE_WAIT)

    rc, out = _reap(handoff, **STALE_NOW)
    assert rc == 0, out

    assert not (inbox / "047-orphan.md").exists(), "the orphan was re-queued as live work"
    requeued = [p.name for p in inbox.iterdir() if p.name.endswith(".md") and p.name.startswith("047")]
    assert requeued == [], requeued
    assert "NOT re-queued" in out, out


def test_reaper_leaves_a_live_sessions_marker_alone(tmp_path):
    """The guard that keeps this from being a footgun.

    Under the real cap a marker young enough to belong to a running session is
    not eligible, and guard 1 correctly still blocks the restock. Without this
    arm the reaper would happily retire the marker of a session that is mid-way
    through a merge.
    """
    handoff = _handoff(tmp_path)
    inbox = handoff / "runner-inbox" / "demo"
    live = inbox / "047-live.md.running"
    live.write_text("a session is working on this right now\n")

    rc, out = _reap(handoff)  # default LANE_SESSION_TIMEOUT of 7200s
    assert rc == 1, out
    assert live.exists(), "the reaper retired a live session's marker"
    assert "retired orphaned marker" not in out, out
    assert "a directive is .running — no restock" in out, out
    assert [p.name for p in inbox.iterdir()] == ["047-live.md.running"]


def test_reaper_dry_run_reports_but_writes_nothing(tmp_path):
    """The rehearsal the directive asked for: it prints, it does not act."""
    handoff = _handoff(tmp_path)
    inbox = handoff / "runner-inbox" / "demo"
    orphan = inbox / "047-orphan.md.running"
    orphan.write_text("orphaned\n")
    time.sleep(STALE_WAIT)

    rc, out = run(RUNNER, "--dry-run", str(REPO), "demo",
                  env={"LANE_HANDOFF": str(handoff), **STALE_NOW})
    assert rc == 0, out
    assert "WOULD RETIRE 047-orphan.md.running" in out, out
    assert orphan.exists(), "dry-run retired a marker"
    assert [p.name for p in inbox.iterdir()] == ["047-orphan.md.running"]


def test_restock_once_does_not_requeue_a_running_directive(tmp_path):
    """`--restock-once` starts no session, so it must not re-queue one either.

    Found while proving the reaper (integrator/205): the startup crash-recovery
    pass was skipped under --dry-run but NOT under --restock-once, so a nudge
    aimed at an idle lane renamed a BUSY lane's in-flight marker back to `.md`
    for the real runner to take a second time. It also made the reaper dead code
    on that path — crash recovery had already renamed everything away before it
    ran.
    """
    handoff = _handoff(tmp_path)
    inbox = handoff / "runner-inbox" / "demo"
    live = inbox / "047-in-flight.md.running"
    live.write_text("busy\n")

    rc, out = _reap(handoff)
    assert rc == 1, out
    assert live.exists(), "--restock-once re-queued a live session's directive"
    assert not (inbox / "047-in-flight.md").exists(), (
        "--restock-once handed an in-flight directive back to the queue glob"
    )
    assert "re-queued interrupted" not in out, out


# --- the two paths that actually run in production ---------------------------
# A mutation battery on the reaper killed every mutant EXCEPT "delete the reap
# call from the idle loop" — because the tests above drive `--restock-once`, and
# the idle loop is where the reaper runs for real. These two drive the loop
# itself. `LANE_IDLE_SLEEP` exists so they can.


def _run_loop(
    tmp_path, handoff, fake_claude, seconds=3.0, after_start=None,
    until=None, ceiling=45.0, **env,
):
    """Run the real serve loop until its pass condition appears, then kill it.

    SIGKILL to the whole process group, and `start_new_session=True` so that
    group is never pytest's: the runner traps INT/TERM/HUP and answers with
    `kill 0`, which under a shared group would take the test session down with
    it. KILL cannot be trapped, so the trap never runs at all.

    WORKDIR is tmp_path, not REPO: the runner seeds a cross-root settings.json
    into whatever workdir it is handed, and a test has no business writing that
    into the checkout.

    🔴 `seconds=` USED TO BE A DURATION, AND THAT MADE THESE TESTS A STOPWATCH
    ----------------------------------------------------------------------------
    The old shape slept a fixed budget, killed the runner, and asserted ONCE on
    whatever had been printed by then. That budget was not a property of the
    thing under test — it was a guess about how fast this machine boots a bash
    runner, and it silently became the assertion. integrator-288 measured the
    consequence: composed into a 149-file band, two of these went red (a
    different subset each run, so a flake, not order pollution) while passing
    66/66 when the file runs alone. `lane-runner.sh` had gained a few `git`
    subprocesses on the startup path, the runner reached `idle - no queued work`
    a second later than before, and the reaping iteration never ran inside the
    budget. Nothing about the behaviour under test had changed.

    So `until=` is the acceptance's OWN condition and the wait is a DEADLINE:
    poll the runner's output until that string appears, or until a generous
    ceiling elapses. A slow machine now costs seconds, not a red — and a genuine
    regression still fails, because the string never arrives.

    `seconds=` is kept for the callers that assert on an ABSENCE, where there is
    no string to wait for and a fixed observation window is the correct shape.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "claude"
    fake.write_text(fake_claude)
    fake.chmod(0o755)

    e = dict(os.environ)
    e.update({
        "LANE_HANDOFF": str(handoff),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "LANE_IDLE_SLEEP": "1",
    })
    e.update(env)
    p = subprocess.Popen(
        ["bash", str(RUNNER), str(tmp_path), "demo"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        cwd=str(REPO), env=e, start_new_session=True,
    )
    # Drain stdout on a thread. The deadline below has to READ the output while
    # the runner is still alive, and a pipe that nobody drains can also fill and
    # block the runner mid-startup — which would look exactly like the slowness
    # this deadline exists to tolerate.
    chunks: list[str] = []
    reader = threading.Thread(
        target=lambda: chunks.extend(iter(p.stdout.readline, "")), daemon=True
    )
    reader.start()

    def _wait_for(cond, limit):
        """Poll until `cond` holds. A string is matched against the runner's
        output; a callable receives that output and returns the test's own
        acceptance.

        🔴 THE PASS CONDITION IS WHATEVER THE TEST ASSERTS — ALL OF IT. This
        took two wrong turns, and both are the same mistake from opposite ends:

          * Waiting on `"was renamed by the session itself"` fired one line too
            EARLY: the runner prints it *before* calling `sweep_session_running`,
            so the SIGKILL landed before the sweep ran and the tests went red on
            their filesystem assertion having "reached" their condition.
          * Waiting on the retired file appearing on disk fired one line too
            LATE-in-the-wrong-way: `retire_running_marker` does `mv` and THEN
            echoes, so the predicate went true between the two and the kill ate
            the log line the test also asserts on.

        A test that asserts on output AND on disk has a conjunction for a pass
        condition, so the predicate is that conjunction. Anything narrower grades
        something the test does not.
        """
        stop = time.monotonic() + limit
        while time.monotonic() < stop:
            out_so_far = "".join(chunks)
            if cond(out_so_far) if callable(cond) else cond in out_so_far:
                return True
            time.sleep(0.05)
        return False

    try:
        if after_start is not None:
            # The point of the idle-loop test: this state must appear AFTER the
            # runner has started, or startup crash-recovery reaches it first and
            # the loop's own reaper is never the thing under test.
            #
            # 🔴 THIS WAS `time.sleep(1.0)`, AND THAT IS THE OTHER HALF OF THE
            # FLAKE. One second was a guess at how long the runner takes to
            # finish its ONE-SHOT crash-recovery pass. When `lane-runner.sh`
            # gained a few `git` subprocesses on the startup path, the guess
            # stopped holding under band load: `after_start` fired FIRST, so
            # crash recovery — which is not bounded by SESSION_START — retired
            # the sibling marker the test requires to survive, and the test read
            # as a broken SINCE bound. Waiting for the runner's own "serving
            # lanes" line makes the ordering an INVARIANT rather than a race:
            # that line is printed after the recovery pass, so once it appears
            # the pass is provably done however slow the machine is.
            assert _wait_for("[runner] serving lanes:", ceiling), (
                "the runner never finished its startup pass within "
                f"{ceiling}s:\n{''.join(chunks)}"
            )
            after_start()
        if until is None:
            time.sleep(seconds)
        else:
            _wait_for(until, ceiling)
    finally:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    reader.join(timeout=30)
    try:
        p.stdout.close()
    except OSError:
        # Already closed by the reader thread reaching EOF after the SIGKILL.
        # Nothing to clean up and nothing to report: the output we came for is
        # in `chunks`, and a teardown that raises here would mask the real
        # assertion below it.
        pass
    try:
        p.wait(timeout=30)
    except subprocess.TimeoutExpired:
        # Reaped for exit status only. The process group has already taken a
        # SIGKILL, so a wait that somehow times out cannot change the outcome
        # of this test — and raising would replace a readable assertion failure
        # with a teardown error.
        pass
    return "".join(chunks)


def test_idle_loop_reaps_a_marker_orphaned_after_the_runner_started(tmp_path):
    """The production path, and the one startup crash-recovery cannot reach.

    Crash recovery runs ONCE, at runner start. This orphan appears afterwards —
    which is the real shape: a session orphans its own marker hours into a
    long-lived runner. Before integrator/205 nothing looked at it again and the
    lane idled until a human noticed.
    """
    handoff = _handoff(tmp_path, program=None)   # no program file: no restock noise
    inbox = handoff / "runner-inbox" / "demo"

    out = _run_loop(
        tmp_path, handoff, "#!/bin/bash\nexit 0\n",
        # The deadline's condition IS the assertion below. Anything else and the
        # wait grades something the test does not.
        until=lambda out: (
            "retired orphaned marker" in out
            and list(inbox.glob("047-orphan.md.stale-*"))
            and not list(inbox.glob("*.md.running"))
        ),
        LANE_SESSION_TIMEOUT="1", LANE_STALE_RUNNING_GRACE="0",
        after_start=lambda: (inbox / "047-orphan.md.running").write_text("orphaned\n"),
    )
    assert "retired orphaned marker" in out, out
    assert not list(inbox.glob("*.md.running")), (
        f"the lane is still wedged: {[p.name for p in inbox.iterdir()]}"
    )
    assert list(inbox.glob("047-orphan.md.stale-*")), [p.name for p in inbox.iterdir()]


def test_a_session_that_renames_its_own_marker_does_not_wedge_the_lane(tmp_path):
    """The measured bug, end to end, with a session that does what ours do.

    A self-restock session marks its RESTOCK file `…superseded-by-047` and
    writes `047-….md.running` in its place. The runner's `mv "$RUN" …` then has
    nothing to move: before this fix it printed an mv error, called the
    directive consumed, and left the new marker behind forever — `inbox_running`
    stayed 1, guard 1 refused every restock, and the lane went idle with nothing
    in the window to say why (integrator 4:00-4:10am, native 8:59-10:10am,
    lane1b 7:33-10:10am, all on 2026-09-05).
    """
    handoff = _handoff(tmp_path, program=None)
    inbox = handoff / "runner-inbox" / "demo"
    (inbox / "001-work.md").write_text("do the thing\n")

    fake = (
        "#!/bin/bash\n"
        f'INBOX="{inbox}"\n'
        'for R in "$INBOX"/*.md.running; do\n'
        '  [ -e "$R" ] || continue\n'
        '  mv "$R" "${R%.running}.superseded-by-047"\n'
        'done\n'
        ': > "$INBOX/047-self-written.md.running"\n'
        "exit 0\n"
    )
    # The acceptance is output AND disk, so the wait condition is both.
    out = _run_loop(
        tmp_path, handoff, fake,
        until=lambda out: (
            "was renamed by the session itself" in out
            and list(inbox.glob("047-self-written.md.stale-*"))
            and not list(inbox.glob("*.md.running"))
        ),
    )

    assert "was renamed by the session itself" in out, out
    assert not list(inbox.glob("*.md.running")), (
        f"the lane is wedged exactly as it was before the fix: "
        f"{[p.name for p in inbox.iterdir()]}"
    )
    assert list(inbox.glob("047-self-written.md.stale-*")), [p.name for p in inbox.iterdir()]
    # And the directive the session really did run is not handed back as work.
    assert not (inbox / "001-work.md").exists()


def test_the_post_session_sweep_only_touches_this_sessions_own_leftovers(tmp_path):
    """The bound that keeps the sweep from being a blunt instrument.

    The sweep fires when a session renamed its own marker, and it must retire
    only what THAT session left behind. A `.running` marker that already existed
    when the session started is somebody else's — a duplicate runner's live
    take, most plausibly — and retiring it would hand that lane's in-flight
    directive to a second session, the very hazard the startup crash-recovery
    pass has always carried.

    So the marker here is created a clear interval BEFORE the work is queued,
    which puts its ctime below the session's start stamp.
    """
    handoff = _handoff(tmp_path, program=None)
    inbox = handoff / "runner-inbox" / "demo"
    other = inbox / "099-someone-elses.md.running"

    def stage():
        other.write_text("a sibling runner is mid-session on this\n")
        time.sleep(2.0)   # ctime gap, so `other` predates SESSION_START
        (inbox / "001-work.md").write_text("do the thing\n")

    fake = (
        "#!/bin/bash\n"
        f'INBOX="{inbox}"\n'
        'mv "$INBOX/001-work.md.running" "$INBOX/001-work.md.superseded-by-047"\n'
        ': > "$INBOX/047-self-written.md.running"\n'
        "exit 0\n"
    )
    # Default 7200s cap throughout, so the idle reaper is not what spares
    # `other` — only the sweep's SINCE bound can.
    out = _run_loop(
        tmp_path, handoff, fake, after_start=stage,
        until=lambda out: (
            "was renamed by the session itself" in out
            and list(inbox.glob("047-self-written.md.stale-*"))
        ),
    )

    assert "was renamed by the session itself" in out, out
    assert list(inbox.glob("047-self-written.md.stale-*")), (
        f"the sweep did not run at all: {[p.name for p in inbox.iterdir()]}"
    )
    assert other.exists(), (
        "the sweep retired a marker that predates the session — that is a "
        f"sibling runner's live directive: {[p.name for p in inbox.iterdir()]}"
    )


# ------------------------------------------- notice 39 rung 2: the agent tag ----
#
# WHAT THESE GUARD, AND WHY THEY ARE HERE RATHER THAN BESIDE THE HELPER
# ---------------------------------------------------------------------
# `test_agent_origin_outbound_tag.py` proves the tag is BUILT correctly. Nothing
# proved it was ever INSTALLED in the shell that types the curl, and that is the
# half that failed: notice 39 specifies rung 2 as "ONE line in lane-runner.sh
# that ... sources latency's curl shadow", which cannot work (#4662). Every Bash
# tool call in a lane session is a fresh shell exec'd from the profile, and a
# shell FUNCTION does not survive exec. Sourced in the runner it would merge,
# pass every gate, be recorded done, and tag nothing — #4632's shape exactly
# (D70: merged, tested, ruled, inert for four days).
#
# So these tests deliberately do not call the helper. They run a real login shell
# the way the runner spawns one and read the argv it would have put on the wire.
#
# The third test is the one with teeth. Redirecting ZDOTDIR does not ADD a
# startup file, it MOVES zsh's whole search: point it at a directory lacking
# `.zprofile` and `~/.zprofile` silently stops being read in every lane shell.
# Measured: HOMEBREW_PREFIX empties, so brew and its PATH vanish fleet-wide. That
# regression is far larger than the one rung 2 fixes and it is completely silent,
# so it gets a test with its own negative control.

ZSH = shutil.which("zsh")
needs_zsh = pytest.mark.skipif(ZSH is None, reason="the lane shell is zsh; none installed here")

ZDOTDIR_DIR = REPO / "tools" / "lane-zdotdir"
SHADOW = REPO / "tools" / "bl-agent-curl.sh"


def _tag_block():
    """The runner's own tag-gating code, lifted out and made callable.

    Extracted rather than reimplemented so the test exercises the shipped text.
    Asserted non-empty: an extraction that silently matches nothing would make
    every assertion below vacuously pass (the blind-zero class, gotcha #53).
    """
    src = RUNNER.read_text()
    start = src.index("BL_REPO=")
    end = src.index("\n}\n", src.index("bl_warn_if_runner_is_stale()", start)) + 3
    block = src[start:end]
    for name in ("bl_tag_lane", "bl_carrier_zdotdir", "bl_warn_if_runner_is_stale"):
        assert f"{name}()" in block, f"extraction lost {name}:\n{block}"
    return block


def _bundle_repo(root, *, chain=True, shadow=True, in_working_tree=True):
    """A throwaway git repo carrying (or missing) the carrier bundle.

    `in_working_tree=False` deletes the files from the CHECKOUT after committing
    them. That is the whole point of #4685: the fleet runs `$HOME/bainluck`,
    whose checkout lags master by a merge cycle and can hold uncommitted edits,
    so delivery must read the committed ref and never the working tree.
    """
    root.mkdir(parents=True, exist_ok=True)
    git = ["git", "-C", str(root)]
    subprocess.run(git[:1] + ["init", "-q", str(root)], check=True)
    (root / "lane-runner.sh").write_text("#!/bin/bash\n# stand-in\n")
    if chain:
        (root / "tools" / "lane-zdotdir").mkdir(parents=True)
        for name in (".zshenv", ".zprofile", ".zshrc", ".zlogin"):
            shutil.copy(ZDOTDIR_DIR / name, root / "tools" / "lane-zdotdir" / name)
    if shadow:
        (root / "tools").mkdir(parents=True, exist_ok=True)
        shutil.copy(SHADOW, root / "tools" / "bl-agent-curl.sh")
    subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
    subprocess.run(
        git + ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "bundle"],
        check=True, capture_output=True,
    )
    if not in_working_tree:
        shutil.rmtree(root / "tools", ignore_errors=True)
        assert not (root / "tools").exists()
    return root


def _resolve_carrier(repo, cache, ref="HEAD", extra=None):
    """Run the shipped `bl_carrier_zdotdir` against `repo`. Returns (rc, stdout)."""
    block = _tag_block().replace(
        'BL_REPO="$(cd "$(dirname "$0")" && pwd -P)"', f'BL_REPO="{repo}"'
    )
    assert str(repo) in block, "the BL_REPO override did not apply"
    env = dict(os.environ, BL_CARRIER_REF=ref, BL_CARRIER_ROOT=str(cache))
    env.update(extra or {})
    p = subprocess.run(
        ["bash", "-c", f"set -u\n{block}\nbl_carrier_zdotdir"],
        capture_output=True, text=True, timeout=60, env=env,
    )
    return p.returncode, p.stdout.strip()


def _lane_shell(script, env=None, home=None):
    """Run `script` in a login zsh, as `lane-runner.sh` spawns one.

    `env -i`-equivalent: the environment is built from nothing, so anything the
    assertions read can only have come from a startup file that actually ran.
    An inherited value would make the chain test pass without a chain.
    """
    base = {"HOME": str(home or Path.home()), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    base.update(env or {})
    p = subprocess.run(
        [ZSH, "-l", "-c", script], capture_output=True, text=True, env=base, timeout=60
    )
    return p.returncode, p.stdout + p.stderr


def test_the_runner_gates_the_tag_on_the_lane_name():
    """One lane first (notice 39 guard 3): a lane not on the list gets nothing."""
    block = _tag_block()
    for lanes, lane, want in [
        ("latency", "latency", 0), ("latency", "ux", 1),
        ("all", "ux", 0), ("latency ux", "ux", 0), ("latency ux", "live", 1),
    ]:
        p = subprocess.run(
            ["bash", "-c", f'set -u; BL_TAG_LANES={lanes!r}\n{block}\nbl_tag_lane {lane!r}'],
            capture_output=True, text=True, cwd=str(REPO), timeout=30,
        )
        assert p.returncode == want, f"BL_TAG_LANES={lanes} lane={lane}: {p.returncode} {p.stderr}"


def test_every_lane_in_lanes_conf_is_tagged_by_default():
    """Notice 39 rung 2, widened: with nothing set, EVERY lane names itself.

    The default moved from `latency` to `all` on 2026-09-10 once the one-lane
    server-side read was paid through the real carrier (4 tagged -> 0 rows, 4
    untagged controls -> 4 rows, production 16:34Z).

    COMPUTED FROM `lanes.conf`, NOT ENUMERATED HERE, and that is the point: a
    lane added tomorrow inherits the rule without anyone remembering this test
    exists. Enumerating the ten names would pass forever while lane eleven went
    out untagged — the exact shape of the defect rung 2 was written to fix.

    Asserted against an UNSET `BL_TAG_LANES`, so it reads the shipped default
    rather than a value the test supplied to itself. The sibling test above
    still covers explicit narrowing.
    """
    conf = (REPO / "lanes.conf").read_text()
    m = re.search(r'^LANES_ALL="([^"]+)"', conf, re.M)
    assert m, "lanes.conf no longer declares LANES_ALL as a double-quoted literal"
    lanes = m.group(1).split()
    # Denominator guard: an empty or truncated list makes every case below
    # vacuously true (the blind-zero class, gotcha #53).
    assert len(lanes) >= 8, f"lanes.conf lists only {len(lanes)}: {lanes}"

    block = _tag_block()
    env = {k: v for k, v in os.environ.items() if k != "BL_TAG_LANES"}
    untagged = []
    for lane in lanes:
        p = subprocess.run(
            ["bash", "-c", f'set -u\n{block}\nbl_tag_lane {lane!r}'],
            capture_output=True, text=True, cwd=str(REPO), timeout=30, env=env,
        )
        if p.returncode != 0:
            untagged.append(f"{lane} (rc={p.returncode}) {p.stderr.strip()}")
    assert untagged == [], (
        "a lane runs untagged under the shipped default, so its production reads "
        "land in search_query_logs indistinguishable from a person's (notice 39):"
        "\n  " + "\n  ".join(untagged)
    )


def test_the_runner_refuses_to_point_zdotdir_at_a_checkout_without_the_chain(tmp_path):
    """Notice 39 guard 1, in its dangerous direction.

    A missing shadow must degrade to plain curl. Exporting ZDOTDIR anyway would
    not merely skip the tag, it would break the shell — and this is not
    hypothetical: on 2026-09-09 `~/bainluck/tools/bl-agent-curl.sh` did not exist
    on disk (that tree was stale at 8991f1a6; the shadow merged later at
    8c37c7f0), which is the exact path the shadow's docstring tells agents to use.
    """
    cache = tmp_path / "cache"

    rc, out = _resolve_carrier(_bundle_repo(tmp_path / "empty", chain=False, shadow=False), cache)
    assert rc != 0 and out == "", f"a ref with no bundle was accepted: {out!r}"

    rc, out = _resolve_carrier(_bundle_repo(tmp_path / "nochain", chain=False), cache)
    assert rc != 0 and out == "", f"a shadow with no chain beside it was accepted: {out!r}"

    rc, out = _resolve_carrier(_bundle_repo(tmp_path / "noshadow", shadow=False), cache)
    assert rc != 0 and out == "", f"a chain with no shadow beside it was accepted: {out!r}"

    # Positive control: with both committed it must say yes, or the three
    # refusals above prove nothing about the bundle and everything about a
    # broken path (gotcha #53 — a refusal that refuses everything is not a guard).
    rc, out = _resolve_carrier(_bundle_repo(tmp_path / "whole"), cache)
    assert rc == 0 and out.endswith("/tools/lane-zdotdir"), (
        f"the resolver refuses even a complete bundle — it tags nobody: {out!r}"
    )
    assert (Path(out) / ".zshenv").is_file(), out


def test_runner_delivery_installs_the_complete_carrier_bundle(tmp_path):
    """CERT-2461's required repair: delivery is to the RUNTIME, not to a checkout.

    The BLOCK was not about the carrier being wrong — it was that the ship was
    inert at its delivery boundary. `lanes.conf` runs `$HOME/bainluck/lane-runner.sh`,
    and on 2026-09-09 that tree held neither `tools/lane-zdotdir/` nor
    `tools/bl-agent-curl.sh` on disk, so the presence guard fell through and every
    lane ran untagged while every gate read GREEN.

    So the bundle is resolved from a COMMITTED REF and materialized into a cache
    the runner owns. This asserts the whole bundle arrives — not just the one file
    the guard happens to test — from a repo whose WORKING TREE has none of it.
    """
    repo = _bundle_repo(tmp_path / "stale", in_working_tree=False)
    cache = tmp_path / "cache"

    rc, out = _resolve_carrier(repo, cache)
    assert rc == 0, f"delivery refused a repo that has the bundle committed: {out!r}"

    zdot = Path(out)
    for name in (".zshenv", ".zprofile", ".zshrc", ".zlogin"):
        assert (zdot / name).is_file(), f"{name} was not delivered into {zdot}"
    shadow = zdot.parent / "bl-agent-curl.sh"
    assert shadow.is_file(), f"the shadow was not delivered beside the chain: {zdot}"

    # Byte-identical to what is committed, or it is a different carrier.
    assert (zdot / ".zshenv").read_text() == (ZDOTDIR_DIR / ".zshenv").read_text()
    assert shadow.read_text() == SHADOW.read_text()

    # Content-addressed and idempotent: asking twice yields the same directory
    # and does not republish. Two runners start within seconds of each other.
    rc2, out2 = _resolve_carrier(repo, cache)
    assert (rc2, out2) == (rc, out), f"delivery is not idempotent: {out!r} vs {out2!r}"
    assert len(list(cache.iterdir())) == 1, f"delivery left litter: {list(cache.iterdir())}"

    # Nothing half-written is ever visible: no staging directory survives.
    assert not [p for p in cache.iterdir() if p.name.startswith(".staging")], list(cache.iterdir())


def test_a_delivery_that_cannot_be_written_refuses_instead_of_naming_a_path(tmp_path):
    """The worst failure this code can have, and the one four other tests missed.

    Every other test here runs where materialization succeeds, so none of them
    can see the final presence check deleted — that mutation survived them all.
    It is the load-bearing one: if the cache cannot be written and the resolver
    still echoes a path, `lane-runner.sh` exports ZDOTDIR to a directory that does
    not exist. That does not merely skip the tag. It moves zsh's whole startup
    search off $HOME, so `~/.zprofile` stops being read in every lane shell,
    fleet-wide — measured: HOMEBREW_PREFIX empties and brew leaves PATH.

    Refusing must therefore survive a cache that cannot be created, not just a
    ref that has nothing in it.
    """
    repo = _bundle_repo(tmp_path / "repo")
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("a regular file, so mkdir -p beneath it cannot succeed\n")

    rc, out = _resolve_carrier(repo, blocker / "cache")
    assert out == "", (
        f"named a carrier directory it could not create: {out!r} — exporting this "
        "as ZDOTDIR drops ~/.zprofile from every lane shell"
    )
    assert rc != 0, "an unwritable cache reported success"


def test_delivery_never_reads_the_working_tree(tmp_path):
    """The mutation that would silently restore #4685.

    A resolver that fell back to `$BL_REPO/tools/...` would pass every test above
    — they all run where the committed content and the checkout agree. Here they
    DISAGREE: the checkout carries a decoy chain that must never be delivered.
    """
    repo = _bundle_repo(tmp_path / "repo", in_working_tree=False)
    decoy = repo / "tools" / "lane-zdotdir"
    decoy.mkdir(parents=True)
    (decoy / ".zshenv").write_text("# DECOY — the working tree's copy\n")
    (repo / "tools" / "bl-agent-curl.sh").write_text("# DECOY shadow\n")

    rc, out = _resolve_carrier(repo, tmp_path / "cache")
    assert rc == 0, out
    assert "DECOY" not in (Path(out) / ".zshenv").read_text(), (
        f"delivery served the working tree instead of the committed ref: {out}"
    )
    assert "DECOY" not in (Path(out).parent / "bl-agent-curl.sh").read_text(), out


def test_the_runner_says_so_when_it_is_not_the_committed_runner(tmp_path):
    """#4689: drift must be loud.

    A tooling ship that merges green and changes nothing is this repo's recurring
    failure (#4632: D70 merged, tested, ruled, inert four days; CERT-2461 the
    same shape). A lane cannot tell that the runner executing it is not the one
    on master, so it says so itself — on stderr, once, never fatally.
    """
    repo = _bundle_repo(tmp_path / "repo")
    block = _tag_block().replace(
        'BL_REPO="$(cd "$(dirname "$0")" && pwd -P)"', f'BL_REPO="{repo}"'
    )
    env = dict(os.environ, BL_CARRIER_REF="HEAD", BL_CARRIER_ROOT=str(tmp_path / "c"))

    # `$0` inside `bash -c` is the argument after the command string, so the
    # runner under test is named there rather than by editing the block.
    committed = repo / "lane-runner.sh"
    p = subprocess.run(
        ["bash", "-c", f'set -u\n{block}\nbl_warn_if_runner_is_stale lane', str(committed)],
        capture_output=True, text=True, timeout=60, env=env,
    )
    assert p.returncode == 0, p.stderr
    assert "WARNING" not in p.stderr, (
        f"warned about a runner that IS the committed one — the warning is noise:\n{p.stderr}"
    )

    drifted = tmp_path / "drifted-lane-runner.sh"
    drifted.write_text(committed.read_text() + "\n# an edit that never merged\n")
    p = subprocess.run(
        ["bash", "-c", f'set -u\n{block}\nbl_warn_if_runner_is_stale lane', str(drifted)],
        capture_output=True, text=True, timeout=60, env=env,
    )
    assert p.returncode == 0, "the drift warning must never be fatal — a lane that " \
        "cannot run is worse than one running a stale runner"
    assert "WARNING" in p.stderr and "#4685" in p.stderr, (
        f"a runner that is not on master said nothing:\n{p.stderr!r}"
    )
    assert p.stdout == "", f"the warning belongs on stderr, not in the log stream: {p.stdout!r}"


@needs_zsh
def test_a_lane_shell_carries_the_tag_to_our_hosts_and_nowhere_else():
    """The end of the wire. Not the helper — the shell the lane actually types in."""
    env = {"ZDOTDIR": str(ZDOTDIR_DIR), "BL_AGENT": "latency", "BL_CURL_PRINT": "1"}

    rc, ours = _lane_shell('curl -s "https://api.bainluck.com/api/events/search?q=x"', env)
    assert rc == 0, ours
    assert "x-bainluck-origin: latency" in ours, f"a lane's own read went out untagged:\n{ours}"
    assert "BainLuckBot/1.0 (latency)" in ours, ours

    # An internal header naming our lanes has no business on a third party's wire.
    rc, theirs = _lane_shell('curl -s "https://api.kalshi.com/trade-api/v2/events"', env)
    assert rc == 0, theirs
    assert "x-bainluck-origin" not in theirs, f"tagged a third party:\n{theirs}"

    # Guard 1 at the shell level: unnamed passes through as plain curl.
    rc, unnamed = _lane_shell(
        'curl -s "https://api.bainluck.com/api/events/search?q=x"',
        {"ZDOTDIR": str(ZDOTDIR_DIR), "BL_CURL_PRINT": "1"},
    )
    assert rc == 0, unnamed
    assert "x-bainluck-origin" not in unnamed, (
        "an unnamed caller was given a substituted tag; any non-'user' value "
        f"SUPPRESSES the search-log row, so this deletes it from the table:\n{unnamed}"
    )


@needs_zsh
def test_the_zdotdir_chain_does_not_drop_the_users_own_startup_files(tmp_path):
    """Redirecting ZDOTDIR moves the search; each name here must chain the real one.

    Hermetic: a synthetic HOME whose markers exist nowhere else, so a marker in
    the output can only mean that file was sourced.
    """
    home = tmp_path / "home"
    home.mkdir()
    for name in (".zshenv", ".zprofile", ".zlogin"):
        (home / name).write_text(f'export MARK_{name[1:].upper()}=yes\n')

    probe = 'echo "env=$MARK_ZSHENV prof=$MARK_ZPROFILE login=$MARK_ZLOGIN"'

    # Negative control FIRST. Without it, a pass below could just mean zsh never
    # honoured ZDOTDIR at all and read $HOME the whole time.
    bare = tmp_path / "bare"
    bare.mkdir()
    rc, out = _lane_shell(probe, {"ZDOTDIR": str(bare)}, home=home)
    assert "env= prof= login=" in out, (
        f"expected an empty ZDOTDIR to drop all three user files; got {out!r} — "
        "zsh is not honouring ZDOTDIR here, so the real assertion proves nothing"
    )

    rc, out = _lane_shell(probe, {"ZDOTDIR": str(ZDOTDIR_DIR)}, home=home)
    assert rc == 0, out
    assert "env=yes prof=yes login=yes" in out, (
        f"the chain dropped a user startup file: {out!r}. Every lane shell would "
        "silently lose whatever ~/.zprofile sets — on the lane machine that is "
        "brew's shellenv, i.e. HOMEBREW_PREFIX and half of PATH."
    )


def test_the_session_launch_actually_consults_the_gate():
    """The wiring, not just the parts.

    A perfect gate and a perfect chain still tag nothing if the launch line never
    calls one. Asserted on the shipped text because the alternative — starting a
    real lane session — is not something a test may do.
    """
    src = RUNNER.read_text()
    launch = src.index("timeout \"$SESSION_TIMEOUT\" claude")
    window = src[launch - 500:launch]
    assert "bl_tag_lane" in window, (
        "the session launch does not consult bl_tag_lane; the tag is inert"
    )
    assert "bl_carrier_zdotdir" in window, (
        "the launch does not resolve the carrier from the committed ref; it is "
        "back to trusting whatever the checkout happens to hold (#4685)"
    )
    assert 'export BL_AGENT="$L" ZDOTDIR=' in window, (
        "the launch exports something other than both halves of the tag"
    )
    # The export must be reached ONLY when the resolver succeeded, or a refused
    # delivery still points ZDOTDIR somewhere and breaks every lane shell.
    assert 'ZDOTDIR="$BL_ZD"' in window, (
        "ZDOTDIR is exported from something other than the resolver's own answer"
    )


@needs_zsh
def test_a_chain_without_its_shadow_degrades_to_plain_curl_and_stays_quiet(tmp_path):
    """Notice 39 guard 1: an absent shadow file falls through to PLAIN curl.

    `lane-runner.sh` already refuses to point ZDOTDIR at such a checkout, so this
    is the second layer — a runner started before the tree moved, or ZDOTDIR set
    by hand. The unguarded source is not merely untagged: `.zshenv` runs for every
    zsh there is, so a failing `.` would print an error on the stderr of every
    command every lane runs, fleet-wide.

    Added because the mutation that deletes the presence guard survived the first
    five tests here — all of them happen to run with the shadow present.
    """
    chain = tmp_path / "tools" / "lane-zdotdir"
    chain.mkdir(parents=True)
    for f in ZDOTDIR_DIR.iterdir():
        shutil.copy(f, chain / f.name)
    assert not (tmp_path / "tools" / "bl-agent-curl.sh").exists()

    rc, out = _lane_shell('echo "curl -> $(type curl)"', {"ZDOTDIR": str(chain)})
    assert rc == 0, out
    assert "shell function" not in out, f"installed a shadow that is not there:\n{out}"
    assert "curl -> curl is /usr/bin/curl" in out, out
    for noise in ("no such file", "not found", "No such file"):
        assert noise not in out, (
            f"an absent shadow made noise on every shell's stderr: {out!r}"
        )


# ------------------------------------------------ the supervisor window ----
#
# latency/313, 2026-09-10 (Fable-5, at Alex's ask). `start-lanes.sh` used to END
# by printing the supervisor command for Alex to run by hand in a second window.
# That made the fleet's self-healing depend on a human remembering a step after
# every reboot — and it is the one step whose omission is SILENT: without the
# supervisor, the first lane that dies stays dead, while every lane still up
# makes the fleet look healthy.
#
# Both arms are asserted. A test that only covered "it launches one" would pass
# just as happily on a script that launches a second supervisor over a live one,
# and two supervisors double every relaunch either of them decides to make.


def _fake_supervisor(tmp_path):
    p = tmp_path / "fake-lanes-supervisor.sh"
    p.write_text("#!/bin/bash\nsleep 0\n")
    p.chmod(0o755)
    return p


def test_start_lanes_launches_the_supervisor_when_none_is_running(tmp_path):
    sup = _fake_supervisor(tmp_path)
    conf = write_conf(tmp_path, {"alpha": str(tmp_path)}, graders=0, supervisor=str(sup))
    rc, out = run(
        START,
        "--dry-run",
        env={
            "LANES_CONF": str(conf),
            "PATH": f"{stub_pgrep(tmp_path, found=False)}:{os.environ['PATH']}",
        },
    )
    assert rc == 0, out
    assert "supervisor: started" in out, f"no supervisor window is opened:\n{out}"
    assert str(sup) in out, f"the window does not run the supervisor script:\n{out}"
    # It is counted in the tally, or Alex reads "13 windows opened" and sees 14.
    assert "and 1 supervisor" in out, f"the supervisor is opened but not counted:\n{out}"


def test_start_lanes_does_not_open_a_SECOND_supervisor(tmp_path):
    sup = _fake_supervisor(tmp_path)
    conf = write_conf(tmp_path, {"alpha": str(tmp_path)}, graders=0, supervisor=str(sup))
    rc, out = run(
        START,
        "--dry-run",
        env={
            "LANES_CONF": str(conf),
            "PATH": f"{stub_pgrep(tmp_path, found=True)}:{os.environ['PATH']}",
        },
    )
    assert rc == 0, out
    assert "supervisor: already running" in out, out
    assert "supervisor: started" not in out, f"opened a second supervisor:\n{out}"
    assert str(sup) not in out, f"a duplicate supervisor window is opened:\n{out}"
    assert "and 0 supervisor" in out, f"counted a window it did not open:\n{out}"


def test_the_supervisor_window_prevents_sleep_but_lets_the_DISPLAY_sleep(tmp_path):
    """`-is`, never `-d`.

    Alex had been running `caffeinate -dimsu` in a window of its own beside the
    supervisor. Folding that in wholesale would keep his SCREEN awake for as long
    as the fleet runs, which nothing about supervising lanes needs. The flags are
    asserted exactly, because `-dis` would pass any check for "contains -i".
    """
    sup = _fake_supervisor(tmp_path)
    conf = write_conf(tmp_path, {"alpha": str(tmp_path)}, graders=0, supervisor=str(sup))
    rc, out = run(
        START,
        "--dry-run",
        env={
            "LANES_CONF": str(conf),
            "PATH": f"{stub_pgrep(tmp_path, found=False)}:{os.environ['PATH']}",
        },
    )
    assert rc == 0, out
    line = next((ln for ln in out.splitlines() if "caffeinate" in ln), None)
    assert line is not None, f"the supervisor is not launched under caffeinate:\n{out}"
    flags = re.search(r"caffeinate\s+(-\S+)", line)
    assert flags, line
    assert set(flags.group(1)) == set("-is"), (
        f"caffeinate flags are {flags.group(1)!r}, expected exactly -is "
        f"(no -d: the display may sleep): {line}"
    )


def test_start_lanes_survives_a_checkout_with_no_supervisor_script(tmp_path):
    """Tolerated, not fatal — the same rule the measurement bus gets above.

    An older checkout must still bring up every lane. But it must SAY so: a
    missing supervisor and a running one both produce a fleet that looks fine
    for exactly as long as nothing dies.
    """
    conf = write_conf(
        tmp_path,
        {"alpha": str(tmp_path)},
        graders=0,
        supervisor=str(tmp_path / "nope-supervisor.sh"),
    )
    rc, out = run(
        START,
        "--dry-run",
        env={
            "LANES_CONF": str(conf),
            "PATH": f"{stub_pgrep(tmp_path, found=False)}:{os.environ['PATH']}",
        },
    )
    assert rc == 0, out
    assert "supervisor: SKIPPED" in out, f"a missing supervisor is silent:\n{out}"
    assert "alpha" in out, f"a missing supervisor stopped the lanes launching:\n{out}"


def test_start_lanes_no_longer_asks_alex_to_run_the_supervisor_by_hand():
    """The instruction has to LEAVE, not merely be joined by the automation.

    A script that opens the window and still prints "also run the supervisor
    once" teaches the reader to run a second one, which is the state this change
    exists to end.
    """
    src = START.read_text()
    assert "Also run the supervisor once" not in src, (
        "start-lanes.sh still tells Alex to launch the supervisor by hand"
    )


def test_the_supervisor_path_lives_in_lanes_conf_like_every_other_runner():
    """Same reason the lane list does: the two scripts must not be able to
    disagree about the topology, and which script is the supervisor is part of
    it. A path spelled inside start-lanes.sh is a second copy by definition."""
    assert source_conf('echo "${SUPERVISOR:-UNSET}"').strip().endswith(
        "lanes-supervisor.sh"
    ), "lanes.conf does not name the supervisor"
