"""Guard tests for tools/runner-text-drift.sh (latency/309, 2026-09-10, #4777).

WHAT REGRESSED, AND WHY THESE TESTS EXIST
-----------------------------------------
Bash reads a compound command into memory in full before executing it. The lane
runner's body is one `while true; do … done`, so a runner executes the AST it
parsed at process start and never re-reads its file. On 2026-09-10 notice 39's
rung 2 merged at 11:19Z into a file that ten runners — all started ~13h earlier —
would never re-read. Every gate was green; nothing was tagged. Third such ship in
a week (#4632, #4685, then this).

`lane-runner.sh` already had a staleness guard and could not see it: it hashes the
bytes ON DISK against master, and those were byte-identical. The mismatch was
between the file and what the running processes held in memory. So the check has
to be OUT OF PROCESS, and that is what is guarded here.

Every test drives the tool against a SYNTHETIC long-running script via
`--pattern`, so nothing here reads, restarts or reports on the live fleet, and the
suite behaves identically on Alex's laptop and on Linux CI where no lane runs.

BOTH ARMS, ALWAYS. A staleness detector that only ever fires is as useless as one
that never does, so each behaviour is asserted in both directions, and the
non-obvious preconditions are asserted too — the subshell test first proves the
process table really does hold two matching processes, because otherwise
"reported exactly one" would pass while testing nothing.
"""

import os
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "runner-text-drift.sh"

# `$1` is a sentinel the fixture waits on. A process appearing in `ps` proves only
# that bash was exec'd, NOT that it has read its script yet — and a test that then
# rewrites that script can truncate it inside bash's read window, so bash sees an
# empty file and exits 0. That raced 1 run in 3 before the sentinel existed.
LOOP = '#!/bin/bash\ntouch "$1"\nwhile true; do sleep 1; done\n'


def _run(*args, timeout=60):
    return subprocess.run(
        ["bash", str(TOOL), *args], capture_output=True, text=True, timeout=timeout
    )


def _wait_visible(proc, pattern, timeout=20.0):
    """Block until `ps` shows the process carrying the pattern, or fail loudly.

    Without this the tool can run before the fork is in the process table, which
    would make every arm below pass for the wrong reason.

    The failure message has to DISCRIMINATE. "Never appeared in ps" is produced
    equally by a bash that died at startup, a `ps` that cannot be run at all, and
    a `ps` whose output was truncated past the script name — and the first CI run
    of this file hit one of those three while reporting a sentence that fitted all
    three. So on timeout, say which: whether the process is alive, and what `ps`
    actually printed for it.
    """
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        # `-ww`, or procps truncates to 80 columns when stdout is not a terminal
        # and pytest's tmp_path pushes the script name past the cut — which is
        # exactly how this failed on Linux CI while passing on macOS.
        last = subprocess.run(
            ["ps", "-ww", "-o", "command=", "-p", str(proc.pid)],
            capture_output=True, text=True,
        ).stdout
        if pattern in last:
            return
        time.sleep(0.1)

    alive = proc.poll() is None
    allps = subprocess.run(
        ["ps", "-axww", "-o", "pid=,command="], capture_output=True, text=True
    )
    pytest.fail(
        f"pid {proc.pid} never appeared in ps carrying {pattern!r}.\n"
        f"process alive: {alive} (returncode {proc.returncode})\n"
        f"ps -ww -p {proc.pid} printed: {last!r}\n"
        f"ps -axww rc={allps.returncode}, {len(allps.stdout.splitlines())} lines, "
        f"rows mentioning the pattern: "
        f"{[ln for ln in allps.stdout.splitlines() if pattern in ln]}"
    )


@pytest.fixture
def launcher(tmp_path, request):
    """A unique-named long-running script, started and reaped around the test."""
    procs = []

    def _start(body=LOOP, name=None):
        name = name or f"fake-runner-{request.node.name[:24]}-{os.getpid()}.sh"
        script = tmp_path / name
        script.write_text(body)
        script.chmod(0o755)
        sentinel = tmp_path / f"{name}.started"
        started = time.time()
        proc = subprocess.Popen(["/bin/bash", str(script), str(sentinel)])
        procs.append(proc)
        _wait_visible(proc, script.name)
        # Both conditions, because they answer different questions: `ps` says the
        # process exists, the sentinel says bash has finished reading its script
        # and is inside the loop. Only the second makes it safe to touch the file.
        deadline = time.time() + 15
        while time.time() < deadline and not sentinel.exists():
            assert proc.poll() is None, f"launcher exited {proc.returncode} at startup"
            time.sleep(0.05)
        assert sentinel.exists(), "launcher never signalled that it had started"
        return script, proc, started

    yield _start

    for proc in procs:
        proc.kill()
        proc.wait(timeout=10)


def _set_mtime(path, when):
    os.utime(path, (when, when))


def _start_epoch(pid):
    """The process's start time exactly as the tool computes it, from `ps lstart`.

    The arms below must set mtimes relative to THIS, not to `time.time()` around
    `Popen`. On an idle laptop the fork lands in the same second and the two agree;
    on a loaded 4-shard CI runner the process can start a second or more later, so
    "same second" and "60s after start" silently became "before start" and every
    staleness arm read `current`. Anchoring on the tool's own clock removes the
    machine's load from the assertion.
    """
    out = subprocess.run(
        ["ps", "-ww", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True
    ).stdout.strip()
    assert out, f"ps gave no lstart for pid {pid}"
    return time.mktime(time.strptime(" ".join(out.split()), "%a %b %d %H:%M:%S %Y"))


def _run_seeing(script_name, proc, attempts=5):
    """Run the tool, retrying until it sees `proc`, and diagnose it if it never does.

    The bare form flaked once under load (74 tests in parallel with the launcher
    suite): the tool reported "nothing to check" for a pid `ps` had just shown.
    Retrying is only honest if the retry can also FAIL, so each attempt first
    establishes that the process is still alive — otherwise a test that killed its
    own subject would look like a tool that went blind, and vice versa.
    """
    last = None
    for _ in range(attempts):
        assert proc.poll() is None, (
            f"the fake launcher (pid {proc.pid}) exited with {proc.returncode} before "
            "the tool ran — this is the test's own subject dying, not a tool defect"
        )
        last = _run("--pattern", script_name)
        if f"pid {proc.pid}" in last.stdout:
            return last
        time.sleep(0.3)
    snap = subprocess.run(
        ["ps", "-axww", "-o", "pid=,ppid=,command="], capture_output=True, text=True
    ).stdout
    rows = [ln for ln in snap.splitlines() if script_name in ln]
    pytest.fail(
        f"tool never reported live pid {proc.pid}.\n"
        f"tool stdout: {last.stdout!r}\ntool stderr: {last.stderr!r}\n"
        f"ps rows carrying {script_name!r}: {rows}"
    )


def test_tool_parses():
    """A shell tool that does not parse is the one failure no arm below catches."""
    p = subprocess.run(["bash", "-n", str(TOOL)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_reports_current_when_the_file_predates_the_process(launcher):
    script, proc, started = launcher()
    # Unambiguously older than the process, without a sleep: lstart has one-second
    # granularity, so a 60s margin cannot be lost to truncation.
    _set_mtime(script, _start_epoch(proc.pid) - 60)

    p = _run_seeing(script.name, proc)

    assert "current" in p.stdout
    assert "STALE" not in p.stdout
    assert "1 current, 0 stale, 0 unknown" in p.stdout
    assert p.returncode == 0, f"exit {p.returncode}: {p.stdout}{p.stderr}"


def test_reports_stale_when_the_file_changed_after_the_process_started(launcher):
    script, proc, started = launcher()
    # Replaced by RENAME, not rewritten in place — which is both what a checkout
    # actually does and the only form that cannot truncate the file out from under
    # the bash process still reading it.
    new = script.with_suffix(".new")
    new.write_text(LOOP + "# text this running process cannot possibly hold\n")
    new.chmod(0o755)
    os.replace(new, script)
    _set_mtime(script, _start_epoch(proc.pid) + 60)

    p = _run_seeing(script.name, proc)

    assert "STALE" in p.stdout
    assert "restart it" in p.stdout
    assert "0 current, 1 stale, 0 unknown" in p.stdout
    # 1 is the result, not a harness story (gotcha #124) — a caller must be able
    # to gate on it, so this asserts the value and not merely "non-zero".
    assert p.returncode == 1, f"exit {p.returncode}: {p.stdout}{p.stderr}"


def test_same_second_counts_as_stale(launcher):
    """The ambiguous case resolves toward over-reporting.

    A false STALE costs a restart nobody needed; a false CURRENT is how a ship
    sits inert for four days.
    """
    script, proc, started = launcher()
    _set_mtime(script, _start_epoch(proc.pid))

    p = _run_seeing(script.name, proc)

    assert "STALE" in p.stdout, p.stdout
    assert p.returncode == 1


def test_a_matching_ancestor_is_still_reported(launcher, tmp_path):
    """The pgrep regression, guarded.

    `pgrep -f` excludes "the current pgrep or pkill process and all of its
    ancestors" (man pgrep, -a). A lane's runner IS its session's ancestor, so the
    first draft of this tool — run from a lane, as intended — reported every lane's
    runner except the one asking. It was blind to exactly the caller's own lane.
    """
    out = tmp_path / "from-inside.txt"
    name = f"fake-ancestor-{os.getpid()}.sh"
    body = (
        "#!/bin/bash\n"
        'touch "$1"\n'
        f'bash {TOOL} --pattern "$(basename "$0")" > {out} 2>&1\n'
        f'echo "EXIT:$?" >> {out}\n'
        "while true; do sleep 1; done\n"
    )
    script, proc, _ = launcher(body=body, name=name)

    deadline = time.time() + 30
    while time.time() < deadline and not (out.exists() and "EXIT:" in out.read_text()):
        time.sleep(0.2)
    text = out.read_text() if out.exists() else ""

    assert "EXIT:" in text, f"tool never finished from inside the launcher: {text!r}"
    assert f"pid {proc.pid}" in text, (
        "the tool did not report the launcher that is its own ancestor — "
        f"pgrep-style ancestor exclusion is back. got: {text!r}"
    )


def test_a_session_subshell_is_not_reported_twice(launcher):
    """A runner's session subshell shares both argv and the parsed AST.

    Reporting it separately would double every count and read as twice as many
    stale runners as exist.
    """
    body = (
        "#!/bin/bash\n"
        'touch "$1"\n'
        "( while true; do sleep 1; done ) &\n"
        "while true; do sleep 1; done\n"
    )
    script, proc, started = launcher(body=body)
    _set_mtime(script, _start_epoch(proc.pid) + 60)

    # PRECONDITION, asserted so this test cannot pass vacuously: if the subshell
    # does not actually show up in `ps` under the same argv, "reported exactly
    # one" would prove nothing at all.
    deadline = time.time() + 10
    matching = []
    while time.time() < deadline:
        snap = subprocess.run(
            ["ps", "-axww", "-o", "pid=,ppid=,command="], capture_output=True, text=True
        ).stdout.splitlines()
        matching = [ln for ln in snap if f"/{script.name}" in ln]
        if len(matching) >= 2:
            break
        time.sleep(0.2)
    assert len(matching) >= 2, (
        f"expected the launcher AND its subshell in ps, saw {len(matching)}: {matching}"
    )

    p = _run_seeing(script.name, proc)

    assert p.stdout.count(f"  {script.name}  ") == 1, p.stdout
    assert "0 current, 1 stale, 0 unknown" in p.stdout, p.stdout


def test_no_matching_process_says_so_and_exits_clean():
    """Silence must not read as "all current" — CI and an idle laptop hit this."""
    p = _run("--pattern", "no-such-launcher-abcdef123.sh")

    assert "no launcher processes running" in p.stdout, p.stdout
    assert "stale" not in p.stdout
    assert p.returncode == 0


def test_it_still_detects_staleness_under_gnu_stat_and_date(launcher, tmp_path):
    """The Linux defect, made reproducible on macOS.

    The tool probes BSD flags first and falls back to GNU. GNU `stat -f` is not
    "unknown flag" — it is *filesystem status*: it prints a multi-line block and
    then exits non-zero because `%m` was read as a filename. The `&&` chain
    correctly declines to return, but the block is already on stdout, so the
    caller captures garbage plus the real answer, the numeric comparison errors,
    and EVERY launcher reports `current`. Three CI runs died on this while every
    arm passed locally, because macOS takes the BSD branch and never sees it.

    These shims give macOS GNU's dialect, so the false-clean is catchable here.
    """
    bindir = tmp_path / "gnubin"
    bindir.mkdir()
    (bindir / "stat").write_text(
        "#!/bin/bash\n"
        # GNU: -c FMT file works; -f is filesystem status, prints, then fails.
        'if [ "$1" = "-c" ] && [ "$2" = "%Y" ]; then exec /usr/bin/stat -f %m "$3"; fi\n'
        'if [ "$1" = "-f" ]; then\n'
        '  echo "  File: \\"$3\\""\n'
        '  echo "    ID: 0 Namelen: 255 Type: apfs"\n'
        '  echo "Block size: 4096"\n'
        "  exit 1\n"
        "fi\n"
        "exit 1\n"
    )
    (bindir / "date").write_text(
        "#!/bin/bash\n"
        # GNU: no -j; -d parses a human string.
        'if [ "$1" = "-j" ]; then echo "date: invalid option -- j" >&2; exit 1; fi\n'
        'if [ "$1" = "-d" ]; then exec /bin/date -j -f "%a %b %d %T %Y" "$2" "$3"; fi\n'
        'exec /bin/date "$@"\n'
    )
    for f in ("stat", "date"):
        (bindir / f).chmod(0o755)

    script, proc, _ = launcher()
    _set_mtime(script, _start_epoch(proc.pid) + 60)
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"}

    p = subprocess.run(
        ["bash", str(TOOL), "--pattern", script.name],
        capture_output=True, text=True, env=env, timeout=60,
    )

    assert "STALE" in p.stdout, (
        "under GNU's stat/date dialect the tool failed to see a stale launcher — "
        f"a failed dialect probe is leaking into the answer. got: {p.stdout!r}"
    )
    assert "0 current, 1 stale, 0 unknown" in p.stdout, p.stdout
    assert p.returncode == 1


def test_an_unreadable_process_table_is_never_reported_as_a_clean_fleet(tmp_path):
    """The flake that found this: a `ps` that returns nothing must not read as "all current".

    With no guard, a failed or throttled `ps` empties the snapshot, every pattern
    matches nothing, and the tool exits 0 saying there is nothing to check — a
    false CURRENT, which is the single direction this tool exists to prevent. It
    must exit 2 (the check could not run) so a caller can tell it apart from a
    genuinely idle machine.
    """
    stub = tmp_path / "ps"
    stub.write_text("#!/bin/bash\nexit 1\n")
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}

    p = subprocess.run(
        ["bash", str(TOOL), "--pattern", "anything.sh"],
        capture_output=True, text=True, env=env, timeout=60,
    )

    assert p.returncode == 2, f"exit {p.returncode}: {p.stdout}{p.stderr}"
    assert "could not read the process table" in p.stderr, p.stderr
    assert "no launcher processes running" not in p.stdout, p.stdout


def test_a_bad_argument_exits_2_not_1():
    """2 is "the check could not run"; 1 is "a runner is stale". A caller that
    cannot tell them apart will read a typo as a clean fleet, or a stale fleet as
    a broken tool."""
    p = _run("--nonsense")
    assert p.returncode == 2, f"exit {p.returncode}: {p.stdout}{p.stderr}"

    p = _run("--pattern")
    assert p.returncode == 2, f"exit {p.returncode}: {p.stdout}{p.stderr}"
