"""#1894 / C-CERT-SENTRY-R3 — the two findings that blocked queue 351's policy.

## What this file is for

R3 blocked the (already merged) Sentry volume policy on two findings. They are
independent defects with one shared shape, and the measured diagnosis in #1894 is
that **neither fix works alone**:

**Finding 1 — the budget was priced above affordance.** The policy priced
184.25 events/day against a quota that affords ~164.5/day. The old model was a
*replay plus hand-added reserves*, compared to a budget in an assertion. An
assertion is not construction: nothing stopped the priced total from exceeding
the budget, and nothing stopped the budget itself from being restated. The fix is
that the per-process emission allowance is **divided out of** the budget
(``app/utils/sentry_budget.py``), so the fleet ceiling is
``allowance x incarnations <= budget`` by arithmetic rather than by review.

**Finding 2 — the filter was phase two of the blindness.** 64,039 discards/day
survive quota restoration, because ``event_signature`` collapsed every event that
carries no exception, no frames, no culprit and no transaction to the single
string ``'unknown|?|?'`` — and ``BACKSTOP_PER_WINDOW = 1`` then destroyed all but
the first of them, per process, per day. Celery Beat cron check-ins are the
instance that was measured (~19k/day, and the SDK bills their loss to the *error*
outcome at ``sentry_sdk/client.py:883``, poisoning the very number the budget is
measured against). The general defect is the collapse, not the cron.

## Why the tests below are written the way they are

Every assertion here is about a PROPERTY that must hold for any input, not about a
number that happened to come out of one census. The census-replay suite in
``test_sentry_filter.py`` prices the sample; this file constrains the policy.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.sentry_filter import (
    BACKSTOP_PER_WINDOW,
    build_before_send,
    classify,
    event_signature,
)


# =============================================================================
# Event builders
# =============================================================================

def check_in_event(slug: str = "poll-live-prediction-markets") -> dict:
    """Exactly the shape ``sentry_sdk/crons/api.py:_create_check_in_event`` emits.

    ``CeleryIntegration(monitor_beat_tasks=True)`` (``app/tasks/__init__.py:617``)
    makes ``sentry_sdk/integrations/celery/beat.py:152`` fire one of these on every
    due-task dispatch, in the beat process. ``sentry_sdk/client.py:872-875`` only
    excludes ``type == "transaction"`` from ``before_send``, so these reach us.
    """
    return {
        "type": "check_in",
        "monitor_slug": slug,
        "check_in_id": uuid.uuid4().hex,
        "status": "in_progress",
        "duration": None,
        "environment": "production",
        "release": "abc123",
    }


def bare_message_event(text: str = "something happened") -> dict:
    """An event with no exception, no frames, no culprit and no transaction.

    The residual class after the cron fix: this is what ``capture_message`` looks
    like once the scope carries no transaction, and it is the next thing that
    would have collapsed into ``'unknown|?|?'``.
    """
    return {"message": text}


# =============================================================================
# Finding 2a — the signature collapse, as a GENERAL property
# =============================================================================

class TestSignatureNeverCollapsesToUnknown:
    """The defect is not "cron check-ins are throttled". It is that an event the
    filter cannot identify gets throttled AS IF it were an identified repeat.

    A signature is a claim that two events are the same thing. ``'unknown|?|?'``
    is not that claim — it is the absence of one — and treating an absence as an
    identity is gotcha #53 at the throttling layer. Measured cost: 19,066 events
    on 2026-08-16 alone.
    """

    def test_a_check_in_is_not_governed_by_the_error_filter(self):
        """A cron check-in is monitoring, not an error, and must pass untouched.

        Two independent reasons, either sufficient: it is not an error, so an
        error-volume policy has no business judging it; and the SDK records its
        loss as ``data_category="error"`` (``client.py:883``, hardcoded), so
        dropping one corrupts the metric the budget is enforced against.
        """
        bs = build_before_send()
        kept = sum(1 for _ in range(500) if bs(check_in_event(), {}) is not None)
        assert kept == 500, (
            "cron check-ins are being eaten by the error filter — this is the "
            "measured 19k/day in #1894, and it also silently kills Sentry Crons"
        )

    def test_distinct_monitors_do_not_share_one_signature(self):
        """``'unknown|?|?'`` for every slug is one bucket for the whole beat."""
        sigs = {
            event_signature(check_in_event(slug), "", {})
            for slug in ("warm-typeahead", "poll-all-odds", "heartbeat")
        }
        assert len(sigs) == 3, f"three monitors collapsed to {sigs}"

    def test_no_event_shape_yields_a_fully_unknown_signature(self):
        """The general form. If every identity field is missing, the signature
        must still say what the event WAS — never the all-unknown string."""
        for event in (check_in_event(), bare_message_event(), {}):
            sig = event_signature(event, "", {})
            assert sig != "unknown|?|?", f"collapsed identity for {event!r}"

    def test_distinct_bare_messages_are_distinct_signatures(self):
        """The next class that would have collapsed after the cron fix."""
        a = event_signature(bare_message_event("disk full"), "", {})
        b = event_signature(bare_message_event("token expired"), "", {})
        assert a != b, "two unrelated messages share one throttle allowance"

    def test_an_unidentifiable_event_is_counted_where_a_human_can_see_it(self):
        """Silent collapse is the defect. If the filter still cannot identify an
        event, that fact must appear in the counters rather than in nothing."""
        bs = build_before_send()
        for _ in range(50):
            bs({}, {})
        assert "unidentified" in bs.counts, (
            "no counter names the events the filter could not identify"
        )


# =============================================================================
# Finding 2b — a DECLARED, OBSERVABLE discard ceiling
# =============================================================================

class TestDiscardCeilingIsDeclaredAndObservable:
    """Alex, 2026-08-17: *"a discard counter nobody can read is the same defect
    one level up."* Pre-fix the counters existed only as a per-process log line
    at ``sentry_filter.py:641`` — readable only by someone who already suspected
    the problem and could reach ``heroku logs``. That is not observability.
    """

    def test_the_ceiling_is_a_named_constant_with_a_number(self):
        from app.utils import sentry_budget

        assert isinstance(sentry_budget.DISCARD_CEILING_PER_DAY, int)
        assert sentry_budget.DISCARD_CEILING_PER_DAY > 0

    def test_the_measured_defect_would_have_breached_it(self):
        """64,039/day (R3) and 19,066/day (the cron instance) must both be over
        the line, or the ceiling is decorative."""
        from app.utils import sentry_budget

        assert 64_039 > sentry_budget.DISCARD_CEILING_PER_DAY
        assert sentry_budget.over_discard_ceiling(64_039, window_s=86_400)
        assert sentry_budget.over_discard_ceiling(19_066, window_s=86_400)

    def test_a_healthy_day_is_under_it(self):
        """Measured accepted volume on a live-quota day was 770-1,269/day."""
        from app.utils import sentry_budget

        assert not sentry_budget.over_discard_ceiling(1_269, window_s=86_400)

    def test_the_ceiling_is_rate_based_not_count_based(self):
        """A count handed over without its window is not a measurement. Half the
        events in half the window is the SAME rate and must read the same."""
        from app.utils import sentry_budget

        ceiling = sentry_budget.DISCARD_CEILING_PER_DAY
        assert sentry_budget.over_discard_ceiling(ceiling + 100, window_s=86_400)
        assert sentry_budget.over_discard_ceiling(
            (ceiling + 100) // 2, window_s=43_200
        ), "a half-day window doubled the effective allowance"

    def test_the_counters_are_exported_for_reading(self):
        """Observable means a reader that is not this process can get the number."""
        from app.utils import sentry_filter

        assert hasattr(sentry_filter, "export_counts")
        assert hasattr(sentry_filter, "filter_discard_census")

    def test_the_automatic_push_never_touches_redis_off_a_dyno(self):
        """The export runs on the exception path (gotcha #39). Off production it
        must not even try — an earlier draft opened a connection per filter
        instance and stalled the census replay suite at 34%."""
        from app.utils import sentry_filter

        assert sentry_filter.EXPORT_ENABLED is False, (
            "EXPORT_ENABLED should be false without $DYNO; a test run must never "
            "pay a Redis round-trip per SentryVolumeFilter"
        )

    def test_a_filter_instance_stays_quiet_for_its_first_minute(self):
        """``_last_log`` starting at 0.0 made the very first event of every
        process fire the summary. Hundreds of instances, hundreds of pushes."""
        from app.utils.sentry_filter import SentryVolumeFilter

        f = SentryVolumeFilter()
        assert f._last_log > 0.0

    def test_a_redis_read_failure_is_not_reported_as_zero_discards(self):
        """gotcha #53 at the observability layer: 'I could not read' and
        'there was nothing' must not share a rendering."""
        from app.utils import sentry_filter

        census = sentry_filter.summarize_filter_counts({})
        assert census["over_ceiling"] is None
        assert census["discarded_per_day"] is None

    def test_the_census_reports_a_verdict_not_just_a_number(self):
        """gotcha #53: a number without its verdict gets read as whatever the
        reader already believed."""
        from app.utils import sentry_filter

        census = sentry_filter.summarize_filter_counts(
            {
                "host-a:1": {
                    "passed": 2, "dropped": 10, "throttled": 0,
                    "backstopped": 64_000, "unidentified": 0, "window_s": 86_400,
                }
            }
        )
        assert census["discarded_per_day"] > 60_000
        assert census["over_ceiling"] is True
        assert census["ceiling_per_day"] > 0

    def test_an_empty_census_is_not_a_healthy_census(self):
        """No processes reporting is an ABSENCE, and must not render as zero
        discards / green — the exact shape that let #1894 run 14 days."""
        from app.utils import sentry_filter

        census = sentry_filter.summarize_filter_counts({})
        assert census["status"] == "no_data"
        assert census["over_ceiling"] is None


# =============================================================================
# R4 — the ceiling derives from declared NEED, never from raw quota
# =============================================================================

#: Fixed instant inside the measured 07-21 -> 08-21 cycle, so ``cycle_length_days``
#: is 31 by construction and not by whatever day the suite happens to run
#: (gotcha #44: an anchor that branches on the clock is not an anchor).
_IN_CYCLE = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


class TestTheCeilingDerivesFromNeedNotQuota:
    """``C-CERT-SENTRY-R4`` refused to arm, and its reason was one line:

        ``DISCARD_CEILING_PER_DAY = QUOTA_EVENTS_PER_MONTH``

    At the 5,000-event plan that produced 5,000/day, which is a defensible
    blindness ceiling. At the 50,000 plan it produces 50,000/day, under which the
    measured 19,066/day cron blindness renders healthy. The ceiling was never
    wrong by arithmetic — it was a *budget* wearing a *ceiling's* name, and the
    two agreed only for as long as the plan did not change.

    Alex, 2026-08-17: *the ceiling derives from declared NEED, capped well under
    quota, never raw quota.*
    """

    def test_the_ceiling_is_not_simply_the_quota(self):
        """The whole defect, forbidden by name and through the pre-existing
        public surface — so a later refactor that keeps these function names but
        quietly restores ``= QUOTA_EVENTS_PER_MONTH`` is still caught.

        This is the one assertion in the class that fails against the old code
        for a BEHAVIOURAL reason rather than a missing attribute.
        """
        from app.utils import sentry_budget

        assert (
            sentry_budget.DISCARD_CEILING_PER_DAY
            != sentry_budget.QUOTA_EVENTS_PER_MONTH
        ), (
            "the discard ceiling is the monthly quota again — a plan upgrade "
            "now raises the blindness allowance with it (C-CERT-SENTRY-R4)"
        )

    def test_the_predicate_itself_tracks_need_not_the_frozen_constant(
        self, monkeypatch
    ):
        """``over_discard_ceiling`` is what every consumer actually calls. If the
        deriver is correct but the predicate still reads a stale import-time
        number, nothing user-visible changed."""
        from app.utils import sentry_budget

        monkeypatch.setattr(sentry_budget, "QUOTA_EVENTS_PER_MONTH", 50_000)
        assert sentry_budget.over_discard_ceiling(19_066, 86_400, now=_IN_CYCLE)
        assert not sentry_budget.over_discard_ceiling(1_269, 86_400, now=_IN_CYCLE)

    def test_the_old_coupling_would_go_blind_on_the_known_specimen(self):
        """The executable specimen. Not a story about a defect — the defect,
        run. If this ever stops failing under the old rule, the rule was fine
        and this whole class is unnecessary."""
        from app.utils import sentry_budget

        old_rule_ceiling = 50_000  # == QUOTA_EVENTS_PER_MONTH on the current plan
        assert not (19_066 > old_rule_ceiling), (
            "premise check: 19,066/day must be UNDER the old quota-derived "
            "ceiling — that is what made it blind"
        )
        assert sentry_budget.discard_ceiling_per_day(_IN_CYCLE) < old_rule_ceiling

    @pytest.mark.parametrize("quota", [5_000, 50_000])
    def test_the_blindness_specimen_is_over_ceiling_at_every_plan(
        self, monkeypatch, quota
    ):
        """19,066/day (the cron instance, 2026-08-16) and 64,039/day (R3) must
        both breach at BOTH plans. A ceiling a plan upgrade can switch off is not
        a ceiling."""
        from app.utils import sentry_budget

        monkeypatch.setattr(sentry_budget, "QUOTA_EVENTS_PER_MONTH", quota)
        ceiling = sentry_budget.discard_ceiling_per_day(_IN_CYCLE)

        assert 19_066 > ceiling, f"19,066/day renders healthy at quota {quota}"
        assert 64_039 > ceiling, f"64,039/day renders healthy at quota {quota}"

    @pytest.mark.parametrize("quota", [5_000, 50_000])
    def test_a_healthy_day_is_still_under_it(self, monkeypatch, quota):
        """The other direction, or the fix is just a lower number that cries
        wolf. Measured healthy accepted volume was 770-1,269/day."""
        from app.utils import sentry_budget

        monkeypatch.setattr(sentry_budget, "QUOTA_EVENTS_PER_MONTH", quota)
        assert 1_269 < sentry_budget.discard_ceiling_per_day(_IN_CYCLE)

    def test_a_tenfold_quota_raise_does_not_tenfold_the_ceiling(self, monkeypatch):
        """The property R4 actually wants. The ceiling may move with need — the
        solved cap genuinely rises when more is affordable — but it must not
        TRACK the plan."""
        from app.utils import sentry_budget

        monkeypatch.setattr(sentry_budget, "QUOTA_EVENTS_PER_MONTH", 5_000)
        small = sentry_budget.discard_ceiling_per_day(_IN_CYCLE)
        monkeypatch.setattr(sentry_budget, "QUOTA_EVENTS_PER_MONTH", 50_000)
        big = sentry_budget.discard_ceiling_per_day(_IN_CYCLE)

        assert big / small < 2.0, (
            f"a 10x quota raise moved the ceiling {big / small:.1f}x "
            f"({small} -> {big}) — the ceiling is still tracking the plan"
        )

    def test_the_ceiling_is_one_cycle_of_declared_need(self, monkeypatch):
        """Derived, and the derivation is checkable rather than asserted."""
        import math

        from app.utils import sentry_budget

        monkeypatch.setattr(sentry_budget, "QUOTA_EVENTS_PER_MONTH", 50_000)
        expected = math.ceil(
            sentry_budget.declared_need_per_day(_IN_CYCLE)
            * sentry_budget.cycle_length_days(_IN_CYCLE)
        )
        assert sentry_budget.discard_ceiling_per_day(_IN_CYCLE) == expected

    def test_the_ceiling_never_exceeds_the_quota(self, monkeypatch):
        """Quota's one remaining role, and it is a clamp in the safe direction
        only. Past the quota the ceiling has stopped bounding anything."""
        from app.utils import sentry_budget

        monkeypatch.setattr(sentry_budget, "QUOTA_EVENTS_PER_MONTH", 500)
        v = sentry_budget.discard_ceiling_verdict(_IN_CYCLE)
        assert v["ceiling_per_day"] <= 500
        assert v["clamped_by_quota"] is True

    def test_the_share_of_quota_is_reported_not_silently_enforced(self, monkeypatch):
        """A *fractional* clamp would be a quota-derived ceiling on every
        occasion it binds — and at the 5,000 default it binds immediately, which
        would reinstate exactly the coupling this class removes. So 'well under
        quota' is measured and reported, and a violation is loud."""
        from app.utils import sentry_budget

        monkeypatch.setattr(sentry_budget, "QUOTA_EVENTS_PER_MONTH", 50_000)
        assert sentry_budget.discard_ceiling_verdict(_IN_CYCLE)["well_under_quota"]

        monkeypatch.setattr(sentry_budget, "QUOTA_EVENTS_PER_MONTH", 5_000)
        v = sentry_budget.discard_ceiling_verdict(_IN_CYCLE)
        assert v["well_under_quota"] is False, (
            "at a plan the policy cannot even afford cap 1 on, the ceiling is "
            "NOT comfortably under quota, and the verdict must say so"
        )
        assert v["derived_from"] == "declared_need_per_day * cycle_days"

    def test_the_exported_constant_agrees_with_the_function(self):
        """``sentry_filter`` reads the module constant on the exception path.
        The two must not drift — a constant that disagrees with its own deriver
        is the typed literal R3 deleted, restored by the back door."""
        from app.utils import sentry_budget

        assert (
            sentry_budget.DISCARD_CEILING_PER_DAY
            == sentry_budget.discard_ceiling_per_day()
        )


# =============================================================================
# Finding 1 — the budget is DIVIDED OUT of the quota, not compared to it
# =============================================================================

class TestBudgetIsBoundedByConstruction:
    """R3: the policy priced 184.25/day against a 164.47/day affordance.

    The old model computed a priced total and then *asserted* it was under the
    budget. Every failure mode of that shape is the same: the assertion is one
    edit away from being retuned, and the number it guards is one new reserve
    away from being wrong. Here the per-process allowance is obtained BY DIVIDING
    the budget, so the fleet total cannot exceed it for any input.
    """

    def test_the_billing_cycle_is_the_measured_one(self):
        """Measured in #1894 over two consecutive cycles: acceptance resumes on
        the 21st (06-21 and 07-21) and dies mid-cycle both times."""
        from app.utils import sentry_budget

        assert sentry_budget.BILLING_CYCLE_RESET_DAY == 21
        start, end = sentry_budget.cycle_window(
            datetime(2026, 8, 5, tzinfo=timezone.utc)
        )
        assert start == datetime(2026, 7, 21, tzinfo=timezone.utc)
        assert end == datetime(2026, 8, 21, tzinfo=timezone.utc)

    def test_the_reset_day_itself_starts_a_new_cycle(self):
        from app.utils import sentry_budget

        start, _ = sentry_budget.cycle_window(
            datetime(2026, 8, 21, 0, 0, tzinfo=timezone.utc)
        )
        assert start == datetime(2026, 8, 21, tzinfo=timezone.utc)

    def test_the_budget_uses_the_REAL_cycle_length_not_a_mean_month(self):
        """5,000/30.4 = 164.47 is a mean. The 07-21 -> 08-21 cycle is 31 days, so
        the honest affordance that month is 161.29 — and pricing against the mean
        overspends by 19 events every 31-day cycle."""
        from app.utils import sentry_budget

        aug = sentry_budget.sustainable_daily_budget(
            datetime(2026, 8, 5, tzinfo=timezone.utc)
        )
        assert round(aug, 2) == round(5_000 / 31, 2)

    def test_overspending_early_SHRINKS_the_remaining_budget(self):
        """The measured failure: ~823/day for 8 days, then 22 days of silence.
        A flat mean budget cannot express that; a reset-aware one must."""
        from app.utils import sentry_budget

        day8 = datetime(2026, 7, 29, tzinfo=timezone.utc)
        fresh = sentry_budget.remaining_daily_budget(day8, accepted_this_cycle=0)
        burnt = sentry_budget.remaining_daily_budget(day8, accepted_this_cycle=4_900)
        assert burnt < fresh
        assert burnt < 10, "spending 98% of the quota must collapse the allowance"

    def test_the_budget_never_goes_negative_or_explodes_at_the_boundary(self):
        from app.utils import sentry_budget

        last = datetime(2026, 8, 20, 23, 59, tzinfo=timezone.utc)
        assert sentry_budget.remaining_daily_budget(last, 10_000) == 0.0
        assert sentry_budget.remaining_daily_budget(last, 0) <= 5_000

    def test_the_fleet_ceiling_cannot_exceed_the_budget_on_ANY_day(self):
        """THE construction test. Not one number — every day of a whole year."""
        from app.utils import sentry_budget

        day = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for _ in range(400):
            ceiling = sentry_budget.fleet_emission_ceiling(day)
            budget = sentry_budget.sustainable_daily_budget(day)
            assert ceiling <= budget, (
                f"{day:%Y-%m-%d}: ceiling {ceiling} > affordance {budget:.2f}"
            )
            day += timedelta(days=1)

    def test_when_it_fits_it_clears_the_margin_and_when_it_does_not_it_SAYS_so(self):
        """The honest disjunction, and the reason this is not a red test today.

        On the 31-day 07-21 -> 08-21 cycle the complete price at cap 1 is
        150.2/day against 141.94/day affordable: it does NOT fit. That is R3's
        finding, reproduced by construction rather than argued. What the code
        must guarantee is not "it always fits" — that would be a lie the moment
        production got noisier — but that it can never fit *silently by leaving a
        reserve out*, and that a miss carries its own size.
        """
        from app.utils import sentry_budget

        for day in (
            datetime(2026, 2, 25, tzinfo=timezone.utc),   # 28-day cycle
            datetime(2026, 8, 17, tzinfo=timezone.utc),   # 31-day cycle
            datetime(2026, 9, 30, tzinfo=timezone.utc),   # 30-day cycle
        ):
            verdict = sentry_budget.budget_verdict(day)
            if verdict["fits"]:
                assert verdict["priced_per_day"] <= verdict["affordable_per_day"]
                assert verdict["shortfall_per_day"] == 0.0
            else:
                assert verdict["shortfall_per_day"] > 0.0
                assert verdict["required_monthly_quota"] > verdict["quota_per_month"]

    def test_the_shortfall_names_the_quota_that_would_close_it(self):
        """"We are over budget" is not actionable; "buy 5,291/month" is."""
        from app.utils import sentry_budget

        now = datetime(2026, 8, 17, tzinfo=timezone.utc)
        needed = sentry_budget.required_monthly_quota(now)
        raised = sentry_budget.priced_daily_total(1) <= (
            needed / sentry_budget.cycle_length_days(now)
        ) * (1 - sentry_budget.MIN_SAFE_MARGIN) + 1e-9
        assert raised, "the quoted quota does not actually close the gap"

    def test_the_missing_reserve_is_now_INSIDE_the_price(self):
        """R3's finding 1 in one line: ``watchdog_ceiling_per_day`` was asserted
        in its own test, beside the model, where it could not affect the number
        the model produced."""
        from app.utils import sentry_budget

        priced = sentry_budget.priced_daily_total(1)
        assert priced >= (
            sentry_budget.CENSUS_REPLAY_PER_DAY_AT_CAP_1
            + sentry_budget.novel_signature_reserve(1)
            + sentry_budget.watchdog_ceiling_per_day(1)
        )

    def test_the_r3_priced_total_is_now_structurally_unreachable(self):
        """184.25/day was reachable because the model only ADDED reserves. Under
        a divided allowance there is nothing to add to: a novel signature and a
        failed-open watchdog spend the same allowance as everything else."""
        from app.utils import sentry_budget

        now = datetime(2026, 8, 17, tzinfo=timezone.utc)
        assert sentry_budget.fleet_emission_ceiling(now) < 184.25

    def test_the_margin_floor_matches_the_one_the_replay_suite_uses(self):
        """Two copies of a safety floor that can drift is a third defect."""
        from app.utils import sentry_budget
        from tests.fixtures.sentry_formation import MIN_SAFE_MARGIN

        assert sentry_budget.MIN_SAFE_MARGIN == MIN_SAFE_MARGIN

    def test_the_cap_is_never_zero_so_novel_bugs_still_surface(self):
        """A budget that resolves to "emit nothing" is a mute, not a budget.

        This is the boundary of the construction and it is chosen, not an
        oversight: when the price does not fit, the cap floors at 1 and the
        overage is REPORTED. Silencing the fleet to fit a bill would re-break
        codex finding (b) — every novel failure site must send its first event —
        and would make the monitoring system take production's visibility down
        to protect its own invoice.
        """
        from app.utils import sentry_budget

        for quota in (1, 100, 5_000, 500_000):
            assert (
                sentry_budget.effective_backstop_per_window(
                    datetime(2026, 8, 17, tzinfo=timezone.utc),
                    base_per_day=10_000.0 if quota < 5_000 else 136.2,
                )
                >= 1
            )


class TestTheCapIsSolvedFromTheBudget:
    """The construction, exercised from both directions.

    The old model let you write ``BACKSTOP_PER_WINDOW = 3`` and then argue about
    whether it fit. Here the cap is the RETURN VALUE of a search over the budget,
    so the only way to raise it is to make it affordable.
    """

    def test_the_shipped_cap_is_the_solved_cap(self):
        from app.utils import sentry_budget
        from app.utils import sentry_filter

        assert sentry_filter.BACKSTOP_PER_WINDOW == (
            sentry_budget.effective_backstop_per_window()
        )

    def test_a_bigger_quota_can_buy_a_bigger_cap(self):
        """Direction one: affordance is the thing that moves the cap."""
        from app.utils import sentry_budget

        now = datetime(2026, 8, 17, tzinfo=timezone.utc)
        lean = sentry_budget.solve_backstop_per_window(now, base_per_day=136.2)
        with_headroom = sentry_budget.solve_backstop_per_window(
            now, base_per_day=0.0
        )
        assert with_headroom > lean

    def test_a_noisier_fleet_cannot_keep_the_same_cap(self):
        """Direction two: the cap falls when the census cost rises. Under the old
        model the cap was a literal and a noisier fleet changed nothing."""
        from app.utils import sentry_budget

        now = datetime(2026, 8, 17, tzinfo=timezone.utc)
        assert sentry_budget.solve_backstop_per_window(
            now, base_per_day=5_000.0
        ) == 0

    def test_the_solve_NEVER_returns_a_cap_it_cannot_afford(self):
        """The property, over a wide sweep rather than one example."""
        from app.utils import sentry_budget

        now = datetime(2026, 8, 17, tzinfo=timezone.utc)
        for base in (0.0, 12.5, 60.0, 136.2, 140.0, 200.0, 5_000.0):
            cap = sentry_budget.solve_backstop_per_window(now, base_per_day=base)
            if cap:
                assert sentry_budget.priced_daily_total(
                    cap, base
                ) <= sentry_budget.affordable_daily_emission(now)

    def test_an_overcommitted_budget_is_LOUD_not_absorbed(self):
        from app.utils import sentry_budget

        verdict = sentry_budget.budget_verdict(
            datetime(2026, 8, 17, tzinfo=timezone.utc), base_per_day=5_000.0
        )
        assert verdict["fits"] is False
        assert verdict["solved_cap"] == 0
        assert verdict["backstop_per_window"] == 1
        assert verdict["shortfall_per_day"] > 0

    def test_an_UNMEASURED_cap_is_unpriceable_and_can_never_be_selected(self):
        """The replay cost is not linear in the cap (1 -> 3 costs +20.8/day) and
        nobody has measured 2, 4 or 8. An earlier draft priced every cap with the
        cap-1 base, so a quota raise selected cap 8 on a number that had never
        been measured for cap 8 — R3's own defect, one level down.
        """
        from app.utils import sentry_budget

        assert sentry_budget.priced_daily_total(2) == float("inf")
        assert sentry_budget.priced_daily_total(8) == float("inf")
        assert set(sentry_budget.SOLVABLE_CAPS) == set(
            sentry_budget.CENSUS_REPLAY_PER_DAY
        )

    def test_even_an_enormous_quota_cannot_buy_an_unmeasured_cap(self):
        from app.utils import sentry_budget

        now = datetime(2026, 8, 17, tzinfo=timezone.utc)
        assert sentry_budget.solve_backstop_per_window(
            now, base_per_day=0.0
        ) in sentry_budget.SOLVABLE_CAPS

    def test_the_census_base_constant_still_matches_the_replay_suite(self):
        """Anti-drift: the price is quoted from a measurement that lives in
        another file, and a stale copy of a measurement is worse than none."""
        from app.utils import sentry_budget

        assert sentry_budget.CENSUS_REPLAY_PER_DAY_AT_CAP_1 == 136.2

    def test_the_formation_constants_match_the_procfile_derived_ones(self):
        from app.utils import sentry_budget
        from tests.fixtures.sentry_formation import (
            MAX_WORKER_CONCURRENCY,
            WATCHDOG_COOLDOWN_WINDOWS_PER_DAY,
            WATCHDOG_PAIRS_PER_DAY,
            WATCHDOG_POOL_CHILDREN,
        )

        assert sentry_budget.MAX_WORKER_POOL_CHILDREN == MAX_WORKER_CONCURRENCY
        assert sentry_budget.WATCHDOG_POOL_CHILDREN == WATCHDOG_POOL_CHILDREN
        assert (
            sentry_budget.WATCHDOG_COOLDOWN_WINDOWS_PER_DAY
            == WATCHDOG_COOLDOWN_WINDOWS_PER_DAY
        )
        assert sentry_budget.WATCHDOG_PAIRS_PER_DAY == WATCHDOG_PAIRS_PER_DAY

    def test_the_backstop_still_caps_repeats(self):
        """The per-signature cap survives: the solve bounds the total, the
        backstop bounds any one signature. Losing either re-opens a hole."""
        assert BACKSTOP_PER_WINDOW >= 1


class TestStructuredLogTelemetryIsNotOnOurPath:
    """#1894 flagged ``sentry_sdk/client.py:1190`` as a possible second exposure:
    telemetry passed through a ``before_send`` with no type guard.

    Checked, and it is NOT ours — ``client.py:1184-1191`` selects
    ``get_before_send_log`` / ``get_before_send_metric``, which read the separate
    ``before_send_log`` / ``before_send_metric`` options. Neither init site sets
    them (``app/main.py:50-58``, ``app/tasks/__init__.py:609-619``), so the log and
    metric batchers never reach ``SentryVolumeFilter``. Recorded as a test so the
    day someone sets one of those options, this states the consequence.
    """

    def test_neither_init_site_sets_a_telemetry_before_send(self):
        import inspect

        import app.main as main_mod
        import app.tasks as tasks_mod

        for mod in (main_mod, tasks_mod):
            src = inspect.getsource(mod)
            assert "before_send_log" not in src, (
                f"{mod.__name__} now routes structured logs through a before_send "
                "— SentryVolumeFilter was never designed to judge them"
            )
            assert "before_send_metric" not in src


class TestNeitherFixWorksAlone:
    """Alex's framing, made executable: the two findings are coupled.

    Fixing only the budget leaves 64k discards/day that survive the quota reset.
    Fixing only the filter leaves an emission model that prices above affordance
    the moment a novel signature appears. Both are asserted here so a partial
    revert is loud.
    """

    def test_cron_volume_no_longer_reaches_the_error_budget_at_all(self):
        """5,000 check-ins — a day and a half of real beat traffic — cost zero
        discards. Pre-fix this was 4,999 ``before_send`` losses, every one of
        them billed to the error category by ``client.py:883``."""
        bs = build_before_send()
        for _ in range(5_000):
            bs(check_in_event(), {})
        assert bs.counts["backstopped"] == 0
        assert bs.counts["dropped"] == 0
        assert bs.counts["not_error"] == 5_000

    def test_and_the_emission_side_is_still_bounded(self):
        from app.utils import sentry_budget

        now = datetime(2026, 8, 17, tzinfo=timezone.utc)
        assert (
            sentry_budget.fleet_emission_ceiling(now)
            <= sentry_budget.sustainable_daily_budget(now)
        )

    def test_the_discard_ceiling_would_have_caught_the_cron_flood(self):
        """And the observability half closes the loop: had this existed on
        2026-08-14, the very first ops read would have been RED."""
        from app.utils.sentry_filter import summarize_filter_counts

        census = summarize_filter_counts(
            {
                "scheduler:1": {
                    "passed": 1, "dropped": 0, "throttled": 0,
                    "backstopped": 10_153, "not_error": 0, "unidentified": 10_153,
                    "window_s": 43_200,
                },
                "worker-realtime:176": {
                    "passed": 2, "dropped": 0, "throttled": 0,
                    "backstopped": 2_167, "not_error": 0, "unidentified": 2_167,
                    "window_s": 43_200,
                },
            }
        )
        assert census["over_ceiling"] is True
        assert census["unidentified"] > 0, (
            "the counter that names 'we could not tell these apart' is the one "
            "that would have pointed straight at the signature collapse"
        )


@pytest.mark.parametrize("verdict", ["drop", "throttle", "pass"])
def test_the_three_tiers_still_exist_after_the_change(verdict):
    """Regression guard: the R3 fixes must not quietly delete a tier."""
    from app.utils import sentry_filter

    assert verdict in (
        sentry_filter.VERDICT_DROP,
        sentry_filter.VERDICT_THROTTLE,
        sentry_filter.VERDICT_PASS,
    )


def test_a_real_redis_churn_error_is_still_dropped():
    """The policy's original job must survive both fixes."""
    event = {
        "exception": {
            "values": [{"type": "ConnectionError", "module": "redis.exceptions",
                        "value": "Error 8 connecting to broker"}]
        }
    }
    assert classify(event, {}) == "drop"


# =============================================================================
# R4 finding P1 — a long-lived process must not carry its cycle across a reset
# =============================================================================

class TestThePolicyIsNotFrozenAtImport:
    """C-CERT-SENTRY-R4, BLOCK: *"the shipping cap and exported budget verdict
    freeze at import, so a live process crossing a 28->31-day billing cycle
    hides the required 8.26/day shortfall."*

    Every function in ``sentry_budget`` already derived cycle length from the
    timestamp it was handed. The defect was one level up — ``sentry_filter``
    read two of them ONCE, at import, and a dyno outlives a billing cycle. The
    transition then smooths away a real shortfall, which is the worst direction
    for a budget instrument to be wrong in: nothing changed, nobody acted, and
    the number improved.
    """

    #: Inside the 28-day 2026-02-21 -> 2026-03-21 cycle.
    FEB = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    #: Inside the 31-day 2026-03-21 -> 2026-04-21 cycle that follows it.
    MAR = datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc)

    def test_the_two_cycles_really_do_differ_in_length(self):
        """Premise check. If these are the same length the specimen proves
        nothing, and the test would pass for the wrong reason."""
        from app.utils import sentry_budget

        assert sentry_budget.cycle_length_days(self.FEB) == 28
        assert sentry_budget.cycle_length_days(self.MAR) == 31

    def test_the_verdict_follows_the_boundary(self, monkeypatch):
        """Codex's exact specimen, at quota 5,000."""
        from app.utils import sentry_budget

        monkeypatch.setattr(sentry_budget, "QUOTA_EVENTS_PER_MONTH", 5_000)
        monkeypatch.setattr(
            sentry_budget, "_CACHE", {"key": None, "cap": None, "verdict": None}
        )

        before = sentry_budget.current_budget_verdict(self.FEB)
        after = sentry_budget.current_budget_verdict(self.MAR)

        assert before["cycle_days"] == 28
        assert after["cycle_days"] == 31, (
            "the process carried the previous cycle across the reset — the "
            "import-frozen verdict, restored"
        )
        assert after["shortfall_per_day"] == 8.26
        assert after["fits"] is False

    def test_the_enforced_cap_follows_the_boundary(self, monkeypatch):
        """The other half: the cap the filter ENFORCES, not just what it reports."""
        from app.utils import sentry_budget

        monkeypatch.setattr(sentry_budget, "QUOTA_EVENTS_PER_MONTH", 6_200)
        monkeypatch.setattr(
            sentry_budget, "_CACHE", {"key": None, "cap": None, "verdict": None}
        )

        before = sentry_budget.current_backstop_per_window(self.FEB)
        after = sentry_budget.current_backstop_per_window(self.MAR)
        fresh = sentry_budget.effective_backstop_per_window(self.MAR)

        assert after == fresh, (
            f"enforced {after} after the reset, fresh solve says {fresh} "
            f"(was {before} in the 28-day cycle)"
        )

    def test_the_filter_reads_live_not_the_import_snapshot(self):
        """A named constant that still exists is not the same as a constant that
        is still ENFORCED. Guards against a later edit re-pointing the hot path
        at the frozen value."""
        import inspect

        from app.utils import sentry_filter

        emit = inspect.getsource(sentry_filter.summarize_filter_counts)
        assert "current_budget_verdict" in emit
        assert "BUDGET_VERDICT" not in emit.replace("current_budget_verdict", "")

        src = inspect.getsource(sentry_filter)
        assert "limit=sentry_budget.current_backstop_per_window()" in src, (
            "the backstop is enforced from the import-time snapshot again"
        )

    def test_the_import_snapshot_is_still_available_and_named_as_such(self):
        """Kept deliberately: 'what did this process boot with' is a real
        question, and answering it must not be confused with the live policy."""
        from app.utils import sentry_filter

        assert hasattr(sentry_filter, "BACKSTOP_PER_WINDOW_AT_IMPORT")
        assert hasattr(sentry_filter, "BUDGET_VERDICT_AT_IMPORT")

    def test_the_cache_does_not_re_solve_within_a_cycle(self, monkeypatch):
        """It is read on the hot path. One date comparison in the common case,
        not a search per event."""
        from app.utils import sentry_budget

        monkeypatch.setattr(
            sentry_budget, "_CACHE", {"key": None, "cap": None, "verdict": None}
        )
        calls = {"n": 0}
        real = sentry_budget.effective_backstop_per_window

        def counted(now=None, base=None):
            calls["n"] += 1
            return real(now, base)

        monkeypatch.setattr(sentry_budget, "effective_backstop_per_window", counted)

        sentry_budget.current_backstop_per_window(self.MAR)
        after_first = calls["n"]
        for _ in range(50):
            sentry_budget.current_backstop_per_window(self.MAR)

        # One REFRESH costs several solves (``budget_verdict`` re-enters via
        # shortfall + required-quota). What must not grow is the refresh count.
        assert after_first > 0
        assert calls["n"] == after_first, (
            f"re-solved on {calls['n'] - after_first} extra calls inside one cycle"
        )

        # ...and crossing the boundary DOES pay for a refresh, or the memo is
        # just the frozen constant with more ceremony.
        sentry_budget.current_backstop_per_window(self.FEB)
        assert calls["n"] > after_first

    def test_an_exported_verdict_cannot_be_mutated_by_its_reader(self, monkeypatch):
        """The dict travels into counter payloads. A caller mutating it would
        make the next reader's verdict depend on who read it first."""
        from app.utils import sentry_budget

        monkeypatch.setattr(
            sentry_budget, "_CACHE", {"key": None, "cap": None, "verdict": None}
        )
        first = sentry_budget.current_budget_verdict(self.MAR)
        first["shortfall_per_day"] = 0.0
        assert sentry_budget.current_budget_verdict(self.MAR)["shortfall_per_day"] != 0.0


class TestTheDisplayedCeilingIsTheEnforcedCeiling:
    """``C-CERT-SENTRY-R4`` BLOCK: ops displayed 5,292 and evaluated against 5,859.

    Neither number was miscomputed. The display read the import-time constant
    ``DISCARD_CEILING_PER_DAY``; the verdict called ``discard_ceiling_per_day()``
    live. Between them sat a band of discard rates that the ops page calls a
    breach and the enforcement does not — and a reader of the payload has no way
    to know which of the two they are looking at.

    They split for two reasons that are both guaranteed to happen again, not for
    an exotic one:

    * a web dyno outlives a billing cycle, so a 28-day ceiling frozen at boot is
      carried into a 31-day cycle;
    * a quota change lands after the dyno booted — which is exactly what was
      done on 2026-08-14, when ``SENTRY_QUOTA_EVENTS_PER_MONTH`` was raised in
      the release AFTER the one that shipped the ceiling, deliberately and in
      that order.

    This is the same family as #53 / #124 / rulings 071 and 072: an instrument
    reporting confidently about a quantity it did not measure. The fix is
    structural rather than a corrected constant — ONE derivation per read, whose
    value is both reported and compared against.
    """

    def test_the_census_ceiling_is_the_one_the_verdict_used(self, monkeypatch):
        """The property, stated so no arithmetic can satisfy it accidentally.

        The frozen constant is moved far away from the live derivation and the
        census is driven through its real path. If the display ever reads the
        constant again, ``ceiling_per_day`` comes back as the stale number while
        ``over_ceiling`` was decided by the live one — which is R4 exactly.
        """
        from app.utils import sentry_budget, sentry_filter

        live = sentry_budget.discard_ceiling_per_day()
        monkeypatch.setattr(sentry_budget, "DISCARD_CEILING_PER_DAY", live + 10_000)

        # A rate strictly inside the band between the two candidate ceilings.
        rate = live + 1
        rows = {"p1": {"window_s": 86_400.0, "cap": 1, "dropped": rate}}
        census = sentry_filter.summarize_filter_counts(rows)

        assert census["ceiling_per_day"] == live, (
            "the census displayed the frozen constant while judging against the "
            "live derivation — C-CERT-SENTRY-R4's 5,292-vs-5,859 split"
        )
        assert census["over_ceiling"] is True
        assert census["discarded_per_day"] > census["ceiling_per_day"]

    def test_a_rate_just_UNDER_the_displayed_ceiling_is_not_a_breach(self):
        """The other direction, so 'always True' cannot pass this class."""
        from app.utils import sentry_budget, sentry_filter

        live = sentry_budget.discard_ceiling_per_day()
        rows = {"p1": {"window_s": 86_400.0, "cap": 1, "dropped": live - 1}}
        census = sentry_filter.summarize_filter_counts(rows)

        assert census["over_ceiling"] is False
        assert census["ceiling_per_day"] == live

    def test_the_verdict_helper_and_the_census_cannot_disagree(self):
        """``over_discard_ceiling`` is the same derivation, not a second one.

        It is still called from elsewhere, so it must not be allowed to drift
        back into being an independent computation.
        """
        from app.utils import sentry_budget

        live = sentry_budget.discard_ceiling_per_day()
        for rate in (live - 1, live, live + 1):
            reading = sentry_budget.discard_ceiling_reading(rate, 86_400.0)
            assert reading["over_ceiling"] == sentry_budget.over_discard_ceiling(
                rate, 86_400.0
            )
            assert reading["ceiling_per_day"] == live

    def test_the_no_data_and_unavailable_paths_also_show_the_live_ceiling(
        self, monkeypatch
    ):
        """An operator reading the empty census must not be shown a stale bound.

        These paths report ``over_ceiling: None`` — correctly, since there is
        nothing to judge — but they still PRINT a ceiling, and a stale one there
        is the same lie with no verdict attached to contradict it.
        """
        from app.utils import sentry_budget, sentry_filter

        live = sentry_budget.discard_ceiling_per_day()
        monkeypatch.setattr(sentry_budget, "DISCARD_CEILING_PER_DAY", live + 10_000)

        empty = sentry_filter.summarize_filter_counts({})
        assert empty["ceiling_per_day"] == live
        assert empty["over_ceiling"] is None

        def _boom():
            raise RuntimeError("redis down")

        monkeypatch.setattr(sentry_filter, "_read_filter_counts", _boom)
        unavailable = sentry_filter.filter_discard_census()
        assert unavailable["status"] == "unavailable"
        assert unavailable["ceiling_per_day"] == live

    def test_R4s_literal_numbers_and_what_5500_a_day_actually_is(self, monkeypatch):
        """5,292 vs 5,859, reproduced exactly — and the 5,500 specimen resolved.

        The split is the CYCLE LENGTH, measured here rather than inferred: at the
        50,000 quota a 31-day cycle derives **5,859** and a 28-day cycle derives
        **5,292**. So a dyno that booted in February and is still up in March
        displays 5,292 while enforcing 5,859. That is R4's pair of numbers, and
        neither is a typo or a bad constant.

        🔴 **The directive's specimen said 5,500/day should read
        ``over_ceiling: true``. Under this fix it reads FALSE, and that is
        deliberate** — flagged rather than quietly resolved either way.

        5,500 sits inside the band precisely because the two candidates
        disagree. Picking the lower one is more conservative and is also
        *stale on purpose*: it would mean the ceiling an operator is held to
        depends on which month a dyno last restarted in, which is not a ceiling.
        The live derivation for the cycle we are actually in is 5,859, so 5,500
        is genuinely under it.

        If Alex wants the conservative reading instead, it is one line in
        ``discard_ceiling_reading`` — which is the entire benefit of there being
        one derivation. This test pins whichever is chosen so the choice cannot
        drift back into being an accident.
        """
        import importlib

        from app.utils import sentry_budget

        monkeypatch.setenv("SENTRY_QUOTA_EVENTS_PER_MONTH", "50000")
        sb = importlib.reload(sentry_budget)
        try:
            march = datetime(2026, 3, 25, tzinfo=timezone.utc)
            february = datetime(2026, 2, 25, tzinfo=timezone.utc)

            assert sb.cycle_length_days(march) == 31
            assert sb.cycle_length_days(february) == 28
            assert sb.discard_ceiling_per_day(march) == 5_859
            assert sb.discard_ceiling_per_day(february) == 5_292

            # The band R4 found, named as an interval rather than as two numbers.
            in_march = sb.discard_ceiling_reading(5_500, 86_400.0, march)
            assert in_march["ceiling_per_day"] == 5_859
            assert in_march["over_ceiling"] is False

            # And the same rate IS a breach inside a 28-day cycle — because the
            # ceiling genuinely is lower then, not because a constant went stale.
            in_february = sb.discard_ceiling_reading(5_500, 86_400.0, february)
            assert in_february["ceiling_per_day"] == 5_292
            assert in_february["over_ceiling"] is True
        finally:
            monkeypatch.delenv("SENTRY_QUOTA_EVENTS_PER_MONTH", raising=False)
            importlib.reload(sentry_budget)
