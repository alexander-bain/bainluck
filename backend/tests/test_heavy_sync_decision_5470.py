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

    EVERY minute is asserted, not the first (latency/362). With more than one
    nominal fire per hour the difference is the whole point: `*/20` and
    `34,42,50` are indistinguishable under the scheduler we measured, but under a
    punctual one the first delivers a single useful attempt an hour and the
    second delivers three. Checking only the first minute would pass both.
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

    HOURLY WAS NOT ENOUGH EITHER, and the floor below is the measurement that
    says so (latency/362, 2026-09-13 04:44Z). "Hourly => 24 attempts/day" counts
    SLOTS; in the 16 nominal slots since this workflow landed the scheduler
    delivered **4 runs**, so the real attempt rate was ~6/day and heavy sat
    7h06m / 81 commits behind the main app's live commit. Expected in-band
    deliveries are N x 0.25 x 0.42 => N x 0.104/h, which is why three fires an
    hour (~3.2h) is the floor and one (~9.6h) is not.

    Attempts are near-free by construction and that is asserted, not assumed:
    `decide` HOLDs on `main_live == heavy_live` BEFORE consulting the clock, so
    an extra run against an already-synced app never deploys. If that ordering
    is ever inverted, raising the frequency would start cycling the worker and
    this test should stop licensing it.

    No ceiling is asserted. The cost of one more attempt is one calibration unit
    (~2 min, measured) and the rate that would price it — the 4-of-16 delivery
    fraction — is one day old and soft; pinning a maximum here would pin that
    number. The real bound is the band: every fire must sit inside it, which the
    test above enforces, so the schedule cannot grow past the band's width.
    """
    hour_field = _cron().group(2)
    assert hour_field == "*", (
        f"heavy-sync must fire at least hourly, got hour field {hour_field!r}: the fire "
        "minute is not controllable (#5662), so attempts are the only lever on the band"
    )
    minutes = _cron_minutes()
    assert len(minutes) >= 3, (
        f"heavy-sync fires {len(minutes)} time(s) an hour ({minutes}); the measured "
        "delivery rate was 4 runs in 16 nominal slots, so at fewer than 3 the expected "
        "wait exceeds the ~3h drift this design claims to bound"
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
