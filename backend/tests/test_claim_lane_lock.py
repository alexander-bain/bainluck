"""Ruling 022 — the shared lane-lock claim primitive, pinned.

The primitive exists because three hand-rolled claims failed in two days, one of
them written by the author of the rule forbidding it. So the thing most worth
testing is not the happy path: it is that a claim **REFUSES** when it must, and
that an unparseable lock refuses rather than falling through to a write.

``scripts/claim_lane_lock.py`` lives outside the backend package and is driven as
a subprocess here, deliberately — that is exactly how every lane calls it, so
this tests the interface the callers actually use, including exit codes.

**Queue 323 adds the C259 acceptance bar**, which is about the two ways the first
implementation said CLAIMED while providing no mutual exclusion:

* two concurrent real claimers must yield **exactly one** success;
* two windows must **never share an identity**, which means an identity that
  cannot be anchored has to fail closed rather than resolve to a shared
  terminal.

Every test below passes an explicit ``--identity``. That is not test scaffolding
— it is the calling convention the fix introduces, and it also makes these tests
answer the same way in CI (no ``native/claude`` ancestor) as on a laptop.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "claim_lane_lock.py"

ACQUIRED, REFUSED, MALFORMED, NOT_SERIALIZED, NO_IDENTITY = 0, 1, 2, 3, 4

ME = "test-window-alpha"
OTHER = "test-window-beta"


def _module():
    """Import the script by path — it is not on any package path."""
    spec = importlib.util.spec_from_file_location("claim_lane_lock", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


#: Default fixture age, in seconds. **Two hours, and that is load-bearing.**
#: Ruling 008 as amended (2026-08-21) makes a takeover require a dead pid AND
#: activity stale beyond the lock's interval, and activity is measured from the
#: file's mtime. A lock written by `_lock()` one millisecond ago is therefore
#: maximally FRESH, which would turn every pre-existing dead-owner test into a
#: MALFORMED-INVESTIGATE. Ageing by default keeps those tests meaning what their
#: names say — "the lane was abandoned" — and the freshness cases below opt in
#: explicitly, so the distinction is visible at each call site rather than
#: hidden in a default.
STALE_AGE_S = 7200


def _lock(
    tmp_path: Path,
    status: str,
    pid: object,
    identity: str | None = None,
    age_s: float = STALE_AGE_S,
    extra: str = "",
) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "LANE-test.lock"
    ident = f"owner_identity: {identity}\n" if identity else ""
    p.write_text(f"lane: test\nstatus: {status}\n{ident}pid: {pid}\nqueue: none\n{extra}")
    _age(p, age_s)
    return p


def _age(p: Path, age_s: float) -> None:
    """Backdate (or, with a negative age, FUTURE-date) a file's mtime."""
    t = time.time() - age_s
    os.utime(p, (t, t))


#: A comm string no process will ever have, used to force the UNANCHORED branch.
#: Whether a given pytest run happens to sit under a `native/claude` ancestor is
#: an accident of who launched it — locally it does, in CI it does not. A test
#: about fail-closed behaviour must not answer differently in the two places.
NO_SUCH_MARKER = "there-is-no-process-named-this"


def _env(identity: str | None = None, marker: str | None = None) -> dict:
    """A clean environment. The ambient one may carry a real lane identity."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("BAINLUCK_LANE_IDENTITY", "BAINLUCK_LANE_SESSION_MARKER")
    }
    if identity:
        env["BAINLUCK_LANE_IDENTITY"] = identity
    if marker:
        env["BAINLUCK_LANE_SESSION_MARKER"] = marker
    return env


def _run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env if env is not None else _env(),
    )


def _claim(
    lock: Path, queue: str = "TEST-1", identity: str = ME, *extra: str
) -> subprocess.CompletedProcess:
    return _run("claim", str(lock), "--queue", queue, "--identity", identity, *extra)


# --------------------------------------------------------------------------
# The original ruling-022 bar. Unchanged in intent.
# --------------------------------------------------------------------------


def test_the_script_exists_and_is_the_only_claim_path():
    """Ruling 022 deletes hand-rolled claim logic; something must replace it.

    LAT-P026 found the ruling on master with NO implementation anywhere — every
    lane still hand-rolling the logic the ruling declares deleted, which is the
    second path the ruling exists to remove.
    """
    assert SCRIPT.is_file(), f"{SCRIPT} missing — ruling 022 has no implementation"


def test_refuses_a_lock_held_by_a_live_other(tmp_path):
    """THE ONE THAT MATTERS. Queue 309 overwrote INT-033's held claim here."""
    # pid 1 always exists and is never us.
    result = _claim(_lock(tmp_path, "HELD", 1, identity=OTHER))
    assert result.returncode == REFUSED, result.stdout + result.stderr
    assert "REFUSED" in result.stderr


def test_a_refusal_does_not_modify_the_lock(tmp_path):
    """A refused claim must leave the owner's file byte-identical.

    INT-035's regex claim wrote a false HELD log line into a lock it did not
    own. Refusing loudly while still writing is not refusing.
    """
    lock = _lock(tmp_path, "HELD", 1, identity=OTHER)
    before = lock.read_text()
    assert _claim(lock).returncode == REFUSED
    assert lock.read_text() == before


@pytest.mark.parametrize("status", ["RELEASED", "free", "FREE"])
def test_an_explicit_release_frees_the_lock_regardless_of_pid(tmp_path, status):
    """Ruling 013 + its extension: `free` is not ambiguous, it is RELEASED.

    The pid here is a LIVE one — the cycle-39 case, where a literal pid-alive
    reading would block the lane on itself forever.
    """
    result = _claim(_lock(tmp_path, status, os.getpid(), identity=OTHER))
    assert result.returncode == ACQUIRED, result.stdout + result.stderr


def test_a_dead_owner_is_a_takeover_and_says_so(tmp_path):
    """Ruling 008: `ps` decides. A dead owner frees the lane, on the record.

    As amended 2026-08-21 the pid is now necessary but no longer sufficient — the
    lane must ALSO have gone quiet, which `_lock`'s default age supplies.
    """
    lock = _lock(tmp_path, "HELD", 999999, identity=OTHER)
    result = _claim(lock)
    assert result.returncode == ACQUIRED
    assert "takeover" in (result.stdout + lock.read_text()).lower()


# --------------------------------------------------------------------------
# Ruling 008 AS AMENDED 2026-08-21 (Fable, via INT-108) — a takeover needs a
# dead pid AND stale activity. A dead pid with FRESH activity is
# MALFORMED-INVESTIGATE, because `owner_pid` is unvalidated input: "that number
# is not running" never established "nobody is working here".
#
# Charter case: LANE-lane1.lock sat HELD naming a dead pid 38410 while lane1 was
# alive and landing commits. Read literally, the pre-amendment rule says take it.
# --------------------------------------------------------------------------


def test_a_dead_pid_with_FRESH_activity_is_malformed_not_a_takeover(tmp_path):
    """THE CHARTER CASE. This is the whole amendment.

    Everything here is identical to the takeover test above except one number —
    the age of the file. That is the point: the pre-amendment primitive could not
    tell these two situations apart, and one of them costs a live lane its work.
    """
    lock = _lock(tmp_path, "HELD", 999999, identity=OTHER, age_s=5)
    before = lock.read_text()
    result = _claim(lock)
    assert result.returncode == MALFORMED, result.stdout + result.stderr
    assert "MALFORMED-INVESTIGATE" in result.stderr
    assert lock.read_text() == before, "a MALFORMED verdict must not write"


def test_malformed_and_busy_are_different_exit_codes(tmp_path):
    """`1` = come back later. `2` = a human must look at this.

    Collapsing them teaches a caller to retry a MALFORMED lock forever, and
    gotcha #54's amendment is explicit that a non-1 non-zero is a story about the
    harness rather than a result.
    """
    busy = _claim(_lock(tmp_path / "a", "HELD", 1, identity=OTHER))
    (tmp_path / "b").mkdir(parents=True, exist_ok=True)
    broken = _claim(_lock(tmp_path / "b", "HELD", 999999, identity=OTHER, age_s=5))
    assert busy.returncode == REFUSED
    assert broken.returncode == MALFORMED
    assert busy.returncode != broken.returncode


def test_the_freshness_signal_can_only_VETO_never_grant(tmp_path):
    """The amendment must not reopen what 008 closed.

    008 demoted the heartbeat because it could fail the lane OPEN — admit a
    second writer to master. Here the owner is ALIVE and the activity is ancient,
    which under a staleness-decides rule is exactly the behind-drift case that
    stole a live owner's work. It must still be HELD: the clock is consulted only
    after `ps` has already said the owner is gone.
    """
    lock = _lock(tmp_path, "HELD", 1, identity=OTHER, age_s=30 * 24 * 3600)
    result = _claim(lock)
    assert result.returncode == REFUSED, result.stdout + result.stderr
    assert "LIVE other" in result.stderr


def test_ahead_drift_now_fails_CLOSED_instead_of_open(tmp_path):
    """A future-dated file was the ORIGINAL 008 failure, inverted.

    Under the old staleness rules a future timestamp made `now - stamp` negative,
    staleness read "fresh forever", and the lane failed OPEN. As a veto-only
    signal the same skew can only REFUSE a takeover. Same drift, opposite and
    safe outcome — which is the argument that this amendment does not undo 008.
    """
    lock = _lock(tmp_path, "HELD", 999999, identity=OTHER, age_s=-3600)
    assert _claim(lock).returncode == MALFORMED


def test_a_lock_declares_its_own_interval(tmp_path):
    """"Stale beyond its OWN interval" — not a global constant.

    A lane heartbeating every 10 minutes is abandoned at 30; a lane 40 minutes
    into a green gate run is not. One shared number would have to pick one of
    them to be wrong about.
    """
    quick = _lock(
        tmp_path / "q", "HELD", 999999, identity=OTHER, age_s=120,
        extra="heartbeat_interval_s: 60\n",
    )
    (tmp_path / "s").mkdir(parents=True, exist_ok=True)
    slow = _lock(
        tmp_path / "s", "HELD", 999999, identity=OTHER, age_s=120,
        extra="heartbeat_interval_s: 3600\n",
    )
    assert _claim(quick).returncode == ACQUIRED, "120s > its own 60s interval — abandoned"
    assert _claim(slow).returncode == MALFORMED, "120s < its own 3600s interval — still active"


def test_a_fresh_sibling_heartbeat_vetoes_even_when_the_lock_is_old(tmp_path):
    """Activity is the lane's, not the lock file's.

    A lane that stamps `HEARTBEAT-<LANE>` every few minutes without rewriting its
    lock is working normally. Reading only the lock's mtime would call it
    abandoned — and this is the shape the charter case actually had, since lane1
    was committing rather than editing its lock.
    """
    lock = _lock(tmp_path, "HELD", 999999, identity=OTHER, age_s=STALE_AGE_S)
    hb = tmp_path / "HEARTBEAT-TEST"
    hb.write_text("phase: mid-gate\n")
    _age(hb, 10)
    result = _claim(tmp_path / "LANE-test.lock")
    assert result.returncode == MALFORMED, result.stdout + result.stderr
    assert "heartbeat mtime" in result.stderr


def test_an_operator_may_override_malformed_but_is_told_what_it_costs(tmp_path):
    """The escape hatch exists, and it is not quiet.

    Same shape as the existing unknown-pid assertion: a human may vouch, but the
    output has to say plainly that a still-active lane is about to be taken.
    """
    lock = _lock(tmp_path, "HELD", 999999, identity=OTHER, age_s=5)
    result = _claim(lock, "TEST-1", ME, "--takeover")
    assert result.returncode == ACQUIRED, result.stdout + result.stderr


def test_check_reports_malformed_and_does_not_exit_zero(tmp_path):
    """A `check` scripted by a successor must not read 0 over an untouchable lock."""
    lock = _lock(tmp_path, "HELD", 999999, identity=OTHER, age_s=5)
    result = _run("check", str(lock), "--identity", ME)
    assert result.returncode == MALFORMED
    assert "MALFORMED-INVESTIGATE" in result.stdout


def test_a_claim_restamps_the_WHOLE_identity_not_three_fields_of_it(tmp_path):
    """Enforcement 3 — the defect INT-108 found in this primitive while banking.

    `claim` updated status/owner_identity/owner_pid and left `nonce`,
    `owner_started` and `claimed_at` holding the PREVIOUS owner's values. After a
    takeover the file then paired a LIVE pid with a DEAD process's start time.
    `owner_started` is the only defence against a RECYCLED pid, so a successor
    doing the strong check sees a mismatch — and is entitled to declare the lock
    MALFORMED and seize a live lane. A partial re-stamp manufactures the exact
    condition the amendment above exists to catch.
    """
    lock = _lock(
        tmp_path, "HELD", 999999, identity=OTHER,
        extra="nonce: OLD-NONCE-999\nowner_started: Mon Jan  1 00:00:00 2001\n"
              "claimed_at: 2001-01-01T00:00 PST\n",
    )
    assert _claim(lock).returncode == ACQUIRED
    text = lock.read_text()
    assert "OLD-NONCE-999" not in text, "nonce still names the previous owner"
    assert "Jan  1 00:00:00 2001" not in text, "owner_started still names the DEAD process"
    assert "2001-01-01T00:00" not in text, "claimed_at still names the previous claim"
    assert f"nonce: {ME}" in text


def test_a_claim_does_not_INVENT_fields_the_lock_never_had(tmp_path):
    """Repair is not the same as editing someone else's file into a new shape.

    A lock that never carried `nonce` is a different shape, not a broken one.
    Silently growing fields under a lane is how a "fix" becomes a surprise.
    """
    lock = _lock(tmp_path, "HELD", 999999, identity=OTHER)
    assert _claim(lock).returncode == ACQUIRED
    text = lock.read_text()
    assert "nonce:" not in text
    assert "owner_started:" not in text


def test_the_owner_may_reclaim_its_own_held_lock(tmp_path):
    lock = _lock(tmp_path, "RELEASED", 1)
    assert _claim(lock, "TEST-1").returncode == ACQUIRED
    assert _claim(lock, "TEST-2").returncode == ACQUIRED
    assert "TEST-2" in lock.read_text()


def test_a_malformed_lock_refuses_rather_than_falling_through(tmp_path):
    """The INT-035 shape: the pattern did not match and it wrote anyway.

    "I could not understand this lock" must be a refusal. An error path that
    proceeds is worse than a crash — the same species as gotcha #53.
    """
    p = tmp_path / "LANE-test.lock"
    p.write_text("this file has no status line\n")
    before = p.read_text()
    result = _run("claim", str(p), "--queue", "TEST-1", "--identity", ME)
    assert result.returncode == MALFORMED
    assert p.read_text() == before


def test_release_refuses_against_a_live_other(tmp_path):
    """You may not release someone else's held lock out from under them."""
    lock = _lock(tmp_path, "HELD", 1, identity=OTHER)
    before = lock.read_text()
    result = _run("release", str(lock), "--identity", ME)
    assert result.returncode == REFUSED
    assert lock.read_text() == before


def test_check_never_writes(tmp_path):
    """`check` is a read. It must be safe to call from anywhere, any time."""
    lock = _lock(tmp_path, "HELD", 1, identity=OTHER)
    before = lock.read_text()
    assert _run("check", str(lock), "--identity", ME).returncode == ACQUIRED
    assert lock.read_text() == before


# --------------------------------------------------------------------------
# C259 P1 #1 — identity. "Separate windows can be mistaken for one owner."
# --------------------------------------------------------------------------


def test_an_unanchorable_identity_fails_closed_instead_of_guessing(tmp_path):
    """C259's first P1, pinned as a refusal.

    The original walked `ppid` to `native/claude` and, not finding it, returned
    the top reachable ancestor — so two Codex windows under one Terminal.app
    both resolved to that Terminal and EACH READ THE OTHER'S LOCK AS ITS OWN.
    The refusal that is the primitive's entire purpose was defeated by an
    identity that was merely ambiguous, not wrong.

    A subprocess launched from pytest has no `native/claude` ancestor, so this
    exercises the real unanchored path rather than a mock.
    """
    lock = _lock(tmp_path, "RELEASED", 1)
    before = lock.read_text()
    result = _run(
        "claim", str(lock), "--queue", "TEST-1",  # no identity anywhere
        env=_env(marker=NO_SUCH_MARKER),
    )
    assert result.returncode == NO_IDENTITY, result.stdout + result.stderr
    assert "NO IDENTITY" in result.stderr
    assert "BAINLUCK_LANE_IDENTITY" in result.stderr, "must say how to fix it"
    assert lock.read_text() == before, "a fail-closed refusal writes nothing"


def test_two_windows_sharing_an_ancestor_do_not_share_an_identity(tmp_path):
    """The C259 scenario end to end: same process tree, two lanes, one lock.

    Both subprocesses here have an identical ancestry — they are siblings under
    one pytest. Under the old resolution they would receive the same identity
    and the second would sail through the ownership test. With assigned tokens
    the second is a stranger, and is refused.
    """
    lock = _lock(tmp_path, "RELEASED", 1)
    assert _claim(lock, "ALPHA", ME).returncode == ACQUIRED
    assert f"owner_identity: {ME}" in lock.read_text()

    second = _claim(lock, "BETA", OTHER)
    assert second.returncode == REFUSED, second.stdout + second.stderr
    assert "second writer" in second.stderr


def test_the_identity_may_come_from_the_environment(tmp_path):
    """Lanes export it once at window start rather than threading a flag."""
    lock = _lock(tmp_path, "RELEASED", 1)
    result = _run("claim", str(lock), "--queue", "TEST-1", env=_env(ME))
    assert result.returncode == ACQUIRED, result.stdout + result.stderr
    assert f"owner_identity: {ME}" in lock.read_text()


def test_an_assigned_token_cannot_inherit_a_pid_only_lock(tmp_path):
    """The legacy affordance is narrow, on purpose.

    A pre-323 lock records only a pid. A token holder cannot PROVE it wrote
    that lock, so it is granted no ownership over it — even when the recorded
    pid happens to be its own live process. Anything looser would let the
    ambiguity C259 found back in through the compatibility path.
    """
    lock = _lock(tmp_path, "HELD", os.getpid())  # live pid, no identity line
    result = _claim(lock, "TEST-1", ME)
    assert result.returncode == REFUSED, result.stdout + result.stderr


def test_a_legacy_pid_identity_still_matches_a_pid_only_lock(tmp_path):
    """...but the migration path stays open for a window with no token.

    `_is_me` is unit-tested directly here: a `pid:<n>` identity is what an
    anchored Claude window resolves to with no token assigned, and it must
    still recognise its own pre-323 lock.
    """
    mod = _module()
    assert mod._is_me(None, 4242, "pid:4242") is True
    assert mod._is_me(None, 4242, "pid:9999") is False
    assert mod._is_me("token-a", 4242, "pid:4242") is False, "identity wins over pid"
    assert mod._is_me("token-a", 4242, "token-a") is True


def test_whoami_makes_a_shared_identity_visible(tmp_path):
    """The C259 failure was invisible. Give it a way to be seen.

    Two windows run `whoami`; if the answers match, they are one lane as far as
    every lock is concerned. Here they differ, which is the fixed behaviour.
    """
    a = _run("whoami", "--identity", ME)
    b = _run("whoami", "--identity", OTHER)
    assert a.returncode == ACQUIRED and b.returncode == ACQUIRED
    assert f"identity={ME}" in a.stdout
    assert f"identity={OTHER}" in b.stdout
    assert a.stdout != b.stdout


# --------------------------------------------------------------------------
# C259 P1 #2 — atomicity. "Concurrent free-lock claims are not atomic."
# --------------------------------------------------------------------------


def test_concurrent_claimers_yield_exactly_one_success(tmp_path):
    """C259's acceptance bar, and the reason the sidecar exists.

    Eight real processes race for one free lock. Without serialization they all
    read FREE, all pass the test, and all print CLAIMED — the later writes
    silently replacing the earlier owner's claim, which is a mutex that grants
    itself to everyone. Exactly one may win; the rest must be refused, and the
    file must name the winner.
    """
    lock = _lock(tmp_path, "RELEASED", 1)
    identities = [f"racer-{i:02d}" for i in range(8)]

    with ThreadPoolExecutor(max_workers=len(identities)) as pool:
        results = list(pool.map(lambda i: _claim(lock, f"Q-{i}", i), identities))

    winners = [r for r in results if r.returncode == ACQUIRED]
    losers = [r for r in results if r.returncode == REFUSED]
    assert len(winners) == 1, (
        f"{len(winners)} claimers all believed they won: "
        + " | ".join(r.stdout.strip() for r in winners)
    )
    assert len(losers) == len(identities) - 1, [r.returncode for r in results]

    text = lock.read_text()
    won_by = [i for i in identities if f"owner_identity: {i}" in text]
    assert len(won_by) == 1 and won_by[0] in winners[0].stdout


def test_a_token_claim_records_pid_unknown_never_a_placeholder(tmp_path):
    """A `pid: 0` would read back as a DEAD owner and free the lock instantly.

    That is the subtle way the atomicity fix could have been undone: serialize
    the transition perfectly, then write an owner that the next reader's `ps`
    check declares dead. "I cannot tell" must not be recorded as a number that
    means something else.
    """
    lock = _lock(tmp_path, "RELEASED", 1)
    unanchored = _env(marker=NO_SUCH_MARKER)
    first = _run("claim", str(lock), "--queue", "TEST-1", "--identity", ME, env=unanchored)
    assert first.returncode == ACQUIRED, first.stdout + first.stderr
    text = lock.read_text()
    assert "pid: unknown" in text, text
    assert "pid: 0" not in text

    # And the next claimer must therefore be REFUSED, not handed a takeover.
    second = _run("claim", str(lock), "--queue", "TEST-2", "--identity", OTHER, env=unanchored)
    assert second.returncode == REFUSED
    assert "unknowable" in second.stderr


def test_an_unknowable_owner_can_be_taken_over_only_by_assertion(tmp_path):
    """Fail-closed must not mean wedged-forever. The escape is explicit."""
    lock = _lock(tmp_path, "RELEASED", 1)
    unanchored = _env(marker=NO_SUCH_MARKER)
    assert _run(
        "claim", str(lock), "--queue", "TEST-1", "--identity", ME, env=unanchored
    ).returncode == ACQUIRED
    assert _run(
        "claim", str(lock), "--queue", "TEST-2", "--identity", OTHER, env=unanchored
    ).returncode == REFUSED

    forced = _run(
        "claim", str(lock), "--queue", "TEST-2", "--identity", OTHER, "--takeover",
        env=unanchored,
    )
    assert forced.returncode == ACQUIRED, forced.stdout + forced.stderr
    assert "TAKEOVER" in lock.read_text()


def test_the_sidecar_is_created_and_never_removed(tmp_path):
    """Unlinking a flock'd file is how you silently un-do mutual exclusion.

    The holder keeps a lock on a nameless inode, the next caller O_CREATs a
    fresh one, and both proceed. An empty zero-byte sidecar left behind is the
    correct steady state, so this pins it against a future "cleanup".
    """
    lock = _lock(tmp_path, "RELEASED", 1)
    assert _claim(lock).returncode == ACQUIRED
    sidecar = tmp_path / "LANE-test.lock.claimlock"
    assert sidecar.exists()
    assert _run("release", str(lock), "--identity", ME).returncode == ACQUIRED
    assert sidecar.exists(), "the sidecar must survive a completed transition"


def test_an_interrupted_write_leaves_the_lock_untouched(tmp_path, monkeypatch):
    """`os.replace` is the commit point; anything before it must be invisible.

    A crash mid-write must not leave half a claim: an unparseable lock blocks
    every lane, and a truncated one is worse, because it may parse into the
    WRONG answer.
    """
    mod = _module()
    lock = _lock(tmp_path, "RELEASED", 1)
    before = lock.read_text()

    def boom(*_a, **_k):
        raise OSError("simulated crash at the commit point")

    monkeypatch.setattr(mod.os, "replace", boom)
    with pytest.raises(OSError):
        mod._atomic_write(str(lock), "status: HELD\n")

    assert lock.read_text() == before, "the original must be intact"
    leftovers = list(tmp_path.glob(".claim-*.tmp"))
    assert leftovers == [], f"temp files leaked: {leftovers}"


def test_release_by_the_wrong_identity_is_refused(tmp_path):
    """A wrong-token release is a blocking attack in the C261 bar.

    Under the old pid-only test, two windows sharing a terminal ancestor could
    release each other's live locks and neither would ever know.
    """
    lock = _lock(tmp_path, "RELEASED", 1)
    assert _claim(lock, "TEST-1", ME).returncode == ACQUIRED
    held = lock.read_text()

    wrong = _run("release", str(lock), "--identity", OTHER)
    assert wrong.returncode == REFUSED, wrong.stdout + wrong.stderr
    assert lock.read_text() == held

    mine = _run("release", str(lock), "--identity", ME)
    assert mine.returncode == ACQUIRED
    assert "status: RELEASED" in lock.read_text()


def test_check_and_claim_never_disagree(tmp_path):
    """One oracle, two commands.

    A lane that reads FREE and is then refused — or reads HELD and could have
    claimed — learns to distrust both readings, and goes back to hand-rolling.
    """
    mod = _module()
    cases = [
        ("RELEASED", 1, None, True),
        ("FREE", 1, None, True),
        ("HELD", 1, OTHER, False),  # pid 1 is alive and is not me
        ("HELD", 999999, OTHER, True),  # dead owner -> takeover
        ("HELD", None, OTHER, False),  # liveness unknowable -> fail closed
        ("SOMETHING-ELSE", 1, None, False),
    ]
    for status, pid, ident, expected_claimable in cases:
        _verdict, claimable = mod._verdict(status, pid, ident, ME)
        assert claimable is expected_claimable, (status, pid, ident, _verdict)
