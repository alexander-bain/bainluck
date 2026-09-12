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
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "heavy_sync_decision.py"
WORKFLOW = REPO / ".github" / "workflows" / "heavy-sync.yml"

PUSH, HOLD, REFUSE, USAGE = 0, 1, 2, 3

A = "a" * 40          # a plausible "main live" sha
B = "b" * 40          # a plausible "heavy live" sha


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
    """:34-:58 must be arithmetic, so a re-measurement moves it.

    Pinning the literals alone would let someone edit a constant and leave the
    band stale; pinning only the derivation would let both drift together. Both,
    together, is the check.
    """
    opens, closes = sync.window_bounds()
    assert (opens, closes) == (34, 58)
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
    assert sync.window_bounds()[0] == 44
    monkeypatch.setattr(sync, "REBUILD_DURATION_MIN", 22)

    monkeypatch.setattr(sync, "MIN_RELEASE_LAG_MIN", 8)
    assert sync.window_bounds()[0] == 29
    monkeypatch.setattr(sync, "MIN_RELEASE_LAG_MIN", 3)

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
    """
    assert sync.REBUILD_DURATION_MIN == 22
    stale_open = sync.REBUILD_START_MIN + 7 - sync.MIN_RELEASE_LAG_MIN
    assert stale_open < sync.REBUILD_START_MIN + sync.REBUILD_DURATION_MIN


def test_the_whole_band_lands_clear_of_the_rebuild():
    """Not an edge check — every minute in the band must be safe, both ends.

    The opening edge is tested against the rebuild's END, and the closing edge
    against the NEXT rebuild's start, each with the lag that applies to it.
    """
    opens, closes = sync.window_bounds()
    rebuild_end = sync.REBUILD_START_MIN + sync.REBUILD_DURATION_MIN
    # Earliest cycle a push at `opens` can produce is still after the rebuild.
    assert opens + sync.MIN_RELEASE_LAG_MIN >= rebuild_end
    # Latest cycle a push at `closes` can produce is still before the next one.
    assert closes + sync.MAX_RELEASE_LAG_MIN < 60 + sync.REBUILD_START_MIN


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


def test_the_workflows_cron_minute_is_inside_the_derived_band():
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
    """
    minute = int(_cron().group(1))
    opens, closes = sync.window_bounds()
    assert opens <= minute <= closes


def test_enough_attempts_that_a_random_fire_minute_reaches_the_band():
    """THE sync-nothing guard, keyed on the quantity that controls the outcome.

    Since the fire minute is effectively uniform (#5662, measured), the only
    lever on whether any run lands inside the band is HOW MANY runs there are.
    At the derived band's width a 3-hourly cron was 8 attempts/day => ~8.3h
    expected wait, against a design claiming to bound drift to ~3h; this pins
    the schedule at hourly-or-better so the expected wait stays ~2.5h.

    Attempts are near-free by construction and that is asserted, not assumed:
    `decide` HOLDs on `main_live == heavy_live` BEFORE consulting the clock, so
    an extra run against an already-synced app never deploys. If that ordering
    is ever inverted, raising the frequency would start cycling the worker and
    this test should stop licensing it.
    """
    hour_field = _cron().group(2)
    assert hour_field == "*", (
        f"heavy-sync must fire at least hourly, got hour field {hour_field!r}: the fire "
        "minute is not controllable (#5662), so attempts are the only lever on the band"
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
