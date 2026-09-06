"""`tools/stage-cert.sh` must not hand out a fresh id for a sha that is already
being graded.

CERT-2020 and CERT-2021 (lane1b/054, sha 1ff738bc) are the same commit staged
twice: the tool guarantees an unused *id* and never looked at the *sha*, so
re-running it after CI turned green produced a second block, and two bus
sessions claimed the two ids in the same minute. Two verdicts on one commit is
the state standing notices 12/17 exist to prevent.

The guard is deliberately narrow — it fires only when the existing block is
still LIVE — because this tool sits on every lane's critical path and must
never wedge the bus for a legitimate re-stage.
"""

import os
import signal
import subprocess
import threading
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "stage-cert.sh"

# Enough blocks that the id scan and the duplicate scan take real time, which is
# what opens the window two invocations race through. With a two-block queue the
# critical section is short enough that the pre-lock script looks correct most
# runs; the negative control below is what proves this width is sufficient.
RACE_QUEUE_BLOCKS = 400
RACE_TRIALS = 8

STAGED_SHA = "1ff738bce62df2b9eef6f685061f0235a1ffbd81"
DONE_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
FRESH_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _block(cert_id, status, sha):
    return (
        f"\n# CERT-{cert_id} -- SOME-SUBJECT-{cert_id}\n\n"
        f"queue_id: SOME-SUBJECT-{cert_id}\n"
        f"status: {status}\n"
        f"lane: lane1b\n"
        f"issue: #1\n"
        f"pr: https://example.invalid/pr\n"
        f"branch: lane1b/whatever\n"
        f"sha: {sha}\n\n"
        f"## Ship\nprose\n\nmore prose after a blank line\n"
    )


@pytest.fixture
def queue(tmp_path):
    q = tmp_path / "CERT-QUEUE.md"
    log = tmp_path / "CODEX-CERT-LOG.md"
    q.write_text(
        "# CERT QUEUE\n"
        + _block(100, "running", STAGED_SHA)
        + _block(101, "done", DONE_SHA)
    )
    log.write_text("# LEDGER\n")
    return q, log


def _stage(queue, sha, body="body\n", **env_extra):
    q, log = queue
    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(q.parent),
        "CERT_QUEUE": str(q),
        "CERT_LOG": str(log),
    }
    env.update(env_extra)
    return subprocess.run(
        [
            "bash", str(SCRIPT), "SUBJ", "lane1b", "lane1b/br", sha,
            "https://example.invalid/pr", "#1",
        ],
        input=body, capture_output=True, text=True, env=env,
    )


class TestRefusesALiveDuplicate:
    def test_a_sha_already_being_graded_is_refused(self, queue):
        r = _stage(queue, STAGED_SHA)
        assert r.returncode == 2, r.stdout + r.stderr
        assert "REFUSING" in r.stderr
        assert "CERT-100" in r.stderr, "the refusal must name the block it found"

    def test_the_refusal_appends_nothing(self, queue):
        """The property that actually matters: a refused stage leaves no
        half-written block and burns no id."""
        q, _ = queue
        before = q.read_text()
        _stage(queue, STAGED_SHA)
        assert q.read_text() == before

    def test_a_short_sha_still_collides_with_the_full_one(self, queue):
        r = _stage(queue, STAGED_SHA[:12])
        assert r.returncode == 2, "a 12-char sha names the same commit"
        assert "CERT-100" in r.stderr


class TestDoesNotWedgeTheBus:
    """Every one of these staged fine before the guard and must still."""

    def test_a_fresh_sha_is_staged(self, queue):
        q, _ = queue
        r = _stage(queue, FRESH_SHA)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "CERT-102"
        assert FRESH_SHA in q.read_text()

    def test_a_sha_whose_block_is_done_is_a_legitimate_restage(self, queue):
        """A second opinion or a re-arm on an already-graded sha is real work,
        and the guard must not be the thing that stops it."""
        r = _stage(queue, DONE_SHA)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "CERT-102"

    def test_the_override_is_honoured(self, queue):
        r = _stage(queue, STAGED_SHA, ALLOW_DUPLICATE_SHA="1")
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "CERT-102"

    def test_the_id_is_still_max_plus_one(self, queue):
        """Regression: the guard runs after the id scan and must not disturb
        it — CERT-1853 is what happens when that scan drifts."""
        q, _ = queue
        _stage(queue, FRESH_SHA)
        assert "# CERT-102 -- SUBJ" in q.read_text()

    def test_the_body_is_still_written_verbatim(self, queue):
        q, _ = queue
        _stage(queue, FRESH_SHA, body="## MY PRESENTATION\nline two\n")
        assert "## MY PRESENTATION\nline two\n" in q.read_text()


def _race_queue(tmp_path, name="CERT-QUEUE.md"):
    """A queue wide enough to have a real critical section."""
    q = tmp_path / name
    log = tmp_path / "CODEX-CERT-LOG.md"
    q.write_text(
        "# CERT QUEUE\n"
        + "".join(_block(200 + i, "done", f"{i:040x}") for i in range(RACE_QUEUE_BLOCKS))
    )
    log.write_text("# LEDGER\n")
    return q, log


def _run_two_at_once(script, q, log, sha, workdir):
    """Two invocations that enter the critical section together.

    Threads alone are not enough: `subprocess` spawn jitter is larger than the
    section we are trying to overlap, so each side is started first and made to
    spin on a file that appears only once both are already hot.
    """
    go = workdir / "go"
    runner = workdir / "runner.sh"
    runner.write_text(
        f'while [ ! -f "{go}" ]; do :; done\n'
        f'exec bash "{script}" SUBJ lane1b lane1b/br "{sha}" '
        f'https://example.invalid/pr "#1"\n'
    )
    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(workdir),
        "CERT_QUEUE": str(q),
        "CERT_LOG": str(log),
        # Long enough that the loser waits for the winner rather than timing out.
        "STAGE_CERT_LOCK_WAIT": "20",
    }
    results = {}

    def go_run(slot):
        results[slot] = subprocess.run(
            ["bash", str(runner)], input="body\n",
            capture_output=True, text=True, env=env,
        )

    threads = [threading.Thread(target=go_run, args=(i,)) for i in (0, 1)]
    for t in threads:
        t.start()
    # Both are spinning by now; release them into the section together.
    go.write_text("")
    for t in threads:
        t.join(timeout=60)
    return [results[0], results[1]]


def _tally(q, sha):
    text = q.read_text()
    sha_rows = sum(1 for ln in text.splitlines() if ln.strip() == f"sha: {sha}")
    ids = [ln.split()[1] for ln in text.splitlines() if ln.startswith("# CERT-")]
    return sha_rows, ids


class TestTheLockIsReal:
    """The duplicate-sha guard cannot see a block that has not been written yet.

    `flock 9 2>/dev/null || true` reads as a lock and is not one on a host with
    no `flock` — which is this one — so the id scan, the duplicate check and the
    append all ran unlocked and two invocations could interleave straight
    through the guard.
    """

    def test_two_synchronised_same_sha_invocations_produce_one_block(self, tmp_path):
        for trial in range(RACE_TRIALS):
            work = tmp_path / f"t{trial}"
            work.mkdir()
            q, log = _race_queue(work)
            before_ids = _tally(q, FRESH_SHA)[1]

            rs = _run_two_at_once(SCRIPT, q, log, FRESH_SHA, work)
            codes = sorted(r.returncode for r in rs)
            sha_rows, ids = _tally(q, FRESH_SHA)
            new_ids = [i for i in ids if i not in before_ids]

            assert codes == [0, 2], (
                f"trial {trial}: expected one success and one refusal, got {codes}\n"
                + "\n".join(r.stderr for r in rs)
            )
            assert sha_rows == 1, f"trial {trial}: {sha_rows} blocks for one sha"
            assert len(new_ids) == 1, f"trial {trial}: ids appended {new_ids}"
            assert len(set(new_ids)) == len(new_ids), "the same id was used twice"

    def test_a_held_lock_fails_closed_without_mutating(self, tmp_path):
        """The property that matters when the lock cannot be taken: refuse, and
        write nothing. A tool that proceeds on a failed acquisition is the
        unlocked tool with extra steps."""
        q, log = _race_queue(tmp_path)
        lockd = Path(str(q) + ".lockd")
        lockd.mkdir()
        (lockd / "pid").write_text(str(os.getpid()))
        before = q.read_text()

        r = _stage((q, log), FRESH_SHA, STAGE_CERT_LOCK_WAIT="1")

        assert r.returncode == 3, r.stdout + r.stderr
        assert "REFUSING" in r.stderr
        assert q.read_text() == before, "a refused acquisition must append nothing"

    def test_the_lock_is_released_so_the_next_stage_succeeds(self, tmp_path):
        """Fail-closed is only safe if the ordinary path always releases."""
        q, log = _race_queue(tmp_path)
        assert _stage((q, log), FRESH_SHA).returncode == 0
        assert not Path(str(q) + ".lockd").exists(), "lock survived a clean exit"
        # And a refusal path must release too, or one refusal wedges the bus.
        r = _stage((q, log), FRESH_SHA)
        assert r.returncode == 2, "second stage of a live sha is the dupe refusal"
        assert not Path(str(q) + ".lockd").exists(), "lock survived the refusal"


def _pre_repair_variant(src):
    """The script with the PRE-REPAIR trap shape restored.

    `trap _release_lock EXIT INT TERM HUP` — one handler for the exit and for
    every signal, installed only once the lock is held, and a release with no
    idempotency and no ownership check.
    """
    lines = src.splitlines(keepends=True)
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("_release_lock() {"):
            while not lines[i].startswith("}"):
                i += 1
            i += 1
            out.append(
                '_release_lock() {\n'
                '  [ -n "$_LOCK_HELD" ] || return 0\n'
                '  rm -f "$LOCKD/pid" 2>/dev/null\n'
                '  rmdir "$LOCKD" 2>/dev/null\n'
                '}\n'
            )
            continue
        if ln.rstrip() == "trap _release_lock EXIT" or ln.startswith("trap 'exit "):
            i += 1
            continue
        if ln.strip() == "_LOCK_HELD=1":
            out.append(ln)
            out.append("    trap _release_lock EXIT INT TERM HUP\n")
            i += 1
            continue
        out.append(ln)
        i += 1
    return "".join(out)


def _term_during_critical_section(script, workdir):
    """SIGTERM a run that is provably holding the lock, at a known point.

    Getting a signal to land INSIDE the critical section is otherwise a race:
    the section is ~0.15s even against the real 41k-line queue, and bash defers
    a trap until the current foreground command returns. Both problems are
    solved by making `CERT_LOG` a FIFO. The id scan opens it and blocks with the
    lock already taken, the TERM is delivered and held pending, and closing the
    writer end releases grep so the trap fires at a command boundary we chose.
    Deterministic, and no multi-megabyte fixture.
    """
    q = workdir / "Q.md"
    q.write_text("# Q\n")
    fifo = workdir / "log.fifo"
    os.mkfifo(fifo)
    lockd = Path(str(q) + ".lockd")

    p = subprocess.Popen(
        ["bash", str(script), "SUBJ", "lane1b", "lane1b/br", FRESH_SHA,
         "https://example.invalid/pr", "#1"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(workdir),
             "CERT_QUEUE": str(q), "CERT_LOG": str(fifo)},
    )
    time.sleep(0.4)
    held_during_scan = lockd.exists()
    p.send_signal(signal.SIGTERM)
    time.sleep(0.2)
    open(fifo, "w").close()
    out, _err = p.communicate(input="body\n", timeout=60)
    return {
        "held_during_scan": held_during_scan,
        "returncode": p.returncode,
        "stdout": out.strip(),
        "appended": len(q.read_text()) - len("# Q\n"),
        "orphan_lock": lockd.exists(),
    }


class TestASignalCannotResumeIntoTheCriticalSection:
    """A bash trap handler RESUMES where it left off unless it exits.

    So `trap _release_lock EXIT INT TERM HUP` dropped the lock on TERM and then
    carried on inside the section it no longer held — appending, printing a cert
    id and exiting 0. Signal traps now only `exit`; EXIT is the one cleanup path.
    """

    def test_a_term_holding_the_lock_fails_closed(self, tmp_path):
        r = _term_during_critical_section(SCRIPT, tmp_path)
        assert r["held_during_scan"], "probe never got the lock; it proves nothing"
        assert r["returncode"] != 0, "a terminated stage must not report success"
        assert r["returncode"] == 143, f"expected 128+SIGTERM, got {r['returncode']}"
        assert r["stdout"] == "", f"a terminated stage handed out id {r['stdout']!r}"
        assert r["appended"] == 0, "a terminated stage appended to the queue"
        assert not r["orphan_lock"], "the EXIT trap must still release the lock"

    def test_a_terminated_run_never_releases_a_successors_lock(self, tmp_path):
        """The release is ownership-checked, so no arrangement of traps can make
        one run delete a lock that belongs to another."""
        q, log = _race_queue(tmp_path)
        lockd = Path(str(q) + ".lockd")
        lockd.mkdir()
        (lockd / "pid").write_text("999999")  # a foreign holder

        p = subprocess.Popen(
            ["bash", str(SCRIPT), "SUBJ", "lane1b", "lane1b/br", FRESH_SHA,
             "https://example.invalid/pr", "#1"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path),
                 "CERT_QUEUE": str(q), "CERT_LOG": str(log),
                 "STAGE_CERT_LOCK_WAIT": "30"},
        )
        time.sleep(0.5)          # it is waiting on the foreign lock
        p.send_signal(signal.SIGTERM)
        p.communicate(timeout=60)

        assert p.returncode == 143
        assert lockd.exists(), "the terminated run removed a lock it did not own"
        assert (lockd / "pid").read_text() == "999999", "it rewrote a foreign lock"

    def test_the_pre_repair_trap_shape_really_did_resume_and_append(self, tmp_path):
        """Falsification. Without this, the two tests above would pass just as
        happily against a script that never handled the signal at all."""
        buggy = tmp_path / "stage-cert-pre-repair.sh"
        buggy.write_text(_pre_repair_variant(SCRIPT.read_text()))
        work = tmp_path / "w"
        work.mkdir()

        r = _term_during_critical_section(buggy, work)

        assert r["held_during_scan"]
        assert r["returncode"] == 0 and r["appended"] > 0, (
            "the pre-repair trap shape is supposed to survive its own TERM and "
            f"append anyway; got {r}"
        )
        assert r["stdout"].startswith("CERT-"), (
            "and hand out a cert id after termination — which is the defect "
            "CERT-2035 blocked on"
        )


class TestGuardIsNotVacuous:
    def test_without_the_guard_the_duplicate_would_have_been_staged(
        self, queue, tmp_path
    ):
        """Falsification: strip the refusal from a copy of the script and the
        same call succeeds. Without this, a guard that never fires and a guard
        that always passes look identical from the tests above.
        """
        stripped = tmp_path / "stage-cert-noguard.sh"
        src = SCRIPT.read_text()
        start = src.index('if [ "${ALLOW_DUPLICATE_SHA:-0}" != "1" ]; then')
        end = src.index("\nfi\n", start) + len("\nfi\n")
        stripped.write_text(src[:start] + src[end:])

        q, log = queue
        r = subprocess.run(
            [
                "bash", str(stripped), "SUBJ", "lane1b", "lane1b/br", STAGED_SHA,
                "https://example.invalid/pr", "#1",
            ],
            input="body\n", capture_output=True, text=True,
            env={
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "HOME": str(tmp_path),
                "CERT_QUEUE": str(q),
                "CERT_LOG": str(log),
            },
        )
        assert r.returncode == 0
        assert r.stdout.strip() == "CERT-102", (
            "the pre-guard tool stages a second block on a sha already being "
            "graded — which is exactly CERT-2020/CERT-2021"
        )

    def test_without_the_lock_the_same_race_really_does_double_stage(self, tmp_path):
        """Falsification for `TestTheLockIsReal`.

        A concurrency test that never had a window to fail through proves
        nothing — it would pass just as well against the unlocked script. So
        run the identical trials against a copy with the lock stripped out and
        require the failure to actually appear. If this ever stops finding a
        double-stage, the race test above has gone vacuous (the machine got
        faster, or the critical section got narrower) and `RACE_QUEUE_BLOCKS`
        must be widened rather than the assertion relaxed.
        """
        src = SCRIPT.read_text()
        start = src.index('LOCKD="$Q.lockd"')
        end = src.index("\ndone\n", start) + len("\ndone\n")
        unlocked = tmp_path / "stage-cert-nolock.sh"
        unlocked.write_text(src[:start] + src[end:])

        double_staged = 0
        for trial in range(RACE_TRIALS):
            work = tmp_path / f"u{trial}"
            work.mkdir()
            q, log = _race_queue(work)
            rs = _run_two_at_once(unlocked, q, log, FRESH_SHA, work)
            sha_rows, _ = _tally(q, FRESH_SHA)
            if sorted(r.returncode for r in rs) == [0, 0] or sha_rows > 1:
                double_staged += 1

        assert double_staged > 0, (
            f"{RACE_TRIALS} synchronised trials against the UNLOCKED script never "
            "produced a double stage, so the locked test above is not being "
            "exercised — widen RACE_QUEUE_BLOCKS"
        )
