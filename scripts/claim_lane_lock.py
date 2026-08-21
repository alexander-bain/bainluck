#!/usr/bin/env python3
"""The shared lane-lock claim primitive — ruling 022.

ONE implementation of READ -> TEST -> WRITE, consumed by every lane and by the
Integrator. Hand-rolled claim logic is deleted, not deprecated: a second path
that still works is a second path that still gets used, under time pressure, by
the lane that does not know this exists yet.

Why this file exists, in three failures inside two days:

* **Queue 309 overwrote INT-033's held claim** mid-gate-run, in good faith,
  obeying ruling 017's instruction to take the lock. Nothing told it that taking
  could be refused.
* **INT-035's regex claim** pattern-matched ``^status: RELEASED`` and appended a
  ``HELD`` line without reading the current value, against a lock held by a live
  Queue 310. The authoritative fields survived only because the pattern found
  nothing to replace. It was written by the author of the rule forbidding it,
  hours later. The mistake was never in the understanding.
* **A fresh latency window self-identified as INT-036 from ambient tree state**
  and proceeded with that authority, having claimed nothing.

Queue 323 — the C259 fast-follow — closes the two P1s a real-process audit found
in the first implementation. Both were cases where the primitive **reported
success while providing no mutual exclusion at all**:

1. **Shared fallback identity.** Identity walked ``ppid`` to ``native/claude``
   and, failing to find it, returned the top reachable ancestor. Two Codex
   windows launched from one Terminal.app therefore resolved to the SAME pid, so
   a lock HELD by one read as ``HELD BY ME`` to the other and the second-writer
   refusal — the entire reason the primitive exists — was defeated. Identity is
   now an **assigned token**, and an unresolvable identity **fails closed**
   instead of climbing to a shared GUI ancestor.
2. **A non-atomic claim.** ``_read`` -> test -> ``open(...,"w")`` had no
   ``flock``, no ``O_EXCL``, no compare-and-swap. Two callers could both read
   FREE, both pass the test, and both print ``CLAIMED``; the later write
   silently replaced the earlier owner. No amount of pid correctness fixes a
   read-modify-write race. The whole transition now runs under an exclusive OS
   file lock and lands via ``os.replace``.

Usage::

    python3 scripts/claim_lane_lock.py claim   <lock_path> --queue "INT-037" [--note "..."]
    python3 scripts/claim_lane_lock.py release <lock_path> [--note "..."]
    python3 scripts/claim_lane_lock.py check   <lock_path>
    python3 scripts/claim_lane_lock.py whoami

Identity, in precedence order: ``--identity TOKEN``, then
``$BAINLUCK_LANE_IDENTITY``, then ``pid:<session pid>`` **only when the session
pid was anchored on the ``native/claude`` marker**. With none of those, every
command that needs an identity refuses with exit 4 and says what to export. A
shared ancestor is not an identity.

Exit codes: ``0`` acquired/released/free, ``1`` REFUSED (held by a live other),
``2`` malformed lock, ``3`` could not serialize (another claim is in flight),
``4`` identity unavailable — fail closed. A refusal is a normal outcome, not an
error to retry past.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import errno
import fcntl
import os
import re
import subprocess
import sys
import tempfile
import time
from typing import Optional

#: The process name of a Claude Code session. Identity resolution anchors on it.
#: Overridable because not every caller runs under Claude Code — a CI job or a
#: different harness has no such ancestor, and the tests need to exercise the
#: unanchored branch deterministically rather than depending on who launched
#: them. An unset override is the normal case.
SESSION_COMM_MARKER = os.environ.get("BAINLUCK_LANE_SESSION_MARKER", "native/claude")

#: Env var carrying an explicitly assigned, unique-per-window identity token.
IDENTITY_ENV = "BAINLUCK_LANE_IDENTITY"

#: Appended to the lock path to get the serialization sidecar. NEVER unlinked —
#: see `_exclusive`.
SIDECAR_SUFFIX = ".claimlock"

#: How long to wait for the serialization sidecar before giving up. A claim is a
#: sub-second operation; anything longer means a wedged holder, and blocking
#: forever inside a lane's Phase 0 is its own outage.
SERIALIZE_TIMEOUT_S = 10.0

FREE_STATES = {"RELEASED", "FREE"}

#: Ruling 008 as AMENDED 2026-08-21: a takeover needs a dead pid AND activity
#: stale beyond the lock's own interval. A lock may declare its interval with a
#: `heartbeat_interval_s:` line; this is the fallback, set generously so that a
#: long green gate run never looks abandoned. Erring high fails CLOSED (refuses
#: a takeover), which is the direction 008 exists to protect.
DEFAULT_ACTIVITY_INTERVAL_S = 1800

ACQUIRED, REFUSED, MALFORMED, NOT_SERIALIZED, NO_IDENTITY = 0, 1, 2, 3, 4


class IdentityUnavailable(Exception):
    """Raised when no identity can be proven. Never resolved by guessing."""


def _ps_alive(pid: int) -> bool:
    """Ruling 008: `ps` is the whole test. Never the heartbeat."""
    return subprocess.run(
        ["ps", "-p", str(pid)], capture_output=True
    ).returncode == 0


def _ps_started(pid: int) -> Optional[str]:
    """`ps -o lstart` for a pid, or None. The defence against a RECYCLED pid.

    A pid is only unique among LIVE processes. `owner_pid` alone therefore cannot
    distinguish "the owner is still running" from "the owner died and the OS
    handed its number to something else". Pairing it with the start time makes
    the identity checkable, which is why a claim must re-stamp BOTH or neither.
    """
    r = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True
    )
    out = r.stdout.strip()
    return out or None


def _heartbeat_path(lock_path: str) -> Optional[str]:
    """`.../LANE-integrator.lock` -> `.../HEARTBEAT-INTEGRATOR`, if it exists."""
    base = os.path.basename(lock_path)
    m = re.match(r"^LANE-(.+)\.lock$", base)
    if not m:
        return None
    cand = os.path.join(os.path.dirname(lock_path), f"HEARTBEAT-{m.group(1).upper()}")
    return cand if os.path.exists(cand) else None


def _activity_age_s(lock_path: str) -> tuple[Optional[float], str]:
    """Seconds since this lane last DID something, and where that came from.

    Deliberately **mtime, not a written timestamp.** Ruling 008 demoted the
    heartbeat because it was a human-authored string that drifted in both
    directions; an mtime is written by the kernel on an actual write. This
    amendment may only ever VETO a takeover, so it must not reintroduce a signal
    a typo can forge.

    A future mtime (a skewed clock) yields age 0 — i.e. "fresh" — which REFUSES
    the takeover. Ahead-drift therefore fails CLOSED here, the exact inversion of
    the ahead-drift failure that 008 was written for.
    """
    newest, src = None, "none"
    for path, label in ((lock_path, "lock mtime"), (_heartbeat_path(lock_path), "heartbeat mtime")):
        if not path:
            continue
        try:
            mt = os.stat(path).st_mtime
        except OSError:
            continue
        if newest is None or mt > newest:
            newest, src = mt, label
    if newest is None:
        return None, src
    return max(0.0, time.time() - newest), src


def _declared_interval_s(text: str) -> int:
    """The lock's OWN interval, per the amendment. Not a global constant.

    A lane heartbeating every 10 minutes is stale at 30; a lane mid-way through a
    40-minute gate run is not. Letting each lock state its own cadence is what
    makes "stale beyond its own interval" a testable sentence.
    """
    m = re.search(r"(?m)^heartbeat_interval_s:\s*(\d+)", text)
    return int(m.group(1)) if m else DEFAULT_ACTIVITY_INTERVAL_S


def _comm(pid: int) -> str:
    out = subprocess.run(
        ["ps", "-o", "comm=", "-p", str(pid)], capture_output=True, text=True
    )
    return out.stdout.strip()


def _ppid(pid: int) -> Optional[int]:
    out = subprocess.run(
        ["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True
    )
    raw = out.stdout.strip()
    return int(raw) if raw.isdigit() else None


def session_pid() -> tuple[int, bool]:
    """Resolve the SESSION's pid, and say whether it is ANCHORED.

    The ruling-022 addendum as first written said "held by me requires
    ``owner_pid == $$``". **That is wrong for a Claude Code window and would
    never match.** Every Bash tool call runs in a FRESH SUBSHELL, so ``$$`` is a
    different number every time and never equals the long-lived session process.
    A lane testing ``owner_pid == $$`` can neither confirm nor refute its own
    identity: it would refuse its own valid lock, then "recover" by overwriting
    it — turning the guard into the very failure it was written to stop.

    So identity resolves by walking ``ppid`` up to the ``native/claude``
    ancestor, which outlives every subshell and is the thing a lock owner
    actually IS.

    **The second element of the return is what queue 323 adds, and it is the
    whole fix.** The original returned the top reachable ancestor when the
    marker was absent, calling that "honest". It is not honest, it is
    AMBIGUOUS: two Codex windows opened from one Terminal.app both walk to that
    same Terminal and receive the SAME identity, so each reads the other's HELD
    lock as its own. C259 reproduced exactly that against real process trees. An
    unanchored walk therefore returns ``anchored=False``, and callers must
    refuse rather than use it.
    """
    pid = os.getpid()
    seen: set[int] = set()
    while pid and pid not in seen and pid > 1:
        seen.add(pid)
        if SESSION_COMM_MARKER in _comm(pid):
            return pid, True
        parent = _ppid(pid)
        if parent is None or parent <= 1:
            break
        pid = parent
    return pid, False


def _valid_token(tok: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._:@+-]{3,120}", tok))


def resolve_identity(explicit: Optional[str] = None) -> tuple[str, Optional[int]]:
    """Return ``(identity, liveness_pid)``, or raise `IdentityUnavailable`.

    ``liveness_pid`` is what ``ps`` gets asked about. It is ``None`` for an
    assigned token whose window pid cannot be anchored, in which case liveness
    is unknowable and a HELD lock stays HELD — fail closed.
    """
    for source, tok in (
        ("--identity", explicit),
        (IDENTITY_ENV, os.environ.get(IDENTITY_ENV)),
    ):
        if tok:
            tok = tok.strip()
            if not _valid_token(tok):
                raise IdentityUnavailable(
                    f"{source} value {tok!r} is not a usable identity token "
                    f"(3-120 chars of [A-Za-z0-9._:@+-])."
                )
            pid, anchored = session_pid()
            return tok, (pid if anchored else None)

    pid, anchored = session_pid()
    if anchored:
        return f"pid:{pid}", pid

    raise IdentityUnavailable(
        "no assigned identity, and the session pid could not be anchored on "
        f"{SESSION_COMM_MARKER!r} — the walk ended at pid {pid}, which may be a "
        "terminal shared with other lane windows.\n"
        "Refusing to guess: two windows under one terminal would receive the "
        "SAME identity and each would read the other's HELD lock as its own "
        "(C259, reproduced against real process trees).\n"
        f'Assign one: export {IDENTITY_ENV}="<lane>-<window>-<unique>" '
        "or pass --identity."
    )


@contextlib.contextmanager
def _exclusive(lock_path: str, timeout: float = SERIALIZE_TIMEOUT_S):
    """Serialize the whole read-test-write against concurrent claimers.

    C259's second P1: without this, two callers both read FREE, both pass the
    test, and both report success — the later write silently replacing the
    earlier owner's claim.

    The sidecar is **never unlinked**, deliberately, and that is not laziness.
    Unlinking a flock'd file is the classic way to break the mutual exclusion it
    provides: the holder keeps a lock on an inode with no name, the next caller
    ``O_CREAT``s a *fresh* inode, and both proceed. "Stale sidecar cleanup" is an
    attack on this function, not a maintenance task. An empty zero-byte sidecar
    is the correct steady state.
    """
    sidecar = lock_path + SIDECAR_SUFFIX
    try:
        fd = os.open(sidecar, os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as exc:
        print(f"MALFORMED: cannot open {sidecar}: {exc}", file=sys.stderr)
        sys.exit(MALFORMED)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                    raise
                if time.monotonic() >= deadline:
                    print(
                        f"NOT SERIALIZED: another claim has held {sidecar} for "
                        f"{timeout:g}s. Someone else is mid-transition, or a "
                        f"process is wedged. Nothing was written.",
                        file=sys.stderr,
                    )
                    sys.exit(NOT_SERIALIZED)
                time.sleep(0.02)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _atomic_write(path: str, text: str) -> None:
    """Replace `path` with `text` in one step, or leave it entirely untouched.

    A crash, a SIGKILL, or a full disk partway through must not leave a lock
    file that is half a claim — an unparseable lock blocks every lane, and a
    truncated one is worse still because it may parse into the wrong answer. The
    temp file lands in the same directory, so ``os.replace`` is a rename within
    one filesystem, which POSIX makes atomic.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".claim-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _read(path: str) -> tuple[str, str, Optional[int], Optional[str], re.Match]:
    try:
        text = open(path).read()
    except OSError as exc:
        print(f"MALFORMED: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(MALFORMED)
    # `.*$` is LOAD-BEARING, not tidiness (ruling 071). The old pattern was
    # `^status:\s*(\S+)` — it matched only the FIRST TOKEN, so `m.end()` stopped
    # there and both writers below did
    #     text[:m.start()] + "status: NEW   # stamp." + text[m.end():]
    # which re-appended everything already on that line. Every release therefore
    # COMPOUNDED the status line instead of replacing it. Measured 2026-08-16:
    # LANE-calibration.lock at 12 `status:` lines, LANE-lane1.lock at 6, and
    # LANE-latency.lock carrying ~35 stamps welded onto a single line. Ruling 071
    # makes such a file MALFORMED and therefore read as HELD, so this one regex
    # was quietly fencing lanes out of their own work.
    m = re.search(r"(?m)^status:\s*(\S+).*$", text)
    if not m:
        print(f"MALFORMED: no `status:` line in {path}", file=sys.stderr)
        sys.exit(MALFORMED)
    # Ruling 071: more than one `status:` or `owner_pid:` line is MALFORMED and
    # reads as HELD, fail-safe. Refuse rather than guess which line is the truth.
    if len(re.findall(r"(?m)^status:", text)) > 1:
        print(
            f"MALFORMED: {path} has {len(re.findall(r'(?m)^status:', text))} `status:` "
            "lines. Ruling 071: a lock with more than one is MALFORMED and reads as "
            "HELD. Repair belongs to the OWNER while its pid is alive. Collapse it to "
            "one `status:` line with the history BELOW it, then retry.",
            file=sys.stderr,
        )
        sys.exit(MALFORMED)
    if len(re.findall(r"(?m)^owner_pid:", text)) > 1:
        print(
            f"MALFORMED: {path} has multiple `owner_pid:` lines (ruling 071).",
            file=sys.stderr,
        )
        sys.exit(MALFORMED)
    pm = re.search(r"(?m)^(?:owner_)?pid:\s*(\d+)", text)
    im = re.search(r"(?m)^owner_identity:\s*(\S+)", text)
    return (
        text,
        m.group(1).upper().rstrip(","),
        (int(pm.group(1)) if pm else None),
        (im.group(1) if im else None),
        m,
    )


def _is_me(owner_identity: Optional[str], owner_pid: Optional[int], me: str) -> bool:
    """Ownership is an EXACT identity match, and nothing weaker.

    A lock written before queue 323 carries no ``owner_identity``. Then, and
    only then, a ``pid:<n>`` identity may match the recorded pid — that is the
    one legacy affordance, and it is deliberately unavailable to assigned
    tokens: a token holder facing a pid-only lock **cannot prove ownership**, so
    it is granted none.
    """
    if owner_identity is not None:
        return owner_identity == me
    if owner_pid is not None and me.startswith("pid:"):
        return me == f"pid:{owner_pid}"
    return False


def _stamp() -> str:
    return datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M %Z")


def _identity_or_exit(args) -> tuple[str, Optional[int]]:
    try:
        return resolve_identity(getattr(args, "identity", None))
    except IdentityUnavailable as exc:
        print(f"NO IDENTITY: {exc}", file=sys.stderr)
        sys.exit(NO_IDENTITY)


def _verdict(
    status: str,
    owner: Optional[int],
    owner_identity: Optional[str],
    me: str,
    takeover_ok: bool = False,
    activity_age_s: Optional[float] = None,
    activity_src: str = "none",
    interval_s: int = DEFAULT_ACTIVITY_INTERVAL_S,
) -> tuple[str, bool]:
    """Return ``(human verdict, claimable)``.

    ONE oracle, shared by `check` and `claim`, so the two can never disagree
    about the same lock — a lane that reads "FREE" and is then refused, or vice
    versa, learns to distrust both.
    """
    alive = _ps_alive(owner) if owner else False
    if status in FREE_STATES:
        return "FREE (explicitly released)", True
    if status == "HELD" and _is_me(owner_identity, owner, me):
        return "HELD BY ME", True
    if status == "HELD" and owner is None:
        # An owner whose pid is UNKNOWN is not an owner who is dead. `ps` has no
        # answer here, so the lock stays HELD and only an operator asserting
        # `--takeover` may break it. The alternative — treating "I cannot tell"
        # as "it is free" — is the gotcha-#53 shape: an error path resolving to
        # the reassuring reading.
        if takeover_ok:
            return (
                "TAKEOVER ASSERTED over an owner with no recorded pid (liveness "
                "was unknowable; an operator vouched for it)",
                True,
            )
        return (
            "HELD by an owner with no recorded pid — liveness unknowable, treat "
            "as HELD (pass --takeover to assert otherwise)",
            False,
        )
    if status == "HELD" and alive:
        who = owner_identity or f"pid {owner}"
        return f"HELD by a LIVE other ({who}, pid {owner})", False
    if status == "HELD":
        # Ruling 008 AS AMENDED 2026-08-21 (Fable, via INT-108). A dead pid is
        # NO LONGER SUFFICIENT. `owner_pid` is an unvalidated hand-written field,
        # so "that number is not running" does not establish "nobody is working
        # here" — the charter case was LANE-lane1.lock naming a dead 38410 while
        # lane1 was alive and landing commits. Require the second, independent
        # signal: the lane has also gone QUIET.
        #
        # This does not undo what 008 closed. The clock can only ever REFUSE here
        # (a fresh reading blocks a takeover); it can never grant one, because a
        # live pid has already returned HELD above. Both drift directions
        # therefore fail closed.
        if activity_age_s is not None and activity_age_s < interval_s:
            if takeover_ok:
                return (
                    f"🔴 MALFORMED-INVESTIGATE OVERRIDDEN — dead pid {owner} but "
                    f"{activity_src} is only {activity_age_s:.0f}s old (< {interval_s}s "
                    "interval). An operator asserted --takeover over a lane that "
                    "still looks ACTIVE. If a live lane loses its work, this is why.",
                    True,
                )
            return (
                f"🔴 MALFORMED-INVESTIGATE (ruling 008 as amended): owner pid {owner} "
                f"is DEAD but {activity_src} is only {activity_age_s:.0f}s old, inside "
                f"this lock's own {interval_s}s interval. A dead pid with fresh "
                "activity is a lock naming the WRONG pid, not an abandoned lane. "
                "TAKE NOTHING. Find the live owner and have it re-stamp owner_pid "
                "(and owner_started). Say so loudly in your report — ruling 071: a "
                "malformed lock reads as HELD.",
                False,
            )
        aged = (
            f"{activity_src} {activity_age_s:.0f}s old, past this lock's {interval_s}s interval"
            if activity_age_s is not None
            else "no activity signal available"
        )
        return f"FREE (owner pid {owner} is dead; {aged} — takeover, record it)", True
    return f"UNKNOWN status {status!r} — treat as HELD and stop", False


def cmd_whoami(args) -> int:
    """Print this window's resolved identity. Diagnostic; writes nothing.

    Worth having as a first-class command: the C259 failure was two windows
    silently sharing one identity, which nobody could SEE. Run it in both
    windows; if the answers match, they are one lane as far as every lock is
    concerned.
    """
    pid, anchored = session_pid()
    try:
        me, live_pid = resolve_identity(getattr(args, "identity", None))
    except IdentityUnavailable as exc:
        print(f"NO IDENTITY: {exc}", file=sys.stderr)
        return NO_IDENTITY
    source = (
        "--identity"
        if getattr(args, "identity", None)
        else IDENTITY_ENV
        if os.environ.get(IDENTITY_ENV)
        else "session-pid"
    )
    print(
        f"identity={me} liveness_pid={live_pid} session_pid={pid} "
        f"anchored={anchored} source={source}"
    )
    return ACQUIRED


def cmd_check(args) -> int:
    text, status, owner, owner_identity, _ = _read(args.lock)
    me, _live = _identity_or_exit(args)
    alive = _ps_alive(owner) if owner else False
    age, src = _activity_age_s(args.lock)
    interval = _declared_interval_s(text)
    verdict, claimable = _verdict(
        status, owner, owner_identity, me,
        activity_age_s=age, activity_src=src, interval_s=interval,
    )
    print(
        f"status={status} owner_identity={owner_identity} owner_pid={owner} "
        f"alive={alive} activity={'%.0fs' % age if age is not None else 'unknown'}"
        f"({src}) interval={interval}s me={me} -> {verdict}"
    )
    # A `check` that reports MALFORMED must not exit 0. Gotcha #54's amendment:
    # `1` is a result, anything else is a story about the harness — and this IS a
    # story about the harness. A reader scripting `check` would otherwise get a
    # clean exit over a lock that must not be touched.
    if not claimable and verdict.startswith("🔴 MALFORMED"):
        return MALFORMED
    return ACQUIRED


def cmd_claim(args) -> int:
    me, live_pid = _identity_or_exit(args)

    # Everything from here to the write is ONE serialized transition. Two
    # concurrent claimers on a free lock now yield exactly one CLAIMED: the
    # loser blocks here, then re-reads and finds the winner's HELD.
    with _exclusive(args.lock):
        text, status, owner, owner_identity, m = _read(args.lock)

        # --- TEST, before any write. This is the whole ruling. ---
        # Read activity BEFORE the write, or the write itself makes the lock look
        # fresh and every takeover self-vetoes.
        age, src = _activity_age_s(args.lock)
        verdict, claimable = _verdict(
            status, owner, owner_identity, me,
            takeover_ok=getattr(args, "takeover", False),
            activity_age_s=age, activity_src=src,
            interval_s=_declared_interval_s(text),
        )
        if not claimable:
            print(
                f"REFUSED: {verdict}. You are the second writer (me={me}). "
                f"Stop and say so — do NOT overwrite.",
                file=sys.stderr,
            )
            # Two refusals, two exit codes, because they are two different facts.
            # `1` = "the lane is legitimately busy, come back later". `2` = "this
            # lock does not make sense, a human must look at it". Collapsing them
            # teaches a caller to retry a MALFORMED lock forever.
            return MALFORMED if verdict.startswith("🔴 MALFORMED") else REFUSED

        takeover = status == "HELD" and not _is_me(owner_identity, owner, me)
        stamp = _stamp()

        # --- WRITE, only now, and all at once. ---
        # `pid: unknown` when the window could not be anchored, NEVER a
        # placeholder integer. A `pid: 0` would be read back by the next
        # claimer as a dead owner and the lock would free itself instantly —
        # re-opening the exact race the sidecar was added to close.
        new = text[: m.start()] + f"status: HELD   # {stamp} — {args.queue}." + text[m.end():]
        new = re.sub(
            r"(?m)^(owner_)?pid:.*$",
            lambda mo: f"{mo.group(1) or ''}pid: {live_pid if live_pid is not None else 'unknown'}",
            new,
            count=1,
        )
        if re.search(r"(?m)^owner_identity:", new):
            new = re.sub(r"(?m)^owner_identity:.*$", f"owner_identity: {me}", new, count=1)
        elif re.search(r"(?m)^(owner_)?pid:.*$", new):
            # Anchor it beside the pid, so a human reads the two together.
            new = re.sub(
                r"(?m)^((owner_)?pid:.*)$",
                lambda mo: f"owner_identity: {me}\n{mo.group(1)}",
                new,
                count=1,
            )
        else:
            new = new[: m.start()] + f"owner_identity: {me}\n" + new[m.start():]
        new = re.sub(r"(?m)^queue:.*$", f"queue: {args.queue}", new, count=1)

        # --- RE-STAMP THE WHOLE IDENTITY, not three fields of it. ---
        # Ruling 008 as amended, enforcement 3. Until INT-108 this writer updated
        # `status`, `owner_identity` and `owner_pid` and left `nonce`,
        # `owner_started` and `claimed_at` holding the PREVIOUS owner's values.
        # After a takeover the file then paired a LIVE pid with a DEAD process's
        # start time — and `owner_started` is the only thing that catches a
        # recycled pid, so the next reader doing the strong check sees a mismatch
        # and is entitled to call the lock MALFORMED and seize a live lane.
        # A partial re-stamp manufactures the precise condition the amendment
        # exists to catch. Found by INT-108 on its own claim, one minute after
        # banking the ruling.
        started = _ps_started(live_pid) if live_pid is not None else None
        for field, value in (
            ("nonce", me),
            ("owner_started", f"{started}  (durable `{SESSION_COMM_MARKER}` session process, "
                              "NOT a subshell)" if started else "unknown"),
            ("claimed_at", stamp),
        ):
            if re.search(rf"(?m)^{field}:", new):
                new = re.sub(rf"(?m)^{field}:.*$", f"{field}: {value}", new, count=1)
        # Absent fields are NOT invented. A lock that never carried `nonce` is a
        # different shape, not a broken one, and silently growing fields under a
        # lane is how a "repair" becomes an edit to someone else's file.

        line = (
            f"- {stamp} — **HELD** by {args.queue}, identity {me}, "
            f"pid {live_pid if live_pid is not None else 'unknown'} "
            f"(claimed via scripts/claim_lane_lock.py)."
        )
        if takeover:
            line += (
                f" **TAKEOVER** of {owner_identity or 'an unnamed owner'}: prior owner pid "
                + (f"{owner} was dead." if owner is not None else "was unknown; --takeover asserted.")
            )
        if args.note:
            line += f" {args.note}"
        new += line + "\n"
        _atomic_write(args.lock, new)

    print(
        f"CLAIMED {args.queue} identity={me} pid={live_pid}"
        + (" (takeover)" if takeover else "")
    )
    return ACQUIRED


def cmd_release(args) -> int:
    me, live_pid = _identity_or_exit(args)

    with _exclusive(args.lock):
        text, status, owner, owner_identity, m = _read(args.lock)

        # A release by the WRONG IDENTITY must be refused — not merely a release
        # by a different pid. Under the old pid-only test, two windows sharing a
        # terminal ancestor could release each other's live locks and neither
        # would ever know. Liveness that cannot be established fails closed.
        cleanup = status == "HELD" and not _is_me(owner_identity, owner, me)
        if cleanup:
            unknown_liveness = owner is None
            if unknown_liveness or _ps_alive(owner):
                who = owner_identity or f"pid {owner}"
                print(
                    f"REFUSED: will not release a lock HELD by {who} (me={me}"
                    + (", liveness unknowable" if unknown_liveness else ", ALIVE")
                    + "). Only the owner may release it.",
                    file=sys.stderr,
                )
                return REFUSED

        stamp = _stamp()
        new = text[: m.start()] + f"status: RELEASED   # {stamp}." + text[m.end():]
        line = f"- {stamp} — **RELEASED** by identity {me} (pid {live_pid})."
        if cleanup:
            line += (
                f" **CLEANUP of a DEAD owner** "
                f"({owner_identity or 'unknown identity'}, pid {owner}) — not my own claim."
            )
        if args.note:
            line += f" {args.note}"
        new += line + "\n"
        _atomic_write(args.lock, new)

    print(
        f"RELEASED identity={me} pid={live_pid}"
        + (" (cleanup of a dead owner)" if cleanup else "")
    )
    return ACQUIRED


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("claim", "release", "check"):
        s = sub.add_parser(name)
        s.add_argument("lock")
        s.add_argument("--note", default="")
        s.add_argument(
            "--identity", default=None, help="assigned unique identity token for this window"
        )
        if name == "claim":
            s.add_argument("--queue", required=True)
            s.add_argument(
                "--takeover",
                action="store_true",
                help="assert a takeover over an owner whose liveness cannot be established",
            )
    w = sub.add_parser("whoami")
    w.add_argument("--identity", default=None)
    args = ap.parse_args()
    return {
        "claim": cmd_claim,
        "release": cmd_release,
        "check": cmd_check,
        "whoami": cmd_whoami,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
