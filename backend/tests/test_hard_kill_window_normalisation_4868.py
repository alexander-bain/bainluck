"""LAT-P329 (#4868) — ``hard_kills_24h`` subtracted counters measured over
different windows, and published the difference as a kill count.

The specimen, read from production ``4f31a25a`` on 2026-09-10 18:55Z,
``GET /api/admin/task-metrics?task=datagolf_live``::

    starts_24h        284      starts_window_s      49524  (13.76 h)  20.64/h
    successes_24h     132      successes_window_s   22123  ( 6.15 h)  21.46/h
    hard_kills_24h    151   <- "53% of runs were SIGKILLed"
    health            healthy

Normalised by each counter's own window, successes run slightly FASTER than
starts: there is no kill signal at all. The 151 is a 6.2-hour count subtracted
from a 13.8-hour one. Every counter is ``SET NX EX 86400`` at its own first
increment, so the four keys expire on four schedules; once anything separates
their birthdays the difference is permanently biased, and the bias scales with
the task's frequency (``datagolf_live`` fires ~21×/h, so a 7.6-hour offset
manufactures ~150 phantom kills). ``_terminal_evidence_refutes_hard_kill``
already knew the failure mode but can only ever refute ONE kill — the last run,
the only one its stamps speak for — so 150 of 151 survived into the field.

Why it matters beyond one bad number: ship 2 (#4456) is "front-end changes stop
killing price and schedule jobs", and this is the instrument that ship is graded
on. While the field can be biased by an arbitrary window offset, a before/after
read cannot tell "we stopped killing jobs" from "the two counter keys happen to
be better aligned this week".

THE LOAD-BEARING PROPERTY, pinned by ``TestItReducesToTheOldNumber``: when the
counters share a window the algebra collapses to the old subtraction exactly,
(S/W − T/W) × W = S − T. So this is not a redefinition of the field — a task
whose keys are aligned reports what it always reported, to the unit, and the
value moves only where the windows disagree.
"""

from __future__ import annotations

import random

import pytest

from app.tasks.redis_state import (
    _HARD_KILL_MIN_WINDOW_S,
    normalised_hard_kills_24h,
)


def _raw(counts: dict) -> int:
    return max(
        0,
        int(counts.get("starts") or 0)
        - (
            int(counts.get("successes") or 0)
            + int(counts.get("failures") or 0)
            + int(counts.get("incompletes") or 0)
        ),
    )


class TestTheProductionSpecimen:
    #: verbatim from #4868
    COUNTS = {"starts": 284, "successes": 132, "failures": 0, "incompletes": 0}
    WINDOWS = {"starts_window_s": 49524, "successes_window_s": 22123}

    def test_the_151_phantom_kills_become_zero(self):
        assert _raw(self.COUNTS) == 152  # 151 after the one-kill refutation
        value, basis = normalised_hard_kills_24h(
            self.COUNTS, self.WINDOWS, _raw(self.COUNTS)
        )
        assert value == 0, "there is no kill signal in this payload at all"
        assert basis == "window_normalised"

    def test_the_reason_is_that_successes_outpace_starts(self):
        """Not an arbitrary threshold — the terminal rate is genuinely higher,
        which is why the honest answer is zero rather than 'a bit less than 151'."""
        starts_per_h = 284 / (49524 / 3600)
        successes_per_h = 132 / (22123 / 3600)
        assert successes_per_h > starts_per_h


class TestTheRealKillSignalSurvives:
    """The direction that would hurt most if this over-corrected: a task that
    genuinely never reaches a handler must still report its kills."""

    def test_starts_with_no_terminal_of_any_kind_reports_every_start(self):
        """``precompute_interestingness``: 6 starts, 6 kills, zero successes,
        zero failures, zero incompletes."""
        value, basis = normalised_hard_kills_24h(
            {"starts": 6}, {"starts_window_s": 86400}, 6
        )
        assert value == 6
        assert basis == "window_normalised"

    def test_a_zero_counter_needs_no_window_of_its_own(self):
        """A task that has never succeeded has no ``:successes`` key and so no
        window. That must stay measurable — it is the real hard-kill shape, and
        demanding a window for a count of zero would make it unmeasurable
        exactly when it matters."""
        value, basis = normalised_hard_kills_24h(
            {"starts": 40, "successes": 0, "failures": 0, "incompletes": 0},
            {"starts_window_s": 7200, "successes_window_s": None},
            40,
        )
        assert (value, basis) == (40, "window_normalised")

    def test_half_the_runs_killed_on_matched_windows_reports_half(self):
        counts = {"starts": 100, "successes": 50}
        windows = {"starts_window_s": 36000, "successes_window_s": 36000}
        assert normalised_hard_kills_24h(counts, windows, 50) == (
            50,
            "window_normalised",
        )


class TestItReducesToTheOldNumber:
    """The property that makes this safe to publish under the existing name."""

    def test_matched_windows_reproduce_the_raw_difference_exactly(self):
        counts = {"starts": 284, "successes": 132, "failures": 3, "incompletes": 1}
        w = 49524
        windows = {f"{k}_window_s": w for k in
                   ("starts", "successes", "failures", "incompletes")}
        raw = _raw(counts)
        assert normalised_hard_kills_24h(counts, windows, raw) == (
            raw,
            "window_normalised",
        )

    def test_the_identity_holds_across_twenty_thousand_random_payloads(self):
        """(S/W − T/W) × W = S − T. Asserted rather than reasoned about, because
        a rounding choice or a stray unit conversion would break it silently and
        the whole safety argument for this change rests on it."""
        rng = random.Random(7)
        for _ in range(20_000):
            w = rng.randint(_HARD_KILL_MIN_WINDOW_S, 86_400)
            starts = rng.randint(0, 5_000)
            cap = max(1, starts // 3)
            counts = {
                "starts": starts,
                "successes": rng.randint(0, cap),
                "failures": rng.randint(0, cap),
                "incompletes": rng.randint(0, cap),
            }
            windows = {f"{k}_window_s": w for k in
                       ("starts", "successes", "failures", "incompletes")}
            raw = _raw(counts)
            assert normalised_hard_kills_24h(counts, windows, raw) == (
                raw,
                "window_normalised",
            ), (counts, w)


class TestWhenItCannotNormaliseItSaysSoAndKeepsTheOldNumber:
    """``None`` was the first design and it was wrong: it reads as "no kills" to
    anything that does not check the basis, and it discards the only figure
    available on a task whose TTLs are unreadable. The defect was never that the
    raw number exists — it is that it was published unlabelled."""

    def test_an_unreadable_terminal_window_falls_back_labelled(self):
        counts = {"starts": 200, "successes": 120}
        windows = {"starts_window_s": 40000, "successes_window_s": None}
        assert normalised_hard_kills_24h(counts, windows, 80) == (
            80,
            "raw_unnormalised:window_unmeasurable",
        )

    def test_a_window_too_young_to_be_a_rate_falls_back_labelled(self):
        """One fire in the first 30 seconds of a counter's life extrapolates to
        2,880 a day. Below the floor the rate is one event over an epsilon."""
        counts = {"starts": 5, "successes": 1}
        windows = {"starts_window_s": 30, "successes_window_s": 30}
        assert normalised_hard_kills_24h(counts, windows, 4) == (
            4,
            "raw_unnormalised:window_too_short",
        )

    def test_a_missing_starts_window_falls_back_rather_than_dividing_by_none(self):
        assert normalised_hard_kills_24h(
            {"starts": 9, "successes": 2}, {}, 7
        ) == (7, "raw_unnormalised:window_too_short")

    @pytest.mark.parametrize("basis_case", ["unmeasurable", "too_short"])
    def test_every_fallback_is_labelled_raw_unnormalised(self, basis_case):
        """A reader must never have to guess which of the two numbers it is
        holding. Any future branch that returns the raw value without saying so
        is the #4868 defect coming back."""
        if basis_case == "unmeasurable":
            out = normalised_hard_kills_24h(
                {"starts": 200, "successes": 120},
                {"starts_window_s": 40000, "successes_window_s": 0},
                80,
            )
        else:
            out = normalised_hard_kills_24h(
                {"starts": 5, "successes": 1},
                {"starts_window_s": 10, "successes_window_s": 10},
                4,
            )
        assert out[1].startswith("raw_unnormalised:")


class TestTheEdges:
    def test_a_task_with_no_starts_is_zero_not_a_fallback(self):
        """No starts means nothing could have been killed. That is an answer,
        not an absence, and it must not be labelled unnormalised."""
        assert normalised_hard_kills_24h({"starts": 0}, {}, 0) == (
            0,
            "window_normalised",
        )

    def test_terminals_outpacing_starts_clamps_at_zero_never_negative(self):
        value, _ = normalised_hard_kills_24h(
            {"starts": 10, "successes": 900},
            {"starts_window_s": 3600, "successes_window_s": 3600},
            0,
        )
        assert value == 0

    def test_all_three_terminal_counters_are_summed_not_just_successes(self):
        """A run that ends in a failure or a teardown reached a handler just as
        much as one that succeeded. Dropping either would manufacture kills out
        of the tasks that fail honestly."""
        counts = {"starts": 90, "successes": 30, "failures": 30, "incompletes": 30}
        windows = {f"{k}_window_s": 36000 for k in
                   ("starts", "successes", "failures", "incompletes")}
        assert normalised_hard_kills_24h(counts, windows, 0)[0] == 0

    def test_a_skew_in_the_other_direction_raises_the_count(self):
        """The correction is not a one-way suppressor. If the TERMINAL window is
        the long one, the raw difference UNDER-counts and the normalised figure
        must be higher — otherwise this is just a way of making numbers smaller."""
        counts = {"starts": 100, "successes": 100}
        windows = {"starts_window_s": 3600, "successes_window_s": 36000}
        value, basis = normalised_hard_kills_24h(counts, windows, 0)
        assert basis == "window_normalised"
        assert value == 90, "100/h started, 10/h finished, over one hour"


# =============================================================================
# The wiring, driven through the real `get_task_metrics`
# =============================================================================

from app.tasks import redis_state  # noqa: E402
from app.tasks.redis_state import TASK_METRICS_PREFIX, WINDOW_COUNTER_TTL  # noqa: E402


class _FakeWithWindows:
    """Redis double whose counters have READABLE TTLs.

    The `_Fake` in `test_lat_p070_hard_kill_reconciliation.py` returns `ttl` -1,
    so every window reads as unmeasurable and the fallback path is taken — which
    is exactly why the whole pre-existing suite kept passing through this change
    untouched, and exactly why it cannot exercise the normalised path. Windows
    are given here as AGES; the double converts to the TTL the code reads back.
    """

    def __init__(self, task, hash_fields, counters, window_ages):
        self.task = task
        self.hash_fields = hash_fields
        self.counters = counters
        self.window_ages = window_ages

    def hgetall(self, key):
        return self.hash_fields if key.rsplit(":", 1)[-1] == self.task else {}

    def get(self, key):
        return self.counters.get(key)

    def ttl(self, key):
        label = key.rsplit(":", 1)[-1]
        if label in self.window_ages:
            return WINDOW_COUNTER_TTL - self.window_ages[label]
        return -2 if key not in self.counters else -1

    def lrange(self, *_a, **_k):
        return []

    def keys(self, _pattern):
        return [f"{TASK_METRICS_PREFIX}:{self.task}".encode()]


def _metrics(monkeypatch, task, hash_fields, counters, window_ages):
    monkeypatch.setattr(
        redis_state,
        "get_redis_client",
        lambda *a, **k: _FakeWithWindows(task, hash_fields, counters, window_ages),
    )
    return redis_state.get_task_metrics(task)


class TestThePublishedPayload:
    def test_the_datagolf_specimen_publishes_zero_and_keeps_the_raw_beside_it(
        self, monkeypatch
    ):
        result = _metrics(
            monkeypatch,
            "datagolf_live",
            {b"consecutive_failures": b"0"},
            {
                f"{TASK_METRICS_PREFIX}:datagolf_live:starts": b"284",
                f"{TASK_METRICS_PREFIX}:datagolf_live:successes": b"132",
            },
            {"starts": 49524, "successes": 22123},
        )
        assert result["hard_kills_24h"] == 0
        assert result["hard_kills_basis"] == "window_normalised"
        assert result["hard_kills_raw_diff"] == 152, (
            "the old number stays visible — the gap between the two IS the skew"
        )

    def test_the_refutation_still_fires_where_the_normalised_figure_is_zero(
        self, monkeypatch
    ):
        """The gate is on the RAW difference. Gating it on the normalised figure
        instead would stop publishing `hard_kills_refuted` on precisely the
        skewed-window tasks this change is about — a mutant that survived until
        this test existed."""
        result = _metrics(
            monkeypatch,
            "datagolf_live",
            {
                b"consecutive_failures": b"0",
                b"last_started_at": b"2026-09-10T18:00:00+00:00",
                b"last_success_at": b"2026-09-10T18:00:01+00:00",
            },
            {
                f"{TASK_METRICS_PREFIX}:datagolf_live:starts": b"284",
                f"{TASK_METRICS_PREFIX}:datagolf_live:successes": b"132",
            },
            {"starts": 49524, "successes": 22123},
        )
        assert "hard_kills_refuted" in result
        assert result["hard_kills_24h"] == 0
        assert result["hard_kills_raw_diff"] == 151, "the one refuted kill comes off"

    def test_health_is_identical_where_the_refutation_is_read(self, monkeypatch):
        """Why the gate choice is safe rather than merely deliberate. The health
        branch that reads `hard_kill_refutation` sits under
        `successes == failures == incompletes == 0`, and with every terminal at
        zero the terminal rate is zero too — so the normalised figure and the raw
        difference are equal by construction and both gates open together."""
        counters = {f"{TASK_METRICS_PREFIX}:some_task:starts": b"12"}
        windows = {"starts": 43200}

        killed = _metrics(
            monkeypatch, "some_task", {b"consecutive_failures": b"0"},
            counters, windows,
        )
        assert killed["hard_kills_24h"] == killed["hard_kills_raw_diff"] == 12
        assert killed["health"] == "critical"
        assert "hard-killed" in killed["health_reason"]

        refuted = _metrics(
            monkeypatch,
            "some_task",
            {
                b"consecutive_failures": b"0",
                b"last_started_at": b"2026-09-10T18:00:00+00:00",
                b"last_success_at": b"2026-09-10T18:00:01+00:00",
            },
            counters,
            windows,
        )
        assert refuted["health"] == "healthy"

    def test_a_task_whose_ttls_are_unreadable_still_publishes_a_number(
        self, monkeypatch
    ):
        """The fallback, end to end. `None` here would read as "no kills" to
        every caller that does not check the basis."""
        result = _metrics(
            monkeypatch,
            "some_task",
            {b"consecutive_failures": b"0"},
            {
                f"{TASK_METRICS_PREFIX}:some_task:starts": b"10",
                f"{TASK_METRICS_PREFIX}:some_task:successes": b"4",
            },
            {},
        )
        assert result["hard_kills_24h"] == 6
        assert result["hard_kills_basis"] == "raw_unnormalised:window_too_short"
