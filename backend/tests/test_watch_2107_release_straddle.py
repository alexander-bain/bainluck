"""Ruling 130: a window that straddles a release is INCONCLUSIVE, on BOTH arms.

WHY THIS TEST EXISTS.

`docs/rulings/130-a-window-that-straddles-a-release-is-inconclusive.md` was
banked on this branch as prose, and prose is not a predicate. The ruling names
two failure directions and both are silent:

1. **False break** — a release ships mid-window, the window still holds pre-fix
   errors, the day is recorded FAILED and the counter resets to zero. As long as
   the deploy cadence beats the streak length (it does), seven days becomes
   eight, then nine, forever, and the instrument reads as "the fix is not
   holding".
2. **False bank** — a release ships a *regression* late in an otherwise clean
   window; the pre-release majority keeps the rate under threshold; the day
   banks and the streak certifies a slug that was live for forty minutes of it.

Direction 2 is why INCONCLUSIVE is a third verdict and not "count it as a
failure, to be safe": a conservative shortcut fixes direction 1 and leaves
direction 2 exactly where it was.

The two arms have different intervals, so they get different tests. Arm B's
interval is the probe window (`_detect_release` over the `commit` set already
collected by `run_probe` and, until now, thrown away). Arm A's interval is the
24 h Sentry `statsPeriod` (`arm_a_release_window`), which a single-slug
60-minute probe can sit entirely inside while the count itself spans two
deploys.

THE TRAP THIS FILE IS ALSO GUARDING, because the same script fell into it eight
days ago: `_detect_restart` used to be `len(processes) > 1`, a predicate that
was **unconditionally true** in production, so the falsifier could never bank a
day and nobody noticed, because "not yet closed" is the expected reading. A
straddle detector that fires on every window would reproduce that failure with a
new name. So `test_the_healthy_shape_is_not_a_straddle` and
`test_a_full_day_of_one_commit_is_clear` are load-bearing: they assert the
detectors are FALSE on the shape production has almost all the time.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "watch_2107_feed_500s.py"

SHA_A = "ad99166ec1d24f8b0a5c"
SHA_B = "b5c2a750993e1146aa07"

NOW = datetime(2026, 8, 24, 18, 0, tzinfo=timezone.utc)


def _load():
    spec = importlib.util.spec_from_file_location("watch_2107", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _row(started: datetime, commits: dict) -> dict:
    return {"started_at": started.isoformat(), "probe": {"commits": commits}}


def _probe(**over) -> dict:
    """A clean single-slug window. Every field the grader reads is present."""
    base = {
        "samples": 60,
        "server_errors": 0,
        "transport_errors": 0,
        "process_ids": {"w1": 12, "w2": 12},
        "commits": {SHA_A: 24},
        "restarted": False,
        "restart_reasons": [],
        "release_straddle": False,
        "release_reasons": [],
    }
    base.update(over)
    return base


CLEAR = {"verdict": "CLEAR", "reason": "one commit across the lookback"}
STRADDLED = {"verdict": "STRADDLED", "reason": "two commits in the lookback"}
UNKNOWN_COVERAGE = {"verdict": "UNKNOWN", "reason": "no anchor row"}
SENTRY_CLEAN = {"verdict": "CLEAN", "count_24h": 0, "reason": None}
SENTRY_FIRED = {"verdict": "FIRED", "count_24h": 9, "reason": "9 events in 24h"}


# ------------------------------------------------- arm B: inside the window


class TestArmBDetectsAReleaseInsideTheWindow:
    def test_the_healthy_shape_is_not_a_straddle(self):
        """One slug answering all hour. This must be FALSE or the seven never bank."""
        mod = _load()
        straddled, reasons = mod._detect_release({SHA_A: 24})
        assert straddled is False
        assert reasons == []

    def test_two_commits_inside_one_window_is_a_straddle(self):
        mod = _load()
        straddled, reasons = mod._detect_release({SHA_A: 19, SHA_B: 5})
        assert straddled is True
        assert "a release landed mid-window" in reasons[0]
        assert SHA_A[:12] in reasons[0] and SHA_B[:12] in reasons[0]

    def test_a_missing_commit_field_is_not_a_change(self):
        """`/api/health` predating the field reports None. Gotcha #53: the
        instrument not seeing a value is not the value differing. That case is
        the `process_ids` arm's, and it must not be double-reported here."""
        mod = _load()
        assert mod._detect_release({SHA_A: 20, None: 4}) == (False, [])
        assert mod._detect_release({None: 12}) == (False, [])
        assert mod._detect_release({}) == (False, [])


# ------------------------------------------- arm A: inside the 24h lookback


class TestArmALookback:
    def test_a_full_day_of_one_commit_is_clear(self):
        """The shape a deploy-free date has. Must be CLEAR, or nothing ever banks."""
        mod = _load()
        rows = [
            _row(NOW - timedelta(hours=h), {SHA_A: 20})
            for h in (48, 36, 26, 20, 12, 3)
        ]
        out = mod.arm_a_release_window(rows, NOW, {SHA_A: 24})
        assert out["verdict"] == "CLEAR", out["reason"]
        assert out["source"] == "history"

    def test_a_deploy_inside_the_lookback_straddles_even_when_the_window_is_single_slug(self):
        """The case arm B structurally cannot see: the probe ran entirely on
        SHA_B, but the 24h count it is scored against also covers SHA_A."""
        mod = _load()
        rows = [
            _row(NOW - timedelta(hours=30), {SHA_A: 20}),
            _row(NOW - timedelta(hours=20), {SHA_A: 20}),
            _row(NOW - timedelta(hours=4), {SHA_B: 20}),
        ]
        out = mod.arm_a_release_window(rows, NOW, {SHA_B: 24})
        assert out["verdict"] == "STRADDLED"
        assert "24h arm-A lookback" in out["reason"]

    def test_rows_inside_the_lookback_alone_cannot_certify_it(self):
        """A fresh state file agreeing with itself is not coverage.

        Rows inside the lookback all start after `now - 24h` by construction, so
        their unanimity says nothing about the hours before the earliest of them.
        Without an observation at or before the boundary the honest answer is
        UNKNOWN — and UNKNOWN is INCONCLUSIVE, never CLEAR.
        """
        mod = _load()
        rows = [_row(NOW - timedelta(hours=2), {SHA_A: 20})]
        out = mod.arm_a_release_window(rows, NOW, {SHA_A: 24})
        assert out["verdict"] == "UNKNOWN"
        assert "--last-release-at" in out["reason"]

    def test_unknown_resolves_after_one_day_of_history(self):
        """The warm-up is BOUNDED. This is the assertion that separates this
        detector from `_detect_restart`'s old unconditionally-true predicate:
        add the anchor row and the same input grades CLEAR."""
        mod = _load()
        rows = [
            _row(NOW - timedelta(hours=25), {SHA_A: 20}),
            _row(NOW - timedelta(hours=2), {SHA_A: 20}),
        ]
        assert mod.arm_a_release_window(rows, NOW, {SHA_A: 24})["verdict"] == "CLEAR"

    def test_an_empty_state_file_is_unknown_not_clear(self):
        mod = _load()
        assert mod.arm_a_release_window([], NOW, {SHA_A: 24})["verdict"] == "UNKNOWN"

    def test_a_release_older_than_the_lookback_does_not_straddle(self):
        """A deploy 30h ago is outside a 24h count. The commit before it is not
        in the lookback set, so it must not poison the verdict."""
        mod = _load()
        rows = [
            _row(NOW - timedelta(hours=40), {SHA_A: 20}),
            _row(NOW - timedelta(hours=26), {SHA_B: 20}),
            _row(NOW - timedelta(hours=5), {SHA_B: 20}),
        ]
        out = mod.arm_a_release_window(rows, NOW, {SHA_B: 24})
        assert out["verdict"] == "CLEAR", out["reason"]


class TestOperatorOverride:
    def test_a_recent_release_straddles(self):
        mod = _load()
        out = mod.arm_a_release_window(
            [], NOW, {SHA_A: 24}, last_release_at=NOW - timedelta(hours=3))
        assert out["verdict"] == "STRADDLED"
        assert out["source"] == "operator"
        assert "3.0h ago" in out["reason"]

    def test_an_old_release_clears_without_any_history(self):
        """The escape hatch: the operator reading `heroku releases` knows the
        answer exactly, so a first run on a deploy-free date need not wait a day."""
        mod = _load()
        out = mod.arm_a_release_window(
            [], NOW, {SHA_A: 24}, last_release_at=NOW - timedelta(hours=31))
        assert out["verdict"] == "CLEAR"
        assert out["source"] == "operator"

    def test_the_override_beats_the_history(self):
        """Recorded history is inference; the release list is the fact."""
        mod = _load()
        rows = [_row(NOW - timedelta(hours=h), {SHA_A: 20}) for h in (30, 10, 2)]
        out = mod.arm_a_release_window(
            rows, NOW, {SHA_A: 24}, last_release_at=NOW - timedelta(hours=1))
        assert out["verdict"] == "STRADDLED"
        assert out["source"] == "operator"

    def test_the_boundary_is_the_lookback_not_a_fudge(self):
        mod = _load()
        just_inside = mod.arm_a_release_window(
            [], NOW, {}, last_release_at=NOW - timedelta(hours=23, minutes=59))
        just_outside = mod.arm_a_release_window(
            [], NOW, {}, last_release_at=NOW - timedelta(hours=24, minutes=1))
        assert just_inside["verdict"] == "STRADDLED"
        assert just_outside["verdict"] == "CLEAR"


# ------------------------------------------------------------- the cascade


class TestGradeWindowOrdering:
    """Each straddle sits ahead of the arm it disqualifies, and no further."""

    def test_a_straddling_window_with_5xx_is_inconclusive_not_failed(self):
        """Direction 1, the false break. Those 500s may belong to the slug that
        was retired mid-window; resetting the counter on them is the bug."""
        mod = _load()
        grade = mod.grade_window(
            _probe(server_errors=4, commits={SHA_A: 19, SHA_B: 5},
                   release_straddle=True,
                   release_reasons=["2 distinct commits answered inside the window"]),
            SENTRY_CLEAN, counts_as_day=True, release=STRADDLED)
        assert grade["verdict"] == "INCONCLUSIVE"
        assert grade["counts_toward_seven"] is False
        assert "ruling 130" in grade["reasons"][0]

    def test_a_straddling_window_with_no_errors_does_not_bank(self):
        """Direction 2, the false bank. Clean is not enough if it is clean about
        two systems."""
        mod = _load()
        grade = mod.grade_window(
            _probe(release_straddle=True, release_reasons=["a release landed mid-window"]),
            SENTRY_CLEAN, counts_as_day=True, release=STRADDLED)
        assert grade["verdict"] == "INCONCLUSIVE"
        assert grade["counts_toward_seven"] is False

    def test_arm_a_straddle_does_NOT_suppress_arm_b_5xx(self):
        """The line this ruling must not cross.

        The probe ran end to end on one slug, so its 500s are attributable to
        that slug. Yesterday's deploy sitting in arm A's 24h lookback says
        nothing about them. A blanket pre-check would grade this INCONCLUSIVE
        and convert a real refutation into a shrug.
        """
        mod = _load()
        grade = mod.grade_window(
            _probe(server_errors=7), SENTRY_CLEAN, counts_as_day=True, release=STRADDLED)
        assert grade["verdict"] == "FAILED"
        assert "7 5xx" in grade["reasons"][0]

    def test_arm_a_straddle_DOES_suppress_a_sentry_failure(self):
        """The mirror: the 24h count is the thing that spans the deploy, so a
        non-zero count inside it cannot be attributed to the current slug."""
        mod = _load()
        grade = mod.grade_window(
            _probe(), SENTRY_FIRED, counts_as_day=True, release=STRADDLED)
        assert grade["verdict"] == "INCONCLUSIVE"
        assert "arm A's 24h lookback is STRADDLED" in grade["reasons"][0]

    def test_unknown_arm_a_coverage_is_inconclusive(self):
        mod = _load()
        grade = mod.grade_window(
            _probe(), SENTRY_CLEAN, counts_as_day=True, release=UNKNOWN_COVERAGE)
        assert grade["verdict"] == "INCONCLUSIVE"
        assert grade["counts_toward_seven"] is False

    def test_no_samples_still_outranks_everything(self):
        """A window that collected nothing is not a straddle finding, it is not
        a measurement at all (docstring point 1, gotcha #53)."""
        mod = _load()
        grade = mod.grade_window(
            _probe(samples=0, release_straddle=True, release_reasons=["x"]),
            SENTRY_CLEAN, counts_as_day=True, release=STRADDLED)
        assert grade["verdict"] == "NO_SAMPLES"

    def test_a_deploy_free_clean_window_still_banks(self):
        """The whole point. Ruling 130 must not become the next predicate that
        is true on every window."""
        mod = _load()
        grade = mod.grade_window(_probe(), SENTRY_CLEAN, counts_as_day=True, release=CLEAR)
        assert grade["verdict"] == "CLEAN", grade["reasons"]
        assert grade["counts_toward_seven"] is True

    def test_release_is_a_required_argument(self):
        """A default would let a caller skip the check and still get CLEAN."""
        import inspect
        mod = _load()
        sig = inspect.signature(mod.grade_window)
        assert sig.parameters["release"].default is inspect.Parameter.empty


# --------------------------------------------------------- logged, not dropped


class TestSummarizeReportsStraddles:
    def _write(self, tmp_path: Path, rows: list[dict]) -> Path:
        import json
        state = tmp_path / "watch.jsonl"
        state.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        return state

    def _day(self, date_str: str, *, verdict: str, reasons: list[str]) -> dict:
        return {
            "issue": 2107,
            "label": "day",
            "is_day": True,
            "started_at": f"{date_str}T12:00:00+00:00",
            "probe": {"samples": 60, "server_errors": 0, "process_ids": {"w1": 1},
                      "commits": {SHA_A: 12}},
            "sentry": {"count_24h": 0},
            "grade": {"verdict": verdict, "reasons": reasons},
            "counts_toward_seven": verdict == "CLEAN",
        }

    def test_a_straddled_day_is_named_in_the_summary(self):
        """Ruling 130: logged, not dropped. A streak stuck at 2/7 because deploys
        keep landing and a streak stuck at 2/7 because the fix keeps regressing
        print the same number; only one of them is about the fix."""
        import tempfile
        mod = _load()
        with tempfile.TemporaryDirectory() as td:
            state = self._write(Path(td), [
                self._day("2026-08-22", verdict="CLEAN", reasons=[]),
                self._day("2026-08-23", verdict="CLEAN", reasons=[]),
                self._day("2026-08-24", verdict="INCONCLUSIVE",
                          reasons=["ruling 130: the window straddles a release"]),
            ])
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                mod.summarize(state)
        out = buf.getvalue()
        assert "RELEASE-STRADDLED (ruling 130): 1 day-window(s) on 2026-08-24" in out
        assert "neither banked nor counted against" in out

    def test_a_straddled_day_neither_banks_nor_breaks_the_streak(self):
        """It is a discarded observation, so the streak simply does not reach
        past it — 2 clean dates before it, and it contributes nothing itself.
        Critically it is not recorded as a FAILED date either."""
        import contextlib
        import io
        import tempfile
        mod = _load()
        with tempfile.TemporaryDirectory() as td:
            state = self._write(Path(td), [
                self._day("2026-08-22", verdict="CLEAN", reasons=[]),
                self._day("2026-08-23", verdict="CLEAN", reasons=[]),
                self._day("2026-08-24", verdict="INCONCLUSIVE",
                          reasons=["ruling 130: the window straddles a release"]),
            ])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                mod.summarize(state)
        out = buf.getvalue()
        assert "clean UTC dates: ['2026-08-22', '2026-08-23']" in out
        assert "consecutive clean days: 0/7" in out


def test_a_malformed_state_line_is_skipped_loudly_not_silently():
    """`_read_rows` is now shared by the grader and the summary, so a corrupt
    line would otherwise be able to change a verdict without saying so."""
    import contextlib
    import io
    import tempfile
    mod = _load()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "watch.jsonl"
        state.write_text('{"started_at": "2026-08-24T12:00:00+00:00"}\nNOT JSON\n')
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rows = mod._read_rows(state)
    assert len(rows) == 1
    assert "is not JSON — skipped, not counted" in buf.getvalue()
