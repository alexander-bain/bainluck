#!/usr/bin/env python3
"""Refuse a master push that would land a Heroku release on the rebuild — #4997.

Standing notice 29, amended Thu 2026-09-10: the window check is the clock read
in the SAME command as the push, never computed from sleeps or an opening stamp.
This is that rule as a program, for the same reason
``scripts/cert_merge_eligibility.py`` is a program: a paragraph is not a check.

WHY IT EXISTS
=============
authority/114 pushed master at **23:03:21Z** believing it was 23:39Z. CI finished
at 23:17:24Z, so the release cycled the dynos on top of the 23:15Z accuracy-page
rebuild — the exact collision notice 29 exists to prevent.

It had checked the window **three times** and got "inside" every time. It was
computing the current time by adding its own ``sleep`` durations to the session's
opening stamp. That arithmetic drifts one way only — **ahead**, because it omits
every tool call's own latency — so a window check computed that way **can never
tell you that you are outside the window**. It is a self-confirming instrument,
and it feels like diligence the whole time it is running.

So the design constraint is not "check the clock". It is: **make it structurally
impossible to act on a time you did not just measure.**

  * ``exec`` reads the clock and then ``execvp``s the push itself. "Same command"
    becomes a property of the program instead of the operator's discipline.
  * **There is no way to hand the CLI a time.** The ``now`` seam the tests drive
    every branch through is a keyword argument on :func:`run`, unreachable from
    ``argv``. A ``--now`` flag would put back exactly the hole this closes.

WHY IT DOES NOT REFUSE EVERY PUSH
=================================
Notice 29 binds the **release**, not the push, and a frontend-only merge releases
nothing (#4456; ``.github/scripts/heroku-release-required.sh``). Those are ~13 of
the day's pushes. A guard that refuses them is a guard lanes learn to skip, and a
skipped guard protects nothing — so given ``--before/--after`` this asks that
script and passes a no-release range at any minute of the hour.

Given no range it **assumes a release**, which is the same asymmetry that script
documents about itself: a missed refusal kills a two-hour rebuild, a redundant one
costs a wait.

THE NUMBERS, AND THE ONE THAT IS RESIDUE
========================================
Notice 29 derives the band rather than asserting it, so this file derives it too —
change a constant, not a literal, when the deploy lag moves:

    earliest = rebuild start :15 + min deploy lag 10 + rebuild duration ~7 = :32
    latest   = rebuild start :15 + 60 - max deploy lag 20 = :55, - 5 margin = :50

Notice 29's own text then adds "(preferred :40–:52)", which runs two minutes past
its own hard band. That is residue from the pre-amendment sentence, where :40–:52
described when to take a *merge* slot; the amendment redefined the band as a
*push* window. **:32–:50 is the operative sentence.** Reported to Fable-5 by
authority/116 — recorded here so nobody restores the wider band from the notice.

USAGE
=====
::

    # the whole point — the clock read and the push are one command
    python3 scripts/push_window_guard.py exec --before "$BEFORE" --after "$AFTER" \
        -- git -c push.default=simple push origin master

    # just the verdict (exit 0 inside / 1 outside), e.g. to decide how long to sleep
    python3 scripts/push_window_guard.py check --after "$SHA"

Exit codes: ``0`` inside the window (``exec`` then becomes the pushed command's
own code), ``1`` outside — a RESULT, not an error (gotcha #124), ``2`` usage.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# The accuracy-page rebuild this guard is protecting: starts :15 past the hour and
# runs about 7 minutes (integrator/291, measured 3-for-3 on 2026-09-10).
REBUILD_START_MIN = 15
REBUILD_DURATION_MIN = 7
# Push -> production, CI-queue dependent. Never assume the low end: integrator/291's
# own batch G took 19.5 minutes.
MIN_DEPLOY_LAG_MIN = 10
MAX_DEPLOY_LAG_MIN = 20
# Slack on the closing edge, so a lag at the top of the measured range still lands
# clear of the next hour's rebuild.
CLOSE_MARGIN_MIN = 5

RELEASE_REQUIRED_SCRIPT = ".github/scripts/heroku-release-required.sh"

PACIFIC = ZoneInfo("America/Los_Angeles")


def window_bounds() -> tuple[int, int]:
    """The (open, close) minutes past the hour, derived — never asserted."""
    opens = REBUILD_START_MIN + MIN_DEPLOY_LAG_MIN + REBUILD_DURATION_MIN
    closes = REBUILD_START_MIN + 60 - MAX_DEPLOY_LAG_MIN - CLOSE_MARGIN_MIN
    return opens, closes


@dataclass(frozen=True)
class Verdict:
    """One window reading. ``minutes_to_open`` is 0 when already inside."""

    inside: bool
    minute: int
    opens: int
    closes: int
    minutes_to_open: int
    minutes_left: int


def window_verdict(now: datetime) -> Verdict:
    """Is ``now`` inside the push window? Both bounds inclusive.

    Inclusive on purpose: :32 and :50 are the derived edges themselves, and the
    margin that makes the closing edge safe is already inside ``window_bounds``.
    A second layer of caution here would silently narrow a band two other
    documents quote by its endpoints.
    """
    opens, closes = window_bounds()
    minute = now.astimezone(timezone.utc).minute
    inside = opens <= minute <= closes
    if inside:
        return Verdict(True, minute, opens, closes, 0, closes - minute)
    # Outside: how long until the NEXT opening, which may be in the next hour.
    to_open = (opens - minute) if minute < opens else (60 - minute + opens)
    return Verdict(False, minute, opens, closes, to_open, 0)


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
    toward releasing, so a guard built on it must fail toward refusing.
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
        description="Refuse a master push that would land a release on the :15 rebuild.",
    )
    parser.add_argument("mode", choices=["check", "exec"])
    parser.add_argument("--before", help="base sha of the range being pushed")
    parser.add_argument("--after", help="head sha of the range being pushed")
    parser.add_argument("--repo", default=".")
    parser.epilog = "for `exec`: -- followed by the push command to run inside the window"

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
    # decision that gates the push. Not at import, not by the caller, not passed in.
    now = now or datetime.now(timezone.utc)

    required, why = release_required(args.before, args.after, args.repo)
    verdict = window_verdict(now)

    print(f"push window guard — clock read now: {stamps(now)}")
    print(f"  release required: {'yes' if required else 'NO'} — {why}")
    print(f"  window: :{verdict.opens:02d}–:{verdict.closes:02d} UTC (notice 29, derived)")

    if not required:
        print("🟢 PASS — this range releases nothing, so there is no rebuild to collide with.")
    elif verdict.inside:
        print(
            f"🟢 PASS — :{verdict.minute:02d} is inside the window, "
            f"{verdict.minutes_left} min of it left."
        )
    else:
        print(
            f"🔴 REFUSE — :{verdict.minute:02d} is outside :{verdict.opens:02d}–:{verdict.closes:02d}. "
            f"The window opens in {verdict.minutes_to_open} min."
        )
        print(
            "   Do NOT compute the new time by adding a sleep to this reading — that is the "
            "bug this guard exists for. Sleep, then run this command again."
        )
        sys.stdout.flush()
        return 1

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
