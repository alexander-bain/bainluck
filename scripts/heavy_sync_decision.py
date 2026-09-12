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
        --heavy-is-ancestor true [--dispatched]

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
#: MEASURED on production 2026-09-12 (latency/350), NOT notice 29's "~7": the
#: `precompute_calibration_main` phase ledger read `elapsed_ms = 1,332,567`
#: (22m13s) with `deferred_rebuild.elapsed_ms = 1,256,026` (20m56s), and
#: `last_success_at` 11:37:13Z against a :15 start. The sibling guard
#: `push_window_guard.py` still carries 7 — see #5470's note; correcting it there
#: without also retiring notice 29 would narrow THAT band to three minutes.
REBUILD_DURATION_MIN = 22
#: Push -> heavy release. A Heroku build with NO CI in front of it, so both ends
#: are well under the main app's CI-queue-dependent lag. ESTIMATES, not
#: measurements — named as constants precisely so the first real reading can move
#: the band instead of being argued about. Widen rather than narrow when unsure.
MIN_RELEASE_LAG_MIN = 3
MAX_RELEASE_LAG_MIN = 12
#: Slack on the closing edge so a lag at the top of the range still lands clear of
#: the NEXT hour's rebuild.
CLOSE_MARGIN_MIN = 5


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
    4. Only then does the clock get a say.
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

    why_now = "attended run: window bypassed" if dispatched else f"inside :{opens}-:{closes}"
    return Decision(
        PUSH,
        "PUSH",
        f"heavy {heavy_live[:9]} -> main's live {main_live[:9]} ({why_now})",
    )


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
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return USAGE

    decision = decide(
        main_live=args.main_live,
        heavy_live=args.heavy_live,
        heavy_is_ancestor=_bool_arg(args.heavy_is_ancestor),
        dispatched=args.dispatched,
    )
    print(f"{decision.verdict}: {decision.reason}")
    return decision.code


if __name__ == "__main__":
    sys.exit(main())
