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


def _lock(tmp_path: Path, status: str, pid: object, identity: str | None = None) -> Path:
    p = tmp_path / "LANE-test.lock"
    ident = f"owner_identity: {identity}\n" if identity else ""
    p.write_text(f"lane: test\nstatus: {status}\n{ident}pid: {pid}\nqueue: none\n")
    return p


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
    """Ruling 008: `ps` decides. A dead owner frees the lane, on the record."""
    lock = _lock(tmp_path, "HELD", 999999, identity=OTHER)
    result = _claim(lock)
    assert result.returncode == ACQUIRED
    assert "takeover" in (result.stdout + lock.read_text()).lower()


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
