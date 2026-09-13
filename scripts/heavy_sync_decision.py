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

**AND THE BAND IS DERIVED AGAINST ONE OF THREE RESIDENTS, WHICH IS WHY IT IS NOT
THE LAST GATE (#5886).** ``worker-heavy`` runs at concurrency 2 and the rebuild is
only one of the jobs scheduled on it. The first unattended convergence
(2026-09-13T09:53:58Z) landed 19m44s clear of the rebuild — the band did its job —
and cycled ``prediction_market_match`` 3m58s in and ``rebuild_typeahead_index``
58s in, both of which are scheduled INSIDE the band by construction: the matcher
fires ``:05/:20/:35/:50`` and runs 154-552s, so it occupies 19 of the band's 25
minutes, and the typeahead fires ``:53``. There is no 25-minute window that clears
all three (matcher-free minutes are ``:14-:20``, ``:29-:35``, ``:44-:50``,
``:59-:05``), so narrowing the band cannot fix this and would only cost triggers.

So the clock stops being the last word: :func:`inflight_verdict` ASKS the fleet
what it is running instead of predicting it, from the ``active`` set the main
app's ``/api/admin/celery/inspect`` already broadcasts, and holds while a
``HEAVY_TASKS`` job is in flight. The band stays — it is the fallback for the runs
where that answer cannot be read, and a cost gate that cannot read its fact must
never take the sync down (the polarity rule in :func:`decide`).

What the probe does NOT cover, stated so nobody reads it as a proof: a job that
STARTS in the 36-118s between the push and the release (the typeahead at ``:53``
is exactly that case), and a job on ``worker-heavy`` that is not in
``HEAVY_TASKS`` — the inspect reply is keyed by an opaque ``celery@<uuid>``
hostname, so membership of that set is the only channel that names the heavy
fleet. Both residuals are narrower than today's, and neither is silent: the
verdict names what it saw.

Usage (the workflow gathers facts, this judges, the workflow acts on the code)::

    python3 scripts/heavy_sync_decision.py decide \\
        --main-live "$MAIN_LIVE" --heavy-live "$HEAVY_LIVE" \\
        --heavy-is-ancestor true [--heavy-release-age-min N] [--dispatched]
    python3 scripts/heavy_sync_decision.py inflight \\
        --inspect-json /tmp/inspect.json [--dispatched]

Exit codes: ``0`` PUSH · ``1`` HOLD (a benign result, not an error — gotcha #124) ·
``2`` REFUSE (unsafe; somebody should look) · ``3`` usage. ``inflight`` uses the
same two benign codes: ``0`` proceed (IDLE, or UNKNOWN — see the polarity rule) ·
``1`` HOLD.

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
#: instead of being argued about.
#:
#: MIN IS NOW READ FROM EVERY SYNC THIS WORKFLOW HAS EVER COMPLETED, not from
#: one of them (latency/374, `Pushing ...` -> `remote: Released vN` in the run
#: logs, cross-checked against the release records):
#:
#:     v14  run 34750397765  09:52:01.518Z -> 09:53:59.010Z   117.5s
#:     v13  run 34743071282  06:34:38.837Z -> 06:35:15.077Z    36.2s  <- the floor
#:     v12  run 34720427451  21:37:14.249Z -> 21:38:10.096Z    55.8s
#:     v11  run 34714692872  19:37:36.353Z -> 19:38:15.612Z    39.3s
#:
#: `opens` SUBTRACTS this, so only a LOWER bound on the real lag makes the
#: opening edge safe, and the single 1m57.5s reading it was set from was the
#: SLOWEST of the four — three times the real floor. 1 is therefore still not a
#: lower bound: 36.2s is 0.60 min, so the honest floored value is 0 and the band
#: opens at the rebuild's own ceiling rather than a minute inside it. Headroom
#: against the worst observed rebuild goes from **5 seconds** to 1m05s
#: (`test_the_opening_edge_clears_the_worst_rebuild_at_the_fastest_real_lag`).
#: MAX stays an estimate at 12 and is deliberately NOT moved down to the 1m57.5s
#: ceiling these four readings give: it sits on the CLOSING edge, where the band
#: shrinks as the number grows, so over-estimating buys safety and costs only
#: opportunity. The four readings are recorded here anyway, because the day
#: something wants a real upper bound (an imminent-fire gate would) they are the
#: measurement, and re-deriving it from one log line is how 1 got here.
#:
#: Cost of the move, measured rather than assumed (latency/372): CI completions
#: on master cluster at :40-:59 with ZERO in :30-:40, so :34 -> :37 -> :38 loses
#: no triggers at all — 8/13 in band at every one of the three edges.
MIN_RELEASE_LAG_MIN = 0
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
# IN FLIGHT — ask the fleet what it is running instead of predicting it (#5886)
# ---------------------------------------------------------------------------
#
# THE BAND PROTECTS ONE OF THREE RESIDENTS. The header states the measurement;
# this is the mechanism. Three facts make it cheap:
#
#   * only `worker-heavy` consumes the `heavy` queue, and `HEAVY_TASKS` is the
#     single source of what routes there (`task_routes` and every beat entry's
#     `options["queue"]` are both written from it, in `app/tasks/__init__.py`).
#     So "a HEAVY_TASKS task is active ANYWHERE" and "worker-heavy is busy" are
#     the same reading, and no worker identity is needed — which matters,
#     because `inspect` names workers `celery@<uuid>` with no app or dyno in it;
#   * the set is READ FROM THAT FILE rather than copied here. A second copy is
#     the drift this repo has already paid for twice (the `ß`/`æ` normaliser
#     tables of #5878), and a list of 28 task names would rot in a week.
#     `test_the_heavy_task_set_is_the_one_the_app_routes_on` asserts the parse
#     equals the imported `app.tasks.HEAVY_TASKS`, both directions;
#   * the payload is gathered by the workflow, not fetched here. Our own host
#     must carry `x-bainluck-origin` (notice 39) and this script cannot import
#     the carrier — it runs on a bare runner before any `pip install`, which is
#     the exemption `test_agent_origin_outbound_tag.py` grants it for the Heroku
#     reads. A `curl -H` in the workflow tags the call without the import.

#: The name of the assignment this module reads the heavy fleet's task set from.
HEAVY_TASKS_NAME = "HEAVY_TASKS"
#: Where that assignment lives, relative to the repo root.
HEAVY_TASKS_SOURCE = "backend/app/tasks/__init__.py"

BUSY, IDLE = 1, 0


def heavy_task_names(source: str) -> frozenset | None:
    """The `HEAVY_TASKS` string set, parsed out of `source`, or ``None``.

    ``None`` — never ``frozenset()`` — when the assignment is missing, is not a
    set/list of plain strings, or the file does not parse. An empty set would
    make every reading IDLE: the worker would be declared free precisely when
    this module has lost the ability to tell, which is gotcha #53's failure
    written as a gate. The caller treats ``None`` as UNKNOWN.
    """
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(getattr(t, "id", None) == HEAVY_TASKS_NAME for t in node.targets):
            continue
        value = node.value
        if not isinstance(value, (ast.Set, ast.List, ast.Tuple)):
            return None
        names = {
            e.value for e in value.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        }
        # A set literal that parsed but yielded nothing usable is unknown, not
        # empty — same reason as above.
        return frozenset(names) or None
    return None


def active_task_names(payload) -> list | None:
    """Every task name the inspect payload reports as ACTIVE, or ``None``.

    ``None`` when the payload names no worker at all. That is the reading a
    failed broadcast produces — `/api/admin/celery/inspect` composes its reply
    from `registered`/`active`/`reserved`, so a broker that answered nothing
    returns a body carrying only `_cache` — and it is indistinguishable in shape
    from a genuinely idle fleet. It is NOT indistinguishable in meaning: three
    workers have replied to every reading this repo has taken, so no worker keys
    means the instrument failed, and "the instrument failed" must not read as
    "nothing is running" (gotcha #53).
    """
    if not isinstance(payload, dict):
        return None
    names = []
    workers = 0
    for key, value in payload.items():
        if key.startswith("_") or not isinstance(value, dict):
            continue
        workers += 1
        for task in value.get("active") or []:
            if isinstance(task, dict) and task.get("name"):
                names.append(str(task["name"]))
    if not workers:
        return None
    return names


def inflight_verdict(
    *,
    active: list | None,
    heavy: frozenset | None,
    dispatched: bool = False,
) -> Decision:
    """Is a heavy job in flight, so that a release would kill it mid-run?

    The polarity is :func:`decide`'s, for the same reason: this is a COST gate,
    not a safety one. A killed heavy job self-heals on its next beat — the
    09:53:58Z matcher restarted at 10:05 and succeeded at 10:09:37, and the cost
    was one lost pass — while a sync that cannot happen is #5470 itself, silent
    and unbounded. So an unreadable fact PROCEEDS, and says that it is doing so.

    ``--dispatched`` bypasses it, exactly as it bypasses the clock and the cycle
    floor: an attended run is a person accepting one lost pass to get the code
    onto the worker now. It never bypasses the never-backwards guard.
    """
    if dispatched:
        return Decision(IDLE, "BYPASSED", "attended run: the in-flight veto is bypassed")
    if heavy is None:
        return Decision(
            IDLE, "UNKNOWN",
            f"the {HEAVY_TASKS_NAME} set could not be read from {HEAVY_TASKS_SOURCE} — "
            "proceeding, because a cost gate that cannot read its fact must not be "
            "able to stop the sync",
        )
    if active is None:
        return Decision(
            IDLE, "UNKNOWN",
            "the inspect reply named no worker, so the fleet did not answer — "
            "proceeding (an unreadable cost gate never holds the sync)",
        )
    busy = sorted({name for name in active if name in heavy})
    if busy:
        short = ", ".join(n.rsplit(".", 1)[-1] for n in busy)
        return Decision(
            BUSY, "BUSY",
            f"worker-heavy is running {short} — a release cycles the dyno and kills "
            "it mid-run (#5886); the next trigger re-reads and re-judges",
        )
    return Decision(IDLE, "IDLE", "no heavy job is in flight")


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
    f = sub.add_parser(
        "inflight",
        help="hold while a HEAVY_TASKS job is running on worker-heavy (#5886)",
    )
    f.add_argument(
        "--inspect-json",
        required=True,
        help="path to the body of /api/admin/celery/inspect, as the workflow "
        "fetched it. Missing, empty or unparseable is UNKNOWN, which PROCEEDS.",
    )
    f.add_argument(
        "--tasks-source",
        default="",
        help=f"override the path to the file carrying {HEAVY_TASKS_NAME} "
        f"(default: <repo>/{HEAVY_TASKS_SOURCE})",
    )
    f.add_argument(
        "--dispatched",
        action="store_true",
        help="an attended workflow_dispatch run: bypasses the in-flight veto, "
        "never the never-backwards guard",
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
    except SystemExit as exc:
        # READ THE VALUE, don't catch the class (gotcha #54). argparse raises
        # SystemExit(0) for `--help` and SystemExit(2) for a bad argument, and
        # folding both into USAGE made `--help` exit 3 — the code the workflow
        # and notice 10's dry-run clause both read as "the script is broken".
        if not exc.code:
            raise
        return USAGE

    if args.command == "inflight":
        import json
        import os

        # EVERY read here is wrapped, and the wrap is the gate's polarity, not
        # defensive habit: a crash would exit 1 from argparse-land or a
        # traceback, and the workflow reads 1 as HOLD. A gate that holds the
        # sync because it could not open a file is the failure #5470 is.
        def _read(path: str) -> str | None:
            try:
                with open(path, encoding="utf-8") as handle:
                    return handle.read()
            except OSError:
                return None

        source_path = args.tasks_source or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            *HEAVY_TASKS_SOURCE.split("/"),
        )
        source = _read(source_path)
        heavy = heavy_task_names(source) if source is not None else None

        raw = _read(args.inspect_json)
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = None
        active = active_task_names(payload) if payload is not None else None

        decision = inflight_verdict(active=active, heavy=heavy, dispatched=args.dispatched)
        print(f"{decision.verdict}: {decision.reason}")
        return decision.code

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
