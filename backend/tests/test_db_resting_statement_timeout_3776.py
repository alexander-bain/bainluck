"""Every connection rests at a FINITE ``statement_timeout`` — #3776, ship #4456.

The defect these guard: production `pg_settings` on 2026-09-09 read
``statement_timeout`` with ``boot_val = reset_val = 0``, i.e. the server-wide
default is *no timeout*, and neither engine set one at connect time. So an
unarmed statement had no bound, and every ``SET LOCAL`` reverted to unbounded
the instant its transaction ended. A worker SIGKILLed by a Heroku release left
its Postgres backend running forever — 2d18h measured on 2026-09-05 — pinning
the global xmin horizon so autovacuum reclaimed nothing anywhere in the
database.

What is asserted here is deliberately the RELATION, not a copied number
(#2779's lesson: a hand-pinned table goes stale and the guard stops meaning
anything). The resting bound must sit in the band between "longer than
anything we legitimately run" and "short enough that an orphan self-clears",
and both edges are read from the constants that define them.
"""

import app.services.database as db_mod
from app.services.database import DB_STATEMENT_TIMEOUT_MS, build_connect_args
from app.utils.calibration_phase_ledger import HARD_LIMIT_MS


PROD_URL = "postgresql+asyncpg://u:p@ec2-1-2-3-4.compute.amazonaws.com:5432/d"
LOCAL_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/bainluck"


class TestRestingBoundIsFiniteAndBanded:
    def test_bound_is_finite_and_positive(self):
        # 0 is not "no opinion" in Postgres — it is the DISABLED value, and it
        # is precisely the state that produced the 2d18h orphan.
        assert isinstance(DB_STATEMENT_TIMEOUT_MS, int)
        assert DB_STATEMENT_TIMEOUT_MS > 0

    def test_bound_exceeds_the_longest_statement_we_legitimately_run(self):
        # The calibration beat is the longest-running DB task in the app; its
        # Celery hard limit is the ceiling on how long any single statement it
        # issues can possibly be alive and still belong to a live worker. A
        # resting bound below that would start cancelling real work.
        assert DB_STATEMENT_TIMEOUT_MS > HARD_LIMIT_MS, (
            f"resting bound {DB_STATEMENT_TIMEOUT_MS} ms is at or below the "
            f"calibration hard limit {HARD_LIMIT_MS} ms — it would cancel work "
            "that is still legitimately owned by a live worker"
        )

    def test_bound_exceeds_the_main_computes_own_armed_bound(self):
        # Read from the module that arms it rather than restated, so raising
        # the arm without raising the rest cannot pass silently.
        from app.tasks.precompute_calibration import _MAIN_COMPUTE_STMT_TIMEOUT_MS

        assert DB_STATEMENT_TIMEOUT_MS > _MAIN_COMPUTE_STMT_TIMEOUT_MS

    def test_bound_is_not_widened_back_toward_forever(self):
        # The upper edge is what stops a future "just give it more room" from
        # restoring the defect under a different spelling. Two hours is already
        # 2.7x the longest thing we run; a multi-hour statement is the bug.
        assert DB_STATEMENT_TIMEOUT_MS <= 2 * 60 * 60 * 1000


class TestBothEnginesCarryIt:
    """One engine hardened and the other not is how #3776 happened."""

    def test_web_engine_connect_args_carry_the_timeout(self):
        args = db_mod.connect_args
        assert args.get("server_settings", {}).get("statement_timeout") == str(
            DB_STATEMENT_TIMEOUT_MS
        ), f"web engine connect_args missing the resting bound: {args}"

    def test_task_engine_passes_the_timeout_to_its_engine(self, monkeypatch):
        # The task engine is the one that serves the calibration build, and it
        # is the one that was missing the bound.
        #
        # Asserted on what ``_get_task_engine`` actually HANDS the engine
        # factory, not on its source text. A source scan was the first draft
        # and it could not fail: the function's own docstring names
        # ``build_connect_args``, so a mutation that ripped the call out and
        # restored the old inline copy still matched the grep and the guard
        # went green. Intercepting the factory costs nothing (no connection is
        # opened) and cannot be satisfied by prose.
        from app.tasks import base as task_base

        captured: dict = {}

        def fake_create_async_engine(url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return object()

        monkeypatch.setattr(
            task_base, "create_async_engine", fake_create_async_engine
        )
        task_base._get_task_engine()

        args = captured["kwargs"]["connect_args"]
        assert args.get("server_settings", {}).get("statement_timeout") == str(
            DB_STATEMENT_TIMEOUT_MS
        ), f"task engine connect_args missing the resting bound: {args}"

    def test_builder_output_is_what_the_task_engine_would_pass(self):
        args = build_connect_args(PROD_URL)
        assert args["server_settings"]["statement_timeout"] == str(
            DB_STATEMENT_TIMEOUT_MS
        )


class TestBuilderPreservesExistingBehaviour:
    def test_production_url_still_requires_ssl(self):
        assert build_connect_args(PROD_URL)["ssl"] == "require"

    def test_local_url_still_omits_ssl(self):
        assert "ssl" not in build_connect_args(LOCAL_URL)

    def test_local_url_still_gets_the_timeout(self):
        # Dev and CI must rest at the same bound as production, or the first
        # place an unbounded statement is observed is production.
        assert "server_settings" in build_connect_args(LOCAL_URL)

    def test_non_asyncpg_url_gets_no_server_settings(self):
        # sqlite has no startup-parameter channel; passing one is a TypeError
        # at connect time, which would take the whole test suite down.
        args = build_connect_args("sqlite+aiosqlite:///:memory:")
        assert "server_settings" not in args
