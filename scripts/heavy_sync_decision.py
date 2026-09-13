#!/usr/bin/env python3
"""#5470 — may the heavy app be synced to the main app's live commit RIGHT NOW?

**The failure this closes.** Since the heavy split (9/11 ~1pm PT) the main site
deploys itself and ``bainluck-heavy`` does not. At 12:48am Sat it sat 84 commits
behind; seven hours after Alex's manual redeploy it was **158 commits / 42
``backend/app`` files** behind again. Every background-job fix merged in between
is "live" on the website and NOT running — #5505 shipped GREEN with 109 published
Polymarket legs waiting on a worker that never got the code. ``/health``, the main
app's release list and a LOOK at the page are all blind to it.

**Why this is not "deploy heavy with every main-site release."** Notice 48 names
that mechanism in a parenthetical; it is a design, and it re-breaks ship 2. A
heavy release cycles ``worker-heavy.1``, and a dyno cycle kills whatever it is
mid-way through — which is the precise failure moving the worker into its own app
was meant to end. There were **31 backend deploys in 24h** (measured 2026-09-12),
so per-release means 31 heavy cycles a day, for code that mostly does not change
what heavy runs.

**And not "whenever a cron happens to fire" either — that was the first design and
it is the one that failed.** A schedule is uncorrelated with the thing it is
chasing: drift is CREATED by main-app deploys, so the rate you need to sync at is
the rate they happen at, and a clock cannot know that. Worse, GitHub does not
deliver the slots — measured 2026-09-13 05:15Z over every run this workflow has
ever had, **4 runs against 17 nominal hourly slots**, the last of them 3h48m
earlier, while heavy sat 7h33m and 98 commits behind with four launch ships dark
on it. Buying more lottery tickets (``34,42,50``, latency/362) raises the expected
rate and leaves the tail exactly as heavy-tailed.

So the primary trigger is ``workflow_run`` on CI completing on ``master``: the
event that CREATES the drift is the event that clears it, and the opportunity rate
tracks the deploy rate for free — including the case that matters most, a quiet
night, where no deploys means no drift means nothing is owed. The cron stays as a
backstop for the one thing the event cannot cover: a sync that was HELD (out of
band, or under the floor below) while no further deploy arrives to re-offer it.

**Which makes the trigger rate stop being the cycle rate, so the floor below is
what keeps the price honest.** ~31 CI-success runs a day against a 25-minute band
is ~13 cycles/day, and this file already rejected that rate at the top. The
``ACCEPTED_CYCLES_PER_DAY`` floor holds the cost at the budget the cron raise was
priced against, and it binds only when triggers are plentiful — at today's ~2.5
cycles/day it never fires at all.

**And not "push at a quiet minute" either.** 31 beats route to ``queue: heavy`` on
one dyno at concurrency 2 — ``*/15``, ``*/20``, ``*/30``, two 15-minute cluster
beats, plus hourly singles. No minute of the hour is reliably free of all of them.

**So what makes a window derivable at all** is a measurement the two rejected
designs did not have: what a cycle actually COSTS. It is one unit, not a pass.

* The curve is **published before** the rebuild runs (D45's publish-first reorder),
  so a kill costs a reader nothing.
* :func:`save_staged_cursor` is called **per unit, immediately after the commit**
  (``precompute_calibration.py`` "COMMIT, then advance"), so a kill costs exactly
  the in-flight unit — ``staged:unit_ms_mean`` = **119,456 ms ≈ 2 min** on
  production, against a 22-minute pass.
* Banked units survive across beats by design: a beat banks ~10 of 128
  (``staged:units_this_beat`` = 10, ``staged:units_banked`` = 120), so a full
  census intentionally spans ~13 beats.

That inverts the cost model. The job is therefore **not** to dodge all 31 beats —
impossible — but to dodge the ONE long, expensive stretch and lean on the measured
per-item durability for the rest. The band below is exactly that.

**The bank is discarded by the CONTENT of a deploy, not its timing.** The
``staged-unit/v1`` fingerprint hashes ``CALIBRATION_POPULATION_VERSION``, the tie
authority and the unit statement, so a deploy that edits the calibration statement
throws away every banked unit whenever it lands, and one that does not touch it
costs a single unit whenever it lands. Timing is the small term in both branches —
which is why a wide, cheap band beats a precise idle probe.

Usage (the workflow gathers facts, this judges, the workflow acts on the code)::

    python3 scripts/heavy_sync_decision.py decide \\
        --main-live "$MAIN_LIVE" --heavy-live "$HEAVY_LIVE" \\
        --heavy-is-ancestor true [--heavy-release-age-min N] [--dispatched]

Exit codes: ``0`` PUSH · ``1`` HOLD (a benign result, not an error — gotcha #124) ·
``2`` REFUSE (unsafe; somebody should look) · ``3`` usage.

There is deliberately **no ``--now`` flag**. authority/114 checked its window three
times and pushed 29 minutes early because it computed the time from its own
``sleep`` durations instead of reading a clock (#4997) — arithmetic that can only
drift ahead, so it can never report "outside". The clock is read here, in the same
process as the verdict; tests drive the ``now=`` keyword seam instead (gotcha #44).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

# ── the window, derived from measurements — never typed in ─────────────────────

#: The accuracy rebuild's beat. Hourly at :15 (beat schedule is the authority).
REBUILD_START_MIN = 15
#: MEASURED on production, and this constant is a CEILING on the rebuild, not its
#: typical length — the band is only safe if no rebuild outlives it. latency/350
#: read one run at 22m13s (`elapsed_ms = 1,332,567`); latency/372 then read the
#: task-metrics ring of 30 consecutive runs (2026-09-12T17:14Z .. 09-13T09:15Z)
#: and the MAX was 22m31s (09-12 19:14:59 -> 19:37:30), i.e. 22 understated the
#: observed ceiling by 31s. 23 covers every run in that ring. The sibling guard
#: `push_window_guard.py` still carries 7 — see #5470's note; correcting it there
#: without also retiring notice 29 would narrow THAT band to three minutes.
REBUILD_DURATION_MIN = 23
#: Push -> heavy release. A Heroku build with NO CI in front of it, so both ends
#: are well under the main app's CI-queue-dependent lag. These were ESTIMATES —
#: named as constants precisely so the first real reading could move the band
#: instead of being argued about. MIN now HAS its first real reading, from the
#: first unattended convergence (heavy-sync run 34750397765, 2026-09-13): the
#: workflow logged `PUSH:` at 09:52:01.509Z and Heroku logged `Released v14` at
#: 09:53:59.010Z — 1m57.5s. So 3 was never a lower bound on the lag, and a lower
#: bound is the only thing that makes the opening edge safe (`opens` SUBTRACTS
#: it), so the one reading we have must be ABOVE it, not equal to it: 1, the
#: measurement floored to the minute the gate actually works in. MAX stays an
#: estimate; it sits on the closing edge, where over-estimating is the safe
#: direction. Cost of the move, measured rather than assumed (latency/372): CI
#: completions on master cluster at :40-:59 with ZERO in :30-:40, so :34 -> :37
#: loses no triggers at all — 8/13 in band before and after.
MIN_RELEASE_LAG_MIN = 1
MAX_RELEASE_LAG_MIN = 12
#: Slack on the closing edge so a lag at the top of the range still lands clear of
#: the NEXT hour's rebuild.
CLOSE_MARGIN_MIN = 5


#: The cycle budget this file has ALREADY priced and accepted, in heavy releases
#: per day. It is not a new number: the raise to three cron attempts an hour
#: (latency/362) was justified at "~7.5 heavy cycles a day against today's ~2.5",
#: and the same paragraph rejects N=6's "~15/day" as too many. 8 is that accepted
#: rate, rounded up so the floor never forbids what the cron was licensed to do.
#: A cycle costs ONE calibration unit (~2 min measured), so this prices at ~16
#: min/day of recomputation.
ACCEPTED_CYCLES_PER_DAY = 8


def min_cycle_interval_min() -> int:
    """The floor between two heavy releases, derived from the accepted budget.

    Derived and not typed in for the same reason as :func:`window_bounds`: moving
    the budget must move the floor, or the two drift apart and the comment above
    becomes a story about a number nothing enforces
    (``test_moving_the_accepted_budget_moves_the_floor``).
    """
    return round(24 * 60 / ACCEPTED_CYCLES_PER_DAY)


def window_bounds() -> tuple[int, int]:
    """The (open, close) minutes past the hour, derived — never asserted.

    ``opens`` is the earliest push whose EARLIEST possible cycle still lands after
    the rebuild has finished; ``closes`` the latest push whose LATEST possible
    cycle still lands clear of the next one. Both edges therefore move on their
    own if any measured input moves, which is the property
    ``test_moving_a_measured_constant_moves_the_band`` pins.
    """
    opens = REBUILD_START_MIN + REBUILD_DURATION_MIN - MIN_RELEASE_LAG_MIN
    closes = REBUILD_START_MIN + 60 - MAX_RELEASE_LAG_MIN - CLOSE_MARGIN_MIN
    return opens, closes


def inside_window(now: datetime) -> bool:
    """Both bounds inclusive — the margin that makes them safe is in the bounds."""
    opens, closes = window_bounds()
    return opens <= now.astimezone(timezone.utc).minute <= closes


# ── the verdict ────────────────────────────────────────────────────────────────

PUSH, HOLD, REFUSE, USAGE = 0, 1, 2, 3

_VALID_SHA_LEN = 40


@dataclass(frozen=True)
class Decision:
    """One sync reading. ``code`` is the process exit code the workflow gates on."""

    code: int
    verdict: str
    reason: str


def _is_sha(value: str | None) -> bool:
    """A full 40-char hex sha and nothing else.

    An abbreviation is refused rather than accepted: notice 28's amendment is the
    precedent — a short sha makes an API answer EMPTY rather than wrong, and an
    empty answer here would read as "nothing to do" (gotcha #53).
    """
    return bool(
        value
        and len(value) == _VALID_SHA_LEN
        and all(c in "0123456789abcdef" for c in value.lower())
    )


def decide(
    *,
    main_live: str | None,
    heavy_live: str | None,
    heavy_is_ancestor: bool | None,
    dispatched: bool = False,
    heavy_release_age_min: int | None = None,
    now: datetime | None = None,
) -> Decision:
    """Judge one sync opportunity. Pure apart from the clock it reads itself.

    Order is the safety order, not the narrative one:

    1. **Unreadable facts REFUSE.** A missing or abbreviated sha cannot be
       reasoned about, and "cannot prove" is never permission.
    2. **Already in sync HOLDS** — checked before the window so the overwhelmingly
       common run reports "up to date" rather than a window skip it never needed.
    3. **Divergence REFUSES**, and does so BEFORE the window and regardless of
       ``--dispatched``: an attended run may overrule a clock, never a
       never-backwards guard. This is the one that must not be forceable.
    4. Only then do the two COST gates — the clock, then the cycle floor — get a
       say, and they fail in the OPPOSITE direction to the guards above them. A
       safety guard that cannot read its fact refuses; a cost gate that cannot
       read its fact proceeds. ``heavy_release_age_min=None`` is therefore not a
       hold: an unreadable release age means we do not know that heavy was
       disturbed recently, and the harm of one extra cycle (~2 min of
       recomputation) is not the harm of missing the sync this ship exists for.
    """
    if not _is_sha(main_live):
        return Decision(REFUSE, "REFUSE", f"main live ref unreadable: {main_live!r}")
    if not _is_sha(heavy_live):
        return Decision(REFUSE, "REFUSE", f"heavy live ref unreadable: {heavy_live!r}")

    if main_live == heavy_live:
        return Decision(HOLD, "HOLD", f"heavy is already on {main_live[:9]} — nothing to do")

    if heavy_is_ancestor is not True:
        # Not an ancestor, or an ancestry we could not establish. A push in either
        # state can rewind the heavy app, so both fail closed (ci.yml's deploy
        # guard reasons identically about its own `HAVE_LIVE`).
        return Decision(
            REFUSE,
            "REFUSE",
            f"heavy {heavy_live[:9]} is not a proven ancestor of main {main_live[:9]} — "
            "refusing rather than rewinding heavy",
        )

    now = now or datetime.now(timezone.utc)
    opens, closes = window_bounds()
    if not dispatched and not inside_window(now):
        return Decision(
            HOLD,
            "HOLD",
            f":{now.astimezone(timezone.utc).minute:02d} is outside the :{opens}-:{closes} "
            f"heavy-sync window (the :{REBUILD_START_MIN} accuracy rebuild runs "
            f"{REBUILD_DURATION_MIN} min) — the next scheduled run retries",
        )

    floor = min_cycle_interval_min()
    if not dispatched and heavy_release_age_min is not None and heavy_release_age_min < floor:
        return Decision(
            HOLD,
            "HOLD",
            f"heavy was released {heavy_release_age_min} min ago, inside the {floor}-min "
            f"cycle floor ({ACCEPTED_CYCLES_PER_DAY} cycles/day) — a release cycles "
            "worker-heavy, so the trigger rate is not the cycle rate",
        )

    why_now = "attended run: window bypassed" if dispatched else f"inside :{opens}-:{closes}"
    return Decision(
        PUSH,
        "PUSH",
        f"heavy {heavy_live[:9]} -> main's live {main_live[:9]} ({why_now})",
    )


# ---------------------------------------------------------------------------
# READBACK — did the push actually become the release heavy is running? (#5722)
# ---------------------------------------------------------------------------
#
# THE GIT REF IS NOT THE ANSWER, AND ASKING IT COST US THE FIRST EVER SYNC.
#
# Run 34714692872 (2026-09-12 19:37Z) pushed `10c0ee5cd` to bainluck-heavy,
# Heroku built it, printed `Released v11`, and ran the release command clean.
# The workflow then read `git ls-remote heroku-heavy refs/heads/master` and got
# `87a095b4` — the PRE-PUSH sha — and failed the job. Heavy was, and is, on the
# new code: `heroku releases -a bainluck-heavy` showed `v11 Deploy 10c0ee5c`.
#
# A Heroku git endpoint is a push endpoint that triggers a build, not a plain
# git server, and the ref it advertises advances asynchronously after the
# release. So the readback raced it and lost.
#
# Why that is worth a script rather than a retry loop in YAML: #5470 exists
# because heavy drift is SILENT, and #5662's repair existed because a job that
# looks fine while doing nothing is the failure mode. A job that reports failure
# every time it succeeds is the same corrosion pointed the other way — within a
# day nobody reads the red, and the run that fails for a real reason becomes
# invisible. So the readback asks the RELEASE record, which is what notice 48
# already means by "heavy carries the sha", and it distinguishes three outcomes
# where the old line had two.

CONFIRMED = 0
MISMATCH = 1
UNREADABLE = 2


def readback_verdict(*, expected: str | None, observed: str | None) -> Decision:
    """Is the release heavy is running built from ``expected``?

    ``UNREADABLE`` is deliberately NOT folded into ``MISMATCH`` (gotcha #53).
    "the API did not answer" and "heavy is on a different commit" call for
    opposite responses — the first is retried, the second is a genuine stop —
    and the old one-line check could not tell them apart, so an unreadable
    answer and a wrong one both printed the same false claim about heavy's sha.
    """
    if not _is_sha(expected):
        return Decision(REFUSE, "REFUSE", f"expected sha unreadable: {expected!r}")
    if not observed:
        return Decision(UNREADABLE, "UNREADABLE", "the release API did not name a commit")
    if not _is_sha(observed):
        return Decision(
            UNREADABLE, "UNREADABLE", f"the release API named something that is not a sha: {observed!r}"
        )
    if observed.lower() == expected.lower():
        return Decision(CONFIRMED, "CONFIRMED", f"heavy's release is built from {expected[:9]}")
    return Decision(
        MISMATCH,
        "MISMATCH",
        f"heavy's release is built from {observed[:9]}, not the {expected[:9]} just pushed",
    )


def poll_readback(
    *,
    expected: str | None,
    fetch,
    attempts: int = 10,
    delay_s: float = 6.0,
    sleep=None,
) -> Decision:
    """Re-ask until the release record catches up, or the budget runs out.

    ``fetch`` returns the commit of the app's current release, or ``None`` if it
    could not be read. It is injected so the classification above is testable
    without a network, a credential, or a clock.

    A MISMATCH is retried rather than trusted immediately, because the race this
    exists for PRESENTS as a mismatch: the first read returns the previous
    release. Only a mismatch that survives the whole budget is reported as one.
    """
    import time

    sleep = sleep or time.sleep
    verdict = readback_verdict(expected=expected, observed=None)
    for attempt in range(1, max(1, attempts) + 1):
        try:
            observed = fetch()
        except Exception as exc:  # noqa: BLE001 - any read failure is UNREADABLE, not a mismatch
            observed = None
            print(f"  attempt {attempt}: release read failed ({type(exc).__name__}: {exc})")
        verdict = readback_verdict(expected=expected, observed=observed)
        if verdict.code in (CONFIRMED, REFUSE):
            return verdict
        print(f"  attempt {attempt}/{attempts}: {verdict.verdict} — {verdict.reason}")
        if attempt < attempts:
            sleep(delay_s)
    return verdict


def _heroku_get(path: str, token: str, extra: dict | None = None):
    """One Platform API read. Stdlib only — this script imports nothing external
    and must stay that way so it runs on a bare runner before any `pip install`.
    """
    import json
    import urllib.request

    # The trailing `/` in the literal is load-bearing, not a tidy-up target:
    # `backend/tests/test_agent_origin_outbound_tag.py` proves statically that
    # this call is third-party (so the origin carrier would be a no-op here,
    # and this file can stay importless), and it can only prove that while the
    # literal prefix CLOSES the authority. `f"...heroku.com{path}"` would leave
    # the host open to whatever `path` holds, and is correctly reported.
    req = urllib.request.Request(
        f"https://api.heroku.com/{path}",
        headers={
            "Accept": "application/vnd.heroku+json; version=3",
            "Authorization": f"Bearer {token}",
            **(extra or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _current_release(app: str, token: str) -> dict | None:
    """The app's CURRENT release record, or ``None`` if the API named none."""
    releases = _heroku_get(
        f"apps/{app}/releases", token, {"Range": "version ..; order=desc, max=1"}
    )
    if not releases:
        return None
    return releases[0] or None


def heroku_release_age_min(app: str, token: str, now: datetime | None = None) -> int | None:
    """Minutes since the app's current release, or ``None`` if unreadable.

    A CONFIG-ONLY release counts here, and that is the difference between this
    question and :func:`heroku_release_commit`'s. That function reads a slugless
    release as unreadable because it cannot say which commit is running; this one
    wants to know when heavy was last DISTURBED, and a config change cycles the
    dyno exactly as a deploy does. Two questions, two right answers — the failure
    would be to reuse one reader for both (gotcha #53).
    """
    release = _current_release(app, token)
    created = (release or {}).get("created_at")
    if not created:
        return None
    stamp = str(created).strip().replace("Z", "+00:00")
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    # A release stamped in the FUTURE (clock skew between the API and the runner)
    # reads as age 0, never as a negative that would sail under the floor.
    return max(0, int((now - when).total_seconds() // 60))


def heroku_release_commit(app: str, token: str) -> str | None:
    """The commit the app's CURRENT release was built from, via the Platform API."""
    release = _current_release(app, token)
    if not release:
        return None
    slug = release.get("slug") or {}
    slug_id = slug.get("id")
    if not slug_id:
        # A release with no slug is a config change, not a deploy — it cannot
        # tell us which commit is running, and saying "no" would be a lie.
        return None
    return (_heroku_get(f"apps/{app}/slugs/{slug_id}", token) or {}).get("commit")


def _age_arg(value: str | None) -> int | None:
    """Minutes, or ``None`` for "the workflow could not read it".

    Deliberately NOT ``type=int``. The workflow computes this from an API read
    that is allowed to fail, so the empty string is a legitimate value here —
    and argparse would turn it into a usage exit, which the workflow reads as a
    story about the harness and refuses on (gotcha #54). An unreadable age is a
    fact about a COST gate, and it proceeds; it must never take the sync down.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def _bool_arg(value: str) -> bool | None:
    """`true`/`false` only. Anything else is UNKNOWN, which refuses upstream."""
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="heavy_sync_decision.py",
        description="May bainluck-heavy be synced to the main app's live commit now?",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("decide", help="print the verdict and exit on its code")
    d.add_argument("--main-live", required=True, help="the MAIN app's live sha (40 hex)")
    d.add_argument("--heavy-live", required=True, help="the HEAVY app's live sha (40 hex)")
    d.add_argument(
        "--heavy-is-ancestor",
        required=True,
        help="true|false — is the heavy sha a proven ancestor of the main one? "
        "Anything else is treated as unknown and refuses.",
    )
    d.add_argument(
        "--dispatched",
        action="store_true",
        help="an attended workflow_dispatch run: bypasses the CLOCK only, never the "
        "never-backwards guard",
    )
    d.add_argument(
        "--heavy-release-age-min",
        default="",
        help="minutes since heavy's current release. Empty or unparseable means "
        "UNREADABLE, which does not hold — see the cost-gate polarity in decide().",
    )
    a = sub.add_parser(
        "age", help="print minutes since the app's current release (empty if unreadable)"
    )
    a.add_argument("--app", required=True, help="the Heroku app, e.g. bainluck-heavy")
    v = sub.add_parser(
        "verify", help="confirm heavy's CURRENT RELEASE is built from the sha just pushed"
    )
    v.add_argument("--app", required=True, help="the Heroku app, e.g. bainluck-heavy")
    v.add_argument("--expect", required=True, help="the sha that was just pushed (40 hex)")
    v.add_argument("--attempts", type=int, default=10)
    v.add_argument("--delay-s", type=float, default=6.0)

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return USAGE

    if args.command == "age":
        import os

        # Prints the NUMBER ALONE on stdout so the workflow can capture it with
        # `$(...)`, and every diagnostic goes to stderr. Always exits 0: the
        # caller's contract is the string, and an empty string already carries
        # "unreadable" — a non-zero here would make a cost gate able to fail a
        # job that has nothing wrong with it.
        token = os.environ.get("HEROKU_API_KEY", "")
        if not token:
            print("HEROKU_API_KEY is not set, so no release age can be read", file=sys.stderr)
            return 0
        try:
            age = heroku_release_age_min(args.app, token)
        except Exception as exc:  # noqa: BLE001 - any read failure is "unreadable"
            print(f"release age unreadable ({type(exc).__name__}: {exc})", file=sys.stderr)
            return 0
        if age is None:
            print(f"{args.app}: the release API named no usable created_at", file=sys.stderr)
            return 0
        print(age)
        return 0

    if args.command == "verify":
        import os

        token = os.environ.get("HEROKU_API_KEY", "")
        if not token:
            # Gotcha #9: checked here, never in a step-level `if`.
            print("UNREADABLE: HEROKU_API_KEY is not set, so no release can be read")
            return UNREADABLE
        decision = poll_readback(
            expected=args.expect,
            fetch=lambda: heroku_release_commit(args.app, token),
            attempts=args.attempts,
            delay_s=args.delay_s,
        )
        print(f"{decision.verdict}: {decision.reason}")
        return decision.code

    decision = decide(
        main_live=args.main_live,
        heavy_live=args.heavy_live,
        heavy_is_ancestor=_bool_arg(args.heavy_is_ancestor),
        dispatched=args.dispatched,
        heavy_release_age_min=_age_arg(args.heavy_release_age_min),
    )
    print(f"{decision.verdict}: {decision.reason}")
    return decision.code


if __name__ == "__main__":
    sys.exit(main())
