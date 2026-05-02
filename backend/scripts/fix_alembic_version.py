"""One-time fix: remove stale ba4924b27a0c from alembic_version.

The add_user_seen_mkts migration originally ran as a separate branch
(wrong down_revision), leaving both entries in alembic_version. Since
add_user_seen_mkts supersedes ba4924b27a0c, we remove the stale entry
so Alembic can proceed with the linear chain.
"""
import os

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/bainluck",
)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    versions = [r[0] for r in rows]
    print(f"Current alembic_version entries: {versions}")

    if "ba4924b27a0c" in versions and "add_user_seen_mkts" in versions:
        conn.execute(text("DELETE FROM alembic_version WHERE version_num = 'ba4924b27a0c'"))
        conn.commit()
        print("Removed stale ba4924b27a0c entry")
    else:
        print("No cleanup needed")
