"""Ruling 136: the falsifier tests a CODE CHANGE, not a slug.

WHY THIS FILE EXISTS, AND WHY IT REPLACES TWO OTHERS.

#2107's closure gate has banked ZERO days since it was written, across three
successive attempts to make it strict:

* `_detect_restart` was `len(processes) > 1` — unconditionally true for eight
  days, because production runs one web dyno with `WEB_CONCURRENCY=2`;
* ruling 130 disqualified any window containing a deploy — 2 of 12 UTC dates
  could host one, longest consecutive run 2, against a requirement of 7;
* ruling 135 narrowed arm A to the live slug above a 6 h exposure floor — still
  ~41 % per attempt, and in practice far worse, because without
  `--last-release-at` the 6 h bound came from walking recorded windows back
  until the SHA changed, and at one window per day against 0.34 releases/hour
  consecutive windows essentially never share a SHA.

Every one of those failed in the SAME DIRECTION: the gate graded INCONCLUSIVE,
which reads to a later reader as "not yet proven" rather than "broken", so
nobody went looking. Three days of grading were lost to the third one, and
underneath it sat two defects that could never have surfaced because every
window was already disqualified before they were reached — `SENTRY_ORG`
defaulting to a 404ing org, and the only recorded window carrying
`is_day: false`.

So this suite is written in matched pairs, and the pairs run in both directions
on purpose. A relaxation tested only for what it now ALLOWS becomes a hole; a
strictness tested only for what it REFUSES becomes the unrunnable gate again.
`TestTheCriterionIsRunnable` is the load-bearing one, and it is the assertion
none of the three retired predicates could have passed.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "watch_2107_feed_500s.py"

SHA_A = "ad99166ec1d24f8b0a5c"
SHA_B = "b5c2a750993e1146aa07"

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
DEPLOY = datetime(2026, 8, 27, 11, 30, tzinfo=timezone.utc)


def _load():
    spec = importlib.util.spec_from_file_location("watch_2107_blast", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()


# ------------------------------------------------------------------- builders


def _probe(**over) -> dict:
    """A healthy 90-minute window: 90 samples, one slug, two stable workers."""
    start = NOW - timedelta(minutes=90)
    base = {
        "samples": 90,
        "sample_times": [(start + timedelta(minutes=i)).isoformat() for i in range(90)],
        "server_errors": 0,
        "transport_errors": 0,
        "failures": [],
        "process_ids": {"w1": 45, "w2": 45},
        "commits": {SHA_A: 90},
        "restarted": False,
        "restart_reasons": [],
        "release_straddle": False,
        "release_reasons": [],
    }
    base.update(over)
    return base


def _sentry(verdict="CLEAN", **over) -> dict:
    base = {"verdict": verdict, "reason": "0 events in the 24h lookback",
            "count_24h": 0, "count_scored": 0, "excluded_by_blast": 0,
            "source": "events-endpoint"}
    base.update(over)
    return base


def _ancestry(verdict="CONTAINS", **over) -> dict:
    base = {"verdict": verdict, "reason": "all 1 observed slug(s) contain the fix",
            "commits": [SHA_A], "missing": [], "unresolved": []}
    base.update(over)
    return base


def _boundary(at=DEPLOY, source="explicit", uncertain_from=None) -> dict:
    return {"at": at.isoformat(), "source": source,
            "uncertain_from": (uncertain_from or at).isoformat()}


def _grade(probe=None, sentry=None, ancestry=None, boundaries=None,
           counts_as_day=True, source="test"):
    probe = probe if probe is not None else _probe()
    boundaries = boundaries if boundaries is not None else []
    bands = mod.blast_bands(boundaries)
    errors = mod.attribute_errors(probe.get("failures") or [], bands)
    return mod.grade_window(
        probe,
        sentry if sentry is not None else _sentry(),
        counts_as_day=counts_as_day,
        errors=errors,
        ancestry=ancestry if ancestry is not None else _ancestry(),
        boundaries=boundaries,
        boundary_source=source,
    )


def _failure(at: datetime, status=500) -> dict:
    return {"at": at.isoformat(), "status": status, "commit": SHA_A}


# --------------------------------------------------------- clause 1: tolerance


class TestReleasesAreTolerated:
    """The whole point of the amendment. Every test here was INCONCLUSIVE before."""

    def test_a_clean_window_containing_a_release_BANKS(self):
        # Ruling 130 graded exactly this INCONCLUSIVE, which is what made the
        # gate unrunnable at 0.34 releases/hour.
        probe = _probe(commits={SHA_A: 45, SHA_B: 45}, release_straddle=True,
                       release_reasons=["2 distinct commits answered inside the window"])
        grade = _grade(probe=probe, boundaries=[_boundary()],
                       ancestry=_ancestry(commits=[SHA_A, SHA_B]))
        assert grade["verdict"] == "CLEAN"
        assert grade["counts_toward_seven"] is True

    def test_a_release_in_the_lookback_does_not_disqualify_arm_a(self):
        # Ruling 135's STRADDLED/NARROWED/exposure-hours machinery is gone; arm
        # A is graded on its own count, blast-excluded, and nothing else.
        grade = _grade(boundaries=[_boundary()])
        assert grade["verdict"] == "CLEAN"

    def test_no_verdict_reason_ever_mentions_a_straddle(self):
        probe = _probe(commits={SHA_A: 45, SHA_B: 45}, release_straddle=True)
        grade = _grade(probe=probe, boundaries=[_boundary()],
                       ancestry=_ancestry(commits=[SHA_A, SHA_B]))
        joined = " ".join(grade["reasons"]).lower()
        assert "straddle" not in joined
        assert "ruling 130" not in joined

    def test_the_grade_names_the_criterion_it_was_taken_under(self):
        # A row recorded under one criterion and read under another is how a
        # re-spec launders old evidence. Every row says which ruler measured it.
        assert _grade()["criterion"] == "ruling-136"


# ------------------------------------------------------ clause 2/3: attribution


class TestTheBlastWindowAttributesErrors:
    def test_an_error_far_from_any_deploy_is_FAILED(self):
        probe = _probe(server_errors=1, failures=[_failure(NOW - timedelta(minutes=60))])
        grade = _grade(probe=probe, boundaries=[_boundary()])
        assert grade["verdict"] == "FAILED"
        assert grade["errors_attributable"] == 1

    def test_an_error_inside_the_blast_window_is_INCONCLUSIVE_not_failed(self):
        probe = _probe(server_errors=1, failures=[_failure(DEPLOY + timedelta(minutes=4))])
        grade = _grade(probe=probe, boundaries=[_boundary()])
        assert grade["verdict"] == "INCONCLUSIVE"
        assert grade["errors_in_blast_window"] == 1

    def test_an_error_inside_the_blast_window_ALSO_cannot_bank(self):
        # The relaxation is about attribution, not about silence. A blast-window
        # error blocks the day exactly as hard as it fails to refute it.
        probe = _probe(server_errors=1, failures=[_failure(DEPLOY + timedelta(minutes=4))])
        grade = _grade(probe=probe, boundaries=[_boundary()])
        assert grade["counts_toward_seven"] is False

    @pytest.mark.parametrize("offset_minutes,expected", [
        (-1, "FAILED"),          # BEFORE the boundary — the old slug's, and attributable
        (0, "INCONCLUSIVE"),     # exactly on it
        (9.9, "INCONCLUSIVE"),
        (10.0, "INCONCLUSIVE"),  # the boundary is inclusive
        (10.1, "FAILED"),
        (30, "FAILED"),
    ])
    def test_the_ten_minute_boundary_is_exact(self, offset_minutes, expected):
        probe = _probe(server_errors=1,
                       failures=[_failure(DEPLOY + timedelta(minutes=offset_minutes))])
        assert _grade(probe=probe, boundaries=[_boundary()])["verdict"] == expected

    def test_an_error_with_no_boundary_known_at_all_is_FAILED(self):
        # Docstring point 4: an unknown boundary must not buy an exclusion. Fewer
        # known boundaries -> more FAILED, which is the recoverable direction.
        probe = _probe(server_errors=1, failures=[_failure(DEPLOY + timedelta(minutes=2))])
        assert _grade(probe=probe, boundaries=[])["verdict"] == "FAILED"

    def test_a_transport_error_is_NOT_counted_as_a_5xx(self):
        # `failures` carries status None for a refused connection. Clauses 2 and
        # 3 are about 500s, and a request that got no answer at all is not
        # evidence of one — it could be the prober's own network. It keeps the
        # transport branch (INCONCLUSIVE) and must never read as a refutation.
        probe = _probe(transport_errors=1,
                       failures=[_failure(NOW - timedelta(minutes=60), status=None)])
        grade = _grade(probe=probe, boundaries=[_boundary()])
        assert grade["errors_attributable"] == 0
        assert grade["verdict"] == "INCONCLUSIVE"
        assert "transport" in " ".join(grade["reasons"])

    def test_errors_the_fifty_row_cap_hid_are_charged_as_attributable(self):
        # `run_probe` records at most 50 failures but counts all of them. An
        # error the cap hid is not thereby inside a blast window, so the
        # remainder must land on the FAILED side — otherwise a flood of >50
        # errors that happened to start near a deploy would grade INCONCLUSIVE.
        probe = _probe(
            server_errors=60,
            failures=[_failure(DEPLOY + timedelta(minutes=m % 10)) for m in range(50)])
        grade = _grade(probe=probe, boundaries=[_boundary()])
        assert grade["errors_in_blast_window"] == 50
        assert grade["errors_attributable"] == 10
        assert grade["verdict"] == "FAILED"

    def test_the_cap_correction_does_not_invent_errors_in_a_clean_window(self):
        grade = _grade(boundaries=[_boundary()])
        assert grade["errors_attributable"] == 0
        assert grade["verdict"] == "CLEAN"

    def test_multiple_boundaries_each_carry_their_own_band(self):
        second = DEPLOY - timedelta(minutes=40)
        probe = _probe(server_errors=2, failures=[
            _failure(DEPLOY + timedelta(minutes=3)),
            _failure(second + timedelta(minutes=3)),
        ])
        grade = _grade(probe=probe,
                       boundaries=[_boundary(), _boundary(at=second)])
        assert grade["errors_in_blast_window"] == 2
        assert grade["errors_attributable"] == 0


class TestObservedBoundariesCarryTheirUncertainty:
    def test_a_commit_transition_becomes_a_boundary(self):
        t0 = NOW - timedelta(minutes=10)
        t1 = NOW - timedelta(minutes=9)
        timeline = [{"at": t0.isoformat(), "commit": SHA_A},
                    {"at": t1.isoformat(), "commit": SHA_B}]
        bounds = mod.deploy_boundaries(timeline, [])
        assert len(bounds) == 1
        assert bounds[0]["source"] == "observed"
        assert bounds[0]["from_commit"] == SHA_A[:12]

    def test_the_band_starts_at_the_LAST_sample_on_the_old_slug(self):
        # The deploy happened somewhere between the two samples, so the band is
        # measured from the earlier one. Anything else attributes a cutover error
        # to the code on the strength of a sampling artefact.
        t0 = NOW - timedelta(minutes=10)
        t1 = NOW - timedelta(minutes=9)
        bounds = mod.deploy_boundaries(
            [{"at": t0.isoformat(), "commit": SHA_A},
             {"at": t1.isoformat(), "commit": SHA_B}], [])
        bands = mod.blast_bands(bounds)
        assert mod.in_blast(t0 + timedelta(seconds=30), bands)

    def test_a_steady_slug_produces_no_boundary(self):
        timeline = [{"at": (NOW - timedelta(minutes=i)).isoformat(), "commit": SHA_A}
                    for i in range(10, 0, -1)]
        assert mod.deploy_boundaries(timeline, []) == []

    def test_a_missing_commit_field_is_not_a_transition(self):
        # `/api/health` that fails to answer reports commit None. "The instrument
        # could not see it" is not "the value changed" (gotcha #53).
        timeline = [{"at": (NOW - timedelta(minutes=3)).isoformat(), "commit": SHA_A},
                    {"at": (NOW - timedelta(minutes=2)).isoformat(), "commit": None},
                    {"at": (NOW - timedelta(minutes=1)).isoformat(), "commit": SHA_A}]
        assert mod.deploy_boundaries(timeline, []) == []

    def test_explicit_and_observed_boundaries_coexist(self):
        t0, t1 = NOW - timedelta(minutes=10), NOW - timedelta(minutes=9)
        bounds = mod.deploy_boundaries(
            [{"at": t0.isoformat(), "commit": SHA_A},
             {"at": t1.isoformat(), "commit": SHA_B}], [DEPLOY])
        assert {b["source"] for b in bounds} == {"explicit", "observed"}


# ------------------------------------------------------- clause 4: fix ancestry


class TestEverySlugMustCarryTheFix:
    """The check that makes tolerating releases sound rather than merely convenient."""

    def test_a_rollback_to_a_pre_fix_slug_cannot_bank(self):
        # THE hole that clause 1 would otherwise open: a clean window measured on
        # a slug without the fix in it certifies nothing, and it looks identical
        # to a clean window that certifies everything.
        grade = _grade(ancestry=_ancestry("MISSING",
                                          reason=f"{SHA_B[:12]} lacks b2e3e1a9",
                                          missing=[f"{SHA_B[:12]} lacks b2e3e1a9"]))
        assert grade["verdict"] == "INCONCLUSIVE"
        assert grade["counts_toward_seven"] is False
        assert "clause 4" in " ".join(grade["reasons"])

    def test_an_unresolvable_sha_is_inconclusive_not_assumed_fine(self):
        grade = _grade(ancestry=_ancestry("UNRESOLVED", unresolved=[SHA_B],
                                          reason="not in this clone"))
        assert grade["verdict"] == "INCONCLUSIVE"

    def test_skipping_the_check_cannot_produce_a_clean(self):
        # `--fix-commit ''` is allowed, but it buys an INCONCLUSIVE, not a bank.
        # An opt-out that silently weakens the criterion is the criterion.
        grade = _grade(ancestry=_ancestry("UNCHECKED", reason="no --fix-commit supplied"))
        assert grade["verdict"] == "INCONCLUSIVE"

    def test_a_contained_fix_banks(self):
        assert _grade(ancestry=_ancestry("CONTAINS"))["verdict"] == "CLEAN"

    def test_ancestry_does_NOT_suppress_a_real_5xx(self):
        # Ordering: the refutation outranks the ancestry check, because a 500 on
        # a slug we cannot place is still a 500 someone got.
        probe = _probe(server_errors=1, failures=[_failure(NOW - timedelta(minutes=60))])
        grade = _grade(probe=probe, ancestry=_ancestry("UNRESOLVED"))
        assert grade["verdict"] == "FAILED"

    def test_the_real_checker_accepts_the_shipped_fix(self):
        # Not a mock: this runs `git merge-base --is-ancestor` against HEAD, so
        # it fails if the fix commits named in the script are wrong or gone.
        out = mod.check_fix_ancestry({"HEAD": 1}, list(mod.DEFAULT_FIX_COMMITS))
        assert out["verdict"] == "CONTAINS", out["reason"]

    def test_the_real_checker_refuses_a_sha_it_cannot_resolve(self):
        out = mod.check_fix_ancestry({"deadbeefdeadbeef": 1}, list(mod.DEFAULT_FIX_COMMITS))
        assert out["verdict"] == "UNRESOLVED"

    def test_the_real_checker_catches_a_slug_predating_the_fix(self):
        # The fix's own parent is a real pre-fix slug, so this is the rollback
        # case measured against real history rather than a fabricated SHA.
        out = mod.check_fix_ancestry({"b2e3e1a9~1": 1}, ["b2e3e1a9"])
        assert out["verdict"] == "MISSING"


# ------------------------------------------------------ the exposure floor


class TestTheFloorIsCountedInRequests:
    def test_a_gutted_window_cannot_bank(self):
        probe = _probe(samples=10, sample_times=[
            (NOW - timedelta(minutes=i)).isoformat() for i in range(10)])
        grade = _grade(probe=probe)
        assert grade["verdict"] == "INCONCLUSIVE"
        assert "exposure floor" in " ".join(grade["reasons"])

    def test_samples_inside_a_blast_window_do_not_count_toward_the_floor(self):
        # 55 samples, 20 of them inside a band -> 35 clear, under the floor.
        start = DEPLOY - timedelta(minutes=5)
        probe = _probe(samples=55, sample_times=[
            (start + timedelta(minutes=i)).isoformat() for i in range(55)])
        grade = _grade(probe=probe, boundaries=[_boundary()])
        assert grade["verdict"] == "INCONCLUSIVE"
        assert grade["served_outside_blast"] < mod.MIN_SERVED_REQUESTS

    def test_a_ninety_minute_window_with_one_deploy_still_clears(self):
        # The reason DEFAULT_WINDOW_MINUTES is 90 and not 60.
        grade = _grade(boundaries=[_boundary()])
        assert grade["served_outside_blast"] >= mod.MIN_SERVED_REQUESTS
        assert grade["verdict"] == "CLEAN"

    def test_a_sixty_minute_window_with_one_deploy_sits_on_the_floor(self):
        # Pinned as the JUSTIFICATION for the 90-minute default, not as a wish:
        # 60 samples minus an 11-sample band is 49, one short. A criterion that
        # is merely clearable is the ruling-135 mistake in miniature.
        start = DEPLOY - timedelta(minutes=30)
        probe = _probe(samples=60, sample_times=[
            (start + timedelta(minutes=i)).isoformat() for i in range(60)])
        grade = _grade(probe=probe, boundaries=[_boundary()])
        assert grade["served_outside_blast"] < mod.MIN_SERVED_REQUESTS

    def test_the_floor_does_NOT_suppress_a_real_5xx(self):
        # A refutation is a refutation however few requests were made. A volume
        # floor that swallowed one would be a hole, not a floor.
        probe = _probe(samples=5, server_errors=1,
                       sample_times=[(NOW - timedelta(minutes=i)).isoformat()
                                     for i in range(5)],
                       failures=[_failure(NOW - timedelta(minutes=60))])
        assert _grade(probe=probe)["verdict"] == "FAILED"

    def test_the_floor_is_stated_in_requests_not_hours(self):
        grade = _grade()
        assert grade["served_floor"] == mod.MIN_SERVED_REQUESTS == 50
        assert "exposure_floor_hours" not in grade

    def test_transport_errors_are_charged_against_the_floor(self):
        probe = _probe(transport_errors=45)
        grade = _grade(probe=probe)
        assert grade["served_outside_blast"] == 45
        assert grade["verdict"] == "INCONCLUSIVE"


# ------------------------------------------------------------------- arm A


class TestArmAExcludesTheBlastWindow:
    def _issue(self, event_times, bucket_total=None):
        return {
            "id": "7677420933",
            "stats": {"24h": [[int((NOW - timedelta(hours=h)).timestamp()),
                               0] for h in range(24, 0, -1)]},
        }, [{"dateCreated": t.isoformat().replace("+00:00", "Z")} for t in event_times]

    def _patched(self, monkeypatch, events, bucket_total):
        issue, raw = self._issue(events)
        if bucket_total:
            issue["stats"]["24h"][-1][1] = bucket_total

        def fake(url, token):
            return [issue] if "/issues/?" in url else raw
        monkeypatch.setattr(mod, "_sentry_get", fake)

    def test_an_event_outside_every_band_fires(self, monkeypatch):
        self._patched(monkeypatch, [NOW - timedelta(hours=3)], 1)
        out = mod.sentry_events_since("tok", mod.blast_bands([_boundary()]), NOW)
        assert out["verdict"] == "FIRED"
        assert out["count_scored"] == 1

    def test_an_event_inside_a_band_is_excluded(self, monkeypatch):
        self._patched(monkeypatch, [DEPLOY + timedelta(minutes=5)], 1)
        out = mod.sentry_events_since("tok", mod.blast_bands([_boundary()]), NOW)
        assert out["verdict"] == "CLEAN"
        assert out["excluded_by_blast"] == 1
        assert "ruling 136" in out["reason"]

    def test_an_excluded_event_is_still_reported(self, monkeypatch):
        # Ruling 130's logged-not-dropped clause survives the amendment.
        self._patched(monkeypatch, [DEPLOY + timedelta(minutes=5)], 1)
        out = mod.sentry_events_since("tok", mod.blast_bands([_boundary()]), NOW)
        assert out["excluded_by_blast"] == 1
        assert out["count_24h"] == 1

    def test_events_older_than_the_lookback_are_not_counted(self, monkeypatch):
        self._patched(monkeypatch, [NOW - timedelta(hours=30)], 0)
        out = mod.sentry_events_since("tok", [], NOW)
        assert out["verdict"] == "CLEAN"

    def test_a_truncated_event_list_falls_back_to_the_unexcluded_total(self, monkeypatch):
        # The one way this read can lie in the dangerous direction. 100 events
        # back with a bucket total of 250 means 150 are invisible, so no
        # exclusion is applied and the verdict is taken from the total.
        issue = {"id": "1", "stats": {"24h": [[int(NOW.timestamp()), 250]]}}
        raw = [{"dateCreated": (DEPLOY + timedelta(minutes=1)).isoformat()
                .replace("+00:00", "Z")}] * 100
        monkeypatch.setattr(mod, "_sentry_get",
                            lambda url, token: [issue] if "/issues/?" in url else raw)
        out = mod.sentry_events_since("tok", mod.blast_bands([_boundary()]), NOW)
        assert out["verdict"] == "FIRED"
        assert out["source"] == "buckets-fallback"
        assert out["count_scored"] == 250

    def test_a_missing_token_is_UNKNOWN_and_cannot_bank(self, monkeypatch):
        out = mod.sentry_events_since(None, [], NOW)
        assert out["verdict"] == "UNKNOWN"
        assert _grade(sentry=out)["verdict"] == "INCONCLUSIVE"

    def test_an_error_object_from_sentry_is_UNKNOWN_not_CLEAN(self, monkeypatch):
        # The `bain-luck` 404 returned `{"error": ...}`. Reading that as an empty
        # issue list would have graded a permanently-blind arm A as CLEAN.
        monkeypatch.setattr(mod, "_sentry_get",
                            lambda url, token: {"error": "apigateway", "detail": "Not found"})
        out = mod.sentry_events_since("tok", [], NOW)
        assert out["verdict"] == "UNKNOWN"

    def test_the_default_org_is_the_one_that_answers(self, monkeypatch):
        # Measured 2026-08-26: `bain-luck` 404s, `alexander-bain` returns 200.
        # A wrong default here is not a loud failure, it is a permanent
        # INCONCLUSIVE, which is the failure mode this whole ruling is about.
        monkeypatch.delenv("SENTRY_ORG", raising=False)
        fresh = _load()
        assert fresh.SENTRY_ORG == "alexander-bain"


# ---------------------------------------------------------- cascade ordering


class TestTheCascadeOrderIsTheSpecification:
    def test_no_samples_outranks_everything(self):
        probe = _probe(samples=0, sample_times=[])
        assert _grade(probe=probe)["verdict"] == "NO_SAMPLES"

    def test_an_attributable_5xx_outranks_the_floor_the_ancestry_and_arm_a(self):
        probe = _probe(samples=3, server_errors=1,
                       sample_times=[(NOW - timedelta(minutes=i)).isoformat()
                                     for i in range(3)],
                       failures=[_failure(NOW - timedelta(minutes=60))])
        grade = _grade(probe=probe, sentry=_sentry("UNKNOWN"),
                       ancestry=_ancestry("UNRESOLVED"))
        assert grade["verdict"] == "FAILED"

    def test_a_restart_still_disqualifies(self):
        # The contrast that makes ruling 136 coherent: a RELEASE between two
        # fix-carrying slugs is not a change of the system under test, but a
        # RESTART clears the process-globals this issue is about, so it is.
        probe = _probe(restarted=True, restart_reasons=["w1 uptime reset mid-window"])
        assert _grade(probe=probe)["verdict"] == "INCONCLUSIVE"

    def test_an_unmeasured_coverage_arm_cannot_bank(self):
        assert _grade(probe=_probe(process_ids={}))["verdict"] == "INCONCLUSIVE"

    def test_a_non_day_window_never_banks_however_clean(self):
        grade = _grade(counts_as_day=False)
        assert grade["verdict"] == "CLEAN"
        assert grade["counts_toward_seven"] is False

    def test_the_grade_records_what_it_was_judged_against(self):
        grade = _grade(boundaries=[_boundary()], source="heroku (100 releases)")
        assert grade["blast_window_minutes"] == 10
        assert grade["served_floor"] == 50
        assert grade["deploy_boundaries"] == 1
        assert grade["boundary_source"] == "heroku (100 releases)"
        assert grade["fix_ancestry"] == "CONTAINS"


# --------------------------------------------------------- streak reporting


class TestTheStreakSaysWhyItEnded:
    def _row(self, date, verdict, clean):
        return {"is_day": True, "started_at": f"{date}T12:00:00+00:00",
                "counts_toward_seven": clean, "grade": {"verdict": verdict}}

    def test_a_failed_day_and_an_ungraded_day_are_distinguishable(self):
        # Three days were lost because "streak 0/7" printed the same whether the
        # fix regressed or the instrument could not read.
        failed = mod.streak_from_rows([
            self._row("2026-08-25", "CLEAN", True),
            self._row("2026-08-26", "FAILED", False)])
        vague = mod.streak_from_rows([
            self._row("2026-08-25", "CLEAN", True),
            self._row("2026-08-26", "INCONCLUSIVE", False)])
        assert "FAILED" in failed["stopped_by"]
        assert "INCONCLUSIVE" in vague["stopped_by"]
        assert failed["stopped_by"] != vague["stopped_by"]

    def test_consecutive_clean_dates_count(self):
        rows = [self._row(f"2026-08-2{d}", "CLEAN", True) for d in range(1, 8)]
        assert mod.streak_from_rows(rows)["streak"] == 7

    def test_a_calendar_gap_ends_the_streak_and_says_so(self):
        out = mod.streak_from_rows([
            self._row("2026-08-24", "CLEAN", True),
            self._row("2026-08-26", "CLEAN", True)])
        assert out["streak"] == 1
        assert "calendar gap" in out["stopped_by"]

    def test_the_earliest_closure_date_is_stated(self):
        out = mod.streak_from_rows([
            self._row("2026-08-27", "CLEAN", True),
            self._row("2026-08-28", "CLEAN", True)])
        # 2 banked, 5 to go, so the seventh is 2026-09-02.
        assert out["earliest_closure_date"] == "2026-09-02"

    def test_no_clean_days_means_no_closure_date_is_promised(self):
        out = mod.streak_from_rows([self._row("2026-08-27", "FAILED", False)])
        assert out["earliest_closure_date"] is None
        assert out["streak"] == 0

    def test_a_non_day_row_is_not_a_day(self):
        rows = [{"is_day": False, "started_at": "2026-08-27T12:00:00+00:00",
                 "counts_toward_seven": False, "grade": {"verdict": "FAILED"}}]
        out = mod.streak_from_rows(rows)
        assert out["day_windows"] == 0
        assert out["streak"] == 0


# ------------------------------------------------------- the runnability claim


class TestTheCriterionIsRunnable:
    """The assertion none of the three retired predicates could have passed.

    Ruling 135 shipped with a floor that was clearable in principle and
    unreachable in practice, and the gap between those two was three days of
    zero grading. So runnability is asserted against the deploy cadence actually
    measured, not against a hand-built happy path.
    """

    def _cadence_window(self, deploys_in_window: int, minutes: int = 90):
        """A `minutes`-long window with N evenly-spaced deploys inside it."""
        start = NOW - timedelta(minutes=minutes)
        boundaries = [
            _boundary(at=start + timedelta(minutes=(i + 1) * minutes / (deploys_in_window + 1)))
            for i in range(deploys_in_window)
        ]
        probe = _probe(samples=minutes, sample_times=[
            (start + timedelta(minutes=i)).isoformat() for i in range(minutes)])
        return probe, boundaries

    @pytest.mark.parametrize("deploys", [0, 1, 2, 3])
    def test_the_default_window_banks_at_the_measured_cadence(self, deploys):
        # Deploys per 90-minute window, measured over the same 100 releases by
        # stepping a candidate start every 5 minutes (n=3,532):
        #     0 -> 73.24 %   1 -> 12.77 %   2 -> 8.47 %   3 -> 3.94 %
        # i.e. 98.41 % of windows. All of these must BANK, because a criterion
        # that only banks on a deploy-free day is ruling 130 again.
        probe, boundaries = self._cadence_window(deploys)
        grade = _grade(probe=probe, boundaries=boundaries,
                       ancestry=_ancestry(commits=[SHA_A]))
        assert grade["verdict"] == "CLEAN", grade["reasons"]

    def test_the_cap_this_criterion_does_have_is_named_not_hidden(self):
        # FOUR evenly-spaced deploys in 90 minutes leaves 46 served requests,
        # four short of the floor, so it grades INCONCLUSIVE and the day is
        # re-run. That is 0.99 % of measured windows and in practice fewer,
        # because real 4-deploy windows are CLUSTERED and their bands overlap
        # rather than costing 10 minutes each — the whole-span simulation put
        # 90-minute clearance at 3524/3532 = 99.8 %.
        #
        # Recorded as a test rather than left to be discovered: a criterion with
        # an unstated cap reads as covering everything it does not cover, which
        # is the ruling-135 failure with the numbers moved.
        probe, boundaries = self._cadence_window(4)
        grade = _grade(probe=probe, boundaries=boundaries)
        assert grade["verdict"] == "INCONCLUSIVE"
        assert grade["served_outside_blast"] == 46

    def test_a_window_saturated_with_deploys_does_NOT_bank(self):
        # The other direction. Nine deploys in 90 minutes blasts the whole
        # window, and a window with no unblasted exposure must not certify.
        probe, boundaries = self._cadence_window(9)
        assert _grade(probe=probe, boundaries=boundaries)["verdict"] == "INCONCLUSIVE"

    def test_the_blast_window_is_a_pinned_constant_with_a_derivation(self):
        assert mod.DEPLOY_BLAST_WINDOW_MINUTES == 10
        src = _SCRIPT.read_text()
        # The enrichment table is the derivation. If the constant moves without
        # it, the number became a preference.
        assert "enrichment" in src and "3.12x" in src

    def test_the_default_window_is_a_pinned_constant_with_a_derivation(self):
        assert mod.DEFAULT_WINDOW_MINUTES == 90
        assert "3524/3532" in _SCRIPT.read_text()


# ------------------------------------------------------------ the retirement


class TestRetiredCriteriaStayRetired:
    """Pinned in the file they were removed from, so a revert is a test failure.

    Two prior criteria are gone. Naming them here rather than deleting them
    silently is the same discipline as pinning a rejected lever: the next lane
    to hit a stuck gate will reach for exactly these, because they read as the
    strict option.
    """

    def test_the_six_hour_exposure_floor_is_gone(self):
        # Ruling 135. Unrunnable: ~41 % per attempt, ~868 days expected wait for
        # seven consecutive. A floor in hours measures the deploy cadence.
        assert not hasattr(mod, "MIN_POST_RELEASE_EXPOSURE_HOURS")

    def test_the_arm_a_straddle_verdict_is_gone(self):
        # Ruling 130. 2 of 12 UTC dates could host a deploy-free lookback.
        assert not hasattr(mod, "arm_a_release_window")
        assert not hasattr(mod, "_narrow_since")

    def test_grade_window_no_longer_takes_a_release_verdict(self):
        import inspect
        params = set(inspect.signature(mod.grade_window).parameters)
        assert "release" not in params
        assert {"errors", "ancestry", "boundaries"} <= params

    def test_the_bucket_sum_survives_as_the_fallback_only(self):
        # `sum_buckets_since` is still correct and still used when the event list
        # is truncated; what it cannot do is express a 10-minute band, which is
        # why it stopped being the primary read.
        now_ts = int(NOW.timestamp())
        buckets = [[now_ts - 7200, 3], [now_ts - 3600, 5]]
        # A cutoff 50 minutes back sits INSIDE the newest bucket, so the older
        # one drops. A cutoff 90 minutes back sits inside the OLDER bucket, and
        # that bucket is deliberately KEPT — rounding a partial bucket in can
        # only turn a would-be CLEAN into a FIRED, never the reverse.
        assert mod.sum_buckets_since(buckets, NOW - timedelta(minutes=50)) == (8, 5, True)
        assert mod.sum_buckets_since(buckets, NOW - timedelta(minutes=90)) == (8, 8, False)
