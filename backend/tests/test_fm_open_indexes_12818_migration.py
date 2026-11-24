"""Tests for #12818 open-market partial indexes migration safety and DDL."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

from app.utils.migration_lock_budget import batch_is_retryable

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic/versions/fm_open_indexes_12818.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("fm_open_indexes_12818", MIGRATION)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata_and_safety_rules():
    mod = _load_migration()
    text = MIGRATION.read_text(encoding="utf-8")

    assert len(mod.revision) <= 32
    assert mod.down_revision == "retired_team_redirects_13229"
    assert "MIGRATION-CLASS" in text
    assert f"alembic downgrade {mod.down_revision}" in text

    # Lock-retry compatibility: no COMMIT or autocommit_block inside migration body
    assert batch_is_retryable([text]) is True

    # Gotcha #31: executed body must never contain CONCURRENTLY
    executed = re.sub(r'"""(?:.|\n)*?"""', "", text)
    executed = re.sub(r"'''(?:.|\n)*?'''", "", executed)
    executed = "\n".join(re.sub(r"#.*$", "", ln) for ln in executed.splitlines())
    assert "CONCURRENTLY" not in executed.upper()


def test_upgrade_and_downgrade_emit_expected_partial_indexes(monkeypatch):
    mod = _load_migration()
    execs: list[str] = []
    drops: list[tuple[str, dict]] = []

    fake_op = SimpleNamespace(
        execute=lambda sql: execs.append(" ".join(str(sql).split())),
        drop_index=lambda name, **kw: drops.append((name, kw)),
    )
    monkeypatch.setattr(mod, "op", fake_op)

    mod.upgrade()
    assert len(execs) == 3

    vol, res, slug = execs
    assert "CREATE INDEX IF NOT EXISTS ix_fm_open_volume_24h" in vol
    assert "ON futures_markets (volume_24h DESC NULLS LAST, updated_at DESC NULLS LAST, id)" in vol
    assert "WHERE status = 'open'" in vol

    assert "CREATE INDEX IF NOT EXISTS ix_fm_open_resolution_date" in res
    assert "ON futures_markets (resolution_date ASC, volume_24h DESC NULLS LAST, id)" in res
    assert "WHERE status = 'open' AND resolution_date IS NOT NULL" in res

    assert "CREATE INDEX IF NOT EXISTS ix_fm_open_pm_event_slug" in slug
    assert "ON futures_markets ((market_metadata ->> 'polymarket_event_slug') text_pattern_ops)" in slug
    assert "WHERE status = 'open' AND (market_metadata ->> 'polymarket_event_slug') IS NOT NULL" in slug

    mod.downgrade()
    assert drops == [
        ("ix_fm_open_pm_event_slug", {"table_name": "futures_markets", "if_exists": True}),
        ("ix_fm_open_resolution_date", {"table_name": "futures_markets", "if_exists": True}),
        ("ix_fm_open_volume_24h", {"table_name": "futures_markets", "if_exists": True}),
    ]
