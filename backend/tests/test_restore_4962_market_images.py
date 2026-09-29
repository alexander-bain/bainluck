"""Execute bounded restore SQL; SQLite proves predicates, not PG scheduling."""

import sqlite3
from types import SimpleNamespace

import pytest

from scripts import restore_4962_market_images as restore
from scripts.repair_4962_market_image_repick import PINNED_SPECIMENS


@pytest.fixture
def case():
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE futures_markets (id INTEGER PRIMARY KEY, name TEXT, llm_sport_category TEXT, status TEXT, image_url TEXT, image_width INTEGER, image_height INTEGER)"
    )
    db.execute(
        f"CREATE TABLE {restore.BACKUP_TABLE} (id INTEGER PRIMARY KEY, image_url TEXT, image_width INTEGER, image_height INTEGER)"
    )
    rows = []
    for market_id, (name, category, photo) in PINNED_SPECIMENS.items():
        row = SimpleNamespace(
            id=market_id,
            name=name,
            llm_sport_category=category,
            status="open",
            image_url=f"https://images.pexels.com/photos/{photo}/pexels-photo-{photo}.jpeg",
            image_width=940,
            image_height=None,
            current_image=None,
            current_width=None,
            current_height=None,
        )
        rows.append(row)
        db.execute(
            "INSERT INTO futures_markets VALUES (?, ?, ?, ?, NULL, NULL, NULL)",
            (market_id, name, category, row.status),
        )
        db.execute(
            f"INSERT INTO {restore.BACKUP_TABLE} VALUES (?, ?, ?, ?)",
            (market_id, row.image_url, row.image_width, row.image_height),
        )
    # An old backup outside the repair must never be restored.
    db.execute(
        "INSERT INTO futures_markets VALUES (1, 'Other', 'golf', 'open', NULL, NULL, NULL)"
    )
    db.execute(f"INSERT INTO {restore.BACKUP_TABLE} VALUES (1, 'other.jpg', 1, 2)")
    db.commit()

    class Session:
        async def execute(self, statement, params):
            return db.execute(str(statement), params)

        async def rollback(self):
            db.rollback()

    yield db, Session(), rows
    db.close()


async def test_valid_restore_restores_two_exactly_and_ignores_other_backup(case):
    db, session, rows = case
    assert await restore.restore_captured_rows(session, rows)
    for row in rows:
        assert db.execute(
            "SELECT image_url, image_width, image_height FROM futures_markets WHERE id=?",
            (row.id,),
        ).fetchone() == (row.image_url, 940, None)
    assert db.execute(
        "SELECT image_url FROM futures_markets WHERE id=1"
    ).fetchone() == (None,)


@pytest.mark.parametrize(
    "table,column,value",
    [
        ("futures_markets", "image_url", "new-good.jpg"),
        ("futures_markets", "image_width", 100),
        ("futures_markets", "image_height", 100),
        ("futures_markets", "name", "Different identity"),
        ("futures_markets", "llm_sport_category", "politics"),
        ("futures_markets", "status", "resolved"),
        (restore.BACKUP_TABLE, "image_url", "new-backup.jpg"),
        (restore.BACKUP_TABLE, "image_width", 100),
        (restore.BACKUP_TABLE, "image_height", 100),
    ],
)
async def test_change_after_capture_refuses_whole_batch_preserving_writer(
    case, table, column, value
):
    db, session, rows = case
    db.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (value, rows[1].id))
    db.commit()
    assert not await restore.restore_captured_rows(session, rows)
    assert db.execute(
        "SELECT image_url FROM futures_markets WHERE id=?", (rows[0].id,)
    ).fetchone() == (None,)
    assert db.execute(
        f"SELECT {column} FROM {table} WHERE id=?", (rows[1].id,)
    ).fetchone() == (value,)


@pytest.mark.parametrize(
    "changes",
    [
        dict(name="Different identity"),
        dict(llm_sport_category="golf"),
        dict(image_url="new-backup.jpg"),
        dict(current_image="new-good.jpg"),
        dict(current_width=100),
        dict(current_height=100),
    ],
)
async def test_already_changed_snapshot_refuses_without_partial_restore(case, changes):
    db, session, rows = case
    for field, value in changes.items():
        setattr(rows[1], field, value)
    assert not await restore.restore_captured_rows(session, rows)
    assert db.execute(
        "SELECT image_url FROM futures_markets WHERE id=?", (rows[0].id,)
    ).fetchone() == (None,)


def test_restore_scope_cannot_widen():
    assert restore._parse_ids("109295") == (109295,)
    with pytest.raises(ValueError, match="only narrow"):
        restore._parse_ids("109295,1")
