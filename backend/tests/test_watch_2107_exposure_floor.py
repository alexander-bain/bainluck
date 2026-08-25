"""Ruling 135: arm A narrows to the live slug, ABOVE a minimum-exposure floor.

WHY THIS FILE EXISTS.

Ruling 130 made a release-straddled window INCONCLUSIVE. That was right about
attribution and wrong about arithmetic: LAT-P087 then measured the rule against
production and found it **unschedulable**. Across 96 deploys in the twelve days
2026-08-12..08-24 (median gap 0.67 h, p90 11.0 h), exactly 2 of 12 UTC dates
could host a deploy-free 24 h and the longest consecutive run was 2 — against a
seven-day requirement. The falsifier could not be run, ever, and an unrunnable
falsifier grades INCONCLUSIVE forever, which reads to every future reader as
"not yet proven" rather than "broken". That is the `_detect_restart` failure
again, with a new name.

Alex ruled Option B on 2026-08-24: scope arm A's count to the live slug rather
than disqualify the day, above a **minimum-exposure floor**. Both halves are
load-bearing and this file exists because each half fails silently on its own:

* **narrowing without a floor** banks a day on forty minutes of silence;
* **the floor without narrowing** is the flat-24h rule, i.e. ruling 130, i.e.
  unschedulable.

So the tests come in matched pairs — the shape that must now PASS next to the
shape that must still FAIL — because a one-directional test suite is how a
relaxation quietly becomes a hole. `TestTheFloorIsStillRunnable` is the
load-bearing one in the other direction: it asserts the floor is clearable on
the deploy cadence actually measured, which is the property ruling 130 lacked.

The floor's second half is a SERVED-REQUESTS floor. Six deploy-free hours during
which nothing was asked of `/api/feed` is six hours of nothing observed; a bug
that never had a chance to fire did not fail to fire. Production exposes no
readable per-interval count of real user feed requests (`user_seen_markets` is
empty — 0 rows, ever; `pg_stat_statements` holds only ingestion writes for
`futures_markets`), so the floor is stated over the probe's own served requests,
which is the one count this instrument can vouch for.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "watch_2107_feed_500s.py"

SHA_A = "ad99166ec1d24f8b0a5c"
SHA_B = "b5c2a750993e1146aa07"

NOW = datetime(2026, 8, 24, 18, 0, tzinfo=timezone.utc)


def _load():
    spec = importlib.util.spec_from_file_location("watch_2107_floor", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _row(started: datetime, commits: dict) -> dict:
    return {"started_at": started.isoformat(), "probe": {"commits": commits}}


def _probe(**over) -> dict:
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


def _narrowed(hours: float = 8.0) -> dict:
    return {
        "verdict": "NARROWED",
        "reason": "scoped to the live slug",
        "source": "operator",
        "narrow_since": (NOW - timedelta(hours=hours)).isoformat(),
        "exposure_hours": hours,
    }


CLEAR = {"verdict": "CLEAR", "reason": "one commit", "narrow_since": None,
         "exposure_hours": None}
SENTRY_CLEAN = {"verdict": "CLEAN", "count_24h": 0, "count_scored": 0,
                "narrowed": True, "reason": None}


# ------------------------------------------------ the floor exists and is 6 h


class TestRuling135MinimumExposureFloor:
    def test_below_the_floor_does_not_narrow(self):
        """40 minutes of silence after a deploy is evidence about 40 minutes."""
        mod = _load()
        out = mod.arm_a_release_window(
            [], NOW, {SHA_A: 24}, last_release_at=NOW - timedelta(minutes=40))
        assert out["verdict"] == "STRADDLED"
        assert "minimum-exposure floor" in out["reason"]

    def test_above_the_floor_narrows(self):
        mod = _load()
        out = mod.arm_a_release_window(
            [], NOW, {SHA_A: 24}, last_release_at=NOW - timedelta(hours=9))
        assert out["verdict"] == "NARROWED"
        assert out["exposure_hours"] == 9.0
        assert out["narrow_since"] == (NOW - timedelta(hours=9)).isoformat()

    @pytest.mark.parametrize("minutes,expected", [
        (359, "STRADDLED"),   # 5 h 59 m
        (360, "NARROWED"),    # exactly 6 h — the floor is inclusive
        (361, "NARROWED"),
    ])
    def test_the_floor_boundary_is_exact(self, minutes, expected):
        """A floor stated to a tenth of an hour but implemented with a fudge is
        a different floor, and nobody would find out which one."""
        mod = _load()
        out = mod.arm_a_release_window(
            [], NOW, {}, last_release_at=NOW - timedelta(minutes=minutes))
        assert out["verdict"] == expected

    def test_the_floor_is_six_hours_and_that_number_is_derived(self):
        """6.0 is not a taste. It is the most conservative floor that still
        admits a seven-day streak on the measured deploy cadence (12 h admits a
        run of 4, and 24 h a run of 2). Pinning the constant makes a later
        'tighten it a bit' edit visible as a test change rather than an
        unschedulable falsifier discovered a fortnight later."""
        mod = _load()
        assert mod.MIN_POST_RELEASE_EXPOSURE_HOURS == 6.0

    def test_a_floor_that_cannot_be_cleared_is_the_bug_being_fixed(self):
        """The other direction, and the reason ruling 130 needed amending: with
        the deploy cadence production actually has, the floor must be clearable.
        A 7 h old release on a 24 h lookback is the ordinary case, and it must
        reach a verdict that can bank."""
        mod = _load()
        out = mod.arm_a_release_window(
            [], NOW, {SHA_A: 24}, last_release_at=NOW - timedelta(hours=7))
        assert out["verdict"] == "NARROWED"
        grade = _load().grade_window(
            _probe(), SENTRY_CLEAN, counts_as_day=True, release=out)
        assert grade["verdict"] == "CLEAN"
        assert grade["counts_toward_seven"] is True


class TestNarrowingFromHistoryAlone:
    """No `--last-release-at`. The recorded windows still BOUND the takeover."""

    def test_history_can_narrow_when_the_slug_has_been_observed_long_enough(self):
        mod = _load()
        rows = [
            _row(NOW - timedelta(hours=30), {SHA_A: 20}),
            _row(NOW - timedelta(hours=20), {SHA_A: 20}),
            _row(NOW - timedelta(hours=11), {SHA_B: 20}),
            _row(NOW - timedelta(hours=3), {SHA_B: 20}),
        ]
        out = mod.arm_a_release_window(rows, NOW, {SHA_B: 24})
        assert out["verdict"] == "NARROWED"
        assert out["exposure_hours"] == 11.0
        assert out["source"] == "history"

    def test_the_bound_is_the_oldest_observation_not_the_newest(self):
        """Taking the newest agreeing row would credit 3 h instead of 11 h and
        fail a day that qualified — the harmless direction, but it would make
        the instrument look broken rather than the schedule look tight."""
        mod = _load()
        rows = [
            _row(NOW - timedelta(hours=30), {SHA_A: 20}),
            _row(NOW - timedelta(hours=11), {SHA_B: 20}),
            _row(NOW - timedelta(hours=3), {SHA_B: 20}),
        ]
        assert mod.arm_a_release_window(rows, NOW, {SHA_B: 24})["exposure_hours"] == 11.0

    def test_an_observation_gap_is_not_filled_in(self):
        """Conservative on purpose. The slug may well have been live for 20 h,
        but only 5 h of it was OBSERVED, so only 5 h is credited — and 5 h is
        under the floor. Under-crediting costs a re-run tomorrow;
        over-crediting banks a day nobody watched."""
        mod = _load()
        rows = [
            _row(NOW - timedelta(hours=30), {SHA_A: 20}),
            _row(NOW - timedelta(hours=5), {SHA_B: 20}),
        ]
        out = mod.arm_a_release_window(rows, NOW, {SHA_B: 24})
        assert out["verdict"] == "STRADDLED"
        assert out["exposure_hours"] == 5.0
        assert "--last-release-at" in out["reason"]

    def test_a_multi_slug_window_has_no_slug_to_narrow_to(self):
        """Arm B already disqualifies this window; arm A must not invent a
        current slug for it by picking one of the two."""
        mod = _load()
        rows = [_row(NOW - timedelta(hours=30), {SHA_A: 20})]
        out = mod.arm_a_release_window(rows, NOW, {SHA_A: 12, SHA_B: 12})
        assert out["verdict"] == "STRADDLED"
        assert out["narrow_since"] is None
        assert "no single live slug" in out["reason"]

    def test_a_deploy_free_lookback_is_still_plain_CLEAR(self):
        """Ruling 135 must not become a predicate that is true on every window.
        With no deploy in the lookback there is nothing to narrow, and the count
        stays the full 24 h."""
        mod = _load()
        rows = [_row(NOW - timedelta(hours=h), {SHA_A: 20}) for h in (48, 26, 12, 3)]
        out = mod.arm_a_release_window(rows, NOW, {SHA_A: 24})
        assert out["verdict"] == "CLEAR"
        assert out["narrow_since"] is None
        assert out["exposure_hours"] is None


# ------------------------------------------------- the count is actually scoped


class TestTheCountIsScopedToTheLiveSlug:
    """Narrowing that does not reach the arithmetic is prose."""

    @staticmethod
    def _buckets(counts: list[int], end: datetime) -> list:
        """24 hourly `[epoch, count]` points ending at `end`."""
        return [
            [int((end - timedelta(hours=len(counts) - i)).timestamp()), c]
            for i, c in enumerate(counts)
        ]

    def test_events_before_the_narrowing_are_dropped(self):
        mod = _load()
        counts = [0] * 24
        counts[2] = 9          # ~22 h ago, on the retired slug
        buckets = self._buckets(counts, NOW)
        total, scored, narrowed = mod.sum_buckets_since(
            buckets, NOW - timedelta(hours=6))
        assert total == 9
        assert scored == 0
        assert narrowed is True

    def test_events_after_the_narrowing_are_kept(self):
        mod = _load()
        counts = [0] * 24
        counts[21] = 4         # ~3 h ago, on the live slug
        total, scored, _ = mod.sum_buckets_since(
            self._buckets(counts, NOW), NOW - timedelta(hours=6))
        assert (total, scored) == (4, 4)

    def test_the_bucket_the_deploy_landed_in_is_KEPT(self):
        """Rounding a partial bucket INTO the count can only turn a would-be
        CLEAN into a FIRED, never the reverse. A false FAILED gets investigated;
        a false CLEAN closes the issue."""
        mod = _load()
        counts = [0] * 24
        counts[17] = 2
        buckets = self._buckets(counts, NOW)
        # narrow to 30 minutes AFTER that bucket opened
        landed = datetime.fromtimestamp(buckets[17][0], tz=timezone.utc)
        _total, scored, _ = mod.sum_buckets_since(buckets, landed + timedelta(minutes=30))
        assert scored == 2

    def test_no_narrowing_asked_means_no_narrowing_claimed(self):
        mod = _load()
        buckets = self._buckets([1] * 24, NOW)
        total, scored, narrowed = mod.sum_buckets_since(buckets, None)
        assert (total, scored, narrowed) == (24, 24, False)

    def test_a_narrowing_that_covers_everything_reports_narrowed_false(self):
        """`narrowed` must mean 'a bucket was actually dropped', because the
        grader uses it to decide whether a non-zero count is attributable. A
        cutoff older than the whole series drops nothing, and saying otherwise
        would let two slugs' events be scored against one."""
        mod = _load()
        buckets = self._buckets([0] * 23 + [3], NOW)
        total, scored, narrowed = mod.sum_buckets_since(
            buckets, NOW - timedelta(hours=48))
        assert (total, scored, narrowed) == (3, 3, False)

    def test_an_empty_bucket_list_does_not_crash_or_claim_a_scope(self):
        mod = _load()
        assert mod.sum_buckets_since([], NOW - timedelta(hours=6)) == (0, 0, False)


# ------------------------------------------------------------ the cascade


class TestNarrowedGradesThroughToAVerdict:
    def test_a_narrowed_clean_window_banks(self):
        """The whole point of Option B: this day is bankable, where under
        ruling 130 alone it was INCONCLUSIVE and the streak never started."""
        mod = _load()
        grade = mod.grade_window(
            _probe(), SENTRY_CLEAN, counts_as_day=True, release=_narrowed(8.0))
        assert grade["verdict"] == "CLEAN", grade["reasons"]
        assert grade["counts_toward_seven"] is True
        assert grade["exposure_hours"] == 8.0

    def test_a_narrowed_non_zero_count_is_FAILED_not_inconclusive(self):
        """The sharpening half. Once the count is attributable to the live slug,
        a non-zero one refutes the fix — that is what narrowing bought."""
        mod = _load()
        sentry = {"verdict": "FIRED", "count_24h": 40, "count_scored": 6,
                  "narrowed": True, "reason": "6 events since the release"}
        grade = mod.grade_window(_probe(), sentry, counts_as_day=True,
                                 release=_narrowed(8.0))
        assert grade["verdict"] == "FAILED"
        assert "6 events" in grade["reasons"][0]

    def test_a_narrowed_verdict_whose_count_was_NOT_narrowed_is_refused(self):
        """Fail-closed. The verdict claims a scope the count does not have, so
        those events may belong to the retired slug — INCONCLUSIVE, never
        FAILED, and certainly never CLEAN."""
        mod = _load()
        sentry = {"verdict": "FIRED", "count_24h": 40, "count_scored": 40,
                  "narrowed": False, "reason": "40 events in 24h"}
        grade = mod.grade_window(_probe(), sentry, counts_as_day=True,
                                 release=_narrowed(8.0))
        assert grade["verdict"] == "INCONCLUSIVE"
        assert "not attributable to the live slug" in grade["reasons"][0]

    def test_a_narrowed_verdict_with_no_exposure_number_is_refused(self):
        """NARROWED is a claim about how much exposure it narrowed TO. Without
        the number the claim cannot be checked against the floor, and an
        uncheckable claim must not be able to produce a CLEAN."""
        mod = _load()
        release = {"verdict": "NARROWED", "reason": "scoped", "source": "operator",
                   "narrow_since": (NOW - timedelta(hours=8)).isoformat(),
                   "exposure_hours": None}
        grade = mod.grade_window(_probe(), SENTRY_CLEAN, counts_as_day=True,
                                 release=release)
        assert grade["verdict"] == "INCONCLUSIVE"
        assert "no exposure_hours" in grade["reasons"][0]

    def test_narrowing_does_NOT_suppress_arm_b_5xx(self):
        """Unchanged by ruling 135, and worth re-pinning here: 500s observed on
        a single-slug window are that slug's, whatever arm A is scoped to."""
        mod = _load()
        grade = mod.grade_window(_probe(server_errors=3), SENTRY_CLEAN,
                                 counts_as_day=True, release=_narrowed(8.0))
        assert grade["verdict"] == "FAILED"
        assert "3 5xx" in grade["reasons"][0]


class TestServedRequestsFloor:
    def test_a_window_that_served_almost_nothing_cannot_bank(self):
        """A bug that never had a chance to fire did not fail to fire."""
        mod = _load()
        grade = mod.grade_window(
            _probe(samples=60, transport_errors=48), SENTRY_CLEAN,
            counts_as_day=True, release=CLEAR)
        assert grade["verdict"] == "INCONCLUSIVE"
        assert "exposure floor" in grade["reasons"][0]
        assert grade["served_requests"] == 12
        assert grade["counts_toward_seven"] is False

    def test_a_full_window_clears_the_floor(self):
        mod = _load()
        grade = mod.grade_window(_probe(), SENTRY_CLEAN, counts_as_day=True,
                                 release=CLEAR)
        assert grade["verdict"] == "CLEAN"
        assert grade["served_requests"] == 60

    @pytest.mark.parametrize("samples,expected", [
        (50, "CLEAN"),          # the floor is inclusive
        (49, "INCONCLUSIVE"),
    ])
    def test_the_served_floor_boundary_is_exact(self, samples, expected):
        mod = _load()
        grade = mod.grade_window(
            _probe(samples=samples), SENTRY_CLEAN, counts_as_day=True, release=CLEAR)
        assert grade["verdict"] == expected

    def test_the_gap_the_floor_actually_closes_is_a_SHORT_WINDOW(self):
        """Worth stating plainly, because the floor's bite is not where it looks.

        The cascade already grades `transport_errors > 0` as INCONCLUSIVE, so any
        window with served < samples was already disqualified — which means the
        served floor binds, in practice, on windows that never ATTEMPTED enough:
        `--minutes 5` at `--interval 60` makes five requests, all of them clean,
        and before ruling 135 that banked a day toward the seven. Five minutes of
        silence closing a P1 is the hole; this is the assertion that it is shut.
        """
        mod = _load()
        grade = mod.grade_window(
            _probe(samples=5), SENTRY_CLEAN, counts_as_day=True, release=CLEAR)
        assert grade["verdict"] == "INCONCLUSIVE"
        assert grade["counts_toward_seven"] is False
        assert "did not exercise" in grade["reasons"][0]

    def test_a_partly_transport_broken_window_is_named_by_the_right_cause(self):
        """Both rules fire on this window; the cascade decides which one speaks.
        The floor sits FIRST so the row says 'not enough was served' rather than
        'some requests failed to connect' — two different repairs (run longer vs
        investigate the network), and a row that names the wrong one sends the
        next reader to the wrong place."""
        mod = _load()
        grade = mod.grade_window(
            _probe(samples=60, transport_errors=48), SENTRY_CLEAN,
            counts_as_day=True, release=CLEAR)
        assert grade["verdict"] == "INCONCLUSIVE"
        assert "exposure floor" in grade["reasons"][0]
        assert not any("transport errors" in r for r in grade["reasons"])

    def test_the_served_floor_does_NOT_suppress_a_real_5xx(self):
        """Ordering, and the reason the floor sits AFTER the 5xx check. A window
        that served eight requests and got three 500s has refuted the fix; a
        volume criterion that swallowed that would be a hole, not a floor."""
        mod = _load()
        grade = mod.grade_window(
            _probe(samples=60, transport_errors=52, server_errors=3), SENTRY_CLEAN,
            counts_as_day=True, release=CLEAR)
        assert grade["verdict"] == "FAILED"

    def test_the_served_floor_is_a_pinned_constant(self):
        mod = _load()
        assert mod.MIN_SERVED_REQUESTS == 50
        # A 60-minute window at --interval 60 makes 60 requests, so the floor has
        # to leave room for a few transport blips or it is a coin flip, not a
        # criterion. Ten is that room; a floor of 60 would be unclearable.
        assert mod.MIN_SERVED_REQUESTS < 60


class TestBothFloorsFailClosed:
    """Absent data grades INCONCLUSIVE. Never CLEAN."""

    def test_a_missing_release_verdict_still_cannot_produce_a_clean(self):
        mod = _load()
        grade = mod.grade_window(_probe(), SENTRY_CLEAN, counts_as_day=True,
                                 release=None)
        assert grade["verdict"] == "INCONCLUSIVE"

    def test_an_unreadable_sentry_arm_still_cannot_produce_a_clean(self):
        mod = _load()
        sentry = {"verdict": "UNKNOWN", "reason": "SENTRY_AUTH_TOKEN not set",
                  "count_24h": None, "count_scored": None, "narrowed": False}
        grade = mod.grade_window(_probe(), sentry, counts_as_day=True,
                                 release=_narrowed(8.0))
        assert grade["verdict"] == "INCONCLUSIVE"

    def test_the_grade_records_both_floors_it_was_judged_against(self):
        """So a row recorded today can be re-read after the constants move,
        instead of being silently re-interpreted under the new ones."""
        mod = _load()
        grade = mod.grade_window(_probe(), SENTRY_CLEAN, counts_as_day=True,
                                 release=_narrowed(8.0))
        assert grade["served_floor"] == mod.MIN_SERVED_REQUESTS
        assert grade["exposure_floor_hours"] == mod.MIN_POST_RELEASE_EXPOSURE_HOURS


def test_the_narrowing_is_wired_into_main_not_just_available():
    """The failure this program keeps meeting: a correct function nothing calls.

    `main` must resolve the release verdict BEFORE reading Sentry — the verdict
    decides what interval the count covers — and must pass `narrow_since` in.
    Asserted on the source because the alternative is an end-to-end run against
    production Sentry, which is not a unit test.
    """
    source = _SCRIPT.read_text()
    main_body = source.split("def main()", 1)[1]
    release_at = main_body.index("release = arm_a_release_window")
    sentry_at = main_body.index("sentry = sentry_24h_count")
    assert release_at < sentry_at, "the count is read before its interval is known"
    assert "since=_parse_stamp(release.get(\"narrow_since\"))" in main_body
    assert "window_started=started" in main_body
