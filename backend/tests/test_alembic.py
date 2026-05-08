"""Alembic migration safety tests.

Prevents the two classes of migration failures that have caused outages:
1. Multiple heads — alembic upgrade heads fails silently (Procfile || echo absorbs it)
2. Deleted migration files — alembic can't find the revision, blocks ALL future migrations
"""

from alembic.config import Config
from alembic.script import ScriptDirectory

ALEMBIC_INI = "alembic.ini"
MIN_MIGRATION_COUNT = 62


def _get_script_directory() -> ScriptDirectory:
    cfg = Config(ALEMBIC_INI)
    return ScriptDirectory.from_config(cfg)


class TestAlembicSingleHead:
    """Alembic must have exactly one head — multiple heads cause silent deploy failures."""

    def test_single_head(self):
        script = _get_script_directory()
        heads = list(script.get_heads())
        assert len(heads) == 1, (
            f"Multiple alembic heads detected: {heads}. "
            f"Run 'alembic merge heads -m \"merge\"' to fix."
        )


class TestAlembicMigrationCount:
    """Migration files must never be deleted — causes 'Can't locate revision' on deploy.

    This caused a full site outage on May 1-2, 2026 (gotcha #27).
    The count should only ever go UP. If this test fails, a migration
    file was deleted that Heroku's alembic_version table still references.
    """

    def test_migration_count_never_decreases(self):
        script = _get_script_directory()
        revisions = list(script.walk_revisions())
        assert len(revisions) >= MIN_MIGRATION_COUNT, (
            f"Expected at least {MIN_MIGRATION_COUNT} migration files, "
            f"found {len(revisions)}. A migration file may have been deleted. "
            f"NEVER delete a migration that has run on Heroku — it breaks "
            f"alembic upgrade heads permanently."
        )

    def test_all_revisions_form_a_chain(self):
        """Every revision must be reachable from head — no orphaned files."""
        script = _get_script_directory()
        heads = list(script.get_heads())
        if len(heads) != 1:
            return  # Single-head test will catch this
        reachable = set()
        for rev in script.walk_revisions(base="base", head=heads[0]):
            reachable.add(rev.revision)
        all_revs = {rev.revision for rev in script.walk_revisions()}
        orphaned = all_revs - reachable
        assert not orphaned, (
            f"Orphaned migration files not reachable from head: {orphaned}. "
            f"These may cause alembic errors."
        )
