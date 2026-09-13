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
from datetime import datetime, timezone
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
    assert "api.bainluck.com" in curl_line
    assert "X-BainLuck-Origin" in body
    # One read is not a reading: two of eight calls to this endpoint returned
    # HTTP 500 when it was measured (2026-09-13 11:02-11:03Z). UNKNOWN proceeds,
    # so a flaky instrument does not break the sync — it quietly turns the veto
    # off, which is worse than failing, because the gate still reads as present.
    assert "--retry" in body


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
