"""#5470 — the heavy-sync decision, pinned on the properties that make it safe.

The bug this closes is not "somebody forgot to redeploy heavy". It is that
NOTHING deployed heavy: the main app ships itself, heavy does not, and every
instrument a person would reach for (`/health`, the main app's release list, a
LOOK at the page) reports green while a merged background-job fix never runs.

So the tests that matter are not "does :42 push". They are:

* the band is **derived** from measured constants, so a corrected measurement
  moves it instead of leaving a stale literal behind;
* the decision **cannot be handed a time** — a ``--now`` flag would rebuild the
  #4997 hole, where a guard computed the clock from its own ``sleep`` durations
  and so could never report "outside";
* it **refuses toward safety** on every unreadable fact, because "cannot prove"
  is not permission;
* an attended run may overrule the **clock** and never the **never-backwards
  guard** — that asymmetry is the whole safety story and is tested in both
  directions;
* the workflow **gates** on the exit code rather than printing it beside the push.

Every case drives a fixed ``now`` through the ``now=`` keyword seam (gotcha #44:
a test anchor that reads the clock is a test that branches on the clock). The one
test that reads the real clock asserts only self-consistency, which holds at every
minute of the day.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "heavy_sync_decision.py"
WORKFLOW = REPO / ".github" / "workflows" / "heavy-sync.yml"

PUSH, HOLD, REFUSE, USAGE = 0, 1, 2, 3

A = "a" * 40          # a plausible "main live" sha
B = "b" * 40          # a plausible "heavy live" sha

# ── production readings the band must survive, recorded here so the guards below
#    can be checked against the WORLD and not only against each other ───────────

#: Worst `precompute_calibration_main` run in the task-metrics ring of 30
#: consecutive runs, read 2026-09-13T10:02Z (latency/372): 09-12 19:14:59Z ->
#: 19:37:30Z = 22m31s. The band's REBUILD_DURATION_MIN is a ceiling on this.
OBSERVED_REBUILD_MAX_MIN = 22.517
#: EVERY push -> heavy-release lag this workflow has ever produced, read from
#: the run logs (`Pushing ...` -> `remote: Released vN`) and cross-checked
#: against the release records (latency/374):
#:
#:     v14  run 34750397765  09:52:01.518Z -> 09:53:59.010Z   117.5s
#:     v13  run 34743071282  06:34:38.837Z -> 06:35:15.077Z    36.2s
#:     v12  run 34720427451  21:37:14.249Z -> 21:38:10.096Z    55.8s
#:     v11  run 34714692872  19:37:36.353Z -> 19:38:15.612Z    39.3s
#:
#: The list is here rather than a single number because the FASTEST is the one
#: the opening edge is safe against, and the first version of this constant was
#: set from the 117.5s reading — the SLOWEST of the four, three times the real
#: floor. MIN_RELEASE_LAG_MIN must sit at or below the fastest; see
#: `test_the_min_lag_is_a_real_lower_bound_and_not_merely_self_consistent`.
OBSERVED_RELEASE_LAGS_MIN = (1.958, 0.603, 0.930, 0.655)
OBSERVED_RELEASE_LAG_MIN = min(OBSERVED_RELEASE_LAGS_MIN)


def _module():
    """Import the script by path — it is not on any package path."""
    spec = importlib.util.spec_from_file_location("heavy_sync_decision", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    # Registered BEFORE exec: `from __future__ import annotations` makes the
    # dataclass fields strings, and `@dataclass` resolves them through
    # `sys.modules[cls.__module__]`.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


sync = _module()


def _at(minute: int) -> datetime:
    """A fixed UTC instant at ``minute`` past a fixed hour. Never the clock."""
    return datetime(2026, 9, 12, 14, minute, 0, tzinfo=timezone.utc)


def _workflow_code() -> str:
    """The workflow with its `#` comment lines removed.

    Scanning the raw file is the trap these very assertions fell into first: the
    comments EXPLAIN what the code must not do ("NOT origin/master", "No --force,
    ever"), so a naive `not in` matches the explanation and fails on a correct
    file — or, worse, passes on a wrong one whose comment was deleted. A scan
    that cannot tell code from prose is not measuring the code.
    """
    return "\n".join(
        line for line in WORKFLOW.read_text().splitlines()
        if not line.lstrip().startswith("#")
    )


# ── the band, and where its numbers come from ──────────────────────────────────


def test_the_band_falls_out_of_the_measured_constants():
    """The band must be arithmetic, so a re-measurement moves it.

    Pinning the literals alone would let someone edit a constant and leave the
    band stale; pinning only the derivation would let both drift together. Both,
    together, is the check.
    """
    opens, closes = sync.window_bounds()
    assert (opens, closes) == (38, 58)
    assert opens == (
        sync.REBUILD_START_MIN + sync.REBUILD_DURATION_MIN - sync.MIN_RELEASE_LAG_MIN
    )
    assert closes == (
        sync.REBUILD_START_MIN + 60 - sync.MAX_RELEASE_LAG_MIN - sync.CLOSE_MARGIN_MIN
    )


def test_moving_a_measured_constant_moves_the_band(monkeypatch):
    """The equality above is satisfied by hardcoded 34/58 — this is not.

    Each constant is moved on its own, so a band that ignored any ONE of them
    would survive the test above and die here.
    """
    monkeypatch.setattr(sync, "REBUILD_DURATION_MIN", 32)
    assert sync.window_bounds()[0] == 47
    monkeypatch.setattr(sync, "REBUILD_DURATION_MIN", 23)

    monkeypatch.setattr(sync, "MIN_RELEASE_LAG_MIN", 8)
    assert sync.window_bounds()[0] == 30
    monkeypatch.setattr(sync, "MIN_RELEASE_LAG_MIN", 0)

    monkeypatch.setattr(sync, "MAX_RELEASE_LAG_MIN", 25)
    assert sync.window_bounds()[1] == 45
    monkeypatch.setattr(sync, "MAX_RELEASE_LAG_MIN", 12)

    monkeypatch.setattr(sync, "CLOSE_MARGIN_MIN", 15)
    assert sync.window_bounds()[1] == 48


def test_the_rebuild_duration_is_the_measured_one_not_notice_29s_seven():
    """The sibling guard still carries 7; this one must not inherit it.

    `push_window_guard.py`'s REBUILD_DURATION_MIN = 7 predates the production
    read (`elapsed_ms` 1,332,567 = 22m13s). A band built on 7 would open at :19 —
    squarely inside the rebuild it exists to dodge.

    23, not 22: this constant is a CEILING, and latency/372 read the 30-run
    task-metrics ring (2026-09-12T17:14Z .. 09-13T09:15Z) whose MAX was 22m31s.
    """
    assert sync.REBUILD_DURATION_MIN == 23
    stale_open = sync.REBUILD_START_MIN + 7 - sync.MIN_RELEASE_LAG_MIN
    assert stale_open < sync.REBUILD_START_MIN + sync.REBUILD_DURATION_MIN
    # The ceiling must cover the worst run actually observed, not the typical one.
    assert sync.REBUILD_DURATION_MIN >= OBSERVED_REBUILD_MAX_MIN


def test_the_whole_band_lands_clear_of_the_rebuild():
    """Not an edge check — every minute in the band must be safe, both ends.

    The opening edge is tested against the rebuild's END, and the closing edge
    against the NEXT rebuild's start, each with the lag that applies to it.
    """
    opens, closes = sync.window_bounds()
    rebuild_end = sync.REBUILD_START_MIN + sync.REBUILD_DURATION_MIN
    # Earliest cycle a push at `opens` can produce is still after the rebuild.
    # NOTE: substitute `window_bounds()` and this line reads
    # `START + DURATION >= START + DURATION`. It is an IDENTITY — true for every
    # value of MIN_RELEASE_LAG_MIN, including ones no real lag can reach. That is
    # why it did not notice :34, and why the two tests below exist.
    assert opens + sync.MIN_RELEASE_LAG_MIN >= rebuild_end
    # Latest cycle a push at `closes` can produce is still before the next one.
    assert closes + sync.MAX_RELEASE_LAG_MIN < 60 + sync.REBUILD_START_MIN


def test_the_min_lag_is_a_real_lower_bound_and_not_merely_self_consistent():
    """`opens` SUBTRACTS this constant, so only a LOWER bound makes it safe.

    The sibling above cannot see this: it is an identity in the constants. So a
    MIN_RELEASE_LAG_MIN larger than any lag that can actually occur passes every
    other guard in this file while moving `opens` earlier by exactly the size of
    the error. That is the whole of the :34 defect — 3 was an admitted estimate,
    and the first real reading came in at 1m57.5s.

    AND IT IS ALSO THE WHOLE OF THE :37 DEFECT, which is why this test is
    written against a LIST. One reading is not a bound: 1m57.5s was the slowest
    of the four syncs this workflow has completed, and the fastest was 36.2s. A
    constant set from the slowest reading is an over-estimate wearing a
    measurement's clothes, and the gate it feeds moves the wrong way by exactly
    that much.

    Checked against recorded production readings rather than another constant.
    """
    assert sync.MIN_RELEASE_LAG_MIN <= min(OBSERVED_RELEASE_LAGS_MIN)
    # Not vacuous on the list: the bound must hold against EVERY reading, so a
    # future sync faster than any of these reddens this line rather than
    # quietly widening the band it was supposed to close.
    assert all(sync.MIN_RELEASE_LAG_MIN <= lag for lag in OBSERVED_RELEASE_LAGS_MIN)


def test_the_opening_edge_clears_the_worst_rebuild_at_the_fastest_real_lag():
    """The end-to-end safety property, in observed units, not in constants.

    RED on the pre-2026-09-13 band: `opens` :34 + a 1.958-minute lag releases at
    :35:58, while the worst observed rebuild runs to :37:31. The band opened
    while the rebuild it exists to dodge was still running, and every guard in
    this file was green. Today's release survived only because that hour's
    rebuild happened to finish at :34:14.

    THE HEADROOM IS THE READING, NOT THE PASS/FAIL. At :37 with the fastest
    observed lag the release lands at :37:36 against a worst rebuild ending
    :37:31 — green by **5 seconds**, which is a coin toss dressed as a guard.
    At :38 it is 1m05s. So the assertion is stated with the margin beside it:
    a band that passes by seconds is reported, not celebrated.
    """
    opens, _ = sync.window_bounds()
    earliest_release = opens + OBSERVED_RELEASE_LAG_MIN
    worst_rebuild_end = sync.REBUILD_START_MIN + OBSERVED_REBUILD_MAX_MIN
    headroom_s = (earliest_release - worst_rebuild_end) * 60
    assert earliest_release >= worst_rebuild_end, f"headroom {headroom_s:.0f}s"
    # A minute of slack between the two measured extremes. Below this the band
    # is decided by which of two production timings happened to be worse that
    # hour, and the next reading on either constant flips it.
    assert headroom_s >= 60, f"only {headroom_s:.0f}s of headroom"


# ── the clock cannot be handed in ──────────────────────────────────────────────


def test_the_cli_has_no_now_flag():
    """#4997's hole: a guard that accepts a time can be told the wrong one.

    Asserted by BEHAVIOUR, not by grepping the source for ``--now``: the module
    docstring says the flag is deliberately absent, so a text scan matches its
    own explanation. Being rejected by the parser is the property that matters.
    """
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "decide", "--main-live", A, "--heavy-live", B,
         "--heavy-is-ancestor", "true", "--now", "2026-09-12T14:40:00Z"],
        capture_output=True, text=True,
    )
    assert proc.returncode == USAGE


@pytest.mark.parametrize("argv", [["--help"], ["decide", "--help"], ["inflight", "--help"]])
def test_help_exits_clean_while_a_bad_argument_still_exits_usage(argv):
    """`--help` is an answer, not a usage error — and the two shared code 3.

    `except SystemExit: return USAGE` caught the class instead of reading the
    value (gotcha #54), so every `--help` exited 3: the code the workflow's own
    case statement calls "a story about the harness, not a verdict", and the
    code notice 10's dry-run clause reads as a failed pre-flight. The bad-flag
    line is the control — the fix must not make the parser permissive.
    """
    ok = subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr[-400:]
    assert "usage:" in ok.stdout

    bad = subprocess.run(
        [sys.executable, str(SCRIPT), "inflight", "--no-such-flag"],
        capture_output=True, text=True,
    )
    assert bad.returncode == USAGE


def test_the_real_clock_only_has_to_be_self_consistent():
    """True at every minute of the day — the one test that reads a clock."""
    now = datetime.now(timezone.utc)
    opens, closes = sync.window_bounds()
    assert sync.inside_window(now) == (opens <= now.minute <= closes)


# ── refusing toward safety ─────────────────────────────────────────────────────


def test_an_unreadable_sha_refuses_rather_than_reading_as_nothing_to_do():
    """An empty ref is a response shape, not an absence (gotcha #53).

    Treating it as "no work" is the failure mode: heavy would drift forever while
    the job stayed green.
    """
    for main, heavy in ((None, B), ("", B), (A, None), (A, "")):
        d = sync.decide(main_live=main, heavy_live=heavy, heavy_is_ancestor=True,
                        now=_at(42))
        assert d.code == REFUSE, (main, heavy)


def test_an_abbreviated_sha_refuses():
    """Notice 28's precedent: a short sha makes an answer EMPTY, not wrong."""
    d = sync.decide(main_live=A[:9], heavy_live=B, heavy_is_ancestor=True, now=_at(42))
    assert d.code == REFUSE


def test_an_unknown_ancestry_refuses_and_is_not_read_as_a_plain_no():
    """`--heavy-is-ancestor` neither true nor false must refuse, not hold."""
    assert sync._bool_arg("maybe") is None
    d = sync.decide(main_live=A, heavy_live=B, heavy_is_ancestor=None, now=_at(42))
    assert d.code == REFUSE


def test_a_diverged_heavy_refuses_rather_than_rewinding_it():
    d = sync.decide(main_live=A, heavy_live=B, heavy_is_ancestor=False, now=_at(42))
    assert d.code == REFUSE
    assert "not a proven ancestor" in d.reason


# ── the asymmetry an attended run is allowed ───────────────────────────────────


def test_dispatch_bypasses_the_clock():
    inside = sync.decide(main_live=A, heavy_live=B, heavy_is_ancestor=True,
                         dispatched=False, now=_at(5))
    assert inside.code == HOLD
    forced = sync.decide(main_live=A, heavy_live=B, heavy_is_ancestor=True,
                         dispatched=True, now=_at(5))
    assert forced.code == PUSH


def test_dispatch_does_NOT_bypass_the_never_backwards_guard():
    """The one thing an attended run may never overrule.

    A `--dispatched` that also forced past divergence would make the flag a
    rewind switch — the single most dangerous thing this job could grow.
    """
    for minute in (5, 42):
        d = sync.decide(main_live=A, heavy_live=B, heavy_is_ancestor=False,
                        dispatched=True, now=_at(minute))
        assert d.code == REFUSE, minute


# ── ordering: the common run must not report a window it never needed ──────────


def test_already_in_sync_holds_before_the_window_is_consulted():
    """The overwhelmingly common run, at a minute that is OUTSIDE the band.

    If the window were consulted first this would say "outside the window",
    which reads as work pending when there is none.
    """
    d = sync.decide(main_live=A, heavy_live=A, heavy_is_ancestor=True, now=_at(5))
    assert d.code == HOLD
    assert "already on" in d.reason


def test_an_unreadable_sha_refuses_even_when_the_two_are_equal():
    """Two empty strings are equal — that must not read as "in sync"."""
    d = sync.decide(main_live="", heavy_live="", heavy_is_ancestor=True, now=_at(42))
    assert d.code == REFUSE


# ── inside the band, the happy path, and the CLI contract the workflow uses ────


def test_inside_the_band_it_pushes_and_outside_it_holds():
    opens, closes = sync.window_bounds()
    for minute in (opens, 42, closes):
        d = sync.decide(main_live=A, heavy_live=B, heavy_is_ancestor=True, now=_at(minute))
        assert d.code == PUSH, minute
    for minute in (opens - 1, closes + 1, 0, 15, 30):
        d = sync.decide(main_live=A, heavy_live=B, heavy_is_ancestor=True, now=_at(minute))
        assert d.code == HOLD, minute


def test_the_cli_exit_codes_are_the_codes_the_workflow_branches_on():
    """The workflow's `case` has arms for 0/1/2 and a catch-all; prove they exist."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "decide", "--main-live", A, "--heavy-live", A,
         "--heavy-is-ancestor", "true"],
        capture_output=True, text=True,
    )
    assert proc.returncode == HOLD
    assert "HOLD" in proc.stdout

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "decide", "--main-live", A, "--heavy-live", B,
         "--heavy-is-ancestor", "false"],
        capture_output=True, text=True,
    )
    assert proc.returncode == REFUSE
    assert "REFUSE" in proc.stdout


# ── the workflow and the script must agree ─────────────────────────────────────


def _cron() -> re.Match[str]:
    cron = re.search(r"cron:\s*'(\S+)\s+(\S+)\s+\S+\s+\S+\s+\S+'", WORKFLOW.read_text())
    assert cron, "no cron found in the workflow"
    return cron


def _cron_minutes() -> list[int]:
    """Every minute past the hour the schedule nominally fires.

    A comma list, because the minute field stopped being a single number when
    latency/362 raised the attempt count (16 nominal slots had delivered 4 runs).
    Deliberately NOT a general cron parser: a step (`*/20`) or a range (`34-50`)
    is refused here rather than silently accepted, because both forms would put
    fires outside the derived band and the test below would then be asserting
    something weaker than it reads.
    """
    field = _cron().group(1)
    assert re.fullmatch(r"\d{1,2}(,\d{1,2})*", field), (
        f"the cron minute field {field!r} is not a plain comma list. Steps and "
        "ranges are refused on purpose: they scatter fires outside the derived "
        "band, and `window_bounds()` — not the cron syntax — is what makes an "
        "attempt useful"
    )
    return [int(m) for m in field.split(",")]


def test_the_workflows_cron_minutes_are_inside_the_derived_band():
    """Kept for the punctual case, and NO LONGER the guard against syncing nothing.

    #5662: this assertion used to carry the docstring "a cron outside the band
    would HOLD every run — the job would stay green and sync nothing, which is
    this issue wearing a passing check". It was aimed at the right failure and
    keyed on the wrong quantity. Measured over all 100 `event=schedule` runs in
    this repo, **0 of 98 fired within 5 minutes of their slot** (median 239m),
    and four workflows with fixed cron minutes land across all six 10-minute
    buckets. The minute asserted here is therefore not the minute the job reads,
    so passing it never ruled the failure out — the sync-nothing guard is
    `test_enough_attempts_that_a_random_fire_minute_reaches_the_band` below.

    It still earns its place: it is the cross-check that a band moved by a
    corrected measurement did not leave the nominal schedule behind, and it is
    the property we would rely on again if the scheduler ever became punctual.

    EVERY minute is asserted, not the first (latency/362). At today's authorised
    single fire the two readings coincide, and the loop is kept deliberately: the
    moment anyone adds a minute it is the only thing standing between a
    multi-fire cron and a schedule whose extra attempts all land outside the band
    — `*/20` and an all-in-band list are indistinguishable under the scheduler we
    measured, but under a punctual one the first delivers a single useful attempt
    an hour. Checking only the first minute would pass both.
    """
    opens, closes = sync.window_bounds()
    outside = [m for m in _cron_minutes() if not (opens <= m <= closes)]
    assert not outside, (
        f"cron minutes {outside} are outside the derived band {opens}-{closes}: a "
        "fire there can only HOLD, so it is an attempt that cannot sync"
    )


def test_enough_attempts_that_a_random_fire_minute_reaches_the_band():
    """THE sync-nothing guard, keyed on the quantity that controls the outcome.

    Since the fire minute is effectively uniform (#5662, measured), the only
    lever on whether any run lands inside the band is HOW MANY runs there are.
    At the derived band's width a 3-hourly cron was 8 attempts/day => ~8.3h
    expected wait, against a design claiming to bound drift to ~3h.

    HOURLY IS NOT ENOUGH ON ITS OWN, and that is now the `workflow_run`
    trigger's job rather than the cron's (latency/362 measured why: "hourly =>
    24 attempts/day" counts SLOTS, and in the 16 nominal slots after this
    workflow landed the scheduler delivered 4 runs, ~6/day, while heavy sat
    7h06m / 81 commits behind main's live commit). The answer to a scheduler
    that cannot be trusted is not more tickets in the same lottery — it is a
    trigger correlated with the thing that creates the drift, which is the
    deploy. The cron is the backstop, and one hourly attempt is what it is
    AUTHORISED to be (Codex, 2026-09-13 07:44Z).

    So this test no longer licenses a raise, and the assertion below is the
    guard against re-deriving one: the arithmetic that argues for N>1 is still
    in the workflow and still correct, which is exactly why a lane can read it
    back as permission. It is not permission. Changing N is Alex's call, and
    the test says so at the point where someone would change it.

    Attempts are near-free by construction and that is asserted, not assumed:
    `decide` HOLDs on `main_live == heavy_live` BEFORE consulting the clock, so
    an extra run against an already-synced app never deploys. That ordering is
    what would make a future authorised raise cheap; if it is ever inverted,
    extra fires start cycling the worker and the raise must be re-priced.
    """
    hour_field = _cron().group(2)
    assert hour_field == "*", (
        f"heavy-sync must fire at least hourly, got hour field {hour_field!r}: the fire "
        "minute is not controllable (#5662), so attempts are the only lever on the band"
    )
    minutes = _cron_minutes()
    assert len(minutes) == 1, (
        f"heavy-sync fires {len(minutes)} time(s) an hour ({minutes}); the authorised "
        "cadence is ONE hourly attempt (Codex 2026-09-13 07:44Z). The in-band arithmetic "
        "in the workflow argues for more and is not an authorisation — a cadence that "
        "reaches master is still not approved. Raise it only on Alex's word, and "
        "re-measure the 4-of-16 delivery rate first; the durable fix is the "
        "`workflow_run` trigger, which fires on the deploy that creates the drift"
    )

    # The ordering that makes hourly attempts cheap. Out-of-band on purpose: if
    # the window were consulted first this would HOLD for the window's reason,
    # or PUSH, instead of reporting "nothing to do".
    opens, _ = sync.window_bounds()
    in_sync = sync.decide(
        main_live=A,
        heavy_live=A,
        heavy_is_ancestor=True,
        now=datetime(2026, 9, 12, 12, (opens - 5) % 60, tzinfo=timezone.utc),
    )
    assert in_sync.code == HOLD
    assert "nothing to do" in in_sync.reason


def test_the_workflow_gates_the_push_on_the_decision():
    """Not "does it mention the script" — does the PUSH depend on its verdict."""
    body = _workflow_code()
    assert "scripts/heavy_sync_decision.py decide" in body
    assert "DECISION=$?" in body
    # The push must come after the case that exits on HOLD/REFUSE.
    assert body.index("DECISION=$?") < body.index("git push heroku-heavy")
    # Precisely "no push forces", not "the string never appears": the rejection
    # branch legitimately EXPLAINS that it is not retrying with --force, and a
    # blanket scan would fail on that honest line while still passing a file
    # whose push forced under a variable.
    pushes = [ln for ln in body.splitlines() if "git push" in ln]
    assert pushes, "no push found in the workflow"
    assert all("--force" not in ln and "-f " not in ln for ln in pushes)


def test_the_workflow_targets_mains_live_ref_not_origin_master():
    """Heavy must never be ahead of the migrations the primary app applied.

    Heavy's release phase skips `alembic upgrade heads` but still runs
    `assert_migrations_applied.py`, so pushing origin/master could red the heavy
    release on a migration main has not applied yet.
    """
    body = _workflow_code()
    assert 'git push heroku-heavy "$MAIN_LIVE:refs/heads/master"' in body
    assert "origin/master" not in body


def test_the_sync_does_not_share_the_main_deploy_concurrency_group():
    """`heroku-deploy` coalesces PENDING jobs: 31 deploys/day would starve this."""
    body = WORKFLOW.read_text()
    assert "group: heavy-deploy" in body
    assert "group: heroku-deploy" not in body


# ---------------------------------------------------------------------------
# #5886 — the in-flight gate. The band cleared the rebuild by 19m44s and the
# same release still killed two other heavy jobs, because the band is derived
# against one of `worker-heavy`'s three scheduled residents.
# ---------------------------------------------------------------------------

BUSY, CLEAR = 1, 0

#: The inspect reading taken while the incident's own shape was live
#: (production, 2026-09-13T10:53:13Z): the matcher fired :50 and the typeahead
#: :53, exactly the two jobs the 09:53:58Z release cycled, with four non-heavy
#: tasks running beside them on the other two workers. Kept verbatim so the
#: gate is exercised against a payload the fleet really produced.
PRODUCTION_ACTIVE_1053Z = [
    "app.tasks.warm_prop_families",
    "app.tasks.poll_all_odds",
    "app.tasks.poll_live_prediction_markets",
    "app.tasks.prewarm_live_feed_shapes",
    "app.tasks.match_prediction_markets",
    "app.tasks.rebuild_typeahead_index",
]
#: The same endpoint 4 minutes earlier, when nothing heavy was running on the
#: realtime worker's side. `poll_live_prediction_markets` is the control: it is
#: active on almost every reading and must never be mistaken for a heavy job.
PRODUCTION_ACTIVE_NON_HEAVY = ["app.tasks.poll_live_prediction_markets"]


def _inspect_body(names, workers=3):
    """An `/api/admin/celery/inspect` body carrying `names` across `workers`."""
    body = {"_cache": {"cached": False, "age_s": 0.0}}
    for i in range(workers):
        body[f"celery@worker-{i}"] = {
            "total_registered": 190,
            "taxonomy_tasks": [],
            "active": [],
            "reserved_count": 0,
            "reserved_sample": [],
        }
    for i, name in enumerate(names):
        body[f"celery@worker-{i % max(1, workers)}"]["active"].append(
            {"name": name, "id": f"id-{i}"}
        )
    return body


def _heavy_set():
    """The heavy task set as the script parses it out of the app."""
    source = (REPO / "backend" / "app" / "tasks" / "__init__.py").read_text()
    return sync.heavy_task_names(source)


def test_the_heavy_task_set_is_the_one_the_app_routes_on():
    """The parse must equal `app.tasks.HEAVY_TASKS`, both directions.

    The script cannot import celery — it runs on a bare runner — so the set has
    to be read out of the source. A COPY would have been the obvious move and
    is the one this repo has already paid for twice: #5878 found two drifted
    copies of a normaliser table, one carrying `ß` and the other `æ`. So the
    only defence is that the two records are asserted equal, in a test that can
    import the real one.
    """
    from app.tasks import HEAVY_TASKS

    parsed = _heavy_set()
    assert parsed is not None
    assert set(parsed) == set(HEAVY_TASKS), {
        "only in the parse": sorted(set(parsed) - set(HEAVY_TASKS)),
        "only in the app": sorted(set(HEAVY_TASKS) - set(parsed)),
    }
    # The residents this gate exists for, named rather than implied.
    for resident in (
        "app.tasks.precompute_calibration_main",
        "app.tasks.match_prediction_markets",
        "app.tasks.rebuild_typeahead_index",
    ):
        assert resident in parsed


@pytest.mark.parametrize(
    "source",
    [
        "",                                   # nothing at all
        "OTHER = {'app.tasks.x'}",            # a different assignment
        "HEAVY_TASKS = compute_the_set()",    # not a literal
        "HEAVY_TASKS = set()",                # a call, not a literal
        "HEAVY_TASKS = []",                   # a literal that parsed and is empty
        "HEAVY_TASKS = {A_NAME, ANOTHER}",    # a literal holding no strings
        "HEAVY_TASKS = {",                    # does not parse
    ],
)
def test_an_unreadable_task_set_is_unknown_and_never_an_empty_one(source):
    """`frozenset()` would declare the worker idle for every reading.

    This is gotcha #53 as a gate: "I could not tell" and "nothing is running"
    are opposite facts, and the empty set is the shape that makes them read
    alike. The caller PROCEEDS on unknown, so the harm is a missed veto — but
    it must be reported as unknown, not as a clean fleet.
    """
    assert sync.heavy_task_names(source) is None


# ---------------------------------------------------------------------------
# #5886 residual (b) — WHAT RUNS ON worker-heavy IS NOT `HEAVY_TASKS`
# ---------------------------------------------------------------------------


def _authored_set():
    """The beats authored onto the heavy queue, as the script parses them."""
    source = (REPO / "backend" / "app" / "tasks" / "__init__.py").read_text()
    return sync.heavy_queue_beat_tasks(source)


#: The three the gap was found on, and the minute each fires. Named rather than
#: derived, so that moving one is a decision somebody makes here and not a
#: number that quietly follows the app.
AUTHORED_HEAVY_BEATS = {
    "app.tasks.refresh_linked_polymarket_books": 38,
    "app.tasks.refresh_linked_game_books": 20,
    "app.tasks.refresh_dated_fixture_starts": 7,
}


def test_three_beats_run_on_worker_heavy_without_being_in_heavy_tasks():
    """The defect, stated as the two facts that make it one.

    A beat entry carrying `options={"queue": "heavy"}` runs on worker-heavy
    whether or not its task is in `HEAVY_TASKS`, because `apply_async(queue=…)`
    overrules `task_routes`. The gate read membership, so these three were
    invisible to it and a sync could cycle the dyno on top of one.

    BOTH halves are asserted, because either alone is vacuous: that the parse
    finds them (or the test proves nothing about this file) and that they are
    genuinely NOT members (or it proves nothing about the gap). If someone
    closes the gap the other way — by adding them to `HEAVY_TASKS` — this test
    fails loudly and is the right place to record that, rather than passing
    while its subject has moved.
    """
    from app.tasks import HEAVY_TASKS

    authored = _authored_set()
    assert authored is not None
    for task in AUTHORED_HEAVY_BEATS:
        assert task in authored, sorted(authored)
        assert task not in HEAVY_TASKS


def test_the_gates_set_is_exactly_the_two_arms_and_is_wider_than_either():
    """The composed set, checked against the app's own objects both ways."""
    from app.tasks import HEAVY_TASKS

    declared, authored = _heavy_set(), _authored_set()
    composed = sync.heavy_worker_task_names(declared, authored)
    assert composed == frozenset(HEAVY_TASKS) | authored
    # Non-vacuous: the union really did add something, and lost nothing.
    assert composed > frozenset(HEAVY_TASKS)
    assert frozenset(HEAVY_TASKS) <= composed and authored <= composed


def test_the_price_refresher_the_gate_could_not_see_fires_inside_the_band():
    """Why this is a reader's bug and not a tidiness one.

    `refresh_linked_polymarket_books` gives a LINKED market with no outcome rows
    a price (#3613); its Kalshi twin does the same (#3518). The first fires at
    :38 — `window_bounds()`'s opening minute — so the gate was blind exactly
    where a push happens. The minute is read from the app's beat literal, never
    from this file, so moving the beat moves the assertion with it.
    """
    opens, closes = sync.window_bounds()
    minute = _beat_minute("refresh-linked-polymarket-books-hourly")
    assert minute == AUTHORED_HEAVY_BEATS["app.tasks.refresh_linked_polymarket_books"]
    assert opens <= minute <= closes, (opens, minute, closes)


def _beat_minute(beat_key: str) -> int:
    """The `crontab(minute=N)` of one beat, read from the app's live schedule."""
    from app.tasks import celery_app

    return int(str(celery_app.conf.beat_schedule[beat_key]["schedule"]._orig_minute))


def test_the_gate_holds_on_a_job_only_the_beat_literal_names():
    """The verdict, and the control that proves the old reading was the defect.

    Same payload, two sets: the composed one HOLDS and the declared-only one
    proceeds. The second assertion is the bug as it stood, pinned so nobody
    re-narrows the set and finds every test still green.
    """
    payload = _inspect_body(["app.tasks.refresh_linked_polymarket_books"])
    active = sync.active_task_names(payload)

    held = sync.inflight_verdict(
        active=active,
        heavy=sync.heavy_worker_task_names(_heavy_set(), _authored_set()),
    )
    assert held.code == BUSY
    assert "refresh_linked_polymarket_books" in held.reason

    blind = sync.inflight_verdict(active=active, heavy=_heavy_set())
    assert blind.code == CLEAR


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # The shape the gap is made of: heavy in the options, not a member.
        (
            "celery_app.conf.beat_schedule = {'b': {'task': 'app.tasks.x',"
            " 'options': {'queue': 'heavy'}}}",
            {"app.tasks.x"},
        ),
        # Another queue is not this queue.
        (
            "celery_app.conf.beat_schedule = {'b': {'task': 'app.tasks.x',"
            " 'options': {'queue': 'background'}}}",
            set(),
        ),
        # No options at all — routed by `task_routes`, which the other arm reads.
        ("celery_app.conf.beat_schedule = {'b': {'task': 'app.tasks.x'}}", set()),
        # A computed queue is not a literal one and must not be guessed at.
        (
            "celery_app.conf.beat_schedule = {'b': {'task': 'app.tasks.x',"
            " 'options': {'queue': QUEUE}}}",
            set(),
        ),
        # A computed TASK cannot be named, so it cannot be held on.
        (
            "celery_app.conf.beat_schedule = {'b': {'task': NAME,"
            " 'options': {'queue': 'heavy'}}}",
            set(),
        ),
        # An empty schedule is a real, readable answer: nothing is authored.
        ("celery_app.conf.beat_schedule = {}", set()),
    ],
)
def test_the_beat_arm_reads_the_literal_and_nothing_else(source, expected):
    assert sync.heavy_queue_beat_tasks(source) == frozenset(expected)


@pytest.mark.parametrize(
    "source",
    [
        "",                                        # nothing at all
        "OTHER = {'a': 1}",                        # a different assignment
        "celery_app.conf.beat_schedule = build()",  # not a literal
        "celery_app.conf.other_attr = {}",          # the wrong attribute
        "celery_app.conf.beat_schedule = {",        # does not parse
    ],
)
def test_an_unreadable_schedule_is_unknown_and_not_an_empty_authored_set(source):
    """`frozenset()` and `None` are different answers here, unlike above.

    Empty means "no beat is authored onto the queue", which is an ordinary state
    of the real file and must stay distinguishable from "the literal is gone" —
    the caller says the second out loud and does not say the first.
    """
    assert sync.heavy_queue_beat_tasks(source) is None


def test_a_lost_beat_arm_narrows_to_the_old_set_and_a_lost_member_set_is_unknown():
    """The two arms fail differently, and the composer keeps them different.

    Losing `beat_schedule` puts the gate back to exactly the reading it had
    before this arm existed — degraded, still a veto. Losing `HEAVY_TASKS` is
    the gotcha-#53 case the existing test protects and stays UNKNOWN, which
    PROCEEDS: a cost gate that cannot read its fact must never stop the sync.
    """
    declared = frozenset({"app.tasks.a"})
    authored = frozenset({"app.tasks.b"})
    assert sync.heavy_worker_task_names(declared, None) == declared
    assert sync.heavy_worker_task_names(None, authored) is None
    assert sync.heavy_worker_task_names(None, None) is None
    assert sync.heavy_worker_task_names(declared, frozenset()) == declared


def test_the_cli_holds_on_the_beat_only_job_and_says_when_it_lost_the_arm(
    tmp_path, capsys
):
    """The wiring, which is the half a pure-function test cannot reach.

    A composed set that never reaches `inflight_verdict` is a fix that reads
    right and does nothing (the repo has paid for that shape). So the CLI is
    driven against the app's REAL source with a payload naming a beat-only job,
    and separately against a source whose schedule it cannot read — where the
    veto survives on the declared arm and the narrowing is said on stderr.
    """
    body = tmp_path / "inspect.json"
    body.write_text(json.dumps(_inspect_body(["app.tasks.refresh_linked_game_books"])))
    assert sync.main(["inflight", "--inspect-json", str(body)]) == BUSY
    assert "refresh_linked_game_books" in capsys.readouterr().out

    partial = tmp_path / "tasks.py"
    partial.write_text("HEAVY_TASKS = {'app.tasks.match_prediction_markets'}\n")
    still_busy = tmp_path / "declared.json"
    still_busy.write_text(
        json.dumps(_inspect_body(["app.tasks.match_prediction_markets"]))
    )
    assert (
        sync.main(
            [
                "inflight",
                "--inspect-json", str(still_busy),
                "--tasks-source", str(partial),
            ]
        )
        == BUSY
    )
    captured = capsys.readouterr()
    assert "beat_schedule" in captured.err
    # The narrowing goes to stderr ONLY: the workflow parses the verdict off
    # stdout with `${INFLIGHT_OUT%%:*}` and a second line there would become it.
    assert captured.out.startswith("BUSY:")
    assert "\n" not in captured.out.strip()


def test_the_workflows_prose_no_longer_states_the_reading_that_was_wrong():
    """Read the RAW file, comments included — the assertion IS about the prose.

    `_workflow_code()` strips comments on purpose, because a code assertion that
    matches an explanation measures nothing. This one is the other kind: the
    comment block is where a reader learns what the in-flight gate can see, and
    it said "`HEAVY_TASKS` membership is what names the heavy fleet in it",
    which was the false sentence behind #5886's second residual. A file that
    describes a narrower reading than its script performs is the same drift as a
    beat literal that says `background` while the loop routes it to `heavy`.
    """
    raw = WORKFLOW.read_text()
    assert "membership is what names" not in raw
    assert "heavy_queue_beat_tasks" in raw
    assert "refresh_linked_polymarket_books" in raw


def test_a_reply_naming_no_worker_is_unknown_not_an_idle_fleet():
    """A failed broadcast returns a body with only `_cache` in it.

    `/api/admin/celery/inspect` composes its reply from the inspect maps, so a
    broker that answered nothing yields no worker keys — the same SHAPE as an
    idle fleet and the opposite MEANING. Three workers have replied to every
    reading taken of this endpoint.
    """
    assert sync.active_task_names({"_cache": {"cached": False}}) is None
    assert sync.active_task_names(None) is None
    assert sync.active_task_names([]) is None
    # A worker that replied with an empty active list IS idle, and must not be
    # confused with the case above.
    assert sync.active_task_names(_inspect_body([])) == []


def test_the_incidents_own_reading_holds_the_sync():
    """The 09:53:58Z release, re-judged against a payload from the same shape."""
    verdict = sync.inflight_verdict(
        active=sync.active_task_names(_inspect_body(PRODUCTION_ACTIVE_1053Z)),
        heavy=_heavy_set(),
    )
    assert verdict.code == BUSY
    assert verdict.verdict == "BUSY"
    # It names what it saw — a hold nobody can read is a hold nobody trusts.
    assert "match_prediction_markets" in verdict.reason
    assert "rebuild_typeahead_index" in verdict.reason


def test_a_busy_realtime_worker_is_not_a_busy_heavy_one():
    """The control. `poll_live_prediction_markets` runs on the 2-minute realtime
    beat and is active on nearly every reading; a gate that held on it would
    hold forever, which is #5470 again with a tidier reason.
    """
    verdict = sync.inflight_verdict(
        active=sync.active_task_names(_inspect_body(PRODUCTION_ACTIVE_NON_HEAVY)),
        heavy=_heavy_set(),
    )
    assert verdict.code == CLEAR
    assert verdict.verdict == "IDLE"


def test_an_unreadable_fact_proceeds_because_this_is_a_cost_gate():
    """Both halves of the fact, each unreadable on its own.

    The polarity is the one `decide` states: a killed heavy job self-heals on
    its next beat (the 09:53 matcher restarted 10:05 and succeeded 10:09:37),
    while a sync that cannot happen is silent unbounded drift. So unknown
    proceeds — and says so, rather than printing IDLE and inviting the reading
    that the fleet was checked.
    """
    no_set = sync.inflight_verdict(active=[], heavy=None)
    assert (no_set.code, no_set.verdict) == (CLEAR, "UNKNOWN")
    assert "HEAVY_TASKS" in no_set.reason

    no_reply = sync.inflight_verdict(active=None, heavy=_heavy_set())
    assert (no_reply.code, no_reply.verdict) == (CLEAR, "UNKNOWN")
    assert "did not answer" in no_reply.reason


def test_an_attended_run_bypasses_the_in_flight_veto():
    """Same licence as the clock and the floor: a person may accept one lost
    pass to get the code onto the worker now. It is still not a licence over
    the never-backwards guard, which `decide` owns and this gate never sees.
    """
    verdict = sync.inflight_verdict(
        active=sync.active_task_names(_inspect_body(PRODUCTION_ACTIVE_1053Z)),
        heavy=_heavy_set(),
        dispatched=True,
    )
    assert verdict.code == CLEAR
    assert verdict.verdict == "BYPASSED"


def test_the_cli_holds_on_a_busy_fleet_and_proceeds_on_a_missing_file(tmp_path):
    """Exit codes, because the workflow branches on them and nothing else."""
    busy = tmp_path / "busy.json"
    busy.write_text(json.dumps(_inspect_body(PRODUCTION_ACTIVE_1053Z)))
    assert sync.main(["inflight", "--inspect-json", str(busy)]) == BUSY

    idle = tmp_path / "idle.json"
    idle.write_text(json.dumps(_inspect_body(PRODUCTION_ACTIVE_NON_HEAVY)))
    assert sync.main(["inflight", "--inspect-json", str(idle)]) == CLEAR

    # The three ways the workflow's `curl` can leave the file useless. None of
    # them may raise, because a traceback exits non-zero and the workflow reads
    # non-zero as a hold.
    missing = tmp_path / "never-written.json"
    assert sync.main(["inflight", "--inspect-json", str(missing)]) == CLEAR
    empty = tmp_path / "empty.json"
    empty.write_text("")
    assert sync.main(["inflight", "--inspect-json", str(empty)]) == CLEAR
    html = tmp_path / "html.json"
    html.write_text("<html>502 Bad Gateway</html>")
    assert sync.main(["inflight", "--inspect-json", str(html)]) == CLEAR


def test_the_cli_reads_the_apps_real_task_file_by_default(tmp_path, capsys):
    """The default path resolves from the SCRIPT's location, not the cwd.

    A workflow step runs from the checkout root today, and a relative default
    would turn into UNKNOWN — a silently disabled veto — the first time anything
    ran it from anywhere else.
    """
    busy = tmp_path / "busy.json"
    busy.write_text(json.dumps(_inspect_body(["app.tasks.match_prediction_markets"])))
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert sync.main(["inflight", "--inspect-json", str(busy)]) == BUSY
    finally:
        os.chdir(cwd)
    assert "match_prediction_markets" in capsys.readouterr().out


def test_the_workflow_gates_the_push_on_the_in_flight_verdict():
    """Not "does it call the gate" — does the PUSH depend on it, and is the
    read tagged as machine traffic against our own host (notice 39)."""
    body = _workflow_code()
    assert "heavy_sync_decision.py inflight" in body
    assert "INFLIGHT=$?" in body
    assert body.index("INFLIGHT=$?") < body.index("git push heroku-heavy")
    # The gate runs AFTER the cheap local verdict, so the ~90% of runs that hold
    # on "already in sync" never touch the admin API at all.
    assert body.index("DECISION=$?") < body.index("INFLIGHT=$?")
    # Our host, so it carries the origin tag; the script cannot import the
    # carrier, which is why the read lives in the workflow.
    curl_line = next(
        ln for ln in body.splitlines() if "api/admin/celery/inspect" in ln
    )
    # The WHOLE url, by equality. `"api.bainluck.com" in line` is the substring
    # check CodeQL calls `py/incomplete-url-substring-sanitization` and it is
    # right to: the host it matches can sit anywhere, so `evil.test/?r=api.
    # bainluck.com` satisfies it. Here that would pass a workflow reading the
    # active fleet off somebody else's box.
    url = re.search(r'"(https://[^"]+)"', curl_line)
    assert url and url.group(1) == "https://api.bainluck.com/api/admin/celery/inspect"
    assert "X-BainLuck-Origin" in body
    # One read is not a reading: two of eight calls to this endpoint returned
    # HTTP 500 when it was measured (2026-09-13 11:02-11:03Z). UNKNOWN proceeds,
    # so a flaky instrument does not break the sync — it quietly turns the veto
    # off, which is worse than failing, because the gate still reads as present.
    assert "--retry" in body


# ---------------------------------------------------------------------------
# #5470 — BUSY IS "NOT YET". The three gates (band, cycle floor, in-flight) each
# hold for a good reason and composed into a convergence rate of ~zero: heavy
# sat 299 min / 75 commits behind at 14:53Z on 2026-09-13 with five
# `backend/app/tasks` files dark, and in those five hours exactly one trigger
# cleared band AND floor (14:46:23Z, run 34763629805) and held on a busy worker.
# Sampled on the minute after it: BUSY at :54/:55/:56/:57 and IDLE at :58:02,
# still inside the band. So the read is repeated until the band closes.
#
# The property these pin is that waiting is strictly more chances at the SAME
# verdict — it can never push in a state one read would not have pushed in, and
# it can never reach past the band, because its deadline IS the band.
# ---------------------------------------------------------------------------


def test_the_wait_deadline_is_the_band_and_never_a_number_of_its_own():
    """A second constant here would be a second answer to one question."""
    opens, closes = sync.window_bounds()
    # The whole band, asked at its opening second.
    assert sync.band_seconds_left(_at(opens)) == (closes - opens + 1) * 60
    # Halfway through, exactly the remainder — no rounding to a whole minute.
    assert sync.band_seconds_left(_at(50).replace(second=17)) == (closes - 50 + 1) * 60 - 17


def test_moving_a_measured_constant_moves_the_deadline(monkeypatch):
    """The same derivation test the band itself carries — the deadline is not
    allowed to be a literal that happens to match today's edges."""
    before = sync.band_seconds_left(_at(50))
    monkeypatch.setattr(sync, "CLOSE_MARGIN_MIN", sync.CLOSE_MARGIN_MIN + 3)
    after = sync.band_seconds_left(_at(50))
    assert after == before - 3 * 60


def test_the_deadline_and_the_window_agree_at_every_minute_of_the_hour():
    """One fact, two readers: "may I push" and "is it worth waiting" must never
    disagree about where the band is. Every minute, so no edge is assumed."""
    for minute in range(60):
        now = _at(minute)
        assert (sync.band_seconds_left(now) > 0) is sync.inside_window(now), minute


def test_the_last_second_of_the_band_is_still_inside_it():
    """`inside_window` is minute-inclusive, so the edge is the END of `closes`.
    An off-by-one here would throw away the final minute of every band — which
    is exactly the minute the 14:58:02Z idle reading landed in."""
    _, closes = sync.window_bounds()
    last = _at(closes).replace(second=59)
    assert sync.inside_window(last)
    assert sync.band_seconds_left(last) == 1
    assert sync.band_seconds_left(_at(closes)) == 60


def test_the_deadline_carries_the_hour_rather_than_going_negative(monkeypatch):
    """If a re-measurement ever pushes `closes` to 59, the edge is the NEXT
    hour's :00 — arithmetic that clamps instead would silently stop waiting a
    minute early forever."""
    monkeypatch.setattr(sync, "window_bounds", lambda: (38, 59))
    monkeypatch.setattr(
        sync, "inside_window", lambda now: 38 <= now.astimezone(timezone.utc).minute <= 59
    )
    assert sync.band_seconds_left(_at(59).replace(second=30)) == 30


def test_the_deadline_is_zero_outside_the_band():
    opens, closes = sync.window_bounds()
    assert sync.band_seconds_left(_at(opens - 1)) == 0
    assert sync.band_seconds_left(_at((closes + 1) % 60)) == 0


def test_the_deadline_subcommand_prints_the_number_alone_and_exits_zero():
    """`age`'s contract, for `age`'s reason: the caller captures the string, and
    a non-zero would let the wait's own deadline fail a healthy job."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "band-seconds-left"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    assert out.isdigit(), out
    # Self-consistent at whatever minute it really is — the one clock-reading
    # assertion that holds at every minute of the day (gotcha #44).
    assert 0 <= int(out) <= (sync.window_bounds()[1] - sync.window_bounds()[0] + 1) * 60


# ── and the loop itself, RUN rather than grepped ───────────────────────────────
#
# A `"while true" in body` assertion is a source scan: it passes on a loop that
# spins forever, on one that never sleeps, and on one that pushes on a stale
# payload. So the block is lifted out of the YAML and executed, with `curl`,
# `sleep` and the DEADLINE stubbed and the REAL decision script judging the
# payloads. The clock never enters: the deadline stub is a scripted sequence,
# which is the only way to test a module that deliberately has no `--now`.

BUSY_BODY = json.dumps(
    {"celery@one": {"active": [{"name": "app.tasks.match_prediction_markets"}]}}
)
IDLE_BODY = json.dumps({"celery@one": {"active": []}})


def _extract_wait_loop() -> str:
    lines = _workflow_code().splitlines()
    # From the streak's initialiser, not from `while`: the counter is read
    # inside the loop, so a block that starts one line later runs under `set -u`
    # against an unset variable and the harness fails for its own reason.
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "IDLE_STREAK=0")
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == "done")
    return "\n".join(ln[10:] for ln in lines[start:end + 1])


def _run_wait_loop(
    tmp_path, *, bodies, deadlines, dispatched=False, curl_fails=False, age=""
):
    """Run the workflow's wait loop against a scripted fleet. Returns
    (INFLIGHT exit code, curl calls, sleeps).

    ``age`` is `HEAVY_AGE_MIN` as `read_facts` stamped it — the fact the veto's
    expiry is asked about at the edge (#5886). It defaults to the empty string,
    which is UNREADABLE and holds, so every test written before the expiry
    existed keeps the behaviour it was written against.
    """
    stub = tmp_path / "stub"
    stub.mkdir(parents=True)
    state = tmp_path / "state"
    state.mkdir(parents=True)
    (state / "bodies").write_text("\n".join(bodies))
    (state / "deadlines").write_text("\n".join(str(d) for d in deadlines))

    (stub / "curl").write_text(
        "#!/bin/bash\n"
        f"n=$(cat {state}/curls 2>/dev/null || echo 0); n=$((n+1)); echo $n > {state}/curls\n"
        + ("exit 22\n" if curl_fails else
           "out=''\n"
           'while [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done\n'
           f"body=$(sed -n \"${{n}}p\" {state}/bodies)\n"
           '[ -n "$body" ] || exit 22\n'
           'printf %s "$body" > "$out"\n')
    )
    (stub / "sleep").write_text(
        "#!/bin/bash\n"
        f"n=$(cat {state}/sleeps 2>/dev/null || echo 0); echo $((n+1)) > {state}/sleeps\n"
    )
    # One shim for both script calls: the deadline is scripted, everything else
    # is the real module, so the gate under test is never faked.
    (stub / "python3").write_text(
        "#!/bin/bash\n"
        'case "$*" in\n'
        "  *band-seconds-left*)\n"
        f"    n=$(cat {state}/deadline_reads 2>/dev/null || echo 0); n=$((n+1))\n"
        f"    echo $n > {state}/deadline_reads\n"
        f"    sed -n \"${{n}}p\" {state}/deadlines\n"
        "    ;;\n"
        f'  *) exec "{sys.executable}" "$@" ;;\n'
        "esac\n"
    )
    for name in ("curl", "sleep", "python3"):
        (stub / name).chmod(0o755)

    script = tmp_path / "loop.sh"
    script.write_text(
        "set -uo pipefail\n"
        f'INSPECT_JSON="{tmp_path}/inspect.json"\n'
        'ADMIN_TOKEN="token"\n'
        f'DISPATCH_FLAG="{"--dispatched" if dispatched else ""}"\n'
        f'HEAVY_AGE_MIN="{age}"\n'
        + _extract_wait_loop()
        + '\necho "INFLIGHT=$INFLIGHT VETO_EXPIRED=[$VETO_EXPIRED]"\n'
    )
    proc = subprocess.run(
        ["bash", str(script)],
        capture_output=True, text=True, cwd=str(REPO),
        env={**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"},
        timeout=60,
    )
    assert "INFLIGHT=" in proc.stdout, proc.stdout + proc.stderr
    tail = proc.stdout.rsplit("INFLIGHT=", 1)[1]
    code = int(tail.split()[0])
    # Read from the shell variable rather than inferred from `code`, because the
    # whole point of the flag is that code 0 no longer means one thing: the two
    # ways to reach it — a clear fleet and a cycled one — must stay tellable
    # apart by anything that reads this loop, the log summary included.
    veto_expired = tail.split("VETO_EXPIRED=[", 1)[1].split("]", 1)[0] != ""
    reads = int((state / "curls").read_text()) if (state / "curls").exists() else 0
    sleeps = int((state / "sleeps").read_text()) if (state / "sleeps").exists() else 0
    return code, reads, sleeps, veto_expired


def test_a_busy_worker_is_waited_out_and_the_idle_moment_is_taken(tmp_path):
    """The 14:46Z run, replayed: busy, busy, then the :58 idle it never saw.

    The idle now has to be seen TWICE before the push (#5886), so the run that
    used to end on read 3 ends on read 4 — the same verdict, one poll later.
    """
    code, reads, sleeps, _ = _run_wait_loop(
        tmp_path,
        bodies=[BUSY_BODY, BUSY_BODY, IDLE_BODY, IDLE_BODY],
        deadlines=[600, 540, 480],
    )
    assert code == 0
    assert (reads, sleeps) == (4, 3)


def test_the_wait_stops_at_the_bands_edge_and_holds(tmp_path):
    """Waiting may cost the run; it may never cost the rebuild. At the edge the
    verdict is still BUSY, which the step below turns into a green HOLD."""
    code, reads, sleeps, _ = _run_wait_loop(
        tmp_path, bodies=[BUSY_BODY, BUSY_BODY, IDLE_BODY], deadlines=[600, 30]
    )
    assert code == 1
    # It stopped BEFORE the idle payload — the band, not the fleet, ended it.
    assert (reads, sleeps) == (2, 1)


def test_an_unreadable_deadline_stops_the_wait_rather_than_licensing_it(tmp_path):
    """`[ "" -le 56 ]` exits 2, which an `if` reads as false — i.e. as
    permission to sleep again. Anything but digits must mean stop."""
    for bad in ("", "unreadable", "-1"):
        code, reads, sleeps, _ = _run_wait_loop(
            tmp_path / bad.replace("-", "neg") if bad else tmp_path / "empty",
            bodies=[BUSY_BODY, IDLE_BODY], deadlines=[bad],
        )
        assert (code, reads, sleeps) == (1, 1, 0), bad


def test_one_idle_reading_is_not_enough_to_push(tmp_path):
    """v15, replayed: the gate printed IDLE at 16:57:10Z while
    `matching_reconciliation` had been running since 16:56:59.9Z.

    The reply is a SNAPSHOT of unknown age — 5 s of endpoint cache, a 25.6 s
    measured broadcast, two retries — so one reading cannot see a job that
    started inside it. An idle fleet now costs exactly one poll to confirm.
    """
    code, reads, sleeps, _ = _run_wait_loop(
        tmp_path, bodies=[IDLE_BODY, IDLE_BODY], deadlines=[600, 540]
    )
    assert (code, reads, sleeps) == (0, 2, 1)


def test_a_job_the_first_snapshot_could_not_see_is_caught_by_the_second(tmp_path):
    """The whole point, stated as the failure it prevents.

    Read 1 is the stale snapshot that says IDLE; read 2 is the one that can see
    the job. The loop must NOT have pushed on read 1, and having found a busy
    fleet it goes back to waiting — the streak resets.
    """
    code, reads, sleeps, _ = _run_wait_loop(
        tmp_path,
        bodies=[IDLE_BODY, BUSY_BODY, IDLE_BODY, IDLE_BODY],
        deadlines=[600, 540, 480, 420],
    )
    assert code == 0
    # 1 idle, 1 busy (streak reset), then the two that confirm each other.
    assert (reads, sleeps) == (4, 3)


def test_a_busy_reading_resets_the_streak_rather_than_counting_toward_it(tmp_path):
    """Two idle readings with a busy one between them are not a confirmation —
    they are two first readings. Only the band may end the wait early."""
    code, reads, sleeps, _ = _run_wait_loop(
        tmp_path,
        bodies=[IDLE_BODY, BUSY_BODY, IDLE_BODY, BUSY_BODY, IDLE_BODY, IDLE_BODY],
        deadlines=[600, 540, 480, 420, 360, 300],
    )
    assert (code, reads, sleeps) == (0, 6, 5)


def test_the_confirm_degrades_to_a_single_read_at_the_edge(tmp_path):
    """THE CONFIRM MAY COST A POLL; IT MAY NEVER COST A CYCLE.

    At the band's edge an unconfirmed IDLE pushes — which is exactly the
    reading this gate used before the confirm existed. So the confirm is
    strictly additional safety inside the band and takes nothing away at it.

    THE DEADLINE HERE USED TO BE `30`, WHICH IS WHY THIS TEST WAS GREEN WHILE
    THE PROPERTY IT NAMES WAS FALSE (#6283). 30 was the threshold's own value:
    the one input at which the branch cannot be wrong. Run 117 on 2026-09-15
    entered the confirm with 36 s left, spent 55.7 s in it, and lost the cycle
    to the very fallback this docstring says it degrades to. So the deadlines
    are now swept across the turn, and the first of them is that specimen.
    """
    for deadline in (1, 30, 36, sync.CONFIRM_SEPARATION_SECONDS):
        code, reads, sleeps, _ = _run_wait_loop(
            tmp_path / f"d{deadline}", bodies=[IDLE_BODY, IDLE_BODY],
            deadlines=[deadline],
        )
        assert (code, reads, sleeps) == (0, 1, 0), (
            f"{deadline}s of band left is less than one turn of the loop "
            f"({sync.CONFIRM_SEPARATION_SECONDS}s), so the confirm spent a "
            "cycle it could not finish paying for"
        )

    # And the reverse population, or the assertion above is satisfiable by a
    # loop that never confirms at all: one second past a whole turn, there is
    # room to confirm and the confirm happens.
    code, reads, sleeps, _ = _run_wait_loop(
        tmp_path / "affordable",
        bodies=[IDLE_BODY, IDLE_BODY],
        deadlines=[sync.CONFIRM_SEPARATION_SECONDS + 1],
    )
    assert (code, reads, sleeps) == (0, 2, 1)


def test_the_bands_edge_is_a_whole_turn_of_the_wait_loop():
    """THE EDGE IS A VERDICT, SO IT IS DERIVED — the rule the script states
    about itself and the YAML did not keep.

    A turn is the sleep AND the read it ends on. `INFLIGHT_POLL_SECONDS` alone
    under-states it by the whole broadcast, and every second of the gap is an
    hour of `bainluck-heavy` serving code the main app has stopped serving.
    """
    loop = _extract_wait_loop()
    assert f'"$BAND_LEFT" -le {sync.CONFIRM_SEPARATION_SECONDS} ]' in loop, (
        "the wait loop's edge is not the derived turn cost; two copies of one "
        "number is how a comment becomes a story about a value nothing enforces"
    )
    # Derived, and derived UPWARDS: a turn is strictly more than its sleep.
    assert (
        sync.CONFIRM_SEPARATION_SECONDS
        == sync.INFLIGHT_POLL_SECONDS + sync.INFLIGHT_READ_SECONDS
    )
    assert sync.INFLIGHT_READ_SECONDS >= 26, (
        "the inspect broadcast measured 25.6-29.6 s over eight production "
        "reads; rounding it DOWN puts the edge back inside a turn"
    )
    # A turn still has to fit in the band, or the loop would break on its first
    # read at every minute and the confirm would never run at all.
    band_s = (sync.window_bounds()[1] - sync.window_bounds()[0] + 1) * 60
    assert sync.CONFIRM_SEPARATION_SECONDS * sync.IDLE_CONFIRMATIONS < band_s


def test_the_workflow_confirms_the_number_of_times_the_script_documents():
    """Two copies of one number is how a comment becomes a story about a value
    nothing enforces — the same rule `INFLIGHT_POLL_SECONDS` is held to."""
    loop = _extract_wait_loop()
    assert f'-ge {sync.IDLE_CONFIRMATIONS} ]' in loop
    # It is a sample COUNT, not a threshold, but it still has to be a count the
    # band can afford: the confirmations plus the polls between them must fit
    # inside the band with room to push, or the gate would be spending the
    # cycle it exists to deliver.
    band_s = (sync.window_bounds()[1] - sync.window_bounds()[0] + 1) * 60
    assert sync.IDLE_CONFIRMATIONS >= 2, "one reading cannot confirm itself"
    assert sync.IDLE_CONFIRMATIONS * sync.INFLIGHT_POLL_SECONDS < band_s


def test_the_confirm_poll_can_never_be_served_two_copies_of_one_snapshot():
    """THE ONE CHANGE THAT WOULD MAKE THE CONFIRM UNFALSIFIABLE.

    `/api/admin/celery/inspect` memoises its broadcast set for `_INSPECT_TTL_S`
    (5 s, and that constant exists because this endpoint took production down —
    LAT-P071). So if the sleep between confirmations ever drops below the memo,
    the second reading is not a second reading: it is a byte-for-byte replay of
    the first, and `IDLE_CONFIRMATIONS = 2` becomes a confirm that cannot fail.

    That is a live temptation rather than a hypothetical one. The confirm's
    blind window is the SEPARATION of two readings (~25.6 s of broadcast plus
    this sleep, ~56 s), and the obvious way to narrow it is to poll faster.
    This is the floor under that instinct; the ceiling is LAT-P071 itself.
    """
    from app.routes.admin_celery import _INSPECT_TTL_S

    assert sync.INFLIGHT_POLL_SECONDS > _INSPECT_TTL_S, (
        f"the confirm sleeps {sync.INFLIGHT_POLL_SECONDS}s but the endpoint "
        f"serves a cached snapshot for {_INSPECT_TTL_S}s — the two "
        "confirmations would be one reading counted twice"
    )


def test_an_attended_run_never_waits(tmp_path):
    """`--dispatched` BYPASSES the veto, so there is nothing to wait for; a wait
    here would make an attended run slower than the unattended one."""
    code, reads, sleeps, _ = _run_wait_loop(
        tmp_path, bodies=[BUSY_BODY], deadlines=[600], dispatched=True
    )
    assert (code, reads, sleeps) == (0, 1, 0)


def test_an_unknown_reading_is_never_confirmed_because_it_is_not_an_idle_one(tmp_path):
    """`IDLE` and `UNKNOWN` share exit code 0 and are opposite facts.

    Both PROCEED — the cost-gate polarity is untouched — but only `IDLE` is a
    reading about the fleet, so only `IDLE` is worth a second look. A second
    reading of a broken instrument is still broken: confirming it would spend
    band to learn nothing, on exactly the runs where the gate is already blind.
    This is the shape that makes it a real distinction rather than a tidy one:
    a body naming NO WORKER is a failed broadcast (gotcha #53), not a quiet
    fleet, and it is indistinguishable from one by exit code alone.
    """
    no_worker = json.dumps({"_cache": {"age": 0.0}})
    code, reads, sleeps, _ = _run_wait_loop(
        tmp_path, bodies=[no_worker, IDLE_BODY], deadlines=[600, 540]
    )
    assert (code, reads, sleeps) == (0, 1, 0)


def test_a_failed_read_still_proceeds_and_is_never_served_a_stale_payload(tmp_path):
    """The cost-gate polarity, unchanged by the loop: an unreadable fact
    PROCEEDS. And because the payload is removed before each read, a read that
    fails cannot be judged on the previous iteration's fleet."""
    code, reads, sleeps, _ = _run_wait_loop(
        tmp_path, bodies=[BUSY_BODY], deadlines=[600], curl_fails=True
    )
    assert (code, reads, sleeps) == (0, 1, 0)
    # And the stale-payload half, directly: a busy read followed by a failed one
    # must not keep holding on the body that is no longer there.
    code, reads, sleeps, _ = _run_wait_loop(
        tmp_path / "second", bodies=[BUSY_BODY], deadlines=[600, 540]
    )
    assert code == 0  # iteration 2's curl has no body left, so it fails -> UNKNOWN
    assert (reads, sleeps) == (2, 1)


def test_the_workflow_removes_the_payload_before_every_read():
    """Source-level companion to the behaviour above: `--fail` writes no body,
    so without this the gate judges the previous iteration's fleet."""
    body = _workflow_code()
    loop = _extract_wait_loop()
    assert 'rm -f "$INSPECT_JSON"' in loop
    assert loop.index('rm -f "$INSPECT_JSON"') < loop.index("api/admin/celery/inspect")
    # and the loop really does wrap the gate the push is judged on
    assert "heavy_sync_decision.py inflight" in loop
    assert body.index("INFLIGHT=$?") < body.index("git push heroku-heavy")


def _extract_final_band_check() -> str:
    lines = _workflow_code().splitlines()
    start = next(
        i for i, ln in enumerate(lines) if ln.strip() == 'if [ -z "$DISPATCH_FLAG" ]; then'
    )
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == " " * 10 + "fi")
    return "\n".join(ln[10:] for ln in lines[start:end + 1])


def _run_final_band_check(tmp_path, *, deadline, dispatched=False):
    """Run the pre-push band re-check. Returns (exit code, reached the push?)."""
    stub = tmp_path / "stub"
    stub.mkdir(parents=True)
    (stub / "python3").write_text(f"#!/bin/bash\nprintf %s {deadline!r}\n")
    (stub / "python3").chmod(0o755)
    script = tmp_path / "check.sh"
    script.write_text(
        "set -uo pipefail\n"
        f'DISPATCH_FLAG="{"--dispatched" if dispatched else ""}"\n'
        + _extract_final_band_check()
        + '\necho "REACHED THE PUSH"\n'
    )
    proc = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, cwd=str(REPO),
        env={**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"}, timeout=60,
    )
    return proc.returncode, "REACHED THE PUSH" in proc.stdout


def test_the_band_is_asked_again_after_the_fleet_read_and_before_the_push(tmp_path):
    """`decide` read the band BEFORE a network read that measured 18.4s and is
    retried twice — and the wait widens that gap on purpose. A verdict that was
    true two minutes ago is not permission to push now."""
    code, pushed = _run_final_band_check(tmp_path / "closed", deadline="0")
    assert (code, pushed) == (0, False)
    code, pushed = _run_final_band_check(tmp_path / "open", deadline="240")
    assert (code, pushed) == (0, True)


def test_the_final_band_check_holds_on_an_answer_it_cannot_read(tmp_path):
    """Its polarity is the OPPOSITE of the cost gates above it: this one keeps
    the accuracy rebuild whole, and "cannot prove" is never permission."""
    for bad in ("", "later", "-5"):
        code, pushed = _run_final_band_check(
            tmp_path / (bad or "empty"), deadline=bad
        )
        assert (code, pushed) == (0, False), bad


def test_an_attended_run_is_exempt_from_the_final_band_check(tmp_path):
    """It is exempt from the band itself — `--dispatched` overrules the clock."""
    code, pushed = _run_final_band_check(tmp_path, deadline="0", dispatched=True)
    assert (code, pushed) == (0, True)


def test_the_final_band_check_stands_between_the_gate_and_the_push():
    body = _workflow_code()
    check = _extract_final_band_check()
    assert "band-seconds-left" in check
    assert body.index(check.splitlines()[0].strip()) > body.index("INFLIGHT=$?")
    assert body.index(check.splitlines()[0].strip()) < body.index("git push heroku-heavy")


def test_the_sleep_in_the_workflow_is_the_poll_the_script_documents():
    """Two copies of one number is how a comment becomes a story about a value
    nothing enforces."""
    loop = _extract_wait_loop()
    assert f"sleep {sync.INFLIGHT_POLL_SECONDS}" in loop
    # THE EDGE IS NOT ASSERTED HERE, AND THE LINE THAT USED TO DO IT WAS THE
    # DEFECT WRITTEN DOWN (#6283). This test also read
    # `assert f'-le {sync.INFLIGHT_POLL_SECONDS} ]' in loop`, which pinned the
    # band's edge to the SLEEP — so the one number the script says must stay
    # derived was held equal to the one it says is a plain sample rate, and a
    # turn of the loop costs both of them. The edge has its own guard:
    # `test_the_bands_edge_is_a_whole_turn_of_the_wait_loop`.
    # It is a sample rate, not a threshold — no verdict turns on its value — but
    # it still has to be a rate that can catch the thing it is watching. Both
    # bounds come from readings this file already holds: a sampler slower than
    # the SLOWEST push -> release lag is slower than the event it is trying to be
    # on time for, and a band that offers only one read is the single read this
    # loop exists to replace.
    band_s = (sync.window_bounds()[1] - sync.window_bounds()[0] + 1) * 60
    assert 0 < sync.INFLIGHT_POLL_SECONDS <= max(OBSERVED_RELEASE_LAGS_MIN) * 60
    assert sync.INFLIGHT_POLL_SECONDS * 2 <= band_s


# ---------------------------------------------------------------------------
# #5722 — the post-push readback. The first ever sync SUCCEEDED and reported
# failure, because it asked the git ref instead of the release record.
# ---------------------------------------------------------------------------

CONFIRMED, MISMATCH, UNREADABLE = 0, 1, 2


def test_the_readback_confirms_when_the_release_is_built_from_the_pushed_sha():
    mod = _module()
    d = mod.readback_verdict(expected=A, observed=A)
    assert d.code == CONFIRMED
    assert d.verdict == "CONFIRMED"


def test_a_release_on_a_different_commit_is_a_mismatch():
    mod = _module()
    d = mod.readback_verdict(expected=A, observed=B)
    assert d.code == MISMATCH
    assert B[:9] in d.reason and A[:9] in d.reason


def test_an_unreadable_release_is_not_a_mismatch():
    """Gotcha #53, and the distinction the old one-line check could not draw.

    "the API did not answer" and "heavy is on a different commit" call for
    opposite responses — retry versus stop — and the replaced line reported both
    as the same false claim about heavy's sha.
    """
    mod = _module()
    for observed in (None, "", "not-a-sha", "10c0ee5c"):  # incl. an ABBREVIATION
        d = mod.readback_verdict(expected=A, observed=observed)
        assert d.code == UNREADABLE, f"{observed!r} should be UNREADABLE, got {d.verdict}"


def test_the_poller_survives_the_race_that_broke_the_first_real_sync():
    """THE REGRESSION, reproduced.

    Run 34714692872 pushed `10c0ee5cd`, Heroku released it, and the immediate
    readback returned the PREVIOUS sha because a Heroku git endpoint advertises
    its ref asynchronously after the release. A single read fails; re-asking
    finds the truth. The stale answer is returned twice so this cannot pass by
    accident on a one-shot retry.
    """
    mod = _module()
    answers = iter([B, B, A])
    slept: list[float] = []
    d = mod.poll_readback(
        expected=A, fetch=lambda: next(answers), attempts=5, delay_s=6.0,
        sleep=slept.append,
    )
    assert d.code == CONFIRMED
    assert slept == [6.0, 6.0], "it must wait between attempts, not spin"


def test_a_genuine_mismatch_still_fails_after_the_budget():
    """The poller must not launder a real mismatch into patience.

    If it retried forever, or returned CONFIRMED on exhaustion, the
    never-backwards guarantee would be reported as holding when it does not.
    """
    mod = _module()
    d = mod.poll_readback(
        expected=A, fetch=lambda: B, attempts=3, delay_s=0.0, sleep=lambda _: None
    )
    assert d.code == MISMATCH


def test_a_fetch_that_raises_is_unreadable_not_a_mismatch():
    """A network error is not evidence about heavy's commit."""
    mod = _module()

    def boom():
        raise OSError("connection reset")

    d = mod.poll_readback(
        expected=A, fetch=boom, attempts=2, delay_s=0.0, sleep=lambda _: None
    )
    assert d.code == UNREADABLE


def test_the_workflow_reads_the_release_record_and_not_the_git_ref_after_pushing():
    """The git ref lost the race once and is not the authority for "is it live".

    Scoped to what happens AFTER the push: `ls-remote` is still the right way to
    read the two live refs BEFORE deciding, so a blanket ban would be wrong.
    """
    body = WORKFLOW.read_text()
    after_push = body.split('git push heroku-heavy "$MAIN_LIVE:refs/heads/master"')[-1]
    assert "heavy_sync_decision.py verify" in after_push

    # COMMENTS ARE STRIPPED FIRST, and that is not a convenience. The comment
    # explaining this very fix has to name `ls-remote` to say what went wrong, so
    # a bare substring search is true on the text that DENIES the defect — the
    # guard would fail on a correct file and pass on one whose explanation had
    # been deleted. Assert about executable lines only.
    code = "\n".join(
        ln for ln in after_push.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "ls-remote" not in code, (
        "the post-push readback must not consult the git ref — it advances "
        "asynchronously after the release and reported a false mismatch on the "
        f"first ever sync.\n{code}"
    )


def test_an_unreadable_readback_does_not_fail_the_job():
    """An unreadable answer is not a negative one; the next run re-judges.

    Failing here would put us back where #5722 started — a red run on a sync
    that worked — just through a different door.
    """
    body = WORKFLOW.read_text()
    after_push = body.split('git push heroku-heavy "$MAIN_LIVE:refs/heads/master"')[-1]
    assert re.search(r"^\s*2\)\s*echo \"::warning::", after_push, re.M), after_push
    assert re.search(r"::warning::.*\n(.*\n)*?\s*exit 0", after_push)


# ---------------------------------------------------------------------------
# #5722 — HEROKU RELEASE PROTOCOL, the unit contract.
#
# `readback_verdict` and `poll_readback` above are tested with no network,
# because they take their fact as an argument. `heroku_release_commit` is where
# that fact is MANUFACTURED, and until now it had only a live two-arm proof
# against the real API — which certifies today's behaviour and pins nothing.
#
# It is two hops (latest release -> that release's slug -> the slug's commit)
# and every hop has a way of being quietly wrong that ends in the SAME failure
# #5722 just closed: a job that reports a false claim about heavy's commit.
# The Range header is the sharpest of them — Heroku's release list defaults to
# ASCENDING from v1, so losing it does not error, it returns the app's FIRST
# release forever and turns every sync red on a heavy that is perfectly fine.
#
# The fake below answers only the exact paths it is routed and raises on any
# other, so a mutant that skips a hop or builds a malformed URL fails loudly
# instead of falling through to a `None` that reads as a tidy UNREADABLE.
# ---------------------------------------------------------------------------

SLUG_ID = "0d1b2c3d-4e5f-6789-abcd-ef0123456789"


class _FakeHeroku:
    """A Platform API that serves the routes it is given and nothing else."""

    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.calls: list[tuple[str, dict[str, str]]] = []

    def urlopen(self, req, timeout=None):
        headers = {k.lower(): v for k, v in req.headers.items()}
        self.calls.append((req.full_url, headers))
        for path, payload in self.routes.items():
            if req.full_url == f"https://api.heroku.com/{path}":
                return io.BytesIO(json.dumps(payload).encode())
        raise AssertionError(
            f"the script asked for a path this contract does not serve: "
            f"{req.full_url!r} (routed: {sorted(self.routes)})"
        )

    def install(self, monkeypatch):
        monkeypatch.setattr(urllib.request, "urlopen", self.urlopen)
        return self

    @property
    def paths(self) -> list[str]:
        return [url.removeprefix("https://api.heroku.com/") for url, _ in self.calls]


def _deployed(app: str = "bainluck-heavy", commit: str = A) -> _FakeHeroku:
    """The ordinary case: the current release is a deploy, built from ``commit``."""
    return _FakeHeroku(
        {
            f"apps/{app}/releases": [{"version": 11, "slug": {"id": SLUG_ID}}],
            f"apps/{app}/slugs/{SLUG_ID}": {"id": SLUG_ID, "commit": commit},
        }
    )


def test_the_commit_comes_from_the_slug_of_the_current_release(monkeypatch):
    """The two-hop contract: the release names a slug, the SLUG names a commit.

    A release record carries no commit of its own. Reading one off the release
    (or off `slug` before dereferencing it) returns `None`, which the readback
    correctly reports as UNREADABLE — so the job goes yellow forever on a heavy
    that is fine, and #5470's whole point (drift must not be silent) is lost to
    a warning nobody reads.
    """
    api = _deployed().install(monkeypatch)

    assert sync.heroku_release_commit("bainluck-heavy", "tok") == A
    assert api.paths == [
        "apps/bainluck-heavy/releases",
        f"apps/bainluck-heavy/slugs/{SLUG_ID}",
    ], "both hops, in order, and no third request"


def test_the_release_read_asks_for_the_LATEST_release_not_the_first(monkeypatch):
    """THE ONE THAT CANNOT BE LEFT TO A LIVE PROOF.

    `GET /apps/{app}/releases` is a paginated Heroku range resource and its
    default order is ASCENDING, so a request with no Range header answers with
    the app's FIRST release — v1, built from whatever commit created the app.
    Nothing errors. The readback then compares the sha we just pushed against a
    months-old one, reports MISMATCH, and fails a sync that worked: exactly the
    bug #5722 closed, rebuilt one layer down.

    The live two-arm proof cannot catch it either, because a real
    `bainluck-heavy` with the header dropped still answers 200 with a real sha.
    """
    api = _deployed().install(monkeypatch)
    sync.heroku_release_commit("bainluck-heavy", "tok")

    _, headers = api.calls[0]
    assert "range" in headers, "the release list must be ranged, or it reads v1"
    assert "order=desc" in headers["range"], headers["range"]
    assert headers["range"].startswith("version"), headers["range"]
    assert "max=1" in headers["range"], headers["range"]

    # The slug fetch is a plain GET of one resource: a Range there would be
    # meaningless, and its presence would mean the two calls had been merged.
    assert "range" not in api.calls[1][1]


def test_a_config_only_release_is_unreadable_and_never_a_mismatch(monkeypatch):
    """A release with no slug is a config change, not a deploy.

    `heroku config:set` on heavy mints a release whose `slug` is null. It says
    nothing about which commit is running, and the honest answer is "cannot
    read" — which the poller retries and, if it persists, WARNS on (exit 0).
    Answering anything else would fail a green sync on a config edit, and
    inventing a commit would be worse: a false CONFIRMED is drift going silent,
    which is the failure #5470 exists to end.

    Both null-slug spellings Heroku emits are covered — the key present and
    null, and the key absent.
    """
    for release in ({"version": 12, "slug": None}, {"version": 12}):
        api = _FakeHeroku({"apps/bainluck-heavy/releases": [release]}).install(monkeypatch)

        assert sync.heroku_release_commit("bainluck-heavy", "tok") is None
        assert api.paths == ["apps/bainluck-heavy/releases"], (
            "with no slug there is nothing to dereference; a second hop here "
            "would be a request against a null id"
        )

        # …and the meaning downstream, which is the whole reason this case matters.
        d = sync.readback_verdict(expected=A, observed=None)
        assert d.code == UNREADABLE


def test_an_answer_that_names_no_commit_is_unreadable_not_an_answer(monkeypatch):
    """Every shape the API can return without naming a commit ends at None.

    `_is_sha` guards the value, but only if the value ARRIVES. These are the
    shapes that reach the readback as a fact rather than as an absence.
    """
    app = "bainluck-heavy"
    shapes = {
        "no releases at all (a brand new app)": {f"apps/{app}/releases": []},
        "a null release row": {f"apps/{app}/releases": [None]},
        "a slug with no id": {f"apps/{app}/releases": [{"slug": {"name": "web.1"}}]},
        "a slug that names no commit": {
            f"apps/{app}/releases": [{"slug": {"id": SLUG_ID}}],
            f"apps/{app}/slugs/{SLUG_ID}": {"id": SLUG_ID},
        },
        "a slug body that is null": {
            f"apps/{app}/releases": [{"slug": {"id": SLUG_ID}}],
            f"apps/{app}/slugs/{SLUG_ID}": None,
        },
    }
    for label, routes in shapes.items():
        _FakeHeroku(routes).install(monkeypatch)
        assert sync.heroku_release_commit(app, "tok") is None, label


def test_the_request_carries_the_versioned_accept_and_the_bearer(monkeypatch):
    """Both headers are load-bearing, and neither failure is visible locally.

    Heroku serves a DIFFERENT, older schema without the versioned Accept, and
    `slug` is not guaranteed on it — so dropping it degrades to the null-slug
    path above and the sync warns forever. Dropping the bearer answers 401,
    which `poll_readback` catches as UNREADABLE: same silent yellow.
    """
    api = _deployed().install(monkeypatch)
    sync.heroku_release_commit("bainluck-heavy", "s3cr3t")

    for _, headers in api.calls:
        assert headers["accept"] == "application/vnd.heroku+json; version=3"
        assert headers["authorization"] == "Bearer s3cr3t"


def test_the_runtime_url_agrees_with_the_static_third_party_proof(monkeypatch):
    """The runtime half of the exemption `test_agent_origin_outbound_tag` grants.

    That guard lets this file skip the origin carrier ONLY because the source
    text pins a host `is_our_host` says is not ours, and it can prove that only
    while the literal prefix CLOSES the authority — `f"...heroku.com{path}"`
    would leave the host to whatever `path` holds. The static proof reads the
    source; this reads what is actually requested. If the two ever disagree, the
    static claim has stopped being true and the exemption has to go with it.
    """
    api = _deployed().install(monkeypatch)
    sync.heroku_release_commit("bainluck-heavy", "tok")

    assert api.calls, "nothing was requested, so nothing was proven"
    for url, _ in api.calls:
        assert urllib.parse.urlsplit(url).hostname == "api.heroku.com", url
        assert url.startswith("https://api.heroku.com/"), url
        assert "//" not in url.removeprefix("https://"), f"malformed path: {url}"


def test_the_app_name_is_the_one_asked_for(monkeypatch):
    """`bainluck` and `bainluck-heavy` are one character apart in every command.

    Reading the MAIN app's release here would CONFIRM every push — main deploys
    itself from the same master — and heavy could sit a month behind, green.
    """
    api = _deployed(app="bainluck-heavy").install(monkeypatch)
    assert sync.heroku_release_commit("bainluck-heavy", "tok") == A
    assert all(p.startswith("apps/bainluck-heavy/") for p in api.paths), api.paths

    # The fake refuses any path it does not serve, so asking for the wrong app
    # is an error rather than a quiet wrong answer.
    _deployed(app="bainluck-heavy").install(monkeypatch)
    with pytest.raises(AssertionError, match="does not serve"):
        sync.heroku_release_commit("bainluck", "tok")


# ═══════════════════════════════════════════════════════════════════════════════
# #5470, the tail — the trigger is the event that creates the drift, and the
# cycle floor is what keeps that affordable.
#
# The cron was never the mechanism failing; it was the mechanism being uncorrelated
# with the problem AND undelivered (4 runs against 17 nominal slots, measured
# 2026-09-13). So CI completing on master is the primary trigger, the schedule
# demotes to a backstop, and a floor holds the cycle rate at the budget this file
# already priced — because the trigger rate is now the deploy rate, not a clock.
#
# The two properties worth the most here are POLARITY and ORDER: a cost gate that
# cannot read its fact must PROCEED (the opposite of every guard above it), and
# it must sit after them, so no arrangement of cheap facts can talk the script out
# of the never-backwards guard.
# ═══════════════════════════════════════════════════════════════════════════════

CI_WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


def _in_band_push(**over):
    """The ordinary PUSH call, with one field overridden per test."""
    kwargs = dict(
        main_live=A, heavy_live=B, heavy_is_ancestor=True, now=_at(40),
    )
    kwargs.update(over)
    return sync.decide(**kwargs)


# ── the floor, derived like the band ───────────────────────────────────────────


def test_the_cycle_floor_falls_out_of_the_accepted_budget():
    """180 min must be arithmetic on a budget, not a number somebody liked.

    Same shape as the band: pin the value AND the derivation, so neither the
    constant nor the formula can drift alone.
    """
    assert sync.min_cycle_interval_min() == 180
    assert sync.min_cycle_interval_min() == round(24 * 60 / sync.ACCEPTED_CYCLES_PER_DAY)


def test_moving_the_accepted_budget_moves_the_floor(monkeypatch):
    """The property, not the number. A re-priced budget must move the gate."""
    monkeypatch.setattr(sync, "ACCEPTED_CYCLES_PER_DAY", 24)
    assert sync.min_cycle_interval_min() == 60
    monkeypatch.setattr(sync, "ACCEPTED_CYCLES_PER_DAY", 4)
    assert sync.min_cycle_interval_min() == 360


def test_the_floor_is_at_least_as_permissive_as_the_cron_it_joins():
    """The floor must never forbid what the triggers are licensed to attempt.

    Written when three in-band cron attempts an hour were priced at ~7.5
    cycles/day; the cron is back to its authorised single hourly fire, so the
    cron alone can no longer reach the budget and the invariant holds with room
    to spare. It is kept, and kept at 8, because the binding consumer is now the
    `workflow_run` trigger rather than the clock: a floor tighter than the budget
    would gate out the very syncs the event trigger exists to deliver, and the
    schedule would look delivered while being held.
    """
    assert sync.ACCEPTED_CYCLES_PER_DAY >= 8, (
        "tightening the budget below the rate the triggers are priced at makes "
        "this file argue with itself"
    )


# ── the gate itself ────────────────────────────────────────────────────────────


def test_a_heavy_released_minutes_ago_holds_even_inside_the_band():
    """The trigger rate is not the cycle rate, and this is the only thing saying so.

    ~31 CI-success runs a day through a 25-minute band is ~13 heavy cycles/day —
    a rate this file rejects at the top, because each one cycles `worker-heavy`.
    """
    d = _in_band_push(heavy_release_age_min=10)
    assert d.code == HOLD
    assert "cycle floor" in d.reason
    assert "180" in d.reason, "the reason must name the floor it enforced"


def test_an_age_past_the_floor_pushes_and_the_boundary_is_inclusive():
    """`< floor` holds; exactly the floor is permission, not a coin toss."""
    assert _in_band_push(heavy_release_age_min=181).code == PUSH
    assert _in_band_push(heavy_release_age_min=180).code == PUSH
    assert _in_band_push(heavy_release_age_min=179).code == HOLD


def test_an_unreadable_age_PROCEEDS_because_a_cost_gate_is_not_a_safety_gate():
    """THE POLARITY TEST, and the one a later reader is most likely to invert.

    Every other unknown in this script refuses, so "unknown -> hold" looks like
    the house style. It is exactly wrong here. An unreadable release age does not
    mean heavy was disturbed recently; it means we could not ask. Holding on it
    would let one flaky Heroku read stop the sync this whole ship exists to make
    happen, to save ~2 minutes of recomputation.
    """
    assert _in_band_push(heavy_release_age_min=None).code == PUSH
    # And the default is the unreadable case, so a caller that never learned
    # about the floor gets the sync rather than silence.
    assert sync.decide(
        main_live=A, heavy_live=B, heavy_is_ancestor=True, now=_at(40)
    ).code == PUSH


def test_an_attended_run_bypasses_the_floor_as_well_as_the_clock():
    """Both COST gates yield to a person; neither safety guard does."""
    assert _in_band_push(heavy_release_age_min=1, dispatched=True).code == PUSH
    assert sync.decide(
        main_live=A, heavy_live=B, heavy_is_ancestor=True,
        heavy_release_age_min=1, dispatched=True, now=_at(5),
    ).code == PUSH


def test_the_floor_can_never_talk_the_script_out_of_the_never_backwards_guard():
    """Order is the safety order. A diverged heavy REFUSES at any age.

    The dangerous refactor is "check the cheap local number first and return
    early" — it would turn a rewind into a benign-looking HOLD, and the next run
    would report the same HOLD, forever, with nobody alerted.
    """
    for age in (0, 1, 179, 180, 10_000):
        d = sync.decide(
            main_live=A, heavy_live=B, heavy_is_ancestor=False,
            heavy_release_age_min=age, now=_at(40),
        )
        assert d.code == REFUSE, age
    # …and an unreadable sha still refuses before the floor is even considered.
    assert sync.decide(
        main_live="abc", heavy_live=B, heavy_is_ancestor=True,
        heavy_release_age_min=0, now=_at(40),
    ).code == REFUSE


def test_the_window_and_the_floor_stay_two_gates_with_two_reasons():
    """Outside the band the reason is the band, even when the floor would also fire.

    Folding them into one HOLD would cost the only diagnosis a person gets from a
    green run: "held because heavy is fresh" and "held because GitHub fired at
    :09" call for completely different responses.
    """
    d = sync.decide(
        main_live=A, heavy_live=B, heavy_is_ancestor=True,
        heavy_release_age_min=1, now=_at(5),
    )
    assert d.code == HOLD
    assert "window" in d.reason and "cycle floor" not in d.reason

    # And in sync beats both, as it already beat the window.
    d = sync.decide(
        main_live=A, heavy_live=A, heavy_is_ancestor=True,
        heavy_release_age_min=1, now=_at(40),
    )
    assert d.code == HOLD and "already on" in d.reason


# ── the CLI carries the age without ever choking on it ─────────────────────────


def test_an_unreadable_age_reaches_decide_as_unknown_and_never_as_a_usage_exit():
    """`type=int` here would be a live outage waiting for one bad API read.

    The workflow computes this from a Heroku call that is allowed to fail, so it
    passes the empty string. argparse would exit 2 on it — which the workflow's
    `case` treats as "a story about the harness" and refuses on, failing a job
    whose only problem was an unreadable cost input.
    """
    for value in ("", "   ", "banana", "12.5", "-"):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "decide", "--main-live", A, "--heavy-live", B,
             "--heavy-is-ancestor", "true", "--heavy-release-age-min", value],
            capture_output=True, text=True,
        )
        assert proc.returncode in (PUSH, HOLD), (value, proc.returncode, proc.stderr)
        assert proc.returncode != USAGE, value
    assert sync._age_arg("") is None
    assert sync._age_arg("banana") is None
    assert sync._age_arg(None) is None
    assert sync._age_arg(" 42 ") == 42


def test_the_parsed_age_reaches_decide_and_is_not_dropped_on_the_way(monkeypatch):
    """The wiring: a number on the command line arrives as that number.

    Asserted in-process on purpose. The obvious version — run the CLI with
    `--heavy-release-age-min 1` and expect the floor's HOLD — passes or fails on
    the wall-clock minute, because the floor sits AFTER the window and the script
    deliberately has no `--now` (#4997). It went red at :19 the first time it
    ran, which is the same trap in a new costume: a test whose verdict depends on
    when CI happened to reach it (gotcha #44).
    """
    seen = {}

    def _spy(**kwargs):
        seen.update(kwargs)
        return sync.Decision(HOLD, "HOLD", "spied")

    monkeypatch.setattr(sync, "decide", _spy)
    assert sync.main(
        ["decide", "--main-live", A, "--heavy-live", B,
         "--heavy-is-ancestor", "true", "--heavy-release-age-min", "1"]
    ) == HOLD
    assert seen["heavy_release_age_min"] == 1
    assert seen["main_live"] == A and seen["heavy_is_ancestor"] is True

    seen.clear()
    sync.main(["decide", "--main-live", A, "--heavy-live", B, "--heavy-is-ancestor", "true"])
    assert seen["heavy_release_age_min"] is None, (
        "an omitted flag must arrive as UNKNOWN, which proceeds — never as 0, "
        "which would hold every sync forever"
    )


# ── reading the age: a different question from reading the commit ──────────────


def _released_at(stamp: str, app: str = "bainluck-heavy", slug: bool = True):
    release = {"version": 12, "created_at": stamp}
    if slug:
        release["slug"] = {"id": SLUG_ID}
    return _FakeHeroku(
        {
            f"apps/{app}/releases": [release],
            f"apps/{app}/slugs/{SLUG_ID}": {"id": SLUG_ID, "commit": A},
        }
    )


def test_the_age_comes_from_created_at(monkeypatch):
    _released_at("2026-09-12T14:00:00Z").install(monkeypatch)
    age = sync.heroku_release_age_min("bainluck-heavy", "tok", now=_at(40))
    assert age == 40


def test_a_CONFIG_ONLY_release_has_no_commit_but_it_does_have_an_age(monkeypatch):
    """The two readers answer two questions, and must not be merged.

    `heroku config:set` mints a slugless release. It cannot say which commit is
    running — so the readback rightly calls it unreadable — but it DID cycle the
    dyno, which is the only thing the floor cares about. Reusing one reader for
    both would make a config edit invisible to the floor, and the sync would
    cycle a worker that restarted a minute ago.
    """
    api = _released_at("2026-09-12T14:30:00Z", slug=False).install(monkeypatch)
    assert sync.heroku_release_age_min("bainluck-heavy", "tok", now=_at(40)) == 10
    assert api.paths == ["apps/bainluck-heavy/releases"], "no slug hop is needed for an age"

    _released_at("2026-09-12T14:30:00Z", slug=False).install(monkeypatch)
    assert sync.heroku_release_commit("bainluck-heavy", "tok") is None


def test_a_stamp_the_script_cannot_read_is_unreadable_and_not_a_zero(monkeypatch):
    """A zero would read as "released just now" and hold the sync out silently."""
    for stamp in ("", "not-a-date", "2026-13-45T99:00:00Z"):
        _released_at(stamp).install(monkeypatch)
        assert sync.heroku_release_age_min("bainluck-heavy", "tok", now=_at(40)) is None

    _FakeHeroku({"apps/bainluck-heavy/releases": []}).install(monkeypatch)
    assert sync.heroku_release_age_min("bainluck-heavy", "tok", now=_at(40)) is None


def test_a_future_stamp_clamps_to_zero_rather_than_sailing_under_the_floor(monkeypatch):
    """Clock skew between Heroku and the runner must fail toward the cautious side.

    A negative age is `< floor` either way, so this is belt and braces — but a
    later refactor that compares `abs(age)` or formats it into a message should
    not be able to print "released -7 min ago".
    """
    _released_at("2026-09-12T14:50:00Z").install(monkeypatch)
    assert sync.heroku_release_age_min("bainluck-heavy", "tok", now=_at(40)) == 0


def test_the_age_read_asks_for_the_LATEST_release_too(monkeypatch):
    """The same paginated trap as the readback: unranged, Heroku answers v1.

    An age computed from v1 is months, which is always past the floor — the gate
    would be permanently open and would read as working.
    """
    api = _released_at("2026-09-12T14:00:00Z").install(monkeypatch)
    sync.heroku_release_age_min("bainluck-heavy", "tok", now=_at(40))
    _, headers = api.calls[0]
    assert "order=desc" in headers.get("range", ""), headers
    assert "max=1" in headers.get("range", ""), headers


def test_the_age_subcommand_prints_the_number_alone_and_always_exits_zero():
    """Its caller is `$(...)`, so stdout is a contract and a non-zero is a hazard.

    With no credential there is nothing to read; the honest answer is an empty
    string, and the job carries on. Failing here would let a cost input take down
    a sync — and this is the exact shape of the first sync's own bug (#5722),
    where a read that could not answer was reported as a negative.
    """
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "age", "--app", "bainluck-heavy"],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "HEROKU_API_KEY": ""},
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "", proc.stdout
    assert "HEROKU_API_KEY" in proc.stderr, "silence would be the unreadable-as-zero bug"


# ── the trigger, in the workflow ───────────────────────────────────────────────


def test_the_primary_trigger_is_CI_completing_on_master():
    """The whole point of the change: an event correlated with the drift.

    A schedule fires whether or not anything deployed, and GitHub delivered 4 of
    17 of them. CI completing on master fires exactly when new drift exists.
    """
    code = _workflow_code()
    assert "workflow_run:" in code
    assert re.search(r"workflows:\s*\[\s*\"CI\"\s*\]", code), code
    assert re.search(r"types:\s*\[\s*completed\s*\]", code), code
    assert re.search(r"branches:\s*\[\s*master\s*\]", code), (
        "without a branch filter every PR's CI run triggers a heavy sync"
    )


def test_the_triggering_workflow_is_named_the_way_ci_yml_actually_names_itself():
    """A `workflow_run` filter is a STRING MATCH against another file's `name:`.

    Rename ci.yml's `name:` and this trigger stops firing — silently, green,
    forever, which is #5470's failure mode exactly. Nothing else in the repo
    couples these two files, so this assertion is the coupling.
    """
    ci_name = re.search(r"(?m)^name:\s*(.+?)\s*$", CI_WORKFLOW.read_text())
    assert ci_name, "ci.yml has no top-level name:"
    named = re.search(r"workflows:\s*\[\s*\"([^\"]+)\"\s*\]", _workflow_code())
    assert named and named.group(1) == ci_name.group(1), (
        f"heavy-sync listens for {named and named.group(1)!r}, "
        f"ci.yml calls itself {ci_name.group(1)!r}"
    )


def test_a_ci_run_that_did_not_succeed_never_syncs():
    """A red CI deployed nothing, so there is no new drift — and the guard must
    not accidentally gate the schedule or the attended dispatch, whose events
    carry no `workflow_run` object at all."""
    code = _workflow_code()
    assert "github.event.workflow_run.conclusion == 'success'" in code
    assert "github.event_name != 'workflow_run'" in code, (
        "without this arm the `if` is false for every scheduled run and the "
        "backstop dies silently"
    )


def test_the_schedule_survives_as_a_backstop():
    """A HELD run needs something to re-offer it when no further deploy arrives.

    Deleting the cron as "superseded" would leave a sync that fell outside the
    band with no second chance until the next merge.
    """
    minutes = [int(m) for m in _cron().group(1).split(",")]
    assert minutes, "the backstop cron was removed"
    opens, closes = sync.window_bounds()
    assert all(opens <= m <= closes for m in minutes), minutes


def test_the_workflow_hands_the_decision_the_age_it_read():
    """A gate nothing calls is a comment. Prove the flag is on the real call."""
    code = _workflow_code()
    assert "--heavy-release-age-min" in code
    assert "heavy_sync_decision.py age --app bainluck-heavy" in code
    decide_call = code[code.index("heavy_sync_decision.py decide"):]
    assert "--heavy-release-age-min" in decide_call[:400], (
        "the age is read but never passed to the decision"
    )


# ---------------------------------------------------------------------------
# #5470 — THE WAIT TO THE BAND. Heavy's own release record, v15..v20: 3h47 /
# 3h06 / 4h01 / 4h06 / 3h47, mean 3h45 against a 3h00 cycle floor. The
# 45-minute residual is the wait for a trigger to arrive while the band is open
# after the floor has cleared — one arrives every ~22 min and 47% of them are
# in band (34/73 measured), which is 45 min of expected wait. The tail is the
# part that hurt: with no deploys the only trigger is a cron measured 19-359
# min late, in band 2 of 11 times, which is the 7h06m episodes in the
# workflow's header. A run that HOLDs at :10 and a run that sleeps to :38
# differ only in whether the opportunity is taken, so the tests below are about
# one thing: the sleep must buy an opportunity WITHOUT buying a weaker verdict.
# ---------------------------------------------------------------------------


def test_the_two_edges_are_one_band_read_from_both_sides():
    """`seconds_until_window_opens` and `band_seconds_left` must not be two
    independent opinions about where the band is — at every minute of the hour
    exactly one of them is non-zero."""
    opens, closes = sync.window_bounds()
    for minute in range(60):
        now = _at(minute)
        inside = sync.inside_window(now)
        assert inside == (opens <= minute <= closes), minute
        assert (sync.seconds_until_window_opens(now) == 0) is inside, minute
        assert (sync.band_seconds_left(now) > 0) is inside, minute


def test_the_wait_lands_on_the_opening_edge_and_never_past_it():
    """Not "about half an hour" — the exact second the band opens, from any
    starting second, carrying the hour when the wait wraps midnight."""
    opens, _ = sync.window_bounds()
    for minute, second in ((0, 0), (10, 31), (36, 59), (opens - 1, 1), (59, 45)):
        now = _at(minute).replace(second=second)
        landed = now + timedelta(seconds=sync.seconds_until_window_opens(now))
        assert (landed.minute, landed.second) == (opens, 0), (minute, second)
        assert sync.inside_window(landed), (minute, second)
    # A real clock carries microseconds, and truncating them lands the sleeper
    # one second SHORT of the edge — outside the band it just waited to reach.
    ragged = _at(30).replace(second=20, microsecond=842205)
    landed = ragged + timedelta(seconds=sync.seconds_until_window_opens(ragged))
    assert sync.inside_window(landed), landed
    assert landed.minute == opens
    # The wrap is a real hour later, not a negative number of seconds.
    late = datetime(2026, 9, 12, 23, 59, 30, tzinfo=timezone.utc)
    assert late + timedelta(seconds=sync.seconds_until_window_opens(late)) == datetime(
        2026, 9, 13, 0, opens, 0, tzinfo=timezone.utc
    )


def test_a_wait_computed_from_a_real_clock_lands_inside_the_band():
    """The one assertion here that reads the WALL clock, and the reason this
    function rounds up: every `now=` anchor in this file is microsecond-zero,
    so the truncation bug was invisible to all of them and showed up the first
    time the subcommand was run against the real clock (gotcha #44 is satisfied
    — the assertion is self-consistent at every minute of the day)."""
    now = datetime.now(timezone.utc)
    secs = sync.seconds_until_window_opens(now)
    assert sync.inside_window(now + timedelta(seconds=secs)), (now, secs)


def test_no_wait_is_ever_longer_than_the_hour_minus_the_band():
    """The only bound the job timeout has to cover."""
    opens, closes = sync.window_bounds()
    worst = max(sync.seconds_until_window_opens(_at(m)) for m in range(60))
    assert worst == (60 - (closes - opens + 1)) * 60


def _wait(minute, *, main=A, heavy=B, ancestor=True, age=None, dispatched=False):
    return sync.wait_seconds(
        main_live=main,
        heavy_live=heavy,
        heavy_is_ancestor=ancestor,
        dispatched=dispatched,
        heavy_release_age_min=age,
        now=_at(minute),
    )


def test_a_run_with_work_to_do_sleeps_to_the_band_and_one_inside_it_does_not():
    opens, closes = sync.window_bounds()
    assert _wait(10) == (opens - 10) * 60
    for minute in (opens, 42, closes):
        assert _wait(minute) == 0, minute


def test_the_wait_is_authorised_by_the_SAME_judge_and_never_a_second_one():
    """The property that makes the sleep safe to add: it answers no question of
    its own. Whenever it waits, `decide` asked about the moment it will wake —
    with the release age it will have by then — says PUSH."""
    for minute in range(60):
        for age in (None, 0, 100, 179, 180, 10_000):
            secs = _wait(minute, age=age)
            if not secs:
                continue
            now = _at(minute)
            projected = None if age is None else age + (secs + 59) // 60
            verdict = sync.decide(
                main_live=A,
                heavy_live=B,
                heavy_is_ancestor=True,
                heavy_release_age_min=projected,
                now=now + timedelta(seconds=secs),
            )
            assert verdict.code == PUSH, (minute, age, verdict.reason)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"main": A, "heavy": A},          # already in sync — nothing to wait for
        {"ancestor": False},              # a diverged heavy refuses on arrival
        {"ancestor": None},               # and so does an ancestry we cannot prove
        {"main": ""},                     # an unreadable fact is not a pending one
        {"heavy": "b" * 7},
    ],
)
def test_a_run_that_would_not_push_when_the_band_opens_never_sleeps(kwargs):
    """Sleeping 28 minutes to print the verdict we already hold is the pure
    cost of this change with none of its benefit."""
    assert _wait(10, **kwargs) == 0


def test_a_run_inside_the_cycle_floor_never_sleeps():
    """The floor is what bounds the waits at ~8 a day rather than one per
    deploy: a heavy released minutes ago is not made pushable by the clock."""
    assert _wait(10, age=5) == 0
    assert _wait(10, age=0) == 0


def test_the_floor_is_asked_about_the_age_at_the_EDGE_not_the_age_now():
    """A heavy 160 min old at :10 is past the 180-min floor by :38. Asking the
    floor about NOW would refuse a wait the floor itself is about to permit —
    and projecting is safe in the only direction that matters, because the real
    age at the push is at or above the projection."""
    opens, _ = sync.window_bounds()
    floor = sync.min_cycle_interval_min()
    gap = opens - 10
    assert _wait(10, age=floor - gap) == gap * 60
    # One minute younger does not lose the opportunity — it moves the target one
    # minute later, to the floor's own clear, which is still inside this band.
    assert _wait(10, age=floor - gap - 1) == (gap + 1) * 60
    # The projection is the wait, in whole minutes, and nothing else.
    assert sync.decide(
        main_live=A, heavy_live=B, heavy_is_ancestor=True,
        heavy_release_age_min=floor - gap, now=_at(10),
    ).code == HOLD


def test_a_trigger_before_a_floor_that_clears_inside_this_band_sleeps_to_the_clear():
    """The residual this ship is named for, in the shape it had on the day.

    heavy v20 released 11:43:49Z, so its 180-min floor cleared at 14:43:49 —
    INSIDE the 14:38-14:58 band, which is not a coincidence but a property (a
    push may only happen in band and the floor is a whole number of hours). A
    trigger at 14:20 is 156 min old at the opening edge: asking only about :38
    projects 174 min, HOLDs, and throws away a window it was four minutes short
    of. The target is the LATER of the two edges."""
    floor = sync.min_cycle_interval_min()
    clears_at = 44
    assert _wait(20, age=floor - (clears_at - 20)) == (clears_at - 20) * 60
    # and the same run, asked only about the band's opening edge, would not have
    # pushed there at all — which is what makes this a closed gap and not a
    # re-statement of the edge above.
    opens, _ = sync.window_bounds()
    assert sync.decide(
        main_live=A, heavy_live=B, heavy_is_ancestor=True,
        heavy_release_age_min=floor - (clears_at - 20) + (opens - 20),
        now=_at(opens),
    ).code == HOLD


def test_a_run_already_inside_the_band_waits_out_a_floor_that_clears_before_the_close():
    """`seconds_until_window_opens` is 0 inside the band, so the opening edge
    has nothing left to say — and this is the commonest arrival of all, because
    the band is where the triggers that matter land."""
    floor = sync.min_cycle_interval_min()
    assert _wait(40, age=floor - 4) == 4 * 60
    assert _wait(40, age=floor) == 0


def test_a_floor_clearing_after_this_bands_close_never_sleeps():
    """The bound that keeps a 3-hour floor from buying a 3-hour runner: a target
    past the closing edge is not a longer sleep, it is a sleep into a different
    hour's band. Asked from inside the band and from outside it."""
    _, closes = sync.window_bounds()
    floor = sync.min_cycle_interval_min()
    # Inside the band at :50, clearing at :00 — one minute past the edge.
    assert _wait(50, age=floor - (closes + 1 - 50) - 1) == 0
    assert _wait(50, age=floor - (closes + 1 - 50)) == 0
    assert _wait(50, age=floor - (closes - 50)) == (closes - 50) * 60
    # Outside it at :10, with a floor that clears two hours from now.
    assert _wait(10, age=floor - 120) == 0


def test_no_wait_ever_lands_outside_the_band_it_is_waiting_for():
    """The property behind both edges, swept rather than sampled: whenever this
    function sleeps, the instant it wakes on is inside the band — never the next
    hour's, never past the close."""
    floor = sync.min_cycle_interval_min()
    for minute in range(60):
        for age in [None, 0, 5, floor - 30, floor - 5, floor - 1, floor, floor + 90]:
            secs = _wait(minute, age=age)
            if not secs:
                continue
            target = _at(minute) + timedelta(seconds=secs)
            assert sync.inside_window(target), (minute, age, secs)
            # …and inside THIS occurrence of it: the next band to open, never a
            # later one. `inside_window` reads only the minute, so it cannot
            # tell a 24-minute wait from one 24 hours longer; the deadline can.
            assert secs <= sync.band_seconds_left_at_open(_at(minute)), (minute, age)


def test_the_projection_can_never_land_under_the_floor_so_its_rounding_cannot_bite():
    """Why the projected age's round-UP is belt over braces here, stated as the
    property rather than left as a comment.

    Rounding the projection up was load-bearing when the only target was the
    band's opening edge: a ragged real `now` made the wait 17m40s, `int()` wrote
    17, and a run one minute short of the floor declined a wait it should have
    taken. Now that the target is the LATER of the two edges, any wait taken
    while the floor still binds is at least the floor's own remainder, which is
    a whole number of minutes — so ceiling and truncation agree, and no rounding
    of this term can change a verdict. Swept over every minute and every age
    either side of the floor.

    (A mutant that truncates instead therefore SURVIVES, and is equivalent by
    this construction rather than untested — the honest report of it.)"""
    floor = sync.min_cycle_interval_min()
    for minute in range(60):
        for age in [0, 5, floor - 30, floor - 18, floor - 1, floor, floor + 90]:
            secs = _wait(minute, age=age)
            if not secs:
                continue
            assert age + secs // 60 >= floor, (minute, age, secs)
            assert age + (secs + 59) // 60 == age + secs // 60 or age >= floor, (
                minute, age, secs
            )


def test_the_deadline_for_a_wait_is_this_bands_close_read_from_either_side():
    """`band_seconds_left_at_open` is the deadline, and it is the SAME band the
    rest of the file reads — inside the band it is what is left, outside it is
    the wait plus the whole band, and it is derived so a moved band moves it."""
    opens, closes = sync.window_bounds()
    band = (closes - opens + 1) * 60
    assert sync.band_seconds_left_at_open(_at(opens)) == band
    assert sync.band_seconds_left_at_open(_at(50)) == sync.band_seconds_left(_at(50))
    assert sync.band_seconds_left_at_open(_at(10)) == (opens - 10) * 60 + band
    # A ragged real second outside the band still lands on the whole band, never
    # a second of it lost to the rounding that gets the sleeper there.
    ragged = _at(10).replace(second=20, microsecond=842205)
    assert sync.band_seconds_left_at_open(ragged) == sync.seconds_until_window_opens(
        ragged
    ) + band


# ── a sleep must be able to afford what it wakes up to (#5470's residual) ──────
#
# `wait_seconds` measured both of its checks to the WAKE instant, which is the one
# instant at which the run decides nothing: it re-reads every fact first, and only
# then is the verdict taken. Everything below is about the distance between those
# two instants, and about the second one being the one that matters.

#: Wake instant to the verdict line, every sleeping run in this workflow's last
#: 100 (14 of them, 2026-09-19..09-20, read 2026-09-20). Recorded as the LIST so
#: the charge can be checked against the world and not only against itself — the
#: same reason `OBSERVED_RELEASE_LAGS_MIN` above is a list. The wake is COMPUTED
#: (the `Sleeping Ns` echo plus N) and never read off the first log line: the two
#: `ls-remote`s that run before anything is printed cost ~5 s, and reading the
#: line would charge them to nobody.
OBSERVED_POST_WAKE_SECONDS = (
    9.72, 10.24, 10.47, 10.62, 10.73, 10.78, 10.86,
    11.50, 11.57, 11.75, 12.04, 12.19, 13.02, 16.41,
)

#: Run 35518945494, 2026-09-20, replayed on its own numbers. The gate reached
#: PUSH at 15:14:47Z with heavy 136 min old, slept 2640 s for the 180-min cycle
#: floor to clear, and woke at 15:58:47Z — 13 s inside a band closing at :59:00.
SPECIMEN_NOW = datetime(2026, 9, 20, 15, 14, 47, 375424, tzinfo=timezone.utc)
SPECIMEN_AGE_MIN = 136
SPECIMEN_SLEPT_S = 2640
#: …and 13.02 s is what waking up cost it, from the same run's log.
SPECIMEN_POST_WAKE_S = 13.02


def _specimen_wait(**over):
    kwargs = dict(
        main_live=A, heavy_live=B, heavy_is_ancestor=True,
        heavy_release_age_min=SPECIMEN_AGE_MIN, now=SPECIMEN_NOW,
    )
    kwargs.update(over)
    return sync.wait_seconds(**kwargs)


def test_a_sleep_that_cannot_afford_its_own_re_read_is_not_taken():
    """The specimen, and the whole of it: every clause of the old authorisation
    was true, and the run still lost the hour.

    The sleep was validated against 15:58:47 — inside the band, past the floor,
    `decide` says PUSH there — and the verdict was taken 13.02 s later, at
    15:59:00, which is not. Forty-four minutes of runner for the verdict it
    already held at 15:14, and `bainluck-heavy` sat on `704cdc47` while the main
    app served `d0555293`."""
    wake = SPECIMEN_NOW + timedelta(seconds=SPECIMEN_SLEPT_S)
    # Every reason the old rule had for taking it, still true.
    assert sync.seconds_until_floor_clears(SPECIMEN_AGE_MIN) == SPECIMEN_SLEPT_S
    assert sync.inside_window(wake), wake
    assert SPECIMEN_SLEPT_S <= sync.band_seconds_left_at_open(SPECIMEN_NOW)
    assert sync.decide(
        main_live=A, heavy_live=B, heavy_is_ancestor=True,
        heavy_release_age_min=SPECIMEN_AGE_MIN + SPECIMEN_SLEPT_S // 60, now=wake,
    ).code == PUSH
    # And the one reason it should not have been: the verdict is taken later
    # than the instant that was judged, and by then the band has shut.
    verdict_at = wake + timedelta(seconds=SPECIMEN_POST_WAKE_S)
    assert not sync.inside_window(verdict_at), verdict_at
    assert sync.POST_WAKE_READ_SECONDS >= SPECIMEN_POST_WAKE_S

    assert _specimen_wait() == 0


def test_the_post_wake_charge_covers_every_post_wake_read_measured():
    """Rounded up from the MAXIMUM, not the median, and the asymmetry is the
    reason: under-stating authorises a sleep that cannot finish — the hour above
    — while over-stating declines one whose remaining band was going to be spent
    for nothing anyway. A charge below the worst reading is a charge that is
    right on average and wrong exactly when it is consulted."""
    assert sync.POST_WAKE_READ_SECONDS >= max(OBSERVED_POST_WAKE_SECONDS)
    assert float(sync.POST_WAKE_READ_SECONDS) == int(sync.POST_WAKE_READ_SECONDS)
    # It is a charge against the band, so it has to be small against the band.
    opens, closes = sync.window_bounds()
    assert sync.wake_to_push_seconds() < (closes - opens + 1) * 60 / 4


def test_the_verdict_still_reads_PUSH_at_the_moment_it_is_actually_taken():
    """The strengthening of `test_the_wait_is_authorised_by_the_SAME_judge`.

    That test asks `decide` about the WAKE, which is not when `decide` is called —
    it is called `POST_WAKE_READ_SECONDS` later, once the facts have been re-read.
    This asks it about that later instant, which is the one the run occupies.

    Both readings agree today (the deadline is what makes them agree, and
    `test_judging_the_wake_is_sound_only_because_the_deadline_covers_the_re_read`
    is where that is pinned), so this is the sweep and not the proof. Its value is
    the ANCHORS: with the whole-minute `now` every other sweep in this file uses,
    the two instants fall in the same minute at every minute of the hour, which is
    exactly why none of them could see this. The seconds below are ragged on
    purpose — a real trigger arrives at an arbitrary second, and the floor clears a
    whole number of minutes after it, so the wake lands on that same second."""
    floor = sync.min_cycle_interval_min()
    checked = 0
    for minute in range(60):
        for second in (0, 13, 31, 47, 59):
            for age in (None, 0, 100, floor - 48, floor - 20, floor - 1, floor, 10_000):
                now = _at(minute).replace(second=second)
                secs = sync.wait_seconds(
                    main_live=A, heavy_live=B, heavy_is_ancestor=True,
                    heavy_release_age_min=age, now=now,
                )
                if not secs:
                    continue
                checked += 1
                projected = None if age is None else age + (secs + 59) // 60
                verdict = sync.decide(
                    main_live=A, heavy_live=B, heavy_is_ancestor=True,
                    heavy_release_age_min=projected,
                    now=now + timedelta(seconds=secs + sync.POST_WAKE_READ_SECONDS),
                )
                assert verdict.code == PUSH, (minute, second, age, verdict.reason)
    assert checked > 200, checked


def test_the_deadline_for_a_sleep_is_everything_the_run_still_owes_the_band():
    """Swept rather than sampled: whenever this sleeps, the band is still open at
    the verdict AND the push is still inside the band's closing edge."""
    floor = sync.min_cycle_interval_min()
    edge_cases = 0
    for minute in range(60):
        for second in (0, 13, 31, 47, 59):
            for age in (None, 0, 5, floor - 48, floor - 30, floor - 8, floor - 1,
                        floor, floor + 90):
                now = _at(minute).replace(second=second)
                secs = sync.wait_seconds(
                    main_live=A, heavy_live=B, heavy_is_ancestor=True,
                    heavy_release_age_min=age, now=now,
                )
                if not secs:
                    continue
                wake = now + timedelta(seconds=secs)
                assert sync.inside_window(
                    wake + timedelta(seconds=sync.POST_WAKE_READ_SECONDS)
                ), (minute, second, age, secs)
                closing_edge = now + timedelta(seconds=sync.band_seconds_left_at_open(now))
                assert wake + timedelta(seconds=sync.wake_to_push_seconds()) <= closing_edge
                if (closing_edge - wake).total_seconds() < 2 * sync.wake_to_push_seconds():
                    edge_cases += 1
    # …and the sweep actually visits the edge this is about, rather than proving
    # a property about waits that all land 20 minutes clear of it.
    assert edge_cases, "the sweep never reached the band's closing edge"


def test_the_two_charges_are_derived_from_measurements_and_are_what_decline_it(
    monkeypatch,
):
    """Two claims in one, because the second is what makes the first matter.

    Derived: `wake_to_push_seconds` is the re-read plus the in-flight read this
    file already measured, never a third literal free to drift from either. And
    load-bearing: zeroing the charges restores the specimen's old behaviour
    exactly, so these two — and not some other gate reached first — are what
    declines it.

    Every `setattr` here is on an INPUT and never on the total, which is the only
    form that can tell a derivation from a coincidence: `= 43` equals the sum
    today, behaves identically today, and stops tracking the moment either half is
    re-measured. That mutant survives a test that patches the total."""
    assert sync.wake_to_push_seconds() == (
        sync.POST_WAKE_READ_SECONDS + sync.INFLIGHT_READ_SECONDS
    )
    assert _specimen_wait() == 0
    monkeypatch.setattr(sync, "POST_WAKE_READ_SECONDS", 0)
    monkeypatch.setattr(sync, "INFLIGHT_READ_SECONDS", 0)
    assert sync.wake_to_push_seconds() == 0
    assert _specimen_wait() == SPECIMEN_SLEPT_S
    monkeypatch.setattr(sync, "INFLIGHT_READ_SECONDS", 600)
    assert sync.wake_to_push_seconds() == 600
    # A costlier fleet read is a shorter usable band, with no second edit.
    assert sync.wait_seconds(
        main_live=A, heavy_live=B, heavy_is_ancestor=True,
        heavy_release_age_min=sync.min_cycle_interval_min() - 8, now=_at(50),
    ) == 0


def test_the_charge_declines_only_sleeps_that_could_not_have_reached_the_push(
    monkeypatch,
):
    """The blast radius, computed two ways rather than asserted.

    Every sleep the charge removes is one whose own run would have died at a gate
    it was always going to reach: `decide` HOLDing on a band that shut during the
    re-read, or the final band check HOLDing after the fleet read. Nothing that
    could have pushed is declined — which is why declining costs nothing, and is
    the claim a reader of this change is entitled to see swept."""
    floor = sync.min_cycle_interval_min()
    charged = {}
    for scenario, post_wake, inflight in (
        ("now", sync.POST_WAKE_READ_SECONDS, sync.INFLIGHT_READ_SECONDS),
        ("before", 0, 0),
    ):
        monkeypatch.setattr(sync, "POST_WAKE_READ_SECONDS", post_wake)
        monkeypatch.setattr(sync, "INFLIGHT_READ_SECONDS", inflight)
        charged[scenario] = {
            (m, s, a): sync.wait_seconds(
                main_live=A, heavy_live=B, heavy_is_ancestor=True,
                heavy_release_age_min=a, now=_at(m).replace(second=s),
            )
            for m in range(60)
            for s in (0, 13, 31, 47, 59)
            for a in (None, 0, 5, floor - 48, floor - 30, floor - 8, floor - 1, floor)
        }
    monkeypatch.undo()
    removed = [k for k, v in charged["before"].items() if v and not charged["now"][k]]
    assert removed, "the charge removes nothing — this test proves nothing"
    for key in removed:
        minute, second, age = key
        now = _at(minute).replace(second=second)
        wake = now + timedelta(seconds=charged["before"][key])
        doomed_at_the_verdict = not sync.inside_window(
            wake + timedelta(seconds=sync.POST_WAKE_READ_SECONDS)
        )
        closing_edge = now + timedelta(seconds=sync.band_seconds_left_at_open(now))
        doomed_at_the_final_check = (
            wake + timedelta(seconds=sync.wake_to_push_seconds()) > closing_edge
        )
        assert doomed_at_the_verdict or doomed_at_the_final_check, key
    # Nothing is GAINED either: the charge may only ever remove a sleep.
    assert not [k for k, v in charged["now"].items() if v and not charged["before"][k]]


def test_a_sleep_that_fits_exactly_lands_the_push_on_a_zero_and_is_not_taken():
    """The deadline is the band's closing EDGE, so `>` re-admits the defect.

    `band_seconds_left` is 0 AT the edge, not at the second after it — the band is
    minute-inclusive and 14:59:00 is already outside. So a sleep whose charge fits
    the remainder EXACTLY puts the push on a zero, and the final band check that
    stands in front of it HOLDs: the same lost cycle this ship is about, one gate
    further down and one second wide.

    Reachable rather than theoretical: it needs only a trigger whose second is
    `-wake_to_push_seconds()` mod 60, which for an arbitrary arrival is 1 in 60 of
    the floor-driven sleeps that reach the edge at all. Found by mutating `>=` back
    to `>` after the fix, which is the only reason it is not still in there."""
    floor = sync.min_cycle_interval_min()
    now = _at(50).replace(second=(-sync.wake_to_push_seconds()) % 60)
    # The exact fit, stated rather than assumed.
    assert 8 * 60 + sync.wake_to_push_seconds() == sync.band_seconds_left_at_open(now)
    secs = sync.wait_seconds(
        main_live=A, heavy_live=B, heavy_is_ancestor=True,
        heavy_release_age_min=floor - 8, now=now,
    )
    assert secs == 0
    # …and this is what taking it would have bought: a push on a closed band.
    would_push_at = now + timedelta(seconds=8 * 60 + sync.wake_to_push_seconds())
    assert sync.band_seconds_left(would_push_at) == 0
    assert not sync.inside_window(would_push_at)


def test_judging_the_wake_is_sound_only_because_the_deadline_covers_the_re_read(
    monkeypatch,
):
    """`decide` is still asked about the WAKE, which is not when it is called. The
    deadline is what makes that sound, and this is the invariant that says so.

    Charging the re-read at the `decide` call as well would be unreachable code —
    once the deadline has proved the band is open all the way to the PUSH, it is
    open at the verdict too, `wake_to_push_seconds()` earlier. So the equivalence
    is asserted instead of duplicated: weakening the deadline separates the two
    instants and fails this, rather than silently re-opening the hour.

    The second half proves that is a real dependency and not a restatement —
    with the charges zeroed, a sleep exists whose two readings DISAGREE."""
    floor = sync.min_cycle_interval_min()
    grid = [
        (m, s, a)
        for m in range(60)
        for s in (0, 13, 17, 31, 43, 47, 59)
        for a in (None, 0, 5, floor - 48, floor - 30, floor - 8, floor - 1, floor)
    ]

    def _readings(minute, second, age):
        now = _at(minute).replace(second=second)
        secs = sync.wait_seconds(
            main_live=A, heavy_live=B, heavy_is_ancestor=True,
            heavy_release_age_min=age, now=now,
        )
        if not secs:
            return None
        projected = None if age is None else age + (secs + 59) // 60
        return tuple(
            sync.decide(
                main_live=A, heavy_live=B, heavy_is_ancestor=True,
                heavy_release_age_min=projected,
                now=now + timedelta(seconds=secs + extra),
            ).code
            for extra in (0, sync.POST_WAKE_READ_SECONDS)
        )

    agreed = 0
    for key in grid:
        readings = _readings(*key)
        if readings is None:
            continue
        assert readings == (PUSH, PUSH), (key, readings)
        agreed += 1
    assert agreed > 200, agreed

    # Now take the deadline's charge away and sweep again. The two readings come
    # apart, and every sleep that separates them is one the old rule took and the
    # run then woke up to lose — so the agreement above is the deadline's doing and
    # not a property of the arithmetic.
    charge = sync.POST_WAKE_READ_SECONDS
    monkeypatch.setattr(sync, "POST_WAKE_READ_SECONDS", 0)
    monkeypatch.setattr(sync, "INFLIGHT_READ_SECONDS", 0)
    assert sync.wake_to_push_seconds() == 0
    disagreed = []
    for minute, second, age in grid:
        now = _at(minute).replace(second=second)
        secs = sync.wait_seconds(
            main_live=A, heavy_live=B, heavy_is_ancestor=True,
            heavy_release_age_min=age, now=now,
        )
        if not secs:
            continue
        if not sync.inside_window(now + timedelta(seconds=secs + charge)):
            disagreed.append((minute, second, age, secs))
    assert disagreed, "the deadline is not what holds the two readings together"


def test_the_post_wake_charge_covers_every_step_between_the_sleep_and_the_verdict():
    """`POST_WAKE_READ_SECONDS` is measured over `read_facts` then `decide`, so it
    is only true while those are the only two things in there. A third read added
    after the sleep is band this constant does not know it is spending."""
    code = _workflow_code()
    after_sleep = code[code.index('sleep "$WAIT_S"'):]
    between = after_sleep[:after_sleep.index("heavy_sync_decision.py decide")]
    assert between.count("read_facts") == 1, between
    for reaches_out in ("curl", "ls-remote", "git fetch", "heavy_sync_decision.py "):
        assert reaches_out not in between, (reaches_out, between)


def test_the_run_still_owes_an_in_flight_read_and_a_final_band_check_after_the_verdict():
    """Why the deadline charges `INFLIGHT_READ_SECONDS` too, pinned on the
    workflow rather than left in a comment: `decide` is not the last gate between
    the wake and the push, so a sleep landing with only the re-read's worth of
    band still loses the cycle — one gate further down."""
    code = _workflow_code()
    between = code[
        code.index("heavy_sync_decision.py decide"):code.index("git push heroku-heavy")
    ]
    assert "celery/inspect" in between
    assert "heavy_sync_decision.py inflight" in between
    assert "heavy_sync_decision.py band-seconds-left" in between
    assert "the band closed while the fleet was being read" in between


def test_the_floors_own_clock_is_read_from_the_budget_and_not_from_a_number(monkeypatch):
    """`seconds_until_floor_clears` may not become a second opinion about the
    floor, and its polarity on an unreadable age is `decide`'s: proceed."""
    floor = sync.min_cycle_interval_min()
    assert sync.seconds_until_floor_clears(None) == 0
    assert sync.seconds_until_floor_clears(floor) == 0
    assert sync.seconds_until_floor_clears(floor + 500) == 0
    assert sync.seconds_until_floor_clears(floor - 24) == 24 * 60
    monkeypatch.setattr(sync, "ACCEPTED_CYCLES_PER_DAY", 6)
    assert sync.seconds_until_floor_clears(floor - 24) == (
        sync.min_cycle_interval_min() - floor + 24
    ) * 60


def test_an_unreadable_age_does_not_stop_the_wait_any_more_than_it_stops_the_push():
    """The cost gate's polarity, carried through the projection unchanged."""
    assert _wait(10, age=None) > 0


def test_an_attended_run_never_sleeps_because_it_is_exempt_from_the_band():
    """`--dispatched` overrules the clock, so waiting for it is waiting for a
    gate that is not being applied."""
    assert _wait(10, dispatched=True) == 0
    assert _wait(10, dispatched=True, age=0) == 0


def test_the_wait_plan_subcommand_prints_the_number_alone_and_exits_zero():
    """`age`'s contract, for a reason of its own: a wait that cannot compute
    itself must degrade to NOT waiting, never to a code the workflow reads."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "wait-plan", "--main-live", A,
         "--heavy-live", B, "--heavy-is-ancestor", "true"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    assert out.isdigit(), out
    opens, closes = sync.window_bounds()
    assert 0 <= int(out) <= (60 - (closes - opens + 1)) * 60
    # The WHY reaches the log without becoming the number the shell captures.
    assert proc.stderr.strip()
    assert "\n" not in proc.stdout.strip()


def test_the_wait_plan_is_handed_the_same_facts_the_decision_gets():
    """A gate fed a subset of the facts is a different gate."""
    code = _workflow_code()
    plan = code[code.index("heavy_sync_decision.py wait-plan"):][:600]
    for flag in ("--main-live", "--heavy-live", "--heavy-is-ancestor",
                 "--heavy-release-age-min", "$DISPATCH_FLAG"):
        assert flag in plan, flag
    # and it is asked BEFORE the decision it exists to make reachable
    assert code.index("heavy_sync_decision.py wait-plan") < code.index(
        "heavy_sync_decision.py decide"
    )


def test_the_job_timeout_covers_the_longest_run_the_band_permits():
    """It is a ceiling on a job that now sleeps, and the thing it protects is
    the `heavy-deploy` group — GitHub's default would hold it six hours."""
    timeout = re.search(r"(?m)^\s*timeout-minutes:\s*(\d+)\s*$", WORKFLOW.read_text())
    assert timeout, "the sleeping job has no timeout"
    opens, closes = sync.window_bounds()
    longest_wait_min = 60 - (closes - opens + 1)
    band_min = closes - opens + 1
    assert int(timeout.group(1)) >= longest_wait_min + band_min, (
        f"timeout-minutes={timeout.group(1)} is under the {longest_wait_min}-min wait "
        f"plus the {band_min}-min band the in-flight loop may spend"
    )


# ── and the prologue itself, RUN rather than grepped ───────────────────────────
#
# Same discipline as the wait loop above: `"read_facts" in body` passes on a
# block that defines the function and never calls it twice, which is the only
# property that makes sleeping safe. So the block is lifted out of the YAML and
# executed with `git`, `sleep` and the two script reads stubbed.


def _extract_prologue() -> str:
    lines = _workflow_code().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "read_facts() {")
    gate = next(
        i for i in range(start, len(lines))
        if lines[i].strip() == 'if [ "$WAIT_S" -gt 0 ]; then'
    )
    end = next(i for i in range(gate + 1, len(lines)) if lines[i] == " " * 10 + "fi")
    return "\n".join(ln[10:] for ln in lines[start:end + 1])


def _run_prologue(tmp_path, *, wait_s, shas, dispatched=False):
    """Run the workflow's prologue against a scripted world.

    Returns (MAIN_LIVE it ended up with, number of ls-remote reads, sleeps).
    `shas` is the sequence of main-live shas `git ls-remote` serves, one per
    read_facts call — so a second, different sha proves the re-read happened
    and that the run did not keep the one it went to sleep on.
    """
    stub = tmp_path / "stub"
    stub.mkdir(parents=True)
    state = tmp_path / "state"
    state.mkdir(parents=True)
    (state / "shas").write_text("\n".join(shas))

    (stub / "git").write_text(
        "#!/bin/bash\n"
        'case "$*" in\n'
        "  *ls-remote*heroku-main*)\n"
        f"    n=$(cat {state}/mains 2>/dev/null || echo 0); n=$((n+1)); echo $n > {state}/mains\n"
        f"    sed -n \"${{n}}p\" {state}/shas; echo '\trefs/heads/master'\n"
        "    ;;\n"
        "  *ls-remote*heroku-heavy*)\n"
        f"    n=$(cat {state}/heavies 2>/dev/null || echo 0)\n"
        f"    echo $((n+1)) > {state}/heavies\n"
        f"    printf '%s\\trefs/heads/master\\n' '{B}'\n"
        "    ;;\n"
        "esac\n"
        "exit 0\n"
    )
    (stub / "sleep").write_text(
        "#!/bin/bash\n"
        f"echo \"$1\" >> {state}/sleeps\n"
    )
    (stub / "python3").write_text(
        "#!/bin/bash\n"
        'case "$*" in\n'
        # `wait-plan` FIRST: its own command line carries
        # `--heavy-release-age-min`, so an `*age*` arm above it would answer the
        # wait with the age and the harness would be testing itself.
        f"  *wait-plan*) echo {wait_s} ;;\n"
        "  *age*) echo 9999 ;;\n"
        f'  *) exec "{sys.executable}" "$@" ;;\n'
        "esac\n"
    )
    for name in ("git", "sleep", "python3"):
        (stub / name).chmod(0o755)

    script = tmp_path / "prologue.sh"
    script.write_text(
        "set -uo pipefail\n"
        + (f'DISPATCHED="{"1" if dispatched else ""}"\n')
        + _extract_prologue()
        + '\necho "ENDED_ON=$MAIN_LIVE"\n'
    )
    proc = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, cwd=str(REPO),
        env={**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"}, timeout=60,
    )
    assert "ENDED_ON=" in proc.stdout, proc.stdout + proc.stderr
    ended = proc.stdout.rsplit("ENDED_ON=", 1)[1].split()[0]
    reads = int((state / "mains").read_text()) if (state / "mains").exists() else 0
    sleeps = (state / "sleeps").read_text().split() if (state / "sleeps").exists() else []
    return ended, reads, sleeps, proc.stderr


def test_a_zero_wait_is_the_run_this_file_has_always_been(tmp_path):
    ended, reads, sleeps, _ = _run_prologue(tmp_path, wait_s=0, shas=[A, "c" * 40])
    assert (ended, reads, sleeps) == (A, 1, [])


def test_the_sleep_happens_and_every_fact_is_read_again_after_it(tmp_path):
    """The whole safety of sleeping: the sha pushed is the one main is serving
    when it is pushed, not the one it was serving when the run started."""
    ended, reads, sleeps, _ = _run_prologue(tmp_path, wait_s=1680, shas=[A, "c" * 40])
    assert sleeps == ["1680"]
    assert reads == 2
    assert ended == "c" * 40, "the run pushed the sha it went to sleep on"


@pytest.mark.parametrize("answer", ["", "later", "-5", "30s"])
def test_a_wait_that_did_not_parse_is_not_a_licence_to_sleep(tmp_path, answer):
    """Gotcha #54 on the value, not the exit code — and the degraded state is
    the old behaviour, which is the only safe direction for a new gate.

    The stderr assertion is what makes the `case` guard load-bearing rather
    than decorative, and it was written because the mutant that deletes the
    guard SURVIVED without it: `[ later -gt 0 ]` already fails closed, so the
    run happens not to sleep either way. What changes is that the log fills
    with a bash `integer expression expected` — an instrument declining to
    parse must say so in its own words, not by tripping over the answer, or
    the next reader debugs the shell instead of the gate.
    """
    ended, reads, sleeps, stderr = _run_prologue(
        tmp_path / answer.replace(" ", "_") or "empty", wait_s=f"'{answer}'", shas=[A, "c" * 40]
    )
    assert (ended, reads, sleeps) == (A, 1, [])
    assert "integer expression" not in stderr, stderr


# ── #5886, THE INVERSION: the in-flight veto expires ───────────────────────────
#
# The gate was built to stop a release killing a heavy job mid-run, and priced
# that kill at "one lost pass" in its own docstring. Censused over ~24 h of this
# workflow's run logs (latency/748): 106 BUSY / 6 IDLE / 0 UNKNOWN in-flight
# readings, no minute of the band clearing, and 6 of the 8 runs that reached PUSH
# killed by the gate. `bainluck-heavy` reached 5h16m against a 180-min floor.
#
# A cost gate with no expiry is a veto, so the veto now expires — at the band's
# closing edge only, on a run that has already spent the band looking for the
# idle moment the gate wants.

#: Every heavy-release interval since v17, in minutes, read from
#: `heroku releases -a bainluck-heavy` on 2026-09-20 (53 releases total; v8..v16
#: are the pre-`workflow_run` design and are excluded deliberately — they are not
#: the population this clause is tuned against). The body of the distribution is
#: the floor plus at most one band; the four-value tail is what the expiry
#: truncates, and it is the only part of the record that must move.
OBSERVED_HEAVY_INTERVALS_MIN = (
    185.6, 240.8, 246.0, 227.0, 195.5, 224.6, 185.0, 240.0, 190.2, 225.8,
    183.9, 236.3, 239.8, 193.8, 284.4, 196.1, 223.8, 183.0, 188.6, 183.9,
    226.4, 194.5, 285.5, 194.1, 239.8, 239.2, 227.9, 184.4, 188.9, 225.7,
    184.7, 240.1, 189.1, 227.0, 182.4, 190.6, 286.2, 244.3, 190.2, 225.5,
    185.8, 238.0, 310.5, 238.6,
)


def test_the_veto_expiry_is_the_floor_plus_its_licensed_band():
    """Derived from the two things it is made of, never typed in."""
    assert sync.veto_expiry_min() == (
        sync.min_cycle_interval_min() + sync.VETO_BUDGET_BANDS * sync.BAND_PERIOD_MIN
    )
    # And it is strictly later than the moment a sync first becomes permissible,
    # or the veto would have no licence at all and the gate would be deleted
    # rather than bounded.
    assert sync.veto_expiry_min() > sync.min_cycle_interval_min()


def test_moving_the_accepted_budget_moves_the_veto_expiry(monkeypatch):
    """The floor and the expiry are one number and a licence, not two numbers.

    Halving the accepted cycle rate doubles the floor, and the expiry has to
    follow it — a literal 240 would silently become "the floor minus 120".
    """
    monkeypatch.setattr(sync, "ACCEPTED_CYCLES_PER_DAY", 4)
    assert sync.min_cycle_interval_min() == 360
    assert sync.veto_expiry_min() == 360 + sync.BAND_PERIOD_MIN


def test_the_licence_is_one_band_and_not_a_free_number(monkeypatch):
    """`VETO_BUDGET_BANDS` is counted in BANDS because that is the unit the
    veto's own message promises in ("the next trigger re-reads and re-judges").
    Two bands is a different claim and must read as one."""
    monkeypatch.setattr(sync, "VETO_BUDGET_BANDS", 2)
    assert sync.veto_expiry_min() == sync.min_cycle_interval_min() + 120


def test_the_expiry_is_silent_on_the_body_of_the_release_record():
    """CHECKED AGAINST THE WORLD, NOT ONLY AGAINST ITSELF.

    A clause that fires on every cycle has not bounded the veto, it has removed
    it — and the gate protects something real. So the measured record decides:
    the normal interval must sit inside the licence and only the tail outside it.
    """
    expiry = sync.veto_expiry_min()
    fires = [g for g in OBSERVED_HEAVY_INTERVALS_MIN if g >= expiry]
    quiet = [g for g in OBSERVED_HEAVY_INTERVALS_MIN if g < expiry]
    # The tail, and today's 310.5 is in it. The four intervals that sit within
    # a tenth of a minute of the expiry (240.0, 240.1, 240.8, 244.3) are in the
    # list too and were NOT in the first draft of it — the expiry is inclusive,
    # and a hand-written expectation is how that gets forgotten.
    assert sorted(fires) == [
        240.0, 240.1, 240.8, 244.3, 246.0, 284.4, 285.5, 286.2, 310.5
    ], fires
    # Fires on a minority, so the gate still does its job on the common cycle.
    assert len(fires) / len(OBSERVED_HEAVY_INTERVALS_MIN) < 0.25
    # And it is not vacuous in the other direction: the clause has to have
    # something to bite on, or it is prose.
    assert fires and max(quiet) < expiry


def test_the_starved_episode_this_clause_exists_for_would_have_fired():
    """v59 -> v60 ran 310.5 min, and today's open interval passed 300 min with
    run 35526966041 reading `heavy release age: 300 min` and holding on BUSY."""
    assert sync.veto_expired(300).code == sync.IDLE
    assert sync.veto_expired(300).verdict == "EXPIRED"
    assert sync.veto_expired(310).code == sync.IDLE


@pytest.mark.parametrize("age", [0, 1, 179, 180, 200, 239])
def test_a_run_inside_the_licence_keeps_the_veto(age):
    """Everything short of the expiry holds, floor included: clearing the floor
    is what makes a sync PERMITTED, never what makes the veto spent."""
    decision = sync.veto_expired(age)
    assert decision.code == sync.BUSY
    assert decision.verdict == "LICENSED"


def test_the_boundary_is_inclusive_and_the_minute_below_it_is_not():
    """The two adjacent inputs, because a `>` here is a whole extra band of
    drift and reads identically in every other test."""
    assert sync.veto_expired(sync.veto_expiry_min()).code == sync.IDLE
    assert sync.veto_expired(sync.veto_expiry_min() - 1).code == sync.BUSY


@pytest.mark.parametrize("raw", ["", "   ", "unreadable", "300min", None])
def test_an_unreadable_age_holds_and_is_the_one_cost_gate_that_does(raw):
    """THE POLARITY INVERSION, ASSERTED RATHER THAN COMMENTED.

    Every other cost gate in this file proceeds on a fact it cannot read, because
    proceeding is the ship. This one cannot: proceeding here means cycling the
    dyno on top of a job we can SEE running, so the escalation has to prove its
    premise. An age we could not read proves nothing.

    Asserted against `decide`'s opposite answer on the SAME unreadable input, so
    the test cannot pass by both gates quietly agreeing.
    """
    parsed = sync._age_arg(raw)
    assert parsed is None
    assert sync.veto_expired(parsed).code == sync.BUSY
    assert sync.veto_expired(parsed).verdict == "LICENSED"
    # The contrast: the cycle floor, given the same unreadable age, PUSHes.
    assert sync.decide(
        main_live=A, heavy_live=B, heavy_is_ancestor=True,
        heavy_release_age_min=parsed, now=_at(sync.window_bounds()[0]),
    ).code == PUSH


def test_the_veto_cli_exit_codes_are_the_ones_the_workflow_branches_on():
    """0 = expired (cycle it), 1 = still licensed (hold). The workflow reads the
    VALUE, so a third code must never appear from a legitimate input."""
    for age, expected in (("300", 0), ("239", 1), ("", 1), ("junk", 1)):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "veto-expired", "--heavy-release-age-min", age],
            capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == expected, (age, proc.stdout, proc.stderr)
        # The verdict is the first token, which is how the workflow reads it.
        assert proc.stdout.split(":", 1)[0] in {"EXPIRED", "LICENSED"}, proc.stdout


def test_the_expiry_is_only_ever_asked_at_the_edge():
    """STRUCTURAL, and the property the whole design rests on.

    The clause may only decide what happens to a band that is already lost. If
    `veto-expired` were consulted anywhere else in the loop, a run would cycle a
    busy fleet at :39 with twenty minutes of band left in which the fleet might
    have gone idle by itself — which is the gate, deleted.
    """
    loop = _extract_wait_loop()
    assert loop.count("veto-expired") == 1, loop
    edge = loop.split(f'"$BAND_LEFT" -le {sync.CONFIRM_SEPARATION_SECONDS} ]', 1)
    assert len(edge) == 2, "the edge branch moved; this guard is now aimed at nothing"
    before, after = edge
    assert "veto-expired" not in before
    # ...and inside the edge's own BUSY arm, not its idle one: an idle reading at
    # the edge already pushes, so asking there would be dead code that reads like
    # a policy.
    assert "veto-expired" in after.split("break", 1)[0]


def test_the_expiry_is_asked_only_of_a_busy_reading():
    """It is an escalation of the BUSY verdict. Reaching it from the idle arm
    would make an idle push claim it cycled a running job."""
    loop = _extract_wait_loop()
    idle_arm, busy_arm = loop.split('if [ "$INFLIGHT" -eq 0 ]; then', 1)[1].split("else", 1)
    assert "veto-expired" not in idle_arm
    assert "veto-expired" in busy_arm


def test_a_starved_run_cycles_the_busy_fleet_at_the_edge(tmp_path):
    """END TO END, through the real script: run 35525028003, replayed.

    It reached PUSH with `heavy release age: 280 min`, polled the entire band,
    found every reading busy, and exited HOLD. With the expiry it pushes.
    """
    code, reads, sleeps, veto = _run_wait_loop(
        tmp_path, bodies=[BUSY_BODY, BUSY_BODY], deadlines=[600, 30], age="280"
    )
    assert (code, reads, sleeps) == (0, 2, 1)
    assert veto is True


def test_the_same_run_inside_the_licence_still_holds(tmp_path):
    """The reverse population, or the test above is satisfied by a loop that
    pushes on every busy fleet. 220 min is run 35520366305 — 22 polls, 22 busy —
    and it must STILL hold, because its next trigger genuinely has a band left
    to try in.
    """
    code, reads, sleeps, veto = _run_wait_loop(
        tmp_path, bodies=[BUSY_BODY, BUSY_BODY], deadlines=[600, 30], age="220"
    )
    assert (code, reads, sleeps) == (1, 2, 1)
    assert veto is False


def test_a_starved_run_still_prefers_an_idle_moment_inside_the_band(tmp_path):
    """THE CLAUSE TAKES NOTHING AWAY, which is the claim that makes it safe.

    A starved run does not push on the first busy reading — it spends the whole
    band exactly as before, and takes an idle moment the instant it appears. The
    expiry is the fallback for the band it was going to lose, never a shortcut
    through it.
    """
    code, reads, sleeps, veto = _run_wait_loop(
        tmp_path,
        bodies=[BUSY_BODY, BUSY_BODY, IDLE_BODY, IDLE_BODY],
        deadlines=[600, 540, 480],
        age="600",
    )
    assert (code, reads, sleeps) == (0, 4, 3)
    # It pushed on a CONFIRMED IDLE fleet, not on the expiry.
    assert veto is False


def test_a_starved_run_with_an_unreadable_age_holds_end_to_end(tmp_path):
    """The workflow passes `${HEAVY_AGE_MIN:-}`, which is empty whenever the
    Platform API read failed. Through the loop, that is still a hold."""
    code, reads, sleeps, veto = _run_wait_loop(
        tmp_path, bodies=[BUSY_BODY, BUSY_BODY], deadlines=[600, 30], age=""
    )
    assert (code, reads, sleeps) == (1, 2, 1)
    assert veto is False


def test_the_stamped_age_understates_the_drift_at_the_edge():
    """WHICH DIRECTION THE STALE FACT ERRS IN, asserted rather than assumed.

    `HEAVY_AGE_MIN` is stamped by `read_facts` before the loop and is not
    re-read, so by the time the edge is reached it is up to a whole band old. An
    age that is too LOW can only hold a veto that should have expired — never
    expire one that should have held — so the staleness is safe in the one
    direction that matters, and this pins that rather than the comment.
    """
    band_width_min = sync.window_bounds()[1] - sync.window_bounds()[0]
    true_age = sync.veto_expiry_min() + band_width_min - 1
    stamped = true_age - band_width_min
    assert sync.veto_expired(stamped).code == sync.BUSY, (
        "the stale age must be able to under-fire — that is the safe direction"
    )
    assert sync.veto_expired(true_age).code == sync.IDLE, (
        "and the fresh age must fire, or the staleness is not the reason"
    )


def test_the_summary_line_cannot_claim_a_clear_fleet_on_a_cycled_one():
    """A cycled-anyway run and a genuinely idle one both leave `INFLIGHT=0`, so
    the log line after the loop has to read the flag. Without this the run that
    knowingly killed a job prints "clear to cycle worker-heavy", and the next
    reader of #5886 cannot tell the two apart in a log."""
    code = _workflow_code()
    body = code.split('case "$INFLIGHT" in', 1)[1]
    assert 'if [ -n "$VETO_EXPIRED" ]; then' in body.split("esac", 1)[0]
    # And the variable is initialised in the block the loop lives in, so `set -u`
    # cannot be what discovers it.
    assert "VETO_EXPIRED=" in code.split("while true; do", 1)[0].rsplit("IDLE_STREAK=0", 1)[1]
    # THE WRITE, NOT ONLY THE READ. Deleting `VETO_EXPIRED=1` from the expiry
    # branch leaves every assertion above true and the summary line silently
    # wrong again — the mutant that survived this guard until it was widened,
    # and the reason it is worth writing twice. It is killed end to end by
    # `test_a_starved_run_cycles_the_busy_fleet_at_the_edge`; this states why.
    expiry_branch = _extract_wait_loop().split("veto-expired", 1)[1].split("break", 1)[0]
    assert "VETO_EXPIRED=1" in expiry_branch, expiry_branch


def test_the_expiry_never_reaches_past_the_band_or_the_never_backwards_guard():
    """WHAT IT IS EXEMPT FROM IS EXACTLY ONE GATE.

    The final band check and the ancestry refusal both sit after the wait loop
    and are not conditioned on the flag, so a starved run still cannot push
    outside the band or rewind heavy.
    """
    code = _workflow_code()
    after_esac = code.split('case "$INFLIGHT" in', 1)[1].split("esac", 1)[1]
    assert "band-seconds-left" in after_esac, "the final band check is gone"
    assert "VETO_EXPIRED" not in after_esac.split("BEHIND=", 1)[0], (
        "the final band check learned about the expiry — it must not"
    )
    # And the push itself is still the plain one. Read off the PUSH COMMAND and
    # not the file: the file legitimately contains the string in the echo that
    # explains why a rejection is never retried with it, so `"--force" not in
    # code` fails on a correct workflow — the trap `_workflow_code`'s own
    # docstring names, met again one layer down.
    push = next(
        line for line in code.splitlines() if "git push heroku-heavy" in line
    )
    assert "--force" not in push and "-f " not in push, push
