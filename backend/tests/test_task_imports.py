"""Import and registration tests for untested task modules (#507)."""

import pytest


class TestDailyDigestTask:
    def test_import(self):
        from app.tasks.daily_digest import send_daily_digest
        assert callable(send_daily_digest)

    def test_registered(self):
        from app.tasks import celery_app
        assert "app.tasks.send_daily_digest_task" in celery_app.tasks or any(
            "daily_digest" in k for k in celery_app.tasks
        )


class TestExportEngagementTask:
    def test_import(self):
        from app.tasks.export_engagement import _export_engagement_impl
        assert callable(_export_engagement_impl)

    def test_registered(self):
        from app.tasks import celery_app
        assert any("export_engagement" in k for k in celery_app.tasks)


class TestGameStateBackfillTask:
    def test_import(self):
        from app.tasks.game_state_backfill import _backfill_game_state
        assert callable(_backfill_game_state)


class TestTeamIdentityBackfillTask:
    def test_import(self):
        from app.tasks.team_identity_backfill import _backfill_team_identities
        assert callable(_backfill_team_identities)


class TestPrecomputeInterestingnessTask:
    def test_import(self):
        from app.tasks.precompute_interestingness import _precompute_interestingness
        assert callable(_precompute_interestingness)

    def test_registered(self):
        from app.tasks import celery_app
        assert any("precompute_interestingness" in k for k in celery_app.tasks)
