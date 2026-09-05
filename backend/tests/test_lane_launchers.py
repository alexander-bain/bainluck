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


def write_conf(tmp_path, lanes, graders=2, runner=None, lane4=None, bus=None):
    """A synthetic lanes.conf. `lanes` maps lane name -> worktree dir.

    `bus` defaults to None = BUS_RUNNER unset, which is the older-checkout case:
    the launchers must still bring up every lane and grader without it.
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
    )
    return conf


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
