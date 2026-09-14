#!/usr/bin/env python3
"""Read the clock in the same command as a master push — #4997, #6044.

**THE PUSH WINDOW IS RETIRED. THIS SCRIPT NO LONGER REFUSES ANYTHING ON THE
CLOCK.** What is left is the half of it that was never about the window: the
stamps come from one measurement taken immediately before the push, and ``exec``
hands the push straight to ``execvp`` so that stays true.

WHY THE WINDOW IS GONE, MEASURED RATHER THAN RELAYED
====================================================
Notice 29's :32–:50 restriction was retired by the coordinator on 2026-09-13 at
16:55 PT, after the attended scheduler move. The band existed for exactly one
mechanism: a main-app release cycled the celery beat that dispatches the :15
accuracy-page rebuild, so a release landing on the rebuild killed it. Beat no
longer runs on the main app.

Read from the deployed apps at 2026-09-14 02:41Z, one read, both apps:

  * ``bainluck`` runs web + worker-background + worker-realtime + worker-ws and
    **no scheduler dyno at all**. All four came up 02:35:2xZ under release
    **v4510** (``631384d0``, 02:34:57Z).
  * ``bainluck-heavy`` carries ``scheduler.1`` (``celery … beat``) beside
    ``worker-heavy.1``, **both up since 23:50:2xZ** — straight through that
    release, and through v4509 before it.

So the dispatcher and the executor of the thing this band protected both sit on
the app that main-app releases do not touch. The collision the guard refuses to
risk can no longer occur, and refusing costs the desk — which merges hourly — up
to 41 minutes of every hour for nothing.

Removed rather than left switchable: a band behind a flag is a band someone
re-enables from an old notice. The derivation is kept below as history, and
``test_push_window_guard_4997.py`` pins that it never comes back by accident.

WHAT THE RETIRED BAND WAS, FOR THE RECORD
=========================================
Derived, never asserted — rebuild start :15, min deploy lag 10, rebuild duration
~7 ⇒ opens :32; :15 + 60 − max deploy lag 20 − 5 margin ⇒ closes :50. Notice 29's
"(preferred :40–:52)" ran two minutes past its own hard band; that was residue
from the pre-amendment sentence, reported by authority/116. None of these numbers
is load-bearing any more. **If beat is ever moved back onto the main app, this is
the arithmetic to restore — with a fresh dyno census beside it, not from memory.**

WHY IT EXISTED
==============
authority/114 pushed master at **23:03:21Z** believing it was 23:39Z. CI finished
at 23:17:24Z, so the release cycled the dynos on top of the 23:15Z accuracy-page
rebuild — the exact collision notice 29 exists to prevent.

It had checked the window **three times** and got "inside" every time. It was
computing the current time by adding its own ``sleep`` durations to the session's
opening stamp. That arithmetic drifts one way only — **ahead**, because it omits
every tool call's own latency — so a window check computed that way **can never
tell you that you are outside the window**. It is a self-confirming instrument,
and it feels like diligence the whole time it is running.

That reasoning outlives the band it was written for. A stamp quoted into a ledger
or a merge message is navigated by later sessions (notice 24), so the constraint
is still: **make it structurally impossible to report a time you did not just
measure.**

  * ``exec`` reads the clock and then ``execvp``s the push itself. "Same command"
    becomes a property of the program instead of the operator's discipline.
  * **There is no way to hand the CLI a time.** The ``now`` seam the tests drive
    every branch through is a keyword argument on :func:`run`, unreachable from
    ``argv``. A ``--now`` flag would put back exactly the hole this closes.

WHAT IT STILL TELLS YOU
=======================
Whether the range forces a Heroku release — the deploy path's own answer
(``.github/scripts/heroku-release-required.sh``, #4456), not a guess from the
file list. That is no longer a gate, but it is what a desk wants to know: a
release-forcing merge owes a production check on the release line that carries
it, and a heavy-task change owes a ``bainluck-heavy`` line (notice 48).

Given no ``--before/--after`` it reports "assuming a release", the same asymmetry
that script documents about itself. It is now the cautious *label*, not a refusal.

USAGE
=====
::

    # the whole point — the clock read and the push are one command
    python3 scripts/push_window_guard.py exec --before "$BEFORE" --after "$AFTER" \
        -- git -c push.default=simple push origin master

    # just the report, without pushing
    python3 scripts/push_window_guard.py check --before "$BEFORE" --after "$AFTER"

Exit codes: ``0`` always for the report itself — there is no clock-based refusal
left (``exec`` then becomes the pushed command's own code); ``2`` usage.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

RELEASE_REQUIRED_SCRIPT = ".github/scripts/heroku-release-required.sh"

PACIFIC = ZoneInfo("America/Los_Angeles")

# The retirement this file enforces by having no band left to evaluate. Printed,
# so a desk that runs this out of muscle memory reads why it was not stopped —
# and dated, so the next reader can check it against the notice rather than
# trusting this line.
WINDOW_RETIRED_NOTE = (
    "push window: RETIRED 2026-09-13 16:55 PT (#6044). Notice 29's :32-:50 band "
    "protected the :15 accuracy rebuild from main-app releases cycling celery "
    "beat; beat now runs on bainluck-heavy, which those releases do not touch. "
    "Nothing here gates on the minute."
)


def _short(ref: str) -> str:
    """Abbreviate a sha, but never a ref name — `origin/ma..origin/ma` reads as a bug."""
    body = ref[:40]
    if len(body) >= 7 and all(c in "0123456789abcdef" for c in body.lower()):
        return body[:9]
    return ref


def release_required(before: str | None, after: str | None, repo: str = ".") -> tuple[bool, str]:
    """Ask the deploy path itself whether this range cycles the dynos.

    Returns ``(required, why)``. Every uncertain path returns ``True``: no range
    given, the script missing, a non-zero exit, an unparseable answer. This
    mirrors ``heroku-release-required.sh``'s own stated asymmetry — it fails
    toward releasing, so a reader built on it says "assume a release" rather than
    "no release" when it cannot tell. Since the window retired this decides a
    LABEL, not a refusal, and the asymmetry still points the safe way: being told
    to expect a release you do not get costs a glance at `heroku releases`, while
    the reverse leaves a production check unpaid.
    """
    if not before or not after:
        return True, "no --before/--after range given — assuming a release"
    path = os.path.join(repo, RELEASE_REQUIRED_SCRIPT)
    if not os.path.exists(path):
        return True, f"{RELEASE_REQUIRED_SCRIPT} not found — assuming a release"
    proc = subprocess.run(
        ["bash", path, before, after],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    answer = proc.stdout.strip().splitlines()[-1].strip() if proc.stdout.strip() else ""
    if proc.returncode != 0:
        return True, f"{RELEASE_REQUIRED_SCRIPT} exited {proc.returncode} — assuming a release"
    rng = f"{_short(before)}..{_short(after)}"
    if answer == "false":
        return False, f"{rng} changes nothing Heroku serves"
    if answer == "true":
        return True, f"{rng} forces a Heroku release"
    return True, f"{RELEASE_REQUIRED_SCRIPT} said {answer!r} — assuming a release"


def stamps(now: datetime) -> str:
    """Both stamps notice 24 asks for, from one measurement of one clock."""
    utc = now.astimezone(timezone.utc)
    return (
        f"{now.astimezone(PACIFIC).strftime('%a %Y-%m-%d %I:%M:%S%p PT').replace('AM', 'am').replace('PM', 'pm')}"
        f"  /  {utc.strftime('%H:%M:%SZ')}"
    )


def run(argv: list[str] | None = None, now: datetime | None = None) -> int:
    """Library entry point. ``now`` is the test seam and is NOT reachable from argv."""
    parser = argparse.ArgumentParser(
        prog="push_window_guard.py",
        description="Read the clock in the same command as a master push, and report "
        "whether the range forces a Heroku release. The :32-:50 push window is retired; "
        "this refuses nothing on the clock.",
    )
    parser.add_argument("mode", choices=["check", "exec"])
    parser.add_argument("--before", help="base sha of the range being pushed")
    parser.add_argument("--after", help="head sha of the range being pushed")
    parser.add_argument("--repo", default=".")
    parser.epilog = "for `exec`: -- followed by the push command to run"

    # Split on `--` by hand rather than with argparse.REMAINDER. REMAINDER starts
    # collecting at the first token it does not recognise as belonging to a
    # preceding option, which swallowed `--repo` and — worse — swallowed an
    # unknown `--now` instead of rejecting it. A guard whose whole purpose is to
    # refuse a supplied time must not have a parser that silently accepts one.
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        cut = argv.index("--")
        flags, command = argv[:cut], argv[cut + 1 :]
    else:
        flags, command = argv, []
    args = parser.parse_args(flags)

    if args.mode == "exec" and not command:
        parser.error("exec needs a command: ... exec -- git push origin master")

    # 🔴 The clock is read HERE, after argument parsing and immediately before the
    # push it is reported beside. Not at import, not by the caller, not passed in.
    now = now or datetime.now(timezone.utc)

    required, why = release_required(args.before, args.after, args.repo)

    print(f"push window guard — clock read now: {stamps(now)}")
    print(f"  release required: {'yes' if required else 'NO'} — {why}")
    print(f"  {WINDOW_RETIRED_NOTE}")
    if required:
        print(
            "🟢 GO — this range forces a release, so a production check is owed on the "
            "release line that carries it (and a bainluck-heavy line if it touches a "
            "heavy task, notice 48)."
        )
    else:
        print("🟢 GO — this range changes nothing Heroku serves, so no release follows.")

    if args.mode == "check":
        return 0

    print("   after it lands, quote the API's own date, not this one:")
    print(
        "   gh api repos/alexander-bain/bainluck/commits/<sha> --jq .commit.committer.date"
    )
    print(f"→ {' '.join(command)}")
    sys.stdout.flush()
    # execvp, not subprocess: the push inherits this process outright, so its exit
    # code is the caller's and there is no wrapper left to swallow a failure.
    os.execvp(command[0], command)
    raise AssertionError("unreachable: execvp does not return")  # pragma: no cover


if __name__ == "__main__":
    sys.exit(run())
