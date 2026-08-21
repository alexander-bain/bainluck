"""CAL-P086B (#2076) — the fallback, once source-chunking was refuted.

#2076's three options are now all closed except one:

* **Option 1, raise the budget** — refuted by measurement at 240 s, 900 s and
  1,350 s, each consuming essentially its whole budget with ``db_rows 0``.
  1,350,000 ms is the ceiling of the *Celery task's* shape, because the task is
  ``soft_time_limit=1800``.
* **Options 2/3, narrow or chunk** — refuted by plan (CAL-P086B): a tail-filtered
  chunk costs **1.0000x** the unfiltered fold, and the root-filtered form that
  DOES work leaves the binding chunk at **0.7616x** over a 3-way (not 7-way)
  partition, against a cost model measured understating this fold by >= 2.35x.

What is left is CAL-P079's finding, which was always the durable one: *the
reader belongs inside the dyno, next to the database, on a worker whose budget
is its own.* The twin worker is that — **except that its budget is not its own**.
It inherits Celery's ``soft_time_limit``, and a statement allowed to outlive the
soft limit is killed mid-flight with no artifact written.

A Heroku **one-off dyno** has no Celery limit over it. So the fallback is not
new code for the fold; it is letting the SAME code run on the host that can
afford it, and making sure its result survives the host's death — which is the
part that was missing. ``scripts/measure_published_twin.py`` wrote its artifact
to a FILE and to stdout, both of which die with a ``heroku run:detached`` dyno
(gotcha #48: never trust a detached run's stdout; prove it with a durable row).
"""

from __future__ import annotations

import pytest

from app.tasks.calibration_published_twin_worker import (
    DEFAULT_TIMEOUT_MS,
    MAX_TIMEOUT_MS,
    MIN_TIMEOUT_MS,
    ONE_OFF_MAX_TIMEOUT_MS,
    clamp_timeout_ms,
)


class TestTheTwoCeilingsAreDifferentHostsNotTwoOpinions:
    def test_the_celery_ceiling_is_unchanged(self):
        """The whole point is that nothing about the scheduled path moves."""
        assert MAX_TIMEOUT_MS == 1_350_000
        assert clamp_timeout_ms(10_000_000) == MAX_TIMEOUT_MS

    def test_the_one_off_ceiling_is_strictly_larger_and_clears_the_measured_floor(self):
        assert ONE_OFF_MAX_TIMEOUT_MS > MAX_TIMEOUT_MS
        # 901.96 s is the largest duration the fold has been MEASURED to consume
        # without finishing. A ceiling that cannot comfortably exceed it cannot
        # tell "slow" from "never finishes", which is the only question left.
        assert ONE_OFF_MAX_TIMEOUT_MS >= 3 * 901_960

    def test_the_larger_ceiling_is_only_reachable_by_asking_for_it(self):
        """A default that quietly grew would put a 90-minute statement on the
        beat schedule, which is the one outcome worse than the timeout."""
        assert clamp_timeout_ms(ONE_OFF_MAX_TIMEOUT_MS) == MAX_TIMEOUT_MS
        assert (
            clamp_timeout_ms(ONE_OFF_MAX_TIMEOUT_MS, ceiling=ONE_OFF_MAX_TIMEOUT_MS)
            == ONE_OFF_MAX_TIMEOUT_MS
        )

    @pytest.mark.parametrize(
        "given,ceiling,expected",
        [
            (0, MAX_TIMEOUT_MS, MIN_TIMEOUT_MS),
            (-5, ONE_OFF_MAX_TIMEOUT_MS, MIN_TIMEOUT_MS),
            ("nonsense", ONE_OFF_MAX_TIMEOUT_MS, DEFAULT_TIMEOUT_MS),
            (None, ONE_OFF_MAX_TIMEOUT_MS, DEFAULT_TIMEOUT_MS),
            (600_000, ONE_OFF_MAX_TIMEOUT_MS, 600_000),
            (10**12, ONE_OFF_MAX_TIMEOUT_MS, ONE_OFF_MAX_TIMEOUT_MS),
        ],
    )
    def test_clamping_is_the_same_function_under_both_ceilings(
        self, given, ceiling, expected
    ):
        assert clamp_timeout_ms(given, ceiling=ceiling) == expected

    def test_a_nonsense_ceiling_falls_back_to_the_celery_one(self):
        """Fail toward the SMALLER budget. A ceiling argument that arrives
        malformed must never widen anything."""
        assert clamp_timeout_ms(10_000_000, ceiling="lots") == MAX_TIMEOUT_MS
        assert clamp_timeout_ms(10_000_000, ceiling=None) == MAX_TIMEOUT_MS


class TestTheScriptCanBankThroughTheWorker:
    """The missing half of the in-dyno shape: a result that outlives the dyno."""

    def test_the_script_exposes_a_bank_flag(self):
        from scripts.measure_published_twin import _parse_args

        args = _parse_args(["--bank", "--timeout-ms", "5400000"])
        assert args.bank is True
        assert args.timeout_ms == 5_400_000

    def test_bank_is_off_by_default(self):
        from scripts.measure_published_twin import _parse_args

        assert _parse_args([]).bank is False

    @pytest.mark.asyncio
    async def test_bank_routes_through_run_published_twin_at_the_one_off_ceiling(
        self, monkeypatch
    ):
        """Not a re-implementation. The one-off path must run the SAME function
        the scheduled path runs, or the two drift and the gate that fired on a
        dyno is not the gate the beat would have fired."""
        import scripts.measure_published_twin as mod

        seen: dict = {}

        async def _fake(*, timeout_ms, ceiling=None):
            seen["timeout_ms"] = timeout_ms
            seen["ceiling"] = ceiling
            return {"verdict": "agrees", "measured": True, "durable": "published"}

        monkeypatch.setattr(mod, "_run_published_twin", _fake, raising=False)
        rc = await mod.main(["--bank", "--timeout-ms", "5400000"])
        assert rc == 0
        assert seen["timeout_ms"] == 5_400_000
        assert seen["ceiling"] == ONE_OFF_MAX_TIMEOUT_MS

    @pytest.mark.asyncio
    async def test_a_failed_durable_write_does_not_read_as_success(self, monkeypatch):
        """gotcha #53 on the one path where it costs the most: on a detached
        dyno the artifact IS the durable row, so an unbanked run has produced
        nothing a reader can ever see, whatever the verdict says."""
        import scripts.measure_published_twin as mod

        async def _fake(*, timeout_ms, ceiling=None):
            return {
                "verdict": "agrees",
                "measured": True,
                "durable": "error",
                "durable_error": "OperationalError: nope",
            }

        monkeypatch.setattr(mod, "_run_published_twin", _fake, raising=False)
        rc = await mod.main(["--bank"])
        assert rc == 3, "a lost artifact is its own exit code, not a silent 0"

    @pytest.mark.asyncio
    async def test_an_unmeasurable_banked_run_still_exits_2(self, monkeypatch):
        import scripts.measure_published_twin as mod

        async def _fake(*, timeout_ms, ceiling=None):
            return {
                "verdict": "unmeasurable",
                "measured": False,
                "durable": "published",
            }

        monkeypatch.setattr(mod, "_run_published_twin", _fake, raising=False)
        assert await mod.main(["--bank"]) == 2

    @pytest.mark.asyncio
    async def test_a_banked_disagreement_still_exits_1(self, monkeypatch):
        import scripts.measure_published_twin as mod

        async def _fake(*, timeout_ms, ceiling=None):
            return {"verdict": "disagrees", "measured": True, "durable": "published"}

        monkeypatch.setattr(mod, "_run_published_twin", _fake, raising=False)
        assert await mod.main(["--bank"]) == 1
